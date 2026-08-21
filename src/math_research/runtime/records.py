"""Append-only records for one iterative session.

Nothing here is a trust record. An ``IterationRecord`` says what was proposed,
what the isolated verifier said about it, and what it cost; it says nothing
about whether the proposal is true. ``LeadSession.epistemic_warrant_created``
is a field rather than a computation precisely so that its unconditional
``False`` is visible in every serialized session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..domain.entities import OpaqueId
from ..novelty import NoveltyRecheckError, classify_prior_art
from . import POLICY_VERSION, SCHEMA_VERSION
from .serialization import canonical_hash


class ValueEnum(str, Enum):
    """String enum with ordering suppressed.

    None of these vocabularies is a scale. An `unresolved` iteration is not
    "less than" a rejected one, and a stop reason is not a grade, so supplying
    a lexicographic order would make meaningless comparisons evaluate to True.
    """

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value

    def __lt__(self, other: object) -> bool:
        raise TypeError(f"{type(self).__name__} is not ordered; compare an explicit permitted set")

    __le__ = __lt__
    __gt__ = __lt__
    __ge__ = __lt__


class TerminalReason(ValueEnum):
    """Why a session stopped. Exactly one applies to a completed session.

    There is no `solved` value, and its absence is the point. The best outcome
    this runtime can reach is `awaiting_human_review`: a proposal the isolated
    verifier did not fault, handed to a person. Nothing here closes a problem.
    """

    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    STAGNATED = "stagnated"
    ITERATIONS_EXHAUSTED = "iterations_exhausted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ITERATION_FAILED = "iteration_failed"
    NO_LIVE_BRANCH = "no_live_branch"


class IterationOutcome(ValueEnum):
    """What one iteration produced."""

    AWAITING_REVIEW = "awaiting_review"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"
    DUPLICATE_HYPOTHESIS = "duplicate_hypothesis"
    ITERATION_BUDGET_EXHAUSTED = "iteration_budget_exhausted"
    PROPOSER_FAILED = "proposer_failed"
    VERIFIER_FAILED = "verifier_failed"


#: Outcomes after which continuing is pointless rather than merely unpromising.
#: A failed model call is terminal here because the Phase 2 job already
#: exhausted its own attempts; retrying above it would double-count a bound.
#: `ITERATION_BUDGET_EXHAUSTED` is kept out of this set because it is not a
#: failure -- the run hit a bound it was given, which is a different fact and
#: gets its own terminal reason so the two are never read as the same event.
TERMINAL_ITERATION_OUTCOMES = frozenset({
    IterationOutcome.AWAITING_REVIEW,
    IterationOutcome.PROPOSER_FAILED,
    IterationOutcome.VERIFIER_FAILED,
})


@dataclass(frozen=True, slots=True, kw_only=True)
class TargetIdentity:
    """The parts of the problem an iterative session may never change.

    Frozen before the first model call and re-derived from the dossier on every
    iteration. This is what makes iteration safe: the lead may try a different
    argument, but it cannot try a different theorem.
    """

    target_claim_id: OpaqueId
    target_statement_hash: str
    formalization_statement_hash: str
    assumption_manifest_hash: str
    semantic_alignment_hash: str
    dossier_hash: str

    def frozen_hash(self) -> str:
        return canonical_hash({
            "assumption_manifest_hash": self.assumption_manifest_hash,
            "dossier_hash": self.dossier_hash,
            "formalization_statement_hash": self.formalization_statement_hash,
            "semantic_alignment_hash": self.semantic_alignment_hash,
            "target_claim_id": self.target_claim_id.value,
            "target_statement_hash": self.target_statement_hash,
        })


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifierFinding:
    """One finding as the isolated verifier reported it. Never a judgement."""

    code: str
    outcome: str


@dataclass(frozen=True, slots=True, kw_only=True)
class IterationUsage:
    """Measured spend for one iteration, read back from the Phase 2 budget."""

    model_calls: int
    input_tokens: int
    output_tokens: int
    cost_microusd: int


@dataclass(frozen=True, slots=True, kw_only=True)
class IterationRecord:
    """One turn: at most one proposer call and at most one verifier call."""

    iteration_index: int
    run_id: OpaqueId
    branch_id: str
    hypothesis_digest: str
    duplicate_of_iteration: int | None
    proposal_id: OpaqueId | None
    proposal_kind: str | None
    proposal_artifact_hash: str | None
    verifier_manifest_hash: str | None
    verifier_recommendation: str | None
    findings: tuple[VerifierFinding, ...]
    outcome: IterationOutcome
    phase2_run_status: str
    usage: IterationUsage
    productive: bool
    content_hash: str = ""

    def with_content_hash(self) -> IterationRecord:
        from dataclasses import replace

        preimage = {
            "branch_id": self.branch_id,
            "duplicate_of_iteration": self.duplicate_of_iteration,
            "findings": [{"code": item.code, "outcome": item.outcome} for item in self.findings],
            "hypothesis_digest": self.hypothesis_digest,
            "iteration_index": self.iteration_index,
            "outcome": self.outcome.value,
            "phase2_run_status": self.phase2_run_status,
            "proposal_artifact_hash": self.proposal_artifact_hash,
            "proposal_kind": self.proposal_kind,
            "productive": self.productive,
            "run_id": self.run_id.value,
            "verifier_manifest_hash": self.verifier_manifest_hash,
            "verifier_recommendation": self.verifier_recommendation,
        }
        return replace(self, content_hash=canonical_hash(preimage))


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionUsage:
    """Session totals. Every field is a sum of measured iteration usage."""

    iterations: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    cost_microusd: int
    elapsed_milliseconds: int


@dataclass(frozen=True, slots=True, kw_only=True)
class LeadSession:
    """The record of one bounded iterative run.

    `epistemic_warrant_created` and `obligations_discharged` are not computed.
    They are constants, asserted on construction, because the runtime has no
    code path that could make them anything else and a reader of the record
    should not have to take that on faith.
    """

    session_id: OpaqueId
    dossier_id: OpaqueId
    target: TargetIdentity
    session_configuration_id: OpaqueId
    session_configuration_hash: str
    iterations: tuple[IterationRecord, ...]
    terminal_reason: TerminalReason
    exhausted_bound: str | None
    usage: SessionUsage
    distinct_hypotheses: int
    started_at: str
    ended_at: str
    novelty_recheck_id: str
    novelty_recheck_hash: str
    prior_art_outcome: str
    prior_art_relationship: str
    prior_resolution: str
    prior_resolution_verification: str
    report_classification: str
    target_resolution_status: str
    epistemic_warrant_created: bool = False
    obligations_discharged: int = 0
    novelty_assessment: str = "not_assessed"
    significance_assessment: str = "not_assessed"
    retention_gain_measured: bool = False
    policy_version: str = POLICY_VERSION
    schema_version: str = SCHEMA_VERSION
    content_hash: str = ""

    def __post_init__(self) -> None:
        if self.epistemic_warrant_created:
            raise ValueError("a runtime session cannot create an epistemic warrant")
        if self.obligations_discharged != 0:
            raise ValueError("a runtime session cannot discharge a proof obligation")
        if self.retention_gain_measured:
            raise ValueError("nothing in this runtime measures retention gain (ADR-0029)")
        try:
            classification = classify_prior_art(
                outcome=self.prior_art_outcome,
                relationship=self.prior_art_relationship,
                prior_resolution=self.prior_resolution,
                verification_status=self.prior_resolution_verification,
            )
        except NoveltyRecheckError as error:
            raise ValueError(f"invalid prior-art classification: {error}") from error
        if (
            self.report_classification != classification.report_classification
            or self.target_resolution_status != classification.target_resolution_status
        ):
            raise ValueError("session prior-art classification is not derived from its source fields")

    def with_content_hash(self) -> LeadSession:
        from dataclasses import replace

        preimage = {
            "dossier_id": self.dossier_id.value,
            "distinct_hypotheses": self.distinct_hypotheses,
            "epistemic_warrant_created": self.epistemic_warrant_created,
            "exhausted_bound": self.exhausted_bound,
            "iterations": [item.content_hash for item in self.iterations],
            "novelty_assessment": self.novelty_assessment,
            "novelty_recheck_hash": self.novelty_recheck_hash,
            "novelty_recheck_id": self.novelty_recheck_id,
            "prior_art_outcome": self.prior_art_outcome,
            "prior_art_relationship": self.prior_art_relationship,
            "prior_resolution": self.prior_resolution,
            "prior_resolution_verification": self.prior_resolution_verification,
            "report_classification": self.report_classification,
            "obligations_discharged": self.obligations_discharged,
            "policy_version": self.policy_version,
            "retention_gain_measured": self.retention_gain_measured,
            "schema_version": self.schema_version,
            "session_configuration_hash": self.session_configuration_hash,
            "session_configuration_id": self.session_configuration_id.value,
            "session_id": self.session_id.value,
            "significance_assessment": self.significance_assessment,
            "target_resolution_status": self.target_resolution_status,
            "target_frozen_hash": self.target.frozen_hash(),
            "terminal_reason": self.terminal_reason.value,
            # Token and cost totals are excluded on purpose: they are true
            # observations of one execution, not part of what the session
            # means, and including them would make an otherwise identical
            # replay hash differently.
            "usage_iterations": self.usage.iterations,
            "usage_model_calls": self.usage.model_calls,
        }
        return replace(self, content_hash=canonical_hash(preimage))
