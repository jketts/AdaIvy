from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from spikes.phase4b_parsing.parser_spike import (
    BOUNDS,
    compare_representations,
    ingest_ocr_candidate,
    parse_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "phase4b" / "parsing"
SOURCE_ID = "source.synthetic.pythagorean.v1"


def read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def parse(name: str, media_type: str) -> dict:
    return parse_candidate(
        source_id=SOURCE_ID,
        representation_id=f"representation.{name}",
        media_type=media_type,
        original=read(name),
    )


class ParserContractTests(unittest.TestCase):
    def assert_exact_source_spans(self, record: dict, original: bytes) -> None:
        for segment in record["segments"]:
            span = segment["original_byte_span"]
            self.assertIsNotNone(span)
            raw = original[span["start"] : span["end"]]
            self.assertEqual(
                "sha256:" + hashlib.sha256(raw).hexdigest(),
                segment["original_slice_sha256"],
            )

    def test_authoritative_html_is_a_candidate_with_exact_byte_lineage(self) -> None:
        original = read("authoritative.html")
        record = parse("authoritative.html", "text/html")
        self.assertEqual("accepted_candidate", record["status"])
        self.assertNotIn(record["status"], {"verified", "accepted_evidence"})
        self.assertEqual(len(original), record["original_lineage"]["byte_length"])
        self.assertEqual(
            "sha256:" + hashlib.sha256(original).hexdigest(),
            record["original_lineage"]["sha256"],
        )
        self.assertEqual(
            ["x^2 + y^2 = z^2"],
            [item["normalized_text"] for item in record["segments"] if item["kind"] == "formula"],
        )
        self.assert_exact_source_spans(record, original)

    def test_nonexecuting_tex_is_lexed_without_expansion(self) -> None:
        original = read("nonexecuting.tex")
        record = parse("nonexecuting.tex", "application/x-tex")
        self.assertEqual("accepted_candidate", record["status"])
        self.assertEqual([], record["warnings"])
        self.assertEqual(
            ["x^2 + y^2 = z^2"],
            [item["normalized_text"] for item in record["segments"] if item["kind"] == "formula"],
        )
        self.assert_exact_source_spans(record, original)

    def test_restricted_born_digital_pdf_preserves_literal_spans(self) -> None:
        original = read("born-digital.pdf")
        record = parse("born-digital.pdf", "application/pdf")
        self.assertEqual("accepted_candidate", record["status"])
        self.assertEqual(["restricted_uncompressed_pdf_profile"], record["warnings"])
        self.assertEqual(
            ["x^2 + y^2 = 1"],
            [item["normalized_text"] for item in record["segments"] if item["kind"] == "formula"],
        )
        self.assert_exact_source_spans(record, original)

    def test_ocr_output_is_captured_but_has_no_claimed_original_text_span(self) -> None:
        original = read("scanned-image.pgm")
        candidate = read("scanned-image.ocr.txt")
        record = ingest_ocr_candidate(
            source_id=SOURCE_ID,
            representation_id="representation.scanned-image.ocr",
            original=original,
            candidate=candidate,
        )
        self.assertEqual("quarantined", record["status"])
        self.assertEqual("ocr_requires_independent_review", record["quarantine_reason"])
        self.assertEqual(["no_exact_original_text_span"], record["warnings"])
        self.assertTrue(record["segments"])
        self.assertTrue(all(item["original_byte_span"] is None for item in record["segments"]))
        self.assertEqual(
            "sha256:" + hashlib.sha256(original).hexdigest(),
            record["original_lineage"]["sha256"],
        )
        self.assertEqual(
            "sha256:" + hashlib.sha256(candidate).hexdigest(),
            record["candidate_lineage"]["sha256"],
        )

    def test_representation_agreement_does_not_verify_and_disagreement_quarantines(self) -> None:
        html = parse("authoritative.html", "text/html")
        tex = parse("nonexecuting.tex", "application/x-tex")
        pdf = parse("born-digital.pdf", "application/pdf")
        agreement = compare_representations(html, tex)
        disagreement = compare_representations(html, pdf)
        self.assertEqual("identical_candidate_text", agreement["agreement"])
        self.assertFalse(agreement["quarantine_required"])
        self.assertEqual("disagreement", disagreement["agreement"])
        self.assertTrue(disagreement["quarantine_required"])

    def test_two_quarantined_empty_representations_cannot_agree(self) -> None:
        left = parse("hostile.html", "text/html")
        right = parse("hostile.html", "text/html")
        comparison = compare_representations(left, right)
        self.assertEqual("not_comparable", comparison["agreement"])
        self.assertEqual("quarantined", comparison["comparison_status"])
        self.assertEqual(
            "representation_not_accepted_candidate", comparison["quarantine_reason"]
        )
        self.assertTrue(comparison["quarantine_required"])

    def test_accepted_text_only_representations_cannot_agree_on_empty_formula_sets(self) -> None:
        value = b"<html><body><p>Text only</p></body></html>"
        left = parse_candidate(
            source_id=SOURCE_ID,
            representation_id="representation.text-only.left",
            media_type="text/html",
            original=value,
        )
        right = dict(left, representation_id="representation.text-only.right")
        comparison = compare_representations(left, right)
        self.assertEqual("not_comparable", comparison["agreement"])
        self.assertEqual("formula_missing", comparison["quarantine_reason"])


class HostileInputTests(unittest.TestCase):
    def test_hostile_html_is_quarantined(self) -> None:
        record = parse("hostile.html", "text/html")
        self.assertEqual("quarantined", record["status"])
        self.assertEqual("html_active_content_forbidden", record["quarantine_reason"])
        self.assertEqual([], record["segments"])

    def test_hostile_tex_is_quarantined_before_any_expansion(self) -> None:
        record = parse("hostile.tex", "application/x-tex")
        self.assertEqual("quarantined", record["status"])
        self.assertEqual("tex_active_or_expanding_command_forbidden", record["quarantine_reason"])
        self.assertEqual([], record["segments"])

    def test_hostile_pdf_is_quarantined(self) -> None:
        record = parse("hostile.pdf", "application/pdf")
        self.assertEqual("quarantined", record["status"])
        self.assertEqual("pdf_active_or_embedded_content_forbidden", record["quarantine_reason"])
        self.assertEqual([], record["segments"])

    def test_html_processing_instruction_is_quarantined(self) -> None:
        record = parse_candidate(
            source_id=SOURCE_ID,
            representation_id="representation.processing-instruction.html",
            media_type="text/html",
            original=b"<?xml version='1.0'?><html><body><p>x</p></body></html>",
        )
        self.assertEqual("html_processing_instruction_forbidden", record["quarantine_reason"])

    def test_html_meta_refresh_is_quarantined(self) -> None:
        record = parse_candidate(
            source_id=SOURCE_ID,
            representation_id="representation.meta-refresh.html",
            media_type="text/html",
            original=(
                b'<html><head><meta http-equiv="refresh" content="0;url=https://attacker.invalid">'
                b"</head><body><p>x</p></body></html>"
            ),
        )
        self.assertEqual("html_meta_refresh_forbidden", record["quarantine_reason"])

    def test_unknown_and_active_html_attributes_are_quarantined(self) -> None:
        cases = (
            (b'<html><body><p mystery="1">x</p></body></html>', "html_attribute_outside_profile"),
            (b'<html><body><p onclick="steal()">x</p></body></html>', "html_active_attribute_forbidden"),
            (b'<html><body><p href="javascript:steal()">x</p></body></html>', "html_external_reference_forbidden"),
        )
        for index, (value, reason) in enumerate(cases):
            with self.subTest(reason=reason):
                record = parse_candidate(
                    source_id=SOURCE_ID,
                    representation_id=f"representation.attribute-{index}.html",
                    media_type="text/html",
                    original=value,
                )
                self.assertEqual(reason, record["quarantine_reason"])

    def test_empty_tex_formula_cannot_be_admitted(self) -> None:
        record = parse_candidate(
            source_id=SOURCE_ID,
            representation_id="representation.empty-formula.tex",
            media_type="application/x-tex",
            original=b"\\[   \\]",
        )
        self.assertEqual("empty_segment_forbidden", record["quarantine_reason"])


class BoundTests(unittest.TestCase):
    def parse_html_bytes(self, value: bytes) -> dict:
        return parse_candidate(
            source_id=SOURCE_ID,
            representation_id="representation.generated.html",
            media_type="text/html",
            original=value,
        )

    def test_input_byte_bound_fails_closed(self) -> None:
        record = self.parse_html_bytes(b"x" * (BOUNDS["max_input_bytes"] + 1))
        self.assertEqual("input_byte_bound_exceeded", record["quarantine_reason"])

    def test_ocr_candidate_byte_bound_fails_closed(self) -> None:
        record = ingest_ocr_candidate(
            source_id=SOURCE_ID,
            representation_id="representation.oversized.ocr",
            original=b"P2\n1 1\n255\n0\n",
            candidate=b"x" * (BOUNDS["max_candidate_bytes"] + 1),
        )
        self.assertEqual("candidate_byte_bound_exceeded", record["quarantine_reason"])
        self.assertEqual([], record["segments"])

    def test_single_segment_byte_bound_fails_closed(self) -> None:
        value = b"<html><body><p>" + b"x" * (BOUNDS["max_segment_bytes"] + 1) + b"</p></body></html>"
        record = self.parse_html_bytes(value)
        self.assertEqual("segment_bound_exceeded", record["quarantine_reason"])

    def test_segment_count_bound_fails_closed(self) -> None:
        value = b"<html><body>" + b"<p>x</p>" * (BOUNDS["max_segments"] + 1) + b"</body></html>"
        record = self.parse_html_bytes(value)
        self.assertEqual("segment_count_bound_exceeded", record["quarantine_reason"])

    def test_formula_count_bound_fails_closed(self) -> None:
        value = b"<html><body>" + b"<math>x</math>" * (BOUNDS["max_formulas"] + 1) + b"</body></html>"
        record = self.parse_html_bytes(value)
        self.assertEqual("formula_count_bound_exceeded", record["quarantine_reason"])

    def test_warning_count_bound_fails_closed(self) -> None:
        commands = "\n".join(
            "\\unknown" + chr(ord("a") + index)
            for index in range(BOUNDS["max_warnings"] + 1)
        )
        record = parse_candidate(
            source_id=SOURCE_ID,
            representation_id="representation.generated.tex",
            media_type="application/x-tex",
            original=(commands + "\n\\[x=y\\]\n").encode(),
        )
        self.assertEqual("warning_bound_exceeded", record["quarantine_reason"])

    def test_output_byte_bound_fails_closed(self) -> None:
        paragraph = b"<p>" + b"x" * 700 + b"</p>"
        value = b"<html><body>" + paragraph * 20 + b"</body></html>"
        record = self.parse_html_bytes(value)
        self.assertEqual("output_byte_bound_exceeded", record["quarantine_reason"])
        self.assertEqual([], record["segments"])

    def test_success_output_is_bounded_and_deterministic(self) -> None:
        first = parse("authoritative.html", "text/html")
        second = parse("authoritative.html", "text/html")
        encoded = json.dumps(first, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(first, second)
        self.assertLessEqual(len(encoded), BOUNDS["max_output_bytes"])


if __name__ == "__main__":
    unittest.main()
