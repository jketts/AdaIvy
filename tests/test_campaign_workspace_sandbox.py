"""Offline acceptance tests for the ADR-0082 v2 workspace sandbox.

No container runtime: container execution is a fake executor per the existing
ADR-0066 test pattern, and the checked-in pending v2 lock is itself the
fixture for the fail-closed activation tests.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest

from math_research.campaign.experiment_sandbox.sandbox import (
    BOOTSTRAP_SHA256,
    SandboxError,
    SandboxProgramRequest,
)
from math_research.campaign.experiment_sandbox.target_schema import (
    EXACT_GRAPH_CLASS_ID,
    EXACT_GRAPH_TARGET_CLASS,
    TargetClassError,
    resolve_target_class,
)
from math_research.campaign.experiment_sandbox.workspace_activation import (
    WORKSPACE_ACTIVATION_SCHEMA,
    WORKSPACE_PROBE_IDS,
    WorkspaceActivation,
    WorkspaceActivationError,
    build_workspace_activation_report,
    require_activatable_workspace_lock,
    verify_workspace_activation,
)
from math_research.campaign.experiment_sandbox.workspace_image_lock import (
    PLACEHOLDER_DIGEST,
    WORKSPACE_LOCK_PATH,
    WORKSPACE_LOCK_SCHEMA,
    WORKSPACE_RUNTIME_ROLE,
    WorkspaceImageLock,
    WorkspaceImageLockError,
    WorkspacePackagePin,
    load_workspace_image_lock,
)
from math_research.campaign.experiment_sandbox.workspace_runner import (
    WORKSPACE_ADAPTER_ID,
    ActivatedWorkspaceCampaignRunner,
    WorkspaceRunnerError,
    limits_from_request_v2,
)
from math_research.campaign.experiment_sandbox.workspace_sandbox import (
    BOOTSTRAP_V2_SHA256,
    MAX_CPU_SECONDS_V2,
    MAX_MEMORY_BYTES_V2,
    MAX_WALL_SECONDS_V2,
    MAX_WORKSPACE_BYTES_V2,
    MAX_WORKSPACE_INODES_V2,
    RESPONSE_PROTOCOL_V2,
    WorkspaceContainerObservation,
    WorkspaceExecution,
    WorkspaceSandbox,
    WorkspaceSandboxLimits,
    manifest_delta,
    workspace_manifest,
)
from math_research.campaign.records import RecordStatus, canonical_hash
from math_research.campaign.runner import ExperimentRequest, ResourceLimits
from math_research.campaign.verifier_router import (
    ROUTE_EXACT_GRAPH,
    route_for_target_class,
)
from math_research.phase4b.oci_parser_sandbox import OciRuntimeIdentity

ROOT = Path(__file__).resolve().parent.parent
IN_CLASS_TARGETS = (
    ROOT / "fixtures/campaign-experiment/target-exact-graph-distance-spectrum-v1.json",
    ROOT / "fixtures/campaign-experiment/target-exact-graph-order12-v2.json",
)
OFF_CLASS_TARGET = (
    ROOT / "fixtures/campaign-experiment/target-off-class-numeric-engine-v1.json"
)


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def pinned_packages() -> tuple[WorkspacePackagePin, ...]:
    return tuple(
        WorkspacePackagePin(
            name=name, version=version, wheel_sha256=digest(name.encode()),
            license=license_, source_url=f"https://pypi.org/project/{name}/",
            digest_status="pinned",
        )
        for name, version, license_ in (
            ("gmpy2", "2.2.1", "LGPL-3.0-or-later"),
            ("networkx", "3.5", "BSD-3-Clause"),
            ("sympy", "1.14.0", "BSD-3-Clause"),
        )
    )


def built_lock() -> WorkspaceImageLock:
    """A hand-built NON-pending lock: dataclass construction is measurement,
    not authorization; only the loader and gate speak for the checked-in lock."""

    index = digest(b"workspace-image")
    return WorkspaceImageLock(
        schema_version=WORKSPACE_LOCK_SCHEMA,
        lock_path=WORKSPACE_LOCK_PATH,
        lock_sha256=digest(b"workspace-lock"),
        image_reference=f"registry.local/adaivy/campaign-workspace@{index}",
        oci_index_digest=index,
        platform="linux/arm64",
        platform_manifest_digest=digest(b"workspace-manifest"),
        runtime_role=WORKSPACE_RUNTIME_ROLE,
        pull_policy="never",
        network_default="none",
        status="built",
        build_status="built_and_probed",
        base_lock="config/campaign-experiment-oci-image-v1.json",
        base_image_reference="docker.io/library/python@" + digest(b"base"),
        probe_evidence_path="reports/campaign-workspace-sandbox/v2/activation.json",
        packages=pinned_packages(),
        forbidden_packages=("numpy", "scipy"),
    )


def fake_runtime(lock: WorkspaceImageLock) -> OciRuntimeIdentity:
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


def response_frame(
    stdin_payload: bytes, *, result: bytes | None, stdout: bytes = b"",
    stderr: bytes = b"", exit_code: int = 0, signal: int | None = None,
) -> bytes:
    request = json.loads(stdin_payload)
    value = {
        "child_exit_code": None if signal is not None else exit_code,
        "child_signal": signal,
        "child_wait_status": 0,
        "input_artifact_hashes": sorted(
            item["hash"] for item in request["input_artifacts"]
        ),
        "kernel_controls": {},
        "program_artifact_hash": request["program_artifact_hash"],
        "result_base64": (
            None if result is None else base64.b64encode(result).decode("ascii")
        ),
        "result_bytes_observed": 0 if result is None else len(result),
        "result_present": result is not None,
        "result_truncated": False,
        "schema_version": RESPONSE_PROTOCOL_V2,
        "stderr_base64": base64.b64encode(stderr).decode("ascii"),
        "stderr_bytes_observed": len(stderr),
        "stderr_truncated": False,
        "stdout_base64": base64.b64encode(stdout).decode("ascii"),
        "stdout_bytes_observed": len(stdout),
        "stdout_truncated": False,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class FakeExecutor:
    """Scripted fake container: writes files, returns a canonical v2 frame."""

    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = 0

    def execute(self, *, command, stdin_payload, workspace_path, wall_seconds,
                stdout_limit, stderr_limit):
        self.calls += 1
        frame = self.behavior(workspace_path, stdin_payload, self.calls)
        return WorkspaceContainerObservation(
            exit_code=0, timed_out=False, output_limit=None, stdout=frame,
            stderr=b"", stdout_observed=len(frame), oom_killed=False,
            wall_milliseconds=1,
        )


def program_request(source: bytes = b"print('bounded')\n") -> SandboxProgramRequest:
    return SandboxProgramRequest(
        program_source=source, program_artifact_hash=digest(source),
    )


def make_sandbox(behavior, *, limits: WorkspaceSandboxLimits | None = None) -> WorkspaceSandbox:
    lock = built_lock()
    return WorkspaceSandbox(
        expected_runtime=fake_runtime(lock), image_lock=lock,
        executor=FakeExecutor(behavior), limits=limits or WorkspaceSandboxLimits(),
    )


class PendingLockGateTests(unittest.TestCase):
    def test_checked_in_lock_loads_and_is_pending(self):
        lock = load_workspace_image_lock(ROOT)
        self.assertTrue(lock.pending)
        self.assertEqual(WORKSPACE_RUNTIME_ROLE, lock.runtime_role)
        self.assertEqual(("gmpy2", "networkx", "sympy"),
                         tuple(item.name for item in lock.packages))
        self.assertEqual(("numpy", "scipy"), lock.forbidden_packages)
        self.assertTrue(all(item.placeholder for item in lock.packages))

    def test_activation_gate_refuses_placeholder_digests(self):
        with self.assertRaisesRegex(
            WorkspaceActivationError, "pending_operator_build",
        ):
            require_activatable_workspace_lock(ROOT)

    def test_sandbox_constructor_refuses_the_pending_lock(self):
        lock = load_workspace_image_lock(ROOT)
        with self.assertRaisesRegex(SandboxError, "pending"):
            WorkspaceSandbox(
                expected_runtime=fake_runtime(lock), image_lock=lock,
                executor=FakeExecutor(lambda *a: b""),
            )

    def test_report_builder_refuses_a_pending_lock(self):
        lock = load_workspace_image_lock(ROOT)
        with self.assertRaisesRegex(WorkspaceActivationError, "pending"):
            build_workspace_activation_report(
                lock=lock, environment_hash=digest(b"env"),
                policy_hash=digest(b"policy"),
                target_class=EXACT_GRAPH_TARGET_CLASS,
                determinism_replica_policy={
                    "minimum": 1, "maximum": 4,
                    "single_replica_meaning": "determinism_unverified_recorded",
                },
                probes=[],
            )


class LockLoaderFailClosedTests(unittest.TestCase):
    def mutated_root(self, mutate) -> Path:
        staging = Path(tempfile.mkdtemp(prefix="adaivy-workspace-lock-test-"))
        self.addCleanup(shutil.rmtree, staging, ignore_errors=True)
        (staging / "config").mkdir()
        for name in (
            "campaign-experiment-oci-image-v1.json",
            "phase4b-oci-image-linux-arm64-v1.json",
        ):
            shutil.copy2(ROOT / "config" / name, staging / "config" / name)
        value = json.loads((ROOT / WORKSPACE_LOCK_PATH).read_text("utf-8"))
        mutate(value)
        (staging / WORKSPACE_LOCK_PATH).write_text(
            json.dumps(value, indent=2), "utf-8",
        )
        return staging

    def test_unknown_field_forbidden_package_and_false_claim_all_reject(self):
        def add_field(value):
            value["extra"] = True

        def add_numpy(value):
            value["inventory"]["production_python_dependencies"].append({
                "name": "numpy", "version": "2.3.0",
                "wheel_sha256": digest(b"numpy"), "license": "BSD-3-Clause",
                "source_url": "https://pypi.org/project/numpy/",
                "digest_status": "pinned",
            })

        def claim_built(value):
            value["build_status"] = "built_and_probed"

        def widen_network(value):
            value["authorization"]["network_default"] = "egress"

        def drop_sympy(value):
            value["inventory"]["production_python_dependencies"] = [
                item for item in value["inventory"]["production_python_dependencies"]
                if item["name"] != "sympy"
            ]

        for mutate in (add_field, add_numpy, claim_built, widen_network, drop_sympy):
            with self.assertRaises(WorkspaceImageLockError):
                load_workspace_image_lock(self.mutated_root(mutate))

    def test_pinned_status_with_placeholder_wheel_rejects(self):
        def lie_about_pin(value):
            value["inventory"]["production_python_dependencies"][0][
                "digest_status"
            ] = "pinned"

        with self.assertRaisesRegex(WorkspaceImageLockError, "disagrees"):
            load_workspace_image_lock(self.mutated_root(lie_about_pin))


class LimitCeilingTests(unittest.TestCase):
    def test_operator_budgeted_ceilings_admit_and_bound(self):
        at_ceiling = WorkspaceSandboxLimits(
            max_cpu_seconds=MAX_CPU_SECONDS_V2,
            max_wall_seconds=MAX_WALL_SECONDS_V2,
            max_memory_bytes=MAX_MEMORY_BYTES_V2,
            max_workspace_bytes=MAX_WORKSPACE_BYTES_V2,
            max_workspace_inodes=MAX_WORKSPACE_INODES_V2,
        )
        self.assertEqual(3_600, at_ceiling.max_cpu_seconds)
        for changes in (
            {"max_cpu_seconds": MAX_CPU_SECONDS_V2 + 1,
             "max_wall_seconds": MAX_WALL_SECONDS_V2},
            {"max_wall_seconds": MAX_WALL_SECONDS_V2 + 1},
            {"max_memory_bytes": MAX_MEMORY_BYTES_V2 + 1},
            {"max_workspace_bytes": MAX_WORKSPACE_BYTES_V2 + 1},
            {"max_workspace_inodes": MAX_WORKSPACE_INODES_V2 + 1},
            {"determinism_replicas": 0},
            {"determinism_replicas": 5},
        ):
            with self.assertRaisesRegex(SandboxError, "ceiling|integer"):
                WorkspaceSandboxLimits(**changes)

    def test_cpu_may_not_exceed_wall_and_replica_one_is_unverified(self):
        with self.assertRaisesRegex(SandboxError, "CPU ceiling"):
            WorkspaceSandboxLimits(max_cpu_seconds=100, max_wall_seconds=50)
        self.assertTrue(WorkspaceSandboxLimits(determinism_replicas=1).determinism_unverified)
        self.assertFalse(WorkspaceSandboxLimits(determinism_replicas=2).determinism_unverified)

    def test_request_translation_never_rounds_up(self):
        request = ExperimentRequest(
            campaign_id="campaign.test", action_id="action.1",
            tool_id=WORKSPACE_ADAPTER_ID, program_artifact_hash=digest(b"p"),
            program_source=b"p", input_artifacts=(), arguments=(),
            resource_limits=ResourceLimits(
                cpu_milliseconds=1_999_999, wall_milliseconds=2_500_000,
                memory_bytes=1_073_741_824, output_bytes=65_536, process_count=7,
            ), network="none",
        )
        limits = limits_from_request_v2(request)
        self.assertEqual(1_999, limits.max_cpu_seconds)
        self.assertEqual(2_500, limits.max_wall_seconds)
        with self.assertRaises(WorkspaceRunnerError):
            limits_from_request_v2(replace(
                request, resource_limits=replace(
                    request.resource_limits, cpu_milliseconds=999,
                ),
            ))


class CommandAndBootstrapTests(unittest.TestCase):
    def test_v2_bootstrap_has_its_own_hash_and_site_packages_visible(self):
        self.assertNotEqual(BOOTSTRAP_SHA256, BOOTSTRAP_V2_SHA256)
        sandbox = make_sandbox(lambda *a: b"")
        command = sandbox.command(Path("/tmp/replica-0"))
        self.assertIn("-I", command)
        self.assertIn("-c", command)
        self.assertNotIn("-S", command)
        for flag in (
            "--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true", "--user=65534:65534",
            "--env=PYTHONHASHSEED=0",
        ):
            self.assertIn(flag, command)
        mount = next(item for item in command if item.startswith("--mount="))
        self.assertIn("destination=/workspace", mount)


class WorkspaceManifestAcrossRunsTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(tempfile.mkdtemp(prefix="adaivy-workspace-test-"))
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)

    def test_two_consecutive_runs_chain_their_manifests(self):
        def first_run(workspace_path, stdin_payload, _call):
            (workspace_path / "data.json").write_bytes(b"[1,2,3]")
            return response_frame(stdin_payload, result=b'{"stage":1}')

        def second_run(workspace_path, stdin_payload, _call):
            data = (workspace_path / "data.json").read_bytes()
            assert data == b"[1,2,3]", "second run did not see the first run's output"
            (workspace_path / "derived.json").write_bytes(b"[6]")
            return response_frame(stdin_payload, result=b'{"stage":2}')

        one = make_sandbox(first_run).run(program_request(), self.workspace)
        self.assertEqual("completed", one.status)
        self.assertTrue(one.workspace_promoted)
        self.assertEqual(["data.json"], one.workspace_delta["added"])
        self.assertEqual(
            b"[1,2,3]", (self.workspace / "data.json").read_bytes(),
        )

        two = make_sandbox(second_run).run(program_request(b"stage2\n"), self.workspace)
        self.assertEqual("completed", two.status)
        # The chain: run one's after-manifest is run two's before-manifest.
        self.assertEqual(
            one.workspace_manifest_after["content_hash"],
            two.workspace_manifest_before["content_hash"],
        )
        self.assertEqual(["derived.json"], two.workspace_delta["added"])
        record = two.semantic_record()
        self.assertEqual(
            record["workspace_manifest_before_hash"],
            one.workspace_manifest_after["content_hash"],
        )
        self.assertEqual(record["content_hash"], canonical_hash({
            key: item for key, item in record.items() if key != "content_hash"
        }))
        # Manifest entries are exact: path, size, sha256, deterministically ordered.
        entry = two.workspace_manifest_after["entries"][1]
        self.assertEqual(
            {"path": "derived.json", "sha256": digest(b"[6]"), "size": 3}, entry,
        )

    def test_manifest_ceilings_and_symlinks_fail_closed(self):
        (self.workspace / "big.bin").write_bytes(b"x" * 200_000)
        with self.assertRaisesRegex(SandboxError, "byte_ceiling"):
            workspace_manifest(self.workspace, max_bytes=65_536, max_inodes=100)
        (self.workspace / "big.bin").unlink()
        (self.workspace / "real.txt").write_bytes(b"y")
        (self.workspace / "link.txt").symlink_to(self.workspace / "real.txt")
        with self.assertRaisesRegex(SandboxError, "entry_unsupported"):
            workspace_manifest(self.workspace, max_bytes=65_536, max_inodes=100)


class DeterminismTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(tempfile.mkdtemp(prefix="adaivy-workspace-det-"))
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)

    def test_single_replica_is_flagged_determinism_unverified(self):
        def run(workspace_path, stdin_payload, _call):
            (workspace_path / "out.json").write_bytes(b"{}")
            return response_frame(stdin_payload, result=b'{"ok":1}')

        execution = make_sandbox(
            run, limits=WorkspaceSandboxLimits(determinism_replicas=1),
        ).run(program_request(), self.workspace)
        self.assertEqual("completed", execution.status)
        self.assertEqual(1, execution.determinism_replicas)
        self.assertTrue(execution.determinism_unverified)
        self.assertFalse(execution.deterministic)
        record = execution.semantic_record()
        self.assertTrue(record["determinism_unverified"])
        self.assertEqual(1, record["determinism_replicas"])

    def test_diverging_results_and_workspaces_are_refused(self):
        def flaky_result(workspace_path, stdin_payload, call):
            return response_frame(stdin_payload, result=b'{"n":%d}' % call)

        flaky = make_sandbox(flaky_result).run(program_request(), self.workspace)
        self.assertEqual("refused", flaky.status)
        self.assertEqual("nondeterministic_result", flaky.refusal_code)
        self.assertFalse(flaky.workspace_promoted)

        def flaky_workspace(workspace_path, stdin_payload, call):
            (workspace_path / "state.bin").write_bytes(b"%d" % call)
            return response_frame(stdin_payload, result=b'{"ok":1}')

        drifting = make_sandbox(flaky_workspace).run(program_request(), self.workspace)
        self.assertEqual("refused", drifting.status)
        self.assertEqual("nondeterministic_workspace", drifting.refusal_code)
        self.assertFalse(drifting.workspace_promoted)
        # A refused run must not have leaked replica state into the workspace.
        self.assertEqual([], list(self.workspace.iterdir()))


class FailureAsDataTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(tempfile.mkdtemp(prefix="adaivy-workspace-fail-"))
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)

    def test_nonzero_exit_is_structured_diagnostics_not_a_dead_end(self):
        def failing(workspace_path, stdin_payload, _call):
            (workspace_path / "partial.json").write_bytes(b"[1]")
            return response_frame(
                stdin_payload, result=None, exit_code=3,
                stderr=b"Traceback: exact search aborted at depth 7\n",
            )

        execution = make_sandbox(failing).run(program_request(), self.workspace)
        self.assertEqual("program_failed", execution.status)
        self.assertEqual("program_nonzero_exit", execution.refusal_code)
        diagnostics = execution.failure_diagnostics()
        self.assertEqual(3, diagnostics["child_exit_code"])
        self.assertIn("depth 7", diagnostics["stderr_excerpt"])
        self.assertEqual(["partial.json"], diagnostics["workspace_delta"]["added"])
        self.assertEqual(diagnostics["content_hash"], canonical_hash({
            key: item for key, item in diagnostics.items()
            if key != "content_hash"
        }))
        self.assertFalse(diagnostics["epistemic_warrant_created"])
        # Failure is data the next run may build on: the partial write persists.
        self.assertTrue(execution.workspace_promoted)
        self.assertEqual(b"[1]", (self.workspace / "partial.json").read_bytes())


class TargetSchemaClassTests(unittest.TestCase):
    def test_any_in_class_target_is_admitted(self):
        hashes = set()
        for path in IN_CLASS_TARGETS:
            target = EXACT_GRAPH_TARGET_CLASS.admit_target(path.read_bytes())
            hashes.add(target.target_hash)
            admission = EXACT_GRAPH_TARGET_CLASS.admission_record(target)
            self.assertEqual(
                EXACT_GRAPH_TARGET_CLASS.definition_hash,
                admission["class_definition_hash"],
            )
            self.assertFalse(admission["epistemic_warrant_created"])
        self.assertEqual(2, len(hashes), "class admission must span target hashes")

    def test_off_class_target_is_a_typed_refusal(self):
        with self.assertRaises(TargetClassError) as caught:
            EXACT_GRAPH_TARGET_CLASS.admit_target(OFF_CLASS_TARGET.read_bytes())
        self.assertTrue(
            caught.exception.refusal_code.startswith("target_outside_schema_class:")
        )

    def test_class_definition_is_content_hashed_and_registered(self):
        record = EXACT_GRAPH_TARGET_CLASS.definition_record()
        self.assertEqual(12, len(record["field_names"]))
        self.assertEqual(
            EXACT_GRAPH_TARGET_CLASS.definition_hash, canonical_hash(record),
        )
        self.assertIs(
            EXACT_GRAPH_TARGET_CLASS, resolve_target_class(EXACT_GRAPH_CLASS_ID),
        )
        with self.assertRaises(TargetClassError):
            resolve_target_class("adaivy.campaign-target-class.unknown.v9")
        self.assertEqual(
            ROUTE_EXACT_GRAPH, route_for_target_class(EXACT_GRAPH_CLASS_ID),
        )
        with self.assertRaises(ValueError):
            route_for_target_class("adaivy.campaign-target-class.unknown.v9")


def probe_observation(probe_id: str) -> dict:
    if probe_id == "pr.workspace-nondeterministic-program-refused":
        return {
            "refusal_code": "nondeterministic_result", "replica_count": 2,
            "results_differed": True, "status": "refused",
        }
    if probe_id == "pr.workspace-manifest-ledgered":
        return {
            "first_manifest_hash": digest(b"manifest-1"),
            "second_manifest_hash": digest(b"manifest-2"),
            "second_run_read_first_output": True,
        }
    if probe_id == "pr.workspace-package-set-exact":
        return {
            "allowlist_importable": True, "numpy_refused": True,
            "scipy_refused": True,
        }
    return {"demonstrated": True}


def synthetic_report(lock: WorkspaceImageLock) -> dict:
    probes = []
    for probe_id in WORKSPACE_PROBE_IDS:
        probe = {
            "observation": probe_observation(probe_id),
            "passed": True,
            "probe_id": probe_id,
        }
        probe["content_hash"] = canonical_hash(probe)
        probes.append(probe)
    return build_workspace_activation_report(
        lock=lock, environment_hash=digest(b"env"), policy_hash=digest(b"policy"),
        target_class=EXACT_GRAPH_TARGET_CLASS,
        determinism_replica_policy={
            "minimum": 1, "maximum": 4,
            "single_replica_meaning": "determinism_unverified_recorded",
        },
        probes=probes,
    )


class WorkspaceActivationRecordTests(unittest.TestCase):
    def test_synthetic_record_round_trips_and_binds_the_class(self):
        report = synthetic_report(built_lock())
        attestation = verify_workspace_activation(report)
        self.assertTrue(attestation.activated)
        self.assertEqual(EXACT_GRAPH_CLASS_ID, attestation.target_schema_class_id)
        self.assertEqual(
            EXACT_GRAPH_TARGET_CLASS.definition_hash,
            attestation.target_class_definition_hash,
        )
        self.assertEqual(BOOTSTRAP_V2_SHA256, attestation.bootstrap_hash)

    def test_mutations_fail_closed(self):
        base = synthetic_report(built_lock())
        for mutate in (
            lambda x: x["probes"].pop(),
            lambda x: x["probes"][0].update(passed=False),
            lambda x: x.update(target_class_definition_hash=digest(b"other")),
            lambda x: x.update(bootstrap_hash=BOOTSTRAP_SHA256),
            lambda x: x["probes"][11]["observation"].update(numpy_refused=False),
            lambda x: x["determinism_replica_policy"].update(maximum=8),
        ):
            report = copy.deepcopy(base)
            mutate(report)
            with self.assertRaises(ValueError):
                verify_workspace_activation(report)


def attestation() -> WorkspaceActivation:
    return WorkspaceActivation(
        schema_version=WORKSPACE_ACTIVATION_SCHEMA, status="activated",
        environment_hash=digest(b"env"), policy_hash=digest(b"policy"),
        bootstrap_hash=BOOTSTRAP_V2_SHA256,
        workspace_lock_sha256=digest(b"lock"),
        target_schema_class_id=EXACT_GRAPH_CLASS_ID,
        target_class_definition_hash=EXACT_GRAPH_TARGET_CLASS.definition_hash,
        probes_total=16, probes_flipped=16, probes_blocked=0,
        content_hash=digest(b"activation"),
    )


class FakeWorkspaceSandboxPort:
    def __init__(self, limits, activation, execution_factory):
        self.limits = limits
        self.control_policy_sha256 = activation.policy_hash
        self.bootstrap_sha256 = activation.bootstrap_hash
        self.environment_sha256 = activation.environment_hash
        self.policy_sha256 = digest(b"full-policy")
        self.execution_factory = execution_factory

    def configuration_record(self):
        return {
            "determinism_unverified": self.limits.determinism_unverified,
            "limits": self.limits.to_record(),
        }

    def run(self, request, workspace):
        return self.execution_factory(self.limits)


def port_execution(limits, *, status: str, refusal: str | None, result: bytes | None):
    from math_research.campaign.experiment_sandbox.sandbox import SandboxOutcome

    outcome = SandboxOutcome(
        status=status, refusal_code=refusal, result=result,
        result_bytes_observed=0 if result is None else len(result),
        result_truncated=False, stdout=b"", stdout_bytes_observed=0,
        stdout_truncated=False, stderr=b"exact search aborted",
        stderr_bytes_observed=20, stderr_truncated=False,
        container_exit_code=0,
        child_exit_code=0 if status == "completed" else 2, child_signal=None,
        oom_killed=False, wall_timed_out=False,
        container_stdout_bytes_observed=0, container_stderr=b"",
        wall_milliseconds=2,
    )
    manifest = {
        "entries": [], "file_count": 0, "inode_count": 0,
        "schema_version": "adaivy.campaign-workspace-manifest.v1",
        "total_bytes": 0,
    }
    manifest["content_hash"] = canonical_hash(manifest)
    return WorkspaceExecution(
        status=status, refusal_code=refusal, replicas=(outcome,),
        deterministic=not limits.determinism_unverified,
        determinism_replicas=limits.determinism_replicas,
        determinism_unverified=limits.determinism_unverified,
        outcome=outcome, workspace_manifest_before=manifest,
        workspace_manifest_after=manifest, workspace_promoted=True,
    )


class WorkspaceRunnerTests(unittest.TestCase):
    def runner(self, *, status="completed", refusal=None,
               result=b'{"candidate":1}', replicas=2, workspace=None):
        activation = attestation()
        return ActivatedWorkspaceCampaignRunner(
            sandbox_factory=lambda limits: FakeWorkspaceSandboxPort(
                limits, activation,
                lambda inner: port_execution(
                    inner, status=status, refusal=refusal, result=result,
                ),
            ),
            activation=activation,
            target_class=EXACT_GRAPH_TARGET_CLASS,
            workspace_dir=workspace or Path("/nonexistent-fake-workspace"),
            determinism_replicas=replicas,
        )

    def request(self, **changes):
        source = b"print('bounded')\n"
        value = dict(
            campaign_id="campaign.test", action_id="action.9",
            tool_id=WORKSPACE_ADAPTER_ID, program_artifact_hash=digest(source),
            program_source=source, input_artifacts=(), arguments=(),
            resource_limits=ResourceLimits(
                cpu_milliseconds=600_000, wall_milliseconds=900_000,
                memory_bytes=2_147_483_648, output_bytes=65_536,
                process_count=15,
            ), network="none",
        )
        value.update(changes)
        return ExperimentRequest(**value)

    def test_repeated_runs_append_records_and_failures_are_nonterminal(self):
        runner = self.runner(status="program_failed",
                             refusal="program_nonzero_exit", result=None)
        first = runner(self.request())
        second = runner(self.request())
        self.assertEqual(RecordStatus.FAILED, first.status)
        self.assertEqual(first.result, second.result)
        payload = json.loads(first.result)
        self.assertEqual(
            "adaivy.campaign-workspace-failure-diagnostics.v1",
            payload["schema_version"],
        )
        self.assertEqual(2, len(runner.run_records))
        self.assertEqual(
            "program_failed", runner.last_run_record["status"],
        )

    def test_replica_one_surfaces_determinism_unverified(self):
        runner = self.runner(replicas=1)
        result = runner(self.request())
        self.assertEqual(RecordStatus.COMPLETED, result.status)
        self.assertTrue(runner.last_run_record["determinism_unverified"])
        self.assertEqual(1, runner.last_run_record["determinism_replicas"])

    def test_runner_admits_any_in_class_target_and_refuses_off_class(self):
        runner = self.runner()
        for path in IN_CLASS_TARGETS:
            runner.admit_target(path.read_bytes())
        with self.assertRaises(TargetClassError):
            runner.admit_target(OFF_CLASS_TARGET.read_bytes())

    def test_runner_refuses_wrong_class_adapter_and_network(self):
        activation = attestation()
        with self.assertRaisesRegex(WorkspaceRunnerError, "class differs"):
            ActivatedWorkspaceCampaignRunner(
                sandbox_factory=lambda limits: None,
                activation=replace(
                    activation, target_schema_class_id="adaivy.other.v1",
                ),
                target_class=EXACT_GRAPH_TARGET_CLASS,
                workspace_dir=Path("/nonexistent"),
            )
        runner = self.runner()
        with self.assertRaises(WorkspaceRunnerError):
            runner(self.request(tool_id="shell"))
        with self.assertRaises(WorkspaceRunnerError):
            runner(self.request(network="egress"))


if __name__ == "__main__":
    unittest.main()
