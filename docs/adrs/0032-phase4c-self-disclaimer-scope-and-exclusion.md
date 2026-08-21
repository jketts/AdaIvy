# ADR-0032: Self-disclaimer scope, exclusion, and a compositional cue rule

- **Status:** accepted and implemented; the five predictions below were
  recorded **before** measurement, per the ADR-0031 revisit condition, and all
  five held on measurement (see "Measured outcome")
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 12.2 rebuildable index projections,
  Section 19 separately gated hybrid-retrieval prerequisites
- **Decision owners:** repository owner

## Context

ADR-0031 shipped Phase 4C with `applicability_precision_at_5` measured at
`0.6` against a gate of `1.0`, and fired its own revisit trigger on the first
clause. It states the condition any successor must meet:

> A future slice that wants this gate must either fix the scope unit on a
> stated principle *before* measuring, or use a different signal class.

It also records two measured facts that bound this slice. First, the
demotion-only constraint makes the gate unreachable by construction: the four
applicability queries have fused candidate sets of 4, 5, 5 and 4 against a
top-k of 5, so every retrieved relevant document is already inside the cutoff
and `6/10` is invariant under every reordering. ADR-0031 names this an error in
itself, not a discovery. Second, an exclusion variant measured `6/7 = 0.857`,
with the whole residual at `applicability-selfadjoint`, where
`unbounded-spectral-mismatch` escapes demotion because its self-disclaiming
sentence shares no token with the query and the matched terms sit in a
preceding sentence carrying no cue.

A third fact is visible in the acceptance suite rather than the ADR.
`tests/test_phase4c_hybrid_retrieval.py::test_the_cue_table_hits_exactly_the_non_applicable_documents`
asserts that the six frozen self-disclaiming cue phrases are coextensive with
the three non-applicable documents on this corpus. Under sentence scope that
coextension is partly harmless, because a cue only fires when a query term
lands in its sentence. Under any wider scope it is not: the signal would reduce
to "this document is one of the three the lexicon was authored against", and a
gate closed that way measures the lexicon, not the method. ADR-0031 already
names a fitted cue lexicon as this slice's weakest part. Widening the scope
without also changing how cues are constructed would make that weakness
load-bearing.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (document scope + exclusion, keep the enumerated cue table) | ADR-0031 measured exclusion at 0.857; only the three non-applicable documents carry a cue | Closes the gate with the smallest diff | The cue table is coextensive with the target set, so the gate would measure the lexicon; ADR-0031's stated weakness becomes load-bearing | Principle stated before measuring |
| Wrap (document scope + exclusion + compositional cue rule + adversarial controls) | Same, plus the project's existing evidence vocabulary | Gate closes on a rule rather than a list; generalization is measured rather than asserted | Third fixture extension; two new vocabularies to freeze; the over-exclusion probe can break document scope and leave the gate open | Owner-approved fixture extension; predictions recorded first |
| Interoperate (accept 0.6 as the measured ceiling) | ADR-0031's own arithmetic | Honest, zero new code | Lowers a frozen benchmark threshold after measuring it; leaves the WP2 gate open under WP4 and WP5 | Threshold amendment |
| Build/defer (no new slice) | -- | -- | Leaves a fired revisit trigger under later work; silent drift, prohibited by AGENTS.md | -- |

## Decision

Adopt the wrap option. Four changes, each with its principle stated here and
its prediction recorded below before any measurement.

### 1. The scope unit is the retrieval unit, not the sentence

ADR-0031 partitions cues by *what the cue is about*: a self-disclaiming cue is
about the document's own evidentiary coverage, an object-level cue is about the
mathematics. That partition already determines the scope, and the two classes
do not share it. A claim about what this document supplies has the document as
its subject, so its scope is the document. A claim that a mathematical object
fails has that object as its subject, so its scope is the sentence containing
it. Sentence scope for self-disclaiming cues was an unmotivated inheritance
from the object-level class, not a consequence of the partition.

Object-level cues keep sentence scope and remain non-demoting, unchanged.

**Validity bound.** The rule is declared valid only where the retrieval unit is
a *single-claim unit*. The Phase 4C corpus documents are two-to-three sentence
single-claim units, so the document is the single-claim unit here. When the
retrieval unit becomes a multi-section parsed document — the deferred Phase 4B
projection slice — the scope must be re-derived to the smallest enclosing
single-claim unit, and this rule may not be carried across unchanged. This is a
boundary, not a fix, and it is recorded in the same terms AGENTS.md uses for the
two synthesis-slice boundaries.

### 2. The signal excludes rather than demotes

The demotion-only constraint is withdrawn as ADR-0031's recorded error. A
document whose own bytes disclaim the evidentiary element the query asks for is
not a worse candidate for that query; it is not a candidate. Exclusion removes
it from the ordering.

ADR-0031's stated reason for demotion-only — protecting `duplicate_rate_at_5` —
was unnecessary, but its arithmetic was also stated wrongly there and is
corrected here. Exclusion *shrinks* the duplicate denominator, which *raises*
the rate at a constant numerator; it is not safe merely because the numerator
cannot rise. The gate is `<= 0.05`, so at numerator `1` the denominator must
stay at or above `20`. Exclusion removes at most a handful of hits from a
denominator in the fifties, so the margin is wide. The gate is asserted against
the measured value regardless, and the property below is asserted separately,
because exclusion can move a retained document *into* the cutoff window and the
duplicate pair travels together.

Three invariants replace ADR-0031's demotion-only invariant:

1. exclusion never raises any document's fused score — scores are untouched;
2. exclusion preserves the relative order of every retained document;
3. exclusion never names a document outside the candidate set.

Invariant 2 is deliberately weaker than "never promotes". A retained document
can enter the top-k because something above it left. That is the point of
exclusion, and it is why the duplicate gate is re-measured rather than argued.

### 3. Cues are composed, not enumerated

The six enumerated self-disclaiming phrases are replaced by a composition of
two frozen vocabularies. A self-disclaimer fires only where both parts are
present:

- an **absence operator** whose subject is the document's own supply of
  material — `does not provide`, `states no`, `is inapplicable`,
  `no ... is supplied`, `no ... is given`, `is insufficient`, `may look`;
- an **evidence noun** naming what a document supplies — `theorem`, `lemma`,
  `proof`, `hypothesis`, `hypotheses`, `certificate`, `bound`, `eigenbasis`,
  `applicability`, `witness`.

The operator vocabulary carries *subjecthood* and the noun vocabulary carries
*evidentiality*, and neither fires alone. This is what separates
`this note states no hypotheses` — the document disclaiming its own coverage —
from `the argument uses no compactness assumption`, where the mathematics is
the subject and a missing hypothesis is a strength. `uses no` is therefore not
an operator, and its exclusion is a consequence of the subjecthood principle
rather than a listed exception.

The two ADR-0031 exclusions survive for the same reason they were made:
`without` states a hypothesis (`without compact resolvent`), and bare `no` is
mathematical content that false-positives on
`renamed-container-count-result`. Both now fall out of the operator rule
instead of being enumerated exceptions.

There is still no cue-count threshold. Presence is boolean.

### 4. Two adversarial applicability controls

The owner has approved extending the frozen fixtures a second time. Two
documents and two queries are added, authored against the principles in 1 and 3
and deliberately not against the vocabularies:

- a non-applicable document that self-disclaims through a composition of
  in-vocabulary parts that appears in **no** enumerated ADR-0031 phrase. It
  probes whether the compositional rule generalizes where the enumerated table
  would have missed.
- an applicable document that contains an absence claim about a *mathematical*
  object rather than an evidentiary one. It probes over-exclusion, and it is the
  control that can break document scope.

The corpus becomes 19 documents and the query set 17, with 6 applicability
queries. Previously pinned measured values again stop describing the fixture
set and are re-pinned.

## Predictions recorded before measurement

Stated here so the outcome can contradict them:

1. `applicability_precision_at_5` reaches `1.0`. The residual ADR-0031 measured
   is `unbounded-spectral-mismatch` on `applicability-selfadjoint`; document
   scope reaches its disclaimer from the query terms in the preceding sentence.
2. No gold in any category is excluded. Only the three non-applicable documents
   carry a document-as-subject absence claim over an evidence noun today.
3. The generalization control is excluded by the compositional rule.
4. The over-exclusion control is retained. This is the least certain
   prediction: if document scope is too coarse, this is where it shows, and the
   gate stays open with a better-understood cause than ADR-0031 had.
5. `duplicate_rate_at_5` stays inside `0.05`, and no previously passing gate
   regresses.

A `1.0` obtained by amending any of the four rules after seeing which control
failed is worthless, and is the forbidden outcome this ADR is written to
prevent.

## Measured outcome

Implemented and measured on 21 August 2026, on the extended fixtures: 19
documents, 17 queries, 6 of them applicability. Seven of seven gates hold. The
baseline column is the pure lexical baseline re-measured on the same extended
fixtures (`spikes/phase4c_benchmark/evaluator.py`, and reproduced inside the
harness with both vocabularies emptied and the alias signal disabled).

| Metric | Baseline | Hybrid | Support | Gate |
|---|---|---|---|---|
| necessary-lemma recall@5 | 1.0 | 1.0 | 3/3 | pass |
| applicability precision@5 | 8/14 = 0.571 | **1.0** | 8/8 | pass |
| contradiction recall@5 | 1.0 | 1.0 | 2/2 | pass |
| notation-variant recall@5 | 1.0 | 1.0 | 2/2 | pass |
| renamed-known-result recall@10 | 0.0 | **1.0** | 4/4 | pass |
| duplicate rate@5 | 1/61 = 0.0164 | 1/50 = 0.02 | 1/50 | pass |
| deterministic rebuild | -- | identical | -- | pass |
| external cost | 0 | 0 | -- | pass |

Precision rose by removing candidates, not by promoting any: the numerator
stayed at 8 and the denominator fell from 14 to 8. Exactly four documents are
ever excluded, and they are exactly the four non-applicable documents in the
corpus -- `optimization-distractor`, `residual-bound-gap`,
`topology-distractor`, `unbounded-spectral-mismatch`.

### Every prediction, held or failed

**Prediction 1 -- `applicability_precision_at_5` reaches `1.0`. HELD.** Measured
`8/8`. The ADR-0031 residual closed for the stated reason and not another one:
on `applicability-selfadjoint` the disclaiming sentence of
`unbounded-spectral-mismatch` still shares no token with the query, and the
acceptance suite asserts that ADR-0031's sentence scope would fire on *no*
sentence of that document under that query while document scope does fire. The
mechanism, not just the number, is pinned.

**Prediction 2 -- no gold in any category is excluded. HELD.** Asserted over
every one of the 17 queries and all five categories, with a gold read as
`applicable_ids` for an applicability query and `relevant_ids` everywhere else.
Neither contradiction gold is excluded, and `boundary-contradiction` still
carries all three object-level cues in a sentence containing matched query
terms while being retained.

**Prediction 3 -- the generalization control is excluded by the compositional
rule. HELD.** `residual-bound-gap` is excluded through `no ... is given` over
the evidence noun `proof`. The frame fires on that document and on no other in
the corpus, and none of ADR-0031's six enumerated phrases matches the document
at all: an enumerated table would have missed it, which is what the composition
was adopted for.

**Prediction 4 -- the over-exclusion control is retained. HELD.** This was the
least certain prediction and the one that could have broken document scope.
`hypothesis-free-supremum` is excluded by no query. `uses no` is not an absence
operator because its subject is the mathematics, and the suite demonstrates the
cost of getting that wrong rather than asserting it: admitting either `uses no`
or bare `no` as an operator excludes this applicable gold immediately.

**Prediction 5 -- `duplicate_rate_at_5` stays inside `0.05` and no previously
passing gate regresses. HELD, with the predicted cost visible.** No gate
regressed. The duplicate rate moved from `1/61` to `1/50`: exclusion shrinks the
denominator at a constant numerator, so the rate *rose* while staying well
inside the gate, exactly as this ADR's corrected arithmetic said it would. The
`>= 20` denominator floor the ADR derived is met with a factor of 2.5 to spare.
This is recorded as a cost rather than smoothed over: measured against the pure
lexical baseline the hybrid does worsen this one already-met metric, which the
benchmark spec's "may not worsen" comparison clause otherwise reads against. The
gate is asserted against the measured value, both endpoints are pinned in the
acceptance suite, and the discontinuity is recorded in the spec document.

None of the four rules was amended after measurement. Neither vocabulary grew,
no threshold was added, and no fixture was adjusted to move a gate. The
`1.0` here is therefore the kind the ADR was written to allow rather than the
kind it was written to prevent.

### Recorded consequences of exclusion

Exclusion is deliberately allowed to pull a retained document *into* the cutoff
window, and it does: `lemma-compactness` gains `finite-dimensional-spectral`
and `renamed-uniform-bound-result`, and `applicability-supremum` gains
`finite-dimensional-spectral` at rank five, because documents above them left. The acceptance suite asserts this as a
property rather than treating it as an anomaly, together with the three
invariants -- no score changes, retained relative order is preserved, and no
document outside the candidate set is ever named.

The report schema version moved to `adaivy.phase4c-hybrid-retrieval.v2` because
the report shape changed: `demoted_ids` became `excluded_ids`, and each hit now
carries its absence operators, evidence nouns, and matched query terms instead
of a hedge penalty and a demotion flag. Nothing is filtered from the report; an
excluded document keeps its hit, its operator, its noun, and its matched terms.

The ADR-0031 penalty term was deleted rather than retained at zero. With
exclusion it can no longer change an outcome, and a term that changes no outcome
is dead complexity that later readers would have to re-derive.

### Not closed by this slice

Document scope remains declared valid only for single-claim retrieval units.
That boundary is untested here because the corpus has no multi-section unit, and
it must be re-derived before the deferred Phase 4B projection slice reuses this
rule.

The composition is coextensive with the four non-applicable documents *as a
whole* on this corpus. What the suite establishes is narrower and is the thing
ADR-0031 lacked: no single absence operator and no single evidence noun is
coextensive with that set, so the gate measures the rule rather than a list
authored against the answer key. A corpus with a self-disclaiming document that
is nonetheless applicable would test the composition itself, and none exists
today.

## Consequences

The acceptance suite remains the sole executable record of the slice's
thresholds and now has to assert the properties above: that exclusion never
raises a score, that it preserves relative order among retained documents, that
neither vocabulary fires alone, that no single vocabulary entry is coextensive
with the target set, that no gold is excluded in any category, and that removing
either vocabulary entirely restores the pure lexical ordering.

Replacing the enumerated table with a composition removes the coextension the
old suite asserted, so
`test_the_cue_table_hits_exactly_the_non_applicable_documents` is replaced by
its compositional successors rather than kept.

Three fixture extensions now sit between the originally frozen benchmark and
the current numbers. Anyone comparing against a pre-extension measurement is
comparing across corpora. The discontinuity is recorded here, in ADR-0031, and
in the spec document.

Retrieval remains candidate generation. Exclusion is not an applicability
judgement: it removes a candidate from a result list and creates no premise,
warrant, applicability record, or graph admission. A document excluded here is
still fully present in the report, with its operator, its noun, and its scope
recorded, because nothing is filtered from the report.

## Validation and revisit trigger

The decision stays valid while the complete offline check remains green, the
module reaches no network and imports no third-party package, fusion stays in
score space, exclusion satisfies the three invariants above, and the alias
fixture stays free of document identifiers.

Reconsider if either vocabulary has to grow to pass a control, if a cue-count
threshold becomes necessary, if any gold is found excluded in any category, if
the retrieval unit stops being a single-claim unit, or if a gate can only be met
by promoting a document the lexical signal did not retrieve.
