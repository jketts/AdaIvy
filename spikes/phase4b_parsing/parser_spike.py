"""Bounded, stdlib-only parser contract used by the Phase 4B adoption spike.

This is deliberately not a general HTML, TeX, PDF, or OCR parser.  It exercises
the custody and failure contracts that a later gated adapter must satisfy while
accepting only small synthetic profiles.  Every output remains a candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any


SCHEMA_VERSION = "phase4b-parser-spike-v1"
BOUNDS = {
    "max_input_bytes": 32_768,
    "max_candidate_bytes": 16_384,
    "max_output_bytes": 12_288,
    "max_segments": 32,
    "max_formulas": 16,
    "max_segment_bytes": 4_096,
    "max_warnings": 16,
    "max_markup_tokens": 512,
}


class ParserRejection(ValueError):
    """A fail-closed rejection with a stable machine-readable reason."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _lineage(value: bytes) -> dict[str, Any]:
    return {"byte_length": len(value), "sha256": _sha256(value)}


def _segment(
    *, kind: str, text: str, original: bytes, start: int, end: int
) -> dict[str, Any]:
    raw = original[start:end]
    if not text.strip() or not raw:
        raise ParserRejection("empty_segment_forbidden")
    if end < start or len(raw) > BOUNDS["max_segment_bytes"]:
        raise ParserRejection("segment_bound_exceeded")
    return {
        "kind": kind,
        "normalized_text": text,
        "original_byte_span": {"end": end, "start": start},
        "original_slice_sha256": _sha256(raw),
    }


@dataclass
class _HTMLCollector(HTMLParser):
    original: bytes

    def __post_init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.segments: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.stack: list[str] = []
        self.token_count = 0
        decoded = self.original.decode("utf-8", errors="strict")
        self._decoded = decoded
        starts = [0]
        for match in re.finditer("\n", decoded):
            starts.append(match.end())
        self._line_starts = starts

    def _bump(self) -> None:
        self.token_count += 1
        if self.token_count > BOUNDS["max_markup_tokens"]:
            raise ParserRejection("markup_token_bound_exceeded")

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower() != "doctype html":
            raise ParserRejection("html_doctype_or_declaration_forbidden")
        self._bump()

    def handle_comment(self, data: str) -> None:
        self._bump()
        self._warn("html_comment_ignored")

    def handle_entityref(self, name: str) -> None:
        raise ParserRejection("html_entity_reference_forbidden")

    def handle_charref(self, name: str) -> None:
        raise ParserRejection("html_character_reference_forbidden")

    def unknown_decl(self, data: str) -> None:
        raise ParserRejection("html_unknown_declaration_forbidden")

    def handle_pi(self, data: str) -> None:
        raise ParserRejection("html_processing_instruction_forbidden")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._bump()
        tag = tag.lower()
        if tag in {"script", "iframe", "object", "embed", "applet", "style", "svg"}:
            raise ParserRejection("html_active_content_forbidden")
        allowed = {
            "html", "head", "meta", "title", "body", "article", "section",
            "div", "h1", "h2", "h3", "h4", "p", "span", "strong", "em",
            "ol", "ul", "li", "blockquote", "math", "mrow", "mi", "mn",
            "mo", "msup", "msub", "mfrac", "semantics", "annotation",
        }
        if tag not in allowed:
            raise ParserRejection("html_tag_outside_profile")
        attribute_map = {name.lower(): (value or "").strip() for name, value in attrs}
        if tag == "meta" and attribute_map.get("http-equiv", "").lower() == "refresh":
            raise ParserRejection("html_meta_refresh_forbidden")
        global_attributes = {"aria-label", "class", "id", "lang", "role"}
        tag_attributes = {
            "meta": {"charset", "content", "http-equiv", "name"},
            "math": {"display", "xmlns"},
            "annotation": {"encoding"},
        }
        for name, value in attrs:
            lower_name = name.lower()
            lower_value = (value or "").strip().lower()
            if lower_name.startswith("on") or lower_name in {"srcdoc", "formaction"}:
                raise ParserRejection("html_active_attribute_forbidden")
            if lower_name in {"href", "src", "action", "poster", "data", "xlink:href"}:
                if lower_value.startswith(
                    ("http:", "https:", "file:", "data:", "javascript:", "vbscript:", "//")
                ):
                    raise ParserRejection("html_external_reference_forbidden")
            if lower_name not in global_attributes | tag_attributes.get(tag, set()):
                raise ParserRejection("html_attribute_outside_profile")
        if tag != "meta":
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() != "meta":
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        self._bump()
        tag = tag.lower()
        if not self.stack or self.stack[-1] != tag:
            raise ParserRejection("html_unbalanced_structure")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        self._bump()
        normalized = " ".join(data.split())
        if not normalized or not self.stack or self.stack[-1] in {"head", "title"}:
            return
        line, column = self.getpos()
        char_start = self._line_starts[line - 1] + column
        start = len(self._decoded[:char_start].encode("utf-8"))
        end = start + len(data.encode("utf-8"))
        kind = "formula" if "math" in self.stack else "text"
        self.segments.append(
            _segment(kind=kind, text=normalized, original=self.original, start=start, end=end)
        )
        _enforce_segment_counts(self.segments)

    def close_checked(self) -> None:
        self.close()
        if self.stack:
            raise ParserRejection("html_unbalanced_structure")

    def _warn(self, warning: str) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)
        if len(self.warnings) > BOUNDS["max_warnings"]:
            raise ParserRejection("warning_bound_exceeded")


def _enforce_segment_counts(segments: list[dict[str, Any]]) -> None:
    if len(segments) > BOUNDS["max_segments"]:
        raise ParserRejection("segment_count_bound_exceeded")
    if sum(item["kind"] == "formula" for item in segments) > BOUNDS["max_formulas"]:
        raise ParserRejection("formula_count_bound_exceeded")


def _parse_html(original: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    collector = _HTMLCollector(original)
    collector.feed(original.decode("utf-8", errors="strict"))
    collector.close_checked()
    if not collector.segments:
        raise ParserRejection("html_no_supported_content")
    return collector.segments, collector.warnings


_DANGEROUS_TEX_COMMANDS = {
    "catcode", "csname", "def", "documentclass", "endcsname", "everyjob",
    "include", "includegraphics", "immediate", "input", "loop", "newcommand",
    "openin", "openout", "read", "repeat", "special", "usepackage", "write",
}
_KNOWN_TEX_COMMANDS = {"begin", "end", "section", "subsection", "textbf", "emph"}


def _parse_tex(original: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    text = original.decode("utf-8", errors="strict")
    if "\x00" in text:
        raise ParserRejection("tex_nul_forbidden")
    commands = list(re.finditer(r"\\([A-Za-z@]+)", text))
    if len(commands) > BOUNDS["max_markup_tokens"]:
        raise ParserRejection("markup_token_bound_exceeded")
    for command in commands:
        if command.group(1).lower() in _DANGEROUS_TEX_COMMANDS:
            raise ParserRejection("tex_active_or_expanding_command_forbidden")
    if text.count("{") != text.count("}"):
        raise ParserRejection("tex_unbalanced_group")

    warnings = sorted({
        "unknown_tex_command:" + item.group(1)
        for item in commands
        if item.group(1).lower() not in _KNOWN_TEX_COMMANDS
        and item.group(1) not in {"[", "]"}
    })
    if len(warnings) > BOUNDS["max_warnings"]:
        raise ParserRejection("warning_bound_exceeded")

    spans: list[tuple[int, int]] = []
    segments: list[dict[str, Any]] = []
    formula_patterns = (
        re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$", re.DOTALL),
        re.compile(r"\\\[(.+?)\\\]", re.DOTALL),
        re.compile(r"\\begin\{equation\*?\}(.+?)\\end\{equation\*?\}", re.DOTALL),
    )
    for pattern in formula_patterns:
        for match in pattern.finditer(text):
            char_start, char_end = match.span(1)
            start = len(text[:char_start].encode("utf-8"))
            end = len(text[:char_end].encode("utf-8"))
            spans.append((char_start, char_end))
            segments.append(_segment(
                kind="formula", text=" ".join(match.group(1).split()),
                original=original, start=start, end=end,
            ))

    for match in re.finditer(r"\\(?:sub)?section\{([^{}]+)\}", text):
        char_start, char_end = match.span(1)
        start = len(text[:char_start].encode("utf-8"))
        end = len(text[:char_end].encode("utf-8"))
        segments.append(_segment(
            kind="text", text=" ".join(match.group(1).split()),
            original=original, start=start, end=end,
        ))
    segments.sort(key=lambda item: item["original_byte_span"]["start"])
    _enforce_segment_counts(segments)
    if not segments:
        raise ParserRejection("tex_no_supported_content")
    return segments, warnings


_FORBIDDEN_PDF_TOKENS = (
    b"/AA", b"/AcroForm", b"/EmbeddedFile", b"/Encrypt", b"/JavaScript",
    b"/JS", b"/Launch", b"/OpenAction", b"/RichMedia", b"/SubmitForm",
    b"/URI", b"/XFA",
)


def _decode_pdf_literal(raw: bytes) -> str:
    if any(byte > 0x7F for byte in raw):
        raise ParserRejection("pdf_literal_encoding_outside_profile")
    result = bytearray()
    index = 0
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9}
    while index < len(raw):
        byte = raw[index]
        if byte != 92:
            result.append(byte)
            index += 1
            continue
        index += 1
        if index >= len(raw):
            raise ParserRejection("pdf_malformed_literal")
        escaped = raw[index]
        if escaped in escapes:
            result.append(escapes[escaped])
        elif escaped in (40, 41, 92):
            result.append(escaped)
        else:
            raise ParserRejection("pdf_escape_outside_profile")
        index += 1
    return result.decode("ascii")


def _parse_pdf(original: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    if not original.startswith(b"%PDF-1.") or not original.rstrip().endswith(b"%%EOF"):
        raise ParserRejection("pdf_envelope_invalid")
    if any(token in original for token in _FORBIDDEN_PDF_TOKENS):
        raise ParserRejection("pdf_active_or_embedded_content_forbidden")
    if b"/Filter" in original:
        raise ParserRejection("pdf_compressed_stream_outside_profile")
    if original.count(b" obj") > BOUNDS["max_markup_tokens"]:
        raise ParserRejection("markup_token_bound_exceeded")
    segments: list[dict[str, Any]] = []
    for match in re.finditer(rb"\(([^()]*)\)\s*Tj", original):
        decoded = _decode_pdf_literal(match.group(1))
        kind = "formula" if decoded.startswith("FORMULA:") else "text"
        normalized = decoded.removeprefix("FORMULA:").strip()
        segments.append(_segment(
            kind=kind, text=" ".join(normalized.split()), original=original,
            start=match.start(1), end=match.end(1),
        ))
        _enforce_segment_counts(segments)
    if not segments:
        if b"/Subtype /Image" in original:
            raise ParserRejection("ocr_required")
        raise ParserRejection("pdf_no_born_digital_text")
    return segments, ["restricted_uncompressed_pdf_profile"]


def parse_candidate(
    *, source_id: str, representation_id: str, media_type: str, original: bytes
) -> dict[str, Any]:
    """Parse one bounded representation, returning candidate or quarantine state."""
    base: dict[str, Any] = {
        "bounds": dict(BOUNDS),
        "media_type": media_type,
        "original_lineage": _lineage(original),
        "parser_profile": "stdlib-restricted-spike-v1",
        "quarantine_reason": None,
        "representation_id": representation_id,
        "schema_version": SCHEMA_VERSION,
        "segments": [],
        "source_id": source_id,
        "status": "quarantined",
        "warnings": [],
    }
    try:
        if len(original) > BOUNDS["max_input_bytes"]:
            raise ParserRejection("input_byte_bound_exceeded")
        if media_type == "text/html":
            segments, warnings = _parse_html(original)
        elif media_type in {"application/x-tex", "text/x-tex"}:
            segments, warnings = _parse_tex(original)
        elif media_type == "application/pdf":
            segments, warnings = _parse_pdf(original)
        else:
            raise ParserRejection("unsupported_media_type")
        base.update(status="accepted_candidate", segments=segments, warnings=warnings)
        if len(_canonical_bytes(base)) > BOUNDS["max_output_bytes"]:
            raise ParserRejection("output_byte_bound_exceeded")
    except (ParserRejection, UnicodeDecodeError) as error:
        reason = error.reason if isinstance(error, ParserRejection) else "invalid_utf8"
        base.update(quarantine_reason=reason, segments=[], status="quarantined", warnings=[])
    return base


def ingest_ocr_candidate(
    *, source_id: str, representation_id: str, original: bytes, candidate: bytes
) -> dict[str, Any]:
    """Capture, but never admit, output proposed by a future OCR adapter."""
    record: dict[str, Any] = {
        "bounds": dict(BOUNDS),
        "candidate_lineage": _lineage(candidate),
        "media_type": "application/vnd.adaivy.ocr-candidate+plain",
        "original_lineage": _lineage(original),
        "parser_profile": "captured-ocr-output-spike-v1",
        "quarantine_reason": "ocr_requires_independent_review",
        "representation_id": representation_id,
        "schema_version": SCHEMA_VERSION,
        "segments": [],
        "source_id": source_id,
        "status": "quarantined",
        "warnings": ["no_exact_original_text_span"],
    }
    try:
        if len(original) > BOUNDS["max_input_bytes"]:
            raise ParserRejection("input_byte_bound_exceeded")
        if len(candidate) > BOUNDS["max_candidate_bytes"]:
            raise ParserRejection("candidate_byte_bound_exceeded")
        decoded = candidate.decode("utf-8", errors="strict")
        cursor = 0
        for line in decoded.splitlines(keepends=True):
            content = line.rstrip("\r\n")
            raw = content.encode("utf-8")
            if content.strip():
                record["segments"].append({
                    "candidate_byte_span": {"end": cursor + len(raw), "start": cursor},
                    "candidate_slice_sha256": _sha256(raw),
                    "kind": "ocr_text_candidate",
                    "normalized_text": " ".join(content.split()),
                    "original_byte_span": None,
                })
                _enforce_segment_counts(record["segments"])
            cursor += len(line.encode("utf-8"))
        if not record["segments"]:
            raise ParserRejection("ocr_candidate_empty")
        if len(_canonical_bytes(record)) > BOUNDS["max_output_bytes"]:
            raise ParserRejection("output_byte_bound_exceeded")
    except (ParserRejection, UnicodeDecodeError) as error:
        reason = error.reason if isinstance(error, ParserRejection) else "invalid_utf8"
        record.update(quarantine_reason=reason, segments=[], warnings=[])
    return record


def compare_representations(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Compare formula proposals without treating agreement as verification."""
    if left.get("source_id") != right.get("source_id"):
        raise ValueError("representations must bind the same source_id")
    left_formulas = [s["normalized_text"] for s in left.get("segments", []) if s["kind"] == "formula"]
    right_formulas = [s["normalized_text"] for s in right.get("segments", []) if s["kind"] == "formula"]
    rejection_reason = None
    if left.get("status") != "accepted_candidate" or right.get("status") != "accepted_candidate":
        rejection_reason = "representation_not_accepted_candidate"
    elif not left_formulas or not right_formulas:
        rejection_reason = "formula_missing"
    if rejection_reason is not None:
        return {
            "agreement": "not_comparable",
            "comparison_status": "quarantined",
            "left_formula_digest": _sha256(_canonical_bytes({"values": left_formulas})),
            "left_representation_id": left["representation_id"],
            "quarantine_reason": rejection_reason,
            "quarantine_required": True,
            "right_formula_digest": _sha256(_canonical_bytes({"values": right_formulas})),
            "right_representation_id": right["representation_id"],
            "schema_version": "phase4b-representation-comparison-spike-v1",
            "source_id": left["source_id"],
        }
    agreement = "identical_candidate_text" if left_formulas == right_formulas else "disagreement"
    return {
        "agreement": agreement,
        "comparison_status": "accepted_candidate",
        "left_formula_digest": _sha256(_canonical_bytes({"values": left_formulas})),
        "left_representation_id": left["representation_id"],
        "quarantine_reason": "formula_disagreement" if agreement == "disagreement" else None,
        "quarantine_required": agreement == "disagreement",
        "right_formula_digest": _sha256(_canonical_bytes({"values": right_formulas})),
        "right_representation_id": right["representation_id"],
        "schema_version": "phase4b-representation-comparison-spike-v1",
        "source_id": left["source_id"],
    }
