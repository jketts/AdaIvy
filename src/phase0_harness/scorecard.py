"""Corrected, dimensional interpretation of immutable Phase 0 observations."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes

CORRECTION_SCHEMA_VERSION = "0.2.0-phase0-scorecard"
CAPABILITY_WEIGHTS = {
    "target_fidelity": 3,
    "applicability_separation": 3,
    "obligations_and_failures": 3,
    "evidence_warrant_typing": 3,
    "exportability": 2,
    "replay_determinism": 2,
    "verifier_reconstruction": 2,
}


def _license_status(component: dict[str, Any]) -> str:
    license_text = component["license"].lower()
    blockers = set(component.get("hard_gates", []))
    if "license_absent" in blockers or license_text == "noassertion":
        return "absent"
    if "modification_not_permitted" in blockers:
        return "restrictive"
    if "unresolved" in license_text or "unlicensed" in license_text:
        return "unresolved"
    if license_text in {
        "no_public_code",
        "no_public_official_code",
        "no_reusable_code_identified",
        "method/paper",
    }:
        return "not_applicable_to_runnable_code"
    return "identified"


def _evaluation_status(status: str) -> str:
    return {
        "succeeded": "evaluated_complete",
        "partial": "evaluated_partial",
        "failed": "evaluated_failed",
        "blocked": "not_evaluated_blocked",
        "deferred": "not_evaluated_deferred",
    }[status]


def _runnability(status: str) -> str:
    return {
        "succeeded": "runnable",
        "partial": "runnable_with_limitations",
        "failed": "attempted_but_failed",
        "blocked": "unavailable_on_observed_host",
        "deferred": "not_attempted",
    }[status]


def _capability_score(component: dict[str, Any]) -> float | None:
    if component["status"] in {"blocked", "deferred"}:
        return None
    scores = component["scores"]
    numerator = sum(scores[key] * weight for key, weight in CAPABILITY_WEIGHTS.items())
    denominator = 2 * sum(CAPABILITY_WEIGHTS.values())
    return round(numerator / denominator * 100, 1)


def _integration_effort(component: dict[str, Any]) -> dict[str, Any] | None:
    if component["status"] in {"blocked", "deferred"}:
        return None
    score = component["scores"]["setup_review_cost"]
    return {
        "observed_level": {2: "low", 1: "moderate", 0: "high_or_failed"}[score],
        "frozen_observation": score,
        "wall_ms": component["measurements"]["wall_ms"],
        "expert_review_minutes": component["measurements"]["expert_review_minutes"],
    }


def derive_correction(raw: dict[str, Any], *, raw_sha256: str) -> dict[str, Any]:
    corrected: list[dict[str, Any]] = []
    baseline_score: float | None = None
    for component in raw["components"]:
        capability_score = _capability_score(component)
        if component["component_id"] == "file-baseline":
            baseline_score = capability_score
        corrected.append(
            {
                "component_id": component["component_id"],
                "name": component["name"],
                "evaluation_status": _evaluation_status(component["status"]),
                "runnability": _runnability(component["status"]),
                "capability_score": capability_score,
                "measured_capability": (
                    {key: component["scores"][key] for key in CAPABILITY_WEIGHTS}
                    if capability_score is not None
                    else None
                ),
                "integration_effort": _integration_effort(component),
                "evidence_completeness": {
                    "succeeded": "complete_for_selected_spike",
                    "partial": "partial_for_selected_spike",
                    "failed": "failed_run_evidence_retained",
                    "blocked": "prerequisite_evidence_only",
                    "deferred": "inventory_only",
                }[component["status"]],
                "license_status": _license_status(component),
                "license_observation": component["license"],
                "blockers": list(component["hard_gates"]),
                "recommendation": component["recommendation"],
                "raw_semantic_result_hash": component["semantic_result_hash"],
            }
        )
    if baseline_score is None:
        raise ValueError("file baseline lacks an executed capability score")
    for component in corrected:
        score = component["capability_score"]
        component["comparison_to_file_baseline"] = (
            None
            if score is None
            else {
                "baseline_score": baseline_score,
                "candidate_score": score,
                "score_delta": round(score - baseline_score, 1),
            }
        )
    return {
        "schema_version": CORRECTION_SCHEMA_VERSION,
        "source": {
            "path": "reports/phase-0/results.json",
            "sha256": raw_sha256,
            "schema_version": raw["schema_version"],
            "observed_at": raw["observed_at"],
        },
        "capability_weights": CAPABILITY_WEIGHTS,
        "components": corrected,
    }


def render_correction(correction: dict[str, Any]) -> str:
    lines = [
        "# Phase 0 Corrected Scorecard",
        "",
        f"Raw observation SHA-256: `{correction['source']['sha256']}`  ",
        f"Observed: {correction['source']['observed_at']}  ",
        "Blocked and deferred candidates were not evaluated. Their capability and baseline comparison are `null`.",
        "",
        "| Component | Evaluation | Runnability | Capability | Effort | Evidence | License | vs file | Recommendation | Blockers |",
        "|---|---|---|---:|---|---|---|---:|---|---|",
    ]
    for item in correction["components"]:
        score = "null" if item["capability_score"] is None else f"{item['capability_score']:.1f}"
        effort = "null" if item["integration_effort"] is None else item["integration_effort"]["observed_level"]
        comparison = item["comparison_to_file_baseline"]
        delta = "null" if comparison is None else f"{comparison['score_delta']:+.1f}"
        blockers = ", ".join(item["blockers"]) or "none"
        lines.append(
            f"| {item['name']} | {item['evaluation_status']} | {item['runnability']} | {score} | {effort} | "
            f"{item['evidence_completeness']} | {item['license_status']} | {delta} | {item['recommendation']} | {blockers} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The file baseline is the only complete executed interchange result. The OMDoc projection is an executed partial result whose lossless replay depends on the canonical JSON sidecar. All other entries retain blockers or deferral evidence without a capability ranking.",
            "",
            "The historical aggregate `weighted_score` fields remain only in the immutable raw result and must not be used for adoption decisions.",
            "",
        ]
    )
    return "\n".join(lines)


def write_correction(raw_path: Path, output_path: Path, scorecard_path: Path) -> dict[str, Any]:
    raw_bytes = raw_path.read_bytes()
    import json

    raw = json.loads(raw_bytes)
    correction = derive_correction(raw, raw_sha256=hashlib.sha256(raw_bytes).hexdigest())
    output_path.write_bytes(canonical_bytes(correction) + b"\n")
    scorecard_path.write_text(render_correction(correction), encoding="utf-8")
    return correction
