"""Unit and adversarial tests for the unified campaign budget and backoff.

Everything is exact integer arithmetic.  Failures and rate-limit observations
are preserved in the ledger, an exceeded bound is reported rather than hidden,
and the backoff schedule is a bounded deterministic sequence rather than a
reconnect loop.
"""

from __future__ import annotations

import unittest

from math_research.campaign.budget import (
    BackoffPolicy,
    BudgetCapability,
    BudgetExhaustedError,
    CampaignBudget,
    CampaignBudgetError,
    CampaignBudgetLedger,
    ChargeEvent,
    SubBudget,
    backoff_delays_milliseconds,
    next_retry_delay_milliseconds,
)
from math_research.campaign.records import RecordStatus, UsageSource

PRICING_HASH = "sha256:" + "a" * 64
REQUEST_HASH = "sha256:" + "b" * 64


def sub(**overrides):
    values = dict(
        max_requests=10, max_input_tokens=1_000, max_output_tokens=1_000,
        max_cost_microusd=1_000_000, max_bytes=1_000_000, max_documents=100,
    )
    values.update(overrides)
    return SubBudget(**values)


def budget(**overrides):
    values = dict(
        campaign_id="campaign.slice2",
        pricing_snapshot_hash=PRICING_HASH,
        max_total_cost_microusd=2_000_000,
        max_wall_milliseconds=60_000,
        model=sub(), embedding=sub(), network=sub(), tool=sub(), storage=sub(),
    )
    values.update(overrides)
    return CampaignBudget(**values).finalized()


def clock():
    instants = iter(f"2026-08-22T00:00:{index:02d}Z" for index in range(60))
    return lambda: next(instants)


def charge(ledger, **overrides):
    values = dict(
        capability=BudgetCapability.MODEL,
        credential_profile_id="adaivy",
        purpose="campaign_planner",
        status=RecordStatus.COMPLETED,
        request_hash=REQUEST_HASH,
        usage_source=UsageSource.API_REPORTED,
        input_tokens=10, output_tokens=5, cost_microusd=200,
    )
    values.update(overrides)
    return ledger.charge(**values)


class CampaignBudgetTests(unittest.TestCase):
    def test_budget_hash_round_trips_and_detects_tampering(self):
        built = budget()
        built.verify_hashes()
        forged = CampaignBudget(
            campaign_id=built.campaign_id,
            pricing_snapshot_hash=built.pricing_snapshot_hash,
            max_total_cost_microusd=built.max_total_cost_microusd + 1,
            max_wall_milliseconds=built.max_wall_milliseconds,
            model=built.model, embedding=built.embedding, network=built.network,
            tool=built.tool, storage=built.storage,
            content_hash=built.content_hash,
        )
        with self.assertRaises(CampaignBudgetError):
            forged.verify_hashes()

    def test_negative_and_boolean_quantities_are_rejected(self):
        with self.assertRaises(CampaignBudgetError):
            sub(max_requests=-1)
        with self.assertRaises(CampaignBudgetError):
            sub(max_documents=True)

    def test_an_unfinalized_budget_cannot_open_a_ledger(self):
        values = dict(
            campaign_id="campaign.slice2", pricing_snapshot_hash=PRICING_HASH,
            max_total_cost_microusd=1, max_wall_milliseconds=1,
            model=sub(), embedding=sub(), network=sub(), tool=sub(), storage=sub(),
        )
        with self.assertRaises(CampaignBudgetError):
            CampaignBudgetLedger(CampaignBudget(**values), recorded_at=clock())


class LedgerTests(unittest.TestCase):
    def test_all_capabilities_close_under_one_budget(self):
        ledger = CampaignBudgetLedger(budget(), recorded_at=clock())
        charge(ledger)
        charge(ledger, capability=BudgetCapability.EMBEDDING,
               purpose="corpus_embedding", input_tokens=40, output_tokens=0,
               cost_microusd=100, documents=2)
        charge(ledger, capability=BudgetCapability.NETWORK,
               purpose="acquire_source", usage_source=UsageSource.LOCALLY_MEASURED,
               input_tokens=0, output_tokens=0, cost_microusd=0,
               bytes_transferred=4_096)
        charge(ledger, capability=BudgetCapability.TOOL, purpose="run_program",
               usage_source=UsageSource.LOCALLY_MEASURED,
               input_tokens=0, output_tokens=0, cost_microusd=0)
        charge(ledger, capability=BudgetCapability.STORAGE, purpose="persist_artifact",
               usage_source=UsageSource.LOCALLY_MEASURED,
               input_tokens=0, output_tokens=0, cost_microusd=0,
               bytes_transferred=2_048)
        closeout = ledger.close(wall_milliseconds_used=1_234)

        self.assertEqual(closeout.status, "within_bounds")
        self.assertEqual(closeout.exceeded_bounds, ())
        self.assertEqual(closeout.total_cost_microusd, 300)
        self.assertEqual(closeout.remaining_total_cost_microusd, 2_000_000 - 300)
        self.assertEqual(closeout.wall_milliseconds_used, 1_234)
        self.assertEqual(closeout.remaining_wall_milliseconds, 60_000 - 1_234)
        self.assertEqual(closeout.charge_event_count, 5)
        self.assertEqual(closeout.pricing_snapshot_hash, PRICING_HASH)
        by_capability = {item.capability: item for item in closeout.capabilities}
        self.assertEqual(set(by_capability), set(BudgetCapability))
        model = by_capability[BudgetCapability.MODEL]
        self.assertEqual(
            (model.requests_attempted, model.requests_completed,
             model.requests_failed, model.requests_incomplete),
            (1, 1, 0, 0),
        )
        self.assertEqual(model.remaining_requests, 9)
        embedding = by_capability[BudgetCapability.EMBEDDING]
        self.assertEqual(embedding.documents, 2)
        self.assertEqual(embedding.remaining_documents, 98)
        self.assertEqual(by_capability[BudgetCapability.NETWORK].bytes_transferred, 4_096)
        self.assertEqual(by_capability[BudgetCapability.STORAGE].remaining_bytes,
                         1_000_000 - 2_048)

    def test_admit_fails_closed_before_any_effect(self):
        ledger = CampaignBudgetLedger(
            budget(model=sub(max_requests=1)), recorded_at=clock(),
        )
        ledger.admit(BudgetCapability.MODEL)
        charge(ledger)
        with self.assertRaises(BudgetExhaustedError):
            ledger.admit(BudgetCapability.MODEL)

    def test_the_total_cost_bound_refuses_what_sub_budgets_would_allow(self):
        ledger = CampaignBudgetLedger(
            budget(max_total_cost_microusd=250), recorded_at=clock(),
        )
        charge(ledger, cost_microusd=200)
        with self.assertRaises(BudgetExhaustedError):
            ledger.admit(BudgetCapability.EMBEDDING, cost_microusd=100)

    def test_an_observed_overshoot_is_preserved_and_then_refused(self):
        ledger = CampaignBudgetLedger(
            budget(model=sub(max_cost_microusd=100)), recorded_at=clock(),
        )
        ledger.admit(BudgetCapability.MODEL)
        # The provider reported more usage than the reservation: the paid
        # attempt is recorded, not discarded, and the ledger then refuses.
        event = charge(ledger, cost_microusd=150)
        self.assertEqual(event.cost_microusd, 150)
        with self.assertRaises(BudgetExhaustedError):
            ledger.admit(BudgetCapability.NETWORK)
        closeout = ledger.close(wall_milliseconds_used=1)
        self.assertEqual(closeout.status, "exceeded")
        self.assertEqual(closeout.exceeded_bounds, ("model.cost_microusd",))

    def test_failures_and_rate_limits_are_preserved_in_the_closeout(self):
        ledger = CampaignBudgetLedger(budget(), recorded_at=clock())
        charge(ledger)
        charge(ledger, status=RecordStatus.FAILED,
               usage_source=UsageSource.UNAVAILABLE,
               input_tokens=0, output_tokens=0, cost_microusd=0,
               failure_classification="retryable:http_429",
               rate_limit_retry_after_milliseconds=2_000)
        charge(ledger, status=RecordStatus.INCOMPLETE,
               usage_source=UsageSource.UNAVAILABLE,
               input_tokens=0, output_tokens=0, cost_microusd=0,
               failure_classification="retryable:timeout")
        closeout = ledger.close(wall_milliseconds_used=5)
        self.assertEqual(closeout.failure_event_sequences, (2, 3))
        self.assertEqual(closeout.rate_limit_event_sequences, (2,))
        model = {item.capability: item for item in closeout.capabilities}[
            BudgetCapability.MODEL
        ]
        self.assertEqual(
            (model.requests_attempted, model.requests_completed,
             model.requests_failed, model.requests_incomplete),
            (3, 1, 1, 1),
        )

    def test_a_completed_charge_cannot_carry_a_failure_classification(self):
        ledger = CampaignBudgetLedger(budget(), recorded_at=clock())
        with self.assertRaises(CampaignBudgetError):
            charge(ledger, failure_classification="looks_fine_anyway")

    def test_wall_time_exhaustion_is_reported_at_close(self):
        ledger = CampaignBudgetLedger(
            budget(max_wall_milliseconds=100), recorded_at=clock(),
        )
        closeout = ledger.close(wall_milliseconds_used=101)
        self.assertEqual(closeout.status, "exceeded")
        self.assertIn("total.wall_milliseconds", closeout.exceeded_bounds)
        self.assertEqual(closeout.remaining_wall_milliseconds, -1)

    def test_a_closed_ledger_is_terminal(self):
        ledger = CampaignBudgetLedger(budget(), recorded_at=clock())
        ledger.close(wall_milliseconds_used=1)
        with self.assertRaises(CampaignBudgetError):
            charge(ledger)
        with self.assertRaises(CampaignBudgetError):
            ledger.close(wall_milliseconds_used=1)
        with self.assertRaises(BudgetExhaustedError):
            ledger.admit(BudgetCapability.MODEL)

    def test_events_are_append_only_and_sequenced(self):
        ledger = CampaignBudgetLedger(budget(), recorded_at=clock())
        charge(ledger)
        charge(ledger, capability=BudgetCapability.TOOL, purpose="run_program",
               usage_source=UsageSource.LOCALLY_MEASURED,
               input_tokens=0, output_tokens=0, cost_microusd=0)
        self.assertEqual([item.sequence for item in ledger.events], [1, 2])
        exported = ledger.events
        self.assertIsInstance(exported, tuple)

    def test_usage_and_timing_are_operational_not_semantic(self):
        ledger_a = CampaignBudgetLedger(budget(), recorded_at=clock())
        later = iter(["2026-08-22T09:00:00Z"])
        ledger_b = CampaignBudgetLedger(budget(), recorded_at=lambda: next(later))
        first = charge(ledger_a, input_tokens=10, output_tokens=5, cost_microusd=200)
        second = charge(ledger_b, input_tokens=99, output_tokens=1, cost_microusd=7)
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertNotEqual(first.operational_hash, second.operational_hash)

    def test_charge_event_rejects_unknown_schema(self):
        with self.assertRaises(CampaignBudgetError):
            ChargeEvent(
                sequence=1, campaign_id="campaign.slice2",
                capability=BudgetCapability.MODEL,
                credential_profile_id="adaivy", purpose="campaign_planner",
                status=RecordStatus.COMPLETED, request_hash=REQUEST_HASH,
                usage_source=UsageSource.UNAVAILABLE, requests=1,
                input_tokens=0, output_tokens=0, cost_microusd=0,
                bytes_transferred=0, documents=0, failure_classification=None,
                rate_limit_retry_after_milliseconds=None,
                recorded_at="2026-08-22T00:00:00Z",
                schema_version="adaivy.campaign-budget.v2",
            )


class BackoffTests(unittest.TestCase):
    def policy(self, **overrides):
        values = dict(
            base_milliseconds=1_000, multiplier_numerator=3,
            multiplier_denominator=2, max_delay_milliseconds=8_000,
            max_retries=6,
        )
        values.update(overrides)
        return BackoffPolicy(**values)

    def test_schedule_is_exact_bounded_integer_arithmetic(self):
        delays = backoff_delays_milliseconds(self.policy())
        self.assertEqual(delays, (1_000, 1_500, 2_250, 3_375, 5_062, 7_593))
        self.assertEqual(delays, backoff_delays_milliseconds(self.policy()))

    def test_the_delay_ceiling_caps_growth(self):
        delays = backoff_delays_milliseconds(self.policy(
            multiplier_numerator=4, multiplier_denominator=1, max_retries=5,
        ))
        self.assertEqual(delays, (1_000, 4_000, 8_000, 8_000, 8_000))

    def test_retries_exhaust_to_terminal_none(self):
        policy = self.policy(max_retries=2)
        self.assertEqual(
            next_retry_delay_milliseconds(policy, retries_performed=0), 1_000,
        )
        self.assertEqual(
            next_retry_delay_milliseconds(policy, retries_performed=1), 1_500,
        )
        self.assertIsNone(
            next_retry_delay_milliseconds(policy, retries_performed=2),
        )

    def test_observed_retry_after_lengthens_but_never_shortens_or_extends(self):
        policy = self.policy()
        self.assertEqual(
            next_retry_delay_milliseconds(
                policy, retries_performed=0,
                observed_retry_after_milliseconds=5_000,
            ),
            5_000,
        )
        self.assertEqual(
            next_retry_delay_milliseconds(
                policy, retries_performed=1,
                observed_retry_after_milliseconds=1,
            ),
            1_500,
        )
        self.assertEqual(
            next_retry_delay_milliseconds(
                policy, retries_performed=0,
                observed_retry_after_milliseconds=3_600_000,
            ),
            8_000,
        )
        self.assertIsNone(
            next_retry_delay_milliseconds(
                policy, retries_performed=6,
                observed_retry_after_milliseconds=1,
            ),
        )

    def test_a_reconnect_loop_shape_is_rejected(self):
        with self.assertRaises(CampaignBudgetError):
            self.policy(multiplier_numerator=1, multiplier_denominator=2)
        with self.assertRaises(CampaignBudgetError):
            self.policy(base_milliseconds=0)
        with self.assertRaises(CampaignBudgetError):
            self.policy(max_delay_milliseconds=500)
        with self.assertRaises(CampaignBudgetError):
            self.policy(max_retries=65)


if __name__ == "__main__":
    unittest.main()
