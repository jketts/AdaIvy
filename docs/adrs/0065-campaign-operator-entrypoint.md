# ADR-0065: Give the ADR-0057 campaign an operator entrypoint

- **Status:** accepted for the wiring slice; generated-code execution stays
  fail-closed pending ADR-0066
- **Date:** 2026-08-22
- **Blueprint requirement:** ADR-0057 §1--§4; ADR-0047 bounded runtime;
  ADR-0055 `before_research` checkpoint; ADR-0026 acceptance-suite rule
- **Decision owners:** repository owner and researcher

## Context

ADR-0057 is accepted and implemented. `src/math_research/campaign/` contains
the action ledger (`derive`, `write_program`, `run_program`, `inspect_result`,
`falsify`, `verify`, `ask_user`, `suspend_branch`, `report`), the sequential
runner that validates and dispatches one action per model call, the live
gateway planner, and strict replay.

**Nothing can start it.** Every reference to `GatewayCampaignPlanner` outside
its own module is a test. No CLI constructs a `SequentialCampaignRunner`, no
`Makefile` target exercises one, and the only non-test consumer of the package
is `publication/production.py`, which reads an *already existing* campaign
export as provenance. The subsystem can therefore be audited and published but
not run.

The measured consequence is the failure ADR-0057 was written to stop. Because
the campaign has no entrypoint, the driving Codex or Claude Code task performs
the mathematics itself, outside any ledger, and the campaign layer sees the
result only as an import. ADR-0057 §5 already says what happens then: the work
is external, `attribution_status` is `external_assisted`, and no
`adaivy_campaign` discovery sentence may be printed. That is the honest
outcome, and it is the *only* outcome reachable today.

This is a wiring gap, not a missing capability. The capability was decided,
built, bounded, and tested; it has no front door.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt: add a `campaign_cli.py` in the `runtime_cli.py` shape | `runtime_cli.py` already implements the fixture-default / `--execute` / content-hashed-config / confirmed-pricing pattern for ADR-0047 | The accepted capability becomes reachable; no new trust, no new network surface, no new model authority | One more operator surface to keep fail-closed | Fixture default calls nothing; live path needs `--execute` plus matching content-hashed config and confirmed pricing; `run_program` refuses by name |
| Wrap: drive the campaign from `runtime_cli.py` | ADR-0047 and ADR-0057 are distinct loops with distinct bounds | No new module | Two loops multiply each other's bounds, exactly what ADR-0047 refuses for ADR-0041 refinement | Rejected |
| Interoperate: leave it to ad-hoc scripts | Current state | Nothing to build | Ad-hoc scripts are the mechanism by which the mathematics keeps happening outside the ledger | Rejected |
| Build/defer: wait for the ADR-0066 sandbox | The sandbox gates `run_program` only | Fewer moving parts | `derive`, `write_program`, `inspect_result`, `falsify`, `verify` and `report` need no sandbox; deferring all of them keeps the whole loop unreachable for one action's sake | Rejected |

## Decision

Add `src/math_research/campaign_cli.py`, one `campaign` subparser in
`src/math_research/cli.py`, and one offline `campaign` target in the `Makefile`
inside the `check` aggregate.

**This decision widens no capability.** It adds no record type, no action type,
no adapter, no provider, no network surface beyond the Phase 2 gateway ADR-0030
and ADR-0048 already admit, and no authority for a model or tool result. It
changes no file under `src/math_research/campaign/`. It makes an
accepted-but-unreachable capability reachable, and it makes every refusal that
was already implemented in the library observable from a command line.

### 1. Commands

- `config-create` writes a content-hashed campaign configuration carrying every
  bound the runner policy enforces: `max_actions`, `max_tool_runs`,
  `max_model_calls`, `max_input_tokens`, `max_output_tokens`,
  `max_cost_microusd`, `max_program_bytes`, `max_artifact_bytes`,
  `max_context_bytes`, `max_cpu_milliseconds`, `max_wall_milliseconds`,
  `max_memory_bytes`, `max_output_bytes`, `max_process_count`, and
  `allowed_tools`. Bounds are operator input and are not trusted to be sane:
  each is checked against a hard ceiling declared in the module and a
  configuration above a ceiling is refused outright rather than clamped.
- `target` freezes and writes the campaign target record. Its `sha256` over its
  own canonical bytes is the campaign `target_hash`, so the target identity in
  the ledger is re-derivable from a file rather than asserted.
- `run` assembles `PlannerPort` + `CampaignExperimentRunner` + `VerifierPort` +
  `ArtifactStore` and drives `SequentialCampaignRunner` to a terminal action.
- `inspect` and `replay` read a persisted campaign. Both are model-free and
  tool-free per ADR-0057 §4 and its acceptance gate 10.
- `export` writes the canonical campaign bytes in exactly the form
  `publication_cli.py --campaign-export` consumes, closing the loop from
  entrypoint to publication.

### 2. Defaults and refusals

`--provider fixture` is the default. The fixture planner is a scripted
`PlannerPort` holding no gateway; it makes zero model calls and zero network
calls and needs no key. Its model-call records carry `provider: "fixture"`,
`usage_source: "unavailable"`, zero tokens and a null estimated cost, so a
fixture campaign can never present itself as measured work.

A live provider additionally requires all of: `--execute`; a content-hashed
live configuration whose `provider` equals the named provider; a pricing
snapshot that is confirmed and matches that configuration; the exact
`--activation-acknowledgement` string; and a passing static preflight. Each
absent or mismatched precondition produces a named machine-readable refusal and
exit code 2, and constructs no gateway.

Per ADR-0057 §3, the live path then performs **exactly one** no-retry
activation request through the same gateway, configuration, frozen environment
and pricing snapshot the lead will use. That request is the first campaign
model attempt, it counts against every bound, and it is retained whether it
passes or fails. A failed activation is a **terminal recorded activation
failure**: the activation model call and action are written into the campaign
ledger with status `failed`, the terminal reason is
`provider_activation_failed`, and the command exits 2. It is never
`proposer_declined` and never `completed`, and no second gateway is constructed.
An activation that was never executed because a binding check failed records
zero attempted requests and writes no model-call record, because no request was
made.

The campaign configuration caps are additionally checked against the live
configuration budget before the activation request: a live budget whose
attempts, input tokens, output tokens, or cost exceed the campaign caps is a
refusal, so the two bound sets cannot disagree.

### 3. `run_program` stays fail-closed and names its gate

The injected `CampaignExperimentRunner` in this entrypoint executes nothing. It
opens no subprocess and no socket, imports no process or network module, and
returns a recorded `failed` tool run whose result names the reason
`experiment_sandbox_gate_not_passed_adr_0066` and the blocking decision
`ADR-0066`. The refusal is preserved in the ledger as a missing-tool result
rather than discarded, per the standing rule that failures stay in
machine-readable output. No sandbox is implemented, stubbed, or approximated
here; ADR-0066 is the separate digest-pinned OCI gate and this ADR grants it
nothing in advance.

The offline path is scripted end to end. It opens no subprocess and no socket.

### 4. The isolated verifier is recorded as absent

ADR-0057 §1 sends a selected candidate to an isolated verifier. No campaign
verifier port implementation exists in the repository, and inventing one is a
separate decision. This entrypoint therefore injects a `VerifierPort` that
records the absence: a `failed` tool run naming
`isolated_campaign_verifier_not_wired`. A `verify` action consequently produces
no verification, and `verifications_completed` is a computed zero in the facts
of every campaign this entrypoint can run. That is a named gap, visible in every
run, and not a defect of this wiring.

### 5. ADR-0055 binds before research starts

`run` refuses without a `before_research` novelty re-check bound to the same
problem identifier, the same dossier content hash, and the campaign identifier
as its next action. Unlike `runtime_cli.py`, the twenty-four-hour freshness
window **is** enforced at `run` time against `--recorded-at`, because starting
research is the action ADR-0055 gates. It is deliberately **not** re-enforced by
`inspect` or `replay`, for ADR-0058's reason: re-enforcing it there would make
an existing campaign uninspectable after a day and break the
regenerable-from-records guarantee.

### 6. Determinism

`--recorded-at` is a required argument, not a clock read; this module reads no
clock. Given identical inputs the fixture path produces byte-identical
`campaign.json`, `campaign-facts.json`, `target.json` and artifact bytes across
runs, restarts and processes. Semantic and operational identity stay separated
exactly as ADR-0057 §4 requires: the per-record `content_hash` excludes
`recorded_at`, usage, pricing, cost and resource observations, and the separate
`operational_hash` covers them. `run` writes append-only: a root that already
holds `campaign.json` is refused, and re-writing any durable file with
different bytes is refused.

### 7. `make check` stays offline

The `campaign` target runs only the zero-network fixture dry path, in a mktemp
directory it deletes, and asserts the recorded outcome rather than the exit
status. It needs no network, no model provider, no container runtime and no
third-party package.

## Consequences

An operator can now run a bounded campaign, and a campaign export produced by
that run is exactly what `publication_cli` consumes, so the ledger-to-paper
path is closed for the first time. Because `run_program` refuses and no isolated
verifier is wired, what the entrypoint can currently demonstrate is *provenance
closure*, not mathematics: a campaign it runs reaches a terminal `report` with
zero programs executed and zero verifications completed. Any report that
presents such a campaign as a discovery is over-claiming, and the derived facts
say so in fields rather than prose.

The trusted boundary does not move. No `EpistemicWarrant`, semantic-alignment
approval, applicability assertion, graph admission, novelty status or
significance status is produced on any path. Model and tool output stays an
untrusted proposal.

Negative consequences, stated plainly:

- A mid-run `CampaignRunnerError` raised by `SequentialCampaignRunner.run()`
  discards the partial in-memory ledger, because the runner raises instead of
  returning a partial run. This entrypoint does not change `runner.py`, so the
  refusal is reported by name and the actions taken before it are lost. Fixing
  that is a change to `runner.py` and a separate decision.
- The fixture path's model-call records are records of a scripted call that
  never left the process. `provider: "fixture"`, `usage_source: "unavailable"`
  and a `measurement_status` of `unavailable` are what distinguish them; a
  reader who ignores those fields could miscount `requests_attempted`.
- One more operator surface exists that can spend money if pointed at a live
  provider with `--execute`.

## Blueprint deviation

None. This is the operator surface ADR-0057 assumed and did not specify.

## Acceptance gates

Encoded as executable assertions in `tests/test_campaign_cli.py` and asserted
on the recorded outcome by `make campaign`:

1. the fixture path reaches a terminal `report` action, constructs no gateway,
   makes zero model calls, opens zero sockets and zero subprocesses, and the
   resulting export verifies;
2. two fixture runs with identical inputs produce byte-identical
   `campaign.json`, `campaign-facts.json` and `target.json`;
3. a live provider without `--execute` refuses with
   `live_campaign_requires_explicit_execute` and constructs no gateway;
4. a live provider whose `--live-config` names a different provider refuses with
   `campaign_provider_differs_from_live_configuration`;
5. a live provider without a live configuration or pricing snapshot refuses with
   `live_campaign_requires_live_config_and_pricing_snapshot`, one without the
   exact acknowledgement string refuses with
   `live_provider_activation_not_acknowledged`, and a live budget above a
   campaign cap refuses with
   `live_configuration_budget_exceeds_campaign_configuration_cap` and names the
   exceeded bound;
6. `run_program` is refused with reason
   `experiment_sandbox_gate_not_passed_adr_0066` naming blocking decision
   `ADR-0066`, the refusal is retained as a `failed` tool run, and
   `programs_executed` is zero;
7. a `verify` action records `isolated_campaign_verifier_not_wired` and
   `verifications_completed` is zero;
8. `run` without a bound `before_research` novelty re-check refuses with
   `fresh_novelty_recheck_required_before_research`; a re-check bound to a
   different next action refuses with `recheck_bound_to_different_action`; and a
   re-check older than the twenty-four hour window refuses with
   `recheck_too_old_for_action`;
9. a configuration bound above its declared ceiling is refused rather than
   clamped, a `max_actions` of one is refused because it leaves no research
   action, and a duplicate or unknown configuration field is refused;
10. `replay` verifies closure while making zero provider, network, subprocess and
    tool calls;
11. a single-field mutation of a ledger ancestor breaks replay closure, and so
    do deleting an ancestor action, mutating stored artifact bytes, and
    substituting the frozen target record;
12. `export` output is byte-identical to `campaign.json` and re-verifies through
    `verify_campaign_export`, the form `publication_cli --campaign-export`
    consumes; and
13. every path reports `epistemic_warrant_created: false`, every derived
    guardrail field is `false` or zero, and a second `run` into a recorded root
    refuses with `campaign_root_already_recorded`;
14. a failed activation is retained as one attempted request with zero completed
    responses, exactly one gateway is constructed, and the output contains
    neither `proposer_declined` nor a `completed` terminal status; and an
    activation that never executed records zero attempted requests, writes
    `activation.json`, and writes no `campaign.json`.

Falsifiability probes, each a named single-field mutation that must produce the
forbidden verdict: `campaign.json` ancestor `declared_rationale` mutation must
break the semantic hash; ancestor `recorded_at` mutation must break the
operational hash; ancestor deletion must break sequence closure; an
`artifacts/` byte mutation must break artifact closure; a `campaign-facts.json`
`guardrails.epistemic_warrant_created` flip to `true` must be refused by
`inspect`; and a `--max-actions` one above the ceiling must be refused by
`config-create`.

## Validation and revisit trigger

Valid while the fixture path stays the default and stays offline, the live path
keeps requiring `--execute` plus a matching content-hashed configuration and a
confirmed pricing snapshot, exactly one no-retry activation precedes research, a
failed activation stays terminal and recorded, `run_program` keeps naming
ADR-0066, replay stays model-free and tool-free, and `make check` stays offline
and standard-library only.

Revisit when ADR-0066 passes and `run_program` becomes executable, when an
isolated campaign verifier is wired, before allowing `run` to continue past a
mid-run runner error with a partial ledger, and before any second campaign
entrypoint is added.
