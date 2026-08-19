"""Deterministic projection into OpenAI's documented Structured Outputs subset.

The provider schema is an execution aid, never a canonical trust schema.
Constraints omitted here remain mandatory in the canonical post-response
validator.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from . import PHASE2_SCHEMA_VERSION
from .records import ProviderSchemaPreparation
from .serialization import canonical_bytes, canonical_json, sha256_bytes


OPENAI_STRUCTURED_OUTPUTS_DOC = "https://developers.openai.com/api/docs/guides/structured-outputs"
PROJECTION_IMPLEMENTATION = "openai-strict-schema-projection/1.1.0"
MAX_OBJECT_PROPERTIES = 5_000
MAX_NESTING_DEPTH = 10
MAX_ENUM_VALUES = 1_000
MAX_SCHEMA_STRING_BUDGET = 120_000
MAX_LARGE_ENUM_STRING_BUDGET = 15_000

_TYPES = {"string", "number", "boolean", "integer", "object", "array", "null"}
_METADATA_KEYWORDS = {
    "$schema": "JSON Schema dialect metadata is not part of the provider response contract",
    "$id": "canonical schema identity is retained outside the provider projection",
    "title": "display metadata is not needed by the provider response contract",
}
_LOCALLY_ENFORCED = {
    "uniqueItems": "canonical.array.unique_items",
    "minLength": "canonical.string.min_length",
    "maxLength": "canonical.string.max_length",
}
_FORBIDDEN_COMPOSITION = {
    "allOf", "not", "dependentRequired", "dependentSchemas", "if", "then", "else",
}
_EMITTED_KEYWORDS = {
    "type", "description", "properties", "required", "additionalProperties",
    "items", "enum", "const", "anyOf", "$defs", "$ref", "pattern", "format",
    "multipleOf", "maximum", "exclusiveMaximum", "minimum", "exclusiveMinimum",
    "minItems", "maxItems",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class SchemaTransformation:
    schema_version: str = PHASE2_SCHEMA_VERSION
    operation: str
    path: str
    keyword: str
    reason: str
    canonical_post_validation_rule: str
    inferred_value: str | None = None
    inference_source: str | None = None
    canonical_value_summary: str | None = None
    canonical_value_hash: str | None = None
    provider_only: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSchemaIssue:
    schema_version: str = PHASE2_SCHEMA_VERSION
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSchemaMetrics:
    schema_version: str = PHASE2_SCHEMA_VERSION
    property_count: int
    maximum_nesting_depth: int
    enum_value_count: int
    schema_string_budget_characters: int


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationManifest:
    schema_version: str = PHASE2_SCHEMA_VERSION
    provider: str = "openai"
    projection_implementation: str = PROJECTION_IMPLEMENTATION
    documentation_source: str = OPENAI_STRUCTURED_OUTPUTS_DOC
    canonical_schema_hash: str
    provider_schema_hash: str
    transformations: tuple[SchemaTransformation, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderSchemaCompatibilityReport:
    schema_version: str = PHASE2_SCHEMA_VERSION
    provider: str = "openai"
    projection_implementation: str = PROJECTION_IMPLEMENTATION
    documentation_source: str = OPENAI_STRUCTURED_OUTPUTS_DOC
    compatible: bool
    canonical_schema_hash: str
    provider_schema_hash: str | None
    issues: tuple[ProviderSchemaIssue, ...]
    metrics: ProviderSchemaMetrics | None


class ProviderSchemaError(ValueError):
    def __init__(self, report: ProviderSchemaCompatibilityReport) -> None:
        self.report = report
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in report.issues)
        super().__init__(details or "provider schema is incompatible")


def project_openai_schema(canonical_schema_text: str) -> ProviderSchemaPreparation:
    """Project and lint a canonical schema without changing its source bytes."""

    canonical_data = canonical_schema_text.encode("utf-8")
    canonical_schema_hash = sha256_bytes(canonical_data)
    issues: list[ProviderSchemaIssue] = []
    try:
        schema = _loads_schema(canonical_schema_text)
    except (ValueError, json.JSONDecodeError) as error:
        report = ProviderSchemaCompatibilityReport(
            compatible=False,
            canonical_schema_hash=canonical_schema_hash,
            provider_schema_hash=None,
            issues=(ProviderSchemaIssue(code="invalid_json", path="", message=str(error)),),
            metrics=None,
        )
        raise ProviderSchemaError(report) from error
    if not isinstance(schema, dict):
        issues.append(ProviderSchemaIssue(
            code="root_must_be_object", path="", message="schema root must be a JSON object",
        ))
        report = ProviderSchemaCompatibilityReport(
            compatible=False, canonical_schema_hash=canonical_schema_hash,
            provider_schema_hash=None, issues=tuple(issues), metrics=None,
        )
        raise ProviderSchemaError(report)

    transformations: list[SchemaTransformation] = []
    projected = _project_node(schema, "", transformations, issues, root=True)
    provider_schema_hash: str | None = None
    metrics: ProviderSchemaMetrics | None = None
    if not issues:
        provider_schema_hash = sha256_bytes(canonical_bytes(projected))
        metrics, lint_issues = lint_openai_schema(projected)
        issues.extend(lint_issues)
    report = ProviderSchemaCompatibilityReport(
        compatible=not issues,
        canonical_schema_hash=canonical_schema_hash,
        provider_schema_hash=provider_schema_hash,
        issues=tuple(sorted(issues, key=lambda item: (item.path, item.code, item.message))),
        metrics=metrics,
    )
    if issues or provider_schema_hash is None:
        raise ProviderSchemaError(report)

    transformations_tuple = tuple(sorted(
        transformations,
        key=lambda item: (item.path, item.operation, item.keyword, item.reason),
    ))
    manifest = TransformationManifest(
        canonical_schema_hash=canonical_schema_hash,
        provider_schema_hash=provider_schema_hash,
        transformations=transformations_tuple,
    )
    return ProviderSchemaPreparation(
        provider="openai",
        canonical_schema_hash=canonical_schema_hash,
        provider_schema_hash=provider_schema_hash,
        provider_schema_json=canonical_json(projected),
        transformation_manifest_json=canonical_json(manifest),
        compatibility_report_json=canonical_json(report),
        compatibility_report_text=render_compatibility_report(report, transformations_tuple),
    )


def lint_openai_schema(schema: dict[str, Any]) -> tuple[ProviderSchemaMetrics, tuple[ProviderSchemaIssue, ...]]:
    """Recursively validate the projected provider schema and documented limits."""

    issues: list[ProviderSchemaIssue] = []
    counters = {"properties": 0, "depth": 0, "enum": 0, "strings": 0}
    if schema.get("type") != "object":
        issues.append(ProviderSchemaIssue(
            code="root_must_be_object", path="/type", message="root type must be object",
        ))
    if "anyOf" in schema:
        issues.append(ProviderSchemaIssue(
            code="root_anyof_unsupported", path="/anyOf", message="root anyOf is not supported",
        ))
    _lint_node(schema, "", 1, counters, issues, schema)
    if counters["properties"] > MAX_OBJECT_PROPERTIES:
        issues.append(ProviderSchemaIssue(
            code="property_limit_exceeded", path="/properties",
            message=f"{counters['properties']} properties exceeds {MAX_OBJECT_PROPERTIES}",
        ))
    if counters["depth"] > MAX_NESTING_DEPTH:
        issues.append(ProviderSchemaIssue(
            code="nesting_limit_exceeded", path="",
            message=f"nesting depth {counters['depth']} exceeds {MAX_NESTING_DEPTH}",
        ))
    if counters["enum"] > MAX_ENUM_VALUES:
        issues.append(ProviderSchemaIssue(
            code="enum_limit_exceeded", path="",
            message=f"{counters['enum']} enum values exceeds {MAX_ENUM_VALUES}",
        ))
    if counters["strings"] > MAX_SCHEMA_STRING_BUDGET:
        issues.append(ProviderSchemaIssue(
            code="string_budget_exceeded", path="",
            message=f"schema string budget {counters['strings']} exceeds {MAX_SCHEMA_STRING_BUDGET}",
        ))
    try:
        first = canonical_bytes(schema)
        second = canonical_bytes(json.loads(first))
        if first != second:
            issues.append(ProviderSchemaIssue(
                code="non_deterministic_serialization", path="",
                message="canonical serialization is not byte-stable",
            ))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        issues.append(ProviderSchemaIssue(
            code="not_canonically_serializable", path="", message=str(error),
        ))
    metrics = ProviderSchemaMetrics(
        property_count=counters["properties"],
        maximum_nesting_depth=counters["depth"],
        enum_value_count=counters["enum"],
        schema_string_budget_characters=counters["strings"],
    )
    return metrics, tuple(sorted(issues, key=lambda item: (item.path, item.code, item.message)))


def render_compatibility_report(
    report: ProviderSchemaCompatibilityReport,
    transformations: tuple[SchemaTransformation, ...] = (),
) -> str:
    lines = [
        "# OpenAI Structured Outputs Compatibility Report",
        "",
        f"- Compatible: {'yes' if report.compatible else 'no'}",
        f"- Projection: `{report.projection_implementation}`",
        f"- Canonical schema hash: `{report.canonical_schema_hash}`",
        f"- Provider schema hash: `{report.provider_schema_hash or 'not-produced'}`",
        f"- Documentation: {report.documentation_source}",
    ]
    if report.metrics is not None:
        lines.extend([
            f"- Object properties: {report.metrics.property_count}/{MAX_OBJECT_PROPERTIES}",
            f"- Nesting depth: {report.metrics.maximum_nesting_depth}/{MAX_NESTING_DEPTH}",
            f"- Enum values: {report.metrics.enum_value_count}/{MAX_ENUM_VALUES}",
            f"- String budget: {report.metrics.schema_string_budget_characters}/{MAX_SCHEMA_STRING_BUDGET}",
        ])
    lines.extend(["", "## Issues", ""])
    lines.extend(
        f"- `{issue.code}` at `{issue.path or '/'}`: {issue.message}" for issue in report.issues
    )
    if not report.issues:
        lines.append("- None.")
    lines.extend(["", "## Transformations", ""])
    for item in transformations:
        inference = ""
        if item.inferred_value is not None:
            inference = (
                f"; inferred `{item.inferred_value}` from `{item.inference_source}`"
                f"; canonical values `{item.canonical_value_summary}`"
                f"; canonical value hash `{item.canonical_value_hash}`"
                f"; provider-only `{str(item.provider_only).lower()}`"
            )
        lines.append(
            f"- `{item.operation}` `{item.path or '/'}`: {item.reason}{inference}; "
            f"post-validation `{item.canonical_post_validation_rule}`."
        )
    if not transformations:
        lines.append("- None.")
    lines.extend([
        "",
        "The projected schema is provider-specific and is not a canonical trust schema. "
        "Every response is parsed and validated again against the unchanged canonical schema before trust-policy checks or proposal-only import.",
        "",
    ])
    return "\n".join(lines)


def _project_node(
    node: Any,
    path: str,
    transformations: list[SchemaTransformation],
    issues: list[ProviderSchemaIssue],
    *,
    root: bool = False,
) -> dict[str, Any]:
    if not isinstance(node, dict):
        issues.append(ProviderSchemaIssue(
            code="schema_node_not_object", path=path, message="schema node must be an object",
        ))
        return {}
    if root and "anyOf" in node:
        issues.append(ProviderSchemaIssue(
            code="root_anyof_unsupported", path="/anyOf", message="root anyOf is not supported",
        ))
    if root and node.get("type") != "object":
        issues.append(ProviderSchemaIssue(
            code="root_must_be_object", path="/type", message="root type must be object",
        ))

    projected: dict[str, Any] = {}
    for keyword in sorted(node):
        value = node[keyword]
        keyword_path = _pointer(path, keyword)
        if keyword in _METADATA_KEYWORDS:
            transformations.append(SchemaTransformation(
                operation="removed", path=keyword_path, keyword=keyword,
                reason=_METADATA_KEYWORDS[keyword],
                canonical_post_validation_rule="canonical.schema.identity_and_metadata_retained",
            ))
            continue
        if keyword in _LOCALLY_ENFORCED:
            transformations.append(SchemaTransformation(
                operation="removed", path=keyword_path, keyword=keyword,
                reason="constraint is not in the documented provider allowlist and remains locally enforced",
                canonical_post_validation_rule=_LOCALLY_ENFORCED[keyword],
            ))
            continue
        if keyword in _FORBIDDEN_COMPOSITION:
            issues.append(ProviderSchemaIssue(
                code="unsupported_composition_keyword", path=keyword_path,
                message=f"{keyword} is unsupported by OpenAI Structured Outputs",
            ))
            continue
        if keyword not in _EMITTED_KEYWORDS:
            issues.append(ProviderSchemaIssue(
                code="unsupported_keyword", path=keyword_path,
                message=f"unhandled schema keyword: {keyword}",
            ))
            continue
        if keyword in {"required", "additionalProperties"}:
            continue
        if keyword == "properties":
            if not isinstance(value, dict):
                issues.append(ProviderSchemaIssue(
                    code="invalid_properties", path=keyword_path, message="properties must be an object",
                ))
                continue
            projected[keyword] = {
                name: _project_node(child, _pointer(keyword_path, name), transformations, issues)
                for name, child in sorted(value.items())
            }
            continue
        if keyword == "$defs":
            if not isinstance(value, dict):
                issues.append(ProviderSchemaIssue(
                    code="invalid_definitions", path=keyword_path, message="$defs must be an object",
                ))
                continue
            projected[keyword] = {
                name: _project_node(child, _pointer(keyword_path, name), transformations, issues)
                for name, child in sorted(value.items())
            }
            continue
        if keyword == "items":
            projected[keyword] = _project_node(value, keyword_path, transformations, issues)
            continue
        if keyword == "anyOf":
            if not isinstance(value, list):
                issues.append(ProviderSchemaIssue(
                    code="invalid_anyof", path=keyword_path, message="anyOf must be an array",
                ))
                continue
            projected[keyword] = [
                _project_node(child, _pointer(keyword_path, str(index)), transformations, issues)
                for index, child in enumerate(value)
            ]
            continue
        if keyword == "type":
            if _provider_types(value, keyword_path, issues) is None:
                continue
        projected[keyword] = value

    _type_terminal_node(node, projected, path, transformations, issues)

    if node.get("type") == "object":
        properties = projected.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        original_required = node.get("required", [])
        if not isinstance(original_required, list) or any(not isinstance(item, str) for item in original_required):
            issues.append(ProviderSchemaIssue(
                code="invalid_required", path=_pointer(path, "required"), message="required must be an array of strings",
            ))
            original_required = []
        unknown_required = sorted(set(original_required) - set(properties))
        if unknown_required:
            issues.append(ProviderSchemaIssue(
                code="required_unknown_property", path=_pointer(path, "required"),
                message=f"required contains unknown properties: {unknown_required}",
            ))
        optional = sorted(set(properties) - set(original_required))
        for name in optional:
            property_path = _pointer(_pointer(path, "properties"), name)
            properties[name] = _make_nullable(properties[name], property_path, transformations, issues)
        all_required = sorted(properties)
        projected["required"] = all_required
        if original_required != all_required:
            transformations.append(SchemaTransformation(
                operation="rewritten" if "required" in node else "added",
                path=_pointer(path, "required"), keyword="required",
                reason="OpenAI Structured Outputs requires every object property to be required",
                canonical_post_validation_rule="canonical.object.original_required_and_optional_semantics",
            ))
        projected["additionalProperties"] = False
        if node.get("additionalProperties") is not False:
            transformations.append(SchemaTransformation(
                operation="rewritten" if "additionalProperties" in node else "added",
                path=_pointer(path, "additionalProperties"), keyword="additionalProperties",
                reason="OpenAI Structured Outputs requires additionalProperties false on every object",
                canonical_post_validation_rule="canonical.object.additional_properties",
            ))
    return projected


def _make_nullable(
    schema: dict[str, Any],
    path: str,
    transformations: list[SchemaTransformation],
    issues: list[ProviderSchemaIssue],
) -> dict[str, Any]:
    value = dict(schema)
    declared = value.get("type")
    if isinstance(declared, str):
        if declared != "null":
            value["type"] = [declared, "null"]
            transformations.append(SchemaTransformation(
                operation="rewritten", path=_pointer(path, "type"), keyword="type",
                reason="optional canonical field is represented as required and nullable for the provider",
                canonical_post_validation_rule="canonical.object.original_required_and_optional_semantics",
            ))
        return value
    if isinstance(declared, list):
        if "null" not in declared:
            value["type"] = [*declared, "null"]
            transformations.append(SchemaTransformation(
                operation="rewritten", path=_pointer(path, "type"), keyword="type",
                reason="optional canonical field is represented as required and nullable for the provider",
                canonical_post_validation_rule="canonical.object.original_required_and_optional_semantics",
            ))
        return value
    if "anyOf" in value and isinstance(value["anyOf"], list):
        value["anyOf"] = [*value["anyOf"], {"type": "null"}]
        transformations.append(SchemaTransformation(
            operation="rewritten", path=_pointer(path, "anyOf"), keyword="anyOf",
            reason="optional canonical field is represented as required and nullable for the provider",
            canonical_post_validation_rule="canonical.object.original_required_and_optional_semantics",
        ))
        return value
    issues.append(ProviderSchemaIssue(
        code="optional_field_not_representable", path=path,
        message="optional field has no supported type or anyOf declaration for nullable projection",
    ))
    return value


def _lint_node(
    node: Any,
    path: str,
    depth: int,
    counters: dict[str, int],
    issues: list[ProviderSchemaIssue],
    root_schema: dict[str, Any],
) -> None:
    counters["depth"] = max(counters["depth"], depth)
    if not isinstance(node, dict):
        issues.append(ProviderSchemaIssue(
            code="schema_node_not_object", path=path, message="schema node must be an object",
        ))
        return
    for keyword in node:
        if keyword not in _EMITTED_KEYWORDS:
            issues.append(ProviderSchemaIssue(
                code="unsupported_keyword", path=_pointer(path, keyword),
                message=f"provider schema contains unsupported keyword: {keyword}",
            ))
    declared = node.get("type")
    has_declared_type = "type" in node
    types = _provider_types(declared, _pointer(path, "type"), issues) if has_declared_type else ()
    types = types or ()
    _lint_terminal_node(node, path, types, has_declared_type, issues)
    if "$ref" in node:
        reference = node["$ref"]
        if not isinstance(reference, str) or _resolve_local_ref(root_schema, reference) is None:
            issues.append(ProviderSchemaIssue(
                code="unresolved_ref", path=_pointer(path, "$ref"),
                message=f"local schema reference cannot be resolved: {reference!r}",
            ))
    properties = node.get("properties")
    if "object" in types:
        if not isinstance(properties, dict):
            issues.append(ProviderSchemaIssue(
                code="object_properties_missing", path=_pointer(path, "properties"),
                message="object must declare properties",
            ))
            properties = {}
        if node.get("additionalProperties") is not False:
            issues.append(ProviderSchemaIssue(
                code="additional_properties_must_be_false", path=_pointer(path, "additionalProperties"),
                message="additionalProperties must be false",
            ))
        required = node.get("required")
        expected = sorted(properties)
        if not isinstance(required, list) or sorted(required) != expected or len(required) != len(set(required or [])):
            issues.append(ProviderSchemaIssue(
                code="all_properties_must_be_required", path=_pointer(path, "required"),
                message="required must list every property exactly once",
            ))
        counters["properties"] += len(properties)
        for name, child in sorted(properties.items()):
            counters["strings"] += len(name)
            _lint_node(
                child, _pointer(_pointer(path, "properties"), name), depth + 1,
                counters, issues, root_schema,
            )
    if "items" in node:
        _lint_node(node["items"], _pointer(path, "items"), depth + 1, counters, issues, root_schema)
    if "anyOf" in node:
        any_of = node["anyOf"]
        if not isinstance(any_of, list):
            issues.append(ProviderSchemaIssue(
                code="invalid_anyof", path=_pointer(path, "anyOf"), message="anyOf must be an array",
            ))
        else:
            for index, child in enumerate(any_of):
                _lint_node(
                    child, _pointer(_pointer(path, "anyOf"), str(index)), depth + 1,
                    counters, issues, root_schema,
                )
    definitions = node.get("$defs")
    if definitions is not None:
        if not isinstance(definitions, dict):
            issues.append(ProviderSchemaIssue(
                code="invalid_definitions", path=_pointer(path, "$defs"), message="$defs must be an object",
            ))
        else:
            for name, child in sorted(definitions.items()):
                counters["strings"] += len(name)
                _lint_node(
                    child, _pointer(_pointer(path, "$defs"), name), depth + 1,
                    counters, issues, root_schema,
                )
    enum = node.get("enum")
    if enum is not None:
        if not isinstance(enum, list):
            issues.append(ProviderSchemaIssue(
                code="invalid_enum", path=_pointer(path, "enum"), message="enum must be an array",
            ))
        else:
            counters["enum"] += len(enum)
            string_size = sum(len(item) for item in enum if isinstance(item, str))
            counters["strings"] += string_size
            if len(enum) > 250 and string_size > MAX_LARGE_ENUM_STRING_BUDGET:
                issues.append(ProviderSchemaIssue(
                    code="large_enum_string_budget_exceeded", path=_pointer(path, "enum"),
                    message=f"enum string budget {string_size} exceeds {MAX_LARGE_ENUM_STRING_BUDGET}",
                ))
    const = node.get("const")
    if isinstance(const, str):
        counters["strings"] += len(const)
    for keyword, value in node.items():
        if keyword not in {"const", "enum"} and isinstance(value, float) and not math.isfinite(value):
            issues.append(ProviderSchemaIssue(
                code="non_finite_number", path=_pointer(path, keyword), message="non-finite numbers are not canonical JSON",
            ))


def _type_terminal_node(
    canonical: dict[str, Any],
    projected: dict[str, Any],
    path: str,
    transformations: list[SchemaTransformation],
    issues: list[ProviderSchemaIssue],
) -> None:
    sources = tuple(keyword for keyword in ("const", "enum") if keyword in canonical)
    if not sources:
        return
    if len(sources) != 1:
        issues.append(ProviderSchemaIssue(
            code="ambiguous_terminal_source", path=path,
            message="a terminal node may not combine const and enum for provider inference",
        ))
        return
    source = sources[0]
    values = _terminal_values(canonical[source], source, path, issues)
    if values is None:
        return
    declared = projected.get("type")
    if declared is None:
        inferred = _infer_terminal_type(values, source, path, issues)
        if inferred is None:
            return
        projected["type"] = inferred
        canonical_value = canonical[source]
        transformations.append(SchemaTransformation(
            operation="add",
            path=_pointer(path, "type"),
            keyword="type",
            inferred_value=inferred,
            inference_source=source,
            canonical_value_summary=(
                f"const {inferred}" if source == "const" else f"{len(values)}-value {inferred} enum"
            ),
            canonical_value_hash=sha256_bytes(canonical_bytes(canonical_value)),
            reason="OpenAI strict-schema terminal typing",
            canonical_post_validation_rule=f"canonical.{source}",
            provider_only=True,
        ))
        declared_types = (inferred,)
    else:
        declared_types = _provider_types(declared, _pointer(path, "type"), issues)
        if declared_types is None:
            return
    _check_terminal_values(values, source, path, declared_types, issues)


def _lint_terminal_node(
    node: dict[str, Any],
    path: str,
    declared_types: tuple[str, ...],
    has_declared_type: bool,
    issues: list[ProviderSchemaIssue],
) -> None:
    sources = tuple(keyword for keyword in ("const", "enum") if keyword in node)
    if not sources:
        return
    if not has_declared_type:
        issues.append(ProviderSchemaIssue(
            code="terminal_type_missing", path=_pointer(path, "type"),
            message="const and enum provider nodes require an explicit type",
        ))
    if len(sources) != 1:
        issues.append(ProviderSchemaIssue(
            code="ambiguous_terminal_source", path=path,
            message="a terminal node may not combine const and enum",
        ))
        return
    source = sources[0]
    values = _terminal_values(node[source], source, path, issues)
    if values is None:
        return
    if declared_types:
        _check_terminal_values(values, source, path, declared_types, issues)
    elif not has_declared_type:
        _infer_terminal_type(values, source, path, issues)


def _terminal_values(
    value: Any,
    source: str,
    path: str,
    issues: list[ProviderSchemaIssue],
) -> tuple[Any, ...] | None:
    if source == "const":
        return (value,)
    if not isinstance(value, list):
        issues.append(ProviderSchemaIssue(
            code="invalid_enum", path=_pointer(path, "enum"), message="enum must be an array",
        ))
        return None
    if not value:
        issues.append(ProviderSchemaIssue(
            code="empty_enum", path=_pointer(path, "enum"), message="enum must not be empty",
        ))
        return None
    return tuple(value)


def _infer_terminal_type(
    values: tuple[Any, ...],
    source: str,
    path: str,
    issues: list[ProviderSchemaIssue],
) -> str | None:
    kinds: set[str] = set()
    invalid = False
    for index, value in enumerate(values):
        value_path = _pointer(path, source) if source == "const" else _pointer(_pointer(path, "enum"), str(index))
        kind = _json_type(value)
        if kind == "non_finite_number":
            issues.append(ProviderSchemaIssue(
                code="non_finite_number", path=value_path,
                message="terminal numeric values must be finite",
            ))
            invalid = True
        elif kind not in {"string", "boolean", "integer", "number"}:
            issues.append(ProviderSchemaIssue(
                code="terminal_type_not_inferable", path=value_path,
                message=f"provider terminal type cannot be inferred from {kind}",
            ))
            invalid = True
        else:
            kinds.add(kind)
    if invalid:
        return None
    if kinds == {"integer", "number"}:
        return "number"
    if len(kinds) == 1:
        return next(iter(kinds))
    issues.append(ProviderSchemaIssue(
        code="heterogeneous_terminal_values", path=_pointer(path, source),
        message=f"terminal values have incompatible JSON types: {sorted(kinds)}",
    ))
    return None


def _check_terminal_values(
    values: tuple[Any, ...],
    source: str,
    path: str,
    declared_types: tuple[str, ...],
    issues: list[ProviderSchemaIssue],
) -> None:
    for index, value in enumerate(values):
        value_path = _pointer(path, source) if source == "const" else _pointer(_pointer(path, "enum"), str(index))
        if _json_type(value) == "non_finite_number":
            issues.append(ProviderSchemaIssue(
                code="non_finite_number", path=value_path,
                message="terminal numeric values must be finite",
            ))
            continue
        if not any(_value_matches_type(value, declared) for declared in declared_types):
            issues.append(ProviderSchemaIssue(
                code="terminal_value_type_conflict", path=value_path,
                message=f"terminal value conflicts with declared provider type {list(declared_types)!r}",
            ))


def _provider_types(
    declared: Any,
    path: str,
    issues: list[ProviderSchemaIssue],
) -> tuple[str, ...] | None:
    values = tuple(declared) if isinstance(declared, list) else (declared,)
    if not values or any(not isinstance(item, str) or item not in _TYPES for item in values):
        issues.append(ProviderSchemaIssue(
            code="unsupported_type", path=path,
            message=f"unsupported type declaration: {declared!r}",
        ))
        return None
    if len(values) != len(set(values)):
        issues.append(ProviderSchemaIssue(
            code="unsupported_type_union", path=path,
            message=f"duplicate type union members: {declared!r}",
        ))
        return None
    if len(values) > 1 and not (
        len(values) == 2 and "null" in values and len(set(values) - {"null"}) == 1
    ):
        issues.append(ProviderSchemaIssue(
            code="unsupported_type_union", path=path,
            message="only a single type or a nullable two-type union is supported",
        ))
        return None
    return values


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number" if math.isfinite(value) else "non_finite_number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unsupported"


def _value_matches_type(value: Any, declared: str) -> bool:
    kind = _json_type(value)
    if declared == "number":
        return kind in {"integer", "number"}
    return kind == declared


def _resolve_local_ref(root: dict[str, Any], reference: str) -> Any | None:
    if reference == "#":
        return root
    if not reference.startswith("#/"):
        return None
    current: Any = root
    for raw_token in reference[2:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            return None
    return current if isinstance(current, dict) else None


def _loads_schema(text: str) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate object key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)


def _pointer(parent: str, token: str) -> str:
    escaped = token.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}"
