"""Measured resource controls for the parser-connected Darwin sandbox."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import unittest
from unittest.mock import patch

from math_research.phase4b.parser_sandbox import (
    CONTRACT_VERSION, DarwinResourceSandboxWorker, SandboxLimits, _kill_worker, _profile,
    measured_runtime_identity,
)
from math_research.phase4b.parsing import (
    HTML_PROFILE, ParseRequest, run_production_parser, verify_result_record,
)


ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "fixtures" / "phase4b" / "parsing" / "authoritative.html").read_bytes()


VALID_WORKER = r'''
import base64, hashlib, json, sys
request = json.loads(sys.stdin.buffer.read())
original = base64.b64decode(request["original_bytes_base64"], validate=True)
original_hash = "sha256:" + hashlib.sha256(original).hexdigest()
anchor = {
    "end": 1, "object_id": None, "original_sha256": original_hash,
    "page_index": None,
    "slice_sha256": "sha256:" + hashlib.sha256(original[:1]).hexdigest(),
    "start": 0,
}
outcome = {
    "references": [],
    "segments": [{
        "anchor": anchor, "kind": "text", "load_bearing": False,
        "normalized_text": original[:1].decode("ascii"),
        "segment_id": "segment.sandbox.fixture",
    }],
    "transformations": ["identity"], "warnings": [],
}
sys.stdout.write(json.dumps({
    "outcome": outcome, "schema_version": "phase4b-parser-worker-response-v2",
    "status": "completed",
}, sort_keys=True, separators=(",", ":")))
'''


def request() -> ParseRequest:
    return ParseRequest.create(
        request_id="request.resource-sandbox", source_id="source.resource-sandbox",
        content_object_id="content.resource-sandbox",
        representation_id="representation.resource-sandbox",
        media_type=HTML_PROFILE.media_type, profile_name=HTML_PROFILE.name,
        original_bytes=HTML,
    )


def worker(source: str = VALID_WORKER, *, limits: SandboxLimits | None = None) -> DarwinResourceSandboxWorker:
    return DarwinResourceSandboxWorker(
        name="test-pinned-parser", version="0.0.0", worker_source=source,
        expected_dependency_environment_sha256=measured_runtime_identity(), limits=limits,
    )


class Phase4BParserResourceSandboxTests(unittest.TestCase):
    def require_darwin(self) -> None:
        if platform.system() != "Darwin" or not Path("/usr/bin/sandbox-exec").is_file():
            self.skipTest("named Darwin sandbox-exec boundary unavailable")

    def test_unavailable_named_platform_fails_closed_or_darwin_executes(self) -> None:
        execution = worker().execute(request())
        self.assertIn(execution.status, {"completed", "sandbox_rejected"})
        if platform.system() != "Darwin":
            expected = (
                "sandbox_privileged_identity_rejected"
                if hasattr(os, "geteuid") and os.geteuid() == 0
                else "sandbox_named_platform_unavailable"
            )
            self.assertEqual(expected, execution.failure_code)
            self.assertIsNone(execution.outcome)

    def test_connected_worker_yields_valid_candidate_and_measured_evidence(self) -> None:
        self.require_darwin()
        sandbox = worker()
        result = run_production_parser(request(), worker=sandbox)
        self.assertEqual("candidate_proposal", result.disposition, result.to_record())
        verify_result_record(result.to_record(), HTML)
        evidence = sandbox.last_evidence
        assert evidence is not None
        self.assertEqual(CONTRACT_VERSION, evidence.schema_version)
        self.assertEqual("completed", evidence.status)
        self.assertGreaterEqual(evidence.wall_milliseconds, 0)
        self.assertGreaterEqual(evidence.cpu_milliseconds, 0)
        self.assertGreater(evidence.sampled_peak_resident_bytes, 0)
        self.assertEqual(
            "parent_sampled_rss_tripwire_not_strict",
            evidence.limit_enforcement["max_memory_bytes"],
        )
        self.assertEqual(
            "sandbox_process_fork_deny",
            evidence.limit_enforcement["max_processes"],
        )
        self.assertGreater(evidence.stdout_bytes_observed, 0)
        self.assertEqual(0, evidence.stderr_bytes_observed)
        self.assertEqual(sandbox.implementation_sha256, evidence.worker_source_sha256)
        self.assertEqual(
            measured_runtime_identity(), evidence.dependency_environment_sha256,
        )
        self.assertEqual(
            "sha256:" + hashlib.sha256(VALID_WORKER.encode()).hexdigest(),
            sandbox.implementation_sha256,
        )
        json.dumps(evidence.to_record(), sort_keys=True, separators=(",", ":"))

    def test_protocol_distinguishes_content_rejection_from_worker_failure(self) -> None:
        self.require_darwin()
        template = r'''
import json, sys
sys.stdin.buffer.read()
sys.stdout.write(json.dumps({
    "failure_code": "__FAILURE_CODE__",
    "schema_version": "phase4b-parser-worker-response-v2",
    "status": "__STATUS__",
}, sort_keys=True, separators=(",", ":")))
'''
        rejected_worker = worker(
            template.replace("__STATUS__", "rejected").replace(
                "__FAILURE_CODE__", "html_active_content_forbidden",
            )
        )
        rejected_execution = rejected_worker.execute(request())
        self.assertEqual("content_rejected", rejected_execution.status)
        rejected_result = run_production_parser(request(), worker=rejected_worker)
        self.assertEqual("quarantined", rejected_result.disposition)
        self.assertEqual("rejected", rejected_result.adapter_status)
        self.assertEqual((), rejected_result.segments)

        failed_worker = worker(
            template.replace("__STATUS__", "failed").replace(
                "__FAILURE_CODE__", "parser_internal_failure",
            )
        )
        failed_execution = failed_worker.execute(request())
        self.assertEqual("failed", failed_execution.status)
        failed_result = run_production_parser(request(), worker=failed_worker)
        self.assertEqual("failed", failed_result.disposition)
        self.assertEqual("failed", failed_result.adapter_status)
        self.assertEqual((), failed_result.segments)

    def test_parent_enforces_stdout_ceiling_and_discards_candidate(self) -> None:
        self.require_darwin()
        sandbox = worker(
            "import sys; sys.stdout.write('x' * 100000)",
            limits=SandboxLimits(max_stdout_bytes=1_024),
        )
        execution = sandbox.execute(request())
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_stdout_limit_exceeded", execution.failure_code)
        self.assertIsNone(execution.outcome)
        self.assertEqual(1_024, execution.stdout_byte_length)
        assert sandbox.last_evidence is not None
        self.assertEqual(1_024, sandbox.last_evidence.limits["max_stdout_bytes"])

    def test_parent_wall_deadline_kills_worker_group(self) -> None:
        self.require_darwin()
        sandbox = worker(
            "while True: pass",
            limits=SandboxLimits(max_wall_seconds=1, max_cpu_seconds=2),
        )
        execution = sandbox.execute(request())
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_wall_time_exceeded", execution.failure_code)
        self.assertIsNone(execution.outcome)
        self.assertLess(execution.operation.duration_ms, 3_000)
        assert sandbox.last_evidence is not None
        self.assertGreater(sandbox.last_evidence.cpu_milliseconds, 0)

    def test_kernel_cpu_limit_terminates_busy_worker_before_wall_deadline(self) -> None:
        self.require_darwin()
        sandbox = worker(
            "while True: pass",
            limits=SandboxLimits(max_wall_seconds=3, max_cpu_seconds=1),
        )
        execution = sandbox.execute(request())
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_cpu_limit_exceeded", execution.failure_code)
        self.assertLess(execution.operation.duration_ms, 3_000)
        assert sandbox.last_evidence is not None
        self.assertGreaterEqual(sandbox.last_evidence.cpu_milliseconds, 750)

    def test_sampled_resident_memory_tripwire_rejects_observed_overage(self) -> None:
        self.require_darwin()
        sandbox = worker(
            "import time; allocation = bytearray(100_000_000); time.sleep(5)",
            limits=SandboxLimits(
                max_wall_seconds=3, max_memory_bytes=32 * 1_024 * 1_024,
            ),
        )
        execution = sandbox.execute(request())
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_sampled_memory_limit_exceeded", execution.failure_code)
        assert sandbox.last_evidence is not None
        self.assertGreater(
            sandbox.last_evidence.sampled_peak_resident_bytes,
            sandbox.last_evidence.limits["max_memory_bytes"],
        )

    def test_dependency_environment_claim_must_equal_measured_runtime(self) -> None:
        with self.assertRaisesRegex(ValueError, "measured runtime identity"):
            DarwinResourceSandboxWorker(
                name="test-pinned-parser", version="0.0.0",
                worker_source=VALID_WORKER,
                expected_dependency_environment_sha256="sha256:" + "0" * 64,
            )

    def test_privileged_effective_identity_is_rejected_before_launch(self) -> None:
        sandbox = worker()
        with patch("math_research.phase4b.parser_sandbox.os.geteuid", return_value=0):
            execution = sandbox.execute(request())
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_privileged_identity_rejected", execution.failure_code)
        self.assertIsNone(execution.operation.worker_exit_code)

    def test_any_root_user_or_group_identity_is_rejected_before_launch(self) -> None:
        for function in ("getuid", "geteuid", "getgid", "getegid"):
            with self.subTest(function=function), patch(
                f"math_research.phase4b.parser_sandbox.os.{function}", return_value=0,
            ):
                execution = worker().execute(request())
            self.assertEqual("sandbox_rejected", execution.status)
            self.assertEqual("sandbox_privileged_identity_rejected", execution.failure_code)
        with patch(
            "math_research.phase4b.parser_sandbox.os.getgroups", return_value=[20, 0],
        ):
            execution = worker().execute(request())
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_privileged_identity_rejected", execution.failure_code)

    def test_profile_has_no_broad_mach_or_process_information_allowance(self) -> None:
        profile = _profile(Path(sys.base_prefix).resolve())
        self.assertNotIn("(allow mach-lookup)", profile)
        self.assertNotIn("process-info", profile)

    def test_kernel_open_file_limit_is_applied_to_worker(self) -> None:
        self.require_darwin()
        source = r'''
import os
handles = []
try:
    for _ in range(100):
        handles.append(open("/dev/null", "rb"))
except OSError:
    os._exit(73)
os._exit(74)
'''
        sandbox = worker(source, limits=SandboxLimits(max_open_files=16))
        execution = sandbox.execute(request())
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_worker_failed", execution.failure_code)
        self.assertEqual(73, execution.operation.worker_exit_code)
        assert sandbox.last_evidence is not None
        self.assertEqual(16, sandbox.last_evidence.limits["max_open_files"])

    def test_os_profile_denies_worker_network_and_process_creation(self) -> None:
        self.require_darwin()
        sources = {
            "network": "import socket; socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'x', ('127.0.0.1', 9))",
            "process": "import subprocess, sys; subprocess.run((sys.executable, '-c', 'pass'))",
            "unapproved_read": "open('/bin/sh', 'rb').read(1)",
            "configuration_read": "open('/etc/passwd', 'rb').read(1)",
            "workspace_read": f"open({str(ROOT / 'README.md')!r}, 'rb').read(1)",
            "filesystem_write": "open('worker-output', 'wb').write(b'x')",
        }
        for name, source in sources.items():
            with self.subTest(name=name):
                execution = worker(source).execute(request())
                self.assertEqual("sandbox_rejected", execution.status)
                self.assertEqual("sandbox_worker_failed", execution.failure_code)
                self.assertIsNone(execution.outcome)

    def test_limits_cannot_exceed_sealed_parser_bounds(self) -> None:
        with self.assertRaisesRegex(ValueError, "sealed parser ceiling"):
            SandboxLimits(max_open_files=65)
        with self.assertRaisesRegex(ValueError, "sealed parser ceiling"):
            SandboxLimits(max_processes=2)

    def test_group_kill_permission_race_falls_back_to_direct_child(self) -> None:
        process = unittest.mock.Mock()
        process.pid = 123
        process.poll.return_value = None
        with patch(
            "math_research.phase4b.parser_sandbox.os.killpg",
            side_effect=PermissionError,
        ):
            _kill_worker(process)
        process.kill.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
