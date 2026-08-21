"""Canonical serialization for review decisions.

Reuses the Phase 5 primitives unchanged, exactly as the synthesis slice does, so
one canonicalization covers every record that lands in the shared SQLite file.
The semantic/operational split follows the Phase 3B precedent: `recorded_at` and
`sequence` are operational observations and are excluded from semantic identity.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from ..phase5.serialization import (
    ZERO_HASH,
    canonical_bytes,
    canonical_hash,
    sha256_bytes,
    stable_id,
)

#: Removed before a semantic hash is taken. `sequence` is the journal's
#: insertion counter and `recorded_at` is a wall-clock observation supplied by
#: the caller; neither may change what a decision MEANS.
OPERATIONAL_FIELDS = ("content_hash", "operational_hash", "recorded_at", "sequence")

#: A decision payload may carry an `operational` sub-object for observations that
#: move without changing meaning -- a Phase 3B finding's `created_at`, its
#: `elapsed_milliseconds`. It is excluded from semantic identity and retained in
#: the operational hash, following the Phase 3B precedent.
PAYLOAD_OPERATIONAL_KEY = "operational"


def public_value(value: Any) -> Any:
    """Project domain objects to JSON-native values.

    `Enum` is tested before `str` because the review axes subclass `str`, and
    testing `str` first would return the member rather than its value.
    """
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int)):
        # bool is a subclass of int and is already JSON-native. Floats are
        # deliberately not accepted: this repository admits exact values only.
        return value
    if isinstance(value, Mapping):
        return {str(key): public_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [public_value(item) for item in value]
    projector = getattr(value, "value", None)
    if isinstance(projector, str):
        return projector
    raise TypeError(f"value of type {type(value).__name__} is not JSON-native")


def semantic_record_preimage(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    for key in OPERATIONAL_FIELDS:
        result.pop(key, None)
    payload = result.get("payload")
    if isinstance(payload, Mapping) and PAYLOAD_OPERATIONAL_KEY in payload:
        trimmed = dict(payload)
        trimmed.pop(PAYLOAD_OPERATIONAL_KEY, None)
        result["payload"] = trimmed
    return result


def semantic_record_hash(value: Mapping[str, Any]) -> str:
    return canonical_hash(semantic_record_preimage(value))


def operational_record_hash(value: Mapping[str, Any]) -> str:
    """Covers everything except the operational hash field itself."""
    result = dict(value)
    result.pop("operational_hash", None)
    return canonical_hash(result)


def finalize_record(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["content_hash"] = ZERO_HASH
    result["operational_hash"] = ZERO_HASH
    result["content_hash"] = semantic_record_hash(result)
    result["operational_hash"] = operational_record_hash(result)
    return result


def semantic_export_hash(value: Mapping[str, Any]) -> str:
    """Export-level semantic hash with per-record operational fields removed."""
    result = dict(value)
    result.pop("content_hash", None)
    result.pop("operational_hash", None)
    for key in ("decisions", "refusals"):
        items = result.get(key)
        if isinstance(items, list):
            result[key] = [semantic_record_preimage(item) for item in items]
    return canonical_hash(result)


def operational_export_hash(value: Mapping[str, Any]) -> str:
    result = dict(value)
    result.pop("operational_hash", None)
    return canonical_hash(result)


__all__ = [
    "OPERATIONAL_FIELDS",
    "PAYLOAD_OPERATIONAL_KEY",
    "ZERO_HASH",
    "canonical_bytes",
    "canonical_hash",
    "finalize_record",
    "operational_export_hash",
    "operational_record_hash",
    "public_value",
    "semantic_export_hash",
    "semantic_record_hash",
    "semantic_record_preimage",
    "sha256_bytes",
    "stable_id",
]
