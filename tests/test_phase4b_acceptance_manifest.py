"""Frozen structure and hash checks for the 30-case Phase 4B inventory.

These tests establish P4B-AT-001 through P4B-AT-004 corpus shape.  They do not
claim the complete ADR-0028 behavioral or production-path gate.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest

from math_research.phase4b.parsing import (
    HTML_PROFILE, PDF_PROFILE, TEX_PROFILE, ParseRequest, run_parser,
)


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "fixtures" / "phase4b" / "acceptance" / "manifest.json"
MANIFEST_ROOT = MANIFEST_PATH.parent
PHASE4B_FIXTURE_ROOT = MANIFEST_ROOT.parent.resolve()
MANIFEST_FIELDS = {
    "schema_version", "fixture_license", "declared_counts", "fixtures",
    "coverage_status", "content_hash",
}
ENTRY_FIELDS = {
    "case_id", "class", "format", "role", "expected_outcome", "path",
    "byte_length", "sha256",
}


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def strict_json(data: bytes) -> dict[str, object]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    value = json.loads(data, object_pairs_hook=pairs, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


class Phase4BAcceptanceManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = strict_json(MANIFEST_PATH.read_bytes())
        cls.fixtures = cls.manifest["fixtures"]

    def test_manifest_schema_license_and_self_hash_are_exact(self) -> None:
        self.assertEqual(set(self.manifest), MANIFEST_FIELDS)
        self.assertEqual(
            self.manifest["schema_version"], "adaivy.phase4b-acceptance-manifest.v1"
        )
        self.assertEqual(
            self.manifest["coverage_status"],
            "actual_corpus_strict_workers_authorized_not_activated",
        )
        self.assertEqual(
            self.manifest["fixture_license"],
            {
                "copyright_notice": "Project-authored synthetic acceptance fixtures; 2026 AdaIvy contributors",
                "license_expression": "LicenseRef-AdaIvy-Synthetic-Fixture",
                "redistribution_status": "allowed",
            },
        )
        semantic = dict(self.manifest)
        observed = semantic.pop("content_hash")
        self.assertEqual(observed, sha256(canonical_bytes(semantic)))

    def test_exact_30_case_allocation_and_unique_classification(self) -> None:
        self.assertIsInstance(self.fixtures, list)
        self.assertEqual(len(self.fixtures), 30)
        self.assertEqual(len({item["case_id"] for item in self.fixtures}), 30)
        self.assertEqual(len({item["path"] for item in self.fixtures}), 30)
        for item in self.fixtures:
            self.assertEqual(set(item), ENTRY_FIELDS)

        classes = Counter(item["class"] for item in self.fixtures)
        acquisition_roles = Counter(
            item["role"] for item in self.fixtures if item["class"] == "acquisition"
        )
        parser_formats = Counter(
            item["format"] for item in self.fixtures if item["class"] == "parsing"
        )
        parser_roles = Counter(
            (item["format"], item["role"])
            for item in self.fixtures if item["class"] == "parsing"
        )
        self.assertEqual(classes, {"acquisition": 12, "parsing": 12, "lifecycle_integration": 6})
        self.assertEqual(acquisition_roles, {"allowed": 3, "denied": 9})
        self.assertEqual(parser_formats, {"html": 4, "tex": 4, "pdf": 4})
        self.assertEqual(
            parser_roles,
            {
                (fmt, role): 1
                for fmt in ("html", "tex", "pdf")
                for role in ("ordinary", "warning", "attack", "malformed_or_limit")
            },
        )
        self.assertEqual(
            self.manifest["declared_counts"],
            {
                "total": 30, "acquisition": 12, "acquisition_allowed": 3,
                "acquisition_denied": 9, "parsing": 12, "parsing_html": 4,
                "parsing_tex": 4, "parsing_pdf": 4, "lifecycle_integration": 6,
            },
        )

    def test_every_path_is_bounded_project_fixture_with_exact_bytes_and_hash(self) -> None:
        for item in self.fixtures:
            with self.subTest(case_id=item["case_id"]):
                path = (MANIFEST_ROOT / item["path"]).resolve()
                self.assertTrue(path.is_relative_to(PHASE4B_FIXTURE_ROOT))
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                data = path.read_bytes()
                self.assertGreater(len(data), 0)
                self.assertLessEqual(len(data), 2_097_152)
                self.assertEqual(item["byte_length"], len(data))
                self.assertEqual(item["sha256"], sha256(data))

    def test_json_case_specs_have_closed_shape_and_match_manifest(self) -> None:
        expected_fields = {"case_id", "expected_outcome", "scenario"}
        for item in self.fixtures:
            if item["class"] == "parsing":
                continue
            with self.subTest(case_id=item["case_id"]):
                path = (MANIFEST_ROOT / item["path"]).resolve()
                value = strict_json(path.read_bytes())
                self.assertEqual(set(value), expected_fields)
                self.assertEqual(value["case_id"], item["case_id"])
                self.assertEqual(value["expected_outcome"], item["expected_outcome"])
                self.assertIsInstance(value["scenario"], str)
                self.assertTrue(value["scenario"])

    def test_parser_inventory_outcomes_match_the_current_restricted_fixture_profiles(self) -> None:
        profiles = {"html": HTML_PROFILE, "tex": TEX_PROFILE, "pdf": PDF_PROFILE}
        for item in self.fixtures:
            if item["class"] != "parsing":
                continue
            with self.subTest(case_id=item["case_id"]):
                data = (MANIFEST_ROOT / item["path"]).resolve().read_bytes()
                profile = profiles[item["format"]]
                request = ParseRequest.create(
                    request_id=item["case_id"], source_id="source.phase4b.manifest",
                    content_object_id="content." + item["case_id"],
                    representation_id="representation." + item["case_id"],
                    media_type=profile.media_type, profile_name=profile.name,
                    original_bytes=data,
                )
                result = run_parser(request)
                self.assertEqual(result.disposition, item["expected_outcome"])
                if item["role"] == "warning":
                    self.assertTrue(result.warnings)
                if result.disposition == "candidate_proposal":
                    self.assertTrue(result.segments)
                    for segment in result.segments:
                        segment.anchor.validate(data)


if __name__ == "__main__":
    unittest.main()
