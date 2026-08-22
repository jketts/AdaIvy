# A6. The cubic equation `z^2 + y^2 z + x^3 = 2` — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item A6 (tier A)
**Declared domain:** diophantine-geometry
**Intake file:** docs/research-targets/intake/a6-cubic-diophantine-z2-y2z-x3-v1.json
**Frozen in one line:** The set
`S = { (x,y,z) in Z^3 : z^2 + y^2 z + x^3 - 2 = 0 }` is infinite.

This is a scoped intake package. It does not approve a formalization, establish
that the frozen statement is open, authorize source acquisition, assess novelty
or significance, create mathematical warrant, or activate a runtime capability.
Novelty, significance, and source applicability are `not_assessed`. The planning
dossier's claim that this equation is one of six remaining after three of nine
were settled in 2026 is untrusted and unacquired; it is recorded in section 6.
The exact integer computations reported below are local, bounded, and create no
warrant.

## 1. Frozen target

Let

`S = { (x,y,z) in Z^3 : z^2 + y^2 * z + x^3 - 2 = 0 }`,

equivalently the integral solution set of `z^2 + y^2 z + x^3 = 2`, where `x`,
`y`, `z` each range over all of `Z` including zero and negative values.

**Frozen statement.** `S` is infinite. Explicitly, with height
`H(x,y,z) = max(|x|,|y|,|z|)`:

for every positive integer `B` there exists `(x,y,z) in S` with `H(x,y,z) > B`.

**One direction only.** The planning dossier poses a determination question
whose two answers are finiteness and infinitude. Exactly one is frozen here:
infinitude. A proof of finiteness *refutes* this target rather than answering
it, and is retained as a recorded negative outcome under section 9 — not
reported as a success against this claim. The disjunction is not the target.

**Why infinitude and not finiteness.** Three reasons, of which only the third is
a reason about mathematics rather than about method.

- The positive certificate for infinitude has an exact, replayable shape: an
  explicit parametric family given by integer polynomials in one parameter, plus
  a polynomial identity over `Z` verified by coefficient comparison. That fits
  the exact-arithmetic trust path directly. A finiteness proof would need
  effective results on integral points of an affine cubic surface, which is a
  capability AdaIvy does not have and which section 12 lists as requiring a new
  ADR.
- Freezing finiteness would make the bounded slice's natural output — new
  solutions of larger height — evidence *against* the frozen target, which
  inverts the incentive structure of the protocol.
- An exploration-only divisor heuristic diverges. For each `x` the number of
  divisors of `x^3 - 2` is about `log|x|`, and a divisor split must make a
  quantity of size about `|x|^(3/2)` a perfect square, so the expected count
  over `|x| <= X` is of order `X^(1/4) log X`, which diverges. The measured
  counts in section 7 are consistent with that order. This is labelled
  exploration-only in the intake file: it is not evidence that `S` is infinite,
  it creates no warrant, and it may never enter a certificate. It is recorded
  because the *choice of direction* must be auditable, not because it justifies
  the claim.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| the equation | `z^2 + y^2 z + x^3 - 2 = 0`, constant `-2` on the left, equivalently `z^2 + y^2 z + x^3 = 2` | `z^2 + y^2 z + x^3 + 2 = 0`; any sign variant; any version with a free parameter |
| integral solution | a triple of rational integers | `S`-integral point, algebraic-integer point, rational point, or solution over a ring of integers of a number field |
| `S` | the full solution set in `Z^3`, no normalization applied to the *set* | the set of solutions with `y >= 0` only, or with `x > 0` only |
| infinite | `S` has infinitely many elements; equivalently unbounded height | infinitely many `x`-values, or infinitely many `y`-values; those are stronger statements |
| height | `max(|x|,|y|,|z|)` | logarithmic height, projective height, or `|x|` alone |
| finiteness | `|S| < infinity`; the frozen target is its exact negation | "finiteness or infinitude", which is a disjunction and not a target |
| obvious symmetries | only `y -> -y`, since `y` occurs solely as `y^2` | `x -> -x` or `z -> -z`, neither of which preserves the equation |
| the target direction | infinitude, chosen and justified in section 1 | the disjunction; or finiteness, which is recorded as a rejected target and an outcome shape |
| known small solutions | the triples in section 7, each re-checked by exact substitution | any solution list taken from a catalogue or recalled by a model without substitution |
| complete in `x` | for the stated `x`, all `y` and all `z` are covered by the divisor characterization | a box search in `(x,y)` or `(y,z)`, which is complete in nothing |

## 3. Formalization and quantifiers

```
let S = { (x,y,z) in Z^3 : z^2 + y^2 * z + x^3 - 2 = 0 }

claim: forall B in Z with B >= 1,
         exists (x,y,z) in S with max(|x|,|y|,|z|) > B
```

Quantifier list as recorded in the intake file:

- `forall B a positive integer`
- `exists (x,y,z) in Z^3 with z^2 + y^2 * z + x^3 - 2 = 0 and max(|x|,|y|,|z|) > B`

`formal_language` is `typed_informal_math`, `version` 1, `approval_status`
`proposed`. The freeze is clean: `S` is exactly specified independently of any
source, so no operator answer is needed to state the target. What is *not*
settled is the mapping to the source question, which is why the strength
relation in section 4 is `unresolved` and why section 13 names the exact
question. `needs_clarification` was considered and rejected for that reason: the
ambiguity blocks the *alignment*, not the freeze.

`target_claim.scope` is `particular`: the claim is a single assertion about one
fixed set. The `existential` reading was rejected — the target is not "find one
object" but "this specific set is unbounded" — and `unrestricted_universal` was
rejected because there is no universally quantified family of objects, only the
`forall B` that unwinds the word "infinite".

## 4. Semantic alignment to the source statement

**Quantifier mapping.**

- `determine the integral solutions, and in particular the finiteness or infinitude of the integral solution set`
  maps to: one direction is frozen: `S` is infinite. The finiteness reading is a
  rejected target retained only as an outcome shape.
- `x, y, z in Z` maps to: all three coordinates range over all of `Z`, including
  zero and negative values.
- `the solution set is infinite` maps to: `forall B >= 1` there exists a
  solution of height greater than `B`, where height is `max(|x|,|y|,|z|)`.
- `the equation z^2 + y^2 z + x^3 - 2 = 0` maps to: one fixed equation with the
  constant `-2` on the left-hand side; no parameter is left free.

**Definition mapping.**

- `integral solution` — a triple of rational integers; not an `S`-integral,
  algebraic-integer, or rational point.
- `height` — `max(|x|,|y|,|z|)`; no logarithmic or projective height is used.
- `finiteness` — the cardinality of `S` is finite; the frozen target is exactly
  its negation and is not a disjunction of the two directions.
- `known small solutions` — the triples listed in assumption
  `verified_small_solutions`, each re-checked by exact substitution.
- `obvious symmetries` — only `y -> -y`; `x -> -x` and `z -> -z` do not preserve
  the equation.

**Assumption delta.**

- The source poses a determination question with two possible answers; the
  frozen target commits to infinitude, so a proof of finiteness refutes the
  frozen claim rather than answering it, and is retained under the
  negative-outcome contract.
- No bound on `x`, `y` or `z` is assumed. The bounded sweep is a search envelope
  and is not part of the statement.
- No published integral-point table for the Mordell slices `z = 1`, `z = -1` and
  `y = 0` is assumed; using one is an acquisition item.
- The direction was chosen using an exploration-only heuristic and a bounded
  sweep; neither is asserted as evidence for the claim, and the choice is
  auditable rather than justified.

**Edge-case delta.**

- `z = 0` is impossible, since it forces `x^3 = 2` and 2 is not a cube; the
  divisor characterization depends on this.
- `y -> -y` is a symmetry, so solutions are enumerated with `y >= 0`; the
  infinitude claim is unaffected.
- Solutions come in pairs sharing `(x,y)`: the two roots `z` and `z'` of the
  monic quadratic satisfy `z * z' = x^3 - 2` and `z + z' = -y^2`, and are
  rational integers together.
- `S` is nonempty, since `(1,0,1)` and `(1,0,-1)` lie in it, so no global
  congruence obstruction can exist and the local battery can only prune.
- `x = 0` is allowed and contributes `(0,1,1)` and `(0,1,-2)`; `x = 1`
  contributes the two solutions with `y = 0`.

**Strength relation:** `unresolved`. The mapping to the source statement cannot
be settled before the source is acquired: whether the source asks for a complete
determination of `S`, for finiteness, or for infinitude is unknown offline, and
the three are different targets. See section 6, claim U2.

## 5. Provenance and acquisition plan

No source has been acquired. Under ADR-0050 acquisition is human-planned,
exact-URL, and separately authorized; this section is the plan only. Every row
is `pending_acquisition`, applicability `not_assessed`.

Only the first row's locator is not invented here: it is the URL already
recorded in the planning dossier's source ledger. The remaining rows are
operator search targets and assert no DOI. ADR-0051 supplies the
identity-resolution step: one operator-initiated Crossref metadata query per
target, terms drawn as exact substrings of a supplied local context file,
results `untrusted_inspiration_candidate` only.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| FrontierMath open-problems index | `https://epoch.ai/frontiermath/open-problems` — the locator recorded in the planning dossier's source ledger | claims U1 and U2: whether this equation appears there, and the exact wording of the question asked about it | pending_acquisition |
| The individual problem statement for this equation on that index | resolve from row 1 once acquired; acquire the exact problem page | claim U2, the decisive one: whether the intended question is finiteness, infinitude, or a complete determination of `S`; also the intended solution ring | pending_acquisition |
| The source behind the "three of nine settled in 2026" report | identify from rows 1 and 2, or from the operator's own supplied notes | claim U1: the nine-equation list, the three settled, and this equation's membership among the remaining six | pending_acquisition |
| Integral-point tables for Mordell curves `Y^2 = X^3 + k` covering `k = 2`, `k = 1`, `k = -1` (Gebel, Petho and Zimmer style tables) | resolve via one ADR-0051 Crossref query per item on the exact title strings; acquire the located table pages | the three slices `y = 0`, `z = 1`, `z = -1` in section 7: their integral points are finite by Siegel, and a complete list would close those slices exactly | pending_acquisition |
| A reference on integral points of affine cubic surfaces and their fibrations | resolve via ADR-0051 Crossref query; acquire the relevant theorem statements | the finiteness direction, which is the rejected target and the section 9 outcome shape; also any known parametrization technique for such surfaces | pending_acquisition |

## 6. Prior-status claims to re-check

Each item is untrusted. None has been acquired, quoted from a primary source, or
reviewed. All are named as items the ADR-0055 pre-research novelty re-check must
cover immediately before research starts, bound to the intake file's subject
hash.

- **U1.** The planning dossier reports, from operator-supplied notes, that this
  equation is one of six remaining after three of nine were settled in 2026. The
  membership, the counts, and the date are all untrusted and unacquired.
- **U2, decisive for alignment.** The precise intended question is not
  verifiable offline: "determine all integral solutions", "decide finiteness",
  and "decide infinitude" are three different targets. The frozen target commits
  to infinitude of an exactly specified `S`, so the freeze itself is clean, but
  the mapping to the source is `unresolved` and human approval of that mapping
  is still required. Section 5 row 2 is the named acquisition target that
  settles it, and section 13 states the question verbatim.
- **U3.** The planning dossier's source-status line for A6 says the candidate
  equation and its status come from operator-supplied notes and that
  primary-source verification is pending. That instruction is inherited
  unchanged.
- **U4.** Whether the equation's integral solutions are already catalogued
  anywhere, and whether any of the small solutions listed in section 7 are
  published, is unknown. The solutions below were computed locally and are
  exact; their *novelty* is `not_assessed` and is not claimed.

## 7. Bounded first slice

**The exact structural reduction the slice is built on.** For fixed `x` put
`c = x^3 - 2`. Since 2 is not a perfect cube, `c != 0`. The equation is a monic
quadratic in `z`, so `z = 0` would force `c = 0`; hence `z != 0` and, from
`z^2 + y^2 z + c = 0`, `z` divides `c`. Writing `d = c/z`, the two roots satisfy

`z + d = -y^2` and `z * d = c`.

Therefore, for each `x` and each divisor `z` of `x^3 - 2`, the triple `(x,y,z)`
lies in `S` if and only if `-(z + (x^3-2)/z)` is a nonnegative perfect square,
and `y` is then its nonnegative square root. **So for a given `x`, the complete
solution set over all `y` and all `z` is a walk over the divisors of
`x^3 - 2`.** The sweep is therefore complete in `x`, not a box in `(x,y)`.

**Inputs and arithmetic.** Arbitrary-precision integers only. Factorization of
`x^3 - 2` by deterministic Miller-Rabin on the small-prime witness set plus
Pollard rho; divisor enumeration from the factorization; perfect-square testing
by exact integer square root. Every candidate triple is re-checked by
substituting into `z^2 + y^2 z + x^3 - 2` and confirming the value is exactly 0.
No floating-point value appears anywhere.

**Symmetry quotient.** Only `y -> -y`, so solutions are enumerated with
`y >= 0`; each such triple stands for at most two solutions. No other coordinate
sign change preserves the equation, and none is quotiented.

**What has already been run, exactly.** The sweep above was executed for
`|x| <= 30000`, complete in `x` and exhaustive in `y` and `z` for each such `x`,
with every reported triple re-checked by exact substitution. It found 57 values
of `x` carrying a solution and 116 triples with `y >= 0`. The solutions with
`|x| <= 200`, as `(x, y, z)` with `y >= 0`:

```
( 0,  1,   1)   ( 0,  1,   -2)
( 1,  0,   1)   ( 1,  0,   -1)
(-2,  3,   1)   (-2,  3,  -10)
(-7,  8,   5)   (-7,  8,  -69)
( 8,  7, -15)   ( 8,  7,  -34)
(20, 17, -31)   (20, 17, -258)
(26, 17, -87)   (26, 17, -202)
(26, 19, -58)   (26, 19, -303)
(-32, 9, 145)   (-32, 9, -226)
(-52,31, 129)   (-52,31,-1090)
(-94,221, 17)   (-94,221,-48858)
(128,59,-775)   (128,59,-2706)
(133,78,-415)   (133,78,-5669)
(161,64,-1903)  (161,64,-2193)
(-199,308, 83)  (-199,308,-94947)
```

Each row is one `(x,y)` with its two `z` roots, as `root_pairing` requires. The
count of `x`-values carrying a solution was 14, 24, 34, 46 and 57 at the cutoffs
`|x| <= 200, 1000, 3000, 10000, 30000`.

That is a bounded local computation. It determines `S` exactly inside the swept
envelope and says nothing about `S` outside it.

**An exact algebraic route already checked, and its collapse.** In
`Z[t]/(t^3 - 2)` the identity `(2t^2 + 2t - 1)^2 = 4t + 17` holds. Taking norms
and clearing denominators gives a polynomial identity over `Z`, verified here by
coefficient comparison:

`(m^2 - 17)^3 - 128 = (m^3 + 3m^2 - 21m - 71)(m^3 - 3m^2 - 21m + 71)`.

For odd `m` both cubic factors are divisible by 8 — a complete check, since each
factor modulo 8 depends only on `m` modulo 8 and there are four odd residues —
and `x = (m^2 - 17)/4` is an integer. Writing `A(m)` and `B(m)` for the factors
divided by 8, we get `x^3 - 2 = A(m) B(m)` for every odd `m`: an infinite supply
of factorizations of `x^3 - 2`, which is exactly what the divisor
characterization consumes. But the solution condition is
`A(m) + B(m) = m(m^2 - 21)/4` equal to `y^2` or `-y^2`, which is a genus-one
condition in `m`. It holds at `m = 3` and `m = 7`, recovering `(-2,3,1)`,
`(-2,3,-10)`, `(8,7,-15)` and `(8,7,-34)` — four of the smallest solutions above
— and it has finitely many solutions overall. **So the family produces
infinitely many factorizations and only finitely many points.** This is recorded
as the named trap: any new candidate family must be tested for the same collapse
before search, by computing its induced square condition and its genus.

**Local obstruction battery, exactly specified.** Reduction of the equation
modulo 8 and modulo 9, constraining the 2-adic and 3-adic structure of `z` and
`y`; reduction modulo the primes 7, 13, 31 and 43, the small primes congruent to
1 modulo 3 where cubing is not surjective so that `x^3 - 2` misses residue
classes; and 2-adic and 3-adic valuation conditions on the pair `(z, (x^3-2)/z)`
derived from `z + (x^3-2)/z = -y^2`. Because `(1,0,1) in S`, no member of this
battery can be a global obstruction. The battery prunes divisor classes for a
given `x` and refutes candidate parametric families; a battery pass is never
evidence for the target.

**The next envelope.** Extend the complete-in-`x` sweep to `|x| <= 10^6`, which
is about 2 million factorizations of integers up to `10^18` — feasible with
Pollard rho and exact integer arithmetic. Exhaustive in `x` up to the bound, and
for each `x` exhaustive in `y` and `z`. Nothing is sampled. In parallel,
generate candidate parametric families from identities in `Z[2^(1/3)]` of the
same shape as the one above, and run each through the collapse test before any
search.

**Boundary of the claim the slice can support.** A sweep complete in `x` for
`|x| <= X` establishes only that `S` is exactly the listed set inside that
envelope. It cannot establish infinitude, it cannot establish finiteness, and
its growth counts are not a trend argument for either. What it can support: a
new solution above the previous envelope, verified by substitution; the
refutation of a candidate family at a specific parameter value; and an exact
record of the frontier.

## 8. Certificate and verifier contract

| Result shape | Certificate format | Independent verifier |
|---|---|---|
| `S` is infinite | explicit integer polynomials `X(m)`, `Y(m)`, `Z(m)` in one parameter, a stated congruence class of `m` on which they take integer values, and the polynomial identity `Z^2 + Y^2 Z + X^3 - 2 = 0` in `Z[m]` | expand the identity by exact coefficient comparison in `Z[m]` and confirm every coefficient is 0; separately confirm the integrality congruence by checking the residues of the stated modulus; separately confirm the family has unbounded height by comparing leading coefficients |
| a new solution above the envelope | the triple `(x,y,z)` and, for auditability, the divisor `z` of `x^3 - 2` and the factorization used | substitute into `z^2 + y^2 z + x^3 - 2` and confirm exactly 0; confirm `z` divides `x^3 - 2` by exact division |
| a candidate family refuted | the family's polynomials, its induced square condition, and either the genus computation showing finiteness or an exact local obstruction from the frozen battery with the modulus and the excluded residues | recompute the induced condition from the polynomials; replay the modular exclusion by exhaustive residue check at the stated modulus |
| complete determination inside an envelope | the envelope bound, the full solution list, and for each `x` the factorization of `x^3 - 2` used | re-run the divisor walk for a sampled set of `x` and confirm the list matches; re-check every listed triple by substitution |
| finiteness proved (refutes the frozen target) | the full argument, with every computational step reduced to one of the certificate shapes above | human review, plus replay of every embedded exact certificate. Recorded as a refutation of this dossier's target, never as a success against it |
| unresolved | the exact envelope, the list of refuted families with their induced conditions, and the open obligations | replay of the sweep to confirm the envelope, and inspection of the refutation records |

**Refused as a certificate.** Floating-point arithmetic of any kind, including
floating-point square roots, height estimates, or numerical elliptic-curve and
lattice output. A model's assertion that a family works, that a solution exists,
or that a set is finite. A third-party program's output — including a
computer-algebra system's rank, generator, or integral-point claim — that has
not been replayed against an exact check. The failure of a sweep to find further
solutions. A growth count presented as a trend argument for infinitude or
finiteness.

## 9. Useful negative outcomes

- **The refuted-family ledger.** Every candidate family, its induced square
  condition, and the exact reason it collapses. The
  `rational_factorization_family` entry above is the first record: it is a
  genuine infinite factorization family with a genus-one point condition, and
  the structural reason for the collapse — fixing the factorization by
  polynomial identities always forces `A + B = plus or minus a square` — is the
  reusable fact. Any future attempt that starts from a polynomial factorization
  inherits this obstruction.
- **The exclusion set.** The divisor classes and residue classes excluded by the
  frozen local battery, with their moduli. Permanent exact facts, reusable by
  any later attempt regardless of which direction turns out to be true.
- **The frontier.** The exact envelope in which `S` is completely determined,
  with the solution list and the per-`x` factorizations, so the next slice
  resumes from a recorded position rather than re-sweeping.
- **A finiteness proof.** If produced, it refutes the frozen target. It is
  retained at full value as a mathematical result and recorded as a refutation
  of this dossier's claim; the dossier then retires rather than being rewritten
  to claim the other direction.
- **The Mordell reductions.** The three slices `y = 0`, `z = 1`, `z = -1` reduce
  to `z^2 = 2 - x^3`, `y^2 = 1 - x^3`, `y^2 = x^3 - 1`. Each has finitely many
  integral points by Siegel's theorem, so no infinite family lives inside them.
  That is a permanent reduction: it tells any infinitude attempt where *not* to
  look, and it stands whether or not the integral-point tables in section 5 are
  ever acquired.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. `version` 1, `phase`
`exploratory`.

Metrics: `solutions_exactly_verified`, `x_values_swept`,
`divisor_classes_pruned`, `candidate_families_refuted`,
`local_obstruction_checks_run`, `failed_routes_preserved`, `model_cost_usd`.

Success criteria:

- an exhibited parametric family given by explicit integer polynomials in one
  parameter, together with a polynomial identity over `Z` verified by
  coefficient comparison, establishing that `S` is infinite
- an exhibited solution of height above the previously swept envelope, verified
  by exact substitution, together with the exact envelope in which `S` is now
  completely determined
- or an explicit unresolved outcome recording the smallest remaining obligation,
  namely the exact list of candidate families refuted with their induced square
  conditions and the exact envelope in which `S` is completely determined

Stopping rules:

- stop when a parametric family is verified by an exact polynomial identity over
  `Z` and its square condition is shown to have infinitely many integer
  solutions
- stop when a proof of finiteness is produced: it refutes the frozen target and
  is recorded as a refutation, never reported as a success against this claim
- stop when the fresh model spend reaches USD 20
- stop when no candidate family has been refuted and no new solution has been
  certified for two consecutive review points
- never promote a complete sweep over a bounded range of `x` into finiteness or
  into infinitude: exhaustion of the envelope determines `S` only inside that
  envelope

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| The frozen direction is the false one | If `S` is finite, the target is unprovable and every hour spent on families is spent on a nonexistent object | The choice is justified and auditable in section 1, the heuristic is labelled exploration-only, and the finiteness outcome is a first-class recorded result under section 9 rather than a failure to hide |
| Growth counts read as evidence | 14, 24, 34, 46, 57 looks like a trend and is not one | `finite_search_not_a_determination` and `infinitude_heuristic_exploration_only` both forbid it; the last stopping rule forbids promotion in either direction |
| The source asks a different question | Finiteness, infinitude, and complete determination are three targets; alignment to the wrong one wastes the whole slice | `strength_relation` is `unresolved`, U2 is named as decisive, section 5 row 2 is the acquisition target, and section 13 states the question verbatim |
| Repeating the collapsed family route | The polynomial-factorization idea is natural, looks promising, and provably cannot work as stated | `family_route_trap` records the structural reason and mandates the collapse test on every new family before search |
| Trusting a computer-algebra integral-point claim | A CAS rank or generator claim on the Mordell slices would silently enter the trust path | Section 8 refuses unreplayed third-party output; the Mordell tables are acquisition items, and local re-derivation is a capability item in section 12 |
| Floating point in square testing or height comparison | The obvious implementation of "is this a square" uses a floating square root and is wrong at large size | `exact_arithmetic_requirement` mandates exact integer square root and exact substitution re-checks; the executed sweep already works this way |
| Factorization cost at the next envelope | The `|x| <= 10^6` envelope needs about 2 million factorizations of integers near `10^18`; a naive method makes the envelope meaningless | Pollard rho with deterministic Miller-Rabin, all exact; the envelope, its cost, and the frontier are recorded so an extension is a decision rather than a drift |
| Missing the second root | Reporting one `z` and not its partner makes the solution list silently incomplete and breaks the completeness claim | `root_pairing` requires both roots; the section 7 listing is arranged in pairs so an omission is visible |

## 12. Capability check

**Covered by existing AdaIvy capabilities.**

- Declarative intake with the trust boundary intact: the intake file validates
  against `schemas/problem-definition-v1.schema.json` and yields
  `logical_status unknown`, novelty and significance `not_assessed`, zero
  warrants.
- Exact arbitrary-precision integer arithmetic, deterministic Miller-Rabin,
  Pollard rho, divisor enumeration, exact integer square roots, and polynomial
  coefficient comparison over `Z` — all project-authored standard-library work
  under `src/`, with deterministic serialization, content hashes, and captured
  output. The sweep reported in section 7 is exactly this.
- Machine-readable preservation of failed routes, which the refuted-family
  ledger in section 9 depends on.
- ADR-0055 pre-research novelty re-check, required by section 6.
- ADR-0051 one-shot Crossref metadata query for the identity-resolution step in
  section 5, inspiration-only.
- ADR-0036 publication projection if any result is rendered: an exact polynomial
  identity without a kernel-checked attestation reaches `Proposition` at best,
  and the unacquired source statement renders as an OPEN OBLIGATION rather than
  a citation.

**Would require a new ADR.**

- A computer-algebra or arithmetic-geometry library — elliptic-curve rank and
  generator computation, Mordell-curve integral points, Groebner bases, descent,
  or lattice reduction. This is the one capability the finiteness direction
  would need, and it is exactly why that direction is not the frozen target.
  Pinning, licensing, and gating such a dependency is a separate decision.
- Effective methods on integral points of affine cubic surfaces implemented
  locally. Not available and not assumed.
- Acquisition of any section 5 source, which is ADR-0050 territory and needs
  per-URL human planning and separate authorization.
- Execution of model-generated code, which stays disabled under ADR-0057 until
  its digest-pinned OCI sandbox gate passes. Every program here is
  project-authored and reviewed.
- A job class long enough for envelopes materially beyond `|x| <= 10^6`, if the
  bounded-subprocess convention would be exceeded.

**Explicitly not activated.** Parallel specialists, evolutionary search, higher
search tiers, crawling, result following, and automated novelty or significance
assessment.

## 13. Open questions before intake

1. **The decisive one.** What exactly does the original source ask about
   `z^2 + y^2 z + x^3 - 2 = 0`: to determine all integral solutions, to decide
   whether the integral solution set is finite, or to decide whether it is
   infinite? This is U2. The freeze does not depend on the answer, but the
   semantic alignment does, and `strength_relation` stays `unresolved` until it
   is answered from the acquired source.
2. Does the operator accept infinitude as the frozen direction, on the
   justification in section 1? Freezing finiteness instead would need a new
   intake file, a different certificate contract, and the arithmetic-geometry
   capability that section 12 lists as requiring a new ADR.
3. Is the solution ring `Z` in the source, or a ring of integers, or the
   rationals? The frozen reading is rational integers.
4. Is `|x| <= 10^6` the right next envelope, or should the first run stay at the
   already-swept `|x| <= 30000` and spend its budget on candidate families
   instead?
5. Should the Mordell-table acquisition (section 5 row 4) be planned at all, or
   should the three slices `y = 0`, `z = 1`, `z = -1` be left as recorded
   reductions with Siegel finiteness and no complete list?
