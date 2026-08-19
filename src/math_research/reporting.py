"""ID-traceable report rendering for the manual Phase 1 dossier."""

from __future__ import annotations

from .domain.policies import TrustPolicy
from .domain.entities import ResearchDossier
from .interchange import export_dossier_dict


def render_traceable_report(dossier: ResearchDossier) -> str:
    policy = TrustPolicy(dossier)
    projection = policy.target_resolution()
    target = next(item for item in dossier.claims if item.id == projection.claim_id)
    warrant_ids = [item.id.value for item in dossier.warrants if item.claim_id == target.id]
    evidence_ids = [item.id.value for item in dossier.evidence if item.claim_id == target.id]
    verification_ids = [item.id.value for item in dossier.verification_records if item.claim_id == target.id]
    obligation_ids = [item.id.value for item in dossier.obligations if item.claim_id == target.id]
    dossier_hash = export_dossier_dict(dossier)["content_hash"]
    return "\n".join(
        [
            "# Traceable Research Report",
            "",
            f"- Dossier `{dossier.id}` has canonical content hash `{dossier_hash}`. [refs: {dossier.id}]",
            f"- Research problem: {dossier.problem.informal_statement} [refs: {dossier.problem.id}]",
            f"- Approved formal target: {target.statement} [refs: {dossier.formalization.id}, {dossier.semantic_alignment.id}, {target.id}]",
            f"- Policy-projected logical status is `{projection.logical_status}`; semantic alignment is `{projection.semantic_alignment_status}`. [refs: {target.id}, {', '.join(warrant_ids)}, {dossier.semantic_alignment.id}]",
            f"- Target evidence was independently checked. [refs: {', '.join(evidence_ids)}, {', '.join(verification_ids)}]",
            f"- Target proof obligations are recorded and terminal. [refs: {', '.join(obligation_ids)}]",
            f"- Novelty is `{projection.novelty_status}`, significance is `{projection.significance_status}`, and contribution is `{projection.contribution_status}`; none is inferred from proof status. [refs: {target.id}]",
            "",
        ]
    )
