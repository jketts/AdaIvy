"""Digest-pinned OCI sandbox that executes ONE untrusted campaign program.

This is the mechanism, not the authorization: constructing an
:class:`OciExperimentSandbox` measures a boundary, it does not activate one.
:mod:`math_research.campaign.experiment_sandbox.activation` holds the release
condition and :mod:`.runner` refuses to run without it.

Threat model, which is the reason this exists separately from the Phase 4B
parser gate: the parser gate runs *our pinned code* on untrusted input, and
this runs *untrusted code*.  The program was written by a model that may have
read a retrieved document, so an upstream prompt injection arrives here as an
executable rather than as text.

Consequences that shape the design:

* The program arrives on **bounded stdin** (ADR-0016), never on a writable
  mount, so no path exists by which it can change between hashing and
  execution.  The in-container bootstrap re-hashes the bytes it decoded and
  refuses on any mismatch.
* The only environment is ``LANG=C.UTF-8`` and ``PYTHONHASHSEED=0``.  Both are
  literals; no host-derived variable, and specifically no credential, is
  passed.
* stdout, stderr and the result artifact are bounded **independently**, and a
  truncated result is recorded as a refusal.  Truncation never reads as a
  complete result.
* Resource measurement is host-observed only.  See
  :data:`MEASUREMENT_POLICY` and the note on it: an in-container number is not
  accepted as a measurement, because a child process in this container can
  ``PTRACE_ATTACH`` its parent (measured, not assumed), so anything the
  in-container reporter says about resources is program-influenceable.
* The program's output is an untrusted candidate.  This module decides nothing
  about whether it is *right*; :mod:`.verifier` does that, in the host process,
  exactly, from the candidate alone.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Mapping

from ...phase4b.oci_parser_sandbox import (
    OciRuntimeIdentity,
    _bounded_process,
    _closed_json,
    _docker_environment,
)
from ..records import canonical_hash
from .image_lock import OciImageLock

CONTRACT_VERSION = "adaivy.campaign-experiment-oci-sandbox.v1"
POLICY_SCHEMA = "adaivy.campaign-experiment-sandbox-policy.v1"
REQUEST_PROTOCOL = "adaivy.campaign-experiment-stdin-request.v1"
RESPONSE_PROTOCOL = "adaivy.campaign-experiment-stdout-response.v1"
PROGRAM_CONTRACT = "adaivy.campaign-experiment-program.v1"

# Host-observed only.  wall time is measured outside the container and output
# bytes are counted on the host; container CPU and peak memory are NOT
# host-observable for a linux/arm64 container on a darwin host, and an
# in-container reading of them is program-influenceable, so they are not
# recorded as measurements at all.  See ADR-0066 notes in the slice report.
MEASUREMENT_POLICY = "host_observed_only"

MAX_WALL_SECONDS = 120
MAX_CPU_SECONDS = 60
MAX_MEMORY_BYTES = 536_870_912
MIN_MEMORY_BYTES = 33_554_432
MAX_OPEN_FILES = 256
MAX_PROCESSES = 16
MAX_TEMP_FILE_BYTES = 8_388_608
MAX_TMPFS_BYTES = 33_554_432
MAX_TEMP_INODES = 256
MAX_RESULT_BYTES = 262_144
MAX_STREAM_BYTES = 65_536
MAX_STDIN_BYTES = 4_194_304
MAX_PROGRAM_BYTES = 262_144
MIN_DETERMINISM_REPLICAS = 2
MAX_DETERMINISM_REPLICAS = 4

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_ARGUMENT = re.compile(r"^[A-Za-z0-9_.:=+,-]{0,128}$")
_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")

_STDOUT_PATH = "/tmp/adaivy-program-stdout"
_STDERR_PATH = "/tmp/adaivy-program-stderr"
_RESULT_PATH = "/tmp/adaivy-program-result"

REFUSAL_CODES = (
    "sandbox_runtime_unavailable",
    "sandbox_runtime_identity_mismatch",
    "sandbox_image_lock_mismatch",
    "sandbox_program_hash_mismatch",
    "sandbox_program_byte_bound",
    "sandbox_stdin_byte_bound",
    "sandbox_argument_rejected",
    "sandbox_launch_failed",
    "sandbox_control_state_unavailable",
    "sandbox_wall_time_exceeded",
    "sandbox_container_stdout_limit_exceeded",
    "sandbox_container_stderr_limit_exceeded",
    "sandbox_memory_limit_exceeded",
    "sandbox_container_nonzero_exit",
    "sandbox_response_invalid",
    "sandbox_response_not_canonical",
    "sandbox_response_bound_exceeded",
    "program_nonzero_exit",
    "program_signalled",
    "program_result_absent",
    "result_truncated",
    "stdout_truncated",
    "stderr_truncated",
    "nondeterministic_result",
    "nondeterministic_stdout",
    "nondeterministic_stderr",
    "nondeterministic_exit",
)


class SandboxError(ValueError):
    """A sandbox request is malformed before any container is launched."""


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


# The in-container bootstrap.  It is pinned, content-hashed, and forks the
# untrusted program into its own session with stdin on /dev/null and stdout and
# stderr redirected into bounded tmpfs files, so an ordinary program cannot
# corrupt the response frame by printing.  The fork is CONTAINMENT OF ACCIDENT
# and not a trust boundary: a hostile child shares this uid and can ptrace this
# parent.  What makes the response trustworthy is enforced on the host -- the
# container must exit 0 and its stdout must be exactly one canonical response
# object -- and what makes the candidate meaningful is the exact verifier,
# which never runs here.
_BOOTSTRAP = r'''import base64, hashlib, io, json, os, sys, traceback

REQUEST = "adaivy.campaign-experiment-stdin-request.v1"
RESPONSE = "adaivy.campaign-experiment-stdout-response.v1"
CONTRACT = "adaivy.campaign-experiment-program.v1"
FIELDS = {
    "arguments", "input_artifacts", "limits", "program_artifact_hash",
    "program_source_base64", "result_path", "schema_version", "stderr_path",
    "stdout_path",
}

try:
    raw = sys.stdin.buffer.read()
    payload = json.loads(raw.decode("utf-8"))
except Exception:
    os._exit(91)
if not isinstance(payload, dict) or set(payload) != FIELDS:
    os._exit(92)
if payload["schema_version"] != REQUEST:
    os._exit(93)
try:
    program = base64.b64decode(payload["program_source_base64"], validate=True)
except Exception:
    os._exit(94)
if "sha256:" + hashlib.sha256(program).hexdigest() != payload["program_artifact_hash"]:
    os._exit(95)
inputs = {}
try:
    for item in payload["input_artifacts"]:
        if set(item) != {"bytes_base64", "hash"}:
            os._exit(96)
        blob = base64.b64decode(item["bytes_base64"], validate=True)
        if "sha256:" + hashlib.sha256(blob).hexdigest() != item["hash"]:
            os._exit(96)
        inputs[item["hash"]] = blob
except SystemExit:
    raise
except Exception:
    os._exit(96)
limits = payload["limits"]
out_path = payload["stdout_path"]
err_path = payload["stderr_path"]
res_path = payload["result_path"]
try:
    for path in (out_path, err_path):
        with open(path, "wb"):
            pass
except OSError:
    os._exit(97)

pid = os.fork()
if pid == 0:
    try:
        os.setsid()
        null = os.open(os.devnull, os.O_RDONLY)
        handle_out = os.open(out_path, os.O_WRONLY | os.O_TRUNC)
        handle_err = os.open(err_path, os.O_WRONLY | os.O_TRUNC)
        os.dup2(null, 0)
        os.dup2(handle_out, 1)
        os.dup2(handle_err, 2)
        os.closerange(3, 256)
        sys.stdin = io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8")
        sys.stdout = io.TextIOWrapper(io.FileIO(1, "w", closefd=False), encoding="utf-8")
        sys.stderr = io.TextIOWrapper(io.FileIO(2, "w", closefd=False), encoding="utf-8")
    except BaseException:
        os._exit(98)
    namespace = {
        "__name__": "__main__",
        "__builtins__": __builtins__,
        "ADAIVY_PROGRAM_CONTRACT": CONTRACT,
        "ADAIVY_RESULT_PATH": res_path,
        "ADAIVY_INPUT_ARTIFACTS": inputs,
        "ADAIVY_INPUT_ARTIFACT_HASHES": tuple(sorted(inputs)),
        "ADAIVY_ARGUMENTS": tuple(payload["arguments"]),
    }
    status = 0
    try:
        exec(compile(program, "<adaivy-campaign-experiment-program>", "exec"), namespace, namespace)
    except SystemExit as error:
        status = error.code if isinstance(error.code, int) else 1
    except BaseException:
        try:
            traceback.print_exc()
        except BaseException:
            pass
        status = 1
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except BaseException:
        status = status or 1
    os._exit(status & 0xFF)

_pid, wait_status, _rusage = os.wait4(pid, 0)
try:
    os.killpg(pid, 9)
except OSError:
    pass


def kernel_controls():
    found = {}
    for path, keys in (
        ("/sys/fs/cgroup/memory.events", ("oom_kill",)),
        ("/sys/fs/cgroup/pids.events", ("max",)),
        ("/sys/fs/cgroup/cpu.stat", ("usage_usec",)),
    ):
        try:
            with open(path) as handle:
                for line in handle:
                    name, _, value = line.partition(" ")
                    if name in keys:
                        found[path.rsplit("/", 1)[1] + "." + name] = int(value)
        except (OSError, ValueError):
            pass
    try:
        with open("/sys/fs/cgroup/memory.peak") as handle:
            found["memory.peak"] = int(handle.read().strip())
    except (OSError, ValueError):
        pass
    return found


def bounded(path, limit):
    try:
        size = os.stat(path).st_size
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        return None, 0, False
    return data[:limit], max(size, len(data)), (len(data) > limit or size > limit)


result, result_observed, result_truncated = bounded(res_path, limits["max_result_bytes"])
stdout, stdout_observed, stdout_truncated = bounded(out_path, limits["max_stdout_bytes"])
stderr, stderr_observed, stderr_truncated = bounded(err_path, limits["max_stderr_bytes"])
response = {
    "child_exit_code": (wait_status >> 8) if (wait_status & 0xFF) == 0 else None,
    "child_signal": (wait_status & 0x7F) or None,
    "child_wait_status": wait_status,
    "input_artifact_hashes": sorted(inputs),
    "kernel_controls": kernel_controls(),
    "program_artifact_hash": payload["program_artifact_hash"],
    "result_base64": None if result is None else base64.b64encode(result).decode("ascii"),
    "result_bytes_observed": result_observed,
    "result_present": result is not None,
    "result_truncated": result_truncated,
    "schema_version": RESPONSE,
    "stderr_base64": base64.b64encode(stderr or b"").decode("ascii"),
    "stderr_bytes_observed": stderr_observed,
    "stderr_truncated": stderr_truncated,
    "stdout_base64": base64.b64encode(stdout or b"").decode("ascii"),
    "stdout_bytes_observed": stdout_observed,
    "stdout_truncated": stdout_truncated,
}
sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")))
sys.stdout.flush()
os._exit(0)
'''

BOOTSTRAP_SHA256 = _sha256(_BOOTSTRAP.encode("utf-8"))
_RESPONSE_FIELDS = frozenset({
    "child_exit_code", "child_signal", "child_wait_status", "input_artifact_hashes",
    "kernel_controls", "program_artifact_hash", "result_base64",
    "result_bytes_observed", "result_present", "result_truncated", "schema_version",
    "stderr_base64", "stderr_bytes_observed", "stderr_truncated", "stdout_base64",
    "stdout_bytes_observed", "stdout_truncated",
})


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignSandboxLimits:
    """Every bound is a ceiling-checked input.  Nothing here is raised to fit."""

    max_wall_seconds: int = 30
    max_cpu_seconds: int = 10
    max_memory_bytes: int = 268_435_456
    max_open_files: int = 64
    max_processes: int = 8
    max_temp_file_bytes: int = MAX_TEMP_FILE_BYTES
    max_tmpfs_bytes: int = 16_777_216
    max_temp_inodes: int = 128
    max_result_bytes: int = MAX_RESULT_BYTES
    max_stdout_bytes: int = MAX_STREAM_BYTES
    max_stderr_bytes: int = MAX_STREAM_BYTES
    max_stdin_bytes: int = MAX_STDIN_BYTES
    max_program_bytes: int = MAX_PROGRAM_BYTES
    determinism_replicas: int = MIN_DETERMINISM_REPLICAS

    def __post_init__(self) -> None:
        ceilings = {
            "max_wall_seconds": (1, MAX_WALL_SECONDS),
            "max_cpu_seconds": (1, MAX_CPU_SECONDS),
            "max_memory_bytes": (MIN_MEMORY_BYTES, MAX_MEMORY_BYTES),
            "max_open_files": (16, MAX_OPEN_FILES),
            # Two processes minimum: the pinned bootstrap plus the program.
            "max_processes": (2, MAX_PROCESSES),
            "max_temp_file_bytes": (65_536, MAX_TEMP_FILE_BYTES),
            "max_tmpfs_bytes": (1_048_576, MAX_TMPFS_BYTES),
            "max_temp_inodes": (16, MAX_TEMP_INODES),
            "max_result_bytes": (1, MAX_RESULT_BYTES),
            "max_stdout_bytes": (1, MAX_STREAM_BYTES),
            "max_stderr_bytes": (1, MAX_STREAM_BYTES),
            "max_stdin_bytes": (1_024, MAX_STDIN_BYTES),
            "max_program_bytes": (1, MAX_PROGRAM_BYTES),
            "determinism_replicas": (MIN_DETERMINISM_REPLICAS, MAX_DETERMINISM_REPLICAS),
        }
        for name, (floor, ceiling) in ceilings.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise SandboxError(f"{name} must be an integer")
            if not floor <= value <= ceiling:
                raise SandboxError(f"{name} is outside the campaign sandbox ceiling")
        if self.max_cpu_seconds > self.max_wall_seconds:
            raise SandboxError("the CPU ceiling may not exceed the wall ceiling")
        streams = self.max_result_bytes + self.max_stdout_bytes + self.max_stderr_bytes
        if streams > self.max_tmpfs_bytes:
            raise SandboxError("the bounded streams do not fit inside the tmpfs bound")
        if streams > self.max_temp_file_bytes * 3:
            raise SandboxError("a bounded stream exceeds the per-file size ceiling")

    @property
    def max_container_stdout_bytes(self) -> int:
        """The response frame is base64 plus a small closed JSON header."""

        payload = self.max_result_bytes + self.max_stdout_bytes + self.max_stderr_bytes
        return 4_096 + ((payload + 2) // 3) * 4

    def to_record(self) -> dict[str, int]:
        return {
            name: getattr(self, name)
            for name in sorted(self.__dataclass_fields__)
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SandboxProgramRequest:
    """One untrusted program, its hash, and its read-only input artifacts."""

    program_source: bytes
    program_artifact_hash: str
    input_artifacts: tuple[tuple[str, bytes], ...] = ()
    arguments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.program_source, bytes) or not self.program_source:
            raise SandboxError("program source must be non-empty bytes")
        if _SHA256.fullmatch(self.program_artifact_hash) is None:
            raise SandboxError("program_artifact_hash must be a canonical sha256")
        seen: set[str] = set()
        for content_hash, content in self.input_artifacts:
            if _SHA256.fullmatch(content_hash) is None:
                raise SandboxError("input artifact hash must be a canonical sha256")
            if not isinstance(content, bytes):
                raise SandboxError("input artifact must be bytes")
            if _sha256(content) != content_hash:
                raise SandboxError("input artifact hash does not match its bytes")
            if content_hash in seen:
                raise SandboxError("input artifact hash is repeated")
            seen.add(content_hash)
        for argument in self.arguments:
            if not isinstance(argument, str) or _SAFE_ARGUMENT.fullmatch(argument) is None:
                raise SandboxError("argument is outside the closed vocabulary")
            if "/" in argument or "\\" in argument or ".." in argument or "~" in argument:
                raise SandboxError("argument carries a path")

    @property
    def input_artifact_hashes(self) -> tuple[str, ...]:
        return tuple(sorted(item[0] for item in self.input_artifacts))


@dataclass(frozen=True, slots=True, kw_only=True)
class SandboxOutcome:
    """One replica of one execution.  Timings are operational, never semantic."""

    status: str
    refusal_code: str | None
    result: bytes | None
    result_bytes_observed: int
    result_truncated: bool
    stdout: bytes
    stdout_bytes_observed: int
    stdout_truncated: bool
    stderr: bytes
    stderr_bytes_observed: int
    stderr_truncated: bool
    container_exit_code: int | None
    child_exit_code: int | None
    child_signal: int | None
    oom_killed: bool
    wall_timed_out: bool
    container_stdout_bytes_observed: int
    container_stderr: bytes
    kernel_controls: Mapping[str, int] = field(default_factory=dict)
    wall_milliseconds: int = 0

    def semantic_record(self) -> dict[str, Any]:
        """Everything a replay must reproduce byte for byte."""

        return {
            "child_exit_code": self.child_exit_code,
            "child_signal": self.child_signal,
            "container_exit_code": self.container_exit_code,
            "oom_killed": self.oom_killed,
            "refusal_code": self.refusal_code,
            "result_bytes_observed": self.result_bytes_observed,
            "result_present": self.result is not None,
            "result_sha256": None if self.result is None else _sha256(self.result),
            "result_truncated": self.result_truncated,
            "status": self.status,
            "stderr_bytes_observed": self.stderr_bytes_observed,
            "stderr_sha256": _sha256(self.stderr),
            "stderr_truncated": self.stderr_truncated,
            "stdout_bytes_observed": self.stdout_bytes_observed,
            "stdout_sha256": _sha256(self.stdout),
            "stdout_truncated": self.stdout_truncated,
            "wall_timed_out": self.wall_timed_out,
        }

    def operational_record(self) -> dict[str, Any]:
        """Host-observed timings and kernel counters.  Never content-hashed."""

        return {
            "container_stdout_bytes_observed": self.container_stdout_bytes_observed,
            "kernel_controls": {
                key: self.kernel_controls[key] for key in sorted(self.kernel_controls)
            },
            "measurement_policy": MEASUREMENT_POLICY,
            "wall_milliseconds": self.wall_milliseconds,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SandboxExecution:
    """A full execution: every replica, plus the determinism gate's verdict."""

    status: str
    refusal_code: str | None
    replicas: tuple[SandboxOutcome, ...]
    deterministic: bool
    outcome: SandboxOutcome

    def semantic_record(self) -> dict[str, Any]:
        return {
            "deterministic": self.deterministic,
            "refusal_code": self.refusal_code,
            "replica_count": len(self.replicas),
            "replicas": [item.semantic_record() for item in self.replicas],
            "status": self.status,
        }

    def operational_record(self) -> dict[str, Any]:
        return {
            "replicas": [item.operational_record() for item in self.replicas],
            "wall_milliseconds": sum(item.wall_milliseconds for item in self.replicas),
        }


def _policy(
    runtime: OciRuntimeIdentity, lock: OciImageLock, limits: CampaignSandboxLimits,
) -> dict[str, Any]:
    return {
        "capabilities": "drop_all",
        "cpu": "kernel_rlimit_cpu_plus_cgroup_single_cpu",
        "determinism": "byte_identical_result_across_fresh_containers",
        "environment": ["LANG=C.UTF-8", "PYTHONHASHSEED=0"],
        "image": runtime.image_reference,
        "image_lock": lock.lock_path,
        "image_lock_sha256": lock.lock_sha256,
        "limits": limits.to_record(),
        "measurement": MEASUREMENT_POLICY,
        "memory": "kernel_cgroup_memory_and_swap_hard_ceiling",
        "network": "oci_network_namespace_none",
        "no_new_privileges": True,
        "open_files": "kernel_rlimit_nofile",
        "platform": runtime.platform,
        "processes": "kernel_cgroup_pids_limit",
        "program_transport": "bounded_stdin_no_writable_mount",
        "protocol_request": REQUEST_PROTOCOL,
        "protocol_response": RESPONSE_PROTOCOL,
        "pull_policy": "never",
        "root_filesystem": "read_only",
        "runtime_role": lock.runtime_role,
        "schema_version": POLICY_SCHEMA,
        "secrets": "closed_docker_client_environment_and_no_host_mounts",
        "temporary": "bounded_noexec_nosuid_nodev_tmpfs",
        "user": "65534:65534",
        "verifier_location": "host_process_outside_container",
    }


class OciExperimentSandbox:
    """Execute one untrusted program in the exact, preinstalled OCI image.

    This class is a mechanism.  It grants nothing and decides nothing about the
    mathematics; see :mod:`.runner` for the authorization gate and
    :mod:`.verifier` for the only component that gives a candidate meaning.
    """

    contract_version = CONTRACT_VERSION

    def __init__(
        self, *, expected_runtime: OciRuntimeIdentity, image_lock: OciImageLock,
        limits: CampaignSandboxLimits | None = None,
    ) -> None:
        if expected_runtime.image_reference != image_lock.image_reference:
            raise SandboxError("runtime image differs from the digest-pinned lock")
        if expected_runtime.platform != image_lock.platform:
            raise SandboxError("runtime platform differs from the digest-pinned lock")
        if image_lock.pull_policy != "never" or image_lock.network_default != "none":
            raise SandboxError("image lock relaxed the pull or network policy")
        self.expected_runtime = expected_runtime
        self.image_lock = image_lock
        self.limits = limits or CampaignSandboxLimits()

    @property
    def policy_sha256(self) -> str:
        return canonical_hash(_policy(self.expected_runtime, self.image_lock, self.limits))

    @property
    def control_policy_sha256(self) -> str:
        """Identity of invariant controls, excluding request-tightenable limits."""

        value = _policy(self.expected_runtime, self.image_lock, self.limits)
        value.pop("limits")
        return canonical_hash(value)

    @property
    def bootstrap_sha256(self) -> str:
        return BOOTSTRAP_SHA256

    @property
    def environment_sha256(self) -> str:
        return self.expected_runtime.environment_sha256

    def policy_record(self) -> dict[str, Any]:
        return _policy(self.expected_runtime, self.image_lock, self.limits)

    def configuration_record(self) -> dict[str, Any]:
        return {
            "bootstrap_sha256": self.bootstrap_sha256,
            "contract_version": CONTRACT_VERSION,
            "control_policy_sha256": self.control_policy_sha256,
            "environment_sha256": self.environment_sha256,
            "image_lock": self.image_lock.to_record(),
            "limits": self.limits.to_record(),
            "measurement_policy": MEASUREMENT_POLICY,
            "policy_sha256": self.policy_sha256,
            "program_contract": PROGRAM_CONTRACT,
            "protocol_request": REQUEST_PROTOCOL,
            "protocol_response": RESPONSE_PROTOCOL,
        }

    def command(self, cidfile: Path) -> tuple[str, ...]:
        """The Phase 4B control set verbatim, plus the ADR-0066 additions."""

        runtime = self.expected_runtime
        limits = self.limits
        return (
            runtime.docker_executable, "run",
            "--interactive",
            "--pull=never",
            f"--platform={runtime.platform}",
            "--network=none",
            "--read-only",
            f"--memory={limits.max_memory_bytes}",
            f"--memory-swap={limits.max_memory_bytes}",
            f"--pids-limit={limits.max_processes}",
            f"--ulimit=nofile={limits.max_open_files}:{limits.max_open_files}",
            f"--ulimit=fsize={limits.max_temp_file_bytes}:{limits.max_temp_file_bytes}",
            f"--ulimit=cpu={limits.max_cpu_seconds}:{limits.max_cpu_seconds}",
            "--cpus=1.0",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true",
            "--user=65534:65534",
            (
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,"
                f"size={limits.max_tmpfs_bytes},nr_inodes={limits.max_temp_inodes},"
                "mode=0700,uid=65534,gid=65534"
            ),
            "--workdir=/tmp",
            "--env=LANG=C.UTF-8",
            "--env=PYTHONHASHSEED=0",
            f"--cidfile={cidfile}",
            "--entrypoint=python3",
            runtime.image_reference,
            "-I", "-S", "-c", _BOOTSTRAP,
        )

    def stdin_payload(self, request: SandboxProgramRequest) -> bytes:
        """The exact bytes written to stdin.  Nothing else reaches the program."""

        if _sha256(request.program_source) != request.program_artifact_hash:
            raise SandboxError("sandbox_program_hash_mismatch")
        if len(request.program_source) > self.limits.max_program_bytes:
            raise SandboxError("sandbox_program_byte_bound")
        payload = {
            "arguments": list(request.arguments),
            "input_artifacts": [
                {
                    "bytes_base64": base64.b64encode(content).decode("ascii"),
                    "hash": content_hash,
                }
                for content_hash, content in sorted(request.input_artifacts)
            ],
            "limits": {
                "max_result_bytes": self.limits.max_result_bytes,
                "max_stderr_bytes": self.limits.max_stderr_bytes,
                "max_stdout_bytes": self.limits.max_stdout_bytes,
            },
            "program_artifact_hash": request.program_artifact_hash,
            "program_source_base64": base64.b64encode(request.program_source).decode("ascii"),
            "result_path": _RESULT_PATH,
            "schema_version": REQUEST_PROTOCOL,
            "stderr_path": _STDERR_PATH,
            "stdout_path": _STDOUT_PATH,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    # -- execution -----------------------------------------------------------

    def _refused(
        self, code: str, *, wall_milliseconds: int = 0,
        container_exit_code: int | None = None, container_stderr: bytes = b"",
        container_stdout_bytes_observed: int = 0, oom_killed: bool = False,
        wall_timed_out: bool = False,
    ) -> SandboxOutcome:
        return SandboxOutcome(
            status="refused", refusal_code=code, result=None,
            result_bytes_observed=0, result_truncated=False, stdout=b"",
            stdout_bytes_observed=0, stdout_truncated=False, stderr=b"",
            stderr_bytes_observed=0, stderr_truncated=False,
            container_exit_code=container_exit_code, child_exit_code=None,
            child_signal=None, oom_killed=oom_killed, wall_timed_out=wall_timed_out,
            container_stdout_bytes_observed=container_stdout_bytes_observed,
            container_stderr=container_stderr[:4_096], kernel_controls={},
            wall_milliseconds=wall_milliseconds,
        )

    def _container_state(self, container_id: str) -> dict[str, Any]:
        runtime = self.expected_runtime
        completed = subprocess.run(
            (
                runtime.docker_executable, "container", "inspect", container_id,
                "--format", "{{json .State}}",
            ),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=_docker_environment(Path(runtime.docker_executable), runtime.daemon_host),
            check=False, timeout=15,
        )
        if completed.returncode != 0:
            raise ValueError("OCI container state unavailable")
        return _closed_json(completed.stdout, "campaign sandbox container state")

    def _remove_container(self, container_id: str) -> bool:
        runtime = self.expected_runtime
        try:
            completed = subprocess.run(
                (runtime.docker_executable, "container", "rm", "--force", container_id),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=_docker_environment(
                    Path(runtime.docker_executable), runtime.daemon_host,
                ),
                check=False, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0

    def run_once(self, request: SandboxProgramRequest) -> SandboxOutcome:
        """Launch one fresh container.  Every failure path is a recorded refusal."""

        started = time.monotonic()
        runtime = self.expected_runtime
        try:
            payload = self.stdin_payload(request)
        except SandboxError as error:
            return self._refused(str(error.args[0]))
        if len(payload) > self.limits.max_stdin_bytes:
            return self._refused("sandbox_stdin_byte_bound")
        try:
            measured = OciRuntimeIdentity.measure(
                docker_executable=Path(runtime.docker_executable),
                daemon_host=runtime.daemon_host,
                image_reference=runtime.image_reference,
                platform=runtime.platform,
            )
        except (OSError, ValueError):
            return self._refused(
                "sandbox_runtime_unavailable",
                wall_milliseconds=int((time.monotonic() - started) * 1_000),
            )
        if measured != runtime:
            return self._refused(
                "sandbox_runtime_identity_mismatch",
                wall_milliseconds=int((time.monotonic() - started) * 1_000),
            )

        state: dict[str, Any] = {}
        cleanup_ok = False
        with tempfile.TemporaryDirectory(prefix="adaivy-campaign-oci-") as temporary:
            cidfile = Path(temporary) / "cid"
            try:
                process = _bounded_process(
                    self.command(cidfile), input_bytes=payload,
                    environment=_docker_environment(
                        Path(runtime.docker_executable), runtime.daemon_host,
                    ),
                    wall_seconds=self.limits.max_wall_seconds,
                    stdout_limit=self.limits.max_container_stdout_bytes,
                    stderr_limit=MAX_STREAM_BYTES,
                )
            except (OSError, subprocess.SubprocessError, ValueError):
                return self._refused(
                    "sandbox_launch_failed",
                    wall_milliseconds=int((time.monotonic() - started) * 1_000),
                )
            container_id = ""
            try:
                if cidfile.is_file():
                    container_id = cidfile.read_text("ascii").strip()
                if _CONTAINER_ID.fullmatch(container_id):
                    state = self._container_state(container_id)
            except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
                state = {}
            finally:
                if container_id:
                    cleanup_ok = self._remove_container(container_id)

        wall = max(0, int((time.monotonic() - started) * 1_000))
        if (
            not state
            or not cleanup_ok
            or not isinstance(state.get("OOMKilled"), bool)
            or state.get("ExitCode") != process.exit_code
        ):
            return self._refused(
                "sandbox_control_state_unavailable", wall_milliseconds=wall,
                container_exit_code=process.exit_code,
                container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed,
            )
        oom = state.get("OOMKilled") is True
        if process.timed_out:
            return self._refused(
                "sandbox_wall_time_exceeded", wall_milliseconds=wall,
                container_exit_code=process.exit_code, container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed,
                oom_killed=oom, wall_timed_out=True,
            )
        if process.output_limit:
            return self._refused(
                f"sandbox_container_{process.output_limit}_limit_exceeded",
                wall_milliseconds=wall, container_exit_code=process.exit_code,
                container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed, oom_killed=oom,
            )
        if oom:
            # The container's cgroup hit its hard ceiling.  Whether the pinned
            # bootstrap or the program was killed, no complete result exists.
            return self._refused(
                "sandbox_memory_limit_exceeded", wall_milliseconds=wall,
                container_exit_code=process.exit_code, container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed, oom_killed=True,
            )
        if process.exit_code != 0:
            return self._refused(
                "sandbox_container_nonzero_exit", wall_milliseconds=wall,
                container_exit_code=process.exit_code, container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed,
            )
        return self._decode(request, process, wall)

    def _decode(self, request: SandboxProgramRequest, process: Any, wall: int) -> SandboxOutcome:
        raw = process.stdout
        if len(raw) > self.limits.max_container_stdout_bytes:
            return self._refused(
                "sandbox_response_bound_exceeded", wall_milliseconds=wall,
                container_exit_code=process.exit_code, container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed,
            )
        try:
            value = _closed_json(raw, "campaign sandbox response")
        except ValueError:
            return self._refused(
                "sandbox_response_invalid", wall_milliseconds=wall,
                container_exit_code=process.exit_code, container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed,
            )
        # Exactly one canonical object and nothing else.  A program that wrote
        # to the container's real stdout -- directly or through the parent's
        # /proc file descriptor -- breaks this and is refused.
        if json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") != raw:
            return self._refused(
                "sandbox_response_not_canonical", wall_milliseconds=wall,
                container_exit_code=process.exit_code, container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed,
            )
        if (
            frozenset(value) != _RESPONSE_FIELDS
            or value["schema_version"] != RESPONSE_PROTOCOL
            or value["program_artifact_hash"] != request.program_artifact_hash
            or value["input_artifact_hashes"] != list(request.input_artifact_hashes)
        ):
            return self._refused(
                "sandbox_response_invalid", wall_milliseconds=wall,
                container_exit_code=process.exit_code, container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed,
            )
        try:
            result, result_observed, result_truncated = self._stream(
                value, "result", self.limits.max_result_bytes, optional=True,
            )
            stdout, stdout_observed, stdout_truncated = self._stream(
                value, "stdout", self.limits.max_stdout_bytes,
            )
            stderr, stderr_observed, stderr_truncated = self._stream(
                value, "stderr", self.limits.max_stderr_bytes,
            )
            child_exit = value["child_exit_code"]
            child_signal = value["child_signal"]
            controls = value["kernel_controls"]
            if not isinstance(controls, dict) or any(
                not isinstance(item, int) or isinstance(item, bool)
                for item in controls.values()
            ):
                raise SandboxError("kernel controls are malformed")
            for name, item in (("child_exit_code", child_exit), ("child_signal", child_signal)):
                if item is not None and (
                    not isinstance(item, int) or isinstance(item, bool) or not 0 <= item <= 255
                ):
                    raise SandboxError(f"{name} is malformed")
            if not isinstance(value["child_wait_status"], int):
                raise SandboxError("child_wait_status is malformed")
            if value["result_present"] is not (result is not None):
                raise SandboxError("result presence disagrees with the payload")
        except SandboxError:
            return self._refused(
                "sandbox_response_invalid", wall_milliseconds=wall,
                container_exit_code=process.exit_code, container_stderr=process.stderr,
                container_stdout_bytes_observed=process.stdout_observed,
            )

        refusal: str | None = None
        if result_truncated:
            refusal = "result_truncated"
        elif stdout_truncated:
            refusal = "stdout_truncated"
        elif stderr_truncated:
            refusal = "stderr_truncated"
        elif child_signal is not None:
            refusal = "program_signalled"
        elif child_exit != 0:
            refusal = "program_nonzero_exit"
        elif result is None:
            refusal = "program_result_absent"
        status = "completed" if refusal is None else "program_failed"
        return SandboxOutcome(
            status=status, refusal_code=refusal,
            result=None if refusal is not None else result,
            result_bytes_observed=result_observed, result_truncated=result_truncated,
            stdout=stdout, stdout_bytes_observed=stdout_observed,
            stdout_truncated=stdout_truncated, stderr=stderr,
            stderr_bytes_observed=stderr_observed, stderr_truncated=stderr_truncated,
            container_exit_code=process.exit_code, child_exit_code=child_exit,
            child_signal=child_signal, oom_killed=False, wall_timed_out=False,
            container_stdout_bytes_observed=process.stdout_observed,
            container_stderr=process.stderr[:4_096],
            kernel_controls={
                str(key): int(controls[key]) for key in sorted(controls)
            },
            wall_milliseconds=wall,
        )

    def _stream(
        self, value: Mapping[str, Any], name: str, limit: int, *, optional: bool = False,
    ) -> tuple[bytes | None, int, bool]:
        encoded = value[f"{name}_base64"]
        observed = value[f"{name}_bytes_observed"]
        truncated = value[f"{name}_truncated"]
        if not isinstance(truncated, bool):
            raise SandboxError(f"{name}_truncated is malformed")
        if not isinstance(observed, int) or isinstance(observed, bool) or observed < 0:
            raise SandboxError(f"{name}_bytes_observed is malformed")
        if encoded is None:
            if not optional:
                raise SandboxError(f"{name} payload is absent")
            return None, observed, truncated
        if not isinstance(encoded, str):
            raise SandboxError(f"{name} payload is malformed")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise SandboxError(f"{name} payload is not base64") from error
        if len(data) > limit:
            raise SandboxError(f"{name} payload exceeds its bound")
        if observed < len(data) or (observed > limit) != truncated:
            raise SandboxError(f"{name} truncation flag disagrees with its bytes")
        return data, observed, truncated

    def run(self, request: SandboxProgramRequest) -> SandboxExecution:
        """Run the determinism gate: repeated fresh containers must agree."""

        replicas: list[SandboxOutcome] = []
        for _index in range(self.limits.determinism_replicas):
            outcome = self.run_once(request)
            replicas.append(outcome)
            if outcome.status == "refused":
                return SandboxExecution(
                    status="refused", refusal_code=outcome.refusal_code,
                    replicas=tuple(replicas), deterministic=False, outcome=outcome,
                )
        first = replicas[0]
        divergence: str | None = None
        for other in replicas[1:]:
            if first.result != other.result:
                divergence = "nondeterministic_result"
            elif first.stdout != other.stdout:
                divergence = "nondeterministic_stdout"
            elif first.stderr != other.stderr:
                divergence = "nondeterministic_stderr"
            elif (
                first.child_exit_code != other.child_exit_code
                or first.child_signal != other.child_signal
                or first.refusal_code != other.refusal_code
            ):
                divergence = "nondeterministic_exit"
            if divergence is not None:
                break
        if divergence is not None:
            return SandboxExecution(
                status="refused", refusal_code=divergence, replicas=tuple(replicas),
                deterministic=False, outcome=first,
            )
        return SandboxExecution(
            status=first.status, refusal_code=first.refusal_code,
            replicas=tuple(replicas), deterministic=True, outcome=first,
        )


__all__ = [
    "BOOTSTRAP_SHA256", "CONTRACT_VERSION", "CampaignSandboxLimits",
    "MEASUREMENT_POLICY", "MAX_PROGRAM_BYTES", "MAX_RESULT_BYTES",
    "MAX_TEMP_INODES",
    "MAX_STDIN_BYTES", "MAX_STREAM_BYTES", "OciExperimentSandbox",
    "POLICY_SCHEMA", "PROGRAM_CONTRACT", "REFUSAL_CODES", "REQUEST_PROTOCOL",
    "RESPONSE_PROTOCOL", "SandboxError", "SandboxExecution", "SandboxOutcome",
    "SandboxProgramRequest",
]
