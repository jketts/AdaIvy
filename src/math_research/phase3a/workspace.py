"""Transactional SQLite/CAS adapter for canonical Phase 3A memory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ..domain.entities import OpaqueId
from ..phase2.artifacts import FileArtifactStore
from ..phase2.sqlite_workspace import SQLiteWorkspace
from . import MEMORY_SCHEMA_VERSION
from .records import (
    Disposition,
    DocumentMarker,
    EvidencePackManifest,
    EvidenceRelation,
    EvidenceUnit,
    EvidenceUnitType,
    NormalizedDocument,
    ParserRunRecord,
    QuarantineState,
    ResearchMemoryRecord,
    RetrievalHit,
    RetrievalQueryRecord,
    SourceArtifact,
    SourceReference,
    SourceSpan,
    SourceVersionRelation,
    record_type,
)
from .serialization import canonical_hash, canonical_json, public_value, record_from_dict, validate_record_hashes


class MemoryCommandRejected(RuntimeError):
    pass


class ResearchMemoryWorkspace:
    """Small local adapter; canonical records never depend on this class."""

    def __init__(self, root: Path, *, artifact_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.durable = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.connection = self.durable.connection
        try:
            self._migrate_phase3a()
        except BaseException:
            self.durable.close()
            raise
        self.artifacts = FileArtifactStore(artifact_root or self.root / "artifacts")

    def close(self) -> None:
        self.durable.close()

    def __enter__(self) -> "ResearchMemoryWorkspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def migration_versions(self) -> tuple[str, ...]:
        phase3a = tuple(
            f"phase3a:{row[0]}" for row in self.connection.execute(
                "SELECT version FROM phase3a_schema_migrations ORDER BY version"
            )
        )
        return self.durable.migration_versions + phase3a

    def _migrate_phase3a(self) -> None:
        directory = Path(__file__).resolve().parents[3] / "migrations" / "phase3a"
        files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        if not files:
            raise RuntimeError(f"no Phase 3A migrations found in {directory}")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS phase3a_schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        applied = {
            row["version"]: row["checksum"]
            for row in self.connection.execute("SELECT version,checksum FROM phase3a_schema_migrations")
        }
        for path in files:
            version = path.name.split("_", 1)[0]
            data = path.read_bytes()
            checksum = hashlib.sha256(data).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(f"Phase 3A migration checksum drift: {path.name}")
                continue
            statements = [statement.strip() for statement in data.decode("utf-8").split(";") if statement.strip()]
            with self.durable.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO phase3a_schema_migrations(version,checksum,applied_at) VALUES(?,?,?)",
                    (version, checksum, "2026-08-19T00:00:00Z"),
                )

    @property
    def engine_identity(self) -> dict[str, object]:
        compile_options = tuple(row[0] for row in self.connection.execute("PRAGMA compile_options"))
        return {
            "sqlite_version": sqlite3.sqlite_version,
            "fts5_enabled": any("ENABLE_FTS5" in option for option in compile_options)
            or self._fts5_probe(),
            "tokenizer": "unicode61 remove_diacritics 0",
        }

    def _fts5_probe(self) -> bool:
        try:
            self.connection.execute("SELECT count(*) FROM evidence_fts").fetchone()
            return True
        except sqlite3.DatabaseError:
            return False

    def _append_record(self, connection: sqlite3.Connection, record: ResearchMemoryRecord, now: str) -> None:
        validate_record_hashes(record)
        kind = record_type(record)
        payload = canonical_json(record)
        payload_hash = canonical_hash(record)
        identifier = record.id.value
        existing = connection.execute(
            "SELECT record_type,canonical_hash,canonical_json FROM research_memory_records WHERE record_id=?",
            (identifier,),
        ).fetchone()
        if existing:
            if existing["record_type"] != kind or existing["canonical_hash"] != payload_hash or existing["canonical_json"] != payload:
                raise ValueError(f"research-memory record ID cannot be rewritten: {identifier}")
            return
        disposition = getattr(record, "disposition", None)
        disposition_value = disposition.value if isinstance(disposition, Disposition) else None
        source_id = getattr(record, "source_artifact_id", None)
        connection.execute(
            "INSERT INTO research_memory_records VALUES(?,?,?,?,?,?,?,?)",
            (
                identifier, kind, record.schema_version, payload_hash, payload,
                disposition_value, source_id.value if isinstance(source_id, OpaqueId) else None, now,
            ),
        )

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        event_id: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, object],
        now: str,
        idempotency_key: str,
    ) -> None:
        payload_json = canonical_json(payload)
        event_hash = canonical_hash(
            {"aggregate_id": aggregate_id, "event_type": event_type, "payload": payload, "created_at": now}
        )
        existing = connection.execute(
            "SELECT * FROM research_memory_events WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if existing:
            if (
                existing["aggregate_id"] != aggregate_id
                or existing["event_type"] != event_type
                or existing["payload_json"] != payload_json
                or existing["event_hash"] != event_hash
            ):
                raise ValueError("memory event idempotency key reused with different semantics")
            return
        connection.execute(
            "INSERT INTO research_memory_events(event_id,schema_version,aggregate_id,event_type,payload_json,event_hash,created_at,idempotency_key) VALUES(?,?,?,?,?,?,?,?)",
            (event_id, MEMORY_SCHEMA_VERSION, aggregate_id, event_type, payload_json, event_hash, now, idempotency_key),
        )

    def commit_records(
        self,
        records: tuple[ResearchMemoryRecord, ...],
        *,
        aggregate_id: OpaqueId,
        command_id: OpaqueId,
        kind: str,
        idempotency_key: str,
        request_hash: str,
        now: str,
        deadline_at: str,
        max_attempts: int = 1,
    ) -> tuple[OpaqueId, ...]:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if _parse(now) >= _parse(deadline_at):
            self._record_terminal_command(
                command_id=command_id, kind=kind, idempotency_key=idempotency_key, request_hash=request_hash,
                now=now, deadline_at=deadline_at, max_attempts=max_attempts, status="timed_out",
            )
            raise MemoryCommandRejected("memory command deadline elapsed")
        ordered = tuple(sorted(records, key=lambda record: (record_type(record), record.id.value)))
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM research_memory_commands WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash or existing["kind"] != kind:
                    raise ValueError("memory command idempotency key reused with different semantics")
                if existing["status"] == "succeeded":
                    result = json.loads(existing["result_json"])
                    return tuple(OpaqueId(value) for value in result["record_ids"])
                if existing["status"] in {"cancelled", "timed_out"}:
                    raise MemoryCommandRejected(f"memory command is {existing['status']}")
                if existing["status"] == "failed":
                    if existing["attempts"] >= existing["max_attempts"]:
                        raise MemoryCommandRejected("memory command attempt budget exhausted")
                    connection.execute(
                        "UPDATE research_memory_commands SET attempts=attempts+1,status='running',updated_at=? WHERE command_id=?",
                        (now, existing["command_id"]),
                    )
            else:
                connection.execute(
                    "INSERT INTO research_memory_commands VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (command_id.value, kind, idempotency_key, request_hash, "running", 1, max_attempts, deadline_at, None, now, now),
                )
            for record in ordered:
                self._append_record(connection, record, now)
            self._validate_canonical_state(connection)
            result = {"schema_version": MEMORY_SCHEMA_VERSION, "record_ids": [record.id.value for record in ordered]}
            connection.execute(
                "UPDATE research_memory_commands SET status='succeeded',result_json=?,updated_at=? WHERE idempotency_key=?",
                (canonical_json(result), now, idempotency_key),
            )
            self._append_event(
                connection,
                event_id=f"event.{canonical_hash({'key': idempotency_key})[7:31]}",
                aggregate_id=aggregate_id.value,
                event_type=f"{kind}_committed",
                payload={"command_id": command_id.value, "record_ids": result["record_ids"], "request_hash": request_hash},
                now=now,
                idempotency_key=f"event:{idempotency_key}",
            )
            return tuple(record.id for record in ordered)

    def _validate_canonical_state(self, connection: sqlite3.Connection) -> None:
        records = {
            row["record_id"]: record_from_dict(row["record_type"], json.loads(row["canonical_json"]))
            for row in connection.execute(
                "SELECT record_id,record_type,canonical_json FROM research_memory_records"
            )
        }

        def require(identifier: OpaqueId, expected: type[object], message: str) -> object:
            value = records.get(identifier.value)
            if not isinstance(value, expected):
                raise ValueError(message)
            return value

        for record in records.values():
            if isinstance(record, SourceArtifact):
                reference = require(record.source_reference_id, SourceReference, "source artifact references unknown source")
                assert isinstance(reference, SourceReference)
                if reference.acquisition_status.value != "bytes_available" or reference.content_hash != record.artifact_hash:
                    raise ValueError("source artifact conflicts with source-reference acquisition state")
            elif isinstance(record, SourceVersionRelation):
                require(record.source_artifact_id, SourceArtifact, "version relation source is unknown")
                require(record.target_artifact_id, SourceArtifact, "version relation target is unknown")
                if record.evidence_span_id is not None:
                    require(record.evidence_span_id, SourceSpan, "version relation evidence span is unknown")
            elif isinstance(record, ParserRunRecord):
                require(record.source_artifact_id, SourceArtifact, "parser run source artifact is unknown")
            elif isinstance(record, NormalizedDocument):
                artifact = require(record.source_artifact_id, SourceArtifact, "normalized document artifact is unknown")
                run = require(record.parser_run_id, ParserRunRecord, "normalized document parser run is unknown")
                assert isinstance(artifact, SourceArtifact) and isinstance(run, ParserRunRecord)
                if run.source_artifact_id != artifact.id or artifact.quarantine_state is not QuarantineState.ELIGIBLE:
                    raise ValueError("normalized document crosses parser/quarantine provenance")
            elif isinstance(record, SourceSpan):
                document = require(record.normalized_document_id, NormalizedDocument, "source span document is unknown")
                require(record.source_artifact_id, SourceArtifact, "source span artifact is unknown")
                assert isinstance(document, NormalizedDocument)
                if document.source_artifact_id != record.source_artifact_id:
                    raise ValueError("source span crosses document/artifact provenance")
            elif isinstance(record, DocumentMarker):
                document = require(record.normalized_document_id, NormalizedDocument, "marker document is unknown")
                span = require(record.span_id, SourceSpan, "marker span is unknown")
                assert isinstance(document, NormalizedDocument) and isinstance(span, SourceSpan)
                if span.normalized_document_id != document.id:
                    raise ValueError("marker span belongs to a different document")
            elif isinstance(record, EvidenceUnit) and record.unit_type is not EvidenceUnitType.MODEL_PROPOSED_CLAIM:
                assert record.source_artifact_id is not None and record.normalized_document_id is not None
                artifact = require(record.source_artifact_id, SourceArtifact, "evidence artifact is unknown")
                document = require(record.normalized_document_id, NormalizedDocument, "evidence document is unknown")
                assert isinstance(artifact, SourceArtifact) and isinstance(document, NormalizedDocument)
                if artifact.quarantine_state is not QuarantineState.ELIGIBLE or document.source_artifact_id != artifact.id:
                    raise ValueError("evidence crosses quarantine or document provenance")
                for identifier in record.source_span_ids:
                    span = require(identifier, SourceSpan, "evidence span is unknown")
                    assert isinstance(span, SourceSpan)
                    if span.source_artifact_id != artifact.id or span.normalized_document_id != document.id:
                        raise ValueError("evidence span belongs to different source provenance")
            elif isinstance(record, EvidenceRelation):
                require(record.source_unit_id, EvidenceUnit, "relation source unit is unknown")
                require(record.target_unit_id, EvidenceUnit, "relation target unit is unknown")
                for identifier in record.assertion_span_ids:
                    require(identifier, SourceSpan, "relation assertion span is unknown")
            elif isinstance(record, RetrievalHit):
                require(record.query_id, RetrievalQueryRecord, "retrieval hit query is unknown")
                unit = require(record.evidence_unit_id, EvidenceUnit, "retrieval hit evidence is unknown")
                artifact = require(record.source_artifact_id, SourceArtifact, "retrieval hit artifact is unknown")
                assert isinstance(unit, EvidenceUnit) and isinstance(artifact, SourceArtifact)
                if unit.source_artifact_id != artifact.id or tuple(record.source_span_ids) != tuple(unit.source_span_ids):
                    raise ValueError("retrieval hit does not preserve exact evidence provenance")
            elif isinstance(record, EvidencePackManifest):
                require(record.query_id, RetrievalQueryRecord, "evidence pack query is unknown")
                hit_units = {
                    item.evidence_unit_id
                    for item in records.values()
                    if isinstance(item, RetrievalHit) and item.query_id == record.query_id
                }
                if any(identifier not in hit_units for identifier in record.included_evidence_unit_ids):
                    raise ValueError("evidence pack includes a unit outside its retrieval result")

    def _record_terminal_command(
        self, *, command_id: OpaqueId, kind: str, idempotency_key: str, request_hash: str,
        now: str, deadline_at: str, max_attempts: int, status: str,
    ) -> None:
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT kind,request_hash,status FROM research_memory_commands WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                if existing["kind"] != kind or existing["request_hash"] != request_hash:
                    raise ValueError("memory command idempotency key reused with different semantics")
                if existing["status"] == "succeeded":
                    raise MemoryCommandRejected("succeeded command cannot become terminal failure")
                connection.execute(
                    "UPDATE research_memory_commands SET status=?,updated_at=? WHERE idempotency_key=?",
                    (status, now, idempotency_key),
                )
                return
            connection.execute(
                "INSERT INTO research_memory_commands VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    command_id.value, kind, idempotency_key, request_hash, status,
                    1 if status == "failed" else 0, max_attempts, deadline_at, None, now, now,
                ),
            )

    def record_failed_command(
        self, *, command_id: OpaqueId, kind: str, idempotency_key: str,
        request_hash: str, now: str, deadline_at: str, max_attempts: int,
    ) -> None:
        """Persist a bounded failed attempt without committing semantic records."""
        self._record_terminal_command(
            command_id=command_id, kind=kind, idempotency_key=idempotency_key,
            request_hash=request_hash, now=now, deadline_at=deadline_at,
            max_attempts=max_attempts, status="failed",
        )

    def cancel_command(self, idempotency_key: str, *, now: str) -> None:
        with self.durable.transaction() as connection:
            row = connection.execute(
                "SELECT status FROM research_memory_commands WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if row is None:
                raise KeyError(idempotency_key)
            if row["status"] == "succeeded":
                raise MemoryCommandRejected("succeeded command cannot be cancelled retroactively")
            connection.execute(
                "UPDATE research_memory_commands SET status='cancelled',updated_at=? WHERE idempotency_key=?",
                (now, idempotency_key),
            )

    def begin_command(
        self, *, command_id: OpaqueId, kind: str, idempotency_key: str,
        request_hash: str, now: str, deadline_at: str, max_attempts: int,
    ) -> None:
        """Reserve one bounded local parser command before asynchronous work."""
        if max_attempts <= 0 or _parse(now) >= _parse(deadline_at):
            raise MemoryCommandRejected("cannot begin an exhausted memory command")
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT kind,request_hash FROM research_memory_commands WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                if existing["kind"] != kind or existing["request_hash"] != request_hash:
                    raise ValueError("memory command idempotency key reused with different semantics")
                return
            connection.execute(
                "INSERT INTO research_memory_commands VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (command_id.value, kind, idempotency_key, request_hash, "running", 1, max_attempts, deadline_at, None, now, now),
            )

    def records(self, kind: str) -> tuple[ResearchMemoryRecord, ...]:
        return tuple(
            record_from_dict(kind, json.loads(row["canonical_json"]))
            for row in self.connection.execute(
                "SELECT canonical_json FROM research_memory_records WHERE record_type=? ORDER BY record_id", (kind,)
            )
        )

    def all_records(self) -> tuple[ResearchMemoryRecord, ...]:
        return tuple(
            record_from_dict(row["record_type"], json.loads(row["canonical_json"]))
            for row in self.connection.execute(
                "SELECT record_type,canonical_json FROM research_memory_records ORDER BY record_type,record_id"
            )
        )

    def get_record(self, record_id: OpaqueId) -> ResearchMemoryRecord:
        row = self.connection.execute(
            "SELECT record_type,canonical_json FROM research_memory_records WHERE record_id=?", (record_id.value,)
        ).fetchone()
        if row is None:
            raise KeyError(record_id.value)
        return record_from_dict(row["record_type"], json.loads(row["canonical_json"]))

    def source_bytes(self, artifact: SourceArtifact) -> bytes:
        return self.artifacts.get(artifact.artifact_hash)

    def artifact_bytes(self, content_hash: str) -> bytes:
        return self.artifacts.get(content_hash)

    def rebuild_index(self, *, aggregate_id: OpaqueId, now: str) -> dict[str, object]:
        identity = self.engine_identity
        if not identity["fts5_enabled"]:
            raise RuntimeError("SQLite FTS5 is unavailable")
        source_references = {record.id: record for record in self.records("source_reference") if isinstance(record, SourceReference)}
        source_artifacts = {record.id: record for record in self.records("source_artifact") if isinstance(record, SourceArtifact)}
        spans = {record.id: record for record in self.records("source_span")}
        eligible_rows: list[tuple[str, str, int, str, str, str, str]] = []
        manifest_units: list[dict[str, str]] = []
        for unit in self.records("evidence_unit"):
            assert isinstance(unit, EvidenceUnit)
            if unit.source_artifact_id is None or not unit.source_span_ids:
                continue
            artifact = source_artifacts.get(unit.source_artifact_id)
            if artifact is None or artifact.quarantine_state.value != "eligible_for_parsing":
                continue
            reference = source_references.get(artifact.source_reference_id)
            if reference is None or "local_retrieval" not in reference.license_metadata.usage_rights:
                continue
            span = spans[unit.source_span_ids[0]]
            payload = public_value(unit)["payload"]
            body = " ".join(str(value) for value in payload.values() if isinstance(value, (str, int, float)))
            eligible_rows.append(
                (unit.id.value, artifact.id.value, span.normalized_start, reference.title, body, unit.unit_type.value, unit.id.value)
            )
            row = self.connection.execute(
                "SELECT canonical_hash FROM research_memory_records WHERE record_id=?", (unit.id.value,)
            ).fetchone()
            manifest_units.append({"evidence_unit_id": unit.id.value, "canonical_hash": row["canonical_hash"]})
        eligible_rows.sort(key=lambda item: (item[1], item[2], item[0]))
        corpus_manifest = {
            "schema_version": MEMORY_SCHEMA_VERSION,
            "engine_identity": identity,
            "units": manifest_units,
            "index_policy": "proposal-source-units-with-local-retrieval-right-v1",
        }
        manifest_hash = canonical_hash(corpus_manifest)
        with self.durable.transaction() as connection:
            connection.execute("DELETE FROM evidence_fts")
            connection.executemany(
                "INSERT INTO evidence_fts(evidence_unit_id,source_artifact_id,normalized_start,title,body,unit_type) VALUES(?,?,?,?,?,?)",
                [row[:6] for row in eligible_rows],
            )
            self._append_event(
                connection, event_id=f"event.index.{manifest_hash[7:31]}", aggregate_id=aggregate_id.value,
                event_type="fts_index_rebuilt", payload={"corpus_manifest_hash": manifest_hash, "unit_count": len(eligible_rows), "engine_identity": identity},
                now=now, idempotency_key=f"index:{manifest_hash}",
            )
        return {**corpus_manifest, "content_hash": manifest_hash}

    def fts_search(self, expression: str, *, limit: int) -> tuple[dict[str, object], ...]:
        if limit <= 0:
            raise ValueError("retrieval limit must be positive")
        rows = self.connection.execute(
            """SELECT evidence_unit_id,source_artifact_id,CAST(normalized_start AS INTEGER) AS normalized_start,
                      bm25(evidence_fts, 0.0, 0.0, 0.0, 2.0, 1.0, 0.5) AS raw_score
               FROM evidence_fts WHERE evidence_fts MATCH ?
               ORDER BY raw_score ASC, source_artifact_id ASC, normalized_start ASC, evidence_unit_id ASC LIMIT ?""",
            (expression, limit),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def timeline(self, aggregate_id: OpaqueId) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "schema_version": row["schema_version"], "sequence": row["sequence"], "event_id": row["event_id"],
                "aggregate_id": row["aggregate_id"], "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]), "event_hash": row["event_hash"],
                "created_at": row["created_at"], "idempotency_key": row["idempotency_key"],
            }
            for row in self.connection.execute(
                "SELECT * FROM research_memory_events WHERE aggregate_id=? ORDER BY sequence", (aggregate_id.value,)
            )
        )

    def event_replay_hash(self, aggregate_id: OpaqueId) -> str:
        events = [
            {key: value for key, value in event.items() if key != "sequence"}
            for event in self.timeline(aggregate_id)
        ]
        return canonical_hash(events)

    def import_proposal(self, package: dict[str, object], *, source_label: str, now: str) -> dict[str, object]:
        package_hash = canonical_hash(package)
        proposal_id = f"memory-import.{package_hash[7:31]}"
        proposal = {
            "schema_version": MEMORY_SCHEMA_VERSION, "proposal_id": proposal_id, "package_hash": package_hash,
            "source_label": source_label, "disposition": "proposal", "created_at": now,
        }
        with self.durable.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO research_memory_import_proposals VALUES(?,?,?,?,?,?,?)",
                (proposal_id, MEMORY_SCHEMA_VERSION, package_hash, source_label, "proposal", canonical_json(package), now),
            )
        return proposal


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
