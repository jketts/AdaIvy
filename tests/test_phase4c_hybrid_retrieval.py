"""Acceptance suite for the bounded Phase 4C hybrid-retrieval slice.

Per ADR-0026 and the "Consequences" sections of ADR-0031 and ADR-0046, this
suite is the only executable record of this slice's thresholds, and each
forbidden outcome must be demonstrated impossible rather than left untested. So
the tests are written as properties over the whole frozen query set, not as a
happy path:

* label separation -- a token that exists only in an id or a classification
  label retrieves nothing, and mutating every applicability, source-class and
  duplicate-group value leaves the suppression set unchanged;
* suppression is removal, not promotion -- over all fifteen queries the hedge
  never raises a fused score, never introduces a document, and the retained
  ordering is an order-preserving subsequence of the pre-suppression ordering;
* suppression is not hiding -- every suppressed candidate keeps a full hit
  record with its cue evidence and its pre-suppression rank, every query reports
  `suppressed_ids` and `suppressed_inapplicable_ids`, and the non-gated
  disclosure metric keeps the pre-suppression value recomputable;
* the scope unit -- scope blocks union a sentence with exactly its immediate
  predecessor when the sentence opens with an anaphor, the relation is not
  transitive, and the anaphor tuple is frozen and closed;
* cue-class partition -- the two classes are disjoint and byte-frozen,
  object-level cues cannot suppress, and neither contradiction gold is
  suppressed;
* cue neutrality -- with the suppressing table emptied the fused ordering is
  exactly the pure lexical ordering and nothing is suppressed;
* alias hygiene -- no document identifier anywhere in the alias fixture, at
  least five entries exercised by no query and matching no document, and
  removing one exercised entry fails exactly its own query;
* honest metrics -- zero-denominator ratios are `None`/`undetermined`, never a
  passing zero, including under total retrieval collapse, and the CLI still
  exits 1 and still emits a report when a gate fails;
* determinism, bounds, zero external cost, and pinned measured values kept
  separate from the proposed thresholds.

Measured values below are OBSERVATIONS, not targets. They are pinned so that any
retrieval, cue, weighting, fusion, or metric change has to be a deliberate edit
to this file. ADR-0031 measured `applicability_precision_at_5` at `0.6` with the
gate unmet; that number is not deleted here, it is retained as the pinned value
of the non-gated disclosure metric.
"""

from __future__ import annotations

import ast
import dataclasses
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
from math_research.phase4c import bounds as bounds_module
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
    # MEASURED under ADR-0046. ADR-0031 measured 0.6 here with the gate unmet,
    # for two causes it recorded: a demotion-only signal cannot move a metric
    # whose candidate sets are already inside the top-k cutoff, and the frozen
    # same-sentence scope unit never fired on `applicability-selfadjoint`.
    # ADR-0046 replaces demotion with removal and the sentence with the
    # anaphor-resolved scope block. The 0.6 is not deleted: it is the pinned
    # value of the non-gated disclosure metric two lines below.
    "applicability_precision_at_5": 1.0,
    "applicability_precision_at_5_pre_suppression": 0.6,
    "contradiction_recall_at_5": 1.0,
    "notation_variant_recall_at_5": 1.0,
    "renamed_known_result_recall_at_10": 1.0,
    "duplicate_rate_at_5": 1 / 42,
    "external_spend_usd": 0,
    "network_calls": 0,
    "model_or_api_calls": 0,
    "downloaded_artifacts": 0,
}
MEASURED_SUPPORT = {
    "necessary_lemma_recall_at_5": (3, 3),
    "applicability_precision_at_5": (6, 6),
    "applicability_precision_at_5_pre_suppression": (6, 10),
    "contradiction_recall_at_5": (2, 2),
    "notation_variant_recall_at_5": (2, 2),
    "renamed_known_result_recall_at_10": (4, 4),
    "duplicate_rate_at_5": (1, 42),
}
MEASURED_GATE_STATUS = {
    "necessary_lemma_recall_at_5": "pass",
    "applicability_precision_at_5": "pass",
    "contradiction_recall_at_5": "pass",
    "notation_variant_recall_at_5": "pass",
    "renamed_known_result_recall_at_10": "pass",
    "duplicate_rate_at_5_maximum": "pass",
    "external_spend_usd": "pass",
}
MEASURED_GATE_SUMMARY = {"pass": 7, "fail": 0, "undetermined": 0, "overall": "pass"}
DISCLOSURE_METRIC = "applicability_precision_at_5_pre_suppression"

# Measured lexical-baseline values on the same extended fixtures, for the
# "may not worsen a metric the baseline already met" comparison. Untouched by
# ADR-0046: these are the lexical baseline's own numbers, not this slice's.
BASELINE_METRICS = {
    "necessary_lemma_recall_at_5": 1.0,
    "applicability_precision_at_5": 0.6,
    "contradiction_recall_at_5": 1.0,
    "notation_variant_recall_at_5": 1.0,
    "renamed_known_result_recall_at_10": 0.0,
    "duplicate_rate_at_5": 1 / 50,
}

# The gate values, as a frozen literal. `proposed_thresholds` is asserted
# byte-equal to this, so a gate cannot have been lowered to meet a measurement.
FROZEN_PROPOSED_THRESHOLDS = {
    "applicability_precision_at_5": 1.0,
    "contradiction_recall_at_5": 1.0,
    "duplicate_rate_at_5_maximum": 0.05,
    "external_spend_usd": 0,
    "necessary_lemma_recall_at_5": 1.0,
    "notation_variant_recall_at_5": 1.0,
    "renamed_known_result_recall_at_10": 1.0,
}

# The cue tables, as frozen literals. ADR-0046 changed the scope unit and did
# not touch either table; pinning them as literals is what makes a later cue
# addition a visible edit to this file rather than a silent lexicon fit.
FROZEN_SELF_DISCLAIMING_CUES = (
    "does not provide",
    "inapplicable",
    "insufficient",
    "may look",
    "states no",
    "as stated",
)
FROZEN_OBJECT_LEVEL_CUES = ("fails", "violates", "counterexample")
# The anaphor list, as a frozen literal. Six entries, closed, lowercase, single
# tokens, sentence-initial position only.
FROZEN_ANAPHOR_PRONOUNS = ("it", "this", "that", "these", "those", "they")
# The only two corpus documents whose scope-block partition differs from their
# sentence partition, i.e. the only two that open a sentence with an anaphor.
# `renamed-cover-result` carries no self-disclaiming cue anywhere, so it is not
# suppressible under any scope unit; it is listed to show the block rule is a
# property of the prose and not of the applicability label.
FROZEN_SCOPE_BLOCK_UNION_DOCUMENT_IDS = (
    "renamed-cover-result",
    "unbounded-spectral-mismatch",
)
# The corpus-wide suppressed set, as a frozen LITERAL. It is deliberately NOT
# read from the manifest's `applicability` field. It does coincide exactly with
# the corpus's three non-applicable documents; that coincidence is a property of
# how the fixture was authored -- the author wrote the disclaimers into those
# three documents -- and not evidence that the rule reads the label.
# `test_suppression_is_invariant_under_every_mutated_label` is what shows the
# rule does not read the label, and ADR-0046 defers the negative control that
# would show it does not over-fire.
FROZEN_SUPPRESSED_DOCUMENT_IDS = (
    "optimization-distractor",
    "topology-distractor",
    "unbounded-spectral-mismatch",
)

# The three orderings, pinned side by side so a removal is visible as a removal:
# the pre-suppression ordering, the retained ordering the query returns, and the
# suppressed ids. `ordered_ids` must be an order-preserving subsequence of
# `pre_suppression_ordered_ids` for every query.
MEASURED_PRE_SUPPRESSION_ORDERED_IDS = {
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
        "spectral-lemma", "finite-dimensional-spectral",
        "renamed-uniform-bound-result", "unbounded-spectral-mismatch",
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
        "finite-dimensional-spectral", "topology-distractor",
        "unbounded-spectral-mismatch",
    ),
    "renamed-maximal-chain": (
        "renamed-maximal-chain-result", "separation-lemma", "spectral-lemma",
        "compactness-lemma",
    ),
    "renamed-container-count": ("renamed-container-count-result", "renamed-cover-result"),
    "renamed-known": (
        "renamed-cover-result", "finite-dimensional-spectral",
        "topology-distractor", "unbounded-spectral-mismatch",
    ),
}
MEASURED_ORDERED_IDS = {
    "lemma-compactness": (
        "compactness-lemma", "spectral-lemma", "banach-notation",
        "separation-lemma", "finite-dimensional-spectral",
    ),
    "lemma-spectral": ("spectral-lemma", "finite-dimensional-spectral"),
    "lemma-separation": ("separation-lemma", "compactness-lemma", "renamed-cover-result"),
    "applicability-spectral": ("finite-dimensional-spectral", "spectral-lemma"),
    "applicability-certificate": (
        "duplicate-certificate-a", "duplicate-certificate-b",
        "renamed-maximal-chain-result", "renamed-uniform-bound-result",
    ),
    "applicability-compactness": (
        "compactness-lemma", "finite-dimensional-spectral", "separation-lemma",
    ),
    "applicability-selfadjoint": (
        "spectral-lemma", "finite-dimensional-spectral", "renamed-uniform-bound-result",
    ),
    "contradiction-boundary": (
        "boundary-contradiction", "monotonicity-contradiction", "renamed-cover-result",
    ),
    "contradiction-monotonicity": ("monotonicity-contradiction", "boundary-contradiction"),
    "notation-banach": ("banach-notation", "boundary-contradiction"),
    "notation-psd": ("psd-notation", "finite-dimensional-spectral"),
    "renamed-uniform-bound": (
        "renamed-uniform-bound-result", "banach-notation", "finite-dimensional-spectral",
    ),
    "renamed-maximal-chain": (
        "renamed-maximal-chain-result", "separation-lemma", "spectral-lemma",
        "compactness-lemma",
    ),
    "renamed-container-count": ("renamed-container-count-result", "renamed-cover-result"),
    "renamed-known": ("renamed-cover-result", "finite-dimensional-spectral"),
}
MEASURED_SUPPRESSED_IDS = {
    "lemma-compactness": ("topology-distractor", "unbounded-spectral-mismatch"),
    "lemma-spectral": ("unbounded-spectral-mismatch",),
    "lemma-separation": (),
    "applicability-spectral": ("topology-distractor", "unbounded-spectral-mismatch"),
    "applicability-certificate": ("optimization-distractor",),
    "applicability-compactness": ("topology-distractor", "unbounded-spectral-mismatch"),
    "applicability-selfadjoint": ("unbounded-spectral-mismatch",),
    "contradiction-boundary": (),
    "contradiction-monotonicity": (),
    "notation-banach": (),
    "notation-psd": ("unbounded-spectral-mismatch",),
    "renamed-uniform-bound": ("topology-distractor", "unbounded-spectral-mismatch"),
    "renamed-maximal-chain": (),
    "renamed-container-count": (),
    "renamed-known": ("topology-distractor", "unbounded-spectral-mismatch"),
}
# Total retrieved hits at the duplicate cutoff, after and before suppression.
# The duplicate numerator stays 1: no suppression promotes a document into the
# cutoff, and no applicable duplicate is ever removed.
MEASURED_RETRIEVED_HITS_AT_5 = 42
MEASURED_PRE_SUPPRESSION_HITS_AT_5 = 54

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


def _sentence_scope_verdict(documents, query: str, document_id: str) -> bool:
    """The ADR-0031 SENTENCE scope rule, reimplemented here independently.

    The production signal no longer offers the sentence unit, so the older rule
    is spelled out here rather than reached through a flag. It is used to show
    that the improvement is attributable to the scope unit: under the sentence
    unit `applicability-selfadjoint` suppresses nothing, which is exactly the
    `6/7 = 0.857` ADR-0031 measured for an exclusion variant.
    """

    terms = set(text_module.tokens(query))
    document = next(item for item in documents if item.identifier == document_id)
    patterns = [text_module.cue_pattern(cue) for cue in SELF_DISCLAIMING_CUES]
    for sentence in text_module.sentences(document.text):
        if not terms & set(text_module.tokens(sentence)):
            continue
        folded = sentence.casefold()
        if any(pattern.search(folded) for pattern in patterns):
            return True
    return False


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


class Phase4CSuppressionIsRemovalOnlyTests(unittest.TestCase):
    """ADR-0046 invariants 1-4, as properties over all fifteen queries.

    Owner ruling 2 made the removal-not-promotion property a condition of
    reversing ADR-0031's demotion-only constraint, so the subsequence test below
    is an explicit order-preserving walk. A set comparison would accept a
    promotion and is therefore not sufficient.
    """

    def setUp(self) -> None:
        self.with_hedge = frozen_report()
        self.without_hedge = evaluate_hybrid(FIXTURES, self_disclaiming_cues=())

    def test_hedge_never_raises_a_fused_score_over_every_query(self) -> None:
        hedged = {item["id"]: item for item in self.with_hedge["operational"]["results"]}
        plain = {item["id"]: item for item in self.without_hedge["operational"]["results"]}
        self.assertEqual(len(hedged), BOUNDS.query_count)
        self.assertEqual(set(hedged), set(plain))
        compared = lowered = 0
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
                if score < plain_scores[document_id]:
                    lowered += 1
        self.assertGreater(compared, 0)
        # The comparison is not vacuous: some scores really are lowered.
        self.assertGreater(lowered, 0)

    def test_hedge_never_introduces_a_document_over_every_query(self) -> None:
        hedged = result_by_id(self.with_hedge)
        plain = result_by_id(self.without_hedge)
        for query_id, entry in hedged.items():
            with self.subTest(query=query_id):
                # FORBIDDEN: introducing a document. The pre-suppression
                # candidate set is byte-identical to the empty-cue-table set
                # once both are canonically ordered.
                self.assertEqual(
                    sorted(entry["fused_candidate_ids"]),
                    sorted(plain[query_id]["fused_candidate_ids"]),
                )
                self.assertLessEqual(
                    set(entry["ordered_ids"]) | set(entry["suppressed_ids"]),
                    set(entry["fused_candidate_ids"]),
                )
                self.assertLessEqual(
                    set(entry["suppressed_ids"]), set(entry["fused_candidate_ids"])
                )
                self.assertLessEqual(
                    set(entry["suppressed_ids"]),
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
                        suppressed=True,
                        self_disclaiming_cues=("insufficient",),
                        object_level_cues=(),
                        scoped_query_terms=("x",),
                    )
                ],
                alias_phrase_points=ALIAS_PHRASE_POINTS,
            )

    def test_the_score_raise_guard_is_reachable_and_used_by_fusion(self) -> None:
        # FORBIDDEN: a verdict raising a fused score. The happy path being
        # monotone is not a demonstration that the guard works, so the guard is
        # called directly with a raised score, and `fuse` is shown to route
        # every candidate through it.
        fusion_module.enforce_no_score_raise("d", 2.0, 2.0)
        fusion_module.enforce_no_score_raise("d", 2.0, 1.0)
        with self.assertRaises(Phase4CValidationError) as caught:
            fusion_module.enforce_no_score_raise("d", 1.0, 2.0)
        self.assertIn("raised the fused score", str(caught.exception))
        source = ast.parse(
            (PACKAGE_DIR / "fusion.py").read_text(encoding="utf-8")
        )
        fuse_body = next(
            node
            for node in ast.walk(source)
            if isinstance(node, ast.FunctionDef) and node.name == "fuse"
        )
        called = {
            node.func.id
            for node in ast.walk(fuse_body)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertIn("enforce_no_score_raise", called)
        self.assertIn("enforce_subsequence", called)

    def test_the_retained_ordering_is_a_subsequence_of_the_pre_suppression_one(
        self,
    ) -> None:
        # FORBIDDEN: promotion. Owner ruling 2's condition. The walk below is
        # written out here rather than delegated to the production helper, so a
        # bug in that helper cannot make this test vacuous.
        def is_subsequence(inner: list[str], outer: list[str]) -> bool:
            position = 0
            for identifier in inner:
                while position < len(outer) and outer[position] != identifier:
                    position += 1
                if position == len(outer):
                    return False
                position += 1
            return True

        self.assertTrue(is_subsequence(["a", "c"], ["a", "b", "c"]))
        self.assertFalse(is_subsequence(["c", "a"], ["a", "b", "c"]))
        self.assertFalse(is_subsequence(["a", "d"], ["a", "b", "c"]))
        checked = 0
        for entry in self.with_hedge["results"]:
            with self.subTest(query=entry["id"]):
                self.assertTrue(
                    is_subsequence(
                        entry["ordered_ids"], entry["pre_suppression_ordered_ids"]
                    ),
                    "suppression reordered or promoted a candidate",
                )
                # And against the untruncated ordering, which is stronger:
                # truncation is not a reordering.
                self.assertTrue(
                    is_subsequence(entry["ordered_ids"], entry["fused_candidate_ids"])
                )
            checked += 1
        self.assertEqual(checked, BOUNDS.query_count)

    def test_the_subsequence_guard_rejects_a_promotion(self) -> None:
        fusion_module.enforce_subsequence(["a", "c"], ["a", "b", "c"])
        for retained_ids in (["c", "a"], ["a", "d"]):
            with self.subTest(retained=retained_ids), self.assertRaises(
                Phase4CValidationError
            ):
                fusion_module.enforce_subsequence(retained_ids, ["a", "b", "c"])

    def test_no_suppressed_document_is_ever_returned(self) -> None:
        observed = 0
        for entry in self.with_hedge["results"]:
            with self.subTest(query=entry["id"]):
                self.assertEqual(
                    set(entry["ordered_ids"]) & set(entry["suppressed_ids"]), set()
                )
                for hit in entry["hits"]:
                    if hit["suppressed"]:
                        self.assertNotIn(hit["document_id"], entry["ordered_ids"])
                        observed += 1
        self.assertGreater(observed, 0)

    def test_an_empty_suppressing_table_suppresses_nothing(self) -> None:
        report = evaluate_hybrid(
            FIXTURES, self_disclaiming_cues=(), alias_signal=EmptyAliasSignal()
        )
        for entry in report["results"]:
            with self.subTest(query=entry["id"]):
                self.assertEqual(entry["suppressed_ids"], [])
                self.assertEqual(entry["suppressed_inapplicable_ids"], [])
                self.assertEqual(
                    entry["ordered_ids"],
                    entry["lexical_candidate_ids"][: entry["top_k"]],
                )
                self.assertEqual(
                    entry["ordered_ids"], entry["pre_suppression_ordered_ids"]
                )

    def test_emptying_the_object_level_table_changes_no_suppression(self) -> None:
        neutralised = result_by_id(evaluate_hybrid(FIXTURES, object_level_cues=()))
        frozen = result_by_id(self.with_hedge)
        for query_id, entry in neutralised.items():
            with self.subTest(query=query_id):
                self.assertEqual(
                    entry["suppressed_ids"], frozen[query_id]["suppressed_ids"]
                )
                self.assertEqual(
                    entry["ordered_ids"], frozen[query_id]["ordered_ids"]
                )

    def test_suppressed_hits_rank_below_every_retained_hit(self) -> None:
        for entry in self.with_hedge["results"]:
            flags = [hit["suppressed"] for hit in entry["hits"]]
            with self.subTest(query=entry["id"]):
                # The pre-suppression ordering still places every suppressed
                # candidate after every retained one, so the flag sequence is
                # monotone. Removal is what moves a metric; the score penalty
                # exists so the disclosed pre-suppression ordering is the one
                # ADR-0031 would have returned.
                self.assertEqual(flags, sorted(flags))


class Phase4CCueClassTests(unittest.TestCase):
    def test_the_cue_tables_are_byte_frozen_literals(self) -> None:
        # FORBIDDEN: a fitted lexicon. ADR-0046 changed the scope unit and must
        # not have changed a cue, so both tables are compared against literals
        # spelled out in this file rather than against themselves.
        self.assertEqual(SELF_DISCLAIMING_CUES, FROZEN_SELF_DISCLAIMING_CUES)
        self.assertEqual(OBJECT_LEVEL_CUES, FROZEN_OBJECT_LEVEL_CUES)
        self.assertEqual(len(FROZEN_SELF_DISCLAIMING_CUES), 6)
        self.assertEqual(len(FROZEN_OBJECT_LEVEL_CUES), 3)
        declared = frozen_report()["declared_method"]["hedging_signal"]
        self.assertEqual(
            declared["self_disclaiming_cues"], list(FROZEN_SELF_DISCLAIMING_CUES)
        )
        self.assertEqual(declared["object_level_cues"], list(FROZEN_OBJECT_LEVEL_CUES))

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

    def test_a_document_with_only_object_level_cues_is_never_suppressed(self) -> None:
        observed = 0
        for entry in frozen_report()["results"]:
            for hit in entry["hits"]:
                if hit["object_level_cues"] and not hit["self_disclaiming_cues"]:
                    observed += 1
                    with self.subTest(query=entry["id"], document=hit["document_id"]):
                        self.assertFalse(hit["suppressed"])
        self.assertGreater(observed, 0)

    def test_neither_contradiction_gold_is_ever_suppressed(self) -> None:
        for entry in frozen_report()["results"]:
            for gold in MEASURED_CONTRADICTION_GOLDS:
                with self.subTest(query=entry["id"], gold=gold):
                    self.assertNotIn(gold, entry["suppressed_ids"])

    def test_no_gold_carries_a_self_disclaiming_cue_anywhere_in_its_body(self) -> None:
        # The load-bearing guard on all five recall gates, asserted corpus-wide
        # rather than per scope unit: if no protected gold contains a
        # self-disclaiming cue ANYWHERE in its bytes, then under ANY scope unit
        # -- sentence, scope block, paragraph, whole document -- no protected
        # gold is suppressible. Widening the scope unit cannot cost recall here.
        documents = load_corpus(FIXTURES)
        queries, _ = load_gold(FIXTURES, documents)
        protected: set[str] = set()
        for query in queries:
            if query.category == "applicability":
                # For an applicability query the inapplicable relevant documents
                # are exactly the ones the signal is meant to remove, so only
                # the applicable ids are protected.
                protected |= set(query.applicable_ids or ())
            else:
                protected |= set(query.relevant_ids)
        self.assertEqual(len(protected), 14)
        patterns = [text_module.cue_pattern(cue) for cue in SELF_DISCLAIMING_CUES]
        checked = 0
        for document in documents:
            if document.identifier not in protected:
                continue
            with self.subTest(document=document.identifier):
                folded = document.text.casefold()
                for cue, pattern in zip(SELF_DISCLAIMING_CUES, patterns, strict=True):
                    self.assertIsNone(pattern.search(folded), cue)
            checked += 1
        self.assertEqual(checked, 14)

    def test_boundary_contradiction_carries_object_level_cues_in_query_scope(self) -> None:
        # This is the exact case a naive negation signal breaks: an applicable
        # contradiction gold whose matched query terms share a scope block with
        # `fails`, `violates`, and `counterexample`.
        documents = load_corpus(FIXTURES)
        signal = HedgingScopeSignal(documents)
        queries, _ = load_gold(FIXTURES, documents)
        query = next(
            item for item in queries if item.identifier == "contradiction-boundary"
        )
        verdict = signal.verdicts(query.query, ["boundary-contradiction"])[0]
        self.assertFalse(verdict.suppressed)
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
            verdict.suppressed,
            "bare `no` suppresses an applicable gold, which is why it is excluded",
        )

    def test_cue_matching_is_word_boundary_anchored(self) -> None:
        pattern = text_module.cue_pattern("is not")
        self.assertIsNone(pattern.search("this note states no theorem"))
        self.assertIsNotNone(pattern.search("the hypothesis is not satisfied"))

    def test_there_is_no_cue_count_threshold_and_no_scope_parameter(self) -> None:
        self.assertIsNone(hedging_module.CUE_COUNT_THRESHOLD)
        declared = frozen_report()["declared_method"]["hedging_signal"]
        self.assertIsNone(declared["cue_count_threshold"])
        self.assertEqual(declared["direction"], "suppression_only")
        # The declared method cannot drift from the method run: the constant and
        # the report must carry the same literal.
        self.assertEqual(
            hedging_module.SCOPE_RULE,
            "matched-query-term-in-same-scope-block-as-self-disclaiming-cue",
        )
        self.assertEqual(declared["scope_rule"], hedging_module.SCOPE_RULE)
        self.assertEqual(declared["scope_block_rule"], text_module.SCOPE_BLOCK_RULE)
        self.assertEqual(declared["sentence_rule"], text_module.SENTENCE_RULE)
        self.assertEqual(
            declared["sentence_split_pattern"], text_module.SENTENCE_SPLIT_PATTERN
        )
        # Antecedent depth is a stated rule, not a tunable window length: the
        # only integer in the declared scope method is the literal 1.
        self.assertEqual(declared["anaphor_antecedent_depth"], 1)
        self.assertEqual(declared["anaphor_pronouns"], list(FROZEN_ANAPHOR_PRONOUNS))

    def test_the_cue_table_hits_exactly_the_non_applicable_documents(self) -> None:
        # Corpus-wide audit of the suppressing table, independent of any query.
        documents = load_corpus(FIXTURES)
        patterns = [text_module.cue_pattern(cue) for cue in SELF_DISCLAIMING_CUES]
        hit = {
            document.identifier
            for document in documents
            if any(
                pattern.search(block.casefold())
                for block in text_module.scope_blocks(document.text)
                for pattern in patterns
            )
        }
        self.assertEqual(hit, set(FROZEN_SUPPRESSED_DOCUMENT_IDS))
        non_applicable = {
            document.identifier
            for document in documents
            if document.applicability != "applicable"
        }
        # The coincidence is disclosed, not relied on: the assertion above is
        # against a literal, and the label-mutation test is what shows the rule
        # does not read `applicability`.
        self.assertEqual(non_applicable, set(FROZEN_SUPPRESSED_DOCUMENT_IDS))


class Phase4CScopeBlockTests(unittest.TestCase):
    """The ADR-0046 scope unit, tested as a unit rule with no query in sight."""

    def test_the_anaphor_list_is_a_frozen_closed_six_tuple(self) -> None:
        # FORBIDDEN: padding the vocabulary until a query passes.
        self.assertEqual(text_module.ANAPHOR_PRONOUNS, FROZEN_ANAPHOR_PRONOUNS)
        self.assertEqual(len(FROZEN_ANAPHOR_PRONOUNS), 6)
        self.assertEqual(len(set(FROZEN_ANAPHOR_PRONOUNS)), 6)
        for pronoun in FROZEN_ANAPHOR_PRONOUNS:
            with self.subTest(pronoun=pronoun):
                self.assertEqual(pronoun, pronoun.lower())
                self.assertEqual(text_module.tokens(pronoun), (pronoun,))

    def test_an_anaphor_initial_sentence_unions_with_exactly_its_predecessor(
        self,
    ) -> None:
        blocks = text_module.scope_blocks("Alpha holds. It does not provide beta.")
        self.assertEqual(
            blocks, ("Alpha holds.", "Alpha holds. It does not provide beta.")
        )

    def test_a_non_anaphor_sentence_does_not_union(self) -> None:
        blocks = text_module.scope_blocks("Alpha holds. Beta does not provide gamma.")
        self.assertEqual(blocks, ("Alpha holds.", "Beta does not provide gamma."))

    def test_the_first_sentence_never_unions(self) -> None:
        self.assertEqual(text_module.scope_blocks("It fails."), ("It fails.",))

    def test_empty_text_yields_no_blocks(self) -> None:
        for empty in ("", "   ", "\n\t"):
            with self.subTest(text=repr(empty)):
                self.assertEqual(text_module.scope_blocks(empty), ())
                self.assertEqual(text_module.sentences(empty), ())

    def test_a_mid_sentence_anaphor_creates_no_union(self) -> None:
        source = "Alpha holds. Beta shows that it fails."
        self.assertEqual(
            text_module.scope_blocks(source), text_module.sentences(source)
        )

    def test_the_relation_is_not_transitive(self) -> None:
        # FORBIDDEN: an unbounded window. Chaining would make the scope a
        # window, a window has a length, and a length read off a corpus is the
        # forbidden outcome. The third block contains the second sentence and
        # NOT the first.
        blocks = text_module.scope_blocks("S one. It two. It three.")
        self.assertEqual(len(blocks), 3)
        self.assertEqual(blocks[2], "It two. It three.")
        self.assertNotIn("S one", blocks[2])
        self.assertEqual(blocks[1], "S one. It two.")

    def test_each_block_covers_exactly_one_sentence_plus_at_most_one_more(self) -> None:
        for document in load_corpus(FIXTURES):
            units = text_module.sentences(document.text)
            blocks = text_module.scope_blocks(document.text)
            with self.subTest(document=document.identifier):
                self.assertEqual(len(blocks), len(units))
                for index, block in enumerate(blocks):
                    self.assertIn(units[index], block)
                    if block != units[index]:
                        self.assertGreater(index, 0)
                        self.assertEqual(block, f"{units[index - 1]} {units[index]}")

    def test_the_block_partition_reduces_to_the_sentence_partition_elsewhere(
        self,
    ) -> None:
        differing = tuple(
            sorted(
                document.identifier
                for document in load_corpus(FIXTURES)
                if text_module.scope_blocks(document.text)
                != text_module.sentences(document.text)
            )
        )
        # Only two of the seventeen documents open a sentence with an anaphor,
        # so for the other fifteen the new scope unit is the old one exactly.
        self.assertEqual(differing, FROZEN_SCOPE_BLOCK_UNION_DOCUMENT_IDS)

    def test_the_shared_tokenizer_behaviour_is_unchanged(self) -> None:
        # `text` is shared by all three signals, so the scope-block addition
        # must not perturb the tokenizer or the phrase matcher.
        self.assertEqual(text_module.NORMALIZATION_FORM, "NFC")
        self.assertEqual(text_module.TOKEN_PATTERN, r"[^\W_]+")
        self.assertEqual(
            text_module.SENTENCE_RULE,
            "nfc-collapse-whitespace-then-split-after-terminal-period-question-exclamation",
        )
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


class Phase4CCueNeutralityTests(unittest.TestCase):
    def test_removing_every_suppressing_cue_yields_the_pure_lexical_ordering(self) -> None:
        report = evaluate_hybrid(
            FIXTURES, self_disclaiming_cues=(), alias_signal=EmptyAliasSignal()
        )
        for entry in report["results"]:
            with self.subTest(query=entry["id"]):
                self.assertEqual(entry["suppressed_ids"], [])
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
                # An ordering change implies a suppression. Nothing else moved.
                self.assertTrue(hedged[query_id]["suppressed_ids"])

    def test_suppression_is_invariant_under_every_mutated_label(self) -> None:
        # FORBIDDEN: the applicability label as a retrieval feature. Every
        # `applicability`, `source_class` and `duplicate_group` value is mutated
        # in an in-memory copy of the corpus metadata and the suppression set is
        # asserted unchanged, query by query. This is the executable answer to
        # "does the rule secretly read the label"; it is done at the signal
        # level because the gold loader validates `applicable_ids` against the
        # manifest's labels and would reject a mutated fixture on disk.
        documents = load_corpus(FIXTURES)
        queries, _ = load_gold(FIXTURES, documents)
        rotated_applicability = {
            "applicable": "insufficient_evidence",
            "insufficient_evidence": "incompatible_hypotheses",
            "incompatible_hypotheses": "applicable",
        }
        rotated_source = {
            "primary": "informal",
            "secondary": "primary",
            "historical": "secondary",
            "informal": "historical",
        }
        mutated = tuple(
            dataclasses.replace(
                document,
                applicability=rotated_applicability[document.applicability],
                source_class=rotated_source[document.source_class],
                duplicate_group=(
                    None
                    if document.duplicate_group is None
                    else f"mutated-{document.duplicate_group}"
                ),
            )
            for document in documents
        )
        for original, changed in zip(documents, mutated, strict=True):
            self.assertNotEqual(original.applicability, changed.applicability)
            self.assertNotEqual(original.source_class, changed.source_class)
            self.assertEqual(original.text, changed.text)
        baseline = HedgingScopeSignal(documents)
        perturbed = HedgingScopeSignal(mutated)
        identifiers = [document.identifier for document in documents]
        observed = 0
        for query in queries:
            before = {
                verdict.document_id: verdict.suppressed
                for verdict in baseline.verdicts(query.query, identifiers)
            }
            after = {
                verdict.document_id: verdict.suppressed
                for verdict in perturbed.verdicts(query.query, identifiers)
            }
            with self.subTest(query=query.identifier):
                self.assertEqual(before, after)
            observed += sum(before.values())
        self.assertGreater(observed, 0)

    def test_the_suppressed_set_is_a_frozen_literal_not_a_label_lookup(self) -> None:
        # Disclosure, per ADR-0046. The corpus-wide suppressed set is asserted
        # against a literal enumerated in this file. It coincides exactly with
        # the corpus's three non-applicable documents; that coincidence is a
        # property of how the fixture was authored -- the author wrote the
        # disclaimers into those three documents -- and is not evidence that the
        # rule reads the label. `test_suppression_is_invariant_under_every_
        # mutated_label` is what shows the rule does not read it, and ADR-0046
        # defers the negative control that would show it does not over-fire.
        suppressed: set[str] = set()
        for entry in frozen_report()["results"]:
            suppressed |= set(entry["suppressed_ids"])
        self.assertEqual(tuple(sorted(suppressed)), FROZEN_SUPPRESSED_DOCUMENT_IDS)
        self.assertEqual(len(FROZEN_SUPPRESSED_DOCUMENT_IDS), 3)


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
            # Every gate passes under ADR-0046, so the fresh process must exit
            # 0. Tolerating exit 1 here would let a regression to a failing
            # gate pass this determinism check unnoticed.
            self.assertEqual(completed.returncode, 0, completed.stderr)
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
        for name in (
            "applicability_precision_at_5",
            DISCLOSURE_METRIC,
            "duplicate_rate_at_5",
        ):
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
                    "suppressed_ids",
                    "suppressed_inapplicable_ids",
                    "pre_suppression_ordered_ids",
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
        # No inapplicable hit is RETAINED any more, which is the improvement.
        # The visibility obligation therefore moves rather than disappears: the
        # inapplicable hits that were retrieved and then removed are reported
        # per query, so the report still shows every one of them.
        self.assertFalse(any(item["inapplicable_retrieved_ids"] for item in results))
        self.assertTrue(any(item["suppressed_inapplicable_ids"] for item in results))
        self.assertEqual(
            sorted(
                {
                    identifier
                    for item in results
                    for identifier in item["suppressed_inapplicable_ids"]
                }
            ),
            list(FROZEN_SUPPRESSED_DOCUMENT_IDS),
        )

    def test_no_suppressed_candidate_leaves_the_report(self) -> None:
        # FORBIDDEN: hiding an inapplicable hit. Suppression removes a candidate
        # from the returned list and from nothing else, so every suppressed
        # candidate must still carry a full hit record with its cue evidence,
        # its scoped query terms, and its pre-suppression rank.
        documents = load_corpus(FIXTURES)
        applicability = {
            document.identifier: document.applicability for document in documents
        }
        audited = 0
        for entry in frozen_report()["results"]:
            hits = {hit["document_id"]: hit for hit in entry["hits"]}
            with self.subTest(query=entry["id"]):
                # Nothing leaves the report: the hit records are exactly the
                # pre-suppression candidate set.
                self.assertEqual(set(hits), set(entry["fused_candidate_ids"]))
                self.assertEqual(
                    sorted(hits),
                    sorted(set(entry["ordered_ids"]) | set(entry["suppressed_ids"])
                           | set(entry["fused_candidate_ids"])),
                )
                self.assertEqual(
                    sorted(entry["suppressed_ids"]),
                    sorted(
                        hit["document_id"] for hit in entry["hits"] if hit["suppressed"]
                    ),
                )
                self.assertEqual(
                    entry["suppressed_inapplicable_ids"],
                    sorted(
                        identifier
                        for identifier in entry["suppressed_ids"]
                        if applicability[identifier] != "applicable"
                    ),
                )
                ranks = [hit["pre_suppression_rank"] for hit in entry["hits"]]
                self.assertEqual(ranks, list(range(1, len(entry["hits"]) + 1)))
                for identifier in entry["suppressed_ids"]:
                    hit = hits[identifier]
                    self.assertTrue(hit["suppressed"])
                    self.assertTrue(hit["self_disclaiming_cues"])
                    self.assertTrue(hit["scoped_query_terms"])
                    self.assertGreaterEqual(hit["pre_suppression_rank"], 1)
                    audited += 1
        self.assertEqual(audited, sum(len(v) for v in MEASURED_SUPPRESSED_IDS.values()))

    def test_the_pre_suppression_number_stays_recomputable_from_the_report(self) -> None:
        # FORBIDDEN: hiding the pre-improvement number. The disclosure metric
        # holds ADR-0031's measured 0.6 and is recomputed here from `results`
        # by running the same metric definition over the pre-suppression
        # ordering, so the report cannot claim a disclosure it does not support.
        report = frozen_report()
        self.assertEqual(report["metrics"][DISCLOSURE_METRIC], 0.6)
        self.assertEqual(
            report["metric_support"][DISCLOSURE_METRIC],
            {"numerator": 6, "denominator": 10, "defined": True},
        )
        recomputed = benchmark_module.applicability_precision(
            report["results"], "pre_suppression_ordered_ids"
        )
        self.assertEqual((recomputed.numerator, recomputed.denominator), (6, 10))
        self.assertEqual(recomputed.value, report["metrics"][DISCLOSURE_METRIC])
        # And the gated metric, over the retained ordering, is the improvement.
        gated = benchmark_module.applicability_precision(report["results"])
        self.assertEqual((gated.numerator, gated.denominator), (6, 6))
        self.assertEqual(gated.value, report["metrics"]["applicability_precision_at_5"])
        self.assertEqual(
            report["metrics"][DISCLOSURE_METRIC],
            BASELINE_METRICS["applicability_precision_at_5"],
        )

    def test_the_disclosure_metric_can_never_pass_or_fail_a_gate(self) -> None:
        report = frozen_report()
        self.assertIn(DISCLOSURE_METRIC, report["metrics"])
        self.assertNotIn(DISCLOSURE_METRIC, THRESHOLD_KEYS)
        self.assertNotIn(DISCLOSURE_METRIC, report["gate_evaluation"])
        self.assertNotIn(DISCLOSURE_METRIC, report["proposed_thresholds"])
        self.assertNotIn(DISCLOSURE_METRIC, bounds_module.GATE_COMPARISONS)
        self.assertNotIn(
            DISCLOSURE_METRIC,
            {value[0] for value in bounds_module.GATE_COMPARISONS.values()},
        )
        self.assertEqual(benchmark_module.DISCLOSURE_METRIC, DISCLOSURE_METRIC)

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
        # The duplicate denominator is the retrieved-hit total at the cutoff,
        # and it is the retained total, not the pre-suppression one.
        self.assertEqual(
            support["duplicate_rate_at_5"]["denominator"], MEASURED_RETRIEVED_HITS_AT_5
        )

    def test_the_retrieved_hit_total_fell_only_by_removal(self) -> None:
        results = result_by_id(frozen_report())
        retained = sum(
            min(len(entry["ordered_ids"]), BOUNDS.duplicate_cutoff)
            for entry in results.values()
        )
        pre = sum(
            min(len(entry["pre_suppression_ordered_ids"]), BOUNDS.duplicate_cutoff)
            for entry in results.values()
        )
        self.assertEqual(retained, MEASURED_RETRIEVED_HITS_AT_5)
        self.assertEqual(pre, MEASURED_PRE_SUPPRESSION_HITS_AT_5)
        self.assertLess(retained, pre)
        # The duplicate numerator does not rise. A rise would have proved that
        # suppression promoted a document into the cutoff.
        self.assertEqual(frozen_report()["metric_support"]["duplicate_rate_at_5"][
            "numerator"
        ], 1)

    def test_measured_gate_statuses_and_summary_are_pinned(self) -> None:
        report = frozen_report()
        self.assertEqual(
            {key: value["status"] for key, value in report["gate_evaluation"].items()},
            MEASURED_GATE_STATUS,
        )
        self.assertEqual(report["gate_summary"], MEASURED_GATE_SUMMARY)
        self.assertEqual(set(report["gate_evaluation"]), set(THRESHOLD_KEYS))
        self.assertEqual(len(THRESHOLD_KEYS), 7)

    def test_measured_values_are_not_the_proposed_thresholds(self) -> None:
        # The gates are still READ FROM THE FIXTURE, never from a measurement.
        # Every gate now holds, so "measured is below its gate" no longer
        # separates the two -- what separates them is that `proposed_thresholds`
        # is byte-equal to a literal frozen in this file, so a gate CANNOT have
        # been lowered to meet the measurement.
        report = frozen_report()
        thresholds = report["proposed_thresholds"]
        _queries, loaded = load_gold(FIXTURES, load_corpus(FIXTURES))
        self.assertEqual(thresholds, loaded)
        self.assertEqual(
            canonical_bytes(thresholds), canonical_bytes(FROZEN_PROPOSED_THRESHOLDS)
        )
        self.assertEqual(thresholds["applicability_precision_at_5"], 1.0)
        self.assertEqual(thresholds["renamed_known_result_recall_at_10"], 1.0)
        self.assertEqual(thresholds["duplicate_rate_at_5_maximum"], 0.05)
        self.assertEqual(set(thresholds), set(THRESHOLD_KEYS))
        # The measured applicability precision now EQUALS its gate rather than
        # sitting below it, and the gate value is unchanged from ADR-0031.
        self.assertEqual(
            report["metrics"]["applicability_precision_at_5"],
            thresholds["applicability_precision_at_5"],
        )
        self.assertEqual(MEASURED_GATE_STATUS["applicability_precision_at_5"], "pass")
        # And the pre-suppression number is still below it, which is what the
        # disclosure metric is for.
        self.assertLess(
            report["metrics"][DISCLOSURE_METRIC],
            thresholds["applicability_precision_at_5"],
        )

    def test_ordered_ids_are_pinned_per_query(self) -> None:
        results = result_by_id(frozen_report())
        self.assertEqual(set(results), set(MEASURED_ORDERED_IDS))
        for query_id, expected in MEASURED_ORDERED_IDS.items():
            with self.subTest(query=query_id):
                self.assertEqual(tuple(results[query_id]["ordered_ids"]), expected)

    def test_pre_suppression_ordered_ids_are_pinned_per_query(self) -> None:
        results = result_by_id(frozen_report())
        self.assertEqual(set(results), set(MEASURED_PRE_SUPPRESSION_ORDERED_IDS))
        for query_id, expected in MEASURED_PRE_SUPPRESSION_ORDERED_IDS.items():
            with self.subTest(query=query_id):
                entry = results[query_id]
                self.assertEqual(tuple(entry["pre_suppression_ordered_ids"]), expected)
                # Side by side: the retained ordering is this list with the
                # suppressed ids taken out, in place.
                self.assertEqual(
                    tuple(
                        identifier
                        for identifier in expected
                        if identifier not in set(entry["suppressed_ids"])
                    )[: entry["top_k"]],
                    tuple(entry["ordered_ids"]),
                )

    def test_suppressions_are_pinned_per_query(self) -> None:
        results = result_by_id(frozen_report())
        for query_id, expected in MEASURED_SUPPRESSED_IDS.items():
            with self.subTest(query=query_id):
                self.assertEqual(tuple(results[query_id]["suppressed_ids"]), expected)

    def test_hybrid_does_not_worsen_a_metric_the_baseline_already_met(self) -> None:
        metrics = frozen_report()["metrics"]
        for name in (
            "necessary_lemma_recall_at_5",
            "contradiction_recall_at_5",
            "notation_variant_recall_at_5",
        ):
            with self.subTest(metric=name):
                self.assertGreaterEqual(metrics[name], BASELINE_METRICS[name])
        # `duplicate_rate_at_5` is compared against its GATE, not against the
        # baseline VALUE, per the owner ruling recorded in ADR-0046 and in a
        # dated note in HYBRID_RETRIEVAL_BENCHMARK_V1.md. The reason is that the
        # rate is not monotone in retrieval quality: its denominator is a
        # retrieval volume, so removing a non-duplicate bad result raises the
        # rate while removing zero duplicates. Reading "may not worsen" against
        # the baseline value would therefore penalise a signal precisely for
        # improving precision, and on this corpus the literal reading is jointly
        # unsatisfiable with the precision gate for any label-blind signal:
        # reaching 1.0 drops the denominator to at most 50 while the numerator
        # cannot fall below 1 without removing an applicable duplicate gold,
        # which would itself be "hiding a duplicate".
        thresholds = frozen_report()["proposed_thresholds"]
        self.assertLessEqual(
            metrics["duplicate_rate_at_5"], thresholds["duplicate_rate_at_5_maximum"]
        )
        self.assertEqual(
            frozen_report()["gate_evaluation"]["duplicate_rate_at_5_maximum"]["status"],
            "pass",
        )
        # The movement is disclosed rather than hidden: the rate did rise off
        # the baseline value, and it is still inside its gate.
        self.assertGreater(
            metrics["duplicate_rate_at_5"], BASELINE_METRICS["duplicate_rate_at_5"]
        )
        # The required gain: the renamed gate moves from 0.0 to 1.0.
        self.assertGreater(
            metrics["renamed_known_result_recall_at_10"],
            BASELINE_METRICS["renamed_known_result_recall_at_10"],
        )
        # And what was an honest non-gain under ADR-0031 is now a strict gain.
        self.assertGreater(
            metrics["applicability_precision_at_5"],
            BASELINE_METRICS["applicability_precision_at_5"],
        )
        self.assertEqual(
            metrics[DISCLOSURE_METRIC],
            BASELINE_METRICS["applicability_precision_at_5"],
        )

    def test_why_the_applicability_gate_is_met_by_suppression(self) -> None:
        """The gate is met by removal, and the record shows why removal is what it took.

        1. Every applicability query's pre-suppression candidate set is at or
           below its top-k cutoff, so no reordering could move this metric:
           `6/10` was invariant under every permutation. That is why ADR-0031's
           demotion-only rule could not reach the gate, and why this slice had
           to be able to remove.
        2. On all four queries the inapplicable relevant documents are now
           suppressed and therefore absent from `ordered_ids`, while every
           applicable relevant document is retained.
        3. `applicability-selfadjoint` is the query ADR-0031 recorded as the
           residual at `6/7 = 0.857`: its self-disclaiming sentence shares no
           token with the query, and only the scope block reaches it. It
           suppresses `unbounded-spectral-mismatch` here.
        """

        results = result_by_id(frozen_report())
        applicability_ids = (
            "applicability-spectral",
            "applicability-certificate",
            "applicability-compactness",
            "applicability-selfadjoint",
        )
        for query_id in applicability_ids:
            entry = results[query_id]
            with self.subTest(query=query_id):
                self.assertLessEqual(
                    len(entry["fused_candidate_ids"]), entry["top_k"]
                )
                inapplicable_relevant = {
                    identifier
                    for identifier in entry["relevant_ids"]
                    if identifier not in entry["applicable_ids"]
                }
                self.assertTrue(inapplicable_relevant)
                self.assertTrue(inapplicable_relevant <= set(entry["suppressed_ids"]))
                # Removed, not merely ranked last.
                self.assertEqual(
                    inapplicable_relevant & set(entry["ordered_ids"]), set()
                )
                self.assertEqual(entry["inapplicable_retrieved_ids"], [])
                # Every applicable relevant document survives.
                self.assertTrue(
                    set(entry["applicable_ids"]) & set(entry["pre_suppression_ordered_ids"])
                    <= set(entry["ordered_ids"])
                )
        # The residual ADR-0031 recorded, and the query the scope block reaches.
        selfadjoint = results["applicability-selfadjoint"]
        self.assertEqual(
            selfadjoint["suppressed_ids"], ["unbounded-spectral-mismatch"]
        )
        self.assertIn(
            "unbounded-spectral-mismatch", selfadjoint["pre_suppression_ordered_ids"]
        )
        # Under the frozen SENTENCE unit this query suppressed nothing, which is
        # exactly the 6/7 = 0.857 ADR-0031 measured. That is asserted here so
        # the improvement is attributed to the scope unit and to nothing else.
        documents = load_corpus(FIXTURES)
        queries, _ = load_gold(FIXTURES, documents)
        query = next(
            item for item in queries if item.identifier == "applicability-selfadjoint"
        )
        sentence_scoped = _sentence_scope_verdict(
            documents, query.query, "unbounded-spectral-mismatch"
        )
        self.assertFalse(sentence_scoped)

    def test_every_missed_relevant_document_was_deliberately_suppressed(self) -> None:
        # A consequence of removal that the report must show rather than
        # smooth over: an inapplicable document named in an applicability
        # query's `relevant_ids` IS topically relevant, so removing it makes it
        # a "missed relevant" hit. That is correct and it is disclosed. The
        # property asserted here is that nothing else goes missing: every
        # missed relevant document is one this slice suppressed on purpose, and
        # no applicable document is ever missed.
        results = result_by_id(frozen_report())
        missed_queries = sorted(
            query_id for query_id, entry in results.items() if entry["missed_relevant_ids"]
        )
        self.assertEqual(
            missed_queries,
            [
                "applicability-certificate",
                "applicability-compactness",
                "applicability-selfadjoint",
                "applicability-spectral",
            ],
        )
        for query_id, entry in results.items():
            with self.subTest(query=query_id):
                self.assertLessEqual(
                    set(entry["missed_relevant_ids"]), set(entry["suppressed_ids"])
                )
                if entry["category"] == "applicability":
                    self.assertEqual(
                        set(entry["missed_relevant_ids"])
                        & set(entry["applicable_ids"]),
                        set(),
                    )
                else:
                    # Every recall gate is at 1.0, so nothing is missed here.
                    self.assertEqual(entry["missed_relevant_ids"], [])

    def test_schema_version_and_method_are_pinned(self) -> None:
        self.assertEqual(SCHEMA_VERSION, "adaivy.phase4c-hybrid-retrieval.v2")
        self.assertEqual(frozen_report()["schema_version"], SCHEMA_VERSION)
        self.assertEqual(frozen_report()["method"], benchmark_module.METHOD)
        self.assertEqual(benchmark_module.METHOD, "phase4c-hybrid-score-space-fusion")
        self.assertEqual(
            benchmark_module.FUSION_METHOD,
            "score-space-additive-fusion-with-suppression",
        )

    def test_a_v1_report_is_rejected_rather_than_migrated(self) -> None:
        report = json.loads(json.dumps(frozen_report()))
        report["schema_version"] = "adaivy.phase4c-hybrid-retrieval.v1"
        with self.assertRaises(Phase4CValidationError) as caught:
            verify_report(report)
        self.assertIn("schema version", str(caught.exception))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class Phase4CCliTests(unittest.TestCase):
    def test_benchmark_exits_zero_when_every_gate_passes(self) -> None:
        from math_research.phase4c_cli import main

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            status = main(
                ["benchmark", "--fixtures", str(FIXTURES), "--output", str(output)]
            )
            self.assertEqual(status, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["content_hash"], frozen_report()["content_hash"])
            self.assertEqual(output.read_bytes(), canonical_bytes(report))
            self.assertEqual(main(["inspect", str(output)]), 0)

    def test_benchmark_still_exits_one_and_still_emits_on_a_gate_failure(self) -> None:
        # This test exists because the happy path turned green. With every gate
        # passing, "a failing gate is never hidden" would otherwise become
        # untested at exactly the moment nothing fails, so a gate failure is
        # forced here through a degenerate lexical signal and the CLI is
        # required to exit 1 AND still emit a full verifiable report.
        from math_research import phase4c_cli

        def collapsed(fixtures, **kwargs):
            return evaluate_hybrid(
                fixtures,
                lexical_signal=EmptyLexicalIndex(),
                alias_signal=EmptyAliasSignal(),
                **kwargs,
            )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            with patch.object(phase4c_cli, "evaluate_hybrid", collapsed):
                status = phase4c_cli.main(
                    ["benchmark", "--fixtures", str(FIXTURES), "--output", str(output)]
                )
            self.assertEqual(status, 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertNotEqual(
                report["gate_summary"]["overall"], "pass", report["gate_summary"]
            )
            self.assertTrue(verify_report(report)["verified"])
            # Nothing is hidden: every query is still present, and the failing
            # and undetermined gates are named.
            self.assertEqual(len(report["results"]), BOUNDS.query_count)
            self.assertEqual(
                sorted(report["zero_hit_query_ids"]),
                sorted(item["id"] for item in report["results"]),
            )
            failing = sorted(
                key
                for key, value in report["gate_evaluation"].items()
                if value["status"] != "pass"
            )
            self.assertTrue(failing)
            self.assertEqual(phase4c_cli.main(["inspect", str(output)]), 1)

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
            self.assertNotEqual(
                report["metrics"]["applicability_precision_at_5"], 0.5
            )
            report["metrics"]["applicability_precision_at_5"] = 0.5
            path.write_bytes(canonical_bytes(report))
            self.assertEqual(main(["inspect", str(path)]), 1)

    def test_the_cli_summary_reports_suppression(self) -> None:
        from math_research.phase4c_cli import _summary

        summary = _summary(frozen_report())
        self.assertEqual(
            summary["queries_with_suppressions"],
            sorted(
                query_id
                for query_id, ids in MEASURED_SUPPRESSED_IDS.items()
                if ids
            ),
        )
        self.assertEqual(
            summary["suppressed_inapplicable_ids"],
            list(FROZEN_SUPPRESSED_DOCUMENT_IDS),
        )
        self.assertEqual(summary["failing_gates"], [])
        self.assertEqual(summary["undetermined_gates"], [])
        self.assertEqual(summary["gate_summary"], MEASURED_GATE_SUMMARY)
        self.assertEqual(summary["queries_with_inapplicable_hits"], [])
        self.assertNotIn("queries_with_demotions", summary)


if __name__ == "__main__":
    unittest.main()
