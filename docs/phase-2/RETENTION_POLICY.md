# Phase 2 Retention and Redaction Policy

Date: 2026-08-19

## Retained

- exact versioned prompt-template text and hash;
- canonical serialized proposer/verifier context and referenced entity IDs;
- schema-validated structured output, concise declared rationale, refusal text,
  result status, retry classification, provider/model/capability metadata, and
  provider request ID when returned;
- on provider HTTP failures: status, SDK exception class, failed request ID,
  provider error type/code/param, sanitized message, Content-Type, full response
  body SHA-256 and byte length, and at most 4096 UTF-8 bytes of sanitized body;
- adapter and SDK versions, model, endpoint, provider request-schema hash,
  provider projection manifest hash, and compatibility-report hash;
- normalized input/output tokens and configured integer micro-USD cost;
- verifier-context bytes and manifest, proposal artifacts, canonical dossier,
  append-only events, jobs, budgets, and report data;
- redacted external-process stdout/stderr, exit status, environment identity,
  input/output/package hashes, and validated proposal payloads.

Phase 2 retains these local records indefinitely because no deletion/hold
workflow exists yet. CAS garbage collection and configurable retention periods
are explicitly deferred.

## Not requested or retained

- hidden chain-of-thought, private reasoning tokens/content, or provider-side
  conversation state;
- credentials, authorization headers, API keys, secret environment values, or
  unredacted secret-like output;
- unvalidated mathematics in accepted domain state;
- proposer self-ratings, persuasive summaries, or unrelated branch history in
  the verifier context.

The live Responses request sets provider-side `store` to false. Credentials are
read only from the configured environment variable at call time and never
enter a port value object, database row, event, or artifact.

## Redaction and failure behavior

Credential-shaped strings and values from secret-like environment variables are
replaced with `[REDACTED]` before process logs, environment identity, provider
messages, or response previews are stored. Authorization and proxy-authorization
headers, cookies, arbitrary response headers, outbound headers, API keys, and
complete environment mappings are never retained. Only response Content-Type
and the SDK's supported failed-request ID are extracted from provider transport
metadata. The complete response body is hashed before its sanitized preview is
truncated to 4096 bytes; unredacted complete response bytes are not retained.
If output cannot pass canonical schema and semantic target/reference checks,
the non-success metadata is retained but no proposal or domain mutation is
committed.

## Revisit gate

Before any multi-user, remote, regulated, or production deployment, define
retention duration, legal hold, deletion, backup, encryption, access control,
and audit-log policy in a new ADR. This Phase 2 policy is local-development only.
