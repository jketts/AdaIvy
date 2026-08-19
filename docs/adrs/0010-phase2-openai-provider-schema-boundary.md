# ADR-0010: Project canonical schemas at the OpenAI provider boundary

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** §§8.1–8.3, C2, C13, Phase 2 model boundary
- **Decision owners:** repository maintainer and operator

## Context

The first live attempt returned HTTP 400 before a response ID or usage record.
The standard-library HTTP adapter discarded the response body, and it sent the
canonical model-output JSON Schema directly to the provider. The canonical
schemas contain constraints such as `uniqueItems` that are valid local trust
requirements but are not in OpenAI's documented Structured Outputs subset.
The failed workspace and status artifact remain unchanged historical evidence.

ADR-0007 selected a standard-library HTTP adapter to avoid an SDK dependency.
The provider failure demonstrated a measured need for the SDK's documented
`APIStatusError.status_code`, `.response`, and failed-request `.request_id`
interfaces and for an explicit provider-schema compilation boundary.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Keep sending canonical schema | Failed HTTP 400 and missing diagnostics | No new code | Provider subset and trust schema remain conflated | Rejected |
| Weaken canonical schema | None | Smaller request | Violates trust and historical schema hashes | Prohibited |
| Project into documented subset, then validate canonically | Local projection/linter and adversarial tests | Preserves trust semantics and fails before network | Projection must track provider documentation | Selected |
| Replace local validation with provider adherence | Provider only promises its supported subset | Less local code | Unsupported semantics could be silently lost | Rejected |

## Decision

Keep the proposer and verifier schemas byte-for-byte canonical. Before budget
reservation, deterministically compile each into an OpenAI-only strict schema,
lint the documented limits, and emit a transformation manifest. Metadata and
locally enforceable unsupported constraints may be omitted only with a named
canonical post-validation rule. Unknown keywords, unsupported composition, or
constraints without reliable local enforcement fail closed before a client or
network request is created.

The response path is provider projection, canonical parsing/validation,
trust-policy checks, then proposal-only import. The projection is never a trust
schema.

Use the optional OpenAI Python SDK pinned to `3.3.0` for the live provider
adapter. Disable SDK retries with `max_retries=0`; workflow policy remains the
only retry authority. Retain a sanitized 4096-byte failure preview, full body
hash and length, Content-Type, failed request ID, SDK/adapter/model/endpoint and
provider-schema identifiers. Never retain authorization, cookies, arbitrary
headers, full environment state, or secrets.

This ADR supersedes only ADR-0007's standard-library HTTP transport decision.
Its provider-neutral port, proposal-only boundary, and independence policy stay
active.

## Consequences

- The offline fake adapter and all Phase 0–2 checks remain SDK-optional.
- A live run now requires the exact optional SDK version and fails preflight if
  it is absent or different.
- Canonical validation remains mandatory even after provider schema adherence.
- Diagnostic bodies are retained only in bounded, redacted form; the full body
  itself is represented by hash and byte length.
- Direct SDK version, upstream artifact hash, license, and removal path are
  recorded in `docs/phase-2/PROVIDER_DEPENDENCY.md`.
- The provider dependency file pins the direct SDK. A fully hash-locked
  transitive environment remains required before claiming clean-room provider
  replay; this does not block the standard-library offline suite or mark the
  live gate passed.

## Blueprint deviation

The SDK addition revises ADR-0007's narrower transport choice after a measured
failure. It does not alter domain dependencies: only the outward adapter imports
the SDK at call time. Revisit on a second provider, a provider subset change, or
an SDK interface change.

## Validation and revisit trigger

Keep this decision only while canonical hashes remain fixed; projection and
manifest output are deterministic; recursive compatibility checks pass; local
canonical constraints reject invalid responses before proposal import; HTTP 400
is not retried; diagnostics pass credential-leak scans; and all Phase 0–2 tests
remain green. The allowlist is based on:
https://developers.openai.com/api/docs/guides/structured-outputs
