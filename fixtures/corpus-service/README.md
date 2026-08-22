# Corpus-service synthetic fixtures (ADR-0072 Slice 3)

Everything in this directory is project-authored synthetic test data under
`LicenseRef-AdaIvy-Synthetic-Fixture`. No document is a real publication and no
licence identifier here refers to a real grant of rights; the
`LicenseRef-AdaIvy-Synthetic-*` strings exist only so the policy-derivation
paths (admit full text, admit metadata-only, quarantine unknown) are each
exercised offline.

Contents:

- `fixture-source-rights-policy-v1.json` — the human-authored, content-hashed
  source-and-rights policy the tests derive per-document decisions from.
- `fixture-snapshot-archive-v1/` — a six-document synthetic snapshot archive:
  two admitted full-text documents, one metadata-only licence, one unknown
  licence (quarantined), one unsupported format (quarantined), one invalid
  UTF-8 body (parse-failure quarantine).
- `fixture-tranche-config-v1.json` — the operator-configured bounded tranche
  pinning the archive manifest hash and the policy content hash.

The fixtures were generated once and their content hashes are pinned literally
in `tests/test_corpus_service_store.py` and asserted by `make corpus-service`.
Regenerating them is a reviewed change, never an incidental one.
