"""Trust projections over immutable Phase 1 records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .entities import (
    AlignmentStatus,
    ApplicabilityStatus,
    Claim,
    ClaimScope,
    Compatibility,
    Disposition,
    ENTITY_SCHEMA_VERSION,
    EvidenceKind,
    ObligationStatus,
    OpaqueId,
    RecordStatus,
    RepresentationStatus,
    ResearchDossier,
    StrengthRelation,
    VerificationOutcome,
    WarrantKind,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TrustProjection:
    schema_version: str
    claim_id: OpaqueId
    semantic_alignment_status: str
    logical_status: str
    warrant_kinds: tuple[str, ...]
    novelty_status: str
    significance_status: str
    contribution_status: str
    blockers: tuple[str, ...]


class TrustPolicy:
    def __init__(self, dossier: ResearchDossier) -> None:
        self.dossier = dossier
        self.claims = {item.id: item for item in dossier.claims}
        self.warrants = {item.id: item for item in dossier.warrants}
        self.evidence = {item.id: item for item in dossier.evidence}
        self.verifications = {item.id: item for item in dossier.verification_records}
        self.obligations = {item.id: item for item in dossier.obligations}
        self.maps = {item.id: item for item in dossier.representation_maps}
        self.applicability = {item.implication_obligation_id: item for item in dossier.source_applicability}

    def _warrant_is_accepted(self, warrant_id: OpaqueId) -> bool:
        warrant = self.warrants[warrant_id]
        if warrant.status is not RecordStatus.ACTIVE or not warrant.evidence_ids:
            return False
        evidence = [self.evidence.get(item_id) for item_id in warrant.evidence_ids]
        if any(
            item is None
            or item.claim_id != warrant.claim_id
            or item.disposition is not Disposition.ACCEPTED
            for item in evidence
        ):
            return False
        records = [self.verifications.get(item_id) for item_id in warrant.verification_record_ids]
        claim = self.claims[warrant.claim_id]
        statement_hash = "sha256:" + hashlib.sha256(
            json.dumps(claim.statement, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).hexdigest()
        if not records or any(
            item is None
            or item.claim_id != warrant.claim_id
            or item.outcome is not VerificationOutcome.PASS
            or item.disposition is not Disposition.ACCEPTED
            or item.target_statement_hash != statement_hash
            or not item.independent_from_proposer
            for item in records
        ):
            return False
        return True

    def _representation_blockers(self, claim: Claim) -> list[str]:
        blockers: list[str] = []
        for map_id in claim.representation_map_ids:
            mapping = self.maps.get(map_id)
            if mapping is None or mapping.status is not RepresentationStatus.VERIFIED:
                blockers.append(f"representation_map_not_verified:{map_id}")
                continue
            for obligation_id in mapping.bridge_obligation_ids:
                obligation = self.obligations.get(obligation_id)
                if obligation is None or obligation.status is not ObligationStatus.DISCHARGED:
                    blockers.append(f"representation_bridge_open:{obligation_id}")
        return blockers

    def _open_obligation_blockers(self, claim_id: OpaqueId) -> list[str]:
        return [
            f"open_obligation:{item.id}"
            for item in self.dossier.obligations
            if item.claim_id == claim_id and item.status in {ObligationStatus.OPEN, ObligationStatus.BLOCKED}
        ]

    def project_claim(self, claim_id: OpaqueId) -> TrustProjection:
        claim = self.claims[claim_id]
        claim_warrants = [item for item in self.dossier.warrants if item.claim_id == claim_id]
        active = [item for item in claim_warrants if self._warrant_is_accepted(item.id)]
        blockers = self._representation_blockers(claim) + self._open_obligation_blockers(claim_id)
        kinds = tuple(sorted({item.kind.value for item in active}))

        logical_status = "unknown"
        if any(item.kind is WarrantKind.EXACT_COUNTEREXAMPLE for item in active):
            logical_status = "disproved"
        elif not blockers and any(
            item.kind in {WarrantKind.FORMAL_PROOF, WarrantKind.RIGOROUS_DERIVATION}
            for item in active
        ):
            logical_status = "proved"
        elif any(
            item.kind in {
                WarrantKind.EXPERIMENTAL_OBSERVATION,
                WarrantKind.SOURCE_REPORT,
                WarrantKind.MODEL_AGREEMENT,
            }
            for item in active
        ):
            logical_status = "supported"

        # Finite experiments and model agreement never prove unrestricted claims.
        if claim.scope is ClaimScope.UNRESTRICTED_UNIVERSAL and logical_status == "proved":
            proof_kinds = {WarrantKind.FORMAL_PROOF, WarrantKind.RIGOROUS_DERIVATION}
            if not any(item.kind in proof_kinds for item in active):
                logical_status = "supported"

        alignment = self.dossier.semantic_alignment
        semantic_status = (
            "approved_equivalent"
            if alignment.compared_claim_id == claim_id
            and alignment.status is AlignmentStatus.RESEARCHER_APPROVED
            and alignment.strength_relation is StrengthRelation.EQUIVALENT
            else "not_approved_equivalent"
        )
        return TrustProjection(
            schema_version=ENTITY_SCHEMA_VERSION,
            claim_id=claim_id,
            semantic_alignment_status=semantic_status,
            logical_status=logical_status,
            warrant_kinds=kinds,
            novelty_status="not_assessed" if claim.novelty_assessment_id is None else "linked",
            significance_status="not_assessed" if claim.significance_assessment_id is None else "linked",
            contribution_status="unattributed" if not claim.contribution_ids else "linked",
            blockers=tuple(sorted(blockers)),
        )

    def target_resolution(self) -> TrustProjection:
        target_id = self.dossier.formalization.target_claim_id
        projection = self.project_claim(target_id)
        alignment = self.dossier.semantic_alignment
        aligned = (
            self.dossier.problem.active_formalization_id == self.dossier.formalization.id
            and alignment.formalization_id == self.dossier.formalization.id
            and alignment.compared_claim_id == target_id
            and alignment.status is AlignmentStatus.RESEARCHER_APPROVED
            and alignment.strength_relation is StrengthRelation.EQUIVALENT
            and not alignment.assumption_delta
            and not alignment.edge_case_delta
        )
        if aligned:
            return projection
        return TrustProjection(
            schema_version=projection.schema_version,
            claim_id=projection.claim_id,
            semantic_alignment_status="not_approved_equivalent",
            logical_status="unknown",
            warrant_kinds=projection.warrant_kinds,
            novelty_status=projection.novelty_status,
            significance_status=projection.significance_status,
            contribution_status=projection.contribution_status,
            blockers=tuple(sorted((*projection.blockers, "semantic_target_not_resolved"))),
        )

    def can_discharge_obligation(self, obligation_id: OpaqueId, supporting_claim_id: OpaqueId) -> tuple[bool, str]:
        obligation = self.obligations[obligation_id]
        supporting_claim = self.claims[supporting_claim_id]
        target_claim = self.claims[obligation.claim_id]
        if (
            obligation.normalized_statement
            and obligation.normalized_statement.strip() == target_claim.statement.strip()
            and supporting_claim.statement.strip() == target_claim.statement.strip()
        ):
            return False, "helper_restates_target"
        if obligation.category == "literature_applicability":
            record = self.applicability.get(obligation_id)
            if record is None:
                return False, "applicability_record_missing"
            if record.status is not ApplicabilityStatus.CHECKED:
                return False, "applicability_not_checked"
            if record.hypothesis_compatibility is not Compatibility.COMPATIBLE:
                return False, "source_hypotheses_incompatible"
            if not record.implication_verified:
                return False, "source_implication_unverified"
        projection = self.project_claim(supporting_claim_id)
        if projection.logical_status not in {"proved", "disproved"}:
            return False, "supporting_claim_not_resolved"
        return True, "policy_allows_discharge"
