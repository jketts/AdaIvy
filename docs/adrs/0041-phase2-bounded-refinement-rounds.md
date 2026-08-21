# ADR-0041: Phase 2 bounded refinement rounds and measured verifier independence

- **Status:** accepted
- **Date:** 2026-08-21
- **Blueprint requirement:** Phase 2 durable proposer/verifier loop; ADR-0006
  durable workspace; ADR-0007 model boundaries and verifier independence;
  ADR-0008 pinned pricing; ADR-0022 stable protected evidence; ADR-0030
  multi-provider gateways; ADR-0038 provider selection on the run path, whose
  "Cross-provider verifier independence" deferral this ADR closes; ADR-0039
  declarative problem intake (the dossier a run starts with is unchanged here)
- **Decision owners:** Phase 2 owner

## Context

Two defects, one cause: `BaselineResearchLoop` could express more than the run
path let it.

**Defect 1 — the loop parked after one round.** `advance` ran exactly one
proposer job and one verifier job. `_execute_verifier` then set
`AWAITING_REVIEW` or `UNRESOLVED` and the durable timeline stopped at sequence
7. A verifier that said "this step does not follow" produced a parked run and
nothing else: no second attempt, no obligation discharge inside a run. Calling
`advance` again was a no-op. Every durable identity was hardcoded
(`job.{run}.proposer`, `f"job:{run}:proposer"`, `proposal.{run}.verifier`,
`manifest.{run}.verifier`, `call.{run}.{purpose}.attempt.{n}`), so a second
round could not even be written without colliding.

**Defect 2 — one gateway served both roles.** `phase2_cli._loop`
(`src/math_research/phase2_cli.py:158` at commit `6ac08e3`) built a single
gateway object and passed it as both `proposer=` and `verifier=`. The loop's own
signature had always taken them separately, and `VerifierIndependence` already
had `different_model` and `different_provider` fields, but the run path
collapsed all of it.

This is precisely the gap ADR-0038 recorded and deferred: "Cross-provider
verifier independence. `_loop` still uses one gateway for both proposer and
verifier and records `different_provider=False`. Two providers in one run is a
separate slice with its own independence semantics." This is that slice. The
five run-path defects ADR-0038 enumerated — the `("fake", "openai")` choice
literal, the OpenAI-adapter fallback for every provider, the single-key `.env`
loader, the universal `OPENAI_API_KEY` demand, and the OpenAI-only leak scan —
are fixed upstream and are **not** restated as findings here. Registry-derived
`RUN_PROVIDER_CHOICES`, `_prepare_live_run`, `load_provider_environment` and
`provider_secret_values` are taken as given and reused.

The consequence is reported rather than re-measured here: the run recorded at
`reports/phase-2/live-openai-gpt5-mini-problem-intake-v1/live-run-status.json`
(untracked on this tree and deliberately not read or reproduced by this slice —
two succeeded `gpt-5-mini-2025-08-07` calls through `phase2 start --execute`)
carries `different_model: false`, `different_provider: false`,
`context_isolated: true`, `separate_model_call: true`. The verifier-independence
claim therefore rested entirely on context isolation plus a second call to *the
same model at the same provider*. Worse, `VerifierIndependence` arrived as a
caller-supplied value: an operator could have written `different_provider=True`
on that run and the durable manifest would have repeated the assertion.

Rounds and roles are the same question on two axes, which is why they are
decided together. A cross-provider verifier *strengthens* independence. Round
N+1's proposer seeing round N's findings *weakens* it. Deciding one without the
other would let the report claim the strengthening while hiding the weakening.

Constraints discovered while implementing, all verified rather than assumed:

- `runs.status` carries a `CHECK` enumeration and `verifier_manifests.run_id` is
  `UNIQUE`. Both had to change, and SQLite cannot widen a `CHECK` on a
  referenced table with foreign keys enabled.
- `reports/phase-2/workspace.sqlite3` is *sealed evidence*: it is pinned
  byte-for-byte by the ADR-0022 Phase 4A protected-evidence manifest
  (`reports/phase-4a-production/protected-evidence-v2.json`). Both
  `tests/test_phase2_report.py` and the `make check` `phase2` target opened it
  read-write, so the first schema migration to land would have rewritten
  committed evidence in place and broken the Phase 4A gate. It did, once,
  during this slice; that is what surfaced the problem.
- Proposal and verifier-manifest identifiers appear verbatim in
  `render_durable_report`, whose hash is pinned in
  `reports/phase-2/demonstration.json` and
  `reports/phase-2/live-provider-status.json`.
- The live-run configuration files in `config/` carry pinned `content_hash`
  values over a closed field set, so the budget shape in that schema cannot gain
  a field without invalidating every one of them.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt: unbounded retry until the verifier is satisfied | none | simple | unbounded spend; a proposer that learns to please the verifier converges on agreement, not truth | rejected: no declared bound, and model agreement is not proof |
| Wrap: bounded rounds capped by a literal in the loop | prototype | small diff | a magic number is not a declared budget, is not durable, and cannot differ per run | rejected: ADR-0026 forbids a threshold that is not an executable, declared bound |
| **Interoperate: bounded rounds capped by the run's declared `BudgetLimits`, enforced durably, with a named terminal state; verifier independence measured from the two resolved gateways** | this slice; `tests/test_phase2_refinement_rounds.py`, 35 cases | the cap is per-run, recorded at creation, and enforced by the workspace; the stopping bound is named; independence stops being assertable | one SQLite table rebuild; a sealed read-only open mode; asymmetric round-one identity | chosen |
| Build/defer: leave the loop single-round and add refinement in a later phase | — | no migration | leaves "the verifier faulted it, now what" permanently unanswered inside a run | rejected |

## Decision

### The round cap is declared, durable, and enforced

`BudgetLimits` gains `max_refinement_rounds: int = 1`. The default of `1` is the
*identity*, not a tuned constant: a run that declares nothing behaves exactly as
it did before this ADR — one round, no refinement. A caller that wants
refinement must say how many rounds it will pay for.

The cap is written into the `budgets` row at `create_run` alongside
`used_refinement_rounds`, and `create_run` refuses to re-create an existing run
with a different cap. Enforcement lives in
`SQLiteWorkspace.reserve_refinement_round`, which raises
`RefinementRoundsExhausted` for any round beyond the cap and is idempotent for a
round already granted, so a crash between granting a round and enqueueing its
job cannot consume two.

The cap is deliberately **not** an `exhausted_dimensions` entry. `reserve_call`
refuses every call once any dimension is exhausted, and a run on its last
permitted round must still be able to finish that round.

`run_to_terminal`'s bound is derived from the cap (`2 * cap + 2`), never from a
literal. Its old `max_steps=4` default is gone; an explicit value is still
accepted, and `live_gate.execute_live_gate` still passes `max_steps=2`.

### Exhausting the allowance is its own terminal state

`RunStatus.REFINEMENT_EXHAUSTED` (`"refinement_exhausted"`) means: a refuting or
defective finding warranted another round and a declared bound refused it. It is
neither a success nor a failure, and it is not `unresolved`. Alongside it, the
append-only `run_stop_records` table names *why*:

| `stop_reason` | `stop_bound` | terminal status |
|---|---|---|
| `no_refinement_warranted` | `null` | `awaiting_review` or `unresolved`, as before |
| `budget_bound` | the binding dimension (`cost`, `input_tokens`, `output_tokens`, `attempts`, `time`) | `refinement_exhausted` |
| `refinement_round_cap` | `refinement_rounds` | `refinement_exhausted` |
| `non_success` | `null` | `unresolved` |

Budget is evaluated **before** the round counter, so when both would refuse the
next round the operator is told the money or the tokens ran out rather than that
a counter did. `binding_bounds` records every bound that was binding, and
`stop_bound` names the first in the fixed order cost, input tokens, output
tokens, attempts, time.

The projection for "can we afford one more round" is the *measured* usage of the
round that just finished — exact integers summed from `model_calls`, no
floating point, no growth model — plus any dimension the budget snapshot already
reports exhausted. Token and cost accounting aggregate across rounds because
`record_usage` was already per call; the tests assert the totals equal the sum
over all rounds.

### Refinement is conditional, from fields the verifier schema already requires

`classify_finding` maps one schema-valid finding artifact to
`RefinementOutcomeClass` using only `result_type`, `findings[].outcome` and
`recommendation`:

- `refuting` — any `outcome == "contradicts"`, or `recommendation == "reject"`.
- `defective` — `result_type` in `{inconclusive, failure}`, or any
  `outcome == "unresolved"`, or `recommendation == "unresolved"`.
- `supporting` — every outcome `supports` and `recommendation == "manual_review"`.
- `indeterminate` — schema-valid but says nothing either way, e.g. an empty
  findings list.

Only `refuting` and `defective` warrant another round. `supporting` and
`indeterminate` do not: a finding that supports the candidate must not trigger a
pointless re-proposal, and an empty finding list is treated conservatively as
saying nothing rather than as a fault. No new classifier was invented and no
model is asked to grade its own output. Every completed round is recorded
immutably in `refinement_rounds` with its candidate hash, finding hash,
classification and trigger decision, so the decision is auditable rather than
re-derived.

### What multi-round does to verifier independence — the honest answer

**It does not widen the verifier's context, and it does narrow the verifier's
causal independence. Both are recorded.**

What is preserved:

- Prior findings go to the **proposer only**. Round N+1's verifier context has
  the same key set as round one's; the tests assert that equality and assert
  that neither the round-one finding text nor the round-one candidate appears in
  the round-two verifier's bytes.
- The exclusion list *grows*. Every earlier round's proposal identifiers and
  model-call identifiers are added to `excluded_entity_ids`, so a later round
  cannot become a back door into material the independence policy withheld from
  round one.
- Each round writes its own `VerifierContextManifest` — `verifier_manifests` is
  now keyed `(run_id, round_index)` — so each round's isolation is separately
  auditable, hash for hash, against the bytes that round's verifier received.

What is lost, and is now stated in the record rather than inferred:

- The candidate the round-N+1 verifier reviews **was shaped by that verifier's
  own earlier findings**. The verifier is still isolated from the proposer's
  narrative, but it is no longer independent of its own prior output. A
  multi-round run can therefore drift toward a candidate that satisfies this
  verifier rather than one that is correct — which is precisely why the run is
  bounded and why nothing here can produce an `EpistemicWarrant`.
- The manifest records this directly: `candidate_shaped_by_rounds` lists the
  rounds whose findings shaped the candidate (empty on round one), and
  `withheld_prior_finding_hashes` lists the finding artifacts the proposer was
  shown and this verifier was not.
- `context_isolated` therefore must **not** be read as "the verifier's judgement
  is independent of everything that came before". It means exactly what it is
  measured from: the proposer's model call is excluded and the proposer's
  narrative is absent from these bytes.

Across roles, in the same place, for symmetry:

- `different_provider` and `different_model` are now **computed** from the two
  resolved gateway configurations, never accepted as flags. A run whose roles
  resolve to the same provider records `different_provider: false` even if the
  operator asked for `true`. Unresolvable gateway identity — a scripted fixture,
  say — records `false`: an unmeasurable independence claim is refused, not
  assumed. One gateway object serving both roles is never independent.
- `separate_model_call` is asserted by construction (this loop always makes two
  calls against two request artifacts) and `context_isolated` is derived from the
  serialized verifier context that was actually produced.
- Three dimensions remain operator-declared, and this is a real gap:
  `deterministic_checker`, `independently_implemented_checker` and
  `formal_kernel` are facts about how a checker was built, not about how it was
  called, and nothing the loop observes settles them. An operator can still
  assert `formal_kernel=True` for a model gateway. Closing that requires a
  checker registry the loop can interrogate and is out of this slice.
- A multi-round cross-provider run may therefore claim: separate calls, isolated
  contexts, distinct providers, distinct models, per-round manifests. It may
  **not** claim that the verifier's judgement is independent of its own earlier
  findings, nor that the checker is independently implemented or formal.

### Round-indexed identity, with round one keeping its historical name

Job IDs, idempotency keys, proposal IDs, event keys, manifest IDs, request IDs
and model-call IDs are round-injective. Round one keeps its pre-ADR-0041
spelling (`proposal.{run}.proposer`) and later rounds carry an explicit segment
(`proposal.{run}.proposer.round.2`, `job:{run}:proposer:round:2`,
`call.{run}.verifier.round.2.attempt.1`).

The asymmetry is deliberate. Proposal and manifest identifiers appear verbatim
in `render_durable_report`, whose hash is pinned in committed evidence, so
renaming round one would make sealed Phase 2 evidence unreproducible from
current code. With the suffix scheme, regenerating the demonstration reproduces
the pinned `report_hash`, `audit_event_replay_hash`, `accepted_dossier_hash` and
verifier-context hash exactly. Nothing has to parse a name to learn a round:
`jobs.round_index` and the `refinement_rounds` ledger carry it explicitly.

Crash-idempotency is preserved. `LateCommitRejected` and
`fault_after_proposal_artifact_once` behave unchanged, and the new suite proves
a crash between round two's artifact and its semantic commit replays to exactly
four proposals, four `proposal_imported` events with four distinct idempotency
keys, and two recorded round-two proposer attempts — the failed attempt is kept,
not erased.

### Per-role provider selection on the run path

ADR-0038's single-role gate is factored into `_role_gateway` and applied to
**both** roles unchanged: the configuration and the pinned snapshot must load,
the selected provider must equal the configured provider, the snapshot must name
that provider and be the one the configuration names and be bound to the
configured model, and the adapter is then built through
`provider_registry.build_gateway`. No role falls back to a default adapter, and
the ADR-0038 defect-2 regression class is not reintroduced on the second role.

`start` and `advance` accept `--verifier-provider`, `--verifier-config` and
`--verifier-pricing-snapshot`. `--verifier-provider`'s choices are the same
registry-derived `RUN_PROVIDER_CHOICES` as `--provider`, so a provider added to
the registry is selectable for either role with no further edit. Omitting the
verifier flags reuses the proposer's provider, which is the unchanged
single-provider path. The verifier role passes its own `_live_inputs` and
`preflight_live_gate` before the run starts, so a cross-provider run whose
verifier provider is unconfigured refuses rather than starting half-configured
or quietly borrowing the proposer's credentials.

`live_run_configurations` is keyed `(run_id, role)`, and per-role pricing
snapshots and per-role output-token reserves flow into the loop so cost
aggregates correctly across two rate cards rather than assuming one
`pricing_snapshot_id` per run.

`_live_inputs`, `load_provider_environment`, `provider_secret_values`,
`RUN_PROVIDER_CHOICES` and the unconfirmed-pricing refusal are ADR-0038's and
are untouched.

### Sealed read-only workspaces

`SQLiteWorkspace(path, read_only=True)` opens the file immutable, copies it into
an in-memory database, applies pending migrations to the copy, and then refuses
any durable write with `SealedWorkspaceError`. Read-only Phase 2 subcommands use
it. This is what keeps a schema migration from rewriting ADR-0022 protected
evidence in place; verified by hash before and after, including no `-wal`/`-shm`
side files.

## Consequences

**Migration.** `migrations/0004_phase2_refinement_rounds.sql` adds
`budgets.max_refinement_rounds`, `budgets.used_refinement_rounds` and
`jobs.round_index`; rebuilds `runs` to widen the status `CHECK`; rebuilds
`verifier_manifests` with `round_index` and `UNIQUE(run_id, round_index)`;
rebuilds `live_run_configurations` with `PRIMARY KEY(run_id, role)`; and creates
`refinement_rounds` and `run_stop_records`. Rebuilding a referenced table needs
foreign keys off, which is impossible inside the migration transaction, so the
runner honours one declared directive — `-- adaivy-migration: rebuild-tables` on
line 1 — under which it disables foreign keys and enables `legacy_alter_table`
for exactly that file, restores both afterwards, and fails closed if
`PRAGMA foreign_key_check` reports any violation. An unrecognised
`-- adaivy-migration:` directive is a `MigrationError`. Existing workspaces open
and replay: the committed `reports/phase-2/workspace.sqlite3` migrates in a
read-only in-memory copy and still reproduces its pinned report hash, with its
single manifest labelled round one and `used_refinement_rounds = 0`.

**Reproducibility.** Round-one request, candidate, finding and verifier-context
bytes are unchanged, so a single-round run is byte-identical to before. The
traceable report gains lines only when a run actually refined (more than one
round, or a named stopping bound), so every pre-ADR-0041 report renders
identically. Two independent processes with identical inputs produce
byte-identical semantic state across a three-round run. No wall clock or
randomness enters identity; all arithmetic is integer.

**Operational.** A multi-round run makes more model calls, and the wall-clock
job deadline set at `start` still applies to every round: a run whose deadline
expires mid-sequence parks in `running` with timed-out jobs, unchanged from
ADR-0007 but now more reachable. `reserve_call`'s pre-call estimate uses the
per-role output reserve, so a small cost cap can refuse a call before the
round-level projection is ever consulted; that path still lands in `unresolved`
with `stop_reason = non_success`, not in `refinement_exhausted`.

**Security and licensing.** No new dependency, no network, no subprocess. Only
non-secret provider and model identifiers enter the independence record. Nothing
here creates an `EpistemicWarrant`, approves semantic alignment, asserts source
applicability, or sets novelty or significance; every round still commits
proposals with `disposition = "proposal"`, and the tests assert the target claim
remains `unknown` after a cap-exhausting run.

**Negative consequences, stated plainly.**

1. Round-one identity is spelled differently from later rounds. Chosen over
   breaking sealed evidence; documented, and the round is carried in a column.
2. Multi-round runs cost the verifier's causal independence, as set out above.
   The record says so; the code cannot prevent it.
3. Three independence dimensions are still assertable by an operator.
4. The refinement-round cap is not yet expressible in a live-run configuration
   file, so live runs get the default of one round. Adding it would invalidate
   every pinned `content_hash` in `config/`.
5. `execute_live_gate` remains single-role and single-round; it still builds one
   gateway for both roles and now records the *measured* `different_provider:
   false` that follows from that, which is what its own assertion checks.
   Cross-provider verification is reachable through `phase2 start`/`advance`,
   not through the live gate.
6. `deterministic_fake_results` still returns a canned even-integers proof
   regardless of the problem. Out of scope here, and this slice's tests do not
   depend on that content: every round is an explicit scripted sequence.
7. No cross-provider run has been executed live, and none was attempted. Every
   cross-provider property here is measured offline from resolved adapter
   configurations; auth acceptance, response shape and token accounting for a
   two-provider run are untested, exactly as ADR-0038 records for the
   single-provider case. Their absence is not a pass.
8. `--verifier-provider fake` alongside a live proposer is accepted and builds a
   scripted verifier. That is useful for a dry run and is a footgun: the
   resulting manifest correctly records `different_provider: false`, but a reader
   must check the run's recorded configurations to see that no verifier model was
   called at all.

## Blueprint deviation

None to the trust architecture. Model and verifier output remain proposals in
every round; the Phase 1 core is unchanged and untouched by the loop.

One deviation from a local convention, recorded rather than hidden: migration
`0004` disables foreign keys and enables `legacy_alter_table` for the duration
of one file. It is the only mechanism SQLite offers for widening a `CHECK`
constraint on a referenced table, it is gated behind an explicit in-file
directive, and it is followed by a `PRAGMA foreign_key_check` that fails the
migration on any violation. Revisit if a future migration needs the same escape
hatch for a table with rows that a rebuild would silently drop.

## Validation and revisit trigger

`tests/test_phase2_refinement_rounds.py` (35 cases) is the acceptance suite:

- a refuting round one repaired and converging on round two, with four jobs,
  four proposals, four calls, four distinct round-indexed identities, one
  `refinement_round_enqueued` event and an unchanged dossier;
- round two's proposer receiving round one's structured findings and prior
  candidate, under its own versioned template, while round one's context has no
  `refinement` key at all;
- a run exhausting the declared cap landing in `refinement_exhausted` with
  `stop_bound = refinement_rounds`, not in `unresolved`, and making no calls for
  the round it was refused;
- a run stopped by the cost budget before the cap, naming `cost`, with
  `rounds_used = 1` of `5`;
- the same scripts with a generous cost cap stopping on the cap instead, so the
  precedence is demonstrated in both directions;
- a crash inside round two replaying with no double commit and both attempts
  retained;
- per-round manifests separately recorded, each hashing the exact bytes its
  round's verifier received, with round two's exclusion list containing round
  one's proposals and calls and its `candidate_shaped_by_rounds == (1,)`;
- a supporting finding never enqueueing a pointless round;
- measured independence: cross-provider `true`, same-provider `false`, an
  operator-asserted `true` on a same-provider run overridden to `false`, one
  shared gateway never independent, unresolvable identity refused;
- each role routing to its own adapter (`openai` and `anthropic` instances, no
  network), the verifier role passing the same ADR-0038 binding gate as the
  proposer, and a live role without a configuration failing closed;
- a sealed read-only replay refusing writes and leaving the file's bytes
  identical, and every reporting subcommand leaving a workspace file's bytes
  unchanged;
- through the CLI: the declared cap recorded and surfaced by `phase2 rounds`, a
  cap below one refused with no run record created, a verifier configuration
  supplied without `--verifier-provider` refused rather than ignored, live inputs
  for a scripted verifier refused, an unconfigured live verifier refusing the run
  with no run record created, and `--verifier-provider` choices asserted to be
  derived from the registry rather than re-listed.

`make check` and `python3 -m unittest discover -s tests` (1413 tests, 16
skipped) both pass at commit `6ac08e3`, with `reports/` unmodified afterwards.
Two independent processes produce byte-identical semantic state for a
three-round run, the sealed `reports/phase-2/workspace.sqlite3` replays to its
pinned report hash with its bytes unchanged, and a regenerated Phase 2
demonstration reproduces the pinned `report_hash`,
`audit_event_replay_hash`, `accepted_dossier_hash` and verifier-context hash.

Revisit if any of the following appears: a run whose refinement converges by
pleasing the verifier rather than fixing the mathematics, which would mean the
cap is too high or the trigger too weak; a measured retention gain that justifies
carrying prior findings to the verifier as well, which would require re-deriving
what `context_isolated` means; a checker registry that would let the loop measure
the remaining three independence dimensions; or a live-run configuration schema
version that can carry the round cap.
