# ADR-0071: Resume terminal campaign finalization and emit an automatic draft

- **Status:** accepted and implemented 22 August 2026
- **Date:** 2026-08-22
- **Blueprint requirement:** C8, C9, C10, C15; ADR-0036, ADR-0047,
  ADR-0056, ADR-0057, and ADR-0065
- **Decision owners:** repository owner and researcher

## Context

`campaign run` closed and persisted its ledger but stopped before producing a
reader-facing artifact. The existing publication projection could render a
strict manuscript, yet required a separately authored manuscript and separate
command. An interruption after the terminal ledger was written therefore left
deterministic finalization unfinished.

The current ledger is not sufficient for safe continuation in the middle of a
paid campaign. Planner history, accepted raw action envelopes, selection state,
non-secret live configuration, and request intent are not checkpointed after
each action. Re-running the current runner would repeat activation and may
repeat a paid request. Calling that operation "resume" would violate C10.

## Decision

Every terminal `campaign run`, including an activation-only terminal failure,
attempts a deterministic publication projection after the canonical campaign
ledger is durable. It writes `publication-draft/paper.tex`, the publication
ledger and records, `MANIFEST.json`, and a top-level
`publication-draft.json`. The draft embeds the exact campaign export and
derived facts.

The projection is deliberately claim-free. A campaign export does not yet
contain the typed mathematical claims, citations, applicability decisions,
formal attestations, or representation bridges required by the publication
schema. The draft therefore records one open formalization obligation, creates
no warrant, leaves novelty and significance `not_assessed`, and carries null
publication approval. A projection failure is reported but cannot change the
already durable campaign outcome.

`adaivy campaign resume ROOT` is added with a narrow, explicit scope. It:

1. loads and verifies an existing terminal campaign, target, configuration,
   novelty record, derived facts, and usage;
2. generates a missing draft or verifies the existing bundle; and
3. performs no provider, network, tool, or subprocess work.

It does **not** continue a partially executed research loop. A root without a
complete verified `campaign.json` is refused. Genuine mid-campaign continuation
requires an append-only action checkpoint chain, paid-request intent records,
planner and selection-state hydration, activation reuse, and a single-writer
lock. That work remains in the end-to-end runtime plan.

The automatic path emits LaTeX but does not compile it. This preserves the
offline campaign gate and avoids making a local executable lookup or process
launch implicit in `make check`. PDF production remains the explicit pinned
`publication typeset`/`publication build` gate from ADR-0056.

## Consequences

- A completed campaign always attempts to leave a readable, provenance-backed
  LaTeX status draft without a second authored summary.
- Re-entering terminal finalization is idempotent and never repeats paid work.
- Existing report bytes are verified; a mismatched or tampered bundle is
  refused rather than overwritten.
- This slice does not claim crash-safe mid-campaign resumption or automatic
  conversion of model prose into a mathematical publication claim.

## Validation and revisit trigger

The acceptance suite demonstrates automatic `paper.tex` generation, null
approval, zero claims, bundle verification, byte-preserving terminal re-entry,
and zero provider, network, or subprocess effects during `resume`.

Revisit before enabling mid-campaign continuation, automatic PDF compilation in
the campaign command, or promotion of campaign artifacts into typed publication
claims.
