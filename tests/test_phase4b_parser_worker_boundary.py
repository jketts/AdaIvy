"""Fail-closed checks for the unactivated Phase 4B production worker port."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from math_research.phase4b.parsing import (
    HTML_PROFILE, OS_SANDBOX_LIMITATIONS, PRODUCTION_PARSER_STATUS,
    PRODUCTION_WORKER_DEPENDENCY_ID, ParseRequest, RestrictedStdlibAdapter,
    WorkerExecution, run_production_parser, verify_result_record,
)


ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "fixtures" / "phase4b" / "parsing" / "authoritative.html").read_bytes()


def request() -> ParseRequest:
    return ParseRequest.create(
        request_id="request.worker-boundary", source_id="source.worker-boundary",
        content_object_id="content.worker-boundary",
        representation_id="representation.worker-boundary",
        media_type=HTML_PROFILE.media_type, profile_name=HTML_PROFILE.name,
        original_bytes=HTML,
    )


class CapturedFixtureWorker:
    """Injected test double; its declaration is deliberately not activation evidence."""

    name = "test-captured-worker"
    version = "0.0.0"
    implementation_sha256 = "sha256:" + "1" * 64
    dependency_environment_sha256 = "sha256:" + "2" * 64
    sandbox_contract = "external-os-sandbox-contract-v1"

    def execute(self, parse_request: ParseRequest) -> WorkerExecution:
        outcome = RestrictedStdlibAdapter().parse(parse_request)
        return WorkerExecution.capture(
            outcome=outcome, operation_id="operation.test-captured-worker",
            duration_ms=7, worker_exit_code=0,
            stdout=b"bounded worker stdout", stderr=b"bounded worker stderr",
        )


class Phase4BParserWorkerBoundaryTests(unittest.TestCase):
    def test_no_worker_is_activated_by_default_and_returns_missing_dependency(self) -> None:
        result = run_production_parser(request())
        self.assertEqual(result.disposition, "failed")
        self.assertEqual(
            result.failure_code, f"missing_dependency:{PRODUCTION_WORKER_DEPENDENCY_ID}"
        )
        self.assertEqual(result.adapter_status, "missing_dependency")
        self.assertEqual(result.parser_identity["adapter_name"], "none")
        self.assertEqual(result.segments, ())
        verify_result_record(result.to_record(), HTML)

    def test_explicit_worker_outcome_captures_hashes_exit_and_duration(self) -> None:
        result = run_production_parser(request(), worker=CapturedFixtureWorker())
        self.assertEqual(result.disposition, "candidate_proposal")
        self.assertEqual(result.parser_identity["adapter_name"], "test-captured-worker")
        self.assertEqual(result.operation.duration_ms, 7)
        self.assertEqual(result.operation.worker_exit_code, 0)
        self.assertEqual(result.operation.stdout_byte_length, 21)
        self.assertEqual(result.operation.stderr_byte_length, 21)
        self.assertEqual(
            result.operation.stdout_sha256,
            "sha256:" + hashlib.sha256(b"bounded worker stdout").hexdigest(),
        )
        self.assertEqual(
            result.operation.stderr_sha256,
            "sha256:" + hashlib.sha256(b"bounded worker stderr").hexdigest(),
        )
        verify_result_record(result.to_record(), HTML)

    def test_sandbox_rejection_exposes_no_candidate_content(self) -> None:
        class RejectedWorker(CapturedFixtureWorker):
            def execute(self, parse_request: ParseRequest) -> WorkerExecution:
                return WorkerExecution.capture(
                    outcome=None, operation_id="operation.test-sandbox-rejection",
                    status="sandbox_rejected", failure_code="sandbox_write_escape_denied",
                    duration_ms=2, worker_exit_code=126, stderr=b"denied",
                )

        result = run_production_parser(request(), worker=RejectedWorker())
        self.assertEqual(result.disposition, "quarantined")
        self.assertEqual(result.failure_code, "sandbox_write_escape_denied")
        self.assertEqual(result.segments, ())
        self.assertEqual(result.references, ())
        verify_result_record(result.to_record(), HTML)

    def test_content_rejection_is_distinct_from_worker_failure(self) -> None:
        class UnsuccessfulWorker(CapturedFixtureWorker):
            status = "failed"

            def execute(self, parse_request: ParseRequest) -> WorkerExecution:
                return WorkerExecution.capture(
                    outcome=None, operation_id=f"operation.test.{self.status}",
                    status=self.status, failure_code="closed_reason",
                    duration_ms=1, worker_exit_code=0,
                )

        rejected = UnsuccessfulWorker()
        rejected.status = "content_rejected"
        quarantined = run_production_parser(request(), worker=rejected)
        self.assertEqual("quarantined", quarantined.disposition)
        self.assertEqual("rejected", quarantined.adapter_status)
        self.assertEqual((), quarantined.segments)

        failed = run_production_parser(request(), worker=UnsuccessfulWorker())
        self.assertEqual("failed", failed.disposition)
        self.assertEqual("failed", failed.adapter_status)
        self.assertEqual((), failed.segments)

    def test_repository_makes_no_portable_os_sandbox_claim(self) -> None:
        self.assertEqual(
            PRODUCTION_PARSER_STATUS,
            "disabled_pending_pinned_worker_and_os_sandbox",
        )
        self.assertEqual(len(OS_SANDBOX_LIMITATIONS), 4)
        self.assertTrue(any("strict subsets" in item for item in OS_SANDBOX_LIMITATIONS))
        self.assertTrue(any("not production" in item for item in OS_SANDBOX_LIMITATIONS))
        self.assertTrue(any("portable" in item for item in OS_SANDBOX_LIMITATIONS))
        self.assertTrue(any("not strict" in item for item in OS_SANDBOX_LIMITATIONS))


if __name__ == "__main__":
    unittest.main()
