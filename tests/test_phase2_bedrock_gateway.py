"""Acceptance suite for the opt-in AWS Bedrock ``InvokeModel`` gateway.

Hermetic by construction: every transport is a recorded fake, every credential
is synthetic, the signing clock is frozen, and no test opens a socket, reads the
process environment, or touches the repository ``.env``.

The suite encodes ADR-0030's Bedrock clauses as executable assertions:
per-family mapping keyed by model-id prefix, an explicit unsupported-family
failure for everything else, a required region, retryable-versus-fatal AWS error
classification, unconfirmed placeholder pricing, no credential or signing
material in any diagnostic, and ``MALFORMED`` rather than a fabricated success
when output does not validate against the requested canonical schema.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
import unittest
from datetime import datetime, timezone
from pathlib import Path

from math_research.domain.entities import OpaqueId, oid
from math_research.phase2 import bedrock_gateway
from math_research.phase2.aws_sigv4 import SIGV4_IMPLEMENTATION_VERSION
from math_research.phase2.bedrock_gateway import (
    BEDROCK_ADAPTER_VERSION,
    BEDROCK_PRICING_SOURCE,
    BEDROCK_PROVIDER,
    BEDROCK_SIGNING_SERVICE,
    BedrockConfigurationError,
    BedrockCredentialError,
    BedrockHttpRequest,
    BedrockHttpResponse,
    BedrockInvokeGateway,
    BedrockProviderConfig,
    BedrockTransportFailure,
    BedrockTransportTimeout,
    FamilyPrompt,
    MODEL_FAMILIES,
    SCHEMA_INSTRUCTION,
    UnsupportedModelFamilyError,
    classify_bedrock_error,
    extract_error_code,
    resolve_model_family,
    supported_family_ids,
)
from math_research.phase2.live_config import _FIELDS as LIVE_CONFIG_FIELDS
from math_research.phase2.live_config import load_live_run_configuration
from math_research.phase2.pricing import _FIELDS as PRICING_FIELDS
from math_research.phase2.pricing import (
    PRICING_UNITS,
    estimate_cost_microusd,
    load_pricing_snapshot,
)
from math_research.phase2.records import (
    ModelRequest,
    ModelResultStatus,
    PricingSnapshot,
)
from math_research.phase2.serialization import canonical_hash, canonical_json


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
LIVE_CONFIG_PATH = CONFIG_DIR / "phase2-live-bedrock-v1.json"
PRICING_PATH = (
    CONFIG_DIR / "bedrock-anthropic-claude-opus-5-pricing-unconfirmed-2026-08-21.json"
)

# Synthetic credentials. AWS's published example values, never real.
ACCESS_KEY_ID = "AKIDEXAMPLE"
SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
SESSION_TOKEN = "FQoDYXdzEEXAMPLESESSIONTOKEN=="
FROZEN_MOMENT = datetime(2026, 8, 21, 9, 30, 0, tzinfo=timezone.utc)
ABSENT_ENV_FILE = Path("/nonexistent-adaivy-test/.env")

RESPONSE_SCHEMA = json.dumps(
    {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "result_type", "target_claim_id"],
        "properties": {
            "schema_version": {"const": "2.0.0"},
            "result_type": {"enum": ["candidate_claim", "failure"]},
            "target_claim_id": {"type": "string", "minLength": 1},
        },
    },
    sort_keys=True,
)
VALID_OUTPUT = json.dumps(
    {
        "schema_version": "2.0.0",
        "result_type": "candidate_claim",
        "target_claim_id": "claim.alpha",
    },
    sort_keys=True,
)


def environment(**overrides: str) -> dict[str, str]:
    values = {
        "AWS_ACCESS_KEY_ID": ACCESS_KEY_ID,
        "AWS_SECRET_ACCESS_KEY": SECRET_ACCESS_KEY,
        "AWS_REGION": "us-east-1",
    }
    values.update(overrides)
    return {key: value for key, value in values.items() if value}


def model_request(**overrides: object) -> ModelRequest:
    values: dict[str, object] = {
        "request_id": oid("req.bedrock.1"),
        "run_id": oid("run.bedrock.1"),
        "purpose": "proposer",
        "template_id": "template.proposer",
        "template_version": "1.0.0",
        "template_hash": "sha256:" + "0" * 64,
        "template_text": "Propose a candidate claim.",
        "serialized_context": '{"context":"alpha"}',
        "response_schema": RESPONSE_SCHEMA,
        "referenced_entity_ids": (oid("entity.alpha"),),
        "timeout_milliseconds": 120_000,
        "max_output_tokens": 4_096,
    }
    values.update(overrides)
    return ModelRequest(**values)  # type: ignore[arg-type]


class RecordingTransport:
    """A fake transport. Records what would have been sent; opens no socket."""

    def __init__(self, *responses: BedrockHttpResponse | Exception) -> None:
        self._queue = list(responses)
        self.requests: list[BedrockHttpRequest] = []

    def send(self, request: BedrockHttpRequest) -> BedrockHttpResponse:
        self.requests.append(request)
        if not self._queue:
            raise AssertionError("transport called more often than scripted")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def json_response(
    payload: object,
    *,
    status_code: int = 200,
    headers: tuple[tuple[str, str], ...] = (),
) -> BedrockHttpResponse:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    base = (
        ("content-type", "application/json"),
        ("x-amzn-requestid", "req-abc-123"),
    )
    return BedrockHttpResponse(
        status_code=status_code, headers=base + headers, body=body,
    )


def anthropic_success(text: str = VALID_OUTPUT) -> BedrockHttpResponse:
    return json_response(
        {
            "id": "msg_01",
            "type": "message",
            "role": "assistant",
            "model": "anthropic.claude-opus-5",
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 41, "output_tokens": 17},
        }
    )


def gateway(
    model_identifier: str = "anthropic.claude-opus-5",
    *,
    transport: object | None = None,
    env: dict[str, str] | None = None,
    region: str | None = None,
) -> BedrockInvokeGateway:
    return BedrockInvokeGateway(
        BedrockProviderConfig(model_identifier=model_identifier, region=region),
        transport=transport,  # type: ignore[arg-type]
        environment=environment() if env is None else env,
        env_file_path=ABSENT_ENV_FILE,
        clock=lambda: FROZEN_MOMENT,
    )


# --------------------------------------------------------------------------
# Family mapping
# --------------------------------------------------------------------------


class FamilyResolutionTests(unittest.TestCase):
    def test_every_mapped_prefix_resolves_to_its_family(self) -> None:
        cases = {
            "anthropic.claude-opus-5": "anthropic.messages",
            "anthropic.claude-3-5-sonnet-20241022-v2:0": "anthropic.messages",
            "amazon.nova-pro-v1:0": "amazon.nova.messages",
            "amazon.titan-text-express-v1": "amazon.titan.text",
            "amazon.titan-tg1-large": "amazon.titan.text",
            "meta.llama3-70b-instruct-v1:0": "meta.llama3.prompt",
            "meta.llama3-3-70b-instruct-v1:0": "meta.llama3.prompt",
            "mistral.mistral-7b-instruct-v0:2": "mistral.prompt",
            "mistral.mixtral-8x7b-instruct-v0:1": "mistral.prompt",
            "mistral.mistral-large-2402-v1:0": "mistral.prompt",
            "ai21.jamba-1-5-large-v1:0": "ai21.jamba.chat",
            "cohere.command-r-plus-v1:0": "cohere.command-r.chat",
            "cohere.command-text-v14": "cohere.command.generate",
            "cohere.command-light-text-v14": "cohere.command.generate",
        }
        for model_identifier, family_id in cases.items():
            with self.subTest(model_identifier=model_identifier):
                self.assertEqual(
                    resolve_model_family(model_identifier).family.family_id,
                    family_id,
                )

    def test_cross_region_routing_prefix_is_stripped_for_resolution_only(self) -> None:
        for prefix in ("us.", "eu.", "apac.", "us-gov.", "jp.", "au.", "ca."):
            with self.subTest(prefix=prefix):
                resolution = resolve_model_family(prefix + "anthropic.claude-opus-5")
                self.assertEqual(resolution.family.family_id, "anthropic.messages")
                self.assertEqual(resolution.routing_prefix, prefix)
                # The full id, routing prefix included, stays on the wire.
                self.assertEqual(
                    resolution.model_identifier, prefix + "anthropic.claude-opus-5"
                )

    def test_longest_prefix_wins_so_a_narrow_id_is_not_captured(self) -> None:
        self.assertEqual(
            resolve_model_family("cohere.command-r-v1:0").matched_prefix,
            "cohere.command-r",
        )
        self.assertEqual(
            resolve_model_family("cohere.command-light-text-v14").matched_prefix,
            "cohere.command-light-text",
        )

    def test_known_but_unmapped_families_fail_closed_with_a_reason(self) -> None:
        cases = (
            "amazon.titan-embed-text-v2:0",
            "amazon.titan-image-generator-v1",
            "amazon.nova-canvas-v1:0",
            "amazon.nova-reel-v1:0",
            "cohere.embed-english-v3",
            "cohere.rerank-v3-5:0",
            "meta.llama2-70b-chat-v1",
            "meta.llama4-scout-17b-instruct-v1:0",
            "mistral.pixtral-large-2502-v1:0",
            "mistral.mistral-large-2407-v1:0",
            "ai21.j2-ultra-v1",
            "stability.stable-diffusion-xl-v1",
            "luma.ray-v2:0",
        )
        for model_identifier in cases:
            with self.subTest(model_identifier=model_identifier):
                with self.assertRaises(UnsupportedModelFamilyError) as caught:
                    resolve_model_family(model_identifier)
                message = str(caught.exception)
                self.assertIn("unsupported model family", message)
                self.assertIn(model_identifier, message)

    def test_unknown_vendor_fails_closed(self) -> None:
        for model_identifier in (
            "acme.superllm-v1",
            "writer.palmyra-x5-v1:0",
            "deepseek.r1-v1:0",
            "openai.gpt-oss-120b-1:0",
            "qwen.qwen3-32b-v1:0",
            "titan-text-express-v1",
        ):
            with self.subTest(model_identifier=model_identifier):
                with self.assertRaises(UnsupportedModelFamilyError) as caught:
                    resolve_model_family(model_identifier)
                self.assertIn("unsupported model family", str(caught.exception))
                self.assertIn(
                    "no mapped Bedrock request body shape", str(caught.exception)
                )

    def test_unsupported_family_message_lists_the_supported_families(self) -> None:
        with self.assertRaises(UnsupportedModelFamilyError) as caught:
            resolve_model_family("acme.superllm-v1")
        for family_id in supported_family_ids():
            self.assertIn(family_id, str(caught.exception))

    def test_model_arn_and_malformed_ids_are_rejected(self) -> None:
        for model_identifier in (
            "arn:aws:bedrock:us-east-1:123456789012:inference-profile/x",
            "",
            ".anthropic.claude",
            "anthropic.claude opus",
            "anthropic.claude\nopus",
            "anthropic.claude/opus",
        ):
            with self.subTest(model_identifier=model_identifier):
                with self.assertRaises(BedrockConfigurationError):
                    resolve_model_family(model_identifier)

    def test_no_two_families_claim_the_same_prefix(self) -> None:
        prefixes = [
            prefix for family in MODEL_FAMILIES for prefix in family.prefixes
        ]
        self.assertEqual(len(prefixes), len(set(prefixes)))

    def test_family_ids_are_unique(self) -> None:
        ids = [family.family_id for family in MODEL_FAMILIES]
        self.assertEqual(sorted(ids), sorted(set(ids)))

    def test_config_refuses_an_unmapped_family_at_construction(self) -> None:
        """Nothing that could send a guessed body shape can be built at all."""
        with self.assertRaises(UnsupportedModelFamilyError):
            BedrockProviderConfig(model_identifier="acme.superllm-v1")

    def test_gateway_refuses_an_unmapped_family_at_construction(self) -> None:
        config = BedrockProviderConfig(model_identifier="anthropic.claude-opus-5")
        # Bypassing the frozen config validator still cannot produce a gateway.
        object.__setattr__(config, "model_identifier", "acme.superllm-v1")
        with self.assertRaises(UnsupportedModelFamilyError):
            BedrockInvokeGateway(config)


# --------------------------------------------------------------------------
# Per-family request bodies
# --------------------------------------------------------------------------


class FamilyBodyTests(unittest.TestCase):
    PROMPT = FamilyPrompt(
        system_text="SYS", user_text="USER", max_output_tokens=256,
    )

    def body(self, model_identifier: str) -> dict:
        family = resolve_model_family(model_identifier).family
        return family.build_body(self.PROMPT)

    def test_anthropic_body(self) -> None:
        self.assertEqual(
            self.body("anthropic.claude-opus-5"),
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 256,
                "temperature": 0,
                "system": "SYS",
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "USER"}]}
                ],
            },
        )

    def test_nova_body(self) -> None:
        self.assertEqual(
            self.body("amazon.nova-pro-v1:0"),
            {
                "schemaVersion": "messages-v1",
                "system": [{"text": "SYS"}],
                "messages": [{"role": "user", "content": [{"text": "USER"}]}],
                "inferenceConfig": {"maxNewTokens": 256, "temperature": 0},
            },
        )

    def test_titan_text_body(self) -> None:
        self.assertEqual(
            self.body("amazon.titan-text-express-v1"),
            {
                "inputText": "SYS\n\nUSER",
                "textGenerationConfig": {
                    "maxTokenCount": 256, "temperature": 0, "stopSequences": [],
                },
            },
        )

    def test_llama3_body_uses_the_llama3_chat_template(self) -> None:
        self.assertEqual(
            self.body("meta.llama3-70b-instruct-v1:0"),
            {
                "prompt": (
                    "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
                    "SYS<|eot_id|>"
                    "<|start_header_id|>user<|end_header_id|>\n\n"
                    "USER<|eot_id|>"
                    "<|start_header_id|>assistant<|end_header_id|>\n\n"
                ),
                "max_gen_len": 256,
                "temperature": 0,
            },
        )

    def test_mistral_body(self) -> None:
        self.assertEqual(
            self.body("mistral.mistral-7b-instruct-v0:2"),
            {
                "prompt": "<s>[INST] SYS\n\nUSER [/INST]",
                "max_tokens": 256,
                "temperature": 0,
            },
        )

    def test_jamba_body(self) -> None:
        self.assertEqual(
            self.body("ai21.jamba-1-5-large-v1:0"),
            {
                "messages": [
                    {"role": "system", "content": "SYS"},
                    {"role": "user", "content": "USER"},
                ],
                "max_tokens": 256,
                "temperature": 0,
            },
        )

    def test_cohere_chat_body(self) -> None:
        self.assertEqual(
            self.body("cohere.command-r-plus-v1:0"),
            {
                "message": "SYS\n\nUSER",
                "chat_history": [],
                "max_tokens": 256,
                "temperature": 0,
            },
        )

    def test_cohere_generate_body(self) -> None:
        self.assertEqual(
            self.body("cohere.command-text-v14"),
            {"prompt": "SYS\n\nUSER", "max_tokens": 256, "temperature": 0},
        )

    def test_every_family_has_a_body_test(self) -> None:
        """A new family cannot be added without pinning its body shape here."""
        tested = {
            "anthropic.messages": "anthropic.claude-opus-5",
            "amazon.nova.messages": "amazon.nova-pro-v1:0",
            "amazon.titan.text": "amazon.titan-text-express-v1",
            "meta.llama3.prompt": "meta.llama3-70b-instruct-v1:0",
            "mistral.prompt": "mistral.mistral-7b-instruct-v0:2",
            "ai21.jamba.chat": "ai21.jamba-1-5-large-v1:0",
            "cohere.command-r.chat": "cohere.command-r-plus-v1:0",
            "cohere.command.generate": "cohere.command-text-v14",
        }
        self.assertEqual(set(tested), set(supported_family_ids()))


# --------------------------------------------------------------------------
# Region and credentials
# --------------------------------------------------------------------------


class RegionAndCredentialTests(unittest.TestCase):
    def test_absent_region_fails_closed_with_a_clear_error(self) -> None:
        adapter = gateway(env=environment(AWS_REGION=""))
        with self.assertRaises(BedrockCredentialError) as caught:
            adapter.resolve_region()
        message = str(caught.exception)
        self.assertIn("AWS_REGION is not configured", message)
        self.assertIn("Bedrock requires an explicit region", message)

    def test_complete_refuses_to_call_without_a_region(self) -> None:
        transport = RecordingTransport(anthropic_success())
        adapter = gateway(transport=transport, env=environment(AWS_REGION=""))
        with self.assertRaises(BedrockCredentialError):
            adapter.complete(model_request())
        self.assertEqual(transport.requests, [], "no request may be sent")

    def test_configured_region_is_used_when_the_environment_has_none(self) -> None:
        adapter = gateway(env=environment(AWS_REGION=""), region="eu-west-1")
        self.assertEqual(adapter.resolve_region(), "eu-west-1")

    def test_configured_region_overrides_the_environment(self) -> None:
        adapter = gateway(region="ap-southeast-2")
        self.assertEqual(adapter.resolve_region(), "ap-southeast-2")

    def test_invalid_region_is_rejected(self) -> None:
        with self.assertRaises(BedrockConfigurationError):
            BedrockProviderConfig(
                model_identifier="anthropic.claude-opus-5", region="US-East-1"
            )
        adapter = gateway(env=environment(AWS_REGION="US-East-1"))
        with self.assertRaises(BedrockCredentialError):
            adapter.resolve_region()

    def test_missing_credentials_fail_closed_and_send_nothing(self) -> None:
        for absent in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            with self.subTest(absent=absent):
                transport = RecordingTransport(anthropic_success())
                adapter = gateway(
                    transport=transport, env=environment(**{absent: ""})
                )
                with self.assertRaises(BedrockCredentialError) as caught:
                    adapter.complete(model_request())
                self.assertIn(absent, str(caught.exception))
                self.assertEqual(transport.requests, [])

    def test_credential_error_never_echoes_a_credential_value(self) -> None:
        adapter = gateway(env=environment(AWS_ACCESS_KEY_ID=""))
        with self.assertRaises(BedrockCredentialError) as caught:
            adapter.resolve_credentials()
        self.assertNotIn(SECRET_ACCESS_KEY, str(caught.exception))

    def test_session_token_is_optional_and_signed_when_present(self) -> None:
        transport = RecordingTransport(anthropic_success())
        adapter = gateway(
            transport=transport,
            env=environment(AWS_SESSION_TOKEN=SESSION_TOKEN),
        )
        adapter.complete(model_request())
        headers = dict(transport.requests[0].headers)
        self.assertEqual(headers["x-amz-security-token"], SESSION_TOKEN)
        self.assertIn("x-amz-security-token", headers["Authorization"])


# --------------------------------------------------------------------------
# Signing and endpoint construction
# --------------------------------------------------------------------------


class SigningTests(unittest.TestCase):
    def test_endpoint_url_and_signing_service(self) -> None:
        adapter = gateway()
        self.assertEqual(
            adapter.endpoint_url("us-east-1"),
            "https://bedrock-runtime.us-east-1.amazonaws.com/"
            "model/anthropic.claude-opus-5/invoke",
        )
        self.assertEqual(adapter.config.signing_service, BEDROCK_SIGNING_SERVICE)
        self.assertEqual(BEDROCK_SIGNING_SERVICE, "bedrock")

    def test_model_id_colon_is_percent_encoded_in_the_path(self) -> None:
        adapter = gateway("amazon.nova-pro-v1:0")
        self.assertEqual(
            adapter.endpoint_url("eu-central-1"),
            "https://bedrock-runtime.eu-central-1.amazonaws.com/"
            "model/amazon.nova-pro-v1%3A0/invoke",
        )

    def test_request_is_a_signed_post_with_a_scoped_authorization_header(self) -> None:
        transport = RecordingTransport(anthropic_success())
        adapter = gateway(transport=transport)
        adapter.complete(model_request())
        sent = transport.requests[0]
        headers = {name.lower(): value for name, value in sent.headers}
        self.assertEqual(sent.method, "POST")
        self.assertEqual(
            sent.url,
            "https://bedrock-runtime.us-east-1.amazonaws.com/"
            "model/anthropic.claude-opus-5/invoke",
        )
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["x-amz-date"], "20260821T093000Z")
        self.assertTrue(
            headers["authorization"].startswith(
                "AWS4-HMAC-SHA256 Credential="
                f"{ACCESS_KEY_ID}/20260821/us-east-1/bedrock/aws4_request, "
            )
        )
        self.assertIn(
            "SignedHeaders=accept;content-type;host;x-amz-date,",
            headers["authorization"],
        )
        self.assertEqual(sent.timeout_milliseconds, 120_000)

    def test_body_and_signature_are_deterministic_for_identical_inputs(self) -> None:
        def once() -> BedrockHttpRequest:
            transport = RecordingTransport(anthropic_success())
            adapter = gateway(transport=transport)
            adapter.complete(model_request())
            return transport.requests[0]

        first, second = once(), once()
        self.assertEqual(first.body, second.body)
        self.assertEqual(first.headers, second.headers)

    def test_prompt_carries_the_canonical_schema_verbatim(self) -> None:
        transport = RecordingTransport(anthropic_success())
        adapter = gateway(transport=transport)
        prepared = adapter.prepare(model_request())
        adapter.complete(model_request(), prepared)
        body = json.loads(transport.requests[0].body.decode("utf-8"))
        self.assertIn(SCHEMA_INSTRUCTION, body["system"])
        self.assertIn(prepared.provider_schema_json, body["system"])
        self.assertEqual(
            body["messages"][0]["content"][0]["text"], '{"context":"alpha"}'
        )


class SchemaPreparationTests(unittest.TestCase):
    def test_projection_is_the_identity_and_declares_no_native_strict_mode(self) -> None:
        prepared = gateway().prepare(model_request())
        self.assertEqual(prepared.provider, BEDROCK_PROVIDER)
        self.assertEqual(
            prepared.provider_schema_json, canonical_json(json.loads(RESPONSE_SCHEMA))
        )
        self.assertEqual(
            prepared.canonical_schema_hash, prepared.provider_schema_hash
        )
        manifest = json.loads(prepared.transformation_manifest_json)
        self.assertEqual(manifest["projection"], "identity")
        self.assertFalse(manifest["native_structured_output"])
        self.assertEqual(manifest["adapter_version"], BEDROCK_ADAPTER_VERSION)
        report = json.loads(prepared.compatibility_report_json)
        self.assertFalse(report["native_strict_schema_supported"])
        self.assertTrue(report["canonical_validation_required"])

    def test_non_object_or_invalid_schema_fails_closed(self) -> None:
        adapter = gateway()
        for schema in ("not json", "[]", '"text"'):
            with self.subTest(schema=schema):
                with self.assertRaises(BedrockConfigurationError):
                    adapter.prepare(model_request(response_schema=schema))

    def test_preparation_hashes_reach_the_result(self) -> None:
        transport = RecordingTransport(anthropic_success())
        adapter = gateway(transport=transport)
        prepared = adapter.prepare(model_request())
        result = adapter.complete(model_request(), prepared)
        self.assertEqual(result.provider_schema_hash, prepared.provider_schema_hash)
        self.assertIsNotNone(result.projection_manifest_hash)
        self.assertIsNotNone(result.compatibility_report_hash)


# --------------------------------------------------------------------------
# Response mapping
# --------------------------------------------------------------------------


class SuccessMappingTests(unittest.TestCase):
    def test_anthropic_success(self) -> None:
        adapter = gateway(transport=RecordingTransport(anthropic_success()))
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.SUCCEEDED)
        self.assertEqual(result.provider, BEDROCK_PROVIDER)
        self.assertEqual(result.model_identifier, "anthropic.claude-opus-5")
        self.assertEqual(result.structured_output, VALID_OUTPUT)
        self.assertEqual(result.retry_classification, "none")
        self.assertEqual(result.provider_request_id, "req-abc-123")
        self.assertEqual(result.usage.usage_source, "api_reported")
        self.assertEqual(result.usage.input_tokens, 41)
        self.assertEqual(result.usage.output_tokens, 17)
        self.assertEqual(result.usage.total_tokens, 58)
        self.assertIsNone(result.refusal)
        self.assertIsNone(result.provider_failure)

    def test_success_carries_no_warrant_or_status_field(self) -> None:
        """A Bedrock result is a proposal, exactly like every other provider."""
        adapter = gateway(transport=RecordingTransport(anthropic_success()))
        result = adapter.complete(model_request())
        rendered = json.loads(canonical_json(result))
        for forbidden in ("warrant", "warrant_kind", "claim_status", "truth_status"):
            self.assertNotIn(forbidden, rendered)

    def test_nova_success_and_usage(self) -> None:
        response = json_response(
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": VALID_OUTPUT}],
                    }
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 12, "outputTokens": 8, "totalTokens": 20},
            }
        )
        adapter = gateway("amazon.nova-pro-v1:0", transport=RecordingTransport(response))
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.SUCCEEDED)
        self.assertEqual(result.usage.input_tokens, 12)
        self.assertEqual(result.usage.output_tokens, 8)

    def test_titan_text_success(self) -> None:
        response = json_response(
            {
                "inputTextTokenCount": 30,
                "results": [
                    {
                        "tokenCount": 9,
                        "outputText": VALID_OUTPUT,
                        "completionReason": "FINISH",
                    }
                ],
            }
        )
        adapter = gateway(
            "amazon.titan-text-express-v1", transport=RecordingTransport(response)
        )
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.SUCCEEDED)
        self.assertEqual(result.usage.total_tokens, 39)

    def test_llama3_success(self) -> None:
        response = json_response(
            {
                "generation": VALID_OUTPUT,
                "prompt_token_count": 55,
                "generation_token_count": 11,
                "stop_reason": "stop",
            }
        )
        adapter = gateway(
            "meta.llama3-70b-instruct-v1:0", transport=RecordingTransport(response)
        )
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.SUCCEEDED)
        self.assertEqual(result.usage.input_tokens, 55)

    def test_jamba_success(self) -> None:
        response = json_response(
            {
                "id": "chat-1",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": VALID_OUTPUT},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25,
                },
            }
        )
        adapter = gateway(
            "ai21.jamba-1-5-large-v1:0", transport=RecordingTransport(response)
        )
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.SUCCEEDED)
        self.assertEqual(result.usage.output_tokens, 5)

    def test_mistral_success_takes_usage_from_bedrock_headers(self) -> None:
        response = json_response(
            {"outputs": [{"text": VALID_OUTPUT, "stop_reason": "stop"}]},
            headers=(
                ("x-amzn-bedrock-input-token-count", "77"),
                ("x-amzn-bedrock-output-token-count", "13"),
            ),
        )
        adapter = gateway(
            "mistral.mistral-7b-instruct-v0:2", transport=RecordingTransport(response)
        )
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.SUCCEEDED)
        self.assertEqual(result.usage.usage_source, "api_reported")
        self.assertEqual(result.usage.input_tokens, 77)
        self.assertEqual(result.usage.output_tokens, 13)

    def test_cohere_chat_success_takes_usage_from_bedrock_headers(self) -> None:
        response = json_response(
            {
                "response_id": "r1",
                "text": VALID_OUTPUT,
                "generation_id": "g1",
                "finish_reason": "COMPLETE",
            },
            headers=(
                ("x-amzn-bedrock-input-token-count", "5"),
                ("x-amzn-bedrock-output-token-count", "6"),
            ),
        )
        adapter = gateway(
            "cohere.command-r-plus-v1:0", transport=RecordingTransport(response)
        )
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.SUCCEEDED)
        self.assertEqual(result.usage.total_tokens, 11)

    def test_cohere_generate_success(self) -> None:
        response = json_response(
            {
                "id": "gen-1",
                "generations": [
                    {"id": "g", "text": VALID_OUTPUT, "finish_reason": "COMPLETE"}
                ],
            },
            headers=(
                ("x-amzn-bedrock-input-token-count", "5"),
                ("x-amzn-bedrock-output-token-count", "6"),
            ),
        )
        adapter = gateway(
            "cohere.command-text-v14", transport=RecordingTransport(response)
        )
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.SUCCEEDED)


class RefusalAndIncompleteTests(unittest.TestCase):
    def test_anthropic_refusal_maps_to_refused(self) -> None:
        response = json_response(
            {
                "content": [],
                "stop_reason": "refusal",
                "usage": {"input_tokens": 5, "output_tokens": 0},
            }
        )
        result = gateway(transport=RecordingTransport(response)).complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.REFUSED)
        self.assertEqual(result.retry_classification, "not_retryable:refusal")
        self.assertIsNone(result.structured_output)
        self.assertIsNotNone(result.refusal)

    def test_titan_content_filter_maps_to_refused(self) -> None:
        response = json_response(
            {
                "inputTextTokenCount": 3,
                "results": [
                    {"tokenCount": 0, "outputText": "", "completionReason": "CONTENT_FILTERED"}
                ],
            }
        )
        adapter = gateway(
            "amazon.titan-text-express-v1", transport=RecordingTransport(response)
        )
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.REFUSED)

    def test_truncation_maps_to_incomplete_not_success(self) -> None:
        cases = (
            (
                "anthropic.claude-opus-5",
                {
                    "content": [{"type": "text", "text": '{"schema_ver'}],
                    "stop_reason": "max_tokens",
                    "usage": {"input_tokens": 5, "output_tokens": 4096},
                },
                "max_tokens",
            ),
            (
                "amazon.nova-pro-v1:0",
                {
                    "output": {"message": {"content": [{"text": "{"}]}},
                    "stopReason": "max_tokens",
                    "usage": {"inputTokens": 1, "outputTokens": 2},
                },
                "max_tokens",
            ),
            (
                "amazon.titan-text-express-v1",
                {
                    "inputTextTokenCount": 1,
                    "results": [
                        {"tokenCount": 2, "outputText": "{", "completionReason": "LENGTH"}
                    ],
                },
                "LENGTH",
            ),
            (
                "meta.llama3-70b-instruct-v1:0",
                {
                    "generation": "{",
                    "prompt_token_count": 1,
                    "generation_token_count": 2,
                    "stop_reason": "length",
                },
                "length",
            ),
        )
        for model_identifier, payload, reason in cases:
            with self.subTest(model_identifier=model_identifier):
                adapter = gateway(
                    model_identifier,
                    transport=RecordingTransport(json_response(payload)),
                )
                result = adapter.complete(model_request())
                self.assertEqual(result.status, ModelResultStatus.INCOMPLETE)
                self.assertEqual(result.incomplete_reason, reason)
                self.assertIsNone(result.structured_output)
                self.assertEqual(
                    result.retry_classification, "not_retryable:incomplete_response"
                )


class MalformedOutputTests(unittest.TestCase):
    """Unvalidated output is never returned as a success."""

    def _result(self, payload_text: str):
        adapter = gateway(transport=RecordingTransport(anthropic_success(payload_text)))
        return adapter.complete(model_request())

    def test_output_that_is_not_json_is_malformed(self) -> None:
        result = self._result("here is your claim: {oops")
        self.assertEqual(result.status, ModelResultStatus.MALFORMED)
        self.assertEqual(
            result.retry_classification, "fatal:output_failed_canonical_schema"
        )
        self.assertIsNone(result.structured_output)

    def test_output_wrapped_in_prose_or_a_fence_is_malformed(self) -> None:
        for text in (
            f"Sure! ```json\n{VALID_OUTPUT}\n```",
            f"{VALID_OUTPUT}\nHope that helps.",
        ):
            with self.subTest(text=text[:20]):
                self.assertEqual(
                    self._result(text).status, ModelResultStatus.MALFORMED
                )

    def test_output_that_is_not_an_object_is_malformed(self) -> None:
        for text in ("[]", '"a string"', "42", "null"):
            with self.subTest(text=text):
                self.assertEqual(
                    self._result(text).status, ModelResultStatus.MALFORMED
                )

    def test_output_violating_the_canonical_schema_is_malformed(self) -> None:
        cases = (
            {"schema_version": "1.0.0", "result_type": "candidate_claim", "target_claim_id": "c"},
            {"schema_version": "2.0.0", "result_type": "banned", "target_claim_id": "c"},
            {"schema_version": "2.0.0", "result_type": "candidate_claim"},
            {"schema_version": "2.0.0", "result_type": "candidate_claim", "target_claim_id": ""},
            {
                "schema_version": "2.0.0", "result_type": "candidate_claim",
                "target_claim_id": "c", "extra": 1,
            },
        )
        for payload in cases:
            with self.subTest(payload=payload):
                result = self._result(json.dumps(payload, sort_keys=True))
                self.assertEqual(result.status, ModelResultStatus.MALFORMED)
                self.assertIsNone(result.structured_output)

    def test_response_body_that_is_not_json_is_malformed(self) -> None:
        response = BedrockHttpResponse(
            status_code=200,
            headers=(("content-type", "application/json"),),
            body=b"<html>not json</html>",
        )
        result = gateway(transport=RecordingTransport(response)).complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.MALFORMED)
        self.assertEqual(result.retry_classification, "fatal:response_not_json")

    def test_response_body_that_is_not_an_object_is_malformed(self) -> None:
        result = gateway(
            transport=RecordingTransport(json_response(["not", "an", "object"]))
        ).complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.MALFORMED)
        self.assertEqual(result.retry_classification, "fatal:response_not_object")

    def test_unexpected_family_response_shape_is_malformed(self) -> None:
        cases = (
            ("anthropic.claude-opus-5", {"stop_reason": "end_turn", "content": "text"}),
            ("anthropic.claude-opus-5", {"stop_reason": "end_turn", "content": []}),
            ("amazon.nova-pro-v1:0", {"stopReason": "end_turn", "output": {}}),
            ("amazon.titan-text-express-v1", {"results": []}),
            ("meta.llama3-70b-instruct-v1:0", {"stop_reason": "stop"}),
            ("mistral.mistral-7b-instruct-v0:2", {"outputs": []}),
            ("ai21.jamba-1-5-large-v1:0", {"choices": [{"finish_reason": "stop"}]}),
            ("cohere.command-r-plus-v1:0", {"finish_reason": "COMPLETE"}),
            ("cohere.command-text-v14", {"generations": [{}]}),
        )
        for model_identifier, payload in cases:
            with self.subTest(model_identifier=model_identifier, payload=payload):
                adapter = gateway(
                    model_identifier, transport=RecordingTransport(json_response(payload))
                )
                result = adapter.complete(model_request())
                self.assertEqual(result.status, ModelResultStatus.MALFORMED)
                self.assertEqual(
                    result.retry_classification,
                    "fatal:family_response_shape_unexpected",
                )

    def test_unattributable_usage_is_malformed_not_a_success(self) -> None:
        """A call whose cost cannot be attributed is not recorded as a success."""
        response = json_response(
            {"outputs": [{"text": VALID_OUTPUT, "stop_reason": "stop"}]}
        )
        adapter = gateway(
            "mistral.mistral-7b-instruct-v0:2", transport=RecordingTransport(response)
        )
        result = adapter.complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.MALFORMED)
        self.assertEqual(result.retry_classification, "fatal:missing_usage")
        self.assertEqual(result.usage.usage_source, "unavailable")
        self.assertIsNone(result.structured_output)

    def test_negative_or_non_numeric_token_counts_are_not_accepted(self) -> None:
        response = json_response(
            {
                "content": [{"type": "text", "text": VALID_OUTPUT}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": -1, "output_tokens": "many"},
            }
        )
        result = gateway(transport=RecordingTransport(response)).complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.MALFORMED)
        self.assertEqual(result.retry_classification, "fatal:missing_usage")


# --------------------------------------------------------------------------
# Error classification
# --------------------------------------------------------------------------


class ErrorClassificationTests(unittest.TestCase):
    def test_retryable_codes(self) -> None:
        for code in (
            "ThrottlingException",
            "TooManyRequestsException",
            "ModelNotReadyException",
            "ModelTimeoutException",
            "ServiceUnavailableException",
            "InternalServerException",
        ):
            with self.subTest(code=code):
                retryable, classification = classify_bedrock_error(
                    status_code=400, error_code=code
                )
                self.assertTrue(retryable)
                self.assertEqual(classification, f"retryable:{code}")

    def test_fatal_codes(self) -> None:
        for code in (
            "AccessDeniedException",
            "ValidationException",
            "ResourceNotFoundException",
            "ModelErrorException",
            "ServiceQuotaExceededException",
            "ExpiredTokenException",
            "InvalidSignatureException",
            "UnrecognizedClientException",
        ):
            with self.subTest(code=code):
                retryable, classification = classify_bedrock_error(
                    status_code=503, error_code=code
                )
                self.assertFalse(retryable, "the AWS code must win over the status")
                self.assertEqual(classification, f"fatal:{code}")

    def test_status_fallback_when_no_code_is_present(self) -> None:
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                retryable, classification = classify_bedrock_error(
                    status_code=status, error_code=None
                )
                self.assertTrue(retryable)
                self.assertEqual(classification, f"retryable:http_{status}")
        for status in (400, 403, 404, 413):
            with self.subTest(status=status):
                retryable, classification = classify_bedrock_error(
                    status_code=status, error_code=None
                )
                self.assertFalse(retryable)
                self.assertEqual(classification, f"fatal:http_{status}")

    def test_unknown_code_is_fatal(self) -> None:
        retryable, classification = classify_bedrock_error(
            status_code=418, error_code="SomethingNewException"
        )
        self.assertFalse(retryable)
        self.assertEqual(classification, "fatal:SomethingNewException")

    def test_error_code_is_read_from_header_or_body(self) -> None:
        self.assertEqual(
            extract_error_code(
                headers=(("x-amzn-errortype", "ThrottlingException:http://x/"),),
                body={},
            ),
            "ThrottlingException",
        )
        self.assertEqual(
            extract_error_code(
                headers=(),
                body={"__type": "com.amazon.coral.service#ValidationException"},
            ),
            "ValidationException",
        )
        self.assertEqual(
            extract_error_code(headers=(), body={"code": "AccessDeniedException"}),
            "AccessDeniedException",
        )
        self.assertIsNone(extract_error_code(headers=(), body={"message": "no code"}))
        self.assertIsNone(extract_error_code(headers=(), body="plain text"))

    def test_throttling_response_produces_a_retryable_failure(self) -> None:
        response = json_response(
            {"message": "Too many requests, please wait"},
            status_code=429,
            headers=(("x-amzn-errortype", "ThrottlingException:"),),
        )
        result = gateway(transport=RecordingTransport(response)).complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.FAILED)
        self.assertEqual(
            result.retry_classification, "retryable:ThrottlingException"
        )
        self.assertIsNotNone(result.provider_failure)
        assert result.provider_failure is not None
        self.assertEqual(result.provider_failure.http_status_code, 429)
        self.assertEqual(
            result.provider_failure.provider_error_code, "ThrottlingException"
        )
        self.assertEqual(
            result.provider_failure.adapter_version, BEDROCK_ADAPTER_VERSION
        )
        self.assertEqual(
            result.provider_failure.sdk_version, SIGV4_IMPLEMENTATION_VERSION
        )

    def test_access_denied_response_produces_a_fatal_failure(self) -> None:
        response = json_response(
            {"message": "User is not authorized to perform bedrock:InvokeModel"},
            status_code=403,
            headers=(("x-amzn-errortype", "AccessDeniedException"),),
        )
        result = gateway(transport=RecordingTransport(response)).complete(model_request())
        self.assertEqual(
            result.retry_classification, "fatal:AccessDeniedException"
        )
        assert result.provider_failure is not None
        self.assertIn(
            "not authorized", result.provider_failure.provider_error_message or ""
        )

    def test_validation_error_preserves_the_body_hash_and_length(self) -> None:
        response = json_response(
            {"message": "malformed input request"},
            status_code=400,
            headers=(("x-amzn-errortype", "ValidationException"),),
        )
        result = gateway(transport=RecordingTransport(response)).complete(model_request())
        assert result.provider_failure is not None
        diagnostic = result.provider_failure
        self.assertEqual(result.retry_classification, "fatal:ValidationException")
        self.assertTrue(diagnostic.response_body_sha256.startswith("sha256:"))
        self.assertGreater(diagnostic.response_body_byte_length, 0)
        self.assertFalse(diagnostic.response_body_preview_truncated)

    def test_oversized_error_body_preview_is_truncated_and_flagged(self) -> None:
        response = json_response(
            {"message": "x" * 20_000},
            status_code=400,
            headers=(("x-amzn-errortype", "ValidationException"),),
        )
        result = gateway(transport=RecordingTransport(response)).complete(model_request())
        assert result.provider_failure is not None
        self.assertTrue(result.provider_failure.response_body_preview_truncated)
        self.assertLessEqual(
            len(result.provider_failure.response_body_preview.encode("utf-8")),
            result.provider_failure.diagnostic_text_limit_bytes,
        )

    def test_non_json_error_body_still_produces_a_diagnostic(self) -> None:
        response = BedrockHttpResponse(
            status_code=502,
            headers=(("content-type", "text/html"),),
            body=b"<html>502 Bad Gateway</html>",
        )
        result = gateway(transport=RecordingTransport(response)).complete(model_request())
        self.assertEqual(result.retry_classification, "retryable:http_502")
        assert result.provider_failure is not None
        self.assertIn("502 Bad Gateway", result.provider_failure.response_body_preview)


class TransportFailureTests(unittest.TestCase):
    def test_timeout_maps_to_timed_out_and_retryable(self) -> None:
        transport = RecordingTransport(BedrockTransportTimeout("deadline"))
        result = gateway(transport=transport).complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.TIMED_OUT)
        self.assertEqual(result.retry_classification, "retryable:timeout")
        self.assertEqual(result.usage.usage_source, "unavailable")

    def test_transport_failure_maps_to_failed_and_retryable(self) -> None:
        transport = RecordingTransport(BedrockTransportFailure("reset"))
        result = gateway(transport=transport).complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.FAILED)
        self.assertEqual(result.retry_classification, "retryable:transport")

    def test_transport_returning_the_wrong_type_is_a_fatal_failure(self) -> None:
        class BadTransport:
            def send(self, request: BedrockHttpRequest) -> object:
                return {"status_code": 200}

        result = gateway(transport=BadTransport()).complete(model_request())
        self.assertEqual(result.status, ModelResultStatus.FAILED)
        self.assertEqual(
            result.retry_classification, "fatal:transport_contract_violated"
        )

    def test_response_size_bound_is_configurable_and_bounded(self) -> None:
        transport = RecordingTransport(anthropic_success())
        adapter = BedrockInvokeGateway(
            BedrockProviderConfig(
                model_identifier="anthropic.claude-opus-5", max_response_bytes=1024,
            ),
            transport=transport,
            environment=environment(),
            env_file_path=ABSENT_ENV_FILE,
            clock=lambda: FROZEN_MOMENT,
        )
        adapter.complete(model_request())
        self.assertEqual(transport.requests[0].max_response_bytes, 1024)
        for value in (0, -1, 1 << 40, True):
            with self.subTest(value=value):
                with self.assertRaises(BedrockConfigurationError):
                    BedrockProviderConfig(
                        model_identifier="anthropic.claude-opus-5",
                        max_response_bytes=value,  # type: ignore[arg-type]
                    )


# --------------------------------------------------------------------------
# Secret containment
# --------------------------------------------------------------------------


class SecretContainmentTests(unittest.TestCase):
    """No credential and no signing material may reach a record or diagnostic."""

    def _hostile_error_response(self) -> BedrockHttpResponse:
        """An error body that echoes back everything an attacker would want."""
        return json_response(
            {
                "message": (
                    "Signature mismatch. Provided credential "
                    f"{ACCESS_KEY_ID}, secret {SECRET_ACCESS_KEY}, "
                    f"token {SESSION_TOKEN}"
                ),
                "authorization": f"AWS4-HMAC-SHA256 Credential={ACCESS_KEY_ID}/x",
                "x-amz-security-token": SESSION_TOKEN,
                "nested": {
                    "secret": SECRET_ACCESS_KEY,
                    "echo": [SECRET_ACCESS_KEY, SESSION_TOKEN],
                },
            },
            status_code=403,
            headers=(("x-amzn-errortype", "InvalidSignatureException"),),
        )

    def test_no_credential_reaches_the_failure_diagnostic(self) -> None:
        transport = RecordingTransport(self._hostile_error_response())
        adapter = gateway(
            transport=transport,
            env=environment(AWS_SESSION_TOKEN=SESSION_TOKEN),
        )
        result = adapter.complete(model_request())
        self.assertEqual(
            result.retry_classification, "fatal:InvalidSignatureException"
        )
        rendered = canonical_json(result)
        for secret in (SECRET_ACCESS_KEY, SESSION_TOKEN, ACCESS_KEY_ID):
            self.assertNotIn(secret, rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_no_signing_material_reaches_the_failure_diagnostic(self) -> None:
        transport = RecordingTransport(self._hostile_error_response())
        adapter = gateway(
            transport=transport,
            env=environment(AWS_SESSION_TOKEN=SESSION_TOKEN),
        )
        result = adapter.complete(model_request())
        authorization = dict(transport.requests[0].headers)["Authorization"]
        signature = authorization.rsplit("Signature=", 1)[1]
        rendered = canonical_json(result)
        self.assertNotIn(signature, rendered)
        self.assertNotIn(authorization, rendered)
        self.assertNotIn("AWS4" + SECRET_ACCESS_KEY, rendered)

    def test_successful_result_carries_no_credential(self) -> None:
        adapter = gateway(
            transport=RecordingTransport(anthropic_success()),
            env=environment(AWS_SESSION_TOKEN=SESSION_TOKEN),
        )
        rendered = canonical_json(adapter.complete(model_request()))
        for secret in (SECRET_ACCESS_KEY, SESSION_TOKEN, ACCESS_KEY_ID):
            self.assertNotIn(secret, rendered)

    def test_endpoint_recorded_in_the_diagnostic_carries_no_credential(self) -> None:
        transport = RecordingTransport(self._hostile_error_response())
        adapter = gateway(
            transport=transport,
            env=environment(AWS_SESSION_TOKEN=SESSION_TOKEN),
        )
        result = adapter.complete(model_request())
        assert result.provider_failure is not None
        self.assertNotIn(SECRET_ACCESS_KEY, result.provider_failure.endpoint)
        self.assertNotIn(SESSION_TOKEN, result.provider_failure.endpoint)
        self.assertIn("bedrock-runtime", result.provider_failure.endpoint)

    def test_error_message_field_is_redacted_not_dropped(self) -> None:
        transport = RecordingTransport(self._hostile_error_response())
        adapter = gateway(
            transport=transport,
            env=environment(AWS_SESSION_TOKEN=SESSION_TOKEN),
        )
        result = adapter.complete(model_request())
        assert result.provider_failure is not None
        message = result.provider_failure.provider_error_message or ""
        self.assertIn("Signature mismatch", message, "the failure is preserved")
        self.assertNotIn(SECRET_ACCESS_KEY, message)
        self.assertNotIn(SESSION_TOKEN, message)

    def test_body_hash_is_of_the_raw_body_so_evidence_is_not_lost(self) -> None:
        response = self._hostile_error_response()
        transport = RecordingTransport(response)
        adapter = gateway(transport=transport)
        result = adapter.complete(model_request())
        assert result.provider_failure is not None
        self.assertEqual(
            result.provider_failure.response_body_byte_length, len(response.body)
        )


# --------------------------------------------------------------------------
# Configuration and pricing artifacts
# --------------------------------------------------------------------------


class PricingSnapshotArtifactTests(unittest.TestCase):
    def payload(self) -> dict:
        return json.loads(PRICING_PATH.read_text(encoding="utf-8"))

    def test_file_exists_and_matches_the_pricing_snapshot_schema_field_set(self) -> None:
        payload = self.payload()
        self.assertEqual(set(payload), set(PRICING_FIELDS))
        self.assertEqual(payload["provider"], BEDROCK_PROVIDER)
        self.assertEqual(payload["currency"], "USD")
        self.assertEqual(payload["units"], PRICING_UNITS)

    def test_content_hash_is_self_consistent_and_deterministic(self) -> None:
        payload = self.payload()
        recomputed = dict(payload)
        recomputed["content_hash"] = None
        self.assertEqual(canonical_hash(recomputed), payload["content_hash"])

    def test_file_bytes_are_canonical_so_a_rewrite_is_byte_identical(self) -> None:
        payload = self.payload()
        self.assertEqual(
            PRICING_PATH.read_text(encoding="utf-8"), canonical_json(payload) + "\n"
        )

    def test_rates_are_labelled_unconfirmed_placeholders_naming_the_source(self) -> None:
        source = self.payload()["source"]
        self.assertIn(BEDROCK_PRICING_SOURCE, source)
        self.assertIn("UNCONFIRMED PLACEHOLDER", source)

    def test_snapshot_loads_through_the_repository_pricing_validator(self) -> None:
        snapshot = load_pricing_snapshot(PRICING_PATH)
        self.assertIsInstance(snapshot, PricingSnapshot)
        self.assertEqual(snapshot.provider, BEDROCK_PROVIDER)
        self.assertEqual(
            snapshot.snapshot_id, OpaqueId(self.payload()["snapshot_id"])
        )

    def test_placeholder_rates_make_a_live_call_refuse_rather_than_look_free(self) -> None:
        """Fail closed: an unpriced Bedrock model must not appear to cost nothing."""
        snapshot = load_pricing_snapshot(PRICING_PATH)
        configuration = load_live_run_configuration(LIVE_CONFIG_PATH)
        estimate = estimate_cost_microusd(
            snapshot,
            input_tokens=configuration.per_call_input_token_reserve,
            output_tokens=configuration.per_call_output_token_reserve,
        )
        self.assertGreater(estimate, configuration.budget.max_cost_microusd)


class LiveRunConfigurationArtifactTests(unittest.TestCase):
    def payload(self) -> dict:
        return json.loads(LIVE_CONFIG_PATH.read_text(encoding="utf-8"))

    def test_file_matches_the_live_run_configuration_schema_field_set(self) -> None:
        payload = self.payload()
        self.assertEqual(set(payload), set(LIVE_CONFIG_FIELDS))
        self.assertEqual(payload["provider"], BEDROCK_PROVIDER)
        self.assertEqual(payload["schema_version"], "1.0.0")

    def test_content_hash_is_self_consistent(self) -> None:
        payload = self.payload()
        recomputed = dict(payload)
        recomputed["content_hash"] = None
        self.assertEqual(canonical_hash(recomputed), payload["content_hash"])

    def test_configuration_loads_through_the_repository_validator(self) -> None:
        configuration = load_live_run_configuration(LIVE_CONFIG_PATH)
        self.assertEqual(configuration.provider, BEDROCK_PROVIDER)
        self.assertEqual(
            configuration.model_identifier, self.payload()["model_identifier"]
        )
        self.assertGreater(configuration.call_timeout_milliseconds, 0)

    def test_file_bytes_are_canonical(self) -> None:
        payload = self.payload()
        self.assertEqual(
            LIVE_CONFIG_PATH.read_text(encoding="utf-8"),
            canonical_json(payload) + "\n",
        )

    def test_configuration_references_the_shipped_pricing_snapshot(self) -> None:
        configuration = self.payload()
        pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            configuration["pricing_snapshot_id"], pricing["snapshot_id"]
        )
        self.assertEqual(
            configuration["model_identifier"], pricing["model_identifier"]
        )

    def test_configured_model_resolves_to_a_mapped_family(self) -> None:
        resolution = resolve_model_family(self.payload()["model_identifier"])
        self.assertIn(resolution.family.family_id, supported_family_ids())

    def test_no_credential_appears_in_either_versioned_artifact(self) -> None:
        for path in (LIVE_CONFIG_PATH, PRICING_PATH):
            text = path.read_text(encoding="utf-8")
            for token in ("AWS_SECRET", "aws_secret", "AKIA", "ASIA", "session_token"):
                self.assertNotIn(token, text, f"{path.name} must carry no credential")


# --------------------------------------------------------------------------
# Import and dependency hygiene
# --------------------------------------------------------------------------


class HygieneTests(unittest.TestCase):
    def test_module_holds_no_sdk_or_network_reference_after_import(self) -> None:
        for forbidden in (
            "boto3", "botocore", "anthropic", "socket", "ssl", "requests", "urllib3",
        ):
            self.assertFalse(
                hasattr(bedrock_gateway, forbidden),
                f"bedrock_gateway must not reference {forbidden} at module scope",
            )

    def test_no_third_party_import_appears_in_either_new_module(self) -> None:
        for name in ("bedrock_gateway.py", "aws_sigv4.py"):
            source = (
                REPO_ROOT / "src" / "math_research" / "phase2" / name
            ).read_text(encoding="utf-8")
            for forbidden in ("import boto3", "import botocore", "import anthropic"):
                self.assertNotIn(forbidden, source, f"{name} must stay dependency free")

    def test_runtime_dependencies_are_still_empty(self) -> None:
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["dependencies"], [])

    def test_constructing_the_gateway_resolves_no_credential(self) -> None:
        """Construction must be inert: nothing is read until ``complete``."""
        empty: dict[str, str] = {}
        adapter = BedrockInvokeGateway(
            BedrockProviderConfig(model_identifier="anthropic.claude-opus-5"),
            environment=empty,
            env_file_path=ABSENT_ENV_FILE,
            clock=lambda: FROZEN_MOMENT,
        )
        self.assertEqual(empty, {})
        self.assertEqual(adapter.resolution.family.family_id, "anthropic.messages")

    def test_default_transport_is_not_constructed_until_needed(self) -> None:
        adapter = gateway()
        self.assertIsNone(adapter._transport)

    def test_importing_the_modules_loads_no_network_module(self) -> None:
        """Import must be inert: networking is loaded inside the gated call."""
        program = (
            "import sys;"
            "before=set(sys.modules);"
            "import math_research.phase2.bedrock_gateway;"
            "import math_research.phase2.aws_sigv4;"
            "roots={m.split('.')[0] for m in set(sys.modules)-before};"
            "forbidden={'socket','ssl','http','boto3','botocore','anthropic',"
            "'requests','urllib3'};"
            "print(sorted(roots & forbidden))"
        )
        completed = subprocess.run(
            (sys.executable, "-c", program),
            check=True, capture_output=True, text=True, timeout=60,
            cwd=str(REPO_ROOT),
            env={
                "PYTHONPATH": str(REPO_ROOT / "src"),
                "PATH": "/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        self.assertEqual(completed.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
