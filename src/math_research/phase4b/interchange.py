"""Strict bounded interchange validation for candidate-only Phase 4B records."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from .records import (
    CandidateState, EXPORT_PROFILE, EXPORT_VERSION, LEGACY_EXPORT_PROFILE,
    LEGACY_EXPORT_VERSION, MAX_EXPORT_BYTES, MAX_INPUT_BYTES, MAX_RECORDS,
    RecordType, SCHEMA_VERSION,
)
from .replay_artifacts import validate_artifact, validate_artifact_owner
from .serialization import (
    canonical_bytes, expected_record_id, operational_export_hash,
    operational_record_hash, semantic_export_hash, semantic_record_hash,
)


class Phase4BValidationError(ValueError):
    pass


HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
RECORD_FIELDS = frozenset(
    {
        "schema_version", "record_id", "record_type", "subject_id", "sequence",
        "recorded_at", "payload", "operational", "content_hash", "operational_hash",
    }
)
OPERATIONAL_FIELDS = frozenset(
    {
        "attempt_number", "elapsed_milliseconds", "exit_status", "stdout_hash",
        "stderr_hash", "stdout_bytes", "stderr_bytes",
    }
)
EXPORT_FIELDS = frozenset(
    {
        "schema_version", "profile", "record_schema_version", "records",
        "candidate_projection", "replay_artifacts", "content_hash", "operational_hash",
    }
)
LEGACY_EXPORT_FIELDS = EXPORT_FIELDS - {"replay_artifacts"}
PROJECTION_FIELDS = frozenset(
    {"record_id", "subject_id", "record_type", "current_state", "latest_invalidation_id"}
)

PAYLOAD_FIELDS = {
    RecordType.ACQUISITION_CANDIDATE.value: frozenset(
        {
            "candidate_id", "source_id", "request_id", "normalized_url_hash",
            "content_object_id", "artifact_hash", "byte_length", "media_type_hash",
            "acquisition_adapter_id", "acquisition_adapter_version",
            "policy_snapshot_id", "rights_decision_ids", "terms_snapshot_hash",
            "robots_snapshot_hash", "predecessor_record_ids",
        }
    ),
    RecordType.PARSE_CANDIDATE.value: frozenset(
        {
            "candidate_id", "source_id", "artifact_hash", "parser_id",
            "parser_version", "parser_configuration_hash", "policy_snapshot_id",
            "input_byte_length", "output_byte_length", "segment_count",
            "formula_count", "reference_count", "anchors", "predecessor_record_ids",
        }
    ),
    RecordType.FAILURE.value: frozenset(
        {
            "candidate_id", "operation", "source_id", "input_hash", "failure_code",
            "boundary_id", "observed_byte_count", "policy_snapshot_id",
            "predecessor_record_ids",
        }
    ),
    RecordType.INVALIDATION.value: frozenset(
        {
            "invalidation_id", "trigger_record_id", "affected_record_ids",
            "reason_code", "policy_snapshot_id",
        }
    ),
}
ANCHOR_FIELDS = frozenset(
    {"start_offset", "end_offset", "exact_text_hash", "page_number", "object_id_hash"}
)
FAILURE_CODES = frozenset(
    {
        "authorization_denied", "rights_blocked", "robots_blocked", "terms_blocked",
        "network_policy_blocked", "resource_limit", "unsupported_media",
        "malformed_input", "sandbox_failure", "missing_dependency", "hash_mismatch",
        "mapping_incomplete", "parser_failed", "cancelled",
    }
)
INVALIDATION_REASONS = frozenset(
    {
        "source_correction", "source_revocation", "source_takedown", "source_deletion",
        "rights_changed", "applicability_superseded", "parser_superseded",
        "policy_superseded", "integrity_failure",
    }
)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise Phase4BValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise Phase4BValidationError(f"non-finite JSON number is forbidden: {value}")


def decode_json(data: bytes, *, max_bytes: int = MAX_INPUT_BYTES) -> dict[str, Any]:
    if not isinstance(data, bytes):
        raise TypeError("Phase 4B interchange accepts bytes only")
    if len(data) > max_bytes:
        raise Phase4BValidationError(f"input exceeds {max_bytes} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Phase4BValidationError("input must be strict UTF-8") from error
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except json.JSONDecodeError as error:
        raise Phase4BValidationError("input must be valid JSON") from error
    if not isinstance(value, dict):
        raise Phase4BValidationError("input must be a JSON object")
    return value


def _object(value: object, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Phase4BValidationError(f"{label} must be an object")
    observed = set(value)
    if observed != fields:
        raise Phase4BValidationError(
            f"{label} field set differs; missing={sorted(fields-observed)} "
            f"unknown={sorted(observed-fields)}"
        )
    return value


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise Phase4BValidationError(f"{label} must be a bounded identifier")
    return value


def _hash(value: object, label: str, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise Phase4BValidationError(f"{label} must be a sha256 identity")
    return value


def _count(value: object, label: str, maximum: int = 67_108_864) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise Phase4BValidationError(f"{label} is outside its count bound")
    return value


def _ids(value: object, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise Phase4BValidationError(f"{label} must be a list")
    result = tuple(_identifier(item, f"{label}[]") for item in value)
    if (nonempty and not result) or len(result) > MAX_RECORDS or len(set(result)) != len(result):
        raise Phase4BValidationError(f"{label} is empty, duplicated, or oversized")
    if tuple(sorted(result)) != result:
        raise Phase4BValidationError(f"{label} must be canonically sorted")
    return result


def validate_payload(record_type: str, subject_id: str, payload: object) -> Mapping[str, Any]:
    try:
        fields = PAYLOAD_FIELDS[record_type]
    except KeyError as error:
        raise Phase4BValidationError("record type is not candidate-only") from error
    value = _object(payload, fields, f"{record_type} payload")
    if record_type == RecordType.ACQUISITION_CANDIDATE.value:
        for name in (
            "candidate_id", "source_id", "request_id", "content_object_id",
            "acquisition_adapter_id", "acquisition_adapter_version", "policy_snapshot_id",
        ):
            _identifier(value[name], name)
        if value["source_id"] != subject_id:
            raise Phase4BValidationError("acquisition source differs from subject")
        for name in (
            "normalized_url_hash", "artifact_hash", "media_type_hash",
            "terms_snapshot_hash", "robots_snapshot_hash",
        ):
            _hash(value[name], name)
        _count(value["byte_length"], "byte_length", 2_097_152)
        _ids(value["rights_decision_ids"], "rights_decision_ids", nonempty=True)
        _ids(value["predecessor_record_ids"], "predecessor_record_ids")
    elif record_type == RecordType.PARSE_CANDIDATE.value:
        for name in (
            "candidate_id", "source_id", "parser_id", "parser_version", "policy_snapshot_id"
        ):
            _identifier(value[name], name)
        if value["source_id"] != subject_id:
            raise Phase4BValidationError("parse source differs from subject")
        _hash(value["artifact_hash"], "artifact_hash")
        _hash(value["parser_configuration_hash"], "parser_configuration_hash")
        _count(value["input_byte_length"], "input_byte_length", 2_097_152)
        _count(value["output_byte_length"], "output_byte_length", 8_388_608)
        _count(value["segment_count"], "segment_count", 4_096)
        _count(value["formula_count"], "formula_count", 2_048)
        _count(value["reference_count"], "reference_count", 2_048)
        anchors = value["anchors"]
        if isinstance(anchors, (str, bytes)) or not isinstance(anchors, Sequence) or len(anchors) > 4_096:
            raise Phase4BValidationError("anchors must be a bounded list")
        prior: tuple[int, int] | None = None
        for index, item in enumerate(anchors):
            anchor = _object(item, ANCHOR_FIELDS, f"anchor {index}")
            start = _count(anchor["start_offset"], "start_offset", 2_097_152)
            end = _count(anchor["end_offset"], "end_offset", 2_097_152)
            if end <= start or (prior is not None and (start, end) <= prior):
                raise Phase4BValidationError("anchors must be nonempty and canonically ordered")
            prior = (start, end)
            _hash(anchor["exact_text_hash"], "exact_text_hash")
            if anchor["page_number"] is not None:
                if _count(anchor["page_number"], "page_number", 1_000_000) < 1:
                    raise Phase4BValidationError("page_number begins at one")
            _hash(anchor["object_id_hash"], "object_id_hash", nullable=True)
        _ids(value["predecessor_record_ids"], "predecessor_record_ids")
    elif record_type == RecordType.FAILURE.value:
        for name in ("candidate_id", "source_id", "operation", "boundary_id", "policy_snapshot_id"):
            _identifier(value[name], name)
        if value["source_id"] != subject_id or value["operation"] not in {"acquisition", "parse"}:
            raise Phase4BValidationError("failure operation or source is invalid")
        _hash(value["input_hash"], "input_hash")
        if value["failure_code"] not in FAILURE_CODES:
            raise Phase4BValidationError("failure code is not closed")
        _count(value["observed_byte_count"], "observed_byte_count")
        _ids(value["predecessor_record_ids"], "predecessor_record_ids")
    else:
        for name in ("invalidation_id", "trigger_record_id", "reason_code", "policy_snapshot_id"):
            _identifier(value[name], name)
        if value["reason_code"] not in INVALIDATION_REASONS:
            raise Phase4BValidationError("invalidation reason is not closed")
        _ids(value["affected_record_ids"], "affected_record_ids", nonempty=True)
    return value


def validate_operational(value: object) -> Mapping[str, Any]:
    item = _object(value, OPERATIONAL_FIELDS, "operational metadata")
    _count(item["attempt_number"], "attempt_number", 1_000_000)
    if item["attempt_number"] < 1:
        raise Phase4BValidationError("attempt_number begins at one")
    _count(item["elapsed_milliseconds"], "elapsed_milliseconds", 1_800_000)
    if item["exit_status"] is not None and (
        isinstance(item["exit_status"], bool) or not isinstance(item["exit_status"], int)
        or not -255 <= item["exit_status"] <= 255
    ):
        raise Phase4BValidationError("exit_status is invalid")
    _hash(item["stdout_hash"], "stdout_hash", nullable=True)
    _hash(item["stderr_hash"], "stderr_hash", nullable=True)
    stdout_bytes = _count(item["stdout_bytes"], "stdout_bytes", 8_388_608)
    stderr_bytes = _count(item["stderr_bytes"], "stderr_bytes", 8_388_608)
    if stdout_bytes and item["stdout_hash"] is None:
        raise Phase4BValidationError("nonempty stdout requires its full-stream hash")
    if stderr_bytes and item["stderr_hash"] is None:
        raise Phase4BValidationError("nonempty stderr requires its full-stream hash")
    return item


def validate_record(value: object, *, expected_sequence: int | None = None) -> Mapping[str, Any]:
    record = _object(value, RECORD_FIELDS, "Phase 4B record")
    if record["schema_version"] != SCHEMA_VERSION:
        raise Phase4BValidationError("record schema version mismatch")
    record_type = str(record["record_type"])
    subject_id = _identifier(record["subject_id"], "subject_id")
    _identifier(record["record_id"], "record_id")
    sequence = _count(record["sequence"], "sequence", MAX_RECORDS - 1)
    if expected_sequence is not None and sequence != expected_sequence:
        raise Phase4BValidationError("record sequence is not contiguous")
    recorded_at = _identifier(record["recorded_at"], "recorded_at")
    try:
        parsed_time = datetime.strptime(recorded_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise Phase4BValidationError("recorded_at is not a canonical UTC second") from error
    if parsed_time.strftime("%Y-%m-%dT%H:%M:%SZ") != recorded_at:
        raise Phase4BValidationError("recorded_at is not canonical")
    payload = validate_payload(record_type, subject_id, record["payload"])
    validate_operational(record["operational"])
    if record["record_id"] != expected_record_id(record_type, subject_id, payload):
        raise Phase4BValidationError("record ID does not match semantic payload")
    if semantic_record_hash(record) != record["content_hash"]:
        raise Phase4BValidationError("record semantic hash mismatch")
    if operational_record_hash(record) != record["operational_hash"]:
        raise Phase4BValidationError("record operational hash mismatch")
    return record


def project_records(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    candidate_sequences: dict[str, int] = {}
    for record in records:
        if record["record_type"] == RecordType.INVALIDATION.value:
            continue
        state[record["record_id"]] = {
            "record_id": record["record_id"], "subject_id": record["subject_id"],
            "record_type": record["record_type"],
            "current_state": CandidateState.ACTIVE.value,
            "latest_invalidation_id": None,
        }
        candidate_sequences[str(record["record_id"])] = int(record["sequence"])
    # Projection is deliberately independent of input iteration order.  Sequence
    # remains authoritative for causality and for choosing the latest
    # invalidation, which lets the acceptance gate exercise a genuinely reversed
    # record feed rather than merely reverse SQL insertion order.
    invalidations = sorted(
        (record for record in records if record["record_type"] == RecordType.INVALIDATION.value),
        key=lambda record: int(record["sequence"]),
    )
    for record in invalidations:
        for target in record["payload"]["affected_record_ids"]:
            if (
                target not in state
                or candidate_sequences[target] >= int(record["sequence"])
            ):
                raise Phase4BValidationError("invalidation targets unknown or later candidate")
            state[target]["current_state"] = CandidateState.INVALIDATED.value
            state[target]["latest_invalidation_id"] = record["record_id"]
    return [state[key] for key in sorted(state)]


def verify_export_bytes(data: bytes) -> dict[str, Any]:
    value = decode_json(data, max_bytes=MAX_EXPORT_BYTES)
    legacy = value.get("schema_version") == LEGACY_EXPORT_VERSION
    _object(value, LEGACY_EXPORT_FIELDS if legacy else EXPORT_FIELDS, "Phase 4B export")
    if data != canonical_bytes(value):
        raise Phase4BValidationError("export is not canonical JSON")
    if (
        value["schema_version"] != (LEGACY_EXPORT_VERSION if legacy else EXPORT_VERSION)
        or value["profile"] != (LEGACY_EXPORT_PROFILE if legacy else EXPORT_PROFILE)
        or value["record_schema_version"] != SCHEMA_VERSION
    ):
        raise Phase4BValidationError("export version/profile mismatch")
    records = value["records"]
    projection = value["candidate_projection"]
    if not isinstance(records, list) or len(records) > MAX_RECORDS or not isinstance(projection, list):
        raise Phase4BValidationError("export collections are invalid")
    seen: set[str] = set()
    for sequence, record in enumerate(records):
        item = validate_record(record, expected_sequence=sequence)
        if item["record_id"] in seen:
            raise Phase4BValidationError("duplicate record identity")
        predecessors = item["payload"].get("predecessor_record_ids", [])
        if set(predecessors) - seen:
            raise Phase4BValidationError("record cites an unknown or later predecessor")
        seen.add(str(item["record_id"]))
    expected_projection = project_records(records)
    observed: list[dict[str, Any]] = []
    for item in projection:
        entry = _object(item, PROJECTION_FIELDS, "candidate projection")
        observed.append(dict(entry))
    if observed != expected_projection:
        raise Phase4BValidationError("candidate projection is not derived from records")
    artifacts = value.get("replay_artifacts", [])
    if not isinstance(artifacts, list) or len(artifacts) > MAX_RECORDS * 2:
        raise Phase4BValidationError("replay artifact collection is invalid")
    artifact_ids: set[str] = set()
    records_by_id = {item["record_id"]: item for item in records}
    for sequence, artifact in enumerate(artifacts):
        try:
            item = validate_artifact(artifact, expected_sequence=sequence)
            if item["owner_record_id"] in records_by_id:
                validate_artifact_owner(
                    item, records_by_id[item["owner_record_id"]], records_by_id
                )
        except ValueError as error:
            raise Phase4BValidationError(str(error)) from error
        if item["artifact_id"] in artifact_ids or item["owner_record_id"] not in seen:
            raise Phase4BValidationError("replay artifact identity or owner differs")
        artifact_ids.add(str(item["artifact_id"]))
    if semantic_export_hash(value) != value["content_hash"]:
        raise Phase4BValidationError("export semantic hash mismatch")
    if operational_export_hash(value) != value["operational_hash"]:
        raise Phase4BValidationError("export operational hash mismatch")
    return value


def build_export(
    records: Sequence[Mapping[str, Any]], projection: Sequence[Mapping[str, Any]],
    artifacts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build and self-verify the closed canonical envelope value."""
    value: dict[str, Any] = {
        "schema_version": EXPORT_VERSION,
        "profile": EXPORT_PROFILE,
        "record_schema_version": SCHEMA_VERSION,
        "records": [dict(item) for item in records],
        "candidate_projection": [dict(item) for item in projection],
        "replay_artifacts": [dict(item) for item in artifacts],
    }
    value["content_hash"] = semantic_export_hash(value)
    value["operational_hash"] = operational_export_hash(value)
    verify_export_bytes(canonical_bytes(value))
    return value


def replay(data: bytes) -> dict[str, Any]:
    """Verify and detach a Phase 4B export without mutating durable state."""
    return json.loads(canonical_bytes(verify_export_bytes(data)))


__all__ = [
    "EXPORT_FIELDS", "LEGACY_EXPORT_FIELDS", "OPERATIONAL_FIELDS", "PAYLOAD_FIELDS", "PROJECTION_FIELDS",
    "RECORD_FIELDS", "Phase4BValidationError", "build_export", "decode_json", "project_records", "replay",
    "validate_operational", "validate_payload", "validate_record", "verify_export_bytes",
]
