# Phase 4 Entry-Gate Report

Date: 2026-08-19

Status: **blocked before production implementation; a separate entry gate is
required**

## Outcome

The sealed Phase 3B baseline passed repository preflight, and the working branch
`codex/phase-4` was created from the verified Phase 3B target. Production Phase
4 implementation did not begin.

The authoritative roadmap defines Phase 4, but the repository has no accepted
Phase 4 specification, report, requirement matrix, threat model, dependency
lock, rights-approved corpus, frozen evaluation protocol, acceptance command,
or passed entry-gate evidence. Accepted ADRs also require explicit revisits
before a Phase 4 crawler, embedding boundary, research automation, PDF parsing,
or PaperQA2 integration. These are mandatory decisions rather than details an
implementer may infer.

The quantum-discrimination benchmark is Phase 5 under the current roadmap. No
quantum material was copied, merged, or modified.

## Repository preflight

| Check | Observed result |
|---|---|
| Repository | `/Users/joshuakettlewell/Documents/GitHub/AdaIvy` |
| Initial branch and upstream | `main`, `origin/main` |
| Current branch | `codex/phase-4`, created from the verified target; no upstream |
| Baseline commit | `226b47863f565c9c5a7dc7ac9ac08d490420ecf2` |
| Baseline tree | `5c300820521c0b83b7d19c644ca42f327ef21407` |
| `origin/main` after `git fetch origin main --tags` | `226b47863f565c9c5a7dc7ac9ac08d490420ecf2` |
| `phase-3b` tag object | `9c464ba2b93ec9c80e6fc95421f53e3b54c6ab4c` |
| Peeled `phase-3b` target | `226b47863f565c9c5a7dc7ac9ac08d490420ecf2` |
| Phase 3B evidence ancestor | `6945d8aa206d79c3dc0bd7d7a50aea662414b8e8`, confirmed ancestor |
| Initial worktree and index | clean, including untracked files |
| Remotes | one remote, `origin`, fetch/push `https://github.com/jketts/AdaIvy.git` |
| Existing annotated tags | `phase-2`, `phase-3a`, `phase-3b`; unchanged |

Only the root `AGENTS.md` applies. It was read before any file change. README,
`TECHNICAL_BLUEPRINT.md`, `NOVELTY_LANDSCAPE.md`, all current ADRs, recent
history, and Phase 0 through Phase 3B reports, roadmaps, handoffs, and deferred
work were inspected.

## Authority and conflict resolution

The repository does not state a general conflict-precedence algorithm. No
silent choice was needed here:

1. ADR-0012 explicitly supersedes the revision-0.2 delivery order while
   preserving its history.
2. README and architecture baseline 0.3 repeat ADR-0012's current order:
   Phase 3A research memory, Phase 3B formal grounding, Phase 4 broader
   acquisition and research automation, and Phase 5 adaptive search plus the
   quantum benchmark.
3. Accepted ADR-0003, ADR-0013, and ADR-0014 impose additional prerequisites on
   Phase 4 components and preserve the Phase 3A/3B trust boundaries.
4. The controlling task instruction requires an entry-gate report instead of
   implementation whenever Phase 4 is ambiguous or an entry gate is unpassed.

The broad objective is consistent across the current roadmap. What is absent is
an accepted, bounded production slice and its policies.

## Authoritative Phase 4 scope

### Objective

Broaden the local research-memory foundation into rights-aware source
acquisition and research automation while retaining exact provenance,
rebuildable indexes, explicit applicability review, and orthogonal trust
classifications.

### Required production capabilities

Architecture baseline 0.3 lists:

- licensed source acquisition, controlled crawling, and immutable archives;
- richer math-aware and PDF parsing;
- embeddings and hybrid lexical/semantic/formula/citation retrieval;
- evidence cards and source-applicability review;
- terminology and notation expansion, citation traversal, and bounded novelty
  assessment;
- source-injection and misquotation evaluations; and
- broader research automation plus the deferred embedding-provider boundary.

### Required entities and interfaces

The existing canonical source bytes, versions, normalized documents, exact
spans, evidence units, relations, packs, events, and ResearchMemoryExport remain
authoritative. Phase 4 must use or define the roadmap's `SourceAcquirer`,
`DocumentParser`, `RetrievalIndex`, `ArtifactStore`, `EventStore`, and relevant
repository ports without allowing adapter response objects into the domain.

Evidence cards must retain exact spans, imported statements, hypotheses,
definition mappings, and applicability obligations. Load-bearing use requires
a checked `SourceApplicabilityRecord`. Novelty work requires a reproducible
search protocol and a bounded `NoveltyAssessment`; it cannot prove absence of
prior art.

The current documents do not freeze the Phase 4 schema versions, migration,
command surface, adapter selection, or smallest entity subset. That is an entry
gate item.

### Security and trust boundaries

- Retrieved and parsed content is untrusted candidate data.
- Original content-addressed bytes remain authoritative; parser, embedding,
  reranker, and model-shaped outputs are derived proposals.
- Crawlers remain outside the trusted core and must obey access, license,
  version, failure-retention, deduplication, and rate policies.
- Acquisition credentials must be separated from checker and execution
  environments; secrets and network access remain absent by default.
- Every index is a rebuildable projection and cannot be canonical state.
- Applicability, formal validity, novelty, significance, and human review remain
  distinct records. No retrieval result, parser result, embedding score, model
  agreement, or formal checker result promotes another dimension automatically.
- The accepted Phase 3B stdin/container/Landlock/seccomp/non-root/read-only/
  no-network/resource-limit boundary must remain unchanged.

### Acceptance criteria

The roadmap requires:

- an exact source span and checked applicability record for every load-bearing
  imported theorem;
- necessary-lemma recall and applicability precision at frozen thresholds;
- reliable rejection of real but inapplicable citations;
- prevention of unsupported novelty claims when known results are renamed; and
- canonical state unchanged after index rebuilds.

The testing strategy additionally requires source acquisition through parsing
and retrieval, interrupted-workflow resume, malicious-source and misquotation
cases, incompatible-hypothesis rejection, notation-variant evaluation, citation
correctness, assumption preservation, contradiction retrieval, and exact
failure retention. The thresholds, corpus, repeat count, restart protocol, and
canonical comparison surface are not yet frozen.

### Explicit non-goals for the first bounded slice

- Phase 5 adaptive-search tiers or quantum-discrimination implementation;
- cloud deployment, multi-tenant operation, hidden services, or unrelated
  redesign of Phase 0 through Phase 3B;
- automatic promotion of retrieved, parsed, generated, or formally checked
  claims;
- a web/API surface, live AdaIvy model/provider calls, or secret-dependent
  acceptance unless separately authorized by a later accepted gate; and
- unrestricted crawling or importing source bytes without recorded rights.

### Dependencies on Phase 3A and Phase 3B

Phase 4 extends Phase 3A's immutable bytes, exact spans, quarantine, canonical
exports, deterministic FTS baseline, retrieval manifests, packs, and replay. It
must compare hybrid retrieval against that same lexical baseline on the same
fixtures and leave canonical memory independent of every index.

Phase 3B formal results remain separate from source applicability and statement
faithfulness. Phase 4 must consume formal-checker results only through the
accepted canonical boundary and may not weaken or replace its sealed runtime.

## Quantum-discrimination inventory

The separate worktree `/private/tmp/adaivy-quantum-discrimination` is on branch
`codex/quantum-discrimination-dossier` at
`b9c06d8fb42d690542cc23712c25fde8fe44ef50`. It is clean and contains two
branch-only commits, including tracked theorem-dossier and benchmark-statement
files. Its merge base with the sealed baseline is
`1342827a4ec9736e47cc20d32475b71100c68496`; the sealed `phase-3b` commit is not
its ancestor. It was inventoried only. It was not read into, copied to, merged
with, or otherwise imported by this branch.

This does not block Phase 4 because the current roadmap assigns the quantum
benchmark to Phase 5. It would block any future attempt to treat that worktree
as sealed-baseline Phase 4 input.

## Why the entry gate is blocked

The following decisions and evidence are mandatory and absent:

1. one smallest production slice selected from the broad Phase 4 roadmap;
2. accepted ADR(s) for that slice, including schema/migration compatibility;
3. source/corpus selection with version, license, redistribution, extraction,
   embedding, context-use, retention, and publication rights;
4. parser candidates compared against `plain-text-v1`, with pinned dependency
   graph, hashes, licenses, hostile-input containment, exact span mapping, and
   deterministic replay;
5. an explicit embedding decision: absent from the first slice or a pinned
   local boundary with model-weight/data licenses, offline execution, stable
   manifests, and measured comparison to FTS5;
6. an acquisition decision: local-only for the first slice or a separately
   authorized network boundary with allowlists, redirect/DNS/SSRF controls,
   robots/terms/rate policy, byte limits, credential isolation, and preserved
   failures;
7. accepted mappings for evidence cards, applicability review, citation
   traversal, terminology expansion, and novelty records;
8. a threat model covering malicious documents, parser exploits, archive
   traversal, decompression/resource abuse, prompt injection, source
   misquotation, index poisoning, and cross-project leakage;
9. frozen synthetic or rights-approved fixtures, negative controls, metrics,
   thresholds, repeat/restart protocol, and baseline comparison;
10. exact verification commands, clean-tree policy, and machine-readable gate
    schema.
11. resolution of the sealed Phase 3B export's cross-run canonical-hash defect:
    `elapsed_milliseconds` currently participates in finding IDs, finding
    hashes, export ordering, and the export hash.

Real external acquisition, live model/provider calls, a new high-privilege
runtime, or a materially expanded security boundary also requires separate
authorization under the controlling instruction.

## Verification evidence

All commands ran with `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=src`, and
`OPENAI_API_KEY` removed. Mutable demonstrations used unique directories below
`/private/tmp`; no tracked database, FTS projection, report, or build output was
regenerated.

| Check | Exit | Result |
|---|---:|---|
| `python3 -W error::ResourceWarning -m unittest discover -s tests -q` | 0 | 173/173 passed |
| `python3 -m phase0_harness.cli check` | 0 | 19/19 passed |
| Phase 1 disposable demo and inspect | 0 | round-trip hash preserved; dossier content hash `sha256:ee299e0a6d6295dd005f0292ab5b0ac89320862ed1853935ddc0da5d5b9f96fa` |
| Phase 2 offline report to `/private/tmp` | 0 | completed using the scripted offline baseline |
| Phase 3A disposable demo and inspect, run 1 | 0 | passed; zero API calls |
| Phase 3A disposable demo and inspect, run 2 | 0 | passed; zero API calls |
| Phase 3B disposable sealed-image demo and inspect, run 1 | 0 | all 9 outcomes passed; zero model/API calls; zero trust promotions |
| Phase 3B disposable sealed-image demo and inspect, run 2 | 0 | all 9 outcomes passed; zero model/API calls; zero trust promotions |

The two Phase 3A runs were byte-identical:

- acceptance JSON:
  `sha256:c0ea908f3b6f1c9fd19d83180f3e55f865238dfc4f96727048531d51bfe8c241`;
- ResearchMemoryExport bytes:
  `sha256:f1b57c2cae96638a7545476722685f17eb7470c5b4d0a790ca788de8e8756272`;
- traceable report:
  `sha256:881b2d0a85da1c9c57181c0aeb28ae6efccbc88e4a6521f6d29bd60856544ac9`;
- canonical memory hash:
  `sha256:99891f3b0acd8493adae7976caad8d493995adf2c68522bca2e8da6845e21e4c`;
- event replay hash:
  `sha256:66998142ca524886b021958c54a80cfbb77002ce1035892f4c26ea54ba362e6c`;
  and
- all three repeats plus restart retained ordered-result hash
  `sha256:08d8f51567341a9ab17b03b913f1e5409e2b751e1aa4b60db068de72c72cbb0c`
  and pack-set hash
  `sha256:0586e955336e2e7322168f784662ac5beafaaac26259e07933c1af1deb7b5631`.

The Phase 3B runtime remained the sealed
`sha256:39457cf097e89537ac90e7ddee08cbda8f7f2d49e443cc60a87d6d02d8cb896f`
image. Each run preserved its own restart replay, but independent runs did not
produce the same canonical export:

| Artifact | Run 1 | Run 2 |
|---|---|---|
| export content hash | `sha256:bd942606af74f9b2705d98123828a760284326f23992bbf0f60fc421e5f85c25` | `sha256:6f34bec8c69aa99b6cf666981c7d2fd64df586d4e81b2f9e649b48067ab7f3bf` |
| acceptance file bytes | `sha256:eaaf1d49d92e968bacd30e44a77da570fd3c6d397878b1febc63b286b0c26fd0` | `sha256:058a843a572a243dbd8fc64a7d3311518da570a90d94722a461746ca1b63ce49` |
| export file bytes | `sha256:b6fd0d1a7b1f116ac32018e6dc5c2fd971a4d54ecfbff5f2d864d61136e14fb4` | `sha256:cf69c13adc3b3857749ec271bbf7333425a6cd02cf5d8589c9c8f08e6981d5fb` |

The six executed findings differed in measured `elapsed_milliseconds`; their
content hashes and IDs are derived from that field, which also changes export
ordering and hashing. After excluding only finding IDs, finding content hashes,
and `elapsed_milliseconds`, the findings compared equal. No temporary host path,
process ID, source bytes, checker output, outcome, axiom inventory, or trust
classification differed.

This is a pre-existing Phase 3B production behavior, not a Phase 4 change. It
fails the controlling requirement that incidental timing not affect canonical
hashes. The entry gate must remain blocked until a separately authorized Phase
3B maintenance decision defines and verifies the canonical/operational split.
The fix must retain elapsed time as auditable operational metadata rather than
discard it, and must not weaken the sealed checker or replay validation.

Additional validation results:

- 97 JSON documents parsed; the sole invalid JSON path was the intentional
  `fixtures/phase3b/malformed.json` adversarial fixture exercised by the tests;
- all 11 schema documents parsed and schema semantics were exercised by the
  173-test suite;
- all 53 v4 gate-evidence files matched the v5 preservation manifest and every
  one of the 29 v5 entry-gate conditions remains true;
- all protected Phase 0, Phase 2, and Phase 3A hashes matched their sealed
  values, including the tracked Phase 3A SQLite file;
- the disposable Phase 2 report was byte-identical to the tracked report at
  `sha256:adef3d2d42999f24a877cf512f015c09316a719a163b9899faeb717b69a28b55`;
- credential scanning covered 202 files in `reports/**` and the new Phase 4
  documentation, with zero exact local-credential matches and zero credential
  token-pattern matches;
- `git diff --check`, standard-library `tabnanny`, and AST parsing of 77 Python
  files passed; and
- the repository defines no Ruff, mypy, or Pyright configuration and those
  tools are not installed, so no unconfigured third-party formatter or type
  checker was introduced or claimed.

The measured environment was Python 3.14.4, SQLite 3.53.3 with FTS5, Apple Git
2.50.1, and macOS 26.5.2 build 25F84 on Darwin 25.5.0 arm64.

## Exact independent verification commands

Run from the repository root with the already sealed local Phase 3B image:

```bash
env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -W error::ResourceWarning -m unittest discover -s tests -q
env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m phase0_harness.cli check

phase4_phase1="$(mktemp -d /private/tmp/adaivy-phase4-phase1.XXXXXX)"
env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m math_research.cli demo --output-dir "$phase4_phase1"
env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m math_research.cli inspect "$phase4_phase1/manual-dossier.json"

env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m math_research.cli phase2 report reports/phase-2 \
  run.phase2.demo.fake.v1 --output /private/tmp/adaivy-phase4-phase2-report.md

phase4_phase3a="$(mktemp -d /private/tmp/adaivy-phase4-phase3a.XXXXXX)"
env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m math_research.cli phase3a demo "$phase4_phase3a/workspace" \
  --output-dir "$phase4_phase3a/output"
env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m math_research.cli phase3a inspect \
  "$phase4_phase3a/output/research-memory.json"

phase4_phase3b="$(mktemp -d /private/tmp/adaivy-phase4-phase3b.XXXXXX)"
env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m math_research.cli phase3b demo "$phase4_phase3b/workspace" \
  --output-dir "$phase4_phase3b/output"
env -u OPENAI_API_KEY PYTHONDWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m math_research.cli phase3b inspect \
  "$phase4_phase3b/output/formal-checking.json"

git diff --check
python3 -m tabnanny src tests
git status --short --untracked-files=all
git diff --stat
git diff
git diff --cached --stat
git diff --cached
```

Repeat the Phase 3A and Phase 3B disposable blocks and compare the listed
canonical hashes. Phase 3A must match. Phase 3B currently demonstrates the
recorded blocker until separately repaired and accepted.

## Deliverable inventory and handoff

This gate-only delta contains exactly:

- `docs/phase-4/ENTRY_GATE_REPORT.md` — authority, preflight, scope, blockers,
  verification, and handoff;
- `docs/phase-4/BOUNDED_IMPLEMENTATION_PROMPT.md` — inactive successor prompt
  for entry-gate work only; and
- `reports/phase-4-entry-gate/entry-gate.json` — machine-readable evidence.

The machine-readable evidence content hash is
`sha256:f48f770c026be574e8685b31b37680fdc3b5aa3e3be7f1d3c50b8089f47f1964`,
computed from canonical JSON with its `provenance.content_hash` field set to
`null`.

No production source, fixture, schema, migration, dependency, quantum path, or
existing report changed. Nothing is staged.

If the maintainer elects to preserve this blocked-gate evidence, the proposed
commit message is `docs: record blocked Phase 4 entry gate`, using explicit
pathspecs for only the three paths above. No Phase 4 tag command is appropriate
while the gate is blocked. The existing convention suggests reserving
`phase-4` for a future accepted production commit; do not create or move it now.

Phase 5 handoff: do not begin adaptive search or quantum work. Before Phase 5,
the quantum dossier branch must be reviewed and rebased or otherwise recreated
through an explicit, provenance-preserving decision from a sealed descendant;
it must not be silently imported from its current pre-Phase-3B ancestry.

## Bounded recommendation

Run only the proposed entry-gate task in
`BOUNDED_IMPLEMENTATION_PROMPT.md`. It must resolve and measure the decisions
above without production entities, migrations, network acquisition, model/API
calls, or quantum work. After human acceptance, generate a new production
prompt naming the exact selected slice, accepted ADRs, evidence hash, fixtures,
thresholds, dependencies, and stop line.

Do not use this report as production authorization.
