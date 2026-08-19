# ADR-0008: Pin live-run pricing as versioned non-secret data

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** Phase 2 model gateway, normalized usage/cost, reproducible run configuration
- **Decision owners:** repository maintainers

Credential loading in this ADR is superseded by ADR-0009. The pinned-pricing
decision remains active.

## Context

The first Phase 2 adapter loaded provider, model identifier, credential, and
two cost rates from environment variables. That made credentials appropriately
ephemeral, but made a historical cost estimate impossible to replay or audit:
the rates had no source, timestamp, currency, units, version, model binding, or
content hash. The live-provider acceptance gate requires those facts and must
not fetch or update pricing during a research run.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Keep all values in environment variables | Existing adapter | Smallest code path | Pricing is not durable or replayable | Fails live acceptance |
| Fetch current provider pricing at run time | Provider web data | Convenient | Non-deterministic and network-dependent; silent price changes | Prohibited during a run |
| Pin a versioned pricing snapshot | New schemas, migration, and tests | Reproducible, auditable, non-secret | Operator must explicitly create a snapshot | Selected |
| Hard-code a model and rates | None | Simple | Blueprint forbids silent model selection; rates age invisibly | Rejected |

## Decision

Keep only `OPENAI_API_KEY` in the environment. Put `provider` and
`model_identifier` in an explicit, content-hashed live-run configuration. Put
rates in an explicitly created, content-hashed pricing snapshot that records
snapshot ID, provider, model identifier, source, capture timestamp, currency,
units, and integer micro-USD rates per million input/output tokens.

Every persisted cost estimate references the snapshot ID. API-reported input,
output, and total tokens are stored separately from estimated monetary cost.
The run configuration, snapshot, per-call reservation estimates, actual-usage
cost estimates, provider response IDs, and incomplete-response reason are
persisted through migration `0003`. No research run fetches pricing.

## Consequences

- Live setup now requires two non-secret JSON files in addition to the
  environment-only credential.
- Cost is explicitly an estimate derived from API-reported usage and the pinned
  snapshot; it is not represented as provider-billed or settled cost.
- The original `model_calls.cost_microusd` column remains as a compatibility
  mirror for older databases. New code and reports use
  `estimated_cost_microusd` plus `pricing_snapshot_id`.
- Snapshot/model mismatch and budgets that cannot cover two bounded calls fail
  preflight before any live call or acceptance-status mutation.

## Blueprint deviation

None. This replaces an incomplete Phase 2 configuration detail with the
blueprint's required reproducible, provider-neutral accounting boundary. It
does not change Phase 1 entities or trust semantics.

## Validation and revisit trigger

Unit tests cover snapshot/config hash validation, model binding, two-call
budget preflight, redaction, response-level incompleteness, durable estimates,
and restart replay. Revisit only if a provider supplies authoritative billed
cost per response; retain that as a separate actual-cost field rather than
overwriting the pinned estimate.
