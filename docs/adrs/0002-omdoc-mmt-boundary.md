# ADR-0002: OMDoc/MMT is a mathematical-content interoperability boundary

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** §§3.3 and 22.2; representation-bridge correctness contract
- **Decision owners:** Phase 0 implementer; legal review pending

## Context

The local OMDoc-shaped projection preserved the exact target, claims, and open
obligations, but applicability records, warrant typing, failed-route details,
evaluation boundaries, and verifier-isolation metadata required the canonical
JSON sidecar. The projection scored 68.0 versus the file baseline’s 90.0. MMT’s
repository license permits redistribution without modification, which blocks a
normal modified/forked dependency path without legal clarification.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt OMDoc/MMT as canonical IR | Partial XML spike | Theory/morphism ecosystem | Lossy trust data | Licensing and fidelity |
| Wrap MMT | Inventory | Strong APIs | JVM/toolchain and modification terms | Not tested locally |
| Interoperate through projection | XML + sidecar replay | Reuses math-content concepts | Two linked artifacts | Must prevent divergence |
| Build an invented universal math syntax | No demonstrated need | Tailored fields | Duplicates standards | Rejected by blueprint |

## Decision

Keep `ResearchDossier` canonical and use OMDoc/MMT only as an optional
mathematical-content projection/interoperation surface. Unsupported trust data
must remain explicit in a content-hashed sidecar. Do not claim full OMDoc 1.2 or
MMT conformance from the Phase 0 projection.

## Consequences

Phase 1 does not need MMT. A later adapter needs conformance fixtures, sidecar
linking rules, and legal review. Representation maps remain first-class local
records rather than being inferred from a theory morphism.

## Blueprint deviation

None. The blueprint explicitly treats OMDoc/MMT concepts as design references.

## Validation and revisit trigger

Revisit when a real MMT server round-trip is locally reproducible and the
license permits the intended packaging and modifications.

