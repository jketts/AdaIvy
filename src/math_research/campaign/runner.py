"""Bounded sequential planner/program/tool campaign loop.

Every effectful boundary is injected.  This module imports no subprocess or
network package and never executes model-authored source itself.  It records the
source as an artifact and model-call result before an admitted experiment port
can receive a request for that program.

A rejected action is terminal and RETAINED rather than raised: `run` returns the
partial ledger with `terminal_reason == "action_rejected"` and a `failed`
action naming the refused planner output.  See `SequentialCampaignRunner.run`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from .records import (
    ActionRecord,
    ActionType,
    ActorType,
    CampaignProvenanceError,
    ModelCallRecord,
    RecordStatus,
    ToolRunRecord,
    UsageSource,
    canonical_bytes,
    canonical_hash,
)


ACTION_SCHEMA_VERSION = "1.0.0"
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_SAFE_ARGUMENT = re.compile(r"^[A-Za-z0-9_.:=+,-]{0,128}$")
_ACTION_FIELDS = frozenset({
    "schema_version", "action_type", "branch_id", "rationale", "artifact_text",
    "program_source", "tool_request", "selected_candidate_hash",
    "selected_tool_artifact_hashes", "report_text",
})
_TOOL_FIELDS = frozenset({
    "tool_id", "program_artifact_hash", "input_artifact_hashes", "arguments",
    "resource_limits", "network",
})
_RESOURCE_FIELDS = frozenset({
    "cpu_milliseconds", "wall_milliseconds", "memory_bytes", "output_bytes",
    "process_count",
})
_SUPPORTED_ACTIONS = frozenset({
    ActionType.DERIVE, ActionType.WRITE_PROGRAM, ActionType.RUN_PROGRAM,
    ActionType.INSPECT_RESULT, ActionType.FALSIFY, ActionType.VERIFY,
    ActionType.ASK_USER, ActionType.SUSPEND_BRANCH, ActionType.REPORT,
})


class CampaignRunnerError(CampaignProvenanceError):
    """A planner action or effect request was rejected before execution."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceLimits:
    cpu_milliseconds: int
    wall_milliseconds: int
    memory_bytes: int
    output_bytes: int
    process_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolRequest:
    tool_id: str
    program_artifact_hash: str
    input_artifact_hashes: tuple[str, ...]
    arguments: tuple[str, ...]
    resource_limits: ResourceLimits
    network: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignAction:
    action_type: ActionType
    branch_id: str
    rationale: str
    artifact_text: str | None
    program_source: str | None
    tool_request: ToolRequest | None
    selected_candidate_hash: str | None
    selected_tool_artifact_hashes: tuple[str, ...]
    report_text: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannerContext:
    campaign_id: str
    target_hash: str
    configuration_hash: str
    sequence: int
    previous_action_id: str | None
    available_artifact_hashes: tuple[str, ...]
    recorded_program_hashes: tuple[str, ...]
    selected_candidate_hash: str | None
    selected_tool_artifact_hashes: tuple[str, ...]
    latest_tool_result_hash: str | None
    latest_tool_result: bytes | None
    actions_remaining: int
    tool_runs_remaining: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannerResponse:
    action_json: bytes
    provider: str
    model_identifier: str
    status: RecordStatus
    usage_source: UsageSource
    input_tokens: int
    output_tokens: int
    estimated_cost_microusd: int | None
    provider_request_id: str | None


class PlannerPort(Protocol):
    def __call__(self, context: PlannerContext) -> PlannerResponse: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentRequest:
    campaign_id: str
    action_id: str
    tool_id: str
    program_artifact_hash: str
    program_source: bytes
    input_artifacts: tuple[tuple[str, bytes], ...]
    arguments: tuple[str, ...]
    resource_limits: ResourceLimits
    network: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentResult:
    adapter_id: str
    adapter_version: str
    adapter_configuration_hash: str
    environment_hash: str
    status: RecordStatus
    result: bytes
    stdout: bytes
    stderr: bytes
    measurement_source: UsageSource
    cpu_milliseconds: int | None
    wall_milliseconds: int | None
    peak_memory_bytes: int | None
    output_bytes: int | None


class CampaignExperimentRunner(Protocol):
    def __call__(self, request: ExperimentRequest) -> ExperimentResult: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class VerificationRequest:
    campaign_id: str
    action_id: str
    target_hash: str
    candidate_artifact: tuple[str, bytes]
    tool_artifacts: tuple[tuple[str, bytes], ...]


class VerifierPort(Protocol):
    def __call__(self, request: VerificationRequest) -> ExperimentResult: ...


class ArtifactStore(Protocol):
    def put(self, content: bytes, *, media_type: str) -> str: ...
    def get(self, content_hash: str) -> bytes: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignRunnerPolicy:
    allowed_tools: frozenset[str]
    max_actions: int
    max_tool_runs: int
    max_program_bytes: int
    max_artifact_bytes: int
    max_cpu_milliseconds: int
    max_wall_milliseconds: int
    max_memory_bytes: int
    max_output_bytes: int
    max_process_count: int

    def __post_init__(self) -> None:
        if not self.allowed_tools or any(not _IDENTIFIER.fullmatch(v) for v in self.allowed_tools):
            raise CampaignRunnerError("allowed_tools must contain valid tool identifiers")
        for name in (
            "max_actions", "max_tool_runs", "max_program_bytes", "max_artifact_bytes",
            "max_cpu_milliseconds", "max_wall_milliseconds", "max_memory_bytes",
            "max_output_bytes", "max_process_count",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise CampaignRunnerError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignRun:
    campaign_id: str
    terminal_reason: str
    actions: tuple[ActionRecord, ...]
    model_calls: tuple[ModelCallRecord, ...]
    tool_runs: tuple[ToolRunRecord, ...]
    selected_candidate_hash: str | None
    selected_tool_artifact_hashes: tuple[str, ...]
    report_artifact_hash: str | None
    epistemic_warrant_created: bool = False


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CampaignRunnerError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _exact(value: Mapping[str, Any], fields: frozenset[str], name: str) -> None:
    if frozenset(value) != fields:
        raise CampaignRunnerError(f"{name} fields differ from the closed schema")


def _hash_value(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise CampaignRunnerError(f"{field} must be a sha256 content hash")
    return value


def _optional_hash(value: object, field: str) -> str | None:
    return None if value is None else _hash_value(value, field)


def _bounded_text(value: object, field: str, maximum: int, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum:
        raise CampaignRunnerError(f"{field} must be non-empty and at most {maximum} bytes")
    return value


def _hash_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) != len(set(value)):
        raise CampaignRunnerError(f"{field} must be an array of unique hashes")
    return tuple(_hash_value(item, field) for item in value)


def _positive(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CampaignRunnerError(f"{field} must be a positive integer")
    return value


def _parse_tool_request(value: object) -> ToolRequest:
    if not isinstance(value, dict):
        raise CampaignRunnerError("tool_request must be an object")
    _exact(value, _TOOL_FIELDS, "tool_request")
    tool_id = value["tool_id"]
    if not isinstance(tool_id, str) or not _IDENTIFIER.fullmatch(tool_id):
        raise CampaignRunnerError("tool_id must be a valid identifier")
    arguments = value["arguments"]
    if not isinstance(arguments, list) or any(
        not isinstance(item, str) or not _SAFE_ARGUMENT.fullmatch(item)
        or item in {"..", "."} or ".." in item or "/" in item or "\\" in item or "~" in item
        for item in arguments
    ):
        raise CampaignRunnerError("arguments contain a host path or unsupported value")
    resources = value["resource_limits"]
    if not isinstance(resources, dict):
        raise CampaignRunnerError("resource_limits must be an object")
    _exact(resources, _RESOURCE_FIELDS, "resource_limits")
    network = value["network"]
    if network != "none":
        raise CampaignRunnerError("network must be exactly 'none'")
    return ToolRequest(
        tool_id=tool_id,
        program_artifact_hash=_hash_value(
            value["program_artifact_hash"], "program_artifact_hash",
        ),
        input_artifact_hashes=_hash_tuple(
            value["input_artifact_hashes"], "input_artifact_hashes",
        ),
        arguments=tuple(arguments),
        resource_limits=ResourceLimits(**{
            key: _positive(resources[key], f"resource_limits.{key}")
            for key in sorted(_RESOURCE_FIELDS)
        }),
        network=network,
    )


def parse_campaign_action(raw: bytes | str) -> CampaignAction:
    """Parse the closed planner action schema without trusting an SDK projection."""

    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        value = json.loads(text, object_pairs_hook=_pairs_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CampaignRunnerError("planner action is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise CampaignRunnerError("planner action must be an object")
    _exact(value, _ACTION_FIELDS, "planner action")
    if value["schema_version"] != ACTION_SCHEMA_VERSION:
        raise CampaignRunnerError("unsupported planner action schema_version")
    try:
        action_type = ActionType(value["action_type"])
    except (TypeError, ValueError) as error:
        raise CampaignRunnerError("unknown campaign action") from error
    if action_type not in _SUPPORTED_ACTIONS:
        raise CampaignRunnerError("campaign action is not executable in this runner")
    branch = value["branch_id"]
    if not isinstance(branch, str) or not _IDENTIFIER.fullmatch(branch):
        raise CampaignRunnerError("branch_id must be a valid identifier")
    rationale = _bounded_text(value["rationale"], "rationale", 2_000)
    artifact = _bounded_text(value["artifact_text"], "artifact_text", 262_144, optional=True)
    program = _bounded_text(value["program_source"], "program_source", 262_144, optional=True)
    report = _bounded_text(value["report_text"], "report_text", 65_536, optional=True)
    selected = _optional_hash(value["selected_candidate_hash"], "selected_candidate_hash")
    selected_tools = _hash_tuple(
        value["selected_tool_artifact_hashes"], "selected_tool_artifact_hashes",
    )
    tool = None if value["tool_request"] is None else _parse_tool_request(value["tool_request"])

    empty = (artifact is None, program is None, tool is None, selected is None, not selected_tools, report is None)
    if action_type in {ActionType.DERIVE, ActionType.FALSIFY}:
        if empty != (False, True, True, True, True, True):
            raise CampaignRunnerError(f"{action_type.value} carries forbidden or missing fields")
    elif action_type is ActionType.WRITE_PROGRAM:
        if empty != (True, False, True, True, True, True):
            raise CampaignRunnerError("write_program carries forbidden or missing fields")
    elif action_type is ActionType.RUN_PROGRAM:
        if empty != (True, True, False, True, True, True):
            raise CampaignRunnerError("run_program carries forbidden or missing fields")
    elif action_type is ActionType.INSPECT_RESULT:
        if program is not None or tool is not None or report is not None:
            raise CampaignRunnerError("inspect_result carries forbidden fields")
        if (artifact is None) == (selected is None):
            raise CampaignRunnerError("inspect_result must create or select exactly one candidate")
    elif action_type is ActionType.VERIFY:
        if empty[:3] != (True, True, True) or selected is None or report is not None:
            raise CampaignRunnerError("verify carries forbidden or missing fields")
    else:
        if empty != (True, True, True, True, True, False):
            raise CampaignRunnerError(f"{action_type.value} carries forbidden or missing fields")
    return CampaignAction(
        action_type=action_type, branch_id=branch, rationale=rationale or "",
        artifact_text=artifact, program_source=program, tool_request=tool,
        selected_candidate_hash=selected,
        selected_tool_artifact_hashes=selected_tools, report_text=report,
    )


def _raw_hash(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


class SequentialCampaignRunner:
    def __init__(
        self,
        *,
        campaign_id: str,
        target_hash: str,
        configuration_hash: str,
        live_configuration_hash: str,
        pricing_snapshot_hash: str,
        planner_actor_id: str,
        planner: PlannerPort,
        experiment_runner: CampaignExperimentRunner,
        artifacts: ArtifactStore,
        verifier: VerifierPort,
        policy: CampaignRunnerPolicy,
        recorded_at: Callable[[], str],
    ) -> None:
        for value, name in ((campaign_id, "campaign_id"), (planner_actor_id, "planner_actor_id")):
            if not _IDENTIFIER.fullmatch(value):
                raise CampaignRunnerError(f"{name} must be a valid identifier")
        for value, name in (
            (target_hash, "target_hash"), (configuration_hash, "configuration_hash"),
            (live_configuration_hash, "live_configuration_hash"),
            (pricing_snapshot_hash, "pricing_snapshot_hash"),
        ):
            _hash_value(value, name)
        self.campaign_id = campaign_id
        self.target_hash = target_hash
        self.configuration_hash = configuration_hash
        self.live_configuration_hash = live_configuration_hash
        self.pricing_snapshot_hash = pricing_snapshot_hash
        self.planner_actor_id = planner_actor_id
        self.planner = planner
        self.experiment_runner = experiment_runner
        self.artifacts = artifacts
        self.verifier = verifier
        self.policy = policy
        self.recorded_at = recorded_at

    def run(self) -> CampaignRun:
        """Drive one bounded campaign to a terminal action.

        A rejected planner action is terminal but is never silent: the planner
        output that was rejected is already stored as an artifact, so the
        rejection is recorded as a `failed` action naming its own model call and
        that artifact, `terminal_reason` becomes `action_rejected`, and the
        partial run is RETURNED.  Raising here would leave model-authored bytes
        on disk with no record of who wrote them, which is exactly the loss of a
        failed attempt that AGENTS.md forbids.  A rejection that cannot itself be
        recorded -- a planner result larger than the artifact bound -- still
        raises, because there is no way to name it without breaching the bound
        that rejected it.
        """

        actions: list[ActionRecord] = []
        calls: list[ModelCallRecord] = []
        tools: list[ToolRunRecord] = []
        available = {self.target_hash, self.configuration_hash}
        programs: set[str] = set()
        candidates: set[str] = set()
        tool_artifacts: set[str] = set()
        verifier_private_artifacts: set[str] = set()
        suspended: set[str] = set()
        selected_candidate: str | None = None
        selected_tools: tuple[str, ...] = ()
        latest_tool_result: bytes | None = None
        latest_tool_hash: str | None = None
        report_hash: str | None = None
        terminal = "bounds_exhausted"
        first_sequence = 1

        activation = getattr(self.planner, "activation", None)
        if activation is not None:
            if self.policy.max_actions < 2:
                raise CampaignRunnerError("campaign action bound leaves no research action")
            if (
                activation.probe_status != "passed"
                or activation.operational_readiness != "passed"
                or activation.configuration_hash != self.live_configuration_hash
                or activation.pricing_snapshot_hash != self.pricing_snapshot_hash
                or activation.probe_request_hash is None
            ):
                raise CampaignRunnerError("campaign provider activation is absent or mismatched")
            activation_bytes = canonical_bytes(activation)
            activation_hash = self._store(
                activation_bytes,
                media_type="application/vnd.adaivy.provider-activation+json",
            )
            usage_reported = activation.usage_reported_calls == 1
            calls.append(ModelCallRecord(
                call_id="call.activation", campaign_id=self.campaign_id,
                action_id="action.activation", purpose="provider_activation",
                provider=activation.provider,
                model_identifier=activation.model_identifier,
                live_configuration_hash=self.live_configuration_hash,
                pricing_snapshot_hash=self.pricing_snapshot_hash,
                request_hash=activation.probe_request_hash,
                result_hash=activation_hash, status=RecordStatus.COMPLETED,
                usage_source=(
                    UsageSource.API_REPORTED if usage_reported
                    else UsageSource.UNAVAILABLE
                ),
                input_tokens=activation.input_tokens if usage_reported else 0,
                output_tokens=activation.output_tokens if usage_reported else 0,
                estimated_cost_microusd=(
                    activation.estimated_cost_microusd if usage_reported else None
                ),
                provider_request_id=activation.provider_request_id,
                recorded_at=activation.observed_at,
            ).finalized())
            actions.append(ActionRecord(
                action_id="action.activation", campaign_id=self.campaign_id,
                sequence=1, branch_id="branch.system",
                action_type=ActionType.PLAN, actor_type=ActorType.SYSTEM,
                actor_id="system.provider-activation", parent_action_ids=(),
                input_artifact_hashes=(self.target_hash, self.configuration_hash),
                source_record_ids=("call.activation",),
                output_artifact_hashes=(activation_hash,),
                status=RecordStatus.COMPLETED,
                declared_rationale=(
                    "One no-retry provider activation passed before mathematical work."
                ),
                recorded_at=activation.observed_at,
            ).finalized())
            available.add(activation_hash)
            first_sequence = 2

        for sequence in range(first_sequence, self.policy.max_actions + 1):
            context = PlannerContext(
                campaign_id=self.campaign_id, target_hash=self.target_hash,
                configuration_hash=self.configuration_hash, sequence=sequence,
                previous_action_id=actions[-1].action_id if actions else None,
                available_artifact_hashes=tuple(sorted(available)),
                recorded_program_hashes=tuple(sorted(programs)),
                selected_candidate_hash=selected_candidate,
                selected_tool_artifact_hashes=selected_tools,
                latest_tool_result_hash=latest_tool_hash,
                latest_tool_result=latest_tool_result,
                actions_remaining=self.policy.max_actions - sequence + 1,
                tool_runs_remaining=self.policy.max_tool_runs - len(tools),
            )
            response = self.planner(context)
            action_id = f"action.{sequence}"
            call_id = f"call.{sequence}"
            # A mid-loop rejection must not discard the ledger: `_store` has
            # already written model-authored bytes to the artifact store by the
            # time most of these checks run, and AGENTS.md requires the failed
            # attempt to survive in machine-readable output.  The rejection is
            # therefore recorded as a terminal action and the partial run is
            # returned, rather than raised past the caller.
            source_hash: str | None = None
            try:
                if response.status is not RecordStatus.COMPLETED:
                    source = response.action_json or b'{"planner_result":"unavailable"}'
                    if len(source) > self.policy.max_artifact_bytes:
                        raise CampaignRunnerError("failed planner result exceeds campaign byte bound")
                    source_hash = self._store(
                        source, media_type="application/vnd.adaivy.campaign-planner-result+json",
                    )
                    call = self._model_call(
                        call_id=call_id, action_id=action_id, response=response,
                        request_hash=self._planner_request_hash(context), result_hash=source_hash,
                    )
                    calls.append(call)
                    inputs = (
                        actions[-1].output_artifact_hashes
                        if actions else (self.target_hash, self.configuration_hash)
                    )
                    actions.append(ActionRecord(
                        action_id=action_id, campaign_id=self.campaign_id, sequence=sequence,
                        branch_id="branch.system", action_type=ActionType.PLAN,
                        actor_type=ActorType.MODEL, actor_id=self.planner_actor_id,
                        parent_action_ids=((actions[-1].action_id,) if actions else ()),
                        input_artifact_hashes=inputs, source_record_ids=(call_id,),
                        output_artifact_hashes=(source_hash,), status=response.status,
                        declared_rationale=(
                            "Planner call ended before an executable action was admitted."
                        ),
                        recorded_at=self.recorded_at(),
                    ).finalized())
                    terminal = "planner_" + response.status.value
                    break

                action = parse_campaign_action(response.action_json)
                if action.branch_id in suspended:
                    raise CampaignRunnerError("planner selected a suspended branch")

                source, media_type = self._model_source(action, response.action_json)
                if len(source) > self.policy.max_artifact_bytes:
                    raise CampaignRunnerError("model artifact exceeds campaign byte bound")
                source_hash = self._store(source, media_type=media_type)
                # The exact tool bytes are bound through their content hash.  They
                # remain present in the in-memory planner context but are not passed
                # to the generic JSON serializer, which deliberately has no bytes
                # encoding convention.
                call = self._model_call(
                    call_id=call_id, action_id=action_id, response=response,
                    request_hash=self._planner_request_hash(context), result_hash=source_hash,
                )
                # This append precedes every effectful program/verifier call.
                calls.append(call)

                source_ids = [call_id]
                outputs = [source_hash]
                action_status = RecordStatus.COMPLETED
                inputs = self._inputs(
                    action, actions, source_hash=source_hash, selected_candidate=selected_candidate,
                    selected_tools=selected_tools, available=available,
                )
                if (
                    action.action_type is ActionType.RUN_PROGRAM
                    and action.tool_request is not None
                    and action.tool_request.program_artifact_hash not in programs
                ):
                    raise CampaignRunnerError("only a prior recorded program may run")
                if not set(inputs).issubset(available | {source_hash}):
                    raise CampaignRunnerError("planner selected an artifact outside campaign provenance")

                if action.action_type is ActionType.WRITE_PROGRAM:
                    assert action.program_source is not None
                    if len(action.program_source.encode("utf-8")) > self.policy.max_program_bytes:
                        raise CampaignRunnerError("program exceeds campaign byte bound")
                    programs.add(source_hash)
                elif action.action_type in {ActionType.DERIVE, ActionType.FALSIFY}:
                    candidates.add(source_hash)
                elif action.action_type is ActionType.RUN_PROGRAM:
                    request = self._admit_experiment(action, action_id, programs, available, tools)
                    result = self.experiment_runner(request)
                    tool, artifact_hashes = self._record_tool(
                        action_id, len(tools) + 1, result,
                        request_hash=canonical_hash({
                            "campaign_id": request.campaign_id,
                            "action_id": request.action_id,
                            "tool_id": request.tool_id,
                            "program_artifact_hash": request.program_artifact_hash,
                            "input_artifact_hashes": tuple(
                                item[0] for item in request.input_artifacts
                            ),
                            "arguments": request.arguments,
                            "resource_limits": request.resource_limits,
                            "network": request.network,
                        }),
                    )
                    tools.append(tool)
                    source_ids.append(tool.tool_run_id)
                    outputs.extend(artifact_hashes)
                    available.update(artifact_hashes)
                    tool_artifacts.update(artifact_hashes)
                    latest_tool_hash = tool.result_hash
                    latest_tool_result = result.result
                    action_status = result.status
                elif action.action_type is ActionType.INSPECT_RESULT:
                    if action.selected_tool_artifact_hashes and not set(
                        action.selected_tool_artifact_hashes
                    ).issubset(tool_artifacts):
                        raise CampaignRunnerError("inspection selected a non-tool artifact")
                    chosen = source_hash if action.artifact_text is not None else action.selected_candidate_hash
                    assert chosen is not None
                    if chosen != source_hash and chosen not in candidates:
                        raise CampaignRunnerError("inspection selected an unrecorded candidate")
                    candidates.add(chosen)
                    selected_candidate = chosen
                    selected_tools = action.selected_tool_artifact_hashes
                elif action.action_type is ActionType.VERIFY:
                    if len(tools) >= self.policy.max_tool_runs:
                        raise CampaignRunnerError("campaign tool-run bound exhausted")
                    if action.selected_candidate_hash != selected_candidate:
                        raise CampaignRunnerError("verifier candidate differs from the inspected selection")
                    if action.selected_tool_artifact_hashes != selected_tools:
                        raise CampaignRunnerError("verifier tool artifacts differ from the inspected selection")
                    if selected_candidate is None or selected_candidate not in candidates:
                        raise CampaignRunnerError("no recorded candidate is selected for verification")
                    verification = VerificationRequest(
                        campaign_id=self.campaign_id, action_id=action_id,
                        target_hash=self.target_hash,
                        candidate_artifact=(selected_candidate, self.artifacts.get(selected_candidate)),
                        tool_artifacts=tuple(
                            (item, self.artifacts.get(item)) for item in selected_tools
                        ),
                    )
                    result = self.verifier(verification)
                    tool, artifact_hashes = self._record_tool(
                        action_id, len(tools) + 1, result,
                        request_hash=canonical_hash({
                            "campaign_id": verification.campaign_id,
                            "action_id": verification.action_id,
                            "target_hash": verification.target_hash,
                            "candidate_artifact_hash": verification.candidate_artifact[0],
                            "tool_artifact_hashes": tuple(
                                item[0] for item in verification.tool_artifacts
                            ),
                        }),
                    )
                    tools.append(tool)
                    source_ids.append(tool.tool_run_id)
                    outputs.extend(artifact_hashes)
                    verifier_private_artifacts.update(artifact_hashes)
                    action_status = result.status
                elif action.action_type is ActionType.SUSPEND_BRANCH:
                    suspended.add(action.branch_id)
                elif action.action_type is ActionType.ASK_USER:
                    terminal = "awaiting_user"
                elif action.action_type is ActionType.REPORT:
                    report_hash = source_hash
                    terminal = "reported"

                record = ActionRecord(
                    action_id=action_id, campaign_id=self.campaign_id, sequence=sequence,
                    branch_id=action.branch_id, action_type=action.action_type,
                    actor_type=ActorType.MODEL, actor_id=self.planner_actor_id,
                    parent_action_ids=((actions[-1].action_id,) if actions else ()),
                    input_artifact_hashes=tuple(dict.fromkeys(inputs)),
                    source_record_ids=tuple(source_ids),
                    output_artifact_hashes=tuple(dict.fromkeys(outputs)),
                    status=action_status, declared_rationale=action.rationale,
                    recorded_at=self.recorded_at(),
                ).finalized()
                actions.append(record)
                available.update(
                    item for item in record.output_artifact_hashes
                    if item not in verifier_private_artifacts
                )
                if (
                    action.action_type is ActionType.RUN_PROGRAM
                    and action_status is not RecordStatus.COMPLETED
                ):
                    # ADR-0066: a sandbox failure is terminal. Its diagnostic
                    # is retained but never fed back as repair guidance.
                    terminal = "experiment_failed"
                    break
                if action.action_type in {ActionType.ASK_USER, ActionType.REPORT}:
                    break
            except CampaignRunnerError as rejection:
                if source_hash is None:
                    rejected = response.action_json or b'{"planner_result":"unavailable"}'
                    if len(rejected) > self.policy.max_artifact_bytes:
                        # Storing it would breach the same bound that rejected it.
                        raise
                    source_hash = self._store(
                        rejected,
                        media_type=(
                            "application/vnd.adaivy.campaign-planner-result+json"
                        ),
                    )
                if all(item.call_id != call_id for item in calls):
                    calls.append(self._model_call(
                        call_id=call_id, action_id=action_id, response=response,
                        request_hash=self._planner_request_hash(context),
                        result_hash=source_hash,
                    ))
                # Closure needs every source record used by exactly one action, so
                # a tool run already appended for this action is named here too.
                rejected_sources = [call_id]
                rejected_outputs = [source_hash]
                for item in tools:
                    if item.action_id == action_id:
                        rejected_sources.append(item.tool_run_id)
                        rejected_outputs.extend(
                            (item.result_hash, item.stdout_hash, item.stderr_hash)
                        )
                actions.append(ActionRecord(
                    action_id=action_id, campaign_id=self.campaign_id,
                    sequence=sequence, branch_id="branch.system",
                    action_type=ActionType.PLAN, actor_type=ActorType.SYSTEM,
                    actor_id="system.campaign-runner",
                    parent_action_ids=((actions[-1].action_id,) if actions else ()),
                    input_artifact_hashes=(
                        actions[-1].output_artifact_hashes if actions
                        else (self.target_hash, self.configuration_hash)
                    ),
                    source_record_ids=tuple(rejected_sources),
                    output_artifact_hashes=tuple(dict.fromkeys(rejected_outputs)),
                    status=RecordStatus.FAILED,
                    declared_rationale=(
                        "The campaign runner rejected this planner action and the "
                        "campaign is terminal: " + str(rejection)[:1_000]
                    ),
                    recorded_at=self.recorded_at(),
                ).finalized())
                terminal = "action_rejected"
                break

        return CampaignRun(
            campaign_id=self.campaign_id, terminal_reason=terminal,
            actions=tuple(actions), model_calls=tuple(calls), tool_runs=tuple(tools),
            selected_candidate_hash=selected_candidate,
            selected_tool_artifact_hashes=selected_tools,
            report_artifact_hash=report_hash,
        )

    @staticmethod
    def _planner_request_hash(context: PlannerContext) -> str:
        return canonical_hash({
            "campaign_id": context.campaign_id,
            "target_hash": context.target_hash,
            "configuration_hash": context.configuration_hash,
            "sequence": context.sequence,
            "previous_action_id": context.previous_action_id,
            "available_artifact_hashes": context.available_artifact_hashes,
            "recorded_program_hashes": context.recorded_program_hashes,
            "selected_candidate_hash": context.selected_candidate_hash,
            "selected_tool_artifact_hashes": context.selected_tool_artifact_hashes,
            "latest_tool_result_hash": context.latest_tool_result_hash,
            "actions_remaining": context.actions_remaining,
            "tool_runs_remaining": context.tool_runs_remaining,
        })

    def _model_call(
        self, *, call_id: str, action_id: str, response: PlannerResponse,
        request_hash: str, result_hash: str,
    ) -> ModelCallRecord:
        return ModelCallRecord(
            call_id=call_id, campaign_id=self.campaign_id, action_id=action_id,
            purpose="campaign_planner", provider=response.provider,
            model_identifier=response.model_identifier,
            live_configuration_hash=self.live_configuration_hash,
            pricing_snapshot_hash=self.pricing_snapshot_hash,
            request_hash=request_hash, result_hash=result_hash,
            status=response.status, usage_source=response.usage_source,
            input_tokens=response.input_tokens, output_tokens=response.output_tokens,
            estimated_cost_microusd=response.estimated_cost_microusd,
            provider_request_id=response.provider_request_id,
            recorded_at=self.recorded_at(),
        ).finalized()

    def _store(self, content: bytes, *, media_type: str) -> str:
        expected = _raw_hash(content)
        observed = self.artifacts.put(content, media_type=media_type)
        if observed != expected:
            raise CampaignRunnerError("artifact store returned a hash for different bytes")
        return observed

    def _model_source(self, action: CampaignAction, raw: bytes) -> tuple[bytes, str]:
        if action.program_source is not None:
            return action.program_source.encode("utf-8"), "text/x-python"
        if action.artifact_text is not None:
            return action.artifact_text.encode("utf-8"), "text/plain"
        if action.report_text is not None:
            return action.report_text.encode("utf-8"), "text/plain"
        return raw, "application/vnd.adaivy.campaign-action+json"

    def _inputs(
        self, action: CampaignAction, prior: list[ActionRecord], *, source_hash: str,
        selected_candidate: str | None, selected_tools: tuple[str, ...],
        available: set[str],
    ) -> tuple[str, ...]:
        if action.action_type is ActionType.RUN_PROGRAM:
            assert action.tool_request is not None
            return (
                action.tool_request.program_artifact_hash,
                *action.tool_request.input_artifact_hashes,
            )
        if action.action_type is ActionType.INSPECT_RESULT:
            return tuple(filter(None, (
                action.selected_candidate_hash, *action.selected_tool_artifact_hashes,
            )))
        if action.action_type is ActionType.VERIFY:
            return tuple(filter(None, (selected_candidate, *selected_tools)))
        if prior:
            return tuple(
                item for item in prior[-1].output_artifact_hashes if item in available
            )
        return (self.target_hash, self.configuration_hash)

    def _admit_experiment(
        self, action: CampaignAction, action_id: str, programs: set[str],
        available: set[str], tools: list[ToolRunRecord],
    ) -> ExperimentRequest:
        request = action.tool_request
        assert request is not None
        if request.tool_id not in self.policy.allowed_tools:
            raise CampaignRunnerError("unknown campaign tool")
        if request.program_artifact_hash not in programs:
            raise CampaignRunnerError("only a prior recorded program may run")
        if not set(request.input_artifact_hashes).issubset(available):
            raise CampaignRunnerError("tool input is outside campaign provenance")
        if len(tools) >= self.policy.max_tool_runs:
            raise CampaignRunnerError("campaign tool-run bound exhausted")
        limits = request.resource_limits
        maxima = ResourceLimits(
            cpu_milliseconds=self.policy.max_cpu_milliseconds,
            wall_milliseconds=self.policy.max_wall_milliseconds,
            memory_bytes=self.policy.max_memory_bytes,
            output_bytes=self.policy.max_output_bytes,
            process_count=self.policy.max_process_count,
        )
        for field in _RESOURCE_FIELDS:
            if getattr(limits, field) > getattr(maxima, field):
                raise CampaignRunnerError(f"requested {field} exceeds campaign bound")
        return ExperimentRequest(
            campaign_id=self.campaign_id, action_id=action_id,
            tool_id=request.tool_id,
            program_artifact_hash=request.program_artifact_hash,
            program_source=self.artifacts.get(request.program_artifact_hash),
            input_artifacts=tuple(
                (item, self.artifacts.get(item)) for item in request.input_artifact_hashes
            ),
            arguments=request.arguments, resource_limits=limits, network=request.network,
        )

    def _record_tool(
        self, action_id: str, index: int, result: ExperimentResult, *, request_hash: str,
    ) -> tuple[ToolRunRecord, tuple[str, str, str]]:
        for content in (result.result, result.stdout, result.stderr):
            if len(content) > self.policy.max_artifact_bytes:
                raise CampaignRunnerError("tool artifact exceeds campaign byte bound")
        result_hash = self._store(result.result, media_type="application/octet-stream")
        stdout_hash = self._store(result.stdout, media_type="text/plain")
        stderr_hash = self._store(result.stderr, media_type="text/plain")
        record = ToolRunRecord(
            tool_run_id=f"tool.{index}", campaign_id=self.campaign_id,
            action_id=action_id, adapter_id=result.adapter_id,
            adapter_version=result.adapter_version,
            adapter_configuration_hash=result.adapter_configuration_hash,
            request_hash=request_hash,
            result_hash=result_hash, stdout_hash=stdout_hash, stderr_hash=stderr_hash,
            environment_hash=result.environment_hash, status=result.status,
            measurement_source=result.measurement_source,
            cpu_milliseconds=result.cpu_milliseconds,
            wall_milliseconds=result.wall_milliseconds,
            peak_memory_bytes=result.peak_memory_bytes,
            output_bytes=result.output_bytes, recorded_at=self.recorded_at(),
        ).finalized()
        return record, (result_hash, stdout_hash, stderr_hash)


__all__ = [
    "ACTION_SCHEMA_VERSION", "ArtifactStore", "CampaignAction",
    "CampaignExperimentRunner", "CampaignRun", "CampaignRunnerError",
    "CampaignRunnerPolicy", "ExperimentRequest", "ExperimentResult", "PlannerContext",
    "PlannerPort", "PlannerResponse", "ResourceLimits", "SequentialCampaignRunner",
    "ToolRequest", "VerificationRequest", "VerifierPort", "parse_campaign_action",
]
