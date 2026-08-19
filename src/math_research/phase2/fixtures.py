"""Deterministic accepted-state fixture for the Phase 2 baseline loop."""

from __future__ import annotations

from dataclasses import replace

from ..application.manual_slice import ACTOR, STAMP, build_known_valid_theorem_dossier
from ..domain.entities import AuditEvent, ObligationStatus, ResearchDossier, oid


def build_open_theorem_dossier() -> ResearchDossier:
    """Return an approved target with accepted premises and one open obligation.

    The known-valid Phase 1 dossier is used only as a source of immutable
    vocabulary. Target proof evidence, verification, and warrant are removed;
    accepted definition and representation facts remain. The Phase 1 fixture is
    never mutated.
    """

    base = build_known_valid_theorem_dossier()
    target_id = base.formalization.target_claim_id
    warrants = tuple(item for item in base.warrants if item.claim_id != target_id)
    evidence = tuple(item for item in base.evidence if item.claim_id != target_id)
    verifications = tuple(item for item in base.verification_records if item.claim_id != target_id)
    obligations = tuple(
        replace(item, status=ObligationStatus.OPEN, discharged_by_warrant_id=None)
        if item.claim_id == target_id else item
        for item in base.obligations
    )
    event = AuditEvent(
        id=oid("event.phase2.accepted_state.v1"), created_at=STAMP, created_by=ACTOR,
        aggregate_id=base.problem.id, event_type="phase2_accepted_state_created",
        payload=(("target_claim_id", target_id.value), ("trust_status", "unknown")),
        idempotency_key="phase2-accepted-state-v1",
    )
    return replace(
        base,
        id=oid("dossier.even_sum.phase2.open.v1"),
        warrants=warrants,
        evidence=evidence,
        obligations=obligations,
        verification_records=verifications,
        audit_events=(event,),
        capabilities=(
            "canonical_json", "policy_projection", "append_only_events",
            "durable_workspace", "proposal_only_model_loop",
        ),
    )

