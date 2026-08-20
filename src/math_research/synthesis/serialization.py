"""Canonical serialization for the synthesis slice.

Reuses the Phase 5 primitives unchanged so exports layered on a Phase 5/6
workspace share one canonicalization. Phase 5's `content_hash` convention pops
the key rather than zeroing it; Phase 3B and 4A zero it instead. Mixing the two
would change every hash, so this module deliberately imports rather than
reimplements.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from ..phase5.serialization import (
    ZERO_HASH,
    canonical_bytes,
    canonical_hash,
    content_hash,
    finalize,
    sha256_bytes,
    stable_id,
)


def public_value(value: Any) -> Any:
    """Project domain objects to JSON-native values.

    Phase 5's canonical encoder is a plain `json.dumps`, so anything reaching a
    record must already be JSON-native. Enum is tested before `str` because the
    state axes subclass `str`, and testing `str` first would return the member
    itself rather than its value.
    """
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float)):
        # bool is a subclass of int and is already JSON-native.
        return value
    if isinstance(value, Mapping):
        return {str(key): public_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [public_value(item) for item in value]
    projector = getattr(value, "value", None)
    if callable(projector):
        return public_value(projector())
    raise TypeError(f"value of type {type(value).__name__} is not JSON-native")


def semantic_record_preimage(value: Mapping[str, Any]) -> dict[str, Any]:
    """Record preimage with operational observations removed.

    Section 12: an operational timestamp that is not itself the ordered event
    identity must remain separately hashed metadata, so `recorded_at` is excluded
    from semantic identity. Phase 3B and 4A establish this split; Phase 5 and 6
    instead inject a frozen instant and hash it, which is why this slice cannot
    simply reuse their whole-record hash.
    """
    result = dict(value)
    result.pop("content_hash", None)
    result.pop("operational_hash", None)
    result.pop("recorded_at", None)
    return result


def semantic_record_hash(value: Mapping[str, Any]) -> str:
    return canonical_hash(semantic_record_preimage(value))


def operational_record_hash(value: Mapping[str, Any]) -> str:
    """Covers everything except the operational hash field itself."""
    result = dict(value)
    result.pop("operational_hash", None)
    return canonical_hash(result)


def semantic_export_hash(value: Mapping[str, Any]) -> str:
    """Export-level semantic hash: per-record operational fields removed."""
    result = dict(value)
    result.pop("content_hash", None)
    result.pop("operational_hash", None)
    result["records"] = [semantic_record_preimage(item) for item in result.get("records", [])]
    return canonical_hash(result)


def operational_export_hash(value: Mapping[str, Any]) -> str:
    result = dict(value)
    result.pop("operational_hash", None)
    return canonical_hash(result)


__all__ = [
    "ZERO_HASH",
    "operational_export_hash",
    "operational_record_hash",
    "semantic_export_hash",
    "semantic_record_hash",
    "semantic_record_preimage",
    "canonical_bytes",
    "canonical_hash",
    "content_hash",
    "finalize",
    "public_value",
    "sha256_bytes",
    "stable_id",
]
