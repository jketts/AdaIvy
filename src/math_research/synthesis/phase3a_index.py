"""A `ResultIndex` backed by the existing Phase 3A FTS5/BM25 memory.

Contract Section 6 requires that canonical source and result state stay
independent of any index, and Section 13 forbids this slice from adding a result
extractor. So this adapter does exactly two things: it delegates search to the
unmodified Phase 3A `DeterministicRetriever`, and it joins each hit to declarative
traversal metadata supplied by a project-authored manifest. It derives no
structure from source text itself.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..domain.entities import OpaqueId
from ..phase3a.retrieval import DeterministicRetriever
from ..phase3a.workspace import ResearchMemoryWorkspace
from .ports import IndexHit, IndexedResult
from .state import SynthesisValidationError

ADAPTER_ID = "phase3a-fts5-bm25"
ADAPTER_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultDescriptor:
    """Declarative traversal metadata for one indexed source."""

    source_artifact_id: str
    title: str
    expansion_terms: tuple[str, ...]
    citations: tuple[str, ...]
    approach_signature: str


class Phase3AResultIndex:
    """Adapter over one Phase 3A research-memory workspace."""

    adapter_id = ADAPTER_ID
    adapter_version = ADAPTER_VERSION

    def __init__(
        self,
        workspace: ResearchMemoryWorkspace,
        *,
        corpus_manifest_hash: str,
        descriptors: Mapping[str, ResultDescriptor],
        aggregate_id: OpaqueId,
        actor_id: OpaqueId,
        created_at: str,
    ) -> None:
        self.workspace = workspace
        self._retriever = DeterministicRetriever(workspace)
        self._corpus_manifest_hash = corpus_manifest_hash
        self._descriptors = dict(descriptors)
        self._aggregate_id = aggregate_id
        self._actor_id = actor_id
        self._created_at = created_at

    def corpus_manifest_hash(self) -> str:
        return self._corpus_manifest_hash

    def search(self, query: str, *, limit: int) -> tuple[IndexHit, ...]:
        """Delegate to the unmodified Phase 3A deterministic retriever."""
        result = self._retriever.search(
            query,
            corpus_manifest_hash=self._corpus_manifest_hash,
            limit=limit,
            aggregate_id=self._aggregate_id,
            actor_id=self._actor_id,
            created_at=self._created_at,
        )
        return tuple(
            IndexHit(
                result_id=hit.evidence_unit_id.value,
                rank=hit.rank,
                canonical_score=hit.canonical_score,
                tie_break_key=hit.tie_break_key,
            )
            for hit in result.hits
        )

    def get(self, result_id: str) -> IndexedResult:
        record = self.workspace.get_record(OpaqueId(result_id))
        source_artifact_id = getattr(record, "source_artifact_id", None)
        if source_artifact_id is None:
            raise SynthesisValidationError(
                f"indexed result {result_id} has no source artifact and cannot be traversed"
            )
        key = source_artifact_id.value
        descriptor = self._descriptors.get(key)
        if descriptor is None:
            raise SynthesisValidationError(
                f"no declared traversal descriptor for source artifact {key}"
            )
        return IndexedResult(
            result_id=result_id,
            source_id=key,
            title=descriptor.title,
            terms=descriptor.expansion_terms,
            citations=descriptor.citations,
            approach_signature=descriptor.approach_signature,
        )

    def descriptors(self) -> dict[str, ResultDescriptor]:
        return dict(self._descriptors)


__all__ = ["ADAPTER_ID", "ADAPTER_VERSION", "Phase3AResultIndex", "ResultDescriptor"]
