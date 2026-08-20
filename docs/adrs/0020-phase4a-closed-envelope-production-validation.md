# ADR-0020: Use closed-envelope validation for Phase 4A production interchange

- **Status:** accepted
- **Date:** 2026-08-20
- **Blueprint requirement:** fail-closed canonical interchange and dependency isolation
- **Decision owner:** repository owner

## Context

The accepted Phase 4A prompt required standards-conforming whole-envelope
Draft 2020-12 validation, while ADR-0018 and control P4A-SC-022 authorized the
pinned `jsonschema` environment only for the entry gate and prohibited every
production or ordinary-development import of that environment. The repository
has no approved standards-conforming production validator. Those requirements
could not both be satisfied.

ADR-0019 is intentionally absent from this ancestry and remains reserved for
the separate steering work. This decision therefore uses ADR-0020.

## Decision

Phase 4A production uses fail-closed whole-envelope validation equivalent to
the closed, versioned Phase 4A v1 interchange schema. The runtime validator is
implemented with the Python standard library and is closed to exactly schema
`phase4-review-v1`, profile `phase4-review-v1`, and record schema
`adaivy.phase4a-record.v1`. It does not claim general Draft 2020-12 conformance
and must not grow into a general-purpose JSON Schema interpreter.

The canonical SHA-256 of the reviewed production schema is pinned in production
code and tests. Unknown schema keywords, schema versions, profiles, fields,
record types, or unresolved/non-local references fail closed. Any schema drift
requires a new version and explicit review.

The final checked-in `schemas/phase4-review-v1.schema.json` bytes are the sole
digest authority for this version. Their SHA-256 is
`f166aae343997433370c7d61c08e47c52787d51b59af05edae152b074612537a`.
The earlier `083f42…` value identified a provisional pre-correction schema and
is superseded; neither that value nor any disposable audit report is a schema
authority. Production code and the canonical workflow manifest pin the final
digest above and every verification path re-hashes the schema bytes.

The hash-locked, gate-only `jsonschema.Draft202012Validator` remains an
independent reference oracle. A separate differential conformance suite must
prove agreement on every structural valid/invalid case, including independent
mutations, boundary values, Python/JSON boolean-versus-integer cases, complete
keyword coverage, and rejection of unsupported keywords. Domain, actor,
authority, rights, lifecycle, graph, replay, and hash invariants remain separate
production checks after structural validation.

No production third-party dependency is authorized. Production source files
must not import `jsonschema`, `attrs`, `jsonschema-specifications`,
`referencing`, or `rpds-py`; production and ordinary-development requirements
and lockfiles remain unchanged.

The accepted `phase-4-entry-gate-v1` tag and its 18 files remain immutable.
This decision supersedes only the conflicting production-runtime validation
clause. ADR-0018, the bounded prompt, gate reports, gate evidence, fixtures,
spike, and gate schema are not rewritten.

## Consequences

Production imports, initial verification, replay, restart, and fresh-process
verification share one raw-byte boundary. It rejects oversize input before
parsing, malformed UTF-8/JSON and duplicate keys, then performs the closed
structural validation, domain validation, and hashes last before returning a
detached snapshot.

The production contract stays dependency-free and auditable, at the cost of a
validator that cannot be reused for any other schema or version.

## Validation and revisit trigger

Validate the schema digest, used-keyword inventory, production import graph,
differential oracle agreement, strict raw-byte call paths, and all Phase 4A
domain/adversarial tests. Revisit for any schema byte change, new keyword,
record meaning, version/profile, dependency, or attempt to reuse this validator
outside the closed Phase 4A v1 envelope.
