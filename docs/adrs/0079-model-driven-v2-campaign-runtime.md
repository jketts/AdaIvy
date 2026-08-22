# ADR-0079: Model-driven v2 campaign runtime

- **Status:** accepted
- **Date:** 2026-08-22
- **Plan slice:** `docs/CAMPAIGN_DEPTH_AND_BREADTH_PLAN.md` Slice 12
- **Supersedes in part:** ADR-0065's model-only v1 vocabulary and ADR-0076's
  fixture-closure-only v2 orchestration
- **Decision owners:** repository owner

## Context

The v1 operator runner could call a live model but could not select literature
operations. The v2 end-to-end runner could execute those operations but only
from a preconstructed list of Python closures. This split prevented one
model-directed campaign from iterating over discovery, corpus refresh,
experimentation, and exact verification. The live `ask_user` action also had no
same-campaign continuation path.

## Decision

`ModelDrivenEndToEndCampaignRunner` consumes one v2 structured action from a
planner for each sequence and resolves that action through a closed
`RuntimeEffectRegistry`. `GatewayCampaignPlanner`, when supplied the v2 schema,
uses the v2 prompt addendum and can restore its transcript and measured usage
from completed planner checkpoints.

Planner calls and operation effects have separate append-only checkpoint
namespaces. A planner call is treated as paid by default. Every intent is
durable before its effect; a completed terminal replays without repeating the
effect; an orphaned paid or irreversible intent stops unresolved. Local
idempotent operations may retry under the same idempotency key. Literature
adapters may execute synchronously, but they cross this same durable job
boundary.

The literature ladder is now a repeatable cycle. Search starts a cycle;
optional depth-one following requires its allowlist; acquisition, parsing,
embedding, refresh, and retrieval preserve their causal order. A new search
may start after research. Retrieval must name a generation or projection that
the current campaign observed as published from a completed refresh. Search
must precede the first substantive research action.

`ask_user` is part of the v2 schema. Its question is checkpointed. Resume with
an answer records a separate human-attributed import checkpoint and continues
at the next sequence. The answer is bounded and becomes explicit planner
feedback; it is never treated as mathematical warrant.

Experiment and verifier failures remain recorded non-terminal outcomes while
the action budget remains. All other failed effects stop unresolved. A report
is terminal, and every returned summary remains unapproved and explicitly
states that no epistemic warrant was created.

## Compatibility and activation

The existing `EndToEndCampaignRunner` and deterministic fixture effect set are
retained. Its ordering check now permits repeated cycles, so the fixture and
model-driven paths exercise the same causal rule without changing existing
fixture bytes. The legacy `campaign run` v1 contract also remains available.

This ADR supplies orchestration, not authority. A registry entry does not
activate its provider, network, corpus, embedding, OCI, Lean, or typesetting
adapter. Each adapter must independently pass its existing named gate.

## Validation

Offline acceptance drives model-selected v2 actions through literature,
published-generation retrieval, a failed non-terminal experiment, a durable
human interruption/resume, a second literature cycle, and a terminal report.
It also proves that retrieval against an unobserved generation is refused and
that resume does not repeat completed paid planner calls.
