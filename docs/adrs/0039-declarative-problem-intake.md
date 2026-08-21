# ADR-0039: Declarative problem intake as a builder over Phase 1 entities

- **Status:** accepted for the bounded declarative problem-intake slice;
  implemented 21 August 2026 with all gates measured -- see "Measured outcome"
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 1 versioned problem specification and
  semantic-custody record, Section 4.1/4.2/4.15/4.20 domain records, Section 5
  trust model, Section 21.2 inward dependency direction
- **Decision owners:** repository owner

## Context

The research engine is already problem-agnostic and the intake is not. Both
halves of that sentence are measured, not asserted.

`BaselineResearchLoop` in `src/math_research/phase2/baseline_loop.py` reads a
problem only through `dossier.formalization` and `dossier.semantic_alignment`:
`_proposer_context` selects the target by
`dossier.formalization.target_claim_id`, the premises by
`dossier.formalization.assumption_claim_ids`, and the open obligations by claim
identity; `_verifier_context` adds only accepted evidence and the candidate; and
`_validate_target_and_refs` checks model output against the same identifiers. No
line of that loop mentions any particular problem. `SQLiteWorkspace.create_run`
takes `dossier: ResearchDossier` and stores its canonical bytes.

The only way to obtain a dossier was
`build_known_valid_theorem_dossier()` in `application/manual_slice.py`. It takes
**zero arguments**, hardcodes `STAMP = datetime(2026, 8, 19, tzinfo=utc)` and a
single `ACTOR = oid("actor.manual_researcher")`, and returns one fixed dossier
about the sum of two even integers. `cli.py create` therefore created *the*
dossier, not *a* dossier. Pointing the system at a new research problem meant
writing a new Python module.

Two existing consumers pin that fixed dossier and must not be disturbed:
`tests/test_phase1_*` import `ACTOR`, `STAMP`, and the builder directly, and
`src/math_research/phase6/generality.py` uses it as the GC-01 positive control,
where a rewrite would silently change what "positive control" means. So the
intake has to be a new module, not a refactor of `manual_slice.py`.

Three further measurements bound the design.

**The dossier interchange grammar cannot double as the intake grammar.**
`import_trusted_replay` validates references and hashes, not authority, because
ADR-0005 scopes it to replay of a dossier this system exported and routes foreign
documents to `import_external_proposals`. Measured: taking the exported manual
dossier, changing `created_by` to `actor.untrusted_submitter`, recomputing the
content hash, and re-importing yields a dossier with three warrants that
`TrustPolicy` projects as `proved`. A declarative intake built on that schema
would be a trust hole in the shape of a convenience feature. The intake needs a
narrower grammar with no field that can express a warrant.

**The Phase 1 scenario vocabulary is a different thing.**
`interchange.SCENARIO_KINDS` has exactly five members and
`tests/test_phase1_interchange.py` asserts exactly five Phase 1 fixtures against
them. Those kinds name adversarial *trust traps* (`formally_provable_mistranslation`,
`real_but_inapplicable_theorem`, ...), not research problems. Extending that
vocabulary to carry problem definitions would conflate a trap taxonomy with a
problem specification, so it was not done and is not proposed.

**Time must be an input.** Every deterministic acceptance path in this
repository already takes its instant explicitly: the Makefile passes
`PHASE5_INSTANT` and `PHASE6_INSTANT` rather than `date` output, precisely
because a moving clock breaks byte reproducibility. An intake that called
`utc_now()` would produce a different dossier on every run.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (reuse `research-dossier-v1` as the intake format) | Schema exists; `import_trusted_replay` already validates it | Zero new schema; immediate | Measured: a hand-authored document in that grammar projects as `proved` with three warrants. The grammar has warrant, evidence, and verification fields by design | Would need authority checks inside Phase 1 trust semantics, which are sealed |
| Adopt (extend `SCENARIO_KINDS` / `phase1-scenario` schema) | Five kinds and five fixtures exist | Reuses a validated schema | The five kinds are adversarial trust traps, not problems; `tests/test_phase1_interchange.py` asserts the cardinality; conflates two vocabularies | Owner ruling that the vocabularies are the same thing |
| **Wrap (new narrow declarative grammar plus a builder over existing entities)** | Engine already drives off `dossier.formalization`; `manual_slice.py` is the only builder | Closes the intake gap today; no entity change; no trust-model change; the grammar can omit every trust-bearing field | A second schema to keep aligned with the domain enums; a well-formed problem is not a tractable problem | Enums derived from `domain/entities.py`; explicit instant; content-hash binding; fail-closed validation; forbidden outcome demonstrated impossible |
| Interoperate (copy `manual_slice.py` per problem) | Status quo | No new code | Every new problem is a Python module and a code review; timestamps and actors get copy-pasted; no provenance from dossier back to a problem statement | -- |
| Build/defer (no intake) | -- | -- | The measured architectural gap stays open; silent drift prohibited by AGENTS.md | -- |

## Decision

Adopt the wrap option.

Add `schemas/problem-definition-v1.schema.json` and
`src/math_research/application/problem_intake.py`, plus the
`math_research.cli problem` subcommand in `src/math_research/problem_intake_cli.py`.
The loader validates untrusted bytes and then constructs existing Phase 1
entities. `domain/entities.py` and `domain/policies.py` are unchanged.

Seven boundaries are part of this decision.

**The grammar has no trust-bearing field.** A problem definition declares the
target claim (statement, `kind`, `ClaimScope`), the assumption claims, the
formalization that links them by local ID, the proposed semantic alignment, the
evaluation protocol, the originating principal, and a declared domain. It has no
field for a warrant, evidence, verification record, source applicability record,
representation map, proof status, confidence, novelty, significance,
contribution, semantic-alignment approval, protocol freeze, claim origin, or
timestamp. Those keys are not merely unknown: they are named in
`FORBIDDEN_FIELDS` with the reason they are refused, so a document that tries to
buy trust is told exactly what it may not do.

**Four values are forced, not accepted.** Semantic alignment is always
`AlignmentStatus.PROPOSED` with `approved_by=None`, because approving a target
interpretation is a researcher act (Section 4.15). Every claim origin is
`ClaimOrigin.USER`, because declaring `source` origin would assert provenance
the intake cannot supply (correctness contract C1: a content-addressed source
document version and span). The evaluation protocol is never frozen. The
trust-bearing dossier tuples are literal `()`.

**Enumerated values are derived, never re-listed.** `ProblemType`, `ClaimScope`,
and `StrengthRelation` are taken whole from the Phase 1 enums.
`ApprovalStatus.APPROVED`/`SUPERSEDED` and `ProtocolPhase.CONFIRMATORY` are
excluded, each named once with its reason, because each is a researcher act
rather than a declaration. The published JSON Schema is generated from those
enums by `problem_definition_schema()` and the acceptance suite asserts the file
is byte-identical to the generator output, so the schema cannot drift from the
domain model.

**Two obligations are opened, never discharged.** Every intake dossier carries
an OPEN `logical_gap` obligation recording that no warrant exists and an OPEN
`semantic_alignment` obligation recording that the target interpretation awaits
approval. Both appear as `TrustPolicy` blockers.

**Time is an explicit argument.** `parse_instant` accepts only an explicit UTC
instant of the form `2026-08-21T00:00:00Z`; the CLI takes it as a positional
argument and the Makefile passes `INTAKE_INSTANT`. No document field may supply
it, so there is exactly one source of time. `random`, `secrets`, `time`, and any
`now`/`utcnow` attribute are absent from both modules, and the acceptance suite
asserts their absence by parsing the module source.

**Provenance is bound semantically, with the operational hash kept outside.**
The canonical hash of the accepted document is bound into the dossier ID
(`dossier.<slug>.intake.sha256-<first 16 hex>`) and into an append-only
`problem_definition_recorded` audit event, so the dossier's canonical content
hash covers the problem that produced it. The raw source-byte hash is
operational -- it moves when the file is reformatted without changing meaning --
so it is returned in `ProblemIntakeResult` and printed by the CLI rather than
stored in the dossier, following the Phase 3B semantic/operational split.

**Validation fails closed, once.** Unknown keys, forbidden keys, duplicate JSON
object keys, malformed JSON, non-UTF-8 bytes, non-finite JSON constants, missing
fields, wrong types (including `bool` where an `int` is required), out-of-enum
values, forbidden enum members, unresolved assumption references, duplicate
local IDs, bad identifiers, empty strings, padded strings, control characters
including `\r`, non-NFC text, and over-length or over-count collections are all
rejects. There is no coercion and no silent default: text is rejected for not
being NFC rather than normalized. All issues are collected and raised together as
one typed `ProblemDefinitionError` carrying machine-readable
`ProblemDefinitionIssue` records in a stable order.

## Consequences

The honest risk in this slice is that a declarative intake makes it easy to
define a problem the system cannot make progress on, and easy to mistake a
well-formed dossier for a tractable one. Nothing in this slice measures
difficulty, and a file is not evidence that anything can be done with it. The
existential fixture shipped here -- an odd perfect number below `10^2200` -- is
formally impeccable, exhaustively canonical, and hopeless: it will produce an
intake dossier, a Phase 2 run, and two open obligations, and no progress. The
CLI summary is deliberately shaped to keep this visible: it prints measured
`logical_status`, warrant kinds, and record counts, all of which read zero or
`unknown` for every intake, so a reader who mistakes intake for progress has to
ignore the output rather than misread it. There is no tractability signal, and
adding one would be a new slice with its own evidence.

A second real cost: this is a second schema over the same domain. It is derived
from the Phase 1 enums, and the acceptance suite fails if the published file
stops matching the generator, but the *field* set is still hand-maintained. A new
Phase 1 entity field will not appear here automatically, and should not, since
the intake's job is to omit most of them.

A third: the accepted document's canonical hash is bound into the dossier ID, so
editing a problem file produces a different dossier identity. That is the append-
only behaviour we want -- a revised problem is a new problem -- but it means a
typo fix is not an in-place edit, and two dossiers for the same research question
will co-exist. Nothing supersedes the earlier one; that would be a lifecycle
slice.

What the intake deliberately does **not** do:

- it does not create an `EpistemicWarrant`, `Evidence`, `VerificationRecord`,
  `SourceApplicabilityRecord`, or `RepresentationMap`, and the builder does not
  import those types;
- it does not approve semantic alignment, approve a formalization, freeze an
  evaluation protocol, or discharge an obligation;
- it does not set novelty, significance, or contribution;
- it does not admit anything to a claim graph as accepted knowledge, and the
  Phase 3A path admits an intake dossier only as a `proposal`;
- it does not assert that the declared assumptions are true, that the
  formalization means what the informal statement means, or that the problem is
  tractable, well-posed, open, or interesting;
- it does not read a clock, a network, a model, or a source document;
- it does not modify Phase 1 trust semantics, sealed Phase 2 evidence, Phase 3A
  memory internals, the sealed Phase 3B runtime, the Phase 4A rights boundary,
  deletable content, or protected evidence manifests, so it stays inside the
  ADR-0026 lightweight per-slice process.

## Measured outcome

Implemented and measured on 21 August 2026. `make check` is green: 1317 tests,
16 skipped for the disposable `jsonschema` gate environment, plus every phase
acceptance target including the new `problem-intake` target. The total moves as
concurrent slices land; this slice contributes 56 tests in three modules.

| Property | Gate | Measured |
|---|---|---|
| Example problems load | 2 shapes, non-quantum | 3 files: existential, unrestricted universal, and one that asserts its own proof |
| Measured target status | `unknown` for all | `unknown` for all 3, warrant kinds `()` |
| Rejection classes | one fixture per class, exactly one code each | 28 invalid fixtures over 21 classes, each producing exactly its own code; `too_large` is the 22nd class and is generated in-test rather than committed as a quarter-megabyte fixture |
| Enum-space search for a forbidden outcome | no combination reaches a status other than `unknown` | 360 accepted combinations built and projected; `{"unknown"}` observed |
| Forbidden-key injection | rejected everywhere | 33 keys x 3 fixtures at top level and 33 keys x 6 nested containers, all `forbidden_field` |
| Determinism | byte-identical across runs, processes, hash seeds | identical bytes for `PYTHONHASHSEED` in {0, 1, 12345} and in-process |
| Provenance binding | canonical problem hash inside the dossier's canonical identity | dossier ID suffix and audit-event payload both carry it; reformatting the file leaves the dossier bytes unchanged and moves only the operational hash |
| Schema drift | published file equals generator output | byte-identical; every enum equals its domain enum |
| External cost | zero | no network, model, or third-party import on any tested path |

The trust property is demonstrated three independent ways rather than tested
once. By construction: the builder module never imports
`EpistemicWarrant`, `Evidence`, `VerificationRecord`,
`SourceApplicabilityRecord`, or `RepresentationMap`, asserted by parsing its own
AST, and the five corresponding `ResearchDossier` keyword arguments are asserted
to be empty tuple literals in the AST. By grammar: every forbidden key is
rejected at the top level of all three fixtures and inside all six nested
containers. By exhaustion: all 360 documents the accepted enum space can express
are built and projected, and none reaches `proved`, `disproved`, or `supported`.

The `asserts-its-own-proof-v1` fixture is the named adversarial case. Its title
begins `PROVED:`, its informal statement instructs the reader to treat the target
as proved, formally verified, warranted, novel, and highly significant, its
target statement repeats `PROVED (formal_proof, verified, no open obligations)`,
and its tags include `already-proved` and `warrant-granted`. Measured
`logical_status` is `unknown`, warrant kinds `()`, novelty and significance
`not_assessed`, with three blockers. The Makefile target asserts that recorded
outcome, so a silent move in either direction fails `make check`.

Which existing paths accept an arbitrary dossier, measured:

- **Accept.** `math_research.cli inspect`, `interchange.write_dossier` /
  `export_dossier_dict` / `import_trusted_replay`,
  `domain.repositories.InMemoryTrustStore.append_dossier`,
  `domain.policies.TrustPolicy`, `SQLiteWorkspace.create_run` /
  `save_dossier` / `load_dossier`, and `BaselineResearchLoop.start` /
  `advance` / `run_to_terminal`. The Phase 2 loop drives an intake dossier to
  `awaiting_review` with two `proposal` records, and the reloaded dossier still
  projects `unknown` with no warrants.
- **Accept, as a proposal only.** `ResearchMemoryWorkspace.import_proposal`
  stores an intake dossier export with `disposition == "proposal"` and leaves
  `all_records()` empty. That is the correct Phase 3A behaviour, not a
  limitation.
- **Accept at the request boundary.** `phase3b.validation.parse_request` accepts
  an intake dossier's `claim_id` and `semantic_alignment_id` without
  special-casing. Executing a check needs the sealed ADR-0016 v5 image and is
  outside `make check`, so only the request path is measured here.
- **Now accepts, closed after this ADR was first written.**
  `src/math_research/phase2_cli.py` originally hardcoded
  `build_open_theorem_dossier()` in both `_loop` and the `start` branch. It now
  takes `--problem` plus an explicit `--intake-instant` and resolves the dossier
  through this loader; `_loop` receives the dossier rather than rebuilding one,
  and `advance`, `pause`, and `resume` reload the dossier the run was actually
  started with instead of re-deriving a fixture. Measured end to end on
  `graph-cycle-edge-bound-v1.json`: the run reaches `awaiting_review` with two
  proposals recorded, and the reloaded dossier still projects `unknown` with
  zero warrants and zero evidence. `asserts-its-own-proof-v1.json`, run through
  the same path, also stays `unknown` with zero warrants.

  The deliberate omission is the important half: there is **no** `--dossier`
  option and no `import_trusted_replay` call on externally supplied bytes. A
  problem definition cannot express a warrant; a canonical dossier file can, and
  the measurement in this ADR's Context shows a re-imported dossier projecting
  `proved`. Accepting one on the run path would be a trust hole, so the run path
  takes problem definitions only.
- **Does not apply.** `reporting.render_traceable_report` is not reused: its
  lines assert that target evidence was independently checked, which is never
  true of an intake dossier, and it is shared with the Phase 2 and Phase 3A
  reports whose bytes are pinned by tests. The intake CLI renders its own report
  that states what was declared and what was measured.

## Explicit deferrals

- **A `--dossier` option on any CLI.** Not deferred pending effort: rejected.
  The intake grammar is the trust boundary, and a dossier file bypasses it.
- **Problem lifecycle.** Superseding, revising, or versioning a problem
  definition; linking a revised definition to the dossier it replaces. Today a
  revision is simply a new dossier identity.
- **Tractability, well-posedness, or novelty assessment of a declared problem.**
  Nothing here estimates whether a problem is approachable, and no such signal
  may be inferred from a successful intake.
- **Source-backed assumption claims.** `ClaimOrigin.SOURCE` needs a
  content-addressed source document version and span (C1), which means the
  Phase 4A/4B acquisition path and a rights decision. Intake claims are
  `ClaimOrigin.USER` until then.
- **Representation maps and bridge obligations** declared from a problem file.
  Those are verified records with their own obligations.
- **Unifying the Phase 1 scenario vocabulary with problem definitions.** Not
  done, not proposed; the two are different things.
- **A Draft 2020-12 validation run of the new schema.** `jsonschema` is not
  installed in the ordinary environment and `pyproject.toml` dependencies stay
  `[]`. The schema follows the `prefixItems`/`items: false` pattern already used
  by `research-dossier-v1.schema.json`, and the loader -- not the schema file --
  is the enforcing artifact. Adding it to `make check-gate` is a follow-up.

## Validation and revisit trigger

The decision stays valid while `make check` is green, the intake imports no
third-party or network module, `domain/entities.py` and `domain/policies.py`
remain unmodified by this slice, the published schema stays byte-identical to the
generator output, the grammar contains no trust-bearing field, and every example
problem continues to measure `logical_status == "unknown"`.

Reconsider if a problem definition ever needs to express a warrant, evidence, an
approval, or a frozen protocol; if the intake acquires a clock read, a default, or
a coercion; if a second consumer needs a field the grammar omits badly enough to
motivate widening it; if the operational source-byte hash is found inside a
semantic content hash; or if anyone treats a successful intake as evidence that a
problem is tractable.
