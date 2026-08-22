"""Offline acceptance tests for the ADR-0066 experiment sandbox."""

from __future__ import annotations

from dataclasses import replace
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest

from math_research.campaign.experiment_sandbox.activation import (
    PROBE_IDS,
    REPORT_SCHEMA,
    load_campaign_experiment_activation,
    verify_campaign_experiment_activation,
)
from math_research.campaign.experiment_sandbox.attestation import (
    ACTIVATION_SCHEMA,
    SandboxActivation,
)
from math_research.campaign.experiment_sandbox.image_lock import (
    CAMPAIGN_RUNTIME_ROLE,
    PHASE4B_RUNTIME_ROLE,
    load_campaign_image_lock,
    load_phase4b_image_lock,
)
from math_research.campaign.experiment_sandbox.runner import (
    ADAPTER_ID,
    ActivatedCampaignExperimentRunner,
    CampaignSandboxRunnerError,
    ExactGraphCampaignVerifier,
    build_activated_campaign_experiment_runner,
    limits_from_request,
)
from math_research.campaign.experiment_sandbox.sandbox import (
    BOOTSTRAP_SHA256,
    CampaignSandboxLimits,
    OciExperimentSandbox,
    SandboxExecution,
    SandboxOutcome,
    SandboxProgramRequest,
)
from math_research.campaign.experiment_sandbox.verifier import (
    load_target,
    trust_block,
    verify_candidate,
)
from math_research.campaign.records import RecordStatus
from math_research.campaign.records import canonical_bytes, canonical_hash
from math_research.campaign.runner import ExperimentRequest, ResourceLimits, VerificationRequest
from math_research.phase4b.oci_parser_sandbox import OciRuntimeIdentity

ROOT = Path(__file__).resolve().parent.parent
TARGET_BYTES = (ROOT / "fixtures/campaign-experiment/target-exact-graph-distance-spectrum-v1.json").read_bytes()
TARGET = load_target(TARGET_BYTES)


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def candidate(edges, **changes) -> bytes:
    value = {
        "asserted_construction": "fixture",
        "asserted_satisfies_target": True,
        "edges": edges,
        "order": 10,
        "schema_version": "adaivy.campaign-experiment-graph-candidate.v1",
        "target_id": TARGET.target_id,
    }
    value.update(changes)
    return canonical_bytes(value)


PETERSEN = [
    [0, 1], [0, 4], [0, 5], [1, 2], [1, 6], [2, 3], [2, 7], [3, 4],
    [3, 8], [4, 9], [5, 7], [5, 8], [6, 8], [6, 9], [7, 9],
]
PRISM = [
    [0, 1], [0, 4], [0, 5], [1, 2], [1, 6], [2, 3], [2, 7], [3, 4],
    [3, 8], [4, 9], [5, 6], [5, 9], [6, 7], [7, 8], [8, 9],
]


def fake_runtime(lock) -> OciRuntimeIdentity:
    preimage = {
        "daemon_host": "unix:///tmp/adaivy-docker.sock",
        "docker_executable": "/usr/local/bin/docker",
        "docker_executable_sha256": digest(b"docker"),
        "docker_server_sha256": digest(b"server"),
        "image_architecture": "arm64",
        "image_descriptor_digest": lock.oci_index_digest,
        "image_id": lock.oci_index_digest,
        "image_layers": [digest(b"layer")],
        "image_os": "linux",
        "image_reference": lock.image_reference,
        "platform": "linux/arm64",
        "schema_version": "adaivy.phase4b-oci-runtime-identity.v1",
    }
    return OciRuntimeIdentity(
        **{**preimage, "image_layers": tuple(preimage["image_layers"]),
           "environment_sha256": canonical_hash(preimage)}
    )


class ImageAndCommandTests(unittest.TestCase):
    def test_shared_digest_has_distinct_closed_roles(self):
        campaign = load_campaign_image_lock(ROOT)
        parser = load_phase4b_image_lock(ROOT)
        self.assertEqual(campaign.image_reference, parser.image_reference)
        self.assertEqual(CAMPAIGN_RUNTIME_ROLE, campaign.runtime_role)
        self.assertEqual(PHASE4B_RUNTIME_ROLE, parser.runtime_role)

    def test_command_has_every_kernel_control_and_no_mount(self):
        lock = load_campaign_image_lock(ROOT)
        sandbox = OciExperimentSandbox(expected_runtime=fake_runtime(lock), image_lock=lock)
        command = sandbox.command(Path("/tmp/cid"))
        for flag in (
            "--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true", "--user=65534:65534",
            "--env=PYTHONHASHSEED=0",
        ):
            self.assertIn(flag, command)
        self.assertTrue(any(item.startswith("--memory=") for item in command))
        self.assertTrue(any(item.startswith("--pids-limit=") for item in command))
        tmpfs = next(item for item in command if item.startswith("--tmpfs=/tmp:"))
        self.assertIn("noexec,nosuid,nodev", tmpfs)
        self.assertIn("nr_inodes=128", tmpfs)
        self.assertFalse(any(item.startswith("--volume") or item.startswith("--mount") for item in command))
        self.assertNotIn("sh", command)

    def test_program_is_bounded_hashed_stdin_not_command_text(self):
        lock = load_campaign_image_lock(ROOT)
        sandbox = OciExperimentSandbox(expected_runtime=fake_runtime(lock), image_lock=lock)
        source = b"print('secret program marker')\n"
        request = SandboxProgramRequest(program_source=source, program_artifact_hash=digest(source))
        self.assertNotIn("secret program marker", " ".join(sandbox.command(Path("/tmp/cid"))))
        payload = json.loads(sandbox.stdin_payload(request))
        self.assertEqual(digest(source), payload["program_artifact_hash"])
        with self.assertRaisesRegex(ValueError, "hash_mismatch"):
            sandbox.stdin_payload(replace(request, program_artifact_hash=digest(b"other")))


class ExactVerifierTests(unittest.TestCase):
    def test_exact_candidate_is_rederived_and_grants_no_warrant(self):
        verdict = verify_candidate(TARGET, candidate(PETERSEN))
        self.assertEqual("target_satisfied", verdict.verdict)
        self.assertTrue(all(item["satisfied"] for item in verdict.conditions))
        self.assertEqual(False, verdict.to_record()["trust"]["epistemic_warrant_created"])
        self.assertEqual(False, verdict.to_record()["trust"]["graph_admission"])

    def test_lying_candidate_is_refuted(self):
        verdict = verify_candidate(TARGET, candidate(PRISM))
        self.assertEqual("target_not_satisfied", verdict.verdict)
        self.assertTrue(verdict.claim_refuted)
        failed = {item["condition"] for item in verdict.conditions if not item["satisfied"]}
        self.assertEqual({"distinct_distance_eigenvalues", "inverse_even"}, failed)

    def test_float_measurement_and_trust_assertions_are_refused(self):
        measured = json.loads(candidate(PETERSEN))
        measured["cpu_seconds"] = 1
        self.assertEqual(
            "program_asserted_measurement",
            verify_candidate(TARGET, canonical_bytes(measured)).refusal_code,
        )
        trusted = json.loads(candidate(PETERSEN))
        trusted["proved"] = True
        self.assertEqual(
            "program_asserted_trust_status",
            verify_candidate(TARGET, canonical_bytes(trusted)).refusal_code,
        )
        floated = candidate(PETERSEN).replace(b'"order":10', b'"order":10.0')
        self.assertEqual("float_on_the_trust_path", verify_candidate(TARGET, floated).refusal_code)

    def test_verifier_module_has_no_execution_or_network_import(self):
        path = ROOT / "src/math_research/campaign/experiment_sandbox/verifier.py"
        tree = ast.parse(path.read_text("utf-8"))
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertTrue(imported.isdisjoint({"os", "subprocess", "socket", "ctypes"}))


class ActivationReplayTests(unittest.TestCase):
    def report(self):
        return copy.deepcopy(json.loads(
            (ROOT / "reports/campaign-experiment-sandbox/v1/activation.json").read_text()
        ))

    def test_all_sixteen_named_probes_are_required(self):
        report = self.report()
        attestation = verify_campaign_experiment_activation(report)
        self.assertTrue(attestation.activated)
        self.assertEqual(16, attestation.probes_total)
        loaded, replayed = load_campaign_experiment_activation(canonical_bytes(report))
        self.assertEqual(report, loaded)
        self.assertEqual(attestation, replayed)

    def test_deleted_reordered_and_rehashed_probe_fail_closed(self):
        for mutate in (
            lambda x: x["probes"].pop(),
            lambda x: x["probes"].reverse(),
            lambda x: x["probes"][0].update(passed=False),
        ):
            report = self.report()
            mutate(report)
            with self.assertRaises(ValueError):
                verify_campaign_experiment_activation(report)

        forged = self.report()
        forged["probes"][0]["observation"]["status"] = "refused"
        forged["probes"][0]["content_hash"] = canonical_hash({
            key: item for key, item in forged["probes"][0].items()
            if key != "content_hash"
        })
        forged["content_hash"] = canonical_hash({
            key: item for key, item in forged.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "did not demonstrate"):
            verify_campaign_experiment_activation(forged)

    def test_recorded_activation_builds_the_production_port_without_execution(self):
        report, activation = load_campaign_experiment_activation(
            (ROOT / "reports/campaign-experiment-sandbox/v1/activation.json").read_bytes()
        )
        runtime_record = dict(report["environment"])
        runtime_record["image_layers"] = tuple(runtime_record["image_layers"])
        runtime = OciRuntimeIdentity(**runtime_record)
        runner = build_activated_campaign_experiment_runner(
            repository_root=ROOT, runtime=runtime, activation=activation,
            target_hash=TARGET.target_hash,
        )
        self.assertTrue(runner.activation.activated)


class FakeSandbox:
    def __init__(self, limits, activation, *, fail=False):
        self.limits = limits
        self.policy_sha256 = digest(b"full-policy")
        self.control_policy_sha256 = activation.policy_hash
        self.bootstrap_sha256 = activation.bootstrap_hash
        self.environment_sha256 = activation.environment_hash
        self.fail = fail
        self.requests = []

    def configuration_record(self):
        return {"limits": self.limits.to_record(), "fixture": True}

    def run(self, request):
        self.requests.append(request)
        outcome = SandboxOutcome(
            status="program_failed" if self.fail else "completed",
            refusal_code="program_nonzero_exit" if self.fail else None,
            result=None if self.fail else candidate(PETERSEN), result_bytes_observed=0,
            result_truncated=False, stdout=b"", stdout_bytes_observed=0,
            stdout_truncated=False, stderr=b"", stderr_bytes_observed=0,
            stderr_truncated=False, container_exit_code=0,
            child_exit_code=1 if self.fail else 0, child_signal=None,
            oom_killed=False, wall_timed_out=False,
            container_stdout_bytes_observed=0, container_stderr=b"",
            wall_milliseconds=3,
        )
        return SandboxExecution(
            status=outcome.status, refusal_code=outcome.refusal_code,
            replicas=(outcome, outcome), deterministic=True, outcome=outcome,
        )


def attestation() -> SandboxActivation:
    return SandboxActivation(
        schema_version=ACTIVATION_SCHEMA, status="activated",
        environment_hash=digest(b"env"), policy_hash=digest(b"policy"),
        bootstrap_hash=BOOTSTRAP_SHA256,
        campaign_lock_sha256=digest(b"campaign"), phase4b_lock_sha256=digest(b"phase4b"),
        target_hash=TARGET.target_hash, probes_total=16, probes_flipped=16,
        probes_blocked=0, content_hash=digest(b"activation"),
    )


def experiment_request(**changes):
    source = b"print('bounded')\n"
    value = dict(
        campaign_id="campaign.test", action_id="action.3", tool_id=ADAPTER_ID,
        program_artifact_hash=digest(source), program_source=source,
        input_artifacts=(), arguments=(),
        resource_limits=ResourceLimits(
            cpu_milliseconds=10_000, wall_milliseconds=30_000,
            memory_bytes=268_435_456, output_bytes=65_536, process_count=7,
        ), network="none",
    )
    value.update(changes)
    return ExperimentRequest(**value)


class CampaignPortTests(unittest.TestCase):
    def test_runner_maps_exact_limits_and_returns_untrusted_candidate(self):
        activation = attestation()
        created = []
        def factory(limits):
            sandbox = FakeSandbox(limits, activation)
            created.append(sandbox)
            return sandbox
        runner = ActivatedCampaignExperimentRunner(
            sandbox_factory=factory, activation=activation, target_hash=TARGET.target_hash,
        )
        result = runner(experiment_request())
        self.assertEqual(RecordStatus.COMPLETED, result.status)
        self.assertEqual(candidate(PETERSEN), result.result)
        self.assertEqual(1, len(created[0].requests))
        self.assertIsNone(result.cpu_milliseconds)
        self.assertIsNone(result.peak_memory_bytes)

    def test_runner_refuses_wrong_adapter_network_and_unenforceable_bounds(self):
        activation = attestation()
        calls = []
        def factory(limits):
            calls.append(limits)
            return FakeSandbox(limits, activation)
        runner = ActivatedCampaignExperimentRunner(
            sandbox_factory=factory, activation=activation, target_hash=TARGET.target_hash,
        )
        for request in (
            experiment_request(tool_id="shell"),
            experiment_request(network="egress"),
            experiment_request(resource_limits=replace(
                experiment_request().resource_limits, cpu_milliseconds=999,
            )),
        ):
            with self.assertRaises(CampaignSandboxRunnerError):
                runner(request)
        self.assertEqual([], calls)

    def test_failed_execution_is_a_deterministic_failed_result(self):
        activation = attestation()
        runner = ActivatedCampaignExperimentRunner(
            sandbox_factory=lambda limits: FakeSandbox(limits, activation, fail=True),
            activation=activation, target_hash=TARGET.target_hash,
        )
        first = runner(experiment_request())
        second = runner(experiment_request())
        self.assertEqual(RecordStatus.FAILED, first.status)
        self.assertEqual(first.result, second.result)

    def test_exact_verifier_receives_selection_and_ignores_tool_narrative(self):
        data = candidate(PETERSEN)
        request = VerificationRequest(
            campaign_id="campaign.test", action_id="action.5",
            target_hash=TARGET.target_hash,
            candidate_artifact=(digest(data), data),
            tool_artifacts=((digest(b"a confident lie"), b"a confident lie"),),
        )
        result = ExactGraphCampaignVerifier(target=TARGET)(request)
        self.assertEqual(RecordStatus.COMPLETED, result.status)
        record = json.loads(result.result)
        self.assertEqual("target_satisfied", record["verdict"])
        self.assertEqual(False, record["trust"]["epistemic_warrant_created"])


if __name__ == "__main__":
    unittest.main()
