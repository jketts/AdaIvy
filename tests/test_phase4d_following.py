"""Acceptance tests for depth-one result following (ADR-0068 via ADR-0081)."""

from __future__ import annotations

import copy
import unittest

from math_research.phase4b.serialization import canonical_hash
from math_research.phase4b.records import RecordType, SCHEMA_VERSION
from math_research.phase4b.serialization import (
    expected_record_id, operational_record_hash, semantic_record_hash,
)
from math_research.phase4d.following import (
    build_follow_allowlist, follow_references, validate_follow_allowlist,
    verify_followed,
)

ALLOWLIST = build_follow_allowlist(["doi.org", "arxiv.org"])


def acquisition_record(source_id: str) -> dict:
    h = "sha256:" + "1" * 64
    payload = {
        "candidate_id": "candidate.acquisition.alpha", "source_id": source_id,
        "request_id": "request.acquisition.alpha", "normalized_url_hash": h,
        "content_object_id": "content-object.acquisition.alpha",
        "artifact_hash": h, "byte_length": 128, "media_type_hash": h,
        "acquisition_adapter_id": "adapter.phase4b.scripted",
        "acquisition_adapter_version": "v1", "policy_snapshot_id": "policy.phase4b.v1",
        "rights_decision_ids": ["rights.acquire.alpha", "rights.retain.alpha"],
        "terms_snapshot_hash": h, "robots_snapshot_hash": h,
        "predecessor_record_ids": [],
    }
    value = {
        "schema_version": SCHEMA_VERSION,
        "record_id": expected_record_id(RecordType.ACQUISITION_CANDIDATE.value, source_id, payload),
        "record_type": RecordType.ACQUISITION_CANDIDATE.value,
        "subject_id": source_id, "sequence": 0,
        "recorded_at": "2026-08-22T00:00:00Z", "payload": payload,
        "operational": {
            "attempt_number": 1, "elapsed_milliseconds": 0, "exit_status": None,
            "stdout_hash": None, "stderr_hash": None,
            "stdout_bytes": 0, "stderr_bytes": 0,
        },
    }
    value["content_hash"] = semantic_record_hash(value)
    value["operational_hash"] = operational_record_hash(value)
    return value


def document(document_id: str = "doc.alpha", references: list | None = None) -> dict:
    if references is None:
        references = [
            {"field": "reference_doi", "value": "10.1000/upstream.1"},
            {"field": "reference_url", "value": "https://arxiv.org/abs/2408.01234v1"},
        ]
    return {
        "document_id": document_id,
        "acquisition_record": acquisition_record(document_id),
        "references": references,
    }


class FollowAllowlistTests(unittest.TestCase):
    def test_allowlist_is_content_hashed_and_fails_closed(self) -> None:
        validate_follow_allowlist(ALLOWLIST)
        changed = copy.deepcopy(ALLOWLIST)
        changed["hosts"] = sorted(changed["hosts"] + ["evil.example"])
        with self.assertRaisesRegex(ValueError, "identity differs"):
            validate_follow_allowlist(changed)
        changed["content_hash"] = canonical_hash({
            key: value for key, value in changed.items() if key != "content_hash"
        })
        validate_follow_allowlist(changed)  # rehash succeeds structurally...
        record = follow_references(
            [document()], allowlist=ALLOWLIST, max_followed_per_run=4,
        )
        with self.assertRaisesRegex(ValueError, "binding differs"):
            verify_followed(record, changed)  # ...but never binds to the run.


class FollowReferencesTests(unittest.TestCase):
    def test_followed_candidate_carries_provenance_edge(self) -> None:
        record = follow_references(
            [document()], allowlist=ALLOWLIST, max_followed_per_run=4,
        )
        verify_followed(record, ALLOWLIST)
        self.assertEqual(2, record["followed_count"])
        first = record["followed"][0]
        self.assertEqual("automation", first["origin_selected_by"])
        self.assertEqual(1, first["depth"])
        self.assertEqual("doc.alpha", first["provenance"]["origin_document_id"])
        self.assertEqual("reference_doi", first["provenance"]["reference_field"])
        self.assertEqual("10.1000/upstream.1", first["provenance"]["reference_value"])
        self.assertEqual("https://doi.org/10.1000/upstream.1", first["candidate_url"])
        self.assertEqual("untrusted_inspiration_candidate", first["status"])
        self.assertFalse(first["acquisition_authorized"])
        self.assertEqual("not_assessed", first["applicability"])

    def test_offlist_origin_is_refused_not_enqueued(self) -> None:
        record = follow_references(
            [document(references=[
                {"field": "reference_url", "value": "https://evil.example/paper"},
            ])],
            allowlist=ALLOWLIST, max_followed_per_run=4,
        )
        verify_followed(record, ALLOWLIST)
        self.assertEqual(0, record["followed_count"])
        self.assertEqual(
            "refused_offlist_origin", record["refused"][0]["reason"],
        )

    def test_fanout_cap_is_enforced_and_overflow_is_retained(self) -> None:
        references = [
            {"field": "reference_doi", "value": f"10.1000/upstream.{index}"}
            for index in range(10)
        ]
        record = follow_references(
            [document(references=references)],
            allowlist=ALLOWLIST, max_followed_per_run=3,
        )
        verify_followed(record, ALLOWLIST)
        self.assertEqual(3, record["followed_count"])
        self.assertEqual(7, record["refused_count"])
        self.assertTrue(all(
            item["reason"] == "refused_fanout_bound" for item in record["refused"]
        ))

    def test_depth_two_is_refused_absolutely(self) -> None:
        followed = follow_references(
            [document()], allowlist=ALLOWLIST, max_followed_per_run=4,
        )["followed"][0]
        with self.assertRaisesRegex(ValueError, "further follows"):
            follow_references(
                [followed], allowlist=ALLOWLIST, max_followed_per_run=4,
            )
        marked = dict(document(), depth=1)
        with self.assertRaisesRegex(ValueError, "further follows"):
            follow_references([marked], allowlist=ALLOWLIST, max_followed_per_run=4)

    def test_unverified_acquisition_record_cannot_originate_follows(self) -> None:
        item = document()
        item["acquisition_record"]["payload"]["byte_length"] = 129
        with self.assertRaisesRegex(ValueError, "acquisition record"):
            follow_references([item], allowlist=ALLOWLIST, max_followed_per_run=4)

    def test_query_strings_and_http_targets_are_refused(self) -> None:
        record = follow_references(
            [document(references=[
                {"field": "reference_url", "value": "https://arxiv.org/abs/1?x=1"},
                {"field": "reference_url", "value": "http://arxiv.org/abs/2408.1v1"},
            ])],
            allowlist=ALLOWLIST, max_followed_per_run=4,
        )
        self.assertEqual(0, record["followed_count"])
        self.assertEqual(2, record["refused_count"])
        self.assertTrue(all(
            item["reason"] == "refused_reference_malformed"
            for item in record["refused"]
        ))

    def test_followed_record_cannot_claim_human_selection(self) -> None:
        record = follow_references(
            [document()], allowlist=ALLOWLIST, max_followed_per_run=4,
        )
        changed = copy.deepcopy(record)
        changed["followed"][0]["origin_selected_by"] = "human"
        changed["content_hash"] = canonical_hash({
            key: value for key, value in changed.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "semantics differ"):
            verify_followed(changed, ALLOWLIST)

    def test_rehashed_record_cannot_replace_verified_acquisition_origin(self) -> None:
        record = follow_references(
            [document()], allowlist=ALLOWLIST, max_followed_per_run=4,
        )
        changed = copy.deepcopy(record)
        changed["origin_acquisition_records"][0]["payload"]["byte_length"] = 129
        changed["content_hash"] = canonical_hash({
            key: value for key, value in changed.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "acquisition record is invalid"):
            verify_followed(changed, ALLOWLIST)


if __name__ == "__main__":
    unittest.main()
