# Phase 3A Research-Memory Design Package

Status: Phase 3A bounded implementation and acceptance evidence complete.

This package records the accepted Phase 3A/3B/4 sequence while preserving the
superseded revision-0.2 roadmap in ADR-0012 and version history.

- `ARCHITECTURE_PROPOSAL.md` — bounded vertical slice and roadmap conflict.
- `THREAT_MODEL.md` — untrusted-document, retrieval, citation, and replay risks.
- `ENTITY_SCHEMA_PROPOSAL.md` — immutable entities and separate canonical
  `ResearchMemoryExport` proposal.
- `REQUIREMENT_TEST_MATRIX.md` — implemented measurable acceptance tests.
- `IMPLEMENTATION_SEQUENCE.md` — entry gates, bounded work packages, stop line.
- `DEPENDENCY_LICENSE_ASSESSMENT.md` — parser candidates and corpus rights.
- `COST_ESTIMATE.md` — zero-API baseline and bounded local storage.
- `UNRESOLVED_DECISIONS.md` — resolved entry decisions and future deferrals.
- `DEFERRED_WORK.md` — explicit non-goals.
- `BOUNDED_IMPLEMENTATION_PROMPT.md` — smallest implementation request after
  approvals.
- `PHASE_3A_REPORT.md` — bounded implementation and acceptance evidence.

ADR-0012, ADR-0013, and ADR-0014 are accepted. README, blueprint, and
`AGENTS.md` carry the same bounded Phase 3A stop line.
Acceptance evidence is in `reports/phase-3a/acceptance-v1/`. Phase 3B and
Phase 4 remain unimplemented.
