"""The bounded Phase 2 proposer/verifier workflow.

ADR-0007 gave this loop exactly one proposer call and one verifier call. ADR-0041
extends it to a *bounded* number of rounds: when the round-N verifier returns a
refuting or defective finding, round N+1's proposer is shown that finding and
asked for a revised candidate. The number of rounds is declared per run in
`BudgetLimits.max_refinement_rounds` and enforced durably; exhausting it is the
named terminal state `RunStatus.REFINEMENT_EXHAUSTED`, which is neither a
success nor a crash.

Three properties the extension must not break, and does not:

* Nothing here creates trust. Every round still produces proposals only.
* Round N+1's verifier gains no material the independence policy excludes.
  Prior findings go to the proposer, never to the verifier, and each round
  records its own `VerifierContextManifest` so the isolation of that round is
  separately auditable. What multi-round *does* cost is causal independence:
  the candidate the round-2 verifier reviews was shaped by the round-1
  verifier's own output. That is recorded in the manifest, not hidden.
* Identity is round-indexed, so a crash mid-round followed by replay cannot
  double-commit and cannot collide with the previous round.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from ..domain.entities import Disposition, Entity, OpaqueId, ResearchDossier
from ..interchange import export_dossier_dict
from . import PHASE2_SCHEMA_VERSION
from .independence import measure_context_isolation, measure_role_independence
from .model_gateway import StructuredOutputError, validate_structured_output
from .openai_schema import ProviderSchemaError
from .ports import ArtifactStore, DurableWorkspace, ModelGateway
from .pricing import estimate_cost_microusd
from .prompt_templates import PromptCatalog
from .records import (
    BudgetLimits,
    CostEstimate,
    JobStatus,
    ModelRequest,
    ModelResult,
    ModelResultStatus,
    PricingSnapshot,
    ProposalRecord,
    RefinementOutcomeClass,
    RefinementRoundRecord,
    RunRecord,
    RunStatus,
    RunStopReason,
    RunStopRecord,
    VerifierContextManifest,
    VerifierIndependence,
)
from .serialization import canonical_bytes, canonical_hash, canonical_json, public_value, sha256_bytes
from .sqlite_workspace import BudgetExhausted, LateCommitRejected, RefinementRoundsExhausted


POLICY_VERSION = "phase1-trust-policy-v1"

#: Terminal run statuses. `run_to_terminal` stops on any of them.
TERMINAL_RUN_STATUSES = frozenset({
    RunStatus.AWAITING_REVIEW,
    RunStatus.UNRESOLVED,
    RunStatus.CANCELLED,
    RunStatus.COMPLETED,
    RunStatus.PAUSED,
    RunStatus.REFINEMENT_EXHAUSTED,
})

#: Order in which a binding budget dimension is named. Cost first: an operator
#: who set a money cap wants to be told the money ran out, not that a round
#: counter did.
_BOUND_ORDER = ("cost", "input_tokens", "output_tokens", "attempts", "time")

#: Model calls one further round would need: one proposer, one verifier.
_CALLS_PER_ROUND = 2


class InjectedCrash(RuntimeError):
    pass


def classify_finding(output: Mapping[str, object]) -> RefinementOutcomeClass:
    """Classify a schema-valid verifier finding for the refinement trigger.

    Derived only from fields the verifier schema already requires -- no new
    classifier, and no asking a model to grade its own output:

    * ``refuting``   -- some finding contradicts the candidate, or the verifier
      recommends rejection. The candidate is wrong as written.
    * ``defective``  -- the check did not complete: an ``inconclusive`` or
      ``failure`` result type, an ``unresolved`` outcome, or an ``unresolved``
      recommendation.
    * ``supporting`` -- every finding supports the candidate and the verifier
      recommends manual review. Re-proposing here would be pointless churn.
    * ``indeterminate`` -- schema-valid but says nothing either way, e.g. an
      empty findings list. Treated conservatively as *not* warranting a round.

    Only ``refuting`` and ``defective`` warrant another round.
    """
    findings = output.get("findings") or []
    outcomes = {str(item.get("outcome")) for item in findings if isinstance(item, Mapping)}
    recommendation = str(output.get("recommendation"))
    result_type = str(output.get("result_type"))
    if "contradicts" in outcomes or recommendation == "reject":
        return RefinementOutcomeClass.REFUTING
    if result_type in {"inconclusive", "failure"} or "unresolved" in outcomes or recommendation == "unresolved":
        return RefinementOutcomeClass.DEFECTIVE
    if outcomes == {"supports"} and recommendation == "manual_review":
        return RefinementOutcomeClass.SUPPORTING
    return RefinementOutcomeClass.INDETERMINATE


class BaselineResearchLoop:
    """Orchestrates bounded proposer/verifier rounds with an isolated verifier."""

    def __init__(
        self, *, workspace: DurableWorkspace, artifacts: ArtifactStore,
        proposer: ModelGateway, verifier: ModelGateway,
        independence: VerifierIndependence,
        now: Callable[[], datetime] | None = None,
        prompt_catalog: PromptCatalog | None = None,
        schema_dir: Path | None = None,
        worker_id: str = "phase2.local-worker",
        lease_milliseconds: int = 30_000,
        call_timeout_milliseconds: int = 20_000,
        estimated_output_tokens: int = 512,
        fault_after_proposal_artifact_once: bool = False,
        before_proposal_commit: Callable[[OpaqueId], None] | None = None,
        pricing_snapshot: PricingSnapshot | None = None,
        pricing_snapshots: Mapping[str, PricingSnapshot] | None = None,
        output_token_reserves: Mapping[str, int] | None = None,
    ) -> None:
        self.workspace = workspace
        self.artifacts = artifacts
        self.proposer = proposer
        self.verifier = verifier
        # ADR-0041: the two role axes are measured from the gateways that were
        # actually wired in. A declaration cannot promote a same-provider run to
        # a cross-provider one.
        self.declared_independence = independence
        self.independence = measure_role_independence(
            independence, proposer=proposer, verifier=verifier,
        )
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.prompts = prompt_catalog or PromptCatalog()
        self.schema_dir = schema_dir or Path(__file__).resolve().parents[3] / "schemas"
        self.worker_id = worker_id
        self.lease_milliseconds = lease_milliseconds
        self.call_timeout_milliseconds = call_timeout_milliseconds
        self.estimated_output_tokens = estimated_output_tokens
        self.fault_after_proposal_artifact_once = fault_after_proposal_artifact_once
        self.before_proposal_commit = before_proposal_commit
        self.pricing_snapshot = pricing_snapshot
        # Per-role pricing. Two providers mean two rate cards; a single snapshot
        # stays valid for the single-provider path.
        self.pricing_snapshots: dict[str, PricingSnapshot] = dict(pricing_snapshots or {})
        # Per-role output reserve. Two providers may declare different reserves,
        # and the reserve drives both the request cap and the cost estimate.
        self.output_token_reserves: dict[str, int] = dict(output_token_reserves or {})

    # --- identity -----------------------------------------------------------
    #
    # Every durable identity is round-injective. Round one keeps its
    # pre-ADR-0041 spelling and later rounds carry an explicit ``.round.N``
    # segment. That asymmetry is deliberate, not laziness: `reports/phase-2` is
    # sealed evidence pinned by the ADR-0022 Phase 4A protected-evidence
    # manifest, and proposal and manifest identifiers appear verbatim in the
    # traceable report, so renaming round one would make committed evidence
    # unreproducible from current code. Nothing has to infer a round from a
    # name: `jobs.round_index` and the `refinement_rounds` ledger carry it.

    @staticmethod
    def _round_suffix(round_index: int) -> str:
        return "" if round_index == 1 else f".round.{round_index}"

    @staticmethod
    def _round_key_suffix(round_index: int) -> str:
        return "" if round_index == 1 else f":round:{round_index}"

    @classmethod
    def _job_id(cls, run_id: OpaqueId, purpose: str, round_index: int) -> OpaqueId:
        return OpaqueId(f"job.{run_id.value}.{purpose}{cls._round_suffix(round_index)}")

    @classmethod
    def _job_key(cls, run_id: OpaqueId, purpose: str, round_index: int) -> str:
        return f"job:{run_id.value}:{purpose}{cls._round_key_suffix(round_index)}"

    @classmethod
    def _proposal_id(cls, run_id: OpaqueId, purpose: str, round_index: int) -> OpaqueId:
        return OpaqueId(f"proposal.{run_id.value}.{purpose}{cls._round_suffix(round_index)}")

    @classmethod
    def _proposal_key(cls, run_id: OpaqueId, purpose: str, round_index: int) -> str:
        return f"proposal:{run_id.value}:{purpose}{cls._round_key_suffix(round_index)}"

    @classmethod
    def _call_prefix(cls, run_id: OpaqueId, purpose: str, round_index: int) -> str:
        return f"call.{run_id.value}.{purpose}{cls._round_suffix(round_index)}.attempt."

    def _pricing(self, purpose: str) -> PricingSnapshot | None:
        return self.pricing_snapshots.get(purpose, self.pricing_snapshot)

    def _output_reserve(self, purpose: str) -> int:
        return self.output_token_reserves.get(purpose, self.estimated_output_tokens)

    # --- lifecycle ----------------------------------------------------------

    def start(
        self, *, run_id: OpaqueId, dossier: ResearchDossier, limits: BudgetLimits,
        deadline_milliseconds: int = 120_000,
    ) -> RunRecord:
        now = self._now()
        budget_id = OpaqueId(f"budget.{run_id.value}")
        record = self.workspace.create_run(
            run_id=run_id, dossier=dossier, budget_id=budget_id, limits=limits, now=now,
        )
        deadline = self._after(deadline_milliseconds)
        self.workspace.enqueue_job(
            job_id=self._job_id(run_id, "proposer", 1), run_id=run_id,
            kind="proposer", idempotency_key=self._job_key(run_id, "proposer", 1),
            payload_hash=record.dossier_hash, max_attempts=2,
            deadline_at=deadline, now=now, round_index=1,
        )
        return self.workspace.set_run_status(
            run_id, RunStatus.RUNNING.value, now=now,
            idempotency_key=f"run:{run_id.value}:running",
        )

    def pause(self, run_id: OpaqueId) -> RunRecord:
        return self.workspace.set_run_status(
            run_id, RunStatus.PAUSED.value, now=self._now(),
            idempotency_key=f"run:{run_id.value}:paused",
        )

    def resume(self, run_id: OpaqueId) -> RunRecord:
        return self.workspace.set_run_status(
            run_id, RunStatus.RUNNING.value, now=self._now(),
            idempotency_key=f"run:{run_id.value}:resumed",
        )

    def cancel(self, run_id: OpaqueId) -> RunRecord:
        return self.workspace.set_run_status(
            run_id, RunStatus.CANCELLED.value, now=self._now(),
            idempotency_key=f"run:{run_id.value}:cancelled",
        )

    def advance(self, run_id: OpaqueId) -> RunRecord:
        run = self.workspace.get_run(run_id)
        if run.status is not RunStatus.RUNNING:
            return run
        runnable = [
            item for item in self.workspace.list_jobs(run_id)
            if item.status in {JobStatus.QUEUED, JobStatus.RETRYABLE}
        ]
        if not runnable:
            return run
        # Lowest round first, proposer before verifier inside a round. Only one
        # round is ever in flight, so this is a total order over pending work.
        job = min(runnable, key=lambda item: (item.round_index, 0 if item.kind == "proposer" else 1, item.job_id.value))
        if job.kind == "proposer":
            self._execute_proposer(run, job.round_index)
        elif job.kind == "verifier":
            self._execute_verifier(run, job.round_index)
        return self.workspace.get_run(run_id)

    def run_to_terminal(self, run_id: OpaqueId, *, max_steps: int | None = None) -> RunRecord:
        """Drive rounds until a terminal state, a stall, or the derived bound.

        The step bound is derived from the run's own declared round cap -- two
        advances per round plus one for the start transition and one for the
        terminal transition -- never from a literal.
        """
        if max_steps is None:
            run = self.workspace.get_run(run_id)
            cap = self.workspace.budget(run.budget_id, now=self._now()).limits.max_refinement_rounds
            max_steps = 2 * cap + 2
        previous: tuple[str, tuple[tuple[str, str, int], ...]] | None = None
        for _ in range(max_steps):
            current = self.workspace.get_run(run_id)
            state = (
                current.status.value,
                tuple((item.kind, item.status.value, item.round_index) for item in self.workspace.list_jobs(run_id)),
            )
            if current.status in TERMINAL_RUN_STATUSES:
                return current
            if state == previous:
                return current
            previous = state
            self.advance(run_id)
        return self.workspace.get_run(run_id)

    # --- proposer -----------------------------------------------------------

    def _execute_proposer(self, run: RunRecord, round_index: int) -> None:
        job = self.workspace.claim_job(
            run_id=run.run_id, kind="proposer", worker_id=self.worker_id,
            lease_until=self._after(self.lease_milliseconds), now=self._now(),
            round_index=round_index,
        )
        if job is None:
            return
        dossier = self.workspace.load_dossier(run.dossier_id)
        prior = self._prior_rounds(run, round_index)
        context, referenced = self._proposer_context(
            dossier, prior=prior, round_index=round_index,
            max_refinement_rounds=self.workspace.budget(
                run.budget_id, now=self._now(),
            ).limits.max_refinement_rounds,
        )
        request = self._request(run, "proposer", context, referenced, round_index)
        result, output, result_hash, call_id = self._call(run, job.job_id, request, round_index)
        if output is None:
            self._non_success(run, job.job_id, result, result_hash, "proposer", round_index)
            return
        try:
            self._validate_target_and_refs(output, dossier, expected_hash=None)
        except StructuredOutputError:
            malformed = replace(result, status=ModelResultStatus.MALFORMED)
            self._non_success(run, job.job_id, malformed, result_hash, "proposer", round_index)
            return
        candidate = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "result_type": output["result_type"],
            "target_claim_id": output["target_claim_id"],
            "mathematical_payload": output["mathematical_payload"],
            "referenced_entity_ids": output["referenced_entity_ids"],
        }
        artifact = self.artifacts.put(canonical_bytes(candidate), media_type="application/vnd.adaivy.proposal+json")
        if self.fault_after_proposal_artifact_once:
            self.fault_after_proposal_artifact_once = False
            raise InjectedCrash("simulated crash after artifact creation before semantic commit")
        if self.before_proposal_commit:
            self.before_proposal_commit(run.run_id)
        proposal = ProposalRecord(
            proposal_id=self._proposal_id(run.run_id, "proposer", round_index), run_id=run.run_id,
            proposal_kind=output["result_type"], artifact_hash=artifact.content_hash,
            source_kind="model", source_id=call_id.value,
            target_claim_id=dossier.formalization.target_claim_id,
        )
        try:
            self.workspace.commit_proposal(
                proposal, job_id=job.job_id, worker_id=self.worker_id, now=self._now(),
                event_key=self._proposal_key(run.run_id, "proposer", round_index),
            )
            self.workspace.finish_job(
                job.job_id, worker_id=self.worker_id, status=JobStatus.SUCCEEDED.value,
                result_hash=artifact.content_hash, now=self._now(),
                idempotency_key=self._job_key(run.run_id, "proposer", round_index) + ":succeeded",
            )
        except LateCommitRejected:
            return
        self.workspace.enqueue_job(
            job_id=self._job_id(run.run_id, "verifier", round_index), run_id=run.run_id,
            kind="verifier", idempotency_key=self._job_key(run.run_id, "verifier", round_index),
            payload_hash=artifact.content_hash, max_attempts=2,
            deadline_at=job.deadline_at, now=self._now(), round_index=round_index,
        )

    # --- verifier -----------------------------------------------------------

    def _execute_verifier(self, run: RunRecord, round_index: int) -> None:
        job = self.workspace.claim_job(
            run_id=run.run_id, kind="verifier", worker_id=self.worker_id,
            lease_until=self._after(self.lease_milliseconds), now=self._now(),
            round_index=round_index,
        )
        if job is None:
            return
        dossier = self.workspace.load_dossier(run.dossier_id)
        # The candidate under review is exactly the artifact this verifier job
        # was enqueued for. Deriving it from the job payload, not from an id
        # suffix, keeps the lookup correct even when two rounds happen to
        # produce byte-identical candidates.
        proposer = next(
            item for item in self.workspace.list_proposals(run.run_id)
            if item.source_kind == "model"
            and item.proposal_kind != "verifier_finding"
            and item.artifact_hash == job.payload_hash
        )
        candidate = json.loads(self.artifacts.get(proposer.artifact_hash))
        prior = self._prior_rounds(run, round_index)
        context, included, excluded = self._verifier_context(dossier, proposer, candidate, prior)
        context_text = canonical_json(context)
        context_artifact = self.artifacts.put(context_text.encode("utf-8"), media_type="application/vnd.adaivy.verifier-context+json")
        independence = measure_context_isolation(
            self.independence, serialized_context=context_text,
            excluded_entity_ids=tuple(item.value for item in excluded),
            proposer_call_id=proposer.source_id,
        )
        manifest = VerifierContextManifest(
            manifest_id=OpaqueId(
                f"manifest.{run.run_id.value}.verifier{self._round_suffix(round_index)}"
            ),
            run_id=run.run_id,
            included_entity_ids=included, excluded_entity_ids=excluded,
            policy_version=POLICY_VERSION, serialized_context_hash=sha256_bytes(context_text.encode("utf-8")),
            context_artifact_hash=context_artifact.content_hash, independence=independence,
            round_index=round_index,
            candidate_shaped_by_rounds=tuple(item["round_index"] for item in prior),
            withheld_prior_finding_hashes=tuple(item["finding_artifact_hash"] for item in prior),
        )
        manifest_json = canonical_json(manifest)
        self.workspace.save_manifest(manifest, canonical_json=manifest_json, now=self._now())
        request = self._request(run, "verifier", context, included, round_index)
        result, output, result_hash, call_id = self._call(run, job.job_id, request, round_index)
        if output is None:
            self._non_success(run, job.job_id, result, result_hash, "verifier", round_index)
            return
        try:
            self._validate_target_and_refs(output, dossier, expected_hash=proposer.artifact_hash)
        except StructuredOutputError:
            malformed = replace(result, status=ModelResultStatus.MALFORMED)
            self._non_success(run, job.job_id, malformed, result_hash, "verifier", round_index)
            return
        finding = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "result_type": output["result_type"],
            "target_claim_id": output["target_claim_id"],
            "candidate_artifact_hash": output["candidate_artifact_hash"],
            "findings": output["findings"],
            "recommendation": output["recommendation"],
            "declared_rationale": output["declared_rationale"],
        }
        artifact = self.artifacts.put(canonical_bytes(finding), media_type="application/vnd.adaivy.verifier-finding+json")
        proposal = ProposalRecord(
            proposal_id=self._proposal_id(run.run_id, "verifier", round_index), run_id=run.run_id,
            proposal_kind="verifier_finding", artifact_hash=artifact.content_hash,
            source_kind="model", source_id=call_id.value,
            target_claim_id=dossier.formalization.target_claim_id,
        )
        try:
            self.workspace.commit_proposal(
                proposal, job_id=job.job_id, worker_id=self.worker_id, now=self._now(),
                event_key=self._proposal_key(run.run_id, "verifier", round_index),
            )
            self.workspace.finish_job(
                job.job_id, worker_id=self.worker_id, status=JobStatus.SUCCEEDED.value,
                result_hash=artifact.content_hash, now=self._now(),
                idempotency_key=self._job_key(run.run_id, "verifier", round_index) + ":succeeded",
            )
        except LateCommitRejected:
            return
        self._conclude_round(
            run, round_index=round_index, deadline_at=job.deadline_at,
            candidate_artifact_hash=proposer.artifact_hash,
            finding_artifact_hash=artifact.content_hash, output=output,
        )

    # --- round accounting ---------------------------------------------------

    def _conclude_round(
        self, run: RunRecord, *, round_index: int, deadline_at: str,
        candidate_artifact_hash: str, finding_artifact_hash: str,
        output: Mapping[str, object],
    ) -> None:
        outcome = classify_finding(output)
        recommendation = str(output["recommendation"])
        self.workspace.record_refinement_round(
            RefinementRoundRecord(
                run_id=run.run_id, round_index=round_index,
                candidate_artifact_hash=candidate_artifact_hash,
                finding_artifact_hash=finding_artifact_hash,
                outcome_class=outcome, result_type=str(output["result_type"]),
                recommendation=recommendation,
                refinement_warranted=outcome.warrants_refinement,
            ),
            now=self._now(),
        )
        snapshot = self.workspace.budget(run.budget_id, now=self._now())
        if not outcome.warrants_refinement:
            terminal = RunStatus.AWAITING_REVIEW if recommendation == "manual_review" else RunStatus.UNRESOLVED
            self._stop(
                run, terminal=terminal, reason=RunStopReason.NO_REFINEMENT_WARRANTED,
                bound=None, binding=(), rounds_used=round_index,
                max_rounds=snapshot.limits.max_refinement_rounds,
            )
            return
        # Budget is evaluated before the round counter on purpose: when both
        # would refuse the next round, the operator needs to know the money or
        # tokens ran out, not that a counter did.
        binding = self._binding_bounds(snapshot, run, round_index)
        if binding:
            self._stop(
                run, terminal=RunStatus.REFINEMENT_EXHAUSTED, reason=RunStopReason.BUDGET_BOUND,
                bound=binding[0], binding=binding, rounds_used=round_index,
                max_rounds=snapshot.limits.max_refinement_rounds,
            )
            return
        next_round = round_index + 1
        try:
            self.workspace.reserve_refinement_round(
                run.budget_id, round_index=next_round, now=self._now(),
            )
        except RefinementRoundsExhausted:
            self._stop(
                run, terminal=RunStatus.REFINEMENT_EXHAUSTED,
                reason=RunStopReason.REFINEMENT_ROUND_CAP, bound="refinement_rounds",
                binding=("refinement_rounds",), rounds_used=round_index,
                max_rounds=snapshot.limits.max_refinement_rounds,
            )
            return
        self.workspace.append_event(
            event_id=OpaqueId(f"event.refinement:{run.run_id.value}:round:{next_round}"),
            aggregate_id=run.run_id, event_type="refinement_round_enqueued",
            payload_json=canonical_json({
                "round_index": next_round,
                "prior_round_index": round_index,
                "prior_outcome_class": outcome.value,
                "prior_finding_artifact_hash": finding_artifact_hash,
                "max_refinement_rounds": snapshot.limits.max_refinement_rounds,
            }),
            now=self._now(),
            idempotency_key=f"refinement:{run.run_id.value}:round:{next_round}",
        )
        self.workspace.enqueue_job(
            job_id=self._job_id(run.run_id, "proposer", next_round), run_id=run.run_id,
            kind="proposer", idempotency_key=self._job_key(run.run_id, "proposer", next_round),
            payload_hash=finding_artifact_hash, max_attempts=2,
            deadline_at=deadline_at, now=self._now(), round_index=next_round,
        )

    def _stop(
        self, run: RunRecord, *, terminal: RunStatus, reason: RunStopReason,
        bound: str | None, binding: tuple[str, ...], rounds_used: int, max_rounds: int,
    ) -> None:
        self.workspace.record_run_stop(
            RunStopRecord(
                run_id=run.run_id, terminal_status=terminal, stop_reason=reason,
                stop_bound=bound, binding_bounds=binding, rounds_used=rounds_used,
                max_refinement_rounds=max_rounds,
            ),
            now=self._now(),
        )
        self.workspace.set_run_status(
            run.run_id, terminal.value, now=self._now(),
            idempotency_key=f"run:{run.run_id.value}:{terminal.value}",
        )

    def _binding_bounds(self, snapshot, run: RunRecord, completed_round: int) -> tuple[str, ...]:
        """Which declared budget dimensions refuse one more round.

        Projection is the *measured* cost of the round that just finished --
        exact integers from recorded usage, no floating point, no growth model.
        A dimension already exhausted is binding regardless of the projection.
        """
        binding = set(snapshot.exhausted_dimensions)
        prefixes = tuple(
            self._call_prefix(run.run_id, purpose, completed_round)
            for purpose in ("proposer", "verifier")
        )
        calls = [
            item for item in self.workspace.list_model_calls(run.run_id)
            if str(item["call_id"]).startswith(prefixes)
        ]
        projected_input = sum(int(item["input_tokens"]) for item in calls)
        projected_output = sum(int(item["output_tokens"]) for item in calls)
        projected_cost = sum(int(item["estimated_cost_microusd"] or 0) for item in calls)
        limits = snapshot.limits
        if snapshot.used_cost_microusd + projected_cost > limits.max_cost_microusd:
            binding.add("cost")
        if snapshot.used_input_tokens + projected_input > limits.max_input_tokens:
            binding.add("input_tokens")
        if snapshot.used_output_tokens + projected_output > limits.max_output_tokens:
            binding.add("output_tokens")
        if snapshot.used_attempts + max(_CALLS_PER_ROUND, len(calls)) > limits.max_attempts:
            binding.add("attempts")
        return tuple(sorted(
            binding,
            key=lambda item: (_BOUND_ORDER.index(item) if item in _BOUND_ORDER else len(_BOUND_ORDER), item),
        ))

    def _prior_rounds(self, run: RunRecord, round_index: int) -> tuple[dict[str, object], ...]:
        """Completed rounds before ``round_index``, oldest first, with content."""
        values: list[dict[str, object]] = []
        for record in self.workspace.list_refinement_rounds(run.run_id):
            if record.round_index >= round_index:
                continue
            values.append({
                "round_index": record.round_index,
                "candidate_artifact_hash": record.candidate_artifact_hash,
                "finding_artifact_hash": record.finding_artifact_hash,
                "outcome_class": record.outcome_class.value,
                "recommendation": record.recommendation,
                "candidate": json.loads(self.artifacts.get(record.candidate_artifact_hash)),
                "verifier_finding": json.loads(self.artifacts.get(record.finding_artifact_hash)),
            })
        return tuple(values)

    # --- model call ---------------------------------------------------------

    def _call(
        self, run: RunRecord, job_id: OpaqueId, request: ModelRequest, round_index: int,
    ) -> tuple[ModelResult, dict[str, object] | None, str | None, OpaqueId]:
        job = next(item for item in self.workspace.list_jobs(run.run_id) if item.job_id == job_id)
        call_id = OpaqueId(
            self._call_prefix(run.run_id, request.purpose, round_index) + str(job.attempts)
        )
        call_key = (
            f"call:{run.run_id.value}:{request.purpose}"
            f"{self._round_key_suffix(round_index)}:attempt:{job.attempts}"
        )
        gateway = self.proposer if request.purpose == "proposer" else self.verifier
        pricing = self._pricing(request.purpose)
        request_ref = self.artifacts.put(canonical_bytes(request), media_type="application/vnd.adaivy.model-request+json")
        try:
            preparation = gateway.prepare(request)
        except ProviderSchemaError as error:
            compatibility_ref = self.artifacts.put(
                canonical_bytes(error.report),
                media_type="application/vnd.adaivy.provider-schema-compatibility+json",
            )
            config = getattr(gateway, "config", None)
            result = ModelResult(
                status=ModelResultStatus.FAILED,
                provider="openai" if config is not None else "provider",
                model_identifier=getattr(config, "model_identifier", "unknown"),
                capabilities=tuple(getattr(config, "capabilities", ())),
                structured_output=None,
                declared_rationale=None,
                refusal=None,
                usage=self._zero_usage(),
                retry_classification="fatal:provider_schema_incompatible",
                compatibility_report_hash=compatibility_ref.content_hash,
            )
            result_ref = self.artifacts.put(
                canonical_bytes(result), media_type="application/vnd.adaivy.model-result+json",
            )
            self.workspace.record_model_call(
                call_id=call_id, run_id=run.run_id, purpose=request.purpose,
                request_hash=request_ref.content_hash, result_hash=result_ref.content_hash,
                result=result, now=self._now(), idempotency_key=call_key,
            )
            return result, None, result_ref.content_hash, call_id
        estimate = max(1, (len(request.serialized_context) + len(request.template_text)) // 4)
        reserve = self._output_reserve(request.purpose)
        estimated_cost = (
            estimate_cost_microusd(
                pricing,
                input_tokens=estimate,
                output_tokens=reserve,
            )
            if pricing is not None else 0
        )
        try:
            self.workspace.reserve_call(
                run.budget_id, estimated_input_tokens=estimate,
                estimated_output_tokens=reserve,
                estimated_cost_microusd=estimated_cost, now=self._now(),
            )
        except BudgetExhausted:
            result = ModelResult(
                status=ModelResultStatus.FAILED, provider="none", model_identifier="none",
                capabilities=(), structured_output=None, declared_rationale=None, refusal=None,
                usage=self._zero_usage(), retry_classification="fatal:budget_exhausted",
            )
            return result, None, None, call_id
        if pricing is not None:
            self.workspace.record_cost_estimate(
                CostEstimate(
                    estimate_id=OpaqueId(f"estimate.{call_id.value}"), call_id=call_id,
                    run_id=run.run_id, pricing_snapshot_id=pricing.snapshot_id,
                    input_token_estimate=estimate,
                    output_token_estimate=reserve,
                    estimated_cost_microusd=estimated_cost,
                ),
                now=self._now(),
            )
        projection_manifest_hash = None
        compatibility_report_hash = None
        provider_schema_hash = None
        if preparation is not None:
            provider_ref = self.artifacts.put(
                preparation.provider_schema_json.encode("utf-8"),
                media_type="application/vnd.adaivy.provider-schema+json",
            )
            manifest_ref = self.artifacts.put(
                preparation.transformation_manifest_json.encode("utf-8"),
                media_type="application/vnd.adaivy.schema-projection-manifest+json",
            )
            compatibility_ref = self.artifacts.put(
                preparation.compatibility_report_json.encode("utf-8"),
                media_type="application/vnd.adaivy.provider-schema-compatibility+json",
            )
            self.artifacts.put(
                preparation.compatibility_report_text.encode("utf-8"),
                media_type="text/markdown",
            )
            if provider_ref.content_hash != preparation.provider_schema_hash:
                raise RuntimeError("persisted provider schema hash differs from preparation")
            provider_schema_hash = preparation.provider_schema_hash
            projection_manifest_hash = manifest_ref.content_hash
            compatibility_report_hash = compatibility_ref.content_hash
        result = gateway.complete(request, preparation)
        result = replace(
            result,
            provider_schema_hash=provider_schema_hash,
            projection_manifest_hash=projection_manifest_hash,
            compatibility_report_hash=compatibility_report_hash,
        )
        if pricing is not None:
            actual_estimate = estimate_cost_microusd(
                pricing,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
            )
            result = replace(
                result,
                usage=replace(
                    result.usage,
                    estimated_cost_microusd=actual_estimate,
                    pricing_snapshot_id=pricing.snapshot_id,
                ),
            )
        output: dict[str, object] | None = None
        if result.status is ModelResultStatus.SUCCEEDED and result.structured_output is not None:
            try:
                output = validate_structured_output(
                    request.purpose, result.structured_output, schema_dir=self.schema_dir,
                )
            except StructuredOutputError:
                result = replace(result, status=ModelResultStatus.MALFORMED)
        result_ref = self.artifacts.put(canonical_bytes(result), media_type="application/vnd.adaivy.model-result+json")
        self.workspace.record_usage(
            run.budget_id, input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cost_microusd=result.usage.estimated_cost_microusd or 0,
            now=self._now(),
        )
        self.workspace.record_model_call(
            call_id=call_id, run_id=run.run_id,
            purpose=request.purpose, request_hash=request_ref.content_hash,
            result_hash=result_ref.content_hash, result=result, now=self._now(),
            idempotency_key=call_key,
        )
        if result.status is not ModelResultStatus.SUCCEEDED or output is None:
            return result, None, result_ref.content_hash, call_id
        return result, output, result_ref.content_hash, call_id

    def _non_success(
        self, run: RunRecord, job_id: OpaqueId, result: ModelResult,
        result_hash: str | None, purpose: str, round_index: int,
    ) -> None:
        status = JobStatus.TIMED_OUT if result.status is ModelResultStatus.TIMED_OUT else JobStatus.FAILED
        try:
            self.workspace.finish_job(
                job_id, worker_id=self.worker_id, status=status.value,
                result_hash=result_hash, now=self._now(),
                idempotency_key=self._job_key(run.run_id, purpose, round_index) + f":{status.value}",
            )
        except LateCommitRejected:
            return
        snapshot = self.workspace.budget(run.budget_id, now=self._now())
        self.workspace.record_run_stop(
            RunStopRecord(
                run_id=run.run_id, terminal_status=RunStatus.UNRESOLVED,
                stop_reason=RunStopReason.NON_SUCCESS, stop_bound=None,
                binding_bounds=snapshot.exhausted_dimensions,
                rounds_used=round_index,
                max_refinement_rounds=snapshot.limits.max_refinement_rounds,
            ),
            now=self._now(),
        )
        self.workspace.set_run_status(
            run.run_id, RunStatus.UNRESOLVED.value, now=self._now(),
            idempotency_key=f"run:{run.run_id.value}:unresolved",
        )

    # --- context ------------------------------------------------------------

    def _request(
        self, run: RunRecord, purpose: str, context: dict[str, object],
        referenced: tuple[OpaqueId, ...], round_index: int,
    ) -> ModelRequest:
        template = self.prompts.load(
            "proposer_refinement" if purpose == "proposer" and round_index > 1 else purpose
        )
        schema = (self.schema_dir / f"model-{purpose}-v1.schema.json").read_text(encoding="utf-8")
        return ModelRequest(
            request_id=OpaqueId(
                f"request.{run.run_id.value}.{purpose}{self._round_suffix(round_index)}"
            ),
            run_id=run.run_id,
            purpose=purpose, template_id=template.template_id, template_version=template.version,
            template_hash=template.content_hash, template_text=template.text,
            serialized_context=canonical_json(context), response_schema=schema,
            referenced_entity_ids=referenced, timeout_milliseconds=self.call_timeout_milliseconds,
            max_output_tokens=self._output_reserve(purpose),
        )

    @staticmethod
    def _proposer_context(
        dossier: ResearchDossier, *,
        prior: tuple[dict[str, object], ...] = (),
        round_index: int = 1,
        max_refinement_rounds: int = 1,
    ) -> tuple[dict[str, object], tuple[OpaqueId, ...]]:
        payload = export_dossier_dict(dossier)
        target_id = dossier.formalization.target_claim_id
        target = next(item for item in payload["claims"] if item["id"] == target_id.value)
        premise_ids = set(dossier.formalization.assumption_claim_ids)
        premises = [item for item in payload["claims"] if item["id"] in {value.value for value in premise_ids}]
        obligations = [item for item in payload["obligations"] if item["claim_id"] == target_id.value and item["status"] in {"open", "blocked"}]
        referenced = tuple(sorted((target_id, dossier.formalization.id, dossier.semantic_alignment.id, *premise_ids), key=lambda item: item.value))
        context: dict[str, object] = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "purpose": "bounded_proposal",
            "approved_target": target,
            "formalization": payload["formalization"],
            "semantic_alignment": payload["semantic_alignment"],
            "accepted_premises": premises,
            "open_obligations": obligations,
            "verification_policy": {"policy_version": POLICY_VERSION, "model_outputs_are_proposals": True, "models_cannot_award_warrants": True},
        }
        if not prior:
            # Round one is byte-identical to the pre-ADR-0041 context. A run that
            # never refines produces the same request bytes it always did.
            return context, referenced
        context["refinement"] = {
            "round_index": round_index,
            "max_refinement_rounds": max_refinement_rounds,
            "instruction": (
                "A prior candidate was faulted by an isolated verifier. Address "
                "every finding below and return one revised, schema-valid "
                "candidate. The findings are proposals, not proof of anything."
            ),
            "prior_rounds": [
                {
                    "round_index": item["round_index"],
                    "outcome_class": item["outcome_class"],
                    "candidate_artifact_hash": item["candidate_artifact_hash"],
                    "candidate": item["candidate"],
                    "verifier_finding": item["verifier_finding"],
                }
                for item in prior
            ],
        }
        return context, referenced

    def _verifier_context(
        self, dossier: ResearchDossier, proposal: ProposalRecord, candidate: dict[str, object],
        prior: tuple[dict[str, object], ...] = (),
    ) -> tuple[dict[str, object], tuple[OpaqueId, ...], tuple[OpaqueId, ...]]:
        payload = export_dossier_dict(dossier)
        target_id = dossier.formalization.target_claim_id
        target = next(item for item in payload["claims"] if item["id"] == target_id.value)
        premise_ids = set(dossier.formalization.assumption_claim_ids)
        premises = [item for item in payload["claims"] if item["id"] in {value.value for value in premise_ids}]
        accepted_evidence = [item for item in payload["evidence"] if item["disposition"] == Disposition.ACCEPTED.value]
        included_set = {
            target_id, dossier.formalization.id, dossier.semantic_alignment.id,
            proposal.proposal_id, *premise_ids,
            *(item.id for item in dossier.evidence if item.disposition is Disposition.ACCEPTED),
        }
        all_ids = self._dossier_entity_ids(dossier)
        proposer_call_id = OpaqueId(proposal.source_id)
        # ADR-0041: every earlier round's proposal and model call is withheld
        # too. A later round must not become a back door into material the
        # independence policy excluded from round one.
        prior_ids: set[OpaqueId] = set()
        for record in self.workspace.list_proposals(proposal.run_id):
            if record.proposal_id == proposal.proposal_id:
                continue
            prior_ids.add(record.proposal_id)
            if record.source_kind == "model":
                prior_ids.add(OpaqueId(record.source_id))
        excluded_set = ((all_ids - included_set) | {proposer_call_id} | prior_ids) - included_set
        included = tuple(sorted(included_set, key=lambda item: item.value))
        excluded = tuple(sorted(excluded_set, key=lambda item: item.value))
        context = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "purpose": "isolated_verification",
            "approved_target": target,
            "formalization": payload["formalization"],
            "semantic_alignment": payload["semantic_alignment"],
            "accepted_premises": premises,
            "raw_evidence_and_source_spans": accepted_evidence,
            "candidate": {"proposal_id": proposal.proposal_id.value, "artifact_hash": proposal.artifact_hash, **candidate},
            "verification_policy": {
                "policy_version": POLICY_VERSION,
                "allowed_result": "finding_only",
                "models_cannot_award_warrants": True,
                "manual_review_required_for_acceptance": True,
            },
        }
        return context, included, excluded

    @staticmethod
    def _dossier_entity_ids(dossier: ResearchDossier) -> set[OpaqueId]:
        values: list[Entity] = [
            dossier.problem, dossier.formalization, dossier.semantic_alignment,
            *dossier.claims, *dossier.warrants, *dossier.evidence,
            *dossier.source_applicability, *dossier.obligations,
            *dossier.representation_maps, *dossier.verification_records,
            dossier.evaluation_protocol, *dossier.audit_events,
        ]
        return {item.id for item in values}

    @staticmethod
    def _validate_target_and_refs(output: dict[str, object], dossier: ResearchDossier, expected_hash: str | None) -> None:
        if output.get("target_claim_id") != dossier.formalization.target_claim_id.value:
            raise StructuredOutputError("model output targets a different claim")
        if expected_hash is not None and output.get("candidate_artifact_hash") != expected_hash:
            raise StructuredOutputError("verifier output targets a different candidate artifact")
        known = {item.value for item in BaselineResearchLoop._dossier_entity_ids(dossier)}
        references: list[str] = []
        if "referenced_entity_ids" in output:
            references.extend(output["referenced_entity_ids"])  # type: ignore[arg-type]
        for finding in output.get("findings", []):  # type: ignore[union-attr]
            references.extend(finding["referenced_entity_ids"])
        if not set(references).issubset(known):
            raise StructuredOutputError("model output references unknown entity IDs")

    @staticmethod
    def _zero_usage():
        from .records import ModelUsage
        return ModelUsage(input_tokens=0, output_tokens=0, total_tokens=0, usage_source="unavailable")

    def _now(self) -> str:
        value = self.now().astimezone(timezone.utc)
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _after(self, milliseconds: int) -> str:
        value = self.now().astimezone(timezone.utc) + timedelta(milliseconds=milliseconds)
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def deterministic_candidate(target_claim_id: str, premise_id: str) -> dict[str, object]:
    return {
        "schema_version": PHASE2_SCHEMA_VERSION,
        "result_type": "proof_attempt",
        "target_claim_id": target_claim_id,
        "mathematical_payload": {
            "statement": "Let a=2k and b=2l; then a+b=2(k+l), so a+b is even.",
            "steps": ["Expand both even integers by the accepted definition.", "Factor 2 from their sum."],
            "witness": "k+l",
        },
        "declared_rationale": "Direct use of the accepted definition of even.",
        "referenced_entity_ids": [premise_id],
    }


def deterministic_fake_results(target_claim_id: str, premise_id: str) -> tuple[ModelResult, ModelResult]:
    from .records import ModelUsage
    proposer_value = deterministic_candidate(target_claim_id, premise_id)
    candidate = {key: value for key, value in proposer_value.items() if key != "declared_rationale"}
    candidate_hash = sha256_bytes(canonical_bytes(candidate))
    verifier_value = {
        "schema_version": PHASE2_SCHEMA_VERSION,
        "result_type": "finding",
        "target_claim_id": target_claim_id,
        "candidate_artifact_hash": candidate_hash,
        "findings": [{
            "code": "derivation_checks_out",
            "outcome": "supports",
            "detail": "Each displayed algebraic step follows from the accepted definition, subject to manual trust review.",
            "referenced_entity_ids": [premise_id],
        }],
        "declared_rationale": "The isolated candidate is internally consistent with the supplied premise.",
        "recommendation": "manual_review",
    }
    common = {
        "status": ModelResultStatus.SUCCEEDED,
        "provider": "scripted",
        "model_identifier": "scripted-v1",
        "capabilities": ("structured_output", "deterministic"),
        "refusal": None,
        "retry_classification": "none",
    }
    return (
        ModelResult(**common, structured_output=canonical_json(proposer_value), declared_rationale=proposer_value["declared_rationale"], usage=ModelUsage(input_tokens=120, output_tokens=80, total_tokens=200, usage_source="fixture")),
        ModelResult(**common, structured_output=canonical_json(verifier_value), declared_rationale=verifier_value["declared_rationale"], usage=ModelUsage(input_tokens=160, output_tokens=90, total_tokens=250, usage_source="fixture")),
    )
