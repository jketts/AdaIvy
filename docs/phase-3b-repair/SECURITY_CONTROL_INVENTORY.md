# Security Control Inventory — Phase 3B Bounded Proof Repair

ADR-0040. Controls inherited from the sealed Phase 3B slice are listed only
where the repair layer changes their exposure. Everything in
`docs/phase-3b/FORMAL_CHECKER_THREAT_MODEL.md` and
`docs/phase-3b/TRUST_CLASSIFICATION_POLICY.md` remains in force unmodified.

## C-R1 — Sealed-runtime isolation

The repair layer holds no reference to the container engine, image digest,
launcher, invocation, fixed input path, Landlock hardener, or seccomp policy. It
reaches Lean only by calling `FormalCheckingService.check` with complete request
bytes.

*Enforcement:* source-level absence assertion over `subprocess`, `docker`,
`Popen`, `INVOCATION`, `FIXED_INPUT_PATH`, `RUNTIME_DIGEST`, plus a recording
subclass proving every submission goes through the public `check` method.

*Residual risk:* a future edit could import the adapter directly. The absence
assertion fails on that edit.

## C-R2 — Frozen theorem identity

A proposer's entire output surface is one proof fragment. Statement, hypotheses,
imports, declaration name, claim identity, and meaning tests are copied from the
origin and re-derived from the candidate bytes before submission. A mismatch
raises rather than records.

This is the anti-premise-smuggling control and the reason the port is typed as
`ProposedProof` rather than a request. It answers
`NOVELTY_LANDSCAPE.md:76`: a repair cannot move the central difficulty into a
hypothesis, because it cannot write a hypothesis.

*Residual risk:* premise smuggling *within* a proof fragment — appealing to a
Mathlib lemma that does not say what the proposer implies — is unaffected by
this control and is caught only by Lean itself. That is the correct division:
the kernel judges the proof, this control judges what is being proved.

## C-R3 — No feedback of validator diagnostics

Policy rejections are terminal. A validator diagnostic is a description of how
to evade the validator, so it is never handed to a proposer. A rejected
model-authored fragment ends the session as `proposer_rejected`.

*Detection signal:* a proposer whose sessions frequently end in
`proposer_rejected` is fuzzing the validator, not proving theorems. The
termination reason and `proposer_calls` are both in the session record so this
is visible in aggregate.

## C-R4 — No optimization against semantic or trust checks

Meaning-test failures and unapproved-assumption results are terminal for the
same reason: both are checks about meaning and trust rather than proof errors,
and iterating against them selects for candidates that satisfy the check
without satisfying the intent. Timeouts and output limits are terminal because
they yield no usable diagnostic and cost the most budget.

## C-R5 — Bounded, hashed, honestly labelled diagnostics

The diagnostic handed to a proposer is drawn only from `RawExecution`'s already
bounded retained capture, never from full streams; NUL-stripped; truncated to
`max_diagnostic_bytes`; hashed into the attempt record; and accompanied by
`diagnostic_truncated` so a proposer cannot mistake a clipped diagnostic for a
complete one.

**T-R2, unmitigated in code.** The diagnostic is Lean output influenced by
submitted proof text, so a crafted fragment can place chosen text in front of a
later proposer. Bounding and hashing make this auditable, not impossible. The
port contract requires a live proposer to treat the diagnostic as data and never
as instruction. **This control is documentary while no live proposer exists and
becomes load-bearing the moment one does — it is the primary review item for
that slice.**

## C-R6 — Hard budget bounds

Attempts are capped (default 4, maximum 16) counting the origin. Identical
candidates are never resubmitted. A declining proposer ends the session without
consuming a further attempt. Exhaustion is recorded as `attempts_exhausted`
rather than reported as a failure to prove.

*Rationale:* at ADR-0037's confirmed $49.50/M output rate, an unbounded repair
loop is the most expensive failure mode in the repository.

## C-R7 — No trust promotion on any path

`epistemic_warrant_created` is `False` unconditionally. Every attempt keeps
`disposition = "proposal"` and `trust_effect = "none"`. Semantic alignment,
source applicability, novelty, significance, and contribution remain
unapproved. A kernel-checked repair claims exactly the exact hashed statement
under disclosed assumptions.

Asserted across four distinct session shapes including the successful-repair
path, which is the one where a promotion would be most tempting.

## C-R8 — Append-only attempt history

A repaired candidate is a new record with a content-derived identifier, never a
mutation of the rejected one. Rejected attempts, their diagnostics, and their
findings are all retained in order. `RepairSession` and `RepairAttempt` are
frozen dataclasses.

*Rationale:* if a repair overwrote its predecessor, a session that failed
fifteen times and succeeded once would be indistinguishable from a session that
succeeded immediately.

## Controls explicitly not added

- **Rate limiting or spend metering per proposer.** Belongs with the live
  proposer slice and the missing per-phase cost attribution.
- **Proposer output sanitization beyond the existing validator.** Deliberately
  not added; the unchanged validator is the single place fragment policy is
  decided, and a second, weaker filter would create two answers to one question.
- **Premise-selection provenance.** No premise selection exists yet.
