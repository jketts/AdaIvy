# ADR-0029: Central research lead with selectively activated search complexity

- **Status:** accepted
- **Date:** 2026-08-20
- **Blueprint requirement:** Sections 1, 3, 6, 8, and 17
- **Decision owners:** repository owner

## Context

The architecture correctly starts from a simple proposer--verifier loop and
requires measured gains before enabling parallel or evolutionary search. That
rule prevents premature multi-agent complexity, but "simple" can be read too
narrowly: one short context, one proof route, literature only after failure,
experiments only as a late fallback, and formalization only after an informal
proof appears complete. Such a loop is inexpensive but shallow and is not the
intended research system.

Long-horizon mathematics benefits from one coherent research lead that owns the
current problem interpretation, branch portfolio, unresolved obligations, and
synthesis across time. It also benefits from literature, experiments,
falsification, competing branches, and incremental formalization from the start.
Those capabilities do not require an always-on swarm and do not weaken the
central verifier boundary.

Parallel and evolutionary search have different risk profiles. Bounded
independent specialists can be useful when work decomposes cleanly or the
central loop has measurably stagnated. Evolutionary search is much easier to
misdirect: when fitness is a noisy model judgement, selection can amplify
persuasive errors and premise smuggling. It is defensible only when fitness is
cheap, reproducible, and strongly coupled to verified progress, such as
executable counterexample tests, numerical objectives with certificates, or
Lean-checkable subclaims.

## Decision

The baseline orchestration is one coherent long-horizon research lead plus a
centralized, independently reconstructed verifier. The lead may use multiple
live branches, literature retrieval, executable and numerical experiments,
counterexample search, representation changes, and incremental formalization
without promoting to a multi-agent tier. These are baseline research
capabilities, not evidence of truth.

Literature has two explicit purposes from the beginning of a run:

1. ideation, terminology discovery, prerequisites, contrasting approaches, and
   reusable results; and
2. reproducible novelty checking, including renamed or independently
   rediscovered results.

The two purposes retain separate traces and never create mathematical warrant.
Failure to find prior work is not evidence of novelty.

Formalization is incremental. Candidate definitions, statements, invariants,
and subclaims may be formalized as they mature. Lean or another proof assistant
is applied early to mature local claims and interfaces, not forced onto unstable
conceptual exploration and not deferred until the entire informal argument is
finished. Formal checking never implies semantic fidelity, novelty, or
significance.

Parallel specialists are a bounded overlay around the central lead, not a
replacement hierarchy. Activation requires a recorded prediction that task
structure or measured stagnation makes the overlay likely to improve verified
progress per unit cost. The activation record names the decomposable targets,
baseline window, stagnation or variance signal, verifier policy, budget, merge
rule, stop rule, and expected gain. Specialists receive scoped immutable inputs,
return attributed proposals, and cannot change trust state, redefine the target,
control the central verifier, or silently create more workers.

Every promoted regime is evaluated against the same task fixture and the
central-lead baseline. It is retained only while it improves verified progress
per unit cost, including expert review time and semantic-error cost. A regime
that fails its retention test is stopped; its useful artifacts and negative
results remain in the ordinary branch history.

Evolutionary search has an additional entry gate. Before activation it must
demonstrate:

- a cheap, deterministic or tightly calibrated fitness signal tied to an
  applicable verifier;
- adversarial tests showing that rhetorically persuasive but invalid candidates
  do not outrank valid ones;
- explicit diversity, population, generation, mutation, and total-cost bounds;
- isolation between candidate generation and central verification;
- no use of model confidence, model agreement, retrieval score, or unverified
  prose quality as a proof-fitness surrogate; and
- a benchmarked cost-adjusted gain over both the central lead and bounded
  parallel specialists.

Conceptual proof search with a noisy verifier is ineligible for evolutionary
selection. Failure of fitness calibration immediately demotes the run to the
central-lead baseline.

Material partial results continue to use the existing human-steering boundary.
When the system finds a significant partial theorem, counterexample, reduction,
or reusable method, it surfaces the attributed result and asks for steering; it
does not autonomously redirect the research objective or publish a significance
claim.

## Consequences

- The baseline is richer than a shallow single-thread loop while retaining one
  coherent owner of research state and one centralized verifier boundary.
- Multiple branches, literature, experiments, and incremental formalization do
  not by themselves authorize parallel agents or stronger warrants.
- Search tiers are capability overlays with explicit promotion and demotion,
  not a progression toward an always-on hierarchical swarm.
- Evolutionary search remains disabled for early conceptual work unless a later
  bounded slice supplies the required fitness and cost evidence.
- Existing sealed phases and the currently disabled search tiers are unchanged;
  this ADR refines the target architecture but activates no new runtime.

## Validation and revisit trigger

Any future search-tier implementation must include executable acceptance cases
for activation, non-activation, retention, demotion, budget exhaustion,
verifier-noise attacks, and preservation of partial progress. Revisit this
decision if measured work shows that centralized synthesis is itself a
bottleneck, but do not replace it merely because more workers improve raw
proposal count.
