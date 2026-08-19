# OpenAI Structured Outputs Compatibility Report

- Compatible: yes
- Projection: `openai-strict-schema-projection/1.1.0`
- Canonical schema hash: `sha256:243155a597985e90a00d560cd1f4aa18e16e8ffcde29b6c163a9b1a0ea96652d`
- Provider schema hash: `sha256:7da47da062224e0777931f204baeb3b760f1853f77ce5f54850e21c0782a636d`
- Documentation: https://developers.openai.com/api/docs/guides/structured-outputs
- Object properties: 11/5000
- Nesting depth: 5/10
- Enum values: 9/1000
- String budget: 230/120000

## Issues

- None.

## Transformations

- `removed` `/$id`: canonical schema identity is retained outside the provider projection; post-validation `canonical.schema.identity_and_metadata_retained`.
- `removed` `/$schema`: JSON Schema dialect metadata is not part of the provider response contract; post-validation `canonical.schema.identity_and_metadata_retained`.
- `removed` `/properties/declared_rationale/maxLength`: constraint is not in the documented provider allowlist and remains locally enforced; post-validation `canonical.string.max_length`.
- `add` `/properties/findings/items/properties/outcome/type`: OpenAI strict-schema terminal typing; inferred `string` from `enum`; canonical values `3-value string enum`; canonical value hash `sha256:2d48130c78afa22c71ecf7c1852afc3b902875bfb9b4ab37706063f7108a85ee`; provider-only `true`; post-validation `canonical.enum`.
- `removed` `/properties/findings/items/properties/referenced_entity_ids/uniqueItems`: constraint is not in the documented provider allowlist and remains locally enforced; post-validation `canonical.array.unique_items`.
- `rewritten` `/properties/findings/items/required`: OpenAI Structured Outputs requires every object property to be required; post-validation `canonical.object.original_required_and_optional_semantics`.
- `add` `/properties/recommendation/type`: OpenAI strict-schema terminal typing; inferred `string` from `enum`; canonical values `3-value string enum`; canonical value hash `sha256:04ca677198ccb177003825f8c822188e726750d28b7235a36929bc881130a1cd`; provider-only `true`; post-validation `canonical.enum`.
- `add` `/properties/result_type/type`: OpenAI strict-schema terminal typing; inferred `string` from `enum`; canonical values `3-value string enum`; canonical value hash `sha256:5c589c9ac0e86323ad81fa309424b52f3bce6ad4ba24a7c72448f5f08d06c0e4`; provider-only `true`; post-validation `canonical.enum`.
- `add` `/properties/schema_version/type`: OpenAI strict-schema terminal typing; inferred `string` from `const`; canonical values `const string`; canonical value hash `sha256:0175d86befbe75525f132794baff42abbf4e2a659aa20f2baec341740a9573e7`; provider-only `true`; post-validation `canonical.const`.
- `removed` `/properties/target_claim_id/minLength`: constraint is not in the documented provider allowlist and remains locally enforced; post-validation `canonical.string.min_length`.
- `rewritten` `/required`: OpenAI Structured Outputs requires every object property to be required; post-validation `canonical.object.original_required_and_optional_semantics`.
- `removed` `/title`: display metadata is not needed by the provider response contract; post-validation `canonical.schema.identity_and_metadata_retained`.

The projected schema is provider-specific and is not a canonical trust schema. Every response is parsed and validated again against the unchanged canonical schema before trust-policy checks or proposal-only import.
