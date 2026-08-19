# OpenAI Structured Outputs Compatibility Report

- Compatible: yes
- Projection: `openai-strict-schema-projection/1.1.0`
- Canonical schema hash: `sha256:29a9a65656f50cecefd40b0f11ff8750e5d164549b85d153177bb13ac4a238ce`
- Provider schema hash: `sha256:ae6fb22a5691ab4090bf8e16c7048f61379f1d037ae3fe973b8bbf93c9fadff5`
- Documentation: https://developers.openai.com/api/docs/guides/structured-outputs
- Object properties: 9/5000
- Nesting depth: 4/10
- Enum values: 4/1000
- String budget: 174/120000

## Issues

- None.

## Transformations

- `removed` `/$id`: canonical schema identity is retained outside the provider projection; post-validation `canonical.schema.identity_and_metadata_retained`.
- `removed` `/$schema`: JSON Schema dialect metadata is not part of the provider response contract; post-validation `canonical.schema.identity_and_metadata_retained`.
- `removed` `/properties/declared_rationale/maxLength`: constraint is not in the documented provider allowlist and remains locally enforced; post-validation `canonical.string.max_length`.
- `removed` `/properties/referenced_entity_ids/uniqueItems`: constraint is not in the documented provider allowlist and remains locally enforced; post-validation `canonical.array.unique_items`.
- `add` `/properties/result_type/type`: OpenAI strict-schema terminal typing; inferred `string` from `enum`; canonical values `4-value string enum`; canonical value hash `sha256:e0e4fdf5f521e217138534e52e6ebdaf77e982730907b715a45c9402b80ec73b`; provider-only `true`; post-validation `canonical.enum`.
- `add` `/properties/schema_version/type`: OpenAI strict-schema terminal typing; inferred `string` from `const`; canonical values `const string`; canonical value hash `sha256:0175d86befbe75525f132794baff42abbf4e2a659aa20f2baec341740a9573e7`; provider-only `true`; post-validation `canonical.const`.
- `removed` `/properties/target_claim_id/minLength`: constraint is not in the documented provider allowlist and remains locally enforced; post-validation `canonical.string.min_length`.
- `rewritten` `/required`: OpenAI Structured Outputs requires every object property to be required; post-validation `canonical.object.original_required_and_optional_semantics`.
- `removed` `/title`: display metadata is not needed by the provider response contract; post-validation `canonical.schema.identity_and_metadata_retained`.

The projected schema is provider-specific and is not a canonical trust schema. Every response is parsed and validated again against the unchanged canonical schema before trust-policy checks or proposal-only import.
