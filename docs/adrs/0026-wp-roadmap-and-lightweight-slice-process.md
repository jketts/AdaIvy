# ADR-0026: Resume delivery with a lightweight per-slice process

- **Status:** accepted
- **Date:** 2026-08-20
- **Blueprint requirement:** Section 19 delivery roadmap; AGENTS.md change control
- **Decision owners:** repository owner

## Context

Phases 0 through 6 are implemented as bounded vertical slices and the complete
documented offline check passes: 270 tests (15 skipped for the disposable
`jsonschema` gate environment), the Phase 0 harness check, and every Phase 1,
2, 3A, 3B, 5, and 6 CLI acceptance path.

The verified remaining gap is capability, not correctness:

- Phase 4 exists only as the bounded 4A rights/applicability slice. There is no
  acquisition, PDF/TeX parsing, embedding, or hybrid retrieval, so the first
  benchmark paper (`arXiv:quant-ph/0201109`) remains a metadata-only record with
  no content.
- ADR-0025 exploratory multi-result synthesis is specified but unimplemented.
- Phase 5 covers only the exact commuting/diagonal `QD-FS-01` tier; the JRF
  convergence question is noncommuting.
- Search tiers 2--4 are recorded and disabled.
- Novelty and significance are `not_assessed`; no external evaluation exists.

Phases 3B through 6 were each delivered with a full gate package: entry gate
report, bounded implementation prompt, acceptance-threshold inventory, security
control inventory, dependency/license assessment, and requirement-test matrix,
several bound to owner-approval SHA-256 values. That process is a genuine asset
for trust-bearing work, but its cost per slice is high, and the owner has
determined it is disproportionate for the remaining delivery.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (full gate package per slice) | Phases 3B--6 precedent | Maximum auditability; internally consistent repository | Highest cost per slice; the dominant cost of remaining delivery | Owner approval per gate |
| Wrap (full for trust-bearing, light for plumbing) | Mixed precedent | Proportionate | Boundary between categories is itself a judgement call each time | Category ruling per slice |
| Interoperate (ADR plus tests per slice) | Phases 0--2 precedent | Fastest defensible cadence; ADR record preserved | Loses threshold inventories and explicit security control enumeration | ADR plus green acceptance suite |
| Build/defer (no new process) | -- | -- | Silent architecture drift, prohibited by AGENTS.md | -- |

## Decision

Adopt the interoperate option. Each remaining slice is delivered with exactly
one ADR plus an acceptance test suite that encodes the slice's thresholds as
executable assertions. The threshold inventory, security control inventory,
entry gate report, and bounded implementation prompt are no longer produced as
separate documents for new slices.

Delivery order, accepted by the owner:

- **WP0** repository hardening: installable package, one check entrypoint,
  continuous integration, and honest environment-dependent skips.
- **WP3** ADR-0025 exploratory multi-result synthesis, scenarios `ERS-AC-01`
  through `ERS-AC-12`. Selected first because it is fully specified, adds no
  dependency, and requires no network.
- **WP1/WP2** Phase 4B acquisition and parsing, then Phase 4C hybrid retrieval.
- **WP4** noncommuting Phase 5 expansion and search tiers 2--4.
- **WP5** Phase 6 external evaluation and release hardening.

Two standing policies are also accepted:

- **Dependencies.** Production dependencies are permitted where a slice needs
  them, held to the existing Phase 4A gate standard: exact pinned wheels,
  recorded SHA-256 digests, licenses, offline `--require-hashes` installation,
  and a recorded assessment. WP0 and WP3 add none.
- **External surfaces.** Network acquisition and live model calls are permitted
  only as explicitly gated, opt-in adapters following the Phase 2 provider
  precedent. Every documented acceptance path stays offline, deterministic, and
  free of model and network calls.

## Consequences

New slices carry less standalone documentation, so the acceptance suite becomes
the sole executable record of a slice's thresholds; a weak test is now a direct
loss of auditability rather than a documentation gap. Reviewers lose the
per-slice security control enumeration and must read the ADR and tests instead.
The historical gate packages for Phases 3B through 6 remain effective and
authoritative; this ADR does not weaken or reopen them, and their
owner-approval hashes stand.

Existing sealed boundaries are unchanged: Phase 1 trust semantics, sealed
Phase 2 evidence, Phase 3A memory, the sealed Phase 3B runtime, and Phase 4A
rights and applicability remain authoritative for all later work.

## Blueprint deviation

Two deviations.

First, the process deviation above: Section 19 and the Phase 3B--6 precedent
imply a full gate package per slice, and ADR-0025 Section 13 requires an
owner-approved plan defining trust paths, rights uses, bounds,
dependencies/licenses, schemas, migrations, threat models, event vocabulary,
acceptance fixtures, protected evidence, and production-path tests before
implementation begins. This ADR plus the WP3 implementation ADR are the
owner-approved substitute; the substantive requirements are satisfied inside
those ADRs and the acceptance suite rather than in separate documents. The
requirement is redirected, not waived.

Second, WP3 implements ADR-0025 without the "independent integration re-audit
and dedicated owner-approved entry gate" that Section 19 and ADR-0025 name as
preconditions. The owner has authorized proceeding. The compensating control is
that the WP3 acceptance suite must implement all twelve `ERS-AC` scenarios
including every stated forbidden outcome, and each scenario's forbidden cases
must be demonstrated impossible rather than merely untested.

Revisit trigger: any slice that touches the Phase 3B sealed runtime, the
Phase 4A rights boundary, deletable content, or protected evidence manifests
returns to the full gate package.

## Validation and revisit trigger

The decision stays valid while the complete offline check remains green, every
new slice carries an ADR, and no new slice introduces an ungated network call,
model call, or unpinned dependency.

Reconsider if an acceptance suite is found to assert a threshold it does not
actually enforce, if a slice ships without its ADR, or if a defect reaches a
sealed boundary that a threshold inventory would plausibly have caught.
