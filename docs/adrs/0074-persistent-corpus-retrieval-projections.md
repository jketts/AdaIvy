# ADR-0074: Persistent Corpus Retrieval Projections

- Status: Accepted and implemented
- Date: 2026-08-22
- Supersedes: the Slice 4 implementation gap recorded by ADR-0072

## Decision

Retrieval over the persistent corpus is a separate immutable projection. The
Slice 3 generation is not edited and continues to state
`retrieval_indexed: false`; a projection binds its generation id and hash to
exactly one `(provider, model_identifier, dimension, normalization)` partition
and immutable content-addressed vector artifacts.

Embedding checks the current Phase 4A decision for the exact processor,
provider, model, and observation time before reading source bytes. Unchanged
vectors are replayed; only deltas call the selected profile-bound gateway.
Vector provenance cannot be mixed or relabelled.

A query is persisted as a partition-bound artifact before the read path.
Retrieval makes no provider call and emits exact-span evidence cards plus an
immutable result manifest. Cards remain untrusted inspiration candidates with
unresolved applicability and create no mathematical warrant.

Takedown invalidates dependent generations and removes affected vector objects
from active retention. Historical manifests cannot be loaded for active use.

## Consequences

- The frozen 19-document Phase 4C benchmark remains unchanged.
- Missing, revoked, malformed, or cross-partition artifacts are refusals.
- Vector bytes are primary replay evidence; rankings are rebuildable.
