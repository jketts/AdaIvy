"""The Phase 4C hybrid-retrieval benchmark harness.

Reproduces the eight metrics and gates of
`docs/phase-4c/HYBRID_RETRIEVAL_BENCHMARK_V1.md` on the *fused* ordering.

Honesty rules carried over from the frozen lexical baseline:

* "No data" is not "measured zero". A ratio with a zero denominator reports
  `None` alongside its numerator and denominator, and its gate status is
  `undetermined` -- never `pass`, never `0`.
* Every query appears in the report, including zero-hit queries, duplicate
  hits, inapplicable hits, missed golds, and exclusions. Nothing is filtered.
  An excluded document is absent from `ordered_ids` and still fully present in
  `hits`, in `fused_candidate_ids`, and in `excluded_ids`, with its absence
  operator and evidence noun recorded.
* Declared provenance is assembled from the same constants that build the
  executed SQL, and the executed SQL text is reported verbatim.
* Timestamps, elapsed milliseconds, byte counts, and raw float scores are
  operational. Canonical report identity binds the corpus, gold-query, and
  alias fixture hashes, the ordered result ids, the classifications, and the
  metrics.

Retrieval is candidate generation. Fused rank, metric success, and agreement
between signals are not evidence, and nothing here creates a premise, a
warrant, an applicability judgement, or a graph admission.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import aliases as alias_module
from . import disclaimer as disclaimer_module
from . import lexical as lexical_module
from . import semantic as semantic_module
from .aliases import ALIAS_PHRASE_POINTS, AliasExpansionSignal
from .bounds import (
    BOUNDS,
    CATEGORY_COUNTS,
    GATE_COMPARISONS,
    Phase4CValidationError,
    SCHEMA_VERSION,
    THRESHOLD_KEYS,
    TOP_K_BY_CATEGORY,
)
from .disclaimer import (
    ABSENCE_OPERATORS,
    EVIDENCE_NOUNS,
    OBJECT_LEVEL_CUES,
    SelfDisclaimerSignal,
)
from .fixtures import (
    AliasEntry,
    CORPUS_MANIFEST_NAME,
    GOLD_QUERIES_NAME,
    NAME_ALIASES_NAME,
    load_aliases,
    load_corpus,
    load_gold,
)
from .fusion import fuse, retained_ids
from .lexical import LexicalIndex, corpus_rows, derived_db_bytes, open_index
from .ports import (
    AliasSignal,
    DisclaimerSignal,
    LexicalSignal,
    SemanticPartitionIdentity,
    SemanticSignal,
)
from .semantic import (
    SemanticPartitionSignal,
    default_partition_root,
    load_semantic_partition,
)
from .serialization import canonical_bytes, content_hash, operational_hash, sha256_bytes

METHOD = "phase4c-hybrid-score-space-fusion-with-exclusion"
FUSION_METHOD = "score-space-additive-fusion-with-candidate-exclusion"


@dataclass(frozen=True)
class Measurement:
    """A ratio plus the counts that produced it.

    `value` is `None` when the denominator is zero: no data measured, which is
    not the same claim as a measured zero and can never pass a gate.
    """

    numerator: int
    denominator: int

    @property
    def value(self) -> float | None:
        return None if self.denominator == 0 else self.numerator / self.denominator

    def as_support(self) -> dict[str, Any]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "defined": self.denominator != 0,
        }


def micro_recall(results: Sequence[dict[str, Any]], category: str) -> Measurement:
    found = total = 0
    for item in results:
        if item["category"] != category:
            continue
        gold = set(item["relevant_ids"])
        found += len(gold & set(item["ordered_ids"]))
        total += len(gold)
    return Measurement(found, total)


def gate_status(threshold_key: str, threshold: Any, measured: Any) -> str:
    if measured is None:
        return "undetermined"
    comparison = GATE_COMPARISONS[threshold_key][1]
    if comparison == "at_least":
        return "pass" if measured >= threshold else "fail"
    if comparison == "at_most":
        return "pass" if measured <= threshold else "fail"
    return "pass" if measured == threshold else "fail"


def compute_measurements(
    results: Sequence[dict[str, Any]],
    *,
    duplicate_numerator: int,
    duplicate_denominator: int,
) -> dict[str, Measurement]:
    relevant_applicable = relevant_retrieved = 0
    for item in results:
        if item["category"] != "applicability":
            continue
        retrieved = set(item["relevant_ids"]) & set(item["ordered_ids"])
        relevant_retrieved += len(retrieved)
        relevant_applicable += len(retrieved & set(item["applicable_ids"]))
    return {
        "necessary_lemma_recall_at_5": micro_recall(results, "necessary_lemma"),
        "applicability_precision_at_5": Measurement(
            relevant_applicable, relevant_retrieved
        ),
        "contradiction_recall_at_5": micro_recall(results, "contradiction"),
        "notation_variant_recall_at_5": micro_recall(results, "notation_variant"),
        "renamed_known_result_recall_at_10": micro_recall(
            results, "renamed_known_result"
        ),
        "duplicate_rate_at_5": Measurement(duplicate_numerator, duplicate_denominator),
    }


def declared_method(
    *,
    absence_operators: Sequence[Sequence[str]],
    evidence_nouns: Sequence[str],
    object_level_cues: Sequence[str],
    alias_phrase_points: float,
    semantic_identity: SemanticPartitionIdentity,
    semantic_tier_points: int,
) -> dict[str, Any]:
    return {
        "method": METHOD,
        "fusion": {
            "method": FUSION_METHOD,
            "space": "score",
            "rank_only_combiner": False,
            "reciprocal_rank_fusion": False,
            "lexical_orientation": "relevance = -bm25 (monotone, margins preserved)",
            "composition": (
                "fused_score = (-bm25) + alias_points + semantic_points"
            ),
            "exclusion_rule": (
                "an excluded candidate is removed from the ordering; no score "
                "changes and no penalty term exists"
            ),
            "ordering": "fused_score DESC, document_id ASC",
        },
        "lexical_signal": lexical_module.declared_method(),
        "disclaimer_signal": disclaimer_module.declared_method(
            absence_operators, evidence_nouns, object_level_cues
        ),
        "alias_signal": alias_module.declared_method(alias_phrase_points),
        "semantic_signal": semantic_module.declared_method(
            semantic_identity, semantic_tier_points=semantic_tier_points
        ),
    }


def _alias_table_coverage(
    signal: AliasSignal,
    entries: Sequence[AliasEntry],
    exercised: dict[str, list[str]],
) -> list[dict[str, Any]]:
    coverage: list[dict[str, Any]] = []
    for entry in entries:
        matched: tuple[str, ...] = ()
        if isinstance(signal, AliasExpansionSignal):
            matched = signal.matched_document_ids(entry)
        query_ids = sorted(exercised.get(entry.identifier, ()))
        coverage.append(
            {
                "entry_id": entry.identifier,
                "alias": entry.alias,
                "content_phrase_count": len(entry.content_phrases),
                "exercised_by_query_ids": query_ids,
                "matched_document_ids": list(matched),
                "exercised_by_no_query": not query_ids,
                "matches_no_document": not matched,
            }
        )
    return sorted(coverage, key=lambda item: item["entry_id"])


def evaluate_hybrid(
    fixtures: Path,
    *,
    reverse_insertion: bool = False,
    alias_entries: Sequence[AliasEntry] | None = None,
    absence_operators: Sequence[Sequence[str]] | None = None,
    evidence_nouns: Sequence[str] | None = None,
    object_level_cues: Sequence[str] | None = None,
    alias_phrase_points: float | None = None,
    semantic_partition: Path | None = None,
    lexical_signal: LexicalSignal | None = None,
    disclaimer_signal: DisclaimerSignal | None = None,
    alias_signal: AliasSignal | None = None,
    semantic_signal: SemanticSignal | None = None,
) -> dict[str, Any]:
    """Run the benchmark and return a canonical report.

    Every keyword after `reverse_insertion` exists for the ADR-0032 acceptance
    suite, which must demonstrate the slice's boundaries as properties rather
    than exercise a happy path. The CLI never sets any of them. Any deviation
    from the frozen configuration is recorded in `signal_configuration.
    overrides`, which is inside `content_hash`, so a report produced with an
    override can never collide with a report produced without one.
    """

    started = time.monotonic()
    documents = load_corpus(fixtures)
    queries, thresholds = load_gold(fixtures, documents)
    table = tuple(alias_entries) if alias_entries is not None else load_aliases(fixtures)

    operators = (
        tuple(tuple(item) for item in absence_operators)
        if absence_operators is not None
        else ABSENCE_OPERATORS
    )
    nouns = tuple(evidence_nouns) if evidence_nouns is not None else EVIDENCE_NOUNS
    neutral_cues = (
        tuple(object_level_cues) if object_level_cues is not None else OBJECT_LEVEL_CUES
    )
    points = ALIAS_PHRASE_POINTS if alias_phrase_points is None else alias_phrase_points
    # ADR-0070 freezes the tier points before measurement, so there is no
    # override parameter for them: the only way to change the semantic
    # contribution is to edit the frozen constant, which is a reviewable act.
    tier_points = BOUNDS.semantic_tier_points

    overrides: list[str] = []
    if alias_entries is not None:
        overrides.append("alias_entries")
    if absence_operators is not None:
        overrides.append("absence_operators")
    if evidence_nouns is not None:
        overrides.append("evidence_nouns")
    if object_level_cues is not None:
        overrides.append("object_level_cues")
    if alias_phrase_points is not None:
        overrides.append("alias_phrase_points")
    if semantic_partition is not None:
        overrides.append("semantic_partition")
    if lexical_signal is not None:
        overrides.append("lexical_signal")
    if disclaimer_signal is not None:
        overrides.append("disclaimer_signal")
    if alias_signal is not None:
        overrides.append("alias_signal")
    if semantic_signal is not None:
        overrides.append("semantic_signal")

    metadata = {document.identifier: document for document in documents}
    rows = sorted(corpus_rows(documents), reverse=reverse_insertion)
    connection = open_index(rows)
    try:
        lexical: LexicalSignal = lexical_signal or LexicalIndex(connection)
        disclaimer: DisclaimerSignal = disclaimer_signal or SelfDisclaimerSignal(
            documents,
            absence_operators=operators,
            evidence_nouns=nouns,
            object_level_cues=neutral_cues,
        )
        expander: AliasSignal = alias_signal or AliasExpansionSignal(documents, table)
        # A missing partition is a refusal, not a degradation. A benchmark that
        # quietly dropped a signal would report a number for a system that was
        # not tested, so the partition is loaded before the first query and its
        # absence raises rather than disabling the signal.
        semantic: SemanticSignal = semantic_signal or SemanticPartitionSignal(
            load_semantic_partition(
                semantic_partition
                if semantic_partition is not None
                else default_partition_root(fixtures)
            )
        )
        semantic_identity = semantic.partition_identity()

        results: list[dict[str, Any]] = []
        operational_results: list[dict[str, Any]] = []
        zero_hit_query_ids: list[str] = []
        exercised: dict[str, list[str]] = {}
        duplicate_hits = total_hits = 0

        for query in queries:
            raw_bytes = len(query.query.encode("utf-8"))
            if raw_bytes > BOUNDS.max_query_bytes:
                raise Phase4CValidationError(
                    f"query {query.identifier}: {raw_bytes} raw UTF-8 bytes exceeds "
                    f"the {BOUNDS.max_query_bytes}-byte bound"
                )
            candidates = lexical.candidates(
                query.query, limit=BOUNDS.max_candidates_per_signal
            )
            expansions = expander.expand(
                query.query, limit=BOUNDS.max_candidates_per_signal
            )
            # Keyed on the query IDENTIFIER: the query vector is replayed from
            # the frozen partition and never computed inside this path.
            credits = semantic.credits(
                query.identifier, limit=BOUNDS.semantic_candidate_limit
            )
            for expansion in expansions:
                exercised.setdefault(expansion.entry_id, []).append(query.identifier)

            lexical_ids = [candidate.document_id for candidate in candidates]
            pre_ids = list(lexical_ids)
            for expansion in expansions:
                for document_id, _phrases in expansion.matched:
                    if document_id not in pre_ids:
                        pre_ids.append(document_id)
            for credit in credits:
                if credit.document_id not in pre_ids:
                    pre_ids.append(credit.document_id)
            verdicts = disclaimer.verdicts(query.query, pre_ids)
            hits = fuse(
                candidates,
                expansions,
                verdicts,
                credits=credits,
                alias_phrase_points=points,
                semantic_tier_points=tier_points,
            )

            excluded_ids = sorted(hit.document_id for hit in hits if hit.excluded)
            if set(excluded_ids) - set(pre_ids):
                raise Phase4CValidationError(
                    "the disclaimer signal introduced a document"
                )

            # `ordered_ids` is the post-exclusion result list: every excluded
            # candidate is removed, then the top-k cutoff is applied. Nothing is
            # removed from `hits` or `fused_candidate_ids`.
            ordered_ids = list(retained_ids(hits)[: query.top_k])
            if not ordered_ids:
                zero_hit_query_ids.append(query.identifier)

            seen_groups: set[str] = set()
            duplicate_ids: list[str] = []
            # Duplicate-rate@5 uses the same cutoff for every query, including
            # the renamed-known-result controls whose recall cutoff is ten.
            for identifier in ordered_ids[: BOUNDS.duplicate_cutoff]:
                total_hits += 1
                group = metadata[identifier].duplicate_group
                if group is None:
                    continue
                if group in seen_groups:
                    duplicate_hits += 1
                    duplicate_ids.append(identifier)
                seen_groups.add(group)

            entry: dict[str, Any] = {
                "id": query.identifier,
                "category": query.category,
                "query": query.query,
                "query_bytes": raw_bytes,
                "top_k": query.top_k,
                "relevant_ids": list(query.relevant_ids),
                "lexical_candidate_ids": lexical_ids,
                "fused_candidate_ids": [hit.document_id for hit in hits],
                "ordered_ids": ordered_ids,
                "missed_relevant_ids": sorted(
                    set(query.relevant_ids) - set(ordered_ids)
                ),
                "duplicate_ids_at_5": duplicate_ids,
                "inapplicable_retrieved_ids": sorted(
                    identifier
                    for identifier in ordered_ids
                    if metadata[identifier].applicability != "applicable"
                ),
                "zero_hit": not ordered_ids,
                "excluded_ids": excluded_ids,
                "alias_introduced_ids": sorted(
                    hit.document_id
                    for hit in hits
                    if "alias" in hit.signals and "lexical" not in hit.signals
                ),
                "semantic_candidate_ids": [
                    credit.document_id for credit in credits
                ],
                "semantic_introduced_ids": sorted(
                    hit.document_id
                    for hit in hits
                    if hit.signals == ("semantic",)
                ),
                "alias_expansions": [
                    {
                        "entry_id": expansion.entry_id,
                        "alias": expansion.alias,
                        "matched": [
                            {"document_id": document_id, "matched_phrases": list(phrases)}
                            for document_id, phrases in expansion.matched
                        ],
                    }
                    for expansion in expansions
                ],
                "hits": [hit.semantic_projection() for hit in hits],
            }
            if query.applicable_ids is not None:
                entry["applicable_ids"] = list(query.applicable_ids)
            results.append(entry)
            operational_results.append(
                {
                    "id": query.identifier,
                    "hits": [hit.operational_projection() for hit in hits],
                }
            )

        measurements = compute_measurements(
            results,
            duplicate_numerator=duplicate_hits,
            duplicate_denominator=total_hits,
        )
        metrics: dict[str, Any] = {name: item.value for name, item in measurements.items()}
        metrics.update(
            {
                "external_spend_usd": 0,
                "network_calls": 0,
                "model_or_api_calls": 0,
                "downloaded_artifacts": 0,
            }
        )
        metric_support = {name: item.as_support() for name, item in measurements.items()}

        gate_evaluation = {
            key: {
                "metric": GATE_COMPARISONS[key][0],
                "comparison": GATE_COMPARISONS[key][1],
                "threshold": thresholds[key],
                "measured": metrics[GATE_COMPARISONS[key][0]],
                "status": gate_status(
                    key, thresholds[key], metrics[GATE_COMPARISONS[key][0]]
                ),
            }
            for key in THRESHOLD_KEYS
        }
        statuses = [item["status"] for item in gate_evaluation.values()]

        db_bytes = derived_db_bytes(connection)
        if db_bytes > BOUNDS.max_derived_db_bytes:
            raise Phase4CValidationError(
                f"derived benchmark database bound exceeded: "
                f"{db_bytes} > {BOUNDS.max_derived_db_bytes}"
            )

        semantic = {
            "schema_version": SCHEMA_VERSION,
            "method": METHOD,
            "declared_method": declared_method(
                absence_operators=operators,
                evidence_nouns=nouns,
                object_level_cues=neutral_cues,
                alias_phrase_points=points,
                semantic_identity=semantic_identity,
                semantic_tier_points=tier_points,
            ),
            "signal_configuration": {
                "lexical_signal_id": getattr(lexical, "signal_id", "unknown"),
                "disclaimer_signal_id": getattr(disclaimer, "signal_id", "unknown"),
                "alias_signal_id": getattr(expander, "signal_id", "unknown"),
                "semantic_signal_id": getattr(semantic, "signal_id", "unknown"),
                "alias_entry_count": len(table),
                "overrides": overrides,
            },
            "resource_bounds": {
                **BOUNDS.to_record(),
                "policy_sha256": BOUNDS.policy_sha256,
                "top_k_by_category": dict(sorted(TOP_K_BY_CATEGORY.items())),
                "category_counts": dict(sorted(CATEGORY_COUNTS.items())),
            },
            "corpus_manifest_hash": sha256_bytes(
                (fixtures / CORPUS_MANIFEST_NAME).read_bytes()
            ),
            "gold_queries_hash": sha256_bytes((fixtures / GOLD_QUERIES_NAME).read_bytes()),
            "name_aliases_hash": sha256_bytes((fixtures / NAME_ALIASES_NAME).read_bytes()),
            # ADR-0070: the partition binds report identity. A report built
            # against a different partition is a different report, so both the
            # key and the manifest hash sit inside `content_hash` alongside the
            # corpus, gold-query, and alias fixture hashes.
            "semantic_partition_key": semantic_identity.partition_key_string,
            "semantic_partition_manifest_hash": semantic_identity.manifest_hash,
            "source_hashes": {
                document.identifier: document.source_hash for document in documents
            },
            "alias_table_coverage": _alias_table_coverage(expander, table, exercised),
            "results": results,
            "zero_hit_query_ids": zero_hit_query_ids,
            "metrics": metrics,
            "metric_support": metric_support,
            "proposed_thresholds": thresholds,
            "gate_evaluation": gate_evaluation,
            "gate_summary": {
                "pass": statuses.count("pass"),
                "fail": statuses.count("fail"),
                "undetermined": statuses.count("undetermined"),
                "overall": "pass" if set(statuses) == {"pass"} else "not_pass",
            },
        }

        elapsed_ms = int((time.monotonic() - started) * 1000)
        if elapsed_ms > BOUNDS.max_elapsed_ms:
            raise Phase4CValidationError(
                f"parent-process time bound exceeded: {elapsed_ms} ms"
            )
        operational = {
            "derived_db_bytes": db_bytes,
            "elapsed_ms": elapsed_ms,
            "reverse_insertion": reverse_insertion,
            "sqlite_library_version": sqlite3.sqlite_version,
            "results": operational_results,
        }
        report = dict(semantic)
        report["content_hash"] = content_hash(semantic)
        report["operational"] = operational
        report["operational_hash"] = operational_hash(operational)
        report_bytes = len(canonical_bytes(report))
        if report_bytes > BOUNDS.max_report_bytes:
            raise Phase4CValidationError(
                f"report byte bound exceeded: {report_bytes} > {BOUNDS.max_report_bytes}"
            )
        return report
    finally:
        connection.close()


def verify_report(report: dict[str, Any]) -> dict[str, Any]:
    """Recompute both hashes of an emitted report. Fails closed on mismatch."""

    if not isinstance(report, dict):
        raise Phase4CValidationError("report must be an object")
    for key in ("schema_version", "content_hash", "operational", "operational_hash"):
        if key not in report:
            raise Phase4CValidationError(f"report is missing {key}")
    if report["schema_version"] != SCHEMA_VERSION:
        raise Phase4CValidationError("unsupported report schema version")
    operational = report["operational"]
    if not isinstance(operational, dict):
        raise Phase4CValidationError("report operational section must be an object")
    recomputed = content_hash(report)
    if recomputed != report["content_hash"]:
        raise Phase4CValidationError(
            f"content hash mismatch: recomputed {recomputed}, "
            f"declared {report['content_hash']}"
        )
    recomputed_operational = operational_hash(operational)
    if recomputed_operational != report["operational_hash"]:
        raise Phase4CValidationError(
            f"operational hash mismatch: recomputed {recomputed_operational}, "
            f"declared {report['operational_hash']}"
        )
    return {
        "content_hash": report["content_hash"],
        "operational_hash": report["operational_hash"],
        "schema_version": report["schema_version"],
        "verified": True,
    }


__all__ = [
    "FUSION_METHOD",
    "METHOD",
    "Measurement",
    "compute_measurements",
    "declared_method",
    "evaluate_hybrid",
    "gate_status",
    "micro_recall",
    "verify_report",
]
