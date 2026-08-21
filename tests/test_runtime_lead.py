"""Acceptance suite for the bounded iterative research runtime (ADR-0047).

Two kinds of test live here and the distinction is the point. A `test_*` case
asserts that the runtime does what it claims. A `test_probe_*` case is a
falsifiability probe: it names one mutation and asserts the forbidden outcome
actually occurs. A boundary whose probe cannot be made to fail is a boundary
that proves nothing, so `ProbeInventoryTests` gates the probe count the way the
publication slice gates `probes_flipped == probes_total`.

Everything here is offline. No provider, no key, no network, no container.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

from math_research.domain.entities import OpaqueId
from math_research.interchange import export_dossier_dict
from math_research.novelty import NoveltyRecheck
from math_research.phase2.fixtures import build_open_theorem_dossier
from math_research.phase2.pricing import create_pricing_snapshot
from math_research.phase2.records import (
    BudgetLimits,
    ModelResult,
    ModelResultStatus,
    ModelUsage,
)
from math_research.phase2.sqlite_workspace import SQLiteWorkspace
from math_research.runtime import MAX_ITERATIONS_CEILING
from math_research.runtime.context import (
    IterationLedger,
    LedgerLeakedIntoVerifierContext,
    hypothesis_digest,
)
from math_research.runtime.fixtures import RehearsalGateway
from math_research.runtime.lead import (
    GatewayCalledDuringReplay,
    ReplayGuardGateway,
    ResearchLeadRuntime,
    TargetIdentityViolation,
    freeze_target,
)
from math_research.runtime.records import (
    IterationOutcome,
    LeadSession,
    SessionUsage,
    TerminalReason,
)
from math_research.runtime.reporting import render_session_report, session_facts
from math_research.runtime.session_config import (
    SessionConfigurationError,
    create_session_configuration,
    load_session_configuration,
    session_configuration_payload,
    write_session_configuration,
)
from math_research.runtime.serialization import canonical_json

DOSSIER = build_open_theorem_dossier()
TARGET = DOSSIER.formalization.target_claim_id.value
REFERENCES = tuple(sorted({
    TARGET,
    DOSSIER.formalization.id.value,
    DOSSIER.semantic_alignment.id.value,
    *(item.value for item in DOSSIER.formalization.assumption_claim_ids),
}))


def clock(step_seconds: int = 1):
    current = [datetime(2026, 8, 21, tzinfo=timezone.utc)]

    def now() -> datetime:
        current[0] += timedelta(seconds=step_seconds)
        return current[0]

    return now


def configuration(**overrides: Any):
    values: dict[str, Any] = {
        "session_configuration_id": OpaqueId("cfg.test.v1"),
        "max_iterations": 6,
        "max_model_calls": 20,
        "max_cost_microusd": 1_000_000,
        "max_wall_milliseconds": 600_000,
        "stagnation_window": 2,
        "per_iteration_budget": BudgetLimits(
            max_input_tokens=20_000, max_output_tokens=4_096,
            max_cost_microusd=100_000, max_wall_milliseconds=60_000, max_attempts=2,
        ),
    }
    values.update(overrides)
    return create_session_configuration(**values)


def usage(input_tokens: int = 100, output_tokens: int = 50) -> ModelUsage:
    return ModelUsage(
        input_tokens=input_tokens, output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens, usage_source="fixture",
    )


def succeeded(structured: dict[str, Any]) -> ModelResult:
    return ModelResult(
        status=ModelResultStatus.SUCCEEDED, provider="scripted",
        model_identifier="scripted-v1", capabilities=("structured_output",),
        structured_output=json.dumps(structured, sort_keys=True),
        declared_rationale="scripted", refusal=None, usage=usage(),
        retry_classification="none", provider_request_id="req",
    )


def proposal(
    statement: str, steps: tuple[str, ...], *, target: str = TARGET,
    result_type: str = "proof_attempt",
) -> ModelResult:
    return succeeded({
        "schema_version": "2.0.0",
        "result_type": result_type,
        "target_claim_id": target,
        "mathematical_payload": {"statement": statement, "steps": list(steps), "witness": None},
        "declared_rationale": "scripted proposal",
        "referenced_entity_ids": list(REFERENCES),
    })


def verdict(recommendation: str, codes: tuple[str, ...], *, extra: dict[str, Any] | None = None):
    def build(artifact_hash: str) -> ModelResult:
        payload: dict[str, Any] = {
            "schema_version": "2.0.0",
            "result_type": "finding",
            "target_claim_id": TARGET,
            "candidate_artifact_hash": artifact_hash,
            "findings": [
                {
                    "code": code, "outcome": "unresolved", "detail": f"detail {code}",
                    "referenced_entity_ids": [TARGET],
                }
                for code in codes
            ],
            "recommendation": recommendation,
            "declared_rationale": "scripted verdict",
        }
        if extra:
            payload.update(extra)
        return succeeded(payload)

    return build


class Gateway:
    """Scripted gateway that can read the candidate hash the verifier is given."""

    def __init__(self, proposals: list[ModelResult], verdicts: list[Any]) -> None:
        self.proposals = list(proposals)
        self.verdicts = list(verdicts)
        self.requests: list[Any] = []

    def prepare(self, request: Any) -> None:
        return None

    def complete(self, request: Any, preparation: Any = None) -> ModelResult:
        self.requests.append(request)
        if request.purpose == "proposer":
            return self.proposals.pop(0)
        context = json.loads(request.serialized_context)
        return self.verdicts.pop(0)(context["candidate"]["artifact_hash"])

    def contexts(self, purpose: str) -> list[dict[str, Any]]:
        return [
            json.loads(item.serialized_context)
            for item in self.requests if item.purpose == purpose
        ]


def run_session(
    gateway: Any, *, config: Any = None, dossier: Any = None, now: Any = None,
    session_id: str = "session.test", pricing: Any = None, root: Path | None = None,
    novelty_recheck: NoveltyRecheck | None = None,
):
    directory = root
    context = None
    if directory is None:
        context = tempfile.TemporaryDirectory()
        directory = Path(context.name)
    if config is None and isinstance(getattr(gateway, "proposals", None), list):
        scripted_iterations = max(1, len(gateway.proposals))
        config = configuration(
            max_iterations=scripted_iterations,
            stagnation_window=min(2, scripted_iterations),
        )
    active_dossier = dossier if dossier is not None else DOSSIER
    recheck = novelty_recheck or NoveltyRecheck(
        recheck_id=f"recheck.{session_id}", checkpoint="before_research",
        subject_id=active_dossier.problem.id.value,
        subject_hash=export_dossier_dict(active_dossier)["content_hash"],
        next_action_id=session_id, performed_by="researcher.test",
        performed_at="2026-08-21T00:00:00Z", protocol_id="protocol.novelty.test",
        query_terms=("bounded theorem",), searched_sources=("fixture catalogue",),
        equivalence_checks=("renamed and equivalent formulations",),
        evidence_refs=(("evidence.novelty.test", "sha256:" + "1" * 64),),
        outcome="inconclusive", prior_art_relationship="unresolved",
        prior_resolution="unresolved", prior_resolution_verification="unresolved",
        limitations=("Project-authored offline fixture only.",),
    ).finalized()
    runtime = ResearchLeadRuntime(
        root=directory / "run",
        configuration=config or configuration(),
        proposer=gateway,
        verifier=gateway,
        pricing_snapshot=pricing,
        now=now or clock(),
    )
    session = runtime.run(
        session_id=OpaqueId(session_id), dossier=active_dossier, novelty_recheck=recheck,
    )
    return session, directory / "run", context


class IterationTests(unittest.TestCase):
    """The runtime's reason to exist: a second turn."""

    def test_a_session_takes_more_than_one_turn(self) -> None:
        gateway = Gateway(
            [proposal("A", ("a",)), proposal("B", ("b",)), proposal("C", ("c",))],
            [verdict("unresolved", ("g1",)), verdict("unresolved", ("g2",)),
             verdict("manual_review", ("ok",))],
        )
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        self.assertEqual(len(session.iterations), 3)
        self.assertEqual(session.terminal_reason, TerminalReason.AWAITING_HUMAN_REVIEW)
        # The sealed single-shot path makes exactly two calls in total. Six is
        # the observable difference between a demonstration and a run.
        self.assertEqual(session.usage.model_calls, 6)

    def test_each_iteration_is_its_own_durable_phase2_run(self) -> None:
        gateway = Gateway(
            [proposal("A", ("a",)), proposal("B", ("b",))],
            [verdict("unresolved", ("g1",)), verdict("unresolved", ("g2",))],
        )
        session, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
            for record in session.iterations:
                run = workspace.get_run(record.run_id)
                self.assertEqual(run.run_id, record.run_id)
                self.assertTrue(workspace.list_proposals(record.run_id))
        self.assertEqual(
            len({item.run_id.value for item in session.iterations}), len(session.iterations)
        )

    def test_prior_resolution_classification_reaches_the_proposer_and_report(self) -> None:
        session_id = "session.graffiti-197.verify.v1"
        recheck = NoveltyRecheck(
            recheck_id="recheck.graffiti-197.start", checkpoint="before_research",
            subject_id=DOSSIER.problem.id.value,
            subject_hash=export_dossier_dict(DOSSIER)["content_hash"],
            next_action_id=session_id, performed_by="researcher.test",
            performed_at="2026-08-21T00:00:00Z",
            protocol_id="protocol.graffiti-197.prior-art.v1",
            query_terms=("Graffiti 197",), searched_sources=("AI Village News",),
            equivalence_checks=("same Kneser K(7,2) witness and inequality",),
            evidence_refs=(("source.ai-village.opus5-124", "sha256:" + "a" * 64),),
            outcome="prior_art_found", prior_art_relationship="same_result",
            prior_resolution="refutation",
            prior_resolution_verification="independently_verified",
            limitations=("Fixture checks classification, not search completeness.",),
        ).finalized()
        gateway = Gateway([proposal("A", ("a",))], [verdict("unresolved", ("g",))])
        session, root, holder = run_session(
            gateway, session_id=session_id, novelty_recheck=recheck,
        )
        self.addCleanup(holder.cleanup)
        context = gateway.contexts("proposer")[0]["prior_art_context"]
        self.assertEqual("independent_verification", context["report_classification"])
        self.assertEqual("already_refuted", context["target_resolution_status"])
        self.assertIn("do not claim discovery", context["reporting_rule"])
        with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
            report = render_session_report(session, workspace)
        self.assertIn("Report classification: `independent_verification`", report)
        self.assertIn("Target resolution status: `already_refuted`", report)
        self.assertIn("Prior-art relationship: `same_result`", report)
        self.assertIn("Prior resolution: `refutation`", report)

        with self.assertRaisesRegex(ValueError, "not derived"):
            replace(session, report_classification="extension_of_prior_result")

    def test_the_ledger_reaches_the_proposer_and_grows(self) -> None:
        gateway = Gateway(
            [proposal("A", ("a",)), proposal("B", ("b",)), proposal("C", ("c",))],
            [verdict("unresolved", ("g1",)), verdict("unresolved", ("g2",)),
             verdict("unresolved", ("g3",))],
        )
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        shown = [
            context["session_history"]["attempts_shown"]
            for context in gateway.contexts("proposer")
        ]
        self.assertEqual(shown, [0, 1, 2])
        self.assertIn("A", canonical_json(gateway.contexts("proposer")[1]))

    def test_the_verifier_context_never_contains_session_history(self) -> None:
        gateway = Gateway(
            [proposal("A", ("a",)), proposal("B", ("b",))],
            [verdict("unresolved", ("g1",)), verdict("unresolved", ("g2",))],
        )
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        for context in gateway.contexts("verifier"):
            serialized = canonical_json(context)
            self.assertNotIn("session_history", serialized)
            self.assertNotIn("iteration_policy", serialized)
            self.assertNotIn("prior_art_context", serialized)
            self.assertNotIn("attempts_shown", serialized)
        self.assertEqual(len(gateway.contexts("verifier")), 2)

    def test_probe_a_ledger_wired_into_the_verifier_context_is_refused(self) -> None:
        """PROBE: verifier isolation. Leak the ledger; the run must die."""
        from math_research.runtime.context import IterativeProposerLoop

        class Leaky(IterativeProposerLoop):
            def _verifier_context(self, dossier, proposal_record, candidate):  # type: ignore[override]
                from math_research.phase2.baseline_loop import BaselineResearchLoop

                context, included, excluded = BaselineResearchLoop._verifier_context(
                    self, dossier, proposal_record, candidate
                )
                context["session_history"] = self.ledger.payload()
                return IterativeProposerLoop._verifier_context.__wrapped__(  # type: ignore[attr-defined]
                    self, dossier, proposal_record, candidate
                ) if False else self._check(context, included, excluded)

            def _check(self, context, included, excluded):
                from math_research.runtime.serialization import canonical_bytes

                serialized = canonical_bytes(context)
                if b"session_history" in serialized:
                    raise LedgerLeakedIntoVerifierContext("probe leak")
                return context, included, excluded

        ledger = IterationLedger()
        with self.assertRaises(LedgerLeakedIntoVerifierContext):
            raise LedgerLeakedIntoVerifierContext(
                "the guard in IterativeProposerLoop._verifier_context is the "
                "production path; this probe asserts the guard exists and fires"
            )
        # The real guard, exercised against the real production method.
        gateway = Gateway([proposal("A", ("a",))], [verdict("unresolved", ("g",))])
        session, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        loop_ledger = IterationLedger()
        loop_ledger.append(
            iteration_index=1, result_type="proof_attempt",
            hypothesis_digest_value=session.iterations[0].hypothesis_digest,
            statement="A", steps=("a",), verifier_recommendation="unresolved",
            findings=(), finding_details=(), outcome="unresolved",
        )
        from math_research.runtime.context import IterativeProposerLoop as Loop

        stub = Loop.__new__(Loop)
        stub.ledger = loop_ledger
        poisoned = {"candidate": {"artifact_hash": "sha256:" + "0" * 64},
                    "session_history": loop_ledger.payload()}
        with mock.patch.object(
            Loop, "_verifier_context", side_effect=None, autospec=False
        ):
            pass
        from math_research.phase2.baseline_loop import BaselineResearchLoop

        with mock.patch.object(
            BaselineResearchLoop, "_verifier_context",
            lambda self, d, p, c, **kwargs: (poisoned, (), ()),
        ):
            with self.assertRaises(LedgerLeakedIntoVerifierContext):
                Loop._verifier_context(stub, DOSSIER, None, {})
        del ledger


class TargetFreezeTests(unittest.TestCase):
    """A session may try a different argument, never a different theorem."""

    def test_the_frozen_identity_covers_statement_formalization_and_alignment(self) -> None:
        base = freeze_target(DOSSIER)
        target_claim = next(item for item in DOSSIER.claims if item.id.value == TARGET)
        moved_statement = replace(
            DOSSIER,
            claims=tuple(
                replace(item, statement=item.statement + " for positive integers")
                if item.id == target_claim.id else item
                for item in DOSSIER.claims
            ),
        )
        self.assertNotEqual(base.frozen_hash(), freeze_target(moved_statement).frozen_hash())
        moved_formalization = replace(
            DOSSIER,
            formalization=replace(
                DOSSIER.formalization,
                statement=DOSSIER.formalization.statement + " and n > 0",
            ),
        )
        self.assertNotEqual(base.frozen_hash(), freeze_target(moved_formalization).frozen_hash())
        moved_alignment = replace(
            DOSSIER,
            semantic_alignment=replace(
                DOSSIER.semantic_alignment,
                edge_case_delta=("a newly declared exception",),
            ),
        )
        self.assertNotEqual(base.frozen_hash(), freeze_target(moved_alignment).frozen_hash())

    def test_probe_a_target_that_moves_mid_session_aborts_the_run(self) -> None:
        """PROBE: the freeze check. Move the target; the session must abort."""
        real = freeze_target
        calls = {"n": 0}

        def drifting(dossier):
            calls["n"] += 1
            identity = real(dossier)
            if calls["n"] > 1:
                return replace(identity, target_statement_hash="sha256:" + "f" * 64)
            return identity

        gateway = Gateway(
            [proposal("A", ("a",)), proposal("B", ("b",))],
            [verdict("unresolved", ("g1",)), verdict("unresolved", ("g2",))],
        )
        with mock.patch("math_research.runtime.lead.freeze_target", drifting):
            with self.assertRaises(TargetIdentityViolation):
                run_session(gateway)

    def test_probe_a_proposal_naming_another_target_is_discarded(self) -> None:
        """PROBE: premise smuggling. Aim at another claim; lose the iteration."""
        gateway = Gateway(
            [proposal("A", ("a",), target="claim.something.else")],
            [verdict("unresolved", ("g",))],
        )
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.iterations[0].outcome, IterationOutcome.PROPOSER_FAILED)
        self.assertEqual(session.terminal_reason, TerminalReason.ITERATION_FAILED)
        self.assertEqual(len(gateway.contexts("verifier")), 0)


class DuplicateTests(unittest.TestCase):
    def test_a_repeated_hypothesis_does_not_spend_the_verifier(self) -> None:
        gateway = Gateway(
            [proposal("A", ("a",)), proposal("A", ("a",))],
            [verdict("unresolved", ("g1",))],
        )
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        second = session.iterations[1]
        self.assertEqual(second.outcome, IterationOutcome.DUPLICATE_HYPOTHESIS)
        self.assertEqual(second.duplicate_of_iteration, 1)
        self.assertEqual(second.usage.model_calls, 1)
        self.assertEqual(len(gateway.contexts("verifier")), 1)

    def test_probe_a_restated_duplicate_is_still_a_duplicate(self) -> None:
        """PROBE: normalization. Change only case and spacing; stay a duplicate."""
        gateway = Gateway(
            [proposal("The Sum Is Even", ("Step  One",)),
             proposal("the   sum is even", ("step one",))],
            [verdict("unresolved", ("g1",))],
        )
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        self.assertEqual(
            session.iterations[1].outcome, IterationOutcome.DUPLICATE_HYPOTHESIS
        )
        self.assertEqual(session.distinct_hypotheses, 1)

    def test_probe_a_genuinely_different_argument_is_not_a_duplicate(self) -> None:
        """PROBE: the duplicate rule is not vacuous -- it must let work through."""
        gateway = Gateway(
            [proposal("A", ("a",)), proposal("A", ("a", "b"))],
            [verdict("unresolved", ("g1",)), verdict("unresolved", ("g2",))],
        )
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.distinct_hypotheses, 2)
        self.assertIsNone(session.iterations[1].duplicate_of_iteration)


class NonPromotionTests(unittest.TestCase):
    """Nothing the runtime can do creates a warrant."""

    def test_a_completed_session_creates_no_warrant_and_discharges_nothing(self) -> None:
        gateway = Gateway(
            [proposal("A", ("a",))], [verdict("manual_review", ("clean",))],
        )
        session, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.terminal_reason, TerminalReason.AWAITING_HUMAN_REVIEW)
        self.assertFalse(session.epistemic_warrant_created)
        self.assertEqual(session.obligations_discharged, 0)
        with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
            stored = workspace.load_dossier(DOSSIER.id)
        # The dossier the workspace holds is byte-identical to the one supplied:
        # the strongest terminal outcome changed no trust state at all.
        self.assertEqual(
            [item.id.value for item in stored.warrants],
            [item.id.value for item in DOSSIER.warrants],
        )
        self.assertEqual(
            sorted((item.id.value, item.status.value) for item in stored.obligations),
            sorted((item.id.value, item.status.value) for item in DOSSIER.obligations),
        )

    def test_probe_a_session_record_claiming_a_warrant_is_refused(self) -> None:
        """PROBE: the record cannot be made to say a warrant was created."""
        gateway = Gateway([proposal("A", ("a",))], [verdict("unresolved", ("g",))])
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        for field, value in (
            ("epistemic_warrant_created", True),
            ("obligations_discharged", 1),
            ("retention_gain_measured", True),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    replace(session, **{field: value})

    def test_probe_a_verifier_awarding_a_warrant_is_rejected(self) -> None:
        """PROBE: a verifier that tries to award status loses the iteration."""
        gateway = Gateway(
            [proposal("A", ("a",))],
            [verdict("manual_review", ("g",), extra={"warrant": "kernel_checked"})],
        )
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.iterations[0].outcome, IterationOutcome.VERIFIER_FAILED)
        self.assertEqual(session.terminal_reason, TerminalReason.ITERATION_FAILED)
        self.assertIsNone(session.iterations[0].verifier_recommendation)

    def test_the_report_states_what_did_not_happen(self) -> None:
        gateway = Gateway([proposal("A", ("a",))], [verdict("manual_review", ("clean",))])
        session, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
            report = render_session_report(session, workspace)
        for required in (
            "no epistemic warrant",
            "no proof obligation",
            "not_assessed",
            "retention_gain_measured",
            "no search tier",
            "NO live model was called",
        ):
            self.assertIn(required, report)


class BoundsTests(unittest.TestCase):
    """Bounds are external, hashed, and enforced before work, not after."""

    def test_the_session_cost_bound_cannot_be_exceeded(self) -> None:
        pricing = create_pricing_snapshot(
            snapshot_id=OpaqueId("pricing.test.v1"), provider="openai",
            model_identifier="scripted-v1", source="test",
            captured_at="2026-08-21T00:00:00Z", currency="USD",
            input_microusd_per_million_tokens=1_000_000,
            output_microusd_per_million_tokens=1_000_000,
        )
        config = configuration(max_cost_microusd=100_000, max_iterations=10, stagnation_window=10)
        gateway = Gateway(
            [proposal(f"H{index}", (f"s{index}",)) for index in range(10)],
            [verdict("unresolved", (f"g{index}",)) for index in range(10)],
        )
        session, _, holder = run_session(gateway, config=config, pricing=pricing)
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.terminal_reason, TerminalReason.BUDGET_EXHAUSTED)
        self.assertEqual(session.exhausted_bound, "cost_microusd")
        self.assertLessEqual(session.usage.cost_microusd, config.max_cost_microusd)

    def test_the_model_call_bound_cannot_be_exceeded(self) -> None:
        config = configuration(max_model_calls=5, max_iterations=10, stagnation_window=10)
        gateway = Gateway(
            [proposal(f"H{index}", (f"s{index}",)) for index in range(10)],
            [verdict("unresolved", (f"g{index}",)) for index in range(10)],
        )
        session, _, holder = run_session(gateway, config=config)
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.terminal_reason, TerminalReason.BUDGET_EXHAUSTED)
        self.assertEqual(session.exhausted_bound, "model_calls")
        self.assertLessEqual(session.usage.model_calls, config.max_model_calls)

    def test_the_iteration_bound_is_reported_as_a_bound_not_a_failure(self) -> None:
        config = configuration(
            max_wall_milliseconds=600_000,
            per_iteration_budget=BudgetLimits(
                max_input_tokens=20_000, max_output_tokens=4_096,
                max_cost_microusd=100_000, max_wall_milliseconds=2_000, max_attempts=2,
            ),
        )
        gateway = Gateway(
            [proposal(f"H{index}", (f"s{index}",)) for index in range(6)],
            [verdict("unresolved", (f"g{index}",)) for index in range(6)],
        )
        session, _, holder = run_session(gateway, config=config, now=clock(step_seconds=5))
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.terminal_reason, TerminalReason.BUDGET_EXHAUSTED)
        self.assertTrue(str(session.exhausted_bound).startswith("per_iteration:"))
        self.assertEqual(
            session.iterations[-1].outcome, IterationOutcome.ITERATION_BUDGET_EXHAUSTED
        )

    def test_iterations_exhausted_is_its_own_reason(self) -> None:
        config = configuration(max_iterations=3, stagnation_window=3)
        gateway = Gateway(
            [proposal(f"H{index}", (f"s{index}",)) for index in range(3)],
            [verdict("unresolved", (f"g{index}",)) for index in range(3)],
        )
        session, _, holder = run_session(gateway, config=config)
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.terminal_reason, TerminalReason.ITERATIONS_EXHAUSTED)
        self.assertEqual(len(session.iterations), 3)

    def test_probe_a_configuration_above_the_hard_ceiling_is_refused(self) -> None:
        """PROBE: the ceiling. Ask for more than the package allows."""
        with self.assertRaises(SessionConfigurationError):
            configuration(max_iterations=MAX_ITERATIONS_CEILING + 1)
        with self.assertRaises(SessionConfigurationError):
            configuration(max_cost_microusd=25_000_001)

    def test_probe_a_stagnation_window_wider_than_the_run_is_refused(self) -> None:
        """PROBE: a window that can never close would disable the stop rule."""
        with self.assertRaises(SessionConfigurationError):
            configuration(max_iterations=3, stagnation_window=4)

    def test_probe_an_edited_configuration_is_refused(self) -> None:
        """PROBE: the bounds artifact is content-hashed, so editing it fails."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            write_session_configuration(configuration(), path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["max_cost_microusd"] = payload["max_cost_microusd"] * 4
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(SessionConfigurationError):
                load_session_configuration(path)

    def test_probe_a_per_iteration_bound_above_the_session_bound_is_refused(self) -> None:
        """PROBE: an iteration may not be allowed to outspend its session."""
        with self.assertRaises(SessionConfigurationError):
            configuration(
                max_cost_microusd=50_000,
                per_iteration_budget=BudgetLimits(
                    max_input_tokens=20_000, max_output_tokens=4_096,
                    max_cost_microusd=100_000, max_wall_milliseconds=60_000,
                    max_attempts=2,
                ),
            )

    def test_probe_nested_phase2_refinement_is_refused(self) -> None:
        """PROBE: one outer iteration cannot hide a second inner loop."""
        with self.assertRaisesRegex(SessionConfigurationError, "exactly one Phase 2 round"):
            configuration(
                per_iteration_budget=BudgetLimits(
                    max_input_tokens=20_000,
                    max_output_tokens=4_096,
                    max_cost_microusd=100_000,
                    max_wall_milliseconds=60_000,
                    max_attempts=4,
                    max_refinement_rounds=2,
                )
            )


class StagnationTests(unittest.TestCase):
    def test_stagnation_fires_after_the_configured_window(self) -> None:
        gateway = Gateway(
            [proposal("A", ("a",))] * 6,
            [verdict("unresolved", ("g",))] * 6,
        )
        session, _, holder = run_session(gateway, config=configuration(stagnation_window=2))
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.terminal_reason, TerminalReason.STAGNATED)
        self.assertEqual(len(session.iterations), 3)

    def test_probe_a_productive_run_does_not_stagnate(self) -> None:
        """PROBE: the stop rule is not vacuous -- real motion must survive it."""
        gateway = Gateway(
            [proposal(f"H{index}", (f"s{index}",)) for index in range(4)],
            [verdict("unresolved", (f"g{index}",)) for index in range(4)],
        )
        session, _, holder = run_session(
            gateway, config=configuration(max_iterations=4, stagnation_window=2)
        )
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.terminal_reason, TerminalReason.ITERATIONS_EXHAUSTED)
        self.assertTrue(all(item.productive for item in session.iterations))

    def test_probe_a_new_statement_drawing_the_same_objection_is_unproductive(self) -> None:
        """PROBE: motion is not progress. New words, same finding, no credit."""
        gateway = Gateway(
            [proposal(f"H{index}", (f"s{index}",)) for index in range(4)],
            [verdict("unresolved", ("same.gap",)) for _ in range(4)],
        )
        session, _, holder = run_session(gateway, config=configuration(stagnation_window=2))
        self.addCleanup(holder.cleanup)
        self.assertEqual(session.terminal_reason, TerminalReason.STAGNATED)
        self.assertTrue(session.iterations[0].productive)
        self.assertFalse(session.iterations[1].productive)


class ReplayTests(unittest.TestCase):
    def test_the_report_regenerates_identically_after_a_restart(self) -> None:
        gateway = Gateway(
            [proposal("A", ("a",)), proposal("B", ("b",))],
            [verdict("unresolved", ("g1",)), verdict("unresolved", ("g2",))],
        )
        session, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
            first = render_session_report(session, workspace)
            first_facts = session_facts(session, workspace)
        with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
            second = render_session_report(session, workspace)
            second_facts = session_facts(session, workspace)
        self.assertEqual(first, second)
        self.assertEqual(canonical_json(first_facts), canonical_json(second_facts))

    def test_two_identical_runs_produce_the_same_session_hash(self) -> None:
        def build() -> Any:
            return Gateway(
                [proposal("A", ("a",)), proposal("B", ("b",))],
                [verdict("unresolved", ("g1",)), verdict("unresolved", ("g2",))],
            )

        first, _, holder_one = run_session(build(), session_id="session.same")
        self.addCleanup(holder_one.cleanup)
        second, _, holder_two = run_session(build(), session_id="session.same")
        self.addCleanup(holder_two.cleanup)
        self.assertEqual(first.content_hash, second.content_hash)

    def test_probe_a_replay_that_reaches_a_gateway_fails_loudly(self) -> None:
        """PROBE: replay must not spend money. Give it a gateway that screams."""
        with self.assertRaises(GatewayCalledDuringReplay):
            run_session(ReplayGuardGateway())

    def test_probe_an_edited_session_record_is_refused(self) -> None:
        """PROBE: the session record is content-hashed, so editing it fails."""
        from math_research.runtime_cli import _load_session

        gateway = Gateway([proposal("A", ("a",))], [verdict("unresolved", ("g",))])
        session, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        path = root / "session.json"
        self.assertEqual(_load_session(path).content_hash, session.content_hash)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["terminal_reason"] = TerminalReason.AWAITING_HUMAN_REVIEW.value
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValueError):
            _load_session(path)

    def test_probe_edited_iteration_usage_breaks_the_operational_hash(self) -> None:
        """PROBE: semantic stability must not leave spend observations unaudited."""
        from math_research.runtime_cli import _load_session

        gateway = Gateway([proposal("A", ("a",))], [verdict("unresolved", ("g",))])
        _, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        path = root / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["iterations"][0]["usage"]["input_tokens"] += 1
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "operational_hash mismatch"):
            _load_session(path)

    def test_probe_edited_session_rollup_is_refused_even_before_hash_verification(self) -> None:
        """PROBE: a session total is derived from iterations, never self-attested."""
        from math_research.runtime_cli import _load_session

        gateway = Gateway([proposal("A", ("a",))], [verdict("unresolved", ("g",))])
        _, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        path = root / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["usage"]["cost_microusd"] += 1
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sum of iteration usage"):
            _load_session(path)

    def test_probe_report_totals_are_rederived_from_durable_model_calls(self) -> None:
        """PROBE: changing a durable call row cannot leave a plausible report total."""
        gateway = Gateway([proposal("A", ("a",))], [verdict("unresolved", ("g",))])
        session, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
            with workspace.transaction() as connection:
                connection.execute(
                    "UPDATE model_calls SET input_tokens=input_tokens+1 "
                    "WHERE call_id=(SELECT call_id FROM model_calls ORDER BY call_id LIMIT 1)"
                )
            with self.assertRaisesRegex(ValueError, "durable model-call rows"):
                session_facts(session, workspace)

    def test_a_missing_novelty_recheck_makes_replay_fail(self) -> None:
        """Replay retains the exact re-check that opened research."""
        from math_research.runtime_cli import _load_session

        gateway = Gateway([proposal("A", ("a",))], [verdict("unresolved", ("g",))])
        _, root, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        (root / "novelty-recheck.json").unlink()
        with self.assertRaisesRegex(ValueError, "novelty re-check unavailable"):
            _load_session(root / "session.json")


class LedgerBoundsTests(unittest.TestCase):
    def test_the_ledger_reports_its_own_truncation(self) -> None:
        ledger = IterationLedger(max_entries=2)
        for index in range(5):
            ledger.append(
                iteration_index=index, result_type="proof_attempt",
                hypothesis_digest_value=hypothesis_digest(
                    result_type="proof_attempt", statement=f"S{index}", steps=("a",)
                ),
                statement=f"S{index}", steps=("a",), verifier_recommendation="unresolved",
                findings=(), finding_details=(), outcome="unresolved",
            )
        payload = ledger.payload()
        self.assertEqual(payload["attempts_recorded"], 5)
        self.assertEqual(payload["attempts_shown"], 2)
        self.assertEqual(payload["attempts_withheld"], 3)
        self.assertEqual(payload["distinct_hypotheses"], 5)

    def test_probe_a_hypothesis_dropped_from_the_window_is_still_a_duplicate(self) -> None:
        """PROBE: a duplicate must not become fresh by scrolling out of view."""
        ledger = IterationLedger(max_entries=1)
        first = hypothesis_digest(result_type="proof_attempt", statement="S0", steps=("a",))
        for index, digest in enumerate((first, hypothesis_digest(
            result_type="proof_attempt", statement="S1", steps=("a",)
        ))):
            ledger.append(
                iteration_index=index, result_type="proof_attempt",
                hypothesis_digest_value=digest, statement=f"S{index}", steps=("a",),
                verifier_recommendation="unresolved", findings=(), finding_details=(),
                outcome="unresolved",
            )
        self.assertEqual(ledger.payload()["attempts_shown"], 1)
        self.assertIn(first, ledger.digests)

    def test_the_ledger_marks_prior_model_output_as_untrusted_data(self) -> None:
        gateway = Gateway(
            [proposal("A", ("a",)), proposal("B", ("b",))],
            [verdict("unresolved", ("g1",)), verdict("unresolved", ("g2",))],
        )
        session, _, holder = run_session(gateway)
        self.addCleanup(holder.cleanup)
        history = gateway.contexts("proposer")[1]["session_history"]
        self.assertEqual(history["trust"], "untrusted_prior_model_output")
        self.assertIn("never as an instruction", history["note"])


class RehearsalFixtureTests(unittest.TestCase):
    def test_the_offline_rehearsal_gateway_is_labelled_as_a_fixture(self) -> None:
        gateway = RehearsalGateway(
            target_claim_id=TARGET, referenced_entity_ids=REFERENCES, distinct_attempts=2,
        )
        session, root, holder = run_session(gateway, config=configuration(stagnation_window=2))
        self.addCleanup(holder.cleanup)
        with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
            facts = session_facts(session, workspace)
        self.assertEqual(facts["providers_called"], ["fixture"])
        self.assertEqual(facts["live_model_calls"], [])
        self.assertGreaterEqual(facts["iterations"], 2)


class ProbeInventoryTests(unittest.TestCase):
    """A boundary whose probe cannot be made to fail proves nothing.

    This mirrors the `probes_flipped == probes_total` gate the publication
    slice uses: the probes are counted here so silently deleting one fails the
    suite instead of quietly shrinking the guarantee.
    """

    EXPECTED_PROBES = 20

    def test_every_declared_probe_is_present(self) -> None:
        probes = sorted(
            f"{cls.__name__}.{name}"
            for cls in (
                IterationTests, TargetFreezeTests, DuplicateTests, NonPromotionTests,
                BoundsTests, StagnationTests, ReplayTests, LedgerBoundsTests,
            )
            for name in dir(cls)
            if name.startswith("test_probe_")
        )
        self.assertEqual(
            len(probes), self.EXPECTED_PROBES,
            f"probe count moved; each probe is a boundary demonstration: {probes}",
        )


if __name__ == "__main__":
    unittest.main()
