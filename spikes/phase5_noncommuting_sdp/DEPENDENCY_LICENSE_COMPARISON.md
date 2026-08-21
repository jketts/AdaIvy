# Noncommuting SDP adapter comparison

Status: superseded on 2026-08-21 by the authorized comparison experiment
(ADR-0045). The original review of 2026-08-20 was design-only and downloaded,
imported, and invoked nothing; that is no longer true and the change is recorded
in "Authorization update" below. **No package is selected for production, and
none is installed in the repository environment.** `make check` still runs with
zero third-party packages installed, and the offline path still loads no engine.

The file-based baseline is this spike's exact rational-complex validator. It
can check Hermiticity, PSD via all principal minors for dimensions at most four,
trace normalization, POVM completeness, dual domination, primal/dual values,
and two-sided complementarity. It cannot discover an optimum or turn a
floating-point result into an exact certificate.

| Candidate | Primary evidence | License | Fit | Blocking issue before adoption |
|---|---|---|---|---|
| CVXPY plus an SDP solver | [advanced constraints](https://www.cvxpy.org/tutorial/constraints/index.html) document PSD, Hermitian, and complex expressions; [installation](https://www.cvxpy.org/install/) lists NumPy, SciPy, Clarabel, SCS, and OSQP as dependencies | [Apache-2.0](https://github.com/cvxpy/cvxpy) for CVXPY; every selected solver and transitive wheel still needs separate review | Best modeling-layer ergonomics and explicit complex/Hermitian syntax | Large dependency closure; canonicalization and solver output remain numerical proposals, not proof; pin/hash/license every wheel and compare direct solver formulations |
| Clarabel Python | [official SDP example](https://clarabel.org/stable/examples/py/example_sdp/) uses `PSDTriangleConeT`; [repository](https://github.com/oxfordcontrol/Clarabel.rs) documents SDP and infeasibility detection | Apache-2.0 | Promising direct, permissively licensed interior-point adapter with status/certificate vocabulary | Real conic encoding is required for complex Hermitian matrices; floating residuals need rigorous reconstruction; Python wheel includes compiled Rust and NumPy/SciPy interfaces that require a complete binary/dependency audit |
| SCS Python/direct C | [official API](https://www.cvxgrp.org/scs/api/index.html) returns primal-dual points or infeasibility certificates; [repository](https://github.com/cvxgrp/scs) lists real and complex SDP cones | MIT | Useful independent first-order comparison and failure-route generator | Approximate first-order output is not an exact optimum certificate; SDP support uses BLAS/LAPACK; tolerances, scaling, precision, and native dependency hashes must be frozen |
| CVXOPT | [official SDP interface](https://cvxopt.org/userguide/coneprog.html#semidefinite-programming) exposes primal and dual SDP data and stopping parameters | [GPLv3-or-later](https://cvxopt.org/userguide/copyright.html) | Mature direct SDP interface and useful cross-check candidate | Copyleft compatibility requires owner/legal decision; documented SDP interface is real symmetric, so complex-to-real encoding must be audited; numerical residuals still need exact/interval checking |
| MOSEK Python API | [official SDO tutorial](https://docs.mosek.com/latest/pythonapi/tutorial-sdo-shared.html) supports PSD matrix variables and LMIs; [solution formulation](https://docs.mosek.com/latest/pythonapi/prob-def.html) documents solution and infeasibility information | Commercial EULA; [official guidelines](https://docs.mosek.com/latest/pythonapi/guidelines-optimizer.html#the-license-system) require a valid license | Strong independent commercial benchmark and mature interior-point implementation | License/token availability prevents the offline default path; redistribution and reproducibility terms need review; numerical outputs still require independent rigorous certification |

## Adoption result

No adapter is adopted by this spike. The smallest later experiment should run
the same frozen real and complex fixtures through at least two independent SDP
engines, retain raw solver status/residuals and exact problem encodings, and
attempt rational/algebraic or interval reconstruction. A solver reporting
`optimal` may create only an untrusted candidate until this exact checker (or a
separately gated rigorous certifier) proves primal feasibility, dual
feasibility, and a closed gap.

The present noncommuting fixtures intentionally expose the blocker: simple
rational primal and dual points are feasible but leave an exact `1/4` gap.
Finding the irrational optimum for those pure-state pairs requires a numerical
solver or a separate symbolic derivation; accepting a tolerance-sized gap would
violate the benchmark's exact semantics.

## Authorization update (2026-08-21, ADR-0045)

The repository owner gave an explicit implementation request for the smallest
later experiment described above, restricted to **permissive licences only**:
Clarabel (Apache-2.0), SCS (MIT), CVXPY (Apache-2.0). **CVXOPT
(GPLv3-or-later) and MOSEK (commercial EULA) are out of scope and must not be
added, imported, or referenced as adopted.** The two CVXOPT/MOSEK rows above
therefore remain rejected candidates and are retained only as the record of why.

The authorization does not extend to Phase 5 integration, to enabling search
tiers 2--4, or to letting a numerical result carry a warrant.

### Resolved dependency closure

The owner restriction names three packages. Their actual transitive closure is
larger, and every member had to be licence-reviewed before installation. Fifteen
binary wheels resolved on CPython 3.14.4 / macOS ARM64 / pip 26.0.1, with no
source distribution and no extras selected. Their SHA-256 digests are pinned in
`requirements-phase5-sdp-comparison-py314-macos-arm64.txt`.

| Package | Declared licence | Why present |
|---|---|---|
| clarabel 0.11.1 | Apache-2.0 | authorized engine |
| scs 3.2.11 | MIT | authorized engine |
| cvxpy 1.9.2 | Apache-2.0 | authorized modelling layer |
| numpy 2.5.2 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | required by both engines |
| scipy 1.18.0 | BSD-3-Clause | CSC matrices required by the Clarabel API |
| cffi 2.1.1 | MIT-0 | Clarabel requirement |
| pycparser 3.0 | BSD-3-Clause | cffi requirement |
| osqp 1.1.3 | Apache-2.0 | unconditional cvxpy requirement |
| qdldl 0.1.9.post1 | Apache 2.0 | osqp/cvxpy requirement |
| highspy 1.15.1 | MIT | unconditional cvxpy requirement |
| sparsediffpy 0.3.0 | Apache-2.0 | unconditional cvxpy requirement |
| jinja2 3.1.6 | BSD-3-Clause | osqp requirement |
| MarkupSafe 3.0.3 | BSD-3-Clause | jinja2 requirement |
| joblib 1.5.3 | BSD-3-Clause | osqp requirement |
| setuptools 84.0.0 | MIT | osqp requirement |

**Licence finding that constrains installation.** CVXPY declares CVXOPT, MOSEK,
ECOS, Gurobi, XPRESS, COPT, CyLP and Knitro as *optional extras*
(`cvxopt; extra == "cvxopt"`, `Mosek; extra == "mosek"`,
`ecos; extra == "ecos"`, ...). None is installed because no extra is selected,
and the pinned manifest must always be installed with no extras. Three
independent controls back this up rather than relying on the manifest alone:
`engines.authorize_module` refuses every excluded name before any import;
`tests/test_repository_invariants.py` enumerates the complete set of gated
dynamic loads statically and would fail on an undeclared one; and the CVXPY
adapter refuses to run at all if `cvxpy.installed_solvers()` exposes an excluded
solver, and discards its own result if CVXPY selected any solver other than SCS.

### What the experiment found

Executed in a disposable environment outside the repository. Both engines
reported success on all three frozen fixtures (Clarabel `Solved`, CVXPY/SCS
`optimal`) and both landed within about `1e-11` of `(2 + sqrt(2))/4`.

**Neither result closed the gap.** Converting each engine's returned point to
the exact dyadic rationals it already is, and then applying the benchmark's
exact conditions, rejected every one of the six engine points: POVM completeness
was off by up to `297/36028797018963968`, complementarity was nonzero, and the
exact primal--dual gaps ranged over roughly `1e-14` to `1e-11` -- including one
SCS point whose exact gap was *negative*, i.e. exactly infeasible. A
tolerance-sized gap is not a closed gap.

What did close the gap was the exact reconstruction, which needs no solver: for
a two-outcome case in dimension two the optimum is attained by the spectral
projector onto the positive part of `W_1 - W_2`, the characteristic polynomial
is quadratic, so the whole certificate lives in `Q(sqrt(disc))` and is checked
by exact weak duality plus exact two-sided complementarity. That yields
`(2 + sqrt(2))/4` exactly for both noncommuting fixtures, with an exactly zero
gap, and reproduces the commuting control's known rational certificate of `1`.
It also proves the documented blocker exactly rather than numerically: the
rational candidate `3/4` falls short by exactly `(sqrt(2) - 1)/4`, and
**rational reconstruction fails**, because `1/2 + (1/4)sqrt(2)` is irrational
and no rational of any denominator equals it. That failure is recorded, not
dropped.

The engines therefore contributed corroboration and nothing else. Two engines
agreeing is not evidence of correctness -- they can share a formulation error, a
conditioning failure, or the same wrong optimum -- and the experiment's
disposition is derived only from the exact checks.

### Adapter adoption status, unchanged

Still no adoption. The adapters are spike-local, the engines are absent by
default, and an absent engine is a recorded missing-tool result. The residual
blocker for anything beyond this spike is unchanged and is now measured rather
than predicted: a floating-point interior-point or first-order point is not an
exact certificate, so a general noncommuting Phase 5 expansion needs either an
exact/interval certifier for shapes beyond two outcomes in dimension two, or a
separately gated rigorous certifier.
