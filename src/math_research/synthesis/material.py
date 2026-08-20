"""Material partial-result surfacing and the missing lifecycle writer.

Contract Section 10. Eligible material results traverse the existing ADR-0019
rules, so this module delegates surfacing to the sealed Phase 5 service rather
than reimplementing it. It adds exactly two things the sealed slice does not
provide:

* **Separation of duty.** Phase 5 accepts an identical originating and creating
  principal -- its own deterministic demo path passes the same system principal
  for both. ERS-AC-07 forbids self-authorization, so the check lives here.
* **A lifecycle writer.** The Phase 5 projection reads
  `material_partial_result_lifecycle` records and derives `current_validity` from
  them, but nothing in Phase 5 ever appends one. Section 10 requires that a
  source correction, invalidation, supersession, or changed applicability append
  a semantic record in the same event stream, so this supplies that writer to the
  exact ADR-0019 contract shape.

Phase 5 records and events are never modified.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..phase4a.records import ActorKind, Authority
from ..phase5 import POLICY_ID, POLICY_VERSION
from ..phase5.serialization import canonical_hash, finalize, stable_id
from ..phase5.service import Phase5Service
from .state import SynthesisValidationError, ValueEnum, parse_enum

LIFECYCLE_SCHEMA_VERSION = "adaivy.material-partial-result-lifecycle.v1"
LIFECYCLE_RECORD_TYPE = "material_partial_result_lifecycle"
LIFECYCLE_EVENT_TYPE = "research.material_partial_result_lifecycle_recorded"
LIFECYCLE_CAPABILITY = "review_result_lifecycle"

# Classifications that constitute a genuine material result. None of these is a
# generic progress label, which ERS-AC-07 forbids.
REFUTATION_CLASSIFICATION = "refutes"


class LifecycleChangeKind(ValueEnum):
    CORRECTION = "correction"
    SUPERSESSION = "supersession"
    REVOCATION = "revocation"
    TAKEDOWN = "takedown"
    DELETION = "deletion"
    WITHDRAWAL = "withdrawal"
    RIGHTS_APPLICABILITY_CHANGED = "rights_applicability_changed"
    APPLICABILITY_REVIEW_CHANGED = "applicability_review_changed"


# ADR-0019 derives the state from the change kind; the two must agree.
_DERIVED_STATE = {
    LifecycleChangeKind.CORRECTION: "corrected",
    LifecycleChangeKind.SUPERSESSION: "superseded",
}


def derived_state(kind: LifecycleChangeKind) -> str:
    return _DERIVED_STATE.get(kind, "invalidated")


class SelfAuthorizationRejected(PermissionError):
    """The originating and creating principals are the same."""


def require_separation_of_duty(
    *, originating_principal_id: str, created_by_principal_id: str
) -> None:
    """Reject self-authorization before any surfacing occurs."""
    if originating_principal_id == created_by_principal_id:
        raise SelfAuthorizationRejected(
            "a material result cannot be surfaced by its own originating principal"
        )


def surface_counterexample(
    service: Phase5Service,
    *,
    objective_id: str,
    run_id: str,
    branch_id: str,
    finding_id: str,
    evidence_id: str,
    statement: str,
    originating_principal_id: str,
    created_by_principal_id: str,
    capability_id: str,
    recorded_at: str,
    classification: str = REFUTATION_CLASSIFICATION,
) -> dict[str, Any]:
    """Surface a counterexample through the sealed ADR-0019 path.

    Adds the separation-of-duty precondition, then delegates every identity,
    authority, materiality, causality, and idempotency rule to Phase 5.
    """
    require_separation_of_duty(
        originating_principal_id=originating_principal_id,
        created_by_principal_id=created_by_principal_id,
    )
    if classification != REFUTATION_CLASSIFICATION:
        raise SynthesisValidationError(
            f"a counterexample is classified {REFUTATION_CLASSIFICATION!r}, not {classification!r}"
        )
    return service.surface_material_result(
        objective_id=objective_id,
        run_id=run_id,
        branch_id=branch_id,
        finding_id=finding_id,
        evidence_id=evidence_id,
        classification=classification,
        statement=statement,
        originating_principal_id=originating_principal_id,
        created_by_principal_id=created_by_principal_id,
        capability_id=capability_id,
        recorded_at=recorded_at,
    )


def append_result_lifecycle(
    service: Phase5Service,
    *,
    event_id: str,
    change_kind: LifecycleChangeKind | str,
    principal_id: str,
    capability_id: str,
    reason: str,
    affected_evidence_ids: Sequence[str],
    recorded_at: str,
    source_record_ids: Sequence[str] = (),
    applicability_review_ids: Sequence[str] = (),
    superseding_event_id: str | None = None,
) -> dict[str, Any]:
    """Append one lifecycle record referencing an immutable surfaced event.

    The original event is never mutated: the current-validity view is derived
    from the immutable original plus this later record.
    """
    kind = parse_enum(LifecycleChangeKind, change_kind, field="change_kind")
    workspace = service.workspace
    event_record = workspace.record(event_id)
    if event_record["record_type"] != "material_partial_result_event":
        raise SynthesisValidationError(f"{event_id} is not a surfaced material result event")
    event = event_record["payload"]["event"]

    principal, _capability = service._principal_capability(
        principal_id, capability_id, LIFECYCLE_CAPABILITY
    )
    payload = principal["payload"]
    if payload["actor_kind"] != ActorKind.HUMAN.value or payload["authority"] != Authority.HUMAN_FINAL.value:
        raise PermissionError("result lifecycle review requires a trusted human-final principal")

    if (kind is LifecycleChangeKind.SUPERSESSION) != (superseding_event_id is not None):
        raise SynthesisValidationError(
            "a supersession names its superseding event and no other change kind may"
        )
    if not affected_evidence_ids:
        raise SynthesisValidationError("a lifecycle record must name the affected evidence")

    prior = tuple(
        record
        for record in workspace.records(LIFECYCLE_RECORD_TYPE)
        if record["payload"]["lifecycle"]["material_result_event_id"] == event_id
    )
    sequence = len(prior) + 1
    # The chain roots at the immutable event and then follows prior lifecycle
    # records, mirroring the Phase 5 steering chain.
    causal_predecessor_id = (
        prior[-1]["payload"]["lifecycle"]["lifecycle_id"] if prior else event_id
    )
    idempotency_key = f"result-lifecycle:{event_id}:{kind.value}:{sequence}"
    lifecycle_id = stable_id(
        "result-lifecycle", {"event_id": event_id, "idempotency_key": idempotency_key}
    )

    lifecycle = {
        "lifecycle_id": lifecycle_id,
        "event_type": LIFECYCLE_EVENT_TYPE,
        "idempotency_key": idempotency_key,
        "material_result_event_id": event_id,
        "objective_id": event["objective_id"],
        "run_id": event["run_id"],
        "change_kind": kind.value,
        "derived_state": derived_state(kind),
        "principal_id": principal_id,
        "capability_id": capability_id,
        "required_capability": LIFECYCLE_CAPABILITY,
        "effective_actor_kind": ActorKind.HUMAN.value,
        "authority": Authority.HUMAN_FINAL.value,
        "affected_evidence_ids": list(dict.fromkeys(affected_evidence_ids)),
        "source_record_ids": list(dict.fromkeys(source_record_ids)),
        "applicability_review_ids": list(dict.fromkeys(applicability_review_ids)),
        "reason": reason,
        "created_at": recorded_at,
        "causal_predecessor_id": causal_predecessor_id,
        "superseding_event_id": superseding_event_id,
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "sequence": sequence,
    }
    envelope = finalize(
        {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "record_type": LIFECYCLE_RECORD_TYPE,
            "lifecycle": lifecycle,
        }
    )
    record = workspace.append(
        record_type=LIFECYCLE_RECORD_TYPE,
        subject_id=event_id,
        record_id=lifecycle_id,
        payload=envelope,
        recorded_at=recorded_at,
        event_type=LIFECYCLE_EVENT_TYPE,
        event_idempotency_key=idempotency_key,
        aggregate_id=event["run_id"],
    )
    workspace.rebuild_material_projection()
    return record


__all__ = [
    "LIFECYCLE_CAPABILITY",
    "LIFECYCLE_EVENT_TYPE",
    "LIFECYCLE_RECORD_TYPE",
    "LIFECYCLE_SCHEMA_VERSION",
    "LifecycleChangeKind",
    "REFUTATION_CLASSIFICATION",
    "SelfAuthorizationRejected",
    "append_result_lifecycle",
    "derived_state",
    "require_separation_of_duty",
    "surface_counterexample",
]
