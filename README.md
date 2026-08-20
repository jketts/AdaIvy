# Math Research System

A verification-first platform for using language models, literature retrieval,
symbolic computation, numerical experiments, and formal tools to investigate
mathematical research problems.

The system is not a chatbot with a large context window. Its central state is a
versioned graph of problems, semantic alignments, claims, representations,
evidence, hypotheses, experiments, and proof obligations. Model output is
treated as a proposal until an applicable verifier grants a precisely scoped
warrant.

> Status: Phases 0--4A are preserved; the bounded Phase 5 exact commuting
> quantum benchmark and Phase 6 local confirmatory/release slice are
> implemented. Noncommuting SDP, higher adaptive-search tiers, broader Phase 4
> acquisition, and external evaluation remain deferred.
> See
> [TECHNICAL_BLUEPRINT.md](./TECHNICAL_BLUEPRINT.md) for the build contract and
> [NOVELTY_LANDSCAPE.md](./NOVELTY_LANDSCAPE.md) for the prior-art review that
> informed architecture revision 0.2. ADR-0012 records the accepted revision
> 0.3 delivery sequence while preserving the superseded roadmap history.

## Why this exists

Ordinary chat-based research has predictable failure modes:

- assumptions disappear as a discussion grows;
- a plausible derivation is mistaken for a proof;
- citations are detached from the exact claims they support;
- real citations are used under incompatible hypotheses or definitions;
- computational evidence is reported as a universal result;
- equivalent-looking reformulations are used without proving equivalence;
- a proof assistant verifies a statement that does not mean what the researcher
  intended;
- failed approaches are forgotten and repeated;
- generated summaries contaminate the trusted source corpus.

This project makes those boundaries explicit and machine-checkable.

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

## Core rule

No model-generated claim becomes trusted merely because another model agrees
with it.

A claim is promoted only through explicit evidence and an applicable verifier.
Retrieval supports reasoning; it does not establish truth. Experiments can
refute universal claims and support conjectures; they do not replace proof.

Formal validity, semantic fidelity, literature novelty, mathematical
significance, and human/model/tool contribution are recorded separately. None
is inferred from another.

## High-level architecture

```mermaid
flowchart TD
    A["Research question"] --> B["Formalization"]
    B --> C["Research orchestrator"]
    D["Sources"] --> E["Evidence substrate"]
    E --> C
    C --> F["Hypothesis branches"]
    F --> G["Mathematical tool gateway"]
    F --> J["External research backends"]
    G --> H["Verification pipeline"]
    J --> H
    H -->|"gap or refutation"| C
    H -->|"verified result"| I["Research report"]
```

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
- **Measured orchestration:** begin with a simple proposer–verifier loop and add
  parallel or evolutionary search only when evaluation shows a gain.
- **Evaluation integrity:** confirmatory metrics, data, and stopping rules are
  frozen before held-out execution.
- **Human authority:** the user controls the formal problem and publication of
  conclusions.

## Intended repository layout

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

`AGENTS.md` is shown as an intended file for the implementation repository; it
should be created during Phase 0 with project-specific Codex instructions.

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
7. **Adaptive search and benchmark:** branching and more complex agent regimes
   only where they beat the simple baseline.
8. **Confirmatory evaluation:** held-out tests, contribution reporting,
   clean-room replay, and release hardening.

Each phase has concrete exit criteria in the technical blueprint. Do not begin
with a broad crawler, custom graph platform, or multi-agent swarm. First measure
what existing components already provide and what gap remains.

## Offline repository checks

Phase 0 is implemented as a standard-library-only adoption/evaluation harness,
not as production platform code. Its canonical inputs and outputs are:

- `fixtures/phase0/reference-dossier.json`;
- `schemas/research-dossier.schema.json` and `schemas/backend-result.schema.json`;
- reproducible component spikes under `spikes/`;
- measured results under `reports/phase-0/`.

Run the complete offline check from the repository root. It has no third-party
runtime or development dependencies:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m phase0_harness.cli check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli demo --output-dir reports/phase-1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli inspect reports/phase-1/manual-dossier.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase2 report reports/phase-2 run.phase2.demo.fake.v1 --output reports/phase-2/traceable-report.md
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase3a demo reports/phase-3a/acceptance-v1 --output-dir reports/phase-3a/acceptance-v1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase3a inspect reports/phase-3a/acceptance-v1/research-memory.json
```

The bounded Phase 3B acceptance additionally requires the exact local image
sealed by ADR-0016. Run it only against a disposable workspace so the repository
and the Phase 3A acceptance state remain unchanged:

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
against the unchanged canonical schema before trust checks or proposal import. Provider/model
selection is an explicit content-hashed run configuration, and cost estimates
use an explicitly created, versioned pricing snapshot; a research run never
fetches pricing. Exact fields and commands are documented in
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
they also exclude
race-dependent exit and partial-stream observations that occur after the
classification boundary. All excluded values remain present in exported
operational metadata and are covered by a separate operational hash. This
prevents runtime scheduling variance from changing semantic replay identity
without discarding or leaving operational metadata unaudited. Completed-checker
exit codes and full stream hashes remain semantic inputs. Legacy full-record
Phase 3B exports remain importable under their implicit original hash profile.

This slice adds no model/API call, network acquisition, proof search or repair,
premise retrieval, Why3/SMT/CAS/numerical adapter, web surface, broader Phase 3B
workflow, Phase 4 feature, or quantum implementation.

## Phase 5 exact adaptive quantum benchmark

Phase 5 provides a restart-safe exact commuting/diagonal implementation of the
normalization-corrected JRF iteration. It runs the frozen boundary
counterexample and componentwise-full-support `QD-FS-01` fixtures, checks POVM
feasibility and objective monotonicity in rational arithmetic, and compares the
trajectory with an independent exact diagonal primal/dual optimum certificate.
The workflow requires a falsification branch, records priorities and duplicate
dead ends, retains all checked findings, and keeps search tiers 2--4 disabled
until a cost-adjusted gain is measured.

The exact boundary result is surfaced through the production material-partial-
result event stream and can be steered by an authorized human. Checked results
remain distinct from graph admission, semantic alignment, source
applicability, and stronger mathematical warrants.

```bash
phase5_root="$(mktemp -d /tmp/adaivy-phase5.XXXXXX)"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase5 run \
  "$phase5_root/workspace" fixtures/phase5/quantum-diagonal-v1.json \
  2026-08-20T12:00:00Z --output "$phase5_root/run.json"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase5 list-results \
  "$phase5_root/workspace"
```

## Phase 6 confirmatory evaluation and release

Phase 6 freezes the held-out case, exact method, metrics, capability allowlist,
success criteria, and stopping rule before execution. Its one-pass evaluator
can see only the preregistered case and cannot adapt after observing the
outcome. It consumes the persisted Phase 5 run and material event, executes the
five generality trust controls, records novelty and significance as separate
unassessed dimensions, attributes contributions, and writes a canonical
restart-safe release package plus a traceable report.

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

## References

- [Technical blueprint](./TECHNICAL_BLUEPRINT.md)
- [Prior-art and novelty landscape](./NOVELTY_LANDSCAPE.md)
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
