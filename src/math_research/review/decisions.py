"""Precondition checking for every review decision.

Every function here either returns a `DecisionProposal` whose preconditions have
all been checked, or raises `ReviewRefused` naming exactly the one that failed.
There is no fallback path: a refused `formal_proof` never becomes a
`rigorous_derivation`, and a refused warrant never becomes a weaker warrant.

The trust-critical rule this module enforces is that a warrant traces to a named
human reviewer or to a Phase 3B kernel attestation whose meaning link a named
human approved. A Phase 2 verifier `recommendation` -- including
`manual_review` -- is recorded as an INPUT and is never sufficient on its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..domain.entities import (
    AlignmentStatus,
    ClaimOrigin,
    ObligationStatus,
    OpaqueId,
    ResearchDossier,
    WarrantKind,
)
from ..interchange import export_dossier_dict
from ..phase2.records import RunStatus
from ..phase3b.interchange import validate_finding_dict
from ..phase3b.serialization import semantic_execution_value
from . import (
    FORMAL_KERNEL_WARRANT_KINDS,
    HUMAN_REVIEW_WARRANT_KINDS,
    KERNEL_CHECKED_OUTCOMES,
    MAX_FORMAL_FINDING_BYTES,
    MAX_TEXT_LENGTH,
)
from .ports import ArtifactReader, RunReader
from .records import (
    AlignmentDecision,
    DecisionKind,
    DecisionProposal,
    ReviewVerdict,
    ReviewerIdentity,
    WarrantBasis,
    refuse,
    require_human,
)
from .serialization import canonical_bytes, sha256_bytes, stable_id

VERIFIER_FINDING_KIND = "verifier_finding"

#: Phase 3B flags that must be `false` on an imported finding. The Phase 3B
#: proposal-only contract already forces them; a finding that sets one is
#: attempting to promote its own output and is refused by name.
FINDING_SELF_PROMOTION_FLAGS = (
    "novelty_approved",
    "semantic_alignment_approved",
    "significance_approved",
    "source_applicability_approved",
    "contribution_approved",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RunContext:
    """The Phase 2 run a decision is taken over, plus its committed dossier."""

    run_id: OpaqueId
    status: RunStatus
    dossier: ResearchDossier
    dossier_hash: str
    proposal_source_ids: tuple[str, ...]

    @property
    def target_claim_id(self) -> OpaqueId:
        return self.dossier.formalization.target_claim_id


def _bounded_text(value: str, *, field: str, subject_id: str) -> str:
    if len(value.encode("utf-8")) > MAX_TEXT_LENGTH:
        raise refuse(
            "text_too_long",
            subject_id=subject_id,
            unmet_precondition=f"{field} is at most {MAX_TEXT_LENGTH} UTF-8 bytes",
            detail=f"{field} is {len(value.encode('utf-8'))} bytes",
        )
    return value


def load_run_context(runs: RunReader, run_id: OpaqueId) -> RunContext:
    try:
        run = runs.get_run(run_id)
    except KeyError as error:
        raise refuse(
            "run_not_found",
            subject_id=run_id.value,
            unmet_precondition="the run exists in the Phase 2 durable workspace",
            detail=f"no run {run_id.value} in this workspace",
        ) from error
    dossier = runs.load_dossier(run.dossier_id)
    observed = export_dossier_dict(dossier)["content_hash"]
    if observed != run.dossier_hash:
        raise refuse(
            "dossier_hash_mismatch",
            subject_id=run_id.value,
            unmet_precondition="the stored dossier re-hashes to the hash the run recorded",
            detail=f"run records {run.dossier_hash} but the stored dossier hashes to {observed}",
        )
    return RunContext(
        run_id=run_id,
        status=run.status,
        dossier=dossier,
        dossier_hash=observed,
        proposal_source_ids=tuple(
            sorted({item.source_id for item in runs.list_proposals(run_id)})
        ),
    )


def _reject_proposal_source(context: RunContext, reviewer: ReviewerIdentity) -> None:
    """Separation of duty: the principal that produced a proposal cannot review it."""

    if reviewer.id.value in context.proposal_source_ids:
        raise refuse(
            "reviewer_is_proposal_source",
            subject_id=context.run_id.value,
            unmet_precondition="the reviewer did not produce a proposal on this run",
            detail=(
                f"{reviewer.id.value} is a recorded proposal source on run "
                f"{context.run_id.value}; a proposer cannot review its own output"
            ),
        )


def read_verifier_finding(
    runs: RunReader, artifacts: ArtifactReader, context: RunContext
) -> dict[str, Any]:
    """Load the committed Phase 2 verifier finding for a run.

    The finding is the review INPUT. Its `recommendation` field is carried into
    the decision payload verbatim and is never read as a verdict.
    """

    candidates = [
        item
        for item in runs.list_proposals(context.run_id)
        if item.proposal_kind == VERIFIER_FINDING_KIND
    ]
    if not candidates:
        raise refuse(
            "verifier_finding_missing",
            subject_id=context.run_id.value,
            unmet_precondition="the run committed exactly one verifier finding proposal",
            detail=f"run {context.run_id.value} has no committed {VERIFIER_FINDING_KIND} proposal",
        )
    if len(candidates) > 1:
        raise refuse(
            "verifier_finding_ambiguous",
            subject_id=context.run_id.value,
            unmet_precondition="the run committed exactly one verifier finding proposal",
            detail=f"run {context.run_id.value} has {len(candidates)} verifier findings",
        )
    proposal = candidates[0]
    if not artifacts.exists(proposal.artifact_hash):
        raise refuse(
            "verifier_finding_artifact_missing",
            subject_id=context.run_id.value,
            unmet_precondition="the committed finding artifact is present in the artifact store",
            detail=f"artifact {proposal.artifact_hash} is not in the store",
        )
    data = artifacts.get(proposal.artifact_hash)
    if sha256_bytes(data) != proposal.artifact_hash:
        raise refuse(
            "verifier_finding_artifact_corrupt",
            subject_id=context.run_id.value,
            unmet_precondition="the finding artifact re-hashes to its recorded content hash",
            detail=f"artifact bytes do not hash to {proposal.artifact_hash}",
        )
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise refuse(
            "verifier_finding_unreadable",
            subject_id=context.run_id.value,
            unmet_precondition="the finding artifact is UTF-8 canonical JSON",
            detail=str(error),
        ) from error
    if not isinstance(value, dict) or canonical_bytes(value) != data:
        raise refuse(
            "verifier_finding_not_canonical",
            subject_id=context.run_id.value,
            unmet_precondition="the finding artifact is byte-canonical JSON",
            detail="artifact bytes are not the canonical encoding of their own content",
        )
    if value.get("target_claim_id") != context.target_claim_id.value:
        raise refuse(
            "verifier_finding_target_mismatch",
            subject_id=context.run_id.value,
            unmet_precondition="the finding names the dossier's formalization target claim",
            detail=(
                f"finding names {value.get('target_claim_id')!r} but the dossier target is "
                f"{context.target_claim_id.value!r}"
            ),
        )
    return {
        "artifact_hash": proposal.artifact_hash,
        "proposal_id": proposal.proposal_id.value,
        "source_id": proposal.source_id,
        "source_kind": proposal.source_kind,
        "finding": value,
    }


# ---------------------------------------------------------------------------
# 1. Review verdict over a Phase 2 run awaiting review.
# ---------------------------------------------------------------------------

def build_review_verdict(
    *,
    runs: RunReader,
    artifacts: ArtifactReader,
    run_id: OpaqueId,
    reviewer: ReviewerIdentity,
    verdict: ReviewVerdict,
    independently_checked: bool,
    rationale: str,
) -> tuple[DecisionProposal, dict[str, Any]]:
    context = load_run_context(runs, run_id)
    require_human(reviewer, subject_id=run_id.value)
    _reject_proposal_source(context, reviewer)
    _bounded_text(rationale, field="rationale", subject_id=run_id.value)
    if not rationale.strip():
        raise refuse(
            "rationale_missing",
            subject_id=run_id.value,
            unmet_precondition="the reviewer supplies a non-empty rationale",
            detail="a review verdict without a rationale is not reviewable evidence",
        )
    if context.status is not RunStatus.AWAITING_REVIEW:
        raise refuse(
            "run_not_awaiting_review",
            subject_id=run_id.value,
            unmet_precondition="the run status is awaiting_review",
            detail=f"run {run_id.value} is {context.status.value}",
        )
    loaded = read_verifier_finding(runs, artifacts, context)
    if verdict is ReviewVerdict.ACCEPT_CANDIDATE and not independently_checked:
        # The single most important gate in this slice. Accepting a candidate
        # requires the reviewer to attest an independent check; the model's own
        # `manual_review` recommendation cannot stand in for it.
        raise refuse(
            "independent_check_not_attested",
            subject_id=run_id.value,
            unmet_precondition=(
                "accepting a candidate requires an explicit independent-check attestation "
                "from the reviewer"
            ),
            detail=(
                "the verifier finding recommends "
                f"{loaded['finding'].get('recommendation')!r}; a model recommendation is an input "
                "to review, never a substitute for it"
            ),
        )
    payload = {
        "candidate_artifact_hash": loaded["finding"].get("candidate_artifact_hash"),
        "dossier_hash": context.dossier_hash,
        "dossier_id": context.dossier.id.value,
        "independently_checked": independently_checked,
        "rationale": rationale,
        "run_id": run_id.value,
        "run_status_at_review": context.status.value,
        "target_claim_id": context.target_claim_id.value,
        "verdict": verdict.value,
        "verifier_finding_artifact_hash": loaded["artifact_hash"],
        "verifier_finding_proposal_id": loaded["proposal_id"],
        # Recorded as an input, never as a verdict.
        "verifier_recommendation": loaded["finding"].get("recommendation"),
        "verifier_source_id": loaded["source_id"],
        "verifier_source_kind": loaded["source_kind"],
    }
    proposal = DecisionProposal(
        decision_kind=DecisionKind.REVIEW_VERDICT,
        subject_id=run_id.value,
        reviewer=reviewer,
        idempotency_key=f"review-verdict:{run_id.value}:{reviewer.id.value}",
        payload=payload,
    )
    return proposal, loaded


# ---------------------------------------------------------------------------
# 2. Semantic alignment approval or rejection.
# ---------------------------------------------------------------------------

def build_alignment_decision(
    *,
    runs: RunReader,
    run_id: OpaqueId,
    alignment_id: OpaqueId,
    approver: ReviewerIdentity,
    decision: AlignmentDecision,
    rationale: str,
) -> DecisionProposal:
    context = load_run_context(runs, run_id)
    require_human(approver, subject_id=alignment_id.value)
    _bounded_text(rationale, field="rationale", subject_id=alignment_id.value)
    if not rationale.strip():
        raise refuse(
            "rationale_missing",
            subject_id=alignment_id.value,
            unmet_precondition="the approver supplies a non-empty rationale",
            detail="approving a target interpretation without a stated reason is not review",
        )
    alignment = context.dossier.semantic_alignment
    if alignment.id != alignment_id:
        raise refuse(
            "alignment_not_found",
            subject_id=alignment_id.value,
            unmet_precondition="the named alignment record belongs to this run's dossier",
            detail=(
                f"dossier {context.dossier.id.value} carries alignment {alignment.id.value}, "
                f"not {alignment_id.value}"
            ),
        )
    if alignment.status is not AlignmentStatus.PROPOSED:
        raise refuse(
            "alignment_already_decided",
            subject_id=alignment_id.value,
            unmet_precondition="the alignment record is still `proposed`",
            detail=(
                f"alignment {alignment_id.value} is {alignment.status.value}; superseded state is "
                "marked, never overwritten, so a new formalization is required instead"
            ),
        )
    formalization = context.dossier.formalization
    # Measured, not declared: whether this approval is enough for
    # `TrustPolicy.target_resolution` to resolve the target.
    resolves_target = (
        alignment.compared_claim_id == formalization.target_claim_id
        and alignment.formalization_id == formalization.id
        and context.dossier.problem.active_formalization_id == formalization.id
        and alignment.strength_relation.value == "equivalent"
        and not alignment.assumption_delta
        and not alignment.edge_case_delta
    )
    payload = {
        "alignment_id": alignment_id.value,
        "assumption_delta_count": len(alignment.assumption_delta),
        "compared_claim_id": alignment.compared_claim_id.value,
        "decision": decision.value,
        "dossier_hash": context.dossier_hash,
        "dossier_id": context.dossier.id.value,
        "edge_case_delta_count": len(alignment.edge_case_delta),
        "formalization_id": alignment.formalization_id.value,
        "prior_status": alignment.status.value,
        "rationale": rationale,
        "resolves_target_under_trust_policy": resolves_target,
        "run_id": run_id.value,
        "strength_relation": alignment.strength_relation.value,
    }
    return DecisionProposal(
        decision_kind=DecisionKind.SEMANTIC_ALIGNMENT_DECISION,
        subject_id=alignment_id.value,
        reviewer=approver,
        idempotency_key=(
            f"alignment-decision:{alignment_id.value}:{context.dossier_hash}:{approver.id.value}"
        ),
        payload=payload,
    )


def approved_alignment(
    decisions: tuple[Mapping[str, Any], ...], context: RunContext
) -> Mapping[str, Any] | None:
    """The alignment approval, if any, that covers this exact dossier."""

    alignment_id = context.dossier.semantic_alignment.id.value
    for record in decisions:
        if record.get("decision_kind") != DecisionKind.SEMANTIC_ALIGNMENT_DECISION.value:
            continue
        payload = record.get("payload", {})
        if (
            payload.get("alignment_id") == alignment_id
            and payload.get("decision") == AlignmentDecision.APPROVE.value
            and payload.get("dossier_hash") == context.dossier_hash
        ):
            return record
    return None


def _require_approved_alignment(
    decisions: tuple[Mapping[str, Any], ...], context: RunContext, *, subject_id: str
) -> Mapping[str, Any]:
    record = approved_alignment(decisions, context)
    if record is None:
        raise refuse(
            "semantic_alignment_not_approved",
            subject_id=subject_id,
            unmet_precondition=(
                "a named human approved the semantic alignment record for this exact dossier"
            ),
            detail=(
                f"no approve decision for alignment "
                f"{context.dossier.semantic_alignment.id.value} at dossier hash "
                f"{context.dossier_hash}; a formal result about a formalization is not a result "
                "about the informal problem until the meaning link is approved"
            ),
        )
    return record


# ---------------------------------------------------------------------------
# 3. Warrant granting. The trust-critical surface.
# ---------------------------------------------------------------------------

def _require_claim(context: RunContext, claim_id: OpaqueId) -> None:
    if claim_id not in {item.id for item in context.dossier.claims}:
        raise refuse(
            "claim_not_in_dossier",
            subject_id=claim_id.value,
            unmet_precondition="the warranted claim exists in the run's dossier",
            detail=f"dossier {context.dossier.id.value} carries no claim {claim_id.value}",
        )


def _check_basis_supports_kind(basis: WarrantBasis, kind: WarrantKind, *, subject_id: str) -> None:
    if basis is WarrantBasis.HUMAN_REVIEW:
        if kind.value in HUMAN_REVIEW_WARRANT_KINDS:
            return
        if kind is WarrantKind.FORMAL_PROOF:
            raise refuse(
                "formal_proof_requires_kernel_attestation",
                subject_id=subject_id,
                unmet_precondition="a formal_proof warrant is backed by a kernel attestation",
                detail=(
                    "human review of a model candidate is not a kernel check; supply a Phase 3B "
                    "kernel_checked finding instead. No weaker warrant kind is granted as a fallback"
                ),
            )
        if kind is WarrantKind.SOURCE_REPORT:
            raise refuse(
                "source_report_requires_source_applicability_record",
                subject_id=subject_id,
                unmet_precondition=(
                    "a source_report warrant is backed by a checked SourceApplicabilityRecord"
                ),
                detail=(
                    "this slice creates no applicability records; ADR-0039 defers source-backed "
                    "claims to the Phase 4A/4B acquisition path"
                ),
            )
        raise refuse(
            "warrant_kind_not_reviewable",
            subject_id=subject_id,
            unmet_precondition=(
                "the warrant kind is one this review surface can license: "
                + ", ".join(HUMAN_REVIEW_WARRANT_KINDS)
            ),
            detail=(
                f"{kind.value} is not licensable by human review; model_agreement in particular "
                "measures nothing this slice measures"
            ),
        )
    if kind.value not in FORMAL_KERNEL_WARRANT_KINDS:
        raise refuse(
            "warrant_kind_not_supported_by_kernel_basis",
            subject_id=subject_id,
            unmet_precondition=(
                "a kernel attestation licenses exactly: " + ", ".join(FORMAL_KERNEL_WARRANT_KINDS)
            ),
            detail=f"a Phase 3B kernel check cannot license a {kind.value} warrant",
        )


def _supporting_verdict(
    decisions: tuple[Mapping[str, Any], ...], context: RunContext, claim_id: OpaqueId
) -> Mapping[str, Any]:
    verdicts = [
        item
        for item in decisions
        if item.get("decision_kind") == DecisionKind.REVIEW_VERDICT.value
        and item.get("payload", {}).get("run_id") == context.run_id.value
        and item.get("payload", {}).get("dossier_hash") == context.dossier_hash
    ]
    if not verdicts:
        raise refuse(
            "supporting_review_verdict_missing",
            subject_id=claim_id.value,
            unmet_precondition="a recorded human review verdict covers this run and dossier",
            detail=(
                f"no review verdict for run {context.run_id.value} at dossier hash "
                f"{context.dossier_hash}"
            ),
        )
    accepting = [
        item
        for item in verdicts
        if item["payload"].get("verdict") == ReviewVerdict.ACCEPT_CANDIDATE.value
    ]
    if not accepting:
        raise refuse(
            "supporting_review_verdict_not_accepting",
            subject_id=claim_id.value,
            unmet_precondition="the recorded verdict is accept_candidate",
            detail=(
                "recorded verdicts are "
                + ", ".join(sorted(item["payload"]["verdict"] for item in verdicts))
            ),
        )
    attested = [item for item in accepting if item["payload"].get("independently_checked") is True]
    if not attested:
        raise refuse(
            "independent_check_not_attested",
            subject_id=claim_id.value,
            unmet_precondition="the accepting verdict attests an independent check",
            detail="no accepting verdict on this run records independently_checked = true",
        )
    for item in attested:
        if item["payload"].get("target_claim_id") != claim_id.value:
            continue
        return item
    raise refuse(
        "supporting_verdict_claim_mismatch",
        subject_id=claim_id.value,
        unmet_precondition="the accepting verdict covers the claim being warranted",
        detail=(
            "the attested verdicts cover "
            + ", ".join(sorted(str(item["payload"].get("target_claim_id")) for item in attested))
        ),
    )


def build_human_review_warrant(
    *,
    runs: RunReader,
    journal_decisions: tuple[Mapping[str, Any], ...],
    run_id: OpaqueId,
    claim_id: OpaqueId,
    kind: WarrantKind,
    scope: str,
    grantor: ReviewerIdentity,
) -> DecisionProposal:
    context = load_run_context(runs, run_id)
    require_human(grantor, subject_id=claim_id.value)
    _reject_proposal_source(context, grantor)
    _bounded_text(scope, field="scope", subject_id=claim_id.value)
    if not scope.strip():
        raise refuse(
            "warrant_scope_missing",
            subject_id=claim_id.value,
            unmet_precondition="the grantor states the warrant scope",
            detail="an unscoped warrant asserts more than any reviewer checked",
        )
    _require_claim(context, claim_id)
    _check_basis_supports_kind(WarrantBasis.HUMAN_REVIEW, kind, subject_id=claim_id.value)
    verdict = _supporting_verdict(journal_decisions, context, claim_id)
    _require_approved_alignment(journal_decisions, context, subject_id=claim_id.value)
    payload = {
        "basis": WarrantBasis.HUMAN_REVIEW.value,
        "claim_id": claim_id.value,
        "dossier_hash": context.dossier_hash,
        "dossier_id": context.dossier.id.value,
        "evidence_kind": "model_output",
        "kind": kind.value,
        "run_id": run_id.value,
        "scope": scope,
        "supporting_decision_ids": [verdict["decision_id"]],
        "verifier_finding_artifact_hash": verdict["payload"]["verifier_finding_artifact_hash"],
        "verifier_kind": "human_review",
    }
    warrant_id = "warrant." + stable_id("review", payload).split(".", 1)[1]
    return DecisionProposal(
        decision_kind=DecisionKind.WARRANT_GRANT,
        subject_id=claim_id.value,
        reviewer=grantor,
        idempotency_key=f"warrant-grant:{claim_id.value}:{warrant_id}",
        payload={**payload, "warrant_id": warrant_id},
    )


def _parse_formal_finding(data: bytes, *, subject_id: str) -> dict[str, Any]:
    if len(data) > MAX_FORMAL_FINDING_BYTES:
        raise refuse(
            "formal_finding_too_large",
            subject_id=subject_id,
            unmet_precondition=f"the finding document is at most {MAX_FORMAL_FINDING_BYTES} bytes",
            detail=f"the supplied document is {len(data)} bytes",
        )
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise refuse(
            "formal_finding_unreadable",
            subject_id=subject_id,
            unmet_precondition="the formal-check finding is UTF-8 JSON",
            detail=str(error),
        ) from error
    if not isinstance(value, dict):
        raise refuse(
            "formal_finding_unreadable",
            subject_id=subject_id,
            unmet_precondition="the formal-check finding is a JSON object",
            detail=f"top-level value is {type(value).__name__}",
        )
    return value


def build_kernel_warrant(
    *,
    runs: RunReader,
    journal_decisions: tuple[Mapping[str, Any], ...],
    run_id: OpaqueId,
    finding_bytes: bytes,
    kind: WarrantKind,
    scope: str,
    grantor: ReviewerIdentity,
) -> DecisionProposal:
    """Grant a warrant from a Phase 3B `kernel_checked` formal-check finding.

    The finding's own gating booleans are honoured rather than replaced. All six
    are `false` by the Phase 3B proposal-only contract, and each `false` is read
    for what it says: the kernel created no warrant, approved no meaning link,
    and approved no source applicability. So the kernel supplies the derivation
    and a named human must still have supplied the meaning approval.
    """

    context = load_run_context(runs, run_id)
    require_human(grantor, subject_id=run_id.value)
    _bounded_text(scope, field="scope", subject_id=run_id.value)
    if not scope.strip():
        raise refuse(
            "warrant_scope_missing",
            subject_id=run_id.value,
            unmet_precondition="the grantor states the warrant scope",
            detail="an unscoped warrant asserts more than the kernel checked",
        )
    _check_basis_supports_kind(WarrantBasis.FORMAL_KERNEL, kind, subject_id=run_id.value)
    finding = _parse_formal_finding(finding_bytes, subject_id=run_id.value)

    # Gate order matters: the self-promotion flags are checked before the
    # Phase 3B validator so that a finding claiming its own warrant is refused by
    # that name rather than as a generic contract violation.
    if finding.get("epistemic_warrant_created") is not False:
        raise refuse(
            "finding_claims_self_granted_warrant",
            subject_id=run_id.value,
            unmet_precondition="the finding records epistemic_warrant_created = false",
            detail=(
                "the finding asserts it created its own warrant; a tool cannot grant itself trust, "
                "so the document is refused rather than honoured"
            ),
        )
    for flag in FINDING_SELF_PROMOTION_FLAGS:
        if finding.get(flag) is not False:
            raise refuse(
                "finding_claims_unapproved_promotion",
                subject_id=run_id.value,
                unmet_precondition=f"the finding records {flag} = false",
                detail=f"the finding sets {flag}={finding.get(flag)!r}, which only a reviewer may set",
            )
    if finding.get("disposition") != "proposal" or finding.get("trust_effect") != "none":
        raise refuse(
            "finding_violates_proposal_contract",
            subject_id=run_id.value,
            unmet_precondition="the finding is disposition 'proposal' with trust_effect 'none'",
            detail=(
                f"disposition={finding.get('disposition')!r}, "
                f"trust_effect={finding.get('trust_effect')!r}"
            ),
        )
    try:
        validate_finding_dict(finding)
    except ValueError as error:
        raise refuse(
            "formal_finding_invalid",
            subject_id=run_id.value,
            unmet_precondition="the finding satisfies the Phase 3B replay contract",
            detail=str(error),
        ) from error

    outcome = finding.get("outcome")
    if outcome not in KERNEL_CHECKED_OUTCOMES:
        raise refuse(
            "formal_check_outcome_not_kernel_checked",
            subject_id=run_id.value,
            unmet_precondition=(
                "the finding outcome is one of: " + ", ".join(KERNEL_CHECKED_OUTCOMES)
            ),
            detail=f"the finding outcome is {outcome!r}, which is not a kernel attestation",
        )
    if finding.get("unapproved_assumptions"):
        raise refuse(
            "formal_check_unapproved_assumptions",
            subject_id=run_id.value,
            unmet_precondition="the finding lists no unapproved assumptions",
            detail=f"unapproved assumptions: {finding['unapproved_assumptions']}",
        )
    if finding.get("exact_statement_only") is not True:
        raise refuse(
            "formal_check_not_exact_statement_only",
            subject_id=run_id.value,
            unmet_precondition="the finding records exact_statement_only = true",
            detail="the kernel result does not cover the exact statement",
        )

    claim_id_text = finding.get("claim_id")
    if claim_id_text != context.target_claim_id.value:
        raise refuse(
            "formal_finding_claim_mismatch",
            subject_id=run_id.value,
            unmet_precondition="the finding's claim is this dossier's formalization target",
            detail=(
                f"the finding checked {claim_id_text!r}; the dossier target is "
                f"{context.target_claim_id.value!r}"
            ),
        )
    alignment_id = finding.get("semantic_alignment_id")
    if alignment_id is None:
        raise refuse(
            "formal_finding_has_no_semantic_alignment",
            subject_id=run_id.value,
            unmet_precondition="the finding names the semantic alignment record it was checked under",
            detail="semantic_alignment_id is null, so nothing links the formal target to the problem",
        )
    if alignment_id != context.dossier.semantic_alignment.id.value:
        raise refuse(
            "formal_finding_alignment_mismatch",
            subject_id=run_id.value,
            unmet_precondition="the finding's alignment record is the dossier's alignment record",
            detail=(
                f"the finding names {alignment_id!r}; the dossier carries "
                f"{context.dossier.semantic_alignment.id.value!r}"
            ),
        )

    # `source_applicability_approved` is false on every Phase 3B finding. That is
    # only harmless while no premise of the target claim came from a source.
    claims = {item.id: item for item in context.dossier.claims}
    target = claims[context.target_claim_id]
    source_premises = sorted(
        item.value
        for item in target.assumption_claim_ids
        if item in claims and claims[item].origin is ClaimOrigin.SOURCE
    )
    if source_premises:
        raise refuse(
            "source_applicability_not_approved",
            subject_id=run_id.value,
            unmet_precondition=(
                "no premise of the target claim has ClaimOrigin.SOURCE while the finding records "
                "source_applicability_approved = false"
            ),
            detail=(
                "source-origin premises need a checked SourceApplicabilityRecord: "
                + ", ".join(source_premises)
            ),
        )
    _require_approved_alignment(journal_decisions, context, subject_id=run_id.value)

    # The finding's `created_at` and `elapsed_milliseconds` are operational: they
    # move without changing what the kernel checked. They are retained under
    # `operational`, which the semantic record hash strips, so re-running the same
    # check at a different instant does not change the decision's identity or the
    # successor dossier's content hash.
    semantic_finding, operational = split_formal_finding(finding)
    payload = {
        "basis": WarrantBasis.FORMAL_KERNEL.value,
        "claim_id": context.target_claim_id.value,
        "dossier_hash": context.dossier_hash,
        "dossier_id": context.dossier.id.value,
        "evidence_kind": "formal_artifact",
        "formal_finding_content_hash": finding.get("content_hash"),
        "formal_finding_id": finding.get("id"),
        "formal_finding_outcome": outcome,
        "formal_finding_semantic_alignment_id": alignment_id,
        "formal_finding_semantic_json": canonical_bytes(semantic_finding).decode("utf-8"),
        "formal_target_hash": (finding.get("wrapper_manifest") or {}).get("target_hash"),
        "kind": kind.value,
        "run_id": run_id.value,
        "scope": scope,
        "supporting_decision_ids": [],
        "verifier_kind": "lean_kernel_phase3b",
    }
    warrant_id = "warrant." + stable_id("kernel", payload).split(".", 1)[1]
    return DecisionProposal(
        decision_kind=DecisionKind.WARRANT_GRANT,
        subject_id=context.target_claim_id.value,
        reviewer=grantor,
        idempotency_key=f"warrant-grant:{context.target_claim_id.value}:{warrant_id}",
        payload={**payload, "warrant_id": warrant_id, "operational": operational},
    )


def split_formal_finding(finding: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a Phase 3B finding into its semantic content and its observations.

    Phase 3B's own `finding_content_hash` excludes `created_at` and, for a
    bounded run, `elapsed_milliseconds`. This mirrors that split rather than
    inventing a second convention, and keeps the finding's real `content_hash`
    inside the semantic projection so the stored evidence is self-describing.
    """

    semantic = dict(finding)
    operational: dict[str, Any] = {
        "formal_finding_created_at": finding.get("created_at"),
        "formal_finding_elapsed_milliseconds": None,
    }
    semantic.pop("created_at", None)
    execution = semantic.get("execution")
    if isinstance(execution, dict):
        operational["formal_finding_elapsed_milliseconds"] = execution.get(
            "elapsed_milliseconds"
        )
        semantic["execution"] = semantic_execution_value(execution)
    return semantic, operational


# ---------------------------------------------------------------------------
# 4. Obligation discharge.
# ---------------------------------------------------------------------------

def granted_warrants(
    decisions: tuple[Mapping[str, Any], ...], context: RunContext
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in decisions:
        if record.get("decision_kind") != DecisionKind.WARRANT_GRANT.value:
            continue
        payload = record.get("payload", {})
        if payload.get("dossier_hash") != context.dossier_hash:
            continue
        result[str(payload.get("warrant_id"))] = record
    return result


def build_obligation_discharge(
    *,
    runs: RunReader,
    journal_decisions: tuple[Mapping[str, Any], ...],
    run_id: OpaqueId,
    obligation_id: OpaqueId,
    warrant_id: str,
    reviewer: ReviewerIdentity,
    rationale: str,
) -> DecisionProposal:
    context = load_run_context(runs, run_id)
    require_human(reviewer, subject_id=obligation_id.value)
    _bounded_text(rationale, field="rationale", subject_id=obligation_id.value)
    obligations = {item.id: item for item in context.dossier.obligations}
    if obligation_id not in obligations:
        raise refuse(
            "obligation_not_found",
            subject_id=obligation_id.value,
            unmet_precondition="the obligation exists in the run's dossier",
            detail=f"dossier {context.dossier.id.value} carries no obligation {obligation_id.value}",
        )
    obligation = obligations[obligation_id]
    if obligation.status is not ObligationStatus.OPEN:
        raise refuse(
            "obligation_not_open",
            subject_id=obligation_id.value,
            unmet_precondition="the obligation is open",
            detail=f"obligation {obligation_id.value} is {obligation.status.value}",
        )
    warrants = granted_warrants(journal_decisions, context)
    if warrant_id not in warrants:
        raise refuse(
            "warrant_not_found",
            subject_id=obligation_id.value,
            unmet_precondition=(
                "discharged_by_warrant_id names a warrant this journal actually granted "
                "for this dossier"
            ),
            detail=(
                f"no granted warrant {warrant_id!r} at dossier hash {context.dossier_hash}; "
                "granted warrants are "
                + (", ".join(sorted(warrants)) if warrants else "(none)")
            ),
        )
    grant = warrants[warrant_id]
    if grant["payload"].get("claim_id") != obligation.claim_id.value:
        raise refuse(
            "warrant_does_not_cover_obligation_claim",
            subject_id=obligation_id.value,
            unmet_precondition="the warrant covers the obligation's claim",
            detail=(
                f"warrant {warrant_id} covers {grant['payload'].get('claim_id')!r} but the "
                f"obligation is about {obligation.claim_id.value!r}"
            ),
        )
    if obligation.category == "literature_applicability":
        raise refuse(
            "obligation_category_requires_applicability_record",
            subject_id=obligation_id.value,
            unmet_precondition=(
                "a literature_applicability obligation is discharged against a checked "
                "SourceApplicabilityRecord"
            ),
            detail=(
                "TrustPolicy.can_discharge_obligation requires a checked applicability record; "
                "this slice creates none"
            ),
        )
    if obligation.category == "semantic_alignment":
        _require_approved_alignment(
            journal_decisions, context, subject_id=obligation_id.value
        )
    payload = {
        "claim_id": obligation.claim_id.value,
        "discharged_by_warrant_id": warrant_id,
        "dossier_hash": context.dossier_hash,
        "dossier_id": context.dossier.id.value,
        "obligation_category": obligation.category,
        "obligation_id": obligation_id.value,
        "prior_status": obligation.status.value,
        "rationale": rationale,
        "run_id": run_id.value,
        "warrant_grant_decision_id": grant["decision_id"],
    }
    return DecisionProposal(
        decision_kind=DecisionKind.OBLIGATION_DISCHARGE,
        subject_id=obligation_id.value,
        reviewer=reviewer,
        idempotency_key=f"obligation-discharge:{obligation_id.value}:{warrant_id}",
        payload=payload,
    )
