# Exploratory Multi-Result Research Synthesis v1

Status: **proposed normative architecture contract; inactive pending an
independent re-audit and dedicated owner-approved entry gate**

This contract proposes the earliest safe architecture for exploratory,
multi-result mathematical research synthesis. It creates no operational
discovery, acquisition, parsing, retrieval, extraction, graph, exploration,
synthesis, verification, event, or steering path.

The integrated repository contains approved, effective versions of ADR-0019
through ADR-0024, Material Partial Result Surfacing v1, and the applicable
stable protected-evidence manifest. Their presence does not activate this
contract. ADR-0025 cannot become effective until the combined architecture is
independently re-audited and a dedicated owner-approved entry gate passes.

Within the integrated architecture, Phase 1 trust semantics, Phase 2 append-only semantic events
and run timeline, Phase 3 provenance, Phase 4A rights/applicability and content
lifecycle, and ADR-0019 material-result semantics remain authoritative. This
contract must reuse them rather than create parallel provenance, content,
rights, event, notification, steering, or verification systems.

## 1. Authority and stage boundaries

The future workflow keeps these stages distinct. Output from one stage never
silently receives the authority of a later stage.

1. **Literature discovery** records candidate identities, citations,
   terminology, and possible locations. Discovery metadata is neither source
   content nor authority to acquire or use content.
2. **Authorized source acquisition** acts only after the effective Phase 4A
   rights decision permits acquisition. Retention, parsing, excerpting,
   embedding, model context, redistribution, and publication each require their
   own allowed rights decision.
3. **Representation selection** chooses retained source forms under the same
   rights and lifecycle boundary.
4. **Structured result extraction** creates source-anchored extraction
   proposals without replacing the source statement.
5. **Claim/dependency graph construction** creates attributed relation
   proposals and policy-scoped derived views.
6. **Exploratory branch management** maintains a finite portfolio with explicit
   budgets, parentage, failures, and stop reasons.
7. **Multi-result synthesis** proposes compositions only after explicit
   assumption, quantifier, domain/type, regularity, scope, and conclusion
   comparison.
8. **Bridge-lemma generation** proposes locally minimal missing claims under a
   finite declared comparison rule.
9. **Verification and falsification** records separate fidelity,
   compatibility, test, counterexample, proof, formal, and review outcomes.
10. **Material-partial-result surfacing** uses ADR-0019's immutable event and
    steering lifecycle only after that production path is separately activated.
11. **Human steering** appends authorized decisions; it never overwrites prior
    graph, branch, event, or steering history.

## 2. Four independent state axes

Every structured result and relation exposes four independent axes. No value on
one axis implies a value on another.

### 2.1 Source applicability

Source applicability is imported from the effective Phase 4A human
`ApplicabilityReview` and preserves its exact states:

- `proposed`;
- `checked`;
- `rejected`; and
- `unresolved`.

Only Phase 4A's named-human authority may produce the effective
`checked/applicable` outcome. Applicability answers only whether the exact
identified use of the imported statement is permitted under the reviewed
hypotheses, definitions, scope, exceptions, and implication. It does
not grant content rights, establish extraction fidelity, prove mathematical
truth, establish novelty, or admit anything to a graph view. Content-use
permission remains a separate Phase 4A rights decision.

### 2.2 Extraction fidelity

Extraction fidelity uses only:

- `proposed_extraction` — an attributed extraction proposal exists, but no
  source-faithfulness decision has been recorded;
- `source_checked` — an authorized fidelity record confirms that the exact
  extracted statement, assumptions, notation, and scope match identified source
  anchors and representation versions; and
- `extraction_rejected` — a fidelity record identifies a mismatch,
  unsupported normalization, source disagreement, or insufficient anchor.

`source_checked` means source-faithful extraction only. It does not mean
mathematically proved, rights-allowed, source-applicable, novel, significant,
or admitted to a graph view. A representation disagreement prevents
`source_checked` for the disputed content until the warning is resolved or the
fidelity record explicitly narrows itself to one identified representation.

### 2.3 Mathematical warrant

Mathematical warrant uses these scoped states:

- `unassessed` — no applicable mathematical verification has run;
- `empirically_tested` — bounded numerical, symbolic, or finite testing has
  produced recorded observations; this does not prove an unrestricted claim;
- `counterexample_found` — one recorded witness has independently verified
  assumption satisfaction and conclusion failure for the exact refuted claim;
  it warrants that scoped refutation only;
- `proof_reviewed` — an identified independent or authorized human review has
  recorded a passing complete-derivation verdict for the exact statement and declared
  assumptions under a named policy, without claiming formal-kernel checking;
  and
- `formally_verified` — a named formal kernel or independently validated
  rigorous certificate has validated the exact formal statement under its
  declared definitions, assumptions, imports, runtime, and policy.

These values are not a universal confidence score. `counterexample_found` is a
refutation outcome, not a rung toward proof. `formally_verified` applies only to
the submitted formal statement and declared assumptions. No mathematical-
warrant state implies semantic alignment, source applicability, extraction
fidelity, graph admission, novelty, significance, contribution, or publication
readiness.

### 2.4 Graph admission

Graph admission uses only:

- `proposed` — the result or relation is recorded but absent from the admitted
  research view;
- `admitted_under_policy` — an admission record includes it in one named,
  versioned, deterministic research view;
- `excluded_under_policy` — a policy evaluation records why it is absent; and
- `invalidated_by_later_record` — a later append-only record makes the earlier
  admission ineligible for the current view.

Every admission record cites the admission policy and version, required
effective source-applicability state, required extraction-fidelity state,
minimum permitted mathematical-warrant state and explicit permitted state set,
exact input record identities, admitting record identity, admitting
actor/authority, and current influence-closure identity. Because warrant states
are not a total order, policy must evaluate the explicit set and cannot infer
that `counterexample_found` is above or below a proof state. Admission means
inclusion in that deterministic research view only. It never means universally
true, novel, significant, or permanently valid.

Results and relations have separate applicability, fidelity, warrant, and
admission records. A relation cannot inherit an endpoint's states. Normative
state transitions must use only the qualified terms in this section; no generic
approval label is valid.

## 3. Source-representation policy

### 3.1 Preferred reading order

When rights, identity, availability, and quality permit, prefer:

1. authoritative structured HTML;
2. TeX or LaTeX source;
3. born-digital PDF; and
4. scanned PDF with OCR.

The order grants no acquisition or use authority. For important sources,
multiple representations may be retained: HTML as the primary reading layer,
TeX as the mathematical-source layer, PDF as the rendered-evidence layer, and
OCR as a warning-bearing fallback. Version or representation disagreement
creates an append-only warning and blocks silent selection.

### 3.2 Identity and lineage

Every retained representation and derived artifact identifies exact paper and
version identity, discovery record separately from acquisition authority,
acquisition provenance and actor, source/representation hashes, media type and
role, parser/converter/normalizer/extractor identity and version, exact source
anchors, warnings, parent hashes, and deterministic transformation lineage.
Summaries aid navigation only; they never overwrite or replace exact source
statements.

### 3.3 Untrusted rich content

TeX, LaTeX, HTML, PDF, OCR, converter output, macros, includes, and embedded
instructions are untrusted data. A future processor must prohibit arbitrary
execution, generated-code execution, shell escape, network access, inherited
secrets, uncontrolled includes, writes outside an isolated disposable
workspace, and unbounded macro/include expansion. It requires explicit finite
CPU, memory, wall-time, input, output, recursion, and expansion limits.

This proposal activates no remote crawl, download, converter, or parser.

## 4. Structured result and relation model

A future `StructuredResearchResult` contains the exact statement; normalized
and original notation; assumptions; domains and types; quantifiers; conclusion;
scope; proof technique; dependencies; limitations; source anchors and version;
all four state axes; non-authoritative confidence proposal; extraction method;
known counterexamples; and orthogonal novelty status. Notation normalization has
an explicit transformation record and never establishes equivalence by itself.

Result relations are `depends_on`, `implies`, `equivalent_to`, `stronger_than`,
`weaker_than`, `specializes`, `generalizes`, `contradicts`,
`uses_same_technique`, and `requires_bridge`. Each relation identifies exact
endpoint versions, proposer/extractor, source/evidence anchors, comparison
rationale, open obligations, and its own four state-axis records. The graph is
derived research state, not primary evidence and not mathematical truth.

## 5. Mandatory finite run bounds

Before execution, every synthesis run has one validated, versioned budget
policy whose integer fields use explicit units.

These maxima must be positive integers:

- retrieval iterations;
- citation/dependency hops;
- query fan-out;
- results per query;
- unique discovered sources;
- graph nodes and graph edges;
- branch count;
- branch-generation attempts; and
- overall wall-clock seconds and each enabled resource-unit budget.

These maxima may be zero or a positive integer:

- acquired sources and total acquired bytes, where either is zero if and only
  if both are zero;
- branch depth, where zero permits root branches only; and
- model calls and tool calls, where zero disables that capability.

Missing, Boolean, negative, non-integer, non-finite, unitless, or internally
inconsistent bounds fail closed before a run begins. No component may increase
a bound. Every loop body and branch transition consumes a named budget counter
before execution, including every retrieval iteration, query expansion,
dependency traversal, source acquisition, graph insertion, branch creation or
transition, model call, and tool call. Each run emits exactly one deterministic
terminal reason: `completed`, `converged_under_rule`,
`budget_exhausted:<counter>`, `user_intervention`, or `blocked:<reason>`.

### 5.1 Enforceable exploration reserve

The budget policy stores an exploration-reserve numerator and denominator as
integers satisfying `denominator > 0` and
`0 < numerator < denominator`. For branch-generation budget `B`, the reserved
attempt count is `ceil(B * numerator / denominator)`.

When at least two strategy families are eligible at allocation time, at least
`reserved` attempts must be assigned to eligible non-incumbent families and no
more than `B - reserved` may be assigned to the current highest-ranked
incumbent family. No unavailability waiver applies while two families are
eligible. If fewer than two are eligible, each unfilled reserved slot requires
an append-only `reserve_unavailable` record naming every evaluated family and
its exclusion reason. Strategy-family identity is versioned policy data. The
allocation ledger and reserve equation are exported, so a zero reserve,
over-allocation, unsubstantiated waiver, or post-hoc family relabeling fails
verification.

## 6. Bounded multi-hop retrieval

Each iteration retrieves seed/result candidates, proposes terminology and
missing prerequisites, expands equivalent formulations and notation, follows
backward/forward dependencies within the hop budget, deliberately seeks a
contrasting approach, and appends attributed graph proposals. It stops only
with a Section 5 terminal reason.

The deterministic retrieval trace records iteration number, input graph
snapshot, queries/traversals and parents, adapter/version, filters, budgets
before/after, ordered results, exclusions, graph changes, contrasting-result
classification, and stop reason. Candidate generation may combine prose, exact
terms, citations, symbols/formulas, assumptions, conclusions, metadata, and
graph relations. Canonical source/result state remains independent of lexical,
embedding, formula, vector, reranking, or graph indexes. One top-k vector query
is insufficient and cannot satisfy the multi-hop acceptance scenario.

No remote search, embedding model, vector index, or graph service is selected
or authorized here.

## 7. Exploration and duplicate-attempt policy

Where applicable, the finite portfolio includes direct proof, counterexample
search, restricted cases, computational experimentation, alternative
formulation, cross-domain transfer, multi-paper composition, and formalization/
verification. Each branch records identity, parent, strategy family, exact
hypothesis/objective delta, required evidence, falsification conditions, all
budgets, current state, non-authoritative confidence, failure, discoveries, and
stop reason. Transitions are append-only.

An exact duplicate-attempt key is
`H(normalized_hypothesis_digest, parent_branch_identity,
strategy_family_identity, input_graph_snapshot_identity,
constraint_configuration_digest)` under the named canonicalization and hash
versions. Abandoned attempts remain addressable. The
same key cannot be enqueued again unless an authorized retry record identifies
changed inputs or policy and therefore a new key. Semantic equivalence beyond
exact identity remains a proposed relation and never silently deduplicates.

## 8. Composition and bridge candidates

Before composition, compare assumptions and implication direction; quantifier
kinds and bounds; domains, codomains, object types, and regularity; definition
and notation correspondence; scope and exceptions; source versions; conclusion
strength; and the exact term consumed by the next result. Every mismatch opens
or links an obligation.

A `BridgeLemmaCandidate` identifies a missing claim and records connected result
versions, named mismatch, composition value, preliminary evidence, attempted
falsifications, literature-search protocol/status, mathematical-warrant state,
and obligations. Minimality is local only: a finite mismatch set, finite
candidate set, and deterministic comparison rule must be recorded. A candidate
is locally minimal only if it resolves the named mismatch and no enumerated
proper-subset candidate permits the same valid composition. It makes no claim
of global mathematical minimality.

A bridge candidate is a proposal, not a proved lemma or discharged obligation.
Restating the target fails premise audit. “Not found in the search corpus” is
`search_incomplete` or `not_found_under_protocol`, never novel.

## 9. Verification funnel

Record `not_run`, `blocked`, `failed`, `inconclusive`, or `passed` separately
for source-faithful extraction, logical compatibility, numerical/symbolic
testing, counterexample search, proof review, formal verification, independent
review, and human acceptance. These are stage-execution records, not state-axis
values. Only the authority and policy defined for an axis may append its state
record while citing the relevant execution records. Passing a later stage does
not pass an earlier or orthogonal stage. Search, experiments, rank, graph
centrality, confidence, and model agreement never create proof status.

## 10. Existing event and material-result lifecycle

Exploration reuses the Phase 2 semantic event store and run timeline. Any future
branch, proposal, admission, invalidation, or steering event requires the same
event-store port, causal/idempotency rules, strict acceptance boundary, and
canonical replay. No parallel notification or status framework is permitted.

ADR-0019 surfaced events remain immutable. When source correction, invalidation,
supersession, or changed applicability affects a surfaced event, the future
Phase 5 extension appends a semantic record in the same event stream referencing
the original event, cause, actor/authority, affected influence closure, and
replacement when any. The current-validity view is derived from the immutable
original plus later records. ADR-0019 does not yet define this vocabulary, so
the extension is separately gated before production activation. It cannot use a
mutable event field, parallel status table, or alternate notification path.

Eligible material results still traverse ADR-0019's active-objective/run,
classification, independent-verification, materiality, creator-authority,
causality, idempotency, incomplete-parent, and append-only steering rules.

## 11. Rights, applicability, and lifecycle propagation

Every derived result, relation, graph admission, branch input, retrieval
decision, synthesis proposal, bridge candidate, verification input, and surfaced
partial-result view records its transitive source/result influence identities.

Influence closure is recomputed after source correction, revocation, takedown,
suppression, deletion request/completion, rights expiry/prohibition/change, or a
later human `ApplicabilityReview` that changes the effective decision from
applicable to unresolved or rejected, narrows applicable scope or permitted
use, changes governing conditions, or changes authority/policy version in a way
that changes the effective decision. Rejected or unresolved effective review
fails closed for the affected use.

Propagation appends the triggering record, stops prohibited use, appends
superseding/invalidation records for every affected extraction, relation, graph
view, branch, synthesis proposal, bridge candidate, verification input, and
surfaced partial-result view, then deterministically rebuilds the current view.
Original evidence, source records, graph proposals, events, and decisions remain
immutable and addressable. Prohibited content is removed only through the
existing Phase 4A deletable-content boundary; permitted non-content audit
identity remains.

## 12. Proposal capture, determinism, and replay

Nondeterministic generation creates an immutable captured-proposal record with
the exact raw payload or canonical captured representation, proposal digest,
generator/model identity and configuration, prompt/input identities, source
graph snapshot identity, supported seed, generation timestamp or ordered event
identity, parent branch identity, resource usage, and failure/refusal state.

Once captured, the proposal identity and digest are explicit inputs to
deterministic normalization, admission, export, and replay. Replay never calls
the generator. Regeneration creates a new proposal identity even if content is
equal.

Deterministic output equality requires the same policy-admitted input
identities, policy versions, captured-proposal digests, canonicalization version,
and qualified state-axis records. Canonical outputs include representation/
lineage manifests, fidelity and admission records, retrieval traces, branch and
budget ledgers, proposal envelopes, verification manifests/outcomes,
invalidation/current-view projections, semantic-event linkage, and the
policy-admitted result-graph export. Operational timestamps not selected as an
ordered event identity remain separately hashed metadata.

## 13. Explicit non-capabilities and future gate

This proposal adds no crawler, network access, remote-source adapter, HTML/TeX/
PDF/OCR/archive parser, embedding model, vector database, result extractor,
theorem prover, schema, migration, production event implementation, dependency,
model/API call, autonomous multi-agent/evolutionary runtime, or quantum
implementation.

No implementation begins until a separate owner-approved Phase 5 plan defines
trust paths, exact rights uses, concrete finite bounds, dependencies/licenses,
schemas, migrations, threat models, event vocabulary, acceptance fixtures,
protected evidence, and production-path tests. Phase 4A receives none of these
requirements or capabilities.

## 14. Normative future acceptance scenarios

This section is the single authoritative definition of scenarios `ERS-AC-01`
through `ERS-AC-12`. Every test uses bounded synthetic or rights-cleared
fixtures and records fixture inputs, trace/records, expected output, forbidden
output, and explicit failure conditions.

### ERS-AC-01: Genuine multi-hop three-source synthesis

- **Fixture inputs:** compatible source results A, B, and C plus contrasting
  result D, all with allowed rights and effective `checked/applicable` reviews.
  For every permitted result-count bound, the initial query can return A and B only and
  cannot return C or D. C is discoverable solely by traversing a citation or
  dependency found in iteration one; D is discoverable solely by the declared
  terminology/notation expansion and contrasting-approach query generated from
  iteration-one output.
- **Trace:** at least two retrieval iterations, one expansion, one traversal,
  a graph update after iteration one, one contrasting result, budget counters,
  and a declared convergence or budget stop.
- **Expected:** an `admitted_under_policy` composition referencing A, B, C, the complete
  retrieval trace, compatibility records, exact source/result versions, and D
  recorded as the contrasting result without being silently composed.
- **Forbidden:** manual injection of C or D, one-query/top-k completion, missing
  applicability/fidelity records, or composition before compatibility checks.
- **Fails if:** C or D is initially retrievable, any trace element is absent, any
  source/relation is ineligible, or the expected composition is absent.

### ERS-AC-02: Quantifier mismatch rejection

- **Fixture inputs:** individually eligible results whose composition confuses a
  universal premise with an existential or differently bounded conclusion.
- **Trace:** explicit quantifier comparison and resulting obligation.
- **Expected:** an `excluded_under_policy` composition with a named
  quantifier-mismatch reason.
- **Forbidden:** an `admitted_under_policy` composition or silent quantifier weakening.
- **Fails if:** the mismatch is not recorded or the composition enters the
  policy-admitted view.

### ERS-AC-03: Domain, type, or regularity mismatch rejection

- **Fixture inputs:** individually eligible results differing in domain, object
  type, or required regularity.
- **Trace:** domain/type/regularity comparison and exact failed condition.
- **Expected:** an `excluded_under_policy` composition plus an unresolved obligation.
- **Forbidden:** coercion, assumption insertion, or an `admitted_under_policy` composition without
  an explicit verified bridge.
- **Fails if:** any mismatch is omitted or the unbridged composition receives an
  `admitted_under_policy` record.

### ERS-AC-04: Notation equivalence with false-positive control

- **Fixture inputs:** a declared valid notation-equivalence pair and a control
  using the same symbol in a different domain/type.
- **Trace:** normalization transformations and definition/domain/type mappings
  for both pairs.
- **Expected:** a `proposed` then `admitted_under_policy` equivalence for the
  valid pair and an `excluded_under_policy` relation for the control.
- **Forbidden:** symbol-string equality as equivalence evidence or admission of
  the control.
- **Fails if:** the valid mapping is not recognized, the control receives an
  `admitted_under_policy` record, or either decision lacks its own state-axis records.

### ERS-AC-05: Version or representation disagreement

- **Fixture inputs:** two versions or HTML/TeX/PDF representations with a
  material statement difference.
- **Trace:** exact identities, hashes, anchors, comparison, and warning record.
- **Expected:** warning; disputed content remains `proposed_extraction` or becomes
  `extraction_rejected`, and graph admission remains `excluded_under_policy`
  until the disagreement is explicitly narrowed or resolved.
- **Forbidden:** silent representation selection or overwritten source text.
- **Fails if:** the warning is absent, disputed content receives an
  `admitted_under_policy` record silently, or provenance is incomplete.

### ERS-AC-06: Locally minimal bridge candidate

- **Fixture inputs:** finite named mismatch set, finite candidate set containing
  one candidate and at least one proper-subset candidate, deterministic
  comparison rule, connected result versions, and approved objective.
- **Trace:** evaluation of every enumerated candidate, composition attempt, and
  falsification result.
- **Expected:** the candidate resolving the named mismatch only when no proper-
  subset candidate enables the same valid composition; verification and novelty
  remain open unless separately established.
- **Forbidden:** global-minimality or novelty language, target restatement, or
  omission of a smaller successful candidate.
- **Fails if:** a proper-subset candidate succeeds, the named mismatch remains,
  or the finite comparison evidence is incomplete.

### ERS-AC-07: Counterexample as an ADR-0019 material result

- **Fixture inputs:** exact counterexample with independently verified
  assumption satisfaction and conclusion failure, active objective/run,
  source/result provenance, expected ADR-0019
  classification `refutes`, and authorized materiality/creator records.
- **Trace:** independent verification, materiality and authority decisions,
  event creation/retry, replay, and later steering.
- **Expected:** one immutable, idempotent surfaced event classified `refutes`
  with incomplete parent; deterministic replay; later steering appended
  separately.
- **Forbidden:** generic progress classification, duplicate retry event, mutable
  event/steering state, self-authorization, or completed parent objective.
- **Fails if:** any ADR-0019 identity/authority/materiality/provenance rule is
  absent, retry duplicates the event, replay differs, or steering overwrites.

### ERS-AC-08: Rights-inapplicable source has zero influence

- **Fixture inputs:** one relevant source whose effective rights decision blocks
  each tested use while eligible alternatives remain.
- **Trace:** rights evaluation, exclusions, and influence-closure rebuild.
- **Expected:** the source is absent from parsing/context/relation/synthesis/
  verification/partial-result inputs and the policy-admitted graph view.
- **Forbidden:** score-only suppression after prohibited content was used.
- **Fails if:** any prohibited-use artifact or transitive influence remains.

### ERS-AC-09: Lifecycle and applicability propagation

- **Fixture inputs:** `admitted_under_policy` source-derived state followed separately by source
  correction, revocation, takedown, deletion, a changed rights decision that
  narrows or prohibits the tested use, and superseding human
  `ApplicabilityReview` transitions from `checked/applicable` separately to
  `rejected/inapplicable` and `unresolved`.
- **Trace:** every trigger, full influence closure, append-only invalidations,
  current-view rebuild, and permitted content-removal evidence.
- **Expected:** affected results, relations, graph views, branches, synthesis,
  bridges, verification inputs, and partial-result views are invalidated in the
  current view while original records/events remain addressable.
- **Forbidden:** destructive history mutation, stale `admitted_under_policy` influence,
  deletion outside the Phase 4A boundary, or treating revocation as mathematical
  falsity.
- **Fails if:** any influenced artifact remains current, audit identity changes,
  or rejected/unresolved applicability does not fail closed.

### ERS-AC-10: Deterministic policy-admitted export/replay

- **Fixture inputs:** fixed input identities with effective
  `admitted_under_policy` records, policy versions,
  captured-proposal digests, canonicalization version, and qualified state-axis
  records, including one nondeterministically generated proposal already
  captured.
- **Trace:** normalization, admission, export, fresh-process replay, and proof
  that no generator is called during replay.
- **Expected:** byte-identical canonical policy-admitted graph export and hashes.
- **Forbidden:** proposal regeneration, operational timestamp in semantic
  identity, or unadmitted proposal content in the admitted graph projection.
- **Fails if:** bytes/hashes differ, a generator runs, or any explicit replay
  input differs without producing a new identity.

### ERS-AC-11: Abandoned branch and exact duplicate prevention

- **Fixture inputs:** abandoned attempt with declared normalized hypothesis,
  parent branch, strategy family, graph snapshot, and configuration digests.
- **Trace:** exact duplicate-key calculation, attempted re-enqueue, and optional
  authorized retry with a changed input/policy.
- **Expected:** abandoned attempt remains searchable; exact-key re-enqueue is
  rejected; changed authorized retry receives a new key and linkage.
- **Forbidden:** deletion of failure history, silent retry of the same key, or
  semantic-similarity deduplication without a separately recorded relation
  proposal and its qualified state-axis records.
- **Fails if:** the exact attempt duplicates, the old attempt is inaccessible,
  or changed inputs reuse the old key.

### ERS-AC-12: Append-only human steering

- **Fixture inputs:** active finite portfolio, prior steering history, authorized
  user, and bounded instruction to select/rebudget/redirect/stop.
- **Trace:** actor/authority, causal parent, previous-view identity, new bounded
  instruction, budget validation, and idempotency identity.
- **Expected:** a new steering record and deterministically changed current view
  with all prior branch/objective/steering records byte-identical.
- **Forbidden:** in-place edits, unauthorized budget increase, history deletion,
  or duplicate record on retry.
- **Fails if:** prior bytes change, authority/bounds fail, retry duplicates, or
  the current view does not reflect the appended instruction.

All scenarios also fail if search noncoverage becomes novelty, retrieval or
experimentation creates proof status, stopped/failed/missing-tool outcomes are
not machine-readable, or protected evidence changes during a future quiescent
production-path verification.
