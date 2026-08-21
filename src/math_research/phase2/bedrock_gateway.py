"""Opt-in AWS Bedrock ``InvokeModel`` adapter for the Phase 2 model boundary.

ADR-0030 admits Bedrock as an additional :class:`~.ports.ModelGateway` behind
the existing Phase 2 boundary and fixes three properties of this module:

* Bedrock request and response bodies differ per vendor, so ``ModelRequest`` is
  mapped **per model family, keyed by model-id prefix**. An unrecognised family
  fails closed with an explicit unsupported-family error and a body shape is
  never guessed.
* Bedrock is partner-operated and priced separately. The shipped pricing
  snapshot is an unconfirmed placeholder and must be replaced before live use.
* A model result is a proposal. Nothing here creates an ``EpistemicWarrant``,
  and output that does not validate against the requested canonical schema is
  reported as ``MALFORMED`` rather than returned as a success.

The module is inert on import: no clock, no credential resolution, no socket,
no third-party module. Signing is standard library only, via
:mod:`.aws_sigv4`, whose canonicalisation is pinned against AWS's published
worked examples.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, MutableMapping, Protocol
from urllib.parse import quote

from . import PHASE2_SCHEMA_VERSION
from .aws_sigv4 import (
    AwsCredentials,
    SIGV4_IMPLEMENTATION_VERSION,
    SigV4Error,
    SignedRequest,
    sign_request,
)
from .env_file import load_provider_credentials
from .model_gateway import (
    DIAGNOSTIC_TEXT_LIMIT_BYTES,
    StructuredOutputError,
    _bounded_utf8,
    _validate_canonical_schema,
    redact_secrets,
)
from .records import (
    ModelRequest,
    ModelResult,
    ModelResultStatus,
    ModelUsage,
    ProviderFailureDiagnostic,
    ProviderSchemaPreparation,
)
from .serialization import canonical_json, sha256_bytes


BEDROCK_ADAPTER_VERSION = "bedrock-invoke-model-adapter/1.0.0"
BEDROCK_PROVIDER = "bedrock"
BEDROCK_SIGNING_SERVICE = "bedrock"
BEDROCK_PRICING_SOURCE = "https://aws.amazon.com/bedrock/pricing/"
BEDROCK_INPUT_TOKEN_HEADER = "x-amzn-bedrock-input-token-count"
BEDROCK_OUTPUT_TOKEN_HEADER = "x-amzn-bedrock-output-token-count"
BEDROCK_REQUEST_ID_HEADER = "x-amzn-requestid"
BEDROCK_ERROR_TYPE_HEADER = "x-amzn-errortype"

DEFAULT_MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_ALLOWED_RESPONSE_BYTES = 32 * 1024 * 1024

# Cross-region inference profile prefixes. They select routing, not a vendor,
# so they are stripped before family resolution and kept on the wire.
_GEOGRAPHY_PREFIXES = ("us-gov.", "us.", "eu.", "apac.", "jp.", "au.", "ca.")
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_REGION = re.compile(r"^[a-z0-9-]{1,64}$")

SCHEMA_INSTRUCTION = (
    "Reply with exactly one JSON object and nothing else: no prose, no "
    "markdown fence, no trailing text. The object must validate against this "
    "JSON Schema:"
)


class BedrockConfigurationError(ValueError):
    """The adapter is not usable as configured. Always fails closed."""


class UnsupportedModelFamilyError(BedrockConfigurationError):
    """The model id maps to no confidently implemented Bedrock body shape."""


class BedrockCredentialError(BedrockConfigurationError):
    """A required credential or the required region is absent."""


class BedrockTransportTimeout(Exception):
    """The bounded transport exceeded the caller's deadline."""


class BedrockTransportFailure(Exception):
    """The bounded transport failed before a complete response was read."""


# --------------------------------------------------------------------------
# Transport port
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class BedrockHttpRequest:
    method: str
    url: str
    headers: tuple[tuple[str, str], ...]
    body: bytes
    timeout_milliseconds: int
    max_response_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BedrockHttpResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        for key, value in self.headers:
            if key.lower() == lowered:
                return value
        return None


class BedrockTransport(Protocol):
    def send(self, request: BedrockHttpRequest) -> BedrockHttpResponse: ...


class HttpsBedrockTransport:
    """Single bounded HTTPS request. Networking is imported inside ``send``.

    The ordinary offline path never constructs this class, and the repository
    invariant that no module imports a network module at module scope is why the
    imports live in the method body.
    """

    def send(self, request: BedrockHttpRequest) -> BedrockHttpResponse:
        import http.client
        import ssl
        from urllib.parse import urlsplit

        parts = urlsplit(request.url)
        if parts.scheme != "https" or not parts.hostname:
            raise BedrockTransportFailure("bedrock_endpoint_not_https")
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        connection = http.client.HTTPSConnection(
            parts.hostname,
            port=parts.port or 443,
            timeout=max(0.001, request.timeout_milliseconds / 1000),
            context=context,
        )
        try:
            connection.request(
                request.method, target, body=request.body,
                headers=dict(request.headers),
            )
            response = connection.getresponse()
            body = response.read(request.max_response_bytes + 1)
            if len(body) > request.max_response_bytes:
                raise BedrockTransportFailure("bedrock_response_body_too_large")
            headers = tuple(
                (str(name).lower(), str(value)) for name, value in response.getheaders()
            )
            return BedrockHttpResponse(
                status_code=int(response.status), headers=headers, body=body,
            )
        except TimeoutError as error:
            raise BedrockTransportTimeout("bedrock_transport_timeout") from error
        except BedrockTransportFailure:
            raise
        except OSError as error:
            # An OSError message can echo the host but never the signature or a
            # credential; the caller still routes it through redaction.
            raise BedrockTransportFailure("bedrock_transport_failed") from error
        finally:
            try:
                connection.close()
            except Exception:
                pass


# --------------------------------------------------------------------------
# Per-family mapping
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class FamilyPrompt:
    """Provider-neutral prompt material handed to a family body builder."""

    system_text: str
    user_text: str
    max_output_tokens: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FamilyOutcome:
    """What a family response parser could actually establish.

    ``text`` is a candidate string, never a validated result. ``truncated``
    means the provider stopped for a length reason, which is reported as
    ``INCOMPLETE`` rather than being passed off as a completion.
    """

    text: str | None
    stop_reason: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    refusal: str | None = None
    truncated: bool = False
    parse_error: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelFamily:
    family_id: str
    prefixes: tuple[str, ...]
    documentation: str
    build_body: Callable[[FamilyPrompt], dict[str, Any]]
    parse_response: Callable[[dict[str, Any]], FamilyOutcome]
    reports_usage_in_body: bool


def _combined_prompt(prompt: FamilyPrompt) -> str:
    return f"{prompt.system_text}\n\n{prompt.user_text}"


def _text_or_error(value: Any, where: str) -> tuple[str | None, str | None]:
    if isinstance(value, str):
        return value, None
    return None, f"{where} is not a string"


# -- Anthropic on Bedrock ---------------------------------------------------
# Deliberately hand-mapped rather than delegated to the Anthropic SDK's Bedrock
# client. Two reasons. First, `tests/test_repository_invariants.py` asserts the
# exact set of lazily imported third-party modules, so adding an SDK is an
# architecture change owned by a different change than this one. Second, the
# direct Anthropic gateway is being built separately; routing Bedrock through
# the Anthropic SDK would put one vendor's family on a different transport,
# error taxonomy, and credential path from the other seven families here, which
# defeats the point of a single audited Bedrock surface.
ANTHROPIC_BEDROCK_VERSION = "bedrock-2023-05-31"


def _anthropic_body(prompt: FamilyPrompt) -> dict[str, Any]:
    return {
        "anthropic_version": ANTHROPIC_BEDROCK_VERSION,
        "max_tokens": prompt.max_output_tokens,
        "temperature": 0,
        "system": prompt.system_text,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": prompt.user_text}]}
        ],
    }


def _anthropic_parse(body: dict[str, Any]) -> FamilyOutcome:
    stop_reason = body.get("stop_reason")
    stop = stop_reason if isinstance(stop_reason, str) else None
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    input_tokens = _optional_count(usage.get("input_tokens"))
    output_tokens = _optional_count(usage.get("output_tokens"))
    if stop == "refusal":
        return FamilyOutcome(
            text=None, stop_reason=stop, refusal="provider refusal",
            input_tokens=input_tokens, output_tokens=output_tokens,
        )
    content = body.get("content")
    if not isinstance(content, list):
        return FamilyOutcome(
            text=None, stop_reason=stop, parse_error="content is not an array",
            input_tokens=input_tokens, output_tokens=output_tokens,
        )
    pieces: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            return FamilyOutcome(
                text=None, stop_reason=stop, parse_error="content item is not an object",
                input_tokens=input_tokens, output_tokens=output_tokens,
            )
        if item.get("type") != "text":
            continue
        piece, error = _text_or_error(item.get("text"), "content[].text")
        if error is not None:
            return FamilyOutcome(
                text=None, stop_reason=stop, parse_error=error,
                input_tokens=input_tokens, output_tokens=output_tokens,
            )
        pieces.append(piece or "")
    return FamilyOutcome(
        text="".join(pieces) if pieces else None,
        stop_reason=stop,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        truncated=stop == "max_tokens",
        parse_error=None if pieces else "response contained no text content",
    )


# -- Amazon Nova -----------------------------------------------------------


def _nova_body(prompt: FamilyPrompt) -> dict[str, Any]:
    return {
        "schemaVersion": "messages-v1",
        "system": [{"text": prompt.system_text}],
        "messages": [{"role": "user", "content": [{"text": prompt.user_text}]}],
        "inferenceConfig": {"maxNewTokens": prompt.max_output_tokens, "temperature": 0},
    }


def _nova_parse(body: dict[str, Any]) -> FamilyOutcome:
    stop_reason = body.get("stopReason")
    stop = stop_reason if isinstance(stop_reason, str) else None
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    input_tokens = _optional_count(usage.get("inputTokens"))
    output_tokens = _optional_count(usage.get("outputTokens"))
    output = body.get("output")
    message = output.get("message") if isinstance(output, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return FamilyOutcome(
            text=None, stop_reason=stop,
            parse_error="output.message.content is not an array",
            input_tokens=input_tokens, output_tokens=output_tokens,
        )
    pieces: list[str] = []
    for item in content:
        if not isinstance(item, dict) or "text" not in item:
            continue
        piece, error = _text_or_error(item.get("text"), "output.message.content[].text")
        if error is not None:
            return FamilyOutcome(
                text=None, stop_reason=stop, parse_error=error,
                input_tokens=input_tokens, output_tokens=output_tokens,
            )
        pieces.append(piece or "")
    return FamilyOutcome(
        text="".join(pieces) if pieces else None,
        stop_reason=stop,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        truncated=stop == "max_tokens",
        parse_error=None if pieces else "response contained no text content",
    )


# -- Amazon Titan Text -----------------------------------------------------


def _titan_text_body(prompt: FamilyPrompt) -> dict[str, Any]:
    return {
        "inputText": _combined_prompt(prompt),
        "textGenerationConfig": {
            "maxTokenCount": prompt.max_output_tokens,
            "temperature": 0,
            "stopSequences": [],
        },
    }


def _titan_text_parse(body: dict[str, Any]) -> FamilyOutcome:
    input_tokens = _optional_count(body.get("inputTextTokenCount"))
    results = body.get("results")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return FamilyOutcome(
            text=None, stop_reason=None, input_tokens=input_tokens,
            parse_error="results is not a non-empty array of objects",
        )
    first = results[0]
    reason = first.get("completionReason")
    stop = reason if isinstance(reason, str) else None
    output_tokens = _optional_count(first.get("tokenCount"))
    if stop == "CONTENT_FILTERED":
        return FamilyOutcome(
            text=None, stop_reason=stop, refusal="content filtered by provider",
            input_tokens=input_tokens, output_tokens=output_tokens,
        )
    text, error = _text_or_error(first.get("outputText"), "results[0].outputText")
    return FamilyOutcome(
        text=text, stop_reason=stop, input_tokens=input_tokens,
        output_tokens=output_tokens, truncated=stop == "LENGTH", parse_error=error,
    )


# -- Meta Llama 3 family ---------------------------------------------------


def _llama3_prompt(prompt: FamilyPrompt) -> str:
    return (
        "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
        f"{prompt.system_text}<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"{prompt.user_text}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def _llama3_body(prompt: FamilyPrompt) -> dict[str, Any]:
    return {
        "prompt": _llama3_prompt(prompt),
        "max_gen_len": prompt.max_output_tokens,
        "temperature": 0,
    }


def _llama3_parse(body: dict[str, Any]) -> FamilyOutcome:
    reason = body.get("stop_reason")
    stop = reason if isinstance(reason, str) else None
    text, error = _text_or_error(body.get("generation"), "generation")
    return FamilyOutcome(
        text=text,
        stop_reason=stop,
        input_tokens=_optional_count(body.get("prompt_token_count")),
        output_tokens=_optional_count(body.get("generation_token_count")),
        truncated=stop == "length",
        parse_error=error,
    )


# -- Mistral prompt-completion family --------------------------------------


def _mistral_body(prompt: FamilyPrompt) -> dict[str, Any]:
    return {
        "prompt": f"<s>[INST] {_combined_prompt(prompt)} [/INST]",
        "max_tokens": prompt.max_output_tokens,
        "temperature": 0,
    }


def _mistral_parse(body: dict[str, Any]) -> FamilyOutcome:
    outputs = body.get("outputs")
    if not isinstance(outputs, list) or not outputs or not isinstance(outputs[0], dict):
        return FamilyOutcome(
            text=None, stop_reason=None,
            parse_error="outputs is not a non-empty array of objects",
        )
    first = outputs[0]
    reason = first.get("stop_reason")
    stop = reason if isinstance(reason, str) else None
    text, error = _text_or_error(first.get("text"), "outputs[0].text")
    return FamilyOutcome(
        text=text, stop_reason=stop, truncated=stop == "length", parse_error=error,
    )


# -- AI21 Jamba ------------------------------------------------------------


def _jamba_body(prompt: FamilyPrompt) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": prompt.system_text},
            {"role": "user", "content": prompt.user_text},
        ],
        "max_tokens": prompt.max_output_tokens,
        "temperature": 0,
    }


def _jamba_parse(body: dict[str, Any]) -> FamilyOutcome:
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    input_tokens = _optional_count(usage.get("prompt_tokens"))
    output_tokens = _optional_count(usage.get("completion_tokens"))
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return FamilyOutcome(
            text=None, stop_reason=None, input_tokens=input_tokens,
            output_tokens=output_tokens,
            parse_error="choices is not a non-empty array of objects",
        )
    first = choices[0]
    reason = first.get("finish_reason")
    stop = reason if isinstance(reason, str) else None
    message = first.get("message")
    if not isinstance(message, dict):
        return FamilyOutcome(
            text=None, stop_reason=stop, input_tokens=input_tokens,
            output_tokens=output_tokens,
            parse_error="choices[0].message is not an object",
        )
    text, error = _text_or_error(message.get("content"), "choices[0].message.content")
    return FamilyOutcome(
        text=text, stop_reason=stop, input_tokens=input_tokens,
        output_tokens=output_tokens, truncated=stop == "length", parse_error=error,
    )


# -- Cohere Command R chat -------------------------------------------------


def _cohere_chat_body(prompt: FamilyPrompt) -> dict[str, Any]:
    return {
        "message": _combined_prompt(prompt),
        "chat_history": [],
        "max_tokens": prompt.max_output_tokens,
        "temperature": 0,
    }


def _cohere_chat_parse(body: dict[str, Any]) -> FamilyOutcome:
    reason = body.get("finish_reason")
    stop = reason if isinstance(reason, str) else None
    text, error = _text_or_error(body.get("text"), "text")
    return FamilyOutcome(
        text=text, stop_reason=stop, truncated=stop == "MAX_TOKENS", parse_error=error,
    )


# -- Cohere Command text generation ---------------------------------------


def _cohere_generate_body(prompt: FamilyPrompt) -> dict[str, Any]:
    return {
        "prompt": _combined_prompt(prompt),
        "max_tokens": prompt.max_output_tokens,
        "temperature": 0,
    }


def _cohere_generate_parse(body: dict[str, Any]) -> FamilyOutcome:
    generations = body.get("generations")
    if (
        not isinstance(generations, list)
        or not generations
        or not isinstance(generations[0], dict)
    ):
        return FamilyOutcome(
            text=None, stop_reason=None,
            parse_error="generations is not a non-empty array of objects",
        )
    first = generations[0]
    reason = first.get("finish_reason")
    stop = reason if isinstance(reason, str) else None
    text, error = _text_or_error(first.get("text"), "generations[0].text")
    return FamilyOutcome(
        text=text, stop_reason=stop, truncated=stop == "MAX_TOKENS", parse_error=error,
    )


def _optional_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


# Longest prefix wins, so a narrower id is never captured by a broader vendor
# entry. Every prefix below is a shape the adapter can construct and parse; the
# vendors' other shapes are refused in `_UNSUPPORTED_PREFIXES`.
MODEL_FAMILIES: tuple[ModelFamily, ...] = (
    ModelFamily(
        family_id="anthropic.messages",
        prefixes=("anthropic.",),
        documentation="Anthropic Claude Messages API on Bedrock InvokeModel",
        build_body=_anthropic_body,
        parse_response=_anthropic_parse,
        reports_usage_in_body=True,
    ),
    ModelFamily(
        family_id="amazon.nova.messages",
        prefixes=("amazon.nova-",),
        documentation="Amazon Nova messages-v1 InvokeModel body",
        build_body=_nova_body,
        parse_response=_nova_parse,
        reports_usage_in_body=True,
    ),
    ModelFamily(
        family_id="amazon.titan.text",
        prefixes=("amazon.titan-text-", "amazon.titan-tg1-"),
        documentation="Amazon Titan Text inputText/textGenerationConfig body",
        build_body=_titan_text_body,
        parse_response=_titan_text_parse,
        reports_usage_in_body=True,
    ),
    ModelFamily(
        family_id="meta.llama3.prompt",
        prefixes=("meta.llama3",),
        documentation="Meta Llama 3 prompt/max_gen_len body with the Llama 3 chat template",
        build_body=_llama3_body,
        parse_response=_llama3_parse,
        reports_usage_in_body=True,
    ),
    ModelFamily(
        family_id="mistral.prompt",
        prefixes=(
            "mistral.mistral-7b-instruct",
            "mistral.mixtral-8x7b-instruct",
            "mistral.mistral-small-2402",
            "mistral.mistral-large-2402",
        ),
        documentation="Mistral prompt/outputs InvokeModel body with [INST] delimiters",
        build_body=_mistral_body,
        parse_response=_mistral_parse,
        reports_usage_in_body=False,
    ),
    ModelFamily(
        family_id="ai21.jamba.chat",
        prefixes=("ai21.jamba-",),
        documentation="AI21 Jamba messages/choices InvokeModel body",
        build_body=_jamba_body,
        parse_response=_jamba_parse,
        reports_usage_in_body=True,
    ),
    ModelFamily(
        family_id="cohere.command-r.chat",
        prefixes=("cohere.command-r",),
        documentation="Cohere Command R chat InvokeModel body",
        build_body=_cohere_chat_body,
        parse_response=_cohere_chat_parse,
        reports_usage_in_body=False,
    ),
    ModelFamily(
        family_id="cohere.command.generate",
        prefixes=("cohere.command-text", "cohere.command-light-text"),
        documentation="Cohere Command text-generation InvokeModel body",
        build_body=_cohere_generate_body,
        parse_response=_cohere_generate_parse,
        reports_usage_in_body=False,
    ),
)

# Model ids that exist on Bedrock and are deliberately refused, each with the
# reason. Naming them separates "we know this exists and will not guess its
# body" from "we have never heard of this vendor", and both fail closed.
_UNSUPPORTED_PREFIXES: tuple[tuple[str, str], ...] = (
    ("amazon.titan-embed", "embedding model, not a text-generation body shape"),
    ("amazon.titan-image", "image model, not a text-generation body shape"),
    ("amazon.nova-canvas", "image model, not a text-generation body shape"),
    ("amazon.nova-reel", "video model, not a text-generation body shape"),
    ("amazon.nova-sonic", "speech model, not a text-generation body shape"),
    ("amazon.rerank", "rerank model, not a text-generation body shape"),
    ("cohere.embed", "embedding model, not a text-generation body shape"),
    ("cohere.rerank", "rerank model, not a text-generation body shape"),
    ("meta.llama2", "Llama 2 uses a different chat template; not implemented"),
    ("meta.llama4", "Llama 4 uses a different chat template; not implemented"),
    ("mistral.pixtral", "multimodal chat-completions body; not implemented"),
    ("mistral.mistral-large-2407", "chat-completions body differs from the prompt body"),
    ("mistral.mistral-large-2411", "chat-completions body differs from the prompt body"),
    ("ai21.j2", "legacy Jurassic-2 prompt body; not implemented"),
    ("stability.", "image model, not a text-generation body shape"),
    ("luma.", "video model, not a text-generation body shape"),
    ("twelvelabs.", "video model, not a text-generation body shape"),
)


@dataclass(frozen=True, slots=True, kw_only=True)
class FamilyResolution:
    family: ModelFamily
    model_identifier: str
    routing_prefix: str
    matched_prefix: str


def resolve_model_family(model_identifier: str) -> FamilyResolution:
    """Resolve a Bedrock model id to a mapped family, or fail closed.

    Never returns a default. An unmapped id raises
    :class:`UnsupportedModelFamilyError` so no request can be built with a
    guessed body shape.
    """
    if not isinstance(model_identifier, str) or _MODEL_ID.fullmatch(model_identifier) is None:
        raise BedrockConfigurationError(
            "model_identifier must match "
            r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$ "
            "(Bedrock model ARNs and inference-profile ARNs are not supported)"
        )
    routing_prefix = ""
    remainder = model_identifier
    for prefix in _GEOGRAPHY_PREFIXES:
        if remainder.startswith(prefix):
            routing_prefix = prefix
            remainder = remainder[len(prefix):]
            break
    for prefix, reason in sorted(_UNSUPPORTED_PREFIXES, key=lambda item: -len(item[0])):
        if remainder.startswith(prefix):
            raise UnsupportedModelFamilyError(
                f"unsupported model family for {model_identifier!r}: {reason}; "
                f"supported families are {', '.join(supported_family_ids())}"
            )
    best: tuple[int, ModelFamily, str] | None = None
    for family in MODEL_FAMILIES:
        for prefix in family.prefixes:
            if remainder.startswith(prefix) and (best is None or len(prefix) > best[0]):
                best = (len(prefix), family, prefix)
    if best is None:
        raise UnsupportedModelFamilyError(
            f"unsupported model family for {model_identifier!r}: no mapped "
            "Bedrock request body shape for this model-id prefix; supported "
            f"families are {', '.join(supported_family_ids())}"
        )
    return FamilyResolution(
        family=best[1], model_identifier=model_identifier,
        routing_prefix=routing_prefix, matched_prefix=best[2],
    )


def supported_family_ids() -> tuple[str, ...]:
    return tuple(sorted(family.family_id for family in MODEL_FAMILIES))


def supported_model_prefixes() -> tuple[str, ...]:
    return tuple(sorted(prefix for family in MODEL_FAMILIES for prefix in family.prefixes))


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class BedrockProviderConfig:
    schema_version: str = PHASE2_SCHEMA_VERSION
    model_identifier: str
    # Region is required. It may come from here or from AWS_REGION, but never
    # from a default: a wrong region silently changes jurisdiction and price.
    region: str | None = None
    signing_service: str = BEDROCK_SIGNING_SERVICE
    endpoint_host_template: str = "bedrock-runtime.{region}.amazonaws.com"
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    capabilities: tuple[str, ...] = field(
        default=("invoke_model", "prompt_embedded_schema", "sigv4")
    )

    def __post_init__(self) -> None:
        resolve_model_family(self.model_identifier)
        if self.region is not None and _REGION.fullmatch(self.region) is None:
            raise BedrockConfigurationError("region must be a lowercase AWS region identifier")
        if not self.signing_service or _REGION.fullmatch(self.signing_service) is None:
            raise BedrockConfigurationError("signing_service must be a lowercase identifier")
        if "{region}" not in self.endpoint_host_template:
            raise BedrockConfigurationError("endpoint_host_template must contain {region}")
        if (
            isinstance(self.max_response_bytes, bool)
            or not isinstance(self.max_response_bytes, int)
            or not 1 <= self.max_response_bytes <= MAX_ALLOWED_RESPONSE_BYTES
        ):
            raise BedrockConfigurationError("max_response_bytes is out of bounds")


# --------------------------------------------------------------------------
# Error classification
# --------------------------------------------------------------------------

# Retryable means "the same request may succeed later without human action".
# Anything needing a permission, quota, region, or body change is fatal.
_RETRYABLE_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ModelNotReadyException",
        "ModelTimeoutException",
        "ServiceUnavailableException",
        "InternalServerException",
        "InternalFailure",
        "RequestTimeout",
        "RequestTimeoutException",
        "SlowDown",
        "PriorRequestNotComplete",
    }
)
_FATAL_ERROR_CODES = frozenset(
    {
        "AccessDeniedException",
        "ValidationException",
        "ResourceNotFoundException",
        "ModelErrorException",
        "ModelStreamErrorException",
        "SerializationException",
        "ServiceQuotaExceededException",
        "IncompleteSignature",
        "InvalidSignatureException",
        "MissingAuthenticationToken",
        "ExpiredTokenException",
        "UnrecognizedClientException",
        "InvalidClientTokenId",
        "SignatureDoesNotMatch",
        "UnsupportedOperation",
        "AccessDeniedByBedrockGuardrail",
    }
)
_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504, 509})


def classify_bedrock_error(
    *, status_code: int, error_code: str | None
) -> tuple[bool, str]:
    """Return ``(retryable, retry_classification)``.

    The AWS error code wins over the HTTP status, because Bedrock returns
    ``ThrottlingException`` under several statuses and ``ValidationException``
    under 400 only sometimes.
    """
    code = (error_code or "").strip()
    if code in _RETRYABLE_ERROR_CODES:
        return True, f"retryable:{code}"
    if code in _FATAL_ERROR_CODES:
        return False, f"fatal:{code}"
    if status_code in _RETRYABLE_STATUS_CODES:
        return True, f"retryable:http_{status_code}"
    if code:
        return False, f"fatal:{code}"
    return False, f"fatal:http_{status_code}"


def extract_error_code(
    *, headers: tuple[tuple[str, str], ...], body: Any
) -> str | None:
    """AWS reports the error code in a header, a body field, or both."""
    for name, value in headers:
        if name.lower() == BEDROCK_ERROR_TYPE_HEADER:
            # The header is `Code[:optional-qualifier]`.
            return str(value).split(":", 1)[0].strip() or None
    if isinstance(body, dict):
        for key in ("__type", "code", "Code", "errorType"):
            value = body.get(key)
            if isinstance(value, str) and value:
                # Shapes may be namespaced, e.g. `com.amazon.coral#Foo`.
                return value.rsplit("#", 1)[-1].split(":", 1)[0].strip() or None
    return None


# --------------------------------------------------------------------------
# Gateway
# --------------------------------------------------------------------------


class BedrockInvokeGateway:
    """``ModelGateway`` over Bedrock ``InvokeModel`` with per-family mapping."""

    def __init__(
        self,
        config: BedrockProviderConfig,
        *,
        transport: BedrockTransport | None = None,
        environment: MutableMapping[str, str] | None = None,
        env_file_path: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config
        # Resolved eagerly: a gateway for an unmapped family cannot exist.
        self.resolution = resolve_model_family(config.model_identifier)
        self._transport = transport
        self._environment = environment
        self._env_file_path = env_file_path
        self._clock = clock

    # -- schema boundary ---------------------------------------------------

    def prepare(self, request: ModelRequest) -> ProviderSchemaPreparation:
        """Record how the canonical schema is conveyed. No native strict mode.

        Bedrock ``InvokeModel`` exposes no cross-vendor strict JSON-schema
        response format, so the canonical schema is embedded in the prompt and
        the response is validated locally afterwards. The projection is the
        identity, which is exactly the point: nothing is dropped or relaxed, and
        the provider is given no authority over the contract.
        """
        try:
            schema = json.loads(request.response_schema)
        except json.JSONDecodeError as error:
            raise BedrockConfigurationError(
                f"response_schema is not valid JSON: {error.msg}"
            ) from error
        if not isinstance(schema, dict):
            raise BedrockConfigurationError("response_schema must be a JSON object")
        canonical = canonical_json(schema)
        manifest = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "adapter_version": BEDROCK_ADAPTER_VERSION,
            "provider": BEDROCK_PROVIDER,
            "family_id": self.resolution.family.family_id,
            "strategy": "prompt_embedded_canonical_schema",
            "native_structured_output": False,
            "projection": "identity",
            "transformations": [],
        }
        report = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "provider": BEDROCK_PROVIDER,
            "family_id": self.resolution.family.family_id,
            "native_strict_schema_supported": False,
            "canonical_validation_required": True,
            "notes": [
                "Bedrock InvokeModel has no cross-vendor strict response format.",
                "The canonical schema is embedded in the prompt verbatim.",
                "Provider output is validated against the canonical schema locally; "
                "a failure is reported as malformed, never as a success.",
            ],
        }
        return ProviderSchemaPreparation(
            provider=BEDROCK_PROVIDER,
            canonical_schema_hash=sha256_bytes(canonical.encode("utf-8")),
            provider_schema_hash=sha256_bytes(canonical.encode("utf-8")),
            provider_schema_json=canonical,
            transformation_manifest_json=canonical_json(manifest),
            compatibility_report_json=canonical_json(report),
            compatibility_report_text=(
                f"provider={BEDROCK_PROVIDER} family={self.resolution.family.family_id}\n"
                "native strict schema: unsupported\n"
                "canonical schema conveyance: prompt-embedded, projection=identity\n"
                "canonical post-response validation: required\n"
            ),
        )

    # -- credentials and endpoint -----------------------------------------

    def _values(self) -> MutableMapping[str, str]:
        return os.environ if self._environment is None else self._environment

    def resolve_region(self) -> str:
        values = self._values()
        load_provider_credentials(self._env_file_path, environment=values)
        region = self.config.region or values.get("AWS_REGION") or ""
        region = region.strip()
        if not region:
            raise BedrockCredentialError(
                "AWS_REGION is not configured; Bedrock requires an explicit region "
                "(set AWS_REGION or BedrockProviderConfig.region). No region is "
                "defaulted, because the region selects the endpoint, the data "
                "jurisdiction, and the price."
            )
        if _REGION.fullmatch(region) is None:
            raise BedrockCredentialError(
                "AWS_REGION is not a valid lowercase AWS region identifier"
            )
        return region

    def resolve_credentials(self) -> AwsCredentials:
        values = self._values()
        load_provider_credentials(self._env_file_path, environment=values)
        access_key_id = (values.get("AWS_ACCESS_KEY_ID") or "").strip()
        secret_access_key = values.get("AWS_SECRET_ACCESS_KEY") or ""
        session_token = values.get("AWS_SESSION_TOKEN") or ""
        missing = [
            name
            for name, value in (
                ("AWS_ACCESS_KEY_ID", access_key_id),
                ("AWS_SECRET_ACCESS_KEY", secret_access_key),
            )
            if not value
        ]
        if missing:
            raise BedrockCredentialError(
                f"{' and '.join(missing)} is not configured"
            )
        try:
            return AwsCredentials(
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                session_token=session_token or None,
            )
        except SigV4Error as error:
            # The message is generated from field names only, never a value.
            raise BedrockCredentialError(str(error)) from error

    def endpoint_url(self, region: str) -> str:
        host = self.config.endpoint_host_template.format(region=region)
        # The model id may contain `:`; it is a single path segment, so it is
        # percent-encoded with no safe characters. SigV4 then encodes the
        # already-encoded path a second time, which is the documented non-S3
        # rule and is what `aws_sigv4.canonical_uri_from_path` implements.
        return f"https://{host}/model/{quote(self.config.model_identifier, safe='')}/invoke"

    # -- request construction ---------------------------------------------

    def build_prompt(self, request: ModelRequest, preparation: ProviderSchemaPreparation) -> FamilyPrompt:
        return FamilyPrompt(
            system_text=(
                f"{request.template_text}\n\n{SCHEMA_INSTRUCTION}\n"
                f"{preparation.provider_schema_json}"
            ),
            user_text=request.serialized_context,
            max_output_tokens=request.max_output_tokens,
        )

    def build_body_bytes(self, prompt: FamilyPrompt) -> bytes:
        body = self.resolution.family.build_body(prompt)
        if not isinstance(body, dict):
            raise BedrockConfigurationError("family body builder did not return an object")
        return canonical_json(body).encode("utf-8")

    def sign(
        self, *, url: str, body: bytes, region: str, credentials: AwsCredentials, moment: datetime
    ) -> SignedRequest:
        return sign_request(
            method="POST",
            url=url,
            headers=(("Content-Type", "application/json"), ("Accept", "application/json")),
            body=body,
            credentials=credentials,
            region=region,
            service=self.config.signing_service,
            moment=moment,
            double_encode_path=True,
        )

    # -- completion --------------------------------------------------------

    def complete(
        self, request: ModelRequest, preparation: ProviderSchemaPreparation | None = None,
    ) -> ModelResult:
        prepared = preparation or self.prepare(request)
        # Defence in depth: the constructor already refused an unmapped family.
        resolve_model_family(self.config.model_identifier)
        region = self.resolve_region()
        credentials = self.resolve_credentials()
        url = self.endpoint_url(region)
        body = self.build_body_bytes(self.build_prompt(request, prepared))
        moment = (self._clock or _utc_now)()
        signed = self.sign(
            url=url, body=body, region=region, credentials=credentials, moment=moment
        )
        secrets = credentials.secret_material + (signed.signature, signed.authorization)
        transport = self._transport or HttpsBedrockTransport()
        http_request = BedrockHttpRequest(
            method=signed.method,
            url=signed.url,
            headers=signed.headers,
            body=signed.body,
            timeout_milliseconds=request.timeout_milliseconds,
            max_response_bytes=self.config.max_response_bytes,
        )
        try:
            response = transport.send(http_request)
        except BedrockTransportTimeout:
            return self._failure(
                ModelResultStatus.TIMED_OUT, "retryable:timeout", prepared,
            )
        except BedrockTransportFailure:
            return self._failure(
                ModelResultStatus.FAILED, "retryable:transport", prepared,
            )
        if not isinstance(response, BedrockHttpResponse):
            return self._failure(
                ModelResultStatus.FAILED, "fatal:transport_contract_violated", prepared,
            )
        request_id = response.header(BEDROCK_REQUEST_ID_HEADER)
        if response.status_code != 200:
            parsed = _parse_json_or_text(response.body)
            error_code = extract_error_code(headers=response.headers, body=parsed)
            _, retry = classify_bedrock_error(
                status_code=response.status_code, error_code=error_code
            )
            diagnostic = self._diagnostic(
                response=response,
                parsed=parsed,
                error_code=error_code,
                secrets=secrets,
                prepared=prepared,
                url=url,
                exception_class="BedrockErrorResponse",
            )
            return self._failure(
                ModelResultStatus.FAILED, retry, prepared,
                provider_request_id=request_id, provider_failure=diagnostic,
            )
        try:
            decoded = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._failure(
                ModelResultStatus.MALFORMED, "fatal:response_not_json", prepared,
                provider_request_id=request_id,
            )
        if not isinstance(decoded, dict):
            return self._failure(
                ModelResultStatus.MALFORMED, "fatal:response_not_object", prepared,
                provider_request_id=request_id,
            )
        outcome = self.resolution.family.parse_response(decoded)
        usage = self._usage(outcome, response)
        if outcome.refusal is not None:
            return self._result(
                ModelResultStatus.REFUSED, prepared, usage=usage,
                refusal=outcome.refusal[:2000],
                retry="not_retryable:refusal", provider_request_id=request_id,
            )
        if outcome.truncated:
            return self._result(
                ModelResultStatus.INCOMPLETE, prepared, usage=usage,
                retry="not_retryable:incomplete_response",
                provider_request_id=request_id,
                incomplete_reason=(outcome.stop_reason or "length")[:2000],
            )
        if outcome.parse_error is not None or outcome.text is None:
            return self._result(
                ModelResultStatus.MALFORMED, prepared, usage=usage,
                retry="fatal:family_response_shape_unexpected",
                provider_request_id=request_id,
            )
        if usage.usage_source != "api_reported":
            # Budget accounting is not optional, and a call whose cost cannot be
            # attributed must not be recorded as a success.
            return self._result(
                ModelResultStatus.MALFORMED, prepared, usage=usage,
                retry="fatal:missing_usage", provider_request_id=request_id,
            )
        try:
            _validate_against_canonical_schema(outcome.text, prepared.provider_schema_json)
        except StructuredOutputError:
            return self._result(
                ModelResultStatus.MALFORMED, prepared, usage=usage,
                retry="fatal:output_failed_canonical_schema",
                provider_request_id=request_id,
            )
        return self._result(
            ModelResultStatus.SUCCEEDED, prepared, usage=usage,
            structured_output=outcome.text, retry="none",
            provider_request_id=request_id,
        )

    # -- helpers -----------------------------------------------------------

    def _usage(self, outcome: FamilyOutcome, response: BedrockHttpResponse) -> ModelUsage:
        input_tokens = outcome.input_tokens
        output_tokens = outcome.output_tokens
        if input_tokens is None:
            input_tokens = _header_count(response.header(BEDROCK_INPUT_TOKEN_HEADER))
        if output_tokens is None:
            output_tokens = _header_count(response.header(BEDROCK_OUTPUT_TOKEN_HEADER))
        if input_tokens is None or output_tokens is None:
            return ModelUsage(
                input_tokens=0, output_tokens=0, total_tokens=0,
                usage_source="unavailable",
            )
        return ModelUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            usage_source="api_reported",
        )

    def _result(
        self,
        status: ModelResultStatus,
        prepared: ProviderSchemaPreparation,
        *,
        usage: ModelUsage,
        retry: str,
        structured_output: str | None = None,
        refusal: str | None = None,
        provider_request_id: str | None = None,
        incomplete_reason: str | None = None,
        provider_failure: ProviderFailureDiagnostic | None = None,
    ) -> ModelResult:
        return ModelResult(
            status=status,
            provider=BEDROCK_PROVIDER,
            model_identifier=self.config.model_identifier,
            capabilities=self.config.capabilities,
            structured_output=structured_output,
            declared_rationale=None,
            refusal=refusal,
            usage=usage,
            retry_classification=retry,
            provider_request_id=provider_request_id,
            incomplete_reason=incomplete_reason,
            provider_failure=provider_failure,
            provider_schema_hash=prepared.provider_schema_hash,
            projection_manifest_hash=sha256_bytes(
                prepared.transformation_manifest_json.encode("utf-8")
            ),
            compatibility_report_hash=sha256_bytes(
                prepared.compatibility_report_json.encode("utf-8")
            ),
        )

    def _failure(
        self,
        status: ModelResultStatus,
        retry: str,
        prepared: ProviderSchemaPreparation,
        *,
        provider_request_id: str | None = None,
        provider_failure: ProviderFailureDiagnostic | None = None,
    ) -> ModelResult:
        return self._result(
            status, prepared,
            usage=ModelUsage(
                input_tokens=0, output_tokens=0, total_tokens=0,
                usage_source="unavailable",
            ),
            retry=retry,
            provider_request_id=provider_request_id,
            provider_failure=provider_failure,
        )

    def _diagnostic(
        self,
        *,
        response: BedrockHttpResponse,
        parsed: Any,
        error_code: str | None,
        secrets: tuple[str, ...],
        prepared: ProviderSchemaPreparation,
        url: str,
        exception_class: str,
    ) -> ProviderFailureDiagnostic:
        sanitized = redact_secrets(parsed, secrets)
        rendered = sanitized if isinstance(sanitized, str) else canonical_json(sanitized)
        preview, truncated = _bounded_utf8(rendered, DIAGNOSTIC_TEXT_LIMIT_BYTES)
        message = parsed.get("message") or parsed.get("Message") if isinstance(parsed, dict) else None
        sanitized_message = (
            redact_secrets(str(message), secrets)[:2000] if message is not None else None
        )
        return ProviderFailureDiagnostic(
            http_status_code=int(response.status_code),
            sdk_exception_class=exception_class,
            provider_request_id=response.header(BEDROCK_REQUEST_ID_HEADER),
            provider_error_type=error_code,
            provider_error_code=error_code,
            provider_error_param=None,
            provider_error_message=sanitized_message,
            response_content_type=response.header("content-type"),
            response_body_sha256=sha256_bytes(response.body),
            response_body_byte_length=len(response.body),
            response_body_preview=preview,
            response_body_preview_truncated=truncated,
            diagnostic_text_limit_bytes=DIAGNOSTIC_TEXT_LIMIT_BYTES,
            adapter_version=BEDROCK_ADAPTER_VERSION,
            sdk_version=SIGV4_IMPLEMENTATION_VERSION,
            model_identifier=self.config.model_identifier,
            endpoint=redact_secrets(url, secrets),
            request_schema_hash=prepared.provider_schema_hash,
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _header_count(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _parse_json_or_text(body: bytes) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace") if body else ""


def _validate_against_canonical_schema(raw: str, canonical_schema_json: str) -> dict[str, Any]:
    """Validate provider text against the requested canonical schema.

    Reuses the Phase 2 canonical subset validator so Bedrock output is held to
    exactly the same contract as the existing provider, rather than a looser
    Bedrock-specific one.
    """
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise StructuredOutputError(f"invalid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise StructuredOutputError("structured output must be an object")
    schema = json.loads(canonical_schema_json)
    _validate_canonical_schema(value, schema, "$")
    return value


__all__ = [
    "ANTHROPIC_BEDROCK_VERSION",
    "BEDROCK_ADAPTER_VERSION",
    "BEDROCK_PRICING_SOURCE",
    "BEDROCK_PROVIDER",
    "BEDROCK_SIGNING_SERVICE",
    "BedrockConfigurationError",
    "BedrockCredentialError",
    "BedrockHttpRequest",
    "BedrockHttpResponse",
    "BedrockInvokeGateway",
    "BedrockProviderConfig",
    "BedrockTransport",
    "BedrockTransportFailure",
    "BedrockTransportTimeout",
    "FamilyOutcome",
    "FamilyPrompt",
    "FamilyResolution",
    "HttpsBedrockTransport",
    "MODEL_FAMILIES",
    "ModelFamily",
    "SCHEMA_INSTRUCTION",
    "UnsupportedModelFamilyError",
    "classify_bedrock_error",
    "extract_error_code",
    "resolve_model_family",
    "supported_family_ids",
    "supported_model_prefixes",
]
