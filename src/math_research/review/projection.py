"""Project the review journal into a SUCCESSOR ResearchDossier.

A `ResearchDossier` is an immutable content-hashed value, so nothing here mutates
one. The prior dossier keeps its bytes and its hash; this module derives a new
dossier whose content hash differs, and attaches an `AuditEvent` naming the
reviewers and the prior dossier hash so the chain is auditable in both
directions.

Two entity IDs are deliberately carried over with changed content: a discharged
`ProofObligation` and a decided `SemanticAlignmentRecord`. `TrustPolicy` resolves
blockers and alignment by identity, so a renamed record would read as an
unrelated open obligation. The append-only guarantee therefore lives at the
dossier level -- the prior dossier still holds the OPEN and PROPOSED versions,
and the journal holds the decision that moved them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping

from ..domain.entities import (
    AlignmentStatus,
    AuditEvent,
    Disposition,
    EpistemicWarrant,
    Evidence,
    EvidenceKind,
    ObligationStatus,
    OpaqueId,
    RecordStatus,
    ResearchDossier,
    VerificationOutcome,
    VerificationRecord,
    WarrantKind,
    oid,
)
from ..interchange import content_hash, export_dossier_dict
from . import SUCCESSOR_SCHEMA_VERSION
from .decisions import load_run_context
from .records import AlignmentDecision, DecisionKind, ReviewVerdict, refuse
from .ports import RunReader
from .serialization import canonical_hash, public_value

REVIEW_CAPABILITY = "human_review_decision_journal"

_EVIDENCE_DISPOSITION = {
    ReviewVerdict.ACCEPT_CANDIDATE.value: Disposition.ACCEPTED,
    ReviewVerdict.REJECT_CANDIDATE.value: Disposition.REJECTED,
    ReviewVerdict.INCONCLUSIVE.value: Disposition.PROPOSAL,
}
_VERIFICATION_OUTCOME = {
    ReviewVerdict.ACCEPT_CANDIDATE.value: VerificationOutcome.PASS,
    ReviewVerdict.REJECT_CANDIDATE.value: VerificationOutcome.FAIL,
    ReviewVerdict.INCONCLUSIVE.value: VerificationOutcome.INCONCLUSIVE,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class SuccessorProjection:
    schema_version: str = SUCCESSOR_SCHEMA_VERSION
    prior_dossier_id: str
    prior_dossier_hash: str
    successor: ResearchDossier
    successor_hash: str
    journal_hash: str
    applied_decision_ids: tuple[str, ...]
    reviewers: tuple[str, ...]
    derived_counts: Mapping[str, int]


def _suffix(decision_id: str) -> str:
    return decision_id.split(".", 1)[1]


def _instant(value: str, *, subject_id: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise refuse(
            "recorded_instant_malformed",
            subject_id=subject_id,
            unmet_precondition="every recorded instant is an explicit ISO-8601 UTC instant",
            detail=f"{value!r} is not parseable",
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise refuse(
            "recorded_instant_naive",
            subject_id=subject_id,
            unmet_precondition="every recorded instant is timezone-aware",
            detail=f"{value!r} carries no offset",
        )
    return parsed.astimezone(timezone.utc)


def parse_instant(value: str) -> datetime:
    """Explicit UTC instant, never a clock read."""

    if not value.endswith("Z"):
        raise refuse(
            "instant_not_utc",
            subject_id=value,
            unmet_precondition="the instant is an explicit UTC instant ending in 'Z'",
            detail=f"{value!r} does not end in 'Z'",
        )
    return _instant(value, subject_id=value)


def _event(
    *,
    event_id: str,
    stamp: datetime,
    actor: OpaqueId,
    aggregate_id: OpaqueId,
    event_type: str,
    payload: dict[str, str],
    idempotency_key: str,
) -> AuditEvent:
    return AuditEvent(
        id=oid(event_id),
        created_at=stamp,
        created_by=actor,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=tuple(sorted(payload.items())),
        idempotency_key=idempotency_key,
    )


def build_successor(
    *,
    runs: RunReader,
    run_id: OpaqueId,
    journal_export: Mapping[str, Any],
    projected_at: datetime,
    projected_by: OpaqueId,
) -> SuccessorProjection:
    context = load_run_context(runs, run_id)
    decisions = tuple(journal_export.get("decisions", ()))
    if not decisions:
        raise refuse(
            "journal_empty",
            subject_id=run_id.value,
            unmet_precondition="the review journal holds at least one decision",
            detail="nothing to project; an empty journal is not a successor dossier",
        )
    scoped = tuple(
        item for item in decisions if item.get("payload", {}).get("run_id") == run_id.value
    )
    if not scoped:
        raise refuse(
            "no_decision_for_run",
            subject_id=run_id.value,
            unmet_precondition="at least one journal decision covers this run",
            detail=f"the journal holds {len(decisions)} decisions, none for run {run_id.value}",
        )
    stale = sorted(
        {
            str(item["payload"].get("dossier_hash"))
            for item in scoped
            if item["payload"].get("dossier_hash") != context.dossier_hash
        }
    )
    if stale:
        raise refuse(
            "decision_dossier_hash_mismatch",
            subject_id=run_id.value,
            unmet_precondition="every applied decision was taken against this dossier's hash",
            detail=f"decisions reference {', '.join(stale)}; the run holds {context.dossier_hash}",
        )
    reviewers = tuple(sorted({str(item["reviewer"]["id"]) for item in scoped}))
    if projected_by.value not in reviewers:
        raise refuse(
            "projector_not_a_journal_reviewer",
            subject_id=run_id.value,
            unmet_precondition=(
                "the successor dossier is attributed to a named human who took a recorded decision"
            ),
            detail=f"{projected_by.value} is not among the reviewers {', '.join(reviewers)}",
        )

    ordered = sorted(scoped, key=lambda item: item["decision_id"])
    evidence: list[Evidence] = []
    verifications: list[VerificationRecord] = []
    warrants: list[EpistemicWarrant] = []
    events: list[AuditEvent] = []
    verdict_records: dict[str, tuple[OpaqueId, OpaqueId]] = {}
    obligation_updates: dict[str, Mapping[str, Any]] = {}
    alignment_update: Mapping[str, Any] | None = None

    claims = {item.id: item for item in context.dossier.claims}

    for record in ordered:
        kind = record["decision_kind"]
        payload = record["payload"]
        decision_id = record["decision_id"]
        actor = oid(str(record["reviewer"]["id"]))
        stamp = _instant(str(record["recorded_at"]), subject_id=decision_id)
        suffix = _suffix(decision_id)
        if kind == DecisionKind.REVIEW_VERDICT.value:
            claim_id = oid(str(payload["target_claim_id"]))
            statement = claims[claim_id].statement
            body = _verdict_evidence_text(record)
            item = Evidence(
                id=oid(f"evidence.review.{suffix}"),
                created_at=stamp,
                created_by=actor,
                claim_id=claim_id,
                kind=EvidenceKind.MODEL_OUTPUT,
                content=body,
                artifact_hash=content_hash(body),
                source_ref=(
                    f"phase2:run/{payload['run_id']}/proposal/"
                    f"{payload['verifier_finding_proposal_id']}"
                ),
                disposition=_EVIDENCE_DISPOSITION[str(payload["verdict"])],
            )
            check = VerificationRecord(
                id=oid(f"verification.review.{suffix}"),
                created_at=stamp,
                created_by=actor,
                claim_id=claim_id,
                verifier_kind="human_review",
                outcome=_VERIFICATION_OUTCOME[str(payload["verdict"])],
                evidence_ids=(item.id,),
                target_statement_hash=content_hash(statement),
                independent_from_proposer=True,
                disposition=Disposition.ACCEPTED,
                notes=(
                    f"reviewer={record['reviewer']['id']}",
                    f"attestation={record['reviewer']['attestation']}",
                    f"independently_checked={str(payload['independently_checked']).lower()}",
                    f"verifier_recommendation={payload['verifier_recommendation']}",
                    f"review_decision_id={decision_id}",
                ),
            )
            evidence.append(item)
            verifications.append(check)
            verdict_records[decision_id] = (item.id, check.id)
            events.append(
                _event(
                    event_id=f"event.review.{suffix}",
                    stamp=stamp,
                    actor=actor,
                    aggregate_id=oid(str(payload["run_id"])),
                    event_type="review_verdict_recorded",
                    payload={
                        "decision_id": decision_id,
                        "independently_checked": str(payload["independently_checked"]).lower(),
                        "reviewer": str(record["reviewer"]["id"]),
                        "verdict": str(payload["verdict"]),
                        "verifier_recommendation": str(payload["verifier_recommendation"]),
                    },
                    idempotency_key=f"review-decision:{decision_id}",
                )
            )
        elif kind == DecisionKind.SEMANTIC_ALIGNMENT_DECISION.value:
            alignment_update = record
            events.append(
                _event(
                    event_id=f"event.review.{suffix}",
                    stamp=stamp,
                    actor=actor,
                    aggregate_id=oid(str(payload["alignment_id"])),
                    event_type="semantic_alignment_decided",
                    payload={
                        "approver": str(record["reviewer"]["id"]),
                        "decision": str(payload["decision"]),
                        "decision_id": decision_id,
                        "prior_status": str(payload["prior_status"]),
                        "resolves_target_under_trust_policy": str(
                            payload["resolves_target_under_trust_policy"]
                        ).lower(),
                    },
                    idempotency_key=f"review-decision:{decision_id}",
                )
            )
        elif kind == DecisionKind.WARRANT_GRANT.value:
            claim_id = oid(str(payload["claim_id"]))
            statement = claims[claim_id].statement
            if payload["basis"] == "formal_kernel":
                body = str(payload["formal_finding_semantic_json"])
                item = Evidence(
                    id=oid(f"evidence.kernel.{suffix}"),
                    created_at=stamp,
                    created_by=actor,
                    claim_id=claim_id,
                    kind=EvidenceKind.FORMAL_ARTIFACT,
                    content=body,
                    artifact_hash=content_hash(body),
                    source_ref=f"phase3b:finding/{payload['formal_finding_id']}",
                    disposition=Disposition.ACCEPTED,
                )
                check = VerificationRecord(
                    id=oid(f"verification.kernel.{suffix}"),
                    created_at=stamp,
                    created_by=actor,
                    claim_id=claim_id,
                    verifier_kind=str(payload["verifier_kind"]),
                    outcome=VerificationOutcome.PASS,
                    evidence_ids=(item.id,),
                    target_statement_hash=content_hash(statement),
                    independent_from_proposer=True,
                    disposition=Disposition.ACCEPTED,
                    notes=(
                        f"formal_finding_id={payload['formal_finding_id']}",
                        f"formal_finding_outcome={payload['formal_finding_outcome']}",
                        f"formal_target_hash={payload['formal_target_hash']}",
                        f"semantic_alignment_id={payload['formal_finding_semantic_alignment_id']}",
                        "the kernel checked the formal target; the identification of that target "
                        "with this claim rests on the approved semantic alignment, not on the kernel",
                        f"granted_by={record['reviewer']['id']}",
                    ),
                )
                evidence.append(item)
                verifications.append(check)
                evidence_ids = (item.id,)
                verification_ids = (check.id,)
            else:
                supporting = [str(value) for value in payload["supporting_decision_ids"]]
                missing = [item_id for item_id in supporting if item_id not in verdict_records]
                if missing:
                    raise refuse(
                        "supporting_decision_not_projected",
                        subject_id=str(payload["claim_id"]),
                        unmet_precondition=(
                            "every supporting review verdict a warrant names is in the journal"
                        ),
                        detail=f"missing supporting decisions: {', '.join(sorted(missing))}",
                    )
                evidence_ids = tuple(verdict_records[item_id][0] for item_id in supporting)
                verification_ids = tuple(verdict_records[item_id][1] for item_id in supporting)
            warrant = EpistemicWarrant(
                id=oid(str(payload["warrant_id"])),
                created_at=stamp,
                created_by=actor,
                claim_id=claim_id,
                kind=WarrantKind(str(payload["kind"])),
                scope=str(payload["scope"]),
                evidence_ids=evidence_ids,
                verification_record_ids=verification_ids,
                status=RecordStatus.ACTIVE,
            )
            warrants.append(warrant)
            events.append(
                _event(
                    event_id=f"event.review.{suffix}",
                    stamp=stamp,
                    actor=actor,
                    aggregate_id=claim_id,
                    event_type="epistemic_warrant_granted",
                    payload={
                        "basis": str(payload["basis"]),
                        "decision_id": decision_id,
                        "granted_by": str(record["reviewer"]["id"]),
                        "kind": str(payload["kind"]),
                        "warrant_id": str(payload["warrant_id"]),
                    },
                    idempotency_key=f"review-decision:{decision_id}",
                )
            )
        elif kind == DecisionKind.OBLIGATION_DISCHARGE.value:
            obligation_updates[str(payload["obligation_id"])] = record
            events.append(
                _event(
                    event_id=f"event.review.{suffix}",
                    stamp=stamp,
                    actor=actor,
                    aggregate_id=oid(str(payload["obligation_id"])),
                    event_type="proof_obligation_discharged",
                    payload={
                        "decision_id": decision_id,
                        "discharged_by": str(record["reviewer"]["id"]),
                        "discharged_by_warrant_id": str(payload["discharged_by_warrant_id"]),
                        "prior_status": str(payload["prior_status"]),
                    },
                    idempotency_key=f"review-decision:{decision_id}",
                )
            )
        else:  # pragma: no cover - the journal CHECK constraint forbids this
            raise refuse(
                "unknown_decision_kind",
                subject_id=decision_id,
                unmet_precondition="every journal decision has a known kind",
                detail=f"decision kind {kind!r} is not projectable",
            )

    granted = {item.id.value for item in warrants}
    obligations = []
    for obligation in context.dossier.obligations:
        record = obligation_updates.get(obligation.id.value)
        if record is None:
            obligations.append(obligation)
            continue
        warrant_id = str(record["payload"]["discharged_by_warrant_id"])
        if warrant_id not in granted:
            raise refuse(
                "discharging_warrant_not_projected",
                subject_id=obligation.id.value,
                unmet_precondition=(
                    "discharged_by_warrant_id names a warrant present in the successor dossier"
                ),
                detail=f"warrant {warrant_id} is not among {', '.join(sorted(granted)) or '(none)'}",
            )
        obligations.append(
            replace(
                obligation,
                status=ObligationStatus.DISCHARGED,
                discharged_by_warrant_id=oid(warrant_id),
            )
        )

    alignment = context.dossier.semantic_alignment
    if alignment_update is not None:
        decision = str(alignment_update["payload"]["decision"])
        status = (
            AlignmentStatus.RESEARCHER_APPROVED
            if decision == AlignmentDecision.APPROVE.value
            else AlignmentStatus.DISPUTED
        )
        alignment = replace(
            alignment,
            status=status,
            approved_by=oid(str(alignment_update["reviewer"]["id"])),
        )

    journal_hash = str(journal_export.get("content_hash"))
    applied = tuple(item["decision_id"] for item in ordered)
    identity = canonical_hash(
        public_value(
            {
                "applied_decision_ids": list(applied),
                "journal_hash": journal_hash,
                "prior_dossier_hash": context.dossier_hash,
                "projected_at": projected_at.isoformat(timespec="microseconds").replace(
                    "+00:00", "Z"
                ),
                "projected_by": projected_by.value,
                "schema_version": SUCCESSOR_SCHEMA_VERSION,
            }
        )
    )
    digest = identity.removeprefix("sha256:")[:16]
    projection_event = _event(
        event_id=f"event.review-projection.{digest}",
        stamp=projected_at,
        actor=projected_by,
        aggregate_id=context.dossier.id,
        event_type="review_journal_projected",
        payload={
            "applied_decision_count": str(len(applied)),
            "journal_semantic_hash": journal_hash,
            "prior_dossier_hash": context.dossier_hash,
            "prior_dossier_id": context.dossier.id.value,
            "projected_by": projected_by.value,
            "reviewers": ",".join(reviewers),
            "successor_schema_version": SUCCESSOR_SCHEMA_VERSION,
            "warrants_granted": str(len(warrants)),
        },
        idempotency_key=f"review-projection:{context.dossier_hash}:{identity}",
    )

    successor = ResearchDossier(
        id=oid(f"{context.dossier.id.value}.review.sha256-{digest}"),
        created_at=projected_at,
        created_by=projected_by,
        problem=context.dossier.problem,
        formalization=context.dossier.formalization,
        semantic_alignment=alignment,
        claims=context.dossier.claims,
        warrants=tuple(sorted(warrants, key=lambda item: item.id.value)),
        evidence=tuple(sorted(evidence, key=lambda item: item.id.value)),
        source_applicability=context.dossier.source_applicability,
        obligations=tuple(sorted(obligations, key=lambda item: item.id.value)),
        representation_maps=context.dossier.representation_maps,
        verification_records=tuple(sorted(verifications, key=lambda item: item.id.value)),
        evaluation_protocol=context.dossier.evaluation_protocol,
        audit_events=(
            *context.dossier.audit_events,
            *sorted(events, key=lambda item: item.id.value),
            projection_event,
        ),
        capabilities=tuple(sorted({*context.dossier.capabilities, REVIEW_CAPABILITY})),
    )
    successor_hash = export_dossier_dict(successor)["content_hash"]
    if successor_hash == context.dossier_hash:
        raise refuse(
            "successor_hash_unchanged",
            subject_id=run_id.value,
            unmet_precondition="the successor dossier has a new content hash",
            detail="projection produced a dossier identical to its predecessor",
        )
    return SuccessorProjection(
        prior_dossier_id=context.dossier.id.value,
        prior_dossier_hash=context.dossier_hash,
        successor=successor,
        successor_hash=successor_hash,
        journal_hash=journal_hash,
        applied_decision_ids=applied,
        reviewers=reviewers,
        derived_counts={
            "audit_events": len(events) + 1,
            "evidence": len(evidence),
            "obligations_discharged": len(obligation_updates),
            "verification_records": len(verifications),
            "warrants": len(warrants),
        },
    )


def _verdict_evidence_text(record: Mapping[str, Any]) -> str:
    """The reviewed artifact plus what the reviewer said about it.

    The evidence content names the model finding it reviewed AND the human who
    accepted it, so a reader of the dossier alone cannot mistake accepted
    evidence for an unreviewed model claim.
    """

    payload = record["payload"]
    return "\n".join(
        [
            "human review of a Phase 2 verifier finding",
            f"review_decision_id: {record['decision_id']}",
            f"reviewer: {record['reviewer']['id']}",
            f"reviewer_attestation: {record['reviewer']['attestation']}",
            f"verdict: {payload['verdict']}",
            f"independently_checked: {str(payload['independently_checked']).lower()}",
            f"rationale: {payload['rationale']}",
            f"run_id: {payload['run_id']}",
            f"verifier_finding_artifact_hash: {payload['verifier_finding_artifact_hash']}",
            f"candidate_artifact_hash: {payload['candidate_artifact_hash']}",
            f"verifier_recommendation (input, not a verdict): {payload['verifier_recommendation']}",
        ]
    )
