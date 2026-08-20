"""Canonical identities shared by Phase 5 services and interchange."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


ZERO_HASH = "sha256:" + "0" * 64


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def content_hash(value: Mapping[str, Any]) -> str:
    preimage = dict(value)
    preimage.pop("content_hash", None)
    return canonical_hash(preimage)


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}." + canonical_hash(value)[7:31]


def finalize(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["content_hash"] = content_hash(result)
    return result
