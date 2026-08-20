from __future__ import annotations

from pathlib import Path
import hashlib
import unittest

from math_research.phase4b.parsing import PDF_PROFILE, ParseRequest, run_parser
from math_research.phase4b.pdf_exact_candidate import (
    IMPLEMENTATION_SHA256,
    IMPLEMENTATION_SOURCE_PATH,
    StrictBornDigitalPdfAdapter,
)


ROOT = Path(__file__).resolve().parents[1]
VALID_FIXTURE = ROOT / "fixtures" / "phase4b" / "parsing" / "strict-born-digital-valid.pdf"


def _build_pdf(
    *,
    content: bytes = (
        b"BT\n/F1 12 Tf\n72 720 Td\n(Pythagorean identity) Tj\n"
        b"0 -18 Td\n(FORMULA:x^2 + y^2 = 1) Tj\nET"
    ),
    catalog_extra: bytes = b"",
    stream_extra: bytes = b"",
    trailer_extra: bytes = b"",
    extra_objects: tuple[bytes, ...] = (),
    declared_length: int | None = None,
) -> bytes:
    length = len(content) if declared_length is None else declared_length
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R" + catalog_extra + b" >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> /MediaBox [0 0 612 792] >>"
        ),
        b"<< /Length " + str(length).encode("ascii") + stream_extra + b" >>\nstream\n"
        + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        *extra_objects,
    ]
    data = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_offset = len(data)
    data += b"xref\n0 " + str(len(objects) + 1).encode("ascii") + b"\n"
    data += b"0000000000 65535 f \n"
    for offset in offsets:
        data += f"{offset:010d} 00000 n \n".encode("ascii")
    data += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode("ascii")
        + b" /Root 1 0 R" + trailer_extra + b" >>\nstartxref\n"
        + str(xref_offset).encode("ascii") + b"\n%%EOF\n"
    )
    return data


def _request(data: bytes) -> ParseRequest:
    return ParseRequest.create(
        request_id="request.strict-pdf.v1",
        source_id="source.strict-pdf.v1",
        content_object_id="content.strict-pdf.v1",
        representation_id="representation.strict-pdf.v1",
        media_type="application/pdf",
        profile_name=PDF_PROFILE.name,
        original_bytes=data,
    )


class StrictBornDigitalPdfCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = StrictBornDigitalPdfAdapter()

    def assert_quarantined(self, data: bytes, reason: str) -> None:
        result = run_parser(_request(data), adapter=self.adapter)
        self.assertEqual("quarantined", result.disposition)
        self.assertEqual(reason, result.failure_code)
        self.assertEqual((), result.segments)

    def test_project_fixture_is_valid_deterministic_and_exactly_anchored(self) -> None:
        data = VALID_FIXTURE.read_bytes()
        self.assertEqual(_build_pdf(), data)
        first = run_parser(_request(data), adapter=self.adapter)
        second = run_parser(_request(data), adapter=self.adapter)
        self.assertEqual("candidate_proposal", first.disposition)
        self.assertEqual(first.semantic_sha256, second.semantic_sha256)
        self.assertEqual(
            [("text", "Pythagorean identity"), ("formula", "x^2 + y^2 = 1")],
            [(item.kind, item.normalized_text) for item in first.segments],
        )
        self.assertEqual(
            [b"Pythagorean identity", b"FORMULA:x^2 + y^2 = 1"],
            [data[item.anchor.start:item.anchor.end] for item in first.segments],
        )
        for item in first.segments:
            item.anchor.validate(data)
            self.assertEqual(0, item.anchor.page_index)
            self.assertEqual("4 0 obj", item.anchor.object_id)

    def test_escape_decoding_retains_the_exact_literal_payload_bytes(self) -> None:
        data = _build_pdf(content=b"BT\n/F1 12 Tf\n(A\\(B\\) C) Tj\nET")
        result = run_parser(_request(data), adapter=self.adapter)
        self.assertEqual("candidate_proposal", result.disposition)
        self.assertEqual("A(B) C", result.segments[0].normalized_text)
        anchor = result.segments[0].anchor
        self.assertEqual(b"A\\(B\\) C", data[anchor.start:anchor.end])

    def test_adapter_identity_is_bound_to_the_shipped_candidate_source(self) -> None:
        source = IMPLEMENTATION_SOURCE_PATH.read_bytes()
        expected = "sha256:" + hashlib.sha256(source).hexdigest()
        self.assertEqual(expected, IMPLEMENTATION_SHA256)
        self.assertEqual(expected, self.adapter.implementation_sha256)
        self.assertNotEqual(expected, "sha256:" + hashlib.sha256(source + b"changed").hexdigest())

    def test_acceptance_ordinary_fixture_is_the_valid_strict_subset(self) -> None:
        data = (ROOT / "fixtures" / "phase4b" / "parsing" / "born-digital.pdf").read_bytes()
        result = run_parser(_request(data), adapter=self.adapter)
        self.assertEqual("candidate_proposal", result.disposition)
        self.assertEqual(2, len(result.segments))
        self.assertEqual("strict_valid_uncompressed_pdf_candidate", result.warnings[0])

    def test_actions_encryption_compression_and_object_streams_fail_closed(self) -> None:
        cases = (
            (
                _build_pdf(
                    catalog_extra=b" /OpenAction 6 0 R",
                    extra_objects=(b"<< /S /JavaScript /JS (ignored) >>",),
                ),
                "pdf_active_or_embedded_content_forbidden",
            ),
            (_build_pdf(trailer_extra=b" /Encrypt 6 0 R"), "pdf_active_or_embedded_content_forbidden"),
            (_build_pdf(stream_extra=b" /Filter /FlateDecode"), "pdf_compressed_stream_outside_profile"),
            (
                _build_pdf(extra_objects=(b"<< /Type /ObjStm /N 0 /First 0 /Length 0 >>\nstream\n\nendstream",)),
                "pdf_active_or_embedded_content_forbidden",
            ),
        )
        for data, reason in cases:
            with self.subTest(reason=reason):
                self.assert_quarantined(data, reason)

    def test_html_and_tex_envelopes_inside_valid_pdf_structure_are_ambiguous(self) -> None:
        html = _build_pdf(
            content=b"BT\n/F1 12 Tf\n(<html><body><p>hidden</p></body></html>) Tj\nET",
        )
        tex = _build_pdf(
            content=b"\\section{Hidden}\n$x+y$\nBT\n/F1 12 Tf\n(text) Tj\nET",
        )
        for data in (html, tex):
            self.assert_quarantined(data, "cross_format_envelope_ambiguity")

    def test_malformed_cross_reference_stream_length_and_revision_fail_closed(self) -> None:
        damaged_xref = _build_pdf().replace(b"0000000009 00000 n", b"0000000010 00000 n", 1)
        appended_revision = _build_pdf() + b"startxref\n0\n%%EOF\n"
        cases = (
            (damaged_xref, "pdf_bytes_outside_cross_referenced_objects"),
            (_build_pdf(declared_length=86), "pdf_stream_length_mismatch"),
            (appended_revision, "pdf_incremental_or_ambiguous_revision_forbidden"),
        )
        for data, reason in cases:
            with self.subTest(reason=reason):
                self.assert_quarantined(data, reason)

    def test_unsupported_operators_hex_strings_and_unreferenced_objects_fail_closed(self) -> None:
        cases = (
            (_build_pdf(content=b"BT\n(hello) TJ\nET"), "pdf_content_operator_outside_strict_profile"),
            (_build_pdf(content=b"BT\n<6869> Tj\nET"), "pdf_syntax_outside_strict_profile"),
            (_build_pdf(extra_objects=(b"<< /Type /Metadata >>",)), "pdf_unreferenced_or_unsupported_object_forbidden"),
        )
        for data, reason in cases:
            with self.subTest(reason=reason):
                self.assert_quarantined(data, reason)

    def test_image_only_or_empty_text_is_deferred_to_ocr(self) -> None:
        self.assert_quarantined(_build_pdf(content=b"BT\nET"), "ocr_required_but_deferred")


if __name__ == "__main__":
    unittest.main()
