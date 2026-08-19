# ADR-0013: Keep canonical research memory separate from SQLite FTS5

- **Status:** proposed
- **Date:** 2026-08-19
- **Blueprint requirement:** §§7, 12.2, 14; provenance and rebuildable-index rules
- **Decision owners:** researcher and repository maintainer

## Context

Phase 3A needs deterministic local retrieval on a small manual corpus. The
blueprint anticipates hybrid lexical/vector/formula/graph retrieval, but makes
all indexes rebuildable projections. Phase 2 already selected SQLite for a
single-host durable workspace. The current Python runtime reports SQLite 3.53.3
with FTS5 available; no measured Phase 3A requirement needs a vector database,
search service, or PostgreSQL.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Store canonical units only in FTS/vector rows | Common retrieval pattern | Small data path | Loses exact typed provenance and rebuildability | Violates blueprint |
| Add vector database immediately | No Phase 3A acceptance need | Semantic retrieval | Dependency, cost, drift, canonical coupling | Rejected |
| Use SQLite FTS5 as a derived adapter | Existing SQLite decision and local FTS5 preflight | Small, offline, deterministic under pin | Cross-version BM25/tokenizer drift | Selected proposal |
| Build a custom search engine | None | Full control | Unnecessary correctness/maintenance risk | Rejected |

## Proposed decision

Store immutable source/memory records and canonical JSON behind repository
ports, with source/derived bytes in CAS. Build SQLite FTS5 tables solely as
rebuildable projections. Record the corpus/index manifest, SQLite version,
compile option, tokenizer, field weights, query grammar, score serialization,
and deterministic tie-breaking for every result.

Expose an optional `EmbeddingProvider` port, but require no adapter for Phase 3A
acceptance and forbid embeddings/vector rows from owning canonical source text,
spans, relations, or trust state.

## Consequences

The baseline stays local, offline, and operationally small. Dropping/rebuilding
FTS cannot change canonical exports. Cross-version byte identity is not assumed;
an engine/tokenizer mismatch is an explicit replay blocker. Later hybrid
retrieval can add adapters without migrating trust semantics.

## Blueprint deviation

None in persistence semantics. This deliberately implements only the lexical
subset of the future hybrid strategy and postpones PostgreSQL/vector defaults
until measured requirements justify them.

## Validation and revisit trigger

Keep only if rebuilds, restart retrieval, deterministic tie-breaking, exact
spans, complete manifests, project filters, and prompt-injection tests pass.
Revisit when a frozen evaluation demonstrates that lexical retrieval misses a
required capability enough to justify an embedding/formula/graph adapter.
