# End-to-End Research Runtime Plan

**Status:** proposed implementation plan  
**Date:** 2026-08-22  
**Purpose:** turn AdaIvy's existing bounded components into one budgeted,
resumable research runtime that can search literature, grow a persistent corpus,
retrieve evidence for ideation, investigate candidates, and invoke formal or
exact verification without routine human interruption.

This plan does not itself activate a capability. Implementation begins with a
new ADR that explicitly supersedes the narrower decisions identified below.

## 1. Desired operator experience

An operator supplies a problem, an AdaIvy provider profile, and budgets, then
starts one campaign. After that initial authorization, the campaign should run
without routine approval pauses until it:

- reaches the configured budget or deadline;
- produces a verified result or an honest unresolved report;
- encounters a genuine ambiguity in the problem statement;
- encounters material that cannot be processed under the approved rights
  policy; or
- detects a safety or infrastructure failure that cannot be handled within the
  approved policy.

The normal loop is:

```text
problem and budget
  -> campaign planning
  -> literature query and discovery
  -> authorized acquisition and parsing
  -> persistent corpus and embedding ingestion
  -> hybrid retrieval into the campaign context
  -> derivation, experiments, falsification, and branch updates
  -> optional intermediate verification
  -> final exact and/or Lean verification
  -> result or explicit unresolved obligations
  -> automatic record-driven LaTeX draft
```

The host Codex or Claude session may install, configure, start, inspect, resume,
or import work into AdaIvy. Material research performed outside the campaign
remains explicitly attributed as external work.

## 2. Governing decisions

### 2.1 AdaIvy credentials and budget own the research workload

All model calls made after campaign start must cross an AdaIvy model or
embedding gateway and use an explicitly selected AdaIvy credential profile.
This includes planning, query generation, extraction, source comparison,
ideation, criticism, proof drafting, and embedding generation.

The runtime must not silently inherit a host Codex/Claude credential or fall
back to another provider. A campaign records, without recording secret values:

- credential-profile identifier and source;
- provider, endpoint/deployment identity, and resolved model identifier;
- purpose of every call;
- attempted, completed, failed, and incomplete request counts;
- provider-reported token usage where available;
- embedding input tokens and document counts;
- pinned price snapshot and estimated cost; and
- remaining campaign and per-capability budgets.

The default live profile is `adaivy`. Ambient process credentials must not take
precedence over that profile on a campaign path. A deliberately selected
alternate profile is allowed but is recorded as such. Provider failure is
terminal for that route unless the initial campaign policy explicitly
authorizes a named fallback with its own budget; no implicit fallback to the
host agent is allowed.

### 2.2 One initial authorization, not recurring research approval

The operator's start action freezes the problem, provider routes, source
policy, tool permissions, and budgets. Routine search, retrieval, embedding,
experimentation, and branch selection then proceed inside those bounds.

The new activation ADR should supersede ADR-0055's mandatory human
`before_research` novelty-search gate. AdaIvy should perform and record its own
non-authoritative literature/novelty search during the campaign. That search
still creates no novelty warrant. Human review remains required before a public
novelty claim or publication approval.

Human interruption during research is reserved for target ambiguity, requested
budget expansion, exceptional rights decisions, or an explicit operator pause.
`ask_user` must not be the ordinary way to advance a campaign.

Finishing a campaign automatically produces a draft report from the recorded
campaign state. This is generation, not publication: it does not require human
approval, create a novelty or significance assessment, or announce or
distribute the result.

### 2.3 Lean is available throughout and normally decisive at the end

The campaign can request Lean checking when a definition, lemma, or candidate
has matured enough to benefit from it, but unstable ideation is not forced
through Lean on every iteration.

The default policy is:

- investigate freely within the campaign budget;
- use exact/domain verifiers whenever they cheaply test a candidate;
- allow a campaign action to request Lean at any point;
- require final Lean checking when the claimed result has an approved Lean
  representation and the result class calls for formal proof; and
- otherwise report the strongest honestly verified status and remaining
  formalization obligation.

Lean failure rejects that candidate, not the entire campaign. Safe elaboration
feedback may return to the lead. Policy-rejection details and diagnostics that
would teach sandbox or validator evasion remain isolated. Lean proves the exact
encoded statement; target correspondence remains a separate recorded property.

## 3. Runtime architecture

### 3.1 Extend the campaign action vocabulary

Add first-class campaign actions for:

- `search_literature`;
- `follow_discovery_results`;
- `acquire_source`;
- `parse_source`;
- `embed_sources`;
- `refresh_retrieval_index`;
- `retrieve_evidence`; and
- `formal_check`.

Each action must have immutable inputs, a causal parent, a finite budget, a
terminal record, and replay behavior. Network actions run through dedicated
acquisition gateways, never through the generated-code sandbox. Retrieved text
is untrusted data and cannot alter policy or acquire tool authority.

### 3.2 Run literature ingestion alongside research

Use two coordinated lanes under one campaign control plane:

1. The research lane plans, retrieves, derives, experiments, and verifies.
2. The literature lane discovers, acquires, parses, embeds, and publishes new
   immutable corpus/index generations.

The lanes may progress concurrently, but campaign reproducibility is preserved
at action boundaries. Every retrieval action binds the exact corpus generation,
embedding partition manifest, lexical index generation, query, ranking policy,
and returned evidence-card hashes. A newly completed ingestion generation can
affect only later actions after an explicit `refresh_retrieval_index` event.

Large means operator-configurable and budget bounded, not unlimited. Separate
limits cover queries, result fan-out, acquired bytes, documents, embedding
tokens/cost, storage growth, and wall time. Exhausting the literature allocation
does not discard the research already completed.

### 3.3 Activate a useful literature path

The first production path should combine:

- campaign-generated terminology and equivalent-formulation queries;
- Crossref and the already selected open-access snapshot source;
- ADR-0068 depth-one result following through a pinned scholarly-origin
  allowlist;
- open-access full text where the source policy permits it;
- strict parsing and immutable source spans; and
- quarantine for unsupported formats, ambiguous licences, redirects,
  injection-like content, and parse failures.

This requires a new ADR to supersede ADR-0051's operator-supplied-query-only
rule, ADR-0068's ban on generated queries, and ADR-0067's metadata-only first
slice. Query generation grants discovery authority only; discovered material
remains an untrusted candidate.

To avoid a human decision for every document, the initial authorization may
select a content-hashed source-and-rights policy for a licensed open-access
collection. Per-document decisions are then deterministically derived from the
archive manifest and document licence metadata. Ambiguous or incompatible
records are quarantined rather than prompting during the campaign. This must be
recorded as a replacement for the current human-authored per-document rights
requirement, not implemented as a bypass.

### 3.4 Make the corpus and embeddings durable across campaigns

Create one operator-selected AdaIvy data root outside the Git working tree. It
contains:

- immutable acquired source bytes and parsed spans;
- append-only acquisition, rights, and lineage records;
- immutable content-hashed embedding artifacts;
- partition manifests keyed by `(provider, model_identifier, dimension,
  normalization)`;
- rebuildable lexical, semantic, formula, citation, and claim indexes; and
- campaign-to-corpus usage records.

The default lifecycle is grow-only across runs. A second campaign reuses valid
source and vector artifacts and embeds only new or changed content. Provider or
model changes create a new partition rather than mixing or overwriting vectors.

“Persistent” does not override a legal deletion, takedown, or revoked-rights
requirement. Such an event removes bytes from active use as policy requires,
leaves a non-reconstructive tombstone and dependency record, and invalidates
affected projections. Ordinary campaign cleanup must never delete corpus or
embedding artifacts.

The live corpus database and indexes are local operational state and must not be
committed to Git. Portable, content-addressed manifests and deliberately
promoted evidence bundles remain exportable for replay and publication.

### 3.5 Feed retrieval directly into ideation

Before each substantive planning step, the context builder may execute bounded
hybrid retrieval over the latest admitted corpus generation. Retrieval should
combine, in delivery order:

1. existing lexical/BM25, aliases, disclaimer exclusion, and semantic vectors;
2. metadata/domain filters and exact symbol/formula search;
3. citation-neighborhood traversal; and
4. claim/dependency and contradiction-oriented retrieval.

The lead receives evidence cards containing exact spans, source identity,
retrieval reasons, and explicit untrusted/applicability status—not raw documents
mixed into system instructions. Retrieved material may inspire hypotheses and
queries immediately. It becomes a load-bearing premise only after its
applicability obligation is checked.

### 3.6 Wire the existing execution and verification ports

Replace the campaign CLI's `PendingSandboxExperimentRunner` with the activated
OCI runner when its recorded runtime and lock match. Replace `AbsentVerifier`
with a verifier router:

- exact graph verifier for its admitted target;
- existing exact Phase 5 verifiers for their admitted domains;
- Phase 3B Lean service for formal-check requests; and
- an explicit unsupported outcome when no verifier applies.

The router reconstructs verifier context independently. No verifier receives
the campaign's persuasive narrative, provider credentials, or unrestricted
source corpus.

### 3.7 Generate the report automatically at campaign completion

Every terminal campaign outcome—verified result, counterexample, partial
result, unresolved obligations, budget exhaustion, or blocker—must invoke the
record-driven publication projection automatically.

The completion step must:

- construct the manuscript record from the verified campaign export rather
  than require a separately authored summary;
- generate `paper.tex`, its provenance ledger, linked verification artifacts,
  and `MANIFEST.json` in the campaign output directory;
- compile `paper.pdf` automatically when the pinned typesetting toolchain is
  available;
- otherwise retain a complete LaTeX draft with
  `typeset_status: not_typeset` and a machine-readable missing-tool reason;
- derive titles, claim environments, caveats, attribution, model usage, cost,
  source citations, failed attempts, and unresolved obligations from records;
  and
- make report-generation failure visible without changing the mathematical
  outcome of the campaign.

The generated bundle is always an **unapproved draft**. Human publication
approval, the `before_announcement` novelty re-check, and any external release
remain separate explicit actions. A successful PDF build must never be treated
as approval or endorsement.

## 4. Delivery sequence

### Slice 1 — Activation ADR and truthful documentation baseline

- Write the superseding ADR defining the end-to-end campaign authority,
  credential profile, human-interruption policy, persistent data root, and
  literature budgets.
- Record exactly which clauses of ADR-0047, ADR-0051, ADR-0055, ADR-0067,
  ADR-0068, and ADR-0070 are superseded.
- Create one authoritative capability matrix with separate states for
  `designed`, `accepted`, `implemented`, `activated`, `wired`, and
  `end-to-end runnable`.

Exit: the desired runtime is unambiguous and no existing narrow ADR can be read
as silently still blocking it.

### Slice 2 — AdaIvy credential and unified budget boundary

- Add explicit project credential profiles and prohibit ambient-host fallback.
- Route campaign LLM and embedding calls through those profiles.
- Unify model, embedding, network, tool, storage, and wall-time accounting.
- Preserve request failures and rate-limit observations; apply bounded backoff
  rather than rapid reconnect loops.

Exit: a test campaign proves every internal AI call used the selected AdaIvy
profile and all costs close under one campaign budget.

### Slice 3 — Persistent corpus service

- Turn the corpus replay slice into a durable multi-run store.
- Activate the selected open-access snapshot with a bounded first tranche.
- Add policy-derived per-document rights and quarantine exceptions.
- Store full text and exact parsed spans where licensed.

Exit: two separate campaigns see the same corpus generation, and the second
does not reacquire unchanged documents.

### Slice 4 — Persistent embeddings and live-corpus retrieval

- Embed admitted documents through the AdaIvy embedding profile.
- Persist and reuse vector artifacts across runs.
- Generalize Phase 4C from its 19-document fixture to arbitrary immutable corpus
  generations without weakening the fixture benchmark.
- Add query embedding and retrieval manifests for campaign-generated queries.

Exit: a second run reuses existing vectors, embeds only deltas, and retrieves
from the real corpus with zero provider calls on the retrieval path.

### Slice 5 — Campaign-native literature loop

- Add the literature action types and isolated network workers.
- Allow bounded campaign-generated queries and depth-one result following.
- Run ingestion asynchronously and expose new generations at explicit refresh
  points.
- Place retrieved evidence cards into the next planning context.

Exit: one campaign visibly changes a later research action because of a cited,
content-hashed passage acquired and embedded during that same campaign.

### Slice 6 — Experiment and verifier integration

- Wire the activated OCI experiment runner into the actual campaign entrypoint.
- Add the verifier router and Phase 3B Lean adapter.
- Permit nonterminal candidate failures so the lead can continue while budget
  remains.

Exit: a campaign writes and runs a bounded experiment, inspects the result,
retrieves supporting literature, and submits a selected candidate to an
applicable exact or Lean verifier without leaving AdaIvy.

### Slice 7 — One resumable operator command

ADR-0071 delivers the first bounded part of this slice: terminal campaigns now
produce a claim-free, unapproved LaTeX status bundle automatically, and
`campaign resume ROOT` idempotently completes or verifies that finalization
without paid calls. It intentionally does not claim mid-campaign continuation.
The remaining work below requires action-level checkpoints, request-intent
records, and optional automatic invocation of the pinned PDF typesetter.

- Provide one command that initializes or resumes the data root, validates
  provider profiles and budgets, freezes the target, and starts the campaign.
- Resume from the durable ledger after interruption without repeating paid
  model, acquisition, or embedding work.
- Produce a reusable campaign export and automatically generate the
  record-driven LaTeX draft for every terminal outcome. Compile the PDF when the
  pinned toolchain is present; otherwise preserve the complete `.tex` bundle and
  record the missing typesetter.

Exit: a fresh operator can hand AdaIvy a problem and let it run to a genuine
terminal condition, receiving a traceable report draft without driving
individual phase or publication CLIs.

### Slice 8 — Documentation cleanup

- Update `README.md`, `TECHNICAL_BLUEPRINT.md`, `docs/TECHNICAL_DETAILS.md`, and
  `AGENTS.md` from the authoritative capability matrix.
- Consolidate the common mathematical run procedure from `CODEX.md` and
  `CLAUDE.md` into one runbook; retain thin harness-specific wrappers.
- The obsolete, unreferenced
  `docs/ARCHITECTURE_IMPROVEMENT_SUGGESTIONS_2026-08.md` has been removed; its
  still-relevant integration objective is represented by this roadmap.
- Remove only unreferenced completed `BOUNDED_IMPLEMENTATION_PROMPT*.md` files.
  Preserve prompts cited by ADRs or gate evidence at their existing paths and
  classify them as archived/non-normative through the documentation index;
  changing content-addressed historical evidence is not cleanup.
- Preserve accepted, rejected, and superseded ADRs as historical records. Add
  explicit `superseded_by` metadata rather than deleting decision history.
- Reconcile ADR-0064, ADR-0069, and ADR-0070 status with their implementation;
  update ADR-0057's obsolete OCI-pending status; and resolve the duplicate
  ADR-0038 identifier through an ADR index and stable aliases.
- Mark historical phase reports and plans `ARCHIVED / NON-NORMATIVE` where they
  remain useful evidence but are not current instructions.

Exit: current documentation contains no contradictory capability claims, and a
reader can distinguish implemented components from an activated, wired runtime.

## 5. End-to-end acceptance gate

The work is complete only when a clean, live test demonstrates all of the
following in one campaign:

1. The operator supplies a problem, one AdaIvy credential profile, and budgets.
2. Every internal LLM and embedding request uses that profile and appears in
   the campaign accounting; host-agent work is absent or explicitly imported.
3. AdaIvy generates literature queries, discovers and acquires multiple allowed
   sources, parses them, embeds new documents, and publishes a new corpus/index
   generation while research continues.
4. A later planning action retrieves exact passages from that generation and
   cites their record hashes as inspiration or proposed premises.
5. The campaign runs at least one bounded experiment or falsification action.
6. An applicable exact verifier or Lean checks the selected final candidate.
7. Failure of one candidate does not stop the campaign while budget and a valid
   next action remain.
8. Restart resumes without repeating completed paid calls or deleting corpus
   and vector artifacts.
9. A second campaign reuses the first campaign's corpus and embeddings and only
   pays for deltas.
10. Budget exhaustion produces a complete unresolved report rather than lost
    state or a demand for routine human review.
11. Every terminal outcome automatically produces a provenance-closed
    `paper.tex` bundle, and produces `paper.pdf` when the pinned toolchain is
    available. The bundle remains visibly unapproved until a separate human
    publication action.
12. Offline `make check` remains network- and provider-free, with live campaign,
    acquisition, embedding, OCI, and Lean checks remaining explicit named
    gates.

Passing component tests separately is not sufficient. This gate must exercise
the actual operator entrypoint and prove the complete causal path.

## 6. Explicit non-goals

- Retrieval rank, model agreement, or experimental success does not become
  proof.
- The campaign does not silently publish, assert novelty, or increase its own
  budget.
- Generated programs do not receive network credentials.
- Embedding partitions from different provider/model identities are never
  mixed.
- Persistence does not mean retaining content after a binding deletion or
  takedown requirement.
- The first integration does not require parallel specialists or evolutionary
  search; the central lead can perform the complete workflow.
