# B9. Imaginary quadratic 3-rank at least nine — scoped research dossier

**Compiled:** 22 August 2026
**Planning source:** RESEARCH_TARGET_DOSSIER_2026-08.md, item B9 (tier B)
**Declared domain:** algebraic-number-theory
**Intake file:** docs/research-targets/intake/b9-imaginary-quadratic-3-rank-v1.json
**Frozen in one line:** Exhibit one squarefree integer `d > 0` such that the
class group of the maximal order of `K = Q(sqrt(-d))` has `3`-rank at least `9`.

This is a scoped intake package and nothing more. It does not approve a
formalization, establish any record or open status, authorize source
acquisition, assess novelty or significance, create mathematical warrant, or
activate any capability. Novelty, significance, and source applicability are
`not_assessed`. In particular this dossier makes no claim that `3`-rank `9`
exceeds the published record; the reported record of `8` is an untrusted
planning-note statement recorded in section 6.

## 1. Frozen target

Let `d` be a squarefree integer with `d > 0` and let `K = Q(sqrt(-d))`, an
imaginary quadratic field with defining polynomial `x^2 + d`, irreducible over
`Q` for every such `d`. Let

`D = -d` if `d` is congruent to `3` modulo `4`, and `D = -4d` otherwise,

the fundamental discriminant of `K`, that is the discriminant of the maximal
order `O_K`. Let `Cl(K)` be the ideal class group of `O_K`: nonzero fractional
`O_K`-ideals modulo nonzero principal fractional `O_K`-ideals. Define the
`3`-rank

`r_3(K) = dim over F_3 of Cl(K)/Cl(K)^3`.

**Frozen claim.** There exists a squarefree integer `d > 0` with

`r_3(K) >= 9`,

exhibited together with an exact unconditional certificate of that lower bound.

The prime is frozen at `ell = 3`. The target rank is frozen at `9`. A field with
`r_3 > 9` also satisfies the target. `problem_type` is `compute` and
`target_claim.scope` is `existential`: the direction is fixed, the deliverable
is one explicit object plus its certificate, and a nonexistence outcome is not
an acceptable result shape for this slice.

### Why `ell = 3` and why rank `9`

The planning dossier leaves both the prime and the target rank open, which is a
disjunction over parameter pairs rather than a target. `ell = 3` is chosen
because it is the only prime for which the planning notes report a concrete
record, and because it is the prime with an exact, unconditional, purely
integral verification route (section 8). Rank `9` is chosen as one above the
reported record of `8`: it is the smallest target that would exceed that record
*if the report is correct*, and if the true published record is lower — `6` or
`7`, say — then `9` remains beyond it. The choice is deliberately calibrated
against an untrusted number, so the calibration itself is one of the things the
ADR-0055 pre-research re-check must settle. If the re-check finds a published
field with `r_3 >= 9`, the frozen target is already attained in the literature
and this dossier must be revised before any work starts rather than after.

### The equivalent counting form

The `3`-rank is not directly observable. The frozen target is therefore worked
through its counting equivalent. By the cubic-field correspondence in the form
due to Hasse, for a fundamental discriminant `D` the number of isomorphism
classes of cubic number fields whose field discriminant equals exactly `D` is
`(3^r - 1)/2` where `r = r_3(Q(sqrt(D)))`. Since `(3^r - 1)/2` is strictly
increasing in `r`,

`r_3 >= 9` if and only if there are at least `(3^9 - 1)/2 = 9841` pairwise
non-isomorphic cubic number fields of discriminant exactly `D`.

Exhibiting `9841` such fields, each certified by an exact integral binary cubic
form, is therefore an unconditional lower-bound certificate. Exhibiting `N`
such fields certifies `r_3 >= r` for the largest `r` with `(3^r - 1)/2 <= N`.
The load-bearing hypotheses of the correspondence — `D` fundamental, cubic
discriminant exactly `D` rather than `D` times a square, and the count taken
over isomorphism classes — are named in section 2 and are an acquisition target
in section 5.

## 2. Definitions and conventions

| Term | Frozen meaning | Rejected reading |
|---|---|---|
| the field | `K = Q(sqrt(-d))`, `d` squarefree, `d > 0`, defining polynomial `x^2 + d` | non-squarefree radicand; real quadratic; a relative extension; a field given only by a discriminant with no generator |
| discriminant | fundamental discriminant `D = -d` for `d = 3 mod 4`, else `D = -4d` | the radicand `-d` itself; the discriminant of a non-maximal order; a form discriminant `D f^2` with `f > 1` |
| class group | `Cl(K) = Cl(O_K)`, fractional ideals modulo principal fractional ideals | class group of a non-maximal order; ray class group; relative class group; S-class group; the form class group of a non-fundamental discriminant |
| narrow versus wide | they coincide, because `K` has no real embedding | treating the narrow class group as a possibly larger object here |
| `ell`-rank | `dim over F_3 of Cl(K)/Cl(K)^3` | the `3`-adic valuation of the class number; the order of the `3`-Sylow subgroup; the exponent of the `3`-part; the number of `3`-torsion elements |
| `ell` | frozen at `3` | any other prime; a range of primes |
| target rank | frozen at `9`; larger also qualifies | `8`; "beat the record"; an unspecified improvement |
| cubic field count | isomorphism classes of cubic number fields with field discriminant exactly `D` | GL_2(Z)-classes of forms without a maximality test; forms up to sign; cubic orders; cubic fields with discriminant `D` times a square |
| lower-bound certificate | unconditional: an explicit list of pairwise non-isomorphic cubic fields | a class-group computation whose completeness rests on GRH; the `F_3` rank of an arbitrary relation matrix |
| relation-matrix rank | an **upper** bound on `r_3`, absent proofs of generation and relation completeness | the `3`-rank itself |
| conditional result | any rank whose derivation uses GRH, labelled conditional in every record | a conditional rank merged silently with unconditional data |
| arithmetic | exact integers throughout | floating-point `L`-function values, analytic class number formula, Minkowski or Bach bounds evaluated numerically, floating-point lattice reduction |

## 3. Formalization and quantifiers

Statement, as carried in the intake file:

```
exists d in Z with d > 0 and d squarefree such that, with K = Q(sqrt(-d)),
D = -d if d = 3 mod 4 else D = -4d, O_K the maximal order of K,
Cl(K) = I(O_K)/P(O_K), and r_3(K) = dim_{F_3}(Cl(K)/Cl(K)^3),
we have r_3(K) >= 9; equivalently, by the cubic-field correspondence for the
fundamental discriminant D, there exist at least (3^9 - 1)/2 = 9841 pairwise
non-isomorphic cubic number fields whose field discriminant equals exactly D
```

Quantifiers, explicitly:

- `exists d` an integer with `d > 0` and `d` squarefree.
- `forall` primes `p`, the maximality test for a candidate cubic order at `p` is
  decided exactly.
- `forall` pairs of exhibited cubic fields, non-isomorphism is decided exactly
  by canonical reduced form comparison.
- `ell` is fixed to `3` and the target rank is fixed to `9`, with no
  quantification over either.

Formal language `typed_informal_math`, version 1, approval status `proposed`.
Human approval of the semantic alignment is required and has not been given.

## 4. Semantic alignment to the source statement

The source statement is the planning dossier's rendering, itself an untrusted
planning artifact; no primary source has been acquired.

**Quantifier mapping.**

| Source | Local |
|---|---|
| for a fixed prime `ell` and a frozen target rank | `ell = 3` and target rank `9`, both constants with no quantifier |
| construct an imaginary quadratic field | there exists a squarefree `d > 0` giving `K = Q(sqrt(-d))` |
| whose ideal class group has `ell`-rank at least that target | `r_3(K) = dim over F_3 of Cl(K)/Cl(K)^3` satisfies `r_3(K) >= 9` |
| certified rank lower bound | an unconditional exact certificate, by default `9841` pairwise non-isomorphic cubic fields of discriminant exactly `D` |

**Definition mapping.**

| Source term | Local meaning |
|---|---|
| `ell`-rank | `F_3`-dimension of `Cl(K)/Cl(K)^3`, equal to the number of invariant factors divisible by `3` |
| ideal class group | class group of the maximal order `O_K` |
| imaginary quadratic field | `K = Q(sqrt(-d))`, `d` squarefree, `d > 0`, defining polynomial `x^2 + d` |
| discriminant | fundamental discriminant `D = -d` for `d = 3 mod 4`, else `D = -4d` |
| class-group relation data | a relation matrix retained in the certificate whose `F_3` rank bounds `r_3` from above only |
| independently replayed rank certificate | a separate verifier recomputing every form discriminant, maximality test, canonical reduction, and `F_3` rank from stored exact integers |

**Assumption delta.**

- The planning statement quantifies over a fixed prime and a frozen target rank
  without naming either; this dossier fixes `(ell, rank) = (3, 9)` and claims
  nothing for any other pair.
- The planning verification shape names a class-group relation matrix; this
  dossier keeps it but demotes it to an *upper* bound on the rank absent proofs
  of generation and relation completeness, and promotes the cubic-field
  correspondence to the unconditional lower-bound path.
- GRH-conditional class-group computation is admitted only as exploration
  guidance, never as the certificate; a conditional rank is labelled
  conditional.
- No algebraic-number-theory computer-algebra dependency is assumed, pinned, or
  licensed by this dossier; the bounded first slice is restricted to exact
  standard-library integer arithmetic.
- No novelty, record, or significance claim is made; whether rank `9` exceeds
  the published record is `not_assessed`.

**Edge-case delta.**

- `d = 1` and `d = 2` give `D = -4` and `D = -8` with trivial class group and
  `r_3 = 0`; they are in scope and simply fail the target.
- `d = 3 mod 4` gives odd `D = -d`; every other squarefree `d` gives
  `D = -4d`. The parity of `D` is determined by `d` and must not be chosen
  independently.
- `d = 3` gives `D = -3`, whose class group is trivial and whose field has extra
  roots of unity; the correspondence's hypotheses must be re-read for this
  discriminant rather than assumed.
- A cubic field of discriminant `D` times a nonunit square is not counted; only
  field discriminant exactly `D` counts.
- A reducible integral binary cubic form defines no cubic field and must be
  discarded by an exact irreducibility test before any count.
- Two `GL_2(Z)`-equivalent forms define the same field and must be counted
  once, so the count is over canonical reduced representatives.
- For imaginary quadratic `K` the narrow and wide class groups coincide, so no
  rank differs between those two readings.

**Strength relation:** `weaker`. The frozen target is one parameter pair drawn
from the planning statement's family, so it is a strict special case. It is not
`equivalent`, and cannot be, because no primary source has been acquired.

## 5. Provenance and acquisition plan

No source is acquired by this dossier. Every row is a target an operator would
acquire under ADR-0050 as a human-planned, exact-URL, separately authorized
public fetch. Volume, page, and DOI fields are left to be resolved from the
publisher record at acquisition time and are **not asserted here**.

| Source | Exact locator | Needed for | Status |
|---|---|---|---|
| Hasse's cubic-field correspondence in its precise published form | primary record for Hasse's result relating the count of cubic fields of discriminant `D` to the `3`-rank of `Cl(Q(sqrt(D)))`; identifier to be resolved by the operator, not guessed here | settles the exact hypotheses of the counting criterion, which is the whole unconditional trust path — section 6 row 1 | pending_acquisition, applicability not_assessed |
| A standard computational algebraic number theory text covering the Delone-Faddeev correspondence and cubic form reduction (Cohen) | book record by author, title, series; identifier to be resolved | settles the reduction theory for binary cubic forms of negative discriminant and the maximality criterion — section 6 row 2 | pending_acquisition, applicability not_assessed |
| Davenport and Heilbronn on densities of discriminants of cubic fields | article records by authors, titles, journal; identifiers to be resolved | settles the maximality condition at each prime and the class-count densities used to size the enumeration box | pending_acquisition, applicability not_assessed |
| Belabas on fast enumeration of cubic fields | article record by author, title, journal; identifier to be resolved | settles whether a coefficient-box enumeration can be replaced by a complete reduced-form enumeration within the same budget — section 7 | pending_acquisition, applicability not_assessed |
| Quer, and Diaz y Diaz, on quadratic fields of large `3`-rank | article records by author, title, venue; identifiers to be resolved | settles the reported record of `8`, the true current record, and the parametrized families used to reach large ranks — section 6 rows 3 and 4 | pending_acquisition, applicability not_assessed |
| Scholz reflection and its exact hypotheses | primary or textbook record to be resolved | settles whether the real quadratic side gives a cheaper search route, and whether any reflection bound caps what the frozen target can reach | pending_acquisition, applicability not_assessed |

Under ADR-0051 an operator may run one Crossref metadata query whose terms are
exact-normalized substrings of a supplied local context file. Its results are
inspiration-only, acquire nothing, and do not satisfy the ADR-0055 re-check.

## 6. Prior-status claims to re-check

Each is **untrusted**. None is acquired, quoted, or verified. Each is named as a
claim the ADR-0055 pre-research novelty re-check must cover before any research
starts.

1. **Untrusted:** the cubic-field correspondence in the form used in section 1,
   namely that the number of isomorphism classes of cubic fields of
   discriminant exactly `D` is `(3^r - 1)/2` for fundamental `D`. This dossier
   uses it as a standard textbook fact, and it is exactly the kind of statement
   whose hypotheses shift between renderings. It must be checked against a
   primary source before it closes a certificate. The formula fails for
   non-fundamental discriminants.
2. **Untrusted:** that a squarefree form discriminant implies the associated
   cubic order is maximal and the field discriminant equals the form
   discriminant, and that squarefree negative field discriminants are congruent
   to `1` modulo `4`. Both are used in section 7 as safe filters and both need
   source confirmation.
3. **Untrusted:** the planning dossier's report, from operator notes, of a
   record `3`-rank of `8` for imaginary quadratic class groups. If the true
   record is lower, the frozen target of `9` is unchanged. If it is `9` or
   higher, the frozen target is already attained and this dossier must be
   revised.
4. **Untrusted:** that the planning notes list multiple unachieved prime and
   target-rank pairs, and which they are. This dossier freezes exactly `(3, 9)`.
5. **Untrusted:** the planning dossier's statement that serious
   algebraic-number-theory tooling is required. Treated here as a hard scope
   constraint rather than a fact: no such dependency is pinned or assumed.
6. **Untrusted:** any recollection about which discriminant is the smallest with
   `3`-rank `2` or `3`. No such value is asserted anywhere in this dossier; the
   maximum rank reached inside the enumeration box is a measured output, never
   a prediction.

## 7. Bounded first slice

**Purpose.** The first slice does not attempt rank `9`. It builds and validates
the unconditional verifier, then measures how far a bounded, dependency-free
enumeration reaches. That distance is the deliverable.

**Inputs.** No external input. All objects are generated.

**The safe core: squarefree form discriminants.** An integral binary cubic form
`F(x,y) = a x^3 + b x^2 y + c x y^2 + d_0 y^3` has discriminant

`disc(F) = b^2 c^2 - 4 a c^3 - 4 b^3 d_0 + 18 a b c d_0 - 27 a^2 d_0^2`,

an exact integer. The slice keeps only forms with `disc(F) < 0` and `disc(F)`
**squarefree**. Under that filter the associated cubic order is maximal, so the
field discriminant equals `disc(F)`, and a squarefree negative field
discriminant is automatically a fundamental discriminant congruent to `1`
modulo `4`. This removes the entire prime-by-prime maximality computation from
the trust path in exchange for coverage, which is the safe trade: see the
asymmetry below.

**Envelope E1 — coefficient box.** Enumerate all forms with `a` in
`{1, ..., 30}` and `b, c, d_0` in `{-30, ..., 30}`. That is
`30 * 61^3 = 6806730` forms, each requiring one exact discriminant evaluation.
Coefficients bounded by `30` admit `|disc(F)|` up to roughly `2.2 x 10^7`, so
squarefreeness is decided by a precomputed squarefree sieve to `2.5 x 10^7`,
built by striking multiples of `p^2`. For each surviving form: an exact
irreducibility test over `Q` by rational-root exhaustion on the divisors of the
leading and trailing coefficients; then canonical reduction; then bucketing by
`disc(F)`.

**Canonical reduction.** For `disc(F) < 0` the Hessian

`H_F(x,y) = (b^2 - 3 a c) x^2 + (b c - 9 a d_0) x y + (c^2 - 3 b d_0) y^2`

is positive definite. The slice reduces `H_F` by the classical integral
algorithm, applies the same `GL_2(Z)` transformation to `F`, and applies a fixed
total order as a tie-break, yielding one canonical representative per
`GL_2(Z)`-class. All arithmetic is exact integer. Two forms passing the
squarefree filter define isomorphic cubic fields if and only if they are
`GL_2(Z)`-equivalent, so equality of canonical forms decides non-isomorphism.

**Canonical-form probe.** The reduction routine is probed, not trusted: a fixed
deterministic list of `GL_2(Z)` generator words is applied to each of a fixed
set of forms and the canonical form must be invariant under every word. No
random number generator is used, so the probe is byte-reproducible. A canonical
form that cannot be made to fail proves nothing, so the probe list also
includes a deliberately mutated reducer that must be detected.

**Rank derivation.** For each discriminant bucket with `N` canonical classes,
the certified lower bound is the largest `r` with `(3^r - 1)/2 <= N`. The run
records, per bucket, `D`, `N`, `r`, and the full list of canonical forms.

**Envelope E2 — targeted deepening.** For the buckets with the largest `N`, the
coefficient box is extended along the coefficients that produced those forms.
This is declared non-exhaustive. Its only possible effect is to raise `N` for
those discriminants, which is the safe direction.

**The asymmetry that makes this sound.** Under-counting cannot invalidate a
certified bound: exhibiting fewer cubic fields than exist yields a smaller `r`,
never a wrong one. Over-counting *can* inflate `r` and is the only real danger.
The trust burden therefore sits entirely on three checks — irreducibility,
maximality (here discharged by the squarefree filter), and non-isomorphism —
and not on the completeness of the enumeration. This is why an incomplete
coefficient box is an acceptable design and why the maximality shortcut is a
restriction rather than a risk.

**The relation-matrix route, retained and demoted.** For a candidate `D` the
slice may also build a relation matrix from reduced binary quadratic forms of
discriminant `D` under exact Gauss composition, and compute the rank of that
matrix over `F_3` by exact Gaussian elimination, independently replayed. Its
entailment is stated precisely and narrowly: the found relations are genuine, so
the computed quotient surjects onto no more than what the chosen ideals
generate, and absent a *proof* that those ideals generate `Cl(K)` and that the
found relations span the whole relation lattice, the `F_3` rank of that
computation bounds `r_3(K)` from **above** only. It is never a lower-bound
certificate. When an unconditional lower bound from the cubic-field count and an
upper bound from the relation matrix coincide, `r_3` is pinned exactly — but
only as strongly as the weaker of the two, so if the upper bound rests on a
GRH-derived generating bound the pinning is conditional and is labelled
conditional everywhere it appears.

**Exhaustive versus sampled.** E1 is exhaustive over its coefficient box. E2 is
declared non-exhaustive. Nothing is sampled and no random number generator is
used anywhere in the slice. There is no floating-point value on any trust path.

**Boundary of the claim the slice can support.** Every certified `r` is an
unconditional lower bound for its own `D` and nothing more. The slice cannot
support any statement of the form "the maximum `3`-rank for `|D| <= X` is `r`",
because that needs completeness of the enumeration, which the coefficient box
does not provide. It cannot support any record or novelty claim. The honest
expectation, itself untrusted, is that a box of this size reaches a small
`3`-rank — well under `9` — because the fields with large `3`-rank reported in
the literature have very large discriminants. The gap between what the box
reaches and `9` is the quantity the slice measures and reports.

## 8. Certificate and verifier contract

**Result shape 1: a field with `r_3 >= 9`.** Certificate: the squarefree
integer `d`, the fundamental discriminant `D`, the defining polynomial
`x^2 + d`, and a list of at least `9841` integral binary cubic forms, each with
its coefficients, its exact discriminant equal to `D`, its irreducibility
witness, and its canonical reduced representative; plus a content hash over the
canonical serialization of the whole list. Independent verifier: a separate
program that reads only the coefficient list, recomputes every discriminant,
re-verifies squarefreeness of `D`, re-verifies irreducibility, recomputes every
canonical reduction, asserts that all canonical forms are pairwise distinct,
recomputes the count, re-derives `r` from `(3^r - 1)/2 <= N`, and recomputes the
hash. Nothing in this path uses GRH and nothing uses floating point.

**Result shape 2: a certified frontier bound below `9`.** Certificate: the same
structure with `N < 9841`, the derived `r`, and the envelope definition.
Recorded as a bounded observation, with no record, novelty, or significance
claim attached and with the entailment sentence from section 7 stored alongside
it.

**Result shape 3: a relation-matrix upper bound.** Certificate: the
discriminant, the generating ideals as reduced quadratic forms, the relation
matrix, the `F_3` rank with the elimination transcript, and a statement of which
generation and completeness hypotheses were proved and which were assumed. If
any hypothesis rests on GRH, the record is labelled `conditional` and the label
propagates to every report that mentions it. An unlabelled conditional rank is
a defect, not an oversight.

**Result shape 4: a validated verifier with an unresolved target.**
Certificate: the replayable verifier, the canonical-form probe results including
the deliberately mutated reducer that must be caught, and an explicit statement
of which hypotheses of the cubic-field correspondence remain unacquired.

**Refused as a certificate, in all four shapes:** any floating-point value,
including numerical `L`-function evaluation, the analytic class number formula,
numerically evaluated Minkowski or Bach bounds, and floating-point lattice
reduction; a GRH-conditional class-group computation offered as an
unconditional rank; the output of an unreplayed third-party computer algebra
system; a model's assertion; the failure of a search; and any count of forms
that has not passed the irreducibility, maximality, and non-isomorphism checks.

## 9. Useful negative outcomes

- **The replayable unconditional verifier.** Independent of whether any field is
  found, a verifier that turns a list of cubic forms into a certified `3`-rank
  lower bound is retained, probed, and hashed. It is reusable for any candidate
  `D` from any source, including a candidate an operator supplies by hand.
- **The frontier table.** Every discriminant bucket with its certified `r`,
  hashed, so a later run extends the table instead of rebuilding it.
- **The measured gap.** The distance between the best certified `r` in the box
  and the frozen target `9`, together with the coefficient-box size that
  produced it. This is the concrete input to any decision about whether the
  target needs a parametrized family or a pinned computer algebra dependency.
- **The maximality-shortcut cost.** How many forms the squarefree filter
  discarded. If that fraction is large, implementing the exact prime-by-prime
  maximality criterion becomes the highest-value next step, and the number
  rather than an opinion decides it.
- **Refuted routes.** Any construction attempted and found to have a gap is
  preserved with the gap named — in particular any attempt to read a lower
  bound off a relation matrix, which section 8 refuses.

## 10. Evaluation protocol

Mirrors `evaluation_protocol` in the intake file exactly. Version 1, phase
`exploratory`.

Metrics:

- `cubic_forms_enumerated`
- `reducible_forms_discarded`
- `non_maximal_orders_discarded`
- `canonical_reduced_classes_retained`
- `discriminant_buckets_populated`
- `three_rank_lower_bounds_certified`
- `certificates_independently_replayed`
- `conditional_results_labelled_conditional`
- `failed_routes_preserved`
- `model_cost_usd`

Success criteria:

- one squarefree d > 0 with an unconditional exact certificate that r_3(K) >= 9,
  replayed end to end by an independent verifier from stored exact integers
- an unconditional exact certificate of the largest 3-rank attained inside the
  frozen enumeration box, recorded as a bounded frontier observation with no
  record, novelty, or significance claim attached
- a replayable exact verifier for the cubic-field lower-bound criterion,
  together with a labelled statement of exactly which hypotheses of the
  cubic-field correspondence remain unacquired
- or an explicit unresolved outcome that records the smallest remaining
  obligation

Stopping rules:

- stop on an exact unconditional certificate that r_3(K) >= 9 for one exhibited
  d
- stop when fresh model spend for this target reaches USD 20
- stop when no proof obligation has been discharged and no new certified
  frontier bound recorded for two consecutive review points
- never promote exhaustion of the frozen enumeration box into a statement about
  discriminants outside the box, and never promote a bounded frontier
  observation into a record or novelty claim
- refuse any GRH-conditional or floating-point-derived rank as an unconditional
  certificate and stop rather than relabel it

## 11. Risk register

| Risk | Why it bites | Mitigation |
|---|---|---|
| Relation-matrix rank read as a lower bound. | It is the natural thing to compute and the natural thing to report, and it is an upper bound absent proved generation and relation completeness. Reporting it as the `3`-rank would manufacture a result out of an incomplete computation. | Recorded as a known trap in the intake file; section 8 result shape 3 requires the hypothesis status to be enumerated in the certificate; the unconditional path is the cubic-field count, which does not use the matrix at all. |
| GRH-conditional rank silently accepted. | Standard class-group algorithms rest on a GRH-derived bound for the generating set. Their output looks unconditional. | Any GRH-dependent rank is labelled `conditional` in every record and report, admissible only as exploration guidance; a stopping rule forbids relabelling it. |
| Over-counting cubic fields. | Counting `GL_2(Z)`-orbits without a maximality test, or counting forms rather than classes, inflates `N` and therefore inflates the certified rank. This is the one error direction that produces a wrong result rather than a weak one. | Squarefree-discriminant filter discharges maximality exactly; canonical reduction plus pairwise-distinctness assertion discharges isomorphism; the canonical-form routine carries a probe including a deliberately mutated reducer that must be caught. |
| Wrong reduction theory. | A canonical form that merges two inequivalent classes deflates `N` (safe) but one that splits a class inflates `N` (unsafe). | The probe applies fixed `GL_2(Z)` generator words and asserts invariance, catching the unsafe direction directly. |
| Target rank calibrated against an untrusted number. | If the reported record of `8` is wrong in either direction the target is either unambitious or already attained. | Recorded as an untrusted source report; the ADR-0055 re-check must settle it before work starts; the dossier states that a re-check finding rank `9` in the literature requires revising this dossier rather than proceeding. |
| Target is out of reach without new tooling. | Fields of large `3`-rank have very large discriminants; a stdlib coefficient box will not find one. | The slice's stated deliverable is the verifier plus the measured gap, not the field; section 12 states plainly that pinning a computer algebra dependency is a new ADR. |
| Correspondence hypotheses shift. | The counting formula fails for non-fundamental discriminants and its exact form varies between renderings; using the wrong version would break the whole trust path. | Frozen conventions in section 2, acquisition row 1 in section 5, and the squarefree filter, which forces fundamentality rather than assuming it. |
| Floating point entering the trust path. | Analytic class number formulas and lattice reduction are the natural tools and both are floating point in practice. | Repo-owner rule: floating-point solvers are rejected outright. All arithmetic is exact integer; numerical routes are exploration-only and labelled; the certificate contract refuses them. |
| Bounded enumeration promoted to a completeness statement. | "The maximum `3`-rank for `\|D\| <= X`" is a different and unsupported claim. | Section 7 states the entailment explicitly; the frontier record stores that sentence alongside the numbers; a stopping rule forbids the promotion. |

## 12. Capability check

**Covered by existing AdaIvy capabilities.**

- Phase 1 declarative problem intake and trust policy; the intake file validates
  and creates no warrant, novelty, or significance.
- Exact integer arithmetic with the Python standard library. Discriminants,
  Hessians, form reduction, squarefree sieving, rational-root irreducibility
  tests, Gauss composition of quadratic forms, and Gaussian elimination over
  `F_3` are all integer computations, so nothing here needs a third-party
  numeric package. This matches the engineering rule preferring the standard
  library for the harness.
- Deterministic serialization, explicit schema versions, and content hashing for
  form lists, frontier tables, and certificates.
- Bounded subprocess execution with captured stdout and stderr, no network, for
  the enumerator and the independent verifier.
- Machine-readable preservation of failed attempts, discarded forms, and
  unresolved outcomes, as required for section 9.
- ADR-0047 bounded central-lead runtime if a model proposes routes, inside
  content-hashed session bounds with a proposer-only ledger and model-free
  replay. It discharges no obligation and produces no warrant.
- ADR-0055 pre-research novelty re-check, mandatory before work starts, and
  load-bearing here because the target rank is calibrated against an untrusted
  reported record.
- ADR-0036 publication projection if a report is rendered. An exact
  unconditional certificate reaches `Proposition`; a GRH-conditional rank does
  not and must render with its conditional label intact.

**Would require a new ADR and is not activated by this dossier.**

- **Any algebraic-number-theory computer algebra dependency.** PARI/GP, Sage,
  Magma, FLINT, and any binding to them are not available and are not activated
  here. Adding one requires a new ADR that pins the exact version and digest,
  records the license, defines the sandbox and gate for running it, and states
  how its output is replayed rather than trusted — it is a separate decision
  and this dossier does not make it. The planning dossier's note that serious
  tooling is required is precisely why this is stated plainly rather than left
  implicit.
- Any source acquisition. ADR-0050 permits only public, unauthenticated,
  human-planned, exact-URL fetches, separately authorized. Section 5 is a plan.
- Any Lean formalization of this target. The sealed Phase 3B scope is one
  frozen theorem with a supplied proof fragment; a new frozen statement with
  its imports and meaning tests is a separate decision.
- Any parallel, specialist, evolutionary, or higher search tier; ADR-0029
  requires a recorded prediction and measured retention gain first.
- Any automated novelty or significance assessment.

## 13. Open questions before intake

1. Does the operator accept `9` as the frozen target rank given that it is
   calibrated against an untrusted reported record of `8`, or should the target
   be set from the re-check result instead, which would mean deferring intake
   until the re-check has run?
2. Should the first slice instead freeze a smaller target rank — `4` or `5` —
   so that a positive outcome is reachable without new tooling, keeping `9` as
   a later dossier?
3. Is the squarefree-discriminant restriction acceptable for the first slice,
   or should the exact prime-by-prime maximality criterion be implemented
   before any enumeration runs?
4. Should the relation-matrix route be built at all in the first slice, given
   that it can only produce an upper bound and carries the dossier's main
   mislabelling risk?
5. Does the operator intend to open the computer algebra dependency question as
   its own ADR? If so it should be scoped before the enumeration budget is
   spent, not after.
6. Which of the six acquisition rows in section 5 is authorized, in what order,
   and with which exact URLs?
