"""Ingestion: rights, one provider call per document, exact artifacts.

Ordering is load-bearing and is the whole content of two probes:

1. ``rights.require_rights(source_id, RightsUse.EMBEDDING, at=..., processor_id=...)``
2. only then ``corpus.read(source_id)``
3. only then ``gateway.embed(...)``

following `service.py:185`. A missing, expired, revoked or differently-addressed
decision raises before the source is opened, so no text reaches a provider.

Ingestion and retrieval never share a process. This module writes artifacts; it
reads none back except through `load_partition`, which is the replay path and has
no gateway, no credential and no network surface.

A vector is not evidence. This record creates no applicability record, no
premise, no graph admission and no warrant, and it asserts no novelty or
significance -- ``NOVELTY_LANDSCAPE.md:62-64`` is the governing reading.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..phase2.pricing import estimate_cost_microusd, pricing_snapshot_is_confirmed
from ..phase2.records import PricingSnapshot
from ..phase2.serialization import canonical_hash, canonical_json, sha256_bytes
from .constants import (
    CORPUS_PROVENANCE_PROJECT_AUTHORED,
    CORPUS_PROVENANCE_VALUES,
    FIXTURE_SYNTHETIC_PROVIDER,
    HASH_PATTERN,
    IDENTIFIER_PATTERN,
    LIVE_EMBEDDING_ACKNOWLEDGEMENT,
    OUTPUT_TOKENS_CONSTANT,
)
from .errors import (
    EmbeddingError,
    EmbeddingIngestionError,
    FixtureProviderNotIngestibleError,
    OutputTokensNotZeroError,
)
from .gateways import gateway_corpus_provenance
from .partition import (
    PartitionKey,
    VectorArtifact,
    create_vector_artifact,
    write_partition,
)
from .ports import EmbeddingGateway, RightsGate, SourceTextReader
from .quantization import quantize
from .records import EmbeddingRequest
from .rights import EMBEDDING_RIGHTS_USE
from .run_config import EmbeddingRunConfiguration

INGESTION_RECORD_SCHEMA_VERSION = "adaivy.embedding-ingestion-record.v1"

_RECORD_FIELDS = frozenset({
    "schema_version",
    "run_id",
    "recorded_at",
    "processor_id",
    "partition_key",
    "partition_key_string",
    "corpus_provenance",
    "configuration_content_hash",
    "pricing_snapshot_id",
    "pricing_confirmed",
    "manifest_hash",
    "document_count",
    "documents",
    "total_input_tokens",
    "output_tokens",
    "estimated_cost_microusd",
    "saturated_coordinate_count",
    "provider_calls",
    "creates_epistemic_warrant",
    "asserts_source_applicability",
    "creates_graph_admission",
    "novelty_status",
    "significance_status",
    "content_hash",
})
_DOCUMENT_FIELDS = frozenset({
    "document_id",
    "source_id",
    "source_content_hash",
    "artifact_content_hash",
    "input_tokens",
    "provider_request_id",
    "rights_decision_id",
})


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentRequest:
    """One document to embed: which artifact id, which Phase 4A source."""

    document_id: str
    source_id: str

    def __post_init__(self) -> None:
        if IDENTIFIER_PATTERN.fullmatch(self.document_id) is None:
            raise EmbeddingError(f"document_id is not path-safe: {self.document_id!r}",
                                 code="document_id_invalid")
        if not isinstance(self.source_id, str) or not self.source_id:
            raise EmbeddingError("source_id must be a non-empty string",
                                 code="source_id_invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddedDocument:
    document_id: str
    source_id: str
    source_content_hash: str
    artifact_content_hash: str
    input_tokens: int
    provider_request_id: str | None
    rights_decision_id: str | None

    def payload(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_id": self.source_id,
            "source_content_hash": self.source_content_hash,
            "artifact_content_hash": self.artifact_content_hash,
            "input_tokens": self.input_tokens,
            "provider_request_id": self.provider_request_id,
            "rights_decision_id": self.rights_decision_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class EmbeddingIngestionRecord:
    """Closes provider, bounds, usage, cost and vector bytes into one hash.

    There is no timestamp read anywhere: ``recorded_at`` is an argument, matching
    the report-index rule that a recorded instant is an input and never a clock
    read. Two ingestions of the same bytes with the same argument therefore
    produce byte-identical records, so no operational hash is needed.
    """

    schema_version: str
    run_id: str
    recorded_at: str
    processor_id: str
    partition_key: PartitionKey
    corpus_provenance: str
    configuration_content_hash: str
    pricing_snapshot_id: str
    pricing_confirmed: bool
    manifest_hash: str
    documents: tuple[EmbeddedDocument, ...]
    total_input_tokens: int
    estimated_cost_microusd: int
    provider_calls: int
    content_hash: str

    def payload(self) -> dict[str, Any]:
        return ingestion_record_payload(self)

    @property
    def output_tokens(self) -> int:
        return OUTPUT_TOKENS_CONSTANT


def _record_body(
    *, run_id: str, recorded_at: str, processor_id: str, key: PartitionKey,
    corpus_provenance: str, configuration_content_hash: str,
    pricing_snapshot_id: str, pricing_confirmed: bool, manifest_hash: str,
    documents: Sequence[EmbeddedDocument], total_input_tokens: int,
    estimated_cost_microusd: int, provider_calls: int,
) -> dict[str, Any]:
    return {
        "schema_version": INGESTION_RECORD_SCHEMA_VERSION,
        "run_id": run_id,
        "recorded_at": recorded_at,
        "processor_id": processor_id,
        "partition_key": key.payload(),
        "partition_key_string": key.key_string(),
        "corpus_provenance": corpus_provenance,
        "configuration_content_hash": configuration_content_hash,
        "pricing_snapshot_id": pricing_snapshot_id,
        "pricing_confirmed": pricing_confirmed,
        "manifest_hash": manifest_hash,
        "document_count": len(documents),
        "documents": [item.payload() for item in documents],
        "total_input_tokens": total_input_tokens,
        "output_tokens": OUTPUT_TOKENS_CONSTANT,
        "estimated_cost_microusd": estimated_cost_microusd,
        # Always zero in a record that exists: a saturating coordinate halts
        # ingestion, so this states the count instead of implying it.
        "saturated_coordinate_count": 0,
        "provider_calls": provider_calls,
        "creates_epistemic_warrant": False,
        "asserts_source_applicability": False,
        "creates_graph_admission": False,
        "novelty_status": "not_assessed",
        "significance_status": "not_assessed",
        "content_hash": None,
    }


def ingestion_record_payload(record: EmbeddingIngestionRecord) -> dict[str, Any]:
    body = _record_body(
        run_id=record.run_id, recorded_at=record.recorded_at,
        processor_id=record.processor_id, key=record.partition_key,
        corpus_provenance=record.corpus_provenance,
        configuration_content_hash=record.configuration_content_hash,
        pricing_snapshot_id=record.pricing_snapshot_id,
        pricing_confirmed=record.pricing_confirmed,
        manifest_hash=record.manifest_hash, documents=record.documents,
        total_input_tokens=record.total_input_tokens,
        estimated_cost_microusd=record.estimated_cost_microusd,
        provider_calls=record.provider_calls,
    )
    body["content_hash"] = record.content_hash
    return body


def load_ingestion_record(payload: Mapping[str, Any]) -> EmbeddingIngestionRecord:
    """Exact field-set validation. Nonzero output tokens is a refusal."""

    if not isinstance(payload, Mapping):
        raise EmbeddingIngestionError("ingestion record must be an object")
    if set(payload) != set(_RECORD_FIELDS):
        raise EmbeddingIngestionError(
            "ingestion record fields differ from schema: expected "
            f"{sorted(_RECORD_FIELDS)}, got {sorted(payload)}"
        )
    if payload["schema_version"] != INGESTION_RECORD_SCHEMA_VERSION:
        raise EmbeddingIngestionError("unsupported ingestion record schema_version")
    output_tokens = payload["output_tokens"]
    if not isinstance(output_tokens, int) or isinstance(output_tokens, bool):
        raise EmbeddingIngestionError("output_tokens must be an integer")
    if output_tokens != OUTPUT_TOKENS_CONSTANT:
        raise OutputTokensNotZeroError(
            "an embeddings run produces no output tokens; an ingestion record "
            f"claiming {output_tokens!r} is refused"
        )
    for name in ("creates_epistemic_warrant", "asserts_source_applicability",
                 "creates_graph_admission"):
        if payload[name] is not False:
            raise EmbeddingIngestionError(
                f"{name} must be False: a vector is not evidence"
            )
    for name in ("novelty_status", "significance_status"):
        if payload[name] != "not_assessed":
            raise EmbeddingIngestionError(f"{name} must be not_assessed")
    if payload["saturated_coordinate_count"] != 0:
        raise EmbeddingIngestionError(
            "a saturating coordinate halts ingestion, so a record cannot report one"
        )
    if payload["corpus_provenance"] not in CORPUS_PROVENANCE_VALUES:
        raise EmbeddingIngestionError("unknown corpus_provenance")
    key = PartitionKey(
        provider=str(payload["partition_key"]["provider"]),
        model_identifier=str(payload["partition_key"]["model_identifier"]),
        dimension=int(payload["partition_key"]["dimension"]),
        normalization=str(payload["partition_key"]["normalization"]),
    )
    if key.is_fixture_synthetic:
        raise FixtureProviderNotIngestibleError(
            "no ingestion record may name the fixture_synthetic provider"
        )
    if payload["partition_key_string"] != key.key_string():
        raise EmbeddingIngestionError("partition_key_string does not match partition_key")
    documents: list[EmbeddedDocument] = []
    previous = ""
    entries = payload["documents"]
    if not isinstance(entries, list) or len(entries) != payload["document_count"]:
        raise EmbeddingIngestionError("documents must be an array matching document_count")
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict) or set(entry) != set(_DOCUMENT_FIELDS):
            raise EmbeddingIngestionError(f"documents[{position}] fields differ from schema")
        document_id = str(entry["document_id"])
        if document_id <= previous:
            raise EmbeddingIngestionError("documents must be sorted by document_id")
        previous = document_id
        for name in ("source_content_hash", "artifact_content_hash"):
            if HASH_PATTERN.fullmatch(str(entry[name])) is None:
                raise EmbeddingIngestionError(f"documents[{position}].{name} is not a hash")
        documents.append(EmbeddedDocument(
            document_id=document_id,
            source_id=str(entry["source_id"]),
            source_content_hash=str(entry["source_content_hash"]),
            artifact_content_hash=str(entry["artifact_content_hash"]),
            input_tokens=int(entry["input_tokens"]),
            provider_request_id=(
                None if entry["provider_request_id"] is None
                else str(entry["provider_request_id"])
            ),
            rights_decision_id=(
                None if entry["rights_decision_id"] is None
                else str(entry["rights_decision_id"])
            ),
        ))
    recorded_hash = payload["content_hash"]
    if HASH_PATTERN.fullmatch(str(recorded_hash)) is None:
        raise EmbeddingIngestionError("content_hash is invalid")
    rehashed = dict(payload)
    rehashed["content_hash"] = None
    if canonical_hash(rehashed) != recorded_hash:
        raise EmbeddingIngestionError("ingestion record content_hash mismatch")
    return EmbeddingIngestionRecord(
        schema_version=str(payload["schema_version"]),
        run_id=str(payload["run_id"]),
        recorded_at=str(payload["recorded_at"]),
        processor_id=str(payload["processor_id"]),
        partition_key=key,
        corpus_provenance=str(payload["corpus_provenance"]),
        configuration_content_hash=str(payload["configuration_content_hash"]),
        pricing_snapshot_id=str(payload["pricing_snapshot_id"]),
        pricing_confirmed=bool(payload["pricing_confirmed"]),
        manifest_hash=str(payload["manifest_hash"]),
        documents=tuple(documents),
        total_input_tokens=int(payload["total_input_tokens"]),
        estimated_cost_microusd=int(payload["estimated_cost_microusd"]),
        provider_calls=int(payload["provider_calls"]),
        content_hash=str(recorded_hash),
    )


def read_ingestion_record(path: Path) -> EmbeddingIngestionRecord:
    return load_ingestion_record(json.loads(path.read_text(encoding="utf-8")))


def write_ingestion_record(record: EmbeddingIngestionRecord, path: Path) -> None:
    rendered = canonical_json(ingestion_record_payload(record)) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise EmbeddingIngestionError("ingestion_record_overwrite_refused")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def _rights_decision_id(evaluation: Any) -> str | None:
    value = getattr(evaluation, "decision_id", None)
    return value if isinstance(value, str) else None


def ingest_partition(
    *,
    root: Path,
    configuration: EmbeddingRunConfiguration,
    pricing: PricingSnapshot,
    gateway: EmbeddingGateway,
    rights: RightsGate,
    corpus: SourceTextReader,
    documents: Sequence[DocumentRequest],
    run_id: str,
    recorded_at: str,
    execute: bool = False,
    acknowledgement: str | None = None,
    require_confirmed_pricing: bool = True,
) -> EmbeddingIngestionRecord:
    """Embed each document once and write the partition. Fails closed everywhere."""

    if not execute:
        raise EmbeddingIngestionError(
            "live ingestion requires execute=True; a provider seeing the text is "
            "irreversible"
        )
    if acknowledgement != LIVE_EMBEDDING_ACKNOWLEDGEMENT:
        raise EmbeddingIngestionError(
            f"live ingestion requires the exact acknowledgement "
            f"{LIVE_EMBEDDING_ACKNOWLEDGEMENT}"
        )
    if configuration.provider == FIXTURE_SYNTHETIC_PROVIDER:
        raise FixtureProviderNotIngestibleError(
            "fixture_synthetic is authored offline and can never be ingested"
        )
    key = PartitionKey(
        provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        dimension=configuration.dimension,
        normalization=configuration.normalization,
    )
    if pricing.provider != configuration.provider:
        raise EmbeddingIngestionError("pricing snapshot names a different provider")
    if pricing.output_microusd_per_million_tokens != 0:
        raise EmbeddingIngestionError(
            "an embedding pricing snapshot must declare a zero output rate; "
            "embedding models are input-token-only"
        )
    confirmed = pricing_snapshot_is_confirmed(pricing)
    if require_confirmed_pricing and not confirmed:
        raise EmbeddingIngestionError("pricing snapshot is UNCONFIRMED")
    if not documents:
        raise EmbeddingIngestionError("no documents to embed")
    ordered = sorted(documents, key=lambda item: item.document_id)
    identifiers = [item.document_id for item in ordered]
    if len(set(identifiers)) != len(identifiers):
        raise EmbeddingIngestionError("duplicate document_id in the ingestion request")
    if len(ordered) > configuration.budget.max_calls:
        raise EmbeddingIngestionError(
            f"{len(ordered)} documents exceeds max_calls "
            f"{configuration.budget.max_calls}"
        )

    artifacts: list[VectorArtifact] = []
    embedded: list[EmbeddedDocument] = []
    total_input_tokens = 0
    provider_calls = 0
    for request_spec in ordered:
        # 1. Rights, naming the processor, BEFORE the source is opened.
        evaluation = rights.require_rights(
            request_spec.source_id, EMBEDDING_RIGHTS_USE,
            at=recorded_at, processor_id=configuration.processor_id,
        )
        # 2. Only now is the text read.
        data = corpus.read(request_spec.source_id)
        source_content_hash = sha256_bytes(data)
        text = data.decode("utf-8", "strict")
        # 3. Only now does the provider see it.
        embed_request = EmbeddingRequest(
            document_id=request_spec.document_id,
            source_id=request_spec.source_id,
            source_content_hash=source_content_hash,
            text=text,
            processor_id=configuration.processor_id,
            max_input_tokens=configuration.per_call_input_token_reserve,
            timeout_milliseconds=configuration.call_timeout_milliseconds,
        )
        result = gateway.embed(embed_request)
        provider_calls += 1
        if result.output_tokens != OUTPUT_TOKENS_CONSTANT:
            raise OutputTokensNotZeroError(
                f"{request_spec.document_id}: provider reported "
                f"{result.output_tokens} output tokens"
            )
        if result.provider != configuration.provider:
            raise EmbeddingIngestionError(
                f"{request_spec.document_id}: gateway answered as provider "
                f"{result.provider!r}"
            )
        if result.model_identifier != configuration.model_identifier:
            raise EmbeddingIngestionError(
                f"{request_spec.document_id}: gateway answered with model "
                f"{result.model_identifier!r}, partition declares "
                f"{configuration.model_identifier!r}"
            )
        if result.dimension != configuration.dimension:
            raise EmbeddingIngestionError(
                f"{request_spec.document_id}: provider dimension "
                f"{result.dimension} differs from the partition key"
            )
        if result.input_tokens > configuration.per_call_input_token_reserve:
            raise EmbeddingIngestionError(
                f"{request_spec.document_id}: {result.input_tokens} input tokens "
                f"exceeds the per-call reserve "
                f"{configuration.per_call_input_token_reserve}"
            )
        total_input_tokens += result.input_tokens
        if total_input_tokens > configuration.budget.max_input_tokens:
            raise EmbeddingIngestionError(
                f"input-token budget exhausted at {request_spec.document_id}"
            )
        running_cost = estimate_cost_microusd(
            pricing, input_tokens=total_input_tokens,
            output_tokens=OUTPUT_TOKENS_CONSTANT,
        )
        if running_cost > configuration.budget.max_cost_microusd:
            raise EmbeddingIngestionError(
                f"cost budget exhausted at {request_spec.document_id}"
            )
        # 4. Quantize ONCE. A saturating coordinate halts the whole run.
        quantized = quantize(
            result.provider_coordinates, normalization=configuration.normalization,
        )
        artifact = create_vector_artifact(
            key, document_id=request_spec.document_id,
            source_content_hash=source_content_hash,
            coordinates=quantized.coordinates,
        )
        artifacts.append(artifact)
        embedded.append(EmbeddedDocument(
            document_id=request_spec.document_id,
            source_id=request_spec.source_id,
            source_content_hash=source_content_hash,
            artifact_content_hash=artifact.content_hash,
            input_tokens=result.input_tokens,
            provider_request_id=result.provider_request_id,
            rights_decision_id=_rights_decision_id(evaluation),
        ))

    provenance = gateway_corpus_provenance(gateway)
    if provenance not in CORPUS_PROVENANCE_VALUES:  # pragma: no cover - defensive
        provenance = CORPUS_PROVENANCE_PROJECT_AUTHORED
    partition = write_partition(root, key, artifacts, corpus_provenance=provenance)
    estimated_cost = estimate_cost_microusd(
        pricing, input_tokens=total_input_tokens, output_tokens=OUTPUT_TOKENS_CONSTANT,
    )
    body = _record_body(
        run_id=run_id, recorded_at=recorded_at,
        processor_id=configuration.processor_id, key=key,
        corpus_provenance=provenance,
        configuration_content_hash=configuration.content_hash,
        pricing_snapshot_id=pricing.snapshot_id.value,
        pricing_confirmed=confirmed,
        manifest_hash=partition.manifest_hash, documents=embedded,
        total_input_tokens=total_input_tokens,
        estimated_cost_microusd=estimated_cost, provider_calls=provider_calls,
    )
    body["content_hash"] = canonical_hash(body)
    return load_ingestion_record(body)


def plan_ingestion(
    *,
    configuration: EmbeddingRunConfiguration,
    pricing: PricingSnapshot,
    documents: Sequence[DocumentRequest],
) -> dict[str, Any]:
    """Offline dry run. Names what WOULD be disclosed and calls nothing."""

    ordered = sorted(documents, key=lambda item: item.document_id)
    key = PartitionKey(
        provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        dimension=configuration.dimension,
        normalization=configuration.normalization,
    )
    return {
        "schema_version": "adaivy.embedding-ingestion-plan.v1",
        "execution_status": "not_executed",
        "provider_calls": 0,
        "network_requests": 0,
        "partition_key_string": key.key_string(),
        "processor_id": configuration.processor_id,
        "configuration_content_hash": configuration.content_hash,
        "pricing_snapshot_id": pricing.snapshot_id.value,
        "pricing_confirmed": pricing_snapshot_is_confirmed(pricing),
        "output_tokens": OUTPUT_TOKENS_CONSTANT,
        "document_ids": [item.document_id for item in ordered],
        "source_ids": sorted({item.source_id for item in ordered}),
        "required_acknowledgement": LIVE_EMBEDDING_ACKNOWLEDGEMENT,
        "creates_epistemic_warrant": False,
    }


__all__ = [
    "INGESTION_RECORD_SCHEMA_VERSION",
    "DocumentRequest",
    "EmbeddedDocument",
    "EmbeddingIngestionRecord",
    "ingest_partition",
    "ingestion_record_payload",
    "load_ingestion_record",
    "plan_ingestion",
    "read_ingestion_record",
    "write_ingestion_record",
]
