from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from math_research.domain.entities import oid
from math_research.interchange import import_trusted_replay
from math_research.phase2.artifacts import FileArtifactStore
from math_research.phase2.reporting import report_hash
from math_research.phase2.serialization import canonical_hash, sha256_bytes
from math_research.phase2.sqlite_workspace import SQLiteWorkspace


class Phase2DemonstrationEvidenceTests(unittest.TestCase):
    def test_recorded_demonstration_is_internally_consistent(self) -> None:
        root = Path("reports/phase-2")
        evidence = json.loads((root / "demonstration.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["fake_provider"]["status"], "awaiting_review")
        self.assertEqual(evidence["fake_provider"]["accepted_target_status"], "unknown")
        self.assertEqual(evidence["fake_provider"]["proposal_count"], 2)
        self.assertEqual(evidence["pause_restart_resume"]["status_after_restart"], "paused")
        self.assertEqual(evidence["pause_restart_resume"]["final_status"], "awaiting_review")
        self.assertTrue(evidence["crash_recovery"]["injected_crash_observed"])
        self.assertEqual(evidence["crash_recovery"]["proposals_before_recovery"], 0)
        self.assertEqual(evidence["crash_recovery"]["semantic_proposal_count"], 2)
        self.assertEqual(evidence["external_backend"]["failed_import"]["status"], "rejected")
        self.assertEqual(evidence["external_backend"]["successful_dispositions"], ["proposal"])
        self.assertTrue(evidence["report_replay"]["byte_identical"])
        self.assertEqual(evidence["report_replay"]["first_hash"], evidence["report_replay"]["regenerated_hash"])

        dossier = import_trusted_replay((root / "accepted-dossier.json").read_bytes())
        self.assertEqual(evidence["replay_hashes"]["accepted_dossier_hash"], evidence["fake_provider"]["accepted_dossier_hash"])
        store = FileArtifactStore(root / "artifacts")
        manifest_hash = evidence["model_context_isolation"]["serialized_context_hash"]
        self.assertEqual(sha256_bytes(store.get(manifest_hash)), manifest_hash)

        # Sealed evidence: this file is pinned byte-for-byte by the Phase 4A
        # protected-evidence manifest, so it is replayed read-only.
        with SQLiteWorkspace(root / "workspace.sqlite3", read_only=True) as workspace:
            self.assertEqual(
                report_hash(workspace, oid("run.phase2.demo.fake.v1")),
                evidence["replay_hashes"]["report_hash"],
            )

    def test_live_provider_status_is_honest(self) -> None:
        value = json.loads(Path("reports/phase-2/live-provider-status.json").read_text(encoding="utf-8"))
        self.assertEqual(value["status"], "passed")
        self.assertEqual(value["run_id"], "run.phase2.live.openai.gpt5-mini.v3")
        self.assertEqual(len(value["calls"]), 2)
        self.assertEqual([call["purpose"] for call in value["calls"]], ["proposer", "verifier"])
        self.assertEqual({call["status"] for call in value["calls"]}, {"succeeded"})
        self.assertEqual({call["usage_source"] for call in value["calls"]}, {"api_reported"})
        self.assertEqual(len(set(value["response_ids"])), 2)
        self.assertTrue(all(value["response_ids"]))
        self.assertEqual(sum(call["input_tokens"] for call in value["calls"]), 2367)
        self.assertEqual(sum(call["output_tokens"] for call in value["calls"]), 1824)
        self.assertEqual(sum(call["total_tokens"] for call in value["calls"]), 4191)
        self.assertEqual(value["estimated_cost_microusd"], 4240)
        self.assertEqual(
            sum(call["estimated_cost_microusd"] for call in value["calls"]),
            value["estimated_cost_microusd"],
        )
        self.assertEqual(
            {call["pricing_snapshot_id"] for call in value["calls"]},
            {value["pricing_snapshot_id"]},
        )
        self.assertEqual(value["credential_leak_matches"], 0)
        self.assertEqual(value["history"][0]["status"], "failed")
        self.assertEqual(value["history"][0]["history"][0]["status"], "failed")
        self.assertEqual(value["history"][0]["history"][0]["history"][0]["status"], "blocked")

        root = Path("reports/phase-2/live-openai-gpt5-mini-v3")
        self.assertEqual(sha256_bytes((root / "traceable-report.md").read_bytes()), value["report_hash"])
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "workspace.sqlite3"
            shutil.copyfile(root / "workspace.sqlite3", database)
            with SQLiteWorkspace(database) as workspace:
                run_id = oid(value["run_id"])
                self.assertEqual(report_hash(workspace, run_id), value["report_hash"])
                self.assertEqual(canonical_hash(workspace.timeline(run_id)), value["event_replay_hash"])
                manifest = workspace.get_manifest(run_id)
                self.assertEqual(manifest.serialized_context_hash, value["manifest_hash"])
                self.assertTrue(manifest.independence.context_isolated)
                self.assertTrue(manifest.independence.separate_model_call)
                self.assertFalse(manifest.independence.different_model)
                self.assertFalse(manifest.independence.different_provider)
                self.assertFalse(manifest.independence.fully_independent)
                proposals = workspace.list_proposals(run_id)
                self.assertEqual(len(proposals), 2)
                self.assertEqual({proposal.disposition for proposal in proposals}, {"proposal"})
