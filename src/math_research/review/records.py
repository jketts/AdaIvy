"""Immutable value objects for the review decision journal.

Nothing in this module can create a trust record. It carries the DECLARED
content of a review act plus the identity that made it; `projection.py` is the
only place that turns an accepted decision into a Phase 1 entity, and it refuses
to do so unless `decisions.py` has already checked the preconditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..domain.entities import ID_PATTERN, OpaqueId
from . import REFUSAL_SCHEMA_VERSION, SCHEMA_VERSION


class StrEnum(str, Enum):
    pass


class DecisionKind(StrEnum):
    REVIEW_VERDICT = "review_verdict"
    SEMANTIC_ALIGNMENT_DECISION = "semantic_alignment_decision"
    WARRANT_GRANT = "warrant_grant"
    OBLIGATION_DISCHARGE = "obligation_discharge"


class ReviewerKind(StrEnum):
    """Who is making the decision.

    `MODEL` and `AUTOMATED_TOOL` exist so that a decision claiming a non-human
    reviewer is a NAMED refusal rather than an unrepresentable state. No decision
    with either value is ever recorded.
    """

    HUMAN = "human"
    MODEL = "model"
    AUTOMATED_TOOL = "automated_tool"


class ReviewVerdict(StrEnum):
    """A human verdict over one Phase 2 run awaiting review.

    The Phase 2 verifier's `recommendation` is not a member of this enum. A
    recommendation of `manual_review` is an INPUT that is recorded verbatim in
    the decision payload; the verdict itself always arrives from the reviewer.
    """

    ACCEPT_CANDIDATE = "accept_candidate"
    REJECT_CANDIDATE = "reject_candidate"
    INCONCLUSIVE = "inconclusive"


class AlignmentDecision(StrEnum):
    APPROVE = "approve"
    DISPUTE = "dispute"


class WarrantBasis(StrEnum):
    HUMAN_REVIEW = "human_review"
    FORMAL_KERNEL = "formal_kernel"


@dataclass(frozen=True, slots=True, kw_only=True)
class ReviewerIdentity:
    """A named principal taking responsibility for a decision."""

    id: OpaqueId
    kind: ReviewerKind
    attestation: str

    def value(self) -> dict[str, Any]:
        return {"attestation": self.attestation, "id": self.id.value, "kind": self.kind.value}


@dataclass(frozen=True, slots=True, kw_only=True)
class Refusal:
    """A first-class refusal naming exactly one unmet precondition."""

    schema_version: str = REFUSAL_SCHEMA_VERSION
    code: str
    subject_id: str
    unmet_precondition: str
    detail: str

    def value(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
            "unmet_precondition": self.unmet_precondition,
        }


class ReviewRefused(Exception):
    """Raised instead of granting anything. Carries structured refusals."""

    def __init__(self, refusals: tuple[Refusal, ...]) -> None:
        if not refusals:
            raise ValueError("a refusal must name at least one unmet precondition")
        self.refusals = refusals
        super().__init__("; ".join(f"{item.code}: {item.detail}" for item in refusals))

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.refusals)

    def value(self) -> dict[str, Any]:
        return {"accepted": False, "refusals": [item.value() for item in self.refusals]}


def refuse(code: str, *, subject_id: str, unmet_precondition: str, detail: str) -> ReviewRefused:
    return ReviewRefused(
        (
            Refusal(
                code=code,
                subject_id=subject_id,
                unmet_precondition=unmet_precondition,
                detail=detail,
            ),
        )
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class DecisionProposal:
    """A checked decision that has not yet been appended to the journal.

    `decisions.py` returns this; only `journal.py` gives it a sequence and a
    recorded instant. Identity is content-derived, so an identical decision
    replayed in a different process gets the same `decision_id`.
    """

    schema_version: str = SCHEMA_VERSION
    decision_kind: DecisionKind
    subject_id: str
    reviewer: ReviewerIdentity
    idempotency_key: str
    payload: Mapping[str, Any]

    def identity(self) -> dict[str, Any]:
        """Semantic identity. The `operational` payload block is excluded.

        Two decisions that differ only in an observed instant are the SAME
        decision, so they get the same `decision_id`.
        """

        payload = dict(self.payload)
        payload.pop("operational", None)
        return {
            "decision_kind": self.decision_kind.value,
            "idempotency_key": self.idempotency_key,
            "payload": payload,
            "reviewer": self.reviewer.value(),
            "schema_version": self.schema_version,
            "subject_id": self.subject_id,
        }


def require_identifier(value: str, *, field: str) -> OpaqueId:
    if not ID_PATTERN.fullmatch(value):
        raise refuse(
            "identifier_malformed",
            subject_id=value,
            unmet_precondition=f"{field} matches the Phase 1 opaque identifier pattern",
            detail=f"{field} {value!r} is not a valid opaque identifier",
        )
    return OpaqueId(value)


def require_human(reviewer: ReviewerIdentity, *, subject_id: str) -> ReviewerIdentity:
    """No self-granting: only a human principal may record a review decision."""

    if reviewer.kind is not ReviewerKind.HUMAN:
        raise refuse(
            "reviewer_identity_not_human",
            subject_id=subject_id,
            unmet_precondition="the reviewer identity declares kind 'human'",
            detail=(
                f"reviewer {reviewer.id.value} declares kind {reviewer.kind.value!r}; a review "
                "decision must be taken by a named human, so model and tool output stays a proposal"
            ),
        )
    if not reviewer.attestation.strip():
        raise refuse(
            "reviewer_attestation_missing",
            subject_id=subject_id,
            unmet_precondition="the reviewer supplies a non-empty attestation",
            detail=f"reviewer {reviewer.id.value} supplied no attestation text",
        )
    return reviewer
