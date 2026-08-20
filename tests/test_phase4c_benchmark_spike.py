"""Nonproduction, offline Phase 4C benchmark-spike tests."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

from spikes.phase4c_benchmark.evaluator import canonical_bytes, evaluate_baseline


FIXTURES = Path("fixtures/phase4c")


class Phase4CBenchmarkSpikeTests(unittest.TestCase):
    def test_fixture_and_query_counts_and_license_are_frozen(self) -> None:
        corpus = json.loads((FIXTURES / "corpus-manifest.json").read_text(encoding="utf-8"))
        gold = json.loads((FIXTURES / "gold-queries.json").read_text(encoding="utf-8"))
        self.assertEqual(corpus["fixture_license"], "LicenseRef-AdaIvy-Synthetic-Fixture")
        self.assertEqual(len(corpus["documents"]), 14)
        self.assertEqual(len(gold["queries"]), 10)
        self.assertEqual(
            {category: sum(q["category"] == category for q in gold["queries"]) for category in {
                "necessary_lemma", "applicability", "contradiction", "notation_variant", "renamed_known_result"
            }},
            {"necessary_lemma": 3, "applicability": 2, "contradiction": 2, "notation_variant": 2, "renamed_known_result": 1},
        )

    def test_baseline_is_offline_and_has_zero_external_cost(self) -> None:
        with patch.object(socket, "socket", side_effect=AssertionError("network attempted")), patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("DNS attempted")
        ):
            report = evaluate_baseline(FIXTURES)
        self.assertEqual(report["metrics"]["network_calls"], 0)
        self.assertEqual(report["metrics"]["model_or_api_calls"], 0)
        self.assertEqual(report["metrics"]["external_spend_usd"], 0)

    def test_every_query_and_failure_is_visible(self) -> None:
        report = evaluate_baseline(FIXTURES)
        self.assertEqual(len(report["results"]), 10)
        self.assertEqual({item["id"] for item in report["results"]}, {
            "lemma-compactness", "lemma-spectral", "lemma-separation",
            "applicability-spectral", "applicability-certificate",
            "contradiction-boundary", "contradiction-monotonicity",
            "notation-banach", "notation-psd", "renamed-known",
        })
        self.assertTrue(all("ordered_ids" in item for item in report["results"]))

    def test_metrics_are_measured_not_copied_from_thresholds(self) -> None:
        report = evaluate_baseline(FIXTURES)
        metrics = report["metrics"]
        thresholds = report["proposed_thresholds"]
        self.assertEqual(set(thresholds), {
            "necessary_lemma_recall_at_5", "applicability_precision_at_5",
            "contradiction_recall_at_5", "notation_variant_recall_at_5",
            "renamed_known_result_recall_at_10", "duplicate_rate_at_5_maximum",
            "external_spend_usd",
        })
        for name in (
            "necessary_lemma_recall_at_5", "applicability_precision_at_5",
            "contradiction_recall_at_5", "notation_variant_recall_at_5",
            "renamed_known_result_recall_at_10",
        ):
            self.assertGreaterEqual(metrics[name], 0.0)
            self.assertLessEqual(metrics[name], 1.0)
        self.assertGreaterEqual(metrics["duplicate_rate_at_5"], 0.0)
        self.assertLessEqual(metrics["duplicate_rate_at_5"], 1.0)
        self.assertTrue(
            any(metrics[name] < thresholds[name] for name in (
                "necessary_lemma_recall_at_5", "applicability_precision_at_5",
                "contradiction_recall_at_5", "notation_variant_recall_at_5",
                "renamed_known_result_recall_at_10",
            ))
            or metrics["duplicate_rate_at_5"] > thresholds["duplicate_rate_at_5_maximum"]
        )

    def test_rebuild_and_reverse_insertion_are_semantically_identical(self) -> None:
        reports = [evaluate_baseline(FIXTURES) for _ in range(3)]
        reverse = evaluate_baseline(FIXTURES, reverse_insertion=True)
        hashes = {item["semantic_hash"] for item in [*reports, reverse]}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(canonical_bytes(reports[0]), canonical_bytes(reverse))

    def test_fresh_process_reproduces_semantic_hash(self) -> None:
        local = evaluate_baseline(FIXTURES)
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = "src:."
        completed = subprocess.run(
            [sys.executable, "-m", "spikes.phase4c_benchmark.evaluator"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=environment,
        )
        fresh = json.loads(completed.stdout)
        self.assertEqual(fresh["semantic_hash"], local["semantic_hash"])
        self.assertEqual(canonical_bytes(fresh), canonical_bytes(local))

    def test_evaluator_imports_only_standard_library(self) -> None:
        source = Path("spikes/phase4c_benchmark/evaluator.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        roots = {
            node.names[0].name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
        } | {
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertLessEqual(roots, {
            "__future__", "hashlib", "json", "pathlib", "re", "sqlite3",
            "typing", "unicodedata",
        })

    def test_gold_labels_are_not_indexed_as_retrieval_features(self) -> None:
        report = evaluate_baseline(FIXTURES)
        renamed = next(item for item in report["results"] if item["id"] == "renamed-known")
        # The evaluator indexes only source bytes. Gold IDs/classes cannot make a
        # lexically disjoint historical result appear.
        self.assertNotIn("renamed-cover-result", renamed["ordered_ids"])


if __name__ == "__main__":
    unittest.main()
