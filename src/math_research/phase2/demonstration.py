"""Reproducible Phase 2 acceptance demonstration."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..domain.entities import OpaqueId, oid
from ..interchange import write_dossier
from .artifacts import FileArtifactStore
from .baseline_loop import BaselineResearchLoop, InjectedCrash, deterministic_fake_results
from .external_backend import ExternalBackendService, FilesystemProcessBackend
from .fixtures import build_open_theorem_dossier
from .model_gateway import ScriptedModelGateway
from .records import BudgetLimits, RunStatus, VerifierIndependence
from .reporting import durable_report_data, render_durable_report, report_hash
from .serialization import canonical_json, public_value, sha256_bytes
from .sqlite_workspace import SQLiteWorkspace


class DemoClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def text(self) -> str:
        return self.value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    def advance(self, *, seconds: int = 0, milliseconds: int = 0) -> None:
        self.value += timedelta(seconds=seconds, milliseconds=milliseconds)


def _limits() -> BudgetLimits:
    return BudgetLimits(
        max_input_tokens=30_000, max_output_tokens=5_000,
        max_cost_microusd=10_000_000, max_wall_milliseconds=600_000,
        max_attempts=6,
    )


def _independence() -> VerifierIndependence:
    return VerifierIndependence(
        context_isolated=True, separate_model_call=True,
        different_model=False, different_provider=False,
        deterministic_checker=False, independently_implemented_checker=False,
        formal_kernel=False,
    )


def _fake_loop(workspace: SQLiteWorkspace, artifacts: FileArtifactStore, clock: DemoClock, *, duplicate_proposer: bool = False, fault: bool = False) -> BaselineResearchLoop:
    dossier = build_open_theorem_dossier()
    proposer, verifier = deterministic_fake_results(
        dossier.formalization.target_claim_id.value,
        dossier.formalization.assumption_claim_ids[0].value,
    )
    gateway = ScriptedModelGateway({
        "proposer": [proposer, proposer] if duplicate_proposer else [proposer],
        "verifier": [verifier],
    })
    loop = BaselineResearchLoop(
        workspace=workspace, artifacts=artifacts,
        proposer=gateway, verifier=gateway, independence=_independence(),
        now=clock, fault_after_proposal_artifact_once=fault,
    )
    setattr(loop, "_demo_gateway", gateway)
    return loop


def run_demonstration(output_dir: Path) -> dict[str, object]:
    output_dir = output_dir.resolve()
    if (output_dir / "workspace.sqlite3").exists():
        raise RuntimeError("demonstration workspace already exists; choose a clean output directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = FileArtifactStore(output_dir / "artifacts")
    workspace = SQLiteWorkspace(output_dir / "workspace.sqlite3")
    clock = DemoClock()
    dossier = build_open_theorem_dossier()

    # 1. Deterministic fake provider end to end.
    main_loop = _fake_loop(workspace, artifacts, clock)
    main_run = main_loop.start(run_id=oid("run.phase2.demo.fake.v1"), dossier=dossier, limits=_limits())
    main_final = main_loop.run_to_terminal(main_run.run_id)
    clock.advance(milliseconds=1)

    # 2. Pause, close the database, reopen, resume, and finish.
    pause_loop = _fake_loop(workspace, artifacts, clock)
    pause_run = pause_loop.start(run_id=oid("run.phase2.demo.pause.v1"), dossier=dossier, limits=_limits())
    paused = pause_loop.pause(pause_run.run_id)
    workspace.close()
    workspace = SQLiteWorkspace(output_dir / "workspace.sqlite3")
    observed_after_restart = workspace.get_run(pause_run.run_id)
    resumed_loop = _fake_loop(workspace, artifacts, clock)
    resumed = resumed_loop.resume(pause_run.run_id)
    resumed_final = resumed_loop.run_to_terminal(pause_run.run_id)
    clock.advance(milliseconds=1)

    # 3. Crash after the CAS write, expire the lease, recover, and commit once.
    crash_loop = _fake_loop(workspace, artifacts, clock, duplicate_proposer=True, fault=True)
    crash_run = crash_loop.start(run_id=oid("run.phase2.demo.crash.v1"), dossier=dossier, limits=_limits())
    crash_observed = False
    try:
        crash_loop.advance(crash_run.run_id)
    except InjectedCrash:
        crash_observed = True
    gateway = getattr(crash_loop, "_demo_gateway")
    proposals_before_recovery = len(workspace.list_proposals(crash_run.run_id))
    clock.advance(seconds=31)
    workspace.close()
    workspace = SQLiteWorkspace(output_dir / "workspace.sqlite3")
    recovered_jobs = workspace.recover_jobs(now=clock.text())
    recovered_loop = BaselineResearchLoop(
        workspace=workspace, artifacts=artifacts,
        proposer=gateway, verifier=gateway, independence=_independence(), now=clock,
    )
    crash_final = recovered_loop.run_to_terminal(crash_run.run_id)
    crash_proposals = workspace.list_proposals(crash_run.run_id)
    crash_events = workspace.timeline(crash_run.run_id)
    clock.advance(milliseconds=1)

    # 4/5. Rejected malicious package followed by successful proposal-only import.
    external_loop = _fake_loop(workspace, artifacts, clock)
    external_run = external_loop.start(run_id=oid("run.phase2.demo.external.v1"), dossier=dossier, limits=_limits())
    backend = FilesystemProcessBackend(output_dir / "backend-runs", artifacts)
    service = ExternalBackendService(workspace=workspace, artifacts=artifacts, backend=backend, now=clock.text)
    fixture = Path(__file__).resolve().parents[3] / "fixtures" / "phase2" / "external_backend_fixture.py"
    failed_backend = service.run(
        run_id=external_run.run_id, backend_run_id=oid("backend.phase2.demo.failed.v1"),
        command=(sys.executable, str(fixture), "traversal"),
    )
    successful_backend = service.run(
        run_id=external_run.run_id, backend_run_id=oid("backend.phase2.demo.success.v1"),
        command=(sys.executable, str(fixture), "success"),
    )

    # 6. Regenerate report and canonical dossier after a clean database reopen.
    report_path = output_dir / "traceable-report.md"
    dossier_path = output_dir / "accepted-dossier.json"
    first_report = render_durable_report(workspace, main_run.run_id)
    first_report_hash = report_hash(workspace, main_run.run_id)
    report_path.write_text(first_report, encoding="utf-8")
    write_dossier(workspace.load_dossier(main_run.dossier_id), dossier_path)
    main_data = durable_report_data(workspace, main_run.run_id)
    migration_versions = workspace.migration_versions
    workspace.close()
    workspace = SQLiteWorkspace(output_dir / "workspace.sqlite3")
    regenerated_report = render_durable_report(workspace, main_run.run_id)
    regenerated_hash = report_hash(workspace, main_run.run_id)

    live_status: dict[str, object] = {
        "schema_version": "2.0.0", "status": "blocked",
        "blocker": "use the explicit live-gate command with a run configuration and pinned pricing snapshot",
        "missing_environment_variables": [] if os.environ.get("OPENAI_API_KEY") else ["OPENAI_API_KEY"],
        "missing_configuration_variables": ["provider", "model_identifier", "pricing_snapshot_id"],
        "calls_recorded": 0, "estimated_cost_microusd": None,
    }

    artifact_hashes = sorted({
        item.artifact_hash for item in workspace.list_proposals(main_run.run_id)
    } | {
        str(item["request_hash"]) for item in workspace.list_model_calls(main_run.run_id)
    } | {
        str(item["result_hash"]) for item in workspace.list_model_calls(main_run.run_id)
    })
    evidence: dict[str, object] = {
        "schema_version": "2.0.0",
        "fake_provider": {
            "run_id": main_run.run_id.value,
            "status": main_final.status.value,
            "model_calls": len(workspace.list_model_calls(main_run.run_id)),
            "proposal_count": len(workspace.list_proposals(main_run.run_id)),
            "accepted_dossier_hash": main_run.dossier_hash,
            "accepted_target_status": main_data["accepted_dossier"]["logical_status"],
        },
        "pause_restart_resume": {
            "paused_status": paused.status.value,
            "status_after_restart": observed_after_restart.status.value,
            "resumed_status": resumed.status.value,
            "final_status": resumed_final.status.value,
        },
        "crash_recovery": {
            "injected_crash_observed": crash_observed,
            "proposals_before_recovery": proposals_before_recovery,
            "recovered_job_statuses": sorted({item.status.value for item in recovered_jobs if item.run_id == crash_run.run_id}),
            "final_status": crash_final.status.value,
            "semantic_proposal_count": len(crash_proposals),
            "proposal_import_event_count": sum(item["event_type"] == "proposal_imported" for item in crash_events),
        },
        "external_backend": {
            "failed_import": failed_backend,
            "successful_import": successful_backend,
            "successful_dispositions": [item.disposition for item in workspace.list_proposals(external_run.run_id)],
        },
        "migrations": {
            "applied_versions": migration_versions,
            "foreign_keys": workspace.pragmas["foreign_keys"],
            "journal_mode": workspace.pragmas["journal_mode"],
        },
        "model_context_isolation": workspace.get_manifest(main_run.run_id),
        "report_replay": {
            "first_hash": first_report_hash,
            "regenerated_hash": regenerated_hash,
            "byte_identical": first_report == regenerated_report,
        },
        "replay_hashes": {
            "accepted_dossier_hash": main_run.dossier_hash,
            "audit_event_replay_hash": main_data["audit_replay_hash"],
            "artifact_hashes": artifact_hashes,
            "report_hash": regenerated_hash,
        },
        "live_provider": live_status,
    }
    (output_dir / "demonstration.json").write_text(
        json.dumps(public_value(evidence), indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    (output_dir / "live-provider-status.json").write_text(
        json.dumps(public_value(live_status), indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    workspace.close()
    return evidence
