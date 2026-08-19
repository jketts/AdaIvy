"""Minimal secret-only `.env` loader for the Phase 2 live gate.

This intentionally implements no interpolation, command substitution, or
general configuration loading. Provider, model, pricing, and budgets remain in
their versioned non-secret JSON objects.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import MutableMapping


ENV_FILE_NAME = ".env"
ALLOWED_KEYS = frozenset({"OPENAI_API_KEY"})


class EnvFileError(ValueError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class EnvFileLoadResult:
    schema_version: str = "2.0.0"
    path: str
    file_present: bool
    credential_present: bool
    source: str


def repository_env_path() -> Path:
    return Path(__file__).resolve().parents[3] / ENV_FILE_NAME


def load_repository_env(
    path: Path | None = None,
    *,
    environment: MutableMapping[str, str] | None = None,
) -> EnvFileLoadResult:
    target = (path or repository_env_path()).resolve()
    values = os.environ if environment is None else environment
    if values.get("OPENAI_API_KEY"):
        return EnvFileLoadResult(
            path=str(target), file_present=target.is_file(),
            credential_present=True, source="process_environment",
        )
    if not target.exists():
        return EnvFileLoadResult(
            path=str(target), file_present=False,
            credential_present=False, source="missing",
        )
    if not target.is_file() or target.is_symlink():
        raise EnvFileError(".env must be a regular, non-symlink file")
    mode = stat.S_IMODE(target.stat().st_mode)
    if mode & 0o077:
        raise EnvFileError(".env permissions must be 0600")
    parsed: dict[str, str] = {}
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise EnvFileError(".env must be readable UTF-8 text") from error
    for line_number, original in enumerate(lines, start=1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise EnvFileError(f"invalid .env assignment on line {line_number}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_KEYS:
            raise EnvFileError(f"unsupported .env key on line {line_number}: {key}")
        if key in parsed:
            raise EnvFileError(f"duplicate .env key on line {line_number}: {key}")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif value.startswith(("'", '"')) or value.endswith(("'", '"')):
            raise EnvFileError(f"unmatched .env quote on line {line_number}")
        if not value:
            raise EnvFileError(f"empty .env value on line {line_number}: {key}")
        parsed[key] = value
    api_key = parsed.get("OPENAI_API_KEY")
    if not api_key:
        return EnvFileLoadResult(
            path=str(target), file_present=True,
            credential_present=False, source="env_file",
        )
    values["OPENAI_API_KEY"] = api_key
    return EnvFileLoadResult(
        path=str(target), file_present=True,
        credential_present=True, source="env_file",
    )
