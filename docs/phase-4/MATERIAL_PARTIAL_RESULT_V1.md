# Material Partial Result Surfacing v1

Status: **normative architecture contract; production activation deferred**

This document defines the earliest safe interface for material partial-result
surfacing. It is additive to the passed Phase 4 entry gate. It does not alter or
authorize the Phase 4A rights/applicability production slice and is not evidence
that a production notification or persistence path exists.

## Requirement

Whenever independently verified work materially refutes, restricts,
strengthens, generalizes, or redirects an active research objective, AdaIvy must
append and expose a steerable research event even when the requested objective
remains incomplete.

A material result would reasonably change the user's understanding of the
objective or choice of what to investigate next. An ordinary progress update,
intermediate lemma, failed attempt, speculative observation, retrieved claim,
model agreement, or unverified proposal is not a material partial result.

## Integration point

The production integration point is the existing append-only semantic event
stream keyed by the durable Phase 2 run and the Phase 1 `ResearchProblem`.
`research.material_partial_result_surfaced` is an immutable semantic event, not
a mutable notification and not a new trust projection. The event references
existing verification/evidence/proof artifacts; it does not create a warrant.

Steering is recorded separately as
`research.material_partial_result_steering_recorded`. Current acknowledgement,
dismissal, and selected direction are projections over the ordered steering
records. Reprocessing the same IDs and canonical content is idempotent;
reusing an ID or idempotency key for different content fails closed.

## Normative envelope

`schemas/material-partial-result-event-v1.schema.json` defines the canonical
interchange envelope. Its semantic content contains:

- stable event ID and semantic idempotency key;
- active objective and research-run IDs;
- one classification: `refutes`, `restricts`, `strengthens`, `generalizes`, or
  `redirects`;
- a concise result statement and materiality explanation;
- at least one evidence, certificate, proof, or verified-artifact reference;
- verification status `verified`, a named method, and verification-record IDs;
- originating actor and the separately authorized event creator;
- creation time and bounded causal/parent references;
- `main_objective_incomplete: true`;
- all five available steering actions; and
- append-only steering records, including acknowledgement and dismissal.

Canonical hashing covers all semantic fields except the envelope hash itself.
Operational sequence numbers, database rows, delivery attempts, display state,
and elapsed time are not event identity. They remain separately auditable in
the production event store.

## Creation and acceptance rules

Creation, import, replay, restart, and fresh-process recovery must all traverse
one strict raw-byte acceptance boundary in this order:

1. reject more than 2,097,152 input bytes before decoding or materializing an
   unbounded payload;
2. decode UTF-8 and JSON strictly, rejecting duplicate keys and non-finite
   values;
3. validate the exact closed v1 envelope and field bounds;
4. resolve every actor, authority, objective, run, evidence, verification,
   causal, and steering reference against accepted local state;
5. require the objective to be active and the run to belong to it;
6. require applicable independent verification and prohibit a proposal from
   presenting itself as verified;
7. require explicit materiality assessment under the recorded policy;
8. validate unique IDs, idempotency keys, append-only steering order, and
   causal acyclicity;
9. verify the canonical envelope hash last; and
10. return a detached accepted snapshot before an atomic semantic commit.

The active job/run deadline must be checked throughout reading, validation,
reference resolution, hashing, persistence, export, and replay. A check after
execution is not deadline enforcement. Export must incrementally encode, count,
hash, and write within the existing 67,108,864-byte Phase 4 output ceiling and
publish atomically only after complete verification.

The v1 envelope permits at most 256 steering records, matching the accepted
Phase 4 record bound. Strings and reference collections have the smaller limits
declared in the schema. The envelope carries references, not unbounded proof or
source payloads.

## Authority and verification

The originating actor may be human, model, tool, formal system, external
system, or system process. The event creator must be a named human or system
principal with `surface_verified_result` authority. Origin and creation
authority are distinct: a model may originate a proposal that later becomes
independently verified, but it cannot authorize or verify its own material
event.

At least one referenced verification record must apply to the exact result and
active objective. Allowed method labels are `human_review`,
`deterministic_check`, `formal_kernel`, `rigorous_certificate`, and
`exact_counterexample`. The trust policy, not the label alone, decides whether
the method is sufficient. Retrieval, experiments outside their valid scope,
model agreement, and confidence scores never satisfy this rule.

## Steering interface for later user-facing work

The application boundary must eventually expose these operations without
requiring a specific UI:

```text
list_material_partial_results(run_id, state_filter, cursor, limit)
get_material_partial_result(event_id)
record_material_partial_result_action(event_id, action, actor, authority,
                                      idempotency_key, optional_target_id)
```

Actions are:

- `continue_objective` — retain the active objective and continue research;
- `investigate_result` — open or select a bounded investigation linked to the
  surfaced event;
- `redirect_objective` — create/select a new objective version through the
  existing human-authority workflow;
- `acknowledge` — mark the event seen without changing research direction; and
- `dismiss` — suppress current presentation without deleting history.

Redirect never mutates the old objective. Continue, acknowledge, and dismiss do
not complete it. An authorized later action may supersede a prior steering
choice while retaining the full chain.

## Production activation boundary

No current Phase 4 production schema, migration, repository, export, or CLI
exists to host this event safely. The generic Phase 2 `semantic_events` table
does not itself validate actors, authorities, verification eligibility, or
event-specific replay semantics. Runtime activation is therefore assigned to a
new owner-approved production gate after, or explicitly alongside, Phase 4A.

That gate must decide whether the event rows remain in the general semantic
event table with typed payload repositories or receive additive tables behind
the same event-store port. It must not create a parallel event framework or
reinterpret Phase 0-3B exports.

## Acceptance contract

`tests/test_material_partial_result_contract.py` is an executable preproduction
contract, not a production-path test. It freezes these required cases:

1. verified refutation surfaces while the parent remains incomplete;
2. all five classifications are accepted;
3. ordinary intermediate work is ineligible;
4. unverified proposals are rejected;
5. missing or altered actor/authority data is rejected at creation, import,
   replay, and restart boundaries;
6. evidence and verification references round-trip;
7. stable identity deduplicates replay/restart;
8. acknowledgement and steering history round-trip;
9. surfacing never completes the parent objective;
10. malformed, duplicate-key, oversized, and over-record-limit envelopes fail
    closed; and
11. the passed Phase 4 gate hashes and prior contracts remain unchanged.

The same cases must be rerun against the actual production service, SQLite
adapter, canonical export/import, and fresh-process restart before the feature
can be called implemented.
