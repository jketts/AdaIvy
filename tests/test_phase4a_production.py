from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from math_research.phase4a import interchange as phase4a_interchange
from math_research.phase4a import HARD_TIMEOUT_SECONDS, MAX_EXPORT_BYTES, MAX_RECORDS, MAX_SOURCE_BYTES
from math_research.phase4a.interchange import (
    DeadlineExceeded, MonotonicDeadline, OutputLimitExceeded, build_envelope,
    _run_process_tree, export_workspace, import_replay, run_with_hard_timeout,
    write_bounded_chunks,
)
from math_research.phase4a.content_store import ContentStoreError, read_interchange_file
from math_research.phase4a.records import (
    DISCLOSING_RIGHTS_USES, PROCESSOR_FORBIDDEN_REFUSAL, PROCESSOR_REQUIRED_REFUSAL,
    ActorKind, ApplicabilityOutcome, ApplicabilityReason, ApplicabilityStatus,
    Authority, DisclosureKind, LifecycleType, Processor, RecordType, RightsOutcome,
    RightsReason, RightsUse, RightsValue,
)
from math_research.phase4a.serialization import (
    canonical_bytes, expected_record_id, operational_envelope_hash, record_content_hash,
    semantic_envelope_hash,
)
from math_research.phase4a.service import DeletionInterrupted, Phase4Service, RightsBlocked
from math_research.phase4a.validation import (
    PRODUCTION_SCHEMA_SHA256, Phase4ValidationError, schema_path, validate_durable_records,
    validate_record_for_append, validate_schema_contract, verify_bytes,
)
from math_research.phase2 import SUPPORTED_LIVE_PROVIDERS
from math_research.phase4a.workspace import Phase4Workspace

T0 = "2026-08-20T00:00:00Z"
T1 = "2026-08-20T00:00:01Z"
T2 = "2026-08-20T00:00:02Z"
T3 = "2026-08-20T00:00:03Z"
T4 = "2026-08-20T00:00:04Z"

# ADR-0064 processors. One decision authorizes one processor, and a second
# provider is a second decision, so these three identities stay distinct.
EMBEDDING_PROCESSOR = Processor(
    processor_id="processor.azure-openai.text-embedding-3-large",
    provider="azure_openai", model_identifier="text-embedding-3-large",
    disclosure_kind=DisclosureKind.TEXT_LEAVES_PROCESS,
)
SAME_PROVIDER_OTHER_MODEL = Processor(
    processor_id="processor.azure-openai.text-embedding-3-small",
    provider="azure_openai", model_identifier="text-embedding-3-small",
    disclosure_kind=DisclosureKind.TEXT_LEAVES_PROCESS,
)
SECOND_PROVIDER_PROCESSOR = Processor(
    processor_id="processor.openai.text-embedding-3-large",
    provider="openai", model_identifier="text-embedding-3-large",
    disclosure_kind=DisclosureKind.TEXT_LEAVES_PROCESS,
)


def run_canonical_workflow(fixture_path: Path, root: Path) -> dict[str, Any]:
    """Execute the path-independent canonical workflow in a disposable workspace."""

    value = json.loads(fixture_path.read_bytes(), object_pairs_hook=lambda pairs: dict(pairs))
    if value["schema_version"] != "adaivy.phase4a-canonical-workflow.v1" or value["profile"] != "phase4a-canonical-workflow-v1":
        raise ValueError("unknown canonical workflow fixture")
    expected_policies = {
        "rights": "phase4a-rights-v1", "applicability": "phase4a-applicability-v1",
        "lifecycle": "phase4a-lifecycle-v1", "canonical_identity": "phase4a-canonical-identity-v1",
    }
    if value["policies"] != expected_policies:
        raise ValueError("canonical workflow policies differ")
    root.mkdir(parents=True, exist_ok=True)
    source_value = value["source"]
    source = root / source_value["filename"]
    source.write_text(source_value["content"], encoding="utf-8")
    output = root / "canonical-export.json"
    logical_cards: dict[str, str] = {}
    with Phase4Workspace(root / "workspace") as workspace:
        service = Phase4Service(workspace)
        service.initialize_policy(actor_id=value["actors"]["policy"], recorded_at=value["rights_decisions"][0]["recorded_at"])
        for decision in value["rights_decisions"]:
            service.append_rights(
                source_id=source_value["id"], intended_use=RightsUse(decision["intended_use"]),
                value=RightsValue(decision["value"]), reason_code=RightsReason(decision["reason_code"]),
                reason_detail=decision["reason_detail"], evidence_refs=decision["evidence_refs"],
                actor_id=value["actors"]["owner"], valid_from=decision["valid_from"],
                valid_until=decision["valid_until"], recorded_at=decision["recorded_at"],
                lifecycle_id=decision["lifecycle_id"],
                # ADR-0064: read explicitly, so a fixture that omits the field
                # fails here rather than silently defaulting to no processor.
                processor=decision["processor"],
            )
        provenance = service.intake_local(
            source, source_id=source_value["id"], actor_id=value["actors"]["operator"],
            recorded_at=source_value["intake_recorded_at"], title=source_value["title"],
        )
        source_bytes = source_value["content"].encode("utf-8")
        for card_value in value["evidence_cards"]:
            statement = card_value["imported_statement"].encode("utf-8")
            start = source_bytes.index(statement)
            card = service.create_evidence_card(
                source_id=source_value["id"], span_byte_ranges=((start, start + len(statement)),),
                bibliographic_identity=card_value["bibliographic_identity"],
                imported_statement=card_value["imported_statement"], hypotheses=card_value["hypotheses"],
                definitions=card_value["definitions"], scope=card_value["scope"], exceptions=card_value["exceptions"],
                actor_id=value["actors"][card_value["actor"]], actor_kind=ActorKind.HUMAN,
                reason_detail=card_value["reason_detail"], recorded_at=card_value["recorded_at"],
            )
            logical_cards[card_value["logical_id"]] = card.id
        for review in value["applicability_decisions"]:
            card_id = logical_cards[review["evidence_card"]]
            service.review_applicability(
                source_id=source_value["id"], evidence_card_id=card_id,
                status=ApplicabilityStatus(review["status"]), outcome=ApplicabilityOutcome(review["outcome"]),
                reason_code=ApplicabilityReason(review["reason_code"]), reason_detail=review["reason_detail"],
                evidence_refs=(card_id,), actor_id=value["actors"][review["actor"]], actor_kind=ActorKind.HUMAN,
                recorded_at=review["recorded_at"], checks=review["checks"],
            )
        for lifecycle in value["lifecycle_actions"]:
            service.append_lifecycle(
                source_id=source_value["id"], action=LifecycleType(lifecycle["action"]),
                target_record_id=provenance.id, actor_id=value["actors"][lifecycle["actor"]],
                actor_kind=ActorKind.HUMAN, authority=Authority(lifecycle["authority"]),
                reason_code=lifecycle["reason_code"], reason_detail=lifecycle["reason_detail"],
                evidence_refs=lifecycle["evidence_refs"], recorded_at=lifecycle["recorded_at"],
            )
        semantic, operational, byte_length = export_workspace(workspace, output, exported_at=value["exported_at"])
        record_count = len(workspace.records())
    raw = output.read_bytes()
    return {
        "byte_length": byte_length, "file_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "operational_hash": operational, "record_count": record_count, "semantic_hash": semantic,
    }


class Phase4Fixture:
    def __init__(self, case: unittest.TestCase, *, text: str = "Theorem: if n = 1 then n + 1 = 2.\n") -> None:
        self.case = case
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.txt"
        self.source.write_text(text, encoding="utf-8")
        self.workspace = Phase4Workspace(self.root / "workspace")
        self.service = Phase4Service(self.workspace)
        self.policy = self.service.initialize_policy(actor_id="actor.policy", recorded_at=T0)
        self.source_id = "source.synthetic"

    def close(self) -> None:
        self.workspace.close()
        self.temp.cleanup()

    def right(
        self, use: RightsUse, value: RightsValue = RightsValue.ALLOWED,
        reason: RightsReason | None = None, *, at: str = T0,
        until: str | None = None, predecessor_id: str | None = None,
        processor: Processor | dict[str, Any] | None = None,
    ):
        if reason is None:
            reason = RightsReason.PERMITTED if value is RightsValue.ALLOWED else (
                RightsReason.EXPLICITLY_PROHIBITED if value is RightsValue.PROHIBITED else RightsReason.UNKNOWN_RIGHTS
            )
        return self.service.append_rights(
            source_id=self.source_id, intended_use=use, value=value, reason_code=reason,
            reason_detail=f"synthetic {use.value} decision", evidence_refs=(f"evidence.rights-{use.value.replace('_', '-')}",),
            actor_id="actor.owner", valid_from=T0, valid_until=until, recorded_at=at,
            lifecycle_id=f"rights-lifecycle.{use.value}", processor=processor,
            predecessor_id=predecessor_id,
        )

    def intake(self):
        for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING, RightsUse.EXCERPTING):
            self.right(use)
        return self.service.intake_local(self.source, source_id=self.source_id, actor_id="actor.operator", recorded_at=T1)

    def card(self):
        self.intake()
        data = self.source.read_bytes()
        default = "if n = 1 then n + 1 = 2"
        statement = default if default.encode("utf-8") in data else data.decode("utf-8").rstrip("\n")
        start = data.index(statement.encode("utf-8"))
        return self.service.create_evidence_card(
            source_id=self.source_id, span_byte_ranges=((start, start + len(statement.encode("utf-8"))),),
            bibliographic_identity="Synthetic theorem fixture",
            imported_statement=statement, hypotheses=("n = 1",),
            definitions=("n is an integer",), scope=("synthetic local fixture",), exceptions=(),
            actor_id="actor.curator", actor_kind=ActorKind.HUMAN,
            reason_detail="exact source-derived statement", recorded_at=T2,
        )


class Phase4ProductionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = Phase4Fixture(self)

    def tearDown(self) -> None:
        self.fixture.close()

    def test_policy_schema_and_additive_migration(self) -> None:
        self.assertEqual(PRODUCTION_SCHEMA_SHA256, validate_schema_contract())
        self.assertIn("phase4:0001", self.fixture.workspace.migration_versions)
        self.assertEqual(self.fixture.policy.id, self.fixture.policy.policy_snapshot_id)
        self.assertIsNotNone(self.fixture.workspace.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dossiers'"
        ).fetchone())
        for absent in ("research_memory_records", "formal_check_attempts", "phase4_evidence_card_content", "evidence_fts"):
            self.assertIsNone(self.fixture.workspace.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (absent,)
            ).fetchone())

    def test_seven_rights_outcomes_and_per_use_separation(self) -> None:
        """Every `RightsOutcome` member is reachable, including ADR-0064's seventh."""

        service = self.fixture.service
        source = self.fixture.source_id
        observed: set[RightsOutcome] = set()
        missing = service.evaluate_rights(source, RightsUse.ACQUISITION, at=T1)
        self.assertEqual(RightsOutcome.MISSING_OR_UNKNOWN, missing.outcome)
        observed.add(missing.outcome)
        allowed = self.fixture.right(RightsUse.ACQUISITION)
        self.assertEqual(RightsOutcome.PERMITTED, service.evaluate_rights(source, RightsUse.ACQUISITION, at=T1).outcome)
        observed.add(RightsOutcome.PERMITTED)
        self.assertEqual(RightsOutcome.REQUESTED_USE_INCOMPATIBLE, service.evaluate_rights(source, RightsUse.PUBLICATION, at=T1).outcome)
        observed.add(RightsOutcome.REQUESTED_USE_INCOMPATIBLE)
        prohibited = self.fixture.right(RightsUse.PUBLICATION, RightsValue.PROHIBITED)
        self.assertEqual(RightsOutcome.EXPLICITLY_PROHIBITED, service.evaluate_rights(source, RightsUse.PUBLICATION, at=T1).outcome)
        observed.add(RightsOutcome.EXPLICITLY_PROHIBITED)
        self.fixture.right(RightsUse.EXCERPTING, RightsValue.UNRESOLVED)
        self.assertEqual(RightsOutcome.MISSING_OR_UNKNOWN, service.evaluate_rights(source, RightsUse.EXCERPTING, at=T1).outcome)
        expired = self.fixture.right(RightsUse.PARSING, until=T0)
        self.assertEqual(RightsOutcome.EXPIRED, service.evaluate_rights(source, RightsUse.PARSING, at=T1).outcome)
        observed.add(RightsOutcome.EXPIRED)
        # ADR-0064. One embedding decision authorizes exactly one named processor.
        self.fixture.right(RightsUse.EMBEDDING, processor=EMBEDDING_PROCESSOR)
        self.assertEqual(
            RightsOutcome.PERMITTED,
            service.evaluate_rights(
                source, RightsUse.EMBEDDING, at=T1,
                processor_id=EMBEDDING_PROCESSOR.processor_id,
                provider=EMBEDDING_PROCESSOR.provider,
                model_identifier=EMBEDDING_PROCESSOR.model_identifier,
            ).outcome,
        )
        not_authorized = service.evaluate_rights(
            source, RightsUse.EMBEDDING, at=T1,
            processor_id=SECOND_PROVIDER_PROCESSOR.processor_id,
            provider=SECOND_PROVIDER_PROCESSOR.provider,
            model_identifier=SECOND_PROVIDER_PROCESSOR.model_identifier,
        )
        self.assertEqual(RightsOutcome.PROCESSOR_NOT_AUTHORIZED, not_authorized.outcome)
        self.assertFalse(not_authorized.allowed)
        observed.add(not_authorized.outcome)
        # A lifecycle revocation is tested after source registration below.
        self.fixture.right(RightsUse.STORAGE_AND_RETENTION)
        self.fixture.right(RightsUse.PARSING, predecessor_id=expired.id)
        self.fixture.service.intake_local(self.fixture.source, source_id=source, actor_id="actor.operator", recorded_at=T1)
        provenance = next(item for item in self.fixture.workspace.records() if item["record_type"] == RecordType.SOURCE_PROVENANCE.value)
        service.append_lifecycle(
            source_id=source, action=LifecycleType.REVOCATION, target_record_id=provenance["id"],
            actor_id="actor.owner", actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="rights_revoked", reason_detail="synthetic revocation", evidence_refs=("evidence.revocation",), recorded_at=T2,
        )
        self.assertEqual(RightsOutcome.REVOKED, service.evaluate_rights(source, RightsUse.ACQUISITION, at=T3).outcome)
        observed.add(RightsOutcome.REVOKED)
        self.assertEqual(set(RightsOutcome), observed, "an outcome is unreachable from the service")
        self.assertEqual(7, len(set(RightsOutcome)))

    def test_local_intake_fails_closed_before_open_and_preserves_provenance(self) -> None:
        with self.assertRaises(RightsBlocked):
            self.fixture.service.intake_local(self.fixture.source, source_id=self.fixture.source_id, actor_id="actor.operator", recorded_at=T1)
        self.assertEqual(1, len(self.fixture.workspace.records()))
        provenance = self.fixture.intake()
        self.assertEqual(MAX_SOURCE_BYTES, 2 * 1024 * 1024)
        self.assertEqual(self.fixture.source_id, provenance.payload["source_identity"])
        self.assertEqual("text/plain", provenance.payload["media_type"])
        self.assertNotIn("local_path_hash", provenance.payload)
        self.assertTrue(self.fixture.workspace.source_path_hashes()[self.fixture.source_id].startswith("sha256:"))
        self.assertEqual(self.fixture.source.read_bytes(), self.fixture.workspace.content.read_source(self.fixture.source_id))
        self.assertNotIn("phase3", json.dumps(provenance.payload))

    def test_path_encoding_and_size_boundaries(self) -> None:
        self.fixture.close()
        for size, accepted in ((MAX_SOURCE_BYTES, True), (MAX_SOURCE_BYTES + 1, False)):
            fixture = Phase4Fixture(self, text="")
            try:
                fixture.source.write_bytes(b"a" * size)
                for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
                    fixture.right(use)
                if accepted:
                    record = fixture.service.intake_local(fixture.source, source_id=fixture.source_id, actor_id="actor.operator", recorded_at=T1)
                    self.assertEqual(size, record.payload["byte_length"])
                else:
                    with self.assertRaises(ValueError):
                        fixture.service.intake_local(fixture.source, source_id=fixture.source_id, actor_id="actor.operator", recorded_at=T1)
            finally:
                fixture.close()
        self.fixture = Phase4Fixture(self)
        for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
            self.fixture.right(use)
        wrong = self.fixture.root / "bad.bin"; wrong.write_bytes(b"\xff")
        with self.assertRaises(ValueError):
            self.fixture.service.intake_local(wrong, source_id=self.fixture.source_id, actor_id="actor.operator", recorded_at=T1)

    def test_source_atomic_write_failure_cleans_content_and_temp(self) -> None:
        for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
            self.fixture.right(use)
        before = self.fixture.workspace.records()
        with mock.patch("math_research.phase4a.content_store.os.replace", side_effect=OSError("injected atomic replace failure")):
            with self.assertRaises(OSError):
                self.fixture.service.intake_local(
                    self.fixture.source, source_id=self.fixture.source_id,
                    actor_id="actor.operator", recorded_at=T1,
                )
        self.assertEqual(before, self.fixture.workspace.records())
        self.assertTrue(self.fixture.workspace.content.source_absent(self.fixture.source_id))
        self.assertTrue(self.fixture.workspace.content.temporary_empty())

    def _authorize_intake(self, fixture: Phase4Fixture) -> None:
        for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
            fixture.right(use)

    def _assert_failed_intake_is_clean(
        self, fixture: Phase4Fixture, outside: Path, expected_outside: bytes,
    ) -> None:
        self.assertFalse(any(
            item["record_type"] == RecordType.SOURCE_PROVENANCE.value
            for item in fixture.workspace.records()
        ))
        self.assertFalse(any(
            item["record_type"] == RecordType.LIFECYCLE_ACTION.value
            and item["payload"].get("action") == LifecycleType.DELETION_COMPLETION.value
            for item in fixture.workspace.records()
        ))
        self.assertEqual(0, fixture.workspace.connection.execute(
            "SELECT COUNT(*) FROM phase4_sources WHERE deletion_state='active' OR content_retained=1"
        ).fetchone()[0])
        self.assertEqual(0, fixture.workspace.connection.execute(
            "SELECT COUNT(*) FROM phase4_events e JOIN phase4_records r ON r.record_id=e.record_id "
            "WHERE r.record_type=?", (RecordType.SOURCE_PROVENANCE.value,)
        ).fetchone()[0])
        self.assertTrue(fixture.workspace.content.source_absent(fixture.source_id))
        self.assertTrue(fixture.workspace.content.temporary_empty())
        self.assertEqual((), fixture.workspace.content.object_names())
        self.assertEqual(expected_outside, outside.read_bytes())
        fixture.workspace.verify_durable_integrity()
        with Phase4Workspace(fixture.workspace.root) as reopened:
            reopened.verify_durable_integrity()
            self.assertEqual(0, reopened.connection.execute(
                "SELECT COUNT(*) FROM phase4_sources"
            ).fetchone()[0])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_temporary_symlink_substitution_fails_original_intake_synchronously(self) -> None:
        self._authorize_intake(self.fixture)
        outside = self.fixture.root / "outside-publication.txt"
        outside.write_bytes(b"outside publication marker\n")
        expected_outside = outside.read_bytes()
        real_replace = os.replace
        durable_symlink_observed = False

        def substitute_then_replace(source: str, target: str, **keywords: Any) -> None:
            nonlocal durable_symlink_observed
            os.unlink(source, dir_fd=keywords["src_dir_fd"])
            os.symlink(str(outside), source, dir_fd=keywords["src_dir_fd"])
            real_replace(source, target, **keywords)
            durable_symlink_observed = self.fixture.workspace.content.source_path(
                self.fixture.source_id,
            ).is_symlink()

        with mock.patch(
            "math_research.phase4a.content_store.os.replace",
            side_effect=substitute_then_replace,
        ):
            with self.assertRaises((ContentStoreError, OSError)):
                self.fixture.service.intake_local(
                    self.fixture.source, source_id=self.fixture.source_id,
                    actor_id="actor.operator", recorded_at=T1,
                )
        self.assertFalse(durable_symlink_observed)
        self._assert_failed_intake_is_clean(self.fixture, outside, expected_outside)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_temporary_symlink_substitution_probe_has_parent_timeout(self) -> None:
        code = r'''
import os, tempfile
from pathlib import Path
from unittest import mock
from math_research.phase4a.records import RightsReason, RightsUse, RightsValue
from math_research.phase4a.service import Phase4Service
from math_research.phase4a.workspace import Phase4Workspace
T0 = "2026-08-20T00:00:00Z"
T1 = "2026-08-20T00:00:01Z"
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / "source.txt"; source.write_text("bounded race probe\n", encoding="utf-8")
    outside = root / "outside.txt"; outside.write_text("outside\n", encoding="utf-8")
    workspace_root = root / "workspace"
    with Phase4Workspace(workspace_root) as workspace:
        service = Phase4Service(workspace)
        service.initialize_policy(actor_id="actor.policy", recorded_at=T0)
        for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
            service.append_rights(
                source_id="source.probe", intended_use=use, value=RightsValue.ALLOWED,
                reason_code=RightsReason.PERMITTED, reason_detail="bounded race right",
                evidence_refs=("evidence.probe",), actor_id="actor.owner", valid_from=T0,
                valid_until=None, recorded_at=T0, lifecycle_id="rights-lifecycle." + use.value,
            )
        real_replace = os.replace
        def attack(source_name, target_name, **keywords):
            os.unlink(source_name, dir_fd=keywords["src_dir_fd"])
            os.symlink(str(outside), source_name, dir_fd=keywords["src_dir_fd"])
            real_replace(source_name, target_name, **keywords)
        with mock.patch("math_research.phase4a.content_store.os.replace", side_effect=attack):
            try:
                service.intake_local(
                    source, source_id="source.probe", actor_id="actor.operator", recorded_at=T1,
                )
            except (OSError, RuntimeError):
                pass
            else:
                raise AssertionError("substituted publication returned success")
        assert workspace.connection.execute("SELECT COUNT(*) FROM phase4_sources").fetchone()[0] == 0
        assert workspace.content.source_absent("source.probe")
        assert workspace.content.temporary_empty()
        assert outside.read_text(encoding="utf-8") == "outside\n"
    with Phase4Workspace(workspace_root) as reopened:
        reopened.verify_durable_integrity()
'''
        environment = dict(
            os.environ, PYTHONDONTWRITEBYTECODE="1",
            PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
            env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=10, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr.decode("utf-8", "replace"))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_publication_identity_races_fail_closed_and_allow_clean_retry(self) -> None:
        scenarios = (
            "temporary_regular", "temporary_removed", "destination_symlink",
            "object_directory_swap", "published_symlink", "content_changed",
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                fixture = Phase4Fixture(self)
                try:
                    self._authorize_intake(fixture)
                    outside = fixture.root / "outside-race.txt"
                    outside.write_bytes(b"outside race marker\n")
                    expected_outside = outside.read_bytes()
                    store = fixture.workspace.content
                    real_replace, real_link, real_open = os.replace, os.link, os.open

                    if scenario in {"temporary_regular", "temporary_removed", "content_changed"}:
                        def replace_race(source: str, target: str, **keywords: Any) -> None:
                            if scenario == "temporary_removed":
                                os.unlink(source, dir_fd=keywords["src_dir_fd"])
                            elif scenario == "temporary_regular":
                                os.unlink(source, dir_fd=keywords["src_dir_fd"])
                                changed = real_open(
                                    source, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                    0o600, dir_fd=keywords["src_dir_fd"],
                                )
                                try:
                                    os.write(changed, b"substituted regular bytes\n")
                                    os.fsync(changed)
                                finally:
                                    os.close(changed)
                            else:
                                changed = real_open(source, os.O_WRONLY, dir_fd=keywords["src_dir_fd"])
                                try:
                                    original = fixture.source.read_bytes()
                                    os.write(changed, b"X" * len(original))
                                    os.fsync(changed)
                                finally:
                                    os.close(changed)
                            real_replace(source, target, **keywords)
                        patcher = mock.patch(
                            "math_research.phase4a.content_store.os.replace",
                            side_effect=replace_race,
                        )
                    elif scenario == "destination_symlink":
                        def destination_race(source: str, target: str, **keywords: Any) -> None:
                            os.symlink(str(outside), target, dir_fd=keywords["dst_dir_fd"])
                            real_link(source, target, **keywords)
                        patcher = mock.patch(
                            "math_research.phase4a.content_store.os.link",
                            side_effect=destination_race,
                        )
                    elif scenario == "object_directory_swap":
                        source_name = store.object_key(fixture.source_id)
                        moved_name = source_name + ".moved-race"
                        def directory_race(source: str, target: str, **keywords: Any) -> None:
                            os.rename(
                                source_name, moved_name,
                                src_dir_fd=store._objects_fd, dst_dir_fd=store._objects_fd,
                            )
                            os.symlink(str(outside), source_name, dir_fd=store._objects_fd)
                            real_replace(source, target, **keywords)
                        patcher = mock.patch(
                            "math_research.phase4a.content_store.os.replace",
                            side_effect=directory_race,
                        )
                    else:
                        replaced = False
                        def published_race(path: Any, flags: int, *arguments: Any, **keywords: Any) -> int:
                            nonlocal replaced
                            if path == "source.bin" and not replaced and flags & os.O_RDONLY == os.O_RDONLY:
                                replaced = True
                                os.unlink(path, dir_fd=keywords["dir_fd"])
                                os.symlink(str(outside), path, dir_fd=keywords["dir_fd"])
                            return real_open(path, flags, *arguments, **keywords)
                        patcher = mock.patch(
                            "math_research.phase4a.content_store.os.open",
                            side_effect=published_race,
                        )

                    with patcher, self.assertRaises((ContentStoreError, OSError, FileExistsError)):
                        fixture.service.intake_local(
                            fixture.source, source_id=fixture.source_id,
                            actor_id="actor.operator", recorded_at=T1,
                        )
                    self._assert_failed_intake_is_clean(fixture, outside, expected_outside)
                    accepted = fixture.service.intake_local(
                        fixture.source, source_id=fixture.source_id,
                        actor_id="actor.operator", recorded_at=T1,
                    )
                    self.assertEqual(RecordType.SOURCE_PROVENANCE, accepted.record_type)
                    self.assertEqual(1, fixture.workspace.deletion_info(fixture.source_id)["content_retained"])
                finally:
                    fixture.close()

    def test_database_failure_after_verified_publication_rolls_back_content(self) -> None:
        self._authorize_intake(self.fixture)
        outside = self.fixture.root / "outside-database.txt"
        outside.write_bytes(b"outside database marker\n")
        expected_outside = outside.read_bytes()
        with mock.patch.object(
            self.fixture.workspace, "append", side_effect=sqlite3.OperationalError("injected database failure"),
        ):
            with self.assertRaises(sqlite3.OperationalError):
                self.fixture.service.intake_local(
                    self.fixture.source, source_id=self.fixture.source_id,
                    actor_id="actor.operator", recorded_at=T1,
                )
        self._assert_failed_intake_is_clean(self.fixture, outside, expected_outside)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_and_missing_file_rejected(self) -> None:
        for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
            self.fixture.right(use)
        link = self.fixture.root / "link.txt"; link.symlink_to(self.fixture.source)
        with self.assertRaises(OSError):
            self.fixture.service.intake_local(link, source_id=self.fixture.source_id, actor_id="actor.operator", recorded_at=T1)
        with self.assertRaises(FileNotFoundError):
            self.fixture.service.intake_local(self.fixture.root / "missing.txt", source_id=self.fixture.source_id, actor_id="actor.operator", recorded_at=T1)

    def test_applicability_actor_authority_matrix(self) -> None:
        card = self.fixture.card()
        self.assertEqual("if n = 1 then n + 1 = 2", self.fixture.service.inspect_evidence_card(card.id, at=T3)["imported_statement"])
        self.assertFalse(card.payload["content_exported"])
        self.assertNotIn("imported_statement", card.payload)
        checks = {
            "bibliographic_identity_checked": False, "hypotheses_checked": False,
            "definitions_checked": False, "scope_exceptions_checked": False,
            "implication_checked": False,
        }
        for kind in (ActorKind.MODEL, ActorKind.AUTOMATION, ActorKind.SYSTEM):
            proposal = self.fixture.service.review_applicability(
                source_id=self.fixture.source_id, evidence_card_id=card.id,
                status=ApplicabilityStatus.PROPOSED, outcome=ApplicabilityOutcome.APPLICABLE,
                reason_code=ApplicabilityReason.INSUFFICIENT_EVIDENCE, reason_detail="proposal only",
                evidence_refs=(card.id,), actor_id=f"actor.{kind.value}", actor_kind=kind,
                recorded_at=T3, checks=checks,
            )
            self.assertEqual(Authority.PROPOSAL, proposal.authority)
            with self.assertRaises(Phase4ValidationError):
                self.fixture.service.review_applicability(
                    source_id=self.fixture.source_id, evidence_card_id=card.id,
                    status=ApplicabilityStatus.CHECKED, outcome=ApplicabilityOutcome.APPLICABLE,
                    reason_code=ApplicabilityReason.APPLICABLE, reason_detail="invalid nonhuman final",
                    evidence_refs=(card.id,), actor_id=f"actor.{kind.value}", actor_kind=kind,
                    recorded_at=T3, checks={key: True for key in checks},
                )
        with self.assertRaises(Phase4ValidationError):
            self.fixture.service.review_applicability(
                source_id=self.fixture.source_id, evidence_card_id=card.id,
                status=ApplicabilityStatus.CHECKED, outcome=ApplicabilityOutcome.APPLICABLE,
                reason_code=ApplicabilityReason.APPLICABLE, reason_detail="incomplete human review",
                evidence_refs=(card.id,), actor_id="actor.reviewer", actor_kind=ActorKind.HUMAN,
                recorded_at=T3, checks=checks,
            )
        final = self.fixture.service.review_applicability(
            source_id=self.fixture.source_id, evidence_card_id=card.id,
            status=ApplicabilityStatus.CHECKED, outcome=ApplicabilityOutcome.APPLICABLE,
            reason_code=ApplicabilityReason.APPLICABLE, reason_detail="all dimensions checked",
            evidence_refs=(card.id,), actor_id="actor.reviewer", actor_kind=ActorKind.HUMAN,
            recorded_at=T3, checks={key: True for key in checks},
        )
        self.assertEqual(Authority.HUMAN_FINAL, final.authority)

    def test_lifecycle_takedown_restore_legal_hold_and_deletion(self) -> None:
        card = self.fixture.card()
        provenance = next(
            item for item in self.fixture.workspace.records()
            if item["record_type"] == RecordType.SOURCE_PROVENANCE.value
        )
        before = canonical_bytes(self.fixture.workspace.record(provenance["id"]))
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.TAKEDOWN, target_record_id=provenance["id"],
            actor_id="actor.owner", actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="source_takedown", reason_detail="synthetic takedown", evidence_refs=("evidence.takedown",), recorded_at=T2,
        )
        self.assertTrue(self.fixture.workspace.projection(self.fixture.source_id)["suppressed"])
        with self.assertRaises(RightsBlocked):
            self.fixture.service.inspect_evidence_card(card.id, at=T2)
        self.assertEqual(before, canonical_bytes(self.fixture.workspace.record(provenance["id"])))
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.RESTORE, target_record_id=provenance["id"],
            actor_id="actor.owner", actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="source_restored", reason_detail="reviewed restore", evidence_refs=("evidence.restore",), recorded_at=T3,
        )
        self.assertFalse(self.fixture.workspace.projection(self.fixture.source_id)["suppressed"])
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.LEGAL_HOLD, target_record_id=provenance["id"],
            actor_id="actor.owner", actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="legal_hold", reason_detail="temporary hold", evidence_refs=("evidence.hold",), recorded_at=T3, legal_hold=True,
        )
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.DELETION_REQUEST, target_record_id=provenance["id"],
            actor_id="actor.owner", actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="content_deletion_requested", reason_detail="delete synthetic bytes", evidence_refs=("evidence.delete",), recorded_at=T3,
        )
        with self.assertRaises(ValueError):
            self.fixture.service.complete_deletion(self.fixture.source_id)
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.LEGAL_HOLD, target_record_id=provenance["id"],
            actor_id="actor.owner", actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="legal_hold_released", reason_detail="reviewed hold release", evidence_refs=("evidence.hold-release",), recorded_at=T4, legal_hold=False,
        )
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.DELETION_REQUEST, target_record_id=provenance["id"],
            actor_id="actor.owner", actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="content_deletion_requested", reason_detail="renewed deletion request", evidence_refs=("evidence.delete-2",), recorded_at=T4,
        )
        completion = self.fixture.service.complete_deletion(self.fixture.source_id)
        self.assertEqual(LifecycleType.DELETION_COMPLETION.value, completion["payload"]["action"])
        self.assertFalse(self.fixture.workspace.projection(self.fixture.source_id)["content_retained"])
        self.assertTrue(self.fixture.workspace.content.source_absent(self.fixture.source_id))
        with self.assertRaises((FileNotFoundError, RightsBlocked)):
            self.fixture.service.inspect_evidence_card(card.id, at=T4)
        self.assertEqual(before, canonical_bytes(self.fixture.workspace.record(provenance["id"])))
        self.assertEqual(completion["id"], self.fixture.service.complete_deletion(self.fixture.source_id)["id"])

    def test_deletion_removes_unique_marker_from_all_active_storage(self) -> None:
        self.fixture.close()
        marker = "ADAIVY_UNIQUE_DELETE_MARKER_7f3d9c2a"
        fixture = Phase4Fixture(self, text=marker + "\n")
        try:
            card = fixture.card()
            provenance = next(
                item for item in fixture.workspace.records()
                if item["record_type"] == RecordType.SOURCE_PROVENANCE.value
            )
            self.assertEqual(marker, fixture.service.inspect_evidence_card(card.id, at=T3)["imported_statement"])
            fixture.service.append_lifecycle(
                source_id=fixture.source_id, action=LifecycleType.DELETION_REQUEST,
                target_record_id=provenance["id"], actor_id="actor.owner",
                actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
                reason_code="content_deletion_requested", reason_detail="marker deletion",
                evidence_refs=("evidence.marker-delete",), recorded_at=T4,
            )
            fixture.service.complete_deletion(fixture.source_id)
            fixture.workspace.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            marker_bytes = marker.encode("utf-8")
            survivors = [
                path for path in (fixture.root / "workspace").rglob("*")
                if path.is_file() and marker_bytes in path.read_bytes()
            ]
            self.assertEqual([], survivors)
            self.assertNotIn(marker, json.dumps(fixture.workspace.records()))
            output = fixture.root / "post-delete.json"
            export_workspace(fixture.workspace, output, exported_at=T4)
            self.assertNotIn(marker_bytes, output.read_bytes())
            self.assertTrue(fixture.workspace.content.temporary_empty())
        finally:
            fixture.close()
        self.fixture = Phase4Fixture(self)

    def test_restart_reconciles_interruptions_before_and_after_removal(self) -> None:
        self.fixture.close()
        for boundary in ("before_removal", "after_removal"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source.txt"; source.write_text(f"restart {boundary}\n", encoding="utf-8")
                workspace_root = root / "workspace"
                with Phase4Workspace(workspace_root) as workspace:
                    service = Phase4Service(workspace)
                    service.initialize_policy(actor_id="actor.policy", recorded_at=T0)
                    for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
                        service.append_rights(
                            source_id="source.restart", intended_use=use, value=RightsValue.ALLOWED,
                            reason_code=RightsReason.PERMITTED, reason_detail=f"restart {use.value}",
                            evidence_refs=(f"evidence.restart-{use.value.replace('_', '-')}",),
                            actor_id="actor.owner", valid_from=T0, valid_until=None,
                            recorded_at=T0, lifecycle_id=f"rights-lifecycle.restart-{use.value}",
                        )
                    provenance = service.intake_local(
                        source, source_id="source.restart", actor_id="actor.operator", recorded_at=T1,
                    )
                    service.append_lifecycle(
                        source_id="source.restart", action=LifecycleType.DELETION_REQUEST,
                        target_record_id=provenance.id, actor_id="actor.owner",
                        actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
                        reason_code="content_deletion_requested", reason_detail="restart deletion",
                        evidence_refs=("evidence.restart-delete",), recorded_at=T4,
                    )
                    with self.assertRaises(DeletionInterrupted):
                        service.complete_deletion("source.restart", fail_after=boundary)
                    self.assertEqual("removing", workspace.deletion_info("source.restart")["deletion_state"])
                    self.assertFalse(any(
                        item["payload"].get("action") == LifecycleType.DELETION_COMPLETION.value
                        for item in workspace.records()
                    ))
                with Phase4Workspace(workspace_root) as restarted:
                    Phase4Service(restarted)
                    self.assertEqual("completed", restarted.deletion_info("source.restart")["deletion_state"])
                    self.assertTrue(restarted.content.source_absent("source.restart"))
                    completions = [
                        item for item in restarted.records()
                        if item["record_type"] == RecordType.LIFECYCLE_ACTION.value
                        and item["payload"]["action"] == LifecycleType.DELETION_COMPLETION.value
                    ]
                    self.assertEqual(1, len(completions))
        self.fixture = Phase4Fixture(self)

    def test_deletion_failure_and_phase3_copy_never_emit_false_completion(self) -> None:
        card = self.fixture.card()
        provenance = next(
            item for item in self.fixture.workspace.records()
            if item["record_type"] == RecordType.SOURCE_PROVENANCE.value
        )
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.DELETION_REQUEST,
            target_record_id=provenance["id"], actor_id="actor.owner",
            actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="content_deletion_requested", reason_detail="failure injection",
            evidence_refs=("evidence.failure-delete",), recorded_at=T4,
        )
        with mock.patch.object(self.fixture.workspace.content, "remove_source", side_effect=OSError("injected removal failure")):
            with self.assertRaises(OSError):
                self.fixture.service.complete_deletion(self.fixture.source_id)
        self.assertEqual("incomplete", self.fixture.workspace.deletion_info(self.fixture.source_id)["deletion_state"])
        self.assertTrue(self.fixture.workspace.projection(self.fixture.source_id)["suppressed"])
        self.assertFalse(any(
            item["payload"].get("action") == LifecycleType.DELETION_COMPLETION.value
            for item in self.fixture.workspace.records()
        ))
        self.assertEqual("if n = 1 then n + 1 = 2", self.fixture.workspace.content.read_card(self.fixture.source_id, card.id)["imported_statement"])

        # A fresh explicit request remains fail-closed if prohibited Phase 3 persistence is detected.
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.DELETION_REQUEST,
            target_record_id=provenance["id"], actor_id="actor.owner",
            actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="content_deletion_requested", reason_detail="retry after failed removal",
            evidence_refs=("evidence.failure-delete-retry",), recorded_at=T4,
        )
        self.fixture.workspace.connection.execute("CREATE TABLE research_memory_records(canonical_json TEXT NOT NULL)")
        self.fixture.workspace.connection.execute(
            "INSERT INTO research_memory_records VALUES(?)", (json.dumps({"artifact_hash": provenance["payload"]["artifact_hash"]}),)
        )
        with self.assertRaisesRegex(Phase4ValidationError, "immutable Phase 3"):
            self.fixture.service.complete_deletion(self.fixture.source_id)
        self.assertEqual("incomplete", self.fixture.workspace.deletion_info(self.fixture.source_id)["deletion_state"])
        self.assertTrue(self.fixture.workspace.content.source_absent(self.fixture.source_id))
        self.assertFalse(any(
            item["payload"].get("action") == LifecycleType.DELETION_COMPLETION.value
            for item in self.fixture.workspace.records()
        ))

    def test_identical_bytes_are_independent_per_source_objects(self) -> None:
        source_a = self.fixture.source_id
        source_b = "source.synthetic-copy"
        for source_id in (source_a, source_b):
            for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
                self.fixture.service.append_rights(
                    source_id=source_id, intended_use=use, value=RightsValue.ALLOWED,
                    reason_code=RightsReason.PERMITTED, reason_detail=f"independent {use.value}",
                    evidence_refs=(f"evidence.{source_id}-{use.value.replace('_', '-')}",),
                    actor_id="actor.owner", valid_from=T0, valid_until=None, recorded_at=T0,
                    lifecycle_id=f"rights-lifecycle.{source_id}-{use.value}",
                )
        first = self.fixture.service.intake_local(
            self.fixture.source, source_id=source_a, actor_id="actor.operator", recorded_at=T1,
        )
        second = self.fixture.service.intake_local(
            self.fixture.source, source_id=source_b, actor_id="actor.operator", recorded_at=T1,
        )
        self.assertEqual(first.payload["artifact_hash"], second.payload["artifact_hash"])
        self.assertNotEqual(first.payload["content_object_id"], second.payload["content_object_id"])
        self.fixture.service.append_lifecycle(
            source_id=source_a, action=LifecycleType.DELETION_REQUEST, target_record_id=first.id,
            actor_id="actor.owner", actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="content_deletion_requested", reason_detail="delete only first source",
            evidence_refs=("evidence.delete-first",), recorded_at=T4,
        )
        self.fixture.service.complete_deletion(source_a)
        self.assertTrue(self.fixture.workspace.content.source_absent(source_a))
        self.assertEqual(self.fixture.source.read_bytes(), self.fixture.workspace.content.read_source(source_b))

    def test_export_replay_restart_and_detached_snapshot(self) -> None:
        card = self.fixture.card()
        self.fixture.service.review_applicability(
            source_id=self.fixture.source_id, evidence_card_id=card.id,
            status=ApplicabilityStatus.REJECTED, outcome=ApplicabilityOutcome.REJECTED,
            reason_code=ApplicabilityReason.SCOPE_OR_EXCEPTION, reason_detail="fixture scope differs",
            evidence_refs=(card.id,), actor_id="actor.reviewer", actor_kind=ActorKind.HUMAN,
            recorded_at=T3, checks={
                "bibliographic_identity_checked": True, "hypotheses_checked": True,
                "definitions_checked": True, "scope_exceptions_checked": True,
                "implication_checked": False,
            },
        )
        path = self.fixture.root / "phase4.json"
        first = export_workspace(self.fixture.workspace, path, exported_at=T4)
        second = export_workspace(self.fixture.workspace, self.fixture.root / "phase4-second.json", exported_at=T4)
        self.assertEqual(first, second)
        snapshot = verify_bytes(path.read_bytes())
        value = snapshot.value(); value["records"].clear()
        self.assertGreater(len(snapshot.value()["records"]), 0)
        self.assertEqual(snapshot.content_hash, import_replay(path.read_bytes())["content_hash"])
        restart_root = self.fixture.root / "restart"
        with Phase4Workspace(restart_root) as restarted:
            imported = restarted.import_verified(path.read_bytes())
            self.assertEqual(snapshot.content_hash, imported.content_hash)
            rebuilt = restarted.rebuild_projections(reverse=True)
            self.assertIn(self.fixture.source_id, rebuilt)
            self.assertFalse(restarted.projection(self.fixture.source_id)["content_retained"])
            with self.assertRaises(RightsBlocked):
                Phase4Service(restarted).inspect_evidence_card(card.id, at=T4)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        fresh = subprocess.run(
            [sys.executable, "-m", "math_research.phase4a_cli", "inspect", str(path)],
            cwd=Path(__file__).resolve().parents[1], env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=30,
        )
        self.assertEqual(0, fresh.returncode, fresh.stderr.decode("utf-8", "replace"))
        self.assertEqual(snapshot.content_hash, json.loads(fresh.stdout)["content_hash"])

    def test_two_independent_runs_have_identical_semantic_and_file_hashes(self) -> None:
        self.fixture.close()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "shared.txt"; source.write_text("Shared deterministic source.\n", encoding="utf-8")
            results = []
            file_hashes = []
            for index in range(2):
                with Phase4Workspace(root / f"workspace-{index}") as workspace:
                    service = Phase4Service(workspace)
                    service.initialize_policy(actor_id="actor.policy", recorded_at=T0)
                    for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
                        service.append_rights(
                            source_id="source.shared", intended_use=use, value=RightsValue.ALLOWED,
                            reason_code=RightsReason.PERMITTED, reason_detail=f"shared {use.value} right",
                            evidence_refs=(f"evidence.shared-{use.value.replace('_', '-')}",), actor_id="actor.owner",
                            valid_from=T0, valid_until=None, recorded_at=T0, lifecycle_id=f"rights-lifecycle.shared-{use.value}",
                        )
                    service.intake_local(source, source_id="source.shared", actor_id="actor.operator", recorded_at=T1)
                    output = root / f"export-{index}.json"
                    results.append(export_workspace(workspace, output, exported_at=T2))
                    import hashlib
                    file_hashes.append(hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(results[0], results[1])
            self.assertEqual(file_hashes[0], file_hashes[1])
        self.fixture = Phase4Fixture(self)

    def test_canonical_workflow_manifest_two_fresh_processes(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        fixture = repository / "fixtures/phase4a-production/canonical-workflow-v1.json"
        manifest_path = repository / "fixtures/phase4a-production/manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        self.assertEqual(manifest["fixture_sha256"], "sha256:" + hashlib.sha256(fixture.read_bytes()).hexdigest())
        self.assertEqual(manifest["schema_sha256"], PRODUCTION_SCHEMA_SHA256)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(repository / "src"))
        code = (
            "import json,sys;from pathlib import Path;"
            "from tests.test_phase4a_production import run_canonical_workflow;"
            "print(json.dumps(run_canonical_workflow(Path(sys.argv[1]),Path(sys.argv[2])),sort_keys=True))"
        )
        results = []
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for destination in (Path(first) / "alpha", Path(second) / "beta"):
                process = subprocess.run(
                    [sys.executable, "-c", code, str(fixture), str(destination)], cwd=repository,
                    env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=30, check=False,
                )
                self.assertEqual(0, process.returncode, process.stderr.decode("utf-8", "replace"))
                results.append(json.loads(process.stdout))
        expected = manifest["expected_semantic_export_hash"]
        self.assertEqual([expected, expected], [item["semantic_hash"] for item in results])
        self.assertEqual([manifest["expected_record_count"]] * 2, [item["record_count"] for item in results])
        self.assertNotEqual(results[0]["operational_hash"], results[1]["operational_hash"])
        self.assertNotEqual(results[0]["file_sha256"], results[1]["file_sha256"])

    def test_strict_json_versions_fields_hashes_and_graph(self) -> None:
        self.fixture.intake()
        envelope = build_envelope(
            self.fixture.workspace.records(), exported_at=T4,
            source_path_hashes=self.fixture.workspace.source_path_hashes(),
        )
        raw = canonical_bytes(envelope)
        self.assertEqual(envelope["content_hash"], verify_bytes(raw).content_hash)
        cases: list[bytes] = [b"{", b'{"a":1,"a":2}']
        for data in cases:
            with self.assertRaises(Phase4ValidationError):
                verify_bytes(data)
        mutations = []
        for mutate in (
            lambda value: value.__setitem__("unknown", True),
            lambda value: value.pop("profile"),
            lambda value: value.__setitem__("profile", "phase4-review-v2"),
            lambda value: value["records"][0].__setitem__("schema_version", "adaivy.phase4a-record.v2"),
            lambda value: value["records"].append(copy.deepcopy(value["records"][0])),
            lambda value: value["records"].reverse(),
        ):
            value = copy.deepcopy(envelope); mutate(value); mutations.append(value)
        for value in mutations:
            # Rehash where possible so domain mutations cannot hide behind an outer hash failure.
            for record in value.get("records", []):
                if isinstance(record, dict) and "content_hash" in record:
                    record["content_hash"] = record_content_hash(record)
            if "content_hash" in value:
                value["content_hash"] = semantic_envelope_hash(value)
            if "operational_hash" in value:
                value["operational_hash"] = operational_envelope_hash(value)
            with self.assertRaises((Phase4ValidationError, KeyError)):
                verify_bytes(canonical_bytes(value))

    def test_fully_rehashed_nonhuman_final_and_dangling_reference_rejected(self) -> None:
        card = self.fixture.card()
        review = self.fixture.service.review_applicability(
            source_id=self.fixture.source_id, evidence_card_id=card.id,
            status=ApplicabilityStatus.PROPOSED, outcome=ApplicabilityOutcome.APPLICABLE,
            reason_code=ApplicabilityReason.INSUFFICIENT_EVIDENCE, reason_detail="proposal",
            evidence_refs=(card.id,), actor_id="actor.model", actor_kind=ActorKind.MODEL,
            recorded_at=T3, checks={
                "bibliographic_identity_checked": False, "hypotheses_checked": False,
                "definitions_checked": False, "scope_exceptions_checked": False,
                "implication_checked": False,
            },
        )
        envelope = build_envelope(self.fixture.workspace.records(), exported_at=T4, source_path_hashes=self.fixture.workspace.source_path_hashes())
        for mutation in ("nonhuman_final", "dangling"):
            value = copy.deepcopy(envelope)
            target = next(item for item in value["records"] if item["id"] == review.id)
            if mutation == "nonhuman_final":
                target["authority"] = "human_final"; target["payload"]["status"] = "checked"
            else:
                target["payload"]["evidence_card_id"] = "evidence-card.missing"
            target["content_hash"] = record_content_hash(target)
            value["content_hash"] = semantic_envelope_hash(value); value["operational_hash"] = operational_envelope_hash(value)
            with self.assertRaises(Phase4ValidationError):
                verify_bytes(canonical_bytes(value))

    def test_missing_actor_authority_cycle_and_lifecycle_rewrite_fail_closed(self) -> None:
        card = self.fixture.card()
        first = self.fixture.service.review_applicability(
            source_id=self.fixture.source_id, evidence_card_id=card.id,
            status=ApplicabilityStatus.PROPOSED, outcome=ApplicabilityOutcome.UNRESOLVED,
            reason_code=ApplicabilityReason.INSUFFICIENT_EVIDENCE, reason_detail="first proposal",
            evidence_refs=(card.id,), actor_id="actor.automation", actor_kind=ActorKind.AUTOMATION,
            recorded_at=T3, checks={
                "bibliographic_identity_checked": False, "hypotheses_checked": False,
                "definitions_checked": False, "scope_exceptions_checked": False, "implication_checked": False,
            },
        )
        second = self.fixture.service.review_applicability(
            source_id=self.fixture.source_id, evidence_card_id=card.id,
            status=ApplicabilityStatus.PROPOSED, outcome=ApplicabilityOutcome.UNRESOLVED,
            reason_code=ApplicabilityReason.INSUFFICIENT_EVIDENCE, reason_detail="second proposal",
            evidence_refs=(card.id,), actor_id="actor.automation", actor_kind=ActorKind.AUTOMATION,
            recorded_at=T4, checks={
                "bibliographic_identity_checked": False, "hypotheses_checked": False,
                "definitions_checked": False, "scope_exceptions_checked": False, "implication_checked": False,
            }, predecessor_id=first.id,
        )
        envelope = build_envelope(self.fixture.workspace.records(), exported_at=T4, source_path_hashes=self.fixture.workspace.source_path_hashes())
        mutations = []
        missing_actor = copy.deepcopy(envelope); next(item for item in missing_actor["records"] if item["id"] == first.id).pop("actor_id"); mutations.append(missing_actor)
        missing_authority = copy.deepcopy(envelope); next(item for item in missing_authority["records"] if item["id"] == first.id).pop("authority"); mutations.append(missing_authority)
        cycle = copy.deepcopy(envelope)
        cycle_first = next(item for item in cycle["records"] if item["id"] == first.id)
        cycle_first["predecessor_id"] = second.id; cycle_first["content_hash"] = record_content_hash(cycle_first)
        cycle["content_hash"] = semantic_envelope_hash(cycle); cycle["operational_hash"] = operational_envelope_hash(cycle); mutations.append(cycle)
        for value in mutations:
            with self.assertRaises(Phase4ValidationError):
                verify_bytes(canonical_bytes(value))

    def test_rehashed_broken_supersession_and_lifecycle_chain_are_rejected(self) -> None:
        provenance = self.fixture.intake()
        first = self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.CORRECTION,
            target_record_id=provenance.id, actor_id="actor.owner",
            actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="provenance_corrected", reason_detail="metadata-only correction",
            evidence_refs=("evidence.correction",), recorded_at=T2,
        )
        second = self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.SUPPRESSION,
            target_record_id=provenance.id, actor_id="actor.owner",
            actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="source_suppressed", reason_detail="synthetic suppression",
            evidence_refs=("evidence.suppression",), recorded_at=T3,
        )
        self.assertFalse(first.payload["legal_hold"])
        envelope = build_envelope(
            self.fixture.workspace.records(), exported_at=T4,
            source_path_hashes=self.fixture.workspace.source_path_hashes(),
        )
        for mutation in ("previous_event", "predecessor", "supersedes"):
            value = copy.deepcopy(envelope)
            target = next(item for item in value["records"] if item["id"] == second.id)
            if mutation == "previous_event":
                target["payload"]["previous_event_id"] = None
            elif mutation == "predecessor":
                target["predecessor_id"] = "lifecycle.missing"
            else:
                target["supersedes"] = "lifecycle.missing"
            target["content_hash"] = record_content_hash(target)
            value["content_hash"] = semantic_envelope_hash(value)
            value["operational_hash"] = operational_envelope_hash(value)
            with self.assertRaises(Phase4ValidationError):
                verify_bytes(canonical_bytes(value))

    def test_actual_writer_limits_atomic_cleanup_and_deadline(self) -> None:
        exact = io.BytesIO()
        count, digest = write_bounded_chunks((b"a" * 3, b"b" * 2), exact, max_bytes=5)
        self.assertEqual((5, b"aaabb"), (count, exact.getvalue()))
        self.assertTrue(digest.startswith("sha256:"))
        extra = io.BytesIO()
        with self.assertRaises(OutputLimitExceeded):
            write_bounded_chunks((b"a" * 5, b"x"), extra, max_bytes=5)
        self.assertEqual(b"aaaaa", extra.getvalue())
        ticks = iter((0.0, 0.0, 2.0))
        deadline = MonotonicDeadline.after(1.0, clock=lambda: next(ticks))
        with self.assertRaises(DeadlineExceeded):
            write_bounded_chunks((b"a", b"b"), io.BytesIO(), max_bytes=2, deadline=deadline)
        self.assertEqual(MAX_EXPORT_BYTES, 64 * 1024 * 1024)

    def test_exact_64_mib_and_plus_one_through_actual_writer(self) -> None:
        block = b"x" * (1024 * 1024)
        with tempfile.TemporaryFile() as handle:
            count, _ = write_bounded_chunks((block for _ in range(64)), handle)
            self.assertEqual(MAX_EXPORT_BYTES, count)
            self.assertEqual(MAX_EXPORT_BYTES, handle.tell())
        with tempfile.TemporaryFile() as handle:
            with self.assertRaises(OutputLimitExceeded):
                write_bounded_chunks((*(block for _ in range(64)), b"x"), handle)
            self.assertEqual(MAX_EXPORT_BYTES, handle.tell())

    def test_export_failure_keeps_existing_target_and_removes_temp(self) -> None:
        self.fixture.intake()
        target = self.fixture.root / "export.json"; target.write_bytes(b"prior")
        with self.assertRaises(OutputLimitExceeded):
            export_workspace(self.fixture.workspace, target, exported_at=T4, max_bytes=10)
        self.assertEqual(b"prior", target.read_bytes())
        self.assertEqual([], list(self.fixture.root.glob(".export.json.*")))

    def test_record_limit_and_boolean_integer_separation(self) -> None:
        self.fixture.intake()
        envelope = build_envelope(self.fixture.workspace.records(), exported_at=T4, source_path_hashes=self.fixture.workspace.source_path_hashes())
        value = copy.deepcopy(envelope)
        value["operational"]["elapsed_milliseconds"] = True
        value["operational_hash"] = operational_envelope_hash(value)
        with self.assertRaises(Phase4ValidationError):
            verify_bytes(canonical_bytes(value))
        with self.assertRaises(Phase4ValidationError):
            build_envelope([self.fixture.workspace.records()[0]] * (MAX_RECORDS + 1), exported_at=T4)

    def test_exact_256_and_257_records_through_strict_export_contract(self) -> None:
        self.fixture.intake()
        while self.fixture.workspace.next_sequence < MAX_RECORDS:
            index = self.fixture.workspace.next_sequence
            self.fixture.service.append_rights(
                source_id=self.fixture.source_id, intended_use=RightsUse.EXCERPTING,
                value=RightsValue.ALLOWED, reason_code=RightsReason.RIGHTS_CORRECTED,
                reason_detail=f"bounded correction {index}", evidence_refs=(f"evidence.boundary-{index}",),
                actor_id="actor.owner", valid_from=T0, valid_until=None, recorded_at=T2,
                lifecycle_id=f"rights-lifecycle.boundary-{index}",
            )
        self.assertEqual(MAX_RECORDS, len(self.fixture.workspace.records()))
        envelope = build_envelope(self.fixture.workspace.records(), exported_at=T4, source_path_hashes=self.fixture.workspace.source_path_hashes())
        self.assertEqual(MAX_RECORDS, len(verify_bytes(canonical_bytes(envelope)).value()["records"]))
        with self.assertRaises(Phase4ValidationError):
            self.fixture.service.append_rights(
                source_id=self.fixture.source_id, intended_use=RightsUse.EXCERPTING,
                value=RightsValue.ALLOWED, reason_code=RightsReason.RIGHTS_CORRECTED,
                reason_detail="record 257", evidence_refs=("evidence.boundary-257",),
                actor_id="actor.owner", valid_from=T0, valid_until=None, recorded_at=T2,
                lifecycle_id="rights-lifecycle.boundary-257",
            )
        self.assertEqual(MAX_RECORDS, len(self.fixture.workspace.records()))

    def test_durable_integrity_tampering_fails_restart_and_export(self) -> None:
        self.fixture.close()

        def prepared() -> tuple[tempfile.TemporaryDirectory[str], Path, str]:
            temp = tempfile.TemporaryDirectory()
            root = Path(temp.name)
            source = root / "source.txt"; source.write_text("durable integrity marker\n", encoding="utf-8")
            workspace_root = root / "workspace"
            with Phase4Workspace(workspace_root) as workspace:
                service = Phase4Service(workspace)
                service.initialize_policy(actor_id="actor.policy", recorded_at=T0)
                for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
                    service.append_rights(
                        source_id="source.durable", intended_use=use, value=RightsValue.ALLOWED,
                        reason_code=RightsReason.PERMITTED, reason_detail="durable integrity right",
                        evidence_refs=(f"evidence.durable-{use.value.replace('_', '-')}",),
                        actor_id="actor.owner", valid_from=T0, valid_until=None, recorded_at=T0,
                        lifecycle_id=f"rights-lifecycle.durable-{use.value}",
                    )
                service.intake_local(source, source_id="source.durable", actor_id="actor.operator", recorded_at=T1)
            return temp, workspace_root, "source.durable"

        mutations = ("record_hash", "source_bytes", "missing_source", "unknown_migration", "projection")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                temp, root, source_id = prepared()
                try:
                    database = root / "workspace.sqlite3"
                    if mutation == "record_hash":
                        with closing(sqlite3.connect(database)) as connection:
                            connection.execute("UPDATE phase4_records SET content_hash=? WHERE sequence=0", ("sha256:" + "f" * 64,))
                            connection.commit()
                    elif mutation in {"source_bytes", "missing_source"}:
                        content = root / "phase4-content/objects" / hashlib.sha256(source_id.encode()).hexdigest() / "source.bin"
                        if mutation == "source_bytes":
                            content.write_bytes(b"forged retained source\n")
                        else:
                            content.unlink()
                    elif mutation == "unknown_migration":
                        with closing(sqlite3.connect(database)) as connection:
                            connection.execute(
                                "INSERT INTO phase4_schema_migrations VALUES(?,?,?)",
                                ("9999", "0" * 64, T0),
                            )
                            connection.commit()
                    else:
                        with closing(sqlite3.connect(database)) as connection:
                            connection.execute("UPDATE phase4_suppression_projection SET suppressed=1")
                            connection.commit()
                    with self.assertRaises((Phase4ValidationError, RuntimeError, FileNotFoundError)):
                        Phase4Workspace(root)
                finally:
                    temp.cleanup()
        self.fixture = Phase4Fixture(self)

    def test_open_workspace_rejects_unknown_migration_for_every_verified_use(self) -> None:
        self.fixture.intake()
        database = self.fixture.workspace.root / "workspace.sqlite3"
        before = self.fixture.workspace.records()
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "INSERT INTO phase4_schema_migrations VALUES(?,?,?)",
                ("9999", "0" * 64, T0),
            )
            connection.commit()

        with self.assertRaises(Phase4ValidationError):
            self.fixture.workspace.verify_durable_integrity()
        with self.assertRaises(Phase4ValidationError):
            Phase4Service(self.fixture.workspace)
        with self.assertRaises(Phase4ValidationError):
            export_workspace(
                self.fixture.workspace, self.fixture.root / "unknown-migration.json",
                exported_at=T4,
            )
        self.assertFalse((self.fixture.root / "unknown-migration.json").exists())
        self.assertEqual(before, self.fixture.workspace.records())

        fixture = self.fixture
        workspace_root = fixture.workspace.root
        fixture.workspace.close()
        with self.assertRaises(Phase4ValidationError):
            Phase4Workspace(workspace_root)
        fixture.temp.cleanup()
        self.fixture = Phase4Fixture(self)

    def test_migration_ledger_missing_replaced_malformed_and_duplicate_fail(self) -> None:
        self.fixture.close()

        def prepared() -> tuple[tempfile.TemporaryDirectory[str], Path]:
            temp = tempfile.TemporaryDirectory()
            root = Path(temp.name) / "workspace"
            with Phase4Workspace(root):
                pass
            return temp, root

        for mutation in ("missing", "replaced", "malformed", "duplicate"):
            with self.subTest(mutation=mutation):
                temp, root = prepared()
                try:
                    with closing(sqlite3.connect(root / "workspace.sqlite3")) as connection:
                        if mutation == "missing":
                            connection.execute("DELETE FROM phase4_schema_migrations")
                        elif mutation == "replaced":
                            connection.execute(
                                "UPDATE phase4_schema_migrations SET checksum=?",
                                ("f" * 64,),
                            )
                        elif mutation == "malformed":
                            connection.execute(
                                "UPDATE phase4_schema_migrations SET applied_at='not-a-time'"
                            )
                        else:
                            connection.executescript(
                                "ALTER TABLE phase4_schema_migrations RENAME TO phase4_schema_migrations_old;"
                                "CREATE TABLE phase4_schema_migrations "
                                "(version TEXT, checksum TEXT NOT NULL, applied_at TEXT NOT NULL);"
                                "INSERT INTO phase4_schema_migrations SELECT * FROM phase4_schema_migrations_old;"
                                "INSERT INTO phase4_schema_migrations SELECT * FROM phase4_schema_migrations_old;"
                                "DROP TABLE phase4_schema_migrations_old;"
                            )
                        connection.commit()
                    with self.assertRaises((Phase4ValidationError, sqlite3.DatabaseError)):
                        Phase4Workspace(root)
                finally:
                    temp.cleanup()
        self.fixture = Phase4Fixture(self)

    def test_export_holds_verified_snapshot_through_serialization(self) -> None:
        self.fixture.intake()
        database = self.fixture.workspace.root / "workspace.sqlite3"
        attempted: list[bool] = []
        real_iter_json = phase4a_interchange._iter_json

        def attack_during_serialization(value: dict[str, Any]):
            attempted.append(True)
            with closing(sqlite3.connect(database, timeout=0.0, isolation_level=None)) as connection:
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute(
                        "INSERT INTO phase4_schema_migrations VALUES(?,?,?)",
                        ("9999", "0" * 64, T0),
                    )
            yield from real_iter_json(value)

        output = self.fixture.root / "stable-snapshot.json"
        with mock.patch.object(
            phase4a_interchange, "_iter_json", side_effect=attack_during_serialization,
        ):
            export_workspace(self.fixture.workspace, output, exported_at=T4)
        self.assertEqual([True], attempted)
        self.assertEqual(0, self.fixture.workspace.connection.execute(
            "SELECT COUNT(*) FROM phase4_schema_migrations WHERE version='9999'"
        ).fetchone()[0])
        verify_bytes(output.read_bytes())

    def test_export_revalidates_durable_record_columns(self) -> None:
        self.fixture.intake()
        self.fixture.workspace.connection.execute(
            "UPDATE phase4_records SET content_hash=? WHERE sequence=0",
            ("sha256:" + "e" * 64,),
        )
        with self.assertRaises(Phase4ValidationError):
            export_workspace(self.fixture.workspace, self.fixture.root / "tampered.json", exported_at=T4)

    def test_completed_state_requires_one_event_and_no_surviving_plaintext(self) -> None:
        provenance = self.fixture.intake()
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.DELETION_REQUEST,
            target_record_id=provenance.id, actor_id="actor.owner", actor_kind=ActorKind.HUMAN,
            authority=Authority.HUMAN_FINAL, reason_code="content_deletion_requested",
            reason_detail="integrity completion", evidence_refs=("evidence.integrity-delete",), recorded_at=T4,
        )
        completion = self.fixture.service.complete_deletion(self.fixture.source_id)
        with self.assertRaises(ValueError):
            self.fixture.service.append_lifecycle(
                source_id=self.fixture.source_id, action=LifecycleType.DELETION_REQUEST,
                target_record_id=provenance.id, actor_id="actor.owner", actor_kind=ActorKind.HUMAN,
                authority=Authority.HUMAN_FINAL, reason_code="content_deletion_requested",
                reason_detail="illegal post-completion request", evidence_refs=("evidence.illegal-transition",),
                recorded_at=T4,
            )
        with self.assertRaises(ValueError):
            self.fixture.workspace.append_deletion_completion(
                self.fixture.service._record(
                    record_type=RecordType.LIFECYCLE_ACTION, subject_id=self.fixture.source_id,
                    actor_id="actor.phase4-deletion", actor_kind=ActorKind.SYSTEM,
                    authority=Authority.DETERMINISTIC_POLICY, reason_code="content_deleted",
                    reason_detail="illegal duplicate completion", evidence_refs=("evidence.integrity-delete",),
                    recorded_at=T4, policy_snapshot_id=self.fixture.service.policy_id(),
                    predecessor_id=completion["id"], payload=completion["payload"],
                )
            )
        database = self.fixture.workspace.root / "workspace.sqlite3"
        source_root = self.fixture.workspace.content.source_path(self.fixture.source_id).parent
        source_root.mkdir(parents=True); (source_root / "cards").mkdir(); (source_root / "source.bin").write_text("survivor", encoding="utf-8")
        with self.assertRaises(Phase4ValidationError):
            export_workspace(self.fixture.workspace, self.fixture.root / "forged.json", exported_at=T4)
        (source_root / "source.bin").unlink(); (source_root / "cards").rmdir(); source_root.rmdir()
        with self.fixture.workspace.durable.transaction() as connection:
            connection.execute("DELETE FROM phase4_events WHERE record_id=?", (completion["id"],))
        with self.assertRaises(Phase4ValidationError):
            self.fixture.workspace.verify_durable_integrity()

    def test_repeated_completion_reverifies_absence_and_preserves_history(self) -> None:
        provenance = self.fixture.intake()
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.DELETION_REQUEST,
            target_record_id=provenance.id, actor_id="actor.owner",
            actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
            reason_code="content_deletion_requested", reason_detail="repeat verification",
            evidence_refs=("evidence.repeat-delete",), recorded_at=T4,
        )
        completion = self.fixture.service.complete_deletion(self.fixture.source_id)
        self.assertEqual(
            completion["id"],
            self.fixture.service.complete_deletion(self.fixture.source_id)["id"],
        )
        before = self.fixture.workspace.records()
        source_root = self.fixture.workspace.content.source_path(self.fixture.source_id).parent
        source_root.mkdir()
        (source_root / "cards").mkdir()
        (source_root / "source.bin").write_text("restored readable plaintext", encoding="utf-8")

        with self.assertRaises(Phase4ValidationError):
            self.fixture.service.complete_deletion(self.fixture.source_id)
        with self.assertRaises(Phase4ValidationError):
            self.fixture.workspace.verify_durable_integrity()
        with self.assertRaises(Phase4ValidationError):
            Phase4Service(self.fixture.workspace)
        with self.assertRaises(Phase4ValidationError):
            export_workspace(
                self.fixture.workspace, self.fixture.root / "restored-content.json",
                exported_at=T4,
            )
        self.assertEqual(before, self.fixture.workspace.records())
        completions = [
            record for record in before
            if record["record_type"] == RecordType.LIFECYCLE_ACTION.value
            and record["payload"]["action"] == LifecycleType.DELETION_COMPLETION.value
        ]
        self.assertEqual([completion["id"]], [record["id"] for record in completions])

        fixture = self.fixture
        workspace_root = fixture.workspace.root
        fixture.workspace.close()
        with self.assertRaises(Phase4ValidationError):
            Phase4Workspace(workspace_root)
        fixture.temp.cleanup()
        self.fixture = Phase4Fixture(self)

    def test_repeated_completion_rejects_nonregular_content_locations(self) -> None:
        scenarios = ["directory"]
        if hasattr(os, "symlink"):
            scenarios.append("symlink")
        if hasattr(os, "mkfifo"):
            scenarios.append("fifo")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                fixture = Phase4Fixture(self)
                try:
                    provenance = fixture.intake()
                    fixture.service.append_lifecycle(
                        source_id=fixture.source_id, action=LifecycleType.DELETION_REQUEST,
                        target_record_id=provenance.id, actor_id="actor.owner",
                        actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
                        reason_code="content_deletion_requested",
                        reason_detail=f"{scenario} reappearance",
                        evidence_refs=(f"evidence.{scenario}-delete",), recorded_at=T4,
                    )
                    completion = fixture.service.complete_deletion(fixture.source_id)
                    before = fixture.workspace.records()
                    source_root = fixture.workspace.content.source_path(fixture.source_id).parent
                    if scenario == "directory":
                        source_root.mkdir()
                    elif scenario == "symlink":
                        outside = fixture.root / "outside-content"
                        outside.mkdir()
                        source_root.symlink_to(outside, target_is_directory=True)
                    else:
                        os.mkfifo(source_root)
                    with self.assertRaises(Phase4ValidationError):
                        fixture.service.complete_deletion(fixture.source_id)
                    with self.assertRaises(Phase4ValidationError):
                        fixture.workspace.verify_durable_integrity()
                    self.assertEqual(before, fixture.workspace.records())
                    self.assertEqual(completion["id"], before[-1]["id"])
                finally:
                    fixture.close()

    def test_backdated_lifecycle_append_and_replay_fail_closed(self) -> None:
        provenance = self.fixture.intake()
        first = self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.REVOCATION,
            target_record_id=provenance.id, actor_id="actor.owner", actor_kind=ActorKind.HUMAN,
            authority=Authority.HUMAN_FINAL, reason_code="rights_revoked",
            reason_detail="revoked at T4", evidence_refs=("evidence.backdate",), recorded_at=T4,
        )
        for action in (LifecycleType.RESTORE, LifecycleType.CORRECTION, LifecycleType.DELETION_REQUEST, LifecycleType.TAKEDOWN):
            with self.subTest(action=action.value), self.assertRaises(ValueError):
                self.fixture.service.append_lifecycle(
                    source_id=self.fixture.source_id, action=action, target_record_id=provenance.id,
                    actor_id="actor.owner", actor_kind=ActorKind.HUMAN, authority=Authority.HUMAN_FINAL,
                    reason_code="backdated_event", reason_detail="must fail", evidence_refs=("evidence.backdated",),
                    recorded_at=T3,
                )
        second = self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.CORRECTION,
            target_record_id=provenance.id, actor_id="actor.owner", actor_kind=ActorKind.HUMAN,
            authority=Authority.HUMAN_FINAL, reason_code="provenance_corrected",
            reason_detail="valid equal-time correction", evidence_refs=("evidence.equal-time",), recorded_at=T4,
        )
        envelope = build_envelope(self.fixture.workspace.records(), exported_at=T4, source_path_hashes=self.fixture.workspace.source_path_hashes())
        target = next(item for item in envelope["records"] if item["id"] == second.id)
        target["recorded_at"] = T3
        envelope["operational_hash"] = operational_envelope_hash(envelope)
        with self.assertRaises(Phase4ValidationError):
            verify_bytes(canonical_bytes(envelope))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_fifo_intake_and_interchange_reader_reject_promptly(self) -> None:
        fifo = self.fixture.root / "source.txt"; self.fixture.source.unlink(); os.mkfifo(fifo)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        code = "from pathlib import Path; from math_research.phase4a.content_store import read_local_text; read_local_text(Path(__import__('sys').argv[1]))"
        result = subprocess.run(
            [sys.executable, "-c", code, str(fifo)], cwd=Path(__file__).resolve().parents[1],
            env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=False,
        )
        self.assertNotEqual(0, result.returncode)
        with self.assertRaises(OSError):
            read_interchange_file(fifo, max_bytes=MAX_EXPORT_BYTES)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_content_store_rejects_symlink_components_and_files(self) -> None:
        for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
            self.fixture.right(use)
        outside = self.fixture.root / "outside"; outside.mkdir()
        hashed = self.fixture.workspace.content.source_path(self.fixture.source_id).parent
        hashed.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ContentStoreError):
            self.fixture.service.intake_local(self.fixture.source, source_id=self.fixture.source_id, actor_id="actor.operator", recorded_at=T1)
        self.assertEqual([], list(outside.iterdir()))
        hashed.unlink()
        provenance = self.fixture.service.intake_local(self.fixture.source, source_id=self.fixture.source_id, actor_id="actor.operator", recorded_at=T1)
        source_path = self.fixture.workspace.content.source_path(self.fixture.source_id)
        source_path.unlink(); source_path.symlink_to(self.fixture.source)
        with self.assertRaises(OSError):
            self.fixture.workspace.content.read_source(self.fixture.source_id)
        self.assertEqual(RecordType.SOURCE_PROVENANCE, provenance.record_type)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_content_store_component_swap_cannot_escape_root(self) -> None:
        for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION, RightsUse.PARSING):
            self.fixture.right(use)
        store = self.fixture.workspace.content
        outside = self.fixture.root / "outside-swap"; outside.mkdir()
        source_name = store.object_key(self.fixture.source_id)
        moved_name = source_name + ".moved"
        real_replace = os.replace

        def swap_then_replace(source: str, target: str, **keywords: Any) -> None:
            os.rename(source_name, moved_name, src_dir_fd=store._objects_fd, dst_dir_fd=store._objects_fd)
            os.symlink(str(outside), source_name, dir_fd=store._objects_fd)
            real_replace(source, target, **keywords)

        with mock.patch("math_research.phase4a.content_store.os.replace", side_effect=swap_then_replace):
            with self.assertRaises(ContentStoreError):
                self.fixture.service.intake_local(
                    self.fixture.source, source_id=self.fixture.source_id,
                    actor_id="actor.operator", recorded_at=T1,
                )
        self.assertEqual([], list(outside.iterdir()))
        self.assertTrue(store.temporary_empty())

    def test_record_id_rename_is_rejected_for_every_record_type(self) -> None:
        card = self.fixture.card()
        self.fixture.service.review_applicability(
            source_id=self.fixture.source_id, evidence_card_id=card.id,
            status=ApplicabilityStatus.PROPOSED, outcome=ApplicabilityOutcome.UNRESOLVED,
            reason_code=ApplicabilityReason.INSUFFICIENT_EVIDENCE, reason_detail="ID mutation proposal",
            evidence_refs=(card.id,), actor_id="actor.model", actor_kind=ActorKind.MODEL,
            recorded_at=T3, checks={
                "bibliographic_identity_checked": False, "hypotheses_checked": False,
                "definitions_checked": False, "scope_exceptions_checked": False, "implication_checked": False,
            },
        )
        provenance = next(item for item in self.fixture.workspace.records() if item["record_type"] == RecordType.SOURCE_PROVENANCE.value)
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.CORRECTION,
            target_record_id=provenance["id"], actor_id="actor.owner", actor_kind=ActorKind.HUMAN,
            authority=Authority.HUMAN_FINAL, reason_code="provenance_corrected", reason_detail="ID test",
            evidence_refs=("evidence.id-test",), recorded_at=T4,
        )
        envelope = build_envelope(self.fixture.workspace.records(), exported_at=T4, source_path_hashes=self.fixture.workspace.source_path_hashes())
        for record_type in RecordType:
            with self.subTest(record_type=record_type.value):
                value = copy.deepcopy(envelope)
                target = next(item for item in value["records"] if item["record_type"] == record_type.value)
                old, renamed = target["id"], target["id"] + "-renamed"
                target["id"] = renamed
                for record in value["records"]:
                    for field in ("policy_snapshot_id", "predecessor_id", "supersedes"):
                        if record.get(field) == old:
                            record[field] = renamed
                    for field in ("target_record_id", "previous_event_id", "evidence_card_id"):
                        if isinstance(record.get("payload"), dict) and record["payload"].get(field) == old:
                            record["payload"][field] = renamed
                    record["evidence_refs"] = [renamed if item == old else item for item in record["evidence_refs"]]
                    record["content_hash"] = record_content_hash(record)
                value["content_hash"] = semantic_envelope_hash(value); value["operational_hash"] = operational_envelope_hash(value)
                with self.assertRaises(Phase4ValidationError):
                    verify_bytes(canonical_bytes(value))

    def test_cli_workspace_inspection_is_typed_restricted_and_deterministic(self) -> None:
        card = self.fixture.card()
        provenance = next(item for item in self.fixture.workspace.records() if item["record_type"] == RecordType.SOURCE_PROVENANCE.value)
        lifecycle = self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.CORRECTION,
            target_record_id=provenance["id"], actor_id="actor.owner", actor_kind=ActorKind.HUMAN,
            authority=Authority.HUMAN_FINAL, reason_code="provenance_corrected",
            reason_detail="CLI inspection", evidence_refs=("evidence.cli",), recorded_at=T3,
        )
        right = next(item for item in self.fixture.workspace.records() if item["record_type"] == RecordType.RIGHTS_DECISION.value)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        root = Path(__file__).resolve().parents[1]

        def cli(*arguments: str) -> subprocess.CompletedProcess[bytes]:
            return subprocess.run(
                [sys.executable, "-m", "math_research.phase4a_cli", *arguments], cwd=root, env=environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
            )

        commands = (
            ("inspect-rights", str(self.fixture.workspace.root), right["id"]),
            ("inspect-lifecycle", str(self.fixture.workspace.root), "--record-id", lifecycle.id),
            ("inspect-lifecycle", str(self.fixture.workspace.root), "--source-id", self.fixture.source_id),
            ("inspect-card", str(self.fixture.workspace.root), card.id, T4),
        )
        for command in commands:
            first, second = cli(*command), cli(*command)
            self.assertEqual(0, first.returncode, first.stderr.decode("utf-8", "replace"))
            self.assertEqual(first.stdout, second.stdout)
            json.loads(first.stdout)
        self.assertNotEqual(0, cli("inspect-rights", str(self.fixture.workspace.root), "rights.missing").returncode)
        self.assertNotEqual(0, cli("inspect-rights", str(self.fixture.workspace.root), card.id).returncode)
        self.fixture.service.append_lifecycle(
            source_id=self.fixture.source_id, action=LifecycleType.DELETION_REQUEST,
            target_record_id=provenance["id"], actor_id="actor.owner", actor_kind=ActorKind.HUMAN,
            authority=Authority.HUMAN_FINAL, reason_code="content_deletion_requested",
            reason_detail="delete before CLI inspection", evidence_refs=("evidence.cli-delete",), recorded_at=T4,
        )
        self.fixture.service.complete_deletion(self.fixture.source_id)
        self.assertNotEqual(0, cli("inspect-card", str(self.fixture.workspace.root), card.id, T4).returncode)

    def test_bounded_interchange_reader_exact_limit_plus_one_and_symlink(self) -> None:
        exact = self.fixture.root / "exact.json"; exact.write_bytes(b"x" * MAX_EXPORT_BYTES)
        self.assertEqual(MAX_EXPORT_BYTES, len(read_interchange_file(exact, max_bytes=MAX_EXPORT_BYTES)))
        extra = self.fixture.root / "extra.json"; extra.write_bytes(b"x" * (MAX_EXPORT_BYTES + 1))
        with self.assertRaises(ValueError):
            read_interchange_file(extra, max_bytes=MAX_EXPORT_BYTES)
        if hasattr(os, "symlink"):
            link = self.fixture.root / "link.json"; link.symlink_to(exact)
            with self.assertRaises(OSError):
                read_interchange_file(link, max_bytes=MAX_EXPORT_BYTES)

    def test_process_tree_timeout_kills_child_and_grandchild(self) -> None:
        # The child publishes both pids through an atomically renamed file instead of
        # stdout, so the handshake is readable after the group has been killed. The tree
        # still has to be fully formed before the timeout fires, which is a scheduling
        # race on a loaded machine, so the handshake gets its own bounded escalation:
        # a machine that cannot start two interpreters inside 0.2s retries with more
        # room rather than reporting zero pids.
        code = (
            "import os,signal,subprocess,sys,time;"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            "p=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)']);"
            "handshake=sys.argv[1];partial=handshake+'.partial';"
            "written=open(partial,'w');written.write(f'{os.getpid()} {p.pid}');written.close();"
            "os.replace(partial,handshake);time.sleep(60)"
        )
        pids: list[int] = []
        for attempt, timeout in enumerate((0.2, 1.0, 5.0, 25.0)):
            handshake = self.fixture.root / f"process-tree-pids-{attempt}"
            with self.assertRaises(subprocess.TimeoutExpired):
                _run_process_tree([sys.executable, "-c", code, str(handshake)], timeout=timeout)
            if handshake.exists():
                pids = [int(item) for item in handshake.read_text().split()]
                break
        self.assertEqual(2, len(pids), "child never published its own and its grandchild pid")
        for pid in pids:
            # The grandchild is reaped by init after reparenting, so allow that to land.
            for _ in range(1000):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_parent_timeout_contract_and_zero_external_inventory(self) -> None:
        with mock.patch("math_research.phase4a.interchange._run_process_tree") as run:
            run.return_value = subprocess.CompletedProcess(["true"], 0, b"", b"")
            run_with_hard_timeout(["true"])
            self.assertEqual(HARD_TIMEOUT_SECONDS, run.call_args.kwargs["timeout"])
        with self.assertRaises(ValueError):
            run_with_hard_timeout(["true"], timeout=599)


class Phase4AEmbeddingProcessorProbeTests(unittest.TestCase):
    """The nine ADR-0064 falsifiability probes, plus the rules they protect.

    ADR-0026 makes the acceptance suite the executable record of a slice's
    thresholds, so each probe mutates exactly ONE field of an otherwise valid
    input and must produce the refusal ADR-0064 names. `probes_flipped ==
    probes_total` is asserted below: a rule that cannot be made to fail proves
    nothing.
    """

    # Probe name -> the token that must appear in the observed refusal. The
    # tokens are the ADR's verbatim refusal codes wherever it fixes one.
    PROBES = {
        "pr.embedding-rights-require-processor": PROCESSOR_REQUIRED_REFUSAL,
        "pr.acquisition-rights-forbid-processor": PROCESSOR_FORBIDDEN_REFUSAL,
        "pr.processor-mismatch-blocks": RightsOutcome.PROCESSOR_NOT_AUTHORIZED.value,
        "pr.processor-omitted-for-embedding-raises": PROCESSOR_REQUIRED_REFUSAL,
        "pr.second-provider-not-inherited": RightsOutcome.PROCESSOR_NOT_AUTHORIZED.value,
        "pr.unknown-provider-refused": "provider is not an admitted live provider",
        "pr.expired-embedding-decision-blocks": RightsOutcome.EXPIRED.value,
        "pr.nonhuman-embedding-decision-refused": "rights decisions require human final evidence",
        "pr.processor-field-set-closed": "extra=['region']",
    }

    def fixture(self) -> Phase4Fixture:
        fixture = Phase4Fixture(self)
        self.addCleanup(fixture.close)
        return fixture

    def granted(self) -> Phase4Fixture:
        """An intaken source with one live embedding decision naming one processor."""

        fixture = self.fixture()
        fixture.intake()
        fixture.right(RightsUse.EMBEDDING, processor=EMBEDDING_PROCESSOR, at=T1)
        return fixture

    @staticmethod
    def _refusal(call) -> str:
        """Run one probe body and return the refusal it produced, or ``""``."""

        try:
            call()
        except (Phase4ValidationError, RightsBlocked, ValueError) as error:
            return f"{type(error).__name__}: {error}"
        return ""

    # -- the nine probes -------------------------------------------------

    def probe_embedding_rights_require_processor(self) -> str:
        fixture = self.fixture()
        return self._refusal(lambda: fixture.right(RightsUse.EMBEDDING, processor=None))

    def probe_acquisition_rights_forbid_processor(self) -> str:
        fixture = self.fixture()
        return self._refusal(
            lambda: fixture.right(RightsUse.ACQUISITION, processor=EMBEDDING_PROCESSOR)
        )

    def probe_processor_mismatch_blocks(self) -> str:
        fixture = self.granted()
        evaluation = fixture.service.evaluate_rights(
            fixture.source_id, RightsUse.EMBEDDING, at=T2,
            processor_id=SAME_PROVIDER_OTHER_MODEL.processor_id,
            provider=SAME_PROVIDER_OTHER_MODEL.provider,
            model_identifier=SAME_PROVIDER_OTHER_MODEL.model_identifier,
        )
        self.assertFalse(evaluation.allowed)
        self.assertNotEqual(RightsOutcome.PERMITTED, evaluation.outcome)
        with self.assertRaises(RightsBlocked):
            fixture.service.require_rights(
                fixture.source_id, RightsUse.EMBEDDING, at=T2,
                processor_id=SAME_PROVIDER_OTHER_MODEL.processor_id,
            provider=SAME_PROVIDER_OTHER_MODEL.provider,
            model_identifier=SAME_PROVIDER_OTHER_MODEL.model_identifier,
            )
        return evaluation.outcome.value

    def probe_processor_omitted_for_embedding_raises(self) -> str:
        fixture = self.granted()
        return self._refusal(
            lambda: fixture.service.require_rights(
                fixture.source_id, RightsUse.EMBEDDING, at=T2,
            )
        )

    def probe_second_provider_not_inherited(self) -> str:
        fixture = self.granted()
        evaluation = fixture.service.evaluate_rights(
            fixture.source_id, RightsUse.EMBEDDING, at=T2,
            processor_id=SECOND_PROVIDER_PROCESSOR.processor_id,
            provider=SECOND_PROVIDER_PROCESSOR.provider,
            model_identifier=SECOND_PROVIDER_PROCESSOR.model_identifier,
        )
        self.assertFalse(evaluation.allowed)
        self.assertNotEqual(
            EMBEDDING_PROCESSOR.provider, SECOND_PROVIDER_PROCESSOR.provider,
        )
        return evaluation.outcome.value

    def probe_unknown_provider_refused(self) -> str:
        fixture = self.fixture()
        unknown = dict(EMBEDDING_PROCESSOR.as_payload(), provider="not-a-real-provider")
        self.assertNotIn(unknown["provider"], SUPPORTED_LIVE_PROVIDERS)
        return self._refusal(
            lambda: fixture.right(RightsUse.EMBEDDING, processor=unknown)
        )

    def probe_expired_embedding_decision_blocks(self) -> str:
        fixture = self.fixture()
        fixture.right(RightsUse.EMBEDDING, processor=EMBEDDING_PROCESSOR, until=T0)
        evaluation = fixture.service.evaluate_rights(
            fixture.source_id, RightsUse.EMBEDDING, at=T1,
            processor_id=EMBEDDING_PROCESSOR.processor_id,
                provider=EMBEDDING_PROCESSOR.provider,
                model_identifier=EMBEDDING_PROCESSOR.model_identifier,
        )
        self.assertFalse(evaluation.allowed)
        self.assertNotEqual(RightsOutcome.PERMITTED, evaluation.outcome)
        return evaluation.outcome.value

    def probe_nonhuman_embedding_decision_refused(self) -> str:
        fixture = self.granted()
        decision = copy.deepcopy(
            next(
                record for record in fixture.workspace.records()
                if record["record_type"] == RecordType.RIGHTS_DECISION.value
                and record["payload"]["intended_use"] == RightsUse.EMBEDDING.value
            )
        )
        decision["actor_kind"] = ActorKind.MODEL.value
        decision["authority"] = Authority.PROPOSAL.value
        # Fully re-derive identity and hash, so the refusal is the authority rule
        # and not an incidental hash mismatch.
        decision["content_hash"] = record_content_hash(decision)
        decision["id"] = expected_record_id(decision)
        decision["content_hash"] = record_content_hash(decision)
        return self._refusal(lambda: validate_record_for_append(decision))

    def probe_processor_field_set_closed(self) -> str:
        fixture = self.fixture()
        extra = dict(EMBEDDING_PROCESSOR.as_payload(), region="eastus")
        return self._refusal(lambda: fixture.right(RightsUse.EMBEDDING, processor=extra))

    # -- the gate --------------------------------------------------------

    def test_every_adr_0061_probe_flips(self) -> None:
        flipped = {}
        for name, token in self.PROBES.items():
            with self.subTest(probe=name):
                method = getattr(self, "probe_" + name.removeprefix("pr.").replace("-", "_"))
                observed = method()
                self.assertIn(
                    token, observed,
                    f"{name} did not produce its named refusal; observed {observed!r}",
                )
                flipped[name] = observed
        probes_total, probes_flipped = len(self.PROBES), len(flipped)
        self.assertEqual(9, probes_total, "ADR-0064 names nine probes")
        self.assertEqual(probes_total, probes_flipped)

    # -- the positive side, so an all-reject implementation cannot pass ---

    def test_a_named_processor_is_permitted_and_survives_export_replay(self) -> None:
        fixture = self.granted()
        evaluation = fixture.service.require_rights(
            fixture.source_id, RightsUse.EMBEDDING, at=T2,
            processor_id=EMBEDDING_PROCESSOR.processor_id,
                provider=EMBEDDING_PROCESSOR.provider,
                model_identifier=EMBEDDING_PROCESSOR.model_identifier,
        )
        self.assertEqual(RightsOutcome.PERMITTED, evaluation.outcome)
        self.assertTrue(evaluation.allowed)
        envelope = build_envelope(
            fixture.workspace.records(), exported_at=T4,
            source_path_hashes=fixture.workspace.source_path_hashes(),
        )
        snapshot = verify_bytes(canonical_bytes(envelope))
        decisions = [
            record for record in snapshot.value()["records"]
            if record["record_type"] == RecordType.RIGHTS_DECISION.value
        ]
        embedding = [
            record for record in decisions
            if record["payload"]["intended_use"] == RightsUse.EMBEDDING.value
        ]
        self.assertEqual(
            [EMBEDDING_PROCESSOR.as_payload()],
            [record["payload"]["processor"] for record in embedding],
        )
        self.assertEqual(
            [None] * (len(decisions) - 1),
            [
                record["payload"]["processor"] for record in decisions
                if record["payload"]["intended_use"] != RightsUse.EMBEDDING.value
            ],
        )

    def test_reused_processor_id_cannot_change_provider_or_model(self) -> None:
        fixture = self.granted()
        for provider, model_identifier in (
            ("openai", EMBEDDING_PROCESSOR.model_identifier),
            (EMBEDDING_PROCESSOR.provider, "text-embedding-3-small"),
        ):
            with self.subTest(provider=provider, model_identifier=model_identifier):
                evaluation = fixture.service.evaluate_rights(
                    fixture.source_id, RightsUse.EMBEDDING, at=T2,
                    processor_id=EMBEDDING_PROCESSOR.processor_id,
                    provider=provider, model_identifier=model_identifier,
                )
                self.assertEqual(RightsOutcome.PROCESSOR_NOT_AUTHORIZED, evaluation.outcome)
                self.assertFalse(evaluation.allowed)

    def test_model_context_also_requires_its_own_processor(self) -> None:
        fixture = self.fixture()
        self.assertEqual(
            {RightsUse.EMBEDDING, RightsUse.MODEL_CONTEXT}, set(DISCLOSING_RIGHTS_USES),
        )
        with self.assertRaises(Phase4ValidationError) as refused:
            fixture.right(RightsUse.MODEL_CONTEXT, processor=None)
        self.assertIn(PROCESSOR_REQUIRED_REFUSAL, str(refused.exception))
        local = Processor(
            processor_id="processor.local.exact-text-embedding",
            provider="openai", model_identifier="local-exact-embedding",
            disclosure_kind=DisclosureKind.TEXT_STAYS_LOCAL,
        )
        fixture.right(RightsUse.MODEL_CONTEXT, processor=local)
        self.assertEqual(
            RightsOutcome.PERMITTED,
            fixture.service.evaluate_rights(
                fixture.source_id, RightsUse.MODEL_CONTEXT, at=T1,
                processor_id=local.processor_id,
                provider=local.provider, model_identifier=local.model_identifier,
            ).outcome,
        )

    def test_every_non_disclosing_use_refuses_a_processor(self) -> None:
        for use in RightsUse:
            if use in DISCLOSING_RIGHTS_USES:
                continue
            with self.subTest(use=use.value):
                fixture = self.fixture()
                with self.assertRaises(Phase4ValidationError) as refused:
                    fixture.right(use, processor=EMBEDDING_PROCESSOR)
                self.assertIn(PROCESSOR_FORBIDDEN_REFUSAL, str(refused.exception))
                # Naming a processor when asking is a programming error too.
                with self.assertRaises(ValueError) as asked:
                    fixture.service.evaluate_rights(
                        fixture.source_id, use, at=T1,
                        processor_id=EMBEDDING_PROCESSOR.processor_id,
                provider=EMBEDDING_PROCESSOR.provider,
                model_identifier=EMBEDDING_PROCESSOR.model_identifier,
                    )
                self.assertIn(PROCESSOR_FORBIDDEN_REFUSAL, str(asked.exception))

    def test_both_validation_paths_close_the_field_set_together(self) -> None:
        """A record that validates on append must not fail on durable re-verify.

        ADR-0064 calls this out as load-bearing, so each mutation is asserted
        against the append path AND the durable path.
        """

        fixture = self.granted()
        records = [copy.deepcopy(record) for record in fixture.workspace.records()]
        paths = fixture.workspace.source_path_hashes()
        validate_durable_records(records, source_path_hashes=paths)
        index = next(
            position for position, record in enumerate(records)
            if record["record_type"] == RecordType.RIGHTS_DECISION.value
            and record["payload"]["intended_use"] == RightsUse.EMBEDDING.value
        )
        mutations = (
            lambda payload: payload.__setitem__("processor", None),
            lambda payload: payload["processor"].__setitem__("region", "eastus"),
            lambda payload: payload["processor"].pop("disclosure_kind"),
            lambda payload: payload["processor"].__setitem__("provider", "not-a-real-provider"),
            lambda payload: payload["processor"].__setitem__("model_identifier", ""),
            lambda payload: payload["processor"].__setitem__("disclosure_kind", "text_maybe_leaves"),
            lambda payload: payload.__delitem__("processor"),
        )
        for position, mutate in enumerate(mutations):
            with self.subTest(mutation=position):
                mutated = [copy.deepcopy(record) for record in records]
                mutate(mutated[index]["payload"])
                mutated[index]["content_hash"] = record_content_hash(mutated[index])
                with self.assertRaises(Phase4ValidationError):
                    validate_record_for_append(mutated[index])
                with self.assertRaises(Phase4ValidationError):
                    validate_durable_records(mutated, source_path_hashes=paths)

    def test_the_schema_processor_provider_enum_tracks_the_single_allowlist(self) -> None:
        schema = json.loads(schema_path().read_text(encoding="utf-8"))
        processor = schema["$defs"]["processor"]
        self.assertEqual(
            sorted(SUPPORTED_LIVE_PROVIDERS), sorted(processor["properties"]["provider"]["enum"]),
            "the Phase 4A processor provider enum has drifted from SUPPORTED_LIVE_PROVIDERS",
        )
        self.assertEqual(
            sorted(item.value for item in DisclosureKind),
            sorted(processor["properties"]["disclosure_kind"]["enum"]),
        )
        self.assertEqual(
            ["disclosure_kind", "model_identifier", "processor_id", "provider"],
            sorted(processor["required"]),
        )
        self.assertIn("processor", schema["$defs"]["rights"]["required"])
        self.assertEqual(PRODUCTION_SCHEMA_SHA256, validate_schema_contract())


if __name__ == "__main__":
    unittest.main()
