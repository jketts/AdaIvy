"""Deterministic bounded Phase 4A export, import, replay, and hard timeout."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import EXPORT_PROFILE, EXPORT_SCHEMA_VERSION, HARD_TIMEOUT_SECONDS, MAX_EXPORT_BYTES, MAX_RECORDS, SCHEMA_VERSION
from .serialization import ZERO_HASH, operational_envelope_hash, semantic_envelope_hash
from .validation import POLICY_VERSIONS, Phase4ValidationError, verify_bytes
from .workspace import Phase4Workspace


class DeadlineExceeded(TimeoutError):
    pass


class OutputLimitExceeded(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MonotonicDeadline:
    deadline: float
    clock: Callable[[], float] = time.monotonic

    @classmethod
    def after(cls, seconds: float, *, clock: Callable[[], float] = time.monotonic) -> "MonotonicDeadline":
        if seconds < 0 or seconds > HARD_TIMEOUT_SECONDS:
            raise ValueError("deadline must be between zero and 600 seconds")
        return cls(clock() + seconds, clock)

    def check(self) -> None:
        if self.clock() >= self.deadline:
            raise DeadlineExceeded("Phase 4A cooperative deadline expired")


def build_envelope(
    records: Sequence[Mapping[str, Any]], *, exported_at: str,
    elapsed_milliseconds: int = 0, source_path_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if len(records) > MAX_RECORDS:
        raise Phase4ValidationError("Phase 4A record limit exceeded")
    value: dict[str, Any] = {
        "schema_version": EXPORT_SCHEMA_VERSION, "profile": EXPORT_PROFILE,
        "record_schema_version": SCHEMA_VERSION, "policy_versions": list(POLICY_VERSIONS),
        "records": [dict(record) for record in records], "content_hash": ZERO_HASH,
        "operational": {
            "exported_at": exported_at, "exporter_version": "phase4a-exporter-v1",
            "external_cost_usd": 0, "external_calls": [], "elapsed_milliseconds": elapsed_milliseconds,
            "source_path_hashes": dict(sorted((source_path_hashes or {}).items())),
        },
        "operational_hash": ZERO_HASH,
    }
    value["content_hash"] = semantic_envelope_hash(value)
    value["operational_hash"] = operational_envelope_hash(value)
    return value


def _iter_json(value: Mapping[str, Any]) -> Iterable[bytes]:
    encoder = json.JSONEncoder(allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    for token in encoder.iterencode(value):
        yield token.encode("utf-8")


def write_bounded_chunks(
    chunks: Iterable[bytes], handle: Any, *, max_bytes: int = MAX_EXPORT_BYTES,
    deadline: MonotonicDeadline | None = None,
) -> tuple[int, str]:
    written = 0
    digest = hashlib.sha256()
    for chunk in chunks:
        if deadline is not None:
            deadline.check()
        if not isinstance(chunk, bytes):
            raise TypeError("bounded writer accepts bytes chunks only")
        if written + len(chunk) > max_bytes:
            raise OutputLimitExceeded("Phase 4A output byte limit exceeded")
        handle.write(chunk)
        digest.update(chunk)
        written += len(chunk)
    return written, "sha256:" + digest.hexdigest()


def export_workspace(
    workspace: Phase4Workspace, path: Path, *, exported_at: str,
    elapsed_milliseconds: int = 0, deadline: MonotonicDeadline | None = None,
    max_bytes: int = MAX_EXPORT_BYTES,
) -> tuple[str, str, int]:
    if deadline is not None:
        deadline.check()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with workspace.verified_read_snapshot() as (records, source_path_hashes):
            envelope = build_envelope(
                records, exported_at=exported_at,
                elapsed_milliseconds=elapsed_milliseconds,
                source_path_hashes=source_path_hashes,
            )
            handle = os.fdopen(descriptor, "wb")
            descriptor = -1
            with handle:
                byte_length, _file_digest = write_bounded_chunks(
                    _iter_json(envelope), handle, max_bytes=max_bytes, deadline=deadline,
                )
                handle.flush()
                os.fsync(handle.fileno())
            snapshot = verify_bytes(temporary.read_bytes(), max_bytes=max_bytes)
            os.replace(temporary, path)
        return snapshot.content_hash, snapshot.operational_hash, byte_length
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink()
        raise


def import_replay(data: bytes) -> dict[str, Any]:
    return verify_bytes(data).value()


def import_into_workspace(data: bytes, workspace: Phase4Workspace) -> dict[str, Any]:
    return workspace.import_verified(data).value()


_GROUP_TEARDOWN_GRACE_SECONDS = 5.0
_GROUP_TEARDOWN_POLL_SECONDS = 0.01


def _process_group_is_gone(pgid: int) -> bool:
    """Report whether a process group has finished tearing down.

    Signal delivery and process-group teardown are asynchronous, so a group can
    still be reported as present for a moment after SIGKILL, and a group whose
    last member is mid-exit is reported EPERM rather than ESRCH on macOS. Only
    ESRCH proves the group is gone; anything else is treated as still present so
    the caller's survival check stays exact.
    """

    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _run_process_tree(
    command: Sequence[str], *, timeout: float, cwd: Path | None = None,
) -> subprocess.CompletedProcess[bytes]:
    if os.name != "posix":
        raise RuntimeError("Phase 4A process-tree timeout requires POSIX process groups")
    process = subprocess.Popen(
        list(command), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.output or b"", error.stderr or b""
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process.returncode is None:
            stdout, stderr = process.communicate()
        teardown_deadline = time.monotonic() + _GROUP_TEARDOWN_GRACE_SECONDS
        while not _process_group_is_gone(process.pid):
            if time.monotonic() >= teardown_deadline:
                raise RuntimeError("Phase 4A timed-out process group survived forced termination")
            time.sleep(_GROUP_TEARDOWN_POLL_SECONDS)
        raise subprocess.TimeoutExpired(
            error.cmd, error.timeout, output=stdout, stderr=stderr,
        ) from None
    return subprocess.CompletedProcess(list(command), process.returncode, stdout, stderr)


def run_with_hard_timeout(command: Sequence[str], *, timeout: int = HARD_TIMEOUT_SECONDS, cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    if timeout != HARD_TIMEOUT_SECONDS:
        raise ValueError("Phase 4A parent hard timeout is fixed at 600 seconds")
    return _run_process_tree(command, timeout=timeout, cwd=cwd)
