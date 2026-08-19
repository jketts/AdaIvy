# Phase 3B Entry-Gate Fixture Results

Status: all fixtures specified; none executed

No fixture result below is an observed Lean outcome. Toolchain absence blocks
all twelve. Side-effect/resource fixtures are additionally blocked by the lack
of an accepted sandbox. The machine-readable record is
`reports/phase-3b-entry-gate/fixture-results.json`.

| ID | Synthetic fixture | Expected accepted classification | Observed status | Blocker |
|---|---|---|---|---|
| F01 | valid theorem with complete proof | `kernel_checked` | not evaluated | toolchain unavailable |
| F02 | same theorem using `sorry` | `rejected_placeholder` | not evaluated | toolchain unavailable |
| F03 | same theorem using `admit` | `rejected_placeholder` | not evaluated | toolchain unavailable |
| F04 | false theorem without placeholder | `elaboration_failed` | not evaluated | toolchain unavailable |
| F05 | syntax error | `elaboration_failed` | not evaluated | toolchain unavailable |
| F06 | unknown import | `rejected_policy_violation` before execution | not evaluated | toolchain unavailable |
| F07 | theorem from a newly declared axiom | `kernel_checked_with_unapproved_assumptions` | not evaluated | toolchain unavailable |
| F08 | approved standard classical reasoning | `kernel_checked_with_approved_classical_axioms` with disclosed set | not evaluated | toolchain unavailable |
| F09 | timeout/resource exhaustion | `resource_limit_exceeded` | not evaluated | toolchain and sandbox unavailable |
| F10 | attempted path/filesystem access | `rejected_policy_violation`; OS containment if scan bypassed | not evaluated | toolchain and sandbox unavailable |
| F11 | attempted network/process action | `rejected_policy_violation`; OS containment if scan bypassed | not evaluated | toolchain and sandbox unavailable |
| F12 | oversized output | `resource_limit_exceeded` or named output-limit subtype | not evaluated | toolchain and sandbox unavailable |

## Required assertions on rerun

- F01 checks the exact wrapper declaration and reports its complete axiom set.
- F02/F03 remain rejected even if Lean exits successfully with a warning.
- F04/F05 do not create a checked finding or warrant.
- F06 never expands an unapproved dependency.
- F07 names the custom axiom exactly and cannot be called verified.
- F08 discloses every approved standard dependency rather than saying
  “axiom-free.”
- F09 terminates the whole process group within the frozen bounds.
- F10/F11 cannot observe or mutate anything outside the disposable sandbox.
- F12 retains bounded output bytes, full-stream hash/length where safely
  available, and one terminal result.
- Two repetitions and one clean restart yield identical canonical result hashes
  for every deterministic fixture.
- Wall timing, PID, host temp paths, and run-directory names are noncanonical
  operational metadata.

No fixture may target real resources outside its disposable sandbox.
