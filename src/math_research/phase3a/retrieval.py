"""Deterministic FTS5/BM25 retrieval, evidence packs, and citations."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass

from ..domain.entities import OpaqueId
from . import PACK_POLICY_VERSION, RETRIEVAL_VERSION
from .records import (
    Disposition,
    EvidenceOrigin,
    EvidencePackManifest,
    EvidenceUnit,
    EvidenceUnitType,
    ExcludedPackItem,
    ResearchMemoryRecord,
    RetrievalHit,
    RetrievalQueryRecord,
    SourceArtifact,
    SourceReference,
    SourceSpan,
)
from .serialization import ZERO_HASH, canonical_bytes, canonical_hash, finalize_content_hash, freeze_json, public_value, stable_id, thaw_json
from .workspace import ResearchMemoryWorkspace

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


class CitationValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query: RetrievalQueryRecord
    hits: tuple[RetrievalHit, ...]
    result_hash: str


@dataclass(frozen=True, slots=True)
class PackResult:
    manifest: EvidencePackManifest
    serialized_bytes: bytes


def canonical_query_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    if not normalized or len(normalized.encode("utf-8")) > 4096:
        raise ValueError("retrieval query is empty or exceeds the byte limit")
    return normalized


def fts_expression(value: str) -> str:
    tokens = [token.casefold() for token in _TOKEN.findall(canonical_query_text(value))]
    if not tokens:
        raise ValueError("retrieval query has no supported lexical tokens")
    return " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)


class DeterministicRetriever:
    def __init__(self, workspace: ResearchMemoryWorkspace) -> None:
        self.workspace = workspace

    def search(
        self,
        query_text: str,
        *,
        corpus_manifest_hash: str,
        limit: int,
        aggregate_id: OpaqueId,
        actor_id: OpaqueId,
        created_at: str,
    ) -> RetrievalResult:
        canonical_query = canonical_query_text(query_text)
        query_hash = canonical_hash({"query": canonical_query})
        query_id = stable_id(
            "retrieval-query", {"query_hash": query_hash, "corpus_manifest_hash": corpus_manifest_hash, "limit": limit}
        )
        query = RetrievalQueryRecord(
            id=query_id, canonical_query=canonical_query, query_hash=query_hash,
            corpus_manifest_hash=corpus_manifest_hash, retrieval_method="sqlite_fts5_bm25",
            retrieval_version=RETRIEVAL_VERSION, engine_version=str(self.workspace.engine_identity["sqlite_version"]),
            tokenizer_configuration=str(self.workspace.engine_identity["tokenizer"]), field_weights=(2.0, 1.0, 0.5),
            filters=freeze_json({"quarantine": "exclude", "rights": "local_retrieval"}),  # type: ignore[arg-type]
            requested_limit=limit, created_at=created_at, created_by=actor_id,
        )
        rows = self.workspace.fts_search(fts_expression(canonical_query), limit=limit)
        hits: list[RetrievalHit] = []
        for rank, row in enumerate(rows, start=1):
            unit = self.workspace.get_record(OpaqueId(str(row["evidence_unit_id"])))
            assert isinstance(unit, EvidenceUnit)
            score = float(row["raw_score"])
            if not math.isfinite(score):
                raise ValueError("FTS emitted non-finite BM25 score")
            span = self.workspace.get_record(unit.source_span_ids[0])
            assert isinstance(span, SourceSpan)
            tie_key = f"{row['source_artifact_id']}:{span.normalized_start:020d}:{unit.id.value}"
            hit = RetrievalHit(
                id=stable_id("retrieval-hit", {"query": query.id.value, "unit": unit.id.value, "rank": rank}),
                query_id=query.id, rank=rank, evidence_unit_id=unit.id,
                source_artifact_id=OpaqueId(str(row["source_artifact_id"])), source_span_ids=unit.source_span_ids,
                raw_score=score, canonical_score=format(score, ".17g"), tie_break_key=tie_key,
            )
            hits.append(hit)
        result_hash = canonical_hash({"query": query, "hits": hits})
        records: tuple[ResearchMemoryRecord, ...] = (query, *hits)
        request_hash = canonical_hash({"operation": "retrieval", "query": query})
        self.workspace.commit_records(
            records, aggregate_id=aggregate_id, command_id=stable_id("command", request_hash), kind="retrieval",
            idempotency_key=f"retrieval:{query.id.value}", request_hash=request_hash, now=created_at,
            deadline_at="9999-12-31T23:59:59Z",
        )
        return RetrievalResult(query, tuple(hits), result_hash)


class DeterministicEvidencePackBuilder:
    def __init__(self, workspace: ResearchMemoryWorkspace) -> None:
        self.workspace = workspace

    def build(
        self,
        result: RetrievalResult,
        *,
        byte_budget: int,
        per_source_cap: int,
        aggregate_id: OpaqueId,
        actor_id: OpaqueId,
        created_at: str,
    ) -> PackResult:
        if byte_budget <= 0 or per_source_cap <= 0:
            raise ValueError("pack budgets must be positive")
        included_units: list[OpaqueId] = []
        included_artifacts: list[OpaqueId] = []
        included_spans: list[OpaqueId] = []
        excluded: list[ExcludedPackItem] = []
        source_counts: dict[OpaqueId, int] = {}
        seen_spans: set[tuple[str, int, int]] = set()
        excerpts: list[dict[str, object]] = []

        def serialize(items: list[dict[str, object]]) -> bytes:
            return canonical_bytes(
                {
                    "schema_version": "1.0.0", "policy_version": PACK_POLICY_VERSION,
                    "query_id": result.query.id.value, "evidence": items,
                    "model_commentary": [], "workflow_policy": "external-to-source-content",
                }
            )

        if len(serialize([])) > byte_budget:
            raise ValueError("byte budget cannot hold the empty evidence-pack envelope")
        for hit in result.hits:
            unit = self.workspace.get_record(hit.evidence_unit_id)
            artifact = self.workspace.get_record(hit.source_artifact_id)
            assert isinstance(unit, EvidenceUnit) and isinstance(artifact, SourceArtifact)
            reference = self.workspace.get_record(artifact.source_reference_id)
            assert isinstance(reference, SourceReference)
            if artifact.quarantine_state.value != "eligible_for_parsing":
                excluded.append(ExcludedPackItem(evidence_unit_id=unit.id, reason="quarantine"))
                continue
            if "evidence_pack" not in reference.license_metadata.usage_rights:
                excluded.append(ExcludedPackItem(evidence_unit_id=unit.id, reason="rights"))
                continue
            count = source_counts.get(artifact.id, 0)
            if count >= per_source_cap:
                excluded.append(ExcludedPackItem(evidence_unit_id=unit.id, reason="source_cap"))
                continue
            spans: list[SourceSpan] = []
            duplicate = False
            for span_id in unit.source_span_ids:
                span = self.workspace.get_record(span_id)
                assert isinstance(span, SourceSpan)
                key = (span.exact_text_hash, span.normalized_start, span.normalized_end)
                if key in seen_spans:
                    duplicate = True
                spans.append(span)
            if duplicate:
                excluded.append(ExcludedPackItem(evidence_unit_id=unit.id, reason="duplicate"))
                continue
            excerpt = {
                "schema_version": "1.0.0",
                "evidence_unit_id": unit.id.value,
                "source_artifact_id": artifact.id.value,
                "source_reference_id": reference.id.value,
                "source_span_ids": [span.id.value for span in spans],
                "coordinates": [
                    {"normalized_start": span.normalized_start, "normalized_end": span.normalized_end, "page_number": span.page_number}
                    for span in spans
                ],
                "unit_type": unit.unit_type.value,
                "source_text": public_value(unit)["payload"],
                "source_content_hash": artifact.artifact_hash,
            }
            trial = excerpts + [excerpt]
            trial_size = len(serialize(trial))
            if trial_size > byte_budget:
                excluded.append(ExcludedPackItem(evidence_unit_id=unit.id, reason="byte_budget"))
                continue
            excerpts = trial
            included_units.append(unit.id)
            if artifact.id not in included_artifacts:
                included_artifacts.append(artifact.id)
            for span in spans:
                if span.id not in included_spans:
                    included_spans.append(span.id)
                seen_spans.add((span.exact_text_hash, span.normalized_start, span.normalized_end))
            source_counts[artifact.id] = count + 1
        serialized = serialize(excerpts)
        artifact_ref = self.workspace.artifacts.put(serialized, media_type="application/vnd.adaivy.evidence-pack+json")
        manifest_seed = {
            "query_id": result.query.id.value, "retrieval_result_hash": result.result_hash,
            "policy_version": PACK_POLICY_VERSION, "byte_budget": byte_budget,
            "per_source_cap": per_source_cap, "included": [value.value for value in included_units],
            "excluded": [{"id": item.evidence_unit_id.value, "reason": item.reason} for item in excluded],
        }
        manifest = EvidencePackManifest(
            id=stable_id("evidence-pack", manifest_seed), query_id=result.query.id,
            retrieval_result_hash=result.result_hash, policy_version=PACK_POLICY_VERSION,
            byte_budget=byte_budget, token_budget=None, token_counter_id=None,
            included_evidence_unit_ids=tuple(included_units), included_source_artifact_ids=tuple(included_artifacts),
            included_source_span_ids=tuple(included_spans), excluded_items=tuple(excluded),
            source_diversity_policy=freeze_json({"per_source_cap": per_source_cap, "application_order": "before_budget_fill"}),  # type: ignore[arg-type]
            injection_annotations=(), serialized_pack_artifact_hash=artifact_ref.content_hash,
            content_hash=ZERO_HASH, created_at=created_at, created_by=actor_id,
        )
        manifest = finalize_content_hash(manifest)  # type: ignore[assignment]
        request_hash = canonical_hash({"operation": "evidence_pack", "manifest": manifest})
        self.workspace.commit_records(
            (manifest,), aggregate_id=aggregate_id, command_id=stable_id("command", request_hash), kind="evidence_pack",
            idempotency_key=f"pack:{manifest.id.value}", request_hash=request_hash, now=created_at,
            deadline_at="9999-12-31T23:59:59Z",
        )
        return PackResult(manifest, serialized)


def validate_and_build_model_proposal(
    workspace: ResearchMemoryWorkspace,
    *,
    pack: EvidencePackManifest,
    statement: str,
    cited_evidence_unit_ids: tuple[OpaqueId, ...],
    declared_rationale: str,
    target_claim_id: OpaqueId,
    model_call_id: OpaqueId,
    proposal_artifact_hash: str,
    actor_id: OpaqueId,
    created_at: str,
) -> EvidenceUnit:
    allowed = set(pack.included_evidence_unit_ids)
    if not cited_evidence_unit_ids:
        raise CitationValidationError("source-dependent proposal must cite supplied evidence")
    unknown: list[str] = []
    out_of_pack: list[str] = []
    for identifier in cited_evidence_unit_ids:
        try:
            record = workspace.get_record(identifier)
        except KeyError:
            unknown.append(identifier.value)
            continue
        if not isinstance(record, EvidenceUnit):
            unknown.append(identifier.value)
        elif identifier not in allowed:
            out_of_pack.append(identifier.value)
    if unknown:
        raise CitationValidationError("unknown evidence IDs: " + ", ".join(sorted(unknown)))
    if out_of_pack:
        raise CitationValidationError("evidence IDs absent from exact pack: " + ", ".join(sorted(out_of_pack)))
    proposal = EvidenceUnit(
        id=stable_id("model-proposal", {"call": model_call_id.value, "statement": statement, "citations": cited_evidence_unit_ids}),
        unit_type=EvidenceUnitType.MODEL_PROPOSED_CLAIM, origin=EvidenceOrigin.MODEL,
        source_artifact_id=None, normalized_document_id=None, source_span_ids=(),
        model_call_id=model_call_id, proposal_artifact_hash=proposal_artifact_hash,
        payload=freeze_json(
            {"statement": statement, "cited_evidence_unit_ids": [item.value for item in cited_evidence_unit_ids],
             "declared_rationale": declared_rationale, "target_claim_id": target_claim_id.value}
        ),  # type: ignore[arg-type]
        extraction_method="scripted-value-fixture", extraction_version="1.0.0", warning_codes=(),
        disposition=Disposition.PROPOSAL, content_hash=ZERO_HASH, created_at=created_at, created_by=actor_id,
    )
    return finalize_content_hash(proposal)  # type: ignore[return-value]
