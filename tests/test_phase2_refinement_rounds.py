"""ADR-0041 acceptance suite: bounded refinement rounds and measured independence.

Every gateway here is an explicit per-round script. Nothing depends on the
canned even-integers proof in ``deterministic_fake_results`` being right for the
problem under test, because what is under test is the round logic, not the
mathematics.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from math_research.domain.entities import oid
from math_research.domain.policies import TrustPolicy
from math_research.interchange import export_dossier_bytes
from math_research.phase2.artifacts import FileArtifactStore
from math_research.phase2.baseline_loop import (
    BaselineResearchLoop,
    InjectedCrash,
    classify_finding,
)
from math_research.phase2.fixtures import build_open_theorem_dossier
from math_research.phase2.independence import (
    gateway_identity,
    independence_evidence,
    measure_role_independence,
)
from math_research.phase2.live_config import create_live_run_configuration
from math_research.phase2.model_gateway import ScriptedModelGateway
from math_research.phase2.pricing import create_pricing_snapshot
from math_research.phase2.provider_registry import gateway_provider
from math_research.phase2.records import (
    BudgetLimits,
    ModelResult,
    ModelResultStatus,
    ModelUsage,
    RefinementOutcomeClass,
    RunStatus,
    RunStopReason,
    VerifierIndependence,
)
from math_research.phase2.serialization import canonical_bytes, canonical_json, sha256_bytes
from math_research.phase2.sqlite_workspace import (
    RefinementRoundsExhausted,
    SealedWorkspaceError,
    SQLiteWorkspace,
)
from math_research.phase2_cli import (
    RUN_PROVIDER_CHOICES,
    _role_gateway,
    main as phase2_main,
)
from math_research.phase2.provider_registry import registered_providers


class FrozenClock:
    """Deterministic clock: identity must never depend on wall time."""

    def __init__(self) -> None:
        self.value = datetime(2026, 8, 21, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)

    def text(self) -> str:
        return self.value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def declared_independence(**overrides: bool) -> VerifierIndependence:
    values = {
        "context_isolated": True, "separate_model_call": True,
        "different_model": False, "different_provider": False,
        "deterministic_checker": False, "independently_implemented_checker": False,
        "formal_kernel": False,
    }
    values.update(overrides)
    return VerifierIndependence(**values)  # type: ignore[arg-type]


class ProviderScriptedGateway(ScriptedModelGateway):
    """A scripted gateway that also declares a provider and model identity.

    Needed to exercise measured cross-provider independence offline: a real
    adapter would require a billed call, and this repository never makes one in
    a test.
    """

    class Config:
        def __init__(self, provider: str, model_identifier: str) -> None:
            self.provider = provider
            self.model_identifier = model_identifier
            self.capabilities: tuple[str, ...] = ("structured_output",)

    def __init__(self, scripts, *, provider: str, model_identifier: str) -> None:
        super().__init__(scripts)
        self.config = ProviderScriptedGateway.Config(provider, model_identifier)


# --- scripted round content -------------------------------------------------


def candidate_payload(target: str, premise: str, tag: str) -> dict[str, object]:
    return {
        "schema_version": "2.0.0",
        "result_type": "proof_attempt",
        "target_claim_id": target,
        "mathematical_payload": {
            "statement": f"Candidate attempt {tag} for the approved target.",
            "steps": [f"Step one of attempt {tag}.", f"Step two of attempt {tag}."],
            "witness": f"witness-{tag}",
        },
        "declared_rationale": f"Declared rationale for attempt {tag}.",
        "referenced_entity_ids": [premise],
    }


def committed_candidate_hash(payload: dict[str, object]) -> str:
    """The hash of the artifact the loop actually commits.

    The proposer's declared rationale is stripped before the candidate is
    stored, so a scripted verifier must target the stripped bytes.
    """
    stored = {key: value for key, value in payload.items() if key != "declared_rationale"}
    return sha256_bytes(canonical_bytes(stored))


def finding_payload(
    target: str, premise: str, candidate_hash: str, *,
    outcome: str, recommendation: str, result_type: str = "finding", tag: str = "1",
) -> dict[str, object]:
    return {
        "schema_version": "2.0.0",
        "result_type": result_type,
        "target_claim_id": target,
        "candidate_artifact_hash": candidate_hash,
        "findings": [{
            "code": f"round-{tag}-check",
            "outcome": outcome,
            "detail": f"Isolated finding detail for round {tag}.",
            "referenced_entity_ids": [premise],
        }],
        "declared_rationale": f"Isolated verifier rationale for round {tag}.",
        "recommendation": recommendation,
    }


def scripted_result(payload: dict[str, object], *, input_tokens: int, output_tokens: int) -> ModelResult:
    return ModelResult(
        status=ModelResultStatus.SUCCEEDED, provider="scripted",
        model_identifier="scripted-v1", capabilities=("structured_output", "deterministic"),
        structured_output=canonical_json(payload),
        declared_rationale=str(payload["declared_rationale"]), refusal=None,
        usage=ModelUsage(
            input_tokens=input_tokens, output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens, usage_source="fixture",
        ),
        retry_classification="none",
    )


class RoundCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.clock = FrozenClock()
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.artifacts = FileArtifactStore(self.root / "artifacts")
        self.dossier = build_open_theorem_dossier()
        self.target = self.dossier.formalization.target_claim_id.value
        self.premise = self.dossier.formalization.assumption_claim_ids[0].value

    def tearDown(self) -> None:
        self.workspace.close()
        self.temporary.cleanup()

    def limits(self, **overrides: int) -> BudgetLimits:
        values: dict[str, int] = {
            "max_input_tokens": 100_000, "max_output_tokens": 100_000,
            "max_cost_microusd": 1_000_000, "max_wall_milliseconds": 600_000,
            "max_attempts": 20, "max_refinement_rounds": 1,
        }
        values.update(overrides)
        return BudgetLimits(**values)  # type: ignore[arg-type]

    def candidate(self, tag: str) -> dict[str, object]:
        return candidate_payload(self.target, self.premise, tag)

    def script(self, rounds: tuple[tuple[str, str, str], ...]) -> dict[str, list[ModelResult]]:
        """Build a per-round script from ``(tag, outcome, recommendation)``."""
        proposer: list[ModelResult] = []
        verifier: list[ModelResult] = []
        for index, (tag, outcome, recommendation) in enumerate(rounds, start=1):
            payload = self.candidate(tag)
            proposer.append(scripted_result(payload, input_tokens=120, output_tokens=80))
            verifier.append(scripted_result(
                finding_payload(
                    self.target, self.premise, committed_candidate_hash(payload),
                    outcome=outcome, recommendation=recommendation, tag=str(index),
                ),
                input_tokens=160, output_tokens=90,
            ))
        return {"proposer": proposer, "verifier": verifier}

    def loop(self, scripts, **kwargs) -> tuple[BaselineResearchLoop, ScriptedModelGateway]:
        gateway = ScriptedModelGateway(scripts)
        loop = BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=gateway, verifier=gateway, independence=declared_independence(),
            now=self.clock, **kwargs,
        )
        return loop, gateway


class RefinementTriggerTests(RoundCase):
    def test_classification_is_derived_only_from_schema_fields(self) -> None:
        cases = (
            ("supports", "manual_review", "finding", RefinementOutcomeClass.SUPPORTING),
            ("contradicts", "manual_review", "finding", RefinementOutcomeClass.REFUTING),
            ("supports", "reject", "finding", RefinementOutcomeClass.REFUTING),
            ("unresolved", "unresolved", "finding", RefinementOutcomeClass.DEFECTIVE),
            ("supports", "unresolved", "finding", RefinementOutcomeClass.DEFECTIVE),
            ("supports", "manual_review", "inconclusive", RefinementOutcomeClass.DEFECTIVE),
            ("supports", "manual_review", "failure", RefinementOutcomeClass.DEFECTIVE),
        )
        for outcome, recommendation, result_type, expected in cases:
            with self.subTest(outcome=outcome, recommendation=recommendation, result_type=result_type):
                payload = finding_payload(
                    self.target, self.premise, "sha256:" + "0" * 64,
                    outcome=outcome, recommendation=recommendation, result_type=result_type,
                )
                observed = classify_finding(payload)
                self.assertEqual(observed, expected)
                self.assertEqual(
                    observed.warrants_refinement,
                    expected in {RefinementOutcomeClass.REFUTING, RefinementOutcomeClass.DEFECTIVE},
                )

    def test_empty_findings_are_indeterminate_and_never_refine(self) -> None:
        payload = finding_payload(
            self.target, self.premise, "sha256:" + "0" * 64,
            outcome="supports", recommendation="manual_review",
        )
        payload["findings"] = []
        self.assertEqual(classify_finding(payload), RefinementOutcomeClass.INDETERMINATE)
        self.assertFalse(classify_finding(payload).warrants_refinement)

    def test_supporting_round_one_does_not_enqueue_a_pointless_round(self) -> None:
        loop, gateway = self.loop(self.script((("a", "supports", "manual_review"),)))
        run = loop.start(
            run_id=oid("run.rounds.supporting.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=3),
        )
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.AWAITING_REVIEW)
        self.assertEqual(gateway.call_count, 2)
        rounds = self.workspace.list_refinement_rounds(run.run_id)
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0].outcome_class, RefinementOutcomeClass.SUPPORTING)
        self.assertFalse(rounds[0].refinement_warranted)
        stop = self.workspace.get_run_stop(run.run_id)
        self.assertEqual(stop.stop_reason, RunStopReason.NO_REFINEMENT_WARRANTED)
        self.assertIsNone(stop.stop_bound)
        self.assertEqual(
            self.workspace.budget(run.budget_id, now=self.clock.text()).used_refinement_rounds, 1,
        )


class ConvergingRunTests(RoundCase):
    def test_refuting_round_one_is_repaired_and_converges_on_round_two(self) -> None:
        before = export_dossier_bytes(self.dossier)
        scripts = self.script((
            ("broken", "contradicts", "reject"),
            ("repaired", "supports", "manual_review"),
        ))
        loop, gateway = self.loop(scripts)
        run = loop.start(
            run_id=oid("run.rounds.converge.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=2),
        )
        final = loop.run_to_terminal(run.run_id)

        self.assertEqual(final.status, RunStatus.AWAITING_REVIEW)
        self.assertEqual(gateway.call_count, 4)
        rounds = self.workspace.list_refinement_rounds(run.run_id)
        self.assertEqual([item.round_index for item in rounds], [1, 2])
        self.assertEqual(
            [item.outcome_class for item in rounds],
            [RefinementOutcomeClass.REFUTING, RefinementOutcomeClass.SUPPORTING],
        )
        self.assertEqual([item.refinement_warranted for item in rounds], [True, False])
        stop = self.workspace.get_run_stop(run.run_id)
        self.assertEqual(stop.stop_reason, RunStopReason.NO_REFINEMENT_WARRANTED)
        self.assertEqual(stop.rounds_used, 2)

        # Four durable jobs, two per round, each labelled with its round.
        jobs = self.workspace.list_jobs(run.run_id)
        self.assertEqual(
            sorted((item.kind, item.round_index) for item in jobs),
            [("proposer", 1), ("proposer", 2), ("verifier", 1), ("verifier", 2)],
        )
        self.assertEqual(len({item.job_id.value for item in jobs}), 4)
        self.assertEqual(len({item.idempotency_key for item in jobs}), 4)

        proposals = self.workspace.list_proposals(run.run_id)
        self.assertEqual(len(proposals), 4)
        self.assertEqual({item.disposition for item in proposals}, {"proposal"})
        self.assertEqual(len({item.proposal_id.value for item in proposals}), 4)
        calls = self.workspace.list_model_calls(run.run_id)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len({item["call_id"] for item in calls}), 4)
        self.assertEqual(len({item["idempotency_key"] for item in calls}), 4)

        # The trust core is untouched: four proposals, still no warrant.
        replayed = self.workspace.load_dossier(run.dossier_id)
        self.assertEqual(export_dossier_bytes(replayed), before)
        self.assertEqual(TrustPolicy(replayed).target_resolution().logical_status, "unknown")

        events = [item["event_type"] for item in self.workspace.timeline(run.run_id)]
        self.assertEqual(events.count("refinement_round_enqueued"), 1)
        self.assertEqual(events.count("proposal_imported"), 4)

    def test_round_two_proposer_receives_the_round_one_findings(self) -> None:
        scripts = self.script((
            ("broken", "contradicts", "reject"),
            ("repaired", "supports", "manual_review"),
        ))
        loop, gateway = self.loop(scripts)
        run = loop.start(
            run_id=oid("run.rounds.context.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=2),
        )
        loop.run_to_terminal(run.run_id)
        first_proposer = json.loads(gateway.requests[0].serialized_context)
        second_proposer = json.loads(gateway.requests[2].serialized_context)

        # Round one is byte-identical in shape to the pre-ADR-0041 context.
        self.assertNotIn("refinement", first_proposer)
        self.assertIn("refinement", second_proposer)
        refinement = second_proposer["refinement"]
        self.assertEqual(refinement["round_index"], 2)
        self.assertEqual(refinement["max_refinement_rounds"], 2)
        self.assertEqual([item["round_index"] for item in refinement["prior_rounds"]], [1])
        prior = refinement["prior_rounds"][0]
        self.assertEqual(prior["outcome_class"], "refuting")
        self.assertEqual(prior["verifier_finding"]["recommendation"], "reject")
        self.assertEqual(prior["verifier_finding"]["findings"][0]["outcome"], "contradicts")
        self.assertEqual(prior["candidate"]["mathematical_payload"]["witness"], "witness-broken")
        # The proposer's own earlier rationale is not carried forward: only the
        # committed candidate artifact is, and that never held the rationale.
        self.assertNotIn("declared_rationale", prior["candidate"])

        # Rounds after the first use their own versioned, hashed template.
        self.assertEqual(gateway.requests[0].template_id, "phase2.proposer")
        self.assertEqual(gateway.requests[2].template_id, "phase2.proposer_refinement")
        self.assertNotEqual(gateway.requests[0].template_hash, gateway.requests[2].template_hash)

    def test_token_and_cost_accounting_aggregate_across_rounds(self) -> None:
        scripts = self.script((
            ("broken", "contradicts", "reject"),
            ("repaired", "supports", "manual_review"),
        ))
        loop, _ = self.loop(scripts)
        run = loop.start(
            run_id=oid("run.rounds.accounting.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=2),
        )
        loop.run_to_terminal(run.run_id)
        budget = self.workspace.budget(run.budget_id, now=self.clock.text())
        calls = self.workspace.list_model_calls(run.run_id)
        self.assertEqual(budget.used_input_tokens, sum(int(item["input_tokens"]) for item in calls))
        self.assertEqual(budget.used_output_tokens, sum(int(item["output_tokens"]) for item in calls))
        self.assertEqual(budget.used_input_tokens, 2 * (120 + 160))
        self.assertEqual(budget.used_output_tokens, 2 * (80 + 90))
        self.assertEqual(budget.used_attempts, 4)
        self.assertEqual(budget.used_refinement_rounds, 2)


class RoundCapTests(RoundCase):
    def test_exhausting_the_declared_cap_is_its_own_terminal_state(self) -> None:
        scripts = self.script((
            ("first", "contradicts", "reject"),
            ("second", "contradicts", "reject"),
        ))
        loop, gateway = self.loop(scripts)
        run = loop.start(
            run_id=oid("run.rounds.cap.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=2),
        )
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.REFINEMENT_EXHAUSTED)
        self.assertNotEqual(final.status, RunStatus.UNRESOLVED)
        self.assertEqual(gateway.call_count, 4)
        stop = self.workspace.get_run_stop(run.run_id)
        self.assertEqual(stop.stop_reason, RunStopReason.REFINEMENT_ROUND_CAP)
        self.assertEqual(stop.stop_bound, "refinement_rounds")
        self.assertEqual(stop.binding_bounds, ("refinement_rounds",))
        self.assertEqual((stop.rounds_used, stop.max_refinement_rounds), (2, 2))
        self.assertEqual(len(self.workspace.list_refinement_rounds(run.run_id)), 2)
        # The trust core still says nothing.
        self.assertEqual(
            TrustPolicy(self.workspace.load_dossier(run.dossier_id)).target_resolution().logical_status,
            "unknown",
        )

    def test_default_cap_of_one_keeps_the_single_round_shape(self) -> None:
        loop, gateway = self.loop(self.script((("only", "contradicts", "reject"),)))
        run = loop.start(
            run_id=oid("run.rounds.default.v1"), dossier=self.dossier, limits=self.limits(),
        )
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.REFINEMENT_EXHAUSTED)
        self.assertEqual(gateway.call_count, 2)
        stop = self.workspace.get_run_stop(run.run_id)
        self.assertEqual((stop.rounds_used, stop.max_refinement_rounds), (1, 1))
        self.assertEqual(stop.stop_bound, "refinement_rounds")

    def test_cap_is_recorded_at_run_creation_and_cannot_be_rewritten(self) -> None:
        loop, _ = self.loop(self.script((("a", "supports", "manual_review"),)))
        run = loop.start(
            run_id=oid("run.rounds.declared.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=4),
        )
        self.assertEqual(
            self.workspace.budget(run.budget_id, now=self.clock.text()).limits.max_refinement_rounds, 4,
        )
        with self.assertRaises(ValueError):
            self.workspace.create_run(
                run_id=run.run_id, dossier=self.dossier, budget_id=run.budget_id,
                limits=self.limits(max_refinement_rounds=9), now=self.clock.text(),
            )

    def test_workspace_refuses_a_round_beyond_the_cap(self) -> None:
        loop, _ = self.loop(self.script((("a", "supports", "manual_review"),)))
        run = loop.start(
            run_id=oid("run.rounds.reserve.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=2),
        )
        self.workspace.reserve_refinement_round(run.budget_id, round_index=2, now=self.clock.text())
        # Replaying an already granted round consumes nothing.
        self.workspace.reserve_refinement_round(run.budget_id, round_index=2, now=self.clock.text())
        self.assertEqual(
            self.workspace.budget(run.budget_id, now=self.clock.text()).used_refinement_rounds, 2,
        )
        with self.assertRaises(RefinementRoundsExhausted) as raised:
            self.workspace.reserve_refinement_round(run.budget_id, round_index=3, now=self.clock.text())
        self.assertEqual(raised.exception.max_refinement_rounds, 2)

    def test_a_never_converging_run_terminates_without_an_explicit_step_bound(self) -> None:
        scripts = self.script((
            ("one", "contradicts", "reject"),
            ("two", "contradicts", "reject"),
            ("three", "contradicts", "reject"),
            ("four", "contradicts", "reject"),
        ))
        loop, gateway = self.loop(scripts)
        run = loop.start(
            run_id=oid("run.rounds.never.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=3),
        )
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.REFINEMENT_EXHAUSTED)
        # Three rounds ran and the fourth script was never reached.
        self.assertEqual(gateway.call_count, 6)
        self.assertEqual(len(self.workspace.list_refinement_rounds(run.run_id)), 3)
        # Advancing a terminal run changes nothing.
        self.assertEqual(loop.advance(run.run_id).status, RunStatus.REFINEMENT_EXHAUSTED)
        self.assertEqual(len(self.workspace.list_model_calls(run.run_id)), 6)


class BudgetBoundTests(RoundCase):
    def pricing(self):
        # Zero input rate so the pre-call reserve estimate stays affordable while
        # the measured per-round cost is still positive. Exact integers only.
        snapshot = create_pricing_snapshot(
            snapshot_id=oid("pricing.rounds.test.v1"), provider="openai",
            model_identifier="scripted-v1", source="fixture rates for ADR-0041 tests",
            captured_at="2026-08-21T00:00:00Z", currency="USD",
            input_microusd_per_million_tokens=0,
            output_microusd_per_million_tokens=1_000,
        )
        self.workspace.save_pricing_snapshot(
            snapshot, canonical_json=canonical_json(snapshot), now=self.clock.text(),
        )
        return snapshot

    def test_cost_budget_stops_the_run_before_the_round_cap_does(self) -> None:
        scripts = self.script((
            ("first", "contradicts", "reject"),
            ("second", "contradicts", "reject"),
        ))
        loop, gateway = self.loop(scripts, pricing_snapshot=self.pricing())
        run = loop.start(
            run_id=oid("run.rounds.cost.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=5, max_cost_microusd=3),
        )
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.REFINEMENT_EXHAUSTED)
        self.assertEqual(gateway.call_count, 2)
        stop = self.workspace.get_run_stop(run.run_id)
        # The money, not the counter, is what stopped it -- and it is named.
        self.assertEqual(stop.stop_reason, RunStopReason.BUDGET_BOUND)
        self.assertEqual(stop.stop_bound, "cost")
        self.assertIn("cost", stop.binding_bounds)
        self.assertNotIn("refinement_rounds", stop.binding_bounds)
        self.assertEqual((stop.rounds_used, stop.max_refinement_rounds), (1, 5))
        budget = self.workspace.budget(run.budget_id, now=self.clock.text())
        self.assertEqual(budget.used_refinement_rounds, 1)
        self.assertGreater(budget.used_cost_microusd, 0)

    def test_generous_cost_budget_lets_the_round_cap_be_the_bound(self) -> None:
        scripts = self.script((
            ("first", "contradicts", "reject"),
            ("second", "contradicts", "reject"),
        ))
        loop, gateway = self.loop(scripts, pricing_snapshot=self.pricing())
        run = loop.start(
            run_id=oid("run.rounds.cost-ok.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=2, max_cost_microusd=1_000_000),
        )
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.REFINEMENT_EXHAUSTED)
        self.assertEqual(gateway.call_count, 4)
        stop = self.workspace.get_run_stop(run.run_id)
        self.assertEqual(stop.stop_bound, "refinement_rounds")


class CrashReplayTests(RoundCase):
    def test_crash_inside_round_two_replays_without_double_committing(self) -> None:
        scripts = self.script((
            ("broken", "contradicts", "reject"),
            ("repaired", "supports", "manual_review"),
        ))
        # One extra round-two proposer response: the crashed attempt consumes one.
        scripts["proposer"].insert(1, scripts["proposer"][1])
        gateway = ScriptedModelGateway(scripts)
        loop = BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=gateway, verifier=gateway, independence=declared_independence(),
            now=self.clock,
        )
        run = loop.start(
            run_id=oid("run.rounds.crash.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=2),
        )
        # Finish round one, then crash after round two's artifact exists but
        # before its semantic commit.
        loop.advance(run.run_id)
        loop.advance(run.run_id)
        self.assertEqual(len(self.workspace.list_proposals(run.run_id)), 2)
        loop.fault_after_proposal_artifact_once = True
        with self.assertRaises(InjectedCrash):
            loop.advance(run.run_id)
        self.assertEqual(len(self.workspace.list_proposals(run.run_id)), 2)

        self.clock.advance(31)
        self.workspace.close()
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        recovered = self.workspace.recover_jobs(now=self.clock.text())
        round_two_proposer = next(
            item for item in recovered
            if item.run_id == run.run_id and item.kind == "proposer" and item.round_index == 2
        )
        self.assertEqual(round_two_proposer.attempts, 1)
        resumed = BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=gateway, verifier=gateway, independence=declared_independence(),
            now=self.clock,
        )
        final = resumed.run_to_terminal(run.run_id)

        self.assertEqual(final.status, RunStatus.AWAITING_REVIEW)
        proposals = self.workspace.list_proposals(run.run_id)
        self.assertEqual(len(proposals), 4)
        self.assertEqual(len({item.proposal_id.value for item in proposals}), 4)
        imported = [
            item for item in self.workspace.timeline(run.run_id)
            if item["event_type"] == "proposal_imported"
        ]
        self.assertEqual(len(imported), 4)
        self.assertEqual(len({item["idempotency_key"] for item in imported}), 4)
        rounds = self.workspace.list_refinement_rounds(run.run_id)
        self.assertEqual([item.round_index for item in rounds], [1, 2])
        # Both attempts of round two are preserved; the failure is not erased.
        calls = self.workspace.list_model_calls(run.run_id)
        self.assertEqual(len(calls), 5)
        self.assertEqual(
            sorted(
                item["call_id"] for item in calls
                if ".proposer.round.2." in str(item["call_id"])
            ),
            [
                f"call.{run.run_id.value}.proposer.round.2.attempt.1",
                f"call.{run.run_id.value}.proposer.round.2.attempt.2",
            ],
        )
        self.assertEqual(
            self.workspace.budget(run.budget_id, now=self.clock.text()).used_refinement_rounds, 2,
        )

    def test_replaying_a_finished_multi_round_run_commits_nothing_new(self) -> None:
        scripts = self.script((
            ("broken", "contradicts", "reject"),
            ("repaired", "supports", "manual_review"),
        ))
        loop, _ = self.loop(scripts)
        run = loop.start(
            run_id=oid("run.rounds.replay.v1"), dossier=self.dossier,
            limits=self.limits(max_refinement_rounds=2),
        )
        loop.run_to_terminal(run.run_id)
        before = (
            self.workspace.list_proposals(run.run_id),
            self.workspace.list_jobs(run.run_id),
            self.workspace.timeline(run.run_id),
            self.workspace.list_refinement_rounds(run.run_id),
            self.workspace.get_run_stop(run.run_id),
        )
        loop.run_to_terminal(run.run_id)
        loop.advance(run.run_id)
        after = (
            self.workspace.list_proposals(run.run_id),
            self.workspace.list_jobs(run.run_id),
            self.workspace.timeline(run.run_id),
            self.workspace.list_refinement_rounds(run.run_id),
            self.workspace.get_run_stop(run.run_id),
        )
        self.assertEqual(before, after)


class PerRoundManifestTests(RoundCase):
    def completed_two_rounds(self, run_id: str):
        scripts = self.script((
            ("broken", "contradicts", "reject"),
            ("repaired", "supports", "manual_review"),
        ))
        loop, gateway = self.loop(scripts)
        run = loop.start(
            run_id=oid(run_id), dossier=self.dossier, limits=self.limits(max_refinement_rounds=2),
        )
        loop.run_to_terminal(run.run_id)
        return run, gateway

    def test_each_round_records_its_own_manifest(self) -> None:
        run, gateway = self.completed_two_rounds("run.rounds.manifests.v1")
        manifests = self.workspace.list_manifests(run.run_id)
        self.assertEqual([item.round_index for item in manifests], [1, 2])
        self.assertEqual(len({item.manifest_id.value for item in manifests}), 2)
        self.assertEqual(len({item.serialized_context_hash for item in manifests}), 2)
        # Each manifest is the exact bytes that round's verifier was handed.
        for index, manifest in enumerate(manifests):
            serialized = gateway.requests[2 * index + 1].serialized_context.encode("utf-8")
            self.assertEqual(manifest.serialized_context_hash, sha256_bytes(serialized))
            self.assertEqual(self.artifacts.get(manifest.context_artifact_hash), serialized)
        # The default lookup answers with the latest round; a round may be named.
        self.assertEqual(self.workspace.get_manifest(run.run_id).round_index, 2)
        self.assertEqual(self.workspace.get_manifest(run.run_id, round_index=1).round_index, 1)
        with self.assertRaises(KeyError):
            self.workspace.get_manifest(run.run_id, round_index=3)

    def test_round_two_verifier_gains_no_prior_round_material(self) -> None:
        run, gateway = self.completed_two_rounds("run.rounds.isolation.v1")
        first_verifier = json.loads(gateway.requests[1].serialized_context)
        second_verifier_text = gateway.requests[3].serialized_context
        second_verifier = json.loads(second_verifier_text)
        # Identical key set in both rounds: no new channel opened by round two.
        self.assertEqual(set(first_verifier), set(second_verifier))
        self.assertNotIn("refinement", second_verifier)
        # Nothing from round one leaks: not the finding, not the old candidate,
        # not the proposer's narrative.
        self.assertNotIn("Isolated finding detail for round 1", second_verifier_text)
        self.assertNotIn("witness-broken", second_verifier_text)
        self.assertNotIn("declared_rationale", second_verifier["candidate"])
        self.assertNotIn("Declared rationale for attempt", second_verifier_text)

        manifest = self.workspace.get_manifest(run.run_id, round_index=2)
        excluded = {item.value for item in manifest.excluded_entity_ids}
        included = {item.value for item in manifest.included_entity_ids}
        rounds = self.workspace.list_refinement_rounds(run.run_id)
        self.assertEqual(manifest.candidate_shaped_by_rounds, (1,))
        self.assertEqual(
            manifest.withheld_prior_finding_hashes, (rounds[0].finding_artifact_hash,),
        )
        # Round one keeps its pre-ADR-0041 identity so sealed evidence stays
        # reproducible; the round is carried by jobs.round_index and the ledger.
        for value in (
            f"proposal.{run.run_id.value}.proposer",
            f"proposal.{run.run_id.value}.verifier",
            f"call.{run.run_id.value}.proposer.attempt.1",
            f"call.{run.run_id.value}.verifier.attempt.1",
            f"call.{run.run_id.value}.proposer.round.2.attempt.1",
        ):
            self.assertIn(value, excluded)
            self.assertNotIn(value, included)
        self.assertIn(f"proposal.{run.run_id.value}.proposer.round.2", included)
        self.assertEqual(included & excluded, set())

    def test_round_one_manifest_records_no_prior_shaping(self) -> None:
        run, _ = self.completed_two_rounds("run.rounds.first-manifest.v1")
        manifest = self.workspace.get_manifest(run.run_id, round_index=1)
        self.assertEqual(manifest.candidate_shaped_by_rounds, ())
        self.assertEqual(manifest.withheld_prior_finding_hashes, ())

    def test_manifests_are_immutable(self) -> None:
        run, _ = self.completed_two_rounds("run.rounds.immutable.v1")
        manifest = self.workspace.get_manifest(run.run_id, round_index=2)
        tampered = canonical_json({**json.loads(canonical_json(manifest)), "policy_version": "other"})
        with self.assertRaises(ValueError):
            self.workspace.save_manifest(manifest, canonical_json=tampered, now=self.clock.text())


class MeasuredIndependenceTests(RoundCase):
    def cross_provider_loop(self, scripts):
        proposer = ProviderScriptedGateway(
            {"proposer": scripts["proposer"]}, provider="openai", model_identifier="model-a",
        )
        verifier = ProviderScriptedGateway(
            {"verifier": scripts["verifier"]}, provider="anthropic", model_identifier="model-b",
        )
        loop = BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=proposer, verifier=verifier,
            # An operator asserting a formal kernel it does not have is a
            # separate, still-open gap; the two role axes are what is measured.
            independence=declared_independence(),
            now=self.clock,
        )
        return loop, proposer, verifier

    def test_cross_provider_run_records_measured_difference(self) -> None:
        loop, proposer, verifier = self.cross_provider_loop(
            self.script((("a", "supports", "manual_review"),))
        )
        self.assertTrue(loop.independence.different_provider)
        self.assertTrue(loop.independence.different_model)
        run = loop.start(
            run_id=oid("run.rounds.cross.v1"), dossier=self.dossier, limits=self.limits(),
        )
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.AWAITING_REVIEW)
        manifest = self.workspace.get_manifest(run.run_id)
        self.assertTrue(manifest.independence.different_provider)
        self.assertTrue(manifest.independence.different_model)
        self.assertTrue(manifest.independence.context_isolated)
        self.assertTrue(manifest.independence.separate_model_call)
        # Still not fully independent: the checker is not independently
        # implemented, and that dimension is not something the loop can measure.
        self.assertFalse(manifest.independence.fully_independent)
        evidence = independence_evidence(
            loop.independence, proposer=proposer, verifier=verifier,
        )
        self.assertEqual(evidence["proposer"], {"provider": "openai", "model_identifier": "model-a"})
        self.assertEqual(evidence["verifier"], {"provider": "anthropic", "model_identifier": "model-b"})
        self.assertFalse(evidence["same_gateway_object"])

    def test_same_provider_run_records_no_difference(self) -> None:
        scripts = self.script((("a", "supports", "manual_review"),))
        proposer = ProviderScriptedGateway(
            {"proposer": scripts["proposer"]}, provider="openai", model_identifier="model-a",
        )
        verifier = ProviderScriptedGateway(
            {"verifier": scripts["verifier"]}, provider="openai", model_identifier="model-a",
        )
        loop = BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=proposer, verifier=verifier, independence=declared_independence(),
            now=self.clock,
        )
        run = loop.start(
            run_id=oid("run.rounds.same.v1"), dossier=self.dossier, limits=self.limits(),
        )
        loop.run_to_terminal(run.run_id)
        manifest = self.workspace.get_manifest(run.run_id)
        self.assertFalse(manifest.independence.different_provider)
        self.assertFalse(manifest.independence.different_model)
        self.assertFalse(manifest.independence.fully_independent)

    def test_operator_assertion_cannot_manufacture_independence(self) -> None:
        scripts = self.script((("a", "supports", "manual_review"),))
        proposer = ProviderScriptedGateway(
            {"proposer": scripts["proposer"]}, provider="openai", model_identifier="model-a",
        )
        verifier = ProviderScriptedGateway(
            {"verifier": scripts["verifier"]}, provider="openai", model_identifier="model-a",
        )
        asserted = declared_independence(different_provider=True, different_model=True)
        loop = BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=proposer, verifier=verifier, independence=asserted, now=self.clock,
        )
        self.assertTrue(loop.declared_independence.different_provider)
        self.assertFalse(loop.independence.different_provider)
        self.assertFalse(loop.independence.different_model)
        run = loop.start(
            run_id=oid("run.rounds.asserted.v1"), dossier=self.dossier, limits=self.limits(),
        )
        loop.run_to_terminal(run.run_id)
        recorded = self.workspace.get_manifest(run.run_id).independence
        self.assertFalse(recorded.different_provider)
        self.assertFalse(recorded.different_model)
        self.assertFalse(recorded.fully_independent)

    def test_one_gateway_for_both_roles_is_never_independent(self) -> None:
        gateway = ProviderScriptedGateway({}, provider="openai", model_identifier="model-a")
        measured = measure_role_independence(
            declared_independence(different_provider=True, different_model=True),
            proposer=gateway, verifier=gateway,
        )
        self.assertFalse(measured.different_provider)
        self.assertFalse(measured.different_model)

    def test_unresolvable_identity_refuses_the_claim(self) -> None:
        proposer = ScriptedModelGateway({})
        verifier = ScriptedModelGateway({})
        self.assertIsNone(gateway_identity(proposer))
        measured = measure_role_independence(
            declared_independence(different_provider=True, different_model=True),
            proposer=proposer, verifier=verifier,
        )
        self.assertFalse(measured.different_provider)
        self.assertFalse(measured.different_model)


def role_configuration(provider: str, model: str):
    """A content-hashed configuration bound to its own pinned snapshot."""
    return create_live_run_configuration(
        configuration_id=oid(f"config.{provider}.roles.v1"), provider=provider,
        model_identifier=model, pricing_snapshot_id=oid(f"pricing.{provider}.roles.v1"),
        call_timeout_milliseconds=60_000, per_call_input_token_reserve=1_000,
        per_call_output_token_reserve=1_000,
        budget=BudgetLimits(
            max_input_tokens=10_000, max_output_tokens=2_000,
            max_cost_microusd=10_000, max_wall_milliseconds=60_000, max_attempts=4,
        ),
    )


def role_pricing(configuration):
    """Arbitrary test-only rates. No real price is asserted anywhere here."""
    return create_pricing_snapshot(
        snapshot_id=configuration.pricing_snapshot_id,
        provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        source="test-only recorded rate; not a quoted price",
        captured_at="2026-08-21T00:00:00Z", currency="USD",
        input_microusd_per_million_tokens=1_000,
        output_microusd_per_million_tokens=2_000,
    )


class RoleRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dossier = build_open_theorem_dossier()

    def test_each_role_routes_to_its_own_adapter(self) -> None:
        from math_research.phase2.anthropic_gateway import AnthropicMessagesGateway
        from math_research.phase2.model_gateway import OpenAIResponsesGateway

        proposer_configuration = role_configuration("openai", "gpt-5-mini")
        verifier_configuration = role_configuration("anthropic", "claude-opus-5")
        environment = {"OPENAI_API_KEY": "sk-example", "ANTHROPIC_API_KEY": "sk-example"}
        with patch.dict(os.environ, environment, clear=False):
            proposer = _role_gateway(
                "openai", proposer_configuration, role_pricing(proposer_configuration),
                "proposer", self.dossier,
            )
            verifier = _role_gateway(
                "anthropic", verifier_configuration, role_pricing(verifier_configuration),
                "verifier", self.dossier,
            )
        self.assertIsInstance(proposer, OpenAIResponsesGateway)
        self.assertIsInstance(verifier, AnthropicMessagesGateway)
        self.assertEqual(gateway_provider(proposer), "openai")
        self.assertEqual(gateway_provider(verifier), "anthropic")
        measured = measure_role_independence(
            declared_independence(), proposer=proposer, verifier=verifier,
        )
        self.assertTrue(measured.different_provider)
        self.assertTrue(measured.different_model)

    def test_a_live_role_without_a_configuration_fails_closed(self) -> None:
        with self.assertRaises(RuntimeError):
            _role_gateway("openai", None, None, "verifier", self.dossier)

    def test_the_verifier_role_passes_the_same_binding_gate(self) -> None:
        configuration = role_configuration("openai", "gpt-5-mini")
        mismatched = role_pricing(role_configuration("openai", "other-model"))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-example"}, clear=False):
            with self.assertRaises(RuntimeError):
                # Selected provider is not the configured provider.
                _role_gateway("anthropic", configuration, role_pricing(configuration),
                              "verifier", self.dossier)
            with self.assertRaises(RuntimeError):
                # Snapshot is not the one the configuration names.
                _role_gateway("openai", configuration, mismatched, "verifier", self.dossier)


class RunPathSurfaceTests(unittest.TestCase):
    """The declared cap and the verifier role, exercised through the CLI.

    Every invocation here uses the scripted `fake` provider. No socket is opened
    and no provider is called.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(self, argv: list[str]) -> tuple[int, object]:
        output = io.StringIO()
        with redirect_stdout(output):
            status = phase2_main(argv)
        text = output.getvalue()
        try:
            return status, json.loads(text)
        except json.JSONDecodeError:
            return status, text

    def test_verifier_provider_choices_are_derived_from_the_registry(self) -> None:
        # Same derivation as --provider: a provider admitted at the model
        # boundary must be selectable for either role without a further edit.
        source = Path("src/math_research/phase2_cli.py").read_text(encoding="utf-8")
        self.assertIn('item.add_argument("--verifier-provider", choices=RUN_PROVIDER_CHOICES)', source)
        self.assertEqual(("fake", *registered_providers()), RUN_PROVIDER_CHOICES)

    def test_declared_cap_is_recorded_and_surfaced(self) -> None:
        status, _ = self.invoke([
            "start", str(self.root), "run.cli.rounds.v1", "--execute",
            "--max-refinement-rounds", "3",
        ])
        self.assertEqual(status, 0)
        status, value = self.invoke(["rounds", str(self.root), "run.cli.rounds.v1"])
        self.assertEqual(status, 0)
        self.assertEqual(value["budget"]["limits"]["max_refinement_rounds"], 3)
        self.assertEqual(value["budget"]["used_refinement_rounds"], 1)
        self.assertEqual(len(value["refinement_rounds"]), 1)
        self.assertEqual(value["run_stop"]["stop_reason"], "no_refinement_warranted")
        self.assertIsNone(value["run_stop"]["stop_bound"])
        self.assertEqual(len(value["verifier_context_manifests"]), 1)

    def test_a_cap_below_one_is_refused_and_no_run_is_created(self) -> None:
        status, value = self.invoke([
            "start", str(self.root), "run.cli.badcap.v1", "--max-refinement-rounds", "0",
        ])
        self.assertEqual(status, 2)
        self.assertEqual(
            value["failed_checks"], ["--max-refinement-rounds must be at least 1"],
        )
        with SQLiteWorkspace(self.root / "workspace.sqlite3") as workspace:
            with self.assertRaises(KeyError):
                workspace.get_run(oid("run.cli.badcap.v1"))

    def test_verifier_inputs_without_a_verifier_provider_are_refused(self) -> None:
        status, value = self.invoke([
            "start", str(self.root), "run.cli.orphan.v1",
            "--verifier-config", str(self.root / "absent.json"),
        ])
        self.assertEqual(status, 2)
        self.assertIn("--verifier-provider", value["missing_variables"])
        self.assertTrue(
            any("verifier_inputs_without_verifier_provider" in item
                for item in value["failed_checks"])
        )

    def test_a_scripted_verifier_cannot_be_given_live_inputs(self) -> None:
        status, value = self.invoke([
            "start", str(self.root), "run.cli.fakelive.v1",
            "--verifier-provider", "fake",
            "--verifier-pricing-snapshot", str(self.root / "absent.json"),
        ])
        self.assertEqual(status, 2)
        self.assertTrue(
            any("verifier_provider_fake_with_live_inputs" in item
                for item in value["failed_checks"])
        )

    def test_an_unconfigured_live_verifier_refuses_the_run(self) -> None:
        with patch.dict(os.environ, {}, clear=True), \
                patch("math_research.phase2_cli.load_provider_environment"):
            status, value = self.invoke([
                "start", str(self.root), "run.cli.unconfigured.v1",
                "--verifier-provider", "openai",
                "--verifier-config", str(self.root / "absent.json"),
            ])
        self.assertEqual(status, 2)
        self.assertIn("config.model_identifier", value["missing_variables"])
        with SQLiteWorkspace(self.root / "workspace.sqlite3") as workspace:
            with self.assertRaises(KeyError):
                workspace.get_run(oid("run.cli.unconfigured.v1"))

    def test_reporting_commands_open_the_workspace_read_only(self) -> None:
        status, _ = self.invoke(["start", str(self.root), "run.cli.sealed.v1", "--execute"])
        self.assertEqual(status, 0)
        database = self.root / "workspace.sqlite3"
        before = database.read_bytes()
        for command in ("jobs", "budget", "timeline", "manifest", "review", "rounds", "report"):
            with self.subTest(command=command):
                status, _ = self.invoke([command, str(self.root), "run.cli.sealed.v1"])
                self.assertEqual(status, 0)
        self.assertEqual(database.read_bytes(), before)


class SealedEvidenceTests(RoundCase):
    def test_read_only_replay_refuses_writes_and_leaves_bytes_alone(self) -> None:
        loop, _ = self.loop(self.script((("a", "supports", "manual_review"),)))
        run = loop.start(
            run_id=oid("run.rounds.sealed.v1"), dossier=self.dossier, limits=self.limits(),
        )
        loop.run_to_terminal(run.run_id)
        path = self.root / "workspace.sqlite3"
        self.workspace.close()
        before = path.read_bytes()
        sealed = SQLiteWorkspace(path, read_only=True)
        try:
            self.assertEqual(sealed.get_run(run.run_id).status, RunStatus.AWAITING_REVIEW)
            self.assertEqual(len(sealed.list_refinement_rounds(run.run_id)), 1)
            with self.assertRaises(SealedWorkspaceError):
                sealed.set_run_status(
                    run.run_id, RunStatus.CANCELLED.value, now=self.clock.text(),
                    idempotency_key="sealed-write",
                )
        finally:
            sealed.close()
        self.assertEqual(path.read_bytes(), before)
        self.workspace = SQLiteWorkspace(path)


if __name__ == "__main__":
    unittest.main()
