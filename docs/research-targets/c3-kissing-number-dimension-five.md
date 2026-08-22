# C3. Kissing number in dimension 5 — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item C3 (tier C)
**Declared domain:** discrete-geometry
**Intake file:** docs/research-targets/intake/c3-kissing-number-dimension-five-v1.json
**Frozen in one line:** There exist a positive squarefree integer `d` and 41
vectors in `K^5`, `K = Q(sqrt(d))`, each of exact squared norm `4`, whose
pairwise squared distances are all at least `4`.

This is a scoped intake package. It does not approve a formalization, establish
that the problem is open, authorize source acquisition, assess novelty or
significance, create mathematical warrant, or activate any capability. Novelty,
significance, and source applicability are `not_assessed` and stay that way. The
reported interval `40 <= tau_5 <= 44` is an untrusted candidate; if the known
lower bound is already `41` or higher the frozen target is void and this dossier
must be re-frozen rather than run.

## 1. Frozen target

The planning dossier offers a disjunction: construct 41 tangent spheres, or
prove `tau_5 <= 43`. A disjunction is not a target. **One direction is frozen
here: the lower-bound route.** The upper-bound route is rejected for this slice,
with the reason recorded in sections 2 and 12.

### 1.1 Geometric statement

Let `S` be the closed unit ball in `R^5` centred at the origin. A kissing
configuration of size `N` is a set of `N` unit balls, each externally tangent to
`S`, with pairwise disjoint interiors. Externally tangent to `S` means the
centre is at Euclidean distance exactly `2` from the origin; pairwise disjoint
interiors means any two centres are at Euclidean distance at least `2`.

Frozen geometric target: there is a kissing configuration of size `41` in `R^5`.

### 1.2 Exact algebraic formulation, which is the frozen statement

Let `d` be a positive squarefree integer and `K = Q(sqrt(d))`, understood as a
subfield of `R` through the real embedding sending `sqrt(d)` to the positive
real square root; `d = 1` gives `K = Q`. Order on `K` is the induced real order,
and it is decided exactly: for `a + b*sqrt(d)` with `a, b` rational, the sign is
determined by the signs of `a` and `b` and, when they differ, by comparing `a^2`
with `b^2 * d`, all in exact rational arithmetic.

**Target.** There exist a positive squarefree integer `d` and vectors
`v_1, ..., v_41` in `K^5`, `K = Q(sqrt(d))`, such that

- for every `i`, `<v_i, v_i> = 4` exactly, that is each `v_i` has exact
  Euclidean norm `2`; and
- for every `i != j`, `<v_i - v_j, v_i - v_j> >= 4` in the order of `K`.

Here `<u, w> = sum over t = 1..5 of u_t * w_t`, computed in `K`. Quantifiers: an
existential over `d`, then an existential over 41 vectors; the two conditions
are universally quantified over the finitely many indices. Scope: `existential`.

Because `<v_i, v_i> = <v_j, v_j> = 4`, the identity

`<v_i - v_j, v_i - v_j> = <v_i,v_i> + <v_j,v_j> - 2<v_i,v_j> = 8 - 2<v_i,v_j>`

makes the second condition exactly equivalent to `<v_i, v_j> <= 2` for all
`i != j`. Both forms are recorded because the Gram form `<v_i,v_j> <= 2` is what
a search actually tests, while the distance form is what the geometry says.
Note also that `v_i != v_j` for `i != j` follows: `v_i = v_j` would give
`<v_i,v_j> = 4 > 2`.

### 1.3 What the field restriction does and does not do

Restricting coordinates to one real quadratic field is a restriction on the
**certificate language**, and by folding it into the statement it becomes a
restriction on the target as well. A 41-point configuration realizable only over
a field of degree greater than `2` over `Q`, or only over transcendental
coordinates, would not satisfy the frozen target. That is deliberate: it is the
arithmetic in which this repository can decide order and equality exactly today
(see section 12). `d` is **measured** from the exhibited coordinates and never
declared in advance, following the ADR-0035 rule that the radicand is measured
from the case values.

### 1.4 What is not claimed

No such configuration is known to this dossier and the target may be false. The
frozen target is strictly weaker than `tau_5 >= 41`, and a proof of its negation
would not settle `tau_5`. Nothing here asserts that the problem is open, that
the reported interval is correct, or that any exhibited object would be new.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| kissing configuration | centres at exact Euclidean distance `2` from the origin, pairwise distance at least `2`, in `R^5` | centres on a sphere of radius `1`, which is the unit-vector normalization with angular separation at least `60` degrees; a packing with tangency to each other required rather than merely allowed |
| the frozen direction | the lower-bound route: exhibit 41 vectors | the upper-bound route `tau_5 <= 43`; the disjunction of the two, which is not a target; "improve the interval", which names no statement |
| coordinate field | one real quadratic field `K = Q(sqrt(d))`, `d` positive squarefree, `d` measured from the exhibited coordinates, `d = 1` meaning `Q` | unrestricted real coordinates; unrestricted real algebraic numbers, whose order and equality need root isolation this repository does not have; two distinct surds in one configuration; a cubic or higher irreducible extension; floating-point coordinates |
| exact norm | `<v_i, v_i> = 4` exactly in `K`, that is Euclidean norm exactly `2` | norm within a tolerance; norm `1` after rescaling, which changes the distance threshold to `1` and is a different arithmetic; squared norm `2`, which is the unscaled `D_5` minimal-vector normalization |
| non-overlap | `<v_i - v_j, v_i - v_j> >= 4`, equivalently `<v_i, v_j> <= 2`, with the non-strict inequality | strict `> 4`, which forbids mutual tangency and is a different and harder target; `>= 4 - epsilon` for any tolerance |
| `tau_5` | the maximum size of a kissing configuration in `R^5`, over all real configurations | the maximum over lattice configurations, which is a different and generally smaller quantity; the maximum over configurations with coordinates in a quadratic field, which is the quantity this dossier's target bounds below |
| certificate | the measured `d` together with 41 explicit coordinate vectors in `K^5` | a Gram matrix alone, which additionally requires an exact positive-semidefiniteness and rank-at-most-`5` certificate; a numerically optimized configuration; a configuration reported without its field |
| exclusion over a pool | a **completed** exhaustive search over a frozen finite candidate pool, with its maximum configuration size certified | a branch-and-bound search that exhausted its node budget; a randomized or heuristic search that found nothing |
| the `43` bound | not part of this dossier | any LP or SDP bound, exact or otherwise, treated as settling a slice of this target |

### 2.1 Why the `tau_5 <= 43` route is rejected for this slice

The natural certificate for an upper bound of that shape is a Delsarte-style
linear-programming bound or a Bachoc-Vallentin-style semidefinite-programming
bound, both of which are produced by floating-point solvers. Under this
repository's rules a floating-point solver output is evidence and is not a
theorem, and the repository owner rejects floating-point solvers outright.
Converting such a bound into an exact certificate would require a rational
feasible dual solution together with a verified exact duality argument, and no
capability here checks that. It is named in section 12 as needing a new ADR. It
is not attempted, not partially attempted, and not used as guidance for the
frozen direction.

### 2.2 The Gram-form equivalence, verified

For vectors `u, w` in an inner-product space with `<u,u> = <w,w> = 4`:

`<u - w, u - w> = <u,u> - 2<u,w> + <w,w> = 8 - 2<u,w>`,

so `<u - w, u - w> >= 4` iff `8 - 2<u,w> >= 4` iff `<u,w> <= 2`. Both steps are
equivalences over an ordered field, so nothing is weakened in either direction.
The computation is bilinear expansion only and holds verbatim in `K`.

## 3. Formalization and quantifiers

Formal language: `typed_informal_math`, version 1, approval status `proposed`.
Human approval of the alignment in section 4 has not been requested.

```
exists d : N,
  d >= 1 and squarefree(d) and
  exists v_1 ... v_41 : (Q(sqrt(d)))^5,
    (forall i in [1..41], inner(v_i, v_i) = 4)
    and (forall i j in [1..41], i != j -> inner(v_i - v_j, v_i - v_j) >= 4)
```

where `inner(u, w) = sum over t in [1..5] of u_t * w_t` in `Q(sqrt(d))`, and
`>=` is the order of the real embedding of `Q(sqrt(d))`, decided exactly.

Quantifiers: one existential over `d`; one existential over a 41-tuple of
vectors; two bounded universals over indices, giving `41` norm conditions and
`C(41,2) = 820` distance conditions. No asymptotics, so no implicit epsilon. All
of the inner quantifiers are finite and every condition is exactly decidable in
`K`, so a candidate configuration is checkable in closed form.

## 4. Semantic alignment to the source statement

Human approval of this alignment is required and absent. The source statement is
the planning dossier's line: improve the reported interval `40 <= tau_5 <= 44`
by either constructing 41 unit spheres tangent to a central unit sphere in
five-dimensional Euclidean space or proving `tau_5 <= 43`.

**Quantifier mapping.** "41 unit spheres tangent to a central unit sphere" maps
to the 41 vectors `v_1, ..., v_41`; the sphere centres are the vectors and the
tangency and non-overlap conditions are the two displayed conditions. `d` has no
counterpart in the source line and is introduced by this dossier.

**Definition mapping.**

- "unit sphere tangent to a central unit sphere" maps to `<v_i, v_i> = 4`.
- "41 unit spheres with disjoint interiors" maps to
  `<v_i - v_j, v_i - v_j> >= 4` for `i != j`, equivalently `<v_i, v_j> <= 2`.
- "exact or certified algebraic coordinates and pairwise-distance checks" maps
  to coordinates in one measured `Q(sqrt(d))` with exact field arithmetic and
  exact order decision.
- "`tau_5`" maps to the maximum over all real configurations; the frozen target
  bounds it below only if satisfied.

**Assumption delta.** The source line is a disjunction over two directions; this
dossier keeps exactly one. The source line places no restriction on
coordinates; this dossier restricts them to one real quadratic field and thereby
weakens the target. The source line's `tau_5 <= 43` half is explicitly out of
scope with the reason in section 2.1.

**Edge-case delta.** `v_i = v_j` for `i != j` is impossible under the frozen
conditions, so distinctness need not be assumed separately. Mutual tangency is
allowed, since the distance condition is non-strict. `d = 1` is admitted and
means rational coordinates. A configuration whose coordinates require two
distinct surds, or an extension of degree greater than `2`, does not satisfy the
frozen target even if it satisfies the geometric one.

**Strength relation:** `weaker`. The frozen target is one direction of a
disjunction, further restricted to coordinates in a single real quadratic field,
so it is a strict special case of the source line. It is not `equivalent`: no
primary source has been acquired.

## 5. Provenance and acquisition plan

Nothing in this table has been fetched. Under ADR-0050 acquisition is
human-planned, exact-URL, and separately authorized. Every locator below is an
unverified recollection written from memory; the operator must confirm each one
before acquisition, and a locator that fails to resolve is itself a finding.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Conway and Sloane, "Sphere Packings, Lattices and Groups", 3rd ed., Springer 1999 | ISBN 978-0-387-98585-5, chapter 1 section 2.3 and the laminated-lattice kissing-number table in chapter 6; exact table number to be confirmed | claim 6.2, the reported lower bound `tau_5 >= 40` and the `D_5` configuration that realizes it, which is the baseline the slice reproduces | pending_acquisition, applicability not_assessed |
| Odlyzko and Sloane, "New bounds on the number of unit spheres that can touch a unit sphere in `n` dimensions", J. Combin. Theory Ser. A 26 (1979) 210-214 | doi:10.1016/0097-3165(79)90074-8 | claim 6.1, the historical linear-programming upper bounds in low dimensions, and the fact that the upper-bound route is LP-shaped | pending_acquisition, applicability not_assessed |
| Bachoc and Vallentin, "New upper bounds for kissing numbers from semidefinite programming", J. Amer. Math. Soc. 21 (2008) 909-924 | doi:10.1090/S0894-0347-07-00589-9 | claim 6.1 and the section 2.1 rejection: the reported upper bound's shape, and confirmation that its certificate is a numerically solved SDP | pending_acquisition, applicability not_assessed |
| Mittelmann and Vallentin, "High-accuracy semidefinite programming bounds for kissing numbers", Experimental Mathematics 19 (2010) 175-179 | doi to be confirmed by the operator; recollection is 10.1080/10586458.2010.10129068 | claim 6.1, specifically whether the reported upper bound is `44`, `45`, or something else, and whether any exact rational dual is published | pending_acquisition, applicability not_assessed |
| A current survey or table of best known kissing numbers by dimension | to be identified by the operator; no locator asserted here | claim 6.3, the pre-intake check that the known lower bound is still `40` and not already `41` or more. If it is `41` or more the frozen target is void | pending_acquisition, applicability not_assessed |
| Any published exact or rational certificate for a kissing-number upper bound in a low dimension | to be identified by the operator; none is asserted to exist | whether the section 2.1 rejection could ever be lifted, and what an exact dual certificate would have to contain | pending_acquisition, applicability not_assessed |

## 6. Prior-status claims to re-check

Each is untrusted, none is a premise, and each must be covered by the ADR-0055
pre-research novelty re-check bound to this problem's subject hash before any
run.

- **6.1** "The reported interval is `40 <= tau_5 <= 44`." Untrusted, in both
  endpoints. The upper endpoint does not affect the frozen target and is
  recorded only for context.
- **6.2** "The lower bound `40` is realized by the `D_5` minimal vectors."
  Untrusted. The slice reproduces and exactly verifies the configuration from
  first principles rather than citing it, so a wrong attribution costs nothing
  but a corrected note.
- **6.3** **Pre-intake check, blocking.** "The best known lower bound is `40`."
  If the current best known lower bound is already `41` or higher, the frozen
  target is **void**: it would be asking for something already known, this
  dossier must be re-frozen at a higher count or on a different question, and no
  run may start. This is the single claim whose failure invalidates the dossier
  rather than merely correcting it.
- **6.4** "The problem is open." Untrusted and unassessed.
- **6.5** "A floating-point SDP bound is evidence rather than a theorem." This
  is a repository rule and not a source claim, so it is not untrusted; it is
  recorded here so the distinction between the two kinds of statement in this
  section is explicit.
- **6.6** "No exact rational dual certificate for a dimension-5 kissing bound is
  published." Untrusted, and recorded as a negative recollection, which is the
  weakest kind of claim in this dossier. If one exists, section 12's ADR
  requirement becomes a much smaller piece of work, but it is still a new
  capability.

## 7. Bounded first slice

Four steps, in order, all offline, all exact arithmetic over one measured
`Q(sqrt(d))`. Nothing calls a model or the network. The programs must be
human-authored; see section 12.

### 7.1 Step 1 — the exact checker

Build the predicate directly: given `d` and a list of vectors with coordinates
`a + b*sqrt(d)`, `a, b` rational, verify every `<v_i, v_i> = 4` and every
`<v_i - v_j, v_i - v_j> >= 4`, with the order decided by the exact rule in
section 1.2. The checker is the only component the certificate contract depends
on, so it is written first and probed with deliberately invalid inputs: a vector
of squared norm `4 + 1/10^6`, a pair at squared distance `4 - 1/10^6`, and a
duplicated vector. Each probe must be rejected. A checker that cannot be made to
reject proves nothing.

### 7.2 Step 2 — reproduce and verify the 40-point baseline

The frozen baseline is the scaled `D_5` minimal-vector set

`B = { sqrt(2) * (e_i + s*e_j) : 1 <= i < j <= 5, s in {+1,-1} }` together with
the negatives of those vectors,

which has `4 * C(5,2) = 40` elements, each of squared norm
`2 * (1 + 1) = 4`. Verify all `40` norm conditions and all `C(40,2) = 780`
pairwise distance conditions exactly, over `K = Q(sqrt(2))`, with `d = 2`
measured from the coordinates. This is cheap and its purpose is to validate the
checker against an object whose properties are independently derivable by hand.

### 7.3 Step 3 — the exact single-vector extension test on the baseline

Ask whether any `v` with `<v,v> = 4` satisfies `<v, u> <= 2` for all `u` in `B`.
The run must derive and check this itself; the following is a route note, not an
inherited result, and it is expected to come out infeasible.

Because `B` is closed under negation, the constraints for `u = sqrt(2)(e_i+e_j)`
and `u = -sqrt(2)(e_i+e_j)` together give `|v_i + v_j| <= sqrt(2)`, and likewise
`|v_i - v_j| <= sqrt(2)`. Since
`max(|v_i + v_j|, |v_i - v_j|) = |v_i| + |v_j|`, the constraint set is exactly
`|v_i| + |v_j| <= sqrt(2)` for all `i < j`. Writing `a_i = |v_i|` sorted
decreasingly, `a_1 + a_2 <= sqrt(2)` and `2*a_2 <= a_2 + a_3 <= sqrt(2)`, so
`sum a_i^2 <= a_1^2 + 4*a_2^2 <= (sqrt(2) - a_2)^2 + 4*a_2^2`, a convex function
of `a_2` on `[0, sqrt(2)/2]` whose maximum over that interval is
`max(2, 5/2) = 5/2 < 4`. So `<v,v> <= 5/2 < 4` and no extension exists.

If that comes out as expected, the immediate consequence is that the search
cannot proceed by adding a point to the `D_5` configuration, and any 41-point
configuration must differ from it structurally. That negative result is the
slice's first real finding and is recorded as such.

### 7.4 Step 4 — exhaustive exclusion over one frozen finite pool

**The pool.** `P = P_1 union P_2` over `K = Q(sqrt(2))`, where

- `P_1 = { v in Z^5 : <v,v> = 4 }`, which is `{ +-2*e_i }` (10 vectors) together
  with the sign-and-position variants of `(1,1,1,1,0)` (5 zero positions times
  16 sign patterns, 80 vectors), so `|P_1| = 90`;
- `P_2 = B`, the 40 scaled `D_5` vectors of step 2.

`|P| = 130`. The pool is not the minimal-vector set of any single lattice, which
is the point of taking a union: a pool that *is* one lattice's minimal-vector
set can never exceed that lattice's kissing number, so a search over it is
guaranteed to fail and its exclusion is near-vacuous.

**Exactness of the pool's adjacency.** Inner products within `P_1` are integers
and within `P_2` they are `2` times an integer. Across the two,
`<v, sqrt(2)*(e_i + s*e_j)> = sqrt(2)*(v_i + s*v_j)` is an integer multiple of
`sqrt(2)`, so the condition `<= 2` becomes `k <= sqrt(2)` for an integer `k`,
that is `k <= 1`.
Every one of the `C(130,2) = 8385` adjacency decisions is therefore an exact
integer comparison, precomputed once.

**Algorithm.** Exact maximum clique in the graph on `P` whose edges are the
pairs with `<v,w> <= 2`, by branch and bound with a greedy-colouring upper
bound, a frozen canonical vertex ordering, and exact integer arithmetic
throughout. A clique of size `41` is exactly a witness for the frozen target, so
the search can in principle succeed rather than only exclude.

**Symmetry quotient.** The group of signed coordinate permutations, of order
`2^5 * 5! = 3840`, preserves `P_1` and `P_2` separately and therefore acts on
`P`. It has three orbits on `P`: `{+-2e_i}`, the `(1,1,1,1,0)` type, and `P_2`.
The first branching vertex is therefore restricted to three orbit
representatives instead of `130` vertices, a quotient the run records and
justifies rather than assumes.

**Envelope, cost, and the incomplete-search rule.** `130` vertices, `8385`
precomputed adjacencies, and a frozen node budget for the branch-and-bound
search. Maximum clique is not polynomial and `130` vertices is not a guaranteed
completion, so the rule is explicit: **only a completed search yields a
certified exclusion.** A search that exhausts its node budget is recorded as
`search_incomplete` together with its node count and best clique found, and that
record is never presented as a maximum, an exclusion, or a bound.

**What exhaustion entails.** If the search completes with maximum clique size
`M`: exactly that no subset of `P` of size greater than `M` satisfies the frozen
conditions. It entails nothing about vectors outside `P`, nothing about other
fields, and nothing about `tau_5`. If `M < 41` this is a certified exclusion
over a frozen pool and not evidence that no 41-point configuration exists.

### 7.5 What is exhaustive versus sampled

Exhaustive: steps 2 and 3 over their exactly defined objects, and step 4 over
`P` if and only if it completes. Sampled: nothing. Explicitly excluded from the
slice: any numerical or gradient-based configuration search, any SDP or LP, and
any randomized placement heuristic. A numerically optimized configuration may
never be rounded and submitted; if such a configuration were ever used as a
hint, the resulting exact coordinates would have to satisfy the checker from
scratch, and a near-miss under rounding is not a witness.

## 8. Certificate and verifier contract

### 8.1 Result shape R1 — a 41-point configuration is found

Certificate: the measured squarefree `d`, and 41 vectors each given as five
pairs of exact rationals `(a_t, b_t)` denoting `a_t + b_t*sqrt(d)`. Nothing else
is part of it.

Independent verifier, sharing no code with the search: confirm `d` is a positive
squarefree integer; recompute all `41` inner products `<v_i,v_i>` in `K` and
require each to equal `4` exactly; recompute all `820` values
`<v_i - v_j, v_i - v_j>` and require each to be at least `4` in the exact order
of `K`; and confirm that the `d` used is the one measured from the coordinates
rather than one supplied alongside them. Because the check is self-verifying
against the frozen predicate, the origin of the configuration is irrelevant to
its acceptance: a wrong configuration fails the exact check rather than passing
quietly. This is the same property that makes the ADR-0035 zero-gap certificates
safe, and it is the reason a positive result here does not need a
separation-of-duty argument.

### 8.2 Result shape R2 — a certified pool-restricted maximum

Record: the frozen pool definition, the `8385` adjacency decisions with their
exact values, the symmetry quotient and its justification, the completed
search's maximum clique size `M` with one attaining configuration, the node
count, and a canonical hash.

Independent verifier: rebuild `P` from its definition, recompute the adjacency,
re-run the search, and compare canonical hashes; and separately verify the
exhibited maximum clique with the section 8.1 checker.

### 8.3 Result shape R3 — an incomplete search

Record: everything in R2 except a maximum, plus the field
`search_incomplete: true`, the node budget, the nodes consumed, and the best
clique found. This shape exists so that a budget-exhausted run has a truthful
home and cannot be silently written as R2. It is not an exclusion and not a
bound.

### 8.4 Result shape R4 — a proof that the target is false

Certificate: a proof object in the repository's existing formal or
human-reviewed channel, establishing that no 41 such vectors exist over any real
quadratic field. No route to this is proposed. Note that it would not settle
`tau_5`, since the field restriction is part of the frozen target.

### 8.5 What is refused as a certificate

- Any floating-point value on the trust path: floating-point coordinates, a
  floating-point Gram matrix, a floating-point distance, or a tolerance of any
  size.
- Any LP or SDP output, exact-looking or not, as a bound on this target. This
  includes the `tau_5 <= 43` direction entirely; see sections 2.1 and 12.
- A Gram matrix without exact positive-semidefiniteness and rank-at-most-`5`
  certificates. Coordinates are required precisely so that realizability is not
  an additional obligation.
- A configuration over unrestricted real algebraic numbers whose order
  comparisons rest on root isolation this repository cannot perform exactly.
- A model's assertion that a configuration is valid.
- An unreplayed third-party lattice, geometry, or clique library result.
- Failure of a search, and in particular an incomplete branch-and-bound search
  reported as a maximum.

## 9. Useful negative outcomes

- **The exact checker with its rejection probes.** A reusable predicate over one
  measured real quadratic field for kissing-type configurations in any
  dimension, with demonstrated ability to reject invalid inputs.
- **The verified 40-point baseline.** An independently reproduced and exactly
  checked configuration, which converts claim 6.2 from a citation into a
  checked object.
- **The extension-infeasibility record.** If step 3 comes out as expected, a
  replayable exact argument that the `D_5` configuration admits no 41st point.
  That closes the most obvious route and is the slice's most likely durable
  finding.
- **A certified pool-restricted maximum, or an honest incomplete-search
  record.** Either is retained machine-readably, and the distinction between
  them is enforced by the record shape rather than by wording.
- **The lattice-pool ceiling note.** A recorded reason that pools drawn from a
  single lattice's minimal vectors cannot exceed that lattice's kissing number,
  so future pool choices do not repeat a guaranteed-failure search.
- **The refused-route record for `tau_5 <= 43`.** A written reason, with the ADR
  requirement named, so the upper-bound direction is not re-attempted
  informally.

## 10. Evaluation protocol

Mirrors the intake JSON exactly. Phase: `exploratory`. Version: `1`.

Metrics:

- `exact_squared_norm_checks_verified`
- `exact_pairwise_distance_checks_verified`
- `configurations_of_size_41_exhibited`
- `pool_restricted_maximum_sizes_certified`
- `extension_infeasibility_arguments_replayed`
- `incomplete_searches_recorded_as_incomplete`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria:

- `41 exhibited vectors over one measured real quadratic field K = Q(sqrt(d)) with every squared norm exactly 4 and every pairwise squared distance verified to be at least 4 by exact field arithmetic`
- `a rigorous proof that no such 41 vectors exist over any real quadratic field`
- `or an explicit unresolved outcome recording every certified pool-restricted maximum, every incomplete search with its node budget, and the smallest remaining obligation`

Stopping rules:

- `stop on an exact certificate: 41 vectors passing every exact squared-norm and pairwise-distance check`
- `stop when the fresh model spend reaches USD 25`
- `stop when two consecutive review points certify no new pool-restricted maximum and close no obligation`
- `never promote exhaustion of a frozen finite candidate pool into a claim about tau_5 or about configurations outside the pool, and never record an incomplete branch-and-bound search as an exclusion or a bound`
- `refuse any floating-point, linear-programming, or semidefinite-programming output as a certificate, and do not pursue the tau_5 <= 43 upper-bound route inside this slice`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The target may already be known | If the best known lower bound is already `41`, every run is spent re-deriving a known object | claim 6.3 is a blocking pre-intake check in sections 6 and 13; a positive finding voids the dossier rather than correcting it |
| SDP creep | The upper-bound route is the one with mature machinery, and a solver output is one import away | sections 2.1, 8.5, and 12 refuse it; the stopping rules name it; the repository owner rejects floating-point solvers outright |
| Incomplete search read as exclusion | Maximum clique on `130` vertices may not complete, and the natural log line looks identical either way | a distinct result shape R3 with `search_incomplete: true`; the stopping rules forbid recording it as a bound |
| Field restriction mistaken for the real question | A negative result over `Q(sqrt(d))` says nothing about `tau_5`, but reads as if it does | section 1.3 states it, the strength relation is `weaker`, and result shape R4 repeats it |
| Lattice-pool vacuity | A pool taken from one lattice cannot beat that lattice's kissing number, so the search is guaranteed to fail while looking rigorous | the frozen pool is deliberately a union of two structures; the ceiling note is recorded as an assumption so the next pool choice inherits it |
| Rounded numerical configuration | A floating-point optimizer's output rounded to rationals is the obvious shortcut and would put a float upstream of the certificate | section 7.5 forbids it; the checker's rejection probes are calibrated at `10^-6` so a rounded near-miss fails visibly |
| Gram-matrix shortcut | Presenting a Gram matrix is easier than coordinates and hides a positive-semidefiniteness and rank obligation | section 8.5 requires coordinates; the checker takes coordinates only |
| Order-decision error in `K` | A wrong sign decision for `a + b*sqrt(d)` silently changes every distance verdict | the exact rule is frozen in section 1.2 and the checker is probed with inputs straddling the boundary |
| Model-authored search program | Executing generated code is a capability ADR-0057 leaves disabled | section 12; programs are human-authored or the run does not happen |

## 12. Capability check

**Covered by existing AdaIvy capabilities.** Exact arithmetic over one real
quadratic extension `Q(sqrt(d))` with the radicand measured from the case values
rather than declared, which ADR-0035 already implements for the noncommuting
Phase 5 slice and which is exactly the arithmetic sections 1.2, 7, and 8 need.
The verifier-not-solver separation, also from ADR-0035: a certificate is checked
against the frozen predicate and its origin does not create trust. Exact
rational arithmetic. Declarative problem intake and the Phase 1 trust policy.
Deterministic serialization, content hashing, canonical records, and the
falsifiability-probe pattern from the Phase 6 generality suite, which sections
7.1 and 7.4 reuse. Machine-readable preservation of failed and incomplete
attempts. Bounded, no-network subprocess execution. The ADR-0055 pre-research
novelty re-check, which must cover section 6 and in particular the blocking
claim 6.3.

**Would require a new ADR.**

- **The `tau_5 <= 43` upper-bound route, in any form.** Its natural certificate
  is a floating-point LP or SDP bound, which under this repository's rules is
  evidence and not a theorem, and the repository owner rejects floating-point
  solvers outright. An exact version would need a rational feasible dual
  solution plus a verified exact duality argument and a checker for it. No such
  checker exists here. That is a new capability with its own ADR and acceptance
  suite, and until it exists the upper-bound direction is out of scope for this
  slice. This is the explicit reason the frozen target keeps only the
  lower-bound direction.
- Exact arithmetic over real algebraic number fields beyond one quadratic
  extension: two distinct surds in one configuration, or any extension of degree
  greater than `2`. That needs exact minimal-polynomial arithmetic and exact
  real-root isolation, and ADR-0035 already records the degree-three boundary as
  unresolved for the analogous Phase 5 case. Interval arithmetic with rational
  endpoints would be admissible for exclusion only, never to certify a
  configuration.
- A general exact combinatorial search harness if a future pool grows materially
  beyond the frozen `130` vertices, or if the node budget needs to be raised
  past what one bounded run can hold.
- Execution of a model-authored search program, which ADR-0057 leaves disabled
  until its digest-pinned OCI sandbox gate passes.
- Any parallel or distributed search, which needs ADR-0029 activation evidence.
- Acquisition of any row in section 5, a separate ADR-0050 authorization.

**Explicitly not activated.** No floating-point solver of any kind. No SDP or LP
surface. No new network path, no model call inside the arithmetic, no higher
search tier, no automated novelty or significance assessment.

## 13. Open questions before intake

1. **Blocking.** Is the best known lower bound for `tau_5` still `40`? If it is
   already `41` or higher, the frozen target is void, no run may start, and this
   dossier must be re-frozen at a higher count or on a different question. This
   is claim 6.3 and it must be settled by acquisition and by the ADR-0055
   re-check before intake, not during the run.
2. Does the operator accept restricting coordinates to one real quadratic field,
   given that it makes the target strictly weaker than `tau_5 >= 41` and that a
   negative result over the restricted class settles nothing about `tau_5`?
3. Is the frozen `130`-vector pool the right first pool, or does the operator
   prefer a pool built from a different pair of structures? The pool is the one
   design choice in the slice with no principled justification beyond avoiding
   the single-lattice ceiling.
4. What node budget is authorized for the step-4 search, and is the operator
   content that budget exhaustion yields result shape R3 rather than a bound?
5. Should the `tau_5 <= 43` direction be scoped as its own separate ADR for
   exact LP or SDP dual certificate checking, or set aside entirely?
6. Confirm that the intended deliverable is the checker, the verified baseline,
   the extension-infeasibility record, and a pool-restricted maximum, so that
   the predicted negative outcome is not judged a failure.
