"""Bounded multi-hop retrieval with a deterministic trace.

Contract Section 6. Each iteration retrieves candidates, proposes terminology,
expands equivalent formulations and notation, follows dependencies within the hop
budget, deliberately seeks a contrasting approach, and appends attributed graph
proposals. It stops only with a Section 5 terminal reason.

One top-k query is explicitly insufficient, so the loop is structured so that a
single iteration cannot satisfy it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .budget import BudgetExhausted, BudgetLedger, BudgetPolicy
from .ports import IndexHit, IndexedResult, ResultIndex
from .records import identifier, text
from .serialization import canonical_hash, stable_id
from .state import (
    TERMINAL_COMPLETED,
    TERMINAL_CONVERGED,
    SynthesisValidationError,
    ValueEnum,
    validate_terminal_reason,
)


class QueryOrigin(ValueEnum):
    """How a query or traversal was generated. Recorded per Section 6."""

    SEED = "seed"
    TERMINOLOGY_EXPANSION = "terminology_expansion"
    NOTATION_EXPANSION = "notation_expansion"
    CITATION_TRAVERSAL = "citation_traversal"
    CONTRASTING_APPROACH = "contrasting_approach"


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalStep:
    """One query or traversal with its parent and ordered results."""

    step_id: str
    origin: QueryOrigin
    query: str
    parent_result_ids: tuple[str, ...]
    ordered_result_ids: tuple[str, ...]
    excluded_result_ids: tuple[str, ...]
    hits: tuple[IndexHit, ...] = field(default=())

    def value(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "origin": self.origin.value,
            "query": self.query,
            "parent_result_ids": list(self.parent_result_ids),
            "ordered_result_ids": list(self.ordered_result_ids),
            "excluded_result_ids": list(self.excluded_result_ids),
            "hits": [
                {
                    "result_id": hit.result_id,
                    "rank": hit.rank,
                    "canonical_score": hit.canonical_score,
                    "tie_break_key": hit.tie_break_key,
                }
                for hit in self.hits
            ],
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalIteration:
    """The deterministic per-iteration trace required by Section 6."""

    iteration: int
    input_graph_snapshot_identity: str
    adapter_id: str
    adapter_version: str
    filters: tuple[tuple[str, str], ...]
    budgets_before: dict[str, int]
    budgets_after: dict[str, int]
    steps: tuple[RetrievalStep, ...]
    graph_nodes_added: tuple[str, ...]
    graph_edges_added: tuple[tuple[str, str], ...]
    contrasting_result_ids: tuple[str, ...]
    output_graph_snapshot_identity: str

    def value(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "input_graph_snapshot_identity": self.input_graph_snapshot_identity,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "filters": [{"name": name, "value": value} for name, value in self.filters],
            "budgets_before": dict(self.budgets_before),
            "budgets_after": dict(self.budgets_after),
            "steps": [step.value() for step in self.steps],
            "graph_nodes_added": list(self.graph_nodes_added),
            "graph_edges_added": [list(edge) for edge in self.graph_edges_added],
            "contrasting_result_ids": list(self.contrasting_result_ids),
            "output_graph_snapshot_identity": self.output_graph_snapshot_identity,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalTrace:
    """The complete trace for one bounded multi-hop run."""

    trace_id: str
    seed_queries: tuple[str, ...]
    iterations: tuple[RetrievalIteration, ...]
    discovered_result_ids: tuple[str, ...]
    contrasting_result_ids: tuple[str, ...]
    terminal_reason: str
    corpus_manifest_hash: str

    def value(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "seed_queries": list(self.seed_queries),
            "iterations": [item.value() for item in self.iterations],
            "discovered_result_ids": list(self.discovered_result_ids),
            "contrasting_result_ids": list(self.contrasting_result_ids),
            "terminal_reason": self.terminal_reason,
            "corpus_manifest_hash": self.corpus_manifest_hash,
        }

    def iteration_count(self) -> int:
        return len(self.iterations)

    def origins_used(self) -> frozenset[str]:
        return frozenset(
            step.origin.value for iteration in self.iterations for step in iteration.steps
        )


class MultiHopRetriever:
    """Bounded iterative retrieval over a `ResultIndex`.

    Holds no source content. Every loop body charges a named counter before the
    work it guards, and the run ends with exactly one terminal reason.
    """

    def __init__(
        self,
        index: ResultIndex,
        *,
        policy: BudgetPolicy,
        eligible_result_ids: Sequence[str] | None = None,
    ) -> None:
        self.index = index
        self.policy = policy
        self.ledger = BudgetLedger(policy)
        # Rights and applicability filtering happens before retrieval, so an
        # ineligible result is absent from the candidate set rather than ranked
        # lower. `None` means no restriction was supplied.
        self.eligible = None if eligible_result_ids is None else frozenset(eligible_result_ids)

    def _filters(self) -> tuple[tuple[str, str], ...]:
        return (
            ("quarantine", "exclude"),
            ("rights", "local_retrieval"),
            ("applicability", "effective_checked_only" if self.eligible is not None else "unfiltered"),
        )

    def _admit(self, hits: Sequence[IndexHit]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        ordered: list[str] = []
        excluded: list[str] = []
        for hit in hits:
            if self.eligible is not None and hit.result_id not in self.eligible:
                excluded.append(hit.result_id)
            else:
                ordered.append(hit.result_id)
        return tuple(ordered), tuple(excluded)

    def _snapshot(self, nodes: Sequence[str], edges: Sequence[tuple[str, str]]) -> str:
        return canonical_hash({"nodes": sorted(nodes), "edges": sorted(list(edge) for edge in edges)})

    def _query(
        self,
        query: str,
        *,
        origin: QueryOrigin,
        parents: Sequence[str],
    ) -> RetrievalStep:
        """Run one query. Charges `query_fan_out` before searching."""
        self.ledger.consume("query_fan_out")
        hits = self.index.search(query, limit=self.policy.results_per_query)
        if len(hits) > self.policy.results_per_query:
            raise SynthesisValidationError("index returned more results than the per-query bound")
        ordered, excluded = self._admit(hits)
        return RetrievalStep(
            step_id=stable_id("retrieval-step", {"origin": origin.value, "query": query}),
            origin=origin,
            query=query,
            parent_result_ids=tuple(parents),
            ordered_result_ids=ordered,
            excluded_result_ids=excluded,
            hits=tuple(hits),
        )

    def run(
        self,
        *,
        seed_queries: Sequence[str],
        contrasting_signature: str,
        max_iterations: int | None = None,
    ) -> RetrievalTrace:
        """Execute the bounded loop and return the complete trace."""
        if not seed_queries:
            raise SynthesisValidationError("at least one seed query is required")
        for query in seed_queries:
            text(query, field="seed_query")
        text(contrasting_signature, field="contrasting_signature")

        limit = self.policy.retrieval_iterations if max_iterations is None else max_iterations
        discovered: list[str] = []
        contrasting: list[str] = []
        nodes: list[str] = []
        edges: list[tuple[str, str]] = []
        iterations: list[RetrievalIteration] = []
        terminal_reason = TERMINAL_COMPLETED
        # Terms and citations harvested from the previous iteration's output.
        pending_terms: list[tuple[str, str]] = []
        pending_citations: list[tuple[str, str]] = []

        try:
            for index_number in range(1, limit + 1):
                self.ledger.consume("retrieval_iterations")
                before = self.ledger.consumed()
                input_snapshot = self._snapshot(nodes, edges)
                steps: list[RetrievalStep] = []
                iteration_nodes: list[str] = []
                iteration_edges: list[tuple[str, str]] = []
                iteration_contrasting: list[str] = []

                if index_number == 1:
                    for query in seed_queries:
                        steps.append(self._query(query, origin=QueryOrigin.SEED, parents=()))
                else:
                    # Terminology and notation expansion from prior output. This
                    # is what makes a contrasting approach reachable at all.
                    for parent, term in sorted(set(pending_terms)):
                        origin = (
                            QueryOrigin.NOTATION_EXPANSION
                            if any(character in term for character in "()\\^_")
                            else QueryOrigin.TERMINOLOGY_EXPANSION
                        )
                        steps.append(self._query(term, origin=origin, parents=(parent,)))
                    # Dependency traversal within the hop budget.
                    for parent, cited in sorted(set(pending_citations)):
                        self.ledger.consume("citation_dependency_hops")
                        steps.append(
                            self._query(cited, origin=QueryOrigin.CITATION_TRAVERSAL, parents=(parent,))
                        )
                    # Deliberately seek a contrasting approach.
                    steps.append(
                        self._query(
                            contrasting_signature,
                            origin=QueryOrigin.CONTRASTING_APPROACH,
                            parents=tuple(sorted(discovered)),
                        )
                    )

                pending_terms = []
                pending_citations = []
                for step in steps:
                    for result_id in step.ordered_result_ids:
                        if result_id in discovered:
                            continue
                        self.ledger.consume("unique_discovered_sources")
                        self.ledger.consume("graph_nodes")
                        discovered.append(result_id)
                        iteration_nodes.append(result_id)
                        nodes.append(result_id)
                        record = self.index.get(result_id)
                        if record.approach_signature == contrasting_signature:
                            # Recorded as contrasting, never silently composed.
                            iteration_contrasting.append(result_id)
                            contrasting.append(result_id)
                        pending_terms.extend((result_id, term) for term in record.terms)
                        pending_citations.extend(
                            (result_id, cited) for cited in record.citations
                        )
                        for parent in step.parent_result_ids:
                            self.ledger.consume("graph_edges")
                            iteration_edges.append((parent, result_id))
                            edges.append((parent, result_id))

                iterations.append(
                    RetrievalIteration(
                        iteration=index_number,
                        input_graph_snapshot_identity=input_snapshot,
                        adapter_id=self.index.adapter_id,
                        adapter_version=self.index.adapter_version,
                        filters=self._filters(),
                        budgets_before=before,
                        budgets_after=self.ledger.consumed(),
                        steps=tuple(steps),
                        graph_nodes_added=tuple(iteration_nodes),
                        graph_edges_added=tuple(iteration_edges),
                        contrasting_result_ids=tuple(iteration_contrasting),
                        output_graph_snapshot_identity=self._snapshot(nodes, edges),
                    )
                )

                # Convergence: a completed iteration that discovered nothing new
                # and left nothing to expand or traverse.
                if index_number > 1 and not iteration_nodes and not pending_citations:
                    terminal_reason = TERMINAL_CONVERGED
                    break
        except BudgetExhausted as exhausted:
            terminal_reason = exhausted.terminal_reason

        return RetrievalTrace(
            trace_id=stable_id(
                "retrieval-trace",
                {
                    "seed_queries": sorted(seed_queries),
                    "corpus_manifest_hash": self.index.corpus_manifest_hash(),
                },
            ),
            seed_queries=tuple(seed_queries),
            iterations=tuple(iterations),
            discovered_result_ids=tuple(discovered),
            contrasting_result_ids=tuple(contrasting),
            terminal_reason=validate_terminal_reason(terminal_reason),
            corpus_manifest_hash=self.index.corpus_manifest_hash(),
        )


__all__ = [
    "MultiHopRetriever",
    "QueryOrigin",
    "RetrievalIteration",
    "RetrievalStep",
    "RetrievalTrace",
]
