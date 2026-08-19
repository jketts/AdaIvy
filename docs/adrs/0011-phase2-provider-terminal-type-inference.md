# ADR-0011: Infer provider-only types for scalar const and enum terminals

- **Status:** accepted
- **Date:** 2026-08-19
- **Supersedes:** no architecture decision; refines ADR-0010 projection rules
- **Blueprint requirement:** §§8.1–8.3, C2, C13, Phase 2 model boundary
- **Decision owners:** repository maintainer and operator

## Context

The immutable v2 live workspace records an OpenAI HTTP 400
`invalid_json_schema` response for provider request
`req_32c9c66a4fb1414292df36cb4c031aad`. The first rejected terminal was
`/properties/schema_version`, where the provider projection emitted only
`{"const":"2.0.0"}`. OpenAI required an explicit type alongside the const.
Five other const/enum terminals had the same latent defect.

The canonical schemas are valid trust contracts and remain byte-for-byte
unchanged. The defect belongs only to the OpenAI projection and its linter.

## Decision

Projection version `openai-strict-schema-projection/1.1.0` adds a provider-only
type when a type-less `const` or nonempty `enum` has an unambiguous scalar JSON
type. Inference checks booleans before integers and supports string, boolean,
integer, and finite number values.

For mixed integers and finite non-integer numbers, infer `number`. JSON Schema's
number type admits both, while the unchanged enum continues to enforce exact
membership. All other mixed values fail closed. Empty enums, null-only values,
non-finite numbers, object values, and array values cannot infer a type.

An explicit canonical type is retained. Every const/enum value must conform to
it; conflicts fail local preflight. The provider linter permits only one type or
a two-member nullable union and accepts structural `$ref` and `anyOf` nodes when
their referenced or branch schemas are valid.

Each inferred type is recorded as a deterministic `add` operation with its JSON
Pointer, inferred value, const/enum source, canonical value summary and hash,
reason, canonical validation rule, and provider-only status.

## Consequences

- Canonical proposer and verifier bytes and hashes do not change.
- Projected schemas and their hashes change as expected.
- All six inferred terminals are visible in the generated manifests.
- Projection/linter failures still occur before budget reservation and network
  construction and cannot import proposals.
- The failed v2 workspace, status, request ID, diagnostics, events, and hashes
  remain immutable. Any later attempt must use the v3 configuration, workspace,
  and run ID.
- Canonical post-response and trust-policy validation remain mandatory.

The provider subset is based on the current OpenAI Structured Outputs guide:
https://developers.openai.com/api/docs/guides/structured-outputs
