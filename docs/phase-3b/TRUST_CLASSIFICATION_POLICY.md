# Lean Formal-Checker Trust Classification Policy

Status: proposed; not exercised

## Outcomes

| Outcome | Meaning |
|---|---|
| `proposed` | unexecuted or untrusted formal artifact |
| `checker_running` | transient job state only; no mathematical meaning |
| `elaboration_failed` | Lean rejected syntax, types, imports, or proof elaboration |
| `resource_limit_exceeded` | CPU, wall, memory, process, file, or output limit ended checking |
| `checker_error` | adapter, sandbox, toolchain, invocation, or result-parsing failure |
| `kernel_checked` | exact declaration checked with an empty reported axiom dependency set |
| `kernel_checked_with_approved_classical_axioms` | checked declaration depends only on the disclosed approved standard set |
| `kernel_checked_with_unapproved_assumptions` | kernel check succeeded but a custom, unknown, or disallowed assumption is present |
| `rejected_placeholder` | `sorry`, `admit`, `sorryAx`, or an equivalent placeholder is detected |
| `rejected_policy_violation` | input/import/command or execution behavior violates the restricted profile |

## Initial axiom policy

The policy-approved standard set is exactly:

- `propext`;
- `Quot.sound`; and
- `Classical.choice`.

These names are disclosed in every result that uses them. They are not called
axiom-free. An empty `#print axioms` set is required for plain
`kernel_checked`. Any unknown name, user/model `axiom` declaration, or
placeholder-related axiom yields
`kernel_checked_with_unapproved_assumptions` or a stronger rejection outcome.
`sorryAx` always yields `rejected_placeholder`.

The allowlist is versioned with the policy and must be tested against exact
Lean output. Parse failure, missing axiom output, ambiguous declaration
identity, or an unrecognized diagnostic fails closed as `checker_error`, never
as a kernel-checked result.

## Classification precedence

1. Invalid envelope/hash/target or forbidden command/import becomes
   `rejected_policy_violation`.
2. A placeholder becomes `rejected_placeholder` even when Lean would accept it
   with a warning.
3. A sandbox/resource termination becomes `resource_limit_exceeded`.
4. Toolchain/sandbox/result-parser failure becomes `checker_error`.
5. Ordinary Lean rejection becomes `elaboration_failed`.
6. Only a successful process with the exact expected declaration and complete
   axiom output may enter a kernel-checked classification.
7. The axiom set selects empty, approved-standard, or unapproved-assumption
   classification.

Warnings are retained and policy-classified; they are never silently discarded.
A successful process with an unexpected warning fails closed pending a named
policy rule.

## Forbidden initial profile

Reject user-controlled imports; package commands; `unsafe` declarations;
foreign/extern bindings; executable evaluation (`#eval`, `run_io`, native
execution, or equivalents); arbitrary file/network/process APIs; dynamic
libraries; and arbitrary full Lean files. `native_decide` is outside the
initial profile because it invokes native execution; a future certificate
policy needs a separate decision and independent checking story.

## Relationship to AdaIvy trust

A checker result is immutable evidence about one exact encoded theorem under a
specific toolchain, imports, and assumptions. It cannot:

- approve semantic alignment;
- prove that the encoded theorem matches the informal claim;
- make source evidence applicable;
- close a representation bridge automatically;
- award novelty or significance;
- import model output as accepted mathematics; or
- mutate a claim, obligation, or warrant directly.

During this gate every result remains a proposal/finding. A later production
policy may create a narrowly scoped `formally_verified` warrant only after the
exact target and semantic-alignment requirements pass through domain code.
