# ADR-0030: Multi-provider model gateways behind the existing Phase 2 boundary

- **Status:** accepted for bounded multi-provider adapter implementation
- **Date:** 2026-08-20
- **Blueprint requirement:** Phase 2 opt-in provider credentials, secret
  redaction, and versioned non-secret run configuration
- **Decision owners:** repository owner and operator

## Context

Phase 2 reaches exactly one external model provider. `OpenAIResponsesGateway`
implements the `ModelGateway` port, loads its SDK lazily through `importlib` so
the offline suite never needs it installed, classifies provider failures as
retryable or fatal, and records a content-hashed pricing snapshot per run.
ADR-0009 permits a single credential, `OPENAI_API_KEY`, from a mode-0600
repository-root `.env` that is never allowed to override the process
environment.

The owner asked for coverage of models hosted on Azure, AWS Bedrock, MiniMax,
Qwen on AliCloud, Anthropic, and DeepSeek, with credentials in the local env
file. Three facts constrain how:

- MiniMax, DashScope (Qwen), and DeepSeek all expose OpenAI-compatible chat
  endpoints, so one parameterised adapter can serve them. Azure authenticates
  differently -- an `api-key` header against a deployment-scoped URL with a
  required `api-version` -- and is therefore only partly compatible.
- Bedrock is requested for arbitrary model families, not only Claude. Request
  and response bodies differ per vendor, and the endpoint requires AWS
  Signature Version 4.
- ADR-0009's loader rejects any key other than `OPENAI_API_KEY` and rejects a
  blank value. A multi-provider template copied whole would fail on its first
  unconfigured line, so the credential surface had to change before any adapter
  could read a key.

The runtime is standard-library only (`dependencies = []` is deliberate) and
network access is off by default. Adding six providers must not weaken either.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt one SDK per provider | Existing pinned `openai==3.3.0` boundary works | Native feature coverage and error taxonomy per provider | Six heavy optional dependencies; six code paths to audit | Rejected as default; retained only where genuinely needed |
| Wrap: one OpenAI-compatible adapter plus native adapters where required | Three providers publish compatible endpoints | Far less code and fewer places for a bug; native fidelity kept where compatibility is absent | Compatibility layers drift on structured output, token accounting, and error codes | Selected, with per-provider acceptance tests |
| Interoperate via a single generic HTTP client | Phase 4B `live_transport` shows careful stdlib HTTP is feasible | No dependencies at all | Would re-implement auth, signing, retries, and schema mapping for six providers | Rejected as unnecessary risk |
| Defer | None | No new surface | Leaves the owner's requirement unmet | Rejected |

## Decision

Providers are added as additional `ModelGateway` implementations behind the
existing Phase 2 boundary. Nothing about the trust model changes: a model result
remains a proposal, and no provider response acquires a warrant by being
returned.

- A single parameterised OpenAI-compatible adapter serves MiniMax, Qwen
  (DashScope), and DeepSeek. Azure OpenAI uses the same adapter family but keeps
  its own auth and URL construction rather than being treated as identical.
- Anthropic uses its official SDK, lazily imported, against the Messages API.
- Bedrock maps `ModelRequest` per model family, keyed by model-id prefix. An
  unrecognised family fails closed with an explicit unsupported-family error; a
  request body is never guessed.
- Every provider carries a content-hashed pricing snapshot. Rates recorded
  before confirmation are marked as unconfirmed placeholders and must be
  verified before live use. Bedrock is partner-operated and priced separately
  from first-party rates.
- Provider SDKs stay optional, pinned by version and wheel digest in the
  provider requirements file, and are never installed for offline checks.
- Credentials: `load_repository_env` keeps ADR-0009's accepted semantics
  unchanged, including returning before the file is parsed when the process
  environment already supplies the credential. A new
  `load_provider_credentials` resolves the full provider key set with every one
  of ADR-0009's controls retained -- mode 0600, regular non-symlink file, no
  interpolation or substitution, unknown-key and duplicate rejection, unmatched
  quotes rejected, no value disclosed in the result -- and one deliberate
  change: a blank entry is reported as unconfigured rather than raising, so a
  copied template works and a blank line can never mask a real process-
  environment value. Provider, model, pricing, and budgets remain versioned
  non-secret JSON and must not move into `.env`.

## Consequences

- Operational: six providers become reachable; none is enabled by default. Live
  calls remain behind the existing live-gate acknowledgement.
- Security: the credential surface grows from one key to fourteen entries, of
  which five are non-secret operational settings. Every secret passes through
  `redact_secrets` before reaching a diagnostic or record. Bedrock adds signing
  material that must never be logged. `.env` and `.env.*` stay ignored while
  `.env.example` stays versioned and blank, and a test asserts the example and
  the loader allowlist agree exactly.
- Licensing: each optional SDK adds its own licence to assess before it is
  pinned.
- Reproducibility: live model calls are not deterministic and are excluded from
  canonical replay, exactly as the existing provider boundary already is. The
  offline suite stays hermetic -- no network, no credentials, no sockets -- and
  gains no environment-gated skip.
- Negative: OpenAI-compatibility layers can diverge from the interface they
  imitate, and a divergence may present as a plausible wrong result rather than
  an error. Bedrock's per-family mapping covers only the families implemented,
  and hand-rolled SigV4, if used, is subtle enough that unverified signing is
  worse than a dependency.
- Retrieval: admitting several providers creates a constraint that this ADR does
  not itself resolve. Per `TECHNICAL_BLUEPRINT.md` Section 12.2.1 and the
  multi-provider section of `docs/phase-4c/HYBRID_RETRIEVAL_BENCHMARK_V1.md`,
  embedding vectors must be partitioned by `(provider, model_identifier,
  dimension, normalization)` and compared only within a partition. Two
  same-dimension models from different vendors produce a corrupted similarity
  space that still returns a full, plausibly ordered result set, so no recall or
  precision gate detects it. Current retrieval is lexical only and therefore
  unaffected; any future embedding use must carry its own Phase 4A `embedding`
  rights decision naming the processor, and a second provider is a distinct
  disclosure requiring its own decision.

## Blueprint deviation

None. The blueprint already contemplates an opt-in external provider boundary;
this widens the set of providers behind it without moving the boundary or
granting a model output any additional trust.

## Validation and revisit trigger

Every provider needs hermetic acceptance tests covering auth construction,
success mapping, refusal and incomplete mapping, retryable-versus-fatal
classification, malformed-output rejection, and proof that no credential reaches
a diagnostic. `make check` must stay green with no new skips. Hand-rolled SigV4
must validate against AWS's published test vectors; failing that, a pinned SDK
is required instead. Revisit if a compatibility layer produces a wrong result
that the acceptance tests do not catch, if a provider's pricing or error
taxonomy changes materially, or if the number of optional SDKs makes the
dependency surface harder to audit than the code it replaces.
