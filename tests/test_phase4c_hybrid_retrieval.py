"""Acceptance suite for the bounded Phase 4C hybrid-retrieval slice.

Per ADR-0026 and the "Consequences" section of ADR-0032, this suite is the only
executable record of this slice's thresholds, and each forbidden outcome must be
demonstrated impossible rather than left untested. So the tests are written as
properties over the whole frozen query set, not as a happy path:

* label separation -- a token that exists only in an id or a classification
  label retrieves nothing;
* exclusion never changes a score -- over all seventeen queries every fused
  score equals the score the lexical and alias signals produced;
* exclusion preserves relative order among retained documents, and is
  deliberately allowed to move a retained document *into* the top-k, which is
  why the duplicate gate is re-measured rather than argued;
* compositionality -- neither vocabulary fires alone, emptying either restores
  the pure lexical ordering, and no single absence operator and no single
  evidence noun is coextensive with the set of non-applicable documents;
* subjecthood -- `uses no` and bare `no` are demonstrated to exclude the
  applicable `hypothesis-free-supremum` gold, which is why neither is an
  operator; object-level cues can never exclude; neither contradiction gold is
  excluded;
* generalization -- `residual-bound-gap` is excluded through the
  `no ... is given` frame, which appears in no ADR-0031 enumerated phrase, and
  the ADR-0031 table is demonstrated to miss that document entirely;
* alias hygiene -- no document identifier anywhere in the alias fixture, at
  least five entries exercised by no query and matching no document, and
  removing one exercised entry fails exactly its own query;
* honest metrics -- zero-denominator ratios are `None`/`undetermined`, never a
  passing zero, including under total retrieval collapse;
* determinism, bounds, zero external cost, and pinned measured values kept
  separate from the proposed thresholds.

Measured values below are OBSERVATIONS, not targets. They are pinned so that any
retrieval, vocabulary, weighting, fusion, or metric change has to be a
deliberate edit to this file. They describe the ADR-0032 fixture set -- 19
documents and 17 queries, the third extension -- and are not comparable with any
value measured before it.
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
from math_research.phase4c import disclaimer as disclaimer_module
from math_research.phase4c import fusion as fusion_module
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
from math_research.phase4c.disclaimer import (
    ABSENCE_OPERATORS,
    EVIDENCE_NOUNS,
    OBJECT_LEVEL_CUES,
    SelfDisclaimerSignal,
    render_operator,
)
from math_research.phase4c.fixtures import (
    load_aliases,
    load_corpus,
    load_gold,
    load_object,
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
#
# Measured on the ADR-0032 fixture set: 19 documents, 17 queries, 6 of them
# applicability. This is the THIRD fixture extension, so these values are not
# comparable with any pinned before it.
# --------------------------------------------------------------------------

MEASURED_METRICS = {
    "necessary_lemma_recall_at_5": 1.0,
    # Reached by exclusion, not by reordering: every non-applicable relevant
    # document leaves the result list, so the denominator shrinks from 14 to 8
    # and the numerator stays at 8.
    "applicability_precision_at_5": 1.0,
    "contradiction_recall_at_5": 1.0,
    "notation_variant_recall_at_5": 1.0,
    "renamed_known_result_recall_at_10": 1.0,
    # Exclusion SHRINKS the duplicate denominator, so the rate RISES at a
    # constant numerator: 1/61 lexical, 1/50 hybrid. ADR-0032 predicted this
    # and requires the denominator to stay at or above 20 for the 0.05 gate.
    "duplicate_rate_at_5": 1 / 50,
    "external_spend_usd": 0,
    "network_calls": 0,
    "model_or_api_calls": 0,
    "downloaded_artifacts": 0,
}
MEASURED_SUPPORT = {
    "necessary_lemma_recall_at_5": (3, 3),
    "applicability_precision_at_5": (8, 8),
    "contradiction_recall_at_5": (2, 2),
    "notation_variant_recall_at_5": (2, 2),
    "renamed_known_result_recall_at_10": (4, 4),
    "duplicate_rate_at_5": (1, 50),
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

# Measured lexical-baseline values on the same extended fixtures, for the
# "may not worsen a metric the baseline already met" comparison.
BASELINE_METRICS = {
    "necessary_lemma_recall_at_5": 1.0,
    "applicability_precision_at_5": 8 / 14,
    "contradiction_recall_at_5": 1.0,
    "notation_variant_recall_at_5": 1.0,
    "renamed_known_result_recall_at_10": 0.0,
    "duplicate_rate_at_5": 1 / 61,
}

MEASURED_ORDERED_IDS = {
    "lemma-compactness": (
        "compactness-lemma", "spectral-lemma", "banach-notation",
        "finite-dimensional-spectral", "renamed-uniform-bound-result",
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
        "hypothesis-free-supremum",
    ),
    "applicability-selfadjoint": (
        "spectral-lemma", "finite-dimensional-spectral",
        "renamed-uniform-bound-result",
    ),
    "applicability-psd-cone": ("psd-notation",),
    "applicability-supremum": (
        "hypothesis-free-supremum", "separation-lemma", "compactness-lemma",
        "renamed-cover-result", "finite-dimensional-spectral",
    ),
    "contradiction-boundary": (
        "boundary-contradiction", "monotonicity-contradiction", "renamed-cover-result",
    ),
    "contradiction-monotonicity": ("monotonicity-contradiction", "boundary-contradiction"),
    "notation-banach": ("banach-notation", "boundary-contradiction"),
    "notation-psd": ("psd-notation", "finite-dimensional-spectral"),
    "renamed-uniform-bound": (
        "renamed-uniform-bound-result", "banach-notation",
        "finite-dimensional-spectral",
    ),
    "renamed-maximal-chain": (
        "renamed-maximal-chain-result", "separation-lemma", "hypothesis-free-supremum",
        "spectral-lemma", "compactness-lemma",
    ),
    "renamed-container-count": ("renamed-container-count-result", "renamed-cover-result"),
    "renamed-known": ("renamed-cover-result", "finite-dimensional-spectral"),
}
MEASURED_EXCLUDED_IDS = {
    "lemma-compactness": ("topology-distractor", "unbounded-spectral-mismatch"),
    "lemma-spectral": ("unbounded-spectral-mismatch",),
    "lemma-separation": (),
    "applicability-spectral": ("topology-distractor", "unbounded-spectral-mismatch"),
    "applicability-certificate": ("optimization-distractor",),
    "applicability-compactness": ("topology-distractor", "unbounded-spectral-mismatch"),
    "applicability-selfadjoint": ("unbounded-spectral-mismatch",),
    "applicability-psd-cone": ("residual-bound-gap", "topology-distractor"),
    "applicability-supremum": ("topology-distractor", "unbounded-spectral-mismatch"),
    "contradiction-boundary": (),
    "contradiction-monotonicity": ("residual-bound-gap",),
    "notation-banach": (),
    "notation-psd": ("residual-bound-gap", "unbounded-spectral-mismatch"),
    "renamed-uniform-bound": ("topology-distractor", "unbounded-spectral-mismatch"),
    "renamed-maximal-chain": (),
    "renamed-container-count": (),
    "renamed-known": ("topology-distractor", "unbounded-spectral-mismatch"),
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
# The four non-applicable corpus documents. The compositional rule is measured
# against this set; no SINGLE vocabulary entry may be coextensive with it.
MEASURED_NON_APPLICABLE_DOCUMENTS = (
    "optimization-distractor",
    "residual-bound-gap",
    "topology-distractor",
    "unbounded-spectral-mismatch",
)
# ADR-0032's two adversarial controls, authored against the principles rather
# than against the vocabularies.
GENERALIZATION_CONTROL = "residual-bound-gap"
OVER_EXCLUSION_CONTROL = "hypothesis-free-supremum"
# The ADR-0031 enumerated self-disclaiming table, retained here as a control
# rather than as a signal: the compositional rule must catch a document this
# list misses.
ADR_0031_ENUMERATED_CUES = (
    "does not provide",
    "inapplicable",
    "insufficient",
    "may look",
    "states no",
    "as stated",
)

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
# 2, 3, 4, 5. The self-disclaimer signal
# --------------------------------------------------------------------------


def _fires_on(**overrides) -> set[str]:
    """Corpus-wide audit: which documents the composition fires on.

    Query-independent, so it measures the vocabularies rather than the query
    set. Each document is probed with its own text as the query, which makes
    the "the query reached this document" conservatism rule vacuously true and
    isolates the composition.
    """

    documents = load_corpus(FIXTURES)
    signal = SelfDisclaimerSignal(documents, **overrides)
    fired: set[str] = set()
    for document in documents:
        verdict = signal.verdicts(document.text, [document.identifier])[0]
        if verdict.excluded:
            fired.add(document.identifier)
    return fired


def _gold_ids(entry: dict) -> set[str]:
    """The documents this query must retrieve.

    For an applicability query that is `applicable_ids`: the other relevant
    documents are topically relevant and deliberately not applicable, and
    removing them is the whole point of the signal. For every other category it
    is `relevant_ids`.
    """

    if entry.get("applicable_ids") is not None:
        return set(entry["applicable_ids"])
    return set(entry["relevant_ids"])


class _StubDocument:
    """The minimal shape `SelfDisclaimerSignal` reads: an id and its text.

    Used only to make a single sentence its own retrieval unit, so ADR-0031's
    sentence scope can be measured against ADR-0032's document scope.
    """

    def __init__(self, identifier: str, text: str) -> None:
        self.identifier = identifier
        self.text = text


class Phase4CExclusionInvariantTests(unittest.TestCase):
    """ADR-0032's three invariants, as properties over all seventeen queries."""

    def setUp(self) -> None:
        self.with_signal = frozen_report()
        self.without_signal = evaluate_hybrid(FIXTURES, absence_operators=())

    def test_exclusion_never_changes_a_score_over_every_query(self) -> None:
        # Invariant 1. Two independent checks: the fused score equals the
        # pre-score inside the frozen run, and it equals the score the same
        # document gets when the signal is switched off entirely.
        excluded = {
            item["id"]: item for item in self.with_signal["operational"]["results"]
        }
        plain = {
            item["id"]: item for item in self.without_signal["operational"]["results"]
        }
        self.assertEqual(len(excluded), BOUNDS.query_count)
        self.assertEqual(set(excluded), set(plain))
        compared = 0
        for query_id, entry in excluded.items():
            plain_scores = {
                hit["document_id"]: hit["fused_score"] for hit in plain[query_id]["hits"]
            }
            observed = {hit["document_id"]: hit["fused_score"] for hit in entry["hits"]}
            self.assertEqual(set(observed), set(plain_scores), query_id)
            for hit in entry["hits"]:
                with self.subTest(query=query_id, document=hit["document_id"]):
                    self.assertEqual(hit["fused_score"], hit["pre_score"])
                    self.assertEqual(
                        hit["fused_score"], plain_scores[hit["document_id"]]
                    )
                compared += 1
        self.assertGreater(compared, 0)

    def test_excluded_hits_are_scored_exactly_like_retained_hits(self) -> None:
        # The invariant has to hold for the EXCLUDED documents too, or the
        # signal would be a penalty wearing a boolean.
        semantic = result_by_id(self.with_signal)
        operational = {
            item["id"]: item for item in self.with_signal["operational"]["results"]
        }
        observed = 0
        for query_id, entry in semantic.items():
            scores = {
                hit["document_id"]: hit for hit in operational[query_id]["hits"]
            }
            for document_id in entry["excluded_ids"]:
                hit = scores[document_id]
                with self.subTest(query=query_id, document=document_id):
                    self.assertEqual(hit["fused_score"], hit["pre_score"])
                observed += 1
        self.assertGreater(observed, 0)

    def test_exclusion_preserves_relative_order_among_retained_documents(self) -> None:
        # Invariant 2: the retained subsequence of the fused ordering equals the
        # signal-free ordering restricted to the retained ids.
        excluded = result_by_id(self.with_signal)
        plain = result_by_id(self.without_signal)
        for query_id, entry in excluded.items():
            retained = [
                identifier
                for identifier in entry["fused_candidate_ids"]
                if identifier not in set(entry["excluded_ids"])
            ]
            expected = [
                identifier
                for identifier in plain[query_id]["fused_candidate_ids"]
                if identifier not in set(entry["excluded_ids"])
            ]
            with self.subTest(query=query_id):
                self.assertEqual(retained, expected)
                self.assertEqual(entry["ordered_ids"], retained[: entry["top_k"]])

    def test_exclusion_may_move_a_retained_document_into_the_top_k(self) -> None:
        # ADR-0032 states invariant 2 is deliberately weaker than ADR-0031's
        # "never promotes": a retained document CAN enter the cutoff because
        # something above it left. This is the measured demonstration, and it is
        # why the duplicate gate is re-measured rather than argued.
        excluded = result_by_id(self.with_signal)
        plain = result_by_id(self.without_signal)
        promoted: dict[str, list[str]] = {}
        for query_id, entry in excluded.items():
            gained = [
                identifier
                for identifier in entry["ordered_ids"]
                if identifier not in plain[query_id]["ordered_ids"]
            ]
            if gained:
                promoted[query_id] = gained
        self.assertTrue(promoted, "no retained document entered a cutoff window")
        for query_id, gained in promoted.items():
            with self.subTest(query=query_id):
                # Whatever entered was retained, and something left above it.
                self.assertTrue(set(gained) <= set(excluded[query_id]["ordered_ids"]))
                self.assertTrue(excluded[query_id]["excluded_ids"])

    def test_exclusion_never_introduces_a_document_over_every_query(self) -> None:
        # Invariant 3.
        excluded = result_by_id(self.with_signal)
        plain = result_by_id(self.without_signal)
        for query_id, entry in excluded.items():
            with self.subTest(query=query_id):
                self.assertEqual(
                    set(entry["fused_candidate_ids"]),
                    set(plain[query_id]["fused_candidate_ids"]),
                )
                self.assertLessEqual(
                    set(entry["excluded_ids"]), set(entry["fused_candidate_ids"])
                )
                self.assertLessEqual(
                    set(entry["excluded_ids"]),
                    set(entry["lexical_candidate_ids"])
                    | set(entry["alias_introduced_ids"]),
                )
                self.assertLessEqual(
                    set(entry["ordered_ids"]), set(entry["fused_candidate_ids"])
                )

    def test_fusion_rejects_a_verdict_outside_the_candidate_set(self) -> None:
        from math_research.phase4c.ports import DisclaimerVerdict, LexicalCandidate

        with self.assertRaises(Phase4CValidationError):
            fusion_module.fuse(
                [LexicalCandidate(document_id="a", bm25=-1.0)],
                [],
                [
                    DisclaimerVerdict(
                        document_id="intruder",
                        excluded=True,
                        absence_operators=("is insufficient",),
                        evidence_nouns=("bound",),
                        object_level_cues=(),
                        matched_query_terms=("x",),
                    )
                ],
                alias_phrase_points=ALIAS_PHRASE_POINTS,
            )

    def test_the_disclaimer_signal_rejects_an_unknown_document(self) -> None:
        signal = SelfDisclaimerSignal(load_corpus(FIXTURES))
        with self.assertRaises(Phase4CValidationError):
            signal.verdicts("compact", ["not-a-corpus-document"])

    def test_fusion_carries_no_penalty_term_at_all(self) -> None:
        # ADR-0032 deletes the penalty rather than retaining it at zero: a term
        # that can no longer change an outcome is dead complexity.
        self.assertFalse(hasattr(fusion_module, "HEDGE_PENALTY_RULE"))
        self.assertNotIn("HEDGE_PENALTY_RULE", fusion_module.__all__)
        fields = set(fusion_module.FusedHit.__dataclass_fields__)
        self.assertEqual(
            fields,
            {
                "document_id",
                "signals",
                "lexical_relevance",
                "alias_points",
                "alias_entry_ids",
                "alias_matched_phrases",
                "pre_score",
                "fused_score",
                "excluded",
                "absence_operators",
                "evidence_nouns",
                "object_level_cues",
                "matched_query_terms",
            },
        )
        for removed in ("hedge_penalty", "demoted", "self_disclaiming_cues", "scoped_query_terms"):
            self.assertNotIn(removed, fields)
        for entry in self.with_signal["results"]:
            for hit in entry["hits"]:
                for removed in ("hedge_penalty", "demoted", "self_disclaiming_cues"):
                    self.assertNotIn(removed, hit)
        for entry in self.with_signal["operational"]["results"]:
            for hit in entry["hits"]:
                self.assertNotIn("hedge_penalty", hit)
        self.assertEqual(
            self.with_signal["declared_method"]["fusion"]["composition"],
            "fused_score = (-bm25) + alias_points",
        )

    def test_the_declared_ordering_covers_excluded_hits_too(self) -> None:
        # Exclusion marks a hit; it does not move it. The whole candidate list,
        # excluded members included, is ordered by the declared key.
        operational = {
            item["id"]: item for item in self.with_signal["operational"]["results"]
        }
        for entry in self.with_signal["results"]:
            scores = {
                hit["document_id"]: hit["fused_score"]
                for hit in operational[entry["id"]]["hits"]
            }
            expected = sorted(
                entry["fused_candidate_ids"],
                key=lambda document_id: (-scores[document_id], document_id),
            )
            with self.subTest(query=entry["id"]):
                self.assertEqual(entry["fused_candidate_ids"], expected)
        self.assertEqual(
            self.with_signal["declared_method"]["fusion"]["ordering"],
            "fused_score DESC, document_id ASC",
        )

    def test_every_excluded_document_stays_fully_in_the_report(self) -> None:
        # Nothing is filtered from the report: an excluded document keeps its
        # hit, its operator, its noun, and its matched query terms.
        observed = 0
        for entry in self.with_signal["results"]:
            hits = {hit["document_id"]: hit for hit in entry["hits"]}
            self.assertEqual(list(hits), entry["fused_candidate_ids"])
            for document_id in entry["excluded_ids"]:
                with self.subTest(query=entry["id"], document=document_id):
                    self.assertIn(document_id, entry["fused_candidate_ids"])
                    self.assertNotIn(document_id, entry["ordered_ids"])
                    hit = hits[document_id]
                    self.assertTrue(hit["excluded"])
                    self.assertTrue(hit["absence_operators"])
                    self.assertTrue(hit["evidence_nouns"])
                    self.assertTrue(hit["matched_query_terms"])
                observed += 1
        self.assertGreater(observed, 0)


class Phase4CCompositionalRuleTests(unittest.TestCase):
    def test_neither_vocabulary_fires_alone(self) -> None:
        # The operator vocabulary carries subjecthood and the noun vocabulary
        # carries evidentiality. Presence of one half excludes nothing.
        self.assertEqual(_fires_on(absence_operators=()), set())
        self.assertEqual(_fires_on(evidence_nouns=()), set())
        for overrides in ({"absence_operators": ()}, {"evidence_nouns": ()}):
            report = evaluate_hybrid(FIXTURES, **overrides)
            with self.subTest(**overrides):
                for entry in report["results"]:
                    self.assertEqual(entry["excluded_ids"], [])
                    for hit in entry["hits"]:
                        self.assertFalse(hit["excluded"])

    def test_emptying_either_vocabulary_restores_the_pure_lexical_ordering(self) -> None:
        for overrides in ({"absence_operators": ()}, {"evidence_nouns": ()}):
            report = evaluate_hybrid(
                FIXTURES, alias_signal=EmptyAliasSignal(), **overrides
            )
            for entry in report["results"]:
                with self.subTest(query=entry["id"], **overrides):
                    self.assertEqual(entry["excluded_ids"], [])
                    self.assertEqual(
                        entry["ordered_ids"],
                        entry["lexical_candidate_ids"][: entry["top_k"]],
                    )

    def test_the_vocabularies_are_the_only_thing_that_changes_the_ordering(self) -> None:
        plain = result_by_id(
            evaluate_hybrid(
                FIXTURES, absence_operators=(), alias_signal=EmptyAliasSignal()
            )
        )
        composed = result_by_id(evaluate_hybrid(FIXTURES, alias_signal=EmptyAliasSignal()))
        changed = sorted(
            query_id
            for query_id, entry in composed.items()
            if entry["ordered_ids"] != plain[query_id]["ordered_ids"]
        )
        self.assertGreater(len(changed), 0)
        for query_id in changed:
            with self.subTest(query=query_id):
                # An ordering change implies an exclusion. Nothing else moved.
                self.assertTrue(composed[query_id]["excluded_ids"])

    def test_no_single_absence_operator_is_coextensive_with_the_target_set(self) -> None:
        target = set(MEASURED_NON_APPLICABLE_DOCUMENTS)
        self.assertEqual(
            target,
            {
                document.identifier
                for document in load_corpus(FIXTURES)
                if document.applicability != "applicable"
            },
        )
        # The composition of the two full vocabularies does land on the target
        # set. No single operator does, so the gate measures the rule and not a
        # list authored against the corpus.
        self.assertEqual(_fires_on(), target)
        self.assertGreaterEqual(len(ABSENCE_OPERATORS), 6)
        for operator in ABSENCE_OPERATORS:
            fired = _fires_on(absence_operators=(operator,))
            with self.subTest(operator=render_operator(operator)):
                self.assertNotEqual(fired, target)
                self.assertLess(len(fired), len(target))

    def test_no_single_evidence_noun_is_coextensive_with_the_target_set(self) -> None:
        target = set(MEASURED_NON_APPLICABLE_DOCUMENTS)
        self.assertGreaterEqual(len(EVIDENCE_NOUNS), 10)
        for noun in EVIDENCE_NOUNS:
            fired = _fires_on(evidence_nouns=(noun,))
            with self.subTest(noun=noun):
                self.assertNotEqual(fired, target)
                self.assertLess(len(fired), len(target))

    def test_both_halves_must_share_one_sentence(self) -> None:
        # Detection is per sentence even though scope is the document. A frame
        # whose two parts straddle a sentence boundary composes nothing, and an
        # operator in one sentence with a noun in another composes nothing.
        straddling = "No such object exists. A proof is given in the appendix."
        joined = "No proof of the claim is given here."
        for text in (straddling, joined):
            self.assertIn("proof", text_module.tokens(text))
            self.assertIn("given", text_module.tokens(text))
        self.assertEqual(len(text_module.sentences(straddling)), 2)
        self.assertEqual(len(text_module.sentences(joined)), 1)
        probe_documents = [
            _StubDocument("straddling", straddling),
            _StubDocument("joined", joined),
        ]
        signal = SelfDisclaimerSignal(probe_documents)
        verdicts = {
            item.document_id: item
            for item in signal.verdicts("proof claim object", ["straddling", "joined"])
        }
        self.assertFalse(verdicts["straddling"].excluded)
        self.assertTrue(verdicts["joined"].excluded)
        self.assertEqual(verdicts["joined"].absence_operators, ("no ... is given",))
        # And the frozen corpus case: the two halves that DO fire share one
        # sentence in `residual-bound-gap`.
        documents = load_corpus(FIXTURES)
        gap = next(
            document
            for document in documents
            if document.identifier == GENERALIZATION_CONTROL
        )
        firing = [
            sentence
            for sentence in text_module.sentences(gap.text)
            if "no proof" in sentence and "is given" in sentence
        ]
        self.assertEqual(len(firing), 1)
        verdict = SelfDisclaimerSignal(documents).verdicts(gap.text, [gap.identifier])[0]
        self.assertTrue(verdict.excluded)

    def test_the_frames_have_no_gap_width_parameter(self) -> None:
        # A tuned gap width would be exactly the free parameter this signal is
        # built to avoid. The sentence is the only bound.
        self.assertEqual(disclaimer_module.FRAME_GAP_BOUND, "sentence")
        declared = frozen_report()["declared_method"]["disclaimer_signal"]
        self.assertEqual(declared["frame_gap_bound"], "sentence")
        source = (PACKAGE_DIR / "disclaimer.py").read_text(encoding="utf-8")
        for forbidden in ("max_gap", "gap_width", "max_distance", "window_size"):
            self.assertNotIn(forbidden, source)
        for operator in ABSENCE_OPERATORS:
            with self.subTest(operator=render_operator(operator)):
                self.assertIn(len(operator), (1, 2))
                self.assertTrue(all(isinstance(part, str) for part in operator))

    def test_there_is_no_cue_count_threshold(self) -> None:
        self.assertIsNone(disclaimer_module.CUE_COUNT_THRESHOLD)
        declared = frozen_report()["declared_method"]["disclaimer_signal"]
        self.assertIsNone(declared["cue_count_threshold"])
        self.assertEqual(declared["direction"], "exclusion_only")
        self.assertEqual(
            declared["detection_rule"],
            "absence-operator-and-evidence-noun-co-occur-in-one-sentence",
        )
        self.assertEqual(
            declared["scope_rule"],
            "detected-per-sentence-applied-to-the-whole-single-claim-unit",
        )
        self.assertEqual(declared["scope_unit"], "single-claim-document")
        self.assertEqual(
            declared["composition"], "operator AND evidence_noun, in one sentence"
        )

    def test_the_vocabularies_are_disjoint_and_overlap_is_rejected(self) -> None:
        documents = load_corpus(FIXTURES)
        self.assertEqual(set(EVIDENCE_NOUNS) & set(OBJECT_LEVEL_CUES), set())
        self.assertEqual(len(set(EVIDENCE_NOUNS)), len(EVIDENCE_NOUNS))
        self.assertEqual(len(set(OBJECT_LEVEL_CUES)), len(OBJECT_LEVEL_CUES))
        self.assertEqual(len(set(ABSENCE_OPERATORS)), len(ABSENCE_OPERATORS))
        with self.assertRaises(Phase4CValidationError):
            SelfDisclaimerSignal(
                documents, evidence_nouns=("fails",), object_level_cues=("fails",)
            )
        # An operator may not smuggle an evidence noun into its own phrase,
        # which would collapse the composition into a single list.
        with self.assertRaises(Phase4CValidationError):
            SelfDisclaimerSignal(documents, absence_operators=(("states no proof",),))
        for bad in ((), ("no", "is", "given")):
            with self.subTest(operator=bad), self.assertRaises(Phase4CValidationError):
                SelfDisclaimerSignal(documents, absence_operators=(bad,))

    def test_document_scope_is_what_reaches_the_adr_0031_residual(self) -> None:
        """The measured cause of prediction 1, asserted rather than asserted-of.

        On `applicability-selfadjoint` the disclaiming sentence of
        `unbounded-spectral-mismatch` shares no token with the query and the
        matched terms sit in a preceding sentence. ADR-0031's sentence scope
        therefore could not fire; ADR-0032's document scope does.
        """

        documents = load_corpus(FIXTURES)
        signal = SelfDisclaimerSignal(documents)
        queries, _ = load_gold(FIXTURES, documents)
        query = next(
            item for item in queries if item.identifier == "applicability-selfadjoint"
        )
        verdict = signal.verdicts(query.query, ["unbounded-spectral-mismatch"])[0]
        self.assertTrue(verdict.excluded)
        self.assertTrue(verdict.matched_query_terms)
        document = next(
            item for item in documents if item.identifier == "unbounded-spectral-mismatch"
        )
        # Emulate ADR-0031's sentence scope by making each sentence its own
        # retrieval unit. Under that scope nothing fires.
        sentence_scope = [
            SelfDisclaimerSignal(
                [_StubDocument(f"sentence-{index}", sentence)]
            ).verdicts(query.query, [f"sentence-{index}"])[0]
            for index, sentence in enumerate(text_module.sentences(document.text))
        ]
        self.assertGreater(len(sentence_scope), 1)
        self.assertFalse(
            any(item.excluded for item in sentence_scope),
            "sentence scope would have fired, so this is not the ADR-0031 residual",
        )
        # The composition does fire in one sentence; that sentence just carries
        # no query term, which is exactly why sentence scope missed it.
        self.assertTrue(
            any(item.absence_operators and item.evidence_nouns for item in sentence_scope)
        )


class Phase4CSubjecthoodTests(unittest.TestCase):
    def test_object_level_cues_cannot_cause_an_exclusion(self) -> None:
        # Emptying the object-level vocabulary changes neither the fused
        # ordering nor a single exclusion, so object-level cues have no
        # ordering effect at all.
        neutralised = evaluate_hybrid(FIXTURES, object_level_cues=())
        frozen = result_by_id(frozen_report())
        for entry in neutralised["results"]:
            with self.subTest(query=entry["id"]):
                self.assertEqual(
                    entry["ordered_ids"], frozen[entry["id"]]["ordered_ids"]
                )
                self.assertEqual(
                    entry["excluded_ids"], frozen[entry["id"]]["excluded_ids"]
                )
        self.assertEqual(neutralised["metrics"], frozen_report()["metrics"])

    def test_a_document_with_only_object_level_cues_is_never_excluded(self) -> None:
        observed = 0
        for entry in frozen_report()["results"]:
            for hit in entry["hits"]:
                if hit["object_level_cues"] and not hit["absence_operators"]:
                    observed += 1
                    with self.subTest(query=entry["id"], document=hit["document_id"]):
                        self.assertFalse(hit["excluded"])
        self.assertGreater(observed, 0)

    def test_neither_contradiction_gold_is_ever_excluded(self) -> None:
        for entry in frozen_report()["results"]:
            for gold in MEASURED_CONTRADICTION_GOLDS:
                with self.subTest(query=entry["id"], gold=gold):
                    self.assertNotIn(gold, entry["excluded_ids"])
        self.assertEqual(
            _fires_on() & set(MEASURED_CONTRADICTION_GOLDS), set()
        )

    def test_boundary_contradiction_carries_object_level_cues_in_query_scope(self) -> None:
        # This is the exact case a naive negation signal breaks: an applicable
        # contradiction gold whose matched query terms share a sentence with
        # `fails`, `violates`, and `counterexample`.
        documents = load_corpus(FIXTURES)
        signal = SelfDisclaimerSignal(documents)
        queries, _ = load_gold(FIXTURES, documents)
        query = next(
            item for item in queries if item.identifier == "contradiction-boundary"
        )
        verdict = signal.verdicts(query.query, ["boundary-contradiction"])[0]
        self.assertFalse(verdict.excluded)
        self.assertEqual(verdict.absence_operators, ())
        self.assertEqual(verdict.evidence_nouns, ())
        self.assertEqual(
            set(verdict.object_level_cues), {"fails", "violates", "counterexample"}
        )
        self.assertTrue(verdict.matched_query_terms)
        cue_sentences = [
            sentence
            for sentence in text_module.sentences(
                next(
                    document.text
                    for document in documents
                    if document.identifier == "boundary-contradiction"
                )
            )
            if set(text_module.tokens(sentence)) & set(text_module.tokens(query.query))
            and set(text_module.tokens(sentence)) & set(OBJECT_LEVEL_CUES)
        ]
        self.assertTrue(cue_sentences)

    def test_uses_no_and_bare_no_are_not_operators_because_they_exclude_a_gold(
        self,
    ) -> None:
        """Subjecthood, demonstrated rather than asserted.

        `the argument uses no compactness hypothesis` has the mathematics as its
        subject, and a missing hypothesis there is a strength. Admitting either
        `uses no` or bare `no` as an absence operator excludes
        `hypothesis-free-supremum`, an applicable gold. That is the measured
        reason both stay out, not a listed exception.
        """

        for candidate in (("uses no",), ("no",)):
            fired = _fires_on(absence_operators=(candidate,))
            with self.subTest(operator=render_operator(candidate)):
                self.assertIn(OVER_EXCLUSION_CONTROL, fired)
                self.assertNotIn(candidate, ABSENCE_OPERATORS)
        self.assertNotIn(OVER_EXCLUSION_CONTROL, _fires_on())

    def test_the_adr_0031_operator_exclusions_stay_excluded(self) -> None:
        # `without` states a hypothesis; `may look` has the score as its
        # subject; `as stated` is not about supply at all. None is an operator,
        # and each would fire somewhere the composition should not.
        rendered = {render_operator(operator) for operator in ABSENCE_OPERATORS}
        for excluded in ("without", "may look", "as stated", "no", "uses no"):
            with self.subTest(candidate=excluded):
                self.assertNotIn(excluded, rendered)
        self.assertIn("does not provide", rendered)
        self.assertIn("no ... is given", rendered)
        self.assertNotIn("no", set(EVIDENCE_NOUNS) | set(OBJECT_LEVEL_CUES))


class Phase4CGoldSafetyTests(unittest.TestCase):
    def test_no_gold_is_excluded_in_any_category(self) -> None:
        # ADR-0032 prediction 2, over EVERY query and EVERY category, not just
        # applicability. A gold is `applicable_ids` for an applicability query
        # and `relevant_ids` everywhere else.
        checked = 0
        for entry in frozen_report()["results"]:
            gold = _gold_ids(entry)
            self.assertTrue(gold)
            with self.subTest(query=entry["id"], category=entry["category"]):
                self.assertEqual(gold & set(entry["excluded_ids"]), set())
                for hit in entry["hits"]:
                    if hit["document_id"] in gold:
                        self.assertFalse(hit["excluded"])
            checked += 1
        self.assertEqual(checked, BOUNDS.query_count)
        for category, count in CATEGORY_COUNTS.items():
            observed = sum(
                1
                for entry in frozen_report()["results"]
                if entry["category"] == category
            )
            with self.subTest(category=category):
                self.assertEqual(observed, count)

    def test_only_non_applicable_documents_are_ever_excluded(self) -> None:
        excluded = {
            document_id
            for entry in frozen_report()["results"]
            for document_id in entry["excluded_ids"]
        }
        self.assertEqual(excluded, set(MEASURED_NON_APPLICABLE_DOCUMENTS))
        applicability = {
            document.identifier: document.applicability
            for document in load_corpus(FIXTURES)
        }
        for document_id in excluded:
            with self.subTest(document=document_id):
                self.assertNotEqual(applicability[document_id], "applicable")

    def test_the_over_exclusion_control_is_never_excluded_by_any_query(self) -> None:
        """ADR-0032 prediction 4, the least certain one.

        `hypothesis-free-supremum` states an absence claim about a mathematical
        object -- `the argument uses no compactness hypothesis` -- and is
        applicable. If document scope were too coarse this is where it would
        show.
        """

        documents = load_corpus(FIXTURES)
        control = next(
            document
            for document in documents
            if document.identifier == OVER_EXCLUSION_CONTROL
        )
        self.assertIn("uses no compactness hypothesis", control.text)
        self.assertEqual(control.applicability, "applicable")
        signal = SelfDisclaimerSignal(documents)
        queries, _ = load_gold(FIXTURES, documents)
        for query in queries:
            verdict = signal.verdicts(query.query, [OVER_EXCLUSION_CONTROL])[0]
            with self.subTest(query=query.identifier):
                self.assertFalse(verdict.excluded)
                self.assertEqual(verdict.absence_operators, ())
        for entry in frozen_report()["results"]:
            with self.subTest(query=entry["id"]):
                self.assertNotIn(OVER_EXCLUSION_CONTROL, entry["excluded_ids"])
        # And it is retrieved as the applicable gold of its own query.
        results = result_by_id(frozen_report())
        self.assertIn(
            OVER_EXCLUSION_CONTROL, results["applicability-supremum"]["ordered_ids"]
        )

    def test_the_generalization_control_is_excluded_through_the_frame(self) -> None:
        """ADR-0032 prediction 3.

        `residual-bound-gap` self-disclaims through `no ... is given` over the
        evidence noun `proof`. The frame appears in no ADR-0031 enumerated
        phrase and in no other corpus document.
        """

        documents = load_corpus(FIXTURES)
        control = next(
            document
            for document in documents
            if document.identifier == GENERALIZATION_CONTROL
        )
        self.assertIn("no proof of the claimed cone membership is given", control.text)
        signal = SelfDisclaimerSignal(documents)
        verdict = signal.verdicts(
            "positive semidefinite cone membership proof", [GENERALIZATION_CONTROL]
        )[0]
        self.assertTrue(verdict.excluded)
        self.assertEqual(verdict.absence_operators, ("no ... is given",))
        self.assertEqual(verdict.evidence_nouns, ("proof",))
        results = result_by_id(frozen_report())
        self.assertIn(
            GENERALIZATION_CONTROL, results["applicability-psd-cone"]["excluded_ids"]
        )
        self.assertNotIn(
            GENERALIZATION_CONTROL, results["applicability-psd-cone"]["ordered_ids"]
        )
        # The frame fires on this document and on no other.
        self.assertEqual(
            _fires_on(absence_operators=(("no", "is given"),)),
            {GENERALIZATION_CONTROL},
        )

    def test_the_adr_0031_enumerated_table_misses_the_generalization_control(self) -> None:
        # The control was authored against the principle, not the vocabulary.
        # An enumerated table would have missed it entirely, which is what the
        # composition is for.
        documents = load_corpus(FIXTURES)
        control = next(
            document
            for document in documents
            if document.identifier == GENERALIZATION_CONTROL
        )
        folded = control.text.casefold()
        for cue in ADR_0031_ENUMERATED_CUES:
            with self.subTest(cue=cue):
                self.assertIsNone(text_module.cue_pattern(cue).search(folded))
        # And no enumerated phrase contains the frame that does fire.
        for cue in ADR_0031_ENUMERATED_CUES:
            with self.subTest(cue=cue):
                self.assertNotIn("is given", cue)


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
            # Every gate passes on this fixture set, so the CLI exits 0. A
            # non-zero status here is a real failure, not a recorded one.
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
                    "excluded_ids",
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
        # Exclusion is not filtering: every excluded document keeps its hit and
        # its `fused_candidate_ids` entry, and no applicability query retrieves
        # an inapplicable document any more.
        self.assertTrue(any(item["excluded_ids"] for item in results))
        for entry in results:
            with self.subTest(query=entry["id"]):
                self.assertTrue(
                    set(entry["excluded_ids"]) <= set(entry["fused_candidate_ids"])
                )
                self.assertEqual(entry["inapplicable_retrieved_ids"], [])

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
        self.assertEqual(
            fusion["exclusion_rule"],
            "an excluded candidate is removed from the ordering; no score "
            "changes and no penalty term exists",
        )
        # BM25 magnitudes survive: with the alias signal disabled and the
        # operator vocabulary emptied, every fused score equals -bm25 exactly.
        plain = evaluate_hybrid(
            FIXTURES, absence_operators=(), alias_signal=EmptyAliasSignal()
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
        self.assertEqual(BOUNDS.document_count, 19)
        self.assertEqual(BOUNDS.query_count, 17)
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
        self.assertEqual(CATEGORY_COUNTS["applicability"], 6)
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
        # The measured values are pinned in this file, independently of the
        # fixture's proposed thresholds, and the two are not the same numbers:
        # the duplicate rate is measured at 1/50 against a gate of 0.05.
        self.assertNotEqual(
            report["metrics"]["duplicate_rate_at_5"],
            thresholds["duplicate_rate_at_5_maximum"],
        )
        self.assertLess(
            report["metrics"]["duplicate_rate_at_5"],
            thresholds["duplicate_rate_at_5_maximum"],
        )
        # Every gate is met on this fixture set. Recorded as a measurement, so
        # a regression is a pinned-value edit rather than a silent drift.
        self.assertEqual(set(MEASURED_GATE_STATUS.values()), {"pass"})

    def test_ordered_ids_are_pinned_per_query(self) -> None:
        results = result_by_id(frozen_report())
        self.assertEqual(set(results), set(MEASURED_ORDERED_IDS))
        for query_id, expected in MEASURED_ORDERED_IDS.items():
            with self.subTest(query=query_id):
                self.assertEqual(tuple(results[query_id]["ordered_ids"]), expected)

    def test_exclusions_are_pinned_per_query(self) -> None:
        results = result_by_id(frozen_report())
        self.assertEqual(set(results), set(MEASURED_EXCLUDED_IDS))
        for query_id, expected in MEASURED_EXCLUDED_IDS.items():
            with self.subTest(query=query_id):
                self.assertEqual(tuple(results[query_id]["excluded_ids"]), expected)

    def test_ordered_ids_are_the_post_exclusion_result_list(self) -> None:
        for entry in frozen_report()["results"]:
            with self.subTest(query=entry["id"]):
                self.assertEqual(
                    set(entry["ordered_ids"]) & set(entry["excluded_ids"]), set()
                )
                self.assertLessEqual(len(entry["ordered_ids"]), entry["top_k"])
                self.assertEqual(
                    entry["ordered_ids"],
                    [
                        identifier
                        for identifier in entry["fused_candidate_ids"]
                        if identifier not in set(entry["excluded_ids"])
                    ][: entry["top_k"]],
                )

    def test_hybrid_does_not_worsen_a_metric_the_baseline_already_met(self) -> None:
        metrics = frozen_report()["metrics"]
        baseline = evaluate_hybrid(
            FIXTURES, absence_operators=(), alias_signal=EmptyAliasSignal()
        )["metrics"]
        for name, expected in BASELINE_METRICS.items():
            with self.subTest(metric=name):
                self.assertAlmostEqual(baseline[name], expected, places=12)
        for name in (
            "necessary_lemma_recall_at_5",
            "contradiction_recall_at_5",
            "notation_variant_recall_at_5",
        ):
            with self.subTest(metric=name):
                self.assertGreaterEqual(metrics[name], BASELINE_METRICS[name])
        # The two required gains: the alias signal moves the renamed gate from
        # 0.0 to 1.0, and exclusion moves applicability precision from 8/14 to
        # 1.0 by removing the non-applicable relevant documents.
        self.assertGreater(
            metrics["renamed_known_result_recall_at_10"],
            BASELINE_METRICS["renamed_known_result_recall_at_10"],
        )
        self.assertGreater(
            metrics["applicability_precision_at_5"],
            BASELINE_METRICS["applicability_precision_at_5"],
        )
        # The honest cost, recorded rather than hidden: exclusion SHRINKS the
        # duplicate denominator, so the rate rises from 1/61 to 1/50 at a
        # constant numerator. ADR-0032 predicted this arithmetic and requires
        # the gate to be asserted against the measured value, which is done
        # here with both endpoints pinned.
        self.assertGreater(
            metrics["duplicate_rate_at_5"], BASELINE_METRICS["duplicate_rate_at_5"]
        )
        self.assertAlmostEqual(metrics["duplicate_rate_at_5"], 1 / 50, places=12)
        self.assertLessEqual(
            metrics["duplicate_rate_at_5"],
            frozen_report()["proposed_thresholds"]["duplicate_rate_at_5_maximum"],
        )
        self.assertEqual(
            frozen_report()["metric_support"]["duplicate_rate_at_5"]["numerator"], 1
        )
        self.assertGreaterEqual(
            frozen_report()["metric_support"]["duplicate_rate_at_5"]["denominator"], 20
        )

    def test_how_the_applicability_gate_is_met_by_exclusion(self) -> None:
        """The measured mechanism, recorded so it cannot be mistaken for luck.

        On every applicability query the non-applicable relevant documents are
        excluded and the applicable ones are retained, so the precision
        denominator shrinks rather than the numerator rising. ADR-0031's
        demotion-only rule could not have done this: on four of the six queries
        the fused candidate set is no larger than top-k, so every reordering
        leaves the same set retrieved.
        """

        results = result_by_id(frozen_report())
        applicability = [
            entry
            for entry in frozen_report()["results"]
            if entry["category"] == "applicability"
        ]
        self.assertEqual(len(applicability), CATEGORY_COUNTS["applicability"])
        for entry in applicability:
            inapplicable_relevant = set(entry["relevant_ids"]) - set(
                entry["applicable_ids"]
            )
            with self.subTest(query=entry["id"]):
                self.assertTrue(inapplicable_relevant)
                self.assertTrue(inapplicable_relevant <= set(entry["excluded_ids"]))
                self.assertEqual(
                    inapplicable_relevant & set(entry["ordered_ids"]), set()
                )
                self.assertTrue(
                    set(entry["applicable_ids"]) <= set(entry["ordered_ids"])
                )
                self.assertEqual(entry["inapplicable_retrieved_ids"], [])
        at_or_below_cutoff = sorted(
            entry["id"]
            for entry in applicability
            if len(entry["fused_candidate_ids"]) <= entry["top_k"]
        )
        self.assertEqual(
            at_or_below_cutoff,
            [
                "applicability-certificate",
                "applicability-psd-cone",
                "applicability-selfadjoint",
                "applicability-spectral",
            ],
        )
        # The ADR-0031 residual is now excluded on its own query.
        self.assertIn(
            "unbounded-spectral-mismatch",
            results["applicability-selfadjoint"]["excluded_ids"],
        )

    def test_schema_version_and_method_are_pinned(self) -> None:
        # The report shape changed with ADR-0032, so the schema version moved.
        self.assertEqual(SCHEMA_VERSION, "adaivy.phase4c-hybrid-retrieval.v2")
        self.assertEqual(frozen_report()["schema_version"], SCHEMA_VERSION)
        self.assertEqual(frozen_report()["method"], benchmark_module.METHOD)
        self.assertEqual(
            benchmark_module.METHOD,
            "phase4c-hybrid-score-space-fusion-with-exclusion",
        )
        self.assertEqual(
            benchmark_module.FUSION_METHOD,
            "score-space-additive-fusion-with-candidate-exclusion",
        )
        self.assertEqual(
            frozen_report()["declared_method"]["fusion"]["method"],
            benchmark_module.FUSION_METHOD,
        )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


class Phase4CCliTests(unittest.TestCase):
    def test_benchmark_exits_zero_only_when_every_gate_passes(self) -> None:
        from math_research.phase4c_cli import main

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            status = main(
                ["benchmark", "--fixtures", str(FIXTURES), "--output", str(output)]
            )
            self.assertEqual(status, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["gate_summary"], MEASURED_GATE_SUMMARY)
            self.assertEqual(report["content_hash"], frozen_report()["content_hash"])
            self.assertEqual(output.read_bytes(), canonical_bytes(report))
            self.assertEqual(main(["inspect", str(output)]), 0)

    def test_benchmark_exits_one_when_a_gate_fails(self) -> None:
        # Exit 0 must be earned. A collapsed retriever leaves two gates
        # undetermined, and undetermined is never a pass.
        from math_research.phase4c_cli import _summary

        report = evaluate_hybrid(
            FIXTURES,
            lexical_signal=EmptyLexicalIndex(),
            alias_signal=EmptyAliasSignal(),
        )
        self.assertEqual(report["gate_summary"]["overall"], "not_pass")
        self.assertEqual(_summary(report)["queries_with_exclusions"], [])

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
            report["metrics"]["applicability_precision_at_5"] = 0.5
            path.write_bytes(canonical_bytes(report))
            self.assertEqual(main(["inspect", str(path)]), 1)


if __name__ == "__main__":
    unittest.main()
