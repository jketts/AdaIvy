"""Run the frozen Phase 0 comparison and render evidence artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .adapters import file_baseline, omdoc, probes
from .canonical import canonical_bytes, semantic_result_hash
from .catalog import CANDIDATES, WEIGHTS, empty_scores, weighted_score
from .process import find_executable
from .scorecard import derive_correction, render_correction
from .validation import validate_dossier


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _mutate(value: Any, dotted_path: str, replacement: Any) -> None:
    cursor = value
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
    final = parts[-1]
    if isinstance(cursor, list):
        cursor[int(final)] = replacement
    else:
        cursor[final] = replacement


def evaluate_negative_fixtures(repo_root: Path, dossier: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted((repo_root / "fixtures" / "phase0").glob("negative-*.json")):
        fixture = load_json(path)
        candidate = copy.deepcopy(dossier)
        for mutation in fixture["mutations"]:
            _mutate(candidate, mutation["path"], mutation["value"])
        codes = {issue.code for issue in validate_dossier(candidate, verify_hash=False)}
        expected = set(fixture["expected_issue_codes"])
        results.append(
            {
                "fixture": str(path.relative_to(repo_root)),
                "expected_issue_codes": sorted(expected),
                "observed_issue_codes": sorted(codes),
                "passed": expected <= codes,
            }
        )
    return results


def _inventory_only(candidate: dict[str, Any]) -> dict[str, Any]:
    hard_gates = list(candidate.get("hard_gates", ["local_spike_not_selected"]))
    return {
        "status": "deferred" if candidate["recommendation"] in {"defer", "reference"} else "blocked",
        "summary": "No local executable spike was selected; public artifacts were inventoried and no capability score was inferred.",
        "scores": empty_scores(
            license_clarity=candidate.get("license_score", 0),
            maintenance_evidence=candidate.get("maintenance_score", 0),
        ),
        "hard_gates": hard_gates,
        "evidence": {"inventory": "docs/phase-0/COMPONENT_INVENTORY.md"},
        "duration_ms": 0.0,
    }


def run_evaluation(repo_root: Path, report_dir: Path | None = None) -> dict[str, Any]:
    report_dir = report_dir or repo_root / "reports" / "phase-0"
    artifact_root = report_dir / "artifacts"
    report_dir.mkdir(parents=True, exist_ok=True)
    artifact_root.mkdir(parents=True, exist_ok=True)

    dossier_path = repo_root / "fixtures" / "phase0" / "reference-dossier.json"
    dossier = load_json(dossier_path)
    dossier_issues = validate_dossier(dossier)
    if dossier_issues:
        raise ValueError(f"reference dossier invalid: {[issue.as_dict() for issue in dossier_issues]}")

    adapter_map = {
        "file": lambda output: file_baseline.evaluate(dossier, output),
        "omdoc": lambda output: omdoc.evaluate(dossier, output),
        "albilich": lambda output: probes.evaluate_albilich(dossier, output, repo_root),
        "why3": lambda output: probes.evaluate_why3(dossier, output, repo_root),
        "lean": lambda output: probes.evaluate_lean(dossier, output, repo_root),
        "paperqa": lambda output: probes.evaluate_paperqa(dossier, output, repo_root),
    }

    component_results: list[dict[str, Any]] = []
    for candidate in CANDIDATES:
        output_dir = artifact_root / candidate["id"]
        output_dir.mkdir(parents=True, exist_ok=True)
        adapter = adapter_map.get(candidate.get("adapter", ""))
        measured = adapter(output_dir) if adapter else _inventory_only(candidate)
        result = {
            "component_id": candidate["id"],
            "name": candidate["name"],
            "category": candidate["category"],
            "license": candidate["license"],
            "recommendation": candidate["recommendation"],
            **measured,
        }
        result["measurements"] = {
            "wall_ms": result["duration_ms"],
            "external_processes": 0
            if candidate["id"] in {"file-baseline", "omdoc-projection"} or result["status"] in {"blocked", "deferred"}
            else 1,
            "model_calls": 0,
            "model_cost_usd": 0.0,
            "expert_review_minutes": None,
            "expert_review_status": "not_performed_phase0",
        }
        result["weighted_score"] = weighted_score(result["scores"])
        result["semantic_result_hash"] = semantic_result_hash(result)
        component_results.append(result)

    baseline_score = component_results[0]["weighted_score"]
    for result in component_results:
        delta = round(result["weighted_score"] - baseline_score, 1)
        result["comparison_to_file_baseline"] = {
            "score_delta": delta,
            "score_relation": "higher" if delta > 0 else "equal" if delta == 0 else "lower",
            "baseline_score": baseline_score,
            "candidate_score": result["weighted_score"],
        }

    negative_results = evaluate_negative_fixtures(repo_root, dossier)
    payload = {
        "schema_version": "0.1.0-phase0",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "reference_dossier": str(dossier_path.relative_to(repo_root)),
        "reference_dossier_hash": dossier["content_hash"],
        "rubric": {"scores": [0, 1, 2], "weights": WEIGHTS},
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "executables": {
                name: find_executable(name)
                for name in ("git", "why3", "lean", "lake", "elan", "docker", "cargo", "deno")
            },
        },
        "negative_fixtures": negative_results,
        "components": component_results,
        "checks_passed": all(item["passed"] for item in negative_results)
        and component_results[0]["status"] == "succeeded"
        and component_results[1]["status"] == "partial",
    }
    results_path = report_dir / "results.json"
    raw_bytes = canonical_bytes(payload) + b"\n"
    results_path.write_bytes(raw_bytes)
    correction = derive_correction(payload, raw_sha256=hashlib.sha256(raw_bytes).hexdigest())
    (report_dir / "evaluation-correction.json").write_bytes(canonical_bytes(correction) + b"\n")
    (report_dir / "scorecard.md").write_text(render_correction(correction), encoding="utf-8")
    return payload


def render_scorecard(payload: dict[str, Any]) -> str:
    """Deprecated renderer retained only to interpret historical raw results."""
    lines = [
        "# Phase 0 Measured Scorecard",
        "",
        f"Reference dossier: `{payload['reference_dossier_hash']}`  ",
        f"Observed: {payload['observed_at']}  ",
        "Scores use the frozen rubric in `docs/phase-0/COMPONENT_SCORECARD.md`. A low score means capability was not demonstrated locally; it is not a claim that the upstream system lacks it.",
        "No model calls or paid services were used. Expert review time is explicitly unmeasured (`null`) for this engineering spike.",
        "",
        "| Component | Status | Score | vs file | Decision | Hard gates/blockers |",
        "|---|---:|---:|---:|---|---|",
    ]
    for result in payload["components"]:
        gates = ", ".join(result["hard_gates"]) or "none"
        delta = result["comparison_to_file_baseline"]["score_delta"]
        lines.append(
            f"| {result['name']} | {result['status']} | {result['weighted_score']:.1f} | {delta:+.1f} | {result['recommendation']} | {gates} |"
        )
    lines.extend(["", "## Rejection-fixture checks", ""])
    for fixture in payload["negative_fixtures"]:
        outcome = "PASS" if fixture["passed"] else "FAIL"
        lines.append(f"- **{outcome}** `{fixture['fixture']}` — observed `{', '.join(fixture['observed_issue_codes'])}`")
    lines.extend(["", "## Interpretation", ""])
    lines.append("The file baseline is the only complete local interchange result. The OMDoc projection preserves the target and replays losslessly only because the JSON sidecar remains canonical. Optional proof-state, literature, obligation, and formal-tool probes are blockers on this host unless their prerequisites are explicitly supplied; no missing integration was counted as a pass.")
    lines.append("")
    return "\n".join(lines)
