# Phase 2 Completion Report

Date: 2026-08-19

## Outcome

The durable local workspace and single baseline proposer/verifier loop are
implemented without changing the Phase 1 domain or trust policy. The offline
acceptance path passes. Full Phase 2 acceptance now **passes**: the manually
initiated v3 run recorded exactly one live proposer call and one separately
context-isolated live verifier call. Earlier blocked and failed attempts remain
preserved in the status history and their immutable workspaces.

No Phase 3 feature was implemented.

## Clean entry and compatibility

Before Phase 2 code was written, the repository passed 28 Phase 1 tests and all
19 Phase 0 component checks. The unchanged Phase 1 dossier retained canonical
content hash
`sha256:ee299e0a6d6295dd005f0292ab5b0ac89320862ed1853935ddc0da5d5b9f96fa`.
The immutable Phase 0 raw observation file still has SHA-256
`e8166fed8063ade26d74b55f0139fc2adfd2900d2c8db4a4c3fb8c4a5b144533`.

After the live acceptance record was added, all 101 tests pass, including every
Phase 1 adversarial test, and all 19 Phase 0 checks pass. The Phase 1 CLI
export/import demonstration also passes with its original content hash.

## Implemented boundary

- Frozen Phase 2 value objects and provider-neutral ports exchange opaque IDs,
  schema versions, canonical JSON, and hashes.
- SQLite uses foreign keys, WAL, `FULL` synchronous writes, explicit
  transactions, and ordered checksum-protected migrations `0001` and `0002`.
- Semantic events are append-only and idempotent. Jobs have durable states,
  idempotency keys, leases, retries, attempts, deadlines, and late-commit
  guards. Budgets cover input/output tokens, integer micro-USD cost, elapsed
  time, and attempts.
- The filesystem artifact adapter writes SHA-256 addressed immutable blobs
  atomically and verifies reads.
- The scripted model gateway is deterministic. The opt-in OpenAI Responses
  adapter sends strict JSON-schema output requests with `store: false`, bounded
  output, timeout handling, refusal/retry classification, normalized usage and
  configured cost, capability/model recording, and no hidden-reasoning request.
- Exactly one baseline workflow builds a bounded proposal context, imports a
  candidate as a proposal, constructs an isolated verifier context, persists
  its manifest, imports only a verifier finding, and stops at manual review or
  unresolved.
- The filesystem/process backend records redacted stdout/stderr, exit status,
  environment identity, package/output hashes, timeouts, cancellation, and a
  canonical event. It rejects traversal, symlinks, unexpected files, bad hashes,
  unknown targets, and schema/input-hash mismatch before proposal-only import.
- The manual CLI supports start/advance, jobs, budgets, pause/resume, model
  artifacts, verifier manifest, proposal review, dossier export, audit timeline,
  report, and the full demonstration.

The offline suite remains standard-library-only. The live OpenAI adapter now
has one optional direct dependency, `openai==3.3.0`, whose upstream artifact
hash, Apache-2.0 license, purpose, owner, and removal path are recorded in
`docs/phase-2/PROVIDER_DEPENDENCY.md`.
Prompt/output/process retention and redaction are specified in
`docs/phase-2/RETENTION_POLICY.md`.

## Migration and recovery evidence

The recorded workspace applied migrations `0001` and `0002`, reports
`foreign_keys=1`, and runs in `wal` mode. Tests cover fresh migration, restart,
checksum drift rejection, transaction rollback, and foreign-key enforcement.

The crash demonstration injected failure after creating the proposer CAS blob
but before the database semantic commit. Before recovery there were zero
proposals. After lease expiry, database restart, and replay, the workflow
finished `awaiting_review` with exactly one proposer proposal and one verifier
finding, and exactly two proposal-import events—no duplicate semantic result.

The pause demonstration persisted `paused`, observed the same state after
database restart, resumed to `running`, and finished `awaiting_review`.

## Model-context isolation evidence

The fake run made two distinct calls to `scripted-v1`. Its independence record
correctly says:

- `context_isolated=true`;
- `separate_model_call=true`;
- `different_model=false`;
- `different_provider=false`;
- `deterministic_checker=false`;
- `independently_implemented_checker=false`;
- `formal_kernel=false`;
- derived full independence is false.

Verifier-context and context-artifact hash are both
`sha256:62b67e9db2fb06b8655dc8334a7552c8453f86978eb92b2d16aeea53aae5a46a`.
Tests compare this hash to the exact serialized bytes and check that proposer
rationale, self-ratings, summaries, and unrelated history are absent. The
accepted dossier remains `unknown` with its open obligation; neither call adds
evidence, a verification record, or a warrant.

## External-backend demonstrations

The malicious traversal package exited zero but was rejected with blocker
`artifact path traversal rejected` and imported no proposal. The valid fixture
package was hash/schema checked and imported one `proposal` only. Process
stdout, stderr, environment, package, and output hashes are retained in the CAS
and run directory; the current adapter contract test also proves that the same
evidence is appended to the durable event timeline.

## Initial live-provider preflight history

Historical status: **blocked**. At that time the missing configuration was:

- `ADAIVY_MODEL_PROVIDER`;
- `ADAIVY_OPENAI_MODEL`;
- `OPENAI_API_KEY`;
- `ADAIVY_OPENAI_INPUT_MICROUSD_PER_MILLION`;
- `ADAIVY_OPENAI_OUTPUT_MICROUSD_PER_MILLION`.

Calls recorded: `0`. Cost: `null` (not fabricated). The deterministic fake run
recorded two calls, 280 input tokens, 170 output tokens, and zero micro-USD by
fixture definition. Current official structured-output subset, refusal/status,
and usage behavior were checked against
[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

This is not the current gate result. The later v1 and v2 failures and successful
v3 result are summarized below.

## Successful live-provider acceptance

Status: **passed**. The manually initiated v3 run used the known-valid even-sum
fixture, pinned `openai==3.3.0` adapter dependency, explicit
`gpt-5-mini` configuration, and pricing snapshot
`pricing.openai.gpt5-mini.2026-08-19.v1`. The provider reported model snapshot
`gpt-5-mini-2025-08-07` for both calls.

- Proposer response ID:
  `resp_07822df2a3cc157a016a85705b263c87d082e6f2679308368d`
- Verifier response ID:
  `resp_0124dadfd2b93e8c016a8570668f9487d0b7c38ed0bb2b302a`
- Proposer usage: 955 input, 844 output, 1,799 total tokens; estimated
  1,927 micro-USD.
- Verifier usage: 1,412 input, 980 output, 2,392 total tokens; estimated
  2,313 micro-USD.
- Combined usage: 2,367 input, 1,824 output, 4,191 total tokens; estimated
  4,240 micro-USD (`$0.004240`) from the pinned snapshot.
- Verifier-context manifest hash:
  `sha256:e625dcfdbe8ddab1f266ebb74935e0311ba2f1f3a11acf55920277c5b9e0bdd0`
- Event replay hash:
  `sha256:d5bb8e34704404aa3f69e44f4f19c32787a747fd5a2d70ab323028e998fcd24c`
- Restart-regenerated report hash:
  `sha256:ff706139a8f0415e1f1f6efc0ac714f0e588f187e94e82c7dff0af92d5da8cb9`
- Credential-leak matches: zero.

Both structured outputs passed canonical and trust-policy validation. The
proposer result and verifier finding remain two `proposal` records only. The
run stopped at `awaiting_review`; the accepted dossier remains unknown with its
open obligation. The same-model verifier is correctly labeled
`context_isolated=true`, `separate_model_call=true`, `different_model=false`,
`different_provider=false`, and not fully independent.

## Replay hashes

- Accepted Phase 2 dossier content:
  `sha256:7c4a99e1b129b0bb4192094778a87cdd9c945a5d87cf0f7f6c00f6f9509408f7`
- Main run event replay:
  `sha256:8c185deeb88a6e981bfd5376c868d62163a748f686bf04e5004b89c5d68bea9c`
- Regenerated traceable report:
  `sha256:adef3d2d42999f24a877cf512f015c09316a719a163b9899faeb717b69a28b55`
- Report regeneration is byte-identical across database reopen.
- Six request/result/proposal artifact hashes are enumerated in
  `reports/phase-2/demonstration.json` and verified by the report-consistency
  test.

## Requirement evidence

The complete requirement-to-test mapping is in
`docs/phase-2/REQUIREMENT_TEST_MATRIX.md`. Durable demonstration evidence is in
`reports/phase-2/demonstration.json`; the live acceptance is independently recorded
in `reports/phase-2/live-provider-status.json`.

## Unresolved risks and decisions

- SQLite is intentionally local/single-host. PostgreSQL remains unjustified
  until distributed workload or contention is measured.
- The process adapter is a strict interchange boundary, not an OS sandbox.
- The successful live record is one bounded provider/model sample, not evidence
  of availability or behavior across models, providers, or future API versions.
- Human proposal promotion is intentionally absent; a future review command
  must preserve Phase 1 warrant rules.
- CAS orphan collection, backups, encryption, and migration rollback policy are
  deferred.

The complete stop-line list is `docs/phase-2/DEFERRED_WORK.md`.

## Provider-boundary repairs after failed live attempts

The v1 and v2 one-call attempts failed with HTTP 400 and remain immutable under
their respective workspaces and `reports/phase-2/live-provider-status.json`.
The v2 request ID is `req_32c9c66a4fb1414292df36cb4c031aad`; its safe
diagnostic identified a missing explicit provider type on a scalar const node.
The v1 and v2 acceptance results remain **failed**. The repair itself made no
live request; the operator subsequently ran the distinct v3 workspace and gate,
which passed without rewriting either failed workspace.

The OpenAI boundary now uses a deterministic provider-only strict-schema
projection, recursive local linter, and canonical post-response validation.
`uniqueItems`, `minLength`, and `maxLength` are omitted only from the provider
projection and remain enforced locally. Unknown keywords, unsupported
composition, root `anyOf`, and documented size/depth violations stop before
budget reservation and network construction. The projected schema is not a
canonical trust schema and cannot weaken proposal-only import or trust policy.

The adapter now uses the pinned optional OpenAI SDK and its supported
`APIStatusError` interfaces. HTTP failures retain safe structured diagnostics,
a 4096-byte sanitized preview, and the full response-body hash/length without
retaining credentials, cookies, arbitrary headers, or unredacted bodies. SDK
retries are disabled. Compatibility evidence is under
`reports/phase-2/provider-compatibility/`; ADR-0010 defines the boundary and
ADR-0011 defines terminal type inference.

Projection version `openai-strict-schema-projection/1.1.0` infers provider-only
types for six scalar const/enum nodes and records each addition in the manifest.
Integer-only values infer `integer`; finite numeric values infer `number`; a
mixed integer/finite-number enum also infers `number` while its enum preserves
exact membership. Empty, ambiguous, null-only, non-finite, object, array, and
explicitly conflicting terminals fail closed before budget reservation. The
v3 configuration is now part of the immutable successful acceptance record.

After the terminal-typing repair, all 101 Phase 0–2 tests and all 19 Phase 0
component checks pass. The main Phase 2 traceable report regenerates with its
unchanged hash.

## Phase 3 readiness recommendation

Phase 2 is accepted and technically ready for a separately authorized Phase 3
plan. Stop here: no Phase 3 work is included in this acceptance update. Before
Phase 3 begins, re-read the architecture stop lines, define its bounded
acceptance tests, and preserve the Phase 1 trust semantics and v1–v3 histories.
