from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from math_research.domain.entities import oid
from math_research.phase2.artifacts import FileArtifactStore
from math_research.phase2.baseline_loop import BaselineResearchLoop, deterministic_fake_results
from math_research.phase2.fixtures import build_open_theorem_dossier
from math_research.phase2.env_file import EnvFileError, load_repository_env
from math_research.phase2.live_config import (
    create_live_run_configuration,
    load_live_run_configuration,
    write_live_run_configuration,
)
from math_research.phase2.live_gate import LIVE_GATE_COMMAND_SHAPE, preflight_live_gate
from math_research.phase2.model_gateway import OpenAIProviderConfig, OpenAIResponsesGateway, ScriptedModelGateway, redact_secrets
from math_research.phase2.pricing import create_pricing_snapshot, load_pricing_snapshot, write_pricing_snapshot
from math_research.phase2.records import BudgetLimits, ModelRequest, ModelResultStatus, VerifierIndependence
from math_research.phase2.prompt_templates import PromptCatalog
from math_research.phase2.serialization import canonical_json
from math_research.phase2.sqlite_workspace import SQLiteWorkspace
from math_research.phase2_cli import main as phase2_main


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


def snapshot():
    return create_pricing_snapshot(
        snapshot_id=oid("pricing.openai.configured-model.2026-08-19"),
        provider="openai", model_identifier="configured-model",
        source="operator supplied pricing record", captured_at="2026-08-19T00:00:00Z",
        currency="USD", input_microusd_per_million_tokens=1_000_000,
        output_microusd_per_million_tokens=2_000_000,
    )


def configuration():
    return create_live_run_configuration(
        configuration_id=oid("config.live.acceptance.v1"), provider="openai",
        model_identifier="configured-model", pricing_snapshot_id=snapshot().snapshot_id,
        call_timeout_milliseconds=1_000, per_call_input_token_reserve=1_000,
        per_call_output_token_reserve=500,
        budget=BudgetLimits(
            max_input_tokens=2_000, max_output_tokens=1_000,
            max_cost_microusd=4_000, max_wall_milliseconds=2_000,
            max_attempts=2,
        ),
    )


class PricingAndConfigurationTests(unittest.TestCase):
    def test_versioned_snapshot_and_config_hash_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pricing_path = root / "pricing.json"
            config_path = root / "config.json"
            write_pricing_snapshot(snapshot(), pricing_path)
            write_live_run_configuration(configuration(), config_path)
            self.assertEqual(load_pricing_snapshot(pricing_path), snapshot())
            self.assertEqual(load_live_run_configuration(config_path), configuration())
            for schema in ("pricing-snapshot-v1.schema.json", "live-run-config-v1.schema.json"):
                self.assertIsInstance(json.loads((Path("schemas") / schema).read_text(encoding="utf-8")), dict)

    def test_preflight_checks_key_model_capability_budget_and_redaction(self) -> None:
        checked = preflight_live_gate(
            configuration(), snapshot(), environment={"OPENAI_API_KEY": "sk-preflight-example123"},
            installed_sdk_version="3.3.0",
        )
        self.assertTrue(checked.passed)
        self.assertEqual(checked.missing_variables, ())
        missing = preflight_live_gate(
            configuration(), snapshot(), environment={}, installed_sdk_version="3.3.0",
        )
        self.assertFalse(missing.passed)
        self.assertEqual(missing.missing_variables, ("OPENAI_API_KEY",))
        redacted = redact_secrets({"input_tokens": 3, "authorization": "Bearer sk-preflight-example123"}, ("sk-preflight-example123",))
        self.assertEqual(redacted["input_tokens"], 3)
        self.assertNotIn("sk-preflight-example123", canonical_json(redacted))

    def test_incomplete_configuration_prints_names_and_command_only(self) -> None:
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch("math_research.phase2_cli.load_repository_env"), redirect_stdout(output):
            status = phase2_main(["live-preflight"])
        value = json.loads(output.getvalue())
        self.assertEqual(status, 2)
        self.assertIn("OPENAI_API_KEY", value["missing_variables"])
        self.assertIn("config.model_identifier", value["missing_variables"])
        self.assertIn("pricing.source", value["missing_variables"])
        self.assertEqual(value["command_shape"], LIVE_GATE_COMMAND_SHAPE)
        self.assertEqual(set(value), {"missing_variables", "command_shape"})


class EnvFileTests(unittest.TestCase):
    def test_strict_env_file_loads_key_without_disclosing_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            secret = "sk-local-file-example123"
            path.write_text(f"# local only\nOPENAI_API_KEY='{secret}'\n", encoding="utf-8")
            path.chmod(0o600)
            environment: dict[str, str] = {}
            result = load_repository_env(path, environment=environment)
            self.assertTrue(result.credential_present)
            self.assertEqual(result.source, "env_file")
            self.assertEqual(environment["OPENAI_API_KEY"], secret)
            self.assertNotIn(secret, repr(result))

    def test_process_environment_wins_and_file_is_not_interpreted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("UNSUPPORTED=value\n", encoding="utf-8")
            environment = {"OPENAI_API_KEY": "existing-secret"}
            result = load_repository_env(path, environment=environment)
            self.assertEqual(result.source, "process_environment")
            self.assertEqual(environment["OPENAI_API_KEY"], "existing-secret")

    def test_insecure_or_general_dotenv_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaisesRegex(EnvFileError, "0600"):
                load_repository_env(path, environment={})
            path.chmod(0o600)
            path.write_text("OPENAI_API_KEY=secret\nMODEL=forbidden\n", encoding="utf-8")
            with self.assertRaisesRegex(EnvFileError, "unsupported"):
                load_repository_env(path, environment={})

    def test_secret_files_are_ignored_but_example_is_versioned(self) -> None:
        rules = Path(".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".env", rules)
        self.assertIn(".env.*", rules)
        self.assertIn("!.env.example", rules)
        self.assertEqual(
            [line for line in Path(".env.example").read_text(encoding="utf-8").splitlines() if line.startswith("OPENAI_API_KEY=")],
            ["OPENAI_API_KEY="],
        )


class LiveAdapterBoundaryTests(unittest.TestCase):
    def _request(self) -> ModelRequest:
        template = PromptCatalog().load("proposer")
        return ModelRequest(
            request_id=oid("request.incomplete.v1"), run_id=oid("run.incomplete.v1"),
            purpose="proposer", template_id=template.template_id,
            template_version=template.version, template_hash=template.content_hash,
            template_text=template.text, serialized_context='{"bounded":true}',
            response_schema=Path("schemas/model-proposer-v1.schema.json").read_text(encoding="utf-8"),
            referenced_entity_ids=(oid("claim.even_sum.v1"),),
            timeout_milliseconds=500, max_output_tokens=128,
        )

    def test_response_level_incomplete_is_explicit(self) -> None:
        body = {
            "id": "response-incomplete", "model": "configured-model",
            "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"},
            "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            "output": [],
        }

        class Responses:
            def create(self, **payload):
                return body
        class Client:
            responses = Responses()

        with patch.dict(os.environ, {"OPENAI_API_KEY": "not-retained"}, clear=True):
            result = OpenAIResponsesGateway(
                OpenAIProviderConfig(model_identifier="configured-model"),
                sdk_module=FakeOpenAISDK,
                client_factory=lambda **kwargs: Client(),
            ).complete(self._request())
        self.assertEqual(result.status, ModelResultStatus.INCOMPLETE)
        self.assertEqual(result.incomplete_reason, "max_output_tokens")
        self.assertEqual(result.provider_request_id, "response-incomplete")
        self.assertEqual(result.usage.total_tokens, 15)


class PricingPersistenceTests(unittest.TestCase):
    def test_actual_usage_and_snapshot_cost_estimate_are_separate_and_durable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dossier = build_open_theorem_dossier()
            proposer, verifier = deterministic_fake_results(
                dossier.formalization.target_claim_id.value,
                dossier.formalization.assumption_claim_ids[0].value,
            )
            gateway = ScriptedModelGateway({"proposer": [proposer], "verifier": [verifier]})
            pricing = snapshot()
            run_id = oid("run.priced.fixture.v1")
            with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
                workspace.save_pricing_snapshot(pricing, canonical_json=canonical_json(pricing), now="2026-08-19T00:00:00Z")
                loop = BaselineResearchLoop(
                    workspace=workspace, artifacts=FileArtifactStore(root / "artifacts"),
                    proposer=gateway, verifier=gateway,
                    independence=VerifierIndependence(
                        context_isolated=True, separate_model_call=True,
                        different_model=False, different_provider=False,
                        deterministic_checker=False, independently_implemented_checker=False,
                        formal_kernel=False,
                    ),
                    pricing_snapshot=pricing,
                )
                loop.start(run_id=run_id, dossier=dossier, limits=BudgetLimits(
                    max_input_tokens=20_000, max_output_tokens=4_000,
                    max_cost_microusd=20_000, max_wall_milliseconds=120_000,
                    max_attempts=4,
                ))
                loop.run_to_terminal(run_id)
                calls = workspace.list_model_calls(run_id)
                estimates = workspace.list_cost_estimates(run_id)
                self.assertEqual([call["total_tokens"] for call in calls], [200, 250])
                self.assertTrue(all(call["usage_source"] == "fixture" for call in calls))
                self.assertTrue(all(call["pricing_snapshot_id"] == pricing.snapshot_id.value for call in calls))
                self.assertEqual(len(estimates), 2)
                self.assertTrue(all(item["pricing_snapshot_id"] == pricing.snapshot_id.value for item in estimates))
            with SQLiteWorkspace(root / "workspace.sqlite3") as replayed:
                self.assertEqual(replayed.list_model_calls(run_id), calls)
                self.assertEqual(replayed.list_cost_estimates(run_id), estimates)
