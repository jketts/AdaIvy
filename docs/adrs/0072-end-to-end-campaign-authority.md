# ADR-0072: End-to-end campaign authority under one initial authorization

- **Status:** accepted as a decision record only. This ADR authorizes Slices
  2–6 of the end-to-end runtime plan; it activates no code, wires no component,
  and every capability it names remains exactly as capable as it was the day
  before this ADR was written. Each slice still ships under its own acceptance
  gate before its capability may be claimed.
- **Date:** 2026-08-22
- **Blueprint requirement:** Sections 6–8 (research loop), 7.1/7.3 (candidates
  and retrieval), 12.2 (rebuildable projections and immutable artifacts), 15
  (untrusted retrieved content), 17 (budgets and stop rules); C10 (no repeated
  paid work), C12 (recorded applicability), C15 (novelty orthogonal to
  warrant); `docs/END_TO_END_RESEARCH_RUNTIME_PLAN.md` §§1–3
- **Decision owners:** repository owner

## Context

AdaIvy's components each work inside a deliberately narrow ADR: one Crossref
request per human acknowledgement (ADR-0051), one human-planned URL per
acquisition, a human `before_research` novelty re-check before every campaign
(ADR-0055), an individually human-authored rights decision for every document
(ADR-0064), a metadata/abstract-only ingestion slice (ADR-0067), a ban on
machine-generated queries (ADR-0068), and a 19-document retrieval fixture
(ADR-0070). Those bounds were correct for their slices, and each recorded a
revisit trigger requiring a new ADR before widening.

The owner now wants the behavior described in
`docs/END_TO_END_RESEARCH_RUNTIME_PLAN.md`: supply a problem, an AdaIvy
credential profile, and budgets; authorize once; and receive either a verified
result or an honest unresolved report without routine approval pauses. Read
together, the ADRs above silently block that runtime even after every
component is implemented. This ADR is the explicit decision the revisit
triggers demanded. It supersedes the exact clauses named below, keeps
everything else in force, and states plainly that a decision is not a
capability: after this ADR, the runtime is *authorized*, not *runnable*.

## Options considered

| Option | Evidence | Benefit | Cost/risk | Decision |
|---|---|---|---|---|
| Widen each old ADR in place | fewest files | small diffs | rewrites decision history; the reasons for the old bounds disappear with the bounds | Rejected — ADRs are append-only history |
| One activation ADR per slice (six new ADRs) | matches slice delivery | fine-grained revisit | the interlocking clauses (queries feed following feeds rights feeds embedding) would be re-litigated six times and could drift apart | Rejected |
| One superseding ADR naming exact clauses, slices gated separately | ADR-0068 precedent for clause-level supersession | one coherent authority; old records stand with a pointer; implementation still earns each capability through its own gate | risk of being read as an activation record — mitigated by the Status line and the non-license section | **Selected** |
| Skip the ADR and let implementation reinterpret the old bounds | none | none | the exact failure the ADR process exists to prevent | Rejected |

## Decision

### 1. AdaIvy credentials and budget own the research workload (plan §2.1)

Every model or embedding call made after campaign start must cross an AdaIvy
model or embedding gateway using an explicitly selected AdaIvy credential
profile — planning, query generation, extraction, source comparison, ideation,
criticism, proof drafting, and embedding generation included. The default live
profile is `adaivy`. Ambient host-process credentials (a host Codex or Claude
session's own keys) must never take precedence over the selected profile on a
campaign path, and the runtime must not silently fall back to another provider.
A deliberately selected alternate profile is allowed and recorded as such.
Provider failure is terminal for that route unless the initial campaign policy
explicitly authorized a named fallback with its own budget.

A campaign records, without recording secret values: credential-profile
identifier and source; provider, endpoint/deployment identity, and resolved
model identifier; the purpose of every call; attempted, completed, failed, and
incomplete request counts; provider-reported token usage where available;
embedding input tokens and document counts; the pinned price snapshot and
estimated cost; and remaining campaign and per-capability budgets.

### 2. One initial authorization, restricted human interruption (plan §2.2)

The operator's start action freezes the problem, provider routes, source
policy, tool permissions, and budgets. Routine search, retrieval, embedding,
experimentation, and branch selection then proceed inside those bounds without
per-step approval. `ask_user` is reserved for genuine target ambiguity,
requested budget expansion, exceptional rights decisions, or an explicit
operator pause; it must not be the ordinary way to advance a campaign.

The mandatory human `before_research` novelty re-check of ADR-0055 is
superseded for campaign runs (exact clause below). In its place the campaign
performs and records its own non-authoritative literature/novelty search as
part of research. That search creates no novelty warrant and no `novel`
outcome exists for it, exactly as ADR-0055 already provided for human
searches. **Human review remains required before any public novelty claim or
publication approval.** The `before_announcement` re-check, the human
performer requirement on it, and the ADR-0036 publication-approval boundary
are untouched.

Finishing a campaign automatically produces a draft report from recorded
campaign state under ADR-0071. That is generation, not publication: it needs
no human approval and creates no novelty or significance assessment.

### 3. Lean available throughout, normally decisive at the end (plan §2.3)

A campaign action may request Lean checking whenever a definition, lemma, or
candidate has matured enough to benefit, but unstable ideation is not forced
through Lean every iteration. The default policy: investigate freely within
budget; use exact/domain verifiers whenever they cheaply test a candidate;
allow a `formal_check` request at any point; require final Lean checking when
the claimed result has an approved Lean representation and its result class
calls for formal proof; otherwise report the strongest honestly verified
status and the remaining formalization obligation.

Lean failure rejects that candidate, not the campaign. Safe elaboration
feedback may return to the lead; policy-rejection details and diagnostics that
would teach sandbox or validator evasion remain isolated. Lean proves the
exact encoded statement; target correspondence remains a separately recorded
property, unchanged from the Phase 3B posture.

### 4. Persistent operator-selected data root outside the Git tree (plan §3.4)

One operator-selected AdaIvy data root, outside the Git working tree, holds:
immutable acquired source bytes and parsed spans; append-only acquisition,
rights, and lineage records; immutable content-hashed embedding artifacts;
partition manifests keyed by `(provider, model_identifier, dimension,
normalization)`; rebuildable lexical, semantic, formula, citation, and claim
indexes; and campaign-to-corpus usage records.

The lifecycle is grow-only across runs. A later campaign reuses valid source
and vector artifacts and embeds only new or changed content. A provider or
model change creates a new partition; partitions are never mixed or
overwritten, preserving ADR-0069. Ordinary campaign cleanup must never delete
corpus or embedding artifacts. "Persistent" does not override a legal
deletion, takedown, or revoked-rights requirement: such an event removes bytes
from active use, leaves a non-reconstructive tombstone and dependency record,
and invalidates affected projections, consistent with ADR-0021. The live
database and indexes are local operational state and are not committed to Git;
portable content-addressed manifests and deliberately promoted evidence
bundles remain exportable.

### 5. Literature budgets and the two-lane architecture (plan §3.2)

Literature work runs as a second lane under the same campaign control plane:
the research lane plans, retrieves, derives, experiments, and verifies; the
literature lane discovers, acquires, parses, embeds, and publishes new
immutable corpus/index generations. The lanes may progress concurrently, but
reproducibility is preserved at action boundaries: every retrieval action
binds the exact corpus generation, embedding partition manifest, lexical index
generation, query, ranking policy, and returned evidence-card hashes, and a
newly completed ingestion generation affects only actions after an explicit
`refresh_retrieval_index` event.

"Large" means operator-configured and budget-bounded, never unlimited.
Separate pinned limits cover queries, result fan-out, acquired bytes,
documents, embedding tokens and cost, storage growth, and wall time.
Exhausting the literature allocation does not discard completed research.
Network actions run through dedicated acquisition gateways, never through the
generated-code sandbox, and retrieved text is untrusted data that cannot alter
policy or acquire tool authority.

### 6. Campaign-generated queries with depth-one following (plan §3.3)

The campaign may generate terminology and equivalent-formulation queries
against Crossref and the ADR-0067 open-access snapshot source, and may follow
results depth-one under all six ADR-0068 controls (pinned scholarly-origin
allowlist, absolute depth one, no credentials, no redirects or query strings,
pinned fan-out, machine selection recorded as such). Querying the snapshot
source is local search over already-acquired, content-hashed snapshot bytes,
not a second network discovery origin: Crossref remains the only pinned
network discovery origin, exactly as ADR-0051 provides. Query generation
grants discovery authority only: a discovered document remains an
`untrusted_inspiration_candidate`, and no search rank, retrieval hit, or model
preference becomes relevance, applicability, novelty, significance, or
warrant. Every generated query is recorded with its generating action, budget
consumption, and content hash, replacing ADR-0051's per-request human
acknowledgement with per-campaign authorization plus a complete query ledger.

### 7. Content-hashed source-and-rights policy (plan §3.3)

The initial authorization may select a content-hashed source-and-rights policy
for a licensed open-access collection. Per-document acquisition, retention,
parsing, and embedding-processor decisions are then **deterministically
derived** from the archive manifest and per-document licence metadata under
that policy, rather than authored individually by a human during the campaign.
Ambiguous licences, incompatible records, unsupported formats, redirects,
injection-like content, and parse failures are quarantined — recorded,
retained, and excluded — rather than prompting mid-campaign or being silently
admitted. This is recorded as a **replacement** for the human-authored
per-document rights requirement, not a bypass: every document still carries a
per-document rights record; what changes is that a human authored the policy
once instead of each record. ADR-0064's requirement that an embedded document
carry a processor-bound rights decision naming the processor stands; its
human-authorship mechanism for per-document decisions is explicitly superseded
below so that decision may be policy-derived. Licence diligence still precedes
acquisition, archive and tranche selection remain human acts, and the bounded
first tranche of ADR-0067 remains mandatory.

## Superseded clauses, exactly

Only the clauses listed here are superseded. Every other clause of every named
ADR remains in force, and each named ADR receives a status-line pointer to
this record rather than any edit to its substance.

### ADR-0047 (bounded central research lead runtime)

- The **"Explicit deferrals"** clause — "No Phase 3B proof-repair
  orchestration, retrieval scheduling, experiment scheduling, branch-selection
  policy, specialist worker, parallel execution, evolutionary selection,
  retention-gain measurement, automatic review, or trust promotion is added.
  Each requires its own later decision and acceptance gate." — is superseded
  **only** for retrieval scheduling, experiment scheduling, branch-selection
  policy within budget, and Phase 3B proof-repair/formal-check orchestration
  inside a campaign. This ADR is the required later decision for those four;
  their acceptance gates are Slices 4–6.
- **Not superseded:** specialist workers, parallel execution, evolutionary
  selection, automatic review, and trust promotion remain deferred and
  unauthorized (plan §6 non-goals). Verifier context isolation, the
  one-Phase-2-round-per-iteration rule, `awaiting_human_review` as the
  strongest runtime outcome, the frozen target identity, the bounded
  proposer-only ledger, and zero-model-call replay all stand.

### ADR-0051 (bounded public scholarly web discovery)

- Decision bullet: "one operator-initiated request per invocation, at most ten
  returned candidates" — superseded in its *one operator-initiated request*
  part. Campaign literature actions may issue multiple requests under pinned
  per-campaign query and fan-out budgets. The at-most-ten-candidates cap
  remains in force **per request**; total fan-out across requests is governed
  by the campaign literature budget. Per-request byte, term-count, and
  deadline bounds remain, now pinned in the campaign policy.
- Decision bullet: "every query term must be an NFKC-normalized, case-folded
  exact substring of a supplied local problem or research-context file" —
  superseded. Campaign-generated terminology and equivalent-formulation query
  terms are permitted, each recorded with its generating action and hash.
- Decision bullet: "execution requires a human actor identifier, the exact
  acknowledgement `I_ACKNOWLEDGE_PUBLIC_WEB_DISCOVERY`, and confirmation of
  the exact grounded query hash displayed by the dry run" — superseded for
  campaign-contained discovery; the one initial campaign authorization
  replaces the per-request acknowledgement.
- Decision sentence: "This slice performs no result-link fetch, citation
  traversal, page parsing, recursive query, query generation, scheduling,
  personalization, model call, or credential access." — superseded only in
  the words *result-link fetch* (already narrowed by ADR-0068), *query
  generation*, *scheduling*, and *model call* (a model may compose queries
  through the AdaIvy gateway). The bans on citation traversal beyond depth
  one, recursive querying of followed content, personalization, and credential
  access on discovery/acquisition fetches all stand.
- **Not superseded:** the pinned Crossref origin (any additional provider
  still needs its own ADR and provider-policy review); the
  `untrusted_inspiration_candidate` output status with relevance,
  applicability, novelty, and significance `not_assessed`; the terms-review
  freshness requirement; the DNS global-routability and TLS peer-binding
  controls; the prohibition on inferring relevance, applicability, novelty,
  significance, or warrant from search rank.

### ADR-0055 (two fresh novelty re-checks)

- Decision clause 1 — "A `before_research` re-check is the final recorded
  event before the first research action." — and the freshness sub-clause
  "the pre-research record is persisted immediately before run creation or the
  first runtime action" are superseded **for campaign runs**. The campaign
  performs and records its own non-authoritative literature/novelty search
  during research; that search creates no warrant and has no `novel` outcome.
  ADR-0065's Decision §5 and its probe 8, and ADR-0057's "After the mandatory
  `before_research` novelty checkpoint" sentence, restate this clause and are
  read through this supersession; removing the enforcing code is Slice 2+
  work with its own gate, and until that lands the implemented check still
  fires.
- **Not superseded — stated emphatically:** the `before_announcement` human
  re-check, its human-performer requirement, its 24-hour freshness and
  subject-hash binding, the derived prior-art classification (including the
  Graffiti 197 `independent_verification` / `already_refuted` regression), the
  absence of a `novel` outcome, and the rule that no automated search is a
  novelty authority. Human review before a public novelty claim or
  publication approval is a hard boundary this ADR does not touch.

### ADR-0064 (Phase 4A embedding rights bind a named processor)

- The named boundary "**Human authority is unchanged and unweakened.** Rights
  decisions stay pinned to `(ActorKind.HUMAN, Authority.HUMAN_FINAL)` ... No
  model, automation, or campaign may author one." and the validity condition
  "rights decisions stay human-authored" are superseded **only in the
  authorship mechanism for per-document decisions**: under Decision §7, a
  per-document `embedding` or `model_context` rights decision may be
  deterministically derived from the operator-approved, content-hashed
  source-and-rights policy, with quarantine for any record the policy cannot
  classify. Human authority moves to the policy; it does not disappear. A
  human authors and approves the policy once, the derivation is a
  deterministic function of the archive manifest and per-document licence
  metadata, and no model output ever becomes a rights decision.
- The falsifiability probe `pr.nonhuman-embedding-decision-refused` ("a
  decision authored with `ActorKind.MODEL` or `Authority.PROPOSAL` must
  refuse") is retired and replaced by a recording obligation, mirroring the
  ADR-0068 probe replacement below: a policy-derived decision that does not
  record the policy content hash, the deriving rule identifier, and the exact
  per-document licence inputs must refuse — and a decision authored by a
  model, or carrying `Authority.PROPOSAL`, still refuses.
- The revisit-trigger item "letting a non-human author a rights decision" is
  discharged by this ADR for deterministic policy derivation only.
- **Not superseded:** the required named `processor` for the two disclosing
  uses and its prohibition for every other use; one decision authorizes one
  processor, with no wildcard, no `any`, and no cross-provider inheritance; a
  second provider is a second decision; recorded `disclosure_kind`; unchanged
  expiry, revocation, and takedown semantics; the closed `processor` field
  set; and every other falsifiability probe of ADR-0064.

### ADR-0067 (corpus ingestion at volume)

- The implemented scope ceiling — "a bounded metadata/abstract replay slice"
  (Status) — is superseded as a ceiling: open-access **full text and exact
  parsed spans** may be acquired, retained, and parsed where the approved
  source-and-rights policy permits it.
- The named boundary "Per-document rights do not become per-archive rights.
  ... each document still needs its Phase 4A decisions and, to be embedded,
  its ADR-0064 processor decision" — superseded only in the *authorship
  mechanism*: the per-document decisions still exist per document but are
  deterministically derived from the content-hashed policy (Decision §7)
  instead of individually human-authored. A document the policy cannot
  classify is quarantined, not admitted.
- **Not superseded:** option C itself (one authorized bulk open-access
  snapshot; a snapshot is an acquisition, not a crawl); the mandatory bounded
  first tranche reviewed before the remainder; licence diligence preceding
  acquisition; human archive/version/tranche selection; and — most
  importantly — "Applicability stays manual and stays the ceiling." Corpus
  size must never be reported as knowledge; the count of documents carrying
  an applicability record remains a separate figure.

### ADR-0068 (following discovery results)

- The named boundary "**This does not license query generation.** The machine
  may follow a result; it may not invent the query that produced it.
  ADR-0051's operator-supplied, locally-substring-checked query terms are
  unchanged." — superseded. Campaign-generated queries are licensed under
  Decision §6 with a complete recorded query ledger.
- The falsifiability probe `pr.follow-query-not-generated` ("a
  machine-composed query term must refuse") is retired and replaced by a
  recording obligation: a machine-composed query that is *unrecorded*,
  *unbudgeted*, or *not bound to its generating action* must refuse.
- The revisit-trigger item "permitting machine-generated queries" is
  discharged by this ADR.
- **Not superseded:** all six controls (pinned origin allowlist, absolute
  depth one, no credentials, no redirects or query strings, pinned fan-out,
  machine selection recorded as automation), the untrusted class of followed
  documents, the delimited untrusted rendering region, the non-inheritance of
  rights from discovery, the retained recommendation-against and residual-risk
  record, and the immediate-revisit rule on the first unintended influence of
  a followed document on model output.

### ADR-0070 (Phase 4C semantic signal and corpus scope)

- The corpus-path clause — "The path to a real corpus runs through ADR-0050
  acquisition, one human-planned exact URL at a time, plus a Phase 4A rights
  decision per document and now an ADR-0064 processor decision per document
  before any of it may be embedded." — is superseded as a description of the
  only path: the path now also runs through ADR-0067 option C plus this ADR's
  policy-derived per-document rights.
- The revisit-trigger item "widening the corpus beyond the frozen fixture
  set" and the explicit deferral "Query-side embedding of anything other than
  the frozen gold queries" are discharged: Slice 4 may generalize retrieval to
  arbitrary immutable corpus generations and embed campaign-generated queries
  through the AdaIvy embedding profile.
- **Not superseded:** the 19-document fixture benchmark itself, which remains
  frozen and unweakened as the regression benchmark; the frozen tier
  constants and the ban on retuning them against fixtures; the no-float,
  no-network structure of the retrieval path; the partition binding into
  report identity; and the revisit item "letting a query vector be computed
  live inside the retrieval path" — query embedding is a separate budgeted
  campaign action whose output artifact the retrieval path replays.

## What this decision does not license

It activates nothing. No credential profile, data root, literature action,
policy-derived rights record, corpus generation, query generator, verifier
router, or Lean adapter exists or is wired by virtue of this ADR; each arrives
only through its slice's acceptance gate, and `docs/CAPABILITY_STATUS.md`
remains the authoritative statement of what is implemented, activated, and
wired. It creates no `EpistemicWarrant`, applicability decision, graph
admission, novelty or significance assessment, or publication approval. It
does not let the campaign publish, announce, assert novelty, or increase its
own budget. It grants no network credential to generated programs and no
provider credential to any verifier. It does not authorize specialist workers,
parallel search, evolutionary selection, or automated applicability recording.
Retrieval rank, model agreement, and experimental success remain non-proof.

## Consequences

- Slices 2–6 of the plan are decision-authorized and no narrower ADR can be
  read as silently still blocking them; each still needs its own
  implementation, falsifiability probes, and gate.
- Seven ADRs gain a status-line supersession pointer; their substance is
  unedited, per the append-only history rule.
- The recorded prompt-injection exposure accepted in ADR-0068 grows: machine
  queries choose what discovery returns, and discovery chooses (within the
  allowlist) what is fetched. The allowlist remains the decisive control and
  its membership remains a human judgement.
- Removing the routine `before_research` human gate removes a human
  stale-problem check at campaign start. The mitigation is the recorded
  in-campaign search plus the untouched human `before_announcement` re-check;
  a campaign spent on an already-solved problem is now a budget cost the owner
  has accepted, not a silent claim risk, because no claim leaves without the
  human re-check.
- Policy-derived rights concentrate risk in the policy: a wrong policy is
  wrong for every document it classifies. The mitigations are the content
  hash, the quarantine default for anything ambiguous, and the bounded first
  tranche review.
- `make check` remains network- and provider-free; live campaign,
  acquisition, embedding, OCI, and Lean checks remain explicit named gates.

## Blueprint deviation

None beyond those already recorded. ADR-0068 recorded the deviation from the
no-result-following posture; this ADR extends machine authority to query
composition, which the blueprint's Section 7.1 permits provided crawler output
stays candidate-only and outside the trusted core — both preserved here. The
blueprint's untrusted-content rules (`:1801`, `:1817-1818`) continue to bind
every retrieved byte.

## Validation and revisit trigger

This ADR is validated by the slice gates it authorizes, not by tests of its
own: Slice 2's proof that every internal call used the selected AdaIvy
profile; Slice 3's two-campaign shared corpus generation; Slice 4's
delta-only re-embedding with a zero-provider-call retrieval path; Slice 5's
cited content-hashed passage changing a later action; Slice 6's in-campaign
exact/Lean verification; and ultimately the plan §5 end-to-end acceptance
gate. Until a slice's gate passes, its capability must continue to be reported
as absent.

Revisit with a new ADR before: allowing any campaign path to use an ambient
host credential; adding a discovery provider beyond Crossref and the selected
snapshot source; raising following depth above one; automating the
`before_announcement` re-check or any publication approval; automating
applicability recording; letting the campaign expand its own budget; or
treating any retrieval, search, or model output as a warrant.

Revisit immediately if a campaign-generated query is found to have been
steered by retrieved content into targeting an origin or document the operator
would not have approved — that is the specific new exposure this ADR accepts,
and its first occurrence reopens the decision rather than being handled as a
bug.
