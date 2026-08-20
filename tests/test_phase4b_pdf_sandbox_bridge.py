"""Concrete, non-activating strict-PDF bridge into the Darwin sandbox."""

from __future__ import annotations

import hashlib
from pathlib import Path
import platform
import unittest
from unittest.mock import patch

from math_research.phase4b.parsing import PDF_PROFILE, ParseRequest, run_production_parser
from math_research.phase4b.pdf_exact_candidate import (
    IMPLEMENTATION_SHA256,
    StrictBornDigitalPdfAdapter,
)
from math_research.phase4b.pdf_sandbox_bridge import (
    ARTIFACT_SCHEMA,
    build_pdf_darwin_sandbox_worker,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "phase4b" / "parsing"


def _request(label: str, original: bytes) -> ParseRequest:
    return ParseRequest.create(
        request_id=f"request.pdf-bridge.{label}",
        source_id=f"source.pdf-bridge.{label}",
        content_object_id=f"content.pdf-bridge.{label}",
        representation_id=f"representation.pdf-bridge.{label}",
        media_type=PDF_PROFILE.media_type,
        profile_name=PDF_PROFILE.name,
        original_bytes=original,
    )


class StrictPdfSandboxBridgeTests(unittest.TestCase):
    def test_artifact_binds_pdf_semantics_composed_source_protocol_and_runtime(self) -> None:
        first, first_artifact = build_pdf_darwin_sandbox_worker()
        second, second_artifact = build_pdf_darwin_sandbox_worker()
        self.assertEqual(first_artifact, second_artifact)
        self.assertEqual(ARTIFACT_SCHEMA, first_artifact.schema_version)
        self.assertEqual("phase4b-parser-worker-response-v2", first_artifact.protocol_schema)
        self.assertEqual(IMPLEMENTATION_SHA256, first_artifact.pdf_parser_source_sha256)
        self.assertEqual(first.implementation_sha256, first_artifact.worker_source_sha256)
        self.assertEqual(first.worker_source, second.worker_source)
        self.assertEqual(
            "sha256:" + hashlib.sha256(first.worker_source.encode("utf-8")).hexdigest(),
            first_artifact.worker_source_sha256,
        )
        self.assertNotIn(str(ROOT), first.worker_source)
        self.assertNotIn("math_research", first.worker_source)
        self.assertNotIn("pdf_exact_candidate", first.worker_source)

    def test_non_darwin_fails_closed_without_launch(self) -> None:
        worker, _artifact = build_pdf_darwin_sandbox_worker()
        original = (FIXTURES / "strict-born-digital-valid.pdf").read_bytes()
        with patch("math_research.phase4b.parser_sandbox.platform.system", return_value="Linux"):
            execution = worker.execute(_request("unavailable", original))
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_named_platform_unavailable", execution.failure_code)
        self.assertIsNone(execution.outcome)

    def test_darwin_worker_has_exact_semantic_equality_with_direct_candidate(self) -> None:
        if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            self.skipTest("named Darwin sandbox-exec boundary unavailable")
        worker, artifact = build_pdf_darwin_sandbox_worker()
        original = (FIXTURES / "strict-born-digital-valid.pdf").read_bytes()
        request = _request("valid", original)
        direct = StrictBornDigitalPdfAdapter().parse(request)
        execution = worker.execute(request)
        self.assertEqual("completed", execution.status, execution)
        self.assertEqual(direct, execution.outcome)
        result = run_production_parser(request, worker=worker)
        self.assertEqual("candidate_proposal", result.disposition, result.to_record())
        self.assertEqual(direct.segments, result.segments)
        self.assertEqual(direct.warnings, result.warnings)
        self.assertEqual(direct.transformations, result.transformations)
        self.assertEqual(artifact.worker_source_sha256, worker.implementation_sha256)
        assert worker.last_evidence is not None
        self.assertEqual("completed", worker.last_evidence.status)
        self.assertEqual(artifact.worker_source_sha256, worker.last_evidence.worker_source_sha256)
        self.assertEqual(
            artifact.dependency_environment_sha256,
            worker.last_evidence.dependency_environment_sha256,
        )

    def test_darwin_worker_preserves_closed_parser_failure_code(self) -> None:
        if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            self.skipTest("named Darwin sandbox-exec boundary unavailable")
        worker, _artifact = build_pdf_darwin_sandbox_worker()
        original = (FIXTURES / "hostile.pdf").read_bytes()
        execution = worker.execute(_request("invalid", original))
        self.assertEqual("content_rejected", execution.status)
        self.assertEqual(
            "pdf_incremental_or_ambiguous_revision_forbidden",
            execution.failure_code,
        )
        self.assertEqual(0, execution.operation.worker_exit_code)
        self.assertIsNone(execution.outcome)
        assert worker.last_evidence is not None
        self.assertEqual("completed_content_rejection", worker.last_evidence.status)
        self.assertEqual(execution.failure_code, worker.last_evidence.failure_code)

    def test_cross_format_pdf_worker_failure_maps_to_quarantine(self) -> None:
        if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            self.skipTest("named Darwin sandbox-exec boundary unavailable")
        worker, _artifact = build_pdf_darwin_sandbox_worker()
        original = (FIXTURES / "strict-born-digital-valid.pdf").read_bytes().replace(
            b"Pythagorean identity", b"\\section{H}$x$      ", 1,
        )
        self.assertEqual(
            len((FIXTURES / "strict-born-digital-valid.pdf").read_bytes()), len(original),
        )
        result = run_production_parser(_request("polyglot", original), worker=worker)
        self.assertEqual("quarantined", result.disposition)
        self.assertEqual("rejected", result.adapter_status)
        self.assertEqual("cross_format_envelope_ambiguity", result.failure_code)
        self.assertEqual((), result.segments)


if __name__ == "__main__":
    unittest.main()
