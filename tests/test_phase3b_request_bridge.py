"""Acceptance suite for the ADR-0043 Phase 2 to Phase 3B request bridge.

Nothing here needs the sealed ADR-0016 image: constructing a request is not
executing one, and the one finding this suite builds is produced by the pure
`verify_output` classification path over a synthetic execution.

The load-bearing negative property is the one the suite states loudest: the
bridge does NOT check that the Phase 2 prose payload and the supplied Lean say
the same thing, and a deliberately mismatched pair is carried through with the
correspondence marked unattested rather than refused.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from dataclasses import dataclass, replace
from pathlib import Path

from math_research.domain.entities import OpaqueId, oid
from math_research.phase2.artifacts import FileArtifactStore
from math_research.phase2.baseline_loop import BaselineResearchLoop, deterministic_fake_results
from math_research.phase2.demonstration import DemoClock
from math_research.phase2.fixtures import build_open_theorem_dossier
from math_research.phase2.model_gateway import ScriptedModelGateway
from math_research.phase2.records import BudgetLimits, ProposalRecord, VerifierIndependence
from math_research.phase2.sqlite_workspace import SQLiteWorkspace
from math_research.phase3b import SCHEMA_VERSION
from math_research.phase3b.adapter import DockerLeanAdapter
from math_research.phase3b.bridge import (
    BRIDGE_CORRESPONDENCE_CHECK, BRIDGE_DATABASE_NAME, BRIDGE_HASH_PROFILE, BRIDGE_RECORD_TYPE,
    CORRESPONDENCE_OPERATOR_ASSERTED, CORRESPONDENCE_UNATTESTED, BridgeInputs, BridgeRefusal,
    BridgeStore, bridge_content_hash, bridge_from_paths, build_bridged_request,
    build_correspondence_attestation, open_phase2_sources, parse_bridged_record,
    request_bytes_of, resolve_correspondence, trace_finding, validate_bridged_record_dict,
)
from math_research.phase3b.records import (
    FormalCheckOutcome, RawExecution, SourceKind, StreamCapture,
)
from math_research.phase3b.serialization import canonical_bytes, canonical_hash, public_value, sha256_bytes
from math_research.phase3b.validation import parse_request_bytes
from math_research.phase3b.workspace import FormalCheckWorkspace
from math_research.phase3b.wrapper import generate_wrapper
from math_research.phase3b_cli import main as phase3b_main

FIXTURES = Path("fixtures/phase3b/bridge")
TARGET = FIXTURES / "even-sum-target.lean"
PROOF = FIXTURES / "even-sum-proof.lean"
MISMATCHED_TARGET = FIXTURES / "deliberate-mismatch-mod-four-target.lean"
INSTANT = "2026-08-21T00:00:00Z"
LATER = "2026-08-21T01:00:00Z"
RUN_ID = "run.bridge.acceptance.v1"
PROPOSER_ID = f"proposal.{RUN_ID}.proposer"
VERIFIER_ID = f"proposal.{RUN_ID}.verifier"


def build_phase2_run(root: Path) -> None:
    """Drive the real Phase 2 baseline loop to a committed proposal."""
    artifacts = FileArtifactStore(root / "artifacts")
    workspace = SQLiteWorkspace(root / "workspace.sqlite3")
    clock = DemoClock()
    dossier = build_open_theorem_dossier()
    proposer, verifier = deterministic_fake_results(
        dossier.formalization.target_claim_id.value,
        dossier.formalization.assumption_claim_ids[0].value,
    )
    gateway = ScriptedModelGateway({"proposer": [proposer], "verifier": [verifier]})
    loop = BaselineResearchLoop(
        workspace=workspace, artifacts=artifacts, proposer=gateway, verifier=gateway,
        independence=VerifierIndependence(
            context_isolated=True, separate_model_call=True, different_model=False,
            different_provider=False, deterministic_checker=False,
            independently_implemented_checker=False, formal_kernel=False,
        ),
        now=clock,
    )
    run = loop.start(
        run_id=oid(RUN_ID), dossier=dossier,
        limits=BudgetLimits(
            max_input_tokens=30_000, max_output_tokens=5_000, max_cost_microusd=10_000_000,
            max_wall_milliseconds=600_000, max_attempts=6,
        ),
    )
    loop.run_to_terminal(run.run_id)
    workspace.close()


def inputs(root: Path, **overrides: object) -> BridgeInputs:
    base = {
        "phase2_workspace": root,
        "artifact_root": root / "artifacts",
        "run_id": RUN_ID,
        "proposal_id": PROPOSER_ID,
        "target_statement_path": TARGET,
        "proof_fragment_path": PROOF,
        "lean_source_kind": SourceKind.OPERATOR,
        "created_at": INSTANT,
        "lean_authored_by": "operator.acceptance",
    }
    base.update(overrides)
    return BridgeInputs(**base)  # type: ignore[arg-type]


def capture(text: str) -> StreamCapture:
    data = text.encode()
    return StreamCapture(len(data), sha256_bytes(data), text, len(data), False)


def synthetic_execution() -> RawExecution:
    """A kernel-clean execution transcript. No container is involved."""
    return RawExecution(
        0, "completed", 11,
        capture('{"severity":"information","data":"does not depend on any axioms"}\n'),
        capture(""), True, (),
    )


@dataclass(frozen=True, slots=True)
class FakePhase2Source:
    """Narrow `Phase2ProposalSource` double used for identity-mismatch cases."""

    run: object
    dossier: object
    proposals: tuple[ProposalRecord, ...]

    def get_run(self, run_id: OpaqueId):  # noqa: ANN201 - Protocol shape
        if run_id != self.run.run_id:
            raise KeyError(run_id.value)
        return self.run

    def load_dossier(self, dossier_id: OpaqueId):  # noqa: ANN201 - Protocol shape
        return self.dossier

    def list_proposals(self, run_id: OpaqueId) -> tuple[ProposalRecord, ...]:
        return self.proposals


@dataclass(frozen=True, slots=True)
class FakeArtifacts:
    payloads: dict[str, bytes]

    def exists(self, content_hash: str) -> bool:
        return content_hash in self.payloads

    def get(self, content_hash: str) -> bytes:
        return self.payloads[content_hash]


class BridgeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.phase2 = self.root / "phase2"
        self.phase2.mkdir()
        build_phase2_run(self.phase2)
        self.dossier = build_open_theorem_dossier()

    def build(self, **overrides: object):  # noqa: ANN201 - returns BridgeResult
        return bridge_from_paths(inputs(self.phase2, **overrides))

    def store(self, name: str = "phase3b") -> BridgeStore:
        store = BridgeStore(self.root / name)
        self.addCleanup(store.close)
        return store

    def findings(self, name: str = "phase3b") -> FormalCheckWorkspace:
        workspace = FormalCheckWorkspace(self.root / name)
        self.addCleanup(workspace.close)
        return workspace


class BridgedRequestTests(BridgeTestCase):
    def test_bridged_request_is_accepted_by_the_phase3b_validator(self) -> None:
        result = self.build()
        request = parse_request_bytes(result.request_bytes)
        self.assertEqual(request.claim_id, self.dossier.formalization.target_claim_id)
        self.assertEqual(request.semantic_alignment_id, self.dossier.semantic_alignment.id)
        self.assertIs(request.source_kind, SourceKind.OPERATOR)
        self.assertEqual(request.schema_version, SCHEMA_VERSION)
        self.assertEqual(request.target_statement, TARGET.read_text().strip())
        self.assertEqual(request.proof_fragment, PROOF.read_text().strip())
        self.assertEqual(canonical_hash(request), result.record.request_canonical_hash)
        self.assertEqual(sha256_bytes(result.request_bytes), result.record.request_bytes_hash)
        # The generated wrapper binds the same request, so a finding can be
        # matched back to this record by either hash.
        self.assertEqual(generate_wrapper(request).manifest.source_hash, result.record.request_canonical_hash)

    def test_two_builds_from_the_same_inputs_are_byte_identical(self) -> None:
        first, second = self.build(), self.build()
        self.assertEqual(first.request_bytes, second.request_bytes)
        self.assertEqual(canonical_bytes(first.record), canonical_bytes(second.record))
        self.assertEqual(first.record.content_hash, second.record.content_hash)
        self.assertEqual(first.record.operational_hash, second.record.operational_hash)
        self.assertEqual(first.record.bridge_id, second.record.bridge_id)
        self.assertEqual(request_bytes_of(first.record), first.request_bytes)

    def test_moving_the_input_files_changes_only_the_operational_hash(self) -> None:
        first = self.build()
        moved = self.root / "elsewhere"
        moved.mkdir()
        shutil.copy(TARGET, moved / "t.lean")
        shutil.copy(PROOF, moved / "p.lean")
        second = self.build(target_statement_path=moved / "t.lean", proof_fragment_path=moved / "p.lean")
        self.assertEqual(first.request_bytes, second.request_bytes)
        self.assertEqual(first.record.content_hash, second.record.content_hash)
        self.assertNotEqual(first.record.operational_hash, second.record.operational_hash)

    def test_a_trailing_newline_is_byte_incidental_not_semantic(self) -> None:
        variant = self.root / "variant.lean"
        variant.write_text(TARGET.read_text().strip() + "\n\n\n")
        first = self.build()
        second = self.build(target_statement_path=variant)
        self.assertEqual(first.request_bytes, second.request_bytes)
        self.assertEqual(first.record.content_hash, second.record.content_hash)
        self.assertNotEqual(
            first.record.operational.target_statement_source_bytes_hash,
            second.record.operational.target_statement_source_bytes_hash,
        )

    def test_identifiers_are_content_derived_and_move_with_the_lean(self) -> None:
        first = self.build()
        second = self.build(target_statement_path=MISMATCHED_TARGET)
        self.assertNotEqual(first.record.request.request_id, second.record.request.request_id)
        self.assertNotEqual(first.record.request.declaration_name, second.record.request.declaration_name)
        self.assertNotEqual(first.record.bridge_id, second.record.bridge_id)
        named = self.build(declaration_name="AdaIvyOperatorNamedDeclaration")
        self.assertEqual(named.record.request.declaration_name, "AdaIvyOperatorNamedDeclaration")


class RefusalTests(BridgeTestCase):
    def assertRefused(self, code: str, field: str, **overrides: object) -> None:
        with self.assertRaises(BridgeRefusal) as caught:
            self.build(**overrides)
        self.assertIn(code, caught.exception.codes, caught.exception.rejections)
        self.assertIn(field, [item.field for item in caught.exception.rejections])

    def test_absent_lean_input_is_refused_and_never_derived(self) -> None:
        self.assertRefused(
            "missing_lean_input", "target_statement",
            target_statement_path=self.root / "does-not-exist.lean",
        )
        self.assertRefused(
            "missing_lean_input", "proof_fragment",
            proof_fragment_path=self.root / "also-absent.lean",
        )

    def test_empty_and_undecodable_lean_inputs_are_refused(self) -> None:
        empty = self.root / "empty.lean"
        empty.write_text("   \n")
        self.assertRefused("empty_lean_input", "target_statement", target_statement_path=empty)
        binary = self.root / "binary.lean"
        binary.write_bytes(b"\xff\xfe not utf 8")
        self.assertRefused("invalid_utf8", "proof_fragment", proof_fragment_path=binary)

    def test_lean_that_violates_phase3b_policy_is_refused_with_its_own_codes(self) -> None:
        unsafe = self.root / "unsafe.lean"
        unsafe.write_text("by native_decide\n")
        self.assertRefused("forbidden_lean_feature", "proof_fragment", proof_fragment_path=unsafe)

    def test_unknown_run_proposal_and_bad_instant_are_named(self) -> None:
        self.assertRefused("unknown_run", "run_id", run_id="run.absent.v1")
        self.assertRefused("unknown_proposal", "proposal_id", proposal_id="proposal.absent")
        self.assertRefused("invalid_instant", "created_at", created_at="21 August 2026")

    def test_lean_source_kind_has_no_default_and_external_is_refused(self) -> None:
        self.assertRefused(
            "unsupported_lean_source_kind", "lean_source_kind", lean_source_kind=SourceKind.EXTERNAL,
        )
        with self.assertRaises(TypeError):
            BridgeInputs(  # type: ignore[call-arg]
                phase2_workspace=self.phase2, artifact_root=self.phase2 / "artifacts",
                run_id=RUN_ID, proposal_id=PROPOSER_ID, target_statement_path=TARGET,
                proof_fragment_path=PROOF, created_at=INSTANT,
            )

    def test_a_proposal_without_a_mathematical_payload_is_refused(self) -> None:
        self.assertRefused(
            "missing_mathematical_payload", "artifact.mathematical_payload", proposal_id=VERIFIER_ID,
        )

    def test_absent_workspace_or_artifact_store_is_refused_without_creating_either(self) -> None:
        missing = self.root / "nowhere"
        with self.assertRaises(BridgeRefusal) as caught:
            open_phase2_sources(missing, missing / "artifacts")
        self.assertEqual(
            sorted(caught.exception.codes), ["missing_artifact_store", "missing_phase2_workspace"],
        )
        self.assertFalse(missing.exists())


class ClaimIdentityProvenanceTests(BridgeTestCase):
    def test_claim_id_comes_from_the_dossier_and_not_from_the_lean(self) -> None:
        record = self.build().record
        expected = self.dossier.formalization.target_claim_id
        self.assertEqual(record.request.claim_id, expected)
        self.assertEqual(record.claim_identity.claim_id, expected)
        self.assertEqual(
            record.claim_identity.claim_id_source, "phase2_dossier.formalization.target_claim_id",
        )
        self.assertFalse(record.claim_identity.claim_id_derived_from_lean)
        # The Lean text cannot have supplied the claim ID: it does not contain it.
        self.assertNotIn(expected.value, TARGET.read_text())
        self.assertNotIn(expected.value, PROOF.read_text())

    def test_semantic_alignment_identity_and_status_are_read_not_asserted(self) -> None:
        record = self.build().record
        alignment = self.dossier.semantic_alignment
        self.assertEqual(record.semantic_alignment.semantic_alignment_id, alignment.id)
        self.assertEqual(record.semantic_alignment.status, alignment.status.value)
        self.assertEqual(record.semantic_alignment.semantic_alignment_source, "phase2_dossier.semantic_alignment")
        self.assertFalse(record.trust_grants.semantic_alignment_approved)

    def test_phase2_lineage_records_run_artifact_and_model_call(self) -> None:
        record = self.build().record
        with SQLiteWorkspace(self.phase2 / "workspace.sqlite3") as workspace:
            proposal = next(
                item for item in workspace.list_proposals(oid(RUN_ID))
                if item.proposal_id.value == PROPOSER_ID
            )
            run = workspace.get_run(oid(RUN_ID))
        self.assertEqual(record.phase2_proposal.artifact_hash, proposal.artifact_hash)
        self.assertEqual(record.phase2_proposal.run_id.value, RUN_ID)
        self.assertEqual(record.phase2_proposal.model_call_id, proposal.source_id)
        self.assertEqual(record.phase2_proposal.proposal_source_kind, "model")
        self.assertEqual(record.phase2_proposal.dossier_hash, run.dossier_hash)
        self.assertEqual(record.phase2_proposal.payload_hash, record.payload_correspondence.payload_hash)

    def test_a_proposal_naming_a_different_claim_is_refused(self) -> None:
        """The one cross-check a bridge can make is on identifiers."""
        with SQLiteWorkspace(self.phase2 / "workspace.sqlite3") as workspace:
            run = workspace.get_run(oid(RUN_ID))
            dossier = workspace.load_dossier(run.dossier_id)
            proposal = next(
                item for item in workspace.list_proposals(run.run_id)
                if item.proposal_id.value == PROPOSER_ID
            )
        artifacts = FileArtifactStore(self.phase2 / "artifacts")
        payload = artifacts.get(proposal.artifact_hash)
        source = FakePhase2Source(
            run=run, dossier=dossier,
            proposals=(replace(proposal, target_claim_id=oid("claim.some.other.v1")),),
        )
        with self.assertRaises(BridgeRefusal) as caught:
            build_bridged_request(
                workspace=source, artifacts=FakeArtifacts({proposal.artifact_hash: payload}),
                inputs=inputs(self.phase2),
            )
        self.assertIn("proposal_target_claim_mismatch", caught.exception.codes)

    def test_an_artifact_naming_a_different_claim_is_refused(self) -> None:
        with SQLiteWorkspace(self.phase2 / "workspace.sqlite3") as workspace:
            run = workspace.get_run(oid(RUN_ID))
            dossier = workspace.load_dossier(run.dossier_id)
            proposal = next(
                item for item in workspace.list_proposals(run.run_id)
                if item.proposal_id.value == PROPOSER_ID
            )
        value = json.loads(FileArtifactStore(self.phase2 / "artifacts").get(proposal.artifact_hash))
        value["target_claim_id"] = "claim.some.other.v1"
        source = FakePhase2Source(run=run, dossier=dossier, proposals=(proposal,))
        with self.assertRaises(BridgeRefusal) as caught:
            build_bridged_request(
                workspace=source,
                artifacts=FakeArtifacts({proposal.artifact_hash: canonical_bytes(value)}),
                inputs=inputs(self.phase2),
            )
        self.assertIn("artifact_target_claim_mismatch", caught.exception.codes)


class UnverifiedCorrespondenceTests(BridgeTestCase):
    def test_the_bridge_does_not_compare_prose_with_lean_and_records_that_it_did_not(self) -> None:
        """A mod-4 statement bridged onto an even-sum payload is CARRIED, not caught.

        This is the honest boundary of the slice. The bridge cannot detect the
        mismatch, so it must not appear to have looked: the record says the check
        was not performed and the correspondence is unattested.
        """
        record = self.build(target_statement_path=MISMATCHED_TARGET).record
        self.assertEqual(record.payload_correspondence.bridge_correspondence_check, "none_performed_by_bridge")
        self.assertEqual(
            record.payload_correspondence.correspondence_state_at_build, CORRESPONDENCE_UNATTESTED,
        )
        self.assertIn("did not compare", record.payload_correspondence.notice)
        self.assertNotIn("verified", record.payload_correspondence.correspondence_state_at_build)

    def test_the_unattested_state_is_visible_in_the_durable_record(self) -> None:
        result = self.build()
        store = self.store()
        store.save_bridged_request(result.record, request_bytes=result.request_bytes)
        stored = store.bridged_request(result.record.bridge_id.value)
        self.assertEqual(stored["record_type"], BRIDGE_RECORD_TYPE)
        self.assertEqual(stored["hash_profile"], BRIDGE_HASH_PROFILE)
        state = store.correspondence_state(result.record.bridge_id.value)
        self.assertEqual(state["correspondence_state"], CORRESPONDENCE_UNATTESTED)
        self.assertEqual(state["attesters"], [])
        self.assertEqual(state["bridge_correspondence_check"], BRIDGE_CORRESPONDENCE_CHECK)
        self.assertIs(state["correspondence_machine_verified_by_this_slice"], False)

    def test_resolver_reports_unattested_when_no_attestation_resolves(self) -> None:
        record = self.build().record
        value = public_value(record)
        self.assertEqual(
            resolve_correspondence(value, ())["correspondence_state"], CORRESPONDENCE_UNATTESTED,
        )
        stale = dict(public_value(build_correspondence_attestation(
            record, attester_id="operator.a", statement="read both", attested_at=INSTANT,
        )))
        stale["target_statement_hash"] = sha256_bytes(b"something else")
        resolved = resolve_correspondence(value, (stale,))
        self.assertEqual(resolved["correspondence_state"], CORRESPONDENCE_UNATTESTED)
        self.assertEqual(resolved["stale_attestation_ids"], [stale["attestation_id"]])

    def test_a_record_claiming_a_correspondence_check_is_refused(self) -> None:
        record = self.build().record
        value = public_value(record)
        validate_bridged_record_dict(value)
        for field, replacement, message in (
            ("bridge_correspondence_check", "compared_by_bridge", "cannot perform"),
            ("correspondence_state_at_build", CORRESPONDENCE_OPERATOR_ASSERTED, "other than unattested"),
        ):
            mutated = public_value(record)
            mutated["payload_correspondence"][field] = replacement
            mutated["content_hash"] = ""
            mutated["content_hash"] = bridge_content_hash(mutated)
            with self.assertRaisesRegex(ValueError, message):
                validate_bridged_record_dict(mutated)

    def test_a_record_claiming_its_claim_id_came_from_lean_is_refused(self) -> None:
        record = self.build().record
        mutated = public_value(record)
        mutated["claim_identity"]["claim_id_derived_from_lean"] = True
        mutated["content_hash"] = ""
        mutated["content_hash"] = bridge_content_hash(mutated)
        with self.assertRaisesRegex(ValueError, "claim ID came from Lean"):
            validate_bridged_record_dict(mutated)


class AttestationTests(BridgeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.result = self.build()
        self.record = self.result.record
        self.records = self.store()
        self.records.save_bridged_request(self.record, request_bytes=self.result.request_bytes)

    def test_operator_attestation_is_recorded_with_its_named_attester(self) -> None:
        attestation = build_correspondence_attestation(
            self.record, attester_id="operator.josh",
            statement="Read the payload and the Lean target together; both state the even sum.",
            attested_at=LATER,
        )
        self.records.save_correspondence_attestation(attestation)
        state = self.records.correspondence_state(self.record.bridge_id.value)
        self.assertEqual(state["correspondence_state"], CORRESPONDENCE_OPERATOR_ASSERTED)
        self.assertEqual(state["attesters"], ["operator.josh"])
        self.assertEqual(state["attestation_ids"], [attestation.attestation_id.value])
        self.assertIs(state["correspondence_machine_verified_by_this_slice"], False)
        stored = self.records.correspondence_attestations(self.record.bridge_id.value)[0]
        self.assertEqual(stored["attester_id"], "operator.josh")
        self.assertEqual(stored["attester_role"], "operator")
        self.assertEqual(stored["basis"], "human_reading")
        self.assertEqual(stored["bridge_correspondence_check"], BRIDGE_CORRESPONDENCE_CHECK)
        self.assertEqual(stored["attested_at"], LATER)

    def test_the_attestation_never_rewrites_the_bridge_record(self) -> None:
        before = self.records.bridged_request(self.record.bridge_id.value)
        self.records.save_correspondence_attestation(build_correspondence_attestation(
            self.record, attester_id="operator.josh", statement="read both", attested_at=LATER,
        ))
        after = self.records.bridged_request(self.record.bridge_id.value)
        self.assertEqual(before, after)
        self.assertEqual(
            after["payload_correspondence"]["correspondence_state_at_build"], CORRESPONDENCE_UNATTESTED,
        )

    def test_an_unnamed_attester_or_empty_statement_is_refused(self) -> None:
        for attester, statement, code in (
            ("", "read both", "missing_principal"),
            ("   ", "read both", "missing_principal"),
            ("operator josh", "read both", "invalid_principal"),
            ("operator.josh", "   ", "missing_attestation_statement"),
        ):
            with self.assertRaises(BridgeRefusal) as caught:
                build_correspondence_attestation(
                    self.record, attester_id=attester, statement=statement, attested_at=LATER,
                )
            self.assertIn(code, caught.exception.codes)

    def test_attestations_are_append_only_and_idempotent(self) -> None:
        first = build_correspondence_attestation(
            self.record, attester_id="operator.josh", statement="read both", attested_at=LATER,
        )
        self.records.save_correspondence_attestation(first)
        self.records.save_correspondence_attestation(first)
        second = build_correspondence_attestation(
            self.record, attester_id="operator.other", statement="read both", attested_at=LATER,
        )
        self.records.save_correspondence_attestation(second)
        self.assertEqual(len(self.records.correspondence_attestations(self.record.bridge_id.value)), 2)
        forged = replace(first, statement="asserted something else entirely")
        with self.assertRaisesRegex(ValueError, "content hash mismatch"):
            self.records.save_correspondence_attestation(forged)

    def test_an_attestation_for_an_unknown_bridge_is_refused(self) -> None:
        other = self.build(target_statement_path=MISMATCHED_TARGET)
        attestation = build_correspondence_attestation(
            other.record, attester_id="operator.josh", statement="read both", attested_at=LATER,
        )
        with self.assertRaises(KeyError):
            self.records.save_correspondence_attestation(attestation)


class DurablePersistenceTests(BridgeTestCase):
    def test_records_are_append_only_and_survive_restart(self) -> None:
        result = self.build()
        root = self.root / "restart"
        with BridgeStore(root) as store:
            store.save_bridged_request(result.record, request_bytes=result.request_bytes)
            store.save_bridged_request(result.record, request_bytes=result.request_bytes)
            self.assertEqual(store.migration_versions, ("phase3b-bridge:0001",))
            self.assertTrue((root / BRIDGE_DATABASE_NAME).is_file())
        with BridgeStore(root) as store:
            stored = store.canonical_bridged_requests()
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0], json.loads(canonical_bytes(result.record).decode()))
            rebuilt = parse_bridged_record(stored[0])
            self.assertEqual(rebuilt, result.record)
            events = [
                dict(row) for row in store.connection.execute(
                    "SELECT event_type, bridge_id FROM bridge_events ORDER BY sequence"
                )
            ]
            self.assertEqual(events, [
                {"event_type": "bridged_request_recorded", "bridge_id": result.record.bridge_id.value},
            ])

    def test_a_rewritten_record_under_the_same_id_is_refused(self) -> None:
        """A second build at a later instant is the same bridge, not a rewrite.

        The bridge ID is derived from the semantic preimage, so rebuilding with a
        different `created_at` produces the same ID with different canonical
        bytes. That is exactly the collision an append-only store must refuse.
        """
        first = self.build()
        later = self.build(created_at="2026-08-22T00:00:00Z")
        self.assertEqual(first.record.bridge_id, later.record.bridge_id)
        self.assertEqual(first.record.content_hash, later.record.content_hash)
        self.assertNotEqual(canonical_bytes(first.record), canonical_bytes(later.record))
        store = self.store()
        store.save_bridged_request(first.record, request_bytes=first.request_bytes)
        with self.assertRaisesRegex(ValueError, "cannot be rewritten"):
            store.save_bridged_request(later.record, request_bytes=later.request_bytes)
        self.assertEqual(len(store.canonical_bridged_requests()), 1)

    def test_a_record_that_no_longer_hashes_to_itself_is_refused(self) -> None:
        result = self.build()
        store = self.store()
        tampered = replace(result.record, operational_hash="sha256:" + "0" * 64)
        with self.assertRaisesRegex(ValueError, "operational hash mismatch"):
            store.save_bridged_request(tampered, request_bytes=result.request_bytes)

    def test_request_bytes_must_match_the_recorded_hashes(self) -> None:
        result = self.build()
        store = self.store()
        with self.assertRaisesRegex(ValueError, "recorded bytes hash"):
            store.save_bridged_request(result.record, request_bytes=result.request_bytes + b" ")

    def test_a_record_granting_trust_cannot_be_persisted(self) -> None:
        result = self.build()
        store = self.store()
        granted = replace(
            result.record,
            trust_grants=replace(result.record.trust_grants, epistemic_warrant_created=True),
        )
        granted = replace(granted, content_hash=bridge_content_hash(granted))
        with self.assertRaisesRegex(ValueError, "orthogonal trust decision"):
            store.save_bridged_request(granted, request_bytes=result.request_bytes)


class TraceabilityTests(BridgeTestCase):
    def test_a_finding_traces_back_to_the_exact_proposal_it_formalizes(self) -> None:
        result = self.build()
        request = parse_request_bytes(result.request_bytes)
        finding = DockerLeanAdapter().verify_output(
            request, generate_wrapper(request), synthetic_execution(), created_at=INSTANT,
        )
        store = self.store()
        findings = self.findings()
        store.save_bridged_request(result.record, request_bytes=result.request_bytes)
        findings.save_attempt(result.request_bytes, finding)
        trace = trace_finding(findings=findings, store=store, finding_id=finding.id.value)
        self.assertEqual(trace["bridge_provenance"], "resolved")
        self.assertEqual(trace["bridge_id"], result.record.bridge_id.value)
        self.assertEqual(trace["claim_id"], result.record.request.claim_id.value)
        self.assertIs(trace["epistemic_warrant_created"], False)
        provenance = trace["phase2_provenance"]
        assert isinstance(provenance, dict)
        self.assertEqual(provenance["run_id"], RUN_ID)
        self.assertEqual(provenance["proposal_id"], PROPOSER_ID)
        self.assertEqual(provenance["artifact_hash"], result.record.phase2_proposal.artifact_hash)
        self.assertEqual(provenance["model_call_id"], result.record.phase2_proposal.model_call_id)
        correspondence = trace["correspondence"]
        assert isinstance(correspondence, dict)
        self.assertEqual(correspondence["correspondence_state"], CORRESPONDENCE_UNATTESTED)
        self.assertIs(finding.epistemic_warrant_created, False)
        self.assertEqual(finding.outcome, FormalCheckOutcome.KERNEL_CHECKED)

    def test_a_finding_with_no_bridge_reports_absent_lineage(self) -> None:
        request = parse_request_bytes(Path("fixtures/phase3b/valid.json").read_bytes())
        source = Path("fixtures/phase3b/valid.json").read_bytes()
        finding = DockerLeanAdapter().verify_output(
            request, generate_wrapper(request), synthetic_execution(), created_at=INSTANT,
        )
        store = self.store()
        findings = self.findings()
        findings.save_attempt(source, finding)
        trace = trace_finding(findings=findings, store=store, finding_id=finding.id.value)
        self.assertEqual(trace["bridge_provenance"], "absent")
        self.assertIsNone(trace["bridge_id"])
        self.assertIsNone(trace["phase2_provenance"])


class OfflineAndDeterminismTests(BridgeTestCase):
    def test_the_bridge_module_reads_no_clock_and_no_random_source(self) -> None:
        source = Path("src/math_research/phase3b/bridge.py").read_text()
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            (node.module or "").split(".")[0]
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        self.assertFalse(imported & {"random", "secrets", "time", "subprocess", "socket", "urllib"})
        for attribute in ("now(", "utcnow(", "monotonic(", "time()"):
            self.assertNotIn(attribute, source)
        self.assertNotIn("datetime", imported)

    def test_building_a_request_requires_no_container_runtime(self) -> None:
        source = Path("src/math_research/phase3b/bridge.py").read_text()
        self.assertNotIn("docker", source.lower())
        self.assertNotIn("adapter", source)
        self.assertNotIn("RUNTIME_DIGEST", source)

    def test_the_bridge_never_writes_to_the_phase2_workspace(self) -> None:
        """The Phase 2 port has no mutating method, and the bytes prove it."""
        database = self.phase2 / "workspace.sqlite3"
        with SQLiteWorkspace(database) as workspace:
            proposals = len(workspace.list_proposals(oid(RUN_ID)))
            events = len(workspace.timeline(oid(RUN_ID)))
        before = sha256_bytes(database.read_bytes())
        self.build()
        self.assertEqual(sha256_bytes(database.read_bytes()), before)
        with SQLiteWorkspace(database) as workspace:
            self.assertEqual(len(workspace.list_proposals(oid(RUN_ID))), proposals)
            self.assertEqual(len(workspace.timeline(oid(RUN_ID))), events)


class CommandLineTests(BridgeTestCase):
    def run_cli(self, *argv: str) -> tuple[int, dict[str, object]]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = phase3b_main(list(argv))
        return code, json.loads(buffer.getvalue())

    def test_bridge_attest_and_status_commands_round_trip(self) -> None:
        workspace = self.root / "cli-workspace"
        request = self.root / "cli-request.json"
        record = self.root / "cli-record.json"
        code, summary = self.run_cli(
            "bridge-request", "--phase2-workspace", str(self.phase2),
            "--artifacts", str(self.phase2 / "artifacts"), "--run-id", RUN_ID,
            "--proposal-id", PROPOSER_ID, "--target-statement", str(TARGET),
            "--proof-fragment", str(PROOF), "--lean-source-kind", "model",
            "--lean-authored-by", "model.gpt", "--created-at", INSTANT,
            "--workspace", str(workspace), "--output", str(request), "--record", str(record),
        )
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "bridged")
        correspondence = summary["correspondence"]
        assert isinstance(correspondence, dict)
        self.assertEqual(correspondence["correspondence_state"], CORRESPONDENCE_UNATTESTED)
        self.assertEqual(summary["lean_source_kind"], "model")
        parsed = parse_request_bytes(request.read_bytes())
        self.assertIs(parsed.source_kind, SourceKind.MODEL)
        self.assertEqual(
            parse_bridged_record(json.loads(record.read_bytes())).bridge_id.value, summary["bridge_id"],
        )

        bridge_id = str(summary["bridge_id"])
        code, status = self.run_cli("bridge-status", str(workspace), bridge_id)
        self.assertEqual(code, 0)
        state = status["correspondence"]
        assert isinstance(state, dict)
        self.assertEqual(state["correspondence_state"], CORRESPONDENCE_UNATTESTED)

        code, attested = self.run_cli(
            "bridge-attest", bridge_id, "--workspace", str(workspace),
            "--attester", "operator.josh", "--attested-at", LATER,
            "--statement", "compared the payload prose with the Lean statement line by line",
        )
        self.assertEqual(code, 0)
        self.assertEqual(attested["attester_id"], "operator.josh")
        code, status = self.run_cli("bridge-status", str(workspace), bridge_id)
        state = status["correspondence"]
        assert isinstance(state, dict)
        self.assertEqual(state["correspondence_state"], CORRESPONDENCE_OPERATOR_ASSERTED)
        self.assertEqual(state["attesters"], ["operator.josh"])

    def test_the_cli_refuses_without_writing_a_request(self) -> None:
        output = self.root / "must-not-exist.json"
        code, refusal = self.run_cli(
            "bridge-request", "--phase2-workspace", str(self.phase2),
            "--artifacts", str(self.phase2 / "artifacts"), "--run-id", RUN_ID,
            "--proposal-id", PROPOSER_ID, "--target-statement", str(self.root / "absent.lean"),
            "--proof-fragment", str(PROOF), "--lean-source-kind", "operator",
            "--created-at", INSTANT, "--workspace", str(self.root / "refused-workspace"),
            "--output", str(output),
        )
        self.assertEqual(code, 2)
        self.assertEqual(refusal["status"], "refused")
        self.assertEqual(refusal["codes"], ["missing_lean_input"])
        self.assertFalse(output.exists())

    def test_an_unattested_correspondence_cannot_be_declared_on_the_command_line(self) -> None:
        parser_source = Path("src/math_research/phase3b_cli.py").read_text()
        for forbidden in (
            "--correspondence-verified", "--semantic-alignment-approved", "--grant-warrant",
            "--novelty", "--significance",
        ):
            self.assertNotIn(forbidden, parser_source)


class AdditiveSliceTests(unittest.TestCase):
    """The slice is additive: it must not touch or shadow another Phase 3B slice.

    These are merge-safety assertions. Every ADR-0043 symbol lives in
    `phase3b/bridge.py`, every command name is `bridge-` prefixed, and the
    durable schema is its own migration sequence in its own database file.
    """

    PACKAGE = Path("src/math_research/phase3b")
    PRE_EXISTING = (
        "__init__.py", "adapter.py", "demonstration.py", "interchange.py", "ports.py",
        "records.py", "serialization.py", "service.py", "validation.py", "workspace.py",
        "wrapper.py",
    )

    def test_no_pre_existing_phase3b_module_mentions_the_bridge(self) -> None:
        for name in self.PRE_EXISTING:
            source = (self.PACKAGE / name).read_text()
            self.assertNotIn("bridge", source.lower(), name)

    def test_the_bridge_does_not_import_the_findings_workspace(self) -> None:
        """The findings side arrives through a Protocol, so no cycle is possible."""
        tree = ast.parse((self.PACKAGE / "bridge.py").read_text())
        modules = {
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("workspace", modules)
        self.assertNotIn(".workspace", modules)
        self.assertNotIn("FormalCheckWorkspace(", (self.PACKAGE / "bridge.py").read_text())

    def test_the_durable_schema_is_a_separate_sequence_and_file(self) -> None:
        self.assertEqual(
            sorted(item.name for item in Path("migrations/phase3b-bridge").glob("*.sql")),
            ["0001_request_bridge.sql"],
        )
        self.assertEqual(
            sorted(item.name for item in Path("migrations/phase3b").glob("*.sql")),
            ["0001_formal_checking.sql"],
        )
        self.assertEqual(BRIDGE_DATABASE_NAME, "bridge.sqlite3")

    def test_every_registered_subcommand_name_is_pinned(self) -> None:
        tree = ast.parse(Path("src/math_research/phase3b_cli.py").read_text())
        registered = sorted(
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser" and node.args
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
        )
        self.assertEqual(registered, [
            "bridge-attest", "bridge-request", "bridge-status", "bridge-trace",
            "check", "demo", "finding", "inspect",
        ])


if __name__ == "__main__":
    unittest.main()
