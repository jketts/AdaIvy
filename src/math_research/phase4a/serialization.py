"""Canonical serialization and semantic/operational identity for Phase 4A."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from typing import Any, Mapping

from .records import AuditRecord, RecordType

ZERO_HASH = "sha256:" + "0" * 64
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def public_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: public_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [public_value(item) for item in value]
    if isinstance(value, list):
        return [public_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): public_value(item) for key, item in value.items()}
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        public_value(value), allow_nan=False, ensure_ascii=False,
        separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}.{canonical_hash(value)[7:31]}"


_RECORD_ID_PREFIXES = {
    RecordType.POLICY_SNAPSHOT.value: "phase4-policy",
    RecordType.SOURCE_PROVENANCE.value: "source-provenance",
    RecordType.RIGHTS_DECISION.value: "rights",
    RecordType.LIFECYCLE_ACTION.value: "lifecycle",
    RecordType.EVIDENCE_CARD.value: "evidence-card",
    RecordType.APPLICABILITY_REVIEW.value: "applicability",
}


def expected_record_id(value: AuditRecord | Mapping[str, Any]) -> str:
    """Return the sole deterministic identity contract for a Phase 4A record."""

    record = public_value(value)
    if not isinstance(record, dict):
        raise TypeError("record identity preimage must be an object")
    record_type = record.get("record_type")
    try:
        prefix = _RECORD_ID_PREFIXES[str(record_type)]
    except KeyError as error:
        raise ValueError("unsupported Phase 4A record type for identity") from error
    payload = record.get("payload")
    if record_type == RecordType.POLICY_SNAPSHOT.value:
        return stable_id(prefix, payload)
    identity = {
        "schema_version": record.get("schema_version"),
        "record_type": record_type,
        "subject_id": record.get("subject_id"),
        "actor_id": record.get("actor_id"),
        "actor_kind": record.get("actor_kind"),
        "authority": record.get("authority"),
        "reason_code": record.get("reason_code"),
        "reason_detail": record.get("reason_detail"),
        "evidence_refs": sorted(record.get("evidence_refs", [])),
        "policy_snapshot_id": record.get("policy_snapshot_id"),
        "payload": payload,
        "predecessor_id": record.get("predecessor_id"),
        "supersedes": record.get("supersedes"),
    }
    return stable_id(prefix, identity)


def record_hash_preimage(value: AuditRecord | Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(public_value(value))
    if not isinstance(result, dict):
        raise TypeError("record hash preimage must be an object")
    result["content_hash"] = ZERO_HASH
    # Observation time is auditable but does not alter semantic identity.
    result.pop("recorded_at", None)
    return result


def record_content_hash(value: AuditRecord | Mapping[str, Any]) -> str:
    return canonical_hash(record_hash_preimage(value))


def finalize_record(value: AuditRecord) -> AuditRecord:
    return replace(value, content_hash=record_content_hash(value))


def semantic_envelope_preimage(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(public_value(value))
    result["content_hash"] = ZERO_HASH
    result.pop("operational_hash", None)
    result.pop("operational", None)
    for record in result.get("records", []):
        if isinstance(record, dict):
            record.pop("recorded_at", None)
    return result


def semantic_envelope_hash(value: Mapping[str, Any]) -> str:
    return canonical_hash(semantic_envelope_preimage(value))


def operational_envelope_hash(value: Mapping[str, Any]) -> str:
    result = copy.deepcopy(public_value(value))
    result["operational_hash"] = ZERO_HASH
    return canonical_hash(result)
