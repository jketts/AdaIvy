# B1. Graceful Tree Conjecture — scoped research dossier

**Compiled:** 21 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B1 (tier B)
**Declared domain:** graph-labelling
**Intake file:** docs/research-targets/intake/b1-graceful-lobster-trees-v1.json
**Frozen in one line:** Every finite tree that has a path meeting every vertex
within distance two admits a graceful labelling.

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
the number of edges on the unique path in `T` from `u` to `v`, so `d_T(v,v) = 0`.

A **graceful labelling** of a tree `T` with `m` edges is a bijection

`phi : V(T) -> {0, 1, ..., m}`

such that the induced edge labelling `psi(uv) = |phi(u) - phi(v)|` satisfies

`{ psi(e) : e in E(T) } = {1, 2, ..., m}`

as sets. Because `|E(T)| = m`, this is equivalent to requiring `psi` to be a
bijection from `E(T)` onto `{1, ..., m}`. `T` is **graceful** if at least one
graceful labelling of `T` exists.

Define the **frozen class** `X`: a tree `T` belongs to `X` if and only if there
exists a subgraph `P` of `T` that is a path — that is, `P` is isomorphic to
`P_k` for some `k >= 1`, where `P_1` is a single vertex and no edges — such that

`for every v in V(T) there is w in V(P) with d_T(v,w) <= 2`.

`P` is called a spine of `T`. A tree may have many spines; membership in `X`
requires only that at least one exists.

**Frozen target claim.**

`for every integer m >= 0 and every tree T in X with |E(T)| = m,`
`there exists a bijection phi : V(T) -> {0, ..., m} with`
`{ |phi(u) - phi(v)| : uv in E(T) } = {1, ..., m}.`

This is one claim about one exactly specified class. It is not the Graceful Tree
Conjecture, which is the same statement with `X` replaced by the class of all
trees, and it is not a frontier-extension claim about any particular vertex
count.

### Why this class was frozen

The planning dossier states that merely checking the next vertex count is a
capability result rather than the preferred research contribution, so the target
is a class theorem and not a bound on an exhaustive frontier. The whole Graceful
Tree Conjecture is not an admissible freeze either: it is a single famous
universal statement with no bounded sub-target, and the cross-cutting acceptance
rules require exactly one exact target with a bounded first slice.

`X` was selected against four conditions.

1. `X` is defined by one unambiguous distance condition, so membership in `X` is
   decidable by exact integer arithmetic on an adjacency list, with no
   parameter, no asymptotic, and no appeal to a source convention.
2. `X` strictly contains the caterpillars, which are the same definition with
   `d_T(v,w) <= 1`. Caterpillar gracefulness is a standard classical fact and is
   explicitly excluded from being the frozen target. The containment is strict
   with a concrete exactly checkable witness: the tree on seven vertices
   obtained from `K_{1,3}` by subdividing each edge once (a spider with three
   legs of length two) lies in `X` — take the spine through two of the legs and
   the centre — but deleting its leaves leaves `K_{1,3}`, which is not a path,
   so it is not a caterpillar.
3. `X` is strictly contained in the class of all trees, so the frozen claim is a
   strict special case of the headline conjecture and cannot be mistaken for it.
   The strength relation in section 4 is therefore `weaker`.
4. The gracefulness of `X` is, on the untrusted reading of the operator's notes
   and of common terminology, not settled by any classical theorem of the
   caterpillar type. That reading is a status claim, not a fact. It appears in
   section 6 as an untrusted claim with a named acquisition target, and the
   ADR-0055 pre-research novelty re-check must cover it. If acquisition shows
   that `X` is settled, this dossier is superseded rather than repaired.

The class `X` is commonly called the class of lobsters. That name is used
nowhere in the frozen statement, because the name carries source-dependent
degenerate cases and the frozen definition above does not.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| tree | finite simple connected acyclic undirected graph, at least one vertex | infinite trees; forests; rooted, plane, or edge-weighted trees; multigraphs |
| `m` | the number of edges, so `|V| = m + 1` | `m` as the number of vertices, which shifts the label range by one |
| graceful labelling | bijection `phi : V -> {0,...,m}` whose induced labels `|phi(u) - phi(v)|` form exactly `{1,...,m}` | vertex labels drawn from `{1,...,m+1}`; edge labels merely injective without covering `{1,...,m}`; an alpha-labelling, that is a graceful labelling with a boundary value separating the two sides of the bipartition, which is strictly stronger; near-graceful or `k`-graceful variants that shift the edge-label range |
| induced edge label | the absolute difference `|phi(u) - phi(v)|` of the two endpoint labels | signed difference; difference modulo `m + 1`; a label assigned independently of `phi` |
| graceful (of a tree) | at least one graceful labelling exists | a distinguished or canonical labelling exists; all labellings are graceful; a labelling exists with extra properties |
| class `X` | there exists a path subgraph `P`, possibly a single vertex, with every vertex of `T` within `d_T`-distance 2 of `V(P)` | "deleting every leaf of `T` yields a caterpillar", which is the same class for large trees but is degenerate for `K_1` and `K_2`, where the leaf-deleted graph is empty and no convention is fixed; "diameter at most 5", a different class; "`T` has a longest path within distance 2 of every vertex", which is a formally stronger requirement whose equivalence to the frozen one is unproved here and is therefore not assumed |
| spine `P` | a path subgraph with `k >= 1` vertices; `k = 1` and `k = 2` are allowed | a spine required to have at least one edge; a spine required to be a longest or diametral path; a spine required to be unique |
| distance | number of edges on the unique `T`-path between two vertices; `d_T(v,v) = 0` | distance measured inside `P` rather than inside `T`; weighted distance; distance to the nearest leaf |
| caterpillar | the `d_T(v,w) <= 1` case of the class definition | any tree of small diameter; a tree whose leaf-deletion is a path, which agrees for large trees and is degenerate on `K_1` and `K_2` |
| "every tree in `X` with `m` edges" | universally quantified over all `m >= 0` and all `T in X` with exactly `m` edges | a single `m`; only `m >= 1`; only trees with an even or odd number of vertices; only trees up to some vertex count |
| matching hypothesis | none is imposed; the frozen class has no matching condition | the reported subcase of members of `X` admitting a perfect matching, which section 6 records as a possibly settled proper part of `X` and which is not the frozen target |
| exhaustive frontier | a statement about a bounded set of trees with a stated canonical enumeration; never a statement about `X` | "verified through 35 vertices" read as a claim about the class, or read as 35 edges rather than 35 vertices |
| canonical form of a tree | the centroid-rooted bracket encoding defined in section 7 | any adjacency-list ordering; a degree sequence; a level sequence whose tie-breaking convention is unstated |

## 3. Formalization and quantifiers

Typed informal statement, as it appears in the intake file:

`forall m : N, forall T : Tree, (T in X and edge_count(T) = m) ->`
`exists phi : V(T) -> {0..m}, Bijective(phi) and`
`{ abs(phi(u) - phi(v)) : (u,v) in E(T) } = {1..m}`

with

`T in X  <->  exists P a path subgraph of T,`
`forall v in V(T), exists w in V(P), d_T(v,w) <= 2`.

Quantifiers, in order and with their ranges:

- `forall m` an integer with `m >= 0`;
- `forall T` a finite simple tree with exactly `m` edges and `m + 1` vertices;
- `exists P` a path subgraph of `T` with at least one vertex, witnessing
  `T in X`; the target quantifies over trees for which such a `P` exists, so `P`
  is existential inside the hypothesis and never chosen by the labelling;
- `forall v in V(T)`, `exists w in V(P)` with `d_T(v,w) <= 2`, inside the
  hypothesis;
- `exists phi` a bijection from `V(T)` onto `{0,...,m}`;
- `forall e in E(T)` the induced label lies in `{1,...,m}`, and every element of
  `{1,...,m}` is induced by some edge.

There is no asymptotic in the statement, so no epsilon form is needed. Degenerate
cases are inside the claim rather than excluded: `m = 0` is the one-vertex tree,
whose unique labelling `phi(v) = 0` induces the empty edge-label set, which
equals `{1,...,0} = {}`; `m = 1` is the single edge with `phi` taking the values
`0` and `1`.

Every arithmetic object in the statement is an integer. The only operations on
the trust path are integer subtraction, absolute value, integer comparison, and
set equality on finite sets of integers.

## 4. Semantic alignment to the source statement

The source statement, as rendered in the planning dossier, is: every tree with
`m` edges admits a bijection from its vertices to `{0,...,m}` such that the
absolute differences across its edges are exactly `{1,...,m}`.

**Quantifier mapping.** `m` maps to a non-negative integer edge count, unchanged.
The source's `forall T a tree` is narrowed to `forall T a tree in the frozen
class X`. The source's `exists` labelling is unchanged. A new existential appears
only inside the hypothesis, namely the spine `P` witnessing `T in X`.

**Definition mapping.** "bijection from its vertices to `{0,...,m}`" maps to
`phi` bijective onto `{0,...,m}`. "absolute differences across its edges are
exactly `{1,...,m}`" maps to set equality of the induced edge labels with
`{1,...,m}`, with `psi(uv) = |phi(u) - phi(v)|`. "tree" maps to finite simple
connected acyclic graph. The class `X` has no counterpart in the source
statement; it is a restriction introduced here.

**Assumption delta.** The frozen target adds the hypothesis `T in X` and adds
nothing else. It removes nothing. No matching, diameter, parity, or vertex-count
hypothesis is imposed. No claim is made that `X` is a maximal class for which the
statement is provable by any particular method.

**Edge-case delta.** `m = 0` and `m = 1` are inside the frozen claim, and the
class definition admits them because a spine may be a single vertex. The
leaf-deletion reading of the class definition is degenerate exactly on those two
cases, which is why it was rejected in section 2. The frozen class is closed
under nothing that the slice relies on; in particular no reduction rule is
assumed to keep a tree inside `X`.

**Strength relation:** `weaker`. The frozen target is a strict special case of
the headline conjecture, since `X` is a proper subclass of the trees, witnessed
by any tree with a vertex at distance 3 from every path — for example the tree
obtained from `K_{1,3}` by subdividing each edge twice. The relation is recorded
as `weaker` and not as `equivalent`, and `equivalent` is unavailable in any case
because no primary source has been acquired or quoted.

## 5. Provenance and acquisition plan

Every row is `pending_acquisition`, applicability `not_assessed`. Acquisition is
human-planned, exact-URL, and separately authorized under ADR-0050; nothing here
authorizes a fetch. Rows marked `locator_unverified` carry a bibliographic
identification made offline from recollection: the operator must confirm the
identifier before acquisition, and a wrong identifier must be recorded as such
rather than silently corrected.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| A. Rosa, "On certain valuations of the vertices of a graph", Theory of Graphs (International Symposium, Rome 1966), Gordon and Breach, 1967, pages 349-355 | print volume, the pages defining beta-valuations and the caterpillar result; `locator_unverified` for the exact page range | fixes the original graceful/beta-valuation convention against the section 2 rejected readings; settles claim 6.4 (caterpillar attribution) | pending_acquisition |
| J. A. Gallian, "A Dynamic Survey of Graph Labeling", Electronic Journal of Combinatorics, Dynamic Survey DS6, latest edition | `https://www.combinatorics.org/ojs/index.php/eljc/article/view/DS6`, the subsection on trees and on lobsters; `locator_unverified` for the current edition number and subsection numbering | settles claims 6.1, 6.2, 6.3, 6.5, 6.6 in one document: current status of the frozen class, the perfect-matching subcase, the exhaustive frontier, and attributions | pending_acquisition |
| J.-C. Bermond, "Graceful graphs, radio antennae and French windmills", in Graph Theory and Combinatorics (Proceedings, Open University 1978), Pitman, 1979, pages 18-37 | print volume, the page stating the lobster conjecture; `locator_unverified` | settles claim 6.2, in particular whether the conjecture is stated for exactly the frozen class `X` or for a variant with a different degenerate-case convention | pending_acquisition |
| The computational study behind the reported exhaustive frontier | unidentified; a candidate identification is a computational study of the Graceful Tree Conjecture reporting verification of all trees up to 35 vertices, whose author and identifier this dossier cannot supply offline; `locator_unverified` and `locator_unknown` | settles claim 6.1, including whether the figure counts vertices or edges, whether all trees or a subclass were covered, and whether certificates were retained | pending_acquisition |
| The reported theorem on members of the frozen class admitting a perfect matching | unidentified; the survey row above is the intended route to the exact reference; `locator_unknown` | settles claim 6.5, which determines how much of `X` is already covered and therefore where work must not be spent | pending_acquisition |
| Wright, Richmond, Odlyzko, and McKay, "Constant time generation of free trees", SIAM Journal on Computing, 1986 | print or publisher record; the exact canonical level-sequence convention and the generation order; `locator_unverified` | pins the external generator convention named in section 7 so that the in-repo canonical form can be cross-checked against a documented convention rather than against recollection | pending_acquisition |

No row is required for the slice to run: the slice's coverage argument is
self-contained, using the in-repo canonical form and an independently computed
tree count. The rows are required before any status, novelty, or contribution
statement is made, and before the frozen class may be described as unsettled.

## 6. Prior-status claims to re-check

Each claim below is untrusted. None is used as a premise by the slice. The
ADR-0055 pre-research novelty re-check must cover every one of them, with
evidence hashes, before research execution starts, and each found source must
carry a human-supplied same/equivalent/stronger/weaker/overlapping relationship
to the frozen target.

**6.1 Exhaustive verification through 35 vertices as of July 2026.** From the
operator notes by way of the planning dossier. Untrusted, and additionally
ambiguous: it is not recorded whether 35 counts vertices or edges, whether all
trees or a subclass were covered, whether labellings were retained as
certificates, or whether the computation has been independently replayed. The
frozen target is a class theorem, so this claim bounds only what a bounded
slice can add, not what the target requires.

**6.2 The frozen class `X` is not settled.** This is the load-bearing status
claim of the dossier and it is untrusted. It rests on the common attribution of
an open conjecture about lobsters to Bermond and on the absence of a classical
theorem of the caterpillar type covering `X`. Neither has been checked against a
source here. If `X` turns out to be settled, the correct outcome is a superseding
record, not a re-scoped target.

**6.3 The Graceful Tree Conjecture is open.** Inherited from the planning
dossier's inclusion of B1 as a candidate. Untrusted.

**6.4 Caterpillars are graceful, attributed to Rosa in 1967.** The mathematical
statement is treated as a standard textbook fact and recorded as a `lemma` in the
intake file. The attribution and date are untrusted and are not used anywhere.

**6.5 Members of `X` that admit a perfect matching are graceful.** Recollected as
a published theorem; untrusted, unattributed here, and important, because if true
it covers a large proper part of the frozen class. Rediscovering that part is not
progress on the frozen target, and the risk register records it as such.

**6.6 The class `X` is what the literature calls a lobster.** A terminology
claim, untrusted. Section 2 freezes the definition locally precisely so that an
acquired source's definition must be mapped before its status can be transferred.

## 7. Bounded first slice

The slice is offline, deterministic, exact-integer, and human-authored. It calls
no model on the trust path, opens no network connection, and executes no
model-generated program.

**Inputs.** Two integers fixing the envelope: `N1`, the vertex bound for the
all-trees stage, frozen at `N1 = 18`; and `N2`, the vertex bound for the direct
class stage, frozen at `N2 = 22`. Two resource caps, stated below. No fixture,
table, or published labelling is an input.

**Canonical form.** For a tree `T`, define `canon(T)` as follows. Compute the
centroid by repeatedly deleting all leaves; the process terminates in either a
single vertex or a single edge. In the single-vertex case, root `T` there; in the
single-edge case, split `T` into the two components of `T` minus that edge and
root each at its endpoint of the edge. Encode a rooted tree recursively: a leaf
encodes as `()`, and an internal vertex encodes as `(` followed by the
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
with G1. The envelope size is `sum_{n <= N1} t(n)`, where `t(n)` is the number of
unlabelled trees on `n` vertices; the slice recomputes each `t(n)` from the
standard exact rooted-tree and free-tree integer recurrence and this dossier does
not assert the values. An untrusted planning estimate puts the total at order
`10^5`. Checks, all exact: the number of distinct canonical forms at each `n`
must equal the independently recomputed `t(n)`; the sorted list of canonical
forms is content-hashed and retained; membership in `X` is decided two ways, once
by brute force over all `O(n^2)` vertex pairs as candidate spine endpoints and
once by the iterated-leaf-deletion characterization, and any disagreement halts
the run and is retained as a fixture. Nothing is sampled at this stage.

**Stage 2, the class to `N2`.** Enumerate `X` for `n <= N2` with G2 and
deduplicate by `canon`. For every `n <= N1` the resulting per-`n` count must
equal the Stage 1 filtered count; a mismatch halts the run. For
`N1 < n <= N2` the counts are new outputs with no cross-check available from
Stage 1, so their coverage rests on the class-parameterization argument alone,
and that argument is recorded as an open proof obligation rather than as a
verified fact.

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
the leg-count parameters of a member of `X`. A fitted scheme is a candidate only.
It is recorded with the exact finite set of instances on which it was checked and
with an explicit open proof obligation that it holds for all parameter values.
No fitted scheme is reported as a lemma.

**Resource caps.** The run halts when the total number of retained trees exceeds
`5 * 10^6`, or when the cumulative Stage 3 search-node count exceeds `10^11`, or
under any stopping rule in section 10. The reached `n` is therefore a measured
output of the run and not a promise made here.

**Symmetry and canonicalization.** Isomorphic trees are identified by `canon`, so
the enumeration is over isomorphism classes rather than labelled trees. There is
no further symmetry quotient on the labelling side: complementing a labelling by
`phi -> m - phi` maps graceful labellings to graceful labellings, and the slice
uses that only to halve the Stage 3 search by fixing an orientation, never to
justify skipping a tree.

**Boundary of the claim the slice can support.** On success the slice supports
exactly this: every member of `X` with at most the measured vertex bound is
graceful, each witnessed by a stored labelling that an independent verifier
replays, and the enumeration at each `n` in Stage 1 is complete relative to the
recomputed tree count. It does not support the frozen target, which quantifies
over all `m`. It does not support any statement about trees outside `X`. A
bounded exhaustion is bounded evidence and is never promoted; the stopping rules
in section 10 forbid the promotion explicitly. Conversely, a single member of `X`
proved non-graceful would refute the frozen target and also the Graceful Tree
Conjecture, and that direction is not bounded — one certificate suffices.

## 8. Certificate and verifier contract

Result shapes, each with its certificate format and its independent verifier.

**S1, graceful labelling exhibited.** Certificate: the canonical form string of
`T`; an explicit adjacency list on vertices `0..m`; the integer vector `phi` of
length `m + 1`; and the induced edge-label vector. Verifier: rebuild the tree
from the adjacency list, check acyclicity and connectivity by an exact
union-find over `m` edges and `m + 1` vertices, recompute `canon` and compare
byte-for-byte with the certificate, check `phi` is a bijection onto `{0,...,m}`
by sorting and comparing to the exact integer range, recompute
`|phi(u) - phi(v)|` for every edge with exact integer subtraction, and check that
the multiset of induced labels equals `{1,...,m}` exactly. Every comparison is
integer equality. The verifier shares no code with the search.

**S2, class membership.** Certificate: the adjacency list plus a witnessing spine
given as an explicit vertex sequence, plus, for every vertex, the spine vertex
achieving distance at most 2 and the explicit path realizing it. Verifier:
recheck that the sequence is a path in `T` and that each declared path has length
at most 2 and connects the declared pair. Membership is thus positively
certified; a negative membership verdict is certified instead by exhausting all
`O(n^2)` endpoint pairs, which is small enough to replay in full.

**S3, bounded exhaustive coverage.** Certificate: the envelope parameters; the
per-`n` counts from both generators; the independently recomputed `t(n)` values
with the recurrence used; the sorted deduplicated list of canonical forms and its
content hash; and the list of S1 certificates keyed by canonical form. Verifier:
recompute `t(n)` from the recurrence, recompute the content hash of the sorted
list, check that every listed canonical form has an S1 certificate, and check
that the count of forms matches. Coverage is thereby checked independently of the
generator that produced it.

**S4, member of `X` not graceful.** This is the refutation shape and its bar is
the highest. Certificate: the tree; a fully replayable exhaustion record naming
every pruning rule used, each with its stated soundness lemma; and a second,
methodologically independent exhaustion of the same tree. Two admissible second
methods are unpruned enumeration of all `(m+1)!` labellings, which is only
feasible for small `m`, and a propositional encoding of gracefulness whose
unsatisfiability is accompanied by a proof log that a checker replays. The second
route needs a new ADR (section 12). Until such a route exists, S4 cannot be
produced by this slice, and a search that finds no labelling for a member of `X`
is recorded as an open item, not as a refutation.

**S5, candidate labelling scheme.** Certificate: the scheme as an explicit
formula, the exact finite instance set on which it was checked, the S1
certificate for each such instance, and the open proof obligation that it holds
for all parameters. Explicitly not a theorem and explicitly not a family result.

**Refused as a certificate, in every shape.** Floating-point output of any kind.
A model's verdict, explanation, or claim that a labelling exists or that a scheme
generalizes. A published table or third-party program's output that has not been
replayed inside the slice. Failure of a search, including failure of an
exhaustive-looking search whose pruning rules are not individually justified. A
count that matches an expected value taken from recollection rather than
recomputed from a stated recurrence.

## 9. Useful negative outcomes

If no member of `X` is found to be non-graceful and no family theorem is proved,
the following are retained machine-readably and are the deliverable.

- The exclusion set: the content-hashed sorted list of canonical forms of every
  member of `X` inside the measured envelope, each with its S1 certificate. Any
  future run may skip these without re-searching, and any future frontier claim
  must be consistent with them.
- The exact per-`n` counts of `X`, from both generators, together with the
  recomputed `t(n)` values. These are new exact combinatorial data independent of
  the labelling question.
- Every fitted labelling scheme that failed, paired with the exact smallest
  instance in the envelope that broke it. A refuted scheme is a permanent
  narrowing of the search space for schemes and is more useful than a scheme that
  merely has not failed yet.
- Every candidate pruning rule that was rejected by the `m <= 12` cross-check,
  with the exact tree and labelling that exposed it.
- Any disagreement between the two membership tests or the two generators, kept
  as an acceptance fixture, because a coverage bug that is found once must be
  impossible thereafter.
- The measured cost profile: search nodes and wall time per tree as a function of
  `m`. Under ADR-0029 a specialist or a larger envelope requires a recorded
  prediction and a measured retention gain, and this profile is the only honest
  input to such a prediction.
- The reduction question left open: whether any operation taking a member of `X`
  to a smaller member of `X` preserves gracefulness. A negative answer for a
  specific operation is retained as a refuted route.

## 10. Evaluation protocol

Mirrors the intake file exactly.

Phase: `exploratory`. Version: `1`.

Metrics:

- `class_members_enumerated`
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

- `an exact non-graceful member of the frozen class, certified under shape S4 including its independent second exhaustion`
- `a proof that every member of the frozen class is graceful, with every lemma discharged symbolically rather than by table`
- `a proved reduction rule that maps a member of the frozen class to a strictly smaller member and preserves gracefulness`
- `an explicit unresolved outcome that names the smallest remaining obligation, together with the retained exclusion set and every refuted route`

Stopping rules:

- `stop on an exact certificate of either direction and open no further search`
- `stop when fresh model spend reaches USD 20`
- `stop when two consecutive review points close no proof obligation and refute no route`
- `stop when retained class members exceed 5 * 10^6 or cumulative search nodes exceed 10^11`
- `never promote a bounded exhaustion to the universal claim; a frontier extension is recorded as a capability result and not as progress on the target`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The frozen class is already settled | Claim 6.2 is untrusted and load-bearing. If a published theorem covers `X`, the whole target evaporates and any result would be rediscovery | The ADR-0055 re-check must cover 6.2 with the survey row in section 5 acquired first; the class is defined locally so a found source can be related as same, stronger, weaker, or overlapping rather than argued about |
| A large part of the class is settled | Claim 6.5 reports the perfect-matching subcase as done. Effort spent there produces certificates that are correct and worthless | The re-check must name the subcase explicitly; if confirmed, the slice's Stage 4 must report which fitted schemes only cover the already-settled part |
| Frontier extension mistaken for research | The planning dossier warns about exactly this, and Stage 1 to Stage 3 look like progress while producing a capability result | The target claim is the class theorem; the stopping rules forbid promotion; section 7 states the boundary; the metric names separate certificates from obligations closed |
| Unsound pruning creates a false refutation | A single unjustified pruning rule turns an incomplete search into an apparent counterexample to the Graceful Tree Conjecture, the most damaging possible error | S4 requires a second independent exhaustion, which the slice cannot currently produce, so the slice structurally cannot emit a refutation; the `m <= 12` unpruned cross-check runs on every tree |
| Canonical-form bug creates false coverage | A collision silently drops trees and every downstream coverage statement becomes false | Two independent generators, per-`n` count cross-check against a recomputed recurrence, content-hashed sorted list, and a halt on any disagreement |
| Definition drift on the class | Acquired sources may define the class with different degenerate cases, so their status statements may not transfer | Section 2 freezes the definition and lists the rejected readings; a source's status is transferred only after its definition is mapped row by row |
| Recollected numbers entering the trust path | Tree counts, page ranges, and attributions in this dossier come from recollection | Counts are recomputed by the slice and never quoted as inputs; every locator is flagged `locator_unverified`; every status claim is in section 6 as untrusted |
| Model-generated enumerator executed | The enumerators are the coverage argument; under ADR-0057 production execution of generated code is disabled until its sandbox gate passes | The enumerators, the canonical form, and both verifiers are human-authored repo code; no model-generated program runs on the trust path |
| Search cost blows the envelope silently | Stage 3 is superexponential in the worst case and an unbounded run would consume the budget with nothing retained | Explicit node and member caps, the spend cap, and the stagnation rule; the reached bound is a measured output |

## 12. Capability check

**Covered by existing AdaIvy capabilities.** Declarative problem intake and its
canonical hashing, which produce the dossier this file accompanies. Exact
integer arithmetic in the standard library, which is all the slice needs.
Deterministic serialization, content hashing, and the append-only record path
used to retain certificates and failures. The bounded offline harness under
`make check`, which runs with no network, no model provider, and no container
runtime. The ADR-0047 bounded central-lead runtime, if the structural stage is
driven as composed one-round Phase 2 runs with a size-bounded proposer-only
ledger and a model-free replay. The ADR-0036 publication projection, if any
result is rendered, with claims demoted to `Conjecture` unless a computed
environment says otherwise. The ADR-0055 pre-research novelty re-check, which is
mandatory before execution.

**Would require a new ADR.**

- A propositional encoding with a replayed unsatisfiability proof log, needed for
  result shape S4. There is no SAT capability in the repo and no digest-pinned
  sandbox for a solver or proof checker. Until such an ADR exists the slice
  cannot produce a refutation, and this dossier does not assume it will.
- Acquisition of any row in section 5. Each is a separate human-planned
  exact-URL authorization under ADR-0050, and the print volumes are outside the
  activated public unauthenticated scope entirely.
- Execution of any model-generated enumerator, canonical-form routine, or
  verifier. ADR-0057 keeps production generated-code execution disabled pending
  its own sandbox gate.
- A kernel-checked family theorem. Phase 3B checks a frozen theorem supplied to
  it; there is no Lean formalization of graceful labelling in the repo, and
  producing one is a separate scope decision rather than a capability the slice
  may assume.
- Any parallel, specialist, evolutionary, or higher-tier search over the
  enumeration. ADR-0029 requires a recorded prediction and measured retention
  gain first, and this slice measures the cost profile precisely so that such a
  request could later be made honestly.

## 13. Open questions before intake

1. Is the frozen class `X` the intended freeze, or does the operator prefer a
   smaller class with a cheaper bounded slice, for example the members of `X`
   with spine length at most a fixed bound? The current freeze is a genuine
   named-conjecture-sized target and may be too large for a first slice.
2. Should the reported perfect-matching subcase, once claim 6.5 is checked, be
   excluded from the frozen class by hypothesis, so that the target covers only
   the residual? That would change the target claim and requires a new dossier
   version rather than an edit.
3. Does the operator accept `N1 = 18` and `N2 = 22` as the frozen envelope, given
   that claim 6.1 reports an existing frontier at 35 vertices and the slice's
   bounded output is therefore expected to be strictly inside already-covered
   ground?
4. Is a SAT-plus-proof-log route worth an ADR request now, given that without it
   the slice structurally cannot emit a refutation of the frozen target?
5. The exhaustive-frontier source in section 5 is unidentified. Can the operator
   supply the exact locator from the original notes, so that claim 6.1 is
   checkable rather than merely flagged?
