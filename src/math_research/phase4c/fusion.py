"""Score-space fusion of the four Phase 4C signals.

ADR-0031 rejects rank-only combiners, reciprocal rank fusion included, on
evidence rather than preference: the three recall@5 golds sit at rank one
protected by BM25 margins of 4.4 to 13.2 points, and a rank-only combiner
discards those margins entirely. So fusion adds BM25 magnitudes.

Orientation. SQLite `bm25()` returns a value where *lower* is more relevant.
Fusion works in a higher-is-better space, `lexical_relevance = -bm25`, so that
"a better document scores higher" is the only direction. The transform is
monotone, so BM25 margins are preserved exactly.

    fused_score = lexical_relevance + alias_points + semantic_points
    ordering    = fused_score DESC, document_id ASC

ADR-0070 adds `semantic_points = semantic_tier_points * tier_credit`, in the same
additive position as `alias_phrase_points * phrase_count`. The credit is a
function of the semantic signal's exact-cosine RANK and is re-derived here from
`bounds.semantic_tier_credit`, so a signal cannot assert a magnitude of its own:
the most any document can gain is three points, which is below ADR-0031's
smallest measured BM25 gold margin of 4.4. The semantic signal may therefore
introduce a document the lexical signal missed entirely and cannot on its own
invert a lexical gold ordering.

There is no penalty term. ADR-0032 replaces ADR-0031's demotion with exclusion,
and an excluded document is not a lower-scoring candidate -- it is not a
candidate. The ADR-0031 penalty had a closed form rather than a tuned constant,
but with exclusion it can no longer change any outcome, and a term that changes
no outcome is dead complexity, so `HEDGE_PENALTY_RULE` and the penalty are gone
rather than retained at zero.

Three hard invariants from ADR-0032 are enforced at runtime, not merely
documented:

1. exclusion never changes any document's score: `fused_score == pre_score` for
   every hit, excluded or not;
2. exclusion preserves the relative order of every retained document: the
   retained subsequence of the fused ordering equals the fused ordering
   restricted to the retained ids;
3. the disclaimer signal names no document outside the candidate set, so it can
   never introduce a document the lexical and alias signals did not retrieve.

Invariant 2 is deliberately weaker than ADR-0031's "never promotes". A retained
document *can* enter the top-k because something above it left. That is the
point of exclusion, and it is why the duplicate gate is re-measured against the
measured value rather than argued from the invariant.

A violation raises `Phase4CValidationError`. Fusion fails closed rather than
emitting an ordering it cannot justify.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .bounds import BOUNDS, Phase4CValidationError, semantic_tier_credit
from .ports import (
    AliasExpansion,
    DisclaimerVerdict,
    LexicalCandidate,
    SemanticCredit,
)


@dataclass(frozen=True)
class FusedHit:
    document_id: str
    signals: tuple[str, ...]
    lexical_relevance: float | None
    alias_points: float
    alias_entry_ids: tuple[str, ...]
    alias_matched_phrases: tuple[str, ...]
    semantic_points: float
    semantic_rank: int | None
    semantic_tier_credit: int
    cosine_dot: int | None
    cosine_norm_squared_product: int | None
    pre_score: float
    fused_score: float
    excluded: bool
    absence_operators: tuple[str, ...]
    evidence_nouns: tuple[str, ...]
    object_level_cues: tuple[str, ...]
    matched_query_terms: tuple[str, ...]

    def semantic_projection(self) -> dict[str, Any]:
        """Everything except the float scores, which are operational."""

        return {
            "document_id": self.document_id,
            "signals": list(self.signals),
            "alias_entry_ids": list(self.alias_entry_ids),
            "alias_matched_phrases": list(self.alias_matched_phrases),
            "alias_phrase_count": len(self.alias_matched_phrases),
            "semantic_rank": self.semantic_rank,
            "semantic_tier_credit": self.semantic_tier_credit,
            # The ADR-0065 exact cosine terms, carried and never divided: the
            # quotient is irrational in general. A reader rechecks the ranking
            # by cross-multiplying these integers.
            "cosine_dot": self.cosine_dot,
            "cosine_norm_squared_product": self.cosine_norm_squared_product,
            "excluded": self.excluded,
            "absence_operators": list(self.absence_operators),
            "evidence_nouns": list(self.evidence_nouns),
            "object_level_cues": list(self.object_level_cues),
            "matched_query_terms": list(self.matched_query_terms),
        }

    def operational_projection(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "lexical_relevance": (
                None if self.lexical_relevance is None else round(self.lexical_relevance, 6)
            ),
            "alias_points": round(self.alias_points, 6),
            "semantic_points": round(self.semantic_points, 6),
            "pre_score": round(self.pre_score, 6),
            "fused_score": round(self.fused_score, 6),
        }


def candidate_ids(
    lexical: Sequence[LexicalCandidate],
    expansions: Sequence[AliasExpansion],
    credits: Sequence[SemanticCredit] = (),
) -> tuple[str, ...]:
    """The candidate set: lexical hits, alias hits, then semantic hits.

    Three of the four signals may introduce a document. The disclaimer signal
    may not, and `fuse` refuses a verdict naming anything outside this set.
    """

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
    for credit in credits:
        if credit.document_id not in seen:
            ordered.append(credit.document_id)
            seen.add(credit.document_id)
    return tuple(ordered)


def _tier_credit_of(
    semantic_by_id: dict[str, SemanticCredit], document_id: str
) -> int:
    credit = semantic_by_id.get(document_id)
    return 0 if credit is None else credit.tier_credit


def retained_ids(hits: Sequence[FusedHit]) -> tuple[str, ...]:
    """The fused ordering with every excluded hit removed. Order preserved."""

    return tuple(hit.document_id for hit in hits if not hit.excluded)


def fuse(
    lexical: Sequence[LexicalCandidate],
    expansions: Sequence[AliasExpansion],
    verdicts: Sequence[DisclaimerVerdict],
    *,
    credits: Sequence[SemanticCredit] = (),
    alias_phrase_points: float,
    semantic_tier_points: int = BOUNDS.semantic_tier_points,
) -> tuple[FusedHit, ...]:
    if alias_phrase_points <= 0:
        raise Phase4CValidationError("alias phrase points must be strictly positive")
    if isinstance(semantic_tier_points, bool) or not isinstance(
        semantic_tier_points, int
    ):
        raise Phase4CValidationError("semantic tier points must be an integer")
    if semantic_tier_points <= 0:
        raise Phase4CValidationError("semantic tier points must be strictly positive")
    # The semantic signal may introduce a document, so it is subject to the
    # candidate bound and the bound is enforced HERE rather than trusted to the
    # signal, mirroring `LexicalIndex.candidates`.
    if len(credits) > BOUNDS.max_candidates_per_signal:
        raise Phase4CValidationError(
            f"semantic candidate bound exceeded: {len(credits)} > "
            f"{BOUNDS.max_candidates_per_signal}"
        )

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

    semantic_by_id: dict[str, SemanticCredit] = {}
    for credit in credits:
        if credit.document_id in semantic_by_id:
            raise Phase4CValidationError(
                f"duplicate semantic credit for {credit.document_id!r}"
            )
        # The credit is DERIVED from the rank here, not accepted from the
        # signal. A signal that claims a tier its rank does not earn is refused
        # rather than scored, so the bounded contribution is structural.
        expected = semantic_tier_credit(credit.rank)
        if credit.tier_credit != expected:
            raise Phase4CValidationError(
                f"semantic credit for {credit.document_id!r} claims "
                f"{credit.tier_credit} points at rank {credit.rank}; the frozen "
                f"tiers award {expected}"
            )
        semantic_by_id[credit.document_id] = credit

    members = candidate_ids(lexical, expansions, credits)
    member_set = set(members)

    verdict_by_id: dict[str, DisclaimerVerdict] = {}
    for verdict in verdicts:
        if verdict.document_id in verdict_by_id:
            raise Phase4CValidationError(
                f"duplicate disclaimer verdict for {verdict.document_id!r}"
            )
        if verdict.document_id not in member_set:
            # Invariant 3: the signal may never introduce a document.
            raise Phase4CValidationError(
                "disclaimer verdict names a document outside the candidate set: "
                f"{verdict.document_id!r}"
            )
        verdict_by_id[verdict.document_id] = verdict

    pre_scores = {
        document_id: relevance.get(document_id, 0.0)
        + alias_phrase_points * len(alias_phrases.get(document_id, ()))
        + semantic_tier_points * _tier_credit_of(semantic_by_id, document_id)
        for document_id in members
    }

    hits: list[FusedHit] = []
    for document_id in members:
        verdict = verdict_by_id.get(document_id)
        excluded = bool(verdict and verdict.excluded)
        pre = pre_scores[document_id]
        # Invariant 1: the exclusion verdict contributes no term at all. The
        # fused score IS the pre-score; it is asserted over the whole ordering
        # below rather than assumed from this line.
        fused_score = pre
        signals: list[str] = []
        if document_id in relevance:
            signals.append("lexical")
        if document_id in alias_entries:
            signals.append("alias")
        credit = semantic_by_id.get(document_id)
        if credit is not None:
            signals.append("semantic")
        hits.append(
            FusedHit(
                document_id=document_id,
                signals=tuple(signals),
                lexical_relevance=relevance.get(document_id),
                alias_points=alias_phrase_points * len(alias_phrases.get(document_id, ())),
                alias_entry_ids=tuple(sorted(set(alias_entries.get(document_id, ())))),
                alias_matched_phrases=tuple(alias_phrases.get(document_id, ())),
                semantic_points=(
                    semantic_tier_points * credit.tier_credit if credit else 0
                ),
                semantic_rank=(credit.rank if credit else None),
                semantic_tier_credit=(credit.tier_credit if credit else 0),
                cosine_dot=(credit.cosine_dot if credit else None),
                cosine_norm_squared_product=(
                    credit.cosine_norm_squared_product if credit else None
                ),
                pre_score=pre,
                fused_score=fused_score,
                excluded=excluded,
                absence_operators=(verdict.absence_operators if verdict else ()),
                evidence_nouns=(verdict.evidence_nouns if verdict else ()),
                object_level_cues=(verdict.object_level_cues if verdict else ()),
                matched_query_terms=(verdict.matched_query_terms if verdict else ()),
            )
        )
    ordered = tuple(sorted(hits, key=lambda hit: (-hit.fused_score, hit.document_id)))

    # Invariant 1, over the whole ordering: no hit's fused score differs from
    # the score the lexical and alias signals produced for it.
    for hit in ordered:
        if hit.fused_score != pre_scores[hit.document_id]:
            raise Phase4CValidationError(
                f"exclusion changed the score of {hit.document_id!r}"
            )

    # Invariant 2: the retained subsequence of the fused ordering equals the
    # ordering of the retained ids computed independently from the untouched
    # pre-scores. Recomputed from `members` and `pre_scores` rather than read
    # back off `ordered`, so a future change that reorders on exclusion trips
    # this rather than satisfying it by construction.
    excluded_members = {
        document_id
        for document_id in members
        if verdict_by_id.get(document_id) is not None
        and verdict_by_id[document_id].excluded
    }
    # The declared ordering applies to the WHOLE candidate list: exclusion does
    # not group excluded hits anywhere, it only marks them. Checked before the
    # retained subsequence, because a grouping change would satisfy the weaker
    # retained-order check while contradicting the declared method.
    full_order = tuple(
        sorted(members, key=lambda document_id: (-pre_scores[document_id], document_id))
    )
    if tuple(hit.document_id for hit in ordered) != full_order:
        raise Phase4CValidationError(
            "the fused ordering is not fused_score DESC, document_id ASC"
        )
    retained = retained_ids(ordered)
    independent = tuple(
        sorted(
            (
                document_id
                for document_id in members
                if document_id not in excluded_members
            ),
            key=lambda document_id: (-pre_scores[document_id], document_id),
        )
    )
    if retained != independent:
        raise Phase4CValidationError(
            "exclusion changed the relative order of the retained documents"
        )
    if set(retained) | excluded_members != member_set:
        raise Phase4CValidationError(
            "the retained and excluded hits do not partition the candidate set"
        )
    return ordered


__all__ = ["FusedHit", "candidate_ids", "fuse", "retained_ids"]
