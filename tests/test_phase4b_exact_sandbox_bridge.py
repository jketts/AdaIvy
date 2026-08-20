"""Concrete, non-activating bridge between exact parsing and the OS sandbox."""

from __future__ import annotations

import hashlib
from pathlib import Path
import platform
import unittest
from unittest.mock import patch

from math_research.phase4b.exact_parser_worker import (
    IMPLEMENTATION_SHA256, ExactSourceParserWorker,
)
from math_research.phase4b.exact_sandbox_bridge import (
    ARTIFACT_SCHEMA, build_exact_darwin_sandbox_worker,
)
from math_research.phase4b.parsing import (
    HTML_PROFILE, PDF_PROFILE, TEX_PROFILE, ParseRequest, run_production_parser,
    verify_result_record,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures" / "phase4b" / "parsing"


def request(label: str, profile, original: bytes) -> ParseRequest:
    return ParseRequest.create(
        request_id=f"request.bridge.{label}", source_id=f"source.bridge.{label}",
        content_object_id=f"content.bridge.{label}",
        representation_id=f"representation.bridge.{label}",
        media_type=profile.media_type, profile_name=profile.name,
        original_bytes=original,
    )


class Phase4BExactSandboxBridgeTests(unittest.TestCase):
    def test_artifact_binds_exact_semantics_composed_source_and_runtime(self) -> None:
        first, first_artifact = build_exact_darwin_sandbox_worker()
        second, second_artifact = build_exact_darwin_sandbox_worker()
        self.assertEqual(first_artifact, second_artifact)
        self.assertEqual(ARTIFACT_SCHEMA, first_artifact.schema_version)
        self.assertEqual(IMPLEMENTATION_SHA256, first_artifact.exact_parser_source_sha256)
        self.assertEqual(first.implementation_sha256, first_artifact.worker_source_sha256)
        self.assertEqual(first.worker_source, second.worker_source)
        self.assertNotIn(str(ROOT), first.worker_source)
        self.assertNotIn("math_research", first.worker_source)
        self.assertEqual(
            "sha256:" + hashlib.sha256(first.worker_source.encode()).hexdigest(),
            first_artifact.worker_source_sha256,
        )

    def test_non_darwin_fails_closed_without_launch(self) -> None:
        worker, _artifact = build_exact_darwin_sandbox_worker()
        original = (FIXTURES / "authoritative.html").read_bytes()
        with patch("math_research.phase4b.parser_sandbox.platform.system", return_value="Linux"):
            execution = worker.execute(request("unavailable", HTML_PROFILE, original))
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_named_platform_unavailable", execution.failure_code)
        self.assertIsNone(execution.outcome)

    def test_darwin_bridge_matches_exact_html_and_tex_candidate_semantics(self) -> None:
        if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            self.skipTest("named Darwin sandbox-exec boundary unavailable")
        worker, _artifact = build_exact_darwin_sandbox_worker()
        cases = (
            ("html", HTML_PROFILE, "authoritative.html"),
            ("tex", TEX_PROFILE, "nonexecuting.tex"),
        )
        for label, profile, filename in cases:
            with self.subTest(label=label):
                original = (FIXTURES / filename).read_bytes()
                result = run_production_parser(request(label, profile, original), worker=worker)
                self.assertEqual("candidate_proposal", result.disposition, result.to_record())
                verify_result_record(result.to_record(), original)
                self.assertTrue(result.segments)
                direct = ExactSourceParserWorker().execute(request(label, profile, original))
                self.assertEqual(direct.outcome.segments, result.segments)
                self.assertEqual(direct.outcome.warnings, result.warnings)
                self.assertEqual(direct.outcome.transformations, result.transformations)
                assert worker.last_evidence is not None
                self.assertEqual("completed", worker.last_evidence.status)

    def test_pdf_remains_fail_closed_inside_sandbox(self) -> None:
        if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            self.skipTest("named Darwin sandbox-exec boundary unavailable")
        worker, _artifact = build_exact_darwin_sandbox_worker()
        original = (FIXTURES / "born-digital.pdf").read_bytes()
        execution = worker.execute(request("pdf", PDF_PROFILE, original))
        self.assertEqual("content_rejected", execution.status)
        self.assertEqual("pdf_exact_source_mapping_unsupported", execution.failure_code)
        self.assertEqual(0, execution.operation.worker_exit_code)
        self.assertIsNone(execution.outcome)
        assert worker.last_evidence is not None
        self.assertEqual("completed_content_rejection", worker.last_evidence.status)

    def test_cross_format_worker_failure_maps_to_quarantine_at_parser_boundary(self) -> None:
        if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            self.skipTest("named Darwin sandbox-exec boundary unavailable")
        worker, _artifact = build_exact_darwin_sandbox_worker()
        pdf = (FIXTURES / "strict-born-digital-valid.pdf").read_bytes()
        original = b"<html><body><!--" + pdf + b"--><p>x</p></body></html>"
        result = run_production_parser(request("polyglot", HTML_PROFILE, original), worker=worker)
        self.assertEqual("quarantined", result.disposition)
        self.assertEqual("rejected", result.adapter_status)
        self.assertEqual("cross_format_envelope_ambiguity", result.failure_code)
        self.assertEqual((), result.segments)
        verify_result_record(result.to_record(), original)


if __name__ == "__main__":
    unittest.main()
