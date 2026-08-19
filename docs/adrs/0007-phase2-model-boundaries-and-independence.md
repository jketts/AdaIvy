# ADR-0007: Proposal-only model loop and additive verifier independence

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** revision 0.2 trust invariants, model gateway, verifier context, Phase 2
- **Decision owners:** repository maintainers

## Context

Phase 2 adds a proposer and verifier call without changing the Phase 1 rule
that agreement is not proof. Phase 1 also has one historical
`independent_from_proposer` boolean, while Phase 2 requires seven explicit
dimensions. A provider adapter must be available without making credentials,
network access, an SDK, or current pricing part of the offline path.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt provider SDK and mutable trust state | Common application pattern | Less HTTP parsing | Couples domain and provider; risks self-awarded status | Violates trust/dependency rules |
| Wrap provider behind `ModelGateway` | Blueprint port and adapter boundary | Testable deterministic contract | Adapter must validate changing API responses | Proposal-only import and contract tests |
| Interoperate through generic OpenAI Responses HTTP | Official structured-output/refusal/usage contract | No added dependency; opt-in | Narrow provider feature set | Explicit config, timeout, redaction |
| Build multi-provider routing or agents | Future architecture | More options | Phase 3+ scope | Rejected for Phase 2 |

## Decision

Add a provider-neutral value-object port. The deterministic scripted adapter is
the acceptance reference. Add one opt-in OpenAI Responses adapter using
environment configuration and strict structured-output validation. Record
provider/model/capabilities, prompts, structured outputs, concise declared
rationales, usage, configured integer cost rates, and referenced entity IDs.
Do not request, require, or retain hidden chain-of-thought.

Every provider/backend result enters a dedicated proposal repository. A model
never receives repositories or transition methods and cannot create an accepted
`EpistemicWarrant`. The baseline verifier can produce only a finding and manual
review recommendation. The existing dossier stays unchanged during the loop.

Preserve the Phase 1 `VerificationRecord` and its boolean. Add a Phase 2 frozen
`VerifierIndependence` record with exactly these dimensions:
`context_isolated`, `separate_model_call`, `different_model`,
`different_provider`, `deterministic_checker`,
`independently_implemented_checker`, and `formal_kernel`. A same-provider,
same-model fresh call may set only the first two; full independence is a derived
conjunction, never a marketing label.

## Consequences

Offline tests are deterministic and do not require secrets. Live acceptance is
separately recorded and remains blocked when credentials are absent. Pricing is
never inferred: cost is normalized only from configured per-token rates.
Provider refusal, malformed output, timeout, cancellation, and late success are
explicit non-success paths with no domain mutation.

## Blueprint deviation

The single additive independence record resolves a schema gap without changing
Phase 1 meaning. The standard-library HTTP adapter is narrower than a full SDK
integration, but it implements the required Phase 2 port and keeps provider
concerns outward. Revisit if the API contract cannot be validated without an
SDK or when a second provider becomes a measured requirement.

## Validation and revisit trigger

The model-boundary, isolation-manifest, secret-redaction, refusal, malformed
output, idempotency, budget, cancellation, and all Phase 1 adversarial tests
must pass. Promotion of a finding, a new warrant path, or reinterpretation of
the old independence boolean requires a new ADR and trust-policy review.
