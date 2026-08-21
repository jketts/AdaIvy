"""Opt-in Anthropic Messages API adapter for the Phase 2 model boundary.

ADR-0030 admits this provider. The adapter is an opt-in gated boundary: the SDK
is imported lazily so the offline path never needs it, no network occurs at
import time, and a returned message remains a proposal that carries no warrant.

Two deliberate differences from the OpenAI adapter:

* `prepare` returns ``None``. `project_openai_schema` encodes OpenAI's schema
  dialect and emits a transformation manifest describing OpenAI-specific
  rewrites; reusing it here would misreport what was actually sent. The canonical
  schema is forwarded unmodified and the canonical
  :func:`validate_structured_output` is the sole admission gate, so output is
  never accepted unvalidated. The cost is that this provider gets no
  schema-compatibility lint -- see ADR-0030's revisit trigger.
* No sampling parameters and no thinking token budget are ever sent. Current
  models reject ``temperature``/``top_p``/``top_k`` and
  ``thinking.budget_tokens`` with HTTP 400, so emitting them would fail closed
  for the wrong reason.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from . import PHASE2_SCHEMA_VERSION
from .model_gateway import (
    DIAGNOSTIC_TEXT_LIMIT_BYTES,
    StructuredOutputError,
    _bounded_utf8,
    _optional_string,
    redact_secrets,
    validate_structured_output,
)
from .records import (
    ModelRequest,
    ModelResult,
    ModelResultStatus,
    ModelUsage,
    ProviderFailureDiagnostic,
    ProviderSchemaPreparation,
)
from .serialization import sha256_bytes

PROVIDER = "anthropic"
ANTHROPIC_ADAPTER_VERSION = "anthropic-messages-adapter/1.0.0"
ANTHROPIC_SDK_PACKAGE = "anthropic"
# Confirmed against the PyPI release metadata on 2026-08-21 and pinned by wheel
# digest in requirements-phase2-provider.txt. v1.0.0 is a breaking release whose
# migration notes do not reach this adapter: the client receives plain values
# (`timeout`, `max_retries=0`) rather than httpx objects, the payload already
# uses `output_config={"format": ...}` instead of the removed `output_format`,
# and it passes none of the removed sampling parameters. Re-confirm the digest
# before moving the pin.
ANTHROPIC_SDK_PINNED_VERSION = "1.0.0"
DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"

# Model identifiers are exact and complete as written; a date suffix is never
# appended. Restricting to a known set stops a stale or invented id reaching the
# provider as an opaque 404.
SUPPORTED_MODEL_IDENTIFIERS = frozenset({
    "claude-fable-5",
    "claude-haiku-4-5",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-opus-5",
    "claude-sonnet-4-6",
    "claude-sonnet-5",
})
DEFAULT_MODEL_IDENTIFIER = "claude-opus-5"
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
# `stop_details` is populated only for a refusal; every other stop reason
# leaves it null, so it must be guarded before it is read.
REFUSAL_STOP_REASON = "refusal"
INCOMPLETE_STOP_REASONS = frozenset({"max_tokens", "pause_turn"})
RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})


class AnthropicConfigurationError(ValueError):
    """The adapter was configured with something the provider would reject."""


@dataclass(frozen=True, slots=True, kw_only=True)
class AnthropicProviderConfig:
    schema_version: str = PHASE2_SCHEMA_VERSION
    model_identifier: str = DEFAULT_MODEL_IDENTIFIER
    endpoint: str = DEFAULT_ENDPOINT
    api_key_env: str = "ANTHROPIC_API_KEY"
    effort: str = "high"
    adaptive_thinking: bool = True
    capabilities: tuple[str, ...] = field(
        default=("messages_api", "structured_output", "refusal", "adaptive_thinking"),
    )

    def __post_init__(self) -> None:
        if self.model_identifier not in SUPPORTED_MODEL_IDENTIFIERS:
            raise AnthropicConfigurationError(
                f"unsupported anthropic model identifier: {self.model_identifier}"
            )
        if self.effort not in EFFORT_LEVELS:
            raise AnthropicConfigurationError(f"unsupported effort: {self.effort}")
        if not self.endpoint.startswith("https://"):
            raise AnthropicConfigurationError("endpoint must be https")


def _load_anthropic_sdk() -> Any:
    try:
        return importlib.import_module("anthropic")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "anthropic SDK is not installed; install the pinned Phase 2 provider "
            "dependency"
        ) from error


def anthropic_sdk_version() -> str | None:
    try:
        sdk = importlib.import_module("anthropic")
    except ModuleNotFoundError:
        return None
    return str(getattr(sdk, "__version__", "unknown"))


def _text_from_content(content: Any) -> str | None:
    """Join every text block. `content` is a list of blocks, never one string."""
    if not isinstance(content, (list, tuple)):
        return None
    parts: list[str] = []
    for block in content:
        if getattr(block, "type", None) != "text":
            continue
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts) if parts else None


def _usage(raw: Any) -> ModelUsage | None:
    if raw is None:
        return None
    input_tokens = getattr(raw, "input_tokens", None)
    output_tokens = getattr(raw, "output_tokens", None)
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        return None
    if isinstance(input_tokens, bool) or isinstance(output_tokens, bool):
        return None
    # Cache tokens are billed separately and are not part of the uncached input
    # count; they are added so the recorded total reflects what was processed.
    cache_write = getattr(raw, "cache_creation_input_tokens", None) or 0
    cache_read = getattr(raw, "cache_read_input_tokens", None) or 0
    cache_write = cache_write if isinstance(cache_write, int) else 0
    cache_read = cache_read if isinstance(cache_read, int) else 0
    billed_input = input_tokens + cache_write + cache_read
    return ModelUsage(
        input_tokens=billed_input,
        output_tokens=output_tokens,
        total_tokens=billed_input + output_tokens,
        usage_source=(
            "api_reported_with_cache" if (cache_write or cache_read) else "api_reported"
        ),
    )


def _diagnostic(
    error: Any,
    *,
    api_key: str,
    sdk_version: str,
    config: AnthropicProviderConfig,
    status_code: int,
) -> ProviderFailureDiagnostic:
    body = getattr(error, "body", None)
    error_object = body.get("error") if isinstance(body, dict) else None
    error_object = error_object if isinstance(error_object, dict) else {}
    try:
        raw = json.dumps(body, sort_keys=True).encode("utf-8") if body is not None else b""
    except (TypeError, ValueError):
        raw = repr(body).encode("utf-8", "replace")
    preview, truncated = _bounded_utf8(
        str(redact_secrets(raw.decode("utf-8", "replace"), (api_key,))),
        DIAGNOSTIC_TEXT_LIMIT_BYTES,
    )
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    return ProviderFailureDiagnostic(
        http_status_code=status_code,
        sdk_exception_class=type(error).__name__,
        provider_request_id=_optional_string(getattr(error, "request_id", None)),
        provider_error_type=_optional_string(error_object.get("type")),
        provider_error_code=_optional_string(error_object.get("code")),
        provider_error_param=_optional_string(error_object.get("param")),
        provider_error_message=_optional_string(
            redact_secrets(error_object.get("message"), (api_key,))
        ),
        response_content_type=_optional_string(
            headers.get("content-type") if hasattr(headers, "get") else None
        ),
        response_body_sha256=sha256_bytes(raw),
        response_body_byte_length=len(raw),
        response_body_preview=preview,
        response_body_preview_truncated=truncated,
        diagnostic_text_limit_bytes=DIAGNOSTIC_TEXT_LIMIT_BYTES,
        adapter_version=ANTHROPIC_ADAPTER_VERSION,
        sdk_version=sdk_version,
        model_identifier=config.model_identifier,
        endpoint=config.endpoint,
        request_schema_hash="",
    )


def _failure(
    config: AnthropicProviderConfig,
    status: ModelResultStatus,
    retry: str,
    *,
    provider_request_id: str | None = None,
    provider_failure: ProviderFailureDiagnostic | None = None,
    refusal: str | None = None,
) -> ModelResult:
    return ModelResult(
        status=status,
        provider=PROVIDER,
        model_identifier=config.model_identifier,
        capabilities=config.capabilities,
        structured_output=None,
        declared_rationale=None,
        refusal=refusal,
        usage=ModelUsage(
            input_tokens=0, output_tokens=0, total_tokens=0, usage_source="unavailable",
        ),
        retry_classification=retry,
        provider_request_id=provider_request_id,
        provider_failure=provider_failure,
    )


class AnthropicMessagesGateway:
    """Opt-in Anthropic adapter with a fail-closed structured-output boundary."""

    def __init__(
        self,
        config: AnthropicProviderConfig,
        *,
        sdk_module: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
        credentials: dict[str, str] | None = None,
    ) -> None:
        self.config = config
        self._sdk_module = sdk_module
        self._client_factory = client_factory
        self._credentials = credentials

    def prepare(self, request: ModelRequest) -> ProviderSchemaPreparation | None:
        """No provider projection is performed; see the module docstring."""
        return None

    def _api_key(self) -> str:
        if self._credentials is not None:
            key = self._credentials.get(self.config.api_key_env)
        else:
            import os

            key = os.environ.get(self.config.api_key_env)
        if not key:
            raise RuntimeError(f"{self.config.api_key_env} is not configured")
        return key

    def complete(
        self,
        request: ModelRequest,
        preparation: ProviderSchemaPreparation | None = None,
    ) -> ModelResult:
        api_key = self._api_key()
        sdk = self._sdk_module or _load_anthropic_sdk()
        sdk_version = str(getattr(sdk, "__version__", "unknown"))
        factory = self._client_factory or sdk.Anthropic
        client = factory(
            api_key=api_key,
            timeout=request.timeout_milliseconds / 1000,
            max_retries=0,
        )
        payload: dict[str, Any] = {
            "model": self.config.model_identifier,
            "max_tokens": request.max_output_tokens,
            "system": request.template_text,
            "messages": [{"role": "user", "content": request.serialized_context}],
            "output_config": {
                "effort": self.config.effort,
                "format": {
                    "type": "json_schema",
                    "name": f"adaivy_{request.purpose}_v1",
                    "schema": json.loads(request.response_schema),
                },
            },
        }
        if self.config.adaptive_thinking:
            # Adaptive only. `budget_tokens` is removed on current models.
            payload["thinking"] = {"type": "adaptive"}
        try:
            response = client.messages.create(**payload)
        except sdk.APITimeoutError:
            return _failure(self.config, ModelResultStatus.TIMED_OUT, "retryable:timeout")
        except sdk.APIConnectionError:
            return _failure(self.config, ModelResultStatus.FAILED, "retryable:connection")
        except sdk.APIStatusError as error:
            status_code = getattr(error, "status_code", None)
            if not isinstance(status_code, int) or isinstance(status_code, bool):
                classification, status_code = "fatal:http_unknown", 0
            else:
                retryable = (
                    status_code in RETRYABLE_STATUS_CODES or status_code >= 500
                )
                classification = (
                    "retryable" if retryable else "fatal"
                ) + f":http_{status_code}"
            diagnostic = _diagnostic(
                error, api_key=api_key, sdk_version=sdk_version,
                config=self.config, status_code=status_code,
            )
            return _failure(
                self.config, ModelResultStatus.FAILED, classification,
                provider_request_id=diagnostic.provider_request_id,
                provider_failure=diagnostic,
            )
        return self._map_response(response, request)

    def _map_response(self, response: Any, request: ModelRequest) -> ModelResult:
        request_id = _optional_string(getattr(response, "_request_id", None))
        stop_reason = _optional_string(getattr(response, "stop_reason", None))
        usage = _usage(getattr(response, "usage", None))

        if stop_reason == REFUSAL_STOP_REASON:
            details = getattr(response, "stop_details", None)
            category = _optional_string(getattr(details, "category", None))
            return _failure(
                self.config, ModelResultStatus.REFUSED,
                "fatal:refusal", provider_request_id=request_id,
                refusal=category or REFUSAL_STOP_REASON,
            )
        if stop_reason in INCOMPLETE_STOP_REASONS:
            result = _failure(
                self.config, ModelResultStatus.INCOMPLETE,
                f"retryable:{stop_reason}", provider_request_id=request_id,
            )
            return (
                result if usage is None
                else ModelResult(**{**_as_kwargs(result), "usage": usage})
            )
        if usage is None:
            return _failure(
                self.config, ModelResultStatus.MALFORMED,
                "fatal:usage_unavailable", provider_request_id=request_id,
            )
        raw = _text_from_content(getattr(response, "content", None))
        if raw is None:
            return _failure(
                self.config, ModelResultStatus.MALFORMED,
                "fatal:no_text_content", provider_request_id=request_id,
            )
        try:
            validate_structured_output(request.purpose, raw)
        except StructuredOutputError:
            return _failure(
                self.config, ModelResultStatus.MALFORMED,
                "fatal:structured_output_invalid", provider_request_id=request_id,
            )
        return ModelResult(
            status=ModelResultStatus.SUCCEEDED,
            provider=PROVIDER,
            model_identifier=_optional_string(getattr(response, "model", None))
            or self.config.model_identifier,
            capabilities=self.config.capabilities,
            structured_output=raw,
            declared_rationale=None,
            refusal=None,
            usage=usage,
            retry_classification="none",
            provider_request_id=request_id,
        )


def _as_kwargs(result: ModelResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "provider": result.provider,
        "model_identifier": result.model_identifier,
        "capabilities": result.capabilities,
        "structured_output": result.structured_output,
        "declared_rationale": result.declared_rationale,
        "refusal": result.refusal,
        "usage": result.usage,
        "retry_classification": result.retry_classification,
        "provider_request_id": result.provider_request_id,
        "incomplete_reason": result.incomplete_reason,
        "provider_failure": result.provider_failure,
        "provider_schema_hash": result.provider_schema_hash,
    }
