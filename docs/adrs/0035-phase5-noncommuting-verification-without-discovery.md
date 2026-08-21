# ADR-0035: Noncommuting Phase 5 verifies supplied certificates and does not discover them

- **Status:** accepted; scopes the production noncommuting Phase 5 expansion and
  closes the solver option ADR-0033 left live
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 19 Phase 5 deferred expansion
  (quantum-state-discrimination plugin and independent SDP/numerical checks);
  ADR-0026 WP4
- **Decision owners:** repository owner

## Context

ADR-0033 measured the WP4 entry gate and passed it. The `1/4` primal/dual gap on
both noncommuting pure-state pairs closes to **exactly zero** over one real
quadratic extension of the rationals, with no dependency, no solver, no float,
and no tolerance anywhere on the path. It also constructed
`real-noncommuting-irreducible-cubic-boundary`, whose difference operator has
characteristic polynomial `λ³ − (3/50)λ + 3/1000`. That polynomial has no
rational root, so it is irreducible over `Q`, its roots have degree three, and
the optimum provably is not `a + b√d` for any rationals `a, b` and any `d`. No
certificate over any quadratic extension can close that case, ever.

ADR-0033 was explicit about what it does not do. The certificates were derived by
hand from the two-state Helstrom closed form; the checker verifies them and never
searches. For any instance without a closed form — more than two outcomes, or
higher dimension — the slice supplies no route to a candidate at all. ADR-0033's
addendum to `DEPENDENCY_LICENSE_COMPARISON.md` therefore kept the numerical-SDP
comparison table live, naming the cubic case as the one where an adapter would
still be the only route.

That leaves one decision, and it is the whole content of this ADR: whether the
production expansion accepts a verifier bounded to cases a human has already
solved, or admits a numerical solver as an untrusted candidate generator with the
exact checker as arbiter.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (verification only, no discovery) | ADR-0033 measured exactly-zero gaps over `Q(√2)`, `Q(√2)(i)`, `Q(√5)` with zero floats | Exact semantics preserved end to end; no dependency, no license review, no tolerance; byte-reproducible | Covers only instances whose optimum a human derived; does not answer general noncommuting convergence; risks reading as broader coverage than it has | Recorded certificate provenance; explicit coverage statement in every report |
| Wrap (solver proposes, exact checker arbitrates) | `DEPENDENCY_LICENSE_COMPARISON.md` reviewed five adapters | Would reach instances with no closed form, including the cubic boundary | Large pinned dependency closure; a converged solver result still needs a tolerance to be called zero; owner rejects on machine-noise grounds | Per-wheel hashes and licenses; rigorous certification of every residual |
| Interoperate (leave WP4 as a spike, integrate nothing) | The spike already measures the result | Zero further cost | Leaves Phase 5 at exact diagonal only, so WP4 delivers no capability | -- |
| Build/defer (no decision) | -- | -- | Silent drift, prohibited by AGENTS.md | -- |

## Decision

Adopt the first option. The production noncommuting Phase 5 expansion **verifies
certificates supplied to it and never discovers them.** No numerical solver is
adopted, now or as a gated adapter.

### Why the solver option is closed

The owner rejects numerical solvers on machine-noise grounds, calling out
eigenvalue computation in large matrices. That conclusion is adopted, and the
reasoning is recorded here in a sharper form than "floating point is imprecise",
because the sharper form is what makes it hold.

Forward error alone would not settle it. A backward-stable Hermitian eigensolver
returns eigenvalues exact for `A + E` with `‖E‖ ≈ ε‖A‖`, and Weyl's inequality
bounds each eigenvalue's forward error by `‖E‖` — Hermitian *eigenvalues* are
perfectly conditioned, so a trace norm computed from them has small forward
error. Three other properties are decisive instead:

1. **Any nonzero residual needs a tolerance to be called zero.** A computed gap
   of `1e-16` is not zero, and admitting it means asserting `gap < tol ⇒
   optimal`. Tolerance-based admission is precisely the forbidden outcome this
   benchmark exists to prevent. Exactness is not a precision preference here; it
   is the trust boundary.
2. **Trace-norm optima depend on partitioning a spectrum by sign.** For the
   traceless Hermitian difference operator, `‖D‖₁ = −2λ_neg` depends on the
   *count* of negative eigenvalues, not only their values. Near-degenerate
   clusters make sign and multiplicity determination unreliable even where each
   eigenvalue is well-conditioned. ADR-0033 settled exactly this question for the
   cubic case by an exact Descartes-rule argument over an irreducible polynomial
   — a determination no floating-point spectrum can make.
3. **Eigenvectors and invariant subspaces are conditioned by the spectral gap,
   and non-normal eigenvalues by `1/|y*x|`, which is unbounded.** Certificate
   construction needs eigenvectors, not just eigenvalues.

So the owner's conclusion stands on stronger ground than stated, and the option
is closed rather than deferred. `DEPENDENCY_LICENSE_COMPARISON.md` remains as
a record of a rejected comparison, not a live path.

### Boundaries that are part of this decision

**Verification only.** The module admits a certificate and checks primal
feasibility, dual feasibility, and an exactly closed gap. It contains no search,
no iteration toward an optimum, and no candidate generation. A case arriving
without a certificate produces an explicit unresolved outcome, never an attempt.

**Certificate provenance is recorded, and the certificate is a human input.**
A hand-derived certificate enters through the existing authorized-human-steering
boundary and is recorded with its deriving principal. It is never presented as a
system-generated result.

**Separation of duty is a known weak point here, and it becomes load-bearing.**
AGENTS.md already records that sealed Phase 5 accepts an identical originating
and creating principal. Under ADR-0023 that was tolerable because results were
computed. It is sharper now: if one principal derives a certificate and the same
principal approves its admission, no independent party stands between the
derivation and the trust record. Duality is what contains this — a zero-gap
certificate is self-verifying against the ensemble, so a wrong certificate fails
the exact check rather than passing quietly. The containment is mathematical, not
procedural, and the procedural gap stays open and recorded.

**Field boundary.** `F_d = Q(√d)(i)` for one squarefree `d` per case, with the
radicand measured from the case values rather than declared. Outside the field,
as explicit rejections: two distinct surds, any cubic or higher irreducible
extension, transcendental optima, and any float or tolerance.

**No coverage claim.** The expansion does **not** answer general noncommuting
JRF convergence, and no report, summary, or status line may imply that it does.
Every result carries a field distinguishing a verified supplied certificate from
a discovered optimum, and the latter is never produced.

**Search tiers 2--4 remain disabled**, unchanged by this ADR.

## Consequences

The honest risk in this slice is a **coverage illusion**. The acceptance suite
will show noncommuting cases with exactly-zero gaps and exact independent
optimum agreement, which reads like "the noncommuting case is handled." It is
not. Only instances whose optimum a human already derived in closed form are
handled, and that is a small, structured family — two-outcome ensembles with a
Helstrom closed form. A reviewer should read the coverage field before the gap
field, and the report must make that ordering obvious rather than available.

The measured cubic boundary is the standing reminder. It is a genuine
noncommuting ensemble that this design provably cannot close, retained in the
fixtures specifically so the boundary is visible in every run rather than
inferred from an ADR.

WP4 therefore delivers exactness rather than reach. That was the trade the owner
chose deliberately, and the scope loss is real: the question that motivated
Phase 5 remains open for every instance without a closed form.

## Explicit deferrals

- Exact *discovery* of a noncommuting optimum. Would need an exact method —
  symbolic characteristic-polynomial root isolation with exact algebraic number
  fields, or an exact SDP formulation — not a numerical one. Not attempted.
- Instances with more than two outcomes or dimension above the checker's bound.
- Any numerical, interval, or residual-reconstruction path. Closed, not deferred.
- Search tiers 2--4, which still require ADR-0029 activation evidence and a
  measured cost-adjusted gain.

## Validation and revisit trigger

The decision stays valid while the complete offline check remains green, the
module reaches no network and imports no third-party package, no tolerance
appears on any certificate path, and every result records its certificate
provenance and coverage status.

Reconsider if an instance with no closed form must actually be answered — which
requires an *exact* discovery method, not a reopening of the solver question — or
if the coverage field is ever found absent from a report, misreported, or
summarized as general noncommuting capability.

## Measured outcome

*Appended 21 August 2026 after implementation. Nothing above is rewritten.*

The verification-only expansion is implemented in `src/math_research/phase5/` as
`algebraic.py`, `exact_matrices.py`, `spectrum.py`, `noncommuting.py` and
`ports.py`, with `Phase5Service.admit_supplied_certificate` and
`Phase5Service.run_noncommuting_fixture` added alongside the sealed diagonal
path, a `phase5 verify-noncommuting` CLI subcommand, and the frozen fixture
`fixtures/phase5/noncommuting-certificates-v1.json` (`QD-NC-01`, eight cases).
`DiagonalCase` and `run_case` are byte-for-byte unchanged, because
`phase6/generality.py` drives them for GC-02B.

Measured on the eight frozen cases. Coverage status is the first column
deliberately; the gap column is meaningless without it.

| Case | Coverage status | Field | Primal | Dual | Gap |
|---|---|---|---|---|---|
| `commuting-exact-control` | `certificate_supplied_and_verified` | `Q(i)` | `1` | `1` | **exactly `0`** |
| `real-noncommuting-rational-candidate` | `certificate_supplied_gap_not_closed` | `Q(i)` | `3/4` | `1` | **exactly `1/4`** |
| `complex-noncommuting-rational-candidate` | `certificate_supplied_gap_not_closed` | `Q(i)` | `3/4` | `1` | **exactly `1/4`** |
| `real-noncommuting-algebraic-certificate` | `certificate_supplied_and_verified` | `Q(√2)(i)` | `1/2 + √2/4` | `1/2 + √2/4` | **exactly `0`** |
| `complex-noncommuting-algebraic-certificate` | `certificate_supplied_and_verified` | `Q(√2)(i)` | `1/2 + √2/4` | `1/2 + √2/4` | **exactly `0`** |
| `real-noncommuting-algebraic-certificate-radicand-five` | `certificate_supplied_and_verified` | `Q(√5)(i)` | `1/2 + √5/6` | `1/2 + √5/6` | **exactly `0`** |
| `real-noncommuting-certificate-withheld` | `unresolved_no_certificate_supplied` | `Q(i)` | not measured | not measured | not measured |
| `real-noncommuting-irreducible-cubic-boundary` | `certificate_supplied_outside_represented_field` | `Q(i)` | `3/5` | `11/10` | **exactly `1/2`, unreachable** |

Report content hash `sha256:ea7865cf9a36dca9965c0073a0b3b2c35a3afa80555b7ecdd5018a49645152c3`,
fixture hash `sha256:3504f1445a569515a07f3657dc91d858b9d9d574a6b057151b41134dd265f439`.
Both are pinned in the acceptance suite, so the measurement fails if it moves in
either direction; a silent improvement is as much a failure as a regression.

Five observations matter more than the table.

**The unresolved case is the load-bearing one.**
`real-noncommuting-certificate-withheld` carries the same ensemble as
`real-noncommuting-algebraic-certificate` and no certificate. Its measured
outcome is `unresolved_no_certificate_supplied` with primal, dual and gap all
absent, *even though* the independent closed-form cross-check is available and
reports `1/2 + √2/4` for that ensemble. The cross-check yields a scalar and no
POVM and no dual operator, so it cannot stand in for a certificate, and the
suite asserts that the slice does not use it to close the case. That is the
executable form of "verification only": the one instance where the module could
plausibly have discovered something, it declines.

**Coverage status is exhaustively exercised, not merely present.** All five
producible statuses are reached in the suite, including
`certificate_supplied_and_refuted`, so no reachable branch omits the field.
`optimum_discovered` is named as the forbidden value and admitted nowhere: the
single emission point rejects it, and a fixture declaring it as an expectation is
a reject.

**Two production tightenings over the spike.** The spike's `field_descriptor`
reported `degree_over_rationals` as `2` for `Q(√d)(i)` and `1` for `Q(i)`; both
are wrong, because `[Q(√d, i) : Q] = 4` and `[Q(i) : Q] = 2`. Production records
`degree_over_rationals` and `real_subfield_degree_over_rationals` separately. The
spike also applied its denominator bound to every intermediate value, which
rejects legitimate exact arithmetic on admissible input — a `2×2` determinant
squares denominators, so a certificate with a `2·10⁹` denominator failed the
`10¹²` bound during positive-semidefiniteness checking rather than on input.
Production bounds parsed input only; growth stays bounded because the dimension
bound bounds the degree of every polynomial in the entries. A third, narrower
tightening: a decimal string spelling such as `"1.5"` is now a reject rather than
being read exactly as `3/2`, so no float-shaped literal survives anywhere on the
path.

**Separation of duty is recorded, not repaired.** Every
`noncommuting_certificate_admission` record carries
`derivation_and_admission_principals_identical`, `enforced: false`,
`second_principal_required: false`, the containment
(`mathematical_zero_gap_certificate_is_self_verifying`) and the recorded gap in
prose. In the frozen fixture the two principals are the same
(`principal.phase5.owner`), so the flag reads `true` in every run and the gap is
visible rather than inferred. No second-principal requirement was invented;
sealed Phase 5 accepts an identical originating and creating principal and
changing that is a separate decision.

**One pre-existing property surfaced.** A Phase 5 record's `content_hash`
includes its append `sequence`, and the diagonal material-result event identity
binds the evidence record's content hash. So running the noncommuting fixture and
the diagonal fixture in one workspace moves the diagonal run's record hashes and
material event id, while `run_id`, `fixture_hash`, `finding_ids`, branch and
dead-end counts, and every mathematical value are unchanged. This is sealed
ADR-0023 behaviour, not a regression; Phase 6 is unaffected because it drives the
diagonal fixture in its own workspace. The acceptance suite asserts the
sequence-independent identities and records the reason for the ones it cannot.

Forbidden outcomes are demonstrated impossible rather than left untested. A
tolerance-admitted gap: a certificate leaving `1/1000000000` measures as
`certificate_supplied_gap_not_closed` with that exact gap, and both ADR-0033
epsilon mutations stay dead under direct `sign()` assertions. A discovered
optimum: no module in `src/` constructs a `SuppliedCertificate`, the only `cls(`
call inside the class is in `from_value`, no function outside the parser returns
one, no function name carries a search or optimization token, and a derivation
declaring a solver, search, interval or residual-reconstruction origin is a typed
reject. A certificate without a principal: missing, empty, unrecorded and
nonhuman deriving principals each fail closed, and sealed nonhuman diagonal
steering still raises. A float on the certificate path: typed rejections for
Python floats, JSON floats, `NaN`, decimal spellings and nested float leaves,
plus AST assertions that the exact modules contain no float literal, no
`math`/`decimal`/`random`/`time`/`os` import, no tolerance identifier, and no
`float`/`complex`/`hash` call. A missing coverage field: exhaustive over the
vocabulary. An out-of-field value: typed rejections for two distinct surds, a
cubic extension, a declared transcendental value, and a non-squarefree, negative,
non-integer or boolean radicand.

`make check` is green at the time of writing: every phase target passes and the
whole suite reports OK with 16 skipped for the disposable `jsonschema` gate
environment. No total test count is pinned here, because other slices were
landing concurrently and a moving total would be a false measurement; the
executable record is the 58-test acceptance suite in
`tests/test_phase5_noncommuting_certificates.py`.
Byte-reproducibility holds across two runs, a restart and a replay, and the
report hash is pinned so cross-process determinism is asserted rather than
assumed. `pyproject.toml` dependencies remain `[]`.

### Not done

- Exact *discovery* of a noncommuting optimum, and therefore the cubic-boundary
  case itself. Closed by this ADR, not deferred to this slice.
- Three or more outcomes, or dimension above four. The spectral probe reports
  more than two outcomes as unrepresentable regardless of the actual optimum,
  which under-claims rather than over-claims.
- Distinguishing a high-degree algebraic optimum from a transcendental one. The
  transcendental rejection is a *declaration* check: nothing here detects
  transcendence from values, and nothing distinguishes a hand derivation from a
  transcribed solver output either. Both limits are recorded in the code.
- Surfacing a verified noncommuting certificate as a material partial result.
  The existing event carries a hardcoded diagonal-commuting domain and changing
  it would move sealed identities, so the noncommuting path records findings,
  admissions, unresolved outcomes and a run summary instead.
