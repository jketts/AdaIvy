# Repository Instructions

This repository implements the architecture in `README.md`,
`TECHNICAL_BLUEPRINT.md`, and `NOVELTY_LANDSCAPE.md`. Read all three plus the
current ADRs before changing architecture or phase scope.

## Current phase

Phase 6 is the current completed bounded vertical slice. Phases 3B and 4A,
the Phase 5 exact commuting quantum benchmark, material-result steering, and
the Phase 6 local confirmatory/release workflow are implemented. The Phase 5
scope is exact scalar/diagonal `QD-FS-01` with deterministic tier-0 branches;
search tiers 2--4 remain disabled. The Phase 6 scope is one frozen held-out
case plus deterministic generality controls and canonical replay.

The Phase 1 domain/trust semantics, sealed Phase 2 evidence, Phase 3A memory,
sealed Phase 3B runtime, and Phase 4A rights/applicability boundaries remain
authoritative. Do not add a web UI or HTTP API, crawler, network acquisition,
embeddings, PDF parsing, model/external API calls, noncommuting SDP solver,
multi-agent or evolutionary search, automated novelty/significance assessment,
or enable higher search tiers without a later explicit request and measured
cost-adjusted gain.

## Engineering rules

- Treat external output as untrusted candidate artifacts.
- Compare every component with the file-based baseline using the same fixture.
- Never turn retrieval, experiments, or model agreement into proof status.
- Preserve failed attempts and missing-tool results in machine-readable output.
- Keep Phase 0 through Phase 6 runnable without network access.
- Pin direct runtime/development dependencies and record licenses before adding
  them. Prefer the standard library for the harness.
- Record any necessary departure from the blueprint in `docs/adrs/`; do not
  silently change the architecture.
- Use deterministic serialization, explicit schema versions, content hashes,
  bounded subprocesses, captured stdout/stderr, and no-network execution by
  default.

## Checks

Run the repository check command documented in `README.md`. Phase 5 and 6
changes must keep the complete earlier suite green and additionally pass exact
quantum feasibility/optimum checks, material-result persistence and steering,
frozen held-out capability boundaries, generality controls, restart/replay,
report consistency, and zero-network/model/API checks.
