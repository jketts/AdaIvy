"""Bounded subprocess execution with evidence-preserving failures."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Sequence


def find_executable(name: str) -> str | None:
    return shutil.which(name)


def minimal_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    allowed = ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "WINDIR")
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        environment.update(extra)
    return environment


def run_bounded(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int = 30,
    environment: dict[str, str] | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            env=minimal_environment(environment),
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "command": list(command),
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "timed_out": False,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
    except subprocess.TimeoutExpired as error:
        return {
            "command": list(command),
            "exit_code": None,
            "stdout": error.stdout or "",
            "stderr": error.stderr or "",
            "timed_out": True,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
