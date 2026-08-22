"""ADR-0080 snapshot fetcher acceptance: gated, allowlisted, paced, resumable.

The load-bearing test ingests a multi-hundred-document synthetic snapshot
(generated deterministically here, never committed) through the fetcher and
the ordinary tranche path: an interrupted fetch resumes without refetching,
the second ingest run is delta-only, and a repeat fetch makes zero requests.
Everything crosses a fake transport; no test touches the network.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from math_research.corpus_service import (
    ARCHIVE_MANIFEST_SCHEMA_VERSION,
    SNAPSHOT_ACTIVATION_SCHEMA_VERSION,
    TRANCHE_CONFIG_SCHEMA_VERSION,
)
from math_research.corpus_service.constants import (
    CAPABILITY_ID,
    LIVE_SNAPSHOT_ACKNOWLEDGEMENT,
    MAX_TRANCHE_DOCUMENTS,
    MAX_TRANCHE_DOCUMENTS_STRUCTURAL_CEILING,
    MAX_TRANCHE_TOTAL_BYTES,
    PROVIDER,
)
from math_research.corpus_service.dataroot import initialize_data_root
from math_research.corpus_service.errors import (
    SnapshotAcquisitionNotActiveError,
    SnapshotFetchBoundExceededError,
    SnapshotFetchFailedError,
    SnapshotOriginNotAllowlistedError,
    TrancheConfigInvalidError,
)
from math_research.corpus_service.fetcher import (
    ObjectStoreArchiveSource,
    fetch_snapshot,
)
from math_research.corpus_service.ledger import read_ledger
from math_research.corpus_service.serialization import sealed, sha256_bytes
from math_research.corpus_service.service import ingest_tranche
from math_research.corpus_service.snapshot import validate_tranche_config
from math_research.corpus_service.policy import validate_policy

ORIGIN = "https://export.arxiv.org"
T0 = "2026-08-22T00:00:00Z"
T1 = "2026-08-22T01:00:00Z"
T2 = "2026-08-22T02:00:00Z"

HUMAN = {
    "actor_id": "human.repository-owner",
    "actor_kind": "human",
    "authority": "human_final",
}

OPEN_LICENCE = "LicenseRef-AdaIvy-Synthetic-OpenAccess"
OPEN_LICENCE_URL = "https://example.invalid/licenses/adaivy-synthetic-open-access"
UNKNOWN_LICENCE = "LicenseRef-AdaIvy-Synthetic-Unclassified"


def _active_activation() -> dict:
    return sealed({
        "schema_version": SNAPSHOT_ACTIVATION_SCHEMA_VERSION,
        "status": "active",
        "capability_id": CAPABILITY_ID,
        "acknowledgement_required": LIVE_SNAPSHOT_ACKNOWLEDGEMENT,
        "max_tranche_documents": MAX_TRANCHE_DOCUMENTS,
        "max_tranche_total_bytes": MAX_TRANCHE_TOTAL_BYTES,
        "crawling_allowed": False,
        "result_following_allowed": False,
        "credentials_allowed": False,
        "autonomous_origin_selection": False,
        "network_discovery_origin": "crossref_only_per_adr_0051",
        "licence_diligence_adr": "adr-0067",
        "authorized_by": dict(HUMAN),
        "content_hash": None,
    })


def _pending_activation() -> dict:
    record = dict(_active_activation())
    record["status"] = "pending_owner_activation"
    record["content_hash"] = None
    return sealed(record)


def _synthetic_archive(count: int) -> tuple[dict, dict[str, bytes]]:
    """A deterministic snapshot: every 50th document has an unknown licence."""

    documents = []
    bodies: dict[str, bytes] = {}
    for index in range(count):
        document_id = f"doc-synth-{index:04d}"
        body = (
            f"Synthetic open-access paper {index:04d}.\n\n"
            f"A paragraph about exact topic number {index:04d} with enough "
            "text to be a real span.\n"
        ).encode("utf-8")
        relative_path = f"documents/{document_id}.txt"
        bodies[relative_path] = body
        unknown = index % 50 == 0
        documents.append({
            "document_id": document_id,
            "relative_path": relative_path,
            "media_type": "text/plain",
            "byte_count": len(body),
            "sha256": sha256_bytes(body),
            "licence": {
                "licence": UNKNOWN_LICENCE if unknown else OPEN_LICENCE,
                "licence_url": (
                    "https://example.invalid/licenses/unclassified" if unknown
                    else OPEN_LICENCE_URL
                ),
            },
        })
    manifest = sealed({
        "schema_version": ARCHIVE_MANIFEST_SCHEMA_VERSION,
        "provider": PROVIDER,
        "archive_id": "archive.adaivy-synthetic-snapshot",
        "archive_version": "v1",
        "documents": documents,
        "document_count": len(documents),
        "total_bytes": sum(item["byte_count"] for item in documents),
        "content_hash": None,
    })
    return manifest, bodies


def _policy() -> dict:
    return validate_policy(sealed({
        "schema_version": "adaivy.corpus-service-source-rights-policy.v1",
        "policy_id": "policy.adaivy-synthetic-snapshot-v1",
        "archive": {
            "archive_id": "archive.adaivy-synthetic-snapshot",
            "archive_version": "v1",
        },
        "authored_by": dict(HUMAN),
        "terms_reviewed_at": "2026-08-22",
        "licence_diligence_adr": "adr-0067",
        "default_action": "quarantine",
        "rules": [{
            "rule_id": "rule.synthetic-open-access",
            "licence": OPEN_LICENCE,
            "licence_url": OPEN_LICENCE_URL,
            "acquisition": "allowed",
            "storage_and_retention": "allowed",
            "parsing": "allowed",
            "full_text": True,
            "embedding": {
                "value": "allowed",
                "processor": {
                    "processor_id": "processor.openai.synthetic-fixture-embedding",
                    "provider": "openai",
                    "model_identifier": "synthetic-fixture-embedding-v1",
                    "disclosure_kind": "text_stays_local",
                },
            },
            "model_context": {"value": "prohibited", "processor": None},
        }],
        "content_hash": None,
    }))


def _tranche(manifest: dict, policy: dict, *, max_documents: int) -> dict:
    return validate_tranche_config(sealed({
        "schema_version": TRANCHE_CONFIG_SCHEMA_VERSION,
        "tranche_id": "tranche.adaivy-synthetic-snapshot-v1",
        "archive_manifest_hash": manifest["content_hash"],
        "policy_content_hash": policy["content_hash"],
        "max_documents": max_documents,
        "max_total_bytes": 33_554_432,
        "max_document_bytes": 16_384,
        "selected_by": dict(HUMAN),
        "content_hash": None,
    }))


class FakeTransport:
    """Deterministic offline transport keyed by exact URL."""

    def __init__(self, manifest: dict, bodies: dict[str, bytes], *,
                 fail_after: int | None = None) -> None:
        self.bodies = {
            ORIGIN + "/" + path: body for path, body in bodies.items()
        }
        self.fail_after = fail_after
        self.calls: list[str] = []

    def get(self, url: str) -> bytes:
        self.calls.append(url)
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise OSError("synthetic connection drop")
        return self.bodies[url]


class VirtualClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _fetch(root: Path, manifest: dict, transport: FakeTransport, *,
           run_id: str, recorded_at: str, origin: str = ORIGIN,
           activation: dict | None = None,
           acknowledgement: str | None = LIVE_SNAPSHOT_ACKNOWLEDGEMENT) -> dict:
    clock = VirtualClock()
    return fetch_snapshot(
        root, manifest=manifest, origin=origin,
        activation=activation or _active_activation(),
        acknowledgement=acknowledgement, transport=transport,
        run_id=run_id, recorded_at=recorded_at,
        monotonic=clock.monotonic, sleep=clock.sleep,
    )


class FetcherGateTests(unittest.TestCase):
    def test_pending_record_and_wrong_acknowledgement_refuse(self) -> None:
        manifest, bodies = _synthetic_archive(3)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_data_root(root, data_root_id="dataroot.fetch", initialized_at=T0)
            with self.assertRaises(SnapshotAcquisitionNotActiveError):
                _fetch(root, manifest, FakeTransport(manifest, bodies),
                       run_id="run.gate", recorded_at=T1,
                       activation=_pending_activation())
            with self.assertRaises(SnapshotAcquisitionNotActiveError):
                _fetch(root, manifest, FakeTransport(manifest, bodies),
                       run_id="run.gate", recorded_at=T1,
                       acknowledgement="yes please")
            self.assertEqual([], read_ledger(root, "fetches"))

    def test_off_allowlist_origin_refuses_before_any_request_and_is_ledgered(self) -> None:
        manifest, bodies = _synthetic_archive(3)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_data_root(root, data_root_id="dataroot.fetch", initialized_at=T0)
            transport = FakeTransport(manifest, bodies)
            with self.assertRaises(SnapshotOriginNotAllowlistedError):
                _fetch(root, manifest, transport, run_id="run.evil",
                       recorded_at=T1, origin="https://evil.example")
            self.assertEqual([], transport.calls)
            records = read_ledger(root, "fetches")
            self.assertEqual(1, len(records))
            payload = records[0]["payload"]
            self.assertEqual("refused_off_allowlist", payload["outcome"])
            self.assertEqual("https://evil.example", payload["origin"])
            self.assertEqual(0, payload["byte_count"])

    def test_activation_volume_bound_refuses(self) -> None:
        manifest, _ = _synthetic_archive(MAX_TRANCHE_DOCUMENTS + 1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_data_root(root, data_root_id="dataroot.fetch", initialized_at=T0)
            with self.assertRaises(SnapshotFetchBoundExceededError):
                _fetch(root, manifest, FakeTransport(manifest, {}),
                       run_id="run.big", recorded_at=T1)


class FetcherPacingTests(unittest.TestCase):
    def test_rate_limit_is_observed_between_requests(self) -> None:
        manifest, bodies = _synthetic_archive(3)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_data_root(root, data_root_id="dataroot.fetch", initialized_at=T0)
            transport = FakeTransport(manifest, bodies)
            clock = VirtualClock()
            report = fetch_snapshot(
                root, manifest=manifest, origin=ORIGIN,
                activation=_active_activation(),
                acknowledgement=LIVE_SNAPSHOT_ACKNOWLEDGEMENT,
                transport=transport, run_id="run.paced", recorded_at=T1,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
            self.assertEqual(3, report["documents_fetched"])
            # No wait before the first request; a full pinned interval before
            # each of the other two.
            self.assertEqual([3.0, 3.0], clock.sleeps)
            self.assertEqual(1, report["max_concurrent_connections"])
            self.assertEqual(3000, report["min_request_interval_milliseconds"])
            requests = [
                record["payload"] for record in read_ledger(root, "fetches")
                if record["kind"] == "snapshot_request"
            ]
            self.assertEqual(3, len(requests))
            for payload in requests:
                self.assertEqual(ORIGIN, payload["origin"])
                self.assertEqual("fetched", payload["outcome"])
                self.assertTrue(payload["url"].startswith(ORIGIN + "/documents/"))
                self.assertGreater(payload["byte_count"], 0)


class MultiHundredDocumentAcceptanceTests(unittest.TestCase):
    """The Slice 13 exit criterion, offline: fetch, resume, ingest, delta."""

    def test_fetch_resume_ingest_and_delta_second_run(self) -> None:
        count = 300
        manifest, bodies = _synthetic_archive(count)
        policy = _policy()
        tranche = _tranche(manifest, policy, max_documents=count)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_data_root(root, data_root_id="dataroot.fetch", initialized_at=T0)

            # An interrupted fetch is recorded and loses nothing.
            broken = FakeTransport(manifest, bodies, fail_after=120)
            with self.assertRaises(SnapshotFetchFailedError):
                _fetch(root, manifest, broken, run_id="run.fetch-one", recorded_at=T1)
            outcomes = [
                record["payload"]["outcome"]
                for record in read_ledger(root, "fetches")
                if record["kind"] == "snapshot_request"
            ]
            self.assertEqual(120, outcomes.count("fetched"))
            self.assertEqual(1, outcomes.count("transport_error"))

            # Resume: only the remainder is requested.
            resumed = FakeTransport(manifest, bodies)
            report = _fetch(root, manifest, resumed, run_id="run.fetch-two", recorded_at=T1)
            self.assertEqual(count - 120, report["documents_fetched"])
            self.assertEqual(120, report["documents_already_stored"])
            self.assertEqual(count - 120, len(resumed.calls))

            # Ingest through the ordinary tranche path, zero network.
            archive = ObjectStoreArchiveSource(root, manifest)
            first = ingest_tranche(
                root, policy=policy, archive=archive, tranche_config=tranche,
                run_id="run.ingest-one", recorded_at=T1,
            )
            self.assertEqual(count, first["documents_total"])
            self.assertEqual(count, first["documents_acquired"])
            self.assertEqual(294, first["documents_admitted"])
            self.assertEqual(6, first["documents_quarantined"])
            self.assertTrue(first["generation_published"])
            self.assertEqual(0, first["network_requests"])

            # Second ingest run: delta-only, same generation.
            second = ingest_tranche(
                root, policy=policy, archive=archive, tranche_config=tranche,
                run_id="run.ingest-two", recorded_at=T2,
            )
            self.assertEqual(0, second["documents_acquired"])
            self.assertEqual(count, second["documents_reused"])
            self.assertFalse(second["generation_published"])
            self.assertEqual(first["generation_id"], second["generation_id"])
            self.assertEqual(first["generation_hash"], second["generation_hash"])

            # A repeat fetch makes zero requests.
            idle = FakeTransport(manifest, bodies)
            third = _fetch(root, manifest, idle, run_id="run.fetch-three", recorded_at=T2)
            self.assertEqual(0, third["documents_fetched"])
            self.assertEqual(count, third["documents_already_stored"])
            self.assertEqual(0, third["network_requests"])
            self.assertEqual([], idle.calls)


class TrancheCeilingTests(unittest.TestCase):
    def test_document_ceiling_is_operator_budgeted_below_the_structural_pin(self) -> None:
        manifest, _ = _synthetic_archive(3)
        policy = _policy()
        # Wider than the old 2,048 default is now expressible...
        config = _tranche(manifest, policy, max_documents=4_096)
        self.assertEqual(4_096, config["max_documents"])
        # ...but the structural ceiling is pinned in code and refuses.
        with self.assertRaises(TrancheConfigInvalidError):
            _tranche(
                manifest, policy,
                max_documents=MAX_TRANCHE_DOCUMENTS_STRUCTURAL_CEILING + 1,
            )


if __name__ == "__main__":
    unittest.main()
