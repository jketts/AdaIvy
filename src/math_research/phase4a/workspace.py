"""Additive Phase 4A metadata persistence beside a deletable content boundary."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from ..phase2.sqlite_workspace import SQLiteWorkspace
from . import MAX_RECORDS, SCHEMA_VERSION
from .content_store import Phase4ContentStore
from .records import AuditRecord, LifecycleType, RecordType, VerifiedSnapshot
from .serialization import canonical_bytes, canonical_hash, public_value, record_content_hash, sha256_bytes
from .validation import (
    Phase4ValidationError, validate_durable_records, validate_record_for_append,
    validate_schema_contract, verify_bytes,
)


class Phase4Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.durable = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.connection = self.durable.connection
        self.content = Phase4ContentStore(self.root / "phase4-content")
        try:
            self._migrate()
            self.verify_durable_integrity()
        except BaseException:
            self.content.close()
            self.durable.close()
            raise

    def __enter__(self) -> "Phase4Workspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.content.close()
        self.durable.close()

    def _expected_phase4_migrations(self) -> tuple[tuple[str, str], ...]:
        directory = Path(__file__).resolve().parents[3] / "migrations" / "phase4"
        files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        if not files:
            raise Phase4ValidationError("no Phase 4 migrations found")
        expected = tuple(
            (path.name.split("_", 1)[0], hashlib.sha256(path.read_bytes()).hexdigest())
            for path in files
        )
        if len({version for version, _checksum in expected}) != len(expected):
            raise Phase4ValidationError("duplicate Phase 4 migration version")
        if tuple(version for version, _checksum in expected) != tuple(
            sorted(version for version, _checksum in expected)
        ):
            raise Phase4ValidationError("Phase 4 migration files are not canonically ordered")
        return expected

    def _verify_phase4_migration_ledger(
        self, connection: Any, *, allow_missing_suffix: bool = False,
    ) -> tuple[tuple[str, str], ...]:
        """Verify the authoritative migration identity and application chronology."""

        columns = tuple(
            row[1] for row in connection.execute(
                "PRAGMA table_info(phase4_schema_migrations)"
            )
        )
        if columns != ("version", "checksum", "applied_at"):
            raise Phase4ValidationError("Phase 4 migration ledger columns differ")
        expected = self._expected_phase4_migrations()
        rows = list(connection.execute(
            "SELECT version,checksum,applied_at FROM phase4_schema_migrations ORDER BY rowid"
        ))
        observed = tuple((row["version"], row["checksum"]) for row in rows)
        if len({row["version"] for row in rows}) != len(rows):
            raise Phase4ValidationError("duplicate Phase 4 migration ledger entry")
        permitted = expected[:len(observed)] if allow_missing_suffix else expected
        if observed != permitted:
            raise Phase4ValidationError(
                "Phase 4 migration ledger is missing, unknown, reordered, or drifted"
            )
        applied_at: list[str] = []
        for row in rows:
            value = row["applied_at"]
            if not isinstance(value, str):
                raise Phase4ValidationError("Phase 4 migration chronology is malformed")
            try:
                parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError as error:
                raise Phase4ValidationError(
                    "Phase 4 migration chronology is malformed"
                ) from error
            if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
                raise Phase4ValidationError("Phase 4 migration chronology is noncanonical")
            applied_at.append(value)
        if applied_at != sorted(applied_at):
            raise Phase4ValidationError("Phase 4 migration chronology is reordered")
        return expected

    def _migrate(self) -> None:
        directory = Path(__file__).resolve().parents[3] / "migrations" / "phase4"
        files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        tables = {
            row[0] for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "phase4_schema_migrations" not in tables and any(
            name.startswith("phase4_") for name in tables
        ):
            raise RuntimeError("initialized Phase 4 schema has no migration ledger")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS phase4_schema_migrations "
            "(version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        expected = self._verify_phase4_migration_ledger(
            self.connection, allow_missing_suffix=True,
        )
        rows = list(self.connection.execute(
            "SELECT version,checksum,applied_at FROM phase4_schema_migrations ORDER BY rowid"
        ))
        applied = {row[0]: row[1] for row in rows}
        for path in files:
            version = path.name.split("_", 1)[0]
            data = path.read_bytes()
            checksum = hashlib.sha256(data).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(f"Phase 4 migration checksum drift: {path.name}")
                continue
            statements = [statement.strip() for statement in data.decode("utf-8").split(";") if statement.strip()]
            with self.durable.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO phase4_schema_migrations VALUES(?,?,?)",
                    (version, checksum, "2026-08-20T00:00:00Z"),
                )
        self._verify_phase4_migration_ledger(self.connection)

    @property
    def migration_versions(self) -> tuple[str, ...]:
        expected = self._verify_phase4_migration_ledger(self.connection)
        phase4 = tuple(f"phase4:{version}" for version, _checksum in expected)
        return self.durable.migration_versions + phase4

    @property
    def next_sequence(self) -> int:
        return int(self.connection.execute("SELECT COALESCE(MAX(sequence),-1)+1 FROM phase4_records").fetchone()[0])

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            json.loads(row[0]) for row in self.connection.execute(
                "SELECT canonical_json FROM phase4_records ORDER BY sequence"
            )
        )

    def record(self, record_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT canonical_json FROM phase4_records WHERE record_id=?", (record_id,)
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return json.loads(row[0])

    def append(self, record: AuditRecord) -> None:
        value = public_value(record)
        if record.schema_version != SCHEMA_VERSION or record.content_hash != record_content_hash(record):
            raise Phase4ValidationError("cannot persist invalid Phase 4A record hash/version")
        validate_record_for_append(value)
        payload = canonical_bytes(value).decode("utf-8")
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT canonical_json FROM phase4_records WHERE record_id=?", (record.id,)
            ).fetchone()
            if existing is not None:
                if existing["canonical_json"] != payload:
                    raise ValueError(f"Phase 4A record ID cannot be rewritten: {record.id}")
                return
            if self.next_sequence >= MAX_RECORDS:
                raise Phase4ValidationError("Phase 4A record limit exceeded")
            if record.sequence != self.next_sequence:
                raise ValueError("Phase 4A record sequence is not the next append-only value")
            if record.record_type is RecordType.LIFECYCLE_ACTION:
                source_state = connection.execute(
                    "SELECT deletion_state FROM phase4_sources WHERE source_id=?",
                    (record.subject_id,),
                ).fetchone()
                if source_state is None:
                    raise ValueError("lifecycle source is unknown")
                deletion_state = source_state["deletion_state"]
                if deletion_state in {"completed", "unavailable", "removing"}:
                    raise ValueError("source lifecycle is closed or removal is in progress")
                if (
                    record.payload["action"] == LifecycleType.DELETION_REQUEST.value
                    and deletion_state not in {"active", "requested", "incomplete"}
                ):
                    raise ValueError("illegal deletion request transition")
            connection.execute(
                "INSERT INTO phase4_records VALUES(?,?,?,?,?,?,?,?)",
                (
                    record.id, record.record_type.value, record.schema_version, record.subject_id,
                    record.sequence, record.content_hash, payload, record.recorded_at,
                ),
            )
            connection.execute(
                "INSERT INTO phase4_events(event_id,record_id,event_type,payload_hash,recorded_at) VALUES(?,?,?,?,?)",
                (f"event.{record.id}", record.id, "record_appended", record.content_hash, record.recorded_at),
            )
            if record.record_type is RecordType.SOURCE_PROVENANCE:
                connection.execute(
                    "INSERT INTO phase4_sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        record.subject_id, record.id, record.payload["artifact_hash"],
                        record.payload["content_object_id"], None,
                        int(record.payload["content_retained"]), "active", None, None, None,
                    ),
                )
                connection.execute(
                    "INSERT INTO phase4_suppression_projection VALUES(?,?,?,?,?)",
                    (record.subject_id, int(record.payload["quarantined"]), 0, int(record.payload["content_retained"]), None),
                )
            elif (
                record.record_type is RecordType.LIFECYCLE_ACTION
                and record.payload["action"] == LifecycleType.DELETION_REQUEST.value
            ):
                connection.execute(
                    "UPDATE phase4_sources SET deletion_state='requested',deletion_error=NULL,"
                    "deletion_request_id=?,completion_recorded_at=? WHERE source_id=?",
                    (record.id, record.recorded_at, record.subject_id),
                )
            if record.record_type is RecordType.LIFECYCLE_ACTION:
                self._rebuild_projections_with(connection)

    def append_deletion_completion(self, record: AuditRecord) -> None:
        """Atomically append verified completion and close its operational state."""

        if (
            record.record_type is not RecordType.LIFECYCLE_ACTION
            or record.payload["action"] != LifecycleType.DELETION_COMPLETION.value
            or record.payload["content_retained"] is not False
        ):
            raise ValueError("record is not a physical deletion completion")
        value = public_value(record)
        if record.schema_version != SCHEMA_VERSION or record.content_hash != record_content_hash(record):
            raise Phase4ValidationError("cannot persist invalid Phase 4A completion hash/version")
        validate_record_for_append(value)
        self.verify_source_absent(record.subject_id)
        payload = canonical_bytes(value).decode("utf-8")
        with self.durable.transaction() as connection:
            if self.next_sequence >= MAX_RECORDS:
                raise Phase4ValidationError("Phase 4A record limit exceeded")
            if record.sequence != self.next_sequence:
                raise ValueError("Phase 4A completion sequence is not the next append-only value")
            state = connection.execute(
                "SELECT deletion_state FROM phase4_sources WHERE source_id=?", (record.subject_id,)
            ).fetchone()
            if state is None or state["deletion_state"] != "removing":
                raise ValueError("source is not in verified deletion removal state")
            prior_completions = connection.execute(
                "SELECT COUNT(*) FROM phase4_records WHERE subject_id=? AND record_type=? "
                "AND canonical_json LIKE ?",
                (record.subject_id, RecordType.LIFECYCLE_ACTION.value, '%"action":"deletion_completion"%'),
            ).fetchone()[0]
            if prior_completions:
                raise ValueError("source already has a deletion completion event")
            connection.execute(
                "INSERT INTO phase4_records VALUES(?,?,?,?,?,?,?,?)",
                (
                    record.id, record.record_type.value, record.schema_version, record.subject_id,
                    record.sequence, record.content_hash, payload, record.recorded_at,
                ),
            )
            connection.execute(
                "INSERT INTO phase4_events(event_id,record_id,event_type,payload_hash,recorded_at) VALUES(?,?,?,?,?)",
                (f"event.{record.id}", record.id, "record_appended", record.content_hash, record.recorded_at),
            )
            connection.execute(
                "UPDATE phase4_sources SET content_retained=0,deletion_state='completed',deletion_error=NULL "
                "WHERE source_id=?", (record.subject_id,),
            )
            self._rebuild_projections_with(connection)

    def import_verified(self, data: bytes) -> VerifiedSnapshot:
        snapshot = verify_bytes(data)
        value = snapshot.value()
        with self.durable.transaction() as connection:
            for record in value["records"]:
                payload = canonical_bytes(record).decode("utf-8")
                existing = connection.execute(
                    "SELECT canonical_json FROM phase4_records WHERE record_id=?", (record["id"],)
                ).fetchone()
                if existing is not None and existing["canonical_json"] != payload:
                    raise ValueError("verified import attempted to rewrite a record ID")
                if existing is None:
                    connection.execute(
                        "INSERT INTO phase4_records VALUES(?,?,?,?,?,?,?,?)",
                        (record["id"], record["record_type"], record["schema_version"], record["subject_id"], record["sequence"], record["content_hash"], payload, record["recorded_at"]),
                    )
                    connection.execute(
                        "INSERT INTO phase4_events(event_id,record_id,event_type,payload_hash,recorded_at) VALUES(?,?,?,?,?)",
                        (f"event.{record['id']}", record["id"], "record_appended", record["content_hash"], record["recorded_at"]),
                    )
                    if record["record_type"] == RecordType.SOURCE_PROVENANCE.value:
                        source = record["payload"]
                        connection.execute(
                            "INSERT INTO phase4_sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (
                                record["subject_id"], record["id"], source["artifact_hash"],
                                source["content_object_id"], value["operational"]["source_path_hashes"].get(record["subject_id"]),
                                0, "unavailable", "verified export contains no source content", None, None,
                            ),
                        )
            connection.execute(
                "INSERT OR IGNORE INTO phase4_verified_imports VALUES(?,?,?)",
                (snapshot.content_hash, snapshot.operational_hash, snapshot.canonical_bytes),
            )
            self._rebuild_projections_with(connection)
        self.verify_durable_integrity()
        return snapshot

    def record_source_path(self, source_id: str, local_path_hash: str) -> None:
        with self.durable.transaction() as connection:
            updated = connection.execute(
                "UPDATE phase4_sources SET local_path_hash=? WHERE source_id=? AND local_path_hash IS NULL",
                (local_path_hash, source_id),
            )
            if updated.rowcount != 1:
                row = connection.execute("SELECT local_path_hash FROM phase4_sources WHERE source_id=?", (source_id,)).fetchone()
                if row is None or row["local_path_hash"] != local_path_hash:
                    raise ValueError("source path observation cannot be rewritten")

    def source_path_hashes(self) -> dict[str, str]:
        return {
            row["source_id"]: row["local_path_hash"]
            for row in self.connection.execute(
                "SELECT source_id,local_path_hash FROM phase4_sources WHERE local_path_hash IS NOT NULL ORDER BY source_id"
            )
        }

    def verify_durable_integrity(self) -> None:
        """Fail closed on metadata, append-log, projection, or content drift."""

        with self.durable.transaction() as connection:
            self._verify_durable_integrity_with(connection)

    @contextmanager
    def verified_read_snapshot(
        self,
    ) -> Iterator[tuple[tuple[dict[str, Any], ...], dict[str, str]]]:
        """Hold one stable database snapshot through verified use/serialization."""

        with self.durable.transaction() as connection:
            records, paths = self._verify_durable_integrity_with(connection)
            yield records, paths

    def _verify_durable_integrity_with(
        self, connection: Any,
    ) -> tuple[tuple[dict[str, Any], ...], dict[str, str]]:
        """Verify durable state using the caller's stable database transaction."""

        validate_schema_contract()
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
        if [row[0] for row in integrity] != ["ok"]:
            raise Phase4ValidationError("Phase 4A SQLite integrity check failed")
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise Phase4ValidationError("Phase 4A SQLite foreign-key check failed")
        required_tables = {
            "phase4_records", "phase4_events", "phase4_sources",
            "phase4_suppression_projection", "phase4_verified_imports",
            "phase4_schema_migrations",
        }
        existing = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not required_tables.issubset(existing):
            raise Phase4ValidationError("Phase 4A durable schema is incomplete")
        self._verify_phase4_migration_ledger(connection)
        expected_columns = {
            "phase4_records": ("record_id", "record_type", "schema_version", "subject_id", "sequence", "content_hash", "canonical_json", "recorded_at"),
            "phase4_events": ("sequence", "event_id", "record_id", "event_type", "payload_hash", "recorded_at"),
            "phase4_sources": ("source_id", "provenance_record_id", "artifact_hash", "content_object_id", "local_path_hash", "content_retained", "deletion_state", "deletion_error", "deletion_request_id", "completion_recorded_at"),
            "phase4_suppression_projection": ("source_id", "suppressed", "legal_hold", "content_retained", "last_lifecycle_id"),
            "phase4_verified_imports": ("content_hash", "operational_hash", "canonical_json"),
        }
        for table, columns in expected_columns.items():
            observed = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
            if observed != columns:
                raise Phase4ValidationError(f"Phase 4A durable columns differ for {table}")

        records: list[dict[str, Any]] = []
        rows = list(connection.execute("SELECT * FROM phase4_records ORDER BY sequence"))
        for row in rows:
            try:
                data = row["canonical_json"].encode("utf-8")
                record = json.loads(data)
            except (AttributeError, UnicodeError, json.JSONDecodeError) as error:
                raise Phase4ValidationError("Phase 4A durable record JSON is malformed") from error
            if not isinstance(record, dict) or canonical_bytes(record) != data:
                raise Phase4ValidationError("Phase 4A durable record JSON is noncanonical")
            columns = {
                "record_id": record["id"], "record_type": record["record_type"],
                "schema_version": record["schema_version"], "subject_id": record["subject_id"],
                "sequence": record["sequence"], "content_hash": record["content_hash"],
                "recorded_at": record["recorded_at"],
            }
            if any(row[key] != value for key, value in columns.items()):
                raise Phase4ValidationError("Phase 4A durable record columns disagree with canonical JSON")
            records.append(record)
        paths = {
            row["source_id"]: row["local_path_hash"]
            for row in connection.execute(
                "SELECT source_id,local_path_hash FROM phase4_sources "
                "WHERE local_path_hash IS NOT NULL ORDER BY source_id"
            )
        }
        validate_durable_records(records, source_path_hashes=paths)

        events = list(connection.execute(
            "SELECT event_id,record_id,event_type,payload_hash,recorded_at FROM phase4_events ORDER BY sequence"
        ))
        expected_events = [
            (f"event.{record['id']}", record["id"], "record_appended", record["content_hash"], record["recorded_at"])
            for record in records
        ]
        if [tuple(row) for row in events] != expected_events:
            raise Phase4ValidationError("Phase 4A append event log is incomplete or rewritten")

        by_id = {record["id"]: record for record in records}
        provenance = {
            record["subject_id"]: record for record in records
            if record["record_type"] == RecordType.SOURCE_PROVENANCE.value
        }
        source_rows = {
            row["source_id"]: dict(row)
            for row in connection.execute("SELECT * FROM phase4_sources")
        }
        if set(source_rows) != set(provenance):
            raise Phase4ValidationError("Phase 4A source metadata disagrees with provenance")
        if set(self.content.root_names()) != {"objects", "temporary"}:
            raise Phase4ValidationError("Phase 4A content root contains undeclared data")
        expected_object_names: set[str] = set()
        for source_id, record in provenance.items():
            row = source_rows[source_id]
            payload = record["payload"]
            if (
                row["provenance_record_id"] != record["id"]
                or row["artifact_hash"] != payload["artifact_hash"]
                or row["content_object_id"] != payload["content_object_id"]
                or row["local_path_hash"] != paths.get(source_id)
            ):
                raise Phase4ValidationError("Phase 4A source row was rewritten")
            state = row["deletion_state"]
            lifecycle = [
                item for item in records
                if item["record_type"] == RecordType.LIFECYCLE_ACTION.value
                and item["subject_id"] == source_id
            ]
            requests = [item for item in lifecycle if item["payload"]["action"] == LifecycleType.DELETION_REQUEST.value]
            completions = [item for item in lifecycle if item["payload"]["action"] == LifecycleType.DELETION_COMPLETION.value]
            if state == "completed" and len(completions) != 1:
                raise Phase4ValidationError("completed Phase 4A source lacks exactly one completion event")
            if state not in {"completed", "unavailable"} and completions:
                raise Phase4ValidationError("Phase 4A completion event disagrees with operational state")
            if state in {"requested", "removing", "incomplete", "completed"}:
                if not requests or row["deletion_request_id"] != requests[-1]["id"]:
                    raise Phase4ValidationError("Phase 4A deletion request metadata drift")
                if row["completion_recorded_at"] != requests[-1]["recorded_at"]:
                    raise Phase4ValidationError("Phase 4A deletion completion timestamp drift")
            content_state = self.content.source_state(source_id)
            if content_state == "ambiguous":
                raise Phase4ValidationError("Phase 4A source has ambiguous active/deleting content")
            if state in {"active", "requested"} and content_state != "active":
                raise Phase4ValidationError("retained Phase 4A source content is missing")
            if state in {"completed", "unavailable"} and content_state != "absent":
                raise Phase4ValidationError("non-retained Phase 4A source content remains")
            if self.phase3_copy_detected(source_id):
                raise Phase4ValidationError("Phase 4 source was detected in immutable Phase 3 storage")
            if state == "active" and row["content_retained"] != 1:
                raise Phase4ValidationError("active Phase 4A source is falsely marked absent")
            if state in {"completed", "unavailable"} and row["content_retained"] != 0:
                raise Phase4ValidationError("absent Phase 4A source is falsely marked retained")
            if content_state == "active":
                expected_object_names.add(self.content.object_key(source_id))
                if set(self.content.source_names(source_id)) != {"cards", "source.bin"}:
                    raise Phase4ValidationError("Phase 4A source object contains undeclared data")
                source = self.content.read_source(source_id)
                if sha256_bytes(source) != payload["artifact_hash"] or len(source) != payload["byte_length"]:
                    raise Phase4ValidationError("Phase 4A retained source bytes fail provenance integrity")
                cards = {
                    item["id"]: item for item in records
                    if item["record_type"] == RecordType.EVIDENCE_CARD.value
                    and item["subject_id"] == source_id
                }
                expected_cards = {
                    hashlib.sha256(card_id.encode("utf-8")).hexdigest() + ".json"
                    for card_id in cards
                }
                if set(self.content.card_names(source_id)) != expected_cards:
                    raise Phase4ValidationError("Phase 4A evidence-card content inventory drift")
                for card_id, card in cards.items():
                    content = self.content.read_card(source_id, card_id)
                    fields = {
                        "bibliographic_identity": ("bibliographic_identity_hash", "bibliographic_identity_bytes"),
                        "imported_statement": ("imported_statement_hash", "imported_statement_bytes"),
                    }
                    for name, (hash_name, bytes_name) in fields.items():
                        encoded = content.get(name, "").encode("utf-8") if isinstance(content.get(name), str) else b""
                        if sha256_bytes(encoded) != card["payload"][hash_name] or len(encoded) != card["payload"][bytes_name]:
                            raise Phase4ValidationError("Phase 4A evidence-card text integrity mismatch")
                    for name in ("hypotheses", "definitions", "scope", "exceptions"):
                        value = content.get(name)
                        if not isinstance(value, list) or canonical_hash(value) != card["payload"][f"{name}_hash"] or len(value) != card["payload"][f"{name}_count"]:
                            raise Phase4ValidationError("Phase 4A evidence-card list integrity mismatch")
            elif state == "removing" and content_state == "deleting":
                expected_object_names.add(".deleting-" + self.content.object_key(source_id))
        if set(self.content.object_names()) != expected_object_names:
            raise Phase4ValidationError("Phase 4A content object inventory contains an orphan or substitution")
        if not self.content.temporary_empty():
            raise Phase4ValidationError("Phase 4A temporary content remains")

        expected_projection = self._project_records(records, source_rows)
        actual_projection = {
            row["source_id"]: {
                "suppressed": bool(row["suppressed"]), "legal_hold": bool(row["legal_hold"]),
                "content_retained": bool(row["content_retained"]), "last_lifecycle_id": row["last_lifecycle_id"],
            }
            for row in connection.execute("SELECT * FROM phase4_suppression_projection")
        }
        if actual_projection != expected_projection:
            raise Phase4ValidationError("Phase 4A suppression projection drift")
        for row in connection.execute("SELECT * FROM phase4_verified_imports"):
            snapshot = verify_bytes(bytes(row["canonical_json"]))
            if snapshot.content_hash != row["content_hash"] or snapshot.operational_hash != row["operational_hash"]:
                raise Phase4ValidationError("Phase 4A verified-import metadata drift")
        return tuple(records), paths

    @staticmethod
    def _project_records(
        records: list[dict[str, Any]], source_rows: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        state = {
            record["subject_id"]: {
                "suppressed": bool(record["payload"]["quarantined"]), "legal_hold": False,
                "content_retained": bool(source_rows[record["subject_id"]]["content_retained"]),
                "last_lifecycle_id": None,
            }
            for record in records if record["record_type"] == RecordType.SOURCE_PROVENANCE.value
        }
        for record in records:
            if record["record_type"] != RecordType.LIFECYCLE_ACTION.value:
                continue
            source = state[record["subject_id"]]
            action = LifecycleType(record["payload"]["action"])
            if action in {LifecycleType.REVOCATION, LifecycleType.TAKEDOWN, LifecycleType.SUPPRESSION, LifecycleType.DELETION_REQUEST, LifecycleType.DELETION_COMPLETION}:
                source["suppressed"] = True
            elif action is LifecycleType.RESTORE and source["content_retained"] and source_rows[record["subject_id"]]["deletion_state"] == "active":
                source["suppressed"] = False
            if action is LifecycleType.LEGAL_HOLD:
                source["legal_hold"] = bool(record["payload"]["legal_hold"])
            source["last_lifecycle_id"] = record["id"]
        return state

    def rebuild_projections(self, *, reverse: bool = False) -> dict[str, dict[str, Any]]:
        del reverse  # replay order is always the canonical append sequence
        with self.durable.transaction() as connection:
            return self._rebuild_projections_with(connection)

    def _rebuild_projections_with(self, connection: Any) -> dict[str, dict[str, Any]]:
        records = list(self.records())
        operational = {row["source_id"]: dict(row) for row in connection.execute("SELECT * FROM phase4_sources")}
        state = self._project_records(records, operational)
        connection.execute("DELETE FROM phase4_suppression_projection")
        for source_id in sorted(state):
            value = state[source_id]
            connection.execute(
                "INSERT INTO phase4_suppression_projection VALUES(?,?,?,?,?)",
                (source_id, int(value["suppressed"]), int(value["legal_hold"]), int(value["content_retained"]), value["last_lifecycle_id"]),
            )
        return state

    def projection(self, source_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM phase4_suppression_projection WHERE source_id=?", (source_id,)
        ).fetchone()
        if row is None:
            raise KeyError(source_id)
        return {
            "suppressed": bool(row["suppressed"]), "legal_hold": bool(row["legal_hold"]),
            "content_retained": bool(row["content_retained"]), "last_lifecycle_id": row["last_lifecycle_id"],
        }

    def deletion_info(self, source_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM phase4_sources WHERE source_id=?", (source_id,)).fetchone()
        if row is None:
            raise KeyError(source_id)
        return dict(row)

    def _begin_deletion_removal(self, source_id: str) -> None:
        with self.durable.transaction() as connection:
            updated = connection.execute(
                "UPDATE phase4_sources SET deletion_state='removing',deletion_error=NULL "
                "WHERE source_id=? AND deletion_state IN ('requested','removing')",
                (source_id,),
            )
            if updated.rowcount != 1:
                raise ValueError("source does not have a pending deletion request")
            self._rebuild_projections_with(connection)

    def _record_deletion_failure(self, source_id: str, error: BaseException) -> None:
        retained = not self.content.source_absent(source_id)
        with self.durable.transaction() as connection:
            updated = connection.execute(
                "UPDATE phase4_sources SET deletion_state='incomplete',deletion_error=?,content_retained=? "
                "WHERE source_id=? AND deletion_state='removing'",
                (str(error)[:512], int(retained), source_id),
            )
            if updated.rowcount != 1:
                raise ValueError("source is not in deletion removal state")
            self._rebuild_projections_with(connection)

    def pending_deletions(self) -> tuple[str, ...]:
        return tuple(
            row[0] for row in self.connection.execute(
                "SELECT source_id FROM phase4_sources WHERE deletion_state IN ('requested','removing') ORDER BY source_id"
            )
        )

    def phase3_copy_detected(self, source_id: str) -> bool:
        """Detect prohibited source identity/digest linkage in an injected Phase 3 store."""

        table = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_memory_records'"
        ).fetchone()
        if table is None:
            return False
        info = self.deletion_info(source_id)
        needles = (source_id.encode("utf-8"), str(info["artifact_hash"]).encode("utf-8"))
        columns = [
            row["name"] for row in self.connection.execute("PRAGMA table_info(research_memory_records)")
            if str(row["type"]).upper() in {"TEXT", "BLOB", ""}
        ]
        if not columns:
            return False
        quoted = ",".join('"' + item.replace('"', '""') + '"' for item in columns)
        for row in self.connection.execute(f"SELECT {quoted} FROM research_memory_records"):
            for value in row:
                data = bytes(value) if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")
                if any(needle in data for needle in needles):
                    return True
        return False

    def verify_source_absent(self, source_id: str) -> None:
        if not self.content.source_absent(source_id):
            raise Phase4ValidationError("Phase 4A content object remains accessible")
        if not self.content.temporary_empty():
            raise Phase4ValidationError("Phase 4A temporary content remains")
        if self.phase3_copy_detected(source_id):
            raise Phase4ValidationError("Phase 4 source was detected in immutable Phase 3 storage")
