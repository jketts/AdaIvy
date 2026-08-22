"""ADR-0080 silo bridge: arXiv metadata records into the corpus service.

Descriptive metadata arrives with its rights restrictions intact: the CC0
metadata licence classifies under an exact policy rule, full text stays
forbidden (a policy that says otherwise is refused before any bytes move),
quotation caps apply, and an unclassified licence quarantines.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from math_research.corpus.constants import (
    MAX_QUOTED_ABSTRACT_CHARS,
    METADATA_LICENCE,
    METADATA_LICENCE_URL,
    QUOTATION_ELLIPSIS,
)
from math_research.corpus.records import build_record
from math_research.corpus_service.bridge import (
    BRIDGE_ARCHIVE_ID,
    build_bridge_archive,
    import_arxiv_metadata,
    metadata_document_text,
)
from math_research.corpus_service.dataroot import initialize_data_root, read_object
from math_research.corpus_service.errors import BridgeMetadataFullTextForbiddenError
from math_research.corpus_service.generation import load_generation
from math_research.corpus_service.policy import validate_policy
from math_research.corpus_service.serialization import sealed, sha256_bytes

T0 = "2026-08-22T00:00:00Z"
T1 = "2026-08-22T01:00:00Z"

HUMAN = {
    "actor_id": "human.repository-owner",
    "actor_kind": "human",
    "authority": "human_final",
}

RESPONSE_HASH = "sha256:" + "cd" * 32
PLAN_HASH = "sha256:" + "ef" * 32
DECISIONS = (
    "p4a.bridge-acquisition-0001",
    "p4a.bridge-parsing-0001",
    "p4a.bridge-storage-0001",
)


def _record(arxiv_id: str, title: str, abstract: str) -> dict:
    return build_record(
        {
            "arxiv_id": arxiv_id,
            "title": title,
            "abstract": abstract,
            "authors": ["Ada Ivy"],
            "primary_category": "math.CO",
            "categories": ["math.CO"],
            "doi": None,
            "published": "2026-01-01T00:00:00Z",
            "updated": "2026-01-01T00:00:00Z",
        },
        tranche_id="tranche.bridge-fixture",
        plan_hash=PLAN_HASH,
        response_sha256=RESPONSE_HASH,
        rights_decision_ids=DECISIONS,
    )


def _records() -> list[dict]:
    return [
        _record("2601.00001", "Exact bounds for synthetic graphs", "A short abstract."),
        _record(
            "2601.00002", "A second synthetic result",
            "An abstract long enough to exceed the reader-facing quotation "
            "cap so the bridge must truncate it with the pinned ellipsis "
            "rather than reproduce it, because the terms oblige a projection "
            "to link out rather than reproduce, and this sentence keeps going "
            "to be certain the character count crosses the pinned bound.",
        ),
    ]


def _policy(*, with_cc0_rule: bool = True, full_text: bool = False) -> dict:
    rules = []
    if with_cc0_rule:
        rules.append({
            "rule_id": "rule.arxiv-metadata-cc0",
            "licence": METADATA_LICENCE,
            "licence_url": METADATA_LICENCE_URL,
            "acquisition": "allowed",
            "storage_and_retention": "allowed",
            "parsing": "allowed",
            "full_text": full_text,
            "embedding": {"value": "prohibited", "processor": None},
            "model_context": {"value": "prohibited", "processor": None},
        })
    else:
        rules.append({
            "rule_id": "rule.unrelated",
            "licence": "LicenseRef-Unrelated",
            "licence_url": "https://example.invalid/licenses/unrelated",
            "acquisition": "allowed",
            "storage_and_retention": "allowed",
            "parsing": "allowed",
            "full_text": False,
            "embedding": {"value": "prohibited", "processor": None},
            "model_context": {"value": "prohibited", "processor": None},
        })
    return validate_policy(sealed({
        "schema_version": "adaivy.corpus-service-source-rights-policy.v1",
        "policy_id": "policy.arxiv-metadata-bridge-v1",
        "archive": {"archive_id": BRIDGE_ARCHIVE_ID, "archive_version": "v1"},
        "authored_by": dict(HUMAN),
        "terms_reviewed_at": "2026-08-22",
        "licence_diligence_adr": "adr-0067",
        "default_action": "quarantine",
        "rules": rules,
        "content_hash": None,
    }))


class BridgeArchiveTests(unittest.TestCase):
    def test_archive_is_deterministic_and_quotation_capped(self) -> None:
        records = _records()
        first, first_bodies = build_bridge_archive(records, archive_version="v1")
        second, second_bodies = build_bridge_archive(records, archive_version="v1")
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual(first_bodies, second_bodies)
        long_text = metadata_document_text(records[1])
        self.assertIn(QUOTATION_ELLIPSIS, long_text)
        abstract_line = long_text.split("\n\n")[1]
        self.assertLessEqual(len(abstract_line), MAX_QUOTED_ABSTRACT_CHARS)
        self.assertIn("https://arxiv.org/abs/2601.00002", long_text)
        for document in first["documents"]:
            self.assertEqual(METADATA_LICENCE, document["licence"]["licence"])
            self.assertEqual("text/plain", document["media_type"])


class BridgeImportTests(unittest.TestCase):
    def test_import_admits_metadata_without_full_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_data_root(root, data_root_id="dataroot.bridge", initialized_at=T0)
            report = import_arxiv_metadata(
                root, records=_records(), policy=_policy(),
                tranche_id="tranche.bridge-import-v1", archive_version="v1",
                run_id="run.bridge", recorded_at=T1,
            )
            self.assertEqual(2, report["documents_admitted"])
            self.assertEqual(0, report["documents_quarantined"])
            manifest = load_generation(root, report["generation_id"])
            for entry in manifest["entries"]:
                self.assertTrue(entry["document_id"].startswith("arxiv."))
                self.assertFalse(entry["full_text_stored"])
                self.assertIsNone(entry["spans_sha256"])
                self.assertIsNone(entry["extracted_sha256"])
                self.assertEqual("prohibited", entry["embedding"]["value"])
                self.assertEqual("prohibited", entry["model_context"]["value"])
                # The stored bytes are the capped descriptive rendering.
                body = read_object(root, entry["source_sha256"])
                self.assertEqual(sha256_bytes(body), entry["source_sha256"])

            # A second import is a delta-only no-op.
            second = import_arxiv_metadata(
                root, records=_records(), policy=_policy(),
                tranche_id="tranche.bridge-import-v1", archive_version="v1",
                run_id="run.bridge-two", recorded_at=T1,
            )
            self.assertEqual(0, second["documents_acquired"])
            self.assertEqual(2, second["documents_reused"])
            self.assertEqual(report["generation_id"], second["generation_id"])

    def test_unclassified_licence_quarantines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_data_root(root, data_root_id="dataroot.bridge", initialized_at=T0)
            report = import_arxiv_metadata(
                root, records=_records(), policy=_policy(with_cc0_rule=False),
                tranche_id="tranche.bridge-import-v1", archive_version="v1",
                run_id="run.bridge", recorded_at=T1,
            )
            self.assertEqual(0, report["documents_admitted"])
            self.assertEqual(2, report["documents_quarantined"])
            self.assertEqual(
                {"licence_unknown"},
                set(report["quarantine_reasons"].values()),
            )

    def test_full_text_policy_for_metadata_is_refused_before_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initialize_data_root(root, data_root_id="dataroot.bridge", initialized_at=T0)
            with self.assertRaises(BridgeMetadataFullTextForbiddenError):
                import_arxiv_metadata(
                    root, records=_records(),
                    policy=_policy(full_text=True),
                    tranche_id="tranche.bridge-import-v1", archive_version="v1",
                    run_id="run.bridge", recorded_at=T1,
                )


if __name__ == "__main__":
    unittest.main()
