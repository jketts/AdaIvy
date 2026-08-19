# Phase 0 Execution Plan

**Status:** frozen implementation plan  
**Scope source:** `TECHNICAL_BLUEPRINT.md` §19, Phase 0  
**Goal:** determine what to adopt, wrap, interoperate with, or build before any
production trust-core implementation.

## Deliverables

1. A versioned `ResearchDossier` JSON Schema and valid/invalid reference
   fixtures.
2. A standard-library evaluation harness that validates, hashes, runs, replays,
   and compares component spikes with a file-based baseline.
3. Reproducible spikes for the smallest locally executable representatives:
   file baseline, OMDoc-like XML interchange, Why3 obligation dispatch, Lean
   checking, and a PaperQA-style literature interchange probe.
4. Explicit unavailable/blocker records for candidates that cannot be installed,
   exported, licensed, or exercised locally.
5. A completed component inventory and scorecard with evidence paths.
6. ADRs for the Phase 0 interchange and component decisions.
7. A Phase 1 proposal based only on demonstrated gaps.

## Work sequence and gates

| Step | Work | Gate |
|---|---|---|
| 0.1 | Freeze dossier fields, fixture semantics, metrics, and scoring rubric | Planning artifacts exist before harness code |
| 0.2 | Inventory candidates, source/license status, interfaces, and local prerequisites | Unknown facts are marked unknown, not inferred |
| 0.3 | Select one smallest representative per required category | Selection has a runnable command or recorded blocker |
| 0.4 | Implement schema validator, deterministic file baseline, subprocess runner, and report format | Standard-library unit checks pass offline |
| 0.5 | Implement bounded spikes against the identical dossier | Each spike records environment, duration, stdout/stderr, exit status, and outputs |
| 0.6 | Replay outputs and score candidates against the baseline | Repeated runs have stable semantic hashes or disclose drift |
| 0.7 | Complete decisions and Phase 1 proposal | Every local subsystem maps to a measured gap |

## Reference experiment

The dossier uses a deliberately elementary target: “the sum of two even
integers is even.” It includes:

- an immutable informal statement and approved formalization;
- an approved semantic-alignment record;
- one accepted definition claim;
- one target claim;
- one exact source card with a deliberately unresolved applicability review;
- one open proof obligation;
- one representation map;
- a frozen exploratory evaluation protocol;
- a deterministic budget and artifact manifest.

The target is small enough to represent in every candidate without conflating
component setup with research capability. A negative fixture weakens the target
to a non-equivalent statement while retaining a claimed approval, and another
uses a real-looking source whose hypotheses do not match.

## Common measurements

All integrations receive the same canonical dossier and are measured for:

- schema/import success;
- target fidelity (exact target and alignment IDs survive round-trip);
- source applicability preservation;
- open-obligation and failed-route retention;
- evidence/warrant separation;
- deterministic export and replay;
- verifier input reconstruction;
- wall time, external process count, and manual steps;
- license clarity, maintenance evidence, local/offline operation, and export
  completeness.

The file baseline defines the minimum: lossless deterministic JSON round-trip,
hash replay, full trace retention, no external processes, and no semantic
verification claim.

## Selected minimal integrations

| Category | Primary spike | Reason for minimality | Fallback/blocker behavior |
|---|---|---|---|
| Proof state | Albilich import/export capability probe | Closest open workflow named by the blueprint | Record repository/package/tool absence; evaluate its public schema only if vendored artifacts exist |
| Representation | OMDoc-compatible XML projection | Standards-based and implementable without an MMT server | Preserve unsupported dossier fields in an explicit sidecar; never claim full MMT conformance |
| Obligation dispatch | Why3 single goal to configured provers | Small CLI boundary with machine-checkable exit/output | Record missing binary/prover as a blocker result |
| Formal/tool | Lean single theorem file | Small trusted-kernel smoke test | Record missing `lake`/`lean` and do not substitute model review |
| Literature | PaperQA package/import capability and citation-card export probe | Exercises literature boundary without crawling | Use a local source card only; record unavailable package/API/model credentials |

MathGraph, LeanDojo, LeanSearch, ASTRA, AlphaProof Nexus, RMA, Aletheia,
FunSearch, AlphaEvolve, and Eigenius remain inventory/comparison candidates but
are not all install targets. Phase 0 does not clone large systems merely to
claim coverage.

## Explicit exclusions

No production entities/repositories, PostgreSQL, object storage, crawler,
retrieval index, web/API/CLI product interface, model gateway, multi-agent loop,
or quantum benchmark solver will be implemented. The elementary dossier is an
interchange test, not an attempt at mathematical discovery.

## Completion evidence

Phase 0 is complete when one command runs all offline checks and spikes,
produces a machine-readable report and Markdown scorecard, records every failed
integration as data, and the ADRs make a specific recommendation for each
required capability category.
