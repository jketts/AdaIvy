"""Protocol ports for the three Phase 4C retrieval signals.

The ports exist so the acceptance suite can substitute a degenerate signal --
a lexical signal that retrieves nothing, an empty absence-operator vocabulary,
an alias table with one entry removed -- without the benchmark harness growing
a branch for each case. ADR-0032 requires the acceptance suite to demonstrate
the exclusion invariants and the label-separation boundary as properties, and a
property over a signal needs the signal to be substitutable.

The ports also record the direction of each signal in the type system:

* `LexicalSignal` is the only port that may introduce a document.
* `AliasSignal` may introduce a document, and only through content phrases.
* `DisclaimerSignal` returns verdicts, never scores and never documents. Its
  recorded direction under ADR-0032 is that the signal may only *remove* a
  candidate: it returns no scores and no documents, so no implementation is
  able to raise a fused score or add a candidate. Fusion applies the removal,
  and it leaves every score exactly as the lexical and alias signals set it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LexicalCandidate:
    """One BM25 hit. `bm25` is the raw SQLite value: lower is more relevant."""

    document_id: str
    bm25: float


@dataclass(frozen=True)
class AliasExpansion:
    """One recognised alias name phrase and the documents its content matched."""

    entry_id: str
    alias: str
    matched: tuple[tuple[str, tuple[str, ...]], ...]
    """`(document_id, matched_content_phrases)` pairs, sorted by document id."""


@dataclass(frozen=True)
class DisclaimerVerdict:
    """An exclusion verdict for one candidate document.

    `excluded` is boolean: an absence operator and an evidence noun co-occur in
    one sentence of the document, and the query reached the document at all.
    There is no cue-count threshold. `object_level_cues` is recorded for
    transparency and never affects `excluded`.
    """

    document_id: str
    excluded: bool
    absence_operators: tuple[str, ...]
    evidence_nouns: tuple[str, ...]
    object_level_cues: tuple[str, ...]
    matched_query_terms: tuple[str, ...]


@runtime_checkable
class LexicalSignal(Protocol):
    def candidates(self, query: str, *, limit: int) -> tuple[LexicalCandidate, ...]:
        ...


@runtime_checkable
class AliasSignal(Protocol):
    def expand(self, query: str, *, limit: int) -> tuple[AliasExpansion, ...]:
        ...


@runtime_checkable
class DisclaimerSignal(Protocol):
    def verdicts(
        self, query: str, document_ids: Sequence[str]
    ) -> tuple[DisclaimerVerdict, ...]:
        ...


__all__ = [
    "AliasExpansion",
    "AliasSignal",
    "DisclaimerSignal",
    "DisclaimerVerdict",
    "LexicalCandidate",
    "LexicalSignal",
]
