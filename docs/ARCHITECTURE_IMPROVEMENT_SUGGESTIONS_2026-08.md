# Architecture Improvement Suggestions — Sol/Astra Budget Context

**Date:** 21 August 2026
**Status:** Proposal for discussion, not an ADR. If any of these are adopted they
should be recorded as their own ADR(s) per the repository's existing process,
following ADR-0027.
**Trigger:** A real $10,000 API budget and access to frontier models (Sol is
available; Astra is not — OpenAI paused it on 2026-08-07 pending Preparedness
Framework review, with no public API, pricing, or release date) change what is
worth building next. This document lists concrete, prioritized suggestions
rather than re-litigating the overall approach, which is covered in the
project's own `NOVELTY_LANDSCAPE.md`.

## Summary of the reasoning

The current roadmap (ADR-0026) sequences remaining work as Phase 4B
acquisition/parsing, then Phase 4C hybrid retrieval, then the noncommuting
Phase 5 expansion, then Phase 6 external evaluation — with multi-agent search,
embeddings, and proof search/repair all explicitly deferred pending "a later
explicit request and measured cost-adjusted gain" (`AGENTS.md`). That sequencing
was chosen when the honest expectation was near-zero live model spend. A real
budget doesn't invalidate the underlying principle — measured orchestration,
verification before trust, no capability added without evidence — but it does
mean the project can now afford to *generate* the evidence those gates are
waiting on, rather than deferring indefinitely. The suggestions below are
organized as: what to build to actually go after a real problem, what to
measure before building further, and what to harden given that real money and
a more capable, more agentic model are now in the loop.

## 1. Treat the model gateway swap as its own bounded slice

Move from the current `openai-gpt5-mini` pricing/capability path to Sol
(GPT-5.6 Sol: $2.50/M input, $15/M output, 1M context, 128K max output) as a
first, small, easily-reviewed change:

- A new versioned pricing snapshot following ADR-0008's pattern
  (`config/openai-gpt5.6-sol-pricing-<date>.json`), created explicitly and
  never fetched live, exactly as the existing snapshots work.
- A capability-check entry for Sol's larger context window and output ceiling.
  The Structured Outputs projection logic already deterministically infers
  types for provider-only `const`/`enum` terminals — this should be re-run
  against Sol's schema surface rather than assumed identical to the mini
  model's.
- No change to domain logic. This is exactly the swap the provider-neutral
  gateway was designed for; if it requires touching `domain/` or
  `application/`, that is itself a finding worth recording (a hidden
  model-specific assumption leaking through a port).
- Keep the config model-neutral per the blueprint's existing instruction —
  do not hard-code "Sol" as a name anywhere except the pricing snapshot and
  run configuration; Astra or a future model should be a config change only.

This is cheap, low-risk, and is the prerequisite for everything below.

## 2. Fund the orchestration measurement the blueprint has been deferring

"Measured orchestration: begin with a simple proposer–verifier loop and add
parallel or evolutionary search only when evaluation shows a gain" has been
true in principle but untested in practice — the live provider path is opt-in
and the acceptance suite runs on the deterministic scripted adapter. With
budget, this becomes affordable to actually measure:

- Reserve roughly $1,000–1,500 for a controlled comparison: run the existing
  single proposer / isolated-verifier loop (Phase 2) against a small set of
  real, bounded problems; run a second condition that adds one layer of
  decomposition (a root call that splits the problem, N sub-calls, one
  synthesis call — the closest cheap approximation of the hierarchical
  root/subagent pattern Astra is reported to use) against the same problems.
- Freeze the comparison protocol before running it (metrics, stopping rule,
  cost cap per condition) — this is exactly the discipline `EvaluationProtocol`
  and Phase 6's frozen-case pattern already require elsewhere in the repo, so
  it should reuse those mechanisms rather than being run ad hoc.
- Record cost-per-verified-step and cost-per-closed-obligation for each
  condition, not just solve/no-solve. A hierarchical loop that costs 4x for a
  2x quality gain is a real, fundable trade-off decision, not a foregone one.
- Only if this produces a measured gain should search tiers 2–4 (currently
  disabled in Phase 5) or a general multi-agent mode be built out. This keeps
  the existing principle intact; it just funds the missing measurement.

## 3. Prioritize a Lean proof-search/repair loop — the largest capability gap

Phase 3B today accepts a single, hand-supplied, restricted theorem and proof
fragment; it explicitly excludes proof search or repair, and premise
retrieval (`README.md`, Phase 3B section). This is the single biggest
structural difference between what AdaIvy can currently do and what both
Astra and AlphaProof Nexus actually rely on: generate a candidate, get Lean's
compiler feedback, repair, repeat, with the Lean kernel as the only trust
boundary.

Suggested shape, staying inside the existing trust boundaries (fail-closed
validator, hashed wrapper, sandboxed container, no host mount):

- Add a bounded *repair* loop around the existing sealed Lean adapter: on a
  rejected submission, feed the compiler's diagnostic output back to the
  model as a new, separately hashed proposal rather than a mutation of the
  rejected one, preserving the append-only result history that already
  exists.
- Consider adopting rather than building premise selection — LeanDojo/ReProver
  is already named as component-level prior art in `NOVELTY_LANDSCAPE.md`;
  the "adopt before rebuilding" principle applies directly here.
- Cap repair attempts per obligation with an explicit, budgeted counter,
  following the same pattern as the synthesis slice's per-run bounds and
  exploration-reserve enforcement, so a stuck proof cannot silently consume
  the run's budget.
- This is a genuine new ADR (next available: ADR-0028), since it changes
  Phase 3B's scope, which AGENTS.md currently states adds "no proof search or
  repair" — that boundary needs to be explicitly revised, not quietly crossed.

This is the change most directly responsible for whether AdaIvy could ever
produce something resembling Astra's output, as opposed to only checking
proofs a human already found.

## 4. Bring literature grounding forward, but keep it evidence, not memory

Phase 3A is manually-supplied plain text only; Phase 4B/4C (crawling,
embeddings, hybrid retrieval) are deferred. That deferral made sense against
the original 2010 quantum-discrimination benchmark, where the source set is
small and fixed. It stops making sense the moment the target is a real,
current open problem, because the system's entire premise is that model
recall of a citation is not evidence — only a source-backed, applicability-
checked claim is. Suggested sequencing:

- Do not wait for the full Phase 4C hybrid-retrieval build. A narrower slice
  — licensed/permitted acquisition of the specific papers relevant to whatever
  problem(s) get selected (see §6), parsed through a real PDF path instead of
  the current quarantine-and-skip behavior — is enough to support one or two
  real attempts and is far cheaper than general-purpose crawling.
- Keep the FTS5/BM25 deterministic retrieval and citation-validation machinery
  exactly as designed; the gap is acquisition and parsing coverage, not the
  retrieval model itself.
- Resist the temptation to let Sol's parametric knowledge substitute for this.
  A more fluent model is more convincing when it misquotes or misapplies a
  real theorem, which is precisely the "retrieval removes crude hallucination,
  not subtle misuse" failure mode the project's own novelty review already
  flags from Aletheia's experience.

## 5. Harden budget/cost governance now that spend is real

The persisted-budget and versioned-pricing infrastructure (Phase 2) and the
enforceable exploration reserve (synthesis slice) were built and tested
against small or synthetic numbers. Before any run touches real credit:

- Add an explicit hard-stop integration test: a live-adapter run that hits its
  persisted budget mid-job actually halts rather than merely under-reporting
  cost afterward.
- Re-derive the exploration-reserve arithmetic against Sol's real per-token
  cost (output tokens at $15/M materially changes the ratio between
  cheap-exploration and expensive-verification spend compared to the mini
  model's pricing).
- Log cost per phase (generation, formalization, Lean checking, retrieval) as
  a first-class metric from the start, not reconstructed after the fact —
  this is what will make any future "was the orchestration experiment in §2
  worth it" comparison possible.

## 6. Pick a small, deliberate portfolio of real targets

The existing quantum-state-discrimination benchmark should stay as the
regression/trust test — it is well-understood and already has an independent
exact reference to check against. It is not, itself, a novel-research target.
Suggested allocation of the $10,000 rather than committing it to one attempt:

- 2–3 candidate real problems, chosen the way OpenAI's own selection appears
  to have worked: narrow, well-scoped, open for years rather than famous
  headline conjectures, where a correct partial result or reduction is still
  a meaningful outcome.
- A rough budget split: reserve for the §2 orchestration measurement, reserve
  for the §3 Lean repair-loop build/shakedown, and the remainder split across
  the chosen problems with a hard per-problem cap enforced by the Phase 2
  budget mechanism — so one expensive dead end cannot consume the whole
  allocation before a second problem is even attempted.

## 7. Keep — and lean harder on — the epistemic governance layer

None of the above is a reason to relax semantic-alignment, applicability, or
verifier-isolation checks to move faster. A more capable, more agentic model
produces more fluent wrong answers, not fewer, and premise-smuggling gets
harder to catch by eye as fluency increases. If anything, the fact that Astra
itself was paused over agentic capability concerns (not math) is a reminder
to keep the sandboxed-execution and fail-closed defaults intact as autonomy
and model capability both go up — this is exactly the kind of moment those
controls were designed for, not a reason to loosen them for speed.

## 8. Documentation follow-ups

- Add OpenAI's Astra to `NOVELTY_LANDSCAPE.md` as new, highly relevant prior
  art — it is the strongest existing validation of "generate informally, then
  use Lean as the sole trust boundary," and it raises the bar on what
  "success" needs to look like (genuine open-problem solves, not just
  architecture).
- Flag explicitly, next to that entry, that it is unrelated to the
  `AstrumDrive/ASTRA` project already cited in the same document — pure name
  collision, easy to introduce a confused citation later if not noted once,
  clearly, at the point both names appear.
- Record the model-gateway swap (§1) and any Phase 3B scope change (§3) as
  their own ADRs per the existing process, rather than as informal config
  changes.

## Suggested sequencing

1. Model gateway swap to Sol (§1) — cheap, low-risk, unblocks everything else.
2. Orchestration measurement (§2) and Lean repair-loop build (§3) in parallel
   — they are independent and both gate later spend decisions.
3. Targeted literature acquisition for the chosen problem(s) (§4) once at
   least one candidate problem is selected.
4. Budget-governance hardening (§5) before, not after, the first real-money
   run against a chosen problem.
5. Problem attempts (§6), governed by everything above.
6. Documentation updates (§8) can happen at any point but should not slip
   past the point where a decision has actually been made and needs an ADR.
