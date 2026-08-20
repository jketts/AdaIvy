"""Strict dependency-free candidate for a very small born-digital PDF subset.

This is deliberately not a general PDF implementation.  It accepts one
classic, non-incremental cross-reference table; a flat page tree; direct,
unfiltered content streams; and a small text-operator subset.  Every surfaced
string remains anchored to the literal bytes in the original PDF.  Unsupported
or ambiguous syntax fails closed before any candidate text is returned.

The adapter is pre-activation evidence only.  It performs no I/O and must still
run inside the approved parser-connected OS sandbox before production use.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from .parsing import (
    AdapterOutcome,
    ByteAnchor,
    ContentRejected,
    PARSER_BOUNDS,
    PDF_PROFILE,
    ParseRequest,
    ParsedSegment,
    Profile,
)


_PDF_WS = b"\x00\x09\x0a\x0c\x0d\x20"
_DELIMITERS = b"()<>[]{}/%"
_FORBIDDEN_NAMES = {
    "AA", "AcroForm", "EmbeddedFile", "Encrypt", "Filespec", "GoToE",
    "GoToR", "JavaScript", "JS", "Launch", "ObjStm", "OpenAction",
    "RichMedia", "SubmitForm", "URI", "XFA", "XRef",
}
_MAX_OBJECTS = 1_024
_MAX_PAGES = 256
_MAX_CONTENT_STREAM_BYTES = 2_097_152
_MAX_TOKENS = 65_536


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


IMPLEMENTATION_SOURCE_PATH = Path(__file__).resolve()
IMPLEMENTATION_SHA256 = _sha256(IMPLEMENTATION_SOURCE_PATH.read_bytes())

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


@dataclass(frozen=True)
class _Name:
    value: str


@dataclass(frozen=True)
class _Ref:
    number: int
    generation: int


@dataclass(frozen=True)
class _String:
    value: str
    content_start: int
    content_end: int


@dataclass(frozen=True)
class _Keyword:
    value: str


@dataclass(frozen=True)
class _Object:
    number: int
    generation: int
    value: Any
    stream_start: int | None
    stream_end: int | None
    object_end: int


class _Syntax:
    def __init__(self, data: bytes, position: int = 0) -> None:
        self.data = data
        self.position = position
        self.tokens = 0

    def _reject(self, reason: str = "pdf_syntax_outside_strict_profile") -> None:
        raise ContentRejected(reason)

    def skip_space(self) -> None:
        while self.position < len(self.data):
            byte = self.data[self.position]
            if byte in _PDF_WS:
                self.position += 1
                continue
            if byte == 0x25:  # comment
                end = self.data.find(b"\n", self.position)
                if end < 0:
                    self.position = len(self.data)
                else:
                    self.position = end + 1
                continue
            break

    def _bounded_token(self) -> None:
        self.tokens += 1
        if self.tokens > _MAX_TOKENS:
            self._reject("pdf_token_count_bound_exceeded")

    def parse(self, depth: int = 0) -> Any:
        if depth > PARSER_BOUNDS.max_nesting_depth:
            self._reject("pdf_nesting_bound_exceeded")
        self.skip_space()
        self._bounded_token()
        if self.data.startswith(b"<<", self.position):
            self.position += 2
            result: dict[str, Any] = {}
            while True:
                self.skip_space()
                if self.data.startswith(b">>", self.position):
                    self.position += 2
                    return result
                key = self.parse(depth + 1)
                if not isinstance(key, _Name) or key.value in result:
                    self._reject("pdf_dictionary_invalid_or_duplicate_key")
                result[key.value] = self.parse(depth + 1)
        if self.position >= len(self.data):
            self._reject("pdf_unexpected_end_of_input")
        byte = self.data[self.position]
        if byte == 0x5B:  # [
            self.position += 1
            values: list[Any] = []
            while True:
                self.skip_space()
                if self.position < len(self.data) and self.data[self.position] == 0x5D:
                    self.position += 1
                    return values
                values.append(self.parse(depth + 1))
                if len(values) > _MAX_OBJECTS:
                    self._reject("pdf_array_bound_exceeded")
        if byte == 0x2F:  # name
            start = self.position + 1
            end = start
            while end < len(self.data) and self.data[end] not in _PDF_WS + _DELIMITERS:
                end += 1
            raw = self.data[start:end]
            if not raw or b"#" in raw or any(item < 0x21 or item > 0x7E for item in raw):
                self._reject("pdf_name_outside_strict_profile")
            self.position = end
            name = raw.decode("ascii")
            if name in _FORBIDDEN_NAMES:
                self._reject("pdf_active_or_embedded_content_forbidden")
            if name in {"Filter", "DecodeParms"}:
                self._reject("pdf_compressed_stream_outside_profile")
            return _Name(name)
        if byte == 0x28:  # literal string
            return self._literal_string()
        if byte in b"+-0123456789":
            first = self._integer()
            saved = self.position
            self.skip_space()
            if self.position < len(self.data) and self.data[self.position] in b"0123456789":
                second = self._integer()
                self.skip_space()
                if self.data[self.position:self.position + 1] == b"R":
                    self.position += 1
                    if first < 1 or second < 0 or second > 65535:
                        self._reject("pdf_indirect_reference_invalid")
                    return _Ref(first, second)
            self.position = saved
            return first
        start = self.position
        while self.position < len(self.data) and self.data[self.position] not in _PDF_WS + _DELIMITERS:
            self.position += 1
        raw = self.data[start:self.position]
        if not raw or any(item < 0x21 or item > 0x7E for item in raw):
            self._reject()
        word = raw.decode("ascii")
        if word == "true":
            return True
        if word == "false":
            return False
        if word == "null":
            return None
        return _Keyword(word)

    def _integer(self) -> int:
        match = re.match(rb"[+-]?(?:0|[1-9][0-9]*)", self.data[self.position:])
        if match is None:
            self._reject("pdf_number_outside_strict_profile")
        raw = match.group(0)
        self.position += len(raw)
        value = int(raw)
        if abs(value) > 2_147_483_647:
            self._reject("pdf_number_bound_exceeded")
        return value

    def _literal_string(self) -> _String:
        self.position += 1
        content_start = self.position
        decoded = bytearray()
        nesting = 1
        while self.position < len(self.data):
            byte = self.data[self.position]
            if byte == 0x5C:  # backslash
                self.position += 1
                if self.position >= len(self.data):
                    self._reject("pdf_malformed_literal")
                escaped = self.data[self.position]
                simple = {
                    0x6E: 0x0A, 0x72: 0x0D, 0x74: 0x09, 0x62: 0x08,
                    0x66: 0x0C, 0x28: 0x28, 0x29: 0x29, 0x5C: 0x5C,
                }
                if escaped not in simple:
                    self._reject("pdf_escape_outside_strict_profile")
                decoded.append(simple[escaped])
                self.position += 1
                continue
            if byte == 0x28:
                nesting += 1
                if nesting > PARSER_BOUNDS.max_nesting_depth:
                    self._reject("pdf_nesting_bound_exceeded")
                decoded.append(byte)
                self.position += 1
                continue
            if byte == 0x29:
                nesting -= 1
                if nesting == 0:
                    content_end = self.position
                    self.position += 1
                    if any(item < 0x20 or item > 0x7E for item in decoded):
                        self._reject("pdf_literal_encoding_outside_profile")
                    return _String(decoded.decode("ascii"), content_start, content_end)
                decoded.append(byte)
                self.position += 1
                continue
            if byte < 0x20 or byte > 0x7E:
                self._reject("pdf_literal_encoding_outside_profile")
            decoded.append(byte)
            self.position += 1
        self._reject("pdf_malformed_literal")


class StrictBornDigitalPdfAdapter:
    """ParserAdapter candidate for strict, valid, uncompressed PDFs."""

    name = "adaivy-strict-born-digital-pdf-candidate"
    version = "0.1.0"
    implementation_sha256 = IMPLEMENTATION_SHA256
    dependency_environment_sha256 = _sha256(b"python-standard-library-only")

    def supports(self, profile: Profile) -> bool:
        return profile == PDF_PROFILE

    def parse(self, request: ParseRequest) -> AdapterOutcome:
        if request.profile_name != PDF_PROFILE.name:
            raise ContentRejected("unsupported_parser_profile")
        return parse_strict_pdf(request.original_bytes)


def _dictionary(value: Any, required: set[str], optional: set[str] = set()) -> dict[str, Any]:
    if not isinstance(value, dict) or not required <= set(value) or not set(value) <= required | optional:
        raise ContentRejected("pdf_dictionary_outside_strict_profile")
    return value


def _name(value: Any, expected: str) -> None:
    if value != _Name(expected):
        raise ContentRejected("pdf_object_type_invalid")


def _ref(value: Any) -> _Ref:
    if not isinstance(value, _Ref):
        raise ContentRejected("pdf_indirect_reference_required")
    return value


def _read_xref(data: bytes) -> tuple[dict[tuple[int, int], int], dict[str, Any], int]:
    if not re.fullmatch(rb"%PDF-1\.[0-7]\r?\n[\x00-\xff]*%%EOF\r?\n?", data):
        raise ContentRejected("pdf_envelope_invalid")
    if data.count(b"%%EOF") != 1 or data.count(b"startxref") != 1:
        raise ContentRejected("pdf_incremental_or_ambiguous_revision_forbidden")
    footer = re.search(rb"startxref\r?\n([0-9]+)\r?\n%%EOF\r?\n?\Z", data)
    if footer is None:
        raise ContentRejected("pdf_startxref_invalid")
    xref_offset = int(footer.group(1))
    if xref_offset >= len(data) or data[xref_offset:xref_offset + 5] != b"xref\n":
        raise ContentRejected("pdf_cross_reference_invalid")
    position = xref_offset + 5
    subsection = re.match(rb"0 ([1-9][0-9]*)\n", data[position:])
    if subsection is None:
        raise ContentRejected("pdf_cross_reference_invalid")
    size = int(subsection.group(1))
    if size > _MAX_OBJECTS + 1:
        raise ContentRejected("pdf_object_count_bound_exceeded")
    position += len(subsection.group(0))
    entries: dict[tuple[int, int], int] = {}
    for number in range(size):
        match = re.match(rb"([0-9]{10}) ([0-9]{5}) ([nf]) \n", data[position:])
        if match is None:
            raise ContentRejected("pdf_cross_reference_invalid")
        offset, generation, state = int(match.group(1)), int(match.group(2)), match.group(3)
        position += len(match.group(0))
        if number == 0:
            if (offset, generation, state) != (0, 65535, b"f"):
                raise ContentRejected("pdf_cross_reference_invalid")
        elif state != b"n" or offset <= 0 or offset >= xref_offset:
            raise ContentRejected("pdf_cross_reference_invalid")
        else:
            entries[(number, generation)] = offset
    if data[position:position + 8] != b"trailer\n":
        raise ContentRejected("pdf_trailer_invalid")
    syntax = _Syntax(data, position + 8)
    trailer = _dictionary(syntax.parse(), {"Size", "Root"}, {"Info", "ID"})
    if trailer["Size"] != size or not isinstance(trailer["Root"], _Ref):
        raise ContentRejected("pdf_trailer_invalid")
    if "Info" in trailer:
        _ref(trailer["Info"])
    if "ID" in trailer:
        raise ContentRejected("pdf_identifier_outside_strict_profile")
    syntax.skip_space()
    if syntax.position != footer.start():
        raise ContentRejected("pdf_trailer_ambiguous")
    return entries, trailer, xref_offset


def _read_object(data: bytes, offset: int) -> _Object:
    header = re.match(rb"([1-9][0-9]*) ([0-9]+) obj\r?\n", data[offset:])
    if header is None:
        raise ContentRejected("pdf_cross_reference_object_mismatch")
    number, generation = int(header.group(1)), int(header.group(2))
    syntax = _Syntax(data, offset + len(header.group(0)))
    value = syntax.parse()
    syntax.skip_space()
    stream_start: int | None = None
    stream_end: int | None = None
    if data.startswith(b"stream\n", syntax.position):
        dictionary = _dictionary(value, {"Length"})
        length = dictionary["Length"]
        if isinstance(length, bool) or not isinstance(length, int) or not 0 <= length <= _MAX_CONTENT_STREAM_BYTES:
            raise ContentRejected("pdf_stream_length_invalid_or_unbounded")
        stream_start = syntax.position + len(b"stream\n")
        stream_end = stream_start + length
        if data[stream_end:stream_end + len(b"\nendstream")] != b"\nendstream":
            raise ContentRejected("pdf_stream_length_mismatch")
        syntax.position = stream_end + len(b"\nendstream")
        syntax.skip_space()
    if data[syntax.position:syntax.position + 6] != b"endobj":
        raise ContentRejected("pdf_object_boundary_invalid")
    end = syntax.position + 6
    if end < len(data) and data[end] not in _PDF_WS:
        raise ContentRejected("pdf_object_boundary_invalid")
    return _Object(number, generation, value, stream_start, stream_end, end)


def _extract_text(
    data: bytes,
    obj: _Object,
    page_index: int,
    allowed_fonts: set[str],
) -> list[ParsedSegment]:
    assert obj.stream_start is not None and obj.stream_end is not None
    content = data[obj.stream_start:obj.stream_end]
    syntax = _Syntax(content)
    operands: list[Any] = []
    inside_text = False
    current_font: str | None = None
    strings: list[_String] = []
    signatures: dict[str, tuple[type, ...]] = {
        "BT": (), "ET": (), "Tf": (_Name, int), "Td": (int, int),
        "Tm": (int, int, int, int, int, int), "TL": (int,), "T*": (),
        "Tj": (_String,),
    }
    while True:
        syntax.skip_space()
        if syntax.position == len(content):
            break
        token = syntax.parse()
        if not isinstance(token, _Keyword):
            operands.append(token)
            if len(operands) > 6:
                raise ContentRejected("pdf_content_operand_bound_exceeded")
            continue
        signature = signatures.get(token.value)
        if signature is None or len(operands) != len(signature):
            raise ContentRejected("pdf_content_operator_outside_strict_profile")
        if any(type(value) is not expected for value, expected in zip(operands, signature)):
            raise ContentRejected("pdf_content_operand_invalid")
        if token.value == "BT":
            if inside_text:
                raise ContentRejected("pdf_text_object_invalid")
            inside_text = True
            current_font = None
        elif token.value == "ET":
            if not inside_text:
                raise ContentRejected("pdf_text_object_invalid")
            inside_text = False
        elif not inside_text:
            raise ContentRejected("pdf_text_operator_outside_text_object")
        if token.value == "Tf":
            font_name = operands[0].value
            if font_name not in allowed_fonts:
                raise ContentRejected("pdf_content_font_unresolved")
            current_font = font_name
        if token.value == "Tj":
            if current_font is None:
                raise ContentRejected("pdf_text_without_selected_font")
            strings.append(operands[0])
        operands = []
    if operands or inside_text:
        raise ContentRejected("pdf_text_content_incomplete")
    segments: list[ParsedSegment] = []
    for ordinal, string in enumerate(strings, start=1):
        text = " ".join(string.value.split())
        if not text:
            continue
        kind = "formula" if text.startswith("FORMULA:") else "text"
        if kind == "formula":
            text = text[len("FORMULA:"):].strip()
            if not text:
                raise ContentRejected("pdf_empty_formula")
        start = obj.stream_start + string.content_start
        end = obj.stream_start + string.content_end
        segments.append(ParsedSegment(
            segment_id=f"pdf-page-{page_index + 1}-object-{obj.number}-{obj.generation}-segment-{ordinal}",
            kind=kind,
            normalized_text=text,
            anchor=ByteAnchor.create(
                data, start, end, page_index=page_index,
                object_id=f"{obj.number} {obj.generation} obj",
            ),
            load_bearing=kind == "formula",
        ))
    return segments


def parse_strict_pdf(data: bytes) -> AdapterOutcome:
    """Parse the bounded subset, or raise ``ContentRejected`` without output."""

    _reject_cross_format_ambiguity(data, "pdf")
    entries, trailer, xref_offset = _read_xref(data)
    objects: dict[tuple[int, int], _Object] = {}
    occupied_offsets: set[int] = set()
    ordered_entries = sorted(entries.items(), key=lambda item: item[1])
    if not ordered_entries:
        raise ContentRejected("pdf_cross_reference_has_no_objects")
    header = re.match(rb"%PDF-1\.[0-7]\r?\n", data)
    assert header is not None
    prefix = _Syntax(data, header.end())
    prefix.skip_space()
    if prefix.position != ordered_entries[0][1]:
        raise ContentRejected("pdf_bytes_outside_cross_referenced_objects")
    for ordinal, (identity, offset) in enumerate(ordered_entries):
        if offset in occupied_offsets:
            raise ContentRejected("pdf_cross_reference_duplicate_offset")
        occupied_offsets.add(offset)
        obj = _read_object(data, offset)
        if (obj.number, obj.generation) != identity:
            raise ContentRejected("pdf_cross_reference_object_mismatch")
        next_offset = (
            ordered_entries[ordinal + 1][1]
            if ordinal + 1 < len(ordered_entries)
            else xref_offset
        )
        separator = _Syntax(data, obj.object_end)
        separator.skip_space()
        if separator.position != next_offset:
            raise ContentRejected("pdf_bytes_outside_cross_referenced_objects")
        objects[identity] = obj

    def resolve(reference: _Ref) -> _Object:
        try:
            return objects[(reference.number, reference.generation)]
        except KeyError as error:
            raise ContentRejected("pdf_indirect_reference_unresolved") from error

    catalog = resolve(_ref(trailer["Root"]))
    if catalog.stream_start is not None:
        raise ContentRejected("pdf_catalog_stream_forbidden")
    catalog_dict = _dictionary(catalog.value, {"Type", "Pages"})
    _name(catalog_dict["Type"], "Catalog")
    pages_ref = _ref(catalog_dict["Pages"])
    pages = resolve(pages_ref)
    pages_dict = _dictionary(pages.value, {"Type", "Kids", "Count"})
    _name(pages_dict["Type"], "Pages")
    kids = pages_dict["Kids"]
    count = pages_dict["Count"]
    if not isinstance(kids, list) or isinstance(count, bool) or not isinstance(count, int):
        raise ContentRejected("pdf_page_tree_invalid")
    if count != len(kids) or not 1 <= count <= _MAX_PAGES:
        raise ContentRejected("pdf_page_count_invalid_or_bounded")
    if len(set((item.number, item.generation) for item in kids if isinstance(item, _Ref))) != len(kids):
        raise ContentRejected("pdf_page_tree_duplicate_or_invalid_kid")

    used = {(catalog.number, catalog.generation), (pages.number, pages.generation)}
    segments: list[ParsedSegment] = []
    for page_index, kid in enumerate(kids):
        page = resolve(_ref(kid))
        used.add((page.number, page.generation))
        page_dict = _dictionary(
            page.value,
            {"Type", "Parent", "Contents", "Resources", "MediaBox"},
        )
        _name(page_dict["Type"], "Page")
        if _ref(page_dict["Parent"]) != pages_ref:
            raise ContentRejected("pdf_page_parent_invalid")
        content = resolve(_ref(page_dict["Contents"]))
        used.add((content.number, content.generation))
        if content.stream_start is None:
            raise ContentRejected("pdf_page_content_stream_required")
        media_box = page_dict["MediaBox"]
        if (
            not isinstance(media_box, list)
            or len(media_box) != 4
            or any(isinstance(value, bool) or not isinstance(value, int) for value in media_box)
            or media_box[0] >= media_box[2]
            or media_box[1] >= media_box[3]
        ):
            raise ContentRejected("pdf_media_box_invalid")
        resources = _dictionary(page_dict["Resources"], {"Font"})
        fonts = resources["Font"]
        if not isinstance(fonts, dict) or not fonts:
            raise ContentRejected("pdf_font_resources_invalid")
        allowed_fonts: set[str] = set()
        for font_name, font_ref in fonts.items():
            font = resolve(_ref(font_ref))
            used.add((font.number, font.generation))
            font_dict = _dictionary(font.value, {"Type", "Subtype", "BaseFont"})
            _name(font_dict["Type"], "Font")
            _name(font_dict["Subtype"], "Type1")
            if font_dict["BaseFont"] not in {_Name("Helvetica"), _Name("Times-Roman"), _Name("Courier")}:
                raise ContentRejected("pdf_font_outside_strict_profile")
            allowed_fonts.add(font_name)
        segments.extend(_extract_text(data, content, page_index, allowed_fonts))

    if set(objects) != used:
        raise ContentRejected("pdf_unreferenced_or_unsupported_object_forbidden")
    if not segments:
        raise ContentRejected("ocr_required_but_deferred")
    if len(segments) > PARSER_BOUNDS.max_segments:
        raise ContentRejected("segment_count_bound_exceeded")
    if sum(item.kind == "formula" for item in segments) > PARSER_BOUNDS.max_formulas:
        raise ContentRejected("formula_count_bound_exceeded")
    decoded_bytes = sum(len(item.normalized_text.encode("utf-8")) for item in segments)
    if decoded_bytes > PARSER_BOUNDS.max_decoded_output_bytes:
        raise ContentRejected("decoded_output_byte_bound_exceeded")
    if decoded_bytes > max(1, len(data)) * PARSER_BOUNDS.max_expansion_ratio:
        raise ContentRejected("decoded_output_expansion_ratio_exceeded")
    return AdapterOutcome(
        tuple(segments),
        warnings=("strict_valid_uncompressed_pdf_candidate",),
        transformations=("pdf_literal_escape_decode", "unicode_whitespace_collapse"),
    )
