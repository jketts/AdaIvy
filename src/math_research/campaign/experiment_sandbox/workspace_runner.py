"""Campaign port for the activated ADR-0082 v2 workspace sandbox.

Differences from the v1 :mod:`.runner`, and only these:

* **Schema-class target binding.**  The activation names a target schema
  class; :meth:`ActivatedWorkspaceCampaignRunner.admit_target` admits ANY
  target validating exactly against that class, instead of refusing every
  target hash but one fixture's.
* **Repeated runs over one persistent workspace.**  Each ``__call__`` runs
  against the same campaign-scoped workspace directory, and every run boundary
  appends a content-hashed workspace run record (manifest before/after, delta,
  determinism flags) to :attr:`run_records` -- append-only provenance for the
  ledger, never trust.
* **Failure as data.**  A ``program_failed`` execution returns a FAILED
  :class:`ExperimentResult` whose result bytes are the structured, hashed
  failure diagnostics.  The caller layer (slice 11's runner) decides whether
  to continue; nothing here is terminal.
* **Determinism surfacing.**  When the configured replica count is 1 the run
  record and the adapter configuration both carry ``determinism_unverified``,
  which downstream verifiers and reports must surface.

What did NOT change: proposals are not trust.  A completed run's result is an
untrusted candidate for the host-side exact verifier, exactly as in v1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..records import RecordStatus, UsageSource, canonical_bytes, canonical_hash
from ..runner import ExperimentRequest, ExperimentResult
from .ports import WorkspaceSandboxPort
from .sandbox import SandboxError, SandboxProgramRequest
from .target_schema import TargetSchemaClass
from .verifier import ExperimentTarget
from .workspace_activation import WorkspaceActivation
from .workspace_sandbox import (
    MAX_PROCESSES_V2,
    WorkspaceExecution,
    WorkspaceSandboxLimits,
)

WORKSPACE_ADAPTER_ID = "campaign_workspace_exact_python"
WORKSPACE_ADAPTER_VERSION = "2.0.0"
WORKSPACE_REFUSAL_SCHEMA = "adaivy.campaign-workspace-refusal.v1"


class WorkspaceRunnerError(ValueError):
    """A production request is incompatible with the activated v2 sandbox."""


def _refusal_payload(code: str, detail: str) -> bytes:
    value: dict[str, Any] = {
        "detail": detail,
        "epistemic_warrant_created": False,
        "refusal_code": code,
        "schema_version": WORKSPACE_REFUSAL_SCHEMA,
        "status": "refused",
    }
    value["content_hash"] = canonical_hash(value)
    return canonical_bytes(value)


def limits_from_request_v2(
    request: ExperimentRequest, *, determinism_replicas: int = 2,
    max_workspace_bytes: int = 268_435_456, max_workspace_inodes: int = 4_096,
) -> WorkspaceSandboxLimits:
    """Translate campaign bounds without rounding any model-chosen bound up.

    The v2 structural ceilings admit operator-budgeted long computation (up to
    ``MAX_CPU_SECONDS_V2`` = 3600 s CPU and ``MAX_WALL_SECONDS_V2`` = 4500 s
    wall), but a request still buys exactly what it asked for, floored to
    whole enforceable seconds, never raised to fit.
    """

    limits = request.resource_limits
    if limits.cpu_milliseconds < 1_000 or limits.wall_milliseconds < 1_000:
        raise WorkspaceRunnerError(
            "subsecond limits are not enforceable by this OCI profile"
        )
    if limits.process_count + 1 > MAX_PROCESSES_V2:
        raise WorkspaceRunnerError(
            "process limit leaves no room for the pinned bootstrap"
        )
    try:
        return WorkspaceSandboxLimits(
            max_cpu_seconds=limits.cpu_milliseconds // 1_000,
            max_wall_seconds=limits.wall_milliseconds // 1_000,
            max_memory_bytes=limits.memory_bytes,
            max_processes=limits.process_count + 1,
            max_result_bytes=limits.output_bytes,
            max_stdout_bytes=limits.output_bytes,
            max_stderr_bytes=limits.output_bytes,
            max_workspace_bytes=max_workspace_bytes,
            max_workspace_inodes=max_workspace_inodes,
            determinism_replicas=determinism_replicas,
        )
    except SandboxError as error:
        raise WorkspaceRunnerError(str(error)) from error


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivatedWorkspaceCampaignRunner:
    """The only production runner for v2 workspace executions.

    ``run_records`` is append-only: every run boundary, including failures and
    refusals, leaves a content-hashed record.  Nothing is ever removed.
    """

    sandbox_factory: Callable[[WorkspaceSandboxLimits], WorkspaceSandboxPort]
    activation: WorkspaceActivation
    target_class: TargetSchemaClass
    workspace_dir: Path
    determinism_replicas: int = 2
    run_records: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.activation.activated:
            raise WorkspaceRunnerError("workspace sandbox is not activated")
        if self.activation.target_schema_class_id != self.target_class.class_id:
            raise WorkspaceRunnerError(
                "workspace target schema class differs from activation"
            )
        if self.activation.target_class_definition_hash != self.target_class.definition_hash:
            raise WorkspaceRunnerError(
                "workspace target class definition differs from activation"
            )

    def admit_target(self, target_bytes: bytes) -> ExperimentTarget:
        """Admit any target in the activated schema class; refuse off-class."""

        return self.target_class.admit_target(target_bytes)

    def __call__(self, request: ExperimentRequest) -> ExperimentResult:
        if request.tool_id != WORKSPACE_ADAPTER_ID:
            raise WorkspaceRunnerError("unknown production workspace adapter")
        if request.network != "none":
            raise WorkspaceRunnerError("workspace experiment network must be none")
        derived = limits_from_request_v2(
            request, determinism_replicas=self.determinism_replicas,
        )
        sandbox = self.sandbox_factory(derived)
        if self.activation.environment_hash != sandbox.environment_sha256:
            raise WorkspaceRunnerError("sandbox environment differs from activation")
        if self.activation.policy_hash != sandbox.control_policy_sha256:
            raise WorkspaceRunnerError("sandbox control policy differs from activation")
        if self.activation.bootstrap_hash != sandbox.bootstrap_sha256:
            raise WorkspaceRunnerError("sandbox bootstrap differs from activation")
        configured = sandbox.configuration_record().get("limits")
        if configured is not None and configured != derived.to_record():
            raise WorkspaceRunnerError("sandbox limits differ from admitted request")
        execution = sandbox.run(
            SandboxProgramRequest(
                program_source=request.program_source,
                program_artifact_hash=request.program_artifact_hash,
                input_artifacts=request.input_artifacts,
                arguments=request.arguments,
            ),
            self.workspace_dir,
        )
        self.run_records.append(execution.semantic_record())
        result, status = self._project(execution)
        outcome = execution.outcome
        return ExperimentResult(
            adapter_id=WORKSPACE_ADAPTER_ID,
            adapter_version=WORKSPACE_ADAPTER_VERSION,
            adapter_configuration_hash=canonical_hash(sandbox.configuration_record()),
            environment_hash=sandbox.environment_sha256,
            status=status,
            result=result,
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            measurement_source=UsageSource.LOCALLY_MEASURED,
            cpu_milliseconds=None,
            wall_milliseconds=sum(item.wall_milliseconds for item in execution.replicas),
            peak_memory_bytes=None,
            output_bytes=(
                outcome.result_bytes_observed
                + outcome.stdout_bytes_observed
                + outcome.stderr_bytes_observed
            ),
        )

    @staticmethod
    def _project(execution: WorkspaceExecution) -> tuple[bytes, RecordStatus]:
        """Project an execution to result bytes: candidate, diagnostics, or refusal."""

        if execution.status == "completed" and execution.outcome.result is not None:
            return execution.outcome.result, RecordStatus.COMPLETED
        if execution.status == "program_failed":
            diagnostics = execution.failure_diagnostics()
            assert diagnostics is not None
            return canonical_bytes(diagnostics), RecordStatus.FAILED
        return (
            _refusal_payload(
                execution.refusal_code or "sandbox_execution_failed",
                "The workspace sandbox produced no complete candidate.",
            ),
            RecordStatus.FAILED,
        )

    @property
    def last_run_record(self) -> dict[str, Any] | None:
        return self.run_records[-1] if self.run_records else None


__all__ = [
    "ActivatedWorkspaceCampaignRunner", "WORKSPACE_ADAPTER_ID",
    "WORKSPACE_ADAPTER_VERSION", "WORKSPACE_REFUSAL_SCHEMA",
    "WorkspaceRunnerError", "limits_from_request_v2",
]
