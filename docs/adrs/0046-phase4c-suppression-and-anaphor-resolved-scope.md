# ADR-0046: Suppression capability and anaphor-resolved scope blocks for Phase 4C

- **Status:** superseded before integration by ADR-0032. Preserved as the
  complete record of a concurrently developed alternative; its implementation
  is not authoritative and was not applied to `main`.
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 12.2 rebuildable index projections,
  Section 19 separately gated hybrid-retrieval prerequisites
- **Decision owners:** repository owner

## Integration disposition (2026-08-21)

This worktree was based on the ADR-0031 fixture generation and independently
closed the same applicability gate that ADR-0032 subsequently closed on
`main`. Applying its code would replace the current 19-document, 17-query
third fixture extension with an older 17-document, 15-query corpus and would
replace ADR-0032's compositional, single-claim-document exclusion rule with an
incompatible anaphor-block suppression schema. That is a regression, not an
additive merge.

The reasoning and measured results below remain useful historical evidence.
The authoritative Phase 4C implementation, schema, gates, and scope are those
of ADR-0032. No production code or fixture from this worktree was merged.

## Context

ADR-0031 implemented benchmark-scoped hybrid retrieval and recorded a measured
partial: six of seven gates hold and `applicability_precision_at_5` measures
`0.6` against a gate of `1.0` (ADR-0031 "Measured outcome", line 199). ADR-0031's
own revisit trigger fires on its first clause, "if a gate can only be met by
promoting a document into the top five". This ADR is that revisit.

**Owner ruling 2, obtained before this slice was designed.** ADR-0031's revisit
clause is a *revisit* trigger, not a stop: writing this ADR satisfies it. The
ruling is conditional. The removal-not-promotion property must be enforced
executably, not merely documented: the retained ordering must be a strict
order-preserving subsequence of the pre-suppression ordering, so that nothing is
reordered past anything else. That condition is acceptance assertion A-05 in
`tests/test_phase4c_hybrid_retrieval.py`, written as an explicit subsequence
walk rather than a set comparison, because a set comparison would accept a
promotion.

### Why the gate fails -- verified facts, not assumptions

The metric's denominator is `relevant_ids ∩ ordered_ids` and its numerator
intersects that further with `applicable_ids`
(`src/math_research/phase4c/benchmark.py`, `compute_measurements`). So the metric
is a function of which relevant documents are *returned* and of nothing else.
The ten observations pinned in the suite are:

| query | relevant retrieved | applicable | inapplicable retrieved |
|---|---|---|---|
| applicability-spectral | 2 | 1 | unbounded-spectral-mismatch |
| applicability-certificate | 3 | 2 | optimization-distractor |
| applicability-compactness | 2 | 1 | topology-distractor |
| applicability-selfadjoint | 3 | 2 | unbounded-spectral-mismatch |
| **total** | **10** | **6** | **4** |

**Demotion-only caps the metric at 0.6.** The four applicability queries have
fused candidate sets of 4, 5, 5 and 4 against a top-k of 5, so every retrieved
relevant document is already inside the cutoff and the ratio is invariant under
every reordering. This is enforced in code three times over: the hedge penalty
is `span + 1.0` applied identically to every demoted candidate, so it re-orders
and never removes; fusion raises if a fused score exceeds its pre-score; and the
top-k slice is the identity when the candidate count is at or below top-k.
ADR-0031 calls its own demotion-only rule "an error in this ADR, not a limitation
discovered during implementation".

**Reversing that error is necessary but not sufficient.** ADR-0031 measured an
exclusion variant at `6/7 = 0.857`. That reconciles exactly: `10 - 3 = 7`.
Exclusion under the existing sentence scope catches the three pinned demotions
and misses the fourth, because `applicability-selfadjoint` demotes nothing at
all.

**A correction this ADR carries rather than inherits.** ADR-0031 states that
"exclusion only shrinks the duplicate denominator and cannot raise its
numerator". The direction is mis-stated: shrinking a denominator at a fixed
numerator *raises* the rate. The conclusion ADR-0031 drew from it (that the
duplicate gate has room at the measured denominator) survives on the arithmetic
below, but the stated reason was wrong and is corrected here.

### Methodological hazard, disclosed rather than laundered

The diagnosis is already public. ADR-0031 names the failing query
(`applicability-selfadjoint`), the document (`unbounded-spectral-mismatch`) and
the mechanism. So its instruction to "fix the scope unit on a stated principle
*before* measuring" cannot mean "in ignorance". It is satisfiable only by a
principle a reviewer can evaluate **without reference to any query**, plus
controls that give the principle a way to fail. This ADR claims exactly that and
no more purity than the record permits.

The forbidden inference is "query X fails because the cue sits one sentence away,
therefore widen scope to N sentences". The whole sentence-window family
(`scope = cue sentence ± N`) is rejected here precisely because `N` has no source
other than the observed gap, which is the forbidden outcome "selecting thresholds
after observing a hybrid candidate"
(`docs/phase-4c/HYBRID_RETRIEVAL_BENCHMARK_V1.md`). Both surviving candidates are
parameter-free.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (C1 suppression + C3 anaphor-resolved scope block) | Metric is a function of what is returned; the sentence unit requires a disclaiming sentence to restate its own subject, which expository English does not do | Reaches the gate by removal rather than promotion; scope rule is parameter-free and statable with no reference to any query; keeps every suppressed candidate in the report | Suppression must be shown not to be hiding; on this fixture the suppression set coincides with the three non-applicable documents, so generality is unproven | Subsequence invariant (A-05); full retention of suppressed candidates in the report (A-16); label-mutation invariance (A-22); no cue-table change (A-13) |
| C2 (whole-document scope) | `lexical.py` builds an OR-of-tokens FTS expression, so every retrieved document matches at least one query token by construction | Simplest rule to state | The topical anchor becomes vacuous: C2 degenerates into a query-independent document blocklist, where one "we do not treat the unbounded case" sentence suppresses a forty-page paper for every query | -- |
| C4 (declared unit type / structural metadata) | `finite-dimensional-spectral.txt` and `unbounded-spectral-mismatch.txt` both open `Project-authored source.` | Would need no linguistic rule | Zero discriminative power on the one pair that matters, since the applicable gold and the inapplicable document share the genre marker exactly; and it reconstructs `source_class`, which the lexical index deliberately keeps out of SQLite -- forbidden in substance | -- |
| Interoperate (dependency/negation-scope parsing) | -- | Real anaphora resolution | Needs a third-party parser on a documented acceptance path, forbidden by ADR-0026 and AGENTS.md | -- |
| Build/defer (keep the recorded partial) | The partial is already recorded | Zero risk | Leaves a known error in ADR-0031 (demotion-only) unrepaired and a gate unmet with a stated cause | -- |

On **C2 versus C3**, honestly: on this fixture the two give identical results,
because `unbounded-spectral-mismatch` is the only corpus document whose
disclaimer opens with an anaphor. The fixture cannot discriminate them. C3 was
chosen on out-of-benchmark degradation, not on the metric.

## Decision

Adopt C1 + C3.

**C1 -- suppression capability.** A signal that has determined a document
disclaims its own coverage of what the query asked **removes** it from the
returned list rather than ranking it last, because retrieval returns a list and
precision is measured over what is returned. This reverses ADR-0031's
demotion-only constraint, which that ADR itself identifies as its own error.

**C3 -- the scope unit is an anaphor-resolved scope block.** Stated with no
reference to any query: the sentence unit frozen in ADR-0031 contains a
linguistic error independent of any measurement. It requires the disclaiming
sentence to *restate its own subject*. English expository prose does not do that
-- a writer who introduces a result in one sentence disclaims it in the next with
a pronoun ("It does not provide...", "This says nothing about..."), because
repeating the noun phrase would be redundant. So a same-sentence co-occurrence
rule systematically misses precisely the well-written disclaimers and fires only
on the redundant ones. The scope of a disclaimer is its discourse segment, and
the minimal deterministic realisation of that is: a sentence whose subject is a
sentence-initial third-person anaphor inherits the referential content of the
sentence immediately preceding it.

**The rule.** A *scope block* is each sentence, unioned with the immediately
preceding sentence if and only if the sentence begins with a member of a closed
frozen anaphor list. A document is suppressed when a matched query term and a
self-disclaiming cue occur in the same scope block.

- The anaphor list is frozen, closed, lowercase, single-token, and matched in
  sentence-initial position only under the existing shared tokenizer:
  `("it", "this", "that", "these", "those", "they")`.
- **Antecedent depth is exactly one, and that is not a threshold.** The rule is
  "an anaphor's antecedent is the preceding sentence". Chaining transitively
  would make it a *window*, a window has a length, and a length read off a
  corpus is the forbidden outcome. Non-transitivity is asserted directly (A-11).
- There is no cue-count threshold; `CUE_COUNT_THRESHOLD` stays `None`.
- **The cue tables are unchanged, byte for byte.** Adding a cue in this slice
  would be indefensible, so both tuples are pinned as literals in the suite
  (A-13).

### Boundaries of ADR-0031 that stand unchanged

Fusion stays in score space. Cue classes stay split and frozen. Alias entries
stay keyed on name phrases, with no document identifier in the alias table. No
embeddings, vectors, network, model calls, or new dependencies. Retrieval remains
candidate generation: **suppression is a retrieval decision, not an
applicability judgement**, and a suppressed document is not thereby found
inapplicable.

### Four suppression invariants, enforced at runtime and not merely documented

1. suppression may never raise a fused score;
2. suppression may never introduce a document outside the pre-suppression
   candidate set;
3. the retained ordering is a strict order-preserving **subsequence** of the
   pre-suppression ordering (owner ruling 2's condition);
4. every suppressed candidate remains fully in the report with its cue evidence,
   its pre-suppression rank, and its applicability visibility.

### Suppression must not become hiding

`HYBRID_RETRIEVAL_BENCHMARK_V1.md` lists "hiding a failed query, zero-hit query,
duplicate, or inapplicable hit" as a forbidden outcome. Three controls earn the
distinction between removal and hiding: every suppressed candidate keeps a full
hit record with cue evidence and pre-suppression rank; each query reports
`suppressed_ids` and `suppressed_inapplicable_ids` alongside `ordered_ids`; and a
non-gated disclosure metric, `applicability_precision_at_5_pre_suppression`,
keeps the pre-improvement `0.6` computable from the emitted report forever. That
disclosure metric is deliberately absent from `THRESHOLD_KEYS`,
`GATE_COMPARISONS` and `gate_evaluation`: it can never pass or fail a gate.

### Field rename

`HedgeVerdict.demoted` becomes `HedgeVerdict.suppressed`, and `FusedHit.demoted`
becomes `FusedHit.suppressed`. A field called `demoted` that removes documents is
a lie in a self-describing report. The report schema version moves to
`adaivy.phase4c-hybrid-retrieval.v2` and a v1 report is a hard rejection in
`verify_report`.

## Registered prediction

Recorded **before** the implementation was written, and left unedited afterwards.

Predicted corpus-wide suppression set, exactly three documents:
`optimization-distractor`, `topology-distractor`,
`unbounded-spectral-mismatch`.

Predicted per-query suppressions, with the top-5 count before and after:

| query | suppressed | before -> after |
|---|---|---|
| lemma-compactness | topology-distractor, unbounded-spectral-mismatch | 5 -> 5 |
| lemma-spectral | unbounded-spectral-mismatch | 3 -> 2 |
| lemma-separation | -- | 3 -> 3 |
| applicability-spectral | topology-distractor, unbounded-spectral-mismatch | 4 -> 2 |
| applicability-certificate | optimization-distractor | 5 -> 4 |
| applicability-compactness | topology-distractor, unbounded-spectral-mismatch | 5 -> 3 |
| applicability-selfadjoint | unbounded-spectral-mismatch | 4 -> 3 |
| contradiction-boundary | -- | 3 -> 3 |
| contradiction-monotonicity | -- | 2 -> 2 |
| notation-banach | -- | 2 -> 2 |
| notation-psd | unbounded-spectral-mismatch | 3 -> 2 |
| renamed-uniform-bound | topology-distractor, unbounded-spectral-mismatch | 5 -> 3 |
| renamed-maximal-chain | -- | 4 -> 4 |
| renamed-container-count | -- | 2 -> 2 |
| renamed-known | topology-distractor, unbounded-spectral-mismatch | 4 -> 2 |
| | | **54 -> 42** |

The delta attributable to C3 over C1 alone is exactly four new suppressions of
`unbounded-spectral-mismatch` -- on `lemma-spectral`,
`applicability-selfadjoint`, `renamed-uniform-bound` and `renamed-known`, the
queries where the pinned measurements show it retrieved but not demoted.

Predicted metrics: `necessary_lemma_recall_at_5` `1.0` (3/3);
**`applicability_precision_at_5` `1.0` (6/6)**; `contradiction_recall_at_5`
`1.0` (2/2); `notation_variant_recall_at_5` `1.0` (2/2);
`renamed_known_result_recall_at_10` `1.0` (4/4); `duplicate_rate_at_5`
`1/42 ~= 0.0238095`; `external_spend_usd` `0`; `gate_summary` `{"pass": 7,
"fail": 0, "undetermined": 0, "overall": "pass"}`; `failing_gates` `[]`; and the
disclosure metric `applicability_precision_at_5_pre_suppression` `0.6` (6/10).

Predicted invariant: no promotion occurs on any query, and the duplicate
numerator stays `1`.

**Epistemic status of the prediction.** This is a *derivation* from values
already pinned in the repository, not a blind bet. It checks that the
implementation matches the design. It does **not** show that the design
generalises. Only a control the signal was not authored against could do that,
and that control is deferred below.

### Falsifiers

Any one of these stops the slice and produces a recorded partial, never an
adjustment:

- **F1.** Any recall gate below `1.0` -- the scope block suppressed a gold.
- **F2.** The suppressed set is anything other than the three named documents.
- **F3.** `applicability_precision_at_5` lands at `0.857` (the scope block did
  not fire) or stays at `0.6` (suppression is not reaching `ordered_ids`).
- **F4.** `duplicate_rate_at_5 > 0.05`, or the duplicate numerator rises above
  `1` -- the latter would prove suppression promoted a document into the cutoff.
- **F5.** The retained ordering is not a subsequence of the pre-suppression
  ordering for some query.
- **F6.** Closing the gate requires touching the cue tables, adding a seventh
  anaphor, or chaining anaphora past depth one.

## Measured outcome

Implemented and measured on 21 August 2026. Seven of seven gates hold. Every
value in the registered prediction above was reproduced exactly, and the
prediction was not edited after the measurement. No falsifier fired.

| Metric | Baseline | ADR-0031 hybrid | This slice | Support | Gate |
|---|---|---|---|---|---|
| necessary-lemma recall@5 | 1.0 | 1.0 | 1.0 | 3/3 | pass |
| applicability precision@5 | 0.6 | 0.6 (fail) | **1.0** | 6/6 | pass |
| contradiction recall@5 | 1.0 | 1.0 | 1.0 | 2/2 | pass |
| notation-variant recall@5 | 1.0 | 1.0 | 1.0 | 2/2 | pass |
| renamed-known-result recall@10 | 0.0 | 1.0 | 1.0 | 4/4 | pass |
| duplicate rate@5 | 1/50 | 1/54 | 1/42 | 1/42 | pass |
| deterministic rebuild | -- | identical | identical | -- | pass |
| external cost | 0 | 0 | 0 | -- | pass |

`gate_summary` is `{"pass": 7, "fail": 0, "undetermined": 0, "overall":
"pass"}`; `failing_gates` is `[]`.

Disclosure metric, non-gated: `applicability_precision_at_5_pre_suppression`
measures `0.6` (6/10), which is ADR-0031's value, and the acceptance suite
recomputes it independently from `results` by running the same metric definition
over `pre_suppression_ordered_ids`.

The corpus-wide suppression set is exactly the three predicted documents:
`optimization-distractor`, `topology-distractor`,
`unbounded-spectral-mismatch`. The per-query suppressions and the retrieved-hit
total match the prediction row for row, `54 -> 42`. The duplicate numerator is
still `1`; it did not rise, which is what would have shown a promotion. No
promotion occurs on any query: the retained ordering is an order-preserving
subsequence of the pre-suppression ordering for all fifteen queries, checked at
runtime in fusion and again in the suite.

The improvement is attributable to both halves of the decision, and the suite
pins each half separately. Suppression alone would have reached `6/7 = 0.857`,
the value ADR-0031 measured for an exclusion variant; the residual was
`applicability-selfadjoint`, and the suite asserts that under the ADR-0031
sentence unit that query still suppresses nothing, so the last observation is
closed by the scope block and by nothing else.

One factual correction to this ADR's own design notes, recorded rather than
quietly fixed: the design predicted that `unbounded-spectral-mismatch` would be
the only corpus document whose scope-block partition differs from its sentence
partition. Measured, there are two: `renamed-cover-result` also opens a sentence
with an anaphor ("This older formulation..."). It carries no self-disclaiming cue
anywhere in its bytes, so it is not suppressible under any scope unit and no
measured value changes. The acceptance suite pins the exact two-document set. The
correction strengthens rather than weakens the C2-versus-C3 discussion above:
the block rule fires on prose structure, in a document whose applicability label
is `applicable`, and not on the label.

The prediction being confirmed is evidence that the implementation matches the
design. It is **not** evidence that the design generalises, for the reason stated
under "Epistemic status" above.

## Consequences

The acceptance suite remains the sole executable record of this slice's
thresholds, and it grows the assertions this decision needs: the subsequence
invariant, the empty-cue-table identity, the scope-block unit tests including
non-transitivity and the exact anaphor tuple, the corpus-wide guarantee that no
gold in any category carries a self-disclaiming cue anywhere in its body (which
is what protects the recall gates under *any* scope unit), the full retention of
every suppressed candidate in the report, and the independent recomputation of
the disclosure metric.

Two tests exist because turning a suite green removes coverage if nothing is
watched. First, the CLI exit-1 path keeps a test: with every gate passing, the
"a failing gate is never hidden" behaviour would otherwise become untested at
exactly the moment nothing fails, so a test forces a gate failure with a
degenerate lexical signal and asserts exit 1 plus a still-emitted report.
Second, the fresh-process determinism helper is tightened from tolerating exit 1
to requiring exit 0.

One reporting consequence is worth stating because it looks like a regression
and is not one. An inapplicable document named in an applicability query's
`relevant_ids` is topically relevant, so removing it makes it a *missed relevant*
hit: `queries_with_missed_relevant_ids` now names all four applicability queries,
where under ADR-0031 it was empty. That is the correct reading of the fixture and
it is disclosed rather than smoothed over. The suite pins the property that
nothing else goes missing -- every missed relevant document is one this slice
suppressed on purpose, no applicable document is ever missed, and every
non-applicability query still misses nothing, which is what the five recall gates
at `1.0` say.

`SCHEMA_VERSION` moves to `adaivy.phase4c-hybrid-retrieval.v2`. Every canonical
report hash changes, and a v1 report is rejected rather than migrated. This is a
real migration cost, accepted because the semantic content of a report changed:
`demoted` became `suppressed`, `ordered_ids` now means "retained", and three new
per-query keys and one new metric appear.

ADR-0031's measured-outcome table is **not** edited. It is the historical record
of the partial, and rewriting it would erase the discontinuity. ADR-0031's status
line records that it is partially superseded here.

The honest risk is unchanged in kind from ADR-0031 and is now larger in one
respect: on the current 17 documents the suppression set is *exactly* the three
non-applicable documents. A rule that perfectly reconstructs a withheld label on
a hand-authored corpus is not thereby shown to generalise. A-22 shows the rule
does not *read* the label -- every `applicability`, `source_class` and
`duplicate_group` value in an in-memory manifest copy is mutated and the
suppression set is unchanged -- and A-23 makes the coincidence visible by pinning
the suppressed set as a literal rather than reading it from the manifest. Neither
shows the rule would not over-fire on a corpus where an applicable document
disclaims something no query asked. A reviewer should read those two tests, and
the deferral below, before treating the `1.0` as generality.

## Blueprint deviation

One real deviation, resolved by an owner ruling rather than by a silent
relaxation.

**The `duplicate_rate_at_5` non-worsening clause.**
`docs/phase-4c/HYBRID_RETRIEVAL_BENCHMARK_V1.md` says a hybrid candidate "may
not worsen any metric already met by the baseline". Read literally against the
baseline *value*, `1/42 > 1/50`, so this slice worsens the duplicate rate.

**Owner ruling 1.** For a ratio metric whose denominator is a retrieval volume,
that clause means "must still meet its gate", not "must never move off the
baseline value". The rationale: such a ratio is not monotone in retrieval
quality. Removing a non-duplicate bad result raises the rate while removing zero
duplicates, so the literal reading penalises a signal precisely for improving
precision. The suite's duplicate assertion therefore compares against
`thresholds["duplicate_rate_at_5_maximum"]` rather than against
`BASELINE_METRICS`, with the reasoning written inline in the test rather than as
a bare relaxation. `HYBRID_RETRIEVAL_BENCHMARK_V1.md` carries a **dated note**
recording the ruling; the clause itself is not reworded.

**Necessity, as an impossibility argument.** Reaching `1.0` on applicability
precision removes all four inapplicable relevant observations, so the duplicate
denominator falls to at most `50`. The duplicate numerator cannot fall below `1`
without suppressing a cue-free applicable certificate gold, which would itself be
"hiding a duplicate". So the rate is at least `1/50` -- strictly above the
baseline value unless the signal removes exactly the four label-identified
documents and nothing else, which is a signal keyed on the label, the first
forbidden outcome. Under the literal reading, the gate and the clause are jointly
unsatisfiable by any label-blind signal on this corpus.

**Revisit trigger for the ruling.** If the corpus ever grows enough that a
label-blind signal keeps the duplicate rate at or below the baseline value, the
literal clause becomes satisfiable again and this reading must be withdrawn.

## Explicit deferrals

**Negative controls for the suppression rule -- the most important deferral.**
On the current 17 documents the suppression set is exactly the three
non-applicable documents. The control that would test whether the rule
over-fires: at least two documents labelled `applicable` that carry a
self-disclaiming cue about something no query asked, plus one query whose gold
*is* a disclaiming document. Such a control can only lower the metric, so adding
it is not fitting. It is deferred because a fixture change and a rule change
measured together are two variables and one number, and because a fixture
extension needs owner approval per ADR-0031. Until it exists, the residual risk
is that the fixture author wrote disclaimers into exactly the non-applicable
documents and the rule is reading that authorship rather than a linguistic
property.

Unchanged from ADR-0031: an embedding or vector signal and every Section 12.2.1
obligation with it, blocked on an owner-issued current Phase 4A `embedding`
rights decision naming the processor; consumption of admitted Phase 4B parse
projections, which returns to the full gate package; any `RightsUse` extension;
any change to the Phase 3A index.

Newly deferred here: anaphora resolution beyond sentence-initial token matching.
Real anaphora resolution needs a parser, which is forbidden on a documented
acceptance path, so the limitation is stated in the `text` module docstring in
the same voice as the existing sentence-rule limitation rather than worked
around.

## Process classification

ADR-0026 escalates any slice that touches the Phase 3B sealed runtime, the Phase
4A rights boundary, deletable content, or protected evidence manifests. Checked
one at a time: no subprocess and no container, and the suite already forbids
`subprocess` and `socket` in the package and the string `phase3b` in any Phase 4C
module; no `RightsUse` member is added or read, and the suite forbids importing
`phase4a`; the only data read is `fixtures/phase4c/`, project-authored under
`LicenseRef-AdaIvy-Synthetic-Fixture` and therefore not ADR-0021 deletable
acquired content; no ADR-0022 protected evidence manifest is read or written. So
this slice stays in the ADR-0026 lightweight process: one ADR plus an acceptance
suite. ADR-0031's own revisit trigger firing is not the ADR-0026 escalation
clause and summons no entry gate report, threshold inventory, security control
inventory, dependency assessment, or requirement-test matrix.

## Validation and revisit trigger

The decision stays valid while the complete offline check remains green, the
module reaches no network and imports no third-party package, fusion stays in
score space, suppression stays removal-only with the retained ordering a
subsequence of the pre-suppression ordering, every suppressed candidate stays
fully visible in the report with its pre-suppression rank, the disclosure metric
stays out of every gate structure, the cue tables and the anaphor tuple stay
byte-frozen, and the alias fixture stays free of document identifiers.

Reconsider if the suppression rule is found to suppress a gold in any category;
if a cue has to be added or an anaphor has to be added to close a gate; if
anaphora has to be chained past depth one; if a cue-count threshold or any other
numeric scope parameter becomes necessary; if the negative controls deferred
above show the rule over-firing on applicable documents; if a label-blind signal
ever keeps the duplicate rate at or below the baseline value, which withdraws
owner ruling 1; or if any acceptance path acquires a network call, a model call,
or an unpinned dependency.
