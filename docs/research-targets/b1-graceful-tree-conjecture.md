# B1. Graceful Tree Conjecture — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B1 (tier B)
**Declared domain:** graph-labelling
**Intake file:** docs/research-targets/intake/b1-graceful-tree-conjecture-v1.json
**Frozen in one line:** Every finite tree with `m` edges admits a bijection from
its vertices onto `{0,...,m}` whose induced absolute edge differences are
exactly `{1,...,m}`.

This is a scoped intake package. It does not approve a formalization, establish
that the frozen target is open, authorize acquisition of any source, assess
novelty or significance, create mathematical warrant, or activate a capability.
Novelty, significance, and source applicability are `not_assessed`, and every
external statement recorded below is an untrusted candidate rather than a fact.
Nothing here licenses a claim of contribution.

## 1. Frozen target

Fix the following, all for finite simple undirected graphs.

A **tree** is a finite simple connected acyclic undirected graph with at least
one vertex. For a tree `T` write `V(T)` for its vertex set, `E(T)` for its edge
set, `m = |E(T)|`, and note `|V(T)| = m + 1`. For `u, v in V(T)`, `d_T(u,v)` is
the number of edges on the unique path in `T` from `u` to `v`, so
`d_T(v,v) = 0`.

A **graceful labelling** of a tree `T` with `m` edges is a bijection

`phi : V(T) -> {0, 1, ..., m}`

such that the induced edge labelling `psi(uv) = |phi(u) - phi(v)|` satisfies

`{ psi(e) : e in E(T) } = {1, 2, ..., m}`

as sets. Because `|E(T)| = m`, this is equivalent to requiring `psi` to be a
bijection from `E(T)` onto `{1, ..., m}`. `T` is **graceful** if at least one
graceful labelling of `T` exists.

**Frozen target claim.**

`for every integer m >= 0 and every tree T with |E(T)| = m,`
`there exists a bijection phi : V(T) -> {0, ..., m} with`
`{ |phi(u) - phi(v)| : uv in E(T) } = {1, ..., m}.`

This is the Graceful Tree Conjecture itself, quantified over every finite tree.
No subclass, parameter, diameter bound, matching hypothesis, or vertex-count
bound restricts it. It is one claim, not a disjunction of possible wins, and it
is not a frontier-extension claim about any particular vertex count.

### Why the target is not narrowed

The planning dossier's B1 entry lists useful progress as a new infinite family,
a reduction rule preserving gracefulness, or a certified extension of the
exhaustive frontier, and says that merely checking the next vertex count is a
capability result rather than the preferred research contribution. Those are
statements about what a *slice* should aim at, not permission to shrink the
target. The cross-cutting acceptance rules require one exact target with a
bounded first slice; they do not require the target to be small. Accordingly the
target is the full conjecture and the narrowing lives entirely in section 7,
where a bounded first slice attempts one exactly defined tree class as a
**waypoint** on the way to the conjecture.

The consequence is recorded here rather than left implicit: proving the waypoint
class graceful would be progress and would not be the target. Section 10's
success criteria say so in those words, and the realistic outcome of a bounded
slice against a conjecture of this size is the explicit unresolved outcome with
the smallest remaining obligation named.

A second consequence is that the untrusted status claims in section 6 now bear
on the conjecture directly rather than on a subclass. That makes the ADR-0055
pre-research novelty re-check more load-bearing, not less: the claim that the
Graceful Tree Conjecture is open, and the claim that exhaustive verification
reaches 35 vertices, are both claims about the frozen target itself.

## 2. Definitions and conventions

The first six rows are load-bearing for the target. The remaining rows are
load-bearing for the section 7 slice, and are frozen to the same standard
because a slice whose waypoint class is ambiguous cannot report what it covered.

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| tree | finite simple connected acyclic undirected graph, at least one vertex | infinite trees; forests; rooted, plane, or edge-weighted trees; multigraphs |
| `m` | the number of edges, so `|V| = m + 1` | `m` as the number of vertices, which shifts the label range by one |
| graceful labelling | bijection `phi : V -> {0,...,m}` whose induced labels `|phi(u) - phi(v)|` form exactly `{1,...,m}` | vertex labels drawn from `{1,...,m+1}`; edge labels merely injective without covering `{1,...,m}`; an alpha-labelling, that is a graceful labelling with a boundary value separating the two sides of the bipartition, which is strictly stronger; near-graceful or `k`-graceful variants that shift the edge-label range |
| induced edge label | the absolute difference `|phi(u) - phi(v)|` of the two endpoint labels | signed difference; difference modulo `m + 1`; a label assigned independently of `phi` |
| graceful (of a tree) | at least one graceful labelling exists | a distinguished or canonical labelling exists; all labellings are graceful; a labelling exists with extra properties |
| "every finite tree with `m` edges" | universally quantified over all `m >= 0` and all trees with exactly `m` edges, with no further hypothesis | any subclass, including the section 7 waypoint class; a single `m`; only `m >= 1`; only trees with an even or odd number of vertices; only trees up to some vertex count |
| waypoint class `X` (section 7 only) | there exists a path subgraph `P` of `T`, possibly a single vertex with no edges, such that every vertex of `T` is within `d_T`-distance 2 of `V(P)`; a slice device with no role in the target claim | a hypothesis of the target; "deleting every leaf of `T` yields a caterpillar", which is the same class for large trees but is degenerate for `K_1` and `K_2`, where the leaf-deleted graph is empty and no convention is fixed; "diameter at most 5", a different class; "`T` has a longest path within distance 2 of every vertex", a formally stronger requirement whose equivalence to the frozen one is unproved here and is therefore not assumed |
| spine `P` | a path subgraph with `k >= 1` vertices; `k = 1` and `k = 2` are allowed | a spine required to have at least one edge; a spine required to be a longest or diametral path; a spine required to be unique |
| distance | number of edges on the unique `T`-path between two vertices; `d_T(v,v) = 0` | distance measured inside `P` rather than inside `T`; weighted distance; distance to the nearest leaf |
| caterpillar | the `d_T(v,w) <= 1` case of the waypoint class definition | any tree of small diameter; a tree whose leaf-deletion is a path, which agrees for large trees and is degenerate on `K_1` and `K_2` |
| matching hypothesis | none is imposed anywhere, in the target or in the waypoint class | the reported subcase of members of `X` admitting a perfect matching, which section 6 records as a possibly settled proper part of `X` |
| exhaustive frontier | a statement about a bounded set of trees with a stated canonical enumeration; never a statement about all trees and never about all of `X` | "verified through 35 vertices" read as a claim about the conjecture, or read as 35 edges rather than 35 vertices |
| canonical form of a tree | the centroid-rooted bracket encoding defined in section 7 | any adjacency-list ordering; a degree sequence; a level sequence whose tie-breaking convention is unstated |

## 3. Formalization and quantifiers

Typed informal statement, as it appears in the intake file:

`forall m : N, forall T : Tree, edge_count(T) = m ->`
`exists phi : V(T) -> {0..m}, Bijective(phi) and`
`{ abs(phi(u) - phi(v)) : (u,v) in E(T) } = {1..m}`

Quantifiers, in order and with their ranges:

- `forall m` an integer with `m >= 0`;
- `forall T` a finite simple tree with exactly `m` edges and `m + 1` vertices,
  with no further hypothesis;
- `exists phi` a bijection from `V(T)` onto `{0,...,m}`;
- `forall e in E(T)` the induced label lies in `{1,...,m}`, and every element of
  `{1,...,m}` is induced by some edge.

There is no hypothesis to discharge before the labelling is sought: the
antecedent is only that `T` is a tree with `m` edges. In particular the waypoint
class of section 7 contributes no quantifier here, and no existential over a
spine appears in the target.

There is no asymptotic in the statement, so no epsilon form is needed.
Degenerate cases are inside the claim rather than excluded: `m = 0` is the
one-vertex tree, whose unique labelling `phi(v) = 0` induces the empty
edge-label set, which equals `{1,...,0} = {}`; `m = 1` is the single edge with
`phi` taking the values `0` and `1`.

Every arithmetic object in the statement is an integer. The only operations on
the trust path are integer subtraction, absolute value, integer comparison, and
set equality on finite sets of integers.

## 4. Semantic alignment to the source statement

The source statement, as rendered in the planning dossier, is: every tree with
`m` edges admits a bijection from its vertices to `{0,...,m}` such that the
absolute differences across its edges are exactly `{1,...,m}`.

**Quantifier mapping.** `m` maps to a non-negative integer edge count,
unchanged. `forall T a tree` maps to
`forall T a finite simple tree with exactly m edges`, unchanged and unnarrowed.
The source's `exists` labelling maps to `exists phi`, unchanged. No quantifier
is added and none is removed.

**Definition mapping.** "bijection from its vertices to `{0,...,m}`" maps to
`phi` bijective onto `{0,...,m}`. "absolute differences across its edges are
exactly `{1,...,m}`" maps to set equality of the induced edge labels with
`{1,...,m}`, with `psi(uv) = |phi(u) - phi(v)|`. "tree" maps to finite simple
connected acyclic graph with at least one vertex. The waypoint class `X` has no
counterpart in the source statement and no counterpart in the target; it is a
section 7 slice device only.

**Assumption delta.** The frozen target adds no hypothesis and removes none. It
pins the conventions listed in section 2 — what a tree is, that `m` counts
edges, that the label range is `{0,...,m}`, that the induced label is an
absolute difference, and that gracefulness is existential in the labelling. No
matching, diameter, parity, vertex-count, or subclass hypothesis is imposed
anywhere in the target.

**Edge-case delta.** `m = 0` and `m = 1` are inside the frozen claim rather than
excluded, and section 3 states what the claim says there. The degenerate-case
discipline about the waypoint class — that its leaf-deletion reading is
ambiguous on the one-vertex and one-edge trees, which is why the distance form
is used — bears on section 7's coverage reporting and not on the target.

**Strength relation:** `unresolved`. The frozen target is intended to be the
Graceful Tree Conjecture as the planning dossier renders it, and no narrowing
was applied. Even so the mapping cannot be settled here: the planning dossier is
a rendering, not a primary source, and `equivalent` is unavailable because no
primary source has been acquired or quoted. `weaker` would be wrong now that
nothing is narrowed, and `stronger` would assert more than is known.
`unresolved` is the only honest value until the section 5 rows are acquired.

## 5. Provenance and acquisition plan

Every row is `pending_acquisition`, applicability `not_assessed`. Acquisition is
human-planned, exact-URL, and separately authorized under ADR-0050; nothing here
authorizes a fetch. Rows marked `locator_unverified` carry a bibliographic
identification made offline from recollection: the operator must confirm the
identifier before acquisition, and a wrong identifier must be recorded as such
rather than silently corrected. Because the target is now the conjecture itself,
these rows bear on the status of the frozen target directly.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| A. Rosa, "On certain valuations of the vertices of a graph", Theory of Graphs (International Symposium, Rome 1966), Gordon and Breach, 1967, pages 349-355 | print volume, the pages defining beta-valuations and the caterpillar result; `locator_unverified` for the exact page range | fixes the original graceful/beta-valuation convention against the section 2 rejected readings, which are conventions of the target itself; settles claim 6.4 | pending_acquisition |
| J. A. Gallian, "A Dynamic Survey of Graph Labeling", Electronic Journal of Combinatorics, Dynamic Survey DS6, latest edition | `https://www.combinatorics.org/ojs/index.php/eljc/article/view/DS6`, the subsections on trees and on lobsters | settles claims 6.1, 6.2, 6.3, 6.5 and 6.6 in one document: the current status of the conjecture, the status of the waypoint class, the perfect-matching subcase, the exhaustive frontier, and the attributions | pending_acquisition |
| J.-C. Bermond, "Graceful graphs, radio antennae and French windmills", in Graph Theory and Combinatorics (Proceedings, Open University 1978), Pitman, 1979, pages 18-37 | print volume, the page stating the lobster conjecture; `locator_unverified` | settles claim 6.5, in particular whether the conjecture about the waypoint class is stated for exactly the class of section 7 or for a variant with a different degenerate-case convention | pending_acquisition |
| The computational study behind the reported exhaustive frontier | unidentified; a candidate identification is a computational study of the Graceful Tree Conjecture reporting verification of all trees up to 35 vertices, whose author and identifier this dossier cannot supply offline; `locator_unverified` and `locator_unknown` | settles claim 6.1, including whether the figure counts vertices or edges, whether all trees or a subclass were covered, and whether certificates were retained | pending_acquisition |
| The reported theorem on members of the waypoint class admitting a perfect matching | unidentified; the survey row above is the intended route to the exact reference; `locator_unknown` | settles claim 6.6, which determines how much of the waypoint class is already covered and therefore where slice effort must not be spent | pending_acquisition |
| Wright, Richmond, Odlyzko, and McKay, "Constant time generation of free trees", SIAM Journal on Computing, 1986 | print or publisher record; the exact canonical level-sequence convention and the generation order; `locator_unverified` | pins the external generator convention named in section 7 so that the in-repo canonical form can be cross-checked against a documented convention rather than against recollection | pending_acquisition |

No row is required for the slice to run: the slice's coverage argument is
self-contained, using the in-repo canonical form and an independently computed
tree count. The rows are required before any status, novelty, or contribution
statement is made, and before the conjecture or the waypoint class may be
described as unsettled.

## 6. Prior-status claims to re-check

Each claim below is untrusted. None is used as a premise by the slice. The
ADR-0055 pre-research novelty re-check must cover every one of them, with
evidence hashes, before research execution starts, and each found source must
carry a human-supplied same/equivalent/stronger/weaker/overlapping relationship
to the frozen target. Claims 6.1 and 6.2 are claims about the frozen target
itself, so the re-check is load-bearing for the target and not merely for a
subclass.

**6.1 Exhaustive verification through 35 vertices as of July 2026.** From the
operator notes by way of the planning dossier. Untrusted, and additionally
ambiguous: it is not recorded whether 35 counts vertices or edges, whether all
trees or a subclass were covered, whether labellings were retained as
certificates, or whether the computation has been independently replayed. The
target is a universal statement over all trees, so this claim bounds only what a
bounded slice can add and settles nothing about the target.

**6.2 The Graceful Tree Conjecture is open.** Inherited from the planning
dossier's inclusion of B1 as a candidate. Untrusted, and now directly about the
frozen target: if the conjecture has been settled, this dossier is superseded
rather than repaired.

**6.3 The conjecture is the statement rendered in the planning dossier.** A
fidelity claim, untrusted. The section 2 rejected readings — the label range,
the absolute-difference convention, and whether `m` counts edges or vertices —
are exactly the places where a rendering can drift from the original.

**6.4 Caterpillars are graceful, attributed to Rosa in 1967.** The mathematical
statement is treated as a standard textbook fact and recorded as a `lemma` in
the intake file. The attribution and date are untrusted and are not used
anywhere.

**6.5 The waypoint class of section 7 is not settled, and the corresponding
conjecture is attributed to Bermond in 1979.** Untrusted. This claim does not
affect the target, but it decides whether the section 7 waypoint is worth
attempting: a waypoint that is already a theorem is not a waypoint.

**6.6 Members of the waypoint class that admit a perfect matching are
graceful.** Recollected as a published theorem; untrusted, unattributed here,
and important, because if true it covers a large proper part of the waypoint
class. Rediscovering that part is not progress, and the risk register records it
as such.

## 7. Bounded first slice

The slice is offline, deterministic, exact-integer, and human-authored. It calls
no model on the trust path, opens no network connection, and executes no
model-generated program.

The slice does not attempt the target. It attempts one **waypoint**: an exactly
defined tree class, strictly larger than the classical caterpillars and strictly
smaller than the class of all trees. A theorem for that class would be progress
toward the conjecture and would not be the conjecture.

**The waypoint class.** A tree `T` belongs to `X` if and only if there exists a
subgraph `P` of `T` that is a path — that is, `P` is isomorphic to `P_k` for
some `k >= 1`, where `P_1` is a single vertex and no edges — such that

`for every v in V(T) there is w in V(P) with d_T(v,w) <= 2`.

`P` is called a spine of `T`. A tree may have many spines; membership requires
only that at least one exists. The class is commonly called the class of
lobsters. That name is used nowhere in the target claim and nowhere in the
membership test, because the name carries source-dependent degenerate cases and
the distance definition above does not: the leaf-deletion reading is undefined
on the one-vertex and one-edge trees, whereas the distance reading admits both
by taking `P` to be a single vertex.

`X` was chosen against three conditions.

1. Membership is decidable by exact integer arithmetic on an adjacency list,
   with no parameter, no asymptotic, and no appeal to a source convention.
2. `X` strictly contains the caterpillars, which are the same definition with
   `d_T(v,w) <= 1`, and caterpillar gracefulness is a standard classical fact,
   so the waypoint is not already a classical theorem. The containment is strict
   with a concrete exactly checkable witness: the tree on seven vertices
   obtained from `K_{1,3}` by subdividing each edge once — a spider with three
   legs of length two — lies in `X`, taking the spine through two of the legs
   and the centre, but deleting its leaves leaves `K_{1,3}`, which is not a
   path, so it is not a caterpillar.
3. `X` is strictly contained in the class of all trees, witnessed by the tree
   obtained from `K_{1,3}` by subdividing each edge twice, which has a vertex at
   distance 3 from every path. The waypoint is therefore genuinely short of the
   target, and section 10 requires it to be reported that way.

Whether `X` is itself unsettled is claim 6.5 and is untrusted. If acquisition
shows `X` is a theorem, the waypoint is replaced and the target is untouched.

**Inputs.** Two integers fixing the envelope: `N1`, the vertex bound for the
all-trees stage, frozen at `N1 = 18`; and `N2`, the vertex bound for the
waypoint-class stage, frozen at `N2 = 22`. Two resource caps, stated below. No
fixture, table, or published labelling is an input.

**Canonical form.** For a tree `T`, define `canon(T)` as follows. Compute the
centroid by repeatedly deleting all leaves; the process terminates in either a
single vertex or a single edge. In the single-vertex case, root `T` there; in
the single-edge case, split `T` into the two components of `T` minus that edge
and root each at its endpoint of the edge. Encode a rooted tree recursively: a
leaf encodes as `()`, and an internal vertex encodes as `(` followed by the
concatenation of its children's encodings sorted in ascending lexicographic
order, followed by `)`. Set `canon(T)` to that string in the single-vertex case,
and to `[` plus the two halves' encodings in ascending lexicographic order plus
`]` in the single-edge case. Two trees are isomorphic if and only if their
canonical forms are equal. Strings are compared as byte sequences; no hashing is
used for the comparison itself.

**Generator convention.** Two independent generators are used.

- Generator G1 enumerates all free trees on `n` vertices by the constant-time
  free-tree level-sequence method of Wright, Richmond, Odlyzko, and McKay, whose
  exact canonical level-sequence convention is pinned by the acquisition row in
  section 5. Until that row is acquired the implementation is treated as an
  in-repo enumerator whose output is validated only by the checks below, and it
  is not described as the published algorithm.
- Generator G2 enumerates the members of `X` directly from the class definition:
  choose a spine length `k >= 1`, then for each spine vertex a multiset of legs,
  each leg being a rooted tree of height at most 2 attached to that spine
  vertex, subject to the total vertex count. Duplicates arising from different
  parameter choices are removed by `canon`.

**Stage 1, all trees to `N1`.** Enumerate all free trees with `n <= N1` vertices
with G1. This stage is over all trees, not over `X`, because the target is over
all trees. The envelope size is `sum_{n <= N1} t(n)`, where `t(n)` is the number
of unlabelled trees on `n` vertices; the slice recomputes each `t(n)` from the
standard exact rooted-tree and free-tree integer recurrence and this dossier
does not assert the values. An untrusted planning estimate puts the total at
order `10^5`. Checks, all exact: the number of distinct canonical forms at each
`n` must equal the independently recomputed `t(n)`; the sorted list of canonical
forms is content-hashed and retained; membership in `X` is decided two ways,
once by brute force over all `O(n^2)` vertex pairs as candidate spine endpoints
and once by the iterated-leaf-deletion characterization, and any disagreement
halts the run and is retained as a fixture. Nothing is sampled at this stage.

**Stage 2, the waypoint class to `N2`.** Enumerate `X` for `n <= N2` with G2 and
deduplicate by `canon`. For every `n <= N1` the resulting per-`n` count must
equal the Stage 1 filtered count; a mismatch halts the run. For `N1 < n <= N2`
the counts are new outputs with no cross-check available from Stage 1, so their
coverage rests on the class-parameterization argument alone, and that argument
is recorded as an open proof obligation rather than as a verified fact.

**Stage 3, labelling search.** For each retained tree, search for a graceful
labelling by depth-first assignment of edge labels in descending order from `m`,
maintaining the set of used vertex labels and the set of used edge labels as
exact integer sets. Every pruning rule is stated declaratively and carries its
own proof obligation; for all trees with `m <= 12` the pruned search is
cross-checked against unpruned enumeration of all `(m+1)!` label assignments,
and any divergence halts the run. A found labelling is stored as a certificate.
The absence of a labelling is not stored as a result at this stage; it triggers
the separate protocol in section 8.

**Stage 4, structure.** From the Stage 3 certificates, fit candidate uniform
labelling schemes: formulas giving `phi` as a function of the spine length and
the leg-count parameters of a member of `X`. A fitted scheme is a candidate
only. It is recorded with the exact finite set of instances on which it was
checked and with an explicit open proof obligation that it holds for all
parameter values. No fitted scheme is reported as a lemma, and a scheme proved
for all parameters would establish the waypoint rather than the target.

**Resource caps.** The run halts when the total number of retained trees exceeds
`5 * 10^6`, or when the cumulative Stage 3 search-node count exceeds `10^11`, or
under any stopping rule in section 10. The reached `n` is therefore a measured
output of the run and not a promise made here.

**Symmetry and canonicalization.** Isomorphic trees are identified by `canon`,
so the enumeration is over isomorphism classes rather than labelled trees. There
is no further symmetry quotient on the labelling side: complementing a labelling
by `phi -> m - phi` maps graceful labellings to graceful labellings, and the
slice uses that only to halve the Stage 3 search by fixing an orientation, never
to justify skipping a tree.

**Boundary of the claim the slice can support.** On success the slice supports
exactly this: every tree, and every member of `X`, inside the measured vertex
bound is graceful, each witnessed by a stored labelling that an independent
verifier replays, and the enumeration at each `n` in Stage 1 is complete
relative to the recomputed tree count. It does not support the frozen target,
which quantifies over all `m`. A proved theorem for `X` would not support the
frozen target either; it would be progress with the residual — trees having a
vertex at distance 3 or more from every path — left open. A bounded exhaustion
is bounded evidence and is never promoted; the stopping rules in section 10
forbid the promotion explicitly. Conversely, a single tree proved non-graceful
would refute the frozen target outright, and that direction is not bounded — one
certificate suffices — but section 8 explains why this slice structurally cannot
produce one.

## 8. Certificate and verifier contract

Result shapes, each with its certificate format and its independent verifier.

**S1, graceful labelling exhibited.** Certificate: the canonical form string of
`T`; an explicit adjacency list on vertices `0..m`; the integer vector `phi` of
length `m + 1`; and the induced edge-label vector. Verifier: rebuild the tree
from the adjacency list, check acyclicity and connectivity by an exact
union-find over `m` edges and `m + 1` vertices, recompute `canon` and compare
byte-for-byte with the certificate, check `phi` is a bijection onto `{0,...,m}`
by sorting and comparing to the exact integer range, recompute
`|phi(u) - phi(v)|` for every edge with exact integer subtraction, and check
that the multiset of induced labels equals `{1,...,m}` exactly. Every comparison
is integer equality. The verifier shares no code with the search.

**S2, waypoint class membership.** Certificate: the adjacency list plus a
witnessing spine given as an explicit vertex sequence, plus, for every vertex,
the spine vertex achieving distance at most 2 and the explicit path realizing
it. Verifier: recheck that the sequence is a path in `T` and that each declared
path has length at most 2 and connects the declared pair. Membership is thus
positively certified; a negative membership verdict is certified instead by
exhausting all `O(n^2)` endpoint pairs, which is small enough to replay in full.
This shape reports coverage of the section 7 waypoint and says nothing about the
target.

**S3, bounded exhaustive coverage.** Certificate: the envelope parameters; the
per-`n` counts from both generators; the independently recomputed `t(n)` values
with the recurrence used; the sorted deduplicated list of canonical forms and
its content hash; and the list of S1 certificates keyed by canonical form.
Verifier: recompute `t(n)` from the recurrence, recompute the content hash of
the sorted list, check that every listed canonical form has an S1 certificate,
and check that the count of forms matches. Coverage is thereby checked
independently of the generator that produced it.

**S4, a tree that is not graceful.** This is the refutation shape and its bar is
the highest, because one instance refutes the frozen target. Certificate: the
tree; a fully replayable exhaustion record naming every pruning rule used, each
with its stated soundness lemma; and a second, methodologically independent
exhaustion of the same tree. Two admissible second methods are unpruned
enumeration of all `(m+1)!` labellings, which is only feasible for small `m`,
and a propositional encoding of gracefulness whose unsatisfiability is
accompanied by a proof log that a checker replays. The second route needs a new
ADR (section 12). Until such a route exists, S4 cannot be produced by this
slice, and a search that finds no labelling for a tree is recorded as an open
item, not as a refutation of the conjecture.

**S5, candidate labelling scheme.** Certificate: the scheme as an explicit
formula, the exact finite instance set on which it was checked, the S1
certificate for each such instance, and the open proof obligation that it holds
for all parameters. Explicitly not a theorem, and even when discharged it is a
waypoint result rather than the target.

**Refused as a certificate, in every shape.** Floating-point output of any kind.
A model's verdict, explanation, or claim that a labelling exists or that a
scheme generalizes. A published table or third-party program's output that has
not been replayed inside the slice. Failure of a search, including failure of an
exhaustive-looking search whose pruning rules are not individually justified. A
count that matches an expected value taken from recollection rather than
recomputed from a stated recurrence.

## 9. Useful negative outcomes

Against a conjecture of this size the unresolved outcome is the expected one, so
what is retained when nothing is proved is the actual deliverable.

- The exclusion set: the content-hashed sorted list of canonical forms of every
  tree inside the measured envelope, and of every member of the waypoint class,
  each with its S1 certificate. Any future run may skip these without
  re-searching, and any future frontier claim must be consistent with them.
- The exact per-`n` counts of trees and of the waypoint class, from both
  generators, together with the recomputed `t(n)` values. These are new exact
  combinatorial data independent of the labelling question.
- Every fitted labelling scheme that failed, paired with the exact smallest
  instance in the envelope that broke it. A refuted scheme is a permanent
  narrowing of the search space for schemes and is more useful than a scheme
  that merely has not failed yet.
- Every candidate pruning rule that was rejected by the `m <= 12` cross-check,
  with the exact tree and labelling that exposed it.
- Any disagreement between the two membership tests or the two generators, kept
  as an acceptance fixture, because a coverage bug that is found once must be
  impossible thereafter.
- The measured cost profile: search nodes and wall time per tree as a function
  of `m`. Under ADR-0029 a specialist or a larger envelope requires a recorded
  prediction and a measured retention gain, and this profile is the only honest
  input to such a prediction.
- The reduction question left open: whether any operation taking a tree to a
  smaller tree preserves gracefulness. A negative answer for a specific
  operation is retained as a refuted route, and a positive one proved in general
  would be progress on the target rather than on the waypoint alone.
- The named residual if the waypoint is proved: the trees having a vertex at
  distance 3 or more from every path, which is exactly what would remain of the
  conjecture.

## 10. Evaluation protocol

Mirrors the intake file exactly.

Phase: `exploratory`. Version: `1`.

Metrics:

- `trees_enumerated`
- `waypoint_class_members_enumerated`
- `graceful_labellings_certified`
- `independent_verifier_replays_passed`
- `canonical_form_collisions_detected`
- `generator_disagreements_recorded`
- `pruning_rules_refuted`
- `candidate_schemes_refuted`
- `proof_obligations_opened`
- `proof_obligations_closed`
- `model_cost_usd`

Success criteria:

- `a proof that every finite tree is graceful, with every lemma discharged symbolically rather than by table`
- `an exact non-graceful finite tree, certified under shape S4 including its independent second exhaustion, which refutes the conjecture`
- `a proof that every tree in the section 7 waypoint class is graceful, recorded as progress toward the conjecture and explicitly not as the target, with the residual class named`
- `a proved reduction rule that maps a finite tree to a strictly smaller tree and preserves gracefulness`
- `an explicit unresolved outcome that names the smallest remaining obligation, which is the realistic outcome for a bounded slice against a conjecture of this size, together with the retained exclusion set and every refuted route`

Stopping rules:

- `stop on an exact certificate of either direction and open no further search`
- `stop when fresh model spend reaches USD 20`
- `stop when two consecutive review points close no proof obligation and refute no route`
- `stop when retained trees exceed 5 * 10^6 or cumulative search nodes exceed 10^11`
- `emit no refutation without the independent second exhaustion of shape S4; that route needs a new ADR, so this slice structurally cannot refute the conjecture`
- `never promote a bounded exhaustion to the conjecture; a frontier extension is a capability result, and a waypoint class theorem is progress with a named residual and never the target`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The conjecture is already settled | Claim 6.2 is untrusted and is now a claim about the frozen target itself | The ADR-0055 re-check must cover 6.2 with the survey row in section 5 acquired first; a settled conjecture supersedes this dossier rather than re-scoping it |
| The waypoint is already a theorem | Claim 6.5 is untrusted, and a waypoint that is a theorem is not a waypoint | The re-check must cover 6.5; the target is unaffected either way, and section 7 states that the waypoint is replaced rather than the target narrowed |
| A large part of the waypoint is settled | Claim 6.6 reports the perfect-matching subcase as done. Effort spent there produces certificates that are correct and worthless | The re-check must name the subcase explicitly; if confirmed, Stage 4 must report which fitted schemes only cover the already-settled part |
| Waypoint progress reported as the target | The slice can only ever reach the waypoint, and a class theorem reads like a result on the conjecture | Section 10 requires the waypoint outcome to be recorded as progress with the residual named; section 7's boundary paragraph states what a class theorem leaves open |
| Frontier extension mistaken for research | The planning dossier warns about exactly this, and Stages 1 to 3 look like progress while producing a capability result | The target claim is the conjecture; the stopping rules forbid promotion; the metric names separate certificates from obligations closed |
| Unsound pruning creates a false refutation | One unjustified pruning rule turns an incomplete search into an apparent refutation of the conjecture, the most damaging possible error, and now the target is exactly what would appear refuted | S4 requires a second independent exhaustion, which the slice cannot currently produce, so the slice structurally cannot emit a refutation; the `m <= 12` unpruned cross-check runs on every tree |
| Canonical-form bug creates false coverage | A collision silently drops trees and every downstream coverage statement becomes false | Two independent generators, per-`n` count cross-check against a recomputed recurrence, content-hashed sorted list, and a halt on any disagreement |
| Convention drift in the target | Claim 6.3: the label range, the absolute-difference convention, and whether `m` counts edges or vertices are places where a rendering can drift from the original statement | Section 2 freezes all of them with rejected readings; the Rosa row in section 5 exists to settle them; the alignment relation stays `unresolved` until it is acquired |
| Definition drift on the waypoint class | Acquired sources may define the class with different degenerate cases, so their status statements may not transfer | Section 2 and section 7 freeze the definition and list the rejected readings; a source's status is transferred only after its definition is mapped row by row |
| Recollected numbers entering the trust path | Tree counts, page ranges, and attributions in this dossier come from recollection | Counts are recomputed by the slice and never quoted as inputs; every locator is flagged `locator_unverified`; every status claim is in section 6 as untrusted |
| Model-generated enumerator executed | The enumerators are the coverage argument; under ADR-0057 production execution of generated code is disabled until its sandbox gate passes | The enumerators, the canonical form, and both verifiers are human-authored repo code; no model-generated program runs on the trust path |
| Search cost blows the envelope silently | Stage 3 is superexponential in the worst case and an unbounded run would consume the budget with nothing retained | Explicit node and tree caps, the spend cap, and the stagnation rule; the reached bound is a measured output |

## 12. Capability check

**Covered by existing AdaIvy capabilities.** Declarative problem intake and its
canonical hashing, which produce the dossier this file accompanies. Exact
integer arithmetic in the standard library, which is all the slice needs, as
repository-authored code under `src/` exercised by the offline suite — ad-hoc
exact arithmetic written and run by the driving agent in a scratch workspace is
NOT this capability, but an unmet AdaIvy capability and an external-origin
contribution under ADR-0057 section 5, imported with an `external_codex` or
`human` root and never relabelled as AdaIvy work.
Deterministic serialization, content hashing, and the append-only record path
used to retain certificates and failures. The bounded offline harness under
`make check`, which runs with no network, no model provider, and no container
runtime. The ADR-0047 bounded central-lead runtime, if the structural stage is
driven as composed one-round Phase 2 runs with a size-bounded proposer-only
ledger and a model-free replay. The ADR-0036 publication projection, if any
result is rendered, with claims demoted to `Conjecture` unless a computed
environment says otherwise. The ADR-0055 pre-research novelty re-check, which is
mandatory before execution and which is load-bearing for the target itself.

**Would require a new ADR.**

- A propositional encoding with a replayed unsatisfiability proof log, needed
  for result shape S4. There is no SAT capability in the repo and no
  digest-pinned sandbox for a solver or proof checker. Until such an ADR exists
  the slice cannot refute the conjecture, and this dossier does not assume it
  will.
- Acquisition of any row in section 5. Each is a separate human-planned
  exact-URL authorization under ADR-0050, and the print volumes are outside the
  activated public unauthenticated scope entirely.
- Execution of any model-generated enumerator, canonical-form routine, or
  verifier. ADR-0057 keeps production generated-code execution disabled pending
  its own sandbox gate.
- A kernel-checked theorem, whether for the conjecture or for the waypoint
  class. Phase 3B checks a frozen theorem supplied to it; there is no Lean
  formalization of graceful labelling in the repo, and producing one is a
  separate scope decision rather than a capability the slice may assume.
- Any parallel, specialist, evolutionary, or higher-tier search over the
  enumeration. ADR-0029 requires a recorded prediction and measured retention
  gain first, and this slice measures the cost profile precisely so that such a
  request could later be made honestly.

## 13. Open questions before intake

1. Is the section 7 waypoint the intended one? A smaller waypoint with a cheaper
   bounded slice — for example the members of `X` with spine length at most a
   fixed bound — would produce a weaker result sooner. The target is unaffected
   by the choice, so this is a slice decision rather than a re-freeze.
2. Should the reported perfect-matching subcase, once claim 6.6 is checked, be
   excluded from the waypoint by hypothesis so that slice effort goes only to
   the residual? That changes section 7 and not the target claim.
3. Does the operator accept `N1 = 18` and `N2 = 22` as the frozen envelope,
   given that claim 6.1 reports an existing frontier at 35 vertices and the
   slice's bounded output is therefore expected to be strictly inside
   already-covered ground?
4. Is a SAT-plus-proof-log ADR worth requesting now, given that without it the
   slice structurally cannot refute the conjecture, and that refutation is one
   of only two ways the target resolves?
5. The exhaustive-frontier source in section 5 is unidentified. Can the operator
   supply the exact locator from the original notes, so that claim 6.1 is
   checkable rather than merely flagged?
