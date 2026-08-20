"""Acceptance scenario ERS-AC-07: counterexample as an ADR-0019 material result.

Drives the real, sealed Phase 5 surfacing path over the frozen QD-FS-01 fixture
rather than reimplementing ADR-0019. The lifecycle record this slice adds is
validated against the same contract checker the ADR-0019 suite uses, so the new
writer cannot drift from the frozen schema.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from math_research.phase5.service import Phase5Service
from math_research.phase5.workspace import Phase5ValidationError, Phase5Workspace
from math_research.synthesis.material import (
    LIFECYCLE_EVENT_TYPE,
    LIFECYCLE_RECORD_TYPE,
    LifecycleChangeKind,
    SelfAuthorizationRejected,
    append_result_lifecycle,
    derived_state,
    require_separation_of_duty,
    surface_counterexample,
)
from math_research.synthesis.state import SynthesisValidationError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (ROOT / "fixtures/phase5/quantum-diagonal-v1.json").read_text(encoding="utf-8")
)
T0 = "2026-08-20T12:00:00Z"
T1 = "2026-08-20T13:00:00Z"
T2 = "2026-08-20T14:00:00Z"


class MaterialResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = Phase5Workspace(self.root)
        self.service = Phase5Service(self.workspace)
        # The frozen fixture's boundary case surfaces a material result through
        # the sealed Phase 5 path.
        self.run = self.service.run_quantum_fixture(FIXTURE, recorded_at=T0)
        self.events = self.workspace.records("material_partial_result_event")

    def tearDown(self) -> None:
        self.workspace.close()
        self.temporary.cleanup()

    def event(self) -> dict:
        self.assertTrue(self.events, "the frozen fixture must surface a material result")
        return self.events[0]

    # --- the surfaced event ----------------------------------------------
    def test_surfaced_event_is_classified_refutes_or_restricts_not_generic_progress(self) -> None:
        """Forbidden: generic progress classification."""
        event = self.event()["payload"]["event"]
        self.assertIn(event["classification"], {"refutes", "restricts"})
        self.assertNotIn(event["classification"], {"progress", "update", "info"})

    def test_surfaced_event_has_an_incomplete_parent_objective(self) -> None:
        """Forbidden: completed parent objective."""
        event = self.event()["payload"]["event"]
        self.assertTrue(event["main_objective_incomplete"])
        # The event references subject ids, so resolve through `find` rather
        # than `record`, which is keyed by the content-derived record id.
        objective = self.workspace.find("objective", event["objective_id"])[0]
        self.assertEqual(objective["payload"]["status"], "active")

    def test_event_records_independent_verification_and_materiality(self) -> None:
        event = self.event()["payload"]["event"]
        self.assertEqual(event["verification"]["status"], "verified")
        self.assertTrue(event["verification"]["verification_record_ids"])
        for verification_id in event["verification"]["verification_record_ids"]:
            record = self.workspace.find("verification", verification_id)[0]
            self.assertTrue(record["payload"]["independent_from_proposal"])
        materiality = self.workspace.find(
            "materiality_assessment", event["materiality_assessment_id"]
        )[0]
        self.assertEqual(materiality["payload"]["classification"], event["classification"])

    def test_event_is_idempotent_under_retry(self) -> None:
        """Forbidden: duplicate retry event."""
        before = len(self.workspace.records("material_partial_result_event"))
        repeated = self.service.run_quantum_fixture(FIXTURE, recorded_at=T0)
        self.assertEqual(repeated, self.run)
        self.assertEqual(len(self.workspace.records("material_partial_result_event")), before)

    def test_replay_after_restart_is_byte_identical(self) -> None:
        exported = self.workspace.export_bytes()
        self.workspace.close()
        with Phase5Workspace(self.root) as restarted:
            self.assertEqual(restarted.export_bytes(), exported)
        self.workspace = Phase5Workspace(self.root)

    # --- separation of duty ---------------------------------------------
    def test_self_authorization_is_rejected(self) -> None:
        """Forbidden: self-authorization.

        Sealed Phase 5 accepts an identical originating and creating principal,
        so this slice supplies the separation-of-duty precondition.
        """
        with self.assertRaises(SelfAuthorizationRejected):
            require_separation_of_duty(
                originating_principal_id="principal.phase5.owner",
                created_by_principal_id="principal.phase5.owner",
            )
        event = self.event()["payload"]["event"]
        with self.assertRaises(SelfAuthorizationRejected):
            surface_counterexample(
                self.service,
                objective_id=event["objective_id"],
                run_id=event["run_id"],
                branch_id=event["branch_id"],
                finding_id=event["causal_parent_ids"][0],
                evidence_id=event["evidence_references"][0]["reference_id"],
                statement="a restated counterexample",
                originating_principal_id="principal.phase5.owner",
                created_by_principal_id="principal.phase5.owner",
                capability_id="capability.phase5.surface",
                recorded_at=T1,
            )

    def test_counterexample_must_be_classified_refutes(self) -> None:
        event = self.event()["payload"]["event"]
        with self.assertRaises(SynthesisValidationError):
            surface_counterexample(
                self.service,
                objective_id=event["objective_id"],
                run_id=event["run_id"],
                branch_id=event["branch_id"],
                finding_id=event["causal_parent_ids"][0],
                evidence_id=event["evidence_references"][0]["reference_id"],
                statement="a counterexample",
                originating_principal_id="principal.phase5.deterministic",
                created_by_principal_id="principal.phase5.owner",
                capability_id="capability.phase5.surface",
                recorded_at=T1,
                classification="strengthens",
            )

    # --- the lifecycle writer this slice adds ----------------------------
    def lifecycle(self, kind=LifecycleChangeKind.APPLICABILITY_REVIEW_CHANGED, **kwargs):
        event_id = self.event()["record_id"]
        event = self.event()["payload"]["event"]
        return append_result_lifecycle(
            self.service,
            event_id=event_id,
            change_kind=kind,
            principal_id="principal.phase5.owner",
            capability_id="capability.phase5.lifecycle",
            reason="a superseding applicability review withdrew the permitted use",
            affected_evidence_ids=[event["evidence_references"][0]["reference_id"]],
            recorded_at=T1,
            **kwargs,
        )

    def ensure_lifecycle_capability(self) -> None:
        self.service.ensure_capability(
            capability_id="capability.phase5.lifecycle",
            principal_id="principal.phase5.owner",
            operation="review_result_lifecycle",
            recorded_at=T0,
        )

    def test_lifecycle_record_changes_the_derived_view_without_mutating_the_event(self) -> None:
        """Forbidden: mutable event state."""
        self.ensure_lifecycle_capability()
        original = self.event()
        self.assertEqual(self.workspace.material_results()[0]["current_validity"], "valid")
        self.lifecycle()
        # The immutable original is byte-identical.
        self.assertEqual(self.workspace.record(original["record_id"]), original)
        # The derived current-validity view changed.
        self.assertEqual(self.workspace.material_results()[0]["current_validity"], "invalidated")

    def test_lifecycle_record_matches_the_frozen_adr_0019_contract(self) -> None:
        """The new writer must not drift from the frozen lifecycle schema."""
        self.ensure_lifecycle_capability()
        record = self.lifecycle()
        envelope = record["payload"]
        self.assertEqual(envelope["record_type"], LIFECYCLE_RECORD_TYPE)
        self.assertEqual(
            envelope["schema_version"], "adaivy.material-partial-result-lifecycle.v1"
        )
        lifecycle = envelope["lifecycle"]
        self.assertEqual(
            set(lifecycle),
            {
                "lifecycle_id",
                "event_type",
                "idempotency_key",
                "material_result_event_id",
                "objective_id",
                "run_id",
                "change_kind",
                "derived_state",
                "principal_id",
                "capability_id",
                "required_capability",
                "effective_actor_kind",
                "authority",
                "affected_evidence_ids",
                "source_record_ids",
                "applicability_review_ids",
                "reason",
                "created_at",
                "causal_predecessor_id",
                "superseding_event_id",
                "policy_id",
                "policy_version",
                "sequence",
            },
        )
        self.assertEqual(lifecycle["event_type"], LIFECYCLE_EVENT_TYPE)
        self.assertEqual(lifecycle["required_capability"], "review_result_lifecycle")
        self.assertEqual(lifecycle["causal_predecessor_id"], self.event()["record_id"])
        self.assertEqual(lifecycle["sequence"], 1)

    def test_change_kind_and_derived_state_always_agree(self) -> None:
        for kind in LifecycleChangeKind:
            with self.subTest(kind=kind.value):
                expected = {
                    "correction": "corrected",
                    "supersession": "superseded",
                }.get(kind.value, "invalidated")
                self.assertEqual(derived_state(kind), expected)

    def test_supersession_requires_a_superseding_event_and_others_forbid_it(self) -> None:
        self.ensure_lifecycle_capability()
        with self.assertRaises(SynthesisValidationError):
            self.lifecycle(kind=LifecycleChangeKind.SUPERSESSION)
        with self.assertRaises(SynthesisValidationError):
            self.lifecycle(
                kind=LifecycleChangeKind.TAKEDOWN,
                superseding_event_id="material-result.other",
            )

    def test_lifecycle_records_chain_and_prior_records_stay_identical(self) -> None:
        self.ensure_lifecycle_capability()
        first = self.lifecycle(kind=LifecycleChangeKind.CORRECTION)
        snapshot = json.dumps(first, sort_keys=True)
        second = self.lifecycle(kind=LifecycleChangeKind.TAKEDOWN)
        self.assertEqual(json.dumps(self.workspace.record(first["record_id"]), sort_keys=True), snapshot)
        self.assertEqual(second["payload"]["lifecycle"]["sequence"], 2)
        self.assertEqual(
            second["payload"]["lifecycle"]["causal_predecessor_id"],
            first["payload"]["lifecycle"]["lifecycle_id"],
        )
        # The latest record determines the derived state.
        self.assertEqual(self.workspace.material_results()[0]["current_validity"], "invalidated")

    def test_nonhuman_lifecycle_review_fails_closed(self) -> None:
        self.service.ensure_capability(
            capability_id="capability.phase5.lifecycle-system",
            principal_id="principal.phase5.deterministic",
            operation="review_result_lifecycle",
            recorded_at=T0,
        )
        event = self.event()
        with self.assertRaises(PermissionError):
            append_result_lifecycle(
                self.service,
                event_id=event["record_id"],
                change_kind=LifecycleChangeKind.TAKEDOWN,
                principal_id="principal.phase5.deterministic",
                capability_id="capability.phase5.lifecycle-system",
                reason="automated invalidation attempt",
                affected_evidence_ids=[
                    event["payload"]["event"]["evidence_references"][0]["reference_id"]
                ],
                recorded_at=T1,
            )

    def test_wrong_capability_operation_fails_closed(self) -> None:
        event = self.event()
        with self.assertRaises(PermissionError):
            append_result_lifecycle(
                self.service,
                event_id=event["record_id"],
                change_kind=LifecycleChangeKind.TAKEDOWN,
                principal_id="principal.phase5.owner",
                capability_id="capability.phase5.steer",
                reason="wrong capability",
                affected_evidence_ids=[
                    event["payload"]["event"]["evidence_references"][0]["reference_id"]
                ],
                recorded_at=T1,
            )

    def test_lifecycle_requires_affected_evidence(self) -> None:
        self.ensure_lifecycle_capability()
        event = self.event()
        with self.assertRaises(SynthesisValidationError):
            append_result_lifecycle(
                self.service,
                event_id=event["record_id"],
                change_kind=LifecycleChangeKind.TAKEDOWN,
                principal_id="principal.phase5.owner",
                capability_id="capability.phase5.lifecycle",
                reason="no evidence named",
                affected_evidence_ids=[],
                recorded_at=T1,
            )

    def test_lifecycle_target_must_be_a_surfaced_event(self) -> None:
        self.ensure_lifecycle_capability()
        # An existing record of the wrong type, addressed by its record id.
        other_record_id = self.workspace.records("objective")[0]["record_id"]
        with self.assertRaises(SynthesisValidationError):
            append_result_lifecycle(
                self.service,
                event_id=other_record_id,
                change_kind=LifecycleChangeKind.TAKEDOWN,
                principal_id="principal.phase5.owner",
                capability_id="capability.phase5.lifecycle",
                reason="wrong target",
                affected_evidence_ids=["evidence.x"],
                recorded_at=T1,
            )

    def test_steering_after_lifecycle_is_appended_separately(self) -> None:
        """Expected: later steering appended separately, never overwriting."""
        event = self.event()
        before = self.workspace.records("material_partial_result_steering_action")
        self.service.steer(
            event_id=event["record_id"],
            action="acknowledge",
            principal_id="principal.phase5.owner",
            capability_id="capability.phase5.steer",
            idempotency_key="synthesis-steer-1",
            recorded_at=T2,
        )
        after = self.workspace.records("material_partial_result_steering_action")
        self.assertEqual(len(after), len(before) + 1)
        # The event itself is untouched.
        self.assertEqual(self.workspace.record(event["record_id"]), event)
        self.assertEqual(
            self.workspace.material_results()[0]["latest_steering_action"], "acknowledge"
        )

    def test_invalidated_result_cannot_be_steered(self) -> None:
        self.ensure_lifecycle_capability()
        event = self.event()
        self.lifecycle(kind=LifecycleChangeKind.TAKEDOWN)
        # Phase 5 raises its own typed validation error for an invalidated result.
        with self.assertRaises(Phase5ValidationError) as caught:
            self.service.steer(
                event_id=event["record_id"],
                action="acknowledge",
                principal_id="principal.phase5.owner",
                capability_id="capability.phase5.steer",
                idempotency_key="synthesis-steer-after-invalidation",
                recorded_at=T2,
            )
        self.assertIn("invalidated", str(caught.exception))

    def test_workspace_integrity_holds_after_the_new_record_type(self) -> None:
        self.ensure_lifecycle_capability()
        self.lifecycle()
        self.workspace.verify_integrity()
        exported = self.workspace.export_bytes()
        self.assertEqual(
            self.workspace.save_verified_export(exported)["content_hash"],
            json.loads(exported)["content_hash"],
        )


if __name__ == "__main__":
    unittest.main()
