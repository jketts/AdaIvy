"""Offline acceptance tests for the live-gateway campaign planner adapter."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest

from math_research.campaign.end_to_end import (
    ModelDrivenEndToEndCampaignRunner, RuntimeEffect, RuntimeEffectRegistry,
)
from math_research.campaign.planner import GatewayCampaignPlanner
from math_research.campaign.records import ActionType, RecordStatus, UsageSource
from math_research.campaign.runner import CampaignRunnerError, PlannerContext
from math_research.campaign.runner import (
    CampaignRunnerPolicy, SequentialCampaignRunner,
)
from math_research.campaign.replay import build_campaign_export
from math_research.domain.entities import OpaqueId
from math_research.phase2.live_config import create_live_run_configuration
from math_research.phase2.pricing import create_pricing_snapshot
from math_research.phase2.records import (
    BudgetLimits, ModelResult, ModelResultStatus, ModelUsage,
)
from math_research.provider_activation import LiveProviderProbeResult


def pricing():
    return create_pricing_snapshot(
        snapshot_id=OpaqueId("pricing.campaign.azure.v1"), provider="azure_openai",
        model_identifier="gpt-5.6-sol", source="confirmed acceptance rate",
        captured_at="2026-08-21T00:00:00Z", currency="USD",
        input_microusd_per_million_tokens=10_000_000,
        output_microusd_per_million_tokens=20_000_000,
    )


def configuration(*, attempts=4):
    return create_live_run_configuration(
        configuration_id=OpaqueId("config.campaign.azure.v1"), provider="azure_openai",
        model_identifier="gpt-5.6-sol",
        pricing_snapshot_id=OpaqueId("pricing.campaign.azure.v1"),
        call_timeout_milliseconds=10_000, per_call_input_token_reserve=100,
        per_call_output_token_reserve=100,
        budget=BudgetLimits(
            max_input_tokens=1_000, max_output_tokens=1_000,
            max_cost_microusd=1_000_000, max_wall_milliseconds=60_000,
            max_attempts=attempts,
        ),
    )


def activation(*, passed=True, configured=None):
    configured = configured or configuration()
    return LiveProviderProbeResult(
        probe_status="passed" if passed else "failed",
        provider="azure_openai", model_identifier="gpt-5.6-sol",
        configuration_hash=configured.content_hash,
        pricing_snapshot_hash=pricing().content_hash,
        route_hash="sha256:" + "4" * 64,
        probe_request_hash="sha256:" + "5" * 64,
        observed_at="2026-08-21T00:00:01Z", acknowledgement_confirmed=True,
        static_preflight_status="passed", endpoint_reachability="reached",
        authentication_status="accepted" if passed else "rejected",
        deployment_route_status="accepted", provider_identity_status="passed",
        structured_output_capability="passed" if passed else "failed",
        operational_readiness="passed" if passed else "failed",
        failure_classification=None if passed else "auth_failed", sanitized_failure=None,
        requests_attempted=1, responses_completed=1,
        responses_succeeded=1 if passed else 0,
        responses_failed=0 if passed else 1, responses_incomplete=0,
        usage_reported_calls=1, input_tokens=3, output_tokens=2,
        estimated_cost_microusd=70, provider_request_id="activation-request",
    )


def action(kind="derive"):
    return json.dumps({
        "schema_version": "1.1.0", "action_type": kind, "branch_id": "branch.main",
        "rationale": "test", "artifact_text": "candidate" if kind == "derive" else None,
        "program_source": None, "tool_request": None, "selected_candidate_hash": None,
        "selected_tool_artifact_hashes": [], "report_text": None,
        "read_artifact_hash": None, "note_text": None,
    }, separators=(",", ":"), sort_keys=True)


def report_action():
    value = json.loads(action())
    value["action_type"] = "report"
    value["artifact_text"] = None
    value["report_text"] = "campaign complete"
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class Gateway:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    def prepare(self, request):
        return None

    def complete(self, request, preparation=None):
        self.requests.append(request)
        output, status = self.outputs.pop(0)
        return ModelResult(
            status=status, provider="azure_openai", model_identifier="gpt-5.6-sol",
            capabilities=("structured_output",), structured_output=output,
            declared_rationale=None, refusal=None,
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15,
                             usage_source="api_reported"),
            retry_classification="none", provider_request_id="provider-1",
        )


def context(sequence=1, tool_result=None):
    return PlannerContext(
        campaign_id="campaign.gateway.test", target_hash="sha256:" + "1" * 64,
        configuration_hash="sha256:" + "2" * 64, sequence=sequence,
        previous_action_id=None if sequence == 1 else f"action.{sequence - 1}",
        available_artifact_hashes=("sha256:" + "1" * 64,),
        recorded_program_hashes=(), selected_candidate_hash=None,
        selected_tool_artifact_hashes=(),
        latest_tool_result_hash=None if tool_result is None else "sha256:" + "3" * 64,
        latest_tool_result=tool_result, actions_remaining=3, tool_runs_remaining=2,
    )


class GatewayCampaignPlannerTests(unittest.TestCase):
    def test_v2_schema_selects_end_to_end_prompt_and_restores_accounting(self):
        raw = json.dumps({
            "schema_version": "2.0.0", "action_type": "search_literature",
            "branch_id": "branch.main", "rationale": "grounded search",
            "operation_request": {"query": "spectral graph"},
        }, separators=(",", ":"), sort_keys=True)
        gateway = Gateway([(raw, ModelResultStatus.SUCCEEDED)])
        schema = Path("schemas/model-campaign-action-v2.schema.json").read_text()
        planner = GatewayCampaignPlanner(
            configuration(), pricing(), gateway=gateway, activation=activation(),
            action_schema=schema, max_context_bytes=50_000,
        )
        response = planner(context())
        self.assertEqual("2.0.0", gateway.requests[0].template_version)
        self.assertIn("ordered cycles", gateway.requests[0].template_text)

        restored = GatewayCampaignPlanner(
            configuration(), pricing(), gateway=Gateway([]), activation=activation(),
            action_schema=schema, max_context_bytes=50_000,
        )
        restored.restore_checkpoint(1, {
            "action_json_base64": base64.b64encode(response.action_json).decode("ascii"),
            "status": "completed", "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "estimated_cost_microusd": response.estimated_cost_microusd,
            "provider": response.provider,
            "model_identifier": response.model_identifier,
        })
        self.assertEqual(2, restored.attempts_used)
        self.assertEqual(1, len(restored.previous_actions))

    def test_gateway_planner_drives_the_v2_runtime(self):
        def v2(kind, request):
            return json.dumps({
                "schema_version": "2.0.0", "action_type": kind,
                "branch_id": "branch.main", "rationale": "fixture",
                "operation_request": request,
            }, separators=(",", ":"), sort_keys=True)

        gateway = Gateway([
            (v2("search_literature", {"query": "exact graph"}),
             ModelResultStatus.SUCCEEDED),
            (v2("report", {"status": "bounded conclusion"}),
             ModelResultStatus.SUCCEEDED),
        ])
        configured = configuration(attempts=4)
        planner = GatewayCampaignPlanner(
            configured, pricing(), gateway=gateway,
            activation=activation(configured=configured),
            action_schema=Path("schemas/model-campaign-action-v2.schema.json").read_text(),
            max_context_bytes=50_000,
        )
        with tempfile.TemporaryDirectory() as temporary:
            summary = ModelDrivenEndToEndCampaignRunner(
                Path(temporary), campaign_id="campaign.gateway-v2",
                target_hash="sha256:" + "1" * 64,
                configuration_hash="sha256:" + "2" * 64,
                recorded_at="2026-08-22T00:00:00Z", max_actions=3,
                planner=planner,
                effects=RuntimeEffectRegistry({
                    ActionType.SEARCH_LITERATURE: RuntimeEffect(
                        lambda request, key: {"query": request["query"]}, True,
                    ),
                }),
            ).run()
        self.assertEqual("completed", summary["status"])
        self.assertEqual(["search_literature", "report"], summary["action_types"])
        self.assertEqual(2, len(gateway.requests))

    def test_activation_is_the_first_counted_campaign_model_attempt(self):
        gateway = Gateway([(report_action(), ModelResultStatus.SUCCEEDED)])
        planner = GatewayCampaignPlanner(
            configuration(), pricing(), gateway=gateway, activation=activation(),
            max_context_bytes=50_000,
        )

        class Artifacts:
            def __init__(self):
                self.values = {}

            def put(self, content, *, media_type):
                import hashlib
                key = "sha256:" + hashlib.sha256(content).hexdigest()
                self.values[key] = content
                return key

            def get(self, key):
                return self.values[key]

        def unused(_request):
            raise AssertionError("report-only campaign must not call a tool")

        run = SequentialCampaignRunner(
            campaign_id="campaign.gateway.integration", target_hash="sha256:" + "1" * 64,
            configuration_hash="sha256:" + "2" * 64,
            live_configuration_hash=configuration().content_hash,
            pricing_snapshot_hash=pricing().content_hash,
            planner_actor_id="model.central-lead", planner=planner,
            experiment_runner=unused, artifacts=Artifacts(), verifier=unused,
            policy=CampaignRunnerPolicy(
                allowed_tools=frozenset({"exact_python"}), max_actions=3,
                max_tool_runs=1, max_program_bytes=1_000, max_artifact_bytes=10_000,
                max_cpu_milliseconds=100, max_wall_milliseconds=100,
                max_memory_bytes=1_000, max_output_bytes=1_000, max_process_count=1,
            ),
            recorded_at=lambda: "2026-08-21T00:00:02Z",
        ).run()
        self.assertEqual(["provider_activation", "campaign_planner"], [
            item.purpose for item in run.model_calls
        ])
        self.assertEqual([1, 2], [item.sequence for item in run.actions])
        export = build_campaign_export(
            campaign_id=run.campaign_id, target_hash="sha256:" + "1" * 64,
            configuration_hash="sha256:" + "2" * 64, actions=run.actions,
            model_calls=run.model_calls, tool_runs=run.tool_runs,
        )
        self.assertEqual(2, export.usage["requests_attempted"])
        self.assertEqual(13, export.usage["input_tokens"])

    def test_sol_gateway_receives_bounded_transcript_and_exact_tool_bytes(self):
        gateway = Gateway([
            (action(), ModelResultStatus.SUCCEEDED),
            (action(), ModelResultStatus.SUCCEEDED),
        ])
        planner = GatewayCampaignPlanner(
            configuration(), pricing(), gateway=gateway, activation=activation(),
            max_context_bytes=50_000,
        )
        first = planner(context())
        exact = b"\x00exact\xfftool-result"
        second = planner(context(2, exact))
        self.assertEqual(RecordStatus.COMPLETED, first.status)
        self.assertEqual(UsageSource.API_REPORTED, second.usage_source)
        payload = json.loads(gateway.requests[1].serialized_context)
        self.assertEqual(base64.b64encode(exact).decode("ascii"), payload["latest_tool_result_base64"])
        self.assertEqual(json.loads(action()), payload["previous_actions"][0])
        self.assertEqual(3, planner.attempts_used)  # activation probe plus two actions

    def test_provider_failure_is_returned_as_a_recordable_failed_attempt(self):
        gateway = Gateway([(None, ModelResultStatus.FAILED)])
        planner = GatewayCampaignPlanner(
            configuration(), pricing(), gateway=gateway, activation=activation(),
            max_context_bytes=50_000,
        )
        result = planner(context())
        self.assertEqual(RecordStatus.FAILED, result.status)
        self.assertIn(b'"provider_result":"failed"', result.action_json)

    def test_activation_probe_consumes_the_same_attempt_bound(self):
        configured = configuration(attempts=1)
        planner = GatewayCampaignPlanner(
            configured, pricing(), gateway=Gateway([]),
            activation=activation(configured=configured), max_context_bytes=50_000,
        )
        with self.assertRaisesRegex(CampaignRunnerError, "attempt bound"):
            planner(context())

    def test_context_bound_is_enforced_before_gateway_call(self):
        gateway = Gateway([(action(), ModelResultStatus.SUCCEEDED)])
        planner = GatewayCampaignPlanner(
            configuration(), pricing(), gateway=gateway, activation=activation(),
            max_context_bytes=10,
        )
        with self.assertRaisesRegex(CampaignRunnerError, "context byte bound"):
            planner(context())
        self.assertEqual([], gateway.requests)

    def test_payload_carries_problem_statement_memory_and_feedback(self):
        """ADR-0077: the gateway payload is problem-visible and stateful."""

        from math_research.campaign.runner import ToolFeedback

        gateway = Gateway([(action(), ModelResultStatus.SUCCEEDED)])
        planner = GatewayCampaignPlanner(
            configuration(), pricing(), gateway=gateway, activation=activation(),
            max_context_bytes=100_000,
        )
        base = context(2, b"tool")
        import dataclasses
        enriched = dataclasses.replace(
            base,
            target_statement="Every even n > 2 is bounded.",
            target_statement_hash="sha256:" + "6" * 64,
            frozen_artifact_hashes=("sha256:" + "6" * 64,),
            notes=(("branch.main", "remember the parity argument"),),
            tool_feedback=(ToolFeedback(
                kind="verification", action_id="action.3",
                branch_id="branch.main", status="failed",
                result_hash="sha256:" + "7" * 64,
                result_excerpt='{"counterexample":1}', stderr_excerpt=None,
            ),),
            suspended_branch_ids=("branch.dead",),
            branch_last_status=(("branch.main", "completed"),),
            read_artifact_hash="sha256:" + "8" * 64,
            read_artifact_bytes=b"\x00exact",
            read_artifact_truncated=True,
            last_rejection="branch_id must be a valid identifier",
            repair_attempts_remaining=2,
        )
        planner(enriched)
        payload = json.loads(gateway.requests[0].serialized_context)
        self.assertEqual("Every even n > 2 is bounded.", payload["target_statement"])
        self.assertTrue(payload["target_statement_is_hash_attested"])
        self.assertEqual(
            [{"branch_id": "branch.main", "note_text": "remember the parity argument"}],
            payload["notes"],
        )
        feedback = payload["tool_feedback"][0]
        self.assertEqual("verification", feedback["kind"])
        self.assertTrue(feedback["untrusted_for_warrant"])
        self.assertIn("counterexample", feedback["result_excerpt"])
        self.assertEqual(["branch.dead"], payload["suspended_branch_ids"])
        self.assertEqual(
            base64.b64encode(b"\x00exact").decode("ascii"),
            payload["read_artifact_base64"],
        )
        self.assertTrue(payload["read_artifact_truncated"])
        self.assertTrue(payload["read_artifact_is_untrusted_data"])
        self.assertEqual(
            "branch_id must be a valid identifier", payload["last_rejection"],
        )
        self.assertEqual(2, payload["repair_attempts_remaining"])
        # Planner-side sub-budgets: activation consumed one of four attempts.
        self.assertEqual(3, payload["model_attempts_remaining"])
        self.assertGreater(payload["input_tokens_remaining"], 0)
        self.assertGreater(payload["cost_microusd_remaining"], 0)

    def test_failed_or_mismatched_activation_cannot_construct_a_planner(self):
        with self.assertRaisesRegex(CampaignRunnerError, "activation is required"):
            GatewayCampaignPlanner(
                configuration(), pricing(), gateway=Gateway([]),
                activation=activation(passed=False), max_context_bytes=50_000,
            )


if __name__ == "__main__":
    unittest.main()
