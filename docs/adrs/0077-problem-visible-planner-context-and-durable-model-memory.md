# ADR-0077: Problem-visible planner context and durable model memory

- **Status:** accepted
- **Date:** 2026-08-22
- **Blueprint requirement:** campaign depth and breadth plan, Slice 10
- **Supersedes in part:** ADR-0065's planner-context clauses (hash-only target
  identity, latest-tool-result-only context, verifier and sandbox diagnostics
  structurally withheld from the lead, suspended-branch state unsurfaced)
- **Decision owners:** repository owner

## Context

An audit of the live campaign protocol at `main@953e7a7` found that the
model-facing context makes even a capable model shallow, by construction:

1. `freeze_target` hashes the target statement, formalization, and assumption
   manifest and discards the text; the planner context carries only
   `target_hash`. The model literally cannot read the problem it is asked to
   research.
2. The planner context carries only the latest tool result as bytes. Earlier
   tool results, its own derivations, and evidence exist only as hashes with
   no way to re-read them.
3. Verifier verdicts and counterexamples are recorded as tool runs but never
   fed back (`campaign_cli._build_verifier_router` explicitly documented this
   isolation); sandbox failure diagnostics were "retained but never fed back
   as repair guidance" (ADR-0066).
4. The runner tracks a suspended-branch set and fatally rejects any action on
   a suspended branch, yet never tells the planner which branches are
   suspended.

The design stance correction (plan §1b): trust lives at the boundary, not
inside the loop. Nothing the model reads or writes here acquires warrant;
exact host-side verification remains the only path to a recorded result.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Keep hash-only context | bootstrap ADR-0065 | maximal isolation | model cannot do research; audit finding 1 | none crossed |
| Feed everything raw, unlabeled | — | simple | verifier text could be read as instructions/warrant | violates proposal-not-trust |
| Bounded, labeled, ledgered feedback (chosen) | this ADR | model can read, remember, and react; boundary unchanged | larger context payloads; two new action types | all listed below |

## Decision

### 1. Frozen-target artifacts and the visible statement

At campaign start the operator entrypoint derives, from the same dossier that
produced `target_hash`, the exact canonical bytes whose hashes the frozen
target record already carries:

- the target claim statement (`target_statement_hash` preimage),
- the formalization structure (`formalization_statement_hash` preimage),
- the assumption manifest (`assumption_manifest_hash` preimage).

`runtime/lead.py` gains `frozen_target_context(dossier)` returning these bytes
alongside the plain statement text. The runner receives them as a
`FrozenTargetArtifacts` value and validates byte-for-byte that each artifact
hashes to its declared identity (fail closed on mismatch).

The bounded statement text (at most 65,536 UTF-8 bytes) and its hash are
included in **every** planner payload, so the model always sees the problem it
is working on and can verify the text against the hash in `target.json`.

**Ledger closure constraint.** The campaign export closure rule (every stored
artifact must be introduced by a model-call, tool-run, or import record)
predates this ADR and is kept. Frozen-target artifacts are therefore NOT
placed in the campaign artifact store; they are persisted durably under the
campaign root at `target-artifacts/sha256-<hex>` (append-only, hash-named,
verified on write) and surfaced to the planner as `frozen_artifact_hashes`.
They are readable through `read_artifact` but are not members of the ledger's
`available` set, so no action may name them as ledger inputs. This preserves
the existing closure validator unchanged.

### 2. Two new v1 actions: `read_artifact` and `note`

The closed action schema moves to version `1.1.0`
(`schemas/model-campaign-action-v1.schema.json`); the parser accepts exactly
that version — no mixed-version campaigns.

- `read_artifact` carries `read_artifact_hash`, which must name either an
  in-provenance stored artifact (the runner's `available` set, which excludes
  verifier-private artifacts) or a frozen-target artifact. The bytes (bounded
  to 65,536; deterministic prefix truncation with an explicit truncation flag)
  are echoed in the **next** planner context. Reads are ledgered as normal
  model actions, consume an action slot, and consume **no** tool run.
- `note` carries `note_text` (bounded to 8,192 bytes), stored as a text/plain
  artifact and attached to the action's branch. All notes of the campaign are
  echoed, in recording order, in every later planner context. Notes are the
  model's durable scratch memory and carry no warrant.

### 3. Verification and sandbox feedback

After every `verify`, and after every `run_program`, the runner appends a
structured feedback record to the planner context:

```json
{"kind": "verification"|"experiment", "action_id": "...", "branch_id": "...",
 "status": "completed"|"failed"|"incomplete", "result_hash": "sha256:...",
 "result_excerpt": "<bounded, deterministic UTF-8 decode>",
 "stderr_excerpt": "<experiments only, bounded>",
 "untrusted_for_warrant": true}
```

The excerpt carries the verifier's exact verdict payload — for refutations,
the counterexample / failing invariant the exact verifier recorded. The
records are labeled `untrusted_for_warrant: true`, the live prompt restates
that label, and nothing about the warrant rules changes: verifier-private
artifacts stay outside `available`, only the bounded excerpt travels, and no
feedback record can be selected, verified, or exported as evidence. The
context window keeps the most recent 8 feedback records (deterministic).

### 4. Runner state the model was punished for not knowing

Every planner context now carries:

- `suspended_branch_ids` (sorted): reusing one remains a rejection, but the
  set is now visible;
- `branch_last_status` (sorted `(branch_id, status)` pairs): the last recorded
  action status per branch;
- remaining sub-budgets: `actions_remaining` and `tool_runs_remaining` were
  already present; the live planner adapter additionally reports its own
  remaining model attempts, input/output tokens, and cost reserve.

### 5. Prompt and payload versioning

`CAMPAIGN_PROMPT_VERSION` moves to `1.1.0`. The payload gains the fields above;
`previous_actions` and tool-result bytes remain explicitly labeled untrusted
data. The planner request hash covers the new semantic fields (hashes and
texts, never raw tool bytes), so identical contexts still hash identically
across runs.

## What this ADR does NOT change

- No warrant path: verifier output remains a record, never trust; the
  guardrail block stays constantly false.
- No relaxation of exact verification, artifact bounds, provenance closure,
  or the append-only root.
- Terminal semantics of failures are unchanged here (ADR-0078 / Slice 11 owns
  non-terminal failure and repair).

## Consequences

- Campaign exports produced after this ADR hash differently from bootstrap
  exports (new planner request-hash fields, schema `1.1.0` actions). Old
  recorded campaigns still verify: record schemas are unchanged.
- Context payloads grow; the byte bound still applies and is enforced before
  any provider request (recorded terminal per Slice 9).
- Fixture scripts and the offline `make check` gate emit `1.1.0` actions; the
  offline path remains byte-deterministic.
- Two new ActionType members (`read_artifact`, `note`) are append-only enum
  additions; the v2 end-to-end contract is unaffected.
