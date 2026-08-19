"""Pinned, non-secret pricing snapshots for reproducible Phase 2 estimates."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..domain.entities import OpaqueId
from .records import PricingSnapshot
from .serialization import canonical_hash, canonical_json


PRICING_SNAPSHOT_SCHEMA_VERSION = "1.0.0"
PRICING_UNITS = "micro-USD per 1,000,000 tokens"
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_FIELDS = {
    "schema_version",
    "snapshot_id",
    "provider",
    "model_identifier",
    "source",
    "captured_at",
    "currency",
    "units",
    "input_microusd_per_million_tokens",
    "output_microusd_per_million_tokens",
    "content_hash",
}


class PricingSnapshotError(ValueError):
    pass


def create_pricing_snapshot(
    *,
    snapshot_id: OpaqueId,
    provider: str,
    model_identifier: str,
    source: str,
    captured_at: str,
    currency: str,
    input_microusd_per_million_tokens: int,
    output_microusd_per_million_tokens: int,
) -> PricingSnapshot:
    payload: dict[str, Any] = {
        "schema_version": PRICING_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id.value,
        "provider": provider,
        "model_identifier": model_identifier,
        "source": source,
        "captured_at": captured_at,
        "currency": currency,
        "units": PRICING_UNITS,
        "input_microusd_per_million_tokens": input_microusd_per_million_tokens,
        "output_microusd_per_million_tokens": output_microusd_per_million_tokens,
        "content_hash": None,
    }
    content_hash = canonical_hash(payload)
    payload["content_hash"] = content_hash
    return _snapshot(payload)


def load_pricing_snapshot(path: Path) -> PricingSnapshot:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PricingSnapshotError(f"cannot load pricing snapshot: {path}") from error
    if not isinstance(payload, dict):
        raise PricingSnapshotError("pricing snapshot must be a JSON object")
    return _snapshot(payload)


def write_pricing_snapshot(snapshot: PricingSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(snapshot) + "\n", encoding="utf-8")


def estimate_cost_microusd(snapshot: PricingSnapshot, *, input_tokens: int, output_tokens: int) -> int:
    if min(input_tokens, output_tokens) < 0:
        raise ValueError("token counts must be non-negative")
    numerator = (
        input_tokens * snapshot.input_microusd_per_million_tokens
        + output_tokens * snapshot.output_microusd_per_million_tokens
    )
    return (numerator + 999_999) // 1_000_000 if numerator else 0


def _snapshot(payload: dict[str, Any]) -> PricingSnapshot:
    if set(payload) != _FIELDS:
        raise PricingSnapshotError("pricing snapshot fields differ from schema")
    if payload["schema_version"] != PRICING_SNAPSHOT_SCHEMA_VERSION:
        raise PricingSnapshotError("unsupported pricing snapshot schema_version")
    for field in ("snapshot_id", "provider", "model_identifier", "source", "captured_at", "currency", "units"):
        if not isinstance(payload[field], str) or not payload[field]:
            raise PricingSnapshotError(f"{field} must be a non-empty string")
    if payload["provider"] != "openai":
        raise PricingSnapshotError("unsupported pricing provider")
    if payload["currency"] != "USD" or payload["units"] != PRICING_UNITS:
        raise PricingSnapshotError("pricing currency or units are unsupported")
    try:
        datetime.fromisoformat(payload["captured_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise PricingSnapshotError("captured_at must be an ISO-8601 timestamp") from error
    for field in ("input_microusd_per_million_tokens", "output_microusd_per_million_tokens"):
        if not isinstance(payload[field], int) or isinstance(payload[field], bool) or payload[field] < 0:
            raise PricingSnapshotError(f"{field} must be a non-negative integer")
    content_hash = payload["content_hash"]
    if not isinstance(content_hash, str) or not _HASH.fullmatch(content_hash):
        raise PricingSnapshotError("content_hash is invalid")
    hash_payload = dict(payload)
    hash_payload["content_hash"] = None
    if canonical_hash(hash_payload) != content_hash:
        raise PricingSnapshotError("pricing snapshot content_hash mismatch")
    return PricingSnapshot(
        schema_version=payload["schema_version"],
        snapshot_id=OpaqueId(payload["snapshot_id"]),
        provider=payload["provider"],
        model_identifier=payload["model_identifier"],
        source=payload["source"],
        captured_at=payload["captured_at"],
        currency=payload["currency"],
        units=payload["units"],
        input_microusd_per_million_tokens=payload["input_microusd_per_million_tokens"],
        output_microusd_per_million_tokens=payload["output_microusd_per_million_tokens"],
        content_hash=content_hash,
    )
