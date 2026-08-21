# Noncommuting SDP adapter comparison

Status: design-only adoption spike; reviewed 2026-08-20. No package was
downloaded, imported, invoked, or selected for production.

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

## Addendum, 21 August 2026 (ADR-0033)

The paragraph above still describes the two rational-candidate fixtures, which
are retained unchanged. It is no longer the whole picture, and the sentence
"requires a numerical solver or a separate symbolic derivation" was too strong
in one direction: the second disjunct was taken, with no dependency.

The `1/4` gap on the two noncommuting pure-state pairs is now closed to exactly
zero by project-authored certificates written over one real quadratic extension
of the rationals, checked by the exact arithmetic in `algebraic.py`. No adapter
was adopted, no solver was called, no float was introduced, and no tolerance
exists anywhere on the path. The adoption result above is unchanged: still no
package.

Two things this does not do. It does not *search*: the certificates were
derived by hand from the two-state closed form and the checker only verifies
them, so a case with no closed form still has no route to a candidate. And it
does not extend to every instance -- see the measured `real-noncommuting-irreducible-cubic-boundary`
fixture, whose optimum is provably outside every quadratic extension. That case
is exactly the one where an SDP adapter would still be the only route to a
candidate, so the comparison table above remains live for it.

## Authorization update, 21 August 2026 (ADR-0045)

The bounded comparison experiment admits only Clarabel (Apache-2.0), SCS
(MIT), and CVXPY (Apache-2.0), with their permissively licensed transitive
closure pinned in `requirements-phase5-sdp-comparison-py314-macos-arm64.txt`.
CVXOPT, MOSEK, and every unapproved CVXPY extra remain excluded. The adapters
are spike-local and absent by default.

Both permitted engines reported numerical success on the three comparison
fixtures, but exact conversion rejected every returned floating-point point:
the residuals were small, not zero. The engine-independent exact
reconstruction closed the bounded two-outcome, dimension-two cases over a
quadratic field. Thus the experiment corroborates the formulation but adopts
no engine, grants no warrant, enables no search tier, and does not expand the
production Phase 5 scope.
