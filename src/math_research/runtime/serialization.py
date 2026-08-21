"""Canonical JSON helpers for runtime session records.

Deliberately a separate module from the Phase 2 and Phase 3B equivalents, and
deliberately identical in behaviour: each slice names its own canonicalization
version so a change to one cannot silently re-hash another slice's records.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from ..domain.entities import OpaqueId


def public_value(value: Any) -> Any:
    if isinstance(value, OpaqueId):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: public_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [public_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): public_value(item) for key, item in value.items()}
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        public_value(value), allow_nan=False, ensure_ascii=False,
        separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    return canonical_bytes(value).decode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def stable_id(prefix: str, value: Any) -> OpaqueId:
    return OpaqueId(f"{prefix}.{canonical_hash(value)[7:31]}")
