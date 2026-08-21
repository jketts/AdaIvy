"""Exact finite simple graphs, and the boundary between a spec and a witness.

A :class:`Graph` here is a labelled finite simple graph and nothing more.  It
carries no admission, no warrant, and no claim: it is the object a witness
*spec* denotes, and the spec is content-hashed so a replay result can name the
exact graph it evaluated.

Two boundaries are enforced in this module.

* A spec is admitted only when it is structurally a finite simple graph.  A
  self loop, a vertex outside ``range(order)``, a repeated edge, an unknown
  field, a duplicate JSON key, or a non-integer endpoint is a typed refusal.
  A spec is never repaired.
* Connectivity is *reported*, never assumed.  Graph distance is undefined on a
  disconnected graph, so every distance-consuming function refuses
  ``graph_not_connected`` instead of substituting an infinity, a sentinel, or a
  float.

Arithmetic in this package is exact throughout: ``int`` and
``fractions.Fraction`` only.  No ``float`` value is constructed anywhere, and a
comparison that cannot be decided exactly is a refusal rather than a guess.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Mapping

from ..phase2.serialization import canonical_hash

SPEC_SCHEMA_VERSION = "adaivy.exact-graph-spec.v1"

# Bounds every breadth-first search and every distance table in this package.
# 448 (the shipped G(14,18) witness) is well inside it; the bound exists so a
# malformed or hostile spec cannot ask for an unbounded allocation.
MAX_GRAPH_ORDER = 4096

MAX_SPEC_BYTES = 4_194_304

_SPEC_FIELDS = frozenset({"graph_id", "order", "edges"})


class ExactGraphError(ValueError):
    """Base class for every refusal in :mod:`math_research.exact_graph`.

    Carries a stable string ``code``.  Tests and probes name codes, never
    message text.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


class GraphError(ExactGraphError):
    """A graph spec is malformed, or a graph cannot answer a distance query."""


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise GraphError("graph_spec_malformed", f"invalid_identifier:{field}")
    if value != value.strip() or any(ord(ch) < 0x20 for ch in value):
        raise GraphError("graph_spec_malformed", f"invalid_identifier:{field}")
    return value


def _order(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GraphError("graph_spec_malformed", "order_not_integer")
    if value < 1 or value > MAX_GRAPH_ORDER:
        raise GraphError("graph_spec_malformed", f"order_out_of_bounds:{value}")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class Graph:
    """A labelled finite simple graph on ``range(order)``.

    ``adjacency[v]`` is the neighbour set of ``v``.  Symmetry, irreflexivity,
    and the vertex range are invariants established at construction; no caller
    may build a :class:`Graph` that violates them without going through
    :func:`build_graph`, which refuses.
    """

    graph_id: str
    order: int
    adjacency: tuple[frozenset[int], ...]

    def edges(self) -> tuple[tuple[int, int], ...]:
        """Every edge as a sorted ``(u, v)`` pair, in lexicographic order."""

        return tuple(sorted(
            (u, v) for u in range(self.order) for v in self.adjacency[u] if u < v
        ))

    def size(self) -> int:
        return len(self.edges())

    def degree(self, vertex: int) -> int:
        return len(self.adjacency[self._checked(vertex)])

    def spec_hash(self) -> str:
        """Content hash of the *structure*, over the sorted edge list.

        Deliberately structural: the hash names what was evaluated, not what it
        was called.  Two specs with the same order and the same sorted edge
        list hash identically even under different ``graph_id`` values, so a
        witness cannot be renamed into a different hash.
        """

        return canonical_hash({
            "schema_version": SPEC_SCHEMA_VERSION,
            "order": self.order,
            "edges": [[u, v] for u, v in self.edges()],
        })

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": SPEC_SCHEMA_VERSION,
            "graph_id": self.graph_id,
            "order": self.order,
            "edges": [[u, v] for u, v in self.edges()],
            "spec_hash": self.spec_hash(),
        }

    def _checked(self, vertex: int) -> int:
        if not isinstance(vertex, int) or isinstance(vertex, bool):
            raise GraphError("graph_vertex_out_of_range", "vertex_not_integer")
        if vertex < 0 or vertex >= self.order:
            raise GraphError("graph_vertex_out_of_range", f"vertex:{vertex}")
        return vertex


def build_graph(graph_id: str, order: int, edges: Any) -> Graph:
    """Build a :class:`Graph` from an edge list, refusing anything that is not
    a finite simple graph.  Every constructor in this module routes through it.
    """

    graph_id = _identifier(graph_id, "graph_id")
    order = _order(order)
    neighbours: list[set[int]] = [set() for _ in range(order)]
    seen: set[tuple[int, int]] = set()
    for index, edge in enumerate(edges):
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            raise GraphError("graph_spec_malformed", f"edge_not_pair:{index}")
        u, v = edge
        for endpoint in (u, v):
            if not isinstance(endpoint, int) or isinstance(endpoint, bool):
                raise GraphError("graph_spec_malformed", f"endpoint_not_integer:{index}")
            if endpoint < 0 or endpoint >= order:
                raise GraphError("graph_vertex_out_of_range", f"edges[{index}]:{endpoint}")
        if u == v:
            raise GraphError("graph_self_loop", f"edges[{index}]:{u}")
        key = (u, v) if u < v else (v, u)
        if key in seen:
            raise GraphError("graph_spec_malformed", f"duplicate_edge:{key[0]}-{key[1]}")
        seen.add(key)
        neighbours[u].add(v)
        neighbours[v].add(u)
    return Graph(
        graph_id=graph_id,
        order=order,
        adjacency=tuple(frozenset(item) for item in neighbours),
    )


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise GraphError("graph_spec_malformed", f"duplicate_field:{key}")
        value[key] = item
    return value


def _reject_constant(item: str) -> Any:
    raise GraphError("graph_spec_malformed", f"non_finite_json:{item}")


def load_graph_spec(payload: bytes | str | Mapping[str, Any]) -> Graph:
    """Parse a witness graph spec: ``{graph_id, order, edges:[[u,v],...]}``.

    Fails closed on unknown fields, duplicate keys, malformed JSON, non-finite
    JSON constants, and every structural violation :func:`build_graph` refuses.
    The spec is not required to be connected; connectivity is a reported
    property, and its absence is what makes a distance query refuse later.
    """

    if isinstance(payload, bytes):
        if len(payload) > MAX_SPEC_BYTES:
            raise GraphError("graph_spec_malformed", "spec_too_large")
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise GraphError("graph_spec_malformed", "spec_not_utf8") from error
        return load_graph_spec(text)
    if isinstance(payload, str):
        try:
            value = json.loads(
                payload, object_pairs_hook=_strict_object, parse_constant=_reject_constant,
            )
        except json.JSONDecodeError as error:
            raise GraphError("graph_spec_malformed", "spec_not_json") from error
    else:
        try:
            value = json.loads(
                json.dumps(payload, allow_nan=False),
                object_pairs_hook=_strict_object, parse_constant=_reject_constant,
            )
        except (TypeError, ValueError) as error:
            if isinstance(error, GraphError):
                raise
            raise GraphError("graph_spec_malformed", "spec_not_json") from error
    if not isinstance(value, dict) or set(value) != set(_SPEC_FIELDS):
        raise GraphError("graph_spec_malformed", "field_set_mismatch")
    edges = value["edges"]
    if not isinstance(edges, list):
        raise GraphError("graph_spec_malformed", "edges_not_array")
    if isinstance(value["order"], float) or any(
        isinstance(item, float) for edge in edges if isinstance(edge, list) for item in edge
    ):
        raise GraphError("graph_spec_malformed", "float_in_spec")
    return build_graph(value["graph_id"], value["order"], edges)


def is_triangle_free(g: Graph) -> bool:
    """``True`` when no three vertices are mutually adjacent.  Exact, no sampling."""

    for u in range(g.order):
        for v in g.adjacency[u]:
            if v > u and g.adjacency[u] & g.adjacency[v]:
                return False
    return True


def bfs_distances(g: Graph, source: int) -> tuple[int, ...]:
    """Integer graph distances from ``source``.

    Refuses ``graph_not_connected`` rather than reporting an unreachable vertex
    as an infinity, a sentinel, or a float.
    """

    source = g._checked(source)
    distance = [-1] * g.order
    distance[source] = 0
    frontier = [source]
    reached = 1
    step = 0
    while frontier:
        step += 1
        nxt: list[int] = []
        for u in frontier:
            for v in g.adjacency[u]:
                if distance[v] < 0:
                    distance[v] = step
                    reached += 1
                    nxt.append(v)
        frontier = nxt
    if reached != g.order:
        raise GraphError("graph_not_connected", f"source:{source}")
    return tuple(distance)


def is_connected(g: Graph) -> bool:
    """``True`` when every vertex is reachable from vertex 0."""

    try:
        bfs_distances(g, 0)
    except GraphError as error:
        if error.code == "graph_not_connected":
            return False
        raise
    return True


def cycle(n: int) -> Graph:
    """The cycle ``C_n``, ``graph_id`` ``f"C{n}"``, vertices ``0..n-1`` in order."""

    if not isinstance(n, int) or isinstance(n, bool) or n < 3:
        raise GraphError("graph_spec_malformed", f"cycle_order_below_three:{n}")
    return build_graph(f"C{n}", n, [[i, (i + 1) % n] for i in range(n)])


def kneser(n: int, k: int) -> Graph:
    """The Kneser graph ``K(n,k)``: ``k``-subsets of ``range(n)``, adjacent when
    disjoint.  ``graph_id`` is ``f"K{n}-{k}"`` and vertices are the ``k``-subsets
    in lexicographic order, so the labelling is deterministic.

    Present for the Graffiti 197 coupling: the same reading of "range" that
    Graffiti 322 turns on also governs 197, and 197's candidates are Kneser
    graphs.  Constructing one here creates no claim about either conjecture.
    """

    for name, value in (("n", n), ("k", k)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise GraphError("graph_spec_malformed", f"kneser_parameter:{name}={value}")
    if k > n:
        raise GraphError("graph_spec_malformed", f"kneser_k_exceeds_n:{k}>{n}")
    vertices = tuple(combinations(range(n), k))
    if len(vertices) > MAX_GRAPH_ORDER:
        raise GraphError("graph_spec_malformed", f"kneser_order_out_of_bounds:{len(vertices)}")
    sets = [frozenset(item) for item in vertices]
    edges = [
        [i, j]
        for i in range(len(sets))
        for j in range(i + 1, len(sets))
        if not (sets[i] & sets[j])
    ]
    return build_graph(f"K{n}-{k}", len(vertices), edges)


@dataclass(frozen=True, slots=True, kw_only=True)
class GraffitiLayout:
    """Deterministic vertex layout of ``G(r,t)``.

    Index blocks, in order: ``r`` branch vertices ``b_i``; ``r(r-1)`` oriented
    internal vertices ``x_ij`` (``i != j``) in lexicographic ``(i, j)`` order;
    ``r*t`` leaves ``l_{i,a}`` in lexicographic ``(i, a)`` order.  The layout is
    part of the frozen construction: it is what makes an explicit basis witness
    reproducible byte-for-byte.
    """

    r: int
    t: int

    @property
    def order(self) -> int:
        return self.r * self.r + self.r * self.t

    def branch(self, i: int) -> int:
        return i

    def internal(self, i: int, j: int) -> int:
        if i == j:
            raise GraphError("graph_spec_malformed", f"internal_diagonal:{i}")
        offset = i * (self.r - 1) + (j if j < i else j - 1)
        return self.r + offset

    def leaf(self, i: int, a: int) -> int:
        return self.r + self.r * (self.r - 1) + i * self.t + a

    def branch_indices(self) -> tuple[int, ...]:
        return tuple(range(self.r))

    def internal_pairs(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (i, j) for i in range(self.r) for j in range(self.r) if i != j
        )

    def internal_indices(self) -> tuple[int, ...]:
        return tuple(self.internal(i, j) for i, j in self.internal_pairs())

    def leaf_indices(self) -> tuple[int, ...]:
        return tuple(
            self.leaf(i, a) for i in range(self.r) for a in range(self.t)
        )


def graffiti_family_layout(r: int, t: int) -> GraffitiLayout:
    for name, value in (("r", r), ("t", t)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise GraphError("graph_spec_malformed", f"graffiti_parameter:{name}")
    if r < 4:
        raise GraphError("graph_spec_malformed", f"graffiti_r_below_four:{r}")
    if t < 2:
        raise GraphError("graph_spec_malformed", f"graffiti_t_below_two:{t}")
    layout = GraffitiLayout(r=r, t=t)
    if layout.order > MAX_GRAPH_ORDER:
        raise GraphError("graph_spec_malformed", f"graffiti_order_out_of_bounds:{layout.order}")
    return layout


def graffiti_family(r: int, t: int) -> Graph:
    """``G(r,t)`` from the shipped Graffiti 322 report.

    Replace every edge of ``K_r`` with a path of length three -- branch vertex
    ``b_i``, oriented internal vertex ``x_ij`` for ``i != j``, edges
    ``b_i x_ij`` and ``x_ij x_ji`` -- and attach ``t`` leaves ``l_{i,a}`` to
    every branch vertex.  Hence ``|V| = r^2 + r t`` and
    ``|E| = 3r(r-1)/2 + r t``.  Both identities are *checked* by the tests
    against the constructed object; neither is asserted here.

    The construction is stated in the source for ``r >= 4`` and ``t >= 2``;
    outside that range this refuses rather than extrapolating the source's
    domain.
    """

    layout = graffiti_family_layout(r, t)
    edges: list[list[int]] = []
    for i in range(r):
        for j in range(r):
            if i == j:
                continue
            edges.append([layout.branch(i), layout.internal(i, j)])
            if i < j:
                edges.append([layout.internal(i, j), layout.internal(j, i)])
        for a in range(t):
            edges.append([layout.branch(i), layout.leaf(i, a)])
    return build_graph(f"G({r},{t})", layout.order, edges)
