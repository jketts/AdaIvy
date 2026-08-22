# B6. Chowla's cosine problem — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B6 (tier B)
**Declared domain:** harmonic-analysis
**Intake file:** docs/research-targets/intake/b6-chowla-cosine-negative-excursion-v1.json
**Frozen in one line:** there exists an explicitly presented infinite sequence
of finite sets `A_k` of positive integers with `card(A_k)` strictly increasing
and a computable `K` such that `m(A_k) <= eps * card(A_k)` for every rational
`eps > 0` and every `k >= K(eps)`, where `m(A) = -min_(x in [0, 2 pi))
sum_(a in A) cos(a x)`.

This is a scoped intake package and nothing more. It does not approve a
formalization, does not establish that the question is open, does not authorize
source acquisition, and does not activate any capability. Novelty,
significance, and source applicability are `not_assessed`, and no statement here
creates mathematical warrant, graph admission, or proof status. The intake file
carries `approval_status: needs_clarification`, because the planning dossier
requires the normalization, the domain for `x`, and the meaning of negative
excursion to be copied from a primary source that is not acquired here; all
three are therefore authored locally and flagged for the operator in §13.

## 1. Frozen target

All three contested conventions are defined completely in §2 before the target
is stated. The definitions used below are exactly those.

Frozen statement. There exists an explicitly presented sequence of finite
nonempty sets `A_1, A_2, ...` of positive integers with `card(A_k)` strictly
increasing in `k`, together with a computable function `K` from positive
rationals to positive integers, such that

```
forall eps in Q with eps > 0, forall k >= K(eps),  m(A_k) <= eps * card(A_k),
```

where

```
f_A(x) = sum_(a in A) cos(a x)    and    m(A) = -min_(x in [0, 2 pi)) f_A(x).
```

Symbols. `A_k` is a finite nonempty set of distinct positive integers.
`card(A_k)` is its number of elements. `f_A` is the cosine sum with every
coefficient exactly `1`. `m(A)` is the negative excursion, the magnitude of the
most negative value `f_A` takes; it is a nonnegative real, and §3 records why.
`eps` ranges over positive rationals so that the inequality is exactly
statable. `K` is required to be computable, so a claimed family can be checked
at a named index rather than only asserted asymptotically.

Epsilon form is the frozen form. The planning dossier writes the target as
`o(card(A))`; the frozen statement above is its explicit epsilon form with a
computable threshold. An unquantified "improved constant", or a single set with
a good ratio, does not meet the target.

Target scope is `existential`: one explicitly presented family is wanted. The
problem type is `explore`, because the frozen statement fixes no direction and a
proof that no such family exists would also be an acceptable outcome. Note
carefully that a published lower bound of the shape `m(A) >= c * card(A)` with
`c > 0` would refute the target outright; whether such a bound exists is unknown
here and is §6.3.

The constants `1` and `1/20` in the operator notes are not in the target. They
are untrusted comparison values whose quantity, direction, normalization, and
exponent are all unknown here, and they are recorded in §6.1 rather than used as
thresholds.

## 2. Definitions and conventions

Complete local definitions, in this dossier's own words, of the three items the
planning dossier said must come from the primary source.

**Normalization.** `f_A(x) = sum_(a in A) cos(a x)`, with every coefficient
exactly `1`, and `f_A` is not rescaled. The comparison denominator in the target
inequality is `card(A)`, the number of elements of `A`. Nothing is divided by
`card(A)`, by `sqrt(card(A))`, or by any `L^p` norm; nothing is weighted.

**Domain for `x`.** `x` ranges over the real interval `[0, 2 pi)`. Every element
of `A` is an integer, so `f_A` is `2 pi`-periodic and this interval realizes
every value `f_A` takes on the real line. The choice therefore loses nothing and
is not a restriction.

**Negative excursion.** `m(A) = - min_(x in [0, 2 pi)) f_A(x)`, the magnitude of
the most negative value of `f_A`. It is a single nonnegative real number
attached to `A`.

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| `A` | a finite nonempty set of distinct positive integers | a multiset with multiplicities; a set of reals; a set of arbitrary integers; a set containing `0` |
| `0` in `A` | excluded, because `cos(0 x) = 1` adds a constant that shifts every value and changes the meaning of the excursion | admitted as a harmless element |
| coefficients | all exactly `1` | arbitrary real or integer coefficients `c_a`; signs `+-1`; weights summing to `1` |
| normalization | none; the comparison denominator is `card(A)` | `f_A / card(A)`; `f_A / sqrt(card(A))`; comparison against `card(A)^theta` with `theta != 1` |
| domain for `x` | the real interval `[0, 2 pi)` | `[0, pi]`; a proper arc bounded away from `0`; rational multiples of `pi`; the integers; `[0, 2 pi)` with `0` removed |
| negative excursion `m(A)` | `-min f_A` over the frozen domain | the signed `min f_A`; the integral of the negative part; `max abs(f_A)`; the largest negative coefficient on the Fourier side |
| `o(card(A))` | the epsilon form with a computable threshold `K(eps)` | any asymptotic claim without a computable threshold; a single set with a small ratio; an improved constant in an unstated inequality |
| explicitly presented family | a rule that outputs `A_k` from `k` by an exact finite computation | an existence proof for a family; a probabilistic or random construction with no explicit output; a family defined by an unproved selection |
| certified bound | an exact certificate as fixed in §8 | a floating-point evaluation at any precision; a plot; a numerical minimizer's output; a sampled minimum |

**The exact reduction that makes all of this computable.** For every nonnegative
integer `a`, `cos(a x) = T_a(cos x)`, where `T_a` is the Chebyshev polynomial of
the first kind with integer coefficients, given by `T_0 = 1`, `T_1(c) = c`, and
`T_(k+1)(c) = 2 c T_k(c) - T_(k-1)(c)`. Hence

```
f_A(x) = P_A(cos x)   with   P_A = sum_(a in A) T_a   in Z[c],
```

and since `cos x` sweeps exactly `[-1, 1]` as `x` sweeps `[0, 2 pi)`,

```
min_(x in [0, 2 pi)) f_A(x) = min_(c in [-1, 1]) P_A(c).
```

The analytic problem becomes exact minimization of a univariate integer
polynomial over a rational interval. This is the whole reason the item can be
handled without floating point at all, and it is why §8 can refuse numerical
evaluation without leaving the slice without a method.

## 3. Formalization and quantifiers

Formal statement, in the typed informal register used by the intake file:

```
exists an explicitly presented sequence (A_k)_(k>=1) of finite nonempty
  subsets of the positive integers with card(A_(k+1)) > card(A_k),
exists a computable K : Q_(>0) -> N,
forall eps in Q with eps > 0,
forall k >= K(eps),
  m(A_k) <= eps * card(A_k),
where m(A) = - min_(x in [0, 2 pi)) P_A(cos x)
  and P_A = sum_(a in A) T_a in Z[c]
```

Quantifier list, as frozen in the intake file:

- `exists` an explicitly presented sequence `(A_k)` of finite nonempty sets of
  positive integers with strictly increasing cardinality.
- `exists` a computable `K` from positive rationals to positive integers.
- `forall` rational `eps > 0`.
- `forall k >= K(eps)`.
- `min` over `x in [0, 2 pi)`, equivalently `min` over `c in [-1, 1]` of the
  integer polynomial `P_A`.

Two facts fix the shape of the quantity being bounded, and both are standard.
`f_A` is continuous and `2 pi`-periodic, so its minimum is attained. The mean of
`cos(a x)` over a full period is `0` for every nonzero integer `a`, so the mean
of `f_A` is `0`, hence `min f_A <= 0` and `m(A) >= 0`. The target is therefore a
statement about how small a nonnegative quantity can be driven, never about a
sign change. It is also exactly why `0` is excluded from `A`: with `0` admitted
the mean would be `1` and `m(A)` could be `0`.

The degree of `P_A` is `max(A)`, not `card(A)`. Certificate cost is therefore
driven by the largest element of `A` and a family with few but enormous elements
is admissible under the target and expensive to certify. This is in §11.

## 4. Semantic alignment to the source statement

Quantifier mapping.

| Planning phrase | Frozen quantifier |
|---|---|
| construct arbitrarily large finite sets `A` | `exists` an explicitly presented sequence `(A_k)` with `card(A_k)` strictly increasing |
| in the domain fixed by the original problem | `x in [0, 2 pi)`, frozen locally because the original domain is not acquired |
| the magnitude of the negative excursion is `o(card(A))` | `forall` rational `eps > 0`, `forall k >= K(eps)`, `m(A_k) <= eps * card(A_k)` with `K` computable |
| `f_A(x) = sum_(a in A) cos(a x)` | `P_A(cos x)` with `P_A = sum_(a in A) T_a` in `Z[c]` |

Definition mapping.

| Term | Local meaning |
|---|---|
| negative excursion | `m(A) = -min` over `x in [0, 2 pi)` of `f_A(x)`, a nonnegative real |
| normalization | coefficients exactly `1`, no scaling of `f_A`, comparison denominator `card(A)` |
| domain for `x` | the real interval `[0, 2 pi)`, which is the full real range by `2 pi`-periodicity |
| `A` | a finite nonempty set of distinct positive integers, not a multiset and not containing `0` |
| `o(card(A))` | the explicit epsilon form with a computable threshold `K(eps)` |
| improved constant | a rejected reading of the target; a single better ratio for one set does not meet the frozen statement |

Assumption delta.

- All three conventions the planning dossier told us to copy from the primary
  source are instead authored locally, because no source is acquired. This is
  recorded as the reason `approval_status` is `needs_clarification`.
- The Chebyshev reduction is added so that the target is an exact statement
  about integer polynomials on `[-1, 1]` rather than an analytic statement
  requiring evaluation of transcendental functions.
- The constants `1` and `1/20` from the notes are excluded from the target
  entirely rather than reinterpreted as thresholds.
- A computable threshold function `K` is required, which is stronger than an
  unquantified asymptotic statement and is required so that any claimed family
  is checkable at a stated index.

Edge-case delta.

- `m(A) >= 0` always, so the target is a statement about how small a nonnegative
  quantity can be made, never about a sign change.
- A singleton `A = {1}` gives `P_A(c) = c`, minimum `-1`, so `m(A) = 1` and the
  ratio is `1`. The smallest cases are exactly computable and serve as verifier
  fixtures.
- `A = {1,2}` gives `P_A(c) = 2c^2 + c - 1` with exact minimum `-9/8` at
  `c = -1/4`, so `m(A) = 9/8` and the ratio is `9/16`. The minimizing point is a
  real algebraic number and not a root of unity, which makes it a useful test of
  the algebraic-point machinery.
- If `0` were admitted into `A` the mean of `f_A` would be `1` rather than `0`
  and `m(A)` could be `0`, which is why `0` is excluded.
- The degree of `P_A` is `max(A)`, so certificate cost is driven by the largest
  element and not by `card(A)`; a family with small cardinality and huge
  elements is admissible under the target but expensive to certify.

Strength relation: `unresolved`. The primary source's normalization, domain, and
definition of negative excursion are not acquired, so the mapping from this
frozen statement to the published problem cannot be settled here. Until the
operator supplies them, no result under this intake may be described as a result
about the published problem.

## 5. Provenance and acquisition plan

Every row is `pending_acquisition` and every applicability judgement is
`not_assessed`. No DOI is asserted from memory: where the locator is not known
offline the row records the exact resolution procedure instead of a guess.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Operator's supplied candidate notes, received 21 August 2026 | local artifact held by the operator; must be supplied as a file, not paraphrased | fixes §6.1, in particular what the constants `1` and `1/20` were attached to as received | pending_acquisition, applicability not_assessed |
| The concrete benchmark version of the problem referred to in the notes | `https://epoch.ai/frontiermath/open-problems` as the discovery index recorded in the planning dossier's source ledger, then the individual problem page it links, acquired by exact URL under ADR-0050 | settles §13 Q1 to Q4: the exact normalization, domain, excursion definition, and any verifier contract the benchmark fixes | pending_acquisition, applicability not_assessed |
| Primary statement of Chowla's cosine problem | `locator_unresolved`; resolve by one ADR-0051 Crossref query with the operator-supplied terms `Chowla cosine problem` and `negative excursion of cosine sums`, both exact normalized substrings of this dossier once supplied as local context, then acquire the returned DOI under ADR-0050 | settles §6.2; the acquisition target is the statement paragraph and the definition of the excursion, cited at passage level | pending_acquisition, applicability not_assessed |
| Best known lower bound on the negative excursion | `locator_unresolved`; same ADR-0051 route with the term `lower bound for the minimum of a cosine sum` | settles §6.3, which decides whether the frozen target is already known impossible | pending_acquisition, applicability not_assessed |
| Any published construction achieving a small excursion | `locator_unresolved`; same ADR-0051 route with the term `construction with small negative excursion` | settles §6.3 in the other direction, and would make this slice a reproduction | pending_acquisition, applicability not_assessed |

ADR-0050 acquisition is human-planned, exact-URL, public, unauthenticated and
separately authorized. ADR-0051 discovery is one human-started request returning
at most ten untrusted inspiration candidates and creates no relevance,
applicability, acquisition, novelty, significance, graph-admission or warrant
effect. Nothing here authorizes either. Until the second row is acquired, the
locally authored definitions of §2 stand and the intake stays
`needs_clarification`.

## 6. Prior-status claims to re-check

Each item is an untrusted inherited report, is used as a premise nowhere in §7
or §8, and must be covered by the ADR-0055 pre-research novelty re-check bound
to this problem definition's subject hash before research starts.

1. **Untrusted.** "The operator notes refer to a concrete benchmark version and
   compare constants `1` and `1/20`." Which quantity those constants bound, in
   which direction, under which normalization, and against which exponent of
   `card(A)` are all unknown here. They are recorded as comparison values and
   are not targets, thresholds, or success criteria.
2. **Untrusted.** The primary source's normalization, domain for `x`, and
   definition of negative excursion. The definitions in §2 are authored locally
   and may not coincide with the published ones.
3. **Untrusted, and decision-relevant before any spend.** Whether the frozen
   target is already settled in either direction. A published lower bound of the
   shape `m(A) >= c * card(A)` with `c > 0` refutes it outright, and a published
   construction settles it positively and makes this slice a reproduction. The
   re-check must resolve this first, because otherwise the slice may be
   searching for an object already proved not to exist.
4. **Untrusted.** That the problem is open at all, and the planning dossier's
   framing of "an improved constant or asymptotic bound" as useful progress. The
   frozen target is the epsilon form only; an improved constant in an unstated
   inequality is not a frozen target and cannot be reported as progress against
   one.

## 7. Bounded first slice

Because the intake is `needs_clarification`, the first slice is deliberately
confined to work that survives any operator answer: the exact certificate
machinery, validated against cases whose values are derivable by hand. No search
for a family starts before §13 Q1 to Q4 are answered and §6.3 is resolved.

Inputs. No external data. The definitions of §2. A frozen list of small sets for
which the exact answer is independently derivable.

Algorithms and arithmetic, all exact.

1. Build `T_a` in `Z[c]` by the integer recurrence of §2, with unbounded
   integer coefficients. Build `P_A = sum_(a in A) T_a` exactly.
2. For a rational candidate bound `B > 0`, form `Q = P_A + B` and clear
   denominators to an integer polynomial. Decide whether `Q` has a real root in
   `[-1, 1]` by a Sturm sequence over `Q`, computed with exact rational
   arithmetic. Evaluate `Q` exactly at one rational `c_0` in `[-1, 1]`.
3. If `Q` has no root in `[-1, 1]` and `Q(c_0) > 0`, then `Q > 0` throughout
   `[-1, 1]` by the intermediate value theorem, so `min P_A > -B` and
   `m(A) < B`. This is the tier-one certificate and it is entirely rational.
4. Find the least certified `B` by exact rational bisection on `B`, which
   terminates at any prescribed rational granularity. The bisection is exact
   throughout; it never evaluates a cosine.
5. Validate the stack against the frozen fixtures. `A = {1}` must give
   `P_A(c) = c` and refuse every `B <= 1` while certifying every `B > 1`.
   `A = {1,2}` must give `P_A(c) = 2c^2 + c - 1`, refuse every `B <= 9/8`, and
   certify every `B > 9/8`; at `B = 9/8` the polynomial `Q` has a double root at
   `c = -1/4`, so the certificate correctly declines the boundary case and the
   run records that declining as the expected behaviour rather than a failure.

Search envelope and size. The cost of a Sturm sequence is driven by
`deg P_A = max(A)` and by coefficient growth in the remainder sequence, both of
which are recorded exactly per run. The frozen fixture envelope for the first
slice is `max(A) <= 32` and `card(A) <= 8`, chosen before the run and not tuned
afterwards.

What is exhaustive versus what is sampled. Nothing is sampled. Every reported
bound is a certificate, and the search over `B` in step 4 is an exact bisection
whose output is a certified rational bound plus a refuted rational bound
bracketing the truth.

Boundary of the claim the slice can support. Certifying `m(A_k) <= B_k` for
finitely many `k` supports exactly those finitely many statements. It does not
establish the asymptotic target, does not establish a trend, and is not evidence
for the target. The asymptotic statement requires a proof about the family with
a computable `K`, which is a separate obligation the slice does not attempt.

Exploration lane, off the trust path. A floating-point plot or a numerical
minimizer may propose a candidate family or a candidate `B`. Its output is
labelled exploration-only, never recorded as a bound, and reaches the record
only after step 3 accepts an exact certificate.

## 8. Certificate and verifier contract

The one non-negotiable rule for this item: **no floating-point evaluation of a
cosine sum is a bound**, at any precision, with any informally attached error
estimate, over any number of sample points. Three exact routes are admitted and
nothing else is.

**Route 1, the frozen tier-one certificate: certified analytic bound with exact
rational error terms.** To certify `m(A) < B` for a rational `B > 0`, supply the
set `A`, the rational `B`, the integer polynomial `Q` obtained from `P_A + B` by
clearing denominators, the Sturm sequence of `Q` over `Q`, the sign sequences at
`-1` and at `1`, and one rational `c_0` in `[-1, 1]`. The independent verifier
rebuilds `P_A` from `A` by the Chebyshev recurrence rather than trusting the
supplied polynomial, rebuilds `Q`, recomputes the Sturm sequence and both sign
sequences in exact rational arithmetic, confirms the root count in `[-1, 1]` is
zero, evaluates `Q(c_0) > 0` exactly, and only then accepts `m(A) < B`. Every
step is exact integer or rational arithmetic.

**Route 2: exact algebraic-number evaluation at the relevant points.** To refute
a claimed bound, that is to certify `m(A) >= B`, exhibit a point where `f_A`
drops far enough. The point is presented exactly: either as a rational multiple
of `2 pi`, in which case `cos x` is an algebraic number in a cyclotomic field
and `P_A(cos x)` is evaluated exactly there; or as an algebraic `c` in `[-1, 1]`
presented by an integer minimal polynomial together with an isolating rational
interval, with the sign of `P_A(c) + B` determined by exact algebraic sign
determination rather than by numerical evaluation. The verifier re-derives the
minimal polynomial's irreducibility obligation, re-isolates the root, and
re-determines the sign.

**Route 3: exact interval arithmetic with rational endpoints, exclusion only.**
Rigorous enclosures of `P_A` on rational subintervals, with exact rational
endpoints, may be used only to exclude, that is to show that a claimed upper
bound on `m(A)` is false. A branch-and-bound covering of the whole interval,
even with rigorous rational enclosures, is not admitted as a positive global
bound under current repository doctrine, and admitting it would need a new ADR.
Route 1 makes it unnecessary.

Refused as a certificate, without exception:

- any floating-point evaluation of a cosine, of `f_A`, or of a polynomial,
  including double, extended, and arbitrary-precision floating point, and
  including one carrying an informal error estimate;
- dense grid sampling, an FFT-based scan, a plot, and any statement of the form
  "no sampled point fell below the level";
- a floating-point global optimizer's reported minimum, and any SDP or
  relaxation output not accompanied by an exact rational certificate;
- a model's assertion that a family works, at any confidence;
- an unreplayed third-party computer-algebra transcript, including a symbolic
  minimization the independent verifier has not re-derived;
- a finite collection of certified sets presented as the asymptotic statement.

## 9. Useful negative outcomes

- **Certified ratio table.** For every set examined, the exact certified
  rational upper bound on `m(A)` and the exact refuted rational lower bracket,
  with both certificates. This is a durable exact record independent of whether
  the family target is ever reached, and it is the only honest form in which
  "how small can the ratio get" can be recorded.
- **Refuted families.** A defined candidate family with an exact algebraic-point
  refutation showing its excursion does not shrink as claimed. Retained with the
  refuting point in exact form, so the family is not retried blind.
- **Reduction retained.** The Chebyshev reduction plus the Sturm certificate is
  itself the retained methodological result: it converts an analytic target into
  exact rational arithmetic and removes any need for a floating-point path.
  Building it is progress even with no family found.
- **Cost frontier.** The measured coefficient growth and Sturm cost as a
  function of `max(A)`, which is the real constraint on how far the method
  reaches. A measured wall is a result; a guessed one is not.
- **Refused route.** Every numerically appealing family that the exact verifier
  rejected, with the rejection reason, so the same route is not re-run.
- **Blocking obligation.** If §6.3 resolves against the target, the slice's
  retained output is the recorded refutation reference plus the certificate
  stack, and the target is refrozen rather than pursued.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. Version 1, phase
`exploratory`.

Metrics.

- `candidate_families_defined`
- `chebyshev_polynomials_constructed_exactly`
- `sturm_certificates_verified`
- `sturm_certificates_rejected`
- `exact_rational_upper_bounds_established`
- `exact_algebraic_point_refutations_completed`
- `verifier_fixtures_reproduced_exactly`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria.

- an explicitly presented family with a computable `K(eps)` and, for each
  checked index, an accepted Sturm positivity certificate establishing
  `m(A_k) <= eps * card(A_k)`
- an exact refutation of a defined candidate family by exhibiting an algebraic
  point where `f_A` drops below the claimed level, verified by exact algebraic
  sign determination
- an exact record of the best rational ratio bound `m(A) / card(A)` certified
  for each set examined, with the certificate replayed
- or an explicit unresolved outcome that records the smallest remaining
  obligation together with the operator clarifications still outstanding

Stopping rules.

- stop immediately if the operator clarifications on normalization, domain, and
  negative excursion arrive and contradict the locally frozen definitions,
  because the target must then be refrozen
- stop on an accepted certificate chain for an explicitly presented family with
  a computable threshold function
- stop when the fresh model spend reaches USD 20
- stop when no new certified bound, no new refuted family, and no new discharged
  obligation have been produced across two consecutive review points
- never promote a finite collection of certified sets into the asymptotic
  statement, and never promote a sampled or floating-point observation into any
  bound

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Floating-point evaluation of `f_A` | the natural tooling for this item is analytic and every off-the-shelf route evaluates cosines in floating point, so the trust boundary is breached by default rather than by decision | the Chebyshev reduction removes the need entirely; Route 1 is rational-only; §8 refuses float at any precision and the verifier rebuilds `P_A` from `A` itself |
| Sampling read as a bound | "we checked a million points" is persuasive and worthless, and it is what a numerical exploration lane naturally produces | `numerical_sampling_not_a_bound` is frozen; sampling output cannot be recorded as a bound and reaches the record only through an accepted certificate |
| Wrong normalization | if the source divides by `card(A)` or by `sqrt(card(A))`, every certified number here answers a different question | all three conventions are defined completely in §2, `approval_status` is `needs_clarification`, and §13 names exactly what the operator must supply |
| Constants `1` and `1/20` used as thresholds | they are the only numbers inherited from the notes and would silently become success criteria | they are excluded from the target and confined to §6.1 as untrusted comparison values |
| Target already refuted | a known lower bound linear in `card(A)` would make the search pointless | §6.3 is the first thing the ADR-0055 re-check must settle, before any spend |
| Boundary case declined | at `B` exactly equal to `m(A)` the polynomial has a root and the certificate correctly refuses, which can look like a bug | the fixture `A = {1,2}` at `B = 9/8` makes the declining behaviour an expected, tested outcome |
| Coefficient explosion | Sturm remainder sequences over `Q` grow fast, and `deg P_A = max(A)` rather than `card(A)`, so a family with huge elements is cheap to state and expensive to certify | the first slice freezes `max(A) <= 32`; growth is a recorded metric, never a reason to relax arithmetic |
| Finite evidence promoted to asymptotics | certifying many indices feels like establishing `o(card(A))` | a stopping rule forbids the promotion, and the computable `K` requirement makes the asymptotic obligation explicit and separate |
| Interval arithmetic creep | a rigorous rational branch-and-bound looks like a legitimate global bound and would quietly widen the trust path | `interval_arithmetic_exclusion_only` is frozen; positive global bounds come from Route 1 only, and widening needs a new ADR |

## 12. Capability check

Covered by existing capabilities.

- Exact integer and rational arithmetic with unbounded integers from the
  standard library: the Chebyshev recurrence, integer polynomial arithmetic,
  Sturm sequences over `Q`, exact evaluation at rationals, exact rational
  bisection on `B`. No third-party package and no floating point.
- Deterministic serialization, content hashing, bounded subprocesses, captured
  output, no-network execution, and durable machine-readable retention of
  failures and unresolved outcomes under `make report`.
- Declarative problem intake against
  `schemas/problem-definition-v1.schema.json`, validated offline, creating no
  trust: `logical_status unknown`, `novelty_status not_assessed`,
  `significance_status not_assessed`, zero warrants. The
  `needs_clarification` status is carried in the intake file itself.

Would require a new ADR.

- **Number-field arithmetic for Route 2.** Exact algebraic sign determination in
  a cyclotomic field or in a field presented by a minimal polynomial is a new
  repository-authored module with its own acceptance suite, or a pinned
  third-party algebra dependency with a recorded license and a declared gated
  boundary. Either way it is a new decision; Route 1 does not need it.
- **Any interval-arithmetic global bound.** Admitting a rigorous
  branch-and-bound covering as a positive certificate contradicts the current
  exclusion-only restriction and needs its own ADR. Not requested here.
- **Any numerical or SDP solver.** Rejected outright by repository doctrine, not
  merely gated. If a numerical exploration lane is wanted it is a separate
  decision and its output is exploration-only by construction.
- **Execution of model-generated code.** Disabled under ADR-0057 until the
  digest-pinned OCI sandbox gate passes, so the certificate stack and its
  independent verifier must be repository-authored code exercised by the offline
  suite.
- **Source acquisition.** Every §5 row needs the separately authorized ADR-0050
  step, and the `locator_unresolved` rows additionally need the separately
  authorized ADR-0051 query. The benchmark-page row is the one that lifts
  `needs_clarification`, and it is not authorized here.

Not needed and not requested: parallel specialists, evolutionary search, higher
search tiers, embeddings, a web surface, or any additional model provider path.

## 13. Open questions before intake

These are the clarifications that hold `approval_status` at
`needs_clarification`. Questions 1 to 4 name exactly which source constants and
which domain the operator must supply.

1. **Normalization.** Supply the primary source's normalization: are the
   coefficients of `f_A` all `1`; is `f_A` divided by anything; and is the
   comparison denominator `card(A)`, `sqrt(card(A))`, `card(A)^theta` for some
   stated `theta`, or a norm of `f_A`? The frozen local choice is coefficients
   `1`, no scaling, denominator `card(A)`.
2. **Domain for `x`.** Supply the primary source's domain: `[0, 2 pi)`, the
   circle `R / 2 pi Z`, `[0, pi]`, an arc bounded away from `0`, the real line,
   or a discrete set such as rational multiples of `pi`. The frozen local choice
   is `[0, 2 pi)`, justified by `2 pi`-periodicity. If the source restricts to a
   proper arc the target changes materially and must be refrozen.
3. **Negative excursion.** Supply the primary source's definition: `-min f_A`,
   the signed `min f_A`, the integral or `L^1` norm of the negative part,
   `max abs(f_A)`, or a normalized variant. The frozen local choice is
   `-min f_A` over the frozen domain.
4. **The constants `1` and `1/20`.** Supply, for each, the exact inequality it
   appears in: which quantity it bounds, in which direction, against which
   exponent of `card(A)`, and under which normalization. Until this is supplied
   they stay untrusted comparison values in §6.1 and enter no criterion.
5. **The set `A`.** Confirm that `A` is a set of distinct positive integers with
   `0` excluded, rather than a multiset, a set of arbitrary integers, or a
   coefficient-weighted family. The exclusion of `0` is load-bearing, per §3.
6. **Benchmark verifier contract.** If the concrete benchmark version fixes its
   own target inequality or verifier contract, supply it, because it may differ
   from the frozen statement and would then take precedence for any result
   reported against the benchmark.
7. **Re-check ordering.** Confirm that the ADR-0055 pre-research novelty
   re-check resolves §6.3 before any search spend, since a known lower bound
   linear in `card(A)` would refute the frozen target outright.
