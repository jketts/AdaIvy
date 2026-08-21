# ADR-0034: Execute the Section 18.4 generality control suite with falsifiability probes

- **Status:** accepted for the bounded WP5 Phase 6 generality slice; implemented
  21 August 2026, thirteen controls executing and thirteen probes flipping
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 18.4 generality controls, Section 17.5
  evaluation tiers 1--7, Section 20 scenarios A, B, D, H, I, J and L, Section 18.2
  plugin core contract
- **Decision owners:** repository owner

## Context

ADR-0024 records that "the generality suite executes five deterministic trust
controls". It did not. `_generality_controls()` in
`src/math_research/phase6/service.py` was a literal five-tuple table in which the
`graph_admitted` element was the constant `False` and `passed` was derived as
`admitted is False`. No `TrustPolicy` was constructed, no fixture was read, no
dossier existed, and no policy was called. `controls_passed == 5` was therefore a
tautology, unfalsifiable by any input, and `confirm()`'s `status` field depended
on it. Under AGENTS.md -- "a scenario's forbidden outcomes must be demonstrated
impossible, not merely left untested" -- the five controls did not meet the bar.

Three further measured facts shaped this slice.

**All five controls asserted non-admission.** A system that rejects every input
scored 5/5. Section 18.4 names known theorems *first*, and it is the only
category that makes the other five non-vacuous, because it is the only one whose
failure mode is silence rather than over-claiming. It was the one category
absent.

**Section 18.4 is not a superset of ADR-0024's five.** 18.4 names six categories
with no identifiers, no count and no pass threshold: known theorems, false
conjectures, missing-assumption traps, semantic mistranslations, inapplicable
citations, cross-representation problems. Two of ADR-0024's five
(`unsupported_consensus`, `finite_experiment_overreach`) are Section 20 scenarios
A and B, not 18.4 categories. ADR-0024 covered three of 18.4's six; known
theorems, false conjectures and missing-assumption traps were absent.

**Nothing bound the suite definition into the protocol.** `PROTOCOL_FIELDS`
pinned the Phase 5 fixture hash, the capability allowlist, the metrics, the
stopping rule and the freeze instant, and `protocol_hash = canonical_hash(protocol)`
made all of them unadaptable. The control suite was not among them. Once the
suite became a real fixture, a failing run could have been answered by editing
the suite -- making the protocol *more* adaptable by held-out feedback than it was
before the slice.

Two ordering defects were also measured. `confirm()` called `freeze_protocol`,
which appended a durable `confirmatory_protocol` record, *before* the
fixture-hash check, so a rejected fixture expansion still wrote to the
append-only log; the existing test used a fresh workspace and could not see it.
And `access_count: 1`, `adaptations_after_access: 0` and
`exploratory_result_access_during_execution: False` were literals in a dict
rather than reads of durable state, so a second, different protocol could target
the same held-out case an unbounded number of times under a one-pass banner --
`freeze_protocol` consulted no prior record.

Finally, `confirm()` held the entire Phase 5 fixture in the execution scope and
selected the frozen case from it by list comprehension. The Section 20 scenario L
boundary was a convention, not a mechanism.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (external held-out control corpus, expert-reviewed) | Section 18.4's intent; Section 17.5 tier 8 | The only thing that would actually measure generality | Requires a corpus the project did not author and out-of-repo expert labour; unavailable offline; not in WP5 scope | Owner-commissioned corpus; recorded external reviewer |
| Wrap (execute project-authored controls, each with a mandatory falsifiability probe, and bind the suite into `protocol_hash`) | Phase 1 policy primitives already exist for every category; `tests/test_phase1_adversarial.py` proved each transform reachable | Every control executes; the forbidden outcome of each is demonstrated by construction; a control that cannot fail is itself a failure; no new dependency, no network | The corpus is authored by the party that must pass it, so it measures boundary enforcement on known traps and nothing more | Positive control required; `probes_flipped == controls_total`; suite hash inside `protocol_hash` |
| Interoperate (keep the five declarations, add tests asserting the same strings) | The current state | Cheapest | Replaces one unfalsifiable table with another and leaves the tautology in the release package | -- |
| Build/defer (leave Section 18.4 deferred) | -- | -- | ADR-0024 already claims execution in a shipped release package, so deferring means a standing false claim | -- |

## Decision

Adopt the wrap option.

`src/math_research/phase6/generality.py` executes thirteen controls over a
content-hashed, project-authored suite manifest at
`fixtures/phase6/generality/generality-controls-v1.json`. Each control names an
engine, a parameter set, an expected observation set, and one probe. Each engine
drives real code: Phase 1 `TrustPolicy` (`target_resolution`, `project_claim`,
`can_discharge_obligation`), the exact Phase 5 diagonal engine (`run_case`), or
the new Phase 6 `HeldOutView`. Verdicts are computed observations compared
against the frozen expectation; nothing is declared.

| ID | Category | 18.4 / Section 20 | Executed verdict |
|---|---|---|---|
| GC-01 | known theorems (**positive**) | 18.4; 17.5 tier 1 | `target_resolution()` reaches `proved`, `approved_equivalent`, `blockers == []` |
| GC-02A | false conjectures | 18.4; 17.5 tier 2; §20 C | an `EXACT_COUNTEREXAMPLE` warrant reaches `disproved` |
| GC-02B | false conjectures | 18.4; 17.5 tier 5 | the exact engine reports a nonoptimal fixed point with gap `1/3`, not convergence |
| GC-03 | missing-assumption traps | 18.4; 17.5 tier 3 | a named `assumption_delta` leaves the target `unknown` with `semantic_target_not_resolved` **while** `project_claim(target)` stays `proved` |
| GC-04 | semantic mistranslations | 18.4; 17.5 tier 6; §20 H | a formal artifact bound to the weakened statement leaves the target `unknown` |
| GC-05 | inapplicable citations | 18.4; 17.5 tier 7; §20 I | `(False, "source_hypotheses_incompatible")` with the obligation still `open` |
| GC-06A | cross-representation | 18.4; 17.5 tier 4; §20 D | an unverified map blocks with `representation_map_not_verified` |
| GC-06B | cross-representation | 18.4; §20 D | an open bridge blocks with `representation_bridge_open` |
| GC-07 | unsupported consensus | §20 A | `MODEL_AGREEMENT` reaches `supported`, never `proved` |
| GC-08A | experimental overreach | §20 B | `EXPERIMENTAL_OBSERVATION` on an `unrestricted_universal` claim reaches `supported` |
| GC-08B | premise smuggling | §20 J | `(False, "helper_restates_target")` with the obligation still `open` |
| GC-09A | plugin core contract (**positive**) | 18.4 final sentence; 18.2 | a second-domain dossier reaches `proved` through the same nine projection axes with zero entity types outside `ALL_ENTITY_TYPES` |
| GC-09B | evaluation leakage | §20 L | `HeldOutView` refuses a non-frozen case, records the violation, and exposes only the frozen id |

Seven boundaries are part of this decision.

**Every control carries a falsifiability probe, and the probe gate is a release
gate.** A probe is a *single named field* of the control's own parameters set to a
different value. `validate_suite` refuses a probe that mutates a field the
control does not own, or that does not change the value. A probe *flips* only if
its own stated expectation holds **and** the control's expectation is broken
under the mutation. `run_suite` reports `probes_flipped`, and
`probes_flipped == probes_total` gates the release alongside
`controls_passed == controls_total`. A control that cannot be made to fail is a
suite failure. This is what structurally forecloses the defect being fixed,
rather than replacing one unfalsifiable table with another.

**At least one control is positive, and `validate_suite` refuses a suite without
one.** GC-01 asserts that a known-valid theorem dossier actually reaches
`proved`. `positive_control_admitted` is reported separately and gates the
release. An all-negative suite is scored full marks by a system that rejects
everything, which is the failure mode ADR-0024 shipped.

**The suite definition is inside `protocol_hash`.** `PROTOCOL_FIELDS` gains
`generality_suite_id` and `generality_suite_hash`, and `_validate_protocol`
rejects a loaded suite whose id or `canonical_hash` differs from the frozen
protocol *before the first `workspace.append`*. Editing the suite after a bad run
now requires editing the frozen protocol, which changes `protocol_hash`, the
confirmatory `run_id` and the release hash, and is visible in the diff.

**Validation ordering is the enforcement.** Every precondition -- protocol shape,
immutable pins, freeze-precedes-execution, single held-out case, capability
allowlist, suite identity, fixture hash, fixture shape, benchmark identity,
Phase 5 run, material-result trace, held-out case resolution, and prior-access
conflict -- now sits in `_validate_protocol` and the pre-append block of
`confirm()`, above the first `append`. A rejected expansion leaves
`workspace.records() == ()`. Any future check goes above the first append or it
is not enforcement.

**Held-out access is a durable ledger, not a literal.** A `heldout_access` record
is appended before the case is read, keyed
`stable_id("access.phase6", {benchmark_id, case_id})` and deliberately *not*
keyed on the protocol, so a second different protocol targeting the same case
collides. `access_count` is `len()` of the matching durable records and
`adaptations_after_access` counts `confirmatory_protocol` records whose
`frozen_at` post-dates the earliest access. Both are computed reads. A conflicting
second protocol is refused with `Phase6ValidationError` before it can append
anything.

**The held-out fixture no longer enters the execution scope.** `HeldOutView`
drops every non-frozen case at construction, and `resolve_heldout_case` appends a
durable `heldout_access_violation` record before re-raising a refusal. Section 20
scenario L is now a mechanism with a record, not a convention.

**No sealed boundary is touched.** `domain/entities.py` and
`domain/policies.py` are unchanged: the controls *construct* entities and read
policy projections. No Lean runs, so the sealed Phase 3B runtime and the
ADR-0016 v5 image are untouched and `make check` stays offline. GC-05 is
implemented against the Phase 1 `SourceApplicabilityRecord`, not Phase 4A
`ApplicabilityReview`, so it does not become a third resolver standing in for
Phase 4A alongside `synthesis/applicability.py`. Phase 3A memory, deletable
content (ADR-0021) and protected evidence manifests (ADR-0022) are untouched.
`record_type` is free-form `TEXT`, so the two new record types need no migration
and `phase6_records` is not `ALTER`ed. This slice therefore stays inside the
ADR-0026 lightweight per-slice process.

Novelty and significance are untouched and remain exactly `not_assessed` with
`inferred_from_warrant: False`. The suite writes to neither record, and no
control produces an `EpistemicWarrant`, a semantic-alignment approval, a source
applicability assertion, or a graph admission.

## Consequences

**The honest risk in this slice is that the corpus is authored by the party that
must pass it.** Every fixture is project-authored, recorded as
`control_corpus_provenance: "project_authored"` in the suite manifest, the durable
`generality_control_suite` record, the release package and the rendered report.
The suite demonstrates **boundary enforcement on known traps**. It is not
evidence of generality against unseen traps, and nothing in this slice moves
toward that. Section 18.4's suite is only evidence of generality if the fixtures
were not written by the system's authors, and these were. A reviewer should read
that sentence as the ceiling on this slice, not as boilerplate.

Four things bound the risk and none removes it: every control drives real policy
code rather than a fixture-shaped mock; every control's forbidden outcome is
reachable by a one-field mutation, so no control is a constant; the suite hash is
frozen in the protocol before execution; and the positive controls prevent the
degenerate all-reject pass. The failure mode that remains is a trap category
nobody thought to author.

`baseline_comparison` now reports `phase6_passed` as the count of *negative*
controls passed (eleven), not all thirteen, because the arithmetic-only baseline
enforces zero trust boundaries and a positive control is not a boundary
rejection. It carries `is_generality_measure: false` and an explicit
`interpretation` string. **Eleven versus zero is a count of enforced boundaries on
project-authored traps. It is not a generality rate and must not be read as one.**
No metric of the form "catches X per cent of unseen traps" is computable from
repository data.

Record count, record order and the release payload all changed, so
`confirmatory_run_id`, `confirmatory_result_id` and `release_hash` all changed.
No test or document hard-coded them. `confirmatory-result` and
`phase6-release-package` are bumped to `v2` because
`generality_controls` changed from a list of five declarations to one suite-result
object, and consumers must fail rather than silently mis-read it.

The acceptance suite is the sole executable record of these thresholds under
ADR-0026, so `tests/test_phase6_generality_controls.py` asserts the properties
and not the happy path: that a probe which cannot flip fails the suite *and*
fails the release, that a suite without a positive control is refused, that a
suite omitting an 18.4 category is refused, that nineteen manifest mutations all
fail closed, that five distinct rejected expansions each write zero records, that
a second protocol on the same held-out case is refused, that the suite result is
byte-identical across calls and across a fresh process, and that neither new
module imports the clock, randomness, the environment, `benchmarks.*`, the sealed
Phase 3B runtime, or Phase 4A.

## Measured outcome

Implemented and measured on 21 August 2026. Thirteen of thirteen controls
execute and pass; thirteen of thirteen probes flip.

| Measure | ADR-0024 | ADR-0034 |
|---|---|---|
| Controls that execute anything | 0 of 5 | 13 of 13 |
| Positive controls | 0 | 2 (GC-01, GC-09A) |
| Section 18.4 categories covered | 3 of 6 | 6 of 6 |
| Controls with a demonstrated forbidden outcome | 0 | 13 |
| Suite definition inside `protocol_hash` | no | yes |
| `access_count` source | literal `1` | `len()` of durable `heldout_access` records |
| `adaptations_after_access` source | literal `0` | count of protocols frozen after the earliest access |
| Records a rejected fixture expansion writes | 1 (`confirmatory_protocol`) | 0 |
| External spend, model calls, network calls | 0 | 0 |
| New dependencies | 0 | 0 |

Two findings are recorded rather than fixed.

**`domain/policies.py` lines 127--131 are unreachable.** The scope demotion reads
`if claim.scope is UNRESTRICTED_UNIVERSAL and logical_status == "proved": if not
any(item.kind in {FORMAL_PROOF, RIGOROUS_DERIVATION} for item in active):
logical_status = "supported"`. `logical_status` can only be `"proved"` via the
preceding `elif`, which already established that some active warrant is a
`FORMAL_PROOF` or `RIGOROUS_DERIVATION` over the same `active` list, so the inner
condition is always false. Section 20 scenario B is in fact enforced by the
warrant-kind branch: `EXPERIMENTAL_OBSERVATION` never reaches `"proved"` in the
first place. GC-08A therefore measures the reachable enforcement and says so in
its own `limitations`. Deleting the dead branch would edit Phase 1 trust
semantics and returns the slice to the full gate package, so it was not done.

**A confirmatory re-run at a different `recorded_at` still raises `ValueError`
from `Phase6Workspace.append`, not `Phase6ValidationError`.** `recorded_at` is
part of a record's canonical bytes but not of its `record_id`, so the byte-equality
guard fires. That behaviour predates this slice and is unchanged; the new
prior-access check gives the *meaningful* case -- a different protocol or method on
the same held-out case -- a typed, fail-closed error instead.

The suite deviates from the WP5 plan's nine-control scheme in one respect, for a
stated reason: a control has exactly one engine invocation and one probe, so the
plan's GC-02, GC-06 and GC-08, each of which named two independent legs, are
split into GC-02A/GC-02B, GC-06A/GC-06B and GC-08A/GC-08B. Merging the legs would
have required either a multi-assertion control -- whose probe could then flip one
leg while the other stayed constant -- or a mode-selector parameter that is not a
real field of any fixture. Thirteen single-assertion controls with thirteen
single-field probes is the stricter arrangement.

GC-09B's polarity is also inverted relative to the plan: the control asserts the
refusal *and* the recorded violation, and the probe requests the frozen case to
show the boundary is not simply refusing everything. A probe must break the
control's expectation, and for a negative control that means demonstrating the
permissive answer is reachable.

## Explicit deferrals

- **A genuinely held-out control corpus.** The single most important limitation
  here. Requires fixtures authored by a party other than the one that must pass
  them, and external expert review, which is out-of-repo labour.
- **A real formal kernel for GC-04.** Section 20 scenario H properly executed
  means Lean accepting a proof of a weakened translation, which needs the sealed
  Phase 3B runtime and the ADR-0016 v5 image that `make check` deliberately
  excludes. The offline substitute is a recorded `FORMAL_ARTIFACT` whose
  `VerificationRecord.target_statement_hash` is bound to the statement it
  actually covers.
- **A real inapplicable citation for GC-05.** `arXiv:quant-ph/0201109` is
  metadata-only with no licensed local content, so the imported statement, its
  hypotheses and the source span are synthetic.
- **A real known-theorem corpus for GC-01.** One hand-built dossier. At any
  meaningful scale this means mathlib or a literature corpus.
- **A real second domain plugin for GC-09A.** The contract is tested with a
  minimal graph-theory fixture. Building a second domain is beyond WP5.
- **A measured generality rate.** Not computable from repository data. See the
  `baseline_comparison` note above.
- **Deleting the unreachable scope demotion in `domain/policies.py`.** Phase 1
  trust semantics; returns to the full gate package.
- **Section 18.3's orchestration comparison, Section 20 M false novelty, and
  external expert review.** Model calls, ADR-0029 activation evidence, expanded
  novelty search, and out-of-repo labour respectively. Novelty and significance
  stay `not_assessed`; AGENTS.md forbids automated assessment.

## Validation and revisit trigger

The decision stays valid while the complete offline check remains green, every
control executes against real policy or engine code, every probe flips, at least
one positive control passes, the suite hash stays inside `protocol_hash` and is
verified before the first append, the held-out counters stay computed reads of
durable records, `control_corpus_provenance` stays `project_authored` while the
fixtures are project-authored, novelty and significance stay `not_assessed`, and
the slice reaches no network, no model, and no new dependency.

Reconsider if a control is found whose probe cannot be made to flip by any
single-field mutation, if a control has to be keyed on `graph_admitted` (a
constant `False`), if a suite edit is needed to make a run pass, if a new record
type needs an `ALTER` on `phase6_records`, if a control requires the sealed
Phase 3B runtime or a Phase 4A rights read, or if any consumer starts reading
`baseline_comparison` as a generality measure.
