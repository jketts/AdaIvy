"""Optional exact-image OCI sandbox for Phase 4B parser workers.

The ordinary offline suite does not require a container runtime or image.  A
caller must supply a previously reviewed :class:`OciRuntimeIdentity`; every
execution re-measures the local Docker engine and image and fails closed if the
identity changed.  The image is always addressed by digest and ``--pull=never``
prevents this boundary from acquiring dependencies implicitly.

Unlike the named-Darwin probe, the memory ceiling is a kernel cgroup limit, not
a sampled observation.  The parser source and request enter on stdin, no host
path is mounted, and the container runs non-root with no network, a read-only
root, a bounded noexec tmpfs, no capabilities, and fixed CPU/process/file
limits.  This module establishes an optional sandbox mechanism; it does not
activate a production parser by itself.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
from typing import Any, Mapping

from .parser_sandbox import (
    RESPONSE_SCHEMA,
    _decode_outcome,
    _kill_worker,
    _request_envelope,
)
from .parsing import (
    MAX_WORKER_CAPTURE_BYTES,
    PARSER_BOUNDS,
    ParseRequest,
    WorkerExecution,
)
from .serialization import canonical_hash


CONTRACT_VERSION = "adaivy.phase4b-oci-parser-sandbox.v1"
RUNTIME_SCHEMA = "adaivy.phase4b-oci-runtime-identity.v1"
POLICY_SCHEMA = "adaivy.phase4b-oci-sandbox-policy.v1"
_MAX_CONTROL_OUTPUT_BYTES = 1_048_576
_MAX_STDIN_ENVELOPE_BYTES = 4_194_304
_IMAGE_REFERENCE = re.compile(
    r"^[a-z0-9][a-z0-9._:-]*(?:/[a-z0-9][a-z0-9._-]*)+"
    r"@sha256:[0-9a-f]{64}$"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PLATFORM = re.compile(r"^linux/(?:amd64|arm64|arm/v[67]|386|ppc64le|s390x|riscv64)$")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _exact_image_reference(value: str) -> str:
    if not isinstance(value, str) or _IMAGE_REFERENCE.fullmatch(value) is None:
        raise ValueError("OCI image reference must be an exact sha256 digest reference")
    return value


def _unix_daemon_host(value: str) -> str:
    if not isinstance(value, str) or not value.startswith("unix:///"):
        raise ValueError("OCI daemon host must be an absolute Unix socket")
    path = Path(value.removeprefix("unix://"))
    if not path.is_absolute() or ".." in path.parts or "\x00" in value:
        raise ValueError("OCI daemon host is invalid")
    return value


def _platform(value: str) -> str:
    if not isinstance(value, str) or _PLATFORM.fullmatch(value) is None:
        raise ValueError("OCI platform is outside the closed Linux inventory")
    return value


def _docker_environment(executable: Path, daemon_host: str) -> dict[str, str]:
    return {
        "DOCKER_HOST": daemon_host,
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": str(executable.parent),
    }


def _control_command(
    command: tuple[str, ...], *, executable: Path, daemon_host: str,
) -> bytes:
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_docker_environment(executable, daemon_host),
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("OCI control command unavailable") from error
    if completed.returncode != 0:
        raise ValueError("OCI control command failed closed")
    if len(completed.stdout) > _MAX_CONTROL_OUTPUT_BYTES:
        raise ValueError("OCI control output exceeded its bound")
    return completed.stdout


def _closed_json(data: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"{label} contains duplicate keys")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not an object")
    return value


@dataclass(frozen=True, slots=True)
class OciRuntimeIdentity:
    """Reviewed local engine and exact-image identity.

    ``measure`` performs no pull and no container launch.  Persist the returned
    record in an owner-reviewed activation artifact; constructing it ad hoc is
    diagnostic measurement, not authorization.
    """

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
            raise ValueError("OCI runtime schema differs")
        executable = Path(self.docker_executable)
        if not executable.is_absolute():
            raise ValueError("Docker executable must be absolute")
        _unix_daemon_host(self.daemon_host)
        _platform(self.platform)
        _exact_image_reference(self.image_reference)
        for field in (
            "docker_executable_sha256", "image_descriptor_digest", "image_id",
            "docker_server_sha256", "environment_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, field)) is None:
                raise ValueError(f"{field} is not canonical sha256")
        if self.image_os != "linux" or not self.image_architecture:
            raise ValueError("OCI image platform identity differs")
        if not self.image_layers or any(_SHA256.fullmatch(item) is None for item in self.image_layers):
            raise ValueError("OCI image layer inventory is invalid")
        if self.environment_sha256 != canonical_hash(self._preimage()):
            raise ValueError("OCI runtime environment hash differs")

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
            "schema_version": self.schema_version,
        }

    def to_record(self) -> dict[str, Any]:
        return {**self._preimage(), "environment_sha256": self.environment_sha256}

    @classmethod
    def measure(
        cls, *, docker_executable: Path, daemon_host: str,
        image_reference: str, platform: str,
    ) -> "OciRuntimeIdentity":
        executable = docker_executable.resolve(strict=True)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError("Docker executable is unavailable")
        daemon_host = _unix_daemon_host(daemon_host)
        image_reference = _exact_image_reference(image_reference)
        platform = _platform(platform)
        executable_sha256 = _sha256_bytes(executable.read_bytes())
        server = _closed_json(
            _control_command(
                (str(executable), "version", "--format", "{{json .Server}}"),
                executable=executable, daemon_host=daemon_host,
            ),
            "Docker server identity",
        )
        image = _closed_json(
            _control_command(
                (str(executable), "image", "inspect", image_reference, "--format", "{{json .}}"),
                executable=executable, daemon_host=daemon_host,
            ),
            "OCI image identity",
        )
        descriptor = image.get("Descriptor")
        root = image.get("RootFS")
        repo_digests = image.get("RepoDigests")
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("digest") != image_reference.rsplit("@", 1)[1]
            or not isinstance(repo_digests, list)
            or image_reference.split("/", 2)[-1] not in repo_digests
            or not isinstance(root, dict)
            or not isinstance(root.get("Layers"), list)
        ):
            raise ValueError("local OCI image is not the exact configured digest")
        preimage: dict[str, Any] = {
            "daemon_host": daemon_host,
            "docker_executable": str(executable),
            "docker_executable_sha256": executable_sha256,
            "docker_server_sha256": canonical_hash(server),
            "image_architecture": image.get("Architecture"),
            "image_descriptor_digest": descriptor["digest"],
            "image_id": image.get("Id"),
            "image_layers": list(root["Layers"]),
            "image_os": image.get("Os"),
            "image_reference": image_reference,
            "platform": platform,
            "schema_version": RUNTIME_SCHEMA,
        }
        return cls(
            schema_version=RUNTIME_SCHEMA,
            docker_executable=str(executable),
            docker_executable_sha256=executable_sha256,
            daemon_host=daemon_host,
            platform=platform,
            image_reference=image_reference,
            image_descriptor_digest=descriptor["digest"],
            image_id=image.get("Id"),
            image_os=image.get("Os"),
            image_architecture=image.get("Architecture"),
            image_layers=tuple(root["Layers"]),
            docker_server_sha256=canonical_hash(server),
            environment_sha256=canonical_hash(preimage),
        )


@dataclass(frozen=True, slots=True)
class OciSandboxLimits:
    max_wall_seconds: int = PARSER_BOUNDS.max_wall_seconds
    max_cpu_seconds: int = PARSER_BOUNDS.max_wall_seconds
    max_memory_bytes: int = PARSER_BOUNDS.max_memory_bytes
    max_open_files: int = PARSER_BOUNDS.max_open_files
    max_processes: int = PARSER_BOUNDS.max_processes
    max_stdout_bytes: int = MAX_WORKER_CAPTURE_BYTES
    max_stderr_bytes: int = MAX_WORKER_CAPTURE_BYTES
    max_temp_file_bytes: int = PARSER_BOUNDS.max_temp_bytes

    def __post_init__(self) -> None:
        ceilings = {
            "max_wall_seconds": PARSER_BOUNDS.max_wall_seconds,
            "max_cpu_seconds": PARSER_BOUNDS.max_wall_seconds,
            "max_memory_bytes": PARSER_BOUNDS.max_memory_bytes,
            "max_open_files": PARSER_BOUNDS.max_open_files,
            "max_processes": PARSER_BOUNDS.max_processes,
            "max_stdout_bytes": MAX_WORKER_CAPTURE_BYTES,
            "max_stderr_bytes": MAX_WORKER_CAPTURE_BYTES,
            "max_temp_file_bytes": PARSER_BOUNDS.max_temp_bytes,
        }
        for field, ceiling in ceilings.items():
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= ceiling:
                raise ValueError(f"{field} is outside the Phase 4B parser ceiling")

    def to_record(self) -> dict[str, int]:
        return {
            field: getattr(self, field)
            for field in (
                "max_cpu_seconds", "max_memory_bytes", "max_open_files",
                "max_processes", "max_stderr_bytes", "max_stdout_bytes",
                "max_temp_file_bytes", "max_wall_seconds",
            )
        }


def _policy(runtime: OciRuntimeIdentity, limits: OciSandboxLimits) -> dict[str, Any]:
    return {
        "capabilities": "drop_all",
        "cpu": "kernel_rlimit_cpu_plus_cgroup_single_cpu",
        "image": runtime.image_reference,
        "memory": "kernel_cgroup_memory_and_swap_hard_ceiling",
        "network": "oci_network_namespace_none",
        "no_new_privileges": True,
        "open_files": "kernel_rlimit_nofile",
        "platform": runtime.platform,
        "processes": "kernel_cgroup_pids_limit",
        "pull_policy": "never",
        "root_filesystem": "read_only",
        "schema_version": POLICY_SCHEMA,
        "secrets": "closed_docker_client_environment_and_no_host_mounts",
        "temporary": "bounded_noexec_nosuid_nodev_tmpfs",
        "user": "65534:65534",
        "limits": limits.to_record(),
    }


_BOOTSTRAP = r'''import base64, io, json, sys
payload = json.loads(sys.stdin.buffer.read())
if set(payload) != {"request_base64", "schema_version", "worker_source"}:
    raise SystemExit(91)
if payload["schema_version"] != "phase4b-oci-stdin-worker-v1":
    raise SystemExit(92)
source = payload["worker_source"]
request = base64.b64decode(payload["request_base64"], validate=True)
if not isinstance(source, str) or not source:
    raise SystemExit(93)
sys.stdin = io.TextIOWrapper(io.BytesIO(request), encoding="utf-8")
namespace = {"__name__": "__main__", "__builtins__": __builtins__}
exec(compile(source, "<phase4b-pinned-parser>", "exec"), namespace, namespace)
'''


@dataclass(frozen=True, slots=True)
class OciSandboxExecutionEvidence:
    schema_version: str
    status: str
    failure_code: str | None
    environment_sha256: str
    policy_sha256: str
    worker_source_sha256: str
    bootstrap_sha256: str
    strict_transient_memory_enforcement: bool
    no_network_enforcement: bool
    read_only_input_and_root_enforcement: bool
    bounded_noexec_temporary_enforcement: bool
    no_ambient_secrets_enforcement: bool
    resource_limits_enforcement: bool
    limits: dict[str, int]
    wall_milliseconds: int
    stdout_bytes_observed: int
    stderr_bytes_observed: int
    exit_code: int | None
    oom_killed: bool

    def to_record(self) -> dict[str, Any]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class _BoundedProcessResult:
    stdout: bytes
    stderr: bytes
    stdout_observed: int
    stderr_observed: int
    exit_code: int | None
    timed_out: bool
    output_limit: str | None


def _bounded_process(
    command: tuple[str, ...], *, input_bytes: bytes, environment: dict[str, str],
    wall_seconds: int, stdout_limit: int, stderr_limit: int,
) -> _BoundedProcessResult:
    # ``selectors`` is network-capable in the repository's structural scan,
    # so load it only inside this explicit OCI execution boundary.  It is used
    # solely with the anonymous stdin/stdout/stderr pipes below.
    import selectors

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        start_new_session=True,
    )
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    streams = selectors.DefaultSelector()
    for stream, event, label in (
        (process.stdin, selectors.EVENT_WRITE, "stdin"),
        (process.stdout, selectors.EVENT_READ, "stdout"),
        (process.stderr, selectors.EVENT_READ, "stderr"),
    ):
        os.set_blocking(stream.fileno(), False)
        streams.register(stream, event, label)
    stdout = bytearray()
    stderr = bytearray()
    sent = 0
    timed_out = False
    output_limit: str | None = None
    deadline = time.monotonic() + wall_seconds
    try:
        while streams.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            for key, _mask in streams.select(min(remaining, 0.1)):
                stream = key.fileobj
                label = key.data
                if label == "stdin":
                    try:
                        sent += os.write(stream.fileno(), input_bytes[sent:sent + 65_536])
                    except BrokenPipeError:
                        sent = len(input_bytes)
                    if sent == len(input_bytes):
                        streams.unregister(stream)
                        stream.close()
                    continue
                chunk = os.read(stream.fileno(), 65_536)
                if not chunk:
                    streams.unregister(stream)
                    stream.close()
                    continue
                target = stdout if label == "stdout" else stderr
                maximum = stdout_limit if label == "stdout" else stderr_limit
                target.extend(chunk)
                if len(target) > maximum:
                    output_limit = label
                    break
            if output_limit:
                break
            if process.poll() is not None and not streams.get_map():
                break
        if timed_out or output_limit:
            _kill_worker(process)
        try:
            exit_code = process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _kill_worker(process)
            exit_code = process.wait(timeout=2)
    finally:
        streams.close()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
    return _BoundedProcessResult(
        bytes(stdout[:stdout_limit]), bytes(stderr[:stderr_limit]),
        len(stdout), len(stderr), exit_code, timed_out, output_limit,
    )


class OciParserSandboxWorker:
    """Execute one pinned parser source in an exact, preinstalled OCI image."""

    sandbox_contract = "external-os-sandbox-contract-v1"

    def __init__(
        self, *, name: str, version: str, worker_source: str,
        expected_runtime: OciRuntimeIdentity,
        limits: OciSandboxLimits | None = None,
    ) -> None:
        if not name or not version or not worker_source:
            raise ValueError("worker identity and source are required")
        if len(worker_source.encode("utf-8")) > 262_144:
            raise ValueError("worker source exceeds its closed bound")
        self.name = name
        self.version = version
        self.worker_source = worker_source
        self.implementation_sha256 = _sha256_bytes(worker_source.encode("utf-8"))
        self.dependency_environment_sha256 = expected_runtime.environment_sha256
        self.expected_runtime = expected_runtime
        self.limits = limits or OciSandboxLimits()
        self.last_evidence: OciSandboxExecutionEvidence | None = None

    @property
    def policy_sha256(self) -> str:
        return canonical_hash(_policy(self.expected_runtime, self.limits))

    def _command(self, cidfile: Path) -> tuple[str, ...]:
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
                f"size={limits.max_temp_file_bytes},mode=0700,uid=65534,gid=65534"
            ),
            "--workdir=/tmp",
            "--env=LANG=C.UTF-8",
            f"--cidfile={cidfile}",
            "--entrypoint=python3",
            runtime.image_reference,
            "-I", "-S", "-c", _BOOTSTRAP,
        )

    def _evidence(
        self, *, status: str, failure_code: str | None, started: float,
        process: _BoundedProcessResult | None = None, oom_killed: bool = False,
        controls_enforced: bool = False,
    ) -> None:
        self.last_evidence = OciSandboxExecutionEvidence(
            CONTRACT_VERSION, status, failure_code,
            self.expected_runtime.environment_sha256, self.policy_sha256,
            self.implementation_sha256, _sha256_bytes(_BOOTSTRAP.encode("utf-8")),
            controls_enforced, controls_enforced, controls_enforced,
            controls_enforced, controls_enforced, controls_enforced,
            self.limits.to_record(), max(0, int((time.monotonic() - started) * 1_000)),
            0 if process is None else process.stdout_observed,
            0 if process is None else process.stderr_observed,
            None if process is None else process.exit_code,
            oom_killed,
        )

    def _rejected(
        self, request: ParseRequest, code: str, *, started: float,
        process: _BoundedProcessResult | None = None, oom_killed: bool = False,
        controls_enforced: bool = False,
    ) -> WorkerExecution:
        self._evidence(
            status="rejected", failure_code=code, started=started,
            process=process, oom_killed=oom_killed,
            controls_enforced=controls_enforced,
        )
        return WorkerExecution.capture(
            outcome=None,
            operation_id=f"operation.oci-sandbox.{request.request_id}",
            status="sandbox_rejected",
            failure_code=code,
            duration_ms=self.last_evidence.wall_milliseconds,
            worker_exit_code=None if process is None else process.exit_code,
            stdout=b"" if process is None else process.stdout,
            stderr=b"" if process is None else process.stderr,
        )

    def _container_state(self, container_id: str) -> dict[str, Any]:
        runtime = self.expected_runtime
        data = _control_command(
            (
                runtime.docker_executable, "container", "inspect", container_id,
                "--format", "{{json .State}}",
            ),
            executable=Path(runtime.docker_executable), daemon_host=runtime.daemon_host,
        )
        return _closed_json(data, "OCI container state")

    def _remove_container(self, container_id: str) -> bool:
        runtime = self.expected_runtime
        try:
            _control_command(
                (runtime.docker_executable, "container", "rm", "--force", container_id),
                executable=Path(runtime.docker_executable), daemon_host=runtime.daemon_host,
            )
            return True
        except ValueError:
            return False

    def execute(self, request: ParseRequest) -> WorkerExecution:
        started = time.monotonic()
        runtime = self.expected_runtime
        try:
            measured = OciRuntimeIdentity.measure(
                docker_executable=Path(runtime.docker_executable),
                daemon_host=runtime.daemon_host,
                image_reference=runtime.image_reference,
                platform=runtime.platform,
            )
        except (OSError, ValueError):
            return self._rejected(request, "sandbox_oci_runtime_unavailable", started=started)
        if measured != runtime:
            return self._rejected(request, "sandbox_oci_runtime_identity_mismatch", started=started)

        payload = json.dumps({
            "request_base64": base64.b64encode(_request_envelope(request)).decode("ascii"),
            "schema_version": "phase4b-oci-stdin-worker-v1",
            "worker_source": self.worker_source,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(payload) > _MAX_STDIN_ENVELOPE_BYTES:
            return self._rejected(request, "sandbox_oci_stdin_limit_exceeded", started=started)

        process_result: _BoundedProcessResult | None = None
        state: dict[str, Any] = {}
        cleanup_ok = False
        with tempfile.TemporaryDirectory(prefix="adaivy-p4b-oci-control-") as temporary:
            cidfile = Path(temporary) / "cid"
            try:
                process_result = _bounded_process(
                    self._command(cidfile), input_bytes=payload,
                    environment=_docker_environment(
                        Path(runtime.docker_executable), runtime.daemon_host,
                    ),
                    wall_seconds=self.limits.max_wall_seconds,
                    stdout_limit=self.limits.max_stdout_bytes,
                    stderr_limit=self.limits.max_stderr_bytes,
                )
            except (OSError, subprocess.SubprocessError, ValueError):
                return self._rejected(request, "sandbox_oci_launch_failed", started=started)
            container_id = ""
            try:
                if cidfile.is_file():
                    container_id = cidfile.read_text("ascii").strip()
                if re.fullmatch(r"[0-9a-f]{64}", container_id):
                    state = self._container_state(container_id)
            except (OSError, UnicodeError, ValueError):
                state = {}
            finally:
                if container_id:
                    cleanup_ok = self._remove_container(container_id)

        assert process_result is not None
        if (
            not state
            or not cleanup_ok
            or not isinstance(state.get("OOMKilled"), bool)
            or state.get("ExitCode") != process_result.exit_code
        ):
            return self._rejected(
                request, "sandbox_oci_control_state_unavailable", started=started,
                process=process_result,
            )
        oom_killed = state.get("OOMKilled") is True
        if process_result.timed_out:
            return self._rejected(
                request, "sandbox_wall_time_exceeded", started=started,
                process=process_result, oom_killed=oom_killed,
                controls_enforced=True,
            )
        if process_result.output_limit:
            return self._rejected(
                request, f"sandbox_{process_result.output_limit}_limit_exceeded",
                started=started, process=process_result, oom_killed=oom_killed,
                controls_enforced=True,
            )
        if oom_killed:
            return self._rejected(
                request, "sandbox_memory_limit_exceeded", started=started,
                process=process_result, oom_killed=True,
                controls_enforced=True,
            )
        if process_result.exit_code != 0:
            code = (
                "sandbox_cpu_limit_exceeded"
                if process_result.exit_code in {137, -signal.SIGKILL, 152, -signal.SIGXCPU}
                else "sandbox_worker_failed"
            )
            return self._rejected(
                request, code, started=started, process=process_result,
                controls_enforced=True,
            )

        worker_failure: str | None = None
        try:
            response = _closed_json(process_result.stdout, "OCI worker response")
            if response.get("status") == "completed":
                if set(response) != {"outcome", "schema_version", "status"}:
                    raise ValueError("OCI worker response fields differ")
                if response["schema_version"] != RESPONSE_SCHEMA:
                    raise ValueError("OCI worker response schema differs")
                outcome = _decode_outcome(response["outcome"])
            elif response.get("status") in {"failed", "rejected"}:
                if set(response) != {"failure_code", "schema_version", "status"}:
                    raise ValueError("OCI worker failure fields differ")
                worker_failure = response.get("failure_code")
                if (
                    response["schema_version"] != RESPONSE_SCHEMA
                    or not isinstance(worker_failure, str)
                    or not worker_failure
                    or len(worker_failure) > 128
                    or any(
                        character not in "abcdefghijklmnopqrstuvwxyz0123456789_.:-"
                        for character in worker_failure
                    )
                ):
                    raise ValueError("OCI worker failure response differs")
                outcome = None
            else:
                raise ValueError("OCI worker response status differs")
        except (TypeError, ValueError):
            return self._rejected(
                request, "sandbox_worker_response_invalid", started=started,
                process=process_result, controls_enforced=True,
            )

        content_rejected = response.get("status") == "rejected"
        self._evidence(
            status=(
                "completed" if worker_failure is None
                else "completed_content_rejection" if content_rejected
                else "completed_worker_failure"
            ),
            failure_code=worker_failure,
            started=started,
            process=process_result,
            controls_enforced=True,
        )
        return WorkerExecution.capture(
            outcome=outcome,
            operation_id=f"operation.oci-sandbox.{request.request_id}",
            status=(
                "completed" if worker_failure is None
                else "content_rejected" if content_rejected
                else "failed"
            ),
            failure_code=worker_failure,
            duration_ms=self.last_evidence.wall_milliseconds,
            worker_exit_code=process_result.exit_code,
            stdout=process_result.stdout,
            stderr=process_result.stderr,
        )


__all__ = [
    "CONTRACT_VERSION", "OciParserSandboxWorker", "OciRuntimeIdentity",
    "OciSandboxExecutionEvidence", "OciSandboxLimits", "POLICY_SCHEMA",
    "RUNTIME_SCHEMA",
]
