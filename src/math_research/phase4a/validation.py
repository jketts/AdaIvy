"""Closed-envelope structural and domain verification for Phase 4A.

This is intentionally not a general JSON Schema interpreter.  It directly
encodes the one reviewed production schema whose digest is pinned below.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from . import EXPORT_PROFILE, EXPORT_SCHEMA_VERSION, MAX_EXPORT_BYTES, MAX_RECORDS, SCHEMA_VERSION
from .records import (
    ActorKind, ApplicabilityOutcome, ApplicabilityReason, ApplicabilityStatus,
    Authority, LifecycleType, RecordType, RightsReason, RightsUse, RightsValue,
    VerifiedSnapshot,
)
from .serialization import (
    HASH_RE, canonical_bytes, expected_record_id, operational_envelope_hash,
    record_content_hash, semantic_envelope_hash, stable_id,
)

PRODUCTION_SCHEMA_SHA256 = "sha256:f166aae343997433370c7d61c08e47c52787d51b59af05edae152b074612537a"
POLICY_VERSIONS = [
    "phase4a-rights-v1", "phase4a-applicability-v1",
    "phase4a-lifecycle-v1", "phase4a-canonical-identity-v1",
]
_ID = re.compile(r"^[a-z][a-z0-9_.-]+$")
_REASON = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_TIMESTAMP = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$")
_SUPPORTED_SCHEMA_KEYWORDS = {
    "$schema", "$id", "$defs", "$ref", "title", "type", "additionalProperties",
    "required", "properties", "const", "enum", "items", "minItems", "maxItems",
    "uniqueItems", "minLength", "maxLength", "pattern", "minimum", "maximum", "oneOf",
    "allOf", "if", "then", "maxProperties", "propertyNames",
}


class Phase4ValidationError(ValueError):
    pass


def schema_path() -> Path:
    return Path(__file__).resolve().parents[3] / "schemas" / "phase4-review-v1.schema.json"


def validate_schema_contract(path: Path | None = None) -> str:
    target = path or schema_path()
    data = target.read_bytes()
    observed = "sha256:" + hashlib.sha256(data).hexdigest()
    if observed != PRODUCTION_SCHEMA_SHA256:
        raise Phase4ValidationError("Phase 4A production schema digest drift")
    try:
        schema = json.loads(data)
    except json.JSONDecodeError as error:
        raise Phase4ValidationError("Phase 4A production schema is malformed") from error
    refs: set[str] = set()

    def walk(value: Any, *, in_properties: bool = False) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if not in_properties and key not in _SUPPORTED_SCHEMA_KEYWORDS:
                    raise Phase4ValidationError(f"unsupported production schema keyword: {key}")
                if key == "$ref":
                    if not isinstance(child, str) or not child.startswith("#/$defs/"):
                        raise Phase4ValidationError("non-local production schema reference")
                    refs.add(child.removeprefix("#/$defs/"))
                walk(child, in_properties=key in {"properties", "$defs"})
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(schema)
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict) or not refs.issubset(definitions):
        raise Phase4ValidationError("unresolved production schema reference")
    return observed


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Phase4ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _exact(value: Any, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Phase4ValidationError(f"{path} must be an object")
    if set(value) != fields:
        raise Phase4ValidationError(
            f"{path} fields differ: missing={sorted(fields - set(value))}, extra={sorted(set(value) - fields)}"
        )
    return value


def _string(value: Any, path: str, *, minimum: int = 0, maximum: int = 8192, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise Phase4ValidationError(f"{path} must be a string of length {minimum}..{maximum}")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise Phase4ValidationError(f"{path} has invalid syntax")
    return value


def _identifier(value: Any, path: str) -> str:
    return _string(value, path, minimum=3, maximum=128, pattern=_ID)


def _hash(value: Any, path: str) -> str:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        raise Phase4ValidationError(f"{path} must be a sha256 value")
    return value


def _integer(value: Any, path: str, *, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise Phase4ValidationError(f"{path} must be an integer in range {minimum}..{maximum}")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise Phase4ValidationError(f"{path} must be a boolean")
    return value


def _enum(enum_type: type[Any], value: Any, path: str) -> Any:
    if not isinstance(value, str):
        raise Phase4ValidationError(f"{path} must be a string enum")
    try:
        return enum_type(value)
    except ValueError as error:
        raise Phase4ValidationError(f"{path} has unsupported value {value!r}") from error


def _timestamp(value: Any, path: str) -> str:
    return _string(value, path, minimum=20, maximum=20, pattern=_TIMESTAMP)


def _real_timestamp(value: str, path: str) -> None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise Phase4ValidationError(f"{path} is not a real UTC timestamp") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise Phase4ValidationError(f"{path} is not canonical UTC")


def _nullable(value: Any, validator: Callable[[Any, str], Any], path: str) -> Any:
    return None if value is None else validator(value, path)


def _array(value: Any, path: str, validator: Callable[[Any, str], Any], *, maximum: int, minimum: int = 0, unique: bool = False) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise Phase4ValidationError(f"{path} must be an array of length {minimum}..{maximum}")
    result = [validator(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if unique and len({canonical_bytes(item) for item in result}) != len(result):
        raise Phase4ValidationError(f"{path} must contain unique values")
    return result


_RECORD_FIELDS = {
    "id", "record_type", "subject_id", "sequence", "actor_id", "actor_kind", "authority",
    "reason_code", "reason_detail", "evidence_refs", "recorded_at", "policy_snapshot_id",
    "predecessor_id", "supersedes", "payload", "content_hash", "schema_version",
}


def _validate_record_structure(record: Any, path: str) -> dict[str, Any]:
    value = _exact(record, _RECORD_FIELDS, path)
    _identifier(value["id"], f"{path}.id")
    record_type = _enum(RecordType, value["record_type"], f"{path}.record_type")
    _identifier(value["subject_id"], f"{path}.subject_id")
    _integer(value["sequence"], f"{path}.sequence", maximum=MAX_RECORDS)
    _identifier(value["actor_id"], f"{path}.actor_id")
    _enum(ActorKind, value["actor_kind"], f"{path}.actor_kind")
    _enum(Authority, value["authority"], f"{path}.authority")
    _string(value["reason_code"], f"{path}.reason_code", minimum=1, maximum=64, pattern=_REASON)
    _string(value["reason_detail"], f"{path}.reason_detail", minimum=1, maximum=512)
    _array(value["evidence_refs"], f"{path}.evidence_refs", _identifier, maximum=16, unique=True)
    _timestamp(value["recorded_at"], f"{path}.recorded_at")
    _identifier(value["policy_snapshot_id"], f"{path}.policy_snapshot_id")
    _nullable(value["predecessor_id"], _identifier, f"{path}.predecessor_id")
    _nullable(value["supersedes"], _identifier, f"{path}.supersedes")
    _hash(value["content_hash"], f"{path}.content_hash")
    if value["schema_version"] != SCHEMA_VERSION:
        raise Phase4ValidationError(f"{path}.schema_version is unsupported")
    _validate_payload(record_type, value["payload"], f"{path}.payload")
    return value


def _strings(value: Any, path: str) -> list[str]:
    return _array(value, path, lambda item, item_path: _string(item, item_path, maximum=8192), maximum=32, unique=True)


def _validate_payload(record_type: RecordType, payload: Any, path: str) -> None:
    if record_type is RecordType.POLICY_SNAPSHOT:
        value = _exact(payload, {"schema_sha256", "rights_policy_version", "applicability_policy_version", "lifecycle_policy_version", "canonical_identity_policy_version"}, path)
        _hash(value["schema_sha256"], f"{path}.schema_sha256")
        expected = {
            "rights_policy_version": "phase4a-rights-v1", "applicability_policy_version": "phase4a-applicability-v1",
            "lifecycle_policy_version": "phase4a-lifecycle-v1", "canonical_identity_policy_version": "phase4a-canonical-identity-v1",
        }
        if any(value[key] != item for key, item in expected.items()):
            raise Phase4ValidationError(f"{path} contains an unsupported policy version")
    elif record_type is RecordType.SOURCE_PROVENANCE:
        value = _exact(payload, {"source_identity", "source_name", "content_object_id", "artifact_hash", "byte_length", "media_type", "encoding", "quarantined", "quarantine_reasons", "content_retained", "tombstone"}, path)
        for field in ("source_identity", "content_object_id"):
            _identifier(value[field], f"{path}.{field}")
        _string(value["source_name"], f"{path}.source_name", minimum=1, maximum=255)
        _hash(value["artifact_hash"], f"{path}.artifact_hash")
        _integer(value["byte_length"], f"{path}.byte_length", maximum=2_097_152)
        if value["media_type"] != "text/plain" or value["encoding"] != "utf-8":
            raise Phase4ValidationError(f"{path} permits only UTF-8 text/plain")
        _boolean(value["quarantined"], f"{path}.quarantined"); _boolean(value["content_retained"], f"{path}.content_retained"); _boolean(value["tombstone"], f"{path}.tombstone")
        _array(value["quarantine_reasons"], f"{path}.quarantine_reasons", lambda item, item_path: _string(item, item_path, minimum=1, maximum=64, pattern=_REASON), maximum=16, unique=True)
    elif record_type is RecordType.RIGHTS_DECISION:
        value = _exact(payload, {"source_id", "intended_use", "value", "valid_from", "valid_until", "lifecycle_id"}, path)
        _identifier(value["source_id"], f"{path}.source_id"); _enum(RightsUse, value["intended_use"], f"{path}.intended_use"); _enum(RightsValue, value["value"], f"{path}.value")
        _timestamp(value["valid_from"], f"{path}.valid_from"); _nullable(value["valid_until"], _timestamp, f"{path}.valid_until"); _identifier(value["lifecycle_id"], f"{path}.lifecycle_id")
        if value["valid_until"] is not None and value["valid_until"] < value["valid_from"]:
            raise Phase4ValidationError(f"{path}.valid_until precedes valid_from")
    elif record_type is RecordType.LIFECYCLE_ACTION:
        value = _exact(payload, {"source_id", "action", "target_record_id", "previous_event_id", "original_semantic_hash", "content_retained", "legal_hold"}, path)
        _identifier(value["source_id"], f"{path}.source_id"); _enum(LifecycleType, value["action"], f"{path}.action"); _identifier(value["target_record_id"], f"{path}.target_record_id")
        _nullable(value["previous_event_id"], _identifier, f"{path}.previous_event_id"); _hash(value["original_semantic_hash"], f"{path}.original_semantic_hash")
        _boolean(value["content_retained"], f"{path}.content_retained"); _boolean(value["legal_hold"], f"{path}.legal_hold")
    elif record_type is RecordType.EVIDENCE_CARD:
        value = _exact(payload, {"source_id", "artifact_id", "evidence_unit_id", "span_ids", "span_byte_ranges", "bibliographic_identity_hash", "bibliographic_identity_bytes", "imported_statement_hash", "imported_statement_bytes", "hypotheses_hash", "hypotheses_count", "definitions_hash", "definitions_count", "scope_hash", "scope_count", "exceptions_hash", "exceptions_count", "content_exported"}, path)
        for field in ("source_id", "artifact_id", "evidence_unit_id"):
            _identifier(value[field], f"{path}.{field}")
        _array(value["span_ids"], f"{path}.span_ids", _identifier, maximum=16, minimum=1, unique=True)
        def validate_span(item: Any, item_path: str) -> dict[str, Any]:
            span = _exact(item, {"start", "end", "span_hash"}, item_path)
            start = _integer(span["start"], f"{item_path}.start", maximum=2_097_152)
            end = _integer(span["end"], f"{item_path}.end", minimum=1, maximum=2_097_152)
            _hash(span["span_hash"], f"{item_path}.span_hash")
            if end <= start:
                raise Phase4ValidationError(f"{item_path}.end must exceed start")
            return span
        ranges = _array(value["span_byte_ranges"], f"{path}.span_byte_ranges", validate_span, maximum=16, minimum=1)
        if len(ranges) != len(value["span_ids"]):
            raise Phase4ValidationError(f"{path} span IDs and ranges differ in length")
        if any(ranges[index - 1]["end"] > ranges[index]["start"] for index in range(1, len(ranges))):
            raise Phase4ValidationError(f"{path}.span_byte_ranges must be ordered and non-overlapping")
        for field in ("bibliographic_identity_hash", "imported_statement_hash", "hypotheses_hash", "definitions_hash", "scope_hash", "exceptions_hash"):
            _hash(value[field], f"{path}.{field}")
        for field in ("bibliographic_identity_bytes", "imported_statement_bytes"):
            _integer(value[field], f"{path}.{field}", maximum=8192)
        for field in ("hypotheses_count", "definitions_count", "scope_count", "exceptions_count"):
            _integer(value[field], f"{path}.{field}", maximum=32)
        if value["content_exported"] is not False:
            raise Phase4ValidationError(f"{path}.content_exported must be false")
    else:
        value = _exact(payload, {"source_id", "evidence_card_id", "status", "outcome", "bibliographic_identity_checked", "hypotheses_checked", "definitions_checked", "scope_exceptions_checked", "implication_checked"}, path)
        _identifier(value["source_id"], f"{path}.source_id"); _identifier(value["evidence_card_id"], f"{path}.evidence_card_id")
        _enum(ApplicabilityStatus, value["status"], f"{path}.status"); _enum(ApplicabilityOutcome, value["outcome"], f"{path}.outcome")
        for field in ("bibliographic_identity_checked", "hypotheses_checked", "definitions_checked", "scope_exceptions_checked", "implication_checked"):
            _boolean(value[field], f"{path}.{field}")


def validate_record_for_append(record: Mapping[str, Any]) -> dict[str, Any]:
    """Reject an invalid record before it can enter durable canonical state."""

    value = _validate_record_structure(dict(record), "$")
    if value["content_hash"] != record_content_hash(value):
        raise Phase4ValidationError("record content hash mismatch")
    if value["id"] != expected_record_id(value):
        raise Phase4ValidationError("record deterministic ID mismatch")
    _real_timestamp(value["recorded_at"], "$.recorded_at")
    record_type = RecordType(value["record_type"])
    kind, authority = ActorKind(value["actor_kind"]), Authority(value["authority"])
    if record_type is RecordType.POLICY_SNAPSHOT:
        if (kind, authority) != (ActorKind.SYSTEM, Authority.DETERMINISTIC_POLICY) or value["payload"]["schema_sha256"] != PRODUCTION_SCHEMA_SHA256:
            raise Phase4ValidationError("invalid policy snapshot")
    elif record_type is RecordType.SOURCE_PROVENANCE:
        if (kind, authority, value["reason_code"]) != (ActorKind.HUMAN, Authority.SOURCE_PROVENANCE, "local_user_supplied"):
            raise Phase4ValidationError("invalid source provenance authority")
    elif record_type is RecordType.RIGHTS_DECISION:
        if (kind, authority) != (ActorKind.HUMAN, Authority.HUMAN_FINAL) or not value["evidence_refs"]:
            raise Phase4ValidationError("rights decisions require human final evidence")
        reason = RightsReason(value["reason_code"])
        rights_value = RightsValue(value["payload"]["value"])
        allowed_reasons = {
            RightsValue.ALLOWED: {RightsReason.PERMITTED, RightsReason.RIGHTS_CORRECTED},
            RightsValue.PROHIBITED: {RightsReason.EXPLICITLY_PROHIBITED, RightsReason.RIGHTS_REVOKED, RightsReason.RIGHTS_USE_INCOMPATIBLE},
            RightsValue.UNRESOLVED: {RightsReason.UNKNOWN_RIGHTS, RightsReason.RIGHTS_EXPIRED},
        }
        if reason not in allowed_reasons[rights_value]:
            raise Phase4ValidationError("rights value and reason are inconsistent")
        _real_timestamp(value["payload"]["valid_from"], "$.payload.valid_from")
        if value["payload"]["valid_until"] is not None:
            _real_timestamp(value["payload"]["valid_until"], "$.payload.valid_until")
    elif record_type is RecordType.LIFECYCLE_ACTION:
        if not value["evidence_refs"] or (kind, authority) not in {
            (ActorKind.HUMAN, Authority.HUMAN_FINAL), (ActorKind.SYSTEM, Authority.DETERMINISTIC_POLICY),
        }:
            raise Phase4ValidationError("invalid lifecycle actor/authority")
    elif record_type is RecordType.EVIDENCE_CARD:
        if authority is not Authority.PROPOSAL or not value["evidence_refs"]:
            raise Phase4ValidationError("evidence cards are source-derived proposals")
    else:
        _validate_review_authority(value, kind, authority)
    return value


def _validate_domain(value: dict[str, Any], *, allow_preintake_rights: bool = False) -> None:
    records = value["records"]
    if len(records) > MAX_RECORDS:
        raise Phase4ValidationError("Phase 4A record limit exceeded")
    if [record["sequence"] for record in records] != list(range(len(records))):
        raise Phase4ValidationError("record sequence must be contiguous and canonical")
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise Phase4ValidationError("duplicate Phase 4A record ID")
    by_id = {record["id"]: record for record in records}
    policies = [record for record in records if record["record_type"] == RecordType.POLICY_SNAPSHOT.value]
    if len(policies) != 1 or policies[0]["sequence"] != 0:
        raise Phase4ValidationError("exactly one leading policy snapshot is required")
    policy = policies[0]
    if policy["id"] != policy["policy_snapshot_id"] or policy["payload"]["schema_sha256"] != PRODUCTION_SCHEMA_SHA256:
        raise Phase4ValidationError("policy snapshot does not bind the production schema")
    source_items = [record for record in records if record["record_type"] == RecordType.SOURCE_PROVENANCE.value]
    if len({record["subject_id"] for record in source_items}) != len(source_items):
        raise Phase4ValidationError("duplicate Phase 4A source provenance")
    source_records = {record["subject_id"]: record for record in source_items}
    for source_id, source in source_records.items():
        payload = source["payload"]
        expected_object_id = "phase4-content." + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:32]
        if payload["source_identity"] != source_id or payload["content_object_id"] != expected_object_id:
            raise Phase4ValidationError("source provenance identity/content-object mismatch")
        if payload["tombstone"] or not payload["content_retained"]:
            raise Phase4ValidationError("initial source provenance must describe retained non-tombstone content")
    if not set(value["operational"]["source_path_hashes"]).issubset(source_records):
        raise Phase4ValidationError("operational path observation references unknown source")
    lifecycle_by_source: dict[str, list[dict[str, Any]]] = {}
    predecessor_edges: dict[str, str] = {}
    for record in records:
        _real_timestamp(record["recorded_at"], f"record {record['id']} recorded_at")
        if record["content_hash"] != record_content_hash(record):
            raise Phase4ValidationError(f"record content hash mismatch: {record['id']}")
        if record["id"] != expected_record_id(record):
            raise Phase4ValidationError(f"record deterministic ID mismatch: {record['id']}")
        if record["policy_snapshot_id"] != policy["id"]:
            raise Phase4ValidationError("mixed or unknown policy snapshot")
        if record["predecessor_id"] is not None:
            predecessor = by_id.get(record["predecessor_id"])
            if predecessor is None or predecessor["record_type"] != record["record_type"] or predecessor["subject_id"] != record["subject_id"]:
                raise Phase4ValidationError("invalid predecessor reference")
            if predecessor["sequence"] >= record["sequence"] or predecessor["recorded_at"] > record["recorded_at"]:
                raise Phase4ValidationError("predecessor is not earlier in append/time order")
            predecessor_edges[record["id"]] = predecessor["id"]
        if record["supersedes"] is not None:
            target = by_id.get(record["supersedes"])
            if target is None or target["record_type"] != record["record_type"] or target["subject_id"] != record["subject_id"]:
                raise Phase4ValidationError("invalid supersession reference")
            if target["sequence"] >= record["sequence"] or target["recorded_at"] > record["recorded_at"]:
                raise Phase4ValidationError("superseded record is not earlier in append/time order")
        kind, authority = ActorKind(record["actor_kind"]), Authority(record["authority"])
        record_type = RecordType(record["record_type"])
        if record_type is RecordType.POLICY_SNAPSHOT:
            if (kind, authority) != (ActorKind.SYSTEM, Authority.DETERMINISTIC_POLICY):
                raise Phase4ValidationError("invalid policy snapshot actor/authority")
        elif record_type is RecordType.SOURCE_PROVENANCE:
            if (kind, authority, record["reason_code"]) != (ActorKind.HUMAN, Authority.SOURCE_PROVENANCE, "local_user_supplied"):
                raise Phase4ValidationError("invalid source provenance authority")
        elif record_type is RecordType.RIGHTS_DECISION:
            if (kind, authority) != (ActorKind.HUMAN, Authority.HUMAN_FINAL) or not record["evidence_refs"]:
                raise Phase4ValidationError("rights decisions require human final evidence")
            reason = _enum(RightsReason, record["reason_code"], "rights.reason_code")
            _real_timestamp(record["payload"]["valid_from"], "rights.valid_from")
            if record["payload"]["valid_until"] is not None:
                _real_timestamp(record["payload"]["valid_until"], "rights.valid_until")
            rights_value = RightsValue(record["payload"]["value"])
            allowed_reasons = {
                RightsValue.ALLOWED: {RightsReason.PERMITTED, RightsReason.RIGHTS_CORRECTED},
                RightsValue.PROHIBITED: {RightsReason.EXPLICITLY_PROHIBITED, RightsReason.RIGHTS_REVOKED, RightsReason.RIGHTS_USE_INCOMPATIBLE},
                RightsValue.UNRESOLVED: {RightsReason.UNKNOWN_RIGHTS, RightsReason.RIGHTS_EXPIRED},
            }
            if reason not in allowed_reasons[rights_value]:
                raise Phase4ValidationError("rights value and reason are inconsistent")
        elif record_type is RecordType.LIFECYCLE_ACTION:
            if not record["evidence_refs"] or (kind, authority) not in {
                (ActorKind.HUMAN, Authority.HUMAN_FINAL), (ActorKind.SYSTEM, Authority.DETERMINISTIC_POLICY),
            }:
                raise Phase4ValidationError("invalid lifecycle actor/authority")
            target = by_id.get(record["payload"]["target_record_id"])
            if target is None or target["subject_id"] != record["subject_id"] or target["content_hash"] != record["payload"]["original_semantic_hash"]:
                raise Phase4ValidationError("invalid lifecycle target or original hash")
            lifecycle_by_source.setdefault(record["subject_id"], []).append(record)
        elif record_type is RecordType.EVIDENCE_CARD:
            if authority is not Authority.PROPOSAL or not record["evidence_refs"]:
                raise Phase4ValidationError("evidence cards are source-derived proposals")
        else:
            _validate_review_authority(record, kind, authority)

    for start in predecessor_edges:
        seen: set[str] = set()
        cursor: str | None = start
        while cursor is not None:
            if cursor in seen:
                raise Phase4ValidationError("cycle in predecessor chain")
            seen.add(cursor)
            cursor = predecessor_edges.get(cursor)

    for record in records:
        record_type = RecordType(record["record_type"])
        requires_source = record_type in {
            RecordType.LIFECYCLE_ACTION, RecordType.EVIDENCE_CARD,
            RecordType.APPLICABILITY_REVIEW,
        } or (record_type is RecordType.RIGHTS_DECISION and not allow_preintake_rights)
        if requires_source and record["subject_id"] not in source_records:
            raise Phase4ValidationError("record references unknown source provenance")
        if record_type is RecordType.EVIDENCE_CARD:
            source = source_records[record["subject_id"]]
            payload = record["payload"]
            if payload["source_id"] != record["subject_id"] or payload["artifact_id"] != source["payload"]["content_object_id"]:
                raise Phase4ValidationError("evidence card source/artifact mismatch")
            expected_spans = [stable_id("phase4-span", {"source_id": record["subject_id"], **item}) for item in payload["span_byte_ranges"]]
            if payload["span_ids"] != expected_spans:
                raise Phase4ValidationError("evidence card span identity mismatch")
            expected_unit = stable_id(
                "phase4-evidence-unit",
                {"source_id": record["subject_id"], "artifact_hash": source["payload"]["artifact_hash"], "spans": payload["span_byte_ranges"]},
            )
            if payload["evidence_unit_id"] != expected_unit:
                raise Phase4ValidationError("evidence-card unit identity mismatch")
        elif record_type is RecordType.APPLICABILITY_REVIEW:
            card = by_id.get(record["payload"]["evidence_card_id"])
            if card is None or card["record_type"] != RecordType.EVIDENCE_CARD.value or card["subject_id"] != record["subject_id"]:
                raise Phase4ValidationError("applicability review references unknown evidence card")
    for source_id, events in lifecycle_by_source.items():
        _validate_lifecycle_chain(source_id, events)
    _real_timestamp(value["operational"]["exported_at"], "operational.exported_at")


def _validate_review_authority(record: dict[str, Any], kind: ActorKind, authority: Authority) -> None:
    payload = record["payload"]
    status = ApplicabilityStatus(payload["status"])
    outcome = ApplicabilityOutcome(payload["outcome"])
    _enum(ApplicabilityReason, record["reason_code"], "applicability.reason_code")
    if kind is not ActorKind.HUMAN:
        if authority is not Authority.PROPOSAL or status is not ApplicabilityStatus.PROPOSED:
            raise Phase4ValidationError("nonhuman applicability must remain proposal-only")
    elif status is ApplicabilityStatus.PROPOSED:
        if authority is not Authority.PROPOSAL:
            raise Phase4ValidationError("human proposal has final authority")
    elif authority is not Authority.HUMAN_FINAL:
        raise Phase4ValidationError("final applicability requires named human authority")
    if outcome is ApplicabilityOutcome.APPLICABLE:
        checks = [payload[field] for field in ("bibliographic_identity_checked", "hypotheses_checked", "definitions_checked", "scope_exceptions_checked", "implication_checked")]
        if kind is ActorKind.HUMAN and status is ApplicabilityStatus.CHECKED and not all(checks):
            raise Phase4ValidationError("checked/applicable requires all human review dimensions")
        if status not in {ApplicabilityStatus.PROPOSED, ApplicabilityStatus.CHECKED}:
            raise Phase4ValidationError("applicable outcome conflicts with status")
    if status is ApplicabilityStatus.REJECTED and outcome is not ApplicabilityOutcome.REJECTED:
        raise Phase4ValidationError("rejected applicability status/outcome mismatch")
    if status is ApplicabilityStatus.UNRESOLVED and outcome is not ApplicabilityOutcome.UNRESOLVED:
        raise Phase4ValidationError("unresolved applicability status/outcome mismatch")


def _validate_lifecycle_chain(source_id: str, events: list[dict[str, Any]]) -> None:
    previous: str | None = None
    previous_time: str | None = None
    deletion_requested = False
    legal_hold = False
    for event in events:
        payload = event["payload"]
        if payload["source_id"] != source_id or payload["previous_event_id"] != previous:
            raise Phase4ValidationError("broken or reordered lifecycle chain")
        if previous_time is not None and event["recorded_at"] < previous_time:
            raise Phase4ValidationError("backdated lifecycle event")
        action = LifecycleType(payload["action"])
        if action is LifecycleType.LEGAL_HOLD:
            legal_hold = payload["legal_hold"]
        elif action is LifecycleType.DELETION_REQUEST:
            deletion_requested = True
        elif action is LifecycleType.DELETION_COMPLETION:
            if not deletion_requested or legal_hold or payload["content_retained"]:
                raise Phase4ValidationError("invalid deletion completion")
            deletion_requested = False
        previous = event["id"]
        previous_time = event["recorded_at"]


_ENVELOPE_FIELDS = {"schema_version", "profile", "record_schema_version", "policy_versions", "records", "content_hash", "operational", "operational_hash"}


def validate_structure(value: Any) -> dict[str, Any]:
    """Validate exactly the structural contract represented by the pinned schema."""

    envelope = _exact(value, _ENVELOPE_FIELDS, "$")
    if envelope["schema_version"] != EXPORT_SCHEMA_VERSION or envelope["profile"] != EXPORT_PROFILE or envelope["record_schema_version"] != SCHEMA_VERSION:
        raise Phase4ValidationError("unknown or mixed Phase 4A envelope version/profile")
    if envelope["policy_versions"] != POLICY_VERSIONS:
        raise Phase4ValidationError("unknown or mixed Phase 4A policy versions")
    _array(envelope["records"], "$.records", _validate_record_structure, maximum=MAX_RECORDS)
    _hash(envelope["content_hash"], "$.content_hash"); _hash(envelope["operational_hash"], "$.operational_hash")
    operational = _exact(envelope["operational"], {"exported_at", "exporter_version", "external_cost_usd", "external_calls", "elapsed_milliseconds", "source_path_hashes"}, "$.operational")
    _timestamp(operational["exported_at"], "$.operational.exported_at")
    if operational["exporter_version"] != "phase4a-exporter-v1":
        raise Phase4ValidationError("unsupported exporter or nonzero external cost")
    _integer(operational["external_cost_usd"], "$.operational.external_cost_usd", maximum=0)
    _array(operational["external_calls"], "$.operational.external_calls", lambda item, path: item, maximum=0)
    _integer(operational["elapsed_milliseconds"], "$.operational.elapsed_milliseconds")
    if not isinstance(operational["source_path_hashes"], dict) or len(operational["source_path_hashes"]) > MAX_RECORDS:
        raise Phase4ValidationError("$.operational.source_path_hashes must be a bounded object")
    for source_id, path_hash in operational["source_path_hashes"].items():
        _identifier(source_id, "$.operational.source_path_hashes key")
        _hash(path_hash, f"$.operational.source_path_hashes.{source_id}")
    return envelope


def verify_bytes(data: bytes, *, max_bytes: int = MAX_EXPORT_BYTES) -> VerifiedSnapshot:
    """The sole untrusted acceptance boundary for import/replay/restart."""

    validate_schema_contract()
    if len(data) > max_bytes:
        raise Phase4ValidationError("Phase 4A interchange byte limit exceeded")
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise Phase4ValidationError("Phase 4A interchange is not UTF-8") from error
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=lambda item: (_ for _ in ()).throw(Phase4ValidationError(f"non-finite JSON value: {item}")))
    except json.JSONDecodeError as error:
        raise Phase4ValidationError("malformed Phase 4A JSON") from error
    envelope = validate_structure(value)
    _validate_domain(envelope)
    if envelope["content_hash"] != semantic_envelope_hash(envelope):
        raise Phase4ValidationError("Phase 4A semantic envelope hash mismatch")
    if envelope["operational_hash"] != operational_envelope_hash(envelope):
        raise Phase4ValidationError("Phase 4A operational envelope hash mismatch")
    expected = canonical_bytes(envelope)
    if data not in {expected, expected + b"\n"}:
        raise Phase4ValidationError("Phase 4A interchange is not canonical JSON")
    return VerifiedSnapshot(bytes(expected), envelope["content_hash"], envelope["operational_hash"])


def verify_value(value: Mapping[str, Any]) -> VerifiedSnapshot:
    """Initial verification also traverses the raw-byte boundary."""

    return verify_bytes(canonical_bytes(copy.deepcopy(dict(value))))


def validate_durable_records(
    records: Iterable[Mapping[str, Any]], *, source_path_hashes: Mapping[str, str],
) -> None:
    """Validate durable records while permitting reviewed rights before intake."""

    items = [copy.deepcopy(dict(record)) for record in records]
    if not items:
        return
    envelope = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "profile": EXPORT_PROFILE,
        "record_schema_version": SCHEMA_VERSION,
        "policy_versions": list(POLICY_VERSIONS),
        "records": items,
        "content_hash": "sha256:" + "0" * 64,
        "operational": {
            "exported_at": "2026-08-20T00:00:00Z",
            "exporter_version": "phase4a-exporter-v1",
            "external_cost_usd": 0,
            "external_calls": [],
            "elapsed_milliseconds": 0,
            "source_path_hashes": dict(source_path_hashes),
        },
        "operational_hash": "sha256:" + "0" * 64,
    }
    validate_structure(envelope)
    _validate_domain(envelope, allow_preintake_rights=True)
