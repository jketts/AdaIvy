# AdaIvy Capability Status

**As of:** 2026-08-22  
**Authority:** current implementation status  
**Next integration roadmap:**
[`END_TO_END_RESEARCH_RUNTIME_PLAN.md`](END_TO_END_RESEARCH_RUNTIME_PLAN.md)

This is the canonical human-readable status summary. It distinguishes a design
or accepted decision from code that is implemented, activated, wired into the
operator path, and usable end to end.

| Capability | Implemented | Activated | Campaign-wired | Current scope |
|---|---:|---:|---:|---|
| Provider-neutral model gateway | Yes | Yes, explicit live opt-in | Yes | OpenAI, Azure OpenAI, Anthropic, Bedrock, DeepSeek, MiniMax, and Qwen/DashScope adapters under bounded configurations |
| Central campaign loop | Yes | Yes | Yes | One sequential lead with a durable causal ledger and budget limits |
| Generated-program OCI sandbox | Yes | Yes for one Linux/arm64 exact-graph target | Yes, behind activation matching (ADR-0073) | `campaign run --experiment-activation` wires the activated runner only when the record re-verifies against the current locks; otherwise the pending runner remains with the reason recorded |
| Campaign verifier | Yes: verifier router | Yes | Yes (ADR-0073) | Routes exact-graph, Phase 5 diagonal, and Phase 5 noncommuting candidates plus formal-check envelopes; anything else is an explicit `unsupported` failure |
| Lean checking | Yes | Separate sealed runtime | Port wired; sealed adapter is an explicit opt-in | The router's formal-check route defaults to a recorded missing-tool result; `--formal-check-adapter sealed` uses the Phase 3B Docker Lean service |
| Crossref discovery | Yes | Explicit one-request live opt-in | Offline fixture action wired | Operator-supplied grounded terms, at most ten metadata candidates; live search retains its explicit permit |
| Discovery-result following | Yes | Offline fixture | Yes, depth one | The end-to-end runtime enforces `max_depth: 1` and an allowlisted origin |
| Bulk corpus ingestion | Yes, bounded replay slice | Production activation pending | No | arXiv descriptive metadata and abstracts; no full text |
| Persistent corpus store (ADR-0072 Slice 3) | Yes | Local ingest from an already-acquired archive; live snapshot acquisition pending | Yes in offline end-to-end path | Operator-selected grow-only data root, exact spans, policy-derived rights, immutable generations, idempotent run records, and takedown tombstones; corpus manifests remain `retrieval_indexed: false` because retrieval is a separate projection |
| Embedding ingestion | Yes | Explicit live opt-in | Yes in offline end-to-end path | Exact processor/provider/model rights checks precede reads; profile-bound live gateway remains explicit |
| Persistent vector artifacts | Yes | Yes | Yes in offline end-to-end path | Immutable artifacts stored in the persistent data root and reused across generations |
| Semantic retrieval | Yes | Offline fixture only | No | Fourth Phase 4C signal over 19 project-authored documents and 17 queries |
| Retrieval over acquired corpus | Yes (ADR-0074) | Offline fixture | Yes | Immutable projection binds active corpus generation/hash and exact vector partition; query artifacts and exact-span evidence cards are replayable with zero provider calls |
| Campaign literature/embedding actions | Yes | Offline fixture | Yes | Action schema v2 names search, depth-one follow, acquire, parse, embed, refresh, retrieve, and formal check |
| Named credential profiles and unified budget | Yes | Offline fixture | Yes in `campaign start` | Selection and charge records are durable and secret-free; live resolution refuses ambient credentials and has no implicit fallback |
| Action-level campaign resume | Yes (ADR-0075) | Yes | Yes in `campaign start` | Intent precedes every effect; completed actions replay; ambiguous effects stop unresolved without repetition |
| Automatic campaign LaTeX draft | Yes | Yes | Yes | Every terminal run attempts a claim-free, unapproved `paper.tex` bundle; PDF typesetting remains an explicit gate |
| End-to-end research run | Yes, offline fixture | Offline only | Yes through `campaign start` | One command executes 13 checkpointed actions from literature through report; live effects remain separately gated |

## What works today

- `make check` exercises the complete offline acceptance suite without network,
  provider credentials, a container runtime, or third-party packages.
- Live provider, acquisition, embedding, OCI, Lean, and typesetting paths are
  separate named gates with explicit prerequisites.
- Campaign model calls, actions, artifacts, usage, and costs can be recorded and
  replayed.
- A terminal campaign automatically emits an unapproved LaTeX status bundle,
  and `campaign resume ROOT` idempotently completes or verifies that projection
  without paid calls.
- Exact verifiers, the sealed Lean checker, corpus replay, embedding artifacts,
  and semantic retrieval each work inside their bounded scopes.

## What does not work today

AdaIvy now executes this complete path in the deterministic offline fixture:

```text
literature search -> acquisition -> persistent embedding/indexing -> retrieval
-> iterative investigation and experiments -> exact or Lean verification
```

`campaign start` records every stage and enforces search before research. Live
provider/search/snapshot/container/Lean execution is not implied by this
offline result and still requires each named gate. The legacy `campaign run`
path remains available with its former novelty-check contract. Human
`before_announcement` approval remains required unconditionally.

## Status vocabulary

- **Designed:** described in the blueprint or a proposal.
- **Accepted:** authorized by an accepted ADR.
- **Implemented:** code and acceptance tests exist.
- **Activated:** production prerequisites or an activation record permit use.
- **Campaign-wired:** the real `campaign run` path constructs and calls it.
- **End-to-end runnable:** the operator entrypoint exercises the complete causal
  path, not merely separate component gates.

Only the last state establishes the product behavior described in the runtime
plan.
