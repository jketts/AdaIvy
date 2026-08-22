"""The `embedding` CLI surface.

`author`, `replay` and `probes` are the offline surface and must reach no
provider. `ingest` is the live surface: without `--execute` it emits a
not-executed plan, and with `--execute` it refuses without the exact
acknowledgement string.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from math_research.cli import main as cli_main
from math_research.domain.entities import OpaqueId
from math_research.embedding.constants import LIVE_EMBEDDING_ACKNOWLEDGEMENT
from math_research.embedding.run_config import (
    EmbeddingBudget,
    create_embedding_run_configuration,
    write_embedding_run_configuration,
)
from math_research.embedding_cli import main as embedding_main
from math_research.phase2.pricing import create_pricing_snapshot, write_pricing_snapshot

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "fixtures/embedding/fixture-synthetic-partition-v1.json"
KEY_ARGUMENTS = (
    "--provider", "fixture_synthetic",
    "--model-identifier", "adaivy-cooccurrence-anchor-v1",
    "--dimension", "32",
    "--normalization", "round_half_even_scale_2p30",
)


class CliMixin(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(prefix="adaivy-embedding-cli.")
        self.addCleanup(self._temporary.cleanup)
        self.workspace = Path(self._temporary.name)

    def run_cli(self, argv: list[str]) -> tuple[int, dict]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = embedding_main(argv)
        text = buffer.getvalue().strip()
        return code, json.loads(text) if text else {}


class OfflineSurfaceTests(CliMixin):
    def test_author_then_replay_agree_on_the_manifest_hash(self) -> None:
        root = self.workspace.joinpath("vectors")
        code, authored = self.run_cli(
            ["author", str(FIXTURE), "--root", str(root)]
        )
        self.assertEqual(code, 0)
        self.assertEqual(authored["corpus_provenance"], "project_authored")
        self.assertEqual(authored["provider_calls"], 0)
        self.assertEqual(authored["network_requests"], 0)
        self.assertEqual(authored["vector_count"], 5)
        self.assertEqual(authored["query_ids"], ["probe-spectral-query"])
        code, replayed = self.run_cli(
            ["replay", "--root", str(root), *KEY_ARGUMENTS,
             "--expect-manifest-hash", authored["manifest_hash"]]
        )
        self.assertEqual(code, 0)
        self.assertEqual(replayed["manifest_hash"], authored["manifest_hash"])

    def test_replay_of_an_absent_partition_fails_closed(self) -> None:
        from math_research.embedding.errors import PartitionAbsentError

        with self.assertRaises(PartitionAbsentError):
            self.run_cli(
                ["replay", "--root", str(self.workspace.joinpath("nothing")),
                 *KEY_ARGUMENTS]
            )

    def test_author_is_idempotent_and_writes_identical_bytes(self) -> None:
        root = self.workspace.joinpath("vectors")
        first_code, first = self.run_cli(["author", str(FIXTURE), "--root", str(root)])
        second_code, second = self.run_cli(["author", str(FIXTURE), "--root", str(root)])
        self.assertEqual((first_code, second_code), (0, 0))
        self.assertEqual(first["manifest_hash"], second["manifest_hash"])

    def test_probes_verb_gates_on_every_probe_flipping(self) -> None:
        code, payload = self.run_cli(["probes"])
        self.assertEqual(code, 0)
        self.assertEqual(payload["probes_flipped"], payload["probes_total"])

    def test_the_top_level_cli_dispatches_the_subcommand(self) -> None:
        root = self.workspace.joinpath("dispatch")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli_main(["embedding", "author", str(FIXTURE), "--root", str(root)])
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(buffer.getvalue())["partition_key"]["provider"],
            "fixture_synthetic",
        )


class LiveSurfaceTests(CliMixin):
    def _configuration_paths(self) -> tuple[Path, Path, Path]:
        pricing = create_pricing_snapshot(
            snapshot_id=OpaqueId("pricing.embedding.cli.v1"),
            provider="openai", model_identifier="text-embedding-3-small",
            source="project-authored CLI test rate",
            captured_at="2026-08-22T00:00:00Z", currency="USD",
            input_microusd_per_million_tokens=20_000,
            output_microusd_per_million_tokens=0,
        )
        configuration = create_embedding_run_configuration(
            configuration_id="config.embedding.cli.v1",
            provider="openai", model_identifier="text-embedding-3-small",
            dimension=4, normalization="round_half_even_scale_2p30",
            processor_id="processor.openai.embeddings.v1",
            pricing_snapshot_id=pricing.snapshot_id.value,
            call_timeout_milliseconds=30_000,
            per_call_input_token_reserve=512,
            budget=EmbeddingBudget(
                max_calls=4, max_input_tokens=2_048, max_cost_microusd=100_000,
            ),
        )
        config_path = self.workspace.joinpath("config.json")
        pricing_path = self.workspace.joinpath("pricing.json")
        documents_path = self.workspace.joinpath("documents.json")
        write_embedding_run_configuration(configuration, config_path)
        write_pricing_snapshot(pricing, pricing_path)
        documents_path.write_text(
            json.dumps([{"document_id": "alpha-doc", "source_id": "source.alpha"}]),
            encoding="utf-8",
        )
        return config_path, pricing_path, documents_path

    def test_without_execute_the_plan_calls_nothing(self) -> None:
        config, pricing, documents = self._configuration_paths()
        code, plan = self.run_cli([
            "ingest", str(config), str(pricing), str(documents),
            "--corpus-root", str(self.workspace.joinpath("corpus")),
            "--phase4a-workspace", str(self.workspace.joinpath("phase4a")),
            "--root", str(self.workspace.joinpath("vectors")),
            "--run-id", "run.cli.v1", "--recorded-at", "2026-08-22T00:00:00Z",
        ])
        self.assertEqual(code, 0)
        self.assertEqual(plan["execution_status"], "not_executed")
        self.assertEqual(plan["provider_calls"], 0)
        self.assertEqual(plan["network_requests"], 0)
        self.assertEqual(plan["output_tokens"], 0)
        self.assertEqual(
            plan["required_acknowledgement"], LIVE_EMBEDDING_ACKNOWLEDGEMENT,
        )
        self.assertFalse(self.workspace.joinpath("vectors").exists())
        self.assertFalse(self.workspace.joinpath("phase4a").exists())

    def test_execute_without_the_exact_acknowledgement_is_refused(self) -> None:
        config, pricing, documents = self._configuration_paths()
        for candidate in ("", "yes", LIVE_EMBEDDING_ACKNOWLEDGEMENT.lower()):
            with self.subTest(candidate=candidate):
                with self.assertRaises(SystemExit) as caught:
                    self.run_cli([
                        "ingest", str(config), str(pricing), str(documents),
                        "--corpus-root", str(self.workspace.joinpath("corpus")),
                        "--phase4a-workspace", str(self.workspace.joinpath("phase4a")),
                        "--root", str(self.workspace.joinpath("vectors")),
                        "--run-id", "run.cli.v1",
                        "--recorded-at", "2026-08-22T00:00:00Z",
                        "--execute", "--confirm-live-embedding", candidate,
                    ])
                self.assertEqual(caught.exception.code, 2)
                self.assertFalse(self.workspace.joinpath("vectors").exists())


if __name__ == "__main__":
    unittest.main()
