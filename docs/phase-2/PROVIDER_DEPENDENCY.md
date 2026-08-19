# Phase 2 Optional Provider Dependency

The offline Phase 0–2 suite remains standard-library-only. A live OpenAI run
additionally requires this adapter dependency:

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
