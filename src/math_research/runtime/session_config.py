"""Content-hashed session bounds for one iterative run.

A session's bounds are an artifact, not an argument list. They are written
once, hashed, recorded against the session, and verified before the first model
call, so "what was this run allowed to spend" is answerable from the record
rather than from whoever typed the command.

Every bound is validated against a hard ceiling declared in the package
``__init__``. A configuration file is operator input and is not trusted to be
sane: a file asking for a million iterations is refused rather than clamped,
because silently lowering a requested bound would let the record disagree with
the run.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain.entities import OpaqueId
from ..phase2.records import BudgetLimits
from . import (
    MAX_COST_MICROUSD_CEILING,
    MAX_ITERATIONS_CEILING,
    MAX_MODEL_CALLS_CEILING,
    MAX_WALL_MILLISECONDS_CEILING,
    SESSION_CONFIG_SCHEMA_VERSION,
)
from .serialization import canonical_hash, canonical_json

_HASH = re.compile(r"sha256:[0-9a-f]{64}")

_FIELDS = frozenset({
    "schema_version",
    "session_configuration_id",
    "max_iterations",
    "max_model_calls",
    "max_cost_microusd",
    "max_wall_milliseconds",
    "stagnation_window",
    "per_iteration_budget",
    "content_hash",
})

_ITERATION_BUDGET_FIELDS = frozenset({
    "max_input_tokens",
    "max_output_tokens",
    "max_cost_microusd",
    "max_wall_milliseconds",
    "max_attempts",
})

#: Each bound with the ceiling it is checked against. `stagnation_window` has
#: no cost ceiling; it is bounded by `max_iterations` instead, since a window
#: wider than the run can never close and would disable the stop rule.
_CEILINGS: dict[str, int] = {
    "max_iterations": MAX_ITERATIONS_CEILING,
    "max_model_calls": MAX_MODEL_CALLS_CEILING,
    "max_cost_microusd": MAX_COST_MICROUSD_CEILING,
    "max_wall_milliseconds": MAX_WALL_MILLISECONDS_CEILING,
}


class SessionConfigurationError(ValueError):
    """Fail-closed rejection of a session configuration."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionConfiguration:
    """Immutable session bounds. `content_hash` covers every other field."""

    schema_version: str
    session_configuration_id: OpaqueId
    max_iterations: int
    max_model_calls: int
    max_cost_microusd: int
    max_wall_milliseconds: int
    stagnation_window: int
    per_iteration_budget: BudgetLimits
    content_hash: str


def create_session_configuration(
    *,
    session_configuration_id: OpaqueId,
    max_iterations: int,
    max_model_calls: int,
    max_cost_microusd: int,
    max_wall_milliseconds: int,
    stagnation_window: int,
    per_iteration_budget: BudgetLimits,
) -> SessionConfiguration:
    if per_iteration_budget.max_refinement_rounds != 1:
        raise SessionConfigurationError(
            "the central runtime requires exactly one Phase 2 round per iteration"
        )
    payload: dict[str, Any] = {
        "schema_version": SESSION_CONFIG_SCHEMA_VERSION,
        "session_configuration_id": session_configuration_id.value,
        "max_iterations": max_iterations,
        "max_model_calls": max_model_calls,
        "max_cost_microusd": max_cost_microusd,
        "max_wall_milliseconds": max_wall_milliseconds,
        "stagnation_window": stagnation_window,
        "per_iteration_budget": _budget_payload(per_iteration_budget),
        "content_hash": None,
    }
    payload["content_hash"] = canonical_hash(payload)
    return parse_session_configuration(payload)


def load_session_configuration(path: Path) -> SessionConfiguration:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SessionConfigurationError(f"cannot load session configuration: {path}") from error
    if not isinstance(payload, dict):
        raise SessionConfigurationError("session configuration must be a JSON object")
    return parse_session_configuration(payload)


def write_session_configuration(configuration: SessionConfiguration, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(session_configuration_payload(configuration)) + "\n", encoding="utf-8")


def session_configuration_payload(configuration: SessionConfiguration) -> dict[str, Any]:
    return {
        "schema_version": configuration.schema_version,
        "session_configuration_id": configuration.session_configuration_id.value,
        "max_iterations": configuration.max_iterations,
        "max_model_calls": configuration.max_model_calls,
        "max_cost_microusd": configuration.max_cost_microusd,
        "max_wall_milliseconds": configuration.max_wall_milliseconds,
        "stagnation_window": configuration.stagnation_window,
        "per_iteration_budget": _budget_payload(configuration.per_iteration_budget),
        "content_hash": configuration.content_hash,
    }


def parse_session_configuration(payload: dict[str, Any]) -> SessionConfiguration:
    if set(payload) != _FIELDS:
        raise SessionConfigurationError("session configuration fields differ from schema")
    if payload["schema_version"] != SESSION_CONFIG_SCHEMA_VERSION:
        raise SessionConfigurationError("unsupported session configuration schema_version")
    identifier = payload["session_configuration_id"]
    if not isinstance(identifier, str) or not identifier:
        raise SessionConfigurationError("session_configuration_id must be a non-empty string")
    for field, ceiling in _CEILINGS.items():
        value = _strict_positive(payload[field], field=field)
        if value > ceiling:
            raise SessionConfigurationError(
                f"{field} of {value} exceeds the hard ceiling of {ceiling}"
            )
    window = _strict_positive(payload["stagnation_window"], field="stagnation_window")
    if window > payload["max_iterations"]:
        # A window wider than the run can never close, which would disable the
        # stop rule while appearing to configure it.
        raise SessionConfigurationError("stagnation_window exceeds max_iterations")
    budget = payload["per_iteration_budget"]
    if not isinstance(budget, dict) or set(budget) != _ITERATION_BUDGET_FIELDS:
        raise SessionConfigurationError("per_iteration_budget fields differ from schema")
    for field in sorted(_ITERATION_BUDGET_FIELDS):
        if not isinstance(budget[field], int) or isinstance(budget[field], bool) or budget[field] < 0:
            raise SessionConfigurationError(f"per_iteration_budget.{field} must be a non-negative integer")
    if budget["max_attempts"] < 2:
        # One iteration is one proposer call plus one verifier call. Fewer than
        # two attempts cannot complete a single iteration.
        raise SessionConfigurationError("per_iteration_budget.max_attempts must be at least two")
    if budget["max_cost_microusd"] > payload["max_cost_microusd"]:
        raise SessionConfigurationError("per_iteration cost bound exceeds the session cost bound")
    if budget["max_wall_milliseconds"] > payload["max_wall_milliseconds"]:
        raise SessionConfigurationError("per_iteration time bound exceeds the session time bound")
    content_hash = payload["content_hash"]
    if not isinstance(content_hash, str) or not _HASH.fullmatch(content_hash):
        raise SessionConfigurationError("content_hash is invalid")
    preimage = dict(payload)
    preimage["content_hash"] = None
    if canonical_hash(preimage) != content_hash:
        raise SessionConfigurationError("session configuration content_hash mismatch")
    return SessionConfiguration(
        schema_version=payload["schema_version"],
        session_configuration_id=OpaqueId(identifier),
        max_iterations=payload["max_iterations"],
        max_model_calls=payload["max_model_calls"],
        max_cost_microusd=payload["max_cost_microusd"],
        max_wall_milliseconds=payload["max_wall_milliseconds"],
        stagnation_window=window,
        per_iteration_budget=BudgetLimits(**budget),
        content_hash=content_hash,
    )


def _budget_payload(budget: BudgetLimits) -> dict[str, int]:
    return {
        "max_input_tokens": budget.max_input_tokens,
        "max_output_tokens": budget.max_output_tokens,
        "max_cost_microusd": budget.max_cost_microusd,
        "max_wall_milliseconds": budget.max_wall_milliseconds,
        "max_attempts": budget.max_attempts,
    }


def _strict_positive(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SessionConfigurationError(f"{field} must be a positive integer")
    return value
