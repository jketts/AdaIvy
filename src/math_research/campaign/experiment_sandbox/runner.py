"""Campaign ports for the activated ADR-0066 sandbox and exact verifier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from pathlib import Path

from ..records import RecordStatus, UsageSource, canonical_bytes, canonical_hash
from ..runner import ExperimentRequest, ExperimentResult, VerificationRequest
from .attestation import SandboxActivation
from .image_lock import load_campaign_image_lock, load_phase4b_image_lock
from .ports import ExperimentSandboxPort
from .sandbox import (
    CONTRACT_VERSION,
    MAX_PROCESSES,
    CampaignSandboxLimits,
    SandboxError,
    SandboxProgramRequest,
    OciExperimentSandbox,
)
from ...phase4b.oci_parser_sandbox import OciRuntimeIdentity
from .verifier import ExperimentTarget, trust_block, verify_candidate

ADAPTER_ID = "campaign_exact_python"
ADAPTER_VERSION = "1.0.0"
VERIFIER_ID = "exact_graph_candidate_verifier"
VERIFIER_VERSION = "1.0.0"


class CampaignSandboxRunnerError(ValueError):
    """A production request is incompatible with the activated sandbox."""


def _refusal(code: str, detail: str) -> bytes:
    value: dict[str, Any] = {
        "detail": detail,
        "epistemic_warrant_created": False,
        "refusal_code": code,
        "schema_version": "adaivy.campaign-experiment-refusal.v1",
        "status": "refused",
    }
    value["content_hash"] = canonical_hash(value)
    return canonical_bytes(value)


def limits_from_request(request: ExperimentRequest) -> CampaignSandboxLimits:
    """Translate campaign bounds without rounding any model-chosen bound up."""

    limits = request.resource_limits
    if limits.cpu_milliseconds < 1_000 or limits.wall_milliseconds < 1_000:
        raise CampaignSandboxRunnerError("subsecond limits are not enforceable by this OCI profile")
    if limits.process_count + 1 > MAX_PROCESSES:
        raise CampaignSandboxRunnerError("process limit leaves no room for the pinned bootstrap")
    try:
        return CampaignSandboxLimits(
            max_cpu_seconds=limits.cpu_milliseconds // 1_000,
            max_wall_seconds=limits.wall_milliseconds // 1_000,
            max_memory_bytes=limits.memory_bytes,
            max_processes=limits.process_count + 1,
            max_result_bytes=limits.output_bytes,
            max_stdout_bytes=limits.output_bytes,
            max_stderr_bytes=limits.output_bytes,
        )
    except SandboxError as error:
        raise CampaignSandboxRunnerError(str(error)) from error


@dataclass(frozen=True, slots=True, kw_only=True)
class ActivatedCampaignExperimentRunner:
    """The only production ``CampaignExperimentRunner`` for generated Python."""

    sandbox_factory: Callable[[CampaignSandboxLimits], ExperimentSandboxPort]
    activation: SandboxActivation
    target_hash: str

    def __post_init__(self) -> None:
        if not self.activation.activated:
            raise CampaignSandboxRunnerError("campaign experiment sandbox is not activated")
        if self.activation.target_hash != self.target_hash:
            raise CampaignSandboxRunnerError("campaign target differs from activation")

    def __call__(self, request: ExperimentRequest) -> ExperimentResult:
        if request.tool_id != ADAPTER_ID:
            raise CampaignSandboxRunnerError("unknown production experiment adapter")
        if request.network != "none":
            raise CampaignSandboxRunnerError("campaign experiment network must be none")
        # A caller must construct the sandbox with precisely these derived limits;
        # an adapter cannot silently round up or substitute a looser profile.
        derived = limits_from_request(request)
        sandbox = self.sandbox_factory(derived)
        if self.activation.environment_hash != sandbox.environment_sha256:
            raise CampaignSandboxRunnerError("sandbox environment differs from activation")
        if self.activation.policy_hash != sandbox.control_policy_sha256:
            raise CampaignSandboxRunnerError("sandbox control policy differs from activation")
        if self.activation.bootstrap_hash != sandbox.bootstrap_sha256:
            raise CampaignSandboxRunnerError("sandbox bootstrap differs from activation")
        configured = sandbox.configuration_record().get("limits")
        if configured is not None and configured != derived.to_record():
            raise CampaignSandboxRunnerError("sandbox limits differ from admitted request")
        execution = sandbox.run(SandboxProgramRequest(
            program_source=request.program_source,
            program_artifact_hash=request.program_artifact_hash,
            input_artifacts=request.input_artifacts,
            arguments=request.arguments,
        ))
        outcome = execution.outcome
        if execution.status != "completed" or outcome.result is None:
            result = _refusal(
                execution.refusal_code or "sandbox_execution_failed",
                "The sandbox produced no complete deterministic candidate.",
            )
            status = RecordStatus.FAILED
        else:
            result = outcome.result
            status = RecordStatus.COMPLETED
        return ExperimentResult(
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
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


@dataclass(frozen=True, slots=True, kw_only=True)
class ExactGraphCampaignVerifier:
    """Isolated verifier adapter: only the frozen target and selection enter."""

    target: ExperimentTarget

    def __call__(self, request: VerificationRequest) -> ExperimentResult:
        if request.target_hash != self.target.target_hash:
            raise CampaignSandboxRunnerError("verifier target hash differs")
        candidate_hash, candidate = request.candidate_artifact
        verdict = verify_candidate(self.target, candidate)
        if verdict.candidate_hash != candidate_hash:
            raise CampaignSandboxRunnerError("selected candidate bytes differ from their hash")
        result = canonical_bytes(verdict.to_record())
        return ExperimentResult(
            adapter_id=VERIFIER_ID,
            adapter_version=VERIFIER_VERSION,
            adapter_configuration_hash=canonical_hash({
                "engine": self.target.engine,
                "target_hash": self.target.target_hash,
                "trust": trust_block(),
            }),
            environment_hash=canonical_hash({
                "arithmetic": "int_and_fraction_only",
                "location": "host_process",
                "verifier": VERIFIER_ID,
            }),
            status=(
                RecordStatus.COMPLETED
                if verdict.verdict == "target_satisfied"
                else RecordStatus.FAILED
            ),
            result=result,
            stdout=b"",
            stderr=b"",
            measurement_source=UsageSource.UNAVAILABLE,
            cpu_milliseconds=None,
            wall_milliseconds=None,
            peak_memory_bytes=None,
            output_bytes=len(result),
        )


def build_activated_campaign_experiment_runner(
    *, repository_root: Path, runtime: OciRuntimeIdentity,
    activation: SandboxActivation, target_hash: str,
) -> ActivatedCampaignExperimentRunner:
    """Build the production adapter only from the exact activated lock pair."""

    campaign_lock = load_campaign_image_lock(repository_root)
    phase4b_lock = load_phase4b_image_lock(repository_root)
    if activation.campaign_lock_sha256 != campaign_lock.lock_sha256:
        raise CampaignSandboxRunnerError("campaign image lock differs from activation")
    if activation.phase4b_lock_sha256 != phase4b_lock.lock_sha256:
        raise CampaignSandboxRunnerError("Phase 4B image lock differs from activation")
    if activation.environment_hash != runtime.environment_sha256:
        raise CampaignSandboxRunnerError("OCI runtime differs from activation")

    def factory(limits: CampaignSandboxLimits) -> OciExperimentSandbox:
        return OciExperimentSandbox(
            expected_runtime=runtime, image_lock=campaign_lock, limits=limits,
        )

    return ActivatedCampaignExperimentRunner(
        sandbox_factory=factory, activation=activation, target_hash=target_hash,
    )


__all__ = [
    "ADAPTER_ID", "ADAPTER_VERSION", "ActivatedCampaignExperimentRunner",
    "CampaignSandboxRunnerError", "ExactGraphCampaignVerifier", "VERIFIER_ID",
    "VERIFIER_VERSION", "build_activated_campaign_experiment_runner",
    "limits_from_request",
]
