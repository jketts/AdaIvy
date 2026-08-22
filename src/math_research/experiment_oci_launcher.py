"""The one boundary that may touch a container engine (ADR-0066).

This module exists so `src/math_research/campaign/` stays structurally free of
any process, socket, or engine code -- an invariant the campaign provenance
suite asserts textually, and which makes ADR-0057's "the ordinary offline suite
uses a scripted runner and opens no subprocess or socket" a property of the
package rather than of a test's mocking.

It implements the `ExperimentLauncher` port declared in
`math_research.campaign.experiment_sandbox`.  It is MECHANISM only:

* it decides nothing about which image, path, environment variable, network
  target, or resource limit is admissible -- the sandbox builds the complete
  argv and the bounds, and this module runs exactly what it is given;
* it inherits no ambient credential: the engine-client environment is the
  closed four-entry mapping below, so `DOCKER_*` tokens, cloud credentials, and
  provider keys present in the parent environment are not passed through;
* it captures, truncates, and bounds stdout/stderr, and kills the client on the
  wall deadline or an output overrun.

Importing this module launches nothing.  `selectors` is network-capable in the
repository's structural scan, so it loads lazily inside the execution call and
is used only with the anonymous pipes created there.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .campaign.experiment_sandbox import (
    MAX_CONTROL_OUTPUT_BYTES,
    ExperimentRefusal,
    ExperimentSandboxRefusal,
    LaunchOutcome,
)


LAUNCHER_ID = "oci_experiment_launcher.v1"
_CONTROL_TIMEOUT_SECONDS = 10
_CHUNK_BYTES = 65_536


def _refuse(
    reason: ExperimentRefusal, *, field: str | None = None, detail: str | None = None,
) -> ExperimentSandboxRefusal:
    return ExperimentSandboxRefusal(reason, field=field, detail=detail)


class OciExperimentLauncher:
    """Bounded OCI client launcher for the campaign experiment sandbox.

    Constructing one measures nothing and authorizes nothing.  The sandbox
    still requires a pinned digest, an owner activation record, and a matching
    measured runtime identity before it will call `execute`.
    """

    launcher_id = LAUNCHER_ID

    def __init__(self, *, docker_executable: Path, daemon_host: str) -> None:
        executable = Path(docker_executable)
        if not executable.is_absolute():
            raise _refuse(
                ExperimentRefusal.RUNTIME_UNAVAILABLE, field="docker_executable",
                detail="the engine client must be an absolute path",
            )
        if not daemon_host.startswith("unix:///") or ".." in daemon_host:
            raise _refuse(
                ExperimentRefusal.RUNTIME_IDENTITY_MISMATCH, field="daemon_host",
                detail="the engine daemon must be an absolute Unix socket",
            )
        try:
            resolved = executable.resolve(strict=True)
        except OSError as error:
            raise _refuse(
                ExperimentRefusal.RUNTIME_UNAVAILABLE, field="docker_executable",
            ) from error
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise _refuse(
                ExperimentRefusal.RUNTIME_UNAVAILABLE, field="docker_executable",
            )
        self.docker_executable = str(resolved)
        self.daemon_host = daemon_host

    def client_environment(self) -> dict[str, str]:
        """The complete engine-client environment. Nothing else is inherited."""

        return {
            "DOCKER_HOST": self.daemon_host,
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": str(Path(self.docker_executable).parent),
        }

    def control(self, command: tuple[str, ...]) -> bytes:
        """Run one short, bounded, non-launching engine control command."""

        if not command or command[0] != self.docker_executable:
            raise _refuse(
                ExperimentRefusal.RUNTIME_UNAVAILABLE, field="control_command",
                detail="a control command must invoke the reviewed engine client",
            )
        try:
            completed = subprocess.run(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=self.client_environment(), check=False,
                timeout=_CONTROL_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise _refuse(
                ExperimentRefusal.RUNTIME_UNAVAILABLE, detail="control",
            ) from error
        if completed.returncode != 0:
            raise _refuse(
                ExperimentRefusal.RUNTIME_UNAVAILABLE, detail="control_failed",
            )
        if len(completed.stdout) > MAX_CONTROL_OUTPUT_BYTES:
            raise _refuse(
                ExperimentRefusal.RUNTIME_UNAVAILABLE, detail="control_output_bound",
            )
        return completed.stdout

    def execute(
        self, command: tuple[str, ...], *, input_bytes: bytes, wall_seconds: float,
        stdout_limit: int, stderr_limit: int,
    ) -> LaunchOutcome:
        """Run one bounded container with captured, truncated streams."""

        # `selectors` is network-capable in the repository's structural scan, so
        # it loads only inside this explicit execution boundary and is used
        # solely with the anonymous stdin/stdout/stderr pipes below.
        import selectors

        if not command or command[0] != self.docker_executable:
            raise _refuse(
                ExperimentRefusal.LAUNCH_FAILED, field="command",
                detail="a launch must invoke the reviewed engine client",
            )
        if wall_seconds <= 0 or stdout_limit < 1 or stderr_limit < 1:
            raise _refuse(
                ExperimentRefusal.LAUNCH_FAILED, field="bounds",
                detail="a launch requires a positive wall deadline and output bound",
            )
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=self.client_environment(),
                start_new_session=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise _refuse(
                ExperimentRefusal.LAUNCH_FAILED, detail=type(error).__name__,
            ) from error
        assert process.stdin is not None
        assert process.stdout is not None and process.stderr is not None
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
                            sent += os.write(
                                stream.fileno(), input_bytes[sent:sent + _CHUNK_BYTES],
                            )
                        except BrokenPipeError:
                            sent = len(input_bytes)
                        if sent == len(input_bytes):
                            streams.unregister(stream)
                            stream.close()
                        continue
                    chunk = os.read(stream.fileno(), _CHUNK_BYTES)
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
                _kill(process)
            try:
                exit_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                _kill(process)
                exit_code = process.wait(timeout=2)
        finally:
            streams.close()
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
        return LaunchOutcome(
            stdout=bytes(stdout[:stdout_limit]), stderr=bytes(stderr[:stderr_limit]),
            stdout_observed=len(stdout), stderr_observed=len(stderr),
            exit_code=exit_code, timed_out=timed_out, output_limit=output_limit,
        )


def _kill(process: subprocess.Popen) -> None:
    try:
        process.kill()
    except OSError:
        return


__all__ = ["LAUNCHER_ID", "OciExperimentLauncher"]
