# ADR-0059: Citing a competing result obliges classification, and its witness is replayed under our own engine

- **Status:** accepted for the bounded semantic-gate slice; implemented by the
  change this ADR records, with the falsifiability probes below as the release
  condition
- **Date:** 2026-08-22
- **Blueprint requirement:** C15; Sections 12.4 acquisition provenance, 15
  publication approval, 16.3 untrusted retrieved content, 20 scenario I (real but
  inapplicable theorem); ADR-0036 bibliography closure; ADR-0055 two novelty
  re-checks; ADR-0056 automatic report production; ADR-0057 campaign provenance;
  ADR-0058 convention records and derived headlines; ADR-0060 reading provenance
- **Decision owners:** repository owner and researcher

## Context

Roucairol and Cazenave, *Refutation of Spectral Graph Theory Conjectures with
Search Algorithms*, is in the shipped Graffiti 322 bundle. It was acquired,
content-hashed (`sha256:fdda6abf…`), rights-cleared for excerpting and
publication, given a bibliography entry, cited from the claim and from
`blk.scope.literature`, and given a passage record whose anchor string reads, in
full, **"Graffiti 322 discussion and C4 candidate"**. Everything ADR-0036's
bibliography closure asks for was supplied. Every field of
`records/prior-art.json` in the same bundle is `not_assessed`:
`outcome`, `relationship`, `resolution`, `verification_status`,
`report_classification`, `target_resolution_status`, `recheck_id`,
`recheck_hash`. AdaIvy located a competing candidate refutation of the same
conjecture, wrote its name into a passage anchor, and shipped no classification
of it. The passage record itself carried no text, so under ADR-0060 even the
anchor's own assertion that the cited pages discuss a C4 candidate was an
unreproduced reading.

**The reason no gate fired is one line.**
`publication/manuscript.py::_validate_announcement_novelty_gate` begins:

```python
approval = manuscript.value["publication_approval"]
if approval is None:
    return
```

`publication_approval` is null for every draft, by ADR-0036's design and by
ADR-0055's own validation clause, which requires that "draft publication remains
possible with no approval and no announcement". The consequence was not
intended and is now measured: **the ADR-0055 two-checkpoint novelty policy has no
effect on any artifact that has not already reached human approval, and drafts
are exactly what circulate.** ADR-0056 then made complete, typeset,
classic-layout PDF production automatic for any solved-result manuscript, so the
most persuasive artifact AdaIvy can emit is precisely the one the novelty gate
does not inspect.

**This is a class, not an incident.** ADR-0055's own Context section records
that Graffiti 197 already failed this way: "AdaIvy found and checked an earlier
refutation of the same result, but the generated report did not classify its own
work accordingly", and that "the broad `novelty: not_assessed` label was true but
insufficient". ADR-0055 fixed the *representation* — derived
`report_classification` and `target_resolution_status` fields, which is why
Graffiti 197 renders as `independent_verification` / `already_refuted` — and
attached the *enforcement* to a boundary that drafts never cross. Graffiti 322
then repeated the original failure with the new fields present and set to
`not_assessed`. A second occurrence after a targeted fix is evidence about where
the enforcement point belongs, not about the diligence of the run.

**The missing comparison was mechanically available.** Roucairol and Cazenave's
candidate is C4. C4 needs no search, no acquisition, and no human insight: its
distance matrix is the circulant with row `(0,1,2,1)`, its distance spectrum is
exactly `{4, 0, -2, -2}` — three distinct eigenvalues — and its inverse-even sum
is exactly `2` when `Even(v)` includes `v` and exactly `4` when it does not. So
under the reading AdaIvy froze their witness does not refute (`2 <= 3`), and
under `even_excludes_v` it does (`4 > 3`). One evaluation of *their* witness
under *our* conventions produces the entire external review finding. Nothing in
the repository performed it, because nothing in the repository was obliged to.

**A fourth fact makes the engine unavoidable.** The shipped certificate
`cert.graffiti-322-exact-separation` names its engine
`exact_graph_distance_and_invariant_space_v2`. That identifier occurs in exactly
two places in this repository: the manuscript record and the rendered
`paper.tex`. There is no such engine in `src/`. The certificate is therefore not
reproducible from the repository, which contradicts the ADR-0036 premise that a
third party re-derives `paper.tex` from `records/` and re-checks the mathematics
from the pinned artifacts.

## Options considered

| Option | Evidence | Benefit | Cost/risk | Decision |
|---|---|---|---|---|
| Status quo: a bibliography entry is sufficient engagement | ADR-0036 closure ran correctly on the shipped bundle | Already implemented and already two-way closed | Closure proves a record exists behind a citation, not that the cited result was compared to ours. The shipped bundle satisfied it completely and still shipped `not_assessed` against a paper whose anchor named the competing candidate | Rejected: measured insufficient twice |
| Require a prose paragraph comparing the cited work | Normal scholarly practice | Cheap; a human reader can check it | Prose is the medium the conventions were already lost in (ADR-0058), and `blk.scope.literature` already asserted a literature search that no record in the bundle backs. Unbacked prose is worse than silence because it reads as diligence | Rejected |
| Keep enforcement at human approval and tighten ADR-0055 | The gate is correct where it runs | No new schema surface | Leaves every draft ungated, and ADR-0056 makes drafts fully typeset PDFs. It also repeats the exact fix that Graffiti 322 escaped | Rejected: the enforcement point, not the rule, is the defect |
| Read the prior paper's published numbers and compare them | Their numbers are in the acquired bytes | No engine to build | Their numbers hold under *their* conventions. Comparing across an unrecorded convention change is the whole failure mode of ADR-0058, and Section 16.3 makes retrieved content untrusted data — a retrieved number is not an evaluation | Rejected: a source statement is evidence, not a computation |
| Mandatory classification plus replay of the prior witness through AdaIvy's own exact engine under all enumerated readings | The C4 evaluation is elementary and exact; ADR-0035's verify-don't-discover precedent; the missing engine has to exist anyway for the certificate to be reproducible | The comparison becomes a computed table; the definitional fork surfaces with no human insight; the certificate becomes reproducible from the repository; the gate moves to artifact production where drafts cross it | An exact spectral engine is real work, and exactness forces typed refusals where a floating-point implementation would return a number | **Selected** |

## Decision

Three changes, one boundary move.

**Citing a work that addresses the same target problem obliges classification.**
`citations[]` gains a required boolean `addresses_target_problem`, and
`cited_object` gains `prior_resolution_candidate`. A citation whose
`cited_object` is `prior_resolution_candidate` has `addresses_target_problem`
true; the field cannot contradict the object. When a resolution-typed claim
(ADR-0058) coexists with any citation carrying `addresses_target_problem: true`,
the manuscript must contain a `counter_candidate_replays` entry naming that
citation's witness, or it is refused as
`resolution_claim_without_prior_art_engagement`. This is the gate that would
have caught the shipped report from the passage anchor alone.

**Prior-art engagement gets a slot that does not depend on approval.** New
top-level `prior_art_engagement` — null, or `{"recheck": <adaivy.novelty-recheck.v1>}`
validated through `novelty.load_recheck` — plus a top-level `novelty_rechecks`
list for standalone records such as the `before_research` one. Until now an
ADR-0055 record could only live inside `publication_approval`, so an unapproved
report had nowhere to put one and prose filled the vacuum. Correspondingly,
`obligations[]` gains `tags` drawn from
`{novelty, prior_art, reading, human_review, formalization}`, because "is this
obligation about novelty?" was previously answerable only by reading its prose,
and the ADR-0058 headline gate has to read it mechanically.

**The teeth move to artifact production.** `produce_publication` — the
ADR-0056 single supported reader-facing path — gains a sixth fail-closed
condition: a resolution-typed claim with `prior_art_engagement is None` raises
`resolution_claim_without_prior_art_classification`. It also refuses a bundle
with no falsifiability probe touching reader-facing text
(`publication_has_no_headline_probe`), which is the state the shipped bundle was
in: ten probes, none of them on the title. The existing
`_validate_announcement_novelty_gate` is retained unchanged for approvals; this
is an additional, earlier gate, not a replacement.

**A prior witness is replayed through our own engine, under every enumerated
reading.** New package `src/math_research/exact_graph/` —
`graph.py`, `invariants.py`, `spectrum.py`, `replay.py` — implements the exact
distance-spectrum engine and `replay_candidate`, which evaluates a witness graph
under all four ADR-0058 reading tuples and records one `ReadingResult` per
tuple. Its `ReplayResult` payloads populate `counter_candidate_replays` and back
the `evidence_ref` of each `ReadingVerdict`. The renderer emits a non-optional
derived counter-candidate replay table — witness, reading, verdict — so the prior
candidate's fate under our own conventions appears in the document as a computed
value. The package is also the first in-repository implementation of
`exact_graph_distance_and_invariant_space_v2`, so the shipped certificate becomes
reproducible from the repository rather than from a description of it.

### Engine boundaries

- **Exact arithmetic only, and an undecidable comparison is a refusal.** `int`
  and `Fraction`; no `float`, no tolerance, no epsilon, no rounding.
  `inverse_even` refuses `even_count_zero` rather than dividing;
  `spectral_extent_vs` compares `lambda_max - lambda_min` against a rational by
  Sturm sequences with rational interval refinement and refuses
  `spectral_extent_comparison_undecided` when a bounded number of refinements
  cannot separate them. `replay_used_floating_point` refuses any replay payload
  whose `float_used` is not `False`. A comparison that cannot be decided exactly
  is a typed refusal, never a guess.
- **A large spectrum is refused, not approximated.** Dense characteristic
  polynomials are computed only up to `MAX_DENSE_ORDER = 64`; above it,
  `distinct_eigenvalue_count` refuses
  `spectrum_too_large_without_decomposition`. An honest bound that refuses is
  the alternative to an eigenvalue count nobody can check.
- **An operator-supplied decomposition is verified, never trusted.**
  `verify_decomposition` checks that the block dimensions sum to the graph
  order, that `D v == lambda v` exactly on every supplied scalar basis vector,
  and that each quotient matrix reproduces `D`'s action exactly on its supplied
  basis, and only then returns the distinct-root count of the product of the
  block characteristic polynomials. A mismatch is
  `decomposition_dimension_mismatch` or `decomposition_action_mismatch` — a
  typed refusal, never a warning. This is how a 448-vertex graph gets an exact
  eigenvalue count without a 448×448 characteristic polynomial, and it keeps the
  decomposition in the same category as every other model or operator proposal:
  a proposal, checked.
- **The engine is not tuned to the paper.** The acceptance facts — `G(14,18)`
  with 448 vertices and 525 edges, connected, triangle-free,
  `inverse_even(even_includes_v) == 40049/4444`, exactly nine distinct distance
  eigenvalues under the shipped blocks; C4 with three distinct distance
  eigenvalues and inverse-even `2` or `4` by reading — are *derived* and then
  compared. If `verify_decomposition` disagrees with
  `cert.graffiti-322-exact-separation` on any value, the disagreement is reported
  as a finding and preserved. Adjusting the engine to agree with the paper would
  invert the direction of trust and is prohibited.

**Unbacked claims of having searched are refused.** A prose block whose text
matches the search lexicon — `"search"`, `"searched"`, `"found no"`,
`"no prior"`, `"literature review"`, `"prior art"`, `"pre-research review"` —
and whose `record_refs` name no re-check record is refused as
`prose_asserts_unrecorded_search`. This mirrors the rule already in
`bibliography.py`: an uncited bibliography implies reading that did not happen.
The shipped report's `blk.scope.literature` asserts a pre-research review that
inspected "the Roucairol-Cazenave preprint and publication record" and found
nothing, and no record in that bundle backs the assertion.

### Named boundaries

- **The production gate is an engagement gate, not a freshness gate.**
  `novelty.load_recheck` validates structure, human performer, and content hash;
  it does not enforce the twenty-four-hour bound, which lives in
  `require_checkpoint` and needs an `action_at` and a subject binding. That
  separation is deliberate and load-bearing for ADR-0036: a bundle must stay
  re-derivable from `records/` indefinitely, and a freshness check at render time
  would make yesterday's bundle unrebuildable today. The consequence is stated
  plainly: **at production time a re-check that is stale, or bound to a different
  subject, satisfies this gate.** It proves that a classification exists and was
  performed by a human, not that it is current or that it is about this result.
  Binding the announcement subject hash at production time is a recorded
  follow-up, not a property of this slice; freshness and subject binding remain
  ADR-0055's at approval.
- **`addresses_target_problem` is a declared field, and declaring it `false`
  escapes the replay obligation.** This is a real tension with the repository's
  derived-never-declared rule, and it is accepted with three mitigations rather
  than hidden: the field is *required*, so an author cannot omit the question and
  the false answer is a recorded, hashed, attributable statement rather than
  silence; `cited_object: prior_resolution_candidate` forces it true, so the
  strongest signal cannot be talked down; and a `false` answer on a work whose
  own passage anchor names a candidate for the same conjecture is a discoverable
  contradiction in the bundle. Deriving the field — from the passage text, the
  subject id, or the ADR-0058 convention record's `coupled_subject_ids` — is the
  revisit trigger below.
- **A replay verdict is arithmetic, not adjudication.** `does_not_refute` on a
  prior witness under our reading does not establish that our result is new, and
  `refutes` does not establish that the prior authors refuted the conjecture or
  that their paper claims what our evaluation shows. It says that their witness,
  evaluated under an enumerated reading by our engine, produced that value.
  Priority remains an ADR-0055 human classification; correctness remains
  ADR-0036's evidence ladder.
- **Origin does not demote mathematics.** Following ADR-0057 section 5, a prior
  result being external, or a witness being imported, changes attribution and
  lineage and never the correctness class. The obligation created here is to
  classify and to compare, not to disparage.

## What this decision does not license

No mathematical warrant, novelty status, significance, applicability approval,
semantic-alignment approval, or graph admission is created. A replay result is a
tool observation under ADR-0057's rule: untrusted, unable to discharge an
obligation on its own. Satisfying the production gate does not make a draft an
approved or announced result — `publication_approval` stays null and the document
keeps printing its absence, and ADR-0055's second re-check is still required
before any approval. A classification of `not_found_under_protocol` still means
only that the named protocol found nothing; there is still no `novel` outcome.
Neither the replay engine nor this ADR authorizes network access, autonomous
literature discovery beyond ADR-0050/0051, or a model in the classification path:
a re-check performer is human, and `performer_kind != "human"` is already a
refusal.

The honest scope: this makes an uncompared competing candidate mechanically
detectable at artifact production, and makes the prior witness's fate under our
own conventions a visible computed row. It does not establish that AdaIvy's
result is new, and it does not make AdaIvy's reports correct.

## Consequences

Reader-facing production of a resolution-typed report now requires a human
prior-art classification record. That is a hard cost on iteration speed and it is
the intended one: the artifact that circulates is the artifact that must carry the
classification. Low-level `publication render` remains available for diagnosis,
so the cost falls on reader-facing bundles rather than on development.

The Graffiti 322 result must be rebuilt. On the new records its headline is
qualified (ADR-0058), its replay table shows the C4 candidate refuting under
`even_excludes_v`, and its prior-art classification is no longer `not_assessed`.
The shipped bundle is retained as history and superseded, never edited.

`exact_graph/` is a new mathematical capability in a repository whose Phase 5
scope is deliberately verify-only. It is bounded to the same posture: it
evaluates supplied graphs and verifies supplied decompositions, it does not
search for witnesses, and it opens no discovery path. Its refusals will be
frequent — `MAX_DENSE_ORDER` and `spectral_extent_comparison_undecided` are both
reachable on ordinary inputs — and a refusal propagating into a
`not_evaluated` verdict correctly demotes the whole claim to `proposal` under
ADR-0058. Exactness costs scope here, visibly, and that is the intended
trade.

The `make publication` assertions and the ADR-0036 probe count move to whatever
the fixture actually produces, and never the other way around.

## Falsifiability probes

- `pr.prior-art-engagement-required` — null `prior_art_engagement` on a
  manuscript with a resolution-typed claim; forbidden outcome is a produced
  bundle, in place of
  `resolution_claim_without_prior_art_classification`.
- `pr.citation-addressing-target-requires-replay` — set
  `addresses_target_problem: true` on a citation with no matching replay;
  forbidden outcome is a successful render, in place of
  `resolution_claim_without_prior_art_engagement`.
- `pr.replay-float-refused` — set `float_used: true` on a replay payload;
  forbidden outcome is anything but `replay_used_floating_point`.
- `pr.replay-witness-hash-rebound` — mutate `witness_spec_hash`; forbidden
  outcome is a replay accepted as evidence for the verdict matrix.
- `pr.prose-search-assertion-refused` — strip the recheck reference from
  `record_refs` on a block asserting a literature search; forbidden outcome is a
  successful render, in place of `prose_asserts_unrecorded_search`.
- `pr.headline-probe-required` — empty the reader-facing probe set; forbidden
  outcome is a produced bundle, in place of
  `publication_has_no_headline_probe`.
- `pr.obligation-tag-required` — drop the `novelty` tag from an open obligation;
  forbidden outcome is an unqualified headline (the ADR-0058 gate must stop
  reading it as discharged).
- Engine probes: a decomposition with a perturbed basis vector must refuse
  `decomposition_action_mismatch`; a block dimension sum short of the order must
  refuse `decomposition_dimension_mismatch`; a graph above
  `MAX_DENSE_ORDER` without a decomposition must refuse
  `spectrum_too_large_without_decomposition`.

The C4 replay is the slice's regression fixture: under
`(even_includes_v, range_distinct_count)` the verdict is `does_not_refute`,
under `(even_excludes_v, range_distinct_count)` it is `refutes`, and both extent
readings are `does_not_refute` because the extent is exactly `6`. If that fixture
stops producing those four values, the external review finding has stopped being
reproducible.

## Blueprint deviation

None. Section 12.4 acquisition provenance and Section 16.3's rule that retrieved
content is untrusted data are both strengthened rather than relaxed: a retrieved
number is not accepted as a comparison and must be recomputed locally. Section 20
scenario I already requires a checked implication from a cited result to the
local claim; this slice supplies the executable form for the case where the cited
result is a competing resolution rather than a supporting lemma. ADR-0055's
approval-side gate is retained verbatim; this ADR adds an earlier gate and does
not weaken the later one.

## Validation and revisit trigger

The decision stays valid while: `produce_publication` refuses a resolution-typed
claim with null `prior_art_engagement`; a citation with
`addresses_target_problem: true` cannot render without a matching replay;
`cited_object: prior_resolution_candidate` forces `addresses_target_problem`
true; the replay engine uses no float and no tolerance anywhere and refuses
rather than guesses; `verify_decomposition` rejects a perturbed basis; the C4
fixture reproduces the four verdicts above; the counter-candidate replay table
cannot be suppressed by manuscript input; a search assertion without a re-check
reference is refused; the ADR-0055 approval gate remains in place; and
`make check` stays offline, standard-library only, and model-free.

Reconsider if `addresses_target_problem` can be derived rather than declared (it
should be, and this is the first revisit trigger); if the production-time gate
should additionally bind the announcement subject hash; if a legitimate prior
candidate cannot be expressed as a graph the engine accepts; if
`spectral_extent_comparison_undecided` fires on the ordinary case and therefore
makes every extent reading `not_evaluated`; or if `verify_decomposition`
contradicts the shipped certificate.

Revisit with a new ADR before: allowing a non-human performer for the
classification; allowing the replay engine to search for witnesses rather than
evaluate supplied ones; accepting a retrieved numeric result in place of a local
evaluation; relaxing `MAX_DENSE_ORDER` by approximation rather than by
decomposition; or removing the production-time gate on the grounds that the
approval-time gate exists — the measured history of that argument is in the
Context above.

## Explicit deferrals

- **Binding the announcement subject hash at production time.** Presence and
  validity now; freshness and subject binding stay at approval.
- **Deriving `addresses_target_problem` from passage text or subject coupling.**
  Declared for this slice, with the mitigations named above.
- **Witness search.** The engine evaluates and verifies; it does not discover.
- **Automated acquisition of prior candidates.** Unchanged from
  ADR-0050/0051.
- **Replaying prior candidates for subjects other than the manuscript's own
  resolution target**, including the `problem.graffiti-197` coupling ADR-0058
  records.
