"""Restart-safe Phase 5 persistence beside the accepted Phase 4A workspace."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from ..domain.entities import OpaqueId
from ..phase4a.workspace import Phase4Workspace
from . import EXPORT_VERSION, MAX_EXPORT_BYTES, MAX_INPUT_BYTES, MAX_RECORDS, SCHEMA_VERSION
from .serialization import canonical_bytes, content_hash, finalize, stable_id


class Phase5ValidationError(ValueError):
    pass


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise Phase5ValidationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def decode_json(data: bytes, *, max_bytes: int = MAX_INPUT_BYTES) -> dict[str, Any]:
    if len(data) > max_bytes:
        raise Phase5ValidationError("Phase 5 input exceeds the bounded byte limit")
    try:
        value = json.loads(
            data.decode("utf-8", "strict"), object_pairs_hook=_pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                Phase5ValidationError(f"non-finite JSON number: {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Phase5ValidationError("invalid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise Phase5ValidationError("Phase 5 input must be an object")
    return value


class Phase5Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.phase4 = Phase4Workspace(self.root)
        self.durable = self.phase4.durable
        self.connection = self.durable.connection
        self._migrate()
        self.verify_integrity()

    def __enter__(self) -> "Phase5Workspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.phase4.close()

    def _migration_files(self) -> tuple[Path, ...]:
        directory = Path(__file__).resolve().parents[3] / "migrations" / "phase5"
        files = tuple(sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql")))
        if not files:
            raise Phase5ValidationError("no Phase 5 migration found")
        return files

    def _migrate(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS phase5_schema_migrations "
            "(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)"
        )
        observed = {
            row["version"]: row["checksum"]
            for row in self.connection.execute("SELECT version,checksum FROM phase5_schema_migrations")
        }
        for path in self._migration_files():
            version = path.name.split("_", 1)[0]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if version in observed:
                if observed[version] != digest:
                    raise Phase5ValidationError(f"Phase 5 migration checksum drift: {path.name}")
                continue
            statements = [item.strip() for item in path.read_text("utf-8").split(";") if item.strip()]
            with self.durable.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO phase5_schema_migrations VALUES(?,?,?)",
                    (version, digest, "2026-08-20T00:00:00Z"),
                )

    @property
    def next_sequence(self) -> int:
        return int(self.connection.execute(
            "SELECT COALESCE(MAX(sequence),-1)+1 FROM phase5_records"
        ).fetchone()[0])

    def records(self, record_type: str | None = None) -> tuple[dict[str, Any], ...]:
        if record_type is None:
            rows = self.connection.execute("SELECT canonical_json FROM phase5_records ORDER BY sequence")
        else:
            rows = self.connection.execute(
                "SELECT canonical_json FROM phase5_records WHERE record_type=? ORDER BY sequence",
                (record_type,),
            )
        return tuple(json.loads(row[0]) for row in rows)

    def record(self, record_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT canonical_json FROM phase5_records WHERE record_id=?", (record_id,)
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return json.loads(row[0])

    def find(self, record_type: str, subject_id: str | None = None) -> tuple[dict[str, Any], ...]:
        return tuple(
            item for item in self.records(record_type)
            if subject_id is None or item["subject_id"] == subject_id
        )

    def append(
        self, *, record_type: str, subject_id: str, payload: Mapping[str, Any],
        recorded_at: str, record_id: str | None = None, event_type: str | None = None,
        event_idempotency_key: str | None = None, aggregate_id: str | None = None,
    ) -> dict[str, Any]:
        if not record_type or not subject_id or not recorded_at:
            raise Phase5ValidationError("record type, subject, and timestamp are required")
        identity = {"record_type": record_type, "subject_id": subject_id, "payload": payload}
        record_id = record_id or stable_id(record_type.replace("_", "-"), identity)
        record = finalize({
            "schema_version": SCHEMA_VERSION,
            "record_id": record_id,
            "record_type": record_type,
            "subject_id": subject_id,
            "sequence": self.next_sequence,
            "recorded_at": recorded_at,
            "payload": dict(payload),
        })
        encoded = canonical_bytes(record).decode("utf-8")
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT canonical_json FROM phase5_records WHERE record_id=?", (record_id,)
            ).fetchone()
            if existing is not None:
                old = json.loads(existing[0])
                candidate = dict(record)
                candidate["sequence"] = old["sequence"]
                candidate = finalize(candidate)
                if canonical_bytes(candidate).decode("utf-8") != existing[0]:
                    raise Phase5ValidationError("Phase 5 record identity cannot be rewritten")
                return old
            if self.next_sequence >= MAX_RECORDS:
                raise Phase5ValidationError("Phase 5 record limit exceeded")
            connection.execute(
                "INSERT INTO phase5_records VALUES(?,?,?,?,?,?,?,?)",
                (
                    record_id, record_type, SCHEMA_VERSION, subject_id, record["sequence"],
                    record["content_hash"], encoded, recorded_at,
                ),
            )
            if event_type is not None:
                if event_idempotency_key is None or aggregate_id is None:
                    raise Phase5ValidationError("semantic events require aggregate and idempotency identities")
                self.durable._insert_event(
                    connection, event_id=record_id, aggregate_id=aggregate_id,
                    event_type=event_type, payload_json=canonical_bytes(payload).decode("utf-8"),
                    now=recorded_at, idempotency_key=event_idempotency_key,
                )
        return record

    def rebuild_material_projection(self) -> tuple[dict[str, Any], ...]:
        events = {item["record_id"]: item for item in self.records("material_partial_result_event")}
        actions = self.records("material_partial_result_steering_action")
        lifecycles = self.records("material_partial_result_lifecycle")
        state: dict[str, dict[str, Any]] = {}
        for event_id, record in events.items():
            envelope = record["payload"]
            event = envelope["event"]
            state[event_id] = {
                "event_id": event_id, "objective_id": event["objective_id"],
                "run_id": event["run_id"], "current_validity": "valid",
                "latest_steering_action": None, "latest_lifecycle_id": None,
                "original_content_hash": envelope["content_hash"],
            }
        for record in actions:
            action = record["payload"]["action"]
            state[action["material_result_event_id"]]["latest_steering_action"] = action["action"]
        for record in lifecycles:
            lifecycle = record["payload"]["lifecycle"]
            item = state[lifecycle["material_result_event_id"]]
            item["current_validity"] = lifecycle["derived_state"]
            item["latest_lifecycle_id"] = lifecycle["lifecycle_id"]
        with self.durable.transaction() as connection:
            connection.execute("DELETE FROM phase5_material_projection")
            for event_id in sorted(state):
                item = state[event_id]
                connection.execute(
                    "INSERT INTO phase5_material_projection VALUES(?,?,?,?,?,?,?)",
                    (
                        item["event_id"], item["objective_id"], item["run_id"],
                        item["current_validity"], item["latest_steering_action"],
                        item["latest_lifecycle_id"], item["original_content_hash"],
                    ),
                )
        return tuple(state[key] for key in sorted(state))

    def material_results(self, run_id: str | None = None) -> tuple[dict[str, Any], ...]:
        query = "SELECT * FROM phase5_material_projection"
        params: tuple[Any, ...] = ()
        if run_id is not None:
            query += " WHERE run_id=?"
            params = (run_id,)
        query += " ORDER BY event_id"
        return tuple(dict(row) for row in self.connection.execute(query, params))

    def verify_integrity(self) -> None:
        self.phase4.verify_durable_integrity()
        rows = list(self.connection.execute("SELECT * FROM phase5_records ORDER BY sequence"))
        if [row["sequence"] for row in rows] != list(range(len(rows))):
            raise Phase5ValidationError("Phase 5 append sequence is incomplete or reordered")
        for row in rows:
            value = json.loads(row["canonical_json"])
            if (
                value.get("schema_version") != SCHEMA_VERSION
                or value.get("record_id") != row["record_id"]
                or value.get("record_type") != row["record_type"]
                or value.get("subject_id") != row["subject_id"]
                or value.get("sequence") != row["sequence"]
                or content_hash(value) != row["content_hash"]
                or value.get("content_hash") != row["content_hash"]
            ):
                raise Phase5ValidationError("Phase 5 durable record integrity failed")
        expected = self._project_value()
        actual = tuple(dict(row) for row in self.connection.execute(
            "SELECT * FROM phase5_material_projection ORDER BY event_id"
        ))
        if actual != expected:
            raise Phase5ValidationError("Phase 5 material-result projection drift")

    def _project_value(self) -> tuple[dict[str, Any], ...]:
        events = {item["record_id"]: item for item in self.records("material_partial_result_event")}
        state: dict[str, dict[str, Any]] = {}
        for event_id, record in events.items():
            envelope = record["payload"]
            event = envelope["event"]
            state[event_id] = {
                "event_id": event_id, "objective_id": event["objective_id"],
                "run_id": event["run_id"], "current_validity": "valid",
                "latest_steering_action": None, "latest_lifecycle_id": None,
                "original_content_hash": envelope["content_hash"],
            }
        for record in self.records("material_partial_result_steering_action"):
            action = record["payload"]["action"]
            state[action["material_result_event_id"]]["latest_steering_action"] = action["action"]
        for record in self.records("material_partial_result_lifecycle"):
            lifecycle = record["payload"]["lifecycle"]
            item = state[lifecycle["material_result_event_id"]]
            item["current_validity"] = lifecycle["derived_state"]
            item["latest_lifecycle_id"] = lifecycle["lifecycle_id"]
        return tuple(state[key] for key in sorted(state))

    @contextmanager
    def verified_snapshot(self) -> Iterator[tuple[dict[str, Any], ...]]:
        self.verify_integrity()
        yield self.records()

    def export_value(self) -> dict[str, Any]:
        with self.verified_snapshot() as records:
            value = {
                "schema_version": EXPORT_VERSION,
                "records": list(records),
                "material_results": list(self.material_results()),
            }
            return finalize(value)

    def export_bytes(self) -> bytes:
        data = canonical_bytes(self.export_value())
        if len(data) > MAX_EXPORT_BYTES:
            raise Phase5ValidationError("Phase 5 export exceeds the bounded byte limit")
        return data

    def save_verified_export(self, data: bytes) -> dict[str, Any]:
        value = decode_json(data, max_bytes=MAX_EXPORT_BYTES)
        if set(value) != {"schema_version", "records", "material_results", "content_hash"}:
            raise Phase5ValidationError("Phase 5 export has missing or unknown fields")
        if value["schema_version"] != EXPORT_VERSION or content_hash(value) != value["content_hash"]:
            raise Phase5ValidationError("Phase 5 export identity is invalid")
        with self.durable.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO phase5_verified_exports VALUES(?,?)",
                (value["content_hash"], canonical_bytes(value)),
            )
        return value
