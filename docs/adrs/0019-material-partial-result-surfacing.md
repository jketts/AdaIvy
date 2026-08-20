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

At the time of the original decision, the Phase 4 entry gate had passed but the
approved Phase 4A production implementation did not yet exist. Adding an active
trusted event path then would have introduced a new record meaning, authority
check, and production interface beyond ADR-0017 and ADR-0018.

### Current integration context

Phase 4A now exists in this branch's ancestry. Its durable persistence,
verified export/import/replay, restart recovery, rights decisions,
ApplicabilityReview records, and source lifecycle are authoritative. ADR-0019
integrates with those capabilities; it does not predate, replace, or weaken
them. Material-result production activation remains deferred because Phase 4A
does not produce or accept the three ADR-0019 record types.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Treat the result as progress text | Existing reports and timelines | No new contract | Not durable, steerable, or reliably visible | Rejected |
| Add a separate notification subsystem | No production UI exists | Familiar UI model | Duplicates event identity, persistence, replay, and deduplication | Rejected |
| Extend the existing semantic-event/run model | Phase 2 append-only events and run identity | Reuses durable causality and idempotency | Needs event-specific authority and replay validation | Selected |
| Activate the event in the approved Phase 4A slice now | Phase 4A did not then have a production implementation | Immediate runtime path | Expands the approved gate and trusted boundary | Prohibited without a new gate decision |

## Decision

Add correctness invariant C16 and the normative contract in
`docs/phase-4/MATERIAL_PARTIAL_RESULT_V1.md`. A material partial result is an
immutable semantic event classified as exactly one of `refutes`, `restricts`,
`strengthens`, `generalizes`, or `redirects`. It references an active objective
and run, an exact content-addressed result identity, independent verification,
eligible evidence or certified artifacts, originating principal, authorized
creator capability, causality, and an explicit assertion that the main
objective remains incomplete.

The event reuses the existing append-only semantic event abstraction and run
timeline. User actions are separate immutable append-only steering records.
They can continue the objective, investigate the result, redirect the
objective, acknowledge the event, or dismiss its current presentation.
Acknowledgement or dismissal never deletes or rewrites the event. Stable event
and action IDs plus idempotency keys define deduplication.

Source correction, supersession, revocation, takedown, deletion, withdrawal,
changed rights applicability, and unresolved or rejected applicability review
are represented by separate append-only lifecycle records. The current
validity and steering view is a deterministic projection of the original event
plus later lifecycle and steering records. No record mutates the original.

Actor kind and authority are resolved from trusted Phase 4A context using its
existing `ActorKind` and `Authority` vocabularies. `surface_verified_result`,
`steer_research`, and `review_result_lifecycle` are capabilities, not new
authority values. Human-only steering and lifecycle review require a trusted
human principal with Phase 4A `human_final` authority; an envelope cannot
self-authorize by changing its recorded effective actor kind or authority.
Acceptance re-resolves both from the trusted principal. Phase 4A's human-only
final applicability authority remains unchanged.

This change establishes closed schemas and executable contract vectors only.
It does not create a production table, migration, repository, service, CLI
command, notification channel, or trust promotion. The next owner-approved
production gate that activates the contract must bind trusted
principal/capability resolution, exact result identity, materiality,
verification, evidence applicability and lifecycle, incremental bounded
import/export, persistence, replay, restart, deduplication, and deterministic
steering/lifecycle projection to the actual production path.

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
deferred because the Phase 4A production layer does not implement this event,
steering-action, or lifecycle contract and has not been authorized to do so.

## Validation and revisit trigger

Keep this decision only while the closed schemas and contract tests cover all
five classifications, exact result/evidence/materiality/verification binding,
trusted actor/capability rejection, replay/restart deduplication, separately
appended steering, lifecycle invalidation, incomplete parent status, and the
bounded fail-closed raw boundary. Revisit before runtime activation, or if the
implementation would require a parallel event/status store, a new authority
type, weaker verification, a larger resource boundary, or modification of the
passed Phase 4 gate evidence.
