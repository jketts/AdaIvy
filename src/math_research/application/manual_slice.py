"""Deterministic construction of the complete manual Phase 1 dossier."""

from __future__ import annotations

from datetime import datetime, timezone

from ..domain.entities import (
    AlignmentStatus,
    ApplicabilityStatus,
    ApprovalStatus,
    AuditEvent,
    Claim,
    ClaimOrigin,
    ClaimScope,
    Compatibility,
    Disposition,
    EpistemicWarrant,
    EvaluationProtocol,
    Evidence,
    EvidenceKind,
    Formalization,
    ObligationStatus,
    ProblemType,
    ProofObligation,
    ProtocolPhase,
    RecordStatus,
    RepresentationMap,
    RepresentationStatus,
    ResearchDossier,
    ResearchProblem,
    SemanticAlignmentRecord,
    SourceApplicabilityRecord,
    StrengthRelation,
    VerificationOutcome,
    VerificationRecord,
    WarrantKind,
    oid,
)
from ..interchange import content_hash

STAMP = datetime(2026, 8, 19, 0, 0, tzinfo=timezone.utc)
ACTOR = oid("actor.manual_researcher")


def _hash_text(text: str) -> str:
    return content_hash(text)


def build_known_valid_theorem_dossier() -> ResearchDossier:
    definition = Claim(
        id=oid("claim.even_definition.v1"), created_at=STAMP, created_by=ACTOR,
        kind="definition", statement="An integer n is even iff there exists k in Z with n = 2k.",
        assumption_claim_ids=(), origin=ClaimOrigin.SOURCE, scope=ClaimScope.DEFINITIONAL,
    )
    target = Claim(
        id=oid("claim.even_sum.v1"), created_at=STAMP, created_by=ACTOR,
        kind="theorem", statement="For all integers a and b, if a and b are even, then a + b is even.",
        assumption_claim_ids=(definition.id,), origin=ClaimOrigin.USER,
        scope=ClaimScope.UNRESTRICTED_UNIVERSAL,
        representation_map_ids=(oid("representation.integer_algebra.v1"),),
    )
    encoding = Claim(
        id=oid("claim.integer_algebra_encoding.v1"), created_at=STAMP, created_by=ACTOR,
        kind="equivalence", statement="Integer algebra preserves addition and the existential definition of even.",
        assumption_claim_ids=(definition.id,), origin=ClaimOrigin.USER, scope=ClaimScope.UNRESTRICTED_UNIVERSAL,
    )

    proof_evidence = Evidence(
        id=oid("evidence.even_sum_derivation.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=target.id, kind=EvidenceKind.DERIVATION,
        content="Let a=2k and b=2l. Then a+b=2(k+l), with k+l an integer.",
        artifact_hash=_hash_text("Let a=2k and b=2l. Then a+b=2(k+l), with k+l an integer."),
        source_ref=None, disposition=Disposition.ACCEPTED,
    )
    source_evidence = Evidence(
        id=oid("evidence.even_definition_source.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=definition.id, kind=EvidenceKind.SOURCE_SPAN,
        content="Definition: n is even exactly when n=2k for an integer k.",
        artifact_hash=_hash_text("Definition: n is even exactly when n=2k for an integer k."),
        source_ref="local:manual-source#line-1", disposition=Disposition.ACCEPTED,
    )
    bridge_evidence = Evidence(
        id=oid("evidence.integer_algebra_bridge.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=encoding.id, kind=EvidenceKind.DERIVATION,
        content="The representation uses the same integer carrier, addition, multiplication by 2, and existential quantifier.",
        artifact_hash=_hash_text("The representation uses the same integer carrier, addition, multiplication by 2, and existential quantifier."),
        source_ref=None, disposition=Disposition.ACCEPTED,
    )

    target_verification = VerificationRecord(
        id=oid("verification.even_sum_manual.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=target.id, verifier_kind="independent_manual_derivation_check",
        outcome=VerificationOutcome.PASS, evidence_ids=(proof_evidence.id,),
        target_statement_hash=_hash_text(target.statement), independent_from_proposer=True,
        disposition=Disposition.ACCEPTED,
    )
    source_verification = VerificationRecord(
        id=oid("verification.even_definition_applicability.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=definition.id, verifier_kind="manual_source_applicability_check",
        outcome=VerificationOutcome.PASS, evidence_ids=(source_evidence.id,),
        target_statement_hash=_hash_text(definition.statement), independent_from_proposer=True,
        disposition=Disposition.ACCEPTED,
    )
    bridge_verification = VerificationRecord(
        id=oid("verification.integer_algebra_bridge.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=encoding.id, verifier_kind="manual_representation_check",
        outcome=VerificationOutcome.PASS, evidence_ids=(bridge_evidence.id,),
        target_statement_hash=_hash_text(encoding.statement), independent_from_proposer=True,
        disposition=Disposition.ACCEPTED,
    )

    target_warrant = EpistemicWarrant(
        id=oid("warrant.even_sum_derivation.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=target.id, kind=WarrantKind.RIGOROUS_DERIVATION,
        scope="exact unrestricted target", evidence_ids=(proof_evidence.id,),
        verification_record_ids=(target_verification.id,), status=RecordStatus.ACTIVE,
    )
    source_warrant = EpistemicWarrant(
        id=oid("warrant.even_definition_source.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=definition.id, kind=WarrantKind.SOURCE_REPORT,
        scope="integer definition only", evidence_ids=(source_evidence.id,),
        verification_record_ids=(source_verification.id,), status=RecordStatus.ACTIVE,
    )
    bridge_warrant = EpistemicWarrant(
        id=oid("warrant.integer_algebra_bridge.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=encoding.id, kind=WarrantKind.RIGOROUS_DERIVATION,
        scope="integer algebra representation bridge", evidence_ids=(bridge_evidence.id,),
        verification_record_ids=(bridge_verification.id,), status=RecordStatus.ACTIVE,
    )

    proof_obligation = ProofObligation(
        id=oid("obligation.even_sum_proof.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=target.id, description="Provide a complete proof of the exact target.",
        category="logical_gap", status=ObligationStatus.DISCHARGED,
        discharged_by_warrant_id=target_warrant.id,
    )
    source_obligation = ProofObligation(
        id=oid("obligation.even_definition_applicability.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=definition.id, description="Check domain, definition, and hypotheses of the cited definition.",
        category="literature_applicability", status=ObligationStatus.DISCHARGED,
        discharged_by_warrant_id=source_warrant.id,
    )
    bridge_obligation = ProofObligation(
        id=oid("obligation.integer_algebra_bridge.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=encoding.id, description="Show that the representation preserves every operation used by the proof.",
        category="representation_bridge", status=ObligationStatus.DISCHARGED,
        discharged_by_warrant_id=bridge_warrant.id,
    )

    problem = ResearchProblem(
        id=oid("problem.even_sum.v1"), created_at=STAMP, created_by=ACTOR,
        title="Sum of two even integers", informal_statement=target.statement,
        problem_type=ProblemType.PROVE, tags=("integer-arithmetic", "manual-slice"),
        active_formalization_id=oid("formalization.even_sum.v1"),
    )
    formalization = Formalization(
        id=oid("formalization.even_sum.v1"), created_at=STAMP, created_by=ACTOR,
        problem_id=problem.id, version=1,
        statement="forall a b : Z, Even(a) and Even(b) implies Even(a+b)",
        formal_language="typed_informal_math", quantifiers=("forall a in Z", "forall b in Z"),
        assumption_claim_ids=(definition.id,), target_claim_id=target.id,
        approval_status=ApprovalStatus.APPROVED,
    )
    alignment = SemanticAlignmentRecord(
        id=oid("alignment.even_sum.v1"), created_at=STAMP, created_by=ACTOR,
        problem_id=problem.id, formalization_id=formalization.id, compared_claim_id=target.id,
        quantifier_mapping=(("a", "integer a"), ("b", "integer b")),
        definition_mapping=(("Even(n)", "exists k in Z, n=2k"),),
        assumption_delta=(), edge_case_delta=(), strength_relation=StrengthRelation.EQUIVALENT,
        status=AlignmentStatus.RESEARCHER_APPROVED, approved_by=ACTOR,
    )
    source_applicability = SourceApplicabilityRecord(
        id=oid("applicability.even_definition.v1"), created_at=STAMP, created_by=ACTOR,
        local_claim_id=definition.id, evidence_id=source_evidence.id,
        imported_statement="n is even iff n=2k for some integer k",
        imported_hypotheses=("n is an integer",), definition_mapping=(("even", "same integer definition"),),
        scope_and_exceptions=("integers only",), implication_obligation_id=source_obligation.id,
        bibliographic_status="confirmed", hypothesis_compatibility=Compatibility.COMPATIBLE,
        implication_verified=True, status=ApplicabilityStatus.CHECKED,
    )
    representation = RepresentationMap(
        id=oid("representation.integer_algebra.v1"), created_at=STAMP, created_by=ACTOR,
        source_representation="informal integer arithmetic", target_representation="typed integer algebra",
        encoding_claim_id=encoding.id, preserved_property_claim_ids=(target.id,),
        exceptional_case_claim_ids=(), bridge_obligation_ids=(bridge_obligation.id,),
        status=RepresentationStatus.VERIFIED,
    )
    protocol = EvaluationProtocol(
        id=oid("protocol.manual_slice.v1"), created_at=STAMP, created_by=ACTOR,
        version=1, phase=ProtocolPhase.CONFIRMATORY,
        metrics=("target_fidelity", "trace_completeness"),
        success_criteria=("exact target is policy-projected as proved", "all report claims cite entity IDs"),
        stopping_rules=("one deterministic construction and replay",), frozen_at=STAMP, frozen_by=ACTOR,
    )
    event = AuditEvent(
        id=oid("event.manual_dossier_created.v1"), created_at=STAMP, created_by=ACTOR,
        aggregate_id=problem.id, event_type="manual_dossier_created",
        payload=(("target_claim_id", target.id.value), ("formalization_id", formalization.id.value)),
        idempotency_key="manual-dossier-created-v1",
    )
    return ResearchDossier(
        id=oid("dossier.even_sum.phase1.v1"), created_at=STAMP, created_by=ACTOR,
        problem=problem, formalization=formalization, semantic_alignment=alignment,
        claims=(definition, target, encoding), warrants=(target_warrant, source_warrant, bridge_warrant),
        evidence=(proof_evidence, source_evidence, bridge_evidence),
        source_applicability=(source_applicability,),
        obligations=(proof_obligation, source_obligation, bridge_obligation),
        representation_maps=(representation,),
        verification_records=(target_verification, source_verification, bridge_verification),
        evaluation_protocol=protocol, audit_events=(event,),
        capabilities=("canonical_json", "policy_projection", "append_only_events", "traceable_report"),
    )
