# A1. Erdos #128 — scoped research dossier

**Compiled:** 21 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item A1 (tier A)
**Declared domain:** extremal-graph-theory
**Intake file:** docs/research-targets/intake/a1-erdos-128-local-density-v1.json
**Frozen in one line:** For every integer `n >= 1` and every finite simple
graph `G` on exactly `n` vertices, if every induced subgraph of `G` on at least
`floor(n/2)` vertices has more than `n^2/50` edges, then `G` contains a
triangle.

This is a scoped intake package. It does not approve a formalization, establish
that the problem is open, authorize source acquisition, assess novelty or
significance, create mathematical warrant, or activate a capability. Novelty,
significance, and source applicability are `not_assessed`, and no source has
been acquired: every external statement below is an untrusted candidate.
Nothing here grants graph admission or proof status to any claim.

## 1. Frozen target

Let `n` be an integer with `n >= 1` and let `G` be a finite simple undirected
graph with exactly `n` vertices (no loops, no multiple edges, no weights, no
orientation). Write `V(G)` for its vertex set, `e(H)` for the number of edges
of a graph `H`, and `G[S]` for the subgraph induced on `S`, whose vertex set is
`S` and whose edge set is exactly the edges of `G` with both endpoints in `S`.

The frozen target is the universal implication

> for every integer `n >= 1` and every finite simple graph `G` with
> `|V(G)| = n`: if for every subset `S` of `V(G)` with `|S| >= floor(n/2)` the
> induced subgraph `G[S]` satisfies `50 * e(G[S]) > n^2`, then there exist
> three distinct vertices of `G` that are pairwise adjacent.

Every symbol is pinned:

- `n` is the order of the whole graph `G`, fixed before the hypothesis is read.
  The same `n` appears in the vertex threshold `floor(n/2)` and in the edge
  bound `n^2/50`. It is never `|S|`.
- The vertex threshold is **non-strict**: `|S| >= floor(n/2)`, with
  `floor(n/2) = (n - (n mod 2))/2`.
- The edge bound is **strict**: `e(G[S]) > n^2/50`. It is decided over `Z` as
  `50 * e(G[S]) > n^2`, so `n^2/50` never has to be represented.
- The constant `50` is pinned and is not a parameter.
- "Contains a triangle" means a `K_3` subgraph: three distinct pairwise
  adjacent vertices.

There is no asymptotic quantifier in the frozen target, so no epsilon form is
needed. The planning dossier's statement carries none either; whether the
original source restricts to sufficiently large `n` is exactly the mapping
question recorded in section 4 and cannot be settled before acquisition.

The planning dossier's result shape was "proof, counterexample, or improved
constant". Under cross-cutting rule 1 that disjunction is not a target. The
improved-constant disjunct is removed: replacing `50` by an unknown `c` is a
different frozen target needing its own problem definition. Proof and
counterexample both remain acceptable *outcomes* of this one target, which is
why `problem_type` is `explore` rather than `prove`.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| graph | finite, simple, undirected, unweighted; `n = card(V(G)) >= 1` | multigraph, digraph, hypergraph, infinite graph, weighted graph, the order-zero graph |
| `n` | the order of the whole graph `G`, appearing in both `floor(n/2)` and `n^2/50` | the order of the induced subgraph, giving the weaker local bound `card(S)^2/50` |
| induced subgraph on `S` | `G[S]`: vertex set `S`, plus every edge of `G` with both ends in `S` | an arbitrary (non-induced) subgraph on `S`; a subgraph selected by an edge count rather than a vertex count |
| "on at least `floor(n/2)` vertices" | non-strict, `card(S) >= floor(n/2)`, integer floor | `card(S) > n/2`; `card(S) >= ceil(n/2)`; `card(S) = floor(n/2)` exactly; `card(S) >= n/2` as a rational threshold |
| "more than `n^2/50` edges" | strict, `e(G[S]) > n^2/50`, decided as `50 * e(G[S]) > n^2` over `Z` | `e(G[S]) >= n^2/50`; `e(G[S]) >= ceil(n^2/50)`; the same comparison evaluated in floating point |
| the constant `50` | pinned; part of the statement | a free parameter `c`, i.e. the improved-constant target |
| contains a triangle | three distinct pairwise adjacent vertices (`K_3` subgraph); induced and non-induced coincide for `K_3` | contains an odd cycle (bipartiteness); a closed walk of length three; a triangle in the complement; a subdivision of `K_3` |
| the question mark in the planning statement | frozen as the implication in the affirmative direction | the meta-disjunction "prove or refute or improve"; `problem_type explore` keeps a refutation acceptable without making the target a disjunction |
| blow-up of `C_5` | the balanced blow-up `B(m)`: parts `V_1,...,V_5` of size `m`, complete bipartite between cyclically consecutive parts, empty inside each part | the lexicographic product `C_5[K_m]`, which has triangles inside each part and so is not triangle-free; an unbalanced blow-up (admitted separately in section 7 as its own family) |
| Petersen graph | the Kneser graph `K(5,2)`: vertices the 2-element subsets of `{1,...,5}`, adjacent iff disjoint | any 3-regular girth-5 graph; the Desargues graph; `K(6,2)` |
| `e(G[S])` for `S` empty | `0`; admissible when `floor(n/2) = 0` | treating the empty set as inadmissible, which would change the small-`n` edge cases |

Two consequences of these definitions are used throughout and are recorded as
lemmas in the intake file rather than assumed silently.

**Superset monotonicity.** If `S` is contained in `T` then
`e(G[S]) <= e(G[T])`. Hence the minimum of `e(G[S])` over all `S` with
`|S| >= t` is attained at some `S` with `|S| = t`, and the frozen hypothesis is
equivalent to its restriction to subsets of size exactly `floor(n/2)`. This is
what makes the bounded slice finite in a controlled way.

**Independence blocks the hypothesis.** If `alpha(G) >= floor(n/2)` then some
admissible `S` is independent, so `e(G[S]) = 0` and `50 * 0 > n^2` fails for
every `n >= 1`. Every graph satisfying the hypothesis therefore has
`alpha(G) < floor(n/2)`, and the implication is vacuously true for all others.

## 3. Formalization and quantifiers

```
forall n : Z, n >= 1 ->
  forall G a finite simple undirected graph with |V(G)| = n,
    (forall S subset of V(G), |S| >= floor(n/2)
        -> 50 * edge_count(induced(G, S)) > n^2)
    -> exists u v w in V(G), u, v, w pairwise distinct
                             and pairwise adjacent in G
```

Quantifier order, exactly as in the intake file:

1. `forall n` an integer with `n >= 1`.
2. `forall G` a finite simple undirected graph with exactly `n` vertices.
3. `forall S` a subset of `V(G)` with `|S| >= floor(n/2)` — inside the
   hypothesis, so a single admissible `S` with `50 * e(G[S]) <= n^2` discharges
   the whole implication for that `G`.
4. `exists u, v, w` three distinct pairwise adjacent vertices — the conclusion.

`formal_language` is `typed_informal_math`, `version` 1, `approval_status`
`proposed`. Human approval of the semantic alignment is still required and is
not implied by this file.

The negation, which is what the bounded slice actually searches for, is: there
exist `n >= 1` and a triangle-free `G` of order `n` such that
`50 * e(G[S]) > n^2` for every `S` with `|S| >= floor(n/2)`. By superset
monotonicity that is equivalent to
`50 * min{ e(G[S]) : |S| = floor(n/2) } > n^2`.

## 4. Semantic alignment to the source statement

**Quantifier mapping.** `n` maps to the integer order of the whole graph; `G`
to a finite simple graph on exactly `n` vertices; `S` to a universally
quantified admissible vertex subset in the hypothesis; the triangle to an
existentially quantified triple in the conclusion. The planning statement's
question mark maps to the affirmative implication, with `explore` preserving a
refutation as an outcome.

**Definition mapping.** "Induced subgraph on at least `floor(n/2)` vertices"
maps to `G[S]` for every `S` with `|S| >= floor(n/2)`, non-strict on the count.
"More than `n^2/50` edges" maps to the strict integer comparison
`50 * e(G[S]) > n^2`. "Blow-up of `C_5`" maps to the balanced blow-up `B(m)`,
not the lexicographic product. "Petersen graph" maps to `K(5,2)`.

**Assumption delta.**

- The planning statement is a question; the frozen target is the universal
  implication with `50` and `floor(n/2)` both pinned.
- The improved-constant disjunct of the planning result shape is removed under
  cross-cutting rule 1.
- The frozen target quantifies over all `n >= 1` with no sufficiently-large-`n`
  clause. Whether the original source states it for all `n` or asymptotically
  cannot be decided before the catalogue entry and the original Erdos source
  are acquired.
- Order zero is excluded so that `n^2/50` is positive and the hypothesis is
  non-degenerate.
- Flag-algebra and SDP exploration, named in the planning dossier as a fit
  reason, is admitted as exploration-only and never as a bound.

**Edge-case delta.**

- For `n = 1, 2, 3` the threshold is `0` or `1`, an empty or singleton `S` has
  zero edges, and `50 * 0 > n^2` fails: the implication is vacuously true.
- Whenever `alpha(G) >= floor(n/2)` the hypothesis fails, so the implication is
  vacuous; a counterexample needs `alpha(G) < floor(n/2)`.
- By superset monotonicity only subsets of size exactly `floor(n/2)` need
  checking.
- At `n = 10` the bound `n^2/50` is exactly `2`, so a triangle-free graph of
  order 10 whose every 5-vertex induced subgraph has at least 3 edges would be
  a counterexample. Both named boundary constructions sit at exactly `2` there.
- `S` may be empty when `floor(n/2) = 0`, and the empty graph has `0` edges.

**Strength relation: `unresolved`.** The frozen target is not labelled
`equivalent`, because no primary source has been acquired and the spec forbids
`equivalent` without a quoted acquired source. It is not labelled `weaker`
either: the all-`n` form is *stronger* than any sufficiently-large-`n` form,
while dropping the improved-constant disjunct makes the intake narrower than
the planning result shape, so the relation genuinely runs in both directions
and cannot be settled until the source statement is in hand. `unresolved` is
the honest value and resolving it is the first item in section 13.

## 5. Provenance and acquisition plan

No acquisition is performed by this dossier. Under ADR-0050 acquisition is
public, unauthenticated, human-planned, exact-URL, one request at a time, and
separately authorized. Every row is `pending_acquisition` with applicability
`not_assessed`.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Erdos Problems catalogue entry 128 | `https://www.erdosproblems.com/128` — the whole single HTML page, including the status label, the statement rendering, the claimed-proof link, and the reference list | settles C1 (the `FALSIFIABLE` label), C2 (the claimed proof), C3 (the reported best constant and the named boundary constructions), and C4 (which statement form the catalogue renders) | pending_acquisition, applicability not_assessed |
| The claimed-proof artifact linked from that entry | exact URL to be read off the acquired catalogue page; deliberately not guessed here, since guessing a URL is not human-planned acquisition | settles C2 | pending_acquisition, applicability not_assessed |
| The original Erdos source for the problem | paper, page, and problem number to be identified from the acquired entry's reference list | settles C4, in particular whether the source quantifies over all `n` or over sufficiently large `n`, which is what makes the strength relation `unresolved` | pending_acquisition, applicability not_assessed |
| Post-2025 literature covering the statement and the claim thread | no exact locator can be written before the catalogue entry and its references are acquired; recorded as an ADR-0055 obligation rather than a URL | settles C1 and C2 | pending_acquisition, applicability not_assessed |
| OEIS A006785, triangle-free graphs on `n` unlabeled nodes | `https://oeis.org/A006785` | settles C5, the per-order class counts used as a generator self-check; the sweep recomputes the counts, so this is a convenience and not a dependency | pending_acquisition, applicability not_assessed |

## 6. Prior-status claims to re-check

Each of the following is inherited from the planning notes, is **untrusted**,
and must be covered by the ADR-0055 pre-research novelty re-check bound to this
problem's subject hash immediately before research starts. None of them creates
open status, refuted status, novelty, significance, applicability, graph
admission, or warrant.

- **C1 — status label.** The planning notes report that the catalogue labels
  entry 128 `FALSIFIABLE` rather than `OPEN`. The page is not acquired and the
  label's meaning is not established. This is load-bearing: if `FALSIFIABLE`
  means the statement is known false, the frozen target may already be settled,
  and the correct next action is acquisition and re-check, not search.
- **C2 — claimed proof.** The planning notes report that the entry lists a
  claimed proof. Neither the claim nor its thread nor any post-2025 literature
  has been acquired or reviewed. The claim may resolve the frozen target, may
  address a different statement, or may be wrong; this dossier decides none of
  those. Also load-bearing, and for the same reason.
- **C3 — best constant and boundary examples.** The planning notes report that
  `50` is best possible, with `C_5` blow-ups and the Petersen graph as the
  boundary examples, and that earlier constants exist. The slice recomputes the
  relevant edge counts as exact integers from the constructions themselves; a
  mismatch is recorded as a source discrepancy, never silently reconciled.
- **C4 — statement form.** Whether the source states the implication for all
  `n`, for sufficiently large `n`, or with a different threshold is unknown.
- **C5 — enumeration counts.** The reported numbers of isomorphism classes of
  triangle-free simple graphs for orders 1 to 12 — `1, 2, 3, 7, 14, 38, 107,
  410, 1897, 12172, 105071, 1262180` — are untrusted. The sweep recomputes each
  and treats disagreement as a generator fault that halts the run.

The acquisition plan in section 5 names, per row, which of C1 to C5 that row
would settle. C1 and C2 together are the gate: they are the reason the planning
dossier ranks A1 second rather than first, and no search result from this
target may be reported before they are re-checked.

## 7. Bounded first slice

**Inputs.** None external. Three generators, all constructed locally:

1. **Balanced `C_5` blow-ups.** `B(m)` for `m = 1,...,20`, giving `n = 5m` up
   to 100. Adjacency built directly from the frozen definition.
2. **Unbalanced `C_5` blow-ups.** All part-size vectors `(a_1,...,a_5)` of
   non-negative integers with `sum a_i = n`, for every `n <= 30`. This is
   `C(n+4,4)` vectors per order, at most 46376 at `n = 30`, so the family is
   swept exhaustively rather than sampled.
3. **The Petersen graph**, as `K(5,2)`, given explicitly.
4. **An exhaustive canonical sweep** of triangle-free simple graphs, one
   representative per isomorphism class, orders 1 to 12.

**Exact algorithms and arithmetic.** All integer, all standard library.

- Adjacency as bitsets, one machine integer per vertex.
- Triangle test: for each edge `uv`, `adj[u] & adj[v] != 0`. Zero floats.
- `minlocal(G) = min{ e(G[S]) : |S| = floor(n/2) }`, justified by superset
  monotonicity. Computed by exhaustive enumeration of the `C(n, floor(n/2))`
  subsets in a revolving-door order, so consecutive subsets differ in one
  vertex and the edge count updates by an exact integer popcount difference.
  The subset factor is `C(12,6) = 924` and `C(13,6) = 1716`.
- Hypothesis test: `50 * minlocal(G) > n^2` over `Z`. `n^2/50` is never
  represented as a number.
- `alpha(G)` exactly by integer branch and bound, used as a pre-filter: any `G`
  with `alpha(G) >= floor(n/2)` is discharged without touching `minlocal`.
- `c(n) = max{ minlocal(G)/n^2 : G triangle-free of order n }`, stored as a
  reduced exact fraction with the argmax graph. `c(n) > 1/50` for any surveyed
  `n` **is** a counterexample; `c(n) <= 1/50` is bounded evidence and nothing
  more.

**Search envelope and its size.** Exhaustive over triangle-free isomorphism
classes for orders 1 to 12; order 13 attempted under a frozen node budget and
abandoned with a recorded frontier if the budget is reached. The dominant cost
is class count times subset factor: about `1.26e6 * 924 ≈ 1.2e9` elementary
integer steps at order 12 before the `alpha` pre-filter, and about
`2.08e7 * 1716 ≈ 3.6e10` at order 13, which is why 13 is budgeted rather than
promised.

**Where exhaustion stops being feasible.** At order 14 and above. Two factors
compound: the reported class count rises from about `2.1e7` at order 13 to
about `4.7e8` at order 14 and about `1.4e10` at order 15, and the subset factor
rises to `C(14,7) = 3432`. The product exceeds `1e12` elementary steps at order
14 even with the `alpha` pre-filter, and the generation itself no longer fits a
bounded offline run. Orders 14 and above are therefore explicitly **not**
covered by this slice, and no statement about them may be derived from it.

**Canonicalization and symmetry quotient.** "Unlabeled" means exactly one
representative per isomorphism class. Candidate generation uses `nauty`'s
`geng -t`, which emits canonical triangle-free `graph6` records. That generator
is an **untrusted candidate producer** and is not a pinned repository
dependency (section 12). Its output is re-verified in repository: every record
is decoded independently, re-checked triangle-free exactly, and every reported
witness is recomputed from the decoded adjacency. Two independent checks guard
coverage — the recomputed per-order class counts are compared against C5, and
an in-repository orderly-generation run reproduces the class sets for orders up
to 9 — but exhaustiveness remains a property of the generator, not of the
verifier, and the coverage claim is recorded as generator-dependent. This
follows the Graffiti-322 precedent in `work/graffiti-322-20260821-round2/`.

**Exhaustive versus parametric.** Generators 2 and 4 are exhaustive over their
stated ranges. Generator 1 is a parametric family over `m = 1,...,20` and is
not exhaustive over blow-ups; generator 2 is what covers blow-ups exhaustively
at small orders. Nothing is randomly sampled, so there is no statistical claim
anywhere in the slice.

**Boundary reproduction, stated as a target rather than a claim.** The slice
computes, and does not assume, the exact minima. For the balanced blow-up with
`n = 10t` the expected value is `minlocal(B(2t)) = 2t^2 = n^2/50`, attained for
instance by two non-consecutive full parts plus `t` vertices of a third part.
For the Petersen graph at `n = 10` the expected value is `minlocal = 2`, which
is exactly `n^2/50`. In both cases the graph is triangle-free and the strict
inequality `50 * minlocal > n^2` fails by the smallest possible margin — one
edge. If those computed values match, the slice has established, exactly and
for those specific orders, that the strict "more than" in the frozen statement
cannot be weakened to "at least". If they do not match, the discrepancy is
recorded against C3 and the constructions are re-derived; the reported values
are never trusted over the computed ones.

**Boundary of the claim the slice can support.**

- If a triangle-free graph satisfying the frozen hypothesis is found, the
  universal implication is **refuted outright**. One exact object suffices, and
  it is fully replayable.
- If none is found, the slice supports exactly this: no triangle-free
  isomorphism class of order at most `K` (the highest exhausted order) contains
  a graph satisfying the frozen hypothesis, subject to the generator-dependent
  coverage caveat. It entails nothing about order `K+1` or above, nothing about
  the universal implication, and nothing about the constant `50` being best
  possible in general.
- The exact boundary computations entail sharpness **at the computed orders
  only**. They do not establish the asymptotic optimality of `50`.
- The `c(n)` table is data. A monotone-looking trend in it is not a bound.

## 8. Certificate and verifier contract

| Result shape | Certificate format | Independent verifier |
|---|---|---|
| Counterexample: a triangle-free `G` satisfying the hypothesis | the order `n`, the adjacency as an explicit edge list plus its `graph6` encoding, the value `minlocal(G)` as an exact integer, and the witness subset attaining it | a second implementation rebuilds the adjacency from the edge list alone, re-checks triangle-freeness edge by edge, recomputes `minlocal` by full enumeration of all `C(n, floor(n/2))` subsets without the revolving-door optimization, and re-evaluates `50 * minlocal > n^2` over `Z` |
| Exact boundary sharpness at a given order | the construction parameters (`m`, or the part-size vector, or `K(5,2)`), the derived adjacency, `minlocal` as an exact integer, `n^2` as an exact integer, and the attaining subset | the verifier rebuilds the graph from the parameters only, recomputes `minlocal` by full enumeration, and confirms `50 * minlocal = n^2` exactly (or reports the exact difference) |
| Bounded exhaustion to order `K` | the per-order table of class count, `alpha`-filtered count, `c(n)` as a reduced fraction, and the argmax graph in `graph6`; the generator invocation and its output hash; the frozen enumeration order and node budget | a replay recomputes every per-order class count and every `c(n)` from the recorded generator output, and separately regenerates orders up to 9 in repository and compares class sets. A mismatch is a fault, not a correction |
| Universal proof | a written derivation with every step reduced to the frozen definitions and the two recorded lemmas | human review, plus formal checking only if the whole statement fits one sealed Phase 3B submission (section 12 says it does not) |

**Refused as a certificate, without exception.**

- Any floating-point number, including a flag-algebra or SDP bound, a numerical
  eigenvalue, or a float comparison against `n^2/50`. Exploration-only,
  labelled as such wherever it appears.
- A model's assertion that the implication holds or fails.
- An unreplayed third-party program's output. `nauty` may *produce* candidates;
  only the in-repository exact re-check certifies any of them, and `nauty`'s
  exhaustiveness is recorded as an assumption rather than certified.
- **Failure of a search.** Completing the sweep to order 12 with no witness
  certifies a statement about orders up to 12 and nothing else. It is never a
  proof of the universal implication, and no report may present it as one.
- A `c(n)` table that stays below `1/50`. That is evidence about the surveyed
  orders, not a bound on `c(n)` for larger `n`.

## 9. Useful negative outcomes

Nothing found is still a retained result, preserved machine-readably per the
engineering rules.

- **The exhausted frontier.** The highest order `K` swept exhaustively, with
  per-order class counts, `alpha`-filtered counts, and elapsed node counts.
- **The exact `c(n)` table.** For each surveyed order, the maximum of
  `minlocal(G)/n^2` over triangle-free `G` as a reduced fraction, with the
  argmax graph stored in `graph6` and as an edge list. This is the finite
  shadow of the constant and is the single most reusable artifact of the slice:
  it is exactly the invariant a future improved-constant target would need, and
  it is retained whether or not a counterexample appears.
- **The exact sharpness record.** The computed `minlocal` values for the
  balanced blow-ups, the unbalanced blow-up family, and the Petersen graph,
  with the attaining subsets. Retained even when they merely confirm C3.
- **The exclusion set.** Per order, the count and structural profile of classes
  discharged by the `alpha(G) >= floor(n/2)` pre-filter, with the pre-filter's
  own proof recorded as a discharged obligation.
- **Refuted routes.** Any attempted stability or reduction argument that fails,
  stored with the exact instance that breaks it, in the manner of the
  `prior_parity_route_gap` record in the Graffiti-322 precedent. In particular,
  if the flag-algebra route is attempted at all, its output is filed as
  exploration-only with the refusal reason attached.
- **Source discrepancies.** Any mismatch between a recomputed value and C3 or
  C5, retained as an open discrepancy rather than resolved in favour of either
  side.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. `version` 1, `phase`
`exploratory`.

Metrics:

- `triangle_free_classes_exhausted`
- `hypothesis_satisfying_graphs_found`
- `boundary_constructions_reproduced_exactly`
- `exact_local_density_records_stored`
- `generator_count_mismatches`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria:

- `an exact triangle-free graph satisfying the frozen hypothesis, refuting the
  universal implication`
- `a rigorous proof of the universal implication for every finite simple graph`
- `or an explicit unresolved outcome recording the highest exhausted order, the
  exact per-order table of c(n) = max over triangle-free G of order n of
  minlocal(G)/n^2 as reduced fractions, and the smallest remaining obligation`

Stopping rules:

- `stop on an exact triangle-free graph satisfying the frozen hypothesis`
- `stop on a rigorous derivation covering every finite simple graph in scope`
- `stop when fresh model spend reaches USD 20`
- `stop when two consecutive review points close no obligation and raise no
  exhausted order`
- `never promote a completed bounded sweep to the universal implication; record
  the exhausted order and the exact c(n) table instead`
- `halt and report a generator fault if any recomputed isomorphism-class count
  disagrees with the recorded count`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The problem may already be settled (C1, C2) | the catalogue label is reported as `FALSIFIABLE` and a claimed proof is listed; spending a slice on a closed problem is the single largest waste in this dossier | C1 and C2 are recorded as untrusted status claims, are named in the acquisition plan with the exact page that would settle them, and the ADR-0055 pre-research re-check is a hard gate before any search runs |
| Reading `n` as `card(S)` | the hypothesis becomes far weaker and counterexamples appear that are artifacts of the misreading | `order_scope_of_n` is a definitional assumption; the rejected reading is in the section 2 table; the implementation takes `n` as a separate argument from the subset |
| Weakening "more than" to "at least" | both named boundary constructions sit at exactly `n^2/50`, so this single character flips them from boundary examples into counterexamples | strictness is a definitional assumption; the comparison is a single integer expression `50*e > n^2`; the boundary reproduction step exists precisely to make the one-edge margin visible in every run |
| Floating-point comparison against `n^2/50` | `n^2/50` is not representable; a rounding error at the boundary silently manufactures or destroys a counterexample exactly at the interesting orders | the comparison never leaves `Z`; `exact_arithmetic_requirement` is an assumption; floats are refused as certificates in section 8 |
| Generator-dependent coverage | exhaustiveness of the sweep is `nauty`'s property, not the verifier's; a silently incomplete generation reads as a clean negative result | class counts recomputed and compared against C5; independent in-repository regeneration for orders up to 9; the coverage claim is labelled generator-dependent; a count mismatch halts the run |
| Promoting the sweep to the universal statement | the most likely way this target produces a false result, and the exact failure the planning dossier warns about | a stopping rule forbids it; section 8 lists search failure as a refused certificate; the reported artifact is the exhausted order plus the `c(n)` table, never a bound |
| Flag-algebra or SDP drift onto the trust path | the planning dossier names it as a fit reason, so it will be proposed; its output is floating point | `flag_algebra_sdp_route_refused` is a recorded refused route; the repository owner rejects floating-point solvers outright; ADR-0035 admits no solver; any such output is labelled exploration-only |
| Order 13 partially swept and reported as swept | a budget-abandoned order is easy to mis-summarise as complete | the frontier record stores the highest **exhausted** order separately from the highest **attempted** order, and the node budget and abandonment point are part of the certificate |
| Small-`n` vacuity mistaken for evidence | orders 1 to 9 are largely discharged vacuously by the `alpha` filter, which inflates a "swept 12 orders" summary | the per-order table records the `alpha`-filtered count separately, so vacuous orders are visible as vacuous |

## 12. Capability check

**Covered by existing capabilities.**

- ADR-0039 declarative problem intake: this dossier's intake file is exactly
  that artifact, and `problem validate` plus `problem demo` confirm it creates
  no trust (`logical_status unknown`, novelty and significance `not_assessed`,
  zero warrants).
- Exact integer and rational arithmetic with the standard library only, as used
  by the Graffiti-322 precedent in `work/graffiti-322-20260821-round2/`. The
  whole slice needs nothing beyond `int`, `Fraction`, and bit operations.
- ADR-0055 two-fresh-novelty-rechecks: the mechanism that gates C1 and C2
  before research starts, and the mechanism that would gate any announcement.
- Phase 3A research memory for machine-readable retention of the frontier,
  the `c(n)` table, and failed routes, per the engineering rule on preserving
  failures.
- ADR-0047 bounded central-lead runtime, if a model is involved at all. The
  target is frozen, replay is model-free, and no warrant or obligation
  discharge is producible there — which is the correct posture for this slice.
- ADR-0036 publication projection, if anything is written up. A claim from this
  slice computes to `Conjecture` absent a kernel-checked attestation, which is
  the desired outcome and needs no new decision.

**Would require a new ADR.**

- **Admitting `nauty`/`geng` as a coverage-bearing dependency.** The binary
  exists in the local environment but is not pinned, digest-recorded, or
  licence-recorded in this repository, and the engineering rules require both
  before a dependency is added. Using it as the basis of an exhaustiveness
  claim needs an ADR covering the pin, the licence, the invocation bound, and
  the treatment of its completeness as an assumption. An in-repository orderly
  generator is ordinary code and needs no ADR to *write*; declaring its output
  exhaustive on a trust path is the part that does.
- **Any exact sum-of-squares or rational flag-algebra machinery.** None exists.
  ADR-0035 adopted no solver and records that no interval or
  residual-reconstruction path exists. A floating-point SDP is refused outright
  rather than gated, so there is nothing to activate; an exact replacement in
  graph profile space would be a new capability and a new ADR.
- **Formalizing the universal implication.** The sealed Phase 3B runtime freezes
  one theorem per submission and ADR-0040's repair loop cannot change the
  statement, hypotheses, or imports. A multi-lemma development with graph-theory
  library dependencies is outside the ADR-0016 and ADR-0040 bounds and would
  need its own ADR.
- **Acquisition of any row in section 5.** ADR-0050 human-planned exact-URL
  acquisition, separately authorized, one request at a time. Not performed here.
- **Any Crossref discovery query** over these terms would run under ADR-0051,
  is inspiration-only, and does not itself perform or satisfy the ADR-0055
  re-check.

No new capability is assumed by this dossier. The bounded slice as described
runs on existing exact-arithmetic capability plus one untrusted candidate
generator whose admission is flagged above.

## 13. Open questions before intake

1. **Does C1 or C2 already settle this?** The catalogue label and the claimed
   proof must be acquired and re-checked first. If either resolves the frozen
   target, the correct outcome of this dossier is a recorded closure, not a
   search. This is the gating question and the operator should answer it before
   authorizing any compute.
2. **All `n` or sufficiently large `n`?** The strength relation is `unresolved`
   for exactly this reason. If the source is asymptotic, the frozen all-`n`
   target is strictly stronger and small-order sweeps are less informative than
   they look; the operator may then prefer a re-freeze.
3. **Is `nauty` admitted, or is an in-repository generator required?** This
   decides whether the sweep's coverage claim is generator-dependent or
   self-contained, and it needs a decision before the slice is scheduled.
4. **Is order 13 in scope?** It costs roughly thirty times order 12. The frozen
   envelope is 1 to 12 exhaustive with 13 budgeted; the operator may cut 13
   entirely or raise the budget.
5. **Should the improved-constant target be opened as a sibling?** The `c(n)`
   table this slice produces is exactly its input. It must be its own problem
   definition; it is not opened here.
6. **Confirm the `20` USD spend cap** and the review-point cadence used by the
   stagnation rule.

Human approval of the semantic alignment in sections 3 and 4 remains required
and is not granted by this file.
