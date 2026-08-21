# ADR-0042: Review verdicts and warrant granting as an append-only decision journal

- **Status:** accepted for the bounded human-review slice; implemented
  21 August 2026 with all gates measured -- see "Measured outcome"
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 4.5 epistemic warrant, Section 4.15
  semantic alignment approval, Section 4.20 proof obligations, Section 5 trust
  model (models never award warrants), Section 12 semantic/operational hash
  split, Section 21.2 inward dependency direction
- **Decision owners:** repository owner

## Context

Before this slice nothing in the system could grant an `EpistemicWarrant` from a
real run. That is a measurement, not an impression: `grep -rn
"EpistemicWarrant(" src/` returned exactly two construction sites, both
fixtures --- `application/manual_slice.py` (the hardcoded even-integers dossier)
and `phase6/generality.py` (control fixtures). Neither is reachable from a
problem an operator supplies.

The consequence was a dead end at the exact point where the trust model says a
human must act. ADR-0039 intake opens two OPEN obligations
(`obligation.<slug>.target_unwarranted`, `obligation.<slug>.alignment_unapproved`)
and forces `AlignmentStatus.PROPOSED`, because approving a target interpretation
and warranting a claim are researcher acts. No command could perform either act.
Measured end to end on `fixtures/review/sum-of-two-odds-is-even-v1.json`: Phase 2
drives the intake dossier to `awaiting_review` with two `proposal` records, the
verifier finding recommends `manual_review`, and `TrustPolicy.target_resolution`
reports `unknown` with three blockers --- forever. `math_research.cli phase2
review` prints the proposals; it records no verdict.

Four measurements bound the design.

**A warrant is not one record.** `TrustPolicy._warrant_is_accepted` requires an
ACTIVE warrant with at least one `Evidence` in `Disposition.ACCEPTED` whose
`claim_id` matches, and at least one `VerificationRecord` that is ACCEPTED, PASS,
`independent_from_proposer`, and whose `target_statement_hash` equals
`content_hash(claim.statement)`. So "grant a warrant" necessarily means "record
that a named human accepted specific evidence and performed or attested a
specific verification". A command that wrote only an `EpistemicWarrant` would
produce a warrant `TrustPolicy` ignores, which is worse than no command at all.

**Phase 3B findings always report every trust flag false.**
`phase3b/interchange.py:validate_finding_dict` rejects any finding where
`epistemic_warrant_created`, `semantic_alignment_approved`,
`source_applicability_approved`, `novelty_approved`, `significance_approved`, or
`contribution_approved` is not `False`. Reading those flags as "conditions that
must be true before granting" would make the kernel path unreachable. Reading
them for what they SAY --- the kernel created no warrant, approved no meaning
link, and approved no source applicability --- makes them real gates: the kernel
supplies the derivation, and a named human must still supply the meaning
approval. That is the reading adopted here.

**A dossier is an immutable content-hashed value.** `interchange.py` binds
`content_hash` over the whole dossier and `import_trusted_replay` refuses a
payload whose hash does not match. There is no in-place edit. Recording a
decision therefore cannot touch a dossier; a successor dossier must be derived.

**The verifier's own recommendation is the thing most likely to be mistaken for
a verdict.** `baseline_loop.py` sets `RunStatus.AWAITING_REVIEW` exactly when
`output["recommendation"] == "manual_review"`, and the scripted fake finding
declares `"outcome": "supports"` with detail "Each displayed algebraic step
follows from the accepted definition". A convenience feature that promoted that
to a verdict would be a trust hole shaped like a time saver.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (extend `phase2 review` to write a verdict into the Phase 2 workspace) | The command already reads the proposals | One place to look; no new store | Phase 2 is the sealed evidence boundary and its records are `disposition = 'proposal'` by CHECK constraint; a verdict is not a proposal. Would also mean editing `phase2/*`, which this slice may not do | Owner ruling that Phase 2 may hold trust decisions |
| Adopt (let `import_trusted_replay` accept an externally edited dossier carrying warrants) | The schema already has warrant fields | Zero new code | ADR-0039 measured this exact hole: a hand-edited dossier with a recomputed hash projects as `proved` with three warrants. This is the attack, not the feature | None available |
| **Wrap (new append-only decision journal plus a projection to a successor dossier)** | Phase 3B, Phase 6, and the synthesis slice all layer append-only records on the same SQLite file; `EventStore.append_once` already defines the idempotency semantics | Records the human act as its own immutable fact; keeps Phase 1 entities and Phase 2 evidence untouched; refusals are first-class and retained; the successor chain is auditable in both directions | A second store to keep aligned; discharged obligations and decided alignments reuse an entity ID with changed content (see Consequences) | Content-derived IDs; explicit instants; semantic/operational hash split; every refusal names one unmet precondition; forbidden outcome demonstrated impossible |
| Interoperate (hand-write a successor dossier per review) | Status quo plus a text editor | No new code | No record of who decided what or why; no precondition checking; indistinguishable from the attack above | -- |
| Build/defer (no review surface) | -- | -- | Every real problem stays permanently `awaiting_review`; the trust model's central act is unimplementable | -- |

## Decision

Adopt the wrap option.

Add `src/math_research/review/` (`records.py`, `serialization.py`, `ports.py`,
`journal.py`, `decisions.py`, `projection.py`),
`src/math_research/review_cli.py` with `main(argv) -> int`, and
`migrations/review/0001_review_decision_journal.sql`. The journal layers on the
Phase 2 `SQLiteWorkspace` so one file carries the Phase 2 durable tables and the
review decisions. `domain/entities.py`, `domain/policies.py`, `phase2/*`, and
`phase3b/*` are unchanged; this slice reads them only.

Eight boundaries are part of this decision.

**A warrant traces to a named human or to a kernel plus a named human.** There
are exactly two bases. `human_review` requires a recorded `review_verdict` whose
verdict is `accept_candidate` AND whose `independently_checked` flag is `true`.
`formal_kernel` requires a Phase 3B finding whose outcome is `kernel_checked` or
`kernel_checked_approved_standard_axioms`. Both additionally require a recorded
human approval of the dossier's `SemanticAlignmentRecord`, so every warrant this
surface grants names at least one human being. A verifier `recommendation` is
copied into the decision payload as an input and is never read as a verdict:
neither `decisions.py` nor `projection.py` contains any comparison against
`manual_review`, and the acceptance suite asserts that by parsing their AST.

**The basis fixes the warrant kind, and there is no fallback.** Human review can
license `rigorous_derivation`, `exact_counterexample`, or
`experimental_observation`. A kernel attestation licenses `formal_proof` and
nothing else. `formal_proof` under the human-review basis is refused with
`formal_proof_requires_kernel_attestation`; `source_report` is refused with
`source_report_requires_source_applicability_record` because it needs a checked
`SourceApplicabilityRecord` that ADR-0039 defers; `model_agreement` is refused
with `warrant_kind_not_reviewable` because this slice measures no agreement. A
refused kind never degrades into a weaker one, and the acceptance suite measures
that a refused `formal_proof` leaves the successor with zero warrants and status
`unknown`.

**Only a human may record a decision.** `ReviewerKind` has three members and
only `HUMAN` is ever stored (enforced by a SQL CHECK). `MODEL` and
`AUTOMATED_TOOL` exist precisely so that a decision claiming a non-human
reviewer is the named refusal `reviewer_identity_not_human` rather than an
unrepresentable state. A reviewer whose identity equals a recorded proposal
`source_id` on the run is refused with `reviewer_is_proposal_source`.

**Refusals are first-class and retained.** Every refusal carries a `code`, the
`subject_id`, the `unmet_precondition` it failed, and a `detail`. The CLI prints
them as structured JSON, exits 2, and appends them to an append-only
`review_refusals` table. A dead end is a result, not a discarded attempt.

**Nothing is mutated; a successor dossier is derived.** `review project` reads
the journal and the run's committed dossier and builds a new `ResearchDossier`
with a new content hash. Derived `Evidence`, `VerificationRecord`, and
`EpistemicWarrant` records carry content-derived IDs; the discharged
`ProofObligation` and the decided `SemanticAlignmentRecord` carry over their
prior IDs with changed content, and the projection attaches a
`review_journal_projected` `AuditEvent` naming the reviewers, the projecting
human, and the prior dossier hash. The prior dossier's bytes and hash are
unchanged, which the acceptance suite measures by reloading it from the Phase 2
workspace after projection. The projecting principal must be one of the
reviewers who took a recorded decision, so a successor is never attributed to a
bystander.

**Append-only with derived idempotency keys.** A decision's identity is
`stable_id` over its semantic content, following
`phase3b/serialization.py:stable_id`. Replaying an identical decision returns
the stored record and reports `appended: false`. Reusing a key for different
content is the refusal `idempotency_key_conflict`, so a reviewer cannot rewrite
their own verdict. Keys are derived, not supplied: a revised verdict is out of
scope for the same reason ADR-0039 defers problem revision.

**Semantic identity excludes observations.** A decision's `content_hash` covers
everything except `recorded_at`, `sequence`, and a `payload.operational` block;
the `operational_hash` covers all of it. The kernel path puts the finding's
`created_at` and `elapsed_milliseconds` in that block and stores the finding's
Phase 3B semantic projection as the evidence content, so re-running the same
check at a different instant produces the same decision ID, the same journal
semantic hash, and the same successor dossier hash. This follows the Phase 3B
precedent rather than inventing a second convention.

**Time is an explicit argument.** Every command takes its instant positionally.
`random`, `secrets`, `time`, and any `now`/`utcnow`/`today`/`monotonic`
attribute are absent from all six modules, and the acceptance suite asserts
their absence by parsing the module source. No float literal appears in any of
them, also asserted.

## Consequences

The honest risk in this slice is that it makes a `proved` projection reachable,
and the thing standing between a model's prose and that projection is a human
being's attestation. `independently_checked` is a claim by the reviewer, not a
measurement of the reviewer. Nothing here can tell a careful re-derivation from a
tired click. The design response is to make the attestation explicit, named,
immutable, and quoted inside the evidence content itself --- the projected
evidence text contains `reviewer:`, `independently_checked:`, and
`verifier_recommendation (input, not a verdict):` --- so a later reader can see
exactly whose judgement the status rests on. It cannot make that judgement
correct.

The same caveat has a sharper form on the kernel path. The Lean kernel checks a
formal target; `TrustPolicy` requires the verification record's
`target_statement_hash` to be the hash of the CLAIM's statement. Writing that
hash asserts an identification between the formal target and the informal claim.
That identification rests entirely on the human alignment approval, and the
projected verification record says so in its own notes, alongside the finding's
`wrapper_manifest.target_hash`. A wrong alignment approval yields a formally
impeccable warrant for the wrong statement. This is ADR-0005's
`formally_provable_mistranslation` trap, and this slice does not close it --- it
localizes it to one named, dated, immutable human decision.

Two entity IDs are carried over with changed content: a discharged
`ProofObligation` and a decided `SemanticAlignmentRecord`. `TrustPolicy` resolves
blockers and alignment by identity, so renaming them would read as an unrelated
open obligation and an unapproved alignment. The append-only guarantee therefore
lives at the dossier level: the prior dossier still holds the OPEN and PROPOSED
versions, the journal holds the decision that moved them, and the successor
carries an `AuditEvent` recording the prior status. A direct consequence is that
appending BOTH the prior and the successor dossier to one
`InMemoryTrustStore` raises, because `AppendOnlyRepository.append` refuses an ID
whose immutable content changed. That is the correct behaviour for that store and
a real constraint on any future multi-generation index.

A third cost: this is a second store over the same SQLite file. Table names are
prefixed `review_`, the Phase 2 migrations run first, and no review module
executes SQL outside `journal.py` (asserted by the acceptance suite), but the
two schemas must still be kept aligned by hand.

A fourth: refusals are retained in the journal and deliberately do NOT enter the
successor dossier. Which refusals a reviewer hit depends on the order they tried
things, so admitting them would make the successor hash depend on operator
fumbling. The journal export is the record of attempts; the dossier is the record
of decisions.

What this surface deliberately does **not** do:

- it does not assess novelty, significance, or contribution, and cannot set
  those fields;
- it does not create a `SourceApplicabilityRecord` or a `RepresentationMap`, so
  `source_report` warrants and `literature_applicability` obligations are
  refusals rather than features;
- it does not require or measure independent replication: one human reviewer
  suffices, and a second reviewer's contrary verdict is recorded but does not
  block a grant made by the first;
- it does not verify anything itself --- it records who verified what;
- it does not run Lean; the kernel path consumes a finding produced elsewhere
  and never executes a check;
- it does not accept a dossier file on any command, for the reason ADR-0039
  gives: the dossier grammar can express a warrant and a review decision cannot;
- it does not read a clock, a network, a model, or a source document;
- it does not modify Phase 1 trust semantics, sealed Phase 2 evidence, the
  sealed Phase 3B runtime, or the Phase 4A rights boundary.

## Measured outcome

Implemented and measured on 21 August 2026. `make check` is green: 1459 tests,
16 skipped for the disposable `jsonschema` gate environment, plus every phase
acceptance target. This slice contributes 81 tests in one module.

The end-to-end command sequence, measured:

```
math_research.phase2_cli start WS run.review.odds.v1 \
  --problem fixtures/review/sum-of-two-odds-is-even-v1.json \
  --intake-instant 2026-08-21T00:00:00Z --execute        # -> awaiting_review
math_research.review_cli record-verdict WS run.review.odds.v1 2026-08-21T12:00:00Z \
  --reviewer reviewer.alice --reviewer-kind human --attestation ... \
  --verdict accept_candidate --independently-checked --rationale ...
math_research.review_cli decide-alignment WS run.review.odds.v1 \
  alignment.sum-of-two-odds-is-even.v1 2026-08-21T12:05:00Z ... --decision approve
math_research.review_cli grant-warrant WS run.review.odds.v1 \
  claim.sum-of-two-odds-is-even.odd_plus_odd_is_even 2026-08-21T12:10:00Z ... \
  --kind rigorous_derivation --scope "all pairs of odd integers"
math_research.review_cli discharge-obligation WS ... obligation.<slug>.target_unwarranted ...
math_research.review_cli discharge-obligation WS ... obligation.<slug>.alignment_unapproved ...
math_research.review_cli project WS run.review.odds.v1 2026-08-21T13:00:00Z OUT \
  --projected-by reviewer.alice
math_research.review_cli inspect OUT
```

| Property | Gate | Measured |
|---|---|---|
| Intake starting point | `unknown`, zero warrants, two OPEN obligations | `unknown`, `()`, two OPEN |
| Happy path outcome | `proved` with one ACTIVE warrant whose refs resolve | `proved`, `approved_equivalent`, `("rigorous_derivation",)`, zero blockers, `validate_dossier_payload` empty |
| Kernel path outcome | `proved` with `formal_proof` | `proved`, `("formal_proof",)`, verifier kind `lean_kernel_phase3b` |
| Prior dossier after projection | bytes unchanged | identical bytes, still PROPOSED alignment, still OPEN obligations |
| Successor round-trip | byte-identical through `import_trusted_replay` / `export_dossier_dict` | identical value, identical bytes, identical hash |
| Projection determinism | two independent journals, same decisions and instants | identical successor ID and identical bytes |
| Idempotent replay | second identical decision appends nothing | `appended: false`, one row, original `recorded_at` retained |
| Key reuse for different content | refusal | `idempotency_key_conflict`; the first verdict stands |
| Journal semantic hash | independent of recorded instants | equal semantic hash, different operational hash across a 7-month instant shift |
| Refusing Phase 3B outcomes | all seven refuse, each naming its own outcome | `kernel_checked_unapproved_assumptions`, `policy_rejection`, `elaboration_failure`, `meaning_test_failure`, `timeout`, `output_limit`, `sandbox_failure` |
| Self-promoting finding | refusal by name | `finding_claims_self_granted_warrant`; the five other flags give `finding_claims_unapproved_promotion` |
| Model reviewer | refusal | `reviewer_identity_not_human`; nothing appended |
| Accept without an attested independent check | refusal quoting the recommendation | `independent_check_not_attested`, detail contains `manual_review` |
| `formal_proof` by human review | refusal, no weaker fallback | `formal_proof_requires_kernel_attestation`; successor has zero warrants and status `unknown` |
| Finding instant shift | same decision identity | identical `decision_id` and `content_hash`; `created_at` retained under `payload.operational` |
| Clock, randomness, float | absent from all six modules | asserted by AST |
| SQL outside the journal | none | asserted by source scan |
| External cost | zero | no network, model, or third-party import on any tested path |

The forbidden outcome --- a warrant derivable from a model's own say-so --- is
demonstrated impossible three independent ways. **By construction:** neither
`decisions.py` nor `projection.py` contains any comparison against
`manual_review` or the finding outcome literal `supports`, asserted by parsing
their AST, so no branch can read a recommendation as a verdict. **By gate:** the
run's verifier finding declares `"recommendation": "manual_review"` and
`"outcome": "supports"`, and the measured projection of the stored dossier stays
`unknown`; accepting requires an explicit `--independently-checked` attestation
from a `human` reviewer who is not a recorded proposal source; and the kernel
path refuses any finding that sets `epistemic_warrant_created`. **By
measurement:** a recorded verdict with no alignment approval, an inconclusive
verdict, a disputed alignment, and a refused `formal_proof` each leave the
successor dossier at `unknown` with zero warrants.

## Blueprint deviation

None in trust semantics. One recorded structural deviation: the discharged
`ProofObligation` and the decided `SemanticAlignmentRecord` in the successor
dossier reuse their prior entity IDs with changed content, so append-only is
guaranteed at the dossier and journal level rather than at the entity level.
Necessity: `TrustPolicy` resolves blockers and alignment by identity, so a
renamed record reads as an unrelated open obligation and an unapproved
alignment. Revisit trigger: any consumer that indexes multiple dossier
generations in one `AppendOnlyRepository`.

## Explicit deferrals

- **Wiring into `math_research.cli` and a `make check` acceptance target.** Left
  to the integrator by instruction; `review_cli.main(argv)` is the entry point.
  Until it is wired, this slice's guarantees are covered by
  `tests/test_review_warrant_granting.py` only, and the absence of a Makefile
  target must not be counted as a pass.
- **Required independent replication.** Two-reviewer quorum, reviewer
  disqualification rules beyond the proposal-source check, and any measurement
  of reviewer reliability.
- **Verdict revision.** A reviewer's verdict on a run is immutable. Superseding
  one needs a lifecycle slice, exactly as ADR-0039 defers problem revision.
- **Withdrawing a granted warrant.** `RecordStatus.WITHDRAWN` exists on
  `EpistemicWarrant` and no command sets it.
- **`source_report` warrants and `literature_applicability` discharge.** Both
  need a checked `SourceApplicabilityRecord` from the Phase 4A/4B path.
- **Warrants for non-target claims on the kernel path.** The kernel path checks
  the finding against the dossier's formalization target only.
- **Novelty, significance, and contribution.** Untouched, by standing policy.
- **A JSON Schema for the journal export.** The loader is the enforcing
  artifact, as in ADR-0039; adding the schema to `make check-gate` is a
  follow-up.

## Validation and revisit trigger

The decision stays valid while `make check` is green, the review modules import
no third-party or network module, `domain/`, `phase2/`, and `phase3b/` remain
unmodified by this slice, no review module reads a clock or uses a float, only
`journal.py` executes SQL, every refusal names exactly one unmet precondition,
and every warrant in a projected successor traces to a recorded human decision.

Reconsider if a warrant ever needs to be grantable without a named human; if a
third basis appears; if the Phase 3B proposal-only flags change meaning; if a
consumer needs a mutable dossier; if the `payload.operational` block is ever
found inside a semantic content hash; or if anyone treats
`independently_checked` as a measurement rather than an attestation.
