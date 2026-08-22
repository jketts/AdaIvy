# ADR-0073: Canonical identifier for campaign experiment and verifier wiring

- **Status:** accepted and implemented 22 August 2026
- **Date:** 2026-08-22
- **Supersedes:** the identifier and citation authority of
  `0072-campaign-experiment-and-verifier-wiring.md`; it does not supersede
  `0072-end-to-end-campaign-authority.md`
- **Blueprint requirement:** C7, C10, C13; ADR-0065; ADR-0066; ADR-0072
- **Decision owners:** repository owner and researcher

## Context

Two parallel branches independently allocated ADR-0072. The end-to-end
campaign-authority record landed first and is the authoritative ADR-0072. The
other accepted record wired the activated experiment sandbox and isolated
verifier router into `campaign run`. Reusing a bare identifier for both would
make audit references ambiguous, while deleting or silently renumbering the
parallel decision would erase history.

## Decision

ADR-0073 is the canonical identifier for the campaign experiment and verifier
wiring decision. It adopts the complete technical decision, boundaries,
falsifiability probes, and open questions recorded in
`0072-campaign-experiment-and-verifier-wiring.md` without changing them.

The historical duplicate remains in the repository with explicit supersession
metadata. Current code, tests, capability documentation, and later decisions
must cite ADR-0073 when referring to Slice 6 wiring. Bare ADR-0072 means only
`0072-end-to-end-campaign-authority.md`.

## Consequences

No runtime behavior or authority changes. This record only restores an
unambiguous append-only decision history.

## Validation and revisit trigger

The ADR index must list both historical files and this canonical successor.
Repository references to Slice 6 wiring must cite ADR-0073 or the complete
historical filename. Revisit only if another accepted decision supersedes the
actual experiment/verifier boundary.
