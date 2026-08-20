"""Deterministic synthetic fixtures for the synthesis acceptance scenarios.

All content is project-authored under `LicenseRef-AdaIvy-Synthetic-Fixture`. The
mathematics is deliberately simple and self-contained; no real paper, author, or
citation is represented.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Importable both under `unittest discover -s tests`, which puts this directory
# on sys.path, and as `python3 -m unittest tests.test_synthesis_*`, which does
# not. Without this a standalone module run fails on the sibling import.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from math_research.synthesis.records import (
    NoveltyStatus,
    SourceAnchor,
    StateAxes,
    StructuredResearchResult,
)
from math_research.synthesis.state import (
    ExtractionFidelity,
    GraphAdmission,
    MathematicalWarrant,
    SourceApplicability,
)


def artifact_hash(seed: str) -> str:
    """A stable synthetic artifact hash. Not a hash of real content."""
    import hashlib

    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def anchor(
    *,
    source_id: str,
    version: str = "v1",
    role: str = "tex_source",
    spans: tuple[str, ...] = ("span.a1",),
    card: str = "evidence-card.a1",
) -> SourceAnchor:
    return SourceAnchor(
        source_id=source_id,
        source_version=version,
        representation_role=role,
        artifact_hash=artifact_hash(f"{source_id}:{version}:{role}"),
        span_ids=spans,
        evidence_card_id=card,
    )


def eligible_axes(
    *, warrant: MathematicalWarrant = MathematicalWarrant.PROOF_REVIEWED
) -> StateAxes:
    """Axes for a source-reviewed, source-checked, admissible result."""
    return StateAxes(
        source_applicability=SourceApplicability.CHECKED,
        extraction_fidelity=ExtractionFidelity.SOURCE_CHECKED,
        mathematical_warrant=warrant,
        graph_admission=GraphAdmission.PROPOSED,
    )


def result(
    *,
    result_id: str,
    statement: str,
    conclusion: str,
    assumptions: tuple[str, ...] = (),
    domains: tuple[str, ...] = ("finite_dimensional_hilbert_space",),
    codomains: tuple[str, ...] = ("real_numbers",),
    object_types: tuple[str, ...] = ("positive_semidefinite_operator",),
    regularity: tuple[str, ...] = (),
    quantifiers: tuple[dict[str, Any], ...] = (
        {"variable": "n", "kind": "universal", "bound": "n >= 1"},
    ),
    conclusion_strength: str = "exact",
    scope: tuple[str, ...] = ("synthetic fixture",),
    exceptions: tuple[str, ...] = (),
    dependencies: tuple[str, ...] = (),
    definition_mapping: tuple[dict[str, str], ...] = (
        {"symbol": "T", "definition": "a trace-preserving map"},
    ),
    notation_rule: str = "notation.rule-a",
    notation_version: str = "1.0.0",
    anchors: tuple[SourceAnchor, ...] | None = None,
    axes: StateAxes | None = None,
    novelty: NoveltyStatus = NoveltyStatus.NOT_ASSESSED,
) -> StructuredResearchResult:
    return StructuredResearchResult.from_value(
        {
            "result_id": result_id,
            "exact_statement": statement,
            "notation": {
                "rule_id": notation_rule,
                "rule_version": notation_version,
                "original_notation": statement,
                "normalized_notation": statement.lower(),
                "definition_mapping": list(definition_mapping),
            },
            "assumptions": list(assumptions),
            "domains": list(domains),
            "codomains": list(codomains),
            "object_types": list(object_types),
            "regularity": list(regularity),
            "quantifiers": list(quantifiers),
            "conclusion": conclusion,
            "conclusion_strength": conclusion_strength,
            "scope": list(scope),
            "exceptions": list(exceptions),
            "proof_technique": "synthetic direct argument",
            "dependencies": list(dependencies),
            "limitations": ["synthetic fixture only"],
            "anchors": [item.value() for item in (anchors or (anchor(source_id="source.a"),))],
            "axes": (axes or eligible_axes()).value(),
            "confidence_proposal": "non-authoritative fixture proposal",
            "extraction_method": "project-authored-fixture",
            "extraction_version": "1.0.0",
            "known_counterexamples": [],
            "novelty_status": novelty.value,
        }
    )


# A valid budget policy covering every Section 5 bound. Shared so no test module
# has to import another test module.
VALID_POLICY: dict[str, Any] = {
    "policy_version": "synthesis-budget-v1",
    "retrieval_iterations": 3,
    "citation_dependency_hops": 2,
    "query_fan_out": 4,
    "results_per_query": 5,
    "unique_discovered_sources": 10,
    "graph_nodes": 50,
    "graph_edges": 80,
    "branch_count": 6,
    "branch_generation_attempts": 8,
    "wall_clock_seconds": 60,
    "acquired_sources": 0,
    "acquired_bytes": 0,
    "branch_depth": 2,
    "model_calls": 0,
    "tool_calls": 3,
    "exploration_reserve_numerator": 1,
    "exploration_reserve_denominator": 4,
}
