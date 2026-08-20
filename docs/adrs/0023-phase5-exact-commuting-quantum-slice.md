# ADR-0023: Start Phase 5 with exact commuting quantum discrimination

- **Status:** accepted for the bounded Phase 5 implementation
- **Date:** 2026-08-20
- **Blueprint requirement:** Phase 5 adaptive search and quantum benchmark

## Decision

Implement the first executable `QD-FS-01` slice for diagonal weighted states
and diagonal POVMs using standard-library rational arithmetic. This is the
benchmark's classical/commuting tier, not a universal noncommuting result.
The independent optimum check is the exact diagonal primal/dual SDP reduction:
each coordinate is assigned to a maximal weight and the dual diagonal is the
coordinatewise maximum.

The deterministic tier-0 workflow includes prioritized verification and
falsification branches, duplicate-result dead-end detection, full failure
retention, and the exact QD-CE-01 boundary control. Search tiers 2--4 remain
behind recorded feature states and are disabled because no cost-adjusted gain
has been demonstrated. No model, network, numerical tolerance, or new
dependency is introduced.

Verified results remain checked findings with explicit applicability and
mathematical-warrant labels; they are not admitted to the trusted claim graph.
The exact boundary refutation activates the accepted material-partial-result
event and human steering contract through the existing semantic event store.
Source-derived evidence additionally requires current Phase 4A rights and a
checked applicable review.

## Consequences

Phase 5 is usable end to end for exact scalar and commuting cases and provides
a reproducible foundation for a later noncommuting SDP adapter. It does not
claim to resolve universal `QD-FS-01`, supply a noncommuting solver, or justify
higher search tiers.
