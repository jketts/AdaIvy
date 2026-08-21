"""Signal 1: the frozen SQLite FTS5/BM25 lexical baseline.

This mirrors `spikes/phase4c_benchmark/evaluator.py` exactly and deliberately
duplicates its constants rather than importing them: a spike is not a
production dependency, and ADR-0031 requires the production module to declare
its own method. The two must agree, and the acceptance suite asserts they do.

Label separation: only document body bytes reach an indexed column. Document
ids and the `source_id`/`normalized_start` join columns are UNINDEXED, and
`source_class`, `applicability`, and `duplicate_group` never reach SQLite at
all. `title` and `unit_type` stay empty because the frozen corpus is
single-paragraph plain text with no title line and no unit-type marker;
populating them from the document id or the source class would make an expected
id a retrieval feature.

Declared provenance is derived from the same constants that build the executed
SQL, and the executed SQL text is reported verbatim, so the declared method
cannot drift from the method run.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from .bounds import BOUNDS, Phase4CValidationError
from .fixtures import Document
from .ports import LexicalCandidate
from .text import NORMALIZATION_FORM, tokens


METHOD = "sqlite-fts5-bm25-lexical"
TOKENIZER = "unicode61 remove_diacritics 0"
INDEXED_FIELDS = ("title", "body", "unit_type")
FIELD_WEIGHTS = (2.0, 1.0, 0.5)
UNINDEXED_FIELDS = ("document_id", "source_id", "normalized_start")
FIELD_SOURCES = {
    "title": "empty-corpus-has-no-title-content",
    "body": "document-source-bytes-nfc",
    "unit_type": "empty-corpus-has-no-unit-type-content",
}
TIE_BREAK = "score ASC, document_id ASC"

CREATE_STATEMENT = (
    "CREATE VIRTUAL TABLE lexical USING fts5("
    + ", ".join(f"{name} UNINDEXED" for name in UNINDEXED_FIELDS)
    + ", "
    + ", ".join(INDEXED_FIELDS)
    + f", tokenize='{TOKENIZER}')"
)
INSERT_STATEMENT = (
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
    + ") AS score FROM lexical WHERE lexical MATCH ? "
    + "ORDER BY score ASC, document_id ASC LIMIT ?"
)


def declared_method() -> dict[str, object]:
    """Provenance built from the same constants that build the SQL above."""

    return {
        "method": METHOD,
        "tokenizer": TOKENIZER,
        "normalization_form": NORMALIZATION_FORM,
        "indexed_fields": list(INDEXED_FIELDS),
        "field_weights": list(FIELD_WEIGHTS),
        "field_sources": dict(FIELD_SOURCES),
        "unindexed_fields": list(UNINDEXED_FIELDS),
        "tie_break": TIE_BREAK,
        "create_statement": CREATE_STATEMENT,
        "insert_statement": INSERT_STATEMENT,
        "search_statement": SEARCH_STATEMENT,
    }


def corpus_rows(documents: Sequence[Document]) -> list[tuple[str, str, str, str]]:
    """`(document_id, title, body, unit_type)` rows. Body bytes only."""

    return [(document.identifier, "", document.text, "") for document in documents]


def fts_expression(query: str) -> str:
    """The OR-combined quoted token expression actually sent to FTS5."""

    query_tokens = tokens(query)
    if not query_tokens:
        raise Phase4CValidationError("query has no lexical tokens")
    return " OR ".join('"' + token.replace('"', '""') + '"' for token in query_tokens)


def open_index(rows: Sequence[tuple[str, str, str, str]]) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute(CREATE_STATEMENT)
    connection.executemany(
        INSERT_STATEMENT,
        [
            (identifier, identifier, "0", title, body, unit_type)
            for identifier, title, body, unit_type in rows
        ],
    )
    return connection


def derived_db_bytes(connection: sqlite3.Connection) -> int:
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    return page_count * page_size


class LexicalIndex:
    """A `LexicalSignal` over one in-memory FTS5 index."""

    signal_id = METHOD

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def candidates(self, query: str, *, limit: int) -> tuple[LexicalCandidate, ...]:
        if limit < 1 or limit > BOUNDS.max_candidates_per_signal:
            raise Phase4CValidationError(
                f"lexical candidate limit {limit} is outside "
                f"1..{BOUNDS.max_candidates_per_signal}"
            )
        rows = self._connection.execute(
            SEARCH_STATEMENT, (fts_expression(query), limit)
        ).fetchall()
        if len(rows) > BOUNDS.max_candidates_per_signal:
            raise Phase4CValidationError("lexical candidate bound exceeded")
        return tuple(
            LexicalCandidate(document_id=str(row[0]), bm25=float(row[1])) for row in rows
        )


class EmptyLexicalIndex:
    """A `LexicalSignal` that retrieves nothing.

    Exists for the total-retrieval-collapse case the acceptance suite requires:
    every ratio must then report `None` with its zero denominator and an
    `undetermined` gate, never a passing `0`.
    """

    signal_id = "empty-lexical-signal"

    def candidates(self, query: str, *, limit: int) -> tuple[LexicalCandidate, ...]:
        return ()


def probe(documents: Sequence[Document], query: str, *, limit: int | None = None) -> list[str]:
    """Diagnostic retrieval used by the label-separation tests.

    Any token that exists only in a document id, source class, applicability
    label, or duplicate group must retrieve nothing.
    """

    connection = open_index(corpus_rows(documents))
    try:
        index = LexicalIndex(connection)
        bound = min(len(documents), BOUNDS.max_candidates_per_signal)
        return [
            candidate.document_id
            for candidate in index.candidates(query, limit=limit or bound)
        ]
    finally:
        connection.close()


__all__ = [
    "CREATE_STATEMENT",
    "EmptyLexicalIndex",
    "FIELD_SOURCES",
    "FIELD_WEIGHTS",
    "INDEXED_FIELDS",
    "INSERT_STATEMENT",
    "LexicalIndex",
    "METHOD",
    "SEARCH_STATEMENT",
    "TIE_BREAK",
    "TOKENIZER",
    "UNINDEXED_FIELDS",
    "corpus_rows",
    "declared_method",
    "derived_db_bytes",
    "fts_expression",
    "open_index",
    "probe",
]
