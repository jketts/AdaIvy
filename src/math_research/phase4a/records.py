"""Immutable Phase 4A records and closed vocabularies."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from . import SCHEMA_VERSION


class ValueEnum(str, Enum):
    pass


class ActorKind(ValueEnum):
    HUMAN = "human"
    AUTOMATION = "automation"
    MODEL = "model"
    SYSTEM = "system"


class Authority(ValueEnum):
    SOURCE_PROVENANCE = "source_provenance"
    HUMAN_FINAL = "human_final"
    PROPOSAL = "proposal"
    DETERMINISTIC_POLICY = "deterministic_policy"


class RightsUse(ValueEnum):
    ACQUISITION = "acquisition"
    STORAGE_AND_RETENTION = "storage_and_retention"
    PARSING = "parsing"
    EXCERPTING = "excerpting"
    EMBEDDING = "embedding"
    MODEL_CONTEXT = "model_context"
    REDISTRIBUTION = "redistribution"
    PUBLICATION = "publication"


class DisclosureKind(ValueEnum):
    """Where disclosed source text goes (ADR-0064).

    Recorded, never inferred: a local model still crosses a process boundary
    and still needs its own decision.
    """

    TEXT_LEAVES_PROCESS = "text_leaves_process"
    TEXT_STAYS_LOCAL = "text_stays_local"


# ADR-0064. The only two uses that disclose source text to a named processor.
# Every other use must carry `processor: null`; a processor named there would be
# decoration that later reads as an authorization.
DISCLOSING_RIGHTS_USES = frozenset({RightsUse.EMBEDDING, RightsUse.MODEL_CONTEXT})

# The two refusal codes ADR-0064 fixes verbatim. Defined once so the validator,
# the service, and the probe suite cannot drift apart.
PROCESSOR_REQUIRED_REFUSAL = "embedding_use_requires_processor"
PROCESSOR_FORBIDDEN_REFUSAL = "non_disclosing_use_forbids_processor"


class RightsValue(ValueEnum):
    ALLOWED = "allowed"
    PROHIBITED = "prohibited"
    UNRESOLVED = "unresolved"


class RightsReason(ValueEnum):
    PERMITTED = "permitted"
    EXPLICITLY_PROHIBITED = "explicitly_prohibited"
    UNKNOWN_RIGHTS = "unknown_rights"
    RIGHTS_EXPIRED = "rights_expired"
    RIGHTS_REVOKED = "rights_revoked"
    RIGHTS_USE_INCOMPATIBLE = "rights_use_incompatible"
    RIGHTS_CORRECTED = "rights_corrected"


class RightsOutcome(ValueEnum):
    PERMITTED = "permitted"
    EXPLICITLY_PROHIBITED = "explicitly_prohibited"
    MISSING_OR_UNKNOWN = "missing_or_unknown"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REQUESTED_USE_INCOMPATIBLE = "requested_use_incompatible"
    PROCESSOR_NOT_AUTHORIZED = "processor_not_authorized"


class LifecycleType(ValueEnum):
    CORRECTION = "correction"
    REVOCATION = "revocation"
    TAKEDOWN = "takedown"
    SUPPRESSION = "suppression"
    RESTORE = "restore"
    LEGAL_HOLD = "legal_hold"
    DELETION_REQUEST = "deletion_request"
    DELETION_COMPLETION = "deletion_completion"


class ApplicabilityStatus(ValueEnum):
    PROPOSED = "proposed"
    CHECKED = "checked"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class ApplicabilityOutcome(ValueEnum):
    APPLICABLE = "applicable"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class ApplicabilityReason(ValueEnum):
    APPLICABLE = "applicable"
    INCOMPATIBLE_HYPOTHESES = "incompatible_hypotheses"
    DEFINITION_MISMATCH = "definition_mismatch"
    SCOPE_OR_EXCEPTION = "scope_or_exception"
    MISQUOTATION = "misquotation"
    CONTRADICTION = "contradiction"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    RIGHTS_BLOCKED = "rights_blocked"
    SOURCE_WITHDRAWN = "source_withdrawn"
    MALICIOUS_CONTENT = "malicious_content"


class RecordType(ValueEnum):
    POLICY_SNAPSHOT = "phase4_policy_snapshot"
    SOURCE_PROVENANCE = "source_provenance"
    RIGHTS_DECISION = "source_rights_decision"
    LIFECYCLE_ACTION = "source_lifecycle_action"
    EVIDENCE_CARD = "evidence_card"
    APPLICABILITY_REVIEW = "applicability_review"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditRecord:
    id: str
    record_type: RecordType
    subject_id: str
    sequence: int
    actor_id: str
    actor_kind: ActorKind
    authority: Authority
    reason_code: str
    reason_detail: str
    evidence_refs: tuple[str, ...]
    recorded_at: str
    policy_snapshot_id: str
    predecessor_id: str | None
    supersedes: str | None
    payload: dict[str, Any]
    content_hash: str
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True, slots=True, kw_only=True)
class Processor:
    """The named recipient of disclosed source text (ADR-0064).

    One decision authorizes one processor.  There is no wildcard, no `any`, and
    no fallback: a second provider is a second decision, never an inherited one.
    """

    processor_id: str
    provider: str
    model_identifier: str
    disclosure_kind: DisclosureKind

    def as_payload(self) -> dict[str, str]:
        return {
            "processor_id": self.processor_id,
            "provider": self.provider,
            "model_identifier": self.model_identifier,
            "disclosure_kind": DisclosureKind(self.disclosure_kind).value,
        }


@dataclass(frozen=True, slots=True)
class RightsEvaluation:
    source_id: str
    intended_use: RightsUse
    outcome: RightsOutcome
    allowed: bool
    decision_id: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class VerifiedSnapshot:
    """Detached verified bytes; callers receive a new object on every decode."""

    canonical_bytes: bytes
    content_hash: str
    operational_hash: str

    def value(self) -> dict[str, Any]:
        import json

        value = json.loads(self.canonical_bytes)
        assert isinstance(value, dict)
        return value
