# ADR-0001: Canonical Phase 0 JSON interchange

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** §§4.20, 8.6, 11.5, and Phase 0 exit criteria
- **Decision owners:** Phase 0 implementer; researcher review pending

## Context

The blueprint requires a backend-neutral `ResearchDossier` containing accepted
state and explicit gaps. Phase 0 must freeze the minimum contract without
building production entities or persistence. The file baseline demonstrated a
lossless, byte-stable round-trip with semantic target, source-applicability,
obligation, failed-route, and verifier-isolation records intact. It scored 90.0
under the frozen rubric; its only hard gate is the repository’s unresolved
license.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt an external proof-state format | Albilich/MathGraph inventory and blockers | Existing workflow concepts | No tested common import; MathGraph license absent | Export and license not demonstrated |
| Adopt OMDoc/MMT as the full envelope | OMDoc projection scored 68.0 | Mature math-content concepts | Trust metadata is lossy without a sidecar; MMT has modification restrictions | License and complete round-trip |
| Build a small JSON envelope | File baseline and rejection fixtures pass | Exact, portable, deterministic, offline | Local schema must be maintained | Repository license unresolved |

## Decision

Use canonical UTF-8 JSON with JSON Schema plus explicit semantic validation as
the Phase 0 interchange. External results use a separate envelope and may return
only `proposal` artifacts. Canonical hashes set their own hash field to `null`
before serialization.

## Consequences

The contract is easy to replay and does not commit production storage to JSON.
JSON Schema cannot express all cross-reference and trust rules, so semantic
validation remains mandatory. Phase 1 may use schema primitives such as
Pydantic internally, but exported semantics and hashes must remain compatible.

## Blueprint deviation

None. The blueprint requires a backend-neutral dossier and calls Pydantic-style
schemas a default, not a Phase 0 dependency mandate.

## Validation and revisit trigger

Revisit on an external component demonstrating a complete, licensed, lower-cost
round-trip that preserves every hard invariant, or when version 1.0 interchange
compatibility is proposed.

