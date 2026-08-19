# ADR-0006: SQLite durable workspace behind persistence ports

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** revision 0.2 dependency direction and Phase 2 exit criteria
- **Decision owners:** repository maintainers

## Context

Phase 2 needs transactions, migrations, durable jobs and events, restart
recovery, and reproducible replay on one local workstation. The blueprint names
PostgreSQL as the production default, but no measured Phase 2 acceptance test
requires networked or concurrent multi-host storage. Phase 1 currently has no
persistence ports and must remain dependency-free.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt PostgreSQL | Blueprint production default | Production concurrency features | Service dependency, migrations/operations beyond bounded phase | No measured local requirement |
| Wrap SQLite | Standard-library adapter can exercise transactions, FK, WAL, leases, and recovery | Small, offline, reproducible | Single-host write limits; SQL dialect differs | Must remain behind ports and pass restart/recovery tests |
| Interoperate with files only | Phase 0 baseline exists | Very small | Cannot atomically exercise durable jobs and event/state commits | Fails Phase 2 transaction requirement |
| Build database | None | Custom control | Unacceptable correctness and scope risk | Rejected |

## Decision

Wrap SQLite as the sole Phase 2 durable workspace adapter. Enable foreign keys
and WAL on every connection. Apply ordered migration files transactionally and
record each migration checksum. Keep canonical JSON payloads and artifact hashes
at the boundary. Use immutable ports and records in the application layer; the
Phase 1 domain imports no adapter, SQL, model-provider, or CLI package.

The content-addressed artifact store is a separate filesystem adapter. A
semantic commit links an already-written immutable blob in one database
transaction. An unlinked blob after a crash is an inert orphan; retrying the
same content hash links it once.

## Consequences

The offline acceptance path has no new runtime dependency and can demonstrate
transaction rollback, migrations, leases, budgets, and restart replay. SQLite
is not claimed to satisfy distributed-worker throughput or high availability.
Operational job/run rows advance under transactions; semantic event rows and
content-addressed blobs are append-only. Migration checksum drift is a hard
startup error.

## Blueprint deviation

The deviation is postponing the blueprint's PostgreSQL production default.
Necessity: Phase 2 is explicitly a smallest-local-adapter phase and has no
measured requirement for PostgreSQL. Revisit before distributed workers,
multi-user deployment, or whenever lease/contention measurements exceed local
SQLite capabilities.

## Validation and revisit trigger

Keep this decision only while fresh migration, rollback, FK/WAL, idempotency,
crash recovery, restart replay, and deterministic report tests pass. Add a new
ADR and adapter contract suite before introducing PostgreSQL.
