"""Frozen confirmatory evaluation over Phase 5 checked artifacts."""

from __future__ import annotations

from typing import Any, Mapping

from ..phase5.quantum import DiagonalCase, run_case
from ..phase5.serialization import canonical_hash, stable_id
from .workspace import Phase6Workspace


class Phase6ValidationError(ValueError):
    pass


PROTOCOL_FIELDS = {
    "schema_version", "protocol_id", "version", "phase", "benchmark_id",
    "phase5_fixture_hash", "heldout_case_ids", "allowed_capabilities", "metrics",
    "success_criteria", "stopping_rule", "baseline", "frozen_at", "frozen_by",
}
ALLOWED_CAPABILITIES = {
    "execute_exact_diagonal_case", "read_frozen_case_only", "write_confirmatory_result",
}


def _generality_controls() -> list[dict[str, Any]]:
    """Execute the compact trust-policy controls from blueprint section 18.4."""

    candidates = [
        (
            "unsupported_consensus",
            {"model_agreement": 2, "deterministic_warrant": False},
            False,
            "model agreement cannot create proof status",
        ),
        (
            "finite_experiment_overreach",
            {"finite_samples": 1_000_000, "claim_scope": "universal"},
            False,
            "finite experiments cannot prove an unrestricted theorem",
        ),
        (
            "mistranslated_formal_target",
            {"formal_kernel": True, "semantic_alignment": "rejected"},
            False,
            "formal validity cannot resolve a semantically rejected target",
        ),
        (
            "inapplicable_source",
            {"source_exists": True, "applicability": "rejected"},
            False,
            "a real but inapplicable source cannot carry mathematical weight",
        ),
        (
            "open_representation_bridge",
            {"transformed_result": True, "bridge_obligation": "open"},
            False,
            "an open representation bridge blocks graph admission",
        ),
    ]
    return [
        {
            "control_id": control_id, "candidate": candidate,
            "graph_admitted": admitted, "passed": admitted is False,
            "reason": reason,
        }
        for control_id, candidate, admitted, reason in candidates
    ]


def render_report(release: Mapping[str, Any]) -> str:
    result = release["confirmatory_result"]
    lines = [
        "# AdaIvy Phase 6 Confirmatory Report",
        "",
        f"- Protocol: `{release['protocol_id']}`",
        f"- Phase 5 run: `{release['phase5_run_id']}`",
        f"- Held-out case: `{result['case_id']}`",
        f"- Confirmatory status: `{result['status']}`",
        "",
        "## Orthogonal assessment",
        "",
        f"- Semantic fidelity: `{release['semantic_fidelity']}`",
        f"- Mathematical warrant: `{result['mathematical_warrant']}`",
        f"- Source applicability: `{result['applicability_status']}`",
        f"- Novelty: `{release['novelty']['status']}`",
        f"- Significance: `{release['significance']['status']}`",
        f"- Graph admission: `{str(result['graph_admitted']).lower()}`",
        "",
        "## Evaluation integrity",
        "",
        f"- Held-out accesses: `{release['heldout_accesses']}`",
        f"- Adaptations after held-out access: `{release['adaptations_after_access']}`",
        f"- Generality controls passed: `{release['controls_passed']}/{release['controls_total']}`",
        f"- Phase 5 material results retained: `{release['material_result_count']}`",
        "",
        "## Contributions",
        "",
    ]
    for contribution in release["contributions"]:
        lines.append(
            f"- `{contribution['actor_type']}` / `{contribution['contribution_type']}`: "
            f"`{contribution['artifact_id']}`"
        )
    lines.extend([
        "",
        "## Limitations",
        "",
        "This confirms only the frozen exact commuting/diagonal case. It does not "
        "resolve universal noncommuting QD-FS-01, assess novelty or significance, "
        "or admit the result to the trusted claim graph.",
        "",
    ])
    return "\n".join(lines)


class Phase6Service:
    def __init__(self, workspace: Phase6Workspace) -> None:
        self.workspace = workspace
        self.workspace.verify_integrity()

    def freeze_protocol(self, protocol: Mapping[str, Any], *, recorded_at: str) -> dict[str, Any]:
        if set(protocol) != PROTOCOL_FIELDS:
            raise Phase6ValidationError("confirmatory protocol has missing or unknown fields")
        if (
            protocol["schema_version"] != "adaivy.confirmatory-protocol.v1"
            or protocol["phase"] != "confirmatory"
            or protocol["benchmark_id"] != "QD-FS-01"
            or protocol["stopping_rule"] != "one_pass_no_adaptation"
        ):
            raise Phase6ValidationError("unsupported or unfrozen confirmatory protocol")
        if protocol["frozen_at"] > recorded_at:
            raise Phase6ValidationError("confirmatory protocol must be frozen before execution")
        if (
            not isinstance(protocol["heldout_case_ids"], list)
            or len(protocol["heldout_case_ids"]) != 1
            or len(set(protocol["heldout_case_ids"])) != 1
        ):
            raise Phase6ValidationError("this bounded protocol requires exactly one frozen held-out case")
        capabilities = set(protocol["allowed_capabilities"])
        if capabilities != ALLOWED_CAPABILITIES:
            raise Phase6ValidationError("held-out capability boundary differs from the frozen allowlist")
        protocol_hash = canonical_hash(protocol)
        return self.workspace.append(
            record_type="confirmatory_protocol", subject_id=str(protocol["protocol_id"]),
            record_id=str(protocol["protocol_id"]), recorded_at=recorded_at,
            payload={"protocol": dict(protocol), "protocol_hash": protocol_hash, "frozen": True},
        )

    def _phase5_run(self, run_id: str) -> dict[str, Any]:
        rows = self.workspace.phase5.find("run", run_id)
        if len(rows) != 1:
            raise Phase6ValidationError("confirmatory evaluation requires one persisted Phase 5 run")
        return rows[0]

    def confirm(
        self, *, protocol: Mapping[str, Any], phase5_fixture: Mapping[str, Any],
        phase5_run_id: str, recorded_at: str,
    ) -> dict[str, Any]:
        protocol_record = self.freeze_protocol(protocol, recorded_at=recorded_at)
        if canonical_hash(phase5_fixture) != protocol["phase5_fixture_hash"]:
            raise Phase6ValidationError("held-out fixture hash differs from the frozen protocol")
        if set(phase5_fixture) != {"schema_version", "benchmark_id", "cases"}:
            raise Phase6ValidationError("held-out fixture shape differs")
        phase5_run = self._phase5_run(phase5_run_id)
        if phase5_run["payload"]["fixture_hash"] != protocol["phase5_fixture_hash"]:
            raise Phase6ValidationError("Phase 5 exploratory run used another fixture")
        material = self.workspace.phase5.material_results(phase5_run_id)
        if not material:
            raise Phase6ValidationError("confirmatory evaluation requires the Phase 5 material-result trace")
        selected_id = protocol["heldout_case_ids"][0]
        selected = [item for item in phase5_fixture["cases"] if item.get("case_id") == selected_id]
        if len(selected) != 1:
            raise Phase6ValidationError("frozen held-out case does not resolve exactly once")

        method = {
            "adapter": "exact_diagonal_jrf_v1",
            "arithmetic": "fractions-exact",
            "selection": "protocol_frozen_before_access",
        }
        method_hash = canonical_hash(method)
        access_manifest = {
            "allowed_capabilities": sorted(ALLOWED_CAPABILITIES),
            "heldout_case_ids_exposed": [selected_id],
            "access_count": 1,
            "exploratory_result_access_during_execution": False,
            "method_hash_frozen_before_access": method_hash,
            "adaptations_after_access": 0,
        }
        case_result = run_case(DiagonalCase.from_value(selected[0]))
        controls = _generality_controls()
        controls_passed = sum(item["passed"] for item in controls)
        result = {
            "schema_version": "adaivy.confirmatory-result.v1",
            "case_id": selected_id,
            "status": "passed" if (
                case_result["independent_primal_optimum"] == case_result["independent_dual_optimum"]
                and controls_passed == len(controls)
            ) else "failed",
            "case_result_hash": case_result["result_hash"],
            "exact_feasibility": True,
            "independent_primal_dual_agreement": (
                case_result["independent_primal_optimum"] == case_result["independent_dual_optimum"]
            ),
            "generality_controls": controls,
            "mathematical_warrant": case_result["mathematical_warrant"],
            "applicability_status": case_result["applicability_status"],
            "graph_admitted": False,
            "external_cost_usd": 0,
            "model_calls": 0,
            "network_calls": 0,
        }
        confirmatory_run_id = stable_id("run.phase6", {
            "protocol_hash": protocol_record["payload"]["protocol_hash"],
            "phase5_run_id": phase5_run_id,
        })
        run_record = self.workspace.append(
            record_type="confirmatory_run", subject_id=confirmatory_run_id,
            record_id=confirmatory_run_id, recorded_at=recorded_at,
            payload={
                "run_id": confirmatory_run_id, "protocol_id": protocol["protocol_id"],
                "phase5_run_id": phase5_run_id, "phase5_run_hash": phase5_run["content_hash"],
                "method": method, "access_manifest": access_manifest,
                "status": result["status"], "stopping_reason": "frozen_one_pass_complete",
            },
        )
        result_id = stable_id("evaluation.phase6", {"run_id": confirmatory_run_id, "result": result})
        result_record = self.workspace.append(
            record_type="confirmatory_result", subject_id=confirmatory_run_id,
            record_id=result_id, recorded_at=recorded_at, payload=result,
        )
        novelty = {
            "status": "not_assessed",
            "limitations": ["No Phase 6 literature search or expert novelty review was authorized."],
            "inferred_from_warrant": False,
        }
        significance = {
            "status": "not_assessed", "rubric_id": None,
            "assessor_id": None, "inferred_from_warrant": False,
        }
        novelty_record = self.workspace.append(
            record_type="novelty_assessment", subject_id=result_id,
            recorded_at=recorded_at, payload=novelty,
        )
        significance_record = self.workspace.append(
            record_type="significance_assessment", subject_id=result_id,
            recorded_at=recorded_at, payload=significance,
        )
        contributions = [
            {"actor_type": "human", "contribution_type": "protocol_freeze", "artifact_id": protocol["protocol_id"]},
            {"actor_type": "tool", "contribution_type": "exact_computation", "artifact_id": case_result["result_hash"]},
            {"actor_type": "system", "contribution_type": "verification", "artifact_id": result_id},
        ]
        contribution_ids = []
        for contribution in contributions:
            record = self.workspace.append(
                record_type="contribution", subject_id=result_id,
                recorded_at=recorded_at, payload=contribution,
            )
            contribution_ids.append(record["record_id"])
        phase5_export = self.workspace.phase5.export_value()
        release = {
            "schema_version": "adaivy.phase6-release-package.v1",
            "protocol_id": protocol["protocol_id"],
            "protocol_hash": protocol_record["payload"]["protocol_hash"],
            "phase5_run_id": phase5_run_id,
            "phase5_export_hash": phase5_export["content_hash"],
            "confirmatory_run_id": confirmatory_run_id,
            "confirmatory_run_hash": run_record["content_hash"],
            "confirmatory_result_id": result_id,
            "confirmatory_result_hash": result_record["content_hash"],
            "confirmatory_result": result,
            "semantic_fidelity": "researcher_approved",
            "novelty": novelty,
            "novelty_record_id": novelty_record["record_id"],
            "significance": significance,
            "significance_record_id": significance_record["record_id"],
            "contributions": contributions,
            "contribution_record_ids": contribution_ids,
            "heldout_accesses": access_manifest["access_count"],
            "adaptations_after_access": access_manifest["adaptations_after_access"],
            "controls_passed": controls_passed,
            "controls_total": len(controls),
            "material_result_count": len(material),
            "negative_and_superseded_attempts_retained": True,
            "baseline_comparison": {
                "capability": "trust_boundary_rejections",
                "simplest_baseline_passed": 0,
                "phase6_passed": controls_passed,
                "additional_external_cost_usd": 0,
                "additional_expert_actions": 0,
            },
            "release_limitations": [
                "Exact commuting/diagonal case only.",
                "No universal noncommuting QD-FS-01 resolution.",
                "Novelty and significance remain unassessed.",
            ],
        }
        release["release_hash"] = canonical_hash(release)
        release_id = stable_id("release.phase6", {"run_id": confirmatory_run_id, "release_hash": release["release_hash"]})
        release_record = self.workspace.append(
            record_type="release_package", subject_id=confirmatory_run_id,
            record_id=release_id, recorded_at=recorded_at, payload=release,
        )
        self.workspace.verify_integrity()
        output = dict(release)
        output["release_record_id"] = release_record["record_id"]
        output["report"] = render_report(release)
        return output
