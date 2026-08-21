# Phase 2 Optional Provider Dependency

The offline Phase 0–2 suite remains standard-library-only. Live runs
additionally require the adapter dependency for the provider being called. The
Bedrock adapter needs none: its Signature Version 4 signing is standard-library
only.

A live OpenAI run — and any OpenAI-compatible provider (MiniMax, Qwen on
DashScope, DeepSeek, Azure OpenAI), which share this SDK — requires:

| Field | Value |
|---|---|
| Direct dependency | `openai==3.3.0` |
| Upstream | `https://github.com/openai/openai-python` |
| Distribution | `openai-3.3.0-py3-none-any.whl` |
| PyPI URL | `https://pypi.org/project/openai/3.3.0/` |
| Wheel SHA-256 | `ded6b2112e6d299c7a2573ff6f165dc92fb64ceaa4d7daa42345f091157bd373` |
| Upstream commit from PyPI attestation | `56807c041cb4b54222535a578332fa0649602318` |
| License | Apache-2.0 |
| Reason | Supported `APIStatusError` diagnostics and typed Responses API boundary |
| Owner | Phase 2 OpenAI adapter |
| Removal path | Replace the adapter transport while preserving `ModelGateway`, projection, diagnostics, and tests |

A live Anthropic run requires:

| Field | Value |
|---|---|
| Direct dependency | `anthropic==1.0.0` |
| Upstream | `https://github.com/anthropics/anthropic-sdk-python` |
| Distribution | `anthropic-1.0.0-py3-none-any.whl` |
| PyPI URL | `https://pypi.org/project/anthropic/1.0.0/` |
| Wheel SHA-256 | `32dd52e9e1d774393b27182f451398ba4262287a4d0eab30887f89f1481b3ae4` |
| Upstream commit from PyPI attestation | none published for this release |
| License | MIT |
| Reason | Typed Messages API boundary and `APIStatusError` classification for the Anthropic adapter |
| Owner | Phase 2 Anthropic adapter |
| Removal path | Replace the adapter transport while preserving `ModelGateway`, projection, diagnostics, and tests |

Two things about this pin are weaker than the `openai` one above and must not be
read as equivalent. There is no PyPI publish attestation for the release, so its
provenance rests on the recorded wheel digest alone. And `1.0.0` is a breaking
release: it moves the SDK's HTTP layer to `httpx2` and removes deprecated
request parameters. Neither reaches this adapter — it passes plain values to the
client rather than `httpx` objects, already sends
`output_config={"format": ...}`, and passes no sampling parameters — but a
future pin move must re-check the upstream migration notes rather than assume
the same.

Install explicitly; repository checks never auto-install or access the network:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-phase2-provider.txt
```

The direct package is pinned and its published wheel hash is recorded. The
current execution environment did not permit downloading a transitive lock, so
a fully hash-locked provider environment remains an operational follow-up before
clean-room live replay. Live preflight requires the exact SDK version. The v3
host-environment gate passed; the transitive-lock limitation remains an
operational reproducibility risk rather than an acceptance failure.
