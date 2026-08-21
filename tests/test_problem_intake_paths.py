"""ADR-0039: which existing paths accept an arbitrary intake dossier.

Measured here, not asserted in prose:

- the top-level `create`/`inspect`/`export`(`write_dossier`) path;
- the Phase 2 `BaselineResearchLoop` start/advance/run-to-terminal loop over a
  SQLite workspace with the scripted (no-network, no-model) gateway;
- the Phase 3A research-memory import path, which admits an intake dossier only
  as a `proposal`;
- the Phase 3B formal-check request path, which accepts the intake claim and
  alignment identifiers without special-casing.

The ADR-0039 recorded gap is now closed: `phase2 start` takes `--problem` plus
an explicit `--intake-instant` and resolves its dossier through the intake
loader. What replaced the gap test is the more important assertion -- that the
CLI still has no way to read a canonical *dossier* from a file. The problem
grammar cannot express a warrant; a dossier file can, so accepting one there
would let an edited file inject proof status into a run.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from math_research.application.problem_intake import load_problem_definition_file, parse_instant
from math_research.cli import main as root_main
from math_research.domain.entities import OpaqueId
from math_research.domain.policies import TrustPolicy
from math_research.interchange import export_dossier_bytes, import_trusted_replay
from math_research.phase2.artifacts import FileArtifactStore
from math_research.phase2.baseline_loop import BaselineResearchLoop, deterministic_fake_results
from math_research.phase2.model_gateway import ScriptedModelGateway
from math_research.phase2.records import BudgetLimits, RunStatus, VerifierIndependence
from math_research.phase2.sqlite_workspace import SQLiteWorkspace
from math_research.phase2_cli import _loop as _phase2_loop
from math_research.phase3a.workspace import ResearchMemoryWorkspace
from math_research.phase3b.records import SourceKind
from math_research.phase3b.validation import parse_request
from math_research.problem_intake_cli import main as intake_main

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures" / "problem-intake"
DEFINITION = FIXTURES / "graph-cycle-edge-bound-v1.json"
INSTANT_TEXT = "2026-08-21T00:00:00Z"
INSTANT = parse_instant(INSTANT_TEXT)
FIXED_TIME = "2026-08-21T00:00:00.000000Z"


def _dossier():
    return load_problem_definition_file(DEFINITION, instant=INSTANT).dossier


def _capture(argv: list[str]) -> tuple[int, str]:
    stream = io.StringIO()
    with redirect_stdout(stream):
        code = intake_main(argv)
    return code, stream.getvalue()


class CommandLineTests(unittest.TestCase):
    def test_create_writes_a_canonical_dossier_and_records_measured_trust(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "intake.json"
            code, text = _capture(["create", str(DEFINITION), INSTANT_TEXT, str(output)])
            self.assertEqual(0, code)
            summary = json.loads(text)
            self.assertEqual("unknown", summary["measured_trust"]["logical_status"])
            self.assertEqual([], summary["measured_trust"]["warrant_kinds"])
            self.assertEqual(0, summary["counts"]["warrants"])
            self.assertEqual(2, summary["counts"]["obligations_open"])
            written = output.read_bytes()
            self.assertEqual(export_dossier_bytes(_dossier()) + b"\n", written)
            self.assertEqual(summary["dossier_content_hash"], json.loads(written)["content_hash"])

    def test_create_is_byte_reproducible_across_invocations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "one.json"
            second = Path(temporary) / "two.json"
            _capture(["create", str(DEFINITION), INSTANT_TEXT, str(first)])
            _capture(["create", str(DEFINITION), INSTANT_TEXT, str(second)])
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_validate_accepts_a_valid_file_and_fails_closed_on_an_invalid_one(self) -> None:
        code, text = _capture(["validate", str(DEFINITION)])
        self.assertEqual(0, code)
        self.assertTrue(json.loads(text)["accepted"])
        code, text = _capture(["validate", str(FIXTURES / "invalid" / "forbidden-field-warrants.json")])
        self.assertEqual(2, code)
        payload = json.loads(text)
        self.assertFalse(payload["accepted"])
        self.assertEqual(["forbidden_field"], payload["codes"])
        self.assertEqual("$.warrants", payload["issues"][0]["path"])

    def test_create_on_an_invalid_file_writes_nothing_and_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "must-not-exist.json"
            code, _ = _capture([
                "create", str(FIXTURES / "invalid" / "forbidden-enum-value-approved-formalization.json"),
                INSTANT_TEXT, str(output),
            ])
            self.assertEqual(2, code)
            self.assertFalse(output.exists())

    def test_demo_replays_rederives_and_reports_without_asserting_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "out"
            code, text = _capture(["demo", str(DEFINITION), INSTANT_TEXT, "--output-dir", str(output_dir)])
            self.assertEqual(0, code)
            summary = json.loads(text)
            self.assertTrue(summary["round_trip_hash_preserved"])
            self.assertTrue(summary["rederived_hash_identical"])
            report = (output_dir / "intake-report.md").read_text(encoding="utf-8")
            self.assertIn("MEASURED by Phase 1 TrustPolicy: logical status `unknown`", report)
            self.assertIn("created no warrant", report)
            self.assertNotIn("independently checked", report)
            self.assertEqual(
                json.loads((output_dir / "intake-summary.json").read_text(encoding="utf-8"))["dossier_content_hash"],
                summary["dossier_content_hash"],
            )

    def test_schema_command_prints_the_derived_schema(self) -> None:
        code, text = _capture(["schema"])
        self.assertEqual(0, code)
        self.assertEqual(
            json.loads((REPO_ROOT / "schemas" / "problem-definition-v1.schema.json").read_text(encoding="utf-8")),
            json.loads(text),
        )

    def test_root_cli_routes_problem_and_inspects_the_result(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "intake.json"
            stream = io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(0, root_main(["problem", "create", str(DEFINITION), INSTANT_TEXT, str(output)]))
            stream = io.StringIO()
            with redirect_stdout(stream):
                self.assertEqual(0, root_main(["inspect", str(output)]))
            summary = json.loads(stream.getvalue())
            self.assertEqual("unknown", summary["logical_status"])
            self.assertTrue(summary["dossier_id"].startswith("dossier.graph-cycle-edge-bound.intake.sha256-"))

    def test_no_network_or_model_module_is_imported_on_the_intake_path(self) -> None:
        script = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "from math_research.problem_intake_cli import main;"
            "main(['create', %r, %r, sys.argv[1]]);"
            "loaded = set(sys.modules);"
            "banned = {'socket', 'ssl', 'http.client', 'urllib.request', 'openai', 'anthropic'};"
            "print(sorted(loaded & banned))"
        ) % (str(REPO_ROOT / "src"), str(DEFINITION), INSTANT_TEXT)
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [sys.executable, "-c", script, str(Path(temporary) / "out.json")],
                capture_output=True, check=True, text=True, timeout=120,
            )
        self.assertEqual("[]", completed.stdout.strip().splitlines()[-1])


class Phase2LoopTests(unittest.TestCase):
    """The engine was already problem-agnostic. This measures that it is."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.artifacts = FileArtifactStore(self.root / "artifacts")
        self.dossier = _dossier()

    def tearDown(self) -> None:
        self.workspace.close()
        self.temporary.cleanup()

    def _loop(self) -> BaselineResearchLoop:
        proposer, verifier = deterministic_fake_results(
            self.dossier.formalization.target_claim_id.value,
            self.dossier.formalization.assumption_claim_ids[0].value,
        )
        gateway = ScriptedModelGateway({"proposer": [proposer], "verifier": [verifier]})
        return BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=gateway, verifier=gateway,
            independence=VerifierIndependence(
                context_isolated=True, separate_model_call=True,
                different_model=False, different_provider=False,
                deterministic_checker=False, independently_implemented_checker=False,
                formal_kernel=False,
            ),
            now=lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
        )

    def test_start_and_advance_drive_the_intake_dossier_to_a_terminal_state(self) -> None:
        loop = self._loop()
        run_id = OpaqueId("run.intake.graph.v1")
        run = loop.start(
            run_id=run_id, dossier=self.dossier,
            limits=BudgetLimits(
                max_input_tokens=20_000, max_output_tokens=4_000,
                max_cost_microusd=1000, max_wall_milliseconds=120_000, max_attempts=4,
            ),
        )
        self.assertEqual(RunStatus.RUNNING, run.status)
        final = loop.run_to_terminal(run_id)
        self.assertEqual(RunStatus.AWAITING_REVIEW, final.status)
        stored = self.workspace.load_dossier(final.dossier_id)
        self.assertEqual(export_dossier_bytes(self.dossier), export_dossier_bytes(stored))
        proposals = self.workspace.list_proposals(run_id)
        self.assertEqual(["proposal", "proposal"], [item.disposition for item in proposals])
        # The sealed Phase 2 evidence boundary holds for an intake dossier too.
        self.assertEqual("unknown", TrustPolicy(stored).target_resolution().logical_status)
        self.assertEqual((), stored.warrants)
        self.assertEqual((), stored.verification_records)

    def test_proposer_context_is_built_from_the_declared_target_and_premises(self) -> None:
        context, referenced = BaselineResearchLoop._proposer_context(self.dossier)
        self.assertEqual(
            self.dossier.formalization.target_claim_id.value, context["approved_target"]["id"]
        )
        self.assertEqual(2, len(context["accepted_premises"]))
        self.assertEqual(2, len(context["open_obligations"]))
        self.assertIn(self.dossier.formalization.id, referenced)
        self.assertTrue(context["verification_policy"]["models_cannot_award_warrants"])

    def test_phase2_cli_runs_a_problem_definition_and_never_a_supplied_dossier(self) -> None:
        """The recorded ADR-0039 gap is closed; these are its replacement guards.

        `phase2 start` now resolves its dossier from a problem definition. The
        important half is what it still refuses: there is no option that reads a
        canonical dossier from a file, because the problem grammar cannot express
        a warrant while a dossier file can. Accepting one here would let an
        edited file inject proof status straight into a run.
        """

        source = (REPO_ROOT / "src" / "math_research" / "phase2_cli.py").read_text(encoding="utf-8")
        self.assertIn("problem_intake", source)
        self.assertIn("--problem", source)
        self.assertIn("--intake-instant", source)
        # The dossier is supplied to the loop, never rebuilt inside it.
        self.assertNotIn("dossier=build_open_theorem_dossier()", source)
        # No dossier-file intake, and no trusted-replay call on external bytes.
        self.assertNotIn("--dossier", source)
        # No *call* to trusted replay. The name appears in a docstring there
        # explaining why the option is absent, so match the call syntax.
        self.assertNotIn("import_trusted_replay(", source)

    def test_a_problem_that_asserts_its_own_proof_stays_unknown_through_the_loop(self) -> None:
        """The forbidden outcome, measured through the real run path.

        The fixture claims in prose that it is already proved, machine-checked,
        warranted, novel and significant. Running it must still leave the target
        unresolved with no warrants.
        """

        definition = REPO_ROOT / "fixtures" / "problem-intake" / "asserts-its-own-proof-v1.json"
        dossier = load_problem_definition_file(
            definition, instant=parse_instant("2026-08-21T00:00:00Z")
        ).dossier
        with tempfile.TemporaryDirectory() as temporary:
            workspace = SQLiteWorkspace(Path(temporary) / "workspace.sqlite3")
            try:
                artifacts = FileArtifactStore(Path(temporary) / "artifacts")
                loop = _phase2_loop(
                    workspace, artifacts, "fake", None, None, dossier=dossier
                )
                run_id = OpaqueId("run.asserts.proof")
                loop.start(
                    run_id=run_id, dossier=dossier,
                    limits=BudgetLimits(
                        max_input_tokens=20_000, max_output_tokens=4_000,
                        max_cost_microusd=10_000_000, max_wall_milliseconds=300_000,
                        max_attempts=4,
                    ),
                )
                loop.run_to_terminal(run_id)
                reloaded = workspace.load_dossier(workspace.get_run(run_id).dossier_id)
                resolution = TrustPolicy(reloaded).target_resolution()
                self.assertEqual("unknown", resolution.logical_status)
                self.assertEqual((), reloaded.warrants)
                self.assertEqual((), reloaded.evidence)
                self.assertTrue(workspace.list_proposals(run_id))
            finally:
                workspace.close()


class Phase3PathTests(unittest.TestCase):
    def test_phase3a_memory_admits_an_intake_dossier_only_as_a_proposal(self) -> None:
        payload = json.loads(export_dossier_bytes(_dossier()))
        with tempfile.TemporaryDirectory() as temporary, ResearchMemoryWorkspace(Path(temporary)) as memory:
            proposal = memory.import_proposal(payload, source_label="problem_intake", now=FIXED_TIME)
            self.assertEqual("proposal", proposal["disposition"])
            self.assertEqual("problem_intake", proposal["source_label"])
            self.assertEqual((), memory.all_records())

    def test_phase3b_request_path_accepts_intake_claim_and_alignment_ids(self) -> None:
        dossier = _dossier()
        request = {
            "schema_version": "1.0.0",
            "request_id": "request.intake.graph.v1",
            "claim_id": dossier.formalization.target_claim_id.value,
            "semantic_alignment_id": dossier.semantic_alignment.id.value,
            "source_kind": "operator",
            "declaration_name": "AdaIvyIntakeTarget",
            "imports": [],
            "assumptions": [],
            "target_statement": "True",
            "proof_fragment": "trivial",
            "meaning_tests": [],
        }
        parsed = parse_request(request)
        self.assertEqual(dossier.formalization.target_claim_id, parsed.claim_id)
        self.assertEqual(dossier.semantic_alignment.id, parsed.semantic_alignment_id)
        self.assertEqual(SourceKind.OPERATOR, parsed.source_kind)


class InterchangeRoundTripTests(unittest.TestCase):
    def test_exported_intake_dossier_replays_to_an_identical_dossier(self) -> None:
        dossier = _dossier()
        self.assertEqual(dossier, import_trusted_replay(export_dossier_bytes(dossier)))


if __name__ == "__main__":
    unittest.main()
