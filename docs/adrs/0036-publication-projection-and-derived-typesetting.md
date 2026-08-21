# ADR-0036: Project results into a content-addressed publication bundle; the PDF is derived, never authoritative

- **Status:** accepted for the bounded publication-projection slice. The eight
  predictions in "Predictions recorded before measurement" were written **before**
  the renderer was run against the fixture, per the ADR-0032 precedent.
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 9.3 formal-language representations
  (`informal_math | latex | lean | ...`), Section 12.4 acquisition provenance and
  source hashes, Section 15 publication approval, Section 16 untrusted retrieved
  content, Section 19 phase gates
- **Decision owners:** repository owner

## Context

Nothing in the repository can currently communicate a result to a reader who is
not reading Python. `src/math_research/reporting.py` renders the Phase 1 dossier
as Markdown and `phase6/service.py::render_report` renders the release the same
way. Both are honest and both are unpublishable: no theorem environments, no
mathematics, no bibliography, no way for a third party to re-check anything.

Four facts about the existing repository bound this slice.

**The trust vocabulary already exists and is finer than any document format.**
`FormalCheckOutcome` distinguishes `kernel_checked` from
`kernel_checked_approved_standard_axioms` and from
`kernel_checked_unapproved_assumptions`; `FormalCheckFinding` carries
`approved_axioms`, `unapproved_assumptions`, the `declaration_name`, and a
`WrapperManifest` of seven hashes. `RepresentationStatus` distinguishes
`proposed` from `partially_verified`, `verified`, and `refuted`. A document format
that flattens these into an unqualified "Theorem" destroys the only thing the
project has built.

**The existing Markdown reports already carry the discipline this slice needs.**
`render_traceable_report` appends `[refs: ...]` to every line. That convention is
the correct one and it is unenforced: nothing fails if a line is added without
refs. A LaTeX renderer is where an unenforced convention becomes dangerous,
because LaTeX output is read by people who will not check.

**No LaTeX toolchain is present on the development host.** `pdflatex`,
`xelatex`, `lualatex`, `latexmk` and `tectonic` are all absent. A slice that made
`make check` depend on typesetting would be unrunnable, and one that reported a
skipped typeset step as a pass would repeat the failure mode AGENTS.md names for
the Phase 4B live HTTPS gate.

**LaTeX is a Turing-complete language with file and process access.** `\write18`,
`\input`, `\openout`, `\catcode`, `\csname`, `\directlua` and `\special` all
execute at compile time. Phase 4B acquires source content and Phase 4C retrieves
it; the blueprint's Section 16 rule that retrieved documents are untrusted data
therefore extends to any mathematical fragment that reaches a `.tex` file. A
renderer that interpolates a source-derived statement into LaTeX without a frozen
macro allowlist is a code-execution path wearing a document's clothes.

The failure mode this slice exists to foreclose is narrower and worse than any of
those: **typesetting confers authority that the underlying evidence may not
have.** A conjecture set in Computer Modern inside a `theorem` environment with a
bibliography reads as established mathematics. Presentation quality and epistemic
quality decouple completely, and LaTeX maximises the gap more than any other
output format the project could choose.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (author `.tex` directly, by hand or by model, as the artifact of record) | how mathematics is normally written | expressive, immediate, no renderer to build | the paper becomes a second source of truth that can drift from Lean and from the record store; a model in the authoring path can emit a citation with no source record; nothing is reproducible | rejected: no mechanism can bound drift once prose is authoritative |
| Wrap (project a content-hashed record set into `.tex` + `.bib` + bundle; typeset in a separate pinned gate) | the trust vocabulary, hashes and canonical serialization all already exist | every rendered token is backed by a record id; drift is a record inconsistency, not a prose mismatch; determinism is testable; no model in the path | a renderer cannot express everything a human author can, so expressiveness is bounded by the record schema | selected: ledger closure, bibliography closure, evidence-class demotion, macro allowlist, probe flips |
| Interoperate (render Markdown, convert with pandoc) | pandoc exists | cheap | adds a third-party dependency to the offline path, loses theorem environments and axiom provenance, and the conversion step is where the trust labels get flattened | rejected under the AGENTS.md standard-library preference |
| Build/defer (keep Markdown only) | the current state | zero work | no result this project produces can be communicated or re-checked by anyone outside it, which makes the exactness work unreportable | rejected |

## Decision

Adopt the wrap option. `src/math_research/publication/` projects a
content-hashed manuscript record set into a publication bundle. Nine boundaries
are part of this decision.

**The PDF is derived, the `.tex` is a projection, and the records are the
artifact of record.** The order is strict: records → `.tex` → PDF. Nothing flows
back. `paper.tex` is regenerable from `records/` alone, `paper.pdf` is
regenerable from `paper.tex` alone, and both are hashed in `MANIFEST.json`
against the `manuscript_hash` they were projected from. Editing the `.tex` by
hand is not a supported operation; the bundle records enough to detect it.

**No rendered block exists without a record reference, and the closure is
mechanical rather than conventional.** `render_manuscript` returns a
`RenderedDocument` carrying a `ProvenanceLedger` of every content block, each
with at least one `record_ref`. `paper.tex` is exactly the frozen template plus
the concatenation of the ledger's rendered blocks, and `verify_ledger_closure`
recomputes that concatenation and compares bytes. A block cannot be added to the
document without appearing in the ledger, and it cannot appear in the ledger
without a reference. This is the enforced form of the `[refs: ...]` convention in
`reporting.py`.

**Evidence class decides the environment, and demotion is the default.** The
renderer never accepts an environment name as input. `classify_claim` computes
one of three classes from the records:

| Class | Environment | Requirements, all mandatory |
|---|---|---|
| `kernel_checked_theorem` | `Theorem` | a `kernel_checked` attestation with `unapproved_assumptions == []`, whose `target_statement_hash` equals the hash of the claim's own Lean statement, on a claim whose `representation_status` is `verified` |
| `exact_certificate_proposition` | `Proposition` | an exact certificate whose `arithmetic` is an exact kind, `float_used` false, `gap` an exact rational literal, bound to a recorded run id |
| `proposal` | `Conjecture` | anything else, including every attestation outcome other than bare `kernel_checked` |

`kernel_checked_approved_standard_axioms` renders as `Proposition` with the axiom
list in the environment, not as `Theorem`; `kernel_checked_unapproved_assumptions`
renders as `Conjecture`. There is no flag, option, or fixture field that promotes
a class. Demotion is silent-safe: the failure of a missing record is a weaker
claim, never a stronger one.

**The status block is unsuppressible.** Every document opens with counts by
evidence class, the manuscript and document hashes, the corpus provenance, the
typeset status, and `novelty: not_assessed` / `significance: not_assessed`. It is
emitted by the template rather than by a section block, so no manuscript input
can remove it. If the document contains zero `kernel_checked_theorem` claims, the
status block says so in words.

**A bibliography entry exists if and only if an acquisition record backs it, and
citation closure runs in both directions.** `build_bibliography` derives entries
only from source records carrying a `content_hash`, an `authority`, and a
`rights_outcome` that permits the intended use. There is no free-text bib path
and no model in the path. `\cite{k}` with no entry for `k` is a refusal, and an
entry no block cites is also a refusal, because an uncited bibliography is
padding that implies reading that did not happen. Three citation classes are
recognised and the third is the point:

- `mathlib_declaration` — a fully-qualified declaration plus the pinned mathlib
  commit. Machine-resolvable; carries no bib entry, because the toolchain pin
  *is* the citation.
- `source_record` — a Phase 4A/4B source record. When the cited object is a lemma
  or a hypothesis rather than the paper as a whole, the citation must name a
  **passage** with its own anchor and content hash. Paper-level citation of a
  lemma is a refusal, because blueprint Section 20 scenario I is precisely the
  case where the paper and the theorem exist but the hypothesis does not, and a
  paper-level reference cannot detect it.
- `unresolved_folklore` — no record exists. It renders as an **open obligation**
  in the obligations table, never as prose, and never as a citation.

**Statement drift is a record inconsistency.** A claim carries a
`representation_id`, a `latex_statement`, and a `lean_statement`, and the Lean
statement is hashed and compared against the attestation's
`target_statement_hash`. A mismatch refuses. Every attested claim additionally
prints its verbatim Lean statement beneath the prose one, so residual drift is
visible to a reader rather than only to a test.

**Every LaTeX-bearing field is validated against a frozen macro allowlist.**
Prose fields are escaped character-wise. Mathematical fields pass through a
validator that admits a frozen list of macros and refuses the primitive classes
outright: file input (`\input`, `\include`, `\openin`, `\read`), file and process
output (`\write`, `\openout`, `\immediate`, `\special`, `\directlua`, `\pdfprimitive`),
category-code and name manipulation (`\catcode`, `\csname`, `\expandafter`,
`\def`, `\let`), and package or class loading. Refusal is by class, so an
unrecognised macro is refused rather than passed through. This applies to
project-authored fixtures too: the validator does not have a trusted-input mode.

**Typesetting is a separate named gate whose absence is never a pass.** The
offline `make publication` target renders the bundle, verifies closure, runs the
probe suite, and writes `typeset_status: "not_typeset"` with `pdf_sha256: null`.
`make check-typeset` requires the pinned toolchain in
`config/publication-typeset-toolchain-v1.json`; absent it, the target prints what
is missing and exits non-zero. The compile is bounded, offline, `-no-shell-escape`,
`-halt-on-error`, `-interaction=nonstopmode`, with `SOURCE_DATE_EPOCH` and
`FORCE_SOURCE_DATE` frozen from the bundle so the PDF is byte-reproducible; it
runs twice and refuses unless both runs hash identically. Undefined references
and undefined citations are build failures, because a `??` in a PDF is a trust
break and not a cosmetic defect. No model may iterate on a compile error: a
nondeterministic build defeats the whole projection.

**Each render rule carries a falsifiability probe, and the probe gate is a
release gate.** Following ADR-0034, a probe is a single named field of the
manuscript mutated to a different value, with a stated forbidden outcome —
either a refusal or a named demotion. `run_probes` reports `probes_flipped`, and
`probes_flipped == probes_total` gates `make publication` alongside ledger and
citation closure. A render rule that cannot be made to fail is a suite failure.

This slice creates no warrant, no applicability record, no semantic-alignment
approval and no graph admission. It reads records and emits files. Novelty and
significance are copied through as `not_assessed`; the renderer has no path that
can write either. Rendering is not publication: the bundle carries
`publication_approval: null` until a Section 15 human approval record exists, and
the status block prints the absence.

## Consequences

**The honest risk is that a well-set document is more persuasive than its
evidence, and no mechanism in this slice removes that.** Four things bound it —
demotion is the default, the status block cannot be suppressed, the axioms
appendix makes "verified in Lean" checkable against a pinned toolchain, and the
bibliography cannot contain an entry no acquisition record backs. What remains is
that a reader who ignores the status block will read a `Conjecture` environment as
a result. That is a property of documents, not of this renderer, and the correct
response is that the project's first bundle should contain zero
`kernel_checked_theorem` claims and say so on its first page.

The bundle is the deliverable and the PDF is its readable face. A third party
rebuilds the PDF from `paper.tex` plus the pinned toolchain, re-runs Lean from
`lean/` plus the pinned commits, and re-derives `paper.tex` from `records/`. Any
of the three failing is detectable from the manifest alone.

Expressiveness is bounded by the record schema, and this is a real cost. A remark
that occurs to a human author mid-writing has no record and therefore cannot be
rendered; it must first become a record. The `unresolved_folklore` citation class
exists because the alternative — letting unrecorded background in as prose — is
the drift this slice refuses.

`make check` gains one offline target and no dependency. The renderer is
standard-library only, imports no clock, no randomness and no environment, and
reaches no network, so `tests/test_repository_invariants.py` needs no new gated
boundary. `check-typeset` is the second toolchain gate after `check-sealed`,
`check-gate` and `check-phase4b-oci`, and it is documented in the same terms.

TeX Live is not pinned by digest in this slice — only by distribution, version
and the exact binary invocation — because acquiring an image needs network. The
pin is therefore weaker than the ADR-0016 Lean pin and weaker than the ADR-0028
parser image pin, and the manifest records which pin kind it has.

## Predictions recorded before measurement

Written before the renderer was run against
`fixtures/publication/manuscript-v1.json`, so that the fixture cannot be tuned to
the outcome:

1. The bundle renders zero `kernel_checked_theorem` claims, because no Lean
   attestation is reachable offline and `make check` deliberately excludes the
   sealed Phase 3B runtime.
2. The Phase 5 `QD-FS-01` result renders as `Proposition` under
   `exact_certificate_proposition`, with its gap as an exact rational.
3. The main noncommuting claim renders as `Conjecture`, on the ADR-0033 measured
   boundary that a degree-three optimum admits no quadratic certificate.
4. Ledger closure holds byte-for-byte on the first run, and the document hash is
   identical across two calls and across a fresh process.
5. Every probe flips.
6. The `unresolved_folklore` citation appears in the obligations table and not in
   `refs.bib`.
7. `typeset_status` is `not_typeset` and `pdf_sha256` is null on this host.
8. The status block reports zero theorems in words.

## Measured outcome

Implemented and measured on 21 August 2026. All eight predictions held.

| Prediction | Outcome |
|---|---|
| 1. Zero `kernel_checked_theorem` claims | held: 0 of 5 claims; no `adatheorem` environment in the document |
| 2. The exact diagonal result renders as `Proposition` | held: `cl.orthogonal-2d-optimum`, gap exactly `0` |
| 3. The noncommuting claim renders as `Conjecture` | held: both `cl.cubic-optimum-degree` and `cl.general-noncommuting-convergence` |
| 4. Ledger closure holds and the hash is stable | held: byte-exact on the first run, identical across two calls and a fresh process |
| 5. Every probe flips | held: 17 of 17 |
| 6. Unrecorded background is an obligation, not a bib entry | held: `obl.jrf-general-convergence` in Appendix B, absent from `refs.bib` |
| 7. `typeset_status` is `not_typeset`, `pdf_sha256` null | held: no TeX engine on this host, and `make check-typeset` exits non-zero saying so |
| 8. The status block reports zero theorems in words | held: "This document contains no kernel-checked theorem." |

| Measure | Value |
|---|---|
| Claims by computed class | 0 theorem / 3 exact proposition / 2 proposal |
| Ledger blocks | 24 (13 from the manuscript, 11 derived), every one with a resolving record reference |
| Rendered document | 13,667 bytes of `.tex`; 8 bundle files plus `MANIFEST.json` |
| Falsifiability probes | 17 declared, 17 flipped |
| Single-field mutations checked for promotion | 1,467 across every claim and certificate field; 876 refused outright, 591 rendered, **zero produced a theorem** |
| Bibliography entries | 3, each derived from a source record whose content hash is verified against the actual repository bytes |
| Acceptance assertions | 53 tests |
| New dependencies, network calls, model calls | 0 |

Six things are recorded rather than smoothed over.

**`certificate_role` was added during implementation, because the first
classifier was wrong.** It treated any nonzero gap as a demotion. That is right
for a claim that asserts an optimum and exactly backwards for a claim that
asserts a separation: on `qd-fs-01-scalar-full-support` the certified gap of
`1/196611` *is* the evidence that eight iterations do not attain the optimum, and
on `qd-ce-01-boundary-fixed-point` the gap of `1/3` *is* the evidence that a fixed
point need not be optimal. A claim now names the role it offers its certificate
in, and both mismatches demote: a zero gap cannot support a separation and a
nonzero gap cannot determine an optimum.

**A crash is not a fail-closed refusal, and the first validator crashed.**
Membership tests against the frozen vocabularies raised `TypeError` on an
unhashable value rather than refusing it, so a manuscript field set to `[]`
aborted the projection instead of being rejected with a code. The
promotion-impossibility test found it precisely because it mutates fields to `[]`
and `{}`. Eleven membership checks now guard the type before the lookup. The
lesson generalises: a validator that only refuses the inputs its author imagined
is not fail-closed.

**The shipped fixture carries no attestation on purpose, so the attestation
ladder is exercised by a synthetic manuscript inside the acceptance suite.** The
suite demonstrates that the theorem rung is reachable, that an unverified
representation demotes it, that `kernel_checked_approved_standard_axioms` is a
proposition, that an unapproved assumption demotes to a proposal, that all six
non-kernel outcomes demote, and that a Lean statement edited after checking is
refused by hash. None of that is in the fixture, because printing "Theorem" from
a fabricated attestation in the project's flagship example is exactly the failure
this slice exists to prevent. A bundle with a theorem in it requires
`make check-sealed` and `make check-typeset` together.

**Passage anchors are line ranges, and line ranges shift.** The three sources are
the project's own ADRs, cited by repository path with the sha256 of the file and
the sha256 of the cited line range. The acceptance suite recomputes both against
the actual bytes, so a stale hash fails rather than lying — and it fired within
the implementation session itself, when concurrent work edited ADR-0035 and its
recorded source hash went stale. That is the mechanism working as designed, and it
is also a standing maintenance cost: any edit to a cited file requires the
manuscript to be re-authored. A content-addressed passage store would remove the
cost and does not exist.

**`make publication` asserts counts and properties, never the document hash.**
The manuscript embeds hashes of live repository files, so its own hash moves
whenever a cited ADR is edited. Pinning the document hash in the target would
make ordinary documentation edits fail a publication gate for no epistemic
reason. The gate therefore asserts what must not move: zero theorems, the class
counts, full probe flips, and `not_typeset`.

**One residual risk has no offline check.** Nothing can verify that a rendered
LaTeX statement says what its certificate certifies. The renderer's only answer
is presentational: the certificate table with the exact primal value, dual value
and gap is emitted immediately beside the claim, so a reader can compare the two.
That is a mitigation, not a proof, and it is the reason the exact-certificate
rung is a `Proposition` rather than anything stronger.

## Blueprint deviation

None. Section 9.3 already lists `latex` beside `lean` as a formal language, so a
LaTeX representation of a statement is an existing first-class object rather than
a new one; this slice binds the two to one `representation_id` instead of letting
them be independent renderings. Section 15's publication approval is respected by
recording its absence rather than by asserting it.

## Validation and revisit trigger

The decision stays valid while `make check` remains green and offline; ledger
closure, bibliography closure in both directions, and the macro allowlist all
hold; no evidence class can be promoted by a manuscript field; the status block
is emitted by the template; every probe flips; the document hash is stable across
processes; `typeset_status` is written from an executed compile or is
`not_typeset`; and novelty and significance stay `not_assessed`.

Reconsider if a rendered block is needed that no record can back, if a probe
cannot be made to flip by any single-field mutation, if a legitimate mathematical
fragment requires a macro the allowlist refuses by class, if the PDF cannot be
made byte-reproducible under a pinned toolchain, if a bundle is wanted for a
result whose Lean attestation exists but whose `target_statement_hash` cannot be
bound to the rendered statement, or if any consumer starts treating `paper.pdf`
rather than `records/` as the artifact of record.

## Explicit deferrals

- **A digest-pinned TeX Live image.** Needs network acquisition, so the pin is
  distribution plus version plus invocation in this slice.
- **A real Lean attestation in the bundle.** Requires the sealed ADR-0016 v5
  runtime that `make check` excludes; the offline path therefore demonstrates
  demotion rather than the theorem path. `make check-sealed` plus
  `make check-typeset` together are what would produce a bundle with a theorem in
  it.
- **Section 15 publication approval as an executed record.** Recorded as absent.
- **Multi-document bundles, cross-references between bundles, and journal
  submission formats.** One document, one bundle.
- **Rendering the Phase 4C retrieval report or the Phase 6 release into the same
  bundle.** This slice projects claims, certificates, attestations and sources
  only.
