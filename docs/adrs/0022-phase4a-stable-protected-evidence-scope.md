# ADR-0022: Use an explicit stable protected-evidence scope for Phase 4A

- **Status:** accepted
- **Date:** 2026-08-20
- **Decision owner:** repository owner
- **Supersedes:** directory scanning for Phase 4A protected-evidence checks only

## Context

The accepted Phase 4 entry gate recorded a historical protected scope of 199
objects with aggregate
`sha256:cab6d6fb718af616c7be919a147799bc4eadf3a508e547eb6b83acc7ae83d5e5`.
That historical record remains immutable and valid. Four entries were runtime
or host filesystem artifacts rather than stable AdaIvy evidence, so their
ordinary absence made a directory-scan comparison unstable.

## Decision

Phase 4A and later verification uses the explicit, versioned manifest
`reports/phase-4a-production/protected-evidence-v2.json`. It derives a stable
195-object scope from the historical 199-object manifest by excluding exactly:

- `reports/.DS_Store`: host-generated macOS directory metadata;
- `reports/phase-2/.DS_Store`: host-generated macOS directory metadata;
- `reports/phase-3a/acceptance-v1/workspace.sqlite3-shm`: transient SQLite
  shared-memory/index state;
- `reports/phase-3a/acceptance-v1/workspace.sqlite3-wal`: lifecycle-dependent
  SQLite transaction state normally checkpointed after clean shutdown.

These files must not be regenerated or synthesized to satisfy an evidence
check. Their absence is not evidence mutation. The historical manifest,
entry-gate report, entry-gate evidence, tag, object count, and aggregate remain
unchanged.

Every byte of the remaining 195 objects matches the corresponding historical
manifest digest. Their stable aggregate is
`sha256:3965809035292ae610ebf483ea2600a7b216a12dffc7679ca3e9d1857a8debfb`.
The aggregation preimage consists of one UTF-8 line per object, sorted by the
normalized repository-relative POSIX path. Each line is the lowercase
64-character SHA-256 digest, two ASCII spaces, the path, and LF.

Future verification reads only the explicit manifest. It rejects missing or
changed stable objects, duplicate or non-normalized paths, altered exclusions,
extra entries, volatile `.DS_Store`, `-wal`, or `-shm` entries, an aggregate
mismatch, or a manifest content-hash mismatch. Directory enumeration does not
define evidence membership.

## Consequences

No historical object is rewritten. The v2 manifest and this ADR are new Phase
4A evidence-scope records and are not members of the historical protected set
during their own generation.

Any future stable-scope change requires a new manifest version and explicit
owner review. Existing versions and aggregates remain immutable historical
records.
