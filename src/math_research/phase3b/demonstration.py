"""Production-slice acceptance run using only repository-authored requests."""

from __future__ import annotations

import json
from pathlib import Path

from . import RUNTIME_DIGEST
from .adapter import DockerLeanAdapter
from .interchange import export_workspace, import_trusted_replay
from .records import ExecutionLimits, FormalCheckOutcome
from .serialization import canonical_bytes
from .service import FormalCheckingService
from .workspace import FormalCheckWorkspace

FIXED_TIME = "2026-08-19T00:00:00Z"
FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "phase3b"


def run_acceptance(workspace_root: Path, output_dir: Path) -> dict[str, object]:
    cases = (
        ("valid", DockerLeanAdapter(), FormalCheckOutcome.KERNEL_CHECKED),
        ("placeholder", DockerLeanAdapter(), FormalCheckOutcome.POLICY_REJECTION),
        ("axiom", DockerLeanAdapter(), FormalCheckOutcome.KERNEL_CHECKED_UNAPPROVED_ASSUMPTIONS),
        ("approved-axioms", DockerLeanAdapter(), FormalCheckOutcome.KERNEL_CHECKED_APPROVED_AXIOMS),
        ("malformed", DockerLeanAdapter(), FormalCheckOutcome.POLICY_REJECTION),
        ("meaning-test", DockerLeanAdapter(), FormalCheckOutcome.MEANING_TEST_FAILURE),
        ("timeout", DockerLeanAdapter(ExecutionLimits(wall_milliseconds=1)), FormalCheckOutcome.TIMEOUT),
        ("output-limit", DockerLeanAdapter(ExecutionLimits(combined_output_bytes=1)), FormalCheckOutcome.OUTPUT_LIMIT),
        ("sandbox", DockerLeanAdapter(expected_digest="sha256:" + "0" * 64), FormalCheckOutcome.SANDBOX_FAILURE),
    )
    results: list[dict[str, object]] = []
    with FormalCheckWorkspace(workspace_root) as workspace:
        for fixture, adapter, expected in cases:
            source = (FIXTURES / f"{fixture}.json").read_bytes()
            finding = FormalCheckingService(adapter).check(source, created_at=FIXED_TIME)
            workspace.save_attempt(source, finding)
            results.append({
                "fixture": fixture, "expected": expected.value, "observed": finding.outcome.value,
                "passed": finding.outcome is expected, "finding_id": finding.id.value,
                "content_hash": finding.content_hash,
            })
        output_dir.mkdir(parents=True, exist_ok=True)
        export_path = output_dir / "formal-checking.json"
        export_hash = export_workspace(workspace, export_path)
    replayed = import_trusted_replay(export_path.read_bytes())
    replay_path = output_dir / "formal-checking-replay.json"
    replay_path.write_bytes(canonical_bytes(replayed) + b"\n")
    summary: dict[str, object] = {
        "schema_version": "1.0.0", "status": "passed" if all(bool(item["passed"]) for item in results) else "failed",
        "runtime_digest": RUNTIME_DIGEST, "results": results, "export_hash": export_hash,
        "restart_replay_preserved": import_trusted_replay(replay_path.read_bytes()) == replayed,
        "formal_findings_are_proposals": True, "trust_promotions": 0,
        "adaivy_model_calls": 0, "adaivy_external_api_calls": 0,
    }
    (output_dir / "acceptance.json").write_bytes(canonical_bytes(summary) + b"\n")
    return summary
