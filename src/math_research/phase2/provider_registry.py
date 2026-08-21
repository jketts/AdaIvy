"""One place that knows how to build and preflight each admitted provider.

ADR-0030 added five adapters beside the original OpenAI one. Without a registry
every caller would re-derive which credential a provider needs, which
capabilities its structured-output path requires, and which SDK version to
check -- and `preflight_live_gate` already demonstrated the failure mode by
reporting a missing ``OPENAI_API_KEY`` for a run that never involved OpenAI.

Nothing here enables a provider. Building a gateway performs no network call and
imports no SDK; a live call still requires the live-gate acknowledgement, a
pricing snapshot, and a passing preflight. Every returned gateway satisfies the
`ModelGateway` protocol, and a model result remains a proposal that carries no
warrant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import SUPPORTED_LIVE_PROVIDERS
from .anthropic_gateway import (
    ANTHROPIC_SDK_PACKAGE,
    ANTHROPIC_SDK_PINNED_VERSION,
    AnthropicMessagesGateway,
    AnthropicProviderConfig,
    anthropic_sdk_version,
)
from .bedrock_gateway import (
    BEDROCK_PROVIDER,
    BedrockInvokeGateway,
    BedrockProviderConfig,
)
from .env_file import NON_SECRET_PROVIDER_KEYS
from .model_gateway import (
    OPENAI_SDK_PINNED_VERSION,
    OpenAIProviderConfig,
    OpenAIResponsesGateway,
    openai_sdk_version,
)
from .openai_compatible_gateway import (
    OPENAI_COMPATIBLE_SDK_PACKAGE,
    OPENAI_COMPATIBLE_SDK_PINNED_VERSION,
    SUPPORTED_PROVIDERS as OPENAI_COMPATIBLE_PROVIDERS,
    OpenAICompatibleChatGateway,
    provider_config as openai_compatible_config,
)

UNCONFIRMED_SDK_VERSION = "UNCONFIRMED"


class UnknownProviderError(KeyError):
    """The provider is not admitted at the Phase 2 model boundary."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSpec:
    """What a provider needs before a live call can be attempted."""

    provider: str
    # Credentials that must be resolvable. Absence is a `missing_variables`
    # entry, not a failed check: nothing is wrong, something is unconfigured.
    required_credentials: tuple[str, ...]
    optional_credentials: tuple[str, ...] = ()
    # Non-secret operational settings that must be resolvable, read from
    # `.env.settings` rather than `.env`. Kept separate from credentials so the
    # two files' contents are derived from one declaration instead of a
    # hand-maintained exception list, and so a diagnostic can name a missing
    # endpoint without implying a missing secret. Absence is reported the same
    # way -- a `missing_variables` entry, because nothing is wrong yet.
    required_settings: tuple[str, ...] = ()
    optional_settings: tuple[str, ...] = ()
    # Capabilities the adapter must declare, all of them.
    required_capabilities: frozenset[str]
    # Acceptable ways of constraining output; at least one must be declared.
    # These are NOT interchangeable in strength: `structured_output` means the
    # provider enforces the schema, while `json_object_response_format` and
    # `prompt_embedded_schema` mean only that JSON was requested and the adapter
    # validates the result locally against the canonical schema. Both are safe --
    # neither can yield an unvalidated success -- but a run should be able to
    # tell which guarantee it actually got.
    output_mode_capabilities: frozenset[str]
    sdk_package: str | None
    sdk_pinned_version: str | None
    sdk_version_probe: Callable[[], str | None] | None
    build: Callable[..., Any]

    @property
    def requires_sdk(self) -> bool:
        """False when the adapter needs no third-party package at all."""
        return self.sdk_package is not None

    @property
    def sdk_version_is_confirmed(self) -> bool:
        """Whether a pinned version is actually known.

        Three distinct states, deliberately not collapsed: a provider needing no
        SDK has nothing to confirm and is therefore confirmed; a provider whose
        version is the ``UNCONFIRMED`` sentinel has no recorded wheel digest and
        cannot be pinned yet; anything else is a real pinned version.
        """
        if not self.requires_sdk:
            return True
        return (
            self.sdk_pinned_version is not None
            and self.sdk_pinned_version != UNCONFIRMED_SDK_VERSION
        )


def _build_openai(model_identifier: str, **kwargs: Any) -> OpenAIResponsesGateway:
    return OpenAIResponsesGateway(
        OpenAIProviderConfig(model_identifier=model_identifier), **kwargs
    )


def _build_anthropic(model_identifier: str, **kwargs: Any) -> AnthropicMessagesGateway:
    return AnthropicMessagesGateway(
        AnthropicProviderConfig(model_identifier=model_identifier), **kwargs
    )


def _build_bedrock(model_identifier: str, **kwargs: Any) -> BedrockInvokeGateway:
    region = kwargs.pop("region", None)
    return BedrockInvokeGateway(
        BedrockProviderConfig(model_identifier=model_identifier, region=region), **kwargs
    )


def _openai_compatible_builder(provider: str) -> Callable[..., Any]:
    def build(model_identifier: str, **kwargs: Any) -> OpenAICompatibleChatGateway:
        return OpenAICompatibleChatGateway(
            openai_compatible_config(provider, model_identifier=model_identifier),
            **kwargs,
        )

    return build


# Credential requirements per OpenAI-compatible provider. Every one of these is
# a secret and belongs in `.env`.
_OPENAI_COMPATIBLE_CREDENTIALS: dict[str, tuple[str, ...]] = {
    "minimax": ("MINIMAX_API_KEY",),
    "qwen_dashscope": ("DASHSCOPE_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "azure_openai": ("AZURE_OPENAI_API_KEY",),
}
# Non-secret settings, from `.env.settings`. Azure is not interchangeable with
# the Bearer-token providers: it needs an endpoint, a deployment, and an
# api-version as well as its key, and none of the three is a secret.
_OPENAI_COMPATIBLE_SETTINGS: dict[str, tuple[str, ...]] = {
    "azure_openai": (
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
    ),
}
_OPENAI_COMPATIBLE_OPTIONAL: dict[str, tuple[str, ...]] = {}
_OPENAI_COMPATIBLE_OPTIONAL_SETTINGS: dict[str, tuple[str, ...]] = {
    "minimax": ("MINIMAX_GROUP_ID",),
}


def _registry() -> dict[str, ProviderSpec]:
    specs: dict[str, ProviderSpec] = {
        "openai": ProviderSpec(
            provider="openai",
            required_credentials=("OPENAI_API_KEY",),
            required_capabilities=frozenset({"responses_api"}),
            output_mode_capabilities=frozenset({"structured_output"}),
            sdk_package="openai",
            sdk_pinned_version=OPENAI_SDK_PINNED_VERSION,
            sdk_version_probe=openai_sdk_version,
            build=_build_openai,
        ),
        "anthropic": ProviderSpec(
            provider="anthropic",
            required_credentials=("ANTHROPIC_API_KEY",),
            required_capabilities=frozenset({"messages_api"}),
            output_mode_capabilities=frozenset({"structured_output"}),
            sdk_package=ANTHROPIC_SDK_PACKAGE,
            sdk_pinned_version=ANTHROPIC_SDK_PINNED_VERSION,
            sdk_version_probe=anthropic_sdk_version,
            build=_build_anthropic,
        ),
        BEDROCK_PROVIDER: ProviderSpec(
            provider=BEDROCK_PROVIDER,
            required_credentials=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
            optional_credentials=("AWS_SESSION_TOKEN",),
            # The region is not a secret, and it is still required: Bedrock
            # fails closed without one rather than defaulting to a region.
            required_settings=("AWS_REGION",),
            required_capabilities=frozenset({"invoke_model", "sigv4"}),
            output_mode_capabilities=frozenset({"prompt_embedded_schema"}),
            # Signing is stdlib-only; there is no SDK to pin or probe.
            sdk_package=None,
            sdk_pinned_version=None,
            sdk_version_probe=None,
            build=_build_bedrock,
        ),
    }
    for provider in OPENAI_COMPATIBLE_PROVIDERS:
        specs[provider] = ProviderSpec(
            provider=provider,
            required_credentials=_OPENAI_COMPATIBLE_CREDENTIALS[provider],
            optional_credentials=_OPENAI_COMPATIBLE_OPTIONAL.get(provider, ()),
            required_settings=_OPENAI_COMPATIBLE_SETTINGS.get(provider, ()),
            optional_settings=_OPENAI_COMPATIBLE_OPTIONAL_SETTINGS.get(provider, ()),
            required_capabilities=frozenset({"openai_compatible_chat_completions"}),
            output_mode_capabilities=frozenset({
                "structured_output", "json_object_response_format",
            }),
            sdk_package=OPENAI_COMPATIBLE_SDK_PACKAGE,
            sdk_pinned_version=OPENAI_COMPATIBLE_SDK_PINNED_VERSION,
            sdk_version_probe=openai_sdk_version,
            build=_openai_compatible_builder(provider),
        )
    return specs


PROVIDER_SPECS: dict[str, ProviderSpec] = _registry()


def provider_spec(provider: str) -> ProviderSpec:
    try:
        return PROVIDER_SPECS[provider]
    except KeyError as error:
        raise UnknownProviderError(
            f"provider is not admitted at the Phase 2 model boundary: {provider}"
        ) from error


def build_gateway(provider: str, model_identifier: str, **kwargs: Any) -> Any:
    """Construct the adapter for `provider`. No network, no SDK import."""
    return provider_spec(provider).build(model_identifier, **kwargs)


def registered_providers() -> tuple[str, ...]:
    return tuple(sorted(PROVIDER_SPECS))


# Adapters whose non-secret config does not carry its own ``provider`` field.
# Keyed by class object, not class name, so a rename cannot silently mislabel a
# gateway's provider in a durable independence record.
_PROVIDER_BY_GATEWAY_TYPE: tuple[tuple[type, str], ...] = (
    (OpenAIResponsesGateway, "openai"),
    (AnthropicMessagesGateway, "anthropic"),
    (BedrockInvokeGateway, BEDROCK_PROVIDER),
)


def gateway_provider(gateway: Any) -> str | None:
    """Which admitted provider this gateway will call, or ``None`` if unknown.

    ADR-0041 needs this to *measure* verifier independence instead of trusting a
    declaration. ``None`` means the gateway has no provider identity at all -- a
    scripted fixture, for instance -- and the caller must then refuse rather
    than assume an independence claim.
    """
    declared = getattr(getattr(gateway, "config", None), "provider", None)
    if isinstance(declared, str) and declared in PROVIDER_SPECS:
        return declared
    for gateway_type, provider in _PROVIDER_BY_GATEWAY_TYPE:
        if isinstance(gateway, gateway_type):
            return provider
    return None


def provider_secret_variables(provider: str) -> tuple[str, ...]:
    """Credential variables for `provider` that carry secret material.

    Non-secret operational settings (region, Azure endpoint/deployment/api
    version, MiniMax group id) are excluded: they are configuration, they are
    legitimately recorded, and scanning persisted state for a value like
    ``us-east-1`` would report a false leak. Everything else is treated as
    secret, so a new credential is secret unless it is explicitly declared not
    to be.
    """
    spec = provider_spec(provider)
    return tuple(sorted(
        variable
        for variable in spec.required_credentials + spec.optional_credentials
        if variable not in NON_SECRET_PROVIDER_KEYS
    ))


def provider_secret_values(provider: str, environment: Any) -> tuple[str, ...]:
    """Configured secret values for `provider`, for redaction and leak scans.

    Returns values, so a caller must never place the result in a record: its only
    uses are `redact_secrets` and scanning persisted state for a leak. Sorted and
    de-duplicated so both are deterministic.
    """
    variables = provider_secret_variables(provider)
    return tuple(sorted({
        value for value in (
            (environment.get(name) or "").strip() for name in variables
        ) if value
    }))
