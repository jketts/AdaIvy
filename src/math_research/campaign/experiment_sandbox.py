"""Digest-pinned OCI sandbox for model-authored campaign experiment code.

This module is the gate ADR-0057 section 2 defers to, specified by ADR-0066.  It
is the only production implementation of
:class:`math_research.campaign.runner.CampaignExperimentRunner`, and it is
fail-closed in three independent ways:

1.  Request admission is a pure, offline, closed-vocabulary check.  A
    model-chosen host path, command, adapter, environment field, network target,
    or resource limit is refused before any process could be created.
2.  The image is addressed by digest only.  The shipped configuration ships the
    digest deliberately UNRESOLVED, so every call refuses with
    ``image_digest_unresolved`` until the repository owner pins it.  A missing,
    unpinned, or mismatched digest is a refusal and never a fallback.
3.  Execution additionally requires an owner-reviewed activation record.  With
    no activation the sandbox refuses with ``activation_not_authorized``.

This module contains NO process, socket, or container-engine code at all.  The
campaign package stays structurally free of them: the container launch is an
injected :class:`ExperimentLauncher` port whose only production implementation
is `src/math_research/experiment_oci_launcher.py`, named for what it needs.  A
sandbox constructed without a launcher refuses with ``launcher_unavailable``.

Nothing here creates an ``EpistemicWarrant``, discharges a proof obligation,
approves semantic alignment, asserts source applicability, or sets novelty or
significance.  A sandbox result is an untrusted observation.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import re
import tempfile
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Mapping, Protocol

from .records import (
    CampaignProvenanceError,
    RecordStatus,
    UsageSource,
    ValueEnum,
    canonical_bytes,
    canonical_hash,
)
from .runner import ExperimentRequest, ExperimentResult, ResourceLimits


SANDBOX_CONTRACT_VERSION = "adaivy.campaign-experiment-sandbox.v1"
IMAGE_LOCK_SCHEMA = "adaivy.campaign-experiment-oci-image-lock.v1"
POLICY_SCHEMA = "adaivy.campaign-experiment-sandbox-policy.v1"
RUNTIME_SCHEMA = "adaivy.campaign-experiment-oci-runtime-identity.v1"
ENVELOPE_SCHEMA = "adaivy.campaign-experiment-stdin-envelope.v1"
RESPONSE_SCHEMA = "adaivy.campaign-experiment-stdout-response.v1"
EVIDENCE_SCHEMA = "adaivy.campaign-experiment-sandbox-evidence.v1"
PROFILE_SCHEMA = "adaivy.campaign-experiment-sandbox-profile.v1"
ACTIVATION_SCHEMA = "adaivy.campaign-experiment-sandbox-activation.v1"

ADAPTER_ID = "campaign_experiment_oci_python"
ADAPTER_VERSION = "1.0.0"

# The Phase 4B parser image. ADR-0057 section 2: "The Phase 4B parser image is a
# precedent, not authorization to reuse a parser-specific sandbox for generated
# code."  Pinning it here would silently reuse a parser profile for generated
# code, so it is refused by digest.  `tests/test_campaign_experiment_sandbox.py`
# asserts this constant still equals the digest in
# `config/phase4b-oci-image-linux-arm64-v1.json`, so the refusal cannot drift
# away from the image it is meant to exclude.
PHASE4B_PARSER_IMAGE_DIGEST = (
    "sha256:6b8f06d04d5305c1d1288435388df9165ab41e681fae6439d6349d8053cc3f83"
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_TOOL_ID = re.compile(r"^[a-z][a-z0-9_]{2,47}$")
_ARGUMENT = re.compile(r"^[a-z][a-z0-9_]{0,31}=[A-Za-z0-9_.:+,-]{1,64}$")
_REPOSITORY = re.compile(
    r"^[a-z0-9][a-z0-9._-]*(?:\.[a-z0-9._-]+)?(?:/[a-z0-9][a-z0-9._-]*)+$"
)
_PLATFORM = re.compile(r"^linux/(?:amd64|arm64)$")
_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")


class ExperimentRefusal(ValueEnum):
    """Closed vocabulary of machine-readable sandbox refusal reasons."""

    IDENTIFIER_FORBIDDEN = "identifier_forbidden"
    UNKNOWN_TOOL_ADAPTER = "unknown_tool_adapter"
    SHELL_ADAPTER_FORBIDDEN = "shell_adapter_forbidden"
    NETWORK_FORBIDDEN = "network_forbidden"
    HOST_PATH_FORBIDDEN = "host_path_forbidden"
    ARGUMENT_FORBIDDEN = "argument_forbidden"
    ARGUMENT_COUNT_EXCEEDS_BOUND = "argument_count_exceeds_bound"
    PROGRAM_BYTES_EXCEED_BOUND = "program_bytes_exceed_bound"
    PROGRAM_HASH_MISMATCH = "program_hash_mismatch"
    PROGRAM_SOURCE_NOT_PARSABLE = "program_source_not_parsable"
    PROGRAM_IMPORT_FORBIDDEN = "program_import_forbidden"
    PROGRAM_NETWORK_IMPORT_FORBIDDEN = "program_network_import_forbidden"
    PROGRAM_REFLECTION_FORBIDDEN = "program_reflection_forbidden"
    PROGRAM_DYNAMIC_EXECUTION_FORBIDDEN = "program_dynamic_execution_forbidden"
    PROGRAM_FILESYSTEM_ACCESS_FORBIDDEN = "program_filesystem_access_forbidden"
    INPUT_COUNT_EXCEEDS_BOUND = "input_count_exceeds_bound"
    INPUT_BYTES_EXCEED_BOUND = "input_bytes_exceed_bound"
    INPUT_HASH_MISMATCH = "input_hash_mismatch"
    INPUT_DUPLICATE_HASH = "input_duplicate_hash"
    RESOURCE_LIMIT_EXCEEDS_PROFILE = "resource_limit_exceeds_profile"
    RESOURCE_LIMIT_BELOW_PROFILE_FLOOR = "resource_limit_below_profile_floor"
    RESOURCE_LIMIT_MALFORMED = "resource_limit_malformed"
    ENVELOPE_MALFORMED = "envelope_malformed"
    ENVELOPE_DUPLICATE_KEY = "envelope_duplicate_key"
    ENVELOPE_UNKNOWN_FIELD = "envelope_unknown_field"
    ENVELOPE_SCHEMA_VERSION_UNKNOWN = "envelope_schema_version_unknown"
    ENVIRONMENT_FIELD_FORBIDDEN = "environment_field_forbidden"
    STDIN_ENVELOPE_EXCEEDS_BOUND = "stdin_envelope_exceeds_bound"
    IMAGE_LOCK_MALFORMED = "image_lock_malformed"
    IMAGE_LOCK_DUPLICATE_KEY = "image_lock_duplicate_key"
    IMAGE_LOCK_UNKNOWN_FIELD = "image_lock_unknown_field"
    IMAGE_LOCK_SCHEMA_VERSION_UNKNOWN = "image_lock_schema_version_unknown"
    IMAGE_DIGEST_UNRESOLVED = "image_digest_unresolved"
    IMAGE_DIGEST_MISMATCH = "image_digest_mismatch"
    IMAGE_ROLE_NOT_GENERATED_CODE = "image_role_not_generated_code"
    PARSER_IMAGE_REUSE_FORBIDDEN = "parser_image_reuse_forbidden"
    PROFILE_DECLARATION_MISMATCH = "profile_declaration_mismatch"
    LANGUAGE_SURFACE_DECLARATION_MISMATCH = "language_surface_declaration_mismatch"
    PROFILE_OUTSIDE_ADR_ENVELOPE = "profile_outside_adr_envelope"
    ACTIVATION_NOT_AUTHORIZED = "activation_not_authorized"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    RUNTIME_IDENTITY_MISMATCH = "runtime_identity_mismatch"
    LAUNCHER_UNAVAILABLE = "launcher_unavailable"
    LAUNCH_FAILED = "launch_failed"
    CONTROL_STATE_UNAVAILABLE = "control_state_unavailable"
    WALL_LIMIT_EXCEEDED = "wall_limit_exceeded"
    CPU_LIMIT_EXCEEDED = "cpu_limit_exceeded"
    MEMORY_LIMIT_EXCEEDED = "memory_limit_exceeded"
    STDOUT_LIMIT_EXCEEDED = "stdout_limit_exceeded"
    STDERR_LIMIT_EXCEEDED = "stderr_limit_exceeded"
    WORKER_FAILED = "worker_failed"
    WORKER_RESPONSE_INVALID = "worker_response_invalid"
    RESULT_HASH_MISMATCH = "result_hash_mismatch"


class ExperimentSandboxRefusal(CampaignProvenanceError):
    """A named, machine-readable refusal. No execution occurred or was retained."""

    def __init__(
        self, reason: ExperimentRefusal, *, field: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(reason.value + (f" [{field}]" if field else ""))
        self.reason = reason
        self.field = field
        self.detail = detail

    def record(self) -> dict[str, Any]:
        value = {
            "detail": self.detail,
            "epistemic_warrant_created": False,
            "field": self.field,
            "reason": self.reason.value,
            "schema_version": SANDBOX_CONTRACT_VERSION,
            "trust_effect": "untrusted_observation",
            "verdict": "refused_before_execution",
        }
        value["content_hash"] = canonical_hash(value)
        return value


def _refuse(
    reason: ExperimentRefusal, *, field: str | None = None, detail: str | None = None,
) -> ExperimentSandboxRefusal:
    return ExperimentSandboxRefusal(reason, field=field, detail=detail)


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _closed_object(
    raw: bytes | str, *, malformed: ExperimentRefusal, duplicate: ExperimentRefusal,
    label: str,
) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise _refuse(duplicate, field=key, detail=label)
            result[key] = value
        return result

    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        value = json.loads(text, object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _refuse(malformed, detail=label) from error
    if not isinstance(value, dict):
        raise _refuse(malformed, detail=label)
    return value


# ---------------------------------------------------------------------------
# Bounded language surface for generated programs
# ---------------------------------------------------------------------------

# ADR-0066: the language and package set available to a generated program is
# bounded and narrow, and ADR-0057's revisit trigger fires before it widens.
# Every entry is standard library and has no filesystem, process, or network
# surface.  This static admission check is DEFENCE IN DEPTH and is not a
# security boundary by itself: Python reflection cannot be statically excluded
# in general.  The container is the containment.
ALLOWED_IMPORT_MODULES = frozenset({
    "array", "bisect", "collections", "collections.abc", "dataclasses",
    "enum", "fractions", "functools", "heapq", "itertools", "json", "math",
    "numbers", "operator", "string", "sys", "textwrap", "typing",
})

# Named so a network attempt inside a generated program is refused under its own
# reason rather than the generic import refusal.
NETWORK_IMPORT_MODULES = frozenset({
    "aiohttp", "asyncio", "ftplib", "http", "httpx", "imaplib", "poplib",
    "requests", "selectors", "smtplib", "socket", "socketserver", "ssl",
    "telnetlib", "urllib", "urllib3", "webbrowser", "xmlrpc",
})

FORBIDDEN_PROGRAM_NAMES = frozenset({
    "__import__", "breakpoint", "compile", "eval", "exec", "exit", "globals",
    "help", "input", "locals", "open", "quit", "vars",
})

FORBIDDEN_PROGRAM_ATTRIBUTES = frozenset({
    "__bases__", "__builtins__", "__class__", "__code__", "__dict__",
    "__getattribute__", "__globals__", "__import__", "__loader__", "__mro__",
    "__reduce__", "__reduce_ex__", "__spec__", "__subclasses__",
})

# Any tool identifier whose tokens intersect this set is a shell or process
# adapter and is refused under its own reason (ADR-0057 acceptance gate 2).
SHELL_TOOL_TOKENS = frozenset({
    "bash", "cmd", "curl", "dash", "docker", "eval", "exec", "fish", "git",
    "http", "network", "pip", "popen", "powershell", "sh", "shell", "socket",
    "ssh", "subprocess", "system", "wget", "zsh",
})

ADMITTED_TOOL_IDS = frozenset({"exact_python_search"})


def _admit_module(name: str) -> None:
    root = name.split(".", 1)[0]
    if root in NETWORK_IMPORT_MODULES or name in NETWORK_IMPORT_MODULES:
        raise _refuse(ExperimentRefusal.PROGRAM_NETWORK_IMPORT_FORBIDDEN, field=name)
    if name not in ALLOWED_IMPORT_MODULES and root not in ALLOWED_IMPORT_MODULES:
        raise _refuse(ExperimentRefusal.PROGRAM_IMPORT_FORBIDDEN, field=name)


def _admit_program_source(source: bytes) -> str:
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _refuse(
            ExperimentRefusal.PROGRAM_SOURCE_NOT_PARSABLE, detail="not utf-8",
        ) from error
    try:
        tree = ast.parse(text, filename="<campaign-generated-program>")
    except (SyntaxError, ValueError, RecursionError) as error:
        raise _refuse(
            ExperimentRefusal.PROGRAM_SOURCE_NOT_PARSABLE, detail="syntax",
        ) from error
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _admit_module(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 or not node.module:
                raise _refuse(
                    ExperimentRefusal.PROGRAM_IMPORT_FORBIDDEN, field="relative_import",
                )
            _admit_module(node.module)
            if any(alias.name == "*" for alias in node.names):
                raise _refuse(
                    ExperimentRefusal.PROGRAM_IMPORT_FORBIDDEN, field="star_import",
                )
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_PROGRAM_ATTRIBUTES:
                raise _refuse(
                    ExperimentRefusal.PROGRAM_REFLECTION_FORBIDDEN, field=node.attr,
                )
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_PROGRAM_NAMES:
            if node.id in {"__import__", "compile", "eval", "exec"}:
                reason = ExperimentRefusal.PROGRAM_DYNAMIC_EXECUTION_FORBIDDEN
            elif node.id == "open":
                reason = ExperimentRefusal.PROGRAM_FILESYSTEM_ACCESS_FORBIDDEN
            else:
                reason = ExperimentRefusal.PROGRAM_REFLECTION_FORBIDDEN
            raise _refuse(reason, field=node.id)
    return text


# ---------------------------------------------------------------------------
# Sandbox profile
# ---------------------------------------------------------------------------

# Every number below is derived in ADR-0066 before any fixture existed.  A
# profile may tighten a bound and may never loosen one.
_ADR_CEILINGS: Mapping[str, int] = {
    "max_cpu_milliseconds": 120_000,
    "max_wall_milliseconds": 120_000,
    "max_memory_bytes": 1_073_741_824,
    "max_output_bytes": 1_048_576,
    "max_process_count": 4,
    "max_open_files": 64,
    "max_temp_inodes": 64,
    "max_file_bytes": 8_388_608,
    "max_temp_bytes": 8_388_608,
    "max_work_bytes": 8_388_608,
    "max_stdin_envelope_bytes": 4_194_304,
    "max_program_bytes": 262_144,
    "max_input_artifacts": 8,
    "max_input_bytes_each": 1_048_576,
    "max_input_bytes_total": 4_194_304,
    "max_arguments": 16,
}

# Floors exist because a container cannot honour an arbitrarily small bound: the
# runtime's own documented minimum memory is 6 MiB and a CPython interpreter
# needs materially more, and a container start costs hundreds of milliseconds.
# A declared bound below a floor is a refusal, never a silent widening.
_ADR_FLOORS: Mapping[str, int] = {
    "cpu_milliseconds": 1_000,
    "wall_milliseconds": 1_000,
    "memory_bytes": 67_108_864,
    "output_bytes": 1_024,
    "process_count": 1,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentSandboxProfile:
    """Non-negotiable sandbox bounds. No model input can reach any field."""

    max_cpu_milliseconds: int = _ADR_CEILINGS["max_cpu_milliseconds"]
    max_wall_milliseconds: int = _ADR_CEILINGS["max_wall_milliseconds"]
    max_memory_bytes: int = _ADR_CEILINGS["max_memory_bytes"]
    max_output_bytes: int = _ADR_CEILINGS["max_output_bytes"]
    max_process_count: int = _ADR_CEILINGS["max_process_count"]
    max_open_files: int = _ADR_CEILINGS["max_open_files"]
    max_temp_inodes: int = _ADR_CEILINGS["max_temp_inodes"]
    max_file_bytes: int = _ADR_CEILINGS["max_file_bytes"]
    max_temp_bytes: int = _ADR_CEILINGS["max_temp_bytes"]
    max_work_bytes: int = _ADR_CEILINGS["max_work_bytes"]
    max_stdin_envelope_bytes: int = _ADR_CEILINGS["max_stdin_envelope_bytes"]
    max_program_bytes: int = _ADR_CEILINGS["max_program_bytes"]
    max_input_artifacts: int = _ADR_CEILINGS["max_input_artifacts"]
    max_input_bytes_each: int = _ADR_CEILINGS["max_input_bytes_each"]
    max_input_bytes_total: int = _ADR_CEILINGS["max_input_bytes_total"]
    max_arguments: int = _ADR_CEILINGS["max_arguments"]

    def __post_init__(self) -> None:
        for name, ceiling in _ADR_CEILINGS.items():
            value = getattr(self, name)
            if (
                isinstance(value, bool) or not isinstance(value, int)
                or not 1 <= value <= ceiling
            ):
                raise _refuse(ExperimentRefusal.PROFILE_OUTSIDE_ADR_ENVELOPE, field=name)
        floors = {
            "max_cpu_milliseconds": _ADR_FLOORS["cpu_milliseconds"],
            "max_wall_milliseconds": _ADR_FLOORS["wall_milliseconds"],
            "max_memory_bytes": _ADR_FLOORS["memory_bytes"],
            "max_output_bytes": _ADR_FLOORS["output_bytes"],
            "max_process_count": _ADR_FLOORS["process_count"],
        }
        for name, floor in floors.items():
            if getattr(self, name) < floor:
                raise _refuse(ExperimentRefusal.PROFILE_OUTSIDE_ADR_ENVELOPE, field=name)

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": PROFILE_SCHEMA,
            **{item.name: getattr(self, item.name) for item in fields(self)},
        }


EXPERIMENT_PROFILE = ExperimentSandboxProfile()

# The container environment is fixed here and is the complete set.  The model
# supplies no environment variable, and `ExperimentRequest` carries no
# environment field, so an environment entry cannot arrive from a planner
# action.  `PYTHONHASHSEED=0` requires that `-I`/`-E` are NOT used, which is
# safe precisely because this mapping is the whole environment.
CONTAINER_ENVIRONMENT: Mapping[str, str] = {
    "HOME": "/work",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
    "PYTHONSAFEPATH": "1",
}


# ---------------------------------------------------------------------------
# Named controls
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class SandboxControl:
    """One ADR-0057 section 2 control and how its enforcement is proven."""

    name: str
    clause: str
    mechanism: str
    command_evidence: tuple[str, ...]
    proof: str

    def to_record(self) -> dict[str, Any]:
        value = {item.name: getattr(self, item.name) for item in fields(self)}
        value["command_evidence"] = list(self.command_evidence)
        return value


_PENDING = "kernel_measured_pending_container_gate"

CONTAINER_CONTROLS: tuple[SandboxControl, ...] = (
    SandboxControl(
        name="digest_pinned_image", clause="a digest-pinned image",
        mechanism="image addressed only as repository@sha256 with --pull=never",
        command_evidence=("--pull=never",),
        proof="offline_digest_gate_and_command_construction",
    ),
    SandboxControl(
        name="no_network", clause="no network",
        mechanism="OCI network namespace none",
        command_evidence=("--network=none",), proof=_PENDING,
    ),
    SandboxControl(
        name="read_only_root", clause="a read-only root",
        mechanism="read-only root filesystem with no bind mount or volume",
        command_evidence=("--read-only",), proof=_PENDING,
    ),
    SandboxControl(
        name="noexec_empty_temporary", clause="an empty noexec temporary filesystem",
        mechanism="fresh tmpfs at /tmp with noexec,nosuid,nodev and bounded "
                  "size and nr_inodes",
        command_evidence=("--tmpfs=/tmp:rw,noexec,nosuid,nodev,",), proof=_PENDING,
    ),
    SandboxControl(
        name="no_inherited_credentials", clause="no inherited credentials",
        mechanism="closed client environment, closed container environment, "
                  "--cap-drop=ALL, no-new-privileges, uid/gid 65534",
        command_evidence=(
            "--cap-drop=ALL", "--security-opt=no-new-privileges=true",
            "--user=65534:65534",
        ),
        proof="offline_command_construction_and_" + _PENDING,
    ),
    SandboxControl(
        name="fresh_work_directory", clause="a fresh work directory",
        mechanism="per-container tmpfs at /work as the only writable work directory",
        command_evidence=("--tmpfs=/work:rw,noexec,nosuid,nodev,", "--workdir=/work"),
        proof=_PENDING,
    ),
    SandboxControl(
        name="bounded_json_streams", clause="bounded JSON stdin/stdout/stderr",
        mechanism="closed stdin envelope under a byte bound; non-blocking reads "
                  "truncated and the container killed at the stdout/stderr bound",
        command_evidence=("--interactive",),
        proof="offline_envelope_bound_and_" + _PENDING,
    ),
    SandboxControl(
        name="wall_limit", clause="a hard wall limit",
        mechanism="monotonic parent deadline followed by a container kill",
        command_evidence=(), proof=_PENDING,
    ),
    SandboxControl(
        name="cpu_limit", clause="a hard CPU limit",
        mechanism="kernel RLIMIT_CPU plus a single-CPU cgroup quota",
        command_evidence=("--cpus=1.0",), proof=_PENDING,
    ),
    SandboxControl(
        name="memory_limit", clause="a hard memory limit",
        mechanism="cgroup memory and memory-swap hard ceiling",
        command_evidence=(), proof=_PENDING,
    ),
    SandboxControl(
        name="process_limit", clause="a hard process limit",
        mechanism="cgroup pids limit",
        command_evidence=(), proof=_PENDING,
    ),
    SandboxControl(
        name="file_count_limit", clause="a hard file-count limit",
        mechanism="RLIMIT_NOFILE plus tmpfs nr_inodes",
        command_evidence=(), proof=_PENDING,
    ),
    SandboxControl(
        name="file_size_limit", clause="a hard file-size limit",
        mechanism="RLIMIT_FSIZE plus a bounded tmpfs size",
        command_evidence=(), proof=_PENDING,
    ),
    SandboxControl(
        name="content_addressed_io",
        clause="inputs and outputs are content-addressed",
        mechanism="every program and input byte string is checked against its "
                  "declared sha256 before launch and the response result hash is "
                  "recomputed afterwards",
        command_evidence=(), proof="offline_hash_check",
    ),
    SandboxControl(
        name="no_model_chosen_invocation",
        clause="the model cannot choose a host path, command, image, environment "
               "variable, network target, or resource limit",
        mechanism="closed adapter allowlist, closed argument grammar, fixed image "
                  "and command vector, fixed environment, network=none only, and "
                  "declared limits validated against a fixed profile",
        command_evidence=(), proof="offline_request_admission",
    ),
)


# ---------------------------------------------------------------------------
# Request admission
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class AdmittedExperiment:
    """A request that passed every pre-execution control."""

    campaign_id: str
    action_id: str
    tool_id: str
    program_artifact_hash: str
    program_text: str
    input_artifacts: tuple[tuple[str, bytes], ...]
    arguments: tuple[str, ...]
    declared_limits: ResourceLimits
    effective_limits: ResourceLimits

    def request_record(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "arguments": list(self.arguments),
            "campaign_id": self.campaign_id,
            "declared_limits": {
                item.name: getattr(self.declared_limits, item.name)
                for item in fields(self.declared_limits)
            },
            "effective_limits": {
                item.name: getattr(self.effective_limits, item.name)
                for item in fields(self.effective_limits)
            },
            "input_artifact_hashes": [item[0] for item in self.input_artifacts],
            "network": "none",
            "program_artifact_hash": self.program_artifact_hash,
            "schema_version": SANDBOX_CONTRACT_VERSION,
            "tool_id": self.tool_id,
        }


def _looks_like_path(value: str) -> bool:
    """A host path, path traversal, or NUL byte. A leading `-` is a command flag
    rather than a path and is refused by the argument grammar instead."""

    return (
        "/" in value or "\\" in value or "~" in value or ".." in value
        or "\x00" in value
    )


def _admit_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) or len(value) > 128:
        raise _refuse(ExperimentRefusal.IDENTIFIER_FORBIDDEN, field=field)
    return value


def _admit_limits(
    declared: object, profile: ExperimentSandboxProfile,
) -> tuple[ResourceLimits, ResourceLimits]:
    if not isinstance(declared, ResourceLimits):
        raise _refuse(ExperimentRefusal.RESOURCE_LIMIT_MALFORMED, field="resource_limits")
    ceilings = {
        "cpu_milliseconds": profile.max_cpu_milliseconds,
        "wall_milliseconds": profile.max_wall_milliseconds,
        "memory_bytes": profile.max_memory_bytes,
        "output_bytes": profile.max_output_bytes,
        "process_count": profile.max_process_count,
    }
    effective: dict[str, int] = {}
    for name in sorted(ceilings):
        value = getattr(declared, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise _refuse(ExperimentRefusal.RESOURCE_LIMIT_MALFORMED, field=name)
        if value > ceilings[name]:
            raise _refuse(ExperimentRefusal.RESOURCE_LIMIT_EXCEEDS_PROFILE, field=name)
        if value < _ADR_FLOORS[name]:
            raise _refuse(
                ExperimentRefusal.RESOURCE_LIMIT_BELOW_PROFILE_FLOOR, field=name,
            )
        # A declaration may only tighten. The profile ceiling is never reachable
        # by widening a declared bound.
        effective[name] = min(value, ceilings[name])
    return declared, ResourceLimits(**effective)


def validate_experiment_request(
    request: ExperimentRequest, *,
    profile: ExperimentSandboxProfile = EXPERIMENT_PROFILE,
) -> AdmittedExperiment:
    """Admit or refuse one experiment request. Pure; opens nothing.

    This is the complete pre-execution control surface for everything the model
    can influence.  It runs before, and independently of, the image digest and
    activation gates, so a model-chosen violation is always named precisely.
    """

    if not isinstance(request, ExperimentRequest):
        raise _refuse(ExperimentRefusal.ENVELOPE_MALFORMED, field="request")
    campaign_id = _admit_identifier(request.campaign_id, "campaign_id")
    action_id = _admit_identifier(request.action_id, "action_id")

    tool_id = request.tool_id
    if not isinstance(tool_id, str) or not _TOOL_ID.fullmatch(tool_id):
        raise _refuse(ExperimentRefusal.UNKNOWN_TOOL_ADAPTER, field="tool_id")
    if set(re.split(r"[._:-]", tool_id)) & SHELL_TOOL_TOKENS:
        raise _refuse(ExperimentRefusal.SHELL_ADAPTER_FORBIDDEN, field=tool_id)
    if tool_id not in ADMITTED_TOOL_IDS:
        raise _refuse(ExperimentRefusal.UNKNOWN_TOOL_ADAPTER, field=tool_id)

    if request.network != "none":
        raise _refuse(ExperimentRefusal.NETWORK_FORBIDDEN, field="network")

    arguments = request.arguments
    if not isinstance(arguments, tuple):
        raise _refuse(ExperimentRefusal.ARGUMENT_FORBIDDEN, field="arguments")
    if len(arguments) > profile.max_arguments:
        raise _refuse(ExperimentRefusal.ARGUMENT_COUNT_EXCEEDS_BOUND, field="arguments")
    for item in arguments:
        if not isinstance(item, str):
            raise _refuse(ExperimentRefusal.ARGUMENT_FORBIDDEN, field="arguments")
        if _looks_like_path(item):
            raise _refuse(ExperimentRefusal.HOST_PATH_FORBIDDEN, field=item)
        if not _ARGUMENT.fullmatch(item):
            raise _refuse(ExperimentRefusal.ARGUMENT_FORBIDDEN, field=item)

    program_hash = request.program_artifact_hash
    if not isinstance(program_hash, str) or not _SHA256.fullmatch(program_hash):
        raise _refuse(
            ExperimentRefusal.PROGRAM_HASH_MISMATCH, field="program_artifact_hash",
        )
    source = request.program_source
    if not isinstance(source, bytes) or not source:
        raise _refuse(ExperimentRefusal.PROGRAM_SOURCE_NOT_PARSABLE, field="program_source")
    if len(source) > profile.max_program_bytes:
        raise _refuse(ExperimentRefusal.PROGRAM_BYTES_EXCEED_BOUND, field="program_source")
    if _sha256(source) != program_hash:
        raise _refuse(ExperimentRefusal.PROGRAM_HASH_MISMATCH, field="program_source")
    program_text = _admit_program_source(source)

    inputs = request.input_artifacts
    if not isinstance(inputs, tuple):
        raise _refuse(ExperimentRefusal.ENVELOPE_MALFORMED, field="input_artifacts")
    if len(inputs) > profile.max_input_artifacts:
        raise _refuse(ExperimentRefusal.INPUT_COUNT_EXCEEDS_BOUND, field="input_artifacts")
    seen: set[str] = set()
    total = 0
    for item in inputs:
        if (
            not isinstance(item, tuple) or len(item) != 2
            or not isinstance(item[0], str) or not isinstance(item[1], bytes)
        ):
            raise _refuse(ExperimentRefusal.ENVELOPE_MALFORMED, field="input_artifacts")
        content_hash, content = item
        if not _SHA256.fullmatch(content_hash):
            raise _refuse(ExperimentRefusal.INPUT_HASH_MISMATCH, field=content_hash)
        if content_hash in seen:
            raise _refuse(ExperimentRefusal.INPUT_DUPLICATE_HASH, field=content_hash)
        seen.add(content_hash)
        if len(content) > profile.max_input_bytes_each:
            raise _refuse(ExperimentRefusal.INPUT_BYTES_EXCEED_BOUND, field=content_hash)
        total += len(content)
        if total > profile.max_input_bytes_total:
            raise _refuse(
                ExperimentRefusal.INPUT_BYTES_EXCEED_BOUND, field="input_artifacts",
            )
        if _sha256(content) != content_hash:
            raise _refuse(ExperimentRefusal.INPUT_HASH_MISMATCH, field=content_hash)

    declared, effective = _admit_limits(request.resource_limits, profile)
    return AdmittedExperiment(
        campaign_id=campaign_id, action_id=action_id, tool_id=tool_id,
        program_artifact_hash=program_hash, program_text=program_text,
        input_artifacts=tuple(sorted(inputs)), arguments=arguments,
        declared_limits=declared, effective_limits=effective,
    )


# ---------------------------------------------------------------------------
# Bounded JSON stdin envelope
# ---------------------------------------------------------------------------

_ENVELOPE_FIELDS = frozenset({
    "arguments", "input_artifacts", "program_sha256", "program_source",
    "schema_version",
})
_ENVIRONMENT_FIELD_NAMES = frozenset({
    "env", "environ", "environment", "environment_variables",
})
RESPONSE_FIELDS = frozenset({
    "cpu_milliseconds", "peak_memory_kib", "result_base64", "result_sha256",
    "schema_version", "status",
})


def build_stdin_envelope(
    admitted: AdmittedExperiment, *,
    profile: ExperimentSandboxProfile = EXPERIMENT_PROFILE,
) -> bytes:
    """Serialize the closed, deterministic stdin envelope."""

    payload = {
        "arguments": list(admitted.arguments),
        "input_artifacts": [
            {
                "content_base64": base64.b64encode(content).decode("ascii"),
                "content_hash": content_hash,
            }
            for content_hash, content in admitted.input_artifacts
        ],
        "program_sha256": admitted.program_artifact_hash.removeprefix("sha256:"),
        "program_source": admitted.program_text,
        "schema_version": ENVELOPE_SCHEMA,
    }
    raw = json.dumps(
        payload, allow_nan=False, ensure_ascii=False, separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(raw) > profile.max_stdin_envelope_bytes:
        raise _refuse(
            ExperimentRefusal.STDIN_ENVELOPE_EXCEEDS_BOUND, field="stdin_envelope",
        )
    return raw


def parse_stdin_envelope(
    raw: bytes, *, profile: ExperimentSandboxProfile = EXPERIMENT_PROFILE,
) -> dict[str, Any]:
    """Fail-closed re-parse of the stdin envelope.

    The in-container bootstrap performs the same checks.  Exposing them here
    lets the offline suite prove the closed schema, the duplicate-key refusal,
    the unknown-field refusal, the unknown-schema-version refusal, the
    environment-field refusal, and the byte bound without a container.
    """

    if not isinstance(raw, bytes):
        raise _refuse(ExperimentRefusal.ENVELOPE_MALFORMED, field="stdin_envelope")
    if len(raw) > profile.max_stdin_envelope_bytes:
        raise _refuse(
            ExperimentRefusal.STDIN_ENVELOPE_EXCEEDS_BOUND, field="stdin_envelope",
        )
    value = _closed_object(
        raw, malformed=ExperimentRefusal.ENVELOPE_MALFORMED,
        duplicate=ExperimentRefusal.ENVELOPE_DUPLICATE_KEY, label="stdin_envelope",
    )
    observed = frozenset(value)
    for name in sorted(observed - _ENVELOPE_FIELDS):
        if name in _ENVIRONMENT_FIELD_NAMES:
            raise _refuse(ExperimentRefusal.ENVIRONMENT_FIELD_FORBIDDEN, field=name)
        raise _refuse(ExperimentRefusal.ENVELOPE_UNKNOWN_FIELD, field=name)
    if observed != _ENVELOPE_FIELDS:
        raise _refuse(
            ExperimentRefusal.ENVELOPE_MALFORMED, field="stdin_envelope",
            detail="missing field",
        )
    if value["schema_version"] != ENVELOPE_SCHEMA:
        raise _refuse(
            ExperimentRefusal.ENVELOPE_SCHEMA_VERSION_UNKNOWN, field="schema_version",
        )
    source = value["program_source"]
    if not isinstance(source, str) or not source:
        raise _refuse(ExperimentRefusal.PROGRAM_SOURCE_NOT_PARSABLE, field="program_source")
    if hashlib.sha256(source.encode("utf-8")).hexdigest() != value["program_sha256"]:
        raise _refuse(ExperimentRefusal.PROGRAM_HASH_MISMATCH, field="program_sha256")
    artifacts = value["input_artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) > profile.max_input_artifacts:
        raise _refuse(ExperimentRefusal.INPUT_COUNT_EXCEEDS_BOUND, field="input_artifacts")
    for item in artifacts:
        if not isinstance(item, dict) or frozenset(item) != frozenset(
            {"content_base64", "content_hash"}
        ):
            raise _refuse(ExperimentRefusal.ENVELOPE_UNKNOWN_FIELD, field="input_artifacts")
        try:
            content = base64.b64decode(item["content_base64"], validate=True)
        except (TypeError, ValueError) as error:
            raise _refuse(
                ExperimentRefusal.ENVELOPE_MALFORMED, field="content_base64",
            ) from error
        if _sha256(content) != item["content_hash"]:
            raise _refuse(
                ExperimentRefusal.INPUT_HASH_MISMATCH, field=str(item["content_hash"]),
            )
    arguments = value["arguments"]
    if not isinstance(arguments, list) or len(arguments) > profile.max_arguments:
        raise _refuse(ExperimentRefusal.ARGUMENT_COUNT_EXCEEDS_BOUND, field="arguments")
    for item in arguments:
        if not isinstance(item, str) or _looks_like_path(item):
            raise _refuse(ExperimentRefusal.HOST_PATH_FORBIDDEN, field="arguments")
        if not _ARGUMENT.fullmatch(item):
            raise _refuse(ExperimentRefusal.ARGUMENT_FORBIDDEN, field="arguments")
    return value


# The in-container bootstrap.  It re-checks the closed envelope and the content
# addresses, redirects the generated program's stdout into a buffer, and emits a
# single closed response envelope carrying the result and its sha256.  The
# bootstrap uses `compile`/`exec`; the generated program may not (see
# FORBIDDEN_PROGRAM_NAMES).
_BOOTSTRAP = r'''import base64, hashlib, io, json, resource, sys
def pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise SystemExit(91)
        out[key] = value
    return out
envelope = json.loads(sys.stdin.buffer.read().decode("utf-8"), object_pairs_hook=pairs)
if set(envelope) != {
    "arguments", "input_artifacts", "program_sha256", "program_source", "schema_version",
}:
    raise SystemExit(92)
if envelope["schema_version"] != "adaivy.campaign-experiment-stdin-envelope.v1":
    raise SystemExit(93)
source = envelope["program_source"]
if not isinstance(source, str) or not source:
    raise SystemExit(94)
if hashlib.sha256(source.encode("utf-8")).hexdigest() != envelope["program_sha256"]:
    raise SystemExit(95)
inputs = {}
for item in envelope["input_artifacts"]:
    if set(item) != {"content_base64", "content_hash"}:
        raise SystemExit(96)
    data = base64.b64decode(item["content_base64"], validate=True)
    if "sha256:" + hashlib.sha256(data).hexdigest() != item["content_hash"]:
        raise SystemExit(97)
    inputs[item["content_hash"]] = item["content_base64"]
inner = json.dumps(
    {"arguments": envelope["arguments"], "input_artifacts": inputs},
    sort_keys=True, separators=(",", ":"),
)
captured = io.StringIO()
real = sys.stdout
sys.stdin = io.StringIO(inner)
sys.stdout = captured
try:
    exec(
        compile(source, "<campaign-generated-program>", "exec"),
        {"__name__": "__main__", "__builtins__": __builtins__},
    )
finally:
    sys.stdout = real
result = captured.getvalue().encode("utf-8")
usage = resource.getrusage(resource.RUSAGE_SELF)
real.write(json.dumps({
    "cpu_milliseconds": int((usage.ru_utime + usage.ru_stime) * 1000),
    "peak_memory_kib": int(usage.ru_maxrss),
    "result_base64": base64.b64encode(result).decode("ascii"),
    "result_sha256": "sha256:" + hashlib.sha256(result).hexdigest(),
    "schema_version": "adaivy.campaign-experiment-stdout-response.v1",
    "status": "completed",
}, sort_keys=True, separators=(",", ":")))
'''

BOOTSTRAP_SHA256 = _sha256(_BOOTSTRAP.encode("utf-8"))


# ---------------------------------------------------------------------------
# Image lock
# ---------------------------------------------------------------------------

_LOCK_FIELDS = frozenset({
    "allowed_import_modules", "authorization_status", "digest_status",
    "forbidden_reuse_digests", "image_digest", "image_reference",
    "image_repository", "network_default", "notes", "platform",
    "pull_policy", "resource_profile", "runtime_role", "schema_version",
})
_GENERATED_CODE_ROLE = "campaign_experiment_generated_code_only"
_UNRESOLVED_AUTHORIZATION = "unresolved_pending_owner_pin"
_PINNED_AUTHORIZATION = "authorized_for_bounded_generated_code_execution"


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentImageLock:
    """Owner-authored image pin. The digest may be deliberately unresolved."""

    digest_status: str
    image_repository: str
    image_reference: str | None
    image_digest: str | None
    platform: str
    authorization_status: str
    forbidden_reuse_digests: tuple[str, ...]
    notes: str

    @property
    def pinned(self) -> bool:
        return self.digest_status == "pinned"

    def require_pin(self) -> str:
        """Return the digest-pinned reference or refuse with a named reason."""

        if not self.pinned or self.image_reference is None or self.image_digest is None:
            raise _refuse(
                ExperimentRefusal.IMAGE_DIGEST_UNRESOLVED, field="image_digest",
                detail="the repository owner has not pinned the experiment image digest",
            )
        return self.image_reference

    def to_record(self) -> dict[str, Any]:
        value = {item.name: getattr(self, item.name) for item in fields(self)}
        value["forbidden_reuse_digests"] = list(self.forbidden_reuse_digests)
        value["schema_version"] = IMAGE_LOCK_SCHEMA
        return value


def parse_experiment_image_lock(
    raw: bytes, *, profile: ExperimentSandboxProfile = EXPERIMENT_PROFILE,
) -> ExperimentImageLock:
    """Fail-closed parse of a `config/campaign-experiment-oci-image-*.json` pin."""

    value = _closed_object(
        raw, malformed=ExperimentRefusal.IMAGE_LOCK_MALFORMED,
        duplicate=ExperimentRefusal.IMAGE_LOCK_DUPLICATE_KEY, label="image_lock",
    )
    observed = frozenset(value)
    for name in sorted(observed - _LOCK_FIELDS):
        raise _refuse(ExperimentRefusal.IMAGE_LOCK_UNKNOWN_FIELD, field=name)
    if observed != _LOCK_FIELDS:
        raise _refuse(
            ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="image_lock",
            detail="missing field",
        )
    if value["schema_version"] != IMAGE_LOCK_SCHEMA:
        raise _refuse(
            ExperimentRefusal.IMAGE_LOCK_SCHEMA_VERSION_UNKNOWN, field="schema_version",
        )
    if value["runtime_role"] != _GENERATED_CODE_ROLE:
        raise _refuse(
            ExperimentRefusal.IMAGE_ROLE_NOT_GENERATED_CODE, field="runtime_role",
        )
    if value["network_default"] != "none":
        raise _refuse(ExperimentRefusal.NETWORK_FORBIDDEN, field="network_default")
    if value["pull_policy"] != "never":
        raise _refuse(ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="pull_policy")
    repository = value["image_repository"]
    if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
        raise _refuse(ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="image_repository")
    platform = value["platform"]
    if not isinstance(platform, str) or not _PLATFORM.fullmatch(platform):
        raise _refuse(ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="platform")
    notes = value["notes"]
    if not isinstance(notes, str) or len(notes.encode("utf-8")) > 4_096:
        raise _refuse(ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="notes")

    declared_modules = value["allowed_import_modules"]
    if (
        not isinstance(declared_modules, list)
        or sorted(ALLOWED_IMPORT_MODULES) != declared_modules
    ):
        raise _refuse(
            ExperimentRefusal.LANGUAGE_SURFACE_DECLARATION_MISMATCH,
            field="allowed_import_modules",
        )
    if value["resource_profile"] != profile.to_record():
        raise _refuse(
            ExperimentRefusal.PROFILE_DECLARATION_MISMATCH, field="resource_profile",
        )

    forbidden = value["forbidden_reuse_digests"]
    if (
        not isinstance(forbidden, list)
        or any(
            not isinstance(item, str) or not _SHA256.fullmatch(item)
            for item in forbidden
        )
        or PHASE4B_PARSER_IMAGE_DIGEST not in forbidden
    ):
        raise _refuse(
            ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="forbidden_reuse_digests",
            detail="the Phase 4B parser image digest must be listed as forbidden reuse",
        )

    status = value["digest_status"]
    reference = value["image_reference"]
    digest = value["image_digest"]
    authorization = value["authorization_status"]
    if status == "unresolved":
        if reference is not None or digest is not None:
            raise _refuse(
                ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="image_digest",
                detail="an unresolved pin carries no reference or digest",
            )
        if authorization != _UNRESOLVED_AUTHORIZATION:
            raise _refuse(
                ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="authorization_status",
            )
    elif status == "pinned":
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise _refuse(ExperimentRefusal.IMAGE_DIGEST_UNRESOLVED, field="image_digest")
        if not isinstance(reference, str) or reference != f"{repository}@{digest}":
            raise _refuse(ExperimentRefusal.IMAGE_DIGEST_MISMATCH, field="image_reference")
        if digest in tuple(forbidden):
            raise _refuse(
                ExperimentRefusal.PARSER_IMAGE_REUSE_FORBIDDEN, field="image_digest",
            )
        if authorization != _PINNED_AUTHORIZATION:
            raise _refuse(
                ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="authorization_status",
            )
    else:
        raise _refuse(ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="digest_status")

    return ExperimentImageLock(
        digest_status=status, image_repository=repository, image_reference=reference,
        image_digest=digest, platform=platform, authorization_status=authorization,
        forbidden_reuse_digests=tuple(forbidden), notes=notes,
    )


def load_experiment_image_lock(
    path: Path, *, profile: ExperimentSandboxProfile = EXPERIMENT_PROFILE,
) -> ExperimentImageLock:
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise _refuse(
            ExperimentRefusal.IMAGE_LOCK_MALFORMED, field="path", detail="unreadable",
        ) from error
    return parse_experiment_image_lock(raw, profile=profile)


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

ACTIVATION_ACKNOWLEDGEMENT = (
    "I authorize bounded AdaIvy campaign generated-code execution in the "
    "digest-pinned experiment sandbox."
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentSandboxActivation:
    """Owner-reviewed authorization for live generated-code execution.

    Constructing this object is not authorization by itself: the sandbox also
    requires a pinned digest, a matching measured runtime, and an image-lock
    hash equal to the one it computes.
    """

    status: str
    authorized_by: str
    acknowledgement: str
    image_lock_hash: str
    policy_hash: str
    probe_report_hash: str

    def __post_init__(self) -> None:
        if self.status != "authorized":
            raise _refuse(ExperimentRefusal.ACTIVATION_NOT_AUTHORIZED, field="status")
        if not isinstance(self.authorized_by, str) or not _IDENTIFIER.fullmatch(
            self.authorized_by
        ):
            raise _refuse(
                ExperimentRefusal.ACTIVATION_NOT_AUTHORIZED, field="authorized_by",
            )
        if self.acknowledgement != ACTIVATION_ACKNOWLEDGEMENT:
            raise _refuse(
                ExperimentRefusal.ACTIVATION_NOT_AUTHORIZED, field="acknowledgement",
            )
        for name in ("image_lock_hash", "policy_hash", "probe_report_hash"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                raise _refuse(ExperimentRefusal.ACTIVATION_NOT_AUTHORIZED, field=name)

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": ACTIVATION_SCHEMA,
            **{item.name: getattr(self, item.name) for item in fields(self)},
        }


# ---------------------------------------------------------------------------
# The injected container-engine port
# ---------------------------------------------------------------------------

MAX_CONTROL_OUTPUT_BYTES = 1_048_576


@dataclass(frozen=True, slots=True, kw_only=True)
class LaunchOutcome:
    """One bounded launch as observed by the launcher. Untrusted observation."""

    stdout: bytes
    stderr: bytes
    stdout_observed: int
    stderr_observed: int
    exit_code: int | None
    timed_out: bool
    output_limit: str | None


class ExperimentLauncher(Protocol):
    """The single boundary that may touch a container engine.

    The campaign package deliberately contains no process, socket, or engine
    code, so this port is the whole mechanism surface.  The sandbox decides the
    exact argv and bounds; a launcher only runs what it is given.  Its
    production implementation is `math_research.experiment_oci_launcher`.
    """

    launcher_id: str
    docker_executable: str
    daemon_host: str

    def control(self, command: tuple[str, ...]) -> bytes:
        """Run one short, bounded, non-launching engine control command."""

    def execute(
        self, command: tuple[str, ...], *, input_bytes: bytes, wall_seconds: float,
        stdout_limit: int, stderr_limit: int,
    ) -> LaunchOutcome:
        """Run one bounded container with captured, truncated streams."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentRuntimeIdentity:
    """Measured local engine and exact-image identity for the experiment image."""

    schema_version: str
    docker_executable: str
    docker_executable_sha256: str
    daemon_host: str
    platform: str
    image_reference: str
    image_descriptor_digest: str
    image_id: str
    image_os: str
    image_architecture: str
    image_layers: tuple[str, ...]
    docker_server_sha256: str
    environment_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_SCHEMA:
            raise _refuse(
                ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="schema_version",
            )
        if not Path(self.docker_executable).is_absolute():
            raise _refuse(
                ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="docker_executable",
            )
        if not self.daemon_host.startswith("unix:///") or ".." in self.daemon_host:
            raise _refuse(
                ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="daemon_host",
            )
        if not _PLATFORM.fullmatch(self.platform):
            raise _refuse(ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="platform")
        repository, _, digest = self.image_reference.partition("@")
        if not _REPOSITORY.fullmatch(repository) or not _SHA256.fullmatch(digest):
            raise _refuse(ExperimentRefusal.IMAGE_DIGEST_MISMATCH, field="image_reference")
        if digest == PHASE4B_PARSER_IMAGE_DIGEST:
            raise _refuse(
                ExperimentRefusal.PARSER_IMAGE_REUSE_FORBIDDEN, field="image_reference",
            )
        for name in (
            "docker_executable_sha256", "image_descriptor_digest", "image_id",
            "docker_server_sha256", "environment_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                raise _refuse(ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field=name)
        if self.image_os != "linux" or not self.image_architecture:
            raise _refuse(ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="image_os")
        if not self.image_layers or any(
            not isinstance(item, str) or not _SHA256.fullmatch(item)
            for item in self.image_layers
        ):
            raise _refuse(
                ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="image_layers",
            )
        if self.environment_sha256 != canonical_hash(self._preimage()):
            raise _refuse(
                ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="environment_sha256",
            )

    def _preimage(self) -> dict[str, Any]:
        return {
            "daemon_host": self.daemon_host,
            "docker_executable": self.docker_executable,
            "docker_executable_sha256": self.docker_executable_sha256,
            "docker_server_sha256": self.docker_server_sha256,
            "image_architecture": self.image_architecture,
            "image_descriptor_digest": self.image_descriptor_digest,
            "image_id": self.image_id,
            "image_layers": list(self.image_layers),
            "image_os": self.image_os,
            "image_reference": self.image_reference,
            "platform": self.platform,
            "schema_version": RUNTIME_SCHEMA,
        }

    def to_record(self) -> dict[str, Any]:
        return {**self._preimage(), "environment_sha256": self.environment_sha256}

    @classmethod
    def measure(
        cls, *, launcher: ExperimentLauncher, lock: ExperimentImageLock,
    ) -> "ExperimentRuntimeIdentity":
        """Measure the local engine and image. Performs no pull and no launch.

        The digest comparison lives here rather than in the launcher, so the
        security-relevant check is in the campaign package and a substituted
        launcher cannot relax it.
        """

        reference = lock.require_pin()
        executable = Path(launcher.docker_executable)
        daemon_host = launcher.daemon_host
        if not executable.is_absolute():
            raise _refuse(
                ExperimentRefusal.RUNTIME_UNAVAILABLE, field="docker_executable",
            )
        if not daemon_host.startswith("unix:///") or ".." in daemon_host:
            raise _refuse(
                ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="daemon_host",
            )
        server = _closed_object(
            launcher.control(
                (str(executable), "version", "--format", "{{json .Server}}"),
            ),
            malformed=ExperimentRefusal.RUNTIME_UNAVAILABLE,
            duplicate=ExperimentRefusal.RUNTIME_UNAVAILABLE, label="server",
        )
        image = _closed_object(
            launcher.control(
                (
                    str(executable), "image", "inspect", reference,
                    "--format", "{{json .}}",
                ),
            ),
            malformed=ExperimentRefusal.RUNTIME_UNAVAILABLE,
            duplicate=ExperimentRefusal.RUNTIME_UNAVAILABLE, label="image",
        )
        descriptor = image.get("Descriptor")
        root = image.get("RootFS")
        repo_digests = image.get("RepoDigests")
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("digest") != lock.image_digest
            or not isinstance(repo_digests, list)
            or reference.split("/", 2)[-1] not in repo_digests
            or not isinstance(root, dict)
            or not isinstance(root.get("Layers"), list)
        ):
            raise _refuse(
                ExperimentRefusal.IMAGE_DIGEST_MISMATCH, field="image_reference",
                detail="the local image is not the exact pinned digest",
            )
        preimage = {
            "daemon_host": daemon_host,
            "docker_executable": str(executable),
            "docker_executable_sha256": _sha256(executable.read_bytes()),
            "docker_server_sha256": canonical_hash(server),
            "image_architecture": image.get("Architecture"),
            "image_descriptor_digest": descriptor["digest"],
            "image_id": image.get("Id"),
            "image_layers": list(root["Layers"]),
            "image_os": image.get("Os"),
            "image_reference": reference,
            "platform": lock.platform,
            "schema_version": RUNTIME_SCHEMA,
        }
        return cls(
            schema_version=RUNTIME_SCHEMA,
            docker_executable=str(executable),
            docker_executable_sha256=preimage["docker_executable_sha256"],
            daemon_host=daemon_host, platform=lock.platform,
            image_reference=reference,
            image_descriptor_digest=descriptor["digest"], image_id=image.get("Id"),
            image_os=image.get("Os"), image_architecture=image.get("Architecture"),
            image_layers=tuple(root["Layers"]),
            docker_server_sha256=canonical_hash(server),
            environment_sha256=canonical_hash(preimage),
        )


# ---------------------------------------------------------------------------
# Policy and command construction
# ---------------------------------------------------------------------------

def sandbox_policy(
    *, image_reference: str | None, platform: str,
    profile: ExperimentSandboxProfile, effective: ResourceLimits,
) -> dict[str, Any]:
    return {
        "capabilities": "drop_all",
        "container_environment": dict(sorted(CONTAINER_ENVIRONMENT.items())),
        "cpu": "kernel_rlimit_cpu_plus_single_cpu_cgroup_quota",
        "credentials": "closed_client_environment_and_no_host_mount",
        "effective_limits": {
            item.name: getattr(effective, item.name) for item in fields(effective)
        },
        "file_count": "kernel_rlimit_nofile_plus_tmpfs_nr_inodes",
        "file_size": "kernel_rlimit_fsize_plus_bounded_tmpfs_size",
        "image": image_reference,
        "language_surface": sorted(ALLOWED_IMPORT_MODULES),
        "memory": "cgroup_memory_and_memory_swap_hard_ceiling",
        "network": "oci_network_namespace_none",
        "no_new_privileges": True,
        "platform": platform,
        "processes": "cgroup_pids_limit",
        "profile": profile.to_record(),
        "pull_policy": "never",
        "root_filesystem": "read_only",
        "runtime_role": _GENERATED_CODE_ROLE,
        "schema_version": POLICY_SCHEMA,
        "streams": "bounded_json_stdin_stdout_stderr",
        "temporary": "fresh_bounded_noexec_nosuid_nodev_tmpfs",
        "tool_adapters": sorted(ADMITTED_TOOL_IDS),
        "user": "65534:65534",
        "work_directory": "fresh_per_container_tmpfs_at_/work",
    }


def build_run_command(
    *, runtime: ExperimentRuntimeIdentity, profile: ExperimentSandboxProfile,
    effective: ResourceLimits, cidfile: Path,
) -> tuple[str, ...]:
    """The complete, fixed container invocation.

    No element is derived from model input except the effective resource values,
    each of which is a tightening of a profile bound.  There is no mount, no
    volume, no host path inside the container, and no shell.  The only host path
    on the command line is the client-side cidfile, which the client -- not the
    container -- writes.
    """

    cpu_seconds = max(1, effective.cpu_milliseconds // 1_000)
    return (
        runtime.docker_executable, "run",
        "--rm=false",
        "--interactive",
        "--pull=never",
        f"--platform={runtime.platform}",
        "--network=none",
        "--read-only",
        f"--memory={effective.memory_bytes}",
        f"--memory-swap={effective.memory_bytes}",
        f"--pids-limit={effective.process_count}",
        f"--ulimit=nofile={profile.max_open_files}:{profile.max_open_files}",
        f"--ulimit=fsize={profile.max_file_bytes}:{profile.max_file_bytes}",
        f"--ulimit=cpu={cpu_seconds}:{cpu_seconds}",
        "--ulimit=core=0:0",
        "--cpus=1.0",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--user=65534:65534",
        (
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,"
            f"size={profile.max_temp_bytes},nr_inodes={profile.max_temp_inodes},"
            "mode=0700,uid=65534,gid=65534"
        ),
        (
            "--tmpfs=/work:rw,noexec,nosuid,nodev,"
            f"size={profile.max_work_bytes},nr_inodes={profile.max_temp_inodes},"
            "mode=0700,uid=65534,gid=65534"
        ),
        "--workdir=/work",
        *(
            f"--env={key}={value}"
            for key, value in sorted(CONTAINER_ENVIRONMENT.items())
        ),
        f"--cidfile={cidfile}",
        "--entrypoint=python3",
        runtime.image_reference,
        "-S", "-c", _BOOTSTRAP,
    )


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

KERNEL_ENFORCEMENT_FIELDS = (
    "no_network_enforcement", "read_only_root_enforcement",
    "noexec_empty_temporary_enforcement", "fresh_work_directory_enforcement",
    "no_inherited_credentials_enforcement", "kernel_memory_enforcement",
    "kernel_cpu_enforcement", "kernel_process_enforcement",
    "kernel_file_count_enforcement", "kernel_file_size_enforcement",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentSandboxEvidence:
    """What this attempt actually demonstrated. Never a warrant."""

    verdict: str
    refusal_reason: str | None
    refusal_field: str | None
    policy_sha256: str
    image_lock_sha256: str
    runtime_environment_sha256: str | None
    program_sha256: str | None
    stdin_envelope_sha256: str | None
    result_sha256: str | None
    image_digest_pinned: bool
    activation_authorized: bool
    request_admission_enforcement: bool
    content_addressed_io_enforcement: bool
    bounded_json_stream_enforcement: bool
    no_network_enforcement: bool
    read_only_root_enforcement: bool
    noexec_empty_temporary_enforcement: bool
    fresh_work_directory_enforcement: bool
    no_inherited_credentials_enforcement: bool
    kernel_memory_enforcement: bool
    kernel_cpu_enforcement: bool
    kernel_process_enforcement: bool
    kernel_file_count_enforcement: bool
    kernel_file_size_enforcement: bool
    container_launched: bool
    exit_code: int | None
    oom_killed: bool
    schema_version: str = EVIDENCE_SCHEMA
    adapter_id: str = ADAPTER_ID
    adapter_version: str = ADAPTER_VERSION
    bootstrap_sha256: str = BOOTSTRAP_SHA256
    epistemic_warrant_created: bool = False
    trust_effect: str = "untrusted_observation"

    def semantic_record(self) -> dict[str, Any]:
        """Timing-free identity. Elapsed observations live in the result record."""

        return {item.name: getattr(self, item.name) for item in fields(self)}

    def content_hash(self) -> str:
        return canonical_hash(self.semantic_record())


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------

class CampaignExperimentSandbox:
    """Production :class:`CampaignExperimentRunner`. Refuses until owner-pinned.

    The call order is deliberate and stated in ADR-0066:

    1. request admission (pure, offline, always evaluated first);
    2. the bounded stdin envelope;
    3. the image digest pin;
    4. the owner activation record;
    5. an injected container-engine launcher;
    6. the measured runtime identity; and only then
    7. one bounded container launch.

    A refusal at any step returns a ``FAILED`` :class:`ExperimentResult` whose
    bytes are the canonical refusal record, so the campaign ledger retains the
    dead end instead of losing it to an exception.
    """

    sandbox_contract = SANDBOX_CONTRACT_VERSION

    def __init__(
        self, *, lock: ExperimentImageLock,
        profile: ExperimentSandboxProfile = EXPERIMENT_PROFILE,
        activation: ExperimentSandboxActivation | None = None,
        runtime: ExperimentRuntimeIdentity | None = None,
        launcher: ExperimentLauncher | None = None,
    ) -> None:
        self.lock = lock
        self.profile = profile
        self.activation = activation
        self.runtime = runtime
        self.launcher = launcher
        self.image_lock_sha256 = canonical_hash(lock.to_record())
        self.last_evidence: ExperimentSandboxEvidence | None = None

    # -- policy ---------------------------------------------------------
    def policy(self, effective: ResourceLimits | None = None) -> dict[str, Any]:
        limits = effective or ResourceLimits(
            cpu_milliseconds=self.profile.max_cpu_milliseconds,
            wall_milliseconds=self.profile.max_wall_milliseconds,
            memory_bytes=self.profile.max_memory_bytes,
            output_bytes=self.profile.max_output_bytes,
            process_count=self.profile.max_process_count,
        )
        return sandbox_policy(
            image_reference=self.lock.image_reference, platform=self.lock.platform,
            profile=self.profile, effective=limits,
        )

    @property
    def policy_sha256(self) -> str:
        return canonical_hash(self.policy())

    # -- protocol -------------------------------------------------------
    def __call__(self, request: ExperimentRequest) -> ExperimentResult:
        try:
            admitted = validate_experiment_request(request, profile=self.profile)
        except ExperimentSandboxRefusal as refusal:
            return self._refused(refusal, admitted=None)
        try:
            envelope = build_stdin_envelope(admitted, profile=self.profile)
            parse_stdin_envelope(envelope, profile=self.profile)
            self.lock.require_pin()
            if self.activation is None:
                raise _refuse(
                    ExperimentRefusal.ACTIVATION_NOT_AUTHORIZED, field="activation",
                    detail="no owner-reviewed activation record was supplied",
                )
            if self.activation.image_lock_hash != self.image_lock_sha256:
                raise _refuse(
                    ExperimentRefusal.ACTIVATION_NOT_AUTHORIZED, field="image_lock_hash",
                )
            if self.launcher is None:
                raise _refuse(
                    ExperimentRefusal.LAUNCHER_UNAVAILABLE, field="launcher",
                    detail="no container-engine launcher was injected",
                )
            if self.runtime is None:
                raise _refuse(
                    ExperimentRefusal.RUNTIME_UNAVAILABLE, field="runtime",
                    detail="no measured runtime identity was supplied",
                )
        except ExperimentSandboxRefusal as refusal:
            return self._refused(refusal, admitted=admitted)
        return self._execute(admitted, envelope)

    # -- refusal --------------------------------------------------------
    def _refused(
        self, refusal: ExperimentSandboxRefusal, *,
        admitted: AdmittedExperiment | None,
    ) -> ExperimentResult:
        body = canonical_bytes({
            "adapter_id": ADAPTER_ID,
            "adapter_version": ADAPTER_VERSION,
            "image_lock_sha256": self.image_lock_sha256,
            "policy_sha256": self.policy_sha256,
            "refusal": refusal.record(),
            "request": None if admitted is None else admitted.request_record(),
            "schema_version": SANDBOX_CONTRACT_VERSION,
        })
        self.last_evidence = ExperimentSandboxEvidence(
            verdict="refused_before_execution",
            refusal_reason=refusal.reason.value, refusal_field=refusal.field,
            policy_sha256=self.policy_sha256, image_lock_sha256=self.image_lock_sha256,
            runtime_environment_sha256=(
                None if self.runtime is None else self.runtime.environment_sha256
            ),
            program_sha256=None if admitted is None else admitted.program_artifact_hash,
            stdin_envelope_sha256=None, result_sha256=None,
            image_digest_pinned=self.lock.pinned,
            activation_authorized=self.activation is not None,
            request_admission_enforcement=True,
            content_addressed_io_enforcement=admitted is not None,
            bounded_json_stream_enforcement=False,
            no_network_enforcement=False, read_only_root_enforcement=False,
            noexec_empty_temporary_enforcement=False,
            fresh_work_directory_enforcement=False,
            no_inherited_credentials_enforcement=False,
            kernel_memory_enforcement=False, kernel_cpu_enforcement=False,
            kernel_process_enforcement=False, kernel_file_count_enforcement=False,
            kernel_file_size_enforcement=False, container_launched=False,
            exit_code=None, oom_killed=False,
        )
        return ExperimentResult(
            adapter_id=ADAPTER_ID, adapter_version=ADAPTER_VERSION,
            adapter_configuration_hash=self.policy_sha256,
            environment_hash=self.image_lock_sha256,
            status=RecordStatus.FAILED, result=body, stdout=b"",
            stderr=(
                f"campaign-experiment-sandbox refused: {refusal.reason.value}\n"
            ).encode("utf-8"),
            # A refusal measured nothing. `ToolRunRecord` refuses an
            # `unavailable` measurement that still carries an observation, and
            # fabricating one here would be a false measurement.
            measurement_source=UsageSource.UNAVAILABLE,
            cpu_milliseconds=None, wall_milliseconds=None, peak_memory_bytes=None,
            output_bytes=None,
        )

    # -- execution ------------------------------------------------------
    def _execute(
        self, admitted: AdmittedExperiment, envelope: bytes,
    ) -> ExperimentResult:
        runtime = self.runtime
        launcher = self.launcher
        assert runtime is not None and launcher is not None
        effective = admitted.effective_limits
        started = time.monotonic()
        try:
            measured = ExperimentRuntimeIdentity.measure(
                launcher=launcher, lock=self.lock,
            )
        except ExperimentSandboxRefusal as refusal:
            return self._refused(refusal, admitted=admitted)
        if measured != runtime:
            return self._refused(
                _refuse(ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="runtime"),
                admitted=admitted,
            )

        process: LaunchOutcome | None = None
        state: dict[str, Any] = {}
        removed = False
        with tempfile.TemporaryDirectory(prefix="adaivy-campaign-experiment-") as scratch:
            cidfile = Path(scratch) / "cid"
            command = build_run_command(
                runtime=runtime, profile=self.profile, effective=effective,
                cidfile=cidfile,
            )
            try:
                process = launcher.execute(
                    command, input_bytes=envelope,
                    wall_seconds=effective.wall_milliseconds / 1_000,
                    stdout_limit=effective.output_bytes,
                    stderr_limit=effective.output_bytes,
                )
            except ExperimentSandboxRefusal as refusal:
                return self._refused(refusal, admitted=admitted)
            except (OSError, ValueError) as error:
                return self._refused(
                    _refuse(
                        ExperimentRefusal.LAUNCH_FAILED,
                        detail=type(error).__name__,
                    ),
                    admitted=admitted,
                )
            container_id = ""
            try:
                if cidfile.is_file():
                    container_id = cidfile.read_text("ascii").strip()
                if _CONTAINER_ID.fullmatch(container_id):
                    state = _closed_object(
                        launcher.control((
                            runtime.docker_executable, "container", "inspect",
                            container_id, "--format", "{{json .State}}",
                        )),
                        malformed=ExperimentRefusal.CONTROL_STATE_UNAVAILABLE,
                        duplicate=ExperimentRefusal.CONTROL_STATE_UNAVAILABLE,
                        label="container_state",
                    )
            except (OSError, UnicodeError, ExperimentSandboxRefusal):
                state = {}
            finally:
                if container_id:
                    try:
                        launcher.control((
                            runtime.docker_executable, "container", "rm",
                            "--force", container_id,
                        ))
                        removed = True
                    except ExperimentSandboxRefusal:
                        removed = False

        assert process is not None
        elapsed = max(0, int((time.monotonic() - started) * 1_000))
        if (
            not state or not removed
            or not isinstance(state.get("OOMKilled"), bool)
            or state.get("ExitCode") != process.exit_code
        ):
            return self._refused(
                _refuse(ExperimentRefusal.CONTROL_STATE_UNAVAILABLE), admitted=admitted,
            )
        oom = state.get("OOMKilled") is True
        failure: ExperimentRefusal | None = None
        if process.timed_out:
            failure = ExperimentRefusal.WALL_LIMIT_EXCEEDED
        elif process.output_limit == "stdout":
            failure = ExperimentRefusal.STDOUT_LIMIT_EXCEEDED
        elif process.output_limit == "stderr":
            failure = ExperimentRefusal.STDERR_LIMIT_EXCEEDED
        elif oom:
            failure = ExperimentRefusal.MEMORY_LIMIT_EXCEEDED
        elif process.exit_code != 0:
            failure = (
                ExperimentRefusal.CPU_LIMIT_EXCEEDED
                if process.exit_code in {137, 152, -9, -24}
                else ExperimentRefusal.WORKER_FAILED
            )

        result_bytes = b""
        result_hash: str | None = None
        cpu_milliseconds: int | None = None
        peak_memory_bytes: int | None = None
        if failure is None:
            try:
                response = _closed_object(
                    process.stdout,
                    malformed=ExperimentRefusal.WORKER_RESPONSE_INVALID,
                    duplicate=ExperimentRefusal.WORKER_RESPONSE_INVALID,
                    label="worker_response",
                )
                if frozenset(response) != RESPONSE_FIELDS:
                    raise _refuse(
                        ExperimentRefusal.WORKER_RESPONSE_INVALID, field="fields",
                    )
                if response["schema_version"] != RESPONSE_SCHEMA:
                    raise _refuse(
                        ExperimentRefusal.WORKER_RESPONSE_INVALID,
                        field="schema_version",
                    )
                if response["status"] != "completed":
                    raise _refuse(
                        ExperimentRefusal.WORKER_RESPONSE_INVALID, field="status",
                    )
                result_bytes = base64.b64decode(response["result_base64"], validate=True)
                result_hash = _sha256(result_bytes)
                if result_hash != response["result_sha256"]:
                    raise _refuse(ExperimentRefusal.RESULT_HASH_MISMATCH, field="result")
                for name in ("cpu_milliseconds", "peak_memory_kib"):
                    observed = response[name]
                    if (
                        isinstance(observed, bool) or not isinstance(observed, int)
                        or observed < 0
                    ):
                        raise _refuse(
                            ExperimentRefusal.WORKER_RESPONSE_INVALID, field=name,
                        )
                cpu_milliseconds = int(response["cpu_milliseconds"])
                # `ru_maxrss` is kilobytes on Linux, and this sandbox admits no
                # other platform. The value is an untrusted in-sandbox
                # observation, not a host measurement.
                peak_memory_bytes = int(response["peak_memory_kib"]) * 1_024
            except ExperimentSandboxRefusal as refusal:
                return self._refused(refusal, admitted=admitted)
            except (TypeError, ValueError):
                return self._refused(
                    _refuse(ExperimentRefusal.WORKER_RESPONSE_INVALID),
                    admitted=admitted,
                )

        policy_hash = canonical_hash(self.policy(effective))
        self.last_evidence = ExperimentSandboxEvidence(
            verdict="completed" if failure is None else "bound_enforced",
            refusal_reason=None if failure is None else failure.value,
            refusal_field=None, policy_sha256=policy_hash,
            image_lock_sha256=self.image_lock_sha256,
            runtime_environment_sha256=runtime.environment_sha256,
            program_sha256=admitted.program_artifact_hash,
            stdin_envelope_sha256=_sha256(envelope), result_sha256=result_hash,
            image_digest_pinned=True, activation_authorized=True,
            request_admission_enforcement=True,
            content_addressed_io_enforcement=True,
            bounded_json_stream_enforcement=True,
            container_launched=True, exit_code=process.exit_code, oom_killed=oom,
            **{name: True for name in KERNEL_ENFORCEMENT_FIELDS},
        )
        return ExperimentResult(
            adapter_id=ADAPTER_ID, adapter_version=ADAPTER_VERSION,
            adapter_configuration_hash=policy_hash,
            environment_hash=runtime.environment_sha256,
            status=RecordStatus.COMPLETED if failure is None else RecordStatus.FAILED,
            result=(
                result_bytes if failure is None
                else canonical_bytes({
                    "bound_enforced": failure.value,
                    "epistemic_warrant_created": False,
                    "schema_version": SANDBOX_CONTRACT_VERSION,
                    "trust_effect": "untrusted_observation",
                })
            ),
            stdout=process.stdout, stderr=process.stderr,
            # `ToolRunRecord` requires either every observation or none, so a
            # killed container reports `unavailable` rather than a partial
            # measurement.
            measurement_source=(
                UsageSource.LOCALLY_MEASURED if failure is None
                else UsageSource.UNAVAILABLE
            ),
            cpu_milliseconds=cpu_milliseconds,
            wall_milliseconds=elapsed if failure is None else None,
            peak_memory_bytes=peak_memory_bytes,
            output_bytes=(
                process.stdout_observed + process.stderr_observed
                if failure is None else None
            ),
        )


def build_default_experiment_sandbox(
    *, image_lock_path: Path,
    activation: ExperimentSandboxActivation | None = None,
    runtime: ExperimentRuntimeIdentity | None = None,
    launcher: ExperimentLauncher | None = None,
) -> CampaignExperimentSandbox:
    """Load the owner-authored pin and return the fail-closed production runner.

    Every argument after the pin defaults to absent, so the default construction
    is a refusing runner. Nothing here enables live execution.
    """

    return CampaignExperimentSandbox(
        lock=load_experiment_image_lock(image_lock_path), activation=activation,
        runtime=runtime, launcher=launcher,
    )


__all__ = [
    "ACTIVATION_ACKNOWLEDGEMENT", "ACTIVATION_SCHEMA", "ADAPTER_ID",
    "ADAPTER_VERSION", "ADMITTED_TOOL_IDS", "ALLOWED_IMPORT_MODULES",
    "AdmittedExperiment", "BOOTSTRAP_SHA256", "CONTAINER_CONTROLS",
    "CONTAINER_ENVIRONMENT", "CampaignExperimentSandbox", "ENVELOPE_SCHEMA",
    "EVIDENCE_SCHEMA", "EXPERIMENT_PROFILE", "ExperimentImageLock",
    "ExperimentRefusal", "ExperimentRuntimeIdentity",
    "ExperimentSandboxActivation", "ExperimentSandboxEvidence",
    "ExperimentSandboxProfile", "ExperimentSandboxRefusal",
    "FORBIDDEN_PROGRAM_ATTRIBUTES", "FORBIDDEN_PROGRAM_NAMES",
    "ExperimentLauncher", "IMAGE_LOCK_SCHEMA", "KERNEL_ENFORCEMENT_FIELDS",
    "LaunchOutcome", "MAX_CONTROL_OUTPUT_BYTES", "NETWORK_IMPORT_MODULES",
    "PHASE4B_PARSER_IMAGE_DIGEST", "POLICY_SCHEMA", "PROFILE_SCHEMA",
    "RESPONSE_FIELDS", "RESPONSE_SCHEMA", "RUNTIME_SCHEMA",
    "SANDBOX_CONTRACT_VERSION",
    "SHELL_TOOL_TOKENS", "SandboxControl", "build_default_experiment_sandbox",
    "build_run_command", "build_stdin_envelope", "load_experiment_image_lock",
    "parse_experiment_image_lock", "parse_stdin_envelope", "sandbox_policy",
    "validate_experiment_request",
]
