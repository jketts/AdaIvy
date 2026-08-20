"""Durable, restart-safe workspace for the synthesis slice.

Wraps the Phase 6 workspace, so one SQLite file carries the Phase 2 durable
tables, Phase 4A rights and applicability records, Phase 5 adaptive-quantum
records, Phase 6 release records, and these synthesis records. Table names are
prefixed, and every earlier phase's integrity check runs before this one.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..phase6.workspace import Phase6Workspace
from . import EXPORT_VERSION, MAX_EXPORT_BYTES, MAX_INPUT_BYTES, MAX_RECORDS, SCHEMA_VERSION
from .serialization import (
    canonical_bytes,
    operational_export_hash,
    operational_record_hash,
    semantic_export_hash,
    semantic_record_hash,
    stable_id,
)
from .state import SynthesisValidationError

EXPORT_FIELDS = frozenset(
    {"schema_version", "records", "admission_projection", "content_hash", "operational_hash"}
)
RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "record_id",
        "record_type",
        "subject_id",
        "sequence",
        "recorded_at",
        "payload",
        "content_hash",
        "operational_hash",
    }
)
PROJECTION_FIELDS = frozenset(
    {
        "subject_id",
        "subject_kind",
        "current_admission",
        "admission_record_id",
        "influence_closure_id",
        "latest_invalidation_id",
    }
)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON keys rather than silently keeping the last."""
    seen: dict[str, Any] = {}
    for key, value in items:
        if key in seen:
            raise SynthesisValidationError(f"duplicate JSON key: {key}")
        seen[key] = value
    return seen


def _reject_constant(value: str) -> Any:
    raise SynthesisValidationError(f"non-finite JSON number is not permitted: {value}")


def decode_json(data: bytes, *, max_bytes: int = MAX_INPUT_BYTES) -> dict[str, Any]:
    """Strict decode: bounded, UTF-8, no duplicate keys, no NaN or Infinity."""
    if len(data) > max_bytes:
        raise SynthesisValidationError(f"input exceeds {max_bytes} bytes")
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SynthesisValidationError("input must be strict UTF-8") from error
    value = json.loads(decoded, object_pairs_hook=_pairs, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise SynthesisValidationError("input must be a JSON object")
    return value


def _object(value: object, *, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SynthesisValidationError(f"{label} must be an object")
    observed = set(value)
    if observed != fields:
        missing = sorted(fields - observed)
        unknown = sorted(observed - fields)
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unknown:
            detail.append(f"unknown {', '.join(unknown)}")
        raise SynthesisValidationError(f"{label} field set is not exact: {'; '.join(detail)}")
    return value


def _validate_graph_admission(payload: object, *, subject_id: str) -> None:
    """Validate the persisted projection input, not merely its JSON shape."""
    from .admission import AdmissionPolicy, ExclusionReason
    from .records import StateAxes, content_hash_value, identifier, text
    from .state import ExtractionFidelity, GraphAdmission, parse_enum

    fields = frozenset(
        {
            "admission_id",
            "subject_id",
            "subject_kind",
            "decision",
            "exclusion_reasons",
            "exclusion_detail",
            "policy",
            "evaluated_axes",
            "input_record_ids",
            "influence_closure_id",
            "admitting_actor_id",
            "admitting_authority",
        }
    )
    value = _object(payload, fields=fields, label="graph admission")
    if value["subject_id"] != subject_id:
        raise SynthesisValidationError("graph admission subject does not match its envelope")
    if value["subject_kind"] not in {"structured_result", "result_relation", "composition"}:
        raise SynthesisValidationError("graph admission has an unknown subject kind")
    identifier(value["admission_id"], field="admission_id")
    identifier(value["subject_id"], field="subject_id")
    identifier(value["admitting_actor_id"], field="admitting_actor_id")
    text(value["admitting_authority"], field="admitting_authority")
    content_hash_value(value["influence_closure_id"], field="influence_closure_id")

    policy_value = _object(
        value["policy"],
        fields=frozenset(
            {
                "view_id",
                "policy_version",
                "required_applicability",
                "required_fidelity",
                "minimum_documented_warrant",
                "permitted_warrants",
            }
        ),
        label="admission policy",
    )
    policy = AdmissionPolicy.from_value(policy_value)
    axes = StateAxes.from_value(value["evaluated_axes"])
    decision = parse_enum(GraphAdmission, value["decision"], field="decision")
    if decision not in {
        GraphAdmission.ADMITTED_UNDER_POLICY,
        GraphAdmission.EXCLUDED_UNDER_POLICY,
    }:
        raise SynthesisValidationError("a graph admission decision must be admitted or excluded")

    raw_reasons = value["exclusion_reasons"]
    raw_detail = value["exclusion_detail"]
    raw_inputs = value["input_record_ids"]
    for label, items in (
        ("exclusion_reasons", raw_reasons),
        ("exclusion_detail", raw_detail),
        ("input_record_ids", raw_inputs),
    ):
        if isinstance(items, (str, bytes)) or not isinstance(items, list):
            raise SynthesisValidationError(f"{label} must be a list")
    reasons = tuple(text(item, field="exclusion_reasons[]") for item in raw_reasons)
    if len(set(reasons)) != len(reasons) or set(reasons) - ExclusionReason.ALL:
        raise SynthesisValidationError("graph admission exclusion reasons are invalid")
    for item in raw_detail:
        text(item, field="exclusion_detail[]")
    inputs = tuple(identifier(item, field="input_record_ids[]") for item in raw_inputs)
    if not inputs:
        raise SynthesisValidationError("graph admission must cite at least one input record")

    required_reasons: set[str] = set()
    if axes.graph_admission is GraphAdmission.INVALIDATED_BY_LATER_RECORD:
        required_reasons.add(ExclusionReason.ALREADY_INVALIDATED)
    if axes.source_applicability is not policy.required_applicability:
        required_reasons.add(ExclusionReason.APPLICABILITY_NOT_EFFECTIVE)
    if axes.extraction_fidelity is not policy.required_fidelity:
        required_reasons.add(ExclusionReason.EXTRACTION_NOT_CHECKED)
    if axes.mathematical_warrant not in policy.permitted_warrants:
        required_reasons.add(ExclusionReason.WARRANT_NOT_PERMITTED)
    if not required_reasons.issubset(reasons):
        raise SynthesisValidationError("graph admission omits a mandatory exclusion reason")
    if decision is GraphAdmission.ADMITTED_UNDER_POLICY and reasons:
        raise SynthesisValidationError("an admitted graph subject cannot carry exclusion reasons")
    if decision is GraphAdmission.ADMITTED_UNDER_POLICY and required_reasons:
        raise SynthesisValidationError("unqualified axes cannot be admitted under policy")
    if decision is GraphAdmission.EXCLUDED_UNDER_POLICY and not reasons:
        raise SynthesisValidationError("an excluded graph subject requires an exclusion reason")

    expected_id = stable_id(
        "admission",
        {
            "subject_id": subject_id,
            "policy": policy.value(),
            "axes": axes.value(),
            "inputs": sorted(inputs),
            "influence_closure_id": value["influence_closure_id"],
            "decision": decision.value,
            "reasons": sorted(reasons),
        },
    )
    if value["admission_id"] != expected_id:
        raise SynthesisValidationError("graph admission identity does not match its semantic inputs")


def _validate_record_payload(record_type: str, payload: object, *, subject_id: str) -> None:
    if record_type == "graph_admission":
        _validate_graph_admission(payload, subject_id=subject_id)
        return
    if record_type == "captured_proposal":
        from .proposals import CapturedProposal

        captured = CapturedProposal.from_value(payload)
        if captured.proposal_id != subject_id:
            raise SynthesisValidationError("captured proposal subject does not match its identity")
        return
    if record_type == "influence_invalidation":
        from .influence import InfluencedKind, TriggerKind
        from .records import identifier
        from .state import parse_enum

        fields = frozenset(
            {
                "invalidation_id",
                "trigger_id",
                "node_id",
                "node_kind",
                "trigger_kind",
                "source_id",
                "influence_path",
                "replacement_node_id",
                "graph_admission",
            }
        )
        value = _object(payload, fields=fields, label="influence invalidation")
        if value["node_id"] != subject_id:
            raise SynthesisValidationError("invalidation subject does not match its envelope")
        if value["graph_admission"] != "invalidated_by_later_record":
            raise SynthesisValidationError("invalidation must close graph admission")
        identifier(value["invalidation_id"], field="invalidation_id")
        identifier(value["trigger_id"], field="trigger_id")
        identifier(value["node_id"], field="node_id")
        identifier(value["source_id"], field="source_id")
        parse_enum(InfluencedKind, value["node_kind"], field="node_kind")
        parse_enum(TriggerKind, value["trigger_kind"], field="trigger_kind")
        path = value["influence_path"]
        if isinstance(path, (str, bytes)) or not isinstance(path, list) or len(path) < 2:
            raise SynthesisValidationError("invalidation influence_path must be a nontrivial list")
        for item in path:
            identifier(item, field="influence_path[]")
        if path[0] != subject_id or path[-1] != value["source_id"]:
            raise SynthesisValidationError("invalidation influence path has inconsistent endpoints")
        replacement = value["replacement_node_id"]
        if replacement is not None:
            identifier(replacement, field="replacement_node_id")
        expected = stable_id(
            "invalidation",
            {"trigger_id": value["trigger_id"], "node_id": value["node_id"]},
        )
        if value["invalidation_id"] != expected:
            raise SynthesisValidationError("invalidation identity does not match its inputs")
        return
    raise SynthesisValidationError(f"unsupported synthesis record type: {record_type}")


def _payload_record_id(record_type: str, payload: Mapping[str, Any]) -> str:
    fields = {
        "captured_proposal": "proposal_id",
        "graph_admission": "admission_id",
        "influence_invalidation": "invalidation_id",
    }
    return str(payload[fields[record_type]])


def _project_records(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for row in records:
        payload = row["payload"]
        if row["record_type"] == "graph_admission":
            state[payload["subject_id"]] = {
                "subject_id": payload["subject_id"],
                "subject_kind": payload["subject_kind"],
                "current_admission": payload["decision"],
                "admission_record_id": row["record_id"],
                "influence_closure_id": payload["influence_closure_id"],
                "latest_invalidation_id": None,
            }
        elif row["record_type"] == "influence_invalidation":
            subject = payload["node_id"]
            if subject in state:
                state[subject] = {
                    **state[subject],
                    "current_admission": "invalidated_by_later_record",
                    "latest_invalidation_id": row["record_id"],
                }
    return state


class SynthesisWorkspace:
    """Append-only synthesis record store with deterministic export."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.phase6 = Phase6Workspace(self.root)
        self.durable = self.phase6.durable
        self.connection = self.durable.connection
        try:
            self._migrate()
            self.verify_integrity()
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> SynthesisWorkspace:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    def close(self) -> None:
        self.phase6.close()

    # --- migrations ---------------------------------------------------------
    def _migration_files(self) -> tuple[Path, ...]:
        directory = Path(__file__).resolve().parents[3] / "migrations" / "synthesis"
        files = tuple(sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql")))
        if not files:
            raise SynthesisValidationError("no synthesis migration found")
        return files

    def _migrate(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS synthesis_schema_migrations "
            "(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)"
        )
        observed = {
            row["version"]: row["checksum"]
            for row in self.connection.execute(
                "SELECT version,checksum FROM synthesis_schema_migrations"
            )
        }
        for path in self._migration_files():
            version = path.name.split("_", 1)[0]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if version in observed:
                if observed[version] != digest:
                    raise SynthesisValidationError(
                        f"synthesis migration checksum drift: {path.name}"
                    )
                continue
            statements = [item.strip() for item in path.read_text("utf-8").split(";") if item.strip()]
            with self.durable.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO synthesis_schema_migrations VALUES(?,?,?)",
                    # A frozen instant keeps the database byte-reproducible.
                    (version, digest, "2026-08-20T00:00:00Z"),
                )

    # --- append and read ---------------------------------------------------
    @property
    def next_sequence(self) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(sequence),-1)+1 AS next FROM synthesis_records"
        ).fetchone()
        return int(row["next"])

    def records(self, record_type: str | None = None) -> tuple[dict[str, Any], ...]:
        if record_type is None:
            rows = self.connection.execute(
                "SELECT canonical_json FROM synthesis_records ORDER BY sequence"
            )
        else:
            rows = self.connection.execute(
                "SELECT canonical_json FROM synthesis_records WHERE record_type=? ORDER BY sequence",
                (record_type,),
            )
        return tuple(json.loads(row["canonical_json"]) for row in rows)

    def record(self, record_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT canonical_json FROM synthesis_records WHERE record_id=?", (record_id,)
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return json.loads(row["canonical_json"])

    def append(
        self,
        *,
        record_type: str,
        subject_id: str,
        payload: Mapping[str, Any],
        recorded_at: str,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        """Append one record. An existing identity must carry identical content."""
        if not isinstance(record_type, str) or not record_type:
            raise SynthesisValidationError("record_type must be a non-empty string")
        if not isinstance(subject_id, str) or not subject_id:
            raise SynthesisValidationError("subject_id must be a non-empty string")
        if not isinstance(recorded_at, str) or not recorded_at:
            raise SynthesisValidationError("recorded_at must be a non-empty string")
        _validate_record_payload(record_type, payload, subject_id=subject_id)
        expected_record_id = _payload_record_id(record_type, payload)
        if record_id is not None and record_id != expected_record_id:
            raise SynthesisValidationError("record identity does not match its validated payload")
        resolved_id = expected_record_id
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT canonical_json,sequence FROM synthesis_records WHERE record_id=?",
                (resolved_id,),
            ).fetchone()
            if record_type == "graph_admission":
                for input_id in payload["input_record_ids"]:
                    input_row = connection.execute(
                        "SELECT 1 FROM synthesis_records WHERE record_id=?", (input_id,)
                    ).fetchone()
                    if input_row is None:
                        raise SynthesisValidationError(
                            f"graph admission cites unknown input record: {input_id}"
                        )
            sequence = self.next_sequence if existing is None else int(existing["sequence"])
            value: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "record_id": resolved_id,
                "record_type": record_type,
                "subject_id": subject_id,
                "sequence": sequence,
                "recorded_at": recorded_at,
                "payload": dict(payload),
            }
            # Semantic first, then operational over the completed record, so the
            # operational hash covers the semantic one. Mirrors Phase 3B.
            value["content_hash"] = semantic_record_hash(value)
            value["operational_hash"] = operational_record_hash(value)
            canonical = canonical_bytes(value).decode("utf-8")
            if existing is not None:
                if existing["canonical_json"] != canonical:
                    raise SynthesisValidationError(
                        f"synthesis record identity cannot be rewritten: {resolved_id}"
                    )
                return value
            if sequence >= MAX_RECORDS:
                raise SynthesisValidationError(f"synthesis record ceiling {MAX_RECORDS} reached")
            connection.execute(
                "INSERT INTO synthesis_records VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    resolved_id,
                    record_type,
                    SCHEMA_VERSION,
                    subject_id,
                    sequence,
                    value["content_hash"],
                    value["operational_hash"],
                    canonical,
                    recorded_at,
                ),
            )
        return value

    # --- projection --------------------------------------------------------
    def _project_value(self) -> dict[str, dict[str, Any]]:
        """Rebuild the current admission view from the immutable record log."""
        return _project_records(self.records())

    def rebuild_admission_projection(self) -> dict[str, dict[str, Any]]:
        state = self._project_value()
        with self.durable.transaction() as connection:
            connection.execute("DELETE FROM synthesis_admission_projection")
            for key in sorted(state):
                entry = state[key]
                connection.execute(
                    "INSERT INTO synthesis_admission_projection VALUES(?,?,?,?,?,?)",
                    (
                        entry["subject_id"],
                        entry["subject_kind"],
                        entry["current_admission"],
                        entry["admission_record_id"],
                        entry["influence_closure_id"],
                        entry["latest_invalidation_id"],
                    ),
                )
        return state

    def admission_projection(self) -> tuple[dict[str, Any], ...]:
        rows = self.connection.execute(
            "SELECT * FROM synthesis_admission_projection ORDER BY subject_id"
        )
        return tuple(dict(row) for row in rows)

    # --- integrity and export ---------------------------------------------
    def verify_integrity(self) -> None:
        self.phase6.verify_integrity()
        rows = list(
            self.connection.execute(
                "SELECT record_id,record_type,schema_version,subject_id,sequence,content_hash,"
                "operational_hash,canonical_json,recorded_at FROM synthesis_records ORDER BY sequence"
            )
        )
        seen_ids: set[str] = set()
        for index, row in enumerate(rows):
            if int(row["sequence"]) != index:
                raise SynthesisValidationError("synthesis record sequence is not contiguous")
            value = json.loads(row["canonical_json"])
            _object(value, fields=RECORD_FIELDS, label="synthesis record")
            for column in (
                "record_id",
                "record_type",
                "schema_version",
                "subject_id",
                "recorded_at",
            ):
                if value[column] != row[column]:
                    raise SynthesisValidationError(f"synthesis record {column} drift")
            if int(value["sequence"]) != int(row["sequence"]):
                raise SynthesisValidationError("synthesis record sequence drift")
            _validate_record_payload(
                value["record_type"], value["payload"], subject_id=value["subject_id"]
            )
            if value["record_id"] != _payload_record_id(value["record_type"], value["payload"]):
                raise SynthesisValidationError("synthesis record identity does not match its payload")
            if value["record_type"] == "graph_admission":
                unknown_inputs = set(value["payload"]["input_record_ids"]) - seen_ids
                if unknown_inputs:
                    raise SynthesisValidationError(
                        "graph admission cites unknown or later input records"
                    )
            recomputed = semantic_record_hash(value)
            if recomputed != row["content_hash"] or recomputed != value["content_hash"]:
                raise SynthesisValidationError("synthesis record semantic hash drift")
            operational = operational_record_hash(value)
            if operational != row["operational_hash"] or operational != value["operational_hash"]:
                raise SynthesisValidationError("synthesis record operational hash drift")
            seen_ids.add(value["record_id"])
        projected = self._project_value()
        stored = {entry["subject_id"]: entry for entry in self.admission_projection()}
        if {key: dict(value) for key, value in stored.items()} != projected:
            raise SynthesisValidationError("synthesis admission projection drift")

    @contextmanager
    def verified_snapshot(self):
        self.verify_integrity()
        yield self.records()

    def export_value(self) -> dict[str, Any]:
        with self.verified_snapshot() as records:
            value: dict[str, Any] = {
                "schema_version": EXPORT_VERSION,
                "records": list(records),
                "admission_projection": [dict(item) for item in self.admission_projection()],
            }
            value["content_hash"] = semantic_export_hash(value)
            value["operational_hash"] = operational_export_hash(value)
            return value

    def export_bytes(self) -> bytes:
        data = canonical_bytes(self.export_value())
        if len(data) > MAX_EXPORT_BYTES:
            raise SynthesisValidationError(f"export exceeds {MAX_EXPORT_BYTES} bytes")
        return data

    def save_verified_export(self, data: bytes) -> dict[str, Any]:
        value = verify_export_bytes(data)
        with self.durable.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO synthesis_verified_exports VALUES(?,?)",
                (value["content_hash"], data),
            )
        return value


def verify_export_bytes(data: bytes) -> dict[str, Any]:
    """Strictly verify a canonical, self-contained synthesis export."""
    value = decode_json(data, max_bytes=MAX_EXPORT_BYTES)
    _object(value, fields=EXPORT_FIELDS, label="synthesis export")
    if data != canonical_bytes(value):
        raise SynthesisValidationError("synthesis export is not canonical JSON")
    if value["schema_version"] != EXPORT_VERSION:
        raise SynthesisValidationError("synthesis export schema version mismatch")
    if semantic_export_hash(value) != value["content_hash"]:
        raise SynthesisValidationError("synthesis export semantic hash mismatch")
    if operational_export_hash(value) != value["operational_hash"]:
        raise SynthesisValidationError("synthesis export operational hash mismatch")

    records = value["records"]
    projection = value["admission_projection"]
    if not isinstance(records, list) or not isinstance(projection, list):
        raise SynthesisValidationError("synthesis export records and projection must be lists")
    if len(records) > MAX_RECORDS:
        raise SynthesisValidationError(f"synthesis record ceiling {MAX_RECORDS} exceeded")
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    for sequence, item in enumerate(records):
        record = _object(item, fields=RECORD_FIELDS, label="synthesis record")
        if record["schema_version"] != SCHEMA_VERSION:
            raise SynthesisValidationError("synthesis record schema version mismatch")
        if isinstance(record["sequence"], bool) or record["sequence"] != sequence:
            raise SynthesisValidationError("synthesis record sequence is not contiguous")
        if not isinstance(record["record_id"], str) or record["record_id"] in seen_ids:
            raise SynthesisValidationError("synthesis record identity is invalid or duplicated")
        if record["content_hash"] in seen_hashes:
            raise SynthesisValidationError("synthesis record semantic hash is duplicated")
        _validate_record_payload(
            record["record_type"], record["payload"], subject_id=record["subject_id"]
        )
        if record["record_id"] != _payload_record_id(record["record_type"], record["payload"]):
            raise SynthesisValidationError("record identity does not match its validated payload")
        if record["record_type"] == "graph_admission":
            unknown_inputs = set(record["payload"]["input_record_ids"]) - seen_ids
            if unknown_inputs:
                raise SynthesisValidationError(
                    "graph admission cites unknown or later input records: "
                    + ", ".join(sorted(unknown_inputs))
                )
        if semantic_record_hash(record) != record["content_hash"]:
            raise SynthesisValidationError("synthesis record semantic hash mismatch")
        if operational_record_hash(record) != record["operational_hash"]:
            raise SynthesisValidationError("synthesis record operational hash mismatch")
        seen_ids.add(record["record_id"])
        seen_hashes.add(record["content_hash"])

    observed_projection: dict[str, dict[str, Any]] = {}
    for item in projection:
        entry = _object(item, fields=PROJECTION_FIELDS, label="admission projection entry")
        subject = entry["subject_id"]
        if not isinstance(subject, str) or subject in observed_projection:
            raise SynthesisValidationError("admission projection subject is invalid or duplicated")
        observed_projection[subject] = dict(entry)
    expected_projection = _project_records(records)
    if observed_projection != expected_projection:
        raise SynthesisValidationError("synthesis admission projection is not derived from records")
    return value


__all__ = [
    "EXPORT_FIELDS",
    "PROJECTION_FIELDS",
    "RECORD_FIELDS",
    "SynthesisWorkspace",
    "decode_json",
    "verify_export_bytes",
]
