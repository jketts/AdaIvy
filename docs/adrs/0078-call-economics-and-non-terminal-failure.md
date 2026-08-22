# ADR-0078: Call economics and non-terminal failure

- **Status:** accepted
- **Date:** 2026-08-22
- **Blueprint requirement:** campaign depth and breadth plan, Slice 11
- **Supersedes in part:** ADR-0065's one-shot clauses (hard context-bound
  refusal, instantly-terminal `action_rejected`) and ADR-0066's clause that a
  sandbox execution failure is terminal for the campaign
- **Decision owners:** repository owner

## Context

The bootstrap protocol treated the model as a compiler: one validated
instruction in, one validated action out, any failure fatal. Concretely at
`main@953e7a7`:

- `MAX_CONTEXT_BYTES_CEILING` was 256 KiB against multi-megabyte provider
  windows, and a context over the bound was a hard refusal;
- any `CampaignRunnerError` during action handling was instantly terminal
  (`action_rejected`), so one malformed JSON field ended a funded campaign;
- a failed `run_program` (including a pending-sandbox refusal and a
  determinism refusal) was terminal per ADR-0066, with its diagnostic
  deliberately withheld;
- `ask_user` orphaned the campaign on the live path: the answer could never
  continue the same ledger.

Wrong conjectures, dead-end programs, and malformed retries are budgeted
costs, not violations. Nothing here weakens the boundary: verification,
provenance closure, bounds, and the human publication gate are unchanged.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Keep one-shot semantics | ADR-0065/0066 | simplest audit story | audit findings above; live budget waste | none crossed |
| Unbounded retries | — | maximal recovery | budget dishonesty; infinite loops | violates budget honesty |
| Bounded repair + non-terminal recorded failure (chosen) | this ADR | failures become data; budgets stay real | more ledger states | all listed below |

## Decision

### 1. Ceilings

- `MAX_CONTEXT_BYTES_CEILING` rises from 262,144 to 2,097,152 bytes (2 MiB),
  toward provider windows. The per-configuration bound is still operator
  input, still refused above the ceiling, never clamped.
- Per-call output tokens were already configurable
  (`per_call_output_token_reserve` in the live-run configuration, which has
  no artificial ceiling); this ADR records that the value may be set to the
  provider's model limit. Campaign-total token/cost ceilings are unchanged.
- Live budget `max_attempts` has no ceiling constant and nothing in the
  runner, planner, or configuration validation assumes the shipped value of
  2; raising shipped config values is deferred to Slice 16.

### 2. Deterministic rolling-window context

When a planner payload would exceed `max_context_bytes`, the gateway adapter
collapses `previous_actions` entries oldest-first into deterministic
summaries — `{collapsed: true, action_hash, action_type, branch_id, bounded
rationale, full_action_retained_by_planner: true}` — until the payload fits.
The hash commits to the canonical full action retained in the planner's
bounded in-memory transcript; it is not presented as an artifact hash because
actions whose substantive output is separately stored do not necessarily
store their raw JSON in the artifact store. Only if the payload still exceeds
the bound with every entry collapsed does the call refuse, and that refusal is
the recorded terminal
`context_bound_exhausted` (Slice 9), not a discarded run. Collapse is a pure
function of the same inputs, so identical campaigns still produce identical
requests.

### 3. Bounded repair of malformed actions

A `CampaignRunnerError` raised while admitting a planner action is recorded
(as before) as a `failed` system `plan` action naming the refused bytes, but
is no longer instantly terminal. The exact validation error is echoed to the
model in the next context (`last_rejection`, with
`repair_attempts_remaining`), and the campaign continues. After
`max_repair_attempts` consecutive rejections (policy field, operator flag
`--max-repair-attempts`, default 3, ceiling 8) the campaign is terminal
`action_rejected` exactly as before. Every attempt, failed or repaired,
remains in the ledger; each retry consumes an action slot and a model call,
so repair is paid for out of the same budget.

**Deviation from the plan text:** the plan said "the same sequence number is
retried". Campaign records are append-only and one action id exists per
sequence, so a retry occupies the next sequence with the rejection recorded
at its own sequence; the *semantic* retry contract (same pending work, error
echoed, bounded count, then terminal) is what this ADR adopts.

### 4. Failed experiments are recorded, non-terminal outcomes

A `run_program` whose result status is not `completed` — a real sandbox
failure, a determinism refusal, or the pending-sandbox refusal — is recorded
as a failed tool run and failed action, its bounded diagnostic (exit payload
and stderr excerpt, per ADR-0077 §3) enters the next context, and the
campaign continues while tool-run and campaign budgets remain. This
supersedes ADR-0066's terminal clause. Nothing about execution authority
changes: an unwired sandbox still executes nothing; the refusal is simply no
longer the end of the campaign.

### 5. Action-level checkpointing on the live path; resume staged

`SequentialCampaignRunner` now accepts the ADR-0075 `ActionCheckpointStore`:
an intent is durable before every planner call (marked paid/irreversible on
live providers) and a terminal record is durable after every admitted or
rejected action. The operator entrypoint wires the store under the campaign
root (`action-checkpoints/`), and any checkpoint bytes close the root against
a second `run`.

**Staged follow-up, explicitly not implemented here:** continuing an
`awaiting_user` live campaign through `campaign resume` with an operator
answer (rebuilding runner state from the checkpoints and durable artifacts,
recording the answer as a human-attributed record, and refusing to repeat any
paid intent). The checkpoint plumbing this requires is in place; the resume
driver is the follow-up and until it lands an answered `ask_user` still
requires a new campaign.

## Consequences

- The offline fixture script `program-sandbox-refusal` now continues past the
  refused execution to its terminal report; the `make check` campaign gate
  assertions move accordingly (the refusal count and the failed tool run are
  still asserted — the failure is preserved, not erased).
- The terminal reason `experiment_failed` no longer occurs; readers of old
  ledgers are unaffected (it was a terminal label, not a record schema).
- Checkpoint files appear under fixture campaign roots; they are
  deterministic for frozen `--recorded-at` inputs and are covered by the
  append-only root guard.
- A hostile model can now spend up to `max_repair_attempts` model calls per
  mistake; the cost is bounded by the same attempt/token/cost budgets that
  bounded it before.
