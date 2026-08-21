# Architecture Improvement Suggestions — Sol/Astra Budget Context

**Date:** 21 August 2026
**Revised:** 21 August 2026, against the tree at ADR-0039. See "Revision note".
**Status:** Proposal for discussion, not an ADR. If any of these are adopted they
should be recorded as their own ADR(s) per the repository's existing process.
The next free number is **ADR-0040**.
**Trigger:** A real $10,000 API budget and access to frontier models (Sol is
available; Astra is not — reported paused on 2026-08-07 pending Preparedness
Framework review, with no public API, pricing, or release date) change what is
worth building next. This document lists concrete, prioritized suggestions
rather than re-litigating the overall approach, which is covered in the
project's own `NOVELTY_LANDSCAPE.md`.

## Revision note

The first draft was written against ADR-0027 as the tip and proposed ADR-0028
as the next free number. Twelve ADRs have landed since. Four of the eight
sections were substantially overtaken by work already accepted, and one
carried wrong pricing. Original text is kept below so the reasoning stays
auditable; each section now opens with a **Status** line stating what is
actually true of the tree.

| § | Subject | Status |
|---|---|---|
| 1 | Model gateway swap | **Landed and exceeded** — ADR-0030, ADR-0037, ADR-0038 |
| 2 | Orchestration measurement | **Superseded** — ADR-0029 sets a different baseline and gate |
| 3 | Lean proof-search/repair loop | **Open.** The one substantive build left |
| 4 | Literature grounding | **Landed** — ADR-0028 acquisition/parsing, ADR-0031 benchmark-scoped 4C |
| 5 | Budget/cost governance | **Mostly landed** — two narrow gaps remain |
| 6 | Portfolio of real targets | **Open** — an owner decision, not a build |
| 7 | Epistemic governance | **Standing.** No change requested or needed |
| 8 | Documentation follow-ups | **Partly open** — one item blocked on a citation |

The pricing figures in the original §1 and §5 were wrong by 4.4x on input and
3.3x on output. Corrected in place below, with the original numbers struck
through rather than deleted.

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

**Revised:** of that list, acquisition/parsing and hybrid retrieval have since
landed, and the orchestration question has been answered by ADR-0029 in a
different shape than §2 assumed. Proof search/repair is the remaining
deferral, and is now the whole of the critical path.

## 1. Treat the model gateway swap as its own bounded slice

> **Status: landed and exceeded.** ADR-0030 admitted **seven** providers behind
> the Phase 2 `ModelGateway` port, not a single swap: OpenAI, Azure OpenAI,
> Bedrock, Anthropic, MiniMax, Qwen/DashScope, and DeepSeek. ADR-0037 confirmed
> the five placeholder pricing snapshots. ADR-0038 fixed `--provider` on the run
> path, where `start`/`advance` had accepted only `("fake", "openai")` and
> `_loop` routed every non-fake provider to OpenAI's adapter. The Sol snapshot
> already exists at `config/azure-openai-gpt5-6-sol-pricing-2026-08-21.json`.
>
> Two details of the original text were wrong. The provider is **`azure_openai`,
> not `openai`**, so the suggested filename `config/openai-gpt5.6-sol-pricing-…`
> would have been misfiled. And the rates are not the ones quoted — see below.
>
> The section's closing claim that this is "the prerequisite for everything
> below" no longer holds: it is done, and it gated nothing that has not since
> shipped.

Move from the current `openai-gpt5-mini` pricing/capability path to Sol
(GPT-5.6 Sol: ~~$2.50/M input, $15/M output~~ **$11.00/M input, $49.50/M
output**, 1M context, 128K max output) as a first, small, easily-reviewed
change:

- A new versioned pricing snapshot following ADR-0008's pattern
  (~~`config/openai-gpt5.6-sol-pricing-<date>.json`~~
  **`config/azure-openai-gpt5-6-sol-pricing-2026-08-21.json`**), created
  explicitly and never fetched live, exactly as the existing snapshots work.
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

~~This is cheap, low-risk, and is the prerequisite for everything below.~~

### Correction: the recorded Sol rates

The snapshot records **$11.00/M input and $49.50/M output**, sourced from the
Azure retail prices API capture of 2026-08-21. Those are the *LongCo Data Zone*
meters — deliberately the highest standard-tier pair on the price list — chosen
because:

- the deployment scope is picked by `AZURE_OPENAI_DEPLOYMENT` and the adapter
  cannot know whether Global ($10.00/$45.00) or Data Zone applies; and
- the price list does not state the context-tier boundary, so ShortCo
  ($5.00/$30.00 Global, $5.50/$33.00 Data Zone) cannot be *ruled out* but also
  cannot be relied on at the budget's 20000-token input cap.

The priority-processing meters ($11.00/$66.00) never apply: the adapter
requests no service tier.

This is the conservative direction for a budget guard, and it is the number all
downstream arithmetic must use. At $49.50/M output, the $10,000 budget is
roughly **202M output tokens gross** — not the ~660M implied by $15/M.

## 2. Fund the orchestration measurement the blueprint has been deferring

> **Status: superseded by ADR-0029**, which answers this question in a different
> shape. The experiment as designed is **not** compatible with the accepted
> decision and should not be run as written.
>
> ADR-0029 moved the baseline. It is no longer "a simple proposer–verifier
> loop": the baseline is one coherent long-horizon **research lead** plus a
> centralized, independently reconstructed verifier, and that lead *already*
> has multiple live branches, literature retrieval, executable and numerical
> experiments, counterexample search, representation changes, and incremental
> formalization — all without promoting to a multi-agent tier. So the
> "condition A" this section wants to measure against is a strawman relative
> to what the architecture now specifies.
>
> The proposed "condition B" — a root call that splits the problem, N sub-calls,
> one synthesis call — is the pattern ADR-0029 explicitly rules out: *"Never
> substitute an always-on hierarchical swarm."* Bounded specialists are
> permitted, but as an overlay requiring a recorded activation record naming the
> decomposable targets, baseline window, stagnation or variance signal, verifier
> policy, budget, merge rule, stop rule, and expected gain. Specialists receive
> scoped immutable inputs, return attributed proposals, and cannot change trust
> state, redefine the target, control the central verifier, or silently create
> more workers.
>
> The section's instinct to freeze the protocol before running is right, and
> matches the standing rule against tuning anything after seeing the fixtures.
> Reuse it — but as an ADR-0029 activation record measured against the
> central-lead baseline, not as the two-condition comparison sketched here.
>
> Minor factual fix: search tiers 2–4 are disabled **globally** (`AGENTS.md`
> lines 23, 73, 152), not "in Phase 5". Phase 5 is one place the disablement is
> restated, not its scope.

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
  disabled ~~in Phase 5~~ **globally**) or a general multi-agent mode be built
  out. This keeps the existing principle intact; it just funds the missing
  measurement.

## 3. Prioritize a Lean proof-search/repair loop — the largest capability gap

> **Status: open, and the only substantive build remaining.** No ADR since
> ADR-0016 touches Phase 3B's scope. This section's diagnosis survives review
> intact and its ADR number moves from 0028 to **0040**.
>
> ADR-0029 strengthens the case rather than weakening it: it makes formalization
> *incremental*, with Lean "applied early to mature local claims and interfaces,
> not forced onto unstable conceptual exploration and not deferred until the
> entire informal argument is finished." A per-obligation repair loop is what
> incremental formalization needs in order to be more than aspirational. But
> ADR-0029 does not itself authorize the loop, so the scope change is still a
> new decision record.
>
> One bullet is already project policy rather than a suggestion: adopting
> premise selection before rebuilding it is stated at
> `TECHNICAL_BLUEPRINT.md:294` ("Lean retrieval and proof search | LeanDojo,
> LeanSearch, and available Lean agents | Premise selection, compiler feedback,
> proof repair") and again at `:1393`. It should be cited as the governing
> instruction, not re-argued.

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
  the "adopt before rebuilding" principle applies directly here. **This is
  already the blueprint's standing instruction, not an open choice.**
- Cap repair attempts per obligation with an explicit, budgeted counter,
  following the same pattern as the synthesis slice's per-run bounds and
  exploration-reserve enforcement, so a stuck proof cannot silently consume
  the run's budget.
- This is a genuine new ADR (next available: ~~ADR-0028~~ **ADR-0040**), since
  it changes Phase 3B's scope, which AGENTS.md currently states adds "no proof
  search or repair" — that boundary needs to be explicitly revised, not quietly
  crossed.

This is the change most directly responsible for whether AdaIvy could ever
produce something resembling Astra's output, as opposed to only checking
proofs a human already found.

## 4. Bring literature grounding forward, but keep it evidence, not memory

> **Status: landed.** This section's recommendation — a narrow, problem-scoped
> slice instead of general-purpose crawling — is what happened.
>
> ADR-0028 accepted authorized acquisition plus isolated rich-parser ports over
> Phase 4 content objects, explicitly rejecting both an unrestricted
> crawler/parser pipeline and downloading directly into Phase 3A (which "makes
> revocable bytes immutable and undeletable"). ADR-0031 then scoped Phase 4C to
> the benchmark rather than building general hybrid retrieval. All seven Phase
> 4C gates now hold, and ADR-0032 split the self-disclaimer exclusion out of
> `fusion` into its own module.
>
> The third bullet — do not let Sol's parametric knowledge substitute for
> source-backed retrieval — is not a build item and remains permanently in
> force. It is the same concern as §7.

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

> **Status: mostly landed; two narrow gaps remain.**
>
> The section's stated worry — a run that "merely under-reports cost afterward"
> — is structurally impossible in the current design. Budget is **reserved
> before the call**, not reconciled after it: `reserve_call` raises
> `BudgetExhausted` across all five dimensions (attempts, input tokens, output
> tokens, cost, wall time), pinned by
> `tests/test_phase2_workspace.py::test_each_budget_dimension_prevents_further_calls`
> and `tests/test_phase2_model_loop.py::test_exhausted_budget_prevents_gateway_call`,
> which asserts `gateway.call_count == 0`. ADR-0038 additionally made an
> unconfirmed pricing snapshot a fail-closed live-gate refusal
> (`pricing_snapshot_unconfirmed:<id>`).
>
> **Gap 1 (narrow):** every one of those tests drives the scripted/fake
> gateway. There is no equivalent exercised against a live adapter. Given
> reserve-before-call, this is a lower-severity gap than the section implies —
> it tests the adapter wiring, not the guard.
>
> **Gap 2 (real):** per-phase cost attribution does not exist. Nothing in
> `src/` records cost split by generation, formalization, Lean checking, or
> retrieval. This is worth building *before* the §3 repair loop, because a
> repair loop is precisely the thing whose cost you will want attributed
> separately, and it cannot be reconstructed afterward.
>
> **The second bullet is void as written** — it re-derives the reserve against
> $15/M output, a rate 3.3x below the recorded $49.50/M. Re-deriving against a
> rate that cheap would loosen the guard in the exact direction a budget guard
> must not be loosened. Use $11.00/$49.50.

The persisted-budget and versioned-pricing infrastructure (Phase 2) and the
enforceable exploration reserve (synthesis slice) were built and tested
against small or synthetic numbers. Before any run touches real credit:

- Add an explicit hard-stop integration test: a live-adapter run that hits its
  persisted budget mid-job actually halts rather than merely under-reporting
  cost afterward.
- Re-derive the exploration-reserve arithmetic against Sol's real per-token
  cost (output tokens at ~~$15/M~~ **$49.50/M** materially changes the ratio
  between cheap-exploration and expensive-verification spend compared to the
  mini model's pricing).
- Log cost per phase (generation, formalization, Lean checking, retrieval) as
  a first-class metric from the start, not reconstructed after the fact —
  this is what will make any future "was the orchestration experiment in §2
  worth it" comparison possible.

## 6. Pick a small, deliberate portfolio of real targets

> **Status: open, and an owner decision rather than a build.** Nothing in the
> tree selects or forecloses targets. The regression role of the
> quantum-state-discrimination benchmark is unchanged and is now stronger than
> when this was written: ADR-0033/0035 added exact algebraic certificates for
> the noncommuting case with verification held strictly separate from
> discovery, and ADR-0034 added thirteen generality controls, all thirteen
> flipping.
>
> The budget arithmetic in this section should be redone against $11.00/$49.50
> before any split is committed to. The $1,000–1,500 reserved in §2 buys
> roughly a third of what the original figures implied.
>
> One caution on the first bullet: "chosen the way OpenAI's own selection
> appears to have worked" rests on the unverified Astra reporting flagged in §8.
> It is a reasonable heuristic on its own merits — narrow, long-open, partial
> results still meaningful — and should be argued on those merits rather than
> by appeal to a source the repository cannot cite.

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

> **Status: standing. No change requested, and none should be made.** Recorded
> here as a constraint on §3, which is the section most able to erode it: a
> repair loop that feeds compiler diagnostics back to a model is a new channel
> by which a rejected argument can be reshaped until it passes, and the
> separately-hashed-proposal requirement in §3 exists precisely to keep that
> channel auditable.
>
> ADR-0035 sharpens one point this section does not make. Sealed Phase 5 accepts
> an identical originating and creating principal, so when one principal derives
> a noncommuting certificate and the same principal approves its admission, no
> independent party stands between derivation and trust record. What contains
> that is mathematical, not procedural: a zero-gap certificate is self-verifying
> against the ensemble. Any §3 analogue must be able to make the same claim —
> Lean's kernel is the container — or it does not get the same latitude.

None of the above is a reason to relax semantic-alignment, applicability, or
verifier-isolation checks to move faster. A more capable, more agentic model
produces more fluent wrong answers, not fewer, and premise-smuggling gets
harder to catch by eye as fluency increases. If anything, the fact that Astra
itself was paused over agentic capability concerns (not math) is a reminder
to keep the sandboxed-execution and fail-closed defaults intact as autonomy
and model capability both go up — this is exactly the kind of moment those
controls were designed for, not a reason to loosen them for speed.

## 8. Documentation follow-ups

> **Status: partly open. The first item is blocked on a citation.**
>
> The name-collision point (second bullet) is real and unaddressed:
> `NOVELTY_LANDSCAPE.md:35` cites `ASTRA` as
> `https://github.com/AstrumDrive/ASTRA`, and `:36` cites AlphaProof Nexus at
> `arxiv.org/abs/2605.22763`. OpenAI's Astra appears nowhere. So the collision
> has not yet been introduced — but it will be the moment an Astra entry is
> added, which is exactly why the note should go in at the same time.
>
> **The first bullet cannot be executed as written.** Every entry in
> `NOVELTY_LANDSCAPE.md` carries a resolvable citation. This document's Astra
> claims — the 2026-08-07 pause, the Preparedness Framework review, the
> hierarchical root/subagent pattern, the open-problem solves — are not
> sourced anywhere in the repository, and are not independently verifiable
> from the assistant's knowledge (cutoff May 2026). Sol is corroborated
> in-tree by the owner's own Azure retail-price capture; Astra is not
> corroborated anywhere.
>
> By the project's own standard — model recall of a citation is not evidence,
> only a source-backed claim is (§4, and `NOVELTY_LANDSCAPE.md:64`) — an Astra
> entry written from this document's prose would be precisely the failure the
> standard exists to prevent, committed in the file that defines the standard.
> **Blocked pending a citable source from the owner.** The third bullet is
> discharged: ADR-0030/0037/0038 recorded the gateway work, and §3's scope
> change is queued as ADR-0040.

- Add OpenAI's Astra to `NOVELTY_LANDSCAPE.md` as new, highly relevant prior
  art — it is the strongest existing validation of "generate informally, then
  use Lean as the sole trust boundary," and it raises the bar on what
  "success" needs to look like (genuine open-problem solves, not just
  architecture). **Blocked: needs a citable source.**
- Flag explicitly, next to that entry, that it is unrelated to the
  `AstrumDrive/ASTRA` project already cited in the same document — pure name
  collision, easy to introduce a confused citation later if not noted once,
  clearly, at the point both names appear.
- ~~Record the model-gateway swap (§1) and any Phase 3B scope change (§3) as
  their own ADRs per the existing process, rather than as informal config
  changes.~~ **Done for §1 (ADR-0030, ADR-0037, ADR-0038); §3 is queued as
  ADR-0040.**

## Suggested sequencing

~~The original six-step sequence assumed §1 was unbuilt and §2/§3 were
independent peers. Both premises are gone.~~ Revised:

1. **ADR-0040: bounded Lean repair loop (§3).** The only substantive build
   left, and the whole critical path.
2. **Per-phase cost attribution (§5, gap 2)** — ideally landed *with* or just
   *before* step 1, because repair-loop cost is the first thing anyone will
   want attributed separately and it cannot be reconstructed after the fact.
3. **Re-derive the exploration reserve against $11.00/$49.50 (§5)**, replacing
   the void $15/M derivation, before any real-money run.
4. **Select targets (§6)** — an owner decision, unblocked by the above, and the
   input that determines which papers §4's acquisition path should pull.
5. **ADR-0029 activation record (§2)**, if and only if the central-lead
   baseline shows measured stagnation. Not the two-condition experiment as
   originally drafted.
6. **Documentation (§8):** the collision note lands with any Astra entry; the
   entry itself waits on a citation.

Dropped from the original sequence: step 1 (gateway swap, done), step 3
(targeted acquisition, done), and the live-adapter budget test, which
reserve-before-call demotes from blocker to ordinary coverage.
