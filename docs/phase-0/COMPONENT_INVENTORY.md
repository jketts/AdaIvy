# Candidate Component Inventory

**Observed:** 2026-08-19  
**Method:** primary repositories, official documentation, and papers linked by
the architecture documents. “Open source” is used only when a reusable code
artifact and license were observable. Website claims are inventory evidence,
not fitness evidence.

## Required Phase 0 categories

| Candidate | Category/artifact | License evidence | Maintenance/availability evidence | Local prerequisites and export surface | Phase 0 disposition |
|---|---|---|---|---|---|
| [Albilich](https://github.com/uw-math-ai/albilich) | Proof-state workflow; Python/SQLite repository | Apache-2.0 in repository | Public repository, active 2026 history, standard-library core, documented test suite | Python 3.10+, agent CLI only for live attempts; SQLite, JSON/Markdown/artifact exports | Capability probe; clone/test if permitted, otherwise explicit blocker. Strong wrap/interoperate candidate. |
| [MathGraph](https://github.com/metalogiclabs/mathgraph) | Verification memory and finite-countermodel kernel | **No repository license was visible** at review; website says “open-core” | Public repository with substantial 2026 history and deterministic fallback demos | Python repository; evidence manifests and replay scripts; scope currently finite-equational FALSE-side | License hard-gate blocker. Do not copy or adopt; inventory public interfaces only. |
| [OMDoc 1.2](https://www.omdoc.org/format/) | Semantic mathematical-document format/standard | Format materials have mixed/unclear repository licensing; verify per artifact | Stable format is 1.2; official site says later versions are developmental | XML tooling; statements/theories/proofs; cannot carry the complete dossier without extensions | Test a minimal XML projection as a design reference, not claim conformance. |
| [MMT](https://github.com/UniFormal/MMT) | Foundation-independent theory graphs and morphisms | Custom BSD-like terms permit redistribution **without modification**; not an SPDX-equivalent permissive modification grant | Long-lived public Scala repository with active history | JVM/Scala build and archives; XML fragment of OMDoc plus MMT APIs | Interoperate/defer. Test concepts locally via projection; legal review before dependency/modification. |
| [Why3](https://why3.org/) | Verification-condition language and prover dispatch | LGPL-2.1 for core (official source distribution) | Current official release 1.8.2; mature Inria project | `why3` plus a configured prover; sessions/output files | Wrap CLI if locally installed. Missing executable/prover is a recorded blocker. |
| [Lean 4](https://github.com/leanprover/lean4) / mathlib | Proof assistant and kernel | Apache-2.0 | Mature active project with pinned toolchains | `elan`, `lake`, Lean project/cache; proof source and compiler output | Wrap the smallest theorem check when present; missing toolchain is a blocker, not an auto-install. |
| [LeanDojo](https://github.com/lean-dojo/LeanDojo) | Programmatic Lean interaction and extraction | MIT | Original library is explicitly deprecated in favor of v2; public releases exist | Requires Python `<3.13`, Git, `wget`, `elan`, and GitHub token; current host is Python 3.14 | Rule out this host integration: interpreter/token/toolchain mismatch. Revisit v2 in Phase 3. |
| [LeanSearch v2](https://github.com/frenzymath/LeanSearch-v2) | Global Lean premise retrieval and proof loop | Apache-2.0; bundled FATE-H data CC-BY-4.0 | Public 2026 code/data release | Lean, Mathlib cache, model endpoints; standard server needs two GPUs; proof mode can download on first run | Defer: disproportionate to elementary dossier and unavailable local prerequisites. Retain API as future interoperability target. |
| [PaperQA2](https://github.com/Future-House/paper-qa) | Scientific literature retrieval/synthesis | Apache-2.0 | Active public repository and calendar-versioned releases | Python 3.11+, sizable dependency set; default model/embedding APIs and metadata network; local models possible | Package/import/export capability probe only. No crawler or paid/model run in Phase 0. |
| [Eigenius](https://github.com/eigenius/eigenius) | Typed scientific provenance and cross-system institutions | Apache-2.0 | Very early public 2026 monorepo; repository labels itself early-stage | Rust 1.97+, Deno, native libraries or Docker; Eigon-JSON/CBOR, gRPC/MCP | Interoperate/defer; compare warrant/translation concepts, not a Phase 1 dependency. |

## Research/search systems named by the blueprint or novelty review

| Candidate | Reusable public artifact and license | Phase 0 relevance and blocker |
|---|---|---|
| [ASTRA](https://github.com/AstrumDrive/ASTRA) | Public code, but **no license file/statement visible** at review | Multi-model production roles, API/CLI credentials, Python 3.10–3.12, and remote tool environments exceed the spike. License and host-Python hard blockers. |
| [RMA](https://arxiv.org/abs/2605.22875) | Paper; implementation promised upon acceptance, not public at review | Cannot test. Record as unavailable, not open source. |
| [Aletheia](https://arxiv.org/abs/2602.10177) | Paper/system report; no reusable implementation identified by the blueprint | Cannot test locally; use only reported failure modes as design evidence. |
| [AlphaProof Nexus](https://arxiv.org/abs/2605.22763) | Paper; no reusable implementation identified | Cannot test locally; formal-target-first approach remains comparison context. |
| [ProofAtlas](https://www.proofatlas.ai/) | Public read-only product/site; no reusable licensed repository identified | Cannot test as a backend or dependency. |
| [FunSearch](https://github.com/google-deepmind/funsearch) | Apache-2.0 software; non-code materials CC-BY-4.0 | Repository explicitly omits model, sandbox, and distributed infrastructure. Archive/evaluator concepts only; no Phase 0 agent loop. |
| [AlphaEvolve](https://arxiv.org/abs/2506.13131) | Paper/hosted product; no official reusable implementation identified | Cannot test the named system. Community reimplementations are different candidates and out of scope. |
| [The Agentic Researcher](https://arxiv.org/abs/2603.15914) | Method/paper centered on files, tools, and Git | Motivates the mandatory file baseline; not treated as a dependency. |

## Deferred infrastructure named in the blueprint

PostgreSQL, its vector extensions, S3-compatible object storage, workflow
engines, model SDKs, and web frameworks are deliberately not evaluated in Phase
0. The blueprint schedules these for Phase 2 or later, and introducing them now
would violate the explicit no-database/no-product-platform boundary.

## Local environment observation

On the review host, Python 3.14.4 and `/usr/bin/git` are present. `why3`, Lean,
Lake, Elan, PaperQA, LeanDojo, MathGraph, Docker, Cargo, and Deno were not found.
The harness must therefore produce executable blocker records for the optional
spikes while still fully exercising the file baseline and OMDoc projection.

## Selection conclusion

The smallest honest local set is:

1. file-based JSON baseline — fully executable;
2. OMDoc-concept XML projection — fully executable with the standard library,
   explicitly partial and sidecar-backed;
3. Albilich, Why3, Lean, and PaperQA capability adapters — executable probes
   whose absent prerequisites become evidence, with no network installation;
4. all larger or unavailable systems — inventory evidence and explicit defer or
   blocker decisions.

This selection tests the interchange boundary itself without smuggling Phase 1
domain objects or Phase 2 orchestration into the repository.
