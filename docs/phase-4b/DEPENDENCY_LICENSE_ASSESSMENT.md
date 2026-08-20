# Phase 4B Dependency and License Assessment

Status: **assessment complete; no third-party parser dependency authorized**

Assessment date: 2026-08-20. Target: CPython 3.14 on Darwin arm64. The
machine-readable snapshot is
[`parser-dependency-assessment-v1.json`](parser-dependency-assessment-v1.json).
It is an assessment record, not an install lock and not runtime authority.

## Decision

Keep the production parser boundary disabled. None of the reviewed packages
closes the Phase 4B activation evidence. The in-repo strict HTML/TeX candidate
now supplies deterministic hostile-fixture results, exact byte anchors, and a
named-Darwin sandbox bridge. A separate dependency-free strict PDF candidate
and bridge covers only classic, uncompressed, flat-page Base-14 text PDFs.
Actual-corpus authorization, portable enforcement, and strict transient-memory
enforcement remain missing. The preferred wheels did pass one disposable
hash-locked offline-install inventory spike; that result is not activation.

| Capability | Candidate | Disposition | Reason |
|---|---|---|---|
| HTML | `html5lib==1.1` | reject for Phase 4B | Standards-oriented tree construction does not retain the exact source byte spans required by the Phase 4B anchor contract. Its latest stable release is also from 2020. |
| TeX | `pylatexenc==2.11` | defer; preferred spike | Pure Python, MIT, no declared runtime dependencies, and its node model exposes source `pos`/`len`. It still needs byte/character mapping, hostile-input bounds, environment inspection, and the real sandbox gate. |
| Born-digital PDF | `pypdf==6.16.1` base install | defer; preferred spike | Pure-Python base closure on Python 3.14 and permissive license, but extracted text/layout is not an exact source-byte anchor. Its substantial recent parser-DoS history makes OS limits and adversarial calibration mandatory. |
| Born-digital PDF alternate | `pdfminer.six==20260107` | reject for this spike | Mandatory `cryptography` creates a platform/native closure; that closure was not pinned. Two recent insecure-deserialization CVEs reinforce the preference for the narrower `pypdf` base candidate. |

This decision does not install a package, add a dependency, approve PDF
parsing, or make the fixture oracle production-capable.

Separately, the repository now contains a dependency-free exact-source parser
candidate for a strict UTF-8 HTML subset and a non-expanding TeX subset. Its
multibyte byte anchors and bounds are executable, but it rejects PDF and is not
an authorized production worker. A source-bound copy of its exact semantics now
runs through the named Darwin resource sandbox, but portable and strict
transient-memory enforcement remain open. It therefore does not change the
third-party dispositions above or clear this gate. The strict PDF candidate is
also source-bound to the Darwin sandbox and avoids a third-party runtime, but
it is intentionally not a general PDF extractor.

## Disposable preferred-candidate spike

The assessment-only requirements file was downloaded with `--require-hashes`.
The two wheel digests matched, and an installation from that temporary
wheelhouse with `--no-index --require-hashes --no-deps` produced exactly
`pylatexenc==2.11` and `pypdf==6.16.1`; both packaged license files were
present. No wheel was committed.

The minimal probes failed the activation gate. pylatexenc reports Unicode
character offsets rather than byte offsets; prefix encoding can derive byte
positions, but depth 129 was accepted even though Phase 4B's limit is 128, and
depth 1000 ended in `RecursionError`. In strict mode pypdf rejected all four
sample PDF fixtures with `startxref not found`, including the nominal
born-digital fixture, and still supplied no exact original-byte location for
extracted prose. See
[`parser-dependency-spike-result-v1.json`](parser-dependency-spike-result-v1.json).

## Exact candidate identities

The identities and hashes below came from the named PyPI release JSON on the
assessment date. Links point to primary release or upstream sources.

### HTML: html5lib 1.1

- Release: [`html5lib 1.1` on PyPI](https://pypi.org/project/html5lib/1.1/),
  upstream tag
  [`1.1` at `f87487a4ada2d6cf223bdd182774a01ba3c84618`](https://github.com/html5lib/html5lib-python/tree/f87487a4ada2d6cf223bdd182774a01ba3c84618).
- Wheel: `html5lib-1.1-py2.py3-none-any.whl`, SHA-256
  `0d78f8fde1c230e99fe37986a60526d7049ed4bf8a9fadbad5f00e22e58e041d`.
- Sdist: `html5lib-1.1.tar.gz`, SHA-256
  `b2e5b40261e20f354d198eae92afc10d750afb487ed5e50f9c4eaf07c184146f`.
- Exact base closure: `six==1.17.0` wheel SHA-256
  `4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274`
  and `webencodings==0.5.1` wheel SHA-256
  `a0af1213f3c2226497a97e2b3aa01a7e4bee4f403f95be16fc9acd2947514a78`.
  Their sdist hashes are in the JSON snapshot. Optional `all`, `chardet`,
  `genshi`, and `lxml` extras are excluded.
- Licenses: html5lib and six are MIT; webencodings is BSD. These are
  permissive and compatible in principle if notices are retained. That does
  not grant rights in parsed documents.
- Native/external behavior: all three selected wheels are universal Python
  wheels. The base closure declares no native library or subprocess. html5lib
  supports optional backends, including lxml, so an adapter would have to
  prohibit extras and backend selection. No fetch is needed by the documented
  parse API, but this has not passed the Phase 4B runtime network trap.
- Security: the [NVD keyword result](https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=html5lib)
  contains CVE-2016-9909 and CVE-2016-9910, both affecting versions before
  0.99999999 and therefore not 1.1. Upstream exposes no `SECURITY.md` through
  GitHub's security-policy endpoint. “No known current CVE” is not a
  hostile-input safety claim.
- Rejection basis: html5lib produces normalized tokens/trees and may insert or
  rearrange nodes as HTML parsing requires. Its documented output does not
  carry exact source-byte spans.

### TeX: pylatexenc 2.11

- Release: [`pylatexenc 2.11` on PyPI](https://pypi.org/project/pylatexenc/2.11/),
  upstream tag
  [`v2.11` at `0e936a10f125bc3357b1a9d68de0beec5f835a3f`](https://github.com/phfaist/pylatexenc/tree/0e936a10f125bc3357b1a9d68de0beec5f835a3f).
- Wheel: `pylatexenc-2.11-py2.py3-none-any.whl`, SHA-256
  `e78e7391d6c104f1ed150e21cfaa58016cdb50aa54406a2eecb793649ffdfdd0`.
- Sdist: `pylatexenc-2.11.tar.gz`, SHA-256
  `305a072a99ce736246049c9da05841b9d718c0f7ea8888f5f596cf15cb621053`.
- Closure/license: no declared runtime dependencies; MIT. The universal wheel
  declares no native component.
- Relevant behavior: the upstream node API records character `pos` and `len`,
  making this the strongest narrow TeX candidate. It tokenizes; AdaIvy must not
  invoke TeX compilation, includes, shell escape, executable macros, or ambient
  file lookup.
- Security: the [NVD keyword query](https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=pylatexenc)
  returned zero records on the assessment date. Upstream exposes no GitHub
  security policy. This is weak negative evidence, not proof of safety.
- Deferral basis: metadata does not state a Python requirement, the wheel still
  carries Python 2/3 compatibility tags, and no Phase 4B test has yet proved
  UTF-8 byte-span conversion, bounded nesting/macro behavior, absence of file
  access, or deterministic behavior under the production worker.

### PDF: pypdf 6.16.1

- Release: [`pypdf 6.16.1` on PyPI](https://pypi.org/project/pypdf/6.16.1/),
  upstream tag
  [`6.16.1` at `1bce7a755b4b24ef9d5f2b03f9882c115bec91f2`](https://github.com/py-pdf/pypdf/tree/1bce7a755b4b24ef9d5f2b03f9882c115bec91f2).
- Wheel: `pypdf-6.16.1-py3-none-any.whl`, SHA-256
  `63fec31c4092ae50b6729beedcb469055b60d20c834bde1c402df241f371f644`.
- Sdist: `pypdf-6.16.1.tar.gz`, SHA-256
  `c4d1b43ddae921387321cf63936cd16a7743b91d2da92f165c149a195c972ba9`.
- Closure/license: on Python 3.14 with no extras, the declared runtime closure
  is only pypdf. (`typing_extensions` is conditional on Python before 3.11.)
  BSD-3-Clause. Crypto, image, font, RTL, development, and documentation extras
  are excluded. The selected wheel is universal Python.
- Native/external behavior: the base install declares no native library,
  executable, or subprocess. Optional crypto and image paths must remain
  unavailable. The library exposes attachments, annotations, actions, forms,
  images, and encrypted content; an adapter must reject prohibited features
  before surfacing text and must never execute or export them.
- Security: the [NVD pypdf query](https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=pypdf)
  shows a long sequence of CPU and memory denial-of-service issues. The most
  recent listed issues on the assessment date, CVE-2026-71852 and
  CVE-2026-71870, affect versions before 6.15.0. No result identifies 6.16.1 as
  affected, but the rapid fixes make process isolation and independent bounds
  essential. Upstream exposes no GitHub security policy.
- Deferral basis: pypdf can provide page/layout observations but not the exact
  original byte span for normalized extracted text. The hostile PDF corpus,
  strict-mode feature rejection, memory/CPU gate, and object/page mapping have
  not run against this artifact.

### Rejected PDF alternate: pdfminer.six 20260107

- Release: [`pdfminer.six 20260107` on PyPI](https://pypi.org/project/pdfminer.six/20260107/),
  upstream tag
  [`20260107` at `9e1243c4ad000bf9bbe60e81fc8dde2fccc0ed3b`](https://github.com/pdfminer/pdfminer.six/tree/9e1243c4ad000bf9bbe60e81fc8dde2fccc0ed3b).
- Wheel SHA-256:
  `366585ba97e80dffa8f00cebe303d2f381884d8637af4ce422f1df3ef38111a9`;
  sdist SHA-256:
  `96bfd431e3577a55a0efd25676968ca4ce8fd5b53f14565f85716ff363889602`.
- License: MIT, with an additional included pyHanko notice. Mandatory
  dependencies are `charset-normalizer>=2.0.0` and `cryptography>=36.0.0`.
  The latter brings platform/native behavior. Exact compatible artifacts and
  their full closure were intentionally not selected after rejection; this is
  therefore not an installable lock.
- Security: NVD records
  [CVE-2025-64512](https://nvd.nist.gov/vuln/detail/CVE-2025-64512) and
  [CVE-2025-70559](https://nvd.nist.gov/vuln/detail/CVE-2025-70559) for unsafe
  pickle-based CMap loading before 20251107 and before 20251230 respectively.
  The assessed version is later, but this history matters for an
  untrusted-document parser.

## Evidence still required before any approval

For a deferred candidate and its complete closure:

1. Select exact artifacts for the named target, verify wheel and sdist contents
   and every file-level license/notice, and create a real `--require-hashes`
   lock. An assessment manifest is not that lock.
2. Install only from a reviewed local wheelhouse into a disposable environment
   using `pip --require-hashes --no-index`; prove exact installed-inventory
   equality and absence/wrong-version failure.
3. Run all Phase 4B ordinary, warning, malformed, active-content, encrypted,
   expansion, nesting, count, timeout, and one-over-limit fixtures. Preserve
   failures as records; admit zero false parser successes.
4. Prove exact UTF-8 byte/page/object anchors through restart and replay. Do not
   substitute normalized-text positions for source-byte evidence.
5. Demonstrate the actual worker has OS-enforced no-network, filesystem,
   process, file, memory, CPU, wall-time, environment, and dynamic-loading
   controls. An exit code or wrapper request is not evidence of enforcement.
6. Scan imports and artifact contents for native libraries, executables,
   subprocesses, sockets, plugin discovery, data files, environment reads, and
   optional imports; document each allowed path and removal test.
7. Re-query upstream security releases and NVD immediately before pinning.

## Named Darwin sandbox evidence

The fixed Darwin/arm64 probe now clears an inherited secret and demonstrates
actual OS denials for UDP network access, path-backed writes, process forks,
and reads beneath unapproved `/Users` and `/private` paths. The feasible gate
hashes both the sandbox profile and its bounded results. This is useful
named-platform evidence. A separate protocol-connected fixture worker now
demonstrates bounded wall time, output, CPU, open files, process creation, and
file size with per-process CPU measurements on Darwin; RSS is a sampled
tripwire rather than strict transient-spike enforcement. That fixture is not the
only evidence now: source-bound strict HTML, TeX, and PDF bridges also run
successfully. No portable claim is made, RSS remains sampled, and these narrow
profiles are not production-authorized. The production parser sandbox blocker
therefore remains.

## Source-rights boundary

Permissive parser licenses do not grant acquisition, retention, parsing,
excerpting, redistribution, publication, embedding, or model-context rights for
a document. Every output remains an untrusted candidate governed by its Phase
4A rights and applicability decisions.

## Gate consequence

The standard-library acquisition policy, deterministic fake transport,
records, canonical serialization, and harness remain dependency-free. The
disabled production worker must continue to return `missing_dependency` when no
explicit worker is supplied. It must not auto-download, use a host parser, or
fall back to the fixture oracle. `phase4b/live_transport.py` remains a separate
explicit-human-permit boundary; this assessment does not authorize acquisition.
