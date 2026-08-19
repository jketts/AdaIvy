# Proposed Phase 3A Cost and Storage Budget

Status: design estimate only  
Date: 2026-08-19

## Acceptance baseline

The required Phase 3A acceptance path uses manual files, local SQLite FTS5, the
local CAS, and scripted model fixtures. Required model/API cost is therefore
exactly `$0.00`. No crawler, embedding provider, remote parser, or live model is
needed.

Local monetary storage cost is `$0.00` incremental on the existing workstation;
capacity is still bounded:

| Class | Proposed hard cap |
|---|---:|
| Individual source artifact | 25 MiB |
| Complete four-source gold corpus | 100 MiB |
| Normalized text, maps, markers, and evidence units | 200 MiB |
| FTS/index projections | 200 MiB |
| Pack, parser, log, and replay artifacts | 100 MiB |
| Total Phase 3A acceptance workspace | 600 MiB |

The implementation must measure actual bytes by class and stop before exceeding
the configured cap. Derived/index growth beyond 4x source bytes is a review
signal even if the absolute cap remains.

No cloud/object-storage price is estimated because no provider, region,
retention class, or egress policy is selected. Any later cloud estimate requires
a versioned non-secret pricing snapshot analogous to ADR-0008.

## Optional model exercise

An optional, separately authorized proposer/verifier exercise may reuse the
existing pinned snapshot
`pricing.openai.gpt5-mini.2026-08-19.v1` only while its configured model matches.
At the existing reservation of 10,000 input and 2,048 output tokens per call,
two calls reserve:

- 20,000 input tokens at 250,000 micro-USD per million: 5,000 micro-USD;
- 4,096 output tokens at 2,000,000 micro-USD per million: 8,192 micro-USD;
- total estimate: 13,192 micro-USD (`$0.013192`).

This is a pinned-snapshot estimate, not a bill. API-reported usage and estimated
cost remain separate, billed cost remains unknown unless independently supplied,
and no price may be fetched during a run. Larger evidence packs require a new
explicit run configuration and budget rather than silent expansion.

Embeddings have no approved provider, model, dimensions, price, or acceptance
role. Their budget is therefore `not approved`, not zero-cost.
