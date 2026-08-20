# ADR-0018: Bind Phase 4A to enumerated security and reproducibility controls

- **Status:** accepted
- **Date:** 2026-08-20
- **Blueprint requirement:** security, provenance, reproducibility, evaluation integrity, and human authority
- **Decision owners:** repository owner and researcher

## Context

Owner approval applies only to controls explicitly present in the pre-approval
Phase 4 gate artifacts, not to unnamed defaults. The controlling artifacts and
full hashes are:

- gate report:
  `ccd382ebab45eb6eab574ed0794c9252d60829ae20aa12ba270d92a20b8f7d56`;
- machine evidence:
  `89544036e7f300851277b46b1b5403672ca1a6f2a8887366ffb8445b9d3fc117`.

`docs/phase-4/SECURITY_CONTROL_INVENTORY.md` assigns stable control IDs and
exact source locations to that approved set.
`docs/phase-4/ACCEPTANCE_THRESHOLD_INVENTORY.md` enumerates all numeric and
categorical gate thresholds. The final gate evidence records both inventory
hashes and this ADR's hash.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Refer to “documented defaults” | Prior report prose | Short | Ambiguous and silently extensible | Rejected by owner |
| Copy controls into production code | No production authorization | Executable | Would cross gate-only boundary | Prohibited |
| Bind stable IDs to exact artifact locations and hashes | Owner direction | Reviewable and immutable | Inventory maintenance | Selected |
| Approve future capabilities through guardrails | Deferred proposals | Fewer later reviews | Confuses safeguards with capability authorization | Rejected |

## Decision

Accept exactly controls `P4A-SC-001` through `P4A-SC-024` and thresholds
`P4A-AT-001` through `P4A-AT-028` in the two Phase 4 inventories. A production
implementation must cite the applicable IDs in its requirement-test matrix.

Controls describing a possible future network, parser, archive, embedding, or
hybrid boundary are retained only as minimum stop conditions. They do not
authorize that capability. Any new, changed, or unspecified control requires
renewed owner review before a spike or production change.

The Phase 4 gate may use only project-authored synthetic fixtures, the exact
owner-approved gate-only validator amendment below, disposable state, and the
existing pinned repository runtime. Gate artifacts and failed attempts are
machine-readable. Canonical
semantic identity excludes operational timing, process, temporary-path,
scheduler, and storage-layout fields; those values remain separately auditable.

## Consequences

The accepted boundary is mechanically traceable and cannot expand through
general language. A control inventory change invalidates the gate binding.
Gate-only validation adds no production or ordinary-development dependency and
cannot be represented as production Phase 4 capability.

## Blueprint deviation

None. This makes existing security and reproducibility requirements more
explicit.

## Validation and revisit trigger

Validate inventory IDs, artifact hashes, fixture hashes, schema versions,
candidate export hashes, repeat/restart/replay/rebuild equality, protected
seals, credential scans, and scope guards. Revisit on any inventory byte change,
new dependency, new external input, new authority, or production prompt that
does not cite both this ADR and ADR-0017.

## Accepted gate-validator amendment (2026-08-20)

The pre-commit audit found that the candidate schema required standards-
conforming Draft 2020-12 validation but the repository had no pinned validator.
The owner approved exactly five gate-only binary wheels for CPython 3.14 on
macOS 11 or later ARM64. The approval text SHA-256 is
`98244f19de93af73e220dd0d57b0a9b70921f0b8381e0e7b2cc2c2fa47b8846b`.

This amendment replaces only the former “zero new gate dependencies” clause in
P4A-SC-022 and categorical threshold 11. It permits the hash-locked manifest
`requirements-phase4-gate-py314-macos-arm64.txt` in an isolated disposable gate
environment. It does not authorize production or general development
dependencies, source distributions/builds, other platforms, broader networking,
or changes to Phase 2 provider requirements. All other controls and the
production-authorization stop remain unchanged.
