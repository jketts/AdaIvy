# Repository Instructions

This repository implements the architecture in `README.md`,
`TECHNICAL_BLUEPRINT.md`, and `NOVELTY_LANDSCAPE.md`. Read all three plus the
current ADRs before changing architecture or phase scope.

## Current phase

Phase 3A is the completed bounded, manually supplied research-memory vertical
slice. Stop before Phase 3B unless a later explicit request authorizes it.
Allowed deliverables are immutable local source/provenance records, opaque
metadata-only URI records, the internal `plain-text-v1` UTF-8 parser,
quarantine records, exact source spans, source-derived evidence proposals,
deterministic SQLite FTS5/BM25 retrieval, bounded evidence packs, citation
validation, canonical interchange, CLI/reporting, and acceptance evidence.

The Phase 1 domain and trust-policy semantics and sealed Phase 2 evidence remain
authoritative. Do not add a web UI or HTTP API, crawler, network acquisition,
embeddings or an embedding-provider port, PDF parsing, model or external API
calls, symbolic/formal/numerical tools, multi-agent or evolutionary search,
automated novelty or significance assessment, Phase 3B/4 features, or the
quantum convergence implementation.

## Engineering rules

- Treat external output as untrusted candidate artifacts.
- Compare every component with the file-based baseline using the same fixture.
- Never turn retrieval, experiments, or model agreement into proof status.
- Preserve failed attempts and missing-tool results in machine-readable output.
- Keep Phase 0 through Phase 3A runnable without network access.
- Pin direct runtime/development dependencies and record licenses before adding
  them. Prefer the standard library for the harness.
- Record any necessary departure from the blueprint in `docs/adrs/`; do not
  silently change the architecture.
- Use deterministic serialization, explicit schema versions, content hashes,
  bounded subprocesses, captured stdout/stderr, and no-network execution by
  default.

## Checks

Run the repository check command documented in `README.md`. Phase 3A is not
complete unless every Phase 0–2 test and validator still passes and Phase 3A
schema, migration, ingestion, quarantine, provenance, retrieval, citation,
interchange, restart/replay, metrics, report-consistency, and zero-network/API
checks pass. Acceptance requires the frozen ADR-0013 retrieval thresholds over
three repeats and one restart.
