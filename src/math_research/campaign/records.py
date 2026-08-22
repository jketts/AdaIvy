"""Immutable records for a bounded, provenance-closed research campaign.

This module deliberately contains no executor.  It records decisions and work
performed by an executor without granting either mathematical warrant or
publication authority.  Semantic identity and operational observations have
separate hashes so replay can require both without making timing or usage part
of a mathematical artifact's identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from typing import Any, Mapping


SCHEMA_VERSION = "adaivy.campaign-provenance.v1"
CANONICALIZATION_VERSION = "1.0.0"
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class CampaignProvenanceError(ValueError):
    """A campaign record is malformed, tampered, or causally incomplete."""


class ValueEnum(str, Enum):
    pass


class RecordStatus(ValueEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class ActionType(ValueEnum):
    PLAN = "plan"
    DERIVE = "derive"
    WRITE_PROGRAM = "write_program"
    RUN_PROGRAM = "run_program"
    INSPECT_RESULT = "inspect_result"
    EXPERIMENT = "experiment"
    FALSIFY = "falsify"
    VERIFY = "verify"
    ASK_USER = "ask_user"
    SUSPEND_BRANCH = "suspend_branch"
    REPORT = "report"
    IMPORT = "import"
    SEARCH_LITERATURE = "search_literature"
    FOLLOW_DISCOVERY_RESULTS = "follow_discovery_results"
    ACQUIRE_SOURCE = "acquire_source"
    PARSE_SOURCE = "parse_source"
    EMBED_SOURCES = "embed_sources"
    REFRESH_RETRIEVAL_INDEX = "refresh_retrieval_index"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    FORMAL_CHECK = "formal_check"


class ActorType(ValueEnum):
    SYSTEM = "system"
    MODEL = "model"
    TOOL = "tool"
    HUMAN = "human"
    EXTERNAL_SYSTEM = "external_system"


class UsageSource(ValueEnum):
    API_REPORTED = "api_reported"
    LOCALLY_MEASURED = "locally_measured"
    UNAVAILABLE = "unavailable"


class ExternalOrigin(ValueEnum):
    EXTERNAL_CODEX = "external_codex"
    HUMAN = "human"
    EXTERNAL_SYSTEM = "external_system"


def public_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: public_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): public_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [public_value(item) for item in value]
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        public_value(value), allow_nan=False, ensure_ascii=False,
        separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise CampaignProvenanceError(f"{field} is not a valid identifier")


def _hash(value: str, field: str) -> None:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise CampaignProvenanceError(f"{field} is not a sha256 content hash")


def _optional_hash(value: str | None, field: str) -> None:
    if value is not None:
        _hash(value, field)


def _nonnegative(value: int | None, field: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CampaignProvenanceError(f"{field} must be a non-negative integer")


def _member(value: object, enum: type[Enum], field: str) -> None:
    if not isinstance(value, enum):
        raise CampaignProvenanceError(f"{field} must be a {enum.__name__} value")


def _strings(values: tuple[str, ...], field: str, *, hashes: bool = False) -> None:
    if not isinstance(values, tuple) or len(values) != len(set(values)):
        raise CampaignProvenanceError(f"{field} must be a tuple of unique values")
    for value in values:
        (_hash if hashes else _identifier)(value, field)


def _record_hashes(value: Any, operational_fields: frozenset[str]) -> tuple[str, str]:
    payload = public_value(value)
    payload["content_hash"] = ""
    payload["operational_hash"] = ""
    semantic = {
        key: item for key, item in payload.items()
        if key not in operational_fields and key not in {"content_hash", "operational_hash"}
    }
    content_hash = canonical_hash(semantic)
    payload["content_hash"] = content_hash
    payload.pop("operational_hash", None)
    return content_hash, canonical_hash(payload)


def _finish(value: Any, operational_fields: frozenset[str]) -> Any:
    content_hash, operational_hash = _record_hashes(value, operational_fields)
    return replace(value, content_hash=content_hash, operational_hash=operational_hash)


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionRecord:
    action_id: str
    campaign_id: str
    sequence: int
    branch_id: str
    action_type: ActionType
    actor_type: ActorType
    actor_id: str
    parent_action_ids: tuple[str, ...]
    input_artifact_hashes: tuple[str, ...]
    source_record_ids: tuple[str, ...]
    output_artifact_hashes: tuple[str, ...]
    status: RecordStatus
    declared_rationale: str
    recorded_at: str
    schema_version: str = SCHEMA_VERSION
    record_type: str = "campaign_action"
    content_hash: str = ""
    operational_hash: str = ""

    OPERATIONAL_FIELDS = frozenset({"recorded_at"})

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.record_type != "campaign_action":
            raise CampaignProvenanceError("unsupported campaign action schema")
        _identifier(self.action_id, "action_id")
        _identifier(self.campaign_id, "campaign_id")
        _identifier(self.branch_id, "branch_id")
        _identifier(self.actor_id, "actor_id")
        _member(self.action_type, ActionType, "action_type")
        _member(self.actor_type, ActorType, "actor_type")
        _member(self.status, RecordStatus, "status")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise CampaignProvenanceError("action sequence must be a positive integer")
        _strings(self.parent_action_ids, "parent_action_ids")
        _strings(self.source_record_ids, "source_record_ids")
        _strings(self.input_artifact_hashes, "input_artifact_hashes", hashes=True)
        _strings(self.output_artifact_hashes, "output_artifact_hashes", hashes=True)
        if not isinstance(self.declared_rationale, str) or len(self.declared_rationale) > 2_000:
            raise CampaignProvenanceError("declared_rationale must be at most 2000 characters")
        if not isinstance(self.recorded_at, str) or not self.recorded_at:
            raise CampaignProvenanceError("recorded_at must be supplied")

    def finalized(self) -> ActionRecord:
        return _finish(replace(self, content_hash="", operational_hash=""), self.OPERATIONAL_FIELDS)

    def verify_hashes(self) -> None:
        expected = self.finalized()
        if self.content_hash != expected.content_hash:
            raise CampaignProvenanceError(f"action {self.action_id} content_hash mismatch")
        if self.operational_hash != expected.operational_hash:
            raise CampaignProvenanceError(f"action {self.action_id} operational_hash mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelCallRecord:
    call_id: str
    campaign_id: str
    action_id: str
    purpose: str
    provider: str
    model_identifier: str
    live_configuration_hash: str
    pricing_snapshot_hash: str
    request_hash: str
    result_hash: str
    status: RecordStatus
    usage_source: UsageSource
    input_tokens: int
    output_tokens: int
    estimated_cost_microusd: int | None
    provider_request_id: str | None
    recorded_at: str
    schema_version: str = SCHEMA_VERSION
    record_type: str = "model_call"
    content_hash: str = ""
    operational_hash: str = ""

    OPERATIONAL_FIELDS = frozenset({
        "usage_source", "input_tokens", "output_tokens", "estimated_cost_microusd",
        "provider_request_id", "recorded_at",
    })

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.record_type != "model_call":
            raise CampaignProvenanceError("unsupported model-call schema")
        for field in ("call_id", "campaign_id", "action_id", "purpose", "provider", "model_identifier"):
            _identifier(getattr(self, field), field)
        _member(self.status, RecordStatus, "status")
        _member(self.usage_source, UsageSource, "usage_source")
        for field in ("live_configuration_hash", "pricing_snapshot_hash", "request_hash", "result_hash"):
            _hash(getattr(self, field), field)
        _nonnegative(self.input_tokens, "input_tokens")
        _nonnegative(self.output_tokens, "output_tokens")
        _nonnegative(self.estimated_cost_microusd, "estimated_cost_microusd", optional=True)
        if self.usage_source is UsageSource.UNAVAILABLE:
            if self.input_tokens != 0 or self.output_tokens != 0 or self.estimated_cost_microusd is not None:
                raise CampaignProvenanceError("unavailable model usage cannot carry measured totals")
        elif self.estimated_cost_microusd is None:
            raise CampaignProvenanceError("measured model usage requires an estimated cost")
        if self.provider_request_id is not None and not isinstance(self.provider_request_id, str):
            raise CampaignProvenanceError("provider_request_id must be a string or null")
        if not isinstance(self.recorded_at, str) or not self.recorded_at:
            raise CampaignProvenanceError("recorded_at must be supplied")

    def finalized(self) -> ModelCallRecord:
        return _finish(replace(self, content_hash="", operational_hash=""), self.OPERATIONAL_FIELDS)

    def verify_hashes(self) -> None:
        expected = self.finalized()
        if self.content_hash != expected.content_hash:
            raise CampaignProvenanceError(f"model call {self.call_id} content_hash mismatch")
        if self.operational_hash != expected.operational_hash:
            raise CampaignProvenanceError(f"model call {self.call_id} operational_hash mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolRunRecord:
    tool_run_id: str
    campaign_id: str
    action_id: str
    adapter_id: str
    adapter_version: str
    adapter_configuration_hash: str
    request_hash: str
    result_hash: str
    stdout_hash: str
    stderr_hash: str
    environment_hash: str
    status: RecordStatus
    measurement_source: UsageSource
    cpu_milliseconds: int | None
    wall_milliseconds: int | None
    peak_memory_bytes: int | None
    output_bytes: int | None
    recorded_at: str
    schema_version: str = SCHEMA_VERSION
    record_type: str = "tool_run"
    content_hash: str = ""
    operational_hash: str = ""

    OPERATIONAL_FIELDS = frozenset({
        "measurement_source", "cpu_milliseconds", "wall_milliseconds",
        "peak_memory_bytes", "output_bytes", "recorded_at",
    })

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.record_type != "tool_run":
            raise CampaignProvenanceError("unsupported tool-run schema")
        for field in ("tool_run_id", "campaign_id", "action_id", "adapter_id", "adapter_version"):
            _identifier(getattr(self, field), field)
        _member(self.status, RecordStatus, "status")
        _member(self.measurement_source, UsageSource, "measurement_source")
        for field in (
            "adapter_configuration_hash", "request_hash", "result_hash", "stdout_hash",
            "stderr_hash", "environment_hash",
        ):
            _hash(getattr(self, field), field)
        for field in ("cpu_milliseconds", "wall_milliseconds", "peak_memory_bytes", "output_bytes"):
            _nonnegative(getattr(self, field), field, optional=True)
        observed = (self.cpu_milliseconds, self.wall_milliseconds, self.peak_memory_bytes, self.output_bytes)
        if self.measurement_source is UsageSource.UNAVAILABLE:
            if any(item is not None for item in observed):
                raise CampaignProvenanceError("unavailable tool measurement cannot carry observations")
        elif all(item is None for item in observed):
            # ADR-0066 records host-observed wall time and output bytes while
            # deliberately keeping CPU and peak memory null rather than guessed,
            # so a measured run carries the observations it honestly has -- but
            # a "measured" claim with zero observations is still a lie.
            raise CampaignProvenanceError("locally measured tool run requires at least one resource observation")
        if not isinstance(self.recorded_at, str) or not self.recorded_at:
            raise CampaignProvenanceError("recorded_at must be supplied")

    def finalized(self) -> ToolRunRecord:
        return _finish(replace(self, content_hash="", operational_hash=""), self.OPERATIONAL_FIELDS)

    def verify_hashes(self) -> None:
        expected = self.finalized()
        if self.content_hash != expected.content_hash:
            raise CampaignProvenanceError(f"tool run {self.tool_run_id} content_hash mismatch")
        if self.operational_hash != expected.operational_hash:
            raise CampaignProvenanceError(f"tool run {self.tool_run_id} operational_hash mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportRecord:
    import_id: str
    campaign_id: str
    action_id: str
    origin_type: ExternalOrigin
    source_id: str
    artifact_hash: str
    usage_source: UsageSource
    model_calls: int | None
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_microusd: int | None
    note: str
    recorded_at: str
    schema_version: str = SCHEMA_VERSION
    record_type: str = "external_import"
    content_hash: str = ""
    operational_hash: str = ""

    OPERATIONAL_FIELDS = frozenset({
        "usage_source", "model_calls", "input_tokens", "output_tokens",
        "estimated_cost_microusd", "recorded_at",
    })

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION or self.record_type != "external_import":
            raise CampaignProvenanceError("unsupported import schema")
        for field in ("import_id", "campaign_id", "action_id", "source_id"):
            _identifier(getattr(self, field), field)
        _member(self.origin_type, ExternalOrigin, "origin_type")
        _member(self.usage_source, UsageSource, "usage_source")
        _hash(self.artifact_hash, "artifact_hash")
        for field in ("model_calls", "input_tokens", "output_tokens", "estimated_cost_microusd"):
            _nonnegative(getattr(self, field), field, optional=True)
        observations = (self.model_calls, self.input_tokens, self.output_tokens, self.estimated_cost_microusd)
        # This bounded slice has no verifier for usage claimed by an external
        # system.  Preserve that absence rather than accepting self-reported
        # numbers which could make a mixed campaign look completely measured.
        if self.usage_source is not UsageSource.UNAVAILABLE or any(
            item is not None for item in observations
        ):
            raise CampaignProvenanceError(
                "external import usage is unavailable until a verified usage-record boundary exists"
            )
        if not isinstance(self.note, str) or not self.note:
            raise CampaignProvenanceError("an external import requires a non-empty note")
        if not isinstance(self.recorded_at, str) or not self.recorded_at:
            raise CampaignProvenanceError("recorded_at must be supplied")

    def finalized(self) -> ImportRecord:
        return _finish(replace(self, content_hash="", operational_hash=""), self.OPERATIONAL_FIELDS)

    def verify_hashes(self) -> None:
        expected = self.finalized()
        if self.content_hash != expected.content_hash:
            raise CampaignProvenanceError(f"import {self.import_id} content_hash mismatch")
        if self.operational_hash != expected.operational_hash:
            raise CampaignProvenanceError(f"import {self.import_id} operational_hash mismatch")


__all__ = [
    "ActionRecord", "ActionType", "ActorType", "CANONICALIZATION_VERSION",
    "CampaignProvenanceError", "ExternalOrigin", "ImportRecord", "ModelCallRecord",
    "RecordStatus", "SCHEMA_VERSION", "ToolRunRecord", "UsageSource", "canonical_bytes",
    "canonical_hash", "public_value",
]
