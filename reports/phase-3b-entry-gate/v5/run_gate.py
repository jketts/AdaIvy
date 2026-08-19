#!/usr/bin/env python3
"""Bounded Phase 3B dynamic-input entry-gate v5; no model/API access."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
V4_FIXTURES = HERE.parent / "v4" / "fixtures"
IMAGE = "adaivy-phase3b-gate-v5:lean-v4.32.1"
OUTPUT = HERE / "fixture-results-v5.json"
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
    "F12": "output_limit_exceeded",
    "D13": "kernel_checked",
}
MAX_RETAINED = 8192
MAX_INPUT_BYTES = 256 * 1024
FIXED_INPUT_PATH = "/tmp/adaivy-input.lean"
TMPFS_POLICY = "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture_bytes(fixture_id: str) -> bytes:
    if fixture_id == "D13":
        return (HERE / "fixtures" / "D13.lean").read_bytes()
    return (V4_FIXTURES / f"{fixture_id}.lean").read_bytes()


def docker_create(name: str, argument: str | None = None) -> None:
    command = [
        "docker", "create", "--name", name, "--interactive",
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64",
        "--cpus", "1", "--memory", "1536m", "--memory-swap", "1536m",
        "--ulimit", "nofile=64:64", "--stop-timeout", "1",
        "--tmpfs", TMPFS_POLICY,
        IMAGE,
    ]
    if argument is not None:
        command.append(argument)
    subprocess.run(
        command, check=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, timeout=20,
    )


def run_container(
    name: str,
    source: bytes,
    *,
    timeout: float = 20.0,
    argument: str | None = None,
) -> dict[str, object]:
    docker_create(name, argument)
    started = time.monotonic()
    process = subprocess.Popen(
        ["docker", "start", "--attach", "--interactive", name],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(input=source, timeout=timeout)
        exit_code = process.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
        exit_code = 124
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name], check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
        )
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_ms_noncanonical": int((time.monotonic() - started) * 1000),
        "stdout_length": len(stdout),
        "stdout_sha256": sha256(stdout),
        "stdout_retained": stdout[:MAX_RETAINED].decode("utf-8", "replace"),
        "stdout_truncated": len(stdout) > MAX_RETAINED,
        "stderr_length": len(stderr),
        "stderr_sha256": sha256(stderr),
        "stderr_retained": stderr[:MAX_RETAINED].decode("utf-8", "replace"),
        "stderr_truncated": len(stderr) > MAX_RETAINED,
    }


def classify(fixture_id: str, source: bytes, result: dict[str, object]) -> str:
    combined = str(result["stdout_retained"]) + str(result["stderr_retained"])
    if fixture_id in {"F02", "F03"}:
        placeholder = b"sorry" in source or b"admit" in source
        return "rejected_placeholder" if placeholder and "sorryAx" in combined else "unexpected"
    if fixture_id in {"F06", "F10", "F11"}:
        return "rejected_policy_violation" if result["exit_code"] != 0 else "unexpected"
    if fixture_id in {"F01", "D13"}:
        return "kernel_checked" if result["exit_code"] == 0 and "does not depend on any axioms" in combined else "unexpected"
    if fixture_id in {"F04", "F05"}:
        return "elaboration_failed" if result["exit_code"] != 0 else "unexpected"
    if fixture_id == "F07":
        return "kernel_checked_with_unapproved_assumptions" if result["exit_code"] == 0 and "AdaIvyGateAssumption" in combined else "unexpected"
    if fixture_id == "F08":
        approved = ("propext" in combined and "Classical.choice" in combined and "Quot.sound" in combined)
        return "kernel_checked_with_approved_classical_axioms" if result["exit_code"] == 0 and approved else "unexpected"
    if fixture_id == "F09":
        return "resource_limit_exceeded" if result["timed_out"] or result["exit_code"] != 0 else "unexpected"
    if fixture_id == "F12":
        return "output_limit_exceeded" if result["stdout_truncated"] or result["stderr_truncated"] else "unexpected"
    return "unexpected"


def canonical_record(
    fixture_id: str,
    source: bytes,
    expected: str,
    observed: str,
    result: dict[str, object],
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "source_sha256": sha256(source),
        "source_length": len(source),
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


def boundary_probes(round_number: int) -> list[dict[str, object]]:
    cases = (
        ("empty_stdin", b"", None, 65),
        ("oversized_stdin", b"x" * (MAX_INPUT_BYTES + 1), None, 68),
        ("path_argument", b"", "/trusted/F01.lean", 64),
        ("exact_limit", b" " * (MAX_INPUT_BYTES - 1) + b"\n", None, 0),
    )
    probes = []
    for probe_id, source, argument, expected_exit in cases:
        result = run_container(
            f"adaivy-v5-r{round_number}-probe-{probe_id.replace('_', '-')}",
            source, timeout=20, argument=argument,
        )
        canonical = {
            "probe_id": probe_id,
            "source_length": len(source),
            "source_sha256": sha256(source),
            "argument": argument,
            "expected_exit_code": expected_exit,
            "observed_exit_code": result["exit_code"],
            "timed_out": result["timed_out"],
            "stdout_length": result["stdout_length"],
            "stdout_sha256": result["stdout_sha256"],
            "stderr_length": result["stderr_length"],
            "stderr_sha256": result["stderr_sha256"],
        }
        probes.append({
            **result,
            **canonical,
            "passed": result["exit_code"] == expected_exit and not result["timed_out"],
            "canonical_sha256": sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()),
        })
    return probes


def main() -> int:
    rounds = []
    fixture_hashes = {fixture_id: [] for fixture_id in FIXTURES}
    probe_hashes: dict[str, list[str]] = {}
    all_passed = True
    for round_number, round_kind in enumerate(("repeat_1", "repeat_2", "clean_restart"), 1):
        policy = run_container(
            f"adaivy-v5-r{round_number}-policy", b"",
            argument="--policy-self-test", timeout=10,
        )
        policy_json = json.loads(str(policy["stdout_retained"]))
        fixture_records = []
        for fixture_id, expected in FIXTURES.items():
            source = fixture_bytes(fixture_id)
            timeout = 2.0 if fixture_id == "F09" else 20.0
            result = run_container(
                f"adaivy-v5-r{round_number}-{fixture_id.lower()}", source,
                timeout=timeout,
            )
            observed = classify(fixture_id, source, result)
            passed = observed == expected
            canonical = canonical_record(fixture_id, source, expected, observed, result)
            canonical_hash = sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode())
            fixture_hashes[fixture_id].append(canonical_hash)
            fixture_records.append({
                **result,
                "fixture_id": fixture_id,
                "source_sha256": sha256(source),
                "source_length": len(source),
                "expected": expected,
                "observed": observed,
                "passed": passed,
                "canonical_sha256": canonical_hash,
            })
            all_passed = all_passed and passed
        probes = boundary_probes(round_number)
        for probe in probes:
            probe_hashes.setdefault(str(probe["probe_id"]), []).append(str(probe["canonical_sha256"]))
        policy_passed = (
            policy["exit_code"] == 0
            and policy_json["passed"]
            and policy_json["fixed_input_path"] == FIXED_INPUT_PATH
            and policy_json["max_input_bytes"] == MAX_INPUT_BYTES
        )
        all_passed = all_passed and policy_passed and all(bool(item["passed"]) for item in probes)
        rounds.append({
            "round": round_number,
            "kind": round_kind,
            "policy_probe": policy_json,
            "policy_probe_exit_code": policy["exit_code"],
            "fixtures": fixture_records,
            "boundary_probes": probes,
        })

    canonical_stable = (
        all(len(set(values)) == 1 for values in fixture_hashes.values())
        and all(len(set(values)) == 1 for values in probe_hashes.values())
    )
    d13 = [
        fixture for round_record in rounds for fixture in round_record["fixtures"]
        if fixture["fixture_id"] == "D13"
    ]
    fixed_path_observed = len(d13) == 3 and all(
        FIXED_INPUT_PATH in str(item["stdout_retained"]) for item in d13
    )
    report = {
        "schema_version": "adaivy.phase3b-dynamic-input-fixtures.v5",
        "status": "passed" if all_passed and canonical_stable and fixed_path_observed else "blocked",
        "image": IMAGE,
        "input_contract": {
            "transport": "stdin",
            "fixed_container_path": FIXED_INPUT_PATH,
            "max_input_bytes": MAX_INPUT_BYTES,
            "path_arguments_allowed": False,
            "tmpfs": TMPFS_POLICY,
        },
        "sandbox_policy": {
            "network": "none",
            "rootfs": "read_only",
            "capabilities": [],
            "no_new_privileges": True,
            "user": "65532:65532",
            "pids_limit": 64,
            "cpus": 1,
            "memory_bytes": 1610612736,
            "memory_swap_bytes": 1610612736,
            "nofile": 64,
            "tmpfs": TMPFS_POLICY,
            "host_mounts": [],
            "docker_socket_mount": False,
        },
        "canonical_hashes_by_fixture": fixture_hashes,
        "canonical_hashes_by_boundary_probe": probe_hashes,
        "canonical_across_repeats_and_restart": canonical_stable,
        "all_expected_classifications_passed": all_passed,
        "fixed_input_path_observed_in_dynamic_diagnostics": fixed_path_observed,
        "adaivy_model_calls": 0,
        "adaivy_external_api_calls": 0,
        "rounds": rounds,
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "canonical": canonical_stable,
        "rounds": len(rounds),
        "fixtures_per_round": len(FIXTURES),
        "boundary_probes_per_round": 4,
        "output": str(OUTPUT),
    }, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
