"""Acceptance for the parameterised OpenAI-compatible provider adapter.

ADR-0030's validation clause requires, per provider: auth construction, success
mapping, refusal and incomplete mapping, retryable-versus-fatal classification,
malformed-output rejection, and proof that no credential reaches a diagnostic.

Everything here is hermetic. No network, no credential, no socket: the pinned
SDK is replaced by an injected fake module, `.env` files live in temporary
directories, and the process environment is never read (an explicit mapping is
always injected).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from math_research.domain.entities import oid
from math_research.phase2 import PHASE2_SCHEMA_VERSION
from math_research.phase2.live_config import (
    LIVE_RUN_CONFIG_SCHEMA_VERSION,
    _FIELDS as LIVE_CONFIG_FIELDS,
)
from math_research.phase2.openai_compatible_gateway import (
    AUTH_API_KEY_HEADER,
    AUTH_BEARER_TOKEN,
    OPENAI_COMPATIBLE_ADAPTER_VERSION,
    OPENAI_COMPATIBLE_SDK_PACKAGE,
    OPENAI_COMPATIBLE_SDK_PINNED_VERSION,
    STRUCTURED_OUTPUT_JSON_OBJECT_ONLY,
    STRUCTURED_OUTPUT_JSON_SCHEMA_STRICT,
    STRUCTURED_OUTPUT_UNSUPPORTED,
    SUPPORTED_PROVIDERS,
    OpenAICompatibleChatGateway,
    ProviderConfigurationError,
    adapter_version,
    azure_openai_config,
    classify_http_failure,
    deepseek_config,
    minimax_config,
    provider_config,
    qwen_dashscope_config,
    resolve_endpoint,
)
from math_research.phase2.pricing import (
    PRICING_SNAPSHOT_SCHEMA_VERSION,
    PRICING_UNITS,
    _FIELDS as PRICING_FIELDS,
)
from math_research.phase2.records import ModelRequest, ModelResultStatus
from math_research.phase2.serialization import canonical_hash, canonical_json

SECRET = "sk-compat-local-only-example123"
VALID_PROPOSER_OUTPUT = canonical_json({
    "schema_version": PHASE2_SCHEMA_VERSION,
    "result_type": "candidate_claim",
    "target_claim_id": "claim.compat.v1",
    "mathematical_payload": {
        "statement": "n is even", "steps": ["assume n=2k"], "witness": None,
    },
    "declared_rationale": "bounded example",
    "referenced_entity_ids": ["claim.compat.v1"],
})


# --- injected fake SDK ------------------------------------------------------


class FakeAPIStatusError(Exception):
    def __init__(self, *, status_code, response=None, body=None, request_id="req_compat_1") -> None:
        super().__init__("provider rejected request")
        self.status_code = status_code
        self.response = response
        self.body = body
        self.request_id = request_id


class FakeAPITimeoutError(Exception):
    pass


class FakeAPIConnectionError(Exception):
    pass


class FakeSDK:
    """Stands in for the pinned `openai` package. Never opens a socket."""

    __version__ = f"{OPENAI_COMPATIBLE_SDK_PINNED_VERSION}-test"
    APIStatusError = FakeAPIStatusError
    APITimeoutError = FakeAPITimeoutError
    APIConnectionError = FakeAPIConnectionError

    def __init__(self) -> None:
        self.constructed: list[tuple[str, dict]] = []
        self.payloads: list[dict] = []
        self._outcome = None
        self.OpenAI = self._make_client("OpenAI")
        self.AzureOpenAI = self._make_client("AzureOpenAI")

    def respond_with(self, outcome) -> "FakeSDK":
        self._outcome = outcome
        return self

    def _make_client(self, label: str):
        sdk = self

        class Completions:
            def create(self, **payload):
                sdk.payloads.append(payload)
                outcome = sdk._outcome
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

        class Chat:
            completions = Completions()

        class Client:
            chat = Chat()

        def factory(**kwargs):
            sdk.constructed.append((label, kwargs))
            return Client()

        return factory


def chat_body(
    *,
    content=VALID_PROPOSER_OUTPUT,
    finish_reason="stop",
    usage=None,
    refusal=None,
    extra=None,
    message=True,
):
    body = {
        "id": "chatcmpl-compat-1",
        "model": "reported-model",
        "choices": [{
            "finish_reason": finish_reason,
            "index": 0,
            **({"message": {"role": "assistant", "content": content, "refusal": refusal}}
               if message else {}),
        }],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
        if usage is None else usage,
    }
    if extra:
        body.update(extra)
    return body


def request(purpose: str = "proposer") -> ModelRequest:
    schema = Path(f"schemas/model-{purpose}-v1.schema.json").read_text(encoding="utf-8")
    return ModelRequest(
        request_id=oid("request.compat.v1"),
        run_id=oid("run.compat.v1"),
        purpose=purpose,
        template_id="template.compat.v1",
        template_version="1.0.0",
        template_hash="sha256:" + "0" * 64,
        template_text="bounded developer instruction",
        serialized_context='{"bounded":true}',
        response_schema=schema,
        referenced_entity_ids=(oid("claim.compat.v1"),),
        timeout_milliseconds=2_000,
        max_output_tokens=256,
    )


def gateway(config, sdk, *, environment=None, absent_env=True):
    """Build a gateway whose credential loader can never see a real `.env`."""

    return OpenAICompatibleChatGateway(
        config,
        sdk_module=sdk,
        environment=dict(environment or {}),
        env_path=Path(tempfile.gettempdir()) / "adaivy-nonexistent-env-file",
        schema_dir=Path("schemas"),
    )


BEARER_ENV = {
    "MINIMAX_API_KEY": SECRET,
    "DASHSCOPE_API_KEY": SECRET,
    "DEEPSEEK_API_KEY": SECRET,
}
AZURE_ENV = {
    "AZURE_OPENAI_API_KEY": SECRET,
    "AZURE_OPENAI_ENDPOINT": "https://example-resource.openai.azure.com/",
    "AZURE_OPENAI_DEPLOYMENT": "adaivy-deployment",
    "AZURE_OPENAI_API_VERSION": "2026-01-01-preview",
}


# --- auth and endpoint construction ----------------------------------------


class AuthAndEndpointTests(unittest.TestCase):
    def test_bearer_providers_share_one_shape_with_distinct_identity(self) -> None:
        cases = (
            (minimax_config(model_identifier="MiniMax-Text-01"), "minimax", "MINIMAX_API_KEY"),
            (qwen_dashscope_config(model_identifier="qwen-plus"), "qwen_dashscope", "DASHSCOPE_API_KEY"),
            (deepseek_config(model_identifier="deepseek-chat"), "deepseek", "DEEPSEEK_API_KEY"),
        )
        for config, provider, key_env in cases:
            with self.subTest(provider=provider):
                self.assertEqual(config.provider, provider)
                self.assertEqual(config.api_key_env, key_env)
                self.assertEqual(config.auth_style, AUTH_BEARER_TOKEN)
                self.assertEqual(config.sdk_client_class, "OpenAI")
                endpoint = resolve_endpoint(config, dict(BEARER_ENV))
                self.assertEqual(endpoint.auth_header_name, "authorization")
                self.assertEqual(endpoint.auth_header_scheme, "Bearer")
                self.assertIsNone(endpoint.deployment)
                self.assertTrue(endpoint.request_url.startswith("https://"))
                self.assertTrue(endpoint.request_url.endswith("/chat/completions"))

    def test_qwen_uses_the_dashscope_openai_compatible_base_path(self) -> None:
        endpoint = resolve_endpoint(
            qwen_dashscope_config(model_identifier="qwen-plus"), dict(BEARER_ENV),
        )
        self.assertIn("/compatible-mode/v1", endpoint.request_url)

    def test_minimax_group_id_is_optional_and_omitted_when_unset(self) -> None:
        config = minimax_config(model_identifier="MiniMax-Text-01")
        without = resolve_endpoint(config, {"MINIMAX_API_KEY": SECRET})
        self.assertEqual((), without.query_parameters)
        with_group = resolve_endpoint(
            config, {"MINIMAX_API_KEY": SECRET, "MINIMAX_GROUP_ID": "group-42"},
        )
        self.assertEqual((("GroupId", "group-42"),), with_group.query_parameters)
        blank = resolve_endpoint(
            config, {"MINIMAX_API_KEY": SECRET, "MINIMAX_GROUP_ID": "   "},
        )
        self.assertEqual((), blank.query_parameters)

    def test_azure_uses_api_key_header_deployment_url_and_api_version(self) -> None:
        config = azure_openai_config(model_identifier="gpt-5-mini")
        self.assertEqual(config.auth_style, AUTH_API_KEY_HEADER)
        self.assertEqual(config.sdk_client_class, "AzureOpenAI")
        endpoint = resolve_endpoint(config, dict(AZURE_ENV))
        self.assertEqual(endpoint.auth_header_name, "api-key")
        self.assertIsNone(
            endpoint.auth_header_scheme, "Azure must never receive a Bearer token",
        )
        self.assertEqual(endpoint.deployment, "adaivy-deployment")
        self.assertEqual(
            endpoint.request_url,
            "https://example-resource.openai.azure.com"
            "/openai/deployments/adaivy-deployment/chat/completions",
        )
        self.assertEqual(
            (("api-version", "2026-01-01-preview"),), endpoint.query_parameters,
        )

    def test_azure_fails_closed_on_each_missing_required_setting(self) -> None:
        config = azure_openai_config(model_identifier="gpt-5-mini")
        for variable in (
            "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION",
        ):
            with self.subTest(variable=variable):
                environment = dict(AZURE_ENV)
                environment[variable] = ""
                with self.assertRaises(ProviderConfigurationError) as caught:
                    resolve_endpoint(config, environment)
                self.assertIn(variable, str(caught.exception))
                self.assertNotIn(SECRET, str(caught.exception))

    def test_non_https_and_path_traversing_deployment_are_rejected(self) -> None:
        config = azure_openai_config(model_identifier="gpt-5-mini")
        insecure = dict(AZURE_ENV, AZURE_OPENAI_ENDPOINT="http://example.openai.azure.com")
        with self.assertRaisesRegex(ProviderConfigurationError, "https"):
            resolve_endpoint(config, insecure)
        traversing = dict(AZURE_ENV, AZURE_OPENAI_DEPLOYMENT="a/../b")
        with self.assertRaisesRegex(ProviderConfigurationError, "single path segment"):
            resolve_endpoint(config, traversing)

    def test_client_kwargs_differ_by_auth_style(self) -> None:
        sdk = FakeSDK().respond_with(chat_body())
        gateway(
            deepseek_config(model_identifier="deepseek-chat"), sdk, environment=BEARER_ENV,
        ).complete(request())
        label, kwargs = sdk.constructed[-1]
        self.assertEqual("OpenAI", label)
        self.assertEqual(SECRET, kwargs["api_key"])
        self.assertEqual("https://api.deepseek.com/v1", kwargs["base_url"])
        self.assertEqual(0, kwargs["max_retries"])
        self.assertNotIn("azure_endpoint", kwargs)

        azure_sdk = FakeSDK().respond_with(chat_body())
        gateway(
            azure_openai_config(model_identifier="gpt-5-mini"), azure_sdk, environment=AZURE_ENV,
        ).complete(request())
        label, kwargs = azure_sdk.constructed[-1]
        self.assertEqual("AzureOpenAI", label)
        self.assertEqual("2026-01-01-preview", kwargs["api_version"])
        self.assertEqual("adaivy-deployment", kwargs["azure_deployment"])
        self.assertEqual(
            "https://example-resource.openai.azure.com", kwargs["azure_endpoint"],
        )
        self.assertNotIn("base_url", kwargs)

    def test_unknown_provider_and_missing_sdk_client_fail_closed(self) -> None:
        with self.assertRaisesRegex(ProviderConfigurationError, "unsupported provider"):
            provider_config("bedrock", model_identifier="anything")
        self.assertEqual(
            set(SUPPORTED_PROVIDERS),
            {provider_config(name, model_identifier="m").provider for name in SUPPORTED_PROVIDERS},
        )

        class SDKWithoutAzure(FakeSDK):
            pass

        sdk = SDKWithoutAzure().respond_with(chat_body())
        del sdk.AzureOpenAI
        with self.assertRaisesRegex(ProviderConfigurationError, "AzureOpenAI"):
            gateway(
                azure_openai_config(model_identifier="gpt-5-mini"), sdk, environment=AZURE_ENV,
            ).complete(request())


# --- response mapping -------------------------------------------------------


class ResponseMappingTests(unittest.TestCase):
    def test_strict_schema_success_carries_provider_identity_and_usage(self) -> None:
        sdk = FakeSDK().respond_with(chat_body())
        result = gateway(
            azure_openai_config(model_identifier="gpt-5-mini"), sdk, environment=AZURE_ENV,
        ).complete(request())
        self.assertEqual(ModelResultStatus.SUCCEEDED, result.status)
        self.assertEqual("azure_openai", result.provider)
        self.assertEqual("reported-model", result.model_identifier)
        self.assertEqual(VALID_PROPOSER_OUTPUT, result.structured_output)
        self.assertEqual("chatcmpl-compat-1", result.provider_request_id)
        self.assertEqual("none", result.retry_classification)
        self.assertEqual("api_reported", result.usage.usage_source)
        self.assertEqual(18, result.usage.total_tokens)
        self.assertIsNotNone(result.provider_schema_hash)
        payload = sdk.payloads[-1]
        self.assertEqual("json_schema", payload["response_format"]["type"])
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        self.assertEqual(256, payload["max_completion_tokens"])
        self.assertNotIn("max_tokens", payload)

    def test_compat_providers_use_max_tokens_and_json_object_format(self) -> None:
        sdk = FakeSDK().respond_with(chat_body())
        result = gateway(
            minimax_config(model_identifier="MiniMax-Text-01"), sdk, environment=BEARER_ENV,
        ).complete(request())
        self.assertEqual(ModelResultStatus.SUCCEEDED, result.status)
        self.assertEqual("minimax", result.provider)
        payload = sdk.payloads[-1]
        self.assertEqual({"type": "json_object"}, payload["response_format"])
        self.assertEqual(256, payload["max_tokens"])
        self.assertFalse(payload["stream"])

    def test_json_object_only_output_is_validated_not_trusted(self) -> None:
        config = deepseek_config(model_identifier="deepseek-chat")
        for content, expected in (
            (VALID_PROPOSER_OUTPUT, ModelResultStatus.SUCCEEDED),
            ('{"result_type":"candidate_claim"}', ModelResultStatus.MALFORMED),
            ("not json at all", ModelResultStatus.MALFORMED),
            ('["an","array"]', ModelResultStatus.MALFORMED),
            (
                canonical_json({
                    "schema_version": PHASE2_SCHEMA_VERSION,
                    "result_type": "candidate_claim",
                    "target_claim_id": "claim.compat.v1",
                    "mathematical_payload": {
                        "statement": "s", "steps": [], "witness": None,
                    },
                    "declared_rationale": "r",
                    "referenced_entity_ids": [],
                    "warrant": "granted",
                }),
                ModelResultStatus.MALFORMED,
            ),
        ):
            with self.subTest(content=content[:32]):
                sdk = FakeSDK().respond_with(chat_body(content=content))
                result = gateway(config, sdk, environment=BEARER_ENV).complete(request())
                self.assertEqual(expected, result.status)
                if expected is ModelResultStatus.MALFORMED:
                    self.assertEqual(
                        "fatal:strict_schema_not_enforced_and_output_invalid",
                        result.retry_classification,
                    )
                    self.assertIsNone(result.structured_output)

    def test_strict_mode_rejects_non_object_output_without_fabricating_success(self) -> None:
        sdk = FakeSDK().respond_with(chat_body(content="definitely not json"))
        result = gateway(
            azure_openai_config(model_identifier="gpt-5-mini"), sdk, environment=AZURE_ENV,
        ).complete(request())
        self.assertEqual(ModelResultStatus.MALFORMED, result.status)
        self.assertEqual("fatal:strict_schema_violated", result.retry_classification)
        self.assertIsNone(result.structured_output)

    def test_unsupported_structured_output_never_reaches_a_credential(self) -> None:
        config = deepseek_config(model_identifier="deepseek-chat")
        unsupported = type(config)(
            **{
                **{f: getattr(config, f) for f in config.__slots__},
                "structured_output_mode": STRUCTURED_OUTPUT_UNSUPPORTED,
            }
        )

        def exploding_loader(*args, **kwargs):
            raise AssertionError("credentials must not be read when fail-closed")

        adapter = OpenAICompatibleChatGateway(
            unsupported,
            sdk_module=FakeSDK(),
            environment={},
            credential_loader=exploding_loader,
            client_factory=lambda **_: (_ for _ in ()).throw(
                AssertionError("no client may be constructed"),
            ),
            schema_dir=Path("schemas"),
        )
        result = adapter.complete(request())
        self.assertEqual(ModelResultStatus.MALFORMED, result.status)
        self.assertEqual("fatal:strict_schema_unsupported", result.retry_classification)

    def test_refusal_content_filter_and_length_map_distinctly(self) -> None:
        config = azure_openai_config(model_identifier="gpt-5-mini")
        sdk = FakeSDK().respond_with(chat_body(content=None, refusal="I cannot help with that"))
        refused = gateway(config, sdk, environment=AZURE_ENV).complete(request())
        self.assertEqual(ModelResultStatus.REFUSED, refused.status)
        self.assertEqual("I cannot help with that", refused.refusal)
        self.assertEqual("not_retryable:refusal", refused.retry_classification)

        sdk = FakeSDK().respond_with(chat_body(content=None, finish_reason="content_filter"))
        filtered = gateway(config, sdk, environment=AZURE_ENV).complete(request())
        self.assertEqual(ModelResultStatus.REFUSED, filtered.status)
        self.assertEqual("provider content filter", filtered.refusal)

        for reason in ("length", "max_tokens"):
            with self.subTest(reason=reason):
                sdk = FakeSDK().respond_with(chat_body(finish_reason=reason))
                incomplete = gateway(config, sdk, environment=AZURE_ENV).complete(request())
                self.assertEqual(ModelResultStatus.INCOMPLETE, incomplete.status)
                self.assertEqual(f"finish_reason:{reason}", incomplete.incomplete_reason)
                self.assertEqual(
                    "not_retryable:incomplete_response", incomplete.retry_classification,
                )

    def test_absent_or_oddly_shaped_success_bodies_are_malformed_not_crashes(self) -> None:
        config = deepseek_config(model_identifier="deepseek-chat")
        cases = (
            ({"id": "x", "model": "m"}, "fatal:missing_choices"),
            ({"choices": []}, "fatal:missing_choices"),
            ({"choices": ["not-a-dict"]}, "fatal:missing_choices"),
            (chat_body(message=False), "fatal:missing_output_finish_reason_or_usage"),
            (chat_body(finish_reason=None), "fatal:missing_output_finish_reason_or_usage"),
            (chat_body(usage={}), "fatal:missing_output_finish_reason_or_usage"),
            (chat_body(usage="unexpected"), "fatal:missing_output_finish_reason_or_usage"),
            (chat_body(finish_reason="tool_calls"), "fatal:missing_output_finish_reason_or_usage"),
        )
        for body, classification in cases:
            with self.subTest(classification=classification, body=str(body)[:40]):
                sdk = FakeSDK().respond_with(body)
                result = gateway(config, sdk, environment=BEARER_ENV).complete(request())
                self.assertEqual(ModelResultStatus.MALFORMED, result.status)
                self.assertEqual(classification, result.retry_classification)

    def test_partial_usage_is_labelled_rather_than_reported_as_stated(self) -> None:
        sdk = FakeSDK().respond_with(
            chat_body(usage={"input_tokens": 5, "output_tokens": 3}),
        )
        result = gateway(
            deepseek_config(model_identifier="deepseek-chat"), sdk, environment=BEARER_ENV,
        ).complete(request())
        self.assertEqual(ModelResultStatus.SUCCEEDED, result.status)
        self.assertEqual("api_reported_derived_total", result.usage.usage_source)
        self.assertEqual(8, result.usage.total_tokens)

    def test_undecodable_provider_response_is_retryable_not_a_crash(self) -> None:
        sdk = FakeSDK().respond_with(object())
        result = gateway(
            deepseek_config(model_identifier="deepseek-chat"), sdk, environment=BEARER_ENV,
        ).complete(request())
        self.assertEqual(ModelResultStatus.FAILED, result.status)
        self.assertEqual("retryable:response_decode", result.retry_classification)


class InlineProviderErrorTests(unittest.TestCase):
    def test_error_inside_an_http_200_body_is_a_failure_not_a_success(self) -> None:
        sdk = FakeSDK().respond_with({
            "error": {"message": "quota exhausted", "code": "insufficient_quota"},
        })
        result = gateway(
            deepseek_config(model_identifier="deepseek-chat"), sdk, environment=BEARER_ENV,
        ).complete(request())
        self.assertEqual(ModelResultStatus.FAILED, result.status)
        self.assertEqual("fatal:http_200", result.retry_classification)

    def test_minimax_base_resp_envelope_is_honoured_only_where_configured(self) -> None:
        body = chat_body(extra={"base_resp": {"status_code": 1002, "status_msg": "rate limit"}})
        sdk = FakeSDK().respond_with(body)
        minimax = gateway(
            minimax_config(model_identifier="MiniMax-Text-01"), sdk, environment=BEARER_ENV,
        ).complete(request())
        self.assertEqual(ModelResultStatus.FAILED, minimax.status)

        sdk = FakeSDK().respond_with(body)
        deepseek = gateway(
            deepseek_config(model_identifier="deepseek-chat"), sdk, environment=BEARER_ENV,
        ).complete(request())
        self.assertEqual(
            ModelResultStatus.SUCCEEDED, deepseek.status,
            "no envelope behaviour may be invented for a provider that does not use it",
        )

    def test_zero_status_envelope_is_success(self) -> None:
        sdk = FakeSDK().respond_with(
            chat_body(extra={"base_resp": {"status_code": 0, "status_msg": ""}}),
        )
        result = gateway(
            minimax_config(model_identifier="MiniMax-Text-01"), sdk, environment=BEARER_ENV,
        ).complete(request())
        self.assertEqual(ModelResultStatus.SUCCEEDED, result.status)


# --- error classification ---------------------------------------------------


class ErrorClassificationTests(unittest.TestCase):
    def test_status_rule_mirrors_the_openai_adapter(self) -> None:
        for status, expected in (
            (400, "fatal:http_400"), (401, "fatal:http_401"), (404, "fatal:http_404"),
            (408, "retryable:http_408"), (409, "retryable:http_409"),
            (429, "retryable:http_429"), (500, "retryable:http_500"),
            (503, "retryable:http_503"),
        ):
            with self.subTest(status=status):
                self.assertEqual(expected, classify_http_failure(status))

    def test_bounded_provider_codes_override_the_status_verdict(self) -> None:
        self.assertEqual(
            "retryable:http_400",
            classify_http_failure(400, provider_error_code="Throttling.RateQuota"),
        )
        self.assertEqual(
            "retryable:http_400",
            classify_http_failure(400, provider_error_type="rate_limit_exceeded"),
        )
        self.assertEqual(
            "fatal:http_500", classify_http_failure(500, provider_error_code="invalid_api_key"),
        )
        self.assertEqual(
            "fatal:http_403", classify_http_failure(403, provider_error_code="unrecognised_code"),
        )

    def test_unclassifiable_status_is_never_retried_blindly(self) -> None:
        self.assertEqual("fatal:http_unknown", classify_http_failure(None))

    def test_http_failure_populates_a_full_diagnostic(self) -> None:
        body = {"error": {
            "message": "bad request", "type": "invalid_request_error",
            "code": "invalid_json_schema", "param": "response_format",
        }}
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")

        class Response:
            headers = {"Content-Type": "application/json; charset=utf-8"}

            def content(self):
                return raw

        error = FakeAPIStatusError(status_code=400, response=Response(), body=body)
        sdk = FakeSDK().respond_with(error)
        result = gateway(
            qwen_dashscope_config(model_identifier="qwen-plus"), sdk, environment=BEARER_ENV,
        ).complete(request())
        self.assertEqual(ModelResultStatus.FAILED, result.status)
        self.assertEqual("fatal:http_400", result.retry_classification)
        diagnostic = result.provider_failure
        assert diagnostic is not None
        self.assertEqual(400, diagnostic.http_status_code)
        self.assertEqual("FakeAPIStatusError", diagnostic.sdk_exception_class)
        self.assertEqual("req_compat_1", diagnostic.provider_request_id)
        self.assertEqual("invalid_request_error", diagnostic.provider_error_type)
        self.assertEqual("invalid_json_schema", diagnostic.provider_error_code)
        self.assertEqual("response_format", diagnostic.provider_error_param)
        self.assertEqual("bad request", diagnostic.provider_error_message)
        self.assertEqual("application/json; charset=utf-8", diagnostic.response_content_type)
        self.assertEqual(len(raw), diagnostic.response_body_byte_length)
        self.assertEqual(
            adapter_version("qwen_dashscope"), diagnostic.adapter_version,
        )
        self.assertIn("qwen_dashscope", diagnostic.adapter_version)
        self.assertIn(OPENAI_COMPATIBLE_ADAPTER_VERSION, diagnostic.adapter_version)
        self.assertTrue(diagnostic.endpoint.endswith("/chat/completions"))
        self.assertTrue(diagnostic.response_body_sha256.startswith("sha256:"))

    def test_odd_or_absent_error_bodies_do_not_crash_the_adapter(self) -> None:
        config = deepseek_config(model_identifier="deepseek-chat")
        bodies = (
            None,
            "a bare string body",
            ["unexpected", "array"],
            {"detail": "no error key at all"},
            {"error": "flat string error"},
            {"base_resp": {"status_code": 1004, "status_msg": "auth failed"}},
        )
        for body in bodies:
            with self.subTest(body=str(body)[:32]):
                error = FakeAPIStatusError(status_code=418, body=body, response=None)
                sdk = FakeSDK().respond_with(error)
                result = gateway(config, sdk, environment=BEARER_ENV).complete(request())
                self.assertEqual(ModelResultStatus.FAILED, result.status)
                self.assertEqual("fatal:http_418", result.retry_classification)
                assert result.provider_failure is not None
                self.assertEqual(418, result.provider_failure.http_status_code)

    def test_non_integer_status_yields_a_zero_coded_fatal_diagnostic(self) -> None:
        error = FakeAPIStatusError(status_code="not-an-int", body={"error": {}}, response=None)
        sdk = FakeSDK().respond_with(error)
        result = gateway(
            deepseek_config(model_identifier="deepseek-chat"), sdk, environment=BEARER_ENV,
        ).complete(request())
        self.assertEqual("fatal:http_unknown", result.retry_classification)
        assert result.provider_failure is not None
        self.assertEqual(0, result.provider_failure.http_status_code)

    def test_timeout_and_transport_failures_are_retryable(self) -> None:
        config = minimax_config(model_identifier="MiniMax-Text-01")
        sdk = FakeSDK().respond_with(FakeAPITimeoutError())
        timed_out = gateway(config, sdk, environment=BEARER_ENV).complete(request())
        self.assertEqual(ModelResultStatus.TIMED_OUT, timed_out.status)
        self.assertEqual("retryable:timeout", timed_out.retry_classification)

        sdk = FakeSDK().respond_with(FakeAPIConnectionError())
        transport = gateway(config, sdk, environment=BEARER_ENV).complete(request())
        self.assertEqual(ModelResultStatus.FAILED, transport.status)
        self.assertEqual("retryable:transport", transport.retry_classification)


# --- secret handling --------------------------------------------------------


class SecretHandlingTests(unittest.TestCase):
    def test_a_credential_never_reaches_a_diagnostic_or_a_record(self) -> None:
        body = {
            "error": {
                "message": f"rejected; Authorization: Bearer {SECRET}",
                "type": "invalid_request_error",
                "code": "invalid_api_key",
                "authorization": f"Bearer {SECRET}",
                "api_key": SECRET,
            },
            "echo": SECRET,
        }
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")

        class Response:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {SECRET}",
                "Set-Cookie": f"session={SECRET}",
            }

            def content(self):
                return raw

        error = FakeAPIStatusError(status_code=401, response=Response(), body=body)
        sdk = FakeSDK().respond_with(error)
        result = gateway(
            deepseek_config(model_identifier="deepseek-chat"), sdk, environment=BEARER_ENV,
        ).complete(request())
        diagnostic = result.provider_failure
        assert diagnostic is not None
        rendered = canonical_json(result)
        self.assertNotIn(SECRET, rendered)
        self.assertNotIn(SECRET, canonical_json(diagnostic))
        self.assertNotIn(SECRET, diagnostic.response_body_preview)
        self.assertNotIn(SECRET, str(diagnostic.provider_error_message))
        self.assertIn("[REDACTED]", diagnostic.response_body_preview)
        # The unredacted body hash and length are retained for forensics.
        self.assertEqual(len(raw), diagnostic.response_body_byte_length)

    def test_a_credential_embedded_in_a_base_url_is_redacted_from_the_endpoint(self) -> None:
        config = minimax_config(
            model_identifier="MiniMax-Text-01",
            base_url=f"https://api.minimax.io/v1?token={SECRET}",
        )
        error = FakeAPIStatusError(status_code=400, body=None, response=None)
        sdk = FakeSDK().respond_with(error)
        result = gateway(config, sdk, environment=BEARER_ENV).complete(request())
        assert result.provider_failure is not None
        self.assertNotIn(SECRET, result.provider_failure.endpoint)

    def test_missing_credential_names_the_variable_and_no_value(self) -> None:
        adapter = gateway(
            deepseek_config(model_identifier="deepseek-chat"),
            FakeSDK().respond_with(chat_body()),
            environment={"DEEPSEEK_API_KEY": "   "},
        )
        with self.assertRaises(ProviderConfigurationError) as caught:
            adapter.complete(request())
        self.assertEqual("DEEPSEEK_API_KEY is not configured", str(caught.exception))


class CredentialSourceTests(unittest.TestCase):
    def test_keys_are_resolved_through_the_provider_credential_loader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env_path = Path(temporary) / ".env"
            env_path.write_text(
                f"DEEPSEEK_API_KEY={SECRET}\nMINIMAX_API_KEY=\n", encoding="utf-8",
            )
            env_path.chmod(0o600)
            environment: dict[str, str] = {}
            sdk = FakeSDK().respond_with(chat_body())
            adapter = OpenAICompatibleChatGateway(
                deepseek_config(model_identifier="deepseek-chat"),
                sdk_module=sdk,
                environment=environment,
                env_path=env_path,
                schema_dir=Path("schemas"),
            )
            with patch.dict(os.environ, {}, clear=True):
                result = adapter.complete(request())
                self.assertNotIn(
                    "DEEPSEEK_API_KEY", os.environ,
                    "an injected environment must never write to the process environment",
                )
            self.assertEqual(ModelResultStatus.SUCCEEDED, result.status)
            self.assertEqual(SECRET, sdk.constructed[-1][1]["api_key"])
            loaded = adapter.credential_load_result
            assert loaded is not None
            self.assertEqual(("DEEPSEEK_API_KEY",), loaded.from_env_file)
            self.assertEqual(("MINIMAX_API_KEY",), loaded.blank_in_env_file)
            self.assertNotIn(SECRET, repr(loaded))

    def test_the_env_file_is_read_at_most_once_per_gateway(self) -> None:
        calls: list[object] = []

        def counting_loader(path, *, environment):
            calls.append(path)
            environment["DEEPSEEK_API_KEY"] = SECRET
            return None

        adapter = OpenAICompatibleChatGateway(
            deepseek_config(model_identifier="deepseek-chat"),
            sdk_module=FakeSDK().respond_with(chat_body()),
            environment={},
            credential_loader=counting_loader,
            schema_dir=Path("schemas"),
        )
        adapter.complete(request())
        adapter.complete(request())
        self.assertEqual(1, len(calls))


# --- import-time and offline safety ----------------------------------------


class OfflineSafetyTests(unittest.TestCase):
    def test_prepare_touches_neither_the_sdk_nor_a_credential(self) -> None:
        def exploding_loader(*args, **kwargs):
            raise AssertionError("prepare must not read a credential")

        adapter = OpenAICompatibleChatGateway(
            deepseek_config(model_identifier="deepseek-chat"),
            credential_loader=exploding_loader,
            environment={},
            schema_dir=Path("schemas"),
        )
        prepared = adapter.prepare(request())
        self.assertTrue(prepared.provider_schema_hash.startswith("sha256:"))
        self.assertEqual("openai", prepared.provider)

    def test_module_declares_the_pinned_sdk_and_reuses_one_gated_boundary(self) -> None:
        source = Path(
            "src/math_research/phase2/openai_compatible_gateway.py",
        ).read_text(encoding="utf-8")
        self.assertEqual("openai", OPENAI_COMPATIBLE_SDK_PACKAGE)
        self.assertEqual("3.3.0", OPENAI_COMPATIBLE_SDK_PINNED_VERSION)
        self.assertIn(
            OPENAI_COMPATIBLE_SDK_PINNED_VERSION,
            Path("requirements-phase2-provider.txt").read_text(encoding="utf-8"),
        )
        self.assertNotIn(
            'import_module("openai")', source,
            "the lazy load must be delegated to model_gateway's single declared "
            "gated import so GATED_DYNAMIC_IMPORTS keeps exactly two entries",
        )

    def test_structured_output_modes_are_explicit_per_provider(self) -> None:
        self.assertEqual(
            STRUCTURED_OUTPUT_JSON_SCHEMA_STRICT,
            azure_openai_config(model_identifier="m").structured_output_mode,
        )
        for factory in (minimax_config, qwen_dashscope_config, deepseek_config):
            with self.subTest(factory=factory.__name__):
                self.assertEqual(
                    STRUCTURED_OUTPUT_JSON_OBJECT_ONLY,
                    factory(model_identifier="m").structured_output_mode,
                )


# --- versioned non-secret configuration ------------------------------------


PROVIDER_FILES = (
    ("minimax", "phase2-live-minimax-v1.json", "minimax-text-01-pricing-unconfirmed-2026-08-21.json"),
    ("qwen_dashscope", "phase2-live-qwen-dashscope-v1.json", "qwen-plus-pricing-unconfirmed-2026-08-21.json"),
    ("deepseek", "phase2-live-deepseek-v1.json", "deepseek-chat-pricing-unconfirmed-2026-08-21.json"),
    ("azure_openai", "phase2-live-azure-openai-v1.json", "azure-openai-gpt5-mini-pricing-unconfirmed-2026-08-21.json"),
)


class ProviderConfigurationFileTests(unittest.TestCase):
    """The shipped JSON is non-secret, content-hashed, and byte-deterministic.

    These assertions are provider-agnostic on purpose: they use the same field
    sets and the same hashing rule as `pricing.py` and `live_config.py`, so they
    stay correct once those two modules' `provider` allowlists widen past
    "openai" (see the report accompanying this slice).
    """

    def _payload(self, name: str) -> dict:
        path = Path("config") / name
        raw = path.read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("\n"))
        payload = json.loads(raw)
        self.assertEqual(
            canonical_json(payload) + "\n", raw, "shipped bytes must be canonical",
        )
        return payload

    def test_every_provider_ships_a_config_and_a_pricing_snapshot(self) -> None:
        self.assertEqual(
            sorted(SUPPORTED_PROVIDERS), sorted(name for name, _, _ in PROVIDER_FILES),
        )
        for provider, config_name, pricing_name in PROVIDER_FILES:
            with self.subTest(provider=provider):
                config = self._payload(config_name)
                pricing = self._payload(pricing_name)
                self.assertEqual(LIVE_CONFIG_FIELDS, set(config))
                self.assertEqual(PRICING_FIELDS, set(pricing))
                self.assertEqual(LIVE_RUN_CONFIG_SCHEMA_VERSION, config["schema_version"])
                self.assertEqual(PRICING_SNAPSHOT_SCHEMA_VERSION, pricing["schema_version"])
                self.assertEqual(provider, config["provider"])
                self.assertEqual(provider, pricing["provider"])
                self.assertEqual(pricing["snapshot_id"], config["pricing_snapshot_id"])
                self.assertEqual(
                    pricing["model_identifier"], config["model_identifier"],
                )
                self.assertEqual("USD", pricing["currency"])
                self.assertEqual(PRICING_UNITS, pricing["units"])
                for payload in (config, pricing):
                    unhashed = dict(payload)
                    unhashed["content_hash"] = None
                    self.assertEqual(canonical_hash(unhashed), payload["content_hash"])

    def test_placeholder_rates_are_labelled_unconfirmed_with_a_source(self) -> None:
        for _, _, pricing_name in PROVIDER_FILES:
            with self.subTest(pricing_name=pricing_name):
                pricing = self._payload(pricing_name)
                self.assertIn("UNCONFIRMED PLACEHOLDER", pricing["source"])
                self.assertIn("https://", pricing["source"])
                self.assertIn("unconfirmed", pricing["snapshot_id"])
                self.assertGreater(pricing["input_microusd_per_million_tokens"], 0)
                self.assertGreater(pricing["output_microusd_per_million_tokens"], 0)

    def test_shipped_model_identifiers_are_constructible(self) -> None:
        for provider, config_name, _ in PROVIDER_FILES:
            with self.subTest(provider=provider):
                config = self._payload(config_name)
                built = provider_config(
                    provider, model_identifier=config["model_identifier"],
                )
                self.assertEqual(provider, built.provider)
                self.assertEqual(config["model_identifier"], built.model_identifier)


if __name__ == "__main__":
    unittest.main()
