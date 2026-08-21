"""Explicit, non-secret configuration for the bounded Phase 2 live gate."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.entities import OpaqueId
from . import SUPPORTED_LIVE_PROVIDERS
from .records import BudgetLimits
from .serialization import canonical_hash, canonical_json


LIVE_RUN_CONFIG_SCHEMA_VERSION = "1.0.0"
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_FIELDS = {
    "schema_version",
    "configuration_id",
    "provider",
    "model_identifier",
    "pricing_snapshot_id",
    "call_timeout_milliseconds",
    "per_call_input_token_reserve",
    "per_call_output_token_reserve",
    "budget",
    "content_hash",
}
_BUDGET_FIELDS = {
    "max_input_tokens",
    "max_output_tokens",
    "max_cost_microusd",
    "max_wall_milliseconds",
    "max_attempts",
}


class LiveRunConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class LiveRunConfiguration:
    schema_version: str
    configuration_id: OpaqueId
    provider: str
    model_identifier: str
    pricing_snapshot_id: OpaqueId
    call_timeout_milliseconds: int
    per_call_input_token_reserve: int
    per_call_output_token_reserve: int
    budget: BudgetLimits
    content_hash: str


def create_live_run_configuration(
    *,
    configuration_id: OpaqueId,
    provider: str,
    model_identifier: str,
    pricing_snapshot_id: OpaqueId,
    call_timeout_milliseconds: int,
    per_call_input_token_reserve: int,
    per_call_output_token_reserve: int,
    budget: BudgetLimits,
) -> LiveRunConfiguration:
    payload: dict[str, Any] = {
        "schema_version": LIVE_RUN_CONFIG_SCHEMA_VERSION,
        "configuration_id": configuration_id.value,
        "provider": provider,
        "model_identifier": model_identifier,
        "pricing_snapshot_id": pricing_snapshot_id.value,
        "call_timeout_milliseconds": call_timeout_milliseconds,
        "per_call_input_token_reserve": per_call_input_token_reserve,
        "per_call_output_token_reserve": per_call_output_token_reserve,
        "budget": {
            "max_input_tokens": budget.max_input_tokens,
            "max_output_tokens": budget.max_output_tokens,
            "max_cost_microusd": budget.max_cost_microusd,
            "max_wall_milliseconds": budget.max_wall_milliseconds,
            "max_attempts": budget.max_attempts,
        },
        "content_hash": None,
    }
    payload["content_hash"] = canonical_hash(payload)
    return _configuration(payload)


def load_live_run_configuration(path: Path) -> LiveRunConfiguration:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LiveRunConfigurationError(f"cannot load live-run configuration: {path}") from error
    if not isinstance(payload, dict):
        raise LiveRunConfigurationError("live-run configuration must be a JSON object")
    return _configuration(payload)


def write_live_run_configuration(configuration: LiveRunConfiguration, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(live_run_configuration_payload(configuration)) + "\n", encoding="utf-8")


def live_run_configuration_payload(configuration: LiveRunConfiguration) -> dict[str, Any]:
    return {
        "schema_version": configuration.schema_version,
        "configuration_id": configuration.configuration_id.value,
        "provider": configuration.provider,
        "model_identifier": configuration.model_identifier,
        "pricing_snapshot_id": configuration.pricing_snapshot_id.value,
        "call_timeout_milliseconds": configuration.call_timeout_milliseconds,
        "per_call_input_token_reserve": configuration.per_call_input_token_reserve,
        "per_call_output_token_reserve": configuration.per_call_output_token_reserve,
        "budget": {
            "max_input_tokens": configuration.budget.max_input_tokens,
            "max_output_tokens": configuration.budget.max_output_tokens,
            "max_cost_microusd": configuration.budget.max_cost_microusd,
            "max_wall_milliseconds": configuration.budget.max_wall_milliseconds,
            "max_attempts": configuration.budget.max_attempts,
        },
        "content_hash": configuration.content_hash,
    }


def _configuration(payload: dict[str, Any]) -> LiveRunConfiguration:
    if set(payload) != _FIELDS:
        raise LiveRunConfigurationError("live-run configuration fields differ from schema")
    if payload["schema_version"] != LIVE_RUN_CONFIG_SCHEMA_VERSION:
        raise LiveRunConfigurationError("unsupported live-run configuration schema_version")
    for field in ("configuration_id", "provider", "model_identifier", "pricing_snapshot_id"):
        if not isinstance(payload[field], str) or not payload[field]:
            raise LiveRunConfigurationError(f"{field} must be a non-empty string")
    if payload["provider"] not in SUPPORTED_LIVE_PROVIDERS:
        raise LiveRunConfigurationError("unsupported live provider")
    for field in ("call_timeout_milliseconds", "per_call_input_token_reserve", "per_call_output_token_reserve"):
        if not isinstance(payload[field], int) or isinstance(payload[field], bool) or payload[field] <= 0:
            raise LiveRunConfigurationError(f"{field} must be a positive integer")
    budget = payload["budget"]
    if not isinstance(budget, dict) or set(budget) != _BUDGET_FIELDS:
        raise LiveRunConfigurationError("budget fields differ from schema")
    for field in _BUDGET_FIELDS:
        if not isinstance(budget[field], int) or isinstance(budget[field], bool) or budget[field] < 0:
            raise LiveRunConfigurationError(f"budget.{field} must be a non-negative integer")
    content_hash = payload["content_hash"]
    if not isinstance(content_hash, str) or not _HASH.fullmatch(content_hash):
        raise LiveRunConfigurationError("content_hash is invalid")
    hash_payload = dict(payload)
    hash_payload["content_hash"] = None
    if canonical_hash(hash_payload) != content_hash:
        raise LiveRunConfigurationError("live-run configuration content_hash mismatch")
    return LiveRunConfiguration(
        schema_version=payload["schema_version"],
        configuration_id=OpaqueId(payload["configuration_id"]),
        provider=payload["provider"],
        model_identifier=payload["model_identifier"],
        pricing_snapshot_id=OpaqueId(payload["pricing_snapshot_id"]),
        call_timeout_milliseconds=payload["call_timeout_milliseconds"],
        per_call_input_token_reserve=payload["per_call_input_token_reserve"],
        per_call_output_token_reserve=payload["per_call_output_token_reserve"],
        budget=BudgetLimits(**budget),
        content_hash=content_hash,
    )
