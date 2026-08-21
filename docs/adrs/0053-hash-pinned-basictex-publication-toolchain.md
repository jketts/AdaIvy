# ADR-0053: Add a hash-pinned BasicTeX compiler for classic LaTeX papers

- **Status:** accepted for the optional publication-typesetting gate
- **Date:** 2026-08-21
- **Blueprint requirement:** correctness contract C15, Sections 15.3 and 19;
  ADR-0036 derived typesetting; ADR-0052 linked formal artifacts
- **Decision owners:** repository owner and researcher

## Context

ADR-0036 deliberately left typesetting as a named gate because no LaTeX engine
was installed. That boundary was honest, but it meant a standalone research
paper could be rendered by another PDF library while a `.tex` projection sat
beside it. The requested publication convention is stricter: the readable paper
must use classic LaTeX style and must actually be compiled from its `.tex`
source.

Installing an unversioned host `pdflatex` would make that requirement
unreproducible. The project must name the artifact, verify its bytes, record its
licenses, check the executable version, and keep network acquisition outside
the offline compile.

## Decision

Adopt BasicTeX 2026.0301 for the macOS publication gate. The acquisition record
is `config/publication-typeset-dependency-v1.json`; it pins the upstream package
at SHA-256
`19164fbfef08c30fd433f59203c8804abbbd685d3a344ef7f0ba8c1fd4157cb3`
and records the required-component licenses. BasicTeX is a TeX Live collection,
so its complete machine-readable per-package license inventory remains in the
verified distribution's `tlpkg/texlive.tlpdb`.

`make setup-typeset` is the only acquisition step. It may call Homebrew to fetch
the named cask, verifies the package hash before extraction, and installs no
system package: the TeX Live tree is copied beneath the gitignored
`work/toolchains/basictex-2026.0301/`. No compiler binary is committed.

`make check-typeset` prepends that exact tree to `PATH`. The typeset driver now
checks the first line of `pdflatex --version` against the configured exact
string before compiling. A different TeX Live release is an absent toolchain,
not a compatible pass.

Compilation remains a separate gate and remains offline. It uses the standard
`article` class with Computer Modern, `amsmath`, `amssymb`, `amsthm`, and
`hyperref`; disables shell escape; freezes the source date; compiles twice per
clean build; and refuses undefined references, undefined citations, engine
errors, or differing PDF hashes. Records remain authoritative, `.tex` remains a
projection, and PDF remains derived.

## Consequences

- AdaIvy can produce a genuine classic-LaTeX PDF without a system-wide TeX
  installation.
- The setup download is approximately 140 MB and the extracted local toolchain
  approximately 377 MB; both are outside git.
- `make check` stays dependency-free and offline. Only `setup-typeset` may use
  network access, and only `check-typeset` executes LaTeX.
- This descriptor is currently macOS-specific. A Linux toolchain requires a
  separately hashed artifact and explicit platform record rather than silently
  reusing this pin.
- Typesetting changes no proof, warrant, novelty, significance, or publication
  approval status.

## Acceptance gates

1. Setup refuses an artifact whose SHA-256 differs from the descriptor.
2. A `pdflatex` version mismatch is refused before compilation.
3. Shell escape remains disabled and environment names remain allowlisted.
4. Two clean builds must produce byte-identical PDFs.
5. The final #197 PDF must contain a link annotation to its adjacent `.lean`
   artifact and pass rendered-page visual inspection.

## Revisit trigger

Revisit before supporting another operating system, changing the TeX Live
release or package set, allowing manuscript-controlled packages, enabling shell
escape, downloading during compilation, or making typesetting part of the
ordinary dependency-free `make check` path.
