"""Content-hashed, input-only bounds for a live embedding ingestion run.

`LiveRunConfiguration` cannot be reused. It requires
``per_call_output_token_reserve > 0`` (`live_config.py:138`), `preflight_live_gate`
checks a two-call output budget (`live_gate.py:164`) and `execute_live_gate`
asserts exactly two calls with ``total_tokens > 0`` (`live_gate.py:248`). An
input-only single call violates all three, so this is a separate record with no
output-token field at all -- the absence is the enforcement.

`PricingSnapshot` IS reused unchanged: `pricing.py:141-142` already permits a
zero output rate and `estimate_cost_microusd` (`pricing.py:114-121`) already
zeroes the term, so embeddings are the one place the existing cost shape fits.

There is no wall-clock bound. Every bound here is checkable without reading a
clock, so a run is byte-reproducible; a timeout that nothing enforces would be a
field that reads as a guarantee and is not one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..phase2.serialization import canonical_hash, canonical_json
from .constants import (
    FIXTURE_SYNTHETIC_PROVIDER,
    IDENTIFIER_PATTERN,
    NORMALIZATION_SCHEMES,
    SUPPORTED_EMBEDDING_PROVIDERS,
)
from .errors import EmbeddingRunConfigurationError, FixtureProviderNotIngestibleError

EMBEDDING_RUN_CONFIG_SCHEMA_VERSION = "adaivy.embedding-run-configuration.v1"

_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_FIELDS = frozenset({
    "schema_version",
    "configuration_id",
    "provider",
    "model_identifier",
    "dimension",
    "normalization",
    "processor_id",
    "pricing_snapshot_id",
    "call_timeout_milliseconds",
    "per_call_input_token_reserve",
    "budget",
    "content_hash",
})
_BUDGET_FIELDS = frozenset({
    "max_calls", "max_input_tokens", "max_cost_microusd",
})

#: Any field naming an output token budget is a schema error rather than an
#: ignored key, so a copied-and-pasted `LiveRunConfiguration` fails loudly.
_FORBIDDEN_FIELDS = frozenset({
    "per_call_output_token_reserve", "max_output_tokens", "output_tokens",
})


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingBudget:
    max_calls: int
    max_input_tokens: int
    max_cost_microusd: int

    def payload(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "max_input_tokens": self.max_input_tokens,
            "max_cost_microusd": self.max_cost_microusd,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingRunConfiguration:
    schema_version: str
    configuration_id: str
    provider: str
    model_identifier: str
    dimension: int
    normalization: str
    processor_id: str
    pricing_snapshot_id: str
    call_timeout_milliseconds: int
    per_call_input_token_reserve: int
    budget: EmbeddingBudget
    content_hash: str

    def payload(self) -> dict[str, Any]:
        return embedding_run_configuration_payload(self)


def _configuration_payload(values: dict[str, Any]) -> dict[str, Any]:
    payload = dict(values)
    payload["content_hash"] = None
    payload["content_hash"] = canonical_hash(payload)
    return payload


def create_embedding_run_configuration(
    *,
    configuration_id: str,
    provider: str,
    model_identifier: str,
    dimension: int,
    normalization: str,
    processor_id: str,
    pricing_snapshot_id: str,
    call_timeout_milliseconds: int,
    per_call_input_token_reserve: int,
    budget: EmbeddingBudget,
) -> EmbeddingRunConfiguration:
    payload = _configuration_payload({
        "schema_version": EMBEDDING_RUN_CONFIG_SCHEMA_VERSION,
        "configuration_id": configuration_id,
        "provider": provider,
        "model_identifier": model_identifier,
        "dimension": dimension,
        "normalization": normalization,
        "processor_id": processor_id,
        "pricing_snapshot_id": pricing_snapshot_id,
        "call_timeout_milliseconds": call_timeout_milliseconds,
        "per_call_input_token_reserve": per_call_input_token_reserve,
        "budget": budget.payload(),
    })
    return _configuration(payload)


def load_embedding_run_configuration(path: Path) -> EmbeddingRunConfiguration:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EmbeddingRunConfigurationError(
            f"cannot load embedding run configuration: {path}"
        ) from error
    if not isinstance(payload, dict):
        raise EmbeddingRunConfigurationError("configuration must be a JSON object")
    return _configuration(payload)


def write_embedding_run_configuration(
    configuration: EmbeddingRunConfiguration, path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        canonical_json(embedding_run_configuration_payload(configuration)) + "\n",
        encoding="utf-8",
    )


def embedding_run_configuration_payload(
    configuration: EmbeddingRunConfiguration,
) -> dict[str, Any]:
    return {
        "schema_version": configuration.schema_version,
        "configuration_id": configuration.configuration_id,
        "provider": configuration.provider,
        "model_identifier": configuration.model_identifier,
        "dimension": configuration.dimension,
        "normalization": configuration.normalization,
        "processor_id": configuration.processor_id,
        "pricing_snapshot_id": configuration.pricing_snapshot_id,
        "call_timeout_milliseconds": configuration.call_timeout_milliseconds,
        "per_call_input_token_reserve": configuration.per_call_input_token_reserve,
        "budget": configuration.budget.payload(),
        "content_hash": configuration.content_hash,
    }


def _configuration(payload: dict[str, Any]) -> EmbeddingRunConfiguration:
    forbidden = sorted(_FORBIDDEN_FIELDS.intersection(payload))
    if forbidden:
        raise EmbeddingRunConfigurationError(
            f"embedding runs have no output-token budget; remove {forbidden}"
        )
    if set(payload) != set(_FIELDS):
        raise EmbeddingRunConfigurationError(
            "configuration fields differ from schema: expected "
            f"{sorted(_FIELDS)}, got {sorted(payload)}"
        )
    if payload["schema_version"] != EMBEDDING_RUN_CONFIG_SCHEMA_VERSION:
        raise EmbeddingRunConfigurationError("unsupported configuration schema_version")
    for name in ("configuration_id", "provider", "model_identifier", "normalization",
                 "processor_id", "pricing_snapshot_id"):
        if not isinstance(payload[name], str) or not payload[name]:
            raise EmbeddingRunConfigurationError(f"{name} must be a non-empty string")
    if payload["provider"] == FIXTURE_SYNTHETIC_PROVIDER:
        raise FixtureProviderNotIngestibleError(
            "fixture_synthetic may be authored offline and never produced by a run"
        )
    if payload["provider"] not in SUPPORTED_EMBEDDING_PROVIDERS:
        raise EmbeddingRunConfigurationError(
            f"no embedding adapter for provider {payload['provider']!r}"
        )
    if IDENTIFIER_PATTERN.fullmatch(payload["model_identifier"]) is None:
        raise EmbeddingRunConfigurationError("model_identifier is not path-safe")
    if payload["normalization"] not in NORMALIZATION_SCHEMES:
        raise EmbeddingRunConfigurationError("unknown normalization scheme")
    for name in ("dimension", "call_timeout_milliseconds", "per_call_input_token_reserve"):
        value = payload[name]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise EmbeddingRunConfigurationError(f"{name} must be a positive integer")
    budget = payload["budget"]
    if not isinstance(budget, dict) or set(budget) != set(_BUDGET_FIELDS):
        raise EmbeddingRunConfigurationError("budget fields differ from schema")
    for name in sorted(_BUDGET_FIELDS):
        value = budget[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise EmbeddingRunConfigurationError(f"budget.{name} must be non-negative")
    content_hash = payload["content_hash"]
    if not isinstance(content_hash, str) or not _HASH.fullmatch(content_hash):
        raise EmbeddingRunConfigurationError("content_hash is invalid")
    rehashed = dict(payload)
    rehashed["content_hash"] = None
    if canonical_hash(rehashed) != content_hash:
        raise EmbeddingRunConfigurationError("configuration content_hash mismatch")
    return EmbeddingRunConfiguration(
        schema_version=payload["schema_version"],
        configuration_id=payload["configuration_id"],
        provider=payload["provider"],
        model_identifier=payload["model_identifier"],
        dimension=payload["dimension"],
        normalization=payload["normalization"],
        processor_id=payload["processor_id"],
        pricing_snapshot_id=payload["pricing_snapshot_id"],
        call_timeout_milliseconds=payload["call_timeout_milliseconds"],
        per_call_input_token_reserve=payload["per_call_input_token_reserve"],
        budget=EmbeddingBudget(**budget),
        content_hash=content_hash,
    )


__all__ = [
    "EMBEDDING_RUN_CONFIG_SCHEMA_VERSION",
    "EmbeddingBudget",
    "EmbeddingRunConfiguration",
    "create_embedding_run_configuration",
    "embedding_run_configuration_payload",
    "load_embedding_run_configuration",
    "write_embedding_run_configuration",
]
