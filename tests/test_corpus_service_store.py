"""ADR-0072 Slice 3 acceptance: the persistent corpus service.

The load-bearing test is the exit criterion: two separate runs against the
same data root see the same content-addressed corpus generation and the second
run reacquires nothing.  Everything else here proves the fail-closed edges —
git-tree refusal, immutability, append-only ledgers, policy-derived rights
recording obligations, quarantine, and takedown tombstones.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from math_research.corpus_service.activation import (
    STATUS_PENDING,
    load_production_activation,
    require_active,
)
from math_research.corpus_service.constants import LIVE_SNAPSHOT_ACKNOWLEDGEMENT
from math_research.corpus_service.dataroot import (
    initialize_data_root,
    object_exists,
    object_path,
    ordinary_cleanup,
    read_object,
    write_object,
)
from math_research.corpus_service.derivation import (
    derive_document_rights,
    source_id_for,
    verify_derived_decision,
    _seal as seal_decision,
)
from math_research.corpus_service.errors import (
    ArchiveDocumentMismatchError,
    DataRootInsideGitTreeError,
    DerivedDecisionMissingPolicyHashError,
    DerivedDecisionMissingRuleIdError,
    GenerationInvalidatedError,
    GenerationInvalidError,
    LedgerChainBrokenError,
    NonHumanDerivedDecisionRefusedError,
    ObjectHashMismatchError,
    ObjectMissingError,
    ObjectOverwriteRefusedError,
    PolicyNotHumanAuthoredError,
    ProcessorWildcardForbiddenError,
    SnapshotAcquisitionNotActiveError,
    TrancheBoundExceededError,
)
from math_research.corpus_service.generation import (
    load_generation,
    record_takedown,
    require_active_generation,
    verify_generation,
)
from math_research.corpus_service.ledger import append_ledger, ledger_path, read_ledger
from math_research.corpus_service.policy import load_policy, validate_policy
from math_research.corpus_service.ports import DirectoryArchiveSource
from math_research.corpus_service.rightsstore import PolicyDerivedRightsWriter
from math_research.corpus_service.serialization import (
    canonical_bytes,
    sealed,
    sha256_bytes,
)
from math_research.corpus_service.service import ingest_tranche
from math_research.corpus_service.snapshot import (
    load_archive_manifest,
    load_tranche_config,
)
from math_research.corpus_service.spans import verify_spans_against_source
from math_research.phase4a.records import RightsUse
from math_research.phase4a.service import Phase4Service, RightsBlocked
from math_research.phase4a.workspace import Phase4Workspace

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures" / "corpus-service"
POLICY_PATH = FIXTURES / "fixture-source-rights-policy-v1.json"
ARCHIVE_ROOT = FIXTURES / "fixture-snapshot-archive-v1"
TRANCHE_PATH = FIXTURES / "fixture-tranche-config-v1.json"
ACTIVATION_PATH = REPO / "config" / "corpus-service-snapshot-activation-v1.json"

POLICY_HASH = "sha256:baf9a63c1d526f4a6f2fb846358b16dc3108405a492968753b6ad5d242892c6c"
ARCHIVE_HASH = "sha256:9380f436853a09ce8f4a7003054d9554fc4ade172e07422be8ae801981c68e19"

T0 = "2026-08-22T00:00:00Z"
T1 = "2026-08-22T01:00:00Z"
T2 = "2026-08-22T02:00:00Z"
T3 = "2026-08-22T03:00:00Z"


def _policy() -> dict:
    return load_policy(POLICY_PATH.read_bytes())


def _tranche() -> dict:
    return load_tranche_config(TRANCHE_PATH.read_bytes())


def _archive() -> DirectoryArchiveSource:
    return DirectoryArchiveSource(ARCHIVE_ROOT)


def _init(root: Path) -> None:
    initialize_data_root(root, data_root_id="dataroot.test", initialized_at=T0)


def _ingest(root: Path, run_id: str, recorded_at: str) -> dict:
    return ingest_tranche(
        root, policy=_policy(), archive=_archive(), tranche_config=_tranche(),
        run_id=run_id, recorded_at=recorded_at,
    )


class TwoRunPersistenceTests(unittest.TestCase):
    """The Slice 3 exit criterion, plus grow-only lifecycle."""

    def test_second_run_sees_same_generation_and_reacquires_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            first = _ingest(root, "run.first", T1)
            self.assertEqual(6, first["documents_acquired"])
            self.assertEqual(0, first["documents_reused"])
            self.assertTrue(first["generation_published"])

            # A separate run: fresh objects, same data root, later time.
            second = _ingest(root, "run.second", T2)
            self.assertEqual(0, second["documents_acquired"])
            self.assertEqual(6, second["documents_reused"])
            self.assertFalse(second["generation_published"])
            self.assertEqual(first["generation_id"], second["generation_id"])
            self.assertEqual(first["generation_hash"], second["generation_hash"])

            # The published manifest is one immutable, content-addressed file.
            manifest = load_generation(root, first["generation_id"])
            self.assertEqual(first["generation_hash"], manifest["content_hash"])
            publications = [
                record for record in read_ledger(root, "lineage")
                if record["kind"] == "generation_published"
            ]
            self.assertEqual(1, len(publications))
            # Both runs left usage records; history is append-only.
            usage = read_ledger(root, "usage")
            self.assertEqual(
                ["run.first", "run.second"],
                [record["payload"]["run_id"] for record in usage],
            )

    def test_admission_quarantine_and_rights_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            report = _ingest(root, "run.first", T1)
            self.assertEqual(3, report["documents_admitted"])
            self.assertEqual(3, report["documents_quarantined"])
            self.assertEqual(
                {"doc-parse-failure", "doc-unknown-licence", "doc-unsupported-format"},
                set(report["quarantine_reasons"]),
            )
            self.assertFalse(report["retrieval_indexed"])
            self.assertEqual(0, report["network_requests"])
            self.assertEqual(0, report["documents_with_applicability_record"])

            manifest = load_generation(root, report["generation_id"])
            by_id = {entry["document_id"]: entry for entry in manifest["entries"]}
            self.assertEqual(
                {"doc-metadata-gamma", "doc-open-alpha", "doc-open-beta"},
                set(by_id),
            )
            # Full text and exact spans only where the derived rights permit.
            self.assertTrue(by_id["doc-open-alpha"]["full_text_stored"])
            self.assertIsNotNone(by_id["doc-open-alpha"]["spans_sha256"])
            self.assertFalse(by_id["doc-metadata-gamma"]["full_text_stored"])
            self.assertIsNone(by_id["doc-metadata-gamma"]["spans_sha256"])
            # ADR-0072 §7 recording obligation, echoed into the generation.
            for entry in by_id.values():
                self.assertEqual(POLICY_HASH, entry["policy_content_hash"])
                self.assertIn("licence", entry["licence_inputs"])
                self.assertTrue(entry["rule_id"].startswith("rule."))
            self.assertEqual(
                {"value": "prohibited", "processor_id": None},
                by_id["doc-metadata-gamma"]["embedding"],
            )
            self.assertEqual("allowed", by_id["doc-open-alpha"]["embedding"]["value"])
            # Quarantined documents are recorded and retained, not discarded.
            quarantined = {
                item["document_id"]: item for item in manifest["quarantined"]
            }
            self.assertEqual("licence_unknown", quarantined["doc-unknown-licence"]["quarantine_reason"])
            self.assertTrue(object_exists(root, quarantined["doc-unknown-licence"]["source_sha256"]))

    def test_spans_reproduce_exact_text_from_immutable_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            report = _ingest(root, "run.first", T1)
            manifest = load_generation(root, report["generation_id"])
            entry = next(
                item for item in manifest["entries"]
                if item["document_id"] == "doc-open-alpha"
            )
            spans_doc = json.loads(read_object(root, entry["spans_sha256"]))
            body = read_object(root, entry["source_sha256"])
            verify_spans_against_source(spans_doc, body)
            self.assertEqual(2, spans_doc["span_count"])

    def test_phase4a_machinery_governs_disclosing_uses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            _ingest(root, "run.first", T1)
            writer = PolicyDerivedRightsWriter(
                root, actor_id="human.repository-owner", valid_from=T1,
                valid_until=None,
            )
            open_id = source_id_for("doc-open-alpha")
            shard = writer.locate(open_id)
            self.assertIsNotNone(shard)
            with Phase4Workspace(writer.shard_root(shard)) as workspace:
                service = Phase4Service(workspace)
                evaluation = service.require_rights(
                    open_id, RightsUse.EMBEDDING, at=T2,
                    processor_id="processor.openai.synthetic-fixture-embedding",
                    provider="openai",
                    model_identifier="synthetic-fixture-embedding-v1",
                )
                self.assertTrue(evaluation.allowed)
                # A second processor is a second decision, never inherited.
                with self.assertRaises(RightsBlocked):
                    service.require_rights(
                        open_id, RightsUse.EMBEDDING, at=T2,
                        processor_id="processor.other.embedder",
                        provider="openai", model_identifier="other-v1",
                    )
                # The metadata-only document has no embedding decision at all.
                metadata_id = source_id_for("doc-metadata-gamma")
                with self.assertRaises(RightsBlocked):
                    service.require_rights(
                        metadata_id, RightsUse.EMBEDDING, at=T2,
                        processor_id="processor.openai.synthetic-fixture-embedding",
                        provider="openai",
                        model_identifier="synthetic-fixture-embedding-v1",
                    )


class TakedownTests(unittest.TestCase):
    def test_takedown_tombstones_invalidates_and_revokes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            first = _ingest(root, "run.first", T1)
            writer = PolicyDerivedRightsWriter(
                root, actor_id="human.repository-owner", valid_from=T2,
                valid_until=None,
            )
            manifest = load_generation(root, first["generation_id"])
            entry = next(
                item for item in manifest["entries"]
                if item["document_id"] == "doc-open-beta"
            )
            tombstone = record_takedown(
                root, document_id="doc-open-beta",
                reason_detail="synthetic takedown drill",
                actor_id="human.repository-owner", recorded_at=T2,
                rights_writer=writer,
            )
            payload = tombstone["payload"]
            # Non-reconstructive: hashes and identifiers only, no content.
            self.assertNotIn("text", json.dumps(sorted(payload)))
            self.assertEqual(entry["source_sha256"], payload["source_sha256"])
            self.assertEqual(
                [first["generation_id"]], payload["dependent_generation_ids"],
            )
            self.assertTrue(payload["phase4a_revocation_record_ids"])
            # Bytes are out of active use.
            self.assertFalse(object_path(root, entry["source_sha256"]).exists())
            self.assertFalse(object_path(root, entry["spans_sha256"]).exists())
            # The dependent generation is invalidated for active use.
            with self.assertRaises(GenerationInvalidatedError):
                require_active_generation(root, first["generation_id"])
            # ...but retained for audit.
            self.assertEqual(
                first["generation_hash"],
                load_generation(root, first["generation_id"])["content_hash"],
            )
            # Phase 4A now evaluates every use prohibited (revocation stands).
            shard = writer.locate(source_id_for("doc-open-beta"))
            with Phase4Workspace(writer.shard_root(shard)) as workspace:
                service = Phase4Service(workspace)
                with self.assertRaises(RightsBlocked):
                    service.require_rights(
                        source_id_for("doc-open-beta"),
                        RightsUse.STORAGE_AND_RETENTION, at=T3,
                    )
            # A later run publishes a NEW generation without the document; the
            # takedown is not undone by re-ingesting the same archive.
            third = _ingest(root, "run.third", T3)
            self.assertTrue(third["generation_published"])
            self.assertNotEqual(first["generation_id"], third["generation_id"])
            self.assertEqual(1, third["documents_tombstone_skipped"])
            active = require_active_generation(root, third["generation_id"])
            self.assertEqual(
                ["doc-open-beta"], active["tombstoned_document_ids"],
            )
            self.assertNotIn(
                "doc-open-beta",
                [item["document_id"] for item in active["entries"]],
            )


class FailClosedTests(unittest.TestCase):
    def test_policy_for_another_archive_is_refused_before_writes(self) -> None:
        policy = json.loads(POLICY_PATH.read_text())
        policy["archive"]["archive_id"] = "snapshot.other"
        policy["content_hash"] = None
        policy = sealed(policy)
        config = dict(_tranche())
        config["policy_content_hash"] = policy["content_hash"]
        config["content_hash"] = None
        config = sealed(config)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            with self.assertRaisesRegex(Exception, "different archive identity"):
                ingest_tranche(
                    root, policy=policy, archive=_archive(), tranche_config=config,
                    run_id="run.wrong-archive", recorded_at=T1,
                )
            self.assertEqual([], read_ledger(root, "acquisitions"))

    def test_same_run_id_replays_terminal_report_without_duplicate_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            first = _ingest(root, "run.same", T1)
            second = _ingest(root, "run.same", T1)
            self.assertEqual(first, second)
            self.assertEqual(1, len(read_ledger(root, "usage")))

    def test_data_root_inside_git_tree_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fake_repo = Path(temporary) / "repo"
            fake_repo.joinpath(".git").mkdir(parents=True)
            with self.assertRaises(DataRootInsideGitTreeError):
                initialize_data_root(
                    fake_repo / "data", data_root_id="dataroot.test",
                    initialized_at=T0,
                )

    def test_object_store_is_write_once_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            digest = write_object(root, b"immutable bytes\n")
            self.assertEqual(digest, write_object(root, b"immutable bytes\n"))
            # Same hash slot occupied by different bytes: refused, not replaced.
            object_path(root, digest).write_bytes(b"tampered\n")
            with self.assertRaises(ObjectOverwriteRefusedError):
                write_object(root, b"immutable bytes\n")

    def test_object_read_refuses_absence_and_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            digest = write_object(root, b"immutable bytes\n")
            absent = "sha256:" + "0" * 64
            with self.assertRaises(ObjectMissingError):
                read_object(root, absent)
            object_path(root, digest).write_bytes(b"tampered\n")
            with self.assertRaises(ObjectHashMismatchError):
                read_object(root, digest)

    def test_ledger_tampering_breaks_the_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            append_ledger(root, "usage", kind="corpus_used", recorded_at=T1, payload={"run_id": "run.a"})
            append_ledger(root, "usage", kind="corpus_used", recorded_at=T2, payload={"run_id": "run.b"})
            path = ledger_path(root, "usage")
            lines = path.read_bytes().splitlines(keepends=True)
            path.write_bytes(lines[1])  # drop the first record
            with self.assertRaises(LedgerChainBrokenError):
                read_ledger(root, "usage")

    def test_ordinary_cleanup_never_touches_corpus_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            report = _ingest(root, "run.first", T1)
            root.joinpath("scratch", "run").mkdir(parents=True)
            root.joinpath("scratch", "run", "temp.json").write_bytes(b"{}\n")
            before = sorted(
                str(path.relative_to(root))
                for path in root.joinpath("objects").rglob("*.bin")
            )
            removed = ordinary_cleanup(root)
            self.assertTrue(all(item.startswith("scratch") for item in removed))
            after = sorted(
                str(path.relative_to(root))
                for path in root.joinpath("objects").rglob("*.bin")
            )
            self.assertEqual(before, after)
            self.assertEqual(
                report["generation_hash"],
                load_generation(root, report["generation_id"])["content_hash"],
            )

    def test_tranche_bounds_refuse_rather_than_truncate(self) -> None:
        config = dict(_tranche())
        config["max_documents"] = 2
        config["content_hash"] = None
        config = sealed(config)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            with self.assertRaises(TrancheBoundExceededError):
                ingest_tranche(
                    root, policy=_policy(), archive=_archive(),
                    tranche_config=config, run_id="run.first", recorded_at=T1,
                )

    def test_corrupt_archive_bytes_are_refused_not_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy_root = Path(temporary) / "archive"
            copy_root.joinpath("documents").mkdir(parents=True)
            for path in ARCHIVE_ROOT.rglob("*"):
                if path.is_file():
                    target = copy_root / path.relative_to(ARCHIVE_ROOT)
                    target.write_bytes(path.read_bytes())
            corrupted = copy_root / "documents" / "doc-open-alpha.txt"
            corrupted.write_bytes(corrupted.read_bytes() + b"tamper\n")
            root = Path(temporary) / "data"
            _init(root)
            with self.assertRaises(ArchiveDocumentMismatchError):
                ingest_tranche(
                    root, policy=_policy(),
                    archive=DirectoryArchiveSource(copy_root),
                    tranche_config=_tranche(), run_id="run.first",
                    recorded_at=T1,
                )

    def test_generation_mutation_and_retrieval_claim_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _init(root)
            report = _ingest(root, "run.first", T1)
            manifest = load_generation(root, report["generation_id"])
            mutated = dict(manifest)
            mutated["retrieval_indexed"] = True
            with self.assertRaises(GenerationInvalidError):
                verify_generation(mutated)
            mutated = json.loads(json.dumps(manifest))
            mutated["entries"][0]["rule_id"] = "rule.other"
            with self.assertRaises(GenerationInvalidError):
                verify_generation(mutated)


class PolicyAndDerivationTests(unittest.TestCase):
    def test_fixture_hashes_are_literal_pins(self) -> None:
        self.assertEqual(POLICY_HASH, _policy()["content_hash"])
        manifest = load_archive_manifest(_archive().manifest_bytes())
        self.assertEqual(ARCHIVE_HASH, manifest["content_hash"])
        config = _tranche()
        self.assertEqual(ARCHIVE_HASH, config["archive_manifest_hash"])
        self.assertEqual(POLICY_HASH, config["policy_content_hash"])

    def test_model_authored_policy_is_refused(self) -> None:
        policy = dict(_policy())
        policy["authored_by"] = {
            "actor_id": "model.claude", "actor_kind": "model",
            "authority": "human_final",
        }
        policy["content_hash"] = None
        with self.assertRaises(PolicyNotHumanAuthoredError):
            validate_policy(sealed(policy))
        policy["authored_by"] = {
            "actor_id": "human.repository-owner", "actor_kind": "human",
            "authority": "proposal",
        }
        with self.assertRaises(PolicyNotHumanAuthoredError):
            validate_policy(sealed(policy))

    def test_wildcard_processor_is_refused(self) -> None:
        policy = json.loads(POLICY_PATH.read_text())
        open_rule = next(
            rule for rule in policy["rules"]
            if rule["rule_id"] == "rule.synthetic-open-access"
        )
        open_rule["embedding"]["processor"]["model_identifier"] = "*"
        policy["content_hash"] = None
        with self.assertRaises(ProcessorWildcardForbiddenError):
            validate_policy(sealed(policy))

    def test_derived_decision_records_the_three_obligations(self) -> None:
        manifest = load_archive_manifest(_archive().manifest_bytes())
        document = next(
            item for item in manifest["documents"]
            if item["document_id"] == "doc-open-alpha"
        )
        decision = derive_document_rights(_policy(), document)
        self.assertEqual(POLICY_HASH, decision["policy_content_hash"])
        self.assertEqual("rule.synthetic-open-access", decision["rule_id"])
        self.assertEqual(
            document["licence"]["licence"], decision["licence_inputs"]["licence"],
        )
        # Determinism: derivation is a function.
        again = derive_document_rights(_policy(), document)
        self.assertEqual(decision["content_hash"], again["content_hash"])

    def test_decision_missing_obligations_or_nonhuman_refuses(self) -> None:
        manifest = load_archive_manifest(_archive().manifest_bytes())
        document = next(
            item for item in manifest["documents"]
            if item["document_id"] == "doc-open-alpha"
        )
        decision = derive_document_rights(_policy(), document)

        mutated = dict(decision)
        mutated["policy_content_hash"] = None
        with self.assertRaises(DerivedDecisionMissingPolicyHashError):
            verify_derived_decision(seal_decision(dict(mutated)))

        mutated = dict(decision)
        mutated["rule_id"] = None
        with self.assertRaises(DerivedDecisionMissingRuleIdError):
            verify_derived_decision(seal_decision(dict(mutated)))

        mutated = dict(decision)
        mutated["authored_by"] = {
            "actor_id": "model.claude", "actor_kind": "model",
            "authority": "human_final",
        }
        with self.assertRaises(NonHumanDerivedDecisionRefusedError):
            verify_derived_decision(seal_decision(dict(mutated)))

        mutated = dict(decision)
        mutated["authored_by"] = {
            "actor_id": "human.repository-owner", "actor_kind": "human",
            "authority": "proposal",
        }
        with self.assertRaises(NonHumanDerivedDecisionRefusedError):
            verify_derived_decision(seal_decision(dict(mutated)))

    def test_quarantine_never_admits_and_never_prompts(self) -> None:
        manifest = load_archive_manifest(_archive().manifest_bytes())
        unknown = next(
            item for item in manifest["documents"]
            if item["document_id"] == "doc-unknown-licence"
        )
        decision = derive_document_rights(_policy(), unknown)
        self.assertEqual("quarantined", decision["status"])
        self.assertEqual("licence_unknown", decision["quarantine_reason"])
        self.assertIsNone(decision["uses"])
        self.assertEqual(
            "LicenseRef-AdaIvy-Synthetic-Unclassified",
            decision["licence_inputs"]["licence"],
        )


class ActivationGateTests(unittest.TestCase):
    def test_shipped_activation_is_pending_and_gate_refuses(self) -> None:
        record = load_production_activation(ACTIVATION_PATH.read_bytes())
        self.assertEqual(STATUS_PENDING, record["status"])
        with self.assertRaises(SnapshotAcquisitionNotActiveError):
            require_active(record, acknowledgement=LIVE_SNAPSHOT_ACKNOWLEDGEMENT)

    def test_active_record_still_needs_the_exact_acknowledgement(self) -> None:
        record = dict(load_production_activation(ACTIVATION_PATH.read_bytes()))
        record["status"] = "active"
        record["content_hash"] = None
        record = sealed(record)
        with self.assertRaises(SnapshotAcquisitionNotActiveError):
            require_active(record, acknowledgement=None)
        with self.assertRaises(SnapshotAcquisitionNotActiveError):
            require_active(record, acknowledgement="i_acknowledge")


if __name__ == "__main__":
    unittest.main()
