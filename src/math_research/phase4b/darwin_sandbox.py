"""Named-platform OS sandbox evidence for a future Phase 4B parser worker.

This runner is intentionally not portable and is not a parser activation.  On
Darwin it launches only the repository-owned adversarial probe through the
system ``sandbox-exec`` boundary, with a deny-by-default profile, a cleared
environment, no writable filesystem paths, no network, and no process forks.
Other platforms fail closed with a machine-readable unavailable result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
CONTRACT_VERSION = "adaivy.phase4b-darwin-sandbox-contract.v1"
MAX_CAPTURE_BYTES = 65_536
TIMEOUT_SECONDS = 5


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


@dataclass(frozen=True, slots=True)
class SandboxProbeResult:
    schema_version: str
    platform: str
    action: str
    status: str
    exit_status: int | None
    stdout_hash: str
    stderr_hash: str
    stdout_bytes: int
    stderr_bytes: int
    profile_hash: str
    detail: dict[str, Any]

    def value(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "platform": self.platform,
            "action": self.action,
            "status": self.status,
            "exit_status": self.exit_status,
            "stdout_hash": self.stdout_hash,
            "stderr_hash": self.stderr_hash,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "profile_hash": self.profile_hash,
            "detail": self.detail,
        }


class DarwinSandboxProbeRunner:
    """Exercise actual Darwin sandbox denials without activating a parser."""

    def __init__(self) -> None:
        self.worker = Path(__file__).with_name("_sandbox_probe.py").resolve()
        self.worker_source = self.worker.read_text("utf-8")
        self.executable = Path(sys.executable).resolve()
        self.runtime_root = Path(sys.base_prefix).resolve()

    def _profile(self) -> str:
        # The runtime and immutable system libraries are readable so the fixed
        # Python probe can start. No source/workspace/home path is admitted.
        readable = (
            self.runtime_root,
            Path("/usr/lib"),
            Path("/System/Library"),
            Path("/Library/Apple"),
            Path("/dev/null"),
            Path("/dev/urandom"),
        )
        clauses = ["(version 1)", "(deny default)"]
        for path in readable:
            operation = "subpath" if path.is_dir() else "literal"
            clauses.append(f'(allow file-read* ({operation} "{path}"))')
        # sandbox-exec applies the profile before the fixed interpreter's real
        # app binary is reached. Fork remains denied, so the worker cannot use
        # this allowance to create another process.
        clauses.extend((
            "(allow sysctl-read)", "(allow mach-lookup)", "(allow process-info*)",
            # dyld/Python resolve every ancestor of the immutable runtime.
            # Metadata visibility is not content access.
            "(allow file-read-metadata)",
        ))
        # User, temporary, mounted-volume and configuration content is outside
        # the fixed worker's readable set. The bounded request travels in argv,
        # not through a filesystem object.
        clauses.extend((
            "(allow file-read-data)",
            '(deny file-read-data (subpath "/Users"))',
            '(deny file-read-data (subpath "/private"))',
            '(deny file-read-data (subpath "/Volumes"))',
            '(deny file-read-data (subpath "/etc"))',
        ))
        clauses.append(f'(allow process-exec (subpath "{self.runtime_root}"))')
        # Captured stdout/stderr are inherited anonymous pipes. Permit writing
        # their data while still denying every path-backed filesystem write.
        clauses.extend((
            "(deny process-fork)", "(deny network*)", "(allow file-write-data)",
            '(deny file-write* (subpath "/"))',
        ))
        return "".join(clauses)

    def run(self, action: str, *, target: Path | None = None) -> SandboxProbeResult:
        if action not in {"baseline", "network", "write", "read", "process"}:
            raise ValueError("sandbox probe action is not closed")
        profile = self._profile()
        platform_id = f"{platform.system()}-{platform.machine()}"
        if platform.system() != "Darwin" or not SANDBOX_EXEC.is_file():
            return SandboxProbeResult(
                CONTRACT_VERSION, platform_id, action, "unavailable", None,
                _hash(b""), _hash(b""), 0, 0, _hash(profile.encode("utf-8")),
                {"reason": "named Darwin sandbox-exec boundary unavailable"},
            )
        request = _canonical_bytes({
            "action": action,
            "target": str(target.resolve()) if target is not None else None,
        })
        command = (
            str(SANDBOX_EXEC), "-p", profile, str(self.executable),
            "-I", "-S", "-c", self.worker_source, request.decode("utf-8"),
        )
        environment = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": str(self.executable.parent)}
        try:
            completed = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=environment, cwd="/", timeout=TIMEOUT_SECONDS, check=False,
            )
            stdout = completed.stdout[:MAX_CAPTURE_BYTES]
            stderr = completed.stderr[:MAX_CAPTURE_BYTES]
            detail: dict[str, Any]
            status = "failed"
            try:
                decoded = json.loads(stdout)
                if not isinstance(decoded, dict):
                    raise ValueError
                detail = decoded
                if completed.returncode == 0:
                    status = "allowed" if decoded.get("allowed") is True else "denied"
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                detail = {"reason": "probe output was not a valid bounded envelope"}
            return SandboxProbeResult(
                CONTRACT_VERSION, platform_id, action, status, completed.returncode,
                _hash(stdout), _hash(stderr), len(stdout), len(stderr),
                _hash(profile.encode("utf-8")), detail,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return SandboxProbeResult(
                CONTRACT_VERSION, platform_id, action, "failed", None,
                _hash(b""), _hash(type(error).__name__.encode("utf-8")), 0, 0,
                _hash(profile.encode("utf-8")), {"reason": type(error).__name__},
            )


__all__ = [
    "CONTRACT_VERSION", "DarwinSandboxProbeRunner", "SandboxProbeResult",
]
