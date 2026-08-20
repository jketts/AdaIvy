"""Production-slice acceptance run using only repository-authored requests."""

from __future__ import annotations

import json
import shutil
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


def runtime_preflight() -> dict[str, object]:
    """Report why the sealed runtime is unusable, before any fixture runs.

    Every fixture failing with `sandbox_failure` is the correct fail-closed
    outcome when the ADR-0016 v5 image is absent, but on its own it does not say
    so. This distinguishes an absent engine, an absent or mismatched image, and a
    usable runtime. It inspects only; it never runs a checker, touches a finding,
    or enters any content hash.
    """
    if shutil.which("docker") is None:
        return {
            "runtime_available": False,
            "blocker": "container_engine_absent",
            "detail": "the docker executable is not on PATH, so every fixture will "
                      "fail closed as sandbox_failure",
        }
    available, diagnostic = DockerLeanAdapter()._inspect_runtime()
    if available:
        return {"runtime_available": True, "blocker": None, "detail": ""}
    return {
        "runtime_available": False,
        "blocker": "runtime_image_unavailable",
        "detail": diagnostic,
    }


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
    preflight = runtime_preflight()
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
        "runtime_preflight": preflight,
    }
    (output_dir / "acceptance.json").write_bytes(canonical_bytes(summary) + b"\n")
    return summary
