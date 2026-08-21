"""Acceptance suite for the WP5 Phase 6 generality control suite (ADR-0034).

Under ADR-0026 this file is the executable record of the slice's thresholds.
Two of them are release gates and both are asserted here: every control passes,
and every control's falsifiability probe flips. The second gate exists because
the suite it replaces was a literal table whose `passed` field was derived from
its own hard-coded `admitted is False`, so `controls_passed == 5` was a constant.
A control that cannot be made to fail is tested here as a suite failure.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from math_research.phase5.serialization import canonical_bytes, canonical_hash
from math_research.phase5.service import Phase5Service
from math_research.phase6 import generality
from math_research.phase6.errors import GeneralitySuiteError
from math_research.phase6.heldout import HeldOutView
from math_research.phase6.service import (
    ACCESS_RECORD_TYPE,
    SUITE_RECORD_TYPE,
    VIOLATION_RECORD_TYPE,
    Phase6Service,
    Phase6ValidationError,
)
from math_research.phase6.workspace import Phase6Workspace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PHASE5_FIXTURE = json.loads((ROOT / "fixtures/phase5/quantum-diagonal-v1.json").read_text("utf-8"))
PROTOCOL = json.loads((ROOT / "fixtures/phase6/confirmatory-protocol-v1.json").read_text("utf-8"))
SUITE = generality.load_suite()
RESULT = generality.run_suite(SUITE)
T0 = "2026-08-20T12:00:00Z"
T1 = "2026-08-20T14:00:00Z"

SECTION_18_4_CATEGORIES = {
    "known_theorems",
    "false_conjectures",
    "missing_assumption_traps",
    "semantic_mistranslations",
    "inapplicable_citations",
    "cross_representation_problems",
}


def _control(control_id: str) -> dict:
    return next(item for item in RESULT["controls"] if item["control_id"] == control_id)


class ExecutedControlTests(unittest.TestCase):
    """Every control executes. None of them is a declaration."""

    def test_every_control_passes_its_executed_expectation(self) -> None:
        self.assertEqual(RESULT["controls_total"], len(SUITE["controls"]))
        for control in RESULT["controls"]:
            with self.subTest(control=control["control_id"]):
                self.assertEqual([], control["mismatches"])
                self.assertTrue(control["passed"])
                # The verdict came from an engine run, not from the manifest.
                for key, value in control["expected"].items():
                    self.assertIn(key, control["observed"])
                    self.assertEqual(value, control["observed"][key])
        self.assertEqual(RESULT["controls_total"], RESULT["controls_passed"])
        self.assertEqual([], RESULT["failed_control_ids"])

    def test_every_probe_flips(self) -> None:
        for control in RESULT["controls"]:
            probe = control["probe"]
            with self.subTest(probe=probe["probe_id"]):
                self.assertTrue(probe["probe_expected_matched"], probe["mismatches"])
                self.assertTrue(probe["control_expectation_broken"])
                self.assertNotEqual([], probe["broken_keys"])
                self.assertTrue(probe["flipped"])
        self.assertEqual(RESULT["probes_total"], RESULT["probes_flipped"])
        self.assertEqual([], RESULT["unflipped_probe_ids"])
        self.assertTrue(RESULT["suite_passed"])

    def test_probe_is_a_single_named_field_mutation_of_the_control_fixture(self) -> None:
        for control in SUITE["controls"]:
            probe = control["probe"]
            with self.subTest(control=control["control_id"]):
                self.assertIn(probe["field"], control["parameters"])
                self.assertNotEqual(control["parameters"][probe["field"]], probe["value"])
                mutated = dict(control["parameters"])
                mutated[probe["field"]] = probe["value"]
                differing = [
                    key for key in sorted(mutated)
                    if mutated[key] != control["parameters"][key]
                ]
                self.assertEqual([probe["field"]], differing)
                self.assertTrue(probe["forbidden_outcome"])

    def test_positive_control_proves_a_known_theorem(self) -> None:
        """GC-01. Without this, a system that rejects everything scores full marks."""

        control = _control("GC-01")
        self.assertEqual("positive", control["polarity"])
        self.assertEqual("known_theorems", control["category"])
        self.assertEqual("proved", control["observed"]["target_logical_status"])
        self.assertEqual(
            "approved_equivalent", control["observed"]["target_semantic_alignment_status"]
        )
        self.assertEqual([], control["observed"]["target_blockers"])
        self.assertTrue(control["observed"]["dossier_valid"])
        self.assertTrue(RESULT["positive_control_admitted"])
        self.assertGreaterEqual(RESULT["positive_controls_total"], 1)
        self.assertEqual(
            RESULT["positive_controls_total"], RESULT["positive_controls_passed"]
        )
        # The probe degrades exactly one field and the theorem stops being proved.
        self.assertEqual("unknown", control["probe"]["observed"]["target_logical_status"])

    def test_suite_covers_every_section_18_4_category(self) -> None:
        self.assertLessEqual(SECTION_18_4_CATEGORIES, set(RESULT["categories_covered"]))
        self.assertLessEqual(
            {"unsupported_consensus", "finite_experiment_overreach", "premise_smuggling",
             "plugin_core_contract", "evaluation_leakage"},
            set(RESULT["categories_covered"]),
        )

    def test_missing_assumption_keeps_the_two_axes_separate(self) -> None:
        """GC-03. The target must not resolve while the translated claim stays proved."""

        observed = _control("GC-03")["observed"]
        self.assertEqual("unknown", observed["target_logical_status"])
        self.assertIn("semantic_target_not_resolved", observed["target_blockers"])
        self.assertEqual("proved", observed["target_projection_logical_status"])

    def test_exact_engine_reports_a_nonoptimal_fixed_point(self) -> None:
        """GC-02B. The false conjecture is universal JRF convergence."""

        observed = _control("GC-02B")["observed"]
        self.assertTrue(observed["fixed_point"])
        self.assertTrue(observed["nonoptimal_fixed_point"])
        self.assertNotEqual("0", observed["primal_dual_gap"])
        self.assertFalse(observed["graph_admitted"])

    def test_second_domain_uses_only_core_entities(self) -> None:
        """GC-09A. Section 18.4: no core entity semantics change for a plugin."""

        observed = _control("GC-09A")["observed"]
        self.assertEqual([], observed["entity_types_outside_core"])
        self.assertEqual("1.0.0", observed["entity_schema_version"])
        self.assertEqual(list(generality.PROJECTION_AXES), observed["projection_axes"])
        self.assertEqual("proved", observed["target_logical_status"])
        self.assertEqual("supported", _control("GC-09A")["probe"]["observed"]["target_logical_status"])

    def test_suite_records_project_authored_provenance_and_its_limitations(self) -> None:
        self.assertEqual("project_authored", RESULT["control_corpus_provenance"])
        self.assertTrue(RESULT["limitations"])
        joined = " ".join(RESULT["limitations"]).lower()
        self.assertIn("project-authored", joined)
        self.assertIn("not evidence of generality against unseen traps", joined)
        for control in RESULT["controls"]:
            with self.subTest(control=control["control_id"]):
                self.assertTrue(control["limitations"])


class UnfalsifiableControlIsASuiteFailureTests(unittest.TestCase):
    """The gate that forecloses the defect this slice fixes."""

    def _suite_with_dead_probe(self) -> dict:
        suite = deepcopy(SUITE)
        control = next(item for item in suite["controls"] if item["control_id"] == "GC-06A")
        # Mutating the bridge obligation cannot change a verdict that is already
        # decided by an unverified representation map, so this probe cannot flip.
        control["probe"]["field"] = "bridge_obligation_status"
        control["probe"]["value"] = "waived"
        control["probe"]["expected"] = {"target_logical_status": "unknown"}
        return suite

    def test_a_control_whose_probe_cannot_flip_fails_the_suite(self) -> None:
        result = generality.run_suite(self._suite_with_dead_probe())
        self.assertEqual(result["controls_total"], result["controls_passed"])
        self.assertLess(result["probes_flipped"], result["probes_total"])
        self.assertEqual(["GC-06A-P1"], result["unflipped_probe_ids"])
        self.assertFalse(result["suite_passed"])
        probe = next(
            item["probe"] for item in result["controls"] if item["control_id"] == "GC-06A"
        )
        self.assertTrue(probe["probe_expected_matched"])
        self.assertFalse(probe["control_expectation_broken"])

    def test_a_dead_probe_fails_the_confirmatory_release(self) -> None:
        suite = self._suite_with_dead_probe()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "dead-probe-suite.json"
            path.write_bytes(canonical_bytes(suite))
            protocol = dict(PROTOCOL)
            protocol["generality_suite_hash"] = canonical_hash(suite)
            with Phase6Workspace(root / "workspace") as workspace:
                phase5 = Phase5Service(workspace.phase5).run_quantum_fixture(
                    PHASE5_FIXTURE, recorded_at=T0
                )
                service = Phase6Service(workspace, generality_suite_path=path)
                result = service.confirm(
                    protocol=protocol, phase5_fixture=PHASE5_FIXTURE,
                    phase5_run_id=phase5["run_id"], recorded_at=T1,
                )
        self.assertEqual("failed", result["confirmatory_result"]["status"])
        self.assertEqual(result["controls_total"], result["controls_passed"])
        self.assertLess(result["probes_flipped"], result["probes_total"])

    def test_a_suite_without_a_positive_control_is_refused(self) -> None:
        suite = deepcopy(SUITE)
        suite["controls"] = [
            item for item in suite["controls"] if item["polarity"] != "positive"
        ]
        with self.assertRaises(GeneralitySuiteError):
            generality.validate_suite(suite)

    def test_a_suite_omitting_a_section_18_4_category_is_refused(self) -> None:
        suite = deepcopy(SUITE)
        suite["controls"] = [
            item for item in suite["controls"]
            if item["category"] != "inapplicable_citations"
        ]
        with self.assertRaises(GeneralitySuiteError):
            generality.validate_suite(suite)


class SuiteManifestFailsClosedTests(unittest.TestCase):
    def _mutate(self, change) -> dict:
        suite = deepcopy(SUITE)
        change(suite)
        return suite

    def test_unknown_and_missing_fields_are_rejected(self) -> None:
        cases = {
            "unknown suite field": lambda s: s.update({"extra": 1}),
            "missing suite field": lambda s: s.pop("limitations"),
            "unknown schema version": lambda s: s.update({"schema_version": "adaivy.x.v9"}),
            "unknown provenance": lambda s: s.update({"control_corpus_provenance": "external"}),
            "unknown engine": lambda s: s["controls"][0].update({"engine": "does_not_exist"}),
            "unknown category": lambda s: s["controls"][0].update({"category": "vibes"}),
            "unknown polarity": lambda s: s["controls"][0].update({"polarity": "maybe"}),
            "unknown control field": lambda s: s["controls"][0].update({"extra": 1}),
            "unknown probe field": lambda s: s["controls"][0]["probe"].update({"extra": 1}),
            "parameters off signature": lambda s: s["controls"][0]["parameters"].update({"x": 1}),
            "unobservable expectation": lambda s: s["controls"][0]["expected"].update({"x": 1}),
            "unobservable probe expectation": (
                lambda s: s["controls"][0]["probe"]["expected"].update({"x": 1})
            ),
            "probe mutates a foreign field": (
                lambda s: s["controls"][0]["probe"].update({"field": "not_a_parameter"})
            ),
            "probe changes nothing": lambda s: s["controls"][0]["probe"].update(
                {"value": s["controls"][0]["parameters"][s["controls"][0]["probe"]["field"]]}
            ),
            "duplicate control id": lambda s: s["controls"].append(deepcopy(s["controls"][0])),
            "empty expectation": lambda s: s["controls"][0].update({"expected": {}}),
            "no controls": lambda s: s.update({"controls": []}),
            "no limitations": lambda s: s.update({"limitations": []}),
            "unnamed forbidden outcome": (
                lambda s: s["controls"][0]["probe"].update({"forbidden_outcome": ""})
            ),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(GeneralitySuiteError):
                    generality.validate_suite(self._mutate(change))

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "suite.json"
            path.write_bytes(b'{"suite_id": "a", "suite_id": "b"}')
            with self.assertRaises(GeneralitySuiteError):
                generality.load_suite(path)

    def test_malformed_and_oversized_suites_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broken = root / "broken.json"
            broken.write_bytes(b"{not json")
            oversized = root / "oversized.json"
            oversized.write_bytes(b'{"pad": "' + b"x" * generality.MAX_SUITE_BYTES + b'"}')
            not_an_object = root / "list.json"
            not_an_object.write_bytes(b"[]")
            for path in (broken, oversized, not_an_object):
                with self.subTest(path=path.name):
                    with self.assertRaises(GeneralitySuiteError):
                        generality.load_suite(path)

    def test_an_unreadable_suite_is_rejected(self) -> None:
        with self.assertRaises(GeneralitySuiteError):
            generality.load_suite(Path("/nonexistent/generality-suite.json"))


class ProtocolBindsTheSuiteDefinitionTests(unittest.TestCase):
    """The suite definition is inside `protocol_hash`, so it cannot be edited later."""

    def test_protocol_pins_the_current_suite_identity(self) -> None:
        self.assertIn("generality_suite_id", PROTOCOL)
        self.assertIn("generality_suite_hash", PROTOCOL)
        self.assertEqual(SUITE["suite_id"], PROTOCOL["generality_suite_id"])
        self.assertEqual(generality.suite_hash(SUITE), PROTOCOL["generality_suite_hash"])
        self.assertIn("generality_suite_id", generality_protocol_fields())
        self.assertIn("generality_suite_hash", generality_protocol_fields())

    def test_editing_the_suite_after_freezing_fails_closed_and_writes_nothing(self) -> None:
        suite = deepcopy(SUITE)
        suite["controls"][0]["expected"]["target_logical_status"] = "unknown"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "edited-suite.json"
            path.write_bytes(canonical_bytes(suite))
            with Phase6Workspace(root / "workspace") as workspace:
                phase5 = Phase5Service(workspace.phase5).run_quantum_fixture(
                    PHASE5_FIXTURE, recorded_at=T0
                )
                service = Phase6Service(workspace, generality_suite_path=path)
                with self.assertRaisesRegex(Phase6ValidationError, "suite hash differs"):
                    service.confirm(
                        protocol=PROTOCOL, phase5_fixture=PHASE5_FIXTURE,
                        phase5_run_id=phase5["run_id"], recorded_at=T1,
                    )
                self.assertEqual((), workspace.records())

    def test_a_protocol_naming_another_suite_id_fails_closed(self) -> None:
        protocol = dict(PROTOCOL)
        protocol["generality_suite_id"] = "suite.phase6.some-other-suite"
        with tempfile.TemporaryDirectory() as temporary:
            with Phase6Workspace(Path(temporary)) as workspace:
                with self.assertRaisesRegex(Phase6ValidationError, "not the one the protocol froze"):
                    Phase6Service(workspace).freeze_protocol(protocol, recorded_at=T1)
                self.assertEqual((), workspace.records())


def generality_protocol_fields() -> set[str]:
    from math_research.phase6.service import PROTOCOL_FIELDS

    return set(PROTOCOL_FIELDS)


class ValidationOrderingTests(unittest.TestCase):
    """A rejected expansion must leave the append-only log untouched."""

    def _rejected(self, **overrides) -> tuple[int, int]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with Phase6Workspace(root) as workspace:
                phase5 = Phase5Service(workspace.phase5).run_quantum_fixture(
                    PHASE5_FIXTURE, recorded_at=T0
                )
                arguments = {
                    "protocol": PROTOCOL, "phase5_fixture": PHASE5_FIXTURE,
                    "phase5_run_id": phase5["run_id"], "recorded_at": T1,
                }
                arguments.update(overrides)
                with self.assertRaises(Phase6ValidationError):
                    Phase6Service(workspace).confirm(**arguments)
                return len(workspace.records()), len(workspace.records("confirmatory_protocol"))

    def test_fixture_expansion_writes_no_record(self) -> None:
        fixture = json.loads(json.dumps(PHASE5_FIXTURE))
        fixture["cases"].append(dict(fixture["cases"][1], case_id="qd-fs-01-extra-case"))
        self.assertEqual((0, 0), self._rejected(phase5_fixture=fixture))

    def test_capability_expansion_writes_no_record(self) -> None:
        protocol = dict(PROTOCOL)
        protocol["allowed_capabilities"] = sorted(
            list(PROTOCOL["allowed_capabilities"]) + ["read_exploratory_results"]
        )
        self.assertEqual((0, 0), self._rejected(protocol=protocol))

    def test_heldout_scope_expansion_writes_no_record(self) -> None:
        protocol = dict(PROTOCOL)
        protocol["heldout_case_ids"] = [
            "qd-fs-01-orthogonal-2d", "qd-fs-01-scalar-full-support",
        ]
        self.assertEqual((0, 0), self._rejected(protocol=protocol))

    def test_missing_material_trace_writes_no_record(self) -> None:
        self.assertEqual((0, 0), self._rejected(phase5_run_id="missing.run"))

    def test_unresolvable_heldout_case_writes_no_record(self) -> None:
        protocol = dict(PROTOCOL)
        protocol["heldout_case_ids"] = ["qd-fs-01-not-in-this-fixture"]
        self.assertEqual((0, 0), self._rejected(protocol=protocol))


class HeldOutAccessLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _confirm(self, workspace: Phase6Workspace, protocol=None) -> dict:
        phase5 = Phase5Service(workspace.phase5).run_quantum_fixture(
            PHASE5_FIXTURE, recorded_at=T0
        )
        return Phase6Service(workspace).confirm(
            protocol=PROTOCOL if protocol is None else protocol,
            phase5_fixture=PHASE5_FIXTURE, phase5_run_id=phase5["run_id"], recorded_at=T1,
        )

    def test_access_count_is_a_read_of_durable_records(self) -> None:
        with Phase6Workspace(self.root) as workspace:
            result = self._confirm(workspace)
            accesses = workspace.records(ACCESS_RECORD_TYPE)
            self.assertEqual(1, len(accesses))
            self.assertEqual(len(accesses), result["heldout_accesses"])
            self.assertEqual(accesses[0]["record_id"], result["heldout_access_record_id"])
            payload = accesses[0]["payload"]
            self.assertEqual("qd-fs-01-orthogonal-2d", payload["case_id"])
            self.assertEqual(PROTOCOL["protocol_id"], payload["protocol_id"])
            run = workspace.records("confirmatory_run")[0]["payload"]
            manifest = run["access_manifest"]
            self.assertEqual([accesses[0]["record_id"]], manifest["access_record_ids"])
            self.assertEqual(1, manifest["access_count"])
            self.assertEqual(0, manifest["adaptations_after_access"])
            self.assertEqual([], manifest["adaptation_protocol_ids"])
            self.assertEqual(["qd-fs-01-orthogonal-2d"], manifest["heldout_case_ids_exposed"])
            self.assertEqual(1, len(workspace.records(SUITE_RECORD_TYPE)))

    def test_a_second_protocol_on_the_same_heldout_case_is_refused(self) -> None:
        with Phase6Workspace(self.root) as workspace:
            self._confirm(workspace)
            before = len(workspace.records())
            second = dict(PROTOCOL)
            second["protocol_id"] = "protocol.qd-fs-01.confirmatory-v2"
            second["version"] = 2
            second["frozen_at"] = "2026-08-20T13:30:00Z"
            phase5_run_id = workspace.phase5.records("run")[0]["subject_id"]
            with self.assertRaisesRegex(Phase6ValidationError, "already accessed"):
                Phase6Service(workspace).confirm(
                    protocol=second, phase5_fixture=PHASE5_FIXTURE,
                    phase5_run_id=phase5_run_id, recorded_at=T1,
                )
            self.assertEqual(before, len(workspace.records()))
            self.assertEqual(1, len(workspace.records(ACCESS_RECORD_TYPE)))
            self.assertEqual(1, len(workspace.records("confirmatory_protocol")))

    def test_repeated_identical_confirmation_records_one_access(self) -> None:
        with Phase6Workspace(self.root) as workspace:
            first = self._confirm(workspace)
        with Phase6Workspace(self.root) as restarted:
            run_id = restarted.phase5.records("run")[0]["subject_id"]
            second = Phase6Service(restarted).confirm(
                protocol=PROTOCOL, phase5_fixture=PHASE5_FIXTURE,
                phase5_run_id=run_id, recorded_at=T1,
            )
            self.assertEqual(first, second)
            self.assertEqual(1, len(restarted.records(ACCESS_RECORD_TYPE)))

    def test_a_non_frozen_case_is_refused_and_the_violation_is_durable(self) -> None:
        with Phase6Workspace(self.root) as workspace:
            service = Phase6Service(workspace)
            view = HeldOutView(
                benchmark_id="QD-FS-01", cases=PHASE5_FIXTURE["cases"],
                frozen_case_ids=("qd-fs-01-orthogonal-2d",),
            )
            with self.assertRaises(Phase6ValidationError):
                service.resolve_heldout_case(
                    view, "qd-fs-01-scalar-full-support", recorded_at=T1
                )
            violations = workspace.records(VIOLATION_RECORD_TYPE)
            self.assertEqual(1, len(violations))
            payload = violations[0]["payload"]
            self.assertEqual("heldout_access_violation", payload["kind"])
            self.assertEqual("qd-fs-01-scalar-full-support", payload["requested_case_id"])
            self.assertEqual(["qd-fs-01-orthogonal-2d"], payload["visible_case_ids"])
            self.assertEqual("case_outside_frozen_heldout_scope", payload["reason"])

    def test_the_view_drops_every_non_frozen_case(self) -> None:
        view = HeldOutView(
            benchmark_id="QD-FS-01", cases=PHASE5_FIXTURE["cases"],
            frozen_case_ids=("qd-fs-01-orthogonal-2d",),
        )
        self.assertEqual(("qd-fs-01-orthogonal-2d",), view.visible_case_ids)
        self.assertEqual(
            "qd-fs-01-orthogonal-2d", view.case("qd-fs-01-orthogonal-2d")["case_id"]
        )
        for case in PHASE5_FIXTURE["cases"]:
            if case["case_id"] != "qd-fs-01-orthogonal-2d":
                with self.assertRaises(Phase6ValidationError):
                    view.case(case["case_id"])
        self.assertEqual(2, len(view.violations))


class DeterminismTests(unittest.TestCase):
    def test_repeated_execution_is_byte_identical(self) -> None:
        first = canonical_bytes(generality.run_suite(SUITE))
        second = canonical_bytes(generality.run_suite(generality.load_suite()))
        self.assertEqual(first, second)

    def test_execution_is_byte_identical_in_a_fresh_process(self) -> None:
        script = (
            "import sys;"
            "from math_research.phase5.serialization import canonical_bytes;"
            "from math_research.phase6 import generality;"
            "sys.stdout.buffer.write("
            "canonical_bytes(generality.run_suite(generality.load_suite())))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, check=True,
            env={"PYTHONPATH": str(SRC), "PYTHONHASHSEED": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            cwd=str(ROOT),
        )
        self.assertEqual(canonical_bytes(RESULT), completed.stdout)

    def test_no_control_reads_the_clock_randomness_or_the_environment(self) -> None:
        forbidden_modules = {
            "time", "random", "secrets", "uuid", "os", "socket", "datetime",
            "subprocess", "sqlite3",
        }
        forbidden_calls = {"now", "utcnow", "today", "getenv", "monotonic", "urandom"}
        for name in ("generality.py", "heldout.py"):
            path = SRC / "math_research" / "phase6" / name
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            with self.subTest(module=name):
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotIn(alias.name.split(".")[0], forbidden_modules)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        self.assertNotIn(node.module.split(".")[0], forbidden_modules)
                    elif isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Attribute):
                            self.assertNotIn(node.func.attr, forbidden_calls)
                        if isinstance(node.func, ast.Name):
                            self.assertNotEqual("hash", node.func.id)
                            self.assertNotEqual("id", node.func.id)


class BoundaryTests(unittest.TestCase):
    """ADR-0034 boundaries stated as properties rather than as prose."""

    def test_phase6_does_not_import_the_benchmark_plugin_or_the_sealed_runtime(self) -> None:
        forbidden = ("benchmarks", "math_research.phase3b", "math_research.phase4a")
        roots = [SRC / "math_research" / "phase6", SRC / "math_research" / "domain"]
        for root in roots:
            for path in sorted(root.rglob("*.py")):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names = [node.module]
                    for name in names:
                        with self.subTest(path=path.name, imported=name):
                            for item in forbidden:
                                self.assertFalse(
                                    name == item or name.startswith(item + "."),
                                    f"{path} imports {name}",
                                )

    def test_the_suite_does_not_touch_novelty_or_significance(self) -> None:
        text = (SRC / "math_research" / "phase6" / "generality.py").read_text("utf-8")
        self.assertNotIn("novelty_assessment", text)
        self.assertNotIn("significance_assessment", text)
        for control in RESULT["controls"]:
            observed = control["observed"]
            if "target_novelty_status" in observed:
                with self.subTest(control=control["control_id"]):
                    self.assertEqual("not_assessed", observed["target_novelty_status"])
                    self.assertEqual("not_assessed", observed["target_significance_status"])

    def test_phase1_domain_semantics_are_unchanged(self) -> None:
        """The controls construct entities; they never redefine trust semantics."""

        from math_research.domain import entities, policies

        self.assertEqual("1.0.0", entities.ENTITY_SCHEMA_VERSION)
        self.assertEqual(
            [
                "schema_version", "claim_id", "semantic_alignment_status", "logical_status",
                "warrant_kinds", "novelty_status", "significance_status",
                "contribution_status", "blockers",
            ],
            list(generality.PROJECTION_AXES),
        )
        self.assertEqual(
            {
                "formal_proof", "rigorous_derivation", "exact_counterexample",
                "experimental_observation", "source_report", "model_agreement",
            },
            {item.value for item in entities.WarrantKind},
        )
        self.assertTrue(hasattr(policies.TrustPolicy, "target_resolution"))
        self.assertTrue(hasattr(policies.TrustPolicy, "can_discharge_obligation"))

    def test_the_phase5_fixture_hash_pinned_by_the_protocol_is_unchanged(self) -> None:
        self.assertEqual(PROTOCOL["phase5_fixture_hash"], canonical_hash(PHASE5_FIXTURE))


if __name__ == "__main__":
    unittest.main()
