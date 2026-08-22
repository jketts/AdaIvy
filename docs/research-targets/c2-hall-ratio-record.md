# C2. Hall-ratio record — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item C2 (tier C)
**Declared domain:** diophantine-approximation
**Intake file:** docs/research-targets/intake/c2-hall-ratio-record-v1.json
**Frozen in one line:** There exist positive integers `x` and `y` with
`y^2 != x^3` such that the exact integer inequality
`x > 10000 * (y^2 - x^3)^2` holds.

This is a scoped intake package. It does not approve a formalization, establish
that the problem is open, authorize source acquisition, assess novelty or
significance, create mathematical warrant, or activate any capability. Novelty,
significance, and source applicability are `not_assessed` and stay that way. No
primary source has been acquired, so the reported record and the reported ratio
normalization in section 6 are untrusted candidates and are not premises.

## 1. Frozen target

**Target.** There exist positive integers `x` and `y` with `y^2 != x^3` such
that

`x > 10000 * (y^2 - x^3)^2`.

Symbols: `x` and `y` range over the positive integers `{1, 2, 3, ...}`. The
quantity `h = y^2 - x^3` is an integer, nonzero by the hypothesis `y^2 != x^3`.
Both sides of the displayed inequality are integers, so the comparison is an
exact integer comparison. Quantifier structure: a single existential over a pair
of positive integers, unbounded. Scope: `existential`.

The displayed inequality is the frozen form. It is equivalent, on the frozen
domain, to the ratio form `sqrt(x) / |y^2 - x^3| > 100`; the equivalence is
verified in section 2.1 rather than assumed. The frozen form is the one that
appears on every trust path, because it never mentions a square root.

## 2. Definitions and conventions

### 2.1 The equivalence, verified

Let `x, y` be positive integers with `y^2 != x^3`, and put `h = y^2 - x^3`, so
`h` is a nonzero integer and `|h| >= 1`.

*Step 1.* `|h| > 0`, so multiplying the strict inequality
`sqrt(x) / |h| > 100` by the positive quantity `|h|` preserves it in both
directions:

`sqrt(x) / |h| > 100`  iff  `sqrt(x) > 100 * |h|`.

*Step 2.* Since `x >= 1`, `sqrt(x)` denotes the nonnegative real square root, so
`sqrt(x) >= 0`; and `100 * |h| > 0`. For nonnegative reals `a` and `b`, the map
`t -> t^2` is strictly increasing on `[0, inf)`, hence `a > b` iff `a^2 > b^2`.
Applying this with `a = sqrt(x)` and `b = 100 * |h|`:

`sqrt(x) > 100 * |h|`  iff  `(sqrt(x))^2 > (100 * |h|)^2`.

*Step 3.* `(sqrt(x))^2 = x` because `x >= 0`. And
`(100 * |h|)^2 = 10000 * |h|^2 = 10000 * h^2`, because `|h|^2 = h^2` for every
integer `h`. Therefore

`sqrt(x) / |h| > 100`  iff  `x > 10000 * h^2`,

which is the frozen form with `h = y^2 - x^3`. Both directions hold; nothing was
weakened. The planning dossier writes the right-hand side as
`10000 |y^2 - x^3|^2`, which is the same integer as `10000 (y^2 - x^3)^2` by the
identity `|h|^2 = h^2`, so the two renderings agree.

Two consequences worth recording. First, `sqrt(x)` never needs to be computed:
the trust path evaluates only integer multiplications and one integer
comparison, so the "no floating point" rule is satisfied by construction rather
than by discipline. Second, since `|h| >= 1`, the inequality forces
`x > 10000`, so no witness has `x <= 10000`.

### 2.2 Definitions table

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| the ratio | `sqrt(x) / \|y^2 - x^3\|`, with the numerator the square root of `x` and the denominator the absolute value of `y^2 - x^3` | the reciprocal `\|y^2 - x^3\| / sqrt(x)`, under which "greater than 100" becomes "less than 1/100" and the target inverts; any logarithmic normalization such as `log x / (2 log\|y^2-x^3\|)` |
| the threshold | strictly greater than `100`, that is `x > 10000 h^2` with strict inequality | `>= 100`, which admits the boundary case `x = 10000 h^2`; a threshold of `46.6` or any value read off a reported record |
| sign convention | absolute value, so `y^2 - x^3` and `x^3 - y^2` give the same target | a signed convention requiring `y^2 - x^3 > 0`, or requiring `x^3 - y^2 > 0`; each halves the search space and defines a different problem |
| `x`, `y` | positive integers, `x >= 1` and `y >= 1` | integers, which would admit `y <= 0` and `x <= 0`; rationals; `y = 0` |
| `y^2 != x^3` | excludes exactly the pairs where `h = 0`, for which the ratio is undefined and the frozen inequality `x > 0` would hold vacuously and wrongly | omitting the hypothesis, which makes every `x` with `x^3` a perfect square a spurious witness of the frozen inequality |
| the checked form | the integer inequality `x > 10000 * (y^2 - x^3)^2` | the real inequality evaluated by computing a floating-point square root and comparing; a rational or interval approximation of `sqrt(x)` |
| witness | one pair `(x, y)` of positive integers with `y^2 != x^3` satisfying the frozen integer inequality | a pair whose ratio merely exceeds the reported record `46.6`; a pair found by a floating-point search and not re-checked exactly |
| certified exclusion range | `1 <= x <= X` for a frozen `X`, exhausted over **all** positive `y` by the reduction of section 2.3 | a range exhausted only over a sampled or bounded set of `y`, which would be a strictly weaker record with the same wording |

### 2.3 The nearest-square reduction, verified

This is the reduction that makes the target searchable and that makes a bounded
sweep say something universal in `y`.

Fix an integer `x >= 1` and let `r = isqrt(x^3)`, the exact integer square root,
so `r^2 <= x^3 < (r+1)^2`. First, `r >= x`: from `x >= 1` we get `x^2 <= x^3`,
and `isqrt` is nondecreasing, so `x = isqrt(x^2) <= isqrt(x^3) = r`.

Let `y >= 1` be an integer with `y^2 != x^3`, and `h = y^2 - x^3`.

- If `y <= r - 1`, then `y^2 <= (r-1)^2 = r^2 - 2r + 1 <= x^3 - 2r + 1`, so
  `h <= -(2r - 1)` and `|h| >= 2r - 1 >= 2x - 1 >= x`.
- If `y >= r + 2`, then `y^2 >= (r+2)^2 = r^2 + 4r + 4`, while
  `x^3 < (r+1)^2 = r^2 + 2r + 1`, so `h > 2r + 3 > x`, and `|h| > x`.

In either case `|h| >= x`, hence `10000 h^2 >= 10000 x^2 >= 10000 x > x`, so the
frozen inequality fails. Therefore **every** witness has `y in {r, r+1}` where
`r = isqrt(x^3)`.

Consequently a sweep over `1 <= x <= X` needs to examine exactly two values of
`y` per `x`, and the resulting exclusion is universal in `y` rather than
truncated: it establishes that no positive integer `y` whatsoever pairs with any
`x <= X`. The case `y = r` with `r^2 = x^3` is excluded by the hypothesis
`y^2 != x^3` and is skipped, leaving only `y = r + 1` for those `x`.

## 3. Formalization and quantifiers

Formal language: `typed_informal_math`, version 1, approval status `proposed`.
Human approval of the alignment in section 4 has not been requested.

```
exists x y : N,
  x >= 1 and y >= 1
  and y^2 != x^3
  and x > 10000 * (y^2 - x^3)^2
```

Quantifiers: two existentials over the positive integers, both unbounded. There
are no other quantifiers; in particular no asymptotic content and no implicit
epsilon. Everything in the body is a polynomial identity or comparison over `Z`,
decidable exactly.

The reduction of section 2.3 supplies the derived universal statement that a
bounded run can actually establish:

```
forall x : N, 1 <= x <= X ->
  forall y : N, y >= 1 and y^2 != x^3 ->
    not (x > 10000 * (y^2 - x^3)^2)
```

which is proved for a frozen `X` by checking only
`y in {isqrt(x^3), isqrt(x^3)+1}` for each `x`. That derived statement is
bounded in `x` and
universal in `y`, and it is not the target.

## 4. Semantic alignment to the source statement

Human approval of this alignment is required and absent. The source statement
used here is the planning dossier's line: find positive integers `x, y` with
`y^2 != x^3` such that `sqrt(x)/|y^2 - x^3| > 100`, checked without floating
point, for example as `x > 10000 |y^2 - x^3|^2`. That line is itself a
transcription of an unacquired benchmark statement.

**Quantifier mapping.** `x` maps to "positive integer `x`"; `y` maps to
"positive integer `y`". The planning line has no further quantifier.

**Definition mapping.**

- `sqrt(x)/|y^2 - x^3| > 100` maps to `x > 10000 * (y^2 - x^3)^2`, by the
  equivalence verified in section 2.1.
- "without floating point" maps to: the only operations on the trust path are
  integer multiplication, subtraction, exponentiation to fixed small exponents,
  exact integer square root in the search reduction, and integer comparison.
- "the two integers and direct big-integer arithmetic" maps to the certificate
  contract of section 8.1.

**Assumption delta.** The frozen target uses absolute value, so it is
insensitive to the sign convention; the benchmark may not be. The threshold is
strict. The domain is positive integers in both coordinates. If the primary
benchmark statement normalizes the ratio differently — reciprocal, signed,
logarithmic, or with a different exponent on `x` — then this is a different
target and the result is a **new dossier**, not an edit of this one. That
possibility is the reason the strength relation below is `unresolved` and is
recorded as claim 6.2.

**Edge-case delta.** `h = 0` is excluded by hypothesis and is not a vacuous
witness. No witness has `x <= 10000`, a consequence of `|h| >= 1`. `y = r` is
skipped exactly when `x^3` is a perfect square. For `x = 1` we get `x^3 = 1`
and `r = 1`, and the only candidate `y = 2` gives `h = 3`, failing the
inequality.

**Strength relation:** `unresolved`. The frozen target is a faithful
transcription of the planning line, but the planning line's own fidelity to the
benchmark statement cannot be settled before acquisition, and `equivalent` is
not available without a quoted acquired source.

## 5. Provenance and acquisition plan

Nothing in this table has been fetched. Under ADR-0050 acquisition is
human-planned, exact-URL, and separately authorized. Every locator below is an
unverified recollection written from memory; the operator must confirm each one
before acquisition, and a locator that fails to resolve is a finding to record.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| FrontierMath open-problems index, the entry carrying this Hall-ratio task | https://epoch.ai/frontiermath/open-problems , the individual problem page for the Hall-ratio task | claims 6.1 and 6.2: the exact benchmark statement, its ratio normalization, its threshold, and its verifier contract. This is the single row that decides whether the frozen target is the intended one | pending_acquisition, applicability not_assessed |
| Marshall Hall Jr., "The Diophantine equation `x^3 - y^2 = k`", in Computers in Number Theory, Academic Press 1971, pages 173-198 | no DOI known; locator to be supplied by the operator | the original normalization of the conjecture and of the ratio, and the original sign convention | pending_acquisition, applicability not_assessed |
| Elkies, "Rational points near curves and small nonzero `\|x^3 - y^2\|` via lattice reduction", ANTS-IV, LNCS 1838 (2000), pages 33-63 | doi:10.1007/10722028_2 | claim 6.3: the 1998 example, the ratio value reported for it, and the lattice-reduction search method whose status as exploration-only is recorded in section 7.4 | pending_acquisition, applicability not_assessed |
| The maintained table of Hall's-conjecture records | exact URL unknown and to be supplied by the operator under ADR-0050 | claim 6.3 and claim 6.4: the current record value, the record holder, and the normalization the table uses | pending_acquisition, applicability not_assessed |
| Any recent survey of Hall's conjecture and the `abc` connection | to be identified by the operator; no locator asserted here | claim 6.5: whether the existence of ratios above 100 is expected, expected to be finite, or conjecturally impossible, which changes how a negative outcome should be read | pending_acquisition, applicability not_assessed |

## 6. Prior-status claims to re-check

Each is untrusted, none is a premise, and each must be covered by the ADR-0055
pre-research novelty re-check bound to this problem's subject hash before any
run.

- **6.1** "The benchmark asks for a ratio above `100`." Untrusted. If the
  threshold differs, the frozen inequality's constant `10000` changes and the
  target changes with it.
- **6.2** "The ratio is normalized as `sqrt(x)/|y^2 - x^3|`." Untrusted, and the
  single highest-impact claim in this dossier. A reciprocal, signed, or
  logarithmic normalization makes this a different target requiring a new
  dossier rather than a correction.
- **6.3** "The current record is about `46.6`, from Elkies's 1998 example."
  Untrusted, both as to value and as to attribution. It is recorded because it
  calibrates how far a bounded sweep is from the frontier, not because it is
  used in any computation.
- **6.4** "No pair with ratio above `100` is known." Untrusted and unassessed.
  This dossier does not establish that the target is open.
- **6.5** "Small `|h|` reduces to Mordell equations `y^2 = x^3 + h` whose
  integral points are tabulated for small `|h|`." Untrusted. If true it would
  close the `|h| = 1, 2, 3, ...` strata by citation rather than by sweeping, but
  only after acquisition and only as far as the tables' own certified range
  reaches. It is route guidance, not a premise.
- **6.6** "Lattice reduction is the method that produces good examples."
  Untrusted. Section 12 records that an exact-integer implementation of it is
  not an existing capability.

## 7. Bounded first slice

One sub-slice, exhaustive, offline, exact integer arithmetic throughout. This is
the cleanest certificate contract in the whole portfolio: a positive result is
two integers and three multiplications, and a negative result is a universal
statement in `y` over a frozen range of `x`. Nothing here calls a model or the
network. The program must be human-authored; see section 12.

### 7.1 Inputs and algorithm

**Input.** The frozen sweep bound `X = 10^8`, and the frozen range
`1 <= x <= X`.

**Algorithm.** For `x = 1, 2, ..., X`:

1. Compute `c = x^3` by exact integer multiplication.
2. Compute `r = isqrt(c)` by exact integer square root. The implementation seeds
   Newton's iteration from the previous `r` and iterates in exact integer
   arithmetic until the invariant `r^2 <= c < (r+1)^2` is verified; the
   invariant is checked, not assumed, on every step.
3. If `r * r != c`, evaluate `h = r*r - c` and test `10000 * h * h < x`.
4. Evaluate `h = (r+1)*(r+1) - c` and test `10000 * h * h < x`.
5. Record any pair passing a test as a candidate witness and hand it to the
   independent verifier of section 8.1.

Steps 3 and 4 are exhaustive over `y` by the reduction of section 2.3, which the
run re-derives and re-checks rather than inheriting from this dossier: for a
frozen sample of `x` values the run also brute-forces `y` over
`[r - 100, r + 100]` and confirms that no additional candidate appears, as a
falsifiability probe on the reduction itself. A probe that cannot fail proves
nothing, so the probe is also run with the reduction deliberately mis-stated as
`y in {r}` and must then flag the missing `y = r+1` cases.

### 7.2 Search envelope and arithmetic cost

The envelope is `X = 10^8` values of `x`, each costing one cube (operands to
about `80` bits at the top of the range), one warm-started exact integer square
root, and at most four multiplications and two comparisons. That is on the order
of `10^9` big-integer operations at `80`-bit width. Throughput is measured and
recorded rather than assumed; the record carries the measured rate so the
extrapolation below is arithmetic on a measured number.

The extrapolation matters and is stated plainly: the reported record in claim
6.3 sits near `x` of order `10^15` to `10^16`. Reaching `10^16` by this sweep
would require `10^8` times the frozen work. Direct sweeping therefore cannot
approach the reported frontier, and no amount of budget inside this slice
changes that. The value of the slice is the exact verifier, the falsifiability
probe on the reduction, and a certified exclusion envelope that is universal
in `y`.

### 7.3 What is enumerated exhaustively versus sampled

Exhaustive: every integer `x` in `[1, X]`, and, by the reduction, every positive
integer `y` whatsoever. Sampled: only the falsifiability probe of section 7.1,
which is a check on the reduction and never a substitute for it. No
canonicalization or symmetry quotient applies, because the target has no
symmetry to quotient by: the pair `(x, y)` is ordered and both coordinates carry
different roles.

### 7.4 Rejected search strategies, and why

- **Enumerating `y` instead of `x`.** Sweeping `y` to `Y` covers only `x` up to
  about `Y^(2/3)`, so it is strictly less efficient per unit of exact
  arithmetic. Rejected as redundant.
- **Naive two-dimensional sweep over `(x, y)`.** Superseded by the reduction,
  which removes an entire dimension with a proof rather than a heuristic.
- **Floating-point pre-filtering.** Computing `sqrt(x)` in floating point to
  pre-screen would put a float on the path from candidate generation to the
  record. It is refused; the exact `isqrt` reduction is both exact and cheaper.
- **Lattice-reduction accelerated search.** This is the method claim 6.6
  attributes to the good examples, and it is the only route that plausibly
  reaches the reported frontier. An exact-integer implementation is not an
  existing capability here and is listed in section 12 as needing a new ADR. It
  is not part of this slice.

### 7.5 The boundary of the claim the slice can support

The slice can support exactly: for every integer `x` with `1 <= x <= 10^8` and
every positive integer `y` with `y^2 != x^3`, the inequality
`x > 10000 (y^2 - x^3)^2` is false. It cannot support anything about `x > 10^8`.
It is a needle-in-a-haystack existential and the expected outcome is the
certified exclusion envelope, not a witness.

## 8. Certificate and verifier contract

### 8.1 Result shape R1 — a witness is found

Certificate: the ordered pair `(x, y)` in exact decimal. Nothing else is needed
and nothing else is accepted as part of it.

Independent verifier, sharing no code with the search: read `x` and `y`, confirm
both are integers with `x >= 1` and `y >= 1`, compute `c = x^3` and `s = y^2` by
exact big-integer arithmetic, confirm `s != c`, set `h = s - c`, and confirm
`x > 10000 * h * h`. Four exact multiplications, one subtraction, one
comparison, no square root, no division, no floating point. This is the whole
contract, and its brevity is the point: the certificate is small enough that a
reader can check it by hand for small operands and a second independent
implementation can check it in a few lines.

### 8.2 Result shape R2 — a certified exclusion envelope

Record: the frozen bound `X`, the exhaustive statement of section 7.5, the
reduction of section 2.3 in machine-readable form together with the outcome of
its falsifiability probe, the measured candidate count at each `|h|` stratum
(the minimum of `10000 h^2 - x` observed, which quantifies how far the range is
from producing a witness), and a canonical hash of the record.

Independent verifier: re-run the sweep from `X` alone and compare canonical
hashes; and independently re-derive the reduction and re-run its probe.

### 8.3 Result shape R3 — a proof that no witness exists

Certificate: a proof object in the repository's existing formal or
human-reviewed channel. No route to this shape is proposed here; it is listed so
that the negation of the target has a declared contract rather than being
unrepresentable. Claim 6.5, if it survives acquisition, is the only visible
partial route, and it closes strata rather than the target.

### 8.4 What is refused as a certificate

- Any floating-point value on the trust path, including a floating-point
  `sqrt(x)` used to compute or display the ratio. A displayed ratio value is
  presentation, never evidence; the record stores `x`, `y`, and `h`, not a
  decimal ratio.
- A rational or interval approximation to `sqrt(x)`. Exact interval arithmetic
  with rational endpoints is admissible only for exclusion, and here it is
  unnecessary because the integer form is exact.
- A model's assertion that a pair satisfies the inequality.
- An unreplayed third-party or library computation of `isqrt`, `x^3`, or the
  comparison.
- Failure of the sweep. R2 is not evidence about `x > X`.
- A pair whose ratio exceeds the reported record `46.6` but not `100`. That is a
  distinct recorded outcome and must never be reported as meeting the frozen
  target.

## 9. Useful negative outcomes

- **The certified exclusion envelope.** The R2 record for `1 <= x <= 10^8`,
  universal in `y`. Because of the reduction it is a genuinely quantified
  statement and not a sampled one, which is unusual for a bounded search and is
  the main retained asset.
- **The reduction, with its falsifiability probe.** A proved statement that only
  `y in {isqrt(x^3), isqrt(x^3)+1}` can matter, with a probe demonstrating that
  a mis-stated version of it fails. This is reusable for any future Hall-type
  target and is independent of the frozen threshold `100`.
- **A measured distance-to-frontier record.** The minimum observed value of
  `10000 h^2 - x` per `|h|` stratum, which is a machine-readable measure of how
  far the swept range is from a witness, and which makes the cost argument of
  section 7.2 concrete instead of rhetorical.
- **A closed route record.** The rejected strategies of section 7.4 are
  preserved with reasons, including the explicit note that direct sweeping
  cannot reach the reported frontier, so a later run does not re-attempt it.
- **A near-miss ledger.** Any pair with ratio above the reported record but
  below the frozen threshold is retained under its own label, never as a
  near-success on the frozen target.

## 10. Evaluation protocol

Mirrors the intake JSON exactly. Phase: `exploratory`. Version: `1`.

Metrics:

- `x_values_swept_exhaustively`
- `exact_integer_square_roots_verified`
- `candidate_pairs_meeting_frozen_inequality`
- `certified_exclusion_ranges_recorded`
- `reduction_falsifiability_probes_flipped`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria:

- `an exhibited pair of positive integers (x, y) with y^2 != x^3 for which x > 10000 * (y^2 - x^3)^2 is confirmed by independent big-integer arithmetic`
- `a rigorous proof that no such pair of positive integers exists`
- `or an explicit unresolved outcome recording the certified exclusion range 1 <= x <= X, universal in y, and the smallest remaining obligation`

Stopping rules:

- `stop on an exact certificate: a pair (x, y) confirmed by the independent big-integer verifier`
- `stop when the fresh model spend reaches USD 25`
- `stop when two consecutive review points extend the certified exclusion range by nothing and close no obligation`
- `never promote the certified exclusion range 1 <= x <= X into a claim about any x greater than X`
- `refuse any floating-point square root or ratio value as evidence and halt rather than record one`

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Normalization mismatch | If the benchmark's ratio is the reciprocal or is signed, every hour spent is spent on a different problem | claim 6.2 is the highest-priority acquisition row; the strength relation is `unresolved`; a mismatch produces a new dossier rather than an edit |
| Threshold drift | Reading the threshold off the reported record `46.6` instead of the frozen `100` would silently change the target and make a non-witness look like a win | the threshold is frozen in section 1 and in the certificate contract; section 8.4 refuses sub-threshold pairs; the near-miss ledger gives them a separate home |
| Floating point via the ratio display | The ratio is the natural thing to print, and printing it invites computing it | the record stores `x`, `y`, `h` only; a displayed ratio is labelled presentation; section 8.4 refuses it as evidence |
| Reduction error | The whole exhaustiveness claim in `y` rests on section 2.3; an off-by-one there would silently turn a universal statement into a false one | the reduction is re-derived in-run, probed against a brute-force window, and probed again in a deliberately mis-stated form that must fail |
| Frontier illusion | `10^8` swept values read as progress toward a record near `10^16` | section 7.2 states the factor of `10^8` explicitly; the stopping rules forbid promotion |
| The target may be false | An unbounded existential can absorb any budget | the deliverable is defined as the R2 envelope; spend and stagnation caps are in the stopping rules; the success criteria include the unresolved outcome |
| Warm-started `isqrt` drift | Seeding Newton from the previous `r` is the main speedup and a wrong seed silently returns a wrong `r` | the invariant `r^2 <= x^3 < (r+1)^2` is verified on every step, so a wrong `r` is a hard failure rather than a wrong verdict |
| Lattice route creeping in | It is the only route to the frontier and therefore constantly tempting | section 7.4 rejects it for this slice and section 12 records that it needs a new ADR |

## 12. Capability check

**Covered by existing AdaIvy capabilities.** Exact unbounded integer arithmetic
and exact integer square root from the standard library, which is everything
sections 7 and 8 need, as repository-authored code under `src/` exercised by the
offline suite — ad-hoc exact arithmetic written and run by the driving agent in a
scratch workspace is NOT this capability, but an unmet AdaIvy capability and an
external-origin contribution under ADR-0057 section 5, imported with an
`external_codex` or `human` root and never relabelled as AdaIvy work.
Declarative problem intake and the Phase 1 trust policy.
Deterministic serialization, content hashing, and canonical records for the R2
envelope. The falsifiability-probe pattern already used by the Phase 6
generality suite and the publication projection, which is what section 7.1's
probe on the reduction imitates: a rule that cannot be made to fail proves
nothing. Machine-readable preservation of failed routes. Bounded, no-network
subprocess execution with captured output. The ADR-0055 pre-research novelty
re-check, which must cover every claim in section 6.

**Would require a new ADR.**

- An exact-integer lattice-reduction search, the one route that plausibly
  reaches the reported frontier. Exact LLL over the integers is not a
  floating-point solver and is therefore not excluded in principle by the
  repository-owner rule, but it does not exist here and adding it is a new
  capability decision with its own acceptance suite.
- Execution of a model-authored search program. ADR-0057 leaves production
  generated-code execution disabled until its digest-pinned OCI sandbox gate
  passes, so the sweep program is human-authored or the run does not happen.
- Any parallel or distributed sweep. The current runtime is one bounded central
  lead; parallel specialists need ADR-0029 activation evidence and a measured
  retention gain.
- A durable resumable sweep store, if a later slice's `X` exceeds one bounded
  run.
- Acquisition of any row in section 5, which is a separate ADR-0050
  authorization with an exact URL.

**Explicitly not activated.** No floating-point solver of any kind, which the
repository owner rejects outright and which this target does not need. No new
network path, no model call inside the arithmetic, no higher search tier, no
automated novelty or significance assessment.

## 13. Open questions before intake

1. Is the threshold `100` and the normalization `sqrt(x)/|y^2 - x^3|` confirmed
   against the benchmark statement? Until claim 6.2 is settled, the frozen
   target may be the wrong problem, and no run should start.
2. Does the benchmark use absolute value, or does it fix a sign? The frozen
   target uses absolute value and is therefore a union of the two signed
   variants.
3. Is `X = 10^8` the right first envelope, given that it cannot approach the
   reported frontier? An operator may prefer a much smaller `X` whose only
   purpose is to exercise the verifier and the probe.
4. Should the `|h| = 1, 2, 3` strata be closed by acquiring the Mordell-equation
   tables of claim 6.5 instead of by sweeping? That is an acquisition decision
   and changes the slice's shape.
5. Is an exact-integer lattice-reduction capability something the operator wants
   scoped as a separate ADR, or is this target to remain a verifier-plus-sweep
   exercise?
6. Confirm that the intended deliverable is the R2 certified exclusion envelope,
   so that the predicted negative outcome is not judged a failure.
