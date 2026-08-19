"""Immutable values for the bounded formal-checking adapter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..domain.entities import OpaqueId
from . import SCHEMA_VERSION


class SourceKind(str, Enum):
    OPERATOR = "operator"
    MODEL = "model"
    EXTERNAL = "external"


class FormalCheckOutcome(str, Enum):
    KERNEL_CHECKED = "kernel_checked"
    KERNEL_CHECKED_APPROVED_AXIOMS = "kernel_checked_approved_standard_axioms"
    KERNEL_CHECKED_UNAPPROVED_ASSUMPTIONS = "kernel_checked_unapproved_assumptions"
    POLICY_REJECTION = "policy_rejection"
    ELABORATION_FAILURE = "elaboration_failure"
    MEANING_TEST_FAILURE = "meaning_test_failure"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit"
    SANDBOX_FAILURE = "sandbox_failure"


@dataclass(frozen=True, slots=True)
class DeclaredAssumption:
    name: str
    type_expression: str


@dataclass(frozen=True, slots=True)
class MeaningTest:
    test_id: str
    statement: str
    proof_fragment: str


@dataclass(frozen=True, slots=True)
class FormalCheckRequest:
    request_id: OpaqueId
    claim_id: OpaqueId
    semantic_alignment_id: OpaqueId | None
    source_kind: SourceKind
    declaration_name: str
    imports: tuple[str, ...]
    assumptions: tuple[DeclaredAssumption, ...]
    target_statement: str
    proof_fragment: str
    meaning_tests: tuple[MeaningTest, ...]
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class PolicyRejection:
    code: str
    field: str
    detail: str


@dataclass(frozen=True, slots=True)
class WrapperManifest:
    source_hash: str
    target_hash: str
    proof_fragment_hash: str
    declaration_hash: str
    import_manifest_hash: str
    wrapper_hash: str
    invocation_hash: str
    policy_hash: str
    runtime_hash: str
    wrapper_byte_length: int
    target_line: int
    meaning_test_start_line: int | None
    schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class GeneratedWrapper:
    source: bytes
    manifest: WrapperManifest


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    wall_milliseconds: int = 20_000
    combined_output_bytes: int = 65_536
    retained_stdout_bytes: int = 8_192
    retained_stderr_bytes: int = 8_192


@dataclass(frozen=True, slots=True)
class StreamCapture:
    byte_length: int
    content_hash: str
    retained_utf8: str
    retained_byte_length: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class RawExecution:
    exit_code: int | None
    termination_reason: str
    elapsed_milliseconds: int
    stdout: StreamCapture
    stderr: StreamCapture
    container_removed: bool
    adapter_diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormalCheckFinding:
    id: OpaqueId
    request_id: OpaqueId
    claim_id: OpaqueId
    semantic_alignment_id: OpaqueId | None
    source_kind: SourceKind
    outcome: FormalCheckOutcome
    disposition: str
    trust_effect: str
    exact_statement_only: bool
    approved_axioms: tuple[str, ...]
    unapproved_assumptions: tuple[str, ...]
    policy_rejections: tuple[PolicyRejection, ...]
    wrapper_manifest: WrapperManifest | None
    execution: RawExecution | None
    meaning_tests_diagnostic_only: bool
    semantic_alignment_approved: bool
    source_applicability_approved: bool
    novelty_approved: bool
    significance_approved: bool
    contribution_approved: bool
    epistemic_warrant_created: bool
    created_at: str
    content_hash: str
    schema_version: str = SCHEMA_VERSION

