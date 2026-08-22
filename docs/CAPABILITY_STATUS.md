# AdaIvy Capability Status

**As of:** 2026-08-22  
**Authority:** current implementation status  
**Current depth/breadth roadmap:**
[`CAMPAIGN_DEPTH_AND_BREADTH_PLAN.md`](CAMPAIGN_DEPTH_AND_BREADTH_PLAN.md)

This is the canonical human-readable status summary. It distinguishes a design
or accepted decision from code that is implemented, activated, wired into the
operator path, and usable end to end.

| Capability | Implemented | Activated | Campaign-wired | Current scope |
|---|---:|---:|---:|---|
| Provider-neutral model gateway | Yes | Yes, explicit live opt-in | Yes | OpenAI, Azure OpenAI, Anthropic, Bedrock, DeepSeek, MiniMax, and Qwen/DashScope adapters under bounded configurations |
| Central campaign loop | Yes | Offline fixture; live provider separately gated | Yes | v1 compatibility plus a model-driven v2 loop with separate paid-planner/effect checkpoints, repeatable literature cycles, and bounded context memory |
| Generated-program OCI sandbox | Yes | Yes for one Linux/arm64 exact-graph target | Yes, behind activation matching (ADR-0073) | `campaign run --experiment-activation` wires the activated runner only when the record re-verifies against the current locks; otherwise the pending runner remains with the reason recorded |
| Campaign verifier | Yes: verifier router | Yes | Yes (ADR-0073) | Routes exact-graph, Phase 5 diagonal, and Phase 5 noncommuting candidates plus formal-check envelopes; anything else is an explicit `unsupported` failure |
| Lean checking | Yes | Separate sealed runtime | Port wired; sealed adapter is an explicit opt-in | The router's formal-check route defaults to a recorded missing-tool result; `--formal-check-adapter sealed` uses the Phase 3B Docker Lean service |
| Scholarly discovery | Yes | Authorized live v2 run pending | Model-driven v2 registry | Paginated Crossref/arXiv/OpenAlex adapters, exact source-grounded campaign queries, bounded bytes/requests, and strict transport verification |
| Discovery-result following | Yes | Offline fixture | Yes, depth one | Requires a verified acquisition record, `max_depth: 1`, and an allowlisted origin |
| Bulk corpus ingestion | Yes | Production acquisition activation pending | Available to the v2 effect registry | Resumable allowlisted snapshot fetch, PDF/LaTeX extraction ports, bulk rights quarantine, arXiv metadata bridge, and delta-only ingest |
| Persistent corpus store (ADR-0072 Slice 3) | Yes | Local ingest from an already-acquired archive; live snapshot acquisition pending | Yes in offline end-to-end path | Operator-selected grow-only data root, exact spans, policy-derived rights, immutable generations, idempotent run records, and takedown tombstones; corpus manifests remain `retrieval_indexed: false` because retrieval is a separate projection |
| Embedding ingestion | Yes | Explicit live opt-in | Yes in offline end-to-end path | Exact processor/provider/model rights checks precede reads; profile-bound live gateway remains explicit |
| Persistent vector artifacts | Yes | Yes | Yes in offline end-to-end path | Immutable artifacts stored in the persistent data root and reused across generations |
| Semantic retrieval | Yes | Offline fixture only | Available to the v2 effect registry | Existing Phase 4C benchmark plus chunked corpus projections and exact-span evidence cards |
| Retrieval over acquired corpus | Yes (ADR-0074) | Offline fixture | Yes | Immutable projection binds active corpus generation/hash and exact vector partition; query artifacts and exact-span evidence cards are replayable with zero provider calls |
| Campaign literature/embedding actions | Yes | Offline fixture | Yes | A model can choose v2 search/follow/acquire/parse/embed/refresh/retrieve actions through a closed effect registry; fixture closures remain the deterministic `campaign start` adapter |
| Named credential profiles and unified budget | Yes | Offline fixture | Yes in `campaign start` | Selection and charge records are durable and secret-free; live resolution refuses ambient credentials and has no implicit fallback |
| Action-level campaign resume | Yes (ADR-0075/0076/0079) | Yes | Yes | Intent precedes planner and operation effects; completed actions replay; ambiguous paid effects stop; a bounded human answer continues the same v2 campaign |
| Scientific workspace sandbox v2 | Yes | Pending pinned-image build and 16-probe activation | Registry boundary implemented | Persistent campaign workspace, exact manifest/hash checks, atomic promotion rollback, configurable bounds and explicit `determinism_unverified` propagation |
| Automatic campaign LaTeX draft | Yes | Yes | Yes | Every terminal end-to-end run writes a provenance-closed, claim-free, unapproved bundle and automatically invokes the pinned typesetter only when its exact toolchain is present |
| End-to-end research run | Yes, offline fixture and model-driven v2 engine | Offline only | Fixture CLI plus v2 runtime API | Model-chosen actions can traverse literature, published-generation retrieval, experiment, verification, interruption/resume, and report; live effects remain separately gated |
| Live end-to-end acceptance | Gate definition implemented | Pending operator activation | Preflight command only | `campaign live-acceptance` validates the sealed gate and all named evidence with zero effects; no real end-to-end acceptance run is claimed |

## What works today

- `make check` exercises the complete offline acceptance suite without network,
  provider credentials, a container runtime, or third-party packages.
- Live provider, acquisition, embedding, OCI, and Lean paths are separate named
  gates with explicit prerequisites. The end-to-end report checks the pinned
  typesetter and compiles only when the exact declared toolchain is present.
- Campaign model calls, actions, artifacts, usage, and costs can be recorded and
  replayed.
- A terminal campaign automatically emits an unapproved LaTeX status bundle,
  and `campaign resume ROOT` idempotently completes or verifies that projection
  without paid calls.
- Exact verifiers, the sealed Lean checker, corpus replay, embedding artifacts,
  and semantic retrieval each work inside their bounded scopes.

## Remaining live boundary

AdaIvy now executes this complete path in the deterministic offline fixture:

```text
profile-bound query planning -> literature search -> acquisition
-> persistent embedding/indexing -> rights-checked retrieval
-> evidence-guided experiment -> exact refutation -> repair -> exact verification
```

`campaign start` remains the deterministic fixture adapter. The model-driven
v2 engine is implemented and tested with an injected gateway/effect registry,
but no checked-in command silently composes pending live authorities. Live
provider/search/snapshot/embedding/container/Lean execution is not implied by
the offline result and still requires each named gate. The Slice 16 readiness
command reports zero calls and remains pending. The legacy `campaign run` path
remains available with its former novelty-check contract. Human
`before_announcement` approval remains required unconditionally.

## Status vocabulary

- **Designed:** described in the blueprint or a proposal.
- **Accepted:** authorized by an accepted ADR.
- **Implemented:** code and acceptance tests exist.
- **Activated:** production prerequisites or an activation record permit use.
- **Campaign-wired:** an operator campaign entrypoint constructs and calls it;
  the matrix names `campaign start` or legacy `campaign run` where they differ.
- **End-to-end runnable:** the operator entrypoint exercises the complete causal
  path, not merely separate component gates.

Only the last state establishes the product behavior described in the runtime
plan.
