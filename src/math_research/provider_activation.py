"""Shared static and live provider-activation boundary.

The ordinary provider preflight is deliberately offline.  A passing static
preflight therefore says nothing about whether a credential is accepted by the
configured endpoint.  This module keeps that result separate from an explicit,
single-request live observation.  The actual transport is an injected port: no
network package is imported here and the offline suite uses only scripted
callables.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Mapping

from .domain.entities import OpaqueId
from .phase2.live_config import LiveRunConfiguration
from .phase2.live_gate import preflight_live_gate
from .phase2.model_gateway import redact_secrets
from .phase2.pricing import estimate_cost_microusd
from .phase2.provider_registry import provider_secret_values, provider_spec
from .phase2.records import (
    ModelRequest,
    ModelResult,
    ModelResultStatus,
    PricingSnapshot,
    ProviderFailureDiagnostic,
)
from .phase2.ports import ModelGateway
from .phase2.serialization import canonical_hash, canonical_json, sha256_bytes


PROVIDER_ACTIVATION_SCHEMA_VERSION = "1.0.0"
LIVE_PROBE_ACKNOWLEDGEMENT = "I AUTHORIZE ONE LIVE PROVIDER ACTIVATION PROBE"
PROBE_INPUT_TOKEN_RESERVE = 512
PROBE_MAX_OUTPUT_TOKENS = 128
PROBE_TIMEOUT_MILLISECONDS = 30_000
PROBE_PROMPT = (
    "Return exactly {\"ok\":true}. This request checks the configured route, "
    "authentication, model identity, and strict structured output; it performs no research."
)
PROBE_SCHEMA = canonical_json({
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"const": True}},
})


@dataclass(frozen=True, slots=True, kw_only=True)
class StaticProviderPreflight:
    """Offline configuration result; never evidence of live readiness."""

    schema_version: str = PROVIDER_ACTIVATION_SCHEMA_VERSION
    status: str
    provider: str
    model_identifier: str
    configuration_hash: str
    pricing_snapshot_hash: str
    route_hash: str
    missing_variables: tuple[str, ...]
    failed_checks: tuple[str, ...]
    reserved_probe_cost_microusd: int
    network_call_performed: bool = False
    operational_readiness: str = "not_tested"


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderProbeRequest:
    """The complete bounded instruction supplied to a live probe port."""

    schema_version: str = PROVIDER_ACTIVATION_SCHEMA_VERSION
    purpose: str = "provider_activation_probe"
    provider: str
    model_identifier: str
    configuration_hash: str
    pricing_snapshot_hash: str
    route_hash: str
    timeout_milliseconds: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_microusd: int
    max_attempts: int = 1
    max_retries: int = 0


ProviderProbePort = Callable[[ProviderProbeRequest], ModelResult]


class GatewayProviderProbe:
    """Execute the one activation request through AdaIvy's admitted gateway."""

    def __init__(self, configuration: LiveRunConfiguration, gateway: ModelGateway) -> None:
        self.configuration = configuration
        self.gateway = gateway
        self.called = False

    def __call__(self, request: ProviderProbeRequest) -> ModelResult:
        if self.called:
            raise ValueError("provider activation probe is single-use")
        if (
            request.provider != self.configuration.provider
            or request.model_identifier != self.configuration.model_identifier
            or request.configuration_hash != self.configuration.content_hash
            or request.max_attempts != 1
            or request.max_retries != 0
        ):
            raise ValueError("provider activation request does not match its configuration")
        self.called = True
        model_request = ModelRequest(
            request_id=OpaqueId(
                "request.provider-activation."
                + self.configuration.configuration_id.value
            ),
            run_id=OpaqueId(
                "run.provider-activation." + self.configuration.configuration_id.value
            ),
            purpose="provider_activation_probe",
            template_id="provider.activation",
            template_version=PROVIDER_ACTIVATION_SCHEMA_VERSION,
            template_hash=sha256_bytes(PROBE_PROMPT.encode("utf-8")),
            template_text=PROBE_PROMPT,
            serialized_context=canonical_json({
                "configuration_hash": request.configuration_hash,
                "pricing_snapshot_hash": request.pricing_snapshot_hash,
                "route_hash": request.route_hash,
                "research_content": None,
            }),
            response_schema=PROBE_SCHEMA,
            referenced_entity_ids=(),
            timeout_milliseconds=request.timeout_milliseconds,
            max_output_tokens=request.max_output_tokens,
        )
        prepared = self.gateway.prepare(model_request)
        return self.gateway.complete(model_request, prepared)


@dataclass(frozen=True, slots=True, kw_only=True)
class SanitizedProbeFailure:
    """Bounded provider failure detail with the endpoint retained only by hash."""

    http_status_code: int
    sdk_exception_class: str
    provider_request_id: str | None
    provider_error_type: str | None
    provider_error_code: str | None
    provider_error_param: str | None
    provider_error_message: str | None
    response_content_type: str | None
    response_body_sha256: str
    response_body_byte_length: int
    response_body_preview: str
    response_body_preview_truncated: bool
    adapter_version: str
    sdk_version: str
    endpoint_hash: str
    request_schema_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LiveProviderProbeResult:
    """One live observation.  It is operational evidence, never mathematical evidence."""

    schema_version: str = PROVIDER_ACTIVATION_SCHEMA_VERSION
    probe_status: str
    provider: str
    model_identifier: str
    configuration_hash: str
    pricing_snapshot_hash: str
    route_hash: str
    probe_request_hash: str | None
    observed_at: str
    acknowledgement_confirmed: bool
    static_preflight_status: str
    endpoint_reachability: str
    authentication_status: str
    deployment_route_status: str
    provider_identity_status: str
    structured_output_capability: str
    operational_readiness: str
    failure_classification: str | None
    sanitized_failure: SanitizedProbeFailure | None
    requests_attempted: int
    responses_completed: int
    responses_succeeded: int
    responses_failed: int
    responses_incomplete: int
    usage_reported_calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost_microusd: int
    provider_request_id: str | None
    max_attempts: int = 1
    retries_performed: int = 0
    response_text_retained: bool = False
    epistemic_warrant_created: bool = False


def provider_route_hash(
    provider: str, environment: Mapping[str, str],
) -> str:
    """Hash exactly the non-secret settings that determine a provider route."""

    spec = provider_spec(provider)
    names = tuple(sorted(spec.required_settings + spec.optional_settings))
    return canonical_hash({
        "provider": provider,
        "settings": {name: environment.get(name) for name in names},
    })


def static_provider_preflight(
    configuration: LiveRunConfiguration,
    pricing: PricingSnapshot,
    *,
    environment: Mapping[str, str],
    installed_sdk_version: str | None = None,
) -> StaticProviderPreflight:
    """Run the existing no-socket preflight and label its scope honestly."""

    checked = preflight_live_gate(
        configuration,
        pricing,
        environment=environment,
        installed_sdk_version=installed_sdk_version,
    )
    reserved = estimate_cost_microusd(
        pricing,
        input_tokens=PROBE_INPUT_TOKEN_RESERVE,
        output_tokens=PROBE_MAX_OUTPUT_TOKENS,
    )
    failed = list(checked.failed_checks)
    if reserved > configuration.budget.max_cost_microusd:
        failed.append("probe_reserved_cost_exceeds_budget")
    if configuration.budget.max_attempts < 1:
        failed.append("probe_attempt_not_budgeted")
    status = "passed" if not checked.missing_variables and not failed else "failed"
    return StaticProviderPreflight(
        status=status,
        provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        configuration_hash=configuration.content_hash,
        pricing_snapshot_hash=pricing.content_hash,
        route_hash=provider_route_hash(configuration.provider, environment),
        missing_variables=checked.missing_variables,
        failed_checks=tuple(sorted(set(failed))),
        reserved_probe_cost_microusd=reserved,
    )


def run_live_provider_probe(
    static: StaticProviderPreflight,
    configuration: LiveRunConfiguration,
    pricing: PricingSnapshot,
    *,
    environment: Mapping[str, str],
    acknowledgement: str,
    observed_at: str,
    probe: ProviderProbePort,
) -> LiveProviderProbeResult:
    """Attempt one explicitly acknowledged probe, without retry or fallback."""

    current_route_hash = provider_route_hash(configuration.provider, environment)
    binding_failures: list[str] = []
    if static.configuration_hash != configuration.content_hash:
        binding_failures.append("configuration_hash_changed_after_static_preflight")
    if static.pricing_snapshot_hash != pricing.content_hash:
        binding_failures.append("pricing_snapshot_hash_changed_after_static_preflight")
    if static.route_hash != current_route_hash:
        binding_failures.append("route_hash_changed_after_static_preflight")
    if static.provider != configuration.provider or static.model_identifier != configuration.model_identifier:
        binding_failures.append("provider_or_model_changed_after_static_preflight")
    if acknowledgement != LIVE_PROBE_ACKNOWLEDGEMENT:
        binding_failures.append("live_probe_not_acknowledged")
    if static.status != "passed":
        binding_failures.append("static_preflight_not_passed")
    if binding_failures:
        return _not_executed(
            static, configuration, pricing, current_route_hash,
            observed_at=observed_at,
            acknowledgement_confirmed=acknowledgement == LIVE_PROBE_ACKNOWLEDGEMENT,
            failure_classification=";".join(sorted(set(binding_failures))),
        )

    request = ProviderProbeRequest(
        provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        configuration_hash=configuration.content_hash,
        pricing_snapshot_hash=pricing.content_hash,
        route_hash=current_route_hash,
        timeout_milliseconds=min(
            configuration.call_timeout_milliseconds, PROBE_TIMEOUT_MILLISECONDS,
        ),
        max_input_tokens=PROBE_INPUT_TOKEN_RESERVE,
        max_output_tokens=PROBE_MAX_OUTPUT_TOKENS,
        max_cost_microusd=static.reserved_probe_cost_microusd,
    )
    request_hash = canonical_hash(request)
    try:
        result = probe(request)
    except Exception as error:  # the exception message may contain a credential
        return LiveProviderProbeResult(
            probe_status="failed",
            provider=configuration.provider,
            model_identifier=configuration.model_identifier,
            configuration_hash=configuration.content_hash,
            pricing_snapshot_hash=pricing.content_hash,
            route_hash=current_route_hash,
            probe_request_hash=request_hash,
            observed_at=observed_at,
            acknowledgement_confirmed=True,
            static_preflight_status=static.status,
            endpoint_reachability="unreachable",
            authentication_status="indeterminate",
            deployment_route_status="indeterminate",
            provider_identity_status="not_tested",
            structured_output_capability="not_tested",
            operational_readiness="failed",
            failure_classification=f"probe_exception:{type(error).__name__}",
            sanitized_failure=None,
            requests_attempted=1,
            responses_completed=0,
            responses_succeeded=0,
            responses_failed=0,
            responses_incomplete=0,
            usage_reported_calls=0,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_microusd=0,
            provider_request_id=None,
        )

    return _classify_result(
        static, configuration, pricing, current_route_hash, request_hash,
        result=result, environment=environment, observed_at=observed_at,
    )


def _not_executed(
    static: StaticProviderPreflight,
    configuration: LiveRunConfiguration,
    pricing: PricingSnapshot,
    route_hash: str,
    *,
    observed_at: str,
    acknowledgement_confirmed: bool,
    failure_classification: str,
) -> LiveProviderProbeResult:
    return LiveProviderProbeResult(
        probe_status="not_executed",
        provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        configuration_hash=configuration.content_hash,
        pricing_snapshot_hash=pricing.content_hash,
        route_hash=route_hash,
        probe_request_hash=None,
        observed_at=observed_at,
        acknowledgement_confirmed=acknowledgement_confirmed,
        static_preflight_status=static.status,
        endpoint_reachability="not_tested",
        authentication_status="not_tested",
        deployment_route_status="not_tested",
        provider_identity_status="not_tested",
        structured_output_capability="not_tested",
        operational_readiness="not_tested",
        failure_classification=failure_classification,
        sanitized_failure=None,
        requests_attempted=0,
        responses_completed=0,
        responses_succeeded=0,
        responses_failed=0,
        responses_incomplete=0,
        usage_reported_calls=0,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_microusd=0,
        provider_request_id=None,
    )


def _classify_result(
    static: StaticProviderPreflight,
    configuration: LiveRunConfiguration,
    pricing: PricingSnapshot,
    route_hash: str,
    request_hash: str,
    *,
    result: ModelResult,
    environment: Mapping[str, str],
    observed_at: str,
) -> LiveProviderProbeResult:
    failure = result.provider_failure
    http_status = failure.http_status_code if failure is not None else None
    response_received = int(
        http_status is not None and http_status > 0
        or result.status in {
            ModelResultStatus.SUCCEEDED,
            ModelResultStatus.REFUSED,
            ModelResultStatus.INCOMPLETE,
            ModelResultStatus.MALFORMED,
        }
    )
    response_succeeded = int(result.status is ModelResultStatus.SUCCEEDED)
    response_failed = int(
        result.status in {
            ModelResultStatus.FAILED,
            ModelResultStatus.MALFORMED,
            ModelResultStatus.REFUSED,
        }
    )
    response_incomplete = int(
        result.status in {ModelResultStatus.INCOMPLETE, ModelResultStatus.TIMED_OUT}
    )
    if response_received:
        reachability = "reached"
    elif result.status is ModelResultStatus.TIMED_OUT:
        reachability = "indeterminate"
    else:
        reachability = "unreachable"

    if http_status == 401:
        authentication = "rejected"
    elif failure is None and response_received:
        authentication = "accepted"
    else:
        authentication = "indeterminate"

    if http_status == 404:
        route_status = "rejected"
    elif failure is None and response_received:
        route_status = "accepted"
    else:
        route_status = "indeterminate"

    identity_passed = (
        result.provider == configuration.provider
        and result.model_identifier == configuration.model_identifier
    )
    identity_status = "passed" if identity_passed else "failed"
    try:
        structured_value = json.loads(result.structured_output or "null")
    except json.JSONDecodeError:
        structured_value = None
    structured_passed = (
        result.status is ModelResultStatus.SUCCEEDED
        and structured_value == {"ok": True}
    )
    capability_status = "passed" if structured_passed else "failed"
    usage_reported = int(result.usage.usage_source != "unavailable")
    actual_cost = estimate_cost_microusd(
        pricing,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )
    within_bounds = (
        result.usage.input_tokens <= PROBE_INPUT_TOKEN_RESERVE
        and result.usage.output_tokens <= PROBE_MAX_OUTPUT_TOKENS
        and actual_cost <= static.reserved_probe_cost_microusd
    )
    ready = (
        reachability == "reached"
        and authentication == "accepted"
        and route_status == "accepted"
        and identity_passed
        and structured_passed
        and within_bounds
    )
    if not within_bounds:
        classification = "probe_bound_exceeded"
    elif not identity_passed:
        classification = "provider_identity_mismatch"
    elif ready:
        classification = None
    else:
        classification = result.retry_classification

    secrets = provider_secret_values(configuration.provider, environment)
    classification = _redacted_text(classification, secrets, limit=512)
    provider_request_id = _redacted_text(
        result.provider_request_id, secrets, limit=512,
    )
    return LiveProviderProbeResult(
        probe_status="passed" if ready else "failed",
        provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        configuration_hash=configuration.content_hash,
        pricing_snapshot_hash=pricing.content_hash,
        route_hash=route_hash,
        probe_request_hash=request_hash,
        observed_at=observed_at,
        acknowledgement_confirmed=True,
        static_preflight_status=static.status,
        endpoint_reachability=reachability,
        authentication_status=authentication,
        deployment_route_status=route_status,
        provider_identity_status=identity_status,
        structured_output_capability=capability_status,
        operational_readiness="passed" if ready else "failed",
        failure_classification=classification,
        sanitized_failure=(
            None if failure is None else _sanitize_failure(failure, secrets)
        ),
        requests_attempted=1,
        responses_completed=response_succeeded,
        responses_succeeded=response_succeeded,
        responses_failed=response_failed,
        responses_incomplete=response_incomplete,
        usage_reported_calls=usage_reported,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        estimated_cost_microusd=actual_cost,
        provider_request_id=provider_request_id,
    )


def _sanitize_failure(
    failure: ProviderFailureDiagnostic, secrets: tuple[str, ...],
) -> SanitizedProbeFailure:
    endpoint = _redacted_text(failure.endpoint, secrets) or ""
    return SanitizedProbeFailure(
        http_status_code=failure.http_status_code,
        sdk_exception_class=_redacted_text(
            failure.sdk_exception_class, secrets, limit=256,
        ) or "unknown",
        provider_request_id=_redacted_text(
            failure.provider_request_id, secrets, limit=512,
        ),
        provider_error_type=_redacted_text(
            failure.provider_error_type, secrets, limit=512,
        ),
        provider_error_code=_redacted_text(
            failure.provider_error_code, secrets, limit=512,
        ),
        provider_error_param=_redacted_text(
            failure.provider_error_param, secrets, limit=512,
        ),
        provider_error_message=_redacted_text(
            failure.provider_error_message, secrets, limit=2_000,
        ),
        response_content_type=_redacted_text(
            failure.response_content_type, secrets, limit=256,
        ),
        response_body_sha256=failure.response_body_sha256,
        response_body_byte_length=failure.response_body_byte_length,
        response_body_preview=_redacted_text(
            failure.response_body_preview, secrets,
        ) or "",
        response_body_preview_truncated=failure.response_body_preview_truncated,
        adapter_version=_redacted_text(
            failure.adapter_version, secrets, limit=256,
        ) or "unknown",
        sdk_version=_redacted_text(failure.sdk_version, secrets, limit=256) or "unknown",
        endpoint_hash=canonical_hash(endpoint),
        request_schema_hash=failure.request_schema_hash,
    )


def _redacted_text(
    value: str | None, secrets: tuple[str, ...], *, limit: int = 4_096,
) -> str | None:
    if value is None:
        return None
    sanitized = redact_secrets(value, secrets)
    return str(sanitized)[:limit]
