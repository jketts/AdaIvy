"""Strict fail-closed loaders for the frozen Phase 4C benchmark fixtures.

Unknown keys, duplicate JSON keys, wrong types (a `bool` is not an `int`),
unknown category or class members, path escapes, cardinality mismatches, and
out-of-bound resources are rejects. Nothing is coerced and nothing is defaulted.

Label separation: `id`, `source_class`, `applicability`, and `duplicate_group`
are loaded into Python-side metadata only. No loader here hands them to a
searchable column, a query, or the alias matcher.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bounds import (
    ALIAS_SCHEMA_VERSION,
    APPLICABILITY_CLASSES,
    BOUNDS,
    CATEGORIES,
    CATEGORY_COUNTS,
    CORPUS_SCHEMA_VERSION,
    FIXTURE_LICENSE,
    GOLD_SCHEMA_VERSION,
    Phase4CValidationError,
    SOURCE_CLASSES,
    THRESHOLD_KEYS,
    TOP_K_BY_CATEGORY,
)
from .serialization import sha256_bytes
from .text import normalize, tokens

CORPUS_MANIFEST_NAME = "corpus-manifest.json"
GOLD_QUERIES_NAME = "gold-queries.json"
NAME_ALIASES_NAME = "name-aliases.json"

CORPUS_KEYS = {"schema_version", "fixture_license", "documents"}
DOCUMENT_KEYS = {
    "id",
    "path",
    "source_class",
    "applicability",
    "contradiction",
    "duplicate_group",
}
GOLD_KEYS = {"schema_version", "queries", "proposed_thresholds"}
QUERY_KEYS = {"id", "category", "query", "relevant_ids", "top_k"}
ALIAS_FILE_KEYS = {"schema_version", "fixture_license", "aliases"}
ALIAS_ENTRY_KEYS = {"id", "alias", "content_phrases"}


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise Phase4CValidationError(f"duplicate JSON key: {key!r}")
        seen[key] = value
    return seen


def load_object(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise Phase4CValidationError(f"{path} is not readable: {error}") from error
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Phase4CValidationError(f"{path} is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise Phase4CValidationError(f"{path} must contain an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown:
        raise Phase4CValidationError(f"{where}: unknown keys {unknown}")
    if missing:
        raise Phase4CValidationError(f"{where}: missing keys {missing}")


def _require_text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise Phase4CValidationError(
            f"{where}: expected a non-empty string, got {type(value).__name__}"
        )
    return value


def _require_member(value: Any, allowed: tuple[str, ...], where: str) -> str:
    text = _require_text(value, where)
    if text not in allowed:
        raise Phase4CValidationError(f"{where}: {text!r} is not one of {list(allowed)}")
    return text


def _require_bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise Phase4CValidationError(
            f"{where}: expected a boolean, got {type(value).__name__}"
        )
    return value


def _require_int(value: Any, where: str) -> int:
    # `bool` is a subclass of `int` and is rejected explicitly: accepting
    # `true` as `top_k` would be a coercion, and coercions are forbidden.
    if isinstance(value, bool) or not isinstance(value, int):
        raise Phase4CValidationError(
            f"{where}: expected an integer, got {type(value).__name__}"
        )
    return value


def _require_number(value: Any, where: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Phase4CValidationError(
            f"{where}: expected a number, got {type(value).__name__}"
        )
    return value


def _require_unique_text_list(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise Phase4CValidationError(f"{where}: expected a non-empty list")
    items = tuple(
        _require_text(item, f"{where}[{index}]") for index, item in enumerate(value)
    )
    if len(set(items)) != len(items):
        raise Phase4CValidationError(f"{where}: duplicate entries")
    return items


@dataclass(frozen=True)
class Document:
    """One corpus document. `text` is the only field any signal may search."""

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


@dataclass(frozen=True)
class AliasEntry:
    """One content-keyed alias entry.

    `identifier` is a reporting label only. It is never matched against a
    document, a query, or another alias. `alias` is the name phrase recognised
    in a query; `content_phrases` are the only phrases matched against document
    bodies. No document identifier may appear in any of the three fields, which
    the acceptance suite asserts against the raw fixture bytes.
    """

    identifier: str
    alias: str
    content_phrases: tuple[str, ...]

    @property
    def alias_tokens(self) -> tuple[str, ...]:
        return tokens(self.alias)

    @property
    def content_phrase_tokens(self) -> tuple[tuple[str, ...], ...]:
        return tuple(tokens(phrase) for phrase in self.content_phrases)


def load_corpus(fixtures: Path) -> tuple[Document, ...]:
    path = fixtures / CORPUS_MANIFEST_NAME
    manifest = load_object(path)
    _exact_keys(manifest, CORPUS_KEYS, "corpus manifest")
    if manifest["schema_version"] != CORPUS_SCHEMA_VERSION:
        raise Phase4CValidationError("unsupported corpus manifest schema version")
    if manifest["fixture_license"] != FIXTURE_LICENSE:
        raise Phase4CValidationError("unsupported fixture license")
    entries = manifest["documents"]
    if not isinstance(entries, list):
        raise Phase4CValidationError("corpus manifest documents must be a list")
    if len(entries) != BOUNDS.document_count:
        raise Phase4CValidationError(
            f"fixture cardinality mismatch: {len(entries)} documents, "
            f"expected {BOUNDS.document_count}"
        )

    root = fixtures.resolve()
    documents: list[Document] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"documents[{index}]"
        if not isinstance(entry, dict):
            raise Phase4CValidationError(f"{where}: document entry must be an object")
        _exact_keys(entry, DOCUMENT_KEYS, where)
        identifier = _require_text(entry["id"], f"{where}.id")
        relative = _require_text(entry["path"], f"{where}.path")
        if identifier in seen_ids:
            raise Phase4CValidationError("duplicate document id")
        if relative in seen_paths:
            raise Phase4CValidationError("duplicate document path")
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative:
            raise Phase4CValidationError(
                f"{where}.path: must be a relative path inside the fixture directory"
            )
        resolved = (root / relative).resolve()
        if root not in resolved.parents:
            raise Phase4CValidationError("fixture path escape")
        group = entry["duplicate_group"]
        if group is not None:
            group = _require_text(group, f"{where}.duplicate_group")
        try:
            raw = resolved.read_bytes()
        except OSError as error:
            raise Phase4CValidationError(f"{where}.path is not readable") from error
        documents.append(
            Document(
                identifier=identifier,
                path=relative,
                source_class=_require_member(
                    entry["source_class"], SOURCE_CLASSES, f"{where}.source_class"
                ),
                applicability=_require_member(
                    entry["applicability"], APPLICABILITY_CLASSES, f"{where}.applicability"
                ),
                contradiction=_require_bool(entry["contradiction"], f"{where}.contradiction"),
                duplicate_group=group,
                text=normalize(raw.decode("utf-8", "strict")),
                source_hash=sha256_bytes(raw),
            )
        )
        seen_ids.add(identifier)
        seen_paths.add(relative)
    return tuple(documents)


def load_gold(
    fixtures: Path, documents: tuple[Document, ...]
) -> tuple[tuple[GoldQuery, ...], dict[str, Any]]:
    path = fixtures / GOLD_QUERIES_NAME
    gold = load_object(path)
    _exact_keys(gold, GOLD_KEYS, "gold query manifest")
    if gold["schema_version"] != GOLD_SCHEMA_VERSION:
        raise Phase4CValidationError("unsupported gold query manifest schema version")
    thresholds = gold["proposed_thresholds"]
    if not isinstance(thresholds, dict):
        raise Phase4CValidationError("proposed_thresholds must be an object")
    _exact_keys(thresholds, set(THRESHOLD_KEYS), "proposed_thresholds")
    for key, value in thresholds.items():
        _require_number(value, f"proposed_thresholds.{key}")
    entries = gold["queries"]
    if not isinstance(entries, list):
        raise Phase4CValidationError("gold queries must be a list")
    if len(entries) != BOUNDS.query_count:
        raise Phase4CValidationError(
            f"fixture cardinality mismatch: {len(entries)} queries, "
            f"expected {BOUNDS.query_count}"
        )

    corpus_ids = {document.identifier for document in documents}
    applicable_corpus_ids = {
        document.identifier
        for document in documents
        if document.applicability == "applicable"
    }
    queries: list[GoldQuery] = []
    seen_ids: set[str] = set()
    counts = {category: 0 for category in CATEGORIES}
    for index, entry in enumerate(entries):
        where = f"queries[{index}]"
        if not isinstance(entry, dict):
            raise Phase4CValidationError(f"{where}: query entry must be an object")
        category = _require_member(entry.get("category"), CATEGORIES, f"{where}.category")
        expected = set(QUERY_KEYS)
        if category == "applicability":
            expected.add("applicable_ids")
        _exact_keys(entry, expected, f"{where} (category {category})")
        identifier = _require_text(entry["id"], f"{where}.id")
        if identifier in seen_ids:
            raise Phase4CValidationError("duplicate query id")
        text = _require_text(entry["query"], f"{where}.query")
        raw_bytes = len(text.encode("utf-8"))
        if raw_bytes > BOUNDS.max_query_bytes:
            raise Phase4CValidationError(
                f"{where}.query: {raw_bytes} raw UTF-8 bytes exceeds the "
                f"{BOUNDS.max_query_bytes}-byte bound"
            )
        top_k = _require_int(entry["top_k"], f"{where}.top_k")
        if top_k != TOP_K_BY_CATEGORY[category]:
            raise Phase4CValidationError(
                f"{where}.top_k: category {category} requires top_k "
                f"{TOP_K_BY_CATEGORY[category]}, got {top_k}"
            )
        relevant_ids = _require_unique_text_list(
            entry["relevant_ids"], f"{where}.relevant_ids"
        )
        unknown = sorted(set(relevant_ids) - corpus_ids)
        if unknown:
            raise Phase4CValidationError(f"{where}.relevant_ids: not in the corpus {unknown}")
        applicable_ids: tuple[str, ...] | None = None
        if category == "applicability":
            applicable_ids = _require_unique_text_list(
                entry["applicable_ids"], f"{where}.applicable_ids"
            )
            if not set(applicable_ids) <= set(relevant_ids):
                raise Phase4CValidationError(
                    f"{where}.applicable_ids: must be a subset of relevant_ids"
                )
            expected_applicable = set(relevant_ids) & applicable_corpus_ids
            if set(applicable_ids) != expected_applicable:
                raise Phase4CValidationError(
                    f"{where}.applicable_ids: disagrees with corpus applicability "
                    f"labels {sorted(expected_applicable)}"
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
        raise Phase4CValidationError(
            f"gold query category distribution mismatch: {counts}"
        )
    return tuple(queries), thresholds


def load_aliases(fixtures: Path) -> tuple[AliasEntry, ...]:
    path = fixtures / NAME_ALIASES_NAME
    document = load_object(path)
    _exact_keys(document, ALIAS_FILE_KEYS, "name alias manifest")
    if document["schema_version"] != ALIAS_SCHEMA_VERSION:
        raise Phase4CValidationError("unsupported name alias manifest schema version")
    if document["fixture_license"] != FIXTURE_LICENSE:
        raise Phase4CValidationError("unsupported fixture license")
    entries = document["aliases"]
    if not isinstance(entries, list) or not entries:
        raise Phase4CValidationError("name alias manifest aliases must be a non-empty list")

    aliases: list[AliasEntry] = []
    seen_ids: set[str] = set()
    seen_alias_tokens: set[tuple[str, ...]] = set()
    for index, entry in enumerate(entries):
        where = f"aliases[{index}]"
        if not isinstance(entry, dict):
            raise Phase4CValidationError(f"{where}: alias entry must be an object")
        _exact_keys(entry, ALIAS_ENTRY_KEYS, where)
        identifier = _require_text(entry["id"], f"{where}.id")
        if identifier in seen_ids:
            raise Phase4CValidationError("duplicate alias entry id")
        alias = _require_text(entry["alias"], f"{where}.alias")
        alias_tokens = tokens(alias)
        if not alias_tokens:
            raise Phase4CValidationError(f"{where}.alias: has no lexical tokens")
        if alias_tokens in seen_alias_tokens:
            raise Phase4CValidationError(f"{where}.alias: duplicate alias name phrase")
        phrases = _require_unique_text_list(
            entry["content_phrases"], f"{where}.content_phrases"
        )
        for offset, phrase in enumerate(phrases):
            if not tokens(phrase):
                raise Phase4CValidationError(
                    f"{where}.content_phrases[{offset}]: has no lexical tokens"
                )
        aliases.append(
            AliasEntry(identifier=identifier, alias=alias, content_phrases=phrases)
        )
        seen_ids.add(identifier)
        seen_alias_tokens.add(alias_tokens)
    return tuple(aliases)


__all__ = [
    "ALIAS_ENTRY_KEYS",
    "ALIAS_FILE_KEYS",
    "AliasEntry",
    "CORPUS_KEYS",
    "CORPUS_MANIFEST_NAME",
    "DOCUMENT_KEYS",
    "Document",
    "GOLD_KEYS",
    "GOLD_QUERIES_NAME",
    "GoldQuery",
    "NAME_ALIASES_NAME",
    "QUERY_KEYS",
    "load_aliases",
    "load_corpus",
    "load_gold",
    "load_object",
    "reject_duplicate_keys",
]
