"""Fail-closed, parser-worker-connected Darwin resource sandbox.

This module supplies an integration boundary, not an activated parser.  A
caller's pinned worker source is executed through Darwin ``sandbox-exec`` with
no network, no filesystem writes, no process forks, a cleared environment,
parent-enforced output and wall bounds, and POSIX resource limits. Resident
memory is only a sampled tripwire: a short-lived spike can evade observation.
Platforms without that named boundary return a rejected
:class:`WorkerExecution`.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

from .parsing import (
    AdapterOutcome,
    ByteAnchor,
    MAX_WORKER_CAPTURE_BYTES,
    PARSER_BOUNDS,
    ParseRequest,
    ParsedReference,
    ParsedSegment,
    WorkerExecution,
)


CONTRACT_VERSION = "adaivy.phase4b-parser-resource-sandbox.v3"
RESPONSE_SCHEMA = "phase4b-parser-worker-response-v2"
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    max_wall_seconds: int = PARSER_BOUNDS.max_wall_seconds
    max_cpu_seconds: int = PARSER_BOUNDS.max_wall_seconds
    max_memory_bytes: int = PARSER_BOUNDS.max_memory_bytes
    max_open_files: int = PARSER_BOUNDS.max_open_files
    max_processes: int = 1
    max_stdout_bytes: int = MAX_WORKER_CAPTURE_BYTES
    max_stderr_bytes: int = MAX_WORKER_CAPTURE_BYTES
    max_temp_file_bytes: int = PARSER_BOUNDS.max_temp_bytes

    def __post_init__(self) -> None:
        ceilings = {
            "max_wall_seconds": PARSER_BOUNDS.max_wall_seconds,
            "max_cpu_seconds": PARSER_BOUNDS.max_wall_seconds,
            "max_memory_bytes": PARSER_BOUNDS.max_memory_bytes,
            "max_open_files": PARSER_BOUNDS.max_open_files,
            "max_processes": 1,
            "max_stdout_bytes": MAX_WORKER_CAPTURE_BYTES,
            "max_stderr_bytes": MAX_WORKER_CAPTURE_BYTES,
            "max_temp_file_bytes": PARSER_BOUNDS.max_temp_bytes,
        }
        for field, ceiling in ceilings.items():
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= ceiling:
                raise ValueError(f"{field} is outside the sealed parser ceiling")

    def to_record(self) -> dict[str, int]:
        return {
            field: getattr(self, field)
            for field in (
                "max_cpu_seconds", "max_memory_bytes", "max_open_files",
                "max_processes", "max_stderr_bytes", "max_stdout_bytes",
                "max_temp_file_bytes", "max_wall_seconds",
            )
        }


@dataclass(frozen=True, slots=True)
class SandboxExecutionEvidence:
    schema_version: str
    platform: str
    status: str
    failure_code: str | None
    limits: dict[str, int]
    limit_enforcement: dict[str, str]
    wall_milliseconds: int
    cpu_milliseconds: int
    sampled_peak_resident_bytes: int
    stdout_bytes_observed: int
    stderr_bytes_observed: int
    exit_code: int | None
    terminating_signal: int | None
    profile_sha256: str
    worker_source_sha256: str
    dependency_environment_sha256: str

    def to_record(self) -> dict[str, Any]:
        return {
            "cpu_milliseconds": self.cpu_milliseconds,
            "exit_code": self.exit_code,
            "failure_code": self.failure_code,
            "limits": self.limits,
            "limit_enforcement": self.limit_enforcement,
            "sampled_peak_resident_bytes": self.sampled_peak_resident_bytes,
            "platform": self.platform,
            "profile_sha256": self.profile_sha256,
            "schema_version": self.schema_version,
            "status": self.status,
            "stderr_bytes_observed": self.stderr_bytes_observed,
            "stdout_bytes_observed": self.stdout_bytes_observed,
            "terminating_signal": self.terminating_signal,
            "wall_milliseconds": self.wall_milliseconds,
            "worker_source_sha256": self.worker_source_sha256,
            "dependency_environment_sha256": self.dependency_environment_sha256,
        }


def measured_runtime_identity() -> str:
    """Hash the exact interpreter build and named-platform runtime identity."""
    executable = Path(sys.executable).resolve()
    digest = hashlib.sha256()
    with executable.open("rb") as source:
        while chunk := source.read(1_048_576):
            digest.update(chunk)
    record = {
        "executable_path": str(executable),
        "executable_sha256": "sha256:" + digest.hexdigest(),
        "implementation": sys.implementation.name,
        "implementation_cache_tag": sys.implementation.cache_tag,
        "machine": platform.machine(),
        "python_version": sys.version,
        "runtime_root": str(Path(sys.base_prefix).resolve()),
        "system": platform.system(),
        "system_release": platform.release(),
    }
    return _sha256(_canonical_bytes(record))


def _limit_enforcement() -> dict[str, str]:
    """Describe mechanisms without promoting observations to enforcement."""
    return {
        "max_cpu_seconds": "kernel_rlimit_cpu",
        "max_memory_bytes": "parent_sampled_rss_tripwire_not_strict",
        "max_open_files": "kernel_rlimit_nofile",
        "max_processes": "sandbox_process_fork_deny",
        "max_stderr_bytes": "parent_pipe_capture_hard_ceiling",
        "max_stdout_bytes": "parent_pipe_capture_hard_ceiling",
        "max_temp_file_bytes": "kernel_rlimit_fsize_defense_in_depth_path_writes_denied",
        "max_wall_seconds": "parent_monotonic_deadline_process_group_kill",
    }


def _profile(runtime_root: Path) -> str:
    readable = (
        runtime_root, Path("/usr/lib"), Path("/System/Library"),
        Path("/Library/Apple"), Path("/dev/null"), Path("/dev/urandom"),
    )
    clauses = ["(version 1)", "(deny default)"]
    for path in readable:
        operation = "subpath" if path.is_dir() else "literal"
        clauses.append(f'(allow file-read* ({operation} "{path}"))')
    clauses.extend((
        "(allow sysctl-read)",
        "(allow file-read-metadata)",
        '(allow file-read-data (literal "/"))',
        '(deny file-read-data (subpath "/Users"))',
        '(deny file-read-data (subpath "/private"))',
        '(deny file-read-data (subpath "/Volumes"))',
        '(deny file-read-data (subpath "/etc"))',
        f'(allow process-exec (subpath "{runtime_root}"))',
        "(deny process-fork)", "(deny network*)", "(allow file-write-data)",
        '(deny file-write* (subpath "/"))',
    ))
    return "".join(clauses)


def _set_resource_limits(limits: SandboxLimits) -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (limits.max_cpu_seconds, limits.max_cpu_seconds))
    resource.setrlimit(resource.RLIMIT_NOFILE, (limits.max_open_files, limits.max_open_files))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits.max_temp_file_bytes, limits.max_temp_file_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # Darwin exposes RLIMIT_AS/DATA constants but rejects useful finite values
    # for this interpreter. Resident memory is sampled from proc_pidinfo as a
    # parent-side tripwire; it is not strict transient-spike enforcement.


def _darwin_task_metrics(pid: int) -> tuple[int, int]:
    """Return per-PID resident bytes and CPU milliseconds from the kernel."""
    import ctypes

    class ProcTaskInfo(ctypes.Structure):
        _fields_ = [
            ("virtual_size", ctypes.c_uint64), ("resident_size", ctypes.c_uint64),
            ("total_user", ctypes.c_uint64), ("total_system", ctypes.c_uint64),
            ("threads_user", ctypes.c_uint64), ("threads_system", ctypes.c_uint64),
            *[(name, ctypes.c_int32) for name in (
                "policy", "faults", "pageins", "cow_faults", "messages_sent",
                "messages_received", "syscalls_mach", "syscalls_unix", "csw",
                "threadnum", "numrunning", "priority",
            )],
        ]

    library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    function = library.proc_pidinfo
    function.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    function.restype = ctypes.c_int
    info = ProcTaskInfo()
    size = function(pid, 4, 0, ctypes.byref(info), ctypes.sizeof(info))
    if size != ctypes.sizeof(info):
        raise OSError(ctypes.get_errno(), "proc_pidinfo failed")
    class MachTimebaseInfo(ctypes.Structure):
        _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]

    timebase = MachTimebaseInfo()
    system = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    if system.mach_timebase_info(ctypes.byref(timebase)) != 0 or timebase.denom == 0:
        raise OSError("mach_timebase_info failed")
    ticks = int(info.total_user + info.total_system)
    cpu_milliseconds = (ticks * int(timebase.numer)) // int(timebase.denom) // 1_000_000
    return int(info.resident_size), cpu_milliseconds


def _request_envelope(request: ParseRequest) -> bytes:
    return _canonical_bytes({
        "original_bytes_base64": base64.b64encode(request.original_bytes).decode("ascii"),
        "request": request.to_record(),
        "schema_version": "phase4b-parser-worker-request-v1",
    })


def _kill_worker(process: subprocess.Popen[bytes]) -> None:
    """Best-effort group kill with a direct-child fallback for Darwin races."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
        return
    except (ProcessLookupError, PermissionError):
        # sandbox-exec can exit between poll(2) and killpg(2), leaving either
        # ESRCH or EPERM while Popen has not yet observed the wait status.
        pass
    try:
        process.kill()
    except (ProcessLookupError, PermissionError):
        pass


def _has_privileged_identity() -> bool:
    """Reject root user/group identities and set-id process ancestry."""
    identity_functions = tuple(
        function for function in ("getuid", "geteuid", "getgid", "getegid")
        if hasattr(os, function)
    )
    if len(identity_functions) != 4:
        return True
    if any(getattr(os, function)() == 0 for function in identity_functions):
        return True
    if not hasattr(os, "getgroups") or 0 in os.getgroups():
        return True
    if platform.system() != "Darwin":
        return False
    import ctypes

    try:
        system = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    except OSError:
        return True
    system.issetugid.argtypes = []
    system.issetugid.restype = ctypes.c_int
    return system.issetugid() != 0


def _strict_mapping(value: object, keys: set[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"invalid {name} envelope")
    return value


def _decode_outcome(value: object) -> AdapterOutcome:
    record = _strict_mapping(
        value, {"references", "segments", "transformations", "warnings"}, "outcome",
    )
    if not all(isinstance(record[field], list) for field in record):
        raise ValueError("outcome collections must be lists")
    segments = []
    for item in record["segments"]:
        segment = _strict_mapping(
            item, {"anchor", "kind", "load_bearing", "normalized_text", "segment_id"},
            "segment",
        )
        anchor = _strict_mapping(
            segment["anchor"],
            {"end", "object_id", "original_sha256", "page_index", "slice_sha256", "start"},
            "anchor",
        )
        segments.append(ParsedSegment(
            segment_id=segment["segment_id"], kind=segment["kind"],
            normalized_text=segment["normalized_text"],
            anchor=ByteAnchor(**dict(anchor)), load_bearing=segment["load_bearing"],
        ))
    references = []
    for item in record["references"]:
        reference = _strict_mapping(item, {"anchor", "reference_id", "target"}, "reference")
        anchor = _strict_mapping(
            reference["anchor"],
            {"end", "object_id", "original_sha256", "page_index", "slice_sha256", "start"},
            "anchor",
        )
        references.append(ParsedReference(
            reference_id=reference["reference_id"], target=reference["target"],
            anchor=ByteAnchor(**dict(anchor)),
        ))
    return AdapterOutcome(
        tuple(segments), tuple(references), tuple(record["warnings"]),
        tuple(record["transformations"]),
    )


class DarwinResourceSandboxWorker:
    """Execute one pinned Python parser source as a concrete ParserWorker port."""

    sandbox_contract = "external-os-sandbox-contract-v1"

    def __init__(
        self, *, name: str, version: str, worker_source: str,
        expected_dependency_environment_sha256: str,
        limits: SandboxLimits | None = None,
    ) -> None:
        if not name or not version or not worker_source:
            raise ValueError("worker identity and source are required")
        measured_environment = measured_runtime_identity()
        if expected_dependency_environment_sha256 != measured_environment:
            raise ValueError("dependency environment differs from measured runtime identity")
        self.name = name
        self.version = version
        self.worker_source = worker_source
        self.implementation_sha256 = _sha256(worker_source.encode("utf-8"))
        self.dependency_environment_sha256 = measured_environment
        self.limits = limits or SandboxLimits()
        self.executable = Path(sys.executable).resolve()
        self.runtime_root = Path(sys.base_prefix).resolve()
        self.last_evidence: SandboxExecutionEvidence | None = None

    def _rejected(
        self, request: ParseRequest, failure_code: str, *, started: float,
        stdout: bytes = b"", stderr: bytes = b"", exit_code: int | None = None,
        cpu_ms: int = 0, peak_bytes: int = 0, profile_hash: str,
        stdout_observed: int | None = None, stderr_observed: int | None = None,
    ) -> WorkerExecution:
        duration = max(0, int((time.monotonic() - started) * 1_000))
        terminating_signal = -exit_code if exit_code is not None and exit_code < 0 else None
        self.last_evidence = SandboxExecutionEvidence(
            CONTRACT_VERSION, f"{platform.system()}-{platform.machine()}", "rejected",
            failure_code, self.limits.to_record(), _limit_enforcement(), duration, cpu_ms, peak_bytes,
            len(stdout) if stdout_observed is None else stdout_observed,
            len(stderr) if stderr_observed is None else stderr_observed,
            exit_code, terminating_signal, profile_hash,
            self.implementation_sha256, self.dependency_environment_sha256,
        )
        return WorkerExecution.capture(
            outcome=None, operation_id=f"operation.sandbox.{request.request_id}",
            status="sandbox_rejected", failure_code=failure_code,
            duration_ms=duration, worker_exit_code=exit_code,
            stdout=stdout[:self.limits.max_stdout_bytes],
            stderr=stderr[:self.limits.max_stderr_bytes],
        )

    def execute(self, request: ParseRequest) -> WorkerExecution:
        # ``selectors`` is classified as network-capable by the repository
        # invariant, so it is loaded only inside this explicitly supplied,
        # named-platform worker boundary. It multiplexes anonymous pipes only.
        import selectors

        started = time.monotonic()
        profile = _profile(self.runtime_root)
        profile_hash = _sha256(profile.encode("utf-8"))
        if _has_privileged_identity():
            return self._rejected(
                request, "sandbox_privileged_identity_rejected", started=started,
                profile_hash=profile_hash,
            )
        if platform.system() != "Darwin" or not SANDBOX_EXEC.is_file():
            return self._rejected(
                request, "sandbox_named_platform_unavailable", started=started,
                profile_hash=profile_hash,
            )
        command = (
            str(SANDBOX_EXEC), "-p", profile, str(self.executable),
            "-I", "-S", "-c", self.worker_source,
        )
        stdout = bytearray()
        stderr = bytearray()
        output_limit: str | None = None
        timed_out = False
        sampled_memory_limit = False
        peak_bytes = 0
        cpu_ms = 0
        exit_code: int | None = None
        process: subprocess.Popen[bytes] | None = None
        streams: selectors.BaseSelector | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="adaivy-p4b-sandbox-") as temporary:
                process = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=temporary, env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": str(self.executable.parent)},
                    start_new_session=True, preexec_fn=lambda: _set_resource_limits(self.limits),
                )
                assert process.stdin is not None and process.stdout is not None and process.stderr is not None
                request_bytes = _request_envelope(request)
                streams = selectors.DefaultSelector()
                for stream, event, label in (
                    (process.stdin, selectors.EVENT_WRITE, "stdin"),
                    (process.stdout, selectors.EVENT_READ, "stdout"),
                    (process.stderr, selectors.EVENT_READ, "stderr"),
                ):
                    os.set_blocking(stream.fileno(), False)
                    streams.register(stream, event, label)
                sent = 0
                deadline = started + self.limits.max_wall_seconds
                while streams.get_map():
                    try:
                        resident, process_cpu_ms = _darwin_task_metrics(process.pid)
                    except OSError:
                        # A process that has just exited may disappear between
                        # poll iterations; all other measurement loss fails
                        # closed below if it occurred while still running.
                        if process.poll() is None:
                            sampled_memory_limit = True
                            break
                    else:
                        peak_bytes = max(peak_bytes, resident)
                        cpu_ms = max(cpu_ms, process_cpu_ms)
                        if resident > self.limits.max_memory_bytes:
                            sampled_memory_limit = True
                            break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        break
                    for key, _mask in streams.select(min(remaining, 0.1)):
                        label = key.data
                        stream = key.fileobj
                        if label == "stdin":
                            try:
                                sent += os.write(stream.fileno(), request_bytes[sent:sent + 65_536])
                            except BrokenPipeError:
                                sent = len(request_bytes)
                            if sent == len(request_bytes):
                                streams.unregister(stream)
                                stream.close()
                        else:
                            chunk = os.read(stream.fileno(), 65_536)
                            if not chunk:
                                streams.unregister(stream)
                                stream.close()
                                continue
                            target = stdout if label == "stdout" else stderr
                            maximum = self.limits.max_stdout_bytes if label == "stdout" else self.limits.max_stderr_bytes
                            target.extend(chunk)
                            if len(target) > maximum:
                                output_limit = label
                                break
                    if timed_out or output_limit or sampled_memory_limit:
                        break
                    if process.poll() is not None and not streams.get_map():
                        break
                if timed_out or output_limit or sampled_memory_limit:
                    _kill_worker(process)
                try:
                    exit_code = process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    _kill_worker(process)
                    exit_code = process.wait(timeout=1)
                streams.close()
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            if streams is not None:
                streams.close()
            if process is not None and process.poll() is None:
                _kill_worker(process)
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
            return self._rejected(
                request, "sandbox_launch_failed", started=started,
                stderr=type(error).__name__.encode("ascii"), profile_hash=profile_hash,
            )
        bounded_stdout = bytes(stdout[:self.limits.max_stdout_bytes])
        bounded_stderr = bytes(stderr[:self.limits.max_stderr_bytes])
        if timed_out:
            return self._rejected(
                request, "sandbox_wall_time_exceeded", started=started,
                stdout=bounded_stdout, stderr=bounded_stderr, exit_code=exit_code,
                cpu_ms=cpu_ms, peak_bytes=peak_bytes, profile_hash=profile_hash,
                stdout_observed=len(stdout), stderr_observed=len(stderr),
            )
        if output_limit:
            return self._rejected(
                request, f"sandbox_{output_limit}_limit_exceeded", started=started,
                stdout=bounded_stdout, stderr=bounded_stderr, exit_code=exit_code,
                cpu_ms=cpu_ms, peak_bytes=peak_bytes, profile_hash=profile_hash,
                stdout_observed=len(stdout), stderr_observed=len(stderr),
            )
        if sampled_memory_limit:
            return self._rejected(
                request, "sandbox_sampled_memory_limit_exceeded", started=started,
                stdout=bounded_stdout, stderr=bounded_stderr, exit_code=exit_code,
                cpu_ms=cpu_ms, peak_bytes=peak_bytes, profile_hash=profile_hash,
                stdout_observed=len(stdout), stderr_observed=len(stderr),
            )
        if exit_code != 0:
            cpu_threshold = self.limits.max_cpu_seconds * 750
            cpu_signal = exit_code in {-signal.SIGXCPU, -signal.SIGKILL}
            code = (
                "sandbox_cpu_limit_exceeded"
                if cpu_signal and cpu_ms >= cpu_threshold
                else "sandbox_worker_failed"
            )
            return self._rejected(
                request, code, started=started, stdout=bounded_stdout,
                stderr=bounded_stderr, exit_code=exit_code, cpu_ms=cpu_ms,
                peak_bytes=peak_bytes, profile_hash=profile_hash,
                stdout_observed=len(stdout), stderr_observed=len(stderr),
            )
        worker_failure: str | None = None
        try:
            decoded_response = json.loads(bounded_stdout)
            if not isinstance(decoded_response, Mapping):
                raise ValueError("worker response is not a mapping")
            if decoded_response.get("status") == "completed":
                response = _strict_mapping(
                    decoded_response, {"outcome", "schema_version", "status"}, "response",
                )
                if response["schema_version"] != RESPONSE_SCHEMA:
                    raise ValueError("worker response schema is invalid")
                outcome = _decode_outcome(response["outcome"])
            elif decoded_response.get("status") in {"failed", "rejected"}:
                response = _strict_mapping(
                    decoded_response, {"failure_code", "schema_version", "status"}, "response",
                )
                worker_failure = response["failure_code"]
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
                    raise ValueError("worker failure response is invalid")
                outcome = None
            else:
                raise ValueError("worker response status is invalid")
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
            return self._rejected(
                request, "sandbox_worker_response_invalid", started=started,
                stdout=bounded_stdout, stderr=bounded_stderr, exit_code=exit_code,
                cpu_ms=cpu_ms, peak_bytes=peak_bytes, profile_hash=profile_hash,
                stdout_observed=len(stdout), stderr_observed=len(stderr),
            )
        duration = max(0, int((time.monotonic() - started) * 1_000))
        content_rejected = decoded_response.get("status") == "rejected"
        self.last_evidence = SandboxExecutionEvidence(
            CONTRACT_VERSION, f"{platform.system()}-{platform.machine()}",
            (
                "completed" if worker_failure is None
                else "completed_content_rejection" if content_rejected
                else "completed_worker_failure"
            ),
            worker_failure, self.limits.to_record(), _limit_enforcement(),
            duration, cpu_ms, peak_bytes, len(stdout), len(stderr),
            exit_code, None, profile_hash, self.implementation_sha256,
            self.dependency_environment_sha256,
        )
        return WorkerExecution.capture(
            outcome=outcome, operation_id=f"operation.sandbox.{request.request_id}",
            status=(
                "completed" if worker_failure is None
                else "content_rejected" if content_rejected
                else "failed"
            ),
            failure_code=worker_failure,
            duration_ms=duration, worker_exit_code=exit_code,
            stdout=bounded_stdout, stderr=bounded_stderr,
        )


__all__ = [
    "CONTRACT_VERSION", "DarwinResourceSandboxWorker", "RESPONSE_SCHEMA",
    "SandboxExecutionEvidence", "SandboxLimits", "measured_runtime_identity",
]
