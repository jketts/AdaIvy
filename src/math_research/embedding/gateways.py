"""Embedding gateway adapters.

Both credentialed providers -- ``openai`` and ``azure_openai`` -- reach
embeddings through the `openai` SDK. That SDK is loaded through
`phase2.model_gateway._load_openai_sdk`, which is the single declared gated
import at ``src/math_research/phase2/model_gateway.py``. This module therefore
adds NO new entry to ``GATED_DYNAMIC_IMPORTS``: it calls no ``import_module``
itself, exactly as `phase2/openai_compatible_gateway.py:57` already does.

`gateway_corpus_provenance` is fail-closed. Only a recognised live adapter can
produce ``provider_embedded``; anything else -- a scripted fixture, a stub, an
unrecognised object -- yields ``project_authored``, so a fixture vector can never
be reported as evidence about real embedding quality.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

# `_load_openai_sdk` is the ONE declared gated load of the `openai` SDK.
# Importing it here rather than re-declaring `import_module("openai")` is what
# keeps `tests/test_repository_invariants.py` unchanged.
from ..phase2.model_gateway import OPENAI_SDK_PINNED_VERSION, _load_openai_sdk
from ..phase2.provider_registry import provider_secret_variables
from .constants import (
    CORPUS_PROVENANCE_PROJECT_AUTHORED,
    CORPUS_PROVENANCE_PROVIDER_EMBEDDED,
    SUPPORTED_EMBEDDING_PROVIDERS,
)
from .errors import EmbeddingError, ProviderCallForbiddenError
from .ports import EmbeddingGateway
from .records import EmbeddingRequest, EmbeddingResult, EmbeddingUsage

EMBEDDING_ADAPTER_VERSION = "openai-embeddings-adapter/1.0.0"

#: Azure exposes embeddings on a deployment-scoped URL; the SDK's Azure client
#: builds it from these non-secret settings. Never a Bearer token.
AZURE_SETTING_VARIABLES = (
    "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenAIEmbeddingConfig:
    provider: str
    model_identifier: str
    dimension: int
    api_key_env: str = "OPENAI_API_KEY"
    base_url_env: str | None = None
    deployment_env: str | None = None
    api_version_env: str | None = None
    capabilities: tuple[str, ...] = field(default=("embeddings", "input_only"))
    sdk_client_class: str = "OpenAI"
    sdk_pinned_version: str = OPENAI_SDK_PINNED_VERSION

    def __post_init__(self) -> None:
        if self.provider not in SUPPORTED_EMBEDDING_PROVIDERS:
            raise EmbeddingError(
                f"no embedding adapter for provider {self.provider!r}",
                code="embedding_provider_unsupported",
            )


def openai_embedding_config(*, model_identifier: str, dimension: int) -> OpenAIEmbeddingConfig:
    return OpenAIEmbeddingConfig(
        provider="openai", model_identifier=model_identifier, dimension=dimension,
        api_key_env="OPENAI_API_KEY", sdk_client_class="OpenAI",
    )


def azure_openai_embedding_config(
    *, model_identifier: str, dimension: int,
) -> OpenAIEmbeddingConfig:
    return OpenAIEmbeddingConfig(
        provider="azure_openai", model_identifier=model_identifier, dimension=dimension,
        api_key_env="AZURE_OPENAI_API_KEY",
        base_url_env="AZURE_OPENAI_ENDPOINT",
        deployment_env="AZURE_OPENAI_DEPLOYMENT",
        api_version_env="AZURE_OPENAI_API_VERSION",
        sdk_client_class="AzureOpenAI",
    )


class OpenAIEmbeddingGateway:
    """Opt-in live adapter. One call, one text, input tokens only."""

    def __init__(
        self,
        config: OpenAIEmbeddingConfig,
        *,
        sdk_module: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.config = config
        self._sdk_module = sdk_module
        self._client_factory = client_factory
        self._environment = environment if environment is not None else os.environ

    def secret_variables(self) -> tuple[str, ...]:
        """Reused from `phase2.provider_registry`, never re-derived here."""

        return provider_secret_variables(self.config.provider)

    def _client(self, request: EmbeddingRequest) -> Any:
        api_key = (self._environment.get(self.config.api_key_env) or "").strip()
        if not api_key:
            raise EmbeddingError(
                f"{self.config.api_key_env} is not configured",
                code="embedding_credential_absent",
            )
        sdk = self._sdk_module or _load_openai_sdk()
        factory = self._client_factory or getattr(sdk, self.config.sdk_client_class)
        arguments: dict[str, Any] = {
            "api_key": api_key,
            "timeout": request.timeout_milliseconds,
            "max_retries": 0,
        }
        if self.config.provider == "azure_openai":
            for name, variable in (
                ("azure_endpoint", self.config.base_url_env),
                ("azure_deployment", self.config.deployment_env),
                ("api_version", self.config.api_version_env),
            ):
                value = (self._environment.get(variable or "") or "").strip()
                if not value:
                    raise EmbeddingError(
                        f"{variable} is not configured",
                        code="embedding_setting_absent",
                    )
                arguments[name] = value
        return factory(**arguments)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        client = self._client(request)
        response = client.embeddings.create(
            model=self.config.model_identifier,
            input=request.text,
            encoding_format="float",
        )
        body = _response_mapping(response)
        data = body.get("data")
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise EmbeddingError(
                "provider returned other than exactly one embedding",
                code="embedding_response_malformed",
            )
        coordinates = data[0].get("embedding")
        if not isinstance(coordinates, list) or not coordinates:
            raise EmbeddingError(
                "provider embedding is not a non-empty array",
                code="embedding_response_malformed",
            )
        if len(coordinates) != self.config.dimension:
            raise EmbeddingError(
                f"provider returned dimension {len(coordinates)}, "
                f"partition declares {self.config.dimension}",
                code="embedding_dimension_mismatch",
            )
        usage = body.get("usage")
        if not isinstance(usage, dict):
            raise EmbeddingError("provider reported no usage",
                                 code="embedding_usage_unavailable")
        prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
        if not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool):
            raise EmbeddingError("provider reported no integer input-token count",
                                 code="embedding_usage_unavailable")
        # A provider that reports completion tokens for an embeddings call is
        # not describing an embeddings call. Refuse rather than coerce to zero.
        for name in ("completion_tokens", "output_tokens"):
            reported = usage.get(name)
            if isinstance(reported, int) and not isinstance(reported, bool) and reported != 0:
                raise EmbeddingError(
                    f"provider reported {name}={reported} for an embeddings call",
                    code="output_tokens_not_zero",
                )
        request_id = body.get("id")
        return EmbeddingResult(
            provider=self.config.provider,
            model_identifier=str(body.get("model") or self.config.model_identifier),
            provider_coordinates=tuple(coordinates),
            usage=EmbeddingUsage(input_tokens=prompt_tokens, usage_source="api_reported"),
            provider_request_id=request_id if isinstance(request_id, str) else None,
            capabilities=self.config.capabilities,
        )


def _response_mapping(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    for method_name in ("to_dict", "model_dump"):
        method = getattr(response, method_name, None)
        if callable(method):
            value = method()
            if isinstance(value, dict):
                return value
    raise EmbeddingError("provider response is not a supported mapping",
                         code="embedding_response_malformed")


class ScriptedEmbeddingGateway:
    """Deterministic offline adapter whose vectors are supplied by the caller.

    Its results are project-authored, which `gateway_corpus_provenance` records.
    It makes no network call and holds no credential.
    """

    def __init__(
        self,
        *,
        provider: str,
        model_identifier: str,
        vectors: Mapping[str, Sequence[float]],
        input_tokens: Mapping[str, int] | None = None,
    ) -> None:
        if provider not in SUPPORTED_EMBEDDING_PROVIDERS:
            raise EmbeddingError(
                f"no embedding adapter for provider {provider!r}",
                code="embedding_provider_unsupported",
            )
        self.provider = provider
        self.model_identifier = model_identifier
        self._vectors = {key: tuple(value) for key, value in sorted(vectors.items())}
        self._input_tokens = dict(sorted((input_tokens or {}).items()))
        self.requests: list[EmbeddingRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.requests.append(request)
        try:
            coordinates = self._vectors[request.document_id]
        except KeyError as error:
            raise EmbeddingError(
                f"scripted gateway has no vector for {request.document_id}",
                code="embedding_script_exhausted",
            ) from error
        return EmbeddingResult(
            provider=self.provider,
            model_identifier=self.model_identifier,
            provider_coordinates=coordinates,
            usage=EmbeddingUsage(
                input_tokens=self._input_tokens.get(request.document_id, 1),
                usage_source="fixture",
            ),
            provider_request_id=f"scripted:{request.document_id}",
        )


class ForbiddingEmbeddingGateway:
    """Raises on any call. The instrument for `pr.rebuild-makes-no-provider-call`.

    A replay must reproduce the manifest hash with this installed, which is only
    meaningful because a call through it is loud rather than silent.
    """

    def __init__(self) -> None:
        self.attempts = 0

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        self.attempts += 1
        raise ProviderCallForbiddenError(
            f"a replay must not call a provider (attempted for {request.document_id})"
        )


#: Adapters that legitimately speak to a provider. Fail-closed: membership is
#: the ONLY route to a ``provider_embedded`` manifest.
LIVE_EMBEDDING_GATEWAY_TYPES: tuple[type, ...] = (OpenAIEmbeddingGateway,)


def gateway_corpus_provenance(gateway: EmbeddingGateway) -> str:
    if isinstance(gateway, LIVE_EMBEDDING_GATEWAY_TYPES):
        return CORPUS_PROVENANCE_PROVIDER_EMBEDDED
    return CORPUS_PROVENANCE_PROJECT_AUTHORED


__all__ = [
    "AZURE_SETTING_VARIABLES",
    "EMBEDDING_ADAPTER_VERSION",
    "ForbiddingEmbeddingGateway",
    "LIVE_EMBEDDING_GATEWAY_TYPES",
    "OpenAIEmbeddingConfig",
    "OpenAIEmbeddingGateway",
    "ScriptedEmbeddingGateway",
    "azure_openai_embedding_config",
    "gateway_corpus_provenance",
    "openai_embedding_config",
]
