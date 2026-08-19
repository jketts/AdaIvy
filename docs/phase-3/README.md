# Phase 3A Research-Memory Design Package

Status: proposed; no Phase 3 implementation exists.

This package deliberately reconciles, rather than silently replaces, the
blueprint's existing tool-focused Phase 3 roadmap.

- `ARCHITECTURE_PROPOSAL.md` — bounded vertical slice and roadmap conflict.
- `THREAT_MODEL.md` — untrusted-document, retrieval, citation, and replay risks.
- `ENTITY_SCHEMA_PROPOSAL.md` — immutable entities and separate canonical
  `ResearchMemoryExport` proposal.
- `REQUIREMENT_TEST_MATRIX.md` — proposed measurable acceptance tests.
- `IMPLEMENTATION_SEQUENCE.md` — entry gates, bounded work packages, stop line.
- `DEPENDENCY_LICENSE_ASSESSMENT.md` — parser candidates and corpus rights.
- `COST_ESTIMATE.md` — zero-API baseline and bounded local storage.
- `UNRESOLVED_DECISIONS.md` — decisions requiring human approval.
- `DEFERRED_WORK.md` — explicit non-goals.
- `BOUNDED_IMPLEMENTATION_PROMPT.md` — smallest implementation request after
  approvals.

Related proposed decisions are ADR-0012, ADR-0013, and ADR-0014. Until they are
accepted, `README.md`, `TECHNICAL_BLUEPRINT.md`, and `AGENTS.md` remain the
authoritative roadmap and Phase 2 stop line.
