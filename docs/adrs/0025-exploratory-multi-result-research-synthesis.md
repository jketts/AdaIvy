# ADR-0025: Define exploratory multi-result research synthesis as a future gated capability

- **Status:** proposed (architecture only; inactive pending independent
  re-audit and a dedicated owner-approved entry gate)
- **Date:** 2026-08-20
- **Blueprint requirement:** C1-C17 (C17 proposed), research lifecycle,
  retrieval, verification, and Phase 5
- **Decision owners:** repository owner and researcher

## Context

AdaIvy has architectural primitives for claims, source provenance, explicit
assumptions, representation bridges, proof obligations, competing branches,
verification, and append-only events. Phase 4A separately establishes a
fail-closed local rights and human applicability lifecycle. ADR-0019 defines
how verified material partial results will eventually be surfaced without
completing an objective or creating a parallel notification system.

Those primitives do not yet define how a future research workflow may discover
literature, compare multiple structured mathematical results, explore competing
routes, identify a locally minimal bridge proposal under a declared finite
comparison, and synthesize results without
laundering retrieval or model output into mathematical authority. A vague
"research agent" or one top-k vector query would obscure source authority,
assumption mismatches, failed branches, and the distinction between a proposed
composition and a verified result.

This proposal was drafted in parallel under the provisional number ADR-0023.
Integration assigns ADR-0023 to the accepted bounded Phase 5 quantum slice and
ADR-0024 to the accepted bounded Phase 6 confirmatory slice, so this inactive
proposal is canonically renumbered ADR-0025.

Approved versions of ADR-0019 through ADR-0022, the Material Partial Result
Surfacing v1 contract, and the stable protected-evidence manifest are now in the
integrated ancestry. Their presence does not activate this proposal. ADR-0025
still requires an independent architecture audit and a dedicated owner-approved
entry gate before any implementation work begins.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Treat retrieval plus a long model context as synthesis | Common RAG pattern | Small apparent workflow | Hides assumptions, dependencies, source versions, and failed routes | Rejected |
| Add an autonomous multi-agent research subsystem | Blueprint search tiers | Broad exploration | Duplicates orchestration and expands authority before measurement | Rejected |
| Define a bounded result graph and branch portfolio over existing trust boundaries | Existing claim/evidence, branch, event, rights, and verification architecture | Attributable, replayable, falsifiable, and human-steerable | More explicit records and future gates | Selected |
| Defer even the architecture | Current production boundary is sufficient for Phase 4A | No present scope change | Leaves future synthesis semantics ambiguous | Rejected by this architecture request |

## Decision

Propose the normative future contract in
`docs/phase-4/EXPLORATORY_RESEARCH_SYNTHESIS_V1.md`. The capability is a bounded
pipeline with distinct stages for literature discovery, authorized acquisition,
representation selection, structured result extraction, claim/dependency graph
construction, branch management, multi-result synthesis, bridge-lemma
generation, verification/falsification, material-partial-result surfacing, and
human steering.

Discovery metadata grants no authority to acquire or use source content.
Acquisition, retention, parsing, excerpting, model context, redistribution, and
publication remain independently governed by the Phase 4A rights lifecycle.
Every load-bearing source use requires the existing human-only final
applicability decision. Revocation, correction, takedown, deletion, or changed
rights applicability invalidates affected active derived projections without
rewriting their append-only history.

Structured source statements and inferred result relations remain proposals
until separate source-applicability, extraction-fidelity, mathematical-warrant,
and policy-admission records establish their exact scopes. No one axis implies
another. Extracted summaries never replace exact source statements. The derived
result/claim graph is research state, not primary evidence and not mathematical
truth. Synthesis must compare assumptions, quantifiers, domains, types, scope,
and conclusions before proposing composition. A bridge-lemma candidate records
a locally minimal missing claim under a finite declared comparison rule; it is
not a theorem, proof-obligation discharge, global minimum, or novelty claim.

Exploration uses a bounded portfolio of identifiable branches, preserves
negative findings and abandoned branches, reserves a configurable budget for
diverse or lower-ranked routes, and remains replayable and steerable. A single
top-k vector search is explicitly insufficient. Future retrieval must combine
appropriate lexical, citation, symbol/formula, assumption/conclusion, semantic,
and graph signals behind replaceable projections.

Verification follows a funnel from source-faithful extraction through logical
compatibility, testing and counterexample search, proof checking, formal
verification, independent review, and human acceptance. Later stages do not
silently imply earlier or orthogonal trust dimensions. Verified material
counterexamples, equivalences, restricted theorems, contradictions, bridge
lemmas, and reusable intermediate results may use ADR-0019's existing semantic
event and steering path when its production gate is activated. No parallel
event, notification, provenance, rights, content, or verification subsystem is
authorized.

## Consequences

- Future research synthesis has an explicit trust-preserving lifecycle rather
  than an autonomous-agent label.
- Multiple source representations may be retained and compared, but every form
  remains untrusted, versioned, content-addressed input. TeX is never executed.
- Deterministic policy-admitted artifacts and projections can be replayed from
  explicit admitted-input identities and immutable captured-proposal digests;
  inherently nondeterministic exploratory outputs remain attributed proposals.
- Human steering can redirect or stop exploration without erasing prior branch
  history.
- The explicit result model and relation vocabulary will require separately
  reviewed schemas, migrations, ports, resource bounds, and acceptance fixtures
  before any implementation.
- Phase 4A receives no scope, authority, or production capability from this
  proposal, which makes no claim that exploration or synthesis works.

## Explicit deferrals

This proposal does not authorize a crawler, network access, arXiv adapter,
HTML/TeX/PDF/OCR parser, embedding model, vector database, claim extractor,
theorem prover, schema, persistence migration, production event implementation,
dependency, model/API call, multi-agent runtime, or quantum implementation.
Each trust path requires a separate bounded gate and owner approval.

## Blueprint deviation

None. This proposes a refinement of the deferred Phase 5 branch-search and
research-automation architecture while preserving Phase 4A and the measured
search-complexity ladder. It does not advance implementation phase scope.

## Validation and revisit trigger

Make this proposal effective only after the integrated architecture is
independently re-audited, a dedicated owner-approved entry gate passes, and the
future implementation plan satisfies all twelve
acceptance scenarios in the normative contract, preserves the Phase 4A
fail-closed rights model and human-only applicability authority, reuses the
existing append-only event/run timeline, and reproduces policy-admitted
result-graph exports deterministically. Revisit before introducing any concrete
record schema, database migration, parser, acquisition adapter, retrieval index,
model/tool dependency, production event path, or authority change.
