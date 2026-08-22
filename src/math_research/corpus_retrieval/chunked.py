"""ADR-0080 chunked projections: bounded chunks as the retrieval unit.

A v1 projection embeds one vector per whole document; this module embeds one
vector per deterministic fixed-size character window (with declared overlap)
over the document's extracted text.  The chunking parameters are declared in
the projection manifest, chunk spans are exact character offsets carried with
the sha256 of their exact text, and retrieval returns per-chunk evidence
cards — a single document may yield many cards.  Partition purity is
unchanged: one ``(provider, model, dimension, normalization)`` partition per
projection, one corpus provenance, and never a mixed one.

Trust is unchanged too: every card is an ``untrusted_inspiration_candidate``
with unresolved applicability, and nothing here creates warrant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..corpus_service.constants import (
    CHUNKING_POLICY,
    MAX_CHUNKS_PER_DOCUMENT,
    MAX_CHUNK_WINDOW_CHARS,
)
from ..corpus_service.dataroot import read_object, write_object
from ..corpus_service.generation import require_active_generation
from ..corpus_service.serialization import (
    canonical_bytes,
    sealed,
    sha256_bytes,
    strict_canonical_object,
    verify_sealed,
)
from ..embedding.gateways import gateway_corpus_provenance
from ..embedding.partition import (
    ARTIFACT_KIND_DOCUMENT,
    ARTIFACT_KIND_QUERY,
    PartitionKey,
    PartitionedVector,
    artifact_payload,
    create_vector_artifact,
)
from ..embedding.ports import EmbeddingGateway
from ..embedding.quantization import quantize
from ..embedding.records import EmbeddingRequest
from ..embedding.similarity import rank_exact_cosine
from .service import (
    CorpusRetrievalError,
    _projection_dir,
    _query_dir,
    _result_dir,
    _vector_from_object,
    require_document_embedding_rights,
)

CHUNKED_PROJECTION_SCHEMA_VERSION = "adaivy.corpus-retrieval-chunked-projection.v1"
CHUNKED_QUERY_SCHEMA_VERSION = "adaivy.corpus-retrieval-chunked-query.v1"
CHUNKED_EVIDENCE_CARD_SCHEMA_VERSION = "adaivy.corpus-retrieval-chunked-evidence-card.v1"
CHUNKED_RESULT_SCHEMA_VERSION = "adaivy.corpus-retrieval-chunked-result.v1"

_CHUNKED_QUERY_ID = re.compile(r"^chunkquery\.[0-9a-f]{24}$")
_CHUNKED_RETRIEVAL_ID = re.compile(r"^chunkretrieval\.[0-9a-f]{24}$")
_RANKING_POLICY = "exact_cosine_desc_then_chunk_id_asc_v1"

_VECTOR_ENTRY_FIELDS = frozenset({
    "document_id", "chunk_index", "start_offset", "end_offset", "text_sha256",
    "exact_text_hash", "source_content_hash", "artifact_content_hash",
    "artifact_object_hash", "corpus_provenance",
})


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    """Declared in the projection manifest; a config states, never widens."""

    window_chars: int
    overlap_chars: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.window_chars, bool)
            or not isinstance(self.window_chars, int)
            or not 1 <= self.window_chars <= MAX_CHUNK_WINDOW_CHARS
        ):
            raise CorpusRetrievalError(
                f"chunk window must be 1..{MAX_CHUNK_WINDOW_CHARS} characters"
            )
        if (
            isinstance(self.overlap_chars, bool)
            or not isinstance(self.overlap_chars, int)
            or not 0 <= self.overlap_chars < self.window_chars
        ):
            raise CorpusRetrievalError(
                "chunk overlap must be a non-negative integer smaller than "
                "the window"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "policy": CHUNKING_POLICY,
            "window_chars": self.window_chars,
            "overlap_chars": self.overlap_chars,
        }

    @classmethod
    def from_payload(cls, value: Any) -> "ChunkingConfig":
        if not isinstance(value, Mapping) or set(value) != {
            "policy", "window_chars", "overlap_chars",
        } or value["policy"] != CHUNKING_POLICY:
            raise CorpusRetrievalError("chunking declaration differs")
        return cls(
            window_chars=value["window_chars"],
            overlap_chars=value["overlap_chars"],
        )


def chunk_spans(text: str, config: ChunkingConfig) -> list[tuple[int, int]]:
    """Deterministic fixed-size windows with declared overlap. Exact offsets."""

    if not text:
        raise CorpusRetrievalError("cannot chunk empty text")
    stride = config.window_chars - config.overlap_chars
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = min(start + config.window_chars, len(text))
        spans.append((start, end))
        if end == len(text):
            break
        start += stride
    if len(spans) > MAX_CHUNKS_PER_DOCUMENT:
        raise CorpusRetrievalError(
            f"document yields {len(spans)} chunks; the pinned bound is "
            f"{MAX_CHUNKS_PER_DOCUMENT}"
        )
    return spans


def _chunk_artifact_id(document_id: str, chunk_index: int) -> str:
    return f"{document_id}.chunk-{chunk_index:05d}"


def _chunked_projection_id(body: Mapping[str, Any]) -> str:
    digest = sha256_bytes(canonical_bytes({
        key: value for key, value in body.items()
        if key not in {"projection_id", "content_hash"}
    }))
    return "chunkgen." + digest.removeprefix("sha256:")[:24]


def _chunked_projection_path(root: Path, projection_id: str) -> Path:
    if not projection_id.startswith("chunkgen.") or any(
        item in projection_id for item in ("/", "\\", "..")
    ):
        raise CorpusRetrievalError("invalid chunked projection identifier")
    return _projection_dir(root).joinpath(projection_id + ".json")


def _verify_chunked_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = verify_sealed(
        value, label="chunked retrieval projection",
        code="retrieval_projection_invalid",
    )
    expected = {
        "schema_version", "projection_id", "corpus_generation_id",
        "corpus_generation_hash", "partition_key", "chunking",
        "corpus_provenance", "vector_count", "vectors", "ranking_policy",
        "creates_warrant", "content_hash",
    }
    if set(manifest) != expected:
        raise CorpusRetrievalError("chunked projection fields differ")
    if manifest["schema_version"] != CHUNKED_PROJECTION_SCHEMA_VERSION:
        raise CorpusRetrievalError("chunked projection schema differs")
    if manifest["creates_warrant"] is not False:
        raise CorpusRetrievalError("chunked projection cannot create warrant")
    if manifest["ranking_policy"] != _RANKING_POLICY:
        raise CorpusRetrievalError("chunked projection ranking policy differs")
    ChunkingConfig.from_payload(manifest["chunking"])
    key = manifest["partition_key"]
    try:
        PartitionKey(
            provider=key["provider"], model_identifier=key["model_identifier"],
            dimension=key["dimension"], normalization=key["normalization"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CorpusRetrievalError("chunked partition key differs") from error
    vectors = manifest["vectors"]
    if not isinstance(vectors, list) or manifest["vector_count"] != len(vectors):
        raise CorpusRetrievalError("chunked projection vector count differs")
    seen: list[tuple[str, int]] = []
    for index, entry in enumerate(vectors):
        if not isinstance(entry, Mapping) or set(entry) != _VECTOR_ENTRY_FIELDS:
            raise CorpusRetrievalError(f"chunked vector {index} fields differ")
        if entry["corpus_provenance"] != manifest["corpus_provenance"]:
            raise CorpusRetrievalError("a projection cannot mix vector provenance")
        if (
            isinstance(entry["chunk_index"], bool)
            or not isinstance(entry["chunk_index"], int)
            or entry["chunk_index"] < 0
            or not isinstance(entry["start_offset"], int)
            or not isinstance(entry["end_offset"], int)
            or not 0 <= entry["start_offset"] < entry["end_offset"]
        ):
            raise CorpusRetrievalError(f"chunked vector {index} span differs")
        seen.append((entry["document_id"], entry["chunk_index"]))
    if seen != sorted(set(seen)):
        raise CorpusRetrievalError(
            "chunked vectors must be sorted and unique by (document, chunk)"
        )
    if manifest["projection_id"] != _chunked_projection_id(manifest):
        raise CorpusRetrievalError("chunked projection identity differs")
    return manifest


def _prior_chunk_vectors(
    root: Path, key: PartitionKey, chunking: ChunkingConfig,
) -> dict[tuple[str, int, str], dict[str, Any]]:
    found: dict[tuple[str, int, str], dict[str, Any]] = {}
    directory = _projection_dir(root)
    if not directory.exists():
        return found
    for path in sorted(directory.glob("chunkgen.*.json")):
        value = _verify_chunked_manifest(strict_canonical_object(
            path.read_bytes(), maximum=67_108_864,
            label="chunked retrieval projection",
            code="retrieval_projection_invalid",
        ))
        try:
            generation = require_active_generation(root, value["corpus_generation_id"])
        except Exception:
            continue
        if generation["content_hash"] != value["corpus_generation_hash"]:
            continue
        if value["partition_key"] != key.payload():
            continue
        if value["chunking"] != chunking.payload():
            continue
        for entry in value["vectors"]:
            found[(
                entry["document_id"], entry["chunk_index"],
                entry["exact_text_hash"],
            )] = dict(entry)
    return found


def _document_text_hash(document: Mapping[str, Any]) -> str:
    extracted = document.get("extracted_sha256")
    return extracted if extracted is not None else document["source_sha256"]


def build_chunked_projection(
    root: Path, *, generation_id: str, key: PartitionKey,
    chunking: ChunkingConfig, gateway: EmbeddingGateway, processor_id: str,
    max_input_tokens: int, timeout_milliseconds: int, recorded_at: str,
) -> dict[str, Any]:
    """Embed chunk deltas and publish an immutable chunked projection."""

    generation = require_active_generation(root, generation_id)
    prior = _prior_chunk_vectors(root, key, chunking)
    produced_provenance = gateway_corpus_provenance(gateway)
    entries: list[dict[str, Any]] = []
    provider_calls = 0
    for document in generation["entries"]:
        if not document["full_text_stored"] or document["spans_sha256"] is None:
            continue
        require_document_embedding_rights(
            root, document=document, key=key, processor_id=processor_id,
            recorded_at=recorded_at,
        )
        text_sha256 = _document_text_hash(document)
        try:
            text = read_object(root, text_sha256).decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            raise CorpusRetrievalError("stored text is not strict UTF-8") from error
        for chunk_index, (start, end) in enumerate(chunk_spans(text, chunking)):
            exact = text[start:end]
            exact_text_hash = sha256_bytes(exact.encode("utf-8"))
            reuse = prior.get((document["document_id"], chunk_index, exact_text_hash))
            if reuse is not None:
                entry = dict(reuse)
                # Re-verify the stored artifact bytes before trusting reuse.
                _vector_from_object(
                    root, key, {
                        "document_id": _chunk_artifact_id(
                            entry["document_id"], entry["chunk_index"],
                        ),
                        "source_content_hash": entry["source_content_hash"],
                        "artifact_content_hash": entry["artifact_content_hash"],
                        "artifact_object_hash": entry["artifact_object_hash"],
                    }, expected_kind=ARTIFACT_KIND_DOCUMENT,
                )
            else:
                artifact_id = _chunk_artifact_id(document["document_id"], chunk_index)
                result = gateway.embed(EmbeddingRequest(
                    document_id=artifact_id,
                    source_id=document["source_id"],
                    source_content_hash=exact_text_hash,
                    text=exact,
                    processor_id=processor_id,
                    max_input_tokens=max_input_tokens,
                    timeout_milliseconds=timeout_milliseconds,
                ))
                provider_calls += 1
                if (
                    result.provider != key.provider
                    or result.model_identifier != key.model_identifier
                ):
                    raise CorpusRetrievalError("embedding result partition differs")
                quantized = quantize(
                    result.provider_coordinates, normalization=key.normalization,
                )
                artifact = create_vector_artifact(
                    key, document_id=artifact_id,
                    source_content_hash=exact_text_hash,
                    coordinates=quantized.coordinates,
                )
                artifact_object_hash = write_object(
                    root, canonical_bytes(artifact_payload(key, artifact)),
                )
                entry = {
                    "document_id": document["document_id"],
                    "chunk_index": chunk_index,
                    "start_offset": start,
                    "end_offset": end,
                    "text_sha256": text_sha256,
                    "exact_text_hash": exact_text_hash,
                    "source_content_hash": exact_text_hash,
                    "artifact_content_hash": artifact.content_hash,
                    "artifact_object_hash": artifact_object_hash,
                    "corpus_provenance": produced_provenance,
                }
            entries.append(entry)
    if not entries:
        raise CorpusRetrievalError("generation has no embedding-authorized full text")
    provenances = {entry["corpus_provenance"] for entry in entries}
    if len(provenances) != 1:
        raise CorpusRetrievalError("a projection cannot mix vector provenance")
    body: dict[str, Any] = {
        "schema_version": CHUNKED_PROJECTION_SCHEMA_VERSION,
        "projection_id": None,
        "corpus_generation_id": generation_id,
        "corpus_generation_hash": generation["content_hash"],
        "partition_key": key.payload(),
        "chunking": chunking.payload(),
        "corpus_provenance": next(iter(provenances)),
        "vector_count": len(entries),
        "vectors": sorted(
            entries, key=lambda item: (item["document_id"], item["chunk_index"]),
        ),
        "ranking_policy": _RANKING_POLICY,
        "creates_warrant": False,
        "content_hash": None,
    }
    body["projection_id"] = _chunked_projection_id(body)
    manifest = _verify_chunked_manifest(sealed(body))
    path = _chunked_projection_path(root, manifest["projection_id"])
    rendered = canonical_bytes(manifest) + b"\n"
    if path.exists():
        if path.read_bytes() != rendered:
            raise CorpusRetrievalError("chunked projection overwrite refused")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".partial")
        temporary.write_bytes(rendered)
        temporary.replace(path)
    return {"manifest": manifest, "provider_calls": provider_calls}


def load_chunked_projection(root: Path, projection_id: str) -> dict[str, Any]:
    manifest = _verify_chunked_manifest(strict_canonical_object(
        _chunked_projection_path(root, projection_id).read_bytes(),
        maximum=67_108_864, label="chunked retrieval projection",
        code="retrieval_projection_invalid",
    ))
    generation = require_active_generation(root, manifest["corpus_generation_id"])
    if generation["content_hash"] != manifest["corpus_generation_hash"]:
        raise CorpusRetrievalError("projection corpus generation hash differs")
    current = {
        entry["document_id"]: _document_text_hash(entry)
        for entry in generation["entries"]
    }
    for entry in manifest["vectors"]:
        if current.get(entry["document_id"]) != entry["text_sha256"]:
            raise CorpusRetrievalError(
                "chunked vector is not bound to the generation's text"
            )
    return manifest


def _load_chunk_artifacts(
    root: Path, manifest: Mapping[str, Any],
) -> dict[str, Any]:
    key_payload = manifest["partition_key"]
    key = PartitionKey(
        provider=key_payload["provider"],
        model_identifier=key_payload["model_identifier"],
        dimension=key_payload["dimension"],
        normalization=key_payload["normalization"],
    )
    artifacts = {}
    for entry in manifest["vectors"]:
        binding = {
            "document_id": _chunk_artifact_id(entry["document_id"], entry["chunk_index"]),
            "source_content_hash": entry["source_content_hash"],
            "artifact_content_hash": entry["artifact_content_hash"],
            "artifact_object_hash": entry["artifact_object_hash"],
        }
        artifacts[binding["document_id"]] = (
            _vector_from_object(
                root, key, binding, expected_kind=ARTIFACT_KIND_DOCUMENT,
            ),
            dict(entry),
        )
    return {"key": key, "artifacts": artifacts}


def embed_chunked_query(
    root: Path, *, projection_id: str, query: str, gateway: EmbeddingGateway,
    processor_id: str, max_input_tokens: int, timeout_milliseconds: int,
) -> dict[str, Any]:
    """Persist one partition-bound query vector for a chunked projection."""

    if not isinstance(query, str) or not query.strip():
        raise CorpusRetrievalError("query must be non-empty")
    manifest = load_chunked_projection(root, projection_id)
    loaded = _load_chunk_artifacts(root, manifest)
    key: PartitionKey = loaded["key"]
    query_bytes = query.encode("utf-8")
    query_hash = sha256_bytes(query_bytes)
    query_id = "query." + query_hash.removeprefix("sha256:")[:24]
    result = gateway.embed(EmbeddingRequest(
        document_id=query_id, source_id=query_id, source_content_hash=query_hash,
        text=query, processor_id=processor_id, max_input_tokens=max_input_tokens,
        timeout_milliseconds=timeout_milliseconds,
    ))
    if result.provider != key.provider or result.model_identifier != key.model_identifier:
        raise CorpusRetrievalError("query embedding result partition differs")
    quantized = quantize(result.provider_coordinates, normalization=key.normalization)
    artifact = create_vector_artifact(
        key, document_id=query_id, source_content_hash=query_hash,
        coordinates=quantized.coordinates, artifact_kind=ARTIFACT_KIND_QUERY,
    )
    query_object_hash = write_object(root, query_bytes)
    artifact_object_hash = write_object(
        root, canonical_bytes(artifact_payload(key, artifact)),
    )
    body = sealed({
        "schema_version": CHUNKED_QUERY_SCHEMA_VERSION,
        "query_embedding_id": "chunkquery." + sha256_bytes(canonical_bytes({
            "projection_id": projection_id,
            "partition_key": key.payload(),
            "query_hash": query_hash,
            "artifact_content_hash": artifact.content_hash,
        })).removeprefix("sha256:")[:24],
        "projection_id": projection_id,
        "projection_hash": manifest["content_hash"],
        "partition_key": key.payload(),
        "query_hash": query_hash,
        "query_object_hash": query_object_hash,
        "artifact_content_hash": artifact.content_hash,
        "artifact_object_hash": artifact_object_hash,
        "ranking_policy": _RANKING_POLICY,
        "creates_warrant": False,
        "content_hash": None,
    })
    path = _query_dir(root).joinpath(body["query_embedding_id"] + ".json")
    rendered = canonical_bytes(body) + b"\n"
    if path.exists() and path.read_bytes() != rendered:
        raise CorpusRetrievalError("query embedding overwrite refused")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(rendered)
    return body


def _load_chunked_query(root: Path, query_embedding_id: str) -> dict[str, Any]:
    if _CHUNKED_QUERY_ID.fullmatch(query_embedding_id) is None:
        raise CorpusRetrievalError("invalid chunked query embedding identifier")
    manifest = verify_sealed(
        strict_canonical_object(
            _query_dir(root).joinpath(query_embedding_id + ".json").read_bytes(),
            maximum=1_048_576, label="chunked query embedding",
            code="retrieval_query_invalid",
        ),
        label="chunked query embedding", code="retrieval_query_invalid",
    )
    if set(manifest) != {
        "schema_version", "query_embedding_id", "projection_id",
        "projection_hash", "partition_key", "query_hash", "query_object_hash",
        "artifact_content_hash", "artifact_object_hash", "ranking_policy",
        "creates_warrant", "content_hash",
    } or manifest["schema_version"] != CHUNKED_QUERY_SCHEMA_VERSION:
        raise CorpusRetrievalError("chunked query embedding fields differ")
    if manifest["ranking_policy"] != _RANKING_POLICY:
        raise CorpusRetrievalError("chunked query ranking policy differs")
    if manifest["creates_warrant"] is not False:
        raise CorpusRetrievalError("chunked query cannot create warrant")
    expected_id = "chunkquery." + sha256_bytes(canonical_bytes({
        "projection_id": manifest["projection_id"],
        "partition_key": manifest["partition_key"],
        "query_hash": manifest["query_hash"],
        "artifact_content_hash": manifest["artifact_content_hash"],
    })).removeprefix("sha256:")[:24]
    if manifest["query_embedding_id"] != query_embedding_id or expected_id != query_embedding_id:
        raise CorpusRetrievalError("chunked query identity differs")
    projection = load_chunked_projection(root, manifest["projection_id"])
    if projection["content_hash"] != manifest["projection_hash"]:
        raise CorpusRetrievalError("chunked query projection binding differs")
    if manifest["partition_key"] != projection["partition_key"]:
        raise CorpusRetrievalError("chunked query partition binding differs")
    return dict(manifest)


def retrieve_chunked_evidence(
    root: Path, *, query_embedding_id: str, limit: int = 5,
) -> tuple[dict[str, Any], ...]:
    """Replay a chunked projection: per-chunk evidence cards, zero provider calls."""

    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise CorpusRetrievalError("limit must be an integer from 1 through 100")
    query_manifest = _load_chunked_query(root, query_embedding_id)
    projection = load_chunked_projection(root, query_manifest["projection_id"])
    loaded = _load_chunk_artifacts(root, projection)
    key: PartitionKey = loaded["key"]
    query_binding = {
        "document_id": None,
        "source_content_hash": query_manifest["query_hash"],
        "artifact_content_hash": query_manifest["artifact_content_hash"],
        "artifact_object_hash": query_manifest["artifact_object_hash"],
    }
    query_value = strict_canonical_object(
        read_object(root, query_manifest["artifact_object_hash"]),
        maximum=16_777_216, label="chunked query vector artifact",
        code="retrieval_query_invalid",
    )
    query_binding["document_id"] = query_value["document_id"]
    query_artifact = _vector_from_object(
        root, key, query_binding, expected_kind=ARTIFACT_KIND_QUERY,
    )
    ranked = rank_exact_cosine(
        PartitionedVector(
            partition_key=key, document_id=query_artifact.document_id,
            coordinates=query_artifact.coordinates,
            artifact_kind=ARTIFACT_KIND_QUERY,
        ),
        tuple(
            PartitionedVector(
                partition_key=key, document_id=chunk_id,
                coordinates=artifact.coordinates,
                artifact_kind=ARTIFACT_KIND_DOCUMENT,
            )
            for chunk_id, (artifact, _) in sorted(loaded["artifacts"].items())
        ),
    )
    generation = require_active_generation(
        root, projection["corpus_generation_id"],
    )
    documents = {entry["document_id"]: entry for entry in generation["entries"]}
    cards: list[dict[str, Any]] = []
    for rank, (chunk_id, cosine) in enumerate(ranked[:limit], start=1):
        _, entry = loaded["artifacts"][chunk_id]
        document = documents[entry["document_id"]]
        text = read_object(root, entry["text_sha256"]).decode("utf-8", "strict")
        exact = text[entry["start_offset"]: entry["end_offset"]]
        if sha256_bytes(exact.encode("utf-8")) != entry["exact_text_hash"]:
            raise CorpusRetrievalError(
                "chunk span does not reproduce its exact text; tamper evidence"
            )
        cards.append(sealed({
            "schema_version": CHUNKED_EVIDENCE_CARD_SCHEMA_VERSION,
            "projection_id": projection["projection_id"],
            "rank": rank,
            "document_id": entry["document_id"],
            "source_id": document["source_id"],
            "source_content_hash": document["source_sha256"],
            "text_sha256": entry["text_sha256"],
            "extraction": document["extraction"],
            "chunk_index": entry["chunk_index"],
            "start_offset": entry["start_offset"],
            "end_offset": entry["end_offset"],
            "exact_text": exact,
            "exact_text_hash": entry["exact_text_hash"],
            "cosine_terms": [cosine[0], cosine[1]],
            "trust_status": "untrusted_inspiration_candidate",
            "applicability_status": "unresolved",
            "creates_warrant": False,
            "content_hash": None,
        }))
    card_object_hashes = [
        write_object(root, canonical_bytes(card) + b"\n") for card in cards
    ]
    result = sealed({
        "schema_version": CHUNKED_RESULT_SCHEMA_VERSION,
        "retrieval_id": "chunkretrieval." + sha256_bytes(canonical_bytes({
            "query_embedding_id": query_embedding_id,
            "limit": limit,
            "evidence_card_hashes": [card["content_hash"] for card in cards],
        })).removeprefix("sha256:")[:24],
        "query_embedding_id": query_embedding_id,
        "projection_id": projection["projection_id"],
        "ranking_policy": _RANKING_POLICY,
        "limit": limit,
        "evidence_card_hashes": [card["content_hash"] for card in cards],
        "evidence_card_object_hashes": card_object_hashes,
        "provider_calls": 0,
        "creates_warrant": False,
        "content_hash": None,
    })
    result_path = _result_dir(root).joinpath(result["retrieval_id"] + ".json")
    rendered = canonical_bytes(result) + b"\n"
    if result_path.exists() and result_path.read_bytes() != rendered:
        raise CorpusRetrievalError("chunked retrieval result overwrite refused")
    if not result_path.exists():
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_bytes(rendered)
    return tuple(cards)


__all__ = [
    "CHUNKED_EVIDENCE_CARD_SCHEMA_VERSION",
    "CHUNKED_PROJECTION_SCHEMA_VERSION",
    "CHUNKED_QUERY_SCHEMA_VERSION",
    "CHUNKED_RESULT_SCHEMA_VERSION",
    "ChunkingConfig",
    "build_chunked_projection",
    "chunk_spans",
    "embed_chunked_query",
    "load_chunked_projection",
    "retrieve_chunked_evidence",
]
