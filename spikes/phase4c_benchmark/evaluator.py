"""Offline lexical baseline for the proposed Phase 4C benchmark.

This is deliberately not a production retriever. It mirrors the Phase 3A
FTS5/BM25 query shape closely enough to freeze a comparison fixture before any
hybrid signal or index exists.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from typing import Any, Iterable


SCHEMA_VERSION = "adaivy.phase4c-lexical-baseline.v1"
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _fts_expression(query: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(query.split()))
    if not normalized or len(normalized.encode("utf-8")) > 4096:
        raise ValueError("query is empty or too large")
    tokens = [token.casefold() for token in _TOKEN.findall(normalized)]
    if not tokens:
        raise ValueError("query has no lexical tokens")
    return " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _micro_recall(results: Iterable[dict[str, Any]], category: str) -> float:
    found = total = 0
    for item in results:
        if item["category"] != category:
            continue
        gold = set(item["relevant_ids"])
        found += len(gold & set(item["ordered_ids"]))
        total += len(gold)
    return _ratio(found, total)


def evaluate_baseline(fixtures: Path, *, reverse_insertion: bool = False) -> dict[str, Any]:
    manifest_path = fixtures / "corpus-manifest.json"
    queries_path = fixtures / "gold-queries.json"
    manifest = _load_object(manifest_path)
    gold = _load_object(queries_path)
    documents = manifest.get("documents")
    queries = gold.get("queries")
    if manifest.get("schema_version") != "adaivy.phase4c-corpus.v1" or not isinstance(documents, list):
        raise ValueError("unsupported corpus manifest")
    if gold.get("schema_version") != "adaivy.phase4c-gold-queries.v1" or not isinstance(queries, list):
        raise ValueError("unsupported gold query manifest")
    if len(documents) != 14 or len(queries) != 10:
        raise ValueError("fixture cardinality mismatch")

    rows: list[tuple[str, str, str, str]] = []
    metadata: dict[str, dict[str, Any]] = {}
    source_hashes: dict[str, str] = {}
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("document entry must be an object")
        identifier = str(document["id"])
        path = (fixtures / str(document["path"])).resolve()
        if fixtures.resolve() not in path.parents:
            raise ValueError("fixture path escape")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if identifier in metadata:
            raise ValueError("duplicate document id")
        metadata[identifier] = document
        source_hashes[identifier] = sha256_bytes(raw)
        rows.append((identifier, identifier.replace("-", " "), text, str(document["source_class"])))
    rows.sort(reverse=reverse_insertion)

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE lexical USING fts5("
            "document_id UNINDEXED, source_id UNINDEXED, normalized_start UNINDEXED, "
            "title, body, unit_type, tokenize='unicode61 remove_diacritics 0')"
        )
        connection.executemany(
            "INSERT INTO lexical(document_id, source_id, normalized_start, title, body, unit_type) "
            "VALUES (?, ?, '0', ?, ?, ?)",
            [(identifier, identifier, title, body, unit_type) for identifier, title, body, unit_type in rows],
        )
        results: list[dict[str, Any]] = []
        duplicate_hits = total_hits = 0
        for query in queries:
            if not isinstance(query, dict):
                raise ValueError("query entry must be an object")
            top_k = int(query["top_k"])
            result_rows = connection.execute(
                "SELECT document_id, bm25(lexical, 0.0, 0.0, 0.0, 2.0, 1.0, 0.5) AS score FROM lexical "
                "WHERE lexical MATCH ? ORDER BY score ASC, document_id ASC LIMIT ?",
                (_fts_expression(str(query["query"])), top_k),
            ).fetchall()
            ordered_ids = [str(row[0]) for row in result_rows]
            seen_groups: set[str] = set()
            # Duplicate-rate@5 uses the same cutoff for every query, including
            # the renamed-known-result control whose recall cutoff is ten.
            for identifier in ordered_ids[:5]:
                total_hits += 1
                group = metadata[identifier].get("duplicate_group")
                if group is not None:
                    group_string = str(group)
                    if group_string in seen_groups:
                        duplicate_hits += 1
                    seen_groups.add(group_string)
            results.append(
                {
                    "id": str(query["id"]),
                    "category": str(query["category"]),
                    "query": str(query["query"]),
                    "top_k": top_k,
                    "relevant_ids": list(query["relevant_ids"]),
                    "ordered_ids": ordered_ids,
                }
            )

        relevant_applicable = relevant_retrieved = 0
        for query, result in zip(queries, results, strict=True):
            if query["category"] != "applicability":
                continue
            relevant = set(query["relevant_ids"])
            retrieved = relevant & set(result["ordered_ids"])
            relevant_retrieved += len(retrieved)
            relevant_applicable += len(retrieved & set(query["applicable_ids"]))

        metrics = {
            "necessary_lemma_recall_at_5": _micro_recall(results, "necessary_lemma"),
            "applicability_precision_at_5": _ratio(relevant_applicable, relevant_retrieved),
            "contradiction_recall_at_5": _micro_recall(results, "contradiction"),
            "notation_variant_recall_at_5": _micro_recall(results, "notation_variant"),
            "renamed_known_result_recall_at_10": _micro_recall(results, "renamed_known_result"),
            "duplicate_rate_at_5": _ratio(duplicate_hits, total_hits),
            "external_spend_usd": 0,
            "network_calls": 0,
            "model_or_api_calls": 0,
        }
        semantic = {
            "schema_version": SCHEMA_VERSION,
            "method": "sqlite-fts5-bm25-lexical-baseline",
            "tokenizer": "unicode61 remove_diacritics 0",
            "field_weights": [2.0, 1.0, 0.5],
            "corpus_manifest_hash": sha256_bytes(manifest_path.read_bytes()),
            "gold_queries_hash": sha256_bytes(queries_path.read_bytes()),
            "source_hashes": source_hashes,
            "results": results,
            "metrics": metrics,
            "proposed_thresholds": gold["proposed_thresholds"],
        }
        report = dict(semantic)
        report["semantic_hash"] = sha256_bytes(canonical_bytes(semantic))
        if len(canonical_bytes(report)) > 262_144:
            raise ValueError("report byte bound exceeded")
        return report
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(evaluate_baseline(Path("fixtures/phase4c")), indent=2, sort_keys=True))
