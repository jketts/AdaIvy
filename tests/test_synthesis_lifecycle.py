"""Acceptance scenarios ERS-AC-06, ERS-AC-08, and ERS-AC-09.

Section 14 of `docs/phase-4/EXPLORATORY_RESEARCH_SYNTHESIS_V1.md` is normative.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from math_research.phase4a.records import (
    ActorKind,
    ApplicabilityOutcome,
    ApplicabilityReason,
    ApplicabilityStatus,
    RightsReason,
    RightsUse,
    RightsValue,
)
from math_research.phase4a.service import Phase4Service
from math_research.phase4a.workspace import Phase4Workspace

from math_research.synthesis.applicability import (
    AmbiguousApplicability,
    REQUIRED_CHECKS,
    applicability_snapshot,
    resolve_effective,
)
from math_research.synthesis.bridges import (
    LiteratureSearchStatus,
    audit_premises,
    evaluate_local_minimality,
    make_candidate,
)
from math_research.synthesis.influence import (
    InfluencedKind,
    InfluenceGraph,
    TriggerKind,
)
from math_research.synthesis.records import NoveltyStatus
from math_research.synthesis.state import (
    MathematicalWarrant,
    MismatchKind,
    SourceApplicability,
    SynthesisValidationError,
)

DIGEST = "sha256:" + "d" * 64


def review(
    record_id,
    card,
    status,
    outcome,
    sequence,
    *,
    supersedes=None,
    actor_kind="human",
    authority="human_final",
    checks=True,
    source_id="source.a",
):
    review_id = record_id if "." in record_id else f"applicability.{record_id}"
    supersedes_id = (
        supersedes
        if supersedes is None or "." in supersedes
        else f"applicability.{supersedes}"
    )
    payload = {
        "source_id": source_id,
        "evidence_card_id": card,
        "status": status,
        "outcome": outcome,
    }
    payload.update({key: checks for key in REQUIRED_CHECKS})
    return {
        "id": review_id,
        "record_type": "applicability_review",
        "actor_kind": actor_kind,
        "authority": authority,
        "actor_id": "actor.reviewer",
        "sequence": sequence,
        "supersedes": supersedes_id,
        "payload": payload,
    }


class BridgeMinimalityTests(unittest.TestCase):
    """ERS-AC-06: locally minimal bridge candidate."""

    def setUp(self) -> None:
        self.connected = [("result.a", DIGEST), ("result.b", DIGEST)]
        # The composition needs the commuting hypothesis; the full-support
        # hypothesis alone is not enough, and the pair is not needed either.
        self.required = "the operators commute"
        self.extra = "the prior has full support"

    def permits(self, claims):
        return self.required in claims

    def test_candidate_resolving_the_mismatch_with_no_smaller_success_is_minimal(self) -> None:
        candidate = make_candidate(
            claims=[self.required],
            resolves_mismatch=MismatchKind.DOMAIN,
            connected=self.connected,
            composition_value="permits the diagonal reduction",
            literature_search_protocol="local FTS5 protocol v1",
            literature_search_status=LiteratureSearchStatus.NOT_FOUND_UNDER_PROTOCOL,
        )
        evaluation = evaluate_local_minimality(
            candidate,
            target_conclusion="the iteration reaches a global optimum",
            permits_composition=self.permits,
        )
        self.assertTrue(evaluation.locally_minimal)
        self.assertTrue(evaluation.mismatch_resolved)
        self.assertEqual(evaluation.smaller_successful_subsets, ())
        # The empty set was actually evaluated, proving a bridge was needed.
        self.assertIn(((), False), evaluation.evaluated_subsets)
        # Minimality is recorded as local only.
        self.assertEqual(evaluation.value()["minimality_scope"], "local_only")

    def test_candidate_with_a_successful_proper_subset_is_not_minimal(self) -> None:
        """Fails if a proper-subset candidate succeeds."""
        candidate = make_candidate(
            claims=[self.required, self.extra],
            resolves_mismatch=MismatchKind.DOMAIN,
            connected=self.connected,
            composition_value="permits the diagonal reduction",
            literature_search_protocol="local FTS5 protocol v1",
        )
        evaluation = evaluate_local_minimality(
            candidate,
            target_conclusion="the iteration reaches a global optimum",
            permits_composition=self.permits,
        )
        self.assertFalse(evaluation.locally_minimal)
        self.assertIn((self.required,), evaluation.smaller_successful_subsets)

    def test_smaller_successful_candidate_cannot_be_omitted_from_the_record(self) -> None:
        """Forbidden: omission of a smaller successful candidate."""
        smaller = make_candidate(
            claims=[self.required],
            resolves_mismatch=MismatchKind.DOMAIN,
            connected=self.connected,
            composition_value="permits the reduction",
            literature_search_protocol="local FTS5 protocol v1",
        )
        larger = make_candidate(
            claims=[self.required, self.extra],
            resolves_mismatch=MismatchKind.DOMAIN,
            connected=self.connected,
            composition_value="permits the reduction",
            literature_search_protocol="local FTS5 protocol v1",
        )
        evaluation = evaluate_local_minimality(
            larger,
            target_conclusion="the iteration reaches a global optimum",
            permits_composition=self.permits,
            enumerated_candidates=[smaller, larger],
        )
        self.assertFalse(evaluation.locally_minimal)
        exported = evaluation.value()
        # Every enumerated subset and its outcome is in the exported evidence.
        self.assertEqual(len(exported["evaluated_subsets"]), len(evaluation.evaluated_subsets))
        self.assertIn([self.required], exported["smaller_successful_subsets"])

    def test_target_restatement_fails_the_premise_audit(self) -> None:
        """Forbidden: target restatement."""
        target = "the iteration reaches a global optimum"
        candidate = make_candidate(
            claims=[target],
            resolves_mismatch=MismatchKind.CONCLUSION_STRENGTH,
            connected=self.connected,
            composition_value="trivially permits the composition",
            literature_search_protocol="local FTS5 protocol v1",
        )
        passed, detail = audit_premises(candidate, target_conclusion=target)
        self.assertFalse(passed)
        self.assertIn("restates the target", detail)
        evaluation = evaluate_local_minimality(
            candidate,
            target_conclusion=target,
            permits_composition=lambda claims: target in claims,
        )
        self.assertFalse(evaluation.locally_minimal)
        self.assertFalse(evaluation.premise_audit_passed)

    def test_candidate_that_does_not_permit_the_composition_is_refused(self) -> None:
        candidate = make_candidate(
            claims=["an unrelated hypothesis"],
            resolves_mismatch=MismatchKind.DOMAIN,
            connected=self.connected,
            composition_value="claims to permit the reduction",
            literature_search_protocol="local FTS5 protocol v1",
        )
        with self.assertRaises(SynthesisValidationError):
            evaluate_local_minimality(
                candidate,
                target_conclusion="the iteration reaches a global optimum",
                permits_composition=self.permits,
            )

    def test_candidate_cannot_carry_a_proof_warrant(self) -> None:
        """A bridge candidate is a proposal, not a proved lemma."""
        for warrant in (MathematicalWarrant.PROOF_REVIEWED, MathematicalWarrant.FORMALLY_VERIFIED):
            with self.subTest(warrant=warrant), self.assertRaises(SynthesisValidationError):
                make_candidate(
                    claims=[self.required],
                    resolves_mismatch=MismatchKind.DOMAIN,
                    connected=self.connected,
                    composition_value="v",
                    literature_search_protocol="p",
                    warrant=warrant,
                )

    def test_search_noncoverage_never_becomes_novelty(self) -> None:
        """Forbidden: novelty language from search noncoverage."""
        self.assertNotIn("novel", [item.value for item in LiteratureSearchStatus])
        self.assertNotIn("novel", [item.value for item in NoveltyStatus])
        with self.assertRaises(SynthesisValidationError):
            make_candidate(
                claims=[self.required],
                resolves_mismatch=MismatchKind.DOMAIN,
                connected=self.connected,
                composition_value="v",
                literature_search_protocol="p",
                literature_search_status=LiteratureSearchStatus.NOT_FOUND_UNDER_PROTOCOL,
                novelty=NoveltyStatus.KNOWN_PRIOR_RESULT,
            )


class RightsZeroInfluenceTests(unittest.TestCase):
    """ERS-AC-08: rights-inapplicable source has zero influence."""

    def setUp(self) -> None:
        self.graph = InfluenceGraph()
        # Two independent chains: one from the blocked source, one from an
        # eligible alternative.
        self.graph.register(
            node_id="extraction.blocked",
            kind=InfluencedKind.EXTRACTION,
            direct_source_ids=["source.blocked"],
        )
        self.graph.register(
            node_id="extraction.allowed",
            kind=InfluencedKind.EXTRACTION,
            direct_source_ids=["source.allowed"],
        )
        for kind, node, parent in (
            (InfluencedKind.STRUCTURED_RESULT, "result.blocked", "extraction.blocked"),
            (InfluencedKind.STRUCTURED_RESULT, "result.allowed", "extraction.allowed"),
        ):
            self.graph.register(node_id=node, kind=kind, direct_input_ids=[parent])
        for kind, node in (
            (InfluencedKind.RESULT_RELATION, "relation.blocked"),
            (InfluencedKind.SYNTHESIS_PROPOSAL, "synthesis.blocked"),
            (InfluencedKind.VERIFICATION_INPUT, "verification.blocked"),
            (InfluencedKind.SURFACED_PARTIAL_RESULT, "surfaced.blocked"),
            (InfluencedKind.BRIDGE_CANDIDATE, "bridge.blocked"),
            (InfluencedKind.RETRIEVAL_DECISION, "retrieval.blocked"),
            (InfluencedKind.GRAPH_ADMISSION, "admission.blocked"),
            (InfluencedKind.BRANCH_INPUT, "branch.blocked"),
        ):
            self.graph.register(node_id=node, kind=kind, direct_input_ids=["result.blocked"])

    def test_prohibited_source_is_absent_from_every_input_class(self) -> None:
        self.graph.propagate(
            kind=TriggerKind.RIGHTS_PROHIBITION,
            source_id="source.blocked",
            actor_id="actor.owner",
            authority="human_final",
            detail="rights decision prohibits every tested use",
        )
        candidates = [node.node_id for node in self.graph.nodes()]
        eligible = self.graph.eligible_inputs(candidates)
        # Every artifact class named by ERS-AC-08 is absent.
        for node_id in (
            "extraction.blocked",
            "result.blocked",
            "relation.blocked",
            "synthesis.blocked",
            "verification.blocked",
            "surfaced.blocked",
            "bridge.blocked",
            "retrieval.blocked",
            "admission.blocked",
            "branch.blocked",
        ):
            self.assertNotIn(node_id, eligible)
        # The eligible alternative remains.
        self.assertIn("result.allowed", eligible)
        self.assertIn("extraction.allowed", eligible)

    def test_no_transitive_influence_of_the_blocked_source_remains(self) -> None:
        self.graph.propagate(
            kind=TriggerKind.RIGHTS_PROHIBITION,
            source_id="source.blocked",
            actor_id="actor.owner",
            authority="human_final",
            detail="prohibited",
        )
        for node_id in self.graph.current_node_ids():
            with self.subTest(node_id=node_id):
                self.assertNotIn("source.blocked", self.graph.transitive_sources(node_id))

    def test_exclusion_is_not_score_only_suppression(self) -> None:
        """Forbidden: score-only suppression after prohibited content was used.

        The prohibited artifacts must be absent from the input set entirely, not
        merely ranked lower, so no ordering of the candidate list can reintroduce
        them.
        """
        self.graph.propagate(
            kind=TriggerKind.RIGHTS_PROHIBITION,
            source_id="source.blocked",
            actor_id="actor.owner",
            authority="human_final",
            detail="prohibited",
        )
        candidates = [node.node_id for node in self.graph.nodes()]
        forward = self.graph.eligible_inputs(candidates)
        reverse = self.graph.eligible_inputs(list(reversed(candidates)))
        self.assertEqual(forward, reverse)
        self.assertEqual(set(forward), {"extraction.allowed", "result.allowed"})

    def test_influence_path_is_recorded_for_every_invalidation(self) -> None:
        result = self.graph.propagate(
            kind=TriggerKind.RIGHTS_PROHIBITION,
            source_id="source.blocked",
            actor_id="actor.owner",
            authority="human_final",
            detail="prohibited",
        )
        for record in result.invalidations:
            with self.subTest(node_id=record.node_id):
                self.assertEqual(record.influence_path[0], record.node_id)
                self.assertEqual(record.influence_path[-1], "source.blocked")


class LifecyclePropagationTests(unittest.TestCase):
    """ERS-AC-09: lifecycle and applicability propagation."""

    def build(self) -> InfluenceGraph:
        graph = InfluenceGraph()
        graph.register(
            node_id="extraction.a",
            kind=InfluencedKind.EXTRACTION,
            direct_source_ids=["source.a"],
        )
        graph.register(
            node_id="result.a", kind=InfluencedKind.STRUCTURED_RESULT, direct_input_ids=["extraction.a"]
        )
        graph.register(
            node_id="relation.ab", kind=InfluencedKind.RESULT_RELATION, direct_input_ids=["result.a"]
        )
        graph.register(
            node_id="admission.a", kind=InfluencedKind.GRAPH_ADMISSION, direct_input_ids=["relation.ab"]
        )
        graph.register(
            node_id="branch.a", kind=InfluencedKind.BRANCH_INPUT, direct_input_ids=["result.a"]
        )
        graph.register(
            node_id="synthesis.a", kind=InfluencedKind.SYNTHESIS_PROPOSAL, direct_input_ids=["relation.ab"]
        )
        graph.register(
            node_id="bridge.a", kind=InfluencedKind.BRIDGE_CANDIDATE, direct_input_ids=["synthesis.a"]
        )
        graph.register(
            node_id="verification.a",
            kind=InfluencedKind.VERIFICATION_INPUT,
            direct_input_ids=["synthesis.a"],
        )
        graph.register(
            node_id="surfaced.a",
            kind=InfluencedKind.SURFACED_PARTIAL_RESULT,
            direct_input_ids=["verification.a"],
        )
        return graph

    def test_each_contract_trigger_invalidates_the_whole_closure(self) -> None:
        for trigger in (
            TriggerKind.SOURCE_CORRECTION,
            TriggerKind.REVOCATION,
            TriggerKind.TAKEDOWN,
            TriggerKind.SUPPRESSION,
            TriggerKind.DELETION_REQUEST,
            TriggerKind.DELETION_COMPLETION,
            TriggerKind.RIGHTS_EXPIRY,
            TriggerKind.RIGHTS_PROHIBITION,
            TriggerKind.RIGHTS_CHANGE,
            TriggerKind.APPLICABILITY_REJECTED,
            TriggerKind.APPLICABILITY_UNRESOLVED,
            TriggerKind.APPLICABILITY_SCOPE_NARROWED,
            TriggerKind.APPLICABILITY_CONDITIONS_CHANGED,
            TriggerKind.APPLICABILITY_AUTHORITY_CHANGED,
        ):
            with self.subTest(trigger=trigger.value):
                graph = self.build()
                result = graph.propagate(
                    kind=trigger,
                    source_id="source.a",
                    actor_id="actor.owner",
                    authority="human_final",
                    detail=f"{trigger.value} occurred",
                )
                # Every influenced artifact class is invalidated.
                self.assertEqual(
                    set(result.invalidated_node_ids),
                    {
                        "extraction.a",
                        "result.a",
                        "relation.ab",
                        "admission.a",
                        "branch.a",
                        "synthesis.a",
                        "bridge.a",
                        "verification.a",
                        "surfaced.a",
                    },
                )
                self.assertEqual(result.current_node_ids, ())
                self.assertNotEqual(
                    result.closure_identity_before, result.closure_identity_after
                )

    def test_original_records_remain_immutable_and_addressable(self) -> None:
        """Forbidden: destructive history mutation."""
        graph = self.build()
        before = {node.node_id: node.value() for node in graph.nodes()}
        graph.propagate(
            kind=TriggerKind.TAKEDOWN,
            source_id="source.a",
            actor_id="actor.owner",
            authority="human_final",
            detail="takedown notice received",
        )
        after = {node.node_id: node.value() for node in graph.nodes()}
        self.assertEqual(before, after)
        # Still addressable by identity after invalidation.
        self.assertEqual(graph.get("surfaced.a").node_id, "surfaced.a")

    def test_no_stale_admitted_influence_survives(self) -> None:
        """Forbidden: stale admitted_under_policy influence."""
        graph = self.build()
        graph.propagate(
            kind=TriggerKind.APPLICABILITY_REJECTED,
            source_id="source.a",
            actor_id="actor.owner",
            authority="human_final",
            detail="superseding review rejected the use",
        )
        self.assertNotIn("admission.a", graph.current_node_ids())
        for record in graph.invalidations():
            self.assertEqual(record.value()["graph_admission"], "invalidated_by_later_record")

    def test_propagation_is_idempotent_and_does_not_double_invalidate(self) -> None:
        graph = self.build()
        first = graph.propagate(
            kind=TriggerKind.TAKEDOWN,
            source_id="source.a",
            actor_id="actor.owner",
            authority="human_final",
            detail="takedown notice received",
        )
        second = graph.propagate(
            kind=TriggerKind.TAKEDOWN,
            source_id="source.a",
            actor_id="actor.owner",
            authority="human_final",
            detail="takedown notice received",
        )
        self.assertEqual(len(first.invalidations), 9)
        self.assertEqual(second.invalidations, ())
        self.assertEqual(len(graph.invalidations()), 9)

    def test_revocation_is_not_treated_as_mathematical_falsity(self) -> None:
        """Forbidden: treating revocation as mathematical falsity.

        A revocation invalidates the current view. It must not touch any
        mathematical-warrant record, so the invalidation carries only graph
        admission.
        """
        graph = self.build()
        result = graph.propagate(
            kind=TriggerKind.REVOCATION,
            source_id="source.a",
            actor_id="actor.owner",
            authority="human_final",
            detail="rights revoked",
        )
        for record in result.invalidations:
            exported = record.value()
            self.assertEqual(exported["graph_admission"], "invalidated_by_later_record")
            self.assertNotIn("mathematical_warrant", exported)

    def test_replacement_is_linked_when_one_exists(self) -> None:
        graph = self.build()
        result = graph.propagate(
            kind=TriggerKind.SOURCE_CORRECTION,
            source_id="source.a",
            actor_id="actor.owner",
            authority="human_final",
            detail="corrected statement issued",
            replacements={"result.a": "result.a-corrected"},
        )
        replaced = {item.node_id: item.replacement_node_id for item in result.invalidations}
        self.assertEqual(replaced["result.a"], "result.a-corrected")
        self.assertIsNone(replaced["relation.ab"])


class EffectiveApplicabilityTests(unittest.TestCase):
    """Section 2.1: the effective review is imported, never produced here."""

    def test_checked_applicable_permits_use(self) -> None:
        records = [review("r1", "evidence-card.a1", "checked", "applicable", 1)]
        decision = resolve_effective(records, evidence_card_id="evidence-card.a1")
        self.assertTrue(decision.permits_use)
        self.assertIs(decision.status, SourceApplicability.CHECKED)

    def test_superseding_review_becomes_effective(self) -> None:
        records = [
            review("r1", "evidence-card.a1", "checked", "applicable", 1),
            review("r2", "evidence-card.a1", "rejected", "rejected", 2, supersedes="r1"),
        ]
        decision = resolve_effective(records, evidence_card_id="evidence-card.a1")
        self.assertIs(decision.status, SourceApplicability.REJECTED)
        self.assertFalse(decision.permits_use)
        self.assertEqual(decision.superseded_review_ids, ("applicability.r1",))

    def test_rejected_and_unresolved_both_fail_closed(self) -> None:
        for status, outcome in (("rejected", "rejected"), ("unresolved", "unresolved")):
            records = [review("r1", "evidence-card.a1", status, outcome, 1)]
            with self.subTest(status=status):
                decision = resolve_effective(records, evidence_card_id="evidence-card.a1")
                self.assertFalse(decision.permits_use)

    def test_forked_chain_is_ambiguous_and_fails_closed(self) -> None:
        records = [
            review("r1", "evidence-card.a1", "checked", "applicable", 1),
            review("r2", "evidence-card.a1", "rejected", "rejected", 2, supersedes="r1"),
            review("r3", "evidence-card.a1", "checked", "applicable", 3, supersedes="r1"),
        ]
        with self.assertRaises(AmbiguousApplicability):
            resolve_effective(records, evidence_card_id="evidence-card.a1")

    def test_nonhuman_authority_cannot_produce_an_effective_decision(self) -> None:
        for actor_kind, authority in (
            ("model", "human_final"),
            ("automation", "human_final"),
            ("human", "proposal"),
        ):
            records = [
                review(
                    "r1",
                    "evidence-card.a1",
                    "checked",
                    "applicable",
                    1,
                    actor_kind=actor_kind,
                    authority=authority,
                )
            ]
            with self.subTest(actor_kind=actor_kind, authority=authority):
                with self.assertRaises(SynthesisValidationError):
                    resolve_effective(records, evidence_card_id="evidence-card.a1")

    def test_checked_applicable_requires_every_review_dimension(self) -> None:
        records = [review("r1", "evidence-card.a1", "checked", "applicable", 1, checks=False)]
        with self.assertRaises(SynthesisValidationError):
            resolve_effective(records, evidence_card_id="evidence-card.a1")

    def test_missing_review_fails_closed(self) -> None:
        with self.assertRaises(SynthesisValidationError):
            resolve_effective([], evidence_card_id="evidence-card.a1")

    def test_dangling_supersession_fails_closed(self) -> None:
        records = [
            review(
                "r2",
                "evidence-card.a1",
                "checked",
                "applicable",
                2,
                supersedes="missing",
            )
        ]
        with self.assertRaises(SynthesisValidationError):
            resolve_effective(records, evidence_card_id="evidence-card.a1")

    def test_synthesis_record_id_alias_does_not_replace_phase4a_id(self) -> None:
        malformed = review("r1", "evidence-card.a1", "checked", "applicable", 1)
        malformed["record_id"] = malformed.pop("id")
        with self.assertRaises(SynthesisValidationError):
            resolve_effective([malformed], evidence_card_id="evidence-card.a1")

    def test_cyclic_supersession_fails_closed(self) -> None:
        records = [
            review("r1", "evidence-card.a1", "checked", "applicable", 1, supersedes="r2"),
            review("r2", "evidence-card.a1", "checked", "applicable", 2, supersedes="r1"),
        ]
        with self.assertRaises(SynthesisValidationError):
            resolve_effective(records, evidence_card_id="evidence-card.a1")

    def test_cross_card_supersession_fails_closed(self) -> None:
        records = [
            review("r1", "evidence-card.a1", "checked", "applicable", 1),
            review("r2", "evidence-card.a2", "checked", "applicable", 2, supersedes="r1"),
        ]
        with self.assertRaises(SynthesisValidationError):
            resolve_effective(records, evidence_card_id="evidence-card.a2")

    def test_reviews_over_one_source_are_resolved_per_card(self) -> None:
        """Phase 4A keys a review's subject to the source, not the card."""
        records = [
            review("r1", "evidence-card.a1", "checked", "applicable", 1),
            review("r2", "evidence-card.a2", "rejected", "rejected", 2),
        ]
        first = resolve_effective(records, evidence_card_id="evidence-card.a1")
        second = resolve_effective(records, evidence_card_id="evidence-card.a2")
        self.assertTrue(first.permits_use)
        self.assertFalse(second.permits_use)

    def test_snapshot_identity_is_deterministic_and_order_independent(self) -> None:
        records = [
            review("r1", "evidence-card.a1", "checked", "applicable", 1),
            review("r2", "evidence-card.a2", "unresolved", "unresolved", 2),
        ]
        self.assertEqual(
            applicability_snapshot(records), applicability_snapshot(list(reversed(records)))
        )

    def test_real_phase4a_workspace_review_shape_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.txt"
            source_path.write_text("Theorem: if n = 1 then n + 1 = 2.\n", encoding="utf-8")
            with Phase4Workspace(root / "workspace") as workspace:
                service = Phase4Service(workspace)
                service.initialize_policy(
                    actor_id="actor.policy", recorded_at="2026-08-20T00:00:00Z"
                )
                for intended_use in (
                    RightsUse.ACQUISITION,
                    RightsUse.STORAGE_AND_RETENTION,
                    RightsUse.PARSING,
                    RightsUse.EXCERPTING,
                ):
                    service.append_rights(
                        source_id="source.synthetic",
                        intended_use=intended_use,
                        value=RightsValue.ALLOWED,
                        reason_code=RightsReason.PERMITTED,
                        reason_detail=f"permit {intended_use.value}",
                        evidence_refs=(f"evidence.rights-{intended_use.value}",),
                        actor_id="actor.owner",
                        valid_from="2026-08-20T00:00:00Z",
                        valid_until=None,
                        recorded_at="2026-08-20T00:00:00Z",
                        lifecycle_id=f"rights-lifecycle.{intended_use.value}",
                    )
                service.intake_local(
                    source_path,
                    source_id="source.synthetic",
                    actor_id="actor.operator",
                    recorded_at="2026-08-20T00:00:01Z",
                )
                statement = "if n = 1 then n + 1 = 2"
                source_bytes = source_path.read_bytes()
                start = source_bytes.index(statement.encode("utf-8"))
                card = service.create_evidence_card(
                    source_id="source.synthetic",
                    span_byte_ranges=((start, start + len(statement.encode("utf-8"))),),
                    bibliographic_identity="Synthetic theorem fixture",
                    imported_statement=statement,
                    hypotheses=("n = 1",),
                    definitions=("n is an integer",),
                    scope=("synthetic local fixture",),
                    exceptions=(),
                    actor_id="actor.curator",
                    actor_kind=ActorKind.HUMAN,
                    reason_detail="exact source-derived statement",
                    recorded_at="2026-08-20T00:00:02Z",
                )
                review_record = service.review_applicability(
                    source_id="source.synthetic",
                    evidence_card_id=card.id,
                    status=ApplicabilityStatus.CHECKED,
                    outcome=ApplicabilityOutcome.APPLICABLE,
                    reason_code=ApplicabilityReason.APPLICABLE,
                    reason_detail="all applicability dimensions checked",
                    evidence_refs=(card.id,),
                    actor_id="actor.reviewer",
                    actor_kind=ActorKind.HUMAN,
                    recorded_at="2026-08-20T00:00:03Z",
                    checks={key: True for key in REQUIRED_CHECKS},
                )

                decision = resolve_effective(
                    workspace.records(), evidence_card_id=card.id
                )

        self.assertEqual(review_record.id, decision.review_record_id)
        self.assertTrue(decision.permits_use)


if __name__ == "__main__":
    unittest.main()
