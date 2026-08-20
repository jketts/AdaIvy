from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from spikes.phase5_noncommuting_sdp import (
    CertificateInputError,
    canonical_bytes,
    validate_fixture,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "phase5-noncommuting-sdp" / "exact-small-cases.json"


class NoncommutingSDPSpikeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]

    def test_exact_commuting_control_closes_primal_dual_gap(self) -> None:
        result = validate_fixture(self.cases[0])
        self.assertFalse(result["noncommuting"])
        self.assertEqual("0", result["primal_dual_gap"])
        self.assertTrue(result["complementarity_exact"])
        self.assertTrue(result["exact_optimum_certificate"])
        self.assertFalse(result["blocked_without_solver"])

    def test_real_noncommuting_candidate_remains_unresolved(self) -> None:
        result = validate_fixture(self.cases[1])
        self.assertTrue(result["noncommuting"])
        self.assertEqual("3/4", result["primal_value"])
        self.assertEqual("1", result["dual_value"])
        self.assertEqual("1/4", result["primal_dual_gap"])
        self.assertFalse(result["exact_optimum_certificate"])
        self.assertTrue(result["blocked_without_solver"])
        self.assertFalse(result["phase5_integrated"])
        self.assertFalse(result["search_tiers_enabled"])

    def test_complex_hermitian_noncommuting_arithmetic_is_exact(self) -> None:
        result = validate_fixture(self.cases[2])
        self.assertTrue(result["noncommuting"])
        residuals = canonical_bytes(result["left_complementarity_residuals"])
        self.assertIn(b'"im"', residuals)
        self.assertEqual("candidate_only_unresolved", result["disposition"])

    def test_hash_and_output_are_deterministic(self) -> None:
        first = validate_fixture(self.cases[2])
        second = validate_fixture(copy.deepcopy(self.cases[2]))
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))

    def test_nonhermitian_weighted_state_is_rejected(self) -> None:
        case = copy.deepcopy(self.cases[2])
        case["weighted_states"][1][1][0] = {"re": "0", "im": "-1/4"}
        with self.assertRaisesRegex(CertificateInputError, "not Hermitian"):
            validate_fixture(case)

    def test_non_psd_state_is_rejected_exactly(self) -> None:
        case = copy.deepcopy(self.cases[1])
        case["weighted_states"][1] = [["1/4", "1/2"], ["1/2", "1/4"]]
        with self.assertRaisesRegex(CertificateInputError, "not positive semidefinite"):
            validate_fixture(case)

    def test_trace_and_povm_constraints_are_rejected(self) -> None:
        case = copy.deepcopy(self.cases[1])
        case["weighted_states"][0][0][0] = "1/3"
        with self.assertRaisesRegex(CertificateInputError, "traces must sum to one"):
            validate_fixture(case)
        case = copy.deepcopy(self.cases[1])
        case["primal_povm"][1][1][1] = "1/2"
        with self.assertRaisesRegex(CertificateInputError, "sum to identity"):
            validate_fixture(case)

    def test_dual_domination_is_required_not_inferred_from_objective(self) -> None:
        case = copy.deepcopy(self.cases[1])
        case["dual_gamma"] = [["1/4", 0], [0, "1/4"]]
        with self.assertRaisesRegex(CertificateInputError, "dual slack"):
            validate_fixture(case)

    def test_dimension_bound_prevents_unbounded_exact_minor_enumeration(self) -> None:
        case = copy.deepcopy(self.cases[0])
        case["weighted_states"][0] = [[0] * 5 for _ in range(5)]
        with self.assertRaisesRegex(CertificateInputError, "dimension bound"):
            validate_fixture(case)


if __name__ == "__main__":
    unittest.main()
