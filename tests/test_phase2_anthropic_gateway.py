"""Hermetic acceptance for the opt-in Anthropic Messages adapter (ADR-0030).

No network, no credentials, no sockets: the SDK is a fake injected through the
adapter's own seam. These tests pin the provider facts that would otherwise fail
silently or fail closed for the wrong reason -- notably that no sampling
parameter and no thinking budget is ever sent, that `content` is treated as a
list of blocks, and that `stop_details` is read only for a refusal.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from math_research.phase2 import PHASE2_SCHEMA_VERSION
from math_research.phase2.anthropic_gateway import (
    ANTHROPIC_ADAPTER_VERSION,
    DEFAULT_MODEL_IDENTIFIER,
    SUPPORTED_MODEL_IDENTIFIERS,
    AnthropicConfigurationError,
    AnthropicMessagesGateway,
    AnthropicProviderConfig,
)
from math_research.phase2.records import ModelRequest, ModelResultStatus

API_KEY = "sk-ant-secret-value-do-not-leak-123456"
PROPOSER_SCHEMA = "schemas/model-proposer-v1.schema.json"


def valid_output() -> str:
    return json.dumps({
        "schema_version": PHASE2_SCHEMA_VERSION,
        "result_type": "candidate_claim",
        "target_claim_id": "claim.example.v1",
        "mathematical_payload": {
            "statement": "the sum of two even integers is even",
            "steps": ["let a = 2m", "let b = 2n", "a + b = 2(m + n)"],
            "witness": None,
        },
        "declared_rationale": "elementary parity argument",
        "referenced_entity_ids": ["claim.example.v1"],
    })


class Block:
    def __init__(self, type_: str, text: str | None = None) -> None:
        self.type = type_
        if text is not None:
            self.text = text


class Usage:
    def __init__(self, *, input_tokens=11, output_tokens=7, cache_write=0, cache_read=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_write
        self.cache_read_input_tokens = cache_read


_DEFAULT = object()


class Response:
    def __init__(
        self, *, content=None, stop_reason="end_turn", usage=_DEFAULT,
        stop_details=None, model=DEFAULT_MODEL_IDENTIFIER,
    ) -> None:
        self.content = content if content is not None else [Block("text", valid_output())]
        self.stop_reason = stop_reason
        # `usage=None` must stay None: it is the missing-usage case under test.
        self.usage = Usage() if usage is _DEFAULT else usage
        self.stop_details = stop_details
        self.model = model
        self._request_id = "req_example_0001"


class FakeAPIStatusError(Exception):
    def __init__(self, status_code, body=None, request_id="req_err_1") -> None:
        super().__init__("status error")
        self.status_code = status_code
        self.body = body
        self.request_id = request_id
        self.response = None


class FakeAPITimeoutError(Exception):
    pass


class FakeAPIConnectionError(Exception):
    pass


class FakeSDK:
    __version__ = "9.9.9-fake"
    APIStatusError = FakeAPIStatusError
    APITimeoutError = FakeAPITimeoutError
    APIConnectionError = FakeAPIConnectionError
    Anthropic = object


class FakeClient:
    def __init__(self, outcome, recorder: dict) -> None:
        self._outcome = outcome
        self._recorder = recorder
        self.messages = self

    def create(self, **payload):
        self._recorder.update(payload)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def request(**changes) -> ModelRequest:
    values = {
        "request_id": "request.1", "run_id": "run.1", "purpose": "proposer",
        "template_id": "proposer", "template_version": "1", "template_hash": "h",
        "template_text": "system instruction", "serialized_context": "context",
        "response_schema": Path(PROPOSER_SCHEMA).read_text(encoding="utf-8"),
        "referenced_entity_ids": (), "timeout_milliseconds": 30_000,
        "max_output_tokens": 4_096,
    }
    values.update(changes)
    return ModelRequest(**values)


class AnthropicGatewayTests(unittest.TestCase):
    def gateway(self, outcome, *, config=None, recorder=None):
        recorder = recorder if recorder is not None else {}
        configuration = config or AnthropicProviderConfig()
        return AnthropicMessagesGateway(
            configuration,
            sdk_module=FakeSDK,
            client_factory=lambda **_kwargs: FakeClient(outcome, recorder),
            credentials={"ANTHROPIC_API_KEY": API_KEY},
        ), recorder

    def test_default_model_is_opus_5_and_ids_carry_no_date_suffix(self) -> None:
        self.assertEqual("claude-opus-5", DEFAULT_MODEL_IDENTIFIER)
        for identifier in SUPPORTED_MODEL_IDENTIFIERS:
            with self.subTest(identifier=identifier):
                tail = identifier.rsplit("-", 1)[-1]
                self.assertFalse(
                    len(tail) == 8 and tail.isdigit(),
                    "model ids are complete as written; no date suffix",
                )

    def test_unsupported_model_or_effort_or_scheme_fails_closed(self) -> None:
        for change in (
            {"model_identifier": "claude-opus-5-20260101"},
            {"model_identifier": "gpt-5-mini"},
            {"effort": "extreme"},
            {"endpoint": "http://api.anthropic.com/v1/messages"},
        ):
            with self.subTest(change=change):
                with self.assertRaises(AnthropicConfigurationError):
                    AnthropicProviderConfig(**change)

    def test_no_sampling_parameter_or_thinking_budget_is_ever_sent(self) -> None:
        gateway, recorder = self.gateway(Response())
        gateway.complete(request())
        for forbidden in ("temperature", "top_p", "top_k"):
            self.assertNotIn(forbidden, recorder)
        self.assertEqual({"type": "adaptive"}, recorder["thinking"])
        self.assertNotIn("budget_tokens", recorder["thinking"])
        self.assertNotIn("output_format", recorder)
        self.assertIn("format", recorder["output_config"])
        self.assertEqual("high", recorder["output_config"]["effort"])

    def test_no_assistant_prefill_is_sent(self) -> None:
        gateway, recorder = self.gateway(Response())
        gateway.complete(request())
        roles = [message["role"] for message in recorder["messages"]]
        self.assertEqual(["user"], roles, "a trailing assistant prefill returns 400")

    def test_thinking_is_omitted_when_adaptive_is_disabled(self) -> None:
        gateway, recorder = self.gateway(
            Response(), config=AnthropicProviderConfig(adaptive_thinking=False),
        )
        gateway.complete(request())
        self.assertNotIn("thinking", recorder)

    def test_valid_response_succeeds_and_reports_usage(self) -> None:
        gateway, _ = self.gateway(Response())
        result = gateway.complete(request())
        self.assertEqual(ModelResultStatus.SUCCEEDED, result.status)
        self.assertEqual("anthropic", result.provider)
        self.assertEqual("api_reported", result.usage.usage_source)
        self.assertEqual(18, result.usage.total_tokens)
        self.assertEqual("req_example_0001", result.provider_request_id)

    def test_text_is_joined_across_blocks_and_ignores_thinking_blocks(self) -> None:
        payload = valid_output()
        split = len(payload) // 2
        gateway, _ = self.gateway(Response(content=[
            Block("thinking"), Block("text", payload[:split]),
            Block("text", payload[split:]),
        ]))
        self.assertEqual(
            ModelResultStatus.SUCCEEDED, gateway.complete(request()).status,
        )

    def test_content_without_any_text_block_is_malformed(self) -> None:
        gateway, _ = self.gateway(Response(content=[Block("thinking")]))
        result = gateway.complete(request())
        self.assertEqual(ModelResultStatus.MALFORMED, result.status)
        self.assertEqual("fatal:no_text_content", result.retry_classification)

    def test_output_failing_the_canonical_validator_is_never_accepted(self) -> None:
        for body in ("not json", json.dumps({"unexpected": True}), json.dumps([1])):
            with self.subTest(body=body[:20]):
                gateway, _ = self.gateway(Response(content=[Block("text", body)]))
                result = gateway.complete(request())
                self.assertEqual(ModelResultStatus.MALFORMED, result.status)
                self.assertIsNone(result.structured_output)

    def test_refusal_reads_stop_details_and_maps_to_refused(self) -> None:
        class Details:
            category = "cyber"

        gateway, _ = self.gateway(
            Response(stop_reason="refusal", stop_details=Details(), content=[]),
        )
        result = gateway.complete(request())
        self.assertEqual(ModelResultStatus.REFUSED, result.status)
        self.assertEqual("cyber", result.refusal)

    def test_refusal_without_stop_details_does_not_crash(self) -> None:
        gateway, _ = self.gateway(Response(stop_reason="refusal", stop_details=None))
        self.assertEqual(
            ModelResultStatus.REFUSED, gateway.complete(request()).status,
        )

    def test_max_tokens_is_incomplete_and_retains_usage(self) -> None:
        gateway, _ = self.gateway(Response(stop_reason="max_tokens"))
        result = gateway.complete(request())
        self.assertEqual(ModelResultStatus.INCOMPLETE, result.status)
        self.assertEqual(18, result.usage.total_tokens)

    def test_cache_tokens_are_counted_and_labelled_distinctly(self) -> None:
        gateway, _ = self.gateway(
            Response(usage=Usage(input_tokens=5, output_tokens=3, cache_write=10, cache_read=2)),
        )
        result = gateway.complete(request())
        self.assertEqual("api_reported_with_cache", result.usage.usage_source)
        self.assertEqual(17, result.usage.input_tokens)
        self.assertEqual(20, result.usage.total_tokens)

    def test_missing_or_boolean_usage_is_malformed_never_zero(self) -> None:
        for usage in (None, Usage(input_tokens=True, output_tokens=1), Usage(input_tokens="9")):
            with self.subTest(usage=type(usage).__name__):
                gateway, _ = self.gateway(Response(usage=usage))
                result = gateway.complete(request())
                self.assertEqual(ModelResultStatus.MALFORMED, result.status)
                self.assertEqual("fatal:usage_unavailable", result.retry_classification)

    def test_status_errors_are_classified_retryable_or_fatal(self) -> None:
        for status_code, expected in (
            (429, "retryable:http_429"), (408, "retryable:http_408"),
            (503, "retryable:http_503"), (500, "retryable:http_500"),
            (400, "fatal:http_400"), (401, "fatal:http_401"),
            (403, "fatal:http_403"), (404, "fatal:http_404"),
        ):
            with self.subTest(status_code=status_code):
                gateway, _ = self.gateway(FakeAPIStatusError(status_code))
                result = gateway.complete(request())
                self.assertEqual(ModelResultStatus.FAILED, result.status)
                self.assertEqual(expected, result.retry_classification)

    def test_absent_status_code_is_fatal_unknown_and_never_retried_blindly(self) -> None:
        for status_code in (None, "429", True):
            with self.subTest(status_code=status_code):
                gateway, _ = self.gateway(FakeAPIStatusError(status_code))
                result = gateway.complete(request())
                self.assertEqual("fatal:http_unknown", result.retry_classification)
                self.assertEqual(0, result.provider_failure.http_status_code)

    def test_timeout_and_connection_errors_are_retryable(self) -> None:
        for outcome, status, retry in (
            (FakeAPITimeoutError(), ModelResultStatus.TIMED_OUT, "retryable:timeout"),
            (FakeAPIConnectionError(), ModelResultStatus.FAILED, "retryable:connection"),
        ):
            with self.subTest(retry=retry):
                gateway, _ = self.gateway(outcome)
                result = gateway.complete(request())
                self.assertEqual(status, result.status)
                self.assertEqual(retry, result.retry_classification)

    def test_the_api_key_never_reaches_a_diagnostic(self) -> None:
        body = {"error": {
            "type": "authentication_error",
            "message": f"invalid key {API_KEY} supplied",
            "code": "invalid_api_key",
        }}
        gateway, _ = self.gateway(FakeAPIStatusError(401, body=body))
        result = gateway.complete(request())
        diagnostic = result.provider_failure
        self.assertNotIn(API_KEY, repr(diagnostic))
        self.assertNotIn(API_KEY, diagnostic.response_body_preview)
        self.assertNotIn(API_KEY, str(diagnostic.provider_error_message))
        self.assertEqual("authentication_error", diagnostic.provider_error_type)
        self.assertEqual(ANTHROPIC_ADAPTER_VERSION, diagnostic.adapter_version)

    def test_malformed_error_bodies_do_not_crash_the_diagnostic(self) -> None:
        for body in (None, "flat string", [1, 2], {}, {"error": "flat"}, {"error": [1]}):
            with self.subTest(body=repr(body)[:24]):
                gateway, _ = self.gateway(FakeAPIStatusError(500, body=body))
                result = gateway.complete(request())
                self.assertIsNotNone(result.provider_failure)
                self.assertEqual(ModelResultStatus.FAILED, result.status)

    def test_missing_credential_fails_closed_before_any_client_is_built(self) -> None:
        gateway = AnthropicMessagesGateway(
            AnthropicProviderConfig(), sdk_module=FakeSDK, credentials={},
        )
        with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY"):
            gateway.complete(request())

    def test_prepare_declares_no_provider_projection(self) -> None:
        gateway, _ = self.gateway(Response())
        self.assertIsNone(gateway.prepare(request()))


if __name__ == "__main__":
    unittest.main()
