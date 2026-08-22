"""Operator entrypoint for the ADR-0057 provenance-closed research campaign.

ADR-0065 is the wiring decision behind this module: the campaign ledger, the
sequential runner, the live gateway planner, and strict replay were all accepted
and implemented, and nothing could start them. This module is the front door and
nothing more. It adds no record type, no action type, no provider, no network
surface beyond the Phase 2 gateway, and no authority for a model or tool
result. ADR-0073 later wired two existing verified components through this
door: the activated ADR-0066 experiment sandbox (only behind strict
activation-record matching) and the isolated campaign verifier router.

`--provider fixture` is the default: a scripted planner that holds no gateway,
calls nothing, and needs no key, so the offline acceptance path is the default
and spending money is the explicit choice. A live provider additionally requires
`--execute`, a content-hashed live configuration, a confirmed pricing snapshot,
and the exact activation acknowledgement; the shared ADR-0057 §3 activation
service performs exactly one no-retry request through the same gateway the lead
will use, and a failed activation is a terminal recorded activation failure.

`run_program` is fail-closed by default and wired by evidence, not by flag
alone. Without `--experiment-activation` the injected experiment runner
executes nothing and records why. With it, the recorded ADR-0066 activation is
strictly re-verified and the activated OCI runner is wired ONLY when the
activation's runtime identity and both image-lock hashes match the current
repository locks; any mismatch keeps the pending runner and records the exact
rejection reason. `verify` dispatches through the isolated
`CampaignVerifierRouter`: the exact graph verifier for its frozen target, the
Phase 5 exact verifiers for their fixture schemas, an injected Phase 3B
formal-check port, and an explicit `unsupported` outcome when no verifier
applies. A verifier rejection rejects that candidate, never the campaign;
a sandbox execution failure remains terminal per ADR-0066. This module imports
no process, socket, or network module on its default path, and reads no clock:
`--recorded-at` is an argument so the fixture path is byte-reproducible.

Process effects are MEASURED rather than asserted in prose. A CPython audit hook
counts real interpreter `subprocess.*`, `os.*` and `socket.*` events, and the
injected planner, experiment and verifier ports count their own invocations, so
`inspect` and `replay` refuse rather than report a literal zero if any of the
five effect counters moves. An audit hook cannot be evaded by patching a module
attribute or by holding a pre-bound reference, which a mock can.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

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
    _IDENTIFIER as TOOL_IDENTIFIER,
    CampaignRunnerError,
    CampaignRunnerPolicy,
    ExperimentRequest,
    ExperimentResult,
    PlannerContext,
    PlannerResponse,
    ResourceLimits,
    SequentialCampaignRunner,
)
from .campaign.verifier_router import (
    CampaignVerifierRouter,
    ROUTER_ADAPTER_ID,
    UnavailableFormalChecker,
)
from .campaign.experiment_sandbox.verifier import (
    ExperimentTarget,
    VerifierError,
    load_target as load_experiment_target,
)
from .domain.entities import ResearchDossier
from .interchange import export_dossier_dict
from .novelty import (
    NoveltyRecheckError,
    classify_prior_art,
    load_recheck,
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
from .publication.campaign_terminal import (
    REPORT_STATUS_FILE,
    finalize_campaign_report,
)
from .publication.errors import PublicationValidationError
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
CAMPAIGN_FACTS_SCHEMA_VERSION = "adaivy.campaign-facts.v3"
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

#: The fifteenth bound. ADR-0065 §1 requires every bound to be checked against a
#: hard ceiling, and `allowed_tools` was the one field that carried no ceiling and
#: no identifier rule, so a configuration could name five thousand tools or a
#: path traversal and still content-hash cleanly. The ceiling is DERIVED, not
#: chosen: no campaign can perform more than `MAX_TOOL_RUNS_CEILING` tool runs,
#: so an allowlist longer than that grants tool authority no campaign can ever
#: exercise. Each entry must additionally satisfy the runner's own tool
#: identifier rule, so `config-create` cannot mint a tool the runner will always
#: reject for a reason the configuration misattributes.
MAX_ALLOWED_TOOLS_CEILING = MAX_TOOL_RUNS_CEILING

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
#: A paid activation request DID leave the process and then something downstream
#: refused, so the attempt is retained but no campaign action was ever admitted.
#: It is neither `provider_activation_failed` (the probe passed) nor a success.
REFUSAL_ACTIVATION_RETAINED = "provider_activation_retained_without_campaign_start"
REFUSAL_ACTION_SCHEMA_UNREADABLE = "campaign_action_schema_is_not_readable"
REFUSAL_PLANNER_NOT_CONSTRUCTED = "campaign_planner_could_not_be_constructed"
REFUSAL_FIXTURE_WITH_LIVE_FLAGS = "fixture_provider_refuses_live_activation_flags"
#: One reason per rejecting class. `campaign_runner_rejected_the_run` used to be
#: reported for a runner rejection, a ledger provenance failure, a configuration
#: rejection and an `OSError` alike, so the machine-readable reason said less than
#: the human-readable detail.
REFUSAL_RUNNER_REJECTED = "campaign_runner_rejected_the_run"
REFUSAL_LEDGER_INVALID = "campaign_ledger_failed_provenance_validation"
REFUSAL_CONFIG_REJECTED = "campaign_configuration_rejected"
REFUSAL_DURABLE_IO = "campaign_durable_write_failed"
REFUSAL_ACTION_REJECTED = "campaign_action_rejected_mid_run"
REFUSAL_REPLAY_PERFORMED_WORK = (
    "campaign_replay_performed_model_tool_or_network_work"
)
REFUSAL_ARTIFACT_UNRECORDED = "campaign_artifact_store_holds_an_unrecorded_file"
REFUSAL_ARTIFACT_LOG = "campaign_artifact_log_disagrees_with_the_ledger"
REFUSAL_BOUND_VIOLATION = "campaign_recorded_usage_exceeds_configured_bound"
REFUSAL_FACTS_MISMATCH = "campaign_facts_are_not_derived_from_the_ledger"
REFUSAL_ARTIFACT_MISSING = "campaign_artifact_absent_from_the_store"
REFUSAL_ARTIFACT_BYTES = "campaign_artifact_bytes_do_not_match_their_hash"
REFUSAL_TARGET_MISMATCH = "campaign_target_record_does_not_hash_to_the_ledger_target"
REFUSAL_CONFIG_MISMATCH = "campaign_configuration_hash_differs_from_the_ledger"

#: ADR-0066 is the separate digest-pinned OCI experiment-sandbox gate. A run
#: executes model-authored source ONLY when the operator supplies the recorded
#: activation and it strictly re-verifies against the current locks; otherwise
#: the source is recorded and never executed, with the wiring reason retained.
SANDBOX_GATE_DECISION = "ADR-0066"
SANDBOX_REFUSAL_REASON = "experiment_sandbox_not_wired_for_this_run"
SANDBOX_ADAPTER_ID = "experiment_sandbox_pending_gate"
#: The production adapter identity, duplicated here so the default offline path
#: never imports the sandbox module (which imports `subprocess`).  A test
#: asserts it equals `experiment_sandbox.runner.ADAPTER_ID`.
SANDBOX_OCI_ADAPTER_ID = "campaign_exact_python"

#: Experiment wiring vocabulary.  "activated_oci" is only reported after the
#: stored ADR-0066 activation record re-verified byte-for-byte AND its runtime
#: identity and both image-lock hashes matched the current repository locks.
EXPERIMENT_WIRING_ACTIVATED = "activated_oci"
EXPERIMENT_WIRING_PENDING = "pending"
WIRING_REASON_NOT_SUPPLIED = "experiment_activation_record_not_supplied"
WIRING_REASON_REJECTED_PREFIX = "experiment_activation_rejected"

#: The frozen ADR-0066 experiment target admits the exact graph verifier route
#: and, when the OCI runner is wired, binds the activation's `target_hash`.
DEFAULT_EXPERIMENT_TARGET = Path(
    "fixtures/campaign-experiment/target-exact-graph-distance-spectrum-v1.json"
)

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

FIXTURE_SCRIPTS = (
    "derive-inspect-verify-report",
    "program-sandbox-refusal",
    "graph-candidate-verify-report",
    "graph-rejected-candidate-continues",
    "oci-experiment-verify-report",
)

#: The frozen ADR-0066 experiment target identity the graph fixture scripts
#: address.  These edge lists are the canonical Petersen graph (satisfies the
#: frozen target) and the pentagonal prism (same order and size, refuted by the
#: exact distance-spectrum and Inverse Even recomputation).  Neither constant
#: is tuned: both are the exact graphs the ADR-0066 gate itself uses.
FIXTURE_GRAPH_TARGET_ID = "target.exact-graph-distance-spectrum-v1"
_PETERSEN_EDGES = [
    [0, 1], [0, 4], [0, 5], [1, 2], [1, 6], [2, 3], [2, 7], [3, 4],
    [3, 8], [4, 9], [5, 7], [5, 8], [6, 8], [6, 9], [7, 9],
]
_PRISM_EDGES = [
    [0, 1], [0, 4], [0, 5], [1, 2], [1, 6], [2, 3], [2, 7], [3, 4],
    [3, 8], [4, 9], [5, 6], [5, 9], [6, 7], [7, 8], [8, 9],
]


def _fixture_graph_candidate(edges: list[list[int]], construction: str) -> str:
    return json.dumps({
        "asserted_construction": construction,
        "asserted_satisfies_target": True,
        "edges": edges,
        "order": 10,
        "schema_version": "adaivy.campaign-experiment-graph-candidate.v1",
        "target_id": FIXTURE_GRAPH_TARGET_ID,
    }, sort_keys=True, separators=(",", ":"))


FIXTURE_GRAPH_CANDIDATE = _fixture_graph_candidate(_PETERSEN_EDGES, "petersen")
FIXTURE_GRAPH_REFUTED_CANDIDATE = _fixture_graph_candidate(
    _PRISM_EDGES, "pentagonal-prism",
)

#: A deterministic sandbox program for the OCI-gated fixture script: it emits
#: the exact Petersen candidate as its bounded result artifact and asserts
#: nothing about trust or measurement.  Only the activated ADR-0066 runner can
#: execute it; on the offline path it is recorded, refused, and terminal.
FIXTURE_OCI_PROGRAM_SOURCE = (
    "import json\n"
    f"edges = {_PETERSEN_EDGES!r}\n"
    "value = {\n"
    "    'asserted_construction': 'petersen',\n"
    "    'asserted_satisfies_target': True,\n"
    "    'edges': edges,\n"
    "    'order': 10,\n"
    "    'schema_version': 'adaivy.campaign-experiment-graph-candidate.v1',\n"
    f"    'target_id': {FIXTURE_GRAPH_TARGET_ID!r},\n"
    "}\n"
    "payload = json.dumps(value, sort_keys=True, separators=(',', ':'))\n"
    "open(ADAIVY_RESULT_PATH, 'wb').write(payload.encode('utf-8'))\n"
)

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


#: Terminal reasons that mean the campaign did not close cleanly. The ledger is
#: still persisted -- the failure IS the record -- but the command exits 2 and
#: names the terminal reason, so a caller cannot read a rejected run as a run.
REFUSED_TERMINAL_REASONS = frozenset({"action_rejected"})


class CampaignConfigurationError(ValueError):
    """Fail-closed rejection of a campaign configuration."""


class CampaignDurableRewriteError(CampaignConfigurationError):
    """Refusal to rewrite a durable campaign record with different bytes.

    Its own class exists so ADR-0065 §6's `campaign_durable_record_rewrite_refused`
    can be the reported machine-readable `reason` rather than only a substring of
    a catch-all detail string.
    """


# --------------------------------------------------------------------------- #
# Measured process effects
# --------------------------------------------------------------------------- #

#: CPython's own audit-event names for starting a process. These are interpreter
#: events, so no patched module attribute, pre-bound reference, `os.system`,
#: `os.posix_spawn` or `os.exec*` call can slip past them, all of which a mocked
#: `subprocess.run` does miss.
_PROCESS_EVENTS = frozenset({
    "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
    "os.fork", "os.forkpty", "os.fork_exec", "pty.spawn",
})
#: CPython's own audit-event names for socket creation and outbound connection.
#: `socket.__new__` is the real event name; `socket.socket` is NOT an audit event
#: and watching for it observes nothing.
_NETWORK_EVENTS = frozenset({
    "socket.__new__", "socket.connect", "socket.bind", "socket.sendto",
    "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
    "urllib.Request", "ftplib.connect", "http.client.connect",
    "smtplib.connect", "smtplib.send", "imaplib.open", "poplib.connect",
})

#: The five effect counters every command reports.
EFFECT_FIELDS = (
    "model_calls_made", "provider_requests_made", "tool_calls_made",
    "subprocesses_opened", "network_requests",
)


class _EffectMeter:
    """Measured effect counters for one command invocation.

    Two counters are observed by a CPython audit hook and three are counted at
    the injected port itself. None is a literal. ADR-0034's principle applies:
    a control that cannot be made to fail proves nothing, so these are exactly
    the counters that move if a replay ever opens a socket, starts a process,
    calls a planner, or calls a tool port -- and `replay` and `inspect` refuse
    when they do, instead of printing a constant zero next to the work.
    """

    def __init__(self) -> None:
        self._counts = dict.fromkeys(EFFECT_FIELDS, 0)
        self._depth = 0
        self.hook_installed = False
        self._hook_attempted = False

    def _observe(self, event: str, _arguments: object) -> None:
        # Runs inside the interpreter's audit machinery: integers only, no I/O.
        if self._depth == 0:
            return
        if event in _NETWORK_EVENTS:
            self._counts["network_requests"] += 1
        elif event in _PROCESS_EVENTS:
            self._counts["subprocesses_opened"] += 1

    def _install(self) -> None:
        if self._hook_attempted:
            return
        self._hook_attempted = True
        try:
            sys.addaudithook(self._observe)
        except RuntimeError:  # pragma: no cover - audit hooks refused the add
            self.hook_installed = False
        else:
            self.hook_installed = True

    def begin(self) -> None:
        self._install()
        if self._depth == 0:
            self._counts = dict.fromkeys(EFFECT_FIELDS, 0)
        self._depth += 1

    def end(self) -> None:
        self._depth -= 1

    def count(self, field: str) -> None:
        self._counts[field] += 1

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)

    def observed(self) -> bool:
        return any(value != 0 for value in self._counts.values())


_METER = _EffectMeter()


@contextlib.contextmanager
def measure_effects() -> Iterator[_EffectMeter]:
    """Measure process and port effects for the duration of one command."""

    _METER.begin()
    try:
        yield _METER
    finally:
        _METER.end()


def effect_measurement() -> dict[str, Any]:
    """How the effect counters were obtained, so a reader can distrust them."""

    return {
        "mechanism": "sys.addaudithook",
        "audit_hook_installed": _METER.hook_installed,
        "process_events_watched": sorted(_PROCESS_EVENTS),
        "network_events_watched": sorted(_NETWORK_EVENTS),
    }


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
    # A repeated `--allowed-tool` is operator error, not a request to
    # de-duplicate: every numeric bound is refused rather than normalized, and
    # silently collapsing a duplicate here would content-hash a configuration the
    # operator did not write.
    if len(set(allowed_tools)) != len(allowed_tools):
        raise CampaignConfigurationError(
            "allowed_tools contains a duplicate tool identifier"
        )
    payload: dict[str, Any] = {
        "schema_version": CAMPAIGN_CONFIG_SCHEMA_VERSION,
        "campaign_configuration_id": campaign_configuration_id,
        "allowed_tools": sorted(allowed_tools),
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
    if not isinstance(tools, list) or not tools:
        raise CampaignConfigurationError(
            "allowed_tools must be a non-empty list of tool identifiers"
        )
    if len(tools) > MAX_ALLOWED_TOOLS_CEILING:
        raise CampaignConfigurationError(
            f"allowed_tools of {len(tools)} exceeds the hard ceiling of "
            f"{MAX_ALLOWED_TOOLS_CEILING}"
        )
    if any(
        not isinstance(item, str) or not TOOL_IDENTIFIER.fullmatch(item)
        for item in tools
    ):
        # The runner applies exactly this rule, so accepting `../../etc/passwd`
        # here would content-hash a configuration whose every run is refused for
        # a reason the configuration misattributes.
        raise CampaignConfigurationError(
            "every allowed_tools entry must match the campaign tool identifier rule"
        )
    if sorted(set(tools)) != list(tools):
        raise CampaignConfigurationError(
            "allowed_tools must be sorted and free of duplicate tool identifiers"
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


def read_campaign_configuration(path: Path) -> tuple[bytes, CampaignConfiguration]:
    """Read the operator's configuration bytes ONCE and parse those bytes.

    `run` persists these exact bytes as `campaign-config.json`, so reading the
    file a second time later could persist bytes that were never validated.
    """

    try:
        raw = path.read_bytes()
    except OSError as error:
        raise CampaignConfigurationError(
            f"cannot load campaign configuration: {path}"
        ) from error
    payload = _strict_json(raw, what="campaign configuration")
    if not isinstance(payload, dict):
        raise CampaignConfigurationError("campaign configuration must be a JSON object")
    return raw, parse_campaign_configuration(payload)


def load_campaign_configuration(path: Path) -> CampaignConfiguration:
    return read_campaign_configuration(path)[1]


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
    port refuses by name, carries the exact machine-readable reason the
    activated runner was not wired, and the refusal is retained as a failed
    tool run rather than discarded. No sandbox is stubbed or approximated here
    and no subprocess or socket is opened.
    """

    adapter_id = SANDBOX_ADAPTER_ID
    reason = SANDBOX_REFUSAL_REASON

    def __init__(self, *, wiring_reason: str = WIRING_REASON_NOT_SUPPLIED) -> None:
        self.wiring_reason = wiring_reason
        self.requests: list[ExperimentRequest] = []

    def __call__(self, request: ExperimentRequest) -> ExperimentResult:
        self.requests.append(request)
        payload = _refusal_payload(
            SANDBOX_REFUSAL_REASON,
            blocking_decision=SANDBOX_GATE_DECISION,
            wiring_reason=self.wiring_reason,
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
                "wiring_reason": self.wiring_reason,
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


class _MeteredToolPort:
    """Counts real tool-port invocations for whatever port is injected.

    One wrapper for both the experiment runner and the verifier router, so
    `tool_calls_made` is a measurement of this process rather than a claim by
    any individual adapter.
    """

    def __init__(self, port: Any) -> None:
        self._port = port

    def __getattr__(self, name: str) -> Any:
        return getattr(self._port, name)

    def __call__(self, request: Any) -> ExperimentResult:
        _METER.count("tool_calls_made")
        return self._port(request)


class _GuardedExperimentRunner:
    """Converts an activated-runner refusal into a recorded campaign rejection.

    The ADR-0066 adapter raises its own `ValueError` subclass for a request the
    OCI profile cannot enforce (a sub-second limit, an unknown adapter). Left
    unconverted, that exception would escape the sequential runner's rejection
    handling and discard the ledger; as a `CampaignRunnerError` it is retained
    as a terminal `action_rejected` with the reason recorded.
    """

    def __init__(self, runner: Any) -> None:
        self._runner = runner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runner, name)

    def __call__(self, request: ExperimentRequest) -> ExperimentResult:
        try:
            return self._runner(request)
        except CampaignRunnerError:
            raise
        except (ValueError, OSError) as error:
            raise CampaignRunnerError(
                f"activated experiment sandbox refused the request: {error}"
            ) from error


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentWiring:
    """The recorded outcome of one experiment-runner wiring decision."""

    runner: Any
    status: str
    adapter_id: str
    reason: str | None
    activation_content_hash: str | None

    def to_record(self) -> dict[str, Any]:
        return {
            "activation_content_hash": self.activation_content_hash,
            "adapter_id": self.adapter_id,
            "reason": self.reason,
            "status": self.status,
        }


def _pending_wiring(reason: str) -> ExperimentWiring:
    return ExperimentWiring(
        runner=PendingSandboxExperimentRunner(wiring_reason=reason),
        status=EXPERIMENT_WIRING_PENDING, adapter_id=SANDBOX_ADAPTER_ID,
        reason=reason, activation_content_hash=None,
    )


def _wire_experiment_runner(
    args: argparse.Namespace, experiment_target: ExperimentTarget | None,
) -> ExperimentWiring:
    """Wire the activated OCI runner ONLY from a matching activation record.

    Every mismatch keeps the pending runner and records the exact reason:
    unreadable or non-canonical activation bytes, a blocked activation, a
    runtime identity that differs from the recorded one, an image lock whose
    hash moved since activation, or a frozen experiment target that differs
    from the one the activation probed. Nothing here rounds toward execution.
    """

    if args.experiment_activation is None:
        return _pending_wiring(WIRING_REASON_NOT_SUPPLIED)
    if experiment_target is None:
        return _pending_wiring(
            f"{WIRING_REASON_REJECTED_PREFIX}: the frozen experiment target "
            "is not readable, so the activation target_hash cannot be checked"
        )
    try:
        data = args.experiment_activation.read_bytes()
        # Lazy by design: these modules hold `import subprocess` and stay off
        # the default offline import path.
        from .campaign.experiment_sandbox.activation import (
            load_campaign_experiment_activation,
        )
        from .campaign.experiment_sandbox.runner import (
            build_activated_campaign_experiment_runner,
        )
        from .phase4b.oci_parser_sandbox import OciRuntimeIdentity

        report, activation = load_campaign_experiment_activation(data)
        runtime_record = dict(report["environment"])
        runtime_record["image_layers"] = tuple(runtime_record["image_layers"])
        runtime = OciRuntimeIdentity(**runtime_record)
        runner = build_activated_campaign_experiment_runner(
            repository_root=args.experiment_repository_root,
            runtime=runtime, activation=activation,
            target_hash=experiment_target.target_hash,
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        detail = str(error) or type(error).__name__
        return _pending_wiring(f"{WIRING_REASON_REJECTED_PREFIX}: {detail}")
    return ExperimentWiring(
        runner=_GuardedExperimentRunner(runner),
        status=EXPERIMENT_WIRING_ACTIVATED, adapter_id=SANDBOX_OCI_ADAPTER_ID,
        reason=None, activation_content_hash=activation.content_hash,
    )


class _SealedFormalChecker:
    """Phase 3B formal-check port over the sealed Docker Lean adapter.

    Constructed only when the operator explicitly selects the sealed adapter,
    because the Phase 3B adapter module imports `subprocess` and requires the
    ADR-0016 sealed runtime image. `created_at` is the campaign's frozen
    `--recorded-at` instant, never a clock read.
    """

    adapter_id = "phase3b_docker_lean"

    def __init__(self, recorded_at: str) -> None:
        from .phase3b.adapter import DockerLeanAdapter
        from .phase3b.serialization import public_value
        from .phase3b.service import FormalCheckingService

        self._service = FormalCheckingService(DockerLeanAdapter())
        self._public = public_value
        self._recorded_at = recorded_at

    def check(self, request_bytes: bytes) -> Mapping[str, Any]:
        return self._public(
            self._service.check(request_bytes, created_at=self._recorded_at)
        )


def _formal_checker(args: argparse.Namespace) -> Any:
    if args.formal_check_adapter == "sealed":
        return _SealedFormalChecker(args.recorded_at)
    return UnavailableFormalChecker()


def _build_verifier_router(
    args: argparse.Namespace,
    experiment_target: ExperimentTarget | None,
    experiment_target_reason: str | None,
) -> CampaignVerifierRouter:
    """Reconstruct the verifier context from records alone.

    The router receives the frozen experiment target bytes and an injected
    formal-check port -- never the planner, the gateway, a credential, or a
    corpus handle. Verifier results are recorded as tool runs; the sequential
    runner does not feed them back into the planner context, so validator
    diagnostics stay structurally isolated from the lead.
    """

    return CampaignVerifierRouter(
        graph_target=experiment_target,
        graph_target_reason=experiment_target_reason,
        formal_checker=_formal_checker(args),
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


class _MeteredPlanner:
    """Counts planner invocations at the port, for whatever planner is injected.

    `model_calls_made` is therefore a measurement of this process rather than a
    claim about it, and a live planner additionally counts one provider request
    per invocation. `replay` constructs no planner at all, so the counter that
    it reports as zero is the same counter that moves the moment one is used.
    """

    def __init__(self, planner: Any, *, provider: str) -> None:
        self._planner = planner
        self._provider = provider

    def __getattr__(self, name: str) -> Any:
        # The runner reads `planner.activation`; delegate everything else too.
        return getattr(self._planner, name)

    def __call__(self, context: PlannerContext) -> PlannerResponse:
        _METER.count("model_calls_made")
        if self._provider != FIXTURE_PROVIDER:
            _METER.count("provider_requests_made")
        return self._planner(context)


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
        self.graph_candidate_hash = _raw_hash(FIXTURE_GRAPH_CANDIDATE.encode("utf-8"))
        self.refuted_candidate_hash = _raw_hash(
            FIXTURE_GRAPH_REFUTED_CANDIDATE.encode("utf-8")
        )

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
        if self.script == "graph-candidate-verify-report":
            return (
                self._derive_graph, self._inspect_graph, self._verify, self._report,
            )
        if self.script == "graph-rejected-candidate-continues":
            # The first candidate is exactly refuted; the campaign CONTINUES,
            # derives a second candidate, and verifies it. A verifier rejection
            # rejects the candidate, never the campaign.
            return (
                self._derive_refuted, self._inspect_refuted, self._verify,
                self._derive_graph, self._inspect_graph, self._verify,
                self._report,
            )
        if self.script == "oci-experiment-verify-report":
            return (
                self._write_oci_program, self._run_program,
                self._inspect_tool_candidate, self._verify, self._report,
            )
        return (self._derive, self._write_program, self._run_program, self._report)

    def _derive(self, _context: PlannerContext) -> bytes:
        return _action_json("derive", artifact_text=FIXTURE_CANDIDATE_TEXT)

    def _derive_graph(self, _context: PlannerContext) -> bytes:
        return _action_json("derive", artifact_text=FIXTURE_GRAPH_CANDIDATE)

    def _derive_refuted(self, _context: PlannerContext) -> bytes:
        return _action_json("derive", artifact_text=FIXTURE_GRAPH_REFUTED_CANDIDATE)

    def _inspect(self, _context: PlannerContext) -> bytes:
        return _action_json(
            "inspect_result", selected_candidate_hash=self.candidate_hash,
        )

    def _inspect_graph(self, _context: PlannerContext) -> bytes:
        return _action_json(
            "inspect_result", selected_candidate_hash=self.graph_candidate_hash,
        )

    def _inspect_refuted(self, _context: PlannerContext) -> bytes:
        return _action_json(
            "inspect_result", selected_candidate_hash=self.refuted_candidate_hash,
        )

    def _inspect_tool_candidate(self, context: PlannerContext) -> bytes:
        # The sandbox result is an untrusted candidate. Restating its exact
        # bytes as the inspected candidate binds the same content hash, and the
        # tool result artifact is selected alongside it.
        if context.latest_tool_result is None or context.latest_tool_result_hash is None:
            raise CampaignRunnerError("no tool result is available to inspect")
        return _action_json(
            "inspect_result",
            artifact_text=context.latest_tool_result.decode("utf-8"),
            selected_tool_artifact_hashes=[context.latest_tool_result_hash],
        )

    def _verify(self, context: PlannerContext) -> bytes:
        return _action_json(
            "verify",
            selected_candidate_hash=context.selected_candidate_hash,
            selected_tool_artifact_hashes=list(context.selected_tool_artifact_hashes),
        )

    def _write_program(self, _context: PlannerContext) -> bytes:
        return _action_json("write_program", program_source=FIXTURE_PROGRAM_SOURCE)

    def _write_oci_program(self, _context: PlannerContext) -> bytes:
        return _action_json("write_program", program_source=FIXTURE_OCI_PROGRAM_SOURCE)

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


#: The five recorded rollups that ADR-0065 §1 caps. Each pair is
#: (configuration bound, `usage` key derived from the records).
_BOUND_ROLLUPS: tuple[tuple[str, str], ...] = (
    ("max_cost_microusd", "estimated_cost_microusd"),
    ("max_input_tokens", "input_tokens"),
    ("max_model_calls", "requests_attempted"),
    ("max_output_tokens", "output_tokens"),
    ("max_tool_runs", "tool_runs_attempted"),
)


def campaign_bound_compliance(
    export: Any, configuration: CampaignConfiguration,
) -> dict[str, Any]:
    """Compare the recorded rollups with the configured caps.

    Derived from the ledger and the content-hashed configuration alone, so
    `inspect` recomputes it and a hand-edited copy is refused. A campaign that
    blew one of its own caps carries the violation in its DURABLE facts: printing
    the violation on stdout after every durable file had already been written let
    an over-budget campaign inspect, replay and export as if it were clean.
    """

    observed = {
        bound: int(export.usage[key]) for bound, key in _BOUND_ROLLUPS
    }
    configured = {
        bound: getattr(configuration, bound) for bound, _ in _BOUND_ROLLUPS
    }
    exceeded = sorted(
        bound for bound in observed if observed[bound] > configured[bound]
    )
    return {
        "status": "exceeded" if exceeded else "within_bounds",
        "configured": configured,
        "observed": observed,
        "exceeded_bounds": exceeded,
    }


def _experiment_sandbox_facts(export: Any) -> dict[str, Any]:
    """Derive the sandbox block from the ledger's own adapter identities.

    `status` is a fact about what the recorded tool runs show, never an
    assertion about what was configured: a ledger with no experiment tool run
    is `not_exercised`, one whose runs carry the pending adapter is `pending`,
    and one whose runs carry the ADR-0066 production adapter is
    `activated_oci`. A ledger holding both is impossible for one run and is
    reported as `activated_oci` with its refusal count intact.
    """

    pending = [
        item for item in export.tool_runs if item.adapter_id == SANDBOX_ADAPTER_ID
    ]
    activated = [
        item for item in export.tool_runs
        if item.adapter_id == SANDBOX_OCI_ADAPTER_ID
    ]
    if activated:
        status = EXPERIMENT_WIRING_ACTIVATED
    elif pending:
        status = EXPERIMENT_WIRING_PENDING
    else:
        status = "not_exercised"
    return {
        "activation_decision": SANDBOX_GATE_DECISION,
        "status": status,
        "programs_recorded": sum(
            item.action_type is ActionType.WRITE_PROGRAM for item in export.actions
        ),
        "programs_executed": sum(
            item.status is RecordStatus.COMPLETED for item in activated
        ),
        "executions_failed": sum(
            item.status is not RecordStatus.COMPLETED for item in activated
        ),
        "execution_refusals_recorded": len(pending),
    }


def _isolated_verifier_facts(export: Any) -> dict[str, Any]:
    """Derive the verifier block from the router's recorded tool runs."""

    routed = [
        item for item in export.tool_runs if item.adapter_id == ROUTER_ADAPTER_ID
    ]
    return {
        "adapter_id": ROUTER_ADAPTER_ID,
        "status": "router" if routed else "not_exercised",
        "verifications_completed": sum(
            item.status is RecordStatus.COMPLETED for item in routed
        ),
        "verifications_failed": sum(
            item.status is not RecordStatus.COMPLETED for item in routed
        ),
    }


def campaign_facts(
    export: Any, recheck: Any, configuration: CampaignConfiguration,
) -> dict[str, Any]:
    """Derive every fact from the ledger, the bound re-check and the bounds.

    Nothing here is an argument beyond those three, so `inspect` can recompute the
    file and refuse a hand-edited one. No field can promote anything: the
    guardrail block is a constant `False` and is asserted, not chosen.

    The two effect counters this block used to carry (`subprocesses_opened` and
    `network_requests_during_replay`) were literals, and they are not derivable
    from a ledger, which is why they had to be. They now live in the measured
    `effects` block of each command's output instead.
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
        "experiment_sandbox": _experiment_sandbox_facts(export),
        "isolated_verifier": _isolated_verifier_facts(export),
        "bound_compliance": campaign_bound_compliance(export, configuration),
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


#: A stored artifact file is named for the hash of its own bytes.
_ARTIFACT_FILE_NAME = re.compile(r"^sha256-[0-9a-f]{64}$")


def _reconcile_artifact_store(root: Path, expected: frozenset[str]) -> None:
    """Close the artifact store both ways.

    Checking only that every ledger hash resolves is not closure. It admitted a
    file the ledger never recorded -- a discarded partial run left model-authored
    Python source on disk with no record of who wrote it -- and it admitted a file
    whose NAME is a hash its own bytes do not produce, because nothing ever read a
    file the ledger did not ask for.
    """

    directory = root / "artifacts"
    found: set[str] = set()
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if not path.is_file() or not _ARTIFACT_FILE_NAME.fullmatch(path.name):
                raise CampaignProvenanceError(
                    f"{REFUSAL_ARTIFACT_UNRECORDED}: {path.name}"
                )
            named = "sha256:" + path.name[len("sha256-"):]
            if _raw_hash(path.read_bytes()) != named:
                raise CampaignProvenanceError(f"{REFUSAL_ARTIFACT_BYTES}: {named}")
            found.add(named)
    missing = sorted(expected - found)
    if missing:
        raise CampaignProvenanceError(f"{REFUSAL_ARTIFACT_MISSING}: {missing[0]}")
    unrecorded = sorted(found - expected)
    if unrecorded:
        raise CampaignProvenanceError(
            f"{REFUSAL_ARTIFACT_UNRECORDED}: {unrecorded[0]}"
        )


def _reconcile_artifact_log(root: Path, expected: frozenset[str]) -> None:
    """The append-only put log must name exactly the ledger's artifacts."""

    path = root / "artifact-log.jsonl"
    logged: set[str] = set()
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise CampaignProvenanceError(REFUSAL_ARTIFACT_LOG) from error
        for index, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            entry = _strict_json(line.encode("utf-8"), what="artifact log entry")
            if (
                not isinstance(entry, dict)
                or set(entry) != {"content_hash", "media_type"}
                or not isinstance(entry["content_hash"], str)
            ):
                raise CampaignProvenanceError(f"{REFUSAL_ARTIFACT_LOG}: line {index}")
            logged.add(entry["content_hash"])
    if logged != set(expected):
        difference = sorted(logged ^ set(expected))
        raise CampaignProvenanceError(f"{REFUSAL_ARTIFACT_LOG}: {difference[0]}")


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
            raise CampaignDurableRewriteError(
                f"{REFUSAL_DURABLE_REWRITE}: {path.name}"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


#: Every durable file `run` writes. `campaign.json` is deliberately last.
DURABLE_FILE_NAMES = (
    "activation.json", "artifact-log.jsonl", "campaign-config.json",
    "campaign-facts.json", "novelty-recheck.json", "target.json",
    "campaign.json",
)


def _write_durable(root: Path, files: Sequence[tuple[str, bytes]]) -> None:
    """Write every durable file with `campaign.json` LAST.

    `campaign.json` is the file the append-only guard keys on. Writing it first
    meant that an error before `campaign-facts.json` wedged the root permanently:
    a re-run refused `campaign_root_already_recorded` and `inspect` errored on the
    half-written pair. Written last, a failed durable write leaves a root that is
    still refused by the broader guard below but is no longer self-contradictory.
    """

    ordered = sorted(files, key=lambda item: (item[0] == "campaign.json", item[0]))
    for name, content in ordered:
        _write_once(root / name, content)


def _finish_terminal_report(
    root: Path, export: Any, facts: Mapping[str, Any], configuration: Any,
) -> Mapping[str, Any]:
    """Write the report projection and its immutable completion record."""

    report = finalize_campaign_report(root, export, facts, configuration)
    durable = dict(report)
    # Whether this invocation wrote or re-verified the same bundle is an
    # invocation fact, not part of the immutable campaign completion record.
    durable["status"] = "complete"
    _write_once(root / REPORT_STATUS_FILE, canonical_bytes(durable) + b"\n")
    return report


def _failed_terminal_report(error: Exception) -> Mapping[str, Any]:
    return {
        "schema_version": "adaivy.campaign-terminal-report.v1",
        "status": "failed",
        "reason": str(error) or type(error).__name__,
        "typeset_status": "not_typeset",
        "pdf_sha256": None,
        "publication_approval": None,
        "epistemic_warrant_created": False,
    }


def _existing_durable_state(root: Path) -> tuple[str, ...]:
    """Every durable campaign byte already present under `root`.

    Keying the append-only guard on `campaign.json` alone left a hole: a run that
    stored artifacts and then refused wrote no `campaign.json`, so a second run
    into the same root was admitted ON TOP of the first run's model-authored
    bytes and then reported a closed ledger over both. Any durable byte, artifact
    included, closes the root.
    """

    found = [name for name in DURABLE_FILE_NAMES if (root / name).exists()]
    artifacts = root / "artifacts"
    if artifacts.is_dir() and any(artifacts.iterdir()):
        found.append("artifacts/")
    return tuple(sorted(found))


def _rejection_reason(error: Exception) -> str:
    """Name the class of rejection instead of one catch-all.

    ADR-0065 §6 names `campaign_durable_record_rewrite_refused` as a refusal, and
    before this it was never the reported `reason`: a runner rejection, a ledger
    provenance failure, a configuration rejection and an `OSError` all arrived as
    `campaign_runner_rejected_the_run` with the truth demoted to `detail`.
    """

    if isinstance(error, CampaignDurableRewriteError):
        return REFUSAL_DURABLE_REWRITE
    if isinstance(error, CampaignConfigurationError):
        return REFUSAL_CONFIG_REJECTED
    if isinstance(error, CampaignRunnerError):
        return REFUSAL_RUNNER_REJECTED
    if isinstance(error, CampaignProvenanceError):
        return REFUSAL_LEDGER_INVALID
    return REFUSAL_DURABLE_IO


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
    except CampaignDurableRewriteError:
        return _refuse(REFUSAL_DURABLE_REWRITE, path=str(args.output))
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
    except CampaignDurableRewriteError:
        return _refuse(REFUSAL_DURABLE_REWRITE, path=str(args.output))
    except (CampaignConfigurationError, OSError, ValueError) as error:
        return _refuse(str(error))
    _print({
        "status": "written",
        "path": str(args.output),
        "target_hash": _raw_hash(content),
        **record,
    })
    return 0


@dataclass(frozen=True, slots=True, kw_only=True)
class LiveActivationOutcome:
    """Result of the single ADR-0057 §3 activation attempt.

    This type exists so `_live_activation` never prints and never decides. Whether
    a paid request left the process determines whether `run` must write a ledger,
    and that decision cannot be made by the function that fired the request.
    """

    refusal_reason: str | None
    refusal_detail: Mapping[str, Any]
    live: Any | None
    pricing: Any | None
    planner: Any | None
    activation: LiveProviderProbeResult | None


def _live_refusal(reason: str, **detail: Any) -> LiveActivationOutcome:
    return LiveActivationOutcome(
        refusal_reason=reason, refusal_detail=detail,
        live=None, pricing=None, planner=None, activation=None,
    )


def _live_activation(
    args: argparse.Namespace, configuration: CampaignConfiguration,
) -> LiveActivationOutcome:
    """Resolve, bind, and activate the live route, or refuse by name.

    Every inert operator input -- the live configuration, the pricing snapshot,
    the acknowledgement, the environment preflight and the action schema file --
    is read and checked BEFORE `build_gateway`. Reading the action schema during
    planner construction, after the one paid probe had already been fired, meant
    that an unreadable relative `--action-schema` path spent a real billable
    request and then discarded it: the retention branch was reached only for a
    FAILED probe, so a passing probe followed by any downstream failure recorded
    nothing at all.
    """

    if not args.execute:
        return _live_refusal(REFUSAL_LIVE_REQUIRES_EXECUTE, provider=args.provider)
    if args.live_config is None or args.pricing_snapshot is None:
        return _live_refusal(REFUSAL_LIVE_REQUIRES_ARTIFACTS, provider=args.provider)
    try:
        live = load_live_run_configuration(args.live_config)
        pricing = load_pricing_snapshot(args.pricing_snapshot)
    except (LiveRunConfigurationError, PricingSnapshotError, OSError) as error:
        return _live_refusal(str(error))
    if live.provider != args.provider:
        return _live_refusal(
            REFUSAL_PROVIDER_MISMATCH,
            requested=args.provider, configured=live.provider,
        )
    if (
        pricing.snapshot_id != live.pricing_snapshot_id
        or pricing.provider != live.provider
        or pricing.model_identifier != live.model_identifier
        or not pricing_snapshot_is_confirmed(pricing)
    ):
        return _live_refusal(REFUSAL_PRICING_UNCONFIRMED)
    if args.activation_acknowledgement != LIVE_PROBE_ACKNOWLEDGEMENT:
        return _live_refusal(
            REFUSAL_NOT_ACKNOWLEDGED, expected=LIVE_PROBE_ACKNOWLEDGEMENT,
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
        return _live_refusal(REFUSAL_BUDGET_EXCEEDS_CAP, exceeded_bounds=exceeded)

    import os

    environment = dict(os.environ)
    static = static_provider_preflight(live, pricing, environment=environment)
    if static.status != "passed":
        return _live_refusal(
            REFUSAL_STATIC_PREFLIGHT,
            missing_variables=list(static.missing_variables),
            failed_checks=list(static.failed_checks),
        )
    # The last inert input, read before any gateway exists and before any money
    # can be spent. `--action-schema` defaults to a RELATIVE path, so this read
    # fails whenever `run` is invoked from anywhere but the repository root.
    try:
        action_schema = args.action_schema.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return _live_refusal(
            REFUSAL_ACTION_SCHEMA_UNREADABLE,
            action_schema=str(args.action_schema), detail=str(error),
        )

    gateway = build_gateway(live.provider, live.model_identifier)
    _METER.count("provider_requests_made")
    activation = run_live_provider_probe(
        static, live, pricing,
        environment=environment,
        acknowledgement=args.activation_acknowledgement,
        observed_at=args.recorded_at,
        probe=GatewayProviderProbe(live, gateway),
    )
    if activation.probe_status != "passed":
        return LiveActivationOutcome(
            refusal_reason=REFUSAL_ACTIVATION_FAILED,
            refusal_detail={
                "failure_classification": activation.failure_classification,
            },
            live=live, pricing=pricing, planner=None, activation=activation,
        )
    from .campaign.planner import GatewayCampaignPlanner

    try:
        planner = GatewayCampaignPlanner(
            live, pricing, gateway=gateway, activation=activation,
            action_schema=action_schema,
            max_context_bytes=configuration.max_context_bytes,
        )
    except (CampaignProvenanceError, ValueError, OSError) as error:
        return LiveActivationOutcome(
            refusal_reason=REFUSAL_PLANNER_NOT_CONSTRUCTED,
            refusal_detail={"detail": str(error)},
            live=live, pricing=pricing, planner=None, activation=activation,
        )
    return LiveActivationOutcome(
        refusal_reason=None, refusal_detail={},
        live=live, pricing=pricing, planner=planner, activation=activation,
    )


def _activation_record_status(activation: LiveProviderProbeResult) -> RecordStatus:
    """Carry the probe's own response counters into the ledger status.

    ADR-0057 §3 keeps `responses_completed`, `responses_failed` and
    `responses_incomplete` as DISTINCT counters. Hardcoding `failed` collapsed a
    timed-out probe into the failed bucket, so `campaign.json` and
    `campaign-facts.json` reported `responses_failed: 1` for a request that was
    never answered either way. Anything ambiguous stays `failed`, which is the
    fail-closed direction.
    """

    if activation.responses_failed:
        return RecordStatus.FAILED
    if activation.responses_incomplete:
        return RecordStatus.INCOMPLETE
    if activation.responses_completed:
        return RecordStatus.COMPLETED
    return RecordStatus.FAILED


def _activation_only_ledger(
    *,
    campaign_id: str,
    target_hash: str,
    configuration_hash: str,
    activation: LiveProviderProbeResult,
    artifacts: FileArtifactStore,
    rationale: str,
) -> Any:
    """Retain one ADR-0057 §3 activation as the terminal campaign ledger.

    Reached whenever a paid request left the process and no campaign action was
    admitted afterwards -- a failed probe, or a passing probe whose planner could
    not be built. It is never `proposer_declined` and never a success.
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
        result_hash=activation_hash,
        status=_activation_record_status(activation),
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
        declared_rationale=rationale,
        recorded_at=activation.observed_at,
    ).finalized()
    return build_campaign_export(
        campaign_id=campaign_id, target_hash=target_hash,
        configuration_hash=configuration_hash, actions=(action,),
        model_calls=(call,), tool_runs=(),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class _RunInputs:
    """Every inert operator input, read and validated before any gateway."""

    configuration: CampaignConfiguration
    configuration_bytes: bytes
    target_record: Mapping[str, Any]
    target_content: bytes
    target_hash: str
    recheck: Any
    recheck_bytes: bytes


def _run(args: argparse.Namespace) -> int:
    with measure_effects():
        return _run_measured(args)


def _run_measured(args: argparse.Namespace) -> int:
    root: Path = args.root
    existing = _existing_durable_state(root)
    if existing:
        return _refuse(
            REFUSAL_ROOT_RECORDED, root=str(root), recorded_files=list(existing),
        )

    if args.provider == FIXTURE_PROVIDER:
        # The label stays honest, but an operator or script that asked for a live
        # run must not silently receive a green scripted one.
        requested = sorted(
            name for name, present in (
                ("--activation-acknowledgement", bool(args.activation_acknowledgement)),
                ("--execute", bool(args.execute)),
                ("--live-config", args.live_config is not None),
                ("--pricing-snapshot", args.pricing_snapshot is not None),
            ) if present
        )
        if requested:
            return _refuse(
                REFUSAL_FIXTURE_WITH_LIVE_FLAGS,
                provider=args.provider, live_arguments=requested,
            )

    try:
        inputs = _read_run_inputs(args)
    except (
        CampaignConfigurationError, NoveltyRecheckError, OSError, ValueError,
    ) as error:
        return _refuse(str(error))

    configuration = inputs.configuration
    try:
        experiment_target: ExperimentTarget | None = load_experiment_target(
            args.experiment_target.read_bytes()
        )
        experiment_target_reason: str | None = None
    except (OSError, VerifierError) as error:
        experiment_target = None
        experiment_target_reason = (
            f"experiment_target_unreadable: {error}" if str(error)
            else "experiment_target_unreadable"
        )
    wiring = _wire_experiment_runner(args, experiment_target)
    experiment = _MeteredToolPort(wiring.runner)
    verifier = _MeteredToolPort(_build_verifier_router(
        args, experiment_target, experiment_target_reason,
    ))
    activation: LiveProviderProbeResult | None = None
    live_configuration_hash = FIXTURE_LIVE_CONFIGURATION_HASH
    pricing_snapshot_hash = FIXTURE_PRICING_SNAPSHOT_HASH

    if args.provider == FIXTURE_PROVIDER:
        planner: Any = _MeteredPlanner(
            ScriptedCampaignPlanner(
                script=args.fixture_script,
                tool_id=configuration.allowed_tools[0],
                resource_limits=ResourceLimits(
                    cpu_milliseconds=configuration.max_cpu_milliseconds,
                    wall_milliseconds=configuration.max_wall_milliseconds,
                    memory_bytes=configuration.max_memory_bytes,
                    output_bytes=configuration.max_output_bytes,
                    process_count=configuration.max_process_count,
                ),
            ),
            provider=args.provider,
        )
    else:
        outcome = _live_activation(args, configuration)
        activation = outcome.activation
        if activation is not None:
            # ADR-0057 §3: the activation observation is retained whether it
            # passed or failed, and before anything else can consume it.
            root.mkdir(parents=True, exist_ok=True)
            try:
                _write_once(
                    root / "activation.json", canonical_bytes(activation) + b"\n",
                )
            except (CampaignConfigurationError, OSError) as error:
                return _refuse(_rejection_reason(error), detail=str(error))
        if activation is None:
            return _refuse(
                outcome.refusal_reason or REFUSAL_ACTIVATION_NOT_EXECUTED,
                **outcome.refusal_detail,
            )
        if activation.probe_request_hash is None:
            # No request left the process, so there is no model attempt to
            # retain: `requests_attempted` is zero, not one.
            return _refuse(
                REFUSAL_ACTIVATION_NOT_EXECUTED,
                failure_classification=activation.failure_classification,
                requests_attempted=activation.requests_attempted,
                terminal_reason=REFUSAL_ACTIVATION_NOT_EXECUTED,
            )
        if outcome.planner is None:
            # A paid request DID leave the process. Retain it whatever refused
            # afterwards; dropping it would spend money outside every ledger.
            return _retain_activation(
                args=args, inputs=inputs, activation=activation,
                reason=outcome.refusal_reason,
                detail=outcome.refusal_detail,
            )
        planner = _MeteredPlanner(outcome.planner, provider=args.provider)
        live_configuration_hash = outcome.live.content_hash
        pricing_snapshot_hash = outcome.pricing.content_hash

    root.mkdir(parents=True, exist_ok=True)
    artifacts = FileArtifactStore(root / "artifacts")
    try:
        completed = SequentialCampaignRunner(
            campaign_id=args.campaign_id,
            target_hash=inputs.target_hash,
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
            campaign_id=completed.campaign_id, target_hash=inputs.target_hash,
            configuration_hash=configuration.content_hash,
            actions=completed.actions, model_calls=completed.model_calls,
            tool_runs=completed.tool_runs,
        )
        facts = campaign_facts(export, inputs.recheck, configuration)
        files = [
            *_shared_durable_files(inputs),
            ("campaign-facts.json", canonical_bytes(facts) + b"\n"),
            ("campaign.json", export_campaign_bytes(export)),
        ]
        if activation is not None:
            files.append(
                ("activation.json", canonical_bytes(activation) + b"\n"),
            )
        _write_durable(root, files)
    except (
        CampaignRunnerError, CampaignProvenanceError, CampaignConfigurationError, OSError,
    ) as error:
        return _refuse(_rejection_reason(error), detail=str(error))

    try:
        report = _finish_terminal_report(root, export, facts, configuration)
    except (PublicationValidationError, CampaignConfigurationError, OSError) as error:
        # The campaign ledger is already durable. A projection failure is
        # visible, but cannot rewrite the mathematical or operational outcome.
        report = _failed_terminal_report(error)

    payload = {
        "campaign_id": completed.campaign_id,
        "terminal_reason": completed.terminal_reason,
        "provider": args.provider,
        "root": str(root),
        "experiment_runner": wiring.to_record(),
        "verifier_router": {
            "adapter_id": ROUTER_ADAPTER_ID,
            "graph_target_hash": (
                None if experiment_target is None else experiment_target.target_hash
            ),
            "graph_target_reason": experiment_target_reason,
            "formal_check_adapter": args.formal_check_adapter,
        },
        "epistemic_warrant_created": completed.epistemic_warrant_created,
        "effects": _METER.snapshot(),
        "effect_measurement": effect_measurement(),
        "facts": facts,
        "publication_draft": report,
    }
    compliance = facts["bound_compliance"]
    if compliance["status"] != "within_bounds":
        # The violation is already in `campaign-facts.json`; this is the exit code.
        _print({
            "status": "refused", "reason": REFUSAL_BOUND_VIOLATION,
            "exceeded_bounds": compliance["exceeded_bounds"], **payload,
        })
        return 2
    if completed.terminal_reason in REFUSED_TERMINAL_REASONS:
        _print({
            "status": "refused", "reason": REFUSAL_ACTION_REJECTED, **payload,
        })
        return 2
    _print({"status": "recorded", **payload})
    return 0


def _read_run_inputs(args: argparse.Namespace) -> _RunInputs:
    """Read and validate every inert operator input before any gateway exists."""

    configuration_bytes, configuration = read_campaign_configuration(args.config)
    dossier = _dossier(args)
    target_record = campaign_target_record(dossier)
    target_content = campaign_target_bytes(target_record)
    if args.novelty_recheck is None:
        raise NoveltyRecheckError(REFUSAL_NOVELTY_ABSENT)
    recheck_bytes = args.novelty_recheck.read_bytes()
    recheck = load_recheck(recheck_bytes)
    require_checkpoint(
        recheck, checkpoint="before_research",
        subject_id=dossier.problem.id.value,
        subject_hash=str(target_record["dossier_content_hash"]),
        next_action_id=args.campaign_id,
        action_at=args.recorded_at,
    )
    return _RunInputs(
        configuration=configuration, configuration_bytes=configuration_bytes,
        target_record=target_record, target_content=target_content,
        target_hash=_raw_hash(target_content), recheck=recheck,
        recheck_bytes=recheck_bytes,
    )


def _shared_durable_files(inputs: _RunInputs) -> list[tuple[str, bytes]]:
    return [
        ("target.json", inputs.target_content),
        ("campaign-config.json", inputs.configuration_bytes),
        ("novelty-recheck.json", inputs.recheck_bytes),
    ]


def _retain_activation(
    *,
    args: argparse.Namespace,
    inputs: _RunInputs,
    activation: LiveProviderProbeResult,
    reason: str | None,
    detail: Mapping[str, Any],
) -> int:
    """Persist an activation-only ledger and exit 2, naming the terminal reason."""

    passed = activation.probe_status == "passed"
    terminal = (
        REFUSAL_ACTIVATION_RETAINED if passed else REFUSAL_ACTIVATION_FAILED
    )
    rationale = (
        (
            "The single no-retry provider activation succeeded but no campaign "
            "action was admitted, so the paid request is retained and the "
            "campaign is terminal."
        ) if passed else (
            "The single no-retry provider activation failed, so no mathematical "
            "campaign action was admitted."
        )
    )
    root: Path = args.root
    root.mkdir(parents=True, exist_ok=True)
    artifacts = FileArtifactStore(root / "artifacts")
    try:
        export = _activation_only_ledger(
            campaign_id=args.campaign_id, target_hash=inputs.target_hash,
            configuration_hash=inputs.configuration.content_hash,
            activation=activation, artifacts=artifacts, rationale=rationale,
        )
        facts = campaign_facts(export, inputs.recheck, inputs.configuration)
        _write_durable(root, [
            *_shared_durable_files(inputs),
            ("activation.json", canonical_bytes(activation) + b"\n"),
            ("campaign-facts.json", canonical_bytes(facts) + b"\n"),
            ("campaign.json", export_campaign_bytes(export)),
        ])
    except (
        CampaignRunnerError, CampaignProvenanceError, CampaignConfigurationError, OSError,
    ) as error:
        return _refuse(_rejection_reason(error), detail=str(error))
    try:
        report = _finish_terminal_report(root, export, facts, inputs.configuration)
    except (PublicationValidationError, CampaignConfigurationError, OSError) as error:
        report = _failed_terminal_report(error)
    _print({
        "status": "refused",
        "reason": terminal if reason is None else reason,
        "terminal_reason": terminal,
        "fallback_gateway_used": False,
        "failure_classification": activation.failure_classification,
        "root": str(root),
        "effects": _METER.snapshot(),
        "effect_measurement": effect_measurement(),
        "facts": facts,
        "publication_draft": report,
        **{key: value for key, value in detail.items() if key != "reason"},
    })
    return 2


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
    derived = campaign_facts(export, recheck, configuration)
    stored = _strict_json((root / "campaign-facts.json").read_bytes(), what="campaign facts")
    if not isinstance(stored, dict) or stored != derived:
        raise CampaignProvenanceError(REFUSAL_FACTS_MISMATCH)
    checks.append(("facts_are_derived_from_the_ledger", True))
    if dict(export.usage) != derive_usage(
        export.model_calls, export.tool_runs, export.imports,
    ):
        raise CampaignProvenanceError("campaign usage is not derived from its records")
    checks.append(("usage_rollups_recomputed_from_records", True))
    # The one check here whose `passed` is not a constant: an over-budget campaign
    # stays readable, and every command that could present it as clean refuses.
    checks.append((
        "recorded_usage_is_within_configured_bounds",
        derived["bound_compliance"]["status"] == "within_bounds",
    ))
    return LoadedCampaign(
        export=export, facts=derived, stored_facts=stored, checks=tuple(checks),
    )


def _inspect(args: argparse.Namespace) -> int:
    with measure_effects():
        return _inspect_measured(args)


def _inspect_measured(args: argparse.Namespace) -> int:
    try:
        loaded = _load_campaign(args.root)
    except (
        CampaignProvenanceError, CampaignConfigurationError, NoveltyRecheckError, OSError,
        KeyError, TypeError,
    ) as error:
        return _refuse(str(error) or type(error).__name__)
    effects = _METER.snapshot()
    measurement = effect_measurement()
    if _METER.observed() or not _METER.hook_installed:
        return _refuse(
            REFUSAL_REPLAY_PERFORMED_WORK, root=str(args.root),
            effects=effects, effect_measurement=measurement,
        )
    compliance = loaded.facts["bound_compliance"]
    if compliance["status"] != "within_bounds":
        return _refuse(
            REFUSAL_BOUND_VIOLATION, root=str(args.root),
            exceeded_bounds=compliance["exceeded_bounds"],
            effects=effects, effect_measurement=measurement, **loaded.facts,
        )
    _print({
        "status": "verified", "root": str(args.root),
        "effects": effects, "effect_measurement": measurement, **loaded.facts,
    })
    return 0


def _replay(args: argparse.Namespace) -> int:
    with measure_effects():
        return _replay_measured(args)


def _replay_measured(args: argparse.Namespace) -> int:
    """Validate closure and derive the report without invoking a model or tool.

    The five effect counters below are MEASURED, not asserted. They used to be
    constant zeroes compared against a constant zero tuple by `make campaign`,
    which is a literal against a literal: an audit run that made this function
    open a UDP socket and start a process still reported `(0, 0, 0, 0, 0)` and
    still passed the gate.
    """

    try:
        loaded = _load_campaign(args.root)
        hashes = _artifact_hashes(loaded.export)
        expected = frozenset(hashes)
        _reconcile_artifact_store(args.root, expected)
        _reconcile_artifact_log(args.root, expected)
    except (
        CampaignProvenanceError, CampaignConfigurationError, CampaignRunnerError,
        NoveltyRecheckError, OSError, KeyError, TypeError,
    ) as error:
        return _refuse(str(error) or type(error).__name__)
    checks = [
        {"name": name, "passed": passed} for name, passed in loaded.checks
    ]
    checks.append({"name": "every_ledger_artifact_resolves_in_the_store", "passed": True})
    checks.append({
        "name": "artifact_store_holds_no_unrecorded_or_misnamed_file", "passed": True,
    })
    checks.append({"name": "artifact_log_matches_the_ledger", "passed": True})
    effects = _METER.snapshot()
    measurement = effect_measurement()
    compliance = loaded.facts["bound_compliance"]
    refusal: str | None = None
    if _METER.observed() or not _METER.hook_installed:
        refusal = REFUSAL_REPLAY_PERFORMED_WORK
    elif compliance["status"] != "within_bounds":
        refusal = REFUSAL_BOUND_VIOLATION
    _print({
        "schema_version": CAMPAIGN_REPLAY_SCHEMA_VERSION,
        "verified": refusal is None,
        "reason": refusal,
        "root": str(args.root),
        "checks": checks,
        "artifacts_resolved": len(hashes),
        "exceeded_bounds": compliance["exceeded_bounds"],
        **effects,
        "effect_measurement": measurement,
        "epistemic_warrant_created": False,
        "facts": loaded.facts,
    })
    return 0 if refusal is None else 2


def _export(args: argparse.Namespace) -> int:
    with measure_effects():
        return _export_measured(args)


def _export_measured(args: argparse.Namespace) -> int:
    try:
        loaded = _load_campaign(args.root)
        compliance = loaded.facts["bound_compliance"]
        if compliance["status"] != "within_bounds":
            # `publication build --campaign-export` reads exactly these bytes.
            # A campaign that exceeded its own caps may not leave this command
            # labelled as the input to a publication build.
            return _refuse(
                REFUSAL_BOUND_VIOLATION, root=str(args.root),
                exceeded_bounds=compliance["exceeded_bounds"],
            )
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


def _resume(args: argparse.Namespace) -> int:
    """Resume only deterministic terminal finalization; never repeat paid work."""

    with measure_effects():
        try:
            end_to_end_config = args.root / "end-to-end-runtime-config.json"
            if end_to_end_config.exists():
                from .campaign.fixture_runtime import run_fixture_campaign
                value = json.loads(end_to_end_config.read_text(encoding="utf-8"))
                summary = run_fixture_campaign(
                    args.root, data_root=Path(value["data_root"]),
                    campaign_id=value["campaign_id"], recorded_at=value["recorded_at"],
                    repository_root=Path(value["repository_root"]),
                    problem_bytes=None,
                )
                _print({
                    "status": summary["status"], "root": str(args.root),
                    "campaign_id": summary["campaign_id"],
                    "resume_scope": "action_level_end_to_end",
                    "paid_work_repeated": False, "summary": summary,
                })
                return 0 if summary["status"] == "completed" else 1
            loaded = _load_campaign(args.root)
            configuration = load_campaign_configuration(args.root / "campaign-config.json")
            report = _finish_terminal_report(
                args.root, loaded.export, loaded.facts, configuration,
            )
        except (
            CampaignProvenanceError, CampaignConfigurationError, NoveltyRecheckError,
            PublicationValidationError, OSError, KeyError, TypeError,
        ) as error:
            return _refuse(
                "campaign_terminal_resume_refused",
                root=str(args.root), detail=str(error) or type(error).__name__,
                resume_scope="terminal_finalization_only",
            )
        _print({
            "status": "finalized",
            "root": str(args.root),
            "campaign_id": loaded.export.campaign_id,
            "campaign_content_hash": loaded.export.content_hash,
            "resume_scope": "terminal_finalization_only",
            "paid_work_repeated": False,
            "publication_draft": report,
            "effects": _METER.snapshot(),
            "effect_measurement": effect_measurement(),
            "epistemic_warrant_created": False,
        })
        return 0


def _start(args: argparse.Namespace) -> int:
    """Initialize and run the one-command end-to-end fixture campaign."""

    try:
        from .campaign.fixture_runtime import run_fixture_campaign
        summary = run_fixture_campaign(
            args.root, data_root=args.data_root, campaign_id=args.campaign_id,
            recorded_at=args.recorded_at,
            repository_root=args.repository_root,
            problem_bytes=None if args.problem is None else args.problem.read_bytes(),
        )
    except Exception as error:
        return _refuse(
            "campaign_end_to_end_start_refused", root=str(args.root),
            detail=str(error) or type(error).__name__,
        )
    _print({
        "status": summary["status"], "root": str(args.root),
        "campaign_id": summary["campaign_id"],
        "resume_scope": "action_level_end_to_end", "summary": summary,
    })
    return 0 if summary["status"] == "completed" else 1


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
    # Slice 6 wiring (end-to-end runtime plan §3.6, ADR-0073). Without
    # `--experiment-activation` the pending runner remains and records why; an
    # activation record that does not strictly re-verify against the current
    # locks also keeps the pending runner, with the rejection reason recorded.
    run.add_argument("--experiment-activation", type=Path)
    run.add_argument(
        "--experiment-repository-root", type=Path, default=Path("."),
    )
    run.add_argument(
        "--experiment-target", type=Path, default=DEFAULT_EXPERIMENT_TARGET,
    )
    run.add_argument(
        "--formal-check-adapter", choices=("unavailable", "sealed"),
        default="unavailable",
    )

    start = commands.add_parser(
        "start", help="initialize and run/resume one end-to-end campaign",
    )
    start.add_argument("root", type=Path)
    start.add_argument("campaign_id")
    start.add_argument("--data-root", type=Path, required=True)
    start.add_argument("--recorded-at", required=True)
    start.add_argument("--repository-root", type=Path, default=Path("."))
    start.add_argument("--problem", type=Path)

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

    resume = commands.add_parser(
        "resume",
        help="idempotently finish a verified terminal campaign without paid calls",
    )
    resume.add_argument("root", type=Path)

    args = parser.parse_args(argv)
    if args.command == "config-create":
        return _config_create(args)
    if args.command == "target":
        return _target(args)
    if args.command == "run":
        return _run(args)
    if args.command == "start":
        return _start(args)
    if args.command == "inspect":
        return _inspect(args)
    if args.command == "replay":
        return _replay(args)
    if args.command == "export":
        return _export(args)
    if args.command == "resume":
        return _resume(args)
    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
