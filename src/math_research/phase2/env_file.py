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

# Multi-provider credential keys, consumed by `load_provider_credentials`.
# ADR-0009 deliberately restricted `load_repository_env` to a single key; that
# function keeps its exact accepted semantics (including returning before the
# file is parsed when the process environment already supplies the credential)
# and is unchanged. Provider selection, model identity, pricing, and budgets
# stay in content-hashed non-secret JSON -- only credentials may appear here.
PROVIDER_ENV_KEYS = frozenset({
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_REGION",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_ENDPOINT",
    "DASHSCOPE_API_KEY",
    "DEEPSEEK_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_GROUP_ID",
    "OPENAI_API_KEY",
})
# Non-secret operational settings that may sit in `.env` for convenience.
# Excluded from redaction-sensitive reporting only in the sense that they are
# not credentials; they are still never echoed by the loader result.
NON_SECRET_PROVIDER_KEYS = frozenset({
    "AWS_REGION",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_ENDPOINT",
    "MINIMAX_GROUP_ID",
})


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


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderCredentialLoadResult:
    """Which provider keys resolved, and from where. Carries no secret value."""

    schema_version: str = "2.1.0"
    path: str
    file_present: bool
    from_process_environment: tuple[str, ...]
    from_env_file: tuple[str, ...]
    blank_in_env_file: tuple[str, ...]


def _parse_provider_env_file(target: Path) -> dict[str, str]:
    """Parse an already-validated `.env`, applying ADR-0009's strict rules.

    Unlike the single-key loader, a blank value is treated as "not configured"
    rather than an error: a multi-provider template is copied whole and most
    entries stay empty. Unknown keys, duplicates, and unmatched quotes remain
    hard errors, and no interpolation or substitution is performed.
    """
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
        if key not in PROVIDER_ENV_KEYS:
            raise EnvFileError(f"unsupported .env key on line {line_number}: {key}")
        if key in parsed:
            raise EnvFileError(f"duplicate .env key on line {line_number}: {key}")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif value.startswith(("'", '"')) or value.endswith(("'", '"')):
            raise EnvFileError(f"unmatched .env quote on line {line_number}")
        parsed[key] = value
    return parsed


def load_provider_credentials(
    path: Path | None = None,
    *,
    environment: MutableMapping[str, str] | None = None,
) -> ProviderCredentialLoadResult:
    """Resolve every supported provider key without disclosing any value.

    A key already present in the process environment always wins and is never
    overridden. Blank file entries are reported, not applied, so an unconfigured
    provider stays unconfigured instead of masking a real environment value.
    """
    target = (path or repository_env_path()).resolve()
    values = os.environ if environment is None else environment
    present = tuple(sorted(key for key in PROVIDER_ENV_KEYS if values.get(key)))
    if not target.exists():
        return ProviderCredentialLoadResult(
            path=str(target), file_present=False,
            from_process_environment=present, from_env_file=(), blank_in_env_file=(),
        )
    if not target.is_file() or target.is_symlink():
        raise EnvFileError(".env must be a regular, non-symlink file")
    mode = stat.S_IMODE(target.stat().st_mode)
    if mode & 0o077:
        raise EnvFileError(".env permissions must be 0600")
    parsed = _parse_provider_env_file(target)
    applied: list[str] = []
    blank: list[str] = []
    for key, value in parsed.items():
        if not value:
            blank.append(key)
            continue
        if values.get(key):
            continue
        values[key] = value
        applied.append(key)
    return ProviderCredentialLoadResult(
        path=str(target), file_present=True,
        from_process_environment=present,
        from_env_file=tuple(sorted(applied)),
        blank_in_env_file=tuple(sorted(blank)),
    )
