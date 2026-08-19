from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from math_research.application.manual_slice import ACTOR, STAMP, build_known_valid_theorem_dossier
from math_research.domain.entities import (
    AlignmentStatus,
    ApplicabilityStatus,
    Claim,
    ClaimOrigin,
    ClaimScope,
    Compatibility,
    Disposition,
    EpistemicWarrant,
    Evidence,
    EvidenceKind,
    ObligationStatus,
    ProofObligation,
    RecordStatus,
    RepresentationStatus,
    StrengthRelation,
    VerificationOutcome,
    VerificationRecord,
    WarrantKind,
    oid,
)
from math_research.domain.policies import TrustPolicy
from math_research.interchange import content_hash

ROOT = Path(__file__).resolve().parents[1]


def _accepted_warrant(claim: Claim, kind: WarrantKind, evidence_kind: EvidenceKind, suffix: str):
    evidence = Evidence(
        id=oid(f"evidence.{suffix}.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=claim.id, kind=evidence_kind, content=suffix,
        artifact_hash=content_hash(suffix), source_ref=None, disposition=Disposition.ACCEPTED,
    )
    verification = VerificationRecord(
        id=oid(f"verification.{suffix}.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=claim.id, verifier_kind=kind.value, outcome=VerificationOutcome.PASS,
        evidence_ids=(evidence.id,), target_statement_hash=content_hash(claim.statement),
        independent_from_proposer=True, disposition=Disposition.ACCEPTED,
    )
    warrant = EpistemicWarrant(
        id=oid(f"warrant.{suffix}.v1"), created_at=STAMP, created_by=ACTOR,
        claim_id=claim.id, kind=kind, scope="test scope", evidence_ids=(evidence.id,),
        verification_record_ids=(verification.id,), status=RecordStatus.ACTIVE,
    )
    return evidence, verification, warrant


def _replace_target_warrant(kind: WarrantKind, evidence_kind: EvidenceKind, suffix: str, *, target_statement: str | None = None):
    dossier = build_known_valid_theorem_dossier()
    target_id = dossier.formalization.target_claim_id
    target = next(item for item in dossier.claims if item.id == target_id)
    if target_statement is not None:
        target = replace(target, statement=target_statement)
        claims = tuple(target if item.id == target_id else item for item in dossier.claims)
    else:
        claims = dossier.claims
    evidence, verification, warrant = _accepted_warrant(target, kind, evidence_kind, suffix)
    obligations = tuple(
        replace(item, status=ObligationStatus.DISCHARGED, discharged_by_warrant_id=warrant.id)
        if item.claim_id == target_id else item
        for item in dossier.obligations
    )
    return replace(
        dossier,
        claims=claims,
        warrants=tuple(item for item in dossier.warrants if item.claim_id != target_id) + (warrant,),
        evidence=tuple(item for item in dossier.evidence if item.claim_id != target_id) + (evidence,),
        verification_records=tuple(item for item in dossier.verification_records if item.claim_id != target_id) + (verification,),
        obligations=obligations,
    )


class TrustBoundaryAdversarialTests(unittest.TestCase):
    def test_model_or_external_system_agreement_cannot_prove_claim(self) -> None:
        dossier = _replace_target_warrant(WarrantKind.MODEL_AGREEMENT, EvidenceKind.MODEL_OUTPUT, "model_agreement")
        self.assertEqual("supported", TrustPolicy(dossier).target_resolution().logical_status)

    def test_finite_experiments_cannot_prove_unrestricted_universal_theorem(self) -> None:
        dossier = _replace_target_warrant(WarrantKind.EXPERIMENTAL_OBSERVATION, EvidenceKind.EXPERIMENT, "finite_experiment")
        target = next(item for item in dossier.claims if item.id == dossier.formalization.target_claim_id)
        self.assertEqual(ClaimScope.UNRESTRICTED_UNIVERSAL, target.scope)
        self.assertEqual("supported", TrustPolicy(dossier).target_resolution().logical_status)

    def test_unresolved_representation_bridge_cannot_support_original_claim(self) -> None:
        fixture = json.loads((ROOT / "fixtures/phase1/representation-bridge-drops-edge-case.json").read_text())
        dossier = build_known_valid_theorem_dossier()
        broken_map = replace(dossier.representation_maps[0], status=RepresentationStatus.PARTIALLY_VERIFIED)
        partial_projection = TrustPolicy(replace(dossier, representation_maps=(broken_map,))).target_resolution()
        self.assertEqual(fixture["expected"]["target_logical_status"], partial_projection.logical_status)
        self.assertTrue(any(item.startswith(fixture["expected"]["blocker_prefix"]) for item in partial_projection.blockers))

        bridge_id = dossier.representation_maps[0].bridge_obligation_ids[0]
        obligations = tuple(
            replace(item, status=ObligationStatus.OPEN, discharged_by_warrant_id=None)
            if item.id == bridge_id else item
            for item in dossier.obligations
        )
        projection = TrustPolicy(replace(dossier, obligations=obligations)).target_resolution()
        self.assertEqual("unknown", projection.logical_status)
        self.assertTrue(any(item.startswith("representation_bridge_open") for item in projection.blockers))

    def test_formal_warrant_for_weakened_target_does_not_resolve_user_target(self) -> None:
        fixture = json.loads((ROOT / "fixtures/phase1/formally-provable-mistranslation.json").read_text())
        dossier = build_known_valid_theorem_dossier()
        weakened = Claim(
            id=oid("claim.even_sum_zero_case.v1"), created_at=STAMP, created_by=ACTOR,
            kind="theorem", statement="When a=0 and b=0, a+b is even.",
            assumption_claim_ids=(), origin=ClaimOrigin.FORMAL_SYSTEM, scope=ClaimScope.PARTICULAR,
        )
        evidence, verification, warrant = _accepted_warrant(weakened, WarrantKind.FORMAL_PROOF, EvidenceKind.FORMAL_ARTIFACT, "weakened_target")
        alignment = replace(
            dossier.semantic_alignment, compared_claim_id=weakened.id,
            strength_relation=StrengthRelation.WEAKER, status=AlignmentStatus.RESEARCHER_APPROVED,
            edge_case_delta=("all nonzero and unequal inputs omitted",),
        )
        candidate = replace(
            dossier, semantic_alignment=alignment, claims=dossier.claims + (weakened,),
            evidence=dossier.evidence + (evidence,), verification_records=dossier.verification_records + (verification,),
            warrants=dossier.warrants + (warrant,),
        )
        policy = TrustPolicy(candidate)
        self.assertEqual(fixture["expected"]["translated_claim_logical_status"], policy.project_claim(weakened.id).logical_status)
        self.assertEqual(fixture["expected"]["target_logical_status"], policy.target_resolution().logical_status)

    def test_real_citation_with_incompatible_hypotheses_cannot_close_obligation(self) -> None:
        fixture = json.loads((ROOT / "fixtures/phase1/real-but-inapplicable-theorem.json").read_text())
        dossier = build_known_valid_theorem_dossier()
        source_obligation = next(item for item in dossier.obligations if item.category == "literature_applicability")
        open_obligation = replace(source_obligation, status=ObligationStatus.OPEN, discharged_by_warrant_id=None)
        record = replace(
            dossier.source_applicability[0], status=ApplicabilityStatus.CHECKED,
            hypothesis_compatibility=Compatibility.INCOMPATIBLE, implication_verified=False,
        )
        obligations = tuple(open_obligation if item.id == source_obligation.id else item for item in dossier.obligations)
        candidate = replace(dossier, obligations=obligations, source_applicability=(record,))
        allowed, reason = TrustPolicy(candidate).can_discharge_obligation(open_obligation.id, open_obligation.claim_id)
        self.assertFalse(allowed)
        self.assertEqual(fixture["expected"]["reason"], reason)

    def test_helper_lemma_that_restates_target_remains_open(self) -> None:
        dossier = build_known_valid_theorem_dossier()
        target = next(item for item in dossier.claims if item.id == dossier.formalization.target_claim_id)
        helper = replace(target, id=oid("claim.helper_restatement.v1"), origin=ClaimOrigin.MODEL)
        evidence, verification, warrant = _accepted_warrant(helper, WarrantKind.RIGOROUS_DERIVATION, EvidenceKind.DERIVATION, "helper_restatement")
        obligation = ProofObligation(
            id=oid("obligation.helper_restatement.v1"), created_at=STAMP, created_by=ACTOR,
            claim_id=target.id, description="Prove the target via a helper with identical content.",
            category="helper_lemma", status=ObligationStatus.OPEN,
            normalized_statement=target.statement,
        )
        candidate = replace(
            dossier, claims=dossier.claims + (helper,), evidence=dossier.evidence + (evidence,),
            verification_records=dossier.verification_records + (verification,), warrants=dossier.warrants + (warrant,),
            obligations=dossier.obligations + (obligation,),
        )
        allowed, reason = TrustPolicy(candidate).can_discharge_obligation(obligation.id, helper.id)
        self.assertFalse(allowed)
        self.assertEqual("helper_restates_target", reason)
        self.assertEqual(ObligationStatus.OPEN, obligation.status)

    def test_exact_counterexample_disproves_false_universal(self) -> None:
        fixture = json.loads((ROOT / "fixtures/phase1/false-universal-exact-counterexample.json").read_text())
        dossier = _replace_target_warrant(
            WarrantKind.EXACT_COUNTEREXAMPLE,
            EvidenceKind.COUNTEREXAMPLE,
            "n_equals_zero",
            target_statement=fixture["target"],
        )
        self.assertEqual(fixture["expected"]["target_logical_status"], TrustPolicy(dossier).target_resolution().logical_status)


if __name__ == "__main__":
    unittest.main()
