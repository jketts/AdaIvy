from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from math_research.application.manual_slice import build_known_valid_theorem_dossier
from math_research.cli import main as cli_main
from math_research.domain.entities import Disposition
from math_research.domain.policies import TrustPolicy
from math_research.interchange import (
    canonical_bytes,
    export_dossier_dict,
    import_external_proposals,
    import_trusted_replay,
    validate_dossier_payload,
    validate_scenario_payload,
)

ROOT = Path(__file__).resolve().parents[1]


class DossierInterchangeTests(unittest.TestCase):
    def test_canonical_export_import_preserves_ids_meaning_bytes_and_hash(self) -> None:
        dossier = build_known_valid_theorem_dossier()
        payload = export_dossier_dict(dossier)
        self.assertEqual((), validate_dossier_payload(payload))
        replayed = import_trusted_replay(canonical_bytes(payload))
        replay_payload = export_dossier_dict(replayed)
        self.assertEqual(dossier, replayed)
        self.assertEqual(payload["content_hash"], replay_payload["content_hash"])
        self.assertEqual(canonical_bytes(payload), canonical_bytes(replay_payload))
        self.assertEqual(dossier.id, replayed.id)
        self.assertEqual(dossier.formalization.target_claim_id, replayed.formalization.target_claim_id)

    def test_imported_external_proof_artifacts_remain_untrusted_proposals(self) -> None:
        payload = export_dossier_dict(build_known_valid_theorem_dossier())
        bundle = import_external_proposals(payload)
        self.assertEqual(Disposition.PROPOSAL, bundle.disposition)
        self.assertGreater(len(bundle.artifacts), 0)
        self.assertTrue(all(item.disposition is Disposition.PROPOSAL for item in bundle.artifacts))
        self.assertIn("VerificationRecord", {item.artifact_kind for item in bundle.artifacts})

    def test_every_phase1_scenario_fixture_is_versioned_and_known(self) -> None:
        paths = sorted((ROOT / "fixtures" / "phase1").glob("*.json"))
        self.assertEqual(5, len(paths))
        kinds = set()
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("1.0.0", payload["schema_version"])
            self.assertTrue(payload["target"])
            self.assertTrue(payload["expected"])
            self.assertEqual((), validate_scenario_payload(payload))
            kinds.add(payload["kind"])
        self.assertEqual(5, len(kinds))

    def test_normative_schemas_parse_and_phase1_payload_validates(self) -> None:
        for name in ("research-dossier-v1.schema.json", "phase1-scenario.schema.json"):
            schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual((), validate_dossier_payload(export_dossier_dict(build_known_valid_theorem_dossier())))


class ManualVerticalSliceTests(unittest.TestCase):
    def test_manual_cli_creates_inspects_replays_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertEqual(0, cli_main(["demo", "--output-dir", str(output)]))
            dossier_path = output / "manual-dossier.json"
            report_path = output / "traceable-report.md"
            self.assertTrue(dossier_path.exists())
            self.assertTrue(report_path.exists())
            self.assertEqual(0, cli_main(["inspect", str(dossier_path)]))
            dossier = import_trusted_replay(dossier_path.read_bytes())
            known_fixture = json.loads((ROOT / "fixtures/phase1/known-valid-theorem.json").read_text())
            self.assertEqual(known_fixture["expected"]["target_logical_status"], TrustPolicy(dossier).target_resolution().logical_status)
            for line in report_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("- "):
                    self.assertIn("[refs:", line)


if __name__ == "__main__":
    unittest.main()
