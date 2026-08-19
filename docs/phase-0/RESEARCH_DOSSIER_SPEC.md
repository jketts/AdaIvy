# ResearchDossier Interchange Specification

**Interchange version:** `0.1.0-phase0`  
**Canonical encoding:** UTF-8 JSON, object keys sorted for hashing, no NaN or
infinite numbers.

This is a Phase 0 transport envelope, not the production domain model. It fixes
the minimum external-artifact contract required by the blueprint while keeping
records opaque enough for external systems to ignore fields they do not
understand without rewriting trusted state.

## Envelope

Required top-level members are:

- `schema_version` and `dossier_id`;
- `problem`, `formalization`, and `semantic_alignment` snapshots;
- `claims`, `open_obligations`, `source_cards`, and `representation_maps`;
- `capabilities`, `evaluation_protocol`, `budget`, and `artifact_manifest`;
- `failed_routes`, which may be empty but may not be omitted;
- `content_hash`.

All entity IDs are opaque non-empty strings. Referenced claims and artifacts
must resolve inside the dossier. Timestamps use RFC 3339 UTC. External systems
must not edit accepted input records; they return candidate artifacts through a
separate result envelope.

## Hashing

`content_hash` is `sha256:<lowercase hex>` over canonical JSON of the complete
dossier with `content_hash` set to `null`. Arrays retain their declared order.
The hash establishes replay identity, not mathematical truth.

## Semantic minimum

- `formalization.target_claim_id` resolves to exactly one claim.
- `semantic_alignment.formalization_id` and `compared_claim_id` match the active
  formalization and target.
- Only `researcher_approved` qualifies as approved alignment; schema validity
  alone does not approve meaning.
- Every open obligation resolves to a claim and has a non-terminal status.
- Every source card contains an exact local source span, imported hypotheses,
  and a separate bibliographic/applicability status.
- A checked applicability record still does not constitute a proof warrant.
- Representation maps retain bridge obligations and exception claims.
- Confirmatory evaluation protocols must be frozen; Phase 0’s fixture is
  exploratory and frozen only to make evaluation inputs immutable.
- `failed_routes` are append-only exported observations, not deleted noise.

## External result envelope

Backends return `BackendResult` with backend identity/version/configuration,
input dossier hash, run status, candidate claims/artifacts, failures, costs,
and an export hash. Imported claims always have `proposal` disposition. No
backend may emit a local trusted verdict.

## Compatibility rules

- Patch versions may add optional fields.
- Minor versions may add record kinds while retaining old meanings.
- Major versions may change required semantics and require an explicit
  migration.
- Readers reject unknown major versions and preserve unknown optional members
  when round-tripping.

The normative structure is `schemas/research-dossier.schema.json`. Semantic
cross-reference and hash rules that JSON Schema cannot express are enforced by
the Phase 0 validator and tests.
