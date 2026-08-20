from __future__ import annotations

import json
from pathlib import Path
import unittest

from spikes.phase4b_acquisition import (
    AcquisitionCapability,
    AcquisitionPolicy,
    AcquisitionRequest,
    RightsDecision,
    RobotsDecision,
    ScriptedTransport,
    acquire_candidates,
    canonical_bytes,
    replay_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "phase4b-acquisition" / "scripted-corpus.json"


class Phase4BAcquisitionSpikeTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.script = fixture["responses"]
        self.policy = AcquisitionPolicy(
            allowed_hosts=frozenset({"papers.example", "archive.example"}),
            max_redirects=1,
            max_response_bytes=1024,
            max_wall_ms=100,
            max_sources=2,
        )
        self.capability = AcquisitionCapability("capability.phase4b.test", "operator.test", True)
        self.rights = [
            RightsDecision("rights.start", "https://papers.example/start", "acquisition", "allowed"),
            RightsDecision("rights.final", "https://archive.example/paper-v1", "acquisition", "allowed"),
        ]
        self.robots = [
            RobotsDecision("robots.start", "https://papers.example/start", True),
            RobotsDecision("robots.final", "https://archive.example/paper-v1", True),
        ]

    def run_one(self, url: str, *, transport: ScriptedTransport | None = None, **changes):
        transport = transport or ScriptedTransport(self.script)
        result = acquire_candidates(
            [AcquisitionRequest("request.1", url)],
            capability=changes.get("capability", self.capability),
            policy=changes.get("policy", self.policy),
            rights=changes.get("rights", self.rights),
            robots=changes.get("robots", self.robots),
            transport=transport,
        )
        return result, transport

    def test_authorized_redirect_produces_only_an_untrusted_candidate(self) -> None:
        result, transport = self.run_one("https://papers.example/start")
        self.assertEqual(2, len(transport.calls))
        self.assertEqual([], result["failures"])
        self.assertEqual(2, len(result["responses"]))
        self.assertEqual("untrusted_candidate", result["candidates"][0]["disposition"])
        self.assertEqual("none", result["candidates"][0]["proof_status"])
        self.assertEqual("not_assessed", result["candidates"][0]["applicability_status"])

    def test_replay_is_byte_deterministic_and_never_calls_transport(self) -> None:
        first, _ = self.run_one("https://papers.example/start")
        second, _ = self.run_one("https://papers.example/start")
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))
        replay_transport = ScriptedTransport({})
        replayed = replay_manifest(canonical_bytes(first))
        self.assertEqual(first, replayed)
        self.assertEqual([], replay_transport.calls)

    def test_network_requires_explicit_capability_after_prefetch_authorization(self) -> None:
        disabled = AcquisitionCapability("capability.disabled", "operator.test", False)
        result, transport = self.run_one(
            "https://papers.example/start", capability=disabled
        )
        self.assertEqual([], transport.calls)
        self.assertEqual("network_capability_disabled", result["failures"][0]["reason"])

    def test_rights_and_robots_fail_before_transport(self) -> None:
        result, transport = self.run_one("https://papers.example/start", rights=[])
        self.assertEqual([], transport.calls)
        self.assertEqual("rights_not_authorized", result["failures"][0]["reason"])
        result, transport = self.run_one(
            "https://papers.example/start",
            robots=[RobotsDecision("robots.deny", "https://papers.example/start", False)],
        )
        self.assertEqual([], transport.calls)
        self.assertEqual("robots_not_authorized", result["failures"][0]["reason"])

    def test_https_host_and_redirect_destinations_fail_closed(self) -> None:
        for url, reason in (
            ("http://papers.example/start", "https_required"),
            ("https://evil.example/start", "host_not_allowed"),
        ):
            result, transport = self.run_one(url)
            self.assertEqual([], transport.calls)
            self.assertEqual(reason, result["failures"][0]["reason"])
        result, transport = self.run_one(
            "https://papers.example/start",
            rights=self.rights[:1],
            robots=self.robots[:1],
        )
        self.assertEqual(1, len(transport.calls))
        self.assertEqual("rights_not_authorized", result["failures"][0]["reason"])

    def test_redirect_byte_and_time_bounds_are_machine_enforced(self) -> None:
        no_redirects = AcquisitionPolicy(
            self.policy.allowed_hosts, 0, 1024, 100, 2
        )
        result, _ = self.run_one("https://papers.example/start", policy=no_redirects)
        self.assertEqual("redirect_limit_exhausted", result["failures"][0]["reason"])

        small = AcquisitionPolicy(self.policy.allowed_hosts, 1, 8, 100, 2)
        rights = [RightsDecision("r", "https://papers.example/oversized", "acquisition", "allowed")]
        robots = [RobotsDecision("b", "https://papers.example/oversized", True)]
        result, _ = self.run_one(
            "https://papers.example/oversized", policy=small, rights=rights, robots=robots
        )
        self.assertEqual("response_too_large", result["failures"][0]["reason"])

        rights = [RightsDecision("r", "https://papers.example/slow", "acquisition", "allowed")]
        robots = [RobotsDecision("b", "https://papers.example/slow", True)]
        result, _ = self.run_one("https://papers.example/slow", rights=rights, robots=robots)
        self.assertEqual("wall_time_exhausted", result["failures"][0]["reason"])

    def test_source_count_bound_stops_before_transport(self) -> None:
        policy = AcquisitionPolicy(self.policy.allowed_hosts, 1, 1024, 100, 1)
        transport = ScriptedTransport(self.script)
        result = acquire_candidates(
            [
                AcquisitionRequest("request.1", "https://papers.example/start"),
                AcquisitionRequest("request.2", "https://papers.example/start"),
            ],
            capability=self.capability,
            policy=policy,
            rights=self.rights,
            robots=self.robots,
            transport=transport,
        )
        self.assertEqual(2, len(transport.calls))
        self.assertEqual("source_count_exhausted", result["failures"][0]["reason"])

    def test_transport_failure_is_immutable_data_and_fabricates_no_content(self) -> None:
        url = "https://papers.example/missing"
        rights = [RightsDecision("r", url, "acquisition", "allowed")]
        robots = [RobotsDecision("b", url, True)]
        result, _ = self.run_one(url, rights=rights, robots=robots)
        self.assertEqual([], result["candidates"])
        self.assertEqual("transport_failure", result["failures"][0]["reason"])
        for forbidden in ("body", "content_sha256", "content_base64"):
            self.assertNotIn(forbidden, result["failures"][0])
        self.assertIn("manifest_hash", result["failures"][0])
        self.assertEqual(result, replay_manifest(canonical_bytes(result)))

    def test_identical_bytes_from_two_sources_keep_distinct_candidate_identity(self) -> None:
        first_url = "https://papers.example/copy-a"
        second_url = "https://archive.example/copy-b"
        script = {
            first_url: {"status": 200, "headers": {}, "body": "same bytes", "elapsed_ms": 1},
            second_url: {"status": 200, "headers": {}, "body": "same bytes", "elapsed_ms": 1},
        }
        result = acquire_candidates(
            [AcquisitionRequest("request.a", first_url), AcquisitionRequest("request.b", second_url)],
            capability=self.capability,
            policy=self.policy,
            rights=[
                RightsDecision("rights.a", first_url, "acquisition", "allowed"),
                RightsDecision("rights.b", second_url, "acquisition", "allowed"),
            ],
            robots=[RobotsDecision("robots.a", first_url, True), RobotsDecision("robots.b", second_url, True)],
            transport=ScriptedTransport(script),
        )
        self.assertEqual([], result["failures"])
        self.assertEqual(result["candidates"][0]["content_sha256"], result["candidates"][1]["content_sha256"])
        self.assertNotEqual(result["candidates"][0]["candidate_id"], result["candidates"][1]["candidate_id"])
        self.assertEqual(result, replay_manifest(canonical_bytes(result)))


if __name__ == "__main__":
    unittest.main()
