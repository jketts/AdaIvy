"""Signal 2: hedging-scope discrimination. Suppression only.

ADR-0031 partitions cues by a stated principle rather than by which documents
they happen to separate:

* a **self-disclaiming** cue is about the document's own evidentiary status --
  what this document does not supply, does not cover, or does not establish.
  Only these suppress.
* an **object-level** cue is about the mathematics -- something fails, violates
  a hypothesis, or is refuted by a counterexample. These never suppress. Negation
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

Scope rule (ADR-0046): a document is suppressed when a matched query term occurs
in the same **scope block** as a self-disclaiming cue. Scope blocks come from
`text.SCOPE_BLOCK_RULE`, which unions a sentence with its immediate predecessor
exactly when the sentence opens with a sentence-initial anaphor; the sentence
partition of `text.SENTENCE_RULE` is still declared and still reported, because
the block rule is defined on top of it. A matched query term is a query token,
under the shared tokenizer, that occurs as a token in that block. Alias content
phrases are not query terms for this purpose, which keeps the rule conservative
-- it can only suppress a document the query itself reached into.

ADR-0031 froze the sentence as the scope unit. That unit required a disclaiming
sentence to restate its own subject, which is a linguistic error independent of
any measurement; see the `text` module docstring for the statement of the error
and for the standing limitation of sentence-initial token matching. Suppression
is removal from the returned list, not a rank penalty, because retrieval returns
a list and precision is measured over what is returned. Suppression is a
retrieval decision and never an applicability judgement: a suppressed document
is not thereby found inapplicable.

There is **no cue-count threshold** and no numeric scope parameter of any kind.
Presence is boolean and antecedent depth is exactly one. Choosing a count or a
window length after observing the corpus is the forbidden outcome "selecting
thresholds after observing a hybrid candidate".

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
    ANAPHOR_PRONOUNS,
    SCOPE_BLOCK_RULE,
    SENTENCE_RULE,
    SENTENCE_SPLIT_PATTERN,
    cue_pattern,
    scope_blocks,
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

SCOPE_RULE = "matched-query-term-in-same-scope-block-as-self-disclaiming-cue"
CUE_COUNT_THRESHOLD = None  # Presence is boolean. There is no threshold.


def declared_method(
    self_disclaiming_cues: Sequence[str] = SELF_DISCLAIMING_CUES,
    object_level_cues: Sequence[str] = OBJECT_LEVEL_CUES,
) -> dict[str, object]:
    return {
        "method": "hedging-scope-suppression",
        "direction": "suppression_only",
        "scope_rule": SCOPE_RULE,
        "scope_block_rule": SCOPE_BLOCK_RULE,
        "anaphor_pronouns": list(ANAPHOR_PRONOUNS),
        "anaphor_antecedent_depth": 1,
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
    only so the acceptance suite can assert the two properties ADR-0031 and
    ADR-0046 require: that an empty suppressing table leaves the fused ordering
    equal to the pure lexical ordering and suppresses nothing, and that no
    object-level cue can suppress. The benchmark path always passes the frozen
    tables, which this slice does not touch.
    """

    signal_id = "hedging-scope-suppression"

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
        self._scope_blocks = {
            document.identifier: tuple(
                (block.casefold(), frozenset(tokens(block)))
                for block in scope_blocks(document.text)
            )
            for document in documents
        }

    def verdicts(
        self, query: str, document_ids: Sequence[str]
    ) -> tuple[HedgeVerdict, ...]:
        query_terms = set(tokens(query))
        results: list[HedgeVerdict] = []
        for document_id in document_ids:
            if document_id not in self._scope_blocks:
                raise Phase4CValidationError(
                    f"hedge asked about an unknown document {document_id!r}"
                )
            suppressing: set[str] = set()
            object_level: set[str] = set()
            scoped: set[str] = set()
            for folded, block_tokens in self._scope_blocks[document_id]:
                matched = query_terms & block_tokens
                for cue, pattern in self._object_patterns:
                    if pattern.search(folded):
                        object_level.add(cue)
                if not matched:
                    continue
                for cue, pattern in self._self_patterns:
                    if pattern.search(folded):
                        suppressing.add(cue)
                        scoped |= matched
            results.append(
                HedgeVerdict(
                    document_id=document_id,
                    suppressed=bool(suppressing),
                    self_disclaiming_cues=tuple(sorted(suppressing)),
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
