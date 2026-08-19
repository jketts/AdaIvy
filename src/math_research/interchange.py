"""Canonical Phase 1 ResearchDossier interchange and proposal-only imports."""

from __future__ import annotations

import hashlib
import json
import types
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from .domain.entities import (
    ALL_ENTITY_TYPES,
    ENTITY_SCHEMA_VERSION,
    AuditEvent,
    Claim,
    Disposition,
    Entity,
    EvaluationProtocol,
    Evidence,
    Formalization,
    OpaqueId,
    ProofObligation,
    ResearchDossier,
)

DOSSIER_SCHEMA_VERSION = "1.0.0"
HASH_PREFIX = "sha256:"
TYPE_BY_NAME = {item.__name__: item for item in ALL_ENTITY_TYPES}


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationIssue:
    schema_version: str
    path: str
    code: str
    message: str


class DossierValidationError(ValueError):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{item.path}: {item.message}" for item in issues))


@dataclass(frozen=True, slots=True, kw_only=True)
class ProposalArtifact:
    schema_version: str
    id: OpaqueId
    artifact_kind: str
    source_content_hash: str
    canonical_payload: str
    disposition: Disposition = Disposition.PROPOSAL


@dataclass(frozen=True, slots=True, kw_only=True)
class ProposalBundle:
    schema_version: str
    source_content_hash: str
    artifacts: tuple[ProposalArtifact, ...]
    disposition: Disposition = Disposition.PROPOSAL


def _datetime_text(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _primitive(value: Any) -> Any:
    if isinstance(value, OpaqueId):
        return value.value
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        result = {field.name: _primitive(getattr(value, field.name)) for field in fields(value)}
        if isinstance(value, Entity):
            result["object_type"] = type(value).__name__
        return result
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, list):
        return [_primitive(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in value.items()}
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    return HASH_PREFIX + hashlib.sha256(canonical_bytes(value)).hexdigest()


def export_dossier_dict(dossier: ResearchDossier) -> dict[str, Any]:
    payload = _primitive(dossier)
    payload["schema_version"] = DOSSIER_SCHEMA_VERSION
    payload["content_hash"] = None
    payload["content_hash"] = content_hash(payload)
    return payload


def export_dossier_bytes(dossier: ResearchDossier) -> bytes:
    return canonical_bytes(export_dossier_dict(dossier))


def write_dossier(dossier: ResearchDossier, path: Path) -> str:
    payload = export_dossier_dict(dossier)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload) + b"\n")
    return payload["content_hash"]


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def _decode_value(value: Any, annotation: Any) -> Any:
    if annotation is Any:
        return value
    if annotation is OpaqueId:
        return OpaqueId(value)
    if annotation is datetime:
        return _parse_datetime(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and issubclass(annotation, Entity):
        return _decode_entity(value, annotation)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is tuple:
        item_type = args[0]
        return tuple(_decode_value(item, item_type) for item in value)
    if origin in {Union, types.UnionType}:
        if value is None and type(None) in args:
            return None
        options = [item for item in args if item is not type(None)]
        last_error: Exception | None = None
        for option in options:
            try:
                return _decode_value(value, option)
            except (TypeError, ValueError) as error:
                last_error = error
        if last_error:
            raise last_error
    return value


def _decode_entity(payload: dict[str, Any], expected_type: type[Entity] | None = None) -> Entity:
    name = payload.get("object_type")
    entity_type = TYPE_BY_NAME.get(name)
    if entity_type is None:
        raise ValueError(f"unknown object_type: {name!r}")
    if expected_type is not None and entity_type is not expected_type:
        raise ValueError(f"expected {expected_type.__name__}, got {name}")
    annotations = get_type_hints(entity_type)
    kwargs = {
        field.name: _decode_value(payload[field.name], annotations[field.name])
        for field in fields(entity_type)
    }
    return entity_type(**kwargs)


def _walk_objects(value: Any, path: str = "$") -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(value, dict):
        if "object_type" in value:
            found.append((path, value))
        for key, item in value.items():
            found.extend(_walk_objects(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_walk_objects(item, f"{path}[{index}]"))
    return found


def validate_dossier_payload(payload: Any, *, verify_hash: bool = True) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    if not isinstance(payload, dict):
        return (ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$", code="type", message="dossier must be an object"),)
    required = {
        "schema_version", "object_type", "id", "created_at", "created_by",
        "problem", "formalization", "semantic_alignment", "claims", "warrants",
        "evidence", "source_applicability", "obligations", "representation_maps",
        "verification_records", "evaluation_protocol", "audit_events", "capabilities",
        "content_hash",
    }
    for key in sorted(required - set(payload)):
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.{key}", code="required", message="field is required"))
    if issues:
        return tuple(issues)
    if payload["schema_version"] != DOSSIER_SCHEMA_VERSION:
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$.schema_version", code="version", message="unsupported dossier schema version"))
    if payload["object_type"] != "ResearchDossier":
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$.object_type", code="type", message="top-level object must be ResearchDossier"))
    forbidden = {"truth_status", "confidence", "confidence_score"}
    for path, object_payload in _walk_objects(payload):
        if object_payload.get("schema_version") != ENTITY_SCHEMA_VERSION:
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"{path}.schema_version", code="version", message="unsupported public object version"))
        for key in forbidden & set(object_payload):
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"{path}.{key}", code="projection_storage", message="derived status/confidence may not be stored"))
    if verify_hash:
        observed = payload.get("content_hash")
        candidate = dict(payload)
        candidate["content_hash"] = None
        expected = content_hash(candidate)
        if observed != expected:
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$.content_hash", code="hash_mismatch", message="canonical content hash does not match"))
    if issues:
        return tuple(issues)
    try:
        dossier = _decode_entity(payload, ResearchDossier)
    except (KeyError, TypeError, ValueError) as error:
        return (ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$", code="decode", message=str(error)),)

    claim_ids = {item.id for item in dossier.claims}
    evidence_ids = {item.id for item in dossier.evidence}
    obligation_ids = {item.id for item in dossier.obligations}
    warrant_ids = {item.id for item in dossier.warrants}
    verification_ids = {item.id for item in dossier.verification_records}
    map_ids = {item.id for item in dossier.representation_maps}
    all_entities: tuple[Entity, ...] = (
        dossier.problem, dossier.formalization, dossier.semantic_alignment,
        *dossier.claims, *dossier.warrants, *dossier.evidence,
        *dossier.source_applicability, *dossier.obligations,
        *dossier.representation_maps, *dossier.verification_records,
        dossier.evaluation_protocol, *dossier.audit_events,
    )
    all_ids = [item.id for item in all_entities]
    if len(all_ids) != len(set(all_ids)):
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$", code="unique_ids", message="entity IDs must be unique within a dossier"))
    if dossier.formalization.problem_id != dossier.problem.id:
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$.formalization.problem_id", code="reference", message="formalization must reference dossier problem"))
    if dossier.formalization.target_claim_id not in claim_ids:
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$.formalization.target_claim_id", code="reference", message="target claim does not resolve"))
    if dossier.semantic_alignment.formalization_id != dossier.formalization.id:
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$.semantic_alignment.formalization_id", code="reference", message="alignment formalization does not resolve"))
    for claim in dossier.claims:
        if any(item not in claim_ids for item in claim.assumption_claim_ids):
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.claims[{claim.id}].assumption_claim_ids", code="reference", message="assumption claim does not resolve"))
        if any(item not in map_ids for item in claim.representation_map_ids):
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.claims[{claim.id}].representation_map_ids", code="reference", message="representation map does not resolve"))
    for warrant in dossier.warrants:
        if warrant.claim_id not in claim_ids or any(item not in evidence_ids for item in warrant.evidence_ids) or any(item not in verification_ids for item in warrant.verification_record_ids):
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.warrants[{warrant.id}]", code="reference", message="warrant reference does not resolve"))
    for item in dossier.evidence:
        if item.claim_id not in claim_ids:
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.evidence[{item.id}].claim_id", code="reference", message="evidence claim does not resolve"))
        if item.artifact_hash != content_hash(item.content):
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.evidence[{item.id}].artifact_hash", code="hash_mismatch", message="evidence content hash does not match"))
    for record in dossier.source_applicability:
        if record.evidence_id not in evidence_ids or record.implication_obligation_id not in obligation_ids:
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.source_applicability[{record.id}]", code="reference", message="applicability reference does not resolve"))
    for obligation in dossier.obligations:
        if obligation.claim_id not in claim_ids or (obligation.discharged_by_warrant_id is not None and obligation.discharged_by_warrant_id not in warrant_ids):
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.obligations[{obligation.id}]", code="reference", message="obligation reference does not resolve"))
    return tuple(issues)


SCENARIO_KINDS = {
    "known_valid_theorem",
    "false_universal_exact_counterexample",
    "formally_provable_mistranslation",
    "real_but_inapplicable_theorem",
    "representation_bridge_drops_edge_case",
}


def validate_scenario_payload(payload: Any) -> tuple[ValidationIssue, ...]:
    if not isinstance(payload, dict):
        return (ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$", code="type", message="scenario must be an object"),)
    required = {"schema_version", "scenario_id", "kind", "target", "condition", "expected"}
    issues: list[ValidationIssue] = []
    if set(payload) != required:
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$", code="fields", message="scenario fields do not match schema"))
    if payload.get("schema_version") != ENTITY_SCHEMA_VERSION:
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$.schema_version", code="version", message="unsupported scenario version"))
    if payload.get("kind") not in SCENARIO_KINDS:
        issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$.kind", code="enum", message="unknown scenario kind"))
    for key in ("scenario_id", "target"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.{key}", code="type", message="must be a non-empty string"))
    for key in ("condition", "expected"):
        if not isinstance(payload.get(key), dict):
            issues.append(ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path=f"$.{key}", code="type", message="must be an object"))
    return tuple(issues)


def import_trusted_replay(data: bytes | str | dict[str, Any]) -> ResearchDossier:
    payload = data if isinstance(data, dict) else json.loads(data)
    issues = validate_dossier_payload(payload)
    if issues:
        raise DossierValidationError(issues)
    dossier = _decode_entity(payload, ResearchDossier)
    assert isinstance(dossier, ResearchDossier)
    if export_dossier_dict(dossier)["content_hash"] != payload["content_hash"]:
        raise DossierValidationError((ValidationIssue(schema_version=ENTITY_SCHEMA_VERSION, path="$.content_hash", code="round_trip", message="decoded dossier changes canonical content hash"),))
    return dossier


def import_external_proposals(data: bytes | str | dict[str, Any]) -> ProposalBundle:
    payload = data if isinstance(data, dict) else json.loads(data)
    issues = validate_dossier_payload(payload)
    if issues:
        raise DossierValidationError(issues)
    source_hash = payload["content_hash"]
    artifacts: list[ProposalArtifact] = []
    for path, item in _walk_objects(payload):
        if item["object_type"] in {"Claim", "EpistemicWarrant", "Evidence", "VerificationRecord"}:
            artifacts.append(
                ProposalArtifact(
                    schema_version=ENTITY_SCHEMA_VERSION,
                    id=OpaqueId(item["id"]),
                    artifact_kind=item["object_type"],
                    source_content_hash=source_hash,
                    canonical_payload=canonical_bytes(item).decode("utf-8"),
                )
            )
    return ProposalBundle(
        schema_version=ENTITY_SCHEMA_VERSION,
        source_content_hash=source_hash,
        artifacts=tuple(artifacts),
    )
