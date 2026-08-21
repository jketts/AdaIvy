"""Executable evidence for the remaining exact Phase 4B thresholds."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from math_research.phase4b.acquisition import (
    AcquisitionPolicy, AcquisitionPolicyError, AcquisitionRequest,
    AuthorizedResource, Resolution, RightsDecision, RobotsSnapshot,
    RunAuthorization, TermsSnapshot, TransportRequest, TransportResponse,
    acquire,
)
from math_research.phase4b.content_store import Phase4BContentStore
from math_research.phase4b.corpus_authorization import run_parser_corpus_authorization
from math_research.phase4b.parsing import (
    AdapterOutcome, ByteAnchor, HTML_PROFILE, PARSER_BOUNDS, ParseRequest,
    ParsedReference, ParsedSegment, run_parser,
)
from math_research.phase4b.serialization import canonical_hash, sha256_bytes
from math_research.phase4b.threshold_evidence import (
    EXPECTED_ACQUISITION_FAILURES, EXPECTED_PARSER_QUARANTINES,
    deleted_marker_evidence, exact_reason_evidence,
    production_dependency_evidence, resource_and_spend_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = 200_000
START = "https://papers.example/start"
INTERNAL = "https://internal.example/final"
PUBLIC_A = "93.184.216.34"
PUBLIC_B = "8.8.8.8"


class _Clock:
    def __init__(self) -> None:
        self.value = 0

    def now_milliseconds(self) -> int:
        current = self.value
        self.value += 1_000
        return current


class _Resolver:
    def __init__(self, values: dict[str, tuple[str, ...]]) -> None:
        self.values = values

    def resolve(self, hostname: str) -> Resolution:
        return Resolution(hostname, self.values[hostname])


class _Transport:
    def __init__(self, response: TransportResponse) -> None:
        self.response = response

    def fetch(self, _request: TransportRequest) -> TransportResponse:
        return self.response


def _response(
    *, status: int = 200, body: bytes = b"fixture", peer: str = PUBLIC_A,
    location: str | None = None,
) -> TransportResponse:
    headers = (
        (("location", location),) if location is not None
        else (("content-type", "text/html"),)
    )
    return TransportResponse(status, headers, body, peer, 1)


def _acquisition_failure(case_id: str) -> str:
    policy = AcquisitionPolicy()
    origins = ["https://papers.example"]
    urls = [START]
    response = _response()
    addresses = {"papers.example": (PUBLIC_A,), "internal.example": ("127.0.0.1",)}
    network_enabled = True
    terms_captured = NOW
    robots_valid = True
    robots_allowed = True
    omitted_right: str | None = None
    if case_id.endswith("denied-missing-run-authority"):
        network_enabled = False
    elif case_id.endswith("denied-robots-disallow"):
        robots_allowed = False
    elif case_id.endswith("denied-robots-unavailable"):
        robots_valid = False
    elif case_id.endswith("denied-changed-terms"):
        terms_captured = NOW - policy.max_snapshot_age_seconds - 1
    elif case_id.endswith("denied-acquisition-right"):
        omitted_right = "acquisition"
    elif case_id.endswith("denied-retention-right"):
        omitted_right = "storage_and_retention"
    elif case_id.endswith("denied-special-use-redirect"):
        origins.append("https://internal.example")
        urls.append(INTERNAL)
        response = _response(status=302, body=b"", location=INTERNAL)
    elif case_id.endswith("denied-peer-mismatch"):
        response = _response(peer=PUBLIC_B)
    elif case_id.endswith("denied-response-budget"):
        policy = AcquisitionPolicy(max_body_bytes=4)
        response = _response(body=b"12345")
    else:
        raise AssertionError(f"unknown negative acquisition fixture: {case_id}")
    authorization = RunAuthorization(
        "run.threshold-reasons", "human.owner", "human", "human_final",
        "capability.phase4b.thresholds", "acquire_https", network_enabled,
        policy.content_hash, tuple(origins), (AuthorizedResource("request.1", START),),
    )
    rights = tuple(
        RightsDecision(
            f"rights.{index}.{use}", authorization.run_id, url, use, "allowed",
            "human", "human_final", NOW - 1, NOW + 1,
        )
        for index, url in enumerate(urls)
        for use in ("acquisition", "storage_and_retention")
        if use != omitted_right
    )
    terms = tuple(
        TermsSnapshot(
            f"terms.{index}", origin, "a" * 64, terms_captured, True, True,
        )
        for index, origin in enumerate(origins)
    )
    robots = tuple(
        RobotsSnapshot(
            f"robots.{index}", url, "b" * 64, NOW, robots_valid, robots_allowed,
        )
        for index, url in enumerate(urls)
    )
    try:
        result = acquire(
            (AcquisitionRequest(
                authorization.run_id, "request.1", authorization.actor_id, START,
            ),),
            authorization=authorization, policy=policy, rights=rights,
            terms=terms, robots=robots, resolver=_Resolver(addresses),
            transport=_Transport(response), start_clock=_Clock(), now_epoch=NOW,
            recorded_at_epoch=NOW,
        )
    except AcquisitionPolicyError as error:
        return str(error)
    semantic = json.loads(result.semantic_bytes)
    return str(semantic["results"][0]["reason"])


class ExactReasonEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.parser_report = run_parser_corpus_authorization(ROOT)

    def test_all_required_negative_fixtures_have_exact_execution_reasons(self) -> None:
        acquisition = {
            case_id: _acquisition_failure(case_id)
            for case_id in EXPECTED_ACQUISITION_FAILURES
        }
        parser = {
            item["case_id"]: item["failure_code"]
            for item in self.parser_report["cases"]
            if item["case_id"] in EXPECTED_PARSER_QUARANTINES
        }
        evidence = exact_reason_evidence(
            acquisition_failures=acquisition, parser_quarantines=parser,
        )
        self.assertEqual("passed", evidence["status"])
        self.assertEqual(15, evidence["exact_matches"])
        self.assertEqual(15, evidence["required_matches"])
        supplied = evidence["content_hash"]
        preimage = dict(evidence)
        preimage.pop("content_hash")
        self.assertEqual(supplied, canonical_hash(preimage))

    def test_missing_extra_or_wrong_reason_cannot_report_full_accuracy(self) -> None:
        exact_acquisition = dict(EXPECTED_ACQUISITION_FAILURES)
        exact_parser = dict(EXPECTED_PARSER_QUARANTINES)
        missing = dict(exact_acquisition)
        missing.pop(next(iter(missing)))
        with self.assertRaisesRegex(ValueError, "identities differ"):
            exact_reason_evidence(
                acquisition_failures=missing, parser_quarantines=exact_parser,
            )
        wrong = dict(exact_parser)
        wrong[next(iter(wrong))] = "generic_quarantine"
        evidence = exact_reason_evidence(
            acquisition_failures=exact_acquisition, parser_quarantines=wrong,
        )
        self.assertEqual("failed", evidence["status"])
        self.assertEqual(14, evidence["exact_matches"])


class DeletedMarkerEvidenceTests(unittest.TestCase):
    MARKER = b"ADAIVY_PHASE4B_DELETE_MARKER_7f3d9c2a"

    def test_complete_managed_workspace_scan_passes_only_after_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_id = "source.threshold-deletion"
            with Phase4BContentStore(root / "phase4b-content") as content:
                content.publish(
                    source_id, self.MARKER + b"\n",
                    expected_hash=sha256_bytes(self.MARKER + b"\n"),
                )
                for relative in (
                    "cache/empty.cache", "index/empty.fts", "exports/post-delete.json",
                    "logs/phase4b.log", "workspace.sqlite3", "workspace.sqlite3-wal",
                    "workspace.sqlite3-shm", "workspace.sqlite3-journal",
                ):
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"non-reconstructive metadata")
                before = deleted_marker_evidence(root, self.MARKER)
                self.assertEqual("failed", before["status"])
                self.assertEqual(1, before["unique_matching_files"])
                self.assertEqual(
                    1, before["store_classes"]["managed_content"]["marker_matches"],
                )
                self.assertEqual(
                    1,
                    before["store_classes"]["reconstructive_plaintext"]["marker_matches"],
                )
                content.remove(source_id)
                content.verify_absent(source_id)
                after = deleted_marker_evidence(root, self.MARKER)
                self.assertEqual("passed", after["status"])
                self.assertEqual(0, after["unique_matching_files"])
                self.assertTrue(all(
                    item["marker_matches"] == 0
                    for item in after["store_classes"].values()
                ))
                supplied = after["content_hash"]
                preimage = dict(after)
                preimage.pop("content_hash")
                self.assertEqual(supplied, canonical_hash(preimage))

    def test_every_named_managed_store_class_is_detected_and_scan_is_fail_closed(self) -> None:
        paths = {
            "cache": "cache/leak.bin",
            "index": "index/leak.fts",
            "export": "exports/leak.json",
            "temp": "temp/leak.bin",
            "sqlite_and_journal": "workspace.sqlite3-wal",
            "log": "logs/leak.log",
        }
        for store_class, relative in paths.items():
            with self.subTest(store_class=store_class), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(self.MARKER)
                evidence = deleted_marker_evidence(root, self.MARKER)
                self.assertEqual("failed", evidence["status"])
                self.assertEqual(
                    1, evidence["store_classes"][store_class]["marker_matches"],
                )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "real").write_bytes(b"safe")
            (root / "link").symlink_to(root / "real")
            with self.assertRaisesRegex(ValueError, "symlink"):
                deleted_marker_evidence(root, self.MARKER)


class _InjectedAdapter:
    name = "threshold-injected-parser"
    version = "1.0.0"
    implementation_sha256 = "sha256:" + "1" * 64
    dependency_environment_sha256 = "sha256:" + "2" * 64

    def __init__(self, outcome: AdapterOutcome) -> None:
        self.outcome = outcome

    def supports(self, _profile: object) -> bool:
        return True

    def parse(self, _request: ParseRequest) -> AdapterOutcome:
        return self.outcome


def _request(data: bytes) -> ParseRequest:
    return ParseRequest.create(
        request_id="request.threshold-bounds", source_id="source.threshold-bounds",
        content_object_id="content.threshold-bounds",
        representation_id="representation.threshold-bounds",
        media_type=HTML_PROFILE.media_type, profile_name=HTML_PROFILE.name,
        original_bytes=data,
    )


class ExactParserBoundEvidenceTests(unittest.TestCase):
    def test_decoded_absolute_and_expansion_bounds_pass_exactly_and_fail_one_over(self) -> None:
        absolute_request = _request(b"a" * 419_431)
        anchor = ByteAnchor.create(absolute_request.original_bytes, 0, 1)
        exact = ParsedSegment(
            "segment.absolute", "text",
            "x" * PARSER_BOUNDS.max_decoded_output_bytes, anchor, False,
        )
        result = run_parser(
            absolute_request, adapter=_InjectedAdapter(AdapterOutcome((exact,))),
        )
        self.assertEqual("candidate_proposal", result.disposition)
        over = replace(exact, normalized_text=exact.normalized_text + "x")
        result = run_parser(
            absolute_request, adapter=_InjectedAdapter(AdapterOutcome((over,))),
        )
        self.assertEqual("decoded_output_byte_bound_exceeded", result.failure_code)

        ratio_request = _request(b"a" * 1_024)
        ratio_anchor = ByteAnchor.create(ratio_request.original_bytes, 0, 1)
        ratio_bytes = 1_024 * PARSER_BOUNDS.max_expansion_ratio
        exact_ratio = ParsedSegment(
            "segment.ratio", "text", "x" * ratio_bytes, ratio_anchor, False,
        )
        self.assertEqual(
            "candidate_proposal",
            run_parser(
                ratio_request,
                adapter=_InjectedAdapter(AdapterOutcome((exact_ratio,))),
            ).disposition,
        )
        result = run_parser(
            ratio_request,
            adapter=_InjectedAdapter(AdapterOutcome((
                replace(exact_ratio, normalized_text=exact_ratio.normalized_text + "x"),
            ))),
        )
        self.assertEqual("decoded_output_expansion_ratio_exceeded", result.failure_code)

    def test_all_parse_collections_pass_together_at_their_exact_limits(self) -> None:
        parse_request = _request(b"a" * 1_024)
        anchor = ByteAnchor.create(parse_request.original_bytes, 0, 1)
        formulas = tuple(
            ParsedSegment(f"segment.formula.{index}", "formula", "x", anchor, True)
            for index in range(PARSER_BOUNDS.max_formulas)
        )
        text = tuple(
            ParsedSegment(f"segment.text.{index}", "text", "x", anchor, False)
            for index in range(PARSER_BOUNDS.max_segments - len(formulas))
        )
        references = tuple(
            ParsedReference(f"reference.{index}", "x", anchor)
            for index in range(PARSER_BOUNDS.max_references)
        )
        warnings = tuple("w" for _ in range(PARSER_BOUNDS.max_warnings))
        result = run_parser(
            parse_request,
            adapter=_InjectedAdapter(AdapterOutcome(
                formulas + text, references, warnings=warnings,
            )),
        )
        self.assertEqual("candidate_proposal", result.disposition)
        self.assertEqual(PARSER_BOUNDS.max_segments, len(result.segments))
        self.assertEqual(
            PARSER_BOUNDS.max_formulas,
            sum(item.kind == "formula" for item in result.segments),
        )
        self.assertEqual(PARSER_BOUNDS.max_references, len(result.references))
        self.assertEqual(PARSER_BOUNDS.max_warnings, len(result.warnings))

    def test_resource_and_zero_spend_evidence_is_exact_and_closed(self) -> None:
        evidence = resource_and_spend_evidence(external_spend_microusd=0)
        self.assertEqual(8_388_608, evidence["decoded_output_bytes"])
        self.assertEqual(20, evidence["expansion_ratio"])
        self.assertEqual(4_096, evidence["segments"])
        self.assertEqual(2_048, evidence["formulas"])
        self.assertEqual(2_048, evidence["references"])
        self.assertEqual(128, evidence["nesting_depth"])
        self.assertEqual(16_384, evidence["warnings"])
        self.assertEqual(1_800_000, evidence["acquisition_run_wall_milliseconds"])
        self.assertEqual(0, evidence["external_spend_microusd"])
        with self.assertRaisesRegex(ValueError, "must equal zero"):
            resource_and_spend_evidence(external_spend_microusd=1)


class EmptyProductionDependencyEvidenceTests(unittest.TestCase):
    def test_phase4b_has_exactly_empty_production_dependency_evidence(self) -> None:
        evidence = production_dependency_evidence(
            ROOT / "src/math_research/phase4b", ROOT / "pyproject.toml",
        )
        self.assertEqual("passed", evidence["status"])
        self.assertEqual([], evidence["declared_runtime_dependencies"])
        self.assertEqual([], evidence["third_party_imports"])
        self.assertEqual([], evidence["dynamic_third_party_loads"])
        self.assertEqual([], evidence["dependency_wheel_hash_license_inventory"])
        self.assertEqual(0, evidence["mismatches"])

    def test_undeclared_import_or_declared_runtime_dependency_blocks_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "phase4b"
            shutil.copytree(ROOT / "src/math_research/phase4b", source)
            (source / "undeclared.py").write_text("import requests\n", "utf-8")
            evidence = production_dependency_evidence(source, ROOT / "pyproject.toml")
            self.assertEqual("failed", evidence["status"])
            self.assertEqual("requests", evidence["third_party_imports"][0]["module"])


if __name__ == "__main__":
    unittest.main()
