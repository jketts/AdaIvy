"""Inward-facing embedding ports.

`EmbeddingGateway` is a SIBLING of `phase2.ports.ModelGateway`, not a
specialisation of it: an embeddings call has no response schema, no output
tokens, and returns a vector rather than a JSON string.

`RightsGate` and `SourceTextReader` exist so ingestion can be ordered and
observed: the rights decision is checked BEFORE the text is read, following the
ordering already used at `service.py:185`.
"""

from __future__ import annotations

from typing import Any, Protocol

from .records import EmbeddingRequest, EmbeddingResult


class EmbeddingGateway(Protocol):
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...


class RightsGate(Protocol):
    """ADR-0064's processor-bound rights check.

    Slice A adds ``processor_id`` to Phase 4A's ``require_rights``. The keyword
    is REQUIRED here rather than optional in effect: an adapter that cannot
    forward it must refuse, because rights bind the processor and not only the
    use (`TECHNICAL_BLUEPRINT.md:1672-1675`).
    """

    def require_rights(
        self, source_id: str, intended_use: Any, *, at: str,
        processor_id: str | None = None,
    ) -> Any: ...


class SourceTextReader(Protocol):
    """Reads the bytes that will be disclosed to a processor.

    A port rather than a bare ``Path`` so `pr.embedding-without-rights-refused`
    can assert that no read happened, instead of asserting it by inspection.
    """

    def read(self, source_id: str) -> bytes: ...


__all__ = ["EmbeddingGateway", "RightsGate", "SourceTextReader"]
