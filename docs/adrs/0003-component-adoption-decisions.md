# ADR-0003: Phase 0 component adoption decisions

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** §3.3 and Phase 0 adopt/wrap/interoperate/build decisions
- **Decision owners:** Phase 0 implementer; researcher review pending

## Context

Nineteen named systems, standards, methods, or baselines were scored against the
same dossier. Only the file baseline fully ran. The OMDoc concept projection ran
partially. The host lacks Why3, Lean, PaperQA2, and Albilich; a temporary
Albilich checkout request was rejected by the execution approval service before
Git ran. Several research systems expose papers or sites but no reusable
implementation. These are blockers, not negative capability claims.

## Options considered

See `reports/phase-0/results.json`, `reports/phase-0/scorecard.md`, and the full
inventory. Direct adoption is rejected for every external candidate because no
candidate both passed local hard gates and materially beat the baseline.

## Decision

| Capability | Decision | Boundary |
|---|---|---|
| Canonical dossier and replay | **Build** the small file interchange | Phase 0/1 contract only, not a database |
| Proof-state workflow | **Interoperate** with Albilich after a pinned checkout and export spike | External state returns proposals; MathGraph deferred until licensed/tested |
| Math representation | **Interoperate** through an OMDoc projection; defer MMT runtime | Canonical trust metadata stays in dossier |
| Obligation dispatch | **Wrap** Why3 in Phase 3 if a pinned local prover passes | CLI cannot mutate trusted state |
| Formal proof | **Wrap** Lean in Phase 3 if the exact benchmark/toolchain passes | Kernel output creates candidate evidence pending alignment/import policy |
| Lean retrieval | **Defer** LeanDojo and LeanSearch v2 | Re-evaluate against benchmark fit, Python/toolchain/GPU cost |
| Literature | **Wrap** PaperQA2 no earlier than Phase 4 after a local pinned spike | Retrieved citations remain evidence cards, not applicable theorems |
| Typed provenance | **Interoperate/defer** Eigenius | Too large for Phase 1; exchange typed artifacts only |
| Agent/evolution systems | **Defer/reference** ASTRA, RMA, Aletheia, AlphaProof Nexus, ProofAtlas, FunSearch, AlphaEvolve | No Phase 0 or Phase 1 orchestration dependency |

## Consequences

Phase 1 has no external research-system dependency. This reduces operational
risk but means external export assumptions remain unverified. Why3, Lean, and
literature work remain scheduled in their blueprint phases rather than being
pulled forward.

## Blueprint deviation

The Phase 0 request attempted but could not complete a real Albilich checkout;
only the adapter probe and public-artifact inventory were completed. This is a
recorded environment/approval blocker, not a silent substitution. The Phase 0
exit criterion permits explicitly ruling out unavailable artifacts with
evidence.

## Validation and revisit trigger

Revisit an individual decision only after its pinned local spike exports the
same dossier without hard-gate failure and records replay, cost, and review
time.

