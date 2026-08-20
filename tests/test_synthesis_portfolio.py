"""Acceptance scenarios ERS-AC-11 and ERS-AC-12.

Section 14 of `docs/phase-4/EXPLORATORY_RESEARCH_SYNTHESIS_V1.md` is normative.
Each forbidden outcome is asserted impossible, not merely absent.
"""

from __future__ import annotations

import unittest

import sys
from pathlib import Path

# See tests/synthesis_fixtures.py: makes the sibling helper import work whether
# this module is run via `unittest discover -s tests` or by dotted module name.
sys.path.insert(0, str(Path(__file__).resolve().parent))


from math_research.synthesis.branches import (
    BranchPortfolio,
    BranchState,
    DuplicateAttemptRejected,
    RetryAuthorization,
    constraint_configuration_digest,
    duplicate_attempt_key,
    normalize_hypothesis,
    normalized_hypothesis_digest,
)
from math_research.synthesis.budget import BudgetExhausted, BudgetPolicy
from math_research.synthesis.state import StrategyFamily, SynthesisValidationError
from math_research.synthesis.steering import (
    SteeringAction,
    SteeringLog,
    SteeringPrincipal,
)
from synthesis_fixtures import VALID_POLICY



SNAPSHOT = "sha256:" + "b" * 64
CONFIG = {"tolerance": "exact", "max_terms": 8}

HUMAN = SteeringPrincipal(
    principal_id="principal.owner",
    actor_kind="human",
    authority="human_final",
    capability_id="capability.steer",
    capability_operation="steer_research",
)


def portfolio(**overrides) -> BranchPortfolio:
    return BranchPortfolio(BudgetPolicy.from_value({**VALID_POLICY, **overrides}))


def enqueue(pool: BranchPortfolio, *, hypothesis: str, family="direct_proof", **kwargs):
    return pool.enqueue(
        hypothesis=hypothesis,
        strategy_family=family,
        objective_delta="restrict to the commuting case",
        falsification_conditions=("an exact nonoptimal fixed point exists",),
        input_graph_snapshot_identity=SNAPSHOT,
        constraint_configuration=CONFIG,
        **kwargs,
    )


class DuplicateAttemptKeyTests(unittest.TestCase):
    """ERS-AC-11: abandoned branch and exact duplicate prevention."""

    def test_key_is_determined_by_the_five_declared_inputs(self) -> None:
        base = {
            "hypothesis_digest": normalized_hypothesis_digest("the iteration converges"),
            "parent_branch_identity": None,
            "strategy_family": StrategyFamily.DIRECT_PROOF,
            "input_graph_snapshot_identity": SNAPSHOT,
            "constraint_digest": constraint_configuration_digest(CONFIG),
        }
        key = duplicate_attempt_key(**base)
        self.assertEqual(duplicate_attempt_key(**base), key)
        # Changing any one declared input must change the key.
        for field, changed in (
            ("hypothesis_digest", normalized_hypothesis_digest("the iteration diverges")),
            ("parent_branch_identity", "branch.parent"),
            ("strategy_family", StrategyFamily.COUNTEREXAMPLE_SEARCH),
            ("input_graph_snapshot_identity", "sha256:" + "c" * 64),
            ("constraint_digest", constraint_configuration_digest({"tolerance": "interval"})),
        ):
            with self.subTest(field=field):
                self.assertNotEqual(duplicate_attempt_key(**{**base, field: changed}), key)

    def test_hypothesis_normalization_collapses_trivial_restatement(self) -> None:
        self.assertEqual(
            normalize_hypothesis("  The  Iteration   CONVERGES "), "the iteration converges"
        )
        self.assertEqual(
            normalized_hypothesis_digest("The Iteration Converges"),
            normalized_hypothesis_digest("the   iteration converges"),
        )

    def test_exact_duplicate_reenqueue_is_rejected(self) -> None:
        pool = portfolio()
        first = enqueue(pool, hypothesis="the iteration converges")
        consumed = pool.ledger.consumed()
        with self.assertRaises(DuplicateAttemptRejected) as caught:
            enqueue(pool, hypothesis="the iteration converges")
        self.assertEqual(caught.exception.existing_branch_id, first.branch_id)
        self.assertEqual(pool.ledger.consumed(), consumed)

    def test_trivially_restated_hypothesis_is_still_the_same_key(self) -> None:
        """Forbidden: silent retry of the same key."""
        pool = portfolio()
        enqueue(pool, hypothesis="the iteration converges")
        with self.assertRaises(DuplicateAttemptRejected):
            enqueue(pool, hypothesis="  THE   Iteration  Converges  ")

    def test_abandoned_attempt_remains_addressable_and_searchable(self) -> None:
        pool = portfolio()
        branch = enqueue(pool, hypothesis="the iteration converges")
        pool.transition(
            branch.branch_id,
            to_state=BranchState.ACTIVE,
            reason="begin work",
            actor_id="actor.owner",
        )
        pool.transition(
            branch.branch_id,
            to_state=BranchState.ABANDONED,
            reason="refuted by the boundary case",
            actor_id="actor.owner",
            failure_detail="exact nonoptimal fixed point found",
            discoveries=("boundary POVM is a fixed point",),
        )
        abandoned = pool.get(branch.branch_id)
        self.assertIs(abandoned.state, BranchState.ABANDONED)
        # Failure history is preserved, not deleted.
        self.assertEqual(abandoned.failure_detail, "exact nonoptimal fixed point found")
        self.assertEqual(abandoned.discoveries, ("boundary POVM is a fixed point",))
        self.assertIsNotNone(pool.find_by_key(branch.duplicate_key))
        self.assertIn(abandoned, pool.branches())

    def test_abandoned_key_cannot_be_reenqueued_without_a_retry(self) -> None:
        pool = portfolio()
        branch = enqueue(pool, hypothesis="the iteration converges")
        pool.transition(
            branch.branch_id, to_state=BranchState.ABANDONED, reason="dead end", actor_id="actor.owner"
        )
        with self.assertRaises(DuplicateAttemptRejected):
            enqueue(pool, hypothesis="the iteration converges")

    def test_authorized_retry_with_changed_input_receives_a_new_key(self) -> None:
        pool = portfolio()
        branch = enqueue(pool, hypothesis="the iteration converges")
        pool.transition(
            branch.branch_id, to_state=BranchState.ABANDONED, reason="dead end", actor_id="actor.owner"
        )
        retry = RetryAuthorization(
            retry_id="retry.one",
            original_branch_id=branch.branch_id,
            changed_field="constraint_configuration",
            previous_value="tolerance=exact",
            new_value="tolerance=interval",
            authorized_by="actor.owner",
        )
        replacement = pool.enqueue(
            hypothesis="the iteration converges",
            strategy_family="direct_proof",
            objective_delta="restrict to the commuting case",
            falsification_conditions=("an exact nonoptimal fixed point exists",),
            input_graph_snapshot_identity=SNAPSHOT,
            constraint_configuration={"tolerance": "interval", "max_terms": 8},
            retry=retry,
        )
        self.assertNotEqual(replacement.duplicate_key, branch.duplicate_key)
        self.assertNotEqual(replacement.branch_id, branch.branch_id)
        # The original stays addressable and linked through the retry record.
        self.assertIs(pool.get(branch.branch_id).state, BranchState.ABANDONED)
        self.assertEqual(pool.retries()[0].original_branch_id, branch.branch_id)

    def test_retry_that_changes_nothing_is_refused(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            RetryAuthorization(
                retry_id="retry.noop",
                original_branch_id="branch.x",
                changed_field="constraint_configuration",
                previous_value="same",
                new_value="same",
                authorized_by="actor.owner",
            )

    def test_retry_must_name_a_changeable_input_or_policy(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            RetryAuthorization(
                retry_id="retry.bad",
                original_branch_id="branch.x",
                changed_field="mood",
                previous_value="a",
                new_value="b",
                authorized_by="actor.owner",
            )

    def test_history_is_append_only_and_prior_snapshots_are_unchanged(self) -> None:
        """Forbidden: deletion of failure history or in-place edits."""
        pool = portfolio()
        branch = enqueue(pool, hypothesis="the iteration converges")
        original = branch.value()
        pool.transition(
            branch.branch_id, to_state=BranchState.ACTIVE, reason="start", actor_id="actor.owner"
        )
        pool.transition(
            branch.branch_id, to_state=BranchState.ABANDONED, reason="stop", actor_id="actor.owner"
        )
        # The first snapshot object is byte-identical to what it was.
        self.assertEqual(branch.value(), original)
        self.assertIs(branch.state, BranchState.PROPOSED)
        # Every snapshot is retained in append order.
        self.assertEqual(
            [item.state.value for item in pool.history()], ["proposed", "active", "abandoned"]
        )
        self.assertEqual([item.sequence for item in pool.transitions()], [1, 2])

    def test_terminal_states_admit_no_further_transition(self) -> None:
        pool = portfolio()
        branch = enqueue(pool, hypothesis="the iteration converges")
        pool.transition(
            branch.branch_id, to_state=BranchState.ABANDONED, reason="stop", actor_id="actor.owner"
        )
        with self.assertRaises(SynthesisValidationError):
            pool.transition(
                branch.branch_id, to_state=BranchState.ACTIVE, reason="resume", actor_id="actor.owner"
            )

    def test_semantic_similarity_never_silently_deduplicates(self) -> None:
        """Forbidden: semantic-similarity deduplication.

        Two differently worded hypotheses are distinct attempts. Any claim that
        they are equivalent must be a separately recorded relation proposal, so
        the portfolio must enqueue both.
        """
        pool = portfolio()
        first = enqueue(pool, hypothesis="the iteration reaches a global optimum")
        second = enqueue(pool, hypothesis="the procedure attains the best possible value")
        self.assertNotEqual(first.duplicate_key, second.duplicate_key)
        self.assertEqual(len(pool.branches()), 2)

    def test_branch_requires_falsification_conditions(self) -> None:
        pool = portfolio()
        with self.assertRaises(SynthesisValidationError):
            pool.enqueue(
                hypothesis="the iteration converges",
                strategy_family="direct_proof",
                objective_delta="none",
                falsification_conditions=(),
                input_graph_snapshot_identity=SNAPSHOT,
                constraint_configuration=CONFIG,
            )

    def test_depth_and_count_bounds_are_enforced(self) -> None:
        pool = portfolio(branch_depth=1)
        root = enqueue(pool, hypothesis="root claim")
        child = enqueue(pool, hypothesis="child claim", parent_branch_id=root.branch_id)
        self.assertEqual(child.depth, 1)
        with self.assertRaises(SynthesisValidationError):
            enqueue(pool, hypothesis="grandchild claim", parent_branch_id=child.branch_id)

    def test_generation_attempt_bound_limits_enqueues_independently_of_count(self) -> None:
        pool = portfolio(branch_count=6, branch_generation_attempts=1)
        first = enqueue(pool, hypothesis="first claim")
        history = pool.history()
        with self.assertRaises(BudgetExhausted) as caught:
            enqueue(pool, hypothesis="second claim")
        self.assertEqual(caught.exception.counter, "branch_generation_attempts")
        self.assertEqual(pool.history(), history)
        self.assertEqual(pool.branches(), (first,))
        self.assertEqual(pool.ledger.consumed()["branch_generation_attempts"], 1)
        self.assertEqual(pool.ledger.consumed()["branch_count"], 1)

    def test_creation_counter_charge_is_atomic_when_branch_count_is_exhausted(self) -> None:
        pool = portfolio(branch_count=1, branch_generation_attempts=8)
        enqueue(pool, hypothesis="first claim")
        consumed = pool.ledger.consumed()
        history = pool.history()
        with self.assertRaises(BudgetExhausted) as caught:
            enqueue(pool, hypothesis="second claim")
        self.assertEqual(caught.exception.counter, "branch_count")
        self.assertEqual(pool.ledger.consumed(), consumed)
        self.assertEqual(pool.history(), history)

    def test_each_transition_consumes_budget_before_appending_history(self) -> None:
        pool = portfolio(branch_count=6, branch_generation_attempts=2)
        branch = enqueue(pool, hypothesis="bounded transition claim")
        pool.transition(
            branch.branch_id,
            to_state=BranchState.ACTIVE,
            reason="begin work",
            actor_id="actor.owner",
        )
        history = pool.history()
        transitions = pool.transitions()
        with self.assertRaises(BudgetExhausted) as caught:
            pool.transition(
                branch.branch_id,
                to_state=BranchState.ABANDONED,
                reason="stop work",
                actor_id="actor.owner",
            )
        self.assertEqual(caught.exception.counter, "branch_generation_attempts")
        self.assertEqual(pool.history(), history)
        self.assertEqual(pool.transitions(), transitions)
        self.assertIs(pool.get(branch.branch_id).state, BranchState.ACTIVE)

    def test_invalid_transition_does_not_consume_budget_or_mutate_history(self) -> None:
        pool = portfolio()
        branch = enqueue(pool, hypothesis="invalid transition claim")
        consumed = pool.ledger.consumed()
        history = pool.history()
        with self.assertRaises(SynthesisValidationError):
            pool.transition(
                branch.branch_id,
                to_state=BranchState.COMPLETED,
                reason="skip the active state",
                actor_id="actor.owner",
            )
        self.assertEqual(pool.ledger.consumed(), consumed)
        self.assertEqual(pool.history(), history)
        self.assertEqual(pool.transitions(), ())


class SteeringTests(unittest.TestCase):
    """ERS-AC-12: append-only human steering."""

    def setUp(self) -> None:
        self.policy = BudgetPolicy.from_value(VALID_POLICY)
        self.log = SteeringLog(root_id="objective.main", policy=self.policy)

    def test_appended_record_carries_authority_causality_and_previous_view(self) -> None:
        before = self.log.current_view_identity()
        record = self.log.append(
            principal=HUMAN,
            action=SteeringAction.SELECT_BRANCH,
            instruction="pursue the boundary counterexample branch",
            idempotency_key="steer-1",
            target_branch_id="branch.boundary",
        )
        self.assertEqual(record.sequence, 1)
        self.assertEqual(record.causal_predecessor_id, "objective.main")
        self.assertEqual(record.previous_view_identity, before)
        self.assertEqual(record.value()["authority"], "human_final")
        # The current view changed deterministically.
        self.assertNotEqual(self.log.current_view_identity(), before)

    def test_second_record_chains_to_the_first(self) -> None:
        first = self.log.append(
            principal=HUMAN,
            action=SteeringAction.SELECT_BRANCH,
            instruction="pursue branch A",
            idempotency_key="steer-1",
            target_branch_id="branch.a",
        )
        second = self.log.append(
            principal=HUMAN,
            action=SteeringAction.STOP,
            instruction="stop after the boundary result",
            idempotency_key="steer-2",
        )
        self.assertEqual(second.causal_predecessor_id, first.steering_id)
        self.assertEqual(second.sequence, 2)

    def test_prior_records_stay_byte_identical_after_later_appends(self) -> None:
        """Forbidden: in-place edits or history deletion."""
        first = self.log.append(
            principal=HUMAN,
            action=SteeringAction.SELECT_BRANCH,
            instruction="pursue branch A",
            idempotency_key="steer-1",
            target_branch_id="branch.a",
        )
        snapshot = first.value()
        for index in range(2, 5):
            self.log.append(
                principal=HUMAN,
                action=SteeringAction.REDIRECT_OBJECTIVE,
                instruction=f"redirect {index}",
                idempotency_key=f"steer-{index}",
                target_objective_id="objective.secondary",
            )
        self.assertEqual(self.log.records()[0].value(), snapshot)
        self.assertEqual([item.sequence for item in self.log.records()], [1, 2, 3, 4])

    def test_exact_retry_returns_the_existing_record_without_duplicating(self) -> None:
        """Forbidden: duplicate record on retry."""
        arguments = {
            "principal": HUMAN,
            "action": SteeringAction.SELECT_BRANCH,
            "instruction": "pursue branch A",
            "idempotency_key": "steer-1",
            "target_branch_id": "branch.a",
        }
        first = self.log.append(**arguments)
        second = self.log.append(**arguments)
        self.assertEqual(first.steering_id, second.steering_id)
        self.assertEqual(len(self.log.records()), 1)

    def test_reused_key_with_different_semantics_fails_closed(self) -> None:
        self.log.append(
            principal=HUMAN,
            action=SteeringAction.SELECT_BRANCH,
            instruction="pursue branch A",
            idempotency_key="steer-1",
            target_branch_id="branch.a",
        )
        with self.assertRaises(SynthesisValidationError):
            self.log.append(
                principal=HUMAN,
                action=SteeringAction.SELECT_BRANCH,
                instruction="pursue branch B",
                idempotency_key="steer-1",
                target_branch_id="branch.b",
            )

    def test_rebudget_may_only_lower_a_bound(self) -> None:
        """Forbidden: unauthorized budget increase."""
        record = self.log.append(
            principal=HUMAN,
            action=SteeringAction.REBUDGET,
            instruction="narrow the graph budget",
            idempotency_key="steer-budget",
            lowered_bounds={"graph_nodes": 20},
        )
        self.assertEqual(self.log.policy.graph_nodes, 20)
        self.assertEqual(record.action, SteeringAction.REBUDGET)
        with self.assertRaises(SynthesisValidationError):
            self.log.append(
                principal=HUMAN,
                action=SteeringAction.REBUDGET,
                instruction="widen it again",
                idempotency_key="steer-budget-2",
                lowered_bounds={"graph_nodes": 500},
            )
        # The refused instruction changed nothing.
        self.assertEqual(self.log.policy.graph_nodes, 20)

    def test_nonhuman_and_underauthorized_principals_fail_closed(self) -> None:
        for actor_kind, authority in (
            ("model", "human_final"),
            ("automation", "human_final"),
            ("system", "deterministic_policy"),
            ("human", "proposal"),
        ):
            principal = SteeringPrincipal(
                principal_id="principal.other",
                actor_kind=actor_kind,
                authority=authority,
                capability_id="capability.steer",
                capability_operation="steer_research",
            )
            with self.subTest(actor_kind=actor_kind, authority=authority):
                with self.assertRaises(PermissionError):
                    self.log.append(
                        principal=principal,
                        action=SteeringAction.STOP,
                        instruction="stop",
                        idempotency_key=f"steer-{actor_kind}-{authority}",
                    )
        self.assertEqual(self.log.records(), ())

    def test_wrong_capability_operation_fails_closed(self) -> None:
        principal = SteeringPrincipal(
            principal_id="principal.owner",
            actor_kind="human",
            authority="human_final",
            capability_id="capability.surface",
            capability_operation="surface_verified_result",
        )
        with self.assertRaises(PermissionError):
            self.log.append(
                principal=principal,
                action=SteeringAction.STOP,
                instruction="stop",
                idempotency_key="steer-wrong-capability",
            )

    def test_target_arity_is_enforced_per_action(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            self.log.append(
                principal=HUMAN,
                action=SteeringAction.SELECT_BRANCH,
                instruction="pursue",
                idempotency_key="steer-no-target",
            )
        with self.assertRaises(SynthesisValidationError):
            self.log.append(
                principal=HUMAN,
                action=SteeringAction.STOP,
                instruction="stop",
                idempotency_key="steer-extra-target",
                target_branch_id="branch.a",
            )

    def test_only_a_rebudget_may_change_bounds(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            self.log.append(
                principal=HUMAN,
                action=SteeringAction.STOP,
                instruction="stop and shrink",
                idempotency_key="steer-sneaky",
                lowered_bounds={"graph_nodes": 10},
            )

    def test_view_identity_is_reproducible_from_the_record_sequence(self) -> None:
        for index in range(1, 4):
            self.log.append(
                principal=HUMAN,
                action=SteeringAction.REDIRECT_OBJECTIVE,
                instruction=f"redirect {index}",
                idempotency_key=f"steer-{index}",
                target_objective_id="objective.secondary",
            )
        replay = SteeringLog(root_id="objective.main", policy=self.policy)
        for index in range(1, 4):
            replay.append(
                principal=HUMAN,
                action=SteeringAction.REDIRECT_OBJECTIVE,
                instruction=f"redirect {index}",
                idempotency_key=f"steer-{index}",
                target_objective_id="objective.secondary",
            )
        self.assertEqual(replay.current_view_identity(), self.log.current_view_identity())
        self.assertEqual(replay.value(), self.log.value())


if __name__ == "__main__":
    unittest.main()
