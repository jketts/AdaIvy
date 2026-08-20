"""Executable preproduction contract for material partial-result surfacing v1.

These tests freeze the boundary that a later production service must satisfy.
They deliberately do not install a Phase 4 repository, migration, or runtime
authority path.
"""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAX_ENVELOPE_BYTES = 2_097_152
MAX_STEERING_RECORDS = 256
CLASSIFICATIONS = {
    "refutes", "restricts", "strengthens", "generalizes", "redirects",
}
ACTIONS = {
    "continue_objective", "investigate_result", "redirect_objective",
    "acknowledge", "dismiss",
}
METHODS = {
    "human_review", "deterministic_check", "formal_kernel",
    "rigorous_certificate", "exact_counterexample",
}


class ContractRejected(ValueError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def strict_json_loads(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_ENVELOPE_BYTES:
        raise ContractRejected("material-result envelope exceeds the raw-byte limit")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ContractRejected("material-result envelope is not UTF-8") from error

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ContractRejected(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    try:
        value = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ContractRejected(f"non-finite JSON number: {item}")
            ),
        )
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ContractRejected("malformed material-result envelope") from error
    if not isinstance(value, dict):
        raise ContractRejected("material-result envelope must be an object")
    return value


def exact_fields(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractRejected(f"{label} fields differ")
    return value


def timestamp(value: object) -> None:
    if not isinstance(value, str) or len(value) > 64:
        raise ContractRejected("invalid timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractRejected("invalid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractRejected("timestamp must include an offset")


def content_hash(envelope: dict[str, Any]) -> str:
    preimage = copy.deepcopy(envelope)
    preimage.pop("content_hash", None)
    return "sha256:" + hashlib.sha256(canonical_bytes(preimage)).hexdigest()


def seal(envelope: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(envelope)
    value["content_hash"] = content_hash(value)
    return value


class ContractContext:
    active_objectives = {"problem.active"}
    run_objectives = {"run.active": "problem.active"}
    evidence = {"evidence.counterexample"}
    verification_records = {"verification.exact-counterexample"}
    materiality_assessments = {"materiality.user-impact"}
    authorities = {
        "actor.model.explorer": {("authority.result-origin", "result_origin")},
        "actor.system.orchestrator": {
            ("authority.surface-verified-result", "surface_verified_result")
        },
        "actor.human.owner": {("authority.steer-research", "steer_research")},
    }


def validate_authority(value: object, *, allowed_types: set[str], context: ContractContext) -> dict[str, Any]:
    actor = exact_fields(
        value, {"actor_id", "actor_type", "authority_id", "authority_type"},
        "authority",
    )
    if actor["actor_type"] not in allowed_types:
        raise ContractRejected("actor type lacks authority")
    expected = (actor["authority_id"], actor["authority_type"])
    if expected not in context.authorities.get(actor["actor_id"], set()):
        raise ContractRejected("actor/authority pair is not accepted")
    return actor


def validate_envelope(data: bytes, context: ContractContext) -> dict[str, Any]:
    envelope = strict_json_loads(data)
    exact_fields(
        envelope,
        {"schema_version", "record_type", "event", "steering_records", "content_hash"},
        "envelope",
    )
    if envelope["schema_version"] != "adaivy.material-partial-result-event.v1":
        raise ContractRejected("unsupported material-result schema version")
    if envelope["record_type"] != "material_partial_result_envelope":
        raise ContractRejected("unsupported material-result record type")

    event = exact_fields(
        envelope["event"],
        {
            "event_id", "event_type", "semantic_idempotency_key", "objective_id",
            "run_id", "classification", "statement", "materiality_explanation",
            "materiality_assessment_id", "evidence_references", "verification",
            "origin", "created_by", "created_at", "causal_parent_ids",
            "main_objective_incomplete", "available_steering_actions",
        },
        "event",
    )
    if event["event_type"] != "research.material_partial_result_surfaced":
        raise ContractRejected("wrong semantic event type")
    if event["classification"] not in CLASSIFICATIONS:
        raise ContractRejected("unknown material-result classification")
    if not isinstance(event["statement"], str) or not 1 <= len(event["statement"]) <= 4096:
        raise ContractRejected("invalid result statement")
    if not isinstance(event["materiality_explanation"], str) or not 1 <= len(event["materiality_explanation"]) <= 8192:
        raise ContractRejected("invalid materiality explanation")
    if event["materiality_assessment_id"] not in context.materiality_assessments:
        raise ContractRejected("ordinary or unassessed work is not material")
    if event["objective_id"] not in context.active_objectives:
        raise ContractRejected("objective is not active")
    if context.run_objectives.get(event["run_id"]) != event["objective_id"]:
        raise ContractRejected("run does not belong to objective")
    if event["main_objective_incomplete"] is not True:
        raise ContractRejected("surfacing cannot complete the main objective")
    if set(event["available_steering_actions"]) != ACTIONS or len(event["available_steering_actions"]) != 5:
        raise ContractRejected("all steering actions must be available exactly once")
    if not isinstance(event["causal_parent_ids"], list) or len(event["causal_parent_ids"]) > 64:
        raise ContractRejected("invalid causal parents")
    timestamp(event["created_at"])

    origin = validate_authority(
        event["origin"],
        allowed_types={"human", "model", "tool", "formal_system", "external_system", "system"},
        context=context,
    )
    if origin["authority_type"] != "result_origin":
        raise ContractRejected("origin lacks result-origin authority")
    creator = validate_authority(
        event["created_by"], allowed_types={"human", "system"}, context=context,
    )
    if creator["authority_type"] != "surface_verified_result":
        raise ContractRejected("creator lacks surfacing authority")

    references = event["evidence_references"]
    if not isinstance(references, list) or not 1 <= len(references) <= 64:
        raise ContractRejected("verified material result needs bounded evidence")
    for reference in references:
        item = exact_fields(reference, {"reference_id", "reference_kind", "content_hash"}, "evidence reference")
        if item["reference_id"] not in context.evidence:
            raise ContractRejected("unknown evidence reference")
        if item["reference_kind"] not in {"evidence", "certificate", "proof", "verified_artifact"}:
            raise ContractRejected("unknown evidence kind")

    verification = exact_fields(
        event["verification"],
        {"status", "method", "verification_record_ids", "policy_id"},
        "verification",
    )
    if verification["status"] != "verified":
        raise ContractRejected("unverified proposal cannot be surfaced")
    if verification["method"] not in METHODS:
        raise ContractRejected("unknown verification method")
    record_ids = verification["verification_record_ids"]
    if not isinstance(record_ids, list) or not record_ids or len(record_ids) > 64:
        raise ContractRejected("verification records are required")
    if any(item not in context.verification_records for item in record_ids):
        raise ContractRejected("unknown verification record")

    steering = envelope["steering_records"]
    if not isinstance(steering, list) or len(steering) > MAX_STEERING_RECORDS:
        raise ContractRejected("too many steering records")
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for record in steering:
        item = exact_fields(
            record,
            {
                "action_id", "event_id", "event_type", "action", "actor",
                "created_at", "idempotency_key", "target_objective_id",
                "supersedes_action_id",
            },
            "steering record",
        )
        if item["action_id"] in seen_ids or item["idempotency_key"] in seen_keys:
            raise ContractRejected("duplicate steering identity")
        if item["event_id"] != event["event_id"]:
            raise ContractRejected("steering record targets another event")
        if item["event_type"] != "research.material_partial_result_steering_recorded":
            raise ContractRejected("wrong steering event type")
        if item["action"] not in ACTIONS:
            raise ContractRejected("unknown steering action")
        steering_actor = validate_authority(
            item["actor"], allowed_types={"human"}, context=context,
        )
        if steering_actor["authority_type"] != "steer_research":
            raise ContractRejected("actor lacks steering authority")
        needs_target = item["action"] in {"investigate_result", "redirect_objective"}
        if needs_target != (item["target_objective_id"] is not None):
            raise ContractRejected("steering target does not match action")
        if item["supersedes_action_id"] is not None and item["supersedes_action_id"] not in seen_ids:
            raise ContractRejected("steering supersession is dangling or reordered")
        timestamp(item["created_at"])
        seen_ids.add(item["action_id"])
        seen_keys.add(item["idempotency_key"])

    if envelope["content_hash"] != content_hash(envelope):
        raise ContractRejected("material-result content hash mismatch")
    return copy.deepcopy(envelope)


class ContractStore:
    """Test-only idempotency model for the future production acceptance suite."""

    def __init__(self, context: ContractContext) -> None:
        self.context = context
        self.events: dict[str, dict[str, Any]] = {}
        self.keys: dict[str, str] = {}

    def accept(self, data: bytes) -> dict[str, Any]:
        accepted = validate_envelope(data, self.context)
        event = accepted["event"]
        event_id = event["event_id"]
        key = event["semantic_idempotency_key"]
        existing_id = self.keys.get(key)
        existing = self.events.get(event_id)
        if existing_id is not None and existing_id != event_id:
            raise ContractRejected("semantic idempotency key reused")
        if existing is not None:
            if existing != accepted:
                raise ContractRejected("event identity reused with different content")
            return copy.deepcopy(existing)
        self.events[event_id] = copy.deepcopy(accepted)
        self.keys[key] = event_id
        return copy.deepcopy(accepted)


def base_envelope(*, classification: str = "refutes") -> dict[str, Any]:
    return seal(
        {
            "schema_version": "adaivy.material-partial-result-event.v1",
            "record_type": "material_partial_result_envelope",
            "event": {
                "event_id": "material-result.counterexample-1",
                "event_type": "research.material_partial_result_surfaced",
                "semantic_idempotency_key": "material-result:run.active:counterexample-1",
                "objective_id": "problem.active",
                "run_id": "run.active",
                "classification": classification,
                "statement": "The candidate universal statement fails for an exact witness.",
                "materiality_explanation": "The witness rules out the active theorem as stated and changes the next research choice.",
                "materiality_assessment_id": "materiality.user-impact",
                "evidence_references": [
                    {
                        "reference_id": "evidence.counterexample",
                        "reference_kind": "certificate",
                        "content_hash": "sha256:" + "1" * 64,
                    }
                ],
                "verification": {
                    "status": "verified",
                    "method": "exact_counterexample",
                    "verification_record_ids": ["verification.exact-counterexample"],
                    "policy_id": "policy.material-result-v1",
                },
                "origin": {
                    "actor_id": "actor.model.explorer",
                    "actor_type": "model",
                    "authority_id": "authority.result-origin",
                    "authority_type": "result_origin",
                },
                "created_by": {
                    "actor_id": "actor.system.orchestrator",
                    "actor_type": "system",
                    "authority_id": "authority.surface-verified-result",
                    "authority_type": "surface_verified_result",
                },
                "created_at": "2026-08-20T12:00:00+00:00",
                "causal_parent_ids": ["verification.exact-counterexample"],
                "main_objective_incomplete": True,
                "available_steering_actions": sorted(ACTIONS),
            },
            "steering_records": [],
            "content_hash": "sha256:" + "0" * 64,
        }
    )


def steering_record(action: str, *, suffix: str, target: str | None = None, supersedes: str | None = None) -> dict[str, Any]:
    return {
        "action_id": f"steering.{suffix}",
        "event_id": "material-result.counterexample-1",
        "event_type": "research.material_partial_result_steering_recorded",
        "action": action,
        "actor": {
            "actor_id": "actor.human.owner",
            "actor_type": "human",
            "authority_id": "authority.steer-research",
            "authority_type": "steer_research",
        },
        "created_at": "2026-08-20T12:01:00+00:00",
        "idempotency_key": f"steering:{suffix}",
        "target_objective_id": target,
        "supersedes_action_id": supersedes,
    }


class MaterialPartialResultV1ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ContractContext()

    def encoded(self, value: dict[str, Any]) -> bytes:
        return canonical_bytes(seal(value))

    def test_verified_refutation_surfaces_while_objective_remains_incomplete(self) -> None:
        accepted = validate_envelope(canonical_bytes(base_envelope()), self.context)
        self.assertEqual(accepted["event"]["classification"], "refutes")
        self.assertTrue(accepted["event"]["main_objective_incomplete"])

    def test_each_classification_is_accepted(self) -> None:
        for classification in sorted(CLASSIFICATIONS):
            with self.subTest(classification=classification):
                value = base_envelope(classification=classification)
                self.assertEqual(
                    validate_envelope(canonical_bytes(value), self.context)["event"]["classification"],
                    classification,
                )

    def test_ordinary_intermediate_result_is_not_automatically_material(self) -> None:
        value = base_envelope()
        value["event"]["materiality_assessment_id"] = "materiality.missing"
        with self.assertRaisesRegex(ContractRejected, "not material"):
            validate_envelope(self.encoded(value), self.context)

    def test_unverified_proposal_cannot_be_surfaced(self) -> None:
        value = base_envelope()
        value["event"]["verification"]["status"] = "proposed"
        with self.assertRaisesRegex(ContractRejected, "unverified proposal"):
            validate_envelope(self.encoded(value), self.context)

    def test_actor_and_authority_mutations_fail_at_every_acceptance_operation(self) -> None:
        mutations = []
        missing = base_envelope()
        del missing["event"]["created_by"]["authority_id"]
        mutations.append(missing)
        altered = base_envelope()
        altered["event"]["created_by"]["authority_id"] = "authority.untrusted"
        mutations.append(altered)
        wrong_actor = base_envelope()
        wrong_actor["event"]["created_by"]["actor_type"] = "model"
        mutations.append(wrong_actor)

        for operation in ("creation", "import", "replay", "restart"):
            for index, mutation in enumerate(mutations):
                with self.subTest(operation=operation, mutation=index):
                    with self.assertRaises(ContractRejected):
                        ContractStore(self.context).accept(self.encoded(mutation))

    def test_evidence_and_verification_references_survive_export_replay_and_restart(self) -> None:
        raw = canonical_bytes(base_envelope())
        imported = ContractStore(self.context).accept(raw)
        replayed = ContractStore(self.context).accept(canonical_bytes(imported))
        restarted = ContractStore(self.context).accept(canonical_bytes(replayed))
        self.assertEqual(
            restarted["event"]["evidence_references"],
            base_envelope()["event"]["evidence_references"],
        )
        self.assertEqual(
            restarted["event"]["verification"]["verification_record_ids"],
            ["verification.exact-counterexample"],
        )

    def test_event_identity_prevents_duplicate_surfacing(self) -> None:
        store = ContractStore(self.context)
        raw = canonical_bytes(base_envelope())
        first = store.accept(raw)
        second = store.accept(raw)
        self.assertEqual(first, second)
        self.assertEqual(len(store.events), 1)

        changed = base_envelope()
        changed["event"]["statement"] = "Different semantic content under the same event identity."
        with self.assertRaisesRegex(ContractRejected, "different content"):
            store.accept(self.encoded(changed))

    def test_acknowledgement_and_steering_history_survive_replay_and_restart(self) -> None:
        value = base_envelope()
        value["steering_records"] = [
            steering_record("acknowledge", suffix="ack"),
            steering_record(
                "redirect_objective", suffix="redirect",
                target="problem.redirected", supersedes="steering.ack",
            ),
        ]
        value = seal(value)
        replayed = ContractStore(self.context).accept(canonical_bytes(value))
        restarted = ContractStore(self.context).accept(canonical_bytes(replayed))
        self.assertEqual(
            [item["action"] for item in restarted["steering_records"]],
            ["acknowledge", "redirect_objective"],
        )
        self.assertTrue(restarted["event"]["main_objective_incomplete"])

    def test_malformed_duplicate_oversized_and_record_exhaustion_fail_closed(self) -> None:
        with self.assertRaises(ContractRejected):
            validate_envelope(b"{", self.context)
        with self.assertRaisesRegex(ContractRejected, "duplicate JSON key"):
            validate_envelope(b'{"schema_version":"a","schema_version":"b"}', self.context)
        with self.assertRaisesRegex(ContractRejected, "raw-byte limit"):
            validate_envelope(b" " * (MAX_ENVELOPE_BYTES + 1), self.context)

        value = base_envelope()
        value["steering_records"] = [
            steering_record("acknowledge", suffix=f"ack-{index}")
            for index in range(MAX_STEERING_RECORDS + 1)
        ]
        with self.assertRaisesRegex(ContractRejected, "too many steering"):
            validate_envelope(self.encoded(value), self.context)

    def test_schema_freezes_classifications_actions_and_verified_only_status(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/material-partial-result-event-v1.schema.json").read_text(encoding="utf-8")
        )
        event = schema["$defs"]["event"]["properties"]
        self.assertEqual(set(event["classification"]["enum"]), CLASSIFICATIONS)
        self.assertEqual(set(event["available_steering_actions"]["items"]["enum"]), ACTIONS)
        self.assertEqual(schema["$defs"]["verification"]["properties"]["status"]["const"], "verified")
        self.assertTrue(event["main_objective_incomplete"]["const"])

    def test_passed_phase4_gate_contracts_remain_byte_identical(self) -> None:
        expected = {
            "docs/adrs/0017-phase4a-local-rights-applicability-review.md": "78719c5723dd13a4f401c477b8dcc8ecce368ff83faea843acb07ae22761e659",
            "docs/adrs/0018-phase4-gate-security-reproducibility-controls.md": "b5321b3846029bfbd203adcd73e18e77640820ee6fd15cbc95c1546801da53f4",
            "docs/phase-4/SECURITY_CONTROL_INVENTORY.md": "91e33b025dc65414d51735bfaf978a36eb26c064f0bc81470930f47d2f55001b",
            "docs/phase-4/ACCEPTANCE_THRESHOLD_INVENTORY.md": "1d28107aa339caff20bbd706a41dc267bea70a79d8f05031825e9ded387a6283",
            "fixtures/phase4-gate/manifest.json": "aff0338510b876df4c727b2f048272e1f28af8bbad6a448d90f878494c3623e7",
            "schemas/phase4-gate-fixture-v1.schema.json": "ad52d76139362380d89bea28c2399cd703cc2ab7dab298fa175b40b086537858",
        }
        for relative, digest in expected.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
