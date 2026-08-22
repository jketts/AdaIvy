# C5. Erdos #982 — convex-polygon vertex distances — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item C5 (tier C)
**Declared domain:** discrete-geometry
**Intake file:** docs/research-targets/intake/c5-erdos-982-convex-distinct-distances-v1.json
**Frozen in one line:** For every `n >= 3` and every set of `n` points in the
plane in strictly convex position, at least one of the points has at least
`floor(n/2)` distinct distances to the other `n - 1` points.

This is a scoped intake package and nothing more. It does not approve a
formalization, establish that Erdos #982 is open, authorize source acquisition,
assess novelty, significance, or source applicability, create mathematical
warrant, admit anything to a claim graph, or activate a capability. Novelty,
significance, and source applicability are `not_assessed`. The catalogue status
label and the claimed proof described in section 6 are untrusted candidates that
the ADR-0055 pre-research novelty re-check must settle before any work starts,
and if the claimed proof stands the target is void.

## 1. Frozen target

Let `n` be an integer with `n >= 3`. Let `P = {p_1,...,p_n}` be a set of `n`
distinct points of the Euclidean plane `R^2`. Say `P` is in **strictly convex
position** if every `p_i` is a vertex of the convex hull of `P` and no three
points of `P` are collinear; equivalently, `P` is exactly the vertex set of a
convex `n`-gon.

For `p` in `P`, write

`D(P, p) = { dist(p, q) : q in P, q != p }`

for the **set** of distances from `p` to the other points, where `dist` is the
Euclidean distance. `D(P, p)` is a set of positive reals, so `|D(P, p)|` counts
distinct values and not multiplicities; it ranges over `1 <= |D(P,p)| <= n - 1`.

The frozen target is the following universal statement.

> For every integer `n >= 3` and every set `P` of `n` distinct points of `R^2`
> in strictly convex position, there exists `p` in `P` with
> `|D(P, p)| >= floor(n/2)`.

Quantifiers, fully explicit:

`forall n in Z, n >= 3 :`
`forall P subset R^2 with |P| = n and P in strictly convex position :`
`exists p in P : |{ dist(p,q) : q in P, q != p }| >= floor(n/2)`

Equivalently, writing `M(P) = max_{p in P} |D(P, p)|`, the statement is
`M(P) >= floor(n/2)` for every such `P`.

Its negation, which is what a counterexample must exhibit, is:

`exists n >= 3, exists P in strictly convex position with |P| = n, such that`
`forall p in P : |D(P,p)| <= floor(n/2) - 1`

That is, a counterexample must make **every** vertex deficient simultaneously.
Note that for `n = 3` and `n = 4` the requirement `|D(P,p)| <= floor(n/2) - 1`
reads `<= 0` and `<= 0` respectively for `n = 3`, and `<= 1` for `n = 4`; since
`|D(P,p)| >= 1` always, `n = 3` admits no counterexample at all, and `n = 4`
would need every vertex equidistant from the other three, forcing all six
pairwise distances equal, which is impossible in the plane for four points.

**Sharpness.** The regular `n`-gon attains equality: every one of its vertices
has exactly `floor(n/2)` distinct distances, so the bound `floor(n/2)` cannot be
raised to `floor(n/2) + 1`. This is verified exactly in section 2.1 rather than
inherited from the planning notes.

**Why this reading of the planning item.** The planning dossier states item C5
as a question — "is there a vertex having at least `floor(n/2)` distinct
distances to the other vertices?" — with the result shape "proof,
counterexample, or improved guaranteed distance bound". A question plus a
three-way result shape is not a target. The universal statement above is frozen
as the target; the problem type is `explore` because both a proof and an exact
counterexample are acceptable outcomes of the same frozen statement, whereas
"improved guaranteed bound" is a different statement and is not frozen here.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| "form a convex polygon" | `P` is exactly the vertex set of a convex `n`-gon: every point is a hull vertex and no three points are collinear (strictly convex position) | "in convex position" allowing collinear triples, i.e. points on the hull boundary that are not vertices; a convex polygon with `P` merely contained in it; a convex region containing `P`; a simple polygon |
| why collinear triples are excluded | a convex polygon's vertex set has no three collinear members, since a point interior to an edge is a boundary point and not a vertex; admitting them would change which point sets are in scope | admitting them silently |
| direction of that choice | the frozen statement quantifies over **fewer** configurations than the collinear-admitting version, so the frozen statement is **implied by** it and is the weaker of the two; a counterexample containing a collinear triple therefore does **not** refute the frozen target | treating a degenerate counterexample as a refutation |
| `n >= 3` | the frozen lower bound on `n`; a convex polygon needs at least three vertices | `n >= 1` or `n >= 2` (no polygon); `n >= 4`; `n >= 5`; an unstated threshold |
| distinct distances from `p` | `|D(P,p)|`, the cardinality of the **set** of Euclidean distances from `p` to the other `n - 1` points; equal distances collapse to one value | the multiset size, which is always `n - 1`; the number of distinct **squared** distances stated as a different quantity (it is the same number, see 2.2); the number of distinct distances among **all** pairs of `P` |
| which points are counted | all `n - 1` other points of `P`, including the two neighbours of `p` on the polygon | only non-adjacent vertices, i.e. diagonals only; only the neighbours; distances to the centroid or to edges |
| the quantifier over vertices | **existential**: some `p` in `P` attains the bound, i.e. `M(P) >= floor(n/2)` | **universal**: every `p` attains it. That reading is strictly stronger and is **false**; section 2.3 exhibits an exact integer-coordinate strictly convex hexagon with a vertex having only 2 distinct distances while `floor(6/2) = 3` |
| `floor(n/2)` | integer floor: `floor(n/2) = (n-1)/2` for odd `n`, `n/2` for even `n` | `ceil(n/2)`; `n/2` as a rational; `(n-1)/2`; `floor(n/2) + 1` |
| "at least" | `>=`, so the regular `n`-gon with exactly `floor(n/2)` satisfies the statement | `>`, which the regular `n`-gon would refute |
| Erdos #982 vs the classical convex-polygon result | the frozen target is the **per-vertex** statement: one vertex sees many distinct distances | the **total** statement, that a convex `n`-gon determines at least `floor(n/2)` distinct distances overall. The total statement is a weaker consequence and is classical; conflating the two would misstate what is open |
| the frozen equivalence for classification | plane **similarity**: maps `x -> c Q x + t` with `c > 0` real, `Q` a real orthogonal `2 x 2` matrix (determinant `+1` or `-1`, so reflections are included), `t` in `R^2` | affine equivalence, which does **not** preserve distance ratios and therefore does not preserve `|D(P,p)|` — the unit square and a `1 x 2` rectangle are affinely equivalent with per-vertex counts 2 and 3; isometry alone, which splits similar configurations without distinguishing any invariant; order type or combinatorial equivalence; projective equivalence |
| exact representation of a configuration | coordinates in `Q^2`, or in `K^2` for a number field `K = Q(alpha)` with `alpha` given by an exact minimal polynomial and an isolating rational interval; no decimal, no float | decimal or floating-point coordinates; coordinates given to a stated precision; coordinates as symbolic expressions without a normal form |
| the rational-grid family | for a frozen `m`, the point sets contained in `{0,1,...,m}^2`, i.e. subsets of the `(m+1)^2` lattice points | all rational configurations; all algebraic configurations; all real configurations |
| exhaustion of that family | a statement about that finite family alone | evidence for the universal target; see the forbidden-inference row in the intake file |

### 2.1 The regular `n`-gon has exactly `floor(n/2)` distances at each vertex

This is the sharpness example, so it is verified rather than cited.

Place the regular `n`-gon with vertices `v_k = (R cos(2 pi k / n), R sin(2 pi k
/ n))` for `k = 0,...,n-1`, `R > 0`. The distance between `v_0` and `v_k` is the
chord subtending a central angle `2 pi k / n`, hence

`dist(v_0, v_k) = 2 R sin(pi k / n)` for `k = 1,...,n-1`.

Two facts determine the count.

1. *Symmetry.* `sin(pi k / n) = sin(pi (n - k) / n)`, so `k` and `n - k` give
   the same distance. Hence every distance is realized by some
   `k` in `{1,...,floor(n/2)}`.
2. *Strict monotonicity.* For `1 <= k <= floor(n/2)` the argument `pi k / n`
   lies in `(0, pi/2]`, and `sin` is strictly increasing on `[0, pi/2]`.
   Therefore `2 R sin(pi k / n)` is strictly increasing in `k` on that range,
   so those `floor(n/2)` values are pairwise distinct.

Hence `|D(P, v_0)| = floor(n/2)` exactly, and by the rotational symmetry of the
polygon the same holds at every vertex. Consistency check on the multiplicities:
for odd `n`, `n - 1 = 2 floor(n/2)` and each of the `floor(n/2)` values occurs
twice; for even `n`, the value at `k = n/2` is the diameter and occurs once
while the other `n/2 - 1` values occur twice, giving `1 + 2(n/2 - 1) = n - 1`.
Both accounts close exactly.

So `M(P) = floor(n/2)` for the regular `n`-gon: the frozen statement holds with
equality, and no bound larger than `floor(n/2)` is true in general.

### 2.2 Distinct distances equal distinct squared distances

For nonnegative reals `a, b`, `a = b` iff `a^2 = b^2`. Distances are
nonnegative, so squaring is injective on them, and therefore

`|{ dist(p,q) : q in P, q != p }| = |{ dist(p,q)^2 : q in P, q != p }|`.

This is the whole reason the problem is exactly computable without square roots.
For `P subset Q^2` the squared distances are rationals, and after clearing
denominators, integers; equality is then decided by integer comparison. For
`P subset K^2` with `K = Q(alpha)` the squared distances are elements of `K` and
equality is decided by comparing normal forms in `Q[x]/(m(x))`. Note what is and
is not needed: the distinct-distance **count** needs only equality decisions,
never order decisions, so no real-root isolation is required for it. Order and
sign decisions are needed only for the convex-position test, which compares
orientation determinants against zero.

### 2.3 The universal-over-vertices reading is false: an exact witness

The rejected reading — that *every* vertex has at least `floor(n/2)` distinct
distances — is refuted by the following six integer points, taken in this
cyclic order:

`v = (0,0), p_1 = (5,0), p_2 = (12,5), p_3 = (5,12), p_4 = (0,13), p_5 = (-3,4)`

*Strictly convex position.* The consecutive orientation determinants
`cross(a,b,c) = (b_x - a_x)(c_y - a_y) - (b_y - a_y)(c_x - a_x)` around the
cycle are

`25, 84, 28, 48, 39, 20`

all strictly positive, so every turn is a left turn and all six points are hull
vertices in that order. Every one of the `C(6,3) = 20` orientation determinants
is nonzero, so no three of the six points are collinear. Hence the six points
are the vertex set of a strictly convex hexagon.

*The deficient vertex.* The squared distances from `v = (0,0)` are

`|p_1|^2 = 25, |p_2|^2 = 144 + 25 = 169, |p_3|^2 = 25 + 144 = 169,`
`|p_4|^2 = 169, |p_5|^2 = 9 + 16 = 25`

so `{25, 169}` and `|D(P, v)| = 2`, while `floor(6/2) = 3`. The construction is
transparent: `p_1` and `p_5` lie on the circle of radius 5 about `v`, and `p_2`,
`p_3`, `p_4` lie on the circle of radius 13 about `v`, both circles carrying
integer points, and the radii are arranged small-large-large-large-small around
the fan so that the chain still bulges outward.

*The frozen statement is unaffected.* The per-vertex counts of this
configuration are `2, 5, 5, 5, 5, 5`, so `M(P) = 5 >= 3` and the frozen
existential-over-vertices statement holds here comfortably. The witness refutes
only the rejected reading. It is recorded because the difference between "some
vertex" and "every vertex" is exactly the kind of single word that decides the
problem, and because it shows the rejected reading fails at the smallest even
`n` where it can fail rather than only asymptotically.

*Scope note.* The witness has coordinate box `[-3,12] x [0,13]`, so after
translation it needs a `16 x 14` lattice box. It does **not** lie in the `6 x 6`
lattice box that section 7 freezes for the exhaustive sweep. That is itself
informative about how severe the frozen box is, and section 7 says so.

## 3. Formalization and quantifiers

Formal language: `typed_informal_math`, version 1, approval status `proposed`.
Human approval of the semantic alignment in section 4 is still required and is
not implied by this document.

```
forall n : Z, n >= 3 ->
  forall P : FiniteSet(R^2),
    Card(P) = n
    and StrictlyConvexPosition(P)      -- every point a hull vertex,
                                       -- no three points collinear
    ->
    exists p in P,
      Card({ SquaredDist(p,q) : q in P, q != p }) >= floor(n/2)
```

`SquaredDist(p,q) = (p_x - q_x)^2 + (p_y - q_y)^2`. The formalization counts
distinct **squared** distances, which by section 2.2 is the same number as
distinct distances, and which removes square roots from the trust path
altogether.

Quantifier list, in the order a verifier consumes it:

1. `forall n` an integer with `n >= 3`. Unbounded; this is the reason no finite
   computation settles the target.
2. `forall P` a set of `n` distinct points of `R^2` in strictly convex position.
   Unbounded and uncountable; no enumeration reaches it.
3. `exists p in P`, a single vertex, chosen after `P`.
4. The inner cardinality is a finite count over the `n - 1` other points.

The two unbounded universal quantifiers are the whole difficulty. Any bounded
protocol in section 7 replaces quantifier 2 by a finite subfamily and must state
what that replacement does and does not entail; it never discharges
quantifier 1 or quantifier 2.

## 4. Semantic alignment to the source statement

**Quantifier mapping.**

- planning "any `n` distinct points in the plane that form a convex polygon" ->
  `forall n >= 3`, `forall P` with `|P| = n` in strictly convex position.
- planning "is there a vertex" -> `exists p in P`, existential over vertices,
  chosen after `P`.
- planning "having at least `floor(n/2)` distinct distances to the other
  vertices" -> `|{ SquaredDist(p,q) : q in P, q != p }| >= floor(n/2)`, over all
  `n - 1` other points.

**Definition mapping.**

- "form a convex polygon" -> `P` is exactly the vertex set of a convex `n`-gon:
  strictly convex position, no three collinear.
- "distinct distances" -> the cardinality of the set of distance values, not the
  multiset size.
- "the other vertices" -> all `n - 1` points of `P` other than `p`, adjacent and
  non-adjacent alike.
- "the regular polygon shows that `floor(n/2)` would be best possible" -> the
  regular `n`-gon has `M(P) = floor(n/2)` exactly, verified in section 2.1.
- "classify extremal small configurations up to an exact equivalence" -> the
  equivalence is frozen as plane similarity including reflections, with the
  exact test given in section 8.

**Assumption delta.**

- The planning item is a question with a three-way result shape; this definition
  freezes the universal statement itself, with both a proof and an exact
  counterexample admitted as outcomes. The third shape, "improved guaranteed
  distance bound", is a different statement and is not frozen here.
- Strict convexity with no three collinear points is imposed. The source phrase
  "form a convex polygon" is read that way and the reading is justified in
  section 2, but the source text has not been acquired, so the reading is a
  frozen decision rather than a quoted convention.
- `n >= 3` is imposed. The source's threshold is unknown until acquisition.
- The count is over all `n - 1` other vertices. No source text fixes this here.
- Nothing about the catalogue's `FALSIFIABLE` label or the claimed proof is
  assumed; see section 6.

**Edge-case delta.**

- `n = 3` admits no counterexample: `floor(3/2) - 1 = 0` and every vertex has at
  least one distance.
- `n = 4` admits no counterexample: it would require every vertex equidistant
  from the other three, forcing all six pairwise distances equal, which four
  points of the plane cannot do.
- Equality is attained by the regular `n`-gon for every `n >= 3`, so the
  statement is tight and "at least" cannot be strengthened to "more than".
- A counterexample must make **every** vertex deficient at once; a single
  deficient vertex is not a counterexample, and section 2.3 exhibits one.
- A configuration with a collinear triple is outside scope; if the acquired
  source turns out to admit such configurations, the target must be re-frozen,
  because the frozen statement is the weaker of the two.
- Similar configurations have identical per-vertex counts, so the classification
  in section 7 is well defined on similarity classes.

**Strength relation:** `unresolved`. The mapping from the catalogue's phrasing
to this formalization cannot be settled before the source is acquired: the
reading of "form a convex polygon", the threshold on `n`, and the exact bound
are frozen decisions here, not quoted conventions. It is `unresolved` rather
than `equivalent` because no primary source text has been acquired or
quoted in this task.

## 5. Provenance and acquisition plan

Every row is `pending_acquisition` with applicability `not_assessed`. No row has
been fetched, and this dossier authorizes no fetch. Under ADR-0050, acquisition
is human-planned, public-unauthenticated, exact-URL, and separately authorized.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Erdos Problems catalogue entry #982 | `https://www.erdosproblems.com/982`, the full entry including the status label, the bibliographic citation of the original Erdos source, and the reference for the claimed proof | settles claim T1 (the `FALSIFIABLE` label) and claim T2 (the claimed proof), and supplies the exact source wording needed to resolve the `unresolved` strength relation in section 4 | pending_acquisition |
| The original Erdos source cited by entry #982 | to be read off the acquired catalogue entry; the bibliographic details are deliberately not reconstructed here | settles the frozen conventions in section 2: the reading of "form a convex polygon", the threshold on `n`, the bound, and the quantifier over vertices | pending_acquisition |
| The claimed proof cited by entry #982 | to be read off the acquired catalogue entry; author, venue, and identifier deliberately not reconstructed here | settles claim T2, which is void-triggering for this target | pending_acquisition |
| Altman, on a problem of P. Erdos, *American Mathematical Monthly* (1963) | journal article page for the classical result that a convex `n`-gon determines at least `floor(n/2)` distinct distances in total; volume and pages to be confirmed from a secondary index before acquisition | settles claim T3, and fixes the boundary between the classical **total** statement and the frozen **per-vertex** statement so the two are not conflated | pending_acquisition |
| Erdos, on sets of distances of `n` points, *American Mathematical Monthly* (1946) | journal article page; volume and pages to be confirmed from a secondary index before acquisition | background on the distinct-distances programme, needed to interpret what "improved guaranteed fraction" would mean | pending_acquisition |
| Post-2025 literature on distinct distances in convex position | to be assembled by the operator under ADR-0055 as the pre-research novelty re-check protocol, with terminology and equivalent-formulation searches over "distinct distances", "convex position", "convex polygon", "vertex distance set", and "Erdos 982" | settles claim T4 (whether the problem is settled, and whether the per-vertex statement is known for any infinite family of `n`) | pending_acquisition |

Locator honesty note. Only the catalogue URL is given as a complete locator.
The two journal rows name the work and the field it must be looked up in rather
than a volume/page/DOI string, and the original-source and claimed-proof rows
are deliberately left to be read off the acquired catalogue entry. A volume
number or identifier reconstructed from memory would be a fabricated locator,
and a fabricated locator is worse than a missing one because it looks
acquirable.

## 6. Prior-status claims to re-check

Every claim here is an **untrusted source report**. None is a premise of the
frozen target. Each is carried into the intake file as an
`untrusted_source_report` assumption with scope `particular`, and each is on the
checklist for the ADR-0055 pre-research novelty re-check.

- **T1 — the catalogue labels #982 `FALSIFIABLE` rather than `OPEN`.**
  Inherited from the planning dossier, which reports the label as of its
  compilation date. Untrusted. The label is a catalogue rendering, not a
  mathematical verdict, and the catalogue itself has not been acquired.
- **T2 — the catalogue lists a claimed proof.** Inherited from the planning
  dossier. Untrusted, and **this is the load-bearing status claim of this
  dossier**: if the claimed proof is correct and settles the frozen statement,
  the target is void and must not be worked. What would settle T2, in order:
  acquire the catalogue entry to obtain the exact reference; acquire the claimed
  proof itself; determine whether it addresses the per-vertex statement of
  section 1 or only the classical total statement of T3; determine whether it is
  published, refereed, retracted, or a preprint with recorded objections; and
  determine, if it addresses the per-vertex statement, whether it proves it for
  all `n >= 3` or only for a restricted family, since a proof for a restricted
  family leaves the frozen target standing. The post-2025 literature review in
  section 5 must cover the claim thread and any response to it, because a claim
  posted after the planning dossier's compilation date would not appear in the
  inherited note at all. Until T2 is settled the correct status of this dossier
  is "scoped but not activatable".
- **T3 — the classical convex-polygon distinct-distances result.** It is
  reported classically that a convex `n`-gon determines at least `floor(n/2)`
  distinct distances **in total**, attributed to Altman. Untrusted as to
  attribution and exact form. It is a strictly weaker statement than the frozen
  target: the frozen target concentrates the `floor(n/2)` distances at a single
  vertex. This distinction is the most likely source of accidental
  overclaiming — a proof or a citation for the total statement must never be
  reported as progress on the per-vertex statement.
- **T4 — "reproduce the known lower bounds".** The planning dossier's first
  bounded slice says to reproduce the known lower bounds but names none.
  Untrusted and, as inherited, unnamed: there is no locator, no value, and no
  attribution to reproduce. Until section 5's rows are acquired, "the known
  lower bounds" is not a well-formed obligation, and the slice in section 7 does
  not depend on it.
- **T5 — sharpness attribution.** The planning dossier states that the regular
  polygon shows `floor(n/2)` is best possible. The underlying count has been
  verified independently in section 2.1, so the mathematical content is not
  inherited; only the framing "would be best possible" as a statement about the
  open problem remains a planning-note phrasing and stays untrusted.

None of T1 through T5 creates novelty status, significance, applicability,
graph admission, or mathematical warrant, and an empty search never means novel.

## 7. Bounded first slice

The slice does two things: it classifies an exactly enumerable finite family,
and it records with equal care why that family cannot bear on the universal
statement. The second is the more important output.

**Frozen family.** Fix `m = 5`, so the lattice box `B = {0,1,...,5}^2` has 36
points. Fix `n` in `{4,5,6,7}`. The family is every `n`-subset of `B` that is in
strictly convex position. Exact envelope sizes:

- `C(36,4) = 58905`
- `C(36,5) = 376992`
- `C(36,6) = 1947792`
- `C(36,7) = 8347680`
- total subsets inspected: `10731369`

**Inputs.** The integers `m = 5` and `n in {4,5,6,7}`; nothing else. No acquired
source, no model output, and no external file is an input. The slice is
reproducible from those constants alone.

**Exact algorithms and arithmetic.** All arithmetic is integer arithmetic in the
standard library; there is no rational division, no square root, and no floating
point anywhere.

1. *Convex-position filter.* A subset `S` is in strictly convex position iff,
   after sorting `S` by angle about its centroid to obtain a cyclic order, every
   consecutive orientation determinant `cross(a,b,c)` has the same strict sign,
   and additionally every one of the `C(n,3)` orientation determinants is
   nonzero. The determinants are integers; the tests are exact integer sign
   tests. The `C(n,3)` non-collinearity sweep is `4, 10, 20, 35` determinants
   for `n = 4,5,6,7` and is cheap enough to run unconditionally rather than
   inferred from the cyclic test.
2. *Per-vertex counts.* For each surviving `S` and each `p` in `S`, form the set
   of integer squared distances to the other `n - 1` points and take its
   cardinality, justified by section 2.2. Record the vector of `n` counts, and
   from it `M(S) = max` and `mu(S) = min`.
3. *Target check.* Assert `M(S) >= floor(n/2)` for every `S`. Any `S` with
   `M(S) <= floor(n/2) - 1` is an **exact counterexample** — integer coordinates
   are real coordinates, so the object is a genuine planar configuration — and
   it stops the slice immediately under the stopping rules.
4. *Canonicalization to similarity classes.* Two stages, because the cheap
   invariant is not complete.
   - *Bucket key.* Take the multiset of the `C(n,2)` integer squared distances,
     divide every element by the gcd of the multiset, and sort. A similarity of
     ratio `c` multiplies all squared distances by `c^2`; when both
     configurations have rational coordinates that factor is rational
     (section 8), so the gcd-normalized sorted multiset is a similarity
     invariant.
   - *Exact resolution inside a bucket.* The key is **not** a complete
     invariant: homometric point sets sharing a distance multiset without being
     similar exist. Inside each bucket, decide similarity exactly by the
     ratio-bijection test of section 8 over all `n!` bijections, at most
     `7! = 5040`. Reporting a class count from bucket keys alone is refused.
5. *Extremal census.* Record the similarity classes attaining
   `M(S) = floor(n/2)` exactly, and the distribution of `M(S)` and `mu(S)` over
   classes. This is the classification the planning dossier asks for, now with a
   stated equivalence and an exact test.
6. *Rejected-reading witness.* The exact hexagon of section 2.3 is already
   verified and is carried as a fixture of the slice rather than re-searched. It
   documents that the universal-over-vertices reading fails at `n = 6`. Note it
   lies outside `B`, which is recorded as evidence about the box rather than
   about the problem.

**What is exhaustive and what is not.** The `10731369` subsets of `B` are
enumerated exhaustively. Nothing else in this dossier is exhaustive.

**Boundary of the claim the slice can support — and why it is narrow.**

Exhausting the family supports exactly one statement: *no `n`-point subset of
the `6 x 6` lattice box, for `n` in `{4,...,7}`, is a counterexample to the
frozen statement.* Three separate facts make that statement much weaker than it
might look, and all three are stated here rather than left for a reader to
notice.

1. *The family provably omits the sharpness example for most `n`.* If `P` is
   similar to a set of rational points, then every ratio of squared distances of
   `P` is rational, since similarity scales all squared distances by one factor
   and the rational configuration's squared distances are rational. For the
   regular pentagon, `diagonal^2 / side^2 = phi^2 = (3 + sqrt 5)/2`, which is
   irrational; so **no rational configuration is similar to a regular
   pentagon**. For the equilateral triangle, all ratios are 1, so the ratio test
   says nothing, but a rational triangle has rational area (twice the area is an
   integer determinant after clearing denominators) while an equilateral
   triangle of squared side `s^2` has area `(sqrt 3 / 4) s^2`, irrational for
   rational
   `s^2 > 0`; so **no rational configuration is similar to an equilateral
   triangle**, hence none is similar to a regular hexagon either, since
   alternate vertices of a regular hexagon form an equilateral triangle. For
   `n = 7`, the ratio of the second and first chord squared is
   `sin^2(2 pi/7)/sin^2(pi/7) = 4 cos^2(pi/7) = 2(1 + cos(2 pi/7))`, and
   `cos(2 pi/7)` has degree 3 over `Q` with minimal polynomial
   `8 x^3 + 4 x^2 - 4 x - 1`, so that ratio is irrational and **no rational
   configuration is similar to a regular 7-gon**. The single exception in the
   frozen range is `n = 4`: the unit square is rational, and it is in `B`. So
   for three of the four values of `n`, the extremal configuration is provably
   absent from the family being classified.
2. *Counterexamples live on a proper algebraic subset.* A counterexample
   requires `n` simultaneous deficiencies, each of which is a conjunction of
   distance **equalities**. Equalities cut out a proper algebraic subset of the
   configuration space `R^{2n}`. Sweeping a box of lattice points meets the
   rational points of such a subset only by coincidence. The sweep is therefore
   expected to find nothing, and its null result carries essentially no
   information about the universal statement.
3. *A finite family is not a quantifier discharge.* Quantifier 1 of section 3
   (`forall n >= 3`) and quantifier 2 (`forall P`) are untouched. The family is
   finite, countable, and box-bounded; the target ranges over an uncountable set
   for every one of infinitely many `n`.

Taken together: **the exhaustion of this family is not evidence for the frozen
statement and must never be reported as evidence for it.** Its value is the
classification data, the extremal census, and the exact machinery — the integer
convex-position predicate, the squared-distance count, the similarity test —
that any later route reuses.

**The route that could actually bear on the target, labelled non-exhaustive.**
Because counterexamples are equality-constrained, the honest route is to solve
the equalities rather than sample around them. Freeze one `n` and one
**distance-coincidence pattern**: for each vertex, a partition of its `n - 1`
distances into at most `floor(n/2) - 1` classes. Each pattern yields a
polynomial system over `Q` in the `2n` coordinates (the equalities), together
with strict inequalities (the orientation determinants for strict convexity, and
non-degeneracy). Deciding whether that system has a real solution in strictly
convex position is an exact question, to be answered by exact means only:
Groebner basis or rational univariate representation for the equality ideal,
exact real-root isolation with rational interval endpoints used for exclusion
only, and real quantifier elimination for the strict inequalities. A pattern
shown to have no such real solution is an exclusion certificate; a pattern with
a solution yields an exact algebraic counterexample. This route is
non-exhaustive as scoped, because the number of patterns grows very fast and
only a frozen, named subset can be attempted. Section 12 records that this
route needs new capability that AdaIvy does not have.

## 8. Certificate and verifier contract

**Result shape A — an exact counterexample.**

Certificate contents:

- `n`, and the coordinates of the `n` points, either as exact rationals
  (numerator/denominator integer pairs) or as elements of a number field
  `K = Q(alpha)` given by the exact minimal polynomial of `alpha`, an isolating
  rational interval for the intended real root, and each coordinate as a
  polynomial in `alpha` of degree below `deg(alpha)` with rational
  coefficients;
- the cyclic order of the points and all `C(n,3)` orientation determinants with
  their signs;
- for each vertex, the list of squared distances in normal form and the
  partition of them into equal classes, with the equality derivations;
- the SHA-256 of the canonical serialization of all of the above.

Independent verifier: reads only the certificate, recomputes the hash,
recomputes every orientation determinant and checks strict convexity and
non-collinearity, recomputes every squared distance in exact field arithmetic,
recomputes each vertex's distinct-value count from normal-form equality, and
asserts `max_p |D(P,p)| <= floor(n/2) - 1`. Sign decisions on algebraic
quantities are made by exact real algebraic sign determination — refine the
isolating rational interval until the sign is decided — and interval arithmetic
is used only to exclude, never to conclude equality. Equality is always decided
by normal form, never by interval width.

**Result shape B — exhaustion of the frozen rational-grid family.**

Certificate contents: `m`, the `n` range, the exact subset counts
(`58905`, `376992`, `1947792`, `8347680`, total `10731369`), the
canonicalization procedure with both stages named, the similarity-class census,
the full
per-configuration count vectors as a hashed record file, and the extremal class
list. Independent verifier: replays the enumeration deterministically from `m`
and the `n` range alone, recomputes the record file, and compares hashes; then
independently re-runs the ratio-bijection similarity test on the reported class
representatives. Coverage is checked against the stated binomial coefficients.
The certificate must carry, in its own text, the three boundary facts of
section 7; a shape-B certificate without them is incomplete by contract.

**Result shape C — an exclusion certificate for a coincidence pattern.** The
pattern, the polynomial system, the Groebner basis or rational univariate
representation with the exact rational coefficients, and the exclusion argument
for real solutions in strictly convex position. Independent verifier: replays
the ideal computation and rechecks the exclusion, all in exact rational
arithmetic.

**Result shape D — a proof.** For all `n >= 3`, or for one frozen `n` recorded
as a statement about that `n` alone. Under ADR-0036 the environment is computed
from the records: absent a bare `kernel_checked` attestation on a `verified`
representation, such a result reaches `Proposition` at best, and a bounded or
exploratory result reaches `Conjecture`. No manuscript field can promote it.

**The exact similarity test, since the classification depends on it.** For
finite planar point sets `P`, `P'` with `|P| = |P'| = n >= 3 ` and not all
collinear: `P` and `P'` are similar iff there is a bijection `f : P -> P'` and a
single positive constant `r` with `dist(f(a),f(b))^2 = r * dist(a,b)^2` for all
`a, b` in `P`. A bijection preserving all distance ratios extends to a
similarity of the plane with ratio `sqrt r`. When both sets have rational
coordinates, `r` is forced to be rational — take one pair and divide two
rationals — so the test is a finite sequence of exact rational equality checks
over at most `n!` bijections, with no need to construct the similarity map and
no need for `sqrt r` to be rational. Note that `sqrt r` need not be rational
even when both sets are: the map `(x,y) -> (x - y, x + y)` is a similarity of
ratio `sqrt 2` carrying `Z^2` into `Z^2`, which is exactly why the test is
stated on squared distances and ratios rather than by normalizing coordinates.

**Refused as a certificate, without exception.**

- Floating-point coordinates or floating-point distances, at any point on the
  trust path; decimal coordinates; coordinates given "to `k` digits".
- Approximate equality of distances under any tolerance. Distance coincidence is
  the entire content of a counterexample, so a tolerance would manufacture the
  result being sought.
- A numerical optimizer's, SDP solver's, or continuation method's report that no
  configuration exists, or that one nearly does.
- A model's assertion, a model's proof sketch treated as a proof, or agreement
  between two model runs.
- An unreplayed third-party program or its output, including a published
  computational classification.
- Failure of the grid sweep, or of any search, as evidence for the universal
  statement, and in particular any presentation of a null sweep as support
  (section 7, boundary fact 1, makes such a presentation false as well as
  unwarranted).
- A configuration in convex position but with a collinear triple, offered as a
  counterexample; it is outside the frozen scope.
- A single deficient vertex, offered as a counterexample; a counterexample needs
  every vertex deficient (section 2.3).
- A citation or proof of the classical **total** distinct-distances statement
  (T3), offered as progress on the per-vertex statement.

## 9. Useful negative outcomes

- **The similarity-class census** of strictly convex `n`-subsets of the `6 x 6`
  lattice box for `n = 4,...,7`, with per-vertex count vectors, `M(S)`, and
  `mu(S)`. This is the classification the planning dossier asked for, delivered
  with a stated equivalence and an exact test rather than an informal one.
- **The extremal grid configurations**, those attaining `M(S) = floor(n/2)`,
  which are the candidates for a structural lemma about what forces a vertex to
  see few distances.
- **The proof that the method omits its own extremal example.** The
  irrationality arguments of section 7 — pentagon ratio `phi^2`, equilateral
  area, `cos(2 pi/7)` of degree 3 — establish that the rational family cannot
  contain the regular `n`-gon for `n = 3, 5, 6, 7`. This is a real negative
  result about the search design and it transfers to any future
  rational-coordinate search on this problem. It is worth more than the sweep it
  invalidates.
- **The exact witness of section 2.3**, refuting the universal-over-vertices
  reading at `n = 6` with integer coordinates. It is reusable as a fixture and
  as a boundary marker in any report.
- **The exactness observations**: distinct distances equal distinct squared
  distances (2.2), so no square roots enter; distinctness needs only equality
  decisions while convexity needs sign decisions (2.2); the ratio-bijection
  similarity test needs only rational equality checks (section 8). These are
  what make an exact trust path possible at all here, and they are recorded as
  reusable lemmas.
- **Excluded coincidence patterns**, each with its Groebner or rational
  univariate representation exclusion certificate, if the equation route runs.
  Each excluded pattern is a permanent reduction of the counterexample space.
- **The refuted-route record**: random rational sampling of convex position,
  floating-point near-coincidence search, and any tolerance-based distance
  comparison, each recorded with the reason it fails.
- **The frontier**, machine-readable, if the envelope truncates any run.

All of these are preserved in machine-readable output, per the standing
repository rule that failed attempts and missing-tool results are retained.

## 10. Evaluation protocol

Version 1, phase `exploratory`. The strings below are the same strings as the
intake file's `evaluation_protocol`.

**Metrics.**

- `convex_configurations_exactly_enumerated`
- `similarity_classes_canonicalized`
- `per_vertex_distinct_distance_counts_recorded`
- `counterexample_candidates_exactly_refuted`
- `coincidence_patterns_exactly_excluded`
- `failed_routes_preserved`
- `model_cost_usd`

**Success criteria.**

- an exact counterexample: a configuration of n points in strictly convex
  position with exactly represented rational or algebraic coordinates in which
  every vertex has at most floor(n/2) - 1 distinct distances to the other n - 1
  vertices, verified by exact equality tests in its own coordinate field
- a rigorous proof of the frozen universal statement for every n >= 3 under the
  frozen conventions
- a rigorous proof of the frozen universal statement for one frozen value of n,
  recorded as a statement about that n alone and never generalized
- an exact exclusion certificate for a frozen finite set of distance-coincidence
  patterns, showing that no strictly convex real configuration realizes any of
  them
- or an explicit unresolved outcome that records the smallest remaining
  obligation together with the exact family exhausted and what its exhaustion
  does not entail

**Stopping rules.**

- stop on an exact counterexample verified in its own coordinate field by exact
  equality tests
- stop on a rigorous derivation covering every configuration in scope for the
  frozen n
- stop when the frozen rational-grid family is exhausted, recording the
  per-vertex distinct-distance counts and the similarity-class census
- stop when the fresh model spend reaches USD 20
- stop when no new lemma, reduction, exclusion, or extremal class has been
  recorded for two consecutive review points
- never promote exhaustion of the rational-grid family into evidence for the
  universal statement over the reals; that family provably omits the regular
  n-gon for n = 3, 5, 6, and 7

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The catalogue label is `FALSIFIABLE` and a proof is claimed (T1, T2) | If the claim stands, the target is void and every hour spent is wasted; worse, a result could be announced against a settled problem | T2 is named the load-bearing status claim; section 6 lists exactly what would settle it and in what order; the ADR-0055 pre-research re-check must settle it before the first run, and the post-2025 review must cover claims made after the planning dossier's compilation date |
| The rational restriction excludes the sharpness example itself | A null grid sweep looks like supporting evidence and is not even weak evidence; presenting it as support would be false, not merely unwarranted | The exclusion is **proved** in section 7 for `n = 3, 5, 6, 7`; it is a required element of a shape-B certificate; and a stopping rule forbids the promotion in the protocol itself |
| Counterexamples lie on a proper algebraic subset of configuration space | Box sweeps and random rational sampling essentially never meet them, so effort produces logs rather than information | The equation route is named as the route that could bear on the target; the sweep is scoped as classification, not as refutation; random rational sampling is recorded as a forbidden route |
| Convex-position convention drift | Admitting collinear triples changes the configuration class; the frozen statement is the **weaker** of the two readings, so a degenerate counterexample would not refute it while looking as though it did | Frozen row and rejected reading in section 2, with the implication direction stated; a refusal in section 8; and an open question requiring the acquired source to confirm the reading |
| "Some vertex" read as "every vertex" | The stronger reading is false, so working on it would produce a spurious refutation of a statement nobody asked about | Section 2.3 exhibits an exact integer witness at `n = 6`, carried as a slice fixture so the distinction is visible in every run rather than inferred from a table row |
| The classical total statement (T3) confused with the per-vertex statement | The total statement is classical; citing it as progress would be an overclaim with an easy path into a report | Separate rows in section 2 and section 6; an explicit refusal in section 8; the distinction is stated in the semantic alignment |
| `floor` versus `ceil`, `>=` versus `>` | Either slip changes the truth value: with `>` the regular `n`-gon is a counterexample and the problem is trivial | Frozen rows in section 2 with the regular-`n`-gon check of section 2.1 as the discriminating test |
| Floating-point geometry entering through a library | Distance coincidence is the whole content of a counterexample, so any tolerance manufactures results; a repo-owner rule rejects floating-point solvers outright | All predicates are integer or exact-field: orientation determinants for convexity, normal-form equality for distances; floats are refused as certificates, and their appearance is a defect not a tolerance question |
| Similarity canonicalization error | Homometric sets share a distance multiset without being similar, so a bucket-key-only census would silently merge classes and report a wrong classification | Two-stage canonicalization; the bucket key is explicitly a key and not an invariant of record; the ratio-bijection test resolves each bucket; the class count is reported with the test named |
| Affine equivalence used by habit instead of similarity | Affine maps do not preserve distance ratios, so the whole invariant being classified would be destroyed — the unit square and a `1 x 2` rectangle have per-vertex counts 2 and 3 | Frozen equivalence row in section 2 with that exact counterexample recorded |
| A proof for one `n` presented as the theorem | The target's difficulty is the unbounded `forall n`; a single-`n` result is a different statement | Separate success criterion naming the single-`n` outcome as a statement about that `n` alone; ADR-0036 computes the claim environment from records so nothing promotes it |
| New algebraic dependency introduced silently | A Groebner or real-algebraic library is a third-party runtime dependency, outside the standard library and outside the pinned set | Section 12 lists it as requiring a new ADR, with pinning and license recording per the standing engineering rules; the sweep itself needs nothing beyond the standard library |

## 12. Capability check

**Covered by existing, already-authorized AdaIvy capabilities.**

- Phase 1 declarative problem intake and trust policy: the intake file is
  exactly a Phase 1 `problem-definition-v1` document and creates no trust.
- The entire rational-grid slice: integer arithmetic and `fractions` from the
  standard library, deterministic serialization, explicit schema versions,
  content hashes, and bounded no-network subprocesses with captured
  stdout/stderr. No third-party package is needed, which matches the standing
  preference for the standard library in the harness.
- Machine-readable preservation of failed attempts and unresolved outcomes,
  which is what section 9 consists of.
- ADR-0055 pre-research novelty re-check, the mechanism that consumes section 6
  and must precede the first run by construction. Given T2 it is the gating
  step, not a formality.
- ADR-0047 bounded central-lead runtime for proposing patterns and lemmas, and
  ADR-0057 campaign provenance closure if a model writes the enumerator, subject
  to the caveat below.
- ADR-0036 publication projection, which computes the claim environment from the
  records and cannot render a `Theorem` here.

**Would require a new ADR, and is therefore not assumed.**

- **Exact algebraic number arithmetic beyond the Phase 5 field envelope.** The
  slice's algebraic content lives in fields the existing exact machinery does
  not cover. Phase 5 works over one real quadratic extension per case,
  `Q(sqrt d)(i)` with `d` squarefree and measured from the case values, and
  ADR-0035 makes everything outside that envelope — two distinct surds, a cubic
  or higher irreducible extension, a declared transcendental — an explicit typed
  rejection. The regular `n`-gon lives in a cyclotomic field, and
  `cos(2 pi / 7)` generates a cubic field. Section 2.1's verification is a
  symbolic argument about `sin`, deliberately not a field computation, precisely
  so that it stays inside what is available. Any certificate with algebraic
  coordinates needs a general exact algebraic-number capability that does not
  exist here.
- **Groebner basis or rational univariate representation machinery**, with exact
  rational coefficients, for the coincidence-pattern route. No such dependency
  is pinned; adding one means pinning a third-party package and recording its
  license under the standing engineering rules, and it means deciding what a
  replayable ideal-computation certificate is.
- **Exact real algebraic sign determination and real quantifier elimination**
  for the strict-convexity inequalities in the pattern route. Interval
  arithmetic with rational endpoints is admissible for exclusion only; a
  decision procedure for the existential-real fragment is a distinct capability.
- **Production execution of generated code.** Under ADR-0057 this remains
  disabled until its distinct digest-pinned OCI sandbox gate passes. If the
  enumerator is model-written it must run under that gate or be replaced by an
  operator-authored program; the offline path uses injected scripted ports only.
- **An execution envelope beyond the current bounded-subprocess limits**, if the
  lattice box or the `n` range is widened past the `10731369` subsets frozen
  here. This is a bound change rather than a new mechanism, but it must be
  authorized explicitly rather than absorbed.
- **Acquisition of the catalogue entry and the claimed proof.** These are
  acquisitions under ADR-0050, human-planned and exact-URL, and are not
  activated here. Without them T2 cannot be settled, so the dossier's own gating
  question depends on a capability that this document does not exercise.

**Explicitly not activated by this dossier:** any numerical optimizer, SDP
solver, continuation method, or floating-point geometry library; any network
access; any crawler or result-following; any parallel specialist, evolutionary,
or higher search tier; any embeddings or vector store; and any automated novelty
or significance assessment.

## 13. Open questions before intake

1. **Blocking.** Does the claimed proof cited by catalogue entry #982 settle the
   frozen per-vertex statement? Section 6's T2 lists the exact sequence that
   answers this: acquire the entry, acquire the claim, determine whether it
   addresses the per-vertex or only the total statement, determine its
   publication and objection status, and determine whether it covers all
   `n >= 3` or a restricted family. If it settles the statement, the target is
   void and must not be worked. Until this is answered the dossier is scoped but
   not activatable.
2. **Blocking.** Does the source admit degenerate configurations? "Form a convex
   polygon" is frozen here as strictly convex position with no three points
   collinear, and section 2 justifies that reading, but the source text has not
   been acquired. Because the frozen statement is the **weaker** of the two
   readings, a mistake in this direction is not symmetric: a degenerate
   counterexample would not refute the frozen target. The acquired source must
   confirm the reading before intake.
3. **Blocking.** What is the source's threshold on `n`, and is the bound exactly
   `floor(n/2)` with "at least"? Frozen here as `n >= 3` and
   `|D(P,p)| >= floor(n/2)`. If the source says `ceil(n/2)`, or uses a strict
   inequality, the target changes and the regular `n`-gon becomes decisive.
4. Does the count include distances to the two polygon-adjacent vertices? Frozen
   here as all `n - 1` other vertices. A diagonals-only reading would be a
   different problem and would change the sharpness analysis.
5. Is plane similarity, including reflections and positive uniform scaling, the
   intended "exact equivalence" for the classification the planning dossier
   asks for? It is the only one of the natural candidates that preserves the
   invariant being classified, and it is frozen here on that ground, but the
   choice is a decision rather than a quotation and the operator should confirm
   it.
6. May a Groebner basis or rational univariate representation dependency, and an
   exact real algebraic sign-determination capability, be introduced under a new
   ADR? Without them the coincidence-pattern route cannot run and the slice is
   limited to classification, which section 7 shows cannot bear on the target.
7. What lattice box `m` and `n` range are authorized, and what spend cap
   replaces the placeholder USD 20 in section 10? The frozen `m = 5` and
   `n in {4,...,7}` are chosen to fit `10731369` subsets inside a bounded
   subprocess; the exact witness of section 2.3 needs a `16 x 14` box, so the
   frozen box is known to be small relative to interesting configurations.
8. Is Altman's classical total-distinct-distances result the right comparison
   point for T3, and is its attribution correct? The locator is unconfirmed and
   the distinction between total and per-vertex is the dossier's main
   overclaiming risk.
9. Is `discrete-geometry` the intended `declared_domain`, or should the item be
   filed under a combinatorial-geometry domain already in use elsewhere in the
   repository?
