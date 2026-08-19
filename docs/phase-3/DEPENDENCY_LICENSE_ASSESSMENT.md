# Phase 3A Dependency and Licensing Assessment

Status: implemented for bounded Phase 3A
Date: 2026-08-19

No dependency is added by Phase 3A.

## Baseline dependencies

| Component | Proposed role | Current evidence | Decision |
|---|---|---|---|
| Python standard library | Domain records, hashing, JSON, files, jobs | Existing Phase 0–2 offline baseline | Retain |
| `sqlite3` / SQLite FTS5 | Durable adapter and derived BM25 index | Current `.venv` Python reports SQLite 3.53.3 and FTS5 enabled | Wrap behind ports; record runtime/version/compile option |
| Existing CAS and SQLite workspace | Source/derived artifacts, events, jobs, budgets | Accepted Phase 2 implementation and tests | Extend through new ports/migration; never alter accepted v2/v3 DBs |
| OpenAI SDK 3.3.0 | Existing Phase 2 adapter only | Existing Apache-2.0 Phase 2 pin and wheel hash | Phase 3A does not import or call it |

SQLite is public-domain software and Python is distributed under PSF-compatible
terms, but a release inventory must record the actual runtime distribution and
not infer rights for bundled operating-system components.

## Parser decision

Phase 3A uses the internal standard-library parser `plain-text-v1`, version
`1.0.0`, and accepts valid UTF-8 `text/plain` only. PDFs and every unsupported
media type are quarantined without extraction. PDF/OCR/parser packages and
their license evaluations are deferred to Phase 4. Parser output remains
derived and cannot award mathematical trust.

## Gold-corpus rights

The repository does not currently contain a license or a source-rights
manifest. The redistribution license for the paper identified as
arXiv:quant-ph/0201109 is not recorded locally. ArXiv availability does not by
itself establish permission to redistribute the paper bytes. The real related
academic source has not yet been selected.

Before committing source bytes:

1. record the exact source version/content hash;
2. record the paper-level license or explicit redistribution permission from a
   primary source;
3. preserve required attribution and notices;
4. define whether full text, excerpts, derived text, and model contexts are
   permitted separately; and
5. obtain human approval.

While redistribution remains unresolved, keep paper bytes outside Git and
version only a metadata-only record whose `content_hash` is null. Phase 3A does
not require or parse operator-provided academic PDFs; that demonstration is
deferred to Phase 4.

Project-authored primary, related, malformed, contradictory, and
prompt-injection fixtures are used only in the private repository acceptance
suite. Their frozen manifest records
`LicenseRef-AdaIvy-Synthetic-Fixture`, contributor copyright notice, allowed
redistribution, and explicit private-evaluation/local-retrieval/evidence-pack
rights. This internal fixture license reference does not choose a public
repository license or grant rights for any academic corpus.

## Publishing gate

The GitHub remote is private. Do not make it public, create a public release, or
publish a corpus package until both the repository license and each source's
redistribution/usage rights are resolved. This design makes no licensing
decision on the operator's behalf.
