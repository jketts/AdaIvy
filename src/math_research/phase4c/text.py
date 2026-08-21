"""Deterministic text normalization shared by all three Phase 4C signals.

One tokenizer serves every signal so that a "matched query term" means the same
thing to the lexical index, the self-disclaimer rule, and alias phrase
matching.
It mirrors the frozen lexical baseline exactly: Unicode NFC, the token regex
`[^\\W_]+`, and `str.casefold()`.

Sentence splitting is the detection unit of the self-disclaimer signal and is
therefore part of the declared method, not an implementation detail:

1. normalize to NFC and collapse every run of whitespace to a single space;
2. split immediately after a `.`, `!`, or `?` that is followed by whitespace;
3. keep the trailing fragment, so text without terminal punctuation is exactly
   one sentence.

The rule has no abbreviation, decimal, or quotation handling. That is a stated
limitation rather than an oversight: the frozen benchmark corpus contains no
abbreviation, no decimal number, and no quoted period, so adding heuristics
would add untested behaviour. A corpus that needed them would need a new
declared rule and a new report schema version.
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
    "NORMALIZATION_FORM",
    "SENTENCE_RULE",
    "SENTENCE_SPLIT_PATTERN",
    "TOKEN_PATTERN",
    "contains_token_run",
    "cue_pattern",
    "normalize",
    "sentences",
    "tokens",
]
