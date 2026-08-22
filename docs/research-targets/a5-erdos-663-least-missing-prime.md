# A5. Erdos 663 — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item A5 (tier A)
**Declared domain:** analytic-number-theory
**Intake file:** docs/research-targets/intake/a5-erdos-663-least-missing-prime-v1.json
**Frozen in one line:** For every integer `k >= 2` and every rational
`epsilon > 0` there is `N`, permitted to depend on both, such that
`q(n,k) < (1 + epsilon) log n` for every integer `n > N`, where `q(n,k)` is the
least prime not dividing `(n+1)...(n+k)`.

This is a scoped intake package. It does not approve a formalization, establish
that the frozen statement is open, authorize source acquisition, assess novelty
or significance, create mathematical warrant, or activate a runtime capability.
Novelty, significance, and source applicability are `not_assessed`. No statement
here rests on an acquired source; the catalogue rendering quoted in the planning
dossier is an untrusted candidate and is the load-bearing claim in section 6.

## 1. Frozen target

For an integer `k >= 2` and a positive integer `n`, let

`q(n,k) = min { p : p prime, p does not divide product_(1 <= i <= k) (n+i) }`.

The product runs over `i` from 1 to `k` inclusive, so it is `(n+1)...(n+k)` and
starts at `n+1`, not at `n`. The product is an integer greater than 1 and has
finitely many prime divisors, so `q(n,k)` exists and is unique.

**Frozen statement.** For every integer `k >= 2` and every rational
`epsilon > 0` there exists a positive integer `N`, permitted to depend on both
`k` and `epsilon`, such that for every integer `n > N`,

`q(n,k) < (1 + epsilon) * log n`,

where `log` is the natural logarithm.

Quantifier order, explicitly: `k` first, then `epsilon`, then `N` — which may
depend on both — then `n`. `n` ranges over the positive integers from 1, and the
threshold `N` is what excludes the small `n` where the inequality genuinely
fails.

**No `k` is fixed.** This is the planning dossier's candidate statement for A5,
unnarrowed. The target asserts the conclusion for every `k >= 2`, not for one
value.

**`N` may depend on `k`, and must.** The dependence is not a loophole; it is
forced. By `small_primes_always_divide`, every prime at most `k` divides
`(n+1)...(n+k)`, so `q(n,k) > k` for every `n`. Combined with the target's own
inequality this gives `k < (1 + epsilon) log n`, hence

every admissible `N` satisfies `N >= exp(k / (1 + epsilon))`.

So the threshold provably grows at least exponentially in `k`. A `k`-independent
`N` is therefore a strictly stronger statement, and it is a rejected reading in
section 2, not the frozen target. What the target does assert is the conclusion
*for each* `k >= 2`, so the behaviour of `N` and of every error term as `k`
varies is part of what must be established — that is the substance of the
problem, not a caveat on it.

**The waypoint, and why it is only a waypoint.** The planning dossier's first
slice for A5 says to start from a fixed small `k`, and the recommended
activation order repeats it. The first slice therefore carries a waypoint: the
frozen statement at the single value `k = 3`. Three reasons make 3 the right
first `k`.

- At `k = 3` the forced divisor set is exactly `{2, 3}`: among three consecutive
  integers one is even and exactly one is divisible by 3, so `q(n,3) >= 5`, and
  5 is the first prime whose divisibility is a genuine residue condition.
- The residue condition per prime `p >= 5` covers 3 of `p` classes, so the
  density of `n` with `q(n,3) > P` is a product of factors `3/p`. That is small
  enough for the extremal search in section 7 to reach informative `P` inside a
  bounded envelope, and large enough that the extremal `n` are not
  astronomically sparse.
- `k = 2` is a materially easier and structurally different configuration: the
  forced divisor set is `{2}` alone and the residue condition covers only 2 of
  `p` classes per prime.

`k = 3` scopes the slice. It is **not** part of the frozen target, it does not
appear in the formalization of section 3, and it is not a hypothesis anywhere in
the intake file's `target_claim`. Proving the waypoint does not prove the
target, and section 10's success criteria say so in those words.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| `q(n,k)` | least prime that does **not** divide the product | least prime that *does* divide it; least prime power; least integer coprime to the product |
| the product | `(n+1)...(n+k)`, indices 1 to `k` inclusive | `n(n+1)...(n+k-1)`, which shifts `n` by one and changes every extremal value; also rejected: `(n+1)...(n+k-1)` |
| `k` | quantified over every integer `k >= 2`, outermost | `k` fixed to one value, which is the waypoint and a strictly weaker statement |
| `N` | may depend on both `k` and `epsilon`; provably `>= exp(k/(1+epsilon))` | an `N` independent of `k`, which is strictly stronger; also rejected: `N` chosen before `epsilon` |
| `log n` | natural logarithm, base `e` | base 2 or base 10, which rescale the right-hand side by a constant and are different claims |
| `(1 + o(1)) log n` | the explicit form `(1 + epsilon) log n` with `k` and `epsilon` both quantified before `N` | `limsup q(n,k)/log n <= 1` stated without the `N` witness; also rejected: any reading where `N` precedes `epsilon` |
| `epsilon` | positive rational | positive real; equivalent by monotonicity and density, but rationals are chosen so threshold arithmetic stays exact |
| `n` | positive integer, `n >= 1`, with small `n` absorbed by `N` | `n >= 0` or `n` real; at `n <= 0` the product can vanish and `q` is undefined |
| the inequality | strict `<` | non-strict `<=` |
| waypoint | a strictly weaker statement proved en route, recorded as progress | a waypoint reported as the target, or a waypoint whose delta to the target is left unstated |
| "long initial-prime coverage" | every prime at most `P` divides `(n+1)...(n+k)`, that is `q(n,k) > P` | every prime at most `P` divides *some* factor individually with multiplicity conditions; also rejected: `P`-smoothness of the product |
| extremal `n` | either an `n` attaining `max q(n,k)` over a stated finite range, or the least `n` with `q(n,k) > P` for a stated `P` and `k` | "record" `n` with the range, `P`, or `k` left unstated |

## 3. Formalization and quantifiers

```
forall k in Z with k >= 2,
  forall epsilon in Q with epsilon > 0,
    exists N in Z with N >= 1, N depending on k and epsilon,
      forall n in Z with n > N,
        q(n,k) < (1 + epsilon) * log(n)

where q(n,k) = min { p : p prime and p does not divide
                        the product of (n+i) for 1 <= i <= k }
and log is the natural logarithm
```

Quantifier list as recorded in the intake file:

- `forall k an integer with k >= 2`
- `forall epsilon a positive rational`
- `exists N a positive integer, permitted to depend on both k and epsilon`
- `forall n an integer with n > N`

`k` is a universally quantified variable of the target, not a parameter frozen
before it. The value 3 survives only as the waypoint scope in section 7.

`formal_language` is `typed_informal_math`, `version` 1, `approval_status`
`proposed`. Human approval of the semantic alignment below is still required.

## 4. Semantic alignment to the source statement

**Quantifier mapping.**

- `for every fixed k >= 2` maps to: `forall k` an integer with `k >= 2`; every
  `k` is in scope and none is fixed.
- `as n -> infinity` maps to:
  `forall epsilon in Q with epsilon > 0, exists N, forall integers n > N`.
- `q(n,k) < (1 + o(1)) log n` maps to: `q(n,k) < (1 + epsilon) * log n` with `k`
  and `epsilon` both quantified before `N` and `N` permitted to depend on both.
- `n` maps to: `n` an integer with `n > N`; the underlying range is the positive
  integers from 1.
- `the value k = 3 of the first slice` maps to: not a quantifier of the target;
  it scopes only the waypoint proved en route.

**Definition mapping.**

- `q(n,k)` — the least prime not dividing the product of `(n+i)` for
  `1 <= i <= k`.
- `product over 1 <= i <= k of (n+i)` — `(n+1)...(n+k)`; the product starts at
  `n+1`, not at `n`.
- `log n` — natural logarithm of `n`, base `e`.
- `long initial-prime coverage of k consecutive integers` — the property that
  every prime at most `P` divides `(n+1)...(n+k)`, which is exactly the
  condition `q(n,k) > P`.
- `extremal n` — an `n` that attains the maximum of `q(n,k)` over a stated
  finite range, or the least `n` with `q(n,k) > P` for a stated `P` and `k`.
- `waypoint` — a strictly weaker statement proved en route to the target,
  recorded as progress and never as the target.

**Assumption delta.**

- The frozen target adds no hypothesis to the planning dossier's candidate
  statement: it quantifies over every integer `k >= 2` and every rational
  `epsilon > 0`, with no `k` fixed.
- The implicit `(1 + o(1))` is replaced by the explicit `epsilon`-`N` form with
  `k` and `epsilon` both quantified before `N`; this is the same statement
  written so the quantifier order cannot drift.
- `N` is permitted to depend on both `k` and `epsilon`, and must be: the target
  asserts the conclusion for each `k`, not a single threshold serving every `k`
  at once. A `k`-independent `N` is a strictly stronger statement and is a
  rejected reading.
- `epsilon` is quantified over positive rationals rather than positive reals;
  the statements are equivalent by monotonicity in `epsilon` and density of the
  rationals, and the rational choice keeps threshold computations exact.
- The logarithm base is pinned to `e`; no published constant is assumed,
  including the explicit Chebyshev constant used in any re-derivation.
- The value `k = 3` is not part of the target. It scopes the first slice's
  waypoint only, and the slice's `k = 3` work establishes nothing about any
  other `k` and nothing about how `N` and the error terms behave as `k` varies,
  which is exactly what the target's quantification over `k` requires.

**Edge-case delta.**

- For every `k >= 2` and `n >= 1`, every prime at most `k` divides the product,
  so `q(n,k)` is a prime strictly greater than `k`; at the waypoint value
  `k = 3` this gives `q(n,3) >= 5`.
- Small `n` are genuine false instances: `log n` is at most 0.7 for `n <= 2`
  while `q(n,k) > k >= 2`, so they are absorbed by the threshold `N` and are not
  counterexamples to the frozen claim.
- `n` ranges over positive integers only; the statement says nothing about
  `n <= 0`, where the product can vanish and `q` would be undefined.
- The inequality is strict, and the right-hand side is irrational for every
  `n >= 2` and rational `epsilon`, so the boundary case of equality does not
  arise; the frozen statement does not rely on that observation.
- Because `q(n,k) > k` always, every admissible `N` satisfies
  `N >= exp(k/(1+epsilon))`: the threshold provably grows at least exponentially
  in `k`, so the `k`-dependence of `N` is load-bearing rather than incidental.

**Strength relation:** `unresolved`. The frozen statement is the planning
dossier's own candidate statement for A5, with no `k` fixed and no hypothesis
added or removed, so it is not weaker than it. But `equivalent` is refused: the
mapping cannot be settled while the catalogue entry and the original Erdos
source are unacquired, and under this task no source text has been quoted from a
primary source. In particular the reading of `N`'s permitted dependence on `k`
is a decision recorded here, not a fact read off the source. The relation
resolves only after the section 5 acquisition rows are executed and reviewed.

## 5. Provenance and acquisition plan

No source has been acquired. Under ADR-0050 acquisition is human-planned,
exact-URL, and separately authorized; this section is the plan only. Every row
is `pending_acquisition`, applicability `not_assessed`.

Only the first row carries a locator that this dossier did not invent: it is the
URL already recorded in the planning dossier's source ledger. Bibliographic
strings in the remaining rows are operator search targets; no DOI is asserted
for any of them. ADR-0051 supplies the identity-resolution step: one
operator-initiated Crossref metadata query per target, terms drawn as exact
substrings of a supplied local context file, results
`untrusted_inspiration_candidate` only.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Erdos Problems catalogue, entry 663 | `https://www.erdosproblems.com/663` — the locator recorded in the planning dossier's source ledger | claims U1 and U2: the exact statement, its indexing of the product, its treatment of the threshold's dependence on `k`, and the reported status | pending_acquisition |
| The original Erdos source behind entry 663 | identify from the catalogue entry's own bibliography once row 1 is acquired; then acquire that exact item | claim U3: whether the original permits the threshold to depend on `k` or intends one uniform in `k`, and the original indexing of the product; also settles the strength relation in section 4 | pending_acquisition |
| Erdos and Graham, problem collection in combinatorial number theory (1980) | resolve via one ADR-0051 Crossref query on the exact title; acquire the located passage | claim U2: whether the `(1 + o(1)) k log n` bound is stated there and with what proof sketch | pending_acquisition |
| A standard analytic number theory text giving explicit Chebyshev bounds for `theta(x)` | resolve via one ADR-0051 Crossref query; acquire the exact theorem statement page | the explicit constant used in the section 7 re-derivation; without it the constant must be re-derived locally rather than recalled | pending_acquisition |
| Any post-2025 work on the least prime missing from a block of consecutive integers | resolve via ADR-0051 Crossref queries on the exact phrase family; acquire located theorem statements | claim U1: whether the target is settled for any `k`, for all `k`, or for none, and whether a constant better than `k` is published | pending_acquisition |

## 6. Prior-status claims to re-check

Each item is untrusted. None has been acquired, quoted from a primary source, or
reviewed. All are named as items the ADR-0055 pre-research novelty re-check must
cover immediately before research starts, bound to the intake file's subject
hash.

- **U1, load-bearing.** The planning dossier reports Erdos Problem 663 as a
  catalogue entry asking whether `q(n,k) < (1 + o(1)) log n` for every fixed
  `k`, and lists it among tier A candidates rather than as settled. The frozen
  target *is* that question for every `k`, so this claim is what decides whether
  the target is an open problem at all. Untrusted: the catalogue label, the
  current status, and whether any individual `k` is already settled. The named
  acquisition targets are the first and fifth rows of section 5.
- **U2.** The planning dossier reports the `(1 + o(1)) k log n` bound as "easy".
  Untrusted as an attribution and as a statement. Section 7 re-derives it rather
  than citing it, and the re-derivation's constants, as explicit functions of
  `k`, are the deliverable.
- **U3.** Whether the source states the product as `(n+1)...(n+k)` or as
  `n(n+1)...(n+k-1)`, and whether it permits the threshold to depend on `k` or
  intends one uniform in `k`, cannot be checked offline. The frozen reading is
  `(n+1)...(n+k)` with `N` permitted to depend on `k`. A different indexing
  shifts `n` by one and changes every extremal value; a `k`-independent `N` is
  strictly stronger. Both are rejected readings recorded in section 2 for audit.
- **U4.** The planning dossier's source ledger says the catalogue renderings are
  "not substitutes for the original Erdos sources or a literature review". That
  instruction is inherited unchanged, and it is also why the strength relation
  in section 4 is `unresolved` rather than `equivalent`.

## 7. Bounded first slice

The slice is deliberately narrower than the target. It works at the waypoint
value `k = 3` and re-derives the easy bound whose constant is `k`. It does not
attempt the target, and it cannot reach it.

**Piece A — re-derive the easy upper bound with constants explicit in `k`.**

The route, recorded in the intake file as `easy_upper_bound_route` and to be
re-derived rather than assumed: every prime strictly below `q(n,k)` divides
`(n+1)...(n+k)`, so

`theta(q(n,k)) - log q(n,k) <= log((n+1)...(n+k)) <= k * log(n+k)`,

where `theta(x) = sum_(p <= x) log p`. With an explicit Chebyshev bound of the
form `theta(x) > c_1 * x` valid for `x >= x_0`, this yields
`q(n,k) < (k/c_1) * log(n+k) + O(log log n)` with every constant named. The
deliverable is the explicit pair `(N(k, epsilon), constant)` and the arithmetic
that produces it, not the asymptotic shape.

The constant this route gives is proportional to `k`; the target constant is 1.
**That factor-`k` gap is the frozen obligation the slice reports open** — the
factor-3 gap at the waypoint value — and the slice is not expected to close it.
The re-derivation must also produce the exact necessary lower bound
`N >= exp(k/(1 + epsilon))` from section 1, so the recorded threshold is
sandwiched rather than merely asserted.

All arithmetic is exact rational. The Chebyshev constant must be either acquired
(section 5, row 4) or re-derived locally; a constant recalled by a model is
refused as input.

**Piece B — exhaustive extremal search at the waypoint value `k = 3`.**

By `prime_divides_iff_residue`, for a prime `p > k`, `p | (n+1)...(n+k)` iff
`n mod p` lies in `{p-1, ..., p-k}`, which is `k` distinct residues. At `k = 3`
and `p >= 5` that is three residues, so `q(n,3) > P` iff `n` satisfies one of
exactly 3 residue conditions modulo each prime `p` with `5 <= p <= P`. By the
Chinese remainder theorem the set of such `n` is a union of residue classes
modulo `prod_(5 <= p <= P) p`, and the number of classes is exactly
`3^(pi(P) - 2)`.

The search is therefore a complete enumeration of CRT branches, not a sieve over
`n`. Envelope and its exact size:

| `P` | CRT branches `3^(pi(P)-2)` | modulus `prod_(5 <= p <= P) p` |
|---|---|---|
| 11 | 27 | 385 |
| 17 | 243 | 85085 |
| 23 | 2187 | 37182145 |
| 29 | 6561 | 1078282205 |
| 31 | 19683 | 33426748355 |
| 37 | 59049 | 1236789689135 |
| 41 | 177147 | 50708377254535 |

The envelope is frozen at `P <= 41`: 177147 branches, each a CRT reconstruction
over arbitrary-precision integers. For each branch the least positive `n` in the
class is computed exactly, and the minimum over branches is the exact least `n`
with `q(n,3) > P`. That value is a *complete* answer for that `P` at `k = 3`,
not a sample. The same enumeration is available at any other `k` with
`k^(pi(P) - pi(k))` branches, and the slice records that count so a later
extension to a second `k` is a decision rather than a guess.

**Canonicalization and what is exhaustive.** Branches are indexed canonically by
the tuple of chosen offsets in `{1,...,k}` per prime, in increasing prime order,
so the enumeration has no duplicates and no symmetry quotient is needed or
claimed. Enumeration is exhaustive over branches for each `P <= 41` at `k = 3`.
Nothing is sampled. `n` itself is never enumerated.

**Exact comparison against `log n`.** The interesting quantity is
`q(n,3) / log n` at the extremal `n`. Since `log n` is not rational, the
comparison is done with rational interval enclosures: `log n` is bracketed by
rationals from a truncated series with a certified rational remainder bound, and
the comparison `q < (1 + epsilon) * L` is concluded only when it holds for the
whole enclosure. Enclosures are used for exclusion only. A floating-point ratio
may be printed for orientation and is exploration-only; a local probe of this
envelope produced ratios near 2.3, drifting slowly downward as `P` grows, but
that number is orientation and is not a certified value and not evidence about
the limit.

**Boundary of the claim.** Three boundaries, and all three are load-bearing.

- No computation over a finite range of `n`, and no complete enumeration of CRT
  branches for finitely many `P`, can establish the frozen asymptotic claim. Nor
  can it refute it: the claim constrains only `n` beyond an unspecified
  threshold, so no finite set of `n` is a counterexample.
- The waypoint is not the target. Even a full proof at `k = 3` leaves the target
  untouched for every other `k`, and it says nothing about the behaviour of `N`
  or of the error terms as `k` varies — which, since the target quantifies over
  `k`, is a substantial part of what the target asserts.
- The re-derived constant is `k`, not 1. Piece A is a bound of the right shape
  with the wrong constant, and the gap is reported rather than narrated.

What the slice can support is: an exact least `n` with `q(n,3) > P` for each
`P <= 41`, a certified lower bound on `sup q(n,3)/log n` over the enumerated
extremal `n`, an explicit `N(k, epsilon)` for the easy bound with constants
named, and the exact necessary lower bound on any admissible `N`. None of those
is the theorem.

**Realistic reach of the first slice.** Against a full open case quantified over
every `k`, the honest expectation is piece A with named constants, the exact
extremal table at `k = 3`, and a precisely stated remaining obligation. The
success criteria in section 10 name the unresolved outcome as the realistic one
for that reason.

## 8. Certificate and verifier contract

| Result shape | Certificate format | Independent verifier |
|---|---|---|
| explicit upper bound with constants in `k` | the full derivation with every constant named as a function of `k` and `epsilon`, the explicit `N(k, epsilon)`, the source or local derivation of the Chebyshev constant, and every arithmetic step as exact rationals | human review of the derivation plus mechanical replay of every rational computation; the Chebyshev input must resolve to an acquired passage or a local exact derivation |
| certified extremal `n` for a stated `P` and `k` | the value `n`, the stated `k`, the CRT branch tuple that produced it, the complete list of primes at most `P` with, for each, which of `n+1,...,n+k` it divides, and a rational enclosure of `log n` with its remainder bound | recompute the CRT branch, verify each divisibility by exact integer division, verify the enclosure endpoints and remainder bound, and re-derive the minimality over branches |
| the `k = 3` waypoint proved | the full proof of the frozen statement at `k = 3` with an explicit `N(epsilon)`, plus the explicit statement that the result is the waypoint and not the target, plus the waypoint-to-target delta | human review of the proof and replay of every exact computation inside it. A record lacking the waypoint-to-target delta is refused |
| a claimed improved constant `c < k` | the derivation, the exact range of `k` for which it holds, and, for every inequality verified numerically, a rational enclosure with explicit endpoints | replay of the derivation and of every enclosure; a numerically-verified inequality without an enclosure is refused |
| unresolved | the exact envelope reached (`P` bound, `k`, branch count), the closed and open derivation obligations, the constant actually achieved as a function of `k`, and the statement that nothing is established about the `k`-dependence of `N` | replay of the enumeration to confirm the envelope, and inspection of the obligation list |

**Refused as a certificate.** Any floating-point value on a trust path,
including a floating-point evaluation of `log n` or of `q(n,k)/log n`. A model's
assertion of a constant, a threshold, or a Chebyshev bound. A third-party
program's output that has not been replayed. The failure of a sweep to find a
large ratio. Any finite computation presented as settling the asymptotic in
either direction. The `k = 3` waypoint presented as the target.

## 9. Useful negative outcomes

- **The exact extremal record.** For each `P <= 41`, the exact least `n` with
  `q(n,3) > P`, with its CRT branch. This is a permanent exact fact independent
  of the conjecture and is reusable by any later attempt, at `k = 3` or as the
  template for a second `k`.
- **A certified lower bound on the ratio.** The largest certified value of
  `q(n,3)/log n` inside the envelope, with its rational enclosure. If that value
  stays well above 1 as `P` grows, that is a recorded measurement of how far the
  data are from the conjectured constant — not evidence against it.
- **The `k`-dependence frontier.** The exact necessary lower bound
  `N >= exp(k/(1+epsilon))` and the upper bound produced by piece A, together
  bracketing the admissible thresholds. The gap between those two brackets, as a
  function of `k`, is the reusable statement of what the target still needs.
- **The refuted route.** If the re-derivation of piece A cannot be pushed below
  the constant `k` by the intended argument, the exact point where it stalls is
  recorded, together with the inequality that would have to improve. The next
  attempt starts from the named inequality.
- **The frontier.** The `P` bound reached, the `k` worked at, the branch count,
  and the wall of the envelope, so the next slice resumes from a recorded
  position.
- **The structural characterization.** The exact description of the residue
  classes modulo `prod_(5 <= p <= P) p` that achieve `q(n,3) > P`, which is a
  complete answer to a well-posed finite question even when the asymptotic stays
  open.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. `version` 1, `phase`
`exploratory`.

Metrics: `extremal_n_certified`, `crt_branches_enumerated`,
`primes_covered_max`, `rational_enclosures_verified`,
`derivation_obligations_closed`, `waypoint_obligations_closed`,
`failed_routes_preserved`, `model_cost_usd`.

Success criteria:

- an exact re-derivation of the easy upper bound with an explicit threshold `N`
  as a function of `k` and `epsilon` and explicit constants, every step
  replayable in exact rational arithmetic, recorded as progress toward the
  target and never as the target because the constant it yields is `k` and not 1
- the waypoint proved, namely the target statement at the single value `k = 3`
  with an explicit threshold `N` as a function of `epsilon`, recorded as
  progress toward the target and never as the target, since the target
  quantifies over every integer `k >= 2`
- an exactly certified extremal `n` at the waypoint value `k = 3`, together with
  the complete list of primes dividing `(n+1)(n+2)(n+3)` and a rational
  enclosure of `log n` that pins the ratio `q(n,3) / log n` at that `n`
- or, and this is the realistic outcome for a first slice against a full open
  case, an explicit unresolved outcome recording the smallest remaining
  obligation: the re-derived constant written as an explicit function of `k`,
  the gap between it and the target constant 1, and the fact that nothing has
  been established about how the threshold behaves as `k` varies

Stopping rules:

- stop when the easy upper bound is re-derived with explicit constants and an
  explicit threshold as a function of `k` and `epsilon`
- stop when an exact certificate establishes a new largest certified value of
  `q(n,3) / log n` inside the frozen waypoint search envelope
- stop when the fresh model spend reaches USD 20
- stop when no derivation obligation has been closed and no new extremal `n` has
  been certified for two consecutive review points
- never promote a finite sweep of `n` into the asymptotic claim or into its
  refutation: exhausting any range of `n` leaves the limit untouched
- never present the `k = 3` waypoint as the target: the target quantifies over
  every integer `k >= 2`, and one value of `k` establishes nothing about the
  others or about the behaviour of the threshold in `k`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The waypoint is reported as the target | A `k = 3` theorem is a real result and one word from the target's own sentence; the substitution would be almost invisible | `k = 3` is absent from `target_claim`, from section 3, and from the assumption delta; the last stopping rule and the last refused-certificate line both forbid it; `waypoint_obligations_closed` and `derivation_obligations_closed` are separate metrics |
| The `k`-dependence is quietly dropped | The target quantifies over `k`, so an unnamed constant or a threshold that absorbs `k` hides exactly what must be established | `threshold_dependence_on_k` requires every threshold and constant to be an explicit function of `k` and `epsilon`, and pins the exact necessary bound `N >= exp(k/(1+epsilon))` so a claimed threshold can be checked against it |
| Finite search read as an asymptotic result | The measured ratio is near 2.3 and falling; a narrative that it "trends toward 1" would be a fabricated asymptotic | `finite_search_not_asymptotic` forbids it, the fifth stopping rule forbids the promotion, and section 7 states the boundary in both directions |
| Scope creep back into one `k` | Under budget pressure the easy move is to re-freeze `k` and declare success | The `k` row in section 2 records a fixed `k` as a rejected reading; a single-`k` target would require a new intake file with a new canonical hash |
| Product indexing off by one | `n(n+1)(n+2)` versus `(n+1)(n+2)(n+3)` changes every extremal value and every table | Frozen in section 2 with the alternative recorded as rejected; U3 names it as the acquisition question that would settle the source's own indexing |
| Recalled Chebyshev constant | A model-recalled explicit constant is untrusted and would silently corrupt the threshold | Section 5 row 4 is the acquisition target; otherwise the constant is re-derived locally. Recalled values are refused as input |
| Floating-point `log` on the trust path | The repo owner rejects floating-point solvers outright, and a ratio comparison is exactly where a float would sneak in | `exact_arithmetic_requirement` mandates rational enclosures with certified remainder bounds, exclusion-only; floats are print-only and labelled |
| Logarithm base drift | A base-2 reading multiplies the bound by about 1.44 and makes an unrelated statement look proved | `log_base` fixes base `e` and records base 2 and base 10 as rejected |
| Envelope inflation | Branch count grows as `k^(pi(P) - pi(k))`, so a small increase in `P` or in `k` silently multiplies cost | Envelope frozen at `P <= 41` and `k = 3` with the exact branch count and modulus tabulated in section 7; any extension in `P` or `k` is a new decision, not a parameter tweak |
| Uniform-`N` reading adopted by accident | An `N` independent of `k` is a strictly stronger statement; proving the weaker one and stating the stronger would be a false claim | The `N` row in section 2 and the third assumption-delta bullet fix the permitted dependence; U3 names the acquisition question that settles what the source intends |

## 12. Capability check

**Covered by existing AdaIvy capabilities.**

- Declarative intake with the trust boundary intact: the intake file validates
  against `schemas/problem-definition-v1.schema.json` and produces
  `logical_status unknown`, novelty and significance `not_assessed`, zero
  warrants.
- Exact arbitrary-precision integer arithmetic, CRT reconstruction, and exact
  rational arithmetic as project-authored standard-library code under `src/`,
  with deterministic serialization, content hashes, and captured output. Ad-hoc
  exact arithmetic written and run by the driving agent in a scratch workspace is
  NOT this capability: it is an unmet AdaIvy capability and an external-origin
  contribution under ADR-0057 section 5, imported with an `external_codex` or
  `human` root and never relabelled as AdaIvy work.
- Rational interval enclosures with rational endpoints used for exclusion only —
  the exact-arithmetic replacement named in the authoring spec for a numerical
  comparison.
- Machine-readable preservation of failed routes and unresolved outcomes, which
  section 9 relies on.
- ADR-0055 pre-research novelty re-check, required by section 6.
- ADR-0051 one-shot Crossref metadata query for the identity-resolution step in
  section 5, inspiration-only.
- ADR-0036 publication projection if any result is rendered: an exact rational
  derivation without a kernel-checked attestation reaches `Proposition` at best,
  and any unacquired background renders as an OPEN OBLIGATION rather than a
  citation.

**Would require a new ADR.**

- A third-party computer-algebra or number-theory library, for example for
  explicit prime-counting bounds or high-precision logarithms. Not needed for
  the frozen envelope: CRT enumeration and rational enclosures are
  standard-library work.
- Kernel-checked formalization of an asymptotic analytic argument. The sealed
  Phase 3B Lean path checks a frozen theorem statement with a proposed proof
  fragment; a threshold argument quantified over `k` with explicit Chebyshev
  input is far outside that shape, so a kernel-checked route to the target is
  not available and is not assumed.
- Acquisition of any section 5 source, which is ADR-0050 territory and needs
  per-URL human planning and separate authorization.
- Execution of model-generated code, which stays disabled under ADR-0057 until
  its digest-pinned OCI sandbox gate passes. Every program here is
  project-authored and reviewed.
- Any sieve over `n`, or any extension in `k`, large enough to need out-of-core
  storage or a longer-running job class.

**Explicitly not activated.** Parallel specialists, evolutionary search, higher
search tiers, crawling, result following, and automated novelty or significance
assessment.

## 13. Open questions before intake

1. The target quantifies over every `k >= 2`, which is a hard open problem if U1
   holds. What fraction of it can the first slice realistically move? The honest
   answer from section 7 is: piece A with constants named as functions of `k`,
   the exact extremal table at `k = 3` up to `P <= 41`, the exact necessary
   bound on `N`, and no progress at all on closing the factor-`k` gap or on the
   behaviour of `N` across `k`. The operator should confirm that this is
   acceptable reach, because the realistic recorded outcome is the unresolved
   one in section 10.
2. Is the product indexing `(n+1)...(n+k)` correct against the original source?
   This is U3 and is the one question that could invalidate every extremal value
   computed. It cannot be answered offline.
3. Does the source permit the threshold to depend on `k`, as frozen here, or
   intend one uniform in `k`? The frozen reading is the weaker and, given
   `N >= exp(k/(1+epsilon))`, the only satisfiable one; confirming it against
   the source is part of U3.
4. Is `k = 3` the right waypoint, or should the slice aim at `k = 2` first
   despite it being structurally easier? This changes the slice only; the target
   is unaffected, so it does not need a new intake file.
5. Is `P <= 41` the right envelope, or should the first run stay lower so it is
   cheaper, or go higher because the extremal structure only becomes informative
   later?
6. Should the explicit Chebyshev constant be acquired (section 5 row 4) or
   re-derived locally? Re-deriving it is more work but keeps the slice free of
   acquisition dependencies.
