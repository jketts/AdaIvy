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
    retrieve_evidence,
)

__all__ = [
    "CorpusRetrievalError",
    "EVIDENCE_CARD_SCHEMA_VERSION",
    "PROJECTION_SCHEMA_VERSION",
    "Projection",
    "build_projection",
    "embed_query",
    "load_projection",
    "retrieve_evidence",
]
