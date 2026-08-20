"""Focused acceptance tests for durable Phase 4B candidate metadata."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from math_research.phase4a.workspace import Phase4Workspace
from math_research.phase4b.interchange import (
    Phase4BValidationError, decode_json, project_records, verify_export_bytes,
)
from math_research.phase4b.records import MAX_INPUT_BYTES, RecordType
from math_research.phase4b.serialization import canonical_bytes, sha256_bytes
from math_research.phase4b.serialization import operational_export_hash, semantic_export_hash
from math_research.phase4b.replay_artifacts import (
    ACQUISITION_TRACE, ReplayArtifactError, validate_artifact,
)
from math_research.phase4b.workspace import Phase4BWorkspace


T0 = "2026-08-20T00:00:00Z"
H = "sha256:" + "1" * 64
H2 = "sha256:" + "2" * 64
H3 = "sha256:" + "3" * 64
H4 = "sha256:" + "4" * 64


def acquisition_payload() -> dict[str, object]:
    return {
        "candidate_id": "candidate.acquisition.1",
        "source_id": "source.phase4b.1",
        "request_id": "request.phase4b.1",
        "normalized_url_hash": H,
        "content_object_id": "content-object.phase4b.1",
        "artifact_hash": H2,
        "byte_length": 128,
        "media_type_hash": H3,
        "acquisition_adapter_id": "adapter.phase4b.scripted",
        "acquisition_adapter_version": "v1",
        "policy_snapshot_id": "policy.phase4b.v1",
        "rights_decision_ids": ["rights.acquire.1", "rights.retain.1"],
        "terms_snapshot_hash": H3,
        "robots_snapshot_hash": H4,
        "predecessor_record_ids": [],
    }


def parse_payload(predecessor: str) -> dict[str, object]:
    return {
        "candidate_id": "candidate.parse.1",
        "source_id": "source.phase4b.1",
        "artifact_hash": H2,
        "parser_id": "parser.phase4b.synthetic",
        "parser_version": "v1",
        "parser_configuration_hash": H3,
        "policy_snapshot_id": "policy.phase4b.v1",
        "input_byte_length": 128,
        "output_byte_length": 96,
        "segment_count": 1,
        "formula_count": 0,
        "reference_count": 0,
        "anchors": [
            {
                "start_offset": 0,
                "end_offset": 12,
                "exact_text_hash": H4,
                "page_number": 1,
                "object_id_hash": None,
            }
        ],
        "predecessor_record_ids": [predecessor],
    }


def failure_payload(predecessor: str) -> dict[str, object]:
    return {
        "candidate_id": "candidate.failure.1",
        "operation": "parse",
        "source_id": "source.phase4b.1",
        "input_hash": H2,
        "failure_code": "missing_dependency",
        "boundary_id": "boundary.phase4b.parser",
        "observed_byte_count": 128,
        "policy_snapshot_id": "policy.phase4b.v1",
        "predecessor_record_ids": [predecessor],
    }


class Phase4BWorkspaceTests(unittest.TestCase):
    def test_uses_same_sqlite_path_and_does_not_modify_phase4a_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with Phase4Workspace(root) as phase4a:
                before = {
                    row["name"]: row["sql"]
                    for row in phase4a.connection.execute(
                        "SELECT name,sql FROM sqlite_master WHERE name GLOB 'phase4_*'"
                    )
                }
            with Phase4BWorkspace(root) as phase4b:
                self.assertEqual(phase4b.durable.path.resolve(), (root / "workspace.sqlite3").resolve())
                after = {
                    row["name"]: row["sql"]
                    for row in phase4b.connection.execute(
                        "SELECT name,sql FROM sqlite_master WHERE name GLOB 'phase4_*'"
                    )
                }
                self.assertEqual(after, before)
                self.assertTrue(
                    {"phase4b_records", "phase4b_events", "phase4b_candidate_projection"}
                    <= {
                        row[0] for row in phase4b.connection.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    }
                )

    def test_all_record_types_are_append_only_candidate_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Phase4BWorkspace(Path(temporary)) as workspace:
            acquired = workspace.append(
                record_type=RecordType.ACQUISITION_CANDIDATE,
                subject_id="source.phase4b.1", payload=acquisition_payload(), recorded_at=T0,
            )
            parsed = workspace.append(
                record_type=RecordType.PARSE_CANDIDATE,
                subject_id="source.phase4b.1", payload=parse_payload(acquired["record_id"]),
                recorded_at=T0,
            )
            failed = workspace.append(
                record_type=RecordType.FAILURE,
                subject_id="source.phase4b.1", payload=failure_payload(parsed["record_id"]),
                recorded_at=T0,
            )
            invalidated = workspace.append(
                record_type=RecordType.INVALIDATION,
                subject_id="source.phase4b.1",
                payload={
                    "invalidation_id": "invalidation.phase4b.1",
                    "trigger_record_id": "lifecycle.phase4a.revocation.1",
                    "affected_record_ids": sorted([acquired["record_id"], parsed["record_id"]]),
                    "reason_code": "source_revocation",
                    "policy_snapshot_id": "policy.phase4b.v1",
                },
                recorded_at=T0,
            )
            self.assertEqual([item["sequence"] for item in workspace.records()], [0, 1, 2, 3])
            self.assertEqual(invalidated["record_type"], "invalidation")
            projection = {item["record_id"]: item for item in workspace.projection()}
            self.assertEqual(projection[acquired["record_id"]]["current_state"], "invalidated_candidate")
            self.assertEqual(projection[parsed["record_id"]]["latest_invalidation_id"], invalidated["record_id"])
            self.assertEqual(projection[failed["record_id"]]["current_state"], "active_candidate")
            workspace.verify_integrity()

    def test_idempotent_append_preserves_first_operational_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Phase4BWorkspace(Path(temporary)) as workspace:
            first = workspace.append(
                record_type="acquisition_candidate", subject_id="source.phase4b.1",
                payload=acquisition_payload(), recorded_at=T0,
            )
            later = workspace.append(
                record_type="acquisition_candidate", subject_id="source.phase4b.1",
                payload=acquisition_payload(), recorded_at="2026-08-20T00:01:00Z",
                operational={
                    **workspace.default_operational(), "attempt_number": 2,
                    "elapsed_milliseconds": 10,
                },
            )
            self.assertEqual(later, first)
            self.assertEqual(len(workspace.records()), 1)
            with self.assertRaises(sqlite3.IntegrityError):
                workspace.connection.execute(
                    "UPDATE phase4b_records SET subject_id='rewritten'"
                )
            with self.assertRaises(sqlite3.IntegrityError):
                workspace.connection.execute("DELETE FROM phase4b_events")

    def test_semantic_and_operational_hashes_are_separate(self) -> None:
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            with Phase4BWorkspace(Path(one)) as left:
                a = left.append(
                    record_type="acquisition_candidate", subject_id="source.phase4b.1",
                    payload=acquisition_payload(), recorded_at=T0,
                )
            with Phase4BWorkspace(Path(two)) as right:
                b = right.append(
                    record_type="acquisition_candidate", subject_id="source.phase4b.1",
                    payload=acquisition_payload(), recorded_at="2026-08-20T00:01:00Z",
                    operational={
                        **right.default_operational(), "elapsed_milliseconds": 15,
                    },
                )
            self.assertEqual(a["record_id"], b["record_id"])
            self.assertEqual(a["content_hash"], b["content_hash"])
            self.assertNotEqual(a["operational_hash"], b["operational_hash"])

    def test_canonical_export_import_replay_and_reverse_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as replay:
            with Phase4BWorkspace(Path(temporary)) as source:
                acquired = source.append(
                    record_type="acquisition_candidate", subject_id="source.phase4b.1",
                    payload=acquisition_payload(), recorded_at=T0,
                )
                parsed = source.append(
                    record_type="parse_candidate", subject_id="source.phase4b.1",
                    payload=parse_payload(acquired["record_id"]), recorded_at=T0,
                )
                source.append(
                    record_type="invalidation", subject_id="source.phase4b.1",
                    payload={
                        "invalidation_id": "invalidation.phase4b.replay",
                        "trigger_record_id": "lifecycle.phase4a.correction.1",
                        "affected_record_ids": [parsed["record_id"]],
                        "reason_code": "source_correction",
                        "policy_snapshot_id": "policy.phase4b.v1",
                    },
                    recorded_at=T0,
                )
                data = source.export_bytes()
                expected_projection = source.projection()
                self.assertEqual(
                    expected_projection,
                    project_records(tuple(reversed(source.records()))),
                )
                source.rebuild_projection(reverse=True)
                self.assertEqual(source.projection(), expected_projection)
                self.assertEqual(source.export_bytes(), data)
            verified = verify_export_bytes(data)
            with Phase4BWorkspace(Path(replay)) as target:
                imported = target.import_bytes(data)
                self.assertEqual(imported["content_hash"], verified["content_hash"])
                self.assertEqual(target.export_bytes(), data)
                target.import_bytes(data)
                self.assertEqual(len(target.records()), 3)

    def test_strict_raw_boundary_rejects_duplicate_unknown_version_and_oversize(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Phase4BWorkspace(Path(temporary)) as workspace:
            workspace.append(
                record_type="acquisition_candidate", subject_id="source.phase4b.1",
                payload=acquisition_payload(), recorded_at=T0,
            )
            value = workspace.export_value()
            data = workspace.export_bytes()
            duplicate = b'{"profile":"x",' + data[1:]
            with self.assertRaises(Phase4BValidationError):
                verify_export_bytes(duplicate)
            unknown = dict(value)
            unknown["unexpected"] = True
            with self.assertRaises(Phase4BValidationError):
                verify_export_bytes(canonical_bytes(unknown))
            wrong = dict(value)
            wrong["schema_version"] = "adaivy.phase4b-export.v999"
            with self.assertRaises(Phase4BValidationError):
                verify_export_bytes(canonical_bytes(wrong))
            with self.assertRaises(Phase4BValidationError):
                decode_json(b" " * (MAX_INPUT_BYTES + 1))
            with self.assertRaises(Phase4BValidationError):
                verify_export_bytes(json.dumps(value, indent=2).encode("utf-8"))

    def test_plaintext_is_not_a_permitted_record_field_or_durable_value(self) -> None:
        secret = b"PHASE4B_UNIQUE_RECONSTRUCTIVE_PLAINTEXT_DO_NOT_STORE"
        payload = acquisition_payload()
        payload["artifact_hash"] = sha256_bytes(secret)
        polluted = dict(payload)
        polluted["source_text"] = secret.decode("ascii")
        with tempfile.TemporaryDirectory() as temporary, Phase4BWorkspace(Path(temporary)) as workspace:
            with self.assertRaises(Phase4BValidationError):
                workspace.append(
                    record_type="acquisition_candidate", subject_id="source.phase4b.1",
                    payload=polluted, recorded_at=T0,
                )
            workspace.append(
                record_type="acquisition_candidate", subject_id="source.phase4b.1",
                payload=payload, recorded_at=T0,
            )
            exported = workspace.export_bytes()
            self.assertNotIn(secret, exported)
            workspace.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.assertNotIn(secret, (Path(temporary) / "workspace.sqlite3").read_bytes())

    def test_unknown_invalidation_target_fails_without_append(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Phase4BWorkspace(Path(temporary)) as workspace:
            with self.assertRaises(Phase4BValidationError):
                workspace.append(
                    record_type="invalidation", subject_id="source.phase4b.1",
                    payload={
                        "invalidation_id": "invalidation.phase4b.unknown",
                        "trigger_record_id": "lifecycle.phase4a.unknown",
                        "affected_record_ids": ["phase4b-record.unknown"],
                        "reason_code": "source_takedown",
                        "policy_snapshot_id": "policy.phase4b.v1",
                    },
                    recorded_at=T0,
                )
            self.assertEqual(workspace.records(), ())

    def test_migration_checksum_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with Phase4BWorkspace(root) as workspace:
                workspace.connection.execute(
                    "UPDATE phase4b_schema_migrations SET checksum=? WHERE version='0001'",
                    ("0" * 64,),
                )
            with self.assertRaises(Phase4BValidationError):
                Phase4BWorkspace(root)

    def test_replay_artifact_commits_atomically_and_is_append_only(self) -> None:
        malformed = {
            "semantic": {}, "semantic_sha256": H, "operational": {},
            "operational_sha256": H2,
        }
        with tempfile.TemporaryDirectory() as temporary, Phase4BWorkspace(Path(temporary)) as workspace:
            with self.assertRaises(ReplayArtifactError):
                workspace.append(
                    record_type="acquisition_candidate", subject_id="source.phase4b.1",
                    payload=acquisition_payload(), recorded_at=T0,
                    replay_artifacts=((ACQUISITION_TRACE, malformed),),
                )
            self.assertEqual((), workspace.records())
            self.assertEqual((), workspace.replay_artifacts())

    def test_legacy_v1_export_imports_without_inventing_replay_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as target_root:
            with Phase4BWorkspace(Path(source_root)) as source:
                source.append(
                    record_type="acquisition_candidate", subject_id="source.phase4b.1",
                    payload=acquisition_payload(), recorded_at=T0,
                )
                legacy = source.export_value()
            legacy.pop("replay_artifacts")
            legacy["schema_version"] = "adaivy.phase4b-export.v1"
            legacy["profile"] = "phase4b-candidate-audit-v1"
            legacy["content_hash"] = semantic_export_hash(legacy)
            legacy["operational_hash"] = operational_export_hash(legacy)
            data = canonical_bytes(legacy)
            with Phase4BWorkspace(Path(target_root)) as target:
                target.import_bytes(data)
                self.assertEqual(1, len(target.records()))
                self.assertEqual((), target.replay_artifacts())
                self.assertEqual("adaivy.phase4b-export.v2", target.export_value()["schema_version"])

    def test_replay_artifact_tampering_and_plaintext_field_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, Phase4BWorkspace(Path(temporary)) as workspace:
            # Use the service tests for valid artifact construction; here the raw
            # boundary proves a would-be reconstructive field cannot enter.
            forged = {
                "artifact_id": "phase4b-replay-artifact.forged",
                "artifact_type": "parse_proposal",
                "content_hash": H,
                "owner_record_id": "phase4b-parse_candidate.owner",
                "payload": {"normalized_text": "PROHIBITED_RECONSTRUCTIVE_TEXT"},
                "schema_version": "adaivy.phase4b-replay-artifact.v1",
                "sequence": 0,
            }
            with self.assertRaises(ReplayArtifactError):
                validate_artifact(forged)
            workspace.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.assertNotIn(
                b"PROHIBITED_RECONSTRUCTIVE_TEXT",
                (Path(temporary) / "workspace.sqlite3").read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
