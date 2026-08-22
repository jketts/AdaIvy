from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from math_research.corpus.activation import (
    STATUS_PENDING,
    load_production_activation,
)
from math_research.corpus.constants import (
    MAX_CONCURRENT_CONNECTIONS,
    MIN_REQUEST_INTERVAL_MILLISECONDS,
    TRANCHE_MAX_RECORDS,
)
from math_research.corpus.errors import ActivationNotActiveError
from math_research.corpus.probes import PROBES, run_probes
from math_research.corpus.projection import verify_projection
from math_research.corpus.report import verify_report
from math_research.corpus.tranche import load_plan
from math_research.corpus_cli import main


ROOT = Path(__file__).resolve().parents[1]
ACTIVATION = ROOT / "config/corpus-arxiv-metadata-activation-v1.json"
PLAN = ROOT / "fixtures/corpus/fixture-tranche-plan-v1.json"
STORE = ROOT / "fixtures/corpus/store-v1"
EXPECTED_MANIFEST_HASH = (
    "sha256:c1f13ba27e6b3b7abc073683941994a7df023fd1d93e42629f65dfc3e1414bd9"
)


class CorpusAcceptanceTests(unittest.TestCase):
    def test_production_activation_is_pending_and_bounds_are_pinned(self) -> None:
        activation = load_production_activation(ACTIVATION.read_bytes())
        self.assertEqual(STATUS_PENDING, activation["status"])
        self.assertEqual(3_000, MIN_REQUEST_INTERVAL_MILLISECONDS)
        self.assertEqual(1, MAX_CONCURRENT_CONNECTIONS)
        self.assertEqual(2_040, TRANCHE_MAX_RECORDS)
        self.assertFalse(activation["full_text_authorized"])
        self.assertFalse(activation["retrieval_corpus_wired"])

    def test_fixture_plan_and_manifest_hash_are_literal_pins(self) -> None:
        plan = load_plan(PLAN.read_bytes())
        self.assertEqual(6, plan["max_records"])
        manifest = json.loads((STORE / "manifest.json").read_text())
        self.assertEqual(EXPECTED_MANIFEST_HASH, manifest["content_hash"])

    def test_all_named_probes_flip(self) -> None:
        result = run_probes()
        self.assertEqual(29, len(PROBES))
        self.assertEqual(result["probes_total"], result["probes_flipped"])
        self.assertEqual([], result["unflipped_probe_ids"])

    def test_cli_dry_run_makes_no_network_or_process_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch("socket.socket", side_effect=AssertionError("network")),
                patch("socket.create_connection", side_effect=AssertionError("network")),
                patch("socket.getaddrinfo", side_effect=AssertionError("dns")),
                patch("subprocess.Popen", side_effect=AssertionError("process")),
            ):
                self.assertEqual(0, main([
                    "acquire", str(ACTIVATION), str(PLAN),
                    "--store-root", str(root / "store"),
                    "--observed-at-epoch", "0",
                    "--output", str(root / "dry.json"),
                ]))
            result = json.loads((root / "dry.json").read_text())
            self.assertEqual("not_executed", result["status"])
            self.assertEqual(0, result["network_requests"])
            self.assertFalse((root / "store").exists())

    def test_cli_replay_is_network_free_and_byte_reproducible(self) -> None:
        summaries = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(2):
                output = root / f"out-{index}"
                with (
                    patch("socket.socket", side_effect=AssertionError("network")),
                    patch("socket.create_connection", side_effect=AssertionError("network")),
                    patch("socket.getaddrinfo", side_effect=AssertionError("dns")),
                    patch("subprocess.Popen", side_effect=AssertionError("process")),
                ):
                    self.assertEqual(0, main([
                        "replay", str(ACTIVATION), str(PLAN),
                        "--store-root", str(STORE),
                        "--workspace", str(root / f"workspace-{index}"),
                        "--recorded-at", "2026-08-22T12:00:00Z",
                        "--expect-manifest-hash", EXPECTED_MANIFEST_HASH,
                        "--output-dir", str(output),
                    ]))
                ingestion = json.loads((output / "ingestion.json").read_text())
                report = json.loads((output / "report.json").read_text())
                projection = json.loads((output / "projection.json").read_text())
                verify_report(report, records=ingestion["records"])
                verify_projection(projection, records=ingestion["records"])
                self.assertEqual(6, ingestion["record_count"])
                self.assertEqual(18, ingestion["rights_records_written"])
                self.assertEqual(0, ingestion["records_with_applicability_record"])
                summaries.append((output / "summary.json").read_bytes())
            self.assertEqual(summaries[0], summaries[1])

    def test_execute_stays_fail_closed_while_activation_is_pending(self) -> None:
        plan = load_plan(PLAN.read_bytes())
        with tempfile.TemporaryDirectory() as temporary:
            with patch(
                "math_research.corpus.live.build_live_transport",
                side_effect=AssertionError("transport must not be constructed"),
            ) as build_transport:
                with self.assertRaises(ActivationNotActiveError):
                    main([
                        "acquire", str(ACTIVATION), str(PLAN),
                        "--store-root", temporary,
                        "--observed-at-epoch", "1787356800",
                        "--execute", "--operator-id", "human.repository-owner",
                        "--confirm-live-network",
                        "I_ACKNOWLEDGE_LIVE_ARXIV_METADATA_ACQUISITION",
                        "--confirm-plan-hash", plan["content_hash"],
                    ])
                build_transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
