from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from math_research.phase4b.parsing import (
    AdapterOutcome,
    ByteAnchor,
    ContentRejected,
    HTML_PROFILE,
    OCR_PROFILE,
    PARSER_ACTIVATION_STATUS,
    PARSER_BOUNDS,
    PDF_PROFILE,
    ParserDependencyMissing,
    ParseRequest,
    ParsedReference,
    ParsedSegment,
    RestrictedStdlibAdapter,
    TEX_PROFILE,
    TRUST_EFFECTS,
    OperationContext,
    compare_representations,
    run_parser,
    verify_result_record,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "phase4b" / "parsing"
SOURCE_ID = "source.synthetic.pythagorean.production.v1"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def request(name: str, profile=HTML_PROFILE, data: bytes | None = None) -> ParseRequest:
    original = fixture(name) if data is None else data
    return ParseRequest.create(
        request_id=f"request.{name}", source_id=SOURCE_ID,
        content_object_id=f"content.{name}", representation_id=f"representation.{name}",
        media_type=profile.media_type, profile_name=profile.name, original_bytes=original,
    )


class PreActivationFixtureOracleTests(unittest.TestCase):
    def test_stdlib_profile_is_explicitly_a_pre_activation_fixture_oracle(self) -> None:
        self.assertEqual("fixture_oracle_only", PARSER_ACTIVATION_STATUS)
        entry_gate = (ROOT / "docs" / "phase-4b" / "ENTRY_GATE_REPORT.md").read_text("utf-8")
        self.assertIn("implementation evidence pending", entry_gate)

    def assert_anchors(self, result, original: bytes) -> None:
        self.assertTrue(result.segments)
        for segment in result.segments:
            anchor = segment.anchor
            self.assertEqual(
                "sha256:" + hashlib.sha256(original).hexdigest(), anchor.original_sha256
            )
            self.assertEqual(
                "sha256:" + hashlib.sha256(original[anchor.start:anchor.end]).hexdigest(),
                anchor.slice_sha256,
            )

    def test_named_html_profile_produces_only_an_untrusted_candidate(self) -> None:
        parse_request = request("authoritative.html")
        result = run_parser(parse_request)
        self.assertEqual("candidate_proposal", result.disposition)
        self.assertIsNone(result.failure_code)
        self.assertEqual(TRUST_EFFECTS, result.semantic_record()["trust_effects"])
        self.assertEqual(["x^2 + y^2 = z^2"], [
            item.normalized_text for item in result.segments if item.kind == "formula"
        ])
        self.assert_anchors(result, parse_request.original_bytes)

    def test_named_nonexecuting_tex_profile_never_compiles(self) -> None:
        parse_request = request("nonexecuting.tex", TEX_PROFILE)
        result = run_parser(parse_request)
        self.assertEqual("candidate_proposal", result.disposition)
        self.assertEqual(("tex_lexical_whitespace_collapse",), result.transformations)
        self.assertEqual(["x^2 + y^2 = z^2"], [
            item.normalized_text for item in result.segments if item.kind == "formula"
        ])
        self.assert_anchors(result, parse_request.original_bytes)

    def test_named_born_digital_pdf_profile_has_byte_page_and_object_anchors(self) -> None:
        parse_request = request("born-digital.pdf", PDF_PROFILE)
        result = run_parser(parse_request)
        self.assertEqual("candidate_proposal", result.disposition)
        self.assertEqual(["x^2 + y^2 = 1"], [
            item.normalized_text for item in result.segments if item.kind == "formula"
        ])
        self.assertTrue(all(item.anchor.page_index == 0 for item in result.segments))
        self.assertTrue(all(item.anchor.object_id == "4 0 obj" for item in result.segments))
        self.assert_anchors(result, parse_request.original_bytes)

    def test_profile_identity_has_parser_profile_version_policy_and_environment_hashes(self) -> None:
        identity = run_parser(request("authoritative.html")).parser_identity
        self.assertEqual("adaivy-restricted-stdlib", identity["adapter_name"])
        self.assertEqual("1.0.0", identity["adapter_version"])
        self.assertEqual(HTML_PROFILE.name, identity["profile_name"])
        self.assertEqual(HTML_PROFILE.version, identity["profile_version"])
        for field in (
            "adapter_implementation_sha256", "dependency_environment_sha256",
            "policy_sha256", "profile_sha256",
        ):
            self.assertRegex(identity[field], r"^sha256:[0-9a-f]{64}$")

    def test_all_normative_parser_bounds_are_in_every_semantic_record(self) -> None:
        expected = {
            "max_raw_input_bytes": 2_097_152,
            "max_decoded_output_bytes": 8_388_608,
            "max_expansion_ratio": 20,
            "max_wall_seconds": 30,
            "max_memory_bytes": 536_870_912,
            "max_temp_bytes": 67_108_864,
            "max_processes": 16,
            "max_open_files": 64,
            "max_segments": 4_096,
            "max_formulas": 2_048,
            "max_references": 2_048,
            "max_nesting_depth": 128,
            "max_warnings": 16_384,
            "max_transformations": 64,
            "max_anchor_page_index": 1_000_000,
            "max_anchor_object_id_bytes": 256,
        }
        self.assertEqual(expected, PARSER_BOUNDS.to_record())
        self.assertEqual(expected, run_parser(request("authoritative.html")).semantic_record()["bounds"])

    def test_admitted_warning_is_bounded_and_does_not_change_candidate_status(self) -> None:
        data = b"<html><body><!-- retained warning --><p>x</p></body></html>"
        result = run_parser(request("warning.html", data=data))
        self.assertEqual("candidate_proposal", result.disposition)
        self.assertEqual(("html_comment_ignored",), result.warnings)


class StrictRecordAndHashTests(unittest.TestCase):
    @staticmethod
    def _rehash(record: dict) -> None:
        record["semantic_sha256"] = "sha256:" + hashlib.sha256(
            json.dumps(record["semantic"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        record["operational"]["semantic_sha256"] = record["semantic_sha256"]
        record["operational_sha256"] = "sha256:" + hashlib.sha256(
            json.dumps(record["operational"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def test_request_record_rejects_unknown_fields_and_lineage_mismatch(self) -> None:
        parse_request = request("authoritative.html")
        raw = parse_request.to_record()
        with self.assertRaisesRegex(ValueError, "fields"):
            ParseRequest.from_record(dict(raw, surprise=True), parse_request.original_bytes)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            ParseRequest.from_record(dict(raw, original_sha256="sha256:" + "0" * 64), parse_request.original_bytes)

    def test_result_envelope_is_strict_and_recomputes_both_hashes(self) -> None:
        parse_request = request("authoritative.html")
        result = run_parser(parse_request)
        record = result.to_record()
        verify_result_record(record, parse_request.original_bytes)
        with self.assertRaisesRegex(ValueError, "fields"):
            verify_result_record(dict(record, surprise=True), parse_request.original_bytes)
        forged = json.loads(json.dumps(record))
        forged["semantic"]["warnings"].append("forged")
        with self.assertRaisesRegex(ValueError, "semantic hash mismatch"):
            verify_result_record(forged, parse_request.original_bytes)

    def test_semantic_hash_excludes_operational_variation(self) -> None:
        parse_request = request("authoritative.html")
        first = run_parser(
            parse_request,
            operation=OperationContext.create("operation.one", duration_ms=1, stdout=b"one"),
        )
        second = run_parser(
            parse_request,
            operation=OperationContext.create("operation.two", duration_ms=29, stdout=b"two"),
        )
        self.assertEqual(first.semantic_sha256, second.semantic_sha256)
        self.assertNotEqual(first.operational_sha256, second.operational_sha256)

    def test_anchor_forgery_is_detected_with_original_bytes(self) -> None:
        parse_request = request("authoritative.html")
        record = run_parser(parse_request).to_record()
        forged = json.loads(json.dumps(record))
        forged["semantic"]["segments"][0]["anchor"]["slice_sha256"] = "sha256:" + "0" * 64
        forged["semantic_sha256"] = "sha256:" + hashlib.sha256(
            json.dumps(forged["semantic"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        forged["operational"]["semantic_sha256"] = forged["semantic_sha256"]
        forged["operational_sha256"] = "sha256:" + hashlib.sha256(
            json.dumps(forged["operational"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "slice hash mismatch"):
            verify_result_record(forged, parse_request.original_bytes)

    def test_self_rehashed_status_content_and_exit_contradictions_are_rejected(self) -> None:
        parse_request = request("authoritative.html")
        candidate = run_parser(parse_request).to_record()
        hostile_request = request("hostile.html")
        quarantined = run_parser(hostile_request).to_record()
        ocr_request = request("ocr.pgm", OCR_PROFILE, fixture("scanned-image.pgm"))
        not_invoked = run_parser(ocr_request).to_record()
        cases = []
        changed = json.loads(json.dumps(candidate))
        changed["operational"]["adapter_status"] = "failed"
        cases.append((changed, parse_request.original_bytes))
        changed = json.loads(json.dumps(candidate))
        changed["operational"]["operation"]["worker_exit_code"] = 1
        cases.append((changed, parse_request.original_bytes))
        changed = json.loads(json.dumps(quarantined))
        changed["operational"]["adapter_status"] = "completed"
        cases.append((changed, hostile_request.original_bytes))
        changed = json.loads(json.dumps(quarantined))
        changed["semantic"]["warnings"] = ["contradictory_content"]
        cases.append((changed, hostile_request.original_bytes))
        changed = json.loads(json.dumps(not_invoked))
        changed["semantic"]["failure_code"] = "different_failure"
        cases.append((changed, ocr_request.original_bytes))
        changed = json.loads(json.dumps(not_invoked))
        changed["operational"]["operation"]["worker_exit_code"] = 0
        cases.append((changed, ocr_request.original_bytes))
        for changed, original in cases:
            with self.subTest(
                disposition=changed["semantic"]["disposition"],
                status=changed["operational"]["adapter_status"],
            ):
                self._rehash(changed)
                with self.assertRaises(ValueError):
                    verify_result_record(changed, original)


class HostileAndFailureTests(unittest.TestCase):
    def assert_quarantine(self, parse_request: ParseRequest, reason: str) -> None:
        result = run_parser(parse_request)
        self.assertEqual("quarantined", result.disposition)
        self.assertEqual(reason, result.failure_code)
        self.assertEqual((), result.segments)
        self.assertEqual(parse_request.original_sha256, result.semantic_record()["original_lineage"]["sha256"])

    def test_hostile_html_tex_and_pdf_are_retained_as_quarantines(self) -> None:
        self.assert_quarantine(
            request("hostile.html"), "html_active_content_forbidden"
        )
        self.assert_quarantine(
            request("hostile.tex", TEX_PROFILE), "tex_active_or_expanding_command_forbidden"
        )
        self.assert_quarantine(
            request("hostile.pdf", PDF_PROFILE), "pdf_active_or_embedded_content_forbidden"
        )

    def test_structural_cross_format_envelopes_quarantine_before_proposal(self) -> None:
        valid_pdf = fixture("strict-born-digital-valid.pdf")
        html_pdf = b"<html><body><!--\n" + valid_pdf + b"--><p>x</p></body></html>"
        html_tex = (
            b"<html><body><!--\n\\section{Hidden}\n$x+y$\n--><p>x</p></body></html>"
        )
        tex_html = b"\\section{Result}\n$x$\n<html><body><p>hidden</p></body></html>"
        tex_pdf = b"\\section{Result}\n$x$\n" + valid_pdf
        cases = (
            (request("polyglot-html-pdf.html", data=html_pdf),),
            (request("polyglot-html-tex.html", data=html_tex),),
            (request("polyglot-tex-html.tex", TEX_PROFILE, tex_html),),
            (request("polyglot-tex-pdf.tex", TEX_PROFILE, tex_pdf),),
            (request("pdf-claimed-html.html", data=valid_pdf),),
            (request("html-claimed-tex.tex", TEX_PROFILE, b"<html><body><p>x</p></body></html>"),),
        )
        for (parse_request,) in cases:
            with self.subTest(request=parse_request.request_id):
                self.assert_quarantine(parse_request, "cross_format_envelope_ambiguity")

    def test_format_words_and_isolated_math_notation_are_not_polyglot_evidence(self) -> None:
        html = (
            b"<html><body><p>The strings %PDF-1.4, startxref, and \\section are labels; "
            b"the equation $x+y$ is ordinary text.</p></body></html>"
        )
        result = run_parser(request("ordinary-format-words.html", data=html))
        self.assertEqual("candidate_proposal", result.disposition)

    def test_processing_instruction_meta_refresh_active_attribute_and_external_url_reject(self) -> None:
        cases = (
            (b"<?xml version='1.0'?><html><body><p>x</p></body></html>", "html_processing_instruction_forbidden"),
            (b'<html><head><meta http-equiv="refresh" content="0;url=https://bad.invalid"></head><body><p>x</p></body></html>', "html_meta_refresh_forbidden"),
            (b'<html><body><p onclick="steal()">x</p></body></html>', "html_active_attribute_forbidden"),
            (b'<html><body><p href="https://bad.invalid">x</p></body></html>', "html_external_reference_forbidden"),
        )
        for index, (data, reason) in enumerate(cases):
            with self.subTest(reason=reason):
                self.assert_quarantine(request(f"generated-{index}.html", data=data), reason)

    def test_tex_include_definition_and_deep_nesting_reject(self) -> None:
        for index, data in enumerate((b"\\input{secret}", b"\\def\\x{y}", b"{" * 129 + b"x" + b"}" * 129)):
            result = run_parser(request(f"hostile-generated-{index}.tex", TEX_PROFILE, data))
            self.assertEqual("quarantined", result.disposition)
        self.assertEqual(
            "nesting_depth_bound_exceeded",
            run_parser(request("deep.tex", TEX_PROFILE, b"{" * 129 + b"x" + b"}" * 129)).failure_code,
        )

    def test_pdf_action_encryption_filter_and_malformed_cross_reference_reject(self) -> None:
        documents = (
            (b"%PDF-1.4\n1 0 obj\n<< /Encrypt 2 0 R >>\nendobj\n%%EOF", "pdf_active_or_embedded_content_forbidden"),
            (b"%PDF-1.4\n1 0 obj\n<< /Filter /FlateDecode >>\nendobj\n%%EOF", "pdf_compressed_stream_outside_profile"),
            (b"%PDF-1.4\nxref\n0 1\n%%EOF", "pdf_cross_reference_invalid"),
        )
        for index, (data, reason) in enumerate(documents):
            with self.subTest(reason=reason):
                self.assert_quarantine(request(f"hostile-generated-{index}.pdf", PDF_PROFILE, data), reason)

    def test_image_only_pdf_and_explicit_ocr_request_are_machine_readable_deferred_outcomes(self) -> None:
        scanned = b"%PDF-1.4\n1 0 obj\n<< /Subtype /Image >>\nendobj\n%%EOF"
        self.assert_quarantine(
            request("scanned.pdf", PDF_PROFILE, scanned), "ocr_required_but_deferred"
        )
        ocr_request = request("ocr.pgm", OCR_PROFILE, fixture("scanned-image.pgm"))
        result = run_parser(ocr_request)
        self.assertEqual("failed", result.disposition)
        self.assertEqual("ocr_deferred", result.failure_code)
        self.assertEqual("not_invoked", result.adapter_status)


class _MissingAdapter:
    name = "future-missing-parser"
    version = "0.0.0"
    implementation_sha256 = "sha256:" + "1" * 64
    dependency_environment_sha256 = "sha256:" + "2" * 64

    def supports(self, profile) -> bool:
        return True

    def parse(self, parse_request) -> AdapterOutcome:
        raise ParserDependencyMissing("future-parser-wheel")


class _InjectedAdapter:
    name = "future-injected-parser"
    version = "9.9.9"
    implementation_sha256 = "sha256:" + "3" * 64
    dependency_environment_sha256 = "sha256:" + "4" * 64

    def __init__(self, outcome: AdapterOutcome):
        self.outcome = outcome

    def supports(self, profile) -> bool:
        return True

    def parse(self, parse_request) -> AdapterOutcome:
        return self.outcome


class AdapterAndBoundsTests(unittest.TestCase):
    def base_segment(self, parse_request: ParseRequest, text: str = "x") -> ParsedSegment:
        return ParsedSegment(
            "segment.injected.1", "formula", text,
            ByteAnchor.create(parse_request.original_bytes, 0, 1), True,
        )

    def test_missing_dependency_is_retained_without_fabricated_content(self) -> None:
        parse_request = request("authoritative.html")
        result = run_parser(parse_request, adapter=_MissingAdapter())
        self.assertEqual("failed", result.disposition)
        self.assertEqual("missing_dependency:future-parser-wheel", result.failure_code)
        self.assertEqual("missing_dependency", result.adapter_status)
        self.assertEqual((), result.segments)

    def test_replaceable_injected_adapter_cannot_bypass_anchor_validation(self) -> None:
        parse_request = request("authoritative.html")
        valid = run_parser(
            parse_request,
            adapter=_InjectedAdapter(AdapterOutcome((self.base_segment(parse_request),))),
        )
        self.assertEqual("candidate_proposal", valid.disposition)
        forged_anchor = replace(
            self.base_segment(parse_request).anchor, slice_sha256="sha256:" + "0" * 64
        )
        forged = replace(self.base_segment(parse_request), anchor=forged_anchor)
        rejected = run_parser(
            parse_request, adapter=_InjectedAdapter(AdapterOutcome((forged,)))
        )
        self.assertEqual("quarantined", rejected.disposition)
        self.assertEqual("anchor_slice_hash_mismatch", rejected.failure_code)

    def test_empty_adapter_output_and_expansion_are_quarantined(self) -> None:
        parse_request = request("authoritative.html")
        empty = run_parser(parse_request, adapter=_InjectedAdapter(AdapterOutcome(())))
        self.assertEqual("empty_parse_proposal", empty.failure_code)
        huge = self.base_segment(parse_request, "x" * (len(parse_request.original_bytes) * 21))
        expanded = run_parser(
            parse_request, adapter=_InjectedAdapter(AdapterOutcome((huge,)))
        )
        self.assertEqual("decoded_output_expansion_ratio_exceeded", expanded.failure_code)

    def test_formula_reference_warning_and_segment_count_bounds_fail_closed(self) -> None:
        parse_request = request("authoritative.html")
        anchor = ByteAnchor.create(parse_request.original_bytes, 0, 1)
        formula = ParsedSegment("segment.formula", "formula", "x", anchor, True)
        too_many_formulas = tuple(replace(formula, segment_id=f"segment.formula.{i}") for i in range(PARSER_BOUNDS.max_formulas + 1))
        self.assertEqual(
            "formula_count_bound_exceeded",
            run_parser(parse_request, adapter=_InjectedAdapter(AdapterOutcome(too_many_formulas))).failure_code,
        )
        reference = ParsedReference("reference.1", "target", anchor)
        too_many_references = tuple(replace(reference, reference_id=f"reference.{i}") for i in range(PARSER_BOUNDS.max_references + 1))
        self.assertEqual(
            "reference_count_bound_exceeded",
            run_parser(
                parse_request,
                adapter=_InjectedAdapter(AdapterOutcome((formula,), too_many_references)),
            ).failure_code,
        )
        warnings = tuple(f"warning-{i}" for i in range(PARSER_BOUNDS.max_warnings + 1))
        self.assertEqual(
            "warning_count_bound_exceeded",
            run_parser(
                parse_request, adapter=_InjectedAdapter(AdapterOutcome((formula,), warnings=warnings))
            ).failure_code,
        )
        too_many_segments = tuple(
            replace(formula, segment_id=f"segment.text.{i}", kind="text", load_bearing=False)
            for i in range(PARSER_BOUNDS.max_segments + 1)
        )
        self.assertEqual(
            "segment_count_bound_exceeded",
            run_parser(parse_request, adapter=_InjectedAdapter(AdapterOutcome(too_many_segments))).failure_code,
        )

    def test_worker_semantic_identity_and_load_bearing_mismatches_fail_closed(self) -> None:
        parse_request = request("authoritative.html")
        anchor = ByteAnchor.create(parse_request.original_bytes, 0, 1)
        with self.assertRaisesRegex(ValueError, "load-bearing"):
            ParsedSegment("segment.bad", "text", "x", anchor, True)
        segment = ParsedSegment("segment.same", "text", "x", anchor, False)
        result = run_parser(
            parse_request,
            adapter=_InjectedAdapter(AdapterOutcome((segment, segment))),
        )
        self.assertEqual("duplicate_segment_identity", result.failure_code)
        reference = ParsedReference("reference.same", "target", anchor)
        result = run_parser(
            parse_request,
            adapter=_InjectedAdapter(AdapterOutcome((segment,), (reference, reference))),
        )
        self.assertEqual("duplicate_reference_identity", result.failure_code)

    def test_transformations_and_anchor_metadata_are_bounded(self) -> None:
        parse_request = request("authoritative.html")
        segment = self.base_segment(parse_request)
        transformations = tuple(
            f"transform-{index}" for index in range(PARSER_BOUNDS.max_transformations + 1)
        )
        result = run_parser(
            parse_request,
            adapter=_InjectedAdapter(AdapterOutcome((segment,), transformations=transformations)),
        )
        self.assertEqual("transformation_count_bound_exceeded", result.failure_code)
        for anchor, reason in (
            (replace(segment.anchor, page_index=PARSER_BOUNDS.max_anchor_page_index + 1), "anchor_page_index_invalid"),
            (replace(segment.anchor, object_id="x" * (PARSER_BOUNDS.max_anchor_object_id_bytes + 1)), "anchor_object_id_invalid"),
        ):
            with self.subTest(reason=reason):
                result = run_parser(
                    parse_request,
                    adapter=_InjectedAdapter(AdapterOutcome((replace(segment, anchor=anchor),))),
                )
                self.assertEqual(reason, result.failure_code)

    def test_raw_input_at_bound_is_valid_and_one_over_fails(self) -> None:
        at_limit = b"x" * PARSER_BOUNDS.max_raw_input_bytes
        parse_request = request("limit.html", data=at_limit)
        self.assertEqual(PARSER_BOUNDS.max_raw_input_bytes, parse_request.original_byte_length)
        with self.assertRaisesRegex(ValueError, "raw_input_byte_bound_exceeded"):
            request("over.html", data=at_limit + b"x")

    def test_wall_time_and_nonzero_worker_outcomes_fail_closed(self) -> None:
        parse_request = request("authoritative.html")
        timeout = run_parser(
            parse_request,
            operation=OperationContext.create(
                "operation.timeout", duration_ms=PARSER_BOUNDS.max_wall_seconds * 1_000 + 1
            ),
        )
        self.assertEqual("parser_wall_time_bound_exceeded", timeout.failure_code)
        nonzero = run_parser(
            parse_request,
            operation=OperationContext.create("operation.nonzero", worker_exit_code=9),
        )
        self.assertEqual("parser_worker_nonzero_exit", nonzero.failure_code)


class RepresentationComparisonTests(unittest.TestCase):
    def test_equal_candidate_text_is_not_trust_promotion(self) -> None:
        html = run_parser(request("authoritative.html"))
        tex = run_parser(request("nonexecuting.tex", TEX_PROFILE))
        comparison = compare_representations(html, tex)
        self.assertEqual("candidate_text_equal", comparison["comparison"])
        self.assertEqual("none", comparison["trust_effect"])
        self.assertFalse(comparison["quarantine_required"])

    def test_disagreement_and_failed_empty_comparison_fail_closed(self) -> None:
        html = run_parser(request("authoritative.html"))
        pdf = run_parser(request("born-digital.pdf", PDF_PROFILE))
        disagreement = compare_representations(html, pdf)
        self.assertEqual("disagreement", disagreement["comparison"])
        self.assertTrue(disagreement["quarantine_required"])
        failed = run_parser(request("hostile.html"))
        unavailable = compare_representations(failed, failed)
        self.assertEqual("not_comparable", unavailable["comparison"])
        self.assertTrue(unavailable["quarantine_required"])


if __name__ == "__main__":
    unittest.main()
