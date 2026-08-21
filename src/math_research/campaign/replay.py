"""Strict construction and replay verification for campaign provenance."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any, Mapping, TypeVar

from .records import (
    ActionRecord,
    ActionType,
    ActorType,
    CANONICALIZATION_VERSION,
    CampaignProvenanceError,
    ExternalOrigin,
    ImportRecord,
    ModelCallRecord,
    RecordStatus,
    SCHEMA_VERSION,
    ToolRunRecord,
    UsageSource,
    canonical_bytes,
    canonical_hash,
    public_value,
)


_EXPORT_FIELDS = frozenset({
    "schema_version", "canonicalization_version", "campaign_id", "target_hash",
    "configuration_hash", "actions", "model_calls", "tool_runs", "imports", "usage",
    "attribution_status", "measurement_status", "content_hash", "operational_hash",
})
_USAGE_FIELDS = frozenset({
    "requests_attempted", "responses_completed", "responses_failed",
    "responses_incomplete", "usage_reported_calls", "tool_runs_attempted", "tool_runs_completed",
    "tool_runs_failed", "tool_runs_incomplete", "external_imports", "input_tokens",
    "output_tokens", "total_tokens", "estimated_cost_microusd", "billing_status",
})
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignExport:
    campaign_id: str
    target_hash: str
    configuration_hash: str
    actions: tuple[ActionRecord, ...]
    model_calls: tuple[ModelCallRecord, ...]
    tool_runs: tuple[ToolRunRecord, ...]
    imports: tuple[ImportRecord, ...]
    usage: Mapping[str, int | str]
    attribution_status: str
    measurement_status: str
    schema_version: str = SCHEMA_VERSION
    canonicalization_version: str = CANONICALIZATION_VERSION
    content_hash: str = ""
    operational_hash: str = ""


def _tool_status_counts(records: tuple[ToolRunRecord, ...]) -> dict[str, int]:
    return {
        "tool_runs_attempted": len(records),
        "tool_runs_completed": sum(item.status is RecordStatus.COMPLETED for item in records),
        "tool_runs_failed": sum(item.status is RecordStatus.FAILED for item in records),
        "tool_runs_incomplete": sum(item.status is RecordStatus.INCOMPLETE for item in records),
    }


def derive_usage(
    model_calls: tuple[ModelCallRecord, ...],
    tool_runs: tuple[ToolRunRecord, ...],
    imports: tuple[ImportRecord, ...],
) -> dict[str, int | str]:
    """Derive counts and estimates from records; no billed-cost field exists."""

    usage: dict[str, int | str] = {
        "requests_attempted": len(model_calls),
        "responses_completed": sum(item.status is RecordStatus.COMPLETED for item in model_calls),
        "responses_failed": sum(item.status is RecordStatus.FAILED for item in model_calls),
        "responses_incomplete": sum(item.status is RecordStatus.INCOMPLETE for item in model_calls),
        "usage_reported_calls": sum(
            item.usage_source is not UsageSource.UNAVAILABLE for item in model_calls
        ),
        **_tool_status_counts(tool_runs),
        "external_imports": len(imports),
        "input_tokens": sum(item.input_tokens for item in model_calls),
        "output_tokens": sum(item.output_tokens for item in model_calls),
        "estimated_cost_microusd": sum(
            item.estimated_cost_microusd or 0 for item in model_calls
        ),
        "billing_status": "not_billed",
    }
    usage["total_tokens"] = int(usage["input_tokens"]) + int(usage["output_tokens"])
    return usage


def _measurement_status(
    model_calls: tuple[ModelCallRecord, ...],
    tool_runs: tuple[ToolRunRecord, ...],
    imports: tuple[ImportRecord, ...],
) -> str:
    sources = [item.usage_source for item in model_calls]
    sources.extend(item.measurement_source for item in tool_runs)
    sources.extend(item.usage_source for item in imports)
    missing = sum(item is UsageSource.UNAVAILABLE for item in sources)
    if missing == 0:
        return "complete"
    return "unavailable" if missing == len(sources) else "partial"


def _semantic_preimage(export: CampaignExport) -> dict[str, Any]:
    return {
        "schema_version": export.schema_version,
        "canonicalization_version": export.canonicalization_version,
        "campaign_id": export.campaign_id,
        "target_hash": export.target_hash,
        "configuration_hash": export.configuration_hash,
        "action_hashes": [item.content_hash for item in export.actions],
        "model_call_hashes": [item.content_hash for item in export.model_calls],
        "tool_run_hashes": [item.content_hash for item in export.tool_runs],
        "import_hashes": [item.content_hash for item in export.imports],
        "attribution_status": export.attribution_status,
    }


def _operational_hash(export: CampaignExport) -> str:
    value = public_value(export)
    value.pop("operational_hash", None)
    return canonical_hash(value)


def build_campaign_export(
    *,
    campaign_id: str,
    target_hash: str,
    configuration_hash: str,
    actions: tuple[ActionRecord, ...],
    model_calls: tuple[ModelCallRecord, ...] = (),
    tool_runs: tuple[ToolRunRecord, ...] = (),
    imports: tuple[ImportRecord, ...] = (),
) -> CampaignExport:
    actions = tuple(item.finalized() for item in actions)
    model_calls = tuple(item.finalized() for item in model_calls)
    tool_runs = tuple(item.finalized() for item in tool_runs)
    imports = tuple(item.finalized() for item in imports)
    export = CampaignExport(
        campaign_id=campaign_id,
        target_hash=target_hash,
        configuration_hash=configuration_hash,
        actions=actions,
        model_calls=model_calls,
        tool_runs=tool_runs,
        imports=imports,
        usage=derive_usage(model_calls, tool_runs, imports),
        attribution_status="external_assisted" if imports else "adaivy_campaign",
        measurement_status=_measurement_status(model_calls, tool_runs, imports),
    )
    _validate_closure(export)
    export = replace(export, content_hash=canonical_hash(_semantic_preimage(export)))
    return replace(export, operational_hash=_operational_hash(export))


def export_campaign_bytes(export: CampaignExport) -> bytes:
    verify_campaign_export(public_value(export))
    return canonical_bytes(export) + b"\n"


def _exact(value: Mapping[str, Any], expected: frozenset[str], field: str) -> None:
    if set(value) != expected:
        raise CampaignProvenanceError(f"{field} fields differ from the closed schema")


T = TypeVar("T")


def _enum(enum: type[T], value: object, field: str) -> T:
    try:
        return enum(value)  # type: ignore[call-arg]
    except (TypeError, ValueError) as error:
        raise CampaignProvenanceError(f"{field} has an unsupported value") from error


def _tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CampaignProvenanceError(f"{field} must be an array of strings")
    return tuple(value)


def _parse_action(value: object) -> ActionRecord:
    if not isinstance(value, dict):
        raise CampaignProvenanceError("action must be an object")
    expected = frozenset(item.name for item in ActionRecord.__dataclass_fields__.values())
    _exact(value, expected, "action")
    return ActionRecord(
        **{**value,
           "action_type": _enum(ActionType, value["action_type"], "action_type"),
           "actor_type": _enum(ActorType, value["actor_type"], "actor_type"),
           "status": _enum(RecordStatus, value["status"], "status"),
           "parent_action_ids": _tuple(value["parent_action_ids"], "parent_action_ids"),
           "input_artifact_hashes": _tuple(value["input_artifact_hashes"], "input_artifact_hashes"),
           "source_record_ids": _tuple(value["source_record_ids"], "source_record_ids"),
           "output_artifact_hashes": _tuple(value["output_artifact_hashes"], "output_artifact_hashes")}
    )


def _parse_model(value: object) -> ModelCallRecord:
    if not isinstance(value, dict):
        raise CampaignProvenanceError("model call must be an object")
    expected = frozenset(item.name for item in ModelCallRecord.__dataclass_fields__.values())
    _exact(value, expected, "model call")
    return ModelCallRecord(
        **{**value,
           "status": _enum(RecordStatus, value["status"], "status"),
           "usage_source": _enum(UsageSource, value["usage_source"], "usage_source")}
    )


def _parse_tool(value: object) -> ToolRunRecord:
    if not isinstance(value, dict):
        raise CampaignProvenanceError("tool run must be an object")
    expected = frozenset(item.name for item in ToolRunRecord.__dataclass_fields__.values())
    _exact(value, expected, "tool run")
    return ToolRunRecord(
        **{**value,
           "status": _enum(RecordStatus, value["status"], "status"),
           "measurement_source": _enum(
               UsageSource, value["measurement_source"], "measurement_source"
           )}
    )


def _parse_import(value: object) -> ImportRecord:
    if not isinstance(value, dict):
        raise CampaignProvenanceError("external import must be an object")
    expected = frozenset(item.name for item in ImportRecord.__dataclass_fields__.values())
    _exact(value, expected, "external import")
    return ImportRecord(
        **{**value,
           "origin_type": _enum(ExternalOrigin, value["origin_type"], "origin_type"),
           "usage_source": _enum(UsageSource, value["usage_source"], "usage_source")}
    )


def _validate_closure(export: CampaignExport) -> None:
    if export.schema_version != SCHEMA_VERSION:
        raise CampaignProvenanceError("unsupported campaign export schema")
    if export.canonicalization_version != CANONICALIZATION_VERSION:
        raise CampaignProvenanceError("unsupported campaign canonicalization version")
    if not export.campaign_id:
        raise CampaignProvenanceError("campaign_id must be non-empty")
    for field in ("target_hash", "configuration_hash"):
        value = getattr(export, field)
        if not isinstance(value, str) or not _HASH.fullmatch(value):
            raise CampaignProvenanceError(f"{field} is invalid")
    records: list[Any] = [*export.actions, *export.model_calls, *export.tool_runs, *export.imports]
    ids = [
        *(item.action_id for item in export.actions),
        *(item.call_id for item in export.model_calls),
        *(item.tool_run_id for item in export.tool_runs),
        *(item.import_id for item in export.imports),
    ]
    if len(ids) != len(set(ids)):
        raise CampaignProvenanceError("campaign record identifiers are not globally unique")
    if any(item.campaign_id != export.campaign_id for item in records):
        raise CampaignProvenanceError("a record belongs to a different campaign")
    for item in records:
        item.verify_hashes()
    ordered = sorted(export.actions, key=lambda item: item.sequence)
    if list(item.sequence for item in ordered) != list(range(1, len(ordered) + 1)):
        raise CampaignProvenanceError("action sequence is not contiguous")
    if tuple(ordered) != export.actions:
        raise CampaignProvenanceError("actions are not in sequence order")
    action_by_id = {item.action_id: item for item in export.actions}
    source_by_id = {
        **{item.call_id: item for item in export.model_calls},
        **{item.tool_run_id: item for item in export.tool_runs},
        **{item.import_id: item for item in export.imports},
    }
    source_use: dict[str, int] = {key: 0 for key in source_by_id}
    available_artifacts = {export.target_hash, export.configuration_hash}
    for action in export.actions:
        for parent_id in action.parent_action_ids:
            parent = action_by_id.get(parent_id)
            if parent is None or parent.sequence >= action.sequence:
                raise CampaignProvenanceError(
                    f"action {action.action_id} has an absent or non-prior parent"
                )
        missing_inputs = set(action.input_artifact_hashes) - available_artifacts
        if missing_inputs:
            raise CampaignProvenanceError(
                f"action {action.action_id} has inputs outside campaign provenance"
            )
        source_artifacts: set[str] = set()
        for source_id in action.source_record_ids:
            source = source_by_id.get(source_id)
            if source is None or source.action_id != action.action_id:
                raise CampaignProvenanceError(
                    f"action {action.action_id} has an absent or misbound source record"
                )
            source_use[source_id] += 1
            if isinstance(source, ModelCallRecord):
                source_artifacts.add(source.result_hash)
            elif isinstance(source, ToolRunRecord):
                source_artifacts.update((source.result_hash, source.stdout_hash, source.stderr_hash))
            else:
                source_artifacts.add(source.artifact_hash)
        if not set(action.output_artifact_hashes).issubset(source_artifacts):
            raise CampaignProvenanceError(
                f"action {action.action_id} claims an output absent from its source records"
            )
        available_artifacts.update(action.output_artifact_hashes)
    if any(count != 1 for count in source_use.values()):
        raise CampaignProvenanceError("every source record must be used by exactly one action")


def verify_campaign_export(value: bytes | str | Mapping[str, Any]) -> CampaignExport:
    """Parse, close, and hash-check a campaign export without executing work."""

    raw: bytes | None = None
    if isinstance(value, bytes):
        raw = value
        try:
            value = json.loads(value)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CampaignProvenanceError("campaign export is not valid UTF-8 JSON") from error
    elif isinstance(value, str):
        raw = value.encode("utf-8")
        try:
            value = json.loads(value)
        except json.JSONDecodeError as error:
            raise CampaignProvenanceError("campaign export is not valid JSON") from error
    if not isinstance(value, Mapping):
        raise CampaignProvenanceError("campaign export must be an object")
    _exact(value, _EXPORT_FIELDS, "campaign export")
    if raw is not None and raw != canonical_bytes(value) + b"\n":
        raise CampaignProvenanceError("campaign export bytes are not canonical")
    for key in ("actions", "model_calls", "tool_runs", "imports"):
        if not isinstance(value[key], list):
            raise CampaignProvenanceError(f"{key} must be an array")
    usage = value["usage"]
    if not isinstance(usage, Mapping):
        raise CampaignProvenanceError("usage must be an object")
    _exact(usage, _USAGE_FIELDS, "usage")
    export = CampaignExport(
        schema_version=value["schema_version"],
        canonicalization_version=value["canonicalization_version"],
        campaign_id=value["campaign_id"],
        target_hash=value["target_hash"],
        configuration_hash=value["configuration_hash"],
        actions=tuple(_parse_action(item) for item in value["actions"]),
        model_calls=tuple(_parse_model(item) for item in value["model_calls"]),
        tool_runs=tuple(_parse_tool(item) for item in value["tool_runs"]),
        imports=tuple(_parse_import(item) for item in value["imports"]),
        usage=dict(usage),
        attribution_status=value["attribution_status"],
        measurement_status=value["measurement_status"],
        content_hash=value["content_hash"],
        operational_hash=value["operational_hash"],
    )
    _validate_closure(export)
    expected_usage = derive_usage(export.model_calls, export.tool_runs, export.imports)
    if dict(export.usage) != expected_usage:
        raise CampaignProvenanceError("campaign usage is not derived from its records")
    expected_attribution = "external_assisted" if export.imports else "adaivy_campaign"
    if export.attribution_status != expected_attribution:
        raise CampaignProvenanceError("campaign attribution is not derived from its imports")
    expected_measurement = _measurement_status(export.model_calls, export.tool_runs, export.imports)
    if export.measurement_status != expected_measurement:
        raise CampaignProvenanceError("campaign measurement status is not derived")
    if export.content_hash != canonical_hash(_semantic_preimage(export)):
        raise CampaignProvenanceError("campaign content_hash mismatch")
    if export.operational_hash != _operational_hash(export):
        raise CampaignProvenanceError("campaign operational_hash mismatch")
    return export


__all__ = [
    "CampaignExport", "build_campaign_export", "derive_usage", "export_campaign_bytes",
    "verify_campaign_export",
]
