"""Protocol ports for the three Phase 4C retrieval signals.

The ports exist so the acceptance suite can substitute a degenerate signal --
a lexical signal that retrieves nothing, an empty cue table, an alias table
with one entry removed -- without the benchmark harness growing a branch for
each case. ADR-0031 and ADR-0046 require the acceptance suite to demonstrate the
suppression-only and label-separation boundaries as properties, and a property
over a signal needs the signal to be substitutable.

The ports also record the direction of each signal in the type system:

* `LexicalSignal` is the only port that may introduce a document.
* `AliasSignal` may introduce a document, and only through content phrases.
* `HedgeSignal` returns verdicts, never scores and never documents. Fusion
  applies the penalty and performs the removal, so no implementation of
  `HedgeSignal` is able to raise a fused score, add a candidate, or promote one.
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
class HedgeVerdict:
    """A suppression verdict for one candidate document.

    `suppressed` is boolean: presence of an in-scope self-disclaiming cue, with
    no cue-count threshold. `object_level_cues` is recorded for transparency and
    never affects `suppressed`.

    The field is named `suppressed` rather than ADR-0031's `demoted` because
    under ADR-0046 the consequence is removal from the returned list, not a rank
    penalty alone. A field called `demoted` that removes documents would be a
    lie in a self-describing report.
    """

    document_id: str
    suppressed: bool
    self_disclaiming_cues: tuple[str, ...]
    object_level_cues: tuple[str, ...]
    scoped_query_terms: tuple[str, ...]


@runtime_checkable
class LexicalSignal(Protocol):
    def candidates(self, query: str, *, limit: int) -> tuple[LexicalCandidate, ...]:
        ...


@runtime_checkable
class AliasSignal(Protocol):
    def expand(self, query: str, *, limit: int) -> tuple[AliasExpansion, ...]:
        ...


@runtime_checkable
class HedgeSignal(Protocol):
    def verdicts(
        self, query: str, document_ids: Sequence[str]
    ) -> tuple[HedgeVerdict, ...]:
        ...


__all__ = [
    "AliasExpansion",
    "AliasSignal",
    "HedgeSignal",
    "HedgeVerdict",
    "LexicalCandidate",
    "LexicalSignal",
]
