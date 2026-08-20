# Material Partial Result Surfacing v1

Status: **normative architecture contract; production activation deferred**

This document defines the earliest safe interface for material partial-result
surfacing. It is additive to the passed Phase 4 entry gate and the Phase 4A
production implementation now present in ancestry. It does not alter or
authorize the Phase 4A rights/applicability slice and is not evidence that a
production material-result producer, endpoint, migration, notification path,
or persistence path exists.

## Requirement

Whenever independently verified work materially refutes, restricts,
strengthens, generalizes, or redirects an active research objective, AdaIvy must
append and expose a steerable research event even when the requested objective
remains incomplete.

A material result would reasonably change the user's understanding of the
objective or choice of what to investigate next. An ordinary progress update,
intermediate lemma, failed attempt, speculative observation, retrieved claim,
model agreement, or unverified proposal is not a material partial result.

## Integration and record model

The production integration point is the existing append-only semantic event
stream and run timeline keyed by the durable Phase 2 run and Phase 1
`ResearchProblem`. The contract defines three immutable record envelopes:

| Schema | Semantic event | Purpose |
|---|---|---|
| `schemas/material-partial-result-event-v1.schema.json` | `research.material_partial_result_surfaced` | Append the verified result exactly once. |
| `schemas/material-partial-result-steering-action-v1.schema.json` | `research.material_partial_result_steering_recorded` | Append a later human steering choice. |
| `schemas/material-partial-result-lifecycle-v1.schema.json` | `research.material_partial_result_lifecycle_recorded` | Append correction, supersession, or invalidation caused by later evidence state. |

These are typed payloads in the existing semantic stream, not a notification,
provenance, authority, steering, lifecycle, or status subsystem. A current view
is a deterministic projection of the original event plus ordered steering and
lifecycle records. The original event never embeds later records and is never
rewritten. Acknowledgement and dismissal affect presentation only; lifecycle
records affect current validity but retain the original event and its causal
history.

## Exact result identity

The event binds a result to all of the following:

- non-empty statement, object identity, and domain;
- objective, run, and optional branch;
- the ordered canonical evidence-reference snapshot and its SHA-256 digest;
- a named canonicalization version; and
- a result digest computed over the statement, object, domain, objective, run,
  branch, evidence snapshot, and canonicalization version.

Every evidence reference carries its local record ID, kind, and stored content
hash. Acceptance resolves the record and requires the hash to match, the record
to belong to the same objective/run, and its effective lifecycle, rights, and
ApplicabilityReview state to permit use. Deleted, suppressed, revoked,
withdrawn, inapplicable, or unresolved evidence fails closed.

Every verification record must independently verify the same result digest,
objective, run, evidence set, method, and policy identity/version. Every
materiality assessment must name the same result digest, objective, and policy.
Causal parents must resolve to allowed semantic record types in the same
objective/run. Bare membership in an untyped ID set is insufficient.

Allowed verification method labels are `human_review`,
`deterministic_check`, `formal_kernel`, `rigorous_certificate`, and
`exact_counterexample`. The resolved policy, not the label alone, decides
whether the method is sufficient. Retrieval, out-of-scope experiments, model
agreement, and confidence scores never satisfy verification.

## Event envelope

The event contains a stable event ID and semantic idempotency key; active
objective/run/branch identities; exactly one material classification; exact
result identity; materiality explanation and assessment ID; content-addressed
evidence references; verification record references; originating and creating
principal IDs; creating capability; timestamp; causal parents; policy
identity/version; `main_objective_incomplete: true`; and all five available
steering actions.

The event is immutable after acceptance. Reimporting exactly the same event ID,
idempotency key, and canonical content returns the accepted snapshot. Reusing
either identity with different content fails closed.

## Authority and capabilities

Trusted context resolves principals through the established Phase 4A
`ActorKind` values (`human`, `automation`, `model`, `system`) and `Authority`
values (`source_provenance`, `human_final`, `proposal`,
`deterministic_policy`). This contract defines no parallel authority enum.

`surface_verified_result`, `steer_research`, and
`review_result_lifecycle` are named capabilities. A capability record binds one
operation to one authenticated principal. Steering and lifecycle envelopes
record the effective Phase 4A actor kind and authority for audit, but acceptance
re-resolves the principal and requires exact equality; the recorded values
cannot authorize themselves. A surfacing creator must resolve to an authorized
`human_final` or `deterministic_policy` principal. Steering and lifecycle review
are human-only: the principal must resolve to both Phase 4A `human` actor kind
and `human_final` authority. A model or system cannot relabel itself human by
changing payload bytes. Phase 4A's human-only final ApplicabilityReview
authority remains controlling and unchanged.

Origin and creation authority are distinct. A model may originate a proposal
that later becomes independently verified, but it cannot verify or authorize
its own material event merely by being the origin.

## Steering action envelope

A steering action is appended only after its target material-result event is
accepted and still valid. It contains:

- stable action ID and idempotency key;
- target event, objective, run, and branch identities;
- one of `continue_objective`, `investigate_result`, `redirect_objective`,
  `acknowledge`, or `dismiss`;
- authenticated principal, trusted effective Phase 4A actor kind/authority,
  and granted `steer_research` capability IDs;
- timestamp, policy identity/version, causal predecessor, and strict integer
  sequence; and
- optional target objective/branch, required for an investigation or redirect
  and prohibited for the other actions.

The first action causally follows the immutable result event. Each later action
follows the prior action with the next sequence number. Redirect targets must
resolve to existing active permitted objectives or branches with consistent
identity. The old objective is never mutated. Exact replay is idempotent;
identity or idempotency-key reuse with changed content fails closed.

## Lifecycle correction and invalidation

Phase 4A source lifecycle, rights decisions, and ApplicabilityReview records
remain authoritative. A later correction, supersession, revocation, takedown,
deletion, withdrawal, rights-applicability change, or unresolved/rejected
ApplicabilityReview deterministically re-evaluates every dependent material
event. It appends a lifecycle record to the same semantic stream; it does not
mutate the event or create a parallel status store.

The lifecycle record names the target event, objective/run, change kind,
derived state (`corrected`, `superseded`, or `invalidated`), affected evidence,
source lifecycle records, applicability reviews, trusted reviewer capability,
reason, timestamp, causal predecessor, policy, and sequence. Supersession alone
requires a resolvable superseding event. The first lifecycle record causally
follows the original event and later records form an ordered chain.

Current validity is derived from the last accepted lifecycle record. A result
whose evidence has become ineligible cannot support a new surfacing event or a
new steering action. Correction never overwrites the old statement or evidence;
a corrected result is a new event linked through lifecycle causality.

## Closed raw-byte acceptance boundary

Creation, import, replay, restart, and fresh-process recovery must traverse one
strict boundary in this order:

1. reject more than 2,097,152 bytes before decoding or materializing an
   unbounded payload;
2. decode UTF-8 and JSON strictly, rejecting malformed JSON, duplicate object
   keys, and non-finite numbers;
3. validate the applicable Draft 2020-12 closed schema, including its strict
   timestamp offset pattern;
4. reject missing or unknown properties at every object level, empty or
   malformed identifiers/idempotency keys, malformed hashes/policies,
   timezone-less or invalid RFC-3339 timestamps, wrong constants/enums, boolean
   values used as integers, bounds violations, duplicate references, and failed
   conditional or union constraints;
5. resolve objective, run, branch, principal, capability, policy, exact result,
   materiality, verification, evidence, causal, event, and redirect references
   against typed accepted local state;
6. enforce active/permitted identity relationships, independent verification,
   Phase 4A rights/applicability/lifecycle eligibility, human-only operations,
   and append-only causal sequence;
7. verify the canonical content hash last; and
8. return a detached accepted snapshot before an atomic semantic commit.

The JSON Schemas enforce interchange shape and timestamp lexical form. Because
Draft 2020-12 `format` is annotation-only unless a format vocabulary and
implementation are explicitly enabled, this contract does not pretend that an
unavailable optional format plugin validates dates. The executable contract's
handwritten semantic boundary separately calendar-validates strict RFC-3339
timestamps and resolves semantic references; neither check is represented as
standards-conforming JSON Schema validation. The schema oracle must run under
the owner-approved standards-conforming validator and must not be counted as
passing if skipped.

Canonical JSON is UTF-8 with sorted keys, no insignificant whitespace, and no
non-finite values. Each envelope's `content_hash` is SHA-256 over the canonical
envelope with the `content_hash` member omitted. All arrays and strings use the
smaller bounds declared in the schemas; an action or lifecycle chain is limited
to 256 records.

The active job/run deadline must be checked throughout reading, validation,
reference resolution, hashing, persistence, export, and replay. Export must
incrementally encode, count, hash, and write within the existing
67,108,864-byte Phase 4 output ceiling and publish atomically only after full
verification.

## Deferred application boundary

A later application boundary may expose these operations without requiring a
specific UI:

```text
list_material_partial_results(run_id, state_filter, cursor, limit)
get_material_partial_result(event_id)
record_material_partial_result_action(event_id, action, principal,
                                      capability_id, idempotency_key,
                                      optional_target_id)
```

No such endpoint is activated here. The existing Phase 4A SQLite schema,
repository, export/import, CLI, and trust path do not produce, persist, or
accept these record types. Activation requires a new owner-approved production
gate and production-path tests for bounded import/export, persistence, replay,
restart, deduplication, exact semantic binding, Phase 4A lifecycle integration,
and projections. It must use the existing event-store abstraction and must not
reinterpret Phase 0-3B exports.

## Acceptance contract

`tests/test_material_partial_result_contract.py` is an executable
preproduction model, not a production-path test. Its vectors freeze these
invariant groups:

1. a verified event accepts all five material classifications while leaving the
   parent objective incomplete;
2. steering is appended only after the immutable event, exact replay is
   idempotent, and projection is deterministic;
3. conflicting event/action identities and idempotency keys fail closed;
4. model and system principals cannot self-declare human authority;
5. exact result, materiality, verification, evidence, causal, and policy
   bindings reject substitutions;
6. deleted, suppressed, revoked, withdrawn, rights-blocked, and inapplicable
   evidence is ineligible;
7. dangling event, causal, investigation, and redirect targets fail closed;
8. every schema constraint class is mutation-tested, including closure,
   required fields, formats, patterns, arrays, enums, constants, numeric types,
   unions, and conditionals;
9. correction, deletion, revocation, and applicability reversal append
   lifecycle records and deterministically invalidate without mutation;
10. malformed, duplicate-key, non-finite, invalid UTF-8, and oversized raw
    envelopes fail closed; and
11. authoritative Phase 4 gate evidence and all frozen prior contracts remain
    byte-identical.

The same vectors must pass with zero schema/oracle skips against the actual
production service, SQLite adapter, canonical export/import, and fresh-process
restart before this feature can be called implemented.
