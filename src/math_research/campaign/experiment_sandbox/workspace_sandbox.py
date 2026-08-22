"""The ADR-0082 v2 workspace sandbox: exact packages, persistence, long runs.

This is the v2 *workspace* capability that lives ALONGSIDE the untouched v1
instrument in :mod:`.sandbox`.  What v2 widens, and only this:

* **Exact package set.**  The v2 image lock declares gmpy2/networkx/sympy with
  pinned versions and wheel hashes; the bootstrap drops ``-S`` so installed
  site-packages are importable.  The v2 bootstrap text therefore differs from
  v1 and carries its own recorded hash.  No numpy, no scipy, no floats on any
  trust path -- the host-side verifiers are unchanged and still refuse floats.
* **A persistent campaign workspace.**  One campaign-scoped writable directory
  is bind-mounted at ``/workspace`` (still ``--network=none``, still
  credential-free).  At every run boundary the workspace file inventory --
  relative paths, sizes, SHA-256 -- is hashed into a workspace manifest for the
  ledger.  The workspace is provenance, never trust: nothing in it is believed,
  everything a program claims is still re-derived by the host-side verifier.
* **Operator-budgeted long computation.**  Structural ceilings rise to 1 h CPU
  / 75 min wall / 8 GiB memory / 1 GiB tmpfs and workspace; per-run requests
  stay configurable strictly below them and are never rounded up.
* **Configurable determinism replicas, 1--4.**  The replica count is recorded.
  One replica means the determinism gate DID NOT RUN: the execution carries
  ``determinism_unverified=True``, which verifiers and reports must surface.
* **Failure as data.**  A non-zero exit, a signal, or an absent result artifact
  produces a structured, content-hashed diagnostics record (exit status,
  bounded stderr, workspace manifest delta) that the runner layer can choose
  to continue from.  v1 behavior is unchanged.

Container execution is an injected port (:class:`WorkspaceContainerExecutorPort`)
so the manifest, determinism, and promotion logic is testable offline; the only
production executor is :class:`DockerWorkspaceExecutor`, which requires the
built v2 image on a linux/arm64 Docker host.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Mapping, Protocol

from ...phase4b.oci_parser_sandbox import (
    OciRuntimeIdentity,
    _bounded_process,
    _closed_json,
    _docker_environment,
)
from ..records import canonical_hash
from .sandbox import (
    MEASUREMENT_POLICY,
    SandboxError,
    SandboxOutcome,
    SandboxProgramRequest,
    _sha256,
)
from .workspace_image_lock import WorkspaceImageLock

WORKSPACE_CONTRACT_VERSION = "adaivy.campaign-workspace-oci-sandbox.v2"
WORKSPACE_POLICY_SCHEMA = "adaivy.campaign-workspace-sandbox-policy.v2"
REQUEST_PROTOCOL_V2 = "adaivy.campaign-workspace-stdin-request.v2"
RESPONSE_PROTOCOL_V2 = "adaivy.campaign-workspace-stdout-response.v2"
PROGRAM_CONTRACT_V2 = "adaivy.campaign-workspace-program.v2"
WORKSPACE_MANIFEST_SCHEMA = "adaivy.campaign-workspace-manifest.v1"
WORKSPACE_RUN_SCHEMA = "adaivy.campaign-workspace-run.v1"
FAILURE_DIAGNOSTICS_SCHEMA = "adaivy.campaign-workspace-failure-diagnostics.v1"
WORKSPACE_MOUNT_PATH = "/workspace"

# Hard structural ceilings (operator-budgeted requests sit strictly below).
MAX_WALL_SECONDS_V2 = 4_500            # 4_500_000 ms
MAX_CPU_SECONDS_V2 = 3_600             # 3_600_000 ms
MAX_MEMORY_BYTES_V2 = 8_589_934_592    # 8 GiB
MIN_MEMORY_BYTES_V2 = 33_554_432
MAX_OPEN_FILES_V2 = 1_024
MAX_PROCESSES_V2 = 64
MAX_TMPFS_BYTES_V2 = 1_073_741_824     # 1 GiB
MAX_TEMP_FILE_BYTES_V2 = 1_073_741_824
MAX_TEMP_INODES_V2 = 16_384
MAX_WORKSPACE_BYTES_V2 = 1_073_741_824  # 1 GiB
MAX_WORKSPACE_INODES_V2 = 65_536
MAX_RESULT_BYTES_V2 = 262_144
MAX_STREAM_BYTES_V2 = 262_144
MAX_STDIN_BYTES_V2 = 4_194_304
MAX_PROGRAM_BYTES_V2 = 262_144
MIN_DETERMINISM_REPLICAS_V2 = 1
MAX_DETERMINISM_REPLICAS_V2 = 4
MAX_STDERR_EXCERPT_CHARS = 2_048

WORKSPACE_REFUSAL_CODES = (
    "workspace_directory_unavailable",
    "workspace_entry_unsupported",
    "workspace_byte_ceiling_exceeded",
    "workspace_inode_ceiling_exceeded",
    "workspace_promotion_failed",
    "nondeterministic_workspace",
)


# The v2 in-container bootstrap.  Same containment structure as v1 -- the fork
# is containment of accident, not a trust boundary; the exact verifier never
# runs here -- with two deliberate differences: the protocol identifiers are
# v2, and the program additionally receives ADAIVY_WORKSPACE, the mount path of
# the persistent campaign workspace.  This text is content-hashed separately
# from the v1 bootstrap and recorded in the v2 activation.
_BOOTSTRAP_V2 = r'''import base64, hashlib, io, json, os, sys, traceback

REQUEST = "adaivy.campaign-workspace-stdin-request.v2"
RESPONSE = "adaivy.campaign-workspace-stdout-response.v2"
CONTRACT = "adaivy.campaign-workspace-program.v2"
FIELDS = {
    "arguments", "input_artifacts", "limits", "program_artifact_hash",
    "program_source_base64", "result_path", "schema_version", "stderr_path",
    "stdout_path", "workspace_path",
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
workspace = payload["workspace_path"]
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
        os.closerange(3, 1024)
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
        "ADAIVY_WORKSPACE": workspace,
        "ADAIVY_INPUT_ARTIFACTS": inputs,
        "ADAIVY_INPUT_ARTIFACT_HASHES": tuple(sorted(inputs)),
        "ADAIVY_ARGUMENTS": tuple(payload["arguments"]),
    }
    status = 0
    try:
        exec(compile(program, "<adaivy-campaign-workspace-program>", "exec"), namespace, namespace)
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

BOOTSTRAP_V2_SHA256 = _sha256(_BOOTSTRAP_V2.encode("utf-8"))

_STDOUT_PATH = "/tmp/adaivy-program-stdout"
_STDERR_PATH = "/tmp/adaivy-program-stderr"
_RESULT_PATH = "/tmp/adaivy-program-result"
_RESPONSE_FIELDS_V2 = frozenset({
    "child_exit_code", "child_signal", "child_wait_status", "input_artifact_hashes",
    "kernel_controls", "program_artifact_hash", "result_base64",
    "result_bytes_observed", "result_present", "result_truncated", "schema_version",
    "stderr_base64", "stderr_bytes_observed", "stderr_truncated", "stdout_base64",
    "stdout_bytes_observed", "stdout_truncated",
})
_CONTAINER_ID_HEX = frozenset("0123456789abcdef")


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceSandboxLimits:
    """v2 ceilings.  Requests configure below them; nothing is raised to fit."""

    max_wall_seconds: int = 120
    max_cpu_seconds: int = 60
    max_memory_bytes: int = 536_870_912
    max_open_files: int = 256
    max_processes: int = 16
    max_temp_file_bytes: int = 67_108_864
    max_tmpfs_bytes: int = 67_108_864
    max_temp_inodes: int = 1_024
    max_workspace_bytes: int = 268_435_456
    max_workspace_inodes: int = 4_096
    max_result_bytes: int = MAX_RESULT_BYTES_V2
    max_stdout_bytes: int = 65_536
    max_stderr_bytes: int = 65_536
    max_stdin_bytes: int = MAX_STDIN_BYTES_V2
    max_program_bytes: int = MAX_PROGRAM_BYTES_V2
    determinism_replicas: int = 2

    def __post_init__(self) -> None:
        ceilings = {
            "max_wall_seconds": (1, MAX_WALL_SECONDS_V2),
            "max_cpu_seconds": (1, MAX_CPU_SECONDS_V2),
            "max_memory_bytes": (MIN_MEMORY_BYTES_V2, MAX_MEMORY_BYTES_V2),
            "max_open_files": (16, MAX_OPEN_FILES_V2),
            "max_processes": (2, MAX_PROCESSES_V2),
            "max_temp_file_bytes": (65_536, MAX_TEMP_FILE_BYTES_V2),
            "max_tmpfs_bytes": (1_048_576, MAX_TMPFS_BYTES_V2),
            "max_temp_inodes": (16, MAX_TEMP_INODES_V2),
            "max_workspace_bytes": (65_536, MAX_WORKSPACE_BYTES_V2),
            "max_workspace_inodes": (16, MAX_WORKSPACE_INODES_V2),
            "max_result_bytes": (1, MAX_RESULT_BYTES_V2),
            "max_stdout_bytes": (1, MAX_STREAM_BYTES_V2),
            "max_stderr_bytes": (1, MAX_STREAM_BYTES_V2),
            "max_stdin_bytes": (1_024, MAX_STDIN_BYTES_V2),
            "max_program_bytes": (1, MAX_PROGRAM_BYTES_V2),
            "determinism_replicas": (
                MIN_DETERMINISM_REPLICAS_V2, MAX_DETERMINISM_REPLICAS_V2,
            ),
        }
        for name, (floor, ceiling) in ceilings.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise SandboxError(f"{name} must be an integer")
            if not floor <= value <= ceiling:
                raise SandboxError(f"{name} is outside the workspace sandbox ceiling")
        if self.max_cpu_seconds > self.max_wall_seconds:
            raise SandboxError("the CPU ceiling may not exceed the wall ceiling")
        streams = self.max_result_bytes + self.max_stdout_bytes + self.max_stderr_bytes
        if streams > self.max_tmpfs_bytes:
            raise SandboxError("the bounded streams do not fit inside the tmpfs bound")

    @property
    def max_container_stdout_bytes(self) -> int:
        payload = self.max_result_bytes + self.max_stdout_bytes + self.max_stderr_bytes
        return 4_096 + ((payload + 2) // 3) * 4

    @property
    def determinism_unverified(self) -> bool:
        """One replica means the determinism gate cannot run.  Recorded, never hidden."""

        return self.determinism_replicas < 2

    def to_record(self) -> dict[str, int]:
        return {
            name: getattr(self, name)
            for name in sorted(self.__dataclass_fields__)
        }


# -- workspace manifests ------------------------------------------------------


def workspace_manifest(
    workspace: Path, *, max_bytes: int, max_inodes: int,
) -> dict[str, Any]:
    """Hash the workspace file inventory into a ledgerable manifest.

    Provenance, not trust: the manifest states exactly what bytes were present
    at a run boundary.  Symlinks and non-regular files are refused outright --
    a symlink inside a bind-mounted workspace is a container-escape vector for
    reads, so its presence is a structural refusal, not an inventory entry.
    """

    if not workspace.is_dir():
        raise SandboxError("workspace_directory_unavailable")
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    inode_count = 0
    stack = [workspace]
    while stack:
        directory = stack.pop()
        for child in sorted(directory.iterdir()):
            if child.is_symlink():
                raise SandboxError("workspace_entry_unsupported")
            if child.is_dir():
                inode_count += 1
                if inode_count > max_inodes:
                    raise SandboxError("workspace_inode_ceiling_exceeded")
                stack.append(child)
                continue
            if not child.is_file():
                raise SandboxError("workspace_entry_unsupported")
            inode_count += 1
            data = child.read_bytes()
            total_bytes += len(data)
            entries.append({
                "path": child.relative_to(workspace).as_posix(),
                "sha256": _sha256(data),
                "size": len(data),
            })
            if total_bytes > max_bytes:
                raise SandboxError("workspace_byte_ceiling_exceeded")
            if inode_count > max_inodes:
                raise SandboxError("workspace_inode_ceiling_exceeded")
    entries.sort(key=lambda item: item["path"])
    value: dict[str, Any] = {
        "entries": entries,
        "file_count": len(entries),
        "inode_count": inode_count,
        "schema_version": WORKSPACE_MANIFEST_SCHEMA,
        "total_bytes": total_bytes,
    }
    value["content_hash"] = canonical_hash(value)
    return value


def manifest_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """Paths added, removed, and changed between two run-boundary manifests."""

    old = {item["path"]: item["sha256"] for item in before["entries"]}
    new = {item["path"]: item["sha256"] for item in after["entries"]}
    return {
        "added": sorted(set(new) - set(old)),
        "changed": sorted(
            path for path in set(old) & set(new) if old[path] != new[path]
        ),
        "removed": sorted(set(old) - set(new)),
    }


# -- container execution port -------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceContainerObservation:
    """What the host observed about one container run.  Operational data."""

    exit_code: int | None
    timed_out: bool
    output_limit: str | None
    stdout: bytes
    stderr: bytes
    stdout_observed: int
    oom_killed: bool
    wall_milliseconds: int


class WorkspaceExecutorRefusal(ValueError):
    """The executor could not produce a trustworthy container observation."""


class WorkspaceContainerExecutorPort(Protocol):
    """One fresh container run against one replica workspace directory."""

    def execute(
        self, *, command: tuple[str, ...], stdin_payload: bytes,
        workspace_path: Path, wall_seconds: int, stdout_limit: int,
        stderr_limit: int,
    ) -> WorkspaceContainerObservation: ...


class DockerWorkspaceExecutor:
    """The only production executor: digest-pinned Docker on linux/arm64.

    This mirrors the v1 mechanics -- cidfile, state inspection, forced removal
    -- and refuses with a typed code on every path where the kernel-control
    state cannot be confirmed.  It is exercised only on a host with the built
    v2 image; offline tests inject a fake executor instead.
    """

    def __init__(self, runtime: OciRuntimeIdentity) -> None:
        self.runtime = runtime

    def _state(self, container_id: str) -> dict[str, Any]:
        completed = subprocess.run(
            (
                self.runtime.docker_executable, "container", "inspect",
                container_id, "--format", "{{json .State}}",
            ),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=_docker_environment(
                Path(self.runtime.docker_executable), self.runtime.daemon_host,
            ),
            check=False, timeout=15,
        )
        if completed.returncode != 0:
            raise ValueError("workspace container state unavailable")
        return _closed_json(completed.stdout, "workspace sandbox container state")

    def _remove(self, container_id: str) -> bool:
        try:
            completed = subprocess.run(
                (self.runtime.docker_executable, "container", "rm", "--force", container_id),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=_docker_environment(
                    Path(self.runtime.docker_executable), self.runtime.daemon_host,
                ),
                check=False, timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0

    def execute(
        self, *, command: tuple[str, ...], stdin_payload: bytes,
        workspace_path: Path, wall_seconds: int, stdout_limit: int,
        stderr_limit: int,
    ) -> WorkspaceContainerObservation:
        started = time.monotonic()
        try:
            measured = OciRuntimeIdentity.measure(
                docker_executable=Path(self.runtime.docker_executable),
                daemon_host=self.runtime.daemon_host,
                image_reference=self.runtime.image_reference,
                platform=self.runtime.platform,
            )
        except (OSError, ValueError) as error:
            raise WorkspaceExecutorRefusal("sandbox_runtime_unavailable") from error
        if measured != self.runtime:
            raise WorkspaceExecutorRefusal("sandbox_runtime_identity_mismatch")
        state: dict[str, Any] = {}
        cleanup_ok = False
        with tempfile.TemporaryDirectory(prefix="adaivy-workspace-oci-") as temporary:
            cidfile = Path(temporary) / "cid"
            full_command = tuple(
                item.replace("__CIDFILE__", str(cidfile)) for item in command
            )
            try:
                process = _bounded_process(
                    full_command, input_bytes=stdin_payload,
                    environment=_docker_environment(
                        Path(self.runtime.docker_executable), self.runtime.daemon_host,
                    ),
                    wall_seconds=wall_seconds,
                    stdout_limit=stdout_limit,
                    stderr_limit=stderr_limit,
                )
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                raise WorkspaceExecutorRefusal("sandbox_launch_failed") from error
            container_id = ""
            try:
                if cidfile.is_file():
                    container_id = cidfile.read_text("ascii").strip()
                if len(container_id) == 64 and set(container_id) <= _CONTAINER_ID_HEX:
                    state = self._state(container_id)
            except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):
                state = {}
            finally:
                if container_id:
                    cleanup_ok = self._remove(container_id)
        if (
            not state
            or not cleanup_ok
            or not isinstance(state.get("OOMKilled"), bool)
            or state.get("ExitCode") != process.exit_code
        ):
            raise WorkspaceExecutorRefusal("sandbox_control_state_unavailable")
        return WorkspaceContainerObservation(
            exit_code=process.exit_code,
            timed_out=process.timed_out,
            output_limit=process.output_limit,
            stdout=process.stdout,
            stderr=process.stderr,
            stdout_observed=process.stdout_observed,
            oom_killed=state.get("OOMKilled") is True,
            wall_milliseconds=max(0, int((time.monotonic() - started) * 1_000)),
        )


# -- execution records ---------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceExecution:
    """One v2 execution: replicas, determinism verdict, workspace manifests."""

    status: str
    refusal_code: str | None
    replicas: tuple[SandboxOutcome, ...]
    deterministic: bool
    determinism_replicas: int
    determinism_unverified: bool
    outcome: SandboxOutcome
    workspace_manifest_before: Mapping[str, Any]
    workspace_manifest_after: Mapping[str, Any] | None
    workspace_promoted: bool

    @property
    def workspace_delta(self) -> dict[str, Any] | None:
        if self.workspace_manifest_after is None:
            return None
        return manifest_delta(self.workspace_manifest_before, self.workspace_manifest_after)

    def failure_diagnostics(self) -> dict[str, Any] | None:
        """Structured failure-as-data.  ``None`` unless the program failed."""

        if self.status != "program_failed":
            return None
        outcome = self.outcome
        value: dict[str, Any] = {
            "child_exit_code": outcome.child_exit_code,
            "child_signal": outcome.child_signal,
            "epistemic_warrant_created": False,
            "refusal_code": self.refusal_code,
            "result_present": outcome.result is not None,
            "schema_version": FAILURE_DIAGNOSTICS_SCHEMA,
            "stderr_bytes_observed": outcome.stderr_bytes_observed,
            "stderr_excerpt": outcome.stderr.decode("utf-8", "replace")[
                :MAX_STDERR_EXCERPT_CHARS
            ],
            "stderr_sha256": _sha256(outcome.stderr),
            "stderr_truncated": outcome.stderr_truncated,
            "workspace_delta": self.workspace_delta,
        }
        value["content_hash"] = canonical_hash(value)
        return value

    def semantic_record(self) -> dict[str, Any]:
        """The ledger's run-boundary record: replicas plus workspace manifests."""

        value: dict[str, Any] = {
            "determinism_replicas": self.determinism_replicas,
            "determinism_unverified": self.determinism_unverified,
            "deterministic": self.deterministic,
            "failure_diagnostics": self.failure_diagnostics(),
            "refusal_code": self.refusal_code,
            "replica_count": len(self.replicas),
            "replicas": [item.semantic_record() for item in self.replicas],
            "schema_version": WORKSPACE_RUN_SCHEMA,
            "status": self.status,
            "workspace_delta": self.workspace_delta,
            "workspace_manifest_after_hash": (
                None if self.workspace_manifest_after is None
                else self.workspace_manifest_after["content_hash"]
            ),
            "workspace_manifest_before_hash": (
                self.workspace_manifest_before["content_hash"]
            ),
            "workspace_promoted": self.workspace_promoted,
        }
        value["content_hash"] = canonical_hash(value)
        return value

    def operational_record(self) -> dict[str, Any]:
        return {
            "measurement_policy": MEASUREMENT_POLICY,
            "replicas": [item.operational_record() for item in self.replicas],
            "wall_milliseconds": sum(item.wall_milliseconds for item in self.replicas),
        }


# -- the sandbox ----------------------------------------------------------------


def _policy_v2(
    runtime: OciRuntimeIdentity, lock: WorkspaceImageLock,
    limits: WorkspaceSandboxLimits,
) -> dict[str, Any]:
    return {
        "capabilities": "drop_all",
        "cpu": "kernel_rlimit_cpu_plus_cgroup_single_cpu",
        "determinism": (
            "byte_identical_result_and_workspace_across_fresh_containers"
        ),
        "determinism_replicas_configurable": [
            MIN_DETERMINISM_REPLICAS_V2, MAX_DETERMINISM_REPLICAS_V2,
        ],
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
        "packages": [item.to_record() for item in lock.packages],
        "platform": runtime.platform,
        "processes": "kernel_cgroup_pids_limit",
        "program_transport": "bounded_stdin_no_program_mount",
        "protocol_request": REQUEST_PROTOCOL_V2,
        "protocol_response": RESPONSE_PROTOCOL_V2,
        "pull_policy": "never",
        "root_filesystem": "read_only",
        "runtime_role": lock.runtime_role,
        "schema_version": WORKSPACE_POLICY_SCHEMA,
        "secrets": "closed_docker_client_environment_and_no_host_mounts",
        "site_packages": "importable_exact_allowlist_only",
        "temporary": "bounded_noexec_nosuid_nodev_tmpfs",
        "user": "65534:65534",
        "verifier_location": "host_process_outside_container",
        "workspace": "campaign_scoped_bind_mount_manifest_hashed_each_run",
        "workspace_mount": WORKSPACE_MOUNT_PATH,
    }


class WorkspaceSandbox:
    """Execute untrusted programs in the exact v2 image over one workspace.

    A mechanism, not an authorization: :mod:`.workspace_activation` holds the
    release condition, and :mod:`.workspace_runner` refuses to run without it.
    Repeated ``run`` calls against the same workspace directory are the point:
    each run sees the promoted state of the previous one, and every boundary is
    manifest-hashed.
    """

    contract_version = WORKSPACE_CONTRACT_VERSION

    def __init__(
        self, *, expected_runtime: OciRuntimeIdentity,
        image_lock: WorkspaceImageLock, executor: WorkspaceContainerExecutorPort,
        limits: WorkspaceSandboxLimits | None = None,
    ) -> None:
        if image_lock.pending:
            raise SandboxError(
                "workspace image lock digests are pending the operator build"
            )
        if expected_runtime.image_reference != image_lock.image_reference:
            raise SandboxError("runtime image differs from the digest-pinned v2 lock")
        if expected_runtime.platform != image_lock.platform:
            raise SandboxError("runtime platform differs from the digest-pinned v2 lock")
        if image_lock.pull_policy != "never" or image_lock.network_default != "none":
            raise SandboxError("workspace lock relaxed the pull or network policy")
        self.expected_runtime = expected_runtime
        self.image_lock = image_lock
        self.executor = executor
        self.limits = limits or WorkspaceSandboxLimits()

    @property
    def policy_sha256(self) -> str:
        return canonical_hash(
            _policy_v2(self.expected_runtime, self.image_lock, self.limits)
        )

    @property
    def control_policy_sha256(self) -> str:
        value = _policy_v2(self.expected_runtime, self.image_lock, self.limits)
        value.pop("limits")
        return canonical_hash(value)

    @property
    def bootstrap_sha256(self) -> str:
        return BOOTSTRAP_V2_SHA256

    @property
    def environment_sha256(self) -> str:
        return self.expected_runtime.environment_sha256

    def policy_record(self) -> dict[str, Any]:
        return _policy_v2(self.expected_runtime, self.image_lock, self.limits)

    def configuration_record(self) -> dict[str, Any]:
        return {
            "bootstrap_sha256": self.bootstrap_sha256,
            "contract_version": WORKSPACE_CONTRACT_VERSION,
            "control_policy_sha256": self.control_policy_sha256,
            "determinism_unverified": self.limits.determinism_unverified,
            "environment_sha256": self.environment_sha256,
            "image_lock": self.image_lock.to_record(),
            "limits": self.limits.to_record(),
            "measurement_policy": MEASUREMENT_POLICY,
            "policy_sha256": self.policy_sha256,
            "program_contract": PROGRAM_CONTRACT_V2,
            "protocol_request": REQUEST_PROTOCOL_V2,
            "protocol_response": RESPONSE_PROTOCOL_V2,
        }

    def command(self, workspace_path: Path) -> tuple[str, ...]:
        """The v1 kernel-control set, plus the workspace bind mount, minus -S.

        ``__CIDFILE__`` is a placeholder the production executor substitutes
        with its per-run cidfile; fake executors ignore it.
        """

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
            (
                f"--mount=type=bind,source={workspace_path},"
                f"destination={WORKSPACE_MOUNT_PATH}"
            ),
            "--workdir=/tmp",
            "--env=LANG=C.UTF-8",
            "--env=PYTHONHASHSEED=0",
            "--cidfile=__CIDFILE__",
            "--entrypoint=python3",
            runtime.image_reference,
            # -I (implies -E and -s) but NOT -S: the exact allowlisted
            # site-packages of the v2 image are importable.  This is the one
            # deliberate interpreter difference from v1.
            "-I", "-c", _BOOTSTRAP_V2,
        )

    def stdin_payload(self, request: SandboxProgramRequest) -> bytes:
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
            "schema_version": REQUEST_PROTOCOL_V2,
            "stderr_path": _STDERR_PATH,
            "stdout_path": _STDOUT_PATH,
            "workspace_path": WORKSPACE_MOUNT_PATH,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    # -- one replica -----------------------------------------------------------

    def _refused_outcome(self, code: str, *, wall: int = 0) -> SandboxOutcome:
        return SandboxOutcome(
            status="refused", refusal_code=code, result=None,
            result_bytes_observed=0, result_truncated=False, stdout=b"",
            stdout_bytes_observed=0, stdout_truncated=False, stderr=b"",
            stderr_bytes_observed=0, stderr_truncated=False,
            container_exit_code=None, child_exit_code=None, child_signal=None,
            oom_killed=False, wall_timed_out=False,
            container_stdout_bytes_observed=0, container_stderr=b"",
            kernel_controls={}, wall_milliseconds=wall,
        )

    def _run_replica(
        self, request: SandboxProgramRequest, payload: bytes, replica_dir: Path,
    ) -> SandboxOutcome:
        try:
            observation = self.executor.execute(
                command=self.command(replica_dir),
                stdin_payload=payload,
                workspace_path=replica_dir,
                wall_seconds=self.limits.max_wall_seconds,
                stdout_limit=self.limits.max_container_stdout_bytes,
                stderr_limit=MAX_STREAM_BYTES_V2,
            )
        except WorkspaceExecutorRefusal as error:
            return self._refused_outcome(str(error.args[0]))
        wall = observation.wall_milliseconds
        if observation.timed_out:
            return self._refused_outcome("sandbox_wall_time_exceeded", wall=wall)
        if observation.output_limit:
            return self._refused_outcome(
                f"sandbox_container_{observation.output_limit}_limit_exceeded", wall=wall,
            )
        if observation.oom_killed:
            return self._refused_outcome("sandbox_memory_limit_exceeded", wall=wall)
        if observation.exit_code != 0:
            return self._refused_outcome("sandbox_container_nonzero_exit", wall=wall)
        return self._decode(request, observation)

    def _decode(
        self, request: SandboxProgramRequest,
        observation: WorkspaceContainerObservation,
    ) -> SandboxOutcome:
        wall = observation.wall_milliseconds
        raw = observation.stdout
        if len(raw) > self.limits.max_container_stdout_bytes:
            return self._refused_outcome("sandbox_response_bound_exceeded", wall=wall)
        try:
            value = _closed_json(raw, "workspace sandbox response")
        except ValueError:
            return self._refused_outcome("sandbox_response_invalid", wall=wall)
        if json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8") != raw:
            return self._refused_outcome("sandbox_response_not_canonical", wall=wall)
        if (
            frozenset(value) != _RESPONSE_FIELDS_V2
            or value["schema_version"] != RESPONSE_PROTOCOL_V2
            or value["program_artifact_hash"] != request.program_artifact_hash
            or value["input_artifact_hashes"] != list(request.input_artifact_hashes)
        ):
            return self._refused_outcome("sandbox_response_invalid", wall=wall)
        try:
            result, result_observed, result_truncated = _stream(
                value, "result", self.limits.max_result_bytes, optional=True,
            )
            stdout, stdout_observed, stdout_truncated = _stream(
                value, "stdout", self.limits.max_stdout_bytes,
            )
            stderr, stderr_observed, stderr_truncated = _stream(
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
            return self._refused_outcome("sandbox_response_invalid", wall=wall)

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
            container_exit_code=observation.exit_code, child_exit_code=child_exit,
            child_signal=child_signal, oom_killed=False, wall_timed_out=False,
            container_stdout_bytes_observed=observation.stdout_observed,
            container_stderr=observation.stderr[:4_096],
            kernel_controls={
                str(key): int(controls[key]) for key in sorted(controls)
            },
            wall_milliseconds=wall,
        )

    # -- the run boundary --------------------------------------------------------

    def run(self, request: SandboxProgramRequest, workspace: Path) -> WorkspaceExecution:
        """Run the program over the campaign workspace, replicated, manifested.

        Each replica runs a fresh container over a fresh COPY of the pre-run
        workspace state; the persistent workspace is only promoted to a
        replica's post-state when the execution was not refused, so a
        nondeterministic or sandbox-refused run cannot corrupt campaign state.
        A ``program_failed`` run IS promoted and recorded: its partial writes
        and diagnostics are data the next iteration may build on.
        """

        try:
            before = workspace_manifest(
                workspace, max_bytes=self.limits.max_workspace_bytes,
                max_inodes=self.limits.max_workspace_inodes,
            )
        except SandboxError as error:
            outcome = self._refused_outcome(str(error.args[0]))
            return self._refused_execution(outcome, {
                "content_hash": canonical_hash({"unavailable": True}),
                "entries": [], "file_count": 0, "inode_count": 0,
                "schema_version": WORKSPACE_MANIFEST_SCHEMA, "total_bytes": 0,
            })
        try:
            payload = self.stdin_payload(request)
        except SandboxError as error:
            return self._refused_execution(
                self._refused_outcome(str(error.args[0])), before,
            )
        if len(payload) > self.limits.max_stdin_bytes:
            return self._refused_execution(
                self._refused_outcome("sandbox_stdin_byte_bound"), before,
            )

        replicas: list[SandboxOutcome] = []
        post_manifests: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="adaivy-workspace-replicas-") as staging:
            replica_dirs: list[Path] = []
            for index in range(self.limits.determinism_replicas):
                replica_dir = Path(staging) / f"replica-{index}"
                shutil.copytree(workspace, replica_dir, symlinks=False)
                replica_dirs.append(replica_dir)
                outcome = self._run_replica(request, payload, replica_dir)
                replicas.append(outcome)
                if outcome.status == "refused":
                    return self._refused_execution(
                        outcome, before, replicas=tuple(replicas),
                    )
                try:
                    post_manifests.append(workspace_manifest(
                        replica_dir, max_bytes=self.limits.max_workspace_bytes,
                        max_inodes=self.limits.max_workspace_inodes,
                    ))
                except SandboxError as error:
                    return self._refused_execution(
                        self._refused_outcome(str(error.args[0])), before,
                        replicas=tuple(replicas),
                    )

            divergence = self._divergence(replicas, post_manifests)
            if divergence is not None:
                return self._refused_execution(
                    self._refused_outcome(divergence), before,
                    replicas=tuple(replicas),
                )
            promoted = self._promote(workspace, replica_dirs[0])
            if not promoted:
                return self._refused_execution(
                    self._refused_outcome("workspace_promotion_failed"), before,
                    replicas=tuple(replicas),
                )

        first = replicas[0]
        unverified = self.limits.determinism_unverified
        return WorkspaceExecution(
            status=first.status, refusal_code=first.refusal_code,
            replicas=tuple(replicas),
            deterministic=not unverified,
            determinism_replicas=self.limits.determinism_replicas,
            determinism_unverified=unverified,
            outcome=first,
            workspace_manifest_before=before,
            workspace_manifest_after=post_manifests[0],
            workspace_promoted=True,
        )

    def _divergence(
        self, replicas: list[SandboxOutcome], manifests: list[dict[str, Any]],
    ) -> str | None:
        first = replicas[0]
        for other, manifest in zip(replicas[1:], manifests[1:]):
            if first.result != other.result:
                return "nondeterministic_result"
            if first.stdout != other.stdout:
                return "nondeterministic_stdout"
            if first.stderr != other.stderr:
                return "nondeterministic_stderr"
            if (
                first.child_exit_code != other.child_exit_code
                or first.child_signal != other.child_signal
                or first.refusal_code != other.refusal_code
            ):
                return "nondeterministic_exit"
            if manifests[0]["content_hash"] != manifest["content_hash"]:
                return "nondeterministic_workspace"
        return None

    @staticmethod
    def _promote(workspace: Path, replica_dir: Path) -> bool:
        """Replace the persistent workspace contents with the replica state."""

        try:
            for child in workspace.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            for child in replica_dir.iterdir():
                if child.is_dir():
                    shutil.copytree(child, workspace / child.name, symlinks=False)
                else:
                    shutil.copy2(child, workspace / child.name)
        except OSError:
            return False
        return True

    def _refused_execution(
        self, outcome: SandboxOutcome, before: Mapping[str, Any],
        *, replicas: tuple[SandboxOutcome, ...] = (),
    ) -> WorkspaceExecution:
        return WorkspaceExecution(
            status="refused", refusal_code=outcome.refusal_code,
            replicas=replicas or (outcome,),
            deterministic=False,
            determinism_replicas=self.limits.determinism_replicas,
            determinism_unverified=self.limits.determinism_unverified,
            outcome=outcome,
            workspace_manifest_before=before,
            workspace_manifest_after=None,
            workspace_promoted=False,
        )


def _stream(
    value: Mapping[str, Any], name: str, limit: int, *, optional: bool = False,
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


__all__ = [
    "BOOTSTRAP_V2_SHA256", "DockerWorkspaceExecutor",
    "FAILURE_DIAGNOSTICS_SCHEMA", "MAX_CPU_SECONDS_V2",
    "MAX_DETERMINISM_REPLICAS_V2", "MAX_MEMORY_BYTES_V2", "MAX_WALL_SECONDS_V2",
    "MAX_WORKSPACE_BYTES_V2", "MAX_WORKSPACE_INODES_V2",
    "MIN_DETERMINISM_REPLICAS_V2", "PROGRAM_CONTRACT_V2", "REQUEST_PROTOCOL_V2",
    "RESPONSE_PROTOCOL_V2", "WORKSPACE_CONTRACT_VERSION",
    "WORKSPACE_MANIFEST_SCHEMA", "WORKSPACE_MOUNT_PATH",
    "WORKSPACE_POLICY_SCHEMA", "WORKSPACE_REFUSAL_CODES", "WORKSPACE_RUN_SCHEMA",
    "WorkspaceContainerExecutorPort", "WorkspaceContainerObservation",
    "WorkspaceExecution", "WorkspaceExecutorRefusal", "WorkspaceSandbox",
    "WorkspaceSandboxLimits", "manifest_delta", "workspace_manifest",
]
