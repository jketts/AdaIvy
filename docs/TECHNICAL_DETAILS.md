# AdaIvy Technical Details

This file holds the implementation-level detail that used to live in
[`README.md`](../README.md). The README is the short introduction; this document
is the per-phase reference for someone who is going to run, audit, or extend the
system.

Related documents:

- [`README.md`](../README.md) — project introduction and quick start.
- [`TECHNICAL_BLUEPRINT.md`](../TECHNICAL_BLUEPRINT.md) — the build contract.
- [`NOVELTY_LANDSCAPE.md`](../NOVELTY_LANDSCAPE.md) — prior-art review that
  informed architecture revision 0.2.
- [`AGENTS.md`](../AGENTS.md) — repository instructions, current phase, and
  engineering rules.
- [`docs/adrs/`](./adrs/) — architecture decision records. ADR-0012 records the
  accepted revision 0.3 delivery sequence while preserving the superseded
  roadmap history; ADR-0026 records the accepted delivery order for the work
  remaining after Phase 4B.

## Contents

- [What the system does](#what-the-system-does)
- [Architectural principles](#architectural-principles)
- [First benchmark](#first-benchmark)
- [Build sequence](#build-sequence)
- [Offline repository checks](#offline-repository-checks)
- [Multiple model providers, embeddings, and retrieval](#multiple-model-providers-embeddings-and-retrieval)
- [Phase 1 manual trust core](#phase-1-manual-trust-core)
- [Phase 2 durable baseline loop](#phase-2-durable-baseline-loop)
- [Phase 3A bounded research memory](#phase-3a-bounded-research-memory)
- [Phase 3B bounded Lean formal checking](#phase-3b-bounded-lean-formal-checking)
- [Phase 4B authorized acquisition and exact parsing](#phase-4b-authorized-acquisition-and-exact-parsing)
- [Phase 5 exact adaptive quantum benchmark](#phase-5-exact-adaptive-quantum-benchmark)
- [Phase 6 confirmatory evaluation and release](#phase-6-confirmatory-evaluation-and-release)
- [Bounded exploratory synthesis](#bounded-exploratory-synthesis)
- [Intended repository layout](#intended-repository-layout)
- [Suggested implementation defaults](#suggested-implementation-defaults)
- [Definition of done for the first vertical slice](#definition-of-done-for-the-first-vertical-slice)
- [Using this blueprint with Codex](#using-this-blueprint-with-codex)
- [External references](#external-references)

## What the system does

Given an informal research question, the system:

1. creates a precise, versioned problem specification;
2. records and obtains approval for how the working statement maps to the
   researcher’s intended question;
3. identifies ambiguities, assumptions, quantifiers, and success criteria;
4. acquires and parses relevant primary sources;
5. checks whether imported theorems actually apply, not merely whether they
   exist;
6. builds a provenance-preserving claim and dependency graph;
7. explores multiple hypotheses and mathematical representations;
8. calls existing research backends plus symbolic, numerical, discrete, and
   formal tools;
9. searches actively for counterexamples;
10. records every unresolved step as a proof obligation;
11. independently audits proposed arguments using isolated verifier contexts;
    and
12. reports a proof, counterexample, conditional theorem, reduction, or clearly
    delimited unresolved result.

## Architectural principles

- **Verification first:** generation and verification are separate operations.
- **Claims, not chats:** durable state is structured and queryable.
- **Provenance everywhere:** every sourced claim points to an immutable span.
- **Typed uncertainty:** unknown, plausible, tested, proved, and formally checked
  are distinct states, while warrant kinds remain non-interchangeable.
- **Semantic custody:** a correct proof of the wrong formalization does not solve
  the original problem.
- **Applicability before citation:** an imported theorem carries no proof weight
  until its hypotheses, definitions, scope, and implication are checked.
- **Representation integrity:** changing from arithmetic to topology, geometry,
  optimization, or another language creates explicit equivalence obligations.
- **Falsification before persuasion:** counterexample search begins early.
- **Reproducibility:** model, prompt, source, code, dependency, seed, and
  precision versions are recorded.
- **Replaceable components:** models, indexes, solvers, and proof assistants are
  adapters, not architectural dependencies.
- **Adopt before rebuilding:** established open-source systems and standards are
  tested, wrapped, or integrated whenever they improve capability.
- **Deep central loop:** the baseline research lead has literature access,
  experiments, multiple live branches, falsification, and incremental
  formalization from the beginning.
- **Measured orchestration:** activate bounded specialists only when task
  structure or measured stagnation predicts improved verified progress per
  unit cost, and retain them only while evaluation confirms that gain.
- **Evolutionary restraint:** evolutionary search requires a cheap, reliable
  verifier-backed fitness signal; noisy conceptual proof judgement is
  ineligible.
- **Central verification:** parallel workers return attributed proposals and
  never replace, vote over, or control the centralized verifier.
- **Evaluation integrity:** confirmatory metrics, data, and stopping rules are
  frozen before held-out execution.
- **Human authority:** the user controls the formal problem and publication of
  conclusions.

## First benchmark

The first end-to-end benchmark studies the iterative method in:

> M. Jezek, J. Rehacek, and J. Fiurasek, “Finding optimal strategies for
> minimum-error quantum-state discrimination,” arXiv:quant-ph/0201109.

The benchmark asks whether the iteration always reaches a global optimum under
precisely stated assumptions. The platform must remain neutral: a proof, a
counterexample, a corrected theorem, or a reduction to an unresolved lemma are
all successful research outcomes.

Quantum-specific mathematics belongs in a benchmark/domain package. It must not
leak into the core claim, evidence, workflow, or verification abstractions.

## Build sequence

1. **Capability/adoption spike:** evaluate MathGraph/Albilich-style proof state,
   OMDoc/MMT representation, Why3-style obligation dispatch, literature agents,
   and available Lean tooling on the same reference dossier.
2. **Trust core and manual slice:** semantic custody, applicability records,
   orthogonal warrants, obligations, frozen evaluation protocols, and an
   auditable report.
3. **Durable baseline loop:** persistent state, jobs, one proposer, one isolated
   verifier, and one external research-backend adapter.
4. **Phase 3A — bounded research memory:** manual local UTF-8 text ingestion,
   opaque metadata-only URI records, immutable source spans, deterministic
   SQLite FTS5/BM25 retrieval, evidence packs, and citation validation.
5. **Phase 3B — tools and formal grounding:** symbolic/exact/interval/SMT tools,
   a minimal proof-assistant adapter, meaning tests, and counterexample
   workflows.
6. **Phase 4 — broader research acquisition:** crawling, licensed corpus
   ingestion, richer parsing, embeddings, hybrid retrieval, and research
   automation.
7. **Adaptive search and benchmark:** keep one coherent lead and central
   verifier; activate bounded specialist or evolutionary overlays only where
   they beat that rich baseline on verified progress per unit cost.
8. **Confirmatory evaluation:** held-out tests, contribution reporting,
   clean-room replay, and release hardening.

Each phase has concrete exit criteria in the technical blueprint. Do not begin
with a broad crawler, custom graph platform, or hierarchical multi-agent swarm.
The central loop must nevertheless support literature, experimentation,
branching, and incremental formalization rather than becoming shallow. First
measure what existing components already provide and what gap remains.

## Offline repository checks

Phase 0 is implemented as a standard-library-only adoption/evaluation harness,
not as production platform code. Its canonical inputs and outputs are:

- `fixtures/phase0/reference-dossier.json`;
- `schemas/research-dossier.schema.json` and `schemas/backend-result.schema.json`;
- reproducible component spikes under `spikes/`;
- measured results under `reports/phase-0/`.

The single offline entrypoint is `make check`. It needs no network, no model
provider, no container runtime, and no third-party package:

```bash
make check
```

It runs the unit, integration, property, and adversarial suite plus the Phase 0
harness check and the Phase 1, 2, 3A, 4A, 4B, 5, 6, and synthesis acceptance
paths. `make help` lists every target.

Two targets need more than that and are named for what they need.
`make check-gate PY=/path/to/gate-venv/bin/python` requires the disposable
pinned Draft 2020-12 validator environment described in
`docs/phase-4/DEPENDENCY_LICENSE_ASSESSMENT.md`; fifteen gate tests skip
themselves unless that validator is importable, so the target refuses to run
rather than reporting a silent pass. `make check-sealed` covers Phase 3B and is
described below. `make check-all` runs the offline check and the sealed runtime
together.

The individual commands remain available for debugging a single phase; see the
`Makefile` for the exact invocation of each.

The bounded Phase 3B acceptance requires the exact local image sealed by
ADR-0016, which is why it is not part of `make check`. Without the image the
adapter fails closed and the run reports a failed status by design. Run it only
against a disposable workspace so the repository and the Phase 3A acceptance
state remain unchanged:

```bash
phase3b_check_root="$(mktemp -d /tmp/adaivy-phase3b-check.XXXXXX)"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase3b demo "$phase3b_check_root/workspace" --output-dir "$phase3b_check_root/output"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase3b inspect "$phase3b_check_root/output/formal-checking.json"
```

Optional integrations are never installed by the check. Configure an Albilich
checkout with `ALBILICH_ROOT`; place Why3 or Lean on `PATH`; or install PaperQA2
in a separately pinned environment. Missing prerequisites produce explicit
blocker records and do not fail the baseline harness.

The Phase 0 raw observations are immutable. The corrected dimensional
interpretation is `reports/phase-0/evaluation-correction.json`; blocked and
deferred candidates have `capability_score: null`.

Continuous integration (`.github/workflows/check.yml`) runs the offline check on
Linux and macOS, confirms no third-party package is importable, asserts the
expected skip count so a test cannot silently stop running, and runs the
structural invariants. `check-sealed` and `check-gate` stay local/owner-run
because their prerequisites are not publicly available.

## Multiple model providers, embeddings, and retrieval

Nothing in the current implementation makes retrieval depend on a model
provider, and that is worth keeping deliberately rather than by accident.

What holds today:

- Retrieval is lexical only. `src/math_research/phase3a/retrieval.py` is
  SQLite FTS5/BM25 behind a `RetrievalIndex` port that excludes model providers
  by construction, and `src/math_research/synthesis/ports.py` keeps the
  synthesis index replaceable for the same reason.
- There are no embeddings, no vector index, and no embedding-provider port.
  `RightsUse.EMBEDDING` in `src/math_research/phase4a/records.py` is a rights
  enum value awaiting an implementation, not a capability.
- Bounded multi-hop query expansion is deterministic. Terminology, notation,
  citation, and contrasting-approach queries in
  `src/math_research/synthesis/retrieval.py` derive from indexed record terms,
  never from a model, so a retrieval trace and its canonical hash do not vary
  with which provider produced a proposal.
- The live provider boundary currently admits one provider:
  `src/math_research/phase2/live_config.py` rejects anything other than
  `openai`, and `src/math_research/phase2/openai_schema.py` is the only
  structured-output projection. `ModelResult` already carries
  `provider_schema_hash` and `projection_manifest_hash`, so a second projection
  has somewhere to record its identity.

Consequently, admitting a second generation provider does not affect embeddings
or retrieval, because neither has a model-backed path. The exposure is entirely
forward-looking, and one part of it is a silent failure rather than an error:

- **Mixed vector space.** Vectors from different providers, or from different
  embedding models of one provider, share no geometry. A dimension mismatch
  fails loudly; two same-dimension models from different vendors return a full,
  plausibly ordered result set over a corrupted similarity space, which no
  ordering or recall test detects on its own. `TECHNICAL_BLUEPRINT.md` Section
  12.2.1 is the normative rule: partition a vector projection by `(provider,
  model_identifier, dimension, normalization)`, compare only within a partition,
  and rebuild rather than backfill on any provider or model change.
- **Deterministic rebuild.** The proposed Phase 4C gate demands exact equality
  of ordered IDs and canonical report hash across repeated, reverse-insertion,
  and fresh-process builds. No remote embedding API meets that directly, and
  providers reversion models behind stable aliases. Produced vectors must be
  stored as immutable content-hashed artifacts bound into canonical identity, so
  a rebuild replays bytes instead of re-calling the provider.
- **Rights bind the processor.** A current Phase 4A `embedding` rights decision
  authorizes a named processor. Sending the same source text to a second
  provider is a distinct disclosure and needs its own decision.
- **Cost.** Each provider needs its own pinned `PricingSnapshot`. Embedding
  models are input-token-only, which the general request/response cost shape
  does not express.

Multiple providers also unlock something currently unreachable.
`VerifierIndependence.different_provider` is a component of full verifier
independence, and `src/math_research/phase2/live_gate.py` raises if a
same-provider run claims it. A single-provider deployment can never report
`fully_independent`.

## Phase 1 manual trust core

Phase 1 provides frozen typed entities, opaque IDs, append-only in-memory
repositories/events, policy-projected trust status, a separate canonical JSON
interchange mapper, proposal-only external import, five adversarial scenario
fixtures, and a manual CLI. The demo writes a hash-stable dossier, re-imports
it, and renders an ID-traceable report under `reports/phase-1/`.

No database, ORM, network call, crawler, model, formal tool, worker, web UI,
multi-agent orchestration, novelty/significance automation, or quantum solver
is included.

## Phase 2 durable baseline loop

Phase 2 preserves the Phase 1 trust core and adds a local SQLite adapter behind
ports, checksum-protected migrations, append-only semantic events, leased and
idempotent jobs, persisted budgets, a content-addressed filesystem store, one
provider-neutral proposer/verifier loop, and one bounded filesystem/process
backend. The deterministic scripted model adapter is the offline acceptance
path. The opt-in OpenAI Responses adapter reads only `OPENAI_API_KEY` from the
process environment or the ignored repository-root `.env` file and uses the
separately pinned provider SDK. Canonical output schemas are deterministically
projected into the documented OpenAI Structured Outputs subset before budget
reservation. Provider-only scalar `const` and `enum` terminals receive
deterministically inferred explicit types with a manifest entry; ambiguous or
conflicting terminals fail local preflight. Every response is still validated
against the unchanged canonical schema before trust checks or proposal import.
Provider/model selection is an explicit content-hashed run configuration, and
cost estimates use an explicitly created, versioned pricing snapshot; a research
run never fetches pricing. Exact fields and commands are documented in
`docs/phase-2/LIVE_PROVIDER_GATE.md`.

The verifier receives an exact canonical context whose manifest records all
included/excluded IDs and the serialized-context hash. Proposer commentary and
self-ratings are excluded. Every model/backend result remains a proposal; the
workflow never creates an accepted warrant or changes the durable dossier.

The minimal durable CLI is available below `math_research.cli phase2`; use
`--help` to list start/advance, job/budget, pause/resume, artifact/manifest,
review, export, timeline, and report commands. Phase 2 intentionally contains
no retrieval, formal or symbolic tool, web/API surface, multi-agent search,
quantum solver, or automated novelty/significance assessment.

## Phase 3A bounded research memory

Phase 3A adds only a manually supplied, local research-memory vertical slice.
Supported content is UTF-8 plain text parsed by the internal, versioned
`plain-text-v1` parser. Immutable source bytes, source versions, normalized
documents, exact byte spans, source-derived evidence proposals, deterministic
FTS5/BM25 retrieval manifests, bounded evidence packs, and citation validation
remain separate from model-proposed claims and Phase 1 trust warrants.

Metadata-only URI records are opaque user-supplied locators. They receive local
syntax validation only, have no content hash, remain unresolved, and cannot
produce evidence. Phase 3A performs no DNS, HTTP, redirect, availability, or
content check. PDFs and other unsupported media are quarantined without
extraction. The quantum paper is metadata-only until licensed local content is
available; acceptance uses project-authored synthetic sources.

There are no network, model, or external API calls, crawler, embeddings,
embedding-provider port, PDF parser, formal-tool integration, or Phase 3B/4
features in this phase. Retrieval acceptance and the roadmap transition are
frozen in ADR-0013, ADR-0014, and `docs/phase-3/`.

## Phase 3B bounded Lean formal checking

The first Phase 3B production slice accepts one versioned restricted theorem
and proof-fragment request. A fail-closed validator rejects arbitrary Lean
files, unknown imports, placeholders, undeclared axioms, evaluation and native
features, package commands, and side-effect APIs. The trusted wrapper and its
statement, declaration, imports, invocation, policy, runtime, and source are
hashed before only the wrapper bytes are sent on stdin to the exact ADR-0016 v5
image. No host path or mount is exposed to the container.

The adapter bounds time and streamed output, retains full-stream hashes and
lengths with bounded diagnostics, removes its container, persists every result
append-only, and supports canonical export/replay and CLI inspection. Kernel
checking is scoped only to the exact hashes and disclosed assumptions. Every
result remains a proposal: it cannot approve semantic alignment, source
applicability, novelty, significance, contribution, or create an
`EpistemicWarrant`. Meaning tests are diagnostic only.

Formal finding IDs and semantic content hashes exclude recorded timestamps and
measured elapsed milliseconds. For forced timeout/output-limit termination,
they also exclude race-dependent exit and partial-stream observations that occur
after the classification boundary. All excluded values remain present in
exported operational metadata and are covered by a separate operational hash.
This prevents runtime scheduling variance from changing semantic replay identity
without discarding or leaving operational metadata unaudited. Completed-checker
exit codes and full stream hashes remain semantic inputs. Legacy full-record
Phase 3B exports remain importable under their implicit original hash profile.

This slice adds no model/API call, network acquisition, proof search or repair,
premise retrieval, Why3/SMT/CAS/numerical adapter, web surface, broader Phase 3B
workflow, Phase 4 feature, or quantum implementation.

## Phase 4B authorized acquisition and exact parsing

Phase 4B adds an explicit-human, exact-origin HTTPS acquisition port over the
Phase 4A rights and deletable-content boundary. Network remains off by default;
terms, robots, acquisition rights, retention rights, DNS answers, connected
peers, redirects, headers, content type, and all byte/time budgets fail closed.

Dependency-free strict HTML, non-expanding TeX, and narrow born-digital PDF
parsers preserve exact source-byte anchors and return untrusted proposals only.
Production parsing requires the digest-pinned OCI runtime in
`config/phase4b-oci-image-linux-arm64-v1.json`; it runs stdin-only with no
network or host mounts, a read-only root, non-root identity, bounded noexec
temporary storage, and kernel-enforced memory, CPU, process, and file limits.
The ordinary offline suite never pulls or requires this image.

Run the separately configured parser gate:

```bash
make check-phase4b-oci
```

The offline acquisition/parsing metadata path is part of `make check`. The
strict OCI parser gate has passed; the separately acknowledged live HTTPS gate
is the final activation step, and its absence must never be counted as a pass.
See `docs/phase-4b/` and ADR-0028 for the frozen gate package.

## Phase 5 exact adaptive quantum benchmark

Phase 5 provides a restart-safe exact commuting/diagonal implementation of the
normalization-corrected JRF iteration. It runs the frozen boundary
counterexample and componentwise-full-support `QD-FS-01` fixtures, checks POVM
feasibility and objective monotonicity in rational arithmetic, and compares the
trajectory with an independent exact diagonal primal/dual optimum certificate.
The workflow requires a falsification branch, records priorities and duplicate
dead ends, retains all checked findings, and keeps search tiers 2--4 disabled
until a cost-adjusted gain is measured.

The exact boundary result is surfaced through the bounded local
material-partial-result event stream and can be steered by an authorized human.
Checked results remain distinct from graph admission, semantic alignment, source
applicability, and stronger mathematical warrants. ADR-0023 freezes this slice.

```bash
phase5_root="$(mktemp -d /tmp/adaivy-phase5.XXXXXX)"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase5 run \
  "$phase5_root/workspace" fixtures/phase5/quantum-diagonal-v1.json \
  2026-08-20T12:00:00Z --output "$phase5_root/run.json"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase5 list-results \
  "$phase5_root/workspace"
```

The timestamp is an explicit input rather than `date` output because the
acceptance paths are byte-reproducible; the `Makefile` pins the same instants as
`PHASE5_INSTANT` and `PHASE6_INSTANT`.

## Phase 6 confirmatory evaluation and release

Phase 6 freezes the held-out case, exact method, metrics, capability allowlist,
success criteria, and stopping rule before execution. Its one-pass evaluator
can see only the preregistered case and cannot adapt after observing the
outcome. It consumes the persisted Phase 5 run and material event, executes the
five generality trust controls, records novelty and significance as separate
unassessed dimensions, attributes contributions, and writes a canonical
restart-safe release package plus a traceable report.
ADR-0024 freezes this slice and its explicit limitations.

Run the complete offline Phase 5 → Phase 6 workflow:

```bash
phase6_root="$(mktemp -d /tmp/adaivy-phase6.XXXXXX)"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase6 demo \
  "$phase6_root/workspace" fixtures/phase6/confirmatory-protocol-v1.json \
  fixtures/phase5/quantum-diagonal-v1.json \
  2026-08-20T12:00:00Z 2026-08-20T14:00:00Z \
  --output-dir "$phase6_root/output"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase6 inspect \
  "$phase6_root/output/phase6-export.json"
```

## Bounded exploratory synthesis

The synthesis slice implements the ADR-0025 contract in
`docs/phase-4/EXPLORATORY_RESEARCH_SYNTHESIS_V1.md`, frozen by ADR-0027. It
layers over the sealed Phase 6 workspace and keeps every earlier boundary
intact.

Every structured result and relation carries four independent state axes ---
source applicability, extraction fidelity, mathematical warrant, and graph
admission --- and no value on one axis implies a value on another. Warrant
states are not ordered, so admission policy evaluates an explicit permitted set
rather than a threshold. A relation never inherits an endpoint's states.

Each run validates fifteen finite bounds before it begins, charges a named
counter before every loop body, and ends with exactly one terminal reason. The
exploration reserve is enforceable rather than advisory: at least
`ceil(B * numerator / denominator)` branch-generation attempts go to eligible
non-incumbent strategy families, and a waiver is admissible only when fewer than
two families are eligible and every evaluated family is named with its exclusion
reason.

Retrieval is bounded and genuinely multi-hop over the unmodified Phase 3A
FTS5/BM25 index: one top-k query cannot satisfy the acceptance corpus, in which
one source is reachable only by citation traversal and another only by declared
terminology expansion. Composition compares thirteen dimensions before any
composition is proposed, and every mismatch opens an obligation. Bridge
candidates are locally minimal only when no enumerated proper subset permits the
same composition, and search noncoverage is recorded as `search_incomplete` or
`not_found_under_protocol`, never as novelty.

Influence closure is transitive and append-only. Fourteen lifecycle and rights
triggers invalidate every influenced extraction, relation, admission, branch,
synthesis proposal, bridge candidate, verification input, and surfaced
partial-result view, then rebuild the current view deterministically; original
records stay immutable and addressable. Nondeterministic generation is captured
once and replay never calls a generator.

This slice adds no crawler, network access, parser, embedding model, vector
database, result extractor, theorem prover, model call, dependency, or
noncommuting quantum implementation.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli synthesis \
  validate-budget fixtures/synthesis/budget-policy-v1.json
```

Two capabilities it supplies are boundaries rather than fixes. Phase 4A has no
effective-applicability resolver, so `synthesis/applicability.py` defines one and
fails closed on a forked supersession chain. Sealed Phase 5 accepts an identical
originating and creating principal, so the separation-of-duty check in
`synthesis/material.py` applies only to that module's surfacing path.

## Intended repository layout

The blueprint's target layout for the implementation repository is below. It is
the intended destination, not a description of the current tree; the README
documents the layout as it exists today.

```text
math-research-system/
├── README.md
├── TECHNICAL_BLUEPRINT.md
├── AGENTS.md
├── pyproject.toml
├── src/math_research/
│   ├── domain/             # Core entities and state transitions
│   ├── application/        # Use cases and orchestration
│   ├── ports/              # Stable interfaces
│   ├── adapters/           # Models, storage, retrieval, tools, research systems
│   ├── workers/            # Durable job execution
│   ├── api/                # HTTP/CLI entry points
│   └── observability/      # Events, metrics, traces, and audit records
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── property/
│   ├── adversarial/
│   └── evaluations/
├── benchmarks/
│   └── quantum_discrimination/
├── prompts/                # Versioned prompt templates and schemas
├── migrations/
└── infra/
```

`AGENTS.md` was listed as an intended file for the implementation repository; it
was to be created during Phase 0 with project-specific Codex instructions, and
now exists at the repository root.

## Suggested implementation defaults

- Python for orchestration and mathematical tooling
- Pydantic-style schemas at every model and tool boundary
- PostgreSQL as the transactional source of truth
- Object storage for source documents and generated artifacts
- Hybrid lexical, semantic, formula, and graph retrieval
- A durable worker abstraction with idempotent jobs
- Sandboxed tool execution with explicit resource and network policies
- A provider-neutral model gateway; OpenAI Responses API support can be the
  first adapter
- A backend-neutral research-dossier interchange format
- OMDoc/MMT and Why3 concepts as design references rather than an invented
  universal mathematical syntax

These are defaults, not permanent constraints. Ports should make replacement
possible without changing domain logic.

## Definition of done for the first vertical slice

A user can create a problem, approve its formalization and semantic alignment,
open a hypothesis, attach and validate an applicable source-backed claim, run a
reproducible experiment under an evaluation protocol, create and close a proof
obligation, and generate a report whose statements can all be traced to evidence
and warrants.

The slice must also demonstrate that:

- an unsupported model claim cannot be marked proved;
- a formal proof of a mistranslated statement cannot resolve the user’s target;
- a real but inapplicable citation cannot close an obligation;
- an experiment cannot promote a universal theorem to proved;
- a transformed representation cannot be used without an open or discharged
  bridge obligation;
- rerunning the same tool job preserves provenance and does not duplicate state;
- an isolated verifier does not inherit the proposer’s narrative;
- a report distinguishes facts, assumptions, conjectures, unresolved gaps,
  novelty, significance, and contribution.

## Using this blueprint with Codex

Start implementation with a bounded request:

```text
Read README.md, TECHNICAL_BLUEPRINT.md, and NOVELTY_LANDSCAPE.md in full.
Implement Phase 0 only: the common reference dossier, a minimal capability
evaluation harness, the ResearchBackend interchange schema, ADR templates, and
reproducible adoption spikes for the named categories of existing systems. Do
not implement the production database, crawler, domain model, or multi-agent
orchestration yet. Record adopt/wrap/interoperate/build decisions and blockers
with evidence.
```

Then proceed phase by phase, keeping the test suite and architecture decisions
current. The blueprint deliberately avoids selecting a particular current model
name; choose models through configuration and capability checks rather than
hard-coding an alias.

## External references

- [RMA: Research Math Agents](https://arxiv.org/abs/2605.22875)
- [Aletheia](https://arxiv.org/abs/2602.10177)
- [MathGraph](https://www.mathgraph.org/)
- [Albilich](https://github.com/uw-math-ai/albilich)
- [AlphaProof Nexus](https://arxiv.org/abs/2605.22763)
- [OMDoc/MMT](https://docs.mathhub.info/legacy/omdoc-mmt.html)
- [Why3](https://why3.org/)
- [OpenAI Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [OpenAI background mode](https://developers.openai.com/api/docs/guides/background)
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI file search](https://developers.openai.com/api/docs/guides/tools-file-search)
- [First benchmark paper](https://arxiv.org/abs/quant-ph/0201109)
