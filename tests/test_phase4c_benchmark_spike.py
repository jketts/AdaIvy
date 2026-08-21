"""Nonproduction, offline Phase 4C benchmark-spike tests.

These tests are written so that the spec's "Forbidden outcomes" fail loudly
rather than silently: label leakage, vacuous passes, unpinned metrics, unbounded
resources, and fail-open inputs each have a dedicated adversarial case.
"""

from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from unittest.mock import patch

from spikes.phase4c_benchmark import evaluator as ev
from spikes.phase4c_benchmark.evaluator import (
    FixtureError,
    canonical_bytes,
    evaluate_baseline,
    probe,
    semantic_view,
    sha256_bytes,
)


FIXTURES = Path("fixtures/phase4c")
EVALUATOR_SOURCE = Path("spikes/phase4c_benchmark/evaluator.py")

# Measured values of the frozen lexical baseline. These are observations, not
# targets: they are pinned so that any retrieval, tokenizer, weighting, or
# metric change must be a deliberate edit to this file.
MEASURED_METRICS = {
    "necessary_lemma_recall_at_5": 1.0,
    "applicability_precision_at_5": 8 / 14,
    "contradiction_recall_at_5": 1.0,
    "notation_variant_recall_at_5": 1.0,
    "renamed_known_result_recall_at_10": 0.0,
    "duplicate_rate_at_5": 1 / 61,
    "external_spend_usd": 0,
    "network_calls": 0,
    "model_or_api_calls": 0,
}
MEASURED_SUPPORT = {
    "necessary_lemma_recall_at_5": (3, 3),
    "applicability_precision_at_5": (8, 14),
    "contradiction_recall_at_5": (2, 2),
    "notation_variant_recall_at_5": (2, 2),
    "renamed_known_result_recall_at_10": (0, 4),
    "duplicate_rate_at_5": (1, 61),
}
MEASURED_ORDERED_IDS = {
    "applicability-certificate": [
        "duplicate-certificate-a",
        "duplicate-certificate-b",
        "optimization-distractor",
        "renamed-maximal-chain-result",
        "renamed-uniform-bound-result",
    ],
    "applicability-compactness": [
        "topology-distractor",
        "compactness-lemma",
        "finite-dimensional-spectral",
        "separation-lemma",
        "hypothesis-free-supremum",
    ],
    "applicability-psd-cone": [
        "residual-bound-gap",
        "psd-notation",
        "topology-distractor",
    ],
    "applicability-selfadjoint": [
        "spectral-lemma",
        "unbounded-spectral-mismatch",
        "finite-dimensional-spectral",
        "renamed-uniform-bound-result",
    ],
    "applicability-spectral": [
        "finite-dimensional-spectral",
        "unbounded-spectral-mismatch",
        "spectral-lemma",
        "topology-distractor",
    ],
    "applicability-supremum": [
        "hypothesis-free-supremum",
        "separation-lemma",
        "topology-distractor",
        "compactness-lemma",
        "renamed-cover-result",
    ],
    "contradiction-boundary": [
        "boundary-contradiction",
        "monotonicity-contradiction",
        "renamed-cover-result",
    ],
    "contradiction-monotonicity": [
        "monotonicity-contradiction",
        "boundary-contradiction",
        "residual-bound-gap",
    ],
    "lemma-compactness": [
        "compactness-lemma",
        "topology-distractor",
        "spectral-lemma",
        "unbounded-spectral-mismatch",
        "banach-notation",
    ],
    "lemma-separation": [
        "separation-lemma",
        "compactness-lemma",
        "renamed-cover-result",
    ],
    "lemma-spectral": [
        "spectral-lemma",
        "finite-dimensional-spectral",
        "unbounded-spectral-mismatch",
    ],
    "notation-banach": [
        "banach-notation",
        "boundary-contradiction",
    ],
    "notation-psd": [
        "psd-notation",
        "residual-bound-gap",
        "finite-dimensional-spectral",
        "unbounded-spectral-mismatch",
    ],
    "renamed-container-count": [
        "renamed-cover-result",
    ],
    "renamed-known": [
        "topology-distractor",
        "finite-dimensional-spectral",
        "unbounded-spectral-mismatch",
    ],
    "renamed-maximal-chain": [
        "separation-lemma",
        "hypothesis-free-supremum",
        "spectral-lemma",
        "compactness-lemma",
    ],
    "renamed-uniform-bound": [
        "banach-notation",
        "topology-distractor",
        "finite-dimensional-spectral",
        "unbounded-spectral-mismatch",
    ],
}
MEASURED_GATE_STATUS = {
    "necessary_lemma_recall_at_5": "pass",
    "applicability_precision_at_5": "fail",
    "contradiction_recall_at_5": "pass",
    "notation_variant_recall_at_5": "pass",
    "renamed_known_result_recall_at_10": "fail",
    "duplicate_rate_at_5_maximum": "pass",
    "external_spend_usd": "pass",
}


def _corpus_body_tokens() -> set[str]:
    manifest = json.loads((FIXTURES / "corpus-manifest.json").read_text(encoding="utf-8"))
    tokens: set[str] = set()
    for document in manifest["documents"]:
        text = (FIXTURES / document["path"]).read_text(encoding="utf-8")
        tokens |= {token.casefold() for token in ev._TOKEN.findall(text)}
    return tokens


def _label_tokens() -> set[str]:
    manifest = json.loads((FIXTURES / "corpus-manifest.json").read_text(encoding="utf-8"))
    gold = json.loads((FIXTURES / "gold-queries.json").read_text(encoding="utf-8"))
    values: list[str] = []
    for document in manifest["documents"]:
        values += [
            document["id"], document["source_class"], document["applicability"],
            document["duplicate_group"] or "", str(document["contradiction"]),
        ]
    for query in gold["queries"]:
        values += [query["category"], *query["relevant_ids"], *query.get("applicable_ids", [])]
    tokens: set[str] = set()
    for value in values:
        tokens |= {token.casefold() for token in ev._TOKEN.findall(value)}
    return tokens


class _MutatedFixtures:
    """Copy the frozen fixtures into a temp dir and mutate the copy.

    fixtures/phase4c is never written to; only this throwaway copy is.
    """

    def __init__(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name) / "phase4c"
        shutil.copytree(FIXTURES, self.root)

    def __enter__(self) -> "_MutatedFixtures":
        return self

    def __exit__(self, *exc: object) -> None:
        self._directory.cleanup()

    def manifest(self) -> dict:
        return json.loads((self.root / "corpus-manifest.json").read_text(encoding="utf-8"))

    def gold(self) -> dict:
        return json.loads((self.root / "gold-queries.json").read_text(encoding="utf-8"))

    def write_manifest(self, value: dict) -> None:
        (self.root / "corpus-manifest.json").write_text(json.dumps(value, indent=1), encoding="utf-8")

    def write_gold(self, value: dict) -> None:
        (self.root / "gold-queries.json").write_text(json.dumps(value, indent=1), encoding="utf-8")

    def write_raw_gold(self, text: str) -> None:
        (self.root / "gold-queries.json").write_text(text, encoding="utf-8")

    def write_raw_manifest(self, text: str) -> None:
        (self.root / "corpus-manifest.json").write_text(text, encoding="utf-8")

    def write_document(self, relative: str, text: str) -> None:
        (self.root / relative).write_text(text, encoding="utf-8")


class Phase4CFixtureContractTests(unittest.TestCase):
    def test_fixture_and_query_counts_and_license_are_frozen(self) -> None:
        corpus = json.loads((FIXTURES / "corpus-manifest.json").read_text(encoding="utf-8"))
        gold = json.loads((FIXTURES / "gold-queries.json").read_text(encoding="utf-8"))
        self.assertEqual(corpus["fixture_license"], "LicenseRef-AdaIvy-Synthetic-Fixture")
        self.assertEqual(len(corpus["documents"]), 19)
        self.assertEqual(len(gold["queries"]), 17)
        self.assertEqual(
            {category: sum(q["category"] == category for q in gold["queries"]) for category in {
                "necessary_lemma", "applicability", "contradiction", "notation_variant", "renamed_known_result"
            }},
            {"necessary_lemma": 3, "applicability": 6, "contradiction": 2, "notation_variant": 2, "renamed_known_result": 4},
        )

    def test_declared_resource_bounds_match_the_spec(self) -> None:
        # The bound-enforcement tests below patch these constants, so the
        # constants themselves are pinned to the spec numbers here.
        self.assertEqual(ev.DOCUMENT_COUNT, 19)
        self.assertEqual(ev.QUERY_COUNT, 17)
        self.assertEqual(ev.MAX_QUERY_BYTES, 4_096)
        self.assertEqual(ev.MAX_REPORT_BYTES, 262_144)
        self.assertEqual(ev.MAX_DERIVED_DB_BYTES, 2_097_152)
        self.assertEqual(ev.MAX_ELAPSED_MS, 10_000)
        self.assertEqual(ev.DUPLICATE_CUTOFF, 5)
        self.assertEqual(
            ev.TOP_K_BY_CATEGORY,
            {
                "necessary_lemma": 5, "applicability": 5, "contradiction": 5,
                "notation_variant": 5, "renamed_known_result": 10,
            },
        )
        self.assertEqual(
            ev.CATEGORY_COUNTS,
            {
                "necessary_lemma": 3, "applicability": 6, "contradiction": 2,
                "notation_variant": 2, "renamed_known_result": 4,
            },
        )

    def test_baseline_is_offline_and_has_zero_external_cost(self) -> None:
        with patch.object(socket, "socket", side_effect=AssertionError("network attempted")), patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("DNS attempted")
        ):
            report = evaluate_baseline(FIXTURES)
        self.assertEqual(report["metrics"]["network_calls"], 0)
        self.assertEqual(report["metrics"]["model_or_api_calls"], 0)
        self.assertEqual(report["metrics"]["external_spend_usd"], 0)

    def test_evaluator_imports_only_standard_library(self) -> None:
        tree = ast.parse(EVALUATOR_SOURCE.read_text(encoding="utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # Every alias, not just the first: `import json, socket` must fail.
                roots |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    self.fail("relative import in a standalone spike module")
                roots.add((node.module or "").split(".")[0])
        self.assertLessEqual(roots, {
            "__future__", "dataclasses", "hashlib", "json", "pathlib", "re",
            "sqlite3", "time", "typing", "unicodedata",
        })

    def test_import_allowlist_check_sees_every_alias(self) -> None:
        # Guards the checker above against the single-alias blind spot.
        tree = ast.parse("import json, socket\n")
        node = next(item for item in ast.walk(tree) if isinstance(item, ast.Import))
        self.assertEqual({alias.name for alias in node.names}, {"json", "socket"})

    def test_evaluator_names_no_network_or_process_surface(self) -> None:
        source = EVALUATOR_SOURCE.read_text(encoding="utf-8")
        for forbidden in ("socket", "urllib", "http", "subprocess", "requests", "__import__", "importlib"):
            self.assertNotIn(forbidden, source)


class Phase4CLabelSeparationTests(unittest.TestCase):
    def test_only_document_source_bytes_are_searchable(self) -> None:
        manifest = json.loads((FIXTURES / "corpus-manifest.json").read_text(encoding="utf-8"))
        documents = ev._load_corpus(FIXTURES, manifest)
        rows = ev._corpus_rows(documents)
        self.assertEqual(len(rows), 19)
        for (identifier, title, body, unit_type), document in zip(rows, documents, strict=True):
            self.assertEqual(identifier, document.identifier)
            # The frozen corpus has no title or unit-type content of its own, so
            # the two non-body weighted columns are empty rather than filled
            # with the document ID or the source class.
            self.assertEqual(title, "")
            self.assertEqual(unit_type, "")
            source = (FIXTURES / document.path).read_bytes().decode("utf-8")
            self.assertEqual(body, unicodedata.normalize(ev.NORMALIZATION_FORM, source))

    def test_tokens_that_exist_only_in_ids_or_labels_retrieve_nothing(self) -> None:
        body_tokens = _corpus_body_tokens()
        label_only = sorted(_label_tokens() - body_tokens)
        # Sanity: the derivation must actually find label-only tokens, and it
        # must include the ones the audit used as leakage probes. `historical`
        # and `informal` are deliberately absent from this list: they really do
        # occur in document bodies ("Project-authored historical record",
        # "Project-authored informal note"), so they are not label-only.
        self.assertGreaterEqual(len(label_only), 8)
        for token in ("mismatch", "distractor", "primary", "secondary", "duplicate", "variant"):
            self.assertIn(token, label_only)
        for token in label_only:
            with self.subTest(token=token):
                self.assertEqual(probe(FIXTURES, token), [])

    def test_full_document_ids_and_class_labels_are_not_matchable_terms(self) -> None:
        manifest = json.loads((FIXTURES / "corpus-manifest.json").read_text(encoding="utf-8"))
        body_tokens = _corpus_body_tokens()
        for document in manifest["documents"]:
            for value in (document["id"], document["source_class"], document["applicability"]):
                tokens = [token.casefold() for token in ev._TOKEN.findall(value)]
                unique = [token for token in tokens if token not in body_tokens]
                if not unique:
                    continue
                with self.subTest(document=document["id"], value=value):
                    self.assertEqual(probe(FIXTURES, " ".join(unique)), [])

    def test_duplicate_group_label_is_not_a_retrieval_feature(self) -> None:
        # "dual" and "certificate" occur in the duplicate bodies, so the probe
        # uses the label-only token of the group name.
        self.assertEqual(probe(FIXTURES, "duplicate"), [])


class Phase4CMeasuredValueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = evaluate_baseline(FIXTURES)

    def test_every_query_and_failure_is_visible(self) -> None:
        results = self.report["results"]
        self.assertEqual(len(results), 17)
        self.assertEqual({item["id"] for item in results}, set(MEASURED_ORDERED_IDS))
        for item in results:
            self.assertIn("ordered_ids", item)
            self.assertIn("missed_relevant_ids", item)
            self.assertIn("duplicate_ids_at_5", item)
            self.assertIn("inapplicable_retrieved_ids", item)
            self.assertIn("zero_hit", item)
            self.assertEqual(
                item["missed_relevant_ids"],
                sorted(set(item["relevant_ids"]) - set(item["ordered_ids"])),
            )
        self.assertEqual(self.report["zero_hit_query_ids"], [])
        misses = {item["id"]: item["missed_relevant_ids"] for item in results if item["missed_relevant_ids"]}
        self.assertEqual(
            misses,
            {
                "renamed-known": ["renamed-cover-result"],
                "renamed-uniform-bound": ["renamed-uniform-bound-result"],
                "renamed-maximal-chain": ["renamed-maximal-chain-result"],
                "renamed-container-count": ["renamed-container-count-result"],
            },
        )

    def test_measured_metric_values_are_pinned(self) -> None:
        self.assertEqual(set(self.report["metrics"]), set(MEASURED_METRICS))
        for name, expected in MEASURED_METRICS.items():
            with self.subTest(metric=name):
                self.assertAlmostEqual(self.report["metrics"][name], expected, places=12)

    def test_measured_metric_support_counts_are_pinned(self) -> None:
        support = self.report["metric_support"]
        self.assertEqual(set(support), set(MEASURED_SUPPORT))
        for name, (numerator, denominator) in MEASURED_SUPPORT.items():
            with self.subTest(metric=name):
                self.assertEqual(support[name]["numerator"], numerator)
                self.assertEqual(support[name]["denominator"], denominator)
                self.assertTrue(support[name]["defined"])

    def test_measured_ordered_ids_are_pinned(self) -> None:
        actual = {item["id"]: item["ordered_ids"] for item in self.report["results"]}
        self.assertEqual(actual, MEASURED_ORDERED_IDS)

    def test_gate_evaluation_is_pinned_and_never_passes_on_missing_data(self) -> None:
        gates = self.report["gate_evaluation"]
        self.assertEqual(set(gates), set(MEASURED_GATE_STATUS))
        for key, status in MEASURED_GATE_STATUS.items():
            with self.subTest(gate=key):
                self.assertEqual(gates[key]["status"], status)
                self.assertEqual(gates[key]["threshold"], self.report["proposed_thresholds"][key])
        self.assertEqual(
            self.report["gate_summary"], {"pass": 5, "fail": 2, "undetermined": 0, "overall": "not_pass"}
        )

    def test_metrics_are_measured_not_copied_from_thresholds(self) -> None:
        metrics = self.report["metrics"]
        thresholds = self.report["proposed_thresholds"]
        self.assertEqual(set(thresholds), set(ev.THRESHOLD_KEYS))
        for name in (
            "necessary_lemma_recall_at_5", "applicability_precision_at_5",
            "contradiction_recall_at_5", "notation_variant_recall_at_5",
            "renamed_known_result_recall_at_10", "duplicate_rate_at_5",
        ):
            value = metrics[name]
            self.assertIsNotNone(value)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        # The baseline is below at least one proposed gate, and the specific
        # failures are pinned above so this cannot become vacuous.
        self.assertIn("fail", {item["status"] for item in self.report["gate_evaluation"].values()})

    def test_duplicate_detection_is_measured_on_the_frozen_corpus(self) -> None:
        result = next(item for item in self.report["results"] if item["id"] == "applicability-certificate")
        self.assertEqual(result["duplicate_ids_at_5"], ["duplicate-certificate-b"])
        self.assertEqual(
            [item["duplicate_ids_at_5"] for item in self.report["results"] if item["id"] != "applicability-certificate"],
            [[] for _ in range(16)],
        )
        self.assertEqual(self.report["metric_support"]["duplicate_rate_at_5"]["numerator"], 1)

    def test_inapplicable_hits_are_reported_not_hidden(self) -> None:
        by_id = {item["id"]: item["inapplicable_retrieved_ids"] for item in self.report["results"]}
        self.assertEqual(by_id["applicability-spectral"], ["topology-distractor", "unbounded-spectral-mismatch"])
        self.assertEqual(by_id["applicability-certificate"], ["optimization-distractor"])


class Phase4CDeterminismTests(unittest.TestCase):
    def test_rebuild_and_reverse_insertion_are_semantically_identical(self) -> None:
        reports = [evaluate_baseline(FIXTURES) for _ in range(3)]
        reverse = evaluate_baseline(FIXTURES, reverse_insertion=True)
        hashes = {item["semantic_hash"] for item in [*reports, reverse]}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(canonical_bytes(semantic_view(reports[0])), canonical_bytes(semantic_view(reverse)))

    def test_semantic_hash_covers_exactly_the_semantic_view(self) -> None:
        report = evaluate_baseline(FIXTURES)
        self.assertEqual(report["semantic_hash"], sha256_bytes(canonical_bytes(semantic_view(report))))
        self.assertEqual(report["operational_hash"], sha256_bytes(canonical_bytes(report["operational"])))
        # Operational observations stay out of semantic identity, and the
        # semantic key set is pinned so nothing timing-dependent can drift in.
        self.assertEqual(
            set(semantic_view(report)),
            {
                "schema_version", "method", "declared_method", "tokenizer", "field_weights",
                "resource_bounds", "corpus_manifest_hash", "gold_queries_hash", "source_hashes",
                "results", "zero_hit_query_ids", "metrics", "metric_support",
                "proposed_thresholds", "gate_evaluation", "gate_summary",
            },
        )
        self.assertEqual(
            set(report["operational"]),
            {"derived_db_bytes", "elapsed_ms", "reverse_insertion", "sqlite_library_version"},
        )
        for item in report["results"]:
            self.assertEqual(
                set(item) - {"applicable_ids"},
                {
                    "id", "category", "query", "top_k", "relevant_ids", "ordered_ids",
                    "missed_relevant_ids", "duplicate_ids_at_5", "inapplicable_retrieved_ids",
                    "zero_hit",
                },
            )

    def _fresh_process(self, hash_seed: str) -> dict:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = "src:."
        environment["PYTHONHASHSEED"] = hash_seed
        completed = subprocess.run(
            [sys.executable, "-m", "spikes.phase4c_benchmark.evaluator"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=environment,
        )
        return json.loads(completed.stdout)

    def test_fresh_process_reproduces_semantic_hash(self) -> None:
        local = evaluate_baseline(FIXTURES)
        fresh = self._fresh_process("0")
        self.assertEqual(fresh["semantic_hash"], local["semantic_hash"])
        self.assertEqual(canonical_bytes(semantic_view(fresh)), canonical_bytes(semantic_view(local)))

    def test_varied_hash_seeds_reproduce_semantic_hash(self) -> None:
        local = evaluate_baseline(FIXTURES)
        for seed in ("0", "1", "4294967295", "random"):
            with self.subTest(hash_seed=seed):
                fresh = self._fresh_process(seed)
                self.assertEqual(fresh["semantic_hash"], local["semantic_hash"])


class Phase4CDeclaredMethodTests(unittest.TestCase):
    def test_declared_method_is_the_executed_sql(self) -> None:
        report = evaluate_baseline(FIXTURES)
        declared = report["declared_method"]
        self.assertEqual(declared["create_statement"], ev.CREATE_STATEMENT)
        self.assertEqual(declared["search_statement"], ev.SEARCH_STATEMENT)
        self.assertIn(f"tokenize='{declared['tokenizer']}'", ev.CREATE_STATEMENT)
        self.assertIn(
            "bm25(lexical, 0.0, 0.0, 0.0, " + ", ".join(f"{w:.1f}" for w in declared["field_weights"]) + ")",
            ev.SEARCH_STATEMENT,
        )
        self.assertIn("ORDER BY score ASC, document_id ASC", ev.SEARCH_STATEMENT)
        self.assertEqual(declared["field_weights"], [2.0, 1.0, 0.5])
        self.assertEqual(declared["indexed_fields"], ["title", "body", "unit_type"])
        self.assertEqual(declared["tokenizer"], "unicode61 remove_diacritics 0")
        self.assertEqual(declared["normalization_form"], "NFC")
        self.assertEqual(report["metrics"], report["metrics"])  # metrics dict is the measured one
        self.assertEqual(report["field_weights"], list(ev.FIELD_WEIGHTS))
        self.assertEqual(report["tokenizer"], ev.TOKENIZER)

    def test_title_weight_outranks_type_weight_behaviourally(self) -> None:
        # Synthetic probe rows, not corpus content: the frozen corpus has no
        # title/type content, so the 2.0 and 0.5 weights are otherwise inert.
        # Alphabetical order favours "a-type-match", so a title-first result
        # proves the title weight really is the largest.
        rows = [
            ("b-title-match", "zeta", "filler alpha beta", ""),
            ("a-type-match", "", "filler alpha beta", "zeta"),
        ]
        connection = ev.open_index(rows)
        try:
            self.assertEqual(ev.search(connection, "zeta", 5), ["b-title-match", "a-type-match"])
        finally:
            connection.close()

    def test_tie_break_is_document_id_ascending(self) -> None:
        rows = [
            ("zzz-doc", "", "identical body text", ""),
            ("aaa-doc", "", "identical body text", ""),
            ("mmm-doc", "", "identical body text", ""),
        ]
        connection = ev.open_index(rows)
        try:
            self.assertEqual(ev.search(connection, "identical", 5), ["aaa-doc", "mmm-doc", "zzz-doc"])
        finally:
            connection.close()

    def test_unindexed_columns_cannot_be_matched(self) -> None:
        rows = [("sentinel-identifier", "", "body text only", "")]
        connection = ev.open_index(rows)
        try:
            self.assertEqual(ev.search(connection, "sentinel", 5), [])
            self.assertEqual(ev.search(connection, "identifier", 5), [])
            self.assertEqual(ev.search(connection, "body", 5), ["sentinel-identifier"])
        finally:
            connection.close()

    def test_declared_nfc_normalization_and_retained_diacritics_are_exercised(self) -> None:
        composed = unicodedata.normalize("NFC", "Å")
        decomposed = unicodedata.normalize("NFD", "Å")
        self.assertNotEqual(composed, decomposed)
        with _MutatedFixtures() as mutated:
            mutated.write_document(
                "corpus/banach-notation.txt",
                f"Project-authored normalization probe. The {decomposed} unit appears here.\n",
            )
            gold = mutated.gold()
            for query in gold["queries"]:
                if query["id"] == "notation-banach":
                    query["query"] = composed
            mutated.write_gold(gold)
            report = evaluate_baseline(mutated.root)
            result = next(item for item in report["results"] if item["id"] == "notation-banach")
            # NFC on both sides makes the composed query match the decomposed
            # source. Switching the declared form to NFD breaks this.
            self.assertEqual(result["ordered_ids"], ["banach-notation"])

        with _MutatedFixtures() as mutated:
            mutated.write_document(
                "corpus/banach-notation.txt",
                f"Project-authored normalization probe. The {composed} unit appears here.\n",
            )
            gold = mutated.gold()
            for query in gold["queries"]:
                if query["id"] == "notation-banach":
                    query["query"] = "A"
            mutated.write_gold(gold)
            report = evaluate_baseline(mutated.root)
            result = next(item for item in report["results"] if item["id"] == "notation-banach")
            # remove_diacritics 0: a bare "A" must not reach the accented token.
            self.assertNotIn("banach-notation", result["ordered_ids"])


class Phase4CVacuousPassTests(unittest.TestCase):
    def test_total_retrieval_collapse_is_undetermined_not_zero(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            for query in gold["queries"]:
                query["query"] = "zzqqxxnotacorpustoken"
            mutated.write_gold(gold)
            report = evaluate_baseline(mutated.root)
        self.assertEqual([item["ordered_ids"] for item in report["results"]], [[] for _ in range(17)])
        self.assertEqual(len(report["zero_hit_query_ids"]), 17)
        self.assertTrue(all(item["zero_hit"] for item in report["results"]))
        # No data measured: not a passing zero.
        self.assertIsNone(report["metrics"]["duplicate_rate_at_5"])
        self.assertIsNone(report["metrics"]["applicability_precision_at_5"])
        self.assertFalse(report["metric_support"]["duplicate_rate_at_5"]["defined"])
        self.assertFalse(report["metric_support"]["applicability_precision_at_5"]["defined"])
        self.assertEqual(report["gate_evaluation"]["duplicate_rate_at_5_maximum"]["status"], "undetermined")
        self.assertEqual(report["gate_evaluation"]["applicability_precision_at_5"]["status"], "undetermined")
        # Recalls have nonzero denominators, so they are genuine measured zeros.
        for name in (
            "necessary_lemma_recall_at_5", "contradiction_recall_at_5",
            "notation_variant_recall_at_5", "renamed_known_result_recall_at_10",
        ):
            self.assertEqual(report["metrics"][name], 0.0)
            self.assertTrue(report["metric_support"][name]["defined"])
            self.assertEqual(report["gate_evaluation"][name]["status"], "fail")
        self.assertEqual(report["gate_summary"]["undetermined"], 2)
        self.assertEqual(report["gate_summary"]["overall"], "not_pass")
        self.assertLessEqual(report["gate_summary"]["pass"], 1)

    def test_duplicate_rate_is_measured_when_every_document_shares_a_group(self) -> None:
        with _MutatedFixtures() as mutated:
            manifest = mutated.manifest()
            for document in manifest["documents"]:
                document["duplicate_group"] = "everything"
            mutated.write_manifest(manifest)
            report = evaluate_baseline(mutated.root)
        support = report["metric_support"]["duplicate_rate_at_5"]
        # 50 hits at the cutoff of five, fifteen of which are the first member
        # of the single group; every later hit is a declared duplicate.
        self.assertEqual((support["numerator"], support["denominator"]), (44, 61))
        self.assertAlmostEqual(report["metrics"]["duplicate_rate_at_5"], 44 / 61, places=12)
        self.assertEqual(report["gate_evaluation"]["duplicate_rate_at_5_maximum"]["status"], "fail")

    def test_duplicate_rate_is_a_measured_zero_without_any_group(self) -> None:
        with _MutatedFixtures() as mutated:
            manifest = mutated.manifest()
            for document in manifest["documents"]:
                document["duplicate_group"] = None
            mutated.write_manifest(manifest)
            report = evaluate_baseline(mutated.root)
        self.assertEqual(report["metrics"]["duplicate_rate_at_5"], 0.0)
        self.assertEqual(report["metric_support"]["duplicate_rate_at_5"]["denominator"], 61)
        self.assertTrue(report["metric_support"]["duplicate_rate_at_5"]["defined"])


class Phase4CBoundEnforcementTests(unittest.TestCase):
    def test_document_and_query_cardinality_gates_are_enforced(self) -> None:
        with _MutatedFixtures() as mutated:
            manifest = mutated.manifest()
            manifest["documents"] = manifest["documents"][:13]
            mutated.write_manifest(manifest)
            with self.assertRaisesRegex(FixtureError, "cardinality mismatch"):
                evaluate_baseline(mutated.root)
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            gold["queries"] = gold["queries"][:9]
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "cardinality mismatch"):
                evaluate_baseline(mutated.root)

    def test_top_k_is_bounded_and_category_consistent(self) -> None:
        for bad in (19, 1, 17, 0, -5):
            with self.subTest(top_k=bad), _MutatedFixtures() as mutated:
                gold = mutated.gold()
                gold["queries"][0]["top_k"] = bad
                mutated.write_gold(gold)
                with self.assertRaisesRegex(FixtureError, "top_k"):
                    evaluate_baseline(mutated.root)

    def test_renamed_control_top_k_must_stay_ten(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            renamed = next(item for item in gold["queries"] if item["category"] == "renamed_known_result")
            renamed["top_k"] = 5
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "top_k"):
                evaluate_baseline(mutated.root)

    def test_boolean_top_k_is_not_coerced(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            gold["queries"][0]["top_k"] = True
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "expected an integer"):
                evaluate_baseline(mutated.root)

    def test_query_length_bound_is_measured_on_raw_bytes(self) -> None:
        padded = "compact" + (" " * 24_000) + "space"
        self.assertGreater(len(padded.encode("utf-8")), ev.MAX_QUERY_BYTES)
        self.assertLessEqual(len(" ".join(padded.split()).encode("utf-8")), ev.MAX_QUERY_BYTES)
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            gold["queries"][0]["query"] = padded
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "raw UTF-8 bytes exceeds"):
                evaluate_baseline(mutated.root)

    def test_query_at_the_byte_bound_is_accepted(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            gold["queries"][0]["query"] = "compact " + "x" * (ev.MAX_QUERY_BYTES - len("compact "))
            mutated.write_gold(gold)
            evaluate_baseline(mutated.root)

    def test_derived_database_bound_is_measured_and_enforced(self) -> None:
        report = evaluate_baseline(FIXTURES)
        measured = report["operational"]["derived_db_bytes"]
        self.assertGreater(measured, 0)
        self.assertLessEqual(measured, ev.MAX_DERIVED_DB_BYTES)
        with patch.object(ev, "MAX_DERIVED_DB_BYTES", measured - 1):
            with self.assertRaisesRegex(FixtureError, "derived benchmark database bound exceeded"):
                evaluate_baseline(FIXTURES)

    def test_report_byte_bound_is_enforced(self) -> None:
        report = evaluate_baseline(FIXTURES)
        measured = len(canonical_bytes(report))
        self.assertLessEqual(measured, ev.MAX_REPORT_BYTES)
        with patch.object(ev, "MAX_REPORT_BYTES", 512):
            with self.assertRaisesRegex(FixtureError, "report byte bound exceeded"):
                evaluate_baseline(FIXTURES)

    def test_elapsed_time_bound_is_enforced(self) -> None:
        with patch.object(ev, "MAX_ELAPSED_MS", -1):
            with self.assertRaisesRegex(FixtureError, "time bound exceeded"):
                evaluate_baseline(FIXTURES)


class Phase4CFailClosedInputTests(unittest.TestCase):
    def test_unknown_category_is_rejected(self) -> None:
        for bad in ("misc", "necessary_lemma_v2", "Necessary_Lemma", ""):
            with self.subTest(category=bad), _MutatedFixtures() as mutated:
                gold = mutated.gold()
                gold["queries"][0]["category"] = bad
                mutated.write_gold(gold)
                with self.assertRaises(FixtureError):
                    evaluate_baseline(mutated.root)

    def test_category_distribution_is_enforced(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            # A legal category with a legal top-k, but the wrong distribution.
            gold["queries"][0]["category"] = "contradiction"
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "category distribution mismatch"):
                evaluate_baseline(mutated.root)

    def test_unknown_top_level_keys_are_rejected(self) -> None:
        with _MutatedFixtures() as mutated:
            manifest = mutated.manifest()
            manifest["extra"] = 1
            mutated.write_manifest(manifest)
            with self.assertRaisesRegex(FixtureError, "unknown keys"):
                evaluate_baseline(mutated.root)
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            gold["notes"] = "smuggled"
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "unknown keys"):
                evaluate_baseline(mutated.root)

    def test_unknown_per_query_and_per_document_keys_are_rejected(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            gold["queries"][0]["boost"] = 3
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "unknown keys"):
                evaluate_baseline(mutated.root)
        with _MutatedFixtures() as mutated:
            manifest = mutated.manifest()
            manifest["documents"][0]["title"] = "compactness lemma"
            mutated.write_manifest(manifest)
            with self.assertRaisesRegex(FixtureError, "unknown keys"):
                evaluate_baseline(mutated.root)

    def test_applicable_ids_outside_the_applicability_category_are_rejected(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            gold["queries"][0]["applicable_ids"] = ["compactness-lemma"]
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "unknown keys"):
                evaluate_baseline(mutated.root)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        raw = (FIXTURES / "gold-queries.json").read_text(encoding="utf-8")
        smuggled = raw.replace(
            '"schema_version": "adaivy.phase4c-gold-queries.v1",',
            '"schema_version": "attacker.v0",\n  "schema_version": "adaivy.phase4c-gold-queries.v1",',
            1,
        )
        self.assertNotEqual(smuggled, raw)
        with _MutatedFixtures() as mutated:
            mutated.write_raw_gold(smuggled)
            with self.assertRaisesRegex(FixtureError, "duplicate JSON key"):
                evaluate_baseline(mutated.root)
        with _MutatedFixtures() as mutated:
            mutated.write_raw_manifest(
                (FIXTURES / "corpus-manifest.json").read_text(encoding="utf-8").replace(
                    '"fixture_license": "LicenseRef-AdaIvy-Synthetic-Fixture",',
                    '"fixture_license": "Other", "fixture_license": "LicenseRef-AdaIvy-Synthetic-Fixture",',
                    1,
                )
            )
            with self.assertRaisesRegex(FixtureError, "duplicate JSON key"):
                evaluate_baseline(mutated.root)

    def test_relevant_ids_must_be_corpus_documents(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            gold["queries"][0]["relevant_ids"] = ["compactness-lemma", "not-in-corpus"]
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "not in the corpus"):
                evaluate_baseline(mutated.root)

    def test_applicable_ids_must_agree_with_corpus_applicability(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            query = next(item for item in gold["queries"] if item["category"] == "applicability")
            query["applicable_ids"] = list(query["relevant_ids"])
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "disagrees with corpus applicability"):
                evaluate_baseline(mutated.root)

    def test_wrong_types_are_rejected_not_coerced(self) -> None:
        cases = [
            ("gold", lambda g: g["queries"][0].__setitem__("id", 7), "non-empty string"),
            ("gold", lambda g: g["queries"][0].__setitem__("query", ["compact"]), "non-empty string"),
            ("gold", lambda g: g["queries"][0].__setitem__("relevant_ids", "compactness-lemma"), "non-empty list"),
            ("gold", lambda g: g["queries"][0].__setitem__("relevant_ids", []), "non-empty list"),
            ("gold", lambda g: g["queries"].__setitem__(0, ["not", "an", "object"]), "must be an object"),
            ("gold", lambda g: g["proposed_thresholds"].__setitem__("external_spend_usd", "0"), "expected a number"),
            ("manifest", lambda m: m["documents"][0].__setitem__("contradiction", "false"), "expected a boolean"),
            ("manifest", lambda m: m["documents"][0].__setitem__("source_class", "tertiary"), "is not one of"),
            ("manifest", lambda m: m["documents"][0].__setitem__("applicability", "maybe"), "is not one of"),
            ("manifest", lambda m: m["documents"][0].__setitem__("duplicate_group", 3), "non-empty string"),
            ("manifest", lambda m: m.__setitem__("documents", {"a": 1}), "must be a list"),
            ("manifest", lambda m: m.__setitem__("fixture_license", "MIT"), "unsupported fixture license"),
            ("manifest", lambda m: m.__setitem__("schema_version", "adaivy.phase4c-corpus.v2"), "schema version"),
        ]
        for target, mutate, expected in cases:
            with self.subTest(target=target, expected=expected), _MutatedFixtures() as mutated:
                if target == "gold":
                    value = mutated.gold()
                    mutate(value)
                    mutated.write_gold(value)
                else:
                    value = mutated.manifest()
                    mutate(value)
                    mutated.write_manifest(value)
                with self.assertRaisesRegex(FixtureError, expected):
                    evaluate_baseline(mutated.root)

    def test_duplicate_document_ids_and_paths_are_rejected(self) -> None:
        with _MutatedFixtures() as mutated:
            manifest = mutated.manifest()
            manifest["documents"][1] = copy.deepcopy(manifest["documents"][0])
            mutated.write_manifest(manifest)
            with self.assertRaisesRegex(FixtureError, "duplicate document id"):
                evaluate_baseline(mutated.root)
        with _MutatedFixtures() as mutated:
            manifest = mutated.manifest()
            manifest["documents"][1]["path"] = manifest["documents"][0]["path"]
            mutated.write_manifest(manifest)
            with self.assertRaisesRegex(FixtureError, "duplicate document path"):
                evaluate_baseline(mutated.root)

    def test_duplicate_query_ids_are_rejected(self) -> None:
        with _MutatedFixtures() as mutated:
            gold = mutated.gold()
            gold["queries"][1]["id"] = gold["queries"][0]["id"]
            mutated.write_gold(gold)
            with self.assertRaisesRegex(FixtureError, "duplicate query id"):
                evaluate_baseline(mutated.root)

    def test_path_escape_is_rejected(self) -> None:
        for bad in ("../../etc/passwd", "/etc/passwd", "corpus/../../secret.txt"):
            with self.subTest(path=bad), _MutatedFixtures() as mutated:
                manifest = mutated.manifest()
                manifest["documents"][0]["path"] = bad
                mutated.write_manifest(manifest)
                with self.assertRaises(FixtureError):
                    evaluate_baseline(mutated.root)

    def test_symlink_escape_out_of_the_fixture_directory_is_rejected(self) -> None:
        # Only the resolved-path check catches this: the relative path contains
        # no "..", so the syntactic check passes.
        with _MutatedFixtures() as mutated:
            outside = mutated.root.parent / "outside-the-fixture.txt"
            outside.write_text("secret bytes\n", encoding="utf-8")
            link = mutated.root / "corpus" / "linked.txt"
            link.symlink_to(outside)
            manifest = mutated.manifest()
            manifest["documents"][0]["path"] = "corpus/linked.txt"
            mutated.write_manifest(manifest)
            with self.assertRaisesRegex(FixtureError, "path escape"):
                evaluate_baseline(mutated.root)

    def test_query_expression_shape_and_empty_rejection(self) -> None:
        self.assertEqual(ev.fts_expression("Compact  Space"), '"compact" OR "space"')
        self.assertEqual(ev.fts_expression("PSD\u00a0cone"), '"psd" OR "cone"')
        for bad in ("", "   ", "\t\n", "-- ;", "___"):
            with self.subTest(query=bad):
                with self.assertRaises(FixtureError):
                    ev.fts_expression(bad)

    def test_malformed_json_is_rejected(self) -> None:
        with _MutatedFixtures() as mutated:
            mutated.write_raw_gold("{not json")
            with self.assertRaisesRegex(FixtureError, "not valid JSON"):
                evaluate_baseline(mutated.root)


if __name__ == "__main__":
    unittest.main()
