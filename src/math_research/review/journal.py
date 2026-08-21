"""Append-only SQLite journal of review decisions.

Layered on the Phase 2 `SQLiteWorkspace` so one file carries the Phase 2 durable
tables and this journal, exactly as Phase 3B, Phase 6, and the synthesis slice
do. Phase 2 tables are read, never written, by this module.

Append semantics follow `domain/repositories.py:EventStore.append_once`:
replaying an identical decision returns the stored record and appends nothing;
reusing an idempotency key for different content is a refusal, never an
overwrite.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..phase2.sqlite_workspace import SQLiteWorkspace
from . import EXPORT_VERSION, HASH_PROFILE, MAX_DECISIONS, MAX_REFUSALS, SCHEMA_VERSION
from .records import DecisionProposal, Refusal, refuse
from .serialization import (
    canonical_bytes,
    finalize_record,
    operational_export_hash,
    public_value,
    semantic_export_hash,
    semantic_record_hash,
    stable_id,
)

MIGRATION_INSTANT = "2026-08-21T00:00:00Z"


class ReviewJournal:
    """Durable append-only store for review decisions and refusals."""

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

    def __enter__(self) -> "ReviewJournal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.durable.close()

    # -- schema -------------------------------------------------------------

    def _migrate(self) -> None:
        directory = Path(__file__).resolve().parents[3] / "migrations" / "review"
        files = sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        if not files:
            raise RuntimeError(f"no review migrations found in {directory}")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS review_schema_migrations "
            "(version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        applied = dict(
            self.connection.execute("SELECT version,checksum FROM review_schema_migrations")
        )
        for path in files:
            version = path.name.split("_", 1)[0]
            data = path.read_bytes()
            checksum = hashlib.sha256(data).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(f"review migration checksum drift: {path.name}")
                continue
            statements = [item.strip() for item in data.decode("utf-8").split(";") if item.strip()]
            with self.durable.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO review_schema_migrations VALUES(?,?,?)",
                    (version, checksum, MIGRATION_INSTANT),
                )

    @property
    def migration_versions(self) -> tuple[str, ...]:
        rows = self.connection.execute(
            "SELECT version FROM review_schema_migrations ORDER BY version"
        )
        return self.durable.migration_versions + tuple(f"review:{row[0]}" for row in rows)

    # -- append -------------------------------------------------------------

    @property
    def next_decision_sequence(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COALESCE(MAX(sequence),-1)+1 FROM review_decisions"
            ).fetchone()[0]
        )

    @property
    def next_refusal_sequence(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COALESCE(MAX(sequence),-1)+1 FROM review_refusals"
            ).fetchone()[0]
        )

    def append_once(
        self, proposal: DecisionProposal, *, recorded_at: str
    ) -> tuple[dict[str, Any], bool]:
        """Append a checked decision. Returns (record, appended).

        `appended` is False when the identical decision was already recorded, so
        a replay is observably a no-op rather than a silent duplicate.
        """

        identity = public_value(proposal.identity())
        decision_id = stable_id("review-decision", identity)
        candidate = finalize_record(
            {
                "schema_version": SCHEMA_VERSION,
                "hash_profile": HASH_PROFILE,
                "decision_id": decision_id,
                "decision_kind": proposal.decision_kind.value,
                "subject_id": proposal.subject_id,
                "reviewer": proposal.reviewer.value(),
                "idempotency_key": proposal.idempotency_key,
                "payload": public_value(dict(proposal.payload)),
                "sequence": self.next_decision_sequence,
                "recorded_at": recorded_at,
            }
        )
        semantic = semantic_record_hash(candidate)
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT canonical_json FROM review_decisions WHERE idempotency_key=?",
                (proposal.idempotency_key,),
            ).fetchone()
            if existing is not None:
                stored = json.loads(existing["canonical_json"])
                if stored["content_hash"] != semantic:
                    raise refuse(
                        "idempotency_key_conflict",
                        subject_id=proposal.subject_id,
                        unmet_precondition=(
                            "an idempotency key is never reused for different decision content"
                        ),
                        detail=(
                            f"key {proposal.idempotency_key!r} already records decision "
                            f"{stored['decision_id']} with semantic hash {stored['content_hash']}; "
                            "review decisions are append-only and are never rewritten"
                        ),
                    )
                return stored, False
            duplicate = connection.execute(
                "SELECT canonical_json FROM review_decisions WHERE decision_id=?", (decision_id,)
            ).fetchone()
            if duplicate is not None:
                return json.loads(duplicate["canonical_json"]), False
            if candidate["sequence"] >= MAX_DECISIONS:
                raise refuse(
                    "decision_limit_exceeded",
                    subject_id=proposal.subject_id,
                    unmet_precondition=f"the journal holds fewer than {MAX_DECISIONS} decisions",
                    detail=f"the review journal already holds {candidate['sequence']} decisions",
                )
            connection.execute(
                "INSERT INTO review_decisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    decision_id,
                    candidate["decision_kind"],
                    SCHEMA_VERSION,
                    candidate["subject_id"],
                    candidate["sequence"],
                    proposal.reviewer.id.value,
                    proposal.reviewer.kind.value,
                    proposal.idempotency_key,
                    candidate["content_hash"],
                    candidate["operational_hash"],
                    canonical_bytes(candidate).decode("utf-8"),
                    recorded_at,
                ),
            )
        return candidate, True

    def record_refusal(self, refusal: Refusal, *, recorded_at: str) -> dict[str, Any]:
        """Refusals are retained, never discarded. A dead end is a result."""

        body = refusal.value()
        refusal_id = stable_id("review-refusal", body)
        record = {
            **body,
            "refusal_id": refusal_id,
            "sequence": self.next_refusal_sequence,
            "recorded_at": recorded_at,
        }
        record["content_hash"] = semantic_record_hash(record)
        with self.durable.transaction() as connection:
            existing = connection.execute(
                "SELECT canonical_json FROM review_refusals WHERE refusal_id=?", (refusal_id,)
            ).fetchone()
            if existing is not None:
                return json.loads(existing["canonical_json"])
            if record["sequence"] >= MAX_REFUSALS:
                # Bounded store. At the cap the refusal is still returned to the
                # caller, and therefore still printed, but is not persisted. It
                # is never converted into an acceptance, and raising here would
                # replace one refusal with a different one.
                return record
            connection.execute(
                "INSERT INTO review_refusals VALUES(?,?,?,?,?,?,?,?)",
                (
                    refusal_id,
                    refusal.schema_version,
                    refusal.code,
                    refusal.subject_id,
                    record["sequence"],
                    record["content_hash"],
                    canonical_bytes(record).decode("utf-8"),
                    recorded_at,
                ),
            )
        return record

    # -- read ---------------------------------------------------------------

    def decisions(self, *, decision_kind: str | None = None) -> tuple[dict[str, Any], ...]:
        if decision_kind is None:
            rows = self.connection.execute(
                "SELECT canonical_json FROM review_decisions ORDER BY sequence"
            )
        else:
            rows = self.connection.execute(
                "SELECT canonical_json FROM review_decisions WHERE decision_kind=? ORDER BY sequence",
                (decision_kind,),
            )
        return tuple(json.loads(row[0]) for row in rows)

    def decision(self, decision_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT canonical_json FROM review_decisions WHERE decision_id=?", (decision_id,)
        ).fetchone()
        if row is None:
            raise KeyError(decision_id)
        return json.loads(row[0])

    def refusals(self) -> tuple[dict[str, Any], ...]:
        rows = self.connection.execute(
            "SELECT canonical_json FROM review_refusals ORDER BY sequence"
        )
        return tuple(json.loads(row[0]) for row in rows)

    def export(self) -> dict[str, Any]:
        """Canonical journal export.

        Records are ordered by `decision_id`, not by `sequence`, so the semantic
        export hash depends on WHICH decisions exist rather than on the order a
        particular operator happened to enter them.
        """

        decisions = sorted(self.decisions(), key=lambda item: item["decision_id"])
        refusals = sorted(self.refusals(), key=lambda item: item["refusal_id"])
        body: dict[str, Any] = {
            "schema_version": EXPORT_VERSION,
            "record_type": "review_decision_journal",
            "hash_profile": HASH_PROFILE,
            "decisions": decisions,
            "refusals": refusals,
        }
        body["content_hash"] = semantic_export_hash(body)
        body["operational_hash"] = operational_export_hash(body)
        return body
