"""Exact parsed spans over immutable source bytes (ADR-0060 conventions).

A span is a character range into the strict UTF-8 decode of the stored bytes,
carried with the sha256 of its exact substring, so a later reader can verify a
quotation against the immutable object without trusting the quoter.  The
transformation identifier is pinned: no normalization, no trimming, no
collapse — an offset that does not reproduce its text hash is tamper evidence,
not a formatting difference.

Parsing is deliberately simple and total over its declared inputs: paragraphs
are maximal runs of non-blank lines.  Anything the parser cannot decode or
that yields no spans is a ``parse_failure`` and the document is quarantined —
recorded, retained, excluded — rather than approximated.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import PARSED_SPANS_SCHEMA_VERSION
from .constants import (
    HASH_PATTERN,
    IDENTIFIER_PATTERN,
    MAX_DOCUMENT_CHARS,
    MAX_SPANS_PER_DOCUMENT,
    SPAN_TRANSFORMATION,
)
from .errors import SpansInvalidError
from .serialization import sha256_bytes, sealed, verify_sealed

SPANS_FIELDS = frozenset({
    "schema_version", "document_id", "source_sha256", "text_encoding",
    "transformation", "span_count", "spans", "content_hash",
})
_SPAN_FIELDS = frozenset({"span_index", "start_offset", "end_offset", "exact_text_hash"})


class ParseFailure(Exception):
    """Raised for quarantine, never surfaced as a record."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def parse_spans(
    body: bytes, *, document_id: str, source_sha256: str,
) -> dict[str, Any]:
    """Deterministic paragraph spans, or :class:`ParseFailure`."""

    try:
        text = body.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise ParseFailure(f"not strict UTF-8: {error}") from error
    if len(text) > MAX_DOCUMENT_CHARS:
        raise ParseFailure(
            f"document decodes to {len(text)} characters; the pinned bound is "
            f"{MAX_DOCUMENT_CHARS}"
        )
    spans: list[dict[str, Any]] = []
    offset = 0
    start: int | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped and start is None:
            start = offset
        if not stripped and start is not None:
            end = offset
            while end > start and text[end - 1] in "\r\n":
                end -= 1
            spans.append({"start": start, "end": end})
            start = None
        offset += len(line)
    if start is not None:
        end = len(text)
        while end > start and text[end - 1] in "\r\n":
            end -= 1
        spans.append({"start": start, "end": end})
    if not spans:
        raise ParseFailure("document yields no spans")
    if len(spans) > MAX_SPANS_PER_DOCUMENT:
        raise ParseFailure(
            f"document yields {len(spans)} spans; the pinned bound is "
            f"{MAX_SPANS_PER_DOCUMENT}"
        )
    entries = [
        {
            "span_index": index,
            "start_offset": span["start"],
            "end_offset": span["end"],
            "exact_text_hash": sha256_bytes(
                text[span["start"]: span["end"]].encode("utf-8")
            ),
        }
        for index, span in enumerate(spans)
    ]
    return verify_spans(sealed({
        "schema_version": PARSED_SPANS_SCHEMA_VERSION,
        "document_id": document_id,
        "source_sha256": source_sha256,
        "text_encoding": "utf-8",
        "transformation": SPAN_TRANSFORMATION,
        "span_count": len(entries),
        "spans": entries,
        "content_hash": None,
    }))


def verify_spans(value: Mapping[str, Any]) -> dict[str, Any]:
    spans_doc = verify_sealed(
        value, label="parsed spans document", code=SpansInvalidError.code,
    )
    if set(spans_doc) != SPANS_FIELDS:
        raise SpansInvalidError(
            "parsed spans fields differ: "
            f"missing={sorted(SPANS_FIELDS - set(spans_doc))}, "
            f"extra={sorted(set(spans_doc) - SPANS_FIELDS)}"
        )
    if spans_doc["schema_version"] != PARSED_SPANS_SCHEMA_VERSION:
        raise SpansInvalidError("parsed spans schema differs")
    if not isinstance(spans_doc["document_id"], str) or IDENTIFIER_PATTERN.fullmatch(
        spans_doc["document_id"]
    ) is None:
        raise SpansInvalidError("parsed spans document identifier differs")
    if not isinstance(spans_doc["source_sha256"], str) or HASH_PATTERN.fullmatch(
        spans_doc["source_sha256"]
    ) is None:
        raise SpansInvalidError("parsed spans source hash differs")
    if spans_doc["text_encoding"] != "utf-8" or spans_doc["transformation"] != SPAN_TRANSFORMATION:
        raise SpansInvalidError("parsed spans transformation differs; spans are exact")
    entries = spans_doc["spans"]
    if (
        not isinstance(entries, list) or not entries
        or spans_doc["span_count"] != len(entries)
        or len(entries) > MAX_SPANS_PER_DOCUMENT
    ):
        raise SpansInvalidError("parsed spans count differs")
    previous_end = -1
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != _SPAN_FIELDS:
            raise SpansInvalidError(f"span {index} fields differ")
        if entry["span_index"] != index:
            raise SpansInvalidError(f"span {index} declares index {entry['span_index']!r}")
        start = entry["start_offset"]
        end = entry["end_offset"]
        for item in (start, end):
            if isinstance(item, bool) or not isinstance(item, int) or item < 0:
                raise SpansInvalidError(f"span {index} offsets differ")
        if not previous_end < start < end or end > MAX_DOCUMENT_CHARS:
            raise SpansInvalidError(
                f"span {index} is not ordered, disjoint, and within bounds"
            )
        if not isinstance(entry["exact_text_hash"], str) or HASH_PATTERN.fullmatch(
            entry["exact_text_hash"]
        ) is None:
            raise SpansInvalidError(f"span {index} exact text hash differs")
        previous_end = end
    return spans_doc


def verify_spans_against_source(spans_doc: Mapping[str, Any], body: bytes) -> None:
    """Every span must reproduce its exact text hash from the stored bytes."""

    verified = verify_spans(spans_doc)
    if sha256_bytes(body) != verified["source_sha256"]:
        raise SpansInvalidError("source bytes do not hash to the spans' source")
    text = body.decode("utf-8", "strict")
    for entry in verified["spans"]:
        exact = text[entry["start_offset"]: entry["end_offset"]]
        if sha256_bytes(exact.encode("utf-8")) != entry["exact_text_hash"]:
            raise SpansInvalidError(
                f"span {entry['span_index']} does not reproduce its exact text"
            )


__all__ = [
    "ParseFailure",
    "SPANS_FIELDS",
    "parse_spans",
    "verify_spans",
    "verify_spans_against_source",
]
