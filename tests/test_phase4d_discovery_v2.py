"""Acceptance tests for paginated, budgeted, policy-authorized discovery (ADR-0081)."""

from __future__ import annotations

from contextlib import redirect_stdout
import copy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from math_research.phase4b.acquisition import (
    AcquisitionPolicyError, Resolution, TransportRequest, TransportResponse,
)
from math_research.phase4b.live_transport import LiveNetworkPermit
from math_research.phase4b.serialization import canonical_bytes, canonical_hash
from math_research.phase4d.discovery_v2 import (
    CAPABILITY_ID_V2, CONFIG_HASH_V2, dry_run_v2, load_config_v2, sweep,
    verify_report_v2,
)
from math_research.phase4d.policy import (
    authorize_policy, build_policy, ground_query, validate_policy,
)
from math_research.phase4d.providers import request_url
from math_research.phase4d_cli import main as phase4d_main

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/phase4d-public-discovery-v2.json"
SOURCE = (
    b"Minimum-error quantum state discrimination uses a spectral projector "
    b"over an exact Gram matrix."
)
SOURCES = {"problem.statement": SOURCE}
TERMS = ("quantum state discrimination", "spectral projector")
QUERY_TEXT = "quantum state discrimination spectral projector"
ADDRESSES = {
    "api.crossref.org": "93.184.216.34",
    "api.openalex.org": "104.18.6.192",
    "export.arxiv.org": "128.84.21.199",
}
ALL_ORIGINS = (
    "https://api.crossref.org", "https://api.openalex.org",
    "https://export.arxiv.org",
)


def policy_for(
    providers: tuple[str, ...], *, max_requests: int = 8,
    max_response_bytes: int = 33_554_432, max_candidates: int = 1_000,
) -> dict:
    return build_policy(
        grounding_sources=SOURCES, provider_allowlist=list(providers),
        max_requests=max_requests, max_response_bytes=max_response_bytes,
        max_candidates=max_candidates, max_queries=4,
    )


def permit_for(origins: tuple[str, ...]) -> LiveNetworkPermit:
    return LiveNetworkPermit(
        "run.discovery-v2.test", "human.researcher", "human", "human_final",
        CAPABILITY_ID_V2, origins, True,
    )


class FakeResolver:
    def __init__(self, permit: LiveNetworkPermit) -> None:
        self.permit = permit
        self.calls: list[str] = []

    def resolve(self, hostname: str) -> Resolution:
        self.calls.append(hostname)
        return Resolution(hostname, (ADDRESSES[hostname],))


class FakeClock:
    def __init__(self) -> None:
        self.value = 0

    def now_milliseconds(self) -> int:
        self.value += 10
        return self.value


class FakeSleeper:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.sleeps: list[int] = []

    def sleep_milliseconds(self, milliseconds: int) -> None:
        self.sleeps.append(milliseconds)
        self.clock.value += milliseconds


def crossref_body(start: int, count: int, next_cursor: str | None) -> bytes:
    message: dict = {
        "items": [
            {
                "DOI": f"10.1000/work.{start + index}",
                "title": [f"Crossref work {start + index}"],
                "publisher": "Open Research Press",
                "type": "journal-article",
            }
            for index in range(count)
        ],
    }
    if next_cursor is not None:
        message["next-cursor"] = next_cursor
    return canonical_bytes({"status": "ok", "message": message})


def openalex_body(start: int, count: int, next_cursor: str | None) -> bytes:
    return canonical_bytes({
        "results": [
            {
                "id": f"https://openalex.org/W{10_000 + start + index}",
                "display_name": f"OpenAlex work {start + index}",
                "type": "article",
            }
            for index in range(count)
        ],
        "meta": {"next_cursor": next_cursor},
    })


def arxiv_body(start: int, count: int) -> bytes:
    entries = "".join(
        f"<entry><id>http://arxiv.org/abs/2408.{10_000 + start + index}v1</id>"
        f"<title>arXiv work {start + index}</title></entry>"
        for index in range(count)
    )
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom">' + entries + "</feed>"
    ).encode("utf-8")


class FakeTransport:
    """Routes each URL by provider and cursor; every page is deterministic."""

    def __init__(self, permit: LiveNetworkPermit, pages: dict[str, tuple[str, bytes]]) -> None:
        self.permit = permit
        self.pages = pages
        self.requests: list[TransportRequest] = []

    def fetch(self, request: TransportRequest) -> TransportRequest:
        self.requests.append(request)
        content_type, body = self.pages[request.url]
        return TransportResponse(
            200, (("content-type", content_type),), body,
            request.connect_addresses[0], 1,
        )


def full_sweep_pages(config: dict) -> dict[str, tuple[str, bytes]]:
    providers = config["providers"]
    pages: dict[str, tuple[str, bytes]] = {}
    crossref = providers["crossref"]
    pages[request_url("crossref", crossref, QUERY_TEXT, "*")] = (
        "application/json", crossref_body(0, 50, "CR2"),
    )
    pages[request_url("crossref", crossref, QUERY_TEXT, "CR2")] = (
        "application/json", crossref_body(50, 50, "CR3"),
    )
    pages[request_url("crossref", crossref, QUERY_TEXT, "CR3")] = (
        "application/json", crossref_body(100, 30, None),
    )
    openalex = providers["openalex"]
    pages[request_url("openalex", openalex, QUERY_TEXT, "*")] = (
        "application/json", openalex_body(0, 50, "OA2"),
    )
    pages[request_url("openalex", openalex, QUERY_TEXT, "OA2")] = (
        "application/json", openalex_body(50, 50, None),
    )
    arxiv = providers["arxiv"]
    pages[request_url("arxiv", arxiv, QUERY_TEXT, "0")] = (
        "application/atom+xml", arxiv_body(0, 50),
    )
    pages[request_url("arxiv", arxiv, QUERY_TEXT, "50")] = (
        "application/atom+xml", arxiv_body(50, 50),
    )
    pages[request_url("arxiv", arxiv, QUERY_TEXT, "100")] = (
        "application/atom+xml", arxiv_body(100, 20),
    )
    return pages


OBSERVED_AT = 1_787_800_000  # within thirty days of terms_reviewed_at 2026-08-22


class DiscoveryV2ConfigTests(unittest.TestCase):
    def test_config_is_pinned_and_fails_closed(self) -> None:
        config = load_config_v2(CONFIG.read_bytes())
        self.assertEqual(CONFIG_HASH_V2, config["content_hash"])
        self.assertFalse(config["credentials_allowed"])
        changed = copy.deepcopy(config)
        changed["max_requests_per_run"] = 100_000
        changed["content_hash"] = canonical_hash({
            key: value for key, value in changed.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "identity differs"):
            load_config_v2(canonical_bytes(changed))


class QueryPolicyTests(unittest.TestCase):
    def test_one_authorization_covers_the_policy_not_each_query(self) -> None:
        policy = policy_for(("crossref",))
        authorization = authorize_policy(
            policy, actor_id="human.researcher", authorized_at_epoch=OBSERVED_AT,
            capability_id=CAPABILITY_ID_V2,
        )
        self.assertEqual(policy["content_hash"], authorization["policy_hash"])
        self.assertEqual("human_final", authorization["authorized_by"]["authority"])
        self.assertEqual("inspection_only", authorization["trust_effects"])

    def test_generated_query_is_ledgered_with_grounding_spans(self) -> None:
        policy = policy_for(("crossref",))
        query = ground_query(policy, SOURCES, TERMS)
        self.assertEqual(QUERY_TEXT, query["query_text"])
        for term, evidence in zip(query["terms"], query["grounding"]):
            self.assertEqual(term, evidence["term"])
            self.assertEqual("problem.statement", evidence["source_id"])
            normalized = SOURCE.decode("utf-8").casefold()
            self.assertIn(
                term,
                " ".join(normalized.split())[evidence["span_start"]:evidence["span_end"]],
            )

    def test_ungrounded_term_is_refused(self) -> None:
        policy = policy_for(("crossref",))
        with self.assertRaisesRegex(ValueError, "not grounded"):
            ground_query(policy, SOURCES, ("invented free-generation buzzword",))

    def test_policy_over_config_ceiling_is_refused(self) -> None:
        config = load_config_v2(CONFIG.read_bytes())
        policy = policy_for(("crossref",), max_requests=512)
        with self.assertRaisesRegex(ValueError, "ceiling"):
            dry_run_v2(config, policy, SOURCES, [TERMS], 0)


class PaginatedSweepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config_v2(CONFIG.read_bytes())
        self.policy = policy_for(("crossref", "openalex", "arxiv"))
        self.authorization = authorize_policy(
            self.policy, actor_id="human.researcher",
            authorized_at_epoch=OBSERVED_AT, capability_id=CAPABILITY_ID_V2,
        )
        self.permit = permit_for(ALL_ORIGINS)
        self.clock = FakeClock()
        self.sleeper = FakeSleeper(self.clock)

    def run_sweep(self, pages: dict[str, tuple[str, bytes]], policy=None) -> dict:
        policy = policy or self.policy
        authorization = authorize_policy(
            policy, actor_id="human.researcher",
            authorized_at_epoch=OBSERVED_AT, capability_id=CAPABILITY_ID_V2,
        )
        origins = tuple(sorted(
            self.config["providers"][name]["origin"]
            for name in policy["provider_allowlist"]
        ))
        permit = permit_for(origins)
        transport = FakeTransport(permit, pages)
        self.transport = transport
        return sweep(
            self.config, policy, authorization, SOURCES, [TERMS],
            permit=permit, resolver=FakeResolver(permit),
            transport=transport, clock=self.clock, sleeper=self.sleeper,
            observed_at_epoch=OBSERVED_AT,
        )

    def test_multi_page_sweep_accumulates_hundreds_under_budget(self) -> None:
        report = self.run_sweep(full_sweep_pages(self.config))
        verify_report_v2(report, self.policy)
        self.assertEqual("executed", report["status"])
        self.assertEqual(8, report["totals"]["requests"])
        self.assertEqual(350, report["totals"]["candidates"])
        self.assertEqual(
            sum(len(body) for _, body in full_sweep_pages(self.config).values()),
            report["totals"]["response_bytes"],
        )
        providers = {item["provider"] for item in report["candidates"]}
        self.assertEqual({"crossref", "openalex", "arxiv"}, providers)
        self.assertEqual(
            list(range(1, 351)), [item["rank"] for item in report["candidates"]],
        )
        for item in report["candidates"]:
            self.assertEqual("untrusted_inspiration_candidate", item["status"])
            self.assertFalse(item["acquisition_authorized"])
            self.assertEqual("not_assessed", item["novelty"])
        # Every request is ledgered with provider, query, cursor, bytes, outcome.
        for entry in report["request_ledger"]:
            self.assertEqual("executed", entry["outcome"])
            self.assertEqual(
                report["queries"][0]["query_hash"], entry["query_hash"],
            )
            self.assertGreater(entry["response_bytes"], 0)
        cursors = [
            entry["cursor"] for entry in report["request_ledger"]
            if entry["provider"] == "crossref"
        ]
        self.assertEqual(["*", "CR2", "CR3"], cursors)

    def test_rate_limit_interval_is_enforced_and_recorded(self) -> None:
        report = self.run_sweep(full_sweep_pages(self.config))
        # Consecutive same-provider requests inside the minimum interval wait.
        self.assertGreaterEqual(len(self.sleeper.sleeps), 4)
        self.assertTrue(all(wait > 0 for wait in self.sleeper.sleeps))
        waited = [
            timing["waited_milliseconds"]
            for timing in report["operational"]["timings"]
        ]
        self.assertEqual(sum(self.sleeper.sleeps), sum(waited))
        for entry in report["request_ledger"]:
            self.assertEqual(
                self.config["providers"][entry["provider"]]["min_interval_milliseconds"],
                entry["min_interval_milliseconds"],
            )
        # Timings are operational, not semantic: the content hash ignores them.
        semantic = {
            key: value for key, value in report.items()
            if key not in {"content_hash", "operational", "operational_hash"}
        }
        self.assertEqual(canonical_hash(semantic), report["content_hash"])
        self.assertEqual(
            canonical_hash(report["operational"]), report["operational_hash"],
        )

    def test_over_budget_request_is_refused_and_ledgered(self) -> None:
        policy = policy_for(("crossref",), max_requests=2)
        pages = {}
        crossref = self.config["providers"]["crossref"]
        pages[request_url("crossref", crossref, QUERY_TEXT, "*")] = (
            "application/json", crossref_body(0, 50, "CR2"),
        )
        pages[request_url("crossref", crossref, QUERY_TEXT, "CR2")] = (
            "application/json", crossref_body(50, 50, "CR3"),
        )
        report = self.run_sweep(pages, policy=policy)
        verify_report_v2(report, policy)
        self.assertEqual("budget_exhausted", report["status"])
        self.assertEqual(2, report["totals"]["requests"])
        self.assertEqual(100, report["totals"]["candidates"])
        refused = report["request_ledger"][-1]
        self.assertEqual("refused_budget_exhausted", refused["outcome"])
        self.assertFalse(refused["network"])
        self.assertEqual(0, refused["response_bytes"])
        self.assertEqual("CR3", refused["cursor"])
        self.assertEqual(2, len(self.transport.requests))

    def test_byte_budget_exhaustion_refuses_the_next_request(self) -> None:
        policy = policy_for(("crossref",), max_response_bytes=1_024)
        crossref = self.config["providers"]["crossref"]
        pages = {
            request_url("crossref", crossref, QUERY_TEXT, "*"): (
                "application/json", crossref_body(0, 50, "CR2"),
            ),
        }
        report = self.run_sweep(pages, policy=policy)
        verify_report_v2(report, policy)
        self.assertEqual("budget_exhausted", report["status"])
        self.assertEqual(1, report["totals"]["requests"])
        self.assertEqual(
            "refused_budget_exhausted", report["request_ledger"][-1]["outcome"],
        )

    def test_provider_failure_is_retained_not_discarded(self) -> None:
        crossref = self.config["providers"]["crossref"]
        policy = policy_for(("crossref",))
        pages = {
            request_url("crossref", crossref, QUERY_TEXT, "*"): (
                "application/json", b'{"status":"error"}',
            ),
        }
        report = self.run_sweep(pages, policy=policy)
        verify_report_v2(report, policy)
        self.assertEqual("executed", report["status"])
        self.assertEqual(
            "provider_response_invalid", report["request_ledger"][0]["outcome"],
        )
        self.assertEqual([], report["candidates"])

    def test_requests_carry_no_headers_or_credentials(self) -> None:
        self.run_sweep(full_sweep_pages(self.config))
        for request in self.transport.requests:
            self.assertEqual((), request.headers)
            self.assertEqual("GET", request.method)
            query = parse_qs(urlsplit(request.url).query)
            self.assertNotIn("api_key", query)

    def test_mismatched_authorization_actor_is_refused(self) -> None:
        other = LiveNetworkPermit(
            "run.discovery-v2.test", "human.other", "human", "human_final",
            CAPABILITY_ID_V2, ALL_ORIGINS, True,
        )
        transport = FakeTransport(other, full_sweep_pages(self.config))
        with self.assertRaises(AcquisitionPolicyError):
            sweep(
                self.config, self.policy, self.authorization, SOURCES, [TERMS],
                permit=other, resolver=FakeResolver(other), transport=transport,
                clock=self.clock, sleeper=self.sleeper,
                observed_at_epoch=OBSERVED_AT,
            )


class VerifyReportV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config_v2(CONFIG.read_bytes())
        self.policy = policy_for(("crossref",))
        self.report = dry_run_v2(self.config, self.policy, SOURCES, [TERMS], 0)

    def test_dry_run_is_zero_network_and_verifies(self) -> None:
        verify_report_v2(self.report, self.policy)
        self.assertEqual("not_executed", self.report["status"])
        self.assertEqual(0, self.report["totals"]["requests"])
        self.assertEqual([], self.report["request_ledger"])
        self.assertIsNone(self.report["authorization_hash"])

    def test_rehashed_trust_promotion_is_detected(self) -> None:
        changed = copy.deepcopy(self.report)
        changed["trust_effects"] = dict(
            changed["trust_effects"], acquisition_authorized=True,
        )
        semantic = {
            key: value for key, value in changed.items()
            if key not in {"content_hash", "operational", "operational_hash"}
        }
        changed["content_hash"] = canonical_hash(semantic)
        with self.assertRaisesRegex(ValueError, "trust promotion"):
            verify_report_v2(changed, self.policy)

    def test_float_anywhere_is_refused(self) -> None:
        changed = copy.deepcopy(self.report)
        changed["totals"]["response_bytes"] = 0.0
        with self.assertRaisesRegex(ValueError, "float"):
            verify_report_v2(changed, self.policy)

    def test_request_accounting_must_be_exact(self) -> None:
        changed = copy.deepcopy(self.report)
        changed["totals"]["requests"] = 1
        semantic = {
            key: value for key, value in changed.items()
            if key not in {"content_hash", "operational", "operational_hash"}
        }
        changed["content_hash"] = canonical_hash(semantic)
        with self.assertRaisesRegex(ValueError, "accounting"):
            verify_report_v2(changed, self.policy)


class DiscoveryV2CliTests(unittest.TestCase):
    def test_inspect_v2_verifies_report_against_policy(self) -> None:
        config = load_config_v2(CONFIG.read_bytes())
        policy = policy_for(("crossref",))
        report = dry_run_v2(config, policy, SOURCES, [TERMS], 0)
        with tempfile.TemporaryDirectory() as workdir:
            report_path = Path(workdir) / "report.json"
            policy_path = Path(workdir) / "policy.json"
            report_path.write_bytes(canonical_bytes(report))
            policy_path.write_bytes(canonical_bytes(policy))
            output = StringIO()
            with redirect_stdout(output):
                code = phase4d_main([
                    "inspect-v2", str(report_path), "--policy", str(policy_path),
                ])
            self.assertEqual(0, code)
            summary = json.loads(output.getvalue())
            self.assertEqual("not_executed", summary["status"])
            self.assertEqual(policy["content_hash"], summary["policy_hash"])
            self.assertTrue(summary["inspiration_only"])


if __name__ == "__main__":
    unittest.main()
