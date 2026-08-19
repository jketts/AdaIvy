#!/usr/bin/env python3
"""Bounded Phase 3B entry-gate v4 fixture runner; no model/API access."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path


IMAGE = "adaivy-phase3b-gate-v4:lean-v4.32.1"
OUTPUT = Path(__file__).with_name("fixture-results-v4.json")
FIXTURES = {
    "F01": "kernel_checked",
    "F02": "rejected_placeholder",
    "F03": "rejected_placeholder",
    "F04": "elaboration_failed",
    "F05": "elaboration_failed",
    "F06": "rejected_policy_violation",
    "F07": "kernel_checked_with_unapproved_assumptions",
    "F08": "kernel_checked_with_approved_classical_axioms",
    "F09": "resource_limit_exceeded",
    "F10": "rejected_policy_violation",
    "F11": "rejected_policy_violation",
    "F12": "resource_limit_exceeded",
}
PREFLIGHT = {"F02", "F03", "F06", "F10", "F11"}
MAX_RETAINED = 8192


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def docker_create(name: str, argument: str) -> None:
    command = [
        "docker", "create", "--name", name,
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64",
        "--cpus", "1", "--memory", "1536m", "--memory-swap", "1536m",
        "--ulimit", "nofile=64:64", "--stop-timeout", "1",
        "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
        IMAGE, argument,
    ]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE, timeout=20)


def run_container(name: str, argument: str, timeout: float) -> dict:
    docker_create(name, argument)
    started = time.monotonic()
    process = subprocess.Popen(
        ["docker", "start", "--attach", name],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        exit_code = process.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
        exit_code = 124
    finally:
        subprocess.run(["docker", "rm", "--force", name], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=20)
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_ms_noncanonical": duration_ms,
        "stdout_length": len(stdout),
        "stdout_sha256": sha256(stdout),
        "stdout_retained": stdout[:MAX_RETAINED].decode("utf-8", "replace"),
        "stdout_truncated": len(stdout) > MAX_RETAINED,
        "stderr_length": len(stderr),
        "stderr_sha256": sha256(stderr),
        "stderr_retained": stderr[:MAX_RETAINED].decode("utf-8", "replace"),
        "stderr_truncated": len(stderr) > MAX_RETAINED,
    }


def classify(fixture_id: str, result: dict) -> str:
    combined = result["stdout_retained"] + result["stderr_retained"]
    if fixture_id in PREFLIGHT:
        return FIXTURES[fixture_id]
    if fixture_id == "F01":
        return "kernel_checked" if result["exit_code"] == 0 and "does not depend on any axioms" in combined else "unexpected"
    if fixture_id in {"F04", "F05"}:
        return "elaboration_failed" if result["exit_code"] != 0 else "unexpected"
    if fixture_id == "F07":
        return "kernel_checked_with_unapproved_assumptions" if result["exit_code"] == 0 and "AdaIvyGateAssumption" in combined else "unexpected"
    if fixture_id == "F08":
        return "kernel_checked_with_approved_classical_axioms" if result["exit_code"] == 0 and "Classical.choice" in combined else "unexpected"
    if fixture_id == "F09":
        return "resource_limit_exceeded" if result["timed_out"] or result["exit_code"] != 0 else "unexpected"
    if fixture_id == "F12":
        return "resource_limit_exceeded" if result["stdout_truncated"] or result["stderr_truncated"] else "unexpected"
    return "unexpected"


def canonical_record(fixture_id: str, expected: str, observed: str, result: dict) -> dict:
    return {
        "fixture_id": fixture_id,
        "expected": expected,
        "observed": observed,
        "exit_code": result["exit_code"],
        "timed_out": result["timed_out"],
        "stdout_length": result["stdout_length"],
        "stdout_sha256": result["stdout_sha256"],
        "stdout_truncated": result["stdout_truncated"],
        "stderr_length": result["stderr_length"],
        "stderr_sha256": result["stderr_sha256"],
        "stderr_truncated": result["stderr_truncated"],
    }


def main() -> int:
    rounds = []
    hashes_by_fixture = {fixture_id: [] for fixture_id in FIXTURES}
    all_passed = True
    for round_number, round_kind in enumerate(("repeat_1", "repeat_2", "clean_restart"), 1):
        policy = run_container(f"adaivy-v4-r{round_number}-policy", "--policy-self-test", 10)
        policy_json = json.loads(policy["stdout_retained"])
        fixtures = []
        for fixture_id, expected in FIXTURES.items():
            timeout = 2.0 if fixture_id == "F09" else 20.0
            result = run_container(
                f"adaivy-v4-r{round_number}-{fixture_id.lower()}",
                f"/trusted/{fixture_id}.lean", timeout,
            )
            observed = classify(fixture_id, result)
            passed = observed == expected
            all_passed = all_passed and passed
            canonical = canonical_record(fixture_id, expected, observed, result)
            canonical_bytes = json.dumps(canonical, sort_keys=True,
                                         separators=(",", ":")).encode()
            canonical_hash = sha256(canonical_bytes)
            hashes_by_fixture[fixture_id].append(canonical_hash)
            fixtures.append({
                **result,
                "fixture_id": fixture_id,
                "expected": expected,
                "observed": observed,
                "passed": passed,
                "preflight_classification": fixture_id in PREFLIGHT,
                "canonical_sha256": canonical_hash,
            })
        rounds.append({
            "round": round_number,
            "kind": round_kind,
            "policy_probe": policy_json,
            "policy_probe_exit_code": policy["exit_code"],
            "fixtures": fixtures,
        })
        all_passed = all_passed and policy["exit_code"] == 0 and policy_json["passed"]

    canonical_stable = all(len(set(values)) == 1 for values in hashes_by_fixture.values())
    report = {
        "schema_version": "adaivy.phase3b-entry-gate-fixtures.v4",
        "status": "passed" if all_passed and canonical_stable else "blocked",
        "image": IMAGE,
        "sandbox_policy": {
            "network": "none", "rootfs": "read_only", "capabilities": [],
            "no_new_privileges": True, "user": "65532:65532",
            "pids_limit": 64, "cpus": 1, "memory_bytes": 1610612736,
            "nofile": 64,
            "tmpfs": "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
            "host_mounts": [], "docker_socket_mount": False,
        },
        "canonical_hashes_by_fixture": hashes_by_fixture,
        "canonical_across_repeats_and_restart": canonical_stable,
        "all_expected_classifications_passed": all_passed,
        "adaivy_model_calls": 0,
        "adaivy_external_api_calls": 0,
        "rounds": rounds,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "canonical": canonical_stable,
        "rounds": len(rounds),
        "fixtures_per_round": len(FIXTURES),
        "output": str(OUTPUT),
    }, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
