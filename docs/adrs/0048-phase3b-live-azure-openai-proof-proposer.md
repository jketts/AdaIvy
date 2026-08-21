# ADR-0048: Bounded live Azure OpenAI proposer for Phase 3B proof repair

- **Status:** accepted for the opt-in live proposer slice
- **Date:** 2026-08-21
- **Blueprint requirement:** Sections 8 and 19; ADR-0040 bounded proof repair;
  ADR-0030 provider gateways
- **Decision owners:** repository owner and researcher

## Context

ADR-0040 implemented the correct repair control plane but deliberately left its
`ProofProposer` port without a live implementation. Consequently Phase 3B could
exercise repair only with scripts. The owner has now explicitly authorized
model calls and identified an Azure OpenAI deployment already represented by
the Phase 2 provider registry and confirmed pricing snapshot.

The live boundary must not turn a model into a verifier. In particular, it must
not expose validator diagnostics, alter the theorem, retry semantic failures,
or let a successful response create warrant. Live use must remain absent from
the offline `make check` path.

## Decision

Add `phase3b/live_proposer.py` as an outward implementation of ADR-0040's
`ProofProposer`. It reuses the admitted `azure_openai` gateway, its guarded
`.env`/`.env.settings` loading, the exact optional SDK pin, strict structured
output projection, response validation, and the confirmed Azure pricing
snapshot. No second provider transport or dependency is introduced.

The model's entire output schema contains one nonempty `proof_fragment` string.
The context identifies Lean diagnostics as untrusted compiler data. The model
cannot return a target, declaration, import, assumption, claim, meaning test,
or trust field. ADR-0040 independently rebuilds the request and re-derives all
frozen identity fields before every submission. It still repairs exactly
`elaboration_failure`; policy rejection, meaning-test failure, unapproved
assumptions, timeout, output limit, and sandbox failure remain terminal.

Live execution is a separate `phase3b repair-live` command and requires all of:

1. an explicit `--execute` acknowledgement;
2. a content-hashed Phase 3B live configuration;
3. a matching confirmed pricing snapshot;
4. the exact pinned provider SDK;
5. all named Azure credential and endpoint settings; and
6. the sealed ADR-0016 Lean image required by the unchanged checker.

`repair-live-preflight` checks items 2--5 without making a network call. The
configuration bounds model calls, diagnostic bytes, serialized context bytes,
output tokens, timeout, and worst-case reserved cost. At most fifteen model
calls are possible because ADR-0040 caps total attempts at sixteen and the
origin consumes one. Each public call record retains hashes, provider/model,
response ID, usage, attributed cost, and status, but not proof text, diagnostic
text, or credentials. Every checker attempt remains proposal-only durable state.

## Consequences

- Phase 3B can now use a live Azure OpenAI model to propose bounded repairs.
- The model does not gain access to the sealed runtime, validator, launcher,
  container policy, workspace, or trust transition methods.
- A kernel-checked repaired proof is still attributed to `MODEL` and still sets
  `epistemic_warrant_created` to false. Human review and the existing trust
  policy remain separate.
- The offline suite uses a scripted `ModelGateway`; imports open no socket and
  do not require the optional SDK. `make check` remains network-free.
- The first live result is operational evidence about one configured model and
  request, not evidence of general solve rate or cost-adjusted retention gain.

`fixtures/phase3b/live-repair-smoke.json` is the bounded activation request. Its
deliberately unknown proof term produces `elaboration_failure`; a live proposer
may replace only that fragment while the trivial theorem `(n : Nat) : n = n`
and every other request field remain frozen.

## Measured gates

`tests/test_phase3b_live_proposer.py` demonstrates configuration hash checking,
Azure-only routing, SDK/credential/setting/pricing preflight, hard call and cost
bounds, exact one-field output, explicit diagnostic distrust, malformed-output
refusal, and public-record secret/proof-text exclusion. The ADR-0040 suite
continues to prove the theorem-identity, repairable-outcome, attribution, and
non-promotion invariants.

## Revisit trigger

Revisit before admitting another provider, allowing premise retrieval or import
changes, changing the response beyond one proof fragment, retrying any outcome
other than elaboration failure, feeding validator diagnostics to a model,
granting warrant, or using measured live results to activate a higher search
tier. Each is a separate architecture decision.
