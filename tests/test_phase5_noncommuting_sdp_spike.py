"""Acceptance suite for the exact-algebraic noncommuting SDP spike (ADR-0033).

The thresholds this slice claims are asserted here as executable properties:
exact canonical arithmetic, one representation and one hash per value,
rejection rather than coercion outside the represented field, a measured
primal/dual gap on every frozen fixture, a structurally float-free certificate
path, complementarity that actually rejects a perturbed certificate, and
byte-identical output across two runs and two processes.
"""

from __future__ import annotations

import ast
import copy
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from spikes.phase5_noncommuting_sdp import (
    AlgebraicComplex,
    AlgebraicFieldError,
    CertificateInputError,
    Quadratic,
    algebraic,
    canonical_bytes,
    canonical_hash,
    characteristic_polynomial,
    imaginary,
    load_document,
    parse_algebraic,
    quadratic,
    rational_sqrt,
    spectral_field_report,
    two_state_optimum,
    validate_document,
    validate_fixture,
)
from spikes.phase5_noncommuting_sdp import matrices
from spikes.phase5_noncommuting_sdp.validator import (
    FIXTURE_SCHEMA_VERSION,
    REQUIRED_CASE_FIELDS,
    SCHEMA_VERSION,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "phase5-noncommuting-sdp" / "exact-small-cases.json"
SPIKE = ROOT / "spikes" / "phase5_noncommuting_sdp"

# The measured outcome recorded in ADR-0033.  A case that moves in either
# direction is an unreviewed change to a frozen fixture, so both the closed and
# the open gaps are pinned.
MEASURED_GAPS = {
    "commuting-exact-control": "0",
    "real-noncommuting-rational-candidate": "1/4",
    "complex-noncommuting-rational-candidate": "1/4",
    "real-noncommuting-algebraic-certificate": "0",
    "complex-noncommuting-algebraic-certificate": "0",
    "real-noncommuting-algebraic-certificate-radicand-five": "0",
    "real-noncommuting-irreducible-cubic-boundary": "1/2",
}
ALGEBRAIC_CERTIFICATE_CASES = (
    "real-noncommuting-algebraic-certificate",
    "complex-noncommuting-algebraic-certificate",
    "real-noncommuting-algebraic-certificate-radicand-five",
)
SQRT_TWO_OPTIMUM = {"rational": "1/2", "surd": "1/4", "radicand": 2}

# A genuine two-outcome ensemble in dimension three whose difference operator
# has the irreducible characteristic polynomial lambda^3 - (3/50) lambda +
# 3/1000.  Authored to be HARDER than the arithmetic can represent, so the
# boundary is measured rather than avoided.
CUBIC_STATES = (
    [["13/60", "1/20", "1/50"], ["1/20", "1/6", "1/10"], ["1/50", "1/10", "7/60"]],
    [["7/60", "-1/20", "1/50"], ["-1/20", "1/6", "-1/10"], ["1/50", "-1/10", "13/60"]],
)


def _walk(value: object, path: str = "$"):
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


class NoncommutingSDPSpikeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = FIXTURE.read_text(encoding="utf-8")
        cls.document = load_document(cls.text)
        cls.cases = cls.document["cases"]
        cls.by_id = {case["case_id"]: case for case in cls.cases}

    # -- unchanged rational behaviour -------------------------------------
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


class ExactAlgebraicArithmeticTests(unittest.TestCase):
    def test_field_arithmetic_is_exact(self) -> None:
        root2 = quadratic(0, 1, 2)
        self.assertEqual(quadratic(2), root2 * root2)
        self.assertEqual(quadratic(3, 2, 2), (quadratic(1) + root2) * (quadratic(1) + root2))
        # (1 + sqrt 2)^-1 = sqrt 2 - 1, exactly.
        self.assertEqual(quadratic(-1, 1, 2), (quadratic(1) + root2).reciprocal())
        self.assertEqual(quadratic(1), (quadratic(1) + root2) / (quadratic(1) + root2))
        self.assertEqual(quadratic(-2), root2.field_conjugate() * root2)
        self.assertEqual(Fraction(-2), root2.norm())
        # sqrt(3 + 2 sqrt 2) = 1 + sqrt 2 stays inside the field.
        self.assertEqual(quadratic(1, 1, 2), quadratic(3, 2, 2).exact_sqrt())
        self.assertEqual(quadratic(0, Fraction(1, 2), 2), rational_sqrt(Fraction(1, 2)))

    def test_comparison_is_exact_and_never_epsilon_based(self) -> None:
        # 99/70 and 140/99 bracket sqrt 2 within 1e-4; exact comparison still
        # orders them correctly, and equality is never accidental.
        root2 = quadratic(0, 1, 2)
        self.assertTrue(quadratic(Fraction(99, 70)) > root2)
        self.assertTrue(quadratic(Fraction(140, 99)) < root2)
        self.assertEqual(0, (root2 - root2).sign())
        self.assertEqual(1, quadratic(-1, 1, 2).sign())
        self.assertEqual(-1, quadratic(1, -1, 2).sign())
        self.assertEqual(0, quadratic(0).sign())
        # A total order inside one field: sorting is well defined.
        values = [quadratic(1), quadratic(0, 1, 2), quadratic(-3), quadratic(1, -1, 2)]
        self.assertEqual(
            [quadratic(-3), quadratic(1, -1, 2), quadratic(1), quadratic(0, 1, 2)],
            sorted(values),
        )

    def test_sign_and_equality_have_no_epsilon_threshold(self) -> None:
        # Any tolerance, however small, would collapse these into zero.
        tiny = quadratic(Fraction(1, 10**11))
        self.assertEqual(1, tiny.sign())
        self.assertEqual(-1, (-tiny).sign())
        self.assertTrue(tiny > quadratic(0))
        self.assertTrue(quadratic(0) > -tiny)
        self.assertNotEqual(quadratic(0), tiny)
        self.assertEqual(0, (tiny - tiny).sign())
        # The same holds when the tiny quantity is irrational, where the sign is
        # decided by comparing squared magnitudes rather than by subtraction.
        self.assertEqual(1, quadratic(0, Fraction(1, 10**11), 2).sign())
        self.assertEqual(-1, quadratic(0, Fraction(-1, 10**11), 2).sign())
        near_zero = quadratic(Fraction(-1, 10**11), Fraction(1, 10**11), 2)
        self.assertEqual(1, near_zero.sign())
        self.assertEqual(-1, (-near_zero).sign())
        self.assertNotEqual(quadratic(0), near_zero)
        # 665857/470832 differs from sqrt 2 by under 1e-11 and is still ordered.
        self.assertTrue(quadratic(Fraction(665857, 470832)) > quadratic(0, 1, 2))

    def test_complex_arithmetic_and_conjugation_are_exact(self) -> None:
        value = AlgebraicComplex(quadratic(0, 1, 2), quadratic(1))
        self.assertEqual(quadratic(3), value.modulus_squared())
        self.assertEqual(AlgebraicComplex(quadratic(0, 1, 2), quadratic(-1)), value.conjugate())
        self.assertEqual(algebraic(1), value * value.reciprocal())
        self.assertEqual(algebraic(-1), imaginary(1) * imaginary(1))
        self.assertEqual(algebraic(2), imaginary(0, 1, 2) * imaginary(0, -1, 2))

    def test_a_value_has_exactly_one_canonical_form_and_one_hash(self) -> None:
        target = quadratic(Fraction(1, 2), Fraction(1, 4), 2)
        constructions = [
            quadratic(Fraction(1, 2), Fraction(1, 4), 2),
            quadratic(Fraction(1, 2), Fraction(1, 8), 8),
            quadratic(Fraction(1, 2), Fraction(1, 24), 72),
            quadratic(Fraction(1, 2)) + rational_sqrt(Fraction(1, 8)),
            quadratic(Fraction(1, 4)) * (quadratic(2) + quadratic(0, 1, 2)),
        ]
        for candidate in constructions:
            self.assertEqual(target, candidate)
            self.assertEqual(target.canonical(), candidate.canonical())
        hashes = {canonical_hash(item.canonical()) for item in constructions}
        self.assertEqual(1, len(hashes))
        self.assertEqual({"rational": "1/2", "surd": "1/4", "radicand": 2}, target.canonical())
        # Distinct values never collide onto one canonical form.
        self.assertNotEqual(target.canonical(), quadratic(Fraction(1, 2), Fraction(-1, 4), 2).canonical())

    def test_canonical_json_round_trips_and_collapses_redundant_forms(self) -> None:
        samples = [
            algebraic(Fraction(1, 2)),
            algebraic(0, 1, 2),
            imaginary(0, Fraction(-1, 4), 2),
            AlgebraicComplex(quadratic(Fraction(3, 8), Fraction(1, 8), 2), quadratic(Fraction(-1, 8))),
        ]
        for value in samples:
            canonical = value.canonical()
            self.assertEqual(value, parse_algebraic(canonical))
            self.assertEqual(canonical, parse_algebraic(canonical).canonical())
        # Redundant spellings collapse: an explicit zero imaginary part, a
        # non-squarefree radicand, and a surd that cancels all normalize.
        self.assertEqual("1/2", parse_algebraic({"re": "1/2", "im": "0"}).canonical())
        self.assertEqual("2", parse_algebraic({"rational": "0", "surd": "1", "radicand": 4}).canonical())
        self.assertEqual("0", parse_algebraic({"rational": "0", "surd": "0", "radicand": 5}).canonical())
        self.assertEqual(
            {"rational": "0", "surd": "1", "radicand": 2},
            parse_algebraic({"rational": "0", "surd": "1/2", "radicand": 8}).canonical(),
        )

    def test_values_outside_the_field_are_rejected_not_rounded(self) -> None:
        root2 = quadratic(0, 1, 2)
        root3 = quadratic(0, 1, 3)
        # sqrt 2 + sqrt 3 needs Q(sqrt 2, sqrt 3), degree four.
        for operation in (
            lambda: root2 + root3,
            lambda: root2 * root3,
            lambda: root2 - root3,
            lambda: root2 / root3,
            lambda: root2.compare(root3),
            lambda: root2 < root3,
            lambda: AlgebraicComplex(root2, root3),
        ):
            with self.assertRaisesRegex(AlgebraicFieldError, "mixed radicands"):
                operation()
        # A square root that leaves the field is refused, not approximated.
        with self.assertRaisesRegex(AlgebraicFieldError, "outside the represented field"):
            quadratic(1, 1, 2).exact_sqrt()
        with self.assertRaisesRegex(AlgebraicFieldError, "negative"):
            quadratic(-2).exact_sqrt()
        # An imaginary radical is not a member of the real quadratic extension.
        with self.assertRaisesRegex(AlgebraicFieldError, "positive integer"):
            quadratic(0, 1, -1)
        with self.assertRaisesRegex(AlgebraicFieldError, "bound"):
            quadratic(0, 1, 10**9)
        # Symbolic and non-numeric literals are rejected at the parse boundary.
        for bad in ("sqrt(2)", "2**0.5", "nan", "inf", "0x10", "1/0", "", " "):
            with self.assertRaises(AlgebraicFieldError):
                quadratic(bad)
        # A decimal spelling is read EXACTLY, never rounded, and re-emitted in
        # the one canonical p/q form, so canonical identity is still unique.
        self.assertEqual(quadratic(Fraction(3, 2)), quadratic("1.5"))
        self.assertEqual("3/2", quadratic("1.5").canonical())
        self.assertEqual(quadratic(Fraction(3, 10)), quadratic("0.3"))
        # And a denominator past the bound is refused rather than truncated.
        with self.assertRaisesRegex(AlgebraicFieldError, "denominator exceeds"):
            quadratic("0.30000000000000004")
        with self.assertRaises(AlgebraicFieldError):
            quadratic(True)
        with self.assertRaisesRegex(AlgebraicFieldError, "division by an exact zero"):
            quadratic(1) / quadratic(0)
        # Unknown or partial key sets fail closed rather than defaulting.
        for bad_object in (
            {"rational": "1", "surd": "1", "radicand": 2, "extra": 1},
            {"rational": "1", "surd": "1"},
            {"re": "1"},
            {"re": {"re": "1", "im": "1"}, "im": "0"},
            {},
            [1, 2],
        ):
            with self.assertRaises(AlgebraicFieldError):
                parse_algebraic(bad_object)
        with self.assertRaisesRegex(AlgebraicFieldError, "radicand must be an integer"):
            parse_algebraic({"rational": "0", "surd": "1", "radicand": "2"})

    def test_non_canonical_construction_is_impossible(self) -> None:
        # The only container for a number on the certificate path validates its
        # own canonicity, so an uncanonical or inexact component cannot exist.
        for bad in (
            (Fraction(0), Fraction(1), 1),
            (Fraction(0), Fraction(1), 8),
            (Fraction(0), Fraction(0), 2),
            (0.5, Fraction(0), 1),
            (Fraction(0), 0.5, 1),
            (Fraction(0), Fraction(0), True),
        ):
            with self.assertRaises(AlgebraicFieldError):
                Quadratic(*bad)


class MeasuredGapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = load_document(FIXTURE.read_text(encoding="utf-8"))
        cls.report = validate_document(cls.document)
        cls.results = {item["case_id"]: item for item in cls.report["results"]}

    def test_every_frozen_case_reports_its_measured_gap(self) -> None:
        self.assertEqual(set(MEASURED_GAPS), set(self.results))
        for case_id, gap in MEASURED_GAPS.items():
            self.assertEqual(gap, self.results[case_id]["primal_dual_gap"], case_id)

    def test_algebraic_certificates_close_the_gap_to_exactly_zero(self) -> None:
        for case_id in ALGEBRAIC_CERTIFICATE_CASES:
            result = self.results[case_id]
            with self.subTest(case_id):
                self.assertTrue(result["noncommuting"])
                self.assertEqual("0", result["primal_dual_gap"])
                self.assertTrue(result["complementarity_exact"])
                self.assertTrue(result["exact_optimum_certificate"])
                self.assertFalse(result["blocked_without_solver"])
                self.assertIsNone(result["blocked_reason"])
                self.assertEqual("exact_certificate_checked", result["disposition"])
                # Zero is exact zero, not a small residual.
                for residual in (
                    result["left_complementarity_residuals"]
                    + result["right_complementarity_residuals"]
                ):
                    for row in residual:
                        self.assertEqual(["0"] * len(row), row)
                # The certificate value equals the independent closed form.
                self.assertFalse(result["primal_value_is_rational"])
                self.assertEqual(result["primal_value"], result["dual_value"])
                self.assertEqual(result["primal_value"], result["independent_optimum"]["optimum"])
                self.assertTrue(result["primal_matches_independent_optimum"])
                self.assertTrue(result["dual_matches_independent_optimum"])
                self.assertEqual("0", result["shortfall_to_independent_optimum"])

    def test_the_measured_one_quarter_gap_was_a_field_limit_not_infeasibility(self) -> None:
        # The rational candidates are feasible and their gap is exactly 1/4; the
        # optimum they cannot reach is irrational and lies in Q(sqrt 2).
        for case_id in ("real-noncommuting-rational-candidate", "complex-noncommuting-rational-candidate"):
            result = self.results[case_id]
            with self.subTest(case_id):
                self.assertEqual("1/4", result["primal_dual_gap"])
                self.assertEqual(1, result["field"]["radicand"])
                self.assertTrue(result["primal_value_is_rational"])
                self.assertEqual(SQRT_TWO_OPTIMUM, result["independent_optimum"]["optimum"])
                self.assertFalse(result["independent_optimum"]["optimum_is_rational"])
                self.assertEqual(2, result["independent_optimum"]["optimum_radicand"])
                self.assertFalse(result["primal_matches_independent_optimum"])
                self.assertEqual(
                    {"rational": "-1/4", "surd": "1/4", "radicand": 2},
                    result["shortfall_to_independent_optimum"],
                )
                self.assertTrue(result["optimum_representable_in_quadratic_extension"])

    def test_algebraic_certificates_reuse_the_frozen_rational_ensembles(self) -> None:
        # The certificate cases are not easier problems: their ensembles are
        # byte-identical to the ensembles that left a 1/4 gap.
        cases = {case["case_id"]: case for case in self.document["cases"]}
        pairs = (
            ("real-noncommuting-rational-candidate", "real-noncommuting-algebraic-certificate"),
            ("complex-noncommuting-rational-candidate", "complex-noncommuting-algebraic-certificate"),
        )
        for rational_id, algebraic_id in pairs:
            with self.subTest(algebraic_id):
                self.assertEqual(
                    canonical_bytes(cases[rational_id]["weighted_states"]),
                    canonical_bytes(cases[algebraic_id]["weighted_states"]),
                )
                self.assertEqual(
                    self.results[rational_id]["independent_optimum"]["optimum"],
                    self.results[algebraic_id]["independent_optimum"]["optimum"],
                )

    def test_the_field_radicand_is_measured_not_hardcoded(self) -> None:
        self.assertEqual([1, 2, 5], self.report["radicands_used"])
        five = self.results["real-noncommuting-algebraic-certificate-radicand-five"]
        self.assertEqual(5, five["field"]["radicand"])
        self.assertEqual("Q(sqrt(5))(i)", five["field"]["notation"])
        self.assertEqual({"rational": "1/2", "surd": "1/6", "radicand": 5}, five["primal_value"])
        self.assertEqual(5, five["spectral_field_probe"]["eigenvalue_radicand"])

    def test_report_partitions_every_case_exactly_once(self) -> None:
        partition = (
            self.report["exact_certificate_case_ids"]
            + self.report["unresolved_case_ids"]
            + self.report["outside_field_case_ids"]
        )
        self.assertEqual(sorted(MEASURED_GAPS), sorted(partition))
        self.assertEqual(len(partition), len(set(partition)))
        self.assertEqual(
            ["real-noncommuting-irreducible-cubic-boundary"],
            self.report["outside_field_case_ids"],
        )
        self.assertFalse(self.report["phase5_integrated"])
        self.assertFalse(self.report["search_tiers_enabled"])
        self.assertEqual("none_spike_only", self.report["mathematical_warrant"])
        for result in self.report["results"]:
            self.assertFalse(result["graph_admitted"])
            self.assertEqual("none_spike_only", result["mathematical_warrant"])
            self.assertEqual("candidate_check_only", result["proposal_status"])


class MeasuredFieldBoundaryTests(unittest.TestCase):
    """The boundary is measured on a case authored to be too hard, not glossed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = load_document(FIXTURE.read_text(encoding="utf-8"))
        cls.case = {
            item["case_id"]: item for item in cls.document["cases"]
        }["real-noncommuting-irreducible-cubic-boundary"]
        cls.result = validate_fixture(cls.case)

    def test_cubic_case_is_a_legitimate_noncommuting_instance(self) -> None:
        self.assertTrue(self.result["noncommuting"])
        self.assertEqual(3, self.result["dimension"])
        self.assertEqual(2, self.result["outcomes"])
        self.assertTrue(self.result["povm_feasible"])
        self.assertTrue(self.result["dual_feasible"])
        self.assertEqual(["1/2", "1/2"], self.result["weighted_state_traces"])

    def test_the_optimum_is_provably_outside_every_quadratic_extension(self) -> None:
        probe = self.result["spectral_field_probe"]
        self.assertEqual("irreducible_cubic_spectrum", probe["determination"])
        self.assertEqual(3, probe["residual_degree"])
        self.assertEqual([], probe["rational_roots"])
        self.assertTrue(probe["residual_irreducible"])
        self.assertEqual(["1", "0", "-3/50", "3/1000"], probe["characteristic_polynomial"])
        self.assertFalse(probe["representable_in_quadratic_extension"])
        self.assertFalse(self.result["optimum_representable_in_quadratic_extension"])
        self.assertEqual("candidate_only_outside_represented_field", self.result["disposition"])
        self.assertIn("degree at least three", self.result["blocked_reason"])
        self.assertIsNone(self.result["independent_optimum"]["optimum"])

    def test_the_cubic_has_no_rational_root_so_it_is_irreducible_over_q(self) -> None:
        difference = matrices.subtract(
            matrices.parse_matrix(CUBIC_STATES[0]), matrices.parse_matrix(CUBIC_STATES[1])
        )
        coefficients = characteristic_polynomial(difference)
        self.assertEqual(["1", "0", "-3/50", "3/1000"], [item.canonical() for item in coefficients])
        report = spectral_field_report(difference, "witness")
        self.assertEqual(3, report["residual_degree"])
        self.assertEqual([], report["rational_roots"])
        # Named boundary, stated as a property of the field and not of the code:
        # a degree-three eigenvalue cannot be written as a + b sqrt(d).
        self.assertIsNone(report["eigenvalue_radicand"])

    def test_the_boundary_cannot_be_hidden_by_relabelling_the_fixture(self) -> None:
        case = copy.deepcopy(self.case)
        case["expected_quadratic_representable"] = True
        with self.assertRaisesRegex(CertificateInputError, "quadratic-representability"):
            validate_fixture(case)

    def test_the_degree_argument_is_machine_checked_not_asserted(self) -> None:
        probe = self.result["spectral_field_probe"]
        # All roots of a Hermitian operator are real, so Descartes' rule of
        # signs is exact rather than a bound, and the sign classes are counted
        # by integer comparison only.
        self.assertEqual({"positive": 2, "negative": 1, "zero": 0}, probe["real_root_signature"])
        self.assertEqual("0", probe["characteristic_polynomial"][1])
        self.assertIn("traceless with exactly one negative root", probe["trace_norm_argument"])
        self.assertIn("degree 3 over the rationals", probe["trace_norm_argument"])

    def test_claiming_a_closed_gap_on_the_cubic_case_is_rejected(self) -> None:
        case = copy.deepcopy(self.case)
        case["expected_zero_gap"] = True
        with self.assertRaisesRegex(CertificateInputError, "disagrees with residuals"):
            validate_fixture(case)


class PerturbationRejectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        document = load_document(FIXTURE.read_text(encoding="utf-8"))
        cls.case = {
            item["case_id"]: item for item in document["cases"]
        }["real-noncommuting-algebraic-certificate"]

    def _observe(self, case: dict) -> dict:
        relaxed = copy.deepcopy(case)
        relaxed["expected_zero_gap"] = False
        return validate_fixture(relaxed)

    def test_complementarity_rejects_a_swapped_but_feasible_povm(self) -> None:
        case = copy.deepcopy(self.case)
        case["primal_povm"] = [case["primal_povm"][1], case["primal_povm"][0]]
        # Still primal feasible: PSD effects summing to the identity.
        observed = self._observe(case)
        self.assertTrue(observed["povm_feasible"])
        self.assertTrue(observed["dual_feasible"])
        self.assertFalse(observed["complementarity_exact"])
        self.assertFalse(observed["exact_optimum_certificate"])
        self.assertEqual({"rational": "0", "surd": "1/2", "radicand": 2}, observed["primal_dual_gap"])
        residuals = observed["left_complementarity_residuals"]
        self.assertTrue(any(entry != "0" for matrix in residuals for row in matrix for entry in row))
        # And the certificate claiming optimality is rejected outright.
        with self.assertRaisesRegex(CertificateInputError, "disagrees with residuals"):
            validate_fixture(case)

    def test_an_inflated_dual_stays_feasible_but_loses_complementarity(self) -> None:
        case = copy.deepcopy(self.case)
        case["dual_gamma"][0][0] = {"rational": "3/8", "surd": "1/8", "radicand": 2}
        case["dual_gamma"][1][1] = {"rational": "1001/8000", "surd": "1/8", "radicand": 2}
        observed = self._observe(case)
        self.assertTrue(observed["dual_feasible"])
        self.assertEqual("1/8000", observed["primal_dual_gap"])
        self.assertFalse(observed["complementarity_exact"])
        with self.assertRaisesRegex(CertificateInputError, "disagrees with residuals"):
            validate_fixture(case)

    def test_a_deflated_dual_loses_domination_before_any_value_is_reported(self) -> None:
        case = copy.deepcopy(self.case)
        case["dual_gamma"][1][1] = {"rational": "999/8000", "surd": "1/8", "radicand": 2}
        with self.assertRaisesRegex(CertificateInputError, "dual slack"):
            validate_fixture(case)

    def test_a_perturbed_primal_effect_breaks_completeness(self) -> None:
        case = copy.deepcopy(self.case)
        case["primal_povm"][0][0][0] = {"rational": "501/1000", "surd": "1/4", "radicand": 2}
        with self.assertRaisesRegex(CertificateInputError, "sum to identity"):
            validate_fixture(case)

    def test_a_tiny_rational_psd_violation_is_rejected_with_no_tolerance(self) -> None:
        # A dual slack whose determinant is -1/(4*10^11): exactly negative, so
        # exactly rejected.  Any epsilon-based PSD test would admit it.
        document = load_document(FIXTURE.read_text(encoding="utf-8"))
        case = copy.deepcopy(
            {item["case_id"]: item for item in document["cases"]}[
                "real-noncommuting-rational-candidate"
            ]
        )
        case["dual_gamma"] = [["1/2", 0], [0, "99999999999/200000000000"]]
        with self.assertRaisesRegex(CertificateInputError, "dual slack"):
            validate_fixture(case)
        # The unperturbed rational candidate is accepted, so the rejection above
        # is caused by the perturbation and not by the denominator's size.
        accepted = copy.deepcopy(case)
        accepted["dual_gamma"] = [["1/2", 0], [0, "100000000000/200000000000"]]
        self.assertEqual("1/4", validate_fixture(accepted)["primal_dual_gap"])

    def test_no_tolerance_admits_a_near_certificate(self) -> None:
        # The gap is 1/8000 above and 0 for the certificate; nothing in between
        # is accepted, because no comparison consults a tolerance.
        case = copy.deepcopy(self.case)
        case["dual_gamma"][1][1] = {"rational": "1000000001/8000000000", "surd": "1/8", "radicand": 2}
        with self.assertRaisesRegex(CertificateInputError, "disagrees with residuals"):
            validate_fixture(case)


class FailClosedSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = FIXTURE.read_text(encoding="utf-8")
        cls.document = load_document(cls.text)

    def test_document_and_case_schema_versions_are_pinned(self) -> None:
        self.assertEqual(FIXTURE_SCHEMA_VERSION, self.document["schema_version"])
        for case in self.document["cases"]:
            self.assertEqual(SCHEMA_VERSION, case["schema_version"])
            self.assertEqual(REQUIRED_CASE_FIELDS, set(case))

    def test_superseded_case_schema_version_is_rejected(self) -> None:
        case = copy.deepcopy(self.document["cases"][0])
        case["schema_version"] = "adaivy.phase5-noncommuting-sdp-spike.v1"
        with self.assertRaisesRegex(CertificateInputError, "unsupported fields"):
            validate_fixture(case)

    def test_mixed_case_schema_versions_are_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["cases"][1]["schema_version"] = "adaivy.phase5-noncommuting-sdp-spike.v3"
        with self.assertRaisesRegex(CertificateInputError, "mixes or omits"):
            validate_document(document)

    def test_unknown_and_missing_fields_are_rejected(self) -> None:
        case = copy.deepcopy(self.document["cases"][0])
        case["unexpected"] = True
        with self.assertRaisesRegex(CertificateInputError, "unsupported fields"):
            validate_fixture(case)
        case = copy.deepcopy(self.document["cases"][0])
        del case["expected_independent_optimum"]
        with self.assertRaisesRegex(CertificateInputError, "unsupported fields"):
            validate_fixture(case)
        document = copy.deepcopy(self.document)
        document["extra"] = 1
        with self.assertRaisesRegex(CertificateInputError, "missing or unknown fields"):
            validate_document(document)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(CertificateInputError, "duplicate JSON key"):
            load_document('{"schema_version": "a", "schema_version": "b", "cases": []}')

    def test_malformed_json_is_rejected(self) -> None:
        with self.assertRaisesRegex(CertificateInputError, "malformed fixture JSON"):
            load_document("{")

    def test_expectations_are_cross_checked_against_the_exact_computation(self) -> None:
        for field, value, pattern in (
            ("expected_noncommuting", True, "noncommutativity expectation"),
            ("expected_zero_gap", False, "disagrees with residuals"),
            ("expected_independent_optimum", "3/4", "independent-optimum expectation"),
        ):
            case = copy.deepcopy(self.document["cases"][0])
            case[field] = value
            with self.subTest(field):
                with self.assertRaisesRegex(CertificateInputError, pattern):
                    validate_fixture(case)

    def test_a_case_mixing_two_radicands_is_rejected(self) -> None:
        case = copy.deepcopy(self.document["cases"][3])
        case["dual_gamma"][0][1] = {"rational": "1/8", "surd": "1/1000", "radicand": 3}
        with self.assertRaisesRegex(CertificateInputError, "sqrt"):
            validate_fixture(case)

    def test_a_repeated_case_identifier_is_rejected(self) -> None:
        document = copy.deepcopy(self.document)
        document["cases"].append(copy.deepcopy(document["cases"][0]))
        with self.assertRaisesRegex(CertificateInputError, "repeats a case identifier"):
            validate_document(document)


class FloatFreeCertificatePathTests(unittest.TestCase):
    """No float exists on the certificate path, asserted structurally."""

    def test_the_fixture_contains_no_inexact_literal(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        # json.loads would silently produce a float; parse_float makes it a
        # reject, so the absence of floats in the frozen fixture is enforced.
        load_document(text)
        with self.assertRaisesRegex(CertificateInputError, "inexact numeric literal"):
            load_document(text.replace('"1/2"', "0.5", 1))
        for literal in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaisesRegex(CertificateInputError, "inexact numeric literal"):
                load_document(text.replace('"1/2"', literal, 1))

    def test_the_spike_package_declares_no_float_and_no_float_source(self) -> None:
        forbidden_modules = {"math", "cmath", "decimal", "statistics", "random", "numpy"}
        forbidden_calls = {"float", "complex", "round", "pow", "divmod"}
        violations: list[str] = []
        for path in sorted(SPIKE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, (float, complex)):
                    violations.append(f"{path.name}:{node.lineno} float literal")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in forbidden_calls:
                        violations.append(f"{path.name}:{node.lineno} calls {node.func.id}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] in forbidden_modules:
                            violations.append(f"{path.name}:{node.lineno} imports {alias.name}")
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in forbidden_modules:
                        violations.append(f"{path.name}:{node.lineno} imports {node.module}")
        self.assertEqual([], violations)

    def test_no_float_reaches_any_result_or_report(self) -> None:
        report = validate_document(load_document(FIXTURE.read_text(encoding="utf-8")))
        for path, value in _walk(report):
            self.assertNotIsInstance(value, float, path)
            self.assertNotIsInstance(value, complex, path)
        # The serializer refuses rather than rounding when a float is injected.
        with self.assertRaisesRegex(AlgebraicFieldError, "inexact numeric value"):
            canonical_bytes({"primal_value": 0.75})
        with self.assertRaisesRegex(AlgebraicFieldError, "inexact numeric value"):
            canonical_bytes([[1, 2], [3, 0.5]])

    def test_a_float_in_a_supplied_case_is_rejected_not_coerced(self) -> None:
        document = load_document(FIXTURE.read_text(encoding="utf-8"))
        case = copy.deepcopy(document["cases"][0])
        case["weighted_states"][0][0][0] = 0.5
        with self.assertRaises(CertificateInputError):
            validate_fixture(case)

    def test_every_stored_component_is_a_fraction(self) -> None:
        document = load_document(FIXTURE.read_text(encoding="utf-8"))
        for case in document["cases"]:
            for block in (case["weighted_states"], case["primal_povm"], [case["dual_gamma"]]):
                for raw in block:
                    for row in matrices.parse_matrix(raw):
                        for entry in row:
                            self.assertIsInstance(entry.real.rational, Fraction)
                            self.assertIsInstance(entry.real.surd, Fraction)
                            self.assertIsInstance(entry.imag.rational, Fraction)
                            self.assertIsInstance(entry.imag.surd, Fraction)
                            self.assertIsInstance(entry.real.radicand, int)


class DeterminismTests(unittest.TestCase):
    def test_two_runs_in_one_process_are_byte_identical(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        first = canonical_bytes(validate_document(load_document(text)))
        second = canonical_bytes(validate_document(load_document(text)))
        self.assertEqual(first, second)

    def test_two_separate_processes_are_byte_identical(self) -> None:
        driver = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "from spikes.phase5_noncommuting_sdp import canonical_bytes, load_document, validate_document;"
            "sys.stdout.buffer.write("
            "canonical_bytes(validate_document(load_document(open(%r, encoding='utf-8').read()))))"
            % (str(ROOT), str(FIXTURE))
        )
        outputs = []
        for seed in ("0", "1", "12345"):
            environment = dict(os.environ)
            environment["PYTHONHASHSEED"] = seed
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                [sys.executable, "-c", driver],
                capture_output=True,
                cwd=str(ROOT),
                env=environment,
                timeout=120,
                check=True,
            )
            outputs.append(completed.stdout)
        self.assertEqual(1, len(set(outputs)))
        self.assertEqual(
            canonical_bytes(validate_document(load_document(FIXTURE.read_text(encoding="utf-8")))),
            outputs[0],
        )

    def test_the_report_hash_covers_every_case_result(self) -> None:
        report = validate_document(load_document(FIXTURE.read_text(encoding="utf-8")))
        self.assertTrue(report["content_hash"].startswith("sha256:"))
        preimage = {key: value for key, value in report.items() if key != "content_hash"}
        self.assertEqual(canonical_hash(preimage), report["content_hash"])
        for result in report["results"]:
            self.assertTrue(result["content_hash"].startswith("sha256:"))
            body = {key: value for key, value in result.items() if key != "content_hash"}
            self.assertEqual(canonical_hash(body), result["content_hash"])
        # Whitespace in the fixture never changes the measured identity.
        compact = json.dumps(
            load_document(FIXTURE.read_text(encoding="utf-8")), separators=(",", ":")
        )
        self.assertEqual(report["content_hash"], validate_document(load_document(compact))["content_hash"])


class BoundaryDeclarationTests(unittest.TestCase):
    def test_the_field_descriptor_names_what_falls_outside(self) -> None:
        result = validate_fixture(
            {
                item["case_id"]: item
                for item in load_document(FIXTURE.read_text(encoding="utf-8"))["cases"]
            }["real-noncommuting-algebraic-certificate"]
        )
        outside = " ".join(result["field"]["outside_field"])
        self.assertIn("sqrt(2)+sqrt(3)", outside)
        self.assertIn("cubic", outside)
        self.assertIn("transcendental", outside)
        self.assertIn("floating-point", outside)
        self.assertEqual(2, result["field"]["degree_over_rationals"])

    def test_two_state_closed_form_declines_shapes_it_cannot_cover(self) -> None:
        states = tuple(matrices.parse_matrix(item) for item in CUBIC_STATES)
        report = two_state_optimum(states)
        self.assertFalse(report["available"])
        self.assertIn("dimension two only", report["reason"])
        self.assertIsNone(report["optimum"])


if __name__ == "__main__":
    unittest.main()
