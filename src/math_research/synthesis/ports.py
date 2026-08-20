"""Stable interfaces for the synthesis slice.

The retrieval index is a port so the bounded multi-hop loop is independent of
whichever lexical, formula, or graph index backs it. Contract Section 6: canonical
source and result state remains independent of any index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True, kw_only=True)
class IndexedResult:
    """One indexed candidate as the index knows it."""

    result_id: str
    source_id: str
    title: str
    terms: tuple[str, ...]
    citations: tuple[str, ...]
    approach_signature: str

    def value(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "source_id": self.source_id,
            "title": self.title,
            "terms": list(self.terms),
            "citations": list(self.citations),
            "approach_signature": self.approach_signature,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class IndexHit:
    """One ordered hit. `rank` is 1-based; `tie_break_key` is the audit witness."""

    result_id: str
    rank: int
    canonical_score: str
    tie_break_key: str


class ResultIndex(Protocol):
    """A deterministic, replaceable retrieval index."""

    adapter_id: str
    adapter_version: str

    def search(self, query: str, *, limit: int) -> tuple[IndexHit, ...]:
        """Ordered hits for one query. Ties must break deterministically."""

    def get(self, result_id: str) -> IndexedResult:
        """The indexed record, for traversal and expansion."""

    def corpus_manifest_hash(self) -> str:
        """Identity of the exact corpus the index was built over."""


__all__ = ["IndexHit", "IndexedResult", "ResultIndex"]
