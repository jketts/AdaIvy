# ADR-0033: Close the noncommuting spike gap with exact quadratic-extension certificates

- **Status:** accepted for the WP4 entry gate only; implemented 21 August 2026
  with the gap closed on three fixtures and one measured field boundary --
  see "Measured outcome"
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 19 delivery roadmap (WP4 noncommuting
  Phase 5 expansion); ADR-0023 exact-arithmetic invariant for the quantum
  benchmark; ADR-0026 lightweight per-slice process
- **Decision owners:** repository owner

## Context

ADR-0026 places the noncommuting Phase 5 expansion at WP4. The blocker was
recorded and measured before this slice, not assumed.
`spikes/phase5_noncommuting_sdp/` carried three frozen fixtures and an exact
rational-complex validator. On the two noncommuting pure-state pairs the
supplied rational primal and dual points are feasible and leave an exact `1/4`
gap. `DEPENDENCY_LICENSE_COMPARISON.md` reviewed five numerical SDP adapters --
CVXPY, Clarabel, SCS, CVXOPT, MOSEK -- and adopted none, because a solver
reporting `optimal` produces a floating-point proposal, not an exact
certificate, and because accepting a tolerance-sized gap would break the
benchmark's exact semantics that ADR-0023 established.

The cause of the `1/4` gap is now measured precisely rather than described. For
the real pair, weighted states `A0 = diag(1/2, 0)` and
`A1 = [[1/4, 1/4], [1/4, 1/4]]`, the exact optimum is the Helstrom value

    (Tr(A0 + A1) + ||A0 - A1||_1) / 2 = 1/2 + sqrt(2)/4,

because `(A0 - A1)^2 = (1/8) I` exactly, so `||A0 - A1||_1 = sqrt(2)/2`. The
same value holds for the complex pair. The recorded `1/4` therefore decomposes
into two irrational pieces: a primal shortfall of `sqrt(2)/4 - 1/4` and a dual
excess of `1/2 - sqrt(2)/4`. `Fraction` arithmetic cannot represent either
piece, so no rational certificate can close the gap. This is a
representation limit, not infeasibility and not a missing solver.

The relevant fact for the choice of arithmetic is that the optimum is a
*rational plus a rational multiple of the square root of a rational*. For small
two-state discrimination that is the general shape: the trace norm of a
traceless `2 x 2` Hermitian difference with negative determinant is
`sqrt(t^2 - 4 det)`, and the optimum is `(Tr(A0 + A1) + that)/2`. A real
quadratic-extension arithmetic represents it exactly, with zero tolerance.

Three constraints bound the design. ADR-0026's standing policy keeps every
documented acceptance path offline, deterministic, and free of model and network
calls, and `tests/test_repository_invariants.py` enforces standard-library-only
imports; a numerical solver gets no exemption. ADR-0023 fixed exact arithmetic
as the invariant of the quantum benchmark, so introducing a float path anywhere
on the certificate route would reopen a sealed decision. And the spike must
stay out of `src/math_research/phase5/`, which ADR-0023 seals.

One fact about scope was known before implementation and is restated because it
limits what this slice can claim: an exact *checker* is not an exact *solver*.
Verifying a supplied certificate is decidable in this field; discovering one is
not addressed at all.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (numerical SDP adapter) | `DEPENDENCY_LICENSE_COMPARISON.md` reviewed five candidates | Would find optima for instances with no closed form, including the cubic case below | Output is a floating-point proposal needing rigorous reconstruction; large pinned dependency closure; GPL/commercial issues for two candidates; reopens the ADR-0023 exact invariant | Owner dependency decision; pinned hashed wheels; rigorous certifier |
| Wrap (exact algebraic arithmetic over one quadratic extension, standard library) | The measured optimum `1/2 + sqrt(2)/4` lies in `Q(sqrt 2)`; `(A0-A1)^2 = (1/8)I` exactly | Closes the gap to exactly zero with no dependency, no float, no tolerance; keeps ADR-0023's invariant; the field boundary becomes measurable | Covers only degree-two optima; certificates must be derived by hand, so the spike still cannot search; a new field type is new code to get wrong | Zero gap with zero tolerance; exact total comparison; canonical form and hash per value; no float structurally |
| Interoperate (keep the rational checker, record the gap as permanent) | The existing spike | Cheapest; nothing to get wrong | Leaves a measured, closable gap open and mislabels a representation limit as a solver blocker | -- |
| Build/defer (accept a tolerance-sized gap) | -- | -- | Destroys the benchmark's exact semantics; prohibited by ADR-0023 and AGENTS.md | -- |

## Decision

Adopt the wrap option, scoped to the spike.

Implement exact real-algebraic arithmetic in
`spikes/phase5_noncommuting_sdp/algebraic.py` and extend the exact validator to
run every check over that field. Seven boundaries are part of this decision.

**The represented field is stated, not implied.** A value is an element of

    F_d = Q(sqrt(d))(i) = { (a + b*sqrt(d)) + i*(c + e*sqrt(d)) }

for one squarefree integer `d >= 2`, with `a, b, c, e` rational, and `d = 1`
denoting the rational subfield `Q(i)`, which is compatible with every `d`. One
fixture case lives in exactly one `F_d`; `d` is measured from the case's values
and recorded in the result, never hardcoded.

**What falls outside `F_d` is named, and it is a real boundary.** Four classes
are outside and are rejects, not approximations:

- *Two distinct square roots.* `sqrt(2) + sqrt(3)` lives in
  `Q(sqrt 2, sqrt 3)`, degree four. Combining two values with distinct
  nontrivial radicands raises, and a case mixing radicands is rejected before
  any arithmetic runs.
- *A cubic or higher irreducible extension.* This is the substantive boundary,
  and it is reached by an ordinary instance rather than a contrived one. A
  two-outcome ensemble in dimension three whose difference operator has an
  irreducible cubic characteristic polynomial has eigenvalues of degree three
  over `Q`; the trace norm, and therefore the optimum, is then not of the form
  `a + b*sqrt(d)` for any rational `a, b` and any `d`. No certificate over any
  quadratic extension can close that gap. The fixture set contains such a case
  and the validator reports it as outside the field with a machine-checked
  argument, rather than reporting a small gap or omitting the case.
- *A genuinely transcendental optimum.* An instance whose optimum is not
  algebraic is outside this arithmetic by construction and outside any
  algebraic-number arithmetic at all. Nothing in this slice detects that
  situation; it would present as a probe that finds no rational root and no
  quadratic factor, indistinguishable here from a high-degree algebraic case.
  The slice therefore cannot distinguish "high degree" from "transcendental",
  and does not claim to.
- *Any float or tolerance.* There is no floating-point path, and there is no
  epsilon anywhere. This is asserted structurally, not by inspection.

**Comparison is exact and total inside one field.** The sign of
`a + b*sqrt(d)` is decided by integer comparison of `a^2` against `b^2 d` when
the two parts disagree in sign, and by inspection otherwise. Comparison across
two distinct nontrivial radicands is a reject, because that pair is not
contained in any single represented field. There is no epsilon, and no
comparison consults a magnitude threshold.

**Canonicalization is total and one value has one hash.** A value's radicand is
squarefree by construction, a zero surd forces `d = 1`, and a surd that cancels
folds into the rational part; `sqrt(8)/2`, `sqrt(72)/6` and `sqrt(2)` are one
object with one canonical JSON form and one `sha256:`-prefixed digest. Decimal
string spellings such as `"1.5"` are read *exactly* as `3/2` -- never rounded --
and re-emitted in the single canonical `p/q` form, so accepting them does not
create a second representation.

**Rejection is a single explicit exception hierarchy.** Following the
`QuantumInputError` precedent in `src/math_research/phase5/quantum.py`, every
field violation raises `AlgebraicFieldError`, and the validator's
`CertificateInputError` is a subclass of it. There is one error root and no
coercion path: an out-of-field value never becomes an in-field approximation.

**Every SDP check runs over the field, not only over `Fraction`.** Hermiticity,
positive semidefiniteness via all principal minors, trace normalization,
effective support, POVM completeness, dual domination `Gamma >= A_i`, the primal
and dual objective values, and two-sided complementarity `(Gamma - A_i) E_i = 0`
and `E_i (Gamma - A_i) = 0` are all evaluated with algebraic entries. Two
independent measurements are added: an exact spectral field probe on the
difference operator, and the exact two-state closed-form optimum for dimension
two, which cross-checks a zero-gap certificate against a second derivation.

**This spike grants no mathematical warrant and does not enable search tiers 2
through 4.** Nothing here integrates with `src/math_research/phase5/`, touches
a sealed Phase 5 record, the Phase 3B runtime, the Phase 4A rights boundary,
deletable content, or a protected evidence manifest. Every result carries
`mathematical_warrant: none_spike_only`, `proposal_status:
candidate_check_only`, `graph_admitted: false`, `phase5_integrated: false`, and
`search_tiers_enabled: false`. A checked certificate is a checked certificate;
it is not an `EpistemicWarrant`, not an applicability judgement, and not a
novelty or significance assessment.

The owner has approved extending the frozen fixture document for this slice.
The document and case schema versions move from `v1` to `v2`, two required
expectation fields are added (`expected_quadratic_representable` and
`expected_independent_optimum`), and four cases are appended. The three original
cases keep their mathematical content byte-for-byte.

## Consequences

The acceptance suite in `tests/test_phase5_noncommuting_sdp_spike.py` is the
sole executable record of this slice's thresholds under ADR-0026, so it asserts
the boundaries above as properties rather than exercising a happy path. It pins
the measured gap of every case in both directions, so a silent improvement is
as much a failure as a regression.

**The honest risk in this slice is that the certificates were derived, not
discovered.** The exact checker is genuinely exact, but the three closing
certificates were written by hand from the two-state Helstrom closed form. For
any instance with no closed form -- three or more outcomes, or dimension above
two -- this slice supplies no route to a candidate at all, and the exact checker
would sit idle waiting for one. A reader who takes "the gap closed" to mean
"the spike can now solve noncommuting instances" has drawn exactly the wrong
conclusion. Two things bound the risk without removing it: duality makes a
zero-gap certificate self-verifying, so the derivation does not have to be
trusted; and the independent closed-form cross-check catches an authoring error
where duality alone would not. Neither turns the checker into a solver.

A second, narrower risk is that the spectral field probe is conservative in one
direction. It peels rational roots exactly and classifies a residual quadratic
by the squarefree part of its discriminant. A residual *quartic* that happens to
factor into two rational quadratics of the same square class would in fact be
representable, and the probe reports it as outside the field. That is a
false-negative boundary: it can under-claim representability, never over-claim
it. The same conservatism applies to shape: the probe covers two outcomes only,
so a three-outcome case is reported as unrepresentable regardless of its actual
optimum, and a fixture author adding one must record
`expected_quadratic_representable: false`. It fails closed, which is the correct
direction, but a case the probe calls unrepresentable is not proof that it is --
only the irreducible-cubic determination carries a proof, and only because the
degree argument is machine-checked.

Extending a frozen fixture document is a real cost. Anything comparing against
the pre-extension three-case document is comparing across different fixture
sets. The `v1` case schema version is now a reject, and the discontinuity is
recorded here, in the spike README, and in the version strings themselves rather
than being inferred from a diff.

Serialization gains a value grammar with three shapes -- a rational string, a
surd object, and a complex object -- and the surd object is new surface for a
malformed candidate to exploit. Unknown keys, partial key sets, a nested complex
value in a real part, a non-integer radicand, a non-squarefree radicand in
canonical position, a negative radicand, floats, duplicate JSON keys, `NaN`, and
`Infinity` are all rejects.

## Measured outcome

Implemented and measured on 21 August 2026 over the seven frozen fixtures. The
`1/4` gap closed to exactly zero on both noncommuting pure-state pairs, and one
case is a measured boundary that cannot close at all.

| Case | Certificate field | Primal | Dual | Gap | Outcome |
|---|---|---|---|---|---|
| `commuting-exact-control` | `Q` | `1` | `1` | **exactly `0`** | unchanged control |
| `real-noncommuting-rational-candidate` | `Q` | `3/4` | `1` | **exactly `1/4`** | retained blocker |
| `complex-noncommuting-rational-candidate` | `Q` | `3/4` | `1` | **exactly `1/4`** | retained blocker |
| `real-noncommuting-algebraic-certificate` | `Q(sqrt 2)` | `1/2 + sqrt(2)/4` | `1/2 + sqrt(2)/4` | **exactly `0`** | gap closed |
| `complex-noncommuting-algebraic-certificate` | `Q(sqrt 2)(i)` | `1/2 + sqrt(2)/4` | `1/2 + sqrt(2)/4` | **exactly `0`** | gap closed |
| `real-noncommuting-algebraic-certificate-radicand-five` | `Q(sqrt 5)` | `1/2 + sqrt(5)/6` | `1/2 + sqrt(5)/6` | **exactly `0`** | gap closed |
| `real-noncommuting-irreducible-cubic-boundary` | `Q` | `3/5` | `11/10` | **exactly `1/2`, unreachable** | measured boundary |

Zero means zero: all four complementarity residual matrices of each closing
certificate are exactly the zero matrix, entry by entry, and the primal value,
the dual value, and the independent closed-form optimum are the same field
element.

Four details matter more than the table.

**The closing cases are not easier problems.** The weighted-state blocks of
`real-noncommuting-algebraic-certificate` and
`complex-noncommuting-algebraic-certificate` are byte-identical to the ensembles
of the two cases that leave `1/4`, and the acceptance suite asserts that
equality on canonical bytes. The only thing that changed is the field the
certificate is written in. The `1/4` rows are kept so the comparison is visible
in the fixture rather than only in this ADR.

**The field is measured, not hardcoded.** The third closing case lives in
`Q(sqrt 5)`, with an *ensemble* that is itself irrational
(`A1 = [[2/9, sqrt(5)/9], [sqrt(5)/9, 5/18]]`, a rank-one weighted pure state),
and its optimum is `1/2 + sqrt(5)/6`. The report records the radicands actually
used as `[1, 2, 5]`. A `sqrt(2)`-specific implementation would fail this case.

**The cubic boundary is a measured result, not a caveat.** The seventh case is a
genuine noncommuting two-outcome ensemble in dimension three with positive
semidefinite weighted states, traces `1/2` and `1/2`, and a positive definite
sum. Its difference operator has characteristic polynomial

    lambda^3 - (3/50) lambda + 3/1000,

which has no rational root -- checked exactly by rational-root enumeration over
the divisors of the cleared integer coefficients -- and is therefore irreducible
over `Q`. Every root of a Hermitian operator is real, so Descartes' rule of
signs is exact rather than a bound, and the signature is measured as two
positive roots, one negative root, and no zero root. The operator is traceless,
so the trace norm equals `-2` times the single negative root, an algebraic
number of degree three over `Q`. Hence the optimum `(1 + ||D||_1)/2` is of
degree three and is not `a + b*sqrt(d)` for any rational `a, b` and any `d`.
This case is recorded with disposition
`candidate_only_outside_represented_field` and a supplied feasible-but-loose
rational candidate whose gap is exactly `1/2`. The fixture cannot be relabelled
to hide it: claiming `expected_quadratic_representable: true` or
`expected_zero_gap: true` on it is a reject.

**Nothing was tuned and no fixture was chosen to fit the arithmetic.** The
cubic case was authored specifically to be harder than the arithmetic can
represent, and it is reported as such. The two `1/4` cases were not deleted,
softened, or re-derived.

The acceptance suite is 54 tests. Its non-vacuity was checked by mutation:
disabling the positive-semidefiniteness test, forcing complementarity true,
dropping squarefree normalization, dropping the surd from canonical output,
coercing mixed radicands instead of rejecting them, and forcing the probe to
report every spectrum representable each cause failures. Two epsilon mutations
-- snapping a rational or a pure-surd quantity below `1/1000` to zero inside
`sign()` -- initially survived, which means the "no tolerance" claim was
asserted but not enforced; tests were added that kill both, and the mutations
were re-run to confirm. `make check` is green at the time of writing: 1131
tests, 16 skipped for the disposable `jsonschema` gate environment, and every
phase target passes.

## Explicit deferrals

- **Arithmetic over a cubic or higher extension**, and with it the
  `real-noncommuting-irreducible-cubic-boundary` case. This needs a general
  algebraic-number representation (minimal polynomial plus an isolating
  interval, or a primitive-element tower), exact real root isolation, and an
  exact sign test at an algebraic point. It is a materially larger slice than
  this one and is not started.
- **Any exact optimum for three or more outcomes, or for dimension above two.**
  No closed form is implemented and none is claimed; the independent
  cross-check reports itself unavailable for those shapes with a recorded
  reason rather than guessing.
- **Certificate discovery.** This slice verifies; it does not search. An exact
  or rigorously-certified solver remains the open question, and
  `DEPENDENCY_LICENSE_COMPARISON.md` stays live for the instances where a
  solver would be the only route to a candidate.
- **Integration into `src/math_research/phase5/`.** Sealed under ADR-0023.
  Integration is a separate step, gated on what this entry gate measured, and it
  must also decide how a `Q(sqrt d)` value is represented in Phase 5 records and
  content hashes.
- **Search tiers 2 through 4.** Unchanged and disabled. Nothing measured here
  is evidence of cost-adjusted verified gain, which ADR-0029 requires.
- **Quartic residual factorization in the spectral probe.** Reported as outside
  the field, which under-claims rather than over-claims.
- **Distinguishing a high-degree algebraic optimum from a transcendental one.**
  Not attempted.

## Blueprint deviation

The fixture document at `fixtures/phase5-noncommuting-sdp/exact-small-cases.json`
was frozen at `v1` and is extended here to `v2`: two required expectation fields
are added and four cases are appended, with the three original cases keeping
their mathematical content unchanged. The owner authorized the extension for
this slice. The deviation is necessary because the recorded blocker cannot be
shown closed without a certificate for the same ensembles, and cannot be shown
bounded without a case that exceeds the field. The revisit trigger is any
further change to this document: a fixture that changes to make a check pass,
rather than to record a measurement, invalidates the comparison the `v2`
document exists to make.

Otherwise none. No dependency, no network call, no model call, no float path, no
tolerance, no change to a sealed boundary, and no change to search tiers.

## Validation and revisit trigger

The decision stays valid while `make check` remains green, the spike imports
only the standard library, every fixture case's measured gap matches the pinned
value in both directions, the certificate path contains no float and no
tolerance, comparison stays exact and total inside one field, a value keeps
exactly one canonical form and one hash, mixed radicands stay a reject, and the
spike keeps out of `src/math_research/phase5/`.

Reconsider if a fixture's measured gap moves in either direction; if any check
acquires a tolerance, an epsilon, a float, or a numerical solver; if a case
requires two distinct radicands or an extension of degree three or more, which
is the boundary this ADR names and would require a materially different
arithmetic rather than a patch; if the spectral probe is found to report a
representable spectrum as unrepresentable in a case that matters; if a
certificate is admitted whose primal value disagrees with the independent
closed form; or if any part of this spike is treated as a mathematical warrant,
an applicability judgement, or evidence for enabling a higher search tier.
