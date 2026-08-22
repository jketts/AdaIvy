"""Deterministic serialization and identity for the ADR-0067 corpus slice.

Canonical bytes, the sha256 helper and ``public_value`` are reused from Phase 4A
rather than re-implemented, so a corpus artifact hashes the same way a rights
record does.  The only addition is the repository's identity convention stated
once: the hash field is set to ``None`` before hashing, and observation-time
fields live in a separate operational hash (the Phase 3B/4C precedent).
"""

from __future__ import annotations

import copy
import json
from typing import Any, Mapping

from ..phase4a.serialization import canonical_bytes, canonical_hash, public_value, sha256_bytes
from .constants import HASH_PATTERN
from .errors import CorpusError


def content_hash_of(value: Mapping[str, Any], *, field: str = "content_hash") -> str:
    """Hash ``value`` with its own hash field explicitly set to ``None``."""

    preimage = dict(public_value(value))
    preimage[field] = None
    return canonical_hash(preimage)


def sealed(value: Mapping[str, Any], *, field: str = "content_hash") -> dict[str, Any]:
    """Return ``value`` with ``field`` set to its own content hash."""

    result = dict(public_value(value))
    result[field] = content_hash_of(result, field=field)
    return result


def verify_sealed(
    value: Mapping[str, Any], *, field: str = "content_hash", label: str, code: str,
) -> dict[str, Any]:
    result = dict(public_value(value))
    supplied = result.get(field)
    if not isinstance(supplied, str) or HASH_PATTERN.fullmatch(supplied) is None:
        raise CorpusError(f"{label} {field} is not a sha256 value", code=code)
    if content_hash_of(result, field=field) != supplied:
        raise CorpusError(f"{label} {field} does not match its content", code=code)
    return result


def operational_hash_of(value: Mapping[str, Any]) -> str:
    """Hash including observation time; the semantic hash excludes it."""

    preimage = dict(public_value(value))
    preimage["operational_hash"] = None
    return canonical_hash(preimage)


def semantic_preimage(value: Mapping[str, Any]) -> dict[str, Any]:
    """Drop the operational block so timings cannot move a semantic hash."""

    result = copy.deepcopy(dict(public_value(value)))
    result.pop("operational", None)
    result.pop("operational_hash", None)
    return result


def strict_json(data: bytes, *, maximum: int, label: str, code: str) -> Any:
    """Fail-closed JSON: bounded, UTF-8 strict, no duplicate keys, no NaN."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"{label} contains a duplicate key {key!r}")
            value[key] = item
        return value

    if not isinstance(data, bytes) or not data or len(data) > maximum:
        raise CorpusError(f"{label} byte bound differs", code=code)
    try:
        return json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value forbidden: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise CorpusError(f"{label} JSON is invalid: {error}", code=code) from error


def strict_canonical_object(
    data: bytes, *, maximum: int, label: str, code: str,
) -> dict[str, Any]:
    """A JSON object that is byte-identical to its own canonical form."""

    value = strict_json(data, maximum=maximum, label=label, code=code)
    if not isinstance(value, dict):
        raise CorpusError(f"{label} is not an object", code=code)
    if data not in {canonical_bytes(value), canonical_bytes(value) + b"\n"}:
        raise CorpusError(f"{label} is not canonical", code=code)
    return value


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
