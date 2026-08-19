"""Canonical JSON mapping for Phase 3A internal records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from typing import Any, Mapping, cast

from ..domain.entities import OpaqueId
from .records import (
    AcquisitionStatus,
    Disposition,
    DocumentMarker,
    EvidenceOrigin,
    EvidencePackManifest,
    EvidenceRelation,
    EvidenceUnit,
    EvidenceUnitType,
    ExcludedPackItem,
    ExtractionWarning,
    FrozenJson,
    LicenseMetadata,
    NormalizedDocument,
    OriginalLocator,
    ParserRunRecord,
    QuarantineState,
    RelationOrigin,
    RelationType,
    ResearchMemoryRecord,
    RetrievalHit,
    RetrievalQueryRecord,
    SourceArtifact,
    SourceReference,
    SourceSpan,
    SourceVersionRelation,
)

ZERO_HASH = "sha256:" + "0" * 64
_OBJECT_FIELDS = {"publication_metadata", "payload", "filters", "source_diversity_policy"}


def freeze_json(value: Any) -> FrozenJson:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("non-finite JSON number")
        return value
    if isinstance(value, Mapping):
        return tuple((str(key), freeze_json(item)) for key, item in sorted(value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    raise TypeError(f"not a JSON value: {type(value).__name__}")


def thaw_json(value: FrozenJson) -> Any:
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
            return {item[0]: thaw_json(cast(FrozenJson, item[1])) for item in value}
        return [thaw_json(cast(FrozenJson, item)) for item in value]
    return value


def public_value(value: Any, *, field_name: str | None = None) -> Any:
    if isinstance(value, OpaqueId):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: public_value(getattr(value, field.name), field_name=field.name)
            for field in fields(value)
        }
    if isinstance(value, tuple):
        if field_name in _OBJECT_FIELDS:
            return thaw_json(cast(FrozenJson, value))
        return [public_value(item) for item in value]
    if isinstance(value, list):
        return [public_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): public_value(item) for key, item in value.items()}
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        public_value(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json(value: Any) -> str:
    return canonical_bytes(value).decode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def stable_id(prefix: str, value: Any) -> OpaqueId:
    return OpaqueId(f"{prefix}.{canonical_hash(value)[7:31]}")


def self_content_hash(record: ResearchMemoryRecord) -> str:
    payload = public_value(record)
    if "content_hash" not in payload:
        raise TypeError(f"record has no self content hash: {type(record).__name__}")
    payload["content_hash"] = None
    return canonical_hash(payload)


def finalize_content_hash(record: ResearchMemoryRecord) -> ResearchMemoryRecord:
    if isinstance(record, (SourceReference, SourceArtifact)):
        return record
    if not hasattr(record, "content_hash"):
        return record
    return cast(ResearchMemoryRecord, replace(record, content_hash=self_content_hash(record)))


def validate_record_hashes(record: ResearchMemoryRecord) -> None:
    if isinstance(record, SourceArtifact):
        if record.content_hash != record.artifact_hash:
            raise ValueError("source artifact byte hash mismatch")
    elif not isinstance(record, SourceReference) and hasattr(record, "content_hash"):
        expected = self_content_hash(record)
        if cast(Any, record).content_hash != expected:
            raise ValueError(f"{type(record).__name__} content hash mismatch")


def _oid(value: str | None) -> OpaqueId | None:
    return OpaqueId(value) if value is not None else None


def _oids(values: list[str]) -> tuple[OpaqueId, ...]:
    return tuple(OpaqueId(value) for value in values)


def record_from_dict(record_type: str, value: Mapping[str, Any]) -> ResearchMemoryRecord:
    """Construct a typed immutable record from validated public JSON."""

    classes = {
        "source_reference": SourceReference,
        "source_artifact": SourceArtifact,
        "source_version_relation": SourceVersionRelation,
        "parser_run": ParserRunRecord,
        "normalized_document": NormalizedDocument,
        "source_span": SourceSpan,
        "document_marker": DocumentMarker,
        "evidence_unit": EvidenceUnit,
        "evidence_relation": EvidenceRelation,
        "retrieval_query": RetrievalQueryRecord,
        "retrieval_hit": RetrievalHit,
        "evidence_pack": EvidencePackManifest,
    }
    if record_type not in classes:
        raise ValueError(f"unknown research-memory record type: {record_type}")
    expected_fields = {field.name for field in fields(classes[record_type])}
    if set(value) != expected_fields:
        raise ValueError(
            f"{record_type} fields differ: missing={sorted(expected_fields - set(value))}, "
            f"extra={sorted(set(value) - expected_fields)}"
        )
    common_schema = value.get("schema_version", "")
    if record_type == "source_reference":
        license_value = value["license_metadata"]
        expected_license = {field.name for field in fields(LicenseMetadata)}
        if set(license_value) != expected_license:
            raise ValueError("license metadata fields differ")
        record: ResearchMemoryRecord = SourceReference(
            id=OpaqueId(value["id"]), canonical_uri=value["canonical_uri"], supplied_uri=value["supplied_uri"],
            title=value["title"], authors=tuple(value["authors"]),
            publication_metadata=cast(Any, freeze_json(value["publication_metadata"])),
            metadata_assertion_source=value["metadata_assertion_source"], metadata_status=value["metadata_status"],
            retrieved_or_recorded_at=value["retrieved_or_recorded_at"],
            license_metadata=LicenseMetadata(
                license_expression=license_value["license_expression"], copyright_notice=license_value["copyright_notice"],
                usage_rights=tuple(license_value["usage_rights"]), redistribution_status=license_value["redistribution_status"],
                evidence_uri=license_value["evidence_uri"], reviewed_by=_oid(license_value["reviewed_by"]),
            ), acquisition_status=AcquisitionStatus(value["acquisition_status"]), content_hash=value["content_hash"],
            created_at=value["created_at"], created_by=OpaqueId(value["created_by"]), schema_version=common_schema,
        )
    elif record_type == "source_artifact":
        record = SourceArtifact(
            id=OpaqueId(value["id"]), source_reference_id=OpaqueId(value["source_reference_id"]),
            artifact_hash=value["artifact_hash"], byte_length=value["byte_length"], declared_media_type=value["declared_media_type"],
            detected_media_type=value["detected_media_type"], acquisition_method=value["acquisition_method"], acquired_at=value["acquired_at"],
            acquisition_adapter=value["acquisition_adapter"], acquisition_adapter_version=value["acquisition_adapter_version"],
            quarantine_state=QuarantineState(value["quarantine_state"]), quarantine_reasons=tuple(value["quarantine_reasons"]),
            content_hash=value["content_hash"], created_at=value["created_at"], created_by=OpaqueId(value["created_by"]), schema_version=common_schema,
        )
    elif record_type == "source_version_relation":
        record = SourceVersionRelation(
            id=OpaqueId(value["id"]), source_artifact_id=OpaqueId(value["source_artifact_id"]), target_artifact_id=OpaqueId(value["target_artifact_id"]),
            relation=value["relation"], assertion_origin=value["assertion_origin"], disposition=Disposition(value["disposition"]),
            evidence_span_id=_oid(value["evidence_span_id"]), created_at=value["created_at"], created_by=OpaqueId(value["created_by"]), schema_version=common_schema,
        )
    elif record_type == "parser_run":
        record = ParserRunRecord(
            id=OpaqueId(value["id"]), source_artifact_id=OpaqueId(value["source_artifact_id"]), parser_name=value["parser_name"], parser_version=value["parser_version"],
            parser_configuration_hash=value["parser_configuration_hash"], dependency_environment_hash=value["dependency_environment_hash"], input_hash=value["input_hash"],
            status=value["status"], warning_codes=tuple(value["warning_codes"]), declared_confidence=value["declared_confidence"], stdout_artifact_hash=value["stdout_artifact_hash"],
            stderr_artifact_hash=value["stderr_artifact_hash"], output_artifact_hash=value["output_artifact_hash"], idempotency_key=value["idempotency_key"],
            created_at=value["created_at"], schema_version=common_schema,
        )
    elif record_type == "normalized_document":
        record = NormalizedDocument(
            id=OpaqueId(value["id"]), source_artifact_id=OpaqueId(value["source_artifact_id"]), parser_run_id=OpaqueId(value["parser_run_id"]),
            normalized_text_artifact_hash=value["normalized_text_artifact_hash"], structure_map_artifact_hash=value["structure_map_artifact_hash"],
            location_map_artifact_hash=value["location_map_artifact_hash"], unicode_normalization=value["unicode_normalization"], newline_policy=value["newline_policy"],
            coordinate_unit=value["coordinate_unit"], normalization_version=value["normalization_version"],
            warnings=tuple(ExtractionWarning(**warning) for warning in value["warnings"]), disposition=Disposition(value["disposition"]),
            content_hash=value["content_hash"], created_at=value["created_at"], created_by=OpaqueId(value["created_by"]), schema_version=common_schema,
        )
    elif record_type == "source_span":
        locator = value["original_locator"]
        record = SourceSpan(
            id=OpaqueId(value["id"]), source_artifact_id=OpaqueId(value["source_artifact_id"]), normalized_document_id=OpaqueId(value["normalized_document_id"]),
            normalized_start=value["normalized_start"], normalized_end=value["normalized_end"], page_number=value["page_number"], section_path=tuple(value["section_path"]),
            original_locator=OriginalLocator(**locator), exact_text_hash=value["exact_text_hash"], original_quote_hash=value["original_quote_hash"],
            content_hash=value["content_hash"], schema_version=common_schema,
        )
    elif record_type == "document_marker":
        record = DocumentMarker(
            id=OpaqueId(value["id"]), normalized_document_id=OpaqueId(value["normalized_document_id"]), span_id=OpaqueId(value["span_id"]), marker_type=value["marker_type"],
            label=value["label"], ordinal=value["ordinal"], extraction_method=value["extraction_method"], disposition=Disposition(value["disposition"]),
            warning_codes=tuple(value["warning_codes"]), content_hash=value["content_hash"], schema_version=common_schema,
        )
    elif record_type == "evidence_unit":
        record = EvidenceUnit(
            id=OpaqueId(value["id"]), unit_type=EvidenceUnitType(value["unit_type"]), origin=EvidenceOrigin(value["origin"]),
            source_artifact_id=_oid(value["source_artifact_id"]), normalized_document_id=_oid(value["normalized_document_id"]), source_span_ids=_oids(value["source_span_ids"]),
            model_call_id=_oid(value["model_call_id"]), proposal_artifact_hash=value["proposal_artifact_hash"], payload=cast(Any, freeze_json(value["payload"])),
            extraction_method=value["extraction_method"], extraction_version=value["extraction_version"], warning_codes=tuple(value["warning_codes"]),
            disposition=Disposition(value["disposition"]), content_hash=value["content_hash"], created_at=value["created_at"], created_by=OpaqueId(value["created_by"]), schema_version=common_schema,
        )
    elif record_type == "evidence_relation":
        record = EvidenceRelation(
            id=OpaqueId(value["id"]), source_unit_id=OpaqueId(value["source_unit_id"]), target_unit_id=OpaqueId(value["target_unit_id"]),
            relation_type=RelationType(value["relation_type"]), assertion_origin=RelationOrigin(value["assertion_origin"]), assertion_span_ids=_oids(value["assertion_span_ids"]),
            extraction_or_actor_id=value["extraction_or_actor_id"], disposition=Disposition(value["disposition"]), review_record_ids=_oids(value["review_record_ids"]),
            content_hash=value["content_hash"], created_at=value["created_at"], created_by=OpaqueId(value["created_by"]), schema_version=common_schema,
        )
    elif record_type == "retrieval_query":
        record = RetrievalQueryRecord(
            id=OpaqueId(value["id"]), canonical_query=value["canonical_query"], query_hash=value["query_hash"], corpus_manifest_hash=value["corpus_manifest_hash"],
            retrieval_method=value["retrieval_method"], retrieval_version=value["retrieval_version"], engine_version=value["engine_version"],
            tokenizer_configuration=value["tokenizer_configuration"], field_weights=tuple(value["field_weights"]), filters=cast(Any, freeze_json(value["filters"])),
            requested_limit=value["requested_limit"], created_at=value["created_at"], created_by=OpaqueId(value["created_by"]), schema_version=common_schema,
        )
    elif record_type == "retrieval_hit":
        record = RetrievalHit(
            id=OpaqueId(value["id"]), query_id=OpaqueId(value["query_id"]), rank=value["rank"], evidence_unit_id=OpaqueId(value["evidence_unit_id"]),
            source_artifact_id=OpaqueId(value["source_artifact_id"]), source_span_ids=_oids(value["source_span_ids"]), raw_score=value["raw_score"],
            canonical_score=value["canonical_score"], tie_break_key=value["tie_break_key"], schema_version=common_schema,
        )
    elif record_type == "evidence_pack":
        record = EvidencePackManifest(
            id=OpaqueId(value["id"]), query_id=OpaqueId(value["query_id"]), retrieval_result_hash=value["retrieval_result_hash"], policy_version=value["policy_version"],
            byte_budget=value["byte_budget"], token_budget=value["token_budget"], token_counter_id=value["token_counter_id"],
            included_evidence_unit_ids=_oids(value["included_evidence_unit_ids"]), included_source_artifact_ids=_oids(value["included_source_artifact_ids"]),
            included_source_span_ids=_oids(value["included_source_span_ids"]), excluded_items=tuple(ExcludedPackItem(evidence_unit_id=OpaqueId(item["evidence_unit_id"]), reason=item["reason"]) for item in value["excluded_items"]),
            source_diversity_policy=cast(Any, freeze_json(value["source_diversity_policy"])), injection_annotations=_oids(value["injection_annotations"]),
            serialized_pack_artifact_hash=value["serialized_pack_artifact_hash"], content_hash=value["content_hash"], created_at=value["created_at"],
            created_by=OpaqueId(value["created_by"]), schema_version=common_schema,
        )
    else:
        raise ValueError(f"unknown research-memory record type: {record_type}")
    validate_record_hashes(record)
    return record
