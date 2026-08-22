"""Operator entrypoint for the ADR-0057 provenance-closed research campaign.

ADR-0065 is the wiring decision behind this module: the campaign ledger, the
sequential runner, the live gateway planner, and strict replay were all accepted
and implemented, and nothing could start them. This module is the front door and
nothing more. It adds no record type, no action type, no adapter, no provider,
no network surface beyond the Phase 2 gateway, and no authority for a model or
tool result. It changes no file under ``campaign/``.

`--provider fixture` is the default: a scripted planner that holds no gateway,
calls nothing, and needs no key, so the offline acceptance path is the default
and spending money is the explicit choice. A live provider additionally requires
`--execute`, a content-hashed live configuration, a confirmed pricing snapshot,
and the exact activation acknowledgement; the shared ADR-0057 §3 activation
service performs exactly one no-retry request through the same gateway the lead
will use, and a failed activation is a terminal recorded activation failure.

`run_program` is fail-closed here. The injected experiment runner executes
nothing and names the pending ADR-0066 sandbox gate. This module imports no
process, socket, or network module, and reads no clock: `--recorded-at` is an
argument so the fixture path is byte-reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .application.problem_intake import load_problem_definition_file
from .campaign.records import (
    ActionRecord,
    ActionType,
    ActorType,
    CampaignProvenanceError,
    ModelCallRecord,
    RecordStatus,
    UsageSource,
    canonical_bytes,
    canonical_hash,
)
from .campaign.replay import (
    build_campaign_export,
    derive_usage,
    export_campaign_bytes,
    verify_campaign_export,
)
from .campaign.runner import (
    ACTION_SCHEMA_VERSION,
    CampaignRunnerError,
    CampaignRunnerPolicy,
    ExperimentRequest,
    ExperimentResult,
    PlannerContext,
    PlannerResponse,
    ResourceLimits,
    SequentialCampaignRunner,
    VerificationRequest,
)
from .domain.entities import ResearchDossier
from .interchange import export_dossier_dict
from .novelty import (
    NoveltyRecheckError,
    classify_prior_art,
    read_recheck,
    require_checkpoint,
)
from .phase2.live_config import LiveRunConfigurationError, load_live_run_configuration
from .phase2.pricing import (
    PricingSnapshotError,
    load_pricing_snapshot,
    pricing_snapshot_is_confirmed,
)
from .phase2.provider_registry import build_gateway
from .provider_activation import (
    LIVE_PROBE_ACKNOWLEDGEMENT,
    GatewayProviderProbe,
    LiveProviderProbeResult,
    run_live_provider_probe,
    static_provider_preflight,
)
from .runtime.lead import freeze_target


CAMPAIGN_CONFIG_SCHEMA_VERSION = "adaivy.campaign-configuration.v1"
CAMPAIGN_TARGET_SCHEMA_VERSION = "adaivy.campaign-target.v1"
CAMPAIGN_FACTS_SCHEMA_VERSION = "adaivy.campaign-facts.v1"
CAMPAIGN_REPLAY_SCHEMA_VERSION = "adaivy.campaign-replay.v1"
CAMPAIGN_REFUSAL_SCHEMA_VERSION = "adaivy.campaign-refusal.v1"

#: Hard ceilings on every campaign bound, derived from ADR-0065 rather than from
#: any fixture. A configuration file is operator input and is not trusted to be
#: sane: a bound above its ceiling is refused outright, never clamped, because
#: silently lowering a requested bound would let the ledger disagree with the run.
#:
#: ``MAX_ACTIONS_CEILING`` matches ADR-0047's ``MAX_ITERATIONS_CEILING``: one
#: central lead, one action per model call, and a campaign a human can read end
#: to end. ``MAX_MODEL_CALLS_CEILING`` and ``MAX_COST_MICROUSD_CEILING`` are the
#: ADR-0047 runtime ceilings unchanged, so the two loops cannot disagree about
#: what a session may spend. ``MAX_PROGRAM_BYTES_CEILING`` is exactly the
#: ``program_source`` bound the closed action parser already enforces, so a
#: configuration cannot admit a program the parser would reject.
MAX_ACTIONS_CEILING = 64
MAX_TOOL_RUNS_CEILING = 16
MAX_MODEL_CALLS_CEILING = 256
MAX_INPUT_TOKENS_CEILING = 2_000_000
MAX_OUTPUT_TOKENS_CEILING = 500_000
MAX_COST_MICROUSD_CEILING = 25_000_000
MAX_PROGRAM_BYTES_CEILING = 262_144
MAX_ARTIFACT_BYTES_CEILING = 1_048_576
MAX_CONTEXT_BYTES_CEILING = 262_144
MAX_CPU_MILLISECONDS_CEILING = 60_000
MAX_WALL_MILLISECONDS_CEILING = 300_000
MAX_MEMORY_BYTES_CEILING = 536_870_912
MAX_OUTPUT_BYTES_CEILING = 1_048_576
MAX_PROCESS_COUNT_CEILING = 8

#: Named machine-readable refusals. Every one of these is a fail-closed exit,
#: never a downgraded success.
REFUSAL_ROOT_RECORDED = "campaign_root_already_recorded"
REFUSAL_DURABLE_REWRITE = "campaign_durable_record_rewrite_refused"
REFUSAL_NOVELTY_ABSENT = "fresh_novelty_recheck_required_before_research"
REFUSAL_LIVE_REQUIRES_EXECUTE = "live_campaign_requires_explicit_execute"
REFUSAL_LIVE_REQUIRES_ARTIFACTS = (
    "live_campaign_requires_live_config_and_pricing_snapshot"
)
REFUSAL_PROVIDER_MISMATCH = "campaign_provider_differs_from_live_configuration"
REFUSAL_PRICING_UNCONFIRMED = "campaign_pricing_snapshot_not_confirmed_or_mismatched"
REFUSAL_NOT_ACKNOWLEDGED = "live_provider_activation_not_acknowledged"
REFUSAL_STATIC_PREFLIGHT = "static_provider_preflight_failed"
REFUSAL_BUDGET_EXCEEDS_CAP = (
    "live_configuration_budget_exceeds_campaign_configuration_cap"
)
REFUSAL_ACTIVATION_NOT_EXECUTED = "provider_activation_not_executed"
REFUSAL_ACTIVATION_FAILED = "provider_activation_failed"
REFUSAL_RUNNER_REJECTED = "campaign_runner_rejected_the_run"
REFUSAL_BOUND_VIOLATION = "campaign_recorded_usage_exceeds_configured_bound"
REFUSAL_FACTS_MISMATCH = "campaign_facts_are_not_derived_from_the_ledger"
REFUSAL_ARTIFACT_MISSING = "campaign_artifact_absent_from_the_store"
REFUSAL_ARTIFACT_BYTES = "campaign_artifact_bytes_do_not_match_their_hash"
REFUSAL_TARGET_MISMATCH = "campaign_target_record_does_not_hash_to_the_ledger_target"
REFUSAL_CONFIG_MISMATCH = "campaign_configuration_hash_differs_from_the_ledger"

#: ADR-0066 is the separate digest-pinned OCI experiment-sandbox gate. Until it
#: passes, model-authored source is recorded and never executed.
SANDBOX_GATE_DECISION = "ADR-0066"
SANDBOX_REFUSAL_REASON = "experiment_sandbox_gate_not_passed_adr_0066"
SANDBOX_ADAPTER_ID = "experiment_sandbox_pending_gate"

#: ADR-0057 §1 submits a selected candidate to an isolated verifier. No campaign
#: verifier port implementation exists; this records the absence rather than
#: approximating one.
VERIFIER_ABSENT_REASON = "isolated_campaign_verifier_not_wired"
VERIFIER_ADAPTER_ID = "isolated_verifier_absent"

#: The fixture provider has no live configuration and no pricing snapshot. The
#: runner requires both identities to be sha256 hashes, so an explicit "absent"
#: sentinel is recorded rather than a hash of something unrelated.
FIXTURE_PROVIDER = "fixture"
FIXTURE_MODEL_IDENTIFIER = "scripted-campaign-lead"
FIXTURE_LIVE_CONFIGURATION_HASH = canonical_hash({
    "kind": "fixture_sentinel", "live_configuration": "absent",
})
FIXTURE_PRICING_SNAPSHOT_HASH = canonical_hash({
    "kind": "fixture_sentinel", "pricing_snapshot": "absent",
})

FIXTURE_SCRIPTS = ("derive-inspect-verify-report", "program-sandbox-refusal")

FIXTURE_CANDIDATE_TEXT = (
    "Scripted fixture candidate. This text is a placeholder proposal produced by "
    "the offline campaign entrypoint. It contains no mathematics, was not "
    "produced by a model, and carries no warrant."
)
FIXTURE_PROGRAM_SOURCE = (
    "# Scripted fixture program. Recorded, never executed: the ADR-0066\n"
    "# experiment-sandbox gate has not passed.\n"
    "raise SystemExit('this program is not executable in the offline entrypoint')\n"
)
FIXTURE_REPORT_TEXT = (
    "Scripted fixture campaign reached its terminal report action. No program was "
    "executed, no candidate was verified, no model was called, and no epistemic "
    "warrant exists."
)


class CampaignConfigurationError(ValueError):
    """Fail-closed rejection of a campaign configuration."""


# --------------------------------------------------------------------------- #
# Content-hashed campaign configuration
# --------------------------------------------------------------------------- #

_CONFIG_BOUNDS: tuple[tuple[str, int], ...] = (
    ("max_actions", MAX_ACTIONS_CEILING),
    ("max_tool_runs", MAX_TOOL_RUNS_CEILING),
    ("max_model_calls", MAX_MODEL_CALLS_CEILING),
    ("max_input_tokens", MAX_INPUT_TOKENS_CEILING),
    ("max_output_tokens", MAX_OUTPUT_TOKENS_CEILING),
    ("max_cost_microusd", MAX_COST_MICROUSD_CEILING),
    ("max_program_bytes", MAX_PROGRAM_BYTES_CEILING),
    ("max_artifact_bytes", MAX_ARTIFACT_BYTES_CEILING),
    ("max_context_bytes", MAX_CONTEXT_BYTES_CEILING),
    ("max_cpu_milliseconds", MAX_CPU_MILLISECONDS_CEILING),
    ("max_wall_milliseconds", MAX_WALL_MILLISECONDS_CEILING),
    ("max_memory_bytes", MAX_MEMORY_BYTES_CEILING),
    ("max_output_bytes", MAX_OUTPUT_BYTES_CEILING),
    ("max_process_count", MAX_PROCESS_COUNT_CEILING),
)

_CONFIG_FIELDS = frozenset(
    {"schema_version", "campaign_configuration_id", "allowed_tools", "content_hash"}
    | {name for name, _ in _CONFIG_BOUNDS}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignConfiguration:
    """Immutable campaign bounds. `content_hash` covers every other field."""

    schema_version: str
    campaign_configuration_id: str
    allowed_tools: tuple[str, ...]
    max_actions: int
    max_tool_runs: int
    max_model_calls: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_microusd: int
    max_program_bytes: int
    max_artifact_bytes: int
    max_context_bytes: int
    max_cpu_milliseconds: int
    max_wall_milliseconds: int
    max_memory_bytes: int
    max_output_bytes: int
    max_process_count: int
    content_hash: str


def campaign_configuration_payload(
    configuration: CampaignConfiguration,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": configuration.schema_version,
        "campaign_configuration_id": configuration.campaign_configuration_id,
        "allowed_tools": list(configuration.allowed_tools),
        "content_hash": configuration.content_hash,
    }
    for name, _ in _CONFIG_BOUNDS:
        payload[name] = getattr(configuration, name)
    return payload


def create_campaign_configuration(
    *, campaign_configuration_id: str, allowed_tools: tuple[str, ...], **bounds: int
) -> CampaignConfiguration:
    payload: dict[str, Any] = {
        "schema_version": CAMPAIGN_CONFIG_SCHEMA_VERSION,
        "campaign_configuration_id": campaign_configuration_id,
        "allowed_tools": sorted(set(allowed_tools)),
        "content_hash": None,
    }
    for name, _ in _CONFIG_BOUNDS:
        if name not in bounds:
            raise CampaignConfigurationError(f"campaign bound {name} is required")
        payload[name] = bounds[name]
    payload["content_hash"] = canonical_hash(payload)
    return parse_campaign_configuration(payload)


def parse_campaign_configuration(payload: Mapping[str, Any]) -> CampaignConfiguration:
    if set(payload) != _CONFIG_FIELDS:
        raise CampaignConfigurationError(
            "campaign configuration fields differ from the closed schema"
        )
    if payload["schema_version"] != CAMPAIGN_CONFIG_SCHEMA_VERSION:
        raise CampaignConfigurationError(
            "unsupported campaign configuration schema_version"
        )
    identifier = payload["campaign_configuration_id"]
    if not isinstance(identifier, str) or not identifier:
        raise CampaignConfigurationError(
            "campaign_configuration_id must be a non-empty string"
        )
    tools = payload["allowed_tools"]
    if (
        not isinstance(tools, list)
        or not tools
        or any(not isinstance(item, str) or not item for item in tools)
        or sorted(set(tools)) != list(tools)
    ):
        raise CampaignConfigurationError(
            "allowed_tools must be a sorted non-empty list of unique tool identifiers"
        )
    values: dict[str, int] = {}
    for name, ceiling in _CONFIG_BOUNDS:
        value = payload[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise CampaignConfigurationError(f"{name} must be a positive integer")
        if value > ceiling:
            raise CampaignConfigurationError(
                f"{name} of {value} exceeds the hard ceiling of {ceiling}"
            )
        values[name] = value
    # An ADR-0057 §3 activation occupies the first action slot, so a campaign
    # whose action bound is one cannot hold a research action at all.
    if values["max_actions"] < 2:
        raise CampaignConfigurationError(
            "max_actions must be at least two: one activation plus one research action"
        )
    if values["max_model_calls"] < values["max_actions"]:
        raise CampaignConfigurationError(
            "max_model_calls must be at least max_actions: the runner records one "
            "model call per action"
        )
    if values["max_program_bytes"] > values["max_artifact_bytes"]:
        raise CampaignConfigurationError(
            "max_program_bytes exceeds max_artifact_bytes, so a program the parser "
            "accepts could not be stored"
        )
    if values["max_output_bytes"] > values["max_artifact_bytes"]:
        raise CampaignConfigurationError(
            "max_output_bytes exceeds max_artifact_bytes, so admitted tool output "
            "could not be stored"
        )
    content_hash = payload["content_hash"]
    preimage = {key: value for key, value in payload.items() if key != "content_hash"}
    preimage["content_hash"] = None
    if canonical_hash(preimage) != content_hash:
        raise CampaignConfigurationError("campaign configuration content_hash mismatch")
    return CampaignConfiguration(
        schema_version=payload["schema_version"],
        campaign_configuration_id=identifier,
        allowed_tools=tuple(tools),
        content_hash=content_hash,
        **values,
    )


def _strict_json(raw: bytes, *, what: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        for key, value in items:
            if key in seen:
                raise CampaignConfigurationError(f"duplicate {what} field: {key}")
            seen[key] = value
        return seen

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignConfigurationError(f"{what} is not valid UTF-8 JSON") from error


def load_campaign_configuration(path: Path) -> CampaignConfiguration:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise CampaignConfigurationError(
            f"cannot load campaign configuration: {path}"
        ) from error
    payload = _strict_json(raw, what="campaign configuration")
    if not isinstance(payload, dict):
        raise CampaignConfigurationError("campaign configuration must be a JSON object")
    return parse_campaign_configuration(payload)


def campaign_configuration_bytes(configuration: CampaignConfiguration) -> bytes:
    return canonical_bytes(campaign_configuration_payload(configuration)) + b"\n"


def runner_policy(configuration: CampaignConfiguration) -> CampaignRunnerPolicy:
    return CampaignRunnerPolicy(
        allowed_tools=frozenset(configuration.allowed_tools),
        max_actions=configuration.max_actions,
        max_tool_runs=configuration.max_tool_runs,
        max_program_bytes=configuration.max_program_bytes,
        max_artifact_bytes=configuration.max_artifact_bytes,
        max_cpu_milliseconds=configuration.max_cpu_milliseconds,
        max_wall_milliseconds=configuration.max_wall_milliseconds,
        max_memory_bytes=configuration.max_memory_bytes,
        max_output_bytes=configuration.max_output_bytes,
        max_process_count=configuration.max_process_count,
    )


# --------------------------------------------------------------------------- #
# Frozen campaign target
# --------------------------------------------------------------------------- #


def campaign_target_record(dossier: ResearchDossier) -> dict[str, Any]:
    """Freeze the target identity so `target_hash` is re-derivable from a file."""

    target = freeze_target(dossier)
    return {
        "schema_version": CAMPAIGN_TARGET_SCHEMA_VERSION,
        "problem_id": dossier.problem.id.value,
        "dossier_id": dossier.id.value,
        "dossier_content_hash": str(export_dossier_dict(dossier)["content_hash"]),
        "target_claim_id": target.target_claim_id.value,
        "target_statement_hash": target.target_statement_hash,
        "formalization_statement_hash": target.formalization_statement_hash,
        "assumption_manifest_hash": target.assumption_manifest_hash,
        "semantic_alignment_hash": target.semantic_alignment_hash,
        "dossier_hash": target.dossier_hash,
    }


def campaign_target_bytes(record: Mapping[str, Any]) -> bytes:
    return canonical_bytes(record) + b"\n"


def _raw_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


# --------------------------------------------------------------------------- #
# Injected ports
# --------------------------------------------------------------------------- #


class FileArtifactStore:
    """Append-only, content-addressed artifact store under one campaign root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.log = root.parent / "artifact-log.jsonl"

    def path_for(self, content_hash: str) -> Path:
        if not content_hash.startswith("sha256:"):
            raise CampaignRunnerError("artifact identity is not a sha256 content hash")
        return self.root / ("sha256-" + content_hash[len("sha256:"):])

    def put(self, content: bytes, *, media_type: str) -> str:
        content_hash = _raw_hash(content)
        path = self.path_for(content_hash)
        if path.exists():
            if path.read_bytes() != content:
                raise CampaignRunnerError(
                    "artifact store holds different bytes for the same hash"
                )
            return content_hash
        path.write_bytes(content)
        line = json.dumps(
            {"content_hash": content_hash, "media_type": media_type},
            sort_keys=True, separators=(",", ":"),
        )
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return content_hash

    def get(self, content_hash: str) -> bytes:
        path = self.path_for(content_hash)
        if not path.exists():
            raise CampaignRunnerError(f"artifact {content_hash} is not in the store")
        content = path.read_bytes()
        if _raw_hash(content) != content_hash:
            raise CampaignRunnerError(f"artifact {content_hash} bytes do not match")
        return content


def _refusal_payload(reason: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": CAMPAIGN_REFUSAL_SCHEMA_VERSION,
        "reason": reason,
        "executed": False,
        "subprocess_opened": False,
        "network_opened": False,
        "epistemic_warrant_created": False,
    }
    payload.update(extra)
    return payload


class PendingSandboxExperimentRunner:
    """`CampaignExperimentRunner` that executes nothing (ADR-0057 §2, ADR-0066).

    Model-authored source is recorded by the runner and reaches this port; the
    port refuses by name and the refusal is retained as a failed tool run rather
    than discarded. No sandbox is implemented, stubbed, or approximated here and
    no subprocess or socket is opened.
    """

    adapter_id = SANDBOX_ADAPTER_ID
    reason = SANDBOX_REFUSAL_REASON

    def __init__(self) -> None:
        self.requests: list[ExperimentRequest] = []

    def __call__(self, request: ExperimentRequest) -> ExperimentResult:
        self.requests.append(request)
        payload = _refusal_payload(
            SANDBOX_REFUSAL_REASON,
            blocking_decision=SANDBOX_GATE_DECISION,
            tool_id=request.tool_id,
            program_artifact_hash=request.program_artifact_hash,
        )
        return ExperimentResult(
            adapter_id=SANDBOX_ADAPTER_ID,
            adapter_version="0.0.0",
            adapter_configuration_hash=canonical_hash({
                "adapter": SANDBOX_ADAPTER_ID,
                "blocking_decision": SANDBOX_GATE_DECISION,
                "executes_generated_code": False,
            }),
            environment_hash=canonical_hash({
                "environment": "none", "network": "none", "subprocess": "none",
            }),
            status=RecordStatus.FAILED,
            result=canonical_bytes(payload) + b"\n",
            stdout=b"",
            stderr=b"",
            measurement_source=UsageSource.UNAVAILABLE,
            cpu_milliseconds=None,
            wall_milliseconds=None,
            peak_memory_bytes=None,
            output_bytes=None,
        )


class AbsentVerifier:
    """`VerifierPort` that records the absence of an isolated campaign verifier.

    ADR-0057 §1 submits a selected candidate to an isolated verifier. None is
    wired in this repository and inventing one is a separate decision, so this
    port produces a failed tool run naming the absence. It therefore cannot be
    mistaken for verification and creates no warrant.
    """

    adapter_id = VERIFIER_ADAPTER_ID
    reason = VERIFIER_ABSENT_REASON

    def __init__(self) -> None:
        self.requests: list[VerificationRequest] = []

    def __call__(self, request: VerificationRequest) -> ExperimentResult:
        self.requests.append(request)
        payload = _refusal_payload(
            VERIFIER_ABSENT_REASON,
            candidate_artifact_hash=request.candidate_artifact[0],
            verification_performed=False,
        )
        return ExperimentResult(
            adapter_id=VERIFIER_ADAPTER_ID,
            adapter_version="0.0.0",
            adapter_configuration_hash=canonical_hash({
                "adapter": VERIFIER_ADAPTER_ID, "verifier_wired": False,
            }),
            environment_hash=canonical_hash({
                "environment": "none", "network": "none", "subprocess": "none",
            }),
            status=RecordStatus.FAILED,
            result=canonical_bytes(payload) + b"\n",
            stdout=b"",
            stderr=b"",
            measurement_source=UsageSource.UNAVAILABLE,
            cpu_milliseconds=None,
            wall_milliseconds=None,
            peak_memory_bytes=None,
            output_bytes=None,
        )


def _action_json(kind: str, **updates: Any) -> bytes:
    value: dict[str, Any] = {
        "schema_version": ACTION_SCHEMA_VERSION,
        "action_type": kind,
        "branch_id": "branch.main",
        "rationale": f"Scripted offline fixture step: {kind}.",
        "artifact_text": None,
        "program_source": None,
        "tool_request": None,
        "selected_candidate_hash": None,
        "selected_tool_artifact_hashes": [],
        "report_text": None,
    }
    value.update(updates)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ScriptedCampaignPlanner:
    """Offline `PlannerPort`. Holds no gateway, calls nothing, needs no key.

    Its responses are recorded as model calls by the runner, so they carry
    `provider: "fixture"`, `usage_source: "unavailable"`, zero tokens and a null
    estimated cost. A fixture campaign therefore cannot present itself as
    measured provider work.
    """

    def __init__(
        self, *, script: str, tool_id: str, resource_limits: ResourceLimits,
    ) -> None:
        if script not in FIXTURE_SCRIPTS:
            raise CampaignRunnerError(f"unknown fixture script: {script}")
        self.script = script
        self.tool_id = tool_id
        self.resource_limits = resource_limits
        self.contexts: list[PlannerContext] = []
        self.candidate_hash = _raw_hash(FIXTURE_CANDIDATE_TEXT.encode("utf-8"))

    def __call__(self, context: PlannerContext) -> PlannerResponse:
        self.contexts.append(context)
        steps = self._steps()
        index = len(self.contexts) - 1
        if index >= len(steps):
            raise CampaignRunnerError(
                "scripted campaign planner exhausted before a terminal action"
            )
        return PlannerResponse(
            action_json=steps[index](context),
            provider=FIXTURE_PROVIDER,
            model_identifier=FIXTURE_MODEL_IDENTIFIER,
            status=RecordStatus.COMPLETED,
            usage_source=UsageSource.UNAVAILABLE,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_microusd=None,
            provider_request_id=None,
        )

    def _steps(self) -> tuple[Callable[[PlannerContext], bytes], ...]:
        if self.script == "derive-inspect-verify-report":
            return (self._derive, self._inspect, self._verify, self._report)
        return (self._derive, self._write_program, self._run_program, self._report)

    def _derive(self, _context: PlannerContext) -> bytes:
        return _action_json("derive", artifact_text=FIXTURE_CANDIDATE_TEXT)

    def _inspect(self, _context: PlannerContext) -> bytes:
        return _action_json(
            "inspect_result", selected_candidate_hash=self.candidate_hash,
        )

    def _verify(self, context: PlannerContext) -> bytes:
        return _action_json(
            "verify",
            selected_candidate_hash=context.selected_candidate_hash,
            selected_tool_artifact_hashes=list(context.selected_tool_artifact_hashes),
        )

    def _write_program(self, _context: PlannerContext) -> bytes:
        return _action_json("write_program", program_source=FIXTURE_PROGRAM_SOURCE)

    def _run_program(self, context: PlannerContext) -> bytes:
        if not context.recorded_program_hashes:
            raise CampaignRunnerError("no recorded program is available to run")
        return _action_json("run_program", tool_request={
            "tool_id": self.tool_id,
            "program_artifact_hash": context.recorded_program_hashes[0],
            "input_artifact_hashes": [],
            "arguments": [],
            "resource_limits": {
                "cpu_milliseconds": self.resource_limits.cpu_milliseconds,
                "wall_milliseconds": self.resource_limits.wall_milliseconds,
                "memory_bytes": self.resource_limits.memory_bytes,
                "output_bytes": self.resource_limits.output_bytes,
                "process_count": self.resource_limits.process_count,
            },
            "network": "none",
        })

    def _report(self, _context: PlannerContext) -> bytes:
        return _action_json("report", report_text=FIXTURE_REPORT_TEXT)


# --------------------------------------------------------------------------- #
# Derived facts
# --------------------------------------------------------------------------- #


def campaign_facts(export: Any, recheck: Any) -> dict[str, Any]:
    """Derive every fact from the ledger and the bound re-check.

    Nothing here is an argument, so `inspect` can recompute the file and refuse a
    hand-edited one. No field can promote anything: the guardrail block is a
    constant `False`/`0` and is asserted, not chosen.
    """

    actions = list(export.actions)
    terminal = actions[-1] if actions else None
    classification = classify_prior_art(
        outcome=recheck.outcome,
        relationship=recheck.prior_art_relationship,
        prior_resolution=recheck.prior_resolution,
        verification_status=recheck.prior_resolution_verification,
    )
    return {
        "schema_version": CAMPAIGN_FACTS_SCHEMA_VERSION,
        "campaign_id": export.campaign_id,
        "target_hash": export.target_hash,
        "configuration_hash": export.configuration_hash,
        "content_hash": export.content_hash,
        "operational_hash": export.operational_hash,
        "attribution_status": export.attribution_status,
        "measurement_status": export.measurement_status,
        "action_types": [item.action_type.value for item in actions],
        "terminal_action_type": None if terminal is None else terminal.action_type.value,
        "terminal_action_status": None if terminal is None else terminal.status.value,
        "providers": sorted({item.provider for item in export.model_calls}),
        "tool_adapters": sorted({item.adapter_id for item in export.tool_runs}),
        "usage": dict(export.usage),
        "experiment_sandbox": {
            "status": "pending_gate",
            "blocking_decision": SANDBOX_GATE_DECISION,
            "reason": SANDBOX_REFUSAL_REASON,
            "programs_recorded": sum(
                item.action_type is ActionType.WRITE_PROGRAM for item in actions
            ),
            "programs_executed": sum(
                item.adapter_id == SANDBOX_ADAPTER_ID
                and item.status is RecordStatus.COMPLETED
                for item in export.tool_runs
            ),
            "execution_refusals_recorded": sum(
                item.adapter_id == SANDBOX_ADAPTER_ID for item in export.tool_runs
            ),
        },
        "isolated_verifier": {
            "status": "absent",
            "reason": VERIFIER_ABSENT_REASON,
            "verifications_completed": sum(
                item.adapter_id == VERIFIER_ADAPTER_ID
                and item.status is RecordStatus.COMPLETED
                for item in export.tool_runs
            ),
            "verification_refusals_recorded": sum(
                item.adapter_id == VERIFIER_ADAPTER_ID for item in export.tool_runs
            ),
        },
        "novelty_recheck": {
            "recheck_id": recheck.recheck_id,
            "checkpoint": recheck.checkpoint,
            "content_hash": recheck.content_hash,
            "outcome": recheck.outcome,
            "report_classification": classification.report_classification,
            "target_resolution_status": classification.target_resolution_status,
        },
        "guardrails": {
            "epistemic_warrant_created": False,
            "applicability_asserted": False,
            "novelty_assessed": False,
            "significance_assessed": False,
            "graph_admission_created": False,
            "search_tiers_enabled": False,
            "network_requests_during_replay": 0,
            "subprocesses_opened": 0,
        },
    }


def _artifact_hashes(export: Any) -> tuple[str, ...]:
    """Every stored-artifact hash in the ledger.

    `target_hash` and `configuration_hash` are the seed pair and are verified
    against their own files instead, because neither is stored as an artifact.
    Request, adapter-configuration and environment hashes are canonical hashes
    of structures rather than of stored bytes and are excluded for the same
    reason.
    """

    seeds = {export.target_hash, export.configuration_hash}
    found: set[str] = set()
    for action in export.actions:
        found.update(action.input_artifact_hashes)
        found.update(action.output_artifact_hashes)
    for call in export.model_calls:
        found.add(call.result_hash)
    for run in export.tool_runs:
        found.update((run.result_hash, run.stdout_hash, run.stderr_hash))
    return tuple(sorted(found - seeds))


# --------------------------------------------------------------------------- #
# Command implementations
# --------------------------------------------------------------------------- #


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _refuse(reason: str, **extra: Any) -> int:
    _print({"status": "refused", "reason": reason, **extra})
    return 2


def _write_once(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise CampaignConfigurationError(f"{REFUSAL_DURABLE_REWRITE}: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _dossier(args: argparse.Namespace) -> ResearchDossier:
    if getattr(args, "problem", None) is not None:
        instant = datetime.fromisoformat(args.instant)
        return load_problem_definition_file(args.problem, instant=instant).dossier
    from .phase2.fixtures import build_open_theorem_dossier

    return build_open_theorem_dossier()


def _config_create(args: argparse.Namespace) -> int:
    try:
        configuration = create_campaign_configuration(
            campaign_configuration_id=args.campaign_configuration_id,
            allowed_tools=tuple(args.allowed_tool),
            max_actions=args.max_actions,
            max_tool_runs=args.max_tool_runs,
            max_model_calls=args.max_model_calls,
            max_input_tokens=args.max_input_tokens,
            max_output_tokens=args.max_output_tokens,
            max_cost_microusd=args.max_cost_microusd,
            max_program_bytes=args.max_program_bytes,
            max_artifact_bytes=args.max_artifact_bytes,
            max_context_bytes=args.max_context_bytes,
            max_cpu_milliseconds=args.max_cpu_milliseconds,
            max_wall_milliseconds=args.max_wall_milliseconds,
            max_memory_bytes=args.max_memory_bytes,
            max_output_bytes=args.max_output_bytes,
            max_process_count=args.max_process_count,
        )
        _write_once(args.output, campaign_configuration_bytes(configuration))
    except (CampaignConfigurationError, OSError) as error:
        return _refuse(str(error))
    _print({
        "status": "written",
        "path": str(args.output),
        **campaign_configuration_payload(configuration),
    })
    return 0


def _target(args: argparse.Namespace) -> int:
    try:
        record = campaign_target_record(_dossier(args))
        content = campaign_target_bytes(record)
        _write_once(args.output, content)
    except (CampaignConfigurationError, OSError, ValueError) as error:
        return _refuse(str(error))
    _print({
        "status": "written",
        "path": str(args.output),
        "target_hash": _raw_hash(content),
        **record,
    })
    return 0


def _live_activation(
    args: argparse.Namespace, configuration: CampaignConfiguration,
) -> tuple[int, Any, Any, Any, LiveProviderProbeResult | None]:
    """Resolve, bind, and activate the live route, or refuse by name.

    Returns `(exit_code, live, pricing, planner, activation)`. `exit_code` is
    zero only when a passed activation and a constructed planner exist.
    """

    if not args.execute:
        return (
            _refuse(REFUSAL_LIVE_REQUIRES_EXECUTE, provider=args.provider),
            None, None, None, None,
        )
    if args.live_config is None or args.pricing_snapshot is None:
        return (
            _refuse(REFUSAL_LIVE_REQUIRES_ARTIFACTS, provider=args.provider),
            None, None, None, None,
        )
    try:
        live = load_live_run_configuration(args.live_config)
        pricing = load_pricing_snapshot(args.pricing_snapshot)
    except (LiveRunConfigurationError, PricingSnapshotError, OSError) as error:
        return _refuse(str(error)), None, None, None, None
    if live.provider != args.provider:
        return (
            _refuse(
                REFUSAL_PROVIDER_MISMATCH,
                requested=args.provider, configured=live.provider,
            ),
            None, None, None, None,
        )
    if (
        pricing.snapshot_id != live.pricing_snapshot_id
        or pricing.provider != live.provider
        or pricing.model_identifier != live.model_identifier
        or not pricing_snapshot_is_confirmed(pricing)
    ):
        return _refuse(REFUSAL_PRICING_UNCONFIRMED), None, None, None, None
    if args.activation_acknowledgement != LIVE_PROBE_ACKNOWLEDGEMENT:
        return (
            _refuse(REFUSAL_NOT_ACKNOWLEDGED, expected=LIVE_PROBE_ACKNOWLEDGEMENT),
            None, None, None, None,
        )
    exceeded = sorted(
        name for name, live_value, cap in (
            ("max_attempts", live.budget.max_attempts, configuration.max_model_calls),
            ("max_input_tokens", live.budget.max_input_tokens, configuration.max_input_tokens),
            ("max_output_tokens", live.budget.max_output_tokens, configuration.max_output_tokens),
            ("max_cost_microusd", live.budget.max_cost_microusd, configuration.max_cost_microusd),
        ) if live_value > cap
    )
    if exceeded:
        return (
            _refuse(REFUSAL_BUDGET_EXCEEDS_CAP, exceeded_bounds=exceeded),
            None, None, None, None,
        )

    import os

    environment = dict(os.environ)
    static = static_provider_preflight(live, pricing, environment=environment)
    if static.status != "passed":
        return (
            _refuse(
                REFUSAL_STATIC_PREFLIGHT,
                missing_variables=list(static.missing_variables),
                failed_checks=list(static.failed_checks),
            ),
            None, None, None, None,
        )
    gateway = build_gateway(live.provider, live.model_identifier)
    activation = run_live_provider_probe(
        static, live, pricing,
        environment=environment,
        acknowledgement=args.activation_acknowledgement,
        observed_at=args.recorded_at,
        probe=GatewayProviderProbe(live, gateway),
    )
    if activation.probe_status != "passed":
        return 2, live, pricing, None, activation
    from .campaign.planner import GatewayCampaignPlanner

    try:
        planner = GatewayCampaignPlanner(
            live, pricing, gateway=gateway, activation=activation,
            action_schema=args.action_schema.read_text(encoding="utf-8"),
            max_context_bytes=configuration.max_context_bytes,
        )
    except (CampaignRunnerError, OSError) as error:
        return _refuse(str(error)), live, pricing, None, activation
    return 0, live, pricing, planner, activation


def _activation_failure_ledger(
    *,
    campaign_id: str,
    target_hash: str,
    configuration_hash: str,
    activation: LiveProviderProbeResult,
    artifacts: FileArtifactStore,
) -> Any:
    """Retain a failed ADR-0057 §3 activation as the terminal campaign ledger.

    A failed activation is never `proposer_declined` and never `completed`. It is
    one attempted request with zero completed responses, and it is retained.
    """

    activation_hash = artifacts.put(
        canonical_bytes(activation),
        media_type="application/vnd.adaivy.provider-activation+json",
    )
    usage_reported = activation.usage_reported_calls == 1
    call = ModelCallRecord(
        call_id="call.activation", campaign_id=campaign_id,
        action_id="action.activation", purpose="provider_activation",
        provider=activation.provider, model_identifier=activation.model_identifier,
        live_configuration_hash=activation.configuration_hash,
        pricing_snapshot_hash=activation.pricing_snapshot_hash,
        request_hash=str(activation.probe_request_hash),
        result_hash=activation_hash, status=RecordStatus.FAILED,
        usage_source=(
            UsageSource.API_REPORTED if usage_reported else UsageSource.UNAVAILABLE
        ),
        input_tokens=activation.input_tokens if usage_reported else 0,
        output_tokens=activation.output_tokens if usage_reported else 0,
        estimated_cost_microusd=(
            activation.estimated_cost_microusd if usage_reported else None
        ),
        provider_request_id=activation.provider_request_id,
        recorded_at=activation.observed_at,
    ).finalized()
    action = ActionRecord(
        action_id="action.activation", campaign_id=campaign_id, sequence=1,
        branch_id="branch.system", action_type=ActionType.PLAN,
        actor_type=ActorType.SYSTEM, actor_id="system.provider-activation",
        parent_action_ids=(), input_artifact_hashes=(target_hash, configuration_hash),
        source_record_ids=("call.activation",),
        output_artifact_hashes=(activation_hash,), status=RecordStatus.FAILED,
        declared_rationale=(
            "The single no-retry provider activation failed, so no mathematical "
            "campaign action was admitted."
        ),
        recorded_at=activation.observed_at,
    ).finalized()
    return build_campaign_export(
        campaign_id=campaign_id, target_hash=target_hash,
        configuration_hash=configuration_hash, actions=(action,),
        model_calls=(call,), tool_runs=(),
    )


def _run(args: argparse.Namespace) -> int:
    root: Path = args.root
    if (root / "campaign.json").exists():
        return _refuse(REFUSAL_ROOT_RECORDED, root=str(root))
    try:
        configuration = load_campaign_configuration(args.config)
    except CampaignConfigurationError as error:
        return _refuse(str(error))
    try:
        dossier = _dossier(args)
        target_record = campaign_target_record(dossier)
    except (OSError, ValueError) as error:
        return _refuse(str(error))
    target_content = campaign_target_bytes(target_record)
    target_hash = _raw_hash(target_content)

    if args.novelty_recheck is None:
        return _refuse(REFUSAL_NOVELTY_ABSENT)
    try:
        recheck = read_recheck(args.novelty_recheck)
        require_checkpoint(
            recheck, checkpoint="before_research",
            subject_id=dossier.problem.id.value,
            subject_hash=str(target_record["dossier_content_hash"]),
            next_action_id=args.campaign_id,
            action_at=args.recorded_at,
        )
    except (NoveltyRecheckError, OSError) as error:
        return _refuse(str(error))

    experiment = PendingSandboxExperimentRunner()
    verifier = AbsentVerifier()
    activation: LiveProviderProbeResult | None = None
    live_configuration_hash = FIXTURE_LIVE_CONFIGURATION_HASH
    pricing_snapshot_hash = FIXTURE_PRICING_SNAPSHOT_HASH

    if args.provider == FIXTURE_PROVIDER:
        planner: Any = ScriptedCampaignPlanner(
            script=args.fixture_script,
            tool_id=configuration.allowed_tools[0],
            resource_limits=ResourceLimits(
                cpu_milliseconds=configuration.max_cpu_milliseconds,
                wall_milliseconds=configuration.max_wall_milliseconds,
                memory_bytes=configuration.max_memory_bytes,
                output_bytes=configuration.max_output_bytes,
                process_count=configuration.max_process_count,
            ),
        )
    else:
        code, live, pricing, planner, activation = _live_activation(args, configuration)
        if activation is not None:
            # ADR-0057 §3: the activation observation is retained whether it
            # passed or failed, and before anything else can consume it.
            root.mkdir(parents=True, exist_ok=True)
            try:
                _write_once(
                    root / "activation.json", canonical_bytes(activation) + b"\n",
                )
            except (CampaignConfigurationError, OSError) as error:
                return _refuse(str(error))
        if code != 0 and activation is None:
            return code
        if activation is not None and activation.probe_status != "passed":
            if activation.probe_request_hash is None:
                # No request left the process, so there is no model attempt to
                # retain: `requests_attempted` is zero, not one.
                return _refuse(
                    REFUSAL_ACTIVATION_NOT_EXECUTED,
                    failure_classification=activation.failure_classification,
                    requests_attempted=activation.requests_attempted,
                    terminal_reason=REFUSAL_ACTIVATION_NOT_EXECUTED,
                )
            artifacts = FileArtifactStore(root / "artifacts")
            try:
                export = _activation_failure_ledger(
                    campaign_id=args.campaign_id, target_hash=target_hash,
                    configuration_hash=configuration.content_hash,
                    activation=activation, artifacts=artifacts,
                )
                _write_once(root / "target.json", target_content)
                _write_once(root / "campaign-config.json", args.config.read_bytes())
                _write_once(
                    root / "novelty-recheck.json", args.novelty_recheck.read_bytes(),
                )
                facts = campaign_facts(export, recheck)
                _write_once(root / "campaign.json", export_campaign_bytes(export))
                _write_once(
                    root / "campaign-facts.json", canonical_bytes(facts) + b"\n",
                )
            except (CampaignProvenanceError, CampaignConfigurationError, OSError) as error:
                return _refuse(str(error))
            _print({
                "status": "refused",
                "reason": REFUSAL_ACTIVATION_FAILED,
                "terminal_reason": REFUSAL_ACTIVATION_FAILED,
                "fallback_gateway_used": False,
                "failure_classification": activation.failure_classification,
                "root": str(root),
                "facts": facts,
            })
            return 2
        if code != 0 or planner is None:
            return code if code != 0 else _refuse(REFUSAL_ACTIVATION_FAILED)
        live_configuration_hash = live.content_hash
        pricing_snapshot_hash = pricing.content_hash

    root.mkdir(parents=True, exist_ok=True)
    artifacts = FileArtifactStore(root / "artifacts")
    try:
        completed = SequentialCampaignRunner(
            campaign_id=args.campaign_id,
            target_hash=target_hash,
            configuration_hash=configuration.content_hash,
            live_configuration_hash=live_configuration_hash,
            pricing_snapshot_hash=pricing_snapshot_hash,
            planner_actor_id=args.planner_actor_id,
            planner=planner,
            experiment_runner=experiment,
            artifacts=artifacts,
            verifier=verifier,
            policy=runner_policy(configuration),
            recorded_at=lambda: args.recorded_at,
        ).run()
        export = build_campaign_export(
            campaign_id=completed.campaign_id, target_hash=target_hash,
            configuration_hash=configuration.content_hash,
            actions=completed.actions, model_calls=completed.model_calls,
            tool_runs=completed.tool_runs,
        )
        facts = campaign_facts(export, recheck)
        _write_once(root / "target.json", target_content)
        _write_once(root / "campaign-config.json", args.config.read_bytes())
        _write_once(root / "novelty-recheck.json", args.novelty_recheck.read_bytes())
        if activation is not None:
            _write_once(root / "activation.json", canonical_bytes(activation) + b"\n")
        _write_once(root / "campaign.json", export_campaign_bytes(export))
        _write_once(root / "campaign-facts.json", canonical_bytes(facts) + b"\n")
    except (
        CampaignRunnerError, CampaignProvenanceError, CampaignConfigurationError, OSError,
    ) as error:
        # `SequentialCampaignRunner.run` raises rather than returning a partial
        # run, so an in-flight rejection discards the in-memory ledger. ADR-0065
        # records that as a known gap; this module does not change `runner.py`.
        return _refuse(REFUSAL_RUNNER_REJECTED, detail=str(error))

    violations = sorted(
        name for name, observed, cap in (
            ("max_model_calls", int(export.usage["requests_attempted"]), configuration.max_model_calls),
            ("max_tool_runs", int(export.usage["tool_runs_attempted"]), configuration.max_tool_runs),
            ("max_input_tokens", int(export.usage["input_tokens"]), configuration.max_input_tokens),
            ("max_output_tokens", int(export.usage["output_tokens"]), configuration.max_output_tokens),
            ("max_cost_microusd", int(export.usage["estimated_cost_microusd"]), configuration.max_cost_microusd),
        ) if observed > cap
    )
    payload = {
        "campaign_id": completed.campaign_id,
        "terminal_reason": completed.terminal_reason,
        "provider": args.provider,
        "root": str(root),
        "epistemic_warrant_created": completed.epistemic_warrant_created,
        "facts": facts,
    }
    if violations:
        _print({
            "status": "refused", "reason": REFUSAL_BOUND_VIOLATION,
            "exceeded_bounds": violations, **payload,
        })
        return 2
    _print({"status": "recorded", **payload})
    return 0


@dataclass(frozen=True, slots=True)
class LoadedCampaign:
    export: Any
    facts: dict[str, Any]
    stored_facts: dict[str, Any]
    checks: tuple[tuple[str, bool], ...]


def _load_campaign(root: Path) -> LoadedCampaign:
    raw = (root / "campaign.json").read_bytes()
    export = verify_campaign_export(raw)
    checks: list[tuple[str, bool]] = [
        ("campaign_export_canonical_and_closed", True),
    ]
    target_content = (root / "target.json").read_bytes()
    if _raw_hash(target_content) != export.target_hash:
        raise CampaignProvenanceError(REFUSAL_TARGET_MISMATCH)
    checks.append(("target_record_hashes_to_ledger_target", True))
    configuration = load_campaign_configuration(root / "campaign-config.json")
    if configuration.content_hash != export.configuration_hash:
        raise CampaignProvenanceError(REFUSAL_CONFIG_MISMATCH)
    checks.append(("configuration_hash_matches_ledger", True))
    recheck = read_recheck(root / "novelty-recheck.json")
    target_record = _strict_json(target_content, what="campaign target")
    if (
        recheck.checkpoint != "before_research"
        or recheck.subject_id != target_record["problem_id"]
        or recheck.subject_hash != target_record["dossier_content_hash"]
        or recheck.next_action_id != export.campaign_id
    ):
        raise NoveltyRecheckError("campaign_novelty_recheck_binding_mismatch")
    checks.append(("novelty_recheck_bound_to_target_and_campaign", True))
    derived = campaign_facts(export, recheck)
    stored = _strict_json((root / "campaign-facts.json").read_bytes(), what="campaign facts")
    if not isinstance(stored, dict) or stored != derived:
        raise CampaignProvenanceError(REFUSAL_FACTS_MISMATCH)
    checks.append(("facts_are_derived_from_the_ledger", True))
    if dict(export.usage) != derive_usage(
        export.model_calls, export.tool_runs, export.imports,
    ):
        raise CampaignProvenanceError("campaign usage is not derived from its records")
    checks.append(("usage_rollups_recomputed_from_records", True))
    return LoadedCampaign(
        export=export, facts=derived, stored_facts=stored, checks=tuple(checks),
    )


def _inspect(args: argparse.Namespace) -> int:
    try:
        loaded = _load_campaign(args.root)
    except (
        CampaignProvenanceError, CampaignConfigurationError, NoveltyRecheckError, OSError,
        KeyError, TypeError,
    ) as error:
        return _refuse(str(error) or type(error).__name__)
    _print({"status": "verified", "root": str(args.root), **loaded.facts})
    return 0


def _replay(args: argparse.Namespace) -> int:
    """Validate closure and derive the report without invoking a model or tool."""

    try:
        loaded = _load_campaign(args.root)
        store = FileArtifactStore(args.root / "artifacts")
        hashes = _artifact_hashes(loaded.export)
        for content_hash in hashes:
            path = store.path_for(content_hash)
            if not path.exists():
                raise CampaignProvenanceError(
                    f"{REFUSAL_ARTIFACT_MISSING}: {content_hash}"
                )
            if _raw_hash(path.read_bytes()) != content_hash:
                raise CampaignProvenanceError(
                    f"{REFUSAL_ARTIFACT_BYTES}: {content_hash}"
                )
    except (
        CampaignProvenanceError, CampaignConfigurationError, CampaignRunnerError,
        NoveltyRecheckError, OSError, KeyError, TypeError,
    ) as error:
        return _refuse(str(error) or type(error).__name__)
    checks = [
        {"name": name, "passed": passed} for name, passed in loaded.checks
    ]
    checks.append({"name": "every_ledger_artifact_resolves_in_the_store", "passed": True})
    _print({
        "schema_version": CAMPAIGN_REPLAY_SCHEMA_VERSION,
        "verified": True,
        "root": str(args.root),
        "checks": checks,
        "artifacts_resolved": len(hashes),
        "model_calls_made": 0,
        "provider_requests_made": 0,
        "tool_calls_made": 0,
        "subprocesses_opened": 0,
        "network_requests": 0,
        "epistemic_warrant_created": False,
        "facts": loaded.facts,
    })
    return 0


def _export(args: argparse.Namespace) -> int:
    try:
        loaded = _load_campaign(args.root)
        content = export_campaign_bytes(loaded.export)
        _write_once(args.output, content)
    except (
        CampaignProvenanceError, CampaignConfigurationError, NoveltyRecheckError, OSError,
        KeyError, TypeError,
    ) as error:
        return _refuse(str(error) or type(error).__name__)
    _print({
        "status": "written",
        "path": str(args.output),
        "campaign_id": loaded.export.campaign_id,
        "content_hash": loaded.export.content_hash,
        "operational_hash": loaded.export.operational_hash,
        "bytes": len(content),
        "consumed_by": "publication build --campaign-export",
    })
    return 0


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="campaign", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser(
        "config-create", help="write a content-hashed campaign bounds artifact"
    )
    create.add_argument("output", type=Path)
    create.add_argument("--campaign-configuration-id", required=True)
    create.add_argument("--allowed-tool", action="append", required=True)
    for name, _ in _CONFIG_BOUNDS:
        create.add_argument("--" + name.replace("_", "-"), type=int, required=True)

    target = commands.add_parser(
        "target", help="freeze and write the campaign target record"
    )
    target.add_argument("output", type=Path)
    target.add_argument("--problem", type=Path)
    target.add_argument("--instant", default="2026-08-21T00:00:00+00:00")

    run = commands.add_parser("run", help="drive one bounded campaign to a terminal action")
    run.add_argument("root", type=Path)
    run.add_argument("campaign_id")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--recorded-at", required=True)
    run.add_argument("--novelty-recheck", type=Path)
    run.add_argument("--problem", type=Path)
    run.add_argument("--instant", default="2026-08-21T00:00:00+00:00")
    run.add_argument("--provider", default=FIXTURE_PROVIDER)
    run.add_argument("--planner-actor-id", default="model.central-lead")
    run.add_argument("--fixture-script", choices=FIXTURE_SCRIPTS, default=FIXTURE_SCRIPTS[0])
    run.add_argument("--live-config", type=Path)
    run.add_argument("--pricing-snapshot", type=Path)
    run.add_argument("--activation-acknowledgement", default="")
    run.add_argument(
        "--action-schema", type=Path,
        default=Path("schemas/model-campaign-action-v1.schema.json"),
    )
    run.add_argument("--execute", action="store_true")

    inspect = commands.add_parser("inspect", help="verify and inspect a persisted campaign")
    inspect.add_argument("root", type=Path)

    replay = commands.add_parser(
        "replay", help="verify campaign closure with zero model and tool calls"
    )
    replay.add_argument("root", type=Path)

    export = commands.add_parser(
        "export", help="write the canonical campaign bytes publication consumes"
    )
    export.add_argument("root", type=Path)
    export.add_argument("output", type=Path)

    args = parser.parse_args(argv)
    if args.command == "config-create":
        return _config_create(args)
    if args.command == "target":
        return _target(args)
    if args.command == "run":
        return _run(args)
    if args.command == "inspect":
        return _inspect(args)
    if args.command == "replay":
        return _replay(args)
    if args.command == "export":
        return _export(args)
    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
