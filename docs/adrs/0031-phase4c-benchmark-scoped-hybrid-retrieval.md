# ADR-0031: Benchmark-scoped hybrid retrieval with deterministic offline signals

- **Status:** accepted for bounded Phase 4C hybrid retrieval implementation;
  implemented 21 August 2026 with one gate unmet and the revisit trigger
  fired -- see "Measured outcome"
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 12.2 rebuildable index projections,
  Section 12.2.1 provider binding for vector projections, Section 19 separately
  gated hybrid-retrieval prerequisites
- **Decision owners:** repository owner

## Context

ADR-0026 places Phase 4C hybrid retrieval next after Phase 4B.
`docs/phase-4c/HYBRID_RETRIEVAL_BENCHMARK_V1.md` froze a corpus, gold queries,
and eight metric gates before any index existed, and
`spikes/phase4c_benchmark/evaluator.py` measures a SQLite FTS5/BM25 lexical
baseline against them. The baseline meets five gates and fails two. The two
failures have different causes, and the difference determines what a second
signal has to be.

`applicability_precision_at_5` measures `0.6` against a gate of `1.0`. This is a
discrimination failure, not a vocabulary or ranking failure. On
`applicability-spectral` the inapplicable `unbounded-spectral-mismatch` matches
all six query tokens -- identical coverage to the applicable gold -- and loses by
only `0.617` BM25 points on length normalization. On
`applicability-certificate` the inapplicable `optimization-distractor` shares
four of five query tokens, all of them under explicit negation: "no dual
certificate or checked bound is supplied". In both cases the terms that
disqualify the document are absent from the query, so a bag-of-words ranker
cannot see them, and no reweighting of the same term signal separates them.

`renamed_known_result_recall_at_10` measures `0.0` against a gate of `1.0`. The
control query `Borel Lebesgue theorem` shares *zero* tokens with its gold
`renamed-cover-result`: `borel` and `lebesgue` occur nowhere in the corpus, and
the gold says `principle` and `formulation`, never `theorem`. The gold is not
mis-ranked; it is absent from the FTS candidate set. Character n-grams appear to
fix this and do not -- they place the gold ninth of fourteen, and its only
shared trigrams come from the `Project-authored` boilerplate present in all
fourteen documents. That is noise clearing a threshold, not a signal.

Two measured constraints bound any fusion design.

`duplicate_rate_at_5` has no headroom. Only two documents carry a duplicate
group; their bodies differ by one token in twenty-two, they score identically,
and they are separated only by the document-ID tie-break, so they always enter a
result list as a pair. At the current denominator of `31`, a numerator of `1`
passes and a numerator of `2` requires a denominator of `40`. A naive character
n-gram signal places both certificate documents at ranks four and five of
`applicability-spectral`, which has a free fifth slot, and fails the gate on its
own.

The three recall@5 metrics at `1.0` are protected by BM25 margins of `4.4` to
`13.2` points between the gold at rank one and the next document. Rank-based
fusion such as reciprocal rank fusion discards those margins entirely and treats
a gold at BM25 rank one as interchangeable with any other rank one.

Three facts constrain the choice of signal itself. ADR-0026's standing policy is
that every documented acceptance path stays offline, deterministic, and free of
model and network calls, so an embedding candidate gets no exemption. Blueprint
Section 12.2.1 therefore requires produced vectors to be stored as immutable
content-hashed artifacts so a deterministic rebuild replays bytes rather than
re-calling a provider that is neither bit-reproducible nor stable behind its own
model aliases. And `RightsUse.EMBEDDING` exists in
`src/math_research/phase4a/records.py` with no consumer and no issued decision;
Section 12.2.1 requires a current decision naming the processor that receives
the source text. An embedding signal is thus blocked on an owner rights
decision, and is in any case only measurable through a fusion harness that
already replays stored projections offline.

`RightsUse` has no `retrieval` or `indexing` member. Expressing a retrieval-use
right would mean reusing `EMBEDDING`/`MODEL_CONTEXT` against their meaning or
extending the Phase 4A enum, and ADR-0026 returns any slice that touches the
Phase 4A rights boundary to the full gate package.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (embedding second signal now) | Section 12.2.1; `RightsUse.EMBEDDING` exists unused | Directly addresses vocabulary mismatch, the harder of the two failures | Blocked on an owner `embedding` rights decision naming a processor; needs a pinned dependency and a provider-partitioned vector store; still needs the offline fusion harness first | Owner rights decision; per-provider pricing snapshot; content-hashed vector artifacts |
| Wrap (deterministic signals now, embeddings later behind the same fusion port) | Phase 2 provider precedent; `synthesis/phase3a_index.py` adapter precedent | Closes both open gates offline today; leaves the embedding path open rather than foreclosed; no dependency, no network | Two signals must each be shown not to be fitted to the fixtures; alias data does not exist and must be authored | Score-space fusion; demotion-only discrimination; owner-approved fixture extension |
| Interoperate (extend the spike, ship no production module) | The spike already measures the baseline | Cheapest | Leaves Phase 4C unimplemented; a spike is explicitly not a production retriever and cannot be consumed | -- |
| Build/defer (no new slice) | -- | -- | Silent architecture drift, prohibited by AGENTS.md | -- |

## Decision

Adopt the wrap option, scoped to the benchmark.

Implement `src/math_research/phase4c/` as a hybrid retriever over the frozen
Phase 4C benchmark corpus, fusing three deterministic offline signals:

- the existing lexical FTS5/BM25 baseline, preserving the Phase 3A
  title/body/type weights `2.0/1.0/0.5`, the `unicode61 remove_diacritics 0`
  tokenizer, NFC normalization, and document ID as tie-break;
- a **hedging-scope discrimination signal** that demotes a document when a
  matched query term falls within the negation scope of a self-disclaiming cue
  in the document's own bytes;
- a **content-keyed alias expansion signal** that expands a recognised alias
  name phrase in the query into content phrases and matches those against
  document bodies.

Six boundaries are part of this decision.

**Scope.** The module operates only on the project-authored Phase 4C benchmark
fixtures. It consumes no Phase 4B parse projections, reads no Phase 4A rights
decisions, touches no deletable content and no protected evidence manifest, and
does not extend `RightsUse`. It therefore stays inside the ADR-0026 lightweight
per-slice process. Consuming admitted Phase 4B parse projections is a separate
later slice, and because that slice reads the Phase 4A rights boundary it
returns to the full gate package per ADR-0026 and ADR-0028.

**Fusion is in score space, not rank space.** BM25 magnitudes are preserved so
the `4.4`-to-`13.2` point margins that protect the three recall@5 golds survive
fusion. Reciprocal rank fusion and any other rank-only combiner are rejected for
this reason, not on preference.

**The discrimination signal is demotion-only.** It may lower a document's fused
score and may never raise one, and it may never introduce a document that the
lexical signal did not retrieve. This is what protects `duplicate_rate_at_5`,
whose numerator cannot rise from `1` to `2` at the available denominator.

**Cue classes are split and frozen.** Negation is legitimate in a contradiction
document -- a counterexample *is* an assertion that something fails -- so
`boundary-contradiction` carries the cue `fails` in the same sentence as two
matched query terms while being an applicable contradiction gold. Cues are
therefore partitioned into self-disclaiming cues about the document's own
coverage (`does not provide`, `is inapplicable`, `no ... is supplied`,
`insufficient`, `may look`) and object-level cues about the mathematics
(`fails`, `violates`). Only self-disclaiming cues demote. There is no cue-count
threshold, because selecting one after observing the corpus is the forbidden
outcome "selecting thresholds after observing a hybrid candidate".

**Alias entries are keyed on name phrases and expand to content phrases only.**
A document ID never appears in the alias table. Keying an alias to an expected
document ID would make an expected ID a retrieval feature, which the benchmark
lists as a forbidden outcome and which the existing label-separation tests
detect.

**No embeddings, vectors, network, model calls, or new dependencies.** The
runtime stays standard-library only. Section 12.2.1's partitioning rule is not
exercised because no vector projection exists; it binds the later embedding
slice.

The owner has approved extending the frozen benchmark fixtures for this slice.
The extension exists to make both gates measure generalization rather than a
one-to-one fit: the corpus grows to seventeen documents and the query set to
fifteen, adding three renamed controls over genuine mathematical name aliases
and two applicability controls that exercise the discrimination signal on
documents it was not designed against. The alias table carries at least nine
entries, of which at least five are exercised by no query and match no document,
so passing the renamed gate requires a reference work rather than an answer key.
The spec document, the evaluator's cardinality and category-distribution
constants, and the pinned measured values are updated to match.

## Consequences

The acceptance suite is the sole executable record of this slice's thresholds,
so it must assert the boundaries above as properties and not merely exercise the
happy path. Specifically it must demonstrate that the discrimination signal
never promotes a document, that it does not demote either contradiction gold,
that fused ordering is unchanged when every cue is removed from the cue table,
that the alias table contains entries no query exercises, that removing a single
exercised alias entry fails exactly its own query, and that no document ID
appears in the alias fixture.

The honest risk in this slice is that a cue lexicon authored after observing the
corpus is fitted to it. Four things bound that risk and none of them eliminates
it: the two cue classes are distinguished by a stated principle rather than by
which documents they happen to separate; there is no tuned threshold; the new
applicability controls exercise documents the signal was not authored against;
and the signal is demotion-only, so a mis-fire costs recall visibly rather than
inflating precision silently. A reviewer should treat the discrimination signal
as the weakest part of this slice and read its tests first.

Extending frozen benchmark fixtures is a real cost. The previously pinned
measured values no longer describe the current fixture set, so the "measured
baseline versus proposed threshold" separation must be re-established from
scratch and re-pinned. Anyone comparing a future candidate against a
pre-extension number will be comparing across different corpora. The extension
is recorded here, in the spec document, and in the fixture manifest so the
discontinuity is visible rather than inferred.

Duplicate-rate arithmetic improves as a side effect: more queries raise the
denominator, which widens the margin at numerator `1`. This is a consequence of
the extension and not a reason for it, and the gate is still asserted against
the measured value.

Retrieval remains candidate generation. Fused rank, metric success, and
agreement between signals are not evidence, and this module produces no premise,
warrant, applicability judgement, or graph admission.

## Measured outcome

Implemented and measured on 21 August 2026. Six of seven gates hold. One fails.

| Metric | Baseline | Hybrid | Support | Gate |
|---|---|---|---|---|
| necessary-lemma recall@5 | 1.0 | 1.0 | 3/3 | pass |
| applicability precision@5 | 0.6 | **0.6** | 6/10 | **fail** |
| contradiction recall@5 | 1.0 | 1.0 | 2/2 | pass |
| notation-variant recall@5 | 1.0 | 1.0 | 2/2 | pass |
| renamed-known-result recall@10 | 0.0 | **1.0** | 4/4 | pass |
| duplicate rate@5 | 1/50 | 1/54 | 1/54 | pass |
| deterministic rebuild | -- | identical | -- | pass |
| external cost | 0 | 0 | -- | pass |

The alias signal closed the renamed gate as designed, from `0.0` to `1.0` on
four controls. No previously passing gate regressed and duplicate rate improved.

The discrimination signal did not close the applicability gate, and nothing was
tuned to make it. There are two independent measured causes.

**First, the demotion-only constraint in this ADR makes the gate unreachable by
construction.** All four applicability queries have fused candidate sets of 4,
5, 5 and 4 against a top-k of 5. Every retrieved relevant document is therefore
already inside the cutoff, so no permutation of the ordering changes either the
numerator or the denominator: `6/10` is invariant under every reordering. This
is an error in this ADR, not a limitation discovered during implementation. The
evidence was on record before the constraint was written -- the diagnosis noted
that `applicability-certificate` returned only three hits against a cutoff of
five, so no cutoff could exclude the false hit -- and the demotion-only rule was
adopted anyway, to protect `duplicate_rate_at_5`. That protection was also
unnecessary: exclusion only shrinks the duplicate denominator and cannot raise
its numerator, and at a denominator of 54 the gate has room.

**Second, exclusion would not reach the gate either.** Measured, an exclusion
variant scores `6/7 = 0.857`, still short of `1.0`. The whole residual is
`applicability-selfadjoint`, where `unbounded-spectral-mismatch` is not demoted
at all: its self-disclaiming sentence shares no token with the query
`self adjoint operators diagonalization domain conditions`, and the matched
terms all sit in a preceding sentence that carries no cue. Widening the scope
unit from the sentence after observing that failure is fitting the signal to the
fixture, which the forbidden outcomes prohibit, so it was not done.

The fixture extension therefore did exactly what it was added to do. A
discrimination signal validated against two known false hits failed to
generalize to a third control that was authored without reference to it.
Recording that is the result; a `1.0` obtained by widening the scope rule after
seeing which query failed would have been worthless.

The revisit trigger below is fired on its first clause. A future slice that
wants this gate must either fix the scope unit on a stated principle *before*
measuring, or use a different signal class. Structural metadata is not an option
today: the corpus documents carry no title and no unit type, so `title` and
`unit_type` are empty for every document and only `body` is populated.

## Explicit deferrals

- An embedding or vector signal, and with it every Section 12.2.1 obligation:
  partitioning by `(provider, model_identifier, dimension, normalization)`,
  rebuild-not-backfill, content-hashed vector artifacts, per-provider pricing.
  Blocked on an owner-issued current Phase 4A `embedding` rights decision naming
  the processor that receives the source text.
- Consumption of admitted Phase 4B parse projections. Returns to the full gate
  package because it reads the Phase 4A rights boundary.
- Any `RightsUse` extension for a retrieval or indexing use.
- Any change to the Phase 3A index. This module reads through an adapter on the
  `synthesis/phase3a_index.py` precedent and calls no writing path; note that
  `DeterministicRetriever.search` persists query and hit records, so a read-only
  path uses `ResearchMemoryWorkspace.fts_search` directly.

## Validation and revisit trigger

The decision stays valid while the complete offline check remains green, the
module reaches no network and imports no third-party package, fusion stays in
score space, the discrimination signal stays demotion-only, and the alias
fixture stays free of document identifiers.

Reconsider if a gate can only be met by promoting a document into the top five,
if a cue-count threshold becomes necessary, if the discrimination signal is
found to demote a gold in any category, if an alias entry has to be keyed to a
document, or if any acceptance path acquires a network call, a model call, or an
unpinned dependency.
