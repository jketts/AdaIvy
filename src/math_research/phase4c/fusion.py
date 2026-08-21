"""Score-space fusion of the three Phase 4C signals.

ADR-0031 rejects rank-only combiners, reciprocal rank fusion included, on
evidence rather than preference: the three recall@5 golds sit at rank one
protected by BM25 margins of 4.4 to 13.2 points, and a rank-only combiner
discards those margins entirely. So fusion adds and subtracts BM25 magnitudes.

Orientation. SQLite `bm25()` returns a value where *lower* is more relevant.
Fusion works in a higher-is-better space, `lexical_relevance = -bm25`, so that
"demotion lowers a score" and "a better document scores higher" are the same
direction. The transform is monotone, so BM25 margins are preserved exactly.

    pre_score  = lexical_relevance + alias_points
    fused_score = pre_score - hedge_penalty
    ordering    = fused_score DESC, document_id ASC

The hedge penalty has no magnitude parameter. A fixed constant would be a free
parameter chosen against the corpus, which is the failure ADR-0031 names. The
penalty is instead a closed form over the candidate set,

    penalty = (max(pre_score) - min(pre_score)) + 1.0

applied identically to every demoted candidate. That yields exactly two
properties and no tuning surface: every demoted candidate falls strictly below
every non-demoted candidate, and the relative order *within* the demoted group
is unchanged, because the same penalty is subtracted from each.

Three hard invariants are enforced at runtime, not merely documented:

1. the penalty is non-negative, so the hedge can only lower a fused score;
2. `fused_score <= pre_score` for every candidate;
3. the hedge names no document outside the candidate set, so it can never
   introduce a document the lexical and alias signals did not retrieve.

A violation raises `Phase4CValidationError`. Fusion fails closed rather than
emitting an ordering it cannot justify.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .bounds import Phase4CValidationError
from .ports import AliasExpansion, HedgeVerdict, LexicalCandidate


HEDGE_PENALTY_RULE = "candidate-set-score-span-plus-one-applied-to-every-demoted-hit"


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
    demoted: bool
    self_disclaiming_cues: tuple[str, ...]
    object_level_cues: tuple[str, ...]
    scoped_query_terms: tuple[str, ...]

    def semantic_projection(self) -> dict[str, Any]:
        """Everything except the float scores, which are operational."""

        return {
            "document_id": self.document_id,
            "signals": list(self.signals),
            "alias_entry_ids": list(self.alias_entry_ids),
            "alias_matched_phrases": list(self.alias_matched_phrases),
            "alias_phrase_count": len(self.alias_matched_phrases),
            "demoted": self.demoted,
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

    hits: list[FusedHit] = []
    for document_id in members:
        verdict = verdict_by_id.get(document_id)
        demoted = bool(verdict and verdict.demoted)
        applied = penalty if demoted else 0.0
        pre = pre_scores[document_id]
        fused_score = pre - applied
        if fused_score > pre:
            raise Phase4CValidationError("the hedge raised a fused score")
        signals: list[str] = []
        if document_id in relevance:
            signals.append("lexical")
        if document_id in alias_entries:
            signals.append("alias")
        hits.append(
            FusedHit(
                document_id=document_id,
                signals=tuple(signals),
                lexical_relevance=relevance.get(document_id),
                alias_points=alias_phrase_points * len(alias_phrases.get(document_id, ())),
                alias_entry_ids=tuple(sorted(set(alias_entries.get(document_id, ())))),
                alias_matched_phrases=tuple(alias_phrases.get(document_id, ())),
                pre_score=pre,
                hedge_penalty=applied,
                fused_score=fused_score,
                demoted=demoted,
                self_disclaiming_cues=(
                    verdict.self_disclaiming_cues if verdict else ()
                ),
                object_level_cues=(verdict.object_level_cues if verdict else ()),
                scoped_query_terms=(verdict.scoped_query_terms if verdict else ()),
            )
        )
    return tuple(sorted(hits, key=lambda hit: (-hit.fused_score, hit.document_id)))


__all__ = ["FusedHit", "HEDGE_PENALTY_RULE", "candidate_ids", "fuse"]
