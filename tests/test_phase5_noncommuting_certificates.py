"""ADR-0035 acceptance suite: noncommuting Phase 5 verifies, never discovers.

Under ADR-0026 this suite is the sole executable record of the slice's
thresholds, so it asserts ADR-0035's five boundaries as properties and
demonstrates each forbidden outcome impossible rather than leaving it untested.
The forbidden outcomes are: a tolerance-admitted gap, a discovered optimum, a
certificate without a principal, a float on the certificate path, a missing
coverage field, and an out-of-field value.
"""

from __future__ import annotations

import ast
import copy
import inspect
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from math_research.phase5 import (
    NONCOMMUTING_CASE_VERSION,
    NONCOMMUTING_FIXTURE_VERSION,
    NONCOMMUTING_REPORT_VERSION,
    NONCOMMUTING_RESULT_VERSION,
)
from math_research.phase5 import algebraic as alg
from math_research.phase5 import noncommuting as nc
from math_research.phase5 import spectrum as sp
from math_research.phase5.exact_matrices import is_psd, is_zero_matrix, parse_matrix
from math_research.phase5.ports import CertificateSource, FrozenFixtureCertificates
from math_research.phase5.quantum import DiagonalCase, run_case
from math_research.phase5.serialization import canonical_bytes, canonical_hash
from math_research.phase5.service import Phase5Service
from math_research.phase5.workspace import Phase5ValidationError, Phase5Workspace, decode_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "fixtures/phase5/noncommuting-certificates-v1.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text("utf-8"))
DIAGONAL_FIXTURE = json.loads(
    (ROOT / "fixtures/phase5/quantum-diagonal-v1.json").read_text("utf-8")
)
T0 = "2026-08-20T12:00:00Z"
T1 = "2026-08-20T12:01:00Z"

# Frozen instants only; no clock, no randomness, no environment.
PINNED_FIXTURE_HASH = "sha256:3504f1445a569515a07f3657dc91d858b9d9d574a6b057151b41134dd265f439"
PINNED_REPORT_HASH = "sha256:ea7865cf9a36dca9965c0073a0b3b2c35a3afa80555b7ecdd5018a49645152c3"

# The measured outcome, pinned in BOTH directions: a silent improvement is as
# much a failure as a regression, because both are unreviewed changes to a
# frozen benchmark.
MEASURED = {
    "commuting-exact-control": ("certificate_supplied_and_verified", "0", "Q(i)"),
    "real-noncommuting-rational-candidate": (
        "certificate_supplied_gap_not_closed", "1/4", "Q(i)",
    ),
    "complex-noncommuting-rational-candidate": (
        "certificate_supplied_gap_not_closed", "1/4", "Q(i)",
    ),
    "real-noncommuting-algebraic-certificate": (
        "certificate_supplied_and_verified", "0", "Q(sqrt(2))(i)",
    ),
    "complex-noncommuting-algebraic-certificate": (
        "certificate_supplied_and_verified", "0", "Q(sqrt(2))(i)",
    ),
    "real-noncommuting-algebraic-certificate-radicand-five": (
        "certificate_supplied_and_verified", "0", "Q(sqrt(5))(i)",
    ),
    "real-noncommuting-certificate-withheld": (
        "unresolved_no_certificate_supplied", None, "Q(i)",
    ),
    "real-noncommuting-irreducible-cubic-boundary": (
        "certificate_supplied_outside_represented_field", "1/2", "Q(i)",
    ),
}

PRODUCTION_MODULES = (
    "algebraic.py",
    "exact_matrices.py",
    "noncommuting.py",
    "ports.py",
    "spectrum.py",
)


def module_tree(name: str) -> ast.Module:
    path = ROOT / "src/math_research/phase5" / name
    return ast.parse(path.read_text("utf-8"), filename=str(path))


def case(case_id: str) -> dict:
    return copy.deepcopy(next(item for item in FIXTURE["cases"] if item["case_id"] == case_id))


def fixture_with(*cases: dict) -> dict:
    return {
        "schema_version": NONCOMMUTING_FIXTURE_VERSION,
        "benchmark_id": nc.BENCHMARK_ID,
        "cases": [copy.deepcopy(item) for item in cases],
    }


def verify_one(value: dict) -> dict:
    return nc.verify_case(nc.NoncommutingCase.from_value(value))


class MeasuredOutcomeTests(unittest.TestCase):
    """What executes, pinned in both directions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = nc.verify_fixture(FIXTURE)
        cls.by_case = {item["case_id"]: item for item in cls.report["results"]}

    def test_fixture_and_report_hashes_are_pinned(self) -> None:
        self.assertEqual(PINNED_FIXTURE_HASH, canonical_hash(FIXTURE))
        self.assertEqual(PINNED_REPORT_HASH, self.report["content_hash"])
        self.assertEqual(NONCOMMUTING_REPORT_VERSION, self.report["schema_version"])

    def test_every_case_matches_its_measured_coverage_gap_and_field(self) -> None:
        self.assertEqual(sorted(MEASURED), sorted(self.by_case))
        for case_id, (status, gap, notation) in sorted(MEASURED.items()):
            with self.subTest(case_id=case_id):
                result = self.by_case[case_id]
                self.assertEqual(status, result["coverage_status"])
                self.assertEqual(gap, result["primal_dual_gap"])
                self.assertEqual(notation, result["field"]["notation"])
                self.assertEqual(NONCOMMUTING_RESULT_VERSION, result["schema_version"])

    def test_the_quarter_gap_closes_on_byte_identical_ensembles(self) -> None:
        """The closing cases are not easier problems: same ensemble, new field."""
        for open_case, closed_case in (
            ("real-noncommuting-rational-candidate", "real-noncommuting-algebraic-certificate"),
            (
                "complex-noncommuting-rational-candidate",
                "complex-noncommuting-algebraic-certificate",
            ),
        ):
            with self.subTest(case=closed_case):
                self.assertEqual(
                    canonical_bytes(case(open_case)["weighted_states"]),
                    canonical_bytes(case(closed_case)["weighted_states"]),
                )
                self.assertEqual("1/4", self.by_case[open_case]["primal_dual_gap"])
                self.assertEqual("0", self.by_case[closed_case]["primal_dual_gap"])

    def test_zero_means_zero_entry_by_entry(self) -> None:
        for case_id in self.report["verified_certificate_case_ids"]:
            with self.subTest(case_id=case_id):
                result = self.by_case[case_id]
                self.assertTrue(result["complementarity_exact"])
                self.assertEqual(result["primal_value"], result["dual_value"])
                residuals = (
                    result["left_complementarity_residuals"]
                    + result["right_complementarity_residuals"]
                )
                for matrix in residuals:
                    self.assertTrue(is_zero_matrix(parse_matrix(matrix)))

    def test_verified_certificates_agree_with_the_independent_closed_form(self) -> None:
        for case_id in self.report["verified_certificate_case_ids"]:
            with self.subTest(case_id=case_id):
                result = self.by_case[case_id]
                self.assertTrue(result["primal_matches_independent_crosscheck"])
                self.assertTrue(result["dual_matches_independent_crosscheck"])
                self.assertTrue(result["independent_closed_form_crosscheck"]["available"])

    def test_the_field_is_measured_and_three_radicands_are_used(self) -> None:
        self.assertEqual([1, 2, 5], self.report["radicands_used"])
        for result in self.report["results"]:
            self.assertEqual("measured_from_case_values", result["field"]["radicand_source"])

    def test_the_cubic_boundary_is_a_measured_result(self) -> None:
        result = self.by_case["real-noncommuting-irreducible-cubic-boundary"]
        probe = result["spectral_field_probe"]
        self.assertEqual("irreducible_cubic_spectrum", probe["determination"])
        self.assertEqual(3, probe["residual_degree"])
        self.assertTrue(probe["residual_irreducible"])
        self.assertEqual([], probe["rational_roots"])
        self.assertEqual(
            {"negative": 1, "positive": 2, "zero": 0}, probe["real_root_signature"]
        )
        self.assertEqual(
            ["1", "0", "-3/50", "3/1000"], probe["characteristic_polynomial"]
        )
        self.assertFalse(result["optimum_representable_in_quadratic_extension"])
        self.assertIn("hence has degree 3 over the rationals", probe["trace_norm_argument"])


class VerificationOnlyTests(unittest.TestCase):
    """ADR-0035 boundary 1: verification only, never discovery."""

    def test_a_case_without_a_certificate_is_explicitly_unresolved(self) -> None:
        result = verify_one(case("real-noncommuting-certificate-withheld"))
        self.assertEqual(nc.COVERAGE_UNRESOLVED, result["coverage_status"])
        self.assertFalse(result["certificate_supplied"])
        self.assertIsNone(result["certificate_provenance"])
        self.assertIsNone(result["primal_value"])
        self.assertIsNone(result["dual_value"])
        self.assertIsNone(result["primal_dual_gap"])
        self.assertIsNone(result["primal_feasible"])
        self.assertIn("neither searched for one nor defaulted", result["unresolved_reason"])
        self.assertFalse(result["coverage"]["discovery_performed"])

    def test_unresolved_even_where_the_closed_form_crosscheck_is_available(self) -> None:
        """The cross-check yields a scalar and cannot stand in for a certificate."""
        result = verify_one(case("real-noncommuting-certificate-withheld"))
        crosscheck = result["independent_closed_form_crosscheck"]
        self.assertTrue(crosscheck["available"])
        self.assertEqual({"radicand": 2, "rational": "1/2", "surd": "1/4"}, crosscheck["optimum"])
        self.assertFalse(crosscheck["is_certificate"])
        self.assertFalse(crosscheck["is_discovery"])
        self.assertFalse(crosscheck["produces_povm"])
        self.assertFalse(crosscheck["produces_dual_operator"])
        self.assertEqual(nc.COVERAGE_UNRESOLVED, result["coverage_status"])

    def test_no_source_module_constructs_a_certificate(self) -> None:
        constructions = []
        for path in sorted((ROOT / "src/math_research").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text("utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                    if name == "SuppliedCertificate":
                        constructions.append(f"{path.name}:{node.lineno}")
        self.assertEqual([], constructions)

    def test_the_only_certificate_construction_site_is_the_input_parser(self) -> None:
        tree = module_tree("noncommuting.py")
        klass = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "SuppliedCertificate"
        )
        constructing = set()
        for member in klass.body:
            if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(member):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "cls":
                    constructing.add(member.name)
        self.assertEqual({"from_value"}, constructing)

    def test_no_function_outside_the_parser_returns_a_certificate(self) -> None:
        offenders = []
        for name in PRODUCTION_MODULES:
            for node in ast.walk(module_tree(name)):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                annotation = ast.unparse(node.returns) if node.returns else ""
                if "SuppliedCertificate" in annotation and node.name != "from_value":
                    offenders.append(f"{name}:{node.name}")
        self.assertEqual([], offenders)

    def test_a_certificate_declaring_a_solver_origin_is_rejected(self) -> None:
        for derivation in nc.PROHIBITED_DERIVATIONS:
            with self.subTest(derivation=derivation):
                value = case("real-noncommuting-algebraic-certificate")
                value["certificate"]["derivation"] = derivation
                with self.assertRaises(nc.DiscoveryProhibitedError):
                    verify_one(value)

    def test_a_discovered_optimum_status_is_unproducible(self) -> None:
        self.assertNotIn(nc.FORBIDDEN_COVERAGE_STATUS, nc.COVERAGE_STATUSES)
        with self.assertRaises(AssertionError):
            nc._checked_coverage_status(nc.FORBIDDEN_COVERAGE_STATUS)
        with self.assertRaises(AssertionError):
            nc._checked_coverage_status("something_else")
        value = case("real-noncommuting-algebraic-certificate")
        value["expected_coverage_status"] = nc.FORBIDDEN_COVERAGE_STATUS
        with self.assertRaises(nc.CertificateInputError):
            verify_one(value)

    def test_no_search_or_optimization_entry_point_exists(self) -> None:
        forbidden = frozenset(
            {
                "descend", "discover", "iterate", "maximize", "minimize", "optimize",
                "search", "solve", "solver", "step",
            }
        )
        offenders = []
        for name in PRODUCTION_MODULES:
            for node in ast.walk(module_tree(name)):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    tokens = set(node.name.lower().strip("_").split("_"))
                    if tokens & forbidden:
                        offenders.append(f"{name}:{node.name}")
        self.assertEqual([], offenders)

    def test_the_certificate_source_port_only_reads(self) -> None:
        source = FrozenFixtureCertificates(FIXTURE["cases"])
        self.assertIsInstance(source, CertificateSource)
        self.assertIsNone(source.certificate_for("real-noncommuting-certificate-withheld"))
        self.assertIsNotNone(source.certificate_for("real-noncommuting-algebraic-certificate"))
        with self.assertRaises(KeyError):
            source.certificate_for("no-such-case")


class CertificateProvenanceTests(unittest.TestCase):
    """ADR-0035 boundary 2: provenance is recorded and the certificate is human."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_certificate_without_a_recorded_principal_fails_closed(self) -> None:
        value = case("real-noncommuting-algebraic-certificate")
        del value["certificate"]["deriving_principal_id"]
        with self.assertRaises(nc.CertificateProvenanceError):
            verify_one(value)

    def test_an_empty_deriving_principal_fails_closed(self) -> None:
        for empty in ("", None, 0):
            with self.subTest(empty=empty):
                value = case("real-noncommuting-algebraic-certificate")
                value["certificate"]["deriving_principal_id"] = empty
                with self.assertRaises(nc.CertificateProvenanceError):
                    verify_one(value)

    def test_an_unknown_deriving_principal_fails_closed_at_the_boundary(self) -> None:
        value = case("real-noncommuting-algebraic-certificate")
        value["certificate"]["deriving_principal_id"] = "principal.not.recorded"
        with Phase5Workspace(self.root) as workspace:
            with self.assertRaises(Phase5ValidationError):
                Phase5Service(workspace).run_noncommuting_fixture(
                    fixture_with(value, case("real-noncommuting-irreducible-cubic-boundary")),
                    recorded_at=T0,
                )

    def test_a_nonhuman_deriving_principal_fails_closed(self) -> None:
        from math_research.phase4a.records import ActorKind, Authority

        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            service.run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            service.ensure_principal(
                principal_id="principal.phase5.deterministic",
                actor_kind=ActorKind.SYSTEM, authority=Authority.DETERMINISTIC_POLICY,
                recorded_at=T0,
            )
            with self.assertRaises(PermissionError):
                service.admit_supplied_certificate(
                    run_id="run.any", case_id="any",
                    certificate_provenance={
                        "deriving_principal_id": "principal.phase5.deterministic",
                        "derivation": "hand_derived_by_inspection",
                        "system_generated": False,
                    },
                    certificate_hash=canonical_hash({}),
                    admitting_principal_id="principal.phase5.owner",
                    capability_id="capability.phase5.steer", recorded_at=T1,
                )

    def test_a_system_generated_certificate_is_refused(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            service.run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            with self.assertRaises(Phase5ValidationError):
                service.admit_supplied_certificate(
                    run_id="run.any", case_id="any",
                    certificate_provenance={
                        "deriving_principal_id": "principal.phase5.owner",
                        "derivation": "hand_derived_by_inspection",
                        "system_generated": True,
                    },
                    certificate_hash=canonical_hash({}),
                    admitting_principal_id="principal.phase5.owner",
                    capability_id="capability.phase5.steer", recorded_at=T1,
                )

    def test_admission_requires_the_human_steering_capability(self) -> None:
        from math_research.phase4a.records import ActorKind, Authority

        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            service.run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            service.ensure_principal(
                principal_id="principal.phase5.deterministic",
                actor_kind=ActorKind.SYSTEM, authority=Authority.DETERMINISTIC_POLICY,
                recorded_at=T0,
            )
            service.ensure_capability(
                capability_id="capability.phase5.system-steer",
                principal_id="principal.phase5.deterministic",
                operation="steer_research", recorded_at=T0,
            )
            with self.assertRaises(PermissionError):
                service.admit_supplied_certificate(
                    run_id="run.any", case_id="any",
                    certificate_provenance={
                        "deriving_principal_id": "principal.phase5.owner",
                        "derivation": "hand_derived_by_inspection",
                        "system_generated": False,
                    },
                    certificate_hash=canonical_hash({}),
                    admitting_principal_id="principal.phase5.deterministic",
                    capability_id="capability.phase5.system-steer", recorded_at=T1,
                )

    def test_admission_records_the_deriving_principal_and_the_duty_gap(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            result = service.run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            admissions = workspace.records("noncommuting_certificate_admission")
            self.assertEqual(7, len(admissions))
            self.assertEqual(7, len(result["certificate_admission_ids"]))
            for record in admissions:
                payload = record["payload"]
                self.assertEqual("principal.phase5.owner", payload["deriving_principal_id"])
                self.assertEqual("authorized_human_steering", payload["admitted_through"])
                self.assertEqual("steer_research", payload["required_capability"])
                self.assertEqual("human_supplied", payload["certificate_origin"])
                self.assertFalse(payload["system_generated"])
                self.assertFalse(payload["discovery_performed"])
                duty = payload["separation_of_duty"]
                self.assertTrue(duty["derivation_and_admission_principals_identical"])
                self.assertFalse(duty["enforced"])
                self.assertFalse(duty["second_principal_required"])
                self.assertEqual(
                    "mathematical_zero_gap_certificate_is_self_verifying",
                    duty["containment"],
                )
                self.assertIn("load-bearing", duty["recorded_gap"])

    def test_sealed_nonhuman_steering_still_fails_closed(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            diagonal = service.run_quantum_fixture(DIAGONAL_FIXTURE, recorded_at=T0)
            with self.assertRaises(PermissionError):
                service.steer(
                    event_id=diagonal["material_result_event_ids"][0], action="acknowledge",
                    principal_id="principal.phase5.deterministic",
                    capability_id="capability.phase5.surface",
                    idempotency_key="bad-steer", recorded_at=T1,
                )


class CoverageStatusTests(unittest.TestCase):
    """ADR-0035 boundary 3: coverage status is mandatory and honest."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.report = nc.verify_fixture(FIXTURE)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _refuted_case(self) -> dict:
        value = case("commuting-exact-control")
        value["case_id"] = "synthetic-refuted-certificate"
        value["certificate"]["primal_povm"] = [[[1, 0], [0, 0]], [[0, 0], [0, 0]]]
        value["expected_coverage_status"] = nc.COVERAGE_REFUTED
        value["expected_primal_dual_gap"] = "1/2"
        return value

    def test_every_producible_coverage_status_carries_the_field(self) -> None:
        """Exhaustive over the vocabulary, so no reachable branch omits it."""
        produced = {}
        for value in (
            case("real-noncommuting-algebraic-certificate"),
            case("real-noncommuting-rational-candidate"),
            case("real-noncommuting-irreducible-cubic-boundary"),
            case("real-noncommuting-certificate-withheld"),
            self._refuted_case(),
        ):
            result = verify_one(value)
            self.assertIn("coverage_status", result)
            self.assertIn(result["coverage_status"], nc.COVERAGE_STATUSES)
            self.assertEqual(result["coverage_status"], result["coverage"]["status"])
            produced[result["coverage_status"]] = result["case_id"]
        self.assertEqual(sorted(nc.COVERAGE_STATUSES), sorted(produced))

    def test_a_refuted_certificate_retains_its_refutation_reasons(self) -> None:
        result = verify_one(self._refuted_case())
        self.assertEqual(nc.COVERAGE_REFUTED, result["coverage_status"])
        self.assertFalse(result["primal_feasible"])
        self.assertEqual(
            ["POVM effects do not sum to the identity"], result["refutation_reasons"]
        )
        self.assertEqual("candidate_check_only", result["proposal_status"])
        self.assertEqual("none_unresolved", result["mathematical_warrant"])

    def test_the_report_and_run_result_carry_coverage(self) -> None:
        self.assertEqual(
            {
                "certificate_supplied_and_verified": 4,
                "certificate_supplied_gap_not_closed": 2,
                "certificate_supplied_outside_represented_field": 1,
                "certificate_supplied_and_refuted": 0,
                "unresolved_no_certificate_supplied": 1,
            },
            self.report["coverage_status_counts"],
        )
        self.assertFalse(self.report["general_noncommuting_convergence_answered"])
        self.assertFalse(self.report["discovery_performed"])
        self.assertEqual(
            nc.FORBIDDEN_COVERAGE_STATUS, self.report["unproducible_coverage_status"]
        )
        with Phase5Workspace(self.root) as workspace:
            result = Phase5Service(workspace).run_noncommuting_fixture(FIXTURE, recorded_at=T0)
        self.assertEqual(
            self.report["coverage_status_counts"], result["coverage_status_counts"]
        )
        self.assertEqual(8, len(result["case_coverage_status"]))
        self.assertFalse(result["general_noncommuting_convergence_answered"])

    def test_every_export_record_carries_coverage(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            Phase5Service(workspace).run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            export = workspace.export_value()
        findings = [
            item for item in export["records"] if item["record_type"] == "noncommuting_finding"
        ]
        self.assertEqual(8, len(findings))
        for record in findings:
            self.assertIn(record["payload"]["coverage_status"], nc.COVERAGE_STATUSES)
            self.assertIn(record["payload"]["result"]["coverage_status"], nc.COVERAGE_STATUSES)
        summary = [
            item
            for item in export["records"]
            if item["record_type"] == "noncommuting_run_summary"
        ]
        self.assertEqual(1, len(summary))
        self.assertIn("coverage_status_counts", summary[0]["payload"])

    def test_the_rendered_report_puts_coverage_before_gap_for_every_case(self) -> None:
        text = nc.render_noncommuting_report(self.report)
        lines = text.split("\n")
        self.assertIn("## Coverage (read this before any gap)", lines)
        self.assertLess(
            lines.index("## Coverage (read this before any gap)"),
            min(index for index, line in enumerate(lines) if "gap:" in line.lower()),
        )
        for case_id in MEASURED:
            with self.subTest(case_id=case_id):
                start = lines.index(f"### `{case_id}`")
                block = lines[start : start + 12]
                coverage = next(i for i, line in enumerate(block) if "Coverage status:" in line)
                gap = next(i for i, line in enumerate(block) if "primal/dual gap:" in line)
                self.assertLess(coverage, gap)
                self.assertIn(MEASURED[case_id][0], block[coverage])

    def test_no_rendered_line_claims_general_noncommuting_capability(self) -> None:
        text = nc.render_noncommuting_report(self.report)
        lowered = text.lower()
        for phrase in nc.FORBIDDEN_SUMMARY_PHRASES:
            self.assertNotIn(phrase, lowered)
        self.assertIn("NOT answered by this slice", text)
        self.assertIn("verifies supplied certificates; performs no discovery", text)

    def test_the_capability_claim_guard_is_not_vacuous(self) -> None:
        for phrase in nc.FORBIDDEN_SUMMARY_PHRASES:
            with self.subTest(phrase=phrase):
                with self.assertRaises(AssertionError):
                    nc.assert_no_capability_claim(f"- Summary: this slice {phrase} now.")

    def test_a_fixture_without_the_boundary_case_is_rejected(self) -> None:
        with self.assertRaises(nc.CertificateInputError):
            nc.verify_fixture(fixture_with(case("real-noncommuting-algebraic-certificate")))

    def test_the_boundary_case_cannot_be_relabelled(self) -> None:
        for field, replacement in (
            ("expected_coverage_status", nc.COVERAGE_CERTIFICATE_VERIFIED),
            ("expected_optimum_representable", True),
            ("expected_primal_dual_gap", "0"),
        ):
            with self.subTest(field=field):
                value = case("real-noncommuting-irreducible-cubic-boundary")
                value[field] = replacement
                with self.assertRaises(nc.CertificateInputError):
                    verify_one(value)


class FieldBoundaryTests(unittest.TestCase):
    """ADR-0035 boundary 4: one measured squarefree radicand per case."""

    def test_the_radicand_is_measured_from_the_case_values(self) -> None:
        result = verify_one(case("real-noncommuting-algebraic-certificate-radicand-five"))
        self.assertEqual(5, result["field"]["radicand"])
        self.assertEqual("Q(sqrt(5))(i)", result["field"]["notation"])
        self.assertEqual(4, result["field"]["degree_over_rationals"])
        self.assertEqual(2, result["field"]["real_subfield_degree_over_rationals"])
        self.assertEqual(
            5, alg.measure_radicand([alg.algebraic(0, 1, 5), alg.algebraic(1)])
        )

    def test_two_distinct_surds_are_a_typed_rejection(self) -> None:
        with self.assertRaises(alg.MixedRadicandError):
            alg.algebraic(0, 1, 2) + alg.algebraic(0, 1, 3)
        with self.assertRaises(alg.MixedRadicandError):
            alg.measure_radicand([alg.algebraic(0, 1, 2), alg.algebraic(0, 1, 3)])
        with self.assertRaises(alg.MixedRadicandError):
            alg.join_radicands(2, 3)
        value = case("real-noncommuting-algebraic-certificate")
        value["certificate"]["dual_gamma"][0][1] = {
            "rational": "1/8", "surd": "1/8", "radicand": 3,
        }
        with self.assertRaises(alg.MixedRadicandError):
            verify_one(value)

    def test_a_cubic_extension_is_a_typed_rejection(self) -> None:
        self.assertEqual(
            "cubic_or_higher_irreducible_extension",
            alg.HigherDegreeExtensionError.reason_code,
        )
        with self.assertRaises(alg.HigherDegreeExtensionError):
            alg.quadratic(1, 1, 2).exact_sqrt()
        probe = verify_one(case("real-noncommuting-irreducible-cubic-boundary"))[
            "spectral_field_probe"
        ]
        self.assertEqual(
            alg.HigherDegreeExtensionError.reason_code, probe["rejection_reason_code"]
        )

    def test_a_declared_transcendental_value_is_a_typed_rejection(self) -> None:
        with self.assertRaises(alg.TranscendentalValueError):
            alg.parse_quadratic({"transcendental": "pi"})
        value = case("real-noncommuting-algebraic-certificate")
        value["certificate"]["dual_gamma"][0][1] = {"transcendental": "pi"}
        with self.assertRaises(alg.TranscendentalValueError):
            verify_one(value)

    def test_a_float_anywhere_on_the_certificate_path_is_a_typed_rejection(self) -> None:
        with self.assertRaises(alg.InexactValueError):
            alg.quadratic(0.5)
        with self.assertRaises(alg.InexactValueError):
            alg.reject_inexact({"a": [1, 2.5]})
        with self.assertRaises(alg.InexactValueError):
            alg.quadratic("1.5")
        for mutation in ({"json": 0.25}, 0.25, [0.25]):
            with self.subTest(mutation=mutation):
                value = case("real-noncommuting-algebraic-certificate")
                value["certificate"]["dual_gamma"][0][1] = mutation
                with self.assertRaises(alg.InexactValueError):
                    verify_one(value)

    def test_the_json_decoder_refuses_floats_and_duplicate_keys(self) -> None:
        with self.assertRaises(Phase5ValidationError):
            decode_json(b'{"schema_version": 1, "schema_version": 2}')
        with self.assertRaises(Phase5ValidationError):
            decode_json(b'{"a": NaN}')
        with self.assertRaises(alg.InexactValueError):
            nc.verify_fixture(json.loads('{"schema_version": "x", "cases": 0.5}'))
        with self.assertRaises(alg.AlgebraicFieldError):
            alg.parse_quadratic("1/10000000000000")

    def test_no_tolerance_admits_a_gap(self) -> None:
        """A gap of one billionth is a gap, not a zero."""
        value = case("commuting-exact-control")
        value["case_id"] = "synthetic-tiny-gap"
        value["certificate"]["dual_gamma"] = [
            ["1000000001/2000000000", 0], [0, "1000000001/2000000000"],
        ]
        value["expected_coverage_status"] = nc.COVERAGE_GAP_NOT_CLOSED
        value["expected_primal_dual_gap"] = "1/1000000000"
        result = verify_one(value)
        self.assertEqual(nc.COVERAGE_GAP_NOT_CLOSED, result["coverage_status"])
        self.assertEqual("1/1000000000", result["primal_dual_gap"])
        self.assertTrue(result["primal_feasible"])
        self.assertTrue(result["dual_feasible"])
        self.assertFalse(result["complementarity_exact"])

    def test_sign_has_no_epsilon(self) -> None:
        """The two ADR-0033 epsilon mutations stay dead."""
        self.assertEqual(1, alg.quadratic(Fraction(1, 10**9)).sign())
        self.assertEqual(-1, alg.quadratic(Fraction(-1, 10**9)).sign())
        self.assertEqual(1, alg.quadratic(0, Fraction(1, 10**9), 2).sign())
        self.assertEqual(-1, alg.quadratic(0, Fraction(-1, 10**9), 2).sign())
        near = alg.quadratic(Fraction(-1414213, 10**6), Fraction(1, 1), 2)
        self.assertEqual(1, near.sign())
        self.assertEqual(
            -1, alg.quadratic(Fraction(-1414214, 10**6), Fraction(1, 1), 2).sign()
        )

    def test_canonical_form_is_total_and_one_value_has_one_hash(self) -> None:
        self.assertEqual(alg.quadratic(0, 1, 2), alg.quadratic(0, Fraction(1, 2), 8))
        self.assertEqual(alg.quadratic(0, 1, 2), alg.quadratic(0, Fraction(1, 6), 72))
        self.assertEqual(
            alg.algebraic(0, 1, 2).value_hash(), alg.algebraic(0, Fraction(1, 2), 8).value_hash()
        )
        self.assertEqual(alg.quadratic(3), alg.quadratic(1, 2, 1))
        self.assertEqual(1, alg.quadratic(1, 2, 1).radicand)

    def test_malformed_surd_objects_are_rejected(self) -> None:
        for bad in (
            {"rational": "1", "surd": "1"},
            {"rational": "1", "surd": "1", "radicand": "2"},
            {"rational": "1", "surd": "1", "radicand": -2},
            {"rational": "1", "surd": "1", "radicand": 4, "extra": 1},
            {"rational": {"re": "1", "im": "1"}, "surd": "1", "radicand": 2},
            {"rational": "1", "surd": "1", "radicand": True},
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(alg.AlgebraicFieldError):
                    alg.parse_quadratic(bad)

    def test_psd_is_decided_by_exact_minors(self) -> None:
        self.assertTrue(is_psd(parse_matrix([["1/2", 0], [0, 0]])))
        self.assertFalse(is_psd(parse_matrix([["1/2", 0], [0, "-1/1000000000"]])))

    def test_an_invalid_ensemble_is_a_reject_not_a_finding(self) -> None:
        for mutation in (
            [[["1/2", 0], [0, 0]], [[0, 0], [0, "1/3"]]],
            [[["1/2", 0], [0, 0]], [["-1/2", 0], [0, 1]]],
        ):
            with self.subTest(mutation=mutation):
                value = case("commuting-exact-control")
                value["weighted_states"] = mutation
                with self.assertRaises(nc.CertificateInputError):
                    verify_one(value)


class StructuralExactnessTests(unittest.TestCase):
    """No float, no tolerance, no clock, no randomness on the exact path."""

    FORBIDDEN_IMPORTS = frozenset(
        {
            "cmath", "datetime", "decimal", "math", "numpy", "os", "random",
            "scipy", "secrets", "statistics", "time",
        }
    )
    FORBIDDEN_NAME_FRAGMENTS = (
        "approx", "atol", "epsilon", "isclose", "rtol", "tolerance",
    )
    FORBIDDEN_CALLS = frozenset({"complex", "eval", "exec", "float", "hash", "id"})

    def test_no_float_literal_appears_in_the_exact_modules(self) -> None:
        offenders = []
        for name in PRODUCTION_MODULES:
            for node in ast.walk(module_tree(name)):
                if isinstance(node, ast.Constant) and isinstance(node.value, float):
                    offenders.append(f"{name}:{node.lineno}")
        self.assertEqual([], offenders)

    def test_no_inexact_or_nondeterministic_module_is_imported(self) -> None:
        offenders = []
        for name in PRODUCTION_MODULES:
            for node in ast.walk(module_tree(name)):
                if isinstance(node, ast.Import):
                    offenders.extend(
                        f"{name}:{alias.name}"
                        for alias in node.names
                        if alias.name.split(".")[0] in self.FORBIDDEN_IMPORTS
                    )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in self.FORBIDDEN_IMPORTS:
                        offenders.append(f"{name}:{node.module}")
        self.assertEqual([], offenders)

    def test_no_tolerance_identifier_exists(self) -> None:
        offenders = []
        for name in PRODUCTION_MODULES:
            for node in ast.walk(module_tree(name)):
                identifier = None
                if isinstance(node, ast.Name):
                    identifier = node.id
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    identifier = node.name
                elif isinstance(node, ast.arg):
                    identifier = node.arg
                elif isinstance(node, ast.Attribute):
                    identifier = node.attr
                if identifier and any(
                    fragment in identifier.lower() for fragment in self.FORBIDDEN_NAME_FRAGMENTS
                ):
                    offenders.append(f"{name}:{identifier}")
        self.assertEqual([], offenders)

    def test_no_inexact_builtin_is_called(self) -> None:
        offenders = []
        for name in PRODUCTION_MODULES:
            for node in ast.walk(module_tree(name)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in self.FORBIDDEN_CALLS:
                        offenders.append(f"{name}:{node.func.id}")
        self.assertEqual([], offenders)

    def test_every_result_records_the_absence_of_a_tolerance(self) -> None:
        report = nc.verify_fixture(FIXTURE)
        self.assertIsNone(report["tolerance"])
        for result in report["results"]:
            self.assertIsNone(result["tolerance"])
            self.assertIsNone(result["field"]["tolerance"])
            self.assertEqual("exact_algebraic_quadratic_complex", result["arithmetic"])


class SearchTierTests(unittest.TestCase):
    """ADR-0035 boundary 5: tiers 2--4 stay disabled."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_tiers_two_to_four_remain_disabled_everywhere(self) -> None:
        disabled = "disabled_no_measured_cost_adjusted_gain"
        report = nc.verify_fixture(FIXTURE)
        self.assertFalse(report["search_tiers_enabled"])
        for result in report["results"]:
            for tier in ("tier_2", "tier_3", "tier_4"):
                self.assertEqual(disabled, result["search_tiers"][tier])
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            noncommuting = service.run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            diagonal = service.run_quantum_fixture(DIAGONAL_FIXTURE, recorded_at=T0)
        for tier in ("tier_2", "tier_3", "tier_4"):
            self.assertEqual(disabled, noncommuting["search_tiers"][tier])
            self.assertEqual(disabled, diagonal["search_tiers"][tier])


class SealedCompatibilityTests(unittest.TestCase):
    """The sealed diagonal slice and Phase 6's contract are untouched."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_diagonal_case_and_run_case_signatures_are_unchanged(self) -> None:
        self.assertEqual(
            [
                "case_id", "statement_variant", "weights", "initial_povm", "iterations",
                "expected_classification",
            ],
            list(inspect.signature(DiagonalCase).parameters),
        )
        self.assertEqual(["case"], list(inspect.signature(run_case).parameters))
        result = run_case(DiagonalCase.from_value(DIAGONAL_FIXTURE["cases"][0]))
        self.assertEqual("adaivy.quantum-diagonal-result.v1", result["schema_version"])
        self.assertEqual("1/3", result["primal_dual_gap"])
        self.assertTrue(result["nonoptimal_fixed_point"])

    def test_the_diagonal_run_is_unaffected_by_a_noncommuting_run(self) -> None:
        with tempfile.TemporaryDirectory() as alone:
            with Phase5Workspace(Path(alone)) as workspace:
                baseline = Phase5Service(workspace).run_quantum_fixture(
                    DIAGONAL_FIXTURE, recorded_at=T0
                )
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            service.run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            mixed = service.run_quantum_fixture(DIAGONAL_FIXTURE, recorded_at=T0)
            workspace.verify_integrity()
        # Record content hashes embed the append sequence, so only the
        # sequence-independent identities are comparable across two histories.
        self.assertEqual(baseline["fixture_hash"], mixed["fixture_hash"])
        self.assertEqual(baseline["run_id"], mixed["run_id"])
        self.assertEqual(baseline["finding_ids"], mixed["finding_ids"])
        # The material-result event identity binds the evidence RECORD hash,
        # which embeds the append sequence, so it moves when the workspace has a
        # different history. That is sealed pre-existing behaviour, so only the
        # count is compared here.
        self.assertEqual(1, len(baseline["material_result_event_ids"]))
        self.assertEqual(1, len(mixed["material_result_event_ids"]))
        self.assertEqual(baseline["branch_count"], mixed["branch_count"])
        self.assertEqual(baseline["dead_end_count"], mixed["dead_end_count"])

    def test_the_hash_bound_diagonal_fixture_is_untouched(self) -> None:
        protocol = json.loads(
            (ROOT / "fixtures/phase6/confirmatory-protocol-v1.json").read_text("utf-8")
        )
        self.assertEqual(protocol["phase5_fixture_hash"], canonical_hash(DIAGONAL_FIXTURE))

    def test_the_noncommuting_record_envelope_is_the_sealed_version(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            Phase5Service(workspace).run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            for record in workspace.records():
                self.assertEqual("adaivy.phase5-record.v1", record["schema_version"])
            self.assertEqual(
                "adaivy.phase5-workspace.v1", workspace.export_value()["schema_version"]
            )


class ReproducibilityTests(unittest.TestCase):
    """Byte reproducibility across two runs and a restart."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_two_runs_a_restart_and_a_replay_are_byte_identical(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            first = service.run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            second = service.run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            self.assertEqual(first, second)
            exported = workspace.export_bytes()
            self.assertEqual(
                workspace.save_verified_export(exported)["content_hash"],
                json.loads(exported)["content_hash"],
            )
        with Phase5Workspace(self.root) as restarted:
            self.assertEqual(exported, restarted.export_bytes())
            third = Phase5Service(restarted).run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            self.assertEqual(first, third)
            self.assertEqual(exported, restarted.export_bytes())
            restarted.verify_integrity()

    def test_the_report_and_render_are_deterministic(self) -> None:
        first, second = nc.verify_fixture(FIXTURE), nc.verify_fixture(FIXTURE)
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        self.assertEqual(PINNED_REPORT_HASH, first["content_hash"])
        self.assertEqual(
            nc.render_noncommuting_report(first), nc.render_noncommuting_report(second)
        )

    def test_a_rewritten_noncommuting_record_is_refused(self) -> None:
        with Phase5Workspace(self.root) as workspace:
            service = Phase5Service(workspace)
            service.run_noncommuting_fixture(FIXTURE, recorded_at=T0)
            finding = next(
                item
                for item in workspace.records("noncommuting_finding")
                if item["payload"]["coverage_status"] != nc.COVERAGE_CERTIFICATE_VERIFIED
            )
            payload = copy.deepcopy(finding["payload"])
            payload["coverage_status"] = nc.COVERAGE_CERTIFICATE_VERIFIED
            with self.assertRaises(Phase5ValidationError):
                workspace.append(
                    record_type="noncommuting_finding", subject_id=finding["subject_id"],
                    record_id=finding["record_id"], payload=payload, recorded_at=T0,
                )


if __name__ == "__main__":
    unittest.main()
