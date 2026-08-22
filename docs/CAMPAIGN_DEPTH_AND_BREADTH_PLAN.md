# Campaign Depth and Breadth Plan

**Status:** proposed roadmap; requires new ADRs before implementation
**Date:** 2026-08-22
**Predecessor:** [`END_TO_END_RESEARCH_RUNTIME_PLAN.md`](END_TO_END_RESEARCH_RUNTIME_PLAN.md)
(Slices 1–8, closed offline at `main@953e7a7`)
**Purpose:** reverse the deliberately conservative bootstrap decisions that make
the live campaign protocol shallow, without weakening exactness, provenance, or
the trust boundaries that the bootstrap phase established.

## 1. Why this phase exists

Slices 1–8 proved the ledger, checkpoint, budget, corpus, retrieval, and
verification machinery in a deterministic offline fixture. An audit of
`main@953e7a7` shows that the machinery is sound but the *model-facing*
protocol on the live path would make even a very capable model shallow:

1. **The model cannot see the problem.** The live planner context carries only
   `target_hash`; the statement text is hashed at freeze time and never stored
   as a retrievable artifact (`campaign/planner.py`, `runtime/lead.py`).
2. **One usable research call.** Every shipped live provider config sets
   `max_attempts: 2`; the activation probe consumes one, leaving a single
   2,048-output-token research call per campaign.
3. **The rich v2 protocol is fixture-only.** `EndToEndCampaignRunner` (the
   17-action contract with literature, retrieval, and experiment stages) is
   constructed only by `fixture_runtime.py`, where all actions are Python
   closures. The model-driven `SequentialCampaignRunner` speaks the v1
   vocabulary and rejects every literature action.
4. **No feedback, no memory.** Verifier verdicts and counterexamples are
   withheld from the lead; sandbox diagnostics are explicitly never fed back;
   only the most recent tool result is visible as bytes; there is no notes or
   artifact-read action.
5. **Failure is terminal and sometimes destructive.** Any malformed action or
   failed experiment ends the campaign; planner bound exhaustion raises outside
   the runner's protective `try`, discarding the entire ledger — contradicting
   the runner's own no-lost-attempt contract.
6. **The corpus is not filled at runtime.** There is no snapshot fetcher, no
   PDF/LaTeX ingestion path, `pending_owner_activation` on both corpus
   activations, ten hash-pinned Crossref candidates per human-acknowledged
   search, one human-typed acquisition URL per run, and a one-pass
   search→retrieve ladder. Hundreds of relevant papers for a hard target
   (e.g. an Erdős problem) are unreachable by design.
7. **The sandbox is an instrument, not a workspace.** Stdlib-only single-file
   Python, hard-bound to one exact-graph fixture target, 60 s CPU ceiling,
   one-shot semantics.

## 1b. Design stance: freedom inside the boundary, rigor at the boundary

The bootstrap phase drifted into treating the model as a compiler: one
validated instruction in, one validated action out, failure fatal. That
architecture removes exactly the capacities that let a model be creative on a
mathematical problem — reading the problem, holding partial ideas, conjecturing
cheaply, failing often, reacting to counterexamples, and wandering the
literature.

The corrected stance is that **trust lives at the boundary, not inside the
loop.** Inside the campaign, the model may explore freely: wrong conjectures,
dead-end programs, speculative notes, and wide reading are budgeted costs, not
violations. Nothing the model produces is believed. At the boundary, nothing
changes: only an exact host-side verification can turn any of it into a
recorded result, and provenance captures the whole trail either way. Every
slice below widens the interior; none weakens the boundary.

## 2. Governing constraints (unchanged)

These bootstrap invariants are kept, not relaxed:

- **Exactness.** Verifiers refuse floating-point candidate content; meaning is
  established only by exact host-side re-derivation. Numerical solvers remain
  excluded from the trust path.
- **Trust boundary.** Network access and credentials never enter the
  experiment sandbox; acquisition and provider calls cross separately governed
  services with their own budgets and ledgers.
- **Provenance.** Every action, artifact, and cost remains ledgered,
  checkpointed, and replayable; retrieved material remains
  `untrusted_inspiration_candidate` until exactly verified.
- **Human publication gate.** `before_announcement` approval remains
  unconditional.
- **Budget honesty.** Wider limits are still limits: one unified campaign
  budget, per-capability sub-budgets, and terminal unresolved reports on
  exhaustion.

Each slice that widens a previously ADR-narrowed behavior requires its own
superseding ADR; this plan authorizes nothing by itself.

## 3. Slices

Numbering continues from the predecessor plan.

### Slice 9 — Ledger durability hotfix

*Bugfix; no new ADR (restores the documented ADR-0065 contract).*

- Move the planner invocation (`runner.py:508`) inside the protective `try`
  that already wraps action handling, so context-bound and budget-bound
  exhaustion become recorded terminal reasons (`planner_bounds_exhausted`,
  `context_bound_exhausted`) instead of exceptions that discard the ledger at
  `campaign_cli.py:1975`.
- Regression tests: a campaign that exhausts `max_attempts` mid-run and one
  that exceeds `max_context_bytes` must both leave a complete ledger, a
  terminal report, and exit 0.

Exit: no code path can lose a partially completed campaign's records.

### Slice 10 — Problem-visible context and durable model memory

*ADR required: planner context contract v2.*

- Store the frozen target statement, formalization, and assumption manifest as
  campaign artifacts at freeze time; include the statement text (bounded,
  hash-attested) in every planner payload.
- Add a `read_artifact` action: return bounded bytes of any in-provenance
  artifact by hash (prior tool results, own derivations, evidence cards).
  Reads are ledgered and budgeted but cheap; they are the model's memory.
- Add a `note` action: durable, budgeted scratch text attached to a branch,
  echoed back in context summaries.
- Feed verification outcomes back: the verdict, and for refutations the exact
  counterexample or failing invariant, become structured context records.
  Feed sandbox failure diagnostics (exit status, bounded stderr) back the same
  way. Both remain labeled untrusted-for-warrant, trusted-as-record.
- Surface runner state the model is currently punished for not knowing:
  suspended branch ids, per-branch last status, remaining sub-budgets.

Exit: a transcript shows the lead quoting the problem statement, re-reading an
earlier tool result, and revising a candidate in direct response to a
verifier counterexample.

### Slice 11 — Call economics and non-terminal failure

*ADR required: supersedes the one-shot clauses of ADR-0065/ADR-0066.*

- Raise ceilings: `max_attempts` becomes a real per-campaign budget
  (shipped configs move from 2 to an operator-chosen value, e.g. 64–256);
  per-call output tokens configurable to model limits (e.g. 32k);
  `MAX_CONTEXT_BYTES_CEILING` raised toward the provider window (with a
  deterministic rolling-window policy over `previous_actions`: older actions
  collapse to hash + rationale summaries, recoverable via `read_artifact`).
- Malformed actions get a bounded repair loop: the validation error is echoed
  to the model and the same sequence number is retried up to N times before
  `action_rejected` becomes terminal.
- A failed experiment (`run_program` non-completion) is a recorded non-terminal
  outcome while tool-run and campaign budgets remain; its diagnostic enters the
  next context (Slice 10). Determinism-refusals likewise.
- `ask_user` becomes resumable on the live path: action-level resume (already
  built for the fixture path in ADR-0075) is extended to
  `SequentialCampaignRunner`, so an answered question continues the same
  campaign rather than orphaning it.

Exit: an adversarial test campaign survives one malformed action, one failed
experiment, and one interruption/resume, and still reaches a verified terminal
result under one budget.

### Slice 12 — Model-driven v2 runtime (unify the two runners)

*ADR required: retires the v1/v2 split.*

- `GatewayCampaignPlanner` drives `EndToEndCampaignRunner`: the live model
  emits v2 actions; the fixture closures become one injected effect-set among
  several, keeping the offline gate byte-deterministic.
- Relax the single-pass stage ladder to per-cycle ordering: a campaign may run
  many search→acquire→embed→retrieve cycles interleaved with research; the
  guards that survive are "a recorded search precedes the first substantive
  research action" and "retrieval evidence used in planning must come from a
  published generation."
- Literature effects execute asynchronously against the persistent corpus
  service; new generations appear at explicit `refresh_corpus` actions exactly
  as today.

Exit: one small-budget live campaign in which every action is model-chosen
executes literature → retrieval → experiment → exact verification end to end,
and the offline `make check` gate still passes unchanged.

### Slice 13 — Real ingestion: fetcher, PDF/LaTeX parsing, bulk rights

*ADR required: supersedes the no-fetcher and metadata-only clauses of
ADR-0067; activates the corpus-service snapshot gate.*

- Implement the snapshot fetcher behind the existing
  `pending_owner_activation` gate: allowlisted open-access origins (e.g. arXiv
  bulk, OpenAlex/S2 OA links), pinned rate limits, resumable tranches, bytes
  landing in the grow-only data root exactly as the local-archive path does.
- Add a pinned PDF and LaTeX-source extraction toolchain producing plain text
  with exact character spans (extraction tool + version recorded per document;
  spans remain `utf8_exact_char_spans` over the extracted text, with the
  extractor identity part of the provenance chain).
- Derive per-document rights in bulk from machine-readable license metadata
  under the existing policy engine; unknown licenses quarantine as today.
- Bridge or retire the disconnected silos: the arXiv metadata store
  (`corpus/`) and Phase 4B acquisition feed the one persistent corpus service
  rather than remaining parallel dead ends.
- Chunked embeddings: documents embed as bounded chunks (not one vector per
  document), with chunk spans as the retrieval unit and per-chunk evidence
  cards; raise the per-tranche ceiling from 2,048 documents to an
  operator-budgeted value.

Exit: one operator command ingests several hundred licensed full-text papers
from an allowlisted snapshot into a retrievable generation, and a second run
ingests only deltas.

### Slice 14 — Discovery at scale, campaign-generated queries

*ADR required: supersedes ADR-0051's per-search human acknowledgement and
implements ADR-0068 (result following).*

- Replace the hash-pinned 10-result single request with paginated, budgeted
  discovery: cursor/offset support, multiple providers (Crossref, arXiv API,
  OpenAlex), per-campaign literature sub-budget measured in requests and
  bytes, still credential-free where the provider allows.
- Campaign-generated queries: the initial human authorization covers a query
  *policy* (grounded-term expansion rules, budget, origin allowlist) instead
  of each query string; every generated query is still ledgered with its
  grounding evidence. Discovery grants inspection authority only — acquisition
  authorization remains a separate rights-checked step.
- Implement depth-one result following per ADR-0068: references/links from an
  acquired document may be enqueued as discovery candidates with
  `max_followed_per_run` and origin allowlists enforced.
- Batch acquisition: N allowlisted URLs per run under the campaign budget,
  replacing the one human-typed URL, with the same no-redirect/no-header
  discipline.

Exit: a dry-run campaign against an Erdős-class target discovers and ranks
several hundred candidates, acquires the licensed subset (≥100 documents)
without per-search human interaction, and every request is attributable to a
ledgered query with recorded grounding.

### Slice 15 — Exact scientific workspace sandbox

*ADR required: supersedes ADR-0066's empty-package-set and one-target
clauses.*

- Fork the sandbox image: a new digest-pinned image with a small allowlisted
  set of **exact** packages (e.g. `sympy`, `gmpy2`, `networkx`; explicitly no
  numpy/scipy on the candidate path), installed offline with recorded hashes
  per the Phase 4A dependency standard. New lock, new 16-probe activation.
- Multi-file workspace: a campaign-scoped writable volume (still
  network-none, still credential-free) that persists across `run_program`
  calls within one campaign, so programs can build on earlier outputs and
  data files; contents are hashed into the ledger at each run boundary.
- Configurable long computation: raise ceilings to operator-budgeted values
  (e.g. up to 1 h CPU, several GB memory) charged against the unified
  campaign budget; keep the determinism replay gate, with replica count
  configurable for long runs.
- Generalize targets: the activation binds to a target *schema class*, not
  one fixture file; new exact verifier classes are added per problem family
  through the existing router registration path (verifiers stay host-side,
  outside the container, refusing floats as today).
- Iteration semantics from Slice 11 apply: failed runs are recorded,
  diagnosable, non-terminal.

Exit: a live campaign iterates a sympy-based exact search program at least
three times against a non-fixture target, with each iteration reacting to the
previous run's output, and the final candidate verified by an exact host-side
verifier.

### Slice 16 — Live acceptance gate and truthful documentation

- Define the **live** end-to-end acceptance gate: a small-budget real-provider
  campaign on a real (modest) target exercising Slices 10–15, with recorded
  costs, alongside the unchanged offline `make check`.
- Update `CAPABILITY_STATUS.md`, `README.md`, `TECHNICAL_BLUEPRINT.md`, and
  the runbook from the matrix; retire the "offline result must not be read as
  activation" caveat only for capabilities that have genuinely crossed their
  gates.
- Update shipped Makefile/live configs to the new defaults so the checked-in
  configuration can actually execute the protocol it documents.

Exit: a fresh operator can run one live campaign to a genuine terminal
condition, and no document overstates or understates what is activated.

## 4. Ordering and dependencies

```text
Slice 9 (hotfix)  ──────────────┐
Slice 10 (context/memory) ──┐   │
Slice 11 (economics/retry) ─┴─► Slice 12 (model-driven v2)
Slice 13 (ingestion) ───────┐
Slice 14 (discovery) ───────┴─► feed Slice 12 campaigns at scale
Slice 15 (workspace sandbox) ─► independent; lands before or after 12
                                All ─► Slice 16 (live gate + docs)
```

Slice 9 is immediate. Slices 10 and 11 are the depth unlock and can proceed in
parallel. Slice 12 depends on both. Slices 13–15 are independent tracks.
Slice 16 closes the phase.

## 5. Explicit non-goals

- No relaxation of exact verification: wider search, never wider proof.
- No network or credentials inside the experiment sandbox, ever.
- No autonomous publication, novelty assertion, or budget self-increase.
- No retention of content past a binding takedown or license withdrawal.
- No numerical-solver dependence on any trust path.
