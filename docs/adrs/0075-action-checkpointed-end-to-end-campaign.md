# ADR-0075: Action-checkpointed End-to-End Campaign

- Status: Accepted and implemented for the offline fixture runtime
- Date: 2026-08-22
- Extends: ADR-0071 and ADR-0072

## Decision

The central campaign gains first-class search, result-following, acquisition,
parsing, embedding, index-refresh, retrieval, experiment, verification, formal
check, and report actions. A recorded literature search must precede
substantive research; result following is bounded to depth one and an explicit
allowlist. This implements ADR-0072's replacement for the per-run
`before_research` human checkpoint. The `before_announcement` checkpoint is
unchanged.

Every action writes an immutable intent carrying an idempotency key before an
effect, then an immutable terminal. Resume replays completed terminals without
repeating effects. An intent without a terminal is reported as ambiguous and
unresolved; paid or irreversible work is never guessed or repeated.

`campaign start` initializes and executes the complete offline fixture path;
`campaign resume` detects that runtime and performs action-level continuation.
The fixture uses a named profile, one persistent multi-capability budget, the
persistent corpus/retrieval projection, a bounded fixture experiment, exact
artifact verification, and a claim-free report. Live model, network, OCI, and
Lean effects remain behind their existing explicit gates.

## Consequences

- Terminal-finalization resume remains supported for legacy campaigns.
- Ambiguous paid effects stop durably instead of risking a duplicate call.
- Fixture completion demonstrates orchestration, not novelty, significance,
  source applicability, or mathematical truth.
