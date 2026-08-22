"""Deterministic serialization, reused from the ADR-0067 corpus slice.

Same canonical bytes, same ``content_hash: None`` identity convention, same
fail-closed JSON.  Reuse rather than reimplementation keeps every corpus
artifact hashing identically across slices.
"""

from __future__ import annotations

from ..corpus.serialization import (  # noqa: F401 -- deliberate re-export
    canonical_bytes,
    canonical_hash,
    content_hash_of,
    operational_hash_of,
    public_value,
    sealed,
    semantic_preimage,
    sha256_bytes,
    strict_canonical_object,
    strict_json,
    verify_sealed,
)

__all__ = [
    "canonical_bytes",
    "canonical_hash",
    "content_hash_of",
    "operational_hash_of",
    "public_value",
    "sealed",
    "semantic_preimage",
    "sha256_bytes",
    "strict_canonical_object",
    "strict_json",
    "verify_sealed",
]
