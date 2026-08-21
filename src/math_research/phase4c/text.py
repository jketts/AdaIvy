"""Deterministic text normalization shared by all three Phase 4C signals.

One tokenizer serves every signal so that a "matched query term" means the same
thing to the lexical index, the hedging-scope rule, and alias phrase matching.
It mirrors the frozen lexical baseline exactly: Unicode NFC, the token regex
`[^\\W_]+`, and `str.casefold()`.

Sentence splitting is part of the declared method, not an implementation
detail:

1. normalize to NFC and collapse every run of whitespace to a single space;
2. split immediately after a `.`, `!`, or `?` that is followed by whitespace;
3. keep the trailing fragment, so text without terminal punctuation is exactly
   one sentence.

The rule has no abbreviation, decimal, or quotation handling. That is a stated
limitation rather than an oversight: the frozen benchmark corpus contains no
abbreviation, no decimal number, and no quoted period, so adding heuristics
would add untested behaviour. A corpus that needed them would need a new
declared rule and a new report schema version.

The *scope unit* of the hedging signal is the scope block, not the sentence
(ADR-0046). The sentence unit ADR-0031 froze required a disclaiming sentence to
restate its own subject, and English expository prose does not do that: a writer
who introduces a result in one sentence disclaims it in the next with a pronoun
("It does not provide...", "This says nothing about..."), because repeating the
noun phrase would be redundant. So a same-sentence rule systematically misses
the well-written disclaimers and fires only on the redundant ones.

A scope block is each sentence, unioned with the immediately preceding sentence
if and only if the sentence begins with a member of `ANAPHOR_PRONOUNS`:

1. the anaphor list is closed, frozen, lowercase, and single-token, and is
   matched in sentence-initial position only, under the tokenizer above;
2. the antecedent is the preceding *sentence*, never the preceding *block*, so
   the relation is not transitive. Antecedent depth is exactly one and that is
   not a threshold: chaining would make the rule a window, a window has a
   length, and a length read off a corpus is a forbidden outcome;
3. the first sentence of a document is never unioned with anything.

Stated limitation, in the same voice as the sentence rule above: this is
sentence-initial token matching, not anaphora resolution. It cannot tell a
referential `it` from an expletive `it`, cannot resolve across a paragraph
boundary, and cannot pick the correct antecedent when the preceding sentence
introduces two candidates. Real anaphora resolution needs a parser, which is
forbidden on a documented acceptance path (ADR-0026, AGENTS.md), so the gap is
recorded rather than worked around.
"""

from __future__ import annotations

import re
import unicodedata


NORMALIZATION_FORM = "NFC"
TOKEN_PATTERN = r"[^\W_]+"
SENTENCE_SPLIT_PATTERN = r"(?<=[.!?])\s+"
SENTENCE_RULE = (
    "nfc-collapse-whitespace-then-split-after-terminal-period-question-exclamation"
)
# Closed and frozen. Sentence-initial position only, single tokens, lowercase.
ANAPHOR_PRONOUNS = ("it", "this", "that", "these", "those", "they")
SCOPE_BLOCK_RULE = (
    "sentence-unioned-with-its-immediate-predecessor-iff-sentence-initial-anaphor"
)

_TOKEN = re.compile(TOKEN_PATTERN, re.UNICODE)
_SENTENCE = re.compile(SENTENCE_SPLIT_PATTERN)


def normalize(text: str) -> str:
    """NFC normalize and collapse whitespace runs to a single space."""

    return unicodedata.normalize(NORMALIZATION_FORM, " ".join(text.split()))


def tokens(text: str) -> tuple[str, ...]:
    """Case-folded alphanumeric tokens, in order, duplicates preserved."""

    return tuple(token.casefold() for token in _TOKEN.findall(normalize(text)))


def sentences(text: str) -> tuple[str, ...]:
    """Normalized sentences under the declared `SENTENCE_RULE`."""

    normalized = normalize(text)
    if not normalized:
        return ()
    return tuple(part for part in _SENTENCE.split(normalized) if part)


def scope_blocks(text: str) -> tuple[str, ...]:
    """Normalized scope blocks under the declared `SCOPE_BLOCK_RULE`.

    One block per sentence, in sentence order. A block is the sentence itself
    unless the sentence opens with an anaphor, in which case it is the
    immediately preceding sentence followed by the sentence. The predecessor
    contributed is always the raw preceding *sentence*, never that sentence's
    own block, so the relation is not transitive.
    """

    units = sentences(text)
    blocks: list[str] = []
    for index, sentence in enumerate(units):
        leading = tokens(sentence)[:1]
        if index and leading and leading[0] in ANAPHOR_PRONOUNS:
            blocks.append(f"{units[index - 1]} {sentence}")
        else:
            blocks.append(sentence)
    return tuple(blocks)


def contains_token_run(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    """True when `needle` occurs as a contiguous token run inside `haystack`.

    Phrase matching is on token runs rather than raw substrings so that
    `finite subcover` matches the corpus spelling `finite-subcover` while
    `is not` cannot match across the word boundary in `this note`.
    """

    if not needle or len(needle) > len(haystack):
        return False
    first = needle[0]
    span = len(needle)
    for index, token in enumerate(haystack):
        if token == first and haystack[index : index + span] == needle:
            return True
    return False


def cue_pattern(cue: str) -> re.Pattern[str]:
    """Word-boundary-anchored pattern for one normalized cue phrase.

    The `\\b` anchors are load-bearing. Without them a cue such as `is not`
    matches across the word boundary in `this note`, which is how an earlier
    draft of the cue table produced a false positive.
    """

    return re.compile(r"\b" + re.escape(normalize(cue).casefold()) + r"\b")


__all__ = [
    "ANAPHOR_PRONOUNS",
    "NORMALIZATION_FORM",
    "SCOPE_BLOCK_RULE",
    "SENTENCE_RULE",
    "SENTENCE_SPLIT_PATTERN",
    "TOKEN_PATTERN",
    "contains_token_run",
    "cue_pattern",
    "normalize",
    "scope_blocks",
    "sentences",
    "tokens",
]
