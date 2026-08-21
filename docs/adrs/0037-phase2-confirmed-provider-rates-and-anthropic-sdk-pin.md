# ADR-0037: Confirmed Phase 2 provider rates and a pinned Anthropic SDK

- **Status:** accepted
- **Date:** 2026-08-21
- **Blueprint requirement:** Phase 2 opt-in provider credentials, pinned pricing
  snapshots, and versioned non-secret run configuration
- **Decision owners:** repository owner and operator

Numbering note: 0033 through 0035 are taken, and 0036 is claimed by the
concurrent slice that made pricing confirmation a fail-closed live-gate check
(`pricing_snapshot_unconfirmed:<id>`). This ADR is the other half of that work
and depends on nothing in it.

## Context

ADR-0030 admitted seven providers behind the Phase 2 `ModelGateway` boundary and
left two of its own obligations open. Both were fail-closed markers, so the
practical effect was that only OpenAI could complete a live call.

- `ANTHROPIC_SDK_PINNED_VERSION` was the literal string `UNCONFIRMED`. The
  preflight reads that sentinel and appends
  `anthropic_sdk_version_unconfirmed`, so every Anthropic run was refused, and
  `requirements-phase2-provider.txt` pinned only `openai==3.3.0`.
- Five pricing snapshots carried `UNCONFIRMED PLACEHOLDER` sources with rates set
  to 1e9 or 5e6/2e7 micro-USD per million tokens, chosen to exceed any real
  price so a budget refuses the call.

Two of the configured model identifiers no longer exist. `deepseek-chat` is
absent from DeepSeek's current model table, which lists `deepseek-v4-flash` and
`deepseek-v4-pro`; `MiniMax-Text-01` is absent from MiniMax's pay-as-you-go
tables including their Legacy Models section. A rate cannot be captured for a
model no vendor publishes, so confirming these two snapshots necessarily meant
choosing a current model.

Every vendor prices along dimensions this adapter does not pin. DeepSeek charges
peak and off-peak rates and separates cache hits from misses. MiniMax quotes a
list price under a standing 50% promotion, plus a 1.5x priority tier. Qwen
charges a different output rate in thinking mode. Azure charges more for a Data
Zone deployment than a Global one, and more again for priority processing. The
adapter selects none of these, so any single recorded rate is a choice about
which end of the range to record.

Bedrock resisted capture for recorded reasons. The AWS Price List API offer for
`AmazonBedrock` in `us-east-1` (version 20260820130114) contains no Claude Opus 5
product at all; only Claude 2.x, Claude 3 Sonnet/Haiku and Claude Instant appear.
The pricing page's Anthropic table resolves its rates from a client-side region
selector, and `schemas/pricing-snapshot-v1.schema.json` has no region field, so
there is nowhere to record which region a captured rate belongs to.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt the vendors' headline rates as quoted | Each vendor publishes one prominent number | Shortest path; matches marketing copy | The headline is the cheapest cell of a multi-dimensional table (off-peak, cached, discounted, non-thinking, Global); a budget computed from it under-estimates what a call really costs | Rejected: under-recording a rate is the one error a cost budget cannot survive |
| Record the maximum rate over every dimension the adapter does not pin | Adapter sends no `service_tier`, pins no thinking mode, chooses no hour, and cannot know an operator's Azure deployment scope | A budget can never admit a call it cannot pay for; the choice is stated in each snapshot's `source` | Over-estimates a cheap call, so a budget may refuse a run that would in fact have been affordable | Selected; each snapshot's `source` names every rate in the table, not only the one recorded |
| Keep the placeholders and confirm rates at run time | No new capture needed | No stale rate | Requires network access inside the gate, which the boundary forbids, and makes the run non-reproducible | Rejected |
| Defer, keeping all five placeholders | None | No new surface | Leaves six of seven providers uncallable, which is ADR-0030's requirement unmet | Rejected except for Bedrock, where capture actually failed |

## Decision

Rates are recorded as the highest published on-demand rate a call could incur
under the shipped configuration. The rule is uniform: take the maximum over
every dimension the adapter does not itself pin, and record in `source` both the
recorded figure and the alternatives it was chosen over.

| Provider | Model | Input | Output | Recorded end of the range |
|---|---|---|---|---|
| `deepseek` | `deepseek-v4-flash` | 440000 | 1320000 | peak hours, cache miss |
| `minimax` | `MiniMax-M3` | 600000 | 2400000 | undiscounted list, standard tier |
| `qwen_dashscope` | `qwen-plus` | 400000 | 4000000 | thinking-mode output |
| `azure_openai` | `gpt-5.6-sol` | 11000000 | 49500000 | Data Zone, long-context, standard tier |

Rates are micro-USD per million tokens. Model identifiers move with the rate:
`deepseek-chat` becomes `deepseek-v4-flash` and `MiniMax-Text-01` becomes
`MiniMax-M3`, each the current documented model whose published rate is the one
recorded. The MiniMax and Qwen budgets rise from 20000 to 30000 micro-USD,
because a real rate above the previous placeholder's would otherwise fail the
gate's two-call affordability check.

The Azure entry moved for a different reason. It was first captured against
`gpt-5-mini` at 275000/2200000, because that is what the shipped configuration
named. The only reachable deployment on the operator's resource
(`AZURE_OPENAI_DEPLOYMENT=gpt-5.6-sol`) serves a model priced roughly twentyfold
higher, and on Azure the deployment in the URL selects the model while the body's
`model` field does not. A configuration naming `gpt-5-mini` against that
deployment would have estimated a real call at about 1/17th of its cost -- a
plausible wrong number, not an error, which is precisely the failure mode
ADR-0030 warned compatibility layers would produce. The configuration and its
snapshot now name `gpt-5.6-sol`, and its budget rises from 20000 to 500000
micro-USD to cover two calls at that rate. The context-tier choice is the
conservative one under this ADR's rule: Azure's price list does not state where
the ShortCo/LongCo boundary falls, so a 20000-token input cannot be shown to
stay inside the cheaper tier.

Bedrock stays an explicit `UNCONFIRMED PLACEHOLDER` at 1e9 micro-USD per million
tokens in both directions. Its `source` now records both failed capture routes
by name and version, so the next attempt starts from what was already tried
rather than repeating it. This is the mechanism working as intended, not a gap:
the marker is exactly what the concurrent ADR-0036 check consumes to refuse the
run.

The Anthropic SDK is pinned at `anthropic==1.0.0`, MIT licensed, wheel SHA-256
`32dd52e9e1d774393b27182f451398ba4262287a4d0eab30887f89f1481b3ae4`. Version
1.0.0 is a breaking release; its migration surface was checked against this
adapter and does not reach it. The adapter passes plain values to the client
(`timeout`, `max_retries=0`) rather than `httpx` objects, already sends
`output_config={"format": ...}` rather than the removed `output_format`, and
passes none of the removed sampling parameters.

## Consequences

- Operational: five of seven providers can now pass the pricing and SDK parts of
  the preflight. Bedrock still refuses on its unconfirmed rate. Nothing is
  enabled by default and live calls remain behind the live-gate acknowledgement.
- Security: `anthropic` 1.0.0 has no PyPI publish attestation, so its provenance
  rests on the recorded wheel digest alone. That is weaker than the attested
  `openai` pin and is recorded as such in `docs/phase-2/PROVIDER_DEPENDENCY.md`
  rather than presented as equivalent.
- Licensing: MIT, compatible and recorded.
- Reproducibility: the rate table is asserted exactly in
  `tests/test_phase2_openai_compatible_gateway.py`, so a rate cannot drift
  without a deliberate edit. Snapshots stay byte-canonical and content-hashed;
  they were written through `create_pricing_snapshot` rather than by hand.
- Negative, and the reason this ADR exists rather than a config commit: a
  recorded rate is a **capture, not a fact**. Four of these numbers were read
  from vendor documentation that changes without notice, and the fifth
  (`azure_openai`) came from the Azure retail price API. A rate that has since
  moved will still be pinned, hashed, and asserted, and nothing offline can
  detect it. The confirmed marker means "an operator captured this on
  2026-08-21", never "this is what the call will cost".
- Negative: the conservative rule means these budgets are pessimistic. A run
  refused as unaffordable may have been affordable at off-peak, cached,
  discounted, or Global rates.
- Negative: repointing two model identifiers changes which model a live run
  actually calls. The old identifiers were unpriceable, but this is a behaviour
  change, not a bookkeeping one.

## Blueprint deviation

None. Pinned pricing snapshots and an opt-in provider boundary are what the
blueprint already requires; this fills in values it left to the operator.

## Validation and revisit trigger

`make check` stays green with no new skips. The acceptance assertions are:

- The exact rate table and model identifiers, per provider, with a positive
  assertion that no confirmed snapshot's `source` carries `UNCONFIRMED` and that
  each cites an https source and its capture date.
- Each configuration's budget covers two calls at its own pinned rate, so a
  re-capture that raises a rate without raising the budget fails at the rate
  rather than as an opaque `budget_cost_below_two_calls` at gate time.
- The registry's pinned SDK version equals the version in
  `requirements-phase2-provider.txt`, and every requirement line carries a
  64-hex wheel digest. A pin nothing installs would fail every run for a reason
  nothing explains.
- The unconfirmed-pin rule is proved against a substituted spec rather than off
  the shipped registry, with a second test asserting the shipped Anthropic spec
  is no longer reported as unpinned. Without that pair, a silent revert of the
  pin would keep both tests passing.

Revisit when a vendor changes a rate or retires a recorded model, when Bedrock
becomes capturable (either the Price List API publishes the model or the schema
gains a region field), when a pin moves and the upstream migration notes need
re-checking, or if a captured rate is found to have been wrong at capture time --
which would argue for recording a capture expiry rather than a bare timestamp.
