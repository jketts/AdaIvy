"""Fail-closed contract tests for the optional exact-image OCI sandbox."""

from __future__ import annotations

import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from math_research.phase4b.exact_sandbox_bridge import (
    OCI_ARTIFACT_SCHEMA as EXACT_OCI_ARTIFACT_SCHEMA,
    build_exact_oci_sandbox_worker,
)
from math_research.phase4b.corpus_authorization import run_parser_corpus_authorization
from math_research.phase4b.oci_parser_sandbox import (
    OciParserSandboxWorker,
    OciRuntimeIdentity,
    OciSandboxLimits,
    RUNTIME_SCHEMA,
)
from math_research.phase4b.parsing import HTML_PROFILE, ParseRequest, run_production_parser
from math_research.phase4b.oci_sandbox_activation import (
    load_oci_sandbox_activation_evidence,
    run_oci_sandbox_activation_evidence,
    verify_oci_sandbox_activation_evidence,
)
from math_research.phase4b.pdf_sandbox_bridge import (
    OCI_ARTIFACT_SCHEMA as PDF_OCI_ARTIFACT_SCHEMA,
    build_pdf_oci_sandbox_worker,
)
from math_research.phase4b.serialization import canonical_bytes, canonical_hash


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "fixtures/phase4b/parsing/authoritative.html").read_bytes()


def _runtime() -> OciRuntimeIdentity:
    reference = "registry.example/approved/python@sha256:" + "1" * 64
    preimage = {
        "daemon_host": "unix:///tmp/approved-docker.sock",
        "docker_executable": "/opt/approved/docker",
        "docker_executable_sha256": "sha256:" + "2" * 64,
        "docker_server_sha256": "sha256:" + "3" * 64,
        "image_architecture": "arm64",
        "image_descriptor_digest": "sha256:" + "1" * 64,
        "image_id": "sha256:" + "4" * 64,
        "image_layers": ["sha256:" + "5" * 64],
        "image_os": "linux",
        "image_reference": reference,
        "platform": "linux/arm64",
        "schema_version": RUNTIME_SCHEMA,
    }
    return OciRuntimeIdentity(
        schema_version=RUNTIME_SCHEMA,
        docker_executable=preimage["docker_executable"],
        docker_executable_sha256=preimage["docker_executable_sha256"],
        daemon_host=preimage["daemon_host"],
        platform=preimage["platform"],
        image_reference=reference,
        image_descriptor_digest=preimage["image_descriptor_digest"],
        image_id=preimage["image_id"],
        image_os="linux",
        image_architecture="arm64",
        image_layers=tuple(preimage["image_layers"]),
        docker_server_sha256=preimage["docker_server_sha256"],
        environment_sha256=canonical_hash(preimage),
    )


def _request() -> ParseRequest:
    return ParseRequest.create(
        request_id="request.oci-sandbox",
        source_id="source.oci-sandbox",
        content_object_id="content.oci-sandbox",
        representation_id="representation.oci-sandbox",
        media_type=HTML_PROFILE.media_type,
        profile_name=HTML_PROFILE.name,
        original_bytes=HTML,
    )


class Phase4BOciParserSandboxTests(unittest.TestCase):
    def test_runtime_requires_exact_digest_unix_daemon_and_closed_platform(self) -> None:
        runtime = _runtime()
        record = runtime.to_record()
        self.assertEqual(runtime.environment_sha256, canonical_hash({
            key: value for key, value in record.items() if key != "environment_sha256"
        }))
        for changed in (
            {"image_reference": "registry.example/approved/python:latest"},
            {"daemon_host": "tcp://127.0.0.1:2375"},
            {"platform": "windows/amd64"},
        ):
            value = dict(record)
            value.update(changed)
            value["environment_sha256"] = canonical_hash({
                key: item for key, item in value.items() if key != "environment_sha256"
            })
            value["image_layers"] = tuple(value["image_layers"])
            with self.assertRaises(ValueError):
                OciRuntimeIdentity(**value)

    def test_run_command_has_exact_nonactivating_strict_controls(self) -> None:
        worker = OciParserSandboxWorker(
            name="test-worker", version="1", worker_source="raise SystemExit(0)",
            expected_runtime=_runtime(),
        )
        command = worker._command(Path("/tmp/cid"))
        expected = {
            "--interactive", "--pull=never", "--platform=linux/arm64",
            "--network=none", "--read-only", "--memory=536870912",
            "--memory-swap=536870912", "--pids-limit=16",
            "--ulimit=nofile=64:64", "--ulimit=fsize=67108864:67108864",
            "--ulimit=cpu=30:30", "--cpus=1.0", "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true", "--user=65534:65534",
            "--workdir=/tmp", "--env=LANG=C.UTF-8", "--entrypoint=python3",
        }
        self.assertTrue(expected <= set(command))
        self.assertTrue(any(item.startswith("--tmpfs=/tmp:rw,noexec,nosuid,nodev,") for item in command))
        self.assertFalse(any(item.startswith(("--mount", "--volume", "-v")) for item in command))
        self.assertNotIn(worker.worker_source, command)
        self.assertEqual(_runtime().image_reference, command[-5])
        self.assertEqual("external-os-sandbox-contract-v1", worker.sandbox_contract)

    def test_missing_or_changed_runtime_fails_before_container_launch(self) -> None:
        worker = OciParserSandboxWorker(
            name="test-worker", version="1", worker_source="raise SystemExit(0)",
            expected_runtime=_runtime(),
        )
        with patch.object(
            OciRuntimeIdentity, "measure", side_effect=ValueError("missing"),
        ), patch("math_research.phase4b.oci_parser_sandbox._bounded_process") as launch:
            execution = worker.execute(_request())
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_oci_runtime_unavailable", execution.failure_code)
        launch.assert_not_called()
        assert worker.last_evidence is not None
        self.assertFalse(worker.last_evidence.strict_transient_memory_enforcement)

    def test_oci_bridges_bind_same_source_semantics_to_runtime_and_policy(self) -> None:
        text_worker, text_artifact = build_exact_oci_sandbox_worker(
            expected_runtime=_runtime()
        )
        pdf_worker, pdf_artifact = build_pdf_oci_sandbox_worker(
            expected_runtime=_runtime()
        )
        self.assertEqual(EXACT_OCI_ARTIFACT_SCHEMA, text_artifact.schema_version)
        self.assertEqual(PDF_OCI_ARTIFACT_SCHEMA, pdf_artifact.schema_version)
        self.assertEqual(_runtime().environment_sha256, text_artifact.dependency_environment_sha256)
        self.assertEqual(_runtime().environment_sha256, pdf_artifact.dependency_environment_sha256)
        self.assertEqual(text_worker.policy_sha256, text_artifact.sandbox_policy_sha256)
        self.assertEqual(pdf_worker.policy_sha256, pdf_artifact.sandbox_policy_sha256)

    def test_limits_cannot_exceed_phase4b_ceiling(self) -> None:
        with self.assertRaisesRegex(ValueError, "parser ceiling"):
            OciSandboxLimits(max_memory_bytes=536_870_913)
        with self.assertRaisesRegex(ValueError, "parser ceiling"):
            OciSandboxLimits(max_processes=17)

    def test_exact_local_image_executes_and_cgroup_rejects_memory_overage(self) -> None:
        reference = os.environ.get("ADAIVY_PHASE4B_OCI_IMAGE")
        daemon = os.environ.get("ADAIVY_PHASE4B_OCI_DAEMON")
        executable = os.environ.get("ADAIVY_PHASE4B_OCI_DOCKER")
        if not reference or not daemon or not executable:
            self.skipTest("reviewed Phase 4B OCI runtime not explicitly configured")
        runtime = OciRuntimeIdentity.measure(
            docker_executable=Path(executable), daemon_host=daemon,
            image_reference=reference, platform="linux/arm64",
        )
        worker, _artifact = build_exact_oci_sandbox_worker(expected_runtime=runtime)
        result = run_production_parser(_request(), worker=worker)
        self.assertEqual("candidate_proposal", result.disposition, result.to_record())
        assert worker.last_evidence is not None
        self.assertTrue(worker.last_evidence.strict_transient_memory_enforcement)

        memory_worker = OciParserSandboxWorker(
            name="memory-probe", version="1",
            worker_source="allocation = bytearray(100_000_000)",
            expected_runtime=runtime,
            limits=OciSandboxLimits(
                max_memory_bytes=32 * 1_024 * 1_024,
                max_wall_seconds=5,
                max_cpu_seconds=5,
            ),
        )
        execution = memory_worker.execute(_request())
        self.assertEqual("sandbox_rejected", execution.status)
        self.assertEqual("sandbox_memory_limit_exceeded", execution.failure_code)
        assert memory_worker.last_evidence is not None
        self.assertTrue(memory_worker.last_evidence.oom_killed)

        corpus = run_parser_corpus_authorization(ROOT)
        report = run_oci_sandbox_activation_evidence(ROOT, corpus, runtime)
        attestation = verify_oci_sandbox_activation_evidence(report)
        self.assertEqual("authorized", attestation.status)
        self.assertEqual(("html", "pdf", "tex"), attestation.profiles_connected)
        self.assertTrue(attestation.strict_transient_memory_enforcement)
        self.assertEqual(
            report,
            load_oci_sandbox_activation_evidence(canonical_bytes(report)),
        )
        forged = copy.deepcopy(report)
        forged["counts"]["false_admissions"] = 1
        forged["content_hash"] = canonical_hash({
            key: value for key, value in forged.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "corpus counts"):
            verify_oci_sandbox_activation_evidence(forged)


if __name__ == "__main__":
    unittest.main()
