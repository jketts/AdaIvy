"""Deterministic JSON and content-hash helpers for Phase 0 artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_id(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_bytes(value)).hexdigest()}"


def dossier_hash(dossier: dict[str, Any]) -> str:
    payload = dict(dossier)
    payload["content_hash"] = None
    return sha256_id(payload)


def backend_result_hash(result: dict[str, Any]) -> str:
    payload = dict(result)
    payload["export_hash"] = None
    return sha256_id(payload)


def semantic_result_hash(result: dict[str, Any]) -> str:
    """Hash stable result fields, excluding observations that vary by run."""
    volatile = {"duration_ms", "observed_at", "working_directory", "wall_ms"}

    def stable(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items() if key not in volatile}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value

    payload = stable(result)
    return sha256_id(payload)
