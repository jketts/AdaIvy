# PaperQA Phase 0 probe

The probe is intentionally non-agentic. It checks whether the `paperqa` package
is importable and records its installed version. It does not invoke a model,
fetch metadata, crawl sources, or use credentials. If available in a separately
pinned environment, a later run may ingest the local
`fixtures/phase0/source/even-definition.txt` and export evidence candidates;
those candidates remain distinct from applicability and proof.
