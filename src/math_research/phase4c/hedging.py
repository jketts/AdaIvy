"""Signal 2: hedging-scope discrimination. Demotion only.

ADR-0031 partitions cues by a stated principle rather than by which documents
they happen to separate:

* a **self-disclaiming** cue is about the document's own evidentiary status --
  what this document does not supply, does not cover, or does not establish.
  Only these demote.
* an **object-level** cue is about the mathematics -- something fails, violates
  a hypothesis, or is refuted by a counterexample. These never demote. Negation
  is legitimate content in a contradiction document: a counterexample *is* an
  assertion that something fails, and `boundary-contradiction` carries all three
  object-level cues in a sentence containing matched query terms while being an
  applicable contradiction gold.

Two exclusions from the cue table are deliberate and are recorded here because
adding either would be the fitted-lexicon failure ADR-0031 names as this
slice's weakest point:

* `without` is mathematical content ("without compact resolvent" states a
  hypothesis, not a disclaimer);
* bare `no` is mathematical content and false-positives on
  `renamed-container-count-result` ("so no distribution can keep every container
  single"), which is an applicable renamed gold. The self-disclaiming reading is
  carried by the longer phrase `states no`, which is in the table.

Scope rule: a document is demoted when a matched query term occurs in the same
sentence as a self-disclaiming cue. Sentences come from `text.SENTENCE_RULE`.
A matched query term is a query token, under the shared tokenizer, that occurs
as a token in that sentence. Alias content phrases are not query terms for this
purpose, which keeps the rule conservative -- it can only demote a document the
query itself reached into.

There is **no cue-count threshold**. Presence is boolean. Choosing a count
after observing the corpus is the forbidden outcome "selecting thresholds after
observing a hybrid candidate".

Cue matching is `\\b`-anchored. Without the anchors a cue such as `is not`
matches across the word boundary in `this note`, which is how an earlier draft
of this cue table produced a false positive.
"""

from __future__ import annotations

from collections.abc import Sequence

from .bounds import Phase4CValidationError
from .fixtures import Document
from .ports import HedgeVerdict
from .text import (
    SENTENCE_RULE,
    SENTENCE_SPLIT_PATTERN,
    cue_pattern,
    sentences,
    tokens,
)


SELF_DISCLAIMING_CUES = (
    "does not provide",
    "inapplicable",
    "insufficient",
    "may look",
    "states no",
    "as stated",
)
OBJECT_LEVEL_CUES = ("fails", "violates", "counterexample")

SCOPE_RULE = "matched-query-term-in-same-sentence-as-self-disclaiming-cue"
CUE_COUNT_THRESHOLD = None  # Presence is boolean. There is no threshold.


def declared_method(
    self_disclaiming_cues: Sequence[str] = SELF_DISCLAIMING_CUES,
    object_level_cues: Sequence[str] = OBJECT_LEVEL_CUES,
) -> dict[str, object]:
    return {
        "method": "hedging-scope-demotion",
        "direction": "demotion_only",
        "scope_rule": SCOPE_RULE,
        "sentence_rule": SENTENCE_RULE,
        "sentence_split_pattern": SENTENCE_SPLIT_PATTERN,
        "cue_match": "word-boundary-anchored-phrase",
        "cue_count_threshold": CUE_COUNT_THRESHOLD,
        "self_disclaiming_cues": list(self_disclaiming_cues),
        "object_level_cues": list(object_level_cues),
    }


class HedgingScopeSignal:
    """A `HedgeSignal` over the frozen corpus bytes.

    `self_disclaiming_cues` and `object_level_cues` are constructor arguments
    only so the acceptance suite can assert the two properties ADR-0031
    requires: that an empty demoting table leaves the fused ordering equal to
    the pure lexical ordering, and that no object-level cue can demote. The
    benchmark path always passes the frozen tables.
    """

    signal_id = "hedging-scope-demotion"

    def __init__(
        self,
        documents: Sequence[Document],
        *,
        self_disclaiming_cues: Sequence[str] = SELF_DISCLAIMING_CUES,
        object_level_cues: Sequence[str] = OBJECT_LEVEL_CUES,
    ) -> None:
        self_set = tuple(self_disclaiming_cues)
        object_set = tuple(object_level_cues)
        overlap = sorted(set(self_set) & set(object_set))
        if overlap:
            raise Phase4CValidationError(
                f"cue classes must be disjoint; shared cues {overlap}"
            )
        self.self_disclaiming_cues = self_set
        self.object_level_cues = object_set
        self._self_patterns = tuple((cue, cue_pattern(cue)) for cue in self_set)
        self._object_patterns = tuple((cue, cue_pattern(cue)) for cue in object_set)
        self._sentences = {
            document.identifier: tuple(
                (sentence.casefold(), frozenset(tokens(sentence)))
                for sentence in sentences(document.text)
            )
            for document in documents
        }

    def verdicts(
        self, query: str, document_ids: Sequence[str]
    ) -> tuple[HedgeVerdict, ...]:
        query_terms = set(tokens(query))
        results: list[HedgeVerdict] = []
        for document_id in document_ids:
            if document_id not in self._sentences:
                raise Phase4CValidationError(
                    f"hedge asked about an unknown document {document_id!r}"
                )
            demoting: set[str] = set()
            object_level: set[str] = set()
            scoped: set[str] = set()
            for folded, sentence_tokens in self._sentences[document_id]:
                matched = query_terms & sentence_tokens
                for cue, pattern in self._object_patterns:
                    if pattern.search(folded):
                        object_level.add(cue)
                if not matched:
                    continue
                for cue, pattern in self._self_patterns:
                    if pattern.search(folded):
                        demoting.add(cue)
                        scoped |= matched
            results.append(
                HedgeVerdict(
                    document_id=document_id,
                    demoted=bool(demoting),
                    self_disclaiming_cues=tuple(sorted(demoting)),
                    object_level_cues=tuple(sorted(object_level)),
                    scoped_query_terms=tuple(sorted(scoped)),
                )
            )
        return tuple(results)


__all__ = [
    "CUE_COUNT_THRESHOLD",
    "HedgingScopeSignal",
    "OBJECT_LEVEL_CUES",
    "SCOPE_RULE",
    "SELF_DISCLAIMING_CUES",
    "declared_method",
]
