"""Signal 3: content-keyed alias expansion.

An alias entry maps a *name phrase* to *content phrases*. Recognition and
matching are strictly separated:

* recognition reads the query only, and matches the alias name phrase as a
  contiguous token run inside the query token sequence;
* matching reads document bodies only, and matches each content phrase as a
  contiguous token run inside the document token sequence.

Neither step ever reads a document identifier. `AliasEntry.identifier` is a
reporting label; this module never compares it to a document, and the alias
fixture contains no document identifier at all, which the acceptance suite
asserts against the raw fixture bytes. Keying an alias to an expected document
id would make an expected id a retrieval feature, which the benchmark lists as
a forbidden outcome.

Token-run matching rather than raw substring matching is what lets the frozen
content phrase `finite subcover` match the corpus spelling `finite-subcover`.
"""

from __future__ import annotations

from collections.abc import Sequence

from .bounds import BOUNDS, Phase4CValidationError
from .fixtures import AliasEntry, Document
from .ports import AliasExpansion
from .text import contains_token_run, tokens


ALIAS_PHRASE_POINTS = 1.0
"""Score contributed per distinct matched content phrase.

This is a unit weight, not a tuned parameter. It was not chosen by observing
which value moved a gate.

**The ADR-0032 justification for that claim no longer holds, and the correction
is recorded here rather than repaired by retuning.** ADR-0032 argued the weight
was inert because "every renamed-control query's fused candidate set is smaller
than its top-k of ten, so `renamed_known_result_recall_at_10` is invariant to any
strictly positive value". That reasoning depended on the top-k cutoff never
binding, and ADR-0066 makes it bind: the semantic signal names ten candidates for
every query, so every renamed control now has at least ten fused candidates. At a
weight of `0.001` the alias contribution is smaller than a single semantic tier
point, the two semantically-unreachable renamed golds fall out of the top ten,
and the gate reads 0.5.

So the weight is now LOAD-BEARING, and saying so is the honest statement. It has
NOT been re-chosen in response: it remains the unit value it has always had, and
picking a value because it made a gate pass would be fitting a weight to the
fixtures it is measured on. `tests/test_phase4c_hybrid_retrieval.py` pins the
measured conditional behaviour, and
`tests/test_phase4c_semantic_signal.py` records it as a regression.
"""


def declared_method(alias_phrase_points: float = ALIAS_PHRASE_POINTS) -> dict[str, object]:
    return {
        "method": "content-keyed-alias-expansion",
        "recognition": "alias-name-phrase-as-contiguous-query-token-run",
        "matching": "content-phrase-as-contiguous-document-token-run",
        "keyed_on": "name_phrase",
        "expands_to": "content_phrases",
        "reads_document_identifiers": False,
        "alias_phrase_points": alias_phrase_points,
    }


class AliasExpansionSignal:
    """An `AliasSignal` over one frozen alias table and the corpus bodies."""

    signal_id = "content-keyed-alias-expansion"

    def __init__(
        self, documents: Sequence[Document], entries: Sequence[AliasEntry]
    ) -> None:
        self._entries = tuple(entries)
        # Document bodies only. No identifier, class, or label is tokenized here.
        self._document_tokens = tuple(
            (document.identifier, tokens(document.text)) for document in documents
        )

    def entries(self) -> tuple[AliasEntry, ...]:
        return self._entries

    def matched_document_ids(self, entry: AliasEntry) -> tuple[str, ...]:
        matched = [
            identifier
            for identifier, document_tokens in self._document_tokens
            if any(
                contains_token_run(document_tokens, phrase)
                for phrase in entry.content_phrase_tokens
            )
        ]
        return tuple(sorted(matched))

    def expand(self, query: str, *, limit: int) -> tuple[AliasExpansion, ...]:
        if limit < 1 or limit > BOUNDS.max_candidates_per_signal:
            raise Phase4CValidationError(
                f"alias candidate limit {limit} is outside "
                f"1..{BOUNDS.max_candidates_per_signal}"
            )
        query_tokens = tokens(query)
        expansions: list[AliasExpansion] = []
        introduced: set[str] = set()
        for entry in self._entries:
            if not contains_token_run(query_tokens, entry.alias_tokens):
                continue
            matched: list[tuple[str, tuple[str, ...]]] = []
            for identifier, document_tokens in self._document_tokens:
                phrases = tuple(
                    phrase
                    for phrase, phrase_tokens in zip(
                        entry.content_phrases, entry.content_phrase_tokens, strict=True
                    )
                    if contains_token_run(document_tokens, phrase_tokens)
                )
                if phrases:
                    matched.append((identifier, phrases))
                    introduced.add(identifier)
            expansions.append(
                AliasExpansion(
                    entry_id=entry.identifier,
                    alias=entry.alias,
                    matched=tuple(sorted(matched)),
                )
            )
        if len(introduced) > limit:
            raise Phase4CValidationError(
                f"alias candidate bound exceeded: {len(introduced)} > {limit}"
            )
        return tuple(sorted(expansions, key=lambda item: item.entry_id))


class EmptyAliasSignal:
    """An `AliasSignal` that expands nothing."""

    signal_id = "empty-alias-signal"

    def expand(self, query: str, *, limit: int) -> tuple[AliasExpansion, ...]:
        return ()


__all__ = [
    "ALIAS_PHRASE_POINTS",
    "AliasExpansionSignal",
    "EmptyAliasSignal",
    "declared_method",
]
