"""Focused adversarial tests for the exact-source parser worker candidate."""

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

from math_research.phase4b.exact_parser_worker import (
    CANDIDATE_SANDBOX_CONTRACT,
    ExactSourceParserWorker,
    IMPLEMENTATION_SHA256,
    IMPLEMENTATION_SOURCE_PATH,
    parse_exact_html,
    parse_exact_tex,
)
from math_research.phase4b.parsing import (
    ContentRejected,
    HTML_PROFILE,
    PARSER_BOUNDS,
    PDF_PROFILE,
    ParseRequest,
    TEX_PROFILE,
    run_production_parser,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures" / "phase4b"


def _request(name: str, profile, data: bytes) -> ParseRequest:
    return ParseRequest.create(
        request_id=f"request.exact.{name}",
        source_id="source.exact-candidate",
        content_object_id=f"content.exact.{name}",
        representation_id=f"representation.exact.{name}",
        media_type=profile.media_type,
        profile_name=profile.name,
        original_bytes=data,
    )


class ExactHTMLCandidateTests(unittest.TestCase):
    def test_fixture_segments_have_exact_source_byte_anchors(self) -> None:
        original = (FIXTURES / "parsing" / "authoritative.html").read_bytes()
        outcome = parse_exact_html(original)
        self.assertGreaterEqual(len(outcome.segments), 3)
        self.assertTrue(any(item.kind == "formula" for item in outcome.segments))
        for segment in outcome.segments:
            segment.anchor.validate(original)
            raw = original[segment.anchor.start:segment.anchor.end].decode("utf-8")
            self.assertEqual(segment.normalized_text, " ".join(raw.split()))

    def test_multibyte_utf8_offsets_are_byte_not_character_offsets(self) -> None:
        original = "<html><body><p>α  β</p><math><mi>γ²</mi></math></body></html>".encode()
        outcome = parse_exact_html(original)
        alpha, formula = outcome.segments
        self.assertEqual(original[alpha.anchor.start:alpha.anchor.end], "α  β".encode())
        self.assertEqual(original[formula.anchor.start:formula.anchor.end], "γ²".encode())
        self.assertEqual(alpha.normalized_text, "α β")
        self.assertEqual(formula.kind, "formula")

    def test_warning_hostile_malformed_and_ambiguous_inputs_fail_closed(self) -> None:
        warning = (FIXTURES / "acceptance" / "parsing" / "warning.html").read_bytes()
        self.assertEqual(parse_exact_html(warning).warnings, ("html_comment_ignored",))
        cases = (
            ((FIXTURES / "parsing" / "hostile.html").read_bytes(), "html_active_content_forbidden"),
            ((FIXTURES / "acceptance" / "parsing" / "malformed.html").read_bytes(), "html_unbalanced_structure"),
            (b"<html><body><p>&copy;</p></body></html>", "html_entity_reference_outside_profile"),
            (b"<html><body><p onclick=\"x()\">x</p></body></html>", "html_active_attribute_forbidden"),
            (b"<html><body><!-- never closes", "html_unterminated_comment"),
            (b"<html><body><p a=\"1\" a=\"2\">x</p></body></html>", "html_duplicate_attribute"),
            (b"<html><body><p>x</p></body></html><html><body><p>y</p></body></html>", "html_root_structure_invalid"),
        )
        for value, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ContentRejected, f"^{reason}$"):
                    parse_exact_html(value)

    def test_ignored_comment_cannot_hide_a_structurally_valid_pdf_or_tex_envelope(self) -> None:
        pdf = (FIXTURES / "parsing" / "strict-born-digital-valid.pdf").read_bytes()
        cases = (
            b"<html><body><!--\n" + pdf + b"--><p>x</p></body></html>",
            b"<html><body><!--" + pdf + b"--><p>x</p></body></html>",
            b"<html><body><!--\n\\section{Hidden}\n$x+y$\n--><p>x</p></body></html>",
            b"<html><body><!--\\section{Hidden}\n$x+y$--><p>x</p></body></html>",
        )
        for value in cases:
            with self.assertRaisesRegex(ContentRejected, "^cross_format_envelope_ambiguity$"):
                parse_exact_html(value)

    def test_format_words_and_isolated_formula_are_not_an_envelope(self) -> None:
        value = (
            b"<html><body><p>%PDF-1.4 and startxref are names; "
            b"\\section and $x+y$ are mathematical prose.</p></body></html>"
        )
        self.assertTrue(parse_exact_html(value).segments)

    def test_nesting_and_segment_limits_reject_one_over(self) -> None:
        at_limit = b"<html><body>" + b"<div>" * (PARSER_BOUNDS.max_nesting_depth - 3)
        at_limit += b"<p>x</p>" + b"</div>" * (PARSER_BOUNDS.max_nesting_depth - 3)
        at_limit += b"</body></html>"
        self.assertEqual(len(parse_exact_html(at_limit).segments), 1)
        over = b"<html><body>" + b"<div>" * (PARSER_BOUNDS.max_nesting_depth - 2)
        over += b"<p>x</p>" + b"</div>" * (PARSER_BOUNDS.max_nesting_depth - 2)
        over += b"</body></html>"
        with self.assertRaisesRegex(ContentRejected, "nesting_depth_bound_exceeded"):
            parse_exact_html(over)
        too_many = b"<html><body>" + b"<p>x</p>" * (PARSER_BOUNDS.max_segments + 1)
        too_many += b"</body></html>"
        with self.assertRaisesRegex(ContentRejected, "segment_count_bound_exceeded"):
            parse_exact_html(too_many)


class ExactTeXCandidateTests(unittest.TestCase):
    def test_fixture_formula_and_heading_have_exact_anchors(self) -> None:
        original = (FIXTURES / "parsing" / "nonexecuting.tex").read_bytes()
        outcome = parse_exact_tex(original)
        self.assertEqual(
            [(item.kind, item.normalized_text) for item in outcome.segments],
            [("text", "Pythagorean identity"), ("formula", "x^2 + y^2 = z^2")],
        )
        for segment in outcome.segments:
            segment.anchor.validate(original)

    def test_multibyte_tex_offsets_and_unknown_command_warning(self) -> None:
        original = "\\section{Δ result}\n\\mystery{token}\n$α + β = γ$\n".encode()
        outcome = parse_exact_tex(original)
        self.assertEqual(outcome.warnings, ("unknown_tex_command:mystery",))
        heading, formula = outcome.segments
        self.assertEqual(original[heading.anchor.start:heading.anchor.end], "Δ result".encode())
        self.assertEqual(original[formula.anchor.start:formula.anchor.end], "α + β = γ".encode())

    def test_hostile_malformed_comments_and_formula_dialects_fail_closed(self) -> None:
        cases = (
            ((FIXTURES / "parsing" / "hostile.tex").read_bytes(), "tex_active_or_expanding_command_forbidden"),
            ((FIXTURES / "acceptance" / "parsing" / "malformed.tex").read_bytes(), "tex_unbalanced_group"),
            (b"\\section{x} % ambiguous comment\n$x$", "tex_comments_outside_profile"),
            (b"\\section{x}\n$unterminated", "tex_unterminated_formula"),
            (b"\\section{x}\n$$display$$", "tex_display_dollar_outside_profile"),
            (b"\\section{x}\n\\input{other.tex}", "tex_active_or_expanding_command_forbidden"),
        )
        for value, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ContentRejected, f"^{reason}$"):
                    parse_exact_tex(value)

    def test_group_depth_accepts_limit_and_rejects_one_over(self) -> None:
        at_limit = b"{" * PARSER_BOUNDS.max_nesting_depth + b"}" * PARSER_BOUNDS.max_nesting_depth
        at_limit += b"\\section{x}"
        self.assertEqual(len(parse_exact_tex(at_limit).segments), 1)
        over = b"{" * (PARSER_BOUNDS.max_nesting_depth + 1)
        over += b"}" * (PARSER_BOUNDS.max_nesting_depth + 1) + b"\\section{x}"
        with self.assertRaisesRegex(ContentRejected, "nesting_depth_bound_exceeded"):
            parse_exact_tex(over)

    def test_formula_count_and_warning_size_fail_before_unbounded_output(self) -> None:
        formulas = b"\\section{x}\n" + b"$x$" * (PARSER_BOUNDS.max_formulas + 1)
        with self.assertRaisesRegex(ContentRejected, "formula_count_bound_exceeded"):
            parse_exact_tex(formulas)
        long_command = b"\\section{x}\n\\" + b"a" * 300
        with self.assertRaisesRegex(ContentRejected, "warning_invalid"):
            parse_exact_tex(long_command)

    def test_html_and_structural_pdf_envelopes_are_reciprocally_ambiguous(self) -> None:
        pdf = (FIXTURES / "parsing" / "strict-born-digital-valid.pdf").read_bytes()
        cases = (
            b"\\section{Result}\n$x$\n<html><body><p>hidden</p></body></html>",
            b"\\section{Result}\n$x$\n" + pdf,
        )
        for value in cases:
            with self.assertRaisesRegex(ContentRejected, "^cross_format_envelope_ambiguity$"):
                parse_exact_tex(value)


class ExactWorkerBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.worker = ExactSourceParserWorker()

    def test_direct_worker_is_deterministic_and_pdf_fails_closed(self) -> None:
        html = (FIXTURES / "parsing" / "authoritative.html").read_bytes()
        request = _request("html", HTML_PROFILE, html)
        first = self.worker.execute(request)
        second = self.worker.execute(request)
        self.assertEqual(first, second)
        self.assertEqual(first.status, "completed")
        self.assertIsNotNone(first.outcome)

        pdf = (FIXTURES / "parsing" / "born-digital.pdf").read_bytes()
        rejected = self.worker.execute(_request("pdf", PDF_PROFILE, pdf))
        self.assertEqual(rejected.status, "content_rejected")
        self.assertEqual(rejected.failure_code, "pdf_exact_source_mapping_unsupported")
        self.assertIsNone(rejected.outcome)

    def test_implementation_identity_is_bound_to_shipped_source_bytes(self) -> None:
        source = IMPLEMENTATION_SOURCE_PATH.read_bytes()
        expected = "sha256:" + hashlib.sha256(source).hexdigest()
        changed = "sha256:" + hashlib.sha256(source + b"\n# behavior changed").hexdigest()
        self.assertEqual(IMPLEMENTATION_SHA256, expected)
        self.assertEqual(self.worker.implementation_sha256, expected)
        self.assertNotEqual(changed, expected)

    def test_candidate_cannot_cross_production_boundary_without_os_sandbox(self) -> None:
        self.assertEqual(
            self.worker.sandbox_contract,
            CANDIDATE_SANDBOX_CONTRACT,
        )
        original = (FIXTURES / "parsing" / "nonexecuting.tex").read_bytes()
        result = run_production_parser(
            _request("tex", TEX_PROFILE, original), worker=self.worker
        )
        self.assertEqual(result.disposition, "failed")
        self.assertTrue(result.failure_code.startswith("worker_boundary_failure:"))
        self.assertEqual(result.segments, ())
        self.assertEqual(result.references, ())


if __name__ == "__main__":
    unittest.main()
