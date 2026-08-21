"""Canonical identities for the publication projection.

Deliberately a local copy of the same three primitives every other phase
carries, so the projection depends on no phase module and a change to one
phase's canonicalization cannot silently move a published document hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


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


def text_hash(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))
