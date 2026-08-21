"""Acceptance tests for fail-closed campaign-to-publication provenance."""

from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from math_research.campaign import (  # noqa: E402
    ActionRecord,
    ActionType,
    ActorType,
    ExternalOrigin,
    ImportRecord,
    ModelCallRecord,
    RecordStatus,
    ToolRunRecord,
    UsageSource,
    build_campaign_export,
)
from math_research.publication.campaign import (  # noqa: E402
    CertificateContribution,
    ClaimContribution,
    bridge_campaign_to_publication,
    build_publication_campaign_link,
)
from math_research.publication.errors import PublicationValidationError  # noqa: E402


def digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


CAMPAIGN_ID = "campaign.publication.acceptance.v1"
TARGET = digest("target")
CONFIG = digest("configuration")
PROPOSAL = digest("proposal")
CERTIFICATE = digest("certificate")


def action(
    *,
    action_id: str,
    sequence: int,
    action_type: ActionType,
    actor_type: ActorType,
    source_ids: tuple[str, ...],
    outputs: tuple[str, ...],
    parents: tuple[str, ...] = (),
    inputs: tuple[str, ...] = (TARGET,),
    status: RecordStatus = RecordStatus.COMPLETED,
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        campaign_id=CAMPAIGN_ID,
        sequence=sequence,
        branch_id="branch.main",
        action_type=action_type,
        actor_type=actor_type,
        actor_id=f"actor.{action_id}",
        parent_action_ids=parents,
        input_artifact_hashes=inputs,
        source_record_ids=source_ids,
        output_artifact_hashes=outputs,
        status=status,
        declared_rationale="acceptance fixture",
        recorded_at=f"2026-08-21T00:00:0{sequence}Z",
    )


def model_call(
    *,
    call_id: str = "call.derive",
    action_id: str = "action.derive",
    result_hash: str = PROPOSAL,
    status: RecordStatus = RecordStatus.COMPLETED,
    usage_source: UsageSource = UsageSource.API_REPORTED,
    input_tokens: int = 120,
    output_tokens: int = 30,
    cost: int | None = 1_250,
) -> ModelCallRecord:
    return ModelCallRecord(
        call_id=call_id,
        campaign_id=CAMPAIGN_ID,
        action_id=action_id,
        purpose="research",
        provider="openai",
        model_identifier="gpt-5.6-sol",
        live_configuration_hash=digest("live-config"),
        pricing_snapshot_hash=digest("pricing"),
        request_hash=digest(f"request:{call_id}"),
        result_hash=result_hash,
        status=status,
        usage_source=usage_source,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_microusd=cost,
        provider_request_id=f"provider-{call_id}",
        recorded_at="2026-08-21T00:00:01Z",
    )


def tool_run(
    *,
    tool_run_id: str = "tool.verify",
    action_id: str = "action.verify",
    result_hash: str = CERTIFICATE,
    measurement_source: UsageSource = UsageSource.LOCALLY_MEASURED,
) -> ToolRunRecord:
    return ToolRunRecord(
        tool_run_id=tool_run_id,
        campaign_id=CAMPAIGN_ID,
        action_id=action_id,
        adapter_id="exact-checker",
        adapter_version="1.0.0",
        adapter_configuration_hash=digest("tool-config"),
        request_hash=digest(f"tool-request:{tool_run_id}"),
        result_hash=result_hash,
        stdout_hash=digest(f"stdout:{tool_run_id}"),
        stderr_hash=digest(f"stderr:{tool_run_id}"),
        environment_hash=digest("environment"),
        status=RecordStatus.COMPLETED,
        measurement_source=measurement_source,
        cpu_milliseconds=10 if measurement_source is not UsageSource.UNAVAILABLE else None,
        wall_milliseconds=12 if measurement_source is not UsageSource.UNAVAILABLE else None,
        peak_memory_bytes=4096 if measurement_source is not UsageSource.UNAVAILABLE else None,
        output_bytes=512 if measurement_source is not UsageSource.UNAVAILABLE else None,
        recorded_at="2026-08-21T00:00:02Z",
    )


def manuscript(*, generator: str = "AdaIvy project", ai_generated: bool = True) -> dict:
    return {
        "claims": [{
            "claim_id": "claim.result",
            "certificate_id": "certificate.result",
            "authorship": {"ai_generated": ai_generated, "generator": generator},
        }],
        "certificates": [{
            "certificate_id": "certificate.result",
            "run_id": CAMPAIGN_ID,
            "result_hash": CERTIFICATE,
        }],
    }


def internal_campaign(
    *,
    usage_source: UsageSource = UsageSource.API_REPORTED,
    tool_measurement_source: UsageSource = UsageSource.LOCALLY_MEASURED,
):
    call = model_call(
        usage_source=usage_source,
        input_tokens=120 if usage_source is not UsageSource.UNAVAILABLE else 0,
        output_tokens=30 if usage_source is not UsageSource.UNAVAILABLE else 0,
        cost=1_250 if usage_source is not UsageSource.UNAVAILABLE else None,
    )
    checker = tool_run(measurement_source=tool_measurement_source)
    return build_campaign_export(
        campaign_id=CAMPAIGN_ID,
        target_hash=TARGET,
        configuration_hash=CONFIG,
        actions=(
            action(
                action_id="action.derive", sequence=1, action_type=ActionType.DERIVE,
                actor_type=ActorType.MODEL, source_ids=(call.call_id,), outputs=(PROPOSAL,),
            ),
            action(
                action_id="action.verify", sequence=2, action_type=ActionType.VERIFY,
                actor_type=ActorType.TOOL, source_ids=(checker.tool_run_id,),
                outputs=(CERTIFICATE,), parents=("action.derive",), inputs=(PROPOSAL,),
            ),
        ),
        model_calls=(call,),
        tool_runs=(checker,),
    )


def link(campaign, *, discovery: tuple[str, ...] = ("action.derive",)):
    return build_publication_campaign_link(
        campaign,
        claims=(ClaimContribution(
            claim_id="claim.result",
            discovery_action_ids=discovery,
            contribution_action_ids=("action.derive", "action.verify"),
            artifact_hashes=(PROPOSAL, CERTIFICATE),
        ),),
        certificates=(CertificateContribution(
            certificate_id="certificate.result",
            action_id="action.verify",
            artifact_hash=CERTIFICATE,
        ),),
    )


def imported_campaign(origin: ExternalOrigin, *, usage_source: UsageSource):
    imported = ImportRecord(
        import_id="import.discovery",
        campaign_id=CAMPAIGN_ID,
        action_id="action.derive",
        origin_type=origin,
        source_id="external.source",
        artifact_hash=PROPOSAL,
        usage_source=usage_source,
        model_calls=None if usage_source is UsageSource.UNAVAILABLE else 1,
        input_tokens=None if usage_source is UsageSource.UNAVAILABLE else 200,
        output_tokens=None if usage_source is UsageSource.UNAVAILABLE else 50,
        estimated_cost_microusd=None if usage_source is UsageSource.UNAVAILABLE else 5_000,
        note="Imported candidate; no AdaIvy discovery attribution.",
        recorded_at="2026-08-21T00:00:01Z",
    )
    checker = tool_run()
    return build_campaign_export(
        campaign_id=CAMPAIGN_ID,
        target_hash=TARGET,
        configuration_hash=CONFIG,
        actions=(
            action(
                action_id="action.derive", sequence=1, action_type=ActionType.IMPORT,
                actor_type=(ActorType.HUMAN if origin is ExternalOrigin.HUMAN else ActorType.EXTERNAL_SYSTEM),
                source_ids=(imported.import_id,), outputs=(PROPOSAL,),
            ),
            action(
                action_id="action.verify", sequence=2, action_type=ActionType.VERIFY,
                actor_type=ActorType.TOOL, source_ids=(checker.tool_run_id,),
                outputs=(CERTIFICATE,), parents=("action.derive",), inputs=(PROPOSAL,),
            ),
        ),
        tool_runs=(checker,),
        imports=(imported,),
    )


def campaign_with_all_model_outcomes():
    failed_hash = digest("failed-result")
    incomplete_hash = digest("incomplete-result")
    failed = model_call(
        call_id="call.failed", action_id="action.failed", result_hash=failed_hash,
        status=RecordStatus.FAILED, input_tokens=11, output_tokens=2, cost=100,
    )
    incomplete = model_call(
        call_id="call.incomplete", action_id="action.incomplete", result_hash=incomplete_hash,
        status=RecordStatus.INCOMPLETE, input_tokens=13, output_tokens=3, cost=200,
    )
    completed = model_call()
    checker = tool_run()
    return build_campaign_export(
        campaign_id=CAMPAIGN_ID,
        target_hash=TARGET,
        configuration_hash=CONFIG,
        actions=(
            action(
                action_id="action.failed", sequence=1, action_type=ActionType.DERIVE,
                actor_type=ActorType.MODEL, source_ids=(failed.call_id,), outputs=(failed_hash,),
                status=RecordStatus.FAILED,
            ),
            action(
                action_id="action.incomplete", sequence=2, action_type=ActionType.DERIVE,
                actor_type=ActorType.MODEL, source_ids=(incomplete.call_id,),
                outputs=(incomplete_hash,), status=RecordStatus.INCOMPLETE,
            ),
            action(
                action_id="action.derive", sequence=3, action_type=ActionType.DERIVE,
                actor_type=ActorType.MODEL, source_ids=(completed.call_id,), outputs=(PROPOSAL,),
            ),
            action(
                action_id="action.verify", sequence=4, action_type=ActionType.VERIFY,
                actor_type=ActorType.TOOL, source_ids=(checker.tool_run_id,),
                outputs=(CERTIFICATE,), parents=("action.derive",), inputs=(PROPOSAL,),
            ),
        ),
        model_calls=(failed, incomplete, completed),
        tool_runs=(checker,),
    )


class PublicationCampaignTests(unittest.TestCase):
    def test_closed_internal_campaign_allows_adaivy_attribution(self) -> None:
        campaign = internal_campaign()
        projection = bridge_campaign_to_publication(manuscript(), campaign, link(campaign))
        self.assertEqual(projection.claim_authorship["claim.result"], "adaivy_campaign")
        self.assertTrue(projection.adaivy_attribution_allowed["claim.result"])
        self.assertEqual(projection.disclosure["measurement_status"], "complete")
        self.assertEqual(projection.disclosure["requests_attempted"], 1)
        self.assertEqual(projection.disclosure["responses_completed"], 1)
        self.assertEqual(projection.disclosure["responses_failed"], 0)
        self.assertEqual(projection.disclosure["responses_incomplete"], 0)
        self.assertEqual(projection.disclosure["estimated_cost_usd"], "0.00125")
        self.assertEqual(projection.disclosure["cost_kind"], "estimated_not_billed")
        self.assertEqual(projection.disclosure["pricing_snapshot_hashes"], [digest("pricing")])
        self.assertEqual(projection.disclosure["live_configuration_hashes"], [digest("live-config")])
        self.assertIn("not provider-billed", projection.disclosure["note"])

    def test_partial_accounting_refuses_adaivy_generated_attribution(self) -> None:
        campaign = internal_campaign(usage_source=UsageSource.UNAVAILABLE)
        with self.assertRaises(PublicationValidationError) as caught:
            bridge_campaign_to_publication(manuscript(), campaign, link(campaign))
        self.assertEqual(caught.exception.code, "adaivy_origin_requires_closed_campaign")

    def test_partial_internal_campaign_cannot_evade_refusal_with_external_label(self) -> None:
        campaign = internal_campaign(usage_source=UsageSource.UNAVAILABLE)
        with self.assertRaises(PublicationValidationError) as caught:
            bridge_campaign_to_publication(
                manuscript(generator="external Codex"), campaign, link(campaign),
            )
        self.assertEqual(caught.exception.code, "adaivy_origin_requires_closed_campaign")

    def test_unavailable_internal_accounting_cannot_enter_publication(self) -> None:
        campaign = internal_campaign(
            usage_source=UsageSource.UNAVAILABLE,
            tool_measurement_source=UsageSource.UNAVAILABLE,
        )
        with self.assertRaises(PublicationValidationError) as caught:
            bridge_campaign_to_publication(
                manuscript(generator="external Codex"), campaign, link(campaign),
            )
        self.assertEqual(caught.exception.code, "adaivy_origin_requires_closed_campaign")

    def test_attempt_response_outcomes_are_reported_separately(self) -> None:
        campaign = campaign_with_all_model_outcomes()
        projection = bridge_campaign_to_publication(manuscript(), campaign, link(campaign))
        disclosure = projection.disclosure
        self.assertEqual(disclosure["requests_attempted"], 3)
        self.assertEqual(disclosure["responses_completed"], 1)
        self.assertEqual(disclosure["responses_failed"], 1)
        self.assertEqual(disclosure["responses_incomplete"], 1)
        self.assertEqual(disclosure["usage_reported_calls"], 3)

    def test_external_codex_origin_is_derived_and_total_cost_is_unknown(self) -> None:
        campaign = imported_campaign(
            ExternalOrigin.EXTERNAL_CODEX, usage_source=UsageSource.UNAVAILABLE,
        )
        projection = bridge_campaign_to_publication(
            manuscript(generator="external Codex"), campaign, link(campaign),
        )
        self.assertEqual(projection.claim_authorship["claim.result"], "external_codex")
        self.assertFalse(projection.adaivy_attribution_allowed["claim.result"])
        self.assertEqual(projection.disclosure["measurement_status"], "partial")
        self.assertFalse(projection.disclosure["accounting_complete"])
        self.assertIn("total campaign usage and cost are unknown", projection.disclosure["note"])

    def test_external_codex_work_cannot_be_relabelled_as_adaivy(self) -> None:
        campaign = imported_campaign(
            ExternalOrigin.EXTERNAL_CODEX, usage_source=UsageSource.UNAVAILABLE,
        )
        with self.assertRaises(PublicationValidationError) as caught:
            bridge_campaign_to_publication(manuscript(), campaign, link(campaign))
        self.assertEqual(caught.exception.code, "adaivy_origin_requires_closed_campaign")

    def test_human_origin_is_derived(self) -> None:
        campaign = imported_campaign(ExternalOrigin.HUMAN, usage_source=UsageSource.UNAVAILABLE)
        projection = bridge_campaign_to_publication(
            manuscript(generator="human", ai_generated=False), campaign, link(campaign),
        )
        self.assertEqual(projection.claim_authorship["claim.result"], "human")
        self.assertFalse(projection.adaivy_attribution_allowed["claim.result"])

    def test_mixed_discovery_roots_are_not_adaivy_attributable(self) -> None:
        imported = imported_campaign(
            ExternalOrigin.EXTERNAL_CODEX, usage_source=UsageSource.UNAVAILABLE,
        )
        # The verification action is an internal tool action descended from the
        # external candidate. Naming both as discovery roots produces mixed
        # authorship rather than laundering the external root.
        projection = bridge_campaign_to_publication(
            manuscript(generator="mixed"), imported,
            link(imported, discovery=("action.derive", "action.verify")),
        )
        self.assertEqual(projection.claim_authorship["claim.result"], "mixed")
        self.assertFalse(projection.adaivy_attribution_allowed["claim.result"])

    def test_every_claim_must_have_a_campaign_link(self) -> None:
        campaign = internal_campaign()
        broken = build_publication_campaign_link(campaign, claims=(), certificates=link(campaign).certificates)
        with self.assertRaises(PublicationValidationError) as caught:
            bridge_campaign_to_publication(manuscript(), campaign, broken)
        self.assertEqual(caught.exception.code, "campaign_claim_coverage_incomplete")

    def test_certificate_run_must_be_the_campaign(self) -> None:
        campaign = internal_campaign()
        value = manuscript()
        value["certificates"][0]["run_id"] = "run.unrelated"
        with self.assertRaises(PublicationValidationError) as caught:
            bridge_campaign_to_publication(value, campaign, link(campaign))
        self.assertEqual(caught.exception.code, "campaign_certificate_lineage_mismatch")

    def test_certificate_hash_must_resolve_to_the_tool_run(self) -> None:
        campaign = internal_campaign()
        broken = build_publication_campaign_link(
            campaign,
            claims=link(campaign).claims,
            certificates=(CertificateContribution(
                certificate_id="certificate.result",
                action_id="action.verify",
                artifact_hash=digest("invented"),
            ),),
        )
        with self.assertRaises(PublicationValidationError) as caught:
            bridge_campaign_to_publication(manuscript(), campaign, broken)
        self.assertEqual(caught.exception.code, "campaign_certificate_without_tool_run")

    def test_operational_tampering_is_refused_before_disclosure(self) -> None:
        campaign = internal_campaign()
        tampered = _campaign_mapping(campaign)
        tampered["usage"]["estimated_cost_microusd"] = 1
        with self.assertRaises(PublicationValidationError) as caught:
            bridge_campaign_to_publication(manuscript(), tampered, link(campaign))
        self.assertEqual(caught.exception.code, "campaign_export_invalid")

    def test_link_hash_tampering_is_refused(self) -> None:
        campaign = internal_campaign()
        broken = replace(link(campaign), campaign_operational_hash=digest("wrong"))
        with self.assertRaises(PublicationValidationError) as caught:
            bridge_campaign_to_publication(manuscript(), campaign, broken)
        self.assertEqual(caught.exception.code, "campaign_link_hash_mismatch")


def _campaign_mapping(value):
    """Plain mutable value used only for single-field tamper probes."""

    from dataclasses import fields, is_dataclass
    from enum import Enum

    def convert(item):
        if isinstance(item, Enum):
            return item.value
        if is_dataclass(item) and not isinstance(item, type):
            return {field.name: convert(getattr(item, field.name)) for field in fields(item)}
        if isinstance(item, dict):
            return {key: convert(child) for key, child in item.items()}
        if isinstance(item, (tuple, list)):
            return [convert(child) for child in item]
        return item

    return copy.deepcopy(convert(value))


if __name__ == "__main__":
    unittest.main()
