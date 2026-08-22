"""The live embedding adapter's provider boundary, exercised offline.

No network and no SDK: the `openai` client is injected. What is asserted is the
boundary, not the transport -- an embeddings response that reports completion
tokens, the wrong dimension, no usage, or more than one embedding is a refusal,
and the credential never reaches a persisted artifact.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from math_research.embedding.errors import EmbeddingError
from math_research.embedding.gateways import (
    EMBEDDING_ADAPTER_VERSION,
    OpenAIEmbeddingGateway,
    azure_openai_embedding_config,
    openai_embedding_config,
)
from math_research.embedding.records import EmbeddingRequest
from math_research.phase2.live_gate import scan_persisted_secret

REPO_ROOT = Path(__file__).resolve().parent.parent
EMBEDDING_PACKAGE = REPO_ROOT / "src/math_research/embedding"
CLI_MODULE = REPO_ROOT / "src/math_research/embedding_cli.py"
MODEL = "text-embedding-3-small"
SECRET = "sk-test-embedding-secret-value"


def _request(text: str = "the source text") -> EmbeddingRequest:
    return EmbeddingRequest(
        document_id="alpha-doc", source_id="source.alpha",
        source_content_hash="sha256:" + "0" * 64, text=text,
        processor_id="processor.openai.embeddings.v1",
        max_input_tokens=512, timeout_milliseconds=30_000,
    )


class _FakeEmbeddings:
    def __init__(self, response: dict[str, Any], calls: list[dict[str, Any]]) -> None:
        self._response = response
        self._calls = calls

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self._calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response: dict[str, Any], calls: list[dict[str, Any]], **kwargs: Any) -> None:
        self.arguments = kwargs
        self.embeddings = _FakeEmbeddings(response, calls)


def _gateway(response: dict[str, Any], *, azure: bool = False):
    calls: list[dict[str, Any]] = []
    clients: list[_FakeClient] = []

    def factory(**kwargs: Any) -> _FakeClient:
        client = _FakeClient(response, calls, **kwargs)
        clients.append(client)
        return client

    environment = {"OPENAI_API_KEY": SECRET}
    if azure:
        environment = {
            "AZURE_OPENAI_API_KEY": SECRET,
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
            "AZURE_OPENAI_DEPLOYMENT": "embeddings-deployment",
            "AZURE_OPENAI_API_VERSION": "2026-01-01",
        }
    config = (
        azure_openai_embedding_config(model_identifier=MODEL, dimension=3)
        if azure else openai_embedding_config(model_identifier=MODEL, dimension=3)
    )
    gateway = OpenAIEmbeddingGateway(
        config, sdk_module=object(), client_factory=factory, environment=environment,
    )
    return gateway, calls, clients


def _response(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "emb-request-1",
        "model": MODEL,
        "data": [{"embedding": [0.5, -0.25, 0.125], "index": 0}],
        "usage": {"prompt_tokens": 7, "total_tokens": 7},
    }
    payload.update(overrides)
    return payload


class AdapterSuccessTests(unittest.TestCase):
    def test_a_well_formed_response_is_accepted(self) -> None:
        gateway, calls, _ = _gateway(_response())
        result = gateway.embed(_request())
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.model_identifier, MODEL)
        self.assertEqual(result.provider_coordinates, (0.5, -0.25, 0.125))
        self.assertEqual(result.input_tokens, 7)
        self.assertEqual(result.output_tokens, 0)
        self.assertEqual(result.provider_request_id, "emb-request-1")
        self.assertEqual(calls[0]["model"], MODEL)
        self.assertEqual(calls[0]["input"], "the source text")

    def test_azure_supplies_deployment_scoped_settings(self) -> None:
        gateway, _, clients = _gateway(_response(), azure=True)
        gateway.embed(_request())
        arguments = clients[0].arguments
        self.assertEqual(arguments["azure_deployment"], "embeddings-deployment")
        self.assertEqual(arguments["api_version"], "2026-01-01")
        self.assertEqual(arguments["max_retries"], 0)
        self.assertNotIn("authorization", {key.lower() for key in arguments})

    def test_adapter_version_is_declared(self) -> None:
        self.assertTrue(EMBEDDING_ADAPTER_VERSION.startswith("openai-embeddings-adapter/"))


class AdapterRefusalTests(unittest.TestCase):
    def _refusal(self, response: dict[str, Any], code: str) -> None:
        gateway, _, _ = _gateway(response)
        with self.assertRaises(EmbeddingError) as caught:
            gateway.embed(_request())
        self.assertEqual(caught.exception.code, code)

    def test_completion_tokens_are_refused(self) -> None:
        self._refusal(
            _response(usage={"prompt_tokens": 7, "completion_tokens": 3}),
            "output_tokens_not_zero",
        )

    def test_reported_output_tokens_are_refused(self) -> None:
        self._refusal(
            _response(usage={"prompt_tokens": 7, "output_tokens": 1}),
            "output_tokens_not_zero",
        )

    def test_zero_completion_tokens_are_accepted(self) -> None:
        gateway, _, _ = _gateway(_response(usage={"prompt_tokens": 7, "completion_tokens": 0}))
        self.assertEqual(gateway.embed(_request()).input_tokens, 7)

    def test_absent_usage_is_refused(self) -> None:
        self._refusal(_response(usage=None), "embedding_usage_unavailable")

    def test_non_integer_input_tokens_are_refused(self) -> None:
        self._refusal(
            _response(usage={"prompt_tokens": "7"}), "embedding_usage_unavailable",
        )

    def test_wrong_dimension_is_refused(self) -> None:
        self._refusal(
            _response(data=[{"embedding": [0.5, 0.5]}]), "embedding_dimension_mismatch",
        )

    def test_more_than_one_embedding_is_refused(self) -> None:
        self._refusal(
            _response(data=[
                {"embedding": [0.5, 0.5, 0.5]}, {"embedding": [0.1, 0.1, 0.1]},
            ]),
            "embedding_response_malformed",
        )

    def test_missing_credential_is_refused_before_any_client_is_built(self) -> None:
        config = openai_embedding_config(model_identifier=MODEL, dimension=3)
        gateway = OpenAIEmbeddingGateway(
            config, sdk_module=object(),
            client_factory=lambda **kwargs: self.fail("client built without a key"),
            environment={},
        )
        with self.assertRaises(EmbeddingError) as caught:
            gateway.embed(_request())
        self.assertEqual(caught.exception.code, "embedding_credential_absent")

    def test_missing_azure_setting_is_refused(self) -> None:
        config = azure_openai_embedding_config(model_identifier=MODEL, dimension=3)
        gateway = OpenAIEmbeddingGateway(
            config, sdk_module=object(),
            client_factory=lambda **kwargs: self.fail("client built without settings"),
            environment={"AZURE_OPENAI_API_KEY": SECRET},
        )
        with self.assertRaises(EmbeddingError) as caught:
            gateway.embed(_request())
        self.assertEqual(caught.exception.code, "embedding_setting_absent")


class SecretContainmentTests(unittest.TestCase):
    def test_no_credential_reaches_a_persisted_artifact(self) -> None:
        from math_research.embedding.authoring import author_partition, load_authoring_spec

        gateway, _, _ = _gateway(_response())
        result = gateway.embed(_request())
        self.assertNotIn(SECRET, json.dumps(list(result.provider_coordinates)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            author_partition(root, load_authoring_spec(
                REPO_ROOT / "fixtures/embedding/fixture-synthetic-partition-v1.json"
            ))
            paths, fields = scan_persisted_secret(
                root, root.joinpath("absent.sqlite3"), SECRET,
            )
        self.assertEqual((paths, fields), ((), ()))


class GatedImportBoundaryTests(unittest.TestCase):
    """This package adds NO new declared gated import."""

    def _modules(self) -> list[Path]:
        return sorted(
            p for p in EMBEDDING_PACKAGE.rglob("*.py")
            if "__pycache__" not in p.parts
        ) + [CLI_MODULE]

    def test_no_module_here_dynamically_loads_a_third_party_module(self) -> None:
        offenders: list[str] = []
        for path in self._modules():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if name in {"import_module", "find_spec"}:
                    offenders.append(f"{path.name}:{node.lineno}")
        self.assertEqual(
            offenders, [],
            "the embedding slice must reach the openai SDK through "
            "phase2.model_gateway._load_openai_sdk, which is the single declared "
            "gated import; adding a load here would need a new "
            "GATED_DYNAMIC_IMPORTS entry and an ADR",
        )

    def test_no_module_here_imports_openai_at_any_nesting_level(self) -> None:
        offenders: list[str] = []
        for path in self._modules():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                for name in names:
                    if name.split(".", 1)[0] in {"openai", "anthropic", "httpx", "requests"}:
                        offenders.append(f"{path.name}:{node.lineno} {name}")
        self.assertEqual(offenders, [])

    def test_the_declared_gated_import_set_is_unchanged(self) -> None:
        completed = subprocess.run(
            [
                sys.executable, "-m", "unittest",
                "tests.test_repository_invariants."
                "StandardLibraryOnlyRuntimeTests."
                "test_dynamic_third_party_loads_are_declared_gated_boundaries",
            ],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=300,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
