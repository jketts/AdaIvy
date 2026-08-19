from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from math_research.domain.entities import oid
from math_research.phase2.artifacts import FileArtifactStore
from math_research.phase2.baseline_loop import BaselineResearchLoop, deterministic_fake_results
from math_research.phase2.fixtures import build_open_theorem_dossier
from math_research.phase2.live_gate import scan_persisted_secret
from math_research.phase2.model_gateway import (
    DIAGNOSTIC_TEXT_LIMIT_BYTES,
    OpenAIProviderConfig,
    OpenAIResponsesGateway,
    StructuredOutputError,
    validate_structured_output,
)
from math_research.phase2.openai_schema import (
    MAX_ENUM_VALUES,
    MAX_NESTING_DEPTH,
    MAX_OBJECT_PROPERTIES,
    MAX_SCHEMA_STRING_BUDGET,
    ProviderSchemaError,
    lint_openai_schema,
    project_openai_schema,
)
from math_research.phase2.records import BudgetLimits, ModelResultStatus, VerifierIndependence
from math_research.phase2.serialization import canonical_json, sha256_bytes
from math_research.phase2.sqlite_workspace import SQLiteWorkspace


CANONICAL_HASHES = {
    "proposer": "sha256:29a9a65656f50cecefd40b0f11ff8750e5d164549b85d153177bb13ac4a238ce",
    "verifier": "sha256:243155a597985e90a00d560cd1f4aa18e16e8ffcde29b6c163a9b1a0ea96652d",
}
V2_STATUS_HASH = "df2ac002e466e4439ebb7f3f1c3f246be4961d63b67c63f9a2d93dec63bbf248"
V3_STATUS_HASH = "c29c13d80164890d0b5d1d1fdca3eeac66c56300c9683a1c4087d7bc03c1ac05"
V2_FILE_HASHES = {
    "workspace.sqlite3": "4c1c402d142a33d6529fb3991cb18bab2513bcb13dd2eddd3b30af0ab76ad064",
    "artifacts/sha256/0b/0bc29da959cc274e19c46dfbebae70cce6525c6ebbf90a043a3a4628f3ab7fb9": "0bc29da959cc274e19c46dfbebae70cce6525c6ebbf90a043a3a4628f3ab7fb9",
    "artifacts/sha256/17/17ada13e33c2fef8949b6c4e27154cbbfb605e62a6d3af985ad11c8641af7a74": "17ada13e33c2fef8949b6c4e27154cbbfb605e62a6d3af985ad11c8641af7a74",
    "artifacts/sha256/29/295e849ba754d74f4e4ecc5324bd8f2d0a989ddba1641f5282fa0dcd37e2a2e7": "295e849ba754d74f4e4ecc5324bd8f2d0a989ddba1641f5282fa0dcd37e2a2e7",
    "artifacts/sha256/d1/d1a45d3cb73f27b26a55b937ed0175b691c9e78211947f55534de3055629399a": "d1a45d3cb73f27b26a55b937ed0175b691c9e78211947f55534de3055629399a",
    "artifacts/sha256/f7/f7bf4a51b43db5254549ceec0b3d7439f2088c8353924b9306feb7dbafc3a1b2": "f7bf4a51b43db5254549ceec0b3d7439f2088c8353924b9306feb7dbafc3a1b2",
    "artifacts/sha256/fb/fb2ba61e32e254dfb4a4b4d51e6792fad9bf67ab97d2ac819d660db0f078053c": "fb2ba61e32e254dfb4a4b4d51e6792fad9bf67ab97d2ac819d660db0f078053c",
}


class FakeAPIStatusError(Exception):
    def __init__(self, *, response, body, request_id: str = "req_failed_123") -> None:
        super().__init__("provider rejected request")
        self.status_code = 400
        self.response = response
        self.body = body
        self.request_id = request_id
        self.message = body.get("message")
        self.type = body.get("type")
        self.code = body.get("code")
        self.param = body.get("param")


class FakeAPITimeoutError(Exception):
    pass


class FakeAPIConnectionError(Exception):
    pass


class FakeOpenAISDK:
    __version__ = "3.3.0-test"
    APIStatusError = FakeAPIStatusError
    APITimeoutError = FakeAPITimeoutError
    APIConnectionError = FakeAPIConnectionError


def request_error(secret: str, *, padding: int = 0) -> tuple[FakeAPIStatusError, bytes]:
    body_value = {
        "error": {
            "message": f"Invalid schema; Authorization: Bearer {secret}",
            "type": "invalid_request_error",
            "code": "invalid_json_schema",
            "param": "text.format.schema",
            "authorization": f"Bearer {secret}",
        },
        "padding": "x" * padding,
    }
    body = json.dumps(body_value, separators=(",", ":")).encode("utf-8")

    class Response:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {secret}",
            "Set-Cookie": f"session={secret}",
        }

        def content(self):
            return body

    return FakeAPIStatusError(response=Response(), body=body_value["error"]), body


def independence() -> VerifierIndependence:
    return VerifierIndependence(
        context_isolated=True,
        separate_model_call=True,
        different_model=False,
        different_provider=False,
        deterministic_checker=False,
        independently_implemented_checker=False,
        formal_kernel=False,
    )


class OpenAISchemaProjectionTests(unittest.TestCase):
    def schema(self, purpose: str = "proposer") -> str:
        return Path(f"schemas/model-{purpose}-v1.schema.json").read_text(encoding="utf-8")

    def terminal_schema(self, terminal: dict[str, object]) -> str:
        return canonical_json({
            "type": "object",
            "properties": {"value": terminal},
            "required": ["value"],
            "additionalProperties": False,
        })

    def projected_terminal(self, terminal: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
        prepared = project_openai_schema(self.terminal_schema(terminal))
        provider = json.loads(prepared.provider_schema_json)
        manifest = json.loads(prepared.transformation_manifest_json)
        return provider["properties"]["value"], manifest

    def test_all_six_live_schema_terminals_receive_provider_only_string_types(self) -> None:
        expected = {
            "proposer": {
                "/properties/schema_version/type",
                "/properties/result_type/type",
            },
            "verifier": {
                "/properties/schema_version/type",
                "/properties/result_type/type",
                "/properties/findings/items/properties/outcome/type",
                "/properties/recommendation/type",
            },
        }
        observed: set[str] = set()
        for purpose, paths in expected.items():
            prepared = project_openai_schema(self.schema(purpose))
            provider = json.loads(prepared.provider_schema_json)
            self.assertEqual(
                provider["properties"]["schema_version"],
                {"type": "string", "const": "2.0.0"},
            )
            manifest = json.loads(prepared.transformation_manifest_json)
            additions = {
                item["path"]: item
                for item in manifest["transformations"]
                if item["operation"] == "add"
            }
            self.assertEqual(set(additions), paths)
            for path, entry in additions.items():
                observed.add(f"{purpose}:{path}")
                self.assertEqual(entry["keyword"], "type")
                self.assertEqual(entry["inferred_value"], "string")
                self.assertIn(entry["inference_source"], {"const", "enum"})
                self.assertRegex(entry["canonical_value_hash"], r"^sha256:[0-9a-f]{64}$")
                self.assertEqual(entry["reason"], "OpenAI strict-schema terminal typing")
                self.assertTrue(entry["provider_only"])
        self.assertEqual(len(observed), 6)

    def test_scalar_terminal_type_inference_and_numeric_merge_policy(self) -> None:
        cases = (
            ({"enum": ["a", "b"]}, "string"),
            ({"enum": [True, False]}, "boolean"),
            ({"enum": [1, 2]}, "integer"),
            ({"const": 1.25}, "number"),
            ({"enum": [1.25, 2.5]}, "number"),
            ({"enum": [1, 2.5]}, "number"),
        )
        for terminal, expected in cases:
            with self.subTest(terminal=terminal):
                projected, manifest = self.projected_terminal(terminal)
                self.assertEqual(projected["type"], expected)
                additions = [
                    item for item in manifest["transformations"]
                    if item["path"] == "/properties/value/type"
                ]
                self.assertEqual(len(additions), 1)
                self.assertEqual(additions[0]["inferred_value"], expected)
        boolean, _ = self.projected_terminal({"const": True})
        self.assertEqual(boolean["type"], "boolean")
        self.assertNotEqual(boolean["type"], "integer")

    def test_ambiguous_empty_null_object_and_array_terminals_fail_closed(self) -> None:
        cases = (
            ({"enum": []}, "empty_enum", "/properties/value/enum"),
            ({"enum": ["a", True]}, "heterogeneous_terminal_values", "/properties/value/enum"),
            ({"enum": [None]}, "terminal_type_not_inferable", "/properties/value/enum/0"),
            ({"const": {"x": 1}}, "terminal_type_not_inferable", "/properties/value/const"),
            ({"const": [1]}, "terminal_type_not_inferable", "/properties/value/const"),
        )
        for terminal, code, path in cases:
            with self.subTest(terminal=terminal):
                with self.assertRaises(ProviderSchemaError) as failure:
                    project_openai_schema(self.terminal_schema(terminal))
                matching = [item.path for item in failure.exception.report.issues if item.code == code]
                self.assertIn(path, matching)

    def test_explicit_terminal_type_is_retained_or_rejected_on_conflict(self) -> None:
        projected, manifest = self.projected_terminal({"type": "number", "enum": [1, 2.5]})
        self.assertEqual(projected["type"], "number")
        self.assertNotIn(
            "/properties/value/type",
            {item["path"] for item in manifest["transformations"]},
        )
        with self.assertRaises(ProviderSchemaError) as failure:
            project_openai_schema(self.terminal_schema({"type": "string", "enum": ["a", 2]}))
        self.assertIn(
            "/properties/value/enum/1",
            {item.path for item in failure.exception.report.issues if item.code == "terminal_value_type_conflict"},
        )

    def test_nested_properties_items_defs_anyof_and_resolved_refs_are_typed(self) -> None:
        canonical = canonical_json({
            "type": "object",
            "$defs": {"defined": {"const": "defined"}},
            "properties": {
                "direct": {"enum": ["a", "b"]},
                "array": {"type": "array", "items": {"const": 2.5}},
                "choice": {"anyOf": [{"const": True}, {"enum": [1, 2]}]},
                "reference": {"$ref": "#/$defs/defined"},
            },
            "required": ["direct", "array", "choice", "reference"],
            "additionalProperties": False,
        })
        provider = json.loads(project_openai_schema(canonical).provider_schema_json)
        self.assertEqual(provider["$defs"]["defined"]["type"], "string")
        self.assertEqual(provider["properties"]["direct"]["type"], "string")
        self.assertEqual(provider["properties"]["array"]["items"]["type"], "number")
        self.assertEqual(provider["properties"]["choice"]["anyOf"][0]["type"], "boolean")
        self.assertEqual(provider["properties"]["choice"]["anyOf"][1]["type"], "integer")
        self.assertEqual(provider["properties"]["reference"], {"$ref": "#/$defs/defined"})
        invalid = json.loads(canonical)
        invalid["properties"]["reference"]["$ref"] = "#/$defs/missing"
        with self.assertRaises(ProviderSchemaError) as failure:
            project_openai_schema(canonical_json(invalid))
        self.assertIn(
            "/properties/reference/$ref",
            {item.path for item in failure.exception.report.issues if item.code == "unresolved_ref"},
        )

    def test_linter_rejects_untyped_invalid_unions_and_non_finite_values(self) -> None:
        untyped = json.loads(self.terminal_schema({"enum": ["a"]}))
        _, issues = lint_openai_schema(untyped)
        self.assertIn(
            "/properties/value/type",
            {item.path for item in issues if item.code == "terminal_type_missing"},
        )
        invalid_union = json.loads(self.terminal_schema({"type": ["string", "integer"], "enum": ["a"]}))
        _, issues = lint_openai_schema(invalid_union)
        self.assertIn(
            "/properties/value/type",
            {item.path for item in issues if item.code == "unsupported_type_union"},
        )
        non_finite = json.loads(self.terminal_schema({"type": "number", "enum": [1.0]}))
        non_finite["properties"]["value"]["enum"][0] = float("inf")
        _, issues = lint_openai_schema(non_finite)
        self.assertIn(
            "/properties/value/enum/0",
            {item.path for item in issues if item.code == "non_finite_number"},
        )
        multiple = {
            "type": "object",
            "properties": {
                "first": {"enum": ["a"]},
                "second": {"const": True},
            },
            "required": ["first", "second"],
            "additionalProperties": False,
        }
        _, issues = lint_openai_schema(multiple)
        self.assertEqual(
            {item.path for item in issues if item.code == "terminal_type_missing"},
            {"/properties/first/type", "/properties/second/type"},
        )

    def test_unique_items_is_projected_out_but_enforced_canonically(self) -> None:
        prepared = project_openai_schema(self.schema())
        provider = json.loads(prepared.provider_schema_json)
        self.assertNotIn("uniqueItems", provider["properties"]["referenced_entity_ids"])
        manifest = json.loads(prepared.transformation_manifest_json)
        removed = {(item["path"], item["canonical_post_validation_rule"]) for item in manifest["transformations"]}
        self.assertIn(
            ("/properties/referenced_entity_ids/uniqueItems", "canonical.array.unique_items"),
            removed,
        )
        candidate = {
            "schema_version": "2.0.0",
            "result_type": "candidate_claim",
            "target_claim_id": "claim.even_sum.v1",
            "mathematical_payload": {"statement": "x", "steps": [], "witness": None},
            "declared_rationale": "",
            "referenced_entity_ids": ["claim.even_sum.v1", "claim.even_sum.v1"],
        }
        with self.assertRaisesRegex(StructuredOutputError, "unique"):
            validate_structured_output("proposer", canonical_json(candidate))

    def test_nested_objects_are_closed_and_all_properties_required(self) -> None:
        for purpose in ("proposer", "verifier"):
            provider = json.loads(project_openai_schema(self.schema(purpose)).provider_schema_json)
            self._assert_object_rules(provider)

    def _assert_object_rules(self, node: dict[str, object]) -> None:
        declared = node.get("type")
        types = declared if isinstance(declared, list) else [declared]
        if "object" in types:
            properties = node["properties"]
            self.assertFalse(node["additionalProperties"])
            self.assertEqual(sorted(node["required"]), sorted(properties))
            for child in properties.values():
                self._assert_object_rules(child)
        if "items" in node:
            self._assert_object_rules(node["items"])
        for child in node.get("anyOf", []):
            self._assert_object_rules(child)

    def test_optional_property_becomes_required_nullable(self) -> None:
        canonical = canonical_json({
            "type": "object",
            "properties": {"optional": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        })
        prepared = project_openai_schema(canonical)
        provider = json.loads(prepared.provider_schema_json)
        self.assertEqual(provider["required"], ["optional"])
        self.assertEqual(provider["properties"]["optional"]["type"], ["string", "null"])
        manifest = json.loads(prepared.transformation_manifest_json)
        self.assertIn(
            "/properties/optional/type",
            {item["path"] for item in manifest["transformations"]},
        )

    def test_root_anyof_and_unsupported_keyword_report_exact_paths(self) -> None:
        with self.assertRaises(ProviderSchemaError) as root:
            project_openai_schema(canonical_json({"anyOf": [{"type": "object"}]}))
        self.assertIn("/anyOf", {item.path for item in root.exception.report.issues})
        invalid = canonical_json({
            "type": "object",
            "properties": {"value": {"type": "string", "oneOf": [{"type": "string"}]}},
            "required": ["value"],
            "additionalProperties": False,
        })
        with self.assertRaises(ProviderSchemaError) as unsupported:
            project_openai_schema(invalid)
        self.assertEqual(
            [item.path for item in unsupported.exception.report.issues if item.code == "unsupported_keyword"],
            ["/properties/value/oneOf"],
        )

    def test_depth_and_property_limits_are_enforced(self) -> None:
        node: dict[str, object] = {"type": "string"}
        for index in range(MAX_NESTING_DEPTH + 1):
            name = f"level_{index}"
            node = {
                "type": "object", "properties": {name: node},
                "required": [name], "additionalProperties": False,
            }
        with self.assertRaises(ProviderSchemaError) as deep:
            project_openai_schema(canonical_json(node))
        self.assertIn("nesting_limit_exceeded", {item.code for item in deep.exception.report.issues})
        properties = {f"p{index}": {"type": "string"} for index in range(MAX_OBJECT_PROPERTIES + 1)}
        large = {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
        with self.assertRaises(ProviderSchemaError) as wide:
            project_openai_schema(canonical_json(large))
        self.assertIn("property_limit_exceeded", {item.code for item in wide.exception.report.issues})

    def test_enum_and_schema_string_budgets_are_enforced(self) -> None:
        enum_schema = {
            "type": "object",
            "properties": {"value": {"enum": list(range(MAX_ENUM_VALUES + 1))}},
            "required": ["value"],
            "additionalProperties": False,
        }
        with self.assertRaises(ProviderSchemaError) as enum_error:
            project_openai_schema(canonical_json(enum_schema))
        self.assertIn("enum_limit_exceeded", {item.code for item in enum_error.exception.report.issues})
        long_name = "x" * (MAX_SCHEMA_STRING_BUDGET + 1)
        string_schema = {
            "type": "object",
            "properties": {long_name: {"type": "string"}},
            "required": [long_name],
            "additionalProperties": False,
        }
        with self.assertRaises(ProviderSchemaError) as string_error:
            project_openai_schema(canonical_json(string_schema))
        self.assertIn("string_budget_exceeded", {item.code for item in string_error.exception.report.issues})

    def test_projection_is_deterministic_and_canonical_schemas_are_unchanged(self) -> None:
        for purpose, expected_hash in CANONICAL_HASHES.items():
            path = Path(f"schemas/model-{purpose}-v1.schema.json")
            before = path.read_bytes()
            first = project_openai_schema(before.decode("utf-8"))
            second = project_openai_schema(before.decode("utf-8"))
            self.assertEqual(first, second)
            self.assertEqual(first.transformation_manifest_json, second.transformation_manifest_json)
            self.assertEqual(first.compatibility_report_json, second.compatibility_report_json)
            self.assertEqual(first.compatibility_report_text, second.compatibility_report_text)
            self.assertEqual(first.canonical_schema_hash, expected_hash)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sha256_bytes(path.read_bytes()), expected_hash)


class ProviderDiagnosticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.secret = "sk-providerBoundarySecret123456"
        self.dossier = build_open_theorem_dossier()

    def request(self):
        from math_research.phase2.prompt_templates import PromptCatalog
        from math_research.phase2.records import ModelRequest

        template = PromptCatalog().load("proposer")
        return ModelRequest(
            request_id=oid("request.provider.diagnostic.v1"),
            run_id=oid("run.provider.diagnostic.v1"),
            purpose="proposer",
            template_id=template.template_id,
            template_version=template.version,
            template_hash=template.content_hash,
            template_text=template.text,
            serialized_context='{"bounded":true}',
            response_schema=Path("schemas/model-proposer-v1.schema.json").read_text(encoding="utf-8"),
            referenced_entity_ids=(self.dossier.formalization.target_claim_id,),
            timeout_milliseconds=500,
            max_output_tokens=128,
        )

    def gateway(self, error: FakeAPIStatusError, captured: dict[str, object]) -> OpenAIResponsesGateway:
        class Responses:
            def create(inner_self, **payload):
                captured["calls"] = int(captured.get("calls", 0)) + 1
                captured["payload"] = payload
                raise error

        class Client:
            responses = Responses()

        def factory(**kwargs):
            captured["client"] = kwargs
            return Client()

        return OpenAIResponsesGateway(
            OpenAIProviderConfig(model_identifier="configured-model"),
            sdk_module=FakeOpenAISDK,
            client_factory=factory,
        )

    def test_sanitized_http_400_retains_request_id_full_hash_and_bounded_body(self) -> None:
        error, full_body = request_error(self.secret, padding=DIAGNOSTIC_TEXT_LIMIT_BYTES * 2)
        captured: dict[str, object] = {}
        with patch.dict(os.environ, {"OPENAI_API_KEY": self.secret}, clear=True):
            result = self.gateway(error, captured).complete(self.request())
        self.assertEqual(result.status, ModelResultStatus.FAILED)
        self.assertEqual(result.retry_classification, "fatal:http_400")
        self.assertEqual(result.provider_request_id, "req_failed_123")
        diagnostic = result.provider_failure
        self.assertIsNotNone(diagnostic)
        assert diagnostic is not None
        self.assertEqual(diagnostic.http_status_code, 400)
        self.assertEqual(diagnostic.sdk_exception_class, "FakeAPIStatusError")
        self.assertEqual(diagnostic.provider_request_id, "req_failed_123")
        self.assertEqual(diagnostic.provider_error_type, "invalid_request_error")
        self.assertEqual(diagnostic.provider_error_code, "invalid_json_schema")
        self.assertEqual(diagnostic.provider_error_param, "text.format.schema")
        self.assertEqual(diagnostic.response_content_type, "application/json; charset=utf-8")
        self.assertEqual(diagnostic.response_body_sha256, sha256_bytes(full_body))
        self.assertEqual(diagnostic.response_body_byte_length, len(full_body))
        self.assertTrue(diagnostic.response_body_preview_truncated)
        self.assertLessEqual(len(diagnostic.response_body_preview.encode("utf-8")), DIAGNOSTIC_TEXT_LIMIT_BYTES)
        retained = canonical_json(result)
        self.assertNotIn(self.secret, retained)
        self.assertNotIn("Set-Cookie", retained)
        self.assertNotIn("session=", retained)
        self.assertEqual(captured["calls"], 1)
        self.assertEqual(captured["client"]["max_retries"], 0)

    def test_failed_call_debits_no_usage_creates_no_proposal_and_never_calls_verifier(self) -> None:
        error, _ = request_error(self.secret)
        captured: dict[str, object] = {}
        gateway = self.gateway(error, captured)
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"OPENAI_API_KEY": self.secret}, clear=True,
        ):
            root = Path(temporary)
            artifacts = FileArtifactStore(root / "artifacts")
            with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
                loop = BaselineResearchLoop(
                    workspace=workspace,
                    artifacts=artifacts,
                    proposer=gateway,
                    verifier=gateway,
                    independence=independence(),
                )
                run = loop.start(
                    run_id=oid("run.provider.http400.v1"),
                    dossier=self.dossier,
                    limits=BudgetLimits(
                        max_input_tokens=10_000,
                        max_output_tokens=2_000,
                        max_cost_microusd=10_000,
                        max_wall_milliseconds=60_000,
                        max_attempts=2,
                    ),
                )
                loop.run_to_terminal(run.run_id)
                budget = workspace.budget(run.budget_id, now=workspace.get_run(run.run_id).updated_at)
                self.assertEqual((budget.used_input_tokens, budget.used_output_tokens, budget.used_cost_microusd), (0, 0, 0))
                self.assertEqual(budget.used_attempts, 1)
                self.assertEqual(len(workspace.list_model_calls(run.run_id)), 1)
                self.assertEqual(workspace.list_proposals(run.run_id), ())
                call = workspace.list_model_calls(run.run_id)[0]
                result_bytes = artifacts.get(call["result_hash"])
                self.assertNotIn(self.secret.encode("utf-8"), result_bytes)
                self.assertIn(b"req_failed_123", result_bytes)
                self.assertEqual(call["provider_request_id"], "req_failed_123")
            self.assertEqual(
                scan_persisted_secret(root, root / "workspace.sqlite3", self.secret),
                ((), ()),
            )
        self.assertEqual(captured["calls"], 1)

    def test_v2_workspace_status_request_id_and_diagnostics_remain_unchanged(self) -> None:
        status_path = Path("reports/phase-2/live-provider-status.json")
        self.assertEqual(hashlib.sha256(status_path.read_bytes()).hexdigest(), V3_STATUS_HASH)
        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "passed")
        self.assertEqual(len(status["history"]), 1)
        v2_status = status["history"][0]
        reconstructed = (json.dumps(v2_status, indent=2, sort_keys=True) + "\n").encode("utf-8")
        self.assertEqual(hashlib.sha256(reconstructed).hexdigest(), V2_STATUS_HASH)
        self.assertEqual(v2_status["status"], "failed")
        self.assertEqual(v2_status["calls_recorded"], 1)
        self.assertEqual(v2_status["response_ids"], ["req_32c9c66a4fb1414292df36cb4c031aad"])
        self.assertEqual(v2_status["history"][0]["status"], "failed")
        self.assertEqual(v2_status["history"][0]["history"][0]["status"], "blocked")
        root = Path("reports/phase-2/live-openai-gpt5-mini-v2")
        self.assertEqual(
            {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()},
            set(V2_FILE_HASHES),
        )
        for relative, expected in V2_FILE_HASHES.items():
            self.assertEqual(hashlib.sha256((root / relative).read_bytes()).hexdigest(), expected)


class ProviderPreflightWorkflowTests(unittest.TestCase):
    def test_incompatible_schema_fails_before_budget_and_network(self) -> None:
        dossier = build_open_theorem_dossier()
        captured = {"factory_calls": 0}

        def factory(**kwargs):
            captured["factory_calls"] += 1
            raise AssertionError("network client must not be constructed")

        gateway = OpenAIResponsesGateway(
            OpenAIProviderConfig(model_identifier="configured-model"),
            sdk_module=FakeOpenAISDK,
            client_factory=factory,
        )
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"OPENAI_API_KEY": "sk-local-only-example"}, clear=True,
        ):
            root = Path(temporary)
            schemas = root / "schemas"
            schemas.mkdir()
            invalid = json.loads(Path("schemas/model-proposer-v1.schema.json").read_text(encoding="utf-8"))
            invalid["properties"]["result_type"]["type"] = "boolean"
            (schemas / "model-proposer-v1.schema.json").write_text(canonical_json(invalid), encoding="utf-8")
            (schemas / "model-verifier-v1.schema.json").write_bytes(Path("schemas/model-verifier-v1.schema.json").read_bytes())
            with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
                loop = BaselineResearchLoop(
                    workspace=workspace,
                    artifacts=FileArtifactStore(root / "artifacts"),
                    proposer=gateway,
                    verifier=gateway,
                    independence=independence(),
                    schema_dir=schemas,
                )
                run = loop.start(
                    run_id=oid("run.provider.preflight.reject.v1"),
                    dossier=dossier,
                    limits=BudgetLimits(
                        max_input_tokens=10_000,
                        max_output_tokens=2_000,
                        max_cost_microusd=10_000,
                        max_wall_milliseconds=60_000,
                        max_attempts=2,
                    ),
                )
                loop.run_to_terminal(run.run_id)
                budget = workspace.budget(run.budget_id, now=workspace.get_run(run.run_id).updated_at)
                self.assertEqual(budget.used_attempts, 0)
                self.assertEqual(workspace.list_proposals(run.run_id), ())
                calls = workspace.list_model_calls(run.run_id)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0]["retry_classification"], "fatal:provider_schema_incompatible")
        self.assertEqual(captured["factory_calls"], 0)

    def test_duplicate_provider_output_imports_nothing_and_skips_verifier(self) -> None:
        dossier = build_open_theorem_dossier()
        proposer, verifier = deterministic_fake_results(
            dossier.formalization.target_claim_id.value,
            dossier.formalization.assumption_claim_ids[0].value,
        )
        value = json.loads(proposer.structured_output)
        value["referenced_entity_ids"] = [
            dossier.formalization.target_claim_id.value,
            dossier.formalization.target_claim_id.value,
        ]
        responses = [
            {
                "id": "response-proposer",
                "model": "configured-model",
                "status": "completed",
                "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
                "output": [{"content": [{"type": "output_text", "text": canonical_json(value)}]}],
            },
            {
                "id": "response-verifier",
                "model": "configured-model",
                "status": "completed",
                "usage": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
                "output": [{"content": [{"type": "output_text", "text": verifier.structured_output}]}],
            },
        ]
        observed = {"calls": 0}

        class ResponseAPI:
            def create(self, **payload):
                index = observed["calls"]
                observed["calls"] += 1
                return responses[index]

        class Client:
            responses = ResponseAPI()

        gateway = OpenAIResponsesGateway(
            OpenAIProviderConfig(model_identifier="configured-model"),
            sdk_module=FakeOpenAISDK,
            client_factory=lambda **kwargs: Client(),
        )
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"OPENAI_API_KEY": "sk-local-only-example"}, clear=True,
        ):
            root = Path(temporary)
            with SQLiteWorkspace(root / "workspace.sqlite3") as workspace:
                loop = BaselineResearchLoop(
                    workspace=workspace,
                    artifacts=FileArtifactStore(root / "artifacts"),
                    proposer=gateway,
                    verifier=gateway,
                    independence=independence(),
                )
                run = loop.start(
                    run_id=oid("run.provider.duplicate.v1"),
                    dossier=dossier,
                    limits=BudgetLimits(
                        max_input_tokens=10_000,
                        max_output_tokens=2_000,
                        max_cost_microusd=10_000,
                        max_wall_milliseconds=60_000,
                        max_attempts=2,
                    ),
                )
                loop.run_to_terminal(run.run_id)
                self.assertEqual(workspace.list_proposals(run.run_id), ())
                self.assertEqual(len(workspace.list_model_calls(run.run_id)), 1)
        self.assertEqual(observed["calls"], 1)


if __name__ == "__main__":
    unittest.main()
