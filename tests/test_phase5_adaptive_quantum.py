from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from math_research.phase5.quantum import DiagonalCase, QuantumInputError, run_case
from math_research.phase5.service import Phase5Service
from math_research.phase5.workspace import Phase5ValidationError, Phase5Workspace


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "fixtures/phase5/quantum-diagonal-v1.json").read_text("utf-8"))
T0 = "2026-08-20T12:00:00Z"
T1 = "2026-08-20T12:01:00Z"


class ExactQuantumTests(unittest.TestCase):
    def test_boundary_fixed_point_is_exactly_nonoptimal(self) -> None:
        result = run_case(DiagonalCase.from_value(FIXTURE["cases"][0]))
        self.assertTrue(result["fixed_point"])
        self.assertTrue(result["nonoptimal_fixed_point"])
        self.assertEqual("1/3", result["primal_dual_gap"])
        self.assertFalse(result["graph_admitted"])

    def test_full_support_scalar_has_optimal_closed_form_accumulation_point(self) -> None:
        result = run_case(DiagonalCase.from_value(FIXTURE["cases"][1]))
        self.assertTrue(result["initial_full_support"])
        self.assertTrue(result["closed_form_accumulation_point_optimal"])
        self.assertEqual("2/3", result["independent_primal_optimum"])
        self.assertEqual(result["independent_primal_optimum"], result["independent_dual_optimum"])

    def test_qd_fs_01_rejects_singular_initial_component(self) -> None:
        value = dict(FIXTURE["cases"][1])
        value["initial_povm"] = [[1], [0]]
        with self.assertRaises(QuantumInputError):
            run_case(DiagonalCase.from_value(value))


class Phase5WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_run_restart_steering_and_export_are_reproducible(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            first = service.run_quantum_fixture(FIXTURE, recorded_at=T0)
            second = service.run_quantum_fixture(FIXTURE, recorded_at=T0)
            self.assertEqual(first, second)
            self.assertEqual(3, first["branch_count"])
            self.assertEqual(1, len(first["material_result_event_ids"]))
            event_id = first["material_result_event_ids"][0]
            action = service.steer(
                event_id=event_id, action="acknowledge",
                principal_id="principal.phase5.owner", capability_id="capability.phase5.steer",
                idempotency_key="steer.phase5.ack", recorded_at=T1,
            )
            replayed = service.steer(
                event_id=event_id, action="acknowledge",
                principal_id="principal.phase5.owner", capability_id="capability.phase5.steer",
                idempotency_key="steer.phase5.ack", recorded_at=T1,
            )
            self.assertEqual(action, replayed)
            exported = workspace.export_bytes()
            self.assertEqual(workspace.save_verified_export(exported)["content_hash"], json.loads(exported)["content_hash"])
        with Phase5Workspace(self.root) as restarted:
            self.assertEqual("acknowledge", restarted.material_results()[0]["latest_steering_action"])
            self.assertEqual(exported, restarted.export_bytes())

    def test_falsification_branch_is_required(self) -> None:
        fixture = dict(FIXTURE)
        fixture["cases"] = [FIXTURE["cases"][1]]
        with Phase5Workspace(self.root) as workspace:
            with self.assertRaises(Phase5ValidationError):
                Phase5Service(workspace).run_quantum_fixture(fixture, recorded_at=T0)

    def test_source_evidence_without_applicability_fails_closed(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            result = service.run_quantum_fixture(FIXTURE, recorded_at=T0)
            with self.assertRaises((KeyError, Phase5ValidationError)):
                service.register_evidence(
                    evidence_id="evidence.bad-source", objective_id=result["objective_id"],
                    run_id=result["run_id"], kind="source_span", artifact={"candidate": True},
                    source_record_id="missing.source", applicability_review_id="missing.review",
                    recorded_at=T1,
                )

    def test_nonhuman_steering_fails_closed(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            result = service.run_quantum_fixture(FIXTURE, recorded_at=T0)
            event_id = result["material_result_event_ids"][0]
            with self.assertRaises(PermissionError):
                service.steer(
                    event_id=event_id, action="acknowledge",
                    principal_id="principal.phase5.deterministic",
                    capability_id="capability.phase5.surface",
                    idempotency_key="bad-steer", recorded_at=T1,
                )


if __name__ == "__main__":
    unittest.main()
