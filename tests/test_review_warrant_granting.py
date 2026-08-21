"""ADR-0042: recorded human review is the only path from a real run to a warrant.

The forbidden outcome for this slice is a warrant that traces to a model's own
say-so. It is demonstrated impossible three ways:

1. by construction: `review/decisions.py` and `review/projection.py` never read a
   Phase 2 `recommendation` as a verdict, asserted by parsing their AST for the
   absence of any comparison against `manual_review`;
2. by gate: accepting a candidate requires an explicit independent-check
   attestation, and `formal_proof` is refused under the human-review basis with
   no weaker warrant granted as a fallback;
3. by measurement: every refusal branch is exercised and the resulting
   `TrustPolicy` projection is measured rather than assumed.

Every instant in this module is an explicit argument. Nothing here reads a clock.
"""

from __future__ import annotations

import ast
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from math_research.application.problem_intake import load_problem_definition_file
from math_research.domain.entities import (
    AlignmentStatus,
    ClaimOrigin,
    Disposition,
    ObligationStatus,
    OpaqueId,
    RecordStatus,
    ResearchDossier,
    VerificationOutcome,
    WarrantKind,
    oid,
)
from math_research.domain.policies import TrustPolicy
from math_research.domain.repositories import InMemoryTrustStore
from math_research.interchange import (
    export_dossier_bytes,
    export_dossier_dict,
    import_trusted_replay,
    validate_dossier_payload,
    write_dossier,
)
from math_research.phase2.artifacts import FileArtifactStore
from math_research.phase2.baseline_loop import BaselineResearchLoop, deterministic_fake_results
from math_research.phase2.model_gateway import ScriptedModelGateway
from math_research.phase2.records import BudgetLimits, RunStatus, VerifierIndependence
from math_research.phase3b import HASH_PROFILE as PHASE3B_HASH_PROFILE
from math_research.phase3b import SCHEMA_VERSION as PHASE3B_SCHEMA_VERSION
from math_research.phase3b.serialization import (
    canonical_hash as phase3b_canonical_hash,
    finding_content_hash,
    sha256_bytes as phase3b_sha256,
)
from math_research.review import (
    FORMAL_KERNEL_WARRANT_KINDS,
    HUMAN_REVIEW_WARRANT_KINDS,
    KERNEL_CHECKED_OUTCOMES,
)
from math_research.review.decisions import (
    build_alignment_decision,
    build_human_review_warrant,
    build_kernel_warrant,
    build_obligation_discharge,
    build_review_verdict,
)
from math_research.review.journal import ReviewJournal
from math_research.review.projection import build_successor, parse_instant
from math_research.review.records import (
    AlignmentDecision,
    ReviewRefused,
    ReviewVerdict,
    ReviewerIdentity,
    ReviewerKind,
)
from math_research.review.serialization import semantic_record_hash
import math_research.review_cli as review_cli

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "fixtures" / "review" / "sum-of-two-odds-is-even-v1.json"
KERNEL_FIXTURE = REPO_ROOT / "fixtures" / "review" / "phase3b-kernel-checked-odds-v1.json"
DECISIONS_MODULE = REPO_ROOT / "src" / "math_research" / "review" / "decisions.py"
PROJECTION_MODULE = REPO_ROOT / "src" / "math_research" / "review" / "projection.py"

INTAKE_INSTANT = parse_instant("2026-08-21T00:00:00Z")
LOOP_INSTANT = datetime(2026, 8, 21, 6, 0, tzinfo=timezone.utc)
VERDICT_AT = "2026-08-21T12:00:00.000000Z"
ALIGNMENT_AT = "2026-08-21T12:05:00.000000Z"
GRANT_AT = "2026-08-21T12:10:00.000000Z"
DISCHARGE_AT = "2026-08-21T12:15:00.000000Z"
PROJECT_AT = parse_instant("2026-08-21T13:00:00Z")

RUN_ID = OpaqueId("run.review.odds.v1")
SLUG = "sum-of-two-odds-is-even"
TARGET_CLAIM = OpaqueId(f"claim.{SLUG}.odd_plus_odd_is_even")
ALIGNMENT_ID = OpaqueId(f"alignment.{SLUG}.v1")
WARRANT_OBLIGATION = OpaqueId(f"obligation.{SLUG}.target_unwarranted")
ALIGNMENT_OBLIGATION = OpaqueId(f"obligation.{SLUG}.alignment_unapproved")

ALICE = ReviewerIdentity(
    id=oid("reviewer.alice"),
    kind=ReviewerKind.HUMAN,
    attestation="re-derived a+b=2(k+l+1) from the accepted definitions",
)
BOT = ReviewerIdentity(
    id=oid("verifier.model.gpt"),
    kind=ReviewerKind.MODEL,
    attestation="the verifier recommends manual_review",
)


def intake_dossier() -> ResearchDossier:
    return load_problem_definition_file(FIXTURE, instant=INTAKE_INSTANT).dossier


class ReviewFixture:
    """A real Phase 2 run driven to `awaiting_review`, plus a review journal."""

    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dossier = intake_dossier()
        self.journal = ReviewJournal(self.root)
        self.workspace = self.journal.durable
        self.artifacts = FileArtifactStore(self.root / "artifacts")

    def close(self) -> None:
        self.journal.close()
        self.temporary.cleanup()

    def loop(self) -> BaselineResearchLoop:
        proposer, verifier = deterministic_fake_results(
            self.dossier.formalization.target_claim_id.value,
            self.dossier.formalization.assumption_claim_ids[0].value,
        )
        gateway = ScriptedModelGateway({"proposer": [proposer], "verifier": [verifier]})
        return BaselineResearchLoop(
            workspace=self.workspace,
            artifacts=self.artifacts,
            proposer=gateway,
            verifier=gateway,
            independence=VerifierIndependence(
                context_isolated=True, separate_model_call=True, different_model=False,
                different_provider=False, deterministic_checker=False,
                independently_implemented_checker=False, formal_kernel=False,
            ),
            now=lambda: LOOP_INSTANT,
        )

    def drive_to_review(self) -> None:
        loop = self.loop()
        loop.start(
            run_id=RUN_ID,
            dossier=self.dossier,
            limits=BudgetLimits(
                max_input_tokens=20_000, max_output_tokens=4_000, max_cost_microusd=1_000,
                max_wall_milliseconds=120_000, max_attempts=4,
            ),
        )
        final = loop.run_to_terminal(RUN_ID)
        assert final.status is RunStatus.AWAITING_REVIEW, final.status

    # -- decision helpers ---------------------------------------------------

    def record_verdict(
        self,
        *,
        reviewer: ReviewerIdentity = ALICE,
        verdict: ReviewVerdict = ReviewVerdict.ACCEPT_CANDIDATE,
        independently_checked: bool = True,
        rationale: str = "the algebra covers every pair of odd integers",
        recorded_at: str = VERDICT_AT,
    ) -> dict[str, object]:
        proposal, _ = build_review_verdict(
            runs=self.workspace,
            artifacts=self.artifacts,
            run_id=RUN_ID,
            reviewer=reviewer,
            verdict=verdict,
            independently_checked=independently_checked,
            rationale=rationale,
        )
        record, _ = self.journal.append_once(proposal, recorded_at=recorded_at)
        return record

    def approve_alignment(
        self,
        *,
        approver: ReviewerIdentity = ALICE,
        decision: AlignmentDecision = AlignmentDecision.APPROVE,
        recorded_at: str = ALIGNMENT_AT,
    ) -> dict[str, object]:
        proposal = build_alignment_decision(
            runs=self.workspace,
            run_id=RUN_ID,
            alignment_id=ALIGNMENT_ID,
            approver=approver,
            decision=decision,
            rationale="Odd and Even are used with their stated definitions",
        )
        record, _ = self.journal.append_once(proposal, recorded_at=recorded_at)
        return record

    def grant(
        self,
        *,
        kind: WarrantKind = WarrantKind.RIGOROUS_DERIVATION,
        grantor: ReviewerIdentity = ALICE,
        scope: str = "all pairs of odd integers",
        recorded_at: str = GRANT_AT,
    ) -> dict[str, object]:
        proposal = build_human_review_warrant(
            runs=self.workspace,
            journal_decisions=self.journal.decisions(),
            run_id=RUN_ID,
            claim_id=TARGET_CLAIM,
            kind=kind,
            scope=scope,
            grantor=grantor,
        )
        record, _ = self.journal.append_once(proposal, recorded_at=recorded_at)
        return record

    def grant_from_kernel(
        self,
        finding: dict[str, object] | None = None,
        *,
        kind: WarrantKind = WarrantKind.FORMAL_PROOF,
        recorded_at: str = GRANT_AT,
    ) -> dict[str, object]:
        body = json.dumps(finding if finding is not None else kernel_finding()).encode("utf-8")
        proposal = build_kernel_warrant(
            runs=self.workspace,
            journal_decisions=self.journal.decisions(),
            run_id=RUN_ID,
            finding_bytes=body,
            kind=kind,
            scope="all pairs of odd integers, Lean kernel checked",
            grantor=ALICE,
        )
        record, _ = self.journal.append_once(proposal, recorded_at=recorded_at)
        return record

    def discharge(
        self,
        obligation_id: OpaqueId,
        warrant_id: str,
        *,
        reviewer: ReviewerIdentity = ALICE,
        recorded_at: str = DISCHARGE_AT,
    ) -> dict[str, object]:
        proposal = build_obligation_discharge(
            runs=self.workspace,
            journal_decisions=self.journal.decisions(),
            run_id=RUN_ID,
            obligation_id=obligation_id,
            warrant_id=warrant_id,
            reviewer=reviewer,
            rationale="the granted warrant covers the obligation's claim",
        )
        record, _ = self.journal.append_once(proposal, recorded_at=recorded_at)
        return record

    def project(self, *, projected_by: OpaqueId = ALICE.id, at: datetime = PROJECT_AT):
        return build_successor(
            runs=self.workspace,
            run_id=RUN_ID,
            journal_export=self.journal.export(),
            projected_at=at,
            projected_by=projected_by,
        )

    def happy_path(self) -> str:
        """Verdict, alignment approval, warrant, and both discharges."""

        self.record_verdict()
        self.approve_alignment()
        warrant_id = str(self.grant()["payload"]["warrant_id"])
        self.discharge(WARRANT_OBLIGATION, warrant_id)
        self.discharge(ALIGNMENT_OBLIGATION, warrant_id)
        return warrant_id


def kernel_finding(**overrides: object) -> dict[str, object]:
    """A Phase 3B `kernel_checked` finding, re-hashed after any override."""

    value = json.loads(KERNEL_FIXTURE.read_text(encoding="utf-8"))
    value.update(overrides)
    value["content_hash"] = finding_content_hash(value)
    return value


class ReviewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = ReviewFixture()
        self.addCleanup(self.fixture.close)
        self.fixture.drive_to_review()

    def assertRefused(self, code: str, callable_, *args, **kwargs) -> ReviewRefused:
        with self.assertRaises(ReviewRefused) as caught:
            callable_(*args, **kwargs)
        self.assertEqual([code], list(caught.exception.codes))
        refusal = caught.exception.refusals[0]
        self.assertTrue(refusal.unmet_precondition.strip(), "a refusal must name its precondition")
        self.assertTrue(refusal.detail.strip(), "a refusal must carry a detail")
        return caught.exception


# ---------------------------------------------------------------------------
# The intake starting point: no warrant exists and none can be inferred.
# ---------------------------------------------------------------------------

class IntakeStartingPointTests(unittest.TestCase):
    def test_the_intake_dossier_is_unresolved_with_two_open_obligations(self) -> None:
        dossier = intake_dossier()
        projection = TrustPolicy(dossier).target_resolution()
        self.assertEqual("unknown", projection.logical_status)
        self.assertEqual((), projection.warrant_kinds)
        self.assertEqual((), dossier.warrants)
        self.assertEqual((), dossier.evidence)
        self.assertEqual((), dossier.verification_records)
        self.assertEqual(
            [ALIGNMENT_OBLIGATION.value, WARRANT_OBLIGATION.value],
            sorted(item.id.value for item in dossier.obligations),
        )
        self.assertTrue(
            all(item.status is ObligationStatus.OPEN for item in dossier.obligations)
        )
        self.assertIs(AlignmentStatus.PROPOSED, dossier.semantic_alignment.status)


# ---------------------------------------------------------------------------
# Happy path.
# ---------------------------------------------------------------------------

class HappyPathTests(ReviewTestCase):
    def test_awaiting_review_reaches_a_granted_warrant_and_a_proved_target(self) -> None:
        warrant_id = self.fixture.happy_path()
        projection = self.fixture.project()
        successor = projection.successor

        self.assertNotEqual(projection.prior_dossier_hash, projection.successor_hash)
        self.assertEqual(1, len(successor.warrants))
        warrant = successor.warrants[0]
        self.assertEqual(warrant_id, warrant.id.value)
        self.assertIs(WarrantKind.RIGOROUS_DERIVATION, warrant.kind)
        self.assertIs(RecordStatus.ACTIVE, warrant.status)
        self.assertEqual(oid("reviewer.alice"), warrant.created_by)

        # evidence_ids and verification_record_ids point at records that exist
        evidence_ids = {item.id for item in successor.evidence}
        verification_ids = {item.id for item in successor.verification_records}
        self.assertTrue(set(warrant.evidence_ids) <= evidence_ids)
        self.assertTrue(set(warrant.verification_record_ids) <= verification_ids)
        self.assertEqual(1, len(warrant.evidence_ids))
        self.assertEqual(1, len(warrant.verification_record_ids))

        self.assertIs(Disposition.ACCEPTED, successor.evidence[0].disposition)
        check = successor.verification_records[0]
        self.assertIs(VerificationOutcome.PASS, check.outcome)
        self.assertEqual("human_review", check.verifier_kind)
        self.assertTrue(check.independent_from_proposer)

        self.assertIs(AlignmentStatus.RESEARCHER_APPROVED, successor.semantic_alignment.status)
        self.assertEqual(oid("reviewer.alice"), successor.semantic_alignment.approved_by)
        self.assertTrue(
            all(item.status is ObligationStatus.DISCHARGED for item in successor.obligations)
        )
        self.assertEqual(
            {warrant_id},
            {item.discharged_by_warrant_id.value for item in successor.obligations},
        )

        measured = TrustPolicy(successor).target_resolution()
        self.assertEqual("proved", measured.logical_status)
        self.assertEqual("approved_equivalent", measured.semantic_alignment_status)
        self.assertEqual(("rigorous_derivation",), measured.warrant_kinds)
        self.assertEqual((), measured.blockers)
        self.assertEqual((), validate_dossier_payload(export_dossier_dict(successor)))

    def test_the_successor_names_the_reviewer_and_the_prior_dossier_hash(self) -> None:
        self.fixture.happy_path()
        projection = self.fixture.project()
        events = [
            item
            for item in projection.successor.audit_events
            if item.event_type == "review_journal_projected"
        ]
        self.assertEqual(1, len(events))
        payload = dict(events[0].payload)
        self.assertEqual(projection.prior_dossier_hash, payload["prior_dossier_hash"])
        self.assertEqual("reviewer.alice", payload["reviewers"])
        self.assertEqual("reviewer.alice", payload["projected_by"])
        self.assertEqual("1", payload["warrants_granted"])
        self.assertEqual(oid("reviewer.alice"), events[0].created_by)

    def test_the_prior_dossier_bytes_are_untouched(self) -> None:
        before = export_dossier_bytes(self.fixture.dossier)
        self.fixture.happy_path()
        projection = self.fixture.project()
        reloaded = self.fixture.workspace.load_dossier(self.fixture.dossier.id)
        self.assertEqual(before, export_dossier_bytes(reloaded))
        self.assertEqual((), reloaded.warrants)
        self.assertIs(AlignmentStatus.PROPOSED, reloaded.semantic_alignment.status)
        self.assertTrue(all(item.status is ObligationStatus.OPEN for item in reloaded.obligations))
        self.assertNotEqual(reloaded.id, projection.successor.id)

    def test_kernel_attestation_grants_a_formal_proof_warrant(self) -> None:
        self.fixture.approve_alignment()
        record = self.fixture.grant_from_kernel()
        warrant_id = str(record["payload"]["warrant_id"])
        self.fixture.discharge(WARRANT_OBLIGATION, warrant_id)
        self.fixture.discharge(ALIGNMENT_OBLIGATION, warrant_id)
        projection = self.fixture.project()
        warrant = projection.successor.warrants[0]
        self.assertIs(WarrantKind.FORMAL_PROOF, warrant.kind)
        check = projection.successor.verification_records[0]
        self.assertEqual("lean_kernel_phase3b", check.verifier_kind)
        self.assertIs(VerificationOutcome.PASS, check.outcome)
        self.assertTrue(
            any("does not depend on any axioms" in item.content for item in projection.successor.evidence)
        )
        measured = TrustPolicy(projection.successor).target_resolution()
        self.assertEqual("proved", measured.logical_status)
        self.assertEqual(("formal_proof",), measured.warrant_kinds)

    def test_both_kernel_checked_outcomes_are_accepted(self) -> None:
        self.assertEqual(
            ("kernel_checked", "kernel_checked_approved_standard_axioms"),
            KERNEL_CHECKED_OUTCOMES,
        )
        self.fixture.approve_alignment()
        record = self.fixture.grant_from_kernel(
            kernel_finding(
                outcome="kernel_checked_approved_standard_axioms",
                approved_axioms=["Classical.choice", "propext"],
            )
        )
        self.assertEqual("formal_kernel", record["payload"]["basis"])


# ---------------------------------------------------------------------------
# Adversarial: a model recommendation alone cannot produce a warrant.
# ---------------------------------------------------------------------------

class ModelCannotWarrantItselfTests(ReviewTestCase):
    def test_the_run_reaches_awaiting_review_on_a_manual_review_recommendation(self) -> None:
        proposals = self.fixture.workspace.list_proposals(RUN_ID)
        finding = next(item for item in proposals if item.proposal_kind == "verifier_finding")
        body = json.loads(self.fixture.artifacts.get(finding.artifact_hash))
        self.assertEqual("manual_review", body["recommendation"])
        self.assertEqual("supports", body["findings"][0]["outcome"])
        # The model says it supports the target. Measured trust is unchanged.
        stored = self.fixture.workspace.load_dossier(self.fixture.dossier.id)
        self.assertEqual("unknown", TrustPolicy(stored).target_resolution().logical_status)

    def test_a_model_reviewer_identity_is_refused(self) -> None:
        self.assertRefused(
            "reviewer_identity_not_human", self.fixture.record_verdict, reviewer=BOT
        )
        self.assertEqual((), self.fixture.journal.decisions())

    def test_accepting_without_an_independent_check_attestation_is_refused(self) -> None:
        error = self.assertRefused(
            "independent_check_not_attested",
            self.fixture.record_verdict,
            independently_checked=False,
        )
        self.assertIn("manual_review", error.refusals[0].detail)

    def test_a_recorded_verdict_alone_does_not_grant_a_warrant(self) -> None:
        self.fixture.record_verdict()
        self.assertRefused("semantic_alignment_not_approved", self.fixture.grant)
        self.assertEqual(
            (), self.fixture.journal.decisions(decision_kind="warrant_grant")
        )

    def test_an_unattested_verdict_cannot_back_a_warrant(self) -> None:
        self.fixture.record_verdict(
            verdict=ReviewVerdict.INCONCLUSIVE, independently_checked=False
        )
        self.fixture.approve_alignment()
        self.assertRefused("supporting_review_verdict_not_accepting", self.fixture.grant)

    def test_no_command_derives_a_verdict_from_a_recommendation(self) -> None:
        """By construction: neither module compares against a recommendation value."""

        for path in (DECISIONS_MODULE, PROJECTION_MODULE):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            literals = {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            }
            comparisons = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Compare)
                and any(
                    isinstance(item, ast.Constant) and item.value == "manual_review"
                    for item in node.comparators
                )
            ]
            self.assertEqual([], comparisons, f"{path.name} branches on a recommendation")
            self.assertNotIn("supports", literals, f"{path.name} branches on a finding outcome")

    def test_the_projected_evidence_names_the_human_who_accepted_it(self) -> None:
        self.fixture.happy_path()
        projection = self.fixture.project()
        content = projection.successor.evidence[0].content
        self.assertIn("reviewer: reviewer.alice", content)
        self.assertIn("independently_checked: true", content)
        self.assertIn("verifier_recommendation (input, not a verdict): manual_review", content)


# ---------------------------------------------------------------------------
# Refusals: review verdict.
# ---------------------------------------------------------------------------

class VerdictRefusalTests(ReviewTestCase):
    def test_unknown_run_is_refused(self) -> None:
        with self.assertRaises(ReviewRefused) as caught:
            build_review_verdict(
                runs=self.fixture.workspace,
                artifacts=self.fixture.artifacts,
                run_id=OpaqueId("run.absent"),
                reviewer=ALICE,
                verdict=ReviewVerdict.ACCEPT_CANDIDATE,
                independently_checked=True,
                rationale="x",
            )
        self.assertEqual(("run_not_found",), caught.exception.codes)

    def test_a_run_that_is_not_awaiting_review_is_refused(self) -> None:
        self.fixture.loop().cancel(RUN_ID)
        error = self.assertRefused("run_not_awaiting_review", self.fixture.record_verdict)
        self.assertIn("cancelled", error.refusals[0].detail)

    def test_an_empty_rationale_is_refused(self) -> None:
        self.assertRefused("rationale_missing", self.fixture.record_verdict, rationale="   ")

    def test_an_empty_attestation_is_refused(self) -> None:
        self.assertRefused(
            "reviewer_attestation_missing",
            self.fixture.record_verdict,
            reviewer=ReviewerIdentity(
                id=oid("reviewer.mute"), kind=ReviewerKind.HUMAN, attestation=" "
            ),
        )

    def test_the_proposal_source_cannot_review_its_own_output(self) -> None:
        source = self.fixture.workspace.list_proposals(RUN_ID)[0].source_id
        self.assertRefused(
            "reviewer_is_proposal_source",
            self.fixture.record_verdict,
            reviewer=ReviewerIdentity(
                id=oid(source), kind=ReviewerKind.HUMAN, attestation="I wrote it"
            ),
        )

    def test_a_missing_finding_artifact_is_refused(self) -> None:
        class EmptyStore:
            def get(self, content_hash: str) -> bytes:  # pragma: no cover - never reached
                raise AssertionError("must not be read")

            def exists(self, content_hash: str) -> bool:
                return False

        with self.assertRaises(ReviewRefused) as caught:
            build_review_verdict(
                runs=self.fixture.workspace,
                artifacts=EmptyStore(),
                run_id=RUN_ID,
                reviewer=ALICE,
                verdict=ReviewVerdict.ACCEPT_CANDIDATE,
                independently_checked=True,
                rationale="checked",
            )
        self.assertEqual(("verifier_finding_artifact_missing",), caught.exception.codes)

    def test_a_finding_naming_another_claim_is_refused(self) -> None:
        proposals = self.fixture.workspace.list_proposals(RUN_ID)
        finding = next(item for item in proposals if item.proposal_kind == "verifier_finding")
        body = json.loads(self.fixture.artifacts.get(finding.artifact_hash))
        body["target_claim_id"] = "claim.somewhere.else"

        class SwappedStore:
            def __init__(self, inner, target_hash, payload) -> None:
                self.inner = inner
                self.target_hash = target_hash
                self.payload = payload

            def exists(self, content_hash: str) -> bool:
                return True

            def get(self, content_hash: str) -> bytes:
                if content_hash == self.target_hash:
                    return self.payload
                return self.inner.get(content_hash)

        payload = json.dumps(
            body, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        store = SwappedStore(self.fixture.artifacts, finding.artifact_hash, payload)
        with self.assertRaises(ReviewRefused) as caught:
            build_review_verdict(
                runs=self.fixture.workspace,
                artifacts=store,
                run_id=RUN_ID,
                reviewer=ALICE,
                verdict=ReviewVerdict.ACCEPT_CANDIDATE,
                independently_checked=True,
                rationale="checked",
            )
        self.assertEqual(("verifier_finding_artifact_corrupt",), caught.exception.codes)


# ---------------------------------------------------------------------------
# Refusals: alignment.
# ---------------------------------------------------------------------------

class AlignmentRefusalTests(ReviewTestCase):
    def test_an_alignment_from_another_dossier_is_refused(self) -> None:
        with self.assertRaises(ReviewRefused) as caught:
            build_alignment_decision(
                runs=self.fixture.workspace,
                run_id=RUN_ID,
                alignment_id=OpaqueId("alignment.other.v1"),
                approver=ALICE,
                decision=AlignmentDecision.APPROVE,
                rationale="x",
            )
        self.assertEqual(("alignment_not_found",), caught.exception.codes)

    def test_a_model_approver_is_refused(self) -> None:
        self.assertRefused(
            "reviewer_identity_not_human", self.fixture.approve_alignment, approver=BOT
        )

    def test_a_disputed_alignment_does_not_license_a_warrant(self) -> None:
        self.fixture.record_verdict()
        self.fixture.approve_alignment(decision=AlignmentDecision.DISPUTE)
        self.assertRefused("semantic_alignment_not_approved", self.fixture.grant)
        projection_source = self.fixture.journal.decisions(
            decision_kind="semantic_alignment_decision"
        )
        self.assertEqual("dispute", projection_source[0]["payload"]["decision"])

    def test_a_dispute_projects_as_disputed_and_leaves_the_target_unresolved(self) -> None:
        self.fixture.record_verdict()
        self.fixture.approve_alignment(decision=AlignmentDecision.DISPUTE)
        projection = self.fixture.project()
        self.assertIs(AlignmentStatus.DISPUTED, projection.successor.semantic_alignment.status)
        measured = TrustPolicy(projection.successor).target_resolution()
        self.assertEqual("unknown", measured.logical_status)
        self.assertEqual((), measured.warrant_kinds)


# ---------------------------------------------------------------------------
# Refusals: warrant granting under human review.
# ---------------------------------------------------------------------------

class HumanReviewWarrantRefusalTests(ReviewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fixture.record_verdict()
        self.fixture.approve_alignment()

    def test_formal_proof_is_refused_without_a_kernel_attestation(self) -> None:
        error = self.assertRefused(
            "formal_proof_requires_kernel_attestation",
            self.fixture.grant,
            kind=WarrantKind.FORMAL_PROOF,
        )
        self.assertIn("No weaker warrant kind", error.refusals[0].detail)
        self.assertEqual((), self.fixture.journal.decisions(decision_kind="warrant_grant"))

    def test_a_refused_formal_proof_does_not_fall_back_to_a_weaker_kind(self) -> None:
        with self.assertRaises(ReviewRefused):
            self.fixture.grant(kind=WarrantKind.FORMAL_PROOF)
        projection_attempt = self.fixture.project()
        self.assertEqual((), projection_attempt.successor.warrants)
        self.assertEqual("unknown", TrustPolicy(projection_attempt.successor)
                         .target_resolution().logical_status)

    def test_model_agreement_is_refused(self) -> None:
        self.assertRefused(
            "warrant_kind_not_reviewable", self.fixture.grant, kind=WarrantKind.MODEL_AGREEMENT
        )

    def test_source_report_is_refused(self) -> None:
        self.assertRefused(
            "source_report_requires_source_applicability_record",
            self.fixture.grant,
            kind=WarrantKind.SOURCE_REPORT,
        )

    def test_the_reviewable_kinds_are_exactly_three(self) -> None:
        self.assertEqual(
            ("exact_counterexample", "experimental_observation", "rigorous_derivation"),
            HUMAN_REVIEW_WARRANT_KINDS,
        )
        self.assertEqual(("formal_proof",), FORMAL_KERNEL_WARRANT_KINDS)

    def test_an_empty_scope_is_refused(self) -> None:
        self.assertRefused("warrant_scope_missing", self.fixture.grant, scope="  ")

    def test_a_claim_outside_the_dossier_is_refused(self) -> None:
        with self.assertRaises(ReviewRefused) as caught:
            build_human_review_warrant(
                runs=self.fixture.workspace,
                journal_decisions=self.fixture.journal.decisions(),
                run_id=RUN_ID,
                claim_id=OpaqueId("claim.not.here"),
                kind=WarrantKind.RIGOROUS_DERIVATION,
                scope="whatever",
                grantor=ALICE,
            )
        self.assertEqual(("claim_not_in_dossier",), caught.exception.codes)

    def test_an_experimental_observation_warrant_only_supports(self) -> None:
        record = self.fixture.grant(kind=WarrantKind.EXPERIMENTAL_OBSERVATION)
        warrant_id = str(record["payload"]["warrant_id"])
        self.fixture.discharge(WARRANT_OBLIGATION, warrant_id)
        self.fixture.discharge(ALIGNMENT_OBLIGATION, warrant_id)
        measured = TrustPolicy(self.fixture.project().successor).target_resolution()
        self.assertEqual("supported", measured.logical_status)


class WarrantWithoutVerdictTests(ReviewTestCase):
    def test_a_warrant_without_any_verdict_is_refused(self) -> None:
        self.fixture.approve_alignment()
        self.assertRefused("supporting_review_verdict_missing", self.fixture.grant)


# ---------------------------------------------------------------------------
# Refusals: warrant granting from a Phase 3B finding.
# ---------------------------------------------------------------------------

REFUSING_OUTCOMES = (
    "kernel_checked_unapproved_assumptions",
    "policy_rejection",
    "elaboration_failure",
    "meaning_test_failure",
    "timeout",
    "output_limit",
    "sandbox_failure",
)


class KernelWarrantRefusalTests(ReviewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fixture.approve_alignment()

    def test_every_non_kernel_checked_outcome_is_refused(self) -> None:
        for outcome in REFUSING_OUTCOMES:
            with self.subTest(outcome=outcome):
                error = self.assertRefused(
                    "formal_check_outcome_not_kernel_checked",
                    self.fixture.grant_from_kernel,
                    kernel_finding(outcome=outcome),
                )
                self.assertIn(outcome, error.refusals[0].detail)
        self.assertEqual((), self.fixture.journal.decisions(decision_kind="warrant_grant"))

    def test_unapproved_assumptions_are_refused_before_the_outcome_gate_passes(self) -> None:
        self.assertRefused(
            "formal_check_outcome_not_kernel_checked",
            self.fixture.grant_from_kernel,
            kernel_finding(
                outcome="kernel_checked_unapproved_assumptions",
                unapproved_assumptions=["sorryAx"],
            ),
        )

    def test_unapproved_assumptions_on_a_kernel_checked_outcome_are_refused(self) -> None:
        self.assertRefused(
            "formal_check_unapproved_assumptions",
            self.fixture.grant_from_kernel,
            kernel_finding(unapproved_assumptions=["sorryAx"]),
        )

    def test_a_finding_claiming_its_own_warrant_is_refused(self) -> None:
        error = self.assertRefused(
            "finding_claims_self_granted_warrant",
            self.fixture.grant_from_kernel,
            kernel_finding(epistemic_warrant_created=True),
        )
        self.assertIn("cannot grant itself trust", error.refusals[0].detail)

    def test_a_finding_claiming_semantic_approval_is_refused(self) -> None:
        for flag in (
            "semantic_alignment_approved",
            "source_applicability_approved",
            "novelty_approved",
            "significance_approved",
            "contribution_approved",
        ):
            with self.subTest(flag=flag):
                self.assertRefused(
                    "finding_claims_unapproved_promotion",
                    self.fixture.grant_from_kernel,
                    kernel_finding(**{flag: True}),
                )

    def test_a_finding_that_claims_a_trust_effect_is_refused(self) -> None:
        self.assertRefused(
            "finding_violates_proposal_contract",
            self.fixture.grant_from_kernel,
            kernel_finding(trust_effect="warrants_target"),
        )
        self.assertRefused(
            "finding_violates_proposal_contract",
            self.fixture.grant_from_kernel,
            kernel_finding(disposition="accepted"),
        )

    def test_a_tampered_content_hash_is_refused(self) -> None:
        value = kernel_finding()
        value["content_hash"] = phase3b_sha256(b"not the finding")
        self.assertRefused(
            "formal_finding_invalid", self.fixture.grant_from_kernel, value
        )

    def test_a_finding_that_is_not_exact_statement_only_is_refused(self) -> None:
        self.assertRefused(
            "formal_check_not_exact_statement_only",
            self.fixture.grant_from_kernel,
            kernel_finding(exact_statement_only=False),
        )

    def test_a_finding_about_another_claim_is_refused(self) -> None:
        self.assertRefused(
            "formal_finding_claim_mismatch",
            self.fixture.grant_from_kernel,
            kernel_finding(claim_id="claim.other.target"),
        )

    def test_a_finding_without_an_alignment_reference_is_refused(self) -> None:
        self.assertRefused(
            "formal_finding_has_no_semantic_alignment",
            self.fixture.grant_from_kernel,
            kernel_finding(semantic_alignment_id=None),
        )

    def test_a_finding_naming_another_alignment_is_refused(self) -> None:
        self.assertRefused(
            "formal_finding_alignment_mismatch",
            self.fixture.grant_from_kernel,
            kernel_finding(semantic_alignment_id="alignment.elsewhere.v1"),
        )

    def test_a_kernel_basis_cannot_license_another_warrant_kind(self) -> None:
        self.assertRefused(
            "warrant_kind_not_supported_by_kernel_basis",
            self.fixture.grant_from_kernel,
            kind=WarrantKind.RIGOROUS_DERIVATION,
        )

    def test_unreadable_and_oversized_documents_are_refused(self) -> None:
        with self.assertRaises(ReviewRefused) as caught:
            build_kernel_warrant(
                runs=self.fixture.workspace,
                journal_decisions=self.fixture.journal.decisions(),
                run_id=RUN_ID,
                finding_bytes=b"{not json",
                kind=WarrantKind.FORMAL_PROOF,
                scope="x",
                grantor=ALICE,
            )
        self.assertEqual(("formal_finding_unreadable",), caught.exception.codes)
        with self.assertRaises(ReviewRefused) as caught:
            build_kernel_warrant(
                runs=self.fixture.workspace,
                journal_decisions=self.fixture.journal.decisions(),
                run_id=RUN_ID,
                finding_bytes=b"0" * 300_000,
                kind=WarrantKind.FORMAL_PROOF,
                scope="x",
                grantor=ALICE,
            )
        self.assertEqual(("formal_finding_too_large",), caught.exception.codes)

    def test_a_finding_operational_instant_does_not_move_semantic_identity(self) -> None:
        first = self.fixture.grant_from_kernel()
        moved = kernel_finding(created_at="2027-01-01T00:00:00Z")
        second = self.fixture.grant_from_kernel(moved, recorded_at=DISCHARGE_AT)
        self.assertEqual(first["decision_id"], second["decision_id"])
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual(
            "2026-08-21T12:20:00Z",
            first["payload"]["operational"]["formal_finding_created_at"],
        )


class KernelAlignmentGateTests(ReviewTestCase):
    def test_a_kernel_check_without_an_approved_alignment_is_refused(self) -> None:
        error = self.assertRefused(
            "semantic_alignment_not_approved", self.fixture.grant_from_kernel
        )
        self.assertIn("meaning link", error.refusals[0].detail)

    def test_a_source_origin_premise_is_refused_while_applicability_is_unapproved(self) -> None:
        """`source_applicability_approved` is false on every Phase 3B finding.

        That is only harmless while no premise of the target came from a source,
        so the flag is honoured as a gate against the dossier rather than ignored.
        """

        dossier = intake_dossier()
        claims = tuple(
            replace(item, origin=ClaimOrigin.SOURCE)
            if item.kind == "definition" and item.id.value.endswith("odd_definition")
            else item
            for item in dossier.claims
        )
        sourced = replace(
            dossier, id=oid(f"{dossier.id.value}.sourced"), claims=claims
        )
        with tempfile.TemporaryDirectory() as temporary:
            journal = ReviewJournal(Path(temporary))
            self.addCleanup(journal.close)
            run_id = OpaqueId("run.sourced.v1")
            journal.durable.create_run(
                run_id=run_id, dossier=sourced, budget_id=OpaqueId("budget.sourced"),
                limits=BudgetLimits(
                    max_input_tokens=1, max_output_tokens=1, max_cost_microusd=1,
                    max_wall_milliseconds=1, max_attempts=1,
                ),
                now="2026-08-21T00:00:00.000000Z",
            )
            proposal = build_alignment_decision(
                runs=journal.durable, run_id=run_id, alignment_id=ALIGNMENT_ID,
                approver=ALICE, decision=AlignmentDecision.APPROVE,
                rationale="approved for this test",
            )
            journal.append_once(proposal, recorded_at=ALIGNMENT_AT)
            with self.assertRaises(ReviewRefused) as caught:
                build_kernel_warrant(
                    runs=journal.durable,
                    journal_decisions=journal.decisions(),
                    run_id=run_id,
                    finding_bytes=json.dumps(kernel_finding()).encode("utf-8"),
                    kind=WarrantKind.FORMAL_PROOF,
                    scope="x",
                    grantor=ALICE,
                )
            self.assertEqual(("source_applicability_not_approved",), caught.exception.codes)


# ---------------------------------------------------------------------------
# Refusals: obligation discharge.
# ---------------------------------------------------------------------------

class DischargeRefusalTests(ReviewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fixture.record_verdict()
        self.fixture.approve_alignment()
        self.warrant_id = str(self.fixture.grant()["payload"]["warrant_id"])

    def _variant_run(
        self, suffix: str, *, obligations: tuple, approver: ReviewerIdentity
    ) -> tuple[OpaqueId, str]:
        """Register a variant dossier as its own run and kernel-grant a warrant.

        The kernel basis is used because it needs no verdict, which keeps these
        refusal tests about discharge rather than about review.
        """

        dossier = intake_dossier()
        variant = replace(
            dossier, id=oid(f"{dossier.id.value}.{suffix}"), obligations=obligations
        )
        run_id = OpaqueId(f"run.{suffix}.v1")
        self.fixture.workspace.create_run(
            run_id=run_id,
            dossier=variant,
            budget_id=OpaqueId(f"budget.{suffix}"),
            limits=BudgetLimits(
                max_input_tokens=1, max_output_tokens=1, max_cost_microusd=1,
                max_wall_milliseconds=1, max_attempts=1,
            ),
            now="2026-08-21T00:00:00.000000Z",
        )
        alignment = build_alignment_decision(
            runs=self.fixture.workspace,
            run_id=run_id,
            alignment_id=ALIGNMENT_ID,
            approver=approver,
            decision=AlignmentDecision.APPROVE,
            rationale="approved for the variant dossier",
        )
        self.fixture.journal.append_once(alignment, recorded_at=ALIGNMENT_AT)
        kernel = build_kernel_warrant(
            runs=self.fixture.workspace,
            journal_decisions=self.fixture.journal.decisions(),
            run_id=run_id,
            finding_bytes=json.dumps(kernel_finding()).encode("utf-8"),
            kind=WarrantKind.FORMAL_PROOF,
            scope="kernel checked",
            grantor=approver,
        )
        granted, appended = self.fixture.journal.append_once(kernel, recorded_at=GRANT_AT)
        self.assertTrue(appended)
        return run_id, str(granted["payload"]["warrant_id"])

    def test_an_unknown_warrant_is_refused(self) -> None:
        error = self.assertRefused(
            "warrant_not_found",
            self.fixture.discharge,
            WARRANT_OBLIGATION,
            "warrant.invented.by.nobody",
        )
        self.assertIn(self.warrant_id, error.refusals[0].detail)

    def test_a_warrant_granted_against_another_dossier_is_not_visible(self) -> None:
        run_id, _ = self._variant_run(
            "otherdossier",
            obligations=intake_dossier().obligations,
            approver=ReviewerIdentity(
                id=oid("reviewer.dana"), kind=ReviewerKind.HUMAN,
                attestation="approved the variant",
            ),
        )
        with self.assertRaises(ReviewRefused) as caught:
            build_obligation_discharge(
                runs=self.fixture.workspace,
                journal_decisions=self.fixture.journal.decisions(),
                run_id=run_id,
                obligation_id=WARRANT_OBLIGATION,
                warrant_id=self.warrant_id,
                reviewer=ALICE,
                rationale="x",
            )
        self.assertEqual(("warrant_not_found",), caught.exception.codes)

    def test_a_warrant_over_another_claim_is_refused(self) -> None:
        base = intake_dossier()
        other = replace(
            base.obligations[1],
            id=oid(f"obligation.{SLUG}.definition_gap"),
            claim_id=oid(f"claim.{SLUG}.odd_definition"),
        )
        run_id, warrant_id = self._variant_run(
            "otherclaim",
            obligations=(*base.obligations, other),
            approver=ReviewerIdentity(
                id=oid("reviewer.erin"), kind=ReviewerKind.HUMAN,
                attestation="approved the variant",
            ),
        )
        with self.assertRaises(ReviewRefused) as caught:
            build_obligation_discharge(
                runs=self.fixture.workspace,
                journal_decisions=self.fixture.journal.decisions(),
                run_id=run_id,
                obligation_id=other.id,
                warrant_id=warrant_id,
                reviewer=ALICE,
                rationale="x",
            )
        self.assertEqual(
            ("warrant_does_not_cover_obligation_claim",), caught.exception.codes
        )

    def test_a_literature_applicability_obligation_is_refused(self) -> None:
        base = intake_dossier()
        obligations = tuple(
            replace(item, category="literature_applicability")
            if item.id == WARRANT_OBLIGATION
            else item
            for item in base.obligations
        )
        run_id, warrant_id = self._variant_run(
            "literature",
            obligations=obligations,
            approver=ReviewerIdentity(
                id=oid("reviewer.frank"), kind=ReviewerKind.HUMAN,
                attestation="approved the variant",
            ),
        )
        with self.assertRaises(ReviewRefused) as caught:
            build_obligation_discharge(
                runs=self.fixture.workspace,
                journal_decisions=self.fixture.journal.decisions(),
                run_id=run_id,
                obligation_id=WARRANT_OBLIGATION,
                warrant_id=warrant_id,
                reviewer=ALICE,
                rationale="x",
            )
        self.assertEqual(
            ("obligation_category_requires_applicability_record",), caught.exception.codes
        )

    def test_an_unknown_obligation_is_refused(self) -> None:
        self.assertRefused(
            "obligation_not_found",
            self.fixture.discharge,
            OpaqueId("obligation.absent"),
            self.warrant_id,
        )

    def test_a_model_reviewer_cannot_discharge(self) -> None:
        self.assertRefused(
            "reviewer_identity_not_human",
            self.fixture.discharge,
            WARRANT_OBLIGATION,
            self.warrant_id,
            reviewer=BOT,
        )

    def test_discharging_twice_replays_without_change(self) -> None:
        first = self.fixture.discharge(WARRANT_OBLIGATION, self.warrant_id)
        proposal = build_obligation_discharge(
            runs=self.fixture.workspace,
            journal_decisions=self.fixture.journal.decisions(),
            run_id=RUN_ID,
            obligation_id=WARRANT_OBLIGATION,
            warrant_id=self.warrant_id,
            reviewer=ALICE,
            rationale="the granted warrant covers the obligation's claim",
        )
        second, appended = self.fixture.journal.append_once(
            proposal, recorded_at="2026-08-21T18:00:00.000000Z"
        )
        self.assertFalse(appended)
        self.assertEqual(first["decision_id"], second["decision_id"])
        self.assertEqual(first["recorded_at"], second["recorded_at"])

    def test_an_already_discharged_obligation_cannot_be_discharged_again(self) -> None:
        self.fixture.discharge(WARRANT_OBLIGATION, self.warrant_id)
        self.fixture.discharge(ALIGNMENT_OBLIGATION, self.warrant_id)
        projection = self.fixture.project()
        successor = projection.successor

        class SuccessorRuns:
            """A reader that serves the successor dossier for the same run."""

            def __init__(self, inner, dossier) -> None:
                self.inner = inner
                self.dossier = dossier

            def get_run(self, run_id):
                run = self.inner.get_run(run_id)
                return replace(
                    run,
                    dossier_id=self.dossier.id,
                    dossier_hash=export_dossier_dict(self.dossier)["content_hash"],
                )

            def load_dossier(self, dossier_id):
                return self.dossier

            def list_proposals(self, run_id):
                return self.inner.list_proposals(run_id)

        with self.assertRaises(ReviewRefused) as caught:
            build_obligation_discharge(
                runs=SuccessorRuns(self.fixture.workspace, successor),
                journal_decisions=self.fixture.journal.decisions(),
                run_id=RUN_ID,
                obligation_id=WARRANT_OBLIGATION,
                warrant_id=self.warrant_id,
                reviewer=ALICE,
                rationale="x",
            )
        self.assertEqual(("obligation_not_open",), caught.exception.codes)

    def test_the_semantic_alignment_gate_is_enforced_independently(self) -> None:
        """A warrant grant is not by itself licence to close a meaning obligation.

        Every grant path already requires an approved alignment, so this gate is
        defence in depth. It is exercised directly with a journal that holds a
        warrant grant and no alignment approval, which is a state the CLI cannot
        reach and must still be refused.
        """

        decisions = [
            item
            for item in self.fixture.journal.decisions()
            if item["decision_kind"] != "semantic_alignment_decision"
        ]
        self.assertTrue(any(item["decision_kind"] == "warrant_grant" for item in decisions))
        with self.assertRaises(ReviewRefused) as caught:
            build_obligation_discharge(
                runs=self.fixture.workspace,
                journal_decisions=tuple(decisions),
                run_id=RUN_ID,
                obligation_id=ALIGNMENT_OBLIGATION,
                warrant_id=self.warrant_id,
                reviewer=ALICE,
                rationale="x",
            )
        self.assertEqual(("semantic_alignment_not_approved",), caught.exception.codes)


class JournalAppendOnlyTests(ReviewTestCase):
    def test_replaying_a_decision_is_a_no_op(self) -> None:
        first = self.fixture.record_verdict()
        proposal, _ = build_review_verdict(
            runs=self.fixture.workspace,
            artifacts=self.fixture.artifacts,
            run_id=RUN_ID,
            reviewer=ALICE,
            verdict=ReviewVerdict.ACCEPT_CANDIDATE,
            independently_checked=True,
            rationale="the algebra covers every pair of odd integers",
        )
        second, appended = self.fixture.journal.append_once(
            proposal, recorded_at="2027-01-01T00:00:00.000000Z"
        )
        self.assertFalse(appended)
        self.assertEqual(first, second)
        self.assertEqual(1, len(self.fixture.journal.decisions()))

    def test_reusing_a_key_for_different_content_is_refused(self) -> None:
        self.fixture.record_verdict()
        error = self.assertRefused(
            "idempotency_key_conflict",
            self.fixture.record_verdict,
            verdict=ReviewVerdict.REJECT_CANDIDATE,
            independently_checked=False,
        )
        self.assertIn("append-only", error.refusals[0].detail)
        self.assertEqual(1, len(self.fixture.journal.decisions()))
        self.assertEqual(
            "accept_candidate", self.fixture.journal.decisions()[0]["payload"]["verdict"]
        )

    def test_a_second_reviewer_records_an_independent_verdict(self) -> None:
        self.fixture.record_verdict()
        bob = ReviewerIdentity(
            id=oid("reviewer.bob"),
            kind=ReviewerKind.HUMAN,
            attestation="independently checked the same derivation",
        )
        self.fixture.record_verdict(
            reviewer=bob, verdict=ReviewVerdict.REJECT_CANDIDATE,
            independently_checked=False, recorded_at="2026-08-21T12:30:00.000000Z",
        )
        self.assertEqual(2, len(self.fixture.journal.decisions()))
        self.fixture.approve_alignment()
        record = self.fixture.grant()
        self.assertEqual(
            ["reviewer.alice"],
            sorted(
                {
                    self.fixture.journal.decision(item)["reviewer"]["id"]
                    for item in record["payload"]["supporting_decision_ids"]
                }
            ),
        )

    def test_a_rejecting_verdict_is_preserved_as_rejected_evidence(self) -> None:
        self.fixture.record_verdict(
            verdict=ReviewVerdict.REJECT_CANDIDATE, independently_checked=False
        )
        projection = self.fixture.project()
        self.assertEqual(1, len(projection.successor.evidence))
        self.assertIs(Disposition.REJECTED, projection.successor.evidence[0].disposition)
        self.assertIs(
            VerificationOutcome.FAIL, projection.successor.verification_records[0].outcome
        )
        self.assertEqual((), projection.successor.warrants)
        self.assertEqual(
            "unknown", TrustPolicy(projection.successor).target_resolution().logical_status
        )

    def test_refusals_are_retained_in_the_journal(self) -> None:
        with self.assertRaises(ReviewRefused) as caught:
            self.fixture.record_verdict(independently_checked=False)
        stored = self.fixture.journal.record_refusal(
            caught.exception.refusals[0], recorded_at=VERDICT_AT
        )
        again = self.fixture.journal.record_refusal(
            caught.exception.refusals[0], recorded_at="2027-01-01T00:00:00.000000Z"
        )
        self.assertEqual(stored, again)
        self.assertEqual(1, len(self.fixture.journal.refusals()))
        self.assertEqual(
            "independent_check_not_attested", self.fixture.journal.refusals()[0]["code"]
        )

    def test_the_journal_semantic_hash_ignores_recorded_instants(self) -> None:
        self.fixture.happy_path()
        first = self.fixture.journal.export()
        other = ReviewFixture()
        self.addCleanup(other.close)
        other.drive_to_review()
        other.record_verdict(recorded_at="2027-03-03T03:03:03.000000Z")
        other.approve_alignment(recorded_at="2027-03-03T04:03:03.000000Z")
        warrant_id = str(other.grant(recorded_at="2027-03-03T05:03:03.000000Z")["payload"]["warrant_id"])
        other.discharge(WARRANT_OBLIGATION, warrant_id, recorded_at="2027-03-03T06:03:03.000000Z")
        other.discharge(ALIGNMENT_OBLIGATION, warrant_id, recorded_at="2027-03-03T07:03:03.000000Z")
        second = other.journal.export()
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertNotEqual(first["operational_hash"], second["operational_hash"])

    def test_every_stored_record_rehashes_to_its_recorded_semantic_hash(self) -> None:
        self.fixture.happy_path()
        for record in self.fixture.journal.decisions():
            self.assertEqual(record["content_hash"], semantic_record_hash(record))


# ---------------------------------------------------------------------------
# Successor dossier determinism and round-trip.
# ---------------------------------------------------------------------------

class SuccessorDossierTests(ReviewTestCase):
    def test_the_successor_round_trips_byte_identically(self) -> None:
        self.fixture.happy_path()
        projection = self.fixture.project()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "successor.json"
            written = write_dossier(projection.successor, path)
            self.assertEqual(projection.successor_hash, written)
            replayed = import_trusted_replay(path.read_bytes())
            self.assertEqual(projection.successor, replayed)
            self.assertEqual(written, export_dossier_dict(replayed)["content_hash"])
            self.assertEqual(
                export_dossier_bytes(projection.successor), export_dossier_bytes(replayed)
            )

    def test_projection_is_deterministic_across_journals(self) -> None:
        self.fixture.happy_path()
        first = self.fixture.project()
        other = ReviewFixture()
        self.addCleanup(other.close)
        other.drive_to_review()
        other.happy_path()
        second = other.project()
        self.assertEqual(first.successor_hash, second.successor_hash)
        self.assertEqual(first.successor.id, second.successor.id)
        self.assertEqual(
            export_dossier_bytes(first.successor), export_dossier_bytes(second.successor)
        )

    def test_the_successor_is_admissible_to_an_append_only_store(self) -> None:
        self.fixture.happy_path()
        projection = self.fixture.project()
        store = InMemoryTrustStore()
        admitted = store.append_dossier(projection.successor)
        self.assertEqual(projection.successor, admitted)
        self.assertEqual(admitted, store.append_dossier(projection.successor))

    def test_projecting_an_empty_journal_is_refused(self) -> None:
        with self.assertRaises(ReviewRefused) as caught:
            self.fixture.project()
        self.assertEqual(("journal_empty",), caught.exception.codes)

    def test_a_projector_who_took_no_decision_is_refused(self) -> None:
        self.fixture.happy_path()
        with self.assertRaises(ReviewRefused) as caught:
            self.fixture.project(projected_by=oid("operator.carol"))
        self.assertEqual(("projector_not_a_journal_reviewer",), caught.exception.codes)

    def test_a_decision_taken_against_another_dossier_hash_is_refused(self) -> None:
        self.fixture.record_verdict()
        tampered = copy.deepcopy(dict(self.fixture.journal.export()))
        tampered["decisions"][0]["payload"]["dossier_hash"] = "sha256:" + "0" * 64
        with self.assertRaises(ReviewRefused) as caught:
            build_successor(
                runs=self.fixture.workspace,
                run_id=RUN_ID,
                journal_export=tampered,
                projected_at=PROJECT_AT,
                projected_by=ALICE.id,
            )
        self.assertEqual(("decision_dossier_hash_mismatch",), caught.exception.codes)

    def test_the_projection_instant_changes_only_the_successor_identity(self) -> None:
        self.fixture.happy_path()
        first = self.fixture.project()
        second = self.fixture.project(at=parse_instant("2026-08-22T13:00:00Z"))
        self.assertNotEqual(first.successor_hash, second.successor_hash)
        self.assertEqual(
            TrustPolicy(first.successor).target_resolution().logical_status,
            TrustPolicy(second.successor).target_resolution().logical_status,
        )


# ---------------------------------------------------------------------------
# Determinism and offline properties of the modules themselves.
# ---------------------------------------------------------------------------

class ModuleDisciplineTests(unittest.TestCase):
    PATHS = (
        REPO_ROOT / "src" / "math_research" / "review" / "decisions.py",
        REPO_ROOT / "src" / "math_research" / "review" / "projection.py",
        REPO_ROOT / "src" / "math_research" / "review" / "journal.py",
        REPO_ROOT / "src" / "math_research" / "review" / "records.py",
        REPO_ROOT / "src" / "math_research" / "review" / "serialization.py",
        REPO_ROOT / "src" / "math_research" / "review_cli.py",
    )

    def test_no_module_reads_a_clock_or_a_random_source(self) -> None:
        forbidden_modules = {"random", "secrets", "time"}
        forbidden_attributes = {"now", "utcnow", "today", "monotonic"}
        for path in self.PATHS:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(
                            alias.name.split(".")[0], forbidden_modules, f"{path.name}"
                        )
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(
                        node.module.split(".")[0], forbidden_modules, f"{path.name}"
                    )
                if isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, forbidden_attributes, f"{path.name}")

    def test_no_module_uses_floating_point(self) -> None:
        for path in self.PATHS:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant):
                    self.assertNotIsInstance(node.value, float, f"{path.name}")

    def test_the_journal_is_the_only_module_that_writes(self) -> None:
        """Only `journal.py` executes SQL, so no other module can mutate state."""

        for path in self.PATHS:
            if path.name == "journal.py":
                continue
            text = path.read_text(encoding="utf-8")
            for statement in ("INSERT ", "UPDATE ", "DELETE ", "execute("):
                self.assertNotIn(statement, text, f"{path.name} contains {statement!r}")

    def test_the_review_modules_do_not_write_to_phase2_or_phase3b(self) -> None:
        writers = {"save_dossier", "create_run", "set_run_status", "commit_proposal",
                   "save_attempt", "append_event"}
        for path in self.PATHS:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in writers:
                    self.fail(f"{path.name} calls {node.attr} on an upstream phase")


# ---------------------------------------------------------------------------
# CLI surface.
# ---------------------------------------------------------------------------

class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        # Drive the run inside the same workspace the CLI will open.
        self.workspace = self.root / "workspace"
        journal = ReviewJournal(self.workspace)
        artifacts = FileArtifactStore(self.workspace / "artifacts")
        dossier = intake_dossier()
        proposer, verifier = deterministic_fake_results(
            dossier.formalization.target_claim_id.value,
            dossier.formalization.assumption_claim_ids[0].value,
        )
        gateway = ScriptedModelGateway({"proposer": [proposer], "verifier": [verifier]})
        loop = BaselineResearchLoop(
            workspace=journal.durable, artifacts=artifacts, proposer=gateway, verifier=gateway,
            independence=VerifierIndependence(
                context_isolated=True, separate_model_call=True, different_model=False,
                different_provider=False, deterministic_checker=False,
                independently_implemented_checker=False, formal_kernel=False,
            ),
            now=lambda: LOOP_INSTANT,
        )
        loop.start(
            run_id=RUN_ID, dossier=dossier,
            limits=BudgetLimits(
                max_input_tokens=20_000, max_output_tokens=4_000, max_cost_microusd=1_000,
                max_wall_milliseconds=120_000, max_attempts=4,
            ),
        )
        loop.run_to_terminal(RUN_ID)
        journal.close()

    def _run(self, *argv: str) -> int:
        self.stdout = io.StringIO()
        with redirect_stdout(self.stdout):
            return review_cli.main(list(argv))

    def _last_json(self) -> dict:
        return json.loads(self.stdout.getvalue())

    def test_the_cli_walks_the_happy_path_and_refuses_a_model_reviewer(self) -> None:
        self.assertEqual(
            2,
            self._run(
                "record-verdict", str(self.workspace), RUN_ID.value, "2026-08-21T12:00:00Z",
                "--reviewer", "verifier.model.gpt", "--reviewer-kind", "model",
                "--attestation", "the model likes it", "--verdict", "accept_candidate",
                "--rationale", "because I said so", "--independently-checked",
            ),
        )
        self.assertEqual(
            0,
            self._run(
                "record-verdict", str(self.workspace), RUN_ID.value, "2026-08-21T12:00:00Z",
                "--reviewer", "reviewer.alice", "--reviewer-kind", "human",
                "--attestation", "re-derived by hand", "--verdict", "accept_candidate",
                "--rationale", "the algebra holds", "--independently-checked",
            ),
        )
        self.assertEqual(
            0,
            self._run(
                "decide-alignment", str(self.workspace), RUN_ID.value, ALIGNMENT_ID.value,
                "2026-08-21T12:05:00Z", "--reviewer", "reviewer.alice",
                "--reviewer-kind", "human", "--attestation", "compared term by term",
                "--decision", "approve", "--rationale", "definitions match",
            ),
        )
        self.assertEqual(
            2,
            self._run(
                "grant-warrant", str(self.workspace), RUN_ID.value, TARGET_CLAIM.value,
                "2026-08-21T12:10:00Z", "--reviewer", "reviewer.alice",
                "--reviewer-kind", "human", "--attestation", "re-derived by hand",
                "--kind", "formal_proof", "--scope", "all odd pairs",
            ),
        )
        self.assertEqual(
            0,
            self._run(
                "grant-warrant", str(self.workspace), RUN_ID.value, TARGET_CLAIM.value,
                "2026-08-21T12:10:00Z", "--reviewer", "reviewer.alice",
                "--reviewer-kind", "human", "--attestation", "re-derived by hand",
                "--kind", "rigorous_derivation", "--scope", "all odd pairs",
            ),
        )
        journal = ReviewJournal(self.workspace)
        grants = journal.decisions(decision_kind="warrant_grant")
        self.assertEqual(1, len(grants))
        warrant_id = str(grants[0]["payload"]["warrant_id"])
        refusal_codes = {item["code"] for item in journal.refusals()}
        self.assertEqual(
            {"reviewer_identity_not_human", "formal_proof_requires_kernel_attestation"},
            refusal_codes,
        )
        journal.close()
        for obligation in (WARRANT_OBLIGATION, ALIGNMENT_OBLIGATION):
            self.assertEqual(
                0,
                self._run(
                    "discharge-obligation", str(self.workspace), RUN_ID.value,
                    obligation.value, "2026-08-21T12:15:00Z",
                    "--reviewer", "reviewer.alice", "--reviewer-kind", "human",
                    "--attestation", "checked coverage", "--warrant-id", warrant_id,
                    "--rationale", "warrant covers the claim",
                ),
            )
        output = self.root / "successor.json"
        self.assertEqual(
            0,
            self._run(
                "project", str(self.workspace), RUN_ID.value, "2026-08-21T13:00:00Z",
                str(output), "--projected-by", "reviewer.alice",
            ),
        )
        self.assertEqual(0, self._run("inspect", str(output)))
        successor = import_trusted_replay(output.read_bytes())
        measured = TrustPolicy(successor).target_resolution()
        self.assertEqual("proved", measured.logical_status)
        self.assertEqual(("rigorous_derivation",), measured.warrant_kinds)

    def test_the_journal_command_prints_a_canonical_export(self) -> None:
        self.assertEqual(0, self._run("journal", str(self.workspace)))
        output = self.root / "journal.json"
        self.assertEqual(
            0, self._run("journal", str(self.workspace), "--output", str(output))
        )
        value = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual("review_decision_journal", value["record_type"])
        self.assertEqual([], value["decisions"])

    def test_a_refusal_prints_structured_output_naming_the_precondition(self) -> None:
        self.assertEqual(
            2,
            self._run(
                "record-verdict", str(self.workspace), RUN_ID.value, "2026-08-21T12:00:00Z",
                "--reviewer", "reviewer.alice", "--reviewer-kind", "human",
                "--attestation", "skimmed it", "--verdict", "accept_candidate",
                "--rationale", "the model said so",
            ),
        )
        value = self._last_json()
        self.assertFalse(value["accepted"])
        self.assertEqual(1, len(value["refusals"]))
        refusal = value["refusals"][0]
        self.assertEqual("independent_check_not_attested", refusal["code"])
        self.assertIn("independent-check attestation", refusal["unmet_precondition"])
        self.assertIn("manual_review", refusal["detail"])
        self.assertEqual(1, len(value["refusal_record_ids"]))

    def test_an_instant_without_a_utc_marker_is_refused(self) -> None:
        self.assertEqual(
            2,
            self._run(
                "record-verdict", str(self.workspace), RUN_ID.value, "2026-08-21 12:00:00",
                "--reviewer", "reviewer.alice", "--reviewer-kind", "human",
                "--attestation", "x", "--verdict", "inconclusive", "--rationale", "y",
            ),
        )


class Phase3bFixtureIntegrityTests(unittest.TestCase):
    def test_the_committed_kernel_fixture_satisfies_the_phase3b_contract(self) -> None:
        value = json.loads(KERNEL_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(PHASE3B_SCHEMA_VERSION, value["schema_version"])
        self.assertEqual(PHASE3B_HASH_PROFILE, value["hash_profile"])
        self.assertEqual("proposal", value["disposition"])
        self.assertEqual("none", value["trust_effect"])
        self.assertEqual(value["content_hash"], finding_content_hash(value))
        for flag in (
            "epistemic_warrant_created", "semantic_alignment_approved",
            "source_applicability_approved", "novelty_approved",
            "significance_approved", "contribution_approved",
        ):
            self.assertIs(False, value[flag])
        self.assertEqual(
            value["wrapper_manifest"]["target_hash"],
            phase3b_canonical_hash("forall a b : Int, Odd a -> Odd b -> Even (a + b)"),
        )


if __name__ == "__main__":
    unittest.main()
