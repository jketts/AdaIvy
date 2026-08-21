"""Exact graph spectral engine and counter-candidate replay.

This package is the first in-repository implementation of
``exact_graph_distance_and_invariant_space_v2``, the engine named in
``cert.graffiti-322-exact-separation``.  Before it, the shipped certificate
recorded only a result hash produced by an external script and was not
reproducible from this repository; the values it asserts are now *checked* here.

It is also the counter-candidate replay engine: given a witness graph a prior
published work offered, :func:`replay_candidate` evaluates that witness under
every reading tuple of the contested terms and records a verdict for each.

Arithmetic is exact everywhere: ``int`` and ``fractions.Fraction`` only.  No
``float`` is constructed in this package, there is no tolerance and no epsilon,
and a comparison that cannot be decided exactly is a typed refusal rather than
a guess.  Nothing here creates mathematical warrant, novelty, significance,
source applicability, or graph admission.
"""

from __future__ import annotations

from .graph import (
    MAX_GRAPH_ORDER,
    SPEC_SCHEMA_VERSION,
    ExactGraphError,
    GraffitiLayout,
    Graph,
    GraphError,
    bfs_distances,
    build_graph,
    cycle,
    graffiti_family,
    graffiti_family_layout,
    is_connected,
    is_triangle_free,
    kneser,
    load_graph_spec,
)
from .invariants import (
    EVEN_READINGS,
    InvariantError,
    even_count,
    even_count_profile,
    inverse_even,
)
from .replay import (
    ENGINE_ID,
    READING_TUPLES,
    REPLAY_SCHEMA_VERSION,
    VERDICTS,
    ReadingResult,
    ReplayError,
    ReplayResult,
    reading_tuple_product,
    replay_candidate,
)
from .spectrum import (
    BLOCKS_SCHEMA_VERSION,
    MAX_DENSE_ORDER,
    MAX_ISOLATION_STEPS,
    MAX_REFINEMENT_STEPS,
    MAX_ROOT_ENUMERATION,
    RANGE_READINGS,
    BasisWitness,
    Decomposition,
    DecompositionBlocks,
    SpectrumError,
    characteristic_polynomial,
    decomposition_root_polynomial,
    distance_matrix,
    distinct_eigenvalue_count,
    distinct_eigenvalue_lower_bound,
    distinct_root_count,
    krylov_annihilator,
    load_decomposition_blocks,
    minimal_polynomial,
    propose_graffiti_decomposition,
    rayleigh_extent_bound,
    spectral_extent_vs,
    squarefree_part,
    total_distance,
    verify_decomposition,
)

__all__ = [
    "BLOCKS_SCHEMA_VERSION", "BasisWitness", "Decomposition", "DecompositionBlocks",
    "ENGINE_ID", "EVEN_READINGS", "ExactGraphError", "GraffitiLayout", "Graph",
    "GraphError", "InvariantError", "MAX_DENSE_ORDER", "MAX_GRAPH_ORDER",
    "MAX_ISOLATION_STEPS", "MAX_REFINEMENT_STEPS", "MAX_ROOT_ENUMERATION",
    "RANGE_READINGS", "READING_TUPLES", "REPLAY_SCHEMA_VERSION", "ReadingResult",
    "ReplayError", "ReplayResult", "SPEC_SCHEMA_VERSION", "SpectrumError",
    "VERDICTS", "bfs_distances", "build_graph", "characteristic_polynomial",
    "cycle", "decomposition_root_polynomial", "distance_matrix",
    "distinct_eigenvalue_count", "distinct_eigenvalue_lower_bound",
    "distinct_root_count", "even_count", "even_count_profile", "graffiti_family",
    "graffiti_family_layout", "inverse_even", "is_connected", "is_triangle_free",
    "kneser", "krylov_annihilator", "load_decomposition_blocks",
    "load_graph_spec", "minimal_polynomial", "propose_graffiti_decomposition",
    "rayleigh_extent_bound", "reading_tuple_product", "replay_candidate",
    "spectral_extent_vs",
    "squarefree_part", "total_distance", "verify_decomposition",
]
