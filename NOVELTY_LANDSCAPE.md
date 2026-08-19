# Prior-Art and Novelty Landscape

**Project:** Verification-first system for AI-assisted mathematical research  
**Review date:** 19 August 2026  
**Scope:** Publicly accessible papers, project sites, repositories, and technical documentation. This is an engineering prior-art review, not a patentability or freedom-to-operate opinion.

## Executive verdict

The broad concept is **not novel**:

> A user supplies a research problem; agents retrieve mathematical literature; a persistent memory stores knowledge and attempts; models generate and revise proof strategies; symbolic or formal tools verify results; successful and failed routes are retained for later work.

By August 2026, several systems implement most of that description. The closest are **RMA**, **Aletheia**, **MathGraph**, **Albilich**, **ProofAtlas**, **ASTRA**, **AlphaProof Nexus**, and **Eigenius**. Older work already established mathematical knowledge graphs, proof-obligation management, retrieval-assisted theorem proving, and generator/evaluator search.

The proposed project can still be valuable, but it should not be positioned as inventing the “AI mathematician with memory and verification.” Its defensible contribution would be a particularly rigorous, interoperable implementation of **epistemic governance**:

- human-approved, versioned problem meaning;
- explicit bridges between informal, computational, and formal representations;
- evidence types that cannot be silently promoted into stronger conclusions;
- exact source-span and theorem-applicability checks;
- verifier-independent, replayable research records;
- honest terminal outcomes: proof, counterexample, conditional result, or named obstruction.

Even this combination overlaps substantially with MathGraph, Albilich, ProofAtlas, and Eigenius. The opportunity is therefore primarily **engineering integration, standards, evaluation, and trustworthy product design**, rather than idea-level novelty.

## Closest precedents

| System | What overlaps | What remains different or incomplete |
|---|---|---|
| [RMA: Research Math Agents](https://arxiv.org/abs/2605.22875) | Research-problem analysis, literature search and understanding, knowledge bank, structured shared memory, proposer/verifier roles, iterative proof refinement | Very recent; paper says implementation will be released upon acceptance. Natural-language verification and expert grading remain important. |
| [Aletheia](https://arxiv.org/abs/2602.10177) | End-to-end research mathematics, literature browsing, generator–verifier–reviser loop, long inference, honest abstention | Operates mainly in natural language. Human experts still bear the semantic, novelty, and attribution burden. |
| [MathGraph](https://www.mathgraph.org/) | Typed claims, definitions, proofs, countermodels, transformations, proof obligations, verification traces, reusable verification memory, named obstructions | Its public testbed is narrower than the proposed general system; current claims emphasize finite algebraic countermodels and a verification kernel. Conceptually, it is the closest match. |
| [Albilich](https://github.com/uw-math-ai/albilich) | Persistent versioned proof state, claims/routes/inferences/debts/artifacts, exact retrieval cards, adversarial roles, strict verifier permissions, representation switching, append-only history | A small and very recent open-source system. It is nevertheless close enough that rebuilding the same proof-state workflow without comparison would be wasteful. |
| [ProofAtlas](https://www.proofatlas.ai/) | Parallel agents, claims and dependencies, objections, failed routes, reusable lemmas, exact Lean statements, checked evidence, publication status | The public site is currently a read-only atlas and its larger performance claims require independent evaluation. It clearly establishes prior art for a shared proof/evidence graph. |
| [ASTRA](https://github.com/AstrumDrive/ASTRA) | Conjecture formalization, multiple model roles, symbolic/numerical/Lean tools, validation oracle, refutation analysis, persistent investigations, human admission to an axiomatic base | More execution-oriented and less rigorous about mathematical semantics and provenance than the blueprint; very recent and apparently early-stage. |
| [AlphaProof Nexus](https://arxiv.org/abs/2605.22763) | Long-running multi-agent proof search, Lean compiler feedback, optional evolutionary memory, proof/disproof tools, integrity checking, deployment on open research problems including quantum optics | Requires a Lean statement and supporting formal context up front. It powerfully addresses proof search, but not the full informal-to-formal research lifecycle. |
| [Eigenius](https://arxiv.org/abs/2608.04457) | Typed, versioned knowledge graph; immutable provenance; declared/observed/derived/verified warrants; cross-system translations; Lean-backed formal verification | Broader scientific infrastructure rather than a math-research workflow. Its epistemic type system and translation model substantially overlap the proposed trust layer. |
| [LeanMarathon](https://arxiv.org/abs/2606.05400) | Long-horizon proof DAG, durable shared blueprint, adversarial target-fidelity review, scoped agents, recoverable CI-gated work | Concentrated on autoformalizing existing research mathematics rather than selecting and attacking open problems. |
| [The Agentic Researcher](https://arxiv.org/abs/2603.15914) | Sandboxed CLI agents, persistent instructions/TODO/report/Git state, long autonomous runs, falsifiable experiments, disciplined iteration | Deliberately simple and file-based. It shows that a useful first version may not require a large custom platform. |

The landscape is crowded but immature. Several of the closest systems appeared only in 2026, have limited public evaluation, are small repositories, or report project claims that have not yet been independently replicated. That creates room for a careful implementation, but not for a broad novelty claim.

## Component-level prior art

The architecture also recombines several mature lines of work:

1. **Semantic mathematical knowledge representation.** [OMDoc](https://www.omdoc.org/format/) represents mathematical objects, statements, theories, and proofs, while [OMDoc/MMT](https://docs.mathhub.info/legacy/omdoc-mmt.html) adds foundation-independent theory graphs and meaning-preserving theory morphisms. This is direct precedent for the proposed claim graph and representation-map registry.
2. **Proof obligations and pluggable verifiers.** [Why3](https://why3.org/) has long used an intermediate specification language and dispatches verification conditions to multiple automated and interactive provers.
3. **Retrieval-assisted formal proof.** [LeanDojo/ReProver](https://arxiv.org/abs/2306.15626) identifies premise selection as a key bottleneck and combines formal-library analysis with retrieval. Newer systems extend this to global premise sets and long-horizon proof development.
4. **Executable evaluator loops.** [FunSearch](https://deepmind.google/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/) and [AlphaEvolve](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/) retain high-scoring programs and evolve them under automated evaluators. They work best when correctness or quality can be encoded as a reliable executable objective.
5. **Scientific literature agents.** [PaperQA2](https://arxiv.org/abs/2409.13740) performs iterative literature retrieval, cited synthesis, and contradiction detection. It is strong prior art for the acquisition layer, but citations remain evidence rather than proof.
6. **End-to-end automated research.** [The AI Scientist](https://arxiv.org/abs/2408.06292) generates ideas, runs experiments, writes papers, and simulates review. It demonstrates both the promise and the dangers of allowing one pipeline to design, execute, select, and evaluate its own work.

## What existing systems have learned the hard way

### 1. The main failure is often semantic, not syntactic

A proof assistant proves the encoded proposition; it does not prove that the proposition faithfully expresses the researcher’s question. Aletheia’s large-scale Erdős exercise found many outputs that were technically defensible under some reading but did not answer the intended question. AlphaProof Nexus likewise reports finding and correcting ambiguous or wrong formalizations before accepting results.

**Design implication:** create a first-class `SemanticAlignmentRecord`, separate from a formal proof record. It should bind the user’s prose, definitions, quantifiers, edge cases, and formal target, and require explicit human approval when the target changes.

### 2. Retrieval removes crude hallucinations, not subtle misuse

Aletheia reports that web tooling reduced invented papers but shifted errors toward real papers whose results were quoted or applied incorrectly. A retrieval hit is therefore not a theorem dependency.

**Design implication:** every imported result needs an exact source location, statement, hypotheses, definition mapping, and a checked implication to the local claim. Albilich’s “retrieval card is evidence, not proof” rule is the right model.

### 3. A model should not see its own persuasive trace when verifying

Aletheia found that separating generation from verification helped because a long generation trace can bias the verifier toward the proposed answer.

**Design implication:** verifier context should be rebuilt from the formal problem, accepted premises, candidate proof object, and raw evidence—not copied from the proposer’s narrative. Independent prompts are not enough if both roles inherit the same contaminated context.

### 4. Models hide the hard part in a plausible lemma

AlphaProof Nexus reports failed sketches that moved the central difficulty into a helper lemma, sometimes describing a hallucinated lemma as established literature. A recent failure-mode study calls the broader pattern “premise smuggling”: a load-bearing assertion is treated as standard without support.

**Design implication:** require every nontrivial inference to terminate in a verified dependency, an explicitly open obligation, or a named external theorem with checked applicability. Add tests for target restatement disguised as a lemma.

### 5. Formal verification is necessary but not sufficient

Lean can establish logical correctness relative to a statement and axioms. It does not establish novelty, significance, faithful attribution, or alignment with the original informal problem. [First Proof](https://arxiv.org/abs/2602.05192) also notes that research is not merely proving a supplied statement; it includes deciding what to ask and creating the framework in which it can be answered.

**Design implication:** track at least four separate statuses: semantic alignment, logical verification, literature novelty, and mathematical significance. Never collapse them into one “verified” badge.

### 6. Evaluators create the objective—and can create scientific misconduct

An evaluation of AI-scientist systems found inappropriate benchmark choices, undocumented dataset changes, arbitrary metric substitution, and post-hoc selection based on test performance. It also found that workflow traces and code made these failures much easier to detect than the final paper alone ([Luo, Kasirzadeh, and Shah](https://arxiv.org/abs/2509.08713)). A separate evaluation of the original AI Scientist reported that 42% of experiments failed through coding errors and that some manuscripts contained hallucinated results ([Huang et al.](https://arxiv.org/abs/2502.14297)).

**Design implication:** freeze problem statements, datasets, success metrics, and stopping rules before search; retain every run; distinguish exploration from confirmatory evaluation; and never let the same reward signal silently become the publication criterion.

### 7. More orchestration is not always better

RMA reports gains from interacting structured modules, but AlphaProof Nexus found that a basic loop of independent LLM attempts plus Lean feedback reproduced its nine Erdős successes, with sophisticated evolution helping mainly on the hardest cases. The Agentic Researcher similarly obtains long-running work from disciplined files, Git, tools, and prompts.

**Design implication:** start with the smallest durable vertical slice. Add multi-agent markets, elaborate schedulers, or graph databases only when an evaluation demonstrates a specific bottleneck.

### 8. Benchmarks are fragile

First Proof deliberately used unpublished questions to reduce contamination, but it contains only ten problems, requires expensive expert grading, and tests the relatively well-specified final proof stage rather than the whole research process.

**Design implication:** evaluate the platform on multiple axes: target fidelity, source applicability, proof correctness, counterexample quality, progress on unresolved obligations, cost, reproducibility, novelty detection, and human verification time. The quantum-state-discrimination problem is a useful longitudinal case study, not sufficient evidence of generality.

## Novelty map for this project

### Do not claim as novel

- multi-agent mathematical problem solving;
- literature-grounded proof generation;
- a persistent knowledge or proof graph;
- generator/verifier/reviser roles;
- proof obligations and verifier tools;
- retaining failed proof routes;
- Lean-assisted research theorem proving;
- model-generated conjectures evaluated by code;
- human approval before accepting results.

### Potentially differentiating if implemented and evaluated rigorously

1. **Representation-bridge governance.** Every informal→symbolic→numeric→formal conversion is itself a claim with preservation conditions, exceptions, and a proof obligation.
2. **Structural evidence non-escalation.** The data model—not merely prompts—prevents model consensus, retrieval, finite sampling, or ordinary floating-point calculations from acquiring a stronger warrant than they justify.
3. **Semantic target custody.** The original problem and every amended interpretation remain immutable, diffable, and separately approved.
4. **Verifier-neutral interoperability.** One research record can use Lean, SMT, CAS, interval arithmetic, exhaustive finite search, and human review without conflating their guarantees.
5. **Research-integrity-by-construction.** Frozen evaluation protocols, complete negative-result retention, provenance to exact source spans, and audit of the full trajectory are default behavior.
6. **A reusable domain-plugin contract.** A quantum-information plugin and later topology/dynamical-systems plugins share the same epistemic core without hard-coding one field’s ontology.

These are hypotheses for differentiation, not established novelties. MathGraph, Albilich, OMDoc/MMT, ProofAtlas, and Eigenius overlap with several of them. The project would need a precise feature comparison and empirical demonstration.

## Recommended build strategy

### 1. Change Phase 0 from “build the platform” to “validate the gap”

Run a two-week adoption spike against MathGraph, Albilich, ASTRA, OMDoc/MMT, Why3, and Lean-based agent tooling. For each, attempt the same small research dossier and record:

- whether the intended statement can be versioned and approved;
- whether exact source applicability is represented;
- whether failed routes and obligations survive restarts;
- whether evidence types are structurally separated;
- whether a second verifier can replay a result;
- what cannot be expressed without modifying the system.

Only implement capabilities for which the spike produces a concrete gap.

### 2. Treat the system as an interoperability and trust layer

The strongest positioning is:

> A verifier-neutral research workspace that turns model proposals, literature, computations, proof attempts, and formal artifacts into a typed, replayable evidence graph whose trust transitions are mechanically governed.

That is narrower and more defensible than “a general autonomous mathematician.”

### 3. Add the following objects to the blueprint before coding

- `SemanticAlignmentRecord`
- `LiteratureApplicabilityRecord`
- `NoveltyAssessment`
- `SignificanceAssessment`
- `EvaluationProtocol` with frozen metrics, data, and stopping rule
- `ResearchContributionRecord` separating human and system actions
- `VerifierContextManifest` proving what the verifier did and did not see

### 4. Add adversarial acceptance tests

The platform should reject or quarantine:

- a valid Lean proof of a mistranslated theorem;
- a real citation whose theorem does not imply the claim;
- a helper lemma equivalent to the unresolved target;
- a finite numerical test offered as a universal proof;
- an experiment selected because its test-set score was inspected;
- a verifier influenced by the proposer’s untrusted narrative;
- a “novel” result already present under different terminology;
- a correct but vacuous reinterpretation of the user’s question.

### 5. Benchmark against the closest systems, not against chat alone

Compare at minimum with:

- a strong single-agent tool-using baseline;
- a simple proposer/critic loop;
- Albilich or an equivalent persistent proof-state workflow;
- a formal-first Lean agent where the target can be encoded;
- the full proposed trust architecture.

Measure expert review time and detected semantic errors, not only solve rate.

## Bottom line

The original intuition was good, but it has now become an active research category. Building an undifferentiated crawler + vector database + agent loop would duplicate existing work and inherit known failures. Building a carefully specified **semantic-custody, evidence-governance, and verifier-interoperability layer** could still be worthwhile—especially if it is evaluated transparently on both successful and failed research attempts.

The immediate next step should be a build-versus-adopt spike and a revision of the blueprint’s Phase 0, not implementation of the entire architecture.

