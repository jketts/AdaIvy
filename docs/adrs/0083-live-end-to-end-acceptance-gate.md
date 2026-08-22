# ADR-0083: Live end-to-end acceptance gate

- **Status:** accepted; gate definition implemented; live execution pending
- **Date:** 2026-08-22
- **Plan slice:** `docs/CAMPAIGN_DEPTH_AND_BREADTH_PLAN.md` Slice 16
- **Decision owners:** repository owner

## Decision

The live end-to-end gate is a separately sealed configuration, checked by
`campaign live-acceptance` and the offline
`make check-campaign-live-definition` target. It binds the Azure OpenAI route,
v2 action schema, modest exact-graph target class, unified capability budgets,
the mandatory `before_announcement` checkpoint, and the complete set of
provider, discovery, snapshot, embedding, workspace-sandbox, and verifier
activation evidence.

The shipped gate remains `pending_operator_activation`. `--execute` does not
make a network call while that status remains pending, while the exact
acknowledgement is absent, or while any required evidence is missing or fails
canonical hash/status validation. Readiness output always reports zero calls;
it is a preflight record, never evidence that the live campaign ran.

Azure throttling and transient connection failures use the gate's bounded
policy: retry only HTTP 408, 409, 429, 500, 502, 503, and 504; deterministic
exponential delays begin at 2 seconds, cap at 60 seconds, and stop after four
retries. The provider SDK remains configured with implicit retries disabled,
so a future executor must ledger each retry explicitly rather than hiding paid
attempts. Authentication and configuration failures are never retryable.

The campaign-specific live model configuration permits 16 total calls
(including activation), 16,384 reserved input tokens and 8,192 reserved output
tokens per call, and an $8 maximum recorded cost. It does not alter the smaller
Phase 2 demonstration configurations.

## Milestones and current truth

1. **Definition:** implemented and offline-tested. The gate, command,
   configuration, bounded backoff policy, and documentation ship fail-closed.
2. **Execution:** pending. No provider, discovery, acquisition, embedding,
   container, Lean, or publication authorization was fabricated in order to
   close this ADR. A real run becomes valid evidence only after an operator
   changes the sealed status through the repository's activation process,
   supplies all named evidence, uses the exact acknowledgement, and records
   the resulting campaign artifacts and costs. Human publication approval
remains separate and mandatory.
