# ADR-0019: Surface verified material partial results as durable research events

- **Status:** accepted
- **Date:** 2026-08-20
- **Blueprint requirement:** C16, research lifecycle, event vocabulary, and Phase 4 production boundary
- **Decision owners:** repository owner and researcher

## Context

AdaIvy already preserves negative results, proposals, verification records,
warrants, run state, and append-only semantic events. It does not yet define a
durable user-facing event for verified work that materially changes the meaning
or direction of an active objective while leaving that objective incomplete.
Without that contract, a refutation, restriction, strengthening,
generalization, or redirection can remain buried in a run timeline until final
reporting.

The Phase 4 entry gate is passed, but its approved production boundary contains
only the five Phase 4A rights and applicability concepts. Phase 4 production
persistence, export, replay, restart, and user interfaces do not exist. Adding
an active trusted event path to that gate would introduce a new record meaning,
authority check, and production interface beyond ADR-0017 and ADR-0018.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Treat the result as progress text | Existing reports and timelines | No new contract | Not durable, steerable, or reliably visible | Rejected |
| Add a separate notification subsystem | No production UI exists | Familiar UI model | Duplicates event identity, persistence, replay, and deduplication | Rejected |
| Extend the existing semantic-event/run model | Phase 2 append-only events and run identity | Reuses durable causality and idempotency | Needs event-specific authority and replay validation | Selected |
| Activate the event in the approved Phase 4A slice now | Phase 4A has no production implementation | Immediate runtime path | Expands the approved gate and trusted boundary | Prohibited without a new gate decision |

## Decision

Add correctness invariant C16 and the normative contract in
`docs/phase-4/MATERIAL_PARTIAL_RESULT_V1.md`. A material partial result is an
immutable semantic event classified as exactly one of `refutes`, `restricts`,
`strengthens`, `generalizes`, or `redirects`. It references an active objective
and run, independent verification, evidence or certified artifacts, originating
actor, authorized creator, causality, and an explicit assertion that the main
objective remains incomplete.

The event reuses the existing append-only semantic event abstraction and run
timeline. User actions are separate append-only steering records. They can
continue the objective, investigate the result, redirect the objective,
acknowledge the event, or dismiss its current presentation. Acknowledgement or
dismissal never deletes or rewrites the event. Stable event and action IDs plus
idempotency keys define deduplication.

This change establishes a schema and executable contract vectors only. It does
not create a production table, migration, repository, service, CLI command,
notification channel, or trust promotion. The next owner-approved production
gate that activates the contract must bind actor and authority resolution,
verification eligibility, incremental bounded import/export, persistence,
replay, restart, deduplication, and steering-state projection to the actual
production path.

## Consequences

- Verified material progress becomes a first-class architectural outcome rather
  than final-report-only prose.
- Ordinary progress, intermediate lemmas, failed attempts, and speculative or
  unverified observations remain outside the event.
- The parent objective cannot become complete as a side effect of surfacing the
  event.
- Later UI work receives a stable query/command contract without dictating a
  notification design.
- The accepted Phase 4 entry-gate artifacts remain byte-identical and their
  production authorization remains unchanged.
- The feature is not production-complete until the deferred activation checks
  pass on a newly approved production boundary.

## Blueprint deviation

None. The decision extends the existing negative-result, human-authority,
append-only event, and idempotent orchestration rules. Runtime activation is
deferred because the appropriate Phase 4 production layer does not yet exist.

## Validation and revisit trigger

Keep this decision only while the schema and contract tests cover all five
classifications, verified-only creation, actor/authority rejection, evidence
round trips, replay/restart deduplication, durable steering history, incomplete
parent status, and bounded raw input. Revisit before runtime activation, or if
the implementation would require a parallel event store, a new authority type,
weaker verification, a larger resource boundary, or modification of the passed
Phase 4 gate evidence.
