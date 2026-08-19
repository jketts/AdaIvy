# Phase 3B Formal-Checker Entry Gate

Status: blocked before acquisition and checker execution

This package evaluates whether pinned Lean 4 plus mathlib can become AdaIvy's
first formal-checking backend. It contains design and measured prerequisite
evidence only. It does not contain a production domain model, migration,
orchestration path, model integration, proof generation, or quantum-specific
work.

- `ENTRY_GATE_REPORT.md` — outcome and entry evidence.
- `LEAN_MATHLIB_SCORECARD.md` — dimensional comparison with the file baseline.
- `PROPOSED_TOOLCHAIN_MANIFEST.json` — unacquired pin and dependency lock proposal.
- `LICENSING_DEPENDENCY_REPORT.md` — license and dependency findings.
- `FORMAL_CHECKER_THREAT_MODEL.md` — hostile-fragment boundary and controls.
- `TRUST_CLASSIFICATION_POLICY.md` — result meanings and promotion limits.
- `FIXTURE_RESULTS.md` — all twelve fixture outcomes, explicitly unexecuted.
- `REPRODUCIBILITY_EVIDENCE.md` — seals, probe results, and missing evidence.
- `RESEARCH_MEMORY_LINKAGE.md` — design-only future linkage.
- `BOOTSTRAP_COMMANDS.md` — exact operator-authorized acquisition commands.
- `BLOCKERS.md` — stop conditions and unblock criteria.
- `BOUNDED_IMPLEMENTATION_PROMPT.md` — proposed next bounded task.

The machine-readable summary is
`reports/phase-3b-entry-gate/entry-gate.json`. ADR-0015 proposes Lean as the
first backend only after this blocked gate is rerun successfully.
