"""Score-space fusion of the three Phase 4C signals, with suppression.

ADR-0031 rejects rank-only combiners, reciprocal rank fusion included, on
evidence rather than preference: the three recall@5 golds sit at rank one
protected by BM25 margins of 4.4 to 13.2 points, and a rank-only combiner
discards those margins entirely. So fusion adds and subtracts BM25 magnitudes.

Orientation. SQLite `bm25()` returns a value where *lower* is more relevant.
Fusion works in a higher-is-better space, `lexical_relevance = -bm25`, so that
"a penalty lowers a score" and "a better document scores higher" are the same
direction. The transform is monotone, so BM25 margins are preserved exactly.

    pre_score  = lexical_relevance + alias_points
    fused_score = pre_score - hedge_penalty
    ordering    = fused_score DESC, document_id ASC

The hedge penalty has no magnitude parameter. A fixed constant would be a free
parameter chosen against the corpus, which is the failure ADR-0031 names. The
penalty is instead a closed form over the candidate set,

    penalty = (max(pre_score) - min(pre_score)) + 1.0

applied identically to every suppressed candidate. That yields exactly two
properties and no tuning surface: every suppressed candidate falls strictly
below every retained candidate, and the relative order *within* the suppressed
group is unchanged, because the same penalty is subtracted from each.

**ADR-0046: the penalty is no longer the whole response to a verdict.** A
suppressed candidate is *removed* from the retained list, because retrieval
returns a list and precision is measured over what is returned. The penalty is
retained for one reason, and it is a disclosure reason rather than a ranking
one: the penalised ordering is exactly the ordering ADR-0031 returned, so
`ordering()` below is the pre-suppression ordering that the report discloses
side by side with the retained ordering. Removal, not the penalty, is what moves
a metric.

`fuse` therefore returns *every* candidate, in pre-suppression order, each
carrying `suppressed` and its 1-based `pre_suppression_rank`. Nothing is dropped
from the returned tuple: a caller partitions with `retained()` and
`suppressed()`, and the report keeps both. Hiding a suppressed candidate would
be the forbidden outcome "hiding ... an inapplicable hit".

Four hard invariants are enforced at runtime, not merely documented:

1. the penalty is non-negative, so a verdict can only lower a fused score;
2. `fused_score <= pre_score` for every candidate, checked through
   `enforce_no_score_raise`, which the acceptance suite calls directly so the
   guard is demonstrated reachable rather than assumed;
3. the hedge names no document outside the candidate set, so it can never
   introduce a document the lexical and alias signals did not retrieve;
4. `retained()` is an order-preserving subsequence of the full returned tuple,
   which is what makes suppression removal rather than promotion. Removal
   preserves order by construction here, and `enforce_subsequence` checks it.

A violation raises `Phase4CValidationError`. Fusion fails closed rather than
emitting an ordering it cannot justify.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .bounds import Phase4CValidationError
from .ports import AliasExpansion, HedgeVerdict, LexicalCandidate


HEDGE_PENALTY_RULE = "candidate-set-score-span-plus-one-applied-to-every-suppressed-hit"
SUPPRESSION_RULE = "remove-every-suppressed-candidate-from-the-retained-ordering"


def enforce_no_score_raise(
    document_id: str, pre_score: float, fused_score: float
) -> None:
    """Invariant 2. A verdict may lower a fused score and may never raise one.

    Extracted so the acceptance suite can call it with a raised score and show
    the rejection, instead of relying on the happy path being monotone.
    """

    if fused_score > pre_score:
        raise Phase4CValidationError(
            f"the hedge raised the fused score of {document_id!r}: "
            f"{fused_score} > {pre_score}"
        )


def enforce_subsequence(
    retained_ids: Sequence[str], pre_suppression_ids: Sequence[str]
) -> None:
    """Invariant 4. Suppression removes; it never reorders and never promotes.

    `retained_ids` must appear inside `pre_suppression_ids` in the same relative
    order, with no element moved past another and no element introduced. A set
    comparison would accept a promotion, so this is an explicit walk.
    """

    position = 0
    for identifier in retained_ids:
        while position < len(pre_suppression_ids) and (
            pre_suppression_ids[position] != identifier
        ):
            position += 1
        if position == len(pre_suppression_ids):
            raise Phase4CValidationError(
                "suppression promoted or reordered a candidate: "
                f"{identifier!r} is not in order inside the pre-suppression ordering"
            )
        position += 1


@dataclass(frozen=True)
class FusedHit:
    document_id: str
    signals: tuple[str, ...]
    lexical_relevance: float | None
    alias_points: float
    alias_entry_ids: tuple[str, ...]
    alias_matched_phrases: tuple[str, ...]
    pre_score: float
    hedge_penalty: float
    fused_score: float
    pre_suppression_rank: int
    suppressed: bool
    self_disclaiming_cues: tuple[str, ...]
    object_level_cues: tuple[str, ...]
    scoped_query_terms: tuple[str, ...]

    def semantic_projection(self) -> dict[str, Any]:
        """Everything except the float scores, which are operational.

        `pre_suppression_rank` is semantic: it is an integer position in a
        deterministic ordering, and it is what lets a reader of the report see
        where a suppressed document stood before it was removed.
        """

        return {
            "document_id": self.document_id,
            "signals": list(self.signals),
            "alias_entry_ids": list(self.alias_entry_ids),
            "alias_matched_phrases": list(self.alias_matched_phrases),
            "alias_phrase_count": len(self.alias_matched_phrases),
            "pre_suppression_rank": self.pre_suppression_rank,
            "suppressed": self.suppressed,
            "self_disclaiming_cues": list(self.self_disclaiming_cues),
            "object_level_cues": list(self.object_level_cues),
            "scoped_query_terms": list(self.scoped_query_terms),
        }

    def operational_projection(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "lexical_relevance": (
                None if self.lexical_relevance is None else round(self.lexical_relevance, 6)
            ),
            "alias_points": round(self.alias_points, 6),
            "pre_score": round(self.pre_score, 6),
            "hedge_penalty": round(self.hedge_penalty, 6),
            "fused_score": round(self.fused_score, 6),
        }


def candidate_ids(
    lexical: Sequence[LexicalCandidate], expansions: Sequence[AliasExpansion]
) -> tuple[str, ...]:
    """The pre-hedge candidate set: lexical hits plus alias-introduced hits."""

    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in lexical:
        if candidate.document_id not in seen:
            ordered.append(candidate.document_id)
            seen.add(candidate.document_id)
    for expansion in expansions:
        for document_id, _phrases in expansion.matched:
            if document_id not in seen:
                ordered.append(document_id)
                seen.add(document_id)
    return tuple(ordered)


def retained(hits: Sequence[FusedHit]) -> tuple[FusedHit, ...]:
    """The hits a query returns: every candidate that was not suppressed."""

    return tuple(hit for hit in hits if not hit.suppressed)


def suppressed(hits: Sequence[FusedHit]) -> tuple[FusedHit, ...]:
    """The removed candidates. They stay in the report; only the list drops them."""

    return tuple(hit for hit in hits if hit.suppressed)


def fuse(
    lexical: Sequence[LexicalCandidate],
    expansions: Sequence[AliasExpansion],
    verdicts: Sequence[HedgeVerdict],
    *,
    alias_phrase_points: float,
) -> tuple[FusedHit, ...]:
    if alias_phrase_points <= 0:
        raise Phase4CValidationError("alias phrase points must be strictly positive")

    relevance: dict[str, float] = {}
    for candidate in lexical:
        if candidate.document_id in relevance:
            raise Phase4CValidationError(
                f"duplicate lexical candidate {candidate.document_id!r}"
            )
        relevance[candidate.document_id] = -candidate.bm25

    alias_entries: dict[str, list[str]] = {}
    alias_phrases: dict[str, list[str]] = {}
    for expansion in expansions:
        for document_id, phrases in expansion.matched:
            alias_entries.setdefault(document_id, []).append(expansion.entry_id)
            for phrase in phrases:
                bucket = alias_phrases.setdefault(document_id, [])
                if phrase not in bucket:
                    bucket.append(phrase)

    members = candidate_ids(lexical, expansions)
    member_set = set(members)

    verdict_by_id: dict[str, HedgeVerdict] = {}
    for verdict in verdicts:
        if verdict.document_id in verdict_by_id:
            raise Phase4CValidationError(
                f"duplicate hedge verdict for {verdict.document_id!r}"
            )
        if verdict.document_id not in member_set:
            # Invariant 3: the hedge may never introduce a document.
            raise Phase4CValidationError(
                "hedge verdict names a document outside the candidate set: "
                f"{verdict.document_id!r}"
            )
        verdict_by_id[verdict.document_id] = verdict

    pre_scores = {
        document_id: relevance.get(document_id, 0.0)
        + alias_phrase_points * len(alias_phrases.get(document_id, ()))
        for document_id in members
    }
    if pre_scores:
        span = max(pre_scores.values()) - min(pre_scores.values())
        penalty = span + 1.0
    else:
        penalty = 0.0
    if penalty < 0.0:
        raise Phase4CValidationError("hedge penalty must be non-negative")

    unranked: list[tuple[float, str, dict[str, Any]]] = []
    for document_id in members:
        verdict = verdict_by_id.get(document_id)
        is_suppressed = bool(verdict and verdict.suppressed)
        applied = penalty if is_suppressed else 0.0
        pre = pre_scores[document_id]
        fused_score = pre - applied
        enforce_no_score_raise(document_id, pre, fused_score)
        signals: list[str] = []
        if document_id in relevance:
            signals.append("lexical")
        if document_id in alias_entries:
            signals.append("alias")
        unranked.append(
            (
                fused_score,
                document_id,
                {
                    "document_id": document_id,
                    "signals": tuple(signals),
                    "lexical_relevance": relevance.get(document_id),
                    "alias_points": (
                        alias_phrase_points * len(alias_phrases.get(document_id, ()))
                    ),
                    "alias_entry_ids": tuple(
                        sorted(set(alias_entries.get(document_id, ())))
                    ),
                    "alias_matched_phrases": tuple(alias_phrases.get(document_id, ())),
                    "pre_score": pre,
                    "hedge_penalty": applied,
                    "fused_score": fused_score,
                    "suppressed": is_suppressed,
                    "self_disclaiming_cues": (
                        verdict.self_disclaiming_cues if verdict else ()
                    ),
                    "object_level_cues": (verdict.object_level_cues if verdict else ()),
                    "scoped_query_terms": (
                        verdict.scoped_query_terms if verdict else ()
                    ),
                },
            )
        )

    unranked.sort(key=lambda item: (-item[0], item[1]))
    hits = tuple(
        FusedHit(pre_suppression_rank=rank, **fields)
        for rank, (_score, _identifier, fields) in enumerate(unranked, start=1)
    )
    enforce_subsequence(
        [hit.document_id for hit in retained(hits)],
        [hit.document_id for hit in hits],
    )
    return hits


__all__ = [
    "FusedHit",
    "HEDGE_PENALTY_RULE",
    "SUPPRESSION_RULE",
    "candidate_ids",
    "enforce_no_score_raise",
    "enforce_subsequence",
    "fuse",
    "retained",
    "suppressed",
]
