"""ADR-0049 acceptance tests for bounded exact certificate discovery."""

from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from math_research.phase5 import noncommuting as nc
from math_research.phase5 import solver
from math_research.phase5.exact_matrices import identity, zero

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures/phase5/noncommuting-certificates-v1.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text("utf-8"))


def by_id(case_id: str) -> nc.NoncommutingCase:
    value = copy.deepcopy(next(item for item in FIXTURE["cases"] if item["case_id"] == case_id))
    return nc.NoncommutingCase.from_value(value)


class BoundedDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = solver.solve_fixture(FIXTURE)
        cls.results = {item["case_id"]: item for item in cls.report["results"]}

    def test_previous_rational_gaps_are_now_discovered_and_exactly_verified(self) -> None:
        for case_id in (
            "real-noncommuting-rational-candidate",
            "complex-noncommuting-rational-candidate",
            "real-noncommuting-certificate-withheld",
        ):
            with self.subTest(case_id=case_id):
                result = self.results[case_id]
                self.assertEqual(solver.STATUS_VERIFIED, result["solver_status"])
                self.assertTrue(result["optimum_discovered"])
                checked = result["exact_verification"]
                self.assertTrue(checked["primal_feasible"])
                self.assertTrue(checked["dual_feasible"])
                self.assertTrue(checked["complementarity_exact"])
                self.assertEqual("0", checked["primal_dual_gap"])

    def test_generated_candidate_is_not_laundered_as_human_input(self) -> None:
        result = self.results["real-noncommuting-certificate-withheld"]
        provenance = result["candidate"]["provenance"]
        self.assertEqual("system_generated", provenance["certificate_origin"])
        self.assertTrue(provenance["system_generated"])
        self.assertEqual(
            "bounded_exact_solver_candidate_boundary", provenance["admitted_through"]
        )
        self.assertNotEqual(nc.CERTIFICATE_BOUNDARY, provenance["admitted_through"])

    def test_exact_verifier_not_constructor_is_final_authority(self) -> None:
        rejected = {
            "accepted": False,
            "primal_dual_gap": "1/4",
        }
        with patch.object(solver, "verify_exact_certificate_candidate", return_value=rejected):
            result = solver.solve_case(by_id("real-noncommuting-rational-candidate"))
        self.assertEqual(solver.STATUS_REFUTED, result["solver_status"])
        self.assertFalse(result["optimum_discovered"])
        self.assertEqual("none_unresolved", result["mathematical_warrant"])

    def test_the_cubic_boundary_is_preserved_as_unresolved(self) -> None:
        result = self.results["real-noncommuting-irreducible-cubic-boundary"]
        self.assertEqual(solver.STATUS_UNSUPPORTED, result["solver_status"])
        self.assertEqual("dimension_outside_bounded_solver", result["reason_code"])
        self.assertFalse(result["candidate_constructed"])
        self.assertFalse(result["optimum_discovered"])

    def test_three_outcomes_are_explicitly_unresolved(self) -> None:
        source = by_id("real-noncommuting-certificate-withheld")
        case = nc.NoncommutingCase(
            case_id="three-outcome",
            weighted_states=source.weighted_states + (zero(2),),
            certificate=None,
            expected_noncommuting=True,
            expected_optimum_representable=False,
            expected_coverage_status=nc.COVERAGE_UNRESOLVED,
            expected_primal_dual_gap=None,
        )
        result = solver.solve_case(case)
        self.assertEqual(solver.STATUS_UNSUPPORTED, result["solver_status"])
        self.assertEqual("outcome_count_outside_bounded_solver", result["reason_code"])

    def test_report_is_deterministic_and_preserves_all_outcomes(self) -> None:
        again = solver.solve_fixture(copy.deepcopy(FIXTURE))
        self.assertEqual(self.report, again)
        self.assertEqual(7, self.report["status_counts"][solver.STATUS_VERIFIED])
        self.assertEqual(1, self.report["status_counts"][solver.STATUS_UNSUPPORTED])
        self.assertFalse(self.report["general_noncommuting_convergence_answered"])
        self.assertFalse(self.report["search_tiers_enabled"])

    def test_a_bad_generated_candidate_fails_the_same_exact_checker(self) -> None:
        case = by_id("real-noncommuting-certificate-withheld")
        candidate = solver.GeneratedCertificate(
            primal_povm=(identity(2), identity(2)),
            dual_gamma=zero(2),
            construction="deliberately_bad_test_candidate",
        )
        result = nc.verify_exact_certificate_candidate(case, candidate)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["primal_feasible"])
        self.assertFalse(result["dual_feasible"])


class SolverBoundaryTests(unittest.TestCase):
    def test_solver_source_has_no_float_model_network_or_third_party_import(self) -> None:
        path = ROOT / "src/math_research/phase5/solver.py"
        source = path.read_text("utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("socket", imports)
        self.assertNotIn("urllib", imports)
        self.assertNotIn("openai", imports)
        self.assertNotIn("cvxpy", imports)
        self.assertNotIn("clarabel", imports)
        float_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "float"
        ]
        self.assertEqual([], float_calls)
        self.assertNotIn("epsilon", source.lower())

    def test_cli_runs_without_workspace_model_network_or_engine(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            completed = subprocess.run(
                [
                    sys.executable, "-m", "math_research.cli", "phase5",
                    "solve-noncommuting", str(FIXTURE_PATH), "--output", str(output),
                ],
                cwd=ROOT, text=True, capture_output=True, timeout=20, check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            report = json.loads(output.read_text("utf-8"))
            self.assertEqual(solver.SOLVER_REPORT_VERSION, report["schema_version"])
            self.assertEqual(7, report["status_counts"][solver.STATUS_VERIFIED])


if __name__ == "__main__":
    unittest.main()
