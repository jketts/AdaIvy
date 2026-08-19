# Proposed Phase 3A Implementation Sequence

Status: design proposal only  
Date: 2026-08-19

This is a bounded sequence, not implementation authorization.

## Entry gates

Before code changes:

1. approve or reject ADR-0012 through ADR-0014;
2. decide the repository license and corpus redistribution policy;
3. identify the related gold source and record rights for both papers;
4. freeze the corpus manifest, retrieval judgments, acceptance thresholds, and
   storage limits;
5. select and pin one parser after a license/export/coordinate spike;
6. update `AGENTS.md` from Phase 2 only after the roadmap decision; and
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

Implement local regular-file import and metadata-only URI import. Hash before
parse, validate media type and rights metadata, store bytes once in CAS, append
source/version events, and quarantine by default where facts are unresolved.

Exit: identical bytes are idempotent; changed bytes create an explicit version;
unsafe inputs cannot escape the selected boundary.

### 4. One normalization adapter

Select the smallest parser that passes the coordinate/export spike. Run it in a
bounded no-network process, retain process provenance, and emit normalized UTF-8
text, structure markers, location maps, warnings, and a deterministic hash.
Support plain UTF-8 text and exactly one approved PDF path; unsupported media is
quarantined.

Exit: gold spans round-trip; malformed PDF/text cannot import evidence; parser
version changes create a distinct derived artifact.

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

Stop before embeddings, remote fetching/crawling, novelty/significance
automation, PaperQA2, vector databases, formal/numeric/symbolic tools, the
pre-existing Phase 3B tool roadmap, multi-agent search, web/API surfaces, or a
quantum solver. Any such change needs a new bounded plan and ADR where material.
