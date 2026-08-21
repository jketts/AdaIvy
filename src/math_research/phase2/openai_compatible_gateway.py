"""One parameterised adapter for OpenAI-compatible provider gateways.

ADR-0030 accepts a single adapter family for the providers that publish an
OpenAI-compatible *chat completions* surface -- MiniMax, Qwen on AliCloud
DashScope, and DeepSeek -- plus Azure OpenAI, which reuses the same adapter but
keeps its own authentication and URL construction rather than being treated as
identical to the others.

What this module is not:

- It is not a trust boundary. A provider response stays a proposal. Nothing here
  creates an ``EpistemicWarrant``, approves semantic alignment, or sets novelty.
- It is not a second SDK boundary. The pinned ``openai`` package is loaded
  lazily through the one declared gated import in ``model_gateway`` so the
  offline suite never needs it installed and the repository invariant that
  enumerates lazy third-party loads keeps exactly two entries.
- It is not a claim that the compatibility layers behave like OpenAI. Where a
  layer cannot be shown to honour a strict schema, the adapter validates the
  returned bytes against the canonical schema itself and reports ``MALFORMED``
  when they do not conform. It never fabricates a success.

Values recorded here that could not be confirmed offline -- default base URLs,
whether a provider honours strict ``json_schema``, whether MiniMax's group id
belongs in the query string on the compatible endpoint -- are marked UNCONFIRMED
in this file and in the accompanying non-secret configuration JSON. They must be
verified against provider documentation before any live call.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, MutableMapping

from . import PHASE2_SCHEMA_VERSION
from .env_file import load_provider_credentials
from .openai_schema import project_openai_schema
from .records import (
    ModelRequest,
    ModelResult,
    ModelResultStatus,
    ModelUsage,
    ProviderFailureDiagnostic,
    ProviderSchemaPreparation,
)
from .serialization import canonical_json, sha256_bytes

# Reused deliberately rather than reimplemented. The bounded-preview, body-hash
# and redaction helpers must produce byte-identical diagnostics for both
# adapters, and `_load_openai_sdk` is the single declared gated import of the
# pinned SDK (see tests/test_repository_invariants.py::GATED_DYNAMIC_IMPORTS).
from .model_gateway import (  # noqa: PLC2701 - intentional intra-package reuse
    DIAGNOSTIC_TEXT_LIMIT_BYTES,
    _bounded_utf8,
    _load_openai_sdk,
    _optional_string,
    _parse_body_for_diagnostic,
    _response_body_bytes,
    _response_mapping,
    redact_secrets,
    validate_structured_output,
)


# --- versioned identity -----------------------------------------------------

OPENAI_COMPATIBLE_ADAPTER_VERSION = "openai-compatible-chat-adapter/1.0.0"
# Same wheel as the existing boundary: requirements-phase2-provider.txt pins
# openai==3.3.0 with its recorded PyPI wheel digest. All four providers in this
# module are served by that one package; none adds a dependency.
OPENAI_COMPATIBLE_SDK_PACKAGE = "openai"
OPENAI_COMPATIBLE_SDK_PINNED_VERSION = "3.3.0"


def adapter_version(provider: str) -> str:
    """Versioned adapter string carrying provider identity (ADR-0030)."""

    return f"{OPENAI_COMPATIBLE_ADAPTER_VERSION}+{provider}"


# --- provider identities ----------------------------------------------------

PROVIDER_MINIMAX = "minimax"
PROVIDER_QWEN_DASHSCOPE = "qwen_dashscope"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_AZURE_OPENAI = "azure_openai"

SUPPORTED_PROVIDERS = (
    PROVIDER_AZURE_OPENAI,
    PROVIDER_DEEPSEEK,
    PROVIDER_MINIMAX,
    PROVIDER_QWEN_DASHSCOPE,
)


# --- authentication styles --------------------------------------------------

#: ``Authorization: Bearer <key>``, constructed by the SDK from ``api_key``.
AUTH_BEARER_TOKEN = "bearer_token"
#: ``api-key: <key>``. Azure OpenAI only. Never a Bearer token.
AUTH_API_KEY_HEADER = "api_key_header"


# --- structured-output support ---------------------------------------------

#: Provider is documented to enforce a strict ``json_schema`` response format.
STRUCTURED_OUTPUT_JSON_SCHEMA_STRICT = "json_schema_strict"
#: Provider offers JSON mode only. The adapter validates the returned bytes
#: against the canonical schema locally; non-conforming output is MALFORMED.
STRUCTURED_OUTPUT_JSON_OBJECT_ONLY = "json_object_only"
#: Provider cannot be shown to honour any schema. Fail closed before any call.
STRUCTURED_OUTPUT_UNSUPPORTED = "unsupported"


# --- default endpoints (UNCONFIRMED) ---------------------------------------
# These are the documented shapes as understood at authoring time and were not
# reachable for verification offline. Confirm each against current provider
# documentation before a live call; a wrong base URL fails closed rather than
# silently producing a wrong answer, but it still burns a live attempt.

MINIMAX_DEFAULT_BASE_URL = "https://api.minimax.io/v1"  # UNCONFIRMED
QWEN_DASHSCOPE_DEFAULT_BASE_URL = (
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"  # UNCONFIRMED
)
DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"  # UNCONFIRMED
AZURE_DEPLOYMENT_PATH_TEMPLATE = "/openai/deployments/{deployment}"
CHAT_COMPLETIONS_PATH = "/chat/completions"


# --- bounded error taxonomy ------------------------------------------------
# Compatibility layers do not share OpenAI's error taxonomy. These two sets are
# deliberately small and are matched case-insensitively against the provider
# error ``code`` and ``type``. They only ever adjust the status-derived verdict;
# an unrecognised code leaves the HTTP classification untouched. UNCONFIRMED:
# assembled from common vendor strings, not from a verified enumeration.

RETRYABLE_PROVIDER_ERROR_CODES = frozenset({
    "rate_limit_exceeded",
    "rate_limit_reached",
    "rate_limit_error",
    "requesttimeout",
    "server_error",
    "service_unavailable",
    "throttling",
    "throttling.allocationquota",
    "throttling.ratequota",
    "overloaded_error",
})
FATAL_PROVIDER_ERROR_CODES = frozenset({
    "authenticationerror",
    "insufficient_quota",
    "invalid_api_key",
    "invalid_request_error",
    "invalidapikey",
    "permission_denied",
    "unauthorized",
})
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})


class ProviderConfigurationError(RuntimeError):
    """A required non-secret setting or credential is absent.

    The message names environment variables only. It never carries a value.
    """


# --- configuration ---------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenAICompatibleProviderConfig:
    """Frozen, non-secret description of one OpenAI-compatible provider."""

    schema_version: str = PHASE2_SCHEMA_VERSION
    provider: str
    model_identifier: str
    auth_style: str
    api_key_env: str
    structured_output_mode: str
    capabilities: tuple[str, ...]
    #: Literal base URL. Empty when ``base_url_env`` supplies it instead.
    base_url: str = ""
    #: Environment variable holding the resource root (Azure).
    base_url_env: str | None = None
    #: Environment variable holding the deployment name (Azure). Required when
    #: set: a deployment-scoped URL cannot be guessed.
    deployment_env: str | None = None
    #: ``(query parameter, environment variable)``; absent value fails closed.
    required_query_parameters: tuple[tuple[str, str], ...] = ()
    #: ``(query parameter, environment variable)``; omitted when unset.
    optional_query_parameters: tuple[tuple[str, str], ...] = ()
    #: Compatibility layers disagree on the output-cap parameter name.
    max_output_tokens_parameter: str = "max_tokens"
    #: SDK client class. Azure needs the SDK's Azure client for `api-key` auth.
    sdk_client_class: str = "OpenAI"
    #: Provider-specific status envelope returned inside an HTTP 200 body.
    #: MiniMax is documented to use ``base_resp``; others are left unset so no
    #: behaviour is invented for a provider that does not do this.
    inline_status_envelope: str | None = None


def minimax_config(
    *, model_identifier: str, base_url: str = MINIMAX_DEFAULT_BASE_URL,
) -> OpenAICompatibleProviderConfig:
    """MiniMax: Bearer token; group id optional and never required."""

    return OpenAICompatibleProviderConfig(
        provider=PROVIDER_MINIMAX,
        model_identifier=model_identifier,
        base_url=base_url,
        auth_style=AUTH_BEARER_TOKEN,
        api_key_env="MINIMAX_API_KEY",
        structured_output_mode=STRUCTURED_OUTPUT_JSON_OBJECT_ONLY,
        capabilities=("openai_compatible_chat_completions", "json_object_response_format"),
        # UNCONFIRMED placement: some MiniMax endpoints scope a request to a
        # group id. It is optional here and omitted entirely when unset.
        optional_query_parameters=(("GroupId", "MINIMAX_GROUP_ID"),),
        inline_status_envelope="base_resp",
    )


def qwen_dashscope_config(
    *, model_identifier: str, base_url: str = QWEN_DASHSCOPE_DEFAULT_BASE_URL,
) -> OpenAICompatibleProviderConfig:
    """Qwen on AliCloud DashScope: Bearer token, OpenAI-compatible base path."""

    return OpenAICompatibleProviderConfig(
        provider=PROVIDER_QWEN_DASHSCOPE,
        model_identifier=model_identifier,
        base_url=base_url,
        auth_style=AUTH_BEARER_TOKEN,
        api_key_env="DASHSCOPE_API_KEY",
        structured_output_mode=STRUCTURED_OUTPUT_JSON_OBJECT_ONLY,
        capabilities=("openai_compatible_chat_completions", "json_object_response_format"),
    )


def deepseek_config(
    *, model_identifier: str, base_url: str = DEEPSEEK_DEFAULT_BASE_URL,
) -> OpenAICompatibleProviderConfig:
    """DeepSeek: Bearer token."""

    return OpenAICompatibleProviderConfig(
        provider=PROVIDER_DEEPSEEK,
        model_identifier=model_identifier,
        base_url=base_url,
        auth_style=AUTH_BEARER_TOKEN,
        api_key_env="DEEPSEEK_API_KEY",
        structured_output_mode=STRUCTURED_OUTPUT_JSON_OBJECT_ONLY,
        capabilities=("openai_compatible_chat_completions", "json_object_response_format"),
    )


def azure_openai_config(*, model_identifier: str) -> OpenAICompatibleProviderConfig:
    """Azure OpenAI: `api-key` header, deployment-scoped URL, api-version.

    Deliberately not the same shape as the Bearer providers. All three of
    endpoint, deployment, and api-version are required; a missing one fails
    closed instead of being defaulted.
    """

    return OpenAICompatibleProviderConfig(
        provider=PROVIDER_AZURE_OPENAI,
        model_identifier=model_identifier,
        auth_style=AUTH_API_KEY_HEADER,
        api_key_env="AZURE_OPENAI_API_KEY",
        structured_output_mode=STRUCTURED_OUTPUT_JSON_SCHEMA_STRICT,
        capabilities=(
            "openai_compatible_chat_completions",
            "structured_output",
            "refusal",
        ),
        base_url_env="AZURE_OPENAI_ENDPOINT",
        deployment_env="AZURE_OPENAI_DEPLOYMENT",
        required_query_parameters=(("api-version", "AZURE_OPENAI_API_VERSION"),),
        max_output_tokens_parameter="max_completion_tokens",
        sdk_client_class="AzureOpenAI",
    )


_FACTORIES: dict[str, Callable[..., OpenAICompatibleProviderConfig]] = {
    PROVIDER_AZURE_OPENAI: azure_openai_config,
    PROVIDER_DEEPSEEK: deepseek_config,
    PROVIDER_MINIMAX: minimax_config,
    PROVIDER_QWEN_DASHSCOPE: qwen_dashscope_config,
}


def provider_config(provider: str, *, model_identifier: str) -> OpenAICompatibleProviderConfig:
    """Fail closed on an unknown provider rather than guessing a shape."""

    factory = _FACTORIES.get(provider)
    if factory is None:
        raise ProviderConfigurationError(
            f"unsupported provider: {provider!r}; supported: {list(SUPPORTED_PROVIDERS)}"
        )
    return factory(model_identifier=model_identifier)


# --- endpoint resolution ---------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedEndpoint:
    """Non-secret, fully resolved request target. Carries no credential."""

    schema_version: str = PHASE2_SCHEMA_VERSION
    provider: str
    #: Root passed to the SDK client (resource root for Azure).
    base_url: str
    #: Full request URL without the query string.
    request_url: str
    #: Header the credential travels in. ``authorization`` or ``api-key``.
    auth_header_name: str
    #: ``Bearer`` for token providers, ``None`` when the header is the raw key.
    auth_header_scheme: str | None
    #: Sorted ``(name, value)`` pairs. Non-secret settings only.
    query_parameters: tuple[tuple[str, str], ...]
    #: Deployment name when the URL is deployment-scoped.
    deployment: str | None


def resolve_endpoint(
    config: OpenAICompatibleProviderConfig,
    environment: MutableMapping[str, str],
) -> ResolvedEndpoint:
    """Build the request target, failing closed on any missing requirement."""

    if config.base_url_env is not None:
        root = (environment.get(config.base_url_env) or "").strip()
        if not root:
            raise ProviderConfigurationError(f"{config.base_url_env} is not configured")
    else:
        root = config.base_url.strip()
        if not root:
            raise ProviderConfigurationError(
                f"{config.provider} base URL is not configured"
            )
    if not root.startswith("https://"):
        raise ProviderConfigurationError(
            f"{config.provider} base URL must be an https:// URL"
        )
    base_url = root.rstrip("/")

    deployment: str | None = None
    request_url = base_url
    if config.deployment_env is not None:
        deployment = (environment.get(config.deployment_env) or "").strip()
        if not deployment:
            raise ProviderConfigurationError(f"{config.deployment_env} is not configured")
        if "/" in deployment or "?" in deployment:
            raise ProviderConfigurationError(
                f"{config.deployment_env} must be a single path segment"
            )
        request_url += AZURE_DEPLOYMENT_PATH_TEMPLATE.format(deployment=deployment)
    request_url += CHAT_COMPLETIONS_PATH

    parameters: dict[str, str] = {}
    for name, variable in config.required_query_parameters:
        value = (environment.get(variable) or "").strip()
        if not value:
            raise ProviderConfigurationError(f"{variable} is not configured")
        parameters[name] = value
    for name, variable in config.optional_query_parameters:
        value = (environment.get(variable) or "").strip()
        if value:
            parameters[name] = value

    if config.auth_style == AUTH_API_KEY_HEADER:
        header_name, scheme = "api-key", None
    elif config.auth_style == AUTH_BEARER_TOKEN:
        header_name, scheme = "authorization", "Bearer"
    else:
        raise ProviderConfigurationError(f"unsupported auth style: {config.auth_style!r}")

    return ResolvedEndpoint(
        provider=config.provider,
        base_url=base_url,
        request_url=request_url,
        auth_header_name=header_name,
        auth_header_scheme=scheme,
        query_parameters=tuple(sorted(parameters.items())),
        deployment=deployment,
    )


# --- error classification --------------------------------------------------


def classify_http_failure(
    status_code: int | None,
    *,
    provider_error_code: Any = None,
    provider_error_type: Any = None,
) -> str:
    """Map a provider failure to the ``retryable``/``fatal`` retry vocabulary.

    Mirrors the OpenAI adapter's status rule, then lets a small, bounded set of
    provider error strings override it. An absent or non-integer status is
    fatal: an unclassifiable failure must not be retried blindly.
    """

    if status_code is None:
        return "fatal:http_unknown"
    retryable = status_code in _RETRYABLE_STATUS_CODES or status_code >= 500
    tokens = {
        str(value).strip().lower()
        for value in (provider_error_code, provider_error_type)
        if value is not None and str(value).strip()
    }
    if tokens & FATAL_PROVIDER_ERROR_CODES:
        retryable = False
    elif tokens & RETRYABLE_PROVIDER_ERROR_CODES:
        retryable = True
    return ("retryable" if retryable else "fatal") + f":http_{status_code}"


def _int_status(error: Any) -> int | None:
    value = getattr(error, "status_code", None)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _error_mapping(body: Any) -> dict[str, Any]:
    """Normalise a provider error body of unknown shape without crashing."""

    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict):
            return inner
        if isinstance(inner, str):
            return {"message": inner}
        envelope = body.get("base_resp")
        if isinstance(envelope, dict):
            return {
                "message": envelope.get("status_msg"),
                "code": envelope.get("status_code"),
            }
        return body
    if isinstance(body, str):
        return {"message": body}
    if isinstance(body, list):
        return {"message": canonical_json(body)}
    return {}


def _inline_error(body: dict[str, Any], envelope_field: str | None) -> dict[str, Any] | None:
    """Detect a provider error carried inside an HTTP 200 response body."""

    error = body.get("error")
    if isinstance(error, dict) and error:
        return error
    if isinstance(error, str) and error.strip():
        return {"message": error}
    if envelope_field is not None:
        envelope = body.get(envelope_field)
        if isinstance(envelope, dict):
            code = envelope.get("status_code")
            if isinstance(code, int) and not isinstance(code, bool) and code != 0:
                return {
                    "message": envelope.get("status_msg"),
                    "code": code,
                }
    return None


# --- the adapter -----------------------------------------------------------


class OpenAICompatibleChatGateway:
    """``ModelGateway`` over an OpenAI-compatible chat-completions endpoint.

    Parameterised entirely by ``config``. Nothing about the trust model changes:
    every result is a proposal, and a compatibility layer that cannot be shown
    to have honoured the schema yields ``MALFORMED``, never a success.
    """

    def __init__(
        self,
        config: OpenAICompatibleProviderConfig,
        *,
        sdk_module: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
        environment: MutableMapping[str, str] | None = None,
        env_path: Path | None = None,
        credential_loader: Callable[..., Any] | None = None,
        schema_dir: Path | None = None,
    ) -> None:
        self.config = config
        self._sdk_module = sdk_module
        self._client_factory = client_factory
        self._environment = environment
        self._env_path = env_path
        self._credential_loader = credential_loader or load_provider_credentials
        self._schema_dir = schema_dir
        self._credentials_loaded = False
        self.credential_load_result: Any | None = None

    # -- ports --------------------------------------------------------------

    def prepare(self, request: ModelRequest) -> ProviderSchemaPreparation:
        """Project the canonical schema. Never a trust decision.

        The preparation records ``provider="openai"`` because it *is* the
        OpenAI Structured Outputs projection that these layers imitate. True
        provider identity lives in ``ModelResult.provider``.
        """

        return project_openai_schema(request.response_schema)

    def complete(
        self, request: ModelRequest, preparation: ProviderSchemaPreparation | None = None,
    ) -> ModelResult:
        prepared = preparation or self.prepare(request)
        if self.config.structured_output_mode == STRUCTURED_OUTPUT_UNSUPPORTED:
            # Fail closed before touching a credential or a socket.
            return self._failure(
                ModelResultStatus.MALFORMED,
                "fatal:strict_schema_unsupported",
                provider_schema_hash=prepared.provider_schema_hash,
            )
        if self.config.structured_output_mode not in {
            STRUCTURED_OUTPUT_JSON_SCHEMA_STRICT, STRUCTURED_OUTPUT_JSON_OBJECT_ONLY,
        }:
            raise ProviderConfigurationError(
                f"unsupported structured output mode: {self.config.structured_output_mode!r}"
            )

        environment = self._resolve_environment()
        api_key = (environment.get(self.config.api_key_env) or "").strip()
        if not api_key:
            raise ProviderConfigurationError(f"{self.config.api_key_env} is not configured")
        endpoint = resolve_endpoint(self.config, environment)

        sdk = self._sdk_module or _load_openai_sdk()
        factory = self._client_factory or getattr(sdk, self.config.sdk_client_class, None)
        if factory is None:
            raise ProviderConfigurationError(
                f"pinned SDK {OPENAI_COMPATIBLE_SDK_PACKAGE}"
                f"=={OPENAI_COMPATIBLE_SDK_PINNED_VERSION} has no"
                f" {self.config.sdk_client_class} client"
            )
        client = factory(**self._client_kwargs(api_key, endpoint, request))
        payload = self._payload(request, prepared)

        try:
            response = client.chat.completions.create(**payload)
        except sdk.APIStatusError as error:
            diagnostic = self._diagnostic(
                error,
                api_key=api_key,
                sdk_version=str(getattr(sdk, "__version__", "unknown")),
                endpoint=endpoint,
                request_schema_hash=prepared.provider_schema_hash,
            )
            return self._failure(
                ModelResultStatus.FAILED,
                classify_http_failure(
                    _int_status(error),
                    provider_error_code=diagnostic.provider_error_code,
                    provider_error_type=diagnostic.provider_error_type,
                ),
                provider_request_id=diagnostic.provider_request_id,
                provider_failure=diagnostic,
                provider_schema_hash=prepared.provider_schema_hash,
            )
        except sdk.APITimeoutError:
            return self._failure(
                ModelResultStatus.TIMED_OUT, "retryable:timeout",
                provider_schema_hash=prepared.provider_schema_hash,
            )
        except sdk.APIConnectionError:
            return self._failure(
                ModelResultStatus.FAILED, "retryable:transport",
                provider_schema_hash=prepared.provider_schema_hash,
            )

        try:
            body = _response_mapping(response)
        except (TypeError, ValueError):
            return self._failure(
                ModelResultStatus.FAILED, "retryable:response_decode",
                provider_schema_hash=prepared.provider_schema_hash,
            )
        return self._map_response(request, prepared, body)

    # -- internals ----------------------------------------------------------

    def _resolve_environment(self) -> MutableMapping[str, str]:
        values = os.environ if self._environment is None else self._environment
        if not self._credentials_loaded:
            self.credential_load_result = self._credential_loader(
                self._env_path, environment=values,
            )
            self._credentials_loaded = True
        return values

    def _client_kwargs(
        self, api_key: str, endpoint: ResolvedEndpoint, request: ModelRequest,
    ) -> dict[str, Any]:
        timeout = request.timeout_milliseconds / 1000
        if self.config.auth_style == AUTH_API_KEY_HEADER:
            # Azure's `api-key` header, deployment-scoped path, and required
            # api-version query parameter are constructed by the pinned SDK's
            # Azure client from these arguments. A Bearer token is never sent.
            parameters = dict(endpoint.query_parameters)
            api_version = parameters.pop("api-version")
            kwargs: dict[str, Any] = {
                "api_key": api_key,
                "api_version": api_version,
                "azure_endpoint": endpoint.base_url,
                "azure_deployment": endpoint.deployment,
                "timeout": timeout,
                "max_retries": 0,
            }
            if parameters:
                kwargs["default_query"] = dict(sorted(parameters.items()))
            return kwargs
        kwargs = {
            "api_key": api_key,
            "base_url": endpoint.base_url,
            "timeout": timeout,
            "max_retries": 0,
        }
        if endpoint.query_parameters:
            kwargs["default_query"] = dict(endpoint.query_parameters)
        return kwargs

    def _payload(
        self, request: ModelRequest, prepared: ProviderSchemaPreparation,
    ) -> dict[str, Any]:
        if self.config.structured_output_mode == STRUCTURED_OUTPUT_JSON_SCHEMA_STRICT:
            response_format: dict[str, Any] = {
                "type": "json_schema",
                "json_schema": {
                    "name": f"adaivy_{request.purpose}_v1",
                    "strict": True,
                    "schema": json.loads(prepared.provider_schema_json),
                },
            }
        else:
            response_format = {"type": "json_object"}
        return {
            "model": self.config.model_identifier,
            "messages": [
                {"role": "system", "content": request.template_text},
                {"role": "user", "content": request.serialized_context},
            ],
            self.config.max_output_tokens_parameter: request.max_output_tokens,
            "response_format": response_format,
            "stream": False,
        }

    def _map_response(
        self,
        request: ModelRequest,
        prepared: ProviderSchemaPreparation,
        body: dict[str, Any],
    ) -> ModelResult:
        schema_hash = prepared.provider_schema_hash
        model_identifier = (
            body["model"] if isinstance(body.get("model"), str) and body["model"]
            else self.config.model_identifier
        )
        provider_request_id = body["id"] if isinstance(body.get("id"), str) else None
        usage, usage_source = _usage(body.get("usage"))

        inline = _inline_error(body, self.config.inline_status_envelope)
        if inline is not None:
            return self._result(
                ModelResultStatus.FAILED,
                model_identifier=model_identifier,
                usage=usage,
                retry_classification=classify_http_failure(
                    200,
                    provider_error_code=inline.get("code"),
                    provider_error_type=inline.get("type"),
                ),
                provider_request_id=provider_request_id,
                provider_schema_hash=schema_hash,
            )

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return self._result(
                ModelResultStatus.MALFORMED,
                model_identifier=model_identifier, usage=usage,
                retry_classification="fatal:missing_choices",
                provider_request_id=provider_request_id, provider_schema_hash=schema_hash,
            )
        choice = choices[0]
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        finish_reason = choice.get("finish_reason")
        finish = str(finish_reason).strip() if isinstance(finish_reason, str) else ""

        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal.strip():
            return self._result(
                ModelResultStatus.REFUSED,
                model_identifier=model_identifier, usage=usage,
                retry_classification="not_retryable:refusal",
                refusal=refusal[:2_000],
                provider_request_id=provider_request_id, provider_schema_hash=schema_hash,
            )
        if finish == "content_filter":
            return self._result(
                ModelResultStatus.REFUSED,
                model_identifier=model_identifier, usage=usage,
                retry_classification="not_retryable:refusal",
                refusal="provider content filter",
                provider_request_id=provider_request_id, provider_schema_hash=schema_hash,
            )
        if finish in {"length", "max_tokens"}:
            return self._result(
                ModelResultStatus.INCOMPLETE,
                model_identifier=model_identifier, usage=usage,
                retry_classification="not_retryable:incomplete_response",
                incomplete_reason=f"finish_reason:{finish}"[:2_000],
                provider_request_id=provider_request_id, provider_schema_hash=schema_hash,
            )

        content = message.get("content")
        if finish != "stop" or not isinstance(content, str) or not content or usage_source == "unavailable":
            return self._result(
                ModelResultStatus.MALFORMED,
                model_identifier=model_identifier, usage=usage,
                retry_classification="fatal:missing_output_finish_reason_or_usage",
                provider_request_id=provider_request_id, provider_schema_hash=schema_hash,
            )

        if self.config.structured_output_mode == STRUCTURED_OUTPUT_JSON_OBJECT_ONLY:
            # The layer was not asked for, and cannot be shown to enforce, a
            # strict schema. Validate the bytes against the canonical schema
            # here rather than passing unvalidated output off as a success.
            try:
                validate_structured_output(
                    request.purpose, content, schema_dir=self._schema_dir,
                )
            except ValueError:
                return self._result(
                    ModelResultStatus.MALFORMED,
                    model_identifier=model_identifier, usage=usage,
                    retry_classification="fatal:strict_schema_not_enforced_and_output_invalid",
                    provider_request_id=provider_request_id, provider_schema_hash=schema_hash,
                )
        else:
            try:
                decoded = json.loads(content)
            except json.JSONDecodeError:
                decoded = None
            if not isinstance(decoded, dict):
                return self._result(
                    ModelResultStatus.MALFORMED,
                    model_identifier=model_identifier, usage=usage,
                    retry_classification="fatal:strict_schema_violated",
                    provider_request_id=provider_request_id, provider_schema_hash=schema_hash,
                )

        return self._result(
            ModelResultStatus.SUCCEEDED,
            model_identifier=model_identifier, usage=usage,
            retry_classification="none", structured_output=content,
            provider_request_id=provider_request_id, provider_schema_hash=schema_hash,
        )

    def _result(
        self,
        status: ModelResultStatus,
        *,
        model_identifier: str,
        usage: ModelUsage,
        retry_classification: str,
        structured_output: str | None = None,
        refusal: str | None = None,
        incomplete_reason: str | None = None,
        provider_request_id: str | None = None,
        provider_failure: ProviderFailureDiagnostic | None = None,
        provider_schema_hash: str | None = None,
    ) -> ModelResult:
        return ModelResult(
            status=status,
            provider=self.config.provider,
            model_identifier=model_identifier,
            capabilities=self.config.capabilities,
            structured_output=structured_output,
            declared_rationale=None,
            refusal=refusal,
            usage=usage,
            retry_classification=retry_classification,
            provider_request_id=provider_request_id,
            incomplete_reason=incomplete_reason,
            provider_failure=provider_failure,
            provider_schema_hash=provider_schema_hash,
        )

    def _failure(
        self,
        status: ModelResultStatus,
        retry_classification: str,
        *,
        provider_request_id: str | None = None,
        provider_failure: ProviderFailureDiagnostic | None = None,
        provider_schema_hash: str | None = None,
    ) -> ModelResult:
        return self._result(
            status,
            model_identifier=self.config.model_identifier,
            usage=ModelUsage(
                input_tokens=0, output_tokens=0, total_tokens=0,
                usage_source="unavailable",
            ),
            retry_classification=retry_classification,
            provider_request_id=provider_request_id,
            provider_failure=provider_failure,
            provider_schema_hash=provider_schema_hash,
        )

    def _diagnostic(
        self,
        error: Any,
        *,
        api_key: str,
        sdk_version: str,
        endpoint: ResolvedEndpoint,
        request_schema_hash: str,
    ) -> ProviderFailureDiagnostic:
        """Build a diagnostic that has been through ``redact_secrets``."""

        raw_body = getattr(error, "body", None)
        response = getattr(error, "response", None)
        body_bytes = _response_body_bytes(response, raw_body)
        parsed = _parse_body_for_diagnostic(body_bytes, raw_body)
        sanitized = redact_secrets(parsed, (api_key,))
        rendered = sanitized if isinstance(sanitized, str) else canonical_json(sanitized)
        preview, truncated = _bounded_utf8(rendered, DIAGNOSTIC_TEXT_LIMIT_BYTES)

        mapping = _error_mapping(raw_body)
        message = mapping.get("message")
        if message is None:
            message = getattr(error, "message", None)
        sanitized_message = (
            redact_secrets(str(message), (api_key,))[:2_000] if message is not None else None
        )
        headers = getattr(response, "headers", None)
        content_type = None
        if headers is not None:
            try:
                content_type = headers.get("content-type") or headers.get("Content-Type")
            except AttributeError:
                content_type = None
        status = _int_status(error)
        # The endpoint is non-secret, but it is passed through redaction anyway
        # so a credential mistakenly embedded in a base URL cannot leak.
        endpoint_text = redact_secrets(
            _endpoint_text(endpoint), (api_key,),
        )
        return ProviderFailureDiagnostic(
            http_status_code=status if status is not None else 0,
            sdk_exception_class=type(error).__name__,
            provider_request_id=_optional_string(getattr(error, "request_id", None)),
            provider_error_type=_optional_string(
                mapping.get("type") or getattr(error, "type", None)
            ),
            provider_error_code=_optional_string(
                mapping.get("code") if mapping.get("code") is not None
                else getattr(error, "code", None)
            ),
            provider_error_param=_optional_string(
                mapping.get("param") or getattr(error, "param", None)
            ),
            provider_error_message=sanitized_message,
            response_content_type=_optional_string(content_type),
            response_body_sha256=sha256_bytes(body_bytes),
            response_body_byte_length=len(body_bytes),
            response_body_preview=preview,
            response_body_preview_truncated=truncated,
            diagnostic_text_limit_bytes=DIAGNOSTIC_TEXT_LIMIT_BYTES,
            adapter_version=adapter_version(self.config.provider),
            sdk_version=redact_secrets(sdk_version, (api_key,)),
            model_identifier=self.config.model_identifier,
            endpoint=endpoint_text,
            request_schema_hash=request_schema_hash,
        )


def _endpoint_text(endpoint: ResolvedEndpoint) -> str:
    """Deterministic, non-secret rendering of the request target."""

    if not endpoint.query_parameters:
        return endpoint.request_url
    query = "&".join(f"{name}={value}" for name, value in endpoint.query_parameters)
    return f"{endpoint.request_url}?{query}"


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _usage(value: Any) -> tuple[ModelUsage, str]:
    """Map a compat usage block, tolerating the two field vocabularies."""

    if not isinstance(value, dict):
        return _unavailable_usage(), "unavailable"
    input_tokens = _positive_int(value.get("prompt_tokens"))
    if input_tokens is None:
        input_tokens = _positive_int(value.get("input_tokens"))
    output_tokens = _positive_int(value.get("completion_tokens"))
    if output_tokens is None:
        output_tokens = _positive_int(value.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return _unavailable_usage(), "unavailable"
    total_tokens = _positive_int(value.get("total_tokens"))
    if total_tokens is None:
        # Reported parts, derived total. Named distinctly so a report never
        # implies the provider stated a figure it did not state.
        source = "api_reported_derived_total"
        total_tokens = input_tokens + output_tokens
    else:
        source = "api_reported"
    return (
        ModelUsage(
            input_tokens=input_tokens, output_tokens=output_tokens,
            total_tokens=total_tokens, usage_source=source,
        ),
        source,
    )


def _unavailable_usage() -> ModelUsage:
    return ModelUsage(
        input_tokens=0, output_tokens=0, total_tokens=0, usage_source="unavailable",
    )
