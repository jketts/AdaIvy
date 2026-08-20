# Phase 4B parser candidate and license assessment

- **Status:** evaluation spike; no adoption decision
- **Assessed:** 2026-08-20
- **Runtime effect:** none; the executable spike remains standard-library only
- **Sources:** primary project documentation and repositories linked below

No package, binary, model, or trained-data file has been downloaded or added.
Consequently this report records candidate capability and apparent upstream
licensing, not the pinned-wheel, complete transitive-license, vulnerability,
hash, or reproducibility assessment required by ADR-0026 for adoption.

## Staged recommendation

| Stage | Representation | Candidate | Upstream license signal | Finding |
|---|---|---|---|---|
| 0, current | Restricted structured HTML | Python `html.parser` contract baseline | Python standard library / PSF terms already in the runtime | Retain only as a fixture oracle. It is insufficient for general HTML5 parsing, but useful for proving byte-lineage and active-content rejection. |
| 1 | Authoritative structured HTML and MathML | `lxml` | BSD-family for lxml, with ElementTree/PSF exceptions; official wheels bundle zlib, iconv, libxml2, libxslt, and libexslt under additional licenses | Plausible candidate, not approved. Evaluate exact HTML/MathML spans and a separately maintained allowlist. Never use `huge_tree`; disable network/entity resolution; reject active/external content before import. |
| 2 | Non-executing TeX/LaTeX | `plasTeX` | MIT classifier; documented dependencies include Jinja2, Unidecode, Pillow, and typing-extensions | Defer/high risk. Its normal processing expands macros, can load TeX packages, locate them with `kpsewhich`, import plugins, and render. A future spike must prove package loading, plugins, renderers, imagers, filesystem access, and subprocesses are disabled inside a bounded sandbox. The lexical profile here remains the safer baseline. |
| 3 | Born-digital PDF | `pypdf` | BSD-3-Clause | Most promising initial PDF candidate, but not approved. Use text extraction only, reject encryption/active/embedded features, pre-bound content streams, isolate in a bounded subprocess, and preserve operator-level spans rather than treating extracted reading order as authoritative. |
| 4 | Scanned PDF/image OCR | Tesseract 5.x CLI plus explicitly selected trained data | Apache-2.0 for Tesseract; it uses Leptonica (upstream describes BSD 2-clause); official tessdata repositories also publish Apache-2.0 licenses | Defer until born-digital parsing is stable. Treat OCR as attributed derived output with image/model/config hashes and independent review. It can never manufacture an exact original-text span. |

## Primary-source findings

### HTML: lxml

The [official lxml repository](https://github.com/lxml/lxml) describes lxml as
an XML/HTML toolkit. Its [upstream license inventory](https://github.com/lxml/lxml/blob/master/LICENSES.txt)
records the BSD-family project license, ElementTree and PSF-derived portions,
and the libraries/licenses bundled into official binary wheels. This is a
larger compliance surface than one top-level SPDX label.

The upstream [change history](https://github.com/lxml/lxml/blob/master/CHANGES.txt)
also records recent entity-resolution and link-attribute security fixes. That
evidence rules out permissive/default parsing as an AdaIvy trust boundary. An
adoption proposal must select a stable release, pin exact platform wheels and
hashes, inventory every bundled library, and rerun hostile SVG/MathML link and
entity fixtures.

### TeX/LaTeX: plasTeX

The [plasTeX documentation](https://plastex.github.io/plastex/) describes a
Python LaTeX processor producing a DOM-like object. Its
[general options](https://plastex.github.io/plastex/plastex/sec-general-options.html)
show that package loading is enabled by default, `kpsewhich` may be used, and
plugins/renderers are configurable. The
[upstream package metadata](https://github.com/plastex/plastex/blob/master/setup.cfg)
reports version 3.1, an MIT classifier, and direct dependencies on Jinja2,
Unidecode, Pillow, and typing-extensions.

These capabilities conflict with the required non-executing profile unless
they are explicitly disabled and adversarially verified. This assessment does
not assume that parsing TeX is safe merely because the implementation is
Python. No plasTeX dependency should enter production until a separate sandbox
spike demonstrates no file lookup, package loading, plugin import, rendering,
imaging, subprocess execution, or unbounded macro expansion.

### Born-digital PDF: pypdf

The current [pypdf text-extraction documentation](https://pypdf.readthedocs.io/en/latest/user/extract-text.html)
explains that PDF lacks a semantic layer, reading order and whitespace are
ambiguous, and image-only pages need OCR. Earlier official documentation also
records that content-stream extraction can consume far more memory than the
source file size and recommends bounding the decoded stream before extraction.
The [upstream license](https://github.com/py-pdf/pypdf/blob/main/LICENSE) is
BSD-3-Clause, and the project security policy applies fixes to the latest
release.

This makes pypdf appropriate for a later born-digital candidate adapter, not a
source-of-truth normalizer. Any extracted structure remains a representation
proposal tied to PDF operators and original bytes. The adoption gate must test
malformed cross-references, unterminated images, oversized decoded streams,
fonts/ToUnicode maps, encryption, actions, attachments, and deterministic
failure retention.

### OCR: Tesseract

The [official Tesseract manual](https://tesseract-ocr.github.io/tessdoc/Home.html)
identifies the 5.x engine and Apache-2.0 license. The
[upstream repository](https://github.com/tesseract-ocr/tesseract) documents the
CLI/API, the Leptonica dependency, and the separate trained-data requirement;
the [installation guide](https://github.com/tesseract-ocr/tessdoc/blob/main/Installation.md)
likewise treats engine and language data as separate installation components.

A future OCR adapter therefore needs exact hashes and licenses for the engine,
Leptonica and all of its image dependencies, the selected trained-data files,
and configuration. It should run as a no-network bounded subprocess and retain
stdout, stderr, exit status, timeout, missing-tool results, and the unmodified
input image. OCR agreement with another representation is evidence for review,
never proof or permission to invent a source span.

## Adoption gates still missing

Before any candidate can move from this spike into production:

1. Freeze one version/platform set and record exact wheel, sdist, binary, model,
   and trained-data SHA-256 values.
2. Inventory direct, transitive, bundled, and optional dependencies and their
   license/notice obligations; exclude unused extras.
3. Install from an offline `--require-hashes` manifest or a content-addressed
   binary acquisition record.
4. Run each parser in a bounded, no-network, minimal-environment subprocess and
   preserve failures, timeouts, stdout, and stderr as candidate artifacts.
5. Demonstrate exact original-byte lineage, bounded decoded content, stable
   spans, deterministic replay, quarantine, and representation disagreement on
   the actual adapter path.
6. Reconcile parsed-source use with the effective Phase 4A rights decision for
   parsing, retention, excerpting, embedding, model context, and publication.

