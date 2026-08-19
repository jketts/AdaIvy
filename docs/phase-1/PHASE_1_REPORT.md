# Phase 1 Outcome

## Delivered

Phase 1 implements the revision-0.2 trust core as frozen typed entities with
opaque IDs, append-only in-memory repositories/events, derived trust policies,
canonical JSON interchange, proposal-only external import, five fixtures, a
manual CLI, and an entity-ID-traceable report. It introduces no third-party
dependency and performs no network access.

The Phase 0 scorecard is corrected without rewriting raw observations. Only the
file baseline (`100.0`) and OMDoc projection (`69.4`) have measured capability;
all blocked/deferred candidates have `capability_score: null`.

## Architecture decisions

- ADR-0004 separates scorecard dimensions and preserves raw evidence.
- ADR-0005 separates internal trust entities from canonical dossier JSON and
  records the standard-library validated-dataclass choice.
- No additional material deviation from architecture revision 0.2 was needed.

## Verification result

The offline suite covers Phase 0 compatibility, schema/fixture validation,
immutability, append-only behavior, all ten mandatory adversarial boundaries,
canonical export/import, external proposal import, CLI creation/inspection,
and report traceability. The recorded manual dossier is policy-projected as
`proved` only because its exact target alignment, rigorous warrant, accepted
evidence, independent verification, and discharged bridge obligations all
agree.

Unimplemented Phase 2+ work is listed in `docs/phase-1/DEFERRED_WORK.md`.
