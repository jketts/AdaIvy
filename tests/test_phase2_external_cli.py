from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from math_research.domain.entities import oid
from math_research.domain.policies import TrustPolicy
from math_research.interchange import export_dossier_bytes
from math_research.phase2.artifacts import FileArtifactStore
from math_research.phase2.baseline_loop import BaselineResearchLoop, deterministic_fake_results
from math_research.phase2.external_backend import ExternalBackendService, FilesystemProcessBackend
from math_research.phase2.fixtures import build_open_theorem_dossier
from math_research.phase2.model_gateway import ScriptedModelGateway
from math_research.phase2.records import BudgetLimits, VerifierIndependence
from math_research.phase2.sqlite_workspace import SQLiteWorkspace
from math_research.phase2_cli import main as phase2_main


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class ExternalCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.artifacts = FileArtifactStore(self.root / "artifacts")
        self.dossier = build_open_theorem_dossier()
        proposer, verifier = deterministic_fake_results(
            self.dossier.formalization.target_claim_id.value,
            self.dossier.formalization.assumption_claim_ids[0].value,
        )
        gateway = ScriptedModelGateway({"proposer": [proposer], "verifier": [verifier]})
        self.loop = BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=gateway, verifier=gateway,
            independence=VerifierIndependence(
                context_isolated=True, separate_model_call=True, different_model=False,
                different_provider=False, deterministic_checker=False,
                independently_implemented_checker=False, formal_kernel=False,
            ),
        )
        self.run = self.loop.start(
            run_id=oid("run.external.v1"), dossier=self.dossier,
            limits=BudgetLimits(max_input_tokens=10_000, max_output_tokens=2_000, max_cost_microusd=1000, max_wall_milliseconds=120_000, max_attempts=4),
        )
        self.backend = FilesystemProcessBackend(self.root / "backend-runs", self.artifacts)
        self.service = ExternalBackendService(workspace=self.workspace, artifacts=self.artifacts, backend=self.backend, now=now)
        self.fixture = (Path("fixtures/phase2/external_backend_fixture.py").resolve())

    def tearDown(self) -> None:
        self.workspace.close()
        self.temporary.cleanup()


class ExternalBackendTests(ExternalCase):
    def test_successful_package_imports_proposals_only(self) -> None:
        before = TrustPolicy(self.dossier).target_resolution()
        result = self.service.run(
            run_id=self.run.run_id, backend_run_id=oid("backend.success.v1"),
            command=(sys.executable, str(self.fixture), "success"),
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.proposal_ids), 1)
        proposal = self.workspace.list_proposals(self.run.run_id)[0]
        self.assertEqual(proposal.source_kind, "external_backend")
        self.assertEqual(proposal.disposition, "proposal")
        self.assertEqual(TrustPolicy(self.workspace.load_dossier(self.run.dossier_id)).target_resolution(), before)

    def test_malicious_and_malformed_packages_are_rejected(self) -> None:
        for index, mode in enumerate(("traversal", "bad-hash", "schema-mismatch", "unexpected")):
            result = self.service.run(
                run_id=self.run.run_id, backend_run_id=oid(f"backend.rejected.{index}"),
                command=(sys.executable, str(self.fixture), mode),
            )
            self.assertEqual(result.status, "rejected")
            self.assertEqual(result.proposal_ids, ())
        self.assertEqual(self.workspace.list_proposals(self.run.run_id), ())
        self.assertFalse((self.root / "escape.json").exists())

    def test_process_evidence_is_complete(self) -> None:
        result = self.service.run(
            run_id=self.run.run_id, backend_run_id=oid("backend.evidence.v1"),
            command=(sys.executable, str(self.fixture), "success"),
        )
        self.assertEqual(result.exit_status, 0)
        for value in (result.stdout_hash, result.stderr_hash, result.environment_hash, result.package_hash):
            self.assertTrue(value.startswith("sha256:"))
            self.assertTrue(self.artifacts.exists(value)) if value != result.package_hash else None
        run_dir = self.root / "backend-runs" / "backend.evidence.v1"
        self.assertEqual((run_dir / "input" / "dossier.json").read_bytes(), export_dossier_bytes(self.dossier))
        manifest = json.loads((run_dir / "input" / "manifest.json").read_bytes())
        self.assertEqual(manifest["disposition"], "proposal")
        self.assertEqual(manifest["run_id"], self.run.run_id.value)
        event = next(item for item in self.workspace.timeline(self.run.run_id) if item["event_type"] == "backend_execution_recorded")
        self.assertEqual(event["payload"]["stdout_hash"], result.stdout_hash)
        self.assertEqual(event["payload"]["exit_status"], 0)

    def test_timeout_and_cancellation_cannot_commit(self) -> None:
        result = self.service.run(
            run_id=self.run.run_id, backend_run_id=oid("backend.cancelled.v1"),
            command=(sys.executable, "-c", "import time; time.sleep(2)"),
            timeout_milliseconds=1000, cancelled=lambda: True,
        )
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(self.workspace.list_proposals(self.run.run_id), ())
        timed_out = self.service.run(
            run_id=self.run.run_id, backend_run_id=oid("backend.timeout.v1"),
            command=(sys.executable, "-c", "import time; time.sleep(2)"),
            timeout_milliseconds=20,
        )
        self.assertEqual(timed_out.status, "timeout")
        self.assertEqual(self.workspace.list_proposals(self.run.run_id), ())


class Phase2CliTests(unittest.TestCase):
    def test_start_inspect_pause_resume_export_timeline_and_report_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_id = "run.cli.acceptance.v1"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(phase2_main(["start", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["jobs", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["budget", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["pause", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["resume", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["advance", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["advance", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["artifacts", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["manifest", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["review", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["timeline", str(root), run_id]), 0)
                self.assertEqual(phase2_main(["export", str(root), run_id, str(root / "dossier.json")]), 0)
                self.assertEqual(phase2_main(["report", str(root), run_id, "--output", str(root / "report.md")]), 0)
            self.assertTrue((root / "dossier.json").is_file())
            self.assertIn("Durable Phase 2", (root / "report.md").read_text(encoding="utf-8"))


class ScopeGuardTests(unittest.TestCase):
    def test_no_forbidden_phase3_imports_or_integrations(self) -> None:
        source = "\n".join(path.read_text(encoding="utf-8") for path in Path("src/math_research").rglob("*.py"))
        forbidden_imports = ("import psycopg", "import sqlalchemy", "import lean", "import why3", "import paperqa", "import eigenius")
        for value in forbidden_imports:
            self.assertNotIn(value, source.lower())


class Phase2SchemaTests(unittest.TestCase):
    def test_phase2_json_schemas_are_valid_json_and_versioned(self) -> None:
        for name in ("model-proposer-v1.schema.json", "model-verifier-v1.schema.json", "external-backend-package-v1.schema.json"):
            value = json.loads((Path("schemas") / name).read_text(encoding="utf-8"))
            self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertIn("schema_version", value["properties"])
