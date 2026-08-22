"""Executable and replayable activation gate for the ADR-0066 sandbox."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from ...phase4b.oci_parser_sandbox import OciRuntimeIdentity, RUNTIME_SCHEMA
from ..records import canonical_bytes, canonical_hash
from .attestation import ACTIVATION_SCHEMA, SandboxActivation
from .image_lock import load_campaign_image_lock, load_phase4b_image_lock
from .sandbox import (
    BOOTSTRAP_SHA256,
    CampaignSandboxLimits,
    OciExperimentSandbox,
    SandboxExecution,
    SandboxProgramRequest,
    _policy,
)
from .verifier import load_target, trust_block, verify_candidate

REPORT_SCHEMA = "adaivy.campaign-experiment-sandbox-gate.v1"
MAX_ACTIVATION_BYTES = 2_097_152
PROBE_IDS = (
    "pr.sandbox-network-refused",
    "pr.sandbox-write-outside-tmpfs-refused",
    "pr.sandbox-noexec-tmpfs",
    "pr.sandbox-fork-bomb-bounded",
    "pr.sandbox-memory-bounded",
    "pr.sandbox-cpu-bounded",
    "pr.sandbox-no-ambient-secret",
    "pr.sandbox-stdout-truncation-recorded",
    "pr.sandbox-program-measurement-refused",
    "pr.sandbox-nondeterministic-program-refused",
    "pr.sandbox-image-digest-pinned",
    "pr.sandbox-role-not-widened",
    "pr.sandbox-verifier-not-in-container",
    "pr.sandbox-output-creates-no-warrant",
    "pr.sandbox-lying-program-caught",
    "pr.sandbox-absent-runtime-is-a-blocker",
)


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _request(source: bytes) -> SandboxProgramRequest:
    return SandboxProgramRequest(program_source=source, program_artifact_hash=_digest(source))


def _summary(probe_id: str, passed: bool, observation: dict[str, Any]) -> dict[str, Any]:
    value = {
        "observation": observation,
        "passed": passed,
        "probe_id": probe_id,
    }
    value["content_hash"] = canonical_hash(value)
    return value


def _run(
    runtime: OciRuntimeIdentity, lock: Any, source: str,
    limits: CampaignSandboxLimits,
) -> tuple[OciExperimentSandbox, SandboxExecution]:
    sandbox = OciExperimentSandbox(
        expected_runtime=runtime, image_lock=lock, limits=limits,
    )
    return sandbox, sandbox.run(_request(source.encode("utf-8")))


def _blocked_result_source(body: str) -> str:
    return (
        "import json\n"
        "blocked = False\n"
        f"{body}\n"
        "payload=json.dumps({'blocked':blocked},sort_keys=True,separators=(',',':')).encode()\n"
        "open(ADAIVY_RESULT_PATH,'wb').write(payload)\n"
        "raise SystemExit(0 if blocked else 79)\n"
    )


def _completed_blocked(execution: SandboxExecution) -> bool:
    return (
        execution.status == "completed"
        and execution.deterministic
        and execution.outcome.result == b'{"blocked":true}'
    )


def _runtime_without_client(runtime: OciRuntimeIdentity) -> OciRuntimeIdentity:
    values = runtime.to_record()
    values["docker_executable"] = "/nonexistent/adaivy-docker"
    values.pop("environment_sha256")
    values["environment_sha256"] = canonical_hash(values)
    values["image_layers"] = tuple(values["image_layers"])
    return OciRuntimeIdentity(**values)


def run_campaign_experiment_activation(
    repository_root: Path, runtime: OciRuntimeIdentity,
) -> dict[str, Any]:
    """Run all sixteen probes against fresh containers and exact host checks."""

    root = repository_root.resolve()
    lock = load_campaign_image_lock(root)
    phase4b = load_phase4b_image_lock(root)
    target_bytes = (
        root / "fixtures/campaign-experiment/target-exact-graph-distance-spectrum-v1.json"
    ).read_bytes()
    target = load_target(target_bytes)
    default_limits = CampaignSandboxLimits()
    production = OciExperimentSandbox(
        expected_runtime=runtime, image_lock=lock, limits=default_limits,
    )
    probes: list[dict[str, Any]] = []

    def execution_probe(
        probe_id: str, source: str, limits: CampaignSandboxLimits,
        predicate: Callable[[SandboxExecution], bool],
    ) -> SandboxExecution:
        sandbox, execution = _run(runtime, lock, source, limits)
        observation = {
            "bootstrap_sha256": sandbox.bootstrap_sha256,
            "deterministic": execution.deterministic,
            "environment_sha256": sandbox.environment_sha256,
            "policy_sha256": sandbox.policy_sha256,
            "refusal_code": execution.refusal_code,
            "replicas": [
                {
                    **item.semantic_record(),
                    "kernel_controls": {
                        key: item.kernel_controls[key] > 0
                        for key in sorted(item.kernel_controls)
                    },
                }
                for item in execution.replicas
            ],
            "status": execution.status,
        }
        probes.append(_summary(probe_id, predicate(execution), observation))
        return execution

    network = _blocked_result_source(
        "try:\n import socket\n socket.socket().connect(('1.1.1.1',80))\n"
        "except OSError:\n blocked=True"
    )
    execution_probe(PROBE_IDS[0], network, default_limits, _completed_blocked)
    write_root = (
        "import json\nroot_blocked=False\ninode_blocked=False\n"
        "open(ADAIVY_RESULT_PATH,'wb').close()\n"
        "try:\n open('/adaivy-write-escape','wb').write(b'x')\n"
        "except OSError:\n root_blocked=True\n"
        "try:\n"
        " for i in range(512): open('/tmp/inode-%d'%i,'wb').close()\n"
        "except OSError:\n inode_blocked=True\n"
        "blocked=root_blocked and inode_blocked\n"
        "open(ADAIVY_RESULT_PATH,'wb').write(json.dumps({'blocked':blocked},sort_keys=True,separators=(',',':')).encode())\n"
        "raise SystemExit(0 if blocked else 79)\n"
    )
    execution_probe(PROBE_IDS[1], write_root, default_limits, _completed_blocked)
    noexec = _blocked_result_source(
        "import os\np='/tmp/probe'\nopen(p,'wb').write(b'#!/bin/sh\\nexit 0\\n')\n"
        "os.chmod(p,0o700)\ntry:\n os.execv(p,(p,))\nexcept OSError:\n blocked=True"
    )
    execution_probe(PROBE_IDS[2], noexec, default_limits, _completed_blocked)
    fork = (
        "import json,os\nr,w=os.pipe()\nblocked=False\n"
        "try:\n while True:\n  pid=os.fork()\n  if pid==0:\n   os.close(w); os.read(r,1); os._exit(0)\n"
        "except OSError:\n blocked=True\n"
        "open(ADAIVY_RESULT_PATH,'wb').write(json.dumps({'blocked':blocked},sort_keys=True,separators=(',',':')).encode())\n"
        "raise SystemExit(0 if blocked else 79)\n"
    )
    fork_limits = replace(default_limits, max_processes=6)
    execution_probe(
        PROBE_IDS[3], fork, fork_limits,
        lambda e: _completed_blocked(e) and all(
            item.kernel_controls.get("pids.events.max", 0) > 0 for item in e.replicas
        ),
    )
    memory_limits = replace(
        default_limits, max_memory_bytes=33_554_432, max_wall_seconds=5,
        max_cpu_seconds=5,
    )
    execution_probe(
        PROBE_IDS[4], "x=bytearray(256_000_000)\n",
        memory_limits,
        lambda e: e.status != "completed" and any(
            item.oom_killed or item.kernel_controls.get("memory.events.oom_kill", 0) > 0
            for item in e.replicas
        ),
    )
    cpu_limits = replace(default_limits, max_wall_seconds=4, max_cpu_seconds=1)
    execution_probe(
        PROBE_IDS[5], "while True: pass\n", cpu_limits,
        lambda e: e.status != "completed" and any(
            item.child_signal in {9, 24} or item.container_exit_code in {137, 152}
            for item in e.replicas
        ),
    )
    secret_name = "ADAIVY_CAMPAIGN_SANDBOX_SECRET_PROBE"
    prior = __import__("os").environ.get(secret_name)
    __import__("os").environ[secret_name] = "must-not-enter"
    try:
        secret = _blocked_result_source(
            f"import os\nblocked=os.environ.get({secret_name!r}) is None"
        )
        execution_probe(PROBE_IDS[6], secret, default_limits, _completed_blocked)
    finally:
        if prior is None:
            __import__("os").environ.pop(secret_name, None)
        else:
            __import__("os").environ[secret_name] = prior
    stdout_limits = replace(
        default_limits, max_stdout_bytes=64, max_result_bytes=1_024,
        max_stderr_bytes=1_024,
    )
    stdout = (
        "import json\nprint('x'*4096)\n"
        "open(ADAIVY_RESULT_PATH,'wb').write(b'{\"candidate\":true}')\n"
    )
    execution_probe(
        PROBE_IDS[7], stdout, stdout_limits,
        lambda e: e.status == "program_failed"
        and e.refusal_code == "stdout_truncated"
        and e.outcome.stdout_truncated,
    )
    measured_candidate = canonical_bytes({
        "asserted_construction": "forbidden self measurement",
        "asserted_satisfies_target": True,
        "cpu_seconds": 1,
        "edges": [],
        "order": 10,
        "schema_version": "adaivy.campaign-experiment-graph-candidate.v1",
        "target_id": target.target_id,
    })
    measured_verdict = verify_candidate(target, measured_candidate)
    probes.append(_summary(PROBE_IDS[8], measured_verdict.refusal_code == "program_asserted_measurement", {
        "candidate_hash": measured_verdict.candidate_hash,
        "refusal_code": measured_verdict.refusal_code,
        "verdict": measured_verdict.verdict,
    }))
    nondeterministic = (
        "import os\nopen(ADAIVY_RESULT_PATH,'wb').write(os.urandom(32))\n"
    )
    nondeterministic_execution = execution_probe(
        PROBE_IDS[9], nondeterministic, default_limits,
        lambda e: e.status == "refused" and e.refusal_code == "nondeterministic_result",
    )
    # The random bytes are intentionally different and therefore cannot enter
    # the durable activation identity.  Retain only the fact and shape of the
    # divergence, which is the evidence this probe exists to establish.
    probes[-1] = _summary(PROBE_IDS[9], (
        nondeterministic_execution.status == "refused"
        and nondeterministic_execution.refusal_code == "nondeterministic_result"
    ), {
        "refusal_code": nondeterministic_execution.refusal_code,
        "replica_count": len(nondeterministic_execution.replicas),
        "result_byte_counts": [
            item.result_bytes_observed for item in nondeterministic_execution.replicas
        ],
        "results_differed": len({
            item.result for item in nondeterministic_execution.replicas
        }) > 1,
        "status": nondeterministic_execution.status,
    })
    command = production.command(Path("/tmp/adaivy-campaign-probe.cid"))
    probes.append(_summary(PROBE_IDS[10], (
        runtime.image_reference == lock.image_reference
        and "--pull=never" in command
        and runtime.image_descriptor_digest == lock.oci_index_digest
    ), {
        "image_reference": runtime.image_reference,
        "platform_manifest_digest": lock.platform_manifest_digest,
        "pull_policy": "never" if "--pull=never" in command else "different",
    }))
    probes.append(_summary(PROBE_IDS[11], (
        lock.image_reference == phase4b.image_reference
        and lock.runtime_role != phase4b.runtime_role
        and phase4b.runtime_role == "phase4b_parser_sandbox_only"
    ), {
        "campaign_role": lock.runtime_role,
        "phase4b_role": phase4b.runtime_role,
        "shared_image": lock.image_reference == phase4b.image_reference,
    }))
    verifier_source = (
        root / "src/math_research/campaign/experiment_sandbox/verifier.py"
    ).read_text("utf-8")
    verifier_isolated = all(
        marker not in verifier_source
        for marker in ("import subprocess", "import socket", "import os", "OciExperimentSandbox")
    )
    probes.append(_summary(
        PROBE_IDS[12], verifier_isolated,
        {"forbidden_imports_absent": verifier_isolated},
    ))
    probes.append(_summary(PROBE_IDS[13], trust_block() == {
        "candidate_class": "untrusted_sandbox_candidate",
        "epistemic_warrant_created": False,
        "graph_admission": False,
        "novelty_status": "not_assessed",
        "significance_status": "not_assessed",
        "source_applicability_asserted": False,
    }, trust_block()))
    lying_source = (
        root / "fixtures/campaign-experiment/programs/lying-search-v1.py"
    ).read_bytes()
    lying = production.run(_request(lying_source))
    lying_verdict = (
        None if lying.outcome.result is None
        else verify_candidate(target, lying.outcome.result)
    )
    probes.append(_summary(PROBE_IDS[14], (
        lying.status == "completed" and lying_verdict is not None
        and lying_verdict.claim_refuted
        and lying_verdict.verdict == "target_not_satisfied"
    ), {
        "claim_refuted": None if lying_verdict is None else lying_verdict.claim_refuted,
        "sandbox_status": lying.status,
        "verdict": None if lying_verdict is None else lying_verdict.verdict,
    }))
    absent_runtime = _runtime_without_client(runtime)
    absent = OciExperimentSandbox(
        expected_runtime=absent_runtime, image_lock=lock, limits=default_limits,
    ).run(_request(b"open(ADAIVY_RESULT_PATH,'wb').write(b'x')\n"))
    probes.append(_summary(PROBE_IDS[15], (
        absent.status == "refused"
        and absent.refusal_code == "sandbox_runtime_unavailable"
        and len(absent.replicas) == 1
    ), {
        "refusal_code": absent.refusal_code,
        "replica_count": len(absent.replicas),
        "status": absent.status,
    }))

    if tuple(item["probe_id"] for item in probes) != PROBE_IDS:
        raise ValueError("campaign sandbox probe order differs")
    passed = sum(item["passed"] is True for item in probes)
    report: dict[str, Any] = {
        "bootstrap_hash": BOOTSTRAP_SHA256,
        "campaign_lock_sha256": lock.lock_sha256,
        "environment": runtime.to_record(),
        "environment_hash": runtime.environment_sha256,
        "phase4b_lock_sha256": phase4b.lock_sha256,
        "policy": production.policy_record(),
        "policy_hash": production.control_policy_sha256,
        "probes": probes,
        "probes_blocked": len(probes) - passed,
        "probes_flipped": passed,
        "probes_total": len(probes),
        "schema_version": REPORT_SCHEMA,
        "status": "activated" if passed == len(probes) else "blocked",
        "target_hash": target.target_hash,
        "trust": trust_block(),
    }
    report["content_hash"] = canonical_hash(report)
    verify_campaign_experiment_activation(report)
    return report


def verify_campaign_experiment_activation(value: object) -> SandboxActivation:
    """Strictly verify a raw gate record and return its small attestation."""

    fields = {
        "bootstrap_hash", "campaign_lock_sha256", "content_hash", "environment",
        "environment_hash", "phase4b_lock_sha256", "policy", "policy_hash",
        "probes", "probes_blocked", "probes_flipped", "probes_total",
        "schema_version", "status", "target_hash", "trust",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("campaign sandbox activation fields differ")
    if value["schema_version"] != REPORT_SCHEMA:
        raise ValueError("campaign sandbox activation report schema differs")
    if value["content_hash"] != canonical_hash({
        key: item for key, item in value.items() if key != "content_hash"
    }):
        raise ValueError("campaign sandbox activation content hash differs")
    runtime_value = value["environment"]
    if not isinstance(runtime_value, dict):
        raise ValueError("campaign sandbox runtime identity differs")
    runtime_record = dict(runtime_value)
    runtime_record["image_layers"] = tuple(runtime_record.get("image_layers", ()))
    runtime = OciRuntimeIdentity(**runtime_record)
    if runtime.environment_sha256 != value["environment_hash"]:
        raise ValueError("campaign sandbox runtime hash differs")
    policy = value["policy"]
    if not isinstance(policy, dict) or "limits" not in policy:
        raise ValueError("campaign sandbox activation policy differs")
    invariant_policy = dict(policy)
    invariant_policy.pop("limits")
    if canonical_hash(invariant_policy) != value["policy_hash"]:
        raise ValueError("campaign sandbox activation policy hash differs")
    limits_value = policy["limits"]
    if not isinstance(limits_value, dict):
        raise ValueError("campaign sandbox activation limits differ")
    limits = CampaignSandboxLimits(**limits_value)
    # A minimal lock-shaped object is sufficient here; the builder separately
    # resolves both complete lock files and their hashes before execution.
    class BoundLock:
        image_reference = runtime.image_reference
        lock_path = policy.get("image_lock")
        lock_sha256 = policy.get("image_lock_sha256")
        runtime_role = policy.get("runtime_role")
    if _policy(runtime, BoundLock(), limits) != policy:
        raise ValueError("campaign sandbox activation policy fields differ")
    probes = value["probes"]
    if (
        not isinstance(probes, list)
        or tuple(item.get("probe_id") for item in probes if isinstance(item, dict)) != PROBE_IDS
    ):
        raise ValueError("campaign sandbox activation probe inventory differs")
    for probe in probes:
        if not isinstance(probe, dict) or set(probe) != {
            "content_hash", "observation", "passed", "probe_id",
        }:
            raise ValueError("campaign sandbox activation probe fields differ")
        if probe["content_hash"] != canonical_hash({
            key: item for key, item in probe.items() if key != "content_hash"
        }):
            raise ValueError("campaign sandbox activation probe hash differs")
        if probe["passed"] is not True:
            raise ValueError("campaign sandbox activation contains an unflipped probe")
    by_id = {item["probe_id"]: item["observation"] for item in probes}
    blocked_hash = _digest(b'{"blocked":true}')
    for probe_id in PROBE_IDS[:7]:
        observation = by_id[probe_id]
        if not isinstance(observation, dict) or not isinstance(observation.get("replicas"), list):
            raise ValueError(f"{probe_id} observation differs")
    for probe_id in PROBE_IDS[:4]:
        observation = by_id[probe_id]
        if (
            observation.get("status") != "completed"
            or observation.get("deterministic") is not True
            or any(item.get("result_sha256") != blocked_hash for item in observation["replicas"])
        ):
            raise ValueError(f"{probe_id} did not demonstrate its denial")
    if not all(
        item.get("kernel_controls", {}).get("pids.events.max") is True
        for item in by_id[PROBE_IDS[3]]["replicas"]
    ):
        raise ValueError("process probe lacks kernel pids-limit evidence")
    memory = by_id[PROBE_IDS[4]]
    if memory.get("status") == "completed" or not any(
        item.get("oom_killed") is True
        or item.get("kernel_controls", {}).get("memory.events.oom_kill") is True
        for item in memory["replicas"]
    ):
        raise ValueError("memory probe lacks kernel enforcement evidence")
    cpu = by_id[PROBE_IDS[5]]
    if cpu.get("status") == "completed" or not any(
        item.get("child_signal") in {9, 24} or item.get("container_exit_code") in {137, 152}
        for item in cpu["replicas"]
    ):
        raise ValueError("CPU probe lacks kernel enforcement evidence")
    secret = by_id[PROBE_IDS[6]]
    if secret.get("status") != "completed" or any(
        item.get("result_sha256") != blocked_hash for item in secret["replicas"]
    ):
        raise ValueError("ambient-secret probe did not demonstrate absence")
    stdout = by_id[PROBE_IDS[7]]
    if stdout.get("status") != "program_failed" or stdout.get("refusal_code") != "stdout_truncated":
        raise ValueError("stdout truncation probe differs")
    if by_id[PROBE_IDS[8]] != {
        "candidate_hash": by_id[PROBE_IDS[8]].get("candidate_hash"),
        "refusal_code": "program_asserted_measurement",
        "verdict": "candidate_refused",
    }:
        raise ValueError("program measurement probe differs")
    nondeterminism = by_id[PROBE_IDS[9]]
    if (
        nondeterminism.get("status") != "refused"
        or nondeterminism.get("refusal_code") != "nondeterministic_result"
        or nondeterminism.get("replica_count") < 2
        or nondeterminism.get("results_differed") is not True
    ):
        raise ValueError("nondeterminism probe differs")
    image = by_id[PROBE_IDS[10]]
    if image.get("image_reference") != runtime.image_reference or image.get("pull_policy") != "never":
        raise ValueError("image digest probe differs")
    role = by_id[PROBE_IDS[11]]
    if role != {
        "campaign_role": "campaign_experiment_sandbox_only",
        "phase4b_role": "phase4b_parser_sandbox_only",
        "shared_image": True,
    }:
        raise ValueError("role separation probe differs")
    if by_id[PROBE_IDS[12]] != {"forbidden_imports_absent": True}:
        raise ValueError("verifier isolation probe differs")
    if by_id[PROBE_IDS[13]] != trust_block():
        raise ValueError("trust-effect probe differs")
    lying = by_id[PROBE_IDS[14]]
    if lying != {
        "claim_refuted": True, "sandbox_status": "completed",
        "verdict": "target_not_satisfied",
    }:
        raise ValueError("lying-program probe differs")
    absent = by_id[PROBE_IDS[15]]
    if absent != {
        "refusal_code": "sandbox_runtime_unavailable", "replica_count": 1,
        "status": "refused",
    }:
        raise ValueError("absent-runtime probe differs")
    passed = sum(item["passed"] is True for item in probes)
    blocked = len(probes) - passed
    if (
        value["probes_total"] != len(PROBE_IDS)
        or value["probes_flipped"] != passed
        or value["probes_blocked"] != blocked
        or value["status"] != ("activated" if blocked == 0 else "blocked")
        or value["trust"] != trust_block()
    ):
        raise ValueError("campaign sandbox activation summary differs")
    for name in (
        "bootstrap_hash", "campaign_lock_sha256", "environment_hash",
        "phase4b_lock_sha256", "policy_hash", "target_hash",
    ):
        if not isinstance(value[name], str) or not value[name].startswith("sha256:"):
            raise ValueError(f"campaign sandbox {name} is malformed")
    return SandboxActivation(
        schema_version=ACTIVATION_SCHEMA,
        status=value["status"],
        environment_hash=value["environment_hash"],
        policy_hash=value["policy_hash"],
        bootstrap_hash=value["bootstrap_hash"],
        campaign_lock_sha256=value["campaign_lock_sha256"],
        phase4b_lock_sha256=value["phase4b_lock_sha256"],
        target_hash=value["target_hash"],
        probes_total=value["probes_total"],
        probes_flipped=value["probes_flipped"],
        probes_blocked=value["probes_blocked"],
        content_hash=value["content_hash"],
    )


def load_campaign_experiment_activation(data: bytes) -> tuple[dict[str, Any], SandboxActivation]:
    if not isinstance(data, bytes) or not data or len(data) > MAX_ACTIVATION_BYTES:
        raise ValueError("campaign sandbox activation byte bound differs")
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ValueError("campaign sandbox activation contains a duplicate key")
            result[key] = item
        return result
    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("campaign sandbox activation JSON is invalid") from error
    if canonical_bytes(value) != data:
        raise ValueError("campaign sandbox activation is not canonical")
    return value, verify_campaign_experiment_activation(value)


__all__ = [
    "MAX_ACTIVATION_BYTES", "PROBE_IDS", "REPORT_SCHEMA",
    "load_campaign_experiment_activation", "run_campaign_experiment_activation",
    "verify_campaign_experiment_activation",
]
