# B3. Dense polynomials whose squares are sparse — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B3 (tier B)
**Declared domain:** polynomial-algebra
**Intake file:** docs/research-targets/intake/b3-dense-polynomial-sparse-square-v1.json
**Frozen in one line:** There is an explicit infinite family of integer
polynomials of strictly increasing degree `n`, all `n + 1` coefficients nonzero,
whose squares satisfy the exact integer inequality
`nnz(p^2)^5 <= 32 * n^4`.

This is a scoped intake package. It does not approve a formalization, establish
that the frozen target is open, authorize acquisition of any source, assess
novelty or significance, create mathematical warrant, or activate a capability.
Novelty, significance, and source applicability are `not_assessed`. The
formalization's approval status is `needs_clarification`, because the original
statement's one-instance threshold is missing from the supplied rendering and
this dossier did not reconstruct it. Section 13 names the missing item as an
operator question.

## 1. Frozen target

Fix the following. All polynomials are in `Z[x]`.

For `q in Z[x]`, `nnz(q)` is the number of indices `j >= 0` whose coefficient in
`q` is nonzero. `nnz(0) = 0`.

For an integer `n >= 0`, `D(n)` is the set of `p in Z[x]` with `deg p = n` such
that every one of the `n + 1` coefficients `a_0, a_1, ..., a_n` of `p` is a
nonzero integer. Call such a `p` **dense of degree `n`**. `D(n)` is nonempty,
since `1 + x + ... + x^n` lies in it.

**Frozen target claim.** There exist

- a strictly increasing sequence of positive integers `n_1 < n_2 < n_3 < ...`,
- an algorithm that, given `k >= 1`, outputs in finitely many exact integer
  operations the full coefficient vector of a polynomial `p_k in D(n_k)`,

such that for every `k >= 1` the exact integer inequality

`nnz(p_k^2)^5 <= 32 * n_k^4`

holds.

The inequality is the frozen exact form of `nnz(p_k^2) <= 2 * n_k^(4/5)`, with
the exponent `theta = 4/5` and the constant `C = 2` both frozen. It is stated
and tested only in the integer form: fifth powers of an integer count against
`32` times a fourth power of an integer. No logarithm, root, or floating-point
value appears anywhere in the target or in its verification.

The claim is existential: it asserts that such a family exists and is explicitly
producible. It is not a claim about every `n`, and section 2 records that
distinction as a rejected reading rather than a detail.

### The extremal function, defined here and completely

The planning dossier refers to "the associated extremal function" and to a
reported upper exponent `0.811` without supplying either definition. Neither is
taken from a source in this dossier. The following definitions are local, are
written here in full, and are what the frozen target relates to.

For `n >= 0` define

`Q(n) = min { nnz(p^2) : p in D(n) }`.

The minimum exists because `D(n)` is nonempty and `nnz(p^2)` takes values in the
finite set `{1, ..., 2n + 1}`. `Q` is the extremal function used throughout this
dossier. Two exponents attach to it:

`theta_inf = inf { t in Q, t > 0 : there is C in Q, C > 0, with Q(n) <= C n^t for infinitely many n }`

`theta_all = inf { t in Q, t > 0 : there is C in Q, C > 0, with Q(n) <= C n^t for all n >= 1 }`

and `theta_inf <= theta_all`, since a bound for all `n` is in particular a bound
for infinitely many `n`.

The frozen target entails `theta_inf <= 4/5`. It does **not** entail
`theta_all <= 4/5`, because a family supplies a bound only at the degrees `n_k`
it covers, and `Q` is not known here to be monotone or otherwise controlled
between them. That gap is deliberate and is recorded in section 4 as an
edge-case delta and in section 13 as an operator question, because which of the
two exponents the original statement uses is exactly one of the things the
damaged rendering lost.

### What was lost, and what was not reconstructed

The planning dossier states plainly that the supplied rendering loses part of
the one-instance threshold, and instructs that the original FrontierMath
statement and its extremal function be frozen before formalization, without
inferring the threshold from the damaged typography.

This dossier complies as follows. The value `0.811` is treated as an untrusted
comparison value and is used nowhere in the target, the formalization, the
slice, or any certificate. The frozen exponent `4/5` was chosen as a clean exact
rational strictly below it with a clear margin, so that the target is exactly
stated without depending on the untrusted value being right. The lost threshold
was **not** reconstructed. In particular, a numerical coincidence was noticed
and deliberately not used: the product-construction exponent described in
section 7 takes the form `log s / log(d+1)` for integers `s` and `d`, and small
integer pairs exist whose ratio rounds to `0.811`. Guessing the source's
mechanism from a rounded number and then adopting the guessed value as the
threshold would be exactly the inference the planning dossier forbids. No part
of this dossier depends on it, and the frozen target would be unchanged if the
coincidence were spurious.

Consequently the relation "the frozen exponent improves the reported bound" is
**not asserted**. `4/5 < 0.811` as rationals against a decimal, but whether that
constitutes an improvement depends on the source's definition of its extremal
function, on whether its exponent is the infinitely-many-`n` or the all-`n`
version, and on the exact form of its threshold. All three are unknown here.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| polynomial | element of `Z[x]`, coefficients exact integers | coefficients in `Q`, `R`, or a finite field; Laurent polynomials; multivariate |
| dense of degree `n` | `deg p = n` and all `n + 1` coefficients `a_0, ..., a_n` nonzero | `deg p <= n`; a positive proportion of coefficients nonzero; all coefficients positive; coefficients bounded |
| `nnz(q)` | the number of indices with nonzero coefficient in `q`, computed after full expansion | the number of terms written down before collecting; the degree; the number of monomials with coefficient of absolute value greater than one |
| `p^2` | the ordinary square in `Z[x]`, fully expanded and collected | a square modulo some `N` or some polynomial; a formal square with terms uncollected |
| `Q(n)` | `min { nnz(p^2) : p in D(n) }` | a minimum over `deg p <= n`; a minimum over primitive `p` only, which happens to be the same value but is a different definition; a minimum over rational coefficients |
| the exponent | `theta_inf`, the infimum of admissible `t` with `Q(n) <= C n^t` for infinitely many `n` | `theta_all`, the all-`n` version, which is a possibly strictly larger number and is a strictly stronger target; a `limsup log Q(n) / log n`, which needs its own justification to coincide with either |
| frozen `theta` | `4/5`, exactly, as a rational | any exponent strictly below `0.811`; an unspecified epsilon improvement; `0.811` itself; a value reverse-engineered from `0.811` |
| frozen `C` | `2`, exactly, giving the integer test `nnz(p^2)^5 <= 32 n^4` | an unspecified absolute constant; a constant allowed to depend on `k`; an ineffective constant |
| the inequality test | the exact integer comparison `nnz(p^2)^5 <= 32 * n^4` | a floating-point evaluation of `n^(4/5)`; a comparison of `log nnz / log n` against `0.8` in floating point; a fitted exponent from a table of small `n` |
| explicit family | an algorithm that on input `k` outputs the full coefficient vector of `p_k` in finitely many exact integer operations | a non-constructive existence proof; a family defined by an unbounded search; a family whose coefficients are defined only up to an unproved cancellation pattern |
| `0.811` | an untrusted comparison value from the planning notes, of unknown definition, used nowhere | the threshold the frozen target must beat; a known bound on `Q`; a value whose mechanism may be guessed |
| the one-instance threshold | missing from the supplied rendering, not reconstructed here, named as operator question 13.1 | anything inferable from the damaged typography |

## 3. Formalization and quantifiers

Typed informal statement, as it appears in the intake file:

`exists (n : N -> N) (p : N -> Z[x]) (A : Algorithm),`
`  StrictlyIncreasing(n) and`
`  forall k >= 1, A(k) = coefficient_vector(p k) and`
`                 degree(p k) = n k and`
`                 forall i in {0..n k}, coefficient(p k, i) != 0 and`
`                 nnz((p k)^2)^5 <= 32 * (n k)^4`

Quantifiers, in order and with their ranges:

- `exists n` a strictly increasing function from positive integers to positive
  integers, giving the degree sequence;
- `exists p` assigning to each `k >= 1` a polynomial in `Z[x]`;
- `exists A` an algorithm producing the coefficient vector of `p_k` from `k` in
  finitely many exact integer operations, which is what makes the family
  explicit;
- `forall k >= 1`, four conditions: the degree matches, all `n_k + 1`
  coefficients are nonzero, and the exact integer inequality holds;
- `forall i in {0, ..., n_k}` the coefficient is nonzero, inside that.

Every object quantified over is discrete and every relation is decidable on a
given instance: for a fixed `k`, checking the four conditions is a finite exact
integer computation. What is not finite is the `forall k`, and that is precisely
the part no table can supply.

The asymptotic in the planning dossier's "asymptotically few nonzero
coefficients" and "`O(n^theta)`" is discharged by fixing `C = 2` and requiring
the inequality for every `k`, rather than for `k` large. That is a strictly
stronger and simpler form: there is no threshold parameter to leave implicit. If
a construction satisfies the inequality only beyond some `k_0`, the family may
be re-indexed to start at `k_0`, so nothing is lost by the stronger form.

## 4. Semantic alignment to the source statement

The source statement, as rendered in the planning dossier, is: let
`p(x) = a_0 + a_1 x + ... + a_n x^n` have nonzero integer coefficients;
construct such polynomials whose squares have asymptotically few nonzero
coefficients, improving the reported upper exponent `0.811` for the associated
extremal function. The planning dossier also records that the rendering loses
part of the one-instance threshold.

**Quantifier mapping.** "construct such polynomials" maps to the existential
over a strictly increasing degree sequence together with an algorithm, so the
family is explicit rather than merely existent. "asymptotically few nonzero
coefficients" maps to the exact inequality `nnz(p_k^2)^5 <= 32 n_k^4` for every
`k`, which fixes both the exponent and the constant that the source rendering
leaves implicit. "improving the reported upper exponent" maps to nothing: no
comparison to `0.811` is part of the frozen claim.

**Definition mapping.** "nonzero integer coefficients" maps to `p_k in D(n_k)`,
all `n_k + 1` coefficients nonzero integers. "squares" maps to `p_k^2` in
`Z[x]`, fully expanded. "few nonzero coefficients" maps to `nnz`. "the
associated extremal function" maps to the locally defined
`Q(n) = min { nnz(p^2) : p in D(n) }`, which is this dossier's own definition
and is not claimed to be the source's. "the reported upper exponent `0.811`"
maps to an untrusted comparison value used nowhere.

**Assumption delta.** The frozen target adds: an exact exponent `4/5`; an exact
constant `C = 2`; the requirement that the inequality hold for every `k` rather
than eventually; and the requirement that the family be algorithmically
explicit. It removes: any comparison to the reported value `0.811`, and any
claim about the source's extremal function. It leaves undetermined, by
construction, whether the frozen exponent bears on the source's threshold at
all.

**Edge-case delta.** The family bounds `theta_inf` and not `theta_all`; the
all-`n` version is strictly stronger and is not claimed. `n_k` is required to be
strictly increasing but not to cover every degree, so nothing is claimed about
degrees outside the family. Degrees `0` and `1` are outside any useful family:
`Q(0) = 1` and `Q(1) = 3`, and the inequality `3^5 <= 32 * 1^4` is false, so
`n_k = 1` is inadmissible and the family must start higher. That is a property
of the frozen constants and is recorded rather than patched.

**Strength relation:** `unresolved`. The mapping to the source cannot be settled
before the source is acquired, because the source's threshold is missing and its
extremal function is undefined here. `equivalent` is unavailable in any case,
`weaker` would assert that the frozen claim is a special case of a statement
whose content is unknown, and `stronger` would assert the reverse. `unresolved`
is the only honest value.

## 5. Provenance and acquisition plan

Every row is `pending_acquisition` with applicability `not_assessed`.
Acquisition is human-planned, exact-URL, and separately authorized under
ADR-0050. Rows marked `locator_unknown` cannot be turned into a locator without
acquiring an earlier row first.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| FrontierMath open-problems index | `https://epoch.ai/frontiermath/open-problems`, the entry on dense polynomials with sparse squares | settles claims 6.1 and 6.2: the exact original statement, the exact one-instance threshold that the supplied rendering lost, and the exact definition of the extremal function the `0.811` figure refers to. This is the row that closes operator question 13.1 | pending_acquisition |
| The primary statement or problem file linked from that entry | `locator_unknown` until the row above is acquired | settles claim 6.3: whether the threshold is an all-`n` or infinitely-many-`n` bound, whether an explicit construction is required, and whether the constant must be effective | pending_acquisition |
| The construction attaining the reported exponent | `locator_unknown`; identified only by topic, since no reference can be named offline without risking a fabricated citation | settles claim 6.4, and decides whether the product construction in section 7 is the known route or a distinct one. Until this is acquired, any base polynomial the slice finds may already be published | pending_acquisition |
| Earlier work on sparse squares of dense polynomials | `locator_unknown`; the same route as the row above | would settle whether the exact lower bound `Q(n) >= 4` for `n >= 2` used in section 7 is standard, and whether stronger exact lower bounds on `Q` are known that would rule the frozen exponent out entirely | pending_acquisition |
| ADR-0051 bounded Crossref metadata discovery | one operator-initiated query whose terms are exact-normalized substrings of this file, for example `sparse squares` and `nonzero coefficients` | a discovery route only, to help identify the `locator_unknown` rows; results are untrusted inspiration candidates with relevance, applicability, novelty, and significance `not_assessed`, and they neither perform nor satisfy the ADR-0055 re-check | pending_acquisition |

The first row is unlike the corresponding row in the other tier B dossiers: it
is not merely needed before a status claim, it is needed before the
formalization can be approved at all. That is why the approval status is
`needs_clarification`.

## 6. Prior-status claims to re-check

Each claim is untrusted and none is a premise of the slice. The ADR-0055
pre-research novelty re-check must cover all of them.

**6.1 The supplied rendering loses part of the one-instance threshold.**
Recorded by the planning dossier itself. Treated here as true in the only
direction that matters — the threshold is unknown, so it is not used — and the
exact missing item is named in section 13.

**6.2 The reported upper exponent is `0.811`.** Untrusted, and additionally
unusable: the extremal function it refers to is not defined in the planning
dossier. It is used nowhere in this dossier. Whether the frozen exponent `4/5`
improves anything cannot be decided without this claim being resolved together
with 6.3.

**6.3 The exponent refers to a bound of a particular quantified shape.** Whether
the source's exponent bounds `Q(n)` for all large `n` or for infinitely many
`n`, and whether the constant is required to be effective, is unknown. The
frozen target bounds the infinitely-many version, which is the weaker of the
two, so a resolution in favour of the all-`n` version would mean the frozen
target does not address the source's quantity.

**6.4 A construction attaining the reported exponent exists and is published.**
Untrusted and unidentified. This is the rediscovery risk: a base polynomial
found by the slice may be exactly the published one. Section 7 therefore retains
the exhaustive frontier table, which is informative regardless of rediscovery,
rather than only the best base found.

**6.5 The FrontierMath index is the right locator.** The planning dossier's
source ledger describes that page as a discovery index for several candidates
and says exact individual statements still require acquisition. Untrusted as a
locator for this specific entry.

## 7. Bounded first slice

Offline, deterministic, exact-integer, human-authored. No model on the trust
path, no network, no model-generated program executed. Note that the slice may
run before the formalization is approved only in its exhaustive-table stage,
which depends on no source and produces exact statements about `Q`; the family
stage should wait on operator question 13.1, because the exponent it aims at may
change.

**Inputs.** The degree range `2 <= d <= d_max`, frozen at `d_max = 12`; the
coefficient bound `B in {1, 2, 3}`, so coefficients range over
`{-B, ..., -1, 1, ..., B}`; and the lift bound `(d+1)^k <= 10^6` for the family
verification stage. No table, published construction, or prior computation is an
input.

**Exact representation.** A polynomial is a list of exact Python integers of
length `deg + 1`, or, once sparse, a mapping from exponent to exact integer with
zero entries removed. `p^2` is computed by exact integer convolution and
collection; for sparse operands the convolution runs over the support only.
There is no floating-point value anywhere, and no modular reduction:
cancellation must be observed in `Z`, not modulo anything.

**Stage 1, the exhaustive frontier of `Q`.** For each `(d, B)` in the envelope,
compute exactly

`Smin(d, B) = min { nnz(p^2) : p in D(d), all coefficients in {-B..B} \ {0} }`,

which is an exact upper bound on `Q(d)` and equals `Q(d)` only if the true
minimizer has coefficients within the bound — a caveat that is part of every
recorded value. The search is depth-first over `a_0, a_1, ..., a_d`.

*Symmetry quotient.* `nnz(p^2)` is invariant under global negation `p -> -p`,
under `x -> -x`, which flips the sign of odd-index coefficients of both `p` and
`p^2`, and under reversal `p -> x^d p(1/x)`, which reverses the coefficient list
of both. It is also invariant under multiplying `p` by a nonzero integer, so the
search is restricted to primitive `p`, meaning the gcd of the coefficients is
`1`. The group generated by the first three has order at most eight, and the
search keeps only the lexicographically least coefficient vector in each orbit.
Every quotient step is exact and each is separately checked by recomputing
`nnz(p^2)` for a random-free, fixed sample of orbit members and requiring exact
equality.

*Pruning.* The coefficient of `x^i` in `p^2` is `sum over u + v = i of a_u a_v`,
so it depends only on `a_0, ..., a_i`. A prefix `a_0, ..., a_j` therefore
determines the coefficients of `x^0` through `x^j` in `p^2` exactly. Moreover
the coefficients of `x^{2d}` and `x^{2d-1}` in `p^2` are `a_d^2` and
`2 a_{d-1} a_d`, both nonzero, so at least two nonzero coefficients lie above
index `j` whenever `j <= 2d - 2`. The search prunes a prefix when the nonzero
count already determined, plus that lower bound of two, exceeds the current
best. Both facts are stated as lemmas with proofs, and for `d <= 6` and `B <= 2`
the pruned search is cross-checked against unpruned enumeration of all
`(2B)^{d+1}` coefficient vectors; any divergence halts the run.

*Envelope size.* Unpruned, the envelope is `sum over d, B of (2B)^{d+1}`
coefficient vectors, which at `d = 12, B = 3` alone is `6^13`, on the order of
`10^10`; the quotient divides that by at most eight and the pruning is expected
to remove most of the remainder. Visited nodes are capped at `10^11` and the
reached `(d, B)` is a measured output rather than a promise.

*Two exact facts the slice uses and does not assume.* First, `Q(n) >= 4` for
`n >= 2`: the coefficients of `x^0`, `x^1`, `x^{2n-1}`, `x^{2n}` in `p^2` are
`a_0^2`, `2 a_0 a_1`, `2 a_{n-1} a_n`, `a_n^2`, all nonzero, and the four
indices are distinct when `n >= 2`. Second, the bound is attained at `n = 2`:
`p = 1 + 2x - 2x^2` has `p^2 = 1 + 4x - 8x^3 + 4x^4`, so `Q(2) = 4`. Both are
recomputed inside the run.

**Stage 2, the product lift and its exact criterion.** Given a base `p in D(d)`
with `s = nnz(p^2)`, define

`P_k(x) = product over j = 0 to k-1 of p(x^{(d+1)^j})`.

Then the support of `P_k` is exactly the set of integers with a `k`-digit
base-`(d+1)` representation using digits `0..d`, which is every integer in
`[0, (d+1)^k - 1]` exactly once, so `P_k` is dense of degree `n_k = (d+1)^k - 1`
and each of its coefficients is a single product of `k` nonzero base
coefficients and hence nonzero. The support of `P_k^2` is contained in the set
of digit sums with digits from the support of `p^2`, giving `nnz(P_k^2) <= s^k`;
merging and cancellation can only reduce the count, so no cancellation lemma is
needed in this direction. If the base satisfies the exact integer criterion

`s^5 <= (d + 1)^4`

then
`nnz(P_k^2)^5 <= s^{5k} <= (d+1)^{4k} = (n_k + 1)^4 <= 16 n_k^4 <= 32 n_k^4` for
every `k >= 1`, which is the frozen target's inequality with `C = 2`. Combined
with `Q(n) >= 4`, the criterion `s^5 <= (d+1)^4` forces `4^5 = 1024 <= (d+1)^4`,
so `d >= 5`: no base of degree below five can reach the frozen exponent by this
route, whatever its coefficients. That is an exact restriction on where the
search can possibly succeed and it is derived, not assumed.

The slice evaluates the criterion for every `(d, B)` in the Stage 1 table by
exact integer comparison of `Smin(d,B)^5` against `(d+1)^4`. No logarithm is
computed.

**Stage 3, finite verification of a candidate family.** For each base satisfying
the criterion, construct `P_k` for `k = 1, 2, ...` while `(d+1)^k <= 10^6`,
compute `P_k^2` by exact sparse convolution, and check
`nnz(P_k^2)^5 <= 32 n_k^4` exactly. This is a consistency check on the lemmas of
Stage 2. It is not the family theorem, and a table of verified `k` is recorded
as a table.

**Stage 4, the family theorem.** The three lemmas of Stage 2 — unique base
representation giving density, support containment giving `nnz(P_k^2) <= s^k`,
and the exact integer chain giving the frozen inequality — are recorded as proof
obligations and discharged symbolically or not at all. Only their discharge,
plus one base satisfying the criterion, proves the frozen target.

**Boundary of the claim the slice can support.** Stage 1 supports exact
statements of the form: no dense polynomial of degree `d` with coefficients
bounded by `B` has a square with fewer than `Smin(d,B)` nonzero coefficients,
and hence `Q(d) <= Smin(d,B)`. Stage 2 supports exact statements about which
bases do or do not satisfy the criterion. Stage 3 supports exact statements
about the finitely many `k` it checked. None of the three, alone or together,
supports the frozen target, which quantifies over all `k`; only Stage 4 does.
Conversely, a negative Stage 1 result is genuinely informative: if no base in
the envelope satisfies the criterion, then the frozen exponent is unreachable by
the product construction from any base inside the envelope, which is an exact
exclusion and not a failure of search.

## 8. Certificate and verifier contract

**S1, exact minimum in a coefficient box.** Certificate: `(d, B)`; the value
`Smin(d,B)`; one attaining coefficient vector; the full coefficient vector of
its square as `2d + 1` exact integers; the symmetry quotient used with its
representative rule; the pruning lemmas; and the visited-node count. Verifier:
recompute the square by exact convolution independently of the search, compare
all `2d + 1` coefficients by integer equality, recount the nonzeros, and replay
the exhaustion. The verifier shares no code with the search.

**S2, base satisfying the criterion.** Certificate: the base coefficient vector;
its square's full coefficient vector; `s = nnz(p^2)`; and the two integers `s^5`
and `(d+1)^4` with the verdict. Verifier: recompute the square, recount, and
recompute both fifth and fourth powers as exact integers. The comparison is
integer, never a ratio of logarithms.

**S3, finite lift verification.** Certificate: the base; `k`; the sparse
representation of `P_k^2` as exponent-to-integer pairs; `nnz(P_k^2)`; `n_k`; and
the two integers `nnz^5` and `32 n_k^4`. Verifier: rebuild `P_k` from the base
by the stated product rule, square it by exact sparse convolution, compare the
support and coefficients exactly, and recheck the integer inequality. Labelled a
consistency check on Stage 4's lemmas and never a family result.

**S4, the family theorem.** Certificate: the base with its S2 certificate; the
construction rule; and symbolic proofs of the three lemmas, each stated with its
hypotheses. The S3 tables may accompany it as consistency data and contribute
nothing to its status. This is the only shape that establishes the frozen
target.

**S5, bounded exclusion.** Certificate: the full envelope specification; the
Stage 1 table of `Smin(d,B)`; the criterion verdict for each entry; and the
statement of exactly what is excluded, namely that no base inside the envelope
reaches the frozen exponent by the product construction. Verifier: replay any
sampled entry by full re-search and require exact agreement.

**Refused as a certificate, in every shape.** Any floating-point value,
including `log s / log(d+1)` or `n^0.8` computed in floating point. An exponent
fitted to a table of small `n`. A model's assertion that a construction
generalizes, or that a cancellation pattern continues. A published construction
or exponent used without acquisition and replay. Failure of the Stage 1 search
read as a lower bound on `Q`. A verified S3 table at every `k` in the envelope,
presented as S4.

## 9. Useful negative outcomes

- The Stage 1 table of `Smin(d,B)` for the whole reached envelope, with a
  witness polynomial and its exact square for each entry, content-hashed. These
  are exact upper bounds on `Q(d)` and are permanently useful whichever way the
  target resolves.
- The criterion verdict per entry, which converts the table into the exact
  exclusion statement of shape S5: the product route cannot reach `theta = 4/5`
  from any base inside the envelope. That is the most likely outcome of a first
  run and is a real result about the route rather than about the target.
- The derived exact restriction `d >= 5`, with its proof, which narrows any
  future search whatever the envelope.
- Every candidate base that satisfied the criterion but whose lift failed an S3
  check, together with the exact `k` at which it failed. Such a failure would
  indicate a defect in the Stage 2 lemmas rather than in the base, and is
  retained as an acceptance fixture.
- Every alternative construction rule tried and refuted, with the exact instance
  that broke it. The product rule is one route; a refuted second route is a
  permanent narrowing.
- The measured cost profile per `(d, B)`, which is the only honest input to an
  ADR-0029 request for a larger envelope, and which makes clear whether reaching
  `d = 13` or `B = 4` is a budget question or a method question.
- The record that the family stage was blocked on operator question 13.1, if it
  was, so that a later run does not silently adopt a different exponent.

## 10. Evaluation protocol

Mirrors the intake file exactly.

Phase: `exploratory`. Version: `1`.

Metrics:

- `coefficient_boxes_exhausted`
- `minimal_square_supports_certified`
- `bases_meeting_exact_criterion`
- `lift_degrees_verified_exactly`
- `construction_routes_refuted`
- `independent_verifier_replays_passed`
- `proof_obligations_opened`
- `proof_obligations_closed`
- `operator_questions_outstanding`
- `model_cost_usd`

Success criteria:

- `an explicit family with all three lemmas discharged symbolically, satisfying nnz(p_k^2)^5 <= 32 n_k^4 for every k`
- `a base polynomial certified to satisfy the exact criterion s^5 <= (d+1)^4, with the family lemmas left as named open obligations`
- `an exact bounded exclusion stating that no base inside the reached envelope reaches the frozen exponent by the product construction`
- `an explicit unresolved outcome that names the smallest remaining obligation, together with the retained frontier table and every refuted construction route`

Stopping rules:

- `stop on a certified base meeting the exact criterion and move the budget to the family lemmas rather than to a larger envelope`
- `stop when fresh model spend reaches USD 20`
- `stop when two consecutive review points close no proof obligation and refute no route`
- `stop when visited search nodes exceed 10^11 or a lift would exceed degree 10^6`
- `never promote a finite table of verified k to the family theorem, and never promote failure of the bounded search to a lower bound on the extremal function`
- `do not run the family stage while the missing one-instance threshold remains an outstanding operator question, because the exponent it aims at may change`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Reconstructing the lost threshold | The planning dossier forbids inferring it from damaged typography, and a plausible reverse-engineering exists, so the temptation is concrete | `0.811` is used nowhere; the frozen exponent is an independently chosen exact rational; the noticed numerical coincidence is recorded as deliberately unused; approval status is `needs_clarification` and question 13.1 names the missing item |
| Claiming an improvement | `4/5 < 0.811` looks like an improvement and is not one until the source's extremal function and quantifier shape are known | The frozen claim contains no comparison; section 4 states that the improvement relation is not asserted; the strength relation is `unresolved` |
| Wrong exponent variant | If the source's exponent is the all-`n` version, the frozen target bounds a different quantity | Both variants are defined in section 1; the entailment is stated as `theta_inf <= 4/5` only; question 13.2 asks which is intended |
| A table read as a family theorem | Stage 3 verifies the inequality for every `k` in its range, which looks conclusive | S4 is the only shape that establishes the target; S3 is labelled a consistency check; a stopping rule forbids the promotion |
| Floating point entering by the back door | The natural way to compare exponents is `log s / log(d+1)`, and the natural way to test `n^0.8` is a float power | Every comparison is frozen in integer form, `s^5 <= (d+1)^4` and `nnz^5 <= 32 n^4`; floats are refused as certificates in every shape |
| Failure of search read as a bound | Stage 1 exhausts a coefficient box, not `D(d)`, so it bounds `Q` only from above | Every recorded value carries the box caveat; a stopping rule states that failure is never a lower bound on `Q` |
| Rediscovery of the published base | Claim 6.4 is unidentified, so a found base may be the known one | The retained deliverable is the frontier table and the exclusion statement, which are informative either way; no novelty claim before the ADR-0055 re-check |
| Search explosion | The unpruned envelope at the top corner is on the order of `10^10` vectors | Exact symmetry quotient, prefix pruning with proved lemmas, unpruned cross-check at small `(d,B)`, node cap, and a measured reached envelope |
| Unsound pruning or quotient | Either would silently shrink the search and make `Smin` too large, corrupting the exclusion statement in the dangerous direction | Both pruning facts are lemmas with proofs; the quotient is checked by recomputing `nnz` on fixed orbit members; the unpruned cross-check runs at small `(d,B)` |
| Model-generated search code executed | The search and both verifiers are the whole exclusion argument | Human-authored repo code only; ADR-0057 keeps production generated-code execution disabled |

## 12. Capability check

**Covered by existing AdaIvy capabilities.** Declarative problem intake with
canonical hashing. Exact arbitrary-precision integer arithmetic from the
standard library, which is all that convolution, the symmetry quotient, and both
verifiers need. Deterministic serialization, content hashing, and the
append-only record path for certificates and preserved failures. The offline
`make check` harness, with no network, model provider, or container runtime. The
ADR-0047 bounded central-lead runtime for the construction-route stage, as
composed one-round Phase 2 runs with a size-bounded proposer-only ledger and
model-free replay. The ADR-0036 publication projection, which would render the
family theorem as a `Conjecture` unless its environment is computed otherwise,
and which would print the absence of publication approval. The ADR-0055
pre-research novelty re-check.

**Available but separately authorized, not activated by this dossier.** The
ADR-0050 public unauthenticated exact-URL acquisition path is the right shape
for the FrontierMath row in section 5, and that row still needs its own
human-planned authorization; it is also the row that must be acquired before the
formalization can move off `needs_clarification`. The ADR-0051 bounded Crossref
metadata query is the right shape for the `locator_unknown` rows and yields
untrusted inspiration candidates only.

**Would require a new ADR.**

- Execution of any model-generated search, convolution, or verifier code.
  ADR-0057 keeps production generated-code execution disabled pending its own
  sandbox gate, and the exclusion statement of shape S5 depends entirely on the
  search being the code that was reviewed.
- A kernel-checked proof of the three family lemmas. Phase 3B checks a frozen
  theorem supplied to it; there is no formalization of `nnz`, of `D(n)`, or of
  the product construction in the repository, and producing one is a separate
  scope decision.
- Any computer-algebra dependency for polynomial arithmetic. None is needed —
  exact integer convolution over lists and dictionaries suffices — and adding
  one would require pinning and license recording under the standing engineering
  rules.
- Any parallel, specialist, evolutionary, or higher-tier search over the
  coefficient boxes, which needs the ADR-0029 recorded prediction and measured
  retention gain first. The Stage 1 cost profile is measured precisely so that
  such a request could later be made honestly.

## 13. Open questions before intake

These are the reason the formalization's approval status is
`needs_clarification`. Question 13.1 is the missing item the planning dossier
warned about, named exactly.

1. **The missing one-instance threshold.** What is the exact acceptance
   threshold in the original FrontierMath statement — the precise numerical
   value, the direction and strictness of the inequality, and any constant
   attached to it — that a single submitted instance must satisfy? The supplied
   rendering lost it. This dossier did not infer it from the damaged typography,
   does not use `0.811` as a threshold, and froze its own exponent `4/5` and
   constant `2` instead. Until this is answered, no submission can be checked
   against the source's bar and no improvement claim can be made.
2. **Which exponent.** Is the source's extremal function bounded for all large
   `n` or for infinitely many `n`, and is its exponent an infimum of admissible
   `t`, a `limsup` of `log Q(n) / log n`, or something else? The frozen target
   bounds the infinitely-many version only.
3. **The source's extremal function.** What exactly does the source's function
   measure — `min nnz(p^2)` over dense `p` of degree exactly `n`, as defined
   here, or a variant over `deg p <= n`, over a positive-proportion density
   condition, or with a different coefficient ring?
4. **Explicitness and effectivity.** Does the source require an explicit
   construction and an effective constant, or does existence suffice? The frozen
   target requires both, which may be strictly stronger than asked.
5. **Envelope.** Is `d_max = 12` with `B` up to `3` the intended first envelope,
   given that the derived restriction `d >= 5` means only degrees `5` to `12`
   can possibly satisfy the criterion, and that the top corner dominates the
   cost?
6. **Frozen exponent.** If the operator prefers a target that is unambiguously
   an improvement once question 13.1 is answered, the exponent should be
   re-frozen then, in a new dossier version rather than by editing this one.
