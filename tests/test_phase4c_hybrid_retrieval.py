"""Acceptance suite for the bounded Phase 4C hybrid-retrieval slice.

Per ADR-0026 and the "Consequences" section of ADR-0031, this suite is the only
executable record of this slice's thresholds, and each forbidden outcome must be
demonstrated impossible rather than left untested. So the tests are written as
properties over the whole frozen query set, not as a happy path:

* label separation -- a token that exists only in an id or a classification
  label retrieves nothing;
* demotion-only -- over all fifteen queries the hedge never raises a fused
  score and never introduces a document;
* cue-class partition -- the two classes are disjoint, object-level cues cannot
  demote, and neither contradiction gold is demoted;
* cue neutrality -- with the demoting table emptied the fused ordering is
  exactly the pure lexical ordering;
* alias hygiene -- no document identifier anywhere in the alias fixture, at
  least five entries exercised by no query and matching no document, and
  removing one exercised entry fails exactly its own query;
* honest metrics -- zero-denominator ratios are `None`/`undetermined`, never a
  passing zero, including under total retrieval collapse;
* determinism, bounds, zero external cost, and pinned measured values kept
  separate from the proposed thresholds.

Measured values below are OBSERVATIONS, not targets. One of them records a gate
failure. They are pinned so that any retrieval, cue, weighting, fusion, or
metric change has to be a deliberate edit to this file.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from math_research.phase4c import aliases as alias_module
from math_research.phase4c import benchmark as benchmark_module
from math_research.phase4c import fusion as fusion_module
from math_research.phase4c import hedging as hedging_module
from math_research.phase4c import lexical as lexical_module
from math_research.phase4c import text as text_module
from math_research.phase4c.aliases import ALIAS_PHRASE_POINTS, EmptyAliasSignal
from math_research.phase4c.benchmark import (
    Measurement,
    evaluate_hybrid,
    gate_status,
    verify_report,
)
from math_research.phase4c.bounds import (
    BOUNDS,
    CATEGORY_COUNTS,
    Phase4CValidationError,
    SCHEMA_VERSION,
    THRESHOLD_KEYS,
    TOP_K_BY_CATEGORY,
)
from math_research.phase4c.fixtures import (
    load_aliases,
    load_corpus,
    load_gold,
    load_object,
)
from math_research.phase4c.hedging import (
    OBJECT_LEVEL_CUES,
    SELF_DISCLAIMING_CUES,
    HedgingScopeSignal,
)
from math_research.phase4c.lexical import EmptyLexicalIndex, probe
from math_research.phase4c.serialization import (
    canonical_bytes,
    content_hash,
    semantic_preimage,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures" / "phase4c"
PACKAGE_DIR = REPO_ROOT / "src" / "math_research" / "phase4c"
CLI_SOURCE = REPO_ROOT / "src" / "math_research" / "phase4c_cli.py"


# --------------------------------------------------------------------------
# Pinned MEASURED values. Separate from the fixture's proposed thresholds.
# --------------------------------------------------------------------------

MEASURED_METRICS = {
    "necessary_lemma_recall_at_5": 1.0,
    # MEASURED FAILURE, recorded rather than tuned away. The hedge fires
    # correctly on three of four applicability queries but cannot move this
    # number: every applicability query's fused candidate set has at most five
    # members against a top-k of five, so a demotion-only reordering cannot
    # remove a demoted document from the retrieved set. On the fourth query,
    # `applicability-selfadjoint`, the same-sentence scope rule does not fire.
    "applicability_precision_at_5": 0.6,
    "contradiction_recall_at_5": 1.0,
    "notation_variant_recall_at_5": 1.0,
    "renamed_known_result_recall_at_10": 1.0,
    "duplicate_rate_at_5": 1 / 54,
    "external_spend_usd": 0,
    "network_calls": 0,
    "model_or_api_calls": 0,
    "downloaded_artifacts": 0,
}
MEASURED_SUPPORT = {
    "necessary_lemma_recall_at_5": (3, 3),
    "applicability_precision_at_5": (6, 10),
    "contradiction_recall_at_5": (2, 2),
    "notation_variant_recall_at_5": (2, 2),
    "renamed_known_result_recall_at_10": (4, 4),
    "duplicate_rate_at_5": (1, 54),
}
MEASURED_GATE_STATUS = {
    "necessary_lemma_recall_at_5": "pass",
    "applicability_precision_at_5": "fail",
    "contradiction_recall_at_5": "pass",
    "notation_variant_recall_at_5": "pass",
    "renamed_known_result_recall_at_10": "pass",
    "duplicate_rate_at_5_maximum": "pass",
    "external_spend_usd": "pass",
}
MEASURED_GATE_SUMMARY = {"pass": 6, "fail": 1, "undetermined": 0, "overall": "not_pass"}

# Measured lexical-baseline values on the same extended fixtures, for the
# "may not worsen a metric the baseline already met" comparison.
BASELINE_METRICS = {
    "necessary_lemma_recall_at_5": 1.0,
    "applicability_precision_at_5": 0.6,
    "contradiction_recall_at_5": 1.0,
    "notation_variant_recall_at_5": 1.0,
    "renamed_known_result_recall_at_10": 0.0,
    "duplicate_rate_at_5": 1 / 50,
}

MEASURED_ORDERED_IDS = {
    "lemma-compactness": (
        "compactness-lemma", "spectral-lemma", "banach-notation",
        "separation-lemma", "finite-dimensional-spectral",
    ),
    "lemma-spectral": (
        "spectral-lemma", "finite-dimensional-spectral", "unbounded-spectral-mismatch",
    ),
    "lemma-separation": ("separation-lemma", "compactness-lemma", "renamed-cover-result"),
    "applicability-spectral": (
        "finite-dimensional-spectral", "spectral-lemma",
        "unbounded-spectral-mismatch", "topology-distractor",
    ),
    "applicability-certificate": (
        "duplicate-certificate-a", "duplicate-certificate-b",
        "renamed-maximal-chain-result", "renamed-uniform-bound-result",
        "optimization-distractor",
    ),
    "applicability-compactness": (
        "compactness-lemma", "finite-dimensional-spectral", "separation-lemma",
        "topology-distractor", "unbounded-spectral-mismatch",
    ),
    "applicability-selfadjoint": (
        "spectral-lemma", "unbounded-spectral-mismatch",
        "finite-dimensional-spectral", "renamed-uniform-bound-result",
    ),
    "contradiction-boundary": (
        "boundary-contradiction", "monotonicity-contradiction", "renamed-cover-result",
    ),
    "contradiction-monotonicity": ("monotonicity-contradiction", "boundary-contradiction"),
    "notation-banach": ("banach-notation", "boundary-contradiction"),
    "notation-psd": (
        "psd-notation", "finite-dimensional-spectral", "unbounded-spectral-mismatch",
    ),
    "renamed-uniform-bound": (
        "renamed-uniform-bound-result", "banach-notation",
        "finite-dimensional-spectral", "unbounded-spectral-mismatch",
        "topology-distractor",
    ),
    "renamed-maximal-chain": (
        "renamed-maximal-chain-result", "separation-lemma", "spectral-lemma",
        "compactness-lemma",
    ),
    "renamed-container-count": ("renamed-container-count-result", "renamed-cover-result"),
    "renamed-known": (
        "renamed-cover-result", "finite-dimensional-spectral",
        "unbounded-spectral-mismatch", "topology-distractor",
    ),
}
MEASURED_DEMOTED_IDS = {
    "lemma-compactness": ("topology-distractor", "unbounded-spectral-mismatch"),
    "lemma-spectral": (),
    "lemma-separation": (),
    "applicability-spectral": ("topology-distractor", "unbounded-spectral-mismatch"),
    "applicability-certificate": ("optimization-distractor",),
    "applicability-compactness": ("topology-distractor", "unbounded-spectral-mismatch"),
    "applicability-selfadjoint": (),
    "contradiction-boundary": (),
    "contradiction-monotonicity": (),
    "notation-banach": (),
    "notation-psd": ("unbounded-spectral-mismatch",),
    "renamed-uniform-bound": ("topology-distractor",),
    "renamed-maximal-chain": (),
    "renamed-container-count": (),
    "renamed-known": ("topology-distractor",),
}
# Alias entries the frozen query set exercises, and the query each one serves.
MEASURED_EXERCISED_ALIASES = {
    "banach-steinhaus-theorem": "renamed-uniform-bound",
    "borel-lebesgue-theorem": "renamed-known",
    "dirichlet-drawer-principle": "renamed-container-count",
    "kuratowski-zorn-lemma": "renamed-maximal-chain",
}
MEASURED_UNEXERCISED_ALIASES = (
    "bellman-gronwall-inequality",
    "bolzano-weierstrass-theorem",
    "cauchy-bunyakovsky-schwarz-inequality",
    "heine-cantor-theorem",
    "schur-complement-lemma",
    "tychonoff-product-theorem",
)
MEASURED_CONTRADICTION_GOLDS = ("boundary-contradiction", "monotonicity-contradiction")

_REPORT_CACHE: dict[bool, dict] = {}


def frozen_report(reverse_insertion: bool = False) -> dict:
    if reverse_insertion not in _REPORT_CACHE:
        _REPORT_CACHE[reverse_insertion] = evaluate_hybrid(
            FIXTURES, reverse_insertion=reverse_insertion
        )
    return _REPORT_CACHE[reverse_insertion]


def result_by_id(report: dict) -> dict[str, dict]:
    return {item["id"]: item for item in report["results"]}


def _corpus_body_tokens() -> set[str]:
    return {
        token
        for document in load_corpus(FIXTURES)
        for token in text_module.tokens(document.text)
    }


def _label_tokens() -> set[str]:
    manifest = load_object(FIXTURES / "corpus-manifest.json")
    found: set[str] = set()
    for entry in manifest["documents"]:
        for key in ("id", "source_class", "applicability", "duplicate_group"):
            value = entry[key]
            if isinstance(value, str):
                found |= set(text_module.tokens(value))
    return found


# --------------------------------------------------------------------------
# 1. Label separation
# --------------------------------------------------------------------------


class Phase4CLabelSeparationTests(unittest.TestCase):
    def test_only_document_body_bytes_reach_indexed_columns(self) -> None:
        documents = load_corpus(FIXTURES)
        rows = lexical_module.corpus_rows(documents)
        self.assertEqual(len(rows), BOUNDS.document_count)
        for (identifier, title, body, unit_type), document in zip(
            rows, documents, strict=True
        ):
            self.assertEqual(identifier, document.identifier)
            self.assertEqual(title, "")
            self.assertEqual(unit_type, "")
            self.assertEqual(body, document.text)

    def test_tokens_that_exist_only_in_ids_or_labels_retrieve_nothing(self) -> None:
        documents = load_corpus(FIXTURES)
        label_only = sorted(_label_tokens() - _corpus_body_tokens())
        self.assertGreaterEqual(len(label_only), 8)
        for token in ("mismatch", "distractor", "primary", "secondary", "duplicate"):
            self.assertIn(token, label_only)
        for token in label_only:
            with self.subTest(token=token):
                self.assertEqual(probe(documents, token), [])

    def test_full_ids_and_class_labels_are_not_matchable_terms(self) -> None:
        documents = load_corpus(FIXTURES)
        body_tokens = _corpus_body_tokens()
        manifest = load_object(FIXTURES / "corpus-manifest.json")
        for entry in manifest["documents"]:
            for key in ("id", "source_class", "applicability", "duplicate_group"):
                value = entry[key]
                if not isinstance(value, str):
                    continue
                query_tokens = text_module.tokens(value)
                if any(token in body_tokens for token in query_tokens):
                    continue
                with self.subTest(label=value):
                    self.assertEqual(probe(documents, value), [])

    def test_no_label_value_is_ever_written_to_an_indexed_column(self) -> None:
        # The set of values reaching a weighted column is exactly the document
        # bodies plus the empty string, so no classification label can be one.
        documents = load_corpus(FIXTURES)
        indexed_values = {
            value
            for _identifier, *columns in lexical_module.corpus_rows(documents)
            for value in columns
        }
        self.assertEqual(
            indexed_values, {""} | {document.text for document in documents}
        )
        for document in documents:
            with self.subTest(document=document.identifier):
                self.assertNotIn(document.applicability, indexed_values)
                self.assertNotIn(document.source_class, indexed_values)
                self.assertNotIn(document.identifier, indexed_values)
                if document.duplicate_group is not None:
                    self.assertNotIn(document.duplicate_group, indexed_values)
        self.assertEqual(
            lexical_module.UNINDEXED_FIELDS,
            ("document_id", "source_id", "normalized_start"),
        )
        for label in ("source_class", "applicability", "duplicate_group"):
            self.assertNotIn(label, lexical_module.CREATE_STATEMENT)


# --------------------------------------------------------------------------
# 2, 3, 4, 5. The hedging signal
# --------------------------------------------------------------------------


class Phase4CHedgeIsDemotionOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.with_hedge = frozen_report()
        self.without_hedge = evaluate_hybrid(FIXTURES, self_disclaiming_cues=())

    def test_hedge_never_raises_a_fused_score_over_every_query(self) -> None:
        hedged = {item["id"]: item for item in self.with_hedge["operational"]["results"]}
        plain = {item["id"]: item for item in self.without_hedge["operational"]["results"]}
        self.assertEqual(len(hedged), BOUNDS.query_count)
        self.assertEqual(set(hedged), set(plain))
        compared = 0
        for query_id, hedged_entry in hedged.items():
            hedged_scores = {
                hit["document_id"]: hit["fused_score"] for hit in hedged_entry["hits"]
            }
            plain_scores = {
                hit["document_id"]: hit["fused_score"] for hit in plain[query_id]["hits"]
            }
            self.assertEqual(set(hedged_scores), set(plain_scores), query_id)
            for document_id, score in hedged_scores.items():
                with self.subTest(query=query_id, document=document_id):
                    self.assertLessEqual(score, plain_scores[document_id])
                compared += 1
        self.assertGreater(compared, 0)

    def test_hedge_never_introduces_a_document_over_every_query(self) -> None:
        hedged = result_by_id(self.with_hedge)
        plain = result_by_id(self.without_hedge)
        for query_id, entry in hedged.items():
            with self.subTest(query=query_id):
                self.assertEqual(
                    set(entry["fused_candidate_ids"]),
                    set(plain[query_id]["fused_candidate_ids"]),
                )
                self.assertLessEqual(
                    set(entry["demoted_ids"]), set(entry["fused_candidate_ids"])
                )
                self.assertLessEqual(
                    set(entry["demoted_ids"]),
                    set(entry["lexical_candidate_ids"])
                    | set(entry["alias_introduced_ids"]),
                )

    def test_fusion_rejects_a_hedge_verdict_outside_the_candidate_set(self) -> None:
        from math_research.phase4c.ports import HedgeVerdict, LexicalCandidate

        with self.assertRaises(Phase4CValidationError):
            fusion_module.fuse(
                [LexicalCandidate(document_id="a", bm25=-1.0)],
                [],
                [
                    HedgeVerdict(
                        document_id="intruder",
                        demoted=True,
                        self_disclaiming_cues=("insufficient",),
                        object_level_cues=(),
                        scoped_query_terms=("x",),
                    )
                ],
                alias_phrase_points=ALIAS_PHRASE_POINTS,
            )

    def test_demoted_hits_rank_below_every_non_demoted_hit(self) -> None:
        for entry in self.with_hedge["results"]:
            demoted_flags = [hit["demoted"] for hit in entry["hits"]]
            with self.subTest(query=entry["id"]):
                # Non-demoted hits all precede demoted hits: the flag sequence
                # is monotone.
                self.assertEqual(demoted_flags, sorted(demoted_flags))


class Phase4CCueClassTests(unittest.TestCase):
    def test_cue_classes_are_disjoint(self) -> None:
        self.assertEqual(set(SELF_DISCLAIMING_CUES) & set(OBJECT_LEVEL_CUES), set())
        self.assertEqual(len(set(SELF_DISCLAIMING_CUES)), len(SELF_DISCLAIMING_CUES))
        self.assertEqual(len(set(OBJECT_LEVEL_CUES)), len(OBJECT_LEVEL_CUES))

    def test_overlapping_cue_classes_are_rejected(self) -> None:
        documents = load_corpus(FIXTURES)
        with self.assertRaises(Phase4CValidationError):
            HedgingScopeSignal(
                documents,
                self_disclaiming_cues=("fails",),
                object_level_cues=("fails",),
            )

    def test_object_level_cues_cannot_cause_a_demotion(self) -> None:
        # Emptying the object-level table changes neither the fused ordering
        # nor a single demotion, so object-level cues have no ordering effect.
        neutralised = evaluate_hybrid(FIXTURES, object_level_cues=())
        frozen = result_by_id(frozen_report())
        for entry in neutralised["results"]:
            with self.subTest(query=entry["id"]):
                self.assertEqual(
                    entry["ordered_ids"], frozen[entry["id"]]["ordered_ids"]
                )
                self.assertEqual(
                    entry["demoted_ids"], frozen[entry["id"]]["demoted_ids"]
                )

    def test_a_document_with_only_object_level_cues_is_never_demoted(self) -> None:
        observed = 0
        for entry in frozen_report()["results"]:
            for hit in entry["hits"]:
                if hit["object_level_cues"] and not hit["self_disclaiming_cues"]:
                    observed += 1
                    with self.subTest(query=entry["id"], document=hit["document_id"]):
                        self.assertFalse(hit["demoted"])
        self.assertGreater(observed, 0)

    def test_neither_contradiction_gold_is_ever_demoted(self) -> None:
        for entry in frozen_report()["results"]:
            for gold in MEASURED_CONTRADICTION_GOLDS:
                with self.subTest(query=entry["id"], gold=gold):
                    self.assertNotIn(gold, entry["demoted_ids"])

    def test_boundary_contradiction_carries_object_level_cues_in_query_scope(self) -> None:
        # This is the exact case a naive negation signal breaks: an applicable
        # contradiction gold whose matched query terms share a sentence with
        # `fails`, `violates`, and `counterexample`.
        documents = load_corpus(FIXTURES)
        signal = HedgingScopeSignal(documents)
        queries, _ = load_gold(FIXTURES, documents)
        query = next(
            item for item in queries if item.identifier == "contradiction-boundary"
        )
        verdict = signal.verdicts(query.query, ["boundary-contradiction"])[0]
        self.assertFalse(verdict.demoted)
        self.assertEqual(verdict.self_disclaiming_cues, ())
        self.assertEqual(
            set(verdict.object_level_cues), {"fails", "violates", "counterexample"}
        )
        self.assertTrue(verdict.scoped_query_terms == ())

    def test_the_excluded_cues_stay_excluded(self) -> None:
        # `without` and bare `no` are mathematical content, not disclaimers.
        # Bare `no` false-positives on an applicable renamed gold, which this
        # test demonstrates rather than asserts.
        for excluded in ("without", "no"):
            self.assertNotIn(excluded, SELF_DISCLAIMING_CUES)
            self.assertNotIn(excluded, OBJECT_LEVEL_CUES)
        documents = load_corpus(FIXTURES)
        container = next(
            document
            for document in documents
            if document.identifier == "renamed-container-count-result"
        )
        self.assertIn("no distribution", container.text)
        signal = HedgingScopeSignal(
            documents, self_disclaiming_cues=("no",), object_level_cues=()
        )
        verdict = signal.verdicts(
            "Dirichlet drawer principle distribution", ["renamed-container-count-result"]
        )[0]
        self.assertTrue(
            verdict.demoted,
            "bare `no` demotes an applicable gold, which is why it is excluded",
        )

    def test_cue_matching_is_word_boundary_anchored(self) -> None:
        pattern = text_module.cue_pattern("is not")
        self.assertIsNone(pattern.search("this note states no theorem"))
        self.assertIsNotNone(pattern.search("the hypothesis is not satisfied"))

    def test_there_is_no_cue_count_threshold(self) -> None:
        self.assertIsNone(hedging_module.CUE_COUNT_THRESHOLD)
        declared = frozen_report()["declared_method"]["hedging_signal"]
        self.assertIsNone(declared["cue_count_threshold"])
        self.assertEqual(declared["direction"], "demotion_only")
        self.assertEqual(
            declared["scope_rule"],
            "matched-query-term-in-same-sentence-as-self-disclaiming-cue",
        )

    def test_the_cue_table_hits_exactly_the_non_applicable_documents(self) -> None:
        # Corpus-wide audit of the demoting table, independent of any query.
        documents = load_corpus(FIXTURES)
        patterns = [text_module.cue_pattern(cue) for cue in SELF_DISCLAIMING_CUES]
        hit = {
            document.identifier
            for document in documents
            if any(
                pattern.search(sentence.casefold())
                for sentence in text_module.sentences(document.text)
                for pattern in patterns
            )
        }
        non_applicable = {
            document.identifier
            for document in documents
            if document.applicability != "applicable"
        }
        self.assertEqual(hit, non_applicable)
        self.assertEqual(
            non_applicable,
            {
                "optimization-distractor",
                "topology-distractor",
                "unbounded-spectral-mismatch",
            },
        )


class Phase4CCueNeutralityTests(unittest.TestCase):
    def test_removing_every_demoting_cue_yields_the_pure_lexical_ordering(self) -> None:
        report = evaluate_hybrid(
            FIXTURES, self_disclaiming_cues=(), alias_signal=EmptyAliasSignal()
        )
        for entry in report["results"]:
            with self.subTest(query=entry["id"]):
                self.assertEqual(entry["demoted_ids"], [])
                self.assertEqual(
                    entry["ordered_ids"],
                    entry["lexical_candidate_ids"][: entry["top_k"]],
                )

    def test_the_cues_are_the_only_thing_that_changes_the_ordering(self) -> None:
        plain = result_by_id(
            evaluate_hybrid(
                FIXTURES, self_disclaiming_cues=(), alias_signal=EmptyAliasSignal()
            )
        )
        hedged = result_by_id(evaluate_hybrid(FIXTURES, alias_signal=EmptyAliasSignal()))
        changed = sorted(
            query_id
            for query_id, entry in hedged.items()
            if entry["ordered_ids"] != plain[query_id]["ordered_ids"]
        )
        self.assertGreater(len(changed), 0)
        for query_id in changed:
            with self.subTest(query=query_id):
                # An ordering change implies a demotion. Nothing else moved.
                self.assertTrue(hedged[query_id]["demoted_ids"])


# --------------------------------------------------------------------------
# 6, 7, 8. The alias table
# --------------------------------------------------------------------------


class Phase4CAliasTableTests(unittest.TestCase):
    def test_no_document_identifier_appears_in_the_alias_fixture(self) -> None:
        raw = (FIXTURES / "name-aliases.json").read_text(encoding="utf-8")
        documents = load_corpus(FIXTURES)
        self.assertEqual(len(documents), BOUNDS.document_count)
        for document in documents:
            with self.subTest(document=document.identifier):
                self.assertNotIn(document.identifier, raw)
                self.assertNotIn(document.path, raw)

    def test_alias_entries_have_the_exact_key_set(self) -> None:
        payload = load_object(FIXTURES / "name-aliases.json")
        self.assertEqual(set(payload), {"schema_version", "fixture_license", "aliases"})
        for entry in payload["aliases"]:
            self.assertEqual(set(entry), {"id", "alias", "content_phrases"})

    def test_at_least_five_entries_are_idle(self) -> None:
        coverage = {
            item["entry_id"]: item for item in frozen_report()["alias_table_coverage"]
        }
        idle = tuple(
            sorted(
                entry_id
                for entry_id, item in coverage.items()
                if item["exercised_by_no_query"] and item["matches_no_document"]
            )
        )
        self.assertGreaterEqual(len(idle), 5)
        self.assertEqual(idle, MEASURED_UNEXERCISED_ALIASES)
        self.assertGreaterEqual(len(coverage), 9)

    def test_exercised_entries_and_their_queries_are_pinned(self) -> None:
        exercised: dict[str, list[str]] = {}
        for item in frozen_report()["alias_table_coverage"]:
            if item["exercised_by_query_ids"]:
                exercised[item["entry_id"]] = item["exercised_by_query_ids"]
        self.assertEqual(
            {key: value[0] for key, value in exercised.items()},
            MEASURED_EXERCISED_ALIASES,
        )
        for value in exercised.values():
            self.assertEqual(len(value), 1)

    def test_removing_one_exercised_alias_fails_exactly_its_own_query(self) -> None:
        entries = load_aliases(FIXTURES)
        frozen = result_by_id(frozen_report())
        for entry_id, query_id in MEASURED_EXERCISED_ALIASES.items():
            reduced = tuple(item for item in entries if item.identifier != entry_id)
            self.assertEqual(len(reduced), len(entries) - 1)
            report = evaluate_hybrid(FIXTURES, alias_entries=reduced)
            results = result_by_id(report)
            with self.subTest(removed=entry_id):
                self.assertTrue(results[query_id]["missed_relevant_ids"])
                for other_id, other in results.items():
                    if other_id == query_id:
                        continue
                    self.assertEqual(
                        other["missed_relevant_ids"],
                        frozen[other_id]["missed_relevant_ids"],
                        f"removing {entry_id} disturbed {other_id}",
                    )
                self.assertEqual(
                    report["metric_support"]["renamed_known_result_recall_at_10"],
                    {"numerator": 3, "denominator": 4, "defined": True},
                )
                self.assertEqual(
                    report["gate_evaluation"]["renamed_known_result_recall_at_10"][
                        "status"
                    ],
                    "fail",
                )

    def test_alias_signal_reads_no_document_identifier(self) -> None:
        # The alias signal is built from body tokens only: a query naming a
        # document identifier verbatim expands nothing.
        documents = load_corpus(FIXTURES)
        signal = alias_module.AliasExpansionSignal(documents, load_aliases(FIXTURES))
        for document in documents:
            with self.subTest(document=document.identifier):
                self.assertEqual(signal.expand(document.identifier, limit=50), ())

    def test_renamed_gate_is_invariant_to_the_alias_phrase_weight(self) -> None:
        # ALIAS_PHRASE_POINTS is a unit weight, not a tuned parameter.
        for points in (0.001, 0.5, 1.0, 3.0, 1000.0):
            report = evaluate_hybrid(FIXTURES, alias_phrase_points=points)
            with self.subTest(points=points):
                self.assertEqual(
                    report["metrics"]["renamed_known_result_recall_at_10"], 1.0
                )
                for entry in report["results"]:
                    if entry["category"] != "renamed_known_result":
                        continue
                    self.assertEqual(entry["missed_relevant_ids"], [])
        self.assertEqual(ALIAS_PHRASE_POINTS, 1.0)

    def test_a_non_positive_alias_weight_is_rejected(self) -> None:
        for points in (0.0, -1.0):
            with self.subTest(points=points), self.assertRaises(Phase4CValidationError):
                evaluate_hybrid(FIXTURES, alias_phrase_points=points)

    def test_content_phrases_match_token_runs_not_raw_substrings(self) -> None:
        # `finite subcover` must match the corpus spelling `finite-subcover`.
        self.assertTrue(
            text_module.contains_token_run(
                text_module.tokens("The finite-subcover principle says"),
                text_module.tokens("finite subcover"),
            )
        )
        self.assertFalse(
            text_module.contains_token_run(
                text_module.tokens("this note states no theorem"),
                text_module.tokens("is not"),
            )
        )


# --------------------------------------------------------------------------
# 9. Determinism
# --------------------------------------------------------------------------


class Phase4CDeterminismTests(unittest.TestCase):
    def _fresh_process(self, hash_seed: str) -> dict:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(REPO_ROOT / "src")
        environment["PYTHONHASHSEED"] = hash_seed
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "math_research.phase4c_cli",
                    "benchmark",
                    "--fixtures",
                    str(FIXTURES),
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=BOUNDS.max_elapsed_ms // 1000,
                cwd=str(REPO_ROOT),
                env=environment,
            )
            # Exit 1 is the measured gate failure, not a crash.
            self.assertIn(completed.returncode, (0, 1), completed.stderr)
            return json.loads(output.read_text(encoding="utf-8"))

    def test_three_normal_builds_are_byte_identical(self) -> None:
        first = evaluate_hybrid(FIXTURES)
        second = evaluate_hybrid(FIXTURES)
        third = evaluate_hybrid(FIXTURES)
        for other in (second, third):
            self.assertEqual(other["content_hash"], first["content_hash"])
            self.assertEqual(
                canonical_bytes(semantic_preimage(other)),
                canonical_bytes(semantic_preimage(first)),
            )

    def test_reverse_insertion_build_is_semantically_identical(self) -> None:
        forward = evaluate_hybrid(FIXTURES)
        reverse = evaluate_hybrid(FIXTURES, reverse_insertion=True)
        self.assertEqual(reverse["content_hash"], forward["content_hash"])
        self.assertTrue(reverse["operational"]["reverse_insertion"])
        self.assertFalse(forward["operational"]["reverse_insertion"])
        self.assertEqual(
            [item["ordered_ids"] for item in reverse["results"]],
            [item["ordered_ids"] for item in forward["results"]],
        )

    def test_fresh_process_reproduces_the_content_hash(self) -> None:
        local = evaluate_hybrid(FIXTURES)
        fresh = self._fresh_process("0")
        self.assertEqual(fresh["content_hash"], local["content_hash"])
        self.assertEqual(
            canonical_bytes(semantic_preimage(fresh)),
            canonical_bytes(semantic_preimage(local)),
        )

    def test_varied_hash_seeds_reproduce_the_content_hash(self) -> None:
        local = evaluate_hybrid(FIXTURES)
        for seed in ("0", "1", "4294967295", "random"):
            with self.subTest(hash_seed=seed):
                fresh = self._fresh_process(seed)
                self.assertEqual(fresh["content_hash"], local["content_hash"])
                self.assertEqual(
                    [item["ordered_ids"] for item in fresh["results"]],
                    [item["ordered_ids"] for item in local["results"]],
                )

    def test_content_hash_pops_the_key_and_excludes_operational_data(self) -> None:
        report = frozen_report()
        self.assertNotIn("content_hash", semantic_preimage(report))
        self.assertNotIn("operational", semantic_preimage(report))
        self.assertNotIn("operational_hash", semantic_preimage(report))
        self.assertEqual(content_hash(report), report["content_hash"])
        mutated = dict(report)
        mutated["operational"] = {**report["operational"], "elapsed_ms": 999_999}
        self.assertEqual(content_hash(mutated), report["content_hash"])

    def test_verify_report_rejects_a_tampered_ordering(self) -> None:
        report = json.loads(json.dumps(frozen_report()))
        report["results"][0]["ordered_ids"].reverse()
        with self.assertRaises(Phase4CValidationError):
            verify_report(report)

    def test_verify_report_accepts_the_emitted_report(self) -> None:
        verified = verify_report(json.loads(json.dumps(frozen_report())))
        self.assertTrue(verified["verified"])
        self.assertEqual(verified["schema_version"], SCHEMA_VERSION)


# --------------------------------------------------------------------------
# 10, 11. Honest metrics and full visibility
# --------------------------------------------------------------------------


class Phase4CHonestMetricTests(unittest.TestCase):
    def test_zero_denominator_measurement_is_none(self) -> None:
        measurement = Measurement(0, 0)
        self.assertIsNone(measurement.value)
        self.assertEqual(
            measurement.as_support(),
            {"numerator": 0, "denominator": 0, "defined": False},
        )
        self.assertEqual(
            gate_status("duplicate_rate_at_5_maximum", 0.05, None), "undetermined"
        )
        self.assertEqual(
            gate_status("applicability_precision_at_5", 1.0, None), "undetermined"
        )

    def test_total_retrieval_collapse_reports_undetermined_not_pass(self) -> None:
        report = evaluate_hybrid(
            FIXTURES,
            lexical_signal=EmptyLexicalIndex(),
            alias_signal=EmptyAliasSignal(),
        )
        self.assertEqual(
            sorted(report["zero_hit_query_ids"]),
            sorted(item["id"] for item in report["results"]),
        )
        self.assertEqual(len(report["results"]), BOUNDS.query_count)
        for name in ("applicability_precision_at_5", "duplicate_rate_at_5"):
            with self.subTest(metric=name):
                self.assertIsNone(report["metrics"][name])
                self.assertEqual(report["metric_support"][name]["denominator"], 0)
                self.assertFalse(report["metric_support"][name]["defined"])
        for key in ("applicability_precision_at_5", "duplicate_rate_at_5_maximum"):
            with self.subTest(gate=key):
                self.assertEqual(report["gate_evaluation"][key]["status"], "undetermined")
                self.assertNotEqual(report["gate_evaluation"][key]["status"], "pass")
        # A collapsed retriever must not pass the duplicate gate by retrieving
        # nothing. The recall denominators are gold counts, so a collapse is an
        # honest measured zero there rather than "no data".
        for name in (
            "necessary_lemma_recall_at_5",
            "contradiction_recall_at_5",
            "notation_variant_recall_at_5",
            "renamed_known_result_recall_at_10",
        ):
            with self.subTest(metric=name):
                self.assertEqual(report["metrics"][name], 0.0)
                self.assertTrue(report["metric_support"][name]["defined"])
        self.assertEqual(report["gate_summary"]["overall"], "not_pass")
        self.assertEqual(report["gate_summary"]["undetermined"], 2)

    def test_a_collapsed_report_hash_differs_from_the_frozen_report(self) -> None:
        collapsed = evaluate_hybrid(
            FIXTURES,
            lexical_signal=EmptyLexicalIndex(),
            alias_signal=EmptyAliasSignal(),
        )
        self.assertNotEqual(collapsed["content_hash"], frozen_report()["content_hash"])
        self.assertEqual(
            collapsed["signal_configuration"]["overrides"],
            ["lexical_signal", "alias_signal"],
        )
        self.assertEqual(frozen_report()["signal_configuration"]["overrides"], [])

    def test_every_query_and_every_failure_is_visible(self) -> None:
        report = frozen_report()
        results = report["results"]
        documents = load_corpus(FIXTURES)
        queries, _ = load_gold(FIXTURES, documents)
        self.assertEqual(
            [item["id"] for item in results], [query.identifier for query in queries]
        )
        applicability = {
            document.identifier: document.applicability for document in documents
        }
        groups = {document.identifier: document.duplicate_group for document in documents}
        for entry in results:
            with self.subTest(query=entry["id"]):
                for key in (
                    "missed_relevant_ids",
                    "duplicate_ids_at_5",
                    "inapplicable_retrieved_ids",
                    "zero_hit",
                    "demoted_ids",
                    "hits",
                    "alias_expansions",
                    "lexical_candidate_ids",
                    "fused_candidate_ids",
                ):
                    self.assertIn(key, entry)
                self.assertEqual(entry["zero_hit"], not entry["ordered_ids"])
                self.assertEqual(
                    entry["missed_relevant_ids"],
                    sorted(set(entry["relevant_ids"]) - set(entry["ordered_ids"])),
                )
                self.assertEqual(
                    entry["inapplicable_retrieved_ids"],
                    sorted(
                        identifier
                        for identifier in entry["ordered_ids"]
                        if applicability[identifier] != "applicable"
                    ),
                )
                seen: set[str] = set()
                expected_duplicates: list[str] = []
                for identifier in entry["ordered_ids"][: BOUNDS.duplicate_cutoff]:
                    group = groups[identifier]
                    if group is None:
                        continue
                    if group in seen:
                        expected_duplicates.append(identifier)
                    seen.add(group)
                self.assertEqual(entry["duplicate_ids_at_5"], expected_duplicates)
                self.assertEqual(
                    [hit["document_id"] for hit in entry["hits"]],
                    entry["fused_candidate_ids"],
                )
        self.assertIn(
            "applicability-certificate",
            [item["id"] for item in results if item["duplicate_ids_at_5"]],
        )
        self.assertTrue(any(item["inapplicable_retrieved_ids"] for item in results))

    def test_declared_provenance_is_the_executed_sql(self) -> None:
        declared = frozen_report()["declared_method"]["lexical_signal"]
        self.assertEqual(declared["create_statement"], lexical_module.CREATE_STATEMENT)
        self.assertEqual(declared["search_statement"], lexical_module.SEARCH_STATEMENT)
        self.assertEqual(declared["insert_statement"], lexical_module.INSERT_STATEMENT)
        self.assertIn("unicode61 remove_diacritics 0", declared["create_statement"])
        self.assertIn("2.0, 1.0, 0.5", declared["search_statement"])
        self.assertIn("0.0, 0.0, 0.0", declared["search_statement"])
        self.assertIn("ORDER BY score ASC, document_id ASC", declared["search_statement"])
        self.assertEqual(declared["field_weights"], [2.0, 1.0, 0.5])
        self.assertEqual(declared["indexed_fields"], ["title", "body", "unit_type"])
        self.assertEqual(declared["normalization_form"], "NFC")
        self.assertEqual(declared["tokenizer"], "unicode61 remove_diacritics 0")

    def test_fusion_is_declared_and_measured_in_score_space(self) -> None:
        fusion = frozen_report()["declared_method"]["fusion"]
        self.assertEqual(fusion["space"], "score")
        self.assertFalse(fusion["rank_only_combiner"])
        self.assertFalse(fusion["reciprocal_rank_fusion"])
        # BM25 magnitudes survive: with the alias signal disabled and the cue
        # table emptied, every fused score equals -bm25 exactly.
        plain = evaluate_hybrid(
            FIXTURES, self_disclaiming_cues=(), alias_signal=EmptyAliasSignal()
        )
        documents = load_corpus(FIXTURES)
        connection = lexical_module.open_index(lexical_module.corpus_rows(documents))
        try:
            index = lexical_module.LexicalIndex(connection)
            queries, _ = load_gold(FIXTURES, documents)
            operational = {item["id"]: item for item in plain["operational"]["results"]}
            magnitudes: list[float] = []
            for query in queries:
                expected = {
                    candidate.document_id: round(-candidate.bm25, 6)
                    for candidate in index.candidates(query.query, limit=50)
                }
                observed = {
                    hit["document_id"]: hit["fused_score"]
                    for hit in operational[query.identifier]["hits"]
                }
                with self.subTest(query=query.identifier):
                    self.assertEqual(observed, expected)
                magnitudes.extend(expected.values())
        finally:
            connection.close()
        # The margins ADR-0031 protects are BM25 magnitudes, not ranks: fused
        # scores span more than the 4.4-to-13.2 point range it cites.
        self.assertGreater(max(magnitudes), 13.2)
        self.assertGreater(max(magnitudes) - min(magnitudes), 4.4)


# --------------------------------------------------------------------------
# 12. Bounds
# --------------------------------------------------------------------------


class Phase4CBoundsTests(unittest.TestCase):
    def _staged(self, directory: str) -> Path:
        target = Path(directory) / "phase4c"
        shutil.copytree(FIXTURES, target)
        return target

    def _rewrite_gold(self, root: Path, mutate) -> None:
        payload = json.loads((root / "gold-queries.json").read_text(encoding="utf-8"))
        mutate(payload)
        (root / "gold-queries.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_bounds_policy_hash_is_stable_and_declared(self) -> None:
        self.assertEqual(BOUNDS.document_count, 17)
        self.assertEqual(BOUNDS.query_count, 15)
        self.assertEqual(BOUNDS.max_query_bytes, 4_096)
        self.assertEqual(BOUNDS.top_k_default, 5)
        self.assertEqual(BOUNDS.top_k_renamed_control, 10)
        self.assertEqual(BOUNDS.max_candidates_per_signal, 50)
        self.assertEqual(BOUNDS.max_report_bytes, 262_144)
        self.assertEqual(BOUNDS.max_derived_db_bytes, 2_097_152)
        self.assertEqual(BOUNDS.max_elapsed_ms, 10_000)
        self.assertEqual(BOUNDS.duplicate_cutoff, 5)
        self.assertRegex(BOUNDS.policy_sha256, r"^sha256:[0-9a-f]{64}$")
        declared = frozen_report()["resource_bounds"]
        self.assertEqual(declared["policy_sha256"], BOUNDS.policy_sha256)
        for key, value in BOUNDS.to_record().items():
            self.assertEqual(declared[key], value)
        self.assertEqual(
            declared["top_k_by_category"], dict(sorted(TOP_K_BY_CATEGORY.items()))
        )
        self.assertEqual(
            declared["category_counts"], dict(sorted(CATEGORY_COUNTS.items()))
        )
        self.assertEqual(sum(CATEGORY_COUNTS.values()), BOUNDS.query_count)
        self.assertEqual(set(TOP_K_BY_CATEGORY.values()), {5, 10})

    def test_report_and_database_stay_inside_their_byte_bounds(self) -> None:
        report = frozen_report()
        self.assertLessEqual(len(canonical_bytes(report)), BOUNDS.max_report_bytes)
        self.assertLessEqual(
            report["operational"]["derived_db_bytes"], BOUNDS.max_derived_db_bytes
        )
        self.assertLessEqual(report["operational"]["elapsed_ms"], BOUNDS.max_elapsed_ms)

    def test_a_query_at_exactly_the_byte_bound_is_accepted(self) -> None:
        prefix = "Borel Lebesgue theorem "
        exact = prefix + "a" * (BOUNDS.max_query_bytes - len(prefix.encode("utf-8")))
        self.assertEqual(len(exact.encode("utf-8")), BOUNDS.max_query_bytes)
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            self._rewrite_gold(
                root, lambda payload: payload["queries"][-1].__setitem__("query", exact)
            )
            documents = load_corpus(root)
            queries, _ = load_gold(root, documents)
            self.assertEqual(queries[-1].query, exact)
            self.assertEqual(len(queries), BOUNDS.query_count)

    def test_a_query_one_byte_over_the_bound_is_rejected(self) -> None:
        prefix = "Borel Lebesgue theorem "
        over = prefix + "a" * (BOUNDS.max_query_bytes - len(prefix.encode("utf-8")) + 1)
        self.assertEqual(len(over.encode("utf-8")), BOUNDS.max_query_bytes + 1)
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            self._rewrite_gold(
                root, lambda payload: payload["queries"][-1].__setitem__("query", over)
            )
            documents = load_corpus(root)
            with self.assertRaises(Phase4CValidationError):
                load_gold(root, documents)

    def test_bounds_are_measured_on_raw_bytes_not_characters(self) -> None:
        # A two-byte character makes the character count pass while the byte
        # count fails, so the bound must be enforced on encoded bytes.
        text = "é" * ((BOUNDS.max_query_bytes // 2) + 1)
        self.assertLessEqual(len(text), BOUNDS.max_query_bytes)
        self.assertGreater(len(text.encode("utf-8")), BOUNDS.max_query_bytes)
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            self._rewrite_gold(
                root, lambda payload: payload["queries"][-1].__setitem__("query", text)
            )
            documents = load_corpus(root)
            with self.assertRaises(Phase4CValidationError):
                load_gold(root, documents)

    def test_boolean_top_k_is_rejected_not_coerced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            self._rewrite_gold(
                root, lambda payload: payload["queries"][0].__setitem__("top_k", True)
            )
            documents = load_corpus(root)
            with self.assertRaises(Phase4CValidationError) as caught:
                load_gold(root, documents)
            self.assertIn("expected an integer", str(caught.exception))

    def test_integer_contradiction_flag_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            manifest = json.loads(
                (root / "corpus-manifest.json").read_text(encoding="utf-8")
            )
            manifest["documents"][0]["contradiction"] = 0
            (root / "corpus-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(Phase4CValidationError):
                load_corpus(root)

    def test_unknown_keys_and_duplicate_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            self._rewrite_gold(
                root, lambda payload: payload["queries"][0].__setitem__("extra", 1)
            )
            documents = load_corpus(root)
            with self.assertRaises(Phase4CValidationError):
                load_gold(root, documents)
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            (root / "name-aliases.json").write_text(
                '{"schema_version":"adaivy.phase4c-name-aliases.v1",'
                '"schema_version":"adaivy.phase4c-name-aliases.v1",'
                '"fixture_license":"LicenseRef-AdaIvy-Synthetic-Fixture","aliases":[]}',
                encoding="utf-8",
            )
            with self.assertRaises(Phase4CValidationError):
                load_aliases(root)

    def test_wrong_cardinality_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            manifest = json.loads(
                (root / "corpus-manifest.json").read_text(encoding="utf-8")
            )
            manifest["documents"] = manifest["documents"][:-1]
            (root / "corpus-manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            with self.assertRaises(Phase4CValidationError):
                load_corpus(root)
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            self._rewrite_gold(root, lambda payload: payload["queries"].pop())
            documents = load_corpus(root)
            with self.assertRaises(Phase4CValidationError):
                load_gold(root, documents)

    def test_unknown_category_and_wrong_top_k_are_rejected(self) -> None:
        for mutate in (
            lambda payload: payload["queries"][0].__setitem__("category", "invented"),
            lambda payload: payload["queries"][0].__setitem__("top_k", 9),
        ):
            with tempfile.TemporaryDirectory() as directory:
                root = self._staged(directory)
                self._rewrite_gold(root, mutate)
                documents = load_corpus(root)
                with self.assertRaises(Phase4CValidationError):
                    load_gold(root, documents)

    def test_path_escape_is_rejected(self) -> None:
        for bad in ("../corpus-manifest.json", "/etc/hosts", "corpus\\\\note.txt"):
            with tempfile.TemporaryDirectory() as directory:
                root = self._staged(directory)
                manifest = json.loads(
                    (root / "corpus-manifest.json").read_text(encoding="utf-8")
                )
                manifest["documents"][0]["path"] = bad
                (root / "corpus-manifest.json").write_text(
                    json.dumps(manifest), encoding="utf-8"
                )
                with self.subTest(path=bad), self.assertRaises(Phase4CValidationError):
                    load_corpus(root)

    def test_malformed_json_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged(directory)
            (root / "name-aliases.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(Phase4CValidationError):
                load_aliases(root)

    def test_candidate_limit_outside_the_bound_is_rejected(self) -> None:
        documents = load_corpus(FIXTURES)
        connection = lexical_module.open_index(lexical_module.corpus_rows(documents))
        try:
            index = lexical_module.LexicalIndex(connection)
            for limit in (0, -1, BOUNDS.max_candidates_per_signal + 1):
                with self.subTest(limit=limit), self.assertRaises(
                    Phase4CValidationError
                ):
                    index.candidates("compact", limit=limit)
        finally:
            connection.close()
        signal = alias_module.AliasExpansionSignal(documents, load_aliases(FIXTURES))
        with self.assertRaises(Phase4CValidationError):
            signal.expand("Borel Lebesgue theorem", limit=0)

    def test_no_signal_exceeds_the_candidate_bound(self) -> None:
        for entry in frozen_report()["results"]:
            with self.subTest(query=entry["id"]):
                self.assertLessEqual(
                    len(entry["lexical_candidate_ids"]),
                    BOUNDS.max_candidates_per_signal,
                )
                self.assertLessEqual(
                    len(entry["fused_candidate_ids"]),
                    2 * BOUNDS.max_candidates_per_signal,
                )
                self.assertEqual(entry["top_k"], TOP_K_BY_CATEGORY[entry["category"]])
                self.assertLessEqual(len(entry["ordered_ids"]), entry["top_k"])
                self.assertEqual(
                    entry["query_bytes"], len(entry["query"].encode("utf-8"))
                )
                self.assertLessEqual(entry["query_bytes"], BOUNDS.max_query_bytes)

    def test_single_exception_class_is_a_value_error(self) -> None:
        self.assertTrue(issubclass(Phase4CValidationError, ValueError))


# --------------------------------------------------------------------------
# 13. External cost and import surface
# --------------------------------------------------------------------------


class Phase4CExternalCostTests(unittest.TestCase):
    STDLIB_ALLOWLIST = {
        "__future__",
        "argparse",
        "collections",
        "dataclasses",
        "hashlib",
        "json",
        "pathlib",
        "re",
        "sqlite3",
        "time",
        "typing",
        "unicodedata",
    }

    def _sources(self) -> list[Path]:
        modules = sorted(PACKAGE_DIR.glob("*.py"))
        self.assertGreaterEqual(len(modules), 8)
        return [*modules, CLI_SOURCE]

    def test_zero_external_cost_is_measured_with_the_network_blocked(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network attempted")
        ), patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("DNS attempted")
        ):
            report = evaluate_hybrid(FIXTURES)
        for name in (
            "network_calls",
            "model_or_api_calls",
            "downloaded_artifacts",
            "external_spend_usd",
        ):
            self.assertEqual(report["metrics"][name], 0)
        self.assertEqual(
            report["gate_evaluation"]["external_spend_usd"]["status"], "pass"
        )

    def test_every_module_imports_only_the_standard_library(self) -> None:
        for source in self._sources():
            roots: set[str] = set()
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    # Every alias, not just the first: `import json, socket`
                    # must fail this check.
                    roots |= {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue  # a relative import stays inside this package
                    roots.add((node.module or "").split(".")[0])
            with self.subTest(module=source.name):
                self.assertLessEqual(roots, self.STDLIB_ALLOWLIST)

    def test_import_allowlist_check_sees_every_alias(self) -> None:
        tree = ast.parse("import json, socket\n")
        node = next(item for item in ast.walk(tree) if isinstance(item, ast.Import))
        self.assertEqual({alias.name for alias in node.names}, {"json", "socket"})

    def test_no_module_names_a_network_or_process_surface(self) -> None:
        forbidden = (
            "socket",
            "urllib",
            "http",
            "subprocess",
            "requests",
            "ctypes",
            "asyncio",
            "importlib",
        )
        for source in self._sources():
            text = source.read_text(encoding="utf-8")
            for name in forbidden:
                with self.subTest(module=source.name, name=name):
                    self.assertNotIn(name, text)
            with self.subTest(module=source.name, name="dunder-import"):
                self.assertNotIn("__" + "import" + "__", text)

    def test_no_module_reaches_another_phase_or_a_spike(self) -> None:
        # ADR-0031 scope: this slice reads the frozen Phase 4C fixtures only.
        for source in self._sources():
            text = source.read_text(encoding="utf-8")
            for name in (
                "phase3a",
                "phase3b",
                "phase4a",
                "phase4b",
                "phase5",
                "phase6",
                "synthesis",
                "spikes",
            ):
                with self.subTest(module=source.name, name=name):
                    self.assertNotIn(f"import {name}", text)
                    self.assertNotIn(f"from {name}", text)
                    self.assertNotIn(f"from .{name}", text)
                    self.assertNotIn(f"from ..{name}", text)


# --------------------------------------------------------------------------
# 14. Pinned measured values, separate from the proposed thresholds
# --------------------------------------------------------------------------


class Phase4CPinnedMeasurementTests(unittest.TestCase):
    def test_measured_metrics_are_pinned(self) -> None:
        metrics = frozen_report()["metrics"]
        self.assertEqual(set(metrics), set(MEASURED_METRICS))
        for name, expected in MEASURED_METRICS.items():
            with self.subTest(metric=name):
                if isinstance(expected, float):
                    self.assertAlmostEqual(metrics[name], expected, places=12)
                else:
                    self.assertEqual(metrics[name], expected)

    def test_measured_support_counts_are_pinned(self) -> None:
        support = frozen_report()["metric_support"]
        self.assertEqual(set(support), set(MEASURED_SUPPORT))
        for name, (numerator, denominator) in MEASURED_SUPPORT.items():
            with self.subTest(metric=name):
                self.assertEqual(support[name]["numerator"], numerator)
                self.assertEqual(support[name]["denominator"], denominator)
                self.assertTrue(support[name]["defined"])

    def test_measured_gate_statuses_and_summary_are_pinned(self) -> None:
        report = frozen_report()
        self.assertEqual(
            {key: value["status"] for key, value in report["gate_evaluation"].items()},
            MEASURED_GATE_STATUS,
        )
        self.assertEqual(report["gate_summary"], MEASURED_GATE_SUMMARY)
        self.assertEqual(set(report["gate_evaluation"]), set(THRESHOLD_KEYS))

    def test_measured_values_are_not_the_proposed_thresholds(self) -> None:
        report = frozen_report()
        thresholds = report["proposed_thresholds"]
        self.assertEqual(thresholds["applicability_precision_at_5"], 1.0)
        self.assertEqual(thresholds["renamed_known_result_recall_at_10"], 1.0)
        self.assertEqual(thresholds["duplicate_rate_at_5_maximum"], 0.05)
        # The measured applicability precision is strictly below its gate. This
        # slice does not meet that gate and the suite records the fact.
        self.assertLess(
            report["metrics"]["applicability_precision_at_5"],
            thresholds["applicability_precision_at_5"],
        )
        self.assertEqual(MEASURED_GATE_STATUS["applicability_precision_at_5"], "fail")

    def test_ordered_ids_are_pinned_per_query(self) -> None:
        results = result_by_id(frozen_report())
        self.assertEqual(set(results), set(MEASURED_ORDERED_IDS))
        for query_id, expected in MEASURED_ORDERED_IDS.items():
            with self.subTest(query=query_id):
                self.assertEqual(tuple(results[query_id]["ordered_ids"]), expected)

    def test_demotions_are_pinned_per_query(self) -> None:
        results = result_by_id(frozen_report())
        for query_id, expected in MEASURED_DEMOTED_IDS.items():
            with self.subTest(query=query_id):
                self.assertEqual(tuple(results[query_id]["demoted_ids"]), expected)

    def test_hybrid_does_not_worsen_a_metric_the_baseline_already_met(self) -> None:
        metrics = frozen_report()["metrics"]
        for name in (
            "necessary_lemma_recall_at_5",
            "contradiction_recall_at_5",
            "notation_variant_recall_at_5",
        ):
            with self.subTest(metric=name):
                self.assertGreaterEqual(metrics[name], BASELINE_METRICS[name])
        self.assertLessEqual(
            metrics["duplicate_rate_at_5"], BASELINE_METRICS["duplicate_rate_at_5"]
        )
        # The required gain: the renamed gate moves from 0.0 to 1.0.
        self.assertGreater(
            metrics["renamed_known_result_recall_at_10"],
            BASELINE_METRICS["renamed_known_result_recall_at_10"],
        )
        # And the honest non-gain: applicability precision does not move.
        self.assertEqual(
            metrics["applicability_precision_at_5"],
            BASELINE_METRICS["applicability_precision_at_5"],
        )

    def test_why_the_applicability_gate_cannot_be_met_by_demotion(self) -> None:
        """The measured failure has two causes; both are recorded here.

        1. On three of four applicability queries the hedge demotes exactly the
           inapplicable relevant document, but the fused candidate set is no
           larger than top-k, so a demotion-only reordering cannot remove it
           from the retrieved set.
        2. On `applicability-selfadjoint` the same-sentence scope rule does not
           fire at all: the self-disclaiming sentence of
           `unbounded-spectral-mismatch` shares no token with that query.
        """

        results = result_by_id(frozen_report())
        for query_id in (
            "applicability-spectral",
            "applicability-certificate",
            "applicability-compactness",
            "applicability-selfadjoint",
        ):
            entry = results[query_id]
            with self.subTest(query=query_id):
                self.assertLessEqual(len(entry["fused_candidate_ids"]), entry["top_k"])
        for query_id in (
            "applicability-spectral",
            "applicability-certificate",
            "applicability-compactness",
        ):
            entry = results[query_id]
            inapplicable_relevant = {
                identifier
                for identifier in entry["relevant_ids"]
                if identifier not in entry["applicable_ids"]
            }
            with self.subTest(query=query_id):
                self.assertTrue(inapplicable_relevant <= set(entry["demoted_ids"]))
                # Demoted, still retrieved: the demotion had nowhere to go.
                self.assertTrue(inapplicable_relevant <= set(entry["ordered_ids"]))
        self.assertEqual(results["applicability-selfadjoint"]["demoted_ids"], [])
        self.assertIn(
            "unbounded-spectral-mismatch",
            results["applicability-selfadjoint"]["inapplicable_retrieved_ids"],
        )

    def test_schema_version_and_method_are_pinned(self) -> None:
        self.assertEqual(SCHEMA_VERSION, "adaivy.phase4c-hybrid-retrieval.v1")
        self.assertEqual(frozen_report()["schema_version"], SCHEMA_VERSION)
        self.assertEqual(frozen_report()["method"], benchmark_module.METHOD)
        self.assertEqual(benchmark_module.METHOD, "phase4c-hybrid-score-space-fusion")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class Phase4CCliTests(unittest.TestCase):
    def test_benchmark_exits_one_on_a_measured_gate_failure(self) -> None:
        from math_research.phase4c_cli import main

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            status = main(
                ["benchmark", "--fixtures", str(FIXTURES), "--output", str(output)]
            )
            self.assertEqual(status, 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["content_hash"], frozen_report()["content_hash"])
            self.assertEqual(output.read_bytes(), canonical_bytes(report))
            self.assertEqual(main(["inspect", str(output)]), 1)

    def test_missing_fixtures_exit_two(self) -> None:
        from math_research.phase4c_cli import main

        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                main(["benchmark", "--fixtures", str(Path(directory) / "absent")]), 2
            )
            self.assertEqual(main(["inspect", str(Path(directory) / "absent.json")]), 2)

    def test_inspect_rejects_a_tampered_report(self) -> None:
        from math_research.phase4c_cli import main

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            report = json.loads(json.dumps(frozen_report()))
            report["metrics"]["applicability_precision_at_5"] = 1.0
            path.write_bytes(canonical_bytes(report))
            self.assertEqual(main(["inspect", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
