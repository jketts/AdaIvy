"""Acceptance scenario ERS-AC-01: genuine multi-hop three-source synthesis.

Runs against the real Phase 3A FTS5/BM25 index over project-authored synthetic
sources. The corpus is constructed so that C is reachable only by citation
traversal and D only by declared expansion, and the test asserts that property
directly rather than assuming it.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from math_research.domain.entities import OpaqueId
from math_research.phase3a.acquisition import ManualSourceIngestor
from math_research.phase3a.records import LicenseMetadata
from math_research.phase3a.workspace import ResearchMemoryWorkspace
from math_research.synthesis.budget import BudgetPolicy
from math_research.synthesis.phase3a_index import (
    ADAPTER_ID,
    Phase3AResultIndex,
    ResultDescriptor,
)
from math_research.synthesis.retrieval import MultiHopRetriever, QueryOrigin
from math_research.synthesis.state import validate_terminal_reason

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "synthesis"
MANIFEST = json.loads((FIXTURES / "corpus-manifest.json").read_text(encoding="utf-8"))
ACTOR = OpaqueId("actor.synthesis.operator")
AGGREGATE = OpaqueId("memory.synthesis.acceptance.v1")
T0 = "2026-08-20T00:00:00Z"

POLICY = BudgetPolicy.from_value(
    {
        "policy_version": "synthesis-retrieval-v1",
        "retrieval_iterations": 4,
        "citation_dependency_hops": 4,
        "query_fan_out": 32,
        "results_per_query": 5,
        "unique_discovered_sources": 64,
        "graph_nodes": 128,
        "graph_edges": 256,
        "branch_count": 4,
        "branch_generation_attempts": 4,
        "wall_clock_seconds": 60,
        "acquired_sources": 0,
        "acquired_bytes": 0,
        "branch_depth": 2,
        "model_calls": 0,
        "tool_calls": 0,
        "exploration_reserve_numerator": 1,
        "exploration_reserve_denominator": 4,
    }
)


class Corpus:
    """A real Phase 3A memory over the synthetic corpus."""

    def __init__(self, root: Path) -> None:
        self.workspace = ResearchMemoryWorkspace(root / "memory")
        ingestor = ManualSourceIngestor(self.workspace)
        license_value = MANIFEST["fixture_license"]
        license_metadata = LicenseMetadata(
            license_expression=license_value["license_expression"],
            copyright_notice=license_value["copyright_notice"],
            usage_rights=tuple(license_value["usage_rights"]),
            redistribution_status=license_value["redistribution_status"],
            evidence_uri=None,
            reviewed_by=ACTOR,
        )
        self.label_of_artifact: dict[str, str] = {}
        descriptors: dict[str, ResultDescriptor] = {}
        for source in MANIFEST["sources"]:
            result = ingestor.import_local(
                (FIXTURES / source["path"]).resolve(),
                supplied_uri=f"fixture:{source['label']}",
                title=source["title"],
                authors=("AdaIvy contributors",),
                publication_metadata={
                    "fixture_label": source["label"],
                    "project_authored": True,
                },
                license_metadata=license_metadata,
                declared_media_type="text/plain",
                actor_id=ACTOR,
                recorded_at=T0,
                aggregate_id=AGGREGATE,
            )
            if result.quarantined:
                raise AssertionError(
                    f"fixture {source['label']} quarantined: {result.quarantine_reasons}"
                )
            artifact_id = result.source_artifact.id.value
            self.label_of_artifact[artifact_id] = source["label"]
            descriptors[artifact_id] = ResultDescriptor(
                source_artifact_id=artifact_id,
                title=source["title"],
                expansion_terms=tuple(source["expansion_terms"]),
                citations=tuple(source["citations"]),
                approach_signature=source["approach_signature"],
            )
        manifest = self.workspace.rebuild_index(aggregate_id=AGGREGATE, now=T0)
        self.corpus_manifest_hash = manifest["content_hash"]
        self.index = Phase3AResultIndex(
            self.workspace,
            corpus_manifest_hash=self.corpus_manifest_hash,
            descriptors=descriptors,
            aggregate_id=AGGREGATE,
            actor_id=ACTOR,
            created_at=T0,
        )
        self.label_of_unit: dict[str, str] = {}
        for unit in self.workspace.records("evidence_unit"):
            if unit.source_artifact_id is not None:
                self.label_of_unit[unit.id.value] = self.label_of_artifact[
                    unit.source_artifact_id.value
                ]

    def labels(self, result_ids) -> set[str]:
        return {self.label_of_unit[item] for item in result_ids}

    def close(self) -> None:
        self.workspace.close()


class MultiHopSynthesisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.corpus = Corpus(Path(self.temporary.name))
        self.retriever = MultiHopRetriever(self.corpus.index, policy=POLICY)
        self.trace = self.retriever.run(
            seed_queries=MANIFEST["seed_queries"],
            contrasting_signature=MANIFEST["contrasting_signature"],
        )

    def tearDown(self) -> None:
        self.corpus.close()
        self.temporary.cleanup()

    # --- the fixture precondition itself ---------------------------------
    def test_c_and_d_are_not_initially_retrievable(self) -> None:
        """Fails if C or D is initially retrievable.

        Asserted against the real index at every permitted result count, so the
        scenario's precondition is proven rather than assumed.
        """
        for limit in range(1, POLICY.results_per_query + 1):
            hits = self.corpus.index.search(MANIFEST["seed_queries"][0], limit=limit)
            with self.subTest(limit=limit):
                self.assertTrue(
                    self.corpus.labels(hit.result_id for hit in hits) <= {"a-seed", "b-seed"}
                )

    def test_seed_iteration_returns_a_and_b(self) -> None:
        first = self.trace.iterations[0]
        labels = self.corpus.labels(
            result_id for step in first.steps for result_id in step.ordered_result_ids
        )
        self.assertEqual(labels, {"a-seed", "b-seed"})

    # --- the required trace ----------------------------------------------
    def test_trace_has_at_least_two_iterations(self) -> None:
        """One top-k query cannot satisfy this scenario."""
        self.assertGreaterEqual(self.trace.iteration_count(), 2)

    def test_trace_contains_an_expansion_and_a_traversal(self) -> None:
        origins = self.trace.origins_used()
        self.assertIn(QueryOrigin.SEED.value, origins)
        self.assertIn(QueryOrigin.CITATION_TRAVERSAL.value, origins)
        self.assertTrue(
            {QueryOrigin.TERMINOLOGY_EXPANSION.value, QueryOrigin.NOTATION_EXPANSION.value}
            & origins
        )
        self.assertIn(QueryOrigin.CONTRASTING_APPROACH.value, origins)

    def test_graph_is_updated_after_iteration_one(self) -> None:
        first, second = self.trace.iterations[0], self.trace.iterations[1]
        self.assertTrue(first.graph_nodes_added)
        # The second iteration's input snapshot is the first iteration's output.
        self.assertEqual(
            second.input_graph_snapshot_identity, first.output_graph_snapshot_identity
        )
        self.assertNotEqual(
            first.input_graph_snapshot_identity, first.output_graph_snapshot_identity
        )

    def test_every_iteration_records_adapter_filters_and_budget_counters(self) -> None:
        for iteration in self.trace.iterations:
            with self.subTest(iteration=iteration.iteration):
                self.assertEqual(iteration.adapter_id, ADAPTER_ID)
                self.assertTrue(iteration.adapter_version)
                self.assertIn(("quarantine", "exclude"), iteration.filters)
                self.assertLess(
                    iteration.budgets_before["retrieval_iterations"],
                    iteration.budgets_after["retrieval_iterations"] + 1,
                )
                # Budgets are recorded before and after, and consumption only rises.
                for counter, before in iteration.budgets_before.items():
                    self.assertGreaterEqual(iteration.budgets_after[counter], before)

    def test_run_declares_exactly_one_terminal_reason(self) -> None:
        self.assertEqual(
            validate_terminal_reason(self.trace.terminal_reason), self.trace.terminal_reason
        )
        self.assertIn(self.trace.terminal_reason, {"completed", "converged_under_rule"})

    # --- the expected output ---------------------------------------------
    def test_c_is_discovered_solely_by_citation_traversal(self) -> None:
        traversal_labels: set[str] = set()
        other_labels: set[str] = set()
        for iteration in self.trace.iterations:
            for step in iteration.steps:
                target = (
                    traversal_labels
                    if step.origin is QueryOrigin.CITATION_TRAVERSAL
                    else other_labels
                )
                target |= self.corpus.labels(step.ordered_result_ids)
        self.assertIn("c-traversal", traversal_labels)
        self.assertNotIn("c-traversal", other_labels)

    def test_d_is_discovered_solely_by_expansion_or_contrasting_query(self) -> None:
        expansion_origins = {
            QueryOrigin.TERMINOLOGY_EXPANSION,
            QueryOrigin.NOTATION_EXPANSION,
            QueryOrigin.CONTRASTING_APPROACH,
        }
        expansion_labels: set[str] = set()
        other_labels: set[str] = set()
        for iteration in self.trace.iterations:
            for step in iteration.steps:
                target = expansion_labels if step.origin in expansion_origins else other_labels
                target |= self.corpus.labels(step.ordered_result_ids)
        self.assertIn("d-contrasting", expansion_labels)
        self.assertNotIn("d-contrasting", other_labels)

    def test_all_three_composable_sources_plus_the_contrast_are_discovered(self) -> None:
        self.assertEqual(
            self.corpus.labels(self.trace.discovered_result_ids),
            {"a-seed", "b-seed", "c-traversal", "d-contrasting"},
        )

    def test_contrasting_result_is_recorded_and_not_silently_composed(self) -> None:
        """Expected: D recorded as contrasting without being silently composed."""
        self.assertTrue(self.trace.contrasting_result_ids)
        self.assertEqual(self.corpus.labels(self.trace.contrasting_result_ids), {"d-contrasting"})
        # Contrasting results are a separate, explicitly labelled set, so they
        # cannot be mistaken for composable inputs.
        composable = set(self.trace.discovered_result_ids) - set(self.trace.contrasting_result_ids)
        self.assertEqual(
            self.corpus.labels(composable), {"a-seed", "b-seed", "c-traversal"}
        )

    def test_no_manual_injection_of_c_or_d_occurred(self) -> None:
        """Forbidden: manual injection of C or D.

        Every discovered result must appear as an ordered result of some recorded
        step, so nothing can enter the set without a query that found it.
        """
        from_steps = {
            result_id
            for iteration in self.trace.iterations
            for step in iteration.steps
            for result_id in step.ordered_result_ids
        }
        self.assertEqual(set(self.trace.discovered_result_ids), from_steps)

    def test_forbidden_one_query_completion_cannot_reach_the_composition(self) -> None:
        """Forbidden: one-query/top-k completion."""
        single = self.retriever.__class__(self.corpus.index, policy=POLICY).run(
            seed_queries=MANIFEST["seed_queries"],
            contrasting_signature=MANIFEST["contrasting_signature"],
            max_iterations=1,
        )
        self.assertEqual(single.iteration_count(), 1)
        labels = self.corpus.labels(single.discovered_result_ids)
        self.assertNotIn("c-traversal", labels)
        self.assertNotIn("d-contrasting", labels)

    # --- determinism and bounds ------------------------------------------
    def test_trace_is_deterministic_across_repeated_runs(self) -> None:
        repeat = MultiHopRetriever(self.corpus.index, policy=POLICY).run(
            seed_queries=MANIFEST["seed_queries"],
            contrasting_signature=MANIFEST["contrasting_signature"],
        )
        self.assertEqual(repeat.value(), self.trace.value())

    def test_corpus_manifest_hash_is_recorded_in_the_trace(self) -> None:
        self.assertEqual(self.trace.corpus_manifest_hash, self.corpus.corpus_manifest_hash)

    def test_iteration_budget_exhaustion_names_the_counter(self) -> None:
        tight = BudgetPolicy.from_value({**POLICY.value(), "query_fan_out": 1})
        trace = MultiHopRetriever(self.corpus.index, policy=tight).run(
            seed_queries=MANIFEST["seed_queries"],
            contrasting_signature=MANIFEST["contrasting_signature"],
        )
        self.assertEqual(trace.terminal_reason, "budget_exhausted:query_fan_out")
        self.assertEqual(validate_terminal_reason(trace.terminal_reason), trace.terminal_reason)

    def test_ineligible_results_are_excluded_not_ranked_lower(self) -> None:
        """Section 11 applied to retrieval inputs."""
        eligible = [
            result_id
            for result_id, label in self.corpus.label_of_unit.items()
            if label != "b-seed"
        ]
        restricted = MultiHopRetriever(
            self.corpus.index, policy=POLICY, eligible_result_ids=eligible
        ).run(
            seed_queries=MANIFEST["seed_queries"],
            contrasting_signature=MANIFEST["contrasting_signature"],
        )
        self.assertNotIn("b-seed", self.corpus.labels(restricted.discovered_result_ids))
        excluded = {
            result_id
            for iteration in restricted.iterations
            for step in iteration.steps
            for result_id in step.excluded_result_ids
        }
        self.assertEqual(self.corpus.labels(excluded), {"b-seed"})
        for iteration in restricted.iterations:
            self.assertIn(("applicability", "effective_checked_only"), iteration.filters)


if __name__ == "__main__":
    unittest.main()
