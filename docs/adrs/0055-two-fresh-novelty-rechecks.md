# ADR-0055: Two fresh novelty re-checks around every chosen problem

- **Status:** accepted and implemented 21 August 2026
- **Date:** 2026-08-21
- **Blueprint requirement:** C15; Sections 6, 10.1, and 16.3; ADR-0036
  publication approval boundary
- **Decision owners:** repository owner

## Context

The novelty landscape warns that benchmark novelty is fragile: a benchmark can
be solved, reconstructed from existing literature, or accidentally become
training data while still looking locally unchanged. It therefore recommends
novelty detection as an evaluation axis separate from correctness, difficulty,
and generality. The blueprint already keeps novelty orthogonal to mathematical
warrant and requires a novelty/significance assessment before a research-
contribution claim, but no executable lifecycle rule made the assessment fresh
at the two moments where stale knowledge is most costly.

Graffiti 197 exposed a second, more specific failure. AdaIvy found and checked
an earlier refutation of the same result, but the generated report did not
classify its own work accordingly. The broad `novelty: not_assessed` label was
true but insufficient: it concealed that the work was an independent
verification of an already refuted target, not a newly discovered refutation.
Prior-result status therefore has to be a separate, mandatory reporting axis
rather than prose an author may omit.

A search performed when a problem was first considered can be obsolete when
research starts. A search performed at research start can also be obsolete, or
no longer describe the result actually being presented, when that result is
announced. Conversely, treating an empty search result as proof of novelty
would violate the repository's evidence semantics.

## Options considered

| Option | Benefit | Cost/risk | Decision |
|---|---|---|---|
| One novelty review at problem intake | Lowest burden | Can be stale both at research start and announcement | Rejected |
| One review before announcement | Checks the final claim | Allows research to begin on a problem already known to be solved | Rejected |
| Automated novelty score | Cheap and repeatable | Coverage and ranking become an unjustified novelty authority | Rejected |
| Two content- and action-bound human re-checks | Tests the two vulnerable transitions and preserves uncertainty | Requires explicit evidence and a second review | Selected |

## Decision

Every operator-chosen problem has two mandatory novelty checkpoints:

1. A `before_research` re-check is the final recorded event before the first
   research action.
2. A distinct `before_announcement` re-check is the final recorded review
   before a result receives human publication approval.

"Chosen problem" means a supplied problem dossier admitted to a Phase 2 run or
ADR-0047 runtime session. The built-in deterministic Phase 2 acceptance fixture
is infrastructure rehearsal rather than an operator problem choice; production
problem intake is not allowed to use that exemption. "Announcement" means the
non-null human `publication_approval` boundary in ADR-0036. An unapproved draft,
an internal verifier finding, or a material-result event is not an announcement.
Any later public announcement path must adopt this gate before activation.

Each re-check is an `adaivy.novelty-recheck.v1` record. It must identify a human
performer, the exact subject hash, the exact next-action identifier, the search
protocol, query terms, searched sources, equivalent-formulation checks,
content-hashed evidence references, the observed outcome, and explicit coverage
limitations. Allowed outcomes are `prior_art_found`,
`not_found_under_protocol`, and `inconclusive`; there is deliberately no
`novel` outcome.

When prior art is found, the human also records its relationship to the target
(same, equivalent, stronger, weaker, overlapping, or unresolved), the kind of
resolution it reports, and whether that resolution was independently verified.
The reader-facing classification is computed from those fields. A source report
stays `reported_*`; it cannot become `already_proved` or `already_refuted`
without the separately claimed independent-verification state, and the novelty
record itself still creates no warrant.

Every runtime report persists and displays both the computed report role and
target-resolution status. Thus Graffiti 197 is rendered as
`independent_verification` / `already_refuted`. The same fields appear in an
approval-bearing publication projection and its `records/prior-art.json`.
General novelty remains independently `not_assessed`.

Freshness has three executable parts:

- the record is no more than 24 hours old and strictly precedes the action;
- its subject hash and action identifier exactly match the current transition;
- the pre-research record is persisted immediately before run creation or the
  first runtime action, while the pre-announcement record is embedded in the
  approval and links to the first record's identifier and content hash.

The announcement subject hash covers the manuscript identifier and every exact
claim statement, Lean statement, and original-problem citation. Editing a result
therefore invalidates the approval-side re-check. A new run, session, or
approval identifier requires a new record, so a check cannot authorize a
different transition.

The re-check is a bounded human literature-search record, not an assessment or
warrant. It fixes `automatic_novelty_authority` and
`creates_mathematical_warrant` to false. A `not_found_under_protocol` outcome
means only that the named protocol found nothing. Manuscript novelty remains
`not_assessed` unless a separate, explicitly authorized assessment supplies a
stronger conclusion. Crossref Phase 4D candidates may be cited as search
evidence, but Phase 4D does not itself perform the re-check or infer novelty.

## Consequences

AdaIvy now fails closed at both lifecycle boundaries. A stale problem hash,
edited result statement, mismatched action, missing evidence trail, automated
performer, expired record, reused first check, or absent second check prevents
the transition rather than merely adding a warning.

The rule adds process evidence without promoting a mathematical result. It
does not claim exhaustive literature coverage, turn the internal corpus into a
novelty oracle, authorize network access, or change the meanings of proof,
applicability, significance, and graph admission.

Replay retains the exact pre-research record. Publication retains both records
inside the approval-bearing manuscript record, so the decision can be audited
without re-running a search or calling a provider.

## Validation and revisit trigger

`tests/test_novelty_recheck_gate.py` must demonstrate that:

- a chosen problem cannot start without the first check;
- the first check immediately precedes run creation;
- stale subject, wrong action, future, and older-than-24-hour records fail;
- automatic novelty authority and warrant creation are unrepresentable;
- prior-art relationship classifications are derived and cannot be forged, and
  a source report cannot silently become an independently verified resolution;
- the frozen Graffiti 197 regression derives `independent_verification` and
  `already_refuted`, and those values appear in runtime and publication reports;
- publication approval requires two distinct linked checks;
- editing a result invalidates the announcement check; and
- draft publication remains possible with no approval and no announcement.

The existing runtime and publication suites must stay green, and `make check`
must remain network- and model-free.

Revisit with a new ADR before changing the 24-hour bound, accepting a nonhuman
reviewer, treating a search outcome as a novelty judgement, adding an automated
search provider, allowing a re-check to authorize more than one action, or
activating another public announcement path.
