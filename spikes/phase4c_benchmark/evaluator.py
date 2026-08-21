"""Offline lexical baseline for the proposed Phase 4C benchmark.

This is deliberately not a production retriever. It mirrors the Phase 3A
FTS5/BM25 query shape closely enough to freeze a comparison fixture before any
hybrid signal or index exists.

Hardening invariants (see docs/phase-4c/HYBRID_RETRIEVAL_BENCHMARK_V1.md,
"Forbidden outcomes"):

* Only document source bytes reach the searchable columns. Document IDs,
  source classes, applicability labels, and duplicate groups live in UNINDEXED
  columns or in Python-side metadata and can never match a query term.
* Every fixture value is validated against a closed vocabulary and an exact key
  set. Unknown keys, duplicate JSON keys, wrong types, unknown categories, and
  out-of-bound resources are rejects, never coercions.
* "No data" is not "measured zero". A ratio with a zero denominator is reported
  as ``None`` with its numerator/denominator, and its gate is ``undetermined``,
  never ``pass``.
* Declared provenance is built from the same constants that build the executed
  SQL, and the executed SQL text itself is reported.
* Timestamps and elapsed milliseconds are operational, not semantic.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata
from typing import Any


SCHEMA_VERSION = "adaivy.phase4c-lexical-baseline.v1"
CORPUS_SCHEMA_VERSION = "adaivy.phase4c-corpus.v1"
GOLD_SCHEMA_VERSION = "adaivy.phase4c-gold-queries.v1"
FIXTURE_LICENSE = "LicenseRef-AdaIvy-Synthetic-Fixture"

METHOD = "sqlite-fts5-bm25-lexical-baseline"
TOKENIZER = "unicode61 remove_diacritics 0"
NORMALIZATION_FORM = "NFC"
# Phase 3A title/body/type BM25 weights, in indexed-column order.
INDEXED_FIELDS = ("title", "body", "unit_type")
FIELD_WEIGHTS = (2.0, 1.0, 0.5)
UNINDEXED_FIELDS = ("document_id", "source_id", "normalized_start")
# The frozen corpus is unstructured single-paragraph plain text: it carries no
# title line and no unit-type marker of its own. The three weighted columns and
# the mandated 2.0/1.0/0.5 weights are preserved, but only `body` can honestly
# be populated from source content, so `title` and `unit_type` are empty for
# every corpus document. Populating them from the document ID or source class
# would make expected IDs and classification labels retrieval features.
FIELD_SOURCES = {
    "title": "empty-corpus-has-no-title-content",
    "body": "document-source-bytes-nfc",
    "unit_type": "empty-corpus-has-no-unit-type-content",
}

DOCUMENT_COUNT = 14
QUERY_COUNT = 10
MAX_QUERY_BYTES = 4_096
MAX_REPORT_BYTES = 262_144
MAX_DERIVED_DB_BYTES = 2_097_152
MAX_ELAPSED_MS = 10_000
DUPLICATE_CUTOFF = 5

CATEGORIES = ("necessary_lemma", "applicability", "contradiction", "notation_variant", "renamed_known_result")
CATEGORY_COUNTS = {
    "necessary_lemma": 3,
    "applicability": 2,
    "contradiction": 2,
    "notation_variant": 2,
    "renamed_known_result": 1,
}
TOP_K_BY_CATEGORY = {
    "necessary_lemma": 5,
    "applicability": 5,
    "contradiction": 5,
    "notation_variant": 5,
    "renamed_known_result": 10,
}
SOURCE_CLASSES = ("primary", "secondary", "historical", "informal")
APPLICABILITY_CLASSES = ("applicable", "incompatible_hypotheses", "insufficient_evidence")

THRESHOLD_KEYS = (
    "necessary_lemma_recall_at_5",
    "applicability_precision_at_5",
    "contradiction_recall_at_5",
    "notation_variant_recall_at_5",
    "renamed_known_result_recall_at_10",
    "duplicate_rate_at_5_maximum",
    "external_spend_usd",
)
# threshold key -> (measured metric name, comparison)
GATE_COMPARISONS = {
    "necessary_lemma_recall_at_5": ("necessary_lemma_recall_at_5", "at_least"),
    "applicability_precision_at_5": ("applicability_precision_at_5", "at_least"),
    "contradiction_recall_at_5": ("contradiction_recall_at_5", "at_least"),
    "notation_variant_recall_at_5": ("notation_variant_recall_at_5", "at_least"),
    "renamed_known_result_recall_at_10": ("renamed_known_result_recall_at_10", "at_least"),
    "duplicate_rate_at_5_maximum": ("duplicate_rate_at_5", "at_most"),
    "external_spend_usd": ("external_spend_usd", "exactly"),
}

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

CREATE_STATEMENT = (
    "CREATE VIRTUAL TABLE lexical USING fts5("
    + ", ".join(f"{name} UNINDEXED" for name in UNINDEXED_FIELDS)
    + ", "
    + ", ".join(INDEXED_FIELDS)
    + f", tokenize='{TOKENIZER}')"
)
_INSERT_STATEMENT = (
    "INSERT INTO lexical("
    + ", ".join((*UNINDEXED_FIELDS, *INDEXED_FIELDS))
    + ") VALUES ("
    + ", ".join("?" for _ in (*UNINDEXED_FIELDS, *INDEXED_FIELDS))
    + ")"
)
SEARCH_STATEMENT = (
    "SELECT document_id, bm25(lexical, "
    + ", ".join(f"{0.0:.1f}" for _ in UNINDEXED_FIELDS)
    + ", "
    + ", ".join(f"{weight:.1f}" for weight in FIELD_WEIGHTS)
    + ") AS score FROM lexical WHERE lexical MATCH ? ORDER BY score ASC, document_id ASC LIMIT ?"
)


class FixtureError(ValueError):
    """A fixture, query, or resource bound violation. Always fails closed."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def semantic_view(report: dict[str, Any]) -> dict[str, Any]:
    """The exact sub-object covered by ``semantic_hash``."""

    excluded = {"semantic_hash", "operational", "operational_hash"}
    return {key: value for key, value in report.items() if key not in excluded}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise FixtureError(f"duplicate JSON key: {key!r}")
        seen[key] = value
    return seen


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise FixtureError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise FixtureError(f"{path} must contain an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise FixtureError(f"{where}: unknown keys {unknown}")
    if missing:
        raise FixtureError(f"{where}: missing keys {missing}")


def _require_text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise FixtureError(f"{where}: expected a non-empty string, got {type(value).__name__}")
    return value


def _require_member(value: Any, allowed: tuple[str, ...], where: str) -> str:
    text = _require_text(value, where)
    if text not in allowed:
        raise FixtureError(f"{where}: {text!r} is not one of {list(allowed)}")
    return text


def _require_bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise FixtureError(f"{where}: expected a boolean, got {type(value).__name__}")
    return value


def _require_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FixtureError(f"{where}: expected an integer, got {type(value).__name__}")
    return value


def _require_number(value: Any, where: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FixtureError(f"{where}: expected a number, got {type(value).__name__}")
    return value


def _require_id_list(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise FixtureError(f"{where}: expected a non-empty list")
    identifiers = tuple(_require_text(item, f"{where}[{index}]") for index, item in enumerate(value))
    if len(set(identifiers)) != len(identifiers):
        raise FixtureError(f"{where}: duplicate identifiers")
    return identifiers


@dataclass(frozen=True)
class Document:
    identifier: str
    path: str
    source_class: str
    applicability: str
    contradiction: bool
    duplicate_group: str | None
    text: str
    source_hash: str


@dataclass(frozen=True)
class GoldQuery:
    identifier: str
    category: str
    query: str
    top_k: int
    relevant_ids: tuple[str, ...]
    applicable_ids: tuple[str, ...] | None


def _load_corpus(fixtures: Path, manifest: dict[str, Any]) -> list[Document]:
    _exact_keys(manifest, {"schema_version", "fixture_license", "documents"}, "corpus manifest")
    if manifest["schema_version"] != CORPUS_SCHEMA_VERSION:
        raise FixtureError("unsupported corpus manifest schema version")
    if manifest["fixture_license"] != FIXTURE_LICENSE:
        raise FixtureError("unsupported fixture license")
    entries = manifest["documents"]
    if not isinstance(entries, list):
        raise FixtureError("corpus manifest documents must be a list")
    if len(entries) != DOCUMENT_COUNT:
        raise FixtureError(f"fixture cardinality mismatch: {len(entries)} documents, expected {DOCUMENT_COUNT}")

    root = fixtures.resolve()
    documents: list[Document] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"documents[{index}]"
        if not isinstance(entry, dict):
            raise FixtureError(f"{where}: document entry must be an object")
        _exact_keys(
            entry,
            {"id", "path", "source_class", "applicability", "contradiction", "duplicate_group"},
            where,
        )
        identifier = _require_text(entry["id"], f"{where}.id")
        relative = _require_text(entry["path"], f"{where}.path")
        if identifier in seen_ids:
            raise FixtureError("duplicate document id")
        if relative in seen_paths:
            raise FixtureError("duplicate document path")
        if Path(relative).is_absolute() or ".." in Path(relative).parts or "\\" in relative:
            raise FixtureError(f"{where}.path: must be a relative path inside the fixture directory")
        path = (root / relative).resolve()
        if root not in path.parents:
            raise FixtureError("fixture path escape")
        group = entry["duplicate_group"]
        if group is not None:
            group = _require_text(group, f"{where}.duplicate_group")
        raw = path.read_bytes()
        documents.append(
            Document(
                identifier=identifier,
                path=relative,
                source_class=_require_member(entry["source_class"], SOURCE_CLASSES, f"{where}.source_class"),
                applicability=_require_member(
                    entry["applicability"], APPLICABILITY_CLASSES, f"{where}.applicability"
                ),
                contradiction=_require_bool(entry["contradiction"], f"{where}.contradiction"),
                duplicate_group=group,
                text=unicodedata.normalize(NORMALIZATION_FORM, raw.decode("utf-8")),
                source_hash=sha256_bytes(raw),
            )
        )
        seen_ids.add(identifier)
        seen_paths.add(relative)
    return documents


def _load_gold(gold: dict[str, Any], documents: list[Document]) -> tuple[list[GoldQuery], dict[str, Any]]:
    _exact_keys(gold, {"schema_version", "queries", "proposed_thresholds"}, "gold query manifest")
    if gold["schema_version"] != GOLD_SCHEMA_VERSION:
        raise FixtureError("unsupported gold query manifest schema version")
    thresholds = gold["proposed_thresholds"]
    if not isinstance(thresholds, dict):
        raise FixtureError("proposed_thresholds must be an object")
    _exact_keys(thresholds, set(THRESHOLD_KEYS), "proposed_thresholds")
    for key, value in thresholds.items():
        _require_number(value, f"proposed_thresholds.{key}")
    entries = gold["queries"]
    if not isinstance(entries, list):
        raise FixtureError("gold queries must be a list")
    if len(entries) != QUERY_COUNT:
        raise FixtureError(f"fixture cardinality mismatch: {len(entries)} queries, expected {QUERY_COUNT}")

    corpus_ids = {document.identifier for document in documents}
    applicable_corpus_ids = {
        document.identifier for document in documents if document.applicability == "applicable"
    }
    queries: list[GoldQuery] = []
    seen_ids: set[str] = set()
    counts = {category: 0 for category in CATEGORIES}
    for index, entry in enumerate(entries):
        where = f"queries[{index}]"
        if not isinstance(entry, dict):
            raise FixtureError(f"{where}: query entry must be an object")
        category = _require_member(entry.get("category"), CATEGORIES, f"{where}.category")
        expected_keys = {"id", "category", "query", "relevant_ids", "top_k"}
        if category == "applicability":
            expected_keys.add("applicable_ids")
        _exact_keys(entry, expected_keys, f"{where} (category {category})")
        identifier = _require_text(entry["id"], f"{where}.id")
        if identifier in seen_ids:
            raise FixtureError("duplicate query id")
        text = _require_text(entry["query"], f"{where}.query")
        raw_length = len(text.encode("utf-8"))
        if raw_length > MAX_QUERY_BYTES:
            raise FixtureError(
                f"{where}.query: {raw_length} raw UTF-8 bytes exceeds the {MAX_QUERY_BYTES}-byte bound"
            )
        top_k = _require_int(entry["top_k"], f"{where}.top_k")
        if top_k != TOP_K_BY_CATEGORY[category]:
            raise FixtureError(
                f"{where}.top_k: category {category} requires top_k {TOP_K_BY_CATEGORY[category]}, got {top_k}"
            )
        relevant_ids = _require_id_list(entry["relevant_ids"], f"{where}.relevant_ids")
        unknown = sorted(set(relevant_ids) - corpus_ids)
        if unknown:
            raise FixtureError(f"{where}.relevant_ids: not in the corpus {unknown}")
        applicable_ids: tuple[str, ...] | None = None
        if category == "applicability":
            applicable_ids = _require_id_list(entry["applicable_ids"], f"{where}.applicable_ids")
            if not set(applicable_ids) <= set(relevant_ids):
                raise FixtureError(f"{where}.applicable_ids: must be a subset of relevant_ids")
            expected_applicable = set(relevant_ids) & applicable_corpus_ids
            if set(applicable_ids) != expected_applicable:
                raise FixtureError(
                    f"{where}.applicable_ids: disagrees with corpus applicability labels "
                    f"{sorted(expected_applicable)}"
                )
        queries.append(
            GoldQuery(
                identifier=identifier,
                category=category,
                query=text,
                top_k=top_k,
                relevant_ids=relevant_ids,
                applicable_ids=applicable_ids,
            )
        )
        seen_ids.add(identifier)
        counts[category] += 1
    if counts != CATEGORY_COUNTS:
        raise FixtureError(f"gold query category distribution mismatch: {counts}")
    return queries, thresholds


def fts_expression(query: str) -> str:
    """The OR-combined quoted token expression actually sent to FTS5."""

    normalized = unicodedata.normalize(NORMALIZATION_FORM, " ".join(query.split()))
    if not normalized:
        raise FixtureError("query is empty")
    tokens = [token.casefold() for token in _TOKEN.findall(normalized)]
    if not tokens:
        raise FixtureError("query has no lexical tokens")
    return " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)


def open_index(rows: list[tuple[str, str, str, str]]) -> sqlite3.Connection:
    """Build the in-memory index. ``rows`` are ``(document_id, title, body, unit_type)``.

    Only the last three values are searchable; ``document_id`` is UNINDEXED and
    exists for result identity and the deterministic tie-break.
    """

    connection = sqlite3.connect(":memory:")
    connection.execute(CREATE_STATEMENT)
    connection.executemany(
        _INSERT_STATEMENT,
        [
            (identifier, identifier, "0", title, body, unit_type)
            for identifier, title, body, unit_type in rows
        ],
    )
    return connection


def search(connection: sqlite3.Connection, query: str, top_k: int) -> list[str]:
    rows = connection.execute(SEARCH_STATEMENT, (fts_expression(query), top_k)).fetchall()
    return [str(row[0]) for row in rows]


def _corpus_rows(documents: list[Document]) -> list[tuple[str, str, str, str]]:
    # Searchable content is document source bytes only. The document ID, source
    # class, applicability label, and duplicate group are never indexed.
    return [(document.identifier, "", document.text, "") for document in documents]


def probe(fixtures: Path, query: str, *, top_k: int = DOCUMENT_COUNT) -> list[str]:
    """Diagnostic retrieval against the frozen corpus index.

    Used by the label-separation tests: any token that exists only in an ID or
    a classification label must retrieve nothing.
    """

    documents = _load_corpus(fixtures, _load_object(fixtures / "corpus-manifest.json"))
    connection = open_index(_corpus_rows(documents))
    try:
        return search(connection, query, top_k)
    finally:
        connection.close()


def _derived_db_bytes(connection: sqlite3.Connection) -> int:
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    return page_count * page_size


@dataclass(frozen=True)
class Measurement:
    """A ratio plus the counts that produced it.

    ``value`` is ``None`` when the denominator is zero: no data measured, which
    is not the same claim as a measured zero and can never pass a gate.
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


def _micro_recall(results: list[dict[str, Any]], category: str) -> Measurement:
    found = total = 0
    for item in results:
        if item["category"] != category:
            continue
        gold = set(item["relevant_ids"])
        found += len(gold & set(item["ordered_ids"]))
        total += len(gold)
    return Measurement(found, total)


def _gate_status(threshold_key: str, threshold: Any, measured: Any) -> str:
    if measured is None:
        return "undetermined"
    comparison = GATE_COMPARISONS[threshold_key][1]
    if comparison == "at_least":
        return "pass" if measured >= threshold else "fail"
    if comparison == "at_most":
        return "pass" if measured <= threshold else "fail"
    return "pass" if measured == threshold else "fail"


def evaluate_baseline(fixtures: Path, *, reverse_insertion: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    manifest_path = fixtures / "corpus-manifest.json"
    queries_path = fixtures / "gold-queries.json"
    documents = _load_corpus(fixtures, _load_object(manifest_path))
    queries, thresholds = _load_gold(_load_object(queries_path), documents)

    metadata = {document.identifier: document for document in documents}
    source_hashes = {document.identifier: document.source_hash for document in documents}
    rows = sorted(_corpus_rows(documents), reverse=reverse_insertion)

    connection = open_index(rows)
    try:
        results: list[dict[str, Any]] = []
        zero_hit_query_ids: list[str] = []
        duplicate_hits = total_hits = 0
        for query in queries:
            ordered_ids = search(connection, query.query, query.top_k)
            if not ordered_ids:
                zero_hit_query_ids.append(query.identifier)
            seen_groups: set[str] = set()
            duplicate_ids: list[str] = []
            # Duplicate-rate@5 uses the same cutoff for every query, including
            # the renamed-known-result control whose recall cutoff is ten.
            for identifier in ordered_ids[:DUPLICATE_CUTOFF]:
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
                "top_k": query.top_k,
                "relevant_ids": list(query.relevant_ids),
                "ordered_ids": ordered_ids,
                "missed_relevant_ids": sorted(set(query.relevant_ids) - set(ordered_ids)),
                "duplicate_ids_at_5": duplicate_ids,
                "inapplicable_retrieved_ids": sorted(
                    identifier
                    for identifier in ordered_ids
                    if metadata[identifier].applicability != "applicable"
                ),
                "zero_hit": not ordered_ids,
            }
            if query.applicable_ids is not None:
                entry["applicable_ids"] = list(query.applicable_ids)
            results.append(entry)

        relevant_applicable = relevant_retrieved = 0
        for query, result in zip(queries, results, strict=True):
            if query.category != "applicability":
                continue
            assert query.applicable_ids is not None  # guaranteed by _load_gold
            retrieved = set(query.relevant_ids) & set(result["ordered_ids"])
            relevant_retrieved += len(retrieved)
            relevant_applicable += len(retrieved & set(query.applicable_ids))

        measurements = {
            "necessary_lemma_recall_at_5": _micro_recall(results, "necessary_lemma"),
            "applicability_precision_at_5": Measurement(relevant_applicable, relevant_retrieved),
            "contradiction_recall_at_5": _micro_recall(results, "contradiction"),
            "notation_variant_recall_at_5": _micro_recall(results, "notation_variant"),
            "renamed_known_result_recall_at_10": _micro_recall(results, "renamed_known_result"),
            "duplicate_rate_at_5": Measurement(duplicate_hits, total_hits),
        }
        metrics: dict[str, Any] = {name: item.value for name, item in measurements.items()}
        metrics.update({"external_spend_usd": 0, "network_calls": 0, "model_or_api_calls": 0})
        metric_support = {name: item.as_support() for name, item in measurements.items()}

        gate_evaluation = {
            key: {
                "metric": GATE_COMPARISONS[key][0],
                "comparison": GATE_COMPARISONS[key][1],
                "threshold": thresholds[key],
                "measured": metrics[GATE_COMPARISONS[key][0]],
                "status": _gate_status(key, thresholds[key], metrics[GATE_COMPARISONS[key][0]]),
            }
            for key in THRESHOLD_KEYS
        }
        statuses = [item["status"] for item in gate_evaluation.values()]

        derived_db_bytes = _derived_db_bytes(connection)
        if derived_db_bytes > MAX_DERIVED_DB_BYTES:
            raise FixtureError(
                f"derived benchmark database bound exceeded: {derived_db_bytes} > {MAX_DERIVED_DB_BYTES}"
            )

        semantic = {
            "schema_version": SCHEMA_VERSION,
            "method": METHOD,
            "declared_method": {
                "method": METHOD,
                "tokenizer": TOKENIZER,
                "normalization_form": NORMALIZATION_FORM,
                "indexed_fields": list(INDEXED_FIELDS),
                "field_weights": list(FIELD_WEIGHTS),
                "field_sources": dict(FIELD_SOURCES),
                "unindexed_fields": list(UNINDEXED_FIELDS),
                "tie_break": "score ASC, document_id ASC",
                "create_statement": CREATE_STATEMENT,
                "search_statement": SEARCH_STATEMENT,
            },
            "tokenizer": TOKENIZER,
            "field_weights": list(FIELD_WEIGHTS),
            "resource_bounds": {
                "document_count": DOCUMENT_COUNT,
                "query_count": QUERY_COUNT,
                "max_query_bytes": MAX_QUERY_BYTES,
                "max_report_bytes": MAX_REPORT_BYTES,
                "max_derived_db_bytes": MAX_DERIVED_DB_BYTES,
                "max_elapsed_ms": MAX_ELAPSED_MS,
                "top_k_by_category": dict(sorted(TOP_K_BY_CATEGORY.items())),
                "duplicate_cutoff": DUPLICATE_CUTOFF,
            },
            "corpus_manifest_hash": sha256_bytes(manifest_path.read_bytes()),
            "gold_queries_hash": sha256_bytes(queries_path.read_bytes()),
            "source_hashes": source_hashes,
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
        if elapsed_ms > MAX_ELAPSED_MS:
            raise FixtureError(f"parent-process time bound exceeded: {elapsed_ms} ms")
        operational = {
            "derived_db_bytes": derived_db_bytes,
            "elapsed_ms": elapsed_ms,
            "reverse_insertion": reverse_insertion,
            "sqlite_library_version": sqlite3.sqlite_version,
        }
        report = dict(semantic)
        report["semantic_hash"] = sha256_bytes(canonical_bytes(semantic))
        report["operational"] = operational
        report["operational_hash"] = sha256_bytes(canonical_bytes(operational))
        report_bytes = len(canonical_bytes(report))
        if report_bytes > MAX_REPORT_BYTES:
            raise FixtureError(f"report byte bound exceeded: {report_bytes} > {MAX_REPORT_BYTES}")
        return report
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(evaluate_baseline(Path("fixtures/phase4c")), indent=2, sort_keys=True))
