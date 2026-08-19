# Phase 3A Implementation Sequence

Status: Phase 3A sequence completed; stop line active
Date: 2026-08-19

This is the authorized bounded sequence.

## Entry gates

Before code changes:

1. record ADR-0012 through ADR-0014 as accepted;
2. retain the repository and real-paper redistribution status as unresolved and
   commit no unlicensed corpus bytes;
3. freeze the five project-authored synthetic fixtures and quantum metadata-only
   record;
4. freeze Recall@5, MRR, citation precision, quarantine, repeated-order, and
   pack-hash thresholds from the accepted matrix;
5. use only the dependency-free internal `plain-text-v1` parser;
6. update `AGENTS.md`, README, blueprint, and Phase 3A documents to the accepted
   roadmap; and
7. record complete hashes of Phase 2 protected evidence and rerun all 101 tests
   plus 19 Phase 0 checks.

## Work packages

### 1. Freeze contracts and negative fixtures

Create canonical JSON schemas, explicit mappers, opaque IDs, and immutable
internal records for source references/artifacts, normalizations, spans, markers,
evidence units, relations, retrieval records, and packs. Add the malformed,
contradictory, and prompt-injection fixtures before implementation behavior is
written.

Exit: schemas and fixtures validate; Phase 1/2 schemas and entities are
unchanged; foreign imports are proposal-only.

### 2. Extend durable ports and migrations

Add inward research-memory ports and one ordered checksum-protected SQLite
migration. Reuse the Phase 2 CAS, transactions, events, jobs, budgets, leases,
cancellation, and idempotency behavior. Canonical payloads remain separate from
SQL rows.

Exit: fresh migration, upgrade/restart, rollback, checksum drift, FK, orphan
blob, and replay tests pass without changing accepted Phase 2 databases.

### 3. Manual source acquisition

Implement local regular-file import and opaque metadata-only URI import. Perform
local syntax validation without DNS, HTTP, redirects, availability, or content
checks. Hash local bytes before parsing, validate media type and rights metadata,
store supported bytes once in CAS, append source/version events, and quarantine
unsupported/malformed input. Metadata-only records retain null content hashes
and cannot produce evidence.

Exit: identical bytes are idempotent; changed bytes create an explicit version;
unsafe inputs cannot escape the selected boundary.

### 4. One normalization adapter

Use the internal deterministic `plain-text-v1` parser and emit normalized UTF-8
text, structure markers, byte-location maps, warnings, and a deterministic hash.
Support valid UTF-8 `text/plain` only; PDFs, invalid UTF-8, and all other media
are quarantined without extraction.

Exit: synthetic gold spans round-trip; malformed/unsupported text cannot import
evidence; parser-version changes create a distinct derived artifact.

### 5. Typed evidence and relation import

Implement deterministic marker-to-unit construction for explicit structures and
manual curation commands for ambiguous structures. Keep parser/model relations
as proposals and source-explicit relations distinct from local truth.

Exit: every source unit has exact coordinates; all required types validate;
model claims cannot carry source origin.

### 6. SQLite FTS5 baseline

Build a rebuildable FTS5 projection from policy-eligible canonical units. Freeze
query normalization, tokenizer, field weights, score serialization, and
tie-breaking. Persist query/result/index manifests, not the FTS table as truth.

Exit: repeat/restart rebuild and retrieval hashes match on the pinned runtime;
engine mismatch fails explicitly.

### 7. Bounded evidence-pack builder

Apply rights/quarantine filters, deduplication, source caps, deterministic
ranking, byte/token budgets, contradiction retention, and injection annotations.
Emit canonical pack bytes and a complete inclusion/exclusion manifest.

Exit: same inputs produce the same pack hash and every excerpt resolves to
source bytes through its span mapping.

### 8. Proposal-only model boundary

Extend only the scripted proposer/verifier fixture to consume pack IDs. Validate
that every cited evidence-unit ID was included in the exact pack. Preserve the
existing isolation and independence labels. Do not require or execute a live
provider call for acceptance.

Exit: fabricated/out-of-pack citations import nothing; valid model output is
still a proposal and awards no warrant.

### 9. Replay, report, and acceptance

Run crash/restart/retry/budget/cancellation demonstrations; canonical export and
re-import; FTS rebuild; report regeneration; prompt-injection and rights tests;
credential scan; the entire Phase 0–3A suite; and all schema validators.

Exit: the gold corpus demonstrates deterministic retrieval/provenance with an
honest report and no quantum convergence claim.

## Stop line

Stop before embeddings or an embedding port, PDF parsing, remote
fetching/crawling, novelty/significance automation, PaperQA2, vector databases,
formal/numeric/symbolic tools, the Phase 3B tool roadmap, multi-agent search,
web/API surfaces, the real academic-corpus demonstration, or a quantum solver.
Any such change needs a new bounded plan and ADR where material.
