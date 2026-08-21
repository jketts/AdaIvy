"""Frozen confirmatory evaluation over Phase 5 checked artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..phase5.quantum import DiagonalCase, run_case
from ..phase5.serialization import canonical_hash, stable_id
from . import generality
from .errors import GeneralitySuiteError, Phase6ValidationError
from .heldout import HeldOutView
from .workspace import Phase6Workspace

__all__ = [
    "ALLOWED_CAPABILITIES",
    "GeneralitySuiteError",
    "PROTOCOL_FIELDS",
    "Phase6Service",
    "Phase6ValidationError",
    "render_report",
]

PROTOCOL_FIELDS = {
    "schema_version", "protocol_id", "version", "phase", "benchmark_id",
    "phase5_fixture_hash", "heldout_case_ids", "allowed_capabilities", "metrics",
    "success_criteria", "stopping_rule", "baseline", "frozen_at", "frozen_by",
    "generality_suite_id", "generality_suite_hash",
}
ALLOWED_CAPABILITIES = {
    "execute_exact_diagonal_case", "read_frozen_case_only", "write_confirmatory_result",
}

ACCESS_RECORD_TYPE = "heldout_access"
VIOLATION_RECORD_TYPE = "heldout_access_violation"
SUITE_RECORD_TYPE = "generality_control_suite"
ACCESS_SCHEMA_VERSION = "adaivy.heldout-access.v1"

CONFIRMATORY_METHOD = {
    "adapter": "exact_diagonal_jrf_v1",
    "arithmetic": "fractions-exact",
    "selection": "protocol_frozen_before_access",
}


def render_report(release: Mapping[str, Any]) -> str:
    result = release["confirmatory_result"]
    suite = result["generality_controls"]
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
        f"- Held-out access record: `{release['heldout_access_record_id']}`",
        f"- Adaptations after held-out access: `{release['adaptations_after_access']}`",
        f"- Generality controls passed: `{release['controls_passed']}/{release['controls_total']}`",
        f"- Falsifiability probes flipped: `{release['probes_flipped']}/{release['probes_total']}`",
        f"- Phase 5 material results retained: `{release['material_result_count']}`",
        "",
        "## Generality control suite",
        "",
        f"- Suite: `{release['generality_suite_id']}`",
        f"- Suite hash: `{release['generality_suite_hash']}`",
        f"- Control corpus provenance: `{release['control_corpus_provenance']}`",
        f"- Positive control admitted: `{str(release['positive_control_admitted']).lower()}`",
        "",
        "| Control | Category | Polarity | Executed verdict | Probe flipped |",
        "|---|---|---|---|---|",
    ]
    for control in suite["controls"]:
        lines.append(
            f"| `{control['control_id']}` | `{control['category']}` | "
            f"`{control['polarity']}` | "
            f"`{'passed' if control['passed'] else 'failed'}` | "
            f"`{str(control['probe']['flipped']).lower()}` |"
        )
    lines.extend([
        "",
        "Every control above executed against Phase 1 trust policy, the exact "
        "Phase 5 diagonal engine, or the Phase 6 held-out capability boundary, and "
        "each carries a named single-field mutation of its own fixture that must "
        "produce the forbidden verdict. A control whose probe does not flip fails "
        "the suite.",
        "",
        f"The suite corpus is `{release['control_corpus_provenance']}`. It "
        "demonstrates boundary enforcement on known traps. It is not evidence of "
        "generality against unseen traps, and no rate of the form \"catches X per "
        "cent of unseen traps\" is computable from repository data.",
        "",
        "## Contributions",
        "",
    ])
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
    for limitation in release["release_limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


class Phase6Service:
    def __init__(
        self, workspace: Phase6Workspace, *, generality_suite_path: Path | None = None,
    ) -> None:
        self.workspace = workspace
        self.workspace.verify_integrity()
        self.generality_suite = generality.load_suite(generality_suite_path)
        self.generality_suite_hash = generality.suite_hash(self.generality_suite)

    # --- protocol -------------------------------------------------------

    def _validate_protocol(self, protocol: Mapping[str, Any], *, recorded_at: str) -> None:
        """Every confirmatory precondition, with no durable write.

        ADR-0034: the ordering is the enforcement. A rejected fixture, capability,
        suite, or held-out expansion must leave the append-only log untouched, so
        every check lives here and this method is called before the first append.
        """

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
        if protocol["generality_suite_id"] != self.generality_suite["suite_id"]:
            raise Phase6ValidationError("loaded generality suite is not the one the protocol froze")
        if protocol["generality_suite_hash"] != self.generality_suite_hash:
            raise Phase6ValidationError("generality suite hash differs from the frozen protocol")

    def _append_protocol(
        self, protocol: Mapping[str, Any], *, recorded_at: str,
    ) -> dict[str, Any]:
        return self.workspace.append(
            record_type="confirmatory_protocol", subject_id=str(protocol["protocol_id"]),
            record_id=str(protocol["protocol_id"]), recorded_at=recorded_at,
            payload={
                "protocol": dict(protocol), "protocol_hash": canonical_hash(protocol),
                "frozen": True,
            },
        )

    def freeze_protocol(self, protocol: Mapping[str, Any], *, recorded_at: str) -> dict[str, Any]:
        self._validate_protocol(protocol, recorded_at=recorded_at)
        return self._append_protocol(protocol, recorded_at=recorded_at)

    def _phase5_run(self, run_id: str) -> dict[str, Any]:
        rows = self.workspace.phase5.find("run", run_id)
        if len(rows) != 1:
            raise Phase6ValidationError("confirmatory evaluation requires one persisted Phase 5 run")
        return rows[0]

    # --- held-out access ledger ------------------------------------------

    def _access_records(self, benchmark_id: str, case_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            item for item in self.workspace.records(ACCESS_RECORD_TYPE)
            if item["payload"].get("benchmark_id") == benchmark_id
            and item["payload"].get("case_id") == case_id
        )

    def resolve_heldout_case(
        self, view: HeldOutView, case_id: str, *, recorded_at: str,
    ) -> dict[str, Any]:
        """Read one case through the frozen boundary, recording any refusal.

        Section 20 scenario L: the capability boundary blocks the access AND the
        policy violation is recorded. The record is appended before the error
        propagates, so a refused access is durable rather than a lost exception.
        """

        try:
            return view.case(case_id)
        except Phase6ValidationError:
            violation = dict(view.violations[-1])
            violation["schema_version"] = "adaivy.heldout-access-violation.v1"
            self.workspace.append(
                record_type=VIOLATION_RECORD_TYPE, subject_id=str(case_id),
                record_id=stable_id("violation.phase6", violation),
                recorded_at=recorded_at, payload=violation,
            )
            raise

    # --- confirmatory execution ------------------------------------------

    def confirm(
        self, *, protocol: Mapping[str, Any], phase5_fixture: Mapping[str, Any],
        phase5_run_id: str, recorded_at: str,
    ) -> dict[str, Any]:
        # ---- validation. Nothing below writes until every check has passed. --
        self._validate_protocol(protocol, recorded_at=recorded_at)
        if canonical_hash(phase5_fixture) != protocol["phase5_fixture_hash"]:
            raise Phase6ValidationError("held-out fixture hash differs from the frozen protocol")
        if set(phase5_fixture) != {"schema_version", "benchmark_id", "cases"}:
            raise Phase6ValidationError("held-out fixture shape differs")
        if phase5_fixture["benchmark_id"] != protocol["benchmark_id"]:
            raise Phase6ValidationError("held-out fixture is for another benchmark")
        phase5_run = self._phase5_run(phase5_run_id)
        if phase5_run["payload"]["fixture_hash"] != protocol["phase5_fixture_hash"]:
            raise Phase6ValidationError("Phase 5 exploratory run used another fixture")
        material = self.workspace.phase5.material_results(phase5_run_id)
        if not material:
            raise Phase6ValidationError("confirmatory evaluation requires the Phase 5 material-result trace")
        selected_id = str(protocol["heldout_case_ids"][0])
        benchmark_id = str(protocol["benchmark_id"])
        # The view drops every non-frozen case, so nothing below can read one.
        view = HeldOutView(
            benchmark_id=benchmark_id, cases=phase5_fixture["cases"],
            frozen_case_ids=(selected_id,),
        )
        protocol_hash = canonical_hash(protocol)
        method_hash = canonical_hash(CONFIRMATORY_METHOD)
        access_payload = {
            "schema_version": ACCESS_SCHEMA_VERSION,
            "benchmark_id": benchmark_id,
            "case_id": selected_id,
            "protocol_id": str(protocol["protocol_id"]),
            "protocol_hash": protocol_hash,
            "stopping_rule": str(protocol["stopping_rule"]),
            "allowed_capabilities": sorted(ALLOWED_CAPABILITIES),
            "method_hash_frozen_before_access": method_hash,
        }
        access_id = stable_id(
            "access.phase6", {"benchmark_id": benchmark_id, "case_id": selected_id}
        )
        prior = [
            item for item in self._access_records(benchmark_id, selected_id)
            if item["record_id"] == access_id
        ]
        if prior and prior[0]["payload"] != access_payload:
            raise Phase6ValidationError(
                "the frozen held-out case was already accessed under a different protocol "
                "or method; the one-pass stopping rule forbids a second access"
            )
        # Pure: no held-out data, no clock, no durable state.
        suite_result = generality.run_suite(self.generality_suite)

        # ---- durable execution ------------------------------------------
        protocol_record = self._append_protocol(protocol, recorded_at=recorded_at)
        access_record = self.workspace.append(
            record_type=ACCESS_RECORD_TYPE, subject_id=selected_id, record_id=access_id,
            recorded_at=recorded_at, payload=access_payload,
        )
        suite_record = self.workspace.append(
            record_type=SUITE_RECORD_TYPE, subject_id=str(suite_result["suite_id"]),
            record_id=stable_id("suite.phase6", suite_result),
            recorded_at=recorded_at, payload=suite_result,
        )
        accesses = self._access_records(benchmark_id, selected_id)
        first_access_at = min(item["recorded_at"] for item in accesses)
        adaptations = sorted(
            str(item["payload"]["protocol"]["protocol_id"])
            for item in self.workspace.records("confirmatory_protocol")
            if str(item["payload"]["protocol"]["frozen_at"]) > first_access_at
        )
        access_manifest = {
            "allowed_capabilities": sorted(ALLOWED_CAPABILITIES),
            "heldout_case_ids_exposed": list(view.visible_case_ids),
            "access_count": len(accesses),
            "access_record_ids": sorted(item["record_id"] for item in accesses),
            "first_access_recorded_at": first_access_at,
            "exploratory_result_access_during_execution": False,
            "method_hash_frozen_before_access": method_hash,
            "adaptations_after_access": len(adaptations),
            "adaptation_protocol_ids": adaptations,
            "refused_access_count": len(view.violations),
        }
        selected = self.resolve_heldout_case(view, selected_id, recorded_at=recorded_at)
        case_result = run_case(DiagonalCase.from_value(selected))
        controls_passed = int(suite_result["controls_passed"])
        controls_total = int(suite_result["controls_total"])
        probes_flipped = int(suite_result["probes_flipped"])
        probes_total = int(suite_result["probes_total"])
        primal_dual_agreement = (
            case_result["independent_primal_optimum"] == case_result["independent_dual_optimum"]
        )
        passed = (
            primal_dual_agreement
            and controls_passed == controls_total
            and probes_flipped == probes_total
            and bool(suite_result["positive_control_admitted"])
            and access_manifest["access_count"] == 1
            and access_manifest["adaptations_after_access"] == 0
        )
        result = {
            "schema_version": "adaivy.confirmatory-result.v2",
            "case_id": selected_id,
            "status": "passed" if passed else "failed",
            "case_result_hash": case_result["result_hash"],
            "exact_feasibility": True,
            "independent_primal_dual_agreement": primal_dual_agreement,
            "generality_controls": suite_result,
            "generality_suite_id": suite_result["suite_id"],
            "generality_suite_hash": suite_result["suite_hash"],
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
                "method": dict(CONFIRMATORY_METHOD), "access_manifest": access_manifest,
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
            "schema_version": "adaivy.phase6-release-package.v2",
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
            "heldout_access_record_id": access_record["record_id"],
            "heldout_access_violation_records": len(
                self.workspace.records(VIOLATION_RECORD_TYPE)
            ),
            "adaptations_after_access": access_manifest["adaptations_after_access"],
            "generality_suite_id": suite_result["suite_id"],
            "generality_suite_hash": suite_result["suite_hash"],
            "generality_suite_record_id": suite_record["record_id"],
            "control_corpus_provenance": suite_result["control_corpus_provenance"],
            "controls_passed": controls_passed,
            "controls_total": controls_total,
            "probes_flipped": probes_flipped,
            "probes_total": probes_total,
            "positive_control_admitted": suite_result["positive_control_admitted"],
            "positive_control_ids": suite_result["positive_control_ids"],
            "generality_categories_covered": suite_result["categories_covered"],
            "generality_control_verdicts": [
                {
                    "control_id": item["control_id"],
                    "category": item["category"],
                    "polarity": item["polarity"],
                    "engine": item["engine"],
                    "passed": item["passed"],
                    "probe_id": item["probe"]["probe_id"],
                    "probe_flipped": item["probe"]["flipped"],
                }
                for item in suite_result["controls"]
            ],
            "material_result_count": len(material),
            "negative_and_superseded_attempts_retained": True,
            "baseline_comparison": {
                "capability": "trust_boundary_rejections",
                "simplest_baseline_passed": 0,
                "phase6_passed": suite_result["negative_controls_passed"],
                "positive_controls_passed": suite_result["positive_controls_passed"],
                "probes_flipped": probes_flipped,
                "additional_external_cost_usd": 0,
                "additional_expert_actions": 0,
                "is_generality_measure": False,
                "interpretation": (
                    "A count of boundary rejections the arithmetic-only baseline does "
                    "not make, on project-authored traps. It is NOT a generality rate "
                    "and must not be read as one."
                ),
            },
            "release_limitations": [
                "Exact commuting/diagonal case only.",
                "No universal noncommuting QD-FS-01 resolution.",
                "Novelty and significance remain unassessed.",
                *suite_result["limitations"],
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
