# ADR-0058: Contested definitional readings become records; the headline is derived from them

- **Status:** accepted for the bounded semantic-gate slice; implemented by the
  change this ADR records, with the falsifiability probes below as the release
  condition
- **Date:** 2026-08-22
- **Blueprint requirement:** C15; Sections 5.1 and 5.2 trust axes and forbidden
  transitions, Section 18.4 semantic-mistranslation controls, Section 20
  scenario H (formally proved wrong target); ADR-0036 derived typesetting and
  ledger closure; ADR-0055 novelty checkpoints; ADR-0059 prior-art engagement;
  ADR-0060 source reading provenance; `NOVELTY_LANDSCAPE.md` section 1
- **Decision owners:** repository owner and researcher

## Context

AdaIvy shipped `output/pdf/graffiti-322-counterexample/`. Its body is careful:
`blk.scope.literature` says in as many words that "the correct current label is
candidate refutation; novelty and significance are not assessed", and the claim
prose says the graph refutes Graffiti 322 "under the frozen source-faithful
conventions". Its title says `An Exact Counterexample to Graffiti 322` and its
abstract opens "We give an exact counterexample to the source-faithful
formulation of Graffiti 322". A reader who reads only the reader-facing text
that a document format makes prominent gets the opposite of what the record set
supports.

**The mechanism of the failure is not carelessness, it is a hole in the
projection.** ADR-0036's central boundary is that a rendered block exists only
with a resolving record reference and that a claim's environment is computed,
never declared. That boundary covers the ledger. It does not cover the two
fields that appear before the ledger begins: `title` and `abstract` are free
prose validated only for LaTeX safety. Of the ten falsifiability probes in the
shipped bundle, every one mutates a certificate field, a claim field,
`novelty.status`, `run_disclosure`, a source hash, or a LaTeX statement. Not one
touches the title. This was not an oversight in the probe set — there was
nothing for a probe to check the title *against*. No record in the manuscript
stated what the resolution status of the claim was, so no mutation of any field
could make an over-claiming title become a forbidden verdict.

**The mathematics underneath is genuinely convention-relative, and the
conventions entered the document as free prose.** The result depends on two
contested definitional readings: whether `Even(v)` counts `v` itself, and
whether "range" means the number of distinct distance eigenvalues or the extent
`lambda_max - lambda_min`. Under the reading AdaIvy froze
(`even_includes_v`, `range_distinct_count`) the 448-vertex graph refutes. Under
`range_extent` it does not, because the extent of the distance spectrum of
`G(14,18)` exceeds `40049/4444` by three orders of magnitude. Under
`even_excludes_v` the C4 that Roucairol and Cazenave already published refutes
the conjecture, so the AdaIvy construction is not the first refutation. Three
readings, three different reader-facing conclusions, and the only place any of
this was recorded was one sentence of prose in `blk.statement.source`.

**This class of failure was predicted, prescribed against, and half-built.**
`NOVELTY_LANDSCAPE.md` section 1 — "The main failure is often semantic, not
syntactic" — says that a proof assistant proves the encoded proposition and not
that the proposition faithfully expresses the question, and its design
implication is explicit: *create a first-class `SemanticAlignmentRecord`,
separate from a formal proof record*. That entity exists. It is at
`src/math_research/domain/entities.py:194`, it carries `quantifier_mapping`,
`definition_mapping`, `assumption_delta`, `edge_case_delta`, a
`StrengthRelation`, and an `AlignmentStatus` that includes `DISPUTED`. The
publication schema has never referenced it. Blueprint Section 20 scenario H
("formally proved wrong target") describes this exact situation and Section 5.2
forbids the transition `formal warrant -> semantic alignment approved`, and
still the projection had no field in which a dispute about a definition could be
written down. A prescribed defence that is built but not wired into the path
that produces the reader-facing artifact is worth less than an absent one,
because its existence in the entity graph makes the gap look covered.

The entity also has a second, quieter limitation: it models exactly one
alignment — one formalization compared to one problem, approved or disputed. The
Graffiti 322 situation is not one alignment. It is a *set* of admissible
readings under which the same construction gets different verdicts, and the
honest reader-facing statement is the shape of that set, not a single
approve/dispute bit.

## Options considered

| Option | Evidence | Benefit | Cost/risk | Decision |
|---|---|---|---|---|
| Hedge in prose: require the author to qualify the title and abstract | The shipped body already hedged correctly | Zero new machinery; immediate | The shipped report proves this fails: the body hedged and the headline did not, and nothing could detect the contradiction. Prose is exactly the medium in which the conventions were already lost | Rejected: this is the status quo, and the status quo produced the defect |
| Require human sign-off on every title | A human reads a title in one second | Cheap; catches egregious cases | Puts the last trust boundary downstream of the proposition again, which is the root cause. It also fails on drafts, which carry no approval and are exactly what circulate (ADR-0059) | Rejected: no executable rule, and gated on the boundary already known to be inert |
| Automated novelty or confidence score on the headline | Scores are cheap and repeatable | One number per document | Constructs an unjustified authority, which ADR-0055 already rejected for novelty for the same reason. A score also averages away the thing that matters: *which* reading fails | Rejected, on the ADR-0055 precedent |
| Extend `SemanticAlignmentRecord` and reference it from the manuscript | The entity, `definition_mapping`, and `AlignmentStatus.DISPUTED` all exist | Reuses a prescribed entity; single vocabulary across the graph | It models one alignment with an approval bit, and approval is a human act on the trusted graph. Making it carry a set of admissible readings would overload an approval-bearing entity with an unapproved enumeration, and would put publication on the graph-admission path | Rejected for this slice; the entity stays the alignment-approval record and the coupling is stated rather than merged |
| Content-hashed convention record plus a per-reading verdict matrix, with a derived headline qualifier | ADR-0036 proved that computed classification plus mandatory demotion survives 1,467 promotion attempts; `novelty.py` proved the record shape | The definitional fork becomes a first-class enumerable object; the verdict per reading is a computed cell; the headline is a function of records and no field selects it; a reading change invalidates every claim bound to the old hash | Expressiveness is bounded by the enumeration, and the enumeration is author-supplied. A title becomes longer and uglier | **Selected** |

## Decision

Add `src/math_research/conventions.py` — a record module in the shape of
`novelty.py`: `SCHEMA_VERSION = "adaivy.convention-reading.v1"`,
`POLICY_ID = "convention-relative-claim-v1"`, content-bound records, derived
classification, no free-text path to a reader-facing label. Six boundaries carry
the decision.

**A contested definitional term is an enumeration, not a choice.** A
`ConventionRecord` names the subjects it governs and carries one
`ContestedTerm` per contested term; each term carries at least two `Reading`
entries or it is refused as `term_not_contested`. Each `Reading` names the
passage it is drawn from, how well that passage was read (ADR-0060), and who
reads it that way. The record's reading tuples are the sorted Cartesian product
of its terms' readings, computed rather than listed. The record is
repository-level and content-hashed: one reading set governs every report that
asserts a claim under it, so a report cannot quietly adopt a private convention.

**A resolution-typed claim carries a verdict for every reading tuple, or it
carries none.** A claim with a non-null `resolution_target` is
resolution-typed. It must name a `VerdictMatrix`, and the matrix must cover
exactly the convention record's reading tuples: a partial matrix is refused as
`verdict_matrix_incomplete` rather than read as full coverage. Each
`ReadingVerdict` is `refutes`, `does_not_refute`, or `not_evaluated`, and names
the replay or certificate result hash that backs it. `not_evaluated` is a
first-class value because "we did not check this reading" is the honest answer
in most cases and must be renderable.

**Scope is derived, and the derivation is the load-bearing line of the slice.**
`classify_scope` computes one of four values from the verdicts alone: any
`not_evaluated` gives `contested_unevaluated`; no `refutes` gives
`refuted_under_no_reading`; all `refutes` gives `unconditional`; anything else
gives `convention_relative`. There is no input field that supplies a scope, and
the derivation is ordered so that ignorance demotes before disagreement does. To
remove an ambiguity in the enum name: `refuted_under_no_reading` means *no
enumerated reading yields a refutation* — the conjecture stands under every
reading checked. It is the weakest value, not a resolution.

**Scope demotes the evidence class, and the ladder is extended by insertion.**
`evidence.py` gains `convention_relative_proposition` between
`exact_certificate_proposition` and `proposal`, rendered in the
`adaconditional` environment titled **"Proposition (convention-relative)"** so
that the reader meets the qualification in the environment name rather than in a
footnote. A resolution-typed claim whose derived scope is `convention_relative`
classifies no higher than `convention_relative_proposition`; scope
`contested_unevaluated` or `refuted_under_no_reading` demotes to `proposal`;
scope `unconditional` leaves the ADR-0036 ladder untouched. The order of
`EVIDENCE_CLASSES` is load-bearing, because a demotion probe is checked against
the index; the class is inserted and the existing entries are never reordered.

**The displayed title is composed, and no manuscript field can compose it.**
`title` is replaced by `title_stem`: a noun phrase carrying no resolution verb.
The renderer composes the displayed title from the stem plus a qualifier
computed from the weakest evidence class, the derived scope, the ADR-0059
prior-art classification, and any open obligation tagged `novelty` or
`prior_art`. On the current Graffiti 322 records that composition must produce
**"Candidate Counterexample to Graffiti 322 (convention-relative; prior art not
assessed)"**, and the qualifier can only be lost when the records earn its
loss. The frozen `RESOLUTION_LEXICON` — sixteen entries covering the resolution
verbs, their noun forms, and the fidelity phrase ADR-0060 owns, matched
case-insensitively on word boundaries — is refused in
author-supplied headline text whenever the records do not earn it, under
`title_stem_asserts_resolution` and `abstract_overclaims_evidence`. The
composed headline is a ledger block with resolving references to the verdict
matrix, the prior-art engagement, and the obligations it read, so ADR-0036's
byte-exact closure covers the one string that previously sat outside it.

**The fork is shown to the reader as a table, not summarised.** The renderer
emits a non-optional, derived reading-verdict table: one row per reading tuple
with the reading, the exact `InvEven` value as a rational, the range value, and
the verdict. A document whose result depends on a definitional choice must
display the choice and its alternatives. The companion counter-candidate replay
table is ADR-0059's.

`conventions_cli.py` exposes `inspect` (a convention record, its reading tuples,
and the derived scope of a supplied verdict matrix) and `couplings` (subject ids
coupled through a shared reading), wired into `cli.py` beside `novelty`.

### Named boundaries

- **`unconditional` means unconditional over the enumerated readings.** It is
  not a proof that the enumeration is exhaustive, and no mechanism in this slice
  can be. The enumeration is an author-supplied record. Its mitigations are
  structural rather than logical: the record is repository-level so an omission
  is visible across every report that shares it, `require_convention_binding`
  refuses a matrix whose `convention_hash` the record does not have, so adding a
  reading later invalidates every claim asserted under the old set instead of
  silently widening it, and the reading-verdict table puts the enumeration in
  front of a reader who knows the field.
- **Scope is a truth-conditional axis, not a novelty axis.** `convention_relative`
  says the verdict depends on a reading. It says nothing about whether the
  refutation is new; two readings may both refute while one of them makes a
  published prior candidate sufficient. Priority is ADR-0059's axis, and the
  headline qualifier reads both because a reader conflates them.
- **`coupled_subject_ids` is a statement of consequence, not of status.** The
  Graffiti 322 record must name `problem.graffiti-197`, because Roucairol and
  Cazenave hedge that either 197 or 322 is refuted depending on the meaning of
  "range". Naming the coupling makes a reading change visibly reach the other
  subject; it does not change that subject's recorded status, which stays where
  ADR-0055 left it.
- **`SemanticAlignmentRecord` is untouched and unsuperseded.** A convention
  record is an unapproved enumeration of admissible readings; a semantic
  alignment record is a human approval act on the trusted graph. This slice does
  not wire the entity into publication, does not create or modify an alignment,
  and does not let a `convention_relative` scope stand in for
  `AlignmentStatus.DISPUTED`. Wiring the two together is an explicit deferral
  below.
- **The abstract is screened, not derived.** The title is composed from records;
  the abstract remains author-supplied prose subject only to the lexicon gate and
  ADR-0036's escaping. That asymmetry is deliberate for this slice and is a known
  residual gap.

## What this decision does not license

It creates no mathematical warrant, no novelty status, no significance, no
applicability record, no semantic-alignment approval, and no graph admission.
A verdict matrix is a table of computed evaluations; `refutes` in a cell means
one exact evaluation under one reading returned that value, and nothing more.
`unconditional` scope is not a proof and does not promote a claim above the rung
its certificate and attestation already earn under ADR-0036. A convention record
does not make a reading correct, does not settle a definitional dispute, and
does not authorize speaking for a source author. A demoted headline does not
make a draft an endorsed result; an undemoted headline does not make it one
either. Nothing here changes the meaning of proof, and no model or tool output
may write a convention record, a verdict, or a headline qualifier.

The honest scope of the change: it makes one class of over-claim — a headline
asserting resolution while the records show a contested or unevaluated reading
set — mechanically detectable. It does not make AdaIvy's reports correct.

## Consequences

Titles get longer and less quotable, and that is the intended cost. The
qualifier is the part a press summary would drop, which is why it is derived
rather than authored.

Replacing `title` with `title_stem` is a breaking manuscript schema change. Under
the repository's fail-closed rule an existing manuscript carrying `title` is
rejected on the field set, which is correct and which means the already-shipped
`output/pdf/graffiti-322-counterexample/` record set cannot be revalidated by the
new schema. That bundle is append-only history: it is superseded by a rebuild
under the new schema and is not edited in place. The manuscript
`schema_version` must be bumped in the same change, because two field sets under
one version is the mixed-schema case the repository refuses.

Expressiveness stays bounded by the record schema, and this slice tightens the
bound: a remark that a definitional reading is contested can no longer be made
in prose at all in a resolution-typed report. It has to become a
`ContestedTerm` with at least two readings, each anchored to a passage. That is
more work per report and it is the point.

The `adaconditional` environment is a fourth theorem-like environment in the
frozen ADR-0056 template. It must inherit the classic layout rather than
introduce a second one, and it must be visually distinguishable from
`Proposition`, or the demotion is invisible where it matters.

A shared repository-level convention record couples reports. Correcting a
reading is now an event with a blast radius: every verdict matrix bound to the
old `convention_hash` refuses. That is the intended behaviour and it is also a
standing maintenance cost of the same kind ADR-0036 recorded for passage line
ranges.

## Falsifiability probes

Each rule below is a single named field mutation of a fixture whose forbidden
outcome is a named refusal code or a named demotion.
`probes_flipped == probes_total` remains a release gate, and the ADR-0036
release count and the `make publication` assertions move to whatever the fixture
actually produces — never the reverse.

- `pr.headline-qualifier-required` — blank the qualifier inputs; the forbidden
  outcome is a rendered headline with no qualifier.
- `pr.reading-verdict-flip` — flip one `ReadingVerdict` from `refutes`; the
  forbidden outcome is anything above `convention_relative_proposition`, and a
  flip to `not_evaluated` must reach `proposal`.
- `pr.verdict-matrix-incomplete` — delete one reading tuple's verdict; forbidden
  outcome is any derived scope at all, in place of
  `verdict_matrix_incomplete`.
- `pr.convention-hash-rebound` — mutate `convention_hash` on the matrix;
  forbidden outcome is anything but `convention_hash_mismatch`.
- `pr.title-stem-resolution-refused` — set `title_stem` to a lexicon hit;
  forbidden outcome is a successful render, in place of
  `title_stem_asserts_resolution`.
- `pr.abstract-overclaim-refused` — the same mutation on the abstract, against
  `abstract_overclaims_evidence`.
- `pr.resolution-claim-requires-matrix` — null the `verdict_matrix_id` of a
  resolution-typed claim, against
  `resolution_claim_without_verdict_matrix`.
- `pr.term-not-contested` — reduce a `ContestedTerm` to one reading, against
  `term_not_contested`.

Fixtures must cover all four derived scopes, and the Graffiti 322 fixture is the
real record: two contested terms, four reading tuples, `coupled_subject_ids`
naming `problem.graffiti-197`, and the `Even` reading carrying
`reading_status: "asserted"` because the page-47 text layer is not extractable
(ADR-0060).

## Blueprint deviation

None. Section 5.1 already states that a Lean proof may be `formally_verified`
while semantic alignment is disputed, and Section 5.2 already forbids
`formal warrant -> semantic alignment approved`; this slice supplies the
publication-side representation those clauses assumed and did not have. Section
18.4's `semantic_mistranslations` control category exists in the Phase 6
generality suite, so the repository already tested for this failure class on the
claim path while leaving the projection path uncovered; closing that asymmetry is
not a new axis. `SemanticAlignmentRecord` remains the Section 15 approval entity
and is not superseded.

## Validation and revisit trigger

The decision stays valid while: `classify_scope` has no input path; no
manuscript field can select a headline qualifier or an evidence class; a
resolution-typed claim without a complete verdict matrix cannot render; a
`convention_relative` scope cannot render above
`convention_relative_proposition`; the composed headline appears in the ADR-0036
provenance ledger with resolving record references and survives byte-exact
closure; the frozen lexicon is refused in author-supplied headline text whenever
the records do not earn it; the reading-verdict table cannot be suppressed by any
manuscript input; the Graffiti 322 fixture derives `convention_relative` and
renders the qualified headline; every probe above flips; and rendering remains
offline, standard-library only, deterministic across processes, with novelty and
significance still `not_assessed`.

Reconsider if a legitimate report needs a reading set no enumeration can
express, if a derived qualifier cannot be composed without a manuscript hint, if
the composed headline cannot be brought inside ledger closure, if
`convention_relative` proves to be the scope of nearly every report and
therefore stops carrying information, or if any consumer starts treating a
`refutes` cell as a warrant.

Revisit with a new ADR before: adding a fifth scope value or reordering
`EVIDENCE_CLASSES`; allowing a model or tool to author a convention record, a
verdict, or a headline; deriving the abstract; merging convention records into
`SemanticAlignmentRecord`; or allowing an `unconditional` scope to be read as an
exhaustiveness claim.

## Explicit deferrals

- **Wiring `SemanticAlignmentRecord` into the publication schema.** The entity
  stays the approval record on the trusted graph; the publication path gets the
  unapproved enumeration only.
- **A derived abstract.** Lexicon-screened prose for now.
- **Cross-report convention conflict detection.** Two reports may bind different
  convention records for the same subject; the coupling is visible through
  `couplings` and is not yet refused.
- **Propagating a reading change to the coupled subject's recorded status.**
  `coupled_subject_ids` names the coupling; ADR-0055 still owns the status.
