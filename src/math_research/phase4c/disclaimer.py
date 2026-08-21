"""Signal 2: evidentiary self-disclaimer. Exclusion only.

ADR-0032 replaces the ADR-0031 hedging-scope signal. Three things changed and
each has a stated principle rather than a measured justification.

**Cues are composed, not enumerated.** ADR-0031 listed six self-disclaiming
phrases, and its own acceptance suite asserted that the six were coextensive
with the three non-applicable documents in the corpus. A list that is
coextensive with its target set measures the list, not the method. A disclaimer
here fires only where two frozen vocabularies meet:

* an **absence operator** whose subject is the document's own supply of
  material -- `does not provide`, `states no`, `is inapplicable`,
  `is insufficient`, and the frames `no ... is supplied` and `no ... is given`;
* an **evidence noun** naming what a document supplies -- `theorem`, `lemma`,
  `proof`, `hypothesis`, `hypotheses`, `certificate`, `bound`, `eigenbasis`,
  `applicability`, `witness`.

The operator vocabulary carries *subjecthood* and the noun vocabulary carries
*evidentiality*. Neither fires alone. That is what separates
`this note states no theorem, hypotheses, or applicable proof` -- the document
disclaiming its own coverage -- from `the argument uses no compactness
hypothesis`, where a mathematical object is the subject and a missing
hypothesis is a strength rather than a gap. `uses no` is therefore not an
operator, and its absence is a consequence of the subjecthood principle rather
than a listed exception.

The two ADR-0031 exclusions survive for the same reason they were made, and now
fall out of the operator rule instead of being enumerated: `without` states a
hypothesis (`without compact resolvent`), and bare `no` is mathematical content
that false-positives on `renamed-container-count-result` ("so no distribution
can keep every container single"). Neither is an operator, so neither fires.

ADR-0031's `may look` is also gone, on principle rather than on measurement:
in `An optimization score may look feasible`, the subject is the score, so the
cue is object-level. That document is still excluded, through
`no ... is supplied` and `is insufficient`, which are about what it supplies.

**Detection is per sentence; scope is the document.** A disclaimer is detected
where an operator and an evidence noun co-occur in one sentence, because that
co-occurrence is what makes the composition a single claim. Its *scope* is the
whole document, because a claim about what this document supplies has the
document as its subject. ADR-0031 scoped self-disclaimers to the sentence, which
was an unmotivated inheritance from the object-level class: object-level cues are
about a local mathematical fact and keep sentence scope, and they still never
exclude.

Document scope is declared valid only where the retrieval unit is a
*single-claim unit*. The Phase 4C corpus documents are two-to-three sentence
single-claim units. When the retrieval unit becomes a multi-section parsed
document -- the deferred Phase 4B projection slice -- the scope must be
re-derived to the smallest enclosing single-claim unit, and this rule may not be
carried across unchanged. That is a boundary, not a fix.

**The verdict excludes rather than demotes.** ADR-0031 records demotion-only as
its own error: with applicability candidate sets of four and five against a
top-k of five, every retrieved relevant document is already inside the cutoff,
so precision is invariant under every reordering. A document whose own bytes
disclaim the evidentiary element the query asks for is not a worse candidate; it
is not a candidate.

Two conservatism rules are kept from ADR-0031. The document must contain at
least one query token, so the signal can only remove a document the query itself
reached. And there is **no cue-count threshold**: presence is boolean, because
selecting a count after observing the corpus is the forbidden outcome "selecting
thresholds after observing a hybrid candidate".

Matching is on token runs, not on regular expressions over raw text. The frames
need no gap parameter: the two parts must appear in order inside one sentence,
and the sentence bounds the gap. A tuned gap width would be exactly the free
parameter this signal is built to avoid.
"""

from __future__ import annotations

from collections.abc import Sequence

from .bounds import Phase4CValidationError
from .fixtures import Document
from .ports import DisclaimerVerdict
from .text import (
    SENTENCE_RULE,
    SENTENCE_SPLIT_PATTERN,
    contains_token_run,
    sentences,
    tokens,
)


# Each operator is one or two ordered token-run parts. A single part is a
# contiguous phrase; two parts are a frame whose gap the sentence bounds.
ABSENCE_OPERATORS: tuple[tuple[str, ...], ...] = (
    ("does not provide",),
    ("states no",),
    ("is inapplicable",),
    ("is insufficient",),
    ("no", "is supplied"),
    ("no", "is given"),
)
EVIDENCE_NOUNS: tuple[str, ...] = (
    "applicability",
    "bound",
    "certificate",
    "eigenbasis",
    "hypotheses",
    "hypothesis",
    "lemma",
    "proof",
    "theorem",
    "witness",
)
OBJECT_LEVEL_CUES: tuple[str, ...] = ("fails", "violates", "counterexample")

DETECTION_RULE = "absence-operator-and-evidence-noun-co-occur-in-one-sentence"
SCOPE_RULE = "detected-per-sentence-applied-to-the-whole-single-claim-unit"
SCOPE_UNIT = "single-claim-document"
DIRECTION = "exclusion_only"
CUE_COUNT_THRESHOLD = None  # Presence is boolean. There is no threshold.
FRAME_GAP_BOUND = "sentence"  # No token-width parameter exists.


def render_operator(operator: Sequence[str]) -> str:
    """`('no', 'is supplied')` renders as `no ... is supplied`."""

    return " ... ".join(operator)


def declared_method(
    absence_operators: Sequence[Sequence[str]] = ABSENCE_OPERATORS,
    evidence_nouns: Sequence[str] = EVIDENCE_NOUNS,
    object_level_cues: Sequence[str] = OBJECT_LEVEL_CUES,
) -> dict[str, object]:
    return {
        "method": "evidentiary-self-disclaimer-exclusion",
        "direction": DIRECTION,
        "detection_rule": DETECTION_RULE,
        "scope_rule": SCOPE_RULE,
        "scope_unit": SCOPE_UNIT,
        "frame_gap_bound": FRAME_GAP_BOUND,
        "sentence_rule": SENTENCE_RULE,
        "sentence_split_pattern": SENTENCE_SPLIT_PATTERN,
        "cue_match": "token-run",
        "cue_count_threshold": CUE_COUNT_THRESHOLD,
        "composition": "operator AND evidence_noun, in one sentence",
        "absence_operators": [render_operator(item) for item in absence_operators],
        "evidence_nouns": list(evidence_nouns),
        "object_level_cues": list(object_level_cues),
    }


def _operator_matches(sentence_tokens: tuple[str, ...], operator: Sequence[str]) -> bool:
    """True when every part of `operator` occurs in order in the sentence."""

    parts = [tokens(part) for part in operator]
    if any(not part for part in parts):
        raise Phase4CValidationError("an absence operator part is empty")
    cursor = 0
    for part in parts:
        index = _find_run(sentence_tokens, part, cursor)
        if index is None:
            return False
        cursor = index + len(part)
    return True


def _find_run(
    haystack: tuple[str, ...], needle: tuple[str, ...], start: int
) -> int | None:
    span = len(needle)
    for index in range(start, len(haystack) - span + 1):
        if haystack[index : index + span] == needle:
            return index
    return None


class SelfDisclaimerSignal:
    """A `DisclaimerSignal` over the frozen corpus bytes.

    The vocabularies are constructor arguments only so the acceptance suite can
    assert the ADR-0032 properties as properties: that neither vocabulary fires
    alone, that emptying either restores the pure lexical ordering, that no
    single entry is coextensive with the target set, and that no object-level
    cue can exclude. The benchmark path always passes the frozen vocabularies.
    """

    signal_id = "evidentiary-self-disclaimer-exclusion"

    def __init__(
        self,
        documents: Sequence[Document],
        *,
        absence_operators: Sequence[Sequence[str]] = ABSENCE_OPERATORS,
        evidence_nouns: Sequence[str] = EVIDENCE_NOUNS,
        object_level_cues: Sequence[str] = OBJECT_LEVEL_CUES,
    ) -> None:
        self.absence_operators = tuple(tuple(item) for item in absence_operators)
        self.evidence_nouns = tuple(evidence_nouns)
        self.object_level_cues = tuple(object_level_cues)

        noun_set = set(self.evidence_nouns)
        overlap = sorted(noun_set & set(self.object_level_cues))
        if overlap:
            raise Phase4CValidationError(
                f"evidence nouns and object-level cues must be disjoint; shared {overlap}"
            )
        for operator in self.absence_operators:
            if not operator or len(operator) > 2:
                raise Phase4CValidationError(
                    "an absence operator must have one or two parts"
                )
            operator_tokens = {
                token for part in operator for token in tokens(part)
            }
            shared = sorted(operator_tokens & noun_set)
            if shared:
                raise Phase4CValidationError(
                    "an absence operator may not contain an evidence noun; "
                    f"{render_operator(operator)} shares {shared}"
                )

        self._sentences = {
            document.identifier: tuple(
                tokens(sentence) for sentence in sentences(document.text)
            )
            for document in documents
        }
        self._document_tokens = {
            document.identifier: frozenset(tokens(document.text))
            for document in documents
        }

    def verdicts(
        self, query: str, document_ids: Sequence[str]
    ) -> tuple[DisclaimerVerdict, ...]:
        query_terms = set(tokens(query))
        results: list[DisclaimerVerdict] = []
        for document_id in document_ids:
            if document_id not in self._sentences:
                raise Phase4CValidationError(
                    f"the disclaimer signal was asked about an unknown document "
                    f"{document_id!r}"
                )
            operators: set[str] = set()
            nouns: set[str] = set()
            object_level: set[str] = set()
            for sentence_tokens in self._sentences[document_id]:
                present = set(sentence_tokens)
                for cue in self.object_level_cues:
                    if contains_token_run(sentence_tokens, tokens(cue)):
                        object_level.add(cue)
                matched_operators = [
                    render_operator(operator)
                    for operator in self.absence_operators
                    if _operator_matches(sentence_tokens, operator)
                ]
                matched_nouns = sorted(present & set(self.evidence_nouns))
                # Composition: both halves must be present in this sentence.
                if not matched_operators or not matched_nouns:
                    continue
                operators.update(matched_operators)
                nouns.update(matched_nouns)
            matched_query_terms = sorted(
                query_terms & self._document_tokens[document_id]
            )
            excluded = bool(operators and nouns and matched_query_terms)
            results.append(
                DisclaimerVerdict(
                    document_id=document_id,
                    excluded=excluded,
                    absence_operators=tuple(sorted(operators)),
                    evidence_nouns=tuple(sorted(nouns)),
                    object_level_cues=tuple(sorted(object_level)),
                    matched_query_terms=tuple(matched_query_terms),
                )
            )
        return tuple(results)


__all__ = [
    "ABSENCE_OPERATORS",
    "CUE_COUNT_THRESHOLD",
    "DETECTION_RULE",
    "DIRECTION",
    "EVIDENCE_NOUNS",
    "FRAME_GAP_BOUND",
    "OBJECT_LEVEL_CUES",
    "SCOPE_RULE",
    "SCOPE_UNIT",
    "SelfDisclaimerSignal",
    "declared_method",
    "render_operator",
]
