# Repository Instructions

This repository implements the architecture in `README.md`,
`TECHNICAL_BLUEPRINT.md`, and `NOVELTY_LANDSCAPE.md`. Read all three plus the
current ADRs before changing architecture or phase scope.

## Current phase

Phase 2 is the durable workspace and one bounded baseline model loop. Allowed
deliverables are persistence/artifact/job adapters behind ports, versioned
migrations, a provider-neutral model gateway with deterministic and opt-in
live adapters, one proposer/verifier workflow, one filesystem/process
interchange adapter, minimal CLI extensions, and durable replay evidence.

The Phase 1 domain and trust-policy semantics remain the authority. Do not add
a web UI or HTTP API, crawler or retrieval stack, symbolic/formal/numerical
tool integration, multi-agent or evolutionary search, automated novelty or
significance assessment, PostgreSQL without measured need and an ADR, Phase 3
features, or the quantum convergence implementation in Phase 2.

## Engineering rules

- Treat external output as untrusted candidate artifacts.
- Compare every component with the file-based baseline using the same fixture.
- Never turn retrieval, experiments, or model agreement into proof status.
- Preserve failed attempts and missing-tool results in machine-readable output.
- Keep Phase 0, Phase 1, and the deterministic Phase 2 path runnable without
  network access.
- Pin direct runtime/development dependencies and record licenses before adding
  them. Prefer the standard library for the harness.
- Record any necessary departure from the blueprint in `docs/adrs/`; do not
  silently change the architecture.
- Use deterministic serialization, explicit schema versions, content hashes,
  bounded subprocesses, captured stdout/stderr, and no-network execution by
  default.

## Checks

Run the repository check command documented in `README.md`. Phase 2 is not
complete unless Phase 0 and Phase 1 compatibility checks plus Phase 2
migration, recovery, budget, model-boundary, context-isolation,
external-package, CLI, replay, and report-consistency tests pass. A configured
live-provider demonstration is an explicit acceptance gate; when credentials
are absent, record that gate as blocked rather than fabricating success.
