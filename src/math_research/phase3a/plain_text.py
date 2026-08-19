"""Deterministic internal UTF-8 plain-text parser (``plain-text-v1``)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from ..domain.entities import OpaqueId
from ..phase2.ports import ArtifactStore
from . import PARSER_NAME, PARSER_VERSION
from .records import (
    Disposition,
    DocumentMarker,
    EvidenceOrigin,
    EvidenceUnit,
    EvidenceUnitType,
    ExtractionWarning,
    NormalizedDocument,
    OriginalLocator,
    ParserRunRecord,
    SourceArtifact,
    SourceSpan,
)
from .serialization import ZERO_HASH, canonical_bytes, canonical_hash, finalize_content_hash, freeze_json, sha256_bytes, stable_id

PARSER_CONFIGURATION = {
    "coordinate_unit": "utf8_byte",
    "newline_policy": "LF",
    "unicode_normalization": "NFC",
    "marker_syntax": "[TYPE:label] payload",
    "parser_name": PARSER_NAME,
    "parser_version": PARSER_VERSION,
}
PARSER_CONFIGURATION_HASH = canonical_hash(PARSER_CONFIGURATION)
DEPENDENCY_ENVIRONMENT_HASH = canonical_hash(
    {"implementation": "python-standard-library", "unicode_database": unicodedata.unidata_version}
)

_MARKER = re.compile(r"^\[([A-Z_]+)(?::([^\]]*))?\][ \t]*(.*)$")
_INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "system prompt",
    "reveal the api key",
    "exfiltrate credentials",
)


@dataclass(frozen=True, slots=True)
class MappingSegment:
    normalized_start: int
    normalized_end: int
    original_start: int
    original_end: int
    normalized_hash: str
    original_hash: str


@dataclass(frozen=True, slots=True)
class ParseBundle:
    parser_run: ParserRunRecord
    normalized_document: NormalizedDocument | None
    spans: tuple[SourceSpan, ...]
    markers: tuple[DocumentMarker, ...]
    evidence_units: tuple[EvidenceUnit, ...]
    normalized_bytes: bytes | None
    location_map_bytes: bytes | None
    structure_map_bytes: bytes | None


def contains_prompt_injection(data: bytes) -> bool:
    try:
        text = data.decode("utf-8").casefold()
    except UnicodeDecodeError:
        return False
    return any(pattern in text for pattern in _INJECTION_PATTERNS)


def _original_characters(text: str) -> list[tuple[str, int, int]]:
    result: list[tuple[str, int, int]] = []
    offset = 0
    for character in text:
        encoded = character.encode("utf-8")
        result.append((character, offset, offset + len(encoded)))
        offset += len(encoded)
    return result


def _newline_units(characters: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    result: list[tuple[str, int, int]] = []
    index = 0
    while index < len(characters):
        character, start, end = characters[index]
        if character == "\r":
            if index + 1 < len(characters) and characters[index + 1][0] == "\n":
                end = characters[index + 1][2]
                index += 1
            result.append(("\n", start, end))
        else:
            result.append((character, start, end))
        index += 1
    return result


def _clusters(units: list[tuple[str, int, int]]) -> Iterable[list[tuple[str, int, int]]]:
    current: list[tuple[str, int, int]] = []
    for unit in units:
        character = unit[0]
        if current and unicodedata.combining(character) == 0:
            yield current
            current = []
        current.append(unit)
    if current:
        yield current


def normalize_with_mapping(original_bytes: bytes) -> tuple[str, tuple[MappingSegment, ...]]:
    original_text = original_bytes.decode("utf-8", errors="strict")
    normalized_parts: list[str] = []
    segments: list[MappingSegment] = []
    normalized_offset = 0
    for cluster in _clusters(_newline_units(_original_characters(original_text))):
        original_text_cluster = "".join(item[0] for item in cluster)
        normalized_cluster = unicodedata.normalize("NFC", original_text_cluster)
        normalized_data = normalized_cluster.encode("utf-8")
        original_start = cluster[0][1]
        original_end = cluster[-1][2]
        original_data = original_bytes[original_start:original_end]
        segments.append(
            MappingSegment(
                normalized_start=normalized_offset,
                normalized_end=normalized_offset + len(normalized_data),
                original_start=original_start,
                original_end=original_end,
                normalized_hash=sha256_bytes(normalized_data),
                original_hash=sha256_bytes(original_data),
            )
        )
        normalized_parts.append(normalized_cluster)
        normalized_offset += len(normalized_data)
    return "".join(normalized_parts), tuple(segments)


def _original_range(segments: tuple[MappingSegment, ...], start: int, end: int) -> tuple[int, int]:
    overlaps = [segment for segment in segments if segment.normalized_end > start and segment.normalized_start < end]
    if not overlaps:
        raise ValueError("normalized span has no original mapping")
    return overlaps[0].original_start, overlaps[-1].original_end


def _line_parts(text: str) -> Iterable[tuple[str, str, int, int]]:
    """Yield content, terminator, character start, character end."""
    start = 0
    for index, character in enumerate(text):
        if character in {"\n", "\f"}:
            yield text[start:index], character, start, index + 1
            start = index + 1
    if start < len(text):
        yield text[start:], "", start, len(text)


def _byte_offset(text: str, character_offset: int) -> int:
    return len(text[:character_offset].encode("utf-8"))


def _payload(unit_type: EvidenceUnitType, label: str | None, text: str) -> dict[str, object]:
    label_value = label or ""
    if unit_type is EvidenceUnitType.DEFINITION:
        return {"term": label_value, "definiens": text, "scope": "source", "verbatim_text": text}
    if unit_type is EvidenceUnitType.THEOREM:
        return {"label": label_value, "statement": text, "hypotheses": [], "scope": "source", "verbatim_text": text}
    if unit_type is EvidenceUnitType.ASSUMPTION:
        return {"statement": text, "scope": "source", "verbatim_text": text}
    if unit_type is EvidenceUnitType.EQUATION:
        return {"presentation": text, "normalized_expression": None, "label": label, "normalization_status": "not_attempted"}
    if unit_type is EvidenceUnitType.PROOF_STEP:
        return {"statement": text, "local_premise_unit_ids": [], "step_label": label, "verbatim_text": text}
    if unit_type is EvidenceUnitType.EMPIRICAL_RESULT:
        return {"statement": text, "method_text": "source report", "parameters_text": "", "reported_uncertainty": None, "verbatim_text": text}
    if unit_type is EvidenceUnitType.BIBLIOGRAPHIC_REFERENCE:
        return {"citation_text": text, "identifier_candidates": [], "resolved_source_reference_id": None}
    return {"verbatim_text": text, "language": "en", "label": label}


_UNIT_BY_MARKER = {
    "PASSAGE": EvidenceUnitType.SOURCE_PASSAGE,
    "DEFINITION": EvidenceUnitType.DEFINITION,
    "THEOREM": EvidenceUnitType.THEOREM,
    "PROPOSITION": EvidenceUnitType.THEOREM,
    "ASSUMPTION": EvidenceUnitType.ASSUMPTION,
    "EQUATION": EvidenceUnitType.EQUATION,
    "PROOF": EvidenceUnitType.PROOF_STEP,
    "RESULT": EvidenceUnitType.EMPIRICAL_RESULT,
    "REFERENCE": EvidenceUnitType.BIBLIOGRAPHIC_REFERENCE,
    "TABLE": EvidenceUnitType.SOURCE_PASSAGE,
}
_DOCUMENT_MARKER_BY_INPUT = {
    "SECTION": "section",
    "DEFINITION": "definition",
    "THEOREM": "theorem",
    "PROPOSITION": "proposition",
    "EQUATION": "equation",
    "PROOF": "proof",
    "TABLE": "table",
    "FIGURE": "figure",
    "REFERENCE": "reference",
    "FOOTNOTE": "footnote",
}


class PlainTextV1Parser:
    name = PARSER_NAME
    version = PARSER_VERSION

    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def quarantined_run(self, artifact: SourceArtifact, *, reasons: tuple[str, ...], created_at: str) -> ParseBundle:
        stdout = self.artifacts.put(b"", media_type="text/plain")
        stderr = self.artifacts.put((";".join(reasons) + "\n").encode("utf-8"), media_type="text/plain")
        run = ParserRunRecord(
            id=stable_id("parser-run", {"input": artifact.artifact_hash, "config": PARSER_CONFIGURATION_HASH}),
            source_artifact_id=artifact.id, parser_name=self.name, parser_version=self.version,
            parser_configuration_hash=PARSER_CONFIGURATION_HASH, dependency_environment_hash=DEPENDENCY_ENVIRONMENT_HASH,
            input_hash=artifact.artifact_hash, status="quarantined", warning_codes=reasons, declared_confidence=None,
            stdout_artifact_hash=stdout.content_hash, stderr_artifact_hash=stderr.content_hash,
            output_artifact_hash=None, idempotency_key=f"parse:{artifact.artifact_hash}:{PARSER_CONFIGURATION_HASH}",
            created_at=created_at,
        )
        return ParseBundle(run, None, (), (), (), None, None, None)

    def parse(self, artifact: SourceArtifact, original_bytes: bytes, *, actor_id: OpaqueId, created_at: str) -> ParseBundle:
        if artifact.detected_media_type != "text/plain" or artifact.quarantine_state.value != "eligible_for_parsing":
            return self.quarantined_run(artifact, reasons=artifact.quarantine_reasons or ("unsupported_media",), created_at=created_at)
        normalized_text, segments = normalize_with_mapping(original_bytes)
        normalized_bytes = normalized_text.encode("utf-8")
        normalized_ref = self.artifacts.put(normalized_bytes, media_type="text/plain; charset=utf-8")
        stdout = self.artifacts.put(b"plain-text-v1: parsed\n", media_type="text/plain")
        stderr = self.artifacts.put(b"", media_type="text/plain")
        run_id = stable_id("parser-run", {"input": artifact.artifact_hash, "config": PARSER_CONFIGURATION_HASH})
        document_id = stable_id("document", {"source": artifact.id.value, "parser_run": run_id.value, "text": normalized_ref.content_hash})

        spans: list[SourceSpan] = []
        markers: list[DocumentMarker] = []
        units: list[EvidenceUnit] = []
        section_path: tuple[str, ...] = ()
        page = 1
        marker_ordinal = 0

        def make_span(start: int, end: int, current_page: int, sections: tuple[str, ...]) -> SourceSpan:
            original_start, original_end = _original_range(segments, start, end)
            exact = normalized_bytes[start:end]
            original_quote = original_bytes[original_start:original_end]
            seed = {"artifact": artifact.id.value, "document": document_id.value, "start": start, "end": end}
            span = SourceSpan(
                id=stable_id("span", seed), source_artifact_id=artifact.id, normalized_document_id=document_id,
                normalized_start=start, normalized_end=end, page_number=current_page, section_path=sections,
                original_locator=OriginalLocator(
                    locator_kind="text_bytes", page_number=current_page, region_microunits=None,
                    original_start=original_start, original_end=original_end, parser_token_start=None, parser_token_end=None,
                ), exact_text_hash=sha256_bytes(exact), original_quote_hash=sha256_bytes(original_quote),
                content_hash=ZERO_HASH,
            )
            return finalize_content_hash(span)  # type: ignore[return-value]

        for line, terminator, char_start, char_end in _line_parts(normalized_text):
            line_start = _byte_offset(normalized_text, char_start)
            line_end = line_start + len(line.encode("utf-8"))
            match = _MARKER.match(line)
            if match:
                marker_name, label, text = match.groups()
                label = label or None
                if marker_name == "SECTION":
                    section_path = (label or text or "untitled",)
                content_character_start = match.start(3)
                content_start = line_start + len(line[:content_character_start].encode("utf-8"))
                content_end = line_end
                if content_end <= content_start:
                    content_start, content_end = line_start, max(line_end, line_start + 1)
                span = make_span(content_start, content_end, page, section_path)
                spans.append(span)
                marker_type = _DOCUMENT_MARKER_BY_INPUT.get(marker_name)
                if marker_type:
                    marker_ordinal += 1
                    marker = DocumentMarker(
                        id=stable_id("marker", {"document": document_id.value, "span": span.id.value, "type": marker_type, "label": label}),
                        normalized_document_id=document_id, span_id=span.id, marker_type=marker_type, label=label,
                        ordinal=marker_ordinal, extraction_method=PARSER_NAME, disposition=Disposition.PROPOSAL,
                        warning_codes=(), content_hash=ZERO_HASH,
                    )
                    markers.append(finalize_content_hash(marker))  # type: ignore[arg-type]
                unit_type = _UNIT_BY_MARKER.get(marker_name)
                if unit_type is not None and text:
                    unit = EvidenceUnit(
                        id=stable_id("evidence", {"artifact": artifact.id.value, "span": span.id.value, "type": unit_type.value}),
                        unit_type=unit_type, origin=EvidenceOrigin.PARSER_DERIVED, source_artifact_id=artifact.id,
                        normalized_document_id=document_id, source_span_ids=(span.id,), model_call_id=None,
                        proposal_artifact_hash=None, payload=freeze_json(_payload(unit_type, label, text)),  # type: ignore[arg-type]
                        extraction_method=PARSER_NAME, extraction_version=PARSER_VERSION, warning_codes=(),
                        disposition=Disposition.PROPOSAL, content_hash=ZERO_HASH, created_at=created_at, created_by=actor_id,
                    )
                    units.append(finalize_content_hash(unit))  # type: ignore[arg-type]
            elif line.strip():
                leading = len(line) - len(line.lstrip())
                start = line_start + len(line[:leading].encode("utf-8"))
                span = make_span(start, line_end, page, section_path)
                spans.append(span)
                text = line.strip()
                unit = EvidenceUnit(
                    id=stable_id("evidence", {"artifact": artifact.id.value, "span": span.id.value, "type": EvidenceUnitType.SOURCE_PASSAGE.value}),
                    unit_type=EvidenceUnitType.SOURCE_PASSAGE, origin=EvidenceOrigin.PARSER_DERIVED,
                    source_artifact_id=artifact.id, normalized_document_id=document_id, source_span_ids=(span.id,),
                    model_call_id=None, proposal_artifact_hash=None,
                    payload=freeze_json(_payload(EvidenceUnitType.SOURCE_PASSAGE, None, text)),  # type: ignore[arg-type]
                    extraction_method=PARSER_NAME, extraction_version=PARSER_VERSION, warning_codes=(),
                    disposition=Disposition.PROPOSAL, content_hash=ZERO_HASH, created_at=created_at, created_by=actor_id,
                )
                units.append(finalize_content_hash(unit))  # type: ignore[arg-type]
            if terminator == "\f":
                terminator_start = _byte_offset(normalized_text, char_end - 1)
                page_span = make_span(terminator_start, terminator_start + 1, page, section_path)
                spans.append(page_span)
                marker_ordinal += 1
                page_marker = DocumentMarker(
                    id=stable_id("marker", {"document": document_id.value, "span": page_span.id.value, "type": "page", "ordinal": page}),
                    normalized_document_id=document_id, span_id=page_span.id, marker_type="page", label=None, ordinal=page,
                    extraction_method=PARSER_NAME, disposition=Disposition.PROPOSAL, warning_codes=(), content_hash=ZERO_HASH,
                )
                markers.append(finalize_content_hash(page_marker))  # type: ignore[arg-type]
                page += 1

        location_map = {
            "schema_version": "1.0.0",
            "source_artifact_id": artifact.id.value,
            "normalized_document_id": document_id.value,
            "segments": [segment.__dict__ if hasattr(segment, "__dict__") else {
                "normalized_start": segment.normalized_start, "normalized_end": segment.normalized_end,
                "original_start": segment.original_start, "original_end": segment.original_end,
                "normalized_hash": segment.normalized_hash, "original_hash": segment.original_hash,
            } for segment in segments],
        }
        structure_map = {
            "schema_version": "1.0.0", "normalized_document_id": document_id.value,
            "marker_ids": [marker.id.value for marker in markers], "evidence_unit_ids": [unit.id.value for unit in units],
        }
        location_map_bytes = canonical_bytes(location_map)
        structure_map_bytes = canonical_bytes(structure_map)
        location_ref = self.artifacts.put(location_map_bytes, media_type="application/json")
        structure_ref = self.artifacts.put(structure_map_bytes, media_type="application/json")
        warnings: tuple[ExtractionWarning, ...] = ()
        document = NormalizedDocument(
            id=document_id, source_artifact_id=artifact.id, parser_run_id=run_id,
            normalized_text_artifact_hash=normalized_ref.content_hash, structure_map_artifact_hash=structure_ref.content_hash,
            location_map_artifact_hash=location_ref.content_hash, unicode_normalization="NFC", newline_policy="LF",
            coordinate_unit="utf8_byte", normalization_version=PARSER_VERSION, warnings=warnings,
            disposition=Disposition.PROPOSAL, content_hash=ZERO_HASH, created_at=created_at, created_by=actor_id,
        )
        document = finalize_content_hash(document)  # type: ignore[assignment]
        run = ParserRunRecord(
            id=run_id, source_artifact_id=artifact.id, parser_name=self.name, parser_version=self.version,
            parser_configuration_hash=PARSER_CONFIGURATION_HASH, dependency_environment_hash=DEPENDENCY_ENVIRONMENT_HASH,
            input_hash=artifact.artifact_hash, status="succeeded", warning_codes=(), declared_confidence=None,
            stdout_artifact_hash=stdout.content_hash, stderr_artifact_hash=stderr.content_hash,
            output_artifact_hash=normalized_ref.content_hash, idempotency_key=f"parse:{artifact.artifact_hash}:{PARSER_CONFIGURATION_HASH}",
            created_at=created_at,
        )
        return ParseBundle(run, document, tuple(spans), tuple(markers), tuple(units), normalized_bytes, location_map_bytes, structure_map_bytes)
