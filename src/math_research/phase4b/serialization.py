"""Canonical semantic and operational identities for Phase 4B records."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from enum import Enum
from typing import Any


ZERO_HASH = "sha256:" + "0" * 64


def public_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): public_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [public_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    projector = getattr(value, "value", None)
    if callable(projector):
        return public_value(projector())
    raise TypeError(f"{type(value).__name__} is not canonically serializable")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        public_value(value), allow_nan=False, ensure_ascii=False,
        separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}.{canonical_hash(value)[7:31]}"


def expected_record_id(record_type: str, subject_id: str, payload: Mapping[str, Any]) -> str:
    return stable_id(
        f"phase4b-{record_type}",
        {"record_type": record_type, "subject_id": subject_id, "payload": payload},
    )


def semantic_record_preimage(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    for field in (
        "sequence", "recorded_at", "operational", "content_hash", "operational_hash"
    ):
        result.pop(field, None)
    return result


def semantic_record_hash(value: Mapping[str, Any]) -> str:
    return canonical_hash(semantic_record_preimage(value))


def operational_record_hash(value: Mapping[str, Any]) -> str:
    result = copy.deepcopy(dict(value))
    result["operational_hash"] = ZERO_HASH
    return canonical_hash(result)


def semantic_export_preimage(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["content_hash"] = ZERO_HASH
    result.pop("operational_hash", None)
    result["records"] = [semantic_record_preimage(item) for item in result.get("records", [])]
    return result


def semantic_export_hash(value: Mapping[str, Any]) -> str:
    return canonical_hash(semantic_export_preimage(value))


def operational_export_hash(value: Mapping[str, Any]) -> str:
    result = copy.deepcopy(dict(value))
    result["operational_hash"] = ZERO_HASH
    return canonical_hash(result)


__all__ = [
    "ZERO_HASH",
    "canonical_bytes",
    "canonical_hash",
    "expected_record_id",
    "operational_export_hash",
    "operational_record_hash",
    "public_value",
    "semantic_export_hash",
    "semantic_record_hash",
    "sha256_bytes",
    "stable_id",
]
