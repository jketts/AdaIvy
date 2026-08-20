# Phase 4B Requirement/Test Matrix

Status: accepted with ADR-0028

| Requirements | Required evidence and tests |
|---|---|
| P4B-SC-001--005 authority and policy | Exact normalized-run authorization matrix; missing/stale/forked terms, robots, acquisition rights, retention rights, actor, and policy hash each denied before resolver/transport construction. |
| P4B-SC-006--010 network boundary | Fake resolver/peer/redirect adversarial matrix covering public-to-private rebinding, every special-use class, peer mismatch, downgrade, userinfo, cross-origin headers, 5/6 redirects, rate/retry/time/byte boundaries, and durable failure records. |
| P4B-SC-011--014 deletable content | Identical bytes stored as two independently deletable objects; interruption before/after removal; restart reconciliation; marker scan of all managed stores; immutable audit identity unchanged. |
| P4B-SC-015--020 hostile parsing | HTML active-content/external-resource fixtures; TeX shell/include/recursive-macro fixtures; PDF action/attachment/encryption/bomb/cross-reference fixtures; sandbox denies network, write escape, process escape, and environment access. |
| P4B-SC-021--025 provenance and replay | Exact parser/environment/input/transformation/warning manifests; byte/page/object anchor round trips; proposal-only axes; strict raw import/replay/restart/rebuild; semantic/operational hash separation. |
| P4B-SC-026--030 isolation and preservation | Socket/DNS traps; dependency import and offline-install scans; protected-evidence manifest; scope scan for forbidden modules/features; exact and one-over boundary tests; forbidden-outcome mutation suite. |
| P4B-AT-001--004 corpus | Manifest enforces exactly 30 project-authored fixtures with the 12/12/6 distribution and per-format counts. |
| P4B-AT-005--018 correctness/safety | Exact confusion matrices and counters; anchor/hash validation; execution-attempt traps; managed-store deletion scan; Phase 3A write trap; trust-promotion mutation tests. |
| P4B-AT-019--033 resource bounds | At-limit success and one-over failure for URL, origins, requests, redirects, concurrency, rate, retry, robots age, headers, raw/decoded/total bytes, parser resources/counts, and run deadline. |
| P4B-AT-034--036 determinism | Three same-process repeats, two independent gate processes, one fresh restart, one canonical replay, and one reverse-order rebuild with identical semantic bytes/hashes. |
| P4B-AT-037 dependencies | Hash-locked offline installation, installed-inventory equality, license manifest, lazy boundary import, absence/wrong-version failure, production import graph, and removal test. |
| P4B-AT-038 retrieval non-regression | Run accepted Phase 3A fixed gold corpus: Recall@5 1.0, MRR >=0.75, citation precision 1.0, zero quarantine retrieval, stable IDs/hashes. |
| P4B-AT-039 preservation | Verify stable protected-evidence manifest and byte identity of all existing canonical exports and sealed fixtures before and after every gate run. |
| P4B-AT-040 repository acceptance | `make check`, repository invariants, Phase 4A and Phase 4B suites, raw-boundary tests, credentials, protected evidence, Markdown links, and `git diff --check`; sealed/gate environments reported separately. |

## Fixture allocation

The 12 acquisition fixtures contain three permitted success cases and nine
denials: missing run authority, robots disallow, robots unavailable/invalid,
changed terms, acquisition-right denial, retention-right denial, redirect to a
special-use address, connected-peer mismatch, and response-budget overflow.

Each parser format has four fixtures: one admitted ordinary document, one
admitted document with warnings but exact anchors, one active/executable or
external-resource attack, and one malformed/ambiguous/resource-limit case that
must quarantine. PDF fixtures are project-authored minimal born-digital files;
no third-party or academic bytes are fixtures.

The six lifecycle/integration fixtures cover correction/supersession,
revocation/takedown, deletion with restart, two independently deletable copies
of identical bytes, canonical replay/rebuild, and a parse proposal attempting
to self-promote trust.

## Production-path requirement

Mocks may control external nondeterminism but may not replace the code under
test. URL/policy validation, budgeting, streaming, content-object writes,
parser sandbox launch, raw-envelope validation, persistence, deletion,
projection, export, import, replay, and trust rejection must be the actual
bounded production path. A forbidden outcome is accepted as tested only when
an adversarial input reaches the relevant boundary and the boundary rejects it.
