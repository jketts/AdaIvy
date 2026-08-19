# ADR-0009: Permit a local ignored `.env` credential source

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** Phase 2 opt-in provider credentials and secret redaction
- **Decision owners:** repository maintainer and operator

## Context

The Phase 2 live gate originally accepted `OPENAI_API_KEY` only from the
process environment. A key exported in an interactive terminal cannot propagate
back into an already-running desktop application, so repeated preflights could
not see the operator's credential. The operator explicitly requested a local
`.env` workflow. Provider, model, pricing, and budgets must remain non-secret,
versioned run configuration rather than moving into this file.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Process environment only | Repeated preflight reported the key missing | No credential file | Desktop process cannot inherit later shell exports | Operationally blocked |
| General dotenv dependency | Common ecosystem pattern | Broad syntax | New dependency and expansion/injection surface | Unnecessary |
| Strict standard-library `.env` loader | Local tests | Works across desktop launches; no dependency | Local secret exists on disk | Selected with controls |
| Store key in live-run JSON | None | Convenient | Would mix secrets with durable/versioned config | Prohibited |

## Decision

The live CLI may load `OPENAI_API_KEY` from repository-root `.env` only when the
process environment does not already supply it. The loader:

- accepts only `OPENAI_API_KEY`;
- requires a regular non-symlink file with mode `0600`;
- performs no interpolation, substitution, includes, or command execution;
- rejects unknown, duplicate, empty, malformed, or unmatched-quote entries;
- exposes no secret in its result or diagnostics;
- never overrides an existing process-environment credential.

`.env` and `.env.*` are ignored, while `.env.example` is versioned with a blank
value. Provider/model selection and pricing remain in content-hashed JSON.

## Consequences

The credential is no longer environment-only at rest, which is an intentional
operator-approved relaxation. It remains environment-only at the model-adapter
boundary: the loader places it in process memory and the adapter reads only
`os.environ`. The credential file is excluded from artifact, event, database,
log, and report serialization.

## Blueprint deviation

This deliberately departs from ADR-0008's environment-only credential source.
It is necessary for the desktop execution environment and was explicitly
requested by the operator. Revisit if the desktop gains a native secret store
or inherited secret-injection mechanism; prefer that over a disk file.

## Validation and revisit trigger

Tests cover ignored-file rules, permissions, parsing, environment precedence,
absence of interpolation, and non-disclosure. The existing post-run credential
leak scan remains mandatory. Any evidence that `.env` contents enter durable
state immediately invalidates this decision.
