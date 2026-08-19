"""Provider-neutral model contract plus deterministic and opt-in adapters."""

from __future__ import annotations

import json
import importlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import PHASE2_SCHEMA_VERSION
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


class StructuredOutputError(ValueError):
    pass


def validate_structured_output(purpose: str, raw: str, *, schema_dir: Path | None = None) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise StructuredOutputError(f"invalid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise StructuredOutputError("structured output must be an object")
    directory = schema_dir or Path(__file__).resolve().parents[3] / "schemas"
    schema = json.loads((directory / f"model-{purpose}-v1.schema.json").read_text(encoding="utf-8"))
    _validate_canonical_schema(value, schema, "$")
    if purpose == "proposer":
        allowed = {"schema_version", "result_type", "target_claim_id", "mathematical_payload", "declared_rationale", "referenced_entity_ids"}
        _exact_fields(value, allowed)
        if value["schema_version"] != PHASE2_SCHEMA_VERSION or value["result_type"] not in {"candidate_claim", "proof_attempt", "counterexample", "failure"}:
            raise StructuredOutputError("unsupported proposer version or result type")
        _nonempty_string(value["target_claim_id"], "target_claim_id")
        _string(value["declared_rationale"], "declared_rationale", maximum=2000)
        _unique_strings(value["referenced_entity_ids"], "referenced_entity_ids")
        payload = value["mathematical_payload"]
        if not isinstance(payload, dict):
            raise StructuredOutputError("mathematical_payload must be an object")
        _exact_fields(payload, {"statement", "steps", "witness"})
        _string(payload["statement"], "mathematical_payload.statement")
        _unique_strings(payload["steps"], "mathematical_payload.steps", unique=False)
        if payload["witness"] is not None:
            _string(payload["witness"], "mathematical_payload.witness")
        return value
    if purpose == "verifier":
        allowed = {"schema_version", "result_type", "target_claim_id", "candidate_artifact_hash", "findings", "declared_rationale", "recommendation"}
        _exact_fields(value, allowed)
        if value["schema_version"] != PHASE2_SCHEMA_VERSION or value["result_type"] not in {"finding", "inconclusive", "failure"}:
            raise StructuredOutputError("unsupported verifier version or result type")
        _nonempty_string(value["target_claim_id"], "target_claim_id")
        if not isinstance(value["candidate_artifact_hash"], str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value["candidate_artifact_hash"]):
            raise StructuredOutputError("candidate_artifact_hash is invalid")
        if value["recommendation"] not in {"manual_review", "reject", "unresolved"}:
            raise StructuredOutputError("invalid verifier recommendation")
        _string(value["declared_rationale"], "declared_rationale", maximum=2000)
        if not isinstance(value["findings"], list):
            raise StructuredOutputError("findings must be an array")
        for index, finding in enumerate(value["findings"]):
            if not isinstance(finding, dict):
                raise StructuredOutputError(f"findings[{index}] must be an object")
            _exact_fields(finding, {"code", "outcome", "detail", "referenced_entity_ids"})
            _nonempty_string(finding["code"], f"findings[{index}].code")
            if finding["outcome"] not in {"supports", "contradicts", "unresolved"}:
                raise StructuredOutputError(f"findings[{index}].outcome is invalid")
            _string(finding["detail"], f"findings[{index}].detail")
            _unique_strings(finding["referenced_entity_ids"], f"findings[{index}].referenced_entity_ids")
        forbidden = {"warrant", "warrant_kind", "claim_status", "truth_status"}
        if forbidden.intersection(value):
            raise StructuredOutputError("verifier may not award warrants or claim status")
        return value
    raise ValueError(f"unknown structured output purpose: {purpose}")


def _exact_fields(value: dict[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise StructuredOutputError(f"fields differ: expected {sorted(expected)}, got {sorted(value)}")


def _string(value: Any, path: str, *, maximum: int | None = None) -> None:
    if not isinstance(value, str) or (maximum is not None and len(value) > maximum):
        raise StructuredOutputError(f"{path} must be a string" + (f" of at most {maximum} characters" if maximum else ""))


def _nonempty_string(value: Any, path: str) -> None:
    _string(value, path)
    if not value:
        raise StructuredOutputError(f"{path} must be non-empty")


def _unique_strings(value: Any, path: str, *, unique: bool = True) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise StructuredOutputError(f"{path} must be an array of strings")
    if unique and len(value) != len(set(value)):
        raise StructuredOutputError(f"{path} must contain unique values")


def _validate_canonical_schema(value: Any, schema: dict[str, Any], path: str) -> None:
    """Enforce the canonical subset locally, including projected-out constraints."""

    declared = schema.get("type")
    if declared is not None:
        types = declared if isinstance(declared, list) else [declared]
        if not any(_matches_type(value, item) for item in types):
            raise StructuredOutputError(f"{path} does not match canonical type {declared!r}")
    if "const" in schema and value != schema["const"]:
        raise StructuredOutputError(f"{path} does not match canonical const")
    if "enum" in schema and value not in schema["enum"]:
        raise StructuredOutputError(f"{path} is not in canonical enum")
    if "anyOf" in schema:
        matched = 0
        for branch in schema["anyOf"]:
            try:
                _validate_canonical_schema(value, branch, path)
            except StructuredOutputError:
                continue
            matched += 1
        if matched == 0:
            raise StructuredOutputError(f"{path} does not match canonical anyOf")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        missing = [name for name in required if name not in value]
        if missing:
            raise StructuredOutputError(f"{path} is missing required fields {missing}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise StructuredOutputError(f"{path} has additional fields {extra}")
        for name, child in properties.items():
            if name in value:
                _validate_canonical_schema(value[name], child, f"{path}.{name}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise StructuredOutputError(f"{path} has fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise StructuredOutputError(f"{path} has more than {schema['maxItems']} items")
        if schema.get("uniqueItems") and len({canonical_json(item) for item in value}) != len(value):
            raise StructuredOutputError(f"{path} must contain unique items")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_canonical_schema(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise StructuredOutputError(f"{path} is shorter than canonical minimum")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise StructuredOutputError(f"{path} exceeds canonical maximum")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise StructuredOutputError(f"{path} does not match canonical pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        checks = (
            ("minimum", lambda left, right: left >= right),
            ("exclusiveMinimum", lambda left, right: left > right),
            ("maximum", lambda left, right: left <= right),
            ("exclusiveMaximum", lambda left, right: left < right),
        )
        for keyword, comparison in checks:
            if keyword in schema and not comparison(value, schema[keyword]):
                raise StructuredOutputError(f"{path} violates canonical {keyword}")
        if "multipleOf" in schema and value % schema["multipleOf"] != 0:
            raise StructuredOutputError(f"{path} violates canonical multipleOf")


def _matches_type(value: Any, declared: str) -> bool:
    return {
        "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "string": isinstance(value, str),
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }.get(declared, False)


class ScriptedModelGateway:
    """Deterministic adapter whose responses are supplied by the caller."""

    def __init__(self, scripts: dict[str, list[ModelResult]]) -> None:
        self._scripts = {key: list(value) for key, value in scripts.items()}
        self.requests: list[ModelRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def prepare(self, request: ModelRequest) -> ProviderSchemaPreparation | None:
        return None

    def complete(
        self, request: ModelRequest, preparation: ProviderSchemaPreparation | None = None,
    ) -> ModelResult:
        self.requests.append(request)
        queue = self._scripts.get(request.purpose, [])
        if not queue:
            return ModelResult(
                status=ModelResultStatus.FAILED, provider="scripted", model_identifier="scripted-v1",
                capabilities=("structured_output", "deterministic"), structured_output=None,
                declared_rationale=None, refusal=None,
                usage=ModelUsage(input_tokens=0, output_tokens=0, total_tokens=0, usage_source="fixture"),
                retry_classification="fatal:no_script",
            )
        return queue.pop(0)


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenAIProviderConfig:
    schema_version: str = PHASE2_SCHEMA_VERSION
    model_identifier: str
    endpoint: str = "https://api.openai.com/v1/responses"
    api_key_env: str = "OPENAI_API_KEY"
    capabilities: tuple[str, ...] = field(default=("responses_api", "structured_output", "refusal"))


OPENAI_ADAPTER_VERSION = "openai-responses-adapter/2.1.0"
OPENAI_SDK_PINNED_VERSION = "3.3.0"
DIAGNOSTIC_TEXT_LIMIT_BYTES = 4_096


class OpenAIResponsesGateway:
    """Opt-in SDK adapter with a fail-closed provider schema boundary."""

    def __init__(
        self,
        config: OpenAIProviderConfig,
        *,
        sdk_module: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self._sdk_module = sdk_module
        self._client_factory = client_factory

    def prepare(self, request: ModelRequest) -> ProviderSchemaPreparation:
        return project_openai_schema(request.response_schema)

    def complete(
        self, request: ModelRequest, preparation: ProviderSchemaPreparation | None = None,
    ) -> ModelResult:
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.config.api_key_env} is not configured")
        prepared = preparation or self.prepare(request)
        sdk = self._sdk_module or _load_openai_sdk()
        base_url = _base_url(self.config.endpoint)
        factory = self._client_factory or sdk.OpenAI
        client = factory(
            api_key=api_key,
            base_url=base_url,
            timeout=request.timeout_milliseconds / 1000,
            max_retries=0,
        )
        payload = {
            "model": self.config.model_identifier,
            "input": [
                {"role": "developer", "content": request.template_text},
                {"role": "user", "content": request.serialized_context},
            ],
            "store": False,
            "max_output_tokens": request.max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": f"adaivy_{request.purpose}_v1",
                    "strict": True,
                    "schema": json.loads(prepared.provider_schema_json),
                }
            },
        }
        try:
            response = client.responses.create(**payload)
        except sdk.APIStatusError as error:
            retryable = error.status_code in {408, 409, 429} or error.status_code >= 500
            diagnostic = _status_diagnostic(
                error,
                api_key=api_key,
                sdk_version=str(getattr(sdk, "__version__", "unknown")),
                config=self.config,
                request_schema_hash=prepared.provider_schema_hash,
            )
            return _failure(
                self.config,
                ModelResultStatus.FAILED,
                ("retryable" if retryable else "fatal") + f":http_{error.status_code}",
                provider_request_id=diagnostic.provider_request_id,
                provider_failure=diagnostic,
            )
        except sdk.APITimeoutError:
            return _failure(self.config, ModelResultStatus.TIMED_OUT, "retryable:timeout")
        except sdk.APIConnectionError:
            return _failure(self.config, ModelResultStatus.FAILED, "retryable:transport")
        try:
            body = _response_mapping(response)
        except (TypeError, ValueError):
            return _failure(self.config, ModelResultStatus.FAILED, "retryable:response_decode")

        usage_value = body.get("usage")
        usage_complete = isinstance(usage_value, dict) and all(
            isinstance(usage_value.get(field), int) and not isinstance(usage_value.get(field), bool)
            and usage_value[field] >= 0
            for field in ("input_tokens", "output_tokens", "total_tokens")
        )
        usage = ModelUsage(
            input_tokens=usage_value["input_tokens"] if usage_complete else 0,
            output_tokens=usage_value["output_tokens"] if usage_complete else 0,
            total_tokens=usage_value["total_tokens"] if usage_complete else 0,
            usage_source="api_reported" if usage_complete else "unavailable",
        )
        response_status = str(body.get("status") or "completed")
        provider_request_id = body.get("id") if isinstance(body.get("id"), str) else None
        if response_status == "incomplete":
            details = body.get("incomplete_details") or {}
            reason = str(details.get("reason") or "unspecified") if isinstance(details, dict) else "unspecified"
            return ModelResult(
                status=ModelResultStatus.INCOMPLETE, provider="openai",
                model_identifier=body.get("model") or self.config.model_identifier,
                capabilities=self.config.capabilities, structured_output=None,
                declared_rationale=None, refusal=None, usage=usage,
                retry_classification="not_retryable:incomplete_response",
                provider_request_id=provider_request_id, incomplete_reason=reason[:2000],
            )
        if response_status in {"failed", "cancelled"}:
            return ModelResult(
                status=ModelResultStatus.FAILED, provider="openai",
                model_identifier=body.get("model") or self.config.model_identifier,
                capabilities=self.config.capabilities, structured_output=None,
                declared_rationale=None, refusal=None, usage=usage,
                retry_classification=f"not_retryable:response_{response_status}",
                provider_request_id=provider_request_id,
            )
        refusal: str | None = None
        output_text: str | None = None
        for item in body.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") == "refusal":
                    refusal = str(content.get("refusal") or "provider refusal")
                elif content.get("type") == "output_text":
                    output_text = content.get("text")
        if refusal is not None:
            return ModelResult(
                status=ModelResultStatus.REFUSED, provider="openai", model_identifier=body.get("model") or self.config.model_identifier,
                capabilities=self.config.capabilities, structured_output=None, declared_rationale=None,
                refusal=refusal[:2000], usage=usage, retry_classification="not_retryable:refusal",
                provider_request_id=provider_request_id,
            )
        if response_status != "completed" or output_text is None or not usage_complete:
            return ModelResult(
                status=ModelResultStatus.MALFORMED, provider="openai",
                model_identifier=body.get("model") or self.config.model_identifier,
                capabilities=self.config.capabilities, structured_output=None,
                declared_rationale=None, refusal=None, usage=usage,
                retry_classification="fatal:missing_output_status_or_usage",
                provider_request_id=provider_request_id,
            )
        return ModelResult(
            status=ModelResultStatus.SUCCEEDED, provider="openai", model_identifier=body.get("model") or self.config.model_identifier,
            capabilities=self.config.capabilities, structured_output=output_text,
            declared_rationale=None, refusal=None, usage=usage, retry_classification="none",
            provider_request_id=provider_request_id,
        )


def _failure(
    config: OpenAIProviderConfig,
    status: ModelResultStatus,
    retry: str,
    *,
    provider_request_id: str | None = None,
    provider_failure: ProviderFailureDiagnostic | None = None,
) -> ModelResult:
    return ModelResult(
        status=status, provider="openai", model_identifier=config.model_identifier,
        capabilities=config.capabilities, structured_output=None, declared_rationale=None,
        refusal=None, usage=ModelUsage(input_tokens=0, output_tokens=0, total_tokens=0, usage_source="unavailable"),
        retry_classification=retry, provider_request_id=provider_request_id,
        provider_failure=provider_failure,
    )


def _load_openai_sdk() -> Any:
    try:
        return importlib.import_module("openai")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "openai SDK is not installed; install the pinned Phase 2 provider dependency"
        ) from error


def openai_sdk_version() -> str | None:
    try:
        sdk = importlib.import_module("openai")
    except ModuleNotFoundError:
        return None
    return str(getattr(sdk, "__version__", "unknown"))


def _base_url(endpoint: str) -> str:
    suffix = "/responses"
    if not endpoint.startswith("https://") or not endpoint.endswith(suffix):
        raise ValueError("OpenAI endpoint must be an HTTPS /responses endpoint")
    return endpoint[: -len(suffix)]


def _response_mapping(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    for method_name in ("to_dict", "model_dump"):
        method = getattr(response, method_name, None)
        if callable(method):
            value = method()
            if isinstance(value, dict):
                return value
    raise TypeError("provider response is not a supported mapping")


def _status_diagnostic(
    error: Any,
    *,
    api_key: str,
    sdk_version: str,
    config: OpenAIProviderConfig,
    request_schema_hash: str,
) -> ProviderFailureDiagnostic:
    response = error.response
    body_bytes = _response_body_bytes(response, getattr(error, "body", None))
    parsed = _parse_body_for_diagnostic(body_bytes, getattr(error, "body", None))
    sanitized = redact_secrets(parsed, (api_key,))
    if isinstance(sanitized, str):
        rendered = sanitized
    else:
        rendered = canonical_json(sanitized)
    preview, truncated = _bounded_utf8(rendered, DIAGNOSTIC_TEXT_LIMIT_BYTES)
    error_body = getattr(error, "body", None)
    if isinstance(error_body, dict) and isinstance(error_body.get("error"), dict):
        error_body = error_body["error"]
    if not isinstance(error_body, dict):
        error_body = {}
    message = error_body.get("message") or getattr(error, "message", None)
    sanitized_message = redact_secrets(str(message), (api_key,))[:2_000] if message is not None else None
    headers = getattr(response, "headers", None)
    content_type = (
        headers.get("content-type") or headers.get("Content-Type")
        if headers is not None else None
    )
    return ProviderFailureDiagnostic(
        http_status_code=int(error.status_code),
        sdk_exception_class=type(error).__name__,
        provider_request_id=getattr(error, "request_id", None),
        provider_error_type=_optional_string(error_body.get("type") or getattr(error, "type", None)),
        provider_error_code=_optional_string(error_body.get("code") or getattr(error, "code", None)),
        provider_error_param=_optional_string(error_body.get("param") or getattr(error, "param", None)),
        provider_error_message=sanitized_message,
        response_content_type=_optional_string(content_type),
        response_body_sha256=sha256_bytes(body_bytes),
        response_body_byte_length=len(body_bytes),
        response_body_preview=preview,
        response_body_preview_truncated=truncated,
        diagnostic_text_limit_bytes=DIAGNOSTIC_TEXT_LIMIT_BYTES,
        adapter_version=OPENAI_ADAPTER_VERSION,
        sdk_version=sdk_version,
        model_identifier=config.model_identifier,
        endpoint=config.endpoint,
        request_schema_hash=request_schema_hash,
    )


def _response_body_bytes(response: Any, fallback: Any) -> bytes:
    content = getattr(response, "content", None)
    if callable(content):
        content = content()
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    read = getattr(response, "read", None)
    if callable(read):
        value = read()
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return value.encode("utf-8")
    if fallback is None:
        return b""
    if isinstance(fallback, str):
        return fallback.encode("utf-8")
    return canonical_json(fallback).encode("utf-8")


def _parse_body_for_diagnostic(body: bytes, fallback: Any) -> Any:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        if body:
            return body.decode("utf-8", errors="replace")
        return fallback if fallback is not None else ""


def _bounded_utf8(value: str, limit: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value, False
    marker = b"...[TRUNCATED]"
    kept = encoded[: max(0, limit - len(marker))]
    while kept:
        try:
            return (kept + marker).decode("utf-8"), True
        except UnicodeDecodeError:
            kept = kept[:-1]
    return marker[:limit].decode("ascii", errors="ignore"), True


def _optional_string(value: Any) -> str | None:
    return str(value)[:2_000] if value is not None else None


_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
)


def redact_secrets(value: Any, secrets: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        secret_keys = {
            "api_key", "api-key", "x-api-key", "authorization", "proxy-authorization",
            "cookie", "set-cookie", "secret", "access_token", "refresh_token",
        }
        return {key: ("[REDACTED]" if key.lower() in secret_keys else redact_secrets(item, secrets)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item, secrets) for item in value)
    if isinstance(value, str):
        result = value
        for secret in secrets:
            if secret:
                result = result.replace(secret, "[REDACTED]")
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub("[REDACTED]", result)
        return result
    return value
