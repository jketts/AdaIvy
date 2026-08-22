# ADR-0047: Bounded central research lead runtime

- **Status:** accepted for the bounded runtime slice; implemented 21 August
  2026 with an offline rehearsal gateway and an explicit live-provider gate.
  Superseded in part by ADR-0072, which supplies the "later decision" the
  Explicit deferrals clause requires for retrieval scheduling, experiment
  scheduling, branch-selection policy, and Phase 3B proof-repair orchestration
  inside a campaign; every other clause of this record stands.
- **Date:** 2026-08-21
- **Blueprint requirement:** Sections 6, 8, 12, and 17; ADR-0029 central-lead
  baseline; ADR-0041 Phase 2 refinement boundary
- **Decision owners:** repository owner

## Context

ADR-0029 selected one coherent long-horizon research lead with a centralized,
context-isolated verifier as the baseline architecture, but explicitly
activated no runtime. Phase 2 subsequently gained bounded refinement within a
single run under ADR-0041. A separate uncommitted implementation added an outer
session loop but incorrectly labelled itself ADR-0041 and predated that Phase 2
change. Integrating it without a new decision would create both an ADR collision
and two overlapping iteration mechanisms.

The useful capability is narrower than general search: carry a bounded record
of earlier proposals and verifier findings to the next proposer call, keep the
target fixed, stop for named reasons, and retain enough durable state to replay
the report without calling a model. It must not grant trust, silently multiply
bounds, expose proposer history to the verifier, or imply that iteration helps.

## Decision

Add `src/math_research/runtime/` and the `adaivy runtime` command family as a
bounded orchestration layer above Phase 2.

One runtime iteration is exactly one Phase 2 proposer/verifier round stored as
its own durable Phase 2 run. A runtime configuration that asks for more than one
ADR-0041 refinement round inside an iteration is rejected. This makes the outer
session bound the only iterative loop and prevents the two mechanisms from
multiplying model calls or cost.

The target claim, formalization, assumption manifest, semantic alignment, and
dossier identity are frozen before the first call and re-derived before every
iteration. A change raises `TargetIdentityViolation`; no partial session is
presented as coherent.

The proposer receives a bounded ledger of earlier attempts and findings. The
verifier receives the ordinary Phase 2 isolated context for the current
candidate only. Runtime checks reject any session-history field or prior
hypothesis digest that reaches the verifier context.

Session limits are supplied through a content-hashed configuration and checked
before a new iteration. Hard ceilings cover iterations, model calls, cost, wall
time, ledger entries, ledger bytes, and field bytes. Duplicate hypotheses do
not spend a verifier call. Stagnation means consecutive iterations supplied no
new hypothesis-and-finding pair; it is only a stop rule.

The strongest runtime outcome is `awaiting_human_review`. The session record
fixes `epistemic_warrant_created` to false, `obligations_discharged` to zero,
and novelty, significance, and retention gain to `not_assessed` or false. The
runtime writes no trust decision, applicability decision, graph admission, or
publication approval.

Replay reads the content-hashed session and durable Phase 2 workspace and does
not hold a model gateway. A replay path that reaches a gateway fails loudly.

The command defaults to a deterministic fixture gateway. A live run requires
all of `--execute`, a content-hashed live configuration, a confirmed pricing
snapshot, and the existing Phase 2 preflight. This ADR adds no provider and no
new dependency.

## Consequences

- ADR-0029's central baseline now has an executable, bounded outer loop.
- ADR-0041 remains authoritative for refinement within an ordinary Phase 2
  run; ADR-0047 deliberately fixes its per-iteration value to one.
- No specialist, parallel, evolutionary, or higher search tier is activated.
- No claim is promoted, even when a verifier recommends manual review.
- The session records iteration outcomes, usage, duplicate detection,
  stagnation, terminal reason, and semantic/operational identity for audit.
- Whether iteration improves verified progress per unit cost remains
  unmeasured and cannot be inferred from the session report.

## Measured outcome

`tests/test_runtime_lead.py` contains 36 offline tests, including 17 named
falsifiability probes. They cover target drift, verifier-context leakage,
duplicate normalization, non-vacuous distinct attempts, session and iteration
bounds, nested-refinement refusal, stagnation, non-promotion, tampered replay,
and replay gateway access. The suite uses no network, model provider, or
container.

During integration, two defects in the uncommitted implementation were fixed:
the test harness now binds scripted sessions to their supplied iteration count,
and a malformed verifier response that consumed the final permitted attempt is
reported as `verifier_failed`, not as a budget block. A budget outcome is used
only when the bound prevented the required call.

## Explicit deferrals

No Phase 3B proof-repair orchestration, retrieval scheduling, experiment
scheduling, branch-selection policy, specialist worker, parallel execution,
evolutionary selection, retention-gain measurement, automatic review, or trust
promotion is added. Each requires its own later decision and acceptance gate.

## Validation and revisit trigger

The decision remains valid while `make check` stays offline and green; every
iteration remains a distinct one-round Phase 2 run; the target identity is
stable; the ledger remains proposer-only and bounded; replay performs zero
model calls; session reports disclose the absence of warrant, obligation
discharge, novelty/significance assessment, retention measurement, and higher
search tiers; and every named falsifiability probe remains present.

Revisit if Phase 2 and the outer runtime must share a refinement loop, if a live
session needs different proposer and verifier provider configuration, if any
component wants to promote trust, or if measured retention gain is used to
justify a higher search tier.
