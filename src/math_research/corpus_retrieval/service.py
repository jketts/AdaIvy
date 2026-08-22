"""Corpus-backed exact-vector retrieval with immutable replay artifacts.

Embedding is the only provider-facing operation.  Retrieval consumes frozen
query/document artifacts and immutable source bytes, so replay performs zero
provider calls.  Returned passages are untrusted candidates with unresolved
applicability; rank is never promoted into mathematical warrant.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..corpus_service.dataroot import read_object, write_object
from ..corpus_service.generation import require_active_generation
from ..corpus_service.ledger import read_ledger
from ..corpus_service.rightsstore import PolicyDerivedRightsWriter
from ..corpus_service.serialization import (
    canonical_bytes,
    sealed,
    sha256_bytes,
    strict_canonical_object,
    verify_sealed,
)
from ..corpus_service.spans import verify_spans, verify_spans_against_source
from ..embedding.gateways import gateway_corpus_provenance
from ..embedding.partition import (
    ARTIFACT_KIND_DOCUMENT,
    ARTIFACT_KIND_QUERY,
    ARTIFACT_SCHEMA_VERSION,
    DEFAULT_HASH_RULE,
    PartitionKey,
    PartitionedVector,
    VectorArtifact,
    artifact_payload,
    create_vector_artifact,
)
from ..embedding.ports import EmbeddingGateway
from ..embedding.quantization import quantize
from ..embedding.records import EmbeddingRequest
from ..embedding.similarity import rank_exact_cosine
from ..phase4a.records import RightsUse
from ..phase4a.service import Phase4Service, RightsBlocked
from ..phase4a.workspace import Phase4Workspace
from . import EVIDENCE_CARD_SCHEMA_VERSION, PROJECTION_SCHEMA_VERSION


class CorpusRetrievalError(ValueError):
    """A projection or retrieval request failed closed."""


_QUERY_EMBEDDING_ID = re.compile(r"^queryembedding\.[0-9a-f]{24}$")


@dataclass(frozen=True, slots=True)
class Projection:
    manifest: Mapping[str, Any]
    vectors: Mapping[str, VectorArtifact]
    provider_calls: int = 0

    @property
    def projection_id(self) -> str:
        return str(self.manifest["projection_id"])

    @property
    def key(self) -> PartitionKey:
        payload = self.manifest["partition_key"]
        return PartitionKey(
            provider=payload["provider"],
            model_identifier=payload["model_identifier"],
            dimension=payload["dimension"],
            normalization=payload["normalization"],
        )


def _projection_dir(root: Path) -> Path:
    # Derived projections live below the already protected generations tree.
    return Path(root).joinpath("generations", "retrieval")


def _query_dir(root: Path) -> Path:
    return _projection_dir(root).joinpath("queries")


def _result_dir(root: Path) -> Path:
    return _projection_dir(root).joinpath("results")


def _projection_path(root: Path, projection_id: str) -> Path:
    if not projection_id.startswith("retrievalgen.") or any(
        item in projection_id for item in ("/", "\\", "..")
    ):
        raise CorpusRetrievalError("invalid retrieval projection identifier")
    return _projection_dir(root).joinpath(projection_id + ".json")


def _projection_id(body: Mapping[str, Any]) -> str:
    digest = sha256_bytes(canonical_bytes({
        key: value for key, value in body.items()
        if key not in {"projection_id", "content_hash"}
    }))
    return "retrievalgen." + digest.removeprefix("sha256:")[:24]


def _vector_from_object(
    root: Path, key: PartitionKey, entry: Mapping[str, Any], *, expected_kind: str,
) -> VectorArtifact:
    raw = read_object(root, entry["artifact_object_hash"])
    value = strict_canonical_object(
        raw, maximum=16_777_216, label="vector artifact",
        code="retrieval_vector_invalid",
    )
    if set(value) != {
        "schema_version", "hash_rule", "partition_key_string", "artifact_kind",
        "document_id", "dimension", "source_content_hash", "coordinates",
        "content_hash",
    } or value.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise CorpusRetrievalError("vector artifact schema differs")
    if value.get("partition_key_string") != key.key_string():
        raise CorpusRetrievalError("vector artifact partition differs")
    if value.get("dimension") != key.dimension:
        raise CorpusRetrievalError("vector artifact dimension differs")
    if value.get("artifact_kind") != expected_kind:
        raise CorpusRetrievalError("vector artifact kind differs")
    artifact = create_vector_artifact(
        key,
        document_id=value.get("document_id"),
        source_content_hash=value.get("source_content_hash"),
        coordinates=value.get("coordinates"),
        artifact_kind=value.get("artifact_kind", ARTIFACT_KIND_DOCUMENT),
        hash_rule=value.get("hash_rule", DEFAULT_HASH_RULE),
    )
    if artifact.content_hash != value.get("content_hash"):
        raise CorpusRetrievalError("vector artifact content hash differs")
    if artifact.content_hash != entry["artifact_content_hash"]:
        raise CorpusRetrievalError("projection vector binding differs")
    if artifact.document_id != entry["document_id"]:
        raise CorpusRetrievalError("projection vector document binding differs")
    if artifact.source_content_hash != entry["source_content_hash"]:
        raise CorpusRetrievalError("projection vector source binding differs")
    return artifact


def _verify_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = verify_sealed(
        value, label="retrieval projection", code="retrieval_projection_invalid",
    )
    expected = {
        "schema_version", "projection_id", "corpus_generation_id",
        "corpus_generation_hash", "partition_key", "corpus_provenance",
        "vector_count", "vectors", "creates_warrant",
        "content_hash",
    }
    if set(manifest) != expected:
        raise CorpusRetrievalError("retrieval projection fields differ")
    if manifest["schema_version"] != PROJECTION_SCHEMA_VERSION:
        raise CorpusRetrievalError("retrieval projection schema differs")
    if manifest["creates_warrant"] is not False:
        raise CorpusRetrievalError("retrieval projection cannot create warrant")
    key = manifest["partition_key"]
    try:
        PartitionKey(
            provider=key["provider"], model_identifier=key["model_identifier"],
            dimension=key["dimension"], normalization=key["normalization"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CorpusRetrievalError("retrieval partition key differs") from error
    vectors = manifest["vectors"]
    if not isinstance(vectors, list) or manifest["vector_count"] != len(vectors):
        raise CorpusRetrievalError("retrieval projection vector count differs")
    ids = [item.get("document_id") for item in vectors if isinstance(item, Mapping)]
    if len(ids) != len(vectors) or ids != sorted(set(ids)):
        raise CorpusRetrievalError("projection vector identifiers differ")
    for index, entry in enumerate(vectors):
        if set(entry) != {
            "document_id", "source_content_hash", "artifact_content_hash",
            "artifact_object_hash", "corpus_provenance",
        }:
            raise CorpusRetrievalError(f"projection vector {index} fields differ")
        if entry["corpus_provenance"] != manifest["corpus_provenance"]:
            raise CorpusRetrievalError("projection vector provenance differs")
    if manifest["projection_id"] != _projection_id(manifest):
        raise CorpusRetrievalError("retrieval projection identity differs")
    return manifest


def _write_manifest(root: Path, manifest: Mapping[str, Any]) -> None:
    path = _projection_path(root, str(manifest["projection_id"]))
    rendered = canonical_bytes(manifest) + b"\n"
    if path.exists():
        if path.read_bytes() != rendered:
            raise CorpusRetrievalError("retrieval projection overwrite refused")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(rendered)
    temporary.replace(path)


def _prior_vectors(root: Path, key: PartitionKey) -> dict[tuple[str, str], dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    directory = _projection_dir(root)
    if not directory.exists():
        return found
    for path in sorted(directory.glob("retrievalgen.*.json")):
        value = _verify_manifest(strict_canonical_object(
            path.read_bytes(), maximum=16_777_216,
            label="retrieval projection", code="retrieval_projection_invalid",
        ))
        try:
            generation = require_active_generation(root, value["corpus_generation_id"])
        except Exception:
            continue
        if generation["content_hash"] != value["corpus_generation_hash"]:
            continue
        if value["partition_key"] != key.payload():
            continue
        for entry in value["vectors"]:
            found[(entry["document_id"], entry["source_content_hash"])] = dict(entry)
    return found


def build_projection(
    root: Path, *, generation_id: str, key: PartitionKey,
    gateway: EmbeddingGateway, processor_id: str, max_input_tokens: int,
    timeout_milliseconds: int, recorded_at: str,
) -> Projection:
    """Embed only generation deltas and publish an immutable projection."""

    generation = require_active_generation(root, generation_id)
    prior = _prior_vectors(root, key)
    entries: list[dict[str, Any]] = []
    vectors: dict[str, VectorArtifact] = {}
    provider_calls = 0
    produced_provenance = gateway_corpus_provenance(gateway)
    for document in generation["entries"]:
        if not document["full_text_stored"] or document["spans_sha256"] is None:
            continue
        rights = document["embedding"]
        decision = next((
            record["payload"]["decision"]
            for record in reversed(read_ledger(root, "rights"))
            if record["kind"] == "rights_derived"
            and record["payload"]["decision"]["document_id"] == document["document_id"]
        ), None)
        processor = None if decision is None else decision["uses"]["embedding"]["processor"]
        if (
            rights["value"] != "allowed"
            or rights["processor_id"] != processor_id
            or processor is None
            or processor["processor_id"] != processor_id
            or processor["provider"] != key.provider
            or processor["model_identifier"] != key.model_identifier
        ):
            raise CorpusRetrievalError(
                f"embedding rights for {document['document_id']} do not authorize "
                "the exact processor/provider/model partition"
            )
        writer = PolicyDerivedRightsWriter(
            root, actor_id=decision["authored_by"]["actor_id"],
            valid_from=recorded_at, valid_until=None,
        )
        shard = writer.locate(document["source_id"])
        if shard is None:
            raise CorpusRetrievalError("no current Phase 4A rights record exists")
        try:
            with Phase4Workspace(writer.shard_root(shard)) as workspace:
                Phase4Service(workspace).require_rights(
                    document["source_id"], RightsUse.EMBEDDING,
                    at=recorded_at, processor_id=processor_id,
                    provider=key.provider, model_identifier=key.model_identifier,
                )
        except RightsBlocked as error:
            raise CorpusRetrievalError("current embedding rights refuse disclosure") from error
        reuse = prior.get((document["document_id"], document["source_sha256"]))
        if reuse is not None:
            artifact = _vector_from_object(
                root, key, reuse, expected_kind=ARTIFACT_KIND_DOCUMENT,
            )
            entry = reuse
        else:
            body = read_object(root, document["source_sha256"])
            try:
                text = body.decode("utf-8", "strict")
            except UnicodeDecodeError as error:
                raise CorpusRetrievalError("stored source is not strict UTF-8") from error
            result = gateway.embed(EmbeddingRequest(
                document_id=document["document_id"],
                source_id=document["source_id"],
                source_content_hash=document["source_sha256"],
                text=text,
                processor_id=processor_id,
                max_input_tokens=max_input_tokens,
                timeout_milliseconds=timeout_milliseconds,
            ))
            provider_calls += 1
            if result.provider != key.provider or result.model_identifier != key.model_identifier:
                raise CorpusRetrievalError("embedding result partition differs")
            quantized = quantize(
                result.provider_coordinates, normalization=key.normalization,
            )
            artifact = create_vector_artifact(
                key, document_id=document["document_id"],
                source_content_hash=document["source_sha256"],
                coordinates=quantized.coordinates,
            )
            artifact_hash = write_object(
                root, canonical_bytes(artifact_payload(key, artifact)),
            )
            entry = {
                "document_id": document["document_id"],
                "source_content_hash": document["source_sha256"],
                "artifact_content_hash": artifact.content_hash,
                "artifact_object_hash": artifact_hash,
                "corpus_provenance": produced_provenance,
            }
        entries.append(dict(entry))
        vectors[artifact.document_id] = artifact
    if not entries:
        raise CorpusRetrievalError("generation has no embedding-authorized full text")
    provenances = {entry["corpus_provenance"] for entry in entries}
    if len(provenances) != 1:
        raise CorpusRetrievalError("a projection cannot mix vector provenance")
    body: dict[str, Any] = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "projection_id": None,
        "corpus_generation_id": generation_id,
        "corpus_generation_hash": generation["content_hash"],
        "partition_key": key.payload(),
        "corpus_provenance": next(iter(provenances)),
        "vector_count": len(entries),
        "vectors": sorted(entries, key=lambda item: item["document_id"]),
        "creates_warrant": False,
        "content_hash": None,
    }
    body["projection_id"] = _projection_id(body)
    manifest = _verify_manifest(sealed(body))
    _write_manifest(root, manifest)
    return Projection(manifest=manifest, vectors=vectors, provider_calls=provider_calls)


def load_projection(root: Path, projection_id: str) -> Projection:
    manifest = _verify_manifest(strict_canonical_object(
        _projection_path(root, projection_id).read_bytes(),
        maximum=16_777_216, label="retrieval projection",
        code="retrieval_projection_invalid",
    ))
    generation = require_active_generation(root, manifest["corpus_generation_id"])
    if generation["content_hash"] != manifest["corpus_generation_hash"]:
        raise CorpusRetrievalError("projection corpus generation hash differs")
    key_payload = manifest["partition_key"]
    key = PartitionKey(
        provider=key_payload["provider"],
        model_identifier=key_payload["model_identifier"],
        dimension=key_payload["dimension"],
        normalization=key_payload["normalization"],
    )
    current = {
        entry["document_id"]: entry["source_sha256"]
        for entry in generation["entries"]
    }
    for entry in manifest["vectors"]:
        if current.get(entry["document_id"]) != entry["source_content_hash"]:
            raise CorpusRetrievalError("projection vector is not bound to the generation")
    return Projection(
        manifest=manifest,
        vectors={
            entry["document_id"]: _vector_from_object(
                root, key, entry, expected_kind=ARTIFACT_KIND_DOCUMENT,
            )
            for entry in manifest["vectors"]
        },
    )


def embed_query(
    root: Path, *, projection_id: str, query: str, gateway: EmbeddingGateway,
    processor_id: str, max_input_tokens: int, timeout_milliseconds: int,
) -> dict[str, Any]:
    """Persist one partition-bound query vector before the replay-only read path."""

    if not isinstance(query, str) or not query.strip():
        raise CorpusRetrievalError("query must be non-empty")
    projection = load_projection(root, projection_id)
    key = projection.key
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
        "schema_version": "adaivy.corpus-retrieval-query.v1",
        "query_embedding_id": "queryembedding." + sha256_bytes(canonical_bytes({
            "projection_id": projection_id,
            "partition_key": key.payload(),
            "query_hash": query_hash,
            "artifact_content_hash": artifact.content_hash,
        })).removeprefix("sha256:")[:24],
        "projection_id": projection_id,
        "projection_hash": projection.manifest["content_hash"],
        "partition_key": key.payload(),
        "query_hash": query_hash,
        "query_object_hash": query_object_hash,
        "artifact_content_hash": artifact.content_hash,
        "artifact_object_hash": artifact_object_hash,
        "ranking_policy": "exact_cosine_desc_then_document_id_asc_v1",
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


def _load_query(root: Path, query_embedding_id: str) -> tuple[dict[str, Any], VectorArtifact, str]:
    if _QUERY_EMBEDDING_ID.fullmatch(query_embedding_id) is None:
        raise CorpusRetrievalError("invalid query embedding identifier")
    manifest = verify_sealed(
        strict_canonical_object(
            _query_dir(root).joinpath(query_embedding_id + ".json").read_bytes(),
            maximum=1_048_576, label="query embedding",
            code="retrieval_query_invalid",
        ),
        label="query embedding", code="retrieval_query_invalid",
    )
    if set(manifest) != {
        "schema_version", "query_embedding_id", "projection_id",
        "projection_hash", "partition_key", "query_hash", "query_object_hash",
        "artifact_content_hash", "artifact_object_hash", "ranking_policy",
        "creates_warrant", "content_hash",
    } or manifest["schema_version"] != "adaivy.corpus-retrieval-query.v1":
        raise CorpusRetrievalError("query embedding fields differ")
    expected_id = "queryembedding." + sha256_bytes(canonical_bytes({
        "projection_id": manifest["projection_id"],
        "partition_key": manifest["partition_key"],
        "query_hash": manifest["query_hash"],
        "artifact_content_hash": manifest["artifact_content_hash"],
    })).removeprefix("sha256:")[:24]
    if manifest["query_embedding_id"] != query_embedding_id or expected_id != query_embedding_id:
        raise CorpusRetrievalError("query embedding identity differs")
    projection = load_projection(root, manifest["projection_id"])
    if projection.manifest["content_hash"] != manifest["projection_hash"]:
        raise CorpusRetrievalError("query projection binding differs")
    if manifest["partition_key"] != projection.key.payload():
        raise CorpusRetrievalError("query partition binding differs")
    entry = {
        "document_id": query_embedding_id.removeprefix("queryembedding."),
        "source_content_hash": manifest["query_hash"],
        "artifact_content_hash": manifest["artifact_content_hash"],
        "artifact_object_hash": manifest["artifact_object_hash"],
    }
    # Artifact document id is query.<hash-prefix>, not the embedding manifest id.
    artifact_value = strict_canonical_object(
        read_object(root, manifest["artifact_object_hash"]), maximum=16_777_216,
        label="query vector artifact", code="retrieval_query_invalid",
    )
    entry["document_id"] = artifact_value["document_id"]
    artifact = _vector_from_object(
        root, projection.key, entry, expected_kind=ARTIFACT_KIND_QUERY,
    )
    if artifact.artifact_kind != ARTIFACT_KIND_QUERY:
        raise CorpusRetrievalError("query artifact kind differs")
    query_bytes = read_object(root, manifest["query_object_hash"])
    if sha256_bytes(query_bytes) != manifest["query_hash"]:
        raise CorpusRetrievalError("query text hash differs")
    return manifest, artifact, query_bytes.decode("utf-8", "strict")


def _terms(text: str) -> frozenset[str]:
    return frozenset(
        "".join(character for character in token.casefold() if character.isalnum())
        for token in text.split()
        if any(character.isalnum() for character in token)
    )


def _best_span(body: bytes, spans_doc: Mapping[str, Any], query: str) -> tuple[dict[str, Any], str]:
    text = body.decode("utf-8", "strict")
    wanted = _terms(query)
    candidates: list[tuple[int, int, dict[str, Any], str]] = []
    for span in spans_doc["spans"]:
        exact = text[span["start_offset"]:span["end_offset"]]
        candidates.append((
            len(wanted & _terms(exact)), -span["span_index"], dict(span), exact,
        ))
    _, _, selected, exact = max(candidates, key=lambda item: (item[0], item[1]))
    return selected, exact


def retrieve_evidence(
    root: Path, *, query_embedding_id: str, limit: int = 5,
) -> tuple[dict[str, Any], ...]:
    """Replay a projection and return exact source passages; no gateway exists."""

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 100:
        raise CorpusRetrievalError("limit must be an integer from 1 through 100")
    query_manifest, query_artifact, query = _load_query(root, query_embedding_id)
    projection_id = query_manifest["projection_id"]
    projection = load_projection(root, projection_id)
    key = projection.key
    if query_artifact.artifact_kind != ARTIFACT_KIND_QUERY:
        raise CorpusRetrievalError("query artifact must declare artifact_kind=query")
    ranked = rank_exact_cosine(
        PartitionedVector(
            partition_key=key, document_id=query_artifact.document_id,
            coordinates=query_artifact.coordinates,
            artifact_kind=ARTIFACT_KIND_QUERY,
        ),
        tuple(
            PartitionedVector(
                partition_key=key, document_id=artifact.document_id,
                coordinates=artifact.coordinates,
                artifact_kind=ARTIFACT_KIND_DOCUMENT,
            )
            for artifact in projection.vectors.values()
        ),
    )
    generation = require_active_generation(
        root, projection.manifest["corpus_generation_id"],
    )
    documents = {entry["document_id"]: entry for entry in generation["entries"]}
    cards: list[dict[str, Any]] = []
    for rank, (document_id, cosine) in enumerate(ranked[:limit], start=1):
        document = documents[document_id]
        body = read_object(root, document["source_sha256"])
        spans_doc = verify_spans(json.loads(
            read_object(root, document["spans_sha256"]).decode("utf-8")
        ))
        verify_spans_against_source(spans_doc, body)
        span, exact = _best_span(body, spans_doc, query)
        cards.append(sealed({
            "schema_version": EVIDENCE_CARD_SCHEMA_VERSION,
            "projection_id": projection_id,
            "rank": rank,
            "document_id": document_id,
            "source_id": document["source_id"],
            "source_content_hash": document["source_sha256"],
            "span_index": span["span_index"],
            "start_offset": span["start_offset"],
            "end_offset": span["end_offset"],
            "exact_text": exact,
            "exact_text_hash": span["exact_text_hash"],
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
        "schema_version": "adaivy.corpus-retrieval-result.v1",
        "retrieval_id": "retrieval." + sha256_bytes(canonical_bytes({
            "query_embedding_id": query_embedding_id,
            "limit": limit,
            "evidence_card_hashes": [card["content_hash"] for card in cards],
        })).removeprefix("sha256:")[:24],
        "query_embedding_id": query_embedding_id,
        "projection_id": projection_id,
        "ranking_policy": query_manifest["ranking_policy"],
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
        raise CorpusRetrievalError("retrieval result overwrite refused")
    if not result_path.exists():
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_bytes(rendered)
    return tuple(cards)


__all__ = [
    "CorpusRetrievalError", "Projection", "build_projection", "embed_query",
    "load_projection", "retrieve_evidence",
]
