# Phase 0 Blockers and Failed Integrations

| ID | Candidate/scope | Evidence | Impact | Revisit condition |
|---|---|---|---|---|
| B-001 | Albilich local checkout | No configured/vendored checkout. A temporary `git clone --depth 1` request on 2026-08-19 was rejected by the execution approval service before the command ran. | Proof-state import/export was not exercised; public claims received no capability score. | User-approved/policy-permitted pinned checkout, then run CLI and dossier export spike. |
| B-002 | Why3 | `why3` absent from `PATH`. | Obligation-dispatch fixture remains open. | Pinned Why3 plus named prover in isolated environment. |
| B-003 | Lean | `lean`, `lake`, and `elan` absent from `PATH`. | Lean fixture source exists but no formal warrant was produced. | Pinned Lean toolchain; run fixture twice and inspect dependencies/placeholders. |
| B-004 | PaperQA2 | `paperqa` package and `pqa` executable absent. No network/model credentials used. | Literature package/export behavior was not exercised. | Pinned optional environment with local document/model configuration. |
| B-005 | LeanDojo/ASTRA host compatibility | Host Python is 3.14.4; published requirements exclude it (`<3.13` and `<=3.12`, respectively). | No safe in-environment install attempt. | Separate pinned compatible interpreter and dependency lock. |
| B-006 | MathGraph and ASTRA licensing | No license statement/file visible in their public repositories during review. | Direct adoption/copying fails license hard gate. | Upstream license or written legal clearance. |
| B-007 | MMT modification terms | Repository permits redistribution without modification. | No fork, vendoring with patches, or direct dependency recommendation. | Legal review and packaging plan. |
| B-008 | RMA/Aletheia/AlphaProof Nexus/ProofAtlas/AlphaEvolve | No reusable official implementation identified from the architecture’s sources. | Cannot benchmark product claims locally. | Public versioned code and license. |
| B-009 | Repository versioning/license | Workspace had no `.git` repository and no project license at Phase 0 start. | No commit provenance; file baseline license score is zero. | Owner chooses VCS initialization/history and repository license. |

Blockers are emitted again in `reports/phase-0/results.json`; expected blockers
do not cause the baseline check to fail.

