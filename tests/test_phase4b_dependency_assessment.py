import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "docs" / "phase-4b" / "parser-dependency-assessment-v1.json"
SPIKE_RESULT = ROOT / "docs" / "phase-4b" / "parser-dependency-spike-result-v1.json"
HASH_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def canonical_sha256(value: dict) -> str:
    content = dict(value)
    content.pop("assessment_content_sha256")
    encoded = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class Phase4BDependencyAssessmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = ASSESSMENT.read_bytes()
        self.value = json.loads(self.raw)

    def test_manifest_has_closed_top_level_shape_and_is_not_authority(self) -> None:
        self.assertEqual(
            {"activation", "assessment_content_sha256", "assessment_date",
             "candidates", "install_lock", "schema_version", "target"},
            set(self.value),
        )
        self.assertEqual("disabled", self.value["activation"])
        self.assertFalse(self.value["install_lock"])
        self.assertEqual(
            "adaivy.phase4b-parser-dependency-assessment.v1",
            self.value["schema_version"],
        )
        self.assertEqual(
            {"implementation": "CPython", "platform": "darwin-arm64", "python": "3.14"},
            self.value["target"],
        )

    def test_candidate_shape_dispositions_and_closure_rules_are_exact(self) -> None:
        keys = {"artifacts", "capability", "closure", "closure_complete",
                "disposition", "known_cves", "license", "name", "native_code",
                "reason_code", "source_commit", "version"}
        candidates = self.value["candidates"]
        self.assertEqual(
            [("html5lib", "reject"), ("pylatexenc", "defer"),
             ("pypdf", "defer"), ("pdfminer.six", "reject")],
            [(item["name"], item["disposition"]) for item in candidates],
        )
        for item in candidates:
            self.assertEqual(keys, set(item))
            self.assertRegex(item["source_commit"], r"^[0-9a-f]{40}$")
            self.assertNotEqual("approve", item["disposition"])
            self.assertEqual(2, len(item["artifacts"]))
            for artifact in item["artifacts"]:
                self.assertEqual(
                    {"filename", "kind", "sha256", "size_bytes"}, set(artifact)
                )
                self.assertRegex(artifact["sha256"], HASH_RE)
                self.assertGreater(artifact["size_bytes"], 0)
            if item["closure_complete"]:
                self.assertGreaterEqual(len(item["closure"]), 1)
                for package in item["closure"]:
                    self.assertEqual(
                        {"license", "name", "sdist_sha256", "version", "wheel_sha256"},
                        set(package),
                    )
                    self.assertRegex(package["wheel_sha256"], HASH_RE)
                    self.assertRegex(package["sdist_sha256"], HASH_RE)
            else:
                self.assertEqual("reject", item["disposition"])

    def test_embedded_canonical_hash_detects_manifest_mutation(self) -> None:
        self.assertEqual(
            canonical_sha256(self.value), self.value["assessment_content_sha256"]
        )

    def test_serialization_is_deterministic_and_newline_terminated(self) -> None:
        expected = json.dumps(
            self.value, ensure_ascii=False, sort_keys=True, indent=2
        ).encode("utf-8") + b"\n"
        self.assertEqual(expected, self.raw)

    def test_disposable_spike_records_failures_without_activating(self) -> None:
        result = json.loads(SPIKE_RESULT.read_bytes())
        self.assertEqual(
            {"activation", "artifacts_committed", "assessment_date", "install",
             "overall_result", "probes", "requirements_file", "schema_version",
             "target", "unclosed_evidence"},
            set(result),
        )
        self.assertEqual("disabled", result["activation"])
        self.assertEqual("blocked", result["overall_result"])
        self.assertFalse(result["artifacts_committed"])
        self.assertEqual("passed_disposable_only", result["install"]["result"])
        self.assertTrue(result["install"]["no_index"])
        self.assertTrue(result["install"]["download"]["hashes_verified"])
        self.assertEqual(
            [("pylatexenc", "2.11"), ("pypdf", "6.16.1")],
            [(item["name"], item["version"])
             for item in result["install"]["installed_inventory"]],
        )
        self.assertEqual("failed_gate", result["probes"]["pylatexenc"]["result"])
        self.assertEqual("failed_gate", result["probes"]["pypdf"]["result"])
        self.assertFalse(result["probes"]["pypdf"]["exact_source_byte_offsets"])


if __name__ == "__main__":
    unittest.main()
