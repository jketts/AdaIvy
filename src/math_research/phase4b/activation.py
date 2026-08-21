"""Strict composition of independent Phase 4B activation evidence.

This module is an evidence combiner, never an activation switch.  It verifies
the deterministic feasible gate and the external live observation through
their own strict verifiers, then accepts parser-sandbox evidence only through
an explicitly supplied verifier.  The combined record contains hashes and
closed verdicts; it cannot replace or rewrite any of its input evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable, Sequence

from .gate import verify_feasible_gate_report
from .live_gate import verify_live_gate_report
from .serialization import canonical_bytes, canonical_hash


ACTIVATION_EVIDENCE_SCHEMA = "adaivy.phase4b-activation-evidence.v1"
MAX_ACTIVATION_EVIDENCE_BYTES = 65_536
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is not canonical sha256")
    return value


def _exact(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields differ")
    return value


@dataclass(frozen=True, slots=True)
class SandboxActivationAttestation:
    """Closed result returned by a separately reviewed sandbox verifier.

    The current sampled-RSS Darwin evidence cannot produce this attestation.
    A future verifier must validate its own raw schema before constructing it.
    """

    evidence_schema: str
    evidence_hash: str
    parser_corpus_authorization_hash: str
    parser_artifacts_hash: str
    environment_hash: str
    policy_hash: str
    status: str
    profiles_connected: tuple[str, ...]
    strict_transient_memory_enforcement: bool
    no_network_enforcement: bool
    read_only_input_and_root_enforcement: bool
    bounded_noexec_temporary_enforcement: bool
    no_ambient_secrets_enforcement: bool
    resource_limits_enforcement: bool
    production_parser_connected: bool
    production_activated: bool

    def __post_init__(self) -> None:
        for field in (
            "evidence_hash", "parser_corpus_authorization_hash",
            "parser_artifacts_hash", "environment_hash", "policy_hash",
        ):
            _sha256(getattr(self, field), f"sandbox {field}")
        if (
            not self.evidence_schema
            or self.status != "authorized"
            or self.profiles_connected != ("html", "pdf", "tex")
            or any(
                getattr(self, field) is not True
                for field in (
                    "strict_transient_memory_enforcement",
                    "no_network_enforcement",
                    "read_only_input_and_root_enforcement",
                    "bounded_noexec_temporary_enforcement",
                    "no_ambient_secrets_enforcement",
                    "resource_limits_enforcement",
                    "production_parser_connected",
                )
            )
            or self.production_activated is not False
        ):
            raise ValueError("parser sandbox activation attestation is not strict")

    def value(self) -> dict[str, Any]:
        return {
            "evidence_schema": self.evidence_schema,
            "evidence_hash": self.evidence_hash,
            "parser_corpus_authorization_hash": self.parser_corpus_authorization_hash,
            "parser_artifacts_hash": self.parser_artifacts_hash,
            "environment_hash": self.environment_hash,
            "policy_hash": self.policy_hash,
            "status": self.status,
            "profiles_connected": list(self.profiles_connected),
            "strict_transient_memory_enforcement": self.strict_transient_memory_enforcement,
            "no_network_enforcement": self.no_network_enforcement,
            "read_only_input_and_root_enforcement": self.read_only_input_and_root_enforcement,
            "bounded_noexec_temporary_enforcement": self.bounded_noexec_temporary_enforcement,
            "no_ambient_secrets_enforcement": self.no_ambient_secrets_enforcement,
            "resource_limits_enforcement": self.resource_limits_enforcement,
            "production_parser_connected": self.production_parser_connected,
            "production_activated": self.production_activated,
        }


SandboxEvidenceVerifier = Callable[[object], SandboxActivationAttestation]


def _verified_inputs(
    feasible_reports: Sequence[dict[str, Any]],
    live_report: dict[str, Any],
    sandbox_evidence: object,
    *,
    repository_root: Path,
    sandbox_verifier: SandboxEvidenceVerifier,
) -> tuple[tuple[dict[str, Any], dict[str, Any]], SandboxActivationAttestation]:
    if (
        isinstance(feasible_reports, (dict, str, bytes))
        or len(feasible_reports) != 2
        or feasible_reports[0] is feasible_reports[1]
    ):
        raise ValueError("exactly two separately loaded feasible-gate reports are required")
    feasible = tuple(
        verify_feasible_gate_report(report, repository_root)
        for report in feasible_reports
    )
    left_identity = _offline_run_identity(feasible[0])
    right_identity = _offline_run_identity(feasible[1])
    if left_identity != right_identity:
        raise ValueError("independent feasible-gate identities differ")
    verify_live_gate_report(live_report)
    if live_report["execution_status"] != "executed":
        raise ValueError("Phase 4B live gate did not execute")
    if (
        len(live_report["outcomes"]) != live_report["request_count"]
        or any(item.get("outcome") != "candidate_acquired" for item in live_report["outcomes"])
    ):
        raise ValueError("Phase 4B live gate did not acquire every authorized candidate")
    attestation = sandbox_verifier(sandbox_evidence)
    if not isinstance(attestation, SandboxActivationAttestation):
        raise ValueError("parser sandbox verifier returned the wrong type")
    corpus = feasible[0]["parser_corpus_authorization"]
    corpus_hash = _sha256(corpus.get("content_hash"), "parser corpus authorization hash")
    artifacts_hash = canonical_hash(corpus.get("artifacts"))
    if (
        attestation.parser_corpus_authorization_hash != corpus_hash
        or attestation.parser_artifacts_hash != artifacts_hash
    ):
        raise ValueError("parser sandbox evidence is not bound to feasible-gate artifacts")
    return feasible, attestation


def _offline_run_identity(feasible: dict[str, Any]) -> dict[str, str]:
    determinism = feasible["determinism"]
    manifest = feasible["manifest"]
    corpus = feasible["parser_corpus_authorization"]
    sandbox = feasible["exact_parser_sandbox_bridge"]
    probe = feasible["os_sandbox_probe"]
    return {
        "semantic_export_hash": _sha256(
            determinism.get("semantic_export_hash"), "semantic export hash"
        ),
        "manifest_content_hash": _sha256(
            manifest.get("content_hash"), "fixture manifest hash"
        ),
        "parser_corpus_authorization_hash": _sha256(
            corpus.get("content_hash"), "parser corpus authorization hash"
        ),
        "parser_sandbox_identity_hash": canonical_hash({
            "artifacts": sandbox.get("artifacts"),
            "cases": sandbox.get("cases"),
            "profile_hash": probe.get("profile_hash"),
        }),
    }


def _value(
    feasible: tuple[dict[str, Any], dict[str, Any]],
    live_report: dict[str, Any],
    attestation: SandboxActivationAttestation,
) -> dict[str, Any]:
    offline_identity = _offline_run_identity(feasible[0])
    result: dict[str, Any] = {
        "schema_version": ACTIVATION_EVIDENCE_SCHEMA,
        "status": "evidence_complete_pending_owner_activation",
        "activation_effect": "none",
        "production_activated": False,
        "deterministic_offline_evidence": {
            "schema_version": feasible[0]["schema_version"],
            "independent_gate_process_count": 2,
            "report_content_hashes": [item["content_hash"] for item in feasible],
            "gate_policy_hash": feasible[0]["gate_policy_hash"],
            "original_activation_status": feasible[0]["activation_status"],
            **offline_identity,
        },
        "external_live_evidence": {
            "schema_version": live_report["schema_version"],
            "content_hash": live_report["content_hash"],
            "semantic_result_hash": live_report["semantic_result_hash"],
            "operational_result_hash": live_report["operational_result_hash"],
            "request_count": live_report["request_count"],
            "successful_request_count": len(live_report["candidate_evidence"]),
        },
        "parser_sandbox_evidence": attestation.value(),
    }
    result["content_hash"] = canonical_hash(result)
    return result


def create_activation_evidence(
    feasible_reports: Sequence[dict[str, Any]],
    live_report: dict[str, Any],
    sandbox_evidence: object,
    *,
    repository_root: Path,
    sandbox_verifier: SandboxEvidenceVerifier,
) -> dict[str, Any]:
    """Create a non-activating record after independently verifying all inputs."""

    feasible, attestation = _verified_inputs(
        feasible_reports, live_report, sandbox_evidence,
        repository_root=repository_root, sandbox_verifier=sandbox_verifier,
    )
    return _value(feasible, live_report, attestation)


def verify_activation_evidence(
    report: dict[str, Any],
    feasible_reports: Sequence[dict[str, Any]],
    live_report: dict[str, Any],
    sandbox_evidence: object,
    *,
    repository_root: Path,
    sandbox_verifier: SandboxEvidenceVerifier,
) -> dict[str, Any]:
    """Verify a combined record against all three unchanged source reports."""

    _exact(report, {
        "schema_version", "status", "activation_effect", "production_activated",
        "deterministic_offline_evidence", "external_live_evidence",
        "parser_sandbox_evidence", "content_hash",
    }, "Phase 4B activation evidence")
    if report.get("schema_version") != ACTIVATION_EVIDENCE_SCHEMA:
        raise ValueError("Phase 4B activation evidence schema differs")
    supplied_hash = _sha256(report.get("content_hash"), "activation evidence hash")
    preimage = {key: value for key, value in report.items() if key != "content_hash"}
    if supplied_hash != canonical_hash(preimage):
        raise ValueError("Phase 4B activation evidence hash differs")
    feasible, attestation = _verified_inputs(
        feasible_reports, live_report, sandbox_evidence,
        repository_root=repository_root, sandbox_verifier=sandbox_verifier,
    )
    expected = _value(feasible, live_report, attestation)
    if canonical_bytes(report) != canonical_bytes(expected):
        raise ValueError("Phase 4B activation evidence does not match its sources")
    return report


def load_activation_evidence(
    data: bytes,
    feasible_reports: Sequence[dict[str, Any]],
    live_report: dict[str, Any],
    sandbox_evidence: object,
    *,
    repository_root: Path,
    sandbox_verifier: SandboxEvidenceVerifier,
) -> dict[str, Any]:
    """Decode a bounded duplicate-free JSON record and verify every source binding."""

    if not isinstance(data, bytes) or not data or len(data) > MAX_ACTIVATION_EVIDENCE_BYTES:
        raise ValueError("Phase 4B activation evidence byte bound differs")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Phase 4B activation evidence contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8", "strict"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Phase 4B activation evidence JSON is invalid") from error
    if canonical_bytes(value) != data:
        raise ValueError("Phase 4B activation evidence is not canonical")
    return verify_activation_evidence(
        value, feasible_reports, live_report, sandbox_evidence,
        repository_root=repository_root, sandbox_verifier=sandbox_verifier,
    )


__all__ = [
    "ACTIVATION_EVIDENCE_SCHEMA", "MAX_ACTIVATION_EVIDENCE_BYTES",
    "SandboxActivationAttestation", "SandboxEvidenceVerifier",
    "create_activation_evidence", "load_activation_evidence",
    "verify_activation_evidence",
]
