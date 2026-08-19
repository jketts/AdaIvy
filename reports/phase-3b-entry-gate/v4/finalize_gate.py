#!/usr/bin/env python3
"""Evaluate every Phase 3B entry-gate v4 condition and seal the result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "entry-gate-v4.json"
V3_IMAGE = "adaivy-phase3b-gate:lean-v4.32.1"
V4_IMAGE = "adaivy-phase3b-gate-v4:lean-v4.32.1"
V3_DIGEST = "sha256:0d3a26db46d1bace987b273d59087e3e39fbc9901d2bd680bf251f190622eac3"
V4_DIGEST = "sha256:ad81d799c1d9e766e0263c2b703936ca3fb8042e189e7e279b7abd1c7889c60b"
V3_REPORTS = {
    "docker-entry-gate-v3.json": "232e90b95c693a3bb7ff44318e1730b5f2168af2d08855a8378a7c374f2f442f",
    "docker-fixture-results-v3.json": "bb6d8d37543ab578445cfbfd497ede9d61f3d4f3a5a54847c21333554d9bdda4",
    "docker-access-blocked-v2.json": "d6546544169ea05dc6ad8386d499da6e04ae7e870b71bff2d95d0bafc0ff643c",
}


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def docker_inspect(image: str) -> dict:
    result = subprocess.run(
        ["docker", "image", "inspect", image], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )
    return json.loads(result.stdout)[0]


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, timeout=30,
    ).stdout.strip()


def main() -> int:
    acquisition = load("acquisition-manifest-v4.json")
    inventory = load("executable-inventory-v4.json")
    runtime = load("runtime-manifest-v4.json")
    fixtures = load("fixture-results-v4.json")
    replay = load("replay-comparison-v4.json")
    repository = load("repository-verification-v4.json")
    credentials = load("credential-scan-v4.json")
    v3 = docker_inspect(V3_IMAGE)
    v4 = docker_inspect(V4_IMAGE)
    relevant_containers = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=adaivy-v4-", "--format", "{{.ID}}"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        timeout=30,
    ).stdout.split()
    v3_hashes = {
        filename: sha256(HERE.parent / filename) for filename in V3_REPORTS
    }
    policy_rounds = [item["policy_probe"] for item in fixtures["rounds"]]
    required_attempts = {
        "/bin/sh", "/bin/bash", "/usr/bin/env", "/checker/launcher",
        "/lib/ld-linux-aarch64.so.1", "tmpfs_copy", "tmpfs_shebang",
        "execveat", "memfd_create",
    }
    all_policy_attempts_present = all(
        required_attempts <= set(probe["attempts"]) for probe in policy_rounds
    )
    all_policy_attempts_rejected = all(
        probe["passed"]
        and probe["attempts"]["/bin/sh"] != 0
        and probe["attempts"]["/bin/bash"] != 0
        and probe["attempts"]["/usr/bin/env"] != 0
        and probe["attempts"]["/checker/launcher"] != 0
        and probe["attempts"]["/lib/ld-linux-aarch64.so.1"] != 0
        and probe["attempts"]["tmpfs_copy"] != 0
        and probe["attempts"]["tmpfs_shebang"] != 0
        and probe["attempts"]["execveat"] == 1
        and probe["attempts"]["memfd_create"] == 1
        for probe in policy_rounds
    )
    f01 = [
        fixture for round_record in fixtures["rounds"]
        for fixture in round_record["fixtures"] if fixture["fixture_id"] == "F01"
    ]
    conditions = {
        "no_floating_or_latest_acquisition": acquisition["all_acquisitions_exact"] and not acquisition["floating_acquisition_urls"],
        "elan_exact_release_digest_verified": acquisition["acquisitions"][0]["digest_verified"] and acquisition["acquisitions"][0]["github_published_digest"] is not None,
        "every_acquisition_exact_and_digest_verified": acquisition["all_acquisitions_exact"] and acquisition["all_acquisitions_digest_verified"],
        "final_executable_inventory_equals_allowlist": inventory["inventory_equals_approved_manifest"] and not inventory["non_allowlisted_executables"],
        "no_forbidden_runtime_tools": not inventory["forbidden_runtime_paths"] and not runtime["elan_present"] and not runtime["lake_present"] and not runtime["compiler_or_linker_present"] and not runtime["shell_present"],
        "landlock_execute_supported": all(probe["landlock_abi"] >= 1 for probe in policy_rounds),
        "all_executable_policy_attempts_present": all_policy_attempts_present,
        "all_nonallowlisted_and_memory_execution_rejected": all_policy_attempts_rejected,
        "lean_starts_and_valid_proof_checks": len(f01) == 3 and all(item["exit_code"] == 0 and item["observed"] == "kernel_checked" for item in f01),
        "all_12_fixtures_pass_two_repeats_and_restart": fixtures["all_expected_classifications_passed"] and len(fixtures["rounds"]) == 3 and all(len(item["fixtures"]) == 12 for item in fixtures["rounds"]),
        "canonical_across_repeats_and_restart": fixtures["canonical_across_repeats_and_restart"],
        "same_fixture_bytes_as_v3": replay["same_fixture_bytes"],
        "distinct_v3_v4_runtime_manifests": replay["distinct_runtime_manifests"],
        "v3_reports_unchanged": v3_hashes == V3_REPORTS,
        "v3_image_unchanged": v3["Id"] == V3_DIGEST and v3["Size"] == 3423169517,
        "v4_image_matches_sealed_manifest": v4["Id"] == V4_DIGEST and v4["Config"]["Entrypoint"] == ["/checker/launcher"] and v4["Config"]["User"] == "65532:65532",
        "no_gate_containers_remaining": not relevant_containers,
        "all_156_tests_pass": repository["unit_tests"]["observed"] == 156 and repository["status"] == "passed",
        "phase0_19_checks_pass": repository["phase0"]["observed"] == 19,
        "json_and_schema_validation_pass": not repository["json_validation"]["errors"] and repository["schema_validation"]["schema_document_count"] == 10,
        "protected_seals_pass": all(item["passed"] for item in repository["seal_verification"].values()),
        "credential_scan_pass": credentials["status"] == "passed" and credentials["exact_credential_match_count"] == 0 and credentials["token_pattern_match_count"] == 0,
        "no_adaivy_model_or_api_calls": fixtures["adaivy_model_calls"] == 0 and fixtures["adaivy_external_api_calls"] == 0 and repository["adaivy_model_api_calls_during_gate"] == 0,
        "head_and_origin_unchanged": git("rev-parse", "HEAD") == "6cf2af202a44e42dc29b81abb34036eadcf3a345" and git("rev-parse", "origin/main") == "6cf2af202a44e42dc29b81abb34036eadcf3a345",
    }
    passed = all(conditions.values())
    report = {
        "schema_version": "adaivy.phase3b-entry-gate.v4",
        "attempt_id": "phase3b.entry-gate-repair.v4",
        "scope_commit": "26942d97abe0c79cd908f7fe4561d42ddfc9d5da",
        "status": "passed" if passed else "blocked",
        "candidate": "Lean 4 plus mathlib",
        "conditions": conditions,
        "security": {
            "ordinary_seccomp_claimed_as_path_allowlist": False,
            "landlock_abi": sorted({probe["landlock_abi"] for probe in policy_rounds}),
            "path_policy": "initial exact Lean+ELF-loader bootstrap; nested pre-main Landlock ruleset permits exact Lean only and is inherited by descendants",
            "seccomp": "Docker default profile plus launcher BPF denying execveat and memfd_create",
            "docker_controls": fixtures["sandbox_policy"],
            "policy_rounds": policy_rounds,
            "destructive_host_escape_testing": False,
        },
        "runtime": {
            "v3_image_digest": v3["Id"],
            "v3_image_size_bytes": v3["Size"],
            "v4_image_digest": v4["Id"],
            "v4_image_size_bytes": v4["Size"],
            "executable_allowlist": inventory["approved_manifest"],
            "executable_inventory": [item["path"] for item in inventory["executables"]],
            "relevant_containers_remaining": relevant_containers,
        },
        "evidence": {
            "acquisition": "acquisition-manifest-v4.json",
            "runtime": "runtime-manifest-v4.json",
            "executable_inventory": "executable-inventory-v4.json",
            "fixture_results": "fixture-results-v4.json",
            "replay_comparison": "replay-comparison-v4.json",
            "repository_verification": "repository-verification-v4.json",
            "credential_scan": "credential-scan-v4.json",
            "v3_report_sha256": v3_hashes,
        },
        "scope_guards": {
            "production_phase3b_changes": 0,
            "formal_warrants_created": 0,
            "adaivy_model_calls": 0,
            "adaivy_external_api_calls": 0,
            "commits_created": 0,
            "tags_created": 0,
            "pushes": 0,
            "published": False,
            "adr_0015_status_before_gate_decision": "proposed",
        },
        "failed_attempts_preserved": acquisition["rejected_non_candidate_attempts"],
        "decision": "accept ADR-0015 and produce a separate bounded production Phase 3B prompt" if passed else "remain blocked and preserve evidence",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "conditions": len(conditions), "passed": sum(conditions.values()), "output": str(OUTPUT)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
