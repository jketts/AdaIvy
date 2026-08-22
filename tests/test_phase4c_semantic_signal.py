"""Acceptance suite for the ADR-0066 Phase 4C semantic signal.

The ADR requires `probes_flipped == probes_total` and requires each named
boundary to be demonstrated rather than asserted, so this suite is written as
properties over the whole frozen query set and the whole frozen partition:

* every one of the ten falsifiability probes flips, and the probe report is
  byte-identical across fresh processes and four `PYTHONHASHSEED` values;
* the partition is fail-closed under a battery of mutations of its own bytes,
  each of which violates exactly one invariant because every hash the mutation
  does not target is resealed;
* the ranking is exact -- no float is constructed and nothing is divided on the
  semantic path -- and an exact cosine tie orders by `document_id` ascending;
* the contribution is bounded and derived from the RANK, so no signal can hand
  fusion a magnitude of its own choosing;
* the partition key and manifest hash bind report identity;
* the report stays inside `max_report_bytes` with all five semantic fields on
  every hit of every query.

Measured values here are OBSERVATIONS. The three regressions ADR-0066 did not
predict are pinned in `RECORDED_REGRESSIONS` and asserted, because a slice that
quietly made its numbers look good would be a failure even with every gate
green.
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

from math_research.embedding.readpath import sweep_source
from math_research.phase4c import semantic as semantic_module
from math_research.phase4c.aliases import ALIAS_PHRASE_POINTS
from math_research.phase4c.benchmark import evaluate_hybrid
from math_research.phase4c.bounds import (
    BOUNDS,
    MAXIMUM_SEMANTIC_TIER_CREDIT,
    Phase4CValidationError,
    SEMANTIC_HASH_RULE,
    SEMANTIC_TIERS,
    semantic_tier_credit,
    semantic_tier_rule,
)
from math_research.phase4c.fusion import fuse
from math_research.phase4c.ports import (
    LexicalCandidate,
    SemanticCredit,
    SemanticPartitionIdentity,
    SemanticSignal,
)
from math_research.phase4c.probes import PROBES, run_probes
from math_research.phase4c.semantic import (
    DisabledSemanticSignal,
    SemanticPartitionSignal,
    declared_partition_key,
    default_partition_root,
    load_semantic_partition,
)
from math_research.phase4c.serialization import (
    canonical_bytes,
    semantic_preimage,
    sha256_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures" / "phase4c"
PARTITION = REPO_ROOT / "fixtures" / "phase4c-semantic"
PACKAGE_DIR = REPO_ROOT / "src" / "math_research" / "phase4c"

PARTITION_KEY_STRING = (
    "fixture_synthetic~adaivy-cooccurrence-anchor-v1~d32~round_half_even_scale_2p30"
)
#: Read from the fixture README and from the manifest bytes, which must agree.
PARTITION_MANIFEST_HASH = (
    "sha256:0011f3288f2429571528842b276b01a340254e5138e2ebb188a59a0cb2fbbb94"
)

PROBE_IDS = (
    "pr.semantic-cannot-invert-a-lexical-gold",
    "pr.semantic-disabled-is-a-true-noop",
    "pr.semantic-missing-partition-refused",
    "pr.semantic-no-float-constructed",
    "pr.semantic-override-recorded",
    "pr.semantic-partition-in-content-hash",
    "pr.semantic-partition-mismatch-refused",
    "pr.semantic-respects-candidate-bound",
    "pr.semantic-tie-broken-by-document-id",
    "pr.semantic-zero-spend-preserved",
)

# The signal's own output, per query, in rank order. Ten candidates for every
# query, because the corpus has nineteen documents and the frozen limit is ten.
MEASURED_SEMANTIC_CANDIDATES = {
    "lemma-compactness": (
        "compactness-lemma", "hypothesis-free-supremum", "separation-lemma",
        "banach-notation", "optimization-distractor", "topology-distractor",
        "boundary-contradiction", "monotonicity-contradiction",
        "renamed-maximal-chain-result", "spectral-lemma",
    ),
    "lemma-spectral": (
        "spectral-lemma", "finite-dimensional-spectral",
        "hypothesis-free-supremum", "renamed-uniform-bound-result",
        "banach-notation", "unbounded-spectral-mismatch", "renamed-cover-result",
        "optimization-distractor", "topology-distractor",
        "monotonicity-contradiction",
    ),
    "lemma-separation": (
        "separation-lemma", "compactness-lemma", "hypothesis-free-supremum",
        "optimization-distractor", "banach-notation", "boundary-contradiction",
        "topology-distractor", "monotonicity-contradiction",
        "renamed-maximal-chain-result", "renamed-container-count-result",
    ),
    "applicability-spectral": (
        "unbounded-spectral-mismatch", "finite-dimensional-spectral",
        "spectral-lemma", "topology-distractor", "hypothesis-free-supremum",
        "optimization-distractor", "banach-notation",
        "monotonicity-contradiction", "boundary-contradiction",
        "renamed-maximal-chain-result",
    ),
    "applicability-certificate": (
        "duplicate-certificate-b", "duplicate-certificate-a",
        "optimization-distractor", "hypothesis-free-supremum", "banach-notation",
        "renamed-maximal-chain-result", "boundary-contradiction",
        "monotonicity-contradiction", "topology-distractor",
        "renamed-cover-result",
    ),
    "applicability-compactness": (
        "topology-distractor", "hypothesis-free-supremum", "compactness-lemma",
        "separation-lemma", "optimization-distractor", "banach-notation",
        "boundary-contradiction", "monotonicity-contradiction",
        "renamed-maximal-chain-result", "renamed-container-count-result",
    ),
    "applicability-selfadjoint": (
        "unbounded-spectral-mismatch", "finite-dimensional-spectral",
        "spectral-lemma", "hypothesis-free-supremum", "banach-notation",
        "optimization-distractor", "topology-distractor",
        "renamed-uniform-bound-result", "monotonicity-contradiction",
        "boundary-contradiction",
    ),
    "applicability-psd-cone": (
        "residual-bound-gap", "psd-notation", "monotonicity-contradiction",
        "optimization-distractor", "topology-distractor", "banach-notation",
        "hypothesis-free-supremum", "boundary-contradiction",
        "unbounded-spectral-mismatch", "renamed-maximal-chain-result",
    ),
    "applicability-supremum": (
        "hypothesis-free-supremum", "optimization-distractor",
        "compactness-lemma", "banach-notation", "topology-distractor",
        "boundary-contradiction", "monotonicity-contradiction",
        "separation-lemma", "renamed-maximal-chain-result",
        "renamed-cover-result",
    ),
    "contradiction-boundary": (
        "boundary-contradiction", "monotonicity-contradiction",
        "hypothesis-free-supremum", "optimization-distractor", "banach-notation",
        "renamed-cover-result", "topology-distractor",
        "renamed-maximal-chain-result", "separation-lemma", "compactness-lemma",
    ),
    "contradiction-monotonicity": (
        "monotonicity-contradiction", "boundary-contradiction",
        "optimization-distractor", "hypothesis-free-supremum", "banach-notation",
        "topology-distractor", "renamed-maximal-chain-result",
        "separation-lemma", "residual-bound-gap", "compactness-lemma",
    ),
    "notation-banach": (
        "banach-notation", "hypothesis-free-supremum", "optimization-distractor",
        "boundary-contradiction", "monotonicity-contradiction",
        "topology-distractor", "renamed-maximal-chain-result",
        "renamed-uniform-bound-result", "compactness-lemma", "separation-lemma",
    ),
    "notation-psd": (
        "psd-notation", "residual-bound-gap", "optimization-distractor",
        "banach-notation", "hypothesis-free-supremum", "topology-distractor",
        "monotonicity-contradiction", "boundary-contradiction",
        "renamed-maximal-chain-result", "separation-lemma",
    ),
    "renamed-uniform-bound": (
        "banach-notation", "optimization-distractor", "hypothesis-free-supremum",
        "topology-distractor", "boundary-contradiction",
        "monotonicity-contradiction", "renamed-maximal-chain-result",
        "compactness-lemma", "separation-lemma", "renamed-uniform-bound-result",
    ),
    "renamed-maximal-chain": (
        "hypothesis-free-supremum", "optimization-distractor", "banach-notation",
        "boundary-contradiction", "monotonicity-contradiction",
        "topology-distractor", "renamed-maximal-chain-result",
        "compactness-lemma", "separation-lemma", "renamed-uniform-bound-result",
    ),
    "renamed-container-count": (
        "hypothesis-free-supremum", "optimization-distractor", "banach-notation",
        "boundary-contradiction", "monotonicity-contradiction",
        "topology-distractor", "renamed-maximal-chain-result",
        "renamed-cover-result", "compactness-lemma", "separation-lemma",
    ),
    "renamed-known": (
        "optimization-distractor", "hypothesis-free-supremum", "banach-notation",
        "topology-distractor", "boundary-contradiction",
        "monotonicity-contradiction", "renamed-maximal-chain-result",
        "compactness-lemma", "separation-lemma", "spectral-lemma",
    ),
}

# The three movements ADR-0066 did not predict, pinned so the slice cannot be
# read as an unqualified improvement.
RECORDED_REGRESSIONS = {
    # query -> (gold, rank under three signals, rank under four)
    "gold_displaced_from_rank_one": (
        ("renamed-uniform-bound", "renamed-uniform-bound-result", 1, 2),
        ("renamed-maximal-chain", "renamed-maximal-chain-result", 1, 2),
        ("renamed-container-count", "renamed-container-count-result", 1, 4),
    ),
    "queries_newly_retrieving_a_non_applicable_document": 11,
    "alias_weight_invariance_holds": False,
}

_PROBE_CACHE: dict[int, dict] = {}


def probe_report() -> dict:
    if 0 not in _PROBE_CACHE:
        _PROBE_CACHE[0] = run_probes(FIXTURES)
    return _PROBE_CACHE[0]


_REPORT_CACHE: dict[int, dict] = {}


def frozen_report() -> dict:
    if 0 not in _REPORT_CACHE:
        _REPORT_CACHE[0] = evaluate_hybrid(FIXTURES)
    return _REPORT_CACHE[0]


def three_signal_report() -> dict:
    if 1 not in _REPORT_CACHE:
        _REPORT_CACHE[1] = evaluate_hybrid(
            FIXTURES, semantic_signal=DisabledSemanticSignal()
        )
    return _REPORT_CACHE[1]


def result_by_id(report: dict) -> dict[str, dict]:
    return {item["id"]: item for item in report["results"]}


# --------------------------------------------------------------------------
# Partition staging helpers. Every mutation reseals what it does not target,
# so exactly one invariant is violated at a time.
# --------------------------------------------------------------------------


def _seal(body: dict) -> dict:
    preimage = dict(body)
    preimage["content_hash"] = None
    body = dict(body)
    body["content_hash"] = sha256_bytes(canonical_bytes(preimage))
    return body


def _write_json(path: Path, body: dict) -> None:
    path.write_bytes(canonical_bytes(body) + b"\n")


class PartitionStaging(unittest.TestCase):
    """Base class carrying the copy-and-mutate helpers."""

    def _stage(self, directory: str) -> Path:
        target = Path(directory) / "phase4c-semantic"
        shutil.copytree(PARTITION, target)
        return target

    def _manifest(self, root: Path) -> dict:
        return json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    def _rewrite_manifest(self, root: Path, mutate, *, reseal: bool = True) -> None:
        body = self._manifest(root)
        mutate(body)
        _write_json(root / "manifest.json", _seal(body) if reseal else body)

    def _patch_artifact_bytes(self, root: Path, relative: str, mutate) -> None:
        """Rewrite artifact BYTES and fix only the manifest hashes of the bytes.

        The artifact's own `content_hash` is deliberately left stale so a check
        that happens later than the byte-length and byte-hash checks -- such as
        the decimal refusal -- is the one that fires.
        """

        path = root / relative
        raw = mutate(path.read_text(encoding="utf-8"))
        path.write_text(raw, encoding="utf-8")
        encoded = raw.encode("utf-8")

        def fix(manifest: dict) -> None:
            for name in ("documents", "queries"):
                for entry in manifest[name]:
                    if entry["artifact_path"] == relative:
                        entry["artifact_sha256"] = sha256_bytes(encoded)
                        entry["byte_length"] = len(encoded)

        self._rewrite_manifest(root, fix)

    def _rewrite_artifact(
        self, root: Path, relative: str, mutate, *, reseal: bool = True
    ) -> None:
        """Mutate one artifact and update every hash the manifest records for it."""

        path = root / relative
        body = json.loads(path.read_text(encoding="utf-8"))
        mutate(body)
        if reseal:
            body = _seal(body)
        raw = canonical_bytes(body) + b"\n"
        path.write_bytes(raw)

        def fix(manifest: dict) -> None:
            for name in ("documents", "queries"):
                for entry in manifest[name]:
                    if entry["artifact_path"] == relative:
                        entry["artifact_sha256"] = sha256_bytes(raw)
                        entry["byte_length"] = len(raw)
                        entry["content_hash"] = body["content_hash"]

        self._rewrite_manifest(root, fix)

    def _refuses(self, root: Path) -> str:
        with self.assertRaises(Phase4CValidationError) as caught:
            load_semantic_partition(root)
        return str(caught.exception)


# --------------------------------------------------------------------------
# 1. The ten falsifiability probes
# --------------------------------------------------------------------------


class SemanticProbeTests(unittest.TestCase):
    def test_every_probe_flips(self) -> None:
        report = probe_report()
        self.assertEqual(report["probes_total"], 10)
        self.assertEqual(report["probes_flipped"], report["probes_total"])
        self.assertEqual(report["unflipped_probe_ids"], [])

    def test_the_probe_set_is_the_adr_0066_probe_set(self) -> None:
        self.assertEqual(
            tuple(item["probe_id"] for item in probe_report()["probes"]), PROBE_IDS
        )
        self.assertEqual(len(PROBES), len(PROBE_IDS))
        self.assertEqual(len({probe.probe_id for probe in PROBES}), len(PROBES))

    def test_each_probe_leg_is_pinned_and_the_two_legs_differ(self) -> None:
        for item in probe_report()["probes"]:
            with self.subTest(probe=item["probe_id"]):
                self.assertEqual(item["baseline_observed"], item["expected_baseline"])
                self.assertEqual(item["mutated_observed"], item["expected_mutated"])
                self.assertNotEqual(
                    item["baseline_observed"], item["mutated_observed"]
                )
                self.assertIn(item["mutation_target"], ("input", "property"))
                self.assertTrue(item["detail"])

    def test_three_probes_are_refusals_and_seven_are_positive_properties(self) -> None:
        kinds = [item["mutation_target"] for item in probe_report()["probes"]]
        self.assertEqual(kinds.count("input"), 3)
        self.assertEqual(kinds.count("property"), 7)
        self.assertEqual(len(kinds), 10)

    def test_the_probe_report_claims_no_authority(self) -> None:
        report = probe_report()
        self.assertEqual(report["external_spend_usd"], 0)
        self.assertEqual(report["network_calls"], 0)
        self.assertEqual(report["model_or_api_calls"], 0)
        self.assertFalse(report["creates_epistemic_warrant"])
        self.assertFalse(report["asserts_source_applicability"])
        self.assertEqual(report["novelty_status"], "not_assessed")
        self.assertEqual(report["significance_status"], "not_assessed")

    def test_the_inversion_probe_measures_its_own_margin(self) -> None:
        # The probe must not quote ADR-0031's 4.4: it measures the margin on the
        # frozen corpus every run. Three points has to be strictly below it or
        # the property is not established.
        measured = probe_report()["measured_minimum_lexical_gold_margin"]
        self.assertEqual(measured["query_id"], "notation-psd")
        self.assertEqual(measured["gold_id"], "psd-notation")
        self.assertEqual(measured["runner_up_id"], "residual-bound-gap")
        self.assertAlmostEqual(measured["margin"], 4.858259, places=6)
        self.assertGreater(
            measured["margin"], probe_report()["maximum_semantic_contribution"]
        )
        self.assertEqual(probe_report()["maximum_semantic_contribution"], 3)

    def test_probes_are_byte_identical_across_hash_seeds_and_processes(self) -> None:
        local = canonical_bytes(run_probes(FIXTURES))
        for seed in ("0", "1", "4294967295", "random"):
            with self.subTest(hash_seed=seed):
                self.assertEqual(self._fresh_process(seed), local)

    def _fresh_process(self, hash_seed: str) -> bytes:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(REPO_ROOT / "src")
        environment["PYTHONHASHSEED"] = hash_seed
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "probes.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "math_research.phase4c_cli",
                    "probes",
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
            self.assertEqual(completed.returncode, 0, completed.stderr)
            return output.read_bytes()


# --------------------------------------------------------------------------
# 2. The frozen constants
# --------------------------------------------------------------------------


class SemanticFrozenConstantTests(unittest.TestCase):
    def test_the_adr_0066_constants_are_exactly_as_frozen(self) -> None:
        self.assertEqual(BOUNDS.semantic_candidate_limit, 10)
        self.assertEqual(BOUNDS.semantic_tier_points, 1)
        self.assertEqual(SEMANTIC_TIERS, ((1, 2, 3), (3, 5, 2), (6, 10, 1)))
        self.assertEqual(MAXIMUM_SEMANTIC_TIER_CREDIT, 3)
        self.assertEqual(
            [semantic_tier_credit(rank) for rank in range(1, 12)],
            [3, 3, 2, 2, 2, 1, 1, 1, 1, 1, 0],
        )
        # The tiers exactly cover the candidate limit: no rank inside the limit
        # earns zero, and no rank outside it earns anything.
        self.assertEqual(SEMANTIC_TIERS[-1][1], BOUNDS.semantic_candidate_limit)
        self.assertEqual(SEMANTIC_TIERS[0][0], 1)
        for index in range(1, len(SEMANTIC_TIERS)):
            self.assertEqual(
                SEMANTIC_TIERS[index][0], SEMANTIC_TIERS[index - 1][1] + 1
            )

    def test_the_declared_tiering_is_projected_from_the_enforced_tiering(self) -> None:
        declared = frozen_report()["declared_method"]["semantic_signal"]
        self.assertEqual(declared["tiers"], semantic_tier_rule())
        self.assertEqual(declared["candidate_limit"], BOUNDS.semantic_candidate_limit)
        self.assertEqual(
            declared["semantic_tier_points"], BOUNDS.semantic_tier_points
        )
        self.assertEqual(declared["maximum_contribution"], 3)
        for rule in declared["tiers"]:
            with self.subTest(rule=rule):
                self.assertEqual(
                    semantic_tier_credit(rule["first_rank"]), rule["tier_credit"]
                )
                self.assertEqual(
                    semantic_tier_credit(rule["last_rank"]), rule["tier_credit"]
                )

    def test_the_maximum_contribution_is_below_the_measured_bm25_gold_margin(
        self,
    ) -> None:
        margin = probe_report()["measured_minimum_lexical_gold_margin"]["margin"]
        self.assertLess(
            BOUNDS.semantic_tier_points * MAXIMUM_SEMANTIC_TIER_CREDIT, margin
        )

    def test_there_is_no_override_for_the_tier_points(self) -> None:
        # ADR-0066 freezes the tier points before measurement, so unlike the
        # alias weight there is no constructor parameter that can move them.
        import inspect

        signature = inspect.signature(evaluate_hybrid)
        self.assertNotIn("semantic_tier_points", signature.parameters)
        self.assertIn("semantic_partition", signature.parameters)
        self.assertIn("semantic_signal", signature.parameters)

    def test_a_non_positive_tier_weight_is_refused_at_the_fusion_boundary(self) -> None:
        for points in (0, -1, True):
            with self.subTest(points=points), self.assertRaises(
                Phase4CValidationError
            ):
                fuse(
                    [LexicalCandidate(document_id="a", bm25=-1.0)],
                    (),
                    (),
                    alias_phrase_points=ALIAS_PHRASE_POINTS,
                    semantic_tier_points=points,
                )


# --------------------------------------------------------------------------
# 3. Exactness of the semantic path
# --------------------------------------------------------------------------


class SemanticExactnessTests(unittest.TestCase):
    def test_semantic_module_constructs_no_float_and_never_divides(self) -> None:
        source = (PACKAGE_DIR / "semantic.py").read_text(encoding="utf-8")
        self.assertEqual(sweep_source(source, module="semantic.py"), ())

    def test_the_exactness_sweep_can_be_made_to_fail(self) -> None:
        # A check that cannot fail proves nothing.
        for subject in (
            "x = 1.5\n",
            "def f(a, b):\n    return a / b\n",
            "def f(a, b):\n    return a // b\n",
            "y = float('1')\n",
            "import math\n",
        ):
            with self.subTest(subject=subject.strip()):
                self.assertTrue(sweep_source(subject, module="subject"))

    def test_no_float_literal_survives_an_independent_ast_walk(self) -> None:
        tree = ast.parse((PACKAGE_DIR / "semantic.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                self.assertNotIsInstance(node.value, float)
                self.assertNotIsInstance(node.value, complex)
            if isinstance(node, ast.BinOp):
                self.assertNotIsInstance(node.op, (ast.Div, ast.FloorDiv))

    def test_the_cosine_terms_on_every_hit_are_exact_integers(self) -> None:
        seen = 0
        for entry in frozen_report()["results"]:
            for hit in entry["hits"]:
                with self.subTest(query=entry["id"], document=hit["document_id"]):
                    if hit["semantic_rank"] is None:
                        self.assertIsNone(hit["cosine_dot"])
                        self.assertIsNone(hit["cosine_norm_squared_product"])
                        self.assertEqual(hit["semantic_tier_credit"], 0)
                        continue
                    self.assertIsInstance(hit["cosine_dot"], int)
                    self.assertNotIsInstance(hit["cosine_dot"], bool)
                    self.assertIsInstance(hit["cosine_norm_squared_product"], int)
                    self.assertGreater(hit["cosine_norm_squared_product"], 0)
                    seen += 1
        self.assertEqual(seen, BOUNDS.query_count * BOUNDS.semantic_candidate_limit)

    def test_the_reported_cosine_terms_reproduce_the_reported_order(self) -> None:
        # Ranking is recheckable from the report alone, by cross-multiplying
        # integers. No square root, no division, no epsilon.
        for entry in frozen_report()["results"]:
            ranked = sorted(
                (
                    hit
                    for hit in entry["hits"]
                    if hit["semantic_rank"] is not None
                ),
                key=lambda hit: hit["semantic_rank"],
            )
            with self.subTest(query=entry["id"]):
                self.assertEqual(
                    [hit["semantic_rank"] for hit in ranked],
                    list(range(1, len(ranked) + 1)),
                )
                for first, second in zip(ranked, ranked[1:]):
                    left = (
                        first["cosine_dot"] * first["cosine_dot"]
                        * second["cosine_norm_squared_product"]
                    )
                    right = (
                        second["cosine_dot"] * second["cosine_dot"]
                        * first["cosine_norm_squared_product"]
                    )
                    if first["cosine_dot"] >= 0 and second["cosine_dot"] >= 0:
                        self.assertGreaterEqual(left, right)
                    if left == right:
                        self.assertLess(
                            first["document_id"], second["document_id"]
                        )


# --------------------------------------------------------------------------
# 4. The signal: ranking, ties, bounds
# --------------------------------------------------------------------------


class SemanticSignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.signal = SemanticPartitionSignal(load_semantic_partition(PARTITION))

    def test_the_signal_satisfies_the_port(self) -> None:
        self.assertIsInstance(self.signal, SemanticSignal)
        self.assertIsInstance(DisabledSemanticSignal(), SemanticSignal)

    def test_the_candidate_pool_is_the_corpus_and_never_the_queries(self) -> None:
        partition = load_semantic_partition(PARTITION).partition
        self.assertEqual(len(partition.corpus_document_ids()), BOUNDS.document_count)
        self.assertEqual(len(partition.query_ids()), BOUNDS.query_count)
        self.assertEqual(
            partition.vector_count, BOUNDS.document_count + BOUNDS.query_count
        )
        # `document_ids()` is a SUPERSET including the queries, and using it as
        # the candidate pool would make a gold query id a retrieval feature.
        self.assertEqual(
            len(partition.document_ids()),
            BOUNDS.document_count + BOUNDS.query_count,
        )
        queries = set(partition.query_ids())
        for query_id in queries:
            ranked = {item for item, _terms in self.signal.ranked(query_id)}
            with self.subTest(query=query_id):
                self.assertEqual(ranked & queries, set())
                self.assertEqual(ranked, set(partition.corpus_document_ids()))

    def test_every_gold_query_has_a_replayed_query_vector(self) -> None:
        partition = load_semantic_partition(PARTITION).partition
        self.assertEqual(
            set(partition.query_ids()),
            {entry["id"] for entry in frozen_report()["results"]},
        )

    def test_a_query_the_partition_does_not_carry_is_refused(self) -> None:
        for absent in ("not-a-query", "compactness-lemma"):
            with self.subTest(query=absent), self.assertRaises(
                Phase4CValidationError
            ):
                self.signal.credits(absent, limit=BOUNDS.semantic_candidate_limit)

    def test_the_candidate_limit_is_self_enforced(self) -> None:
        for limit in (0, -1, BOUNDS.max_candidates_per_signal + 1):
            with self.subTest(limit=limit), self.assertRaises(
                Phase4CValidationError
            ):
                self.signal.credits("lemma-compactness", limit=limit)

    def test_credits_are_ranked_bounded_and_derived_from_the_rank(self) -> None:
        for query_id in load_semantic_partition(PARTITION).partition.query_ids():
            credits = self.signal.credits(
                query_id, limit=BOUNDS.semantic_candidate_limit
            )
            with self.subTest(query=query_id):
                self.assertEqual(len(credits), BOUNDS.semantic_candidate_limit)
                self.assertLessEqual(len(credits), BOUNDS.max_candidates_per_signal)
                self.assertEqual(
                    [credit.rank for credit in credits],
                    list(range(1, len(credits) + 1)),
                )
                for credit in credits:
                    self.assertEqual(
                        credit.tier_credit, semantic_tier_credit(credit.rank)
                    )
                    self.assertGreater(credit.tier_credit, 0)
                    self.assertLessEqual(
                        credit.tier_credit, MAXIMUM_SEMANTIC_TIER_CREDIT
                    )
                self.assertEqual(
                    len({credit.document_id for credit in credits}), len(credits)
                )

    def test_measured_semantic_candidates_are_pinned(self) -> None:
        results = result_by_id(frozen_report())
        self.assertEqual(set(results), set(MEASURED_SEMANTIC_CANDIDATES))
        for query_id, expected in MEASURED_SEMANTIC_CANDIDATES.items():
            with self.subTest(query=query_id):
                self.assertEqual(
                    tuple(results[query_id]["semantic_candidate_ids"]), expected
                )

    def test_an_exact_cosine_tie_orders_by_document_id_ascending(self) -> None:
        # Two identical vectors, presented so that a set, a dictionary, or the
        # caller's insertion order would put the descending id first.
        from math_research.phase4c.probes import _tie_partition

        signal = SemanticPartitionSignal(_tie_partition())
        ordered = [item for item, _terms in signal.ranked("tie-probe-query")]
        self.assertEqual(ordered, ["aaa-tied-document", "zzz-tied-document"])
        credits = signal.credits("tie-probe-query", limit=2)
        self.assertEqual(
            [credit.document_id for credit in credits],
            ["aaa-tied-document", "zzz-tied-document"],
        )
        self.assertEqual({credit.tier_credit for credit in credits}, {3})

    def test_the_signal_reads_no_document_body_and_no_query_text(self) -> None:
        # It is keyed on the gold query identifier and on frozen coordinates.
        # There is no code path from a document body to a credit.
        source = (PACKAGE_DIR / "semantic.py").read_text(encoding="utf-8")
        for forbidden in ("load_corpus", "load_gold", "tokens(", "sqlite3"):
            with self.subTest(name=forbidden):
                self.assertNotIn(forbidden, source)


# --------------------------------------------------------------------------
# 5. Fusion: bounded, additive, never an exclusion
# --------------------------------------------------------------------------


class SemanticFusionTests(unittest.TestCase):
    def test_the_semantic_term_is_additive_in_the_declared_position(self) -> None:
        for entry, raw in zip(
            frozen_report()["results"],
            frozen_report()["operational"]["results"],
            strict=True,
        ):
            for hit, operational in zip(entry["hits"], raw["hits"], strict=True):
                with self.subTest(query=entry["id"], document=hit["document_id"]):
                    lexical = operational["lexical_relevance"]
                    self.assertAlmostEqual(
                        operational["fused_score"],
                        (0.0 if lexical is None else lexical)
                        + operational["alias_points"]
                        + operational["semantic_points"],
                        places=6,
                    )
                    self.assertEqual(
                        operational["semantic_points"],
                        BOUNDS.semantic_tier_points * hit["semantic_tier_credit"],
                    )
                    self.assertGreaterEqual(operational["semantic_points"], 0)
                    self.assertLessEqual(
                        operational["semantic_points"],
                        BOUNDS.semantic_tier_points * MAXIMUM_SEMANTIC_TIER_CREDIT,
                    )

    def test_fusion_refuses_a_credit_its_rank_does_not_earn(self) -> None:
        for rank, claimed in ((1, 2), (3, 3), (6, 2), (11, 1)):
            with self.subTest(rank=rank, claimed=claimed), self.assertRaises(
                Phase4CValidationError
            ):
                fuse(
                    [LexicalCandidate(document_id="a", bm25=-1.0)],
                    (),
                    (),
                    credits=(
                        SemanticCredit(
                            document_id="a",
                            rank=rank,
                            tier_credit=claimed,
                            cosine_dot=1,
                            cosine_norm_squared_product=1,
                        ),
                    ),
                    alias_phrase_points=ALIAS_PHRASE_POINTS,
                )

    def test_fusion_refuses_a_duplicate_semantic_credit(self) -> None:
        credit = SemanticCredit(
            document_id="a",
            rank=1,
            tier_credit=3,
            cosine_dot=1,
            cosine_norm_squared_product=1,
        )
        with self.assertRaises(Phase4CValidationError):
            fuse(
                [LexicalCandidate(document_id="a", bm25=-1.0)],
                (),
                (),
                credits=(credit, credit),
                alias_phrase_points=ALIAS_PHRASE_POINTS,
            )

    def test_the_semantic_signal_never_excludes_anything(self) -> None:
        # ADR-0032's three exclusion invariants keep holding by construction:
        # this signal contributes score and returns no verdict, so the excluded
        # set is untouched by turning it on.
        with_signal = result_by_id(frozen_report())
        without = result_by_id(three_signal_report())
        for query_id, entry in with_signal.items():
            with self.subTest(query=query_id):
                self.assertEqual(
                    entry["excluded_ids"], without[query_id]["excluded_ids"]
                )
        for entry in frozen_report()["results"]:
            for hit in entry["hits"]:
                if hit["signals"] == ["semantic"]:
                    with self.subTest(query=entry["id"], document=hit["document_id"]):
                        # An introduced document can still be excluded by the
                        # disclaimer signal; what it can never be is excluded BY
                        # the semantic signal, which returns no verdict at all.
                        self.assertEqual(hit["semantic_tier_credit"] > 0, True)

    def test_disabling_the_signal_is_a_true_noop_on_every_score(self) -> None:
        plain = three_signal_report()
        for entry in plain["results"]:
            for hit in entry["hits"]:
                with self.subTest(query=entry["id"], document=hit["document_id"]):
                    self.assertIsNone(hit["semantic_rank"])
                    self.assertEqual(hit["semantic_tier_credit"], 0)
                    self.assertIsNone(hit["cosine_dot"])
        for raw in plain["operational"]["results"]:
            for hit in raw["hits"]:
                with self.subTest(query=raw["id"], document=hit["document_id"]):
                    self.assertEqual(hit["semantic_points"], 0)
                    self.assertEqual(hit["fused_score"], hit["pre_score"])

    def test_the_signal_introduces_documents_and_that_is_declared(self) -> None:
        declared = frozen_report()["declared_method"]["semantic_signal"]
        self.assertTrue(declared["may_introduce_a_document"])
        self.assertEqual(declared["exclusion_effect"], "none")
        introduced = {
            entry["id"]: entry["semantic_introduced_ids"]
            for entry in frozen_report()["results"]
        }
        self.assertEqual(len(introduced), BOUNDS.query_count)
        self.assertTrue(all(introduced.values()))
        for query_id, ids in introduced.items():
            with self.subTest(query=query_id):
                self.assertEqual(ids, sorted(ids))
                self.assertLessEqual(len(ids), BOUNDS.semantic_candidate_limit)


# --------------------------------------------------------------------------
# 6. Report identity and bounds
# --------------------------------------------------------------------------


class SemanticReportIdentityTests(unittest.TestCase):
    def test_the_partition_key_and_manifest_hash_are_in_the_content_hash(self) -> None:
        report = frozen_report()
        self.assertEqual(report["semantic_partition_key"], PARTITION_KEY_STRING)
        self.assertEqual(
            report["semantic_partition_manifest_hash"], PARTITION_MANIFEST_HASH
        )
        preimage = semantic_preimage(report)
        self.assertIn("semantic_partition_key", preimage)
        self.assertIn("semantic_partition_manifest_hash", preimage)

    def test_the_declared_manifest_hash_is_the_manifest_bytes_own_hash(self) -> None:
        body = json.loads((PARTITION / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(body["hash_rule"], SEMANTIC_HASH_RULE)
        self.assertEqual(body["content_hash"], PARTITION_MANIFEST_HASH)
        self.assertEqual(_seal(body)["content_hash"], PARTITION_MANIFEST_HASH)
        self.assertEqual(
            load_semantic_partition(PARTITION).manifest_hash, PARTITION_MANIFEST_HASH
        )

    def test_the_partition_key_is_the_declared_four_component_tuple(self) -> None:
        key = declared_partition_key()
        self.assertEqual(key.provider, "fixture_synthetic")
        self.assertEqual(key.model_identifier, "adaivy-cooccurrence-anchor-v1")
        self.assertEqual(key.dimension, 32)
        self.assertEqual(key.normalization, "round_half_even_scale_2p30")
        self.assertEqual(key.key_string(), PARTITION_KEY_STRING)
        self.assertEqual(key.coordinate_limit, 2**30)

    def test_the_partition_root_is_derived_from_the_fixture_root(self) -> None:
        self.assertEqual(default_partition_root(FIXTURES), PARTITION)
        self.assertEqual(
            default_partition_root(Path("/anywhere/else/phase4c")),
            Path("/anywhere/else/phase4c-semantic"),
        )

    def test_an_injected_signal_is_recorded_in_the_overrides(self) -> None:
        from math_research.phase4c.probes import _StubSemanticSignal

        stubbed = evaluate_hybrid(
            FIXTURES,
            semantic_signal=_StubSemanticSignal(sha256_bytes(b"identity-probe")),
        )
        self.assertEqual(
            stubbed["signal_configuration"]["overrides"], ["semantic_signal"]
        )
        self.assertEqual(
            stubbed["signal_configuration"]["semantic_signal_id"],
            "stub-semantic-signal",
        )
        self.assertNotEqual(stubbed["content_hash"], frozen_report()["content_hash"])
        self.assertEqual(frozen_report()["signal_configuration"]["overrides"], [])
        self.assertEqual(
            frozen_report()["signal_configuration"]["semantic_signal_id"],
            semantic_module.METHOD,
        )

    def test_the_report_stays_inside_its_byte_bound_with_four_signals(self) -> None:
        size = len(canonical_bytes(frozen_report()))
        self.assertLessEqual(size, BOUNDS.max_report_bytes)
        # Recorded, because ADR-0066 named this a real risk worth measuring
        # early: the fourth signal roughly triples the report.
        self.assertGreater(size, len(canonical_bytes(three_signal_report())))
        self.assertLess(size, 200_000)

    def test_every_hit_of_every_query_carries_all_five_semantic_fields(self) -> None:
        hits = 0
        for entry in frozen_report()["results"]:
            for hit in entry["hits"]:
                with self.subTest(query=entry["id"], document=hit["document_id"]):
                    for field in (
                        "semantic_rank",
                        "semantic_tier_credit",
                        "cosine_dot",
                        "cosine_norm_squared_product",
                    ):
                        self.assertIn(field, hit)
                hits += 1
        for raw in frozen_report()["operational"]["results"]:
            for hit in raw["hits"]:
                self.assertIn("semantic_points", hit)
        self.assertGreater(hits, BOUNDS.query_count)

    def test_resource_bounds_declare_the_semantic_constants(self) -> None:
        declared = frozen_report()["resource_bounds"]
        self.assertEqual(declared["semantic_candidate_limit"], 10)
        self.assertEqual(declared["semantic_tier_points"], 1)
        self.assertEqual(declared["policy_sha256"], BOUNDS.policy_sha256)

    def test_the_semantic_signal_claims_no_epistemic_effect(self) -> None:
        declared = frozen_report()["declared_method"]["semantic_signal"]
        self.assertFalse(declared["is_evidence"])
        self.assertFalse(declared["creates_applicability_record"])
        self.assertFalse(declared["creates_epistemic_warrant"])
        self.assertFalse(declared["calls_a_provider"])
        self.assertFalse(declared["opens_a_connection"])
        self.assertFalse(declared["constructs_float"])
        self.assertFalse(declared["divides"])
        self.assertEqual(declared["corpus_provenance"], "project_authored")


# --------------------------------------------------------------------------
# 7. Zero network, zero spend
# --------------------------------------------------------------------------


class SemanticZeroCostTests(unittest.TestCase):
    def test_a_full_four_signal_run_needs_no_network_at_all(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network attempted")
        ), patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("DNS attempted")
        ):
            report = evaluate_hybrid(FIXTURES)
            partition = load_semantic_partition(PARTITION)
        self.assertEqual(report["metrics"]["external_spend_usd"], 0)
        self.assertEqual(report["metrics"]["network_calls"], 0)
        self.assertEqual(report["metrics"]["model_or_api_calls"], 0)
        self.assertEqual(report["metrics"]["downloaded_artifacts"], 0)
        self.assertEqual(
            report["gate_evaluation"]["external_spend_usd"]["status"], "pass"
        )
        self.assertEqual(partition.manifest_hash, PARTITION_MANIFEST_HASH)

    def test_the_probes_need_no_network_either(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network attempted")
        ), patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("DNS attempted")
        ):
            report = run_probes(FIXTURES)
        self.assertEqual(report["probes_flipped"], report["probes_total"])


# --------------------------------------------------------------------------
# 8. Fail-closed partition reading
# --------------------------------------------------------------------------


class SemanticPartitionRefusalTests(PartitionStaging):
    def test_a_staged_copy_of_the_frozen_partition_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            loaded = load_semantic_partition(root)
            self.assertEqual(loaded.manifest_hash, PARTITION_MANIFEST_HASH)

    def test_an_absent_partition_refuses_and_never_degrades(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            absent = Path(directory) / "not-a-partition"
            with self.assertRaises(Phase4CValidationError) as caught:
                load_semantic_partition(absent)
            self.assertIn("is a refusal, not a degradation", str(caught.exception))
            with self.assertRaises(Phase4CValidationError):
                evaluate_hybrid(FIXTURES, semantic_partition=absent)

    def test_a_fixture_root_with_no_sibling_partition_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            staged = Path(directory) / "phase4c"
            shutil.copytree(FIXTURES, staged)
            with self.assertRaises(Phase4CValidationError):
                evaluate_hybrid(staged)

    def test_a_partition_key_mismatch_refuses_on_every_component(self) -> None:
        components = {
            "provider": "openai",
            "model_identifier": "adaivy-cooccurrence-anchor-v2",
            "dimension": 16,
            "normalization": "unit_l2_scale_2p30",
        }
        for component, value in components.items():
            with tempfile.TemporaryDirectory() as directory:
                root = self._stage(directory)
                self._rewrite_manifest(
                    root,
                    lambda body, c=component, v=value: body["partition_key"].__setitem__(
                        c, v
                    ),
                )
                with self.subTest(component=component):
                    self.assertIn(
                        "semantic partition mismatch", self._refuses(root)
                    )

    def test_an_unknown_or_missing_manifest_field_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_manifest(root, lambda body: body.__setitem__("extra", 1))
            self.assertIn("unknown keys", self._refuses(root))
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_manifest(root, lambda body: body.pop("generator"))
            self.assertIn("missing keys", self._refuses(root))

    def test_a_duplicate_json_key_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            (root / "manifest.json").write_text(
                '{"schema_version":"adaivy.vector-partition-manifest.v1",'
                '"schema_version":"adaivy.vector-partition-manifest.v1"}',
                encoding="utf-8",
            )
            self.assertIn("duplicate JSON key", self._refuses(root))

    def test_a_decimal_anywhere_in_the_bytes_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            raw = (root / "manifest.json").read_text(encoding="utf-8")
            (root / "manifest.json").write_text(
                raw.replace('"coordinate_bound_absolute":1073741824',
                            '"coordinate_bound_absolute":1073741824.0'),
                encoding="utf-8",
            )
            self.assertIn("inexact literal", self._refuses(root))
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._patch_artifact_bytes(
                root,
                "artifacts/documents/psd-notation.json",
                lambda raw: raw.replace('"coordinates":[', '"coordinates":[1.5,', 1),
            )
            self.assertIn("inexact literal", self._refuses(root))

    def test_a_tampered_manifest_hash_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_manifest(
                root,
                lambda body: body.__setitem__("corpus_fixture_root", "elsewhere"),
                reseal=False,
            )
            self.assertIn("content hash mismatch", self._refuses(root))

    def test_an_unknown_hash_rule_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_manifest(
                root, lambda body: body.__setitem__("hash_rule", "pop_before_hash")
            )
            self.assertIn("manifest.hash_rule", self._refuses(root))

    def test_a_provider_embedded_claim_on_a_fixture_partition_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_manifest(
                root,
                lambda body: body.__setitem__(
                    "corpus_provenance", "provider_embedded"
                ),
            )
            self.assertIn("manifest.corpus_provenance", self._refuses(root))

    def test_a_tampered_artifact_byte_hash_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)

            def blank(body: dict) -> None:
                for entry in body["documents"]:
                    if entry["document_id"] == "spectral-lemma":
                        entry["artifact_sha256"] = sha256_bytes(b"not-the-bytes")

            self._rewrite_manifest(root, blank)
            self.assertIn("artifact_sha256", self._refuses(root))

    def test_a_tampered_artifact_content_hash_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            relative = "artifacts/documents/spectral-lemma.json"
            self._rewrite_artifact(
                root,
                relative,
                lambda body: body["coordinates"].__setitem__(0, 1),
                reseal=False,
            )
            self.assertIn("content hash mismatch", self._refuses(root))

    def test_a_coordinate_outside_the_declared_scale_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_artifact(
                root,
                "artifacts/documents/spectral-lemma.json",
                lambda body: body["coordinates"].__setitem__(0, 2**30 + 1),
            )
            self.assertIn("a fault, not a rounding detail", self._refuses(root))

    def test_a_coordinate_exactly_at_the_scale_boundary_is_accepted(self) -> None:
        # The declared scale is a CLOSED range: 2**30 is in range.
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_artifact(
                root,
                "artifacts/documents/spectral-lemma.json",
                lambda body: body["coordinates"].__setitem__(0, -(2**30)),
            )
            load_semantic_partition(root)

    def test_a_wrong_dimension_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_artifact(
                root,
                "artifacts/documents/spectral-lemma.json",
                lambda body: body.__setitem__("coordinates", body["coordinates"][:-1]),
            )
            self.assertIn("dimension", self._refuses(root))

    def test_a_boolean_coordinate_is_refused_and_never_coerced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_artifact(
                root,
                "artifacts/documents/spectral-lemma.json",
                lambda body: body["coordinates"].__setitem__(0, True),
            )
            self.assertIn("expected an integer", self._refuses(root))

    def test_a_wrong_cardinality_refuses(self) -> None:
        for name, count_key in (("documents", "document_count"), ("queries", "query_count")):
            with tempfile.TemporaryDirectory() as directory:
                root = self._stage(directory)

                def drop(body: dict, n=name, c=count_key) -> None:
                    body[n] = body[n][:-1]
                    body["expected_counts"][c] -= 1
                    body["expected_counts"]["artifact_count"] -= 1

                self._rewrite_manifest(root, drop)
                with self.subTest(list=name):
                    self.assertIn("semantic", self._refuses(root))

    def test_a_declared_count_that_disagrees_with_the_bytes_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_manifest(
                root,
                lambda body: body["expected_counts"].__setitem__("artifact_count", 35),
            )
            self.assertIn("artifact count", self._refuses(root))

    def test_an_artifact_path_escape_refuses(self) -> None:
        for bad in (
            "../manifest.json",
            "/etc/hosts",
            "artifacts/documents/../../manifest.json",
            "artifacts/queries/spectral-lemma.json",
        ):
            with tempfile.TemporaryDirectory() as directory:
                root = self._stage(directory)

                def repoint(body: dict, path=bad) -> None:
                    for entry in body["documents"]:
                        if entry["document_id"] == "spectral-lemma":
                            entry["artifact_path"] = path

                self._rewrite_manifest(root, repoint)
                with self.subTest(path=bad):
                    self.assertRaises(
                        Phase4CValidationError, load_semantic_partition, root
                    )

    def test_a_misfiled_artifact_kind_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            self._rewrite_artifact(
                root,
                "artifacts/documents/spectral-lemma.json",
                lambda body: body.__setitem__("artifact_kind", "query"),
            )
            self.assertIn("artifact_kind", self._refuses(root))

    def test_an_absent_artifact_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            (root / "artifacts" / "documents" / "spectral-lemma.json").unlink()
            self.assertIn("is absent", self._refuses(root))

    def test_an_id_that_is_both_a_document_and_a_query_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._stage(directory)
            relative = "artifacts/queries/lemma-spectral.json"
            self._rewrite_artifact(
                root, relative, lambda body: body.__setitem__(
                    "document_id", "spectral-lemma"
                )
            )

            def rename(body: dict) -> None:
                for entry in body["queries"]:
                    if entry["artifact_path"] == relative:
                        entry["document_id"] = "spectral-lemma"

            self._rewrite_manifest(root, rename)
            self.assertIn("appears twice in the partition", self._refuses(root))


# --------------------------------------------------------------------------
# 9. The recorded regressions. ADR-0066 got these wrong.
# --------------------------------------------------------------------------


class SemanticRecordedRegressionTests(unittest.TestCase):
    """The findings this slice reports AGAINST itself.

    ADR-0066's recorded prediction was that the two vocabulary-mismatch gates
    improve or hold, the other three hold, and `duplicate_rate_at_5` is the live
    risk. All seven gates pass. Three things the gates do not measure moved in
    the wrong direction, and they are asserted here so the slice cannot be read
    as an unqualified improvement.
    """

    def test_three_renamed_golds_lost_rank_one_to_the_semantic_signal(self) -> None:
        after = result_by_id(frozen_report())
        before = result_by_id(three_signal_report())
        observed = []
        for query_id, entry in after.items():
            for gold in entry["relevant_ids"]:
                old = before[query_id]["ordered_ids"]
                new = entry["ordered_ids"]
                if gold not in old or gold not in new:
                    continue
                if old.index(gold) != new.index(gold):
                    observed.append(
                        (query_id, gold, old.index(gold) + 1, new.index(gold) + 1)
                    )
        self.assertEqual(
            tuple(sorted(observed)),
            tuple(sorted(RECORDED_REGRESSIONS["gold_displaced_from_rank_one"])),
        )
        # Every one of them stayed inside its top-k, which is exactly why no
        # gate sees it.
        for query_id, gold, _old, _new in observed:
            with self.subTest(query=query_id):
                self.assertIn(gold, after[query_id]["ordered_ids"])
                self.assertEqual(after[query_id]["missed_relevant_ids"], [])

    def test_the_adr_0066_inversion_claim_holds_only_for_bm25_carried_golds(
        self,
    ) -> None:
        """ADR-0066 says three points "cannot on its own invert a lexical gold
        ordering" because three is below the 4.4 smallest BM25 gold margin. That
        is true of the BM25-carried golds and FALSE of the alias-carried ones:
        the renamed controls sit at rank one on alias margins near 1.5.
        """

        raw = {
            item["id"]: {hit["document_id"]: hit for hit in item["hits"]}
            for item in three_signal_report()["operational"]["results"]
        }
        before = result_by_id(three_signal_report())
        for query_id, gold, _old, _new in RECORDED_REGRESSIONS[
            "gold_displaced_from_rank_one"
        ]:
            order = before[query_id]["fused_candidate_ids"]
            self.assertEqual(order[0], gold)
            margin = (
                raw[query_id][order[0]]["fused_score"]
                - raw[query_id][order[1]]["fused_score"]
            )
            with self.subTest(query=query_id):
                self.assertLess(
                    margin,
                    BOUNDS.semantic_tier_points * MAXIMUM_SEMANTIC_TIER_CREDIT,
                )
                self.assertGreater(raw[query_id][gold]["alias_points"], 0)

    def test_a_non_applicable_document_newly_enters_eleven_windows(self) -> None:
        after = result_by_id(frozen_report())
        before = result_by_id(three_signal_report())
        self.assertEqual(
            sum(1 for entry in before.values() if entry["inapplicable_retrieved_ids"]),
            0,
        )
        newly = {
            query_id: entry["inapplicable_retrieved_ids"]
            for query_id, entry in after.items()
            if entry["inapplicable_retrieved_ids"]
        }
        self.assertEqual(
            len(newly),
            RECORDED_REGRESSIONS["queries_newly_retrieving_a_non_applicable_document"],
        )
        self.assertEqual(
            {identifier for ids in newly.values() for identifier in ids},
            {"optimization-distractor"},
        )
        # And the gate cannot see it, because it is precision over RELEVANT
        # retrieved documents and this document is not in those gold sets.
        self.assertEqual(frozen_report()["metrics"]["applicability_precision_at_5"], 1.0)

    def test_the_duplicate_rate_fell_by_dilution_and_not_by_fewer_hits(self) -> None:
        after = frozen_report()["metric_support"]["duplicate_rate_at_5"]
        before = three_signal_report()["metric_support"]["duplicate_rate_at_5"]
        self.assertEqual(before, {"numerator": 1, "denominator": 50, "defined": True})
        self.assertEqual(after, {"numerator": 1, "denominator": 85, "defined": True})
        self.assertEqual(after["numerator"], before["numerator"])
        self.assertEqual(
            after["denominator"], BOUNDS.query_count * BOUNDS.duplicate_cutoff
        )
        # The declared duplicate pair is co-retrieved on exactly the one query it
        # was co-retrieved on before -- the fixture author measured it as the most
        # similar pair in the corpus, so the risk was real and it simply did not
        # produce a NEW co-retrieval.
        after_ids = {
            entry["id"]: entry["duplicate_ids_at_5"]
            for entry in frozen_report()["results"]
            if entry["duplicate_ids_at_5"]
        }
        self.assertEqual(
            after_ids, {"applicability-certificate": ["duplicate-certificate-b"]}
        )

    def test_the_alias_weight_is_now_load_bearing(self) -> None:
        self.assertFalse(RECORDED_REGRESSIONS["alias_weight_invariance_holds"])
        degraded = evaluate_hybrid(FIXTURES, alias_phrase_points=0.001)
        self.assertAlmostEqual(
            degraded["metrics"]["renamed_known_result_recall_at_10"], 0.5, places=12
        )
        self.assertEqual(
            degraded["gate_evaluation"]["renamed_known_result_recall_at_10"]["status"],
            "fail",
        )
        # `ALIAS_PHRASE_POINTS` is NOT retuned in response. It stays at the unit
        # value it has always had.
        self.assertEqual(ALIAS_PHRASE_POINTS, 1.0)

    def test_all_seven_gates_still_pass_and_that_is_stated_with_its_caveats(
        self,
    ) -> None:
        summary = frozen_report()["gate_summary"]
        self.assertEqual(summary, {"pass": 7, "fail": 0, "undetermined": 0,
                                   "overall": "pass"})
        # Two of the five ratio gates were already at their ceiling under
        # ADR-0032, so "improve or hold" could only ever be "hold" for them.
        for name in (
            "notation_variant_recall_at_5",
            "renamed_known_result_recall_at_10",
        ):
            with self.subTest(metric=name):
                self.assertEqual(three_signal_report()["metrics"][name], 1.0)
                self.assertEqual(frozen_report()["metrics"][name], 1.0)


if __name__ == "__main__":
    unittest.main()
