"""Append-only Phase 6 records layered on the Phase 5 workspace."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ..phase5.serialization import canonical_bytes, content_hash, finalize, stable_id
from ..phase5.workspace import Phase5Workspace, decode_json
from . import EXPORT_VERSION, MAX_EXPORT_BYTES, MAX_RECORDS, SCHEMA_VERSION


class Phase6Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.phase5 = Phase5Workspace(self.root)
        self.durable = self.phase5.durable
        self.connection = self.durable.connection
        self._migrate()
        self.verify_integrity()

    def __enter__(self) -> "Phase6Workspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.phase5.close()

    def _files(self) -> tuple[Path, ...]:
        root = Path(__file__).resolve().parents[3] / "migrations" / "phase6"
        files = tuple(sorted(root.glob("[0-9][0-9][0-9][0-9]_*.sql")))
        if not files:
            raise ValueError("no Phase 6 migration found")
        return files

    def _migrate(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS phase6_schema_migrations "
            "(version TEXT PRIMARY KEY,checksum TEXT NOT NULL,applied_at TEXT NOT NULL)"
        )
        observed = {
            row["version"]: row["checksum"]
            for row in self.connection.execute("SELECT version,checksum FROM phase6_schema_migrations")
        }
        for path in self._files():
            version = path.name.split("_", 1)[0]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if version in observed:
                if observed[version] != digest:
                    raise ValueError(f"Phase 6 migration checksum drift: {path.name}")
                continue
            statements = [item.strip() for item in path.read_text("utf-8").split(";") if item.strip()]
            with self.durable.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO phase6_schema_migrations VALUES(?,?,?)",
                    (version, digest, "2026-08-20T00:00:00Z"),
                )

    @property
    def next_sequence(self) -> int:
        return int(self.connection.execute(
            "SELECT COALESCE(MAX(sequence),-1)+1 FROM phase6_records"
        ).fetchone()[0])

    def records(self, record_type: str | None = None) -> tuple[dict[str, Any], ...]:
        if record_type is None:
            rows = self.connection.execute("SELECT canonical_json FROM phase6_records ORDER BY sequence")
        else:
            rows = self.connection.execute(
                "SELECT canonical_json FROM phase6_records WHERE record_type=? ORDER BY sequence",
                (record_type,),
            )
        return tuple(json.loads(row[0]) for row in rows)

    def record(self, record_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT canonical_json FROM phase6_records WHERE record_id=?", (record_id,)
        ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return json.loads(row[0])

    def append(
        self, *, record_type: str, subject_id: str, payload: Mapping[str, Any],
        recorded_at: str, record_id: str | None = None,
    ) -> dict[str, Any]:
        identity = {"record_type": record_type, "subject_id": subject_id, "payload": payload}
        record_id = record_id or stable_id(record_type.replace("_", "-"), identity)
        record = finalize({
            "schema_version": SCHEMA_VERSION, "record_id": record_id,
            "record_type": record_type, "subject_id": subject_id,
            "sequence": self.next_sequence, "recorded_at": recorded_at,
            "payload": dict(payload),
        })
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT canonical_json FROM phase6_records WHERE record_id=?", (record_id,)
            ).fetchone()
            if existing is not None:
                old = json.loads(existing[0])
                candidate = dict(record)
                candidate["sequence"] = old["sequence"]
                candidate = finalize(candidate)
                if canonical_bytes(candidate) != bytes(existing[0], "utf-8"):
                    raise ValueError("Phase 6 record identity cannot be rewritten")
                return old
            if self.next_sequence >= MAX_RECORDS:
                raise ValueError("Phase 6 record limit exceeded")
            connection.execute(
                "INSERT INTO phase6_records VALUES(?,?,?,?,?,?,?,?)",
                (
                    record_id, record_type, SCHEMA_VERSION, subject_id, record["sequence"],
                    record["content_hash"], canonical_bytes(record).decode("utf-8"), recorded_at,
                ),
            )
        return record

    def verify_integrity(self) -> None:
        self.phase5.verify_integrity()
        rows = list(self.connection.execute("SELECT * FROM phase6_records ORDER BY sequence"))
        if [row["sequence"] for row in rows] != list(range(len(rows))):
            raise ValueError("Phase 6 record sequence is incomplete or reordered")
        for row in rows:
            value = json.loads(row["canonical_json"])
            if (
                value.get("schema_version") != SCHEMA_VERSION
                or value.get("record_id") != row["record_id"]
                or value.get("sequence") != row["sequence"]
                or value.get("content_hash") != row["content_hash"]
                or content_hash(value) != row["content_hash"]
            ):
                raise ValueError("Phase 6 durable record integrity failed")

    def export_value(self) -> dict[str, Any]:
        self.verify_integrity()
        phase5 = self.phase5.export_value()
        value = {
            "schema_version": EXPORT_VERSION,
            "phase5_export_hash": phase5["content_hash"],
            "records": list(self.records()),
        }
        return finalize(value)

    def export_bytes(self) -> bytes:
        data = canonical_bytes(self.export_value())
        if len(data) > MAX_EXPORT_BYTES:
            raise ValueError("Phase 6 export exceeds the bounded byte limit")
        return data

    def save_verified_export(self, data: bytes) -> dict[str, Any]:
        value = decode_json(data, max_bytes=MAX_EXPORT_BYTES)
        if set(value) != {"schema_version", "phase5_export_hash", "records", "content_hash"}:
            raise ValueError("Phase 6 export has missing or unknown fields")
        if value["schema_version"] != EXPORT_VERSION or value["content_hash"] != content_hash(value):
            raise ValueError("Phase 6 export identity is invalid")
        with self.durable.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO phase6_verified_exports VALUES(?,?)",
                (value["content_hash"], canonical_bytes(value)),
            )
        return value
