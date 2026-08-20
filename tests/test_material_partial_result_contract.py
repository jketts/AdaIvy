"""Executable preproduction contract for material partial-result surfacing v1.

The test model deliberately contains no production repository, migration, CLI,
or authority path.  It freezes closed interchange, semantic binding, immutable
event identity, separate append-only steering, and lifecycle projections for a
later owner-approved production gate.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import unittest
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from math_research.phase4a.records import ActorKind, Authority


ROOT = Path(__file__).resolve().parents[1]
MAX_ENVELOPE_BYTES = 2_097_152
MAX_RECORDS = 256
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,255}$")
VERSION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
CLASSIFICATIONS = {"refutes", "restricts", "strengthens", "generalizes", "redirects"}
ACTIONS = {"continue_objective", "investigate_result", "redirect_objective", "acknowledge", "dismiss"}
METHODS = {"human_review", "deterministic_check", "formal_kernel", "rigorous_certificate", "exact_counterexample"}
REFERENCE_KINDS = {"evidence", "certificate", "proof", "verified_artifact"}
CHANGE_KINDS = {
    "correction", "supersession", "revocation", "takedown", "deletion",
    "withdrawal", "rights_applicability_changed", "applicability_review_changed",
}
ALLOWED_CAUSAL_TYPES = {"verification", "evidence", "formal_finding", "source_lifecycle", "applicability_review"}
SCHEMA_PATHS = (
    ROOT / "schemas/material-partial-result-event-v1.schema.json",
    ROOT / "schemas/material-partial-result-steering-action-v1.schema.json",
    ROOT / "schemas/material-partial-result-lifecycle-v1.schema.json",
)


class ContractRejected(ValueError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def content_hash(envelope: dict[str, Any]) -> str:
    preimage = copy.deepcopy(envelope)
    preimage.pop("content_hash", None)
    return digest(preimage)


def seal(envelope: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(envelope)
    value["content_hash"] = content_hash(value)
    return value


def strict_json_loads(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_ENVELOPE_BYTES:
        raise ContractRejected("envelope exceeds the raw-byte limit")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ContractRejected("envelope is not UTF-8") from error

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ContractRejected(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ContractRejected(f"non-finite JSON number: {item}")
            ),
        )
    except json.JSONDecodeError as error:
        raise ContractRejected("malformed JSON envelope") from error
    if not isinstance(value, dict):
        raise ContractRejected("envelope must be an object")
    return value


def exact_fields(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractRejected(f"{label} fields differ")
    return value


def identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or ID_RE.fullmatch(value) is None:
        raise ContractRejected(f"invalid {label}")
    return value


def hash_value(value: object, label: str) -> str:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        raise ContractRejected(f"invalid {label}")
    return value


def policy_version(value: object, label: str) -> str:
    if not isinstance(value, str) or VERSION_RE.fullmatch(value) is None:
        raise ContractRejected(f"invalid {label}")
    return value


def bounded_string(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise ContractRejected(f"invalid {label}")
    return value


def timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64 or RFC3339_RE.fullmatch(value) is None:
        raise ContractRejected("invalid RFC-3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractRejected("invalid RFC-3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractRejected("timestamp must include an offset")
    return value


def strict_integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractRejected(f"invalid {label}")
    return value


def unique_array(value: object, label: str, minimum: int, maximum: int) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ContractRejected(f"invalid {label}")
    identities = [canonical_bytes(item) for item in value]
    if len(identities) != len(set(identities)):
        raise ContractRejected(f"duplicate {label}")
    return value


def nullable_id(value: object, label: str) -> str | None:
    if value is None:
        return None
    return identifier(value, label)


@dataclass(frozen=True)
class ObjectiveRecord:
    id: str
    active: bool
    permitted: bool


@dataclass(frozen=True)
class RunRecord:
    id: str
    objective_id: str
    active: bool


@dataclass(frozen=True)
class BranchRecord:
    id: str
    objective_id: str
    run_id: str
    active: bool
    permitted: bool


@dataclass(frozen=True)
class PrincipalRecord:
    id: str
    actor_kind: ActorKind
    authority: Authority


@dataclass(frozen=True)
class CapabilityRecord:
    id: str
    principal_id: str
    capability: str


@dataclass(frozen=True)
class PolicyRecord:
    id: str
    version: str
    content_hash: str


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    content_hash: str
    objective_id: str
    run_id: str
    source_record_id: str
    applicability_review_id: str
    lifecycle_state: str = "active"
    rights_state: str = "allowed"
    applicability_state: str = "checked_applicable"

    @property
    def eligible(self) -> bool:
        return (
            self.lifecycle_state == "active"
            and self.rights_state == "allowed"
            and self.applicability_state == "checked_applicable"
        )


@dataclass(frozen=True)
class VerificationRecord:
    id: str
    result_digest: str
    objective_id: str
    run_id: str
    evidence_ids: tuple[str, ...]
    method: str
    policy_id: str
    policy_version: str
    independently_verified: bool


@dataclass(frozen=True)
class MaterialityRecord:
    id: str
    result_digest: str
    objective_id: str
    policy_id: str
    policy_version: str


@dataclass(frozen=True)
class CausalRecord:
    id: str
    record_type: str
    objective_id: str
    run_id: str


def result_digest_for(event: dict[str, Any]) -> str:
    identity = event["result_identity"]
    return digest({
        "statement": identity["statement"],
        "object_id": identity["object_id"],
        "domain": identity["domain"],
        "objective_id": event["objective_id"],
        "run_id": event["run_id"],
        "branch_id": event["branch_id"],
        "evidence_snapshot_hash": identity["evidence_snapshot_hash"],
        "canonicalization_version": identity["canonicalization_version"],
    })


BASE_EVIDENCE_HASH = "sha256:" + "1" * 64
BASE_EVIDENCE_REFS = [{
    "reference_id": "evidence.counterexample",
    "reference_kind": "certificate",
    "content_hash": BASE_EVIDENCE_HASH,
}]
BASE_EVIDENCE_SNAPSHOT = digest(BASE_EVIDENCE_REFS)


def _unsealed_base_event(classification: str = "refutes") -> dict[str, Any]:
    event = {
        "event_id": "material-result.counterexample-1",
        "event_type": "research.material_partial_result_surfaced",
        "semantic_idempotency_key": "material-result:run.active:counterexample-1",
        "objective_id": "problem.active",
        "run_id": "run.active",
        "branch_id": "branch.active",
        "classification": classification,
        "result_identity": {
            "statement": "The candidate universal statement fails for an exact witness.",
            "object_id": "claim.universal",
            "domain": "integer arithmetic",
            "evidence_snapshot_hash": BASE_EVIDENCE_SNAPSHOT,
            "canonicalization_version": "material-result-canonical-v1",
            "result_digest": "sha256:" + "0" * 64,
        },
        "materiality_explanation": "The witness rules out the active theorem as stated and changes the next research choice.",
        "materiality_assessment_id": "materiality.user-impact",
        "evidence_references": copy.deepcopy(BASE_EVIDENCE_REFS),
        "verification": {
            "status": "verified",
            "method": "exact_counterexample",
            "verification_record_ids": ["verification.exact-counterexample"],
            "policy_id": "policy.material-result",
            "policy_version": "material-result-policy-v1",
        },
        "originating_principal_id": "actor.model.explorer",
        "created_by_principal_id": "actor.system.orchestrator",
        "capability_id": "capability.surface-result",
        "required_capability": "surface_verified_result",
        "created_at": "2026-08-20T12:00:00Z",
        "causal_parent_ids": ["verification.exact-counterexample"],
        "policy_id": "policy.material-result",
        "policy_version": "material-result-policy-v1",
        "main_objective_incomplete": True,
        "available_steering_actions": sorted(ACTIONS),
    }
    event["result_identity"]["result_digest"] = result_digest_for(event)
    return event


BASE_RESULT_DIGEST = _unsealed_base_event()["result_identity"]["result_digest"]


class ContractContext:
    def __init__(self) -> None:
        self.objectives = {
            "problem.active": ObjectiveRecord("problem.active", True, True),
            "problem.redirected": ObjectiveRecord("problem.redirected", True, True),
        }
        self.runs = {"run.active": RunRecord("run.active", "problem.active", True)}
        self.branches = {
            "branch.active": BranchRecord("branch.active", "problem.active", "run.active", True, True),
            "branch.redirected": BranchRecord("branch.redirected", "problem.redirected", "run.active", True, True),
        }
        self.principals = {
            "actor.model.explorer": PrincipalRecord("actor.model.explorer", ActorKind.MODEL, Authority.PROPOSAL),
            "actor.system.orchestrator": PrincipalRecord("actor.system.orchestrator", ActorKind.SYSTEM, Authority.DETERMINISTIC_POLICY),
            "actor.human.owner": PrincipalRecord("actor.human.owner", ActorKind.HUMAN, Authority.HUMAN_FINAL),
        }
        self.capabilities = {
            "capability.surface-result": CapabilityRecord("capability.surface-result", "actor.system.orchestrator", "surface_verified_result"),
            "capability.steer-research": CapabilityRecord("capability.steer-research", "actor.human.owner", "steer_research"),
            "capability.review-lifecycle": CapabilityRecord("capability.review-lifecycle", "actor.human.owner", "review_result_lifecycle"),
        }
        self.policies = {
            "policy.material-result": PolicyRecord("policy.material-result", "material-result-policy-v1", "sha256:" + "2" * 64),
        }
        self.evidence = {
            "evidence.counterexample": EvidenceRecord(
                "evidence.counterexample", BASE_EVIDENCE_HASH, "problem.active", "run.active",
                "source.lifecycle.active", "applicability.checked",
            )
        }
        self.verification_records = {
            "verification.exact-counterexample": VerificationRecord(
                "verification.exact-counterexample", BASE_RESULT_DIGEST, "problem.active", "run.active",
                ("evidence.counterexample",), "exact_counterexample", "policy.material-result",
                "material-result-policy-v1", True,
            )
        }
        self.materiality_records = {
            "materiality.user-impact": MaterialityRecord(
                "materiality.user-impact", BASE_RESULT_DIGEST, "problem.active",
                "policy.material-result", "material-result-policy-v1",
            )
        }
        self.causal_records = {
            "verification.exact-counterexample": CausalRecord(
                "verification.exact-counterexample", "verification", "problem.active", "run.active"
            )
        }

    def with_evidence(self, **changes: str) -> "ContractContext":
        updated = copy.deepcopy(self)
        current = updated.evidence["evidence.counterexample"]
        updated.evidence[current.id] = replace(current, **changes)
        return updated


def validate_policy(policy_id: object, version: object, context: ContractContext) -> PolicyRecord:
    resolved_id = identifier(policy_id, "policy ID")
    resolved_version = policy_version(version, "policy version")
    policy = context.policies.get(resolved_id)
    if policy is None or policy.version != resolved_version:
        raise ContractRejected("unknown policy identity or version")
    return policy


def validate_capability(
    principal_id: object,
    capability_id: object,
    required: object,
    context: ContractContext,
    *,
    human_only: bool,
) -> PrincipalRecord:
    resolved_principal = identifier(principal_id, "principal ID")
    resolved_capability = identifier(capability_id, "capability ID")
    bounded_string(required, "required capability", 128)
    principal = context.principals.get(resolved_principal)
    capability = context.capabilities.get(resolved_capability)
    if principal is None or capability is None:
        raise ContractRejected("unknown principal or capability")
    if capability.principal_id != principal.id or capability.capability != required:
        raise ContractRejected("capability is not granted to principal")
    if human_only and (principal.actor_kind is not ActorKind.HUMAN or principal.authority is not Authority.HUMAN_FINAL):
        raise ContractRejected("operation requires trusted human-final authority")
    if not human_only and principal.authority not in {Authority.HUMAN_FINAL, Authority.DETERMINISTIC_POLICY}:
        raise ContractRejected("principal authority cannot surface verified results")
    return principal


def validate_event_structure(envelope: dict[str, Any]) -> dict[str, Any]:
    exact_fields(envelope, {"schema_version", "record_type", "event", "content_hash"}, "event envelope")
    if envelope["schema_version"] != "adaivy.material-partial-result-event.v1" or envelope["record_type"] != "material_partial_result_event":
        raise ContractRejected("unsupported event schema or record type")
    event = exact_fields(envelope["event"], {
        "event_id", "event_type", "semantic_idempotency_key", "objective_id", "run_id", "branch_id",
        "classification", "result_identity", "materiality_explanation", "materiality_assessment_id",
        "evidence_references", "verification", "originating_principal_id", "created_by_principal_id",
        "capability_id", "required_capability", "created_at", "causal_parent_ids", "policy_id",
        "policy_version", "main_objective_incomplete", "available_steering_actions",
    }, "event")
    identifier(event["event_id"], "event ID")
    if event["event_type"] != "research.material_partial_result_surfaced":
        raise ContractRejected("wrong event type")
    bounded_string(event["semantic_idempotency_key"], "semantic idempotency key", 256)
    identifier(event["objective_id"], "objective ID"); identifier(event["run_id"], "run ID")
    nullable_id(event["branch_id"], "branch ID")
    if event["classification"] not in CLASSIFICATIONS:
        raise ContractRejected("unknown classification")
    identity = exact_fields(event["result_identity"], {
        "statement", "object_id", "domain", "evidence_snapshot_hash", "canonicalization_version", "result_digest",
    }, "result identity")
    bounded_string(identity["statement"], "result statement", 4096)
    identifier(identity["object_id"], "object ID"); bounded_string(identity["domain"], "domain", 256)
    hash_value(identity["evidence_snapshot_hash"], "evidence snapshot hash")
    policy_version(identity["canonicalization_version"], "canonicalization version")
    hash_value(identity["result_digest"], "result digest")
    bounded_string(event["materiality_explanation"], "materiality explanation", 8192)
    identifier(event["materiality_assessment_id"], "materiality assessment ID")
    references = unique_array(event["evidence_references"], "evidence references", 1, 64)
    for reference in references:
        item = exact_fields(reference, {"reference_id", "reference_kind", "content_hash"}, "evidence reference")
        identifier(item["reference_id"], "evidence reference ID")
        if item["reference_kind"] not in REFERENCE_KINDS:
            raise ContractRejected("unknown evidence reference kind")
        hash_value(item["content_hash"], "evidence content hash")
    verification = exact_fields(event["verification"], {
        "status", "method", "verification_record_ids", "policy_id", "policy_version",
    }, "verification")
    if verification["status"] != "verified" or verification["method"] not in METHODS:
        raise ContractRejected("invalid verification status or method")
    for record_id in unique_array(verification["verification_record_ids"], "verification references", 1, 64):
        identifier(record_id, "verification record ID")
    identifier(verification["policy_id"], "verification policy ID")
    policy_version(verification["policy_version"], "verification policy version")
    identifier(event["originating_principal_id"], "originating principal ID")
    identifier(event["created_by_principal_id"], "creator principal ID")
    identifier(event["capability_id"], "capability ID")
    if event["required_capability"] != "surface_verified_result":
        raise ContractRejected("wrong surfacing capability")
    timestamp(event["created_at"])
    for parent_id in unique_array(event["causal_parent_ids"], "causal references", 0, 64):
        identifier(parent_id, "causal parent ID")
    identifier(event["policy_id"], "policy ID"); policy_version(event["policy_version"], "policy version")
    if event["main_objective_incomplete"] is not True:
        raise ContractRejected("surfacing cannot complete the objective")
    actions = unique_array(event["available_steering_actions"], "available steering actions", 5, 5)
    if set(actions) != ACTIONS or any(not isinstance(item, str) for item in actions):
        raise ContractRejected("all steering actions must be available exactly once")
    hash_value(envelope["content_hash"], "envelope content hash")
    return event


def validate_event(data: bytes, context: ContractContext) -> dict[str, Any]:
    envelope = strict_json_loads(data)
    event = validate_event_structure(envelope)
    objective = context.objectives.get(event["objective_id"])
    run = context.runs.get(event["run_id"])
    if objective is None or not objective.active or not objective.permitted:
        raise ContractRejected("objective is not active and permitted")
    if run is None or not run.active or run.objective_id != objective.id:
        raise ContractRejected("run does not belong to active objective")
    if event["branch_id"] is not None:
        branch = context.branches.get(event["branch_id"])
        if branch is None or not branch.active or not branch.permitted or branch.objective_id != objective.id or branch.run_id != run.id:
            raise ContractRejected("branch does not belong to active run/objective")
    validate_policy(event["policy_id"], event["policy_version"], context)
    validate_capability(
        event["created_by_principal_id"], event["capability_id"], event["required_capability"], context,
        human_only=False,
    )
    if event["originating_principal_id"] not in context.principals:
        raise ContractRejected("unknown originating principal")
    identity = event["result_identity"]
    if identity["evidence_snapshot_hash"] != digest(event["evidence_references"]):
        raise ContractRejected("evidence snapshot hash mismatch")
    if identity["result_digest"] != result_digest_for(event):
        raise ContractRejected("result digest mismatch")
    evidence_ids: list[str] = []
    for reference in event["evidence_references"]:
        evidence = context.evidence.get(reference["reference_id"])
        if evidence is None or evidence.content_hash != reference["content_hash"]:
            raise ContractRejected("evidence identity or content hash mismatch")
        if evidence.objective_id != objective.id or evidence.run_id != run.id:
            raise ContractRejected("evidence belongs to another objective or run")
        if not evidence.eligible:
            raise ContractRejected("evidence lifecycle, rights, or applicability is ineligible")
        evidence_ids.append(evidence.id)
    verification = event["verification"]
    validate_policy(verification["policy_id"], verification["policy_version"], context)
    for record_id in verification["verification_record_ids"]:
        record = context.verification_records.get(record_id)
        if record is None or not record.independently_verified:
            raise ContractRejected("verification record is missing or not independent")
        if (
            record.result_digest != identity["result_digest"]
            or record.objective_id != objective.id
            or record.run_id != run.id
            or record.method != verification["method"]
            or record.policy_id != verification["policy_id"]
            or record.policy_version != verification["policy_version"]
            or set(record.evidence_ids) != set(evidence_ids)
        ):
            raise ContractRejected("verification record does not bind the exact result")
    materiality = context.materiality_records.get(event["materiality_assessment_id"])
    if materiality is None or (
        materiality.result_digest != identity["result_digest"]
        or materiality.objective_id != objective.id
        or materiality.policy_id != event["policy_id"]
        or materiality.policy_version != event["policy_version"]
    ):
        raise ContractRejected("materiality decision does not bind the exact result")
    for parent_id in event["causal_parent_ids"]:
        parent = context.causal_records.get(parent_id)
        if parent is None or parent.record_type not in ALLOWED_CAUSAL_TYPES:
            raise ContractRejected("dangling or disallowed causal reference")
        if parent.objective_id != objective.id or parent.run_id != run.id:
            raise ContractRejected("cross-run causal substitution")
    if envelope["content_hash"] != content_hash(envelope):
        raise ContractRejected("event content hash mismatch")
    return copy.deepcopy(envelope)


def validate_action_structure(envelope: dict[str, Any]) -> dict[str, Any]:
    exact_fields(envelope, {"schema_version", "record_type", "action", "content_hash"}, "action envelope")
    if envelope["schema_version"] != "adaivy.material-partial-result-steering-action.v1" or envelope["record_type"] != "material_partial_result_steering_action":
        raise ContractRejected("unsupported action schema or record type")
    action = exact_fields(envelope["action"], {
        "action_id", "event_type", "idempotency_key", "material_result_event_id", "objective_id", "run_id",
        "branch_id", "action", "principal_id", "capability_id", "required_capability", "created_at",
        "effective_actor_kind", "authority", "causal_predecessor_id", "target_objective_id",
        "target_branch_id", "policy_id", "policy_version", "sequence",
    }, "steering action")
    identifier(action["action_id"], "action ID")
    if action["event_type"] != "research.material_partial_result_steering_recorded":
        raise ContractRejected("wrong steering event type")
    bounded_string(action["idempotency_key"], "action idempotency key", 256)
    for field in ("material_result_event_id", "objective_id", "run_id", "principal_id", "capability_id", "causal_predecessor_id", "policy_id"):
        identifier(action[field], field)
    nullable_id(action["branch_id"], "branch ID")
    if action["action"] not in ACTIONS:
        raise ContractRejected("unknown steering action")
    if action["effective_actor_kind"] not in {item.value for item in ActorKind}:
        raise ContractRejected("unknown effective actor kind")
    if action["authority"] not in {item.value for item in Authority}:
        raise ContractRejected("unknown Phase 4A authority")
    if action["required_capability"] != "steer_research":
        raise ContractRejected("wrong steering capability")
    timestamp(action["created_at"])
    target_objective = nullable_id(action["target_objective_id"], "target objective ID")
    target_branch = nullable_id(action["target_branch_id"], "target branch ID")
    if action["action"] in {"investigate_result", "redirect_objective"}:
        if target_objective is None and target_branch is None:
            raise ContractRejected("steering target is required")
    elif target_objective is not None or target_branch is not None:
        raise ContractRejected("steering target is forbidden for action")
    policy_version(action["policy_version"], "policy version")
    strict_integer(action["sequence"], "action sequence", 1, MAX_RECORDS)
    hash_value(envelope["content_hash"], "action content hash")
    return action


def validate_lifecycle_structure(envelope: dict[str, Any]) -> dict[str, Any]:
    exact_fields(envelope, {"schema_version", "record_type", "lifecycle", "content_hash"}, "lifecycle envelope")
    if envelope["schema_version"] != "adaivy.material-partial-result-lifecycle.v1" or envelope["record_type"] != "material_partial_result_lifecycle":
        raise ContractRejected("unsupported lifecycle schema or record type")
    item = exact_fields(envelope["lifecycle"], {
        "lifecycle_id", "event_type", "idempotency_key", "material_result_event_id", "objective_id", "run_id",
        "change_kind", "derived_state", "principal_id", "capability_id", "required_capability",
        "effective_actor_kind", "authority", "affected_evidence_ids", "source_record_ids",
        "applicability_review_ids", "reason", "created_at",
        "causal_predecessor_id", "superseding_event_id", "policy_id", "policy_version", "sequence",
    }, "lifecycle record")
    for field in ("lifecycle_id", "material_result_event_id", "objective_id", "run_id", "principal_id", "capability_id", "causal_predecessor_id", "policy_id"):
        identifier(item[field], field)
    if item["event_type"] != "research.material_partial_result_lifecycle_recorded":
        raise ContractRejected("wrong lifecycle event type")
    bounded_string(item["idempotency_key"], "lifecycle idempotency key", 256)
    if item["change_kind"] not in CHANGE_KINDS or item["derived_state"] not in {"corrected", "superseded", "invalidated"}:
        raise ContractRejected("unknown lifecycle change or state")
    if item["effective_actor_kind"] not in {actor.value for actor in ActorKind}:
        raise ContractRejected("unknown effective actor kind")
    if item["authority"] not in {authority.value for authority in Authority}:
        raise ContractRejected("unknown Phase 4A authority")
    expected_state = "corrected" if item["change_kind"] == "correction" else "superseded" if item["change_kind"] == "supersession" else "invalidated"
    if item["derived_state"] != expected_state:
        raise ContractRejected("lifecycle change and state disagree")
    if item["required_capability"] != "review_result_lifecycle":
        raise ContractRejected("wrong lifecycle capability")
    for evidence_id in unique_array(item["affected_evidence_ids"], "affected evidence IDs", 1, 64):
        identifier(evidence_id, "affected evidence ID")
    for field in ("source_record_ids", "applicability_review_ids"):
        for record_id in unique_array(item[field], field, 0, 64):
            identifier(record_id, field)
    bounded_string(item["reason"], "lifecycle reason", 4096)
    timestamp(item["created_at"])
    superseding = nullable_id(item["superseding_event_id"], "superseding event ID")
    if (item["change_kind"] == "supersession") != (superseding is not None):
        raise ContractRejected("superseding event condition failed")
    policy_version(item["policy_version"], "policy version")
    strict_integer(item["sequence"], "lifecycle sequence", 1, MAX_RECORDS)
    hash_value(envelope["content_hash"], "lifecycle content hash")
    return item


class ContractStore:
    """Test-only append-only projection model for a future production gate."""

    def __init__(self, context: ContractContext) -> None:
        self.context = context
        self.events: dict[str, dict[str, Any]] = {}
        self.event_keys: dict[str, str] = {}
        self.actions: dict[str, dict[str, Any]] = {}
        self.action_keys: dict[str, str] = {}
        self.actions_by_event: dict[str, list[str]] = {}
        self.lifecycle: dict[str, dict[str, Any]] = {}
        self.lifecycle_keys: dict[str, str] = {}
        self.lifecycle_by_event: dict[str, list[str]] = {}

    @staticmethod
    def _deduplicate(
        record_id: str,
        key: str,
        accepted: dict[str, Any],
        records: dict[str, dict[str, Any]],
        keys: dict[str, str],
    ) -> dict[str, Any] | None:
        existing_id = keys.get(key)
        existing = records.get(record_id)
        if existing_id is not None and existing_id != record_id:
            raise ContractRejected("idempotency key reused with another identity")
        if existing is not None:
            if existing != accepted:
                raise ContractRejected("record identity reused with different content")
            return copy.deepcopy(existing)
        return None

    def accept_event(self, data: bytes) -> dict[str, Any]:
        accepted = validate_event(data, self.context)
        event = accepted["event"]
        duplicate = self._deduplicate(event["event_id"], event["semantic_idempotency_key"], accepted, self.events, self.event_keys)
        if duplicate is not None:
            return duplicate
        self.events[event["event_id"]] = copy.deepcopy(accepted)
        self.event_keys[event["semantic_idempotency_key"]] = event["event_id"]
        self.actions_by_event[event["event_id"]] = []
        self.lifecycle_by_event[event["event_id"]] = []
        return copy.deepcopy(accepted)

    def current_state(self, event_id: str) -> str:
        history = self.lifecycle_by_event.get(event_id, [])
        if not history:
            return "valid"
        return self.lifecycle[history[-1]]["lifecycle"]["derived_state"]

    def accept_action(self, data: bytes) -> dict[str, Any]:
        accepted = strict_json_loads(data)
        action = validate_action_structure(accepted)
        if accepted["content_hash"] != content_hash(accepted):
            raise ContractRejected("action content hash mismatch")
        duplicate = self._deduplicate(action["action_id"], action["idempotency_key"], accepted, self.actions, self.action_keys)
        if duplicate is not None:
            return duplicate
        event_envelope = self.events.get(action["material_result_event_id"])
        if event_envelope is None:
            raise ContractRejected("steering targets an unknown material-result event")
        event = event_envelope["event"]
        if self.current_state(event["event_id"]) != "valid":
            raise ContractRejected("invalidated material result cannot support steering")
        if (action["objective_id"], action["run_id"], action["branch_id"]) != (event["objective_id"], event["run_id"], event["branch_id"]):
            raise ContractRejected("steering substitutes another objective, run, or branch")
        validate_policy(action["policy_id"], action["policy_version"], self.context)
        principal = validate_capability(action["principal_id"], action["capability_id"], action["required_capability"], self.context, human_only=True)
        if action["effective_actor_kind"] != principal.actor_kind.value or action["authority"] != principal.authority.value:
            raise ContractRejected("recorded actor kind or authority differs from trusted principal")
        history = self.actions_by_event[event["event_id"]]
        expected_predecessor = event["event_id"] if not history else history[-1]
        if action["causal_predecessor_id"] != expected_predecessor or action["sequence"] != len(history) + 1:
            raise ContractRejected("steering history is dangling or reordered")
        target_objective = action["target_objective_id"]
        target_branch = action["target_branch_id"]
        if target_objective is not None:
            objective = self.context.objectives.get(target_objective)
            if objective is None or not objective.active or not objective.permitted:
                raise ContractRejected("unresolved or prohibited target objective")
        if target_branch is not None:
            branch = self.context.branches.get(target_branch)
            if branch is None or not branch.active or not branch.permitted:
                raise ContractRejected("unresolved or prohibited target branch")
            if target_objective is not None and branch.objective_id != target_objective:
                raise ContractRejected("target branch belongs to another objective")
        self.actions[action["action_id"]] = copy.deepcopy(accepted)
        self.action_keys[action["idempotency_key"]] = action["action_id"]
        history.append(action["action_id"])
        return copy.deepcopy(accepted)

    def accept_lifecycle(self, data: bytes) -> dict[str, Any]:
        accepted = strict_json_loads(data)
        item = validate_lifecycle_structure(accepted)
        if accepted["content_hash"] != content_hash(accepted):
            raise ContractRejected("lifecycle content hash mismatch")
        duplicate = self._deduplicate(item["lifecycle_id"], item["idempotency_key"], accepted, self.lifecycle, self.lifecycle_keys)
        if duplicate is not None:
            return duplicate
        event_envelope = self.events.get(item["material_result_event_id"])
        if event_envelope is None:
            raise ContractRejected("lifecycle targets an unknown material-result event")
        event = event_envelope["event"]
        if (item["objective_id"], item["run_id"]) != (event["objective_id"], event["run_id"]):
            raise ContractRejected("lifecycle substitutes another objective or run")
        validate_policy(item["policy_id"], item["policy_version"], self.context)
        principal = validate_capability(item["principal_id"], item["capability_id"], item["required_capability"], self.context, human_only=True)
        if item["effective_actor_kind"] != principal.actor_kind.value or item["authority"] != principal.authority.value:
            raise ContractRejected("recorded actor kind or authority differs from trusted principal")
        event_evidence = {reference["reference_id"] for reference in event["evidence_references"]}
        if not set(item["affected_evidence_ids"]).issubset(event_evidence):
            raise ContractRejected("lifecycle references evidence outside the result")
        for evidence_id in item["affected_evidence_ids"]:
            evidence = self.context.evidence.get(evidence_id)
            if evidence is None:
                raise ContractRejected("lifecycle evidence is unknown")
            if item["change_kind"] == "correction" and evidence.lifecycle_state != "corrected":
                raise ContractRejected("correction is not reflected in evidence state")
            if item["change_kind"] == "revocation" and evidence.lifecycle_state != "revoked":
                raise ContractRejected("revocation is not reflected in evidence state")
            if item["change_kind"] == "deletion" and evidence.lifecycle_state != "deleted":
                raise ContractRejected("deletion is not reflected in evidence state")
            if item["change_kind"] == "rights_applicability_changed" and evidence.rights_state == "allowed":
                raise ContractRejected("rights applicability did not change")
            if item["change_kind"] == "applicability_review_changed" and evidence.applicability_state not in {"rejected", "unresolved"}:
                raise ContractRejected("applicability review did not become ineligible")
        history = self.lifecycle_by_event[event["event_id"]]
        expected_predecessor = event["event_id"] if not history else history[-1]
        if item["causal_predecessor_id"] != expected_predecessor or item["sequence"] != len(history) + 1:
            raise ContractRejected("lifecycle history is dangling or reordered")
        if item["change_kind"] == "supersession" and item["superseding_event_id"] not in self.events:
            raise ContractRejected("superseding event is unresolved")
        self.lifecycle[item["lifecycle_id"]] = copy.deepcopy(accepted)
        self.lifecycle_keys[item["idempotency_key"]] = item["lifecycle_id"]
        history.append(item["lifecycle_id"])
        return copy.deepcopy(accepted)

    def project(self, event_id: str) -> dict[str, Any]:
        if event_id not in self.events:
            raise ContractRejected("unknown event")
        return {
            "event": copy.deepcopy(self.events[event_id]),
            "steering_actions": [copy.deepcopy(self.actions[item]) for item in self.actions_by_event[event_id]],
            "lifecycle_records": [copy.deepcopy(self.lifecycle[item]) for item in self.lifecycle_by_event[event_id]],
            "current_state": self.current_state(event_id),
        }


def base_event(*, classification: str = "refutes") -> dict[str, Any]:
    return seal({
        "schema_version": "adaivy.material-partial-result-event.v1",
        "record_type": "material_partial_result_event",
        "event": _unsealed_base_event(classification),
        "content_hash": "sha256:" + "0" * 64,
    })


def steering_action(
    action: str = "acknowledge",
    *,
    suffix: str = "ack",
    sequence: int = 1,
    predecessor: str = "material-result.counterexample-1",
    principal_id: str = "actor.human.owner",
    capability_id: str = "capability.steer-research",
    target_objective_id: str | None = None,
    target_branch_id: str | None = None,
) -> dict[str, Any]:
    return seal({
        "schema_version": "adaivy.material-partial-result-steering-action.v1",
        "record_type": "material_partial_result_steering_action",
        "action": {
            "action_id": f"steering.{suffix}",
            "event_type": "research.material_partial_result_steering_recorded",
            "idempotency_key": f"steering:{suffix}",
            "material_result_event_id": "material-result.counterexample-1",
            "objective_id": "problem.active",
            "run_id": "run.active",
            "branch_id": "branch.active",
            "action": action,
            "principal_id": principal_id,
            "effective_actor_kind": "human",
            "authority": "human_final",
            "capability_id": capability_id,
            "required_capability": "steer_research",
            "created_at": "2026-08-20T12:01:00Z",
            "causal_predecessor_id": predecessor,
            "target_objective_id": target_objective_id,
            "target_branch_id": target_branch_id,
            "policy_id": "policy.material-result",
            "policy_version": "material-result-policy-v1",
            "sequence": sequence,
        },
        "content_hash": "sha256:" + "0" * 64,
    })


def lifecycle_record(
    change_kind: str,
    *,
    suffix: str,
    derived_state: str,
    source_record_ids: list[str] | None = None,
    applicability_review_ids: list[str] | None = None,
) -> dict[str, Any]:
    return seal({
        "schema_version": "adaivy.material-partial-result-lifecycle.v1",
        "record_type": "material_partial_result_lifecycle",
        "lifecycle": {
            "lifecycle_id": f"result-lifecycle.{suffix}",
            "event_type": "research.material_partial_result_lifecycle_recorded",
            "idempotency_key": f"result-lifecycle:{suffix}",
            "material_result_event_id": "material-result.counterexample-1",
            "objective_id": "problem.active",
            "run_id": "run.active",
            "change_kind": change_kind,
            "derived_state": derived_state,
            "principal_id": "actor.human.owner",
            "effective_actor_kind": "human",
            "authority": "human_final",
            "capability_id": "capability.review-lifecycle",
            "required_capability": "review_result_lifecycle",
            "affected_evidence_ids": ["evidence.counterexample"],
            "source_record_ids": source_record_ids or ["source.lifecycle.active"],
            "applicability_review_ids": applicability_review_ids or ["applicability.checked"],
            "reason": f"The dependent evidence changed through {change_kind}.",
            "created_at": "2026-08-20T12:02:00Z",
            "causal_predecessor_id": "material-result.counterexample-1",
            "superseding_event_id": None,
            "policy_id": "policy.material-result",
            "policy_version": "material-result-policy-v1",
            "sequence": 1,
        },
        "content_hash": "sha256:" + "0" * 64,
    })


def encoded(value: dict[str, Any]) -> bytes:
    return canonical_bytes(seal(value))


class MaterialPartialResultV1ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ContractContext()

    def assert_event_rejected(self, value: dict[str, Any]) -> None:
        with self.assertRaises(ContractRejected):
            validate_event(encoded(value), self.context)

    def test_verified_result_and_all_five_classifications(self) -> None:
        for classification in sorted(CLASSIFICATIONS):
            accepted = validate_event(canonical_bytes(base_event(classification=classification)), self.context)
            self.assertEqual(accepted["event"]["classification"], classification)
            self.assertTrue(accepted["event"]["main_objective_incomplete"])

    def test_steering_appends_after_immutable_event_and_projects_deterministically(self) -> None:
        store = ContractStore(self.context)
        original = store.accept_event(canonical_bytes(base_event()))
        action = steering_action()
        first = store.accept_action(canonical_bytes(action))
        second = store.accept_action(canonical_bytes(action))
        projection = store.project(original["event"]["event_id"])
        self.assertEqual(first, second)
        self.assertEqual(len(store.events), 1)
        self.assertEqual(len(store.actions), 1)
        self.assertEqual(projection["event"], original)
        self.assertNotIn("steering_records", projection["event"])
        self.assertEqual(projection["steering_actions"], [action])

    def test_event_and_action_identity_conflicts_fail_closed(self) -> None:
        store = ContractStore(self.context)
        event = base_event()
        original = store.accept_event(canonical_bytes(event))
        self.assertEqual(store.accept_event(canonical_bytes(event)), original)
        changed_event = base_event()
        changed_event["event"]["created_at"] = "2026-08-20T12:00:01Z"
        with self.assertRaisesRegex(ContractRejected, "different content"):
            store.accept_event(encoded(changed_event))
        reused_event_key = base_event()
        reused_event_key["event"]["event_id"] = "material-result.other"
        with self.assertRaisesRegex(ContractRejected, "idempotency key"):
            store.accept_event(encoded(reused_event_key))
        store.accept_action(canonical_bytes(steering_action()))
        changed = steering_action()
        changed["action"]["created_at"] = "2026-08-20T12:01:01Z"
        with self.assertRaisesRegex(ContractRejected, "different content"):
            store.accept_action(encoded(changed))
        reused_key = steering_action(suffix="other")
        reused_key["action"]["idempotency_key"] = "steering:ack"
        with self.assertRaisesRegex(ContractRejected, "idempotency key"):
            store.accept_action(encoded(reused_key))

    def test_trusted_actor_kind_prevents_model_or_system_human_relabeling(self) -> None:
        for principal, capability, actor_kind, authority in (
            ("actor.model.explorer", "capability.model-steer", "model", "proposal"),
            ("actor.system.orchestrator", "capability.system-steer", "system", "deterministic_policy"),
        ):
            context = copy.deepcopy(self.context)
            context.capabilities[capability] = CapabilityRecord(capability, principal, "steer_research")
            store = ContractStore(context)
            store.accept_event(canonical_bytes(base_event()))
            attempted = steering_action(principal_id=principal, capability_id=capability)
            attempted["action"]["effective_actor_kind"] = actor_kind
            attempted["action"]["authority"] = authority
            with self.subTest(principal=principal), self.assertRaisesRegex(ContractRejected, "human-final"):
                store.accept_action(encoded(attempted))
        claimed_kind = steering_action()
        claimed_kind["action"]["effective_actor_kind"] = "model"
        store = ContractStore(self.context)
        store.accept_event(canonical_bytes(base_event()))
        with self.assertRaisesRegex(ContractRejected, "trusted principal"):
            store.accept_action(encoded(claimed_kind))
        claimed_authority = steering_action()
        claimed_authority["action"]["authority"] = "proposal"
        with self.assertRaisesRegex(ContractRejected, "trusted principal"):
            store.accept_action(encoded(claimed_authority))

    def test_exact_result_materiality_verification_evidence_and_policy_binding(self) -> None:
        mutations: list[tuple[str, Callable[[dict[str, Any], ContractContext], None]]] = []

        def different_statement(value: dict[str, Any], _: ContractContext) -> None:
            value["event"]["result_identity"]["statement"] = "A different statement."
            value["event"]["result_identity"]["result_digest"] = result_digest_for(value["event"])

        def wrong_materiality(_: dict[str, Any], context: ContractContext) -> None:
            item = context.materiality_records["materiality.user-impact"]
            context.materiality_records[item.id] = replace(item, objective_id="problem.redirected")

        def wrong_verification(_: dict[str, Any], context: ContractContext) -> None:
            item = context.verification_records["verification.exact-counterexample"]
            context.verification_records[item.id] = replace(item, result_digest="sha256:" + "9" * 64)

        def wrong_evidence_hash(value: dict[str, Any], _: ContractContext) -> None:
            value["event"]["evidence_references"][0]["content_hash"] = "sha256:" + "8" * 64
            value["event"]["result_identity"]["evidence_snapshot_hash"] = digest(value["event"]["evidence_references"])
            value["event"]["result_identity"]["result_digest"] = result_digest_for(value["event"])

        def dangling_cause(value: dict[str, Any], _: ContractContext) -> None:
            value["event"]["causal_parent_ids"] = ["verification.missing"]

        def cross_run_cause(_: dict[str, Any], context: ContractContext) -> None:
            item = context.causal_records["verification.exact-counterexample"]
            context.causal_records[item.id] = replace(item, run_id="run.other")

        def unknown_policy(value: dict[str, Any], _: ContractContext) -> None:
            value["event"]["policy_id"] = "policy.unknown"

        mutations.extend([
            ("different_statement", different_statement), ("wrong_materiality", wrong_materiality),
            ("wrong_verification", wrong_verification), ("wrong_evidence_hash", wrong_evidence_hash),
            ("dangling_cause", dangling_cause), ("cross_run_cause", cross_run_cause),
            ("unknown_policy", unknown_policy),
        ])
        for name, mutate in mutations:
            value = base_event(); context = copy.deepcopy(self.context); mutate(value, context)
            with self.subTest(name=name), self.assertRaises(ContractRejected):
                validate_event(encoded(value), context)

    def test_ineligible_evidence_states_fail_closed(self) -> None:
        contexts = (
            self.context.with_evidence(lifecycle_state="deleted"),
            self.context.with_evidence(lifecycle_state="suppressed"),
            self.context.with_evidence(lifecycle_state="revoked"),
            self.context.with_evidence(lifecycle_state="takedown"),
            self.context.with_evidence(lifecycle_state="withdrawn"),
            self.context.with_evidence(rights_state="prohibited"),
            self.context.with_evidence(rights_state="revoked"),
            self.context.with_evidence(rights_state="unresolved"),
            self.context.with_evidence(applicability_state="rejected"),
            self.context.with_evidence(applicability_state="unresolved"),
        )
        for context in contexts:
            with self.subTest(evidence=context.evidence["evidence.counterexample"]), self.assertRaisesRegex(ContractRejected, "ineligible"):
                validate_event(canonical_bytes(base_event()), context)

    def test_unresolved_event_and_redirect_targets_fail_closed(self) -> None:
        store = ContractStore(self.context)
        with self.assertRaisesRegex(ContractRejected, "unknown material-result"):
            store.accept_action(canonical_bytes(steering_action()))
        store.accept_event(canonical_bytes(base_event()))
        redirect = steering_action("redirect_objective", target_objective_id="problem.missing")
        with self.assertRaisesRegex(ContractRejected, "target objective"):
            store.accept_action(canonical_bytes(redirect))
        missing_branch = steering_action("investigate_result", suffix="missing", target_branch_id="branch.missing")
        with self.assertRaisesRegex(ContractRejected, "target branch"):
            store.accept_action(canonical_bytes(missing_branch))
        inconsistent = steering_action(
            "redirect_objective", suffix="inconsistent",
            target_objective_id="problem.active", target_branch_id="branch.redirected",
        )
        with self.assertRaisesRegex(ContractRejected, "another objective"):
            store.accept_action(canonical_bytes(inconsistent))

    def test_event_schema_constraint_mutations_fail_closed(self) -> None:
        mutations: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
            ("missing_required", lambda v: v["event"].pop("event_id")),
            ("unknown_envelope", lambda v: v.__setitem__("unknown", 1)),
            ("unknown_event", lambda v: v["event"].__setitem__("unknown", 1)),
            ("unknown_identity", lambda v: v["event"]["result_identity"].__setitem__("unknown", 1)),
            ("unknown_reference", lambda v: v["event"]["evidence_references"][0].__setitem__("unknown", 1)),
            ("unknown_verification", lambda v: v["event"]["verification"].__setitem__("unknown", 1)),
            ("empty_event_id", lambda v: v["event"].__setitem__("event_id", "")),
            ("empty_key", lambda v: v["event"].__setitem__("semantic_idempotency_key", "")),
            ("malformed_hash", lambda v: v["event"]["evidence_references"][0].__setitem__("content_hash", "bad")),
            ("malformed_policy", lambda v: v["event"].__setitem__("policy_id", "bad id")),
            ("invalid_timestamp", lambda v: v["event"].__setitem__("created_at", "2026-99-99T12:00:00Z")),
            ("timezone_less", lambda v: v["event"].__setitem__("created_at", "2026-08-20T12:00:00")),
            ("duplicate_evidence", lambda v: v["event"]["evidence_references"].append(copy.deepcopy(v["event"]["evidence_references"][0]))),
            ("duplicate_verification", lambda v: v["event"]["verification"]["verification_record_ids"].append("verification.exact-counterexample")),
            ("duplicate_causal", lambda v: v["event"]["causal_parent_ids"].append("verification.exact-counterexample")),
        ]
        for name, mutate in mutations:
            value = base_event(); mutate(value)
            with self.subTest(name=name), self.assertRaises(ContractRejected):
                validate_event(encoded(value), self.context)

    def test_action_and_lifecycle_schema_constraints_fail_closed(self) -> None:
        action_mutations: list[Callable[[dict[str, Any]], None]] = [
            lambda v: v["action"].__setitem__("action_id", ""),
            lambda v: v["action"].__setitem__("idempotency_key", ""),
            lambda v: v["action"].__setitem__("created_at", "2026-02-30T12:01:00Z"),
            lambda v: v["action"].__setitem__("created_at", "2026-08-20T12:01:00"),
            lambda v: v["action"].__setitem__("sequence", True),
            lambda v: v["action"].__setitem__("sequence", 257),
            lambda v: v["action"].__setitem__("unknown", 1),
            lambda v: v.__setitem__("unknown", 1),
        ]
        for index, mutate in enumerate(action_mutations):
            value = steering_action(); mutate(value)
            with self.subTest(kind="action", mutation=index), self.assertRaises(ContractRejected):
                validate_action_structure(seal(value))
        missing_target = steering_action("redirect_objective")
        with self.assertRaisesRegex(ContractRejected, "target is required"):
            validate_action_structure(missing_target)

        lifecycle_mutations: list[Callable[[dict[str, Any]], None]] = [
            lambda v: v["lifecycle"].__setitem__("lifecycle_id", ""),
            lambda v: v["lifecycle"].__setitem__("idempotency_key", ""),
            lambda v: v["lifecycle"].__setitem__("created_at", "2026-02-30T12:02:00Z"),
            lambda v: v["lifecycle"].__setitem__("sequence", False),
            lambda v: v["lifecycle"]["affected_evidence_ids"].append("evidence.counterexample"),
            lambda v: v["lifecycle"].__setitem__("unknown", 1),
        ]
        for index, mutate in enumerate(lifecycle_mutations):
            value = lifecycle_record("deletion", suffix="delete", derived_state="invalidated"); mutate(value)
            with self.subTest(kind="lifecycle", mutation=index), self.assertRaises(ContractRejected):
                validate_lifecycle_structure(seal(value))

    def test_correction_deletion_revocation_and_applicability_reversal_project_append_only(self) -> None:
        cases = (
            ("correction", "corrected", {"lifecycle_state": "corrected"}),
            ("deletion", "invalidated", {"lifecycle_state": "deleted"}),
            ("revocation", "invalidated", {"lifecycle_state": "revoked"}),
            ("applicability_review_changed", "invalidated", {"applicability_state": "rejected"}),
        )
        for change_kind, state, evidence_change in cases:
            context = self.context.with_evidence(**evidence_change)
            store = ContractStore(context)
            original = store.accept_event(canonical_bytes(base_event())) if context.evidence["evidence.counterexample"].eligible else None
            if original is None:
                # Existing events were accepted before the later evidence transition.
                store = ContractStore(self.context)
                original = store.accept_event(canonical_bytes(base_event()))
                store.context = context
            record = lifecycle_record(change_kind, suffix=change_kind, derived_state=state)
            accepted = store.accept_lifecycle(canonical_bytes(record))
            projection = store.project(original["event"]["event_id"])
            self.assertEqual(projection["event"], original)
            self.assertEqual(projection["lifecycle_records"], [accepted])
            self.assertEqual(projection["current_state"], state)
            with self.assertRaisesRegex(ContractRejected, "cannot support steering"):
                store.accept_action(canonical_bytes(steering_action()))

    def test_raw_boundary_duplicate_keys_nonfinite_and_oversize_fail_closed(self) -> None:
        for raw in (
            b"{",
            b'{"schema_version":"a","schema_version":"b"}',
            b'{"value":NaN}',
            b"\xff",
            b" " * (MAX_ENVELOPE_BYTES + 1),
        ):
            with self.subTest(raw=raw[:20]), self.assertRaises(ContractRejected):
                validate_event(raw, self.context)

    def test_authoritative_phase4_gate_and_prior_contracts_remain_byte_identical(self) -> None:
        expected = {
            "docs/phase-4/ENTRY_GATE_REPORT.md": "a41eac43cccdabfd6c6910931317cb29c1d8304022c0422f69a07f0f002f8c33",
            "reports/phase-4-entry-gate/entry-gate.json": "bafcdd86c6057ddf39e453d0923c048c7cf1c5b33337723c402fae90badec928",
            "docs/adrs/0017-phase4a-local-rights-applicability-review.md": "78719c5723dd13a4f401c477b8dcc8ecce368ff83faea843acb07ae22761e659",
            "docs/adrs/0018-phase4-gate-security-reproducibility-controls.md": "b5321b3846029bfbd203adcd73e18e77640820ee6fd15cbc95c1546801da53f4",
            "docs/phase-4/SECURITY_CONTROL_INVENTORY.md": "91e33b025dc65414d51735bfaf978a36eb26c064f0bc81470930f47d2f55001b",
            "docs/phase-4/ACCEPTANCE_THRESHOLD_INVENTORY.md": "1d28107aa339caff20bbd706a41dc267bea70a79d8f05031825e9ded387a6283",
            "fixtures/phase4-gate/manifest.json": "aff0338510b876df4c727b2f048272e1f28af8bbad6a448d90f878494c3623e7",
            "schemas/phase4-gate-fixture-v1.schema.json": "ad52d76139362380d89bea28c2399cd703cc2ab7dab298fa175b40b086537858",
        }
        for relative, expected_hash in expected.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected_hash)


HAS_ORACLE = importlib.util.find_spec("jsonschema") is not None


@unittest.skipUnless(HAS_ORACLE, "requires owner-approved isolated Phase 4 gate validator environment")
class MaterialPartialResultSchemaOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from jsonschema import Draft202012Validator

        cls.validators = {}
        for path in SCHEMA_PATHS:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            cls.validators[path.name] = Draft202012Validator(schema)

    def assert_oracle_accepts(self, schema_name: str, value: dict[str, Any]) -> None:
        self.assertEqual(list(self.validators[schema_name].iter_errors(value)), [])

    def assert_oracle_rejects(self, schema_name: str, value: dict[str, Any]) -> None:
        self.assertTrue(list(self.validators[schema_name].iter_errors(value)))

    def test_three_valid_envelopes_and_schema_drafts(self) -> None:
        self.assert_oracle_accepts("material-partial-result-event-v1.schema.json", base_event())
        self.assert_oracle_accepts("material-partial-result-steering-action-v1.schema.json", steering_action())
        self.assert_oracle_accepts(
            "material-partial-result-steering-action-v1.schema.json",
            steering_action("redirect_objective", suffix="redirect", target_objective_id="problem.redirected"),
        )
        self.assert_oracle_accepts(
            "material-partial-result-lifecycle-v1.schema.json",
            lifecycle_record("deletion", suffix="delete", derived_state="invalidated"),
        )
        supersession = lifecycle_record("supersession", suffix="supersede", derived_state="superseded")
        supersession["lifecycle"]["superseding_event_id"] = "material-result.replacement"
        self.assert_oracle_accepts("material-partial-result-lifecycle-v1.schema.json", seal(supersession))

    def test_independent_constraint_class_mutations_are_rejected(self) -> None:
        event_mutations: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
            ("required", lambda v: v["event"].pop("event_id")),
            ("envelope_closure", lambda v: v.__setitem__("unknown", 1)),
            ("event_closure", lambda v: v["event"].__setitem__("unknown", 1)),
            ("identity_closure", lambda v: v["event"]["result_identity"].__setitem__("unknown", 1)),
            ("reference_closure", lambda v: v["event"]["evidence_references"][0].__setitem__("unknown", 1)),
            ("verification_closure", lambda v: v["event"]["verification"].__setitem__("unknown", 1)),
            ("schema_const", lambda v: v.__setitem__("schema_version", "adaivy.material-partial-result-event.v2")),
            ("record_const", lambda v: v.__setitem__("record_type", "other")),
            ("event_const", lambda v: v["event"].__setitem__("event_type", "other")),
            ("id_pattern_empty", lambda v: v["event"].__setitem__("event_id", "")),
            ("id_pattern_character", lambda v: v["event"].__setitem__("event_id", "bad id")),
            ("id_pattern_length", lambda v: v["event"].__setitem__("event_id", "e" * 257)),
            ("key_min_length", lambda v: v["event"].__setitem__("semantic_idempotency_key", "")),
            ("key_max_length", lambda v: v["event"].__setitem__("semantic_idempotency_key", "k" * 257)),
            ("classification_enum", lambda v: v["event"].__setitem__("classification", "ordinary_progress")),
            ("statement_min_length", lambda v: v["event"]["result_identity"].__setitem__("statement", "")),
            ("statement_max_length", lambda v: v["event"]["result_identity"].__setitem__("statement", "s" * 4097)),
            ("domain_max_length", lambda v: v["event"]["result_identity"].__setitem__("domain", "d" * 257)),
            ("hash_pattern", lambda v: v["event"]["result_identity"].__setitem__("result_digest", "sha256:BAD")),
            ("version_pattern", lambda v: v["event"]["result_identity"].__setitem__("canonicalization_version", "bad version")),
            ("reference_enum", lambda v: v["event"]["evidence_references"][0].__setitem__("reference_kind", "claim")),
            ("verification_const", lambda v: v["event"]["verification"].__setitem__("status", "proposed")),
            ("verification_enum", lambda v: v["event"]["verification"].__setitem__("method", "model_agreement")),
            ("timestamp_offset_pattern", lambda v: v["event"].__setitem__("created_at", "2026-08-20T12:00:00")),
            ("timestamp_max_length", lambda v: v["event"].__setitem__("created_at", "2" * 65)),
            ("evidence_min_items", lambda v: v["event"].__setitem__("evidence_references", [])),
            ("evidence_max_items", lambda v: v["event"].__setitem__("evidence_references", [
                {"reference_id": f"evidence.e{i}", "reference_kind": "evidence", "content_hash": "sha256:" + f"{i:064x}"}
                for i in range(65)
            ])),
            ("evidence_unique", lambda v: v["event"]["evidence_references"].append(copy.deepcopy(v["event"]["evidence_references"][0]))),
            ("verification_min_items", lambda v: v["event"]["verification"].__setitem__("verification_record_ids", [])),
            ("verification_max_items", lambda v: v["event"]["verification"].__setitem__("verification_record_ids", [f"verification.v{i}" for i in range(65)])),
            ("verification_unique", lambda v: v["event"]["verification"]["verification_record_ids"].append("verification.exact-counterexample")),
            ("causal_items", lambda v: v["event"].__setitem__("causal_parent_ids", [1])),
            ("causal_max_items", lambda v: v["event"].__setitem__("causal_parent_ids", [f"cause.c{i}" for i in range(65)])),
            ("causal_unique", lambda v: v["event"]["causal_parent_ids"].append("verification.exact-counterexample")),
            ("action_min_items", lambda v: v["event"]["available_steering_actions"].pop()),
            ("action_unique", lambda v: v["event"].__setitem__("available_steering_actions", ["dismiss"] * 5)),
            ("action_item_enum", lambda v: v["event"]["available_steering_actions"].__setitem__(0, "other")),
            ("one_of", lambda v: v["event"].__setitem__("branch_id", 1)),
            ("incomplete_const", lambda v: v["event"].__setitem__("main_objective_incomplete", False)),
            ("capability_const", lambda v: v["event"].__setitem__("required_capability", "other")),
            ("content_hash_pattern", lambda v: v.__setitem__("content_hash", "bad")),
        ]
        for name, mutate in event_mutations:
            value = base_event(); mutate(value)
            with self.subTest(schema="event", mutation=name):
                self.assert_oracle_rejects("material-partial-result-event-v1.schema.json", value)
        action_mutations: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
            ("required", lambda v: v["action"].pop("action_id")),
            ("envelope_closure", lambda v: v.__setitem__("unknown", 1)),
            ("action_closure", lambda v: v["action"].__setitem__("unknown", 1)),
            ("id_pattern", lambda v: v["action"].__setitem__("action_id", "")),
            ("key_min_length", lambda v: v["action"].__setitem__("idempotency_key", "")),
            ("key_max_length", lambda v: v["action"].__setitem__("idempotency_key", "k" * 257)),
            ("action_enum", lambda v: v["action"].__setitem__("action", "other")),
            ("actor_kind_enum", lambda v: v["action"].__setitem__("effective_actor_kind", "other")),
            ("authority_enum", lambda v: v["action"].__setitem__("authority", "other")),
            ("timestamp_pattern", lambda v: v["action"].__setitem__("created_at", "2026-08-20T12:01:00")),
            ("policy_pattern", lambda v: v["action"].__setitem__("policy_version", "bad version")),
            ("one_of_branch", lambda v: v["action"].__setitem__("branch_id", 1)),
            ("one_of_target", lambda v: v["action"].__setitem__("target_branch_id", 1)),
            ("integer_type", lambda v: v["action"].__setitem__("sequence", True)),
            ("integer_minimum", lambda v: v["action"].__setitem__("sequence", 0)),
            ("integer_maximum", lambda v: v["action"].__setitem__("sequence", 257)),
            ("else", lambda v: v["action"].__setitem__("target_objective_id", "problem.active")),
            ("content_hash_pattern", lambda v: v.__setitem__("content_hash", "bad")),
        ]
        for name, mutate in action_mutations:
            value = steering_action(); mutate(value)
            with self.subTest(schema="action", mutation=name):
                self.assert_oracle_rejects("material-partial-result-steering-action-v1.schema.json", value)
        missing_action_target = steering_action("redirect_objective", suffix="missing-target")
        self.assert_oracle_rejects("material-partial-result-steering-action-v1.schema.json", missing_action_target)

        lifecycle_mutations: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
            ("required", lambda v: v["lifecycle"].pop("lifecycle_id")),
            ("envelope_closure", lambda v: v.__setitem__("unknown", 1)),
            ("lifecycle_closure", lambda v: v["lifecycle"].__setitem__("unknown", 1)),
            ("id_pattern", lambda v: v["lifecycle"].__setitem__("lifecycle_id", "")),
            ("key_min_length", lambda v: v["lifecycle"].__setitem__("idempotency_key", "")),
            ("change_enum", lambda v: v["lifecycle"].__setitem__("change_kind", "other")),
            ("state_enum", lambda v: v["lifecycle"].__setitem__("derived_state", "valid")),
            ("actor_kind_enum", lambda v: v["lifecycle"].__setitem__("effective_actor_kind", "other")),
            ("authority_enum", lambda v: v["lifecycle"].__setitem__("authority", "other")),
            ("affected_min_items", lambda v: v["lifecycle"].__setitem__("affected_evidence_ids", [])),
            ("affected_max_items", lambda v: v["lifecycle"].__setitem__("affected_evidence_ids", [f"evidence.e{i}" for i in range(65)])),
            ("affected_unique", lambda v: v["lifecycle"]["affected_evidence_ids"].append("evidence.counterexample")),
            ("source_items", lambda v: v["lifecycle"].__setitem__("source_record_ids", [1])),
            ("source_unique", lambda v: v["lifecycle"]["source_record_ids"].append("source.lifecycle.active")),
            ("applicability_unique", lambda v: v["lifecycle"]["applicability_review_ids"].append("applicability.checked")),
            ("reason_min_length", lambda v: v["lifecycle"].__setitem__("reason", "")),
            ("reason_max_length", lambda v: v["lifecycle"].__setitem__("reason", "r" * 4097)),
            ("timestamp_pattern", lambda v: v["lifecycle"].__setitem__("created_at", "2026-08-20T12:02:00")),
            ("superseding_one_of", lambda v: v["lifecycle"].__setitem__("superseding_event_id", 1)),
            ("integer_type", lambda v: v["lifecycle"].__setitem__("sequence", False)),
            ("integer_minimum", lambda v: v["lifecycle"].__setitem__("sequence", 0)),
            ("content_hash_pattern", lambda v: v.__setitem__("content_hash", "bad")),
        ]
        for name, mutate in lifecycle_mutations:
            value = lifecycle_record("deletion", suffix="delete", derived_state="invalidated"); mutate(value)
            with self.subTest(schema="lifecycle", mutation=name):
                self.assert_oracle_rejects("material-partial-result-lifecycle-v1.schema.json", value)
        conditionals = (
            lifecycle_record("supersession", suffix="supersede", derived_state="superseded"),
            lifecycle_record("correction", suffix="correct", derived_state="invalidated"),
            lifecycle_record("deletion", suffix="delete-wrong-state", derived_state="corrected"),
        )
        non_supersession_target = lifecycle_record("deletion", suffix="delete-target", derived_state="invalidated")
        non_supersession_target["lifecycle"]["superseding_event_id"] = "material-result.other"
        for value in (*conditionals, non_supersession_target):
            self.assert_oracle_rejects("material-partial-result-lifecycle-v1.schema.json", value)

    def test_validation_keyword_inventory_is_closed(self) -> None:
        used: set[str] = set()
        for path in SCHEMA_PATHS:
            schema = json.loads(path.read_text(encoding="utf-8"))

            def visit(value: object) -> None:
                if isinstance(value, dict):
                    used.update(value)
                    for item in value.values():
                        visit(item)
                elif isinstance(value, list):
                    for item in value:
                        visit(item)

            visit(schema)
        required = {
            "$schema", "$id", "$ref", "$defs", "type", "properties", "required",
            "additionalProperties", "const", "enum", "pattern", "minLength",
            "maxLength", "minItems", "maxItems", "uniqueItems", "items", "allOf",
            "oneOf", "anyOf", "if", "then", "else", "minimum", "maximum",
        }
        schema_keywords = {item for item in used if item in required}
        self.assertEqual(schema_keywords, required)


if __name__ == "__main__":
    unittest.main()
