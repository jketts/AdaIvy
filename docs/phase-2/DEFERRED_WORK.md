# Phase 2 Deferred Work

The following work is deliberately not implemented. This list is a stop line,
not a backlog authorization.

## Trust and review

- Design a human-review command that may accept or reject proposals without
  weakening the Phase 1 warrant policy. Phase 2 only inspects proposals and
  pauses at `awaiting_review`; it does not promote findings.
- Decide whether a future deterministic/formal checker may create a proposed
  verification record and what independent acceptance action is required.
- Define retention periods and deletion/hold policy for prompts, outputs,
  refusals, process logs, orphaned CAS blobs, and live-provider metadata.

## Operational hardening

- PostgreSQL adapter, distributed workers, multi-host leases, high availability,
  and measured contention tests.
- OS/container sandboxing for untrusted executable backends. Phase 2 confines
  the interchange directory, environment, paths, package shape, and timeout,
  but does not claim an operating-system security boundary.
- CAS garbage collection for unlinked crash-orphan blobs, backup/restore,
  migration rollback policy, database encryption, and key management.
- Additional provider adapters, provider-independent verification, dynamic
  pricing registry, streaming, background calls, and remote cancellation.

## Phase 3 and later

This is the immutable Phase 2 closeout view. ADR-0012 subsequently sequenced a
bounded manual research-memory slice as Phase 3A, formal tooling as Phase 3B,
and broader acquisition/crawling/embeddings as Phase 4. That accepted sequencing
does not retroactively change what Phase 2 deferred.

- Web UI, HTTP API, crawler, literature retrieval, embeddings, immutable source
  ingestion, formula search, and novelty search.
- Symbolic, numerical, interval, SMT, Lean, Why3, CAS, PaperQA2, Albilich,
  MathGraph, OMDoc/MMT, Eigenius, or other research/formal integrations.
- Multi-agent teams, evolutionary/branch search, automated novelty or
  significance assessment, and the quantum convergence benchmark/solver.
