# Phase 2 Bounded Implementation Plan

Date: 2026-08-19

## Clean entry gate

Before this plan was written, the unchanged repository passed all 28 Phase 1
unit tests and all 19 `phase0_harness check` checks. The Phase 1 canonical
dossier round trip retained content hash
`sha256:ee299e0a6d6295dd005f0292ab5b0ac89320862ed1853935ddc0da5d5b9f96fa`.
Phase 1 domain entities, projections, and import semantics are therefore the
compatibility baseline for Phase 2.

## Boundary

Phase 2 adds adapters and an application workflow around the existing trust
core. It does not revise a Phase 1 entity or allow a model, backend, job, or
database row to confer trust. Every model/backend result is first stored as an
untrusted proposal. Only existing domain policy may interpret accepted state.

## Work packages

1. **Ports and immutable Phase 2 records.** Add dependency-free ports for a
   durable workspace, artifact store, clock, and model gateway. Add frozen,
   versioned operational records for runs, jobs, budgets, model calls,
   proposals, verifier manifests, and explicit independence dimensions.
2. **Durable local adapters.** Implement a standard-library SQLite adapter with
   foreign keys, WAL, transactions, checksum-protected ordered migrations,
   append-only semantic events, leased jobs, idempotency keys, atomic budget
   accounting, and restart recovery. Implement a content-addressed filesystem
   store using verified SHA-256 names and atomic replacement.
3. **Model boundary.** Implement strict proposer and verifier response
   validators, versioned prompt templates, a deterministic scripted gateway,
   and an opt-in OpenAI Responses API adapter selected only by configuration.
   Normalize usage/cost, classify retries/refusals, enforce timeouts, redact
   secrets, and retain no hidden reasoning.
4. **One baseline loop.** Persist an accepted dossier, request exactly one
   proposal, import it proposal-only, construct and persist a deterministic
   isolated verifier context/manifest, request exactly one verification, and
   finish either awaiting manual review or honestly unresolved. The workflow
   owns all transitions and commit guards.
5. **External process interchange.** Export canonical input into an isolated
   run directory, execute a bounded command or fixture, capture process
   evidence, reject unsafe or malformed packages, and import valid mathematics
   as proposals only.
6. **Minimal CLI and replay.** Add commands to start/inspect/control a run,
   inspect artifacts/manifests/proposals, export a dossier, and reconstruct the
   audit timeline and report solely from durable canonical state.
7. **Acceptance and demonstrations.** Run all Phase 0/1/2 tests, schema checks,
   deterministic end-to-end run, pause/restart/resume, crash recovery, failed
   and successful external imports, and report regeneration. Run one live
   proposer/verifier sequence only when explicitly configured credentials are
   present; otherwise record a blocker.

## Bounded implementation choices

- Standard-library `sqlite3`, filesystem, `subprocess`, and `urllib` keep the
  deterministic path dependency-free and offline.
- The database stores canonical payload bytes and operational indexes; it does
  not become the domain model.
- Operational job/run rows may advance transactionally. Semantic events and
  content-addressed artifacts remain append-only.
- Cost is recorded in integer micro-USD. A live adapter requires configured
  per-million-token rates; it never invents pricing.
- The verifier produces findings/recommendations, not self-awarded warrants.
  Manual acceptance remains deferred.

## Stop condition

Stop after the durable baseline loop and its evidence. Do not implement any
Phase 3 retrieval, formal-tool, distributed-worker, multi-agent, UI/API, or
novelty/significance features.
