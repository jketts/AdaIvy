from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from phase0_harness.adapters import file_baseline, omdoc
from phase0_harness.canonical import canonical_bytes, dossier_hash
from phase0_harness.catalog import CANDIDATES
from phase0_harness.evaluator import evaluate_negative_fixtures, run_evaluation
from phase0_harness.validation import validate_backend_result, validate_dossier


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "phase0" / "reference-dossier.json"


class DossierValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dossier = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_reference_fixture_is_valid_and_hash_is_stable(self) -> None:
        self.assertEqual([], validate_dossier(self.dossier))
        self.assertEqual(self.dossier["content_hash"], dossier_hash(self.dossier))
        reparsed = json.loads(canonical_bytes(self.dossier))
        self.assertEqual(canonical_bytes(self.dossier), canonical_bytes(reparsed))

    def test_target_drift_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.dossier)
        candidate["semantic_alignment"]["compared_claim_id"] = "claim.even_definition"
        codes = {issue.code for issue in validate_dossier(candidate, verify_hash=False)}
        self.assertIn("target_fidelity", codes)

    def test_experimental_overreach_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.dossier)
        target = candidate["claims"][1]
        target["truth_status"] = "proved"
        target["warrants"] = [{"kind": "experimentally_observed", "scope": "finite samples", "status": "active"}]
        codes = {issue.code for issue in validate_dossier(candidate, verify_hash=False)}
        self.assertIn("experimental_overreach", codes)

    def test_all_negative_fixtures_trigger_expected_rules(self) -> None:
        results = evaluate_negative_fixtures(ROOT, self.dossier)
        self.assertGreaterEqual(len(results), 3)
        self.assertTrue(all(result["passed"] for result in results), results)

    def test_normative_json_schemas_are_parseable(self) -> None:
        for name in ("research-dossier.schema.json", "backend-result.schema.json"):
            schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])

    def test_backend_result_preserves_proposal_boundary(self) -> None:
        path = ROOT / "fixtures" / "phase0" / "backend-result-proposal.json"
        result = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([], validate_backend_result(result))
        candidate = copy.deepcopy(result)
        candidate["candidate_artifacts"][0]["disposition"] = "trusted"
        codes = {issue.code for issue in validate_backend_result(candidate, verify_hash=False)}
        self.assertIn("trust_boundary", codes)


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dossier = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_file_baseline_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = file_baseline.evaluate(self.dossier, Path(directory))
            self.assertEqual("succeeded", result["status"])
            self.assertTrue(result["evidence"]["byte_stable"])
            self.assertEqual(self.dossier["content_hash"], result["evidence"]["replay_hash"])

    def test_omdoc_projection_retains_exact_target_and_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = omdoc.evaluate(self.dossier, Path(directory))
            self.assertEqual("partial", result["status"])
            self.assertEqual("claim.even_sum", result["evidence"]["target_id_round_trip"])
            self.assertEqual(self.dossier["content_hash"], result["evidence"]["sidecar_hash"])

    def test_full_evaluation_accounts_for_every_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = run_evaluation(ROOT, Path(directory))
            self.assertTrue(payload["checks_passed"])
            self.assertEqual([item["id"] for item in CANDIDATES], [item["component_id"] for item in payload["components"]])
            for component in payload["components"]:
                self.assertIn("comparison_to_file_baseline", component)
                self.assertIn(component["status"], {"succeeded", "partial", "failed", "blocked", "deferred"})
            self.assertTrue((Path(directory) / "results.json").exists())
            self.assertTrue((Path(directory) / "evaluation-correction.json").exists())
            self.assertTrue((Path(directory) / "scorecard.md").exists())


if __name__ == "__main__":
    unittest.main()
