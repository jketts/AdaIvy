"""Action-level resume and literature-loop invariants."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from math_research.campaign.checkpoint import ActionCheckpointStore
from math_research.campaign.end_to_end import (
    EndToEndCampaignRunner,
    EndToEndRuntimeError,
    RuntimeAction,
)
from math_research.campaign.records import ActionType
from math_research.campaign.fixture_runtime import run_fixture_campaign


NOW = "2026-08-22T04:00:00Z"


class EndToEndCheckpointTests(unittest.TestCase):
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
            self.assertEqual(13, first["completed_action_count"])
            self.assertEqual(3, first["charge_event_count"])
            self.assertEqual(first["content_hash"], second["content_hash"])
            self.assertEqual(3, second["charge_event_count"])
            self.assertFalse(first["before_research_human_checkpoint_required"])
            self.assertTrue(first["before_announcement_human_checkpoint_required"])

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
                        ActionType.FOLLOW_DISCOVERY_RESULTS, {"max_depth": 2},
                        lambda key: {},
                    ),
                ])


if __name__ == "__main__":
    unittest.main()
