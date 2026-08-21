"""Acceptance tests for bounded public scholarly discovery (ADR-0051)."""

from __future__ import annotations

import copy
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from math_research.phase4b.acquisition import (
    AcquisitionPolicyError, Resolution, TransportRequest, TransportResponse,
)
from math_research.phase4b.live_transport import LiveNetworkPermit
from math_research.phase4b.serialization import canonical_bytes, canonical_hash
from math_research.phase4d.discovery import (
    CAPABILITY_ID, CONFIG_HASH, LIVE_ACKNOWLEDGEMENT, GroundedQuery, dry_run,
    load_config, request_url, search, verify_report,
)
from math_research.phase4d_cli import main as phase4d_main


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/phase4d-crossref-public-discovery-v1.json"
SOURCE = b"Minimum-error quantum state discrimination uses a spectral projector."
ADDRESS = "93.184.216.34"


def query() -> GroundedQuery:
    return GroundedQuery.create(
        ("quantum state discrimination", "spectral projector"), SOURCE,
    )


def permit(item: GroundedQuery) -> LiveNetworkPermit:
    return LiveNetworkPermit(
        "run.discovery." + item.query_hash[-12:], "human.researcher", "human",
        "human_final", CAPABILITY_ID, ("https://api.crossref.org",), True,
    )


class Resolver:
    def __init__(self, permission: LiveNetworkPermit, address: str = ADDRESS) -> None:
        self.permit = permission
        self.address = address
        self.calls = 0

    def resolve(self, hostname: str) -> Resolution:
        self.calls += 1
        return Resolution(hostname, (self.address,))


class Transport:
    def __init__(self, permission: LiveNetworkPermit, body: bytes) -> None:
        self.permit = permission
        self.body = body
        self.calls = 0
        self.request: TransportRequest | None = None

    def fetch(self, request: TransportRequest) -> TransportResponse:
        self.calls += 1
        self.request = request
        return TransportResponse(
            200, (("content-type", "application/json; charset=utf-8"),),
            self.body, ADDRESS, 1,
        )


def response() -> bytes:
    return canonical_bytes({
        "status": "ok",
        "message": {"items": [
            {
                "DOI": "10.1000/Example.One",
                "title": ["A spectral method"],
                "publisher": "Open Research Press",
                "type": "journal-article",
            },
            {
                "DOI": "not-a-doi",
                "title": ["Discard me"],
            },
        ]},
    })


class PublicDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config(CONFIG.read_bytes())

    def test_config_is_pinned_and_credentials_are_disabled(self) -> None:
        self.assertEqual(CONFIG_HASH, self.config["content_hash"])
        self.assertEqual("public_unauthenticated", self.config["access_mode"])
        self.assertFalse(self.config["credentials_allowed"])
        changed = copy.deepcopy(self.config)
        changed["credentials_allowed"] = True
        changed["content_hash"] = canonical_hash({
            key: value for key, value in changed.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "identity differs"):
            load_config(canonical_bytes(changed))

    def test_every_search_term_must_be_grounded_in_local_text(self) -> None:
        item = query()
        self.assertIn("query.bibliographic=quantum+state+discrimination", request_url(self.config, item))
        with self.assertRaisesRegex(ValueError, "not grounded"):
            GroundedQuery.create(("invented unrelated buzzword",), SOURCE)
        with self.assertRaisesRegex(ValueError, "count"):
            GroundedQuery.create((), SOURCE)

    def test_dry_run_is_zero_network_and_has_no_trust_effect(self) -> None:
        report = verify_report(dry_run(self.config, query(), 0))
        self.assertEqual("not_executed", report["status"])
        self.assertEqual(0, report["network_requests"])
        self.assertEqual([], report["candidates"])
        self.assertTrue(report["inspiration_only"])
        self.assertFalse(report["trust_effects"]["acquisition_authorized"])
        self.assertEqual("none", report["trust_effects"]["mathematical_warrant"])

    def test_one_crossref_request_produces_bounded_inspiration_candidates(self) -> None:
        item = query()
        permission = permit(item)
        resolver = Resolver(permission)
        transport = Transport(permission, response())
        report = verify_report(search(
            self.config, item, permit=permission, resolver=resolver,
            transport=transport, observed_at_epoch=1_787_270_401,
            acknowledgement=LIVE_ACKNOWLEDGEMENT,
            confirmed_query_hash=item.query_hash,
        ))
        self.assertEqual("executed", report["status"])
        self.assertEqual(1, resolver.calls)
        self.assertEqual(1, transport.calls)
        self.assertEqual(1, report["candidate_count"])
        self.assertEqual(1, report["discarded_items"])
        candidate = report["candidates"][0]
        self.assertEqual("https://doi.org/10.1000/example.one", candidate["candidate_url"])
        self.assertEqual("untrusted_inspiration_candidate", candidate["status"])
        self.assertEqual("not_assessed", candidate["applicability"])
        self.assertFalse(candidate["acquisition_authorized"])
        self.assertEqual((), transport.request.headers)
        self.assertEqual((ADDRESS,), transport.request.connect_addresses)

    def test_private_resolution_is_rejected_before_transport(self) -> None:
        item = query()
        permission = permit(item)
        resolver = Resolver(permission, "127.0.0.1")
        transport = Transport(permission, response())
        with self.assertRaisesRegex(AcquisitionPolicyError, "address_forbidden"):
            search(
                self.config, item, permit=permission, resolver=resolver,
                transport=transport, observed_at_epoch=1_787_270_401,
                acknowledgement=LIVE_ACKNOWLEDGEMENT,
                confirmed_query_hash=item.query_hash,
            )
        self.assertEqual(0, transport.calls)

    def test_execution_requires_acknowledgement_and_exact_query_hash(self) -> None:
        item = query()
        permission = permit(item)
        resolver = Resolver(permission)
        transport = Transport(permission, response())
        with self.assertRaisesRegex(AcquisitionPolicyError, "acknowledgement_required"):
            search(
                self.config, item, permit=permission, resolver=resolver,
                transport=transport, observed_at_epoch=1, acknowledgement="",
                confirmed_query_hash=item.query_hash,
            )
        with self.assertRaisesRegex(AcquisitionPolicyError, "confirmation_invalid"):
            search(
                self.config, item, permit=permission, resolver=resolver,
                transport=transport, observed_at_epoch=1,
                acknowledgement=LIVE_ACKNOWLEDGEMENT,
                confirmed_query_hash="sha256:" + "0" * 64,
            )
        self.assertEqual(0, resolver.calls)
        self.assertEqual(0, transport.calls)

    def test_stale_terms_review_fails_before_dns(self) -> None:
        item = query()
        permission = permit(item)
        resolver = Resolver(permission)
        transport = Transport(permission, response())
        with self.assertRaisesRegex(AcquisitionPolicyError, "terms_review_stale"):
            search(
                self.config, item, permit=permission, resolver=resolver,
                transport=transport, observed_at_epoch=1_900_000_000,
                acknowledgement=LIVE_ACKNOWLEDGEMENT,
                confirmed_query_hash=item.query_hash,
            )
        self.assertEqual(0, resolver.calls)
        self.assertEqual(0, transport.calls)

    def test_self_hash_cannot_hide_a_trust_promotion(self) -> None:
        report = dry_run(self.config, query(), 0)
        report["trust_effects"]["mathematical_warrant"] = "proved"
        report["content_hash"] = canonical_hash({
            key: value for key, value in report.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "trust promotion"):
            verify_report(report)

    def test_cli_is_dry_by_default_and_inspects_its_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "problem.txt"
            source.write_bytes(SOURCE)
            output = root / "report.json"
            with redirect_stdout(StringIO()):
                self.assertEqual(0, phase4d_main([
                    "search", str(source), "--term", "quantum state discrimination",
                    "--config", str(CONFIG), "--output", str(output),
                ]))
                self.assertEqual(0, phase4d_main(["inspect", str(output)]))
            report = json.loads(output.read_bytes())
            self.assertEqual("not_executed", report["status"])
            self.assertEqual(0, report["network_requests"])
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    phase4d_main([
                        "search", str(source), "--term", "quantum state discrimination",
                        "--config", str(CONFIG), "--execute",
                    ])


if __name__ == "__main__":
    unittest.main()
