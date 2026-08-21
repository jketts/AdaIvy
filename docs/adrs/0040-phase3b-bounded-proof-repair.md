# ADR-0040: Bounded Phase 3B proof repair above the sealed runtime

- **Status:** accepted for the bounded proof-repair slice; implemented
  21 August 2026 with a scripted proposer. ADR-0048 subsequently authorizes a
  separately gated live Azure OpenAI implementation of the same narrow port.
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 7 Lean-first formal backend; Section 19
  Phase 3B; `TECHNICAL_BLUEPRINT.md:294` and `:1393` on adopting premise
  selection, compiler feedback, and proof repair rather than rebuilding them
- **Decision owners:** repository owner and researcher

## Context

Phase 3B accepts one hand-supplied restricted theorem and proof fragment,
checks it once inside the sealed ADR-0016 v5 container, and records a
proposal-only finding. `docs/phase-3b/BOUNDED_IMPLEMENTATION_PROMPT_V5.md`
closes that task with an explicit exclusion list: "Do not add ... premise
retrieval, proof search or repair, model/API calls, multi-agent
orchestration". That exclusion was correct for the slice it bounded and is the
boundary this ADR revises, explicitly rather than quietly.

The gap is structural, not incremental. Every system the novelty review treats
as comparable prior art -- `NOVELTY_LANDSCAPE.md:36` on AlphaProof Nexus in
particular -- depends on a loop: propose a candidate, read the compiler's
rejection, propose again, with the kernel as the sole trust boundary. Without
it, Phase 3B can only confirm proofs a human already found. ADR-0029 sharpened
the need by making formalization *incremental*, with Lean "applied early to
mature local claims and interfaces"; a per-obligation repair loop is what makes
incremental formalization more than aspirational. ADR-0029 does not itself
authorize the loop, so a scope record is still required.

Three risks decide the shape.

- **Repairing against a check rather than toward a proof.** A loop that retries
  until *any* check stops complaining optimizes against whichever check it can
  see. Validator diagnostics are the sharpest case: a policy rejection is a
  description of how to evade the validator, so feeding one back trains
  evasion. Meaning-test failures and unapproved-assumption results are the same
  class -- both are semantic or trust signals, not proof errors.
- **Premise smuggling.** `NOVELTY_LANDSCAPE.md:76` records failed sketches that
  moved the central difficulty into a helper lemma, sometimes described as
  established literature. A repair loop that can touch the statement, its
  hypotheses, or its imports can weaken the theorem until the proof succeeds,
  and the result will still be reported as kernel-checked.
- **Unbounded spend.** A stuck obligation can absorb a whole run. ADR-0037's
  confirmed rates make this concrete: at the recorded $49.50/M output, an
  unbounded loop is the most expensive failure mode in the repository.

## Options considered

| Option | Benefit | Risk | Decision |
|---|---|---|---|
| General proof search inside the sealed runtime | Strongest capability | Requires reopening the ADR-0016 entry gate, the launcher, and the fixed invocation | Rejected |
| Mutate the rejected request in place and re-run | Cheapest to build | Destroys the append-only attempt history; a repair becomes indistinguishable from the original submission | Rejected |
| Repair on every non-success outcome | Highest solve rate | Trains evasion against the validator and optimizes against meaning tests | Rejected |
| Let the proposer return a full request | Permits import and lemma discovery | Statement, hypotheses, and imports become model-controlled; premise smuggling is unconstrained | Rejected |
| Bounded repair above the checker, elaboration failure only, proposer returns a proof fragment only | Adds the loop without touching any sealed control; premise smuggling is structurally impossible | No premise selection; capability is narrower than the prior art | **Selected** |

## Decision

Add `src/math_research/phase3b/repair.py`, orchestrating strictly above
`FormalCheckingService.check`. The sealed runtime, launcher, fixed invocation,
262,144-byte stdin bound, Landlock hardener, seccomp policy, Docker controls,
wrapper generator, and validator are unchanged and unreferenced.

**The theorem is frozen.** A `ProofProposer` returns `ProposedProof`, whose
whole surface is one `proof_fragment`. The declaration name, target statement,
import manifest, assumption manifest, claim identity, and meaning tests are
copied from the origin request and re-derived from the candidate bytes before
every submission. A mismatch raises `TheoremIdentityViolation` rather than
recording a session, because a session that cannot vouch for its own theorem
identity has no meaning worth persisting.

**Only elaboration failure is repairable.** `REPAIRABLE_OUTCOMES` is exactly
`{ELABORATION_FAILURE}`. Kernel-checked results terminate as success.
Unapproved assumptions, meaning-test failures, timeouts, output limits, sandbox
failures, and policy rejections all terminate. If the validator refuses a
model-authored fragment the session ends as `proposer_rejected`; the loop never
iterates against the validator.

**Every attempt is a separate record.** A repaired candidate gets a
content-derived `request_id`, its own request hash, its own wrapper, and its own
finding hash. It is a new proposal, not a mutation of the rejected one, and
`source_kind` becomes `MODEL` so a model-authored proof is never reported as
operator-authored -- including when the *successful* attempt is the repaired one.

**Bounds are hard.** `RepairLimits.max_attempts` counts the origin submission
and is capped at 16; `max_diagnostic_bytes` is capped at 65,536. Diagnostics
come only from the already-bounded retained capture, are hashed into the record,
and report their own truncation. An identical candidate is never resubmitted.

**Nothing is promoted.** `RepairSession.epistemic_warrant_created` is `False`
unconditionally, every attempt keeps `disposition = "proposal"` and
`trust_effect = "none"`, and a kernel-checked repair still claims only the exact
hashed statement under the disclosed assumptions.

Because ADR-0026's revisit trigger fires on any slice touching Phase 3B, the
gate package in `docs/phase-3b-repair/` is normative for this slice.

## Consequences

Phase 3B gains a repair loop and no Lean capability. Premise selection is *not*
adopted here; `TECHNICAL_BLUEPRINT.md:294` and `:1393` already govern that as
an adopt-before-rebuild decision, and it remains open work.

The offline acceptance path drives a deterministic scripted proposer and
performs no model or network call, so `make check` stays offline. ADR-0048 later
wires a live Azure OpenAI implementation through a separate explicit gate with
a confirmed pricing snapshot and per-phase cost attribution; none of that
changes this slice's control plane.

Reviewers gain one new failure mode to watch: a proposer that reliably converts
elaboration failures into policy rejections is not a proof engine, it is a
fuzzer against the validator, and `proposer_rejected` counts are the signal.

## Blueprint deviation

One deviation. `docs/phase-3b/BOUNDED_IMPLEMENTATION_PROMPT_V5.md` excludes
proof repair and model calls. This ADR revises the repair exclusion and leaves
the model-call exclusion in force: the port exists, no live caller does. The V5
instruction to "stop and require a fresh entry gate" if the runtime "cannot
support the bounded production contract unchanged" is satisfied without a new
runtime gate, because the contract is unchanged -- the slice adds submissions,
not capability. `docs/phase-3b-repair/ENTRY_GATE_REPORT.md` records that
determination and the evidence for it.

## Measured outcome

`tests/test_phase3b_proof_repair.py`, 38 cases, offline. The sealed runtime is
never invoked: `ScriptedLeanAdapter` overrides only `execute` and inherits the
production `validate` and `verify_output`, so the classifier under test is the
real one.

Six adversarial mutations of `repair.py` were each confirmed to fail the suite,
so the thresholds are executable rather than decorative:

| Mutation | Failures |
|---|---|
| widen `REPAIRABLE_OUTCOMES` to policy rejection and meaning-test failure | 2 |
| keep operator attribution on a repaired attempt | 3 |
| remove the attempt cap | 3 |
| set `epistemic_warrant_created = True` | 5 |
| disable duplicate-candidate detection | 2 |
| disable the theorem-identity check | 2 |

**What is not measured by this ADR.** Its scripted suite measures no live-model
solve rate, cost, or `proposer_rejected` rate. ADR-0048 creates a place to record
those observations without retroactively treating them as evidence that repair
improves verified progress per unit cost; the ADR-0029 retention question stays
open.
