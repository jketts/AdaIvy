# Lean/mathlib Entry-Gate Scorecard

Date: 2026-08-19

Blocked and unexecuted capability is not scored as poor capability. The file
baseline and Lean candidate are compared dimensionally under ADR-0004.

| Dimension | File-based baseline | Lean 4 + mathlib candidate |
|---|---|---|
| Evaluation status | evaluated | not evaluated |
| Local runnability | runnable | blocked: executables and cache absent |
| Measured capability | deterministic storage/replay only | not measured |
| Capability score | historical Phase 0 score retained | null |
| Formal-kernel checking | none | proposed, unexecuted |
| Exact target capture | deterministic dossier bytes | designed, unexecuted |
| Placeholder rejection | not applicable | designed, unexecuted |
| Axiom disclosure | not applicable | designed around `#print axioms`, unexecuted |
| Replay determinism | measured | not measured |
| Integration effort | low, already present | medium/high: acquisition, wrapper, parser, sandbox |
| Evidence completeness | complete for file behavior | partial design evidence only |
| License status | repository remains unlicensed | upstream candidate licenses compatible; transitive audit pending |
| Security status | no executable checker | blocked: no accepted hostile-code sandbox |
| Blockers | no mathematical verification | toolchain, lock hashes, sandbox, fixture execution |

## Recommendation

- File baseline: retain for canonical input/output, failure retention, and
  comparison. It cannot provide a formal warrant.
- Lean 4 + mathlib: **propose/wrap after gate**, not adopt yet. The domain stays
  backend-neutral; do not build an abstraction layer until the checker gate
  passes.
- Why3, SMT, OMDoc/MMT, and other proof assistants: defer.

There is no numerical winner and no capability ranking because Lean did not
execute. The first meaningful comparison after acquisition is whether the Lean
wrapper adds reproducible kernel checking and honest failure classification
without weakening the baseline's canonical replay and proposal-only boundary.
