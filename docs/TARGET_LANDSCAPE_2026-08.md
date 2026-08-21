# Candidate Research Targets for AdaIvy — Landscape and Recommendations

**Compiled:** 21 August 2026
**Scope:** Selection of a second benchmark problem class, given the constraint that
targets be approachable, precisely formalizable, and consequential if resolved.
**Selection inputs (stated by owner):** audience = working mathematicians *and*
AI-for-math community *and* non-specialist/investor; domain = new,
finite/combinatorial; success bar = a publishable new fact **and** demonstrating
the system catches what others miss.

This is a target-selection review, not an endorsement of any particular result.
Every "open" status below is a claim about the literature as of the compile date
and must be re-checked immediately before committing effort — §7 explains why that
caveat is unusually load-bearing right now.

---

## 0. Executive summary

Three findings drive everything else.

**(a) The bar moved, and it moved away from "solve a hard problem."** As of
August 2026, solving an Erdős problem is not a news event. OpenAI's Astra
reported ten named-conjecture resolutions — including Connes's rigidity
conjecture and Ehrhart's volume conjecture — all Lean-formalized, for roughly
$2,000 of compute (1 Aug 2026). AlphaProof Nexus reports "a few hundred dollars"
per solved Erdős problem. AdaIvy has no search advantage over these systems and
should not compete on search.

**(b) The bar moved *toward* what AdaIvy is actually built for.** DeepMind's own
audit of Aletheia over ~700 open Erdős problems: 212 candidate resolutions
returned, **31.5% technically correct, 6.5% meaningfully correct, 68.5%
fundamentally flawed** — and the authors state plainly that *literature
verification proved harder than mathematical verification*. Tao's write-up of
Erdős #1026 documents AI deep-research tooling failing to find a 2016 paper that
plain Google Scholar found in minutes. The Leiden Declaration (published 2 June
2026, IMU-endorsed, ~1,854 signatories) formalizes a community expectation of
AI-use disclosure, peer review before announcement, and literature diligence,
with Goldberg naming the core fear: "cluttering the literature with claimed
results that are simply wrong."

Verification, provenance, and novelty-checking are now the scarce goods. That is
precisely and exactly AdaIvy's `SemanticAlignmentRecord` /
`LiteratureApplicabilityRecord` / evidence-non-escalation stack. **Target
selection should exploit the scarcity, not fight the abundance.**

**(c) ⚠️ The current benchmark's headline question appears to be settled in the
literature.** See §1. This needs attention before anything else, and it is also
free demonstration material.

**Recommended portfolio** (detail in §3–§6):

| Lane | Target | Why it fits | Risk |
|---|---|---|---|
| **A — primary** | Brankov–Hansen–Stevanović: 38 open conjectured upper bounds on the Laplacian spectral radius, verified exhaustively only to n ≤ 9 | 38 named, LAA-published conjectures; one harness settles all 38; exact integer char. poly + Sturm, zero floating point; a *certified exhaustion* is publishable even with no kill | Medium. Two prior RL attacks failed on these 38, which cuts both ways |
| **B — differentiator** | Adversarial re-verification of fresh, self-declared-unverified computational proof candidates and of the ⚪/🔴 buckets in Tao's AI-contributions wiki | This is the "catch what others miss" bar, literally. Hits all three audiences at once | Low technical risk, moderate social risk (see §4.4) |
| **C — cheap, on-narrative** | Graffiti #322 / #197 definitional resolution — Roucairol–Cazenave state *in print* that under one reading of "range" one of the two dies, and leave it unresolved | A semantic-alignment failure sitting unresolved in the published record. Small note, direct architectural demonstration | Low |
| **D — warm-up** | Graffiti.pc Hamiltonian-path family (#190a, #199 + ~13 siblings) — one search harness, 15 named targets, cheapest possible verification | Throughput per engineering hour; builds the finite-combinatorial plugin | Low |

Explicitly **not** recommended: erdosproblems.com as a primary hunting ground,
6-chromatic Hadwiger–Nelson, no-three-in-line, kissing-number lower bounds, and
the Zauner/SIC lane. Reasons in §8.

---

## 1. ⚠️ Prior-art alert on the existing quantum benchmark

The README states the first end-to-end benchmark asks "whether the [JRF]
iteration always reaches a global optimum under precisely stated assumptions."
Two papers appear to settle this for pure states:

- **Nakahira, Kato & Usuda**, *Iterative methods for finding optimal quantum
  measurements under minimum-error and minimax criteria*, Phys. Rev. A **91**,
  012318 (2015) — states that for a **linearly independent pure state set**,
  the Ježek et al. algorithm converges to an optimal measurement.
- **Xin Lü & Shi-Hai Dong**, *Iterative algorithm for minimum-error quantum state
  discrimination: Convergence for pure-state ensembles*, Phys. Rev. A **113**,
  022451, published **26 February 2026** (DOI 10.1103/q7wq-ygm9). Verified
  directly against the APS abstract page: represents an n-outcome POVM as a block
  column vector, identifies each update as a partial isometry from a polar
  decomposition, proves the guessing probability increases monotonically, and
  **"prove[s] the convergence of the algorithm for arbitrary ensembles of pure
  states under a mild initialization condition on the supports of the states."**
  No arXiv preprint exists; the paper is paywalled — which is exactly the kind of
  source an arXiv-biased novelty check misses.

**Implications.**

1. The benchmark's headline claim is stale as written. It should be re-scoped
   and the two papers cited as prior art. The residual open questions are
   sharper and better:
   - **mixed-state monotonicity** — is P_succ monotone along the iteration for
     non-pure ρ_j at all? A numerical counterexample is a publishable negative
     result and is exactly-checkable from a rational ensemble in one step.
   - **a diluted JRF with a proved global convergence theorem for mixed states.**
     The template exists: the undiluted RρR iteration in ML tomography is known
     *not* to be globally convergent, dilution (Řeháček–Hradil–Knill–Lvovsky,
     PRA 75, 042108) repairs it, and Gonçalves et al. (arXiv:1306.3057, QIC 14,
     966) proved global convergence of the diluted version. Nobody has done the
     analogous work for JRF.
   - **rate.** No convergence rate is proved in *any* regime, including the
     closed pure-state cases.
2. Do not read this as a setback. A system whose stated purpose is preventing
   "novelty and significance recorded as `not_assessed` from being quietly
   promoted" has just had its own flagship benchmark caught by an ordinary
   literature sweep. Running AdaIvy's own novelty machinery over its own
   benchmark, in public, and having it produce the correct `LiteratureApplicability`
   verdict, is a **better** demonstration than a clean result would have been.
   Phase 6's generality-control suite already has the shape for this.

---

## 2. Selection criteria, derived from what AdaIvy actually is

A target is a good AdaIvy target to the extent it scores on these. They are
deliberately different from "is it a hard problem."

1. **Exact-certificate closure.** Progress is a finite object checkable in exact
   integer/rational/algebraic arithmetic. No floating point anywhere in the
   trust path. (Rules out asymptotics, infinite-dimensional limits, and anything
   whose certificate is a numerical optimum.)
2. **Non-escalation has teeth.** The natural failure mode is exactly the one the
   data model forbids: "we swept to n = 11, therefore it's true." A target where
   an exhaustive finite sweep is *the* evidence is a target where AdaIvy's
   evidence-type separation is load-bearing rather than decorative.
3. **Named and citable.** A conjecture attributed to a person, published in a
   real venue. Auto-generated conjectures with no human conjecturer (e.g. the
   2.5M-conjecture Progressive-GNRPA corpus) are near-worthless for attention.
4. **Definitional hazard present.** Counter-intuitively, targets where the
   literature disagrees about what a term means are *better* for AdaIvy, because
   semantic custody is the differentiator. Most systems either trip on these or
   silently pick a reading.
5. **Low contest density.** The competitive window on well-known,
   certificate-verifiable, finite-dimensional problems is now measured in weeks
   (see §7).
6. **Honest terminal outcomes are all publishable.** A certified exhaustion with
   no counterexample must be a *deliverable*, not a failure — otherwise the
   architecture's "proof, counterexample, conditional result, or named
   obstruction" stance is untested.

---

## 3. Lane A — Exhaustive certification (primary recommendation)

### A1. Brankov–Hansen–Stevanović: 38 open Laplacian spectral-radius bounds ★

**The conjectures.** Let μ = λ₁(L(G)), d_v = deg(v), m_v = average degree of the
neighbours of v. Two families:

- Group 1: μ ≤ max_{v∈V} f(d_v, m_v)
- Group 2: μ ≤ max_{v_i ∼ v_j} f(d_i, m_i, d_j, m_j)

68 specific f were published in V. Brankov, P. Hansen & D. Stevanović,
*Automated conjectures on upper bounds for the largest Laplacian eigenvalue of
graphs*, Linear Algebra Appl. (2006). Examples of ones reported still open:
`max_v √(4d_v³/m_v)`, `max_v √(m_v² + 3d_v²)`, `max_v √(d_v(m_v + 3d_v))`,
`max_{i∼j} 2(d_i+d_j) − (m_i+m_j)`, `max_{i∼j} √(d_i² + d_j² + 2m_i m_j)`.

**Reported status.** 38 of the 68 remain open. The open/closed ledger is
Appendix B of Ghebleh, Al-Yakoob, Kanso & Stevanović, *Reinforcement learning
for graph theory I* (arXiv:2403.18429 → Discrete Appl. Math. 2025), which states
that 38 conjectured bounds are still open after those computational attacks. A
follow-up parallelized attack (arXiv:2509.01607) added kills on bounds 2, 32, 61.
Taieb–Roucairol–Cazenave–Harutyunyan (2026, Springer LNCS
doi:10.1007/978-3-032-09156-7_4) refuted 2 more but the abstract does not name
which.

> **Verification debt before starting.** I could not confirm the "38 open" count
> from the arXiv abstract page — it lives in Appendix B of the full PDF. Step
> zero is: pull the full arXiv:2403.18429 PDF, extract Appendix B verbatim, and
> obtain the Taieb et al. chapter to identify which two they killed. Do not
> start compute before this is a frozen, hashed artifact.

**Why this is the best fit on the list.**

- **Verification horizon is embarrassingly low.** The original 2006 paper checked
  all connected graphs on ≤ 9 vertices. Two RL/cross-entropy campaigns since then
  searched heuristically and found nothing on these 38. *Nobody appears to have
  run an exact exhaustive sweep at n = 10, 11, 12.* Connected graphs: n=10 →
  1.17×10⁷ (seconds); n=11 → 1.01×10⁹ (hours); n=12 → 1.64×10¹¹ (days, with geng
  streaming and early rejection).
- **The arithmetic profile is exactly AdaIvy's.** μ is the largest root of the
  integer Laplacian characteristic polynomial — exact isolation via
  Sturm/Descartes to arbitrary rational precision. The RHS is a max over
  vertices or edges of a nested-radical expression in rationals (m_v =
  (Σ_{u∼v} d_u)/d_v). Comparing an algebraic number to a nested radical is
  exactly decidable. Zero floating point in the trust path.
- **One harness, 38 named targets.** Each is attributed to Brankov, Hansen and
  Stevanović and published in LAA.
- **Both outcomes ship.** A kill = a publishable new fact against a named
  conjecture. No kill = a certified, replayable exhaustion artifact extending the
  verification horizon from n ≤ 9 to n ≤ 11 or 12 across 38 conjectures
  simultaneously — and the precedent that such artifacts are publishable is
  three weeks old (see A2).
- **Non-escalation is the whole point.** The output claim is *"no counterexample
  exists among connected graphs on ≤ 12 vertices,"* full stop — not *"the
  conjectures are probably true."* Enforcing that distinction structurally is
  the demonstration.

**Estimated kill probability across the batch:** meaningful but not high; two
targeted RL campaigns already failed on these, which is weak evidence the easy
counterexamples are gone — and also weak evidence that heuristic search is the
wrong tool and exhaustion is the right one. **Contest density: low.**

### A2. The precedent that makes "certified negative result" a deliverable

Julius Tranquilli, arXiv:2608.02675 (August 2026): a certified exhaustive
computation on the **Erdős–Gyárfás conjecture** (every graph of minimum degree 3
has a cycle whose length is a power of 2), raising the cubic-bipartite lower
bound from 30 to 60 vertices, with **two independently implemented exact oracles
plus a static witness certificate**. No counterexample found; published anyway.

This is the template. It is also, structurally, a weaker version of what AdaIvy
emits by construction — AdaIvy adds canonical serialization, content hashes,
frozen inputs, and byte-for-byte offline replay on top. If the Lane A artifact
is written up the way Tranquilli's was, the differentiator is legible without
having to argue for it.

The gold-standard reference architecture for the whole emit-chain is
**EmptyHexagonLean** (Subercaseaux, Nawrocki, Gallicchio, Codel, Carneiro, Heule,
ITP 2024, arXiv:2403.17370): SAT → DRAT → a Lean proof that the *encoding* is
correct. That last step — verifying that the finite computation actually models
the mathematical statement — is the semantic-alignment gap AdaIvy claims to
close, and there is a worked example of doing it properly.

---

## 4. Lane B — Adversarial re-verification (the differentiator)

This lane is where the selected success bar ("catching what others miss") is
met most directly, and it is the only lane that lands with all three audiences
simultaneously: mathematicians are actively anxious about exactly this (Leiden
Declaration), the AI-for-math community names literature/semantic verification as
the unsolved piece (DeepMind's own audit), and the story compresses to one
legible sentence for a non-specialist.

There are four concrete queues, in descending order of fit.

### B1. The ⚪ unverified and 🔴 incorrect buckets of Tao's AI-contributions wiki ★

`github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erdős-problems`
maintains colour-coded status per claim: 🟢 full resolution / 🟡 partial /
🔴 incorrect / ⚪ unverified. It also separates section 1(a) *AI standalone* from
1(b) *AI result, literature found afterwards* — i.e. it already implements, by
hand, a crude version of AdaIvy's novelty/verification separation.

The 🔴 bucket (problems reported as 11, 51, 233, 358, 616, 647, 888, 963, 1041,
1044) is a labelled corpus of real failure modes — better adversarial acceptance
test material than anything project-authored, and directly addresses the honest
limitation stated in the README that the Phase 6 control corpus is
project-authored and therefore "not evidence of generality against unseen traps."

The ⚪ bucket is a public queue of claims awaiting exactly the service AdaIvy
provides, maintained by the most visible mathematician in this space.

**This is the single highest-leverage item in the whole report** and it is not a
research problem — it is a *deployment* of the existing machinery against
externally-authored, externally-labelled traps. It converts the Phase 6 control
suite from "we built our own traps and passed them" into "we passed traps we did
not write." Do this even if nothing else here is adopted.

### B2. Fresh, self-declared-unverified computational proof candidates

- **Reinhardt maximum-perimeter small polygon at n = 16, 32, 64** —
  arXiv:2608.08001, August 2026, titled as *Computer-Assisted Proof Candidates*.
  The authors reportedly state the results have not received independent human
  expert review and label them proof candidates rather than theorems. The
  certificate is pure exact integer arithmetic: exhaustive screening over 2¹⁵
  (n=16), 2³¹ (n=32), and 2⁶⁴ half-codes (n=64) sign codes on the difference
  body P−P, reducing to 16 / 96 / 896 survivors, then dihedral-orbit elimination.
  Weeks old, finite, exactly replayable, and re-verification is explicitly
  invited. *(I could not fetch the arXiv abstract page directly — rate-limited.
  Confirm authors, date, and the exact self-assessment language before relying
  on this framing.)*
- **Heilbronn Δ(8) and Δ(9)** — Sudermann-Merx, arXiv:2603.11107 (v2, May 2026),
  claims certified ε-global optimality plus exact algebraic coordinates:
  Δ(8) = (−1+√13)/36 and Δ(9) = −11/64 + 9√65/320. Standard references still say
  rigorous values are known only to n ≤ 7. Nobody has independently re-verified
  the MINLP certificates. **Bonus:** the same paper's method took ~15 minutes on
  a desktop for n = 9, so **Δ(10) is a plausible new-fact target sitting directly
  behind the verification work** — verify their n=8,9, then extend to n=10. That
  is the rare case where the re-verification lane and the new-fact lane are the
  same project.
- **Baek's moving-sofa proof** (arXiv:2411.19826, Nov 2024, 119 pp.) — enormous
  press, no confirmed journal acceptance or formalization found as of Aug 2026,
  Wikipedia still hedging. Its predecessor used exact rational QP with
  branch-and-bound (`github.com/jcpaik/sofa-designer`). High visibility, high
  effort, and a real risk of being read as an attack on a correct proof — handle
  only with the framing in §4.4.

### B3. The unrefereed single-author preprint layer in automated-conjecture land

arXiv math.CO in 2026 carries a steady stream of single-author, no-affiliation
papers resolving auto-generated conjectures. These are **novelty-blocking but not
mathematically settling** — a distinction AdaIvy's data model can represent and
most pipelines cannot. Rigorously re-deriving or refuting one is itself
publishable, and demonstrates the `LiteratureApplicabilityRecord` doing real work
rather than ceremonial work.

A concrete collision hazard worth encoding as a test case: arXiv:2608.01396
(2 Aug 2026) claims a proof of **Graffiti.pc #143**, while the **Graffiti (WoW)
#143** is an entirely different conjecture. Two lists, same number. Any system
that conflates them produces a false novelty verdict.

### B4. Provenance errors in canonical references

Low value individually, useful as calibration and as cheap public artifacts:
the smallest known 5-chromatic unit-distance graph is **509** vertices (Parts
2020, per MathWorld and the primary literature) while the Polymath16 wiki still
headlines **510** (G₁₁, 2508 edges). An afternoon's work; a concrete, citable
correction to the canonical reference page for a famous problem.

### 4.4 Framing risk — read this before publishing anything in Lane B

Re-verification work has a social failure mode: it reads as gotcha journalism,
and the community currently under scrutiny is one AdaIvy needs on-side. Three
rules:

1. **Always run the positive control.** A re-verification pass that only ever
   reports problems is indistinguishable from a broken verifier. Publish the
   confirmations alongside the refutations — the Phase 6 suite already encodes
   the principle that "an all-reject system cannot pass."
2. **Report to the maintainer before the world.** Tao's wiki, the arXiv comment
   field, and the author's inbox come before any announcement. This is also
   literally what the Leiden Declaration asks for, and being visibly compliant
   with it is worth more than the finding.
3. **Distinguish "we could not replay this" from "this is wrong."** These are
   different verdicts with different warrants. Collapsing them is precisely the
   evidence-escalation failure the architecture exists to prevent, and doing it
   in public would be self-refuting.

---

## 5. Lane C — Semantic custody (small, cheap, exactly on-narrative)

### C1. Graffiti #322 / #197 — the definitional deadlock ★

Roucairol & Cazenave (ECAI 2025, arXiv:2409.18626) report that Graffiti #322
("if G is triangle-free then Inverse Even ≤ range of eigenvalues of Distance")
**dies immediately** under Aouchiche–Hansen's reading of "range" (= number of
distinct values; C₄ is then a counterexample, 3 distinct distance eigenvalues vs
Inverse Even = 4), while under the usual reading (max − min) they found nothing.
Their own stated conclusion is that *either Graffiti 197 is refuted or Graffiti
322 is refuted* — and they leave it there.

That is a semantic-alignment failure sitting unresolved in the published record,
with two named conjectures downstream of it. Resolving it rigorously — frozen
source (the July 2004 `wow-july2004.pdf`, which requires custom glyph decoding),
both readings stated, a certified kill under each applicable reading, and an
explicit disclosure of the contested interpretation — is a short publishable note
whose *entire content* is the thing AdaIvy claims to do better than everyone
else. Search space is trivial: triangle-free graphs to n = 14 is 4.68×10⁸,
cheap.

The same hazard class recurs across the Fajtlowicz list: "gravity matrix,"
"harmonic," "range," and "deviation" all have conflicting definitions, and
Roucairol–Cazenave document that Graffiti #290 dies instantly under the survey
definition and is "seemingly impossible" under the correct one. A **frozen
definitional registry for the WoW list**, published as an artifact, would be a
genuine service to a small field and a natural output of a
`SemanticAlignmentRecord` implementation.

---

## 6. Lane D — Warm-ups and races

| Target | Statement | Why | Caution |
|---|---|---|---|
| **Graffiti.pc Hamiltonian-path family** (#190a, #199, plus ~13 siblings: 200, 201, 203, 205, 207–213, 217) | e.g. #190a: G connected, L(G) ≤ δ′(G)+1 ⟹ G has a Hamiltonian path. #199: κ(G) ≥ t(G)−2 ⟹ Hamiltonian path | **Best throughput per engineering hour on the list.** One harness, ~15 named targets. Hamiltonicity is a clean exact decision (subset DP, trivial to n=24). Hypotheses are restrictive so filter-first prunes >99%. Almost no literature = low contest | Sources are 2006-era Graffiti.pc; resolutions may sit in *Congressus Numerantium*, which no search engine indexes |
| **TxGraffiti Conjecture 3** | G r-regular, r > 0 ⟹ i(G) ≤ μ*(G), sharp. Open for r ≥ 3 | Sole survivor of Davila's four flagship conjectures; the other three all resolved June–July 2026, and #4's counterexample was a 9-vertex friendship graph. Lean statement supplied in arXiv:2507.17780 Appendix A. Cubic sweep to n=26 + 4-regular to n=18 is a few core-days | **Race, not a project.** It is the obvious next target for every competing pipeline. Start within days or skip |
| **Seymour's Second Neighborhood** — certified sweep | Every oriented graph has a vertex v with \|N⁺⁺(v)\| ≥ \|N⁺(v)\| | Verification is trivial integer counting. No known exhaustive sweep beyond ~7 vertices. A certified exhaustion to n = 10–11 is publishable on the Tranquilli precedent | Oriented graph counts explode: n=9 ≈ 8×10⁹ |

---

## 7. The contest-density problem (why "open" statuses are unreliable right now)

Three data points, all from the last ninety days:

- Of Davila's four flagship TxGraffiti open conjectures published July 2025,
  **three fell between June and July 2026** — two proved, one refuted.
- Erdős's problem #5 from the Horodecki–Rudnicki–Życzkowski "Five Open Problems
  in Quantum Information Theory" list (two-ququart Werner state 2-copy
  distillability) was **solved negatively by four independent groups within five
  days** in July 2026. One of those papers (arXiv:2607.24309, Fraser, Huber,
  Pozsgay, Vona) carries the arXiv comment that it was "found and written up
  with GPT Sol 5.6, Claude Fable, and Claude Opus."
- A conjecture matching AdaIvy's exact target profile (Erveš–Tepeh (1,2)-domination
  on cubic graphs, killed by computer search at n = 18, 20, 22) was refuted by a
  conventional team on **18 August 2026 — three days before this review**.

**Operational consequences.**

1. Any "open" flag older than ~60 days is a weak prior, not a fact. Curated
   lists lag by years; the IQOQI Open Quantum Problems list's most recent update
   is 2023-01-23.
2. Novelty checking must cover **arXiv full text** (not abstracts), plus the
   non-indexed venues where this material actually lands: *Congressus
   Numerantium*, *MATCH Commun. Math. Comput. Chem.*, *Australasian J.
   Combinatorics*, and paywalled APS/Springer journals with no preprint. The
   Lü–Dong paper in §1 has no arXiv version at all — an arXiv-only novelty check
   would have missed it, which is a concrete, testable regression case worth
   adding to the acceptance suite.
3. Prefer targets that are (a) freshly posted and formalized but unattacked, (b)
   structurally adjacent to something just resolved, or (c) in a definitional or
   verification niche where heuristic search is the wrong operator. Lanes A, B
   and C are all chosen on this basis.

⚠️ **One item to check personally.** During research, a pipeline named
`demonstrandum-research` (repo `artifacts/RESULTS.md`, claiming refutations of
Graffiti #143 and #154 in June 2026, and of Davila Conjecture 9) was surfaced and
attributed to this project. If that is not yours, it is a directly competing
pipeline working the identical list with the identical methodology, and should be
treated as the closest prior art in the space. Worth five minutes to determine
which.

---

## 8. Explicitly rejected, with reasons

| Target | Why not |
|---|---|
| **erdosproblems.com as a hunting ground** | Saturated. DeepMind, OpenAI, Harmonic and hobbyists are all on it. ~60% of "AI resolutions" since Oct 2025 were literature rediscovery. "Open" means only that the maintainer has not found a published solution. Use it as a *verification* target (B1), not a search target |
| **Hadwiger–Nelson, 6-chromatic lower bound** | Moonshot. No candidate family; the Minkowski-sum ladder that gave χ ≥ 5 has no 6-analogue; plausible vertex counts ≥ 10⁵–10⁶; Polymath16 never produced an attack route and wound down in Feb 2021 |
| **No-three-in-line record configurations** | Racing Marijn Heule directly. He found n = 76 on 10 Aug 2026 and n = 71 on 17 Aug 2026. Excellent capability demo, zero novelty value |
| **Kissing-number lower bounds** | Active industrial arms race (AlphaEvolve d=11; PackingStar d=25–31). The *upper*-bound side with exact rational SDP duality certificates is far less crowded, but is a much harder engineering project |
| **Zauner / SIC-POVMs** | Number-theoretic (Stark conjectures), not certificate-shaped, and crowded by experts. Also note arXiv:2601.13475 claims an unconditional proof and is not community-accepted — a good adversarial test case, a bad research target |
| **van der Waerden exact values, Schur S(6)** | Upper-bound side infeasible (S(5) alone produced a 2 PB proof). Only lower bounds are tractable and they attract no attention |
| **Vizing's conjecture, Danzer's problem, Reinhardt smoothed octagon** | Search space is a product of two spaces / purely infinitary / infinite-dimensional. No finite certificate |
| **Tuza's conjecture, Bollobás–Nikiforov** | Very heavily searched by both humans and RL. Include only as lottery tickets, never as the plan |

---

## 9. Recommended sequence

**Now (days, no new compute):**

1. Re-scope the JRF benchmark statement in `README.md` and
   `TECHNICAL_BLUEPRINT.md` against Nakahira–Kato–Usuda 2015 and Lü–Dong 2026.
   Add the paywalled-no-preprint case to the novelty-check regression suite.
2. Resolve the `demonstrandum-research` attribution question (§7).
3. Freeze the Lane A prior-art artifact: full arXiv:2403.18429 Appendix B, plus
   the Taieb et al. chapter, content-hashed.

**Next (Lane B1 — highest leverage, uses only existing machinery):**

4. Run the existing Phase 6 machinery over the 🔴 and ⚪ buckets of the Tao
   AI-contributions wiki. Report to the maintainer first. This converts the
   generality-control story from project-authored traps to externally-authored
   ones, which is the honest limitation the README currently names.

**Then (Lane A — the new-fact bet):**

5. Build the finite-combinatorial domain plugin against the BHS Laplacian bounds.
   Exhaustive n = 10 (seconds) → n = 11 (hours) → n = 12 (days), exact
   char. poly + Sturm throughout, emitting a certified exhaustion artifact
   regardless of outcome, in the Tranquilli/EmptyHexagonLean shape.

**In parallel, cheap (Lane C and D):**

6. Graffiti #322/#197 definitional resolution as a short note. Reuse the plugin's
   triangle-free enumeration.
7. Graffiti.pc Hamiltonian-path family as the plugin's second exercise — 15
   targets, one harness.

**Opportunistic:**

8. Heilbronn: re-verify Δ(8) and Δ(9) (Lane B), then attempt Δ(10) (new fact).
   This is the one place where the two lanes are the same project.

---

## 10. Sources

Landscape and calibration:
[Quanta, "Why the Legendary Erdős Problems Are Falling to AI" (3 Aug 2026)](https://www.quantamagazine.org/why-the-legendary-erdos-problems-are-falling-to-ai-20260803/) ·
[OpenAI, "Ten advances in mathematics" (1 Aug 2026)](https://openai.com/index/ten-advances-in-mathematics/) ·
[OpenAI, disproof of the unit distance conjecture (20 May 2026)](https://openai.com/index/model-disproves-discrete-geometry-conjecture/) ·
[arXiv:2605.20695, Alon–Bloom–Gowers et al., remarks on the disproof](https://arxiv.org/html/2605.20695v1) ·
[arXiv:2602.10177, Aletheia](https://arxiv.org/html/2602.10177v1) ·
[arXiv:2601.22401, Semi-Autonomous Mathematics Discovery with Gemini](https://arxiv.org/html/2601.22401v3) ·
[arXiv:2605.22763, AlphaProof Nexus](https://arxiv.org/html/2605.22763v1) ·
[Leiden Declaration on AI and Mathematics](https://leidendeclaration.ai/) ·
[TechCrunch, "OpenAI's embarrassing math" (19 Oct 2025)](https://techcrunch.com/2025/10/19/openais-embarrassing-math/) ·
[Tao, the story of Erdős #1026](https://tagteam.harvard.edu/hub_feeds/3899/feed_items/17100034/content) ·
[teorth/erdosproblems wiki — AI contributions](https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems) ·
[Formal Conjectures (DeepMind)](https://github.com/google-deepmind/formal-conjectures) ·
[Epoch AI, FrontierMath Open Problems](https://epoch.ai/frontiermath/open-problems)

Quantum benchmark prior art:
[Ježek, Řeháček, Fiurášek, quant-ph/0201109](https://arxiv.org/abs/quant-ph/0201109) ·
[Nakahira, Kato & Usuda, PRA 91, 012318 (2015)](https://journals.aps.org/pra/abstract/10.1103/PhysRevA.91.012318) ·
[Lü & Dong, PRA 113, 022451 (26 Feb 2026)](https://journals.aps.org/pra/abstract/10.1103/q7wq-ygm9) ·
[Gonçalves et al., arXiv:1306.3057 (diluted RρR global convergence)](https://arxiv.org/abs/1306.3057) ·
[Tyson, arXiv:0907.3386](https://arxiv.org/abs/0907.3386)

Lane A:
[Ghebleh, Al-Yakoob, Kanso, Stevanović, arXiv:2403.18429](https://arxiv.org/abs/2403.18429) ·
[Parallelizing Wagner's approach, arXiv:2509.01607](https://arxiv.org/pdf/2509.01607) ·
[Taieb, Roucairol, Cazenave, Harutyunyan (2026)](https://link.springer.com/chapter/10.1007/978-3-032-09156-7_4) ·
[Tranquilli, certified Erdős–Gyárfás computation, arXiv:2608.02675](https://arxiv.org/abs/2608.02675) ·
[EmptyHexagonLean, arXiv:2403.17370](https://arxiv.org/html/2403.17370) ·
[House of Graphs 2.0](https://houseofgraphs.org/)

Lane B:
[Reinhardt max-perimeter proof candidates, arXiv:2608.08001](https://arxiv.org/abs/2608.08001) ·
[Sudermann-Merx, Heilbronn via MIO, arXiv:2603.11107](https://arxiv.org/html/2603.11107v2) ·
[Baek, optimality of Gerver's sofa, arXiv:2411.19826](https://arxiv.org/abs/2411.19826) ·
[Alexeev & Mixon, Erdős #707, PNAS](https://www.pnas.org/doi/10.1073/pnas.2531760123) ·
[MathWorld, Hadwiger–Nelson](https://mathworld.wolfram.com/Hadwiger-NelsonProblem.html) ·
[Polymath16 wiki](https://michaelnielsen.org/polymath/index.php?title=Hadwiger-Nelson_problem)

Lanes C and D:
[Roucairol & Cazenave, arXiv:2409.18626 (Table 1 is the WoW open/closed ledger)](https://arxiv.org/html/2409.18626v1) ·
[Davila, "In Reverie Together", arXiv:2507.17780](https://arxiv.org/html/2507.17780) ·
[West, REGS Graffiti.pc page](https://dwest.web.illinois.edu/regs/graffiti.html) ·
[Written on the Wall II open list (Wayback, 2008)](https://web.archive.org/web/20080905162455/http://cms.dt.uh.edu/faculty/delavinae/research/wowII/open.html) ·
[Wagner, arXiv:2104.14516](https://arxiv.org/abs/2104.14516) ·
[Knor, Sedlar & Škrekovski, arXiv:2608.17851 (18 Aug 2026)](https://arxiv.org/abs/2608.17851)
