"""Offline acceptance tests for the shared live-provider activation boundary."""

from __future__ import annotations

import unittest

from math_research.domain.entities import OpaqueId
from math_research.phase2.live_config import create_live_run_configuration
from math_research.phase2.pricing import create_pricing_snapshot, estimate_cost_microusd
from math_research.phase2.records import (
    BudgetLimits,
    ModelResult,
    ModelResultStatus,
    ModelUsage,
    ProviderFailureDiagnostic,
)
from math_research.phase2.serialization import canonical_json
from math_research.provider_activation import (
    GatewayProviderProbe,
    LIVE_PROBE_ACKNOWLEDGEMENT,
    PROBE_MAX_OUTPUT_TOKENS,
    ProviderProbeRequest,
    provider_route_hash,
    run_live_provider_probe,
    static_provider_preflight,
)


SECRET = "azure-secret-must-not-survive"
ENVIRONMENT = {
    "AZURE_OPENAI_API_KEY": SECRET,
    "AZURE_OPENAI_ENDPOINT": "https://resource.openai.azure.com",
    "AZURE_OPENAI_DEPLOYMENT": "sol-deployment",
    "AZURE_OPENAI_API_VERSION": "2025-04-01-preview",
}
OBSERVED_AT = "2026-08-21T18:00:00Z"


def pricing():
    return create_pricing_snapshot(
        snapshot_id=OpaqueId("pricing.activation.azure.v1"),
        provider="azure_openai",
        model_identifier="gpt-5.6-sol",
        source="confirmed test rate",
        captured_at=OBSERVED_AT,
        currency="USD",
        input_microusd_per_million_tokens=11_000_000,
        output_microusd_per_million_tokens=49_500_000,
    )


def configuration():
    return create_live_run_configuration(
        configuration_id=OpaqueId("config.activation.azure.v1"),
        provider="azure_openai",
        model_identifier="gpt-5.6-sol",
        pricing_snapshot_id=OpaqueId("pricing.activation.azure.v1"),
        call_timeout_milliseconds=120_000,
        per_call_input_token_reserve=10_000,
        per_call_output_token_reserve=2_048,
        budget=BudgetLimits(
            max_input_tokens=20_000,
            max_output_tokens=4_096,
            max_cost_microusd=2_000_000,
            max_wall_milliseconds=300_000,
            max_attempts=2,
        ),
    )


def usage(input_tokens=7, output_tokens=3, source="api_reported"):
    return ModelUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        usage_source=source,
    )


def result(
    status=ModelResultStatus.SUCCEEDED,
    *,
    output='{"ok":true}',
    failure=None,
    retry="none",
    model_identifier="gpt-5.6-sol",
    reported_usage=None,
):
    return ModelResult(
        status=status,
        provider="azure_openai",
        model_identifier=model_identifier,
        capabilities=("structured_output",),
        structured_output=output,
        declared_rationale=None,
        refusal=None,
        usage=reported_usage or usage(),
        retry_classification=retry,
        provider_request_id="request-provider-1",
        provider_failure=failure,
    )


def failure(status: int, *, message: str = "provider failure"):
    return ProviderFailureDiagnostic(
        http_status_code=status,
        sdk_exception_class="AuthenticationError",
        provider_request_id=None,
        provider_error_type=None,
        provider_error_code="Unauthorized" if status == 401 else "error",
        provider_error_param=None,
        provider_error_message=message,
        response_content_type="application/json",
        response_body_sha256="sha256:" + "a" * 64,
        response_body_byte_length=len(message),
        response_body_preview=message,
        response_body_preview_truncated=False,
        diagnostic_text_limit_bytes=4096,
        adapter_version="test-adapter/1",
        sdk_version="3.3.0",
        model_identifier="gpt-5.6-sol",
        endpoint=f"https://resource.openai.azure.com/{SECRET}",
        request_schema_hash="sha256:" + "b" * 64,
    )


class RecordingProbe:
    def __init__(self, response):
        self.response = response
        self.requests: list[ProviderProbeRequest] = []

    def __call__(self, request: ProviderProbeRequest) -> ModelResult:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ProviderActivationTests(unittest.TestCase):
    def test_gateway_probe_uses_the_same_admitted_gateway_once(self) -> None:
        class Gateway:
            def __init__(self):
                self.requests = []

            def prepare(self, request):
                self.requests.append(request)
                return None

            def complete(self, request, preparation=None):
                return result()

        gateway = Gateway()
        adapter = GatewayProviderProbe(configuration(), gateway)
        request = ProviderProbeRequest(
            provider="azure_openai", model_identifier="gpt-5.6-sol",
            configuration_hash=configuration().content_hash,
            pricing_snapshot_hash=pricing().content_hash,
            route_hash=provider_route_hash("azure_openai", ENVIRONMENT),
            timeout_milliseconds=1_000, max_input_tokens=512,
            max_output_tokens=128, max_cost_microusd=1_000_000,
        )
        self.assertEqual(ModelResultStatus.SUCCEEDED, adapter(request).status)
        self.assertEqual("provider_activation_probe", gateway.requests[0].purpose)
        self.assertNotIn(SECRET, gateway.requests[0].serialized_context)
        with self.assertRaisesRegex(ValueError, "single-use"):
            adapter(request)

    def static(self, environment=ENVIRONMENT):
        return static_provider_preflight(
            configuration(), pricing(), environment=environment,
            installed_sdk_version="3.3.0",
        )

    def execute(self, probe, *, static=None, environment=ENVIRONMENT, acknowledgement=LIVE_PROBE_ACKNOWLEDGEMENT):
        return run_live_provider_probe(
            static or self.static(environment), configuration(), pricing(),
            environment=environment, acknowledgement=acknowledgement,
            observed_at=OBSERVED_AT, probe=probe,
        )

    def test_static_pass_is_explicitly_not_live_readiness(self):
        checked = self.static()
        self.assertEqual("passed", checked.status)
        self.assertFalse(checked.network_call_performed)
        self.assertEqual("not_tested", checked.operational_readiness)
        self.assertEqual(configuration().content_hash, checked.configuration_hash)
        self.assertEqual(pricing().content_hash, checked.pricing_snapshot_hash)
        self.assertEqual(provider_route_hash("azure_openai", ENVIRONMENT), checked.route_hash)

    def test_missing_acknowledgement_performs_no_request(self):
        probe = RecordingProbe(result())
        observed = self.execute(probe, acknowledgement="")
        self.assertEqual("not_executed", observed.probe_status)
        self.assertEqual(0, observed.requests_attempted)
        self.assertEqual([], probe.requests)
        self.assertIn("live_probe_not_acknowledged", observed.failure_classification)

    def test_live_probe_is_exactly_one_attempt_with_no_retry(self):
        probe = RecordingProbe(result())
        observed = self.execute(probe)
        self.assertEqual("passed", observed.probe_status)
        self.assertEqual(1, observed.requests_attempted)
        self.assertEqual(1, len(probe.requests))
        self.assertEqual(1, probe.requests[0].max_attempts)
        self.assertEqual(0, probe.requests[0].max_retries)
        self.assertEqual(0, observed.retries_performed)
        self.assertEqual("passed", observed.operational_readiness)

    def test_401_is_reached_but_rejected_and_failure_is_sanitized(self):
        diagnostic = failure(401, message=f"bad key {SECRET}")
        probe = RecordingProbe(result(
            ModelResultStatus.FAILED, output=None, failure=diagnostic,
            retry="fatal:http_401", reported_usage=usage(0, 0, "unavailable"),
        ))
        observed = self.execute(probe)
        self.assertEqual("failed", observed.probe_status)
        self.assertEqual("reached", observed.endpoint_reachability)
        self.assertEqual("rejected", observed.authentication_status)
        self.assertEqual("indeterminate", observed.deployment_route_status)
        self.assertEqual(1, observed.requests_attempted)
        self.assertEqual(0, observed.responses_completed)
        self.assertEqual(1, observed.responses_failed)
        self.assertEqual(0, observed.responses_incomplete)
        self.assertEqual(0, observed.usage_reported_calls)
        self.assertEqual(0, observed.estimated_cost_microusd)
        rendered = canonical_json(observed)
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn("model output", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_top_level_provider_fields_are_redacted_too(self):
        compromised = result(
            ModelResultStatus.FAILED, output=None, failure=failure(401),
            retry=f"fatal:{SECRET}", reported_usage=usage(0, 0, "unavailable"),
        )
        compromised = ModelResult(
            status=compromised.status,
            provider=compromised.provider,
            model_identifier=compromised.model_identifier,
            capabilities=compromised.capabilities,
            structured_output=compromised.structured_output,
            declared_rationale=None,
            refusal=None,
            usage=compromised.usage,
            retry_classification=compromised.retry_classification,
            provider_request_id=f"request-{SECRET}",
            provider_failure=compromised.provider_failure,
        )
        observed = self.execute(RecordingProbe(compromised))
        self.assertNotIn(SECRET, canonical_json(observed))

    def test_connection_exception_is_one_unreachable_attempt_without_message(self):
        probe = RecordingProbe(RuntimeError(f"socket failed with {SECRET}"))
        observed = self.execute(probe)
        self.assertEqual(1, len(probe.requests))
        self.assertEqual("unreachable", observed.endpoint_reachability)
        self.assertEqual("indeterminate", observed.authentication_status)
        self.assertEqual("probe_exception:RuntimeError", observed.failure_classification)
        self.assertNotIn(SECRET, canonical_json(observed))

    def test_404_and_429_do_not_invent_authentication_acceptance(self):
        for status, route in ((404, "rejected"), (429, "indeterminate")):
            with self.subTest(status=status):
                observed = self.execute(RecordingProbe(result(
                    ModelResultStatus.FAILED, output=None, failure=failure(status),
                    retry=f"fatal:http_{status}", reported_usage=usage(0, 0, "unavailable"),
                )))
                self.assertEqual("indeterminate", observed.authentication_status)
                self.assertEqual(route, observed.deployment_route_status)
                self.assertEqual("failed", observed.operational_readiness)

    def test_success_counts_usage_cost_and_discards_response_text(self):
        probe = RecordingProbe(result(output="model output must be discarded"))
        observed = self.execute(probe)
        expected_cost = estimate_cost_microusd(pricing(), input_tokens=7, output_tokens=3)
        self.assertEqual(1, observed.responses_completed)
        self.assertEqual(1, observed.responses_succeeded)
        self.assertEqual(0, observed.responses_failed)
        self.assertEqual(1, observed.usage_reported_calls)
        self.assertEqual(expected_cost, observed.estimated_cost_microusd)
        self.assertFalse(observed.response_text_retained)
        self.assertNotIn("model output must be discarded", canonical_json(observed))
        self.assertFalse(observed.epistemic_warrant_created)

    def test_non_successful_2xx_response_proves_auth_not_capability(self):
        for status in (
            ModelResultStatus.MALFORMED,
            ModelResultStatus.INCOMPLETE,
            ModelResultStatus.REFUSED,
        ):
            with self.subTest(status=status):
                observed = self.execute(RecordingProbe(result(status, output=None)))
                self.assertEqual("accepted", observed.authentication_status)
                self.assertEqual("failed", observed.structured_output_capability)
                self.assertEqual("failed", observed.operational_readiness)

    def test_success_status_with_wrong_probe_payload_does_not_activate(self):
        observed = self.execute(RecordingProbe(result(output='{"ok":false}')))
        self.assertEqual("failed", observed.structured_output_capability)
        self.assertEqual("failed", observed.operational_readiness)

    def test_route_change_after_static_preflight_refuses_without_call(self):
        checked = self.static()
        changed = dict(ENVIRONMENT, AZURE_OPENAI_DEPLOYMENT="different-deployment")
        probe = RecordingProbe(result())
        observed = self.execute(probe, static=checked, environment=changed)
        self.assertEqual("not_executed", observed.probe_status)
        self.assertEqual([], probe.requests)
        self.assertIn("route_hash_changed", observed.failure_classification)

    def test_usage_above_probe_bound_cannot_pass(self):
        oversized = result(reported_usage=usage(7, PROBE_MAX_OUTPUT_TOKENS + 1))
        observed = self.execute(RecordingProbe(oversized))
        self.assertEqual("failed", observed.operational_readiness)
        self.assertEqual("probe_bound_exceeded", observed.failure_classification)


if __name__ == "__main__":
    unittest.main()
