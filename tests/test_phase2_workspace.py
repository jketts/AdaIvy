from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from math_research.domain.entities import oid
from math_research.interchange import export_dossier_bytes
from math_research.phase2.artifacts import ArtifactIntegrityError, FileArtifactStore
from math_research.phase2.fixtures import build_open_theorem_dossier
from math_research.phase2.records import BudgetLimits, JobStatus, RunStatus
from math_research.phase2.sqlite_workspace import BudgetExhausted, LateCommitRejected, MigrationError, SQLiteWorkspace


NOW = "2026-08-19T00:00:00.000000Z"
LATER = "2026-08-19T00:00:01.000000Z"
DEADLINE = "2026-08-19T00:01:00.000000Z"


class WorkspaceCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.dossier = build_open_theorem_dossier()
        self.run_id = oid("run.workspace.test.v1")
        self.limits = BudgetLimits(
            max_input_tokens=1000, max_output_tokens=1000,
            max_cost_microusd=1000, max_wall_milliseconds=60_000,
            max_attempts=3,
        )
        self.run = self.workspace.create_run(
            run_id=self.run_id, dossier=self.dossier,
            budget_id=oid("budget.workspace.test.v1"), limits=self.limits, now=NOW,
        )
        self.workspace.set_run_status(
            self.run_id, RunStatus.RUNNING.value, now=NOW,
            idempotency_key="workspace-run-running",
        )

    def tearDown(self) -> None:
        self.workspace.close()
        self.temporary.cleanup()


class SQLiteWorkspaceTests(WorkspaceCase):
    def test_foreign_keys_and_wal_are_enabled(self) -> None:
        self.assertEqual(self.workspace.pragmas, {"foreign_keys": 1, "journal_mode": "wal"})

    def test_atomic_semantic_commit_rolls_back_as_a_unit(self) -> None:
        with self.assertRaises(RuntimeError):
            with self.workspace.transaction() as connection:
                connection.execute(
                    "INSERT INTO semantic_events(event_id,schema_version,aggregate_id,event_type,payload_json,created_at,idempotency_key) VALUES(?,?,?,?,?,?,?)",
                    ("event.rollback", "2.0.0", self.run_id.value, "test", "{}", NOW, "rollback-key"),
                )
                raise RuntimeError("inject rollback")
        count = self.workspace.connection.execute(
            "SELECT COUNT(*) FROM semantic_events WHERE idempotency_key='rollback-key'"
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_events_are_append_only_and_idempotent(self) -> None:
        kwargs = dict(
            event_id=oid("event.idempotent.v1"), aggregate_id=self.run_id,
            event_type="observed", payload_json='{"value":1}', now=NOW,
            idempotency_key="semantic-observation-v1",
        )
        self.workspace.append_event(**kwargs)
        self.workspace.append_event(**kwargs)
        observed = [item for item in self.workspace.timeline(self.run_id) if item["idempotency_key"] == "semantic-observation-v1"]
        self.assertEqual(len(observed), 1)
        with self.assertRaises(ValueError):
            self.workspace.append_event(**{**kwargs, "payload_json": '{"value":2}'})


class MigrationTests(unittest.TestCase):
    def test_fresh_upgrade_restart_and_checksum_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            migrations = root / "migrations"
            shutil.copytree(Path("migrations"), migrations)
            path = root / "workspace.sqlite3"
            first = SQLiteWorkspace(path, migrations_dir=migrations)
            self.assertEqual(first.migration_versions, ("0001", "0002", "0003"))
            first.close()
            second = SQLiteWorkspace(path, migrations_dir=migrations)
            self.assertEqual(second.migration_versions, ("0001", "0002", "0003"))
            second.close()
            migration = migrations / "0002_phase2_indexes.sql"
            migration.write_text(migration.read_text(encoding="utf-8") + "\n-- drift\n", encoding="utf-8")
            with self.assertRaises(MigrationError):
                SQLiteWorkspace(path, migrations_dir=migrations)


class ArtifactStoreTests(unittest.TestCase):
    def test_atomic_put_get_and_hash_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = FileArtifactStore(Path(temporary))
            first = store.put(b"same bytes", media_type="text/plain")
            second = store.put(b"same bytes", media_type="text/plain")
            self.assertEqual(first.content_hash, second.content_hash)
            self.assertEqual(store.get(first.content_hash), b"same bytes")
            target = store._path(first.content_hash)
            target.write_bytes(b"corrupt")
            with self.assertRaises(ArtifactIntegrityError):
                store.get(first.content_hash)


class DurableJobTests(WorkspaceCase):
    def test_lease_retry_deadline_and_idempotent_enqueue(self) -> None:
        job = self.workspace.enqueue_job(
            job_id=oid("job.lease.v1"), run_id=self.run_id, kind="test",
            idempotency_key="lease-job", payload_hash="sha256:" + "1" * 64,
            max_attempts=2, deadline_at=DEADLINE, now=NOW,
        )
        duplicate = self.workspace.enqueue_job(
            job_id=oid("job.lease.duplicate.v1"), run_id=self.run_id, kind="test",
            idempotency_key="lease-job", payload_hash="sha256:" + "1" * 64,
            max_attempts=2, deadline_at=DEADLINE, now=NOW,
        )
        self.assertEqual(job.job_id, duplicate.job_id)
        claimed = self.workspace.claim_job(
            run_id=self.run_id, kind="test", worker_id="worker-a",
            lease_until=LATER, now=NOW,
        )
        self.assertEqual(claimed.status, JobStatus.RUNNING)
        recovered = self.workspace.recover_jobs(now="2026-08-19T00:00:02.000000Z")
        self.assertEqual(next(item for item in recovered if item.job_id == job.job_id).status, JobStatus.RETRYABLE)
        claimed_again = self.workspace.claim_job(
            run_id=self.run_id, kind="test", worker_id="worker-b",
            lease_until="2026-08-19T00:00:03.000000Z", now="2026-08-19T00:00:02.000000Z",
        )
        self.assertEqual(claimed_again.attempts, 2)
        timed_out = self.workspace.recover_jobs(now=DEADLINE)
        self.assertEqual(next(item for item in timed_out if item.job_id == job.job_id).status, JobStatus.TIMED_OUT)


class BudgetTests(WorkspaceCase):
    def test_each_budget_dimension_prevents_further_calls(self) -> None:
        # Attempts.
        budget = self.run.budget_id
        for _ in range(self.limits.max_attempts):
            self.workspace.reserve_call(budget, estimated_input_tokens=0, estimated_output_tokens=0, now=NOW)
        with self.assertRaises(BudgetExhausted) as attempts:
            self.workspace.reserve_call(budget, estimated_input_tokens=0, estimated_output_tokens=0, now=NOW)
        self.assertIn("attempts", attempts.exception.dimensions)

        cases = (
            ("input_tokens", BudgetLimits(max_input_tokens=0, max_output_tokens=10, max_cost_microusd=10, max_wall_milliseconds=10_000, max_attempts=2), 1, 0, NOW),
            ("output_tokens", BudgetLimits(max_input_tokens=10, max_output_tokens=0, max_cost_microusd=10, max_wall_milliseconds=10_000, max_attempts=2), 0, 1, NOW),
            ("cost", BudgetLimits(max_input_tokens=10, max_output_tokens=10, max_cost_microusd=0, max_wall_milliseconds=10_000, max_attempts=2), 0, 0, NOW),
            ("time", BudgetLimits(max_input_tokens=10, max_output_tokens=10, max_cost_microusd=10, max_wall_milliseconds=1, max_attempts=2), 0, 0, LATER),
        )
        for index, (dimension, limits, input_estimate, output_estimate, observed_now) in enumerate(cases):
            run_id = oid(f"run.budget.case.{index}")
            created = self.workspace.create_run(
                run_id=run_id, dossier=self.dossier, budget_id=oid(f"budget.case.{index}"),
                limits=limits, now=NOW,
            )
            with self.assertRaises(BudgetExhausted) as raised:
                self.workspace.reserve_call(
                    created.budget_id, estimated_input_tokens=input_estimate,
                    estimated_output_tokens=output_estimate, now=observed_now,
                )
            self.assertIn(dimension, raised.exception.dimensions)


class WorkflowControlTests(WorkspaceCase):
    def test_late_success_is_rejected(self) -> None:
        job = self.workspace.enqueue_job(
            job_id=oid("job.late.v1"), run_id=self.run_id, kind="late",
            idempotency_key="late-job", payload_hash="sha256:" + "2" * 64,
            max_attempts=1, deadline_at=LATER, now=NOW,
        )
        self.workspace.claim_job(
            run_id=self.run_id, kind="late", worker_id="worker",
            lease_until=LATER, now=NOW,
        )
        self.workspace.recover_jobs(now=LATER)
        with self.assertRaises(LateCommitRejected):
            self.workspace.finish_job(
                job.job_id, worker_id="worker", status=JobStatus.SUCCEEDED.value,
                result_hash="sha256:" + "3" * 64, now=LATER,
                idempotency_key="late-success",
            )

    def test_pause_restart_resume_and_cancel(self) -> None:
        paused = self.workspace.set_run_status(self.run_id, RunStatus.PAUSED.value, now=NOW, idempotency_key="pause-command")
        self.assertEqual(paused.status, RunStatus.PAUSED)
        self.workspace.close()
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        resumed = self.workspace.set_run_status(self.run_id, RunStatus.RUNNING.value, now=LATER, idempotency_key="resume-command")
        self.assertEqual(resumed.status, RunStatus.RUNNING)
        cancelled = self.workspace.set_run_status(self.run_id, RunStatus.CANCELLED.value, now=LATER, idempotency_key="cancel-command")
        self.assertEqual(cancelled.status, RunStatus.CANCELLED)
