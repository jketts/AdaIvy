"""Acceptance scenario ERS-AC-10: deterministic policy-admitted export/replay.

Section 14 of `docs/phase-4/EXPLORATORY_RESEARCH_SYNTHESIS_V1.md` is normative.
The fresh-process replay is a real subprocess, not a reopen in this process, so
the byte-identity claim covers interpreter startup and dict ordering too.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from math_research.synthesis.admission import AdmissionPolicy, evaluate_admission
from math_research.synthesis import EXPORT_VERSION
from math_research.synthesis.proposals import (
    GenerationOutcome,
    GeneratorCalledDuringReplay,
    ProposalStore,
    capture,
)
from math_research.synthesis.serialization import (
    canonical_bytes,
    operational_export_hash,
    semantic_export_hash,
    semantic_record_hash,
)
from math_research.synthesis.state import SynthesisValidationError
from math_research.synthesis.records import StateAxes
from math_research.synthesis.state import (
    ExtractionFidelity,
    GraphAdmission,
    MathematicalWarrant,
    SourceApplicability,
)
from math_research.synthesis.workspace import EXPORT_FIELDS, SynthesisWorkspace, decode_json

ROOT = Path(__file__).resolve().parents[1]
T0 = "2026-08-20T12:00:00Z"
T1 = "2026-08-20T14:30:00Z"
CLOSURE = "sha256:" + "a" * 64
SNAPSHOT = "sha256:" + "e" * 64

# One nondeterministically generated proposal, already captured. Its digest is an
# explicit input to admission and export from here on.
PROPOSAL = capture(
    generator_id="generator.scripted",
    generator_version="1.0.0",
    generator_configuration={"temperature": "0", "top_p": "1"},
    prompt_input_identities=["prompt.compose-v1"],
    source_graph_snapshot_identity=SNAPSHOT,
    ordered_event_identity="event-0001",
    raw_payload='{"proposed_relation": "depends_on", "rationale": "shared premise"}',
    outcome=GenerationOutcome.PRODUCED,
    resource_units_consumed=3,
)
POLICY = AdmissionPolicy.create(
    view_id="view.replay",
    permitted_warrants={MathematicalWarrant.PROOF_REVIEWED},
    minimum_documented_warrant=MathematicalWarrant.PROOF_REVIEWED,
)


def axes(
    *,
    applicability: SourceApplicability = SourceApplicability.CHECKED,
    fidelity: ExtractionFidelity = ExtractionFidelity.SOURCE_CHECKED,
    warrant: MathematicalWarrant = MathematicalWarrant.PROOF_REVIEWED,
) -> StateAxes:
    return StateAxes(
        source_applicability=applicability,
        extraction_fidelity=fidelity,
        mathematical_warrant=warrant,
        graph_admission=GraphAdmission.PROPOSED,
    )


def admission_payload(
    subject_id: str,
    state: StateAxes,
    *,
    policy: AdmissionPolicy = POLICY,
    closure: str = CLOSURE,
    input_record_ids: tuple[str, ...] = (PROPOSAL.proposal_id,),
) -> dict:
    return evaluate_admission(
        policy,
        subject_id=subject_id,
        subject_kind="result_relation",
        axes=state,
        input_record_ids=input_record_ids,
        influence_closure_id=closure,
        admitting_actor_id="actor.replay",
        admitting_authority="human_final",
    ).value()

# A build script the fresh-process replay runs. Written as a literal so the
# subprocess shares no in-memory state with this process.
REPLAY_SCRIPT = '''
import json, sys
from pathlib import Path
sys.path.insert(0, {src!r})
from math_research.synthesis.workspace import SynthesisWorkspace
from math_research.synthesis.proposals import ProposalStore, CapturedProposal, GenerationOutcome

spec = json.loads(Path(sys.argv[2]).read_text())
store = ProposalStore(replay=True)
store.admit(CapturedProposal(
    proposal_id=spec["proposal"]["proposal_id"],
    generator_id=spec["proposal"]["generator_id"],
    generator_version=spec["proposal"]["generator_version"],
    generator_configuration_digest=spec["proposal"]["generator_configuration_digest"],
    prompt_input_identities=tuple(spec["proposal"]["prompt_input_identities"]),
    source_graph_snapshot_identity=spec["proposal"]["source_graph_snapshot_identity"],
    seed=spec["proposal"]["seed"],
    ordered_event_identity=spec["proposal"]["ordered_event_identity"],
    parent_branch_id=spec["proposal"]["parent_branch_id"],
    raw_payload=spec["proposal"]["raw_payload"],
    proposal_digest=spec["proposal"]["proposal_digest"],
    resource_units_consumed=spec["proposal"]["resource_units_consumed"],
    outcome=GenerationOutcome(spec["proposal"]["outcome"]),
    failure_detail=spec["proposal"]["failure_detail"],
))
with SynthesisWorkspace(Path(sys.argv[1])) as workspace:
    for record in spec["appends"]:
        workspace.append(**record)
    workspace.rebuild_admission_projection()
    sys.stdout.buffer.write(workspace.export_bytes())
'''


def build_spec() -> dict:
    """The complete, fixed replay input set."""
    return {
        "proposal": PROPOSAL.value(),
        "appends": [
            {
                "record_type": "captured_proposal",
                "subject_id": PROPOSAL.proposal_id,
                "record_id": PROPOSAL.proposal_id,
                "recorded_at": T0,
                "payload": PROPOSAL.value(),
            },
            {
                "record_type": "graph_admission",
                "subject_id": "relation.ab",
                "recorded_at": T0,
                "payload": admission_payload("relation.ab", axes()),
            },
            {
                "record_type": "graph_admission",
                "subject_id": "relation.cd",
                "recorded_at": T0,
                "payload": admission_payload(
                    "relation.cd",
                    axes(
                        applicability=SourceApplicability.UNRESOLVED,
                        fidelity=ExtractionFidelity.PROPOSED_EXTRACTION,
                        warrant=MathematicalWarrant.UNASSESSED,
                    ),
                ),
            },
        ],
    }


def run_fresh_process(workspace_root: Path, spec_path: Path) -> bytes:
    script = REPLAY_SCRIPT.format(src=str(ROOT / "src"))
    completed = subprocess.run(
        [sys.executable, "-c", script, str(workspace_root), str(spec_path)],
        capture_output=True,
        check=False,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
    )
    if completed.returncode != 0:
        raise AssertionError(f"fresh-process replay failed: {completed.stderr.decode()}")
    return completed.stdout


class DeterministicExportReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.spec_path = self.root / "spec.json"
        self.spec = build_spec()
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self, root: Path) -> bytes:
        with SynthesisWorkspace(root) as workspace:
            for record in self.spec["appends"]:
                workspace.append(**record)
            workspace.rebuild_admission_projection()
            data = workspace.export_bytes()
            workspace.save_verified_export(data)
            return data

    def test_export_is_byte_identical_across_two_in_process_runs(self) -> None:
        first = self.build(self.root / "a")
        second = self.build(self.root / "b")
        self.assertEqual(first, second)

    def test_repeated_append_is_idempotent(self) -> None:
        root = self.root / "idempotent"
        first = self.build(root)
        second = self.build(root)
        self.assertEqual(first, second)
        with SynthesisWorkspace(root) as workspace:
            self.assertEqual(len(workspace.records()), len(self.spec["appends"]))

    def test_fresh_process_replay_is_byte_identical(self) -> None:
        in_process = self.build(self.root / "a")
        fresh = run_fresh_process(self.root / "c", self.spec_path)
        self.assertEqual(in_process, fresh)
        self.assertEqual(
            json.loads(in_process)["content_hash"], json.loads(fresh)["content_hash"]
        )

    def test_restart_export_is_byte_identical(self) -> None:
        root = self.root / "restart"
        first = self.build(root)
        with SynthesisWorkspace(root) as reopened:
            self.assertEqual(reopened.export_bytes(), first)

    def test_export_is_in_canonical_form(self) -> None:
        data = self.build(self.root / "a")
        self.assertEqual(
            data,
            json.dumps(json.loads(data), sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        value = json.loads(data)
        self.assertEqual(set(value), set(EXPORT_FIELDS))
        self.assertEqual(value["schema_version"], EXPORT_VERSION)
        self.assertEqual(semantic_export_hash(value), value["content_hash"])
        self.assertEqual(operational_export_hash(value), value["operational_hash"])

    def test_replay_never_calls_a_generator(self) -> None:
        """Forbidden: proposal regeneration."""
        store = ProposalStore(replay=True)
        store.admit(PROPOSAL)
        calls: list[int] = []

        def generator() -> str:
            calls.append(1)
            return "regenerated"

        with self.assertRaises(GeneratorCalledDuringReplay):
            store.generate(
                generator,
                generator_id="generator.scripted",
                generator_version="1.0.0",
                generator_configuration={},
                prompt_input_identities=[],
                source_graph_snapshot_identity=SNAPSHOT,
                ordered_event_identity="event-0002",
            )
        self.assertEqual(calls, [])
        # The captured proposal is still the one being consumed.
        self.assertEqual(store.get(PROPOSAL.proposal_id).proposal_digest, PROPOSAL.proposal_digest)

    def test_operational_timestamp_is_absent_from_semantic_identity(self) -> None:
        """Forbidden: operational timestamp in semantic identity."""
        first = self.build(self.root / "t0")
        later = dict(self.spec)
        later["appends"] = [{**record, "recorded_at": T1} for record in self.spec["appends"]]
        root = self.root / "t1"
        with SynthesisWorkspace(root) as workspace:
            for record in later["appends"]:
                workspace.append(**record)
            workspace.rebuild_admission_projection()
            shifted = workspace.export_bytes()
        self.assertEqual(json.loads(first)["content_hash"], json.loads(shifted)["content_hash"])
        self.assertNotEqual(
            json.loads(first)["operational_hash"], json.loads(shifted)["operational_hash"]
        )
        # The timestamp is still exported, just outside semantic identity.
        self.assertEqual(json.loads(shifted)["records"][0]["recorded_at"], T1)

    def test_unadmitted_proposal_content_is_absent_from_the_admitted_projection(self) -> None:
        """Forbidden: unadmitted proposal content in the admitted projection."""
        self.build(self.root / "a")
        with SynthesisWorkspace(self.root / "a") as workspace:
            projection = workspace.admission_projection()
            admitted = [
                row for row in projection if row["current_admission"] == "admitted_under_policy"
            ]
            self.assertEqual([row["subject_id"] for row in admitted], ["relation.ab"])
            # The excluded subject is recorded as excluded, and no projection row
            # carries the raw generated payload.
            serialized = json.dumps([dict(row) for row in projection])
            self.assertNotIn("proposed_relation", serialized)
            self.assertNotIn(PROPOSAL.raw_payload, serialized)

    def test_changed_replay_input_produces_a_new_identity(self) -> None:
        """Fails if any explicit replay input differs without a new identity."""
        baseline = json.loads(self.build(self.root / "a"))["content_hash"]
        alternate = capture(
            generator_id="generator.scripted",
            generator_version="1.0.0",
            generator_configuration={"temperature": "0", "top_p": "1"},
            prompt_input_identities=["prompt.compose-v1"],
            source_graph_snapshot_identity=SNAPSHOT,
            ordered_event_identity="event-0002",
            raw_payload='{"proposed_relation": "implies"}',
        )
        policy_v2 = AdmissionPolicy.create(
            view_id="view.replay",
            policy_version="synthesis-admission-v2",
            permitted_warrants={MathematicalWarrant.PROOF_REVIEWED},
            minimum_documented_warrant=MathematicalWarrant.PROOF_REVIEWED,
        )
        variants = {
            "policy_version": admission_payload("relation.ab", axes(), policy=policy_v2),
            "influence_closure_id": admission_payload(
                "relation.ab", axes(), closure="sha256:" + "b" * 64
            ),
            "axes": admission_payload(
                "relation.ab",
                axes(warrant=MathematicalWarrant.EMPIRICALLY_TESTED),
            ),
            "captured_proposal": admission_payload(
                "relation.ab", axes(), input_record_ids=(alternate.proposal_id,)
            ),
        }
        for index, (label, payload) in enumerate(sorted(variants.items())):
            with self.subTest(changed=label):
                appends = [dict(record) for record in self.spec["appends"]]
                if label == "captured_proposal":
                    appends.insert(1, {
                        "record_type": "captured_proposal",
                        "record_id": alternate.proposal_id,
                        "subject_id": alternate.proposal_id,
                        "recorded_at": T0,
                        "payload": alternate.value(),
                    })
                admission_index = 2 if label == "captured_proposal" else 1
                appends[admission_index] = {**appends[admission_index], "payload": payload}
                root = self.root / f"variant-{index}"
                with SynthesisWorkspace(root) as workspace:
                    for record in appends:
                        workspace.append(**record)
                    workspace.rebuild_admission_projection()
                    changed = json.loads(workspace.export_bytes())["content_hash"]
                self.assertNotEqual(changed, baseline)

    def test_unknown_canonicalization_version_fails_closed(self) -> None:
        captured = PROPOSAL.value()
        captured["canonicalization_version"] = "other-canonical-v9"
        with SynthesisWorkspace(self.root / "bad-canonicalization") as workspace:
            with self.assertRaises(SynthesisValidationError):
                workspace.append(
                    record_type="captured_proposal",
                    record_id=PROPOSAL.proposal_id,
                    subject_id=PROPOSAL.proposal_id,
                    payload=captured,
                    recorded_at=T0,
                )

    def test_captured_proposal_identity_covers_every_replay_input(self) -> None:
        captured = PROPOSAL.value()
        captured["prompt_input_identities"] = ["prompt.different"]
        with SynthesisWorkspace(self.root / "forged-proposal") as workspace:
            with self.assertRaises(SynthesisValidationError):
                workspace.append(
                    record_type="captured_proposal",
                    record_id=PROPOSAL.proposal_id,
                    subject_id=PROPOSAL.proposal_id,
                    payload=captured,
                    recorded_at=T0,
                )

    def test_record_identity_cannot_be_rewritten(self) -> None:
        root = self.root / "rewrite"
        self.build(root)
        with SynthesisWorkspace(root) as workspace:
            record = self.spec["appends"][1]
            with self.assertRaises(SynthesisValidationError):
                workspace.append(**{**record, "recorded_at": T1})

    def test_export_decode_fails_closed_on_malformed_input(self) -> None:
        data = self.build(self.root / "a")
        root = self.root / "verify"
        with SynthesisWorkspace(root) as workspace:
            with self.assertRaises(SynthesisValidationError):
                workspace.save_verified_export(b'{"a": 1, "a": 2}')
            with self.assertRaises(SynthesisValidationError):
                workspace.save_verified_export(b'{"schema_version": "x"}')
            with self.assertRaises(SynthesisValidationError):
                workspace.save_verified_export(b"[]")
            tampered = json.loads(data)
            tampered["records"] = []
            with self.assertRaises(SynthesisValidationError):
                workspace.save_verified_export(
                    json.dumps(tampered, sort_keys=True, separators=(",", ":")).encode("utf-8")
                )

    def test_graph_admission_cannot_bypass_policy_validation(self) -> None:
        """An arbitrary dictionary cannot promote an unreviewed result."""
        with SynthesisWorkspace(self.root / "unreviewed") as workspace:
            with self.assertRaises(SynthesisValidationError):
                workspace.append(
                    record_type="graph_admission",
                    subject_id="result.unreviewed",
                    recorded_at=T0,
                    payload={
                        "subject_id": "result.unreviewed",
                        "subject_kind": "structured_result",
                        "decision": "admitted_under_policy",
                        "influence_closure_id": "not-a-hash",
                    },
                )
            self.assertEqual(workspace.records(), ())

    def test_unknown_record_types_and_identity_aliases_fail_closed(self) -> None:
        with SynthesisWorkspace(self.root / "unknown-record") as workspace:
            with self.assertRaises(SynthesisValidationError):
                workspace.append(
                    record_type="generic_approval",
                    subject_id="result.unreviewed",
                    recorded_at=T0,
                    payload={"status": "approved"},
                )
            with self.assertRaises(SynthesisValidationError):
                workspace.append(
                    record_type="captured_proposal",
                    record_id="captured-proposal.alias",
                    subject_id=PROPOSAL.proposal_id,
                    recorded_at=T0,
                    payload=PROPOSAL.value(),
                )
            self.assertEqual(workspace.records(), ())

    def test_self_hashed_forged_projection_is_not_a_verified_export(self) -> None:
        """Top-level hashes cannot authenticate an admission absent its records."""
        forged = {
            "schema_version": EXPORT_VERSION,
            "records": [],
            "admission_projection": [
                {
                    "subject_id": "result.invented",
                    "subject_kind": "structured_result",
                    "current_admission": "admitted_under_policy",
                    "admission_record_id": "admission.invented",
                    "influence_closure_id": CLOSURE,
                    "latest_invalidation_id": None,
                }
            ],
        }
        forged["content_hash"] = semantic_export_hash(forged)
        forged["operational_hash"] = operational_export_hash(forged)
        with SynthesisWorkspace(self.root / "forged") as workspace:
            with self.assertRaises(SynthesisValidationError):
                workspace.save_verified_export(canonical_bytes(forged))

    def test_cli_inspect_rejects_invalid_hashes(self) -> None:
        path = self.root / "bad-export.json"
        path.write_bytes(
            canonical_bytes(
                {
                    "schema_version": EXPORT_VERSION,
                    "records": [],
                    "admission_projection": [],
                    "content_hash": "sha256:bad",
                    "operational_hash": "sha256:bad",
                }
            )
        )
        completed = subprocess.run(
            [sys.executable, "-m", "math_research.cli", "synthesis", "inspect", str(path)],
            cwd=ROOT,
            capture_output=True,
            check=False,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "src")},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn(b"semantic hash mismatch", completed.stderr)

    def test_decode_rejects_non_finite_numbers_and_bad_utf8(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            decode_json(b'{"value": NaN}')
        with self.assertRaises(SynthesisValidationError):
            decode_json(b'{"value": Infinity}')
        with self.assertRaises(SynthesisValidationError):
            decode_json(b'{"value": "\xff\xfe"}')
        with self.assertRaises(SynthesisValidationError):
            decode_json(b'{"a": 1}', max_bytes=4)

    def test_integrity_check_detects_projection_drift(self) -> None:
        root = self.root / "drift"
        self.build(root)
        with SynthesisWorkspace(root) as workspace:
            workspace.connection.execute("DELETE FROM synthesis_admission_projection")
            with self.assertRaises(SynthesisValidationError):
                workspace.verify_integrity()

    def test_migration_checksum_drift_is_detected(self) -> None:
        root = self.root / "checksum"
        self.build(root)
        with SynthesisWorkspace(root) as workspace:
            workspace.connection.execute(
                "UPDATE synthesis_schema_migrations SET checksum='0'*64 WHERE version='0001'"
            )
        with self.assertRaises(SynthesisValidationError):
            SynthesisWorkspace(root)


if __name__ == "__main__":
    unittest.main()
