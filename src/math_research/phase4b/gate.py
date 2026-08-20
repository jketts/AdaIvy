"""Executable offline evidence for the feasible subset of the Phase 4B gate.

This module never turns unavailable dependency installation or a real OS parser
sandbox into a pass.  It exercises only the standard-library fixture oracle,
injected acquisition ports, durable metadata, and repository preservation
controls that can be proved in the ordinary offline environment.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterator, Sequence

from ..phase4a.records import RightsReason, RightsUse, RightsValue
from ..phase4a.service import Phase4Service
from .acquisition import (
    AcquisitionPolicy, AcquisitionPolicyError, AcquisitionRequest,
    AuthorizedResource, Resolution, RightsDecision, RobotsSnapshot,
    RunAuthorization, TermsSnapshot, TransportRequest, TransportResponse,
    acquire,
)
from .darwin_sandbox import CONTRACT_VERSION as DARWIN_SANDBOX_CONTRACT, DarwinSandboxProbeRunner
from .interchange import replay
from .parsing import (
    HTML_PROFILE, PDF_PROFILE, TEX_PROFILE, ParseRequest, RestrictedStdlibAdapter,
    WorkerExecution, run_parser, verify_result_record,
)
from .records import RecordType
from .serialization import canonical_bytes, canonical_hash, sha256_bytes
from .service import Phase4BService
from .workspace import Phase4BWorkspace


REPORT_SCHEMA = "adaivy.phase4b-feasible-gate-evidence.v5"
MANIFEST_SCHEMA = "adaivy.phase4b-acceptance-manifest.v1"
MAX_REPORT_BYTES = 4_194_304
GATE_POLICY = "fixtures/phase4b/acceptance/feasible-gate-policy.json"
PROTECTED_MANIFEST = "reports/phase-4a-production/protected-evidence-v2.json"
CREDENTIAL_MARKER = "P4B_GATE_CREDENTIAL_MARKER_7F4D2C91_DO_NOT_PERSIST"
T0 = "2026-08-20T00:00:00Z"
NOW = 200_000
PUBLIC_A = "93.184.216.34"
PUBLIC_B = "8.8.8.8"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _hash_without(value: dict[str, Any], field: str) -> str:
    preimage = copy.deepcopy(value)
    preimage.pop(field, None)
    return sha256_bytes(canonical_bytes(preimage))


def _exact(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields differ")
    return value


def _count(value: object, label: str, *, maximum: int = 1_000_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{label} is not a bounded nonnegative integer")
    return value


def _sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} is not canonical sha256")
    return value


def _artifact_identity(value: object, label: str) -> dict[str, Any]:
    item = _exact(value, {
        "schema_version", "worker_source_sha256", "dependency_environment_sha256",
        "protocol_schema",
    } | ({"pdf_parser_source_sha256"} if label == "PDF artifact" else {"exact_parser_source_sha256"}), label)
    for field in item:
        if field.endswith("sha256"):
            _sha256(item[field], f"{label} {field}")
        elif not isinstance(item[field], str) or not item[field]:
            raise ValueError(f"{label} identity is invalid")
    expected_schema = (
        "adaivy.phase4b-strict-pdf-sandbox-artifact.v2"
        if label == "PDF artifact"
        else "adaivy.phase4b-exact-parser-sandbox-artifact.v2"
    )
    if (
        item["schema_version"] != expected_schema
        or item["protocol_schema"] != "phase4b-parser-worker-response-v2"
    ):
        raise ValueError(f"{label} schema differs")
    return item


def _bounded_evidence_tree(value: object, label: str, *, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError(f"{label} nesting exceeds its bound")
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        _count(value, label)
        return
    if isinstance(value, str):
        if not value or len(value.encode("utf-8")) > 2_048:
            raise ValueError(f"{label} text is invalid")
        return
    if isinstance(value, list):
        if len(value) > 256:
            raise ValueError(f"{label} list exceeds its bound")
        for item in value:
            _bounded_evidence_tree(item, label, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 256 or any(not isinstance(key, str) or not key for key in value):
            raise ValueError(f"{label} mapping is invalid")
        for item in value.values():
            _bounded_evidence_tree(item, label, depth=depth + 1)
        return
    raise ValueError(f"{label} contains an unsupported value")


def _gate_policy(repository_root: Path) -> tuple[dict[str, Any], str]:
    policy = _json(repository_root / GATE_POLICY)
    _exact(policy, {
        "schema_version", "required_passes", "required_blocked_controls",
        "activation_status",
    }, "feasible gate policy")
    if policy["schema_version"] != "adaivy.phase4b-feasible-gate-policy.v2":
        raise ValueError("feasible gate policy schema differs")
    passes = _exact(policy["required_passes"], {
        "fixture_manifest_total", "acquisition_fixture_executions",
        "parser_fixture_executions", "lifecycle_fixture_executions",
        "ambient_network_calls", "phase3a_writes_caused",
        "protected_evidence_mismatches", "credential_marker_matches",
        "in_process_repeat_count", "independent_process_count", "restart_count",
        "replay_count", "reverse_order_rebuild_count", "semantic_hashes_identical",
        "parser_corpus_authorized",
    }, "feasible gate required passes")
    for field, value in passes.items():
        if field in {"semantic_hashes_identical", "parser_corpus_authorized"}:
            if type(value) is not bool:
                raise ValueError("feasible gate boolean threshold is invalid")
        else:
            _count(value, f"feasible gate threshold {field}")
    if (
        policy["activation_status"] != "blocked_pending_full_gate_controls"
        or policy["required_blocked_controls"]
        != ["os_parser_sandbox", "live_https_operator_transport"]
    ):
        raise ValueError("feasible gate activation policy differs")
    return policy, canonical_hash(policy)


def _verify_lifecycle(
    values: object, expected: list[dict[str, Any]],
) -> None:
    if not isinstance(values, list) or len(values) != len(expected):
        raise ValueError("lifecycle evidence cardinality differs")
    for item, fixture in zip(values, expected):
        evidence = _exact(item, {
            "case_id", "status", "expected_outcome", "observed_outcome",
            "production_paths", "assertions", "evidence_hash",
        } | ({"detail"} if isinstance(item, dict) and "detail" in item else set()), "lifecycle evidence")
        if (
            evidence["case_id"] != fixture["case_id"]
            or evidence["status"] != "passed"
            or evidence["expected_outcome"] != fixture["expected_outcome"]
            or evidence["observed_outcome"] != fixture["expected_outcome"]
            or not isinstance(evidence["production_paths"], list)
            or not evidence["production_paths"]
            or any(not isinstance(path, str) or not path for path in evidence["production_paths"])
            or not isinstance(evidence["assertions"], dict)
            or not evidence["assertions"]
            or any(value is not True for value in evidence["assertions"].values())
        ):
            raise ValueError("lifecycle evidence does not prove its declared case")
        if evidence["evidence_hash"] != _hash_without(evidence, "evidence_hash"):
            raise ValueError("lifecycle evidence hash differs")
        if "detail" in evidence:
            _bounded_evidence_tree(evidence["detail"], "lifecycle detail")


def _verify_sandbox_evidence(report: dict[str, Any]) -> None:
    probe = _exact(report["os_sandbox_probe"], {
        "status", "platform", "contract_schema", "profile_hash", "probes",
        "production_parser_connected", "portable_claim",
    }, "OS sandbox probe")
    if (
        probe["status"] not in {"passed_named_platform_probe", "unavailable", "failed_closed"}
        or probe["production_parser_connected"] is not False
        or probe["portable_claim"] is not False
        or not isinstance(probe["platform"], str) or not probe["platform"]
        or probe["contract_schema"] != DARWIN_SANDBOX_CONTRACT
    ):
        raise ValueError("OS sandbox evidence could imply activation")
    _sha256(probe["profile_hash"], "OS sandbox profile hash")
    probes = probe["probes"]
    if not isinstance(probes, list) or len(probes) != 5:
        raise ValueError("OS sandbox probe inventory differs")
    expected_actions = ["baseline", "network", "write", "process", "read"]
    statuses: dict[str, str] = {}
    for value, action in zip(probes, expected_actions):
        item = _exact(value, {
            "schema_version", "platform", "action", "status", "exit_status",
            "stdout_hash", "stderr_hash", "stdout_bytes", "stderr_bytes",
            "profile_hash", "detail",
        }, "OS sandbox probe result")
        if (
            item["action"] != action or item["platform"] != probe["platform"]
            or item["schema_version"] != probe["contract_schema"]
            or item["profile_hash"] != probe["profile_hash"]
            or item["status"] not in {"allowed", "denied", "failed", "unavailable"}
            or not isinstance(item["detail"], dict)
        ):
            raise ValueError("OS sandbox probe result differs")
        if item["exit_status"] is not None and type(item["exit_status"]) is not int:
            raise ValueError("OS sandbox exit status is invalid")
        _count(item["stdout_bytes"], "OS sandbox stdout bytes", maximum=65_536)
        _count(item["stderr_bytes"], "OS sandbox stderr bytes", maximum=65_536)
        _sha256(item["stdout_hash"], "OS sandbox stdout hash")
        _sha256(item["stderr_hash"], "OS sandbox stderr hash")
        statuses[action] = item["status"]
    if probe["status"] == "passed_named_platform_probe" and statuses != {
        "baseline": "allowed", "network": "denied", "write": "denied",
        "process": "denied", "read": "denied",
    }:
        raise ValueError("OS sandbox passed status lacks exact denials")
    if probe["status"] == "unavailable" and set(statuses.values()) != {"unavailable"}:
        raise ValueError("OS sandbox unavailable status differs")

    bridge = _exact(report["exact_parser_sandbox_bridge"], {
        "status", "artifacts", "cases", "production_parser_connected",
        "profiles_connected", "pdf_connected", "strict_transient_memory_enforcement",
        "portable_claim", "production_activated",
    }, "exact parser sandbox bridge")
    if (
        bridge["status"] not in {"passed_named_darwin_html_tex_pdf", "unavailable", "failed_closed"}
        or bridge["strict_transient_memory_enforcement"] is not False
        or bridge["portable_claim"] is not False
        or bridge["production_activated"] is not False
    ):
        raise ValueError("exact parser sandbox bridge could imply activation")
    artifacts = _exact(bridge["artifacts"], {"html_tex", "pdf"}, "sandbox artifacts")
    _artifact_identity(artifacts["html_tex"], "HTML/TeX artifact")
    _artifact_identity(artifacts["pdf"], "PDF artifact")
    cases = bridge["cases"]
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("sandbox bridge case inventory differs")
    for item, profile in zip(cases, ("html", "tex", "pdf")):
        case = _exact(item, {
            "profile", "disposition", "failure_code", "semantic_sha256",
            "segment_count", "formula_count",
        }, "sandbox bridge case")
        if case["profile"] != profile or case["disposition"] not in {
            "candidate_proposal", "quarantined", "failed",
        }:
            raise ValueError("sandbox bridge case differs")
        if case["failure_code"] is not None and not isinstance(case["failure_code"], str):
            raise ValueError("sandbox bridge failure code is invalid")
        _sha256(case["semantic_sha256"], "sandbox bridge semantic hash")
        _count(case["segment_count"], "sandbox bridge segment count", maximum=4_096)
        _count(case["formula_count"], "sandbox bridge formula count", maximum=2_048)
    completed = all(item["disposition"] == "candidate_proposal" for item in cases)
    if (
        bridge["production_parser_connected"] is not completed
        or bridge["pdf_connected"] is not completed
        or bridge["profiles_connected"] != (["html", "pdf", "tex"] if completed else [])
        or (bridge["status"] == "passed_named_darwin_html_tex_pdf") is not completed
    ):
        raise ValueError("sandbox bridge status and cases differ")


def _verify_corpus(value: object, fixtures: list[dict[str, Any]], manifest_hash: str) -> None:
    corpus = _exact(value, {
        "schema_version", "status", "activation_effect", "artifacts", "cases",
        "counts", "manifest_content_hash", "media_profile_binding",
        "production_activated", "content_hash",
    }, "parser corpus authorization")
    if corpus["content_hash"] != _hash_without(corpus, "content_hash"):
        raise ValueError("parser corpus authorization hash differs")
    if (
        corpus["schema_version"] != "adaivy.phase4b-parser-corpus-authorization.v2"
        or corpus["status"] != "authorized"
        or corpus["activation_effect"] != "none"
        or corpus["production_activated"] is not False
        or corpus["manifest_content_hash"] != manifest_hash
        or corpus["media_profile_binding"] != "exact_format_to_single_profile_v1"
    ):
        raise ValueError("parser corpus authorization semantics differ")
    artifacts = _exact(corpus["artifacts"], {"html_tex", "pdf"}, "corpus artifacts")
    _artifact_identity(artifacts["html_tex"], "HTML/TeX artifact")
    _artifact_identity(artifacts["pdf"], "PDF artifact")
    cases = corpus["cases"]
    if not isinstance(cases, list) or len(cases) != len(fixtures):
        raise ValueError("parser corpus case inventory differs")
    profiles = {HTML_PROFILE.name: HTML_PROFILE, TEX_PROFILE.name: TEX_PROFILE, PDF_PROFILE.name: PDF_PROFILE}
    exact = false = signatures = 0
    for item, fixture in zip(cases, fixtures):
        case = _exact(item, {
            "case_id", "content_signature_match", "exact_disposition_match",
            "expected_outcome", "failure_code", "false_admission",
            "fixture_byte_length", "fixture_sha256", "format", "media_type",
            "media_type_hash", "observed_disposition", "parser_semantic_sha256",
            "profile_name", "profile_sha256", "request_original_sha256",
            "safe_fail_closed", "segment_count",
        }, "parser corpus case")
        profile = profiles.get(case["profile_name"])
        expected_profile = {"html": HTML_PROFILE, "tex": TEX_PROFILE, "pdf": PDF_PROFILE}.get(
            fixture["format"]
        )
        if (
            profile is None or profile != expected_profile
            or case["case_id"] != fixture["case_id"]
            or case["format"] != fixture["format"]
            or case["expected_outcome"] != fixture["expected_outcome"]
            or case["fixture_byte_length"] != fixture["byte_length"]
            or case["fixture_sha256"] != fixture["sha256"]
            or case["request_original_sha256"] != fixture["sha256"]
            or case["media_type"] != profile.media_type
            or case["media_type_hash"] != sha256_bytes(profile.media_type.encode("utf-8"))
            or case["profile_sha256"] != profile.sha256
            or case["observed_disposition"] != fixture["expected_outcome"]
            or case["content_signature_match"] is not True
            or case["exact_disposition_match"] is not True
            or case["false_admission"] is not False
            or case["safe_fail_closed"] is not True
            or type(case["fixture_byte_length"]) is not int
        ):
            raise ValueError("parser corpus case is not exactly manifest-bound")
        if (
            (case["expected_outcome"] == "candidate_proposal" and case["failure_code"] is not None)
            or (case["expected_outcome"] == "quarantined" and (
                not isinstance(case["failure_code"], str) or not case["failure_code"]
            ))
        ):
            raise ValueError("parser corpus failure code is invalid")
        _sha256(case["parser_semantic_sha256"], "parser corpus semantic hash")
        _count(case["segment_count"], "parser corpus segment count", maximum=4_096)
        exact += int(case["exact_disposition_match"])
        false += int(case["false_admission"])
        signatures += int(case["content_signature_match"])
    counts = _exact(corpus["counts"], {
        "cases_exactly_matched", "content_signature_matches",
        "exact_disposition_matches", "false_admissions", "total",
    }, "parser corpus counts")
    for field in counts:
        _count(counts[field], f"parser corpus count {field}")
    expected_counts = {
        "cases_exactly_matched": exact, "content_signature_matches": signatures,
        "exact_disposition_matches": exact, "false_admissions": false,
        "total": len(cases),
    }
    if counts != expected_counts or expected_counts != {
        "cases_exactly_matched": 12, "content_signature_matches": 12,
        "exact_disposition_matches": 12, "false_admissions": 0, "total": 12,
    }:
        raise ValueError("parser corpus counts differ")


def verify_feasible_gate_report(
    report: dict[str, Any], repository_root: Path,
) -> dict[str, Any]:
    """Strictly verify a supplied v5 report without rerunning gate operations."""

    repository_root = repository_root.resolve()
    value = _exact(report, {
        "schema_version", "gate_policy_hash", "activation_status", "manifest",
        "fixture_execution", "fixture_evidence", "network_isolation",
        "phase3a_preservation", "protected_evidence", "credential_marker_scan",
        "determinism", "os_sandbox_probe", "exact_parser_sandbox_bridge",
        "parser_corpus_authorization", "blocked_controls", "content_hash",
    }, "feasible gate report")
    if value["schema_version"] != REPORT_SCHEMA:
        raise ValueError("feasible gate report schema differs")
    if value["content_hash"] != _hash_without(value, "content_hash"):
        raise ValueError("feasible gate report content hash differs")
    policy, policy_hash = _gate_policy(repository_root)
    if (
        value["gate_policy_hash"] != policy_hash
        or value["activation_status"] != policy["activation_status"]
    ):
        raise ValueError("feasible gate report policy binding differs")
    required = policy["required_passes"]
    expected_manifest, _ = verify_fixture_manifest(repository_root)
    if canonical_bytes(value["manifest"]) != canonical_bytes(expected_manifest):
        raise ValueError("feasible gate manifest evidence differs")
    if expected_manifest["counts"]["total"] != required["fixture_manifest_total"]:
        raise ValueError("feasible gate manifest total differs from policy")
    manifest_value = _json(repository_root / "fixtures/phase4b/acceptance/manifest.json")
    fixtures = manifest_value["fixtures"]
    evidence = value["fixture_evidence"]
    if not isinstance(evidence, list) or len(evidence) != 30:
        raise ValueError("feasible gate fixture evidence cardinality differs")
    for item, fixture in zip(evidence, fixtures):
        case = _exact(item, {
            "case_id", "class", "expected_outcome", "fixture_sha256",
            "manifest_verified", "observed_outcome", "execution_status",
        }, "fixture execution evidence")
        expected_case = {
            "case_id": fixture["case_id"], "class": fixture["class"],
            "expected_outcome": fixture["expected_outcome"],
            "fixture_sha256": fixture["sha256"], "manifest_verified": True,
            "observed_outcome": fixture["expected_outcome"], "execution_status": "passed",
        }
        if canonical_bytes(case) != canonical_bytes(expected_case):
            raise ValueError("fixture execution evidence is not manifest-bound")
    execution = _exact(value["fixture_execution"], {
        "status", "executed", "lifecycle_evidence",
    }, "fixture execution summary")
    executed = _exact(execution["executed"], {
        "acquisition", "parsing", "lifecycle_integration",
    }, "fixture execution counts")
    for field in executed:
        _count(executed[field], f"fixture execution {field}")
    if execution["status"] != "passed" or executed != {
        "acquisition": required["acquisition_fixture_executions"],
        "parsing": required["parser_fixture_executions"],
        "lifecycle_integration": required["lifecycle_fixture_executions"],
    }:
        raise ValueError("fixture execution counts differ")
    _verify_lifecycle(
        execution["lifecycle_evidence"],
        [item for item in fixtures if item["class"] == "lifecycle_integration"],
    )
    network = _exact(value["network_isolation"], {
        "status", "socket_attempts", "dns_attempts", "http_calls",
        "model_api_calls", "ambient_network_calls",
    }, "network isolation")
    for field in (
        "socket_attempts", "dns_attempts", "http_calls", "model_api_calls",
        "ambient_network_calls",
    ):
        _count(network[field], f"network isolation {field}")
    if canonical_bytes(network) != canonical_bytes({
        "status": "passed", "socket_attempts": 0, "dns_attempts": 0,
        "http_calls": 0, "model_api_calls": 0, "ambient_network_calls": 0,
    }):
        raise ValueError("feasible gate network isolation differs")
    preservation = _exact(value["phase3a_preservation"], {
        "status", "objects_before", "objects_after", "writes_caused", "snapshot_hash",
    }, "Phase 3A preservation")
    _count(preservation["objects_before"], "Phase 3A objects before")
    _count(preservation["objects_after"], "Phase 3A objects after")
    _count(preservation["writes_caused"], "Phase 3A writes caused")
    if (
        preservation["status"] != "passed" or preservation["writes_caused"] != 0
        or type(preservation["objects_before"]) is not int
        or preservation["objects_before"] < 0
        or preservation["objects_after"] != preservation["objects_before"]
    ):
        raise ValueError("Phase 3A preservation evidence differs")
    _sha256(preservation["snapshot_hash"], "Phase 3A snapshot hash")
    if canonical_bytes(value["protected_evidence"]) != canonical_bytes(
        verify_protected_evidence(repository_root)
    ):
        raise ValueError("protected evidence report differs")
    marker = _exact(value["credential_marker_scan"], {
        "status", "artifacts_scanned", "persisted_files_scanned", "exact_marker_matches",
    }, "credential marker scan")
    _count(marker["exact_marker_matches"], "credential marker matches")
    if marker["status"] != "passed" or marker["exact_marker_matches"] != 0:
        raise ValueError("credential marker scan differs")
    _count(marker["artifacts_scanned"], "credential artifacts scanned")
    _count(marker["persisted_files_scanned"], "credential files scanned")
    determinism = _exact(value["determinism"], {
        "status", "in_process_repeat_count", "independent_process_count",
        "restart_count", "replay_count", "reverse_order_rebuild_count",
        "semantic_hashes_identical", "semantic_export_hash",
    }, "determinism evidence")
    for field in (
        "in_process_repeat_count", "independent_process_count", "restart_count",
        "replay_count", "reverse_order_rebuild_count",
    ):
        _count(determinism[field], f"determinism {field}")
    if type(determinism["semantic_hashes_identical"]) is not bool:
        raise ValueError("determinism boolean is invalid")
    if determinism != {
        "status": "passed",
        **{field: required[field] for field in (
            "in_process_repeat_count", "independent_process_count", "restart_count",
            "replay_count", "reverse_order_rebuild_count", "semantic_hashes_identical",
        )},
        "semantic_export_hash": determinism["semantic_export_hash"],
    }:
        raise ValueError("determinism evidence differs")
    _sha256(determinism["semantic_export_hash"], "determinism semantic hash")
    _verify_sandbox_evidence(value)
    parser_fixtures = [item for item in fixtures if item["class"] == "parsing"]
    _verify_corpus(value["parser_corpus_authorization"], parser_fixtures, manifest_value["content_hash"])
    if canonical_bytes(value["parser_corpus_authorization"]["artifacts"]) != canonical_bytes(
        value["exact_parser_sandbox_bridge"]["artifacts"]
    ):
        raise ValueError("corpus and sandbox parser identities differ")
    blockers = value["blocked_controls"]
    if not isinstance(blockers, list) or len(blockers) != 2:
        raise ValueError("feasible gate blocker inventory differs")
    for item, control in zip(blockers, policy["required_blocked_controls"]):
        blocker = _exact(item, {"control", "status", "reason", "counted_as_pass"}, "blocked control")
        if (
            blocker["control"] != control or blocker["status"] != "blocked"
            or blocker["counted_as_pass"] is not False
            or not isinstance(blocker["reason"], str) or not blocker["reason"]
        ):
            raise ValueError("feasible gate blocked control differs")
    return value


def load_feasible_gate_report(data: bytes, repository_root: Path) -> dict[str, Any]:
    """Decode one bounded canonical report and apply the strict v5 verifier."""

    if not isinstance(data, bytes) or not data or len(data) > MAX_REPORT_BYTES:
        raise ValueError("feasible gate report byte bound differs")
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError("feasible gate report contains a duplicate key")
            result[key] = value
        return result
    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("feasible gate report is not strict JSON") from error
    if not isinstance(value, dict) or data != canonical_bytes(value):
        raise ValueError("feasible gate report is not canonical JSON")
    return verify_feasible_gate_report(value, repository_root)


def verify_fixture_manifest(repository_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base = repository_root / "fixtures/phase4b/acceptance"
    value = _json(base / "manifest.json")
    if set(value) != {
        "schema_version", "fixture_license", "declared_counts", "fixtures",
        "coverage_status", "content_hash",
    }:
        raise ValueError("Phase 4B fixture manifest fields differ")
    if value["schema_version"] != MANIFEST_SCHEMA:
        raise ValueError("Phase 4B fixture manifest schema differs")
    if value["content_hash"] != _hash_without(value, "content_hash"):
        raise ValueError("Phase 4B fixture manifest content hash differs")
    fixtures = value["fixtures"]
    if not isinstance(fixtures, list) or len(fixtures) != 30:
        raise ValueError("Phase 4B fixture count differs")
    observed = {
        "total": len(fixtures),
        "acquisition": sum(item.get("class") == "acquisition" for item in fixtures),
        "acquisition_allowed": sum(
            item.get("class") == "acquisition" and item.get("role") == "allowed"
            for item in fixtures
        ),
        "acquisition_denied": sum(
            item.get("class") == "acquisition" and item.get("role") == "denied"
            for item in fixtures
        ),
        "parsing": sum(item.get("class") == "parsing" for item in fixtures),
        "parsing_html": sum(item.get("class") == "parsing" and item.get("format") == "html" for item in fixtures),
        "parsing_tex": sum(item.get("class") == "parsing" and item.get("format") == "tex" for item in fixtures),
        "parsing_pdf": sum(item.get("class") == "parsing" and item.get("format") == "pdf" for item in fixtures),
        "lifecycle_integration": sum(item.get("class") == "lifecycle_integration" for item in fixtures),
    }
    if observed != value["declared_counts"]:
        raise ValueError("Phase 4B fixture class counts differ")
    case_ids: set[str] = set()
    evidence: list[dict[str, Any]] = []
    for item in fixtures:
        if not isinstance(item, dict) or set(item) != {
            "case_id", "class", "format", "role", "expected_outcome", "path",
            "byte_length", "sha256",
        }:
            raise ValueError("Phase 4B fixture entry fields differ")
        case_id = item["case_id"]
        if not isinstance(case_id, str) or case_id in case_ids:
            raise ValueError("Phase 4B fixture identity is invalid or duplicated")
        case_ids.add(case_id)
        path = (base / item["path"]).resolve()
        if (repository_root / "fixtures/phase4b").resolve() not in path.parents:
            raise ValueError("Phase 4B fixture escapes its managed root")
        data = path.read_bytes()
        if len(data) != item["byte_length"] or sha256_bytes(data) != item["sha256"]:
            raise ValueError(f"Phase 4B fixture bytes differ: {case_id}")
        evidence.append({
            "case_id": case_id,
            "class": item["class"],
            "expected_outcome": item["expected_outcome"],
            "fixture_sha256": item["sha256"],
            "manifest_verified": True,
        })
    return {
        "status": "passed",
        "content_hash": value["content_hash"],
        "counts": observed,
        "license_expression": value["fixture_license"]["license_expression"],
    }, evidence


def verify_protected_evidence(repository_root: Path) -> dict[str, Any]:
    path = repository_root / PROTECTED_MANIFEST
    value = _json(path)
    entries = value.get("stable_objects")
    if (
        value.get("schema_version") != "adaivy.phase4a-protected-evidence.v2"
        or value.get("profile") != "phase4a-stable-protected-evidence-v2"
        or not isinstance(entries, list)
        or value.get("stable_object_count") != len(entries)
    ):
        raise ValueError("protected-evidence manifest identity differs")
    preimage = copy.deepcopy(value)
    preimage["content_hash"] = "sha256:" + "0" * 64
    if value.get("content_hash") != sha256_bytes(canonical_bytes(preimage)):
        raise ValueError("protected-evidence manifest content hash differs")
    lines: list[str] = []
    paths: list[str] = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("protected-evidence entry fields differ")
        relative = item["path"]
        if not isinstance(relative, str) or not relative.startswith("reports/"):
            raise ValueError("protected-evidence path is invalid")
        observed = sha256_bytes((repository_root / relative).read_bytes())
        if observed != item["sha256"]:
            raise ValueError(f"protected evidence changed: {relative}")
        paths.append(relative)
        lines.append(f"{observed.removeprefix('sha256:')}  {relative}\n")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError("protected-evidence paths are not canonical")
    aggregate = sha256_bytes("".join(lines).encode("utf-8"))
    if aggregate != value["aggregation"]["aggregate_sha256"]:
        raise ValueError("protected-evidence aggregate differs")
    return {
        "status": "passed",
        "manifest_path": PROTECTED_MANIFEST,
        "manifest_content_hash": value["content_hash"],
        "objects_verified": len(entries),
        "aggregate_sha256": aggregate,
        "mismatches": 0,
    }


def _phase3a_snapshot(repository_root: Path) -> dict[str, str]:
    roots = (
        "fixtures/phase3a", "reports/phase-3a", "src/math_research/phase3a",
        "schemas", "migrations",
    )
    result: dict[str, str] = {}
    for relative_root in roots:
        root = repository_root / relative_root
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(repository_root).as_posix()
            if "__pycache__" in path.parts:
                continue
            if relative_root in {"schemas", "migrations"} and "phase3a" not in path.name.casefold() and "phase3a" not in relative.casefold():
                continue
            result[relative] = sha256_bytes(path.read_bytes())
    return result


@contextmanager
def _deny_ambient_network(counters: dict[str, int]) -> Iterator[None]:
    # Lazy import preserves the standing no-module-level-network-import rule.
    import socket

    originals = (socket.socket, socket.create_connection, socket.getaddrinfo)

    def deny_socket(*_args: object, **_kwargs: object) -> None:
        counters["socket_attempts"] += 1
        raise AssertionError("ambient socket creation attempted")

    def deny_connection(*_args: object, **_kwargs: object) -> None:
        counters["socket_attempts"] += 1
        raise AssertionError("ambient connection attempted")

    def deny_dns(*_args: object, **_kwargs: object) -> None:
        counters["dns_attempts"] += 1
        raise AssertionError("ambient DNS attempted")

    socket.socket = deny_socket  # type: ignore[assignment]
    socket.create_connection = deny_connection  # type: ignore[assignment]
    socket.getaddrinfo = deny_dns  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket, socket.create_connection, socket.getaddrinfo = originals


class _Clock:
    def __init__(self) -> None:
        self.value = 0

    def now_milliseconds(self) -> int:
        value = self.value
        self.value += 1_000
        return value


class _Resolver:
    def __init__(self, addresses: dict[str, tuple[str, ...]]) -> None:
        self.addresses = addresses

    def resolve(self, hostname: str) -> Resolution:
        return Resolution(hostname, self.addresses[hostname])


class _Transport:
    def __init__(self, values: dict[str, list[TransportResponse]]) -> None:
        self.values = values
        self.offsets: dict[str, int] = {}

    def fetch(self, request: TransportRequest) -> TransportResponse:
        offset = self.offsets.get(request.url, 0)
        self.offsets[request.url] = offset + 1
        return self.values[request.url][min(offset, len(self.values[request.url]) - 1)]


class _FixtureWorker:
    """Explicit fixture worker; never evidence for a production OS sandbox."""

    adapter = RestrictedStdlibAdapter()
    name = "phase4b-gate-fixture-worker"
    version = "1.0.0"
    implementation_sha256 = adapter.implementation_sha256
    dependency_environment_sha256 = adapter.dependency_environment_sha256
    sandbox_contract = "external-os-sandbox-contract-v1"

    def execute(self, request: ParseRequest) -> WorkerExecution:
        return WorkerExecution.capture(
            outcome=self.adapter.parse(request),
            operation_id="operation.phase4b-gate-fixture-worker",
        )


def _response(
    *, status: int = 200, body: bytes = b"project-authored gate bytes",
    peer: str = PUBLIC_A, location: str | None = None,
) -> TransportResponse:
    headers = (("location", location),) if location is not None else (("content-type", "text/html"),)
    return TransportResponse(status, headers, body, peer, 1)


def _acquisition_fixture(case_id: str) -> tuple[str, list[bytes]]:
    start = "https://papers.example/start"
    same = "https://papers.example/final"
    cross = "https://archive.example/final"
    internal = "https://internal.example/final"
    policy = AcquisitionPolicy()
    origins = ["https://papers.example"]
    urls = [start]
    responses: dict[str, list[TransportResponse]] = {start: [_response()]}
    addresses = {"papers.example": (PUBLIC_A,), "archive.example": (PUBLIC_B,), "internal.example": ("127.0.0.1",)}
    actor_kind = "human"
    network_enabled = True
    terms_captured = NOW
    robots_valid = True
    robots_allowed = True
    omitted_right: str | None = None
    if case_id.endswith("allowed-same-origin-redirect"):
        urls.append(same); responses = {start: [_response(status=302, body=b"", location=same)], same: [_response()]}
    elif case_id.endswith("allowed-cross-origin-redirect"):
        origins.append("https://archive.example"); urls.append(cross)
        responses = {start: [_response(status=302, body=b"", location=cross)], cross: [_response(peer=PUBLIC_B)]}
    elif case_id.endswith("denied-missing-run-authority"):
        network_enabled = False
    elif case_id.endswith("denied-robots-disallow"):
        robots_allowed = False
    elif case_id.endswith("denied-robots-unavailable"):
        robots_valid = False
    elif case_id.endswith("denied-changed-terms"):
        terms_captured = NOW - policy.max_snapshot_age_seconds - 1
    elif case_id.endswith("denied-acquisition-right"):
        omitted_right = "acquisition"
    elif case_id.endswith("denied-retention-right"):
        omitted_right = "storage_and_retention"
    elif case_id.endswith("denied-special-use-redirect"):
        origins.append("https://internal.example"); urls.append(internal)
        responses = {start: [_response(status=302, body=b"", location=internal)]}
    elif case_id.endswith("denied-peer-mismatch"):
        responses = {start: [_response(peer=PUBLIC_B)]}
    elif case_id.endswith("denied-response-budget"):
        policy = AcquisitionPolicy(max_body_bytes=4)
        responses = {start: [_response(body=b"12345")]}

    authorization = RunAuthorization(
        "run.phase4b.gate", "human.owner", actor_kind, "human_final",
        "capability.phase4b.gate", "acquire_https", network_enabled,
        policy.content_hash, tuple(origins), (AuthorizedResource("request.gate", start),),
    )
    rights = tuple(
        RightsDecision(
            f"rights.{index}.{use}", authorization.run_id, url, use, "allowed",
            "human", "human_final", NOW - 1, NOW + 1,
        )
        for index, url in enumerate(urls)
        for use in ("acquisition", "storage_and_retention")
        if use != omitted_right
    )
    terms = tuple(
        TermsSnapshot(f"terms.{index}", origin, "a" * 64, terms_captured, True, True)
        for index, origin in enumerate(origins)
    )
    robots = tuple(
        RobotsSnapshot(
            f"robots.{index}", url, "b" * 64, NOW, robots_valid, robots_allowed,
        )
        for index, url in enumerate(urls)
    )
    artifacts: list[bytes] = []
    try:
        result = acquire(
            (AcquisitionRequest(
                authorization.run_id, "request.gate", authorization.actor_id, start,
                (("Authorization", CREDENTIAL_MARKER),),
            ),),
            authorization=authorization, policy=policy, rights=rights, terms=terms,
            robots=robots, resolver=_Resolver(addresses), transport=_Transport(responses),
            start_clock=_Clock(), now_epoch=NOW, recorded_at_epoch=NOW,
        )
    except AcquisitionPolicyError:
        return "denied", artifacts
    artifacts.extend((result.semantic_bytes, result.operational_bytes))
    return ("untrusted_candidate" if result.candidates else "denied"), artifacts


def _initialize_lifecycle_workspace(
    root: Path, source_ids: Sequence[str],
) -> tuple[Phase4BWorkspace, Phase4Service, Phase4BService]:
    workspace = Phase4BWorkspace(root)
    rights = Phase4Service(workspace.phase4a)
    rights.initialize_policy(actor_id="actor.phase4b-gate", recorded_at=T0)
    for source_id in source_ids:
        for use in (
            RightsUse.ACQUISITION,
            RightsUse.STORAGE_AND_RETENTION,
            RightsUse.PARSING,
        ):
            rights.append_rights(
                source_id=source_id,
                intended_use=use,
                value=RightsValue.ALLOWED,
                reason_code=RightsReason.PERMITTED,
                reason_detail="project-authored lifecycle gate authorization",
                evidence_refs=("evidence.phase4b-lifecycle-gate",),
                actor_id="actor.phase4b-gate",
                valid_from=T0,
                valid_until=None,
                recorded_at=T0,
                lifecycle_id=f"rights-lifecycle.{source_id}.{use.value}",
            )
    return workspace, rights, Phase4BService(workspace)


def _service_acquire(
    service: Phase4BService, source_id: str, *, request_suffix: str,
    body: bytes = b"<p>Theorem <math>x + y</math></p>",
) -> dict[str, Any]:
    url = f"https://papers.example/{request_suffix}"
    request_id = f"request.{request_suffix}"
    policy = AcquisitionPolicy()
    authorization = RunAuthorization(
        f"run.{request_suffix}", "actor.phase4b-gate", "human", "human_final",
        "capability.phase4b-gate", "acquire_https", True, policy.content_hash,
        ("https://papers.example",), (AuthorizedResource(request_id, url),),
    )
    stored = service.acquire(
        source_id,
        (AcquisitionRequest(authorization.run_id, request_id, authorization.actor_id, url),),
        authorization=authorization,
        policy=policy,
        terms=(TermsSnapshot(
            f"terms.{request_suffix}", "https://papers.example", "a" * 64,
            NOW, True, True,
        ),),
        robots=(RobotsSnapshot(
            f"robots.{request_suffix}", url, "b" * 64, NOW, True, True,
        ),),
        resolver=_Resolver({"papers.example": (PUBLIC_A,)}),
        transport=_Transport({url: [_response(body=body)]}),
        start_clock=_Clock(),
        now_epoch=NOW,
        recorded_at_epoch=NOW,
        recorded_at="2026-08-20T00:00:01Z",
    )
    if len(stored.records) != 1 or stored.records[0]["record_type"] != RecordType.ACQUISITION_CANDIDATE.value:
        raise ValueError("lifecycle gate acquisition did not persist one candidate")
    return stored.records[0]


def _service_parse(
    service: Phase4BService, source_id: str, acquisition_id: str, *, suffix: str,
) -> dict[str, Any]:
    stored = service.parse(
        source_id,
        acquisition_id,
        request_id=f"request.parse.{suffix}",
        representation_id=f"representation.html.{suffix}",
        media_type=HTML_PROFILE.media_type,
        profile_name=HTML_PROFILE.name,
        recorded_at="2026-08-20T00:00:01Z",
        worker=_FixtureWorker(),
    )
    if stored.record["record_type"] != RecordType.PARSE_CANDIDATE.value:
        raise ValueError("lifecycle gate parser did not persist one candidate")
    return stored.record


def _lifecycle_evidence(
    case_id: str, expected: str, assertions: dict[str, Any],
    *, production_paths: Sequence[str], detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "case_id": case_id,
        "status": "passed",
        "expected_outcome": expected,
        "observed_outcome": expected,
        "production_paths": list(production_paths),
        "assertions": assertions,
    }
    if detail:
        evidence["detail"] = detail
    evidence["evidence_hash"] = canonical_hash(evidence)
    return evidence


def _run_lifecycle_case(
    case_id: str, expected: str, gate_root: Path,
) -> tuple[dict[str, Any], list[bytes]]:
    case_root = gate_root / "lifecycle" / case_id.replace(".", "-")
    artifacts: list[bytes] = []

    if case_id.endswith("correction-supersession"):
        source_id = "source.lifecycle.correction"
        workspace, _rights, service = _initialize_lifecycle_workspace(case_root, (source_id,))
        try:
            acquisition = _service_acquire(service, source_id, request_suffix="correction")
            first_parse = _service_parse(service, source_id, acquisition["record_id"], suffix="correction-v1")
            parser_invalidation = service.invalidate_candidates(
                source_id, (first_parse["record_id"],),
                trigger_record_id="correction.parser-v2",
                reason_code="parser_superseded",
                at="2026-08-20T00:00:02Z",
                erase_content=False,
            )
            second_parse = _service_parse(service, source_id, acquisition["record_id"], suffix="correction-v2")
            active = sorted(
                item["record_id"] for item in workspace.projection()
                if item["subject_id"] == source_id and item["current_state"] == "active_candidate"
            )
            correction = service.invalidate_candidates(
                source_id, active,
                trigger_record_id="correction.source-v2",
                reason_code="source_correction",
                at="2026-08-20T00:00:03Z",
                erase_content=True,
            )
            projection = workspace.projection()
            if not projection or any(item["current_state"] != "invalidated_candidate" for item in projection):
                raise ValueError("correction left a prior candidate active")
            service.content.verify_absent(source_id)
            artifacts.append(workspace.export_bytes())
            evidence = _lifecycle_evidence(
                case_id, expected,
                {
                    "parser_supersession_invalidated_prior_parse": first_parse["record_id"] in parser_invalidation["payload"]["affected_record_ids"],
                    "source_correction_invalidated_remaining_candidates": correction["payload"]["affected_record_ids"] == active,
                    "all_prior_candidates_invalidated": True,
                    "source_content_absent": True,
                },
                production_paths=(
                    "Phase4BService.acquire", "Phase4BService.parse",
                    "Phase4BService.invalidate_candidates", "Phase4BWorkspace.projection",
                ),
                detail={"candidate_count": len(projection), "replacement_parse_id": second_parse["record_id"]},
            )
        finally:
            service.close(); workspace.close()
        return evidence, artifacts

    if case_id.endswith("revocation-takedown"):
        source_id = "source.lifecycle.revocation"
        workspace, rights, service = _initialize_lifecycle_workspace(case_root, (source_id,))
        try:
            acquisition = _service_acquire(service, source_id, request_suffix="revocation")
            parsed = _service_parse(service, source_id, acquisition["record_id"], suffix="revocation")
            revoked = rights.append_rights(
                source_id=source_id,
                intended_use=RightsUse.STORAGE_AND_RETENTION,
                value=RightsValue.PROHIBITED,
                reason_code=RightsReason.EXPLICITLY_PROHIBITED,
                reason_detail="project-authored authoritative takedown",
                evidence_refs=("evidence.phase4b-takedown",),
                actor_id="actor.phase4b-gate",
                valid_from="2026-08-20T00:00:02Z",
                valid_until=None,
                recorded_at="2026-08-20T00:00:02Z",
                lifecycle_id=f"rights-lifecycle.{source_id}.{RightsUse.STORAGE_AND_RETENTION.value}",
            )
            invalidation = service.synchronize_rights(source_id, at="2026-08-20T00:00:02Z")
            if invalidation is None or invalidation["payload"]["trigger_record_id"] != revoked.id:
                raise ValueError("rights revocation identity did not trigger invalidation")
            projection = workspace.projection()
            if any(item["current_state"] != "invalidated_candidate" for item in projection):
                raise ValueError("revocation left a candidate active")
            service.content.verify_absent(source_id)
            artifacts.append(workspace.export_bytes())
            evidence = _lifecycle_evidence(
                case_id, expected,
                {
                    "authoritative_rights_decision_bound": True,
                    "acquisition_invalidated": acquisition["record_id"] in invalidation["payload"]["affected_record_ids"],
                    "parse_invalidated": parsed["record_id"] in invalidation["payload"]["affected_record_ids"],
                    "source_content_absent": True,
                },
                production_paths=(
                    "Phase4Service.append_rights", "Phase4BService.synchronize_rights",
                    "Phase4BContentStore.remove", "Phase4BWorkspace.projection",
                ),
            )
        finally:
            service.close(); workspace.close()
        return evidence, artifacts

    if case_id.endswith("deletion-restart"):
        source_id = "source.lifecycle.deletion"
        workspace, _rights, service = _initialize_lifecycle_workspace(case_root, (source_id,))
        acquisition = _service_acquire(service, source_id, request_suffix="deletion")
        # Model a crash after the append-only deletion tombstone commits but
        # before the source-specific object removal reaches durable completion.
        workspace.append(
            record_type=RecordType.INVALIDATION,
            subject_id=source_id,
            recorded_at="2026-08-20T00:00:02Z",
            payload={
                "invalidation_id": "invalidation.lifecycle-deletion",
                "trigger_record_id": "deletion.authoritative-request",
                "affected_record_ids": [acquisition["record_id"]],
                "reason_code": "source_deletion",
                "policy_snapshot_id": service.rights.policy_id(),
            },
        )
        content_existed_before_restart = service.content.state(source_id) == "active"
        service.close()
        restarted = Phase4BService(workspace)
        try:
            restarted.content.verify_absent(source_id)
            artifacts.append(workspace.export_bytes())
            evidence = _lifecycle_evidence(
                case_id, expected,
                {
                    "interrupted_deletion_state_constructed": content_existed_before_restart,
                    "restart_reconciliation_removed_content": True,
                    "deletion_tombstone_preserved": workspace.projection()[0]["current_state"] == "invalidated_candidate",
                },
                production_paths=(
                    "Phase4BWorkspace.append", "Phase4BService.__init__",
                    "Phase4BService._reconcile_content_state", "Phase4BContentStore.verify_absent",
                ),
            )
        finally:
            restarted.close(); workspace.close()
        return evidence, artifacts

    if case_id.endswith("independent-identical-copies"):
        sources = ("source.lifecycle.copy-a", "source.lifecycle.copy-b")
        workspace, rights, service = _initialize_lifecycle_workspace(case_root, sources)
        try:
            left = _service_acquire(service, sources[0], request_suffix="copy-a")
            right = _service_acquire(service, sources[1], request_suffix="copy-b")
            if left["payload"]["artifact_hash"] != right["payload"]["artifact_hash"]:
                raise ValueError("identical lifecycle bytes did not share their byte hash")
            if left["payload"]["content_object_id"] == right["payload"]["content_object_id"]:
                raise ValueError("identical lifecycle bytes shared a deletable object")
            rights.append_rights(
                source_id=sources[0], intended_use=RightsUse.STORAGE_AND_RETENTION,
                value=RightsValue.PROHIBITED, reason_code=RightsReason.EXPLICITLY_PROHIBITED,
                reason_detail="delete only the first independently owned copy",
                evidence_refs=("evidence.phase4b-delete-copy-a",), actor_id="actor.phase4b-gate",
                valid_from="2026-08-20T00:00:02Z", valid_until=None,
                recorded_at="2026-08-20T00:00:02Z",
                lifecycle_id=f"rights-lifecycle.{sources[0]}.{RightsUse.STORAGE_AND_RETENTION.value}",
            )
            service.synchronize_rights(sources[0], at="2026-08-20T00:00:02Z")
            service.content.verify_absent(sources[0])
            retained = service.content.read(sources[1], expected_hash=right["payload"]["artifact_hash"])
            artifacts.append(workspace.export_bytes())
            evidence = _lifecycle_evidence(
                case_id, expected,
                {
                    "identical_artifact_hash": True,
                    "distinct_content_object_ids": True,
                    "first_copy_absent": True,
                    "second_copy_retained": retained == b"<p>Theorem <math>x + y</math></p>",
                },
                production_paths=(
                    "Phase4BService.acquire", "Phase4BContentStore.publish",
                    "Phase4BService.synchronize_rights", "Phase4BContentStore.read",
                ),
            )
        finally:
            service.close(); workspace.close()
        return evidence, artifacts

    if case_id.endswith("canonical-replay-rebuild"):
        workspace = Phase4BWorkspace(case_root)
        workspace.append(
            record_type=RecordType.ACQUISITION_CANDIDATE,
            subject_id="source.lifecycle.replay",
            payload={**_sample_payload(), "source_id": "source.lifecycle.replay", "candidate_id": "candidate.lifecycle.replay"},
            recorded_at=T0,
        )
        expected_bytes = workspace.export_bytes()
        workspace.rebuild_projection(reverse=True)
        reverse_bytes = workspace.export_bytes()
        workspace.close()
        restarted = Phase4BWorkspace(case_root)
        restart_bytes = restarted.export_bytes()
        restarted.close()
        replay_bytes = canonical_bytes(replay(expected_bytes))
        imported = Phase4BWorkspace(case_root / "imported")
        imported.import_bytes(expected_bytes)
        imported_bytes = imported.export_bytes()
        imported.close()
        if len({expected_bytes, reverse_bytes, restart_bytes, replay_bytes, imported_bytes}) != 1:
            raise ValueError("lifecycle canonical replay identities differ")
        artifacts.extend((expected_bytes, reverse_bytes, restart_bytes, replay_bytes, imported_bytes))
        return _lifecycle_evidence(
            case_id, expected,
            {
                "reverse_rebuild_identical": True,
                "restart_identical": True,
                "canonical_replay_identical": True,
                "fresh_import_identical": True,
            },
            production_paths=(
                "Phase4BWorkspace.export_bytes", "Phase4BWorkspace.rebuild_projection",
                "phase4b.interchange.replay", "Phase4BWorkspace.import_bytes",
            ),
            detail={"semantic_export_hash": json.loads(expected_bytes)["content_hash"]},
        ), artifacts

    if case_id.endswith("trust-self-promotion"):
        original = b"<p>Theorem <math>x + y</math></p>"
        request = ParseRequest.create(
            request_id="request.lifecycle-trust",
            source_id="source.lifecycle.trust",
            content_object_id="content.lifecycle.trust",
            representation_id="representation.lifecycle.trust",
            media_type=HTML_PROFILE.media_type,
            profile_name=HTML_PROFILE.name,
            original_bytes=original,
        )
        valid = run_parser(request).to_record()
        verify_result_record(valid, original)
        promoted = copy.deepcopy(valid)
        promoted["semantic"]["trust_effects"]["applicability"] = "promoted"
        semantic_hash = sha256_bytes(canonical_bytes(promoted["semantic"]))
        promoted["semantic_sha256"] = semantic_hash
        promoted["operational"]["semantic_sha256"] = semantic_hash
        promoted["operational_sha256"] = sha256_bytes(canonical_bytes(promoted["operational"]))
        rejected = False
        rejection_reason = ""
        try:
            verify_result_record(promoted, original)
        except ValueError as error:
            rejected = True
            rejection_reason = str(error)
        if not rejected or rejection_reason != "trust effects mismatch":
            raise ValueError("trust self-promotion did not reach the closed trust boundary")
        artifacts.extend((canonical_bytes(valid), canonical_bytes(promoted)))
        return _lifecycle_evidence(
            case_id, expected,
            {
                "valid_candidate_accepted": True,
                "promotion_envelope_rehashed": True,
                "promotion_rejected": True,
                "rejected_by_exact_trust_boundary": rejection_reason == "trust effects mismatch",
            },
            production_paths=("phase4b.parsing.run_parser", "phase4b.parsing.verify_result_record"),
            detail={"rejection_reason": rejection_reason},
        ), artifacts

    raise ValueError(f"unknown lifecycle fixture: {case_id}")


def _run_fixture_oracles(
    repository_root: Path, fixture_evidence: list[dict[str, Any]], gate_root: Path,
) -> tuple[dict[str, Any], list[bytes]]:
    base = repository_root / "fixtures/phase4b/acceptance"
    manifest = _json(base / "manifest.json")
    profiles = {"html": HTML_PROFILE, "tex": TEX_PROFILE, "pdf": PDF_PROFILE}
    evidence_by_id = {item["case_id"]: item for item in fixture_evidence}
    artifacts: list[bytes] = []
    executed = {"acquisition": 0, "parsing": 0, "lifecycle_integration": 0}
    lifecycle_evidence: list[dict[str, Any]] = []
    for item in manifest["fixtures"]:
        case_id = item["case_id"]
        if item["class"] == "acquisition":
            observed, produced = _acquisition_fixture(case_id)
            artifacts.extend(produced)
            executed["acquisition"] += 1
        elif item["class"] == "parsing":
            profile = profiles[item["format"]]
            data = (base / item["path"]).resolve().read_bytes()
            request = ParseRequest.create(
                request_id=case_id, source_id="source.phase4b.gate",
                content_object_id="content.phase4b.gate",
                representation_id=f"representation.phase4b.{item['format']}",
                media_type=profile.media_type, profile_name=profile.name,
                original_bytes=data,
            )
            result = run_parser(request)
            observed = result.disposition
            artifacts.append(canonical_bytes(result.to_record()))
            executed["parsing"] += 1
        else:
            lifecycle, produced = _run_lifecycle_case(
                case_id, item["expected_outcome"], gate_root,
            )
            observed = lifecycle["observed_outcome"]
            artifacts.extend(produced)
            lifecycle_evidence.append(lifecycle)
            executed["lifecycle_integration"] += 1
        if observed != item["expected_outcome"]:
            raise ValueError(f"fixture outcome differs: {case_id}: {observed}")
        evidence_by_id[case_id]["observed_outcome"] = observed
        evidence_by_id[case_id]["execution_status"] = "passed"
    return {
        "status": "passed",
        "executed": executed,
        "lifecycle_evidence": lifecycle_evidence,
    }, artifacts


def _sample_payload() -> dict[str, Any]:
    h1, h2, h3 = ("sha256:" + character * 64 for character in "123")
    return {
        "candidate_id": "candidate.phase4b.gate", "source_id": "source.phase4b.gate",
        "request_id": "request.phase4b.gate", "normalized_url_hash": h1,
        "content_object_id": "content.phase4b.gate", "artifact_hash": h2,
        "byte_length": 32, "media_type_hash": h3,
        "acquisition_adapter_id": "adapter.phase4b.gate",
        "acquisition_adapter_version": "v1", "policy_snapshot_id": "policy.phase4b.gate",
        "rights_decision_ids": ["rights.acquire.gate", "rights.retain.gate"],
        "terms_snapshot_hash": h1, "robots_snapshot_hash": h2,
        "predecessor_record_ids": [],
    }


def _determinism_evidence(repository_root: Path, gate_root: Path) -> tuple[dict[str, Any], list[bytes]]:
    workspace_root = gate_root / "determinism"
    with Phase4BWorkspace(workspace_root) as workspace:
        workspace.append(
            record_type=RecordType.ACQUISITION_CANDIDATE,
            subject_id="source.phase4b.gate", payload=_sample_payload(), recorded_at=T0,
        )
        repeats = tuple(workspace.export_bytes() for _ in range(3))
        expected = repeats[0]
        if len(set(repeats)) != 1:
            raise ValueError("in-process Phase 4B exports differ")
        workspace.rebuild_projection(reverse=True)
        reverse = workspace.export_bytes()
        if reverse != expected:
            raise ValueError("reverse projection rebuild differs")
    with Phase4BWorkspace(workspace_root) as restarted:
        restart = restarted.export_bytes()
    if restart != expected or canonical_bytes(replay(expected)) != expected:
        raise ValueError("restart or replay differs")
    imported_root = gate_root / "imported"
    with Phase4BWorkspace(imported_root) as imported:
        imported.import_bytes(expected)
        imported_bytes = imported.export_bytes()
    if imported_bytes != expected:
        raise ValueError("imported replay differs")

    export_path = gate_root / "deterministic-export.json"
    export_path.write_bytes(expected)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(repository_root / "src")
    process_hashes: list[str] = []
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-m", "math_research.phase4b_cli", "inspect", str(export_path)],
            cwd=repository_root, env=environment, check=True, capture_output=True,
            text=True, timeout=30,
        )
        process_hashes.append(json.loads(completed.stdout)["content_hash"])
    expected_hash = json.loads(expected)["content_hash"]
    if process_hashes != [expected_hash, expected_hash]:
        raise ValueError("independent process semantic hashes differ")
    return {
        "status": "passed", "in_process_repeat_count": 3,
        "independent_process_count": 2, "restart_count": 1, "replay_count": 1,
        "reverse_order_rebuild_count": 1, "semantic_hashes_identical": True,
        "semantic_export_hash": expected_hash,
    }, [expected, reverse, restart, imported_bytes]


def _sandbox_probe_evidence(gate_root: Path) -> dict[str, Any]:
    runner = DarwinSandboxProbeRunner()
    read_target = gate_root / "sandbox-unapproved-read.bin"
    write_target = gate_root / "sandbox-write-escape.bin"
    read_target.write_bytes(b"project-authored sandbox probe")
    try:
        results = (
            runner.run("baseline"),
            runner.run("network"),
            runner.run("write", target=write_target),
            runner.run("process"),
            runner.run("read", target=read_target),
        )
    finally:
        read_target.unlink(missing_ok=True)
        write_target.unlink(missing_ok=True)
    statuses = {item.action: item.status for item in results}
    if statuses["baseline"] == "unavailable":
        status = "unavailable"
    elif statuses == {
        "baseline": "allowed", "network": "denied", "write": "denied",
        "process": "denied", "read": "denied",
    }:
        status = "passed_named_platform_probe"
    else:
        status = "failed_closed"
    return {
        "status": status,
        "platform": results[0].platform,
        "contract_schema": results[0].schema_version,
        "profile_hash": results[0].profile_hash,
        "probes": [item.value() for item in results],
        "production_parser_connected": False,
        "portable_claim": False,
    }


def _exact_sandbox_bridge_evidence(repository_root: Path) -> dict[str, Any]:
    """Exercise the strict HTML, TeX, and PDF semantics through the sandbox."""
    from .exact_sandbox_bridge import build_exact_darwin_sandbox_worker
    from .pdf_sandbox_bridge import build_pdf_darwin_sandbox_worker
    from .parsing import run_production_parser

    text_worker, text_artifact = build_exact_darwin_sandbox_worker()
    pdf_worker, pdf_artifact = build_pdf_darwin_sandbox_worker()
    cases = (
        ("html", HTML_PROFILE, repository_root / "fixtures/phase4b/parsing/authoritative.html", text_worker),
        ("tex", TEX_PROFILE, repository_root / "fixtures/phase4b/parsing/nonexecuting.tex", text_worker),
        ("pdf", PDF_PROFILE, repository_root / "fixtures/phase4b/parsing/strict-born-digital-valid.pdf", pdf_worker),
    )
    evidence: list[dict[str, Any]] = []
    for label, profile, path, worker in cases:
        original = path.read_bytes()
        request = ParseRequest.create(
            request_id=f"request.gate.exact-sandbox.{label}",
            source_id=f"source.gate.exact-sandbox.{label}",
            content_object_id=f"content.gate.exact-sandbox.{label}",
            representation_id=f"representation.gate.exact-sandbox.{label}",
            media_type=profile.media_type,
            profile_name=profile.name,
            original_bytes=original,
        )
        result = run_production_parser(request, worker=worker)
        if result.disposition == "candidate_proposal":
            verify_result_record(result.to_record(), original)
        evidence.append({
            "profile": label,
            "disposition": result.disposition,
            "failure_code": result.failure_code,
            "semantic_sha256": result.semantic_sha256,
            "segment_count": len(result.segments),
            "formula_count": sum(item.kind == "formula" for item in result.segments),
        })
    completed = all(item["disposition"] == "candidate_proposal" for item in evidence)
    unavailable = all(
        item["failure_code"] in {
            "sandbox_named_platform_unavailable", "sandbox_privileged_identity_rejected",
        }
        for item in evidence
    )
    return {
        "status": (
            "passed_named_darwin_html_tex_pdf" if completed
            else "unavailable" if unavailable else "failed_closed"
        ),
        "artifacts": {
            "html_tex": asdict(text_artifact),
            "pdf": asdict(pdf_artifact),
        },
        "cases": evidence,
        "production_parser_connected": completed,
        "profiles_connected": ["html", "pdf", "tex"] if completed else [],
        "pdf_connected": completed,
        "strict_transient_memory_enforcement": False,
        "portable_claim": False,
        "production_activated": False,
    }


def run_feasible_gate(repository_root: Path, gate_root: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    gate_root = gate_root.resolve()
    gate_root.mkdir(parents=True, exist_ok=True)
    before_phase3a = _phase3a_snapshot(repository_root)
    manifest, fixture_evidence = verify_fixture_manifest(repository_root)
    protected = verify_protected_evidence(repository_root)
    counters = {"socket_attempts": 0, "dns_attempts": 0}
    with _deny_ambient_network(counters):
        fixture_execution, artifacts = _run_fixture_oracles(
            repository_root, fixture_evidence, gate_root,
        )
    determinism, durable_artifacts = _determinism_evidence(repository_root, gate_root)
    sandbox_probe = _sandbox_probe_evidence(gate_root)
    exact_sandbox_bridge = _exact_sandbox_bridge_evidence(repository_root)
    from .corpus_authorization import run_parser_corpus_authorization

    parser_corpus_authorization = run_parser_corpus_authorization(repository_root)
    _policy, gate_policy_hash = _gate_policy(repository_root)
    artifacts.extend(durable_artifacts)
    persisted_paths = sorted(path for path in gate_root.rglob("*") if path.is_file())
    persisted_artifacts = [path.read_bytes() for path in persisted_paths]
    marker = CREDENTIAL_MARKER.encode("ascii")
    marker_matches = sum(
        artifact.count(marker) for artifact in artifacts + persisted_artifacts
    )
    if marker_matches:
        raise ValueError("credential marker reached persisted or canonical gate output")
    after_phase3a = _phase3a_snapshot(repository_root)
    phase3a_writes = sorted(
        set(before_phase3a) ^ set(after_phase3a)
        | {key for key in before_phase3a.keys() & after_phase3a.keys() if before_phase3a[key] != after_phase3a[key]}
    )
    if phase3a_writes:
        raise ValueError("Phase 4B gate changed Phase 3A state")
    network = {
        "status": "passed", **counters, "http_calls": 0, "model_api_calls": 0,
        "ambient_network_calls": counters["socket_attempts"] + counters["dns_attempts"],
    }
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "gate_policy_hash": gate_policy_hash,
        "activation_status": "blocked_pending_full_gate_controls",
        "manifest": manifest,
        "fixture_execution": fixture_execution,
        "fixture_evidence": fixture_evidence,
        "network_isolation": network,
        "phase3a_preservation": {
            "status": "passed", "objects_before": len(before_phase3a),
            "objects_after": len(after_phase3a), "writes_caused": 0,
            "snapshot_hash": canonical_hash(before_phase3a),
        },
        "protected_evidence": protected,
        "credential_marker_scan": {
            "status": "passed", "artifacts_scanned": len(artifacts),
            "persisted_files_scanned": len(persisted_artifacts),
            "exact_marker_matches": marker_matches,
        },
        "determinism": determinism,
        "os_sandbox_probe": sandbox_probe,
        "exact_parser_sandbox_bridge": exact_sandbox_bridge,
        "parser_corpus_authorization": parser_corpus_authorization,
        "blocked_controls": [
            {
                "control": "os_parser_sandbox",
                "status": "blocked",
                "reason": "all three strict candidates run in the Darwin sandbox, but RSS is sampled and no portable enforcement claim exists",
                "counted_as_pass": False,
            },
            {
                "control": "live_https_operator_transport",
                "status": "blocked",
                "reason": "the opt-in adapter and content-hashed operator harness exist, but the separately acknowledged external live-network gate has not executed",
                "counted_as_pass": False,
            },
        ],
    }
    report["content_hash"] = _hash_without(report, "content_hash")
    verify_feasible_gate_report(report, repository_root)
    return report


__all__ = [
    "CREDENTIAL_MARKER", "MANIFEST_SCHEMA", "MAX_REPORT_BYTES", "REPORT_SCHEMA",
    "load_feasible_gate_report", "run_feasible_gate", "verify_feasible_gate_report",
    "verify_fixture_manifest", "verify_protected_evidence",
]
