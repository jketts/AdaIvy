from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Any

from ..process import find_executable, run_bounded


def _blocked(summary: str, scores: dict[str, int], blocker: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {"status": "blocked", "summary": summary, "scores": scores, "hard_gates": [blocker], "evidence": evidence, "duration_ms": 0.0}


def evaluate_albilich(dossier: dict[str, Any], output_dir: Path, repo_root: Path) -> dict[str, Any]:
    scores = _base_scores(license_score=2, maintenance_score=2)
    configured = os.environ.get("ALBILICH_ROOT")
    candidate_root = Path(configured) if configured else repo_root / "third_party" / "albilich"
    if not (candidate_root / "agents" / "generation" / "phase2" / "cli.py").exists():
        return _blocked(
            "Albilich was not vendored or configured; no proof-state round-trip was claimed.", scores,
            "albilich_repository_unavailable",
            {"looked_for": [str(candidate_root)], "configuration": "ALBILICH_ROOT"},
        )
    started = time.monotonic()
    probe = run_bounded([sys.executable, "-m", "agents.generation.phase2.cli", "--help"], cwd=candidate_root)
    if probe["exit_code"] == 0:
        scores["local_offline"] = 1
        scores["setup_review_cost"] = 1
    return {
        "status": "partial" if probe["exit_code"] == 0 else "failed",
        "summary": "CLI availability was exercised, but Albilich has no demonstrated ResearchDossier import/export adapter in this repository.",
        "scores": scores,
        "hard_gates": ["dossier_round_trip_not_demonstrated"],
        "evidence": {"repository": str(candidate_root), "probe": probe},
        "duration_ms": round((time.monotonic() - started) * 1000, 3),
    }


def evaluate_why3(dossier: dict[str, Any], output_dir: Path, repo_root: Path) -> dict[str, Any]:
    scores = _base_scores(license_score=2, maintenance_score=2)
    executable = find_executable("why3")
    if not executable:
        return _blocked("Why3 is not installed; the obligation fixture remains open.", scores, "why3_executable_missing", {"executable": "why3", "fixture": "spikes/why3/even_sum.mlw"})
    started = time.monotonic()
    fixture = repo_root / "spikes" / "why3" / "even_sum.mlw"
    first = run_bounded([executable, "prove", str(fixture)], cwd=output_dir)
    second = run_bounded([executable, "prove", str(fixture)], cwd=output_dir)
    succeeded = first["exit_code"] == 0 and second["exit_code"] == 0
    if succeeded:
        scores.update({"target_fidelity": 2, "obligations_and_failures": 1, "exportability": 1, "replay_determinism": 2 if first["stdout"] == second["stdout"] else 1, "verifier_reconstruction": 2, "local_offline": 2, "security_boundary": 1, "setup_review_cost": 1})
    return {"status": "succeeded" if succeeded else "failed", "summary": "Why3 dispatches the exact integer obligation; its result remains a candidate verifier artifact until bridge/import checks exist.", "scores": scores, "hard_gates": ["dossier_import_not_implemented"], "evidence": {"fixture": str(fixture), "first": first, "replay": second}, "duration_ms": round((time.monotonic() - started) * 1000, 3)}


def evaluate_lean(dossier: dict[str, Any], output_dir: Path, repo_root: Path) -> dict[str, Any]:
    scores = _base_scores(license_score=2, maintenance_score=2)
    executable = find_executable("lean")
    if not executable:
        return _blocked("Lean is not installed; no formal warrant was manufactured.", scores, "lean_executable_missing", {"executable": "lean", "fixture": "spikes/lean/EvenSum.lean"})
    started = time.monotonic()
    fixture = repo_root / "spikes" / "lean" / "EvenSum.lean"
    first = run_bounded([executable, str(fixture)], cwd=output_dir)
    second = run_bounded([executable, str(fixture)], cwd=output_dir)
    source = fixture.read_text(encoding="utf-8")
    placeholders = any(token in source for token in ("sorry", "admit", "axiom"))
    succeeded = first["exit_code"] == 0 and second["exit_code"] == 0 and not placeholders
    if succeeded:
        scores.update({"target_fidelity": 2, "evidence_warrant_typing": 1, "exportability": 1, "replay_determinism": 2 if first["stdout"] == second["stdout"] else 1, "verifier_reconstruction": 2, "local_offline": 2, "security_boundary": 1, "setup_review_cost": 1})
    return {"status": "succeeded" if succeeded else "failed", "summary": "Lean checks an exact integer theorem with no placeholders; semantic alignment and local warrant import remain separate open work.", "scores": scores, "hard_gates": ["formal_warrant_import_not_implemented"], "evidence": {"fixture": str(fixture), "placeholder_detected": placeholders, "first": first, "replay": second}, "duration_ms": round((time.monotonic() - started) * 1000, 3)}


def evaluate_paperqa(dossier: dict[str, Any], output_dir: Path, repo_root: Path) -> dict[str, Any]:
    scores = _base_scores(license_score=2, maintenance_score=2)
    if importlib.util.find_spec("paperqa") is None:
        return _blocked("PaperQA2 is not installed; no network or model-backed substitute was run.", scores, "paperqa_package_missing", {"module": "paperqa", "network_attempted": False, "credentials_used": False})
    started = time.monotonic()
    code = "import importlib.metadata as m; print(m.version('paper-qa'))"
    first = run_bounded([sys.executable, "-c", code], cwd=output_dir)
    if first["exit_code"] == 0:
        scores.update({"local_offline": 1, "license_clarity": 2, "maintenance_evidence": 2, "setup_review_cost": 1})
    return {"status": "partial" if first["exit_code"] == 0 else "failed", "summary": "Only local package/version availability was tested; literature retrieval and applicability remain deliberately untested without a pinned model/index environment.", "scores": scores, "hard_gates": ["citation_card_export_not_demonstrated"], "evidence": {"probe": first, "network_attempted": False, "credentials_used": False}, "duration_ms": round((time.monotonic() - started) * 1000, 3)}


def _base_scores(*, license_score: int, maintenance_score: int) -> dict[str, int]:
    from ..catalog import empty_scores

    return empty_scores(license_clarity=license_score, maintenance_evidence=maintenance_score)
