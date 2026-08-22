# Documentation Index

## Current documents

- [`../README.md`](../README.md) — project overview and quick start
- [`CAPABILITY_STATUS.md`](CAPABILITY_STATUS.md) — canonical current
  implementation and wiring status
- [`END_TO_END_RESEARCH_RUNTIME_PLAN.md`](END_TO_END_RESEARCH_RUNTIME_PLAN.md) —
  proposed integration roadmap
- [`../TECHNICAL_BLUEPRINT.md`](../TECHNICAL_BLUEPRINT.md) — target architecture
  and correctness contract
- [`TECHNICAL_DETAILS.md`](TECHNICAL_DETAILS.md) — current component commands
  and bounded behavior
- [`MATHEMATICS_RUNBOOK.md`](MATHEMATICS_RUNBOOK.md) — shared mathematics
  problem procedure for host harnesses
- [`adrs/README.md`](adrs/README.md) — ADR policy and current integration
  decisions

## Dated research inputs

- [`../NOVELTY_LANDSCAPE.md`](../NOVELTY_LANDSCAPE.md) — prior-art review dated
  19 August 2026
- [`TARGET_LANDSCAPE_2026-08.md`](TARGET_LANDSCAPE_2026-08.md) — dated target
  survey
- [`RESEARCH_TARGET_DOSSIER_2026-08.md`](RESEARCH_TARGET_DOSSIER_2026-08.md) —
  dated target dossier

These documents inform decisions but do not state current runtime capability.

## Historical phase evidence

Directories named `phase-*` contain the plans, prompts, threat models,
acceptance thresholds, dependency assessments, and reports for bounded slices.
They are retained because ADRs and recorded gate evidence cite their paths and,
in some cases, their exact hashes.

Treat these files as **archived, phase-local, and non-normative** unless a
current ADR explicitly names one as an active contract. Do not infer global
runtime capability from an old phase plan or implementation prompt.

## Architecture decisions

ADRs are append-only decision history. A later ADR may supersede a decision,
but cleanup does not delete the earlier record. Current runtime status belongs
in `CAPABILITY_STATUS.md`, not in retroactive rewrites of historical evidence.
