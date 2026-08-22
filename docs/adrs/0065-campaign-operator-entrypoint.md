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
makes an accepted-but-unreachable capability reachable, and it makes every
refusal that was already implemented in the library observable from a command
line.

It makes exactly ONE change under `src/math_research/campaign/`, authorized
after an adversarial audit of this slice and recorded here rather than left
silent. `SequentialCampaignRunner.run` used to raise a mid-loop
`CampaignRunnerError` past its caller and discard the in-memory ledger, while
`ArtifactStore.put` had already written the model-authored bytes that the
rejected action produced. The measured result was model-authored Python source on
disk with no ledger record naming it, no `campaign.json`, and therefore -- since
the append-only guard keyed on `campaign.json` -- a second `run` admitted into
the same root on top of it. The runner now records the rejection as a terminal
`failed` action naming its own model call and the stored bytes, sets
`terminal_reason` to `action_rejected`, and RETURNS the partial run. That is
required by the standing rule that failed attempts stay in machine-readable
output and cannot be done from the CLI. It adds no action type, changes no hash
rule, and relaxes no bound: a rejection whose planner output is itself larger
than the artifact bound still raises, because naming it would breach the bound
that rejected it.

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
  `allowed_tools` is the fifteenth field and now carries a ceiling like the other
  fourteen. The ceiling is DERIVED, not chosen: no campaign can perform more than
  `MAX_TOOL_RUNS_CEILING` tool runs, so an allowlist longer than that grants tool
  authority no campaign can ever exercise, and `MAX_ALLOWED_TOOLS_CEILING` is
  exactly `MAX_TOOL_RUNS_CEILING`. Every entry must additionally satisfy the
  runner's own tool-identifier rule, so `config-create` cannot content-hash a
  configuration naming `../../etc/passwd` that the runner would then reject for a
  reason the configuration misattributes, and a repeated `--allowed-tool` is
  refused rather than silently de-duplicated, exactly as a duplicate numeric
  field is.
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
`PlannerPort` holding no gateway; it performs zero provider requests, opens zero
sockets and zero subprocesses, and needs no key. It DOES produce model-call
records -- one per scripted planner call -- and they carry `provider: "fixture"`,
`usage_source: "unavailable"`, zero tokens and a null estimated cost, so a
fixture campaign can never present itself as measured work. "Zero model calls" is
the wrong claim and this ADR no longer makes it: `requests_attempted` equals the
number of scripted calls and the ledger says so.

`--provider fixture` and the live activation arguments are mutually exclusive.
`--execute`, `--live-config`, `--pricing-snapshot` and a non-empty
`--activation-acknowledgement` are all refused with
`fixture_provider_refuses_live_activation_flags` when the provider is the
fixture. Accepting them and reporting `provider: fixture` kept the label honest
but silently gave an operator or a script that had asked for a live run a green
scripted one, which is the substitution this ADR exists to stop.

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
passes or fails.

Every inert operator input is read and validated **before** `build_gateway`, so
no local file can strand a paid request outside a ledger. That includes
`--action-schema`, which defaults to a *relative* path and was previously read
during planner construction, after the one billable probe had already been fired;
running `campaign run` from any directory but the repository root therefore spent
a real request and recorded nothing. An unreadable schema is now
`campaign_action_schema_is_not_readable`, refused before any gateway exists.

Retention is keyed on whether a request left the process, not on whether it
succeeded. Three outcomes are distinguished:

- `probe_request_hash` is null: nothing left the process, so `requests_attempted`
  is zero, `activation.json` is written, no `campaign.json` is written, and the
  reason is `provider_activation_not_executed`.
- the probe failed: a **terminal recorded activation failure**. The activation
  model call and action are written into the campaign ledger, the terminal reason
  is `provider_activation_failed`, and the command exits 2.
- the probe PASSED and the campaign still did not start: the same
  activation-only ledger is written and the terminal reason is
  `provider_activation_retained_without_campaign_start`. The retention branch was
  previously guarded on a failed probe, so a passing probe followed by any
  downstream failure persisted no `campaign.json`, no `ModelCallRecord` and no
  `ActionRecord` -- one real billable request, zero records.

None of these is ever `proposer_declined`, and no second gateway is constructed.
The activation model-call status is derived from the probe's own response
counters rather than hardcoded, because ADR-0057 §3 keeps `responses_completed`,
`responses_failed` and `responses_incomplete` distinct: a timed-out probe is
`incomplete` and must not be collapsed into the failed bucket, and anything
ambiguous stays `failed`.

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
`operational_hash` covers them. `run` writes append-only. Any durable byte closes the root, not `campaign.json`
alone: `campaign.json`, `campaign-facts.json`, `campaign-config.json`,
`novelty-recheck.json`, `target.json`, `activation.json`, `artifact-log.jsonl`
and a non-empty `artifacts/` each refuse a second `run` with
`campaign_root_already_recorded`. Keying the guard on `campaign.json` alone let a
run that stored artifacts and then refused admit a second run on top of the first
run's model-authored bytes.

`campaign.json` is the **last** durable write. It is the file the guard keys on,
so writing it before `campaign-facts.json` wedged the root permanently: an error
between the two left a root that a re-run refused and that `inspect` could not
read. Re-writing any durable file with different bytes is refused, and that
refusal now reports `campaign_durable_record_rewrite_refused` as its
machine-readable `reason` rather than only inside a detail string.

### 7. A bound violation is durable, and effects are measured

The recorded rollups are compared with the configured caps and the comparison is
DERIVED into `campaign-facts.json` as `bound_compliance`, alongside the observed
and configured values. It was previously computed after every durable file had
already been written and existed only on stdout, so a campaign that blew three of
its own caps persisted, then inspected as `verified`, replayed as
`verified: true`, and exported bytes labelled for `publication build
--campaign-export`. The ledger is still retained -- the violation IS the record --
but `run`, `inspect` and `replay` refuse with
`campaign_recorded_usage_exceeds_configured_bound` and `export` writes nothing.

`inspect` and `replay` also close the artifact store both ways. Every file under
`artifacts/` must be named for the hash of its own bytes, must hash to that name,
and must be named by the ledger; the append-only put log must name exactly the
ledger's artifacts. Checking only that ledger-named hashes resolve admitted both
an orphan file the ledger never recorded and a file whose name is a hash its own
bytes do not produce, because nothing ever read a file the ledger did not ask
for.

The five effect counters `model_calls_made`, `provider_requests_made`,
`tool_calls_made`, `subprocesses_opened` and `network_requests` are **measured**.
Two come from a CPython audit hook over the interpreter's own `subprocess.*`,
`os.*` and `socket.*` events, and three are counted at the injected planner,
experiment and verifier ports. They were constant zeroes compared by `make
campaign` against a constant zero tuple -- a literal against a literal -- and an
audit that made `replay` open a socket and start a process still reported
`(0, 0, 0, 0, 0)` and still passed. `inspect` and `replay` now refuse with
`campaign_replay_performed_model_tool_or_network_work` if any counter moves or if
the audit hook could not be installed, because an unmeasured zero must not read
as a measured one. An audit hook cannot be evaded by patching a module attribute
or by holding a pre-bound reference, which a mock can. The two effect literals
that used to sit in the `campaign-facts.json` guardrail block are gone: they were
not derivable from a ledger, which is why they had to be literals, and the facts
schema version is now `adaivy.campaign-facts.v2`.

Each rejecting class reports its own reason. `campaign_runner_rejected_the_run`,
`campaign_ledger_failed_provenance_validation`,
`campaign_configuration_rejected`, `campaign_durable_record_rewrite_refused` and
`campaign_durable_write_failed` were all previously reported as the first of
those, with the truth demoted to a human-readable `detail` field.

### 8. `make check` stays offline

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

- The fixture path's model-call records are records of a scripted call that
  never left the process. `provider: "fixture"`, `usage_source: "unavailable"`
  and a `measurement_status` of `unavailable` are what distinguish them; a
  reader who ignores those fields could miscount `requests_attempted`. This ADR's
  own gate text used to say the fixture path "makes zero model calls", which is
  the same miscount stated as a claim; it now says what the ledger says.
- One more operator surface exists that can spend money if pointed at a live
  provider with `--execute`.
- A rejected action is retained, so a campaign root can now hold a ledger whose
  terminal action is a `failed` `plan`. `terminal_reason` is `action_rejected`,
  the command exits 2, and the rejection text is in `declared_rationale`; a reader
  who looks only at `campaign.json` existing would read a refused run as a run.
- The effect counters measure THIS process. They observe the interpreter's audit
  events and the injected ports, so they would not see work done by a child
  process or by code that never crosses a port. Nothing on the offline path does
  either, and `run_program` still executes nothing at all.
- **Open, and a decision for the repository owner, not a defect this ADR fixes.**
  A live campaign that chooses `derive` then `report` with provider-reported usage
  yields `attribution_status: adaivy_campaign` (ADR-0057 derives it from the
  absence of imports) together with `measurement_status: complete`, and
  `publication/campaign.py` accepts that pair. Before this entrypoint existed the
  combination was unproducible because nothing could run a campaign; it is now
  reachable, which means an AdaIvy-attributed claim backed by nothing but model
  text is reachable. `run_program` refusing and `verifications_completed` being a
  computed zero are what stand between that and a published discovery, and both
  are fields rather than gates. Changing attribution or measurement semantics is
  outside this ADR and was deliberately not done here.

## Blueprint deviation

None. This is the operator surface ADR-0057 assumed and did not specify. The one
change to `SequentialCampaignRunner.run` is recorded under Decision above; it
retains a failure that was previously discarded and widens nothing.

## Acceptance gates

Encoded as executable assertions in `tests/test_campaign_cli.py` and
`tests/test_campaign_runner.py`, and asserted on the recorded outcome by `make
campaign`:

1. the fixture path reaches a terminal `report` action, constructs no gateway,
   performs zero provider requests, and -- measured by a CPython audit hook --
   opens zero sockets and zero subprocesses; its ledger records one scripted
   planner call per action with `usage_reported_calls: 0` and
   `measurement_status: unavailable`, and the resulting export verifies;
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
9. **each of the fourteen numeric bounds** is refused, one at a time, when set
   one above its declared ceiling, rather than clamped; a `max_actions` of one is
   refused because it leaves no research action; a duplicate or unknown
   configuration field is refused; and `allowed_tools` refuses a non-identifier
   entry, a duplicate entry, and a list longer than
   `MAX_ALLOWED_TOOLS_CEILING` while admitting one exactly at it;
10. `replay` verifies closure while MEASURING zero model, provider, tool,
    subprocess and network effects, and reports the mechanism that measured them;
11. a single-field mutation of a ledger ancestor breaks replay closure, and so
    do deleting an ancestor action, mutating stored artifact bytes, substituting
    the frozen target record, planting an artifact file the ledger never
    recorded, planting a file whose name is a hash its own bytes do not produce,
    planting a file that is not an artifact name at all, and adding an
    artifact-log entry outside the ledger;
12. `export` output is byte-identical to `campaign.json` and re-verifies through
    `verify_campaign_export`, the form `publication_cli --campaign-export`
    consumes; and
13. every path reports `epistemic_warrant_created: false`, every derived
    guardrail field is `false` or zero, and a second `run` into a recorded root
    refuses with `campaign_root_already_recorded`;
14. a failed activation is retained as one attempted request with zero completed
    responses, exactly one gateway is constructed, and the output contains
    neither `proposer_declined` nor a `completed` terminal status; an
    activation that never executed records zero attempted requests, writes
    `activation.json`, and writes no `campaign.json`; a timed-out activation
    records `responses_incomplete: 1` and `responses_failed: 0` in
    `campaign.json` and `campaign-facts.json`, not only in `activation.json`; an
    unreadable `--action-schema` is refused before any gateway is constructed;
    and a PASSED activation whose campaign never started is still retained as a
    ledger with terminal reason
    `provider_activation_retained_without_campaign_start`;
15. `--provider fixture` refuses `--execute`, `--live-config`,
    `--pricing-snapshot` and a non-empty `--activation-acknowledgement` with
    `fixture_provider_refuses_live_activation_flags`;
16. a campaign whose recorded usage exceeds a configured cap records the
    violation in `campaign-facts.json`, and `inspect`, `replay` and `export` all
    refuse it; a within-bounds campaign still exports;
17. a mid-run rejected action is retained: `terminal_reason` is
    `action_rejected`, the terminal action is `failed` with actor type `system`
    and a rationale naming the rejection, every byte in the artifact store is
    named by some action, the partial ledger closes, `replay` verifies it, and a
    second `run` into that root refuses; nothing reaches the experiment or
    verifier port on any of the eight runner rejection paths;
18. a root holding only artifacts, with no `campaign.json`, refuses a second
    `run` with `campaign_root_already_recorded`;
19. `campaign.json` is the last durable write, and a failure writing
    `campaign-facts.json` leaves no `campaign.json` behind; and
20. each rejecting class reports its own distinct machine-readable reason.

Falsifiability probes, each a named single-field mutation that must produce the
forbidden verdict: `campaign.json` ancestor `declared_rationale` mutation must
break the semantic hash; ancestor `recorded_at` mutation must break the
operational hash; ancestor deletion must break sequence closure; an
`artifacts/` byte mutation must break artifact closure; a `campaign-facts.json`
`guardrails.epistemic_warrant_created` flip to `true` must be refused by
`inspect`; a `--max-actions` one above the ceiling must be refused by
`config-create`; and -- the probe for the effect counters themselves -- making
`replay` create a socket and a process must move `network_requests` and
`subprocesses_opened` off zero and must refuse the replay.

## Validation and revisit trigger

Valid while the fixture path stays the default and stays offline, the live path
keeps requiring `--execute` plus a matching content-hashed configuration and a
confirmed pricing snapshot, exactly one no-retry activation precedes research,
every activation request that left the process stays retained in a ledger,
`run_program` keeps naming ADR-0066, replay stays model-free and tool-free with
MEASURED counters, `campaign.json` stays the last durable write, and `make check`
stays offline and standard-library only.

Revisit when ADR-0066 passes and `run_program` becomes executable, when an
isolated campaign verifier is wired, before allowing a rejected action to be
anything other than terminal, before any second campaign entrypoint is added,
and -- separately and first -- before any live campaign export is used as the
provenance for a reader-facing publication, because of the open attribution
question recorded under Consequences.
