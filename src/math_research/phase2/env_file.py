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
SETTINGS_FILE_NAME = ".env.settings"
ALLOWED_KEYS = frozenset({"OPENAI_API_KEY"})

# Two files, one purpose each, and the split is enforced rather than advisory.
#
# `.env` holds secrets and nothing else, so there is exactly one file to keep
# out of git, off a backup, and out of a screen share. ADR-0009 deliberately
# restricted `load_repository_env` to a single key; that function keeps its
# exact accepted semantics (including returning before the file is parsed when
# the process environment already supplies the credential) and is unchanged.
PROVIDER_SECRET_KEYS = frozenset({
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AZURE_OPENAI_API_KEY",
    "DASHSCOPE_API_KEY",
    "DEEPSEEK_API_KEY",
    "MINIMAX_API_KEY",
    "OPENAI_API_KEY",
})
# `.env.settings` holds the non-secret operational settings that are specific to
# one operator's account and therefore must not be committed either: which Azure
# resource and deployment, which api-version, which AWS region, which MiniMax
# group. They were previously accepted in `.env`, which made the one file people
# guard hold two kinds of thing and gave a setting no home of its own.
#
# These are not secrets, but they are not harmless: `AZURE_OPENAI_ENDPOINT` is
# the host a credential is sent to. Whoever can rewrite it can redirect the key.
# So this file gets the same integrity controls as `.env` -- regular file, no
# symlink, mode 0600 -- for integrity rather than confidentiality.
PROVIDER_SETTING_KEYS = frozenset({
    "AWS_REGION",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_ENDPOINT",
    "MINIMAX_GROUP_ID",
})
# Every key either loader will resolve, from either file.
PROVIDER_ENV_KEYS = PROVIDER_SECRET_KEYS | PROVIDER_SETTING_KEYS
# Retained name: callers that ask "which declared variables are not secret" get
# the same answer, now by construction rather than by a hand-kept exception list.
NON_SECRET_PROVIDER_KEYS = PROVIDER_SETTING_KEYS


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


def _parse_provider_env_file(
    target: Path,
    *,
    allowed: frozenset[str] = PROVIDER_SECRET_KEYS,
    belongs_elsewhere: frozenset[str] = PROVIDER_SETTING_KEYS,
    file_name: str = ENV_FILE_NAME,
    other_file_name: str = SETTINGS_FILE_NAME,
) -> dict[str, str]:
    """Parse an already-validated env file, applying ADR-0009's strict rules.

    Unlike the single-key loader, a blank value is treated as "not configured"
    rather than an error: a template is copied whole and most entries stay
    empty. Unknown keys, duplicates, and unmatched quotes remain hard errors,
    and no interpolation or substitution is performed.

    A key that belongs in the *other* file is refused by name, and the error
    says where it goes. Silently accepting it would put a credential in the file
    that exists precisely so credentials are not mixed with settings.
    """
    parsed: dict[str, str] = {}
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise EnvFileError(f"{file_name} must be readable UTF-8 text") from error
    for line_number, original in enumerate(lines, start=1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise EnvFileError(f"invalid {file_name} assignment on line {line_number}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if key in belongs_elsewhere:
            raise EnvFileError(
                f"{key} on line {line_number} of {file_name} belongs in"
                f" {other_file_name}"
            )
        if key not in allowed:
            raise EnvFileError(
                f"unsupported {file_name} key on line {line_number}: {key}"
            )
        if key in parsed:
            raise EnvFileError(
                f"duplicate {file_name} key on line {line_number}: {key}"
            )
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif value.startswith(("'", '"')) or value.endswith(("'", '"')):
            raise EnvFileError(
                f"unmatched {file_name} quote on line {line_number}"
            )
        parsed[key] = value
    return parsed


def _validated_env_file(target: Path, file_name: str) -> None:
    """Reject a file another local account could substitute or rewrite."""

    if not target.is_file() or target.is_symlink():
        raise EnvFileError(f"{file_name} must be a regular, non-symlink file")
    if stat.S_IMODE(target.stat().st_mode) & 0o077:
        raise EnvFileError(f"{file_name} permissions must be 0600")


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
    present = tuple(sorted(key for key in PROVIDER_SECRET_KEYS if values.get(key)))
    if not target.exists():
        return ProviderCredentialLoadResult(
            path=str(target), file_present=False,
            from_process_environment=present, from_env_file=(), blank_in_env_file=(),
        )
    _validated_env_file(target, ENV_FILE_NAME)
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


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSettingsLoadResult:
    """Which non-secret settings resolved, and from where.

    Unlike `ProviderCredentialLoadResult` this may safely name values, because
    every key here is declared non-secret. It still does not, so that one habit
    covers both loaders and a key promoted to secret later cannot leak through a
    diagnostic written when it was not.
    """

    schema_version: str = "1.0.0"
    path: str
    file_present: bool
    from_process_environment: tuple[str, ...]
    from_settings_file: tuple[str, ...]
    blank_in_settings_file: tuple[str, ...]


def repository_settings_path() -> Path:
    return Path(__file__).resolve().parents[3] / SETTINGS_FILE_NAME


def load_provider_settings(
    path: Path | None = None,
    *,
    environment: MutableMapping[str, str] | None = None,
) -> ProviderSettingsLoadResult:
    """Resolve the non-secret operational settings from `.env.settings`.

    Same rules as the credential loader, deliberately: process environment wins
    and is never overridden, a blank entry reports as unconfigured rather than
    masking a real environment value, and unknown or misfiled keys are refused
    by name. A credential found here is an error, not a convenience.
    """
    target = (path or repository_settings_path()).resolve()
    values = os.environ if environment is None else environment
    present = tuple(sorted(key for key in PROVIDER_SETTING_KEYS if values.get(key)))
    if not target.exists():
        return ProviderSettingsLoadResult(
            path=str(target), file_present=False,
            from_process_environment=present,
            from_settings_file=(), blank_in_settings_file=(),
        )
    _validated_env_file(target, SETTINGS_FILE_NAME)
    parsed = _parse_provider_env_file(
        target,
        allowed=PROVIDER_SETTING_KEYS,
        belongs_elsewhere=PROVIDER_SECRET_KEYS,
        file_name=SETTINGS_FILE_NAME,
        other_file_name=ENV_FILE_NAME,
    )
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
    return ProviderSettingsLoadResult(
        path=str(target), file_present=True,
        from_process_environment=present,
        from_settings_file=tuple(sorted(applied)),
        blank_in_settings_file=tuple(sorted(blank)),
    )


def load_provider_environment(
    *,
    env_path: Path | None = None,
    settings_path: Path | None = None,
    environment: MutableMapping[str, str] | None = None,
) -> tuple[ProviderCredentialLoadResult, ProviderSettingsLoadResult]:
    """Load both files into one mapping. Credentials first, settings second.

    Callers that need a live provider need both, and loading only one is the
    mistake this exists to prevent: a resolved credential with an unresolved
    endpoint fails deep inside an adapter instead of at the preflight.
    """
    values = os.environ if environment is None else environment
    return (
        load_provider_credentials(env_path, environment=values),
        load_provider_settings(settings_path, environment=values),
    )
