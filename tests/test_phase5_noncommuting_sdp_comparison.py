"""Acceptance suite for the Phase 5 noncommuting-SDP comparison experiment.

ADR-0045. Every test in this file runs with zero third-party packages installed
and none of them skips: the fail-closed path with both engines absent is the
path that runs in CI, and it is fully assertable. The engine-present paths are
exercised through the :class:`~spikes.phase5_noncommuting_sdp.ports.SDPEngine`
port with a recorded engine, so the trust properties are tested without needing
a solver present.

The forbidden outcomes ADR-0026 requires to be demonstrated impossible, rather
than left untested, are covered here:

* a solver ``optimal`` status being reported as verified or as a warrant --
  :class:`SolverStatusIsNotAWarrantTests`;
* a tolerance-sized gap being accepted as exact --
  :class:`ToleranceSizedGapIsNotExactTests`;
* a GPL or commercial engine being loaded --
  :class:`ExcludedLicenceTests`;
* a network call on a documented acceptance path --
  :class:`NoNetworkOnAcceptancePathTests`;
* a missing engine being silently skipped rather than recorded --
  :class:`MissingEngineIsRecordedTests`.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import io
import json
import socket
import tempfile
import unittest
import urllib.request
from fractions import Fraction
from pathlib import Path
from typing import Any

from spikes.phase5_noncommuting_sdp import comparison_algebraic as alg
from spikes.phase5_noncommuting_sdp import comparison as cmp
from spikes.phase5_noncommuting_sdp import encoding as enc
from spikes.phase5_noncommuting_sdp import engines as eng
from spikes.phase5_noncommuting_sdp import reconstruction as rec
from spikes.phase5_noncommuting_sdp.ports import (
    UNTRUSTED,
    EngineDescriptor,
    EngineProbe,
    EngineRun,
    NumericSolution,
    OperationalObservation,
)
from spikes.phase5_noncommuting_sdp.comparison_validator import CertificateInputError, validate_fixture

REPO_ROOT = Path(__file__).resolve().parents[1]
SPIKE_ROOT = REPO_ROOT / "spikes" / "phase5_noncommuting_sdp"
FIXTURE = REPO_ROOT / "fixtures" / "phase5-noncommuting-sdp" / "comparison-small-cases-v1.json"
MANIFEST = REPO_ROOT / "requirements-phase5-sdp-comparison-py314-macos-arm64.txt"

# (2 + sqrt(2)) / 4 == 0.85355339059327376..., the true optimum of both
# noncommuting fixtures. Held here as its exact algebraic form, never a float.
EXPECTED_OPTIMUM = {"rational_part": "1/2", "surd_coefficient": "1/4", "radicand": 2}

# A three-outcome case, valid for the exact rational baseline but outside the
# bounded two-outcome spectral construction. Defined here, not in the frozen
# fixture file, because it is a test input and not part of the benchmark.
THREE_OUTCOME_CASE: dict[str, Any] = {
    "schema_version": "adaivy.phase5-noncommuting-sdp-spike.v1",
    "case_id": "three-outcome-outside-bounded-construction",
    "weighted_states": [
        [["1/3", 0], [0, 0]],
        [["1/6", "1/6"], ["1/6", "1/6"]],
        [[0, 0], [0, "1/3"]],
    ],
    "primal_povm": [
        [[1, 0], [0, 0]],
        [[0, 0], [0, 0]],
        [[0, 0], [0, 1]],
    ],
    "dual_gamma": [["1/2", 0], [0, "1/2"]],
    "expected_noncommuting": True,
    "expected_zero_gap": False,
}


def load_cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def absent_engines() -> tuple[Any, ...]:
    return eng.default_engines(eng.AbsentModuleResolver())


class RecordedEngine:
    """A stand-in engine that replays a recorded observation.

    It exists so the trust properties of an engine that reports ``optimal`` can
    be asserted without a solver installed. ``provenance`` is fixed to make it
    obvious in any output that no engine actually ran.
    """

    def __init__(
        self,
        engine_id: str,
        objective: float,
        *,
        status: str = "optimal",
        elapsed: float = 1.0,
        primal_blocks: tuple[Any, ...] = (),
        dual_block: tuple[Any, ...] = (),
    ) -> None:
        self.descriptor = EngineDescriptor(
            engine_id=engine_id,
            modules=("recorded",),
            license_expression="not-applicable-recorded-test-input",
            license_url="local",
            role="recorded test input, no engine executed",
            formulation="recorded",
        )
        self._objective = objective
        self._status = status
        self._elapsed = elapsed
        self._primal_blocks = primal_blocks
        self._dual_block = dual_block

    def probe(self) -> EngineProbe:
        return EngineProbe(
            engine_id=self.descriptor.engine_id,
            available=True,
            reason_code="recorded_test_input",
        )

    def solve(self, program: Any) -> EngineRun:
        return EngineRun(
            engine_id=self.descriptor.engine_id,
            probe=self.probe(),
            solution=NumericSolution(
                engine_id=self.descriptor.engine_id,
                engine_status=self._status,
                engine_claims_optimal=True,
                settings=(("eps_abs", "1e-11"),),
                solver_actually_used=self.descriptor.engine_id,
                operational=OperationalObservation(
                    elapsed_milliseconds=self._elapsed,
                    iterations=42,
                    primal_objective=self._objective,
                    dual_objective=self._objective,
                    primal_blocks=self._primal_blocks,
                    dual_block=self._dual_block,
                ),
            ),
        )


class ExactAlgebraicDomainTests(unittest.TestCase):
    def test_sign_is_decided_exactly_with_no_tolerance(self) -> None:
        self.assertEqual(-1, alg.Surd(Fraction(1), Fraction(-1), 2).sign())
        self.assertEqual(1, alg.Surd(Fraction(-1), Fraction(1), 2).sign())
        self.assertEqual(1, alg.Surd(Fraction(2), Fraction(-1), 2).sign())
        self.assertEqual(0, alg.Surd().sign())

    def test_a_nonzero_surd_coefficient_can_never_be_exactly_zero(self) -> None:
        """For squarefree s > 1 no rational combination a + b*sqrt(s) vanishes."""

        for numerator in range(-4, 5):
            for denominator in (1, 2, 3, 7):
                for radicand in (2, 3, 5, 6, 7):
                    value = alg.Surd(Fraction(numerator, denominator), Fraction(1, 4), radicand)
                    self.assertNotEqual(0, value.sign())
                    self.assertFalse(value.is_zero())

    def test_mixing_two_quadratic_fields_is_refused(self) -> None:
        left = alg.Surd(Fraction(0), Fraction(1), 2)
        right = alg.Surd(Fraction(0), Fraction(1), 3)
        with self.assertRaisesRegex(alg.AlgebraicFieldError, "refusing to mix"):
            left + right

    def test_enclosure_is_rigorous(self) -> None:
        root = alg.Surd(Fraction(0), Fraction(1), 2)
        low, high = root.enclosure(25)
        self.assertLessEqual(low * low, Fraction(2))
        self.assertGreaterEqual(high * high, Fraction(2))
        self.assertLess(high - low, Fraction(1, 10**20))

    def test_non_squarefree_and_oversized_radicands_fail_closed(self) -> None:
        with self.assertRaisesRegex(alg.AlgebraicFieldError, "squarefree"):
            alg.Surd(Fraction(0), Fraction(1), 8)
        with self.assertRaisesRegex(alg.AlgebraicFieldError, "exceeds the bound"):
            alg.Surd(Fraction(0), Fraction(1), alg.MAX_SQUAREFREE_RADICAND + 1)

    def test_sqrt_of_a_rational_square_stays_rational(self) -> None:
        self.assertTrue(alg.Surd.sqrt_of(Fraction(9, 4)).is_rational())
        self.assertEqual(Fraction(3, 2), alg.Surd.sqrt_of(Fraction(9, 4)).as_fraction())
        self.assertFalse(alg.Surd.sqrt_of(Fraction(1, 2)).is_rational())

    def test_psd_is_decided_by_exact_minors_not_eigenvalues(self) -> None:
        tiny = Fraction(-1, 10**30)
        matrix = alg.matrix_from_pairs(
            [[(Fraction(1), Fraction(0)), (Fraction(0), Fraction(0))],
             [(Fraction(0), Fraction(0)), (tiny, Fraction(0))]]
        )
        self.assertFalse(alg.is_psd(matrix))

    def test_exact_dimension_bound_is_enforced(self) -> None:
        oversized = alg.zeros(alg.MAX_ALGEBRAIC_DIMENSION + 1)
        with self.assertRaisesRegex(alg.AlgebraicFieldError, "bounded exact dimension"):
            alg.principal_minor_signs(oversized)

    def test_square_free_extraction_is_bounded(self) -> None:
        self.assertEqual((2, 2), alg.square_free_part(8))
        with self.assertRaisesRegex(alg.AlgebraicFieldError, "bounded square-free"):
            alg.square_free_part(alg.MAX_SQUARE_EXTRACTION_INPUT + 1)


class ExactEncodingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_cases()

    def test_real_case_uses_the_identity_embedding(self) -> None:
        body = enc.encode_case(self.cases[1]).public()
        self.assertEqual("real_symmetric", body["field"])
        self.assertEqual("identity", body["real_embedding"])
        self.assertEqual("1", body["objective_scale"])
        self.assertEqual(2, body["block_dimension"])

    def test_complex_case_uses_the_exact_real_embedding_and_scale(self) -> None:
        body = enc.encode_case(self.cases[2]).public()
        self.assertEqual("complex_hermitian", body["field"])
        self.assertEqual("hermitian_to_real_2d", body["real_embedding"])
        self.assertEqual("1/2", body["objective_scale"])
        self.assertEqual(4, body["block_dimension"])
        self.assertEqual(10, body["equality_constraints"])
        self.assertIn("K = J(i*I) is orthogonal", body["real_embedding_justification"])

    def test_every_fixture_entry_converts_to_float_exactly(self) -> None:
        for case in self.cases:
            audit = enc.encode_case(case).public()["float_conversion_audit"]
            self.assertEqual([], audit["inexact_entries"])
            self.assertTrue(audit["all_entries_exactly_representable"])

    def test_an_inexact_float_conversion_is_recorded_not_hidden(self) -> None:
        case = copy.deepcopy(self.cases[1])
        case["weighted_states"][0][0][0] = "1/3"
        audit = enc.encode_case(case).public()["float_conversion_audit"]
        self.assertFalse(audit["all_entries_exactly_representable"])
        self.assertEqual("1/3", audit["inexact_entries"][0]["exact_value"])

    def test_encoding_hash_is_content_addressed_and_deterministic(self) -> None:
        first = enc.encode_case(self.cases[2]).public()
        second = enc.encode_case(copy.deepcopy(self.cases[2])).public()
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertTrue(first["content_hash"].startswith("sha256:"))
        self.assertNotEqual(
            first["content_hash"], enc.encode_case(self.cases[1]).public()["content_hash"]
        )

    def test_malformed_matrices_fail_closed(self) -> None:
        case = copy.deepcopy(self.cases[1])
        case["weighted_states"][0] = [[1, 0]]
        with self.assertRaisesRegex(CertificateInputError, "square"):
            enc.encode_case(case)
        case = copy.deepcopy(self.cases[1])
        case["weighted_states"][0] = [[0] * 5 for _ in range(5)]
        with self.assertRaisesRegex(CertificateInputError, "dimension bound"):
            enc.encode_case(case)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(CertificateInputError, "duplicate JSON key"):
            json.loads('{"a": 1, "a": 2}', object_pairs_hook=enc.reject_duplicate_keys)


class ExactReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_cases()

    def _run(self, index: int) -> rec.ReconstructionResult:
        case = self.cases[index]
        return rec.attempt_reconstruction(case, enc.encode_case(case))

    def test_commuting_control_recovers_the_known_rational_certificate(self) -> None:
        result = self._run(0)
        self.assertTrue(result.certified)
        self.assertEqual(
            {"rational_part": "1", "surd_coefficient": "0", "radicand": 1},
            result.record["exact_optimum"],
        )
        self.assertTrue(result.record["optimum_is_rational"])
        self.assertEqual([], result.record["failed_attempts"])

    def test_noncommuting_optimum_is_exactly_two_plus_root_two_over_four(self) -> None:
        for index in (1, 2):
            with self.subTest(case=self.cases[index]["case_id"]):
                result = self._run(index)
                self.assertTrue(result.certified)
                self.assertEqual(EXPECTED_OPTIMUM, result.record["exact_optimum"])
                self.assertFalse(result.record["optimum_is_rational"])
                self.assertEqual("Q(sqrt(2))", result.record["field"])

    def test_the_exact_optimum_has_a_zero_gap_and_exact_complementarity(self) -> None:
        for index in (0, 1, 2):
            with self.subTest(case=self.cases[index]["case_id"]):
                verification = self._run(index).record["attempts"][1]
                self.assertEqual("verified_exact_optimum", verification["status"])
                self.assertTrue(verification["gap_is_exactly_zero"])
                self.assertTrue(verification["complementarity_exact"])
                self.assertTrue(verification["primal_feasible_exact"])
                self.assertTrue(verification["dual_feasible_exact"])
                self.assertIsNone(verification["tolerance_used"])
                self.assertFalse(verification["uses_floating_point"])

    def test_rational_reconstruction_fails_honestly_for_the_irrational_optimum(self) -> None:
        for index in (1, 2):
            with self.subTest(case=self.cases[index]["case_id"]):
                attempt = self._run(index).record["attempts"][2]
                self.assertEqual("rational_reconstruction", attempt["attempt"])
                self.assertEqual("failed", attempt["status"])
                self.assertEqual("optimum_is_irrational", attempt["reason_code"])
                self.assertFalse(attempt["exact_residual_is_zero"])
                self.assertFalse(attempt["tolerance_sized_gap_accepted"])
                self.assertEqual(2, attempt["proof_of_irrationality"]["radicand"])

    def test_failed_attempts_are_retained_in_the_record(self) -> None:
        record = self._run(1).record
        self.assertIn("rational_reconstruction", record["failed_attempts"])
        self.assertEqual(
            [
                "exact_spectral_reconstruction",
                "exact_certificate_verification",
                "rational_reconstruction",
                "interval_reconstruction",
                "numeric_hypothesis_consistency",
            ],
            record["attempt_order"],
        )

    def test_interval_reconstruction_brackets_the_true_optimum(self) -> None:
        attempt = self._run(1).record["attempts"][3]
        low = Fraction(attempt["enclosure"]["lower_bound"])
        high = Fraction(attempt["enclosure"]["upper_bound"])
        # (2 + sqrt(2))/4 == 0.853553390593273762... lies inside the enclosure,
        # and the enclosure is far tighter than the 1/4 gap it has to resolve.
        self.assertLess(Fraction(853553390593, 10**12), low)
        self.assertLess(high, Fraction(853553390594, 10**12))
        self.assertLess(high - low, Fraction(1, 10**25))
        self.assertGreater(low, Fraction(3, 4))
        self.assertLess(high, Fraction(1))

    def test_three_outcome_case_is_recorded_unsupported_not_guessed(self) -> None:
        validate_fixture(copy.deepcopy(THREE_OUTCOME_CASE))
        program = enc.encode_case(THREE_OUTCOME_CASE)
        result = rec.attempt_reconstruction(THREE_OUTCOME_CASE, program)
        self.assertFalse(result.certified)
        construction = result.record["attempts"][0]
        self.assertEqual("unsupported_shape", construction["status"])
        self.assertEqual(
            "outcome_count_outside_bounded_construction", construction["reason_code"]
        )
        self.assertIsNone(result.record["exact_optimum"])
        self.assertEqual("unresolved_no_exact_certificate", result.record["disposition"])

    def test_state_dimension_above_two_is_recorded_unsupported(self) -> None:
        states = (alg.identity(3), alg.zeros(3))
        certificate, record = rec.spectral_reconstruction("dimension-three", states)
        self.assertIsNone(certificate)
        self.assertEqual("unsupported_shape", record["status"])
        self.assertEqual(
            "state_dimension_outside_bounded_construction", record["reason_code"]
        )

    def test_reconstruction_never_claims_a_warrant(self) -> None:
        record = self._run(1).record
        self.assertFalse(record["warrant_created"])
        self.assertIn("not an EpistemicWarrant", record["note"])


class BaselineCrossCheckTests(unittest.TestCase):
    """The file-based baseline is compared on the same fixture, as required."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = cmp.run_comparison(FIXTURE, engines=absent_engines())

    def test_documented_one_quarter_gap_is_preserved(self) -> None:
        for case in self.report["cases"][1:]:
            with self.subTest(case=case["case_id"]):
                self.assertEqual("1/4", case["baseline_rational_check"]["primal_dual_gap"])
                self.assertFalse(
                    case["baseline_rational_check"]["exact_optimum_certificate"]
                )

    def test_rational_candidate_is_proved_exactly_suboptimal(self) -> None:
        for case in self.report["cases"][1:]:
            with self.subTest(case=case["case_id"]):
                check = case["baseline_cross_check"]
                self.assertEqual("baseline_below_optimum", check["comparison"])
                self.assertTrue(check["baseline_candidate_proved_suboptimal"])
                # (sqrt(2) - 1)/4, the exact amount the rational candidate misses by.
                self.assertEqual(
                    {"rational_part": "-1/4", "surd_coefficient": "1/4", "radicand": 2},
                    check["exact_shortfall"],
                )

    def test_commuting_control_baseline_is_proved_optimal(self) -> None:
        check = self.report["cases"][0]["baseline_cross_check"]
        self.assertEqual("equal", check["comparison"])
        self.assertTrue(check["baseline_candidate_proved_optimal"])


class ToleranceSizedGapIsNotExactTests(unittest.TestCase):
    """FORBIDDEN OUTCOME: a tolerance-sized gap accepted as an exact gap."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.case = load_cases()[0]
        cls.program = enc.encode_case(cls.case)
        cls.states = tuple(
            rec.to_algebraic(enc.parse_matrix(item, label="state"))
            for item in cls.case["weighted_states"]
        )
        cls.povm = (((1.0, 0.0), (0.0, 0.0)), ((0.0, 0.0), (0.0, 1.0)))

    def _audit(self, dual: tuple[tuple[float, ...], ...]) -> dict[str, Any]:
        return rec.float_point_exact_audit(
            self.program, self.states, self.povm, dual, source="recorded_test_input"
        )

    def test_an_exactly_optimal_dyadic_point_is_accepted(self) -> None:
        """Control: the audit is not vacuously rejecting everything."""

        audit = self._audit(((0.5, 0.0), (0.0, 0.5)))
        self.assertEqual("accepted_exact_certificate_from_rationalised_point", audit["status"])
        self.assertTrue(audit["gap_is_exactly_zero"])
        self.assertTrue(audit["complementarity_exact"])
        self.assertTrue(audit["exact_optimum_certificate"])

    def test_a_gap_of_one_billionth_is_rejected(self) -> None:
        audit = self._audit(((0.5 + 5e-10, 0.0), (0.0, 0.5 + 5e-10)))
        self.assertEqual("rejected_not_an_exact_certificate", audit["status"])
        self.assertEqual("tolerance_sized_gap_is_not_an_exact_gap", audit["reason_code"])
        self.assertFalse(audit["gap_is_exactly_zero"])
        self.assertFalse(audit["exact_optimum_certificate"])
        self.assertIsNone(audit["tolerance_used"])
        low = Fraction(audit["gap_enclosure"]["lower_bound"])
        self.assertGreater(low, 0)
        self.assertLess(low, Fraction(1, 10**8))

    def test_a_gap_of_one_part_in_ten_to_the_fifteenth_is_still_rejected(self) -> None:
        audit = self._audit(((0.5 + 5e-16, 0.0), (0.0, 0.5)))
        self.assertEqual("rejected_not_an_exact_certificate", audit["status"])
        self.assertEqual("tolerance_sized_gap_is_not_an_exact_gap", audit["reason_code"])
        self.assertFalse(audit["exact_optimum_certificate"])

    def test_float_conversion_is_exact_and_invents_nothing(self) -> None:
        audit = self._audit(((0.5 + 5e-10, 0.0), (0.0, 0.5 + 5e-10)))
        self.assertEqual("float_to_exact_dyadic_rational", audit["conversion"])
        # The exact gap is the exact dyadic value, not a rounded one.
        expected = 2 * Fraction(0.5 + 5e-10) - Fraction(1)
        self.assertEqual(
            expected, Fraction(audit["primal_dual_gap_exact_form"]["rational_part"])
        )

    def test_an_incomplete_engine_point_is_recorded_not_assumed(self) -> None:
        audit = rec.float_point_exact_audit(
            self.program, self.states, (), (), source="recorded_test_input"
        )
        self.assertEqual("not_attempted", audit["status"])
        self.assertEqual("incomplete_engine_point", audit["reason_code"])


class ExcludedLicenceTests(unittest.TestCase):
    """FORBIDDEN OUTCOME: a GPL or commercial engine being loaded."""

    def test_every_excluded_module_is_refused_by_name(self) -> None:
        for name in eng.EXCLUDED_MODULES:
            with self.subTest(module=name):
                with self.assertRaises(eng.LicenseNotPermittedError) as caught:
                    eng.authorize_module(name)
                self.assertIn("excluded by the ADR-0045 licence restriction", str(caught.exception))

    def test_cvxopt_and_mosek_are_named_explicitly(self) -> None:
        self.assertIn("cvxopt", eng.EXCLUDED_MODULES)
        self.assertIn("mosek", eng.EXCLUDED_MODULES)
        self.assertIn("GPL", eng.EXCLUDED_MODULES["cvxopt"])
        self.assertIn("commercial", eng.EXCLUDED_MODULES["mosek"])

    def test_a_submodule_of_an_excluded_package_is_also_refused(self) -> None:
        with self.assertRaises(eng.LicenseNotPermittedError):
            eng.authorize_module("cvxopt.solvers")

    def test_an_undeclared_module_is_refused(self) -> None:
        with self.assertRaisesRegex(eng.LicenseNotPermittedError, "not in the ADR-0045"):
            eng.authorize_module("some_unreviewed_solver")

    def test_allowlist_and_exclusion_list_are_disjoint(self) -> None:
        self.assertEqual(
            set(), set(eng.AUTHORIZED_MODULES) & set(eng.EXCLUDED_MODULES)
        )

    def test_every_authorised_module_declares_a_permitted_licence(self) -> None:
        for name, entry in eng.AUTHORIZED_MODULES.items():
            with self.subTest(module=name):
                self.assertIn(entry.license_expression, eng.PERMITTED_LICENSE_EXPRESSIONS)

    def test_the_resolvers_refuse_an_excluded_module_before_importing(self) -> None:
        for resolver in (eng.GatedImportlibResolver(), eng.AbsentModuleResolver()):
            with self.subTest(resolver=type(resolver).__name__):
                with self.assertRaises(eng.LicenseNotPermittedError):
                    resolver.load_gated_module("cvxopt")
                with self.assertRaises(eng.LicenseNotPermittedError):
                    resolver.gated_module_version("mosek")

    def test_no_excluded_name_appears_in_a_gated_load_in_the_spike(self) -> None:
        offenders: list[str] = []
        for path in sorted(SPIKE_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if name not in {"import_module", "find_spec", "load_gated_module", "gated_module_version"}:
                    continue
                for argument in node.args:
                    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                        root = argument.value.split(".", 1)[0].lower()
                        if root in eng.EXCLUDED_MODULES:
                            offenders.append(f"{path.name}:{node.lineno} loads {argument.value}")
        self.assertEqual([], offenders)

    def test_the_pinned_manifest_excludes_copyleft_and_commercial_engines(self) -> None:
        text = MANIFEST.read_text(encoding="utf-8")
        requirements = [
            line.split("==")[0].strip().lower()
            for line in text.splitlines()
            if "==" in line and not line.lstrip().startswith("#")
        ]
        self.assertIn("clarabel", requirements)
        self.assertIn("scs", requirements)
        self.assertIn("cvxpy", requirements)
        for name in eng.EXCLUDED_MODULES:
            self.assertNotIn(name, requirements)

    def test_the_manifest_pins_every_requirement_to_a_sha256(self) -> None:
        lines = MANIFEST.read_text(encoding="utf-8").splitlines()
        self.assertIn("--require-hashes", lines)
        self.assertIn("--only-binary=:all:", lines)
        pinned = [item for item in lines if "==" in item and not item.lstrip().startswith("#")]
        hashes = [item for item in lines if "--hash=sha256:" in item]
        self.assertEqual(len(pinned), len(hashes))
        for item in hashes:
            digest = item.split("--hash=sha256:")[1].strip()
            self.assertEqual(64, len(digest))
            self.assertTrue(all(char in "0123456789abcdef" for char in digest))


class MissingEngineIsRecordedTests(unittest.TestCase):
    """FORBIDDEN OUTCOME: a missing engine silently skipped."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = cmp.run_comparison(FIXTURE, engines=absent_engines())

    def test_both_engines_return_a_missing_tool_record(self) -> None:
        for case in self.report["cases"]:
            self.assertEqual(2, len(case["engine_records"]))
            for record in case["engine_records"]:
                with self.subTest(case=case["case_id"], engine=record["engine"]["engine_id"]):
                    self.assertFalse(record["executed"])
                    self.assertEqual("missing_tool", record["result"]["outcome"])
                    self.assertEqual("module_absent", record["result"]["reason_code"])
                    self.assertFalse(record["result"]["network_attempted"])
                    self.assertFalse(record["result"]["creates_warrant"])
                    self.assertFalse(record["counts_towards_independent_engines"])

    def test_missing_tool_records_are_collected_at_report_level(self) -> None:
        self.assertEqual(6, len(self.report["missing_tool_records"]))
        self.assertEqual(
            {"clarabel", "cvxpy-scs"},
            {item["engine_id"] for item in self.report["missing_tool_records"]},
        )

    def test_the_missing_tool_detail_points_at_the_pinned_manifest(self) -> None:
        detail = self.report["cases"][0]["engine_records"][0]["result"]["detail"]
        self.assertIn("requirements-phase5-sdp-comparison-py314-macos-arm64.txt", detail)
        self.assertIn("never counted as a pass", detail)

    def test_the_two_engine_clause_is_reported_unsatisfied(self) -> None:
        self.assertEqual(2, self.report["independent_engines_required"])
        self.assertEqual(0, self.report["minimum_independent_engines_executed"])
        self.assertFalse(self.report["spec_clauses"]["two_independent_engines_run"])
        self.assertEqual(
            "incomplete_engines_absent_or_refused", self.report["experiment_status"]
        )

    def test_retention_clauses_are_not_claimed_when_no_engine_ran(self) -> None:
        clauses = self.report["spec_clauses"]
        self.assertEqual(
            "not_exercised_no_engine_executed", clauses["raw_solver_status_retained"]
        )
        self.assertEqual(
            "not_exercised_no_engine_executed",
            clauses["raw_residuals_iterations_timings_retained"],
        )

    def test_the_exact_result_still_stands_with_no_engine(self) -> None:
        """An absent engine blocks the comparison, not the exact reconstruction."""

        self.assertTrue(self.report["all_cases_exactly_certified"])
        for case in self.report["cases"]:
            self.assertIn("exact_algebraic_reconstruction", case["certified_by"])

    def test_an_engine_that_refuses_on_licence_grounds_is_recorded(self) -> None:
        descriptor = eng.CvxpyScsEngine().descriptor
        probe = EngineProbe(engine_id=descriptor.engine_id, available=True, reason_code="available")
        run = EngineRun(
            engine_id=descriptor.engine_id,
            probe=probe,
            missing_tool=eng.MissingTool(
                engine_id=descriptor.engine_id,
                reason_code="forbidden_solver_present_in_environment",
                detail="refusing to run",
            ),
        )
        self.assertFalse(run.executed)
        self.assertIn("MOSEK", eng.FORBIDDEN_CVXPY_SOLVERS)
        self.assertIn("CVXOPT", eng.FORBIDDEN_CVXPY_SOLVERS)


class SolverStatusIsNotAWarrantTests(unittest.TestCase):
    """FORBIDDEN OUTCOME: an `optimal` status reported as verified."""

    def test_numeric_solution_has_no_verification_field(self) -> None:
        fields = set(NumericSolution.__dataclass_fields__)
        for banned in ("verified", "warrant", "proved", "proof", "trusted", "correct"):
            self.assertEqual(
                [], [name for name in fields if banned in name], f"{banned} must not be a field"
            )

    def test_trust_is_a_constant_that_cannot_be_reassigned(self) -> None:
        solution = RecordedEngine("clarabel", 0.85).solve(None).solution
        self.assertEqual(UNTRUSTED, solution.trust)
        self.assertEqual("untrusted_candidate", solution.trust)
        self.assertNotIn("trust", NumericSolution.__dataclass_fields__)
        with self.assertRaises((AttributeError, TypeError)):
            solution.trust = "verified"

    def test_an_optimal_status_does_not_certify_an_unresolvable_case(self) -> None:
        engine = RecordedEngine("clarabel", 0.6666666666666666, status="optimal")
        case = cmp.run_case(THREE_OUTCOME_CASE, (engine,))
        self.assertEqual("optimal", case["engine_records"][0]["result"]["engine_status"])
        self.assertTrue(case["engine_records"][0]["result"]["engine_claims_optimal"])
        self.assertEqual([], case["certified_by"])
        self.assertFalse(case["exact_optimum_certified"])
        self.assertEqual("unresolved_no_exact_certificate", case["disposition"])
        self.assertFalse(case["engine_status_contributed_to_disposition"])
        self.assertFalse(case["warrant_created"])

    def test_engine_agreement_is_marked_as_not_evidence(self) -> None:
        engines = (RecordedEngine("clarabel", 0.85355), RecordedEngine("cvxpy-scs", 0.85355))
        case = cmp.run_case(load_cases()[1], engines)
        agreement = case["engine_agreement"]
        self.assertFalse(agreement["is_evidence_of_correctness"])
        self.assertFalse(agreement["contributes_to_disposition"])
        self.assertIn("NOT evidence of correctness", agreement["note"])
        self.assertEqual(
            0.0, agreement["pairwise_absolute_differences"][0]["absolute_difference"]
        )

    def test_two_agreeing_engines_do_not_certify_an_unresolvable_case(self) -> None:
        engines = (RecordedEngine("clarabel", 0.666), RecordedEngine("cvxpy-scs", 0.666))
        case = cmp.run_case(THREE_OUTCOME_CASE, engines)
        self.assertEqual(2, case["independent_engines_executed"])
        self.assertTrue(case["two_engine_clause_satisfied"])
        self.assertEqual([], case["certified_by"])
        self.assertEqual("unresolved_no_exact_certificate", case["disposition"])

    def test_an_unregistered_engine_cannot_count_towards_the_clause(self) -> None:
        engine = RecordedEngine("some-unreviewed-engine", 0.85355)
        case = cmp.run_case(load_cases()[1], (engine,))
        record = case["engine_records"][0]
        self.assertFalse(record["authorised_registry_entry"])
        self.assertFalse(record["counts_towards_independent_engines"])
        self.assertEqual(0, case["independent_engines_executed"])

    def test_the_report_level_guardrails_are_all_negative(self) -> None:
        report = cmp.run_comparison(FIXTURE, engines=absent_engines())
        guardrails = report["guardrails"]
        self.assertFalse(guardrails["warrant_created"])
        self.assertFalse(guardrails["phase5_integrated"])
        self.assertFalse(guardrails["phase5_sealed_records_touched"])
        self.assertFalse(guardrails["search_tiers_enabled"])
        self.assertFalse(guardrails["network_attempted"])
        self.assertFalse(guardrails["solver_status_may_create_warrant"])
        self.assertFalse(guardrails["engine_agreement_is_evidence_of_correctness"])
        self.assertFalse(guardrails["tolerance_sized_gap_accepted_as_exact"])
        self.assertEqual(0, guardrails["model_calls"])
        self.assertFalse(report["authorization"]["phase5_integration_authorised"])
        self.assertFalse(report["authorization"]["search_tiers_2_to_4_authorised"])
        self.assertFalse(report["authorization"]["warrant_creation_authorised"])


class ComparisonReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = cmp.run_comparison(FIXTURE, engines=absent_engines())

    def test_report_declares_its_schema_version_and_both_hashes(self) -> None:
        self.assertEqual(
            "adaivy.phase5-noncommuting-sdp-comparison.v1", self.report["schema_version"]
        )
        self.assertTrue(self.report["content_hash"].startswith("sha256:"))
        self.assertTrue(self.report["operational_hash"].startswith("sha256:"))
        self.assertEqual(cmp.SPEC_REFERENCE, self.report["spec_reference"])

    def test_report_verifies_its_own_hashes(self) -> None:
        verification = cmp.verify_report(copy.deepcopy(self.report))
        self.assertTrue(verification["verified"])
        self.assertTrue(verification["semantic_hash_verified"])
        self.assertTrue(verification["operational_hash_verified"])

    def test_tampering_with_an_exact_value_breaks_the_semantic_hash(self) -> None:
        tampered = copy.deepcopy(self.report)
        tampered["cases"][1]["reconstruction"]["exact_optimum"]["surd_coefficient"] = "1/2"
        verification = cmp.verify_report(tampered)
        self.assertFalse(verification["verified"])
        self.assertFalse(verification["semantic_hash_verified"])

    def test_an_unsupported_schema_version_fails_closed(self) -> None:
        tampered = copy.deepcopy(self.report)
        tampered["schema_version"] = "adaivy.phase5-noncommuting-sdp-comparison.v2"
        with self.assertRaisesRegex(CertificateInputError, "unsupported report schema"):
            cmp.verify_report(tampered)
        del tampered["content_hash"]
        tampered["schema_version"] = cmp.COMPARISON_SCHEMA_VERSION
        with self.assertRaisesRegex(CertificateInputError, "missing content_hash"):
            cmp.verify_report(tampered)

    def test_all_three_frozen_cases_including_the_complex_one_are_evaluated(self) -> None:
        self.assertEqual(3, self.report["cases_evaluated"])
        self.assertEqual(
            ["commuting-exact-control", "real-noncommuting-rational-candidate",
             "complex-noncommuting-rational-candidate"],
            [case["case_id"] for case in self.report["cases"]],
        )
        self.assertEqual(
            ["real_symmetric", "real_symmetric", "complex_hermitian"],
            [case["field"] for case in self.report["cases"]],
        )

    def test_report_is_byte_identical_across_runs_with_engines_absent(self) -> None:
        first = cmp.canonical_report_bytes(cmp.run_comparison(FIXTURE, engines=absent_engines()))
        second = cmp.canonical_report_bytes(cmp.run_comparison(FIXTURE, engines=absent_engines()))
        self.assertEqual(first, second)

    def test_exact_encoding_is_retained_per_case(self) -> None:
        for case in self.report["cases"]:
            encoding = case["exact_encoding"]
            self.assertEqual("exact_rational", encoding["arithmetic"])
            self.assertTrue(encoding["content_hash"].startswith("sha256:"))
            self.assertEqual(
                encoding["content_hash"],
                enc.encode_case(
                    next(item for item in load_cases() if item["case_id"] == case["case_id"])
                ).public()["content_hash"],
            )

    def test_authorization_block_records_the_licence_restriction(self) -> None:
        authorization = self.report["authorization"]
        self.assertEqual("ADR-0045", authorization["adr"])
        self.assertEqual("permissive licences only", authorization["license_restriction"])
        self.assertIn("cvxopt", authorization["excluded_modules"])
        self.assertIn("mosek", authorization["excluded_modules"])
        self.assertIn("clarabel", authorization["permitted_modules"])
        self.assertEqual(
            "Apache-2.0", authorization["permitted_modules"]["clarabel"]["license_expression"]
        )


class SemanticVersusOperationalHashTests(unittest.TestCase):
    def test_marked_operational_objects_are_stripped_from_the_semantic_preimage(self) -> None:
        value = {"a": 1, "timings": {"hash_class": "operational_only", "elapsed": 12.5}}
        self.assertEqual(
            {"a": 1, "timings": cmp.SEMANTIC_PLACEHOLDER}, cmp.semantic_preimage(value)
        )

    def test_the_hashes_themselves_are_excluded_from_the_semantic_preimage(self) -> None:
        preimage = cmp.semantic_preimage({"content_hash": "x", "operational_hash": "y", "k": 1})
        self.assertEqual({"k": 1}, preimage)

    def test_timing_variance_changes_the_operational_hash_only(self) -> None:
        case = load_cases()[1]
        fast = cmp.run_case(case, (RecordedEngine("clarabel", 0.85355, elapsed=1.0),))
        slow = cmp.run_case(case, (RecordedEngine("clarabel", 0.85355, elapsed=987.6),))
        self.assertNotEqual(
            fast["engine_records"][0]["operational"]["elapsed_milliseconds"],
            slow["engine_records"][0]["operational"]["elapsed_milliseconds"],
        )
        self.assertEqual(cmp.semantic_preimage(fast), cmp.semantic_preimage(slow))
        self.assertNotEqual(fast, slow)

    def test_a_semantic_change_changes_both_hashes(self) -> None:
        case = load_cases()[1]
        solved = cmp.run_case(case, (RecordedEngine("clarabel", 0.85355, status="optimal"),))
        stalled = cmp.run_case(
            case, (RecordedEngine("clarabel", 0.85355, status="max_iterations"),)
        )
        self.assertNotEqual(cmp.semantic_preimage(solved), cmp.semantic_preimage(stalled))

    def test_operational_observations_are_still_retained_in_the_report(self) -> None:
        case = cmp.run_case(load_cases()[1], (RecordedEngine("clarabel", 0.85355, elapsed=7.5),))
        operational = case["engine_records"][0]["operational"]
        self.assertEqual(7.5, operational["elapsed_milliseconds"])
        self.assertEqual(42, operational["iterations"])
        self.assertEqual(0.85355, operational["primal_objective"])
        self.assertEqual("operational_only", operational["hash_class"])


class NoNetworkOnAcceptancePathTests(unittest.TestCase):
    """FORBIDDEN OUTCOME: a network call on a documented acceptance path."""

    def test_the_whole_comparison_runs_with_every_socket_poisoned(self) -> None:
        def refuse(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("the acceptance path must not touch the network")

        originals = {
            "socket": socket.socket,
            "create_connection": socket.create_connection,
            "getaddrinfo": socket.getaddrinfo,
            "urlopen": urllib.request.urlopen,
        }
        socket.socket = refuse  # type: ignore[assignment]
        socket.create_connection = refuse  # type: ignore[assignment]
        socket.getaddrinfo = refuse  # type: ignore[assignment]
        urllib.request.urlopen = refuse  # type: ignore[assignment]
        try:
            report = cmp.run_comparison(FIXTURE, engines=absent_engines())
        finally:
            socket.socket = originals["socket"]  # type: ignore[assignment]
            socket.create_connection = originals["create_connection"]  # type: ignore[assignment]
            socket.getaddrinfo = originals["getaddrinfo"]  # type: ignore[assignment]
            urllib.request.urlopen = originals["urlopen"]  # type: ignore[assignment]
        self.assertTrue(report["all_cases_exactly_certified"])
        self.assertFalse(report["guardrails"]["network_attempted"])

    def test_the_spike_imports_no_network_module_anywhere(self) -> None:
        network_roots = {
            "socket", "ssl", "asyncio", "selectors", "webbrowser", "urllib",
            "http", "ftplib", "smtplib", "imaplib", "poplib", "xmlrpc",
            "socketserver", "requests", "httpx", "urllib3", "aiohttp",
        }
        offenders: list[str] = []
        for path in sorted(SPIKE_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                for name in names:
                    if name.split(".", 1)[0] in network_roots:
                        offenders.append(f"{path.name}:{node.lineno} imports {name}")
        self.assertEqual([], offenders)


class CommandLineTests(unittest.TestCase):
    """The CLI must emit the report and report a shortfall, never hide one."""

    @staticmethod
    def _run(argv: list[str]) -> tuple[int, dict[str, Any]]:
        from spikes.phase5_noncommuting_sdp import comparison_cli

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = comparison_cli.main(argv)
        return (code, json.loads(buffer.getvalue()))

    def test_run_without_engines_exits_one_and_still_emits_the_report(self) -> None:
        code, payload = self._run(["run", "--fixture", str(FIXTURE), "--no-engines"])
        self.assertEqual(1, code)
        self.assertEqual("incomplete_engines_absent_or_refused", payload["experiment_status"])
        self.assertEqual(6, len(payload["missing_tool_records"]))
        self.assertTrue(payload["all_cases_exactly_certified"])

    def test_the_emitted_report_round_trips_through_inspect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            self._run(["run", "--fixture", str(FIXTURE), "--no-engines", "--output", str(output)])
            code, payload = self._run(["inspect", str(output)])
            self.assertEqual(1, code, "an incomplete comparison must not exit zero")
            self.assertTrue(payload["verified"])
            self.assertTrue(payload["semantic_hash_verified"])
            self.assertTrue(payload["operational_hash_verified"])

    def test_inspect_reports_a_tampered_report_as_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            self._run(["run", "--fixture", str(FIXTURE), "--no-engines", "--output", str(output)])
            document = json.loads(output.read_text(encoding="utf-8"))
            document["all_cases_exactly_certified"] = False
            output.write_text(json.dumps(document), encoding="utf-8")
            code, payload = self._run(["inspect", str(output)])
            self.assertEqual(1, code)
            self.assertFalse(payload["verified"])

    def test_a_missing_fixture_exits_two(self) -> None:
        code, payload = self._run(["run", "--fixture", "does/not/exist.json", "--no-engines"])
        self.assertEqual(2, code)
        self.assertIn("error", payload)

    def test_a_duplicate_key_in_a_report_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            output.write_text('{"schema_version": 1, "schema_version": 2}', encoding="utf-8")
            code, payload = self._run(["inspect", str(output)])
            self.assertEqual(2, code)
            self.assertIn("duplicate JSON key", payload["error"])


class SpikeIsolationTests(unittest.TestCase):
    """The spike stays a spike: no Phase 5 integration, no tier enabling."""

    def test_the_spike_does_not_import_the_phase5_implementation(self) -> None:
        offenders: list[str] = []
        for path in sorted(SPIKE_ROOT.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    if name.split(".", 1)[0] == "math_research":
                        offenders.append(f"{path.name}:{node.lineno} imports {name}")
        self.assertEqual([], offenders)

    def test_the_spike_writes_nothing_outside_an_explicit_output_path(self) -> None:
        """Only the CLI's --output argument may write, and only where told."""

        writers: set[str] = set()
        for path in sorted(SPIKE_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "attr", None)
                    if name in {"write_bytes", "write_text", "mkdir", "unlink", "rmtree"}:
                        writers.add(f"{path.name} calls {name}")
        self.assertEqual({"comparison_cli.py calls write_bytes"}, writers)

    def test_the_spike_declares_no_third_party_import_at_module_scope(self) -> None:
        import sys

        offenders: list[str] = []
        for path in sorted(SPIKE_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in tree.body:
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                for name in names:
                    root = name.split(".", 1)[0]
                    if root not in sys.stdlib_module_names and root != "spikes":
                        offenders.append(f"{path.name}:{node.lineno} imports {name}")
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
