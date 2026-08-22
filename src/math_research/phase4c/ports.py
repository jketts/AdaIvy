"""Protocol ports for the four Phase 4C retrieval signals.

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
* `SemanticSignal` (ADR-0070) may introduce a document, and only through a
  bounded integer tier credit derived from its exact-cosine RANK. It never
  asserts a score of its own: the credit is a function of the rank, so no
  implementation can hand fusion an arbitrary magnitude.

`SemanticSignal` is keyed on the gold-query IDENTIFIER, not the query text, and
that asymmetry with the other three ports is deliberate. ADR-0070 forbids
computing a query vector inside the retrieval path, so the only query vector
that exists is the one ADR-0065 already froze in the partition, and it is
addressed by the identifier under which it was frozen. A port taking query text
would be a port that could be implemented only by embedding live.
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


@dataclass(frozen=True)
class SemanticCredit:
    """One exact-cosine hit and the bounded credit its RANK earns.

    `cosine_dot` and `cosine_norm_squared_product` are the ADR-0065 exact
    integer cosine terms, `(dot(q,d), |q|^2 * |d|^2)`. They are carried, never
    divided: the quotient is irrational in general, so a float cosine would put
    the ordering on machine noise. They are reported so a reader can recheck the
    ranking by cross-multiplying integers.

    `tier_credit` is derived from `rank` by `bounds.semantic_tier_credit` and
    fusion re-derives it before use, so a signal cannot claim credit its rank
    does not earn.
    """

    document_id: str
    rank: int
    tier_credit: int
    cosine_dot: int
    cosine_norm_squared_product: int


@dataclass(frozen=True)
class SemanticPartitionIdentity:
    """The declared partition, as read from bytes. Binds report identity.

    `manifest_hash` is `None` only for a signal that reads no partition at all,
    which is the ADR-0070 "signal disabled" case and is recorded as such rather
    than presented as a partition that happened to be empty.
    """

    partition_key_string: str
    manifest_hash: str | None
    corpus_provenance: str
    vector_count: int
    corpus_document_count: int
    query_count: int


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


@runtime_checkable
class SemanticSignal(Protocol):
    def partition_identity(self) -> SemanticPartitionIdentity:
        ...

    def credits(self, query_id: str, *, limit: int) -> tuple[SemanticCredit, ...]:
        ...


__all__ = [
    "AliasExpansion",
    "AliasSignal",
    "DisclaimerSignal",
    "DisclaimerVerdict",
    "LexicalCandidate",
    "LexicalSignal",
    "SemanticCredit",
    "SemanticPartitionIdentity",
    "SemanticSignal",
]
