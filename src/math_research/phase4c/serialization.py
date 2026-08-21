"""Canonical serialization and report identity for the Phase 4C slice.

Hash convention: **pop-the-key**, never zero-the-key.

`src/math_research/synthesis/serialization.py` records why the choice matters:
Phase 5 pops the `content_hash` key from the preimage while Phase 3B and Phase
4A zero it, and mixing the two changes every hash. This module pops, uniformly:

* `content_hash` covers the report with `content_hash`, `operational`, and
  `operational_hash` **removed** from the preimage.
* `operational_hash` covers the `operational` sub-object exactly as emitted.
  The sub-object carries no hash field of its own, so nothing is popped there,
  and the same pop-only rule applies vacuously.

Timestamps and elapsed milliseconds are operational and are therefore outside
`content_hash` by construction, per the Phase 3B precedent.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


SEMANTIC_EXCLUDED_KEYS = ("content_hash", "operational", "operational_hash")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def semantic_preimage(report: Mapping[str, Any]) -> dict[str, Any]:
    """The exact sub-object covered by `content_hash` (pop-the-key)."""

    result = dict(report)
    for key in SEMANTIC_EXCLUDED_KEYS:
        result.pop(key, None)
    return result


def content_hash(report: Mapping[str, Any]) -> str:
    return canonical_hash(semantic_preimage(report))


def operational_hash(operational: Mapping[str, Any]) -> str:
    return canonical_hash(dict(operational))


__all__ = [
    "SEMANTIC_EXCLUDED_KEYS",
    "canonical_bytes",
    "canonical_hash",
    "content_hash",
    "operational_hash",
    "semantic_preimage",
    "sha256_bytes",
]
