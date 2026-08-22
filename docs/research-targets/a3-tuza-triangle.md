# A3. Erdos #167, Tuza's triangle problem — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item A3 (tier A)
**Declared domain:** graph-packing-and-covering
**Intake file:** docs/research-targets/intake/a3-tuza-triangle-covering-v1.json
**Frozen in one line:** For every finite simple graph `G`,
`tau_3(G) <= 2 nu_3(G)`, where `nu_3(G)` is the maximum number of pairwise
edge-disjoint triangles of `G` and `tau_3(G)` is the minimum number of edges
whose deletion leaves `G` triangle-free.

This is a scoped intake package. It does not approve a formalization, establish
that the problem is open, authorize source acquisition, assess novelty or
significance, create mathematical warrant, or activate a capability. Novelty,
significance, and source applicability are `not_assessed`, and no source has
been acquired: every external statement below is an untrusted candidate.
Nothing here grants graph admission or proof status to any claim.

## 1. Frozen target

Let `G` be a finite simple undirected graph (no loops, no multiple edges, no
weights, no orientation). A **triangle** of `G` is a set of three distinct
pairwise adjacent vertices, identified with its set of three edges. Define

- `nu_3(G)` = the maximum cardinality of a collection of triangles of `G` that
  are pairwise **edge-disjoint**, meaning no two chosen triangles share an
  edge. Sharing a vertex is permitted.
- `tau_3(G)` = the minimum cardinality of a set `D` of **edges** of `G` such
  that the spanning subgraph `G - D`, on all of `V(G)` with edge set
  `E(G) \ D`, contains no triangle.

The frozen target is the universal inequality

> for every finite simple undirected graph `G`: `tau_3(G) <= 2 nu_3(G)`.

Every load-bearing choice is pinned: **edge**-disjoint packing on the left,
**edge** deletion on the right, the constant `2`, and simplicity of `G`. The
planning dossier's other phrasing — a graph with at most `k` edge-disjoint
triangles can be made triangle-free by deleting at most `2k` edges — names the
same object: instantiating `k = nu_3(G)` gives the ratio form, and conversely
the ratio form applied to any `G` with `nu_3(G) <= k` gives
`tau_3(G) <= 2 nu_3(G) <= 2k`. That equivalence is recorded as a definitional
assumption rather than assumed silently.

The planning dossier's result shape was "proof, counterexample, or improved
covering bound". Under cross-cutting rule 1 that disjunction is not a target.
The improved-bound disjunct is removed: replacing `2` by some `c < 2` is a
different frozen target needing its own problem definition. Proof and
counterexample both remain acceptable *outcomes* of this one target, which is
why `problem_type` is `explore` rather than `prove`.

## 2. Definitions and conventions

The planning dossier names the definitional confusions as this item's primary
risk. They are given their own rejected-reading column below.

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| `nu_3(G)` | maximum number of pairwise **edge**-disjoint triangles; two triangles may share a vertex | the **vertex**-disjoint triangle packing number; a packing forbidding both shared edges and shared vertices; the fractional packing number `nu_3*`; the total number of triangles of `G`; the number of triangles in an edge-disjoint decomposition of all of `E(G)`; the size of an arbitrary **maximal** rather than **maximum** packing |
| `tau_3(G)` | minimum number of **edges** whose deletion leaves no triangle | the minimum number of **vertices** whose deletion destroys every triangle; the fractional cover number `tau_3*`; deleting edges from an induced rather than spanning subgraph |
| "edges meeting every triangle" | the same object as `tau_3(G)`: a triangle survives iff none of its three edges is deleted, so a hitting set of the triangle edge-hypergraph and a triangle-destroying deletion set coincide | treating them as two different quantities, or as a vertex hitting set |
| triangle | three distinct pairwise adjacent vertices, identified with its three edges; induced and non-induced coincide for `K_3` | a closed walk of length three; a 3-cycle of a multigraph; a triangle of the complement; a subdivision of `K_3` |
| edge-disjoint | no two chosen triangles share an **edge**; shared vertices allowed | no shared vertex; no shared edge **or** vertex |
| `G - D` | the **spanning** subgraph `(V(G), E(G) \ D)` | the subgraph induced on the vertices untouched by `D` |
| finite graph | finite **simple**: no loops, no multiple edges, no weights. Order zero included, with `tau_3 = nu_3 = 0` | multigraphs, where parallel edges change which triangles are edge-disjoint; infinite graphs; digraphs; the 3-uniform hypergraph analogue |
| "at most `k` edge-disjoint triangles" | `nu_3(G) <= k`; instantiated at `k = nu_3(G)` this is the frozen ratio form | "exactly `k`"; the size of some maximal but non-maximum packing |
| the constant `2` | pinned; part of the statement | a free parameter `c`, i.e. the improved-covering-bound target |
| `K_4`, `K_5` | the complete graphs on 4 and 5 vertices | `K_4` minus an edge; the 4-cycle with both diagonals (which is `K_4`); the book graphs |

**Sharpness values, stated as reproduction targets rather than claims.** The
slice computes these from the definitions with its own exact checkers:
`nu_3(K_4) = 1` and `tau_3(K_4) = 2`; `nu_3(K_5) = 2` and `tau_3(K_5) = 4`. In
both cases the ratio is exactly `2`. The `tau_3` values are cross-checked
against the Mantel/Turan identity `tau_3(K_n) = C(n,2) - floor(n^2/4)`, giving
`6 - 4 = 2` and `10 - 6 = 4`. If a computed value disagrees with the planning
notes' report, the discrepancy is recorded, never silently reconciled.

`K_5` also separates the two readings of `nu_3`: it has two pairwise
edge-disjoint triangles but only one vertex-disjoint triangle. So confusing the
readings changes the left-hand quantity, not merely its interpretation.

## 3. Formalization and quantifiers

```
forall G a finite simple undirected graph,
  tau_3(G) <= 2 * nu_3(G)
where
  nu_3(G) = max { card(P) : P a set of triangles of G, pairwise edge-disjoint }
  tau_3(G) = min { card(D) : D subset of E(G),
                             (V(G), E(G) \ D) contains no triangle }
  a triangle of G = a set of three distinct pairwise adjacent vertices,
                    identified with its three edges
```

Quantifier order, exactly as in the intake file:

1. `forall G` a finite simple undirected graph, with no bound on the order.
2. A `max` over collections `P` of pairwise edge-disjoint triangles, defining
   `nu_3(G)`.
3. A `min` over edge subsets `D` whose deletion leaves no triangle, defining
   `tau_3(G)`.

Both extrema are over finite nonempty sets — the empty packing and the full
edge set `D = E(G)` are always admissible — so both are well defined for every
finite `G`, including the order-zero graph where both are `0`.

`formal_language` is `typed_informal_math`, `version` 1, `approval_status`
`proposed`. Human approval of the semantic alignment is still required and is
not implied by this file.

The negation, which is what the sweep searches for, is: there exists a finite
simple `G` with `tau_3(G) > 2 nu_3(G)`. Note the asymmetry this creates, which
drives section 8: confirming the inequality for one `G` needs only a witness
pair, whereas refuting it needs two exact bounds in opposite directions.

## 4. Semantic alignment to the source statement

**Quantifier mapping.** `G` maps to a universally quantified finite simple
graph with no order bound. `k` in the planning dossier's first phrasing maps to
the instantiation `k = nu_3(G)`, which is what makes the two phrasings the same
object. The packing achieving `nu_3` maps to a maximum over pairwise
edge-disjoint triangle collections; the deletion set achieving `tau_3` to a
minimum over edge subsets leaving the spanning subgraph triangle-free. The
planning statement's question mark maps to the affirmative inequality, with
`explore` preserving a counterexample as an outcome.

**Definition mapping.** "At most `k` edge-disjoint triangles" maps to
`nu_3(G) <= k` with edge-disjointness as frozen. "Made triangle-free by
deleting at most `2k` edges" maps to `tau_3(G) <= 2k` with edge deletion from
the spanning subgraph. "`K_4` and `K_5` show the factor 2 would be best
possible" maps to the four exact integer values in section 2, each recomputed
rather than assumed. "Every finite graph" maps to every finite **simple**
graph.

**Assumption delta.**

- The planning statement is a question and offers two phrasings; the frozen
  target is the ratio form, and the equivalence of the two at `k = nu_3(G)` is
  a recorded definitional assumption.
- The improved-covering-bound disjunct is removed under cross-cutting rule 1.
- Simplicity is made explicit. The planning dossier says "every finite graph";
  multigraphs are excluded here because parallel edges change which triangles
  count as edge-disjoint, which would change `nu_3` and so the whole claim.
- The planning slice says to reproduce "best general bounds". Those are
  unacquired, so the slice reproduces only the `K_4` and `K_5` sharpness
  values, which it can compute exactly from the frozen definitions alone.
- Mature LP formulations are admitted only in exact rational form. A
  floating-point solver is refused rather than discouraged, and the purely
  fractional route is recorded as unable to certify a counterexample at all.

**Edge-case delta.**

- A triangle-free `G` has `nu_3 = tau_3 = 0` and satisfies the inequality with
  equality; the order-zero and order-one graphs are the degenerate cases.
- Every triangle is 2-connected, so it lies inside a single block of `G`. Both
  `nu_3` and `tau_3` are therefore additive over blocks, and a minimal
  counterexample is 2-connected.
- An edge in no triangle belongs to no packing and to no minimum cover, so
  deleting it changes neither parameter. A minimal counterexample therefore has
  every edge in a triangle, and likewise every vertex in a triangle.
- `K_5` separates edge-disjoint from vertex-disjoint packing: two versus one.
- The inequality is isomorphism-invariant, so a sweep over one representative
  per isomorphism class loses nothing.

**Strength relation: `unresolved`.** The frozen ratio form and the planning
dossier's `k` phrasing are genuinely equivalent, and that equivalence is
recorded and provable locally. But the relation to the **source** cannot be
`equivalent`: no primary source has been acquired, and the spec forbids
`equivalent` without a quoted acquired source. Whether the catalogue or Tuza's
original statement restricts to simple graphs, uses the same constant, or is
phrased over multigraphs is unknown, and each of those would change the
relation. `unresolved` is the honest value; resolving it is item 1 of
section 13.

## 5. Provenance and acquisition plan

No acquisition is performed by this dossier. Under ADR-0050 acquisition is
public, unauthenticated, human-planned, exact-URL, one request at a time, and
separately authorized. Every row is `pending_acquisition` with applicability
`not_assessed`.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Erdos Problems catalogue entry 167 | `https://www.erdosproblems.com/167` — the whole single HTML page, including the status label, the statement rendering, and the reference list | settles T1 (current open status), T2 (which phrasing the catalogue renders and whether it says simple or general graph), and identifies the sources for T3 and T4 | pending_acquisition, applicability not_assessed |
| Tuza's original statement of the conjecture | paper, page, and statement number to be identified from the acquired entry's reference list; deliberately not guessed here, since guessing a locator is not human-planned acquisition | settles T2 in the primary source: whether the frozen ratio form is the source form, whether the source restricts to simple graphs, and whether the constant is 2 | pending_acquisition, applicability not_assessed |
| The source for the reported best general covering bound | to be identified from the acquired entry's reference list | settles T3, the "best general bounds" the planning slice asks to reproduce. Until acquired, the slice reproduces only the `K_4` and `K_5` sharpness values | pending_acquisition, applicability not_assessed |
| The source for the reported sharpness of the factor 2 | to be identified from the acquired entry's reference list | settles T4. Note that acquiring it changes nothing on the trust path: the slice recomputes the four exact values itself | pending_acquisition, applicability not_assessed |
| Post-2025 literature on Tuza's conjecture, its fractional and vertex variants, and known reducible classes | no exact locator can be written before the catalogue entry and its references are acquired; recorded as an ADR-0055 obligation rather than a URL | settles T1 and T5, in particular whether a reduction the slice proves is already known | pending_acquisition, applicability not_assessed |
| OEIS A000088, simple graphs on `n` unlabeled nodes | `https://oeis.org/A000088` | settles T6, the per-order class counts used as a generator self-check; the sweep recomputes the counts, so this is a convenience and not a dependency | pending_acquisition, applicability not_assessed |

## 6. Prior-status claims to re-check

Each item is **untrusted**, inherited from the planning notes, and must be
covered by the ADR-0055 pre-research novelty re-check bound to this problem's
subject hash immediately before research starts. None creates open status,
novelty, significance, applicability, graph admission, or warrant.

- **T1 — open status.** The planning dossier cites the catalogue entry but
  states no label for entry 167. Whether the problem is open, partially
  settled, or settled is unknown here.
- **T2 — statement form.** Which phrasing the source uses, and whether it
  restricts to simple graphs or admits multigraphs, is unknown. This is
  load-bearing: over multigraphs `nu_3` changes, so the target would change.
- **T3 — best general bounds.** The planning notes report that best general
  bounds exist and that the slice should reproduce them. Unacquired. The frozen
  slice therefore reproduces only what it can derive: the trivial sandwich
  `nu_3 <= tau_3 <= 3 nu_3` and the `K_4`, `K_5` values.
- **T4 — sharpness of the factor 2.** The planning notes report that `K_4` and
  `K_5` show the factor 2 would be best possible. The slice recomputes all four
  values exactly rather than relying on the report; a mismatch is recorded as a
  source discrepancy.
- **T5 — maturity and rediscovery risk.** The planning notes report that the
  problem is broad and well studied, with mature LP and combinatorial
  formulations and
  natural reductions. This is the principal reason the ADR-0055 re-check must
  cover terminology variants and equivalent formulations, at minimum: Tuza's
  conjecture, triangle edge cover, triangle packing and covering, the
  fractional variant, and the vertex-deletion variant. Any reduction the slice
  proves is very likely already known, and the re-check must be run before, not
  after, the slice reports it.
- **T6 — enumeration counts.** The reported numbers of isomorphism classes of
  simple graphs for orders 1 to 10 — `1, 2, 4, 11, 34, 156, 1044, 12346,
  274668, 12005168`, with order 11 reported as `1018997864` — are untrusted.
  The sweep recomputes each and treats disagreement as a generator fault that
  halts the run.

## 7. Bounded first slice

**Inputs.** None external. Two generators, both constructed locally, plus one
untrusted candidate generator for the sweep.

**Exact algorithms and arithmetic.** All integer and rational, standard library
only.

- Triangle enumeration: for each edge `uv`, iterate over the common
  neighbourhood via bitset intersection `adj[u] & adj[v]`. Yields the complete
  triangle list with its three-edge index set, exactly.
- **Exact `nu_3`** (maximum edge-disjoint triangle packing): depth-first
  branch and bound over the triangle list in a frozen canonical order, with an
  edge-usage bitmask and the bound `card(P) + floor(unused_edges/3)`. Exact
  integers only; the node log is replayable.
- **Exact `tau_3`** (minimum triangle-destroying edge set): iterative deepening
  on `card(D)` from the lower bound upward, branching on the three edges of an
  uncovered triangle. Exact integers only; the node log is replayable.
- **Exact rational LP bounds**, used to prune and to certify: an exact rational
  fractional cover of value `v` gives `nu_3 <= floor(v)`; an exact rational
  fractional packing of value `w` gives `tau_3 >= ceil(w)`. Both are finite
  lists of rationals, replayable by exact arithmetic. No simplex float ever
  appears; a candidate solution may be produced any way at all, but only the
  exact rational feasibility and value check certifies.
- **The one-sided certificate loop, which is the sweep's primary path.** For
  each `G`, greedily build a maximal edge-disjoint packing `P`, then search for
  an edge set `D` with `G - D` triangle-free and `card(D) <= 2 card(P)`. If one
  is found, `G` is certified — `tau_3 <= card(D) <= 2 card(P) <= 2 nu_3` —
  without computing either optimum. Only graphs that resist this cheap
  certificate need the exact optima. This is what makes the sweep affordable
  and is the single most important design choice in the slice.

**Exact reductions the slice proves, not assumes.** Each is a discharged
obligation with its own proof record:

- **R1.** Every triangle is 2-connected, so lies in one block of `G`; `nu_3`
  and `tau_3` are additive over blocks; a minimal counterexample is
  2-connected.
- **R2.** An edge in no triangle is in no packing and no minimum cover;
  deleting it changes neither parameter; a minimal counterexample has every
  edge in a triangle.
- **R3.** A vertex in no triangle can be deleted; a minimal counterexample has
  every vertex in a triangle.
- **R4, a candidate reduction to prove or refute.** If some triangle `T` has
  all three edges in no other triangle, then plausibly
  `nu_3(G) = 1 + nu_3(G - E(T))` and `tau_3(G) = 1 + tau_3(G - E(T))`, so `G`
  reduces. This is stated as a **candidate**: the slice must prove it exactly
  or exhibit the instance that refutes it, and either outcome is retained.

**Sharpness reproduction.** `K_4` and `K_5` are constructed explicitly, their
`nu_3` and `tau_3` computed by both the branch-and-bound checkers and the
Mantel/Turan identity for `tau_3(K_n)`, and the two routes cross-checked. This
is a two-route agreement test on the checkers themselves before any sweep runs.

**Search envelope and its size.** Exhaustive over isomorphism classes of finite
simple graphs, orders 1 to 10; the reported class count at order 10 is about
`1.2e7`. Order 11 is attempted only on the **reduced** class set surviving R1
to R3, and only if that reduced count fits a frozen node budget: the full order
11 count is reported as about `1.0e9`, which is not feasible as a full sweep in
a bounded offline run. Per-graph cost is dominated by triangle enumeration
(`O(n^3)`, at most about `1000` bitset steps at order 10) plus the one-sided
certificate attempt; exact optima are computed only for the residue.

**Where exhaustion stops being feasible.** At order 11 for the full class set,
and at order 12 outright: the reported class count at order 12 exceeds `1e11`,
so no reduction factor available here brings it into a bounded run. Orders 11
and above are therefore **not** covered as full sweeps, and no statement about
them may be derived from this slice.

**Canonicalization.** "Unlabeled" means exactly one representative per
isomorphism class, which is sound because the inequality is
isomorphism-invariant. Candidate generation uses `nauty`'s `geng`, which emits
canonical `graph6` records. That generator is an **untrusted candidate
producer** and is not a pinned repository dependency (section 12). Its output is
re-verified in repository: every record is decoded independently, every
reported witness is recomputed from the decoded adjacency, the per-order class
counts are recomputed and compared against T6, and an in-repository orderly
generation run reproduces the class sets for orders up to 8. Exhaustiveness
remains a property of the generator, not of the verifier, and the coverage
claim is recorded as generator-dependent. This follows the Graffiti-322
precedent in `work/graffiti-322-20260821-round2/`.

**Exhaustive versus sampled.** The class sweep is exhaustive over its stated
orders, subject to the generator caveat. `K_4` and `K_5` are individual
constructed graphs. Nothing is randomly sampled, so there is no statistical
claim anywhere in the slice.

**What a clean finite sweep to order `K` does and does not entail.** It does
entail: every finite simple graph on at most `K` vertices satisfies
`tau_3 <= 2 nu_3`, with per-graph certificates, subject to the
generator-dependent coverage caveat. It also entails an exact value for the
maximum observed ratio over that range. It does **not** entail anything about
order `K+1` or above; it does **not** entail the universal inequality; it does
**not** establish that the factor `2` is best possible in general, only that it
is attained at the orders where equality was found; and the set of equality
cases found is **data**, not a classification of equality cases. A minimal
counterexample, if one exists, could have any order above `K`, and the sweep
constrains only its order from below.

## 8. Certificate and verifier contract

The two directions are **not symmetric**, and the asymmetry is the substance of
this section.

| Result shape | Certificate format | Independent verifier |
|---|---|---|
| The inequality holds for a specific `G` | a list `P` of pairwise edge-disjoint triangles and an edge set `D`, with `card(D) <= 2 card(P)`. Neither need be optimal | a second implementation rebuilds `G` from its edge list, checks that every member of `P` is a triangle of `G` and that the members are pairwise edge-disjoint, enumerates all triangles of `G - D` and confirms there are none, and checks the integer inequality `card(D) <= 2 card(P)`. Purely combinatorial, exact, and cheap |
| Exact `nu_3(G) = p` | the attaining packing (a lower bound witness) plus, for the upper bound, either an exact rational fractional cover of value `v` with `floor(v) = p`, given as an explicit list of rationals, or the replayable branch-and-bound node log establishing that no packing of size `p+1` exists | the verifier checks the packing directly; checks the fractional cover for exact rational feasibility (every triangle's three edge weights sum to at least 1) and recomputes its value; or independently replays the branch-and-bound log node by node and confirms the same exhaustion |
| Exact `tau_3(G) = q` | the attaining deletion set (an upper bound witness) plus, for the lower bound, either an exact rational fractional packing of value `w` with `ceil(w) = q`, given as an explicit list of rationals, or the replayable node log establishing that no deletion set of size `q-1` works | the verifier confirms `G - D` is triangle-free; checks the fractional packing for exact rational feasibility (every edge's incident triangle weights sum to at most 1) and recomputes its value; or replays the node log |
| **Counterexample:** `tau_3(G) > 2 nu_3(G)` | the graph as an edge list plus `graph6`; a certified **upper** bound `nu_3(G) <= p`; a certified **lower** bound `tau_3(G) >= q`; and the integer check `q > 2p`. Both bounds must come from the two rows above. A checked SAT/UNSAT proof log is an admissible substitute for either node log | two independent replays, one per bound, each rebuilding `G` from the edge list alone. This is the hardest certificate in the dossier and the only one that settles the frozen target negatively |
| Bounded exhaustion to order `K` | the per-order table of class count, reduced count surviving R1 to R3, one-sided-certificate count, exact-optimum count, equality cases, and the maximum observed ratio as a reduced fraction with its argmax graph; the generator invocation and its output hash; the frozen node budget | a replay recomputes every per-order count from the recorded generator output, and separately regenerates orders up to 8 in repository and compares class sets. A mismatch is a fault, not a correction |
| Universal proof | a written derivation reduced to the frozen definitions and the recorded lemmas | human review, plus formal checking only if the whole statement fits one sealed Phase 3B submission (section 12 says it does not) |

**Why the fractional route cannot refute the inequality.** Since
`nu_3* = tau_3*`, exact rational LP certificates alone bound `nu_3` from above
and `tau_3` from below by the *same* quantity. A counterexample therefore
requires an integrality gap on at least one side, and `floor`/`ceil` rounding
helps only where the gap is already large. This is recorded as a refused route
so the LP-only path is not replayed blind expecting a counterexample. Integral
bounds must come from a replayable exhaustive search or a checked
unsatisfiability proof.

**Refused as a certificate, without exception.**

- Any floating-point number: a simplex or interior-point optimum, a
  branch-and-cut bound from a floating-point solver, or a tolerance-based
  optimality claim. The repository owner rejects floating-point solvers
  outright and ADR-0035 adopts no solver. Such output is exploration-only and
  is discarded rather than rounded if it reaches a certificate.
- A model's assertion that the inequality holds or fails.
- An unreplayed third-party program's output. `nauty` may *produce* candidates;
  only the in-repository exact re-check certifies any of them, and `nauty`'s
  exhaustiveness is recorded as an assumption rather than certified.
- **Failure of a search.** Completing the sweep to order 10 with no
  counterexample certifies a statement about orders up to 10 and nothing else.
  It is never a proof of the universal inequality.
- A maximal packing presented as a maximum one. `nu_3` is a maximum; a greedy
  maximal packing is a lower bound only, and using it as `nu_3` would make the
  one-sided certificate unsound in the refuting direction.
- An exact value for one parameter used to infer the other. `nu_3` and `tau_3`
  are separately certified; neither is derived from the other except through
  the recorded sandwich lemma, which is a bound and not an equality.

## 9. Useful negative outcomes

- **The exhausted frontier.** The highest order swept exhaustively, kept
  separate from the highest order *attempted*, with per-order class counts and
  node counts.
- **The exact ratio table.** Per order, the maximum of `tau_3(G)/nu_3(G)` as a
  reduced fraction, with the argmax graph in `graph6` and as an edge list. This
  is the artifact a future improved-covering-bound target would take as input,
  and it is retained whether or not a counterexample appears.
- **The equality-case list.** Every `G` found with `tau_3 = 2 nu_3`, stored
  machine-readably per order. This is **data**, explicitly not a classification
  of equality cases, and any report must say so.
- **The proved minimal-counterexample constraint set.** R1, R2, R3, and
  whatever else is proved, each with its proof record and its discharged-
  obligation status. Each constraint shrinks the search space for every future
  run on this target.
- **R4's verdict.** Proved, with its proof; or refuted, with the exact instance
  that breaks it. Both are retained; a refuted candidate reduction is as
  valuable as a proved one, because it stops the route being retried.
- **The reduced class counts.** Per order, how many classes survive R1 to R3.
  This is what determines whether order 11 is reachable at all and is the
  measurement a later run would plan against.
- **Refuted routes.** In particular, confirmation that the purely fractional LP
  route cannot certify a counterexample, recorded as a closed route in the
  manner of the `prior_parity_route_gap` record in the Graffiti-322 precedent.
- **Source discrepancies.** Any mismatch between a recomputed value and T4 or
  T6, retained as an open discrepancy rather than resolved in favour of either
  side.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. `version` 1, `phase`
`exploratory`.

Metrics:

- `unlabeled_graphs_surveyed`
- `graphs_surviving_exact_reductions`
- `graphs_certified_by_one_sided_certificate`
- `exact_optima_computed`
- `equality_cases_recorded`
- `candidate_reductions_proved`
- `candidate_reductions_refuted`
- `generator_count_mismatches`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria:

- `an exact counterexample graph carrying a certified exact upper bound on nu_3
  and a certified exact lower bound on tau_3 with tau_3 > 2*nu_3`
- `a rigorous proof of tau_3(G) <= 2*nu_3(G) for every finite simple graph`
- `or an explicit unresolved outcome recording the highest exhausted order, the
  exact maximum observed ratio tau_3/nu_3 as a reduced fraction with its argmax
  graph, the proved minimal-counterexample structural constraints, and the
  smallest remaining obligation`

Stopping rules:

- `stop on an exact counterexample whose nu_3 upper bound and tau_3 lower bound
  certificates have both been replayed independently`
- `stop on a rigorous derivation covering every finite simple graph in scope`
- `stop when fresh model spend reaches USD 20`
- `stop when two consecutive review points close no obligation, raise no
  exhausted order, and prove no new reduction`
- `never promote a completed finite sweep to the universal inequality; record
  the exhausted order and the surviving reduced class counts instead`
- `discard rather than round any packing or covering bound produced by
  floating-point linear programming`
- `halt and report a generator fault if any recomputed isomorphism-class count
  disagrees with the recorded count`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Edge-disjoint confused with vertex-disjoint | it changes `nu_3` itself, not merely its reading: `K_5` has two edge-disjoint but one vertex-disjoint triangle, so the confusion silently doubles or halves the left-hand side and manufactures counterexamples | `nu_three_definition` is a definitional assumption listing the rejected reading; the section 2 table gives it a row; `K_5` is in the sharpness reproduction precisely because it separates the two |
| Edge deletion confused with vertex deletion | vertex deletion gives a strictly smaller parameter, so the inequality becomes easier and a "verified" sweep proves the wrong thing | `tau_three_definition` is a definitional assumption; `G - D` is defined as the spanning subgraph in the section 2 table; the verifier enumerates triangles of `G - D` directly rather than trusting a count |
| Maximal packing used as maximum | a greedy packing is a lower bound; using it as `nu_3` makes the one-sided certificate unsound in the refuting direction, which is exactly where soundness matters | the one-sided certificate is deliberately one-sided and is documented as such; a refutation requires a certified **upper** bound on `nu_3` from a separate route; section 8 refuses the substitution by name |
| Floating-point LP entering a bound | the problem's mature LP formulations make a solver the obvious tool, and its output looks authoritative | `no_floating_point_linear_programming` is a recorded refused route; every bound on a trust path is an exact rational certificate or a replayable log; a float that reaches a certificate is discarded, not rounded |
| Expecting the fractional route to refute | `nu_3* = tau_3*`, so the LP relaxation cannot separate the two sides; a run could burn its whole budget there | `fractional_route_cannot_certify_a_counterexample` is a recorded refused route with the reason; section 8 states the integrality-gap requirement explicitly |
| Promoting the sweep to the universal statement | the most likely way this target produces a false result, and the exact failure the planning dossier warns about | a stopping rule forbids it; section 8 lists search failure as a refused certificate; the reported artifact is the exhausted order plus the ratio table, never a bound |
| Rediscovering a known reduction | the problem is reported as well studied, so R1 to R4 and anything beyond them are likely already known | T5 records the risk; the ADR-0055 re-check must cover terminology variants and equivalent formulations **before** the slice reports a reduction, not after; a proved reduction is recorded as a discharged obligation, never as a contribution |
| Generator-dependent coverage | exhaustiveness of the sweep is `nauty`'s property, not the verifier's; a silently incomplete generation reads as a clean negative result | class counts recomputed and compared against T6; independent in-repository regeneration for orders up to 8; the coverage claim is labelled generator-dependent; a count mismatch halts the run |
| Order 11 partially swept and reported as swept | the reduced order-11 set may be attempted and abandoned, which is easy to mis-summarise | the frontier record stores highest **exhausted** order separately from highest **attempted** order, and the node budget and abandonment point are part of the certificate |
| Multigraph drift | over multigraphs `nu_3` changes, so a single admitted parallel edge changes the target | simplicity is a definitional assumption and the exclusion's reason is recorded; the decoder rejects any non-simple record rather than normalizing it |

## 12. Capability check

**Covered by existing capabilities.**

- ADR-0039 declarative problem intake: the intake file is exactly that
  artifact, and `problem validate` plus `problem demo` confirm it creates no
  trust (`logical_status unknown`, novelty and significance `not_assessed`,
  zero warrants).
- Exact integer and rational arithmetic with the standard library only, as
  repository-authored code under `src/` exercised by the offline suite. The
  whole slice needs nothing beyond `int`, `Fraction`, and bit operations —
  including the exact rational LP certificate *checks*, which are feasibility
  and value verifications rather than optimizations. Ad-hoc exact arithmetic
  written and run by the driving agent in a scratch workspace, which is the
  shape the `work/graffiti-322-20260821-round2/` precedent actually took, is
  NOT this capability. It is an unmet AdaIvy capability, because the ADR-0057
  campaign has no operator entrypoint to record a program and its run against,
  and anything produced that way is an external-origin contribution under
  ADR-0057 section 5 — imported with an `external_codex` or `human` root and
  never relabelled as AdaIvy work.
- Exhaustive branch and bound with a replayable node log, and canonical
  candidate re-verification, both established by the same precedent.
- ADR-0055 two-fresh-novelty-rechecks: the gate for T1 to T6, and the
  particularly important gate for T5's rediscovery risk.
- Phase 3A memory for machine-readable retention of the frontier, the ratio
  table, the equality cases, the reduction verdicts, and failed routes.
- ADR-0047 bounded central-lead runtime if a model is involved; the target is
  frozen and no warrant is producible there.
- ADR-0036 publication projection for any write-up: a claim from this slice
  computes to `Conjecture` absent a kernel-checked attestation, except that an
  exact certificate reaches `Proposition` — the intended ceiling here.

**Would require a new ADR.**

- **Admitting `nauty`/`geng` as a coverage-bearing dependency.** The binary
  exists in the local environment but is not pinned, digest-recorded, or
  licence-recorded in this repository, and the engineering rules require both
  before a dependency is added. Basing an exhaustiveness claim on it needs an
  ADR covering the pin, the licence, the invocation bound, and the treatment of
  its completeness as an assumption. Writing an in-repository orderly generator
  needs no ADR; declaring its output exhaustive on a trust path does.
- **An exact rational LP *solver*.** Checking a supplied rational certificate
  needs nothing new. *Finding* one does. If the slice is to derive its own
  fractional certificates rather than construct them combinatorially, that is a
  new exact-optimization capability. Note also that ADR-0035 admits
  certificates only from a human deriving principal and rejects any certificate
  declaring a solver or search origin, so a machine-derived LP certificate
  needs either that human boundary or a new ADR defining machine derivation.
- **A checked SAT/UNSAT proof pipeline.** Section 8 admits a checked UNSAT
  proof log as a substitute for a branch-and-bound node log. No SAT solver or
  proof checker exists in this repository, and admitting one — solver, proof
  format, and independent checker — is a new capability needing its own ADR.
- **Any floating-point LP or IP solver.** Refused outright by
  repository-owner rule, not gated. There is nothing to activate.
- **Formalizing the universal inequality.** The sealed Phase 3B runtime freezes
  one theorem per submission and ADR-0040's repair loop cannot change the
  statement, hypotheses, or imports. A development defining `nu_3` and `tau_3`
  and proving the inequality is outside the ADR-0016 and ADR-0040 bounds and
  would need its own ADR.
- **Acquisition of any row in section 5.** ADR-0050, human-planned exact-URL,
  separately authorized. Not performed here.
- **Any Crossref discovery query** over these terms runs under ADR-0051, is
  inspiration-only, and does not itself perform or satisfy the ADR-0055
  re-check.

The exact checkers, the one-sided certificate loop, the reductions, and the
sharpness reproduction all run on existing capability. Only the sweep's
coverage claim and the counterexample-side proof pipelines need new decisions.

## 13. Open questions before intake

1. **Simple or general graphs?** T2 must be resolved by acquiring the source.
   If the original statement is over multigraphs, `nu_3` changes and the frozen
   target must be re-frozen, not amended. This is the gating question.
2. **Is the problem still open (T1)?** The planning dossier records no status
   label for entry 167. The ADR-0055 re-check must settle this before compute
   is authorized.
3. **Is `nauty` admitted, or is an in-repository generator required?** This
   decides whether the sweep's coverage claim is generator-dependent or
   self-contained, and it needs a decision before the slice is scheduled.
4. **How far does the sweep go?** The frozen envelope is orders 1 to 10
   exhaustive, with order 11 attempted only on the R1-to-R3-reduced set inside
   a node budget. The operator may cut order 11 entirely or raise the budget
   once the reduced counts are measured.
5. **Is a SAT/UNSAT proof pipeline authorized?** Without it, counterexample
   lower bounds on `tau_3` rest entirely on replayable branch-and-bound logs,
   which is workable at small orders and increasingly expensive above them.
6. **Should the improved-covering-bound target be opened as a sibling?** The
   ratio table this slice produces is exactly its input. It must be its own
   problem definition; it is not opened here.
7. **Confirm the `20` USD spend cap**, the branch-and-bound node budget, and
   the review-point cadence used by the stagnation rule.

Human approval of the semantic alignment in sections 3 and 4 remains required
and is not granted by this file.
