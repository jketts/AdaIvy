# ADR-0045: Phase 5 noncommuting SDP engine-comparison experiment

> **Number.** Filed as **0045**. Drafted as 0034 while that number looked free;
> 0032--0044 were allocated by concurrent sessions before it landed, so it was
> renumbered on merge with no change to its content.

- **Status:** proposed
- **Date:** 2026-08-21
- **Blueprint requirement:** Phase 5 exact quantum benchmark boundary; the
  adapter-adoption experiment specified at
  `spikes/phase5_noncommuting_sdp/DEPENDENCY_LICENSE_COMPARISON.md` lines 22--28
  and the blocker at lines 30--32; `AGENTS.md` engineering rules (compare with
  the file-based baseline, never turn experiments or model/tool agreement into
  proof status, preserve failed attempts and missing-tool results, pin and
  licence-record dependencies, keep Phase 0--6 runnable without network)
- **Decision owners:** repository owner (authorization and licence restriction);
  implementing session (bounded slice)

## Context

`spikes/phase5_noncommuting_sdp/DEPENDENCY_LICENSE_COMPARISON.md` reviewed five
SDP adapter candidates on 2026-08-20, adopted none, and specified the smallest
later experiment verbatim: run the same frozen real and complex fixtures through
at least two independent SDP engines, retain raw solver status/residuals and
exact problem encodings, and attempt rational/algebraic or interval
reconstruction. It also recorded the substantive blocker: the noncommuting
fixtures have simple rational primal and dual points that are feasible but leave
an exact `1/4` gap, the true optimum is irrational, and accepting a
tolerance-sized gap would violate the benchmark's exact semantics.

`AGENTS.md` lines 38--42 forbid adding a noncommuting SDP solver "without a
later explicit implementation request". **That request has now been given, and it
was given with a restriction: permissive licences only -- Clarabel (Apache-2.0),
SCS (MIT), CVXPY (Apache-2.0). CVXOPT (GPLv3-or-later) and MOSEK (commercial
EULA) are out of scope and must not be added, imported, or referenced as
adopted.** The authorization covers the comparison experiment only. It does not
authorize Phase 5 integration, does not authorize enabling search tiers 2--4
(`src/math_research/phase5/service.py` lines 379--383 record them disabled for
want of measured cost-adjusted gain, and this experiment supplies no such
measurement), and does not authorize letting a numerical result carry a warrant.

Verified facts, established by execution in this session:

- Both engines run and both report success on all three frozen fixtures
  (Clarabel `Solved`, CVXPY/SCS `optimal`), landing within about `1e-11` of
  `(2 + sqrt(2))/4`.
- **Neither engine closed the gap.** Each returned floating-point point was
  converted to the exact dyadic rationals it already is and held to the
  benchmark's exact conditions. All six engine points were rejected: POVM
  completeness was off by up to `297/36028797018963968`, complementarity was
  nonzero, and exact primal--dual gaps ranged over roughly `1e-14` to `1e-11`.
  One SCS point had a *negative* exact gap, i.e. it exactly violated weak
  duality and was infeasible, while its status was `optimal`.
- A solver-free exact reconstruction does close the gap for these fixtures. For
  two outcomes in dimension two the optimum is attained by the spectral
  projector onto the positive part of `W_1 - W_2`; the characteristic polynomial
  is quadratic, so the whole certificate lies in `Q(sqrt(disc))` and is verified
  by exact weak duality plus exact two-sided complementarity. Both noncommuting
  fixtures certify at exactly `1/2 + (1/4)sqrt(2) = (2 + sqrt(2))/4` with an
  exactly zero gap, and the commuting control reproduces its known rational
  certificate of `1`.
- **Rational reconstruction fails**, and the failure is recorded. The optimum is
  `a + b*sqrt(2)` with `b != 0` and `2` squarefree, so no rational of any
  denominator equals it. The closest rational with denominator at most `10**6`
  is `665857/780100`, which leaves an exact nonzero residual. The documented
  `1/4`-gap blocker is now proved exactly rather than asserted: the rational
  candidate `3/4` falls short by exactly `(sqrt(2) - 1)/4`.
- The semantic/operational hash split holds under measurement: two consecutive
  real two-engine runs produced identical `content_hash` and different
  `operational_hash`.

Assumptions, not verified facts:

- Licence strings are as declared in each wheel's `METADATA`. No legal review
  was performed and none is claimed.
- The two engines are independent implementations. They are not independent of
  the shared exact encoding, of NumPy/SciPy, or of IEEE-754 arithmetic.
- Results were observed on one platform only: CPython 3.14.4, macOS ARM64.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt an engine into Phase 5 | both engines solve all three fixtures to `~1e-11` | would unlock the noncommuting Phase 5 expansion | exact audit rejected all six engine points; no measured cost-adjusted verified gain; would put a floating-point result on a warranted path | REJECTED: `AGENTS.md` and ADR-0029 require measured retention gain; a numerical point is not an exact certificate |
| Wrap: spike-local gated adapters behind a port, exact checks arbitrate | this ADR's implementation; fail-closed path fully testable offline with no skip | satisfies the specified experiment; retains raw status/residuals/encodings; keeps the trust boundary structural | two adapters to maintain; a 15-wheel disposable closure to keep pinned | CHOSEN: no Phase 5 integration, no tier enabling, no warrant, permissive licences only |
| Interoperate: use CVXPY's native Hermitian variables per engine | CVXPY documents complex/Hermitian expressions | less encoding code | the two engines would receive two different models, so a disagreement would be uninterpretable | REJECTED: both engines must consume one identical exact encoding |
| Build/defer: exact reconstruction only, no engine at all | the reconstruction certifies all three fixtures with no solver | zero dependencies | would not answer the specified question, and would leave the "do engines actually close the gap?" claim untested | REJECTED as the whole slice; RETAINED as the arbiter inside the chosen option |

Also considered and rejected on licence grounds alone, without evaluation:
CVXOPT (GPL-3.0-or-later) and MOSEK (commercial EULA), plus ECOS, Gurobi,
XPRESS, COPT, CyLP and Knitro, which CVXPY declares as optional extras.

## Decision

Implement the experiment as a **spike-scoped comparison, bounded to
`spikes/phase5_noncommuting_sdp/`**, with the exact boundary below.

1. **Authorization and licence restriction, recorded and enforced.** Permitted:
   Clarabel (Apache-2.0), SCS (MIT), CVXPY (Apache-2.0), plus the BSD/MIT
   numeric closure they require (NumPy, SciPy, and the twelve further wheels
   listed in `DEPENDENCY_LICENSE_COMPARISON.md`). Excluded, and refused by name:
   CVXOPT, MOSEK, ECOS, Gurobi, XPRESS, COPT, CyLP, Knitro. Three independent
   controls, not one: `engines.authorize_module` refuses every excluded name
   before any import; `tests/test_repository_invariants.py` enumerates the
   complete set of gated dynamic loads statically and fails on an undeclared
   one; and the CVXPY adapter refuses to run if `cvxpy.installed_solvers()`
   exposes an excluded solver and discards its own result if CVXPY selected any
   solver other than SCS.

2. **The exact check is the only arbiter.** A case's disposition is derived only
   from an exact check -- the file-based rational baseline
   (`validator.validate_fixture`) and/or the exact algebraic reconstruction.
   `NumericSolution` has no `verified`, `warrant`, `proved`, or `trusted` field,
   and its `trust` is a read-only constant `"untrusted_candidate"`, so no adapter
   and no later code path can construct a numerical result that claims
   otherwise. `engine_status` is retained verbatim as evidence about the engine,
   never about the mathematics.

3. **Two engines agreeing is not evidence of correctness.** The agreement record
   carries `is_evidence_of_correctness: false` and
   `contributes_to_disposition: false`, and an acceptance test asserts that two
   agreeing engines reporting `optimal` do not certify a case the exact checks
   cannot resolve.

4. **No tolerance anywhere on the acceptance path.** Ordering in `Q(sqrt(s))` is
   decided by comparing `a**2` with `s*b**2`; PSD is decided by the signs of all
   principal minors. An engine's point is audited by exact conversion to the
   dyadic rationals it already is. Gaps of `1e-9`, `1e-15`, and the real
   measured `1e-14`--`1e-11` are all rejected.

5. **Bounded reconstruction, failing closed.** The exact spectral construction
   covers exactly two outcomes in dimension two, in a quadratic field with a
   squarefree radicand at most 1000 and bounded square-part extraction. Any other
   shape is recorded as `unsupported_shape` with a reason code and no optimum is
   claimed.

6. **Semantic versus operational hashing, per the Phase 3B precedent.** Any
   object carrying `hash_class: operational_only` -- timings, iteration counts,
   residuals, returned floating-point matrices, and every check derived from
   them -- is replaced by a marker in the semantic preimage. `content_hash`
   covers semantic identity; `operational_hash` covers the complete report.

7. **Absent engines are recorded, never skipped.** With the engines absent every
   adapter returns a `MissingTool` record naming the pinned manifest, the report
   states `experiment_status: incomplete_engines_absent_or_refused`, and the CLI
   exits 1. That is the offline result and it is not a pass. No test in the
   offline suite skips.

8. **Disposable environment only.** The engines are installed from
   `requirements-phase5-sdp-comparison-py314-macos-arm64.txt`
   (3133 bytes, SHA-256
   `1976a945e8683a01eb13d0eac5a8387cee564ba4d2db34365fe68b93355a44e9`) into a
   throwaway environment outside the repository, with `--require-hashes`,
   `--only-binary=:all:`, `--no-index`, and no extras. Never the repository
   `.venv`, system Python, user site, or any production import path.

What remains canonical: `validator.py` as the file-based baseline, the frozen
fixture file, and the exact checks. What may be delegated: the numerical search
for a starting point, which is exactly the part whose output is untrusted.

## Consequences

**Operational.** One new Makefile target, `spike-phase5-sdp`, deliberately
outside `make check`. Its fail-closed leg always runs offline and asserts the
recorded outcome in both directions, so a silent completion (an engine loaded on
the offline path) and a lost certificate both fail. `make check` is unchanged and
still needs zero third-party packages. **No new test skips**: the CI assertion of
exactly 16 skips in `.github/workflows/check.yml` is untouched, because the
fail-closed path is asserted deterministically through an injected
`AbsentModuleResolver` rather than by skipping.

**Security.** Two more gated dynamic boundaries in the declared allowlist, five
new entries in total. `tests/test_repository_invariants.py` now also scans
`spikes/` and forbids a third-party import at *any* nesting level in `src/` and
`spikes/`, so a literal-named gated call is the only route to a third-party
module. One pre-existing exception is declared rather than hidden:
`spikes/phase4_gate/gate_spike.py` imports `jsonschema` at module scope and runs
only in its own disposable environment.

**Licensing.** The owner named three packages; the real closure is fifteen
wheels. All are permissive as declared. The material finding is that CVXPY
declares CVXOPT, MOSEK and ECOS as optional extras, so the manifest must always
be installed with no extras -- a `pip install cvxpy[mosek]` would silently import
commercial and copyleft code. This is why the licence control is enforced in code
and tests and not left to the manifest.

**Reproducibility.** Semantic identity is stable across runs, machines, and
engine timing; verified by two real runs. Semantic identity does *not* claim
stability across engine versions, and should not: module versions are part of the
semantic record deliberately, so an engine upgrade changes the semantic hash.
Floating-point observations are not bit-reproducible and are not hashed as if
they were.

**Migration.** None. No stored record changes, no schema in `src/` changes, no
Phase 5 sealed record is touched, and search tiers 2--4 remain disabled.

**Negative consequences, stated plainly.**

- The exact reconstruction is a *solver* for a very narrow shape: two outcomes,
  dimension two, quadratic field. `AGENTS.md` forbids adding a noncommuting SDP
  solver without an explicit request; the request was given for this experiment,
  and this is the reconstruction step the specification asked for, but it is
  still solving-shaped code and is flagged as such below.
- The experiment answers the question for three 2x2 fixtures only. It does not
  show that any engine is usable for a general noncommuting Phase 5 expansion,
  and it produces no cost-adjusted verified-gain measurement, so it moves the
  ADR-0029 activation evidence forward not at all.
- Maintaining two adapters plus a fifteen-wheel pinned closure is real ongoing
  cost for a spike that adopts nothing.
- The disposable environment was built on one platform. Any other platform is
  unverified and the manifest's wheel tags will not match it.

## Blueprint deviation

**There are four deviations. None is hidden in implementation detail.**

1. **`AGENTS.md` lines 38--42 forbid a noncommuting SDP solver without a later
   explicit implementation request.** The request was given, so the *engine
   adapters* are authorized. But the exact reconstruction in
   `reconstruction.py` also finds an optimum, and for a two-outcome
   dimension-two case that makes it solver-shaped code that the blueprint's
   Phase 5 scope ("exact scalar/diagonal `QD-FS-01` with deterministic tier-0
   branches") does not contain. **Necessity:** the specification at
   `DEPENDENCY_LICENSE_COMPARISON.md` lines 22--28 requires a reconstruction
   attempt, and lines 30--32 make clear that no rational candidate can close the
   gap, so a reconstruction that cannot leave the rational field cannot answer
   the question at all. **Bounding:** it is spike-local, refuses every shape
   outside two outcomes in dimension two, contains no floating-point arithmetic,
   never reads a solver result to decide anything, and is itself checked by
   exact weak duality and complementarity rather than trusted. **Revisit
   trigger:** any request to widen it beyond that shape, to import it from
   `src/`, or to let it certify a Phase 5 record. Any of those needs a new ADR.

2. **`AGENTS.md` requires the standard library for the harness and forbids
   adding a dependency without a later explicit request.** Three direct
   dependencies plus a twelve-wheel transitive closure are now pinned. This is
   authorized and licence-restricted, but it is still the first time this
   repository has an engine-bearing manifest. **Bounding:** disposable
   environment only, absent by default, `make check` unaffected. **Revisit
   trigger:** any proposal to install these into the ordinary environment, to
   add them to `pyproject.toml`, or to select a CVXPY extra.

3. **`tests/test_repository_invariants.py` previously scanned only `src/`, and
   its `GATED_DYNAMIC_IMPORTS` paths were `src`-relative.** This change makes
   those paths repository-root-relative and extends the scan to `spikes/`. That
   is a strengthening, but it does rewrite three pre-existing entries and it
   introduces `DECLARED_MODULE_LEVEL_THIRD_PARTY` to carry one pre-existing
   `jsonschema` import that would otherwise newly fail. **Revisit trigger:** a
   second entry appearing in that exception list, which would mean the rule is
   being worked around rather than followed.

4. **`DEPENDENCY_LICENSE_COMPARISON.md` previously stated that no package had
   been downloaded, imported, or invoked.** That is no longer true and the status
   line has been rewritten rather than left standing. The unchanged part -- that
   nothing is selected for production and nothing is installed in the repository
   environment -- is stated separately so the two claims cannot be confused.

## Validation and revisit trigger

Executable checks that keep this decision valid, all in
`tests/test_phase5_noncommuting_sdp_comparison.py` unless noted, and all runnable
offline with zero third-party packages:

- `ExcludedLicenceTests` -- every excluded module is refused by name, including
  as a submodule; the allowlist and exclusion list are disjoint; every authorised
  module declares a permitted licence expression; no excluded name appears as a
  literal in any gated call anywhere in the spike; the pinned manifest contains
  no excluded package and pins every requirement to a 64-hex SHA-256.
- `SolverStatusIsNotAWarrantTests` -- `NumericSolution` has no verification
  field; `trust` is a constant that cannot be reassigned; an `optimal` status
  does not certify a case the exact checks cannot resolve; two agreeing engines
  do not either; an engine outside the authorised registry cannot count towards
  the two-engine clause; every report-level guardrail is negative.
- `ToleranceSizedGapIsNotExactTests` -- an exactly optimal dyadic point IS
  accepted (so the audit is not vacuously rejecting), while gaps of `1e-9` and
  `5e-16` are rejected with reason `tolerance_sized_gap_is_not_an_exact_gap`.
- `MissingEngineIsRecordedTests` -- both engines absent yield missing-tool
  records, not skips; the two-engine clause is reported unsatisfied; retention
  clauses are reported `not_exercised_no_engine_executed` rather than claimed.
- `NoNetworkOnAcceptancePathTests` -- the whole comparison completes with
  `socket.socket`, `socket.create_connection`, `socket.getaddrinfo` and
  `urllib.request.urlopen` all poisoned, plus a static scan for network imports.
- `ExactReconstructionTests` and `BaselineCrossCheckTests` -- the optimum is
  exactly `1/2 + (1/4)sqrt(2)`; the gap is exactly zero with exact
  complementarity; rational reconstruction fails with a recorded reason; the
  documented `1/4` baseline gap is preserved and the rational candidate is proved
  suboptimal by exactly `(sqrt(2) - 1)/4`; unsupported shapes are recorded.
- `SemanticVersusOperationalHashTests` -- timing variance changes only the
  operational hash; a status change changes both; operational observations are
  still retained in the report.
- `SpikeIsolationTests` -- the spike imports nothing from `math_research`, writes
  only through the CLI's `--output`, and has no module-level third-party import.
- `tests/test_repository_invariants.py` -- the five new gated boundaries are
  declared, and no third-party module is reachable except through a declared
  gated load with a literal name.

Evidence that would cause reconsideration:

- An engine returning a point whose exact audit *accepts*, which would change
  the cost/benefit of a rigorous certifier.
- A measured cost-adjusted verified-gain result for a wider noncommuting scope,
  which is what ADR-0029 requires before any tier or specialist activation and
  which this experiment does **not** provide.
- Any licence change in the fifteen-wheel closure, or a CVXPY release that makes
  an excluded solver an unconditional requirement; either invalidates the
  manifest immediately.
- A second platform where the exact reconstruction and the engines disagree about
  which cases are certifiable, which would point at a formulation error in the
  shared exact encoding rather than at either engine.
