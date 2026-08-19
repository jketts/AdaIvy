# Proposed Phase 3A Dependency and Licensing Assessment

Status: design proposal only  
Date: 2026-08-19

No dependency is added by this design task.

## Baseline dependencies

| Component | Proposed role | Current evidence | Decision |
|---|---|---|---|
| Python standard library | Domain records, hashing, JSON, files, jobs | Existing Phase 0–2 offline baseline | Retain |
| `sqlite3` / SQLite FTS5 | Durable adapter and derived BM25 index | Current `.venv` Python reports SQLite 3.53.3 and FTS5 enabled | Wrap behind ports; record runtime/version/compile option |
| Existing CAS and SQLite workspace | Source/derived artifacts, events, jobs, budgets | Accepted Phase 2 implementation and tests | Extend through new ports/migration; never alter accepted v2/v3 DBs |
| OpenAI SDK 3.3.0 | Optional later model exercise only | Existing Apache-2.0 Phase 2 pin and wheel hash | Not required for Phase 3A acceptance; no call in baseline |

SQLite is public-domain software and Python is distributed under PSF-compatible
terms, but a release inventory must record the actual runtime distribution and
not infer rights for bundled operating-system components.

## Parser candidates requiring a bounded spike

| Candidate | Likely license requiring primary-source verification | Strength | Risk/decision |
|---|---|---|---|
| `pypdf` | BSD-3-Clause | Small pure-Python page text extraction | Candidate for smallest PDF path; coordinate fidelity/equations may fail |
| `pdfminer.six` | MIT | Character/layout-oriented extraction | Candidate if stable location mapping materially beats `pypdf`; larger surface |
| `pdfplumber` | MIT plus transitive dependencies | Higher-level page/layout access | Evaluate only if lower-level options cannot meet span tests |
| GROBID | Apache-2.0 plus JVM/runtime dependencies | Strong scholarly structure/metadata | Defer unless the small parser spike fails; operationally too large by default |
| PyMuPDF | AGPL/commercial licensing model | Strong rendering/layout | Do not adopt without explicit legal decision and distribution analysis |

These license labels are design-review recollections, not a completed license
inventory. Before adoption, record the exact version, official license file,
upstream URL, artifact hash, transitive lock, owner, reason, and removal path as
required by the Phase 0 dependency policy. A package is rejected if its current
primary-source license or transitive obligations are incompatible.

The preferred experiment compares the standard-library file/text baseline,
`pypdf`, and one layout-oriented candidate on the same four-source gold corpus.
Select the smallest option that preserves stable page/span mappings and explicit
warnings. Parser output remains untrusted regardless of license or score.

## Gold-corpus rights

The repository does not currently contain a license or a source-rights
manifest. The redistribution license for the paper identified as
arXiv:quant-ph/0201109 is not recorded locally. ArXiv availability does not by
itself establish permission to redistribute the paper bytes. The related source
has not yet been selected.

Before committing source bytes:

1. record the exact source version/content hash;
2. record the paper-level license or explicit redistribution permission from a
   primary source;
3. preserve required attribution and notices;
4. define whether full text, excerpts, derived text, and model contexts are
   permitted separately; and
5. obtain human approval.

If redistribution remains unresolved, keep paper bytes outside Git, import them
manually into the local CAS, and version only a metadata/expected-hash manifest.
Offline acceptance is then conditional on operator-provided licensed bytes and
must report a blocker when they are absent.

Repository-authored malformed, contradictory, and prompt-injection fixtures
should carry explicit fixture licensing once the repository license is chosen.

## Publishing gate

The GitHub remote is private. Do not make it public, create a public release, or
publish a corpus package until both the repository license and each source's
redistribution/usage rights are resolved. This design makes no licensing
decision on the operator's behalf.
