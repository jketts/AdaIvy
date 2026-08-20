"""Append-only Phase 4B metadata layered over the Phase 4A SQLite workspace."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from ..phase4a.workspace import Phase4Workspace
from .interchange import (
    Phase4BValidationError, build_export, project_records, validate_operational, validate_payload,
    validate_record, verify_export_bytes,
)
from .records import (
    MAX_EXPORT_BYTES, MAX_RECORDS, RecordType, SCHEMA_VERSION,
)
from .replay_artifacts import build_artifact, validate_artifact, validate_artifact_owner
from .serialization import (
    canonical_bytes, expected_record_id, operational_record_hash, semantic_record_hash,
)


class Phase4BWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.phase4a = Phase4Workspace(self.root)
        self.durable = self.phase4a.durable
        self.connection = self.durable.connection
        try:
            self._migrate()
            self.verify_integrity()
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> "Phase4BWorkspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.phase4a.close()

    def _migration_files(self) -> tuple[Path, ...]:
        directory = Path(__file__).resolve().parents[3] / "migrations" / "phase4b"
        files = tuple(sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql")))
        if not files:
            raise Phase4BValidationError("no Phase 4B migration found")
        return files

    def _expected_migrations(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (path.name.split("_", 1)[0], hashlib.sha256(path.read_bytes()).hexdigest())
            for path in self._migration_files()
        )

    def _verify_migration_ledger(self, *, allow_prefix: bool = False) -> None:
        expected = self._expected_migrations()
        rows = tuple(
            (row["version"], row["checksum"])
            for row in self.connection.execute(
                "SELECT version,checksum FROM phase4b_schema_migrations ORDER BY rowid"
            )
        )
        permitted = expected[: len(rows)] if allow_prefix else expected
        if rows != permitted:
            raise Phase4BValidationError("Phase 4B migration ledger is missing, reordered, or drifted")

    def _migrate(self) -> None:
        tables = {
            row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "phase4b_schema_migrations" not in tables and any(
            name.startswith("phase4b_") for name in tables
        ):
            raise Phase4BValidationError("Phase 4B tables exist without a migration ledger")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS phase4b_schema_migrations "
            "(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)"
        )
        self._verify_migration_ledger(allow_prefix=True)
        observed = {
            row["version"]: row["checksum"]
            for row in self.connection.execute(
                "SELECT version,checksum FROM phase4b_schema_migrations"
            )
        }
        for path in self._migration_files():
            version = path.name.split("_", 1)[0]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if version in observed:
                if observed[version] != digest:
                    raise Phase4BValidationError(f"Phase 4B migration checksum drift: {path.name}")
                continue
            statements: list[str] = []
            pending = ""
            for line in path.read_text("utf-8").splitlines(keepends=True):
                pending += line
                if sqlite3.complete_statement(pending):
                    statements.append(pending.strip())
                    pending = ""
            if pending.strip():
                raise Phase4BValidationError(f"incomplete migration SQL: {path.name}")
            with self.durable.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO phase4b_schema_migrations VALUES(?,?,?)",
                    (version, digest, "2026-08-20T00:00:00Z"),
                )
        self._verify_migration_ledger()

    @property
    def next_sequence(self) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(sequence),-1)+1 AS value FROM phase4b_records"
        ).fetchone()
        return int(row["value"])

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            json.loads(row["canonical_json"])
            for row in self.connection.execute(
                "SELECT canonical_json FROM phase4b_records ORDER BY sequence"
            )
        )

    def replay_artifacts(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            json.loads(row["canonical_json"])
            for row in self.connection.execute(
                "SELECT canonical_json FROM phase4b_replay_artifacts ORDER BY sequence"
            )
        )

    def pending_publications(self) -> tuple[dict[str, str], ...]:
        """Return the bounded crash-recovery journal; it is not audit evidence."""
        return tuple(
            dict(row) for row in self.connection.execute(
                "SELECT source_id,artifact_hash,content_object_id,recorded_at "
                "FROM phase4b_pending_publications ORDER BY source_id"
            )
        )

    def begin_publication(
        self, *, source_id: str, artifact_hash: str,
        content_object_id: str, recorded_at: str,
    ) -> None:
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT artifact_hash,content_object_id,recorded_at "
                "FROM phase4b_pending_publications WHERE source_id=?", (source_id,)
            ).fetchone()
            expected = (artifact_hash, content_object_id, recorded_at)
            if existing is not None and tuple(existing) != expected:
                raise Phase4BValidationError("conflicting Phase 4B publication is pending")
            connection.execute(
                "INSERT OR IGNORE INTO phase4b_pending_publications VALUES(?,?,?,?)",
                (source_id, artifact_hash, content_object_id, recorded_at),
            )

    def finish_publication(self, source_id: str) -> None:
        with self.durable.transaction() as connection:
            connection.execute(
                "DELETE FROM phase4b_pending_publications WHERE source_id=?", (source_id,)
            )

    def record(self, record_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT canonical_json FROM phase4b_records WHERE record_id=?", (record_id,)
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return json.loads(row["canonical_json"])

    @staticmethod
    def default_operational() -> dict[str, Any]:
        return {
            "attempt_number": 1, "elapsed_milliseconds": 0, "exit_status": None,
            "stdout_hash": None, "stderr_hash": None, "stdout_bytes": 0,
            "stderr_bytes": 0,
        }

    def _build_record(
        self, *, record_type: str, subject_id: str, payload: Mapping[str, Any],
        recorded_at: str, operational: Mapping[str, Any], sequence: int,
        record_id: str | None,
    ) -> dict[str, Any]:
        validate_payload(record_type, subject_id, payload)
        validate_operational(operational)
        resolved = expected_record_id(record_type, subject_id, payload)
        if record_id is not None and record_id != resolved:
            raise Phase4BValidationError("provided record ID differs from semantic identity")
        value: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION, "record_id": resolved,
            "record_type": record_type, "subject_id": subject_id, "sequence": sequence,
            "recorded_at": recorded_at, "payload": dict(payload),
            "operational": dict(operational),
        }
        value["content_hash"] = semantic_record_hash(value)
        value["operational_hash"] = operational_record_hash(value)
        validate_record(value, expected_sequence=sequence)
        return value

    def append(
        self, *, record_type: str | RecordType, subject_id: str,
        payload: Mapping[str, Any], recorded_at: str,
        operational: Mapping[str, Any] | None = None, record_id: str | None = None,
        replay_artifacts: tuple[tuple[str, Mapping[str, Any]], ...] = (),
    ) -> dict[str, Any]:
        kind = record_type.value if isinstance(record_type, RecordType) else record_type
        candidate_id = expected_record_id(kind, subject_id, payload)
        existing = self.connection.execute(
            "SELECT canonical_json FROM phase4b_records WHERE record_id=?", (candidate_id,)
        ).fetchone()
        sequence = self.next_sequence if existing is None else int(json.loads(existing[0])["sequence"])
        value = self._build_record(
            record_type=kind, subject_id=subject_id, payload=payload,
            recorded_at=recorded_at, operational=operational or self.default_operational(),
            sequence=sequence, record_id=record_id,
        )
        if existing is not None:
            stored = json.loads(existing["canonical_json"])
            if stored["content_hash"] != value["content_hash"]:
                raise Phase4BValidationError("record identity cannot be rewritten")
            if replay_artifacts:
                observed = [
                    json.loads(row["canonical_json"])
                    for row in self.connection.execute(
                        "SELECT canonical_json FROM phase4b_replay_artifacts WHERE owner_record_id=? ORDER BY sequence",
                        (candidate_id,),
                    )
                ]
                expected = [
                    build_artifact(candidate_id, artifact_type, artifact_payload, sequence=item["sequence"])
                    for item, (artifact_type, artifact_payload) in zip(observed, replay_artifacts)
                ]
                if len(observed) != len(replay_artifacts) or observed != expected:
                    raise Phase4BValidationError("record replay artifacts cannot be rewritten")
            return stored
        with self.durable.transaction() as connection:
            self._insert_verified(connection, value)
            for artifact_type, artifact_payload in replay_artifacts:
                self._insert_artifact(
                    connection,
                    build_artifact(
                        candidate_id, artifact_type, artifact_payload,
                        sequence=self._next_artifact_sequence(connection),
                    ),
                )
            self._rebuild_projection_with(connection)
        return value

    @staticmethod
    def _next_artifact_sequence(connection: Any) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence),-1)+1 AS value FROM phase4b_replay_artifacts"
        ).fetchone()
        return int(row["value"])

    def _insert_artifact(self, connection: Any, value: Mapping[str, Any]) -> None:
        try:
            validate_artifact(value, expected_sequence=self._next_artifact_sequence(connection))
        except ValueError as error:
            raise Phase4BValidationError(str(error)) from error
        owner_row = connection.execute(
            "SELECT canonical_json FROM phase4b_records WHERE record_id=?", (value["owner_record_id"],)
        ).fetchone()
        if owner_row is None:
            raise Phase4BValidationError("replay artifact owner is unknown")
        try:
            all_records = {
                row["record_id"]: json.loads(row["canonical_json"])
                for row in connection.execute("SELECT record_id,canonical_json FROM phase4b_records")
            }
            validate_artifact_owner(
                value, json.loads(owner_row["canonical_json"]), all_records
            )
        except ValueError as error:
            raise Phase4BValidationError(str(error)) from error
        connection.execute(
            "INSERT INTO phase4b_replay_artifacts VALUES(?,?,?,?,?,?,?)",
            (
                value["artifact_id"], value["owner_record_id"], value["artifact_type"],
                value["schema_version"], value["content_hash"],
                canonical_bytes(value).decode("utf-8"), value["sequence"],
            ),
        )

    def _insert_verified(self, connection: Any, value: Mapping[str, Any]) -> None:
        validate_record(value)
        if int(value["sequence"]) != self.next_sequence:
            raise Phase4BValidationError("append sequence is not next")
        if self.next_sequence >= MAX_RECORDS:
            raise Phase4BValidationError("Phase 4B record ceiling reached")
        for predecessor in value["payload"].get("predecessor_record_ids", []):
            if connection.execute(
                "SELECT 1 FROM phase4b_records WHERE record_id=?", (predecessor,)
            ).fetchone() is None:
                raise Phase4BValidationError("record predecessor is unknown or not yet appended")
        if value["record_type"] == RecordType.INVALIDATION.value:
            for target in value["payload"]["affected_record_ids"]:
                row = connection.execute(
                    "SELECT record_type FROM phase4b_records WHERE record_id=?", (target,)
                ).fetchone()
                if row is None or row["record_type"] == RecordType.INVALIDATION.value:
                    raise Phase4BValidationError("invalidation target is unknown or not a candidate")
        canonical = canonical_bytes(value).decode("utf-8")
        connection.execute(
            "INSERT INTO phase4b_records VALUES(?,?,?,?,?,?,?,?,?)",
            (
                value["record_id"], value["record_type"], SCHEMA_VERSION,
                value["subject_id"], value["sequence"], value["content_hash"],
                value["operational_hash"], canonical, value["recorded_at"],
            ),
        )
        connection.execute(
            "INSERT INTO phase4b_events(event_id,record_id,event_type,content_hash,operational_hash) "
            "VALUES(?,?,?,?,?)",
            (
                f"event.{value['record_id']}", value["record_id"],
                "candidate_record_appended", value["content_hash"], value["operational_hash"],
            ),
        )

    def _rebuild_projection_with(self, connection: Any, *, reverse: bool = False) -> list[dict[str, Any]]:
        records = self.records()
        state = project_records(tuple(reversed(records)) if reverse else records)
        connection.execute("DELETE FROM phase4b_candidate_projection")
        for item in state:
            connection.execute(
                "INSERT INTO phase4b_candidate_projection VALUES(?,?,?,?,?)",
                (
                    item["record_id"], item["subject_id"], item["record_type"],
                    item["current_state"], item["latest_invalidation_id"],
                ),
            )
        return state

    def rebuild_projection(self, *, reverse: bool = False) -> list[dict[str, Any]]:
        with self.durable.transaction() as connection:
            return self._rebuild_projection_with(connection, reverse=reverse)

    def projection(self) -> list[dict[str, Any]]:
        return [
            dict(row) for row in self.connection.execute(
                "SELECT * FROM phase4b_candidate_projection ORDER BY record_id"
            )
        ]

    def verify_integrity(self) -> None:
        self.phase4a.verify_durable_integrity()
        self._verify_migration_ledger()
        required = {
            "phase4b_records", "phase4b_events", "phase4b_candidate_projection",
            "phase4b_verified_exports", "phase4b_schema_migrations",
            "phase4b_pending_publications",
            "phase4b_replay_artifacts",
        }
        existing = {
            row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not required.issubset(existing):
            raise Phase4BValidationError("Phase 4B durable schema is incomplete")
        expected_columns = {
            "phase4b_records": (
                "record_id", "record_type", "schema_version", "subject_id", "sequence",
                "content_hash", "operational_hash", "canonical_json", "recorded_at",
            ),
            "phase4b_events": (
                "sequence", "event_id", "record_id", "event_type", "content_hash",
                "operational_hash",
            ),
            "phase4b_candidate_projection": (
                "record_id", "subject_id", "record_type", "current_state",
                "latest_invalidation_id",
            ),
            "phase4b_verified_exports": (
                "content_hash", "operational_hash", "canonical_json",
            ),
            "phase4b_pending_publications": (
                "source_id", "artifact_hash", "content_object_id", "recorded_at",
            ),
            "phase4b_replay_artifacts": (
                "artifact_id", "owner_record_id", "artifact_type", "schema_version",
                "content_hash", "canonical_json", "sequence",
            ),
        }
        for table, columns in expected_columns.items():
            observed = tuple(
                row["name"] for row in self.connection.execute(f"PRAGMA table_info({table})")
            )
            if observed != columns:
                raise Phase4BValidationError(f"Phase 4B durable columns differ for {table}")
        triggers = {
            row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name GLOB 'phase4b_*'"
            )
        }
        if triggers != {
            "phase4b_records_no_update", "phase4b_records_no_delete",
            "phase4b_events_no_update", "phase4b_events_no_delete",
            "phase4b_replay_artifacts_no_update", "phase4b_replay_artifacts_no_delete",
        }:
            raise Phase4BValidationError("Phase 4B append-only triggers differ")
        records = self.records()
        for sequence, value in enumerate(records):
            validate_record(value, expected_sequence=sequence)
            row = self.connection.execute(
                "SELECT * FROM phase4b_records WHERE record_id=?", (value["record_id"],)
            ).fetchone()
            for field in (
                "record_id", "record_type", "schema_version", "subject_id", "sequence",
                "content_hash", "operational_hash", "recorded_at",
            ):
                if row[field] != value[field]:
                    raise Phase4BValidationError(f"durable {field} differs from canonical record")
            if row["canonical_json"].encode("utf-8") != canonical_bytes(value):
                raise Phase4BValidationError("durable record JSON is noncanonical")
        expected_events = [
            (
                f"event.{item['record_id']}", item["record_id"],
                "candidate_record_appended", item["content_hash"], item["operational_hash"],
            )
            for item in records
        ]
        observed_events = [
            tuple(row) for row in self.connection.execute(
                "SELECT event_id,record_id,event_type,content_hash,operational_hash "
                "FROM phase4b_events ORDER BY sequence"
            )
        ]
        if observed_events != expected_events:
            raise Phase4BValidationError("Phase 4B event log differs from record log")
        if self.projection() != project_records(records):
            raise Phase4BValidationError("Phase 4B projection drift")
        records_by_id = {item["record_id"]: item for item in records}
        for sequence, artifact in enumerate(self.replay_artifacts()):
            try:
                validate_artifact(artifact, expected_sequence=sequence)
                validate_artifact_owner(
                    artifact, records_by_id[artifact["owner_record_id"]], records_by_id
                )
            except ValueError as error:
                raise Phase4BValidationError(str(error)) from error
            except KeyError as error:
                raise Phase4BValidationError("replay artifact owner is unknown") from error
            row = self.connection.execute(
                "SELECT canonical_json FROM phase4b_replay_artifacts WHERE artifact_id=?",
                (artifact["artifact_id"],),
            ).fetchone()
            if row is None or row["canonical_json"].encode("utf-8") != canonical_bytes(artifact):
                raise Phase4BValidationError("durable replay artifact JSON differs")
        for row in self.connection.execute("SELECT * FROM phase4b_verified_exports"):
            value = verify_export_bytes(bytes(row["canonical_json"]))
            if (
                value["content_hash"] != row["content_hash"]
                or value["operational_hash"] != row["operational_hash"]
            ):
                raise Phase4BValidationError("verified export metadata drift")

    def export_value(self) -> dict[str, Any]:
        self.verify_integrity()
        return build_export(self.records(), self.projection(), self.replay_artifacts())

    def export_bytes(self) -> bytes:
        data = canonical_bytes(self.export_value())
        if len(data) > MAX_EXPORT_BYTES:
            raise Phase4BValidationError("Phase 4B export byte bound exceeded")
        return data

    def import_bytes(self, data: bytes) -> dict[str, Any]:
        value = verify_export_bytes(data)
        with self.durable.transaction() as connection:
            for item in value["records"]:
                existing = connection.execute(
                    "SELECT canonical_json FROM phase4b_records WHERE record_id=?",
                    (item["record_id"],),
                ).fetchone()
                if existing is not None:
                    if existing["canonical_json"].encode("utf-8") != canonical_bytes(item):
                        raise Phase4BValidationError("import conflicts with existing record")
                    continue
                self._insert_verified(connection, item)
            for item in value.get("replay_artifacts", []):
                existing = connection.execute(
                    "SELECT canonical_json FROM phase4b_replay_artifacts WHERE artifact_id=?",
                    (item["artifact_id"],),
                ).fetchone()
                if existing is not None:
                    if existing["canonical_json"].encode("utf-8") != canonical_bytes(item):
                        raise Phase4BValidationError("import conflicts with existing replay artifact")
                    continue
                self._insert_artifact(connection, item)
            self._rebuild_projection_with(connection)
            connection.execute(
                "INSERT OR IGNORE INTO phase4b_verified_exports VALUES(?,?,?)",
                (value["content_hash"], value["operational_hash"], data),
            )
        self.verify_integrity()
        return value


__all__ = ["Phase4BWorkspace"]
