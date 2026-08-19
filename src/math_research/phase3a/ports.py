"""Inward-facing Phase 3A ports.

The ports exchange immutable values and canonical bytes.  They deliberately do
not expose SQLite, the CLI, model providers, or acquisition transports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..domain.entities import OpaqueId
from .plain_text import ParseBundle
from .records import EvidencePackManifest, ResearchMemoryRecord, RetrievalHit, RetrievalQueryRecord, SourceArtifact


class SourceReferenceRepository(Protocol):
    def get_record(self, record_id: OpaqueId) -> ResearchMemoryRecord: ...
    def records(self, record_type: str) -> tuple[ResearchMemoryRecord, ...]: ...


class SourceArtifactRepository(SourceReferenceRepository, Protocol):
    def source_bytes(self, artifact: SourceArtifact) -> bytes: ...


class NormalizedDocumentRepository(SourceArtifactRepository, Protocol):
    def commit_records(self, records: tuple[ResearchMemoryRecord, ...], *, aggregate_id: OpaqueId, command_id: OpaqueId, kind: str, idempotency_key: str, request_hash: str, now: str, deadline_at: str, max_attempts: int = 1) -> tuple[OpaqueId, ...]: ...


class EvidenceUnitRepository(NormalizedDocumentRepository, Protocol):
    pass


class EvidenceRelationRepository(EvidenceUnitRepository, Protocol):
    pass


class ResearchMemoryExportRepository(EvidenceRelationRepository, Protocol):
    def timeline(self, aggregate_id: OpaqueId) -> tuple[dict[str, object], ...]: ...


class DocumentParser(Protocol):
    name: str
    version: str
    def parse(self, artifact: SourceArtifact, original_bytes: bytes, *, actor_id: OpaqueId, created_at: str) -> ParseBundle: ...


class RetrievalIndex(Protocol):
    def rebuild_index(self, *, aggregate_id: OpaqueId, now: str) -> dict[str, object]: ...
    def fts_search(self, expression: str, *, limit: int) -> tuple[dict[str, object], ...]: ...


class EvidencePackBuilder(Protocol):
    def build(self, query: RetrievalQueryRecord, hits: tuple[RetrievalHit, ...], *, byte_budget: int, per_source_cap: int, actor_id: OpaqueId, created_at: str) -> tuple[EvidencePackManifest, bytes]: ...


class ManualSourceAcquirer(Protocol):
    def import_local(self, path: Path, **metadata: object) -> tuple[ResearchMemoryRecord, ...]: ...
