# Lean/mathlib Licensing and Dependency Report

Date: 2026-08-19

Status: proposal reviewed from official upstream metadata; artifacts unacquired

## Direct components

| Component | Proposed pin | Reported license | Treatment |
|---|---|---|---|
| elan | v4.2.1 | Apache-2.0 OR MIT | acquisition tool only; do not vendor without notices |
| Lean 4 | v4.32.1 | Apache-2.0 | external toolchain; record release/binary hashes and notices |
| Lake | bundled with Lean v4.32.1 | Apache-2.0 | external build tool; version and binary hash pending acquisition |
| mathlib | v4.32.1 | Apache-2.0 | external dependency/cache; record exact commit and notices |

The direct license terms are permissive and present no identified architectural
incompatibility with an external checker adapter. This is an engineering
assessment, not legal advice. No upstream source, binary, cache, or license file
was copied into the repository during this gate.

## Transitive lock proposal

The official mathlib v4.32.1 manifest is format 1.2.0 and pins eight dependency
revisions. Those revisions are listed in the proposed manifest. Their licenses
have not been expanded from locally acquired source trees, so the transitive
license audit is **incomplete**. Acceptance requires an inventory generated from
the exact resolved lock; repository landing pages are insufficient evidence for
every file and bundled asset.

## Acquisition and redistribution policy

- Acquire toolchains and caches only in a separately authorized networked step.
- Do not commit the mathlib cache, Lean toolchain binaries, downloaded archives,
  or third-party source trees.
- Retain version, source URL, observed SHA-256, independent expected checksum
  where available, byte size, license expression, and required notices.
- A research check may read only the already pinned local environment and must
  have networking disabled.
- Do not call `lake update`, `lake exe cache get`, elan installation/update, or
  Git fetch from a checker job.

## Resource estimate

Official mathlib documentation describes fetching precompiled artifacts with
`lake exe cache get`; community evidence describes the expanded cache as
multi-gigabyte. This proposal reserves at least 8 GiB for the toolchain,
dependency sources, and cache. Download and expanded sizes remain null until
measured during acquisition. The host currently has 623 GiB free, so disk
capacity is not the blocker.

## License blocker

No direct incompatibility was found. The gate remains blocked because the
transitive inventory and actual acquired-artifact hashes do not yet exist, not
because Lean or mathlib was judged incompatible.
