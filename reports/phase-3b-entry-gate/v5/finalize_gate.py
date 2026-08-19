#!/usr/bin/env python3
"""Evaluate every dynamic-input entry-gate v5 condition and seal the result."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "entry-gate-v5.json"
V3_IMAGE = "adaivy-phase3b-gate:lean-v4.32.1"
V4_IMAGE = "adaivy-phase3b-gate-v4:lean-v4.32.1"
V5_IMAGE = "adaivy-phase3b-gate-v5:lean-v4.32.1"
V3_DIGEST = "sha256:0d3a26db46d1bace987b273d59087e3e39fbc9901d2bd680bf251f190622eac3"
V4_DIGEST = "sha256:ad81d799c1d9e766e0263c2b703936ca3fb8042e189e7e279b7abd1c7889c60b"
V5_DIGEST = "sha256:39457cf097e89537ac90e7ddee08cbda8f7f2d49e443cc60a87d6d02d8cb896f"
SCOPE_HEAD = "1342827a4ec9736e47cc20d32475b71100c68496"
ORIGINAL_PROMPT_SHA256 = "28e1fa0e714b3901b77fb6bb30648af0df4a8fd750f3b4135ee07577d0976c16"
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
    acquisition = load("acquisition-manifest-v5.json")
    inventory = load("executable-inventory-v5.json")
    preservation = load("v4-preservation-v5.json")
    runtime = load("runtime-manifest-v5.json")
    fixtures = load("fixture-results-v5.json")
    failed_attempt = load("fixture-results-v5-attempt1.json")
    repository = load("repository-verification-v5.json")
    credentials = load("credential-scan-v5.json")
    v3 = docker_inspect(V3_IMAGE)
    v4 = docker_inspect(V4_IMAGE)
    v5 = docker_inspect(V5_IMAGE)
    relevant_containers = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=adaivy-v5-", "--format", "{{.ID}}"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        timeout=30,
    ).stdout.split()
    v3_hashes = {
        filename: sha256(HERE.parent / filename) for filename in V3_REPORTS
    }
    v4_observed = {
        path.relative_to(ROOT).as_posix(): sha256(path)
        for path in sorted((HERE.parent / "v4").rglob("*")) if path.is_file()
    }
    original_prompt = ROOT / "docs/phase-3b/BOUNDED_IMPLEMENTATION_PROMPT.md"
    successor_prompt = ROOT / "docs/phase-3b/BOUNDED_IMPLEMENTATION_PROMPT_V5.md"
    policy_adr = ROOT / "docs/adrs/0016-phase3b-bounded-stdin-runtime.md"
    status_paths = []
    for line in git("status", "--porcelain").splitlines():
        if line:
            status_paths.append(line[3:])
    forbidden_scope_prefixes = (
        "src/", "tests/", "schemas/", "migrations/", "fixtures/",
        "benchmarks/quantum", "src/math_research/benchmarks/quantum",
    )
    production_or_quantum_paths = sorted(
        path for path in status_paths if path.startswith(forbidden_scope_prefixes)
    )

    v4_sandbox = json.loads((HERE.parent / "v4/fixture-results-v4.json").read_text())["sandbox_policy"]
    controls_preserved = all(fixtures["sandbox_policy"].get(key) == value for key, value in v4_sandbox.items())
    policy_rounds = [item["policy_probe"] for item in fixtures["rounds"]]
    required_attempts = {
        "/bin/sh", "/bin/bash", "/usr/bin/env", "/checker/launcher",
        "/lib/ld-linux-aarch64.so.1", "tmpfs_copy", "tmpfs_shebang",
        "execveat", "memfd_create",
    }
    policy_attempts_passed = all(
        probe["passed"]
        and required_attempts <= set(probe["attempts"])
        and probe["attempts"]["/bin/sh"] != 0
        and probe["attempts"]["/bin/bash"] != 0
        and probe["attempts"]["/usr/bin/env"] != 0
        and probe["attempts"]["/checker/launcher"] != 0
        and probe["attempts"]["/lib/ld-linux-aarch64.so.1"] != 0
        and probe["attempts"]["tmpfs_copy"] != 0
        and probe["attempts"]["tmpfs_shebang"] != 0
        and probe["attempts"]["execveat"] == 1
        and probe["attempts"]["memfd_create"] == 1
        and probe["fixed_input_path"] == "/tmp/adaivy-input.lean"
        and probe["max_input_bytes"] == 262144
        for probe in policy_rounds
    )
    all_boundary_probes = [
        probe for round_record in fixtures["rounds"]
        for probe in round_record["boundary_probes"]
    ]
    boundary_ids = {probe["probe_id"] for probe in all_boundary_probes}
    v4_fixture_hashes = json.loads((HERE.parent / "v4/runtime-manifest-v4.json").read_text())["trusted_fixture_sha256"]
    v5_fixture_hashes = {
        item["fixture_id"]: item["source_sha256"]
        for item in fixtures["rounds"][0]["fixtures"]
        if item["fixture_id"].startswith("F")
    }
    first_attempt_d13 = [
        fixture for round_record in failed_attempt["rounds"]
        for fixture in round_record["fixtures"] if fixture["fixture_id"] == "D13"
    ]
    failed_attempt_preserved = (
        failed_attempt["status"] == "blocked"
        and len(first_attempt_d13) == 3
        and all(item["observed"] == "unexpected" and "propext" in item["stdout_retained"] for item in first_attempt_d13)
    )
    conditions = {
        "no_network_acquisition_or_toolchain_change": acquisition["status"] == "passed" and not acquisition["network_acquisition_performed"] and not acquisition["toolchain_rebuilt_or_expanded"],
        "v3_image_and_reports_unchanged": v3["Id"] == V3_DIGEST and v3_hashes == V3_REPORTS,
        "v4_image_unchanged": v4["Id"] == V4_DIGEST and v4["Size"] == 651132241,
        "v4_artifacts_unchanged": preservation["v4_report_sha256"] == v4_observed,
        "v5_inherits_exact_v4_rootfs": preservation["v5_inherits_v4_rootfs_diff_ids"] and runtime["rootfs_diff_ids"][:2] == runtime["inherited_v4_rootfs_diff_ids"],
        "only_runtime_launcher_changed": preservation["only_launcher_changed"] and preservation["all_nonlauncher_runtime_files_byte_and_metadata_identical"],
        "v5_image_matches_sealed_manifest": v5["Id"] == V5_DIGEST and v5["Size"] == 651137386 and v5["Config"]["Entrypoint"] == ["/checker/launcher"] and v5["Config"]["User"] == "65532:65532",
        "final_executable_inventory_equals_v4_allowlist": inventory["status"] == "passed" and inventory["inventory_equals_approved_manifest"] and inventory["approved_manifest"] == ["/checker/launcher", "/lib/ld-linux-aarch64.so.1", "/opt/lean/bin/lean"],
        "no_forbidden_runtime_tools": not inventory["forbidden_runtime_paths"] and not inventory["non_allowlisted_executables"] and not runtime["elan_present"] and not runtime["lake_present"] and not runtime["compiler_or_linker_present"] and not runtime["shell_present"],
        "all_v4_docker_controls_preserved": controls_preserved,
        "landlock_seccomp_policy_probe_passes_three_rounds": len(policy_rounds) == 3 and policy_attempts_passed,
        "bounded_stdin_contract_exact": fixtures["input_contract"] == {"fixed_container_path": "/tmp/adaivy-input.lean", "max_input_bytes": 262144, "path_arguments_allowed": False, "tmpfs": "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777", "transport": "stdin"},
        "all_ingress_boundary_probes_pass_three_rounds": len(all_boundary_probes) == 12 and boundary_ids == {"empty_stdin", "oversized_stdin", "path_argument", "exact_limit"} and all(probe["passed"] for probe in all_boundary_probes),
        "dynamic_fixture_not_embedded_and_fixed_path_observed": not runtime["dynamic_fixture_embedded_in_image"] and fixtures["fixed_input_path_observed_in_dynamic_diagnostics"],
        "same_v4_fixture_bytes_over_stdin": v5_fixture_hashes == v4_fixture_hashes,
        "all_13_fixtures_pass_two_repeats_and_restart": fixtures["all_expected_classifications_passed"] and len(fixtures["rounds"]) == 3 and all(len(item["fixtures"]) == 13 for item in fixtures["rounds"]),
        "canonical_across_repeats_and_restart": fixtures["canonical_across_repeats_and_restart"],
        "failed_attempt_preserved_machine_readably": failed_attempt_preserved,
        "all_156_tests_and_repository_commands_pass": repository["status"] == "passed" and repository["unit_tests"]["observed"] == 156 and repository["all_commands_passed"],
        "phase0_19_checks_pass": repository["phase0"]["observed"] == 19,
        "json_and_schema_validation_pass": not repository["json_validation"]["errors"] and repository["schema_validation"]["schema_document_count"] == 10,
        "protected_seals_and_phase3a_cleanliness_pass": all(item["passed"] for item in repository["seal_verification"].values()) and repository["phase3a_tracked_database_unchanged"] and repository["verification_added_no_tracked_diff"],
        "credential_scan_pass": credentials["status"] == "passed" and credentials["exact_credential_match_count"] == 0 and credentials["token_pattern_match_count"] == 0,
        "no_adaivy_model_or_api_calls": fixtures["adaivy_model_calls"] == 0 and fixtures["adaivy_external_api_calls"] == 0 and repository["adaivy_model_api_calls_during_gate"] == 0,
        "scope_head_unchanged": git("rev-parse", "HEAD") == SCOPE_HEAD,
        "no_production_or_quantum_paths_changed": not production_or_quantum_paths,
        "original_production_prompt_unchanged": sha256(original_prompt) == ORIGINAL_PROMPT_SHA256,
        "policy_adr_and_successor_prompt_present": policy_adr.is_file() and "**Status:** accepted" in policy_adr.read_text(encoding="utf-8") and successor_prompt.is_file() and V5_DIGEST in successor_prompt.read_text(encoding="utf-8"),
        "no_v5_containers_remaining": not relevant_containers,
    }
    passed = all(conditions.values())
    report = {
        "schema_version": "adaivy.phase3b-dynamic-input-entry-gate.v5",
        "attempt_id": "phase3b.dynamic-input-entry-gate.v5",
        "scope_commit": SCOPE_HEAD,
        "status": "passed" if passed else "blocked",
        "candidate": "bounded stdin ingestion into sealed Lean 4 plus mathlib runtime",
        "conditions": conditions,
        "input_contract": fixtures["input_contract"],
        "security": {
            "v4_controls_preserved": controls_preserved,
            "docker_controls": fixtures["sandbox_policy"],
            "landlock_abi": sorted({probe["landlock_abi"] for probe in policy_rounds}),
            "path_policy": "v4 exact Lean+ELF-loader bootstrap and nested Lean-only execute policy; stdin source staged at fixed container-only noexec tmpfs path",
            "seccomp": "unchanged v4 Docker default profile plus launcher BPF denying execveat and memfd_create",
            "policy_rounds": policy_rounds,
            "destructive_host_escape_testing": False,
        },
        "runtime": {
            "v3_image_digest": v3["Id"],
            "v4_image_digest": v4["Id"],
            "v4_image_size_bytes": v4["Size"],
            "v5_image_digest": v5["Id"],
            "v5_image_size_bytes": v5["Size"],
            "changed_paths_from_v4": preservation["changed_runtime_paths"],
            "executable_inventory": [item["path"] for item in inventory["executables"]],
            "relevant_containers_remaining": relevant_containers,
        },
        "evidence": {
            "acquisition": "acquisition-manifest-v5.json",
            "runtime": "runtime-manifest-v5.json",
            "executable_inventory": "executable-inventory-v5.json",
            "v4_preservation": "v4-preservation-v5.json",
            "fixture_results": "fixture-results-v5.json",
            "failed_fixture_attempt": "fixture-results-v5-attempt1.json",
            "repository_verification": "repository-verification-v5.json",
            "credential_scan": "credential-scan-v5.json",
            "policy_adr": "docs/adrs/0016-phase3b-bounded-stdin-runtime.md",
            "successor_prompt": "docs/phase-3b/BOUNDED_IMPLEMENTATION_PROMPT_V5.md",
        },
        "scope_guards": {
            "production_phase3b_changes": 0,
            "formal_warrants_created": 0,
            "adaivy_model_calls": 0,
            "adaivy_external_api_calls": 0,
            "quantum_work": 0,
            "commits_created": 0,
            "tags_created": 0,
            "pushes": 0,
            "published": False,
        },
        "failed_attempts_preserved": [
            {
                "id": "v5-d13-simp-approved-axiom-mismatch",
                "accepted_as_candidate": False,
                "result": "gate blocked with stable diagnostics in all three rounds",
                "reason": "the dynamic fixture used simp, which disclosed approved axiom propext while the fixture expected an empty axiom set",
                "repair": "replace only the project-authored gate fixture proof with rfl; runtime and controls unchanged",
                "evidence": "fixture-results-v5-attempt1.json",
                "sha256": sha256(HERE / "fixture-results-v5-attempt1.json"),
            }
        ],
        "decision": "accept ADR-0016 and use the separate v5 bounded production prompt" if passed else "remain blocked and preserve evidence",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "conditions": len(conditions),
        "passed": sum(conditions.values()),
        "output": str(OUTPUT),
    }, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
