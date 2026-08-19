# ADR-0015: Propose Lean 4 plus mathlib as the first formal backend

- **Status:** proposed
- **Date:** 2026-08-19
- **Blueprint requirement:** sections 9.3, 19 Phase 3B, and open decision 6
- **Decision owners:** researcher and repository maintainer

## Context

Phase 3B needs an initial proof-assistant path selected by general-mathematics
library fit, reproducibility, kernel checking, licensing, sandboxability, and
honest trust classification. Phase 0 named Lean but could not execute it. The
Phase 3B entry gate found no local elan/Lean/Lake installation or cache and no
accepted hostile-code sandbox. It therefore did not measure checker capability.

Lean provides a small-kernel checking path, exact theorem statements, explicit
diagnostics, and `#print axioms`; mathlib provides the proposed general-
mathematics library. Both report permissive licenses. These are reasons to
evaluate Lean first, not evidence that the gate has passed.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt Lean/mathlib directly | official releases and design only | library breadth and kernel | hostile elaboration, large cache, version churn | rejected before sandbox/fixtures |
| Wrap pinned Lean/mathlib after gate | proposed manifest and policy | narrow replaceable boundary | acquisition, wrapper/parser, sandbox TCB | selected proposal |
| Start with Why3/SMT | Phase 0 inventory only | automation and obligation dispatch | deferred by requested scope; different trust semantics | no local execution evidence |
| Build a checker or universal abstraction | no need demonstrated | local control | duplicates mature systems and expands TCB | rejected |

## Decision

Propose Lean 4 plus mathlib as the first backend to test through a narrow
wrapper. Pin elan v4.2.1, Lean toolchain `leanprover/lean4:v4.32.1`, and mathlib
v4.32.1, subject to full commit, lock, hash, and license capture during an
authorized acquisition.

Do not adopt the backend or build a production adapter yet. Input is a
restricted theorem/proof fragment embedded in a trusted wrapper; arbitrary Lean
files are outside the initial profile. Checking is offline in an OS/container
sandbox. Placeholder, axiom, warning, unsafe/FFI/native/evaluation, import, and
resource policies fail closed. Every result is a proposal/finding and cannot
approve semantic alignment or mutate warrants.

Keep the architecture backend-neutral at its existing `MathTool`/verifier
conceptual boundary, but do not add a new abstraction layer before this gate
passes. Why3, SMT, OMDoc/MMT, and other proof assistants remain deferred.

## Consequences

The first formal spike can test an exact kernel-backed path without coupling
domain entities to Lean. It also introduces a multi-gigabyte acquisition,
transitive dependency audit, parser/version maintenance, and a substantial
sandbox requirement because elaboration can execute metaprogramming.

`kernel_checked`, approved-standard-axiom, and unapproved-assumption outcomes
remain distinct. Formal checking never implies semantic fidelity, literature
applicability, novelty, significance, or contribution.

## Blueprint deviation

None. The blueprint leaves the first proof assistant open and schedules this
selection in Phase 3B. This ADR narrows evaluation order; it does not implement
the backend.

## Validation and revisit trigger

Accept this ADR only after:

- exact pinned acquisition and complete direct/transitive license inventory;
- offline execution in a demonstrated sandbox;
- all twelve fixtures produce their required classifications;
- placeholder and axiom parsing fail closed;
- repeated/restart canonical result hashes match;
- all Phase 0–3A tests, validators, protected hashes, and credential scans pass.

Reject or revisit if isolation is insufficient, lock/hash resolution is not
reproducible, licensing is incompatible, axiom/placeholder detection is
unreliable, or another checker demonstrably meets the same contract with a
smaller trusted and operational boundary.
