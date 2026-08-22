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
| Generated-program OCI sandbox | Yes | Yes for one Linux/arm64 exact-graph target | **No** | The standalone gate passes, but `campaign run` still injects the pending runner |
| Campaign verifier | Exact-graph adapter exists | Yes for its frozen target | **No** | `campaign run` still injects `AbsentVerifier` |
| Lean checking | Yes | Separate sealed runtime | **No** | Single-shot checking and bounded proof-fragment repair; the campaign cannot call it |
| Crossref discovery | Yes | Explicit one-request live opt-in | **No** | Operator-supplied grounded terms, at most ten metadata candidates |
| Discovery-result following | Decision accepted | No | No | ADR-0068 is not implemented |
| Bulk corpus ingestion | Yes, bounded replay slice | Production activation pending | No | arXiv descriptive metadata and abstracts; no full text |
| Embedding ingestion | Yes | Explicit live opt-in | No | Operator-supplied local documents with processor-bound rights |
| Persistent vector artifacts | Yes | Yes | No | Immutable exact vector artifacts; caller supplies the storage root |
| Semantic retrieval | Yes | Offline fixture only | No | Fourth Phase 4C signal over 19 project-authored documents and 17 queries |
| Retrieval over acquired corpus | **No** | No | No | Corpus records are deliberately marked `retrieval_indexed: false` |
| Campaign literature/embedding actions | **No** | No | No | The campaign action schema has no search, acquire, embed, index, or retrieve action |
| Named credential profiles and unified budget | Yes | No | **No** | Slice 2 boundary: profile selection/resolution refuses ambient credentials, profile-bound model/embedding gateway wrappers, one append-only multi-capability budget ledger, and deterministic bounded backoff; `campaign run` does not construct them yet and the Slice 1 activation ADR has not landed |
| Terminal campaign resume | Yes | Yes | Yes | Idempotently verifies a complete terminal ledger and finishes its draft; it does not yet resume a partial paid run |
| Automatic campaign LaTeX draft | Yes | Yes | Yes | Every terminal run attempts a claim-free, unapproved `paper.tex` bundle; PDF typesetting remains an explicit gate |
| End-to-end autonomous research run | **No** | No | No | Components remain separate; no single command performs the complete loop |

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

AdaIvy cannot yet take a problem and autonomously execute this complete path:

```text
literature search -> acquisition -> persistent embedding/indexing -> retrieval
-> iterative investigation and experiments -> exact or Lean verification
```

The campaign entrypoint does not expose literature actions, does not read the
acquired corpus, does not use the persistent vector artifacts, and does not wire
the implemented sandbox or a verifier. A fresh human novelty re-check is still
required before every campaign under ADR-0055.

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
