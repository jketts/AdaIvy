# Phase 1 Implementation Plan

Phase 1 is limited to the trust core and one manual in-memory vertical slice.

1. Correct the Phase 0 scorecard through a derived, dimensional interpretation
   while preserving the raw result bytes and observations.
2. Define frozen typed entities, opaque IDs, append-only repositories/events,
   and policy projections for logical status and target resolution.
3. Define a separate Phase 1 dossier interchange schema with deterministic
   canonical JSON, explicit versions, content hashes, validation, trusted local
   replay, and proposal-only external import.
4. Build five bounded fixtures and the required adversarial tests around the
   same policy surface.
5. Add a manual CLI that creates and inspects a complete valid-theorem dossier,
   exports and re-imports it, and renders an ID-traceable report.
6. Run Phase 0 compatibility checks plus all Phase 1 schema, unit, adversarial,
   integration, CLI, and report-consistency checks. Stop before Phase 2.

No database, ORM, network, crawler, model, external proof tool, worker, UI,
multi-agent orchestration, or quantum-specific solver is included.
