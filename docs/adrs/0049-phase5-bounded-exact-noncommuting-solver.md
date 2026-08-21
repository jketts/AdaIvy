# ADR-0049: Activate bounded exact noncommuting certificate discovery

- **Status:** accepted and implemented 21 August 2026
- **Date:** 2026-08-21
- **Blueprint requirement:** Phase 5 independent SDP comparison and exact
  verification; ADR-0029 bounded activation; ADR-0035 exact certificate checker;
  ADR-0045 engine-comparison evidence
- **Decision owners:** repository owner

## Context

ADR-0035 deliberately stopped at verifying human-supplied noncommuting
certificates. ADR-0045 subsequently measured a genuine solver-shaped path: for
two outcomes in dimension two the positive spectral projector of `W0-W1` and
the dual `Gamma = W1 + (W0-W1)_+` can be constructed exactly. That spike closed
the noncommuting rational `1/4` gaps without trusting a numerical status or a
tolerance. The owner has now explicitly requested completion of Phase 5,
including solver/discovery rather than verification alone.

A broad SDP solver is still not justified. The repository has evidence for one
small exact family, while its retained dimension-three fixture proves that the
quadratic field cannot represent every ordinary noncommuting optimum. The
correct promotion is therefore the measured bounded construction, not a claim
of general noncommuting coverage.

## Decision

Add `math_research.phase5.solver`, a production exact solver with these fixed
bounds:

- exactly two outcomes;
- exactly two-dimensional Hermitian weighted states;
- one measured field `Q(sqrt(d))(i)` per case;
- no float, tolerance, numerical engine, model call, or network call;
- deterministic tier 0 only; search tiers 2--4 remain disabled.

The solver computes the characteristic discriminant of `W0-W1`, constructs its
positive spectral projector exactly, and derives a primal POVM and dual
operator. This is genuine discovery: a case with no supplied certificate can
now acquire a generated candidate. It is not self-verification. The generated
object crosses a distinct `bounded_exact_solver_candidate_boundary`, records a
system principal, and is passed to ADR-0035's existing exact checker. Only exact
primal feasibility, dual feasibility, a zero primal-dual gap, and exact
two-sided complementarity produce the
`exact_noncommuting_certificate_verification` warrant. A rejected candidate
produces no warrant.

The old supplied-certificate command and schemas do not change. In particular,
ADR-0035 remains true for that path: it still accepts human inputs only and
still never discovers them. Solver results have additive v1 schemas and state
`optimum_discovered` explicitly. They may not be mistaken for the old
`unproducible_coverage_status` field, which remains a contract of the old
verification-only report.

Every unsupported or unrepresentable case is retained. A case outside the
fixed outcome/dimension shape reports `unresolved_unsupported_shape`; a
quadratic construction requiring a higher field reports
`unresolved_outside_represented_field`; and a constructed candidate rejected by
the exact checker reports `candidate_refuted_by_exact_verifier`. None is a pass.
The dimension-three irreducible-cubic fixture therefore remains visible and
unresolved in every acceptance run.

## Alternatives rejected

- **Promote a numerical engine status.** Rejected: `optimal` and small residuals
  are candidate evidence, not an exact mathematical warrant.
- **Reconstruct approximately with a tolerance.** Rejected: this would break
  the exact Phase 5 contract.
- **Call the scalar closed-form cross-check a solver.** Rejected: a scalar is
  not a primal/dual certificate. The activated path constructs both operators
  and passes the independent exact checker.
- **Claim general noncommuting SDP support.** Rejected: the cubic fixture is a
  concrete counterexample to that scope.

## Consequences and measured acceptance

The frozen eight-case production fixture produces seven
`discovered_and_exactly_verified` results, including the previously withheld
certificate and both rational candidates that formerly retained a `1/4` gap.
The dimension-three irreducible-cubic case remains
`unresolved_unsupported_shape`. The result is deterministic and content-hashed.

`make check` runs the solver offline and asserts both sides of this outcome. The
acceptance suite also substitutes a rejecting verifier to prove construction
alone cannot claim discovery, checks a deliberately invalid generated
certificate through the shared exact verifier, exercises the CLI, and scans the
solver for float/model/network/third-party paths.

## Revisit triggers

A new ADR is required before widening outcome count or dimension, adding a
numerical/interval reconstruction acceptance path, enabling a higher search
tier, or claiming general noncommuting JRF convergence. Numerical engines in
ADR-0045 remain optional proposal generators in a disposable environment; no
engine dependency is adopted into production by this decision.
