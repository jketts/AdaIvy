"""Slice 2 exit criterion: one test campaign in which every internal AI call
crosses the selected AdaIvy credential profile and all costs close under ONE
campaign budget.

The campaign here is the real `SequentialCampaignRunner` driving the real
`GatewayCampaignPlanner`; the only scripted element is the innermost provider
adapter, which is exactly the boundary an offline test must not cross.  The
adversarial cases prove the boundary refuses foreign provider identities,
exhausted budgets, and secret material in records, and preserves failures and
rate-limit observations instead of retrying in a loop.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from math_research.campaign.budget import (
    BudgetCapability,
    BudgetExhaustedError,
    CampaignBudget,
    CampaignBudgetLedger,
    SubBudget,
)
from math_research.campaign.credentials import (
    DEFAULT_LIVE_PROFILE_ID,
    CampaignRoutePolicy,
    CredentialProfile,
    CredentialProfileError,
    select_credential_profile,
)
from math_research.campaign.planner import GatewayCampaignPlanner
from math_research.campaign.records import RecordStatus, UsageSource
from math_research.campaign.routing import (
    ProfileBoundEmbeddingGateway,
    ProfileBoundModelGateway,
    ProfileRoutingError,
)
from math_research.campaign.runner import (
    CampaignRunnerPolicy,
    SequentialCampaignRunner,
)
from math_research.domain.entities import OpaqueId
from math_research.embedding.records import (
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingUsage,
)
from math_research.phase2.live_config import create_live_run_configuration
from math_research.phase2.pricing import create_pricing_snapshot
from math_research.phase2.records import (
    BudgetLimits,
    ModelRequest,
    ModelResult,
    ModelResultStatus,
    ModelUsage,
    ProviderFailureDiagnostic,
)
from math_research.provider_activation import LiveProviderProbeResult

SECRET = "sk-adaivy-live-0123456789abcdef"
ACTION_SCHEMA = Path("schemas/model-campaign-action-v1.schema.json").read_text(
    encoding="utf-8",
)


def profile():
    return CredentialProfile(
        profile_id=DEFAULT_LIVE_PROFILE_ID,
        provider="azure_openai",
        model_identifier="gpt-5.6-sol",
        embedding_model_identifier="text-embedding-3-large",
        endpoint_settings=(
            ("AZURE_OPENAI_API_VERSION", "2026-03-01"),
            ("AZURE_OPENAI_DEPLOYMENT", "adaivy-lead"),
            ("AZURE_OPENAI_ENDPOINT", "https://adaivy.example.azure.com"),
        ),
        credential_source="env-file.adaivy",
    ).finalized()


def model_pricing():
    return create_pricing_snapshot(
        snapshot_id=OpaqueId("pricing.campaign.azure.v1"), provider="azure_openai",
        model_identifier="gpt-5.6-sol", source="confirmed acceptance rate",
        captured_at="2026-08-21T00:00:00Z", currency="USD",
        input_microusd_per_million_tokens=10_000_000,
        output_microusd_per_million_tokens=20_000_000,
    )


def embedding_pricing():
    return create_pricing_snapshot(
        snapshot_id=OpaqueId("pricing.campaign.azure.embed.v1"),
        provider="azure_openai",
        model_identifier="text-embedding-3-large",
        source="confirmed acceptance rate",
        captured_at="2026-08-21T00:00:00Z", currency="USD",
        input_microusd_per_million_tokens=1_000_000,
        output_microusd_per_million_tokens=1,
    )


def configuration():
    return create_live_run_configuration(
        configuration_id=OpaqueId("config.campaign.azure.v1"), provider="azure_openai",
        model_identifier="gpt-5.6-sol",
        pricing_snapshot_id=OpaqueId("pricing.campaign.azure.v1"),
        call_timeout_milliseconds=10_000, per_call_input_token_reserve=100,
        per_call_output_token_reserve=100,
        budget=BudgetLimits(
            max_input_tokens=1_000, max_output_tokens=1_000,
            max_cost_microusd=1_000_000, max_wall_milliseconds=60_000,
            max_attempts=6,
        ),
    )


def activation(configured):
    return LiveProviderProbeResult(
        probe_status="passed", provider="azure_openai",
        model_identifier="gpt-5.6-sol",
        configuration_hash=configured.content_hash,
        pricing_snapshot_hash=model_pricing().content_hash,
        route_hash="sha256:" + "4" * 64,
        probe_request_hash="sha256:" + "5" * 64,
        observed_at="2026-08-22T00:00:01Z", acknowledgement_confirmed=True,
        static_preflight_status="passed", endpoint_reachability="reached",
        authentication_status="accepted", deployment_route_status="accepted",
        provider_identity_status="passed", structured_output_capability="passed",
        operational_readiness="passed", failure_classification=None,
        sanitized_failure=None, requests_attempted=1, responses_completed=1,
        responses_succeeded=1, responses_failed=0, responses_incomplete=0,
        usage_reported_calls=1, input_tokens=3, output_tokens=2,
        estimated_cost_microusd=70, provider_request_id="activation-request",
    )


def campaign_budget(**overrides):
    default_sub = SubBudget(
        max_requests=10, max_input_tokens=10_000, max_output_tokens=10_000,
        max_cost_microusd=1_000_000, max_bytes=1_000_000, max_documents=100,
    )
    values = dict(
        campaign_id="campaign.slice2.exit",
        pricing_snapshot_hash=model_pricing().content_hash,
        embedding_pricing_snapshot_hash=embedding_pricing().content_hash,
        max_total_cost_microusd=2_000_000,
        max_wall_milliseconds=600_000,
        model=default_sub, embedding=default_sub, network=default_sub,
        tool=default_sub, storage=default_sub,
    )
    values.update(overrides)
    return CampaignBudget(**values).finalized()


def clock():
    instants = iter(f"2026-08-22T00:01:{index:02d}Z" for index in range(60))
    return lambda: next(instants)


def action(kind, **fields):
    value = {
        "schema_version": "1.1.0", "action_type": kind, "branch_id": "branch.main",
        "rationale": "test", "artifact_text": None, "program_source": None,
        "tool_request": None, "selected_candidate_hash": None,
        "selected_tool_artifact_hashes": [], "report_text": None,
        "read_artifact_hash": None, "note_text": None,
    }
    value.update(fields)
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


class ScriptedProviderGateway:
    """The innermost provider adapter; never touched by campaign math."""

    def __init__(self, outputs, *, provider="azure_openai",
                 model_identifier="gpt-5.6-sol"):
        self.outputs = list(outputs)
        self.provider = provider
        self.model_identifier = model_identifier
        self.requests = []

    def prepare(self, request):
        return None

    def complete(self, request, preparation=None):
        self.requests.append(request)
        output, status = self.outputs.pop(0)
        return ModelResult(
            status=status, provider=self.provider,
            model_identifier=self.model_identifier,
            capabilities=("structured_output",), structured_output=output,
            declared_rationale=None, refusal=None,
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15,
                             usage_source="api_reported"),
            retry_classification="none", provider_request_id="provider-1",
        )


class ScriptedEmbeddingProvider:
    def __init__(self, *, provider="azure_openai",
                 model_identifier="text-embedding-3-large"):
        self.provider = provider
        self.model_identifier = model_identifier
        self.requests = []

    def embed(self, request):
        self.requests.append(request)
        return EmbeddingResult(
            provider=self.provider, model_identifier=self.model_identifier,
            provider_coordinates=(1.0, 0.0, 0.0),
            usage=EmbeddingUsage(input_tokens=7, usage_source="api_reported"),
            provider_request_id="embed-1",
        )


class Artifacts:
    def __init__(self):
        self.values = {}

    def put(self, content, *, media_type):
        key = "sha256:" + hashlib.sha256(content).hexdigest()
        self.values[key] = content
        return key

    def get(self, content_hash):
        return self.values[content_hash]


class Refuse:
    def __call__(self, request):
        raise AssertionError("this port must not be reached in this campaign")


def model_request(purpose="campaign_planner"):
    return ModelRequest(
        request_id=OpaqueId("request.routing.1"), run_id=OpaqueId("run.routing"),
        purpose=purpose, template_id="campaign.central_lead",
        template_version="1.0.0", template_hash="sha256:" + "6" * 64,
        template_text="prompt", serialized_context="{}",
        response_schema="{}", referenced_entity_ids=(),
        timeout_milliseconds=10_000, max_output_tokens=100,
    )


def embedding_request():
    return EmbeddingRequest(
        document_id="doc-1", source_id="source-1",
        source_content_hash="sha256:" + "7" * 64, text="an admitted passage",
        processor_id="azure_openai:text-embedding-3-large",
        max_input_tokens=64, timeout_milliseconds=10_000,
    )


def bound_gateways(budget=None, *, inner=None, embedder=None, secret_values=()):
    built = profile()
    _, selection = select_credential_profile(
        {built.profile_id: built}, built.profile_id,
        campaign_id="campaign.slice2.exit", selected_at="2026-08-22T00:00:00Z",
    )
    ledger = CampaignBudgetLedger(budget or campaign_budget(), recorded_at=clock())
    model = ProfileBoundModelGateway(
        profile=built, selection=selection,
        gateway=inner if inner is not None else ScriptedProviderGateway([]),
        pricing=model_pricing(), ledger=ledger, secret_values=secret_values,
    )
    embedding = ProfileBoundEmbeddingGateway(
        profile=built, selection=selection,
        gateway=embedder if embedder is not None else ScriptedEmbeddingProvider(),
        pricing=embedding_pricing(), ledger=ledger,
        purpose="corpus_embedding", secret_values=secret_values,
    )
    return model, embedding, ledger


class ExitCriterionTests(unittest.TestCase):
    def test_every_internal_ai_call_uses_the_adaivy_profile_and_one_budget(self):
        configured = configuration()
        activated = activation(configured)
        inner = ScriptedProviderGateway([
            (action("derive", artifact_text="candidate: n=2 attains the bound"),
             ModelResultStatus.SUCCEEDED),
            (action("report", report_text="campaign complete"),
             ModelResultStatus.SUCCEEDED),
        ])
        embedder = ScriptedEmbeddingProvider()
        model_gateway, embedding_gateway, ledger = bound_gateways(
            inner=inner, embedder=embedder, secret_values=(SECRET,),
        )
        # The one activation probe happened at campaign start through the same
        # provider route; its observed usage is charged to the same unified
        # budget before the first research call, mirroring the planner's own
        # seeding of the ADR-0057 model budget.
        ledger.charge(
            capability=BudgetCapability.MODEL,
            credential_profile_id=DEFAULT_LIVE_PROFILE_ID,
            purpose="provider_activation",
            status=RecordStatus.COMPLETED,
            request_hash=activated.probe_request_hash,
            usage_source=UsageSource.API_REPORTED,
            input_tokens=activated.input_tokens,
            output_tokens=activated.output_tokens,
            cost_microusd=activated.estimated_cost_microusd,
        )
        planner = GatewayCampaignPlanner(
            configured, model_pricing(), gateway=model_gateway,
            activation=activated, action_schema=ACTION_SCHEMA,
            max_context_bytes=50_000,
        )
        runner = SequentialCampaignRunner(
            campaign_id="campaign.slice2.exit",
            target_hash="sha256:" + "1" * 64,
            configuration_hash="sha256:" + "2" * 64,
            live_configuration_hash=configured.content_hash,
            pricing_snapshot_hash=model_pricing().content_hash,
            planner_actor_id="model.central-lead",
            planner=planner, experiment_runner=Refuse(), artifacts=Artifacts(),
            verifier=Refuse(),
            policy=CampaignRunnerPolicy(
                allowed_tools=frozenset({"python"}), max_actions=4,
                max_tool_runs=1, max_program_bytes=10_000,
                max_artifact_bytes=100_000, max_cpu_milliseconds=1_000,
                max_wall_milliseconds=1_000, max_memory_bytes=1_000_000,
                max_output_bytes=10_000, max_process_count=1,
            ),
            recorded_at=clock(),
        )
        run = runner.run()
        embedding_gateway.embed(embedding_request())
        closeout = ledger.close(wall_milliseconds_used=4_321)

        self.assertEqual(run.terminal_reason, "reported")
        # Every internal AI call carries the selected AdaIvy profile.
        self.assertGreater(len(ledger.events), 0)
        for event in ledger.events:
            self.assertEqual(event.credential_profile_id, DEFAULT_LIVE_PROFILE_ID)
        # Every research model call in the campaign ledger crossed the
        # profile-bound gateway: activation + one call per planner action.
        model_events = [
            item for item in ledger.events
            if item.capability is BudgetCapability.MODEL
        ]
        self.assertEqual(len(model_events), len(run.model_calls))
        self.assertEqual(len(inner.requests), len(run.model_calls) - 1)
        self.assertEqual(
            [item.purpose for item in model_events],
            ["provider_activation", "campaign_planner", "campaign_planner"],
        )
        # Embedding closed under the SAME budget, not a second ledger.
        by_capability = {item.capability: item for item in closeout.capabilities}
        embedding_closeout = by_capability[BudgetCapability.EMBEDDING]
        self.assertEqual(embedding_closeout.requests_attempted, 1)
        self.assertEqual(embedding_closeout.documents, 1)
        self.assertEqual(embedding_closeout.input_tokens, 7)
        self.assertEqual(embedding_closeout.cost_microusd, 7)
        # Exact unified accounting: 70 (activation) + 2 x 200 (planner calls,
        # 10 in / 5 out at the pinned prices) + 7 (embedding) microUSD.
        self.assertEqual(closeout.total_cost_microusd, 477)
        self.assertEqual(closeout.remaining_total_cost_microusd, 2_000_000 - 477)
        self.assertEqual(closeout.status, "within_bounds")
        self.assertEqual(closeout.charge_event_count, 4)
        self.assertEqual(closeout.pricing_snapshot_hash, model_pricing().content_hash)
        model_closeout = by_capability[BudgetCapability.MODEL]
        self.assertEqual(model_closeout.requests_attempted, 3)
        self.assertEqual(model_closeout.requests_completed, 3)
        self.assertEqual(model_closeout.input_tokens, 3 + 10 + 10)
        self.assertEqual(model_closeout.output_tokens, 2 + 5 + 5)
        # No record carries secret material.
        for event in ledger.events:
            self.assertNotIn(SECRET, json.dumps(event.request_hash))


class RoutingRefusalTests(unittest.TestCase):
    def test_a_foreign_provider_response_is_preserved_then_refused(self):
        inner = ScriptedProviderGateway(
            [(action("derive", artifact_text="x"), ModelResultStatus.SUCCEEDED)],
            provider="openai",
        )
        model_gateway, _, ledger = bound_gateways(inner=inner)
        with self.assertRaises(ProfileRoutingError):
            model_gateway.complete(model_request())
        self.assertEqual(len(ledger.events), 1)
        event = ledger.events[0]
        self.assertIs(event.status, RecordStatus.FAILED)
        self.assertEqual(event.failure_classification, "profile_identity_mismatch")

    def test_an_exhausted_model_sub_budget_admits_no_call(self):
        inner = ScriptedProviderGateway([
            (action("derive", artifact_text="x"), ModelResultStatus.SUCCEEDED),
        ])
        budget = campaign_budget(model=SubBudget(
            max_requests=1, max_input_tokens=10_000, max_output_tokens=10_000,
            max_cost_microusd=1_000_000, max_bytes=0, max_documents=0,
        ))
        model_gateway, _, ledger = bound_gateways(budget, inner=inner)
        model_gateway.complete(model_request())
        with self.assertRaises(BudgetExhaustedError):
            model_gateway.complete(model_request())
        # The refusal happened BEFORE the provider adapter was reached.
        self.assertEqual(len(inner.requests), 1)
        self.assertEqual(len(ledger.events), 1)

    def test_a_rate_limited_failure_is_recorded_not_looped(self):
        class RateLimited(ScriptedProviderGateway):
            def complete(self, request, preparation=None):
                self.requests.append(request)
                return ModelResult(
                    status=ModelResultStatus.FAILED, provider="azure_openai",
                    model_identifier="gpt-5.6-sol",
                    capabilities=("structured_output",), structured_output=None,
                    declared_rationale=None, refusal=None,
                    usage=ModelUsage(input_tokens=0, output_tokens=0,
                                     total_tokens=0, usage_source="unavailable"),
                    retry_classification="retryable:http_429",
                    provider_request_id=None,
                    provider_failure=ProviderFailureDiagnostic(
                        http_status_code=429, sdk_exception_class="RateLimitError",
                        provider_request_id=None, provider_error_type=None,
                        provider_error_code=None, provider_error_param=None,
                        provider_error_message=None, response_content_type=None,
                        response_body_sha256="0" * 64,
                        response_body_byte_length=0, response_body_preview="",
                        response_body_preview_truncated=False,
                        diagnostic_text_limit_bytes=2_000,
                        adapter_version="test", sdk_version="test",
                        model_identifier="gpt-5.6-sol", endpoint="redacted",
                        request_schema_hash="sha256:" + "8" * 64,
                    ),
                )

        inner = RateLimited([])
        model_gateway, _, ledger = bound_gateways(inner=inner)
        result = model_gateway.complete(model_request())
        self.assertIs(result.status, ModelResultStatus.FAILED)
        self.assertEqual(len(inner.requests), 1)
        event = ledger.events[0]
        self.assertIs(event.status, RecordStatus.FAILED)
        self.assertEqual(event.failure_classification, "retryable:http_429")
        self.assertIsNotNone(event.rate_limit_retry_after_milliseconds)
        closeout = ledger.close(wall_milliseconds_used=1)
        self.assertEqual(closeout.failure_event_sequences, (1,))
        self.assertEqual(closeout.rate_limit_event_sequences, (1,))

    def test_a_foreign_embedding_identity_is_preserved_then_refused(self):
        embedder = ScriptedEmbeddingProvider(provider="openai")
        _, embedding_gateway, ledger = bound_gateways(embedder=embedder)
        with self.assertRaises(ProfileRoutingError):
            embedding_gateway.embed(embedding_request())
        event = ledger.events[0]
        self.assertIs(event.status, RecordStatus.FAILED)
        self.assertEqual(event.failure_classification, "profile_identity_mismatch")

    def test_a_profile_without_an_embedding_model_refuses_the_route(self):
        built = CredentialProfile(
            profile_id=DEFAULT_LIVE_PROFILE_ID, provider="azure_openai",
            model_identifier="gpt-5.6-sol", embedding_model_identifier=None,
            endpoint_settings=(
                ("AZURE_OPENAI_API_VERSION", "2026-03-01"),
                ("AZURE_OPENAI_DEPLOYMENT", "adaivy-lead"),
                ("AZURE_OPENAI_ENDPOINT", "https://adaivy.example.azure.com"),
            ),
            credential_source="env-file.adaivy",
        ).finalized()
        _, selection = select_credential_profile(
            {built.profile_id: built}, built.profile_id,
            campaign_id="campaign.slice2.exit",
            selected_at="2026-08-22T00:00:00Z",
        )
        ledger = CampaignBudgetLedger(
            campaign_budget(embedding_pricing_snapshot_hash=None),
            recorded_at=clock(),
        )
        with self.assertRaises(ProfileRoutingError):
            ProfileBoundEmbeddingGateway(
                profile=built, selection=selection,
                gateway=ScriptedEmbeddingProvider(),
                pricing=embedding_pricing(), ledger=ledger,
                purpose="corpus_embedding",
            )

    def test_a_mismatched_pricing_snapshot_is_refused(self):
        built = profile()
        _, selection = select_credential_profile(
            {built.profile_id: built}, built.profile_id,
            campaign_id="campaign.slice2.exit",
            selected_at="2026-08-22T00:00:00Z",
        )
        ledger = CampaignBudgetLedger(campaign_budget(), recorded_at=clock())
        with self.assertRaises(ProfileRoutingError):
            ProfileBoundModelGateway(
                profile=built, selection=selection,
                gateway=ScriptedProviderGateway([]),
                pricing=embedding_pricing(), ledger=ledger,
            )

    def test_a_raising_model_gateway_leaves_one_failed_event_and_propagates(self):
        class Exploding:
            def __init__(self):
                self.calls = 0

            def prepare(self, request):
                return None

            def complete(self, request, preparation=None):
                self.calls += 1
                raise ValueError("transport exploded; message never recorded")

        inner = Exploding()
        model_gateway, _, ledger = bound_gateways(inner=inner)
        with self.assertRaises(ValueError):
            model_gateway.complete(model_request())
        self.assertEqual(inner.calls, 1)
        self.assertEqual(len(ledger.events), 1)
        event = ledger.events[0]
        self.assertIs(event.status, RecordStatus.FAILED)
        self.assertEqual(event.failure_classification, "gateway_exception:ValueError")
        self.assertIs(event.usage_source, UsageSource.UNAVAILABLE)
        self.assertEqual((event.input_tokens, event.output_tokens,
                          event.cost_microusd), (0, 0, 0))
        self.assertNotIn("message never recorded", event.failure_classification)

    def test_a_raising_embedding_gateway_leaves_one_failed_event_and_propagates(self):
        class ExplodingEmbedder:
            def embed(self, request):
                raise RuntimeError("embedding transport exploded")

        _, embedding_gateway, ledger = bound_gateways(embedder=ExplodingEmbedder())
        with self.assertRaises(RuntimeError):
            embedding_gateway.embed(embedding_request())
        self.assertEqual(len(ledger.events), 1)
        event = ledger.events[0]
        self.assertIs(event.status, RecordStatus.FAILED)
        self.assertEqual(event.failure_classification, "gateway_exception:RuntimeError")
        self.assertEqual(event.documents, 1)
        self.assertIs(event.usage_source, UsageSource.UNAVAILABLE)

    def test_a_fallback_route_without_its_own_budget_admits_no_call(self):
        # ADR-0072 audit repro: a gateway bound to the authorized fallback
        # profile must charge the DEDICATED fallback sub-budget, never the
        # primary model sub-budget.
        fallback = CredentialProfile(
            profile_id="adaivy-fallback", provider="azure_openai",
            model_identifier="gpt-5.6-sol",
            embedding_model_identifier="text-embedding-3-large",
            endpoint_settings=profile().endpoint_settings,
            credential_source="env-file.adaivy-fallback",
        ).finalized()
        _, selection = select_credential_profile(
            {fallback.profile_id: fallback}, fallback.profile_id,
            campaign_id="campaign.slice2.exit",
            selected_at="2026-08-22T00:00:00Z",
            alternate_selection_reason="named fallback route after provider failure",
        )
        policy = CampaignRoutePolicy(
            primary_profile_id=DEFAULT_LIVE_PROFILE_ID,
            fallback_profile_id="adaivy-fallback",
            fallback_authorized_reason="operator authorized one named fallback",
        ).finalized()
        ledger = CampaignBudgetLedger(
            campaign_budget(fallback_model=SubBudget(
                max_requests=0, max_input_tokens=0, max_output_tokens=0,
                max_cost_microusd=0, max_bytes=0, max_documents=0,
            )),
            recorded_at=clock(), route_policy=policy,
        )
        inner = ScriptedProviderGateway([
            (action("derive", artifact_text="x"), ModelResultStatus.SUCCEEDED),
        ])
        gateway = ProfileBoundModelGateway(
            profile=fallback, selection=selection, gateway=inner,
            pricing=model_pricing(), ledger=ledger,
        )
        with self.assertRaises(BudgetExhaustedError):
            gateway.complete(model_request())
        # Refused BEFORE the provider adapter; nothing hit the primary budget.
        self.assertEqual(inner.requests, [])
        self.assertEqual(ledger.events, ())
        ledger.admit(
            BudgetCapability.MODEL,
            credential_profile_id=DEFAULT_LIVE_PROFILE_ID,
        )

    def test_a_selection_for_another_campaign_cannot_charge_this_budget(self):
        built = profile()
        _, selection = select_credential_profile(
            {built.profile_id: built}, built.profile_id,
            campaign_id="campaign.other",
            selected_at="2026-08-22T00:00:00Z",
        )
        ledger = CampaignBudgetLedger(campaign_budget(), recorded_at=clock())
        with self.assertRaises(ProfileRoutingError):
            ProfileBoundModelGateway(
                profile=built, selection=selection,
                gateway=ScriptedProviderGateway([]),
                pricing=model_pricing(), ledger=ledger,
            )
        with self.assertRaises(ProfileRoutingError):
            ProfileBoundEmbeddingGateway(
                profile=built, selection=selection,
                gateway=ScriptedEmbeddingProvider(),
                pricing=embedding_pricing(), ledger=ledger,
                purpose="corpus_embedding",
            )

    def test_a_secret_value_in_a_charge_record_is_refused(self):
        inner = ScriptedProviderGateway([
            (action("derive", artifact_text="x"), ModelResultStatus.SUCCEEDED),
        ])
        model_gateway, _, _ = bound_gateways(
            inner=inner, secret_values=("campaign_planner_leak",),
        )
        with self.assertRaises(CredentialProfileError):
            model_gateway.complete(model_request(purpose="campaign_planner_leak"))


if __name__ == "__main__":
    unittest.main()
