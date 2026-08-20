# ADR-0024: Use a local frozen confirmatory slice for Phase 6

- **Status:** accepted for the bounded Phase 6 implementation
- **Date:** 2026-08-20
- **Blueprint requirement:** Phase 6 confirmatory evaluation and hardening

## Decision

The first Phase 6 implementation confirms one preregistered exact
commuting/diagonal `QD-FS-01` case. A content-hashed protocol freezes the case,
method, metrics, capability allowlist, success criteria, and one-pass stopping
rule before execution. The evaluator receives only the named held-out case,
records one access, permits no adaptation, and requires an existing Phase 5
run plus its material-result trace.

The generality suite executes five deterministic trust controls: unsupported
model consensus, finite-experiment overreach, a mistranslated formal target,
an inapplicable source, and an open representation bridge. Phase 6 reports its
measured improvement over the arithmetic-only baseline as those additional
trust-boundary rejections, with zero external spend and zero extra expert
actions.

Novelty and significance are recorded as `not_assessed`; contribution records
separate human protocol freezing, exact tool computation, and system
verification. A canonical release package binds the Phase 5 export, protocol,
confirmatory result, controls, assessments, contributions, and limitations for
restart and clean-room replay.

## Consequences

This is a complete local confirmatory workflow without credentials, network,
models, or new dependencies. It does not claim held-out generality beyond the
single frozen case, universal noncommuting convergence, automated novelty or
significance assessment, or publication readiness.
