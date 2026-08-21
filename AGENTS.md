# Repository Instructions

This repository implements the architecture in `README.md`,
`TECHNICAL_BLUEPRINT.md`, and `NOVELTY_LANDSCAPE.md`. Read all three plus the
current ADRs before changing architecture or phase scope.

## Current phase

Bounded Phase 4B authorized acquisition and exact-source parsing (ADR-0028) is
the current work. Its offline acquisition, persistence, deletion, replay,
strict HTML/TeX/PDF candidates, and exact Linux/arm64 OCI parser gate are
implemented. The digest-pinned OCI gate reproduces all twelve parser fixtures
with zero false admissions and demonstrates kernel memory, CPU, process, file,
network-none, read-only-root, noexec-temp, and ambient-secret controls. Network
remains off by default. The separately acknowledged live HTTPS gate is the
final activation step; its absence must never be counted as a pass.

Phases 0 through 6 remain implemented and authoritative. The Phase 5 scope is
still exact scalar/diagonal `QD-FS-01` with deterministic tier-0 branches and
search tiers 2--4 disabled; the Phase 6 scope is still one frozen held-out case
plus deterministic generality controls and canonical replay.

ADR-0026 records the accepted delivery order for the remaining work after
Phase 4B: Phase 4C hybrid retrieval, then the noncommuting Phase 5 expansion,
then Phase 6 external evaluation.

ADR-0029 refines the target orchestration architecture without enabling a new
runtime. The baseline is one coherent long-horizon research lead plus a
centralized verifier, with literature, experiments, multiple branches, and
incremental formalization available inside that central loop. Higher search
tiers remain disabled. Bounded specialists require a recorded prediction and
measured retention gain in verified progress per unit cost; evolutionary search
additionally requires cheap reliable verifier-backed fitness and adversarial
calibration. Never substitute an always-on hierarchical swarm.

The Phase 1 domain/trust semantics, sealed Phase 2 evidence, Phase 3A memory,
sealed Phase 3B runtime, and Phase 4A rights/applicability boundaries remain
authoritative. Do not add a web UI or HTTP API, crawler, network acquisition,
embeddings, PDF parsing, model/external API calls, noncommuting SDP solver,
multi-agent or evolutionary search, automated novelty/significance assessment,
or enable higher search tiers without a later explicit implementation request,
the ADR-0029 activation evidence, and measured cost-adjusted verified gain.

Two capabilities the synthesis slice supplies are boundaries, not fixes, and
must not be assumed to hold elsewhere. `synthesis/applicability.py` resolves the
effective Phase 4A review because Phase 4A itself has no resolver; if Phase 4A
later adopts its own rule the two must be reconciled. The separation-of-duty
check in `synthesis/material.py` applies only to that module's surfacing path,
because sealed Phase 5 accepts an identical originating and creating principal.

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
- Never let vectors from different providers or different embedding models share
  a similarity space. If a second model provider is admitted, partition any
  vector projection by `(provider, model_identifier, dimension, normalization)`,
  rebuild rather than backfill on a provider or model change, and bind stored
  vector bytes into canonical identity so a deterministic rebuild replays
  artifacts instead of re-calling the provider. Mixing degrades retrieval
  silently rather than failing. See `TECHNICAL_BLUEPRINT.md` Section 12.2.1.
- Use deterministic serialization, explicit schema versions, content hashes,
  bounded subprocesses, captured stdout/stderr, and no-network execution by
  default.

## Checks

Run `make check`. It is the single offline entrypoint and needs no network, no
model provider, no container runtime, and no third-party package. Targets that
need more are separate and named for what they need: `make check-sealed`
requires the ADR-0016 v5 image, `make check-gate` requires the disposable
pinned Draft 2020-12 validator environment, and `make check-all` runs both.

Changes must keep the complete earlier suite green and additionally pass exact
quantum feasibility/optimum checks, material-result persistence and steering,
frozen held-out capability boundaries, generality controls, restart/replay,
report consistency, and zero-network/model/API checks.

Under ADR-0026 each new slice ships one ADR plus an acceptance suite that
encodes its thresholds as executable assertions, rather than a separate
threshold inventory. A scenario's forbidden outcomes must be demonstrated
impossible, not merely left untested. `tests/test_repository_invariants.py`
enforces the standing structural properties: no module-level network or
third-party import in `src/`, and every lazy third-party load declared as a
gated boundary.
