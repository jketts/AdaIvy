"""Transactional SQLite implementation of the Phase 2 durable workspace."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..domain.entities import OpaqueId, ResearchDossier
from ..interchange import export_dossier_bytes, export_dossier_dict, import_trusted_replay
from . import PHASE2_SCHEMA_VERSION
from .records import (
    BudgetLimits,
    BudgetSnapshot,
    CostEstimate,
    JobRecord,
    JobStatus,
    ModelResult,
    ProposalRecord,
    PricingSnapshot,
    RefinementOutcomeClass,
    RefinementRoundRecord,
    RunRecord,
    RunStatus,
    RunStopReason,
    RunStopRecord,
    VerifierContextManifest,
    VerifierIndependence,
)
from .serialization import canonical_json


class MigrationError(RuntimeError):
    pass


class BudgetExhausted(RuntimeError):
    def __init__(self, dimensions: tuple[str, ...]) -> None:
        self.dimensions = dimensions
        super().__init__("budget exhausted: " + ", ".join(dimensions))


class LateCommitRejected(RuntimeError):
    pass


class SealedWorkspaceError(RuntimeError):
    """A durable write was attempted against a workspace opened read-only."""


class RefinementRoundsExhausted(RuntimeError):
    """ADR-0041. The declared refinement-round cap refused another round."""

    def __init__(self, *, requested_round: int, max_refinement_rounds: int) -> None:
        self.requested_round = requested_round
        self.max_refinement_rounds = max_refinement_rounds
        super().__init__(
            f"refinement round {requested_round} exceeds the declared cap of "
            f"{max_refinement_rounds}"
        )


#: ADR-0041. Migration files may declare that they need SQLite's table-rebuild
#: procedure. Widening a CHECK constraint on a referenced table is impossible
#: with foreign keys on, so the runner turns them off for exactly that file and
#: re-checks integrity afterwards. Fail closed: an unknown directive is an error.
_REBUILD_DIRECTIVE = "-- adaivy-migration: rebuild-tables"


class SQLiteWorkspace:
    """Transactional durable workspace, or a sealed read-only replay of one.

    ``read_only=True`` exists because some Phase 2 workspaces are *sealed
    evidence*: `reports/phase-2/workspace.sqlite3` is pinned byte-for-byte by
    the ADR-0022 Phase 4A protected-evidence manifest. Opening such a file
    read-write would let a later schema migration rewrite committed evidence in
    place, which is exactly what "protected" is supposed to prevent. In
    read-only mode the file is opened immutable, copied into an in-memory
    database, and the migrations are applied to the copy, so a replay reads the
    current schema while the bytes on disk never change. Any durable write in
    that mode raises `SealedWorkspaceError` rather than vanishing silently.
    """

    def __init__(
        self, path: Path, *, migrations_dir: Path | None = None, read_only: bool = False,
    ) -> None:
        self.path = path.resolve()
        self.read_only = read_only
        self.migrations_dir = migrations_dir or Path(__file__).resolve().parents[3] / "migrations"
        self._sealed = False
        if read_only:
            if not self.path.is_file():
                raise FileNotFoundError(str(self.path))
            source = sqlite3.connect(
                f"file:{self.path}?mode=ro&immutable=1", uri=True, timeout=5.0,
                isolation_level=None,
            )
            try:
                self.connection = sqlite3.connect(":memory:", timeout=5.0, isolation_level=None)
                source.backup(self.connection)
            finally:
                source.close()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        if not read_only:
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = FULL")
        try:
            self._migrate()
        except BaseException:
            self.connection.close()
            raise
        self._sealed = read_only

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteWorkspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self._sealed:
            raise SealedWorkspaceError(
                f"workspace opened read-only; refusing a durable write: {self.path}"
            )
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def _migrate(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        files = sorted(self.migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))
        if not files:
            raise MigrationError(f"no migrations found in {self.migrations_dir}")
        applied = {
            row["version"]: row["checksum"]
            for row in self.connection.execute("SELECT version, checksum FROM schema_migrations")
        }
        for path in files:
            version = path.name.split("_", 1)[0]
            data = path.read_bytes()
            checksum = hashlib.sha256(data).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise MigrationError(f"migration checksum drift: {path.name}")
                continue
            text = data.decode("utf-8")
            statements = [item.strip() for item in text.split(";") if item.strip()]
            rebuild = text.splitlines()[0].strip() == _REBUILD_DIRECTIVE if text.strip() else False
            if not rebuild and text.lstrip().startswith("-- adaivy-migration:"):
                raise MigrationError(f"unknown migration directive: {path.name}")
            if rebuild:
                self.connection.execute("PRAGMA foreign_keys = OFF")
                self.connection.execute("PRAGMA legacy_alter_table = ON")
            try:
                with self.transaction() as connection:
                    for statement in statements:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES(?,?,?)",
                        (version, checksum, _now()),
                    )
            finally:
                if rebuild:
                    self.connection.execute("PRAGMA legacy_alter_table = OFF")
                    self.connection.execute("PRAGMA foreign_keys = ON")
            if rebuild:
                violations = self.connection.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise MigrationError(
                        f"migration left {len(violations)} foreign key violations: {path.name}"
                    )

    @property
    def migration_versions(self) -> tuple[str, ...]:
        return tuple(row[0] for row in self.connection.execute("SELECT version FROM schema_migrations ORDER BY version"))

    @property
    def pragmas(self) -> dict[str, object]:
        return {
            "foreign_keys": self.connection.execute("PRAGMA foreign_keys").fetchone()[0],
            "journal_mode": self.connection.execute("PRAGMA journal_mode").fetchone()[0],
        }

    def _insert_dossier(self, connection: sqlite3.Connection, dossier: ResearchDossier, now: str) -> str:
        payload = export_dossier_bytes(dossier)
        dossier_hash = export_dossier_dict(dossier)["content_hash"]
        existing = connection.execute(
            "SELECT content_hash, canonical_json FROM dossiers WHERE dossier_id = ?", (dossier.id.value,)
        ).fetchone()
        if existing:
            if existing["content_hash"] != dossier_hash or bytes(existing["canonical_json"]) != payload:
                raise ValueError("dossier ID cannot be rewritten")
            return dossier_hash
        connection.execute(
            "INSERT INTO dossiers(dossier_id,schema_version,content_hash,canonical_json,created_at) VALUES(?,?,?,?,?)",
            (dossier.id.value, dossier.schema_version, dossier_hash, payload, now),
        )
        return dossier_hash

    def save_dossier(self, dossier: ResearchDossier) -> str:
        with self.transaction() as connection:
            return self._insert_dossier(connection, dossier, _now())

    def load_dossier(self, dossier_id: OpaqueId) -> ResearchDossier:
        row = self.connection.execute(
            "SELECT canonical_json FROM dossiers WHERE dossier_id = ?", (dossier_id.value,)
        ).fetchone()
        if row is None:
            raise KeyError(dossier_id.value)
        return import_trusted_replay(bytes(row["canonical_json"]))

    def create_run(
        self, *, run_id: OpaqueId, dossier: ResearchDossier, budget_id: OpaqueId,
        limits: BudgetLimits, now: str,
    ) -> RunRecord:
        with self.transaction() as connection:
            dossier_hash = self._insert_dossier(connection, dossier, now)
            existing = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id.value,)).fetchone()
            if existing:
                if existing["dossier_hash"] != dossier_hash or existing["budget_id"] != budget_id.value:
                    raise ValueError("run ID cannot be rewritten")
                declared = connection.execute(
                    "SELECT max_refinement_rounds FROM budgets WHERE budget_id=?",
                    (budget_id.value,),
                ).fetchone()
                if declared is not None and declared["max_refinement_rounds"] != limits.max_refinement_rounds:
                    raise ValueError("declared refinement-round cap cannot be rewritten")
                return self._run(existing)
            connection.execute(
                """INSERT INTO budgets(
                    budget_id,schema_version,max_input_tokens,max_output_tokens,
                    max_cost_microusd,max_wall_milliseconds,max_attempts,
                    used_input_tokens,used_output_tokens,used_cost_microusd,
                    used_attempts,started_at,updated_at,max_refinement_rounds,
                    used_refinement_rounds
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    budget_id.value, PHASE2_SCHEMA_VERSION, limits.max_input_tokens,
                    limits.max_output_tokens, limits.max_cost_microusd,
                    limits.max_wall_milliseconds, limits.max_attempts,
                    0, 0, 0, 0, now, now, limits.max_refinement_rounds, 1,
                ),
            )
            connection.execute(
                "INSERT INTO runs(run_id,schema_version,dossier_id,dossier_hash,budget_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (run_id.value, PHASE2_SCHEMA_VERSION, dossier.id.value, dossier_hash, budget_id.value, RunStatus.QUEUED.value, now, now),
            )
            self._insert_event(
                connection, event_id=f"event.{run_id.value}.created", aggregate_id=run_id.value,
                event_type="run_created", payload_json=canonical_json({"dossier_id": dossier.id.value, "dossier_hash": dossier_hash}),
                now=now, idempotency_key=f"run-created:{run_id.value}",
            )
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id.value,)).fetchone()
            assert row is not None
            return self._run(row)

    def get_run(self, run_id: OpaqueId) -> RunRecord:
        row = self.connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id.value,)).fetchone()
        if row is None:
            raise KeyError(run_id.value)
        return self._run(row)

    def set_run_status(self, run_id: OpaqueId, status: str, *, now: str, idempotency_key: str) -> RunRecord:
        desired = RunStatus(status)
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id.value,)).fetchone()
            if row is None:
                raise KeyError(run_id.value)
            current = RunStatus(row["status"])
            existing_event = connection.execute(
                "SELECT event_type FROM semantic_events WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing_event is not None and current is desired and existing_event["event_type"] == f"run_{desired.value}":
                return self._run(row)
            allowed = {
                RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED},
                RunStatus.RUNNING: {RunStatus.PAUSED, RunStatus.AWAITING_REVIEW, RunStatus.UNRESOLVED, RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.REFINEMENT_EXHAUSTED},
                RunStatus.PAUSED: {RunStatus.RUNNING, RunStatus.CANCELLED},
                RunStatus.AWAITING_REVIEW: {RunStatus.CANCELLED},
                RunStatus.UNRESOLVED: {RunStatus.CANCELLED},
                RunStatus.CANCELLED: set(),
                RunStatus.COMPLETED: set(),
                RunStatus.REFINEMENT_EXHAUSTED: {RunStatus.CANCELLED},
            }
            if current is not desired and desired not in allowed[current]:
                raise LateCommitRejected(f"invalid run transition: {current.value} -> {desired.value}")
            connection.execute("UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?", (desired.value, now, run_id.value))
            if desired is RunStatus.CANCELLED:
                connection.execute(
                    "UPDATE jobs SET status='cancelled', lease_owner=NULL, lease_until=NULL, updated_at=? WHERE run_id=? AND status IN ('queued','running','retryable')",
                    (now, run_id.value),
                )
            self._insert_event(
                connection, event_id=f"event.{idempotency_key}", aggregate_id=run_id.value,
                event_type=f"run_{desired.value}", payload_json=canonical_json({"from": current.value, "to": desired.value}),
                now=now, idempotency_key=idempotency_key,
            )
            updated = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id.value,)).fetchone()
            assert updated is not None
            return self._run(updated)

    def budget(self, budget_id: OpaqueId, *, now: str) -> BudgetSnapshot:
        row = self.connection.execute("SELECT * FROM budgets WHERE budget_id = ?", (budget_id.value,)).fetchone()
        if row is None:
            raise KeyError(budget_id.value)
        return self._budget(row, now)

    def reserve_call(
        self, budget_id: OpaqueId, *, estimated_input_tokens: int,
        estimated_output_tokens: int, estimated_cost_microusd: int = 0, now: str,
    ) -> BudgetSnapshot:
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM budgets WHERE budget_id = ?", (budget_id.value,)).fetchone()
            if row is None:
                raise KeyError(budget_id.value)
            snapshot = self._budget(row, now)
            exhausted = list(snapshot.exhausted_dimensions)
            if row["used_input_tokens"] + estimated_input_tokens > row["max_input_tokens"]:
                exhausted.append("input_tokens")
            if row["used_output_tokens"] + estimated_output_tokens > row["max_output_tokens"]:
                exhausted.append("output_tokens")
            if row["used_cost_microusd"] + estimated_cost_microusd > row["max_cost_microusd"]:
                exhausted.append("cost")
            if exhausted:
                raise BudgetExhausted(tuple(sorted(set(exhausted))))
            connection.execute(
                "UPDATE budgets SET used_attempts=used_attempts+1, updated_at=? WHERE budget_id=?",
                (now, budget_id.value),
            )
            updated = connection.execute("SELECT * FROM budgets WHERE budget_id = ?", (budget_id.value,)).fetchone()
            assert updated is not None
            return self._budget(updated, now)

    def record_usage(
        self, budget_id: OpaqueId, *, input_tokens: int, output_tokens: int,
        cost_microusd: int, now: str,
    ) -> BudgetSnapshot:
        if min(input_tokens, output_tokens, cost_microusd) < 0:
            raise ValueError("usage must be non-negative")
        with self.transaction() as connection:
            connection.execute(
                "UPDATE budgets SET used_input_tokens=used_input_tokens+?, used_output_tokens=used_output_tokens+?, used_cost_microusd=used_cost_microusd+?, updated_at=? WHERE budget_id=?",
                (input_tokens, output_tokens, cost_microusd, now, budget_id.value),
            )
            row = connection.execute("SELECT * FROM budgets WHERE budget_id = ?", (budget_id.value,)).fetchone()
            if row is None:
                raise KeyError(budget_id.value)
            return self._budget(row, now)

    def enqueue_job(
        self, *, job_id: OpaqueId, run_id: OpaqueId, kind: str, idempotency_key: str,
        payload_hash: str, max_attempts: int, deadline_at: str, now: str,
        round_index: int = 1,
    ) -> JobRecord:
        if round_index < 1:
            raise ValueError("round_index must be at least 1")
        with self.transaction() as connection:
            existing = connection.execute("SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing:
                if (
                    existing["run_id"] != run_id.value
                    or existing["kind"] != kind
                    or existing["payload_hash"] != payload_hash
                    or existing["round_index"] != round_index
                ):
                    raise ValueError("job idempotency key reused with different semantics")
                return self._job(existing)
            connection.execute(
                """INSERT INTO jobs(
                    job_id,schema_version,run_id,kind,status,idempotency_key,payload_hash,
                    attempts,max_attempts,deadline_at,lease_owner,lease_until,result_hash,
                    created_at,updated_at,round_index
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job_id.value, PHASE2_SCHEMA_VERSION, run_id.value, kind, JobStatus.QUEUED.value,
                 idempotency_key, payload_hash, 0, max_attempts, deadline_at, None, None, None,
                 now, now, round_index),
            )
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id.value,)).fetchone()
            assert row is not None
            return self._job(row)

    def claim_job(
        self, *, run_id: OpaqueId, kind: str, worker_id: str, lease_until: str, now: str,
        round_index: int | None = None,
    ) -> JobRecord | None:
        with self.transaction() as connection:
            run = connection.execute("SELECT status FROM runs WHERE run_id=?", (run_id.value,)).fetchone()
            if run is None:
                raise KeyError(run_id.value)
            if run["status"] != RunStatus.RUNNING.value:
                return None
            connection.execute(
                "UPDATE jobs SET status='timed_out', lease_owner=NULL, lease_until=NULL, updated_at=? WHERE run_id=? AND deadline_at<=? AND status IN ('queued','running','retryable')",
                (now, run_id.value, now),
            )
            if round_index is None:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE run_id=? AND kind=? AND status IN ('queued','retryable') AND attempts<max_attempts AND deadline_at>? ORDER BY round_index,created_at,job_id LIMIT 1",
                    (run_id.value, kind, now),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE run_id=? AND kind=? AND round_index=? AND status IN ('queued','retryable') AND attempts<max_attempts AND deadline_at>? ORDER BY created_at,job_id LIMIT 1",
                    (run_id.value, kind, round_index, now),
                ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE jobs SET status='running', attempts=attempts+1, lease_owner=?, lease_until=?, updated_at=? WHERE job_id=?",
                (worker_id, lease_until, now, row["job_id"]),
            )
            updated = connection.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()
            assert updated is not None
            return self._job(updated)

    def finish_job(
        self, job_id: OpaqueId, *, worker_id: str, status: str,
        result_hash: str | None, now: str, idempotency_key: str,
    ) -> JobRecord:
        desired = JobStatus(status)
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT jobs.*, runs.status AS run_status FROM jobs JOIN runs USING(run_id) WHERE job_id=?",
                (job_id.value,),
            ).fetchone()
            if row is None:
                raise KeyError(job_id.value)
            current = JobStatus(row["status"])
            if current is desired and row["result_hash"] == result_hash:
                return self._job(row)
            if desired is JobStatus.SUCCEEDED and (
                current in {JobStatus.CANCELLED, JobStatus.TIMED_OUT}
                or row["run_status"] == RunStatus.CANCELLED.value
                or row["deadline_at"] <= now
            ):
                raise LateCommitRejected("cancelled or timed-out job cannot commit success")
            if current is not JobStatus.RUNNING or row["lease_owner"] != worker_id:
                raise LateCommitRejected("worker does not hold the active job lease")
            connection.execute(
                "UPDATE jobs SET status=?, result_hash=?, lease_owner=NULL, lease_until=NULL, updated_at=? WHERE job_id=?",
                (desired.value, result_hash, now, job_id.value),
            )
            self._insert_event(
                connection, event_id=f"event.{idempotency_key}", aggregate_id=row["run_id"],
                event_type=f"job_{desired.value}", payload_json=canonical_json({"job_id": job_id.value, "result_hash": result_hash}),
                now=now, idempotency_key=idempotency_key,
            )
            updated = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id.value,)).fetchone()
            assert updated is not None
            return self._job(updated)

    def list_jobs(self, run_id: OpaqueId) -> tuple[JobRecord, ...]:
        return tuple(self._job(row) for row in self.connection.execute("SELECT * FROM jobs WHERE run_id=? ORDER BY created_at,job_id", (run_id.value,)))

    def recover_jobs(self, *, now: str) -> tuple[JobRecord, ...]:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE jobs SET status=CASE WHEN attempts>=max_attempts THEN 'failed' ELSE 'retryable' END, lease_owner=NULL, lease_until=NULL, updated_at=? WHERE status='running' AND lease_until<=? AND deadline_at>?",
                (now, now, now),
            )
            connection.execute(
                "UPDATE jobs SET status='timed_out', lease_owner=NULL, lease_until=NULL, updated_at=? WHERE status IN ('queued','running','retryable') AND deadline_at<=?",
                (now, now),
            )
            connection.execute(
                "UPDATE jobs SET status='cancelled', lease_owner=NULL, lease_until=NULL, updated_at=? WHERE run_id IN (SELECT run_id FROM runs WHERE status='cancelled') AND status IN ('queued','running','retryable')",
                (now,),
            )
            return tuple(self._job(row) for row in connection.execute("SELECT * FROM jobs ORDER BY created_at,job_id"))

    def commit_proposal(
        self, proposal: ProposalRecord, *, job_id: OpaqueId, worker_id: str,
        now: str, event_key: str,
    ) -> ProposalRecord:
        with self.transaction() as connection:
            job = connection.execute(
                "SELECT jobs.*, runs.status AS run_status FROM jobs JOIN runs USING(run_id) WHERE job_id=?",
                (job_id.value,),
            ).fetchone()
            if job is None:
                raise KeyError(job_id.value)
            if job["run_id"] != proposal.run_id.value:
                raise ValueError("proposal run and job run differ")
            if job["status"] in {JobStatus.CANCELLED.value, JobStatus.TIMED_OUT.value} or job["run_status"] == RunStatus.CANCELLED.value or job["deadline_at"] <= now:
                raise LateCommitRejected("inactive job cannot commit a proposal")
            if job["status"] != JobStatus.RUNNING.value or job["lease_owner"] != worker_id:
                raise LateCommitRejected("worker does not hold proposal job lease")
            connection.execute(
                "INSERT OR IGNORE INTO proposals VALUES(?,?,?,?,?,?,?,?,?,?)",
                (proposal.proposal_id.value, proposal.schema_version, proposal.run_id.value,
                 proposal.proposal_kind, proposal.artifact_hash, proposal.source_kind,
                 proposal.source_id, proposal.target_claim_id.value if proposal.target_claim_id else None,
                 proposal.disposition, now),
            )
            row = connection.execute(
                "SELECT * FROM proposals WHERE run_id=? AND artifact_hash=? AND proposal_kind=?",
                (proposal.run_id.value, proposal.artifact_hash, proposal.proposal_kind),
            ).fetchone()
            assert row is not None
            self._insert_event(
                connection, event_id=f"event.{event_key}", aggregate_id=proposal.run_id.value,
                event_type="proposal_imported", payload_json=canonical_json({"proposal_id": row["proposal_id"], "artifact_hash": row["artifact_hash"], "disposition": "proposal"}),
                now=now, idempotency_key=event_key,
            )
            return self._proposal(row)

    def list_proposals(self, run_id: OpaqueId) -> tuple[ProposalRecord, ...]:
        return tuple(self._proposal(row) for row in self.connection.execute("SELECT * FROM proposals WHERE run_id=? ORDER BY proposal_id", (run_id.value,)))

    def save_manifest(self, manifest: VerifierContextManifest, *, canonical_json: str, now: str) -> VerifierContextManifest:
        payload = json.loads(canonical_json)
        if payload.get("serialized_context_hash") != manifest.serialized_context_hash:
            raise ValueError("manifest JSON and record hash differ")
        if payload.get("round_index", 1) != manifest.round_index:
            raise ValueError("manifest JSON and record round differ")
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT canonical_json FROM verifier_manifests WHERE run_id=? AND round_index=?",
                (manifest.run_id.value, manifest.round_index),
            ).fetchone()
            if existing and existing["canonical_json"] != canonical_json:
                raise ValueError("verifier manifest is immutable")
            connection.execute(
                """INSERT OR IGNORE INTO verifier_manifests(
                    manifest_id,schema_version,run_id,round_index,canonical_json,
                    serialized_context_hash,created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (manifest.manifest_id.value, manifest.schema_version, manifest.run_id.value,
                 manifest.round_index, canonical_json, manifest.serialized_context_hash, now),
            )
        return manifest

    def get_manifest(self, run_id: OpaqueId, *, round_index: int | None = None) -> VerifierContextManifest:
        """Return one round's manifest; ``None`` means the latest recorded round.

        A pre-ADR-0041 workspace holds exactly one manifest per run, which the
        migration labels round one, so the default answer is unchanged there.
        """
        if round_index is None:
            row = self.connection.execute(
                "SELECT canonical_json, round_index FROM verifier_manifests WHERE run_id=? ORDER BY round_index DESC LIMIT 1",
                (run_id.value,),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT canonical_json, round_index FROM verifier_manifests WHERE run_id=? AND round_index=?",
                (run_id.value, round_index),
            ).fetchone()
        if row is None:
            raise KeyError(run_id.value if round_index is None else f"{run_id.value}#{round_index}")
        return self._manifest(row["canonical_json"], row["round_index"])

    def list_manifests(self, run_id: OpaqueId) -> tuple[VerifierContextManifest, ...]:
        return tuple(
            self._manifest(row["canonical_json"], row["round_index"])
            for row in self.connection.execute(
                "SELECT canonical_json, round_index FROM verifier_manifests WHERE run_id=? ORDER BY round_index",
                (run_id.value,),
            )
        )

    @staticmethod
    def _manifest(canonical_json_text: str, round_index: int) -> VerifierContextManifest:
        value = json.loads(canonical_json_text)
        independence = VerifierIndependence(**value["independence"])
        return VerifierContextManifest(
            schema_version=value["schema_version"], manifest_id=OpaqueId(value["manifest_id"]),
            run_id=OpaqueId(value["run_id"]), included_entity_ids=tuple(OpaqueId(item) for item in value["included_entity_ids"]),
            excluded_entity_ids=tuple(OpaqueId(item) for item in value["excluded_entity_ids"]),
            policy_version=value["policy_version"], serialized_context_hash=value["serialized_context_hash"],
            context_artifact_hash=value["context_artifact_hash"], independence=independence,
            round_index=value.get("round_index", round_index),
            candidate_shaped_by_rounds=tuple(value.get("candidate_shaped_by_rounds", ())),
            withheld_prior_finding_hashes=tuple(value.get("withheld_prior_finding_hashes", ())),
        )

    def reserve_refinement_round(
        self, budget_id: OpaqueId, *, round_index: int, now: str,
    ) -> BudgetSnapshot:
        """Grant round ``round_index`` or refuse it against the declared cap.

        Idempotent: replaying an already-granted round is a no-op, so a crash
        between granting a round and enqueueing its job cannot consume two.
        """
        if round_index < 1:
            raise ValueError("round_index must be at least 1")
        with self.transaction() as connection:
            row = connection.execute("SELECT * FROM budgets WHERE budget_id = ?", (budget_id.value,)).fetchone()
            if row is None:
                raise KeyError(budget_id.value)
            if round_index > row["max_refinement_rounds"]:
                raise RefinementRoundsExhausted(
                    requested_round=round_index,
                    max_refinement_rounds=row["max_refinement_rounds"],
                )
            if round_index > row["used_refinement_rounds"]:
                connection.execute(
                    "UPDATE budgets SET used_refinement_rounds=?, updated_at=? WHERE budget_id=?",
                    (round_index, now, budget_id.value),
                )
            updated = connection.execute("SELECT * FROM budgets WHERE budget_id = ?", (budget_id.value,)).fetchone()
            assert updated is not None
            return self._budget(updated, now)

    def record_refinement_round(
        self, record: RefinementRoundRecord, *, now: str,
    ) -> RefinementRoundRecord:
        """Append one immutable round record.

        Re-recording identical content is a no-op; re-recording different
        content for the same round is rejected rather than overwritten.
        """
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM refinement_rounds WHERE run_id=? AND round_index=?",
                (record.run_id.value, record.round_index),
            ).fetchone()
            if existing is not None:
                if (
                    existing["candidate_artifact_hash"] != record.candidate_artifact_hash
                    or existing["finding_artifact_hash"] != record.finding_artifact_hash
                    or existing["outcome_class"] != record.outcome_class.value
                    or existing["result_type"] != record.result_type
                    or existing["recommendation"] != record.recommendation
                    or bool(existing["refinement_warranted"]) != record.refinement_warranted
                ):
                    raise ValueError("refinement round record cannot be rewritten")
                return record
            connection.execute(
                """INSERT INTO refinement_rounds(
                    run_id,round_index,schema_version,candidate_artifact_hash,
                    finding_artifact_hash,outcome_class,result_type,recommendation,
                    refinement_warranted,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (record.run_id.value, record.round_index, record.schema_version,
                 record.candidate_artifact_hash, record.finding_artifact_hash,
                 record.outcome_class.value, record.result_type, record.recommendation,
                 1 if record.refinement_warranted else 0, now),
            )
        return record

    def list_refinement_rounds(self, run_id: OpaqueId) -> tuple[RefinementRoundRecord, ...]:
        return tuple(
            RefinementRoundRecord(
                schema_version=row["schema_version"], run_id=OpaqueId(row["run_id"]),
                round_index=row["round_index"],
                candidate_artifact_hash=row["candidate_artifact_hash"],
                finding_artifact_hash=row["finding_artifact_hash"],
                outcome_class=RefinementOutcomeClass(row["outcome_class"]),
                result_type=row["result_type"], recommendation=row["recommendation"],
                refinement_warranted=bool(row["refinement_warranted"]),
            )
            for row in self.connection.execute(
                "SELECT * FROM refinement_rounds WHERE run_id=? ORDER BY round_index",
                (run_id.value,),
            )
        )

    def record_run_stop(self, record: RunStopRecord, *, now: str) -> RunStopRecord:
        payload = canonical_json(list(record.binding_bounds))
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM run_stop_records WHERE run_id=?", (record.run_id.value,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["terminal_status"] != record.terminal_status.value
                    or existing["stop_reason"] != record.stop_reason.value
                    or existing["stop_bound"] != record.stop_bound
                    or existing["binding_bounds_json"] != payload
                    or existing["rounds_used"] != record.rounds_used
                    or existing["max_refinement_rounds"] != record.max_refinement_rounds
                ):
                    raise ValueError("run stop record cannot be rewritten")
                return record
            connection.execute(
                """INSERT INTO run_stop_records(
                    run_id,schema_version,terminal_status,stop_reason,stop_bound,
                    binding_bounds_json,rounds_used,max_refinement_rounds,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (record.run_id.value, record.schema_version, record.terminal_status.value,
                 record.stop_reason.value, record.stop_bound, payload, record.rounds_used,
                 record.max_refinement_rounds, now),
            )
        return record

    def get_run_stop(self, run_id: OpaqueId) -> RunStopRecord | None:
        row = self.connection.execute(
            "SELECT * FROM run_stop_records WHERE run_id=?", (run_id.value,),
        ).fetchone()
        if row is None:
            return None
        return RunStopRecord(
            schema_version=row["schema_version"], run_id=OpaqueId(row["run_id"]),
            terminal_status=RunStatus(row["terminal_status"]),
            stop_reason=RunStopReason(row["stop_reason"]), stop_bound=row["stop_bound"],
            binding_bounds=tuple(json.loads(row["binding_bounds_json"])),
            rounds_used=row["rounds_used"],
            max_refinement_rounds=row["max_refinement_rounds"],
        )

    def record_model_call(
        self, *, call_id: OpaqueId, run_id: OpaqueId, purpose: str,
        request_hash: str, result_hash: str | None, result: ModelResult,
        now: str, idempotency_key: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO model_calls(
                    call_id,schema_version,run_id,purpose,request_hash,result_hash,status,
                    provider,model_identifier,capabilities_json,input_tokens,output_tokens,
                    cost_microusd,retry_classification,created_at,idempotency_key,total_tokens,
                    usage_source,estimated_cost_microusd,pricing_snapshot_id,
                    provider_request_id,incomplete_reason
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (call_id.value, result.schema_version, run_id.value, purpose, request_hash,
                 result_hash, result.status.value, result.provider, result.model_identifier,
                 canonical_json(result.capabilities), result.usage.input_tokens,
                 result.usage.output_tokens, result.usage.estimated_cost_microusd or 0,
                 result.retry_classification, now, idempotency_key, result.usage.total_tokens,
                 result.usage.usage_source, result.usage.estimated_cost_microusd,
                 result.usage.pricing_snapshot_id.value if result.usage.pricing_snapshot_id else None,
                 result.provider_request_id, result.incomplete_reason),
            )

    def save_pricing_snapshot(
        self, snapshot: PricingSnapshot, *, canonical_json: str, now: str,
    ) -> PricingSnapshot:
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT content_hash,canonical_json FROM pricing_snapshots WHERE snapshot_id=?",
                (snapshot.snapshot_id.value,),
            ).fetchone()
            if existing:
                if existing["content_hash"] != snapshot.content_hash or existing["canonical_json"] != canonical_json:
                    raise ValueError("pricing snapshot ID cannot be rewritten")
                return snapshot
            connection.execute(
                """INSERT INTO pricing_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot.snapshot_id.value, snapshot.schema_version, snapshot.provider,
                    snapshot.model_identifier, snapshot.source, snapshot.captured_at,
                    snapshot.currency, snapshot.units,
                    snapshot.input_microusd_per_million_tokens,
                    snapshot.output_microusd_per_million_tokens,
                    snapshot.content_hash, canonical_json, now,
                ),
            )
        return snapshot

    def save_live_run_configuration(
        self, *, run_id: OpaqueId, configuration_id: OpaqueId, schema_version: str,
        provider: str, model_identifier: str, pricing_snapshot_id: OpaqueId,
        content_hash: str, canonical_json: str, now: str, role: str = "proposer",
    ) -> None:
        if role not in {"proposer", "verifier"}:
            raise ValueError("live run configuration role must be proposer or verifier")
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT content_hash,canonical_json FROM live_run_configurations WHERE run_id=? AND role=?",
                (run_id.value, role),
            ).fetchone()
            if existing:
                if existing["content_hash"] != content_hash or existing["canonical_json"] != canonical_json:
                    raise ValueError("live run configuration cannot be rewritten")
                return
            connection.execute(
                """INSERT INTO live_run_configurations(
                    run_id,role,configuration_id,schema_version,provider,model_identifier,
                    pricing_snapshot_id,content_hash,canonical_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id.value, role, configuration_id.value, schema_version, provider,
                    model_identifier, pricing_snapshot_id.value, content_hash,
                    canonical_json, now,
                ),
            )

    def list_live_run_configurations(self, run_id: OpaqueId) -> tuple[dict[str, object], ...]:
        return tuple(dict(row) for row in self.connection.execute(
            "SELECT * FROM live_run_configurations WHERE run_id=? ORDER BY role", (run_id.value,),
        ))

    def record_cost_estimate(self, estimate: CostEstimate, *, now: str) -> CostEstimate:
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM cost_estimates WHERE call_id=?", (estimate.call_id.value,),
            ).fetchone()
            if existing:
                if (
                    existing["pricing_snapshot_id"] != estimate.pricing_snapshot_id.value
                    or existing["input_token_estimate"] != estimate.input_token_estimate
                    or existing["output_token_estimate"] != estimate.output_token_estimate
                    or existing["estimated_cost_microusd"] != estimate.estimated_cost_microusd
                ):
                    raise ValueError("call cost estimate cannot be rewritten")
                return estimate
            connection.execute(
                "INSERT INTO cost_estimates VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    estimate.estimate_id.value, estimate.schema_version,
                    estimate.call_id.value, estimate.run_id.value,
                    estimate.pricing_snapshot_id.value, estimate.input_token_estimate,
                    estimate.output_token_estimate, estimate.estimated_cost_microusd, now,
                ),
            )
        return estimate

    def list_cost_estimates(self, run_id: OpaqueId) -> tuple[dict[str, object], ...]:
        return tuple(dict(row) for row in self.connection.execute(
            "SELECT * FROM cost_estimates WHERE run_id=? ORDER BY created_at,call_id",
            (run_id.value,),
        ))

    def list_model_calls(self, run_id: OpaqueId) -> tuple[dict[str, object], ...]:
        return tuple(dict(row) for row in self.connection.execute("SELECT * FROM model_calls WHERE run_id=? ORDER BY created_at,call_id", (run_id.value,)))

    def append_event(
        self, *, event_id: OpaqueId, aggregate_id: OpaqueId, event_type: str,
        payload_json: str, now: str, idempotency_key: str,
    ) -> None:
        with self.transaction() as connection:
            self._insert_event(
                connection, event_id=event_id.value, aggregate_id=aggregate_id.value,
                event_type=event_type, payload_json=payload_json, now=now,
                idempotency_key=idempotency_key,
            )

    def _insert_event(
        self, connection: sqlite3.Connection, *, event_id: str, aggregate_id: str,
        event_type: str, payload_json: str, now: str, idempotency_key: str,
    ) -> None:
        existing = connection.execute("SELECT * FROM semantic_events WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existing:
            if existing["aggregate_id"] != aggregate_id or existing["event_type"] != event_type or existing["payload_json"] != payload_json:
                raise ValueError("event idempotency key reused with different semantics")
            return
        connection.execute(
            "INSERT INTO semantic_events(event_id,schema_version,aggregate_id,event_type,payload_json,created_at,idempotency_key) VALUES(?,?,?,?,?,?,?)",
            (event_id, PHASE2_SCHEMA_VERSION, aggregate_id, event_type, payload_json, now, idempotency_key),
        )

    def timeline(self, aggregate_id: OpaqueId) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "schema_version": row["schema_version"], "sequence": row["sequence"],
                "event_id": row["event_id"], "aggregate_id": row["aggregate_id"],
                "event_type": row["event_type"], "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"], "idempotency_key": row["idempotency_key"],
            }
            for row in self.connection.execute("SELECT * FROM semantic_events WHERE aggregate_id=? ORDER BY sequence", (aggregate_id.value,))
        )

    @staticmethod
    def _run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            schema_version=row["schema_version"], run_id=OpaqueId(row["run_id"]),
            dossier_id=OpaqueId(row["dossier_id"]), dossier_hash=row["dossier_hash"],
            budget_id=OpaqueId(row["budget_id"]), status=RunStatus(row["status"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            schema_version=row["schema_version"], job_id=OpaqueId(row["job_id"]),
            run_id=OpaqueId(row["run_id"]), kind=row["kind"], status=JobStatus(row["status"]),
            idempotency_key=row["idempotency_key"], attempts=row["attempts"],
            max_attempts=row["max_attempts"], deadline_at=row["deadline_at"],
            lease_owner=row["lease_owner"], lease_until=row["lease_until"],
            payload_hash=row["payload_hash"], result_hash=row["result_hash"],
            round_index=row["round_index"],
        )

    @staticmethod
    def _proposal(row: sqlite3.Row) -> ProposalRecord:
        return ProposalRecord(
            schema_version=row["schema_version"], proposal_id=OpaqueId(row["proposal_id"]),
            run_id=OpaqueId(row["run_id"]), proposal_kind=row["proposal_kind"],
            artifact_hash=row["artifact_hash"], source_kind=row["source_kind"],
            source_id=row["source_id"],
            target_claim_id=OpaqueId(row["target_claim_id"]) if row["target_claim_id"] else None,
            disposition=row["disposition"],
        )

    @staticmethod
    def _budget(row: sqlite3.Row, now: str) -> BudgetSnapshot:
        elapsed = max(0, int((_parse(now) - _parse(row["started_at"])).total_seconds() * 1000))
        dimensions: list[str] = []
        if row["used_input_tokens"] >= row["max_input_tokens"]:
            dimensions.append("input_tokens")
        if row["used_output_tokens"] >= row["max_output_tokens"]:
            dimensions.append("output_tokens")
        if row["used_cost_microusd"] >= row["max_cost_microusd"]:
            dimensions.append("cost")
        if row["used_attempts"] >= row["max_attempts"]:
            dimensions.append("attempts")
        if elapsed >= row["max_wall_milliseconds"]:
            dimensions.append("time")
        limits = BudgetLimits(
            max_input_tokens=row["max_input_tokens"], max_output_tokens=row["max_output_tokens"],
            max_cost_microusd=row["max_cost_microusd"], max_wall_milliseconds=row["max_wall_milliseconds"],
            max_attempts=row["max_attempts"],
            max_refinement_rounds=row["max_refinement_rounds"],
        )
        # The refinement-round cap is deliberately NOT an ``exhausted_dimensions``
        # entry: ``reserve_call`` refuses any call once a dimension is exhausted,
        # and a run on its last permitted round must still be able to finish that
        # round. The cap is enforced by ``reserve_refinement_round`` instead.
        return BudgetSnapshot(
            budget_id=OpaqueId(row["budget_id"]), limits=limits,
            used_input_tokens=row["used_input_tokens"], used_output_tokens=row["used_output_tokens"],
            used_cost_microusd=row["used_cost_microusd"], used_attempts=row["used_attempts"],
            elapsed_milliseconds=elapsed, exhausted_dimensions=tuple(dimensions),
            used_refinement_rounds=row["used_refinement_rounds"],
        )


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
