# Phase 4B Bounded Implementation Prompt

Status: accepted with ADR-0028

Implement only ADR-0028: authorized HTTPS acquisition plus isolated parsing of
structured HTML, bounded TeX/LaTeX source, and born-digital PDF.

Read `README.md`, `TECHNICAL_BLUEPRINT.md`, `NOVELTY_LANDSCAPE.md`, all ADRs,
and every file in `docs/phase-4b/` before editing production code.

## Required implementation

- Add versioned acquisition request, attempt, response, redirect, policy,
  parser-run, parse-proposal, warning, anchor, and quarantine records.
- Reuse Phase 4A trusted principals, per-use rights, source lifecycle,
  deletable per-source objects, and human applicability. Do not duplicate or
  reinterpret their authority.
- Put network and parsers behind narrow ports. Network defaults off. Live HTTPS
  GET requires an explicit bounded run and exact origin approval.
- Provide a deterministic fake resolver/transport for all acceptance tests.
- Store fetched source bytes and reconstructive parse plaintext only in the
  Phase 4 per-source deletable object.
- Run every rich parser in the isolated no-network resource boundary specified
  by the security inventory. TeX must never compile or execute.
- Preserve original bytes, parser/version identity, warnings, transformations,
  and exact byte/page/object anchors. Quarantine any load-bearing segment that
  cannot be mapped exactly.
- Persist failures and missing parser/dependency outcomes as machine-readable
  non-success records.
- Add a canonical Phase 4B export/import/replay whose semantic identity excludes
  operational time, PID, temporary path, elapsed duration, and scheduling.
- Add one acceptance suite implementing every threshold and forbidden outcome
  in this package.

## Dependency precondition

Before importing any third-party parser, update the Phase 4B dependency
assessment with exact wheel filenames, SHA-256 hashes, direct/transitive
licenses, platform tags, offline `--require-hashes` installation, import scan,
and removal path. If that evidence is unavailable, implement the port and an
explicit `missing_dependency` result; do not silently fall back or weaken the
format claim.

## Forbidden implementation

Do not add Phase 4C embeddings/vector/hybrid retrieval, OCR, archives, browser
execution, ambient proxies, credential forwarding, automated applicability,
model/API calls, novelty/significance automation, scheduler, UI/HTTP API,
noncommuting SDP, or search tiers 2--4. Do not write fetched or parsed content
to Phase 3A, logs, immutable exports, persistent indexes, or global CAS.

Do not use live network in tests. Do not treat successful parsing, retrieval,
formal checking, or model agreement as proof or applicability. Do not change
existing files merely to make the new suite pass without a separately reviewed
ADR.

## Completion

Run `make check`, the Phase 4 gate command, the Phase 4B acceptance suite,
sealed checks when their exact environments are available, repository invariant
tests, credential scans, protected-evidence verification, `git diff --check`,
and Markdown link checks. Report unavailable environments honestly.
