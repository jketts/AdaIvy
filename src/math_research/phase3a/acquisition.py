"""Manual, local-only Phase 3A source acquisition."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from ..domain.entities import OpaqueId
from .plain_text import PlainTextV1Parser, contains_prompt_injection
from .records import (
    AcquisitionStatus,
    Disposition,
    LicenseMetadata,
    QuarantineState,
    ResearchMemoryRecord,
    SourceArtifact,
    SourceReference,
    SourceVersionRelation,
)
from .serialization import canonical_hash, freeze_json, stable_id
from .workspace import ResearchMemoryWorkspace

MAX_SOURCE_BYTES = 2 * 1024 * 1024
ACQUISITION_ADAPTER = "manual-local-file-v1"
ACQUISITION_ADAPTER_VERSION = "1.0.0"
_URI = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:[^\x00-\x1f\x7f]*$")


@dataclass(frozen=True, slots=True)
class IngestionResult:
    source_reference: SourceReference
    source_artifact: SourceArtifact | None
    record_ids: tuple[OpaqueId, ...]
    quarantined: bool
    quarantine_reasons: tuple[str, ...]


def validate_opaque_uri(value: str) -> str:
    if len(value) > 2048 or not _URI.fullmatch(value):
        raise ValueError("invalid opaque source locator syntax")
    return value


def _read_regular_file(path: Path, *, max_bytes: int) -> bytes:
    if not path.is_absolute():
        raise ValueError("manual source path must be absolute")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("manual source must be a regular file")
        if metadata.st_size > max_bytes:
            raise ValueError("manual source exceeds the configured byte budget")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise ValueError("manual source exceeds the configured byte budget")
        return data
    finally:
        os.close(descriptor)


class ManualSourceIngestor:
    def __init__(self, workspace: ResearchMemoryWorkspace) -> None:
        self.workspace = workspace
        self.parser = PlainTextV1Parser(workspace.artifacts)

    def import_metadata_only(
        self,
        *,
        supplied_uri: str,
        title: str,
        authors: tuple[str, ...],
        publication_metadata: dict[str, object],
        license_metadata: LicenseMetadata,
        actor_id: OpaqueId,
        recorded_at: str,
        aggregate_id: OpaqueId,
    ) -> IngestionResult:
        locator = validate_opaque_uri(supplied_uri)
        source_id = stable_id("source", {"uri": locator, "title": title, "authors": authors})
        reference = SourceReference(
            id=source_id, canonical_uri=locator, supplied_uri=locator, title=title, authors=authors,
            publication_metadata=freeze_json(publication_metadata),  # type: ignore[arg-type]
            metadata_assertion_source="operator", metadata_status="proposed", retrieved_or_recorded_at=recorded_at,
            license_metadata=license_metadata, acquisition_status=AcquisitionStatus.METADATA_ONLY,
            content_hash=None, created_at=recorded_at, created_by=actor_id,
        )
        request_hash = canonical_hash({"operation": "metadata_only", "record": reference})
        record_ids = self.workspace.commit_records(
            (reference,), aggregate_id=aggregate_id, command_id=stable_id("command", request_hash),
            kind="source_metadata", idempotency_key=f"metadata:{source_id.value}", request_hash=request_hash,
            now=recorded_at, deadline_at="9999-12-31T23:59:59Z",
        )
        return IngestionResult(reference, None, record_ids, False, ())

    def import_local(
        self,
        path: Path,
        *,
        supplied_uri: str,
        title: str,
        authors: tuple[str, ...],
        publication_metadata: dict[str, object],
        license_metadata: LicenseMetadata,
        declared_media_type: str,
        actor_id: OpaqueId,
        recorded_at: str,
        aggregate_id: OpaqueId,
        max_bytes: int = MAX_SOURCE_BYTES,
        fail_after_artifact: bool = False,
    ) -> IngestionResult:
        locator = validate_opaque_uri(supplied_uri)
        data = _read_regular_file(path, max_bytes=max_bytes)
        artifact_ref = self.workspace.artifacts.put(data, media_type="application/octet-stream")
        if fail_after_artifact:
            raise RuntimeError("simulated crash after artifact creation")
        reasons: list[str] = []
        detected_media_type = "text/plain"
        if declared_media_type != "text/plain":
            reasons.append("unsupported_declared_media_type")
        if path.suffix.casefold() != ".txt":
            reasons.append("unsupported_file_extension")
        if data.startswith(b"%PDF-"):
            detected_media_type = "application/pdf"
            reasons.append("pdf_unsupported")
        try:
            data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            detected_media_type = "unsupported"
            reasons.append("invalid_utf8")
        if b"\x00" in data:
            detected_media_type = "unsupported"
            reasons.append("binary_nul")
        if contains_prompt_injection(data):
            reasons.append("prompt_injection")
        if license_metadata.reviewed_by is None:
            reasons.append("rights_unreviewed")
        reasons = sorted(set(reasons))
        quarantine_state = QuarantineState.QUARANTINED if reasons else QuarantineState.ELIGIBLE
        source_id = stable_id("source", {"content_hash": artifact_ref.content_hash})
        reference = SourceReference(
            id=source_id, canonical_uri=locator, supplied_uri=locator, title=title, authors=authors,
            publication_metadata=freeze_json(publication_metadata),  # type: ignore[arg-type]
            metadata_assertion_source="operator", metadata_status="checked", retrieved_or_recorded_at=recorded_at,
            license_metadata=license_metadata, acquisition_status=AcquisitionStatus.BYTES_AVAILABLE,
            content_hash=artifact_ref.content_hash, created_at=recorded_at, created_by=actor_id,
        )
        artifact = SourceArtifact(
            id=stable_id("artifact", {"content_hash": artifact_ref.content_hash}), source_reference_id=reference.id,
            artifact_hash=artifact_ref.content_hash, byte_length=len(data), declared_media_type=declared_media_type,
            detected_media_type=detected_media_type, acquisition_method="local_file", acquired_at=recorded_at,
            acquisition_adapter=ACQUISITION_ADAPTER, acquisition_adapter_version=ACQUISITION_ADAPTER_VERSION,
            quarantine_state=quarantine_state, quarantine_reasons=tuple(reasons), content_hash=artifact_ref.content_hash,
            created_at=recorded_at, created_by=actor_id,
        )
        bundle = (
            self.parser.quarantined_run(artifact, reasons=tuple(reasons), created_at=recorded_at)
            if reasons else self.parser.parse(artifact, data, actor_id=actor_id, created_at=recorded_at)
        )
        records: tuple[ResearchMemoryRecord, ...] = (
            reference, artifact, bundle.parser_run,
            *((bundle.normalized_document,) if bundle.normalized_document is not None else ()),
            *bundle.spans, *bundle.markers, *bundle.evidence_units,
        )
        request_hash = canonical_hash(
            {"operation": "local_import", "artifact_hash": artifact.artifact_hash, "metadata": reference, "parser": bundle.parser_run.parser_configuration_hash}
        )
        record_ids = self.workspace.commit_records(
            records, aggregate_id=aggregate_id, command_id=stable_id("command", request_hash), kind="source_ingestion",
            idempotency_key=f"ingest:{artifact.artifact_hash}", request_hash=request_hash, now=recorded_at,
            deadline_at="9999-12-31T23:59:59Z", max_attempts=2,
        )
        return IngestionResult(reference, artifact, record_ids, bool(reasons), tuple(reasons))

    def relate_versions(
        self,
        older: SourceArtifact,
        newer: SourceArtifact,
        *,
        actor_id: OpaqueId,
        created_at: str,
        aggregate_id: OpaqueId,
    ) -> SourceVersionRelation:
        relation = SourceVersionRelation(
            id=stable_id("source-version", {"older": older.id.value, "newer": newer.id.value, "relation": "supersedes"}),
            source_artifact_id=newer.id, target_artifact_id=older.id, relation="supersedes",
            assertion_origin="operator", disposition=Disposition.ACCEPTED, evidence_span_id=None,
            created_at=created_at, created_by=actor_id,
        )
        request_hash = canonical_hash(relation)
        self.workspace.commit_records(
            (relation,), aggregate_id=aggregate_id, command_id=stable_id("command", request_hash), kind="source_version",
            idempotency_key=f"version:{relation.id.value}", request_hash=request_hash, now=created_at,
            deadline_at="9999-12-31T23:59:59Z",
        )
        return relation
