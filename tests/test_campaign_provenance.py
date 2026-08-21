from __future__ import annotations

import json
from pathlib import Path
import unittest
from dataclasses import replace

from math_research.campaign import (
    ActionRecord,
    ActionType,
    ActorType,
    CampaignProvenanceError,
    ExternalOrigin,
    ImportRecord,
    ModelCallRecord,
    RecordStatus,
    ToolRunRecord,
    UsageSource,
    build_campaign_export,
    export_campaign_bytes,
    verify_campaign_export,
)


def h(character: str) -> str:
    return "sha256:" + character * 64


def model_call(*, status: RecordStatus = RecordStatus.COMPLETED) -> ModelCallRecord:
    return ModelCallRecord(
        call_id="call.1", campaign_id="campaign.test", action_id="action.1",
        purpose="campaign_planner", provider="azure_openai", model_identifier="gpt-5.6-sol",
        live_configuration_hash=h("1"), pricing_snapshot_hash=h("2"),
        request_hash=h("3"), result_hash=h("4"), status=status,
        usage_source=UsageSource.API_REPORTED, input_tokens=100, output_tokens=20,
        estimated_cost_microusd=2090, provider_request_id="provider-request-1",
        recorded_at="2026-08-21T00:00:01Z",
    ).finalized()


def tool_run() -> ToolRunRecord:
    return ToolRunRecord(
        tool_run_id="tool.1", campaign_id="campaign.test", action_id="action.2",
        adapter_id="exact_graph_search", adapter_version="1.0.0",
        adapter_configuration_hash=h("5"), request_hash=h("6"), result_hash=h("7"),
        stdout_hash=h("8"), stderr_hash=h("9"), environment_hash=h("a"),
        status=RecordStatus.COMPLETED, measurement_source=UsageSource.LOCALLY_MEASURED,
        cpu_milliseconds=80, wall_milliseconds=100, peak_memory_bytes=4096,
        output_bytes=512, recorded_at="2026-08-21T00:00:02Z",
    ).finalized()


def actions() -> tuple[ActionRecord, ...]:
    return (
        ActionRecord(
            action_id="action.1", campaign_id="campaign.test", sequence=1,
            branch_id="branch.main",
            action_type=ActionType.DERIVE, actor_type=ActorType.MODEL,
            actor_id="model.lead", parent_action_ids=(), input_artifact_hashes=(h("b"),),
            source_record_ids=("call.1",), output_artifact_hashes=(h("4"),),
            status=RecordStatus.COMPLETED, declared_rationale="Plan an exact falsification.",
            recorded_at="2026-08-21T00:00:01Z",
        ).finalized(),
        ActionRecord(
            action_id="action.2", campaign_id="campaign.test", sequence=2,
            branch_id="branch.main",
            action_type=ActionType.EXPERIMENT, actor_type=ActorType.TOOL,
            actor_id="tool.exact_graph_search", parent_action_ids=("action.1",),
            input_artifact_hashes=(h("4"),), source_record_ids=("tool.1",),
            output_artifact_hashes=(h("7"),), status=RecordStatus.COMPLETED,
            declared_rationale="Run the selected exact experiment.",
            recorded_at="2026-08-21T00:00:02Z",
        ).finalized(),
    )


def complete_export():
    return build_campaign_export(
        campaign_id="campaign.test", target_hash=h("b"), configuration_hash=h("c"),
        actions=actions(), model_calls=(model_call(),), tool_runs=(tool_run(),),
    )


class CampaignProvenanceTests(unittest.TestCase):
    def test_complete_campaign_replays_from_canonical_bytes(self) -> None:
        export = complete_export()
        replayed = verify_campaign_export(export_campaign_bytes(export))
        self.assertEqual(replayed.content_hash, export.content_hash)
        self.assertEqual(replayed.operational_hash, export.operational_hash)
        self.assertEqual(replayed.attribution_status, "adaivy_campaign")
        self.assertEqual(replayed.measurement_status, "complete")
        self.assertEqual(replayed.usage["requests_attempted"], 1)
        self.assertEqual(replayed.usage["responses_completed"], 1)
        self.assertEqual(replayed.usage["usage_reported_calls"], 1)
        self.assertEqual(replayed.usage["tool_runs_completed"], 1)
        self.assertEqual(replayed.usage["total_tokens"], 120)
        self.assertEqual(replayed.usage["estimated_cost_microusd"], 2090)
        self.assertEqual(replayed.usage["billing_status"], "not_billed")
        self.assertNotIn("billed_cost", replayed.usage)

    def test_status_counters_are_derived_not_declared(self) -> None:
        failed = replace(model_call(), call_id="call.failed", action_id="action.1",
                         status=RecordStatus.FAILED).finalized()
        first = replace(actions()[0], source_record_ids=("call.1", "call.failed")).finalized()
        export = build_campaign_export(
            campaign_id="campaign.test", target_hash=h("b"), configuration_hash=h("c"),
            actions=(first, actions()[1]), model_calls=(model_call(), failed), tool_runs=(tool_run(),),
        )
        self.assertEqual(export.usage["requests_attempted"], 2)
        self.assertEqual(export.usage["responses_completed"], 1)
        self.assertEqual(export.usage["responses_failed"], 1)
        self.assertEqual(export.usage["responses_incomplete"], 0)

    def test_incomplete_model_and_failed_tool_are_counted_separately(self) -> None:
        incomplete = replace(model_call(), status=RecordStatus.INCOMPLETE).finalized()
        failed_tool = replace(tool_run(), status=RecordStatus.FAILED).finalized()
        export = build_campaign_export(
            campaign_id="campaign.test", target_hash=h("b"), configuration_hash=h("c"),
            actions=actions(), model_calls=(incomplete,), tool_runs=(failed_tool,),
        )
        self.assertEqual(export.usage["requests_attempted"], 1)
        self.assertEqual(export.usage["responses_incomplete"], 1)
        self.assertEqual(export.usage["responses_completed"], 0)
        self.assertEqual(export.usage["tool_runs_attempted"], 1)
        self.assertEqual(export.usage["tool_runs_failed"], 1)

    def test_external_codex_import_is_fail_closed_attribution(self) -> None:
        imported = ImportRecord(
            import_id="import.codex.1", campaign_id="campaign.test", action_id="action.3",
            origin_type=ExternalOrigin.EXTERNAL_CODEX, source_id="codex.task.peer",
            artifact_hash=h("d"), usage_source=UsageSource.UNAVAILABLE,
            model_calls=None, input_tokens=None, output_tokens=None,
            estimated_cost_microusd=None, note="Interactive Codex contribution; usage unavailable.",
            recorded_at="2026-08-21T00:00:03Z",
        ).finalized()
        imported_action = ActionRecord(
            action_id="action.3", campaign_id="campaign.test", sequence=3,
            branch_id="branch.main",
            action_type=ActionType.IMPORT, actor_type=ActorType.EXTERNAL_SYSTEM,
            actor_id="codex.task.peer", parent_action_ids=("action.2",),
            input_artifact_hashes=(h("7"),), source_record_ids=("import.codex.1",),
            output_artifact_hashes=(h("d"),), status=RecordStatus.COMPLETED,
            declared_rationale="Import an externally derived candidate as a proposal.",
            recorded_at="2026-08-21T00:00:03Z",
        ).finalized()
        export = build_campaign_export(
            campaign_id="campaign.test", target_hash=h("b"), configuration_hash=h("c"),
            actions=(*actions(), imported_action), model_calls=(model_call(),),
            tool_runs=(tool_run(),), imports=(imported,),
        )
        self.assertEqual(export.attribution_status, "external_assisted")
        self.assertEqual(export.measurement_status, "partial")
        value = json.loads(export_campaign_bytes(export))
        value["attribution_status"] = "adaivy_campaign"
        with self.assertRaisesRegex(CampaignProvenanceError, "attribution"):
            verify_campaign_export(value)

    def test_operational_usage_tampering_is_detected_separately(self) -> None:
        export = complete_export()
        value = json.loads(export_campaign_bytes(export))
        original_content_hash = value["content_hash"]
        value["model_calls"][0]["input_tokens"] += 1
        self.assertEqual(value["content_hash"], original_content_hash)
        with self.assertRaisesRegex(CampaignProvenanceError, "operational_hash mismatch"):
            verify_campaign_export(value)

    def test_summary_tampering_is_rejected(self) -> None:
        value = json.loads(export_campaign_bytes(complete_export()))
        value["usage"]["estimated_cost_microusd"] = 1
        with self.assertRaises(CampaignProvenanceError):
            verify_campaign_export(value)

    def test_missing_source_record_breaks_closure(self) -> None:
        first = replace(actions()[0], source_record_ids=("call.missing",)).finalized()
        with self.assertRaisesRegex(CampaignProvenanceError, "absent or misbound"):
            build_campaign_export(
                campaign_id="campaign.test", target_hash=h("b"), configuration_hash=h("c"),
                actions=(first, actions()[1]), model_calls=(model_call(),), tool_runs=(tool_run(),),
            )

    def test_artifact_from_nowhere_breaks_closure(self) -> None:
        second = replace(actions()[1], input_artifact_hashes=(h("f"),)).finalized()
        with self.assertRaisesRegex(CampaignProvenanceError, "outside campaign provenance"):
            build_campaign_export(
                campaign_id="campaign.test", target_hash=h("b"), configuration_hash=h("c"),
                actions=(actions()[0], second), model_calls=(model_call(),), tool_runs=(tool_run(),),
            )

    def test_orphan_source_record_breaks_closure(self) -> None:
        orphan = replace(model_call(), call_id="call.orphan").finalized()
        with self.assertRaisesRegex(CampaignProvenanceError, "exactly one action"):
            build_campaign_export(
                campaign_id="campaign.test", target_hash=h("b"), configuration_hash=h("c"),
                actions=actions(), model_calls=(model_call(), orphan), tool_runs=(tool_run(),),
            )

    def test_noncanonical_bytes_are_rejected(self) -> None:
        pretty = json.dumps(json.loads(export_campaign_bytes(complete_export())), indent=2).encode()
        with self.assertRaisesRegex(CampaignProvenanceError, "not canonical"):
            verify_campaign_export(pretty)

    def test_extra_field_is_rejected(self) -> None:
        value = json.loads(export_campaign_bytes(complete_export()))
        value["unrecorded_work"] = True
        with self.assertRaisesRegex(CampaignProvenanceError, "closed schema"):
            verify_campaign_export(value)

    def test_unavailable_usage_cannot_smuggle_zero_as_measured(self) -> None:
        with self.assertRaisesRegex(CampaignProvenanceError, "cannot carry measured totals"):
            replace(
                model_call(), usage_source=UsageSource.UNAVAILABLE,
                input_tokens=0, output_tokens=0, estimated_cost_microusd=0,
            )

    def test_external_usage_cannot_self_attest_completeness(self) -> None:
        with self.assertRaisesRegex(CampaignProvenanceError, "verified usage-record"):
            ImportRecord(
                import_id="import.external.usage", campaign_id="campaign.test",
                action_id="action.3", origin_type=ExternalOrigin.EXTERNAL_CODEX,
                source_id="codex.task.peer", artifact_hash=h("d"),
                usage_source=UsageSource.API_REPORTED, model_calls=1,
                input_tokens=10, output_tokens=5, estimated_cost_microusd=3,
                note="Unverified external usage.", recorded_at="2026-08-21T00:00:03Z",
            )

    def test_campaign_core_has_no_network_or_subprocess_import(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (Path("src/math_research/campaign")).glob("*.py")
        )
        for forbidden in ("import socket", "import subprocess", "import urllib", "import http"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
