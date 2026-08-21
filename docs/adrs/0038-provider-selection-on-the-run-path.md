# ADR-0038: Provider selection on the Phase 2 run path

- **Status:** accepted for the bounded provider-selection slice; implemented
  21 August 2026. Six of seven providers have **no** live evidence and are
  recorded as untested, not as passing -- see "Measured outcome".
- **Date:** 2026-08-21
- **Blueprint requirement:** Phase 2 opt-in provider credentials, secret
  redaction, pinned pricing snapshots, and versioned non-secret run
  configuration
- **Decision owners:** repository owner and operator

Numbering note: `0036` is taken by the concurrent publication-projection slice
and `0037` by the concurrent confirmed-rates slice, both authored the same
afternoon. ADR-0037's forward reference to "the concurrent ADR-0036 that made
pricing confirmation a fail-closed live-gate check" refers to **this** ADR; the
number moved, the content did not.

## Context

ADR-0030 admitted seven providers at the Phase 2 model boundary. All seven have
working `ModelGateway` adapters, a shipped `config/phase2-live-*.json` run
configuration, and a shipped `config/*pricing*.json` snapshot. `live-preflight`
and `live-gate` are provider-aware and derive every check from
`provider_registry`.

The run commands were not. Five measured defects, all on the path an operator
actually uses to run a research problem:

1. **`--provider` was restricted to a literal `("fake", "openai")`** on `start`
   and `advance` (`src/math_research/phase2_cli.py:154` before this change).
   Six providers were selectable for `pricing-create`, `live-config-create`,
   `live-preflight`, and `live-gate`, and unselectable for a run.

2. **Widening that list alone would have routed all six to OpenAI's adapter.**
   `_loop` built `OpenAIResponsesGateway(OpenAIProviderConfig(...))` for *any*
   non-fake provider. This is the exact regression class that
   `tests/test_phase2_provider_registry.py::test_each_provider_routes_to_its_own_adapter_not_a_default`
   pins for `execute_live_gate`; the CLI run path still had it, latent only
   because the choice list made it unreachable.

3. **A populated multi-provider `.env` broke every live command.** `_live_inputs`
   called `load_repository_env`, whose ADR-0009 allowlist is exactly
   `{OPENAI_API_KEY}` and which rejects a blank value. Measured against a
   `.env` copied from `.env.example` -- which is what that file's own
   instructions say to do -- with one Anthropic key filled in:
   `EnvFileError: empty .env value on line 12: OPENAI_API_KEY`. The loader fails
   on the blank OpenAI line before it even reaches the unsupported one. Every
   live command, including `live-preflight` and `live-gate`, therefore reported a
   failed check the moment the owner put a key in `.env`. `.env.example` already
   listed all fourteen entries and `load_provider_credentials` already handled
   them; the CLI called the wrong loader.

4. **`_live_inputs` demanded `OPENAI_API_KEY` for every provider.** The precise
   bug ADR-0030 removed from the preflight was still in the CLI: a Bedrock run
   was told to configure an OpenAI credential.

5. **The credential leak scan could not run for six providers.**
   `execute_live_gate` ended with `api_key = os.environ["OPENAI_API_KEY"]`. For
   any other provider that raises `KeyError` *after* both live calls have
   completed and been paid for, turning a passing gate into a `failed` status and
   skipping the leak scan entirely. Bedrock's secret access key and session
   token were never scanned for under any provider.

One further measured gap, adjacent and consumed here: **nothing read the
UNCONFIRMED pricing marker.** ADR-0030 recorded placeholder rates as an
`UNCONFIRMED PLACEHOLDER` string inside the non-secret `source` field.
`load_pricing_snapshot` validates the schema and the content hash and treats that
string as ordinary text, so a placeholder passed the preflight exactly like a
quoted rate and a cost budget was enforced against a number nobody had verified.
Bedrock's placeholder happened to fail the affordability check only because its
rate was set to 1e9 micro-USD on purpose; the four snapshots at 5e6/2e7 passed.

Recorded live evidence before this change: exactly one run,
`reports/phase-2/live-provider-status.json`, provider `openai`, model
`gpt-5-mini`, executed through `live-gate`. No provider had ever completed a
model call through `start` or `advance`.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Widen the `--provider` literal only | Defect 1 above | One-line change | Defect 2 makes it actively dangerous: six providers would silently call OpenAI's endpoint with another vendor's model id and another vendor's key absent. A wrong provider is not an error the operator can see in the output | Rejected |
| Route the run path through `provider_registry` and share one gate with `live-gate` | `execute_live_gate` already does exactly this; the registry, the preflight, and seven shipped configurations exist | One code path for every provider; a provider added to the registry is selectable, constructable, credential-checked, and pricing-bound with no further edit | The run path inherits every preflight refusal, so providers whose optional SDK is absent or whose rate is unconfirmed cannot run until an operator acts | Selected. Choices derived from the registry; adapter construction is itself a gate; per-provider credentials; provider match between selection and configuration |
| Add a per-provider branch in the CLI | -- | Explicit | Seven branches to keep in step with the registry; drift is invisible until a live call goes to the wrong vendor | Rejected |
| Defer | -- | No new surface | Leaves the owner unable to run any problem against six configured providers, which is the immediate goal | Rejected |

## Decision

Adopt the registry-routed option. Nothing about the trust model changes and the
`ModelGateway` port is untouched: a model result remains a proposal and no
provider response acquires a warrant by being returned.

**Choices are derived, never re-listed.**
`RUN_PROVIDER_CHOICES = ("fake", *registered_providers())`. `fake` stays first
and stays the default. A provider added to `PROVIDER_SPECS` appears on `start`
and `advance` automatically, and the acceptance suite asserts the derivation
mechanism, not just the current equality, so a pasted literal fails the suite.

**One gate for every provider, including OpenAI.** `_prepare_live_run` is shared
by `start` and `advance`: credentials resolve through
`load_provider_credentials`; the content-hashed configuration and the pinned
pricing snapshot must both load; the selected provider must equal the configured
provider; and `preflight_live_gate` must pass. `_loop` then builds the adapter
through `build_gateway(configuration.provider, configuration.model_identifier)`
and re-checks the binding between configuration, snapshot, provider, and model
before the loop is constructed.

**Fail closed, by name, with no default.** A missing required field is reported
as its own variable name and nothing else. Azure needs
`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and
`AZURE_OPENAI_API_VERSION`; Bedrock needs `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, and `AWS_REGION`, with `AWS_SESSION_TOKEN` optional.
There is no fallback to a default value, to another provider, or to the fake
gateway: a refused run creates no run record at all. Selecting a provider that
the configuration does not name is `provider_mismatch:selected=X:configured=Y`,
never a silent substitution.

**Credentials come from the multi-provider loader; ADR-0009's single-key loader
is untouched.** `load_repository_env` keeps its accepted semantics and is no
longer called by the CLI. `load_provider_credentials` retains every ADR-0009
control -- mode 0600, regular non-symlink file, no interpolation,
unknown-key/duplicate/unmatched-quote rejection, process environment never
overridden, no value in the result -- and treats a blank entry as unconfigured.

**Unconfirmed pricing is a fail-closed refusal.** `pricing_confirmation_status`
reads the recorded `UNCONFIRMED` marker in `source` and the preflight appends
`pricing_snapshot_unconfirmed:<snapshot_id>`. The classifier is deliberately
**exclusion-only**, on the ADR-0032 precedent: finding the marker can only
withhold confirmation. Its absence is *not* evidence that a rate is right, and
no rate is asserted anywhere in this slice. The operator clears the refusal by
capturing the real rates and recording them with `phase2 pricing-create`.

**Secrets are redacted per provider, not per OpenAI.** `provider_secret_values`
returns the configured secret-bearing credentials for the selected provider,
excluding the declared non-secret operational settings (`AWS_REGION`, the three
Azure settings, `MINIMAX_GROUP_ID`) so a region string cannot be reported as a
leak. The live-gate leak scan and the CLI blocker redaction both use it.

**Schema and serialization are unchanged.** No pricing or configuration schema
version moves, no snapshot content hash changes, and no third-party import is
added at module level. `pyproject.toml` dependencies stay `[]`.

## Consequences

- Operational: all seven providers are selectable and constructable on the run
  path. None is enabled by default; each still needs its credentials, a
  content-hashed configuration, a confirmed pinned snapshot, and -- where the
  adapter uses one -- the pinned optional SDK.
- Operational, negative: `advance` and `start --execute` with a live provider
  spend real money by design. The gate that stands between a typo and a bill is
  the affordability preflight plus the budget in the configuration, and nothing
  more. This is the same exposure the OpenAI path already had, now available to
  six more providers.
- Security: the leak scan now runs for every provider and covers Bedrock's
  secret access key and session token. A non-OpenAI live gate no longer ends in
  `KeyError`.
- `load_repository_env` now has no caller in `src/`. It keeps its ADR-0009
  accepted semantics, its exports, and its tests, and is deliberately left in
  place rather than being changed or removed under a sealed decision; a reader
  should not infer from the absence of a caller that its rules were relaxed.
- Cost: making unconfirmed pricing fail closed means Bedrock cannot run until an
  operator captures a rate, and ADR-0037 documents that the AWS Price List API
  had no Claude Opus 5 product to capture. That is the mechanism working, and it
  is also a real block on a provider the owner asked for.

**The honest risk.** Every one of these providers is verified only up to the
last instruction before the socket. Construction, credential resolution,
endpoint building, capability declaration, pricing binding, and refusal are
tested offline. Auth acceptance, request-body correctness, response shape, token
accounting, error taxonomy, and refusal semantics are not, and cannot be, tested
without a real key. Two of the values on the request path are recorded
`UNCONFIRMED` in the adapter source itself -- the MiniMax, DashScope, and
DeepSeek default base URLs, and whether MiniMax's group id belongs in the query
string. A wrong base URL fails closed rather than returning a wrong answer, but
an OpenAI-compatibility layer that diverges on structured output can return a
plausible wrong result instead of an error, and no offline test detects that.
The second-order risk is procedural: six green providers in the acceptance suite
read like six working providers. They are six providers whose offline half works.

## Measured outcome

Implemented and measured 21 August 2026. `tests/test_phase2_provider_run_path.py`
adds 32 tests; the Phase 2 suite is 352 tests green; the offline unit suite is
green apart from two concurrent slices' in-flight files (`test_phase5_noncommuting_certificates`)
and one CPU-timing test that passes in isolation.

| Property | Measured |
|---|---|
| Providers in `SUPPORTED_LIVE_PROVIDERS` | 7 |
| Selectable on `start` and `advance` | 7 of 7 (was 1 of 7) |
| Constructable from their shipped configuration | 7 of 7 |
| Shipped configuration + pinned snapshot present and cross-bound | 7 of 7 |
| Reporting exactly their own required credentials | 7 of 7 |
| Completing the full run-path bind offline (exit 0, no socket) | 1 of 7 (`bedrock`, with a locally recorded confirmed snapshot) |
| Providers with any recorded live model call | 1 of 7 (`openai`, via `live-gate`, before this slice) |
| Providers with a recorded live call through `start`/`advance` | 0 of 7 |
| Unconfirmed shipped snapshots refused by the preflight | 1 of 7 (`bedrock`; the other six were confirmed by concurrent ADR-0037) |

Only Bedrock reaches exit 0 offline, because it is the only adapter that needs no
optional SDK. That run binds the content-hashed configuration and the pinned
snapshot to the run record, records zero model calls, opens no socket, and
persists no secret -- asserted, including a scan of every workspace file and
every SQLite text column for both the fake secret access key and the fake
session token.

Forbidden outcomes, each demonstrated impossible rather than left untested:

| Forbidden outcome | Demonstration |
|---|---|
| A provider selectable but unconstructable | Every registered provider is built from its shipped model identifier, is the provider-specific adapter class, and satisfies the port shape; the selectable set and the constructable set are asserted equal |
| A missing required config field silently defaulted | Each of Azure's four fields withheld in turn is the only reported variable; `resolve_endpoint` raises naming the withheld variable; Bedrock's `resolve_region` raises naming `AWS_REGION`; no refused run exists in the workspace |
| A secret unredacted in any record, export, or report | A bound Bedrock run is read back through `jobs`, `budget`, `timeline`, `artifacts --content`, `review`, `export`, and `report`, plus a file-and-column scan; a refused run's blocker output is scanned too |
| A network call during the offline suite | Every CLI invocation in the suite runs with `socket.socket`, `socket.create_connection`, and `socket.getaddrinfo` replaced by a raising stub; the guard is itself proved live by two tests that expect it to fire |
| An unconfirmed snapshot passing as confirmed | Shipped snapshots must classify exactly as their file names declare; the preflight refuses the unconfirmed one and passes the same configuration with a confirmed one, so the refusal is not vacuous; the marker is matched case-insensitively |
| A provider in the registry absent from the CLI choices | Choices asserted equal to `("fake", *sorted(SUPPORTED_LIVE_PROVIDERS))` and to `("fake", *registered_providers())`; the derivation expression is asserted in the source; every provider is accepted by both subcommands and an unadmitted name exits 2 from the parser |

Mutation-checked, not assumed: reverting the choices to `("fake", "openai")`
fails five tests, removing the unconfirmed-pricing refusal fails three, and
removing the provider-mismatch check fails one.

**Unexercised until a real key is present, and recorded as untested:** every live
model call for all seven providers through `start`/`advance`; every live call for
`anthropic`, `azure_openai`, `bedrock`, `deepseek`, `minimax`, and
`qwen_dashscope` through any command. Their absence is not a pass, exactly as
AGENTS.md requires for the Phase 4B live HTTPS gate.

## Explicit deferrals

- Any live execution. No key was used, no socket was opened, and no live status
  artifact is written by this slice.
- Bedrock rate capture. Blocked on ADR-0037's recorded capture failure; the
  snapshot schema also has no region field, and a Bedrock rate is region-scoped.
- Verifying the `UNCONFIRMED` values inside `openai_compatible_gateway.py` (base
  URLs, MiniMax group-id placement, the error-code sets). Each needs provider
  documentation, not a code change.
- A machine-readable pricing confirmation field. Adding one moves
  `PRICING_SNAPSHOT_SCHEMA_VERSION` and rewrites every shipped snapshot's
  content hash, and the concurrent rate slice was editing those files. The
  text marker is consumed as an exclusion-only signal until then.
- Cross-provider verifier independence. `_loop` still uses one gateway for both
  proposer and verifier and records `different_provider=False`. Two providers in
  one run is a separate slice with its own independence semantics.
- `AGENTS.md` and `README.md` narrative updates, left to the owner because two
  concurrent slices were editing both files.

## Validation and revisit trigger

Valid while `make check` stays green and fully offline with no new skips, the CLI
choices stay derived from the registry, every provider keeps reporting exactly
its own credentials, and no unconfirmed snapshot passes the preflight.

Revisit if a provider is added whose required configuration cannot be expressed
as environment-variable names (a certificate file, a signed assumed role, an OIDC
exchange); if a compatibility layer is found returning a plausible wrong result
that the offline suite cannot see; if the exclusion-only pricing marker is found
to have let a wrong rate through, which would argue for the schema field deferred
above; or on the first live call by any provider, whose outcome must be recorded
whether it passes or fails.

## Addendum: first live call on the run path (21 August 2026)

This section discharges the revisit trigger above -- "on the first live call by any
provider, whose outcome must be recorded whether it passes or fails" -- for
`openai` and for no other provider.

One live run executed through `phase2 start --execute --problem`, the path this
ADR opened. It is the first recorded live model call through `start`/`advance` by
any provider; the pre-existing `reports/phase-2/live-provider-status.json` records
a `live-gate` call, which is a different entry point. Evidence:
`reports/phase-2/live-openai-gpt5-mini-problem-intake-v1/`, whose
`live-run-status.json` is computed from the workspace and the CLI's own report
rather than hand-authored.

The subject was an ADR-0039 declarative problem definition, not the built-in
fixture: `fixtures/problem-intake/sum-two-squares-mod-four-v1.json`, canonical
hash `sha256:61ce0bfad20f0645...`, asserting that no integer congruent to three
modulo four is a sum of two integer squares. So this run also measures the
ADR-0039 intake and the ADR-0038 run path composed, which nothing had done.

| Property | Measured |
|---|---|
| Entry path | `phase2 start --execute --problem` |
| Provider / configuration | `openai` / `config.phase2.live.gpt5-mini.v3` |
| Resolved model | `gpt-5-mini-2025-08-07` |
| Calls | 2 (`proposer`, `verifier`), both `succeeded`, both `usage_source: api_reported` |
| Cost | 5,628 micro-USD against a 20,000 ceiling; preflight estimated 13,192 for two calls |
| Tokens | 5,093 API-reported |
| Wall time | 31.3 s |
| Budget exit | `exhausted_dimensions: ["attempts"]` -- the run stopped on its own attempt limit, not on cost or wall clock |
| Credential leak matches | 0 across every workspace file and every SQLite text column, 2 configured credentials scanned |
| Mathematical content | A correct proof: assume the contrary, apply the accepted lemma that a square is 0 or 1 mod 4, enumerate the four residue pairs to get sums 0, 1, 2, contradict 3. The verifier returned two `supports` findings citing the premise by its exact claim ID |
| Measured `logical_status` | `unknown` |
| Warrant IDs / evidence IDs | `[]` / `[]` |
| Blockers | `target_unwarranted`, `alignment_unapproved`, `semantic_target_not_resolved` |
| Proposal dispositions / source kinds | `["proposal"]` / `["model"]` |

The load-bearing result is the last four rows. A correct proof, produced by a real
model and confirmed by a real second call, moved the trust projection by exactly
nothing. The report line "model/backend output did not mutate it" is now measured
against live output rather than a fixture.

**What this is not evidence of**, stated because six green offline providers
already read like six working providers:

- The other six providers remain exactly as untested as before. The Status line at
  the head of this ADR does not move: `anthropic`, `azure_openai`, `bedrock`,
  `deepseek`, `minimax`, and `qwen_dashscope` still have no live evidence of any
  kind, and their absence is not a pass.
- One run against one model on one problem is not a measurement of the adapter's
  error taxonomy, refusal semantics, or retry classification. Every value in the
  ADR's "honest risk" paragraph that a single successful call cannot exercise
  stays unexercised, including the recorded `UNCONFIRMED` base URLs of the
  OpenAI-compatible providers, which this run does not touch.
- The verifier was not independent. Measured
  `verifier_context_manifest.independence`: `context_isolated: true` and
  `separate_model_call: true`, but `different_model: false`,
  `different_provider: false`, `formal_kernel: false`,
  `deterministic_checker: false`, `independently_implemented_checker: false`. One
  gateway served both roles, so this is a model checking itself in a fresh
  context. The cross-provider independence slice deferred above is now the
  measured next gap rather than a theoretical one.
- The proof was not formally checked. Nothing converts a Phase 2 proposal into a
  Phase 3B Lean request -- `phase3b` is still reachable only from `cli.py`'s
  dispatcher and from no other module -- so no `kernel_checked` attestation
  exists and the publication projection would render this claim as `Conjecture`.
  The concurrent ADR-0040 does not change this: it adds a repair loop and a
  `ProofProposer` port above the sealed runtime, but that port is a model-shaped
  hole with a scripted proposer only, and its own Consequences section records
  that wiring a live proposer is a separate slice which must satisfy this ADR's
  live-gate precedent. The natural-language-to-Lean step is unbuilt in both
  directions.
- The run reached `awaiting_review` and parks there. No command records a review
  verdict, approves the semantic alignment, or discharges either obligation, so
  the two obligations ADR-0039 opens remain open by construction rather than by
  judgement.

The correctness of the mathematics is a human reading of the proposal text in
`proposals.json`, recorded here as such. It is not a warrant, not a verification
record, and creates no applicability record or graph admission.
