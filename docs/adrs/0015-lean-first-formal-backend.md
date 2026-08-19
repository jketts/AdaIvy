# ADR-0015: Use Lean 4 plus mathlib as the first formal backend

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** sections 9.3, 19 Phase 3B, and open decision 6
- **Decision owners:** researcher and repository maintainer

## Context

Phase 3B needs an initial proof-assistant path selected by general-mathematics
library fit, reproducibility, kernel checking, licensing, sandboxability, and
honest trust classification. Phase 0 named Lean but could not execute it. The
repaired Phase 3B v4 entry gate acquired the exact pinned releases, built a
minimal shell-free runtime, demonstrated effective Landlock execution control,
and measured checker behavior on the frozen fixtures.

Lean provides a small-kernel checking path, exact theorem statements, explicit
diagnostics, and `#print axioms`; mathlib provides the selected general-
mathematics library. The v4 acquisition, runtime, executable-inventory, replay,
and full-gate records are under `reports/phase-3b-entry-gate/v4/`.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt Lean/mathlib directly | official releases and design only | library breadth and kernel | hostile elaboration, large cache, version churn | rejected before sandbox/fixtures |
| Wrap pinned Lean/mathlib after gate | proposed manifest and policy | narrow replaceable boundary | acquisition, wrapper/parser, sandbox TCB | selected proposal |
| Start with Why3/SMT | Phase 0 inventory only | automation and obligation dispatch | deferred by requested scope; different trust semantics | no local execution evidence |
| Build a checker or universal abstraction | no need demonstrated | local control | duplicates mature systems and expands TCB | rejected |

## Decision

Use Lean 4 plus mathlib as the first formal backend through a narrow wrapper.
Pin elan v4.2.1, Lean `v4.32.1` at commit
`f054605aea4b840552cca2e725580bffd1e1b704`, and mathlib `v4.32.1` at commit
`520045ab14e26149ee970e2e617ca04b09bde5d6`.

Production implementation remains a separate bounded task. Input is a
restricted theorem/proof fragment embedded in a trusted wrapper; arbitrary Lean
files remain outside the initial profile. Checking is offline in the sealed
shell-free runtime with the demonstrated Landlock, seccomp, filesystem,
privilege, and resource controls. Placeholder, axiom, warning,
unsafe/FFI/native/evaluation, import, and resource policies fail closed. Every
result is a proposal/finding and cannot approve semantic alignment or mutate
warrants.

Keep the architecture backend-neutral at its existing `MathTool`/verifier
conceptual boundary, but do not add a new abstraction layer before this gate
passes. Why3, SMT, OMDoc/MMT, and other proof assistants remain deferred.

## Consequences

The first production formal slice may now wrap the exact kernel-backed path
without coupling domain entities to Lean. It inherits a pinned runtime,
transitive dependency audit, parser/version maintenance, and the demonstrated
sandbox requirement because elaboration can execute metaprogramming. Changing
the checker, dependency closure, launcher, hardener, or execution policy
invalidates the sealed runtime evidence and requires the gate to be rerun.

`kernel_checked`, approved-standard-axiom, and unapproved-assumption outcomes
remain distinct. Formal checking never implies semantic fidelity, literature
applicability, novelty, significance, or contribution.

## Blueprint deviation

None. The blueprint leaves the first proof assistant open and schedules this
selection in Phase 3B. This ADR narrows evaluation order; it does not implement
the backend.

## Validation and revisit trigger

This decision remains accepted only while:

- exact pinned acquisition and complete direct/transitive license inventory;
- offline execution in a demonstrated sandbox;
- all twelve fixtures produce their required classifications;
- placeholder and axiom parsing fail closed;
- repeated/restart canonical result hashes match;
- all Phase 0–3A tests, validators, protected hashes, and credential scans pass.

Entry-gate repair v4 passed all of these conditions. The decisive record is
`reports/phase-3b-entry-gate/v4/entry-gate-v4.json`; its supporting records
preserve the exact acquisition metadata, OCI-layer executable inventory, three
fixture/policy rounds, v3/v4 replay comparison, repository verification, and
credential scan. The v3 reports and replay image remain distinct and unchanged.

Reject or revisit if isolation is insufficient, lock/hash resolution is not
reproducible, licensing is incompatible, axiom/placeholder detection is
unreliable, or another checker demonstrably meets the same contract with a
smaller trusted and operational boundary.
