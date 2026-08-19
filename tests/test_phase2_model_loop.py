from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from math_research.domain.entities import oid
from math_research.domain.policies import TrustPolicy
from math_research.interchange import export_dossier_bytes
from math_research.phase2.artifacts import FileArtifactStore
from math_research.phase2.baseline_loop import (
    BaselineResearchLoop,
    InjectedCrash,
    deterministic_candidate,
    deterministic_fake_results,
)
from math_research.phase2.fixtures import build_open_theorem_dossier
from math_research.phase2.model_gateway import (
    OpenAIProviderConfig,
    OpenAIResponsesGateway,
    ScriptedModelGateway,
    redact_secrets,
)
from math_research.phase2.records import (
    BudgetLimits,
    ModelResult,
    ModelResultStatus,
    ModelRequest,
    ModelUsage,
    RunStatus,
    VerifierIndependence,
)
from math_research.phase2.prompt_templates import PromptCatalog
from math_research.phase2.reporting import render_durable_report, report_hash
from math_research.phase2.serialization import canonical_hash, canonical_json, sha256_bytes
from math_research.phase2.sqlite_workspace import BudgetExhausted, SQLiteWorkspace


class FakeAPIStatusError(Exception):
    pass


class FakeAPITimeoutError(Exception):
    pass


class FakeAPIConnectionError(Exception):
    pass


class FakeOpenAISDK:
    __version__ = "3.3.0-test"
    APIStatusError = FakeAPIStatusError
    APITimeoutError = FakeAPITimeoutError
    APIConnectionError = FakeAPIConnectionError


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 19, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def independence() -> VerifierIndependence:
    return VerifierIndependence(
        context_isolated=True, separate_model_call=True,
        different_model=False, different_provider=False,
        deterministic_checker=False, independently_implemented_checker=False,
        formal_kernel=False,
    )


class LoopCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.clock = MutableClock()
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.artifacts = FileArtifactStore(self.root / "artifacts")
        self.dossier = build_open_theorem_dossier()
        self.proposer_result, self.verifier_result = deterministic_fake_results(
            self.dossier.formalization.target_claim_id.value,
            self.dossier.formalization.assumption_claim_ids[0].value,
        )
        self.limits = BudgetLimits(
            max_input_tokens=20_000, max_output_tokens=4_000,
            max_cost_microusd=1000, max_wall_milliseconds=120_000,
            max_attempts=4,
        )

    def tearDown(self) -> None:
        self.workspace.close()
        self.temporary.cleanup()

    def loop(self, scripts: dict[str, list[ModelResult]], **kwargs: object) -> tuple[BaselineResearchLoop, ScriptedModelGateway]:
        gateway = ScriptedModelGateway(scripts)
        loop = BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=gateway, verifier=gateway, independence=independence(),
            now=self.clock, **kwargs,
        )
        return loop, gateway


class BaselineLoopTests(LoopCase):
    def test_deterministic_fake_end_to_end(self) -> None:
        before = export_dossier_bytes(self.dossier)
        loop, gateway = self.loop({"proposer": [self.proposer_result], "verifier": [self.verifier_result]})
        run = loop.start(run_id=oid("run.fake.e2e.v1"), dossier=self.dossier, limits=self.limits)
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.AWAITING_REVIEW)
        self.assertEqual(gateway.call_count, 2)
        self.assertEqual(export_dossier_bytes(self.workspace.load_dossier(final.dossier_id)), before)
        self.assertEqual(TrustPolicy(self.workspace.load_dossier(final.dossier_id)).target_resolution().logical_status, "unknown")
        self.assertEqual([item.disposition for item in self.workspace.list_proposals(run.run_id)], ["proposal", "proposal"])
        budget = self.workspace.budget(final.budget_id, now=final.updated_at)
        self.assertEqual((budget.used_input_tokens, budget.used_output_tokens, budget.used_cost_microusd), (280, 170, 0))
        calls = self.workspace.list_model_calls(run.run_id)
        self.assertEqual({item["provider"] for item in calls}, {"scripted"})
        self.assertEqual({item["model_identifier"] for item in calls}, {"scripted-v1"})
        self.assertTrue(all("structured_output" in item["capabilities_json"] for item in calls))

    def test_proposer_context_comes_from_accepted_dossier(self) -> None:
        loop, gateway = self.loop({"proposer": [self.proposer_result]})
        run = loop.start(run_id=oid("run.proposer.context.v1"), dossier=self.dossier, limits=self.limits)
        loop.advance(run.run_id)
        context = json.loads(gateway.requests[0].serialized_context)
        self.assertEqual(context["approved_target"]["id"], self.dossier.formalization.target_claim_id.value)
        self.assertEqual(context["accepted_premises"][0]["id"], self.dossier.formalization.assumption_claim_ids[0].value)
        self.assertTrue(context["verification_policy"]["models_cannot_award_warrants"])

    def test_run_finishes_awaiting_review_or_unresolved(self) -> None:
        loop, _ = self.loop({"proposer": [self.proposer_result], "verifier": [self.verifier_result]})
        run = loop.start(run_id=oid("run.terminal.v1"), dossier=self.dossier, limits=self.limits)
        self.assertIn(loop.run_to_terminal(run.run_id).status, {RunStatus.AWAITING_REVIEW, RunStatus.UNRESOLVED})

    def test_gateway_receives_value_request_only(self) -> None:
        loop, gateway = self.loop({"proposer": [self.proposer_result]})
        run = loop.start(run_id=oid("run.value-request.v1"), dossier=self.dossier, limits=self.limits)
        loop.advance(run.run_id)
        self.assertIsInstance(gateway.requests[0], ModelRequest)
        self.assertFalse(hasattr(gateway.requests[0], "workspace"))
        self.assertFalse(hasattr(gateway.requests[0], "repository"))

    def test_verifier_yields_finding_not_self_awarded_warrant(self) -> None:
        loop, _ = self.loop({"proposer": [self.proposer_result], "verifier": [self.verifier_result]})
        run = loop.start(run_id=oid("run.finding.v1"), dossier=self.dossier, limits=self.limits)
        loop.run_to_terminal(run.run_id)
        self.assertEqual(self.workspace.list_proposals(run.run_id)[1].proposal_kind, "verifier_finding")
        self.assertEqual(self.workspace.load_dossier(run.dossier_id).warrants, self.dossier.warrants)


class ModelBoundaryTests(LoopCase):
    def test_malformed_model_output_causes_no_domain_mutation(self) -> None:
        malformed = replace(self.proposer_result, structured_output="{not-json")
        loop, _ = self.loop({"proposer": [malformed]})
        before = export_dossier_bytes(self.dossier)
        run = loop.start(run_id=oid("run.malformed.v1"), dossier=self.dossier, limits=self.limits)
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.UNRESOLVED)
        self.assertEqual(self.workspace.list_proposals(run.run_id), ())
        self.assertEqual(export_dossier_bytes(self.workspace.load_dossier(final.dossier_id)), before)

    def test_refusal_is_explicit_non_success(self) -> None:
        refusal = replace(
            self.proposer_result, status=ModelResultStatus.REFUSED,
            structured_output=None, declared_rationale=None,
            refusal="I cannot provide this result.", retry_classification="not_retryable:refusal",
        )
        loop, _ = self.loop({"proposer": [refusal]})
        run = loop.start(run_id=oid("run.refusal.v1"), dossier=self.dossier, limits=self.limits)
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.UNRESOLVED)
        self.assertEqual(self.workspace.list_model_calls(run.run_id)[0]["status"], "refused")
        self.assertEqual(self.workspace.list_proposals(run.run_id), ())

    def test_proposer_output_cannot_award_a_warrant(self) -> None:
        value = json.loads(self.proposer_result.structured_output)
        value["warrant"] = {"kind": "formal_proof"}
        malicious = replace(self.proposer_result, structured_output=canonical_json(value))
        loop, _ = self.loop({"proposer": [malicious]})
        run = loop.start(run_id=oid("run.self-warrant.v1"), dossier=self.dossier, limits=self.limits)
        loop.run_to_terminal(run.run_id)
        replay = self.workspace.load_dossier(run.dossier_id)
        self.assertEqual(replay.warrants, self.dossier.warrants)
        self.assertEqual(self.workspace.list_proposals(run.run_id), ())

    def test_invalid_verifier_output_does_not_alter_claim_status(self) -> None:
        invalid = replace(self.verifier_result, structured_output='{"schema_version":"2.0.0","warrant":"formal_proof"}')
        loop, _ = self.loop({"proposer": [self.proposer_result], "verifier": [invalid]})
        run = loop.start(run_id=oid("run.invalid-verifier.v1"), dossier=self.dossier, limits=self.limits)
        final = loop.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.UNRESOLVED)
        self.assertEqual(TrustPolicy(self.workspace.load_dossier(run.dossier_id)).target_resolution().logical_status, "unknown")
        self.assertEqual(len(self.workspace.list_proposals(run.run_id)), 1)

    def test_only_structured_output_and_declared_rationale_are_retained(self) -> None:
        loop, _ = self.loop({"proposer": [self.proposer_result]})
        run = loop.start(run_id=oid("run.retention.v1"), dossier=self.dossier, limits=self.limits)
        loop.advance(run.run_id)
        call = self.workspace.list_model_calls(run.run_id)[0]
        retained = self.artifacts.get(call["result_hash"]).decode("utf-8")
        self.assertIn("declared_rationale", retained)
        self.assertNotIn("chain_of_thought", retained)
        self.assertNotIn("hidden_reasoning", retained)


class VerifierIsolationTests(LoopCase):
    def _completed(self, run_id: str = "run.isolation.v1"):
        loop, gateway = self.loop({"proposer": [self.proposer_result], "verifier": [self.verifier_result]})
        run = loop.start(run_id=oid(run_id), dossier=self.dossier, limits=self.limits)
        loop.run_to_terminal(run.run_id)
        return run, gateway

    def test_verifier_context_excludes_proposer_narrative_by_default(self) -> None:
        run, gateway = self._completed()
        context = json.loads(gateway.requests[1].serialized_context)
        text = gateway.requests[1].serialized_context
        self.assertNotIn("Direct use of the accepted definition", text)
        self.assertNotIn("declared_rationale", context["candidate"])
        self.assertNotIn("self_rating", text)
        self.assertEqual(set(context), {"schema_version", "purpose", "approved_target", "formalization", "semantic_alignment", "accepted_premises", "raw_evidence_and_source_spans", "candidate", "verification_policy"})

    def test_manifest_exactly_represents_serialized_context(self) -> None:
        run, gateway = self._completed("run.manifest.v1")
        manifest = self.workspace.get_manifest(run.run_id)
        serialized = gateway.requests[1].serialized_context.encode("utf-8")
        self.assertEqual(manifest.serialized_context_hash, sha256_bytes(serialized))
        self.assertEqual(manifest.context_artifact_hash, manifest.serialized_context_hash)
        self.assertEqual(self.artifacts.get(manifest.context_artifact_hash), serialized)
        self.assertEqual(set(item.value for item in gateway.requests[1].referenced_entity_ids), set(item.value for item in manifest.included_entity_ids))

    def test_same_model_is_context_isolated_not_fully_independent(self) -> None:
        run, _ = self._completed("run.independence.v1")
        value = self.workspace.get_manifest(run.run_id).independence
        self.assertTrue(value.context_isolated)
        self.assertTrue(value.separate_model_call)
        self.assertFalse(value.different_model)
        self.assertFalse(value.different_provider)
        self.assertFalse(value.fully_independent)

    def test_all_independence_dimensions_are_serialized(self) -> None:
        run, _ = self._completed("run.dimensions.v1")
        value = json.loads(canonical_json(self.workspace.get_manifest(run.run_id).independence))
        self.assertEqual(set(value) - {"schema_version"}, {"context_isolated", "separate_model_call", "different_model", "different_provider", "deterministic_checker", "independently_implemented_checker", "formal_kernel"})


class RecoveryTests(LoopCase):
    def test_retry_is_semantically_idempotent(self) -> None:
        loop, _ = self.loop({"proposer": [self.proposer_result], "verifier": [self.verifier_result]})
        run = loop.start(run_id=oid("run.retry.v1"), dossier=self.dossier, limits=self.limits)
        loop.run_to_terminal(run.run_id)
        loop.run_to_terminal(run.run_id)
        self.assertEqual(len(self.workspace.list_jobs(run.run_id)), 2)
        self.assertEqual(len(self.workspace.list_proposals(run.run_id)), 2)
        self.assertEqual(len(self.workspace.list_model_calls(run.run_id)), 2)
        event_types = [item["event_type"] for item in self.workspace.timeline(run.run_id)]
        self.assertEqual(event_types.count("proposal_imported"), 2)
        self.assertEqual(event_types.count("job_succeeded"), 2)
        replay = self.workspace.load_dossier(run.dossier_id)
        self.assertEqual(len(replay.evidence), len(self.dossier.evidence))
        self.assertEqual(len(replay.warrants), len(self.dossier.warrants))

    def test_orphan_artifact_retry_commits_once(self) -> None:
        loop, gateway = self.loop(
            {"proposer": [self.proposer_result, self.proposer_result], "verifier": [self.verifier_result]},
            fault_after_proposal_artifact_once=True,
        )
        run = loop.start(run_id=oid("run.crash.v1"), dossier=self.dossier, limits=self.limits)
        with self.assertRaises(InjectedCrash):
            loop.advance(run.run_id)
        self.assertEqual(self.workspace.list_proposals(run.run_id), ())
        self.clock.advance(31)
        self.workspace.close()
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.workspace.recover_jobs(now=self.clock().isoformat().replace("+00:00", "Z"))
        resumed = BaselineResearchLoop(
            workspace=self.workspace, artifacts=self.artifacts,
            proposer=gateway, verifier=gateway, independence=independence(), now=self.clock,
        )
        final = resumed.run_to_terminal(run.run_id)
        self.assertEqual(final.status, RunStatus.AWAITING_REVIEW)
        self.assertEqual(len(self.workspace.list_proposals(run.run_id)), 2)
        imported = [event for event in self.workspace.timeline(run.run_id) if event["event_type"] == "proposal_imported"]
        self.assertEqual(len(imported), 2)


class WorkflowBudgetAndCancellationTests(LoopCase):
    def test_exhausted_budget_prevents_gateway_call(self) -> None:
        loop, gateway = self.loop({"proposer": [self.proposer_result]})
        limits = replace(self.limits, max_input_tokens=1)
        run = loop.start(run_id=oid("run.no-budget.v1"), dossier=self.dossier, limits=limits)
        self.assertEqual(loop.run_to_terminal(run.run_id).status, RunStatus.UNRESOLVED)
        self.assertEqual(gateway.call_count, 0)

    def test_cancelled_job_cannot_commit_after_model_returns(self) -> None:
        loop, _ = self.loop({"proposer": [self.proposer_result]})
        run = loop.start(run_id=oid("run.cancel-late.v1"), dossier=self.dossier, limits=self.limits)
        loop.before_proposal_commit = lambda run_id: loop.cancel(run_id)
        loop.advance(run.run_id)
        self.assertEqual(self.workspace.get_run(run.run_id).status, RunStatus.CANCELLED)
        self.assertEqual(self.workspace.list_proposals(run.run_id), ())


class DurableReplayTests(LoopCase):
    def test_database_restart_preserves_canonical_meaning(self) -> None:
        loop, _ = self.loop({"proposer": [self.proposer_result], "verifier": [self.verifier_result]})
        run = loop.start(run_id=oid("run.restart.v1"), dossier=self.dossier, limits=self.limits)
        loop.run_to_terminal(run.run_id)
        before = (
            export_dossier_bytes(self.workspace.load_dossier(run.dossier_id)),
            self.workspace.timeline(run.run_id), self.workspace.list_proposals(run.run_id),
            TrustPolicy(self.workspace.load_dossier(run.dossier_id)).target_resolution(),
        )
        self.workspace.close()
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        after = (
            export_dossier_bytes(self.workspace.load_dossier(run.dossier_id)),
            self.workspace.timeline(run.run_id), self.workspace.list_proposals(run.run_id),
            TrustPolicy(self.workspace.load_dossier(run.dossier_id)).target_resolution(),
        )
        self.assertEqual(before, after)

    def test_timeline_is_reconstructed_from_events(self) -> None:
        loop, _ = self.loop({"proposer": [self.proposer_result], "verifier": [self.verifier_result]})
        run = loop.start(run_id=oid("run.timeline.v1"), dossier=self.dossier, limits=self.limits)
        loop.run_to_terminal(run.run_id)
        timeline = self.workspace.timeline(run.run_id)
        self.assertEqual([item["sequence"] for item in timeline], sorted(item["sequence"] for item in timeline))
        self.assertEqual(canonical_hash(timeline), canonical_hash(self.workspace.timeline(run.run_id)))

    def test_report_bytes_and_hash_are_reproducible(self) -> None:
        loop, _ = self.loop({"proposer": [self.proposer_result], "verifier": [self.verifier_result]})
        run = loop.start(run_id=oid("run.report.v1"), dossier=self.dossier, limits=self.limits)
        loop.run_to_terminal(run.run_id)
        first = render_durable_report(self.workspace, run.run_id)
        first_hash = report_hash(self.workspace, run.run_id)
        self.workspace.close()
        self.workspace = SQLiteWorkspace(self.root / "workspace.sqlite3")
        self.assertEqual(first, render_durable_report(self.workspace, run.run_id))
        self.assertEqual(first_hash, report_hash(self.workspace, run.run_id))


class ModelGatewayContractTests(unittest.TestCase):
    def test_scripted_and_live_adapter_share_contract(self) -> None:
        scripted = ScriptedModelGateway({})
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=False):
            live = OpenAIResponsesGateway(OpenAIProviderConfig(model_identifier="configured-model"))
        self.assertTrue(callable(scripted.complete))
        self.assertTrue(callable(live.complete))

    def test_scripted_gateway_is_deterministic(self) -> None:
        dossier = build_open_theorem_dossier()
        first, _ = deterministic_fake_results(dossier.formalization.target_claim_id.value, dossier.formalization.assumption_claim_ids[0].value)
        self.assertEqual(first, deterministic_fake_results(dossier.formalization.target_claim_id.value, dossier.formalization.assumption_claim_ids[0].value)[0])

    def test_secrets_never_enter_artifacts_events_or_metadata(self) -> None:
        secret = "sk-exampleSECRET123456"
        value = redact_secrets({"authorization": f"Bearer {secret}", "message": f"failed {secret}"}, (secret,))
        self.assertNotIn(secret, json.dumps(value))
        self.assertEqual(value["authorization"], "[REDACTED]")

    def _request(self) -> ModelRequest:
        template = PromptCatalog().load("proposer")
        return ModelRequest(
            request_id=oid("request.gateway.v1"), run_id=oid("run.gateway.v1"),
            purpose="proposer", template_id=template.template_id,
            template_version=template.version, template_hash=template.content_hash,
            template_text=template.text, serialized_context='{"bounded":true}',
            response_schema=Path("schemas/model-proposer-v1.schema.json").read_text(encoding="utf-8"),
            referenced_entity_ids=(oid("claim.even_sum.v1"),),
            timeout_milliseconds=500, max_output_tokens=256,
        )

    def test_usage_integer_cost_provider_metadata_and_bounded_request_are_normalized(self) -> None:
        dossier = build_open_theorem_dossier()
        proposer, _ = deterministic_fake_results(
            dossier.formalization.target_claim_id.value,
            dossier.formalization.assumption_claim_ids[0].value,
        )
        body = {
            "id": "response-test", "model": "configured-model-actual", "status": "completed",
            "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            "output": [{"content": [{"type": "output_text", "text": proposer.structured_output}]}],
        }
        captured: dict[str, object] = {}

        class Responses:
            def create(self, **payload):
                captured["payload"] = payload
                return body

        class Client:
            responses = Responses()

        def factory(**kwargs):
            captured["client"] = kwargs
            return Client()

        config = OpenAIProviderConfig(model_identifier="configured-model")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "not-retained"}, clear=False):
            result = OpenAIResponsesGateway(
                config, sdk_module=FakeOpenAISDK, client_factory=factory,
            ).complete(self._request())
        self.assertEqual(result.status, ModelResultStatus.SUCCEEDED)
        self.assertEqual(result.model_identifier, "configured-model-actual")
        self.assertEqual((result.usage.input_tokens, result.usage.output_tokens, result.usage.total_tokens), (2, 3, 5))
        self.assertIsNone(result.usage.estimated_cost_microusd)
        sent = captured["payload"]
        self.assertFalse(sent["store"])
        self.assertEqual(sent["max_output_tokens"], 256)
        self.assertTrue(sent["text"]["format"]["strict"])
        provider_schema = sent["text"]["format"]["schema"]
        self.assertNotIn("$schema", provider_schema)
        self.assertNotIn("uniqueItems", provider_schema["properties"]["referenced_entity_ids"])
        self.assertNotIn("reasoning", sent)
        self.assertNotIn("not-retained", json.dumps(sent))
        self.assertEqual(captured["client"]["max_retries"], 0)

    def test_timeout_and_retry_classification(self) -> None:
        config = OpenAIProviderConfig(model_identifier="configured-model")
        class Responses:
            def create(self, **payload):
                raise FakeAPITimeoutError()
        class Client:
            responses = Responses()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret"}, clear=False):
            result = OpenAIResponsesGateway(
                config, sdk_module=FakeOpenAISDK, client_factory=lambda **kwargs: Client(),
            ).complete(self._request())
        self.assertEqual(result.status, ModelResultStatus.TIMED_OUT)
        self.assertEqual(result.retry_classification, "retryable:timeout")


class PromptTemplateTests(unittest.TestCase):
    def test_template_version_and_hash_are_recorded(self) -> None:
        catalog = PromptCatalog()
        first = catalog.load("proposer")
        second = catalog.load("proposer")
        self.assertEqual(first, second)
        self.assertEqual(first.version, "1.0.0")
        self.assertEqual(first.content_hash, sha256_bytes(first.text.encode("utf-8")))


class LiveProviderConfigurationTests(unittest.TestCase):
    def test_live_adapter_is_opt_in_and_requires_environment_secret(self) -> None:
        gateway = OpenAIResponsesGateway(OpenAIProviderConfig(model_identifier="configured-model"))
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                gateway.complete(ModelGatewayContractTests()._request())
        self.assertNotIn("not-recorded-secret-value", repr(gateway.config))
