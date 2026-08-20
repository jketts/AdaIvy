"""Subprocess checks for the offline Phase 4B CLI boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class Phase4BCliTests(unittest.TestCase):
    def _run(self, *arguments: str) -> dict[str, object]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-m", "math_research.phase4b_cli", *arguments],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return json.loads(result.stdout)

    def test_empty_workspace_export_inspect_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original"
            replayed = root / "replayed"
            export = root / "candidate-metadata.json"
            initialized = self._run("init", str(original))
            written = self._run("export", str(original), str(export))
            inspected = self._run("inspect", str(export))
            imported = self._run("replay", str(replayed), str(export))
            self.assertEqual(initialized, written)
            self.assertEqual(written, inspected)
            self.assertEqual(inspected, imported)
            self.assertEqual(inspected["profile"], "phase4b-candidate-audit-v2")
            self.assertEqual(inspected["records"], 0)
            self.assertEqual(inspected["active_candidates"], 0)

    def test_top_level_router_exposes_phase4b(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            result = subprocess.run(
                [
                    sys.executable, "-m", "math_research.cli", "phase4b",
                    "init", str(Path(temporary) / "workspace"),
                ],
                cwd=ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(json.loads(result.stdout)["records"], 0)

    def test_feasible_gate_writes_partial_report_without_claiming_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "feasible-gate.json"
            report = self._run(
                "gate", str(ROOT), str(root / "gate-work"), "--output", str(output)
            )
            self.assertEqual(report, json.loads(output.read_text("utf-8")))
            self.assertEqual(
                "blocked_pending_full_gate_controls", report["activation_status"]
            )
            self.assertTrue(all(
                item["status"] == "blocked" and item["counted_as_pass"] is False
                for item in report["blocked_controls"]
            ))


if __name__ == "__main__":
    unittest.main()
