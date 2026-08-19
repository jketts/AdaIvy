"""Immutable internal records for Phase 3A research memory.

These types are deliberately separate from their canonical JSON interchange
representation and from the Phase 1 trust entities.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from ..domain.entities import OpaqueId
from . import MEMORY_SCHEMA_VERSION, PACK_POLICY_VERSION, PARSER_NAME, PARSER_VERSION, RETRIEVAL_VERSION

JsonScalar: TypeAlias = str | int | float | bool | None
FrozenJson: TypeAlias = JsonScalar | tuple["FrozenJson", ...] | tuple[tuple[str, "FrozenJson"], ...]


class StrEnum(str, Enum):
    pass


class AcquisitionStatus(StrEnum):
    METADATA_ONLY = "metadata_only"
    BYTES_AVAILABLE = "bytes_available"
    REJECTED = "rejected"


class QuarantineState(StrEnum):
    QUARANTINED = "quarantined"
    ELIGIBLE = "eligible_for_parsing"
    REJECTED = "rejected"


class Disposition(StrEnum):
    PROPOSAL = "proposal"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class EvidenceUnitType(StrEnum):
    SOURCE_PASSAGE = "source_passage"
    DEFINITION = "definition"
    THEOREM = "theorem_or_proposition"
    ASSUMPTION = "assumption"
    EQUATION = "equation"
    PROOF_STEP = "proof_step"
    EMPIRICAL_RESULT = "empirical_or_numerical_result"
    BIBLIOGRAPHIC_REFERENCE = "bibliographic_reference"
    MODEL_PROPOSED_CLAIM = "model_proposed_claim"


class EvidenceOrigin(StrEnum):
    SOURCE_EXPLICIT = "source_explicit"
    PARSER_DERIVED = "parser_derived"
    OPERATOR_CURATED = "operator_curated"
    MODEL = "model"


class RelationType(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DEFINES = "defines"
    ASSUMES = "assumes"
    DERIVES_FROM = "derives_from"
    CITES = "cites"
    EQUIVALENT_TO = "equivalent_to"
    SPECIALIZES = "specializes"
    SUPERSEDES = "supersedes"


class RelationOrigin(StrEnum):
    SOURCE_ASSERTED = "source_asserted"
    PARSER_PROPOSED = "parser_proposed"
    MODEL_PROPOSED = "model_proposed"
    OPERATOR_ASSERTED = "operator_asserted"


def _schema(value: str) -> None:
    if value != MEMORY_SCHEMA_VERSION:
        raise ValueError(f"unsupported research-memory schema version: {value}")


def _sha256(value: str | None, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"invalid sha256 value: {value!r}")
    if any(character not in "0123456789abcdef" for character in value[7:]):
        raise ValueError(f"invalid sha256 value: {value!r}")


@dataclass(frozen=True, slots=True, kw_only=True)
class LicenseMetadata:
    license_expression: str | None
    copyright_notice: str | None
    usage_rights: tuple[str, ...]
    redistribution_status: str
    evidence_uri: str | None
    reviewed_by: OpaqueId | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceReference:
    id: OpaqueId
    canonical_uri: str
    supplied_uri: str
    title: str
    authors: tuple[str, ...]
    publication_metadata: tuple[tuple[str, FrozenJson], ...]
    metadata_assertion_source: str
    metadata_status: str
    retrieved_or_recorded_at: str
    license_metadata: LicenseMetadata
    acquisition_status: AcquisitionStatus
    content_hash: str | None
    created_at: str
    created_by: OpaqueId
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        _sha256(self.content_hash, nullable=True)
        if self.acquisition_status is AcquisitionStatus.METADATA_ONLY and self.content_hash is not None:
            raise ValueError("metadata-only source must have null content_hash")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceArtifact:
    id: OpaqueId
    source_reference_id: OpaqueId
    artifact_hash: str
    byte_length: int
    declared_media_type: str
    detected_media_type: str
    acquisition_method: str
    acquired_at: str
    acquisition_adapter: str
    acquisition_adapter_version: str
    quarantine_state: QuarantineState
    quarantine_reasons: tuple[str, ...]
    content_hash: str
    created_at: str
    created_by: OpaqueId
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        _sha256(self.artifact_hash)
        _sha256(self.content_hash)
        if self.artifact_hash != self.content_hash:
            raise ValueError("source artifact content_hash must identify original bytes")
        if self.byte_length < 0:
            raise ValueError("source byte length must be non-negative")
        if self.quarantine_state is QuarantineState.ELIGIBLE and self.quarantine_reasons:
            raise ValueError("eligible source cannot retain quarantine reasons")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceVersionRelation:
    id: OpaqueId
    source_artifact_id: OpaqueId
    target_artifact_id: OpaqueId
    relation: str
    assertion_origin: str
    disposition: Disposition
    evidence_span_id: OpaqueId | None
    created_at: str
    created_by: OpaqueId
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        if self.source_artifact_id == self.target_artifact_id:
            raise ValueError("source version relation must connect distinct artifacts")


@dataclass(frozen=True, slots=True, kw_only=True)
class ParserRunRecord:
    id: OpaqueId
    source_artifact_id: OpaqueId
    parser_name: str
    parser_version: str
    parser_configuration_hash: str
    dependency_environment_hash: str
    input_hash: str
    status: str
    warning_codes: tuple[str, ...]
    declared_confidence: float | None
    stdout_artifact_hash: str
    stderr_artifact_hash: str
    output_artifact_hash: str | None
    idempotency_key: str
    created_at: str
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        if self.parser_name != PARSER_NAME or self.parser_version != PARSER_VERSION:
            raise ValueError("Phase 3A permits only plain-text-v1 1.0.0")
        for value in (
            self.parser_configuration_hash,
            self.dependency_environment_hash,
            self.input_hash,
            self.stdout_artifact_hash,
            self.stderr_artifact_hash,
        ):
            _sha256(value)
        _sha256(self.output_artifact_hash, nullable=True)
        if self.declared_confidence is not None and not math.isfinite(self.declared_confidence):
            raise ValueError("parser confidence must be finite")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractionWarning:
    code: str
    message: str
    normalized_start: int | None = None
    normalized_end: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizedDocument:
    id: OpaqueId
    source_artifact_id: OpaqueId
    parser_run_id: OpaqueId
    normalized_text_artifact_hash: str
    structure_map_artifact_hash: str
    location_map_artifact_hash: str
    unicode_normalization: str
    newline_policy: str
    coordinate_unit: str
    normalization_version: str
    warnings: tuple[ExtractionWarning, ...]
    disposition: Disposition
    content_hash: str
    created_at: str
    created_by: OpaqueId
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        for value in (
            self.normalized_text_artifact_hash,
            self.structure_map_artifact_hash,
            self.location_map_artifact_hash,
            self.content_hash,
        ):
            _sha256(value)
        if (self.unicode_normalization, self.newline_policy, self.coordinate_unit) != ("NFC", "LF", "utf8_byte"):
            raise ValueError("unsupported normalization contract")


@dataclass(frozen=True, slots=True, kw_only=True)
class OriginalLocator:
    locator_kind: str
    page_number: int | None
    region_microunits: None
    original_start: int | None
    original_end: int | None
    parser_token_start: None
    parser_token_end: None


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceSpan:
    id: OpaqueId
    source_artifact_id: OpaqueId
    normalized_document_id: OpaqueId
    normalized_start: int
    normalized_end: int
    page_number: int | None
    section_path: tuple[str, ...]
    original_locator: OriginalLocator
    exact_text_hash: str
    original_quote_hash: str | None
    content_hash: str
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        if self.normalized_start < 0 or self.normalized_end <= self.normalized_start:
            raise ValueError("source span must be a nonempty half-open interval")
        for value in (self.exact_text_hash, self.content_hash):
            _sha256(value)
        _sha256(self.original_quote_hash, nullable=True)
        if self.original_locator.locator_kind != "text_bytes":
            raise ValueError("Phase 3A permits only text-byte original locators")


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentMarker:
    id: OpaqueId
    normalized_document_id: OpaqueId
    span_id: OpaqueId
    marker_type: str
    label: str | None
    ordinal: int | None
    extraction_method: str
    disposition: Disposition
    warning_codes: tuple[str, ...]
    content_hash: str
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        _sha256(self.content_hash)


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceUnit:
    id: OpaqueId
    unit_type: EvidenceUnitType
    origin: EvidenceOrigin
    source_artifact_id: OpaqueId | None
    normalized_document_id: OpaqueId | None
    source_span_ids: tuple[OpaqueId, ...]
    model_call_id: OpaqueId | None
    proposal_artifact_hash: str | None
    payload: tuple[tuple[str, FrozenJson], ...]
    extraction_method: str
    extraction_version: str
    warning_codes: tuple[str, ...]
    disposition: Disposition
    content_hash: str
    created_at: str
    created_by: OpaqueId
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        _sha256(self.content_hash)
        _sha256(self.proposal_artifact_hash, nullable=True)
        if self.unit_type is EvidenceUnitType.MODEL_PROPOSED_CLAIM:
            if self.origin is not EvidenceOrigin.MODEL or self.disposition is not Disposition.PROPOSAL:
                raise ValueError("model claim must retain model/proposal trust boundary")
            if self.source_artifact_id is not None or self.normalized_document_id is not None or self.source_span_ids:
                raise ValueError("model claim cannot masquerade as source evidence")
            if self.model_call_id is None or self.proposal_artifact_hash is None:
                raise ValueError("model claim requires model-call and proposal artifact provenance")
        else:
            if self.origin is EvidenceOrigin.MODEL:
                raise ValueError("source-derived unit cannot use model origin")
            if self.source_artifact_id is None or self.normalized_document_id is None or not self.source_span_ids:
                raise ValueError("source-derived unit requires exact source provenance")
            if self.model_call_id is not None or self.proposal_artifact_hash is not None:
                raise ValueError("source-derived unit cannot carry model provenance")
        keys = {key for key, _ in self.payload}
        required_payload_fields = {
            EvidenceUnitType.SOURCE_PASSAGE: {"verbatim_text", "language"},
            EvidenceUnitType.DEFINITION: {"term", "definiens", "scope", "verbatim_text"},
            EvidenceUnitType.THEOREM: {"label", "statement", "hypotheses", "scope", "verbatim_text"},
            EvidenceUnitType.ASSUMPTION: {"statement", "scope", "verbatim_text"},
            EvidenceUnitType.EQUATION: {"presentation", "normalized_expression", "label", "normalization_status"},
            EvidenceUnitType.PROOF_STEP: {"statement", "local_premise_unit_ids", "step_label", "verbatim_text"},
            EvidenceUnitType.EMPIRICAL_RESULT: {"statement", "method_text", "parameters_text", "reported_uncertainty", "verbatim_text"},
            EvidenceUnitType.BIBLIOGRAPHIC_REFERENCE: {"citation_text", "identifier_candidates", "resolved_source_reference_id"},
            EvidenceUnitType.MODEL_PROPOSED_CLAIM: {"statement", "cited_evidence_unit_ids", "declared_rationale", "target_claim_id"},
        }[self.unit_type]
        if not required_payload_fields.issubset(keys):
            raise ValueError(
                f"{self.unit_type.value} payload misses {sorted(required_payload_fields - keys)}"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceRelation:
    id: OpaqueId
    source_unit_id: OpaqueId
    target_unit_id: OpaqueId
    relation_type: RelationType
    assertion_origin: RelationOrigin
    assertion_span_ids: tuple[OpaqueId, ...]
    extraction_or_actor_id: str
    disposition: Disposition
    review_record_ids: tuple[OpaqueId, ...]
    content_hash: str
    created_at: str
    created_by: OpaqueId
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        _sha256(self.content_hash)


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalQueryRecord:
    id: OpaqueId
    canonical_query: str
    query_hash: str
    corpus_manifest_hash: str
    retrieval_method: str
    retrieval_version: str
    engine_version: str
    tokenizer_configuration: str
    field_weights: tuple[float, ...]
    filters: tuple[tuple[str, FrozenJson], ...]
    requested_limit: int
    created_at: str
    created_by: OpaqueId
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        for value in (self.query_hash, self.corpus_manifest_hash):
            _sha256(value)
        if self.retrieval_method != "sqlite_fts5_bm25" or self.retrieval_version != RETRIEVAL_VERSION:
            raise ValueError("unsupported Phase 3A retrieval method")
        if self.requested_limit <= 0 or any(not math.isfinite(value) for value in self.field_weights):
            raise ValueError("invalid retrieval configuration")


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalHit:
    id: OpaqueId
    query_id: OpaqueId
    rank: int
    evidence_unit_id: OpaqueId
    source_artifact_id: OpaqueId
    source_span_ids: tuple[OpaqueId, ...]
    raw_score: float
    canonical_score: str
    tie_break_key: str
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        if self.rank <= 0 or not math.isfinite(self.raw_score):
            raise ValueError("invalid retrieval hit")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExcludedPackItem:
    evidence_unit_id: OpaqueId
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidencePackManifest:
    id: OpaqueId
    query_id: OpaqueId
    retrieval_result_hash: str
    policy_version: str
    byte_budget: int
    token_budget: int | None
    token_counter_id: str | None
    included_evidence_unit_ids: tuple[OpaqueId, ...]
    included_source_artifact_ids: tuple[OpaqueId, ...]
    included_source_span_ids: tuple[OpaqueId, ...]
    excluded_items: tuple[ExcludedPackItem, ...]
    source_diversity_policy: tuple[tuple[str, FrozenJson], ...]
    injection_annotations: tuple[OpaqueId, ...]
    serialized_pack_artifact_hash: str
    content_hash: str
    created_at: str
    created_by: OpaqueId
    schema_version: str = MEMORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _schema(self.schema_version)
        for value in (self.retrieval_result_hash, self.serialized_pack_artifact_hash, self.content_hash):
            _sha256(value)
        if self.policy_version != PACK_POLICY_VERSION or self.byte_budget <= 0:
            raise ValueError("invalid evidence-pack policy")


ResearchMemoryRecord: TypeAlias = (
    SourceReference
    | SourceArtifact
    | SourceVersionRelation
    | ParserRunRecord
    | NormalizedDocument
    | SourceSpan
    | DocumentMarker
    | EvidenceUnit
    | EvidenceRelation
    | RetrievalQueryRecord
    | RetrievalHit
    | EvidencePackManifest
)


RECORD_TYPES: dict[type[object], str] = {
    SourceReference: "source_reference",
    SourceArtifact: "source_artifact",
    SourceVersionRelation: "source_version_relation",
    ParserRunRecord: "parser_run",
    NormalizedDocument: "normalized_document",
    SourceSpan: "source_span",
    DocumentMarker: "document_marker",
    EvidenceUnit: "evidence_unit",
    EvidenceRelation: "evidence_relation",
    RetrievalQueryRecord: "retrieval_query",
    RetrievalHit: "retrieval_hit",
    EvidencePackManifest: "evidence_pack",
}


def record_type(record: ResearchMemoryRecord) -> str:
    try:
        return RECORD_TYPES[type(record)]
    except KeyError as error:
        raise TypeError(f"unsupported research-memory record: {type(record).__name__}") from error
