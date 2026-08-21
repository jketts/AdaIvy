"""Strict OCI parser-sandbox evidence for the Phase 4B activation combiner."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
from typing import Any

from .activation import SandboxActivationAttestation
from .corpus_authorization import _PROFILES, _fixture_path, _manifest
from .exact_sandbox_bridge import build_exact_oci_sandbox_worker
from .oci_parser_sandbox import (
    CONTRACT_VERSION,
    OciParserSandboxWorker,
    OciRuntimeIdentity,
    OciSandboxLimits, _policy,
)
from .parsing import ParseRequest, run_production_parser, verify_result_record
from .pdf_sandbox_bridge import build_pdf_oci_sandbox_worker
from .serialization import canonical_hash, sha256_bytes
from .service import Phase4BService


EVIDENCE_SCHEMA = "adaivy.phase4b-oci-sandbox-activation-evidence.v1"
MAX_EVIDENCE_BYTES = 262_144


def _request(case_id: str, profile, original: bytes) -> ParseRequest:
    return ParseRequest.create(
        request_id=f"request.oci-authorization.{case_id}",
        source_id=f"source.oci-authorization.{case_id}",
        content_object_id=f"content.oci-authorization.{case_id}",
        representation_id=f"representation.oci-authorization.{case_id}",
        media_type=profile.media_type,
        profile_name=profile.name,
        original_bytes=original,
    )


def _execution_record(worker: OciParserSandboxWorker, execution) -> dict[str, Any]:
    evidence = worker.last_evidence
    if evidence is None:
        raise ValueError("OCI worker did not retain execution evidence")
    value = {
        "execution": {
            "failure_code": execution.failure_code,
            "operation": execution.operation.to_record(),
            "status": execution.status,
        },
        "sandbox": evidence.to_record(),
    }
    value["content_hash"] = canonical_hash(value)
    return value


def _probe(
    runtime: OciRuntimeIdentity, label: str, source: str,
    request: ParseRequest, *, limits: OciSandboxLimits | None = None,
) -> dict[str, Any]:
    worker = OciParserSandboxWorker(
        name=f"phase4b-{label}-enforcement-probe", version="1.0.0",
        worker_source=source, expected_runtime=runtime, limits=limits,
    )
    execution = worker.execute(request)
    result = _execution_record(worker, execution)
    result["label"] = label
    result["content_hash"] = canonical_hash({
        key: value for key, value in result.items() if key != "content_hash"
    })
    return result


def run_oci_sandbox_activation_evidence(
    repository_root: Path,
    parser_corpus_authorization: dict[str, Any],
    runtime: OciRuntimeIdentity,
) -> dict[str, Any]:
    """Run the exact corpus and enforcement probes through the reviewed image.

    The returned record is non-activating and is accepted only by
    :func:`verify_oci_sandbox_activation_evidence` plus the independent
    activation combiner.
    """

    if (
        not isinstance(parser_corpus_authorization, dict)
        or parser_corpus_authorization.get("status") != "authorized"
        or parser_corpus_authorization.get("production_activated") is not False
        or parser_corpus_authorization.get("counts", {}).get("total") != 12
    ):
        raise ValueError("parser corpus authorization is not the closed authorized record")
    supplied_corpus_hash = parser_corpus_authorization.get("content_hash")
    if supplied_corpus_hash != canonical_hash({
        key: value for key, value in parser_corpus_authorization.items()
        if key != "content_hash"
    }):
        raise ValueError("parser corpus authorization hash differs")

    text_worker, text_artifact = build_exact_oci_sandbox_worker(expected_runtime=runtime)
    pdf_worker, pdf_artifact = build_pdf_oci_sandbox_worker(expected_runtime=runtime)
    if text_worker.policy_sha256 != pdf_worker.policy_sha256:
        raise ValueError("production OCI parser policies differ")
    original_artifacts = parser_corpus_authorization.get("artifacts")
    if not isinstance(original_artifacts, dict):
        raise ValueError("parser corpus artifacts are invalid")
    try:
        if (
            text_artifact.worker_source_sha256
            != original_artifacts["html_tex"]["worker_source_sha256"]
            or pdf_artifact.worker_source_sha256
            != original_artifacts["pdf"]["worker_source_sha256"]
        ):
            raise ValueError("OCI parser source differs from authorized corpus source")
    except (KeyError, TypeError) as error:
        raise ValueError("parser corpus artifact identity is incomplete") from error

    base, manifest = _manifest(repository_root.resolve())
    fixtures = [item for item in manifest["fixtures"] if item.get("class") == "parsing"]
    expected_cases = {
        item["case_id"]: item for item in parser_corpus_authorization.get("cases", [])
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }
    if len(fixtures) != 12 or len(expected_cases) != 12:
        raise ValueError("parser corpus case inventory differs")
    cases: list[dict[str, Any]] = []
    for item in fixtures:
        case_id = item.get("case_id")
        format_name = item.get("format")
        if not isinstance(case_id, str) or format_name not in _PROFILES:
            raise ValueError("parser fixture declaration differs")
        profile = _PROFILES[format_name]
        original = _fixture_path(base, item.get("path")).read_bytes()
        if (
            item.get("byte_length") != len(original)
            or item.get("sha256") != sha256_bytes(original)
            or not Phase4BService._content_signature_matches(profile.name, original)
        ):
            raise ValueError(f"parser fixture identity differs: {case_id}")
        worker = pdf_worker if format_name == "pdf" else text_worker
        request = _request(case_id, profile, original)
        result = run_production_parser(request, worker=worker)
        if result.disposition == "candidate_proposal":
            verify_result_record(result.to_record(), original)
        expected = expected_cases[case_id]
        if (
            result.disposition != expected.get("observed_disposition")
            or result.disposition != item.get("expected_outcome")
        ):
            raise ValueError(f"OCI parser corpus semantics differ: {case_id}")
        execution_evidence = worker.last_evidence
        if execution_evidence is None:
            raise ValueError("OCI parser execution evidence is absent")
        cases.append({
            "case_id": case_id,
            "disposition": result.disposition,
            "exact_disposition_match": result.disposition == item.get("expected_outcome"),
            "expected_disposition": item.get("expected_outcome"),
            "false_admission": (
                item.get("expected_outcome") == "quarantined"
                and result.disposition == "candidate_proposal"
            ),
            "fixture_sha256": sha256_bytes(original),
            "format": format_name,
            "parser_semantic_sha256": result.semantic_sha256,
            "sandbox_evidence": execution_evidence.to_record(),
            "sandbox_evidence_hash": canonical_hash(execution_evidence.to_record()),
        })

    probe_request = _request(
        "enforcement-probes", _PROFILES["html"],
        (repository_root / "fixtures/phase4b/parsing/authoritative.html").read_bytes(),
    )
    marker_name = "ADAIVY_PHASE4B_OCI_SECRET_PROBE"
    prior_marker = os.environ.get(marker_name)
    os.environ[marker_name] = "must-not-enter-container"
    try:
        probes = {
            "memory": _probe(
                runtime, "memory", "allocation = bytearray(100_000_000)",
                probe_request,
                limits=OciSandboxLimits(
                    max_memory_bytes=32 * 1_024 * 1_024,
                    max_wall_seconds=5, max_cpu_seconds=5,
                ),
            ),
            "network": _probe(
                runtime, "network",
                "import os, socket\ntry:\n socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'x', ('1.1.1.1', 9))\nexcept OSError:\n os._exit(73)\nos._exit(74)",
                probe_request,
            ),
            "read_only_root": _probe(
                runtime, "read-only-root",
                "import os\ntry:\n open('/phase4b-write-escape', 'wb').write(b'x')\nexcept OSError:\n os._exit(73)\nos._exit(74)",
                probe_request,
            ),
            "noexec_temporary": _probe(
                runtime, "noexec-temporary",
                "import os\np='/tmp/probe'\nopen(p,'wb').write(b'#!/bin/sh\\nexit 0\\n')\nos.chmod(p,0o700)\ntry:\n os.execv(p,(p,))\nexcept OSError:\n os._exit(73)\nos._exit(74)",
                probe_request,
            ),
            "no_ambient_secret": _probe(
                runtime, "no-ambient-secret",
                f"import os\nos._exit(74 if os.environ.get({marker_name!r}) else 73)",
                probe_request,
            ),
            "cpu": _probe(
                runtime, "cpu", "while True: pass", probe_request,
                limits=OciSandboxLimits(max_wall_seconds=4, max_cpu_seconds=1),
            ),
        }
    finally:
        if prior_marker is None:
            os.environ.pop(marker_name, None)
        else:
            os.environ[marker_name] = prior_marker

    evidence: dict[str, Any] = {
        "schema_version": EVIDENCE_SCHEMA,
        "parser_corpus_authorization_hash": supplied_corpus_hash,
        "parser_artifacts_hash": canonical_hash(original_artifacts),
        "environment": runtime.to_record(),
        "environment_hash": runtime.environment_sha256,
        "policy_hash": text_worker.policy_sha256,
        "status": "authorized",
        "profiles_connected": ["html", "pdf", "tex"],
        "strict_transient_memory_enforcement": True,
        "no_network_enforcement": True,
        "read_only_input_and_root_enforcement": True,
        "bounded_noexec_temporary_enforcement": True,
        "no_ambient_secrets_enforcement": True,
        "resource_limits_enforcement": True,
        "production_parser_connected": True,
        "production_activated": False,
        "oci_artifacts": {
            "html_tex": asdict(text_artifact),
            "pdf": asdict(pdf_artifact),
        },
        "cases": cases,
        "counts": {
            "exact_disposition_matches": sum(
                item["exact_disposition_match"] for item in cases
            ),
            "false_admissions": sum(item["false_admission"] for item in cases),
            "total": len(cases),
        },
        "enforcement_probes": probes,
    }
    evidence["content_hash"] = canonical_hash(evidence)
    verify_oci_sandbox_activation_evidence(evidence)
    return evidence


def _strict_execution_probe(
    value: object, expected_label: str, expected_code: str,
    expected_exit: int | None,
) -> None:
    if not isinstance(value, dict) or set(value) != {
        "content_hash", "execution", "label", "sandbox",
    }:
        raise ValueError("OCI enforcement probe fields differ")
    if value["content_hash"] != canonical_hash({
        key: item for key, item in value.items() if key != "content_hash"
    }):
        raise ValueError("OCI enforcement probe hash differs")
    execution = value["execution"]
    sandbox = value["sandbox"]
    if not isinstance(execution, dict) or not isinstance(sandbox, dict):
        raise ValueError("OCI enforcement probe payload differs")
    if execution.get("failure_code") != expected_code:
        raise ValueError("OCI enforcement probe failure differs")
    if value["label"] != expected_label:
        raise ValueError("OCI enforcement probe label differs")
    operation = execution.get("operation")
    if not isinstance(operation, dict) or (
        expected_exit is not None and operation.get("worker_exit_code") != expected_exit
    ):
        raise ValueError("OCI enforcement probe exit differs")
    if (
        sandbox.get("schema_version") != CONTRACT_VERSION
        or sandbox.get("strict_transient_memory_enforcement") is not True
        or sandbox.get("no_network_enforcement") is not True
        or sandbox.get("read_only_input_and_root_enforcement") is not True
        or sandbox.get("bounded_noexec_temporary_enforcement") is not True
        or sandbox.get("no_ambient_secrets_enforcement") is not True
        or sandbox.get("resource_limits_enforcement") is not True
    ):
        raise ValueError("OCI enforcement probe is not strict")


def verify_oci_sandbox_activation_evidence(value: object) -> SandboxActivationAttestation:
    """Strict raw-evidence verifier accepted by ``create_activation_evidence``."""

    fields = {
        "schema_version", "parser_corpus_authorization_hash",
        "parser_artifacts_hash", "environment", "environment_hash",
        "policy_hash", "status", "profiles_connected",
        "strict_transient_memory_enforcement", "no_network_enforcement",
        "read_only_input_and_root_enforcement",
        "bounded_noexec_temporary_enforcement", "no_ambient_secrets_enforcement",
        "resource_limits_enforcement", "production_parser_connected",
        "production_activated", "oci_artifacts", "cases", "counts",
        "enforcement_probes", "content_hash",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("OCI sandbox activation evidence fields differ")
    if value["schema_version"] != EVIDENCE_SCHEMA:
        raise ValueError("OCI sandbox activation evidence schema differs")
    supplied_hash = value["content_hash"]
    if supplied_hash != canonical_hash({
        key: item for key, item in value.items() if key != "content_hash"
    }):
        raise ValueError("OCI sandbox activation evidence hash differs")
    runtime_value = value["environment"]
    if not isinstance(runtime_value, dict):
        raise ValueError("OCI runtime evidence differs")
    runtime_record = dict(runtime_value)
    runtime_record["image_layers"] = tuple(runtime_record.get("image_layers", ()))
    runtime = OciRuntimeIdentity(**runtime_record)
    if runtime.environment_sha256 != value["environment_hash"]:
        raise ValueError("OCI sandbox environment binding differs")
    if canonical_hash(_policy(runtime, OciSandboxLimits())) != value["policy_hash"]:
        raise ValueError("OCI sandbox production policy binding differs")
    artifacts = value["oci_artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != {"html_tex", "pdf"}:
        raise ValueError("OCI sandbox artifact inventory differs")
    for artifact in artifacts.values():
        if (
            not isinstance(artifact, dict)
            or artifact.get("dependency_environment_sha256") != runtime.environment_sha256
            or artifact.get("sandbox_policy_sha256") != value["policy_hash"]
            or artifact.get("protocol_schema") != "phase4b-parser-worker-response-v2"
        ):
            raise ValueError("OCI sandbox artifact binding differs")
    cases = value["cases"]
    if (
        not isinstance(cases, list)
        or len(cases) != 12
        or len({item.get("case_id") for item in cases if isinstance(item, dict)}) != 12
        or {name: sum(item.get("format") == name for item in cases) for name in _PROFILES}
        != {"html": 4, "pdf": 4, "tex": 4}
    ):
        raise ValueError("OCI sandbox corpus case inventory differs")
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "case_id", "disposition", "exact_disposition_match",
            "expected_disposition", "false_admission", "fixture_sha256", "format",
            "parser_semantic_sha256", "sandbox_evidence",
            "sandbox_evidence_hash",
        }:
            raise ValueError("OCI sandbox corpus case fields differ")
        sandbox = case["sandbox_evidence"]
        if (
            not isinstance(sandbox, dict)
            or case["sandbox_evidence_hash"] != canonical_hash(sandbox)
            or sandbox.get("environment_sha256") != runtime.environment_sha256
            or sandbox.get("policy_sha256") != value["policy_hash"]
            or sandbox.get("worker_source_sha256") != artifacts[
                "pdf" if case["format"] == "pdf" else "html_tex"
            ].get("worker_source_sha256")
            or sandbox.get("strict_transient_memory_enforcement") is not True
            or sandbox.get("no_network_enforcement") is not True
            or sandbox.get("read_only_input_and_root_enforcement") is not True
            or sandbox.get("bounded_noexec_temporary_enforcement") is not True
            or sandbox.get("no_ambient_secrets_enforcement") is not True
            or sandbox.get("resource_limits_enforcement") is not True
            or case["exact_disposition_match"] is not True
            or case["false_admission"] is not False
            or case["disposition"] != case["expected_disposition"]
            or case["disposition"] not in {"candidate_proposal", "quarantined"}
            or (
                case["disposition"] == "candidate_proposal"
                and sandbox.get("status") != "completed"
            )
            or (
                case["disposition"] == "quarantined"
                and sandbox.get("status") != "completed_content_rejection"
            )
        ):
            raise ValueError("OCI sandbox corpus execution differs")
    if value["counts"] != {
        "exact_disposition_matches": 12,
        "false_admissions": 0,
        "total": 12,
    }:
        raise ValueError("OCI sandbox corpus counts differ")
    probes = value["enforcement_probes"]
    if not isinstance(probes, dict) or set(probes) != {
        "cpu", "memory", "network", "no_ambient_secret",
        "noexec_temporary", "read_only_root",
    }:
        raise ValueError("OCI enforcement probe inventory differs")
    _strict_execution_probe(
        probes["memory"], "memory", "sandbox_memory_limit_exceeded", 137,
    )
    if probes["memory"]["sandbox"].get("oom_killed") is not True:
        raise ValueError("OCI memory probe lacks kernel OOM evidence")
    for name in ("network", "no_ambient_secret", "noexec_temporary", "read_only_root"):
        labels = {
            "network": "network", "no_ambient_secret": "no-ambient-secret",
            "noexec_temporary": "noexec-temporary", "read_only_root": "read-only-root",
        }
        _strict_execution_probe(
            probes[name], labels[name], "sandbox_worker_failed", 73,
        )
    _strict_execution_probe(
        probes["cpu"], "cpu", "sandbox_cpu_limit_exceeded", None,
    )

    return SandboxActivationAttestation(
        evidence_schema=EVIDENCE_SCHEMA,
        evidence_hash=supplied_hash,
        parser_corpus_authorization_hash=value["parser_corpus_authorization_hash"],
        parser_artifacts_hash=value["parser_artifacts_hash"],
        environment_hash=value["environment_hash"],
        policy_hash=value["policy_hash"],
        status=value["status"],
        profiles_connected=tuple(value["profiles_connected"]),
        strict_transient_memory_enforcement=value["strict_transient_memory_enforcement"],
        no_network_enforcement=value["no_network_enforcement"],
        read_only_input_and_root_enforcement=value["read_only_input_and_root_enforcement"],
        bounded_noexec_temporary_enforcement=value["bounded_noexec_temporary_enforcement"],
        no_ambient_secrets_enforcement=value["no_ambient_secrets_enforcement"],
        resource_limits_enforcement=value["resource_limits_enforcement"],
        production_parser_connected=value["production_parser_connected"],
        production_activated=value["production_activated"],
    )


def load_oci_sandbox_activation_evidence(data: bytes) -> dict[str, Any]:
    """Load bounded canonical duplicate-free raw OCI sandbox evidence."""
    if not isinstance(data, bytes) or not data or len(data) > MAX_EVIDENCE_BYTES:
        raise ValueError("OCI sandbox activation evidence byte bound differs")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ValueError("OCI sandbox activation evidence contains a duplicate key")
            result[key] = item
        return result

    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("OCI sandbox activation evidence JSON is invalid") from error
    from .serialization import canonical_bytes

    if canonical_bytes(value) != data:
        raise ValueError("OCI sandbox activation evidence is not canonical")
    verify_oci_sandbox_activation_evidence(value)
    return value


__all__ = [
    "EVIDENCE_SCHEMA", "MAX_EVIDENCE_BYTES",
    "load_oci_sandbox_activation_evidence",
    "run_oci_sandbox_activation_evidence",
    "verify_oci_sandbox_activation_evidence",
]
