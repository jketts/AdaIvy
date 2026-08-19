# Phase 2 Closeout

Date: 2026-08-19

## Closeout decision

Phase 2 is sealed as accepted. The bounded live-provider gate used the existing
known-valid even-sum fixture and recorded exactly one proposer call and one
separate, context-isolated verifier call. No additional provider call is needed
or authorized for closeout.

The live workflow deliberately remains `awaiting_review`. Its two outputs are
acceptance-test evidence with `proposal` disposition, not mathematics accepted
into the Phase 1 trust core. Closing Phase 2 must not import or promote either
proposal. A distinct, future human-review disposition is required if anyone
wants to assess the mathematical content; such a workflow is not implemented.

## Sealed provider evidence

| Field | Complete value |
|---|---|
| Run ID | `run.phase2.live.openai.gpt5-mini.v3` |
| Fixture | `known-valid-even-sum` |
| Proposer response ID | `resp_07822df2a3cc157a016a85705b263c87d082e6f2679308368d` |
| Verifier response ID | `resp_0124dadfd2b93e8c016a8570668f9487d0b7c38ed0bb2b302a` |
| Configured model | `gpt-5-mini` |
| Proposer returned model | `gpt-5-mini-2025-08-07` |
| Verifier returned model | `gpt-5-mini-2025-08-07` |
| Pinned SDK | `openai==3.3.0` |
| SDK wheel SHA-256 | `ded6b2112e6d299c7a2573ff6f165dc92fb64ceaa4d7daa42345f091157bd373` |
| Live-run verifier manifest hash | `sha256:e625dcfdbe8ddab1f266ebb74935e0311ba2f1f3a11acf55920277c5b9e0bdd0` |
| Event replay hash | `sha256:d5bb8e34704404aa3f69e44f4f19c32787a747fd5a2d70ab323028e998fcd24c` |
| Restart-regenerated report hash | `sha256:ff706139a8f0415e1f1f6efc0ac714f0e588f187e94e82c7dff0af92d5da8cb9` |
| Live-provider-status file SHA-256 | `sha256:c29c13d80164890d0b5d1d1fdca3eeac66c56300c9683a1c4087d7bc03c1ac05` |
| Failed v2 database file SHA-256 | `sha256:4c1c402d142a33d6529fb3991cb18bab2513bcb13dd2eddd3b30af0ab76ad064` |
| Accepted v3 database file SHA-256 | `sha256:30e0db8d1bf9b601ce9d262fdce9459dea573c742aaca27f7af97d7895f81e94` |

The v2 database, its failed provider request ID
`req_32c9c66a4fb1414292df36cb4c031aad`, diagnostics, events, and hashes remain
immutable history.

## Schema-boundary evidence

| Contract | Canonical SHA-256 | OpenAI projection SHA-256 |
|---|---|---|
| Proposer v1 | `sha256:29a9a65656f50cecefd40b0f11ff8750e5d164549b85d153177bb13ac4a238ce` | `sha256:ae6fb22a5691ab4090bf8e16c7048f61379f1d037ae3fe973b8bbf93c9fadff5` |
| Verifier v1 | `sha256:243155a597985e90a00d560cd1f4aa18e16e8ffcde29b6c163a9b1a0ea96652d` | `sha256:7da47da062224e0777931f204baeb3b760f1853f77ce5f54850e21c0782a636d` |

Supporting artifact file hashes are:

- proposer transformation manifest:
  `sha256:54b3ecd10391b4d12b456ac7ebd61d05624403e80894631c720f9316c86297a3`;
- verifier transformation manifest:
  `sha256:3494a0d59dd3bc30944202ac40b9ef570a576752055d65274b58eeee43d9fdfb`;
- proposer compatibility report:
  `sha256:1c96b763807b198961cf563c9ddd1d165277e50a0aa4904ebd4c551b2ed182c4`;
- verifier compatibility report:
  `sha256:818967e9e3b5edf70a9ca8a6bc50b4df6098411b24da18d50f5e3b67f5cab7c0`.

Canonical schema bytes were not changed by provider projection.

## Configuration and pricing evidence

| Artifact | Canonical content hash | File SHA-256 |
|---|---|---|
| Pricing snapshot `pricing.openai.gpt5-mini.2026-08-19.v1` | `sha256:a32c6a0c3be255adf7863ba6fd8a5bf1c61c42697c23d7568d843e49e5234053` | `sha256:35a77682d4bc4f73820dae5fb22f5e672f8339e810943bbd04bc7fc0a670dd51` |
| Provider configuration `config.phase2.live.gpt5-mini.v3` | `sha256:03fcff9d4007985799bbf6b1e670a1b9c5900660ee444904c1bc681b04802da3` | `sha256:784e02367e1975d89927290a55b02b44129231f026004e142e3eaf58afb98b3b` |

The pricing snapshot records USD, micro-USD per 1,000,000 tokens, input rate
250,000, output rate 2,000,000, source
`https://developers.openai.com/api/docs/models/gpt-5-mini`, and capture time
`2026-08-19T08:07:15Z`. No price was fetched during the run or closeout.

API-reported usage was 2,367 input tokens, 1,824 output tokens, and 4,191 total
tokens. The pinned-snapshot estimate was 4,240 micro-USD (`$0.004240`). This is
an estimate, not a billed or settled provider charge. Billed cost is not
recorded and remains `null`/unknown.

## Trust and isolation confirmation

- The proposer proof attempt is proposal
  `proposal.run.phase2.live.openai.gpt5-mini.v3.proposer`, artifact
  `sha256:b00eb1e739e5190b7c35c8c5debf1ec0b0757c2437a128cccbe61741bb8ea8ff`.
- The verifier finding is proposal
  `proposal.run.phase2.live.openai.gpt5-mini.v3.verifier`, artifact
  `sha256:af8049d136ae567fa0bccecdd3d03be0c0e3a1182d2b140514197902dd950fb5`.
- No evidence, verification record, warrant, obligation discharge, or accepted
  claim was created from either external output.
- Verifier isolation is recorded as `context_isolated=true` and
  `separate_model_call=true`.
- `different_model=false`, `different_provider=false`,
  `deterministic_checker=false`, `independently_implemented_checker=false`, and
  `formal_kernel=false`; full independence is therefore false.
- The accepted dossier remains unknown with its proof obligation open.

## Verification performed during closeout

| Check | Result |
|---|---|
| Complete Phase 0–2 unit/adversarial/integration suite | 101/101 passed |
| Phase 0 component check | 19/19 passed |
| Repository JSON parsing | 46/46 files passed |
| Phase 0 semantic dossier validator | passed, zero issues |
| Phase 1 canonical dossier validator | passed, original hash preserved |
| Credential scan of artifacts, databases, events, logs, and reports | zero matches |
| Protected v2 database hash after checks | unchanged |
| Protected v3 database hash after checks | unchanged |
| Live-provider-status hash after checks | unchanged |
| Restart report hash after checks | unchanged |
| Provider/network calls during closeout | zero |

## Version control and release policy

The accepted Phase 2 commit and existing annotated tag both resolve to
`f8531aefc39792ecf02c61f0019cea087ebf87f2`. The configured remote is private.
This closeout recommends, but does not create, a reviewed documentation commit
and a later annotated tag named `phase-2-live-accepted`.

The repository license and gold-corpus redistribution rights remain unresolved.
Do not make the repository public, publish a release, or distribute source
documents until those decisions are recorded. No commit, tag, push, release, or
visibility change is performed by this closeout task.

The machine-readable seal is
`reports/phase-2/release-manifest.json`. Its canonical self-null content hash is
`sha256:844a20f5e4f581db7cd4d31981cf7fe35fa370a68812c6d258d1d896f0cba31e`;
the formatted file SHA-256 is
`sha256:90b188e134e0489318319919e09dedf52fb817f658f07b173ff4ab3d75188664`.
