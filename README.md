# AdaIvy

<p align="center">
  <a href="https://staple.ai/"><img src="docs/assets/staple-logo-dark.svg" alt="Staple AI" width="120"></a><br>
  Sponsored and maintained by <a href="https://staple.ai/">Staple AI</a>.
</p>

**A verification-first system for AI-assisted mathematical research.** AdaIvy
combines model-driven investigation, literature retrieval, computation, and
formal tools while keeping proposals separate from verified results.

The intended product is a budgeted, resumable research campaign:

```text
problem -> literature -> persistent corpus and embeddings -> retrieval
        -> investigation and experiments -> exact/Lean verification -> report
```

That complete path is now exercised by an offline, deterministic acceptance
runtime; live effects remain separately activated. See
[Capability Status](docs/CAPABILITY_STATUS.md) for the precise current state and
[End-to-End Research Runtime Plan](docs/END_TO_END_RESEARCH_RUNTIME_PLAN.md) for
the delivered slices and remaining live-activation boundary.

## Current status

Implemented components include:

- provider-neutral model gateways with bounded live activation and accounting;
- a sequential central-lead campaign with a causal, replayable ledger;
- a legacy digest-pinned OCI experiment sandbox plus a fail-closed v2
  persistent scientific workspace with exact target-class routing;
- exact mathematical verifiers and a sealed Lean 4 checking service;
- paginated, policy-authorized Crossref/arXiv/OpenAlex discovery, depth-one
  following, and bounded batch public acquisition;
- bounded arXiv metadata/abstract corpus replay;
- a persistent multi-run corpus store (ADR-0072 Slice 3) at an
  operator-selected data root outside Git, with policy-derived per-document
  rights, quarantine, exact parsed spans, immutable content-addressed
  generations, takedown tombstones, chunked retrieval, and a gated resumable
  snapshot fetcher with pinned extraction identities; live snapshot acquisition
  stays behind its own pending activation;
- processor-bound embedding rights, live embedding ingestion, and immutable
  exact vector artifacts;
- four-signal Phase 4C retrieval, including semantic similarity; and
- record-driven publication with provenance and reproducible typesetting.
- automatic claim-free LaTeX status drafts for terminal campaigns, with
  idempotent terminal-finalization resume;
- persistent corpus-backed vector projections and exact-span evidence cards;
- first-class literature/acquire/parse/embed/index/retrieve/formal-check action
  names; and
- `campaign start` plus action-level `campaign resume` for the complete offline
  fixture path, using an explicit credential profile and unified budget; and
- a model-driven v2 runtime API with a closed effect registry, repeatable
  literature cycles, published-generation retrieval checks, and durable
  human-answer continuation.

The end-to-end workflow is runnable offline. The following live scope remains
separately gated or pending:

- production snapshot acquisition remains pending;
- live Crossref, provider, embedding, OCI, and Lean effects require their named
  activation gates;
- the legacy `campaign run` command retains its compatibility contract,
  including a human novelty re-check; the new end-to-end path structurally
  records search before research and does not require that checkpoint; and
- the offline fixture uses the bounded built-in exact experiment/verifier; the
  generated-program OCI route and v2 workspace image remain separately
  activated campaign paths; and
- the Slice 16 live acceptance definition is shipped fail-closed, but no live
  end-to-end execution evidence has been recorded.

`campaign resume ROOT` detects end-to-end campaign roots and replays completed
action checkpoints without repeating paid work. It still performs the original
terminal-finalization behavior for legacy campaign roots. An orphaned paid or
irreversible intent is retained as unresolved rather than retried; an
idempotent local projection may retry under the same key.

Passing `make check` includes the complete offline fixture campaign. It does not
activate or claim success for any live external capability.

Validate the sealed live-gate definition without making any external call:

```sh
make check-campaign-live-definition
```

The active execution form additionally requires the exact acknowledgement and
a directory containing each named, hash-valid activation record. The checked-in
gate is intentionally pending, so this command currently refuses before I/O:

```sh
python3 -m math_research.cli campaign live-acceptance --execute \
  --evidence-directory /path/to/activation-evidence \
  --activation-acknowledgement I_ACKNOWLEDGE_LIVE_END_TO_END_CAMPAIGN
```

Run that path directly with an external persistent data root:

```sh
python3 -m math_research.cli campaign start work/campaign campaign.example \
  --data-root /path/outside/the/git/tree/adaivy-data \
  --data-root-id dataroot.adaivy.primary --profile-id adaivy \
  --max-model-requests 64 --max-embedding-requests 256 \
  --max-network-requests 64 --max-tool-runs 64 \
  --max-storage-bytes 1000000000 --max-wall-milliseconds 3600000 \
  --recorded-at 2026-08-22T00:10:00Z --problem problem.txt
python3 -m math_research.cli campaign resume work/campaign
```

## Design principles

- **One coherent research lead:** literature, experiments, competing branches,
  and incremental formalization belong in the central campaign loop.
- **AdaIvy owns its spend:** live campaign model and embedding calls must use an
  explicitly selected AdaIvy credential profile and appear in campaign
  accounting. Host Codex or Claude work is an external import.
- **Retrieval supports reasoning:** a retrieved passage may inspire work but is
  not a proof or trusted premise without an applicability record.
- **Verification is independent:** model agreement, retrieval rank, and finite
  experiments cannot create proof status.
- **Lean is available, not compulsory at every step:** use it when a claim is
  mature and for final formal checking where an appropriate Lean statement
  exists.
- **Corpus knowledge persists:** source and embedding artifacts are intended to
  grow across campaigns while derived indexes remain rebuildable.
- **Failure is durable:** failed calls, rejected candidates, missing tools, and
  unresolved obligations remain in the research record.
- **Network is explicit:** offline checks remain offline; live model,
  acquisition, and embedding paths are separately authorized and budgeted.

## Quick start

Requirements: CPython 3.14. The ordinary acceptance suite needs no network,
model provider, container runtime, or third-party package.

```bash
git clone https://github.com/jketts/AdaIvy.git
cd AdaIvy
make check
make help
```

Important additional gates:

| Target | Requirement |
|---|---|
| `make check-sealed` | ADR-0016 v5 Lean image |
| `make check-gate PY=…` | pinned Draft 2020-12 validator environment |
| `make check-phase4b-oci` | Docker and the pinned parser image |
| `make check-campaign-experiment-oci` | Docker and the pinned campaign image |
| `make check-campaign-live-definition` | offline validation of the pending Slice 16 live gate |
| `make check-embedding-live` | configured embedding provider and explicit live acknowledgement |
| `make check-typeset` | pinned local BasicTeX toolchain |
| `make check-all` | offline checks plus the sealed Lean gate |

Every phase is reachable through the common CLI:

```bash
PYTHONPATH=src python3 -m math_research.cli --help
```

Installing the package also provides `adaivy` and `adaivy-phase0` console
scripts. Current commands and their bounded scopes are documented in
[Technical Details](docs/TECHNICAL_DETAILS.md).

## Trust model

AdaIvy records these properties separately:

- fidelity to the intended problem;
- mathematical or empirical warrant;
- source provenance and applicability;
- novelty;
- significance; and
- human, model, and tool contributions.

A proof assistant establishes correctness of the encoded proposition relative
to its environment. It does not establish that the proposition faithfully
captures the informal question, that a cited theorem applies, or that the result
is new. Those distinctions remain visible rather than being collapsed into one
“verified” label.

## Outputs

Checks are gates: they use temporary directories and do not write tracked
artifacts. `make report` is the durable counterpart and writes a content-hashed
index beneath `OUT`, defaulting to `reports/local/run-<stamp>`.

`reports/local/` and `work/` are ignored. Evidence deliberately promoted under
another `reports/` path is tracked. Live, growing corpus databases and derived
indexes do not belong in Git; portable manifests and selected evidence bundles
are exported explicitly.

Reader-facing solved-result papers use the record-driven publication path:

```bash
make publication-build MANUSCRIPT=/path/to/manuscript.json \
  CAMPAIGN_EXPORT=/path/to/campaign.json \
  CAMPAIGN_LINK=/path/to/publication-campaign-link.json \
  PUBLICATION_OUT=output/pdf/my-result
```

The records are authoritative. `paper.tex` is a deterministic projection and
`paper.pdf` is a reproducible build product; neither feeds information back into
the research state.

## Repository map

```text
src/math_research/     domain, phase slices, campaign, adapters, reporting, CLI
tests/                 unit, integration, property, and adversarial tests
fixtures/              deterministic acceptance fixtures
schemas/               versioned interchange schemas
migrations/            durable-workspace migrations
config/                pinned run, pricing, activation, and image configuration
spikes/                reproducible component-evaluation spikes
reports/               recorded gate evidence and ignored local runs
docs/                  technical details, plans, ADRs, and historical evidence
```

## Documentation authority

| Document | Role |
|---|---|
| [Capability Status](docs/CAPABILITY_STATUS.md) | What is implemented, activated, wired, and runnable now |
| [End-to-End Runtime Plan](docs/END_TO_END_RESEARCH_RUNTIME_PLAN.md) | Forward implementation plan |
| [Technical Blueprint](TECHNICAL_BLUEPRINT.md) | Architecture and correctness contract |
| [Technical Details](docs/TECHNICAL_DETAILS.md) | Current commands and bounded component behavior |
| [ADR index](docs/adrs/README.md) | Decision history and current integration ADRs |
| [Prior-Art Landscape](NOVELTY_LANDSCAPE.md) | Dated architecture research, not current runtime status |
| [Repository Instructions](AGENTS.md) | Stable contributor and agent rules |

Historical phase plans, gate reports, threat models, fixtures, and accepted or
superseded ADRs remain evidence. They are not the current capability summary.

## First benchmark

The original benchmark studies the Jezek–Rehacek–Fiurasek iterative method for
minimum-error quantum-state discrimination. Quantum-specific mathematics stays
inside the benchmark package and must not leak into the core claim, evidence,
workflow, or verification abstractions.

## Licence

Licensed under the Apache License 2.0. Fixture corpora under `fixtures/` are
project-authored synthetic data carrying
`LicenseRef-AdaIvy-Synthetic-Fixture`.
