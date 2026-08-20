# ADR-0021: Separate deletable Phase 4A content from immutable audit identity

- **Status:** accepted
- **Date:** 2026-08-20
- **Blueprint requirement:** revocable local-source lifecycle and immutable audit history
- **Decision owner:** repository owner

## Context

Phase 3A deliberately stores immutable source-derived canonical records and an
immutable content-addressed artifact. That is incompatible with Phase 4A's
requirement to complete source-specific physical deletion after revocation,
takedown, or a deletion request. Suppression of Phase 3A records or deletion
from persistent FTS shadow tables would not prove erasure.

## Decision

Phase 3A records, persistence, retrieval, and trust semantics remain unchanged.
No destructive Phase 3A migration or purge is authorized. Phase 4A must not
call a Phase 3A persistence path that stores revocable source text.

Phase 4A separates immutable non-content audit identity from revocable content.
Each explicitly supplied source has its own application-controlled content
object under the Phase 4 content boundary. Objects are not globally
deduplicated, so identical bytes supplied as two sources remain independently
deletable. Source bytes and reconstructive evidence-card plaintext are stored
only inside that per-source object. They must not enter Phase 3A canonical
records, Phase 4 metadata SQLite, immutable audit records, canonical exports,
logs, persistent caches, indexes, or operation-owned temporary files after an
operation completes.

Metadata and immutable audit records may retain source and content-object IDs,
content digests, byte lengths, media type, provenance, actors and authorities,
rights history, lifecycle IDs, timestamps, reasons, and predecessor or
supersession links. Exact source spans retain offsets and non-reversible
digests, not quotations. Evidence-card audit records retain hashes and counts;
their reconstructive plaintext remains in the deletable object.

Phase 4A does not create a persistent full-text index. Consequently deletion
has no Phase 4 FTS shadow tables to scrub or rebuild. Persistent FTS suppression
or `DELETE` from an FTS table is not accepted as erasure proof.

## Deletion completion

`deletion_completion` has this testable application-level meaning: after the
workflow succeeds, no raw source bytes or reconstructive plaintext derived
from that source are accessible in AdaIvy-controlled active content objects,
metadata databases, indexes, caches, managed exports, operation-owned
temporary files, or SQLite journals.

The workflow appends a request, immediately suppresses all reads, marks a
durable pending state, removes the complete per-source object (including card
content), clears operation-owned temporary files, checks the Phase 4 boundary
and any detected Phase 3 store, and only then appends completion. Failure keeps
an `incomplete` non-success state and remains fail closed. Restart reconciles a
`requested` or `removing` operation without restoring content. Repeated
completion is idempotent.

If source identity or its digest is detected in Phase 3 immutable storage or
another undeletable AdaIvy store, completion is forbidden, the source remains
suppressed, and a separate owner decision is required. Phase 4A never purges
the detected Phase 3 copy.

## Limits

This application-level result does not claim erasure from filesystem slack,
operating-system snapshots, external backups, user-created copies, previously
exported files outside the managed workspace, or remote systems. Those stores
are outside this workflow's control.

This decision does not authorize crawling, network acquisition, rich PDF,
HTML, or LaTeX parsing, embeddings, vector or hybrid retrieval, model/API
automation, scheduled research, or autonomous applicability decisions.

## Validation and revisit trigger

Validate absence of a unique marker across the metadata database, WAL/SHM or
journal files, content objects, caches, exports, and temporary directories;
evidence-card removal; audit-byte preservation; interruption on both sides of
physical removal; restart reconciliation; failed and Phase-3-blocked deletion;
idempotence; and source-specific deletion of identical bytes. Revisit before
adding any persistent Phase 4 index, derived-content cache, backup integration,
or downstream persistence adapter.
