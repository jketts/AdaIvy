"""Action-level resume and literature-loop invariants."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import json

from math_research.campaign.checkpoint import ActionCheckpointStore, CheckpointError
from math_research.campaign.end_to_end import (
    ACTION_SCHEMA_PATH,
    EndToEndCampaignRunner,
    EndToEndRuntimeError,
    RuntimeAction,
    parse_planned_action,
)
from math_research.campaign.records import ActionType
from math_research.campaign.fixture_runtime import (
    load_fixture_runtime_config, run_fixture_campaign,
)
from math_research.publication.bundle import verify_bundle


NOW = "2026-08-22T04:00:00Z"


class EndToEndCheckpointTests(unittest.TestCase):
    def test_v2_schema_is_consumed_and_admits_the_experiment_action(self) -> None:
        schema = json.loads(ACTION_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertIn("experiment", schema["properties"]["action_type"]["enum"])
        planned = parse_planned_action(json.dumps({
            "schema_version": "2.0.0", "action_type": "experiment",
            "branch_id": "branch.main", "rationale": "bounded test",
            "operation_request": {"operation": "exact"},
        }), lambda key: {})
        self.assertIs(ActionType.EXPERIMENT, planned.action_type)

    def test_complete_fixture_and_resume_repeat_no_paid_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = Path(__file__).resolve().parents[1]
            first = run_fixture_campaign(
                root / "campaign", data_root=root / "data",
                campaign_id="campaign.fixture.acceptance", recorded_at=NOW,
                repository_root=repository,
            )
            second = run_fixture_campaign(
                root / "campaign", data_root=root / "data",
                campaign_id="campaign.fixture.acceptance", recorded_at=NOW,
                repository_root=repository,
            )
            self.assertEqual("completed", first["status"])
            self.assertEqual(15, first["completed_action_count"])
            self.assertEqual(8, first["charge_event_count"])
            self.assertEqual(first["content_hash"], second["content_hash"])
            self.assertEqual(8, second["charge_event_count"])
            self.assertEqual("candidate_refuted", first["initial_verification_status"])
            self.assertEqual("candidate_verified", first["final_verification_status"])
            self.assertFalse(first["before_research_human_checkpoint_required"])
            self.assertTrue(first["before_announcement_human_checkpoint_required"])
            manifest = verify_bundle(root / "campaign" / "publication")
            self.assertEqual("unapproved", manifest["publication_approval"])
            self.assertIn(manifest["typeset_status"], {"not_typeset", "typeset"})
            self.assertTrue(
                (root / "campaign" / "publication" / "records" / "retrieval-result.json").is_file()
            )

    def test_distinct_campaign_reuses_persistent_vectors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            arguments = dict(
                data_root=root / "data", recorded_at=NOW,
                repository_root=Path(__file__).resolve().parents[1],
            )
            first = run_fixture_campaign(
                root / "one", campaign_id="campaign.reuse.one", **arguments,
            )
            second = run_fixture_campaign(
                root / "two", campaign_id="campaign.reuse.two", **arguments,
            )
            self.assertEqual(2, first["document_embedding_provider_calls"])
            self.assertEqual(0, second["document_embedding_provider_calls"])
            self.assertEqual(8, first["charge_event_count"])
            self.assertEqual(6, second["charge_event_count"])

    def test_budget_exhaustion_produces_unresolved_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_fixture_campaign(
                root / "campaign", data_root=root / "data",
                campaign_id="campaign.fixture.exhausted", recorded_at=NOW,
                repository_root=Path(__file__).resolve().parents[1],
                max_embedding_requests=0,
            )
            self.assertEqual("unresolved", result["status"])
            self.assertEqual("embed_sources", result["unresolved"]["action_type"])
            self.assertTrue((root / "campaign" / "publication" / "paper.tex").is_file())
            manifest = verify_bundle(root / "campaign" / "publication")
            self.assertEqual(result["content_hash"], manifest["campaign_summary_hash"])

    def test_runtime_config_is_sealed_and_data_root_must_be_external(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            campaign = root / "campaign"
            run_fixture_campaign(
                campaign, data_root=root / "data", campaign_id="campaign.config",
                recorded_at=NOW, repository_root=Path(__file__).resolve().parents[1],
            )
            config = campaign / "end-to-end-runtime-config.json"
            original = config.read_text(encoding="utf-8")
            config.write_text(original.replace('"profile_id":"adaivy"', '"profile_id":"other"'))
            with self.assertRaises(ValueError):
                load_fixture_runtime_config(config)
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                run_fixture_campaign(
                    Path(temporary) / "campaign", data_root=repository / "work" / "forbidden-data",
                    campaign_id="campaign.badroot", recorded_at=NOW,
                    repository_root=repository,
                )

    def test_campaign_identifier_cannot_inject_latex(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                run_fixture_campaign(
                    root / "campaign", data_root=root / "data",
                    campaign_id=r"campaign.\input{secret}", recorded_at=NOW,
                    repository_root=Path(__file__).resolve().parents[1],
                )

    def test_resume_replays_completed_action_without_repeating_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []

            def effect(key):
                calls.append(key)
                return {"artifact": "search.fixture"}

            actions = [RuntimeAction(
                ActionType.SEARCH_LITERATURE, {"query": "graph spectrum"},
                effect, True,
            )]
            runner = EndToEndCampaignRunner(
                root, campaign_id="campaign.resume", recorded_at=NOW, max_actions=2,
            )
            self.assertEqual("completed", runner.run(actions)["status"])
            self.assertEqual("completed", runner.run(actions)["status"])
            self.assertEqual(1, len(calls))

    def test_ambiguous_paid_intent_is_never_repeated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ActionCheckpointStore(root, "campaign.ambiguous")
            store.intent(
                sequence=1, action_type="search_literature",
                request={"query": "spectral graph"}, paid_or_irreversible=True,
                recorded_at=NOW,
            )
            calls = []
            runner = EndToEndCampaignRunner(
                root, campaign_id="campaign.ambiguous", recorded_at=NOW,
                max_actions=2,
            )
            summary = runner.run([RuntimeAction(
                ActionType.SEARCH_LITERATURE, {"query": "spectral graph"},
                lambda key: calls.append(key) or {}, True,
            )])
            self.assertEqual("unresolved", summary["status"])
            self.assertEqual([], calls)
            self.assertFalse(summary["unresolved"]["paid_work_repeated"])

    def test_unpaid_intent_is_safely_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ActionCheckpointStore(root, "campaign.unpaid")
            store.intent(
                sequence=1, action_type="search_literature", request={"query": "x"},
                paid_or_irreversible=False, recorded_at=NOW,
            )
            calls: list[str] = []
            terminal = store.execute(
                sequence=1, action_type="search_literature", request={"query": "x"},
                paid_or_irreversible=False, recorded_at=NOW,
                effect=lambda key: calls.append(key) or {"status": "done"},
            )
            self.assertEqual("completed", terminal["status"])
            self.assertEqual(1, len(calls))

    def test_malformed_terminal_cannot_suppress_an_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ActionCheckpointStore(root, "campaign.malformed")
            intent = store.intent(
                sequence=1, action_type="search_literature", request={"query": "x"},
                paid_or_irreversible=False, recorded_at=NOW,
            )
            malformed = {
                "schema_version": "adaivy.campaign-action-checkpoint.v1",
                "record_type": "action_terminal", "campaign_id": "campaign.other",
                "sequence": 1, "action_type": "search_literature",
                "intent_hash": intent["content_hash"],
                "idempotency_key": intent["idempotency_key"], "status": "completed",
                "result": {}, "result_hash": "sha256:" + "0" * 64,
                "recorded_at": NOW,
            }
            from math_research.campaign.records import canonical_bytes, canonical_hash
            malformed["content_hash"] = canonical_hash(malformed)
            path = root / "action-checkpoints" / "000001.terminal.json"
            path.write_bytes(canonical_bytes(malformed) + b"\n")
            with self.assertRaises(CheckpointError):
                store.load(1, "terminal")

    def test_search_is_mandatory_and_depth_is_exactly_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runner = EndToEndCampaignRunner(
                Path(temporary), campaign_id="campaign.policy", recorded_at=NOW,
                max_actions=3,
            )
            with self.assertRaises(EndToEndRuntimeError):
                runner.run([RuntimeAction(ActionType.DERIVE, {}, lambda key: {})])
            with self.assertRaises(EndToEndRuntimeError):
                runner.run([
                    RuntimeAction(ActionType.SEARCH_LITERATURE, {}, lambda key: {}),
                    RuntimeAction(
                        ActionType.FOLLOW_DISCOVERY_RESULTS, {
                            "max_depth": 2, "origin": "x", "allowed_origins": ["x"],
                        },
                        lambda key: {},
                    ),
                ])
            with self.assertRaises(EndToEndRuntimeError):
                runner.run([
                    RuntimeAction(ActionType.SEARCH_LITERATURE, {}, lambda key: {}),
                    RuntimeAction(ActionType.RETRIEVE_EVIDENCE, {}, lambda key: {}),
                ])

    def test_verifier_failure_is_nonterminal_while_actions_remain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            continued: list[str] = []
            runner = EndToEndCampaignRunner(
                root, campaign_id="campaign.refute", recorded_at=NOW, max_actions=9,
            )
            noop = lambda key: {"status": "completed"}
            summary = runner.run([
                RuntimeAction(ActionType.SEARCH_LITERATURE, {}, noop),
                RuntimeAction(ActionType.FOLLOW_DISCOVERY_RESULTS, {
                    "max_depth": 1, "origin": "fixture", "allowed_origins": ["fixture"],
                }, noop),
                RuntimeAction(ActionType.ACQUIRE_SOURCE, {}, noop),
                RuntimeAction(ActionType.PARSE_SOURCE, {}, noop),
                RuntimeAction(ActionType.EMBED_SOURCES, {}, noop),
                RuntimeAction(ActionType.REFRESH_RETRIEVAL_INDEX, {}, noop),
                RuntimeAction(ActionType.RETRIEVE_EVIDENCE, {}, noop),
                RuntimeAction(
                    ActionType.VERIFY, {},
                    lambda key: (_ for _ in ()).throw(ValueError("candidate refuted")),
                ),
                RuntimeAction(
                    ActionType.FALSIFY, {},
                    lambda key: continued.append(key) or {"status": "repaired"},
                ),
            ])
            self.assertEqual("completed", summary["status"])
            self.assertEqual(9, summary["completed_action_count"])
            self.assertEqual(1, summary["failed_action_count"])
            self.assertTrue(summary["candidate_failure_continued"])
            self.assertEqual(1, len(continued))


if __name__ == "__main__":
    unittest.main()
