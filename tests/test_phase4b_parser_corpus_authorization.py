"""Actual-corpus authorization evidence for strict Phase 4B workers."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from math_research.phase4b.corpus_authorization import (
    EVIDENCE_SCHEMA, run_parser_corpus_authorization,
)
from math_research.phase4b.serialization import canonical_hash, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]


class Phase4BParserCorpusAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_parser_corpus_authorization(ROOT)

    def test_all_actual_parser_fixtures_are_source_bound_and_hashed(self) -> None:
        report = self.report
        self.assertEqual(EVIDENCE_SCHEMA, report["schema_version"])
        self.assertEqual(12, report["counts"]["total"])
        self.assertEqual(12, len(report["cases"]))
        self.assertEqual(12, len({item["case_id"] for item in report["cases"]}))
        self.assertEqual({"html": 4, "pdf": 4, "tex": 4}, {
            name: sum(item["format"] == name for item in report["cases"])
            for name in ("html", "pdf", "tex")
        })
        self.assertTrue(all(
            item["fixture_sha256"] == item["request_original_sha256"]
            for item in report["cases"]
        ))
        self.assertTrue(all(
            item["media_type_hash"] == sha256_bytes(item["media_type"].encode("utf-8"))
            for item in report["cases"]
        ))
        supplied = report["content_hash"]
        unhashed = copy.deepcopy(report)
        unhashed.pop("content_hash")
        self.assertEqual(supplied, canonical_hash(unhashed))

    def test_current_corpus_is_authorized_without_activating_production(self) -> None:
        report = self.report
        self.assertEqual("authorized", report["status"])
        self.assertEqual("none", report["activation_effect"])
        self.assertFalse(report["production_activated"])
        self.assertEqual(0, report["counts"]["false_admissions"])
        self.assertEqual(12, report["counts"]["exact_disposition_matches"])
        self.assertTrue(all(item["exact_disposition_match"] for item in report["cases"]))
        admitted_pdf = [
            item for item in report["cases"]
            if item["format"] == "pdf" and item["expected_outcome"] == "candidate_proposal"
        ]
        self.assertEqual(2, len(admitted_pdf))
        self.assertTrue(all(item["observed_disposition"] == "candidate_proposal" for item in admitted_pdf))
        self.assertTrue(all(item["segment_count"] > 0 for item in admitted_pdf))

    def test_fixture_byte_change_fails_before_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary)
            shutil.copytree(ROOT / "fixtures/phase4b", copied / "fixtures/phase4b")
            path = copied / "fixtures/phase4b/acceptance/parsing/warning.html"
            path.write_bytes(path.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "fixture bytes differ"):
                run_parser_corpus_authorization(copied)

    def test_format_profile_mapping_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary)
            shutil.copytree(ROOT / "fixtures/phase4b", copied / "fixtures/phase4b")
            manifest_path = copied / "fixtures/phase4b/acceptance/manifest.json"
            manifest = json.loads(manifest_path.read_text("utf-8"))
            parsing = next(item for item in manifest["fixtures"] if item["class"] == "parsing")
            parsing["format"] = "epub"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "format counts differ"):
                run_parser_corpus_authorization(copied)


if __name__ == "__main__":
    unittest.main()
