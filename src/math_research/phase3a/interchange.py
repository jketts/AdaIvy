"""Canonical ResearchMemoryExport v1 interchange and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..domain.entities import OpaqueId
from . import MEMORY_SCHEMA_VERSION
from .records import (
    EvidencePackManifest,
    EvidenceRelation,
    EvidenceUnit,
    EvidenceUnitType,
    NormalizedDocument,
    ParserRunRecord,
    QuarantineState,
    ResearchMemoryRecord,
    RetrievalHit,
    RetrievalQueryRecord,
    SourceArtifact,
    SourceReference,
    SourceSpan,
    record_type,
)
from .serialization import canonical_bytes, canonical_hash, public_value, record_from_dict, sha256_bytes
from .workspace import ResearchMemoryWorkspace

_CATEGORY_BY_TYPE = {
    "source_reference": "source_references",
    "source_artifact": "source_artifacts",
    "source_version_relation": "source_version_relations",
    "parser_run": "parser_runs",
    "normalized_document": "normalized_documents",
    "source_span": "source_spans",
    "document_marker": "markers",
    "evidence_unit": "evidence_units",
    "evidence_relation": "evidence_relations",
    "retrieval_query": "retrieval_queries",
    "retrieval_hit": "retrieval_hits",
    "evidence_pack": "evidence_packs",
}
_TYPE_BY_CATEGORY = {value: key for key, value in _CATEGORY_BY_TYPE.items()}


@dataclass(frozen=True, slots=True)
class MemoryReplay:
    payload: dict[str, Any]
    records: tuple[ResearchMemoryRecord, ...]
    content_hash: str
    canonical_bytes: bytes


def build_export(
    workspace: ResearchMemoryWorkspace,
    *,
    export_id: OpaqueId,
    aggregate_id: OpaqueId,
    created_at: str,
    created_by: OpaqueId,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "id": export_id.value,
        **{category: [] for category in _TYPE_BY_CATEGORY},
        "audit_event_ids": [event["event_id"] for event in workspace.timeline(aggregate_id)],
        "content_hash": None,
        "created_at": created_at,
        "created_by": created_by.value,
    }
    for record in workspace.all_records():
        payload[_CATEGORY_BY_TYPE[record_type(record)]].append(public_value(record))
    for category in _TYPE_BY_CATEGORY:
        payload[category].sort(key=lambda item: item["id"])
    payload["content_hash"] = canonical_hash(payload)
    return payload


def export_bytes(payload: Mapping[str, Any]) -> bytes:
    validate_export(payload)
    return canonical_bytes(payload)


def write_export(payload: Mapping[str, Any], path: Path) -> str:
    data = export_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(payload["content_hash"])


def import_trusted_replay(data: bytes) -> MemoryReplay:
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("research-memory export is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("research-memory export root must be an object")
    validate_export(payload)
    canonical = canonical_bytes(payload)
    if data != canonical:
        raise ValueError("research-memory replay requires canonical JSON bytes")
    records: list[ResearchMemoryRecord] = []
    for category, kind in _TYPE_BY_CATEGORY.items():
        records.extend(record_from_dict(kind, item) for item in payload[category])
    return MemoryReplay(payload, tuple(records), payload["content_hash"], canonical)


def validate_export(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "id", *tuple(_TYPE_BY_CATEGORY), "audit_event_ids", "content_hash", "created_at", "created_by"
    }
    if set(payload) != required:
        missing = sorted(required - set(payload))
        extra = sorted(set(payload) - required)
        raise ValueError(f"research-memory export fields differ: missing={missing}, extra={extra}")
    if payload["schema_version"] != MEMORY_SCHEMA_VERSION:
        raise ValueError("unsupported research-memory export schema version")
    if not isinstance(payload["content_hash"], str):
        raise ValueError("research-memory export content_hash is required")
    hash_payload = dict(payload)
    hash_payload["content_hash"] = None
    expected = canonical_hash(hash_payload)
    if payload["content_hash"] != expected:
        raise ValueError("research-memory export content hash mismatch")
    typed: dict[str, ResearchMemoryRecord] = {}
    by_kind: dict[str, dict[str, ResearchMemoryRecord]] = {}
    for category, kind in _TYPE_BY_CATEGORY.items():
        values = payload[category]
        if not isinstance(values, list):
            raise ValueError(f"{category} must be an array")
        ids = [item.get("id") for item in values if isinstance(item, dict)]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError(f"{category} must be unique and sorted by ID")
        records = [record_from_dict(kind, item) for item in values]
        by_kind[kind] = {record.id.value: record for record in records}
        for record in records:
            if record.id.value in typed:
                raise ValueError(f"record ID reused across types: {record.id.value}")
            typed[record.id.value] = record

    references = by_kind["source_reference"]
    artifacts = by_kind["source_artifact"]
    runs = by_kind["parser_run"]
    documents = by_kind["normalized_document"]
    spans = by_kind["source_span"]
    units = by_kind["evidence_unit"]
    queries = by_kind["retrieval_query"]
    hits = by_kind["retrieval_hit"]
    for artifact in artifacts.values():
        assert isinstance(artifact, SourceArtifact)
        if artifact.source_reference_id.value not in references:
            raise ValueError("source artifact references unknown source")
    for reference in references.values():
        assert isinstance(reference, SourceReference)
        if reference.acquisition_status.value == "metadata_only":
            if any(isinstance(artifact, SourceArtifact) and artifact.source_reference_id == reference.id for artifact in artifacts.values()):
                raise ValueError("metadata-only source cannot own an artifact")
    for run in runs.values():
        assert isinstance(run, ParserRunRecord)
        if run.source_artifact_id.value not in artifacts:
            raise ValueError("parser run references unknown artifact")
    for document in documents.values():
        assert isinstance(document, NormalizedDocument)
        if document.source_artifact_id.value not in artifacts or document.parser_run_id.value not in runs:
            raise ValueError("normalized document provenance is incomplete")
    for span in spans.values():
        assert isinstance(span, SourceSpan)
        if span.source_artifact_id.value not in artifacts or span.normalized_document_id.value not in documents:
            raise ValueError("source span provenance is incomplete")
    for unit in units.values():
        assert isinstance(unit, EvidenceUnit)
        if unit.unit_type is EvidenceUnitType.MODEL_PROPOSED_CLAIM:
            continue
        if unit.source_artifact_id is None or unit.source_artifact_id.value not in artifacts:
            raise ValueError("source evidence unit lacks artifact")
        artifact = artifacts[unit.source_artifact_id.value]
        assert isinstance(artifact, SourceArtifact)
        if artifact.quarantine_state is not QuarantineState.ELIGIBLE:
            raise ValueError("quarantined artifact cannot produce evidence")
        if unit.normalized_document_id is None or unit.normalized_document_id.value not in documents:
            raise ValueError("source evidence unit lacks normalized document")
        if not unit.source_span_ids or any(identifier.value not in spans for identifier in unit.source_span_ids):
            raise ValueError("source evidence unit lacks exact spans")
    for relation in by_kind["evidence_relation"].values():
        assert isinstance(relation, EvidenceRelation)
        if relation.source_unit_id.value not in units or relation.target_unit_id.value not in units:
            raise ValueError("evidence relation references unknown unit")
    for hit in hits.values():
        assert isinstance(hit, RetrievalHit)
        if hit.query_id.value not in queries or hit.evidence_unit_id.value not in units:
            raise ValueError("retrieval hit references unknown query or evidence")
        if any(identifier.value not in spans for identifier in hit.source_span_ids):
            raise ValueError("retrieval hit references unknown span")
    for pack in by_kind["evidence_pack"].values():
        assert isinstance(pack, EvidencePackManifest)
        if pack.query_id.value not in queries:
            raise ValueError("evidence pack references unknown query")
        if any(identifier.value not in units for identifier in pack.included_evidence_unit_ids):
            raise ValueError("evidence pack contains unknown unit")
        hit_units = {
            hit.evidence_unit_id for hit in hits.values()
            if isinstance(hit, RetrievalHit) and hit.query_id == pack.query_id
        }
        if any(identifier not in hit_units for identifier in pack.included_evidence_unit_ids):
            raise ValueError("evidence pack contains an out-of-result unit")


def validate_provenance(workspace: ResearchMemoryWorkspace) -> dict[str, object]:
    spans_checked = 0
    for span_record in workspace.records("source_span"):
        assert isinstance(span_record, SourceSpan)
        artifact = workspace.get_record(span_record.source_artifact_id)
        document = workspace.get_record(span_record.normalized_document_id)
        assert isinstance(artifact, SourceArtifact) and isinstance(document, NormalizedDocument)
        original = workspace.source_bytes(artifact)
        normalized = workspace.artifact_bytes(document.normalized_text_artifact_hash)
        exact = normalized[span_record.normalized_start:span_record.normalized_end]
        locator = span_record.original_locator
        if locator.original_start is None or locator.original_end is None:
            raise ValueError("plain-text span lacks original byte locator")
        original_quote = original[locator.original_start:locator.original_end]
        if sha256_bytes(exact) != span_record.exact_text_hash:
            raise ValueError("normalized span hash mismatch")
        if sha256_bytes(original_quote) != span_record.original_quote_hash:
            raise ValueError("original span hash mismatch")
        spans_checked += 1
    return {"schema_version": MEMORY_SCHEMA_VERSION, "spans_checked": spans_checked, "all_exact": True}
