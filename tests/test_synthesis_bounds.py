"""Acceptance tests for the synthesis state axes and Section 5 run bounds.

ADR-0026 makes this suite the executable record of the slice's thresholds, so
each closed vocabulary and each fail-closed bound is asserted here rather than
described in a separate threshold inventory.
"""

from __future__ import annotations

import unittest

import sys
from pathlib import Path

# See tests/synthesis_fixtures.py: makes the sibling helper import work whether
# this module is run via `unittest discover -s tests` or by dotted module name.
sys.path.insert(0, str(Path(__file__).resolve().parent))


from math_research.synthesis.budget import (
    BOUND_FIELDS,
    BudgetExhausted,
    BudgetLedger,
    BudgetPolicy,
    POSITIVE_BOUNDS,
    RESERVE_FIELDS,
    ZERO_OR_POSITIVE_BOUNDS,
    allocate_with_reserve,
)
from synthesis_fixtures import VALID_POLICY

from math_research.synthesis.state import (
    ExtractionFidelity,
    GraphAdmission,
    MathematicalWarrant,
    MismatchKind,
    RelationType,
    SourceApplicability,
    StageOutcome,
    StrategyFamily,
    SynthesisValidationError,
    VerificationStage,
    blocked,
    budget_exhausted,
    parse_enum,
    validate_terminal_reason,
)

ALL_FAMILIES = [family.value for family in StrategyFamily]



class StateAxisVocabularyTests(unittest.TestCase):
    """Contract Section 2: the four axes are closed and independent."""

    def test_axis_vocabularies_are_exactly_the_contract_values(self) -> None:
        self.assertEqual(
            [item.value for item in SourceApplicability],
            ["proposed", "checked", "rejected", "unresolved"],
        )
        self.assertEqual(
            [item.value for item in ExtractionFidelity],
            ["proposed_extraction", "source_checked", "extraction_rejected"],
        )
        self.assertEqual(
            [item.value for item in MathematicalWarrant],
            [
                "unassessed",
                "empirically_tested",
                "counterexample_found",
                "proof_reviewed",
                "formally_verified",
            ],
        )
        self.assertEqual(
            [item.value for item in GraphAdmission],
            [
                "proposed",
                "admitted_under_policy",
                "excluded_under_policy",
                "invalidated_by_later_record",
            ],
        )

    def test_relation_vocabulary_is_the_ten_contract_relations(self) -> None:
        self.assertEqual(
            sorted(item.value for item in RelationType),
            sorted(
                [
                    "depends_on",
                    "implies",
                    "equivalent_to",
                    "stronger_than",
                    "weaker_than",
                    "specializes",
                    "generalizes",
                    "contradicts",
                    "uses_same_technique",
                    "requires_bridge",
                ]
            ),
        )

    def test_verification_funnel_is_eight_stages_by_five_outcomes(self) -> None:
        self.assertEqual(len(list(VerificationStage)), 8)
        self.assertEqual(
            [item.value for item in StageOutcome],
            ["not_run", "blocked", "failed", "inconclusive", "passed"],
        )

    def test_mathematical_warrant_has_no_ordering(self) -> None:
        """Section 2.4: warrant states are not a total order.

        Admission policy must evaluate an explicit permitted set, so the axis
        must not expose comparison that would let policy infer that
        counterexample_found sits above or below a proof state.
        """
        with self.assertRaises(TypeError):
            _ = MathematicalWarrant.COUNTEREXAMPLE_FOUND < MathematicalWarrant.PROOF_REVIEWED

    def test_unknown_axis_value_fails_closed_and_names_the_vocabulary(self) -> None:
        with self.assertRaises(SynthesisValidationError) as caught:
            parse_enum(GraphAdmission, "approved", field="graph_admission")
        # Section 2.4: no generic approval label is valid.
        self.assertIn("admitted_under_policy", str(caught.exception))

    def test_boolean_is_not_accepted_as_an_axis_value(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            parse_enum(GraphAdmission, True, field="graph_admission")


class TerminalReasonTests(unittest.TestCase):
    """Section 5: exactly one deterministic terminal reason per run."""

    def test_the_five_terminal_forms_are_accepted(self) -> None:
        for value in (
            "completed",
            "converged_under_rule",
            "user_intervention",
            budget_exhausted("retrieval_iterations"),
            blocked("rights_prohibited"),
        ):
            self.assertEqual(validate_terminal_reason(value), value)

    def test_unknown_or_malformed_terminal_reason_fails_closed(self) -> None:
        for value in ("finished", "budget_exhausted:", "blocked:", "budget_exhausted:a:b", ""):
            with self.subTest(value=value), self.assertRaises(SynthesisValidationError):
                validate_terminal_reason(value)

    def test_counter_name_must_be_colon_free(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            budget_exhausted("graph:nodes")


class BudgetPolicyValidationTests(unittest.TestCase):
    """Section 5: bounds are validated before a run begins."""

    def test_valid_policy_round_trips_through_its_canonical_value(self) -> None:
        policy = BudgetPolicy.from_value(VALID_POLICY)
        self.assertEqual(policy.value(), VALID_POLICY)
        self.assertEqual(BudgetPolicy.from_value(policy.value()), policy)

    def test_every_positive_bound_rejects_zero(self) -> None:
        for field in POSITIVE_BOUNDS:
            with self.subTest(field=field), self.assertRaises(SynthesisValidationError):
                BudgetPolicy.from_value({**VALID_POLICY, field: 0})

    def test_every_bound_rejects_negative_boolean_and_float(self) -> None:
        for field in POSITIVE_BOUNDS + ZERO_OR_POSITIVE_BOUNDS:
            for bad in (-1, True, 2.5, float("inf"), float("nan"), "3", None):
                with self.subTest(field=field, bad=repr(bad)):
                    with self.assertRaises(SynthesisValidationError):
                        BudgetPolicy.from_value({**VALID_POLICY, field: bad})

    def test_zero_permitted_bounds_accept_zero(self) -> None:
        for field in ("branch_depth", "model_calls", "tool_calls"):
            with self.subTest(field=field):
                policy = BudgetPolicy.from_value({**VALID_POLICY, field: 0})
                self.assertEqual(getattr(policy, field), 0)

    def test_acquisition_bounds_are_zero_if_and_only_if_both_are_zero(self) -> None:
        for patch in ({"acquired_sources": 4}, {"acquired_bytes": 4096}):
            with self.subTest(patch=patch), self.assertRaises(SynthesisValidationError):
                BudgetPolicy.from_value({**VALID_POLICY, **patch})
        both = BudgetPolicy.from_value(
            {**VALID_POLICY, "acquired_sources": 4, "acquired_bytes": 4096}
        )
        self.assertEqual((both.acquired_sources, both.acquired_bytes), (4, 4096))

    def test_missing_or_unknown_bound_fails_closed(self) -> None:
        for field in sorted(BOUND_FIELDS):
            partial = {key: value for key, value in VALID_POLICY.items() if key != field}
            with self.subTest(missing=field), self.assertRaises(SynthesisValidationError):
                BudgetPolicy.from_value(partial)
        with self.assertRaises(SynthesisValidationError):
            BudgetPolicy.from_value({**VALID_POLICY, "unbounded": 1})

    def test_reserve_ratio_must_satisfy_the_contract_inequality(self) -> None:
        for numerator, denominator in ((0, 4), (4, 4), (5, 4), (-1, 4), (1, 0), (1, -4)):
            with self.subTest(ratio=(numerator, denominator)):
                with self.assertRaises(SynthesisValidationError):
                    BudgetPolicy.from_value(
                        {
                            **VALID_POLICY,
                            "exploration_reserve_numerator": numerator,
                            "exploration_reserve_denominator": denominator,
                        }
                    )

    def test_reserved_attempts_uses_ceiling_arithmetic(self) -> None:
        cases = ((8, 1, 4, 2), (8, 1, 3, 3), (10, 1, 3, 4), (1, 1, 2, 1), (7, 2, 3, 5))
        for budget, numerator, denominator, expected in cases:
            with self.subTest(budget=budget, ratio=(numerator, denominator)):
                policy = BudgetPolicy.from_value(
                    {
                        **VALID_POLICY,
                        "branch_generation_attempts": budget,
                        "exploration_reserve_numerator": numerator,
                        "exploration_reserve_denominator": denominator,
                    }
                )
                self.assertEqual(policy.reserved_attempts(), expected)

    def test_no_component_may_increase_a_bound(self) -> None:
        policy = BudgetPolicy.from_value(VALID_POLICY)
        with self.assertRaises(SynthesisValidationError):
            policy.restrict(graph_nodes=policy.graph_nodes + 1)
        self.assertEqual(policy.restrict(graph_nodes=10).graph_nodes, 10)

    def test_reserve_ratio_cannot_be_restricted(self) -> None:
        policy = BudgetPolicy.from_value(VALID_POLICY)
        for field in RESERVE_FIELDS:
            with self.subTest(field=field), self.assertRaises(SynthesisValidationError):
                policy.restrict(**{field: 1})


class BudgetLedgerTests(unittest.TestCase):
    """Section 5: every loop body consumes a named counter before executing."""

    def setUp(self) -> None:
        self.policy = BudgetPolicy.from_value(VALID_POLICY)
        self.ledger = BudgetLedger(self.policy)

    def test_consumption_is_charged_against_the_named_counter(self) -> None:
        self.ledger.consume("retrieval_iterations")
        self.assertEqual(self.ledger.consumed()["retrieval_iterations"], 1)
        self.assertEqual(self.ledger.remaining("retrieval_iterations"), 2)

    def test_exhaustion_raises_with_the_terminal_reason_naming_the_counter(self) -> None:
        for _ in range(self.policy.retrieval_iterations):
            self.ledger.consume("retrieval_iterations")
        with self.assertRaises(BudgetExhausted) as caught:
            self.ledger.consume("retrieval_iterations")
        self.assertEqual(caught.exception.counter, "retrieval_iterations")
        self.assertEqual(
            caught.exception.terminal_reason, "budget_exhausted:retrieval_iterations"
        )
        self.assertEqual(validate_terminal_reason(caught.exception.terminal_reason),
                         "budget_exhausted:retrieval_iterations")

    def test_a_zero_bound_counter_disables_the_capability(self) -> None:
        with self.assertRaises(BudgetExhausted) as caught:
            self.ledger.consume("model_calls")
        self.assertEqual(caught.exception.counter, "model_calls")

    def test_unknown_counter_and_nonpositive_amount_fail_closed(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            self.ledger.consume("imagination")
        for amount in (0, -1, True, 1.5):
            with self.subTest(amount=repr(amount)), self.assertRaises(SynthesisValidationError):
                self.ledger.consume("retrieval_iterations", amount)

    def test_ledger_export_carries_bounds_and_consumption(self) -> None:
        self.ledger.consume("graph_nodes", 3)
        exported = self.ledger.ledger_value()
        self.assertEqual(exported["policy_version"], "synthesis-budget-v1")
        self.assertEqual(exported["bounds"]["graph_nodes"], 50)
        self.assertEqual(exported["consumed"]["graph_nodes"], 3)


class ExplorationReserveTests(unittest.TestCase):
    """Section 5.1: the reserve is enforceable, not advisory."""

    def setUp(self) -> None:
        self.policy = BudgetPolicy.from_value(VALID_POLICY)

    def test_valid_allocation_meets_the_reserve(self) -> None:
        allocation = allocate_with_reserve(
            self.policy,
            incumbent_family="direct_proof",
            eligible_families=["direct_proof", "counterexample_search"],
            allocations={"direct_proof": 6, "counterexample_search": 2},
        )
        self.assertEqual(allocation.reserved, 2)
        exported = allocation.value()
        self.assertEqual(exported["reserved"], 2)
        self.assertEqual(exported["reserve_unavailable"], [])

    def test_under_reserved_and_over_allocated_incumbent_both_fail(self) -> None:
        for allocations in ({"direct_proof": 7, "counterexample_search": 1}, {"direct_proof": 8}):
            with self.subTest(allocations=allocations):
                with self.assertRaises(SynthesisValidationError):
                    allocate_with_reserve(
                        self.policy,
                        incumbent_family="direct_proof",
                        eligible_families=["direct_proof", "counterexample_search"],
                        allocations=allocations,
                    )

    def test_no_waiver_applies_while_two_families_are_eligible(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            allocate_with_reserve(
                self.policy,
                incumbent_family="direct_proof",
                eligible_families=["direct_proof", "counterexample_search"],
                allocations={"direct_proof": 6, "counterexample_search": 2},
                waivers=[{"evaluated_families": ALL_FAMILIES, "exclusion_reason": "convenience"}],
            )

    def test_single_eligible_family_requires_one_waiver_per_unfilled_slot(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            allocate_with_reserve(
                self.policy,
                incumbent_family="direct_proof",
                eligible_families=["direct_proof"],
                allocations={"direct_proof": 8},
            )
        allocation = allocate_with_reserve(
            self.policy,
            incumbent_family="direct_proof",
            eligible_families=["direct_proof"],
            allocations={"direct_proof": 8},
            waivers=[
                {"evaluated_families": ALL_FAMILIES, "exclusion_reason": "no local corpus"},
                {"evaluated_families": ALL_FAMILIES, "exclusion_reason": "no tool adapter"},
            ],
        )
        self.assertEqual(len(allocation.waivers), allocation.reserved)

    def test_waiver_naming_a_subset_of_families_is_unsubstantiated(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            allocate_with_reserve(
                self.policy,
                incumbent_family="direct_proof",
                eligible_families=["direct_proof"],
                allocations={"direct_proof": 8},
                waivers=[
                    {"evaluated_families": ["direct_proof"], "exclusion_reason": "a"},
                    {"evaluated_families": ALL_FAMILIES, "exclusion_reason": "b"},
                ],
            )

    def test_allocation_to_an_ineligible_family_fails_closed(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            allocate_with_reserve(
                self.policy,
                incumbent_family="direct_proof",
                eligible_families=["direct_proof", "counterexample_search"],
                allocations={"restricted_cases": 2, "counterexample_search": 2},
            )

    def test_over_allocation_beyond_the_budget_fails_closed(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            allocate_with_reserve(
                self.policy,
                incumbent_family="direct_proof",
                eligible_families=["direct_proof", "counterexample_search"],
                allocations={"direct_proof": 6, "counterexample_search": 5},
            )

    def test_post_hoc_family_relabeling_is_rejected(self) -> None:
        """Strategy-family identity is versioned policy data, not free text."""
        with self.assertRaises(SynthesisValidationError):
            allocate_with_reserve(
                self.policy,
                incumbent_family="direct_proof",
                eligible_families=["direct_proof", "novel_family_invented_later"],
                allocations={"direct_proof": 6, "novel_family_invented_later": 2},
            )


if __name__ == "__main__":
    unittest.main()
