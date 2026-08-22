# ADR-0072: Wire the activated experiment sandbox and a verifier router into `campaign run`

- **Status:** accepted and implemented
- **Date:** 2026-08-22
- **Blueprint requirement:** ADR-0057 §1-2 (isolated experiment and verifier
  ports); ADR-0065 (the operator entrypoint that left both ports fail-closed);
  ADR-0066 (the activated sandbox this wires); ADR-0035 (Phase 5 exact
  verification); ADR-0016/Phase 3B (sealed Lean checking); ADR-0040 (validator
  diagnostics are not repair fuel);
  [`END_TO_END_RESEARCH_RUNTIME_PLAN.md`](../END_TO_END_RESEARCH_RUNTIME_PLAN.md)
  §2.3 and §3.6 (Slice 6)
- **Decision owners:** repository owner and researcher

## Context

ADR-0065 made the campaign loop reachable with a pending experiment runner and
an absent verifier, and ADR-0066 activated a digest-pinned OCI sandbox plus an
exact graph verifier behind their own gate — but `campaign run` still injected
`PendingSandboxExperimentRunner` and `AbsentVerifier`. Every campaign therefore
ended at the same two blockers regardless of what had been activated.

## Decision

### 1. Experiment wiring is evidence-matched, never flag-only

`campaign run --experiment-activation PATH` supplies the stored ADR-0066 gate
record. The record is strictly re-verified (canonical bytes, content hash, all
sixteen probes), its recorded runtime identity is reconstructed, and
`build_activated_campaign_experiment_runner` re-checks the current
`config/campaign-experiment-oci-image-v1.json` and Phase 4B lock hashes and the
frozen experiment target hash against the activation. Only a full match wires
`ActivatedCampaignExperimentRunner`. Anything else — no record supplied, bytes
that do not re-verify, a blocked activation, a moved lock, a different runtime,
an unreadable target — keeps the pending runner, and the exact machine-readable
reason is carried in the run payload and in every recorded execution refusal
(`wiring_reason`). A sandbox execution failure remains terminal
(`experiment_failed`), and its diagnostics are never returned to the lead.

### 2. `AbsentVerifier` is replaced by `CampaignVerifierRouter`

The router dispatches one selected candidate on its declared `schema_version`:

| Candidate schema | Route | Verifier |
|---|---|---|
| `adaivy.campaign-experiment-graph-candidate.v1` | `exact_graph` | ADR-0066 exact graph verifier over the frozen target |
| `adaivy.quantum-diagonal-fixture.v1` | `phase5_quantum_diagonal` | Phase 5 exact diagonal recomputation (checked computation, no target-satisfaction semantics) |
| `adaivy.phase5-noncommuting-fixture.v1` | `phase5_noncommuting` | ADR-0035 exact certificate verification |
| `adaivy.campaign-formal-check-request.v1` | `phase3b_formal_check` | injected Phase 3B port |
| anything else | `unsupported` | explicit FAILED `unsupported` outcome, never a silent pass or fail |

The formal-check port defaults to a machine-readable missing-tool result;
`--formal-check-adapter sealed` injects the real Phase 3B
`FormalCheckingService` over the sealed Docker Lean adapter, lazily, so the
offline path never imports it.

### 3. Isolation invariants

- The router reconstructs verifier context from records alone: frozen target
  bytes and the injected port. It holds no planner, gateway, credential, or
  corpus field, and its configuration record asserts so.
- Verifier results enter the ledger as tool runs; the sequential runner never
  places them in a planner context, so the lead sees action status, not
  verifier payloads.
- Formal-check findings are projected to machine-readable codes before entering
  the campaign ledger: policy-rejection codes and fields survive, free-text
  details, wrapper source and execution diagnostics do not (ADR-0040).
- Generated programs still receive only source bytes, recorded input artifacts,
  and safe arguments — no environment, no credential, `network: "none"`.

### 4. Nonterminal candidate failure

A verifier rejection (exact refutation, unsupported candidate, missing sealed
tool, unapproved assumptions) fails that `verify` action and the campaign
continues while budget and a valid next action remain. Sandbox execution
failure stays terminal per ADR-0066.

### 5. Ledger adjustments

- `campaign-facts` moves to `adaivy.campaign-facts.v3`: the sandbox and
  verifier blocks are now derived from the ledger's recorded adapter
  identities (`not_exercised` / `pending` / `activated_oci`; router counts),
  never asserted.
- `ToolRunRecord` accepts a locally measured run that carries at least one
  observation: ADR-0066 records host-observed wall time and output bytes while
  deliberately keeping CPU and peak memory null rather than guessed. A
  "measured" claim with zero observations is still refused. Measurements remain
  operational, outside the semantic content hash.

## What this decision does not license

No warrant, ever: a completed router verdict is a checked computation bound to
the exact encoded statement; target correspondence remains a separate recorded
property. No novelty, significance, applicability, or graph admission. No
network or credential reaches a generated program or a verifier. No retrieval,
corpus, or literature action (Slices 3–5), and no credential-profile change
(Slice 2).

## Open questions

- **`formal_check` as a first-class campaign action.** The plan (§3.1) names a
  `formal_check` action type. Wiring did not require it: a `verify` action
  whose selected candidate is an `adaivy.campaign-formal-check-request.v1`
  envelope reaches the Phase 3B port through the router. Whether formal
  checking deserves its own closed action schema (with its own budget field and
  replay semantics) is deliberately left open; the envelope is the minimal
  recorded stub.
- **Safe elaboration feedback.** The plan permits safe elaboration feedback to
  return to the lead. Today no verifier output returns to the planner context
  at all, which satisfies the isolation requirement by strictness; a future
  slice defining a vetted feedback projection would relax this deliberately.

## Falsifiability probes

Covered by `tests/test_campaign_verifier_router.py`,
`tests/test_campaign_cli.py`, the offline `make campaign` target, and the
extended `make check-campaign-experiment-oci` gate:

- a tampered activation record keeps the pending runner and records the reason;
- the committed activation record wires the OCI runner with zero subprocesses
  until a program actually runs;
- a prose or unknown-schema candidate is an explicit `unsupported` failure;
- an exactly refuted candidate leaves the campaign continuing to a report;
- a satisfied exact-graph candidate completes `verify` and creates no warrant;
- policy-rejection free text never reaches the campaign ledger;
- under the OCI gate, one generated program executes in the pinned sandbox and
  its inspected candidate verifies through the router inside a single recorded
  campaign; and
- under the sealed-Lean gate (`make check-sealed`), the real Phase 3B kernel
  check is reached through the router's formal-check route and its recorded
  finding is code-only and warrant-free.
