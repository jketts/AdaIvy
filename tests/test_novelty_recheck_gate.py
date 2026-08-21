"""Acceptance tests for ADR-0055's two mandatory novelty checkpoints."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from math_research.application.problem_intake import load_problem_definition_file, parse_instant
from math_research.interchange import export_dossier_dict
from math_research.novelty import (
    NoveltyRecheck,
    NoveltyRecheckError,
    load_recheck,
    require_announcement_chain,
    require_checkpoint,
    write_recheck,
)
from math_research.phase2.sqlite_workspace import SQLiteWorkspace
from math_research.phase2_cli import main as phase2_main
from math_research.publication import PublicationValidationError, load_manuscript
from math_research.publication.manuscript import _announcement_subject_hash


ROOT = Path(__file__).resolve().parent.parent
PROBLEM = ROOT / "fixtures/problem-intake/graph-cycle-edge-bound-v1.json"
MANUSCRIPT = ROOT / "fixtures/publication/manuscript-v1.json"
GRAFFITI_197 = ROOT / "fixtures/novelty/graffiti-197-prior-resolution-v1.json"
INSTANT = "2026-08-21T00:00:00Z"


def recheck(
    *, checkpoint: str, subject_id: str, subject_hash: str, action_id: str,
    recheck_id: str, performed_at: str, previous: NoveltyRecheck | None = None,
    outcome: str = "inconclusive", relationship: str = "unresolved",
    prior_resolution: str = "unresolved", verification_status: str = "unresolved",
) -> NoveltyRecheck:
    return NoveltyRecheck(
        recheck_id=recheck_id, checkpoint=checkpoint, subject_id=subject_id,
        subject_hash=subject_hash, next_action_id=action_id,
        performed_by="reviewer.novelty", performed_at=performed_at,
        protocol_id="protocol.novelty.search.v1",
        query_terms=("renamed formulation", "equivalent theorem"),
        searched_sources=("Crossref metadata", "local acquired corpus"),
        equivalence_checks=("notation variants", "equivalent formulations"),
        evidence_refs=(("search.evidence.v1", "sha256:" + "a" * 64),),
        outcome=outcome, prior_art_relationship=relationship,
        prior_resolution=prior_resolution,
        prior_resolution_verification=verification_status,
        limitations=("Bounded sources cannot establish absence of prior art.",),
        previous_recheck_id=previous.recheck_id if previous else None,
        previous_recheck_hash=previous.content_hash if previous else None,
    ).finalized()


class RecordTests(unittest.TestCase):
    def test_round_trip_is_canonical(self) -> None:
        record = recheck(
            checkpoint="before_research", subject_id="problem.example",
            subject_hash="sha256:" + "1" * 64, action_id="run.example",
            recheck_id="recheck.example.start", performed_at="2026-08-21T00:00:00Z",
        )
        self.assertEqual(record, load_recheck(record.payload()))

    def test_automated_authority_and_warrant_are_impossible(self) -> None:
        record = recheck(
            checkpoint="before_research", subject_id="problem.example",
            subject_hash="sha256:" + "1" * 64, action_id="run.example",
            recheck_id="recheck.example.start", performed_at="2026-08-21T00:00:00Z",
        )
        for field in ("automatic_novelty_authority", "creates_mathematical_warrant"):
            payload = record.payload()
            payload[field] = True
            payload["content_hash"] = record.content_hash
            with self.assertRaises(NoveltyRecheckError):
                load_recheck(payload)

    def test_stale_subject_and_reused_action_are_refused(self) -> None:
        record = recheck(
            checkpoint="before_research", subject_id="problem.example",
            subject_hash="sha256:" + "1" * 64, action_id="run.example",
            recheck_id="recheck.example.start", performed_at="2026-08-21T00:00:00Z",
        )
        with self.assertRaisesRegex(NoveltyRecheckError, "stale_subject_binding"):
            require_checkpoint(
                record, checkpoint="before_research", subject_id="problem.example",
                subject_hash="sha256:" + "2" * 64, next_action_id="run.example",
            )
        with self.assertRaisesRegex(NoveltyRecheckError, "different_action"):
            require_checkpoint(
                record, checkpoint="before_research", subject_id="problem.example",
                subject_hash=record.subject_hash, next_action_id="run.other",
            )

    def test_graffiti_197_is_classified_as_an_independent_verification_of_an_already_refuted_target(self) -> None:
        fixture = json.loads(GRAFFITI_197.read_text(encoding="utf-8"))
        record = NoveltyRecheck(
            recheck_id="recheck.graffiti-197.start", checkpoint="before_research",
            subject_id=fixture["subject_id"], subject_hash=fixture["subject_hash"],
            next_action_id=fixture["next_action_id"], performed_by=fixture["performed_by"],
            performed_at=fixture["performed_at"], protocol_id=fixture["protocol_id"],
            query_terms=tuple(fixture["query_terms"]),
            searched_sources=tuple(fixture["searched_sources"]),
            equivalence_checks=tuple(fixture["equivalence_checks"]),
            evidence_refs=tuple(
                (item["ref_id"], item["content_hash"]) for item in fixture["evidence_refs"]
            ),
            outcome=fixture["outcome"],
            prior_art_relationship=fixture["prior_art_relationship"],
            prior_resolution=fixture["prior_resolution"],
            prior_resolution_verification=fixture["prior_resolution_verification"],
            limitations=tuple(fixture["limitations"]),
        ).finalized()
        self.assertEqual(fixture["expected"], {
            "report_classification": record.classification().report_classification,
            "target_resolution_status": record.classification().target_resolution_status,
            "novelty_status": record.classification().payload()["novelty_status"],
        })
        self.assertEqual(record, load_recheck(record.payload()))

    def test_a_source_report_is_not_silently_upgraded_to_already_refuted(self) -> None:
        record = recheck(
            checkpoint="before_research", subject_id="problem.example",
            subject_hash="sha256:" + "1" * 64, action_id="run.example",
            recheck_id="recheck.example.prior", performed_at="2026-08-21T00:00:00Z",
            outcome="prior_art_found", relationship="same_result",
            prior_resolution="refutation", verification_status="source_report_only",
        )
        self.assertEqual("reported_prior_resolution", record.classification().report_classification)
        self.assertEqual("reported_refuted", record.classification().target_resolution_status)

    def test_verified_matching_prior_results_distinguish_proof_refutation_and_other(self) -> None:
        expected = {
            "proof": "already_proved",
            "refutation": "already_refuted",
            "other_resolution": "already_resolved_other",
        }
        for resolution, status in expected.items():
            with self.subTest(resolution=resolution):
                record = recheck(
                    checkpoint="before_research", subject_id="problem.example",
                    subject_hash="sha256:" + "1" * 64, action_id="run.example",
                    recheck_id=f"recheck.example.{resolution.replace('_', '-')}",
                    performed_at="2026-08-21T00:00:00Z",
                    outcome="prior_art_found", relationship="equivalent_result",
                    prior_resolution=resolution,
                    verification_status="independently_verified",
                )
                self.assertEqual("independent_verification", record.classification().report_classification)
                self.assertEqual(status, record.classification().target_resolution_status)

    def test_prior_art_found_requires_a_coherent_result_relationship(self) -> None:
        with self.assertRaisesRegex(NoveltyRecheckError, "prior_art_classification_inconsistent"):
            recheck(
                checkpoint="before_research", subject_id="problem.example",
                subject_hash="sha256:" + "1" * 64, action_id="run.example",
                recheck_id="recheck.example.bad", performed_at="2026-08-21T00:00:00Z",
                outcome="prior_art_found", relationship="not_applicable",
                prior_resolution="not_applicable", verification_status="not_applicable",
            )

    def test_derived_report_classification_cannot_be_forged_even_with_a_rehash(self) -> None:
        record = recheck(
            checkpoint="before_research", subject_id="problem.example",
            subject_hash="sha256:" + "1" * 64, action_id="run.example",
            recheck_id="recheck.example.prior", performed_at="2026-08-21T00:00:00Z",
            outcome="prior_art_found", relationship="same_result",
            prior_resolution="refutation", verification_status="independently_verified",
        )
        payload = record.payload()
        payload["prior_art"]["report_classification"] = "extension_of_prior_result"
        payload["content_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(NoveltyRecheckError, "prior_art_derived_classification_mismatch"):
            load_recheck(payload)

    def test_recheck_must_be_within_the_freshness_window_and_before_action(self) -> None:
        record = recheck(
            checkpoint="before_research", subject_id="problem.example",
            subject_hash="sha256:" + "1" * 64, action_id="run.example",
            recheck_id="recheck.example.start", performed_at="2026-08-21T00:00:00Z",
        )
        common = {
            "checkpoint": "before_research", "subject_id": "problem.example",
            "subject_hash": record.subject_hash, "next_action_id": "run.example",
        }
        with self.assertRaisesRegex(NoveltyRecheckError, "too_old"):
            require_checkpoint(record, action_at="2026-08-22T00:00:01Z", **common)
        with self.assertRaisesRegex(NoveltyRecheckError, "not_before"):
            require_checkpoint(record, action_at="2026-08-21T00:00:00Z", **common)


class ResearchStartGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dossier = load_problem_definition_file(
            PROBLEM, instant=parse_instant(INSTANT)
        ).dossier

    def test_chosen_problem_cannot_start_without_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status = phase2_main([
                "start", temporary, "run.novelty.missing", "--problem", str(PROBLEM),
                "--intake-instant", INSTANT,
            ])
            self.assertEqual(2, status)

    def test_recheck_is_the_last_event_before_run_creation(self) -> None:
        run_id = "run.novelty.accepted"
        record = recheck(
            checkpoint="before_research", subject_id=self.dossier.problem.id.value,
            subject_hash=export_dossier_dict(self.dossier)["content_hash"],
            action_id=run_id, recheck_id="recheck.novelty.accepted.start",
            performed_at="2026-08-21T00:00:01Z",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "recheck.json"
            write_recheck(record, path)
            with mock.patch(
                "math_research.phase2_cli._now",
                return_value=datetime(2026, 8, 21, 0, 0, 2, tzinfo=timezone.utc),
            ):
                status = phase2_main([
                    "start", str(root / "workspace"), run_id, "--problem", str(PROBLEM),
                    "--intake-instant", INSTANT, "--novelty-recheck", str(path),
                ])
            self.assertEqual(0, status)
            with SQLiteWorkspace(root / "workspace/workspace.sqlite3") as workspace:
                timeline = workspace.timeline(self.dossier.problem.id)
                self.assertEqual((), timeline)
                run_timeline = workspace.timeline(type(self.dossier.problem.id)(run_id))
            self.assertEqual(
                ["novelty_recheck_recorded", "run_created"],
                [item["event_type"] for item in run_timeline[:2]],
            )
            self.assertEqual(record.content_hash, run_timeline[0]["payload"]["content_hash"])


class AnnouncementGateTests(unittest.TestCase):
    def approved(self, *, prior_resolution_found: bool = False) -> dict:
        value = json.loads(MANUSCRIPT.read_text(encoding="utf-8"))
        draft = load_manuscript(value)
        classification = (
            {
                "outcome": "prior_art_found", "relationship": "same_result",
                "prior_resolution": "refutation",
                "verification_status": "independently_verified",
            }
            if prior_resolution_found else
            {
                "outcome": "inconclusive", "relationship": "unresolved",
                "prior_resolution": "unresolved", "verification_status": "unresolved",
            }
        )
        start = recheck(
            checkpoint="before_research", subject_id="problem.publication",
            subject_hash="sha256:" + "3" * 64, action_id="run.publication",
            recheck_id="recheck.publication.start", performed_at="2026-08-21T00:00:00Z",
            **classification,
        )
        announcement = recheck(
            checkpoint="before_announcement", subject_id=draft.manuscript_id,
            subject_hash=_announcement_subject_hash(draft), action_id="approval.publication.v1",
            recheck_id="recheck.publication.announce", performed_at="2026-08-21T01:00:00Z",
            previous=start, **classification,
        )
        value["publication_approval"] = {
            "approval_id": "approval.publication.v1", "approver": "reviewer.publisher",
            "authority": "human_final", "recorded_at": "2026-08-21T01:00:01Z",
            "novelty_rechecks": [start.payload(), announcement.payload()],
        }
        return value

    def test_fresh_second_recheck_allows_approval(self) -> None:
        self.assertIsNotNone(load_manuscript(self.approved()).value["publication_approval"])

    def test_approved_report_surfaces_already_refuted_as_independent_verification(self) -> None:
        from math_research.publication import build_bundle, render_manuscript

        value = self.approved(prior_resolution_found=True)
        # This assertion exercises the prior-result projection itself.  The
        # fixture's unrelated mutation probes are already gated by the main
        # publication acceptance suite and depend on its unapproved baseline.
        value["render_probes"] = []
        manuscript = load_manuscript(value)
        document = render_manuscript(manuscript)
        self.assertIn(r"independent\_verification", document.tex)
        self.assertIn(r"already\_refuted", document.tex)
        prior_art = json.loads(build_bundle(manuscript).files["records/prior-art.json"])
        self.assertEqual("same_result", prior_art["relationship"])
        self.assertEqual("refutation", prior_art["resolution"])
        self.assertEqual("independently_verified", prior_art["verification_status"])
        self.assertEqual("independent_verification", prior_art["report_classification"])
        self.assertEqual("already_refuted", prior_art["target_resolution_status"])

    def test_approval_without_two_rechecks_is_refused(self) -> None:
        value = self.approved()
        value["publication_approval"]["novelty_rechecks"] = []
        with self.assertRaisesRegex(PublicationValidationError, "announcement_novelty_rechecks_required"):
            load_manuscript(value)

    def test_result_edit_makes_the_announcement_recheck_stale(self) -> None:
        value = self.approved()
        value["claims"][0]["prose_statement"] += " Changed after the search."
        with self.assertRaisesRegex(PublicationValidationError, "stale_subject_binding"):
            load_manuscript(value)

    def test_reusing_the_start_check_at_announcement_is_refused(self) -> None:
        value = self.approved()
        value["publication_approval"]["novelty_rechecks"][1] = copy.deepcopy(
            value["publication_approval"]["novelty_rechecks"][0]
        )
        with self.assertRaisesRegex(PublicationValidationError, "checkpoint_mismatch"):
            load_manuscript(value)


if __name__ == "__main__":
    unittest.main()
