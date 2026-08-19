# ADR-0005: Separate Phase 1 trust entities from dossier JSON

- Status: accepted
- Date: 2026-08-19
- Deciders: repository maintainers
- Scope: Phase 1 trust core

## Context

The Phase 0 interchange fixture embeds `truth_status` and warrant snapshots in
claims. Architecture revision 0.2 instead requires immutable claims, orthogonal
warrants and verification records, and truth-like status derived by policy.
Using the Phase 0 JSON shape as the internal domain would silently preserve the
wrong ownership boundary.

## Decision

Implement frozen, typed standard-library entities with opaque IDs. Use explicit
mapping code for the Phase 1 canonical dossier JSON. Never deserialize JSON
directly into trusted repository state. Derived trust projections are excluded
from the canonical entity payload. Phase 0 schemas remain supported as
historical evaluation artifacts, not as the Phase 1 internal model.

External dossier and tool imports create proposal bundles. Hash-verified local
replay is a distinct operation that reconstructs an exported local dossier
without promoting foreign assertions.

## Consequences

The domain stays dependency-free and cannot accidentally store mutable
confidence or logical status. Mapping code is deliberately explicit and must be
kept under round-trip and schema tests. A future Pydantic/API boundary may wrap
the canonical mapping without changing the domain.

## Blueprint alignment and deviation

This follows revision 0.2's domain/interchange boundary. The only deliberate
departure from the suggested default is using validated dataclasses rather than
a Pydantic dependency in Phase 1; this keeps the offline slice minimal and does
not change the public schema contract.
