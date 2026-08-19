# Proposed Phase 4 Entry-Gate Implementation Prompt

Status: **proposal only; not production authorization**

Perform only the AdaIvy Phase 4 entry gate from the sealed Phase 3B baseline.
Do not implement Phase 4 production entities, migrations, adapters, services,
or workflows.

## Preconditions

1. Begin from the annotated `phase-3b` target
   `226b47863f565c9c5a7dc7ac9ac08d490420ecf2` on a dedicated branch.
2. Verify the `phase-3b` tag object is
   `9c464ba2b93ec9c80e6fc95421f53e3b54c6ab4c`, `origin/main` resolves to the
   same commit, evidence commit
   `6945d8aa206d79c3dc0bd7d7a50aea662414b8e8` is an ancestor, every existing
   tag is unchanged, and the tree/index are clean.
3. Read all applicable `AGENTS.md`, README, architecture baseline 0.3,
   `NOVELTY_LANDSCAPE.md`, all accepted ADRs, Phase 3A/3B acceptance evidence,
   and `docs/phase-4/ENTRY_GATE_REPORT.md`.
4. Stop on any baseline discrepancy. Do not stash, restore, delete, rebase,
   merge, amend, force, or repair it automatically.
5. Treat the Phase 3B cross-run canonical-hash discrepancy recorded in the
   Phase 4 entry-gate report as a prerequisite blocker. Do not fix Phase 3B as
   part of this gate. Require a separately authorized maintenance decision and
   passing evidence before evaluating Phase 4 candidates.

## Gate-only work

Produce a reviewable decision package that:

1. selects exactly one smallest complete Phase 4 production slice and proves it
   fits the accepted Phase 4 objective and exit criteria;
2. maps every selected capability to existing or proposed entities, ports,
   schemas, migrations, trust classifications, and acceptance tests;
3. records corpus/source rights separately for acquisition, redistribution,
   parsing, excerpting, embedding, model context, retention, and publication;
4. compares proposed parser behavior against `plain-text-v1` on the same
   synthetic fixtures, including exact source mappings, formula/layout loss,
   malformed inputs, resource bounds, determinism, and quarantine;
5. either excludes embeddings from the selected first slice explicitly or
   evaluates a pinned local-only candidate against FTS5 using the same corpus,
   with dependency/model-weight/data licenses, hashes, runtime manifest, and
   rebuild invariants;
6. either keeps acquisition local-only or specifies a separately authorized,
   bounded network adapter with allowlists, DNS/redirect/SSRF controls,
   robots/terms/rate policy, byte/media/archive limits, credential isolation,
   immutable failure records, and no trusted-core crawler;
7. freezes source-applicability, misquotation, malicious-source,
   renamed-result, incompatible-hypothesis, contradiction, restart, replay,
   and index-rebuild fixtures;
8. freezes necessary-lemma recall, applicability precision, rejection,
   provenance, determinism, and clean-tree thresholds before production code;
9. defines canonical serialization/hashing surfaces that exclude timing,
   process IDs, temporary paths, database layout, and other incidental data;
10. records a threat model, dependency/license manifest, cost estimate,
    requirement-test matrix, exact verification commands, and machine-readable
    gate result; and
11. proposes a new production prompt naming the accepted slice and evidence
    hashes exactly.

Use project-authored synthetic fixtures unless a human-approved rights manifest
authorizes local source bytes. Keep failed candidates and missing-tool results
as machine-readable evidence. Compare every candidate to the file/FTS baseline
on identical fixtures.

## Mandatory preservation controls

- Original bytes remain authoritative; parsing and indexing are derived.
- Source evidence, applicability review, formal statements, checker results,
  semantic alignment, novelty, significance, and human review remain separate.
- No result is promoted merely because it was retrieved, parsed, embedded,
  reranked, generated, model-agreed, or formally checked.
- Preserve append-only event history, canonical replay, restart correctness,
  explicit trust classifications, and failure retention.
- Preserve the accepted Phase 3B bounded-stdin, fixed noexec tmpfs, sealed
  launcher, Landlock, seccomp, no-network, read-only, non-root, resource-limit,
  axiom/placeholder, canonical-hash, and statement-faithfulness boundaries.
- Indexes remain rebuildable projections and cannot mutate canonical state.

## Prohibitions

Do not:

- implement any production Phase 4 capability;
- acquire external data, crawl, resolve URIs, or make model/provider/external
  API calls without a later, explicit authorization that names the boundary;
- add credentials, depend on secrets, or add a high-privilege runtime;
- install or add a dependency before its exact pin, hashes, license graph,
  runtime behavior, and removal plan are approved;
- import, merge, copy, or modify the quantum-discrimination worktree or begin
  Phase 5;
- weaken existing tests, trust policy, sandbox controls, or acceptance criteria;
  or
- commit, tag, push, publish, open a pull request, or change remote state.

## Passing conditions

The gate passes only if all of the following are true:

1. the selected first slice is singular, bounded, and accepted by the
   researcher/repository maintainer;
2. all required ADRs and policy decisions are accepted;
3. rights, dependency, parser, embedding, acquisition, security, schema,
   migration, fixture, threshold, and verification decisions are complete;
4. every local spike passes its frozen functional, adversarial, containment,
   repeat, restart, replay, hash, license, and clean-tree conditions;
5. all Phase 0 through Phase 3B acceptance and seal checks still pass;
6. independent Phase 3B runs have identical canonical semantic hashes while
   retaining elapsed time outside the canonical preimage as auditable
   operational metadata;
7. machine-readable evidence accounts for every condition and failed attempt;
8. zero AdaIvy model/provider/API calls, external source acquisition, quantum
   work, production changes, commits, tags, pushes, or publication occurred;
   and
9. the proposed production prompt is mechanically consistent with the accepted
   gate evidence.

If any condition is absent, ambiguous, not evaluated, or failed, record the
exact blocker and stop. Do not convert a partial gate into production
authorization.
