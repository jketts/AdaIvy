"""Structural and semantic validation for the Phase 0 dossier contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .canonical import backend_result_hash, dossier_hash

HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
ALLOWED_ALIGNMENT_STATUSES = {
    "proposed",
    "researcher_approved",
    "disputed",
    "superseded",
}
OPEN_OBLIGATION_STATUSES = {"open", "assigned", "blocked"}


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


REQUIRED_TOP_LEVEL = (
    "schema_version",
    "dossier_id",
    "problem",
    "formalization",
    "semantic_alignment",
    "claims",
    "open_obligations",
    "source_cards",
    "representation_maps",
    "capabilities",
    "evaluation_protocol",
    "budget",
    "artifact_manifest",
    "failed_routes",
    "verifier_context_manifest",
    "content_hash",
)


def _ids(records: Iterable[dict[str, Any]]) -> list[str]:
    return [record.get("id", "") for record in records]


def validate_dossier(dossier: Any, *, verify_hash: bool = True) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(dossier, dict):
        return [ValidationIssue("$", "type", "dossier must be an object")]

    for field in REQUIRED_TOP_LEVEL:
        if field not in dossier:
            issues.append(ValidationIssue(f"$.{field}", "required", "field is required"))
    if issues:
        return issues

    if dossier["schema_version"] != "0.1.0-phase0":
        issues.append(
            ValidationIssue("$.schema_version", "version", "unsupported schema version")
        )

    object_fields = (
        "problem",
        "formalization",
        "semantic_alignment",
        "evaluation_protocol",
        "budget",
        "artifact_manifest",
        "verifier_context_manifest",
    )
    list_fields = (
        "claims",
        "open_obligations",
        "source_cards",
        "representation_maps",
        "capabilities",
        "failed_routes",
    )
    for field in object_fields:
        if not isinstance(dossier[field], dict):
            issues.append(ValidationIssue(f"$.{field}", "type", "must be an object"))
    for field in list_fields:
        if not isinstance(dossier[field], list):
            issues.append(ValidationIssue(f"$.{field}", "type", "must be an array"))
    if issues:
        return issues

    claim_ids = _ids(dossier["claims"])
    if "" in claim_ids or len(set(claim_ids)) != len(claim_ids):
        issues.append(ValidationIssue("$.claims", "unique_ids", "claim IDs must be unique and non-empty"))
    for index, claim in enumerate(dossier["claims"]):
        for assumption_id in claim.get("assumption_claim_ids", []):
            if assumption_id not in claim_ids:
                issues.append(ValidationIssue(f"$.claims[{index}].assumption_claim_ids", "reference", "assumption claim does not resolve"))
        if claim.get("truth_status") == "proved":
            warrant_kinds = {warrant.get("kind") for warrant in claim.get("warrants", [])}
            if warrant_kinds and warrant_kinds <= {"experimentally_observed"}:
                issues.append(ValidationIssue(f"$.claims[{index}].truth_status", "experimental_overreach", "finite experimental evidence cannot prove an unrestricted claim"))

    formalization = dossier["formalization"]
    alignment = dossier["semantic_alignment"]
    target_id = formalization.get("target_claim_id")
    if target_id not in claim_ids:
        issues.append(ValidationIssue("$.formalization.target_claim_id", "reference", "target claim does not resolve"))
    if formalization.get("problem_id") != dossier["problem"].get("id"):
        issues.append(ValidationIssue("$.formalization.problem_id", "reference", "formalization problem does not match"))
    if alignment.get("formalization_id") != formalization.get("id"):
        issues.append(ValidationIssue("$.semantic_alignment.formalization_id", "reference", "alignment formalization does not match"))
    if alignment.get("compared_claim_id") != target_id:
        issues.append(ValidationIssue("$.semantic_alignment.compared_claim_id", "target_fidelity", "alignment must compare the exact target"))
    if alignment.get("status") not in ALLOWED_ALIGNMENT_STATUSES:
        issues.append(ValidationIssue("$.semantic_alignment.status", "enum", "unknown alignment status"))
    if alignment.get("status") == "researcher_approved" and not alignment.get("approved_by"):
        issues.append(ValidationIssue("$.semantic_alignment.approved_by", "approval", "approved alignment needs a reviewer"))

    obligation_ids = _ids(dossier["open_obligations"])
    for index, obligation in enumerate(dossier["open_obligations"]):
        if obligation.get("claim_id") not in claim_ids:
            issues.append(ValidationIssue(f"$.open_obligations[{index}].claim_id", "reference", "obligation claim does not resolve"))
        if obligation.get("status") not in OPEN_OBLIGATION_STATUSES:
            issues.append(ValidationIssue(f"$.open_obligations[{index}].status", "open_status", "exported open obligation must remain non-terminal"))

    source_span_ids: set[str] = set()
    for index, card in enumerate(dossier["source_cards"]):
        required = (
            "id",
            "local_claim_id",
            "source_span",
            "imported_statement",
            "imported_hypotheses",
            "bibliographic_status",
            "applicability_status",
            "implication_obligation_id",
        )
        for field in required:
            if field not in card:
                issues.append(ValidationIssue(f"$.source_cards[{index}].{field}", "required", "field is required"))
        if card.get("local_claim_id") not in claim_ids:
            issues.append(ValidationIssue(f"$.source_cards[{index}].local_claim_id", "reference", "source-card claim does not resolve"))
        if card.get("implication_obligation_id") not in obligation_ids:
            issues.append(ValidationIssue(f"$.source_cards[{index}].implication_obligation_id", "applicability", "applicability must resolve to an exported open obligation"))
        span = card.get("source_span")
        if not isinstance(span, dict) or not span.get("raw_content") or not span.get("content_hash"):
            issues.append(ValidationIssue(f"$.source_cards[{index}].source_span", "provenance", "exact content and hash are required"))
        elif span.get("id") in source_span_ids:
            issues.append(ValidationIssue(f"$.source_cards[{index}].source_span.id", "unique_ids", "source span IDs must be unique"))
        else:
            source_span_ids.add(span.get("id"))

    for index, mapping in enumerate(dossier["representation_maps"]):
        if mapping.get("encoding_claim_id") not in claim_ids:
            issues.append(ValidationIssue(f"$.representation_maps[{index}].encoding_claim_id", "reference", "encoding claim does not resolve"))
        for obligation_id in mapping.get("bridge_obligation_ids", []):
            if obligation_id not in obligation_ids:
                issues.append(ValidationIssue(f"$.representation_maps[{index}].bridge_obligation_ids", "reference", "bridge obligation does not resolve"))

    manifest = dossier["verifier_context_manifest"]
    if manifest.get("target_claim_ids") != [target_id]:
        issues.append(ValidationIssue("$.verifier_context_manifest.target_claim_ids", "isolation", "verifier manifest must contain the exact target"))
    if not isinstance(manifest.get("excluded_artifact_ids"), list):
        issues.append(ValidationIssue("$.verifier_context_manifest.excluded_artifact_ids", "isolation", "excluded artifacts must be explicit"))

    artifact_ids = {
        artifact.get("id") for artifact in dossier["artifact_manifest"].get("artifacts", [])
    }
    for artifact_id in manifest.get("candidate_artifact_ids", []) + manifest.get("excluded_artifact_ids", []):
        if artifact_id not in artifact_ids:
            issues.append(ValidationIssue("$.verifier_context_manifest", "reference", "verifier artifact does not resolve"))
    for index, route in enumerate(dossier["failed_routes"]):
        if route.get("target_claim_id") not in claim_ids:
            issues.append(ValidationIssue(f"$.failed_routes[{index}].target_claim_id", "reference", "failed route target does not resolve"))
        for artifact_id in route.get("artifact_ids", []):
            if artifact_id not in artifact_ids:
                issues.append(ValidationIssue(f"$.failed_routes[{index}].artifact_ids", "reference", "failed-route artifact does not resolve"))

    protocol = dossier["evaluation_protocol"]
    if protocol.get("phase") == "confirmatory" and not protocol.get("frozen_at"):
        issues.append(ValidationIssue("$.evaluation_protocol.frozen_at", "evaluation_integrity", "confirmatory protocol must be frozen"))

    if verify_hash:
        value = dossier.get("content_hash")
        if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
            issues.append(ValidationIssue("$.content_hash", "hash_format", "content hash must be sha256:<hex>"))
        elif value != dossier_hash(dossier):
            issues.append(ValidationIssue("$.content_hash", "hash_mismatch", "content hash does not match canonical dossier"))

    return issues


def validate_backend_result(result: Any, *, verify_hash: bool = True) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(result, dict):
        return [ValidationIssue("$", "type", "backend result must be an object")]
    required = (
        "schema_version", "backend", "input_dossier_hash", "status",
        "candidate_artifacts", "failures", "cost", "run_manifest", "export_hash",
    )
    for field in required:
        if field not in result:
            issues.append(ValidationIssue(f"$.{field}", "required", "field is required"))
    if issues:
        return issues
    if result["schema_version"] != "0.1.0-phase0":
        issues.append(ValidationIssue("$.schema_version", "version", "unsupported schema version"))
    if result["status"] not in {"succeeded", "failed", "blocked", "partial"}:
        issues.append(ValidationIssue("$.status", "enum", "unknown backend result status"))
    if not isinstance(result["candidate_artifacts"], list):
        issues.append(ValidationIssue("$.candidate_artifacts", "type", "must be an array"))
    else:
        for index, artifact in enumerate(result["candidate_artifacts"]):
            if artifact.get("disposition") != "proposal":
                issues.append(ValidationIssue(f"$.candidate_artifacts[{index}].disposition", "trust_boundary", "external artifacts must import as proposals"))
            if "trusted_verdict" in artifact:
                issues.append(ValidationIssue(f"$.candidate_artifacts[{index}].trusted_verdict", "trust_boundary", "backend cannot set a local trusted verdict"))
    if result["status"] in {"failed", "blocked"} and not result["failures"]:
        issues.append(ValidationIssue("$.failures", "failure_retention", "failed and blocked runs must retain a failure"))
    if verify_hash:
        if not isinstance(result["export_hash"], str) or not HASH_PATTERN.fullmatch(result["export_hash"]):
            issues.append(ValidationIssue("$.export_hash", "hash_format", "export hash must be sha256:<hex>"))
        elif result["export_hash"] != backend_result_hash(result):
            issues.append(ValidationIssue("$.export_hash", "hash_mismatch", "export hash does not match canonical result"))
    return issues
