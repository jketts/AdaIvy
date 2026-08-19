"""Deterministic serialization for Phase 2 value objects."""

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
    if is_dataclass(value):
        return {field.name: public_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [public_value(item) for item in value]
    if isinstance(value, list):
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


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))

