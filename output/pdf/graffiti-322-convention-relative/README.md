# AdaIvy publication bundle

The records in `records/` are the artifact of record. `paper.tex` is a
projection of them and `paper.pdf` is a build product of `paper.tex`. Nothing
flows back.

- `records/manuscript.json` is the canonical record set the projection read.
- `records/ledger.json` names every content block in `paper.tex` and the records
  backing it. `paper.tex` is exactly the frozen template plus these blocks.
- `records/evidence.json` records the computed evidence class of every claim and
  why. No input field selects an environment.
- `records/prior-art.json` records the derived prior-result/report
  classification, read from the manuscript's own prior-art engagement record and
  only then from an approval. An identified matching proof or refutation cannot be
  hidden behind the broader `novelty: not_assessed` status, and an unapproved
  draft carrying a real classification no longer reports `not_assessed`.
- `records/probes.json` records the falsifiability probes: single-field
  mutations of the manuscript, each of which must produce a named refusal or a
  named demotion.
- AI-authored builds also carry `records/campaign.json` and
  `records/publication-campaign-link.json`, the verified operational ledger and
  the exact claim/certificate join used to derive attribution and disclosure.
- `lean/` holds the content-hashed Lean source for every solved claim. Each
  paper claim links to its file and states whether checking is pending, failed,
  or kernel-checked.
- `build.json` pins the typesetting invocation. `typeset_status` is
  `not_typeset` until a compile has actually run; its absence is never a pass.
- `MANIFEST.json` hashes every file above, plus the manuscript, template and
  document hashes.

To re-derive the document:

    python3 -m math_research.cli publication render <manuscript.json> --output-dir <dir>

`document_hash` in `MANIFEST.json` must match. To typeset, see `build.json`.
