# A5. Erdos 663 at `k = 3` — scoped research dossier

**Compiled:** 21 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item A5 (tier A)
**Declared domain:** analytic-number-theory
**Intake file:** docs/research-targets/intake/a5-erdos-663-least-missing-prime-v1.json
**Frozen in one line:** For every rational `epsilon > 0` there is `N` such that
`q(n,3) < (1 + epsilon) log n` for every integer `n > N`, where `q(n,3)` is the
least prime not dividing `(n+1)(n+2)(n+3)`.

This is a scoped intake package. It does not approve a formalization, establish
that the frozen statement is open, authorize source acquisition, assess novelty
or significance, create mathematical warrant, or activate a runtime capability.
Novelty, significance, and source applicability are `not_assessed`. No statement
here rests on an acquired source; the catalogue rendering quoted in the planning
dossier is an untrusted candidate and is listed as such in section 6.

## 1. Frozen target

For an integer `k >= 2` and a positive integer `n`, let

`q(n,k) = min { p : p prime, p does not divide product_(1 <= i <= k) (n+i) }`.

The product runs over `i` from 1 to `k` inclusive, so it is `(n+1)...(n+k)` and
starts at `n+1`, not at `n`. The product is an integer greater than 1 and has
finitely many prime divisors, so `q(n,k)` exists and is unique.

`k` is frozen to the single value 3, so the product is `(n+1)(n+2)(n+3)`.

**Frozen statement.** For every rational `epsilon > 0` there exists a positive
integer `N` such that for every integer `n > N`,

`q(n,3) < (1 + epsilon) * log n`,

where `log` is the natural logarithm.

Quantifier order, explicitly: `epsilon` first, then `N` (which may depend on
`epsilon` and on the frozen `k = 3`), then `n`. `n` ranges over the positive
integers from 1, and the threshold `N` is what excludes the small `n` where the
inequality genuinely fails.

**Why `k = 3` and not another `k`.** The planning dossier says to start with a
fixed small `k`; the directive defaults to `k = 3` and asks for a justification.
Three reasons hold it.

- At `k = 3` the set of *forced* prime divisors is exactly `{2, 3}`: among three
  consecutive integers one is even and exactly one is divisible by 3, so
  `q(n,3) >= 5` always, and 5 is the first prime whose divisibility is a genuine
  residue condition. At `k = 2` the forced set is `{2}` alone and the residue
  condition covers only 2 of `p` classes per prime, which is a materially easier
  and structurally different configuration.
- The residue condition per prime `p >= 5` covers 3 of `p` classes, so the
  density of `n` with `q(n,3) > P` is a product of factors `3/p`. That is small
  enough for the extremal search in section 7 to reach interesting `P` inside a
  bounded envelope, and large enough that the extremal `n` are not astronomically
  sparse.
- The `k`-dependence of the threshold is the whole difficulty of the source
  question, per the planning dossier's own risk line. Freezing the smallest `k`
  at which the structure is fully present is the cheapest way to make that
  dependence explicit and auditable.

Nothing is claimed for `k = 2` or for any `k >= 4`.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| `q(n,k)` | least prime that does **not** divide the product | least prime that *does* divide it; least prime power; least integer coprime to the product |
| the product | `(n+1)(n+2)(n+3)`, indices 1 to `k` inclusive | `n(n+1)(n+2)`, which shifts `n` by one and changes every extremal value; also rejected: `(n+1)...(n+k-1)` |
| `k` | frozen to 3, chosen before `epsilon` and before `N` | `k` quantified inside, or a uniform-in-`k` statement, which is strictly stronger |
| `log n` | natural logarithm, base `e` | base 2 or base 10, which rescale the right-hand side by a constant and are different claims |
| `(1 + o(1)) log n` | the explicit form `(1 + epsilon) log n` with `epsilon` quantified before `N` | `limsup q(n,k)/log n <= 1` stated without the `N` witness; also rejected: any reading where `N` is chosen before `epsilon` |
| `epsilon` | positive rational | positive real; equivalent by monotonicity and density, but rationals are chosen so threshold arithmetic stays exact |
| `n` | positive integer, `n >= 1`, with small `n` absorbed by `N` | `n >= 0` or `n` real; at `n <= 0` the product can vanish and `q` is undefined |
| the inequality | strict `<` | non-strict `<=` |
| "long initial-prime coverage" | every prime at most `P` divides `(n+1)(n+2)(n+3)`, that is `q(n,3) > P` | every prime at most `P` divides *some* factor individually with multiplicity conditions; also rejected: `P`-smoothness of the product |
| extremal `n` | either an `n` attaining `max q(n,3)` over a stated finite range, or the least `n` with `q(n,3) > P` for a stated `P` | "record" `n` with the range or `P` left unstated |

## 3. Formalization and quantifiers

```
forall epsilon in Q with epsilon > 0,
  exists N in Z with N >= 1,
    forall n in Z with n > N,
      q(n,3) < (1 + epsilon) * log(n)

where q(n,3) = min { p : p prime and p does not divide (n+1)*(n+2)*(n+3) }
and log is the natural logarithm
```

Quantifier list as recorded in the intake file:

- `forall epsilon a positive rational`
- `exists N a positive integer, depending on epsilon and on the frozen value k = 3`
- `forall n an integer with n > N`

`formal_language` is `typed_informal_math`, `version` 1, `approval_status`
`proposed`. Human approval of the semantic alignment below is still required.

## 4. Semantic alignment to the source statement

**Quantifier mapping.**

- `for every fixed k >= 2` maps to: `k` is frozen to the single value 3; no other
  `k` is in scope.
- `as n -> infinity` maps to:
  `forall epsilon in Q with epsilon > 0, exists N, forall integers n > N`.
- `q(n,k) < (1 + o(1)) log n` maps to: `q(n,3) < (1 + epsilon) * log n` with
  `epsilon` quantified before `N` and `N` allowed to depend on `epsilon`.
- `n` maps to: `n` an integer with `n > N`; the underlying range is the positive
  integers from 1.

**Definition mapping.**

- `q(n,k)` — the least prime not dividing the product of `(n+i)` for
  `1 <= i <= k`.
- `product over 1 <= i <= k of (n+i)` — `(n+1)(n+2)(n+3)` for the frozen
  `k = 3`; the product starts at `n+1`, not at `n`.
- `log n` — natural logarithm of `n`, base `e`.
- `long initial-prime coverage of k consecutive integers` — the property that
  every prime at most `P` divides `(n+1)(n+2)(n+3)`, which is exactly the
  condition `q(n,3) > P`.
- `extremal n` — an `n` that attains the maximum of `q(n,3)` over a stated finite
  range, or the least `n` with `q(n,3) > P` for a stated `P`.

**Assumption delta.**

- The source quantifies over every fixed `k >= 2`; the frozen target fixes
  `k = 3`, so it is a strict special case and claims nothing about other `k`.
- The implicit `(1 + o(1))` is replaced by the explicit `epsilon`-`N` form with
  `epsilon` quantified before `N`; this is the same statement written so the
  quantifier order cannot drift.
- `epsilon` is quantified over positive rationals rather than positive reals; the
  statements are equivalent by monotonicity in `epsilon` and density of the
  rationals, and the rational choice keeps threshold computations exact.
- The logarithm base is pinned to `e`; no published constant is assumed,
  including the explicit Chebyshev constant used in any re-derivation.

**Edge-case delta.**

- `n = 1` and `n = 2` satisfy `log n <= 0.7` while `q(n,3) >= 5`, so the
  inequality fails there; these are absorbed by `N` and are not counterexamples
  to the frozen claim.
- `q(n,3) >= 5` for every `n >= 1`, because 2 and 3 always divide a product of
  three consecutive integers, so the left-hand side is never 2 or 3.
- `n` ranges over positive integers only; the statement says nothing about
  `n <= 0`, where the product can vanish and `q` would be undefined.
- The inequality is strict, and the right-hand side is irrational for every
  `n >= 2` and rational `epsilon`, so the boundary case of equality does not
  arise; the frozen statement does not rely on that observation.

**Strength relation:** `weaker`. One fixed `k` instead of every fixed `k`: the
frozen target is implied by the source statement and does not imply it.

## 5. Provenance and acquisition plan

No source has been acquired. Under ADR-0050 acquisition is human-planned,
exact-URL, and separately authorized; this section is the plan only. Every row is
`pending_acquisition`, applicability `not_assessed`.

Only the first row carries a locator that this dossier did not invent: it is the
URL already recorded in the planning dossier's source ledger. Bibliographic
strings in the remaining rows are operator search targets; no DOI is asserted for
any of them. ADR-0051 supplies the identity-resolution step: one
operator-initiated Crossref metadata query per target, terms drawn as exact
substrings of a supplied local context file, results
`untrusted_inspiration_candidate` only.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Erdos Problems catalogue, entry 663 | `https://www.erdosproblems.com/663` — the locator recorded in the planning dossier's source ledger | claims U1 and U2: the exact statement, its indexing of the product, and the reported status | pending_acquisition |
| The original Erdos source behind entry 663 | identify from the catalogue entry's own bibliography once row 1 is acquired; then acquire that exact item | claim U3: whether the original asks the question for each fixed `k` or uniformly in `k`, and the original indexing of the product | pending_acquisition |
| Erdos and Graham, problem collection in combinatorial number theory (1980) | resolve via one ADR-0051 Crossref query on the exact title; acquire the located passage | claim U2: whether the `(1 + o(1)) k log n` bound is stated there and with what proof sketch | pending_acquisition |
| A standard analytic number theory text giving explicit Chebyshev bounds for `theta(x)` | resolve via one ADR-0051 Crossref query; acquire the exact theorem statement page | the explicit constant used in the section 7 re-derivation; without it the constant must be re-derived locally rather than recalled | pending_acquisition |
| Any post-2025 work on the least prime missing from a block of consecutive integers | resolve via ADR-0051 Crossref queries on the exact phrase family; acquire located theorem statements | claim U1: whether the `k = 3` case is already settled, and whether a constant better than `k` is published | pending_acquisition |

## 6. Prior-status claims to re-check

Each item is untrusted. None has been acquired, quoted from a primary source, or
reviewed. All are named as items the ADR-0055 pre-research novelty re-check must
cover immediately before research starts, bound to the intake file's subject
hash.

- **U1.** The planning dossier reports Erdos Problem 663 as a catalogue entry
  asking whether `q(n,k) < (1 + o(1)) log n` for every fixed `k`, and lists it
  among tier A candidates rather than as settled. Untrusted: the catalogue label,
  the current status, and whether the `k = 3` case in particular is open.
- **U2.** The planning dossier reports the `(1 + o(1)) k log n` bound as "easy".
  Untrusted as an attribution and as a statement. Section 7 re-derives it rather
  than citing it, and the re-derivation's constants are the deliverable.
- **U3.** Whether the source states the product as `(n+1)...(n+k)` or as
  `n(n+1)...(n+k-1)`, and whether it asks for each fixed `k` or uniformly in `k`,
  cannot be checked offline. The frozen reading is `(n+1)(n+2)(n+3)` with `k`
  fixed first. A different indexing shifts `n` by one and changes every extremal
  value; a uniform-in-`k` reading is a strictly stronger statement. Both are
  rejected readings recorded in section 2 for audit.
- **U4.** The planning dossier's source ledger says the catalogue renderings are
  "not substitutes for the original Erdos sources or a literature review". That
  instruction is inherited unchanged.

## 7. Bounded first slice

Two independent pieces, both exact.

**Piece A — re-derive the easy upper bound at `k = 3` with explicit constants.**

The route, recorded in the intake file as `easy_upper_bound_route` and to be
re-derived rather than assumed: every prime strictly below `q(n,3)` divides
`(n+1)(n+2)(n+3)`, so

`theta(q(n,3)) - log q(n,3) <= log((n+1)(n+2)(n+3)) <= 3 * log(n+3)`,

where `theta(x) = sum_(p <= x) log p`. With an explicit Chebyshev bound of the
form `theta(x) > c_1 * x` valid for `x >= x_0`, this yields
`q(n,3) < (3/c_1) * log(n+3) + O(log log n)` with every constant named. The
deliverable is the explicit pair `(N(epsilon), constant)` and the arithmetic that
produces it, not the asymptotic shape. The constant this route gives is
proportional to `k = 3`; the target constant is 1. **That factor-3 gap is the
frozen obligation the slice reports open**, and the slice is not expected to
close it.

All arithmetic is exact rational. The Chebyshev constant must be either acquired
(section 5, row 4) or re-derived locally; a constant recalled by a model is
refused as input.

**Piece B — exhaustive extremal search for long initial-prime coverage.**

By `prime_divides_iff_residue`, for a prime `p >= 5`,
`p | (n+1)(n+2)(n+3)` iff `n mod p in {p-1, p-2, p-3}`, three distinct residues.
So `q(n,3) > P` iff `n` satisfies one of exactly 3 residue conditions modulo each
prime `p` with `5 <= p <= P`. By the Chinese remainder theorem the set of such
`n` is a union of residue classes modulo `prod_(5 <= p <= P) p`, and the number
of classes is exactly `3^(pi(P) - 2)`.

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
with `q(n,3) > P`. That value is a *complete* answer for that `P`, not a sample.

**Canonicalization and what is exhaustive.** Branches are indexed canonically by
the tuple of chosen offsets in `{1,2,3}` per prime, in increasing prime order, so
the enumeration has no duplicates and no symmetry quotient is needed or claimed.
Enumeration is exhaustive over branches for each `P <= 41`. Nothing is sampled.
`n` itself is never enumerated.

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

**Boundary of the claim.** No computation over a finite range of `n`, and no
complete enumeration of CRT branches for finitely many `P`, can establish the
frozen asymptotic claim. Nor can it refute it: the claim constrains only `n`
beyond an unspecified threshold, so no finite set of `n` is a counterexample.
What piece B can support is: an exact least `n` with `q(n,3) > P` for each
`P <= 41`, a certified lower bound on `sup q(n,3)/log n` over the enumerated
extremal `n`, and an exact structural description of the residue classes
achieving long coverage. Those are the retained facts, and none of them is the
theorem.

## 8. Certificate and verifier contract

| Result shape | Certificate format | Independent verifier |
|---|---|---|
| explicit upper bound at `k = 3` | the full derivation with every constant named, the explicit `N(epsilon)`, the source or local derivation of the Chebyshev constant, and every arithmetic step as exact rationals | human review of the derivation plus mechanical replay of every rational computation; the Chebyshev input must resolve to an acquired passage or a local exact derivation |
| certified extremal `n` for a stated `P` | the value `n`, the CRT branch tuple that produced it, the complete list of primes at most `P` with, for each, which of `n+1`, `n+2`, `n+3` it divides, and a rational enclosure of `log n` with its remainder bound | recompute the CRT branch, verify each divisibility by exact integer division, verify the enclosure endpoints and remainder bound, and re-derive the minimality over branches |
| a claimed improved constant `c < 3` | the derivation plus, for every inequality that was verified numerically, a rational enclosure with explicit endpoints | replay of the derivation and of every enclosure; a numerically-verified inequality without an enclosure is refused |
| unresolved | the exact envelope reached (`P` bound, branch count), the closed and open derivation obligations, and the constant actually achieved | replay of the enumeration to confirm the envelope, and inspection of the obligation list |

**Refused as a certificate.** Any floating-point value on a trust path,
including a floating-point evaluation of `log n` or of `q(n,3)/log n`. A model's
assertion of a constant, a threshold, or a Chebyshev bound. A third-party
program's output that has not been replayed. The failure of a sweep to find a
large ratio. Any finite computation presented as settling the asymptotic in
either direction.

## 9. Useful negative outcomes

- **The exact extremal record.** For each `P <= 41`, the exact least `n` with
  `q(n,3) > P`, with its CRT branch. This is a permanent exact fact independent
  of the conjecture and is reusable by any later attempt.
- **A certified lower bound on the ratio.** The largest certified value of
  `q(n,3)/log n` inside the envelope, with its rational enclosure. If that value
  stays well above 1 as `P` grows, that is a recorded measurement of how far the
  data are from the conjectured constant — not evidence against it.
- **The refuted route.** If the re-derivation of piece A cannot be pushed below
  the constant 3 by the intended argument, the exact point where it stalls is
  recorded, together with the inequality that would have to improve. That is the
  reusable artifact: the next attempt starts from the named inequality.
- **The frontier.** The `P` bound reached, the branch count, and the wall of the
  envelope, so the next slice resumes from a recorded position.
- **The structural characterization.** The exact description of the residue
  classes modulo `prod_(5 <= p <= P) p` that achieve `q(n,3) > P`, which is a
  complete answer to a well-posed finite question even when the asymptotic stays
  open.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. `version` 1, `phase`
`exploratory`.

Metrics: `extremal_n_certified`, `crt_branches_enumerated`,
`primes_covered_max`, `rational_enclosures_verified`,
`derivation_obligations_closed`, `failed_routes_preserved`, `model_cost_usd`.

Success criteria:

- an exact re-derivation of the easy upper bound at `k = 3` with an explicit
  threshold `N` as a function of `epsilon` and explicit constants, every step
  replayable in exact rational arithmetic
- an exactly certified extremal `n` together with the complete list of primes
  dividing `(n+1)(n+2)(n+3)` and a rational enclosure of `log n` that pins the
  ratio `q(n,3) / log n` at that `n`
- or an explicit unresolved outcome recording the smallest remaining obligation,
  namely the exact gap between the re-derived constant at `k = 3` and the target
  constant 1

Stopping rules:

- stop when the easy upper bound at `k = 3` is re-derived with explicit constants
  and an explicit threshold as a function of `epsilon`
- stop when an exact certificate establishes a new largest certified value of
  `q(n,3) / log n` inside the frozen search envelope
- stop when the fresh model spend reaches USD 20
- stop when no derivation obligation has been closed and no new extremal `n` has
  been certified for two consecutive review points
- never promote a finite sweep of `n` into the asymptotic claim or into its
  refutation: exhausting any range of `n` leaves the limit untouched

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Finite search read as an asymptotic result | The measured ratio is near 2.3 and falling; a narrative that it "trends toward 1" would be a fabricated asymptotic | `finite_search_not_asymptotic` is an assumption in the intake file, the last stopping rule forbids the promotion, and section 7 states the boundary in both directions |
| An unquantified `o(1)` in the output | The entire content of the source question is the `k`-dependence of the threshold; an unnamed constant hides exactly that | `threshold_depends_on_k` requires every threshold, error term, and implied constant to be an explicit function of `epsilon` and of `k = 3`; a derivation with an unnamed constant is refused |
| Product indexing off by one | `n(n+1)(n+2)` versus `(n+1)(n+2)(n+3)` changes every extremal value and every table | Frozen in section 2 with the alternative recorded as rejected; U3 names it as the acquisition question that would settle the source's own indexing |
| Recalled Chebyshev constant | A model-recalled explicit constant is untrusted and would silently corrupt the threshold | Section 5 row 4 is the acquisition target; otherwise the constant is re-derived locally. Recalled values are refused as input |
| Floating-point `log` on the trust path | The repo owner rejects floating-point solvers outright, and a ratio comparison is exactly where a float would sneak in | `exact_arithmetic_requirement` mandates rational enclosures with certified remainder bounds, exclusion-only; floats are print-only and labelled |
| Logarithm base drift | A base-2 reading multiplies the bound by about 1.44 and makes an unrelated statement look proved | `log_base` fixes base `e` and records base 2 and base 10 as rejected |
| Envelope inflation | Branch count grows as `3^(pi(P)-2)`, so a small increase in `P` silently multiplies cost | Envelope frozen at `P <= 41` with the exact branch count and modulus tabulated in section 7; any extension is a new decision, not a parameter tweak |
| `k = 3` result read as the source question | The source asks for every fixed `k`; one `k` is a special case | `strength_relation` is `weaker`, and the first quantifier-mapping row says `k` is frozen to 3 with no other `k` in scope |

## 12. Capability check

**Covered by existing AdaIvy capabilities.**

- Declarative intake with the trust boundary intact: the intake file validates
  against `schemas/problem-definition-v1.schema.json` and produces
  `logical_status unknown`, novelty and significance `not_assessed`, zero
  warrants.
- Exact arbitrary-precision integer arithmetic, CRT reconstruction, and exact
  rational arithmetic as project-authored standard-library code under `src/`,
  with deterministic serialization, content hashes, and captured output.
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
  explicit prime-counting bounds or high-precision logarithms. Not needed for the
  frozen envelope: CRT enumeration and rational enclosures are standard-library
  work.
- Acquisition of any section 5 source, which is ADR-0050 territory and needs
  per-URL human planning and separate authorization.
- Execution of model-generated code, which stays disabled under ADR-0057 until
  its digest-pinned OCI sandbox gate passes. Every program here is
  project-authored and reviewed.
- Any sieve over `n` beyond the CRT envelope large enough to need out-of-core
  storage or a longer-running job class.

**Explicitly not activated.** Parallel specialists, evolutionary search, higher
search tiers, crawling, result following, and automated novelty or significance
assessment.

## 13. Open questions before intake

1. Is `k = 3` the value the operator wants frozen, given the justification in
   section 1? `k = 2` is a materially different configuration; `k = 4` and above
   raise the forced-divisor set and shrink the extremal density.
2. Is the product indexing `(n+1)(n+2)(n+3)` correct against the original source?
   This is U3 and is the one question that could invalidate every extremal value
   computed. It cannot be answered offline.
3. Is `P <= 41` the right envelope, or should the frozen bound be lower so the
   first run is cheaper, or higher because the extremal structure only becomes
   informative later?
4. Should the explicit Chebyshev constant be acquired (section 5 row 4) or
   re-derived locally? Re-deriving it is more work but keeps the slice free of
   acquisition dependencies.
5. Should a refutation-shaped outcome be in scope at all? The frozen target is a
   `prove` target; a disproof would need an infinite family of `n`, which no part
   of this slice can produce, so the slice reports only progress and obligations.
