from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from math_research.phase5.serialization import canonical_hash
from math_research.phase5.service import Phase5Service
from math_research.phase6.service import Phase6Service, Phase6ValidationError
from math_research.phase6.workspace import Phase6Workspace


ROOT = Path(__file__).resolve().parents[1]
PHASE5_FIXTURE = json.loads((ROOT / "fixtures/phase5/quantum-diagonal-v1.json").read_text("utf-8"))
PROTOCOL = json.loads((ROOT / "fixtures/phase6/confirmatory-protocol-v1.json").read_text("utf-8"))
T0 = "2026-08-20T12:00:00Z"
T1 = "2026-08-20T14:00:00Z"


class Phase6ConfirmatoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self) -> tuple[dict[str, object], bytes]:
        with Phase6Workspace(self.root) as workspace:
            phase5 = Phase5Service(workspace.phase5).run_quantum_fixture(PHASE5_FIXTURE, recorded_at=T0)
            result = Phase6Service(workspace).confirm(
                protocol=PROTOCOL, phase5_fixture=PHASE5_FIXTURE,
                phase5_run_id=phase5["run_id"], recorded_at=T1,
            )
            return result, workspace.export_bytes()

    def test_end_to_end_confirmatory_run_passes_frozen_controls(self) -> None:
        result, _exported = self._run()
        self.assertEqual("passed", result["confirmatory_result"]["status"])
        self.assertEqual(result["controls_total"], result["controls_passed"])
        self.assertEqual(result["probes_total"], result["probes_flipped"])
        self.assertEqual(result["controls_total"], result["probes_total"])
        self.assertTrue(result["positive_control_admitted"])
        self.assertEqual("project_authored", result["control_corpus_provenance"])
        self.assertEqual(0, result["adaptations_after_access"])
        self.assertEqual(1, result["heldout_accesses"])
        self.assertEqual(0, result["heldout_access_violation_records"])
        self.assertEqual(1, result["material_result_count"])
        self.assertFalse(result["confirmatory_result"]["graph_admitted"])

    def test_release_binds_the_executed_generality_suite(self) -> None:
        result, _exported = self._run()
        self.assertEqual(PROTOCOL["generality_suite_id"], result["generality_suite_id"])
        self.assertEqual(PROTOCOL["generality_suite_hash"], result["generality_suite_hash"])
        suite = result["confirmatory_result"]["generality_controls"]
        self.assertEqual(PROTOCOL["generality_suite_hash"], suite["suite_hash"])
        self.assertTrue(suite["suite_passed"])
        self.assertEqual(
            [item["control_id"] for item in suite["controls"]],
            [item["control_id"] for item in result["generality_control_verdicts"]],
        )
        # The baseline comparison counts boundary rejections, not generality.
        self.assertFalse(result["baseline_comparison"]["is_generality_measure"])
        self.assertEqual(
            suite["negative_controls_passed"], result["baseline_comparison"]["phase6_passed"]
        )

    def test_novelty_significance_and_contribution_are_orthogonal(self) -> None:
        result, _exported = self._run()
        self.assertEqual("not_assessed", result["novelty"]["status"])
        self.assertEqual("not_assessed", result["significance"]["status"])
        self.assertEqual({"human", "tool", "system"}, {item["actor_type"] for item in result["contributions"]})
        self.assertIn("Semantic fidelity", result["report"])
        self.assertIn("Graph admission: `false`", result["report"])

    def test_restart_and_repeated_confirmatory_execution_are_identical(self) -> None:
        first, exported = self._run()
        with Phase6Workspace(self.root) as restarted:
            phase5_run_id = first["phase5_run_id"]
            second = Phase6Service(restarted).confirm(
                protocol=PROTOCOL, phase5_fixture=PHASE5_FIXTURE,
                phase5_run_id=phase5_run_id, recorded_at=T1,
            )
            self.assertEqual(first, second)
            self.assertEqual(exported, restarted.export_bytes())
            self.assertEqual(exported, json.dumps(json.loads(exported), sort_keys=True, separators=(",", ":")).encode())

    def test_fixture_hash_mismatch_fails_before_heldout_execution(self) -> None:
        with Phase6Workspace(self.root) as workspace:
            phase5 = Phase5Service(workspace.phase5).run_quantum_fixture(PHASE5_FIXTURE, recorded_at=T0)
            fixture = json.loads(json.dumps(PHASE5_FIXTURE))
            fixture["cases"][2]["iterations"] = 3
            with self.assertRaises(Phase6ValidationError):
                Phase6Service(workspace).confirm(
                    protocol=PROTOCOL, phase5_fixture=fixture,
                    phase5_run_id=phase5["run_id"], recorded_at=T1,
                )

    def test_protocol_capability_expansion_fails_closed(self) -> None:
        protocol = dict(PROTOCOL)
        protocol["allowed_capabilities"] = list(PROTOCOL["allowed_capabilities"]) + ["read_exploratory_results"]
        with Phase6Workspace(self.root) as workspace:
            with self.assertRaises(Phase6ValidationError):
                Phase6Service(workspace).freeze_protocol(protocol, recorded_at=T1)

    def test_confirmatory_run_requires_phase5_material_result_trace(self) -> None:
        with Phase6Workspace(self.root) as workspace:
            with self.assertRaises(Phase6ValidationError):
                Phase6Service(workspace).confirm(
                    protocol=PROTOCOL, phase5_fixture=PHASE5_FIXTURE,
                    phase5_run_id="missing.run", recorded_at=T1,
                )

    def test_protocol_fixture_hash_is_current(self) -> None:
        self.assertEqual(PROTOCOL["phase5_fixture_hash"], canonical_hash(PHASE5_FIXTURE))


if __name__ == "__main__":
    unittest.main()
