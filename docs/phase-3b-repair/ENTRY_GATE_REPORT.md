# Entry Gate Report — Phase 3B Bounded Proof Repair

- **Slice:** ADR-0040
- **Date:** 21 August 2026
- **Trigger:** ADR-0026's revisit trigger fires on "any slice that touches the
  Phase 3B sealed runtime", returning the slice to the full gate package rather
  than the one-ADR-plus-tests process.

## Why a fresh runtime entry gate is *not* required

`docs/phase-3b/BOUNDED_IMPLEMENTATION_PROMPT_V5.md` instructs: "If the exact v5
runtime is absent, mismatched, or cannot support the bounded production contract
unchanged, stop and require a fresh entry gate."

The runtime supports the contract unchanged. This slice adds *submissions*, not
capability. Each submission is a complete, independently validated request that
the existing production path already accepts. Specifically unchanged and
unreferenced by `repair.py`:

| Sealed control | Status |
|---|---|
| ADR-0016 v5 image and digest | unchanged, unreferenced |
| launcher and fixed invocation | unchanged, unreferenced |
| 262,144-byte stdin bound | unchanged; asserted per wrapper |
| fixed `/tmp/adaivy-input.lean` path | unchanged, unreferenced |
| Landlock hardener, seccomp policy | unchanged, unreferenced |
| Docker create options and controls | unchanged, unreferenced |
| executable inventory, dependency closure | unchanged; no dependency added |
| wrapper generator | unchanged; every submission uses it |
| request validator | unchanged; every submission passes through it |
| axiom allowlist and classification precedence | unchanged |

`test_repair_does_not_reference_docker_the_launcher_or_the_invocation` asserts
absence of `subprocess`, `docker`, `Popen`, `INVOCATION`, `FIXED_INPUT_PATH`,
and `RUNTIME_DIGEST` from the module source, so the separation is executable
rather than asserted in prose.

The one boundary genuinely revised is the V5 prompt's exclusion of "proof search
or repair". ADR-0040 revises it explicitly. The adjacent exclusion of
"model/API calls" is **left in force**: the `ProofProposer` port exists, no live
caller does.

## Trust path

Unchanged from Phase 3B. The Lean kernel remains the sole trust boundary and
the repair layer cannot reach it except through `FormalCheckingService.check`
(`test_repair_reaches_the_checker_only_through_the_public_check_method`).

A repair loop introduces exactly one new trust question: can iteration
manufacture a result the single-shot path would have refused? Three controls
answer no.

1. The theorem is frozen, so iteration cannot weaken what is being proved.
2. Only Lean's own elaboration failure is followed, so iteration cannot
   optimize against the validator, the meaning tests, or the axiom policy.
3. Nothing is promoted, so a kernel-checked repair carries exactly the warrant a
   kernel-checked single shot carries: none.

## Threat model delta

`docs/phase-3b/FORMAL_CHECKER_THREAT_MODEL.md` stands. Two additions.

**T-R1 — Validator evasion by iteration.** An adversarial or merely persistent
proposer could treat validator rejections as a gradient and search for a
fragment that passes validation while smuggling a forbidden feature. *Control:*
policy rejections are terminal and are never fed back; a rejection ends the
session as `proposer_rejected`. A proposer that reliably produces rejections is
visible in the record rather than absorbed by it.

**T-R2 — Diagnostic as instruction.** `RepairContext.diagnostic` is Lean output
influenced by submitted proof text, so a crafted fragment could place
attacker-chosen text in front of a future proposer. *Control:* the diagnostic is
bounded, NUL-stripped, hashed into the record, and labelled with its own
truncation. The port's contract states that a live proposer must treat it as
data and never as instruction. This control is documentary for now and becomes
load-bearing the moment a live proposer exists; it is the primary review item
for that slice.

## Blockers carried forward

- **No live proposer.** Nothing here measures whether repair helps. Solve rate,
  cost per closed obligation, and `proposer_rejected` rate against a real model
  are all unknown, and remain an ADR-0029 retention question.
- **No premise selection.** Governed by `TECHNICAL_BLUEPRINT.md:294` as
  adopt-before-rebuild. Open.
- **No per-phase cost attribution.** Nothing in `src/` splits cost by
  generation, formalization, Lean checking, or retrieval. A repair loop is
  precisely the thing whose cost needs separate attribution and it cannot be
  reconstructed after the fact, so this should land before a live proposer.

## Owner authorization

Recorded as an owner instruction in session on 21 August 2026 to correct the
architecture-suggestions document and then build the slice it identified. The
authorization covers the offline slice as implemented. It does **not** cover a
live model proposer, which requires its own decision.
