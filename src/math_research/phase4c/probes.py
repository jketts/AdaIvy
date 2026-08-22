"""The ten ADR-0070 falsifiability probes for the semantic signal.

ADR-0034 established the standard and ADR-0070 restates it: `probes_flipped ==
probes_total` gates the slice, because a rule that cannot be made to fail proves
nothing.

Every probe has two legs and BOTH are pinned. The `baseline` leg exercises the
accepted path; the `mutated` leg makes one named change. A probe flips only when
each leg produces exactly its pinned observation and the two differ, so a probe
can pass neither by always refusing nor by never firing.

Three probes mutate an INPUT to the production path and their mutated leg is a
refusal: the partition-key mismatch, the missing partition, and the candidate
bound. The other seven state a POSITIVE property -- the inversion ceiling,
exactness of the module text, the tie-breaking rule, partition binding, override
recording, zero spend, and the true-no-op of the disabled signal -- so their
mutated leg fires the same instrument at a deliberately wrong subject instead.
Which of the two a probe is is recorded on the probe as `mutation_target` rather
than left to a reader to infer.

Nothing here is an authority. A flipped probe records that a boundary is
enforced; it creates no applicability record, no premise, no graph admission, no
novelty or significance assessment, and no mathematical warrant.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..embedding.partition import (
    ARTIFACT_KIND_DOCUMENT,
    ARTIFACT_KIND_QUERY,
    Partition,
    PartitionKey,
    VectorArtifact,
)
from ..embedding.readpath import sweep_source
from .aliases import ALIAS_PHRASE_POINTS, AliasExpansionSignal
from .benchmark import evaluate_hybrid, gate_status
from .bounds import (
    BOUNDS,
    MAXIMUM_SEMANTIC_TIER_CREDIT,
    Phase4CValidationError,
    semantic_tier_credit,
)
from .disclaimer import SelfDisclaimerSignal
from .fixtures import load_aliases, load_corpus, load_gold
from .fusion import fuse
from .lexical import LexicalIndex, corpus_rows, open_index
from .ports import LexicalCandidate, SemanticCredit, SemanticPartitionIdentity
from .semantic import (
    DisabledSemanticSignal,
    LoadedPartition,
    SemanticPartitionSignal,
    declared_partition_key,
    default_partition_root,
    load_semantic_partition,
)
from .serialization import canonical_bytes, sha256_bytes

PROBE_REPORT_SCHEMA_VERSION = "adaivy.phase4c-semantic-probe-report.v1"

#: A model identifier that is NOT the declared one. Used only to make the
#: partition-mismatch branch fire; nothing is written and no partition under
#: this key exists.
_OTHER_MODEL_IDENTIFIER = "adaivy-cooccurrence-anchor-v2"
#: A directory name deliberately never created, so the missing-partition branch
#: is exercised without writing anything anywhere.
_ABSENT_PARTITION_DIRNAME = "phase4c-semantic-absent-by-construction"

#: Source text that is deliberately inexact, so the exactness instrument can be
#: shown to fire before it is trusted to report `semantic.py` clean.
_INEXACT_SUBJECT = "def inexact(a, b):\n    return (a * 1.5) + (b / 2)\n"

_REFUSED = "refused"
_ACCEPTED = "accepted"


# --------------------------------------------------------------------------
# In-memory partitions, built without touching the disk at all.
# --------------------------------------------------------------------------


def _stub_artifact(
    document_id: str, coordinates: tuple[int, ...], kind: str
) -> VectorArtifact:
    seal = sha256_bytes(canonical_bytes([document_id, list(coordinates), kind]))
    return VectorArtifact(
        document_id=document_id,
        source_content_hash=seal,
        coordinates=coordinates,
        content_hash=seal,
        artifact_kind=kind,
    )


def _tie_partition() -> LoadedPartition:
    """Two corpus documents with IDENTICAL coordinates, plus one query vector.

    The ids are chosen so that the descending-id document is the one a naive
    implementation would emit first: `zzz-tied-document` sorts after
    `aaa-tied-document`, so an ordering that came out of a set, a dictionary, or
    the caller's insertion order would be visible.
    """

    key = declared_partition_key()
    coordinates = tuple(range(1, key.dimension + 1))
    vectors = {
        "zzz-tied-document": _stub_artifact(
            "zzz-tied-document", coordinates, ARTIFACT_KIND_DOCUMENT
        ),
        "aaa-tied-document": _stub_artifact(
            "aaa-tied-document", coordinates, ARTIFACT_KIND_DOCUMENT
        ),
        "tie-probe-query": _stub_artifact(
            "tie-probe-query", coordinates, ARTIFACT_KIND_QUERY
        ),
    }
    partition = Partition(
        key=key,
        manifest_hash=sha256_bytes(b"adaivy.phase4c-semantic.tie-probe"),
        corpus_provenance="project_authored",
        vectors=vectors,
    )
    return LoadedPartition(partition=partition, manifest_hash=partition.manifest_hash)


class _StubSemanticSignal:
    """A `SemanticSignal` test double. Credits nothing; states an identity.

    It exists so `signal_configuration.overrides` and the partition-identity
    hash inputs can be exercised without a partition on disk. It carries its own
    `signal_id`, so it can never masquerade as the production signal inside a
    content hash.
    """

    signal_id = "stub-semantic-signal"

    def __init__(self, manifest_hash: str) -> None:
        self._manifest_hash = manifest_hash

    def partition_identity(self) -> SemanticPartitionIdentity:
        return SemanticPartitionIdentity(
            partition_key_string=declared_partition_key().key_string(),
            manifest_hash=self._manifest_hash,
            corpus_provenance="project_authored",
            vector_count=0,
            corpus_document_count=0,
            query_count=0,
        )

    def credits(self, query_id: str, *, limit: int) -> tuple[SemanticCredit, ...]:
        return ()


def _synthetic_credits(count: int) -> tuple[SemanticCredit, ...]:
    """`count` credits at consecutive ranks, each with the credit its rank earns."""

    return tuple(
        SemanticCredit(
            document_id=f"probe-candidate-{rank:04d}",
            rank=rank,
            tier_credit=semantic_tier_credit(rank),
            cosine_dot=1,
            cosine_norm_squared_product=1,
        )
        for rank in range(1, count + 1)
    )


# --------------------------------------------------------------------------
# Lexical margins, measured rather than quoted.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _GoldPair:
    query_id: str
    gold_id: str
    runner_up_id: str
    margin: float


def minimum_lexical_gold_margin(fixtures: Path) -> _GoldPair:
    """The smallest BM25-only margin between a rank-one gold and its runner-up.

    Measured from the frozen corpus on every run rather than quoted from
    ADR-0031, so the probe cannot keep asserting a margin the fixtures no longer
    have.
    """

    documents = load_corpus(fixtures)
    queries, _thresholds = load_gold(fixtures, documents)
    connection = open_index(sorted(corpus_rows(documents)))
    pairs: list[_GoldPair] = []
    try:
        index = LexicalIndex(connection)
        for query in queries:
            candidates = index.candidates(
                query.query, limit=BOUNDS.max_candidates_per_signal
            )
            hits = fuse(candidates, (), (), alias_phrase_points=ALIAS_PHRASE_POINTS)
            if len(hits) < 2:
                continue
            gold = set(query.relevant_ids)
            if hits[0].document_id not in gold or hits[1].document_id in gold:
                continue
            pairs.append(
                _GoldPair(
                    query_id=query.identifier,
                    gold_id=hits[0].document_id,
                    runner_up_id=hits[1].document_id,
                    margin=hits[0].fused_score - hits[1].fused_score,
                )
            )
    finally:
        connection.close()
    if not pairs:
        raise Phase4CValidationError(
            "no rank-one lexical gold has a non-gold runner-up, so the "
            "inversion property has no subject to be tested on"
        )
    pairs.sort(key=lambda item: (item.margin, item.query_id))
    return pairs[0]


def _maximum_credit_on(document_id: str) -> tuple[SemanticCredit, ...]:
    return (
        SemanticCredit(
            document_id=document_id,
            rank=1,
            tier_credit=MAXIMUM_SEMANTIC_TIER_CREDIT,
            cosine_dot=1,
            cosine_norm_squared_product=1,
        ),
    )


def _inversion_observation(
    gold_id: str, runner_up_id: str, gold_bm25: float, runner_up_bm25: float
) -> str:
    hits = fuse(
        [
            LexicalCandidate(document_id=gold_id, bm25=gold_bm25),
            LexicalCandidate(document_id=runner_up_id, bm25=runner_up_bm25),
        ],
        (),
        (),
        credits=_maximum_credit_on(runner_up_id),
        alias_phrase_points=ALIAS_PHRASE_POINTS,
        semantic_tier_points=BOUNDS.semantic_tier_points,
    )
    return (
        "gold_still_first" if hits[0].document_id == gold_id else "runner_up_promoted"
    )


# --------------------------------------------------------------------------
# Probe legs
# --------------------------------------------------------------------------


def _partition_baseline(fixtures: Path) -> str:
    load_semantic_partition(default_partition_root(fixtures))
    return _ACCEPTED


def _partition_mismatch(fixtures: Path) -> str:
    load_semantic_partition(
        default_partition_root(fixtures),
        declared_key=PartitionKey(
            provider=declared_partition_key().provider,
            model_identifier=_OTHER_MODEL_IDENTIFIER,
            dimension=declared_partition_key().dimension,
            normalization=declared_partition_key().normalization,
        ),
    )
    return _ACCEPTED


def _full_run_baseline(fixtures: Path) -> str:
    evaluate_hybrid(fixtures)
    return _ACCEPTED


def _absent_partition(fixtures: Path) -> str:
    evaluate_hybrid(
        fixtures,
        semantic_partition=default_partition_root(fixtures).parent.joinpath(
            _ABSENT_PARTITION_DIRNAME
        ),
    )
    # Reaching this line at all is the forbidden outcome: a four-signal
    # benchmark produced a report with no partition to read, which is a number
    # for a system that was not tested. It is named rather than left as a bare
    # `accepted`.
    return "degraded_to_three_signal"


def _bound_respected(fixtures: Path) -> str:
    fuse(
        [LexicalCandidate(document_id="probe-candidate-0001", bm25=-1.0)],
        (),
        (),
        credits=_synthetic_credits(BOUNDS.semantic_candidate_limit),
        alias_phrase_points=ALIAS_PHRASE_POINTS,
    )
    return _ACCEPTED


def _bound_exceeded(fixtures: Path) -> str:
    fuse(
        [LexicalCandidate(document_id="probe-candidate-0001", bm25=-1.0)],
        (),
        (),
        credits=_synthetic_credits(BOUNDS.max_candidates_per_signal + 1),
        alias_phrase_points=ALIAS_PHRASE_POINTS,
    )
    return _ACCEPTED


def _semantic_module_source() -> str:
    return (
        Path(__file__)
        .resolve()
        .parent.joinpath("semantic.py")
        .read_text(encoding="utf-8")
    )


def _exactness_clean(fixtures: Path) -> str:
    findings = sweep_source(_semantic_module_source(), module="semantic.py")
    return "clean" if not findings else "inexact"


def _exactness_instrument_fires(fixtures: Path) -> str:
    findings = sweep_source(_INEXACT_SUBJECT, module="deliberately-inexact-subject")
    return "clean" if not findings else "inexact"


def _tie_order(fixtures: Path) -> str:
    signal = SemanticPartitionSignal(_tie_partition())
    ordered = tuple(item for item, _terms in signal.ranked("tie-probe-query"))
    return (
        "document_id_ascending"
        if ordered == tuple(sorted(ordered))
        else "not_document_id_ascending"
    )


def _tie_order_instrument_fires(fixtures: Path) -> str:
    # Same assertion, deliberately wrong subject: a descending pair.
    ordered = ("zzz-tied-document", "aaa-tied-document")
    return (
        "document_id_ascending"
        if ordered == tuple(sorted(ordered))
        else "not_document_id_ascending"
    )


def _hash_with_manifest(fixtures: Path, manifest_hash: str) -> str:
    report = evaluate_hybrid(
        fixtures, semantic_signal=_StubSemanticSignal(manifest_hash)
    )
    return report["content_hash"]


def _partition_hash_same(fixtures: Path) -> str:
    seal = sha256_bytes(b"adaivy.phase4c-semantic.probe-manifest-one")
    first = _hash_with_manifest(fixtures, seal)
    second = _hash_with_manifest(fixtures, seal)
    return "content_hash_equal" if first == second else "content_hash_changed"


def _partition_hash_changed(fixtures: Path) -> str:
    first = _hash_with_manifest(
        fixtures, sha256_bytes(b"adaivy.phase4c-semantic.probe-manifest-one")
    )
    second = _hash_with_manifest(
        fixtures, sha256_bytes(b"adaivy.phase4c-semantic.probe-manifest-two")
    )
    return "content_hash_equal" if first == second else "content_hash_changed"


def _override_absent(fixtures: Path) -> str:
    report = evaluate_hybrid(fixtures)
    return (
        "recorded"
        if "semantic_signal" in report["signal_configuration"]["overrides"]
        else "not_recorded"
    )


def _override_recorded(fixtures: Path) -> str:
    production = evaluate_hybrid(fixtures)
    stubbed = evaluate_hybrid(
        fixtures,
        semantic_signal=_StubSemanticSignal(
            sha256_bytes(b"adaivy.phase4c-semantic.probe-override")
        ),
    )
    configuration = stubbed["signal_configuration"]
    if "semantic_signal" not in configuration["overrides"]:
        return "not_recorded"
    if configuration["semantic_signal_id"] == production["signal_configuration"][
        "semantic_signal_id"
    ]:
        return "masqueraded_as_production"
    if stubbed["content_hash"] == production["content_hash"]:
        return "hash_unchanged"
    return "recorded"


def _zero_spend_gate(fixtures: Path) -> str:
    report = evaluate_hybrid(fixtures)
    spend = report["metrics"]["external_spend_usd"]
    if spend != 0:
        return "nonzero_spend"
    threshold = report["proposed_thresholds"]["external_spend_usd"]
    return (
        "zero_spend"
        if gate_status("external_spend_usd", threshold, spend) == "pass"
        else "nonzero_spend"
    )


def _zero_spend_gate_instrument_fires(fixtures: Path) -> str:
    # The gate must be capable of failing, or reporting zero spend proves
    # nothing. One cent is fed to the same comparison.
    return (
        "zero_spend"
        if gate_status("external_spend_usd", 0, 1) == "pass"
        else "nonzero_spend"
    )


def _three_signal_scores(fixtures: Path) -> dict[str, float]:
    """The ADR-0032 fused score for every hit, from the THREE-argument `fuse`.

    Recomputed from the signals rather than read back off a four-signal report,
    so `pr.semantic-disabled-is-a-true-noop` compares the disabled run against
    an independently produced pre-ADR-0070 value and not against itself.
    """

    documents = load_corpus(fixtures)
    queries, _thresholds = load_gold(fixtures, documents)
    table = load_aliases(fixtures)
    connection = open_index(sorted(corpus_rows(documents)))
    scores: dict[str, float] = {}
    try:
        index = LexicalIndex(connection)
        disclaimer = SelfDisclaimerSignal(documents)
        expander = AliasExpansionSignal(documents, table)
        for query in queries:
            candidates = index.candidates(
                query.query, limit=BOUNDS.max_candidates_per_signal
            )
            expansions = expander.expand(
                query.query, limit=BOUNDS.max_candidates_per_signal
            )
            pre_ids = [candidate.document_id for candidate in candidates]
            for expansion in expansions:
                for document_id, _phrases in expansion.matched:
                    if document_id not in pre_ids:
                        pre_ids.append(document_id)
            verdicts = disclaimer.verdicts(query.query, pre_ids)
            hits = fuse(
                candidates, expansions, verdicts,
                alias_phrase_points=ALIAS_PHRASE_POINTS,
            )
            for hit in hits:
                scores[f"{query.identifier}::{hit.document_id}"] = round(
                    hit.fused_score, 6
                )
    finally:
        connection.close()
    return scores


def _observed_scores(report: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for entry in report["operational"]["results"]:
        for hit in entry["hits"]:
            scores[f"{entry['id']}::{hit['document_id']}"] = hit["fused_score"]
    return scores


def _disabled_is_a_noop(fixtures: Path) -> str:
    report = evaluate_hybrid(fixtures, semantic_signal=DisabledSemanticSignal())
    for entry in report["results"]:
        for hit in entry["hits"]:
            if hit["semantic_tier_credit"] != 0 or hit["semantic_rank"] is not None:
                return "scores_differ"
    return (
        "exact_match"
        if _observed_scores(report) == _three_signal_scores(fixtures)
        else "scores_differ"
    )


def _enabled_is_not_a_noop(fixtures: Path) -> str:
    # Same comparison, deliberately wrong subject: the ENABLED signal. If this
    # said `exact_match` the fourth term would be changing nothing and the whole
    # slice would be dead weight.
    report = evaluate_hybrid(fixtures)
    return (
        "exact_match"
        if _observed_scores(report) == _three_signal_scores(fixtures)
        else "scores_differ"
    )


@dataclass(frozen=True)
class Probe:
    probe_id: str
    mutation_target: str
    detail: str
    expected_baseline: str
    expected_mutated: str
    baseline: Callable[[Path], str]
    mutated: Callable[[Path], str]


PROBES: tuple[Probe, ...] = (
    Probe(
        probe_id="pr.semantic-partition-mismatch-refused",
        mutation_target="input",
        detail=(
            "a manifest whose partition key differs from the declared one is "
            "refused; a query vector is only ever compared inside its own "
            "geometry and there is no fallback partition"
        ),
        expected_baseline=_ACCEPTED,
        expected_mutated=_REFUSED,
        baseline=_partition_baseline,
        mutated=_partition_mismatch,
    ),
    Probe(
        probe_id="pr.semantic-missing-partition-refused",
        mutation_target="input",
        detail=(
            "an absent partition refuses instead of silently running three "
            "signals; a benchmark that drops a signal reports a number for a "
            "system that was not tested"
        ),
        expected_baseline=_ACCEPTED,
        expected_mutated=_REFUSED,
        baseline=_full_run_baseline,
        mutated=_absent_partition,
    ),
    Probe(
        probe_id="pr.semantic-respects-candidate-bound",
        mutation_target="input",
        detail=(
            "the signal may introduce a document, so returning more than "
            "max_candidates_per_signal credits is refused at the fusion "
            "boundary rather than trusted to the signal"
        ),
        expected_baseline=_ACCEPTED,
        expected_mutated=_REFUSED,
        baseline=_bound_respected,
        mutated=_bound_exceeded,
    ),
    Probe(
        probe_id="pr.semantic-cannot-invert-a-lexical-gold",
        mutation_target="property",
        detail=(
            "maximum semantic credit on the runner-up of the MEASURED minimum "
            "BM25 gold margin does not reorder the pair; the mutated leg fires "
            "the same instrument at a pair whose margin is below the credit, so "
            "the instrument is shown able to see an inversion. This bounds "
            "inversion for BM25-CARRIED golds only: a gold held at rank one by "
            "alias points can sit on a margin below three, and does"
        ),
        expected_baseline="gold_still_first",
        expected_mutated="runner_up_promoted",
        baseline=lambda fixtures: _inversion_observation(
            *_measured_pair_arguments(fixtures)
        ),
        mutated=lambda fixtures: _inversion_observation(
            "probe-gold", "probe-runner-up", -2.0, -1.0
        ),
    ),
    Probe(
        probe_id="pr.semantic-no-float-constructed",
        mutation_target="property",
        detail=(
            "an AST sweep of semantic.py finds no float literal, no float or "
            "complex name, and no true or floor division; the mutated leg fires "
            "the same sweep at a deliberately inexact subject"
        ),
        expected_baseline="clean",
        expected_mutated="inexact",
        baseline=_exactness_clean,
        mutated=_exactness_instrument_fires,
    ),
    Probe(
        probe_id="pr.semantic-tie-broken-by-document-id",
        mutation_target="property",
        detail=(
            "two documents with identical coordinates -- an exact cosine tie -- "
            "come out document_id ascending, with the descending-id document "
            "present so a set, dictionary, or insertion order would be visible"
        ),
        expected_baseline="document_id_ascending",
        expected_mutated="not_document_id_ascending",
        baseline=_tie_order,
        mutated=_tie_order_instrument_fires,
    ),
    Probe(
        probe_id="pr.semantic-partition-in-content-hash",
        mutation_target="property",
        detail=(
            "changing only the partition manifest hash changes the report "
            "content_hash; the baseline leg holds the manifest hash fixed and "
            "everything else identical, so the two legs differ in exactly one "
            "field"
        ),
        expected_baseline="content_hash_equal",
        expected_mutated="content_hash_changed",
        baseline=_partition_hash_same,
        mutated=_partition_hash_changed,
    ),
    Probe(
        probe_id="pr.semantic-override-recorded",
        mutation_target="property",
        detail=(
            "an injected signal appears in signal_configuration.overrides, "
            "carries its own signal_id, and changes the content hash, so a test "
            "double cannot masquerade as the production signal inside a hash"
        ),
        expected_baseline="not_recorded",
        expected_mutated="recorded",
        baseline=_override_absent,
        mutated=_override_recorded,
    ),
    Probe(
        probe_id="pr.semantic-zero-spend-preserved",
        mutation_target="property",
        detail=(
            "external_spend_usd is exactly 0 with the signal enabled, and the "
            "gate that says so is shown able to fail on one cent"
        ),
        expected_baseline="zero_spend",
        expected_mutated="nonzero_spend",
        baseline=_zero_spend_gate,
        mutated=_zero_spend_gate_instrument_fires,
    ),
    Probe(
        probe_id="pr.semantic-disabled-is-a-true-noop",
        mutation_target="property",
        detail=(
            "with the signal disabled every fused score equals "
            "(-bm25) + alias_points recomputed independently, and no hit "
            "carries a rank or a credit; the mutated leg runs the same "
            "comparison against the ENABLED signal, which must differ or the "
            "fourth term would be changing nothing"
        ),
        expected_baseline="exact_match",
        expected_mutated="scores_differ",
        baseline=_disabled_is_a_noop,
        mutated=_enabled_is_not_a_noop,
    ),
)


def _measured_pair_arguments(fixtures: Path) -> tuple[str, str, float, float]:
    """The measured minimum-margin pair, re-expressed as two BM25 values.

    The margin is preserved exactly: `relevance = -bm25`, so handing fusion
    `(-margin, 0.0)` reproduces the measured gap with the runner-up at zero.
    """

    pair = minimum_lexical_gold_margin(fixtures)
    return (pair.gold_id, pair.runner_up_id, -pair.margin, 0.0)


def _run_leg(leg: Callable[[Path], str], fixtures: Path) -> str:
    try:
        return leg(fixtures)
    except Phase4CValidationError:
        return _REFUSED


def run_probes(fixtures: Path) -> dict[str, Any]:
    """Run every probe against the frozen fixtures. Deterministic order."""

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for probe in PROBES:
        if probe.probe_id in seen:
            raise Phase4CValidationError(f"duplicate probe id {probe.probe_id}")
        seen.add(probe.probe_id)
        baseline_observed = _run_leg(probe.baseline, fixtures)
        mutated_observed = _run_leg(probe.mutated, fixtures)
        results.append(
            {
                "probe_id": probe.probe_id,
                "mutation_target": probe.mutation_target,
                "detail": probe.detail,
                "expected_baseline": probe.expected_baseline,
                "expected_mutated": probe.expected_mutated,
                "baseline_observed": baseline_observed,
                "mutated_observed": mutated_observed,
                "flipped": (
                    baseline_observed == probe.expected_baseline
                    and mutated_observed == probe.expected_mutated
                    and baseline_observed != mutated_observed
                ),
            }
        )
    results.sort(key=lambda item: item["probe_id"])
    pair = minimum_lexical_gold_margin(fixtures)
    return {
        "schema_version": PROBE_REPORT_SCHEMA_VERSION,
        "probes_total": len(results),
        "probes_flipped": sum(1 for item in results if item["flipped"]),
        "unflipped_probe_ids": sorted(
            item["probe_id"] for item in results if not item["flipped"]
        ),
        "probes": results,
        "maximum_semantic_contribution": (
            BOUNDS.semantic_tier_points * MAXIMUM_SEMANTIC_TIER_CREDIT
        ),
        "measured_minimum_lexical_gold_margin": {
            "query_id": pair.query_id,
            "gold_id": pair.gold_id,
            "runner_up_id": pair.runner_up_id,
            "margin": round(pair.margin, 6),
        },
        "external_spend_usd": 0,
        "network_calls": 0,
        "model_or_api_calls": 0,
        "creates_epistemic_warrant": False,
        "asserts_source_applicability": False,
        "novelty_status": "not_assessed",
        "significance_status": "not_assessed",
    }


__all__ = [
    "PROBES",
    "PROBE_REPORT_SCHEMA_VERSION",
    "Probe",
    "minimum_lexical_gold_margin",
    "run_probes",
]
