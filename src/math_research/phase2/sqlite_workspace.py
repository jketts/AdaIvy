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
    RunRecord,
    RunStatus,
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


class SQLiteWorkspace:
    def __init__(self, path: Path, *, migrations_dir: Path | None = None) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrations_dir = migrations_dir or Path(__file__).resolve().parents[3] / "migrations"
        self.connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = FULL")
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteWorkspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
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
            statements = [item.strip() for item in data.decode("utf-8").split(";") if item.strip()]
            with self.transaction() as connection:
                for statement in statements:
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES(?,?,?)",
                    (version, checksum, _now()),
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
                return self._run(existing)
            connection.execute(
                "INSERT INTO budgets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    budget_id.value, PHASE2_SCHEMA_VERSION, limits.max_input_tokens,
                    limits.max_output_tokens, limits.max_cost_microusd,
                    limits.max_wall_milliseconds, limits.max_attempts,
                    0, 0, 0, 0, now, now,
                ),
            )
            connection.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)",
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
                RunStatus.RUNNING: {RunStatus.PAUSED, RunStatus.AWAITING_REVIEW, RunStatus.UNRESOLVED, RunStatus.CANCELLED, RunStatus.COMPLETED},
                RunStatus.PAUSED: {RunStatus.RUNNING, RunStatus.CANCELLED},
                RunStatus.AWAITING_REVIEW: {RunStatus.CANCELLED},
                RunStatus.UNRESOLVED: {RunStatus.CANCELLED},
                RunStatus.CANCELLED: set(),
                RunStatus.COMPLETED: set(),
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
    ) -> JobRecord:
        with self.transaction() as connection:
            existing = connection.execute("SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing:
                if existing["run_id"] != run_id.value or existing["kind"] != kind or existing["payload_hash"] != payload_hash:
                    raise ValueError("job idempotency key reused with different semantics")
                return self._job(existing)
            connection.execute(
                "INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id.value, PHASE2_SCHEMA_VERSION, run_id.value, kind, JobStatus.QUEUED.value,
                 idempotency_key, payload_hash, 0, max_attempts, deadline_at, None, None, None, now, now),
            )
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id.value,)).fetchone()
            assert row is not None
            return self._job(row)

    def claim_job(
        self, *, run_id: OpaqueId, kind: str, worker_id: str, lease_until: str, now: str,
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
            row = connection.execute(
                "SELECT * FROM jobs WHERE run_id=? AND kind=? AND status IN ('queued','retryable') AND attempts<max_attempts AND deadline_at>? ORDER BY created_at,job_id LIMIT 1",
                (run_id.value, kind, now),
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
        with self.transaction() as connection:
            existing = connection.execute("SELECT canonical_json FROM verifier_manifests WHERE run_id=?", (manifest.run_id.value,)).fetchone()
            if existing and existing["canonical_json"] != canonical_json:
                raise ValueError("verifier manifest is immutable")
            connection.execute(
                "INSERT OR IGNORE INTO verifier_manifests VALUES(?,?,?,?,?,?)",
                (manifest.manifest_id.value, manifest.schema_version, manifest.run_id.value,
                 canonical_json, manifest.serialized_context_hash, now),
            )
        return manifest

    def get_manifest(self, run_id: OpaqueId) -> VerifierContextManifest:
        row = self.connection.execute("SELECT canonical_json FROM verifier_manifests WHERE run_id=?", (run_id.value,)).fetchone()
        if row is None:
            raise KeyError(run_id.value)
        value = json.loads(row["canonical_json"])
        independence = VerifierIndependence(**value["independence"])
        return VerifierContextManifest(
            schema_version=value["schema_version"], manifest_id=OpaqueId(value["manifest_id"]),
            run_id=OpaqueId(value["run_id"]), included_entity_ids=tuple(OpaqueId(item) for item in value["included_entity_ids"]),
            excluded_entity_ids=tuple(OpaqueId(item) for item in value["excluded_entity_ids"]),
            policy_version=value["policy_version"], serialized_context_hash=value["serialized_context_hash"],
            context_artifact_hash=value["context_artifact_hash"], independence=independence,
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
        content_hash: str, canonical_json: str, now: str,
    ) -> None:
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT content_hash,canonical_json FROM live_run_configurations WHERE run_id=?",
                (run_id.value,),
            ).fetchone()
            if existing:
                if existing["content_hash"] != content_hash or existing["canonical_json"] != canonical_json:
                    raise ValueError("live run configuration cannot be rewritten")
                return
            connection.execute(
                "INSERT INTO live_run_configurations VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    run_id.value, configuration_id.value, schema_version, provider,
                    model_identifier, pricing_snapshot_id.value, content_hash,
                    canonical_json, now,
                ),
            )

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
        )
        return BudgetSnapshot(
            budget_id=OpaqueId(row["budget_id"]), limits=limits,
            used_input_tokens=row["used_input_tokens"], used_output_tokens=row["used_output_tokens"],
            used_cost_microusd=row["used_cost_microusd"], used_attempts=row["used_attempts"],
            elapsed_milliseconds=elapsed, exhausted_dimensions=tuple(dimensions),
        )


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
