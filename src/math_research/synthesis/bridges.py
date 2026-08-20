"""Bridge-lemma candidates under a finite, local minimality rule.

Contract Section 8. Minimality is local only: a finite mismatch set, a finite
candidate set, and a deterministic comparison rule are recorded, and a candidate
is locally minimal only when no enumerated proper-subset candidate permits the
same valid composition. No global minimality or novelty is ever claimed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Any

from . import COMPARISON_RULE_VERSION
from .records import NoveltyStatus, identifier, text
from .serialization import canonical_hash, stable_id
from .state import MathematicalWarrant, MismatchKind, SynthesisValidationError, ValueEnum, parse_enum


class LiteratureSearchStatus(ValueEnum):
    """Search outcome vocabulary (Section 8).

    There is deliberately no value meaning "novel". Absence from the search
    corpus is `search_incomplete` or `not_found_under_protocol`, and neither
    licenses a novelty claim.
    """

    NOT_RUN = "not_run"
    SEARCH_INCOMPLETE = "search_incomplete"
    NOT_FOUND_UNDER_PROTOCOL = "not_found_under_protocol"
    FOUND_PRIOR_RESULT = "found_prior_result"


@dataclass(frozen=True, slots=True, kw_only=True)
class BridgeLemmaCandidate:
    """One proposed missing claim set. A proposal, never a proved lemma."""

    candidate_id: str
    claims: tuple[str, ...]
    resolves_mismatch: MismatchKind
    connected_result_ids: tuple[str, ...]
    connected_result_digests: tuple[str, ...]
    composition_value: str
    preliminary_evidence: tuple[str, ...]
    attempted_falsifications: tuple[str, ...]
    literature_search_protocol: str
    literature_search_status: LiteratureSearchStatus
    mathematical_warrant: MathematicalWarrant
    obligation_ids: tuple[str, ...]
    novelty_status: NoveltyStatus

    def __post_init__(self) -> None:
        identifier(self.candidate_id, field="candidate_id")
        if not self.claims:
            raise SynthesisValidationError("a bridge candidate must propose at least one claim")
        if len(set(self.claims)) != len(self.claims):
            raise SynthesisValidationError("bridge candidate claims must be distinct")
        if len(self.connected_result_ids) < 2:
            raise SynthesisValidationError("a bridge connects at least two results")
        if len(self.connected_result_ids) != len(self.connected_result_digests):
            raise SynthesisValidationError("each connected result needs its exact version digest")
        text(self.composition_value, field="composition_value")
        text(self.literature_search_protocol, field="literature_search_protocol")
        # Section 8: a candidate is a proposal. It cannot arrive already carrying
        # a proof or formal-verification warrant.
        if self.mathematical_warrant in {
            MathematicalWarrant.PROOF_REVIEWED,
            MathematicalWarrant.FORMALLY_VERIFIED,
        }:
            raise SynthesisValidationError(
                "a bridge candidate is a proposal and cannot carry a proof warrant"
            )
        # Search noncoverage must never become a novelty claim.
        if (
            self.literature_search_status
            in {LiteratureSearchStatus.SEARCH_INCOMPLETE, LiteratureSearchStatus.NOT_FOUND_UNDER_PROTOCOL}
            and self.novelty_status not in {NoveltyStatus.NOT_ASSESSED, NoveltyStatus.SEARCH_INCOMPLETE,
                                           NoveltyStatus.NOT_FOUND_UNDER_PROTOCOL}
        ):
            raise SynthesisValidationError(
                "search noncoverage cannot be recorded as anything stronger than "
                "search_incomplete or not_found_under_protocol"
            )

    @property
    def claim_set(self) -> frozenset[str]:
        return frozenset(self.claims)

    def value(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "claims": list(self.claims),
            "resolves_mismatch": self.resolves_mismatch.value,
            "connected_result_ids": list(self.connected_result_ids),
            "connected_result_digests": list(self.connected_result_digests),
            "composition_value": self.composition_value,
            "preliminary_evidence": list(self.preliminary_evidence),
            "attempted_falsifications": list(self.attempted_falsifications),
            "literature_search_protocol": self.literature_search_protocol,
            "literature_search_status": self.literature_search_status.value,
            "mathematical_warrant": self.mathematical_warrant.value,
            "obligation_ids": list(self.obligation_ids),
            "novelty_status": self.novelty_status.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class MinimalityEvaluation:
    """Complete finite comparison evidence for one minimality decision."""

    evaluation_id: str
    candidate_id: str
    rule_version: str
    named_mismatch: MismatchKind
    locally_minimal: bool
    mismatch_resolved: bool
    evaluated_subsets: tuple[tuple[tuple[str, ...], bool], ...]
    smaller_successful_subsets: tuple[tuple[str, ...], ...]
    premise_audit_passed: bool
    premise_audit_detail: str

    def value(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "candidate_id": self.candidate_id,
            "rule_version": self.rule_version,
            "named_mismatch": self.named_mismatch.value,
            "locally_minimal": self.locally_minimal,
            "mismatch_resolved": self.mismatch_resolved,
            # Every enumerated subset and its outcome, so a smaller successful
            # candidate cannot be omitted from the record.
            "evaluated_subsets": [
                {"claims": list(claims), "permits_composition": permitted}
                for claims, permitted in self.evaluated_subsets
            ],
            "smaller_successful_subsets": [list(item) for item in self.smaller_successful_subsets],
            "premise_audit_passed": self.premise_audit_passed,
            "premise_audit_detail": self.premise_audit_detail,
            "minimality_scope": "local_only",
        }


def audit_premises(candidate: BridgeLemmaCandidate, *, target_conclusion: str) -> tuple[bool, str]:
    """Reject a candidate that merely restates the target (Section 8).

    A bridge that assumes the conclusion it is supposed to enable is circular, so
    restating the target fails the premise audit.
    """
    normalized_target = " ".join(target_conclusion.casefold().split())
    for claim in candidate.claims:
        normalized = " ".join(claim.casefold().split())
        if normalized == normalized_target:
            return False, f"claim {claim!r} restates the target conclusion"
        if normalized_target and normalized_target in normalized:
            return False, f"claim {claim!r} contains the target conclusion"
    return True, "no claim restates the target conclusion"


def evaluate_local_minimality(
    candidate: BridgeLemmaCandidate,
    *,
    target_conclusion: str,
    permits_composition: Callable[[frozenset[str]], bool],
    enumerated_candidates: Sequence[BridgeLemmaCandidate] = (),
) -> MinimalityEvaluation:
    """Decide local minimality by enumerating every proper subset.

    `permits_composition` is the deterministic comparison rule. Every proper
    subset of the candidate's claims is evaluated, plus any separately
    enumerated candidate whose claim set is a proper subset, so a smaller
    successful candidate cannot be silently omitted.
    """
    claims = candidate.claim_set
    if not permits_composition(claims):
        raise SynthesisValidationError(
            "a bridge candidate must itself permit the composition it proposes"
        )

    passed, detail = audit_premises(candidate, target_conclusion=target_conclusion)

    subsets: list[tuple[tuple[str, ...], bool]] = []
    successful: list[tuple[str, ...]] = []
    ordered = tuple(sorted(claims))
    # Enumerate every proper subset, including the empty set: if the composition
    # succeeds with no bridge at all, no bridge was needed.
    for size in range(len(ordered)):
        for combination in combinations(ordered, size):
            subset = frozenset(combination)
            permitted = permits_composition(subset)
            subsets.append((combination, permitted))
            if permitted:
                successful.append(combination)

    # Any separately enumerated candidate that is a proper subset also counts.
    for other in enumerated_candidates:
        if other.candidate_id == candidate.candidate_id:
            continue
        if other.claim_set < claims:
            combination = tuple(sorted(other.claim_set))
            permitted = permits_composition(other.claim_set)
            if (combination, permitted) not in subsets:
                subsets.append((combination, permitted))
            if permitted and combination not in successful:
                successful.append(combination)

    mismatch_resolved = candidate.resolves_mismatch is not None and permits_composition(claims)
    locally_minimal = passed and mismatch_resolved and not successful

    evaluation_id = stable_id(
        "minimality",
        {
            "candidate_id": candidate.candidate_id,
            "claims": ordered,
            "rule_version": COMPARISON_RULE_VERSION,
        },
    )
    return MinimalityEvaluation(
        evaluation_id=evaluation_id,
        candidate_id=candidate.candidate_id,
        rule_version=COMPARISON_RULE_VERSION,
        named_mismatch=candidate.resolves_mismatch,
        locally_minimal=locally_minimal,
        mismatch_resolved=mismatch_resolved,
        evaluated_subsets=tuple(sorted(subsets)),
        smaller_successful_subsets=tuple(sorted(successful)),
        premise_audit_passed=passed,
        premise_audit_detail=detail,
    )


def make_candidate(
    *,
    claims: Iterable[str],
    resolves_mismatch: MismatchKind | str,
    connected: Sequence[tuple[str, str]],
    composition_value: str,
    literature_search_protocol: str,
    literature_search_status: LiteratureSearchStatus | str = LiteratureSearchStatus.NOT_RUN,
    preliminary_evidence: Sequence[str] = (),
    attempted_falsifications: Sequence[str] = (),
    obligation_ids: Sequence[str] = (),
    warrant: MathematicalWarrant | str = MathematicalWarrant.UNASSESSED,
    novelty: NoveltyStatus | str = NoveltyStatus.NOT_ASSESSED,
) -> BridgeLemmaCandidate:
    """Build a candidate with a content-derived identity."""
    ordered = tuple(sorted(set(claims)))
    candidate_id = stable_id("bridge-candidate", {"claims": ordered})
    return BridgeLemmaCandidate(
        candidate_id=candidate_id,
        claims=ordered,
        resolves_mismatch=parse_enum(MismatchKind, resolves_mismatch, field="resolves_mismatch"),
        connected_result_ids=tuple(item[0] for item in connected),
        connected_result_digests=tuple(item[1] for item in connected),
        composition_value=composition_value,
        preliminary_evidence=tuple(preliminary_evidence),
        attempted_falsifications=tuple(attempted_falsifications),
        literature_search_protocol=literature_search_protocol,
        literature_search_status=parse_enum(
            LiteratureSearchStatus, literature_search_status, field="literature_search_status"
        ),
        mathematical_warrant=parse_enum(MathematicalWarrant, warrant, field="mathematical_warrant"),
        obligation_ids=tuple(obligation_ids),
        novelty_status=parse_enum(NoveltyStatus, novelty, field="novelty_status"),
    )


__all__ = [
    "BridgeLemmaCandidate",
    "LiteratureSearchStatus",
    "MinimalityEvaluation",
    "audit_premises",
    "evaluate_local_minimality",
    "make_candidate",
]
