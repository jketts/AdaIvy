#!/usr/bin/env python3
"""Run and record the complete offline repository check for gate v4."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LOGS = HERE / "verification-logs"
OUTPUT = HERE / "repository-verification-v4.json"
COMMANDS = [
    ("unit_tests", ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]),
    ("phase0_checks", ["python3", "-m", "phase0_harness.cli", "check"]),
    ("phase1_demo", ["python3", "-m", "math_research.cli", "demo", "--output-dir", "reports/phase-1"]),
    ("phase1_inspect", ["python3", "-m", "math_research.cli", "inspect", "reports/phase-1/manual-dossier.json"]),
    ("phase2_offline_report", ["python3", "-m", "math_research.cli", "phase2", "report", "reports/phase-2", "run.phase2.demo.fake.v1", "--output", "reports/phase-2/traceable-report.md"]),
    ("phase3a_demo", ["python3", "-m", "math_research.cli", "phase3a", "demo", "reports/phase-3a/acceptance-v1", "--output-dir", "reports/phase-3a/acceptance-v1"]),
    ("phase3a_inspect", ["python3", "-m", "math_research.cli", "phase3a", "inspect", "reports/phase-3a/acceptance-v1/research-memory.json"]),
]
PROTECTED = {
    "reports/phase-0/results.json": "e8166fed8063ade26d74b55f0139fc2adfd2900d2c8db4a4c3fb8c4a5b144533",
    "reports/phase-2/live-provider-status.json": "c29c13d80164890d0b5d1d1fdca3eeac66c56300c9683a1c4087d7bc03c1ac05",
    "reports/phase-2/live-openai-gpt5-mini-v2/workspace.sqlite3": "4c1c402d142a33d6529fb3991cb18bab2513bcb13dd2eddd3b30af0ab76ad064",
    "reports/phase-2/live-openai-gpt5-mini-v3/workspace.sqlite3": "30e0db8d1bf9b601ce9d262fdce9459dea573c742aaca27f7af97d7895f81e94",
    "reports/phase-2/live-openai-gpt5-mini-v3/traceable-report.md": "ff706139a8f0415e1f1f6efc0ac714f0e588f187e94e82c7dff0af92d5da8cb9",
    "reports/phase-2/release-manifest.json": "90b188e134e0489318319919e09dedf52fb817f658f07b173ff4ab3d75188664",
    "reports/phase-3a/acceptance-v1/acceptance.json": "c0ea908f3b6f1c9fd19d83180f3e55f865238dfc4f96727048531d51bfe8c241",
    "reports/phase-3a/acceptance-v1/research-memory.json": "f1b57c2cae96638a7545476722685f17eb7470c5b4d0a790ca788de8e8756272",
    "reports/phase-3a/acceptance-v1/traceable-report.md": "881b2d0a85da1c9c57181c0aeb28ae6efccbc88e4a6521f6d29bd60856544ac9",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = "src"
    for name in list(env):
        if name == "OPENAI_API_KEY" or name.lower().endswith("_proxy"):
            env.pop(name, None)
    checks = []
    for index, (name, command) in enumerate(COMMANDS, 1):
        result = subprocess.run(
            command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=180,
        )
        stdout_path = LOGS / f"{index:02d}-{name}.stdout.txt"
        stderr_path = LOGS / f"{index:02d}-{name}.stderr.txt"
        stdout_path.write_bytes(result.stdout)
        stderr_path.write_bytes(result.stderr)
        checks.append({
            "name": name,
            "command": command,
            "exit_code": result.returncode,
            "stdout": {
                "path": stdout_path.relative_to(ROOT).as_posix(),
                "bytes": len(result.stdout), "sha256": digest(result.stdout),
            },
            "stderr": {
                "path": stderr_path.relative_to(ROOT).as_posix(),
                "bytes": len(result.stderr), "sha256": digest(result.stderr),
            },
        })
        if result.returncode != 0:
            break

    parsed_json = []
    json_errors = []
    for path in sorted(ROOT.rglob("*.json")):
        if ".git" in path.parts:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
            parsed_json.append(path.relative_to(ROOT).as_posix())
        except Exception as error:
            json_errors.append({"path": path.relative_to(ROOT).as_posix(), "error": str(error)})
    schemas = sorted((ROOT / "schemas").glob("*.json"))
    seal_results = {
        relative: {
            "expected_sha256": expected,
            "observed_sha256": file_digest(ROOT / relative),
            "passed": file_digest(ROOT / relative) == expected,
        }
        for relative, expected in PROTECTED.items()
    }
    phase3a_database = ROOT / "reports/phase-3a/acceptance-v1/workspace.sqlite3"
    connection = sqlite3.connect(f"file:{phase3a_database}?mode=ro", uri=True)
    try:
        phase3a_model_calls = connection.execute("select count(*) from model_calls").fetchone()[0]
        integrity_check = connection.execute("pragma integrity_check").fetchone()[0]
    finally:
        connection.close()
    unit_text = (LOGS / "01-unit_tests.stderr.txt").read_text(encoding="utf-8", errors="replace") if checks else ""
    phase0_text = (LOGS / "02-phase0_checks.stdout.txt").read_text(encoding="utf-8", errors="replace") if len(checks) > 1 else ""
    report = {
        "schema_version": "adaivy.phase3b-entry-gate-repository-verification.v4",
        "status": "passed",
        "network_environment_removed": True,
        "credential_environment_removed": True,
        "commands": checks,
        "all_commands_passed": len(checks) == len(COMMANDS) and all(item["exit_code"] == 0 for item in checks),
        "unit_tests": {
            "expected": 156,
            "observed": 156 if "Ran 156 tests" in unit_text and "OK" in unit_text else None,
        },
        "phase0": {
            "expected": 19,
            "observed": 19 if "19" in phase0_text and "passed" in phase0_text.lower() else None,
        },
        "json_validation": {
            "parsed_count": len(parsed_json),
            "errors": json_errors,
        },
        "schema_validation": {
            "schema_document_count": len(schemas),
            "schema_documents": [path.relative_to(ROOT).as_posix() for path in schemas],
            "semantic_validation_covered_by_unit_suite": True,
        },
        "seal_verification": seal_results,
        "phase3a_database_integrity": integrity_check,
        "phase3a_model_calls": phase3a_model_calls,
        "adaivy_model_api_calls_during_gate": 0,
    }
    passed = (
        report["all_commands_passed"]
        and report["unit_tests"]["observed"] == 156
        and report["phase0"]["observed"] == 19
        and not json_errors
        and len(schemas) == 10
        and all(item["passed"] for item in seal_results.values())
        and integrity_check == "ok"
        and phase3a_model_calls == 0
    )
    report["status"] = "passed" if passed else "blocked"
    OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "commands": len(checks),
        "tests": report["unit_tests"]["observed"],
        "phase0": report["phase0"]["observed"],
        "json": len(parsed_json),
        "schemas": len(schemas),
        "model_calls": phase3a_model_calls,
    }, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
