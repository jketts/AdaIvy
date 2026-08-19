"""Immutable public value objects for Phase 2 ports and workflow state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain.entities import OpaqueId
from . import PHASE2_SCHEMA_VERSION


class StrEnum(str, Enum):
    pass


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_REVIEW = "awaiting_review"
    UNRESOLVED = "unresolved"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYABLE = "retryable"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ModelResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    REFUSED = "refused"
    INCOMPLETE = "incomplete"
    MALFORMED = "malformed"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactRef:
    schema_version: str = PHASE2_SCHEMA_VERSION
    content_hash: str
    size_bytes: int
    media_type: str


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetLimits:
    schema_version: str = PHASE2_SCHEMA_VERSION
    max_input_tokens: int
    max_output_tokens: int
    max_cost_microusd: int
    max_wall_milliseconds: int
    max_attempts: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetSnapshot:
    schema_version: str = PHASE2_SCHEMA_VERSION
    budget_id: OpaqueId
    limits: BudgetLimits
    used_input_tokens: int
    used_output_tokens: int
    used_cost_microusd: int
    used_attempts: int
    elapsed_milliseconds: int
    exhausted_dimensions: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RunRecord:
    schema_version: str = PHASE2_SCHEMA_VERSION
    run_id: OpaqueId
    dossier_id: OpaqueId
    dossier_hash: str
    budget_id: OpaqueId
    status: RunStatus
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True, kw_only=True)
class JobRecord:
    schema_version: str = PHASE2_SCHEMA_VERSION
    job_id: OpaqueId
    run_id: OpaqueId
    kind: str
    status: JobStatus
    idempotency_key: str
    attempts: int
    max_attempts: int
    deadline_at: str
    lease_owner: str | None
    lease_until: str | None
    payload_hash: str
    result_hash: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelUsage:
    schema_version: str = PHASE2_SCHEMA_VERSION
    input_tokens: int
    output_tokens: int
    total_tokens: int
    usage_source: str
    estimated_cost_microusd: int | None = None
    pricing_snapshot_id: OpaqueId | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelRequest:
    schema_version: str = PHASE2_SCHEMA_VERSION
    request_id: OpaqueId
    run_id: OpaqueId
    purpose: str
    template_id: str
    template_version: str
    template_hash: str
    template_text: str
    serialized_context: str
    response_schema: str
    referenced_entity_ids: tuple[OpaqueId, ...]
    timeout_milliseconds: int
    max_output_tokens: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSchemaPreparation:
    schema_version: str = PHASE2_SCHEMA_VERSION
    provider: str
    canonical_schema_hash: str
    provider_schema_hash: str
    provider_schema_json: str
    transformation_manifest_json: str
    compatibility_report_json: str
    compatibility_report_text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderFailureDiagnostic:
    schema_version: str = PHASE2_SCHEMA_VERSION
    http_status_code: int
    sdk_exception_class: str
    provider_request_id: str | None
    provider_error_type: str | None
    provider_error_code: str | None
    provider_error_param: str | None
    provider_error_message: str | None
    response_content_type: str | None
    response_body_sha256: str
    response_body_byte_length: int
    response_body_preview: str
    response_body_preview_truncated: bool
    diagnostic_text_limit_bytes: int
    adapter_version: str
    sdk_version: str
    model_identifier: str
    endpoint: str
    request_schema_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelResult:
    schema_version: str = PHASE2_SCHEMA_VERSION
    status: ModelResultStatus
    provider: str
    model_identifier: str
    capabilities: tuple[str, ...]
    structured_output: str | None
    declared_rationale: str | None
    refusal: str | None
    usage: ModelUsage
    retry_classification: str
    provider_request_id: str | None = None
    incomplete_reason: str | None = None
    provider_failure: ProviderFailureDiagnostic | None = None
    provider_schema_hash: str | None = None
    projection_manifest_hash: str | None = None
    compatibility_report_hash: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingSnapshot:
    schema_version: str
    snapshot_id: OpaqueId
    provider: str
    model_identifier: str
    source: str
    captured_at: str
    currency: str
    units: str
    input_microusd_per_million_tokens: int
    output_microusd_per_million_tokens: int
    content_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CostEstimate:
    schema_version: str = PHASE2_SCHEMA_VERSION
    estimate_id: OpaqueId
    call_id: OpaqueId
    run_id: OpaqueId
    pricing_snapshot_id: OpaqueId
    input_token_estimate: int
    output_token_estimate: int
    estimated_cost_microusd: int


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifierIndependence:
    schema_version: str = PHASE2_SCHEMA_VERSION
    context_isolated: bool
    separate_model_call: bool
    different_model: bool
    different_provider: bool
    deterministic_checker: bool
    independently_implemented_checker: bool
    formal_kernel: bool

    @property
    def fully_independent(self) -> bool:
        return (
            self.context_isolated
            and self.separate_model_call
            and self.different_model
            and self.different_provider
            and self.independently_implemented_checker
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifierContextManifest:
    schema_version: str = PHASE2_SCHEMA_VERSION
    manifest_id: OpaqueId
    run_id: OpaqueId
    included_entity_ids: tuple[OpaqueId, ...]
    excluded_entity_ids: tuple[OpaqueId, ...]
    policy_version: str
    serialized_context_hash: str
    context_artifact_hash: str
    independence: VerifierIndependence


@dataclass(frozen=True, slots=True, kw_only=True)
class ProposalRecord:
    schema_version: str = PHASE2_SCHEMA_VERSION
    proposal_id: OpaqueId
    run_id: OpaqueId
    proposal_kind: str
    artifact_hash: str
    source_kind: str
    source_id: str
    target_claim_id: OpaqueId | None
    disposition: str = "proposal"


@dataclass(frozen=True, slots=True, kw_only=True)
class BackendResult:
    schema_version: str = PHASE2_SCHEMA_VERSION
    backend_run_id: OpaqueId
    status: str
    exit_status: int | None
    stdout_hash: str
    stderr_hash: str
    environment_hash: str
    package_hash: str | None
    proposal_ids: tuple[OpaqueId, ...]
    blocker: str | None
