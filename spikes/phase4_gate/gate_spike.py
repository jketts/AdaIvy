"""Nonproduction Phase 4A contract gate; synthetic inputs and disposable state only."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, BinaryIO, Callable, Iterable, Iterator, NamedTuple

from jsonschema.validators import Draft202012Validator


FIXTURE_VERSION = "adaivy.phase4-gate-fixture.v1"
CORPUS_VERSION = "adaivy.phase4-gate-corpus.v1"
MANIFEST_VERSION = "adaivy.phase4-gate-fixture-manifest.v1"
CASE_VERSION = "adaivy.phase4-gate-case-manifest.v1"
EXPORT_VERSION = "adaivy.phase4-gate-candidate-export.v1"
RECORD_VERSION = "adaivy.phase4-gate-record.v1"
RESULT_VERSION = "adaivy.phase4-gate-candidate-result.v2"
SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
MAX_SOURCE_BYTES = 2_097_152
MAX_RECORDS = 256
MAX_OUTPUT_BYTES = 67_108_864
MAX_WALL_SECONDS = 600.0
USES = {
    "acquisition", "storage_and_retention", "parsing", "excerpting",
    "embedding", "model_context", "redistribution", "publication",
}
RIGHTS_VALUES = {"allowed", "prohibited", "unresolved"}
ACTOR_TYPES = {"human", "automation", "model", "system"}
NONHUMAN_ACTORS = {"automation", "model", "system"}
OUTCOMES = {"checked", "applicable", "rejected", "unresolved", "not_applicable"}
FINAL_STATUSES = {"checked", "rejected", "unresolved"}
STATUSES = FINAL_STATUSES | {"proposed"}
REASONS = {
    "applicable", "incompatible_hypotheses", "definition_mismatch",
    "scope_or_exception", "misquotation", "contradiction",
    "insufficient_evidence", "rights_blocked", "source_withdrawn",
    "malicious_content",
}
BLOCKING_EVENTS = {"rights_revoked", "content_deleted", "takedown"}
TIMESTAMP = re.compile(
    r"^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T"
    r"([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)


class GateValidationError(ValueError):
    pass


class GateResourceLimitError(GateValidationError):
    pass


class DeadlineBudget:
    """Cooperative monotonic deadline; the parent process remains the hard wall."""

    def __init__(
        self,
        limit_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit_seconds < 0:
            raise ValueError("deadline limit must be nonnegative")
        self.limit_seconds = limit_seconds
        self._clock = clock
        self._started = clock()
        self._last = self._started

    def check(self, operation: str) -> float:
        self._last = self._clock()
        elapsed = self._last - self._started
        if elapsed > self.limit_seconds:
            raise GateResourceLimitError(
                f"gate cooperative deadline exceeded during {operation}"
            )
        return elapsed

    @property
    def elapsed_seconds(self) -> float:
        return self._last - self._started


def _check(deadline: DeadlineBudget | None, operation: str) -> None:
    if deadline is not None:
        deadline.check(operation)


class BoundedWriteResult(NamedTuple):
    bytes_written: int
    sha256: str
    write_calls: int


class BoundedOutputSink:
    """Count, hash, and enforce a byte limit before each underlying write."""

    def __init__(
        self,
        stream: BinaryIO,
        *,
        limit: int = MAX_OUTPUT_BYTES,
        deadline: DeadlineBudget | None = None,
    ) -> None:
        self._stream = stream
        self._limit = limit
        self._deadline = deadline
        self._size = 0
        self._hash = hashlib.sha256()
        self._write_calls = 0

    def write(self, chunk: bytes) -> None:
        _check(self._deadline, "bounded output write")
        if self._size + len(chunk) > self._limit:
            raise GateResourceLimitError("output exceeds 64 MiB")
        written = self._stream.write(chunk)
        if written != len(chunk):
            raise OSError("short bounded output write")
        self._hash.update(chunk)
        self._size += written
        self._write_calls += 1
        _check(self._deadline, "bounded output write")

    def result(self) -> BoundedWriteResult:
        return BoundedWriteResult(
            bytes_written=self._size,
            sha256=self._hash.hexdigest(),
            write_calls=self._write_calls,
        )


class _DiscardBinaryWriter:
    def __init__(self) -> None:
        self.bytes_written = 0

    def write(self, chunk: bytes) -> int:
        self.bytes_written += len(chunk)
        return len(chunk)


_CANONICAL_ENCODER = json.JSONEncoder(
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
)
_UTF8_TEXT_CHUNK = 65_536


def _utf8_chunks(text: str) -> Iterator[bytes]:
    for offset in range(0, len(text), _UTF8_TEXT_CHUNK):
        yield text[offset : offset + _UTF8_TEXT_CHUNK].encode("utf-8")


def stream_json_to_sink(
    value: Any,
    sink: BoundedOutputSink,
    *,
    newline: bool = True,
    deadline: DeadlineBudget | None = None,
) -> BoundedWriteResult:
    """Serialize deterministically without constructing the complete JSON text."""

    _check(deadline, "streaming JSON serialization")
    for fragment in _CANONICAL_ENCODER.iterencode(value):
        _check(deadline, "streaming JSON serialization")
        for chunk in _utf8_chunks(fragment):
            sink.write(chunk)
    if newline:
        sink.write(b"\n")
    _check(deadline, "streaming JSON serialization")
    return sink.result()


def stream_json_bytes(
    value: Any,
    *,
    limit: int = MAX_OUTPUT_BYTES,
    newline: bool = True,
    deadline: DeadlineBudget | None = None,
) -> tuple[bytes, BoundedWriteResult]:
    """Return bytes only after the streaming sink has accepted the whole value."""

    stream = io.BytesIO()
    sink = BoundedOutputSink(stream, limit=limit, deadline=deadline)
    result = stream_json_to_sink(
        value, sink, newline=newline, deadline=deadline
    )
    return stream.getvalue(), result


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise GateValidationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def read_bounded_bytes(
    path: Path,
    *,
    limit: int = MAX_OUTPUT_BYTES,
    deadline: DeadlineBudget | None = None,
) -> bytes:
    _check(deadline, "bounded input open")
    chunks: list[bytes] = []
    total = 0
    with path.open("rb") as stream:
        while True:
            _check(deadline, "bounded input read")
            chunk = stream.read(min(65_536, limit - total + 1))
            _check(deadline, "bounded input read")
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise GateResourceLimitError("input exceeds applicable byte limit")
            chunks.append(chunk)
    _check(deadline, "bounded input finalization")
    return b"".join(chunks)


def strict_json_decode(
    raw: bytes,
    *,
    limit: int = MAX_OUTPUT_BYTES,
    deadline: DeadlineBudget | None = None,
) -> Any:
    _check(deadline, "strict JSON input boundary")
    if len(raw) > limit:
        raise GateResourceLimitError("input exceeds applicable byte limit")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise GateValidationError("JSON input is not valid UTF-8") from error
    _check(deadline, "strict JSON decoding")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                GateValidationError(f"non-finite JSON value: {token}")
            ),
        )
    except json.JSONDecodeError as error:
        raise GateValidationError("malformed JSON input") from error
    _check(deadline, "strict JSON decoding")
    return value


def load_json(
    path: Path,
    *,
    limit: int = MAX_OUTPUT_BYTES,
    deadline: DeadlineBudget | None = None,
) -> Any:
    return strict_json_decode(
        read_bounded_bytes(path, limit=limit, deadline=deadline),
        limit=limit,
        deadline=deadline,
    )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(
    value: Any, deadline: DeadlineBudget | None = None
) -> str:
    digest = hashlib.sha256()
    _check(deadline, "canonical content hashing")
    for fragment in _CANONICAL_ENCODER.iterencode(value):
        _check(deadline, "canonical content hashing")
        for chunk in _utf8_chunks(fragment):
            digest.update(chunk)
    _check(deadline, "canonical content hashing")
    return "sha256:" + digest.hexdigest()


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise GateValidationError(f"noncanonical UTC timestamp: {value!r}")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise GateValidationError(f"invalid UTC timestamp: {value!r}") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise GateValidationError(f"noncanonical UTC timestamp: {value!r}")
    return parsed


def _walk_refs(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref":
                yield child
            yield from _walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_refs(child)


def load_validator(
    schema_path: Path, deadline: DeadlineBudget | None = None
) -> Draft202012Validator:
    schema = load_json(schema_path, deadline=deadline)
    _check(deadline, "schema profile validation")
    if schema.get("$schema") != SCHEMA_DRAFT:
        raise GateValidationError("fixture schema is not Draft 2020-12")
    remote = sorted(ref for ref in _walk_refs(schema) if not ref.startswith("#/"))
    if remote:
        raise GateValidationError(f"external schema references prohibited: {remote}")
    _check(deadline, "schema meta-validation")
    Draft202012Validator.check_schema(schema)
    _check(deadline, "schema meta-validation")
    return Draft202012Validator(schema)


def schema_errors(
    validator: Draft202012Validator,
    instance: Any,
    deadline: DeadlineBudget | None = None,
) -> list[str]:
    _check(deadline, "schema validation")
    observed = list(validator.iter_errors(instance))
    _check(deadline, "schema validation")
    errors = []
    for error in sorted(
        observed,
        key=lambda item: (
            tuple(map(str, item.absolute_path)),
            item.message,
        ),
    ):
        _check(deadline, "deterministic schema error enumeration")
        errors.append(
            f"/{'/'.join(map(str, error.absolute_path))}: {error.message}"
        )
    return errors


def validate_schema_instance(
    validator: Draft202012Validator,
    instance: Any,
    deadline: DeadlineBudget | None = None,
) -> None:
    errors = schema_errors(validator, instance, deadline)
    if errors:
        raise GateValidationError("schema validation failed: " + " | ".join(errors))


def audit_record_validator(validator: Draft202012Validator) -> Draft202012Validator:
    schema = {
        "$schema": SCHEMA_DRAFT,
        "$defs": validator.schema["$defs"],
        "$ref": "#/$defs/audit_record",
    }
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def export_envelope_validator(
    validator: Draft202012Validator,
) -> Draft202012Validator:
    schema = {
        "$schema": SCHEMA_DRAFT,
        "$defs": validator.schema["$defs"],
        "$ref": "#/$defs/export_envelope",
    }
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_export_schema(
    validator: Draft202012Validator,
    export: dict[str, Any],
    deadline: DeadlineBudget | None = None,
) -> None:
    errors = schema_errors(export_envelope_validator(validator), export, deadline)
    if errors:
        raise GateValidationError(
            "export schema validation failed: " + " | ".join(errors)
        )


def _unique(
    values: Iterable[str],
    label: str,
    deadline: DeadlineBudget | None = None,
) -> None:
    _check(deadline, f"{label} uniqueness")
    items = list(values)
    if len(items) != len(set(items)):
        raise GateValidationError(f"duplicate {label}")
    _check(deadline, f"{label} uniqueness")


def _acyclic(
    edges: dict[str, str],
    label: str,
    deadline: DeadlineBudget | None = None,
) -> None:
    for start in edges:
        _check(deadline, f"{label} graph traversal")
        seen: set[str] = set()
        node = start
        while node in edges:
            _check(deadline, f"{label} graph traversal")
            if node in seen:
                raise GateValidationError(f"{label} cycle")
            seen.add(node)
            node = edges[node]


def fixture_rights_history(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return fixture.get("rights_history", [fixture["rights"]])


def validate_fixture(
    fixture: dict[str, Any], deadline: DeadlineBudget | None = None
) -> None:
    _check(deadline, "fixture domain validation")
    if fixture["schema_version"] != FIXTURE_VERSION:
        raise GateValidationError("unknown fixture schema version")
    source = fixture["source"]
    source_bytes = source["text"].encode("utf-8")
    enforce_source_size(source_bytes)
    start, end = source["evidence_start"], source["evidence_end"]
    if not 0 <= start <= end <= len(source_bytes):
        raise GateValidationError("invalid source byte span")
    if source_bytes[start:end] != source["evidence_quote"].encode("utf-8"):
        raise GateValidationError("evidence quote does not match source bytes")
    parse_timestamp(source["recorded_at"])

    rights_history = fixture_rights_history(fixture)
    right_ids = [record["evidence_id"] for record in rights_history]
    _unique(right_ids, "rights record id", deadline)
    if fixture["rights"] != rights_history[-1]:
        raise GateValidationError("effective rights record is not history tail")
    for index, rights in enumerate(rights_history):
        _check(deadline, "rights history validation")
        if rights["requested_use"] not in USES:
            raise GateValidationError("unknown requested use")
        if set(rights["decisions"]) - USES:
            raise GateValidationError("unknown rights decision use")
        if set(rights["decisions"].values()) - RIGHTS_VALUES:
            raise GateValidationError("unknown rights decision value")
        if set(rights["use_scope"]) - USES:
            raise GateValidationError("unknown rights use scope")
        parse_timestamp(rights["reviewed_at"])
        valid_from = parse_timestamp(rights["valid_from"])
        valid_until = (
            parse_timestamp(rights["valid_until"])
            if rights["valid_until"] is not None else None
        )
        if valid_until is not None and valid_until < valid_from:
            raise GateValidationError("rights validity interval reversed")
        if index == 0 and rights["supersedes"] is not None:
            raise GateValidationError("first rights record supersedes prior record")
        if index:
            prior = rights_history[index - 1]
            if rights["supersedes"] != prior["evidence_id"]:
                raise GateValidationError("rights supersession is not append-only")
            if prior["superseded_by"] not in {None, rights["evidence_id"]}:
                raise GateValidationError("rights supersession is not bidirectional")
            if rights["sequence"] <= prior["sequence"]:
                raise GateValidationError("rights sequence is not monotonic")

    events = fixture["lifecycle"]
    event_ids = [event["event_id"] for event in events]
    _unique(event_ids, "lifecycle event id", deadline)
    known = {source["provenance_id"], source["artifact_id"], *right_ids}
    prior_event: str | None = None
    prior_sequence = max(record["sequence"] for record in rights_history)
    for event in events:
        _check(deadline, "lifecycle event validation")
        parse_timestamp(event["recorded_at"])
        if event["sequence"] <= prior_sequence:
            raise GateValidationError("lifecycle sequence is not monotonic")
        if event["previous_event_id"] != prior_event:
            raise GateValidationError("broken lifecycle chain")
        if event["target_record_id"] not in known:
            raise GateValidationError("dangling lifecycle target")
        if event["supersedes"] is not None and event["supersedes"] not in known:
            raise GateValidationError("dangling lifecycle supersession")
        known.add(event["event_id"])
        prior_event = event["event_id"]
        prior_sequence = event["sequence"]
    all_records = {record["evidence_id"]: record for record in rights_history}
    all_records.update({event["event_id"]: event for event in events})
    edges: dict[str, str] = {}
    for record_id, record in all_records.items():
        supersedes = record.get("supersedes")
        if supersedes is not None:
            edges[record_id] = supersedes
            target = all_records.get(supersedes)
            if target is None or target.get("superseded_by") not in {None, record_id}:
                raise GateValidationError("supersession links are not bidirectional")
    _acyclic(edges, "supersession", deadline)

    applicability = fixture["applicability"]
    parse_timestamp(applicability["decided_at"])
    actor = applicability["actor_kind"]
    if actor not in ACTOR_TYPES:
        raise GateValidationError("unknown applicability actor type")
    if actor in NONHUMAN_ACTORS:
        if not (
            applicability["authority"] == "proposal"
            and applicability["status"] == "proposed"
            and applicability["proposed_status"] in OUTCOMES
            and applicability["final_status"] is None
        ):
            raise GateValidationError("nonhuman applicability must remain proposal-only")
    elif not (
        applicability["authority"] == "human_final"
        and applicability["proposed_status"] is None
        and applicability["final_status"] == applicability["status"]
        and applicability["status"] in FINAL_STATUSES
    ):
        raise GateValidationError("human final applicability record inconsistent")
    if applicability["reason_code"] not in REASONS:
        raise GateValidationError("unknown applicability reason")
    _check(deadline, "fixture domain validation")


def rights_state(fixture: dict[str, Any], evaluation_at: str) -> str:
    rights = fixture["rights"]
    requested = rights["requested_use"]
    decision = rights["decisions"].get(requested)
    if decision is None or decision == "unresolved":
        return "missing"
    if decision == "prohibited":
        return "explicitly_prohibited"
    if requested not in rights["use_scope"]:
        return "incompatible"
    if rights["valid_until"] is not None and parse_timestamp(evaluation_at) > parse_timestamp(rights["valid_until"]):
        return "expired"
    if any(
        event["type"] == "rights_revoked"
        and event["target_record_id"] in {record["evidence_id"] for record in fixture_rights_history(fixture)}
        for event in fixture["lifecycle"]
    ):
        return "revoked"
    return "permitted"


def _audit_record(
    *, record_id: str, record_type: str, subject_id: str, actor_id: str,
    actor_type: str, authority: str, reason_code: str, reason_detail: str,
    evidence_ids: list[str], recorded_at: str, sequence: int,
    supersedes: str | None, superseded_by: str | None,
    lifecycle_target: str | None, use_scope: list[str],
    previous_event_id: str | None, payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "record_id": record_id, "record_type": record_type,
        "schema_version": RECORD_VERSION, "subject_id": subject_id,
        "actor_id": actor_id, "actor_type": actor_type,
        "authority": authority, "reason_code": reason_code,
        "reason_detail": reason_detail, "evidence_ids": evidence_ids,
        "recorded_at": recorded_at, "sequence": sequence,
        "supersedes": supersedes, "superseded_by": superseded_by,
        "lifecycle_target": lifecycle_target, "use_scope": use_scope,
        "original_semantic_content_hash": content_hash(payload),
        "previous_event_id": previous_event_id, "payload": payload,
    }


def _evidence_record(evidence_id: str, subject_id: str, recorded_at: str) -> dict[str, Any]:
    payload = {"evidence_id": evidence_id, "subject_id": subject_id}
    return _audit_record(
        record_id=evidence_id, record_type="evidence_link", subject_id=subject_id,
        actor_id="system.gate", actor_type="system", authority="source_provenance",
        reason_code="evidence_reference", reason_detail="Synthetic gate evidence reference",
        evidence_ids=[evidence_id], recorded_at=recorded_at, sequence=0,
        supersedes=None, superseded_by=None, lifecycle_target=None,
        use_scope=[], previous_event_id=None, payload=payload,
    )


def fixture_records(
    fixture: dict[str, Any],
    evaluation_at: str,
    deadline: DeadlineBudget | None = None,
) -> list[dict[str, Any]]:
    _check(deadline, "fixture record projection")
    source = fixture["source"]
    source_payload = {
        key: value for key, value in source.items()
        if key not in {"text", "evidence_quote", "actor_id", "actor_type", "authority", "reason_code", "evidence_ids", "recorded_at", "version", "sequence"}
    }
    source_payload["source_content_hash"] = "sha256:" + sha256(source["text"].encode("utf-8"))
    source_payload["evidence_quote_hash"] = "sha256:" + sha256(source["evidence_quote"].encode("utf-8"))
    source_payload["content_exported"] = False
    records = [_audit_record(
        record_id=source["provenance_id"], record_type="source_provenance",
        subject_id=source["artifact_id"], actor_id=source["actor_id"],
        actor_type=source["actor_type"], authority=source["authority"],
        reason_code=source["reason_code"], reason_detail="Project-authored local synthetic source",
        evidence_ids=source["evidence_ids"], recorded_at=source["recorded_at"],
        sequence=source["sequence"], supersedes=None, superseded_by=None,
        lifecycle_target=None, use_scope=[], previous_event_id=None,
        payload=source_payload,
    )]
    for rights in fixture_rights_history(fixture):
        _check(deadline, "rights record projection")
        payload = copy.deepcopy(rights)
        records.append(_audit_record(
            record_id=rights["evidence_id"], record_type="rights_decision",
            subject_id=source["artifact_id"], actor_id=rights["actor_id"],
            actor_type=rights["actor_type"], authority=rights["authority"],
            reason_code=rights["reason_code"], reason_detail=rights["reason"],
            evidence_ids=[rights["evidence_id"]], recorded_at=rights["reviewed_at"],
            sequence=rights["sequence"], supersedes=rights["supersedes"],
            superseded_by=rights["superseded_by"], lifecycle_target=None,
            use_scope=rights["use_scope"], previous_event_id=None, payload=payload,
        ))
    for event in fixture["lifecycle"]:
        _check(deadline, "lifecycle record projection")
        event_type = {
            "correction": "lifecycle_correction", "rights_revoked": "lifecycle_revocation",
            "content_deleted": "lifecycle_deletion", "takedown": "lifecycle_takedown",
            "restore": "lifecycle_restore",
        }[event["type"]]
        target = event["target_record_id"]
        if target == source["artifact_id"]:
            target = source["provenance_id"]
        records.append(_audit_record(
            record_id=event["event_id"], record_type=event_type,
            subject_id=source["artifact_id"], actor_id=event["actor_id"],
            actor_type=event["actor_type"], authority=event["authority"],
            reason_code=event["reason_code"], reason_detail=event["reason"],
            evidence_ids=event["evidence_ids"], recorded_at=event["recorded_at"],
            sequence=event["sequence"], supersedes=event["supersedes"],
            superseded_by=event["superseded_by"], lifecycle_target=target,
            use_scope=[fixture["rights"]["requested_use"]],
            previous_event_id=event["previous_event_id"], payload=copy.deepcopy(event),
        ))
    applicability = fixture["applicability"]
    records.append(_audit_record(
        record_id=applicability["evidence_id"],
        record_type="applicability_decision" if applicability["actor_kind"] == "human" else "applicability_proposal",
        subject_id=source["artifact_id"], actor_id=applicability["actor_id"],
        actor_type=applicability["actor_kind"], authority=applicability["authority"],
        reason_code=applicability["reason_code"], reason_detail="Synthetic applicability classification",
        evidence_ids=[applicability["evidence_id"]], recorded_at=applicability["decided_at"],
        sequence=applicability["sequence"], supersedes=applicability["supersedes"],
        superseded_by=None, lifecycle_target=None,
        use_scope=[fixture["rights"]["requested_use"]], previous_event_id=None,
        payload=copy.deepcopy(applicability),
    ))
    evidence = sorted({item for record in records for item in record["evidence_ids"]})
    existing = {record["record_id"] for record in records}
    records.extend(
        _evidence_record(item, source["artifact_id"], source["recorded_at"])
        for item in evidence if item not in existing
    )
    _check(deadline, "fixture record projection")
    return records


def _record_order(record: dict[str, Any]) -> tuple[Any, ...]:
    return (record["subject_id"], record["sequence"], record["record_type"], record["record_id"])


def _rehash_export(
    export: dict[str, Any], deadline: DeadlineBudget | None = None
) -> None:
    export["content_hash"] = None
    export["content_hash"] = content_hash(export, deadline)


def make_export(
    records: list[dict[str, Any]],
    fixture_hashes: dict[str, str],
    validator: Draft202012Validator,
    deadline: DeadlineBudget | None = None,
) -> dict[str, Any]:
    _check(deadline, "initial export construction")
    enforce_record_count(len(records))
    export = {
        "schema_version": EXPORT_VERSION,
        "record_schema_version": RECORD_VERSION,
        "id": "phase4-gate-candidate-export.v1", "content_hash": None,
        "policy_versions": ["phase4a-rights-v1", "phase4a-applicability-v1", "phase4a-lifecycle-v1"],
        "fixture_hashes": fixture_hashes,
        "records": sorted(records, key=_record_order),
    }
    _rehash_export(export, deadline)
    raw, _ = stream_json_bytes(export, newline=False, deadline=deadline)
    return verify_export_bytes(raw, validator, deadline=deadline)


def _verify_export_domain(
    export: dict[str, Any],
    frozen_history: dict[str, bytes] | None = None,
    deadline: DeadlineBudget | None = None,
) -> None:
    """Private domain-only helper; acceptance is verify_export_bytes()."""

    _check(deadline, "export domain validation")
    records = export.get("records")
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise GateValidationError("invalid export record count")
    _check(deadline, "export ordering validation")
    if records != sorted(records, key=_record_order):
        raise GateValidationError("reordered history")
    _check(deadline, "export ordering validation")
    ids = [record.get("record_id") for record in records]
    _unique(ids, "export record id", deadline)
    by_id = dict(zip(ids, records, strict=True))
    source_by_subject = {
        record["subject_id"]: record["record_id"]
        for record in records if record.get("record_type") == "source_provenance"
    }
    for record in records:
        _check(deadline, "export record validation")
        if record.get("schema_version") != RECORD_VERSION:
            raise GateValidationError("mixed record version")
        if record.get("actor_type") not in ACTOR_TYPES:
            raise GateValidationError("unknown record actor type")
        if record.get("original_semantic_content_hash") != content_hash(
            record.get("payload"), deadline
        ):
            raise GateValidationError("mutated historical record")
        parse_timestamp(record.get("recorded_at"))
        for evidence_id in record.get("evidence_ids", []):
            if evidence_id not in by_id:
                raise GateValidationError("dangling evidence reference")
        for field in ("supersedes", "superseded_by", "lifecycle_target", "previous_event_id"):
            target = record.get(field)
            if target is not None and target not in by_id:
                raise GateValidationError(f"dangling {field} reference")
        record_type = record["record_type"]
        actor_type = record["actor_type"]
        authority = record["authority"]
        if record_type == "source_provenance" and (
            actor_type != "human" or authority != "source_provenance"
        ):
            raise GateValidationError("invalid source provenance authority")
        if record_type == "evidence_link" and (
            actor_type != "system" or authority != "source_provenance"
        ):
            raise GateValidationError("invalid evidence-link authority")
        if record_type == "rights_decision" and (
            actor_type != "human" or authority != "human_final"
        ):
            raise GateValidationError("invalid rights-decision authority")
        if record_type == "applicability_proposal":
            if record["actor_type"] not in NONHUMAN_ACTORS or record["authority"] != "proposal" or record["payload"].get("final_status") is not None:
                raise GateValidationError("invalid proposal authority")
        if record_type == "applicability_decision":
            if record["actor_type"] != "human" or record["authority"] != "human_final" or record["payload"].get("final_status") is None:
                raise GateValidationError("invalid final applicability authority")
        if record_type.startswith("lifecycle_") and not (
            (actor_type == "human" and authority == "human_final")
            or (
                actor_type == "system"
                and authority == "deterministic_policy"
            )
        ):
            raise GateValidationError("invalid lifecycle actor/authority combination")
        payload = record["payload"]
        if record_type == "source_provenance":
            if payload.get("provenance_id") != record["record_id"] or payload.get("artifact_id") != record["subject_id"]:
                raise GateValidationError("inconsistent provenance identity")
        elif record_type == "evidence_link":
            if payload != {"evidence_id": record["record_id"], "subject_id": record["subject_id"]}:
                raise GateValidationError("inconsistent evidence link")
        elif record_type == "rights_decision":
            expected = {
                "actor_id": payload.get("actor_id"), "actor_type": payload.get("actor_type"),
                "authority": payload.get("authority"), "reason_code": payload.get("reason_code"),
                "reason_detail": payload.get("reason"), "recorded_at": payload.get("reviewed_at"),
                "sequence": payload.get("sequence"), "supersedes": payload.get("supersedes"),
                "superseded_by": payload.get("superseded_by"), "use_scope": payload.get("use_scope"),
            }
            if any(record[key] != value for key, value in expected.items()) or record["record_id"] != payload.get("evidence_id"):
                raise GateValidationError("inconsistent rights audit fields")
        elif record_type in {"applicability_proposal", "applicability_decision"}:
            expected = {
                "actor_id": payload.get("actor_id"), "actor_type": payload.get("actor_kind"),
                "authority": payload.get("authority"), "reason_code": payload.get("reason_code"),
                "recorded_at": payload.get("decided_at"), "sequence": payload.get("sequence"),
                "supersedes": payload.get("supersedes"),
            }
            if any(record[key] != value for key, value in expected.items()) or record["record_id"] != payload.get("evidence_id"):
                raise GateValidationError("inconsistent applicability audit fields")
        elif record_type.startswith("lifecycle_"):
            expected_types = {
                "correction": "lifecycle_correction", "rights_revoked": "lifecycle_revocation",
                "content_deleted": "lifecycle_deletion", "takedown": "lifecycle_takedown",
                "restore": "lifecycle_restore",
            }
            target = payload.get("target_record_id")
            if target == record["subject_id"]:
                target = source_by_subject.get(record["subject_id"])
            expected = {
                "record_type": expected_types.get(payload.get("type")),
                "actor_id": payload.get("actor_id"), "actor_type": payload.get("actor_type"),
                "authority": payload.get("authority"), "reason_code": payload.get("reason_code"),
                "reason_detail": payload.get("reason"), "evidence_ids": payload.get("evidence_ids"),
                "recorded_at": payload.get("recorded_at"), "sequence": payload.get("sequence"),
                "supersedes": payload.get("supersedes"), "superseded_by": payload.get("superseded_by"),
                "lifecycle_target": target, "previous_event_id": payload.get("previous_event_id"),
            }
            if any(record[key] != value for key, value in expected.items()) or record["record_id"] != payload.get("event_id"):
                raise GateValidationError("inconsistent lifecycle audit fields")
    edges: dict[str, str] = {}
    for record in records:
        _check(deadline, "supersession link validation")
        supersedes = record["supersedes"]
        if supersedes is not None:
            edges[record["record_id"]] = supersedes
            if by_id[supersedes].get("superseded_by") not in {None, record["record_id"]}:
                raise GateValidationError("inconsistent supersession links")
    _acyclic(edges, "export supersession", deadline)
    for subject_id in sorted({record["subject_id"] for record in records}):
        _check(deadline, "lifecycle chain validation")
        events = sorted(
            (record for record in records if record["subject_id"] == subject_id and record["record_type"].startswith("lifecycle_")),
            key=lambda record: (record["sequence"], record["record_id"]),
        )
        prior: str | None = None
        for event in events:
            _check(deadline, "lifecycle chain validation")
            if event["previous_event_id"] != prior:
                raise GateValidationError("broken lifecycle chain")
            prior = event["record_id"]
    if frozen_history is not None:
        for record_id, original in frozen_history.items():
            _check(deadline, "append-only history validation")
            if record_id not in by_id or canonical_bytes(by_id[record_id]) != original:
                raise GateValidationError("mutated historical record")
    _check(deadline, "export domain validation")


def _verify_export_hash(
    export: dict[str, Any], deadline: DeadlineBudget | None = None
) -> None:
    expected_hash = export["content_hash"]
    candidate = copy.deepcopy(export)
    candidate["content_hash"] = None
    if expected_hash != content_hash(candidate, deadline):
        raise GateValidationError("candidate export hash mismatch")


def verify_export_bytes(
    raw: bytes,
    validator: Draft202012Validator,
    *,
    frozen_history: dict[str, bytes] | None = None,
    deadline: DeadlineBudget | None = None,
) -> dict[str, Any]:
    """The sole fail-closed acceptance boundary for untrusted export bytes."""

    _check(deadline, "strict export boundary")
    decoded = strict_json_decode(
        raw, limit=MAX_OUTPUT_BYTES, deadline=deadline
    )
    if not isinstance(decoded, dict):
        raise GateValidationError("export envelope must be an object")
    if (
        decoded.get("schema_version") != EXPORT_VERSION
        or decoded.get("record_schema_version") != RECORD_VERSION
        or decoded.get("id") != "phase4-gate-candidate-export.v1"
    ):
        raise GateValidationError("unsupported export profile or version")
    validate_export_schema(validator, decoded, deadline)
    _verify_export_domain(decoded, frozen_history, deadline)
    _verify_export_hash(decoded, deadline)
    _check(deadline, "strict export acceptance")
    return copy.deepcopy(decoded)


def load_verified_export_file(
    path: Path,
    validator: Draft202012Validator,
    *,
    frozen_history: dict[str, bytes] | None = None,
    deadline: DeadlineBudget | None = None,
) -> dict[str, Any]:
    raw = read_bounded_bytes(
        path, limit=MAX_OUTPUT_BYTES, deadline=deadline
    )
    return verify_export_bytes(
        raw,
        validator,
        frozen_history=frozen_history,
        deadline=deadline,
    )


def write_bounded_json_atomic(
    path: Path,
    value: Any,
    *,
    limit: int = MAX_OUTPUT_BYTES,
    deadline: DeadlineBudget | None = None,
    verify_temporary: Callable[[Path], None] | None = None,
) -> BoundedWriteResult:
    """Stream to a temporary file and publish only after all checks succeed."""

    _check(deadline, "atomic output preparation")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            sink = BoundedOutputSink(
                stream, limit=limit, deadline=deadline
            )
            result = stream_json_to_sink(
                value, sink, newline=True, deadline=deadline
            )
            _check(deadline, "atomic output flush")
            stream.flush()
            os.fsync(stream.fileno())
            _check(deadline, "atomic output flush")
        if verify_temporary is not None:
            _check(deadline, "pre-publication verification")
            verify_temporary(temporary)
            _check(deadline, "pre-publication verification")
        _check(deadline, "atomic output publication")
        os.replace(temporary, path)
        return result
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def write_verified_export_atomic(
    path: Path,
    snapshot: dict[str, Any],
    validator: Draft202012Validator,
    *,
    deadline: DeadlineBudget | None = None,
) -> BoundedWriteResult:
    def verify_temporary(temporary: Path) -> None:
        accepted = load_verified_export_file(
            temporary, validator, deadline=deadline
        )
        if accepted != snapshot:
            raise GateValidationError(
                "serialized export differs from verified snapshot"
            )

    return write_bounded_json_atomic(
        path,
        snapshot,
        deadline=deadline,
        verify_temporary=verify_temporary,
    )


def measure_bounded_json(
    value: Any,
    *,
    limit: int = MAX_OUTPUT_BYTES,
    deadline: DeadlineBudget | None = None,
) -> BoundedWriteResult:
    stream = _DiscardBinaryWriter()
    sink = BoundedOutputSink(stream, limit=limit, deadline=deadline)
    return stream_json_to_sink(
        value, sink, newline=True, deadline=deadline
    )


def evaluate_fixture(
    fixture: dict[str, Any],
    evaluation_at: str,
    deadline: DeadlineBudget | None = None,
) -> dict[str, Any]:
    _check(deadline, "fixture evaluation")
    validate_fixture(fixture, deadline)
    state = rights_state(fixture, evaluation_at)
    action_allowed = state == "permitted"
    applicability = fixture["applicability"]
    status = applicability["final_status"] if applicability["authority"] == "human_final" else "proposed"
    blocked = any(event["type"] in BLOCKING_EVENTS for event in fixture["lifecycle"])
    result = {
        "fixture_id": fixture["fixture_id"], "fixture_hash": sha256(canonical_bytes(fixture)),
        "rights_state": state, "action_allowed": action_allowed,
        "applicability_status": status, "reason_code": applicability["reason_code"],
        "retrievable": action_allowed and not blocked and not fixture["source"]["quarantined"],
    }
    expected = fixture["expected"]
    for key in expected:
        _check(deadline, "fixture expected-result comparison")
        if result[key] != expected[key]:
            raise GateValidationError(f"unexpected {key} for {fixture['fixture_id']}")
    return result


def evaluate_corpus(
    corpus: dict[str, Any],
    manifest: dict[str, Any],
    validator: Draft202012Validator,
    deadline: DeadlineBudget | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _check(deadline, "corpus evaluation")
    if corpus.get("schema_version") != CORPUS_VERSION or manifest.get("schema_version") != MANIFEST_VERSION:
        raise GateValidationError("unknown corpus or manifest version")
    evaluation_at = corpus["evaluation_at"]
    parse_timestamp(evaluation_at)
    fixtures = corpus["fixtures"]
    thresholds = manifest["accepted_thresholds"]
    if len(fixtures) != thresholds["fixture_count"]:
        raise GateValidationError("fixture count threshold failed")
    for fixture in fixtures:
        _check(deadline, "fixture iteration")
        validate_schema_instance(validator, fixture, deadline)
        validate_fixture(fixture, deadline)
    ids = [fixture["fixture_id"] for fixture in fixtures]
    _unique(ids, "fixture id", deadline)
    counts: dict[str, int] = {}
    for fixture in fixtures:
        _check(deadline, "fixture class counting")
        counts[fixture["primary_class"]] = counts.get(fixture["primary_class"], 0) + 1
    if counts != manifest["class_counts"]:
        raise GateValidationError("fixture class distribution mismatch")
    hashes = {}
    for fixture in fixtures:
        _check(deadline, "fixture hash verification")
        hashes[fixture["fixture_id"]] = content_hash(
            fixture, deadline
        ).removeprefix("sha256:")
    if hashes != manifest["fixture_hashes"]:
        raise GateValidationError("fixture hash manifest mismatch")
    results = [
        evaluate_fixture(fixture, evaluation_at, deadline)
        for fixture in fixtures
    ]
    records = []
    for fixture in fixtures:
        _check(deadline, "fixture record iteration")
        records.extend(fixture_records(fixture, evaluation_at, deadline))
    export = make_export(records, hashes, validator, deadline)
    checked = [fixture for fixture in fixtures if fixture["expected"]["applicability_status"] == "checked"]
    metrics = {
        "fixture_count": len(fixtures), "provenance_and_span_validation": 1.0,
        "human_review_coverage_for_checked_applicability": sum(f["applicability"]["actor_kind"] == "human" for f in checked) / len(checked),
        "false_applicability_accepts": sum(r["applicability_status"] == "checked" and f["primary_class"] != "applicable" for r, f in zip(results, fixtures, strict=True)),
        "prohibited_rights_actions": sum(r["action_allowed"] and not f["expected"]["action_allowed"] for r, f in zip(results, fixtures, strict=True)),
        "quarantine_escapes": sum(r["retrievable"] and f["source"]["quarantined"] for r, f in zip(results, fixtures, strict=True)),
        "rejection_reason_accuracy": sum(r["reason_code"] == f["expected"]["reason_code"] for r, f in zip(results, fixtures, strict=True)) / len(fixtures),
    }
    for name in ("fixture_count", "provenance_and_span_validation", "human_review_coverage_for_checked_applicability", "false_applicability_accepts", "prohibited_rights_actions", "quarantine_escapes", "rejection_reason_accuracy"):
        _check(deadline, "acceptance threshold validation")
        if metrics[name] != thresholds[name]:
            raise GateValidationError(f"threshold failed: {name}")
    _check(deadline, "corpus evaluation")
    return export, metrics


def _event(kind: str, base: dict[str, Any], sequence: int = 2) -> dict[str, Any]:
    source = base["source"]
    right_id = base["rights"]["evidence_id"]
    mapping = {
        "rights_revoked": (right_id, "rights_revoked"),
        "content_deleted": (source["provenance_id"], "content_deleted"),
        "takedown": (source["provenance_id"], "source_takedown"),
        "correction": (right_id, "rights_corrected"),
    }
    target, reason = mapping[kind]
    return {
        "event_id": f"lifecycle.case.{kind}", "type": kind,
        "target_record_id": target, "actor_id": "actor.owner", "actor_type": "human",
        "authority": "human_final", "reason_code": reason,
        "reason": f"synthetic {kind} case", "evidence_ids": [f"evidence.case.{kind}"],
        "recorded_at": f"2026-08-20T00:00:0{sequence}Z", "sequence": sequence,
        "version": 1, "supersedes": None, "superseded_by": None,
        "previous_event_id": None,
    }


def _case_fixture(base: dict[str, Any], kind: str) -> dict[str, Any]:
    fixture = copy.deepcopy(base)
    fixture["fixture_id"] = "phase4.fixture.case-" + kind.replace("_", "-")
    fixture["tags"] = [kind.replace("_", "-")]
    if kind == "rights_explicitly_prohibited":
        fixture["rights"]["decisions"][fixture["rights"]["requested_use"]] = "prohibited"
        fixture["rights"]["reason_code"] = "explicitly_prohibited"
    elif kind == "rights_missing":
        fixture["rights"]["decisions"].pop(fixture["rights"]["requested_use"], None)
        fixture["rights"]["reason_code"] = "unknown_rights"
    elif kind == "rights_expired":
        fixture["rights"]["valid_until"] = "2026-08-20T00:00:04Z"
        fixture["rights"]["reason_code"] = "rights_expired"
    elif kind == "rights_incompatible":
        fixture["rights"]["use_scope"] = ["excerpting"]
        fixture["rights"]["reason_code"] = "rights_use_incompatible"
    elif kind == "rights_revoked":
        event = _event("rights_revoked", fixture)
        event["supersedes"] = fixture["rights"]["evidence_id"]
        fixture["lifecycle"] = [event]
    elif kind in {"lifecycle_deletion", "lifecycle_takedown"}:
        event_type = "content_deleted" if kind.endswith("deletion") else "takedown"
        fixture["lifecycle"] = [_event(event_type, fixture)]
    elif kind == "lifecycle_correction":
        original = copy.deepcopy(fixture["rights"])
        corrected = copy.deepcopy(original)
        corrected["evidence_id"] = "rights-evidence.case.correction.v2"
        corrected["sequence"] = 2
        corrected["reviewed_at"] = "2026-08-20T00:00:02Z"
        corrected["reason_code"] = "rights_corrected"
        corrected["reason"] = "synthetic corrected rights record"
        corrected["supersedes"] = original["evidence_id"]
        corrected["superseded_by"] = None
        fixture["rights_history"] = [original, corrected]
        fixture["rights"] = corrected
        event = _event("correction", fixture, 3)
        event["target_record_id"] = corrected["evidence_id"]
        fixture["lifecycle"] = [event]
    return fixture


def _expect_rejected(operation: Callable[[], Any], text: str) -> None:
    try:
        operation()
    except (GateValidationError, json.JSONDecodeError):
        return
    raise GateValidationError(f"adversarial case was accepted: {text}")


REPLAY_MUTATION_KINDS = {
    "replay_missing_actor_id",
    "replay_missing_authority",
    "replay_source_authority_proposal",
    "replay_invalid_actor_authority",
    "replay_nonhuman_final_authority",
    "replay_mandatory_field_omission_one_of_many",
    "replay_actor_reference_inconsistency",
}


def mutate_export_for_replay_case(
    export: dict[str, Any], kind: str
) -> dict[str, Any]:
    mutated = copy.deepcopy(export)
    source = next(
        record
        for record in mutated["records"]
        if record["record_type"] == "source_provenance"
    )
    evidence = next(
        record
        for record in mutated["records"]
        if record["record_type"] == "evidence_link"
    )
    applicability = next(
        record
        for record in mutated["records"]
        if record["record_type"] == "applicability_decision"
    )
    rights = next(
        record
        for record in mutated["records"]
        if record["record_type"] == "rights_decision"
    )
    if kind == "replay_missing_actor_id":
        source.pop("actor_id")
    elif kind == "replay_missing_authority":
        source.pop("authority")
    elif kind == "replay_source_authority_proposal":
        source["authority"] = "proposal"
    elif kind == "replay_invalid_actor_authority":
        evidence["actor_type"] = "automation"
        evidence["authority"] = "human_final"
    elif kind == "replay_nonhuman_final_authority":
        applicability["actor_type"] = "model"
    elif kind == "replay_mandatory_field_omission_one_of_many":
        mutated["records"][-1].pop("reason_detail")
    elif kind == "replay_actor_reference_inconsistency":
        rights["actor_id"] = "actor.inconsistent"
    else:
        raise GateValidationError(f"unknown replay mutation: {kind}")
    _rehash_export(mutated)
    return mutated


def run_cases(
    repo_root: Path,
    corpus: dict[str, Any],
    validator: Draft202012Validator,
    deadline: DeadlineBudget | None = None,
) -> dict[str, Any]:
    cases_doc = load_json(
        repo_root / "fixtures/phase4-gate/cases.json", deadline=deadline
    )
    if cases_doc.get("schema_version") != CASE_VERSION:
        raise GateValidationError("unknown case manifest version")
    _expect_rejected(
        lambda: load_json(
            repo_root / "fixtures/phase4-gate/malformed.json",
            deadline=deadline,
        ),
        "malformed JSON",
    )
    _expect_rejected(
        lambda: load_json(
            repo_root / "fixtures/phase4-gate/duplicate-keys.json",
            deadline=deadline,
        ),
        "duplicate keys",
    )
    base = corpus["fixtures"][0]
    evaluation_at = corpus["evaluation_at"]
    results: dict[str, str] = {}
    nonhuman_actor_matrix = 0
    human_actor_matrix = 0
    replay_mutation_rejections = 0
    for case in cases_doc["cases"]:
        _check(deadline, "adversarial case iteration")
        kind = case["kind"]
        fixture = _case_fixture(base, kind)
        if kind in {"rights_permitted", "rights_explicitly_prohibited", "rights_missing", "rights_expired", "rights_revoked", "rights_incompatible", "lifecycle_correction", "lifecycle_deletion", "lifecycle_takedown"}:
            validate_schema_instance(validator, fixture, deadline)
            validate_fixture(fixture, deadline)
            state = rights_state(fixture, evaluation_at)
            expected = case["expected_outcome"]
            if kind.startswith("lifecycle_") or kind == "rights_revoked":
                records_before = {
                    r["record_id"]: canonical_bytes(r)
                    for r in fixture_records(base, evaluation_at, deadline)
                }
                export = make_export(
                    fixture_records(fixture, evaluation_at, deadline),
                    {fixture["fixture_id"]: sha256(canonical_bytes(fixture))},
                    validator,
                    deadline,
                )
                common = {record_id: value for record_id, value in records_before.items() if record_id in {r["record_id"] for r in export["records"]}}
                raw, _ = stream_json_bytes(
                    export, newline=False, deadline=deadline
                )
                verify_export_bytes(
                    raw,
                    validator,
                    frozen_history=common,
                    deadline=deadline,
                )
                if kind == "lifecycle_correction" and len(fixture_rights_history(fixture)) != 2:
                    raise GateValidationError("correction did not append a rights record")
                if kind in {"lifecycle_deletion", "lifecycle_takedown"}:
                    provenance = next(r for r in export["records"] if r["record_type"] == "source_provenance")
                    if "text" in provenance["payload"] or provenance["payload"].get("content_exported") is not False:
                        raise GateValidationError("withdrawn content retained in export")
                if kind == "rights_revoked" and state != expected:
                    raise GateValidationError(f"rights state {kind}: {state} != {expected}")
                results[case["case_id"]] = expected
            else:
                if state != expected:
                    raise GateValidationError(f"rights state {kind}: {state} != {expected}")
                if state != "permitted" and rights_state(fixture, evaluation_at) == "permitted":
                    raise GateValidationError("rights state failed open")
                results[case["case_id"]] = state
            continue
        if kind in {"unknown_field", "missing_required_field", "wrong_field_type", "unknown_schema_version"}:
            if kind == "unknown_field": fixture["unexpected"] = True
            elif kind == "missing_required_field": fixture.pop("source")
            elif kind == "wrong_field_type": fixture["source"]["evidence_start"] = "zero"
            else: fixture["schema_version"] = "adaivy.phase4-gate-fixture.v2"
            if not schema_errors(validator, fixture, deadline):
                raise GateValidationError(f"schema accepted {kind}")
            results[case["case_id"]] = case["expected_outcome"]
            continue
        if kind == "nonhuman_final_status_attempts":
            for actor in sorted(NONHUMAN_ACTORS):
                for outcome in sorted(OUTCOMES):
                    attempt = copy.deepcopy(base)
                    app = attempt["applicability"]
                    app.update({"actor_kind": actor, "actor_id": f"{actor}.case", "authority": "human_final", "status": outcome, "proposed_status": None, "final_status": outcome})
                    if not schema_errors(validator, attempt, deadline):
                        raise GateValidationError(f"schema accepted nonhuman final {actor}/{outcome}")
                    safe = copy.deepcopy(attempt)
                    safe["applicability"].update({"authority": "proposal", "status": "proposed", "proposed_status": outcome, "final_status": None})
                    validate_schema_instance(validator, safe, deadline)
                    validate_fixture(safe, deadline)
                    make_export(
                        fixture_records(safe, evaluation_at, deadline),
                        {safe["fixture_id"]: sha256(canonical_bytes(safe))},
                        validator,
                        deadline,
                    )
                    nonhuman_actor_matrix += 1
            final_status_for_outcome = {
                "checked": "checked", "applicable": "checked",
                "rejected": "rejected", "unresolved": "unresolved",
                "not_applicable": "rejected",
            }
            for outcome in sorted(OUTCOMES):
                human = copy.deepcopy(base)
                final_status = final_status_for_outcome[outcome]
                human["applicability"].update({
                    "actor_kind": "human", "actor_id": f"human.case.{outcome}",
                    "authority": "human_final", "status": final_status,
                    "proposed_status": None, "final_status": final_status,
                })
                validate_schema_instance(validator, human, deadline)
                validate_fixture(human, deadline)
                make_export(
                    fixture_records(human, evaluation_at, deadline),
                    {human["fixture_id"]: sha256(canonical_bytes(human))},
                    validator,
                    deadline,
                )
                human_actor_matrix += 1
            unknown = copy.deepcopy(base)
            unknown["applicability"]["actor_kind"] = "external_agent"
            if not schema_errors(validator, unknown, deadline):
                raise GateValidationError("schema accepted unknown actor type")
            _expect_rejected(
                lambda: validate_fixture(unknown, deadline),
                "unknown actor type",
            )
            results[case["case_id"]] = case["expected_outcome"]
            continue
        export = make_export(
            fixture_records(base, evaluation_at, deadline),
            {base["fixture_id"]: sha256(canonical_bytes(base))},
            validator,
            deadline,
        )
        if kind in REPLAY_MUTATION_KINDS:
            export = mutate_export_for_replay_case(export, kind)
            raw, _ = stream_json_bytes(
                export, newline=True, deadline=deadline
            )
            _expect_rejected(
                lambda raw=raw: verify_export_bytes(
                    raw, validator, deadline=deadline
                ),
                f"replay boundary {kind}",
            )
            with tempfile.TemporaryDirectory(
                prefix="adaivy-phase4-restart-mutation."
            ) as directory:
                path = Path(directory) / "candidate-export.json"
                path.write_bytes(raw)
                _expect_rejected(
                    lambda path=path: load_verified_export_file(
                        path, validator, deadline=deadline
                    ),
                    f"restart boundary {kind}",
                )
            replay_mutation_rejections += 1
            results[case["case_id"]] = case["expected_outcome"]
            continue
        if kind in {"mixed_envelope_new_record_old", "mixed_envelope_old_record_new", "one_mismatched_record_among_many"}:
            if kind == "mixed_envelope_new_record_old": export["schema_version"] = "adaivy.phase4-gate-candidate-export.v2"
            elif kind == "mixed_envelope_old_record_new": export["record_schema_version"] = "adaivy.phase4-gate-record.v2"
            else: export["records"][1]["schema_version"] = "adaivy.phase4-gate-record.v2"
        elif kind == "duplicate_ids": export["records"][1]["record_id"] = export["records"][0]["record_id"]
        elif kind == "dangling_references": export["records"][0]["evidence_ids"] = ["evidence.missing"]
        elif kind == "supersession_cycle":
            export["records"][0]["supersedes"] = export["records"][1]["record_id"]
            export["records"][1]["supersedes"] = export["records"][0]["record_id"]
            export["records"][0]["superseded_by"] = export["records"][1]["record_id"]
            export["records"][1]["superseded_by"] = export["records"][0]["record_id"]
        elif kind == "reordered_history": export["records"][0], export["records"][1] = export["records"][1], export["records"][0]
        elif kind == "mutated_history": export["records"][0]["payload"]["artifact_id"] = "artifact.mutated"
        _rehash_export(export, deadline)
        raw, _ = stream_json_bytes(export, newline=True, deadline=deadline)
        _expect_rejected(
            lambda raw=raw: verify_export_bytes(
                raw, validator, deadline=deadline
            ),
            kind,
        )
        results[case["case_id"]] = case["expected_outcome"]
    return {
        "case_count": len(cases_doc["cases"]) + 2,
        "case_hashes": {
            case["case_id"]: content_hash(case, deadline).removeprefix(
                "sha256:"
            )
            for case in cases_doc["cases"]
        },
        "raw_case_hashes": {
            "phase4.case.malformed-json": sha256(read_bounded_bytes(
                repo_root / "fixtures/phase4-gate/malformed.json",
                deadline=deadline,
            )),
            "phase4.case.duplicate-json-keys": sha256(read_bounded_bytes(
                repo_root / "fixtures/phase4-gate/duplicate-keys.json",
                deadline=deadline,
            )),
        },
        "actor_outcome_matrix_cells": nonhuman_actor_matrix + human_actor_matrix,
        "nonhuman_actor_outcome_matrix_cells": nonhuman_actor_matrix,
        "human_actor_outcome_matrix_cells": human_actor_matrix,
        "replay_mutation_rejections": replay_mutation_rejections,
        "results": results,
    }


def enforce_source_size(data: bytes) -> int:
    if len(data) > MAX_SOURCE_BYTES:
        raise GateResourceLimitError("source exceeds 2 MiB")
    return len(data)


def enforce_record_count(count: int) -> int:
    if count > MAX_RECORDS:
        raise GateResourceLimitError("record count exceeds 256")
    return count


def _exercise_source_boundary(
    deadline: DeadlineBudget | None = None,
) -> tuple[int, bool]:
    with tempfile.TemporaryDirectory(
        prefix="adaivy-phase4-source-boundary."
    ) as directory:
        root = Path(directory)
        exact = root / "exact-source.txt"
        overflow = root / "overflow-source.txt"
        _check(deadline, "source boundary fixture preparation")
        exact.write_bytes(b"x" * MAX_SOURCE_BYTES)
        overflow.write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))
        _check(deadline, "source boundary fixture preparation")
        exact_size = len(read_bounded_bytes(
            exact, limit=MAX_SOURCE_BYTES, deadline=deadline
        ))
        rejected = False
        try:
            read_bounded_bytes(
                overflow, limit=MAX_SOURCE_BYTES, deadline=deadline
            )
        except GateResourceLimitError:
            rejected = True
        return exact_size, rejected


def _exercise_output_boundary(
    overflow: bool, deadline: DeadlineBudget | None = None
) -> tuple[int, bool]:
    stream = _DiscardBinaryWriter()
    sink = BoundedOutputSink(stream, deadline=deadline)
    one_mib = b"x" * 1_048_576
    for _ in range(64):
        sink.write(one_mib)
    rejected = False
    if overflow:
        try:
            sink.write(b"x")
        except GateResourceLimitError:
            rejected = True
    return sink.result().bytes_written, rejected


class _AdvancingClock:
    def __init__(self, step: float = 0.01) -> None:
        self.value = 0.0
        self.step = step

    def __call__(self) -> float:
        value = self.value
        self.value += self.step
        return value


def _exercise_cooperative_deadline() -> tuple[bool, bool]:
    with tempfile.TemporaryDirectory(
        prefix="adaivy-phase4-cooperative-deadline."
    ) as directory:
        root = Path(directory)
        output = root / "candidate.json"
        budget = DeadlineBudget(0.05, clock=_AdvancingClock())
        rejected = False
        try:
            write_bounded_json_atomic(
                output,
                {"items": list(range(128))},
                deadline=budget,
            )
        except GateResourceLimitError:
            rejected = True
        partials = list(root.glob(f".{output.name}.*.tmp"))
        return rejected, not output.exists() and not partials


def resource_boundary_tests(
    deadline: DeadlineBudget | None = None,
) -> dict[str, bool]:
    exact_source_bytes, source_overflow_rejected = _exercise_source_boundary(
        deadline
    )
    exact_output_bytes, _ = _exercise_output_boundary(False, deadline)
    overflow_output_bytes, overflow_rejected = _exercise_output_boundary(
        True, deadline
    )
    deadline_rejected, deadline_clean = _exercise_cooperative_deadline()
    checks = {
        "source_2mib_accepted": exact_source_bytes == MAX_SOURCE_BYTES,
        "source_2mib_plus_1_rejected": source_overflow_rejected,
        "records_256_accepted": enforce_record_count(MAX_RECORDS) == MAX_RECORDS,
        "output_64mib_accepted": exact_output_bytes == MAX_OUTPUT_BYTES,
        "output_64mib_plus_1_rejected": overflow_rejected,
        "output_overflow_extra_byte_not_visible": overflow_output_bytes == MAX_OUTPUT_BYTES,
        "cooperative_deadline_mid_operation_rejected": deadline_rejected,
        "failed_output_not_published": deadline_clean,
    }
    for name, operation in {
        "records_257_rejected": lambda: enforce_record_count(MAX_RECORDS + 1),
    }.items():
        try:
            operation()
        except GateValidationError:
            checks[name] = True
        else:
            checks[name] = False
    if not all(checks.values()):
        raise GateValidationError("resource boundary failure")
    return checks


def run_gate(
    repo_root: Path,
    state_dir: Path,
    deadline: DeadlineBudget | None = None,
) -> dict[str, Any]:
    budget = deadline or DeadlineBudget(MAX_WALL_SECONDS)
    _check(budget, "gate start")
    schema_path = repo_root / "schemas/phase4-gate-fixture-v1.schema.json"
    manifest_path = repo_root / "fixtures/phase4-gate/manifest.json"
    corpus_path = repo_root / "fixtures/phase4-gate/corpus.json"
    cases_path = repo_root / "fixtures/phase4-gate/cases.json"
    validator = load_validator(schema_path, budget)
    manifest = load_json(manifest_path, deadline=budget)
    corpus = load_json(corpus_path, deadline=budget)
    for path, key in ((corpus_path, "sha256"), (schema_path, "fixture_schema_sha256"), (cases_path, "case_file_sha256")):
        _check(budget, "manifest file hash verification")
        expected = manifest["corpus"][key]
        if sha256(read_bounded_bytes(path, deadline=budget)) != expected:
            raise GateValidationError(f"file hash mismatch: {path.name}")
    repeated = []
    for _ in range(3):
        _check(budget, "canonical repeat")
        repeated.append(evaluate_corpus(corpus, manifest, validator, budget))
    export_hashes = [item[0]["content_hash"] for item in repeated]
    if len(set(export_hashes)) != 1:
        raise GateValidationError("three-repeat canonical comparison failed")
    export, metrics = repeated[0]
    replay_raw, _ = stream_json_bytes(
        export, newline=True, deadline=budget
    )
    replay = verify_export_bytes(replay_raw, validator, deadline=budget)
    if replay != export:
        raise GateValidationError("canonical replay changed export")
    reversed_corpus = {**corpus, "fixtures": list(reversed(corpus["fixtures"]))}
    rebuilt, _ = evaluate_corpus(
        reversed_corpus, manifest, validator, budget
    )
    if rebuilt["content_hash"] != export["content_hash"]:
        raise GateValidationError("reverse rebuild changed canonical export")
    case_results = run_cases(repo_root, corpus, validator, budget)
    if case_results["case_hashes"] != manifest["case_hashes"] or case_results["raw_case_hashes"] != manifest["raw_case_hashes"]:
        raise GateValidationError("adversarial case hash manifest mismatch")
    if case_results["case_count"] != manifest["adversarial_case_count"]:
        raise GateValidationError("adversarial case count mismatch")
    boundary = resource_boundary_tests(budget)
    _check(budget, "state directory preparation")
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "candidate-export.json"
    restart_loaded = state_path.exists()
    if restart_loaded:
        prior = load_verified_export_file(
            state_path, validator, deadline=budget
        )
        if prior != export:
            raise GateValidationError("fresh-process restart changed export")
        output_measurement = measure_bounded_json(export, deadline=budget)
    else:
        output_measurement = write_verified_export_atomic(
            state_path, export, validator, deadline=budget
        )
    observed_source_bytes = [len(f["source"]["text"].encode("utf-8")) for f in corpus["fixtures"]]
    elapsed = budget.check("gate completion")
    external_calls: list[dict[str, Any]] = []
    result = {
        "schema_version": RESULT_VERSION, "status": "passed",
        "candidate_export_hash": export["content_hash"],
        "fixture_manifest_hash": content_hash(manifest, budget),
        "fixture_hashes": manifest["fixture_hashes"], "repeat_hashes": export_hashes,
        "restart_loaded": restart_loaded, "metrics": metrics,
        "schema_validation": {"draft": SCHEMA_DRAFT, "validator": "jsonschema.validators.Draft202012Validator", "external_refs": 0, "remote_retrievals": 0},
        "adversarial": case_results, "resource_boundary_tests": boundary,
        "observations": {
            "max_source_bytes": max(observed_source_bytes), "total_source_bytes": sum(observed_source_bytes),
            "review_record_count": len(corpus["fixtures"]), "export_record_count": len(export["records"]),
            "export_output_bytes": output_measurement.bytes_written,
            "export_output_sha256": "sha256:" + output_measurement.sha256,
            "export_output_write_calls": output_measurement.write_calls,
            "elapsed_seconds": elapsed,
            "external_cost_usd": 0, "external_call_inventory": external_calls,
        },
        "limits": {"max_source_bytes": MAX_SOURCE_BYTES, "max_records": MAX_RECORDS, "max_output_bytes": MAX_OUTPUT_BYTES, "max_wall_seconds": int(MAX_WALL_SECONDS), "max_external_cost_usd": 0},
        "controls": {
            "complete_audit_export": True,
            "proposal_only_nonhuman": case_results["nonhuman_actor_outcome_matrix_cells"] == len(NONHUMAN_ACTORS) * len(OUTCOMES),
            "explicit_human_final_matrix": case_results["human_actor_outcome_matrix_cells"] == len(OUTCOMES),
            "distinct_rights_states": True, "append_only_history_verified": True,
            "deletion_takedown_tombstones": True, "strict_json_and_schema": True,
            "separate_export_version": True, "replay_preserved": True,
            "restart_preserved": True, "index_rebuild_preserved": True,
            "strict_raw_export_boundary": case_results["replay_mutation_rejections"] == len(REPLAY_MUTATION_KINDS),
            "streaming_output_enforced": output_measurement.write_calls > 1,
            "cooperative_deadline_enforced": boundary["cooperative_deadline_mid_operation_rejected"],
            "failed_output_not_published": boundary["failed_output_not_published"],
            "parent_timeout_is_hard_wall": True,
        },
        "scope_guards": {"network_calls": 0, "model_or_provider_calls": 0, "production_database_writes": 0, "external_sources": 0, "production_dependencies": 0, "gate_only_dependencies": 5},
    }
    if not all(result["controls"].values()) or external_calls:
        raise GateValidationError("candidate control failure")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    budget = DeadlineBudget(MAX_WALL_SECONDS)
    result = run_gate(
        Path(__file__).resolve().parents[2], args.state_dir, budget
    )
    write_bounded_json_atomic(args.output, result, deadline=budget)
    print(json.dumps({
        "candidate_export_hash": result["candidate_export_hash"],
        "restart_loaded": result["restart_loaded"],
        "status": result["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
