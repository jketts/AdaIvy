# Phase 4A Entry-Gate Requirement/Test Matrix

Status: gate-only
Date: 2026-08-20

| Requirement/control | Gate evidence | Verification |
|---|---|---|
| P4A-SC-001–006 local/plain-text/untrusted-input boundary | ADR-0017; security inventory; synthetic corpus only | Fixture schema/hash validation; scope scan; Phase 3A quarantine tests |
| P4A-SC-007–010 per-use rights and complete decision provenance | Six distinct rights-state cases; audit-complete candidate records | Full actor/authority/reason/evidence/time/version/order/link/hash fields; seven independently rehashed actor/authority mutations rejected through both replay and restart |
| P4A-SC-011–013 append-only correction/revocation/deletion/takedown | Four explicit lifecycle cases; immutable before/after record bytes | monotonic append; unique IDs; target/chain/cycle checks; correction record; deletion/takedown tombstones; replay |
| P4A-SC-014–017 human applicability authority and closed reasons | complete 20-cell actor × outcome matrix: 15 nonhuman proposal cells and five explicit human-final mappings | every nonhuman result remains a proposal with null final status; every outcome has a human-final mapping; unknown actors fail closed |
| P4A-SC-018–020 separate/versioned/canonical export | Candidate export v1 with record v1 | one strict raw-byte boundary for initial verification, import, replay, restart, and fresh process: byte cap, strict JSON, whole-envelope Draft 2020-12 schema, domain invariants, graph/history, then envelope hash; verified snapshot is detached from caller data |
| P4A-SC-021 existing deterministic lexical baseline | Phase 3A acceptance | recall@5 1.0; MRR 1.0 observed versus minima 1.0/0.75; restart/rebuild stable |
| P4A-SC-022 dependency/license boundary | owner amendment; platform manifest; dependency assessment | zero production dependencies; exactly five hash-locked wheels; isolated offline install; installed inventory equality |
| P4A-SC-023 run budgets | measured gate observations and boundary tests | bounded input reader at 2 MiB/2 MiB+1; 256/257; real incremental exporter/sink at 64 MiB/64 MiB+1 with atomic discard; cooperative monotonic deadline during actual work; independent parent hard timeout; USD 0 |
| P4A-SC-024 scope and preservation | machine evidence scope guards | protected hashes; credential scan; two Phase 3B sealed runs; Git diff validation |
| P4A-AT-001–009 exact corpus distribution | fixture manifest | exact class counter comparison |
| P4A-AT-010–015 safety/accuracy metrics | candidate result | exact equality against accepted threshold map |
| P4A-AT-016–020 determinism | candidate result | three in-process repeats, two independent processes, one restart, one replay, one reverse rebuild; all accepted raw exports traverse the same strict verifier |
| P4A-AT-021–022 lexical non-regression | Phase 3A demo evidence | accepted retrieval evaluation |
| P4A-AT-023–028 resources and zero-action guards | measured candidate result; report and machine evidence | actual input/record/output/time/cost observations; streaming UTF-8 byte accounting and incremental hash; no complete output string before the size decision; exact boundary, cooperative-expiry, hard-timeout, atomic-failure, scope, credential, and protected-seal checks |
| Phase 0-3B preservation | repository baseline and sealed v5 evidence | all tests, Phase 0, Phase 3A, two Phase 3B runs/replay, all v5 conditions |

The gate spike validates contracts only. Its schema checks run exclusively in
the owner-approved disposable gate environment. It is not a production record
model, database adapter, migration, service, parser, retriever, or workflow.
Schema validity is necessary but is not domain acceptance: actor/authority,
rights/applicability separation, references, hashes, graph integrity, ordering,
lifecycle, append-only history, and the envelope hash are checked after schema
validation by the same fail-closed raw-byte boundary.
