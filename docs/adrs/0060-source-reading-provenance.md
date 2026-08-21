# ADR-0060: Record how well a source was read, separately from which bytes we hold

- **Status:** accepted for the bounded semantic-gate slice; implemented by the
  change this ADR records, with the falsifiability probes below as the release
  condition
- **Date:** 2026-08-22
- **Blueprint requirement:** C15; Sections 12.4 acquisition provenance and source
  hashes, 16.3 untrusted retrieved content, 20 scenario I (real but inapplicable
  theorem); ADR-0014 source authority, ADR-0017 rights and applicability review,
  ADR-0028 Phase 4B authorized acquisition and exact-source parsing, ADR-0036
  passage-level citation; ADR-0058 convention records; ADR-0059 prior-art
  engagement
- **Decision owners:** repository owner and researcher

## Context

ADR-0036 made passage-level citation mandatory for anything narrower than a
whole work, on the Section 20 scenario I argument that a paper-level reference
cannot detect a mismatched hypothesis. It is the right rule and the shipped
Graffiti 322 bundle followed it. Here is what a passage record contained:

```json
{"anchor": "PDF page 47, Even definition",
 "content_hash": "sha256:c88e5032…",
 "passage_id": "psg.wow.even-definition",
 "quotation_permitted": true}
```

An anchor string, a content hash, a rights flag, and **no text**. The record
proves that some bytes were located and that they have not changed since. It
says nothing whatsoever about whether anyone read them, by what means, or
whether the reading is reproducible. A content hash is a tamper-evidence
mechanism; it was being relied on as a faithfulness mechanism, and those are
different properties.

ADR-0055 named this exact shape of insufficiency for a different field: a broad
`novelty: not_assessed` label was "true but insufficient" because it concealed a
distinction that mattered. A verified `content_hash` on an unread passage is the
same kind of true-but-insufficient record, and it is more dangerous, because
unlike `not_assessed` it reads as a positive result.

The gap became load-bearing. `psg.wow.even-definition` is the passage that fixes
whether `Even(v)` counts `v` itself, which is the linchpin of the entire result
(ADR-0058). The shipped abstract calls the result "an exact counterexample to the
**source-faithful** formulation of Graffiti 322" and the claim prose says the
graph refutes 322 "under the frozen **source-faithful** conventions". The
external reviewer of that report could not extract page 47 at all: the text layer
of the 2004 *Written on the Wall* compilation has broken font encoding and the
page needs OCR. The reading on which the paper's central claim depends is
therefore unconfirmed by anyone outside the run that produced it, in a document
that describes it as faithful to the source, and that fact was discovered during
review rather than read off a record.

**The capability existed; the record did not.** ADR-0028 activates authorized
acquisition with exact-source parsing, so the repository already distinguishes
extraction outcomes at the Phase 4B boundary. The publication passage schema had
no field to carry any of it. The result is that the two least reliable steps in
the whole chain — pulling glyphs off a 2004 PDF, and deciding what a 2004
one-line conjecture statement means — were the two steps with no representation
in the record set, while every downstream step had exact rationals and content
hashes.

There is also a naming trap worth stating explicitly, because the shipped
document walked into it. "Source-faithful" reads like a provenance claim and is
in fact a semantic claim: it asserts that our formalization means what the source
means. Provenance is checkable by hash. Semantic faithfulness is not checkable at
all by this repository, and the phrase borrows the credibility of the former for
the latter.

## Options considered

| Option | Evidence | Benefit | Cost/risk | Decision |
|---|---|---|---|---|
| Status quo: anchor plus content hash | ADR-0036 implemented it; hashes verified against real bytes and a stale hash did fire during that slice | Tamper-evident, cheap, already working | Conflates byte provenance with reading provenance. The shipped bundle satisfied it fully while the linchpin reading was unextractable and undeclared | Rejected: measured insufficient |
| Trust the author's prose account of how a source was read | The shipped body was otherwise candid | No schema change | Prose is precisely where the conventions were lost (ADR-0058) and where an unbacked literature search was asserted (ADR-0059). An unfalsifiable sentence about extraction is not provenance | Rejected |
| Require successful mechanical extraction before a passage may be cited | Strongest possible guarantee of reproducible reading | Nothing unreproducible could ever be cited | Bans the honest case. A 2004 scanned compilation is a legitimate primary source; refusing to cite it does not make the mathematics less dependent on it, it just moves the dependence back into prose. It would also have refused the correct citation of Graffiti 322 itself | Rejected: fails closed against the wrong thing |
| Build a content-addressed passage store holding the source bytes | ADR-0036 named its absence as the cause of a standing maintenance cost | Removes anchor drift and makes re-extraction local | Large, orthogonal to this defect, and rights-encumbered for third-party sources. It would still not record *how well* the bytes were read | Rejected for this slice; not superseded |
| Record extraction method, reading status, verbatim text and its hash, and demote any claim resting on an unreproduced reading | The failure is exactly a missing field; ADR-0036 proved that mandatory demotion from computed records holds under adversarial mutation | The weakest link becomes visible in the record and in the document; a reader can re-extract and compare; "source-faithful" becomes an earned phrase | The status is author-declared, so the record is honest about the reading rather than a verification of it | **Selected** |

## Decision

**A passage record separates what bytes we have from how well we read them.**
`sources[].passages[]` gains four fields:

- `extraction_method` in `{text_layer, ocr, manual_transcription, unextractable}`
  — by what means the bytes were turned into characters;
- `reading_status` in `{verbatim_confirmed, transcribed, asserted}` — how
  reproducible the resulting text is;
- `verbatim_text` — the text itself, **required** unless `reading_status` is
  `asserted`, in which case it must be absent or empty;
- `verbatim_hash` — the content hash of that text, distinct from the passage's
  `content_hash` over the source bytes.

The two hashes answer two different questions and are never interchangeable.
`content_hash` answers "are these the same bytes we acquired?"; `verbatim_hash`
answers "is this the same reading we recorded?" A passage can pass the first and
have nothing to check against the second, which is exactly the shipped state.

Four refusals enforce it: `passage_reading_unrecorded` when either status field
is missing, `passage_verbatim_missing` when a non-asserted reading carries no
text, `passage_verbatim_hash_mismatch` when the hash does not match the text,
and `passage_extraction_inconsistent` when the method and the status contradict.
The consistency matrix is stated rather than left to interpretation:
`unextractable` admits only `asserted`; `ocr` and `manual_transcription` admit
`transcribed` or `asserted` and never `verbatim_confirmed`, because
`verbatim_confirmed` means the bytes yielded the text mechanically and neither
OCR nor a human retyping is that; `text_layer` admits all three.

**A claim may not be described as source-faithful when it rests on an asserted
reading.** `conventions.weakest_reading_status` (ADR-0058) returns the weakest
status among the readings a given reading tuple depends on, under the total order
`asserted < transcribed < verbatim_confirmed`, and it returns `asserted` if any
one reading in the tuple does. The renderer derives its fidelity wording from
that value — "source-verbatim reading" or "source-asserted reading" — and the
phrase **"source-faithful" is on the frozen ADR-0058 `RESOLUTION_LEXICON`**,
refused in author-supplied headline text unless every reading the claim rests on
is confirmed. It is on that list deliberately: it is a semantic claim wearing a
provenance claim's clothes.

**An asserted reading is an open obligation, and it names what is unreproduced.**
A resolution-typed claim resting on a reading with `reading_status: "asserted"`
carries an open obligation tagged `reading` (ADR-0059's obligation tags) whose
statement names the specific passage and the specific reading that no one has
re-extracted. It appears in the obligations table, and because the ADR-0058
headline gate reads open obligations, it also reaches the displayed title. For
the Graffiti 322 record the obligation names `psg.wow.even-definition` and the
`even_includes_v` reading, and the fixture carries `reading_status: "asserted"`
with `extraction_method: "unextractable"`, because that is what is true of page
47.

### Named boundaries

- **This records reading provenance; it does not verify reading.**
  `verbatim_hash` binds the text to itself. Nothing in this slice binds
  `verbatim_text` to the acquired bytes, because doing so requires the
  extraction to be re-runnable offline, which for a broken 2004 text layer it is
  not. So `verbatim_confirmed` is a *claim about extraction*, and only `asserted`
  is self-punishing. The direction of a possible lie is what makes this worth
  shipping: the only way to escape the obligation is to declare a stronger status
  and supply the text, which puts a checkable string in a hashed, published,
  append-only record with an author's name against it. A reader who can extract
  the page can falsify it in one step. Today there is no string and nothing to
  falsify.
- **Byte provenance and reading provenance are orthogonal axes, and neither
  implies the other.** A verified `content_hash` with an `asserted` reading is
  the shipped case and is now visible. A `verbatim_confirmed` reading of a source
  whose `content_hash` no longer matches is a different, already-refused failure.
  Nothing collapses the two into one "sourced" bit.
- **Rights outrank text, and the resulting demotion is correct.** ADR-0036
  publishes `records/` inside the bundle, so `verbatim_text` is published text.
  Where `quotation_permitted` is false the text may not be stored there, and the
  contract admits absent text only for `asserted`. The consequence is deliberate
  and stated: **a reading we may not show the reader is, for the reader, an
  asserted reading**, and it demotes exactly as one. Both Graffiti 322 passages
  carry `quotation_permitted: true`, so the interaction is latent in the current
  fixture; a rights-restricted linchpin passage forces the demoted path, and a
  dedicated refusal for the contradictory combination is a revisit trigger below.
- **`extraction_method` is not a quality score.** `ocr` is not worse than
  `text_layer` in general and `manual_transcription` by a competent human may be
  the most accurate of the three. The field records the mechanism so that a
  reader knows what to repeat; the reproducibility judgement is carried by
  `reading_status`.
- **A passage anchor is still a line or page reference and still drifts.**
  ADR-0036 recorded that cost and this slice does not remove it. The
  content-addressed passage store remains absent.

## What this decision does not license

It creates no mathematical warrant, no applicability record, no
semantic-alignment approval, no novelty or significance, and no graph admission.
`verbatim_confirmed` does not make a reading correct — it makes it reproducible,
which is a strictly weaker and different property; a perfectly extracted sentence
may still be misread. Nor does it authorize speaking for a source author: a
quoted definition plus our gloss of it is still our gloss, and the ADR-0058
convention record is where a disputed gloss goes. Retrieved and extracted text
remains untrusted data under Section 16.3 and remains subject to the ADR-0036
macro allowlist when it reaches a `.tex` file; an extraction is not a citation
and a citation is not a dependency. No model or tool output may set
`reading_status`, and this slice authorizes no new acquisition, no OCR
dependency, and no network access.

The honest scope: this makes an unreproduced reading visible in the record, in
the obligations table, and in the headline, and it makes the phrase
"source-faithful" earned rather than asserted. It does not establish that any
reading of a source is the right one.

## Consequences

The Graffiti 322 rebuild loses the phrase "source-faithful" everywhere and gains
an open obligation naming page 47. Its headline gains the ADR-0058 qualifier
partly for this reason. That is the correct reader-facing description of a result
whose central definitional reading nobody outside the run has reproduced.

Passage authoring gets heavier: every cited passage narrower than a work now
requires either the text or an explicit admission that we cannot supply it. That
is the intended cost and it falls hardest on exactly the sources where it matters
most — old scans, image-only pages, and paywalled bytes.

Adding a required field to `sources[].passages[]` is a breaking schema change on
the fail-closed path, and it lands with ADR-0058's replacement of `title`. Both
share the one `schema_version` bump; two field sets under one version is the
mixed-schema case the repository refuses. Existing bundles are superseded by
rebuilds and are not edited.

`unextractable` is a first-class value, and the repository will accumulate
records that say, permanently, that a page could not be read. That is a
preserved failure in the sense AGENTS.md requires: it stays in the machine-
readable record instead of being resolved by a confident sentence.

## Falsifiability probes

- `pr.passage-asserted-blocks-source-faithful` — set the linchpin passage's
  `reading_status` to `verbatim_confirmed` with text supplied, and confirm the
  fidelity wording and headline change; inversely, on the shipped `asserted`
  fixture, the forbidden outcome is the phrase "source-faithful" or
  "source-verbatim" appearing anywhere in the rendered document.
- `pr.passage-verbatim-missing` — remove `verbatim_text` from a `transcribed`
  passage; forbidden outcome is a successful render, in place of
  `passage_verbatim_missing`.
- `pr.passage-verbatim-hash-mismatch` — mutate one character of
  `verbatim_text`; forbidden outcome is anything but
  `passage_verbatim_hash_mismatch`.
- `pr.passage-extraction-inconsistent` — pair `unextractable` with
  `verbatim_confirmed`; forbidden outcome is anything but
  `passage_extraction_inconsistent`. The `ocr` / `verbatim_confirmed` pairing
  must refuse under the same code.
- `pr.passage-reading-unrecorded` — delete `reading_status`; forbidden outcome is
  a successful render, in place of `passage_reading_unrecorded`.
- `pr.asserted-reading-obligation-required` — close or delete the `reading`-tagged
  obligation while the passage stays `asserted`; forbidden outcome is an
  unqualified headline.

## Blueprint deviation

None. Section 12.4 requires acquisition provenance and source hashes and this
slice adds a second, clearly labelled provenance axis rather than reinterpreting
the first. Section 16.3's untrusted-content rule is unchanged and applies to
`verbatim_text` exactly as to any other retrieved fragment. Section 20 scenario I
already requires that a citation be located precisely enough to detect a
hypothesis mismatch; recording whether the located text was actually read is the
precondition that clause assumed.

## Validation and revisit trigger

The decision stays valid while: a passage cannot render without both status
fields; a non-asserted passage cannot render without text whose hash matches; the
method/status consistency matrix is enforced in both directions; an `asserted`
reading anywhere in a resolution-typed claim's reading tuple forces
"source-asserted" wording, an open `reading`-tagged obligation, and a qualified
headline; "source-faithful" cannot appear in author-supplied headline text unless
every reading is confirmed; the Graffiti 322 fixture keeps
`psg.wow.even-definition` at `unextractable` / `asserted`; every probe above
flips; and the projection stays offline, standard-library only, and
deterministic.

Reconsider if a rights-restricted passage must be recorded as read without
publishing its text (the current path demotes it, and a dedicated refusal for the
`quotation_permitted: false` plus `verbatim_confirmed` combination is the first
follow-up); if `verbatim_confirmed` needs to be bound to the acquired bytes by a
re-runnable extraction rather than declared; if the `asserted` demotion fires on
so many ordinary sources that it stops carrying information; or if a
content-addressed passage store becomes available and makes re-extraction local.

Revisit with a new ADR before: adding a fifth `extraction_method` or a fourth
`reading_status`; letting a model or tool set `reading_status` or author
`verbatim_text`; adding an OCR dependency or any network path to the publication
projection; or treating `verbatim_confirmed` as evidence that a reading is
correct rather than reproducible.

## Explicit deferrals

- **A content-addressed passage store.** Still absent; anchor drift and the
  ADR-0036 maintenance cost remain.
- **Binding `verbatim_text` to the acquired bytes by re-runnable extraction.**
  Declared status for this slice.
- **An OCR capability.** `unextractable` is recorded, not remedied.
- **A refusal for the rights/status contradiction.** Named above; the current
  path demotes rather than refuses.
- **Reading provenance for the Phase 4C retrieval and Phase 4D discovery
  reports.** This slice covers publication passages only.
