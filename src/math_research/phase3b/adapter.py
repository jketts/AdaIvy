"""Fixed-control Docker adapter for the sealed v5 Lean runtime."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import replace
from collections.abc import Callable
from typing import BinaryIO

from . import APPROVED_STANDARD_AXIOMS, MAX_STDIN_BYTES, RUNTIME_DIGEST, RUNTIME_IMAGE, RUNTIME_REFERENCE
from .records import (
    ExecutionLimits, FormalCheckFinding, FormalCheckOutcome, FormalCheckRequest,
    GeneratedWrapper, RawExecution, StreamCapture,
)
from .serialization import canonical_hash, public_value, sha256_bytes, stable_id
from .validation import parse_request
from .wrapper import DOCKER_CREATE_OPTIONS, DOCKER_START_OPTIONS, INVOCATION, POLICY

_NO_AXIOMS = re.compile(r"does not depend on any axioms")
_AXIOMS = re.compile(r"depends on axioms: \[([^]]*)\]")


class _Accumulator:
    def __init__(self, retained_limit: int) -> None:
        self.retained_limit = retained_limit
        self.length = 0
        self.digest = hashlib.sha256()
        self.retained = bytearray()
        self.lock = threading.Lock()

    def add(self, data: bytes) -> None:
        with self.lock:
            self.length += len(data)
            self.digest.update(data)
            room = max(0, self.retained_limit - len(self.retained))
            self.retained.extend(data[:room])

    def result(self) -> StreamCapture:
        with self.lock:
            retained = bytes(self.retained)
            return StreamCapture(
                self.length, "sha256:" + self.digest.hexdigest(), retained.decode("utf-8", "replace"),
                len(retained), self.length > len(retained),
            )


def _read_stream(stream: BinaryIO, accumulator: _Accumulator, output_event: threading.Event, total: Callable[[], int], limit: int) -> None:
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            accumulator.add(chunk)
            if total() > limit:
                output_event.set()
    finally:
        stream.close()


class DockerLeanAdapter:
    """One sealed runtime adapter. No request value becomes a Docker argument."""

    def __init__(self, limits: ExecutionLimits | None = None, *, expected_digest: str = RUNTIME_DIGEST) -> None:
        self.limits = limits or ExecutionLimits()
        self.expected_digest = expected_digest
        self._validate_limits()

    def _validate_limits(self) -> None:
        values = self.limits
        if not (1 <= values.wall_milliseconds <= 120_000):
            raise ValueError("wall_milliseconds outside production bound")
        if not (1 <= values.combined_output_bytes <= 1_048_576):
            raise ValueError("combined_output_bytes outside production bound")
        if not (0 <= values.retained_stdout_bytes <= 65_536 and 0 <= values.retained_stderr_bytes <= 65_536):
            raise ValueError("retained output bound invalid")

    def validate(self, request: FormalCheckRequest) -> None:
        if parse_request(public_value(request)) != request:
            raise ValueError("request failed canonical policy validation")

    def _inspect_runtime(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", RUNTIME_IMAGE], check=False, capture_output=True, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"runtime inspection failed: {type(error).__name__}"
        if result.returncode != 0:
            return False, "runtime image absent or inaccessible: " + result.stderr[:1024].decode("utf-8", "replace")
        try:
            values = json.loads(result.stdout)
            item = values[0]
            config = item["Config"]
            valid = (
                item["Id"] == self.expected_digest
                and config.get("User") == "65532:65532"
                and config.get("Entrypoint") == ["/checker/launcher"]
                and config.get("WorkingDir") == "/trusted"
            )
        except (ValueError, KeyError, IndexError, TypeError):
            return False, "runtime inspection returned malformed metadata"
        return (True, "") if valid else (False, "runtime image seal mismatch")

    @staticmethod
    def _empty_capture() -> StreamCapture:
        return StreamCapture(0, "sha256:" + hashlib.sha256(b"").hexdigest(), "", 0, False)

    def _failure(self, started: float, diagnostic: str, *, container_removed: bool = True) -> RawExecution:
        return RawExecution(None, "sandbox_failure", int((time.monotonic() - started) * 1000), self._empty_capture(), self._empty_capture(), container_removed, (diagnostic[:2048],))

    @staticmethod
    def _remove_container(name: str) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["docker", "rm", "--force", name], check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, f"container removal failed: {type(error).__name__}"
        stderr = result.stderr[:1024].decode("utf-8", "replace")
        if result.returncode == 0 or "No such container" in stderr:
            return True, ""
        return False, "container removal failed: " + stderr

    def execute(self, wrapper: GeneratedWrapper) -> RawExecution:
        started = time.monotonic()
        manifest = wrapper.manifest
        if (
            len(wrapper.source) != manifest.wrapper_byte_length
            or len(wrapper.source) > MAX_STDIN_BYTES
            or sha256_bytes(wrapper.source) != manifest.wrapper_hash
            or manifest.invocation_hash != canonical_hash(INVOCATION)
            or manifest.policy_hash != canonical_hash(POLICY)
            or manifest.runtime_hash != self.expected_digest
        ):
            return self._failure(started, "generated wrapper integrity check failed")
        sealed, diagnostic = self._inspect_runtime()
        if not sealed:
            return self._failure(started, diagnostic)
        name = "adaivy-phase3b-" + uuid.uuid4().hex
        create = ["docker", "create", "--name", name, *DOCKER_CREATE_OPTIONS, RUNTIME_REFERENCE]
        try:
            made = subprocess.run(create, check=False, capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as error:
            removed, cleanup = self._remove_container(name)
            diagnostic = f"container creation failed: {type(error).__name__}"
            return self._failure(started, diagnostic if removed else diagnostic + "; " + cleanup, container_removed=removed)
        if made.returncode != 0:
            removed, cleanup = self._remove_container(name)
            diagnostic = "container creation failed: " + made.stderr[:1024].decode("utf-8", "replace")
            return self._failure(started, diagnostic if removed else diagnostic + "; " + cleanup, container_removed=removed)

        stdout = _Accumulator(self.limits.retained_stdout_bytes)
        stderr = _Accumulator(self.limits.retained_stderr_bytes)
        exceeded = threading.Event()
        removed = False
        reason = "completed"
        diagnostics: list[str] = []
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                ["docker", *DOCKER_START_OPTIONS, name],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            )
            assert process.stdin is not None and process.stdout is not None and process.stderr is not None
            process.stdin.write(wrapper.source)
            process.stdin.close()
            total = lambda: stdout.length + stderr.length
            readers = (
                threading.Thread(target=_read_stream, args=(process.stdout, stdout, exceeded, total, self.limits.combined_output_bytes), daemon=True),
                threading.Thread(target=_read_stream, args=(process.stderr, stderr, exceeded, total, self.limits.combined_output_bytes), daemon=True),
            )
            for reader in readers:
                reader.start()
            deadline = started + self.limits.wall_milliseconds / 1000
            while process.poll() is None:
                if exceeded.is_set():
                    reason = "output_limit"
                    break
                if time.monotonic() >= deadline:
                    reason = "timeout"
                    break
                time.sleep(0.005)
            if reason != "completed":
                removed, cleanup = self._remove_container(name)
                if not removed:
                    diagnostics.append(cleanup)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
            for reader in readers:
                reader.join(timeout=5)
            if reason == "completed" and exceeded.is_set():
                # A very small limit can be crossed in the final read after the
                # checker exits; the stream is still bounded and must not be
                # reported as a successful kernel result.
                reason = "output_limit"
            exit_code = process.returncode
        except (OSError, BrokenPipeError, subprocess.TimeoutExpired) as error:
            reason = "sandbox_failure"
            exit_code = process.returncode if process is not None else None
            diagnostics.append(f"adapter execution failed: {type(error).__name__}")
        finally:
            if not removed:
                removed, cleanup = self._remove_container(name)
                if not removed:
                    diagnostics.append(cleanup)
            if not removed:
                reason = "sandbox_failure"
        return RawExecution(exit_code, reason, int((time.monotonic() - started) * 1000), stdout.result(), stderr.result(), removed, tuple(diagnostics))

    def verify_output(self, request: FormalCheckRequest, wrapper: GeneratedWrapper, execution: RawExecution, *, created_at: str) -> FormalCheckFinding:
        outcome, approved, unapproved = classify_execution(request, wrapper, execution)
        provisional = FormalCheckFinding(
            id=stable_id("formal-finding", {"request": wrapper.manifest.source_hash, "wrapper": wrapper.manifest.wrapper_hash, "execution": execution}),
            request_id=request.request_id, claim_id=request.claim_id, semantic_alignment_id=request.semantic_alignment_id,
            source_kind=request.source_kind, outcome=outcome, disposition="proposal", trust_effect="none",
            exact_statement_only=True, approved_axioms=approved, unapproved_assumptions=unapproved,
            policy_rejections=(), wrapper_manifest=wrapper.manifest, execution=execution,
            meaning_tests_diagnostic_only=True, semantic_alignment_approved=False, source_applicability_approved=False,
            novelty_approved=False, significance_approved=False, contribution_approved=False,
            epistemic_warrant_created=False, created_at=created_at, content_hash="",
        )
        return replace(provisional, content_hash=canonical_hash(provisional))


def _messages(execution: RawExecution) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    for line in execution.stdout.retained_utf8.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            result.append(item)
    return tuple(result)


def classify_execution(request: FormalCheckRequest, wrapper: GeneratedWrapper, execution: RawExecution) -> tuple[FormalCheckOutcome, tuple[str, ...], tuple[str, ...]]:
    if not execution.container_removed:
        return FormalCheckOutcome.SANDBOX_FAILURE, (), ()
    if execution.termination_reason == "timeout":
        return FormalCheckOutcome.TIMEOUT, (), ()
    if execution.termination_reason == "output_limit":
        return FormalCheckOutcome.OUTPUT_LIMIT, (), ()
    if execution.termination_reason == "sandbox_failure":
        return FormalCheckOutcome.SANDBOX_FAILURE, (), ()
    messages = _messages(execution)
    if any(item.get("severity") == "warning" for item in messages):
        return FormalCheckOutcome.SANDBOX_FAILURE, (), ()
    if execution.exit_code != 0:
        meaning_start = wrapper.manifest.meaning_test_start_line
        error_lines = [
            int(item.get("pos", {}).get("line", 0))
            for item in messages if item.get("severity") == "error" and isinstance(item.get("pos"), dict)
        ]
        if meaning_start is not None and error_lines and all(line >= meaning_start for line in error_lines):
            return FormalCheckOutcome.MEANING_TEST_FAILURE, (), ()
        return FormalCheckOutcome.ELABORATION_FAILURE, (), ()
    data = "\n".join(str(item.get("data", "")) for item in messages if item.get("severity") == "information")
    if _NO_AXIOMS.search(data):
        return FormalCheckOutcome.KERNEL_CHECKED, (), ()
    match = _AXIOMS.search(data)
    if match is None:
        return FormalCheckOutcome.SANDBOX_FAILURE, (), ()
    axioms = tuple(sorted(item.strip() for item in match.group(1).split(",") if item.strip()))
    approved_set = set(APPROVED_STANDARD_AXIOMS)
    approved = tuple(item for item in axioms if item in approved_set)
    unapproved = tuple(item for item in axioms if item not in approved_set)
    if unapproved:
        return FormalCheckOutcome.KERNEL_CHECKED_UNAPPROVED_ASSUMPTIONS, approved, unapproved
    return FormalCheckOutcome.KERNEL_CHECKED_APPROVED_AXIOMS, approved, ()
