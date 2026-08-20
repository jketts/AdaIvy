"""Bounded exact-byte parser core for the Phase 4B worker boundary.

This module is a production *candidate*, not an activated production parser.
It deliberately supports only a strict UTF-8 HTML subset and a non-expanding
UTF-8 TeX subset for which every surfaced segment maps to an exact source-byte
slice.  PDF is rejected because the current repository cannot honestly map
general extracted PDF prose back to exact source bytes.

``ExactSourceParserWorker`` is intentionally marked as lacking an OS sandbox.
It can be exercised directly as parser-core evidence, but the existing
``run_production_parser`` boundary will reject it until a parser-connected OS
sandbox supplies the required contract.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .parsing import (
    AdapterOutcome,
    ByteAnchor,
    ContentRejected,
    HTML_PROFILE,
    PARSER_BOUNDS,
    PDF_PROFILE,
    ParsedSegment,
    ParseRequest,
    TEX_PROFILE,
    WorkerExecution,
)


WORKER_NAME = "adaivy-exact-source-parser-candidate"
WORKER_VERSION = "0.1.0"
CANDIDATE_SANDBOX_CONTRACT = "candidate-parser-core-without-os-sandbox-v1"

def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


CROSS_FORMAT_AMBIGUITY = "cross_format_envelope_ambiguity"


def _has_structural_pdf_envelope(original: bytes) -> bool:
    for header in re.finditer(rb"%PDF-1\.[0-7]\r?\n", original):
        tail = original[header.start():]
        for footer in re.finditer(rb"startxref\r?\n([0-9]+)\r?\n%%EOF(?:\r?\n|\Z)", tail):
            offset = int(footer.group(1))
            if offset <= 0 or offset >= footer.start() or not tail.startswith(b"xref\n", offset):
                continue
            subsection = re.match(rb"xref\n0 ([1-9][0-9]*)\n", tail[offset:])
            if subsection is None:
                continue
            size = int(subsection.group(1))
            if size > 1_025:
                continue
            entries_start = offset + len(subsection.group(0))
            entries_end = entries_start + size * 20
            entries = tail[entries_start:entries_end]
            if len(entries) != size * 20 or any(
                re.fullmatch(rb"[0-9]{10} [0-9]{5} [nf] \n", entries[index:index + 20]) is None
                for index in range(0, len(entries), 20)
            ):
                continue
            trailer = tail[entries_end:footer.start()]
            if re.search(rb"\btrailer\s*<<[^<>]*/Size\s+" + str(size).encode("ascii") + rb"\b[^<>]*/Root\s+[1-9][0-9]*\s+[0-9]+\s+R\b[^<>]*>>\s*\Z", trailer, re.DOTALL):
                return True
    return False


def _has_structural_html_envelope(original: bytes) -> bool:
    try:
        text = original.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return False
    for root in re.finditer(r"<html(?:\s[^<>]*)?>", text, re.IGNORECASE):
        close = re.search(r"</html\s*>", text[root.end():], re.IGNORECASE)
        if close is None:
            continue
        candidate = text[root.start():root.end() + close.end()]
        body_open = re.search(r"<body(?:\s[^<>]*)?>", candidate, re.IGNORECASE)
        body_close = re.search(r"</body\s*>", candidate, re.IGNORECASE)
        if (
            body_open is not None and body_close is not None
            and body_open.end() <= body_close.start()
            and len(re.findall(r"<html(?:\s[^<>]*)?>", candidate, re.IGNORECASE)) == 1
            and len(re.findall(r"</html\s*>", candidate, re.IGNORECASE)) == 1
        ):
            return True
    return False


def _has_structural_tex_envelope(original: bytes) -> bool:
    try:
        text = original.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return False
    section = re.search(r"\\(?:sub)?section\{[^{}\r\n]+\}", text)
    if section is None:
        return False
    inline = re.search(r"(?<!\\)\$(?!\$)[^$\r\n]+(?<!\\)\$", text[section.end():])
    display = re.search(r"\\\[[^\]]+\\\]", text[section.end():], re.DOTALL)
    return inline is not None or display is not None


def _reject_cross_format_ambiguity(original: bytes, expected: str) -> None:
    detected = {
        name for name, present in (
            ("html", _has_structural_html_envelope(original)),
            ("tex", _has_structural_tex_envelope(original)),
            ("pdf", _has_structural_pdf_envelope(original)),
        ) if present
    }
    if detected - {expected}:
        raise ContentRejected(CROSS_FORMAT_AMBIGUITY)


IMPLEMENTATION_SOURCE_PATH = Path(__file__).resolve()
# The digest is computed from, rather than embedded in, the shipped source.
# Consequently every source-level behavior change also changes the identity,
# without requiring a self-referential digest substitution step.
IMPLEMENTATION_SHA256 = _sha256(IMPLEMENTATION_SOURCE_PATH.read_bytes())
DEPENDENCY_ENVIRONMENT_SHA256 = _sha256(b"python-standard-library-only")


def _decode_utf8(original: bytes, failure_code: str) -> tuple[str, list[int]]:
    try:
        decoded = original.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ContentRejected(failure_code) from error
    offsets = [0]
    byte_offset = 0
    for character in decoded:
        byte_offset += len(character.encode("utf-8"))
        offsets.append(byte_offset)
    return decoded, offsets


def _segment(
    original: bytes,
    offsets: list[int],
    *,
    ordinal: int,
    kind: str,
    text: str,
    char_start: int,
    char_end: int,
) -> ParsedSegment:
    normalized = " ".join(text.split())
    if not normalized:
        raise ContentRejected("empty_segment_forbidden")
    return ParsedSegment(
        segment_id=f"segment.{ordinal:04d}",
        kind=kind,
        normalized_text=normalized,
        anchor=ByteAnchor.create(
            original, offsets[char_start], offsets[char_end]
        ),
        load_bearing=kind == "formula",
    )


_HTML_ALLOWED_TAGS = {
    "html", "head", "meta", "title", "body", "article", "section", "div",
    "h1", "h2", "h3", "h4", "p", "span", "strong", "em", "ol", "ul",
    "li", "blockquote", "math", "mrow", "mi", "mn", "mo", "msup", "msub",
    "mfrac", "semantics", "annotation",
}
_HTML_VOID_TAGS = {"meta"}
_HTML_GLOBAL_ATTRIBUTES = {"aria-label", "class", "id", "lang", "role"}
_HTML_TAG_ATTRIBUTES = {
    "meta": {"charset", "content", "http-equiv", "name"},
    "math": {"display", "xmlns"},
    "annotation": {"encoding"},
}
_HTML_FORBIDDEN_TAGS = {
    "applet", "embed", "form", "iframe", "object", "script", "style", "svg",
}
_HTML_ATTRIBUTE = re.compile(
    r"\s+([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')"
)


def _end_of_html_tag(text: str, start: int) -> int:
    quote: str | None = None
    index = start + 1
    while index < len(text):
        character = text[index]
        if quote is None and character in {'"', "'"}:
            quote = character
        elif quote == character:
            quote = None
        elif quote is None and character == ">":
            return index + 1
        index += 1
    raise ContentRejected("html_unterminated_tag")


def _parse_html_tag(raw: str) -> tuple[bool, str, dict[str, str], bool]:
    end_match = re.fullmatch(r"</([A-Za-z][A-Za-z0-9:-]*)\s*>", raw)
    if end_match:
        return True, end_match.group(1).lower(), {}, False
    match = re.fullmatch(r"<([A-Za-z][A-Za-z0-9:-]*)(.*?)(/?)>", raw, re.DOTALL)
    if match is None:
        raise ContentRejected("html_malformed_tag")
    tag = match.group(1).lower()
    remainder = match.group(2)
    attributes: dict[str, str] = {}
    position = 0
    while position < len(remainder):
        if remainder[position:].strip() == "":
            break
        attribute = _HTML_ATTRIBUTE.match(remainder, position)
        if attribute is None:
            raise ContentRejected("html_malformed_attribute")
        name = attribute.group(1).lower()
        if name in attributes:
            raise ContentRejected("html_duplicate_attribute")
        attributes[name] = attribute.group(2) if attribute.group(2) is not None else attribute.group(3)
        position = attribute.end()
    return False, tag, attributes, bool(match.group(3))


def parse_exact_html(original: bytes) -> AdapterOutcome:
    """Parse the strict HTML subset without entity or tree repair semantics."""
    _reject_cross_format_ambiguity(original, "html")
    text, offsets = _decode_utf8(original, "html_invalid_utf8")
    if "\x00" in text:
        raise ContentRejected("html_nul_forbidden")
    stack: list[str] = []
    segments: list[ParsedSegment] = []
    warnings: list[str] = []
    index = 0
    saw_doctype = False
    root_seen = False
    root_closed = False
    while index < len(text):
        if text.startswith("<!--", index):
            end = text.find("-->", index + 4)
            if end < 0:
                raise ContentRejected("html_unterminated_comment")
            if "--" in text[index + 4:end]:
                raise ContentRejected("html_malformed_comment")
            if "html_comment_ignored" not in warnings:
                warnings.append("html_comment_ignored")
            index = end + 3
            continue
        if text[index] == "<":
            end = _end_of_html_tag(text, index)
            raw = text[index:end]
            if raw.startswith("<?"):
                raise ContentRejected("html_processing_instruction_forbidden")
            if raw.startswith("<!"):
                if re.fullmatch(r"<!doctype\s+html\s*>", raw, re.IGNORECASE) is None:
                    raise ContentRejected("html_declaration_forbidden")
                if saw_doctype or stack or segments:
                    raise ContentRejected("html_doctype_position_invalid")
                saw_doctype = True
                index = end
                continue
            closing, tag, attributes, self_closing = _parse_html_tag(raw)
            if tag in _HTML_FORBIDDEN_TAGS:
                raise ContentRejected("html_active_content_forbidden")
            if tag not in _HTML_ALLOWED_TAGS:
                raise ContentRejected("html_tag_outside_profile")
            if closing:
                if attributes or self_closing or not stack or stack[-1] != tag:
                    raise ContentRejected("html_unbalanced_structure")
                stack.pop()
                if tag == "html":
                    root_closed = True
            else:
                if not stack:
                    if tag != "html" or root_seen or root_closed:
                        raise ContentRejected("html_root_structure_invalid")
                    root_seen = True
                for name, value in attributes.items():
                    lowered = value.strip().lower()
                    if name.startswith("on") or name in {"srcdoc", "formaction"}:
                        raise ContentRejected("html_active_attribute_forbidden")
                    if name in {"href", "src", "action", "poster", "data", "xlink:href"}:
                        raise ContentRejected("html_external_reference_forbidden")
                    if name not in _HTML_GLOBAL_ATTRIBUTES | _HTML_TAG_ATTRIBUTES.get(tag, set()):
                        raise ContentRejected("html_attribute_outside_profile")
                    if lowered.startswith(("data:", "file:", "http:", "https:", "javascript:", "vbscript:", "//")):
                        raise ContentRejected("html_external_reference_forbidden")
                if tag == "meta" and attributes.get("http-equiv", "").strip().lower() == "refresh":
                    raise ContentRejected("html_meta_refresh_forbidden")
                if self_closing and tag not in _HTML_VOID_TAGS:
                    raise ContentRejected("html_self_closing_tag_outside_profile")
                if tag not in _HTML_VOID_TAGS:
                    stack.append(tag)
                    if len(stack) > PARSER_BOUNDS.max_nesting_depth:
                        raise ContentRejected("nesting_depth_bound_exceeded")
            index = end
            continue
        end = text.find("<", index)
        if end < 0:
            end = len(text)
        raw_text = text[index:end]
        if "&" in raw_text:
            raise ContentRejected("html_entity_reference_outside_profile")
        if raw_text.strip():
            if not stack or stack[-1] in {"head", "title"}:
                if not stack:
                    raise ContentRejected("html_text_outside_root")
            else:
                segments.append(_segment(
                    original, offsets, ordinal=len(segments) + 1,
                    kind="formula" if "math" in stack else "text",
                    text=raw_text, char_start=index, char_end=end,
                ))
                if len(segments) > PARSER_BOUNDS.max_segments:
                    raise ContentRejected("segment_count_bound_exceeded")
                if sum(item.kind == "formula" for item in segments) > PARSER_BOUNDS.max_formulas:
                    raise ContentRejected("formula_count_bound_exceeded")
        index = end
    if stack:
        raise ContentRejected("html_unbalanced_structure")
    if not root_seen or not root_closed:
        raise ContentRejected("html_root_structure_invalid")
    if not segments:
        raise ContentRejected("empty_parse_proposal")
    return AdapterOutcome(
        tuple(segments), warnings=tuple(warnings),
        transformations=("utf8_exact_span_whitespace_collapse",),
    )


_DANGEROUS_TEX_COMMANDS = {
    "catcode", "csname", "def", "documentclass", "endcsname", "everyjob",
    "include", "includegraphics", "immediate", "input", "loop", "newcommand",
    "openin", "openout", "read", "repeat", "special", "usepackage", "write",
}
_KNOWN_TEX_COMMANDS = {"section", "subsection", "textbf", "emph"}
_TEX_COMMAND = re.compile(r"\\([A-Za-z@]+)")


def _unescaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 0


def _validate_tex_groups(text: str) -> None:
    depth = 0
    for index, character in enumerate(text):
        if not _unescaped(text, index):
            continue
        if character == "{":
            depth += 1
            if depth > PARSER_BOUNDS.max_nesting_depth:
                raise ContentRejected("nesting_depth_bound_exceeded")
        elif character == "}":
            depth -= 1
            if depth < 0:
                raise ContentRejected("tex_unbalanced_group")
    if depth:
        raise ContentRejected("tex_unbalanced_group")


def parse_exact_tex(original: bytes) -> AdapterOutcome:
    """Lex the non-expanding TeX subset and preserve UTF-8 byte positions."""
    _reject_cross_format_ambiguity(original, "tex")
    text, offsets = _decode_utf8(original, "tex_invalid_utf8")
    if "\x00" in text:
        raise ContentRejected("tex_nul_forbidden")
    if any(character == "%" and _unescaped(text, index) for index, character in enumerate(text)):
        raise ContentRejected("tex_comments_outside_profile")
    _validate_tex_groups(text)
    warning_values_set: set[str] = set()
    for command in _TEX_COMMAND.finditer(text):
        command_name = command.group(1)
        if command_name.lower() in _DANGEROUS_TEX_COMMANDS:
            raise ContentRejected("tex_active_or_expanding_command_forbidden")
        if command_name.lower() not in _KNOWN_TEX_COMMANDS:
            warning = "unknown_tex_command:" + command_name
            if len(warning.encode("utf-8")) > 256:
                raise ContentRejected("warning_invalid")
            warning_values_set.add(warning)
            if len(warning_values_set) > PARSER_BOUNDS.max_warnings:
                raise ContentRejected("warning_count_bound_exceeded")
    warning_values = sorted(warning_values_set)

    candidates: list[tuple[int, int, str, str]] = []
    formula_count = 0

    def append_candidate(start: int, end: int, kind: str, value: str) -> None:
        nonlocal formula_count
        if len(candidates) >= PARSER_BOUNDS.max_segments:
            raise ContentRejected("segment_count_bound_exceeded")
        if kind == "formula":
            formula_count += 1
            if formula_count > PARSER_BOUNDS.max_formulas:
                raise ContentRejected("formula_count_bound_exceeded")
        candidates.append((start, end, kind, value))

    for match in re.finditer(r"\\(?:sub)?section\{([^{}]+)\}", text):
        start, end = match.span(1)
        append_candidate(start, end, "text", match.group(1))

    index = 0
    while index < len(text):
        if text.startswith("\\[", index):
            end_marker = text.find("\\]", index + 2)
            if end_marker < 0:
                raise ContentRejected("tex_unterminated_formula")
            if "\\[" in text[index + 2:end_marker]:
                raise ContentRejected("tex_nested_formula_outside_profile")
            append_candidate(index + 2, end_marker, "formula", text[index + 2:end_marker])
            index = end_marker + 2
            continue
        if text[index] == "$" and _unescaped(text, index):
            if text.startswith("$$", index):
                raise ContentRejected("tex_display_dollar_outside_profile")
            end_marker = index + 1
            while end_marker < len(text):
                if text[end_marker] == "$" and _unescaped(text, end_marker):
                    break
                end_marker += 1
            if end_marker == len(text):
                raise ContentRejected("tex_unterminated_formula")
            append_candidate(index + 1, end_marker, "formula", text[index + 1:end_marker])
            index = end_marker + 1
            continue
        index += 1

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    occupied_end = -1
    segments: list[ParsedSegment] = []
    for start, end, kind, value in candidates:
        if start < occupied_end:
            raise ContentRejected("tex_overlapping_segment_outside_profile")
        occupied_end = end
        segments.append(_segment(
            original, offsets, ordinal=len(segments) + 1, kind=kind,
            text=value, char_start=start, char_end=end,
        ))
    if not segments:
        raise ContentRejected("empty_parse_proposal")
    return AdapterOutcome(
        tuple(segments), warnings=tuple(warning_values),
        transformations=("tex_nonexpanding_utf8_exact_span_whitespace_collapse",),
    )


class ExactSourceParserWorker:
    """Direct parser-core worker candidate; deliberately not sandbox-authorized."""

    name = WORKER_NAME
    version = WORKER_VERSION
    implementation_sha256 = IMPLEMENTATION_SHA256
    dependency_environment_sha256 = DEPENDENCY_ENVIRONMENT_SHA256
    sandbox_contract = CANDIDATE_SANDBOX_CONTRACT

    def execute(self, request: ParseRequest) -> WorkerExecution:
        try:
            if request.profile_name == HTML_PROFILE.name:
                outcome = parse_exact_html(request.original_bytes)
            elif request.profile_name == TEX_PROFILE.name:
                outcome = parse_exact_tex(request.original_bytes)
            elif request.profile_name == PDF_PROFILE.name:
                raise ContentRejected("pdf_exact_source_mapping_unsupported")
            else:
                raise ContentRejected("unsupported_parser_profile")
            return WorkerExecution.capture(
                outcome=outcome,
                operation_id="operation.parse.exact-source-candidate.v1",
                duration_ms=0,
                worker_exit_code=0,
            )
        except ContentRejected as error:
            return WorkerExecution.capture(
                outcome=None,
                operation_id="operation.parse.exact-source-candidate.v1",
                status="content_rejected",
                failure_code=error.reason,
                duration_ms=0,
                worker_exit_code=2,
            )


__all__ = [
    "CANDIDATE_SANDBOX_CONTRACT",
    "DEPENDENCY_ENVIRONMENT_SHA256",
    "ExactSourceParserWorker",
    "IMPLEMENTATION_SHA256",
    "IMPLEMENTATION_SOURCE_PATH",
    "WORKER_NAME",
    "WORKER_VERSION",
    "parse_exact_html",
    "parse_exact_tex",
]
