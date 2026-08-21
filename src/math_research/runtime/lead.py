"""The bounded central research lead: one problem, many turns, one verifier.

ADR-0047. This is the runtime the architecture has described since ADR-0029 and
never had. It drives the sealed Phase 2 loop once per iteration, carries a
proposer-only ledger between iterations, and stops for a named reason.

What it is not, stated first because the omissions are load-bearing:

- It is **not** a solver. The best terminal reason it can reach is
  `awaiting_human_review`, meaning an isolated verifier declined to fault a
  proposal and a person now has to look. No path here accepts anything.
- It is **not** a search tier. One lead, one centralized verifier, branches
  visited one at a time in a deterministic order. No specialists, no parallel
  workers, no fitness function, no selection.
- It does **not** measure whether iterating helps. The stagnation rule is a
  stop rule. Nothing computes verified progress per unit cost, and the
  ADR-0029 retention question stays open; `retention_gain_measured` is a
  constant `False` that the session record refuses to let anyone set.

Two bounds are enforced twice on purpose. Session spend is capped here, and
each iteration is *additionally* capped by the Phase 2 per-run budget it
already had. An iteration is never started unless the session has room for that
iteration's entire bound, so total spend cannot exceed the session bound even
if a single iteration spends everything it is allowed to.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..domain.entities import OpaqueId, ResearchDossier
from ..interchange import export_dossier_dict
from ..novelty import NoveltyRecheck, require_checkpoint, write_recheck
from ..phase2.artifacts import FileArtifactStore
from ..phase2.records import (
    PricingSnapshot,
    RunStopReason,
    RunStatus,
    VerifierIndependence,
)
from ..phase2.sqlite_workspace import SQLiteWorkspace
from .context import IterationLedger, IterativeProposerLoop, hypothesis_digest
from .records import (
    TERMINAL_ITERATION_OUTCOMES,
    IterationOutcome,
    IterationRecord,
    IterationUsage,
    LeadSession,
    SessionUsage,
    TargetIdentity,
    TerminalReason,
    VerifierFinding,
)
from .serialization import canonical_hash
from .session_config import SessionConfiguration


class TargetIdentityViolation(RuntimeError):
    """The frozen target changed during a session.

    Raised, never recorded. A session whose target moved cannot say what it was
    working on, so its record would be worse than no record. Structurally
    unreachable while the dossier is reloaded from content-addressed bytes; the
    check exists because "structurally unreachable" is a claim about today's
    code and this is the property that makes iteration safe.
    """


class GatewayCalledDuringReplay(RuntimeError):
    """A replay path reached a model gateway.

    Replay renders from durable records alone. Reaching a gateway here would
    mean a report regenerated itself by spending money, so this fails loudly.
    """


class ReplayGuardGateway:
    """A gateway that refuses every call. Used to prove replay stays offline."""

    def prepare(self, request: Any) -> None:
        raise GatewayCalledDuringReplay(f"replay prepared a {request.purpose} call")

    def complete(self, request: Any, preparation: Any = None) -> Any:
        raise GatewayCalledDuringReplay(f"replay attempted a {request.purpose} call")


@dataclass(frozen=True, slots=True, kw_only=True)
class _IterationResult:
    record: IterationRecord
    terminal_reason: TerminalReason | None
    exhausted_bound: str | None = None


def freeze_target(dossier: ResearchDossier) -> TargetIdentity:
    """Derive the identity a session may never change.

    Everything a proposal could weaken is in here: the claim it must target,
    the exact statement of that claim, the formalization, the assumption
    manifest, and the semantic alignment that connects informal intent to
    formal statement. Hashing the alignment matters as much as hashing the
    statement -- a session that kept the statement and quietly loosened the
    alignment would be proving a different thing in the same words.
    """
    target_id = dossier.formalization.target_claim_id
    target = next((item for item in dossier.claims if item.id == target_id), None)
    if target is None:
        raise TargetIdentityViolation(f"dossier has no claim {target_id.value}")
    alignment = dossier.semantic_alignment
    return TargetIdentity(
        target_claim_id=target_id,
        target_statement_hash=canonical_hash(target.statement),
        formalization_statement_hash=canonical_hash({
            "formal_language": dossier.formalization.formal_language.value
            if hasattr(dossier.formalization.formal_language, "value")
            else dossier.formalization.formal_language,
            "quantifiers": list(dossier.formalization.quantifiers),
            "statement": dossier.formalization.statement,
        }),
        assumption_manifest_hash=canonical_hash(
            sorted(item.value for item in dossier.formalization.assumption_claim_ids)
        ),
        semantic_alignment_hash=canonical_hash({
            "assumption_delta": list(alignment.assumption_delta),
            "definition_mapping": [list(pair) for pair in alignment.definition_mapping],
            "edge_case_delta": list(alignment.edge_case_delta),
            "id": alignment.id.value,
            "quantifier_mapping": [list(pair) for pair in alignment.quantifier_mapping],
            "status": getattr(alignment.status, "value", alignment.status),
            "strength_relation": getattr(
                alignment.strength_relation, "value", alignment.strength_relation
            ),
        }),
        dossier_hash=canonical_hash(dossier.id.value),
    )


class ResearchLeadRuntime:
    """One bounded iterative session over one frozen problem."""

    def __init__(
        self,
        *,
        root: Path,
        configuration: SessionConfiguration,
        proposer: Any,
        verifier: Any,
        pricing_snapshot: PricingSnapshot | None = None,
        now: Callable[[], datetime] | None = None,
        schema_dir: Path | None = None,
        ledger: IterationLedger | None = None,
        worker_id: str = "runtime.central-lead",
    ) -> None:
        self.root = root
        self.configuration = configuration
        self.proposer = proposer
        self.verifier = verifier
        self.pricing_snapshot = pricing_snapshot
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.schema_dir = schema_dir
        self.ledger = ledger or IterationLedger()
        self.worker_id = worker_id

    # -- public surface ----------------------------------------------------

    def run(
        self, *, session_id: OpaqueId, dossier: ResearchDossier,
        novelty_recheck: NoveltyRecheck,
    ) -> LeadSession:
        target = freeze_target(dossier)
        started = self.now()
        require_checkpoint(
            novelty_recheck, checkpoint="before_research",
            subject_id=dossier.problem.id.value,
            subject_hash=str(export_dossier_dict(dossier)["content_hash"]),
            next_action_id=session_id.value,
            action_at=self._stamp(started),
        )
        self.root.mkdir(parents=True, exist_ok=True)
        # This is written immediately before the first durable run/model action.
        # A content/action-bound record cannot be reused for another subject or
        # another session, and replay can inspect the exact bytes that opened it.
        write_recheck(novelty_recheck, self.root / "novelty-recheck.json")
        artifacts = FileArtifactStore(self.root / "artifacts")
        records: list[IterationRecord] = []
        seen_finding_signatures: set[str] = set()
        unproductive_streak = 0
        terminal: TerminalReason | None = None
        exhausted_bound: str | None = None

        with SQLiteWorkspace(self.root / "workspace.sqlite3") as workspace:
            if self.pricing_snapshot is not None:
                from ..phase2.serialization import canonical_json as phase2_canonical_json

                workspace.save_pricing_snapshot(
                    self.pricing_snapshot,
                    canonical_json=phase2_canonical_json(self.pricing_snapshot),
                    now=self._stamp(started),
                )
            for index in range(1, self.configuration.max_iterations + 1):
                bound = self._exhausted_bound(records, started)
                if bound is not None:
                    terminal, exhausted_bound = TerminalReason.BUDGET_EXHAUSTED, bound
                    break
                # Re-derived every iteration from the dossier the workspace is
                # about to persist, and compared against the identity frozen
                # before the first call.
                if freeze_target(dossier).frozen_hash() != target.frozen_hash():
                    raise TargetIdentityViolation(
                        "the frozen target changed between iterations"
                    )
                result = self._iterate(
                    workspace=workspace,
                    artifacts=artifacts,
                    session_id=session_id,
                    index=index,
                    dossier=dossier,
                    novelty_recheck=novelty_recheck,
                    seen_finding_signatures=seen_finding_signatures,
                )
                records.append(result.record)
                unproductive_streak = 0 if result.record.productive else unproductive_streak + 1
                if result.terminal_reason is not None:
                    terminal, exhausted_bound = result.terminal_reason, result.exhausted_bound
                    break
                if unproductive_streak >= self.configuration.stagnation_window:
                    terminal = TerminalReason.STAGNATED
                    break
            else:
                terminal = TerminalReason.ITERATIONS_EXHAUSTED
            if terminal is None:
                terminal = TerminalReason.ITERATIONS_EXHAUSTED

        ended = self.now()
        session = LeadSession(
            session_id=session_id,
            dossier_id=dossier.id,
            target=target,
            session_configuration_id=self.configuration.session_configuration_id,
            session_configuration_hash=self.configuration.content_hash,
            iterations=tuple(records),
            terminal_reason=terminal,
            exhausted_bound=exhausted_bound,
            usage=self._session_usage(records, started, ended),
            distinct_hypotheses=len({
                item.hypothesis_digest for item in records if item.hypothesis_digest
            }),
            started_at=self._stamp(started),
            ended_at=self._stamp(ended),
            novelty_recheck_id=novelty_recheck.recheck_id,
            novelty_recheck_hash=novelty_recheck.content_hash,
            prior_art_outcome=novelty_recheck.outcome,
            prior_art_relationship=novelty_recheck.prior_art_relationship,
            prior_resolution=novelty_recheck.prior_resolution,
            prior_resolution_verification=novelty_recheck.prior_resolution_verification,
            report_classification=novelty_recheck.classification().report_classification,
            target_resolution_status=novelty_recheck.classification().target_resolution_status,
        ).with_content_hash()
        self._persist(session)
        return session

    # -- one iteration -----------------------------------------------------

    def _iterate(
        self,
        *,
        workspace: SQLiteWorkspace,
        artifacts: FileArtifactStore,
        session_id: OpaqueId,
        index: int,
        dossier: ResearchDossier,
        novelty_recheck: NoveltyRecheck,
        seen_finding_signatures: set[str],
    ) -> _IterationResult:
        run_id = OpaqueId(f"{session_id.value}.iter.{index:03d}")
        budget_id = OpaqueId(f"budget.{run_id.value}")
        loop = IterativeProposerLoop(
            workspace=workspace,
            artifacts=artifacts,
            proposer=self.proposer,
            verifier=self.verifier,
            independence=self._independence(),
            now=self.now,
            schema_dir=self.schema_dir,
            worker_id=self.worker_id,
            call_timeout_milliseconds=min(
                self.configuration.per_iteration_budget.max_wall_milliseconds, 600_000
            ),
            estimated_output_tokens=max(
                256, self.configuration.per_iteration_budget.max_output_tokens // 2
            ),
            pricing_snapshot=self.pricing_snapshot,
            ledger=self.ledger,
            prior_art_context={
                "recheck_id": novelty_recheck.recheck_id,
                "recheck_hash": novelty_recheck.content_hash,
                "outcome": novelty_recheck.outcome,
                "relationship": novelty_recheck.prior_art_relationship,
                "prior_resolution": novelty_recheck.prior_resolution,
                "prior_resolution_verification": novelty_recheck.prior_resolution_verification,
                **novelty_recheck.classification().payload(),
                "reporting_rule": (
                    "Treat this as binding provenance for the research role. If the report "
                    "classification is independent_verification, do not claim discovery, "
                    "novel proof, or novel refutation; investigate only as verification or "
                    "a clearly delimited extension of the cited prior result."
                ),
            },
        )
        # `create_run` inserts one budget row per run, so the per-iteration
        # budget is a genuinely separate ledger rather than a view of a shared
        # one. Session-level enforcement is this class's own job, above.
        loop.start(
            run_id=run_id,
            dossier=dossier,
            limits=self.configuration.per_iteration_budget,
            deadline_milliseconds=self.configuration.per_iteration_budget.max_wall_milliseconds,
        )

        # -- proposer half
        loop.advance(run_id)
        run = workspace.get_run(run_id)
        proposals = workspace.list_proposals(run_id)
        proposer_record = next(
            (item for item in proposals if item.proposal_id.value.endswith(".proposer")), None
        )
        if proposer_record is None:
            return self._finish_iteration(
                workspace=workspace, run_id=run_id, index=index, run=run,
                digest="", outcome=IterationOutcome.PROPOSER_FAILED, budget_id=budget_id,
                proposal=None, candidate=None, recommendation=None, findings=(),
                details=(), duplicate_of=None, productive=False,
                seen_finding_signatures=seen_finding_signatures,
            )

        candidate = json.loads(artifacts.get(proposer_record.artifact_hash))
        payload = candidate.get("mathematical_payload") or {}
        digest = hypothesis_digest(
            result_type=str(candidate.get("result_type", "")),
            statement=str(payload.get("statement", "")),
            steps=tuple(str(step) for step in payload.get("steps", ())),
        )
        previous = self.ledger.digests
        if digest in previous:
            # Repeating an attempt cannot produce a different verdict from an
            # isolated verifier that never saw the first one, so the verifier
            # call is not spent. The iteration is still consumed: repetition is
            # what the stagnation rule is measuring.
            loop.cancel(run_id)
            duplicate_of = previous.index(digest)
            return self._finish_iteration(
                workspace=workspace, run_id=run_id, index=index,
                run=workspace.get_run(run_id), digest=digest,
                outcome=IterationOutcome.DUPLICATE_HYPOTHESIS, budget_id=budget_id,
                proposal=proposer_record, candidate=candidate, recommendation=None,
                findings=(), details=(), duplicate_of=duplicate_of, productive=False,
                seen_finding_signatures=seen_finding_signatures,
            )

        # -- verifier half
        loop.advance(run_id)
        run = workspace.get_run(run_id)
        verifier_record = next(
            (item for item in workspace.list_proposals(run_id)
             if item.proposal_id.value.endswith(".verifier")),
            None,
        )
        if verifier_record is None:
            return self._finish_iteration(
                workspace=workspace, run_id=run_id, index=index, run=run, digest=digest,
                outcome=IterationOutcome.VERIFIER_FAILED, budget_id=budget_id,
                proposal=proposer_record, candidate=candidate, recommendation=None,
                findings=(), details=(), duplicate_of=None, productive=False,
                seen_finding_signatures=seen_finding_signatures,
            )
        finding_payload = json.loads(artifacts.get(verifier_record.artifact_hash))
        recommendation = str(finding_payload.get("recommendation", ""))
        findings = tuple(
            VerifierFinding(code=str(item["code"]), outcome=str(item["outcome"]))
            for item in finding_payload.get("findings", ())
        )
        details = tuple(str(item.get("detail", "")) for item in finding_payload.get("findings", ()))
        outcome = {
            "manual_review": IterationOutcome.AWAITING_REVIEW,
            "reject": IterationOutcome.REJECTED,
            "unresolved": IterationOutcome.UNRESOLVED,
        }.get(recommendation, IterationOutcome.UNRESOLVED)
        return self._finish_iteration(
            workspace=workspace, run_id=run_id, index=index, run=run, digest=digest,
            outcome=outcome, budget_id=budget_id, proposal=proposer_record,
            candidate=candidate, recommendation=recommendation, findings=findings,
            details=details, duplicate_of=None, productive=True,
            seen_finding_signatures=seen_finding_signatures,
        )

    def _finish_iteration(
        self,
        *,
        workspace: SQLiteWorkspace,
        run_id: OpaqueId,
        index: int,
        run: Any,
        digest: str,
        outcome: IterationOutcome,
        budget_id: OpaqueId,
        proposal: Any,
        candidate: dict[str, Any] | None,
        recommendation: str | None,
        findings: tuple[VerifierFinding, ...],
        details: tuple[str, ...],
        duplicate_of: int | None,
        productive: bool,
        seen_finding_signatures: set[str],
    ) -> _IterationResult:
        payload = (candidate or {}).get("mathematical_payload") or {}
        statement = str(payload.get("statement", ""))
        steps = tuple(str(step) for step in payload.get("steps", ()))
        result_type = str((candidate or {}).get("result_type", "none"))

        # An iteration counts as productive only if it contributed something the
        # session had not already seen: a new hypothesis AND a finding signature
        # not seen before. Both halves matter -- a fresh restatement that draws
        # the same three objections is motion without progress, and that is
        # exactly what the stagnation rule should catch.
        signature = canonical_hash(sorted(
            f"{item.code}:{item.outcome}" for item in findings
        ))
        if productive:
            new_hypothesis = digest not in self.ledger.digests
            new_signature = signature not in seen_finding_signatures
            productive = new_hypothesis and new_signature
        seen_finding_signatures.add(signature)

        manifest_hash: str | None = None
        try:
            manifest_hash = workspace.get_manifest(run_id).serialized_context_hash
        except (KeyError, ValueError):
            manifest_hash = None

        snapshot = workspace.budget(budget_id, now=self._stamp(self.now()))
        # An absent proposal has two very different causes and they must not be
        # reported as one. The model may have refused, timed out, or returned
        # output the sealed validator rejected -- that is a failure. Or this
        # iteration may simply have reached a bound it was given, which is not.
        # `exhausted_dimensions` comes from the Phase 2 budget itself, so the
        # distinction is read off the ledger rather than guessed.
        iteration_bound: str | None = None
        if outcome in {IterationOutcome.PROPOSER_FAILED, IterationOutcome.VERIFIER_FAILED}:
            stop = workspace.get_run_stop(run_id)
            expected_calls = (
                1 if outcome is IterationOutcome.PROPOSER_FAILED else 2
            )
            if (
                snapshot.exhausted_dimensions
                and (
                    snapshot.used_attempts < expected_calls
                    or (
                        stop is not None
                        and stop.stop_reason is RunStopReason.BUDGET_BOUND
                    )
                )
            ):
                iteration_bound = f"per_iteration:{snapshot.exhausted_dimensions[0]}"
                outcome = IterationOutcome.ITERATION_BUDGET_EXHAUSTED

        self.ledger.append(
            iteration_index=index,
            result_type=result_type,
            hypothesis_digest_value=digest,
            statement=statement,
            steps=steps,
            verifier_recommendation=recommendation,
            findings=findings,
            finding_details=details,
            outcome=outcome.value,
        )
        record = IterationRecord(
            iteration_index=index,
            run_id=run_id,
            branch_id=f"branch.{run_id.value}",
            hypothesis_digest=digest,
            duplicate_of_iteration=(duplicate_of + 1) if duplicate_of is not None else None,
            proposal_id=proposal.proposal_id if proposal is not None else None,
            proposal_kind=proposal.proposal_kind if proposal is not None else None,
            proposal_artifact_hash=proposal.artifact_hash if proposal is not None else None,
            verifier_manifest_hash=manifest_hash,
            verifier_recommendation=recommendation,
            findings=findings,
            outcome=outcome,
            phase2_run_status=run.status.value if run is not None else RunStatus.UNRESOLVED.value,
            usage=IterationUsage(
                model_calls=snapshot.used_attempts,
                input_tokens=snapshot.used_input_tokens,
                output_tokens=snapshot.used_output_tokens,
                cost_microusd=snapshot.used_cost_microusd,
            ),
            productive=productive,
        ).with_content_hash()

        terminal: TerminalReason | None = None
        if outcome is IterationOutcome.AWAITING_REVIEW:
            terminal = TerminalReason.AWAITING_HUMAN_REVIEW
        elif outcome is IterationOutcome.ITERATION_BUDGET_EXHAUSTED:
            terminal = TerminalReason.BUDGET_EXHAUSTED
        elif outcome in TERMINAL_ITERATION_OUTCOMES:
            terminal = TerminalReason.ITERATION_FAILED
        return _IterationResult(
            record=record, terminal_reason=terminal, exhausted_bound=iteration_bound,
        )

    # -- bounds ------------------------------------------------------------

    def _exhausted_bound(
        self, records: list[IterationRecord], started: datetime
    ) -> str | None:
        """Name the bound that forbids another iteration, or None.

        Each check reserves the *whole* per-iteration bound rather than asking
        whether anything is left. That is what makes the session bound a real
        ceiling instead of a ceiling plus one iteration's overshoot.
        """
        spent_cost = sum(item.usage.cost_microusd for item in records)
        spent_calls = sum(item.usage.model_calls for item in records)
        per_iteration = self.configuration.per_iteration_budget
        if spent_cost + per_iteration.max_cost_microusd > self.configuration.max_cost_microusd:
            return "cost_microusd"
        if spent_calls + per_iteration.max_attempts > self.configuration.max_model_calls:
            return "model_calls"
        elapsed = self._elapsed_milliseconds(started, self.now())
        if elapsed + per_iteration.max_wall_milliseconds > self.configuration.max_wall_milliseconds:
            return "wall_milliseconds"
        return None

    def _session_usage(
        self, records: list[IterationRecord], started: datetime, ended: datetime
    ) -> SessionUsage:
        return SessionUsage(
            iterations=len(records),
            model_calls=sum(item.usage.model_calls for item in records),
            input_tokens=sum(item.usage.input_tokens for item in records),
            output_tokens=sum(item.usage.output_tokens for item in records),
            cost_microusd=sum(item.usage.cost_microusd for item in records),
            elapsed_milliseconds=self._elapsed_milliseconds(started, ended),
        )

    # -- helpers -----------------------------------------------------------

    def _independence(self) -> VerifierIndependence:
        """Report the independence that actually holds, never more.

        `different_model` and `different_provider` are read off the two gateway
        configurations rather than declared, so a same-provider session cannot
        claim provider independence it does not have.
        """
        proposer = getattr(self.proposer, "config", None)
        verifier = getattr(self.verifier, "config", None)
        same_object = self.proposer is self.verifier
        proposer_model = getattr(proposer, "model_identifier", None)
        verifier_model = getattr(verifier, "model_identifier", None)
        different_model = bool(
            not same_object and proposer_model and verifier_model
            and proposer_model != verifier_model
        )
        proposer_provider = type(self.proposer).__name__
        verifier_provider = type(self.verifier).__name__
        return VerifierIndependence(
            context_isolated=True,
            separate_model_call=True,
            different_model=different_model,
            different_provider=bool(not same_object and proposer_provider != verifier_provider),
            deterministic_checker=False,
            independently_implemented_checker=False,
            formal_kernel=False,
        )

    def _persist(self, session: LeadSession) -> None:
        from .serialization import canonical_json

        path = self.root / "session.json"
        path.write_text(canonical_json(session) + "\n", encoding="utf-8")

    @staticmethod
    def _elapsed_milliseconds(start: datetime, end: datetime) -> int:
        return max(0, int((end - start).total_seconds() * 1000))

    @staticmethod
    def _stamp(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
