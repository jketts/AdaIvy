"""Append-only SQLite persistence for formal-check proposals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..phase2.sqlite_workspace import SQLiteWorkspace

from .records import FormalCheckFinding, FormalCheckOutcome
from .serialization import canonical_hash, canonical_json, finding_content_hash, sha256_bytes
from .validation import RequestValidationError, parse_request_bytes


class FormalCheckWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.durable = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.connection = self.durable.connection
        try:
            self._migrate()
        except BaseException:
            self.durable.close()
            raise

    def __enter__(self) -> "FormalCheckWorkspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.durable.close()

    def _migrate(self) -> None:
        directory = Path(__file__).resolve().parents[3] / "migrations" / "phase3b"
        files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        if not files:
            raise RuntimeError(f"no Phase 3B migrations found in {directory}")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS phase3b_schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        applied = dict(self.connection.execute("SELECT version,checksum FROM phase3b_schema_migrations"))
        for path in files:
            version = path.name.split("_", 1)[0]
            data = path.read_bytes()
            checksum = hashlib.sha256(data).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(f"Phase 3B migration checksum drift: {path.name}")
                continue
            statements = [item.strip() for item in data.decode("utf-8").split(";") if item.strip()]
            with self.durable.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO phase3b_schema_migrations VALUES(?,?,?)", (version, checksum, "2026-08-19T00:00:00Z")
                )

    @property
    def migration_versions(self) -> tuple[str, ...]:
        phase3b = tuple(f"phase3b:{row[0]}" for row in self.connection.execute("SELECT version FROM phase3b_schema_migrations ORDER BY version"))
        return self.durable.migration_versions + phase3b

    def save_attempt(self, request_bytes: bytes, finding: FormalCheckFinding) -> None:
        if finding.content_hash != finding_content_hash(finding):
            raise ValueError("formal finding content hash mismatch")
        if (
            finding.disposition != "proposal" or finding.trust_effect != "none"
            or finding.semantic_alignment_approved or finding.source_applicability_approved
            or finding.novelty_approved or finding.significance_approved
            or finding.contribution_approved or finding.epistemic_warrant_created
        ):
            raise ValueError("formal finding violates proposal-only trust boundary")
        payload = canonical_json(finding)
        request_json: str | None = None
        try:
            parsed = parse_request_bytes(request_bytes)
            request_json = canonical_json(parsed)
            if finding.outcome is FormalCheckOutcome.POLICY_REJECTION:
                if finding.wrapper_manifest is not None:
                    raise ValueError("policy rejection cannot carry a wrapper manifest")
            elif finding.wrapper_manifest is None:
                raise ValueError("validated request finding lacks a wrapper manifest")
            if finding.outcome is not FormalCheckOutcome.POLICY_REJECTION and (
                finding.wrapper_manifest.source_hash != canonical_hash(parsed)
                or finding.request_id != parsed.request_id or finding.claim_id != parsed.claim_id
            ):
                raise ValueError("finding does not correspond to the supplied request")
        except RequestValidationError:
            if finding.outcome is not FormalCheckOutcome.POLICY_REJECTION or finding.wrapper_manifest is not None:
                raise ValueError("invalid request must persist only as a policy rejection")
        with self.durable.transaction() as connection:
            existing = connection.execute("SELECT canonical_json FROM formal_check_attempts WHERE finding_id=?", (finding.id.value,)).fetchone()
            if existing:
                if existing["canonical_json"] != payload:
                    existing_value = json.loads(existing["canonical_json"])
                    if finding_content_hash(existing_value) != finding.content_hash:
                        raise ValueError("formal finding ID cannot be rewritten")
                return
            connection.execute(
                "INSERT INTO formal_check_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    finding.id.value, finding.schema_version, sha256_bytes(request_bytes), len(request_bytes), request_json,
                    request_bytes[:8192].decode("utf-8", "replace"), int(len(request_bytes) > 8192),
                    finding.outcome.value, finding.disposition, finding.content_hash, payload, finding.created_at,
                ),
            )
            event_payload = canonical_hash({"finding_id": finding.id, "content_hash": finding.content_hash})
            connection.execute(
                "INSERT INTO formal_check_events(event_id,finding_id,event_type,payload_hash,created_at,idempotency_key) VALUES(?,?,?,?,?,?)",
                (f"event.{finding.id.value}", finding.id.value, "formal_check_recorded", event_payload, finding.created_at, f"formal-check:{finding.id.value}"),
            )

    def canonical_findings(self) -> tuple[dict[str, object], ...]:
        return tuple(json.loads(row[0]) for row in self.connection.execute("SELECT canonical_json FROM formal_check_attempts ORDER BY finding_id"))

    def finding(self, finding_id: str) -> dict[str, object]:
        row = self.connection.execute("SELECT canonical_json FROM formal_check_attempts WHERE finding_id=?", (finding_id,)).fetchone()
        if row is None:
            raise KeyError(finding_id)
        return json.loads(row[0])
