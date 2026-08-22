# ADR-0070: Phase 4C semantic signal over replayed vectors, and the corpus-scope limit

- **Status:** accepted and implemented; third of three slices. Requires
  ADR-0064 and ADR-0069. The signal remains fixture-scoped and is not connected
  to the acquired corpus or campaign. Superseded in part by ADR-0072: the
  one-URL-at-a-time corpus path description, the corpus-widening revisit item,
  and the gold-queries-only embedding deferral are superseded; the frozen
  19-document benchmark, the frozen constants, and the no-float no-network
  retrieval path stand.
- **Date:** 2026-08-22
- **Blueprint requirement:** Section 7.3 (retrieval strategy); Section 12.2
  (rebuildable projections); the decision row at `TECHNICAL_BLUEPRINT.md:70`;
  ADR-0031 and ADR-0032 (the slice this extends); ADR-0029 (recorded prediction
  before a bounded specialist is activated)
- **Decision owners:** repository owner and researcher

## Context

The blueprint's express intent is that retrieval be hybrid because vectors alone
are insufficient, not that vectors be added because they are fashionable:

> "| Retrieval | Hybrid and provenance-preserving | Vector similarity alone
> loses symbols and assumptions |" (`TECHNICAL_BLUEPRINT.md:70`)

> "Retrieval must be capable of combining prose, exact terms, citations,
> symbols/formulas, assumptions, conclusions, and graph relations. A single
> top-k vector search is insufficient." (`:1227-1229`)

Section 7.3 names seven candidate-generation signals: lexical, semantic, symbol
and formula, metadata and domain filters, citation-graph traversal,
claim/dependency-graph traversal, and contradiction-oriented queries
(`:1152-1163`). Phase 4C implements one of the seven plus two auxiliaries. This
slice adds the second of the seven. Five remain, and that is the honest measure
of how far from "wide" this architecture is.

ADR-0031 deferred this signal deliberately, choosing "Wrap (deterministic signals
now, embeddings later behind the same fusion port)" over "Adopt", and recorded the
unblocking conditions: an owner-issued Phase 4A `embedding` rights decision
naming a processor, §12.2.1's partitioning and artifact obligations, and a pinned
per-provider pricing snapshot. ADR-0064 and ADR-0069 satisfy those. The deferral
is now lifted on its own stated terms rather than overridden.

### The corpus is the binding limit, not the signal

This must be stated before the design, because it is the finding most likely to
be lost. Phase 4C's corpus is a frozen fixture set of **19 documents and 17
queries**, and the count is not incidental -- `fixtures.py:190-255` enforces
`BOUNDS.document_count == 19` exactly and fails closed on any other number.

Adding semantic retrieval over 19 documents does not produce a wide literature
search. It produces a better-measured retrieval benchmark. The path to a real
corpus runs through ADR-0050 acquisition, one human-planned exact URL at a time,
plus a Phase 4A rights decision per document and now an ADR-0064 processor
decision per document before any of it may be embedded. Nothing in this slice
shortens that path, and no report from it may imply otherwise.

## Options considered

| Option | Evidence | Benefit | Cost/risk | Decision |
|---|---|---|---|---|
| Live embedding call inside `evaluate_hybrid` | simplest | query vectors for free | breaks the network-blocked cost test, the `external_spend_usd == 0` gate, the stdlib allowlist, and §12.2.1's replay rule | Rejected |
| Float cosine as an unbounded additive term | BM25 is already float | fidelity to provider scores | injects an unbounded term into a score space whose 4.4-13.2 point BM25 margins ADR-0031 exists to protect; a small vector score change could silently reorder golds | Rejected |
| Exclusion-only semantic signal, mirroring the disclaimer signal | ADR-0032 precedent; three invariants already enforced | cannot promote a wrong document | cannot fix vocabulary mismatch either, which is the *only* failure this signal was deferred to address | Rejected: solves the wrong half |
| Exact-cosine tiering contributing bounded integer points, mirroring the alias signal | `fusion.py:132-181`; `aliases.py:32`; ADR-0069's exact integers | exact and decidable ranking; bounded, auditable contribution; preserves BM25 margins; no float, no network | tier boundaries and point value must be frozen before measurement, or the slice becomes fixture-fitting | **Selected** |

## Decision

Add a fourth port, `SemanticSignal`, to `phase4c/ports.py`, and a
`semantic.py` module that reads **only** ADR-0069 artifacts from one declared
partition. It constructs no float, holds no credential, opens no socket, and
makes no provider call, so every existing Phase 4C invariant survives unchanged.

### Contribution shape, frozen before measurement

The signal ranks documents within its partition by exact integer cosine
(ADR-0069), takes the top `semantic_candidate_limit`, and assigns each a tier by
rank. Fusion adds `semantic_tier_points * tier_credit`, an exact rational
multiple, in the same additive position as `alias_phrase_points * phrase_count`
at `fusion.py:171-175`.

The frozen constants, fixed **now, before any gate is measured**:

- `semantic_candidate_limit = 10`
- three tiers by rank: ranks 1-2 credit `3`, ranks 3-5 credit `2`, ranks 6-10
  credit `1`
- `semantic_tier_points = 1` (so the maximum semantic contribution is 3 points)

Three points is deliberately below ADR-0031's smallest measured BM25 gold margin
of 4.4, so the semantic signal can promote a document the lexical signal missed
entirely but cannot on its own invert a lexical gold ordering. That is the
property being asserted, and `pr.semantic-cannot-invert-a-lexical-gold` tests it.

**These constants are not to be adjusted after seeing gate results.** If a gate
regresses, the regression is the finding and is recorded as such; retuning a
threshold against the fixtures it is measured on would make the whole benchmark
worthless. This is the standing rule in this repository and it is the single
easiest thing to get wrong in this slice.

### Recorded prediction, per ADR-0029

Stated before measurement so the result can falsify it:

- `notation_variant_recall_at_5` and `renamed_known_result_recall_at_10`
  **improve or hold**. These are the vocabulary-mismatch gates and the reason
  ADR-0031 called embeddings "the harder of the two failures".
- `necessary_lemma_recall_at_5`, `applicability_precision_at_5`, and
  `contradiction_recall_at_5` **hold**, not improve. Semantics does not know
  what a hypothesis is.
- `duplicate_rate_at_5_maximum` is the live risk: near-duplicate documents have
  near-identical vectors, so semantic credit may cluster them. If this gate
  regresses, the prediction was wrong and the signal is reported as
  net-negative rather than quietly kept.
- `external_spend_usd` stays exactly `0`, because retrieval replays bytes.

### Named boundaries

- **Zero network at retrieval, structurally.** `semantic.py` reads a partition
  manifest and artifact bytes from disk. The existing substring ban on
  `socket`/`urllib`/`http`/`requests` and the stdlib import allowlist apply to it
  unchanged, and it must pass both without an exemption.
- **A missing partition is a refusal, not a degradation.** If the declared
  partition is absent, `evaluate_hybrid` refuses rather than silently running
  three-signal. A benchmark that quietly drops a signal reports a number for a
  system that was not tested.
- **The signal may introduce a document.** Unlike the disclaimer signal it is not
  exclusion-only, so it is subject to the candidate bound
  (`BOUNDS.max_candidates_per_signal = 50`) and must self-enforce it as
  `LexicalIndex.candidates` does at `lexical.py:129-133`.
- **Exclusion invariants are untouched.** This signal contributes score, never
  exclusion, so ADR-0032's three invariants keep holding by construction and
  their runtime checks at `fusion.py:206-254` are unmodified.
- **Report identity binds the partition.** The partition key and manifest hash
  enter `content_hash` alongside the corpus, gold-query, and alias hashes at
  `benchmark.py:437-444`. A report built against a different partition is a
  different report.
- **`signal_configuration.overrides` still records an injected signal**, so a
  test double cannot masquerade as the production signal inside a hash.

## What this decision does not license

It does not widen the corpus, acquire anything, crawl, follow a result, traverse
a citation, or generate a query. It does not implement the five remaining
Section 7.3 signals. It does not make retrieval a literature search, and it does
not make a retrieval hit evidence: `NOVELTY_LANDSCAPE.md:62-64` governs, and an
imported result still needs an exact source location, statement, hypotheses,
definition mapping, and a checked implication before it is load-bearing. It
creates no applicability record, no premise, no graph admission, no novelty or
significance assessment, and no mathematical warrant. It does not satisfy or
perform an ADR-0055 novelty re-check, which remains human by construction.

## Consequences

- `ports.py` gains a fourth Protocol; `fuse()` gains one additive term;
  `evaluate_hybrid` gains one constructor parameter and two hash inputs;
  `bounds.py` gains the frozen constants above. Every existing determinism test
  (three-normal-builds, reverse-insertion, fresh-process, four hash seeds) must
  pass unchanged, and the report must stay inside `max_report_bytes = 262_144`
  with a fourth signal's fields on every hit -- a real risk worth measuring
  early.
- The seven gates are re-measured. Their previous values are not the baseline to
  protect; the recorded prediction is the thing being tested.
- `make check` stays offline and network-free. The live ingestion path from
  ADR-0069 remains a separate credentialed target.
- Phase 4C's document-scope caveat still applies: the retrieval unit is a
  single-claim unit, and this must be re-derived before any multi-section parsed
  unit reuses the slice.

## Blueprint deviation

None. This implements the second of Section 7.3's seven signals and keeps the
hybrid, provenance-preserving posture of `:70`. It does not claim to satisfy
`:1227-1229`, which requires signals this slice does not add.

## Falsifiability probes

`probes_flipped == probes_total` gates the slice.

- `pr.semantic-partition-mismatch-refused` -- a manifest whose partition key
  differs from the declared one must refuse.
- `pr.semantic-missing-partition-refused` -- an absent partition must refuse,
  not silently run three-signal.
- `pr.semantic-cannot-invert-a-lexical-gold` -- maximum semantic credit applied
  to the runner-up of a gold pair separated by the minimum BM25 margin must not
  reorder them.
- `pr.semantic-respects-candidate-bound` -- returning more than
  `max_candidates_per_signal` must refuse.
- `pr.semantic-no-float-constructed` -- an AST sweep of `semantic.py` must find
  no float literal and no true division.
- `pr.semantic-tie-broken-by-document-id` -- equal exact cosines must order by
  id ascending under all four `PYTHONHASHSEED` values.
- `pr.semantic-partition-in-content-hash` -- changing the partition manifest
  hash must change the report `content_hash`.
- `pr.semantic-override-recorded` -- injecting a stub signal must appear in
  `signal_configuration.overrides` and change the hash.
- `pr.semantic-zero-spend-preserved` -- `external_spend_usd` must remain exactly
  `0` with the signal enabled and the network blocked.
- `pr.semantic-disabled-is-a-true-noop` -- with the signal disabled every fused
  score must equal the ADR-0032 value exactly, mirroring
  `test_fusion_is_declared_and_measured_in_score_space`.

## Validation and revisit trigger

Valid while: retrieval makes no call and constructs no float; the frozen
constants are unchanged; the partition binds into report identity; every probe
flips; and every pre-existing determinism and bounds test passes unmodified.

Reconsider if `duplicate_rate_at_5` regresses -- the prediction above says that
is the likely failure, and the response is to report the signal as net-negative,
not to retune the tiers.

Revisit with a new ADR before: widening the corpus beyond the frozen fixture set;
adding any of the five unimplemented Section 7.3 signals; introducing
approximate nearest neighbour; or letting a query vector be computed live inside
the retrieval path.

## Explicit deferrals

- **Corpus ingestion at scale.** The real blocker for wide retrieval. Needs its
  own ADR covering acquisition volume, per-document rights, and the applicability
  obligation each document carries.
- Symbol and formula search, citation-graph traversal, claim-graph traversal, and
  contradiction-oriented queries: four of Section 7.3's seven signals, unbuilt.
- Reranking with assumption-awareness (`:1160-1163`), which is what would make a
  semantic hit safe to treat as evidence, and which nothing here provides.
- Query-side embedding of anything other than the frozen gold queries.
