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
- [`CAPABILITY_STATUS.md`](./CAPABILITY_STATUS.md) — canonical current runtime
  status.
- [`END_TO_END_RESEARCH_RUNTIME_PLAN.md`](./END_TO_END_RESEARCH_RUNTIME_PLAN.md)
  — proposed integration roadmap.
- [`AGENTS.md`](../AGENTS.md) — stable repository and engineering rules.
- [`docs/adrs/`](./adrs/) — architecture decision records. ADR-0012 records the
  accepted revision 0.3 delivery sequence while preserving the superseded
  roadmap history; ADR-0026 records the accepted delivery order for the work
  remaining after Phase 4B.

## Contents

- [What the system does](#what-the-system-does)
- [Architectural principles](#architectural-principles)
- [First benchmark](#first-benchmark)
- [Active build sequence](#active-build-sequence)
- [Offline repository checks](#offline-repository-checks)
- [Current campaign boundary](#current-campaign-boundary)
- [Multiple model providers, embeddings, and retrieval](#multiple-model-providers-embeddings-and-retrieval)
- [Phase 1 manual trust core](#phase-1-manual-trust-core)
- [Phase 2 durable baseline loop](#phase-2-durable-baseline-loop)
- [Phase 3A bounded research memory](#phase-3a-bounded-research-memory)
- [Phase 3B bounded Lean formal checking](#phase-3b-bounded-lean-formal-checking)
- [Phase 4B authorized acquisition and exact parsing](#phase-4b-authorized-acquisition-and-exact-parsing)
- [Phase 4D grounded public scholarly discovery](#phase-4d-grounded-public-scholarly-discovery)
- [Two mandatory novelty checkpoints](#two-mandatory-novelty-checkpoints)
- [Phase 5 exact adaptive quantum benchmark](#phase-5-exact-adaptive-quantum-benchmark)
- [Phase 6 confirmatory evaluation and release](#phase-6-confirmatory-evaluation-and-release)
- [Bounded exploratory synthesis](#bounded-exploratory-synthesis)
- [Intended repository layout](#intended-repository-layout)
- [Suggested implementation defaults](#suggested-implementation-defaults)
- [Definition of done for the first vertical slice](#definition-of-done-for-the-first-vertical-slice)
- [Using this blueprint with Codex](#using-this-blueprint-with-codex)
- [External references](#external-references)

## What the system is designed to do

The following is the target architecture. It is not yet one connected operator
workflow; the exact implemented and wired state is maintained in
[`CAPABILITY_STATUS.md`](./CAPABILITY_STATUS.md).

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

## Active build sequence

Phases 0–6 supplied the bounded components and trust boundaries. The active
work is now integration, in the order defined by
[`END_TO_END_RESEARCH_RUNTIME_PLAN.md`](./END_TO_END_RESEARCH_RUNTIME_PLAN.md):

1. approve the superseding activation ADR and establish a truthful capability
   matrix;
2. bind every internal model and embedding call to an explicit AdaIvy
   credential profile and unified budget;
3. make the corpus durable and reusable across campaigns;
4. run semantic and lexical retrieval over real corpus generations;
5. add campaign-native literature discovery, acquisition, embedding, and
   retrieval actions;
6. wire the activated experiment sandbox and verifier router, including Lean;
7. expose one resumable operator command; and
8. complete documentation and historical-status cleanup.

Until those slices land, a passing component gate must not be described as an
end-to-end research run.

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

It runs the unit, integration, property, and adversarial suite plus the phase,
embedding, corpus, campaign, synthesis, and publication offline acceptance
paths. `make help` lists every target.

Targets that need more than that are named for what they need.
`make check-gate PY=/path/to/gate-venv/bin/python` requires the disposable
pinned Draft 2020-12 validator environment described in
`docs/phase-4/DEPENDENCY_LICENSE_ASSESSMENT.md`; gate tests skip
themselves unless that validator is importable, so the target refuses to run
rather than reporting a silent pass. `make check-sealed` covers Phase 3B.
`make check-phase4b-oci` and `make check-campaign-experiment-oci` exercise their
digest-pinned sandboxes. `make check-embedding-live` is the explicit credentialed
embedding path. `make check-all` runs the offline check and sealed Lean runtime.

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

## Current campaign boundary

The bounded campaign entrypoint can run a live central model lead through the
AdaIvy gateway and record its actions, usage, cost, and artifacts. It cannot
currently perform the target product workflow:

- its action schema contains no literature search, acquisition, embedding,
  index-refresh, or retrieval action;
- `campaign run` wires the activated ADR-0066 OCI runner only when
  `--experiment-activation` supplies a record that re-verifies against the
  current image locks (ADR-0072); otherwise the pending runner remains with the
  reason recorded, and generated source is never executed;
- `verify` dispatches through the isolated `CampaignVerifierRouter` (exact
  graph, Phase 5 exact domains, and a Phase 3B formal-check port); a candidate
  no route admits is an explicit `unsupported` failure;
- the sealed Phase 3B Lean adapter is an explicit opt-in
  (`--formal-check-adapter sealed`); the offline default records a
  machine-readable missing-tool outcome; and
- a fresh human `before_research` novelty record is still required by ADR-0055.

The end-to-end plan changes these boundaries through a superseding ADR. Until
then, host Codex or Claude work remains an explicit external import rather than
AdaIvy campaign discovery.

## Multiple model providers, embeddings, and retrieval

Generation, embedding ingestion, and retrieval are separate boundaries. The
separation is intentional, but they are not yet orchestrated by the campaign.

What holds today:

- Phase 3A provides SQLite FTS5/BM25 retrieval. Phase 4C adds aliases,
  evidentiary-disclaimer exclusion, and an exact semantic signal over replayed
  vector artifacts. The four-signal benchmark remains frozen at 19 synthetic
  documents and 17 queries.
- There is an embedding-provider port and an exact vector artifact store.
  ADR-0064 makes `RightsUse.EMBEDDING` reachable: a rights
  decision now names the processor that receives the text, so authorizing the
  *use* no longer leaves the *recipient* unstated. ADR-0069 adds
  `src/math_research/embedding/` -- a sibling `EmbeddingGateway`, exact integer
  coordinates quantized once at ingestion, and content-hashed artifacts
  partitioned by `(provider, model_identifier, dimension, normalization)`. A
  rebuild replays those bytes and never re-calls the provider, so the read path
  has no provider, no credential, and no network surface.
- ADR-0070 is implemented: Phase 4C consumes a replayed semantic partition and
  its gates pass. It does not consume ADR-0067 corpus records or arbitrary live
  embedding partitions. The only Phase 4C vectors are project-authored fixture
  vectors and provide no evidence about real embedding quality. There is no
  approximate-nearest-neighbour index; similarity uses an exact linear scan.
- Bounded multi-hop query expansion is deterministic. Terminology, notation,
  citation, and contrasting-approach queries in
  `src/math_research/synthesis/retrieval.py` derive from indexed record terms,
  never from a model, so a retrieval trace and its canonical hash do not vary
  with which provider produced a proposal.
- The live model gateway has bounded OpenAI, Azure OpenAI, Anthropic, Bedrock,
  DeepSeek, MiniMax, and Qwen/DashScope adapters. Embedding ingestion supports
  OpenAI and Azure OpenAI through its sibling port. A configured component does
  not imply the campaign selected it, so every live route remains explicit and
  content-hashed.

The load-bearing rules are:

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

ADR-0040 adds bounded proof-fragment repair above that unchanged checker, and
ADR-0048 supplies an opt-in Azure OpenAI implementation of its narrow proposer
port. Only `elaboration_failure` is fed back; the model can return only a proof
fragment and cannot change the declaration, target, imports, assumptions,
claim identity, or meaning tests. Every repaired attempt remains a proposal and
creates no warrant.

The preflight is offline and reports missing variable names, never values:

```bash
PYTHONPATH=src python3 -m math_research.cli phase3b repair-live-preflight \
  --config config/phase3b-live-azure-openai-v1.json \
  --pricing-snapshot config/azure-openai-gpt5-6-sol-pricing-2026-08-21.json
```

Execution additionally requires the ADR-0016 v5 image and the explicit
`--execute` acknowledgement:

```bash
PYTHONPATH=src python3 -m math_research.cli phase3b repair-live REQUEST.json \
  --workspace WORKSPACE --created-at 2026-08-21T00:00:00Z --execute \
  --config config/phase3b-live-azure-openai-v1.json \
  --pricing-snapshot config/azure-openai-gpt5-6-sol-pricing-2026-08-21.json
```

The offline `make check` path never runs that command and never opens a socket.
Premise retrieval, Why3/SMT/CAS/numerical adapters, a web surface, and broader
Phase 3B workflow remain outside this slice.

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
strict OCI parser gate and separately acknowledged live HTTPS gate have passed.
ADR-0050 activates only public unauthenticated acquisition of one exact URL per
invocation. Network remains off by default; URL query strings, credentials,
caller-supplied request headers, redirects, retries, crawling, autonomous
origin selection, and scheduled acquisition are not enabled.

Validate a plan without opening a socket or creating a workspace:

```bash
PYTHONPATH=src python3 -m math_research.cli phase4b public-acquire \
  work/public-source source.public.example PLAN.json \
  --activation config/phase4b-public-acquisition-activation-v1.json \
  --activation-evidence reports/phase-4b-activation/activation-evidence.json
```

Execution additionally requires `--execute`,
`--confirm-live-network I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK`, and
`--confirm-plan-hash` equal to the verified plan hash printed by the dry run.
The plan must contain current human-reviewed terms, robots, acquisition-right,
and storage/retention-right snapshots. Public reachability is not treated as a
licence or as permission to redistribute. At execution the plan timestamp must
be within five minutes of the system clock, preventing an old terms/robots
snapshot from remaining executable indefinitely. See `docs/phase-4b/`,
ADR-0028 and ADR-0050.

## Phase 4D grounded public scholarly discovery

ADR-0051 adds a deliberately separate discovery surface. The operator supplies
terms and a local UTF-8 problem/context file; every term must occur in that file
after NFKC normalization and case folding. A dry run hashes that grounding and
prints the exact query hash without DNS or HTTPS.

Live execution requires the operator identity, the acknowledgement
`I_ACKNOWLEDGE_PUBLIC_WEB_DISCOVERY`, and that exact query hash. It makes one
public unauthenticated request to the pinned Crossref origin, with at most ten
results, twelve terms, 256 query bytes, a 1 MiB response, and fifteen seconds.
The provider-terms review expires after thirty days. The Phase 4B opt-in
resolver and HTTPS transport retain public-address, connected-peer, TLS, header,
body, and deadline controls.

```bash
PYTHONPATH=src python3 -m math_research.cli phase4d search PROBLEM.txt \
  --term 'quantum state discrimination' --term 'spectral projector' \
  --config config/phase4d-crossref-public-discovery-v1.json
```

Repeat with `--execute --actor-id ACTOR`,
`--confirm-live-network I_ACKNOWLEDGE_PUBLIC_WEB_DISCOVERY`, and
`--confirm-query-hash` equal to the dry-run value to perform the request.
Returned DOI metadata is an `untrusted_inspiration_candidate`; it has no
relevance or applicability decision, no acquisition authorization, no novelty
or significance assessment, and no mathematical warrant. Phase 4D never opens
the DOI URL. Acquiring a selected work remains a separate ADR-0050 Phase 4B
operation with its own terms, robots, and rights evidence.

## Two mandatory novelty checkpoints

ADR-0055 turns novelty review into a fail-closed lifecycle rule without turning
search into a novelty oracle. Before a supplied problem may start a Phase 2 run
or bounded central-lead session, a human creates a `before_research` record
bound to the exact dossier content hash and run/session identifier. The runtime
persists it immediately before the first research action. Before any result can
receive non-null `publication_approval`, a second human
`before_announcement` record must bind every exact claim statement and the
approval identifier, and link to the first record by identifier and hash.

Both records must strictly precede their actions by no more than 24 hours. Each
names its protocol, query terms, searched sources, equivalent-formulation
checks, evidence hashes, observed outcome, and limitations. Use the CLI to
create or inspect the canonical record:

```bash
PYTHONPATH=src python3 -m math_research.cli novelty create before_research \
  PROBLEM_ID sha256:DOSSIER_HASH RUN_ID HUMAN_ID 2026-08-21T00:00:00Z \
  work/novelty-before-research.json \
  --recheck-id RECHECK_ID --protocol-id PROTOCOL_ID \
  --query-term TERM --searched-source SOURCE \
  --equivalence-check EQUIVALENT_FORMULATIONS_REVIEWED \
  --evidence-ref EVIDENCE_ID sha256:EVIDENCE_HASH \
  --prior-art-relationship unresolved --prior-resolution unresolved \
  --prior-resolution-verification unresolved \
  --outcome inconclusive --limitation COVERAGE_LIMIT
```

Pass that file to `phase2 start --novelty-recheck ...` or `runtime run
--novelty-recheck ...`. The announcement-side record uses the same command with
`before_announcement` plus the first record's ID and hash, and is stored inside
the approval-bearing manuscript. `prior_art_found`,
`not_found_under_protocol`, and `inconclusive` are observations only. None
changes the manuscript's `novelty: not_assessed`, creates warrant, or authorizes
network access. Phase 4D output can be referenced as evidence after human
review, but does not satisfy the checkpoint by itself.

## Automatic solved-result publication reports

ADR-0071 also wires a narrower automatic report into the campaign entrypoint.
After its terminal ledger is durable, `campaign run` writes
`publication-draft/paper.tex`, its record ledger, and `MANIFEST.json`. This is a
claim-free status draft because the current campaign export does not yet carry
the typed claim and evidence records needed for a mathematical paper. It is
unapproved, creates no warrant, and stays `not_typeset` on the offline path.

```bash
PYTHONPATH=src python3 -m math_research.cli campaign resume CAMPAIGN_ROOT
```

That command verifies an existing terminal campaign and finishes or verifies
the deterministic draft with zero provider, network, tool, or subprocess work.
It does not resume a partially executed paid campaign; safe mid-run continuation
still needs append-only per-action checkpoints and paid-request intent records.

ADR-0056 makes the record-to-paper path atomic for every reader-facing report
that contains a solved mathematical claim. With the pinned typesetter installed,
the supported command is:

```bash
PYTHONPATH=src PATH="$PWD/work/toolchains/basictex-2026.0301/bin/universal-darwin:$PATH" \
  python3 -m math_research.cli publication build MANUSCRIPT.json --output-dir BUNDLE \
  --campaign-export CAMPAIGN.json --campaign-link PUBLICATION-CAMPAIGN-LINK.json
```

One invocation validates the manuscript and its falsifiability probes, projects
the frozen classic LaTeX template, emits each linked Lean artifact, performs two
clean offline `-no-shell-escape` compiles, compares the PDF bytes, and verifies
the completed manifest. The destination must be fresh. `publication render`
and `publication typeset` remain lower-level diagnostics; diagnostic phase JSON
and Markdown reports are not publication papers.

ADR-0057 adds the provenance-closed campaign boundary above the earlier
text-only central-lead runtime. One AdaIvy gateway-backed lead emits one typed
action per call: derive, write a bounded program, run a previously recorded
program, inspect the byte-exact result, select, verify, suspend, ask, or report.
The orchestrator rejects unknown tools, host paths, network, environment fields,
and excessive resources before calling the injected experiment runner. The
provider activation request uses the same gateway and counts against the same
attempt/token/cost budget. ADR-0066 activates model-authored program execution
only for the bounded exact-graph campaign target after its dedicated
digest-pinned Linux/arm64 OCI gate passes. Output remains an untrusted candidate
until the isolated exact verifier re-derives it; the offline suite continues to
use a zero-process scripted runner.

Those component capabilities are not yet the behavior of the operator
entrypoint. `campaign run` currently injects its earlier pending runner and
absent verifier, so it cannot execute the ADR-0066 sandbox or complete a
verification. This distinction is recorded in
[`CAPABILITY_STATUS.md`](./CAPABILITY_STATUS.md) and is the subject of Slice 6
of the end-to-end runtime plan.

For an AI-authored solved claim, `publication build` requires both campaign
files. It re-verifies semantic and operational hashes, closes each claim and
certificate to its producing actions/artifacts, derives origin and accounting,
and then replaces manuscript-authored attribution and usage fields. External
Codex work stays external; failed and incomplete calls remain counted; cost is
explicitly an estimate from pinned pricing rather than provider billing.

For `prior_art_found`, the operator also records the relationship to the target,
the earlier resolution kind, and whether that resolution was independently
verified. AdaIvy derives rather than accepts the report role and target status.
The Graffiti 197 regression must produce `independent_verification` and
`already_refuted`; runtime reports, approval-bearing manuscript status blocks,
and `records/prior-art.json` all expose those values. A mere source report is
limited to `reported_proved`, `reported_refuted`, or
`reported_resolved_other`, while general novelty remains `not_assessed`.

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

ADR-0049 additionally provides a genuine but deliberately narrow exact solver
for two-outcome, two-dimensional ensembles. It constructs the Helstrom spectral
projector and matching dual operator over one measured quadratic extension,
then submits both to the same exact feasibility, weak-duality, zero-gap, and
two-sided-complementarity checker used for supplied certificates. Construction
does not confer warrant; only that independent exact check can accept the
candidate. Dimension three, three or more outcomes, mixed quadratic fields, and
higher-degree optima remain explicit unresolved outcomes. The solver uses no
float, tolerance, model, network, or numerical engine and does not enable search
tiers 2--4.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase5 \
  solve-noncommuting fixtures/phase5/noncommuting-certificates-v1.json \
  --output /tmp/adaivy-phase5-solver.json
```

## Phase 6 confirmatory evaluation and release

Phase 6 freezes the held-out case, exact method, metrics, capability allowlist,
success criteria, and stopping rule before execution. Its one-pass evaluator
can see only the preregistered case and cannot adapt after observing the
outcome, because `HeldOutView` drops every non-frozen case before execution and
records a durable `heldout_access_violation` for any other request. It consumes
the persisted Phase 5 run and material event, executes the Section 18.4
generality control suite, records novelty and significance as separate unassessed
dimensions, attributes contributions, and writes a canonical restart-safe release
package plus a traceable report.
ADR-0024 freezes this slice and its explicit limitations; ADR-0034 replaces its
declarative five-control table with the executed suite.

The suite is a content-hashed manifest at
`fixtures/phase6/generality/generality-controls-v1.json` whose `suite_id` and
`canonical_hash` are pinned by `generality_suite_id`/`generality_suite_hash` in
the confirmatory protocol and verified before the first durable write, so the
suite cannot be edited after a failing run. Thirteen controls execute against
Phase 1 `TrustPolicy`, the exact Phase 5 diagonal engine, or the Phase 6 held-out
boundary. Each carries one falsifiability probe: a named single-field mutation of
its own parameters that must both satisfy the probe's stated forbidden verdict and
break the control's expectation. Two release gates apply --
`controls_passed == controls_total` and `probes_flipped == probes_total` -- because
a control that cannot be made to fail proves nothing. Two controls are positive
(GC-01 known theorem, GC-09A plugin core contract), so a system that rejects
everything cannot score full marks.

The control corpus is `project_authored`, recorded as such in the manifest, the
durable `generality_control_suite` record, the release package and the report.
The suite demonstrates boundary enforcement on known traps; it is not evidence of
generality against unseen traps. `baseline_comparison` reports eleven enforced
trust boundaries against a baseline of zero and carries
`is_generality_measure: false`; that count is not a generality rate.

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

### Ingest versus verification

`phase6 replay` and `phase6 verify` are deliberately separate commands, because
they make very different claims.

`replay` **ingests** an export into a workspace. It checks only that the envelope
is self-consistent — the declared `content_hash` equals the hash of the envelope
minus that key — and stores the blob in `phase6_verified_exports`. It does not
re-derive anything inside the envelope, and `verify_integrity` does not read that
table, so a workspace holding an ingested export still reports itself intact
regardless of what the export contains.

`verify` (ADR-0044) is the clean-room re-derivation. It reads only its own
temporary copies of the three inputs, re-derives every record `content_hash` and
`record_id`, the protocol guards, the release hash and identity, the Phase 5
bindings, and the held-out case itself via `run_case`, and refuses anything it
cannot reproduce. It writes nothing anywhere and adds no row to any table.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase5 export \
  "$phase6_root/workspace" "$phase6_root/output/phase5-export.json"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m math_research.cli phase6 verify \
  "$phase6_root/output/phase6-export.json" \
  "$phase6_root/output/phase5-export.json" \
  fixtures/phase5/quantum-diagonal-v1.json
```

The verdict separates what was checked from what was not, in two distinct
categories. `unverifiable` names claims about facts outside the system's view:
`semantic_fidelity` and `negative_and_superseded_attempts_retained`.
`not_derived` names the `baseline_comparison` block and its
`simplest_baseline_passed` operand. The Phase 6 operand is now re-derived by
re-executing all thirteen controls and probes, including two positive controls;
the named `arithmetic_only_without_trust_controls` baseline is still not
executed. The block therefore counts enforced boundaries and must not be read as
a generality rate. Nothing in either named-gap list is counted toward `verified`.

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
