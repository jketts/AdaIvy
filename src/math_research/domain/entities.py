"""Immutable Phase 1 trust entities.

Logical status and confidence are intentionally absent. They are policy
projections over these append-only facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Self

ENTITY_SCHEMA_VERSION = "1.0.0"
ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]*$")


@dataclass(frozen=True, slots=True, order=True)
class OpaqueId:
    value: str

    def __post_init__(self) -> None:
        if not ID_PATTERN.fullmatch(self.value):
            raise ValueError(f"invalid opaque ID: {self.value!r}")

    def __str__(self) -> str:
        return self.value


def oid(value: str) -> OpaqueId:
    return OpaqueId(value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrEnum(str, Enum):
    pass


class ProblemType(StrEnum):
    PROVE = "prove"
    DISPROVE = "disprove"
    OPTIMIZE = "optimize"
    CLASSIFY = "classify"
    COMPUTE = "compute"
    EXPLORE = "explore"


class ApprovalStatus(StrEnum):
    PROPOSED = "proposed"
    NEEDS_CLARIFICATION = "needs_clarification"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class AlignmentStatus(StrEnum):
    PROPOSED = "proposed"
    RESEARCHER_APPROVED = "researcher_approved"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"


class StrengthRelation(StrEnum):
    EQUIVALENT = "equivalent"
    WEAKER = "weaker"
    STRONGER = "stronger"
    OVERLAPPING = "overlapping"
    UNRELATED = "unrelated"
    UNRESOLVED = "unresolved"


class ClaimOrigin(StrEnum):
    USER = "user"
    SOURCE = "source"
    MODEL = "model"
    TOOL = "tool"
    FORMAL_SYSTEM = "formal_system"


class ClaimScope(StrEnum):
    UNRESTRICTED_UNIVERSAL = "unrestricted_universal"
    BOUNDED = "bounded"
    EXISTENTIAL = "existential"
    PARTICULAR = "particular"
    DEFINITIONAL = "definitional"


class WarrantKind(StrEnum):
    FORMAL_PROOF = "formal_proof"
    RIGOROUS_DERIVATION = "rigorous_derivation"
    EXACT_COUNTEREXAMPLE = "exact_counterexample"
    EXPERIMENTAL_OBSERVATION = "experimental_observation"
    SOURCE_REPORT = "source_report"
    MODEL_AGREEMENT = "model_agreement"


class RecordStatus(StrEnum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class Disposition(StrEnum):
    PROPOSAL = "proposal"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class EvidenceKind(StrEnum):
    DERIVATION = "derivation"
    FORMAL_ARTIFACT = "formal_artifact"
    COUNTEREXAMPLE = "counterexample"
    EXPERIMENT = "experiment"
    SOURCE_SPAN = "source_span"
    MODEL_OUTPUT = "model_output"


class ApplicabilityStatus(StrEnum):
    PROPOSED = "proposed"
    CHECKED = "checked"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class Compatibility(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNRESOLVED = "unresolved"


class ObligationStatus(StrEnum):
    OPEN = "open"
    BLOCKED = "blocked"
    DISCHARGED = "discharged"
    WAIVED = "waived"


class RepresentationStatus(StrEnum):
    PROPOSED = "proposed"
    PARTIALLY_VERIFIED = "partially_verified"
    VERIFIED = "verified"
    REFUTED = "refuted"


class VerificationOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class ProtocolPhase(StrEnum):
    EXPLORATORY = "exploratory"
    CONFIRMATORY = "confirmatory"


@dataclass(frozen=True, slots=True, kw_only=True)
class Entity:
    id: OpaqueId
    created_at: datetime
    created_by: OpaqueId
    schema_version: str = ENTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ENTITY_SCHEMA_VERSION:
            raise ValueError(f"unsupported entity schema version: {self.schema_version}")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchProblem(Entity):
    title: str
    informal_statement: str
    problem_type: ProblemType
    tags: tuple[str, ...] = ()
    active_formalization_id: OpaqueId | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Formalization(Entity):
    problem_id: OpaqueId
    version: int
    statement: str
    formal_language: str
    quantifiers: tuple[str, ...]
    assumption_claim_ids: tuple[OpaqueId, ...]
    target_claim_id: OpaqueId
    approval_status: ApprovalStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticAlignmentRecord(Entity):
    problem_id: OpaqueId
    formalization_id: OpaqueId
    compared_claim_id: OpaqueId
    quantifier_mapping: tuple[tuple[str, str], ...]
    definition_mapping: tuple[tuple[str, str], ...]
    assumption_delta: tuple[str, ...]
    edge_case_delta: tuple[str, ...]
    strength_relation: StrengthRelation
    status: AlignmentStatus
    approved_by: OpaqueId | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Claim(Entity):
    kind: str
    statement: str
    assumption_claim_ids: tuple[OpaqueId, ...]
    origin: ClaimOrigin
    scope: ClaimScope
    representation_map_ids: tuple[OpaqueId, ...] = ()
    novelty_assessment_id: OpaqueId | None = None
    significance_assessment_id: OpaqueId | None = None
    contribution_ids: tuple[OpaqueId, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class EpistemicWarrant(Entity):
    claim_id: OpaqueId
    kind: WarrantKind
    scope: str
    evidence_ids: tuple[OpaqueId, ...]
    verification_record_ids: tuple[OpaqueId, ...]
    status: RecordStatus = RecordStatus.ACTIVE


@dataclass(frozen=True, slots=True, kw_only=True)
class Evidence(Entity):
    claim_id: OpaqueId
    kind: EvidenceKind
    content: str
    artifact_hash: str
    source_ref: str | None
    disposition: Disposition


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceApplicabilityRecord(Entity):
    local_claim_id: OpaqueId
    evidence_id: OpaqueId
    imported_statement: str
    imported_hypotheses: tuple[str, ...]
    definition_mapping: tuple[tuple[str, str], ...]
    scope_and_exceptions: tuple[str, ...]
    implication_obligation_id: OpaqueId
    bibliographic_status: str
    hypothesis_compatibility: Compatibility
    implication_verified: bool
    status: ApplicabilityStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class ProofObligation(Entity):
    claim_id: OpaqueId
    description: str
    category: str
    status: ObligationStatus
    normalized_statement: str | None = None
    discharged_by_warrant_id: OpaqueId | None = None
    parent_obligation_id: OpaqueId | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class RepresentationMap(Entity):
    source_representation: str
    target_representation: str
    encoding_claim_id: OpaqueId
    preserved_property_claim_ids: tuple[OpaqueId, ...]
    exceptional_case_claim_ids: tuple[OpaqueId, ...]
    bridge_obligation_ids: tuple[OpaqueId, ...]
    status: RepresentationStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class VerificationRecord(Entity):
    claim_id: OpaqueId
    verifier_kind: str
    outcome: VerificationOutcome
    evidence_ids: tuple[OpaqueId, ...]
    target_statement_hash: str
    independent_from_proposer: bool
    disposition: Disposition
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationProtocol(Entity):
    version: int
    phase: ProtocolPhase
    metrics: tuple[str, ...]
    success_criteria: tuple[str, ...]
    stopping_rules: tuple[str, ...]
    frozen_at: datetime | None = None
    frozen_by: OpaqueId | None = None

    def __post_init__(self) -> None:
        Entity.__post_init__(self)
        if (self.frozen_at is None) != (self.frozen_by is None):
            raise ValueError("frozen_at and frozen_by must be set together")
        if self.phase is ProtocolPhase.CONFIRMATORY and self.frozen_at is None:
            raise ValueError("confirmatory protocols must be frozen")

    @property
    def is_frozen(self) -> bool:
        return self.frozen_at is not None

    def freeze(self, *, actor: OpaqueId, at: datetime) -> Self:
        if self.is_frozen:
            return self
        return replace(self, frozen_at=at, frozen_by=actor)

    def revise(self, **changes: object) -> Self:
        if self.is_frozen:
            raise ValueError("frozen evaluation protocol cannot be revised")
        return replace(self, **changes)


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEvent(Entity):
    aggregate_id: OpaqueId
    event_type: str
    payload: tuple[tuple[str, str], ...]
    idempotency_key: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchDossier(Entity):
    problem: ResearchProblem
    formalization: Formalization
    semantic_alignment: SemanticAlignmentRecord
    claims: tuple[Claim, ...]
    warrants: tuple[EpistemicWarrant, ...]
    evidence: tuple[Evidence, ...]
    source_applicability: tuple[SourceApplicabilityRecord, ...]
    obligations: tuple[ProofObligation, ...]
    representation_maps: tuple[RepresentationMap, ...]
    verification_records: tuple[VerificationRecord, ...]
    evaluation_protocol: EvaluationProtocol
    audit_events: tuple[AuditEvent, ...]
    capabilities: tuple[str, ...] = ()


ALL_ENTITY_TYPES = (
    ResearchProblem,
    Formalization,
    SemanticAlignmentRecord,
    Claim,
    EpistemicWarrant,
    Evidence,
    SourceApplicabilityRecord,
    ProofObligation,
    RepresentationMap,
    VerificationRecord,
    EvaluationProtocol,
    ResearchDossier,
    AuditEvent,
)
