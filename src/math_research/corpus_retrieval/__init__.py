"""Persistent retrieval projections over ADR-0072 corpus generations.

The corpus generation remains primary evidence and is never edited to claim it
is indexed.  A projection is a separate immutable artifact binding one active
generation to exactly one ``(provider, model, dimension, normalization)``
partition and to the immutable vector artifacts produced for its documents.
"""

PROJECTION_SCHEMA_VERSION = "adaivy.corpus-retrieval-projection.v1"
EVIDENCE_CARD_SCHEMA_VERSION = "adaivy.corpus-retrieval-evidence-card.v1"

from .service import (  # noqa: E402
    CorpusRetrievalError,
    Projection,
    build_projection,
    embed_query,
    load_projection,
    load_retrieval_result,
    retrieve_evidence,
)
from .chunked import (  # noqa: E402
    CHUNKED_EVIDENCE_CARD_SCHEMA_VERSION,
    CHUNKED_PROJECTION_SCHEMA_VERSION,
    ChunkingConfig,
    build_chunked_projection,
    chunk_spans,
    embed_chunked_query,
    load_chunked_projection,
    retrieve_chunked_evidence,
)

__all__ = [
    "CHUNKED_EVIDENCE_CARD_SCHEMA_VERSION",
    "CHUNKED_PROJECTION_SCHEMA_VERSION",
    "ChunkingConfig",
    "CorpusRetrievalError",
    "EVIDENCE_CARD_SCHEMA_VERSION",
    "PROJECTION_SCHEMA_VERSION",
    "Projection",
    "build_chunked_projection",
    "build_projection",
    "chunk_spans",
    "embed_chunked_query",
    "embed_query",
    "load_chunked_projection",
    "load_projection",
    "load_retrieval_result",
    "retrieve_chunked_evidence",
    "retrieve_evidence",
]
