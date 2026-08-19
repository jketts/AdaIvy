"""Canonical JSON helpers for Phase 3B records."""

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
    return json.dumps(public_value(value), allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def canonical_json(value: Any) -> str:
    return canonical_bytes(value).decode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def semantic_execution_value(value: Any) -> Any:
    """Return classification inputs without incidental runtime observations."""
    result = public_value(value)
    if isinstance(result, dict):
        result.pop("elapsed_milliseconds", None)
        if result.get("termination_reason") in {"timeout", "output_limit"}:
            return {
                "container_removed": result.get("container_removed"),
                "termination_reason": result.get("termination_reason"),
            }
    return result


def finding_hash_preimage(value: Any) -> dict[str, Any]:
    """Build the semantic finding preimage while retaining operational output."""
    result = public_value(value)
    if not isinstance(result, dict):
        raise TypeError("formal finding hash preimage must be an object")
    result["content_hash"] = ""
    result.pop("created_at", None)
    execution = result.get("execution")
    if isinstance(execution, dict):
        result["execution"] = semantic_execution_value(execution)
    return result


def finding_content_hash(value: Any) -> str:
    return canonical_hash(finding_hash_preimage(value))


def semantic_export_hash(value: Any) -> str:
    """Hash semantic export state while excluding operational elapsed time."""
    result = public_value(value)
    if not isinstance(result, dict):
        raise TypeError("formal export hash preimage must be an object")
    result.pop("content_hash", None)
    result.pop("operational_hash", None)
    findings = result.get("findings")
    if isinstance(findings, list):
        for finding in findings:
            if isinstance(finding, dict):
                finding.pop("created_at", None)
                execution = finding.get("execution")
                if isinstance(execution, dict):
                    finding["execution"] = semantic_execution_value(execution)
    return canonical_hash(result)


def operational_export_hash(value: Any) -> str:
    """Hash the complete export, including elapsed time and semantic hash."""
    result = public_value(value)
    if not isinstance(result, dict):
        raise TypeError("formal export operational preimage must be an object")
    result.pop("operational_hash", None)
    return canonical_hash(result)


def stable_id(prefix: str, value: Any) -> OpaqueId:
    return OpaqueId(f"{prefix}.{canonical_hash(value)[7:31]}")
