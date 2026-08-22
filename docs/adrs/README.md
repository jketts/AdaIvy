# Architecture Decision Records

ADRs preserve decision history. Rejected and superseded records are not deleted;
their status or a later ADR identifies the current decision. Current runtime
capability is summarized separately in
[`../CAPABILITY_STATUS.md`](../CAPABILITY_STATUS.md).

## Current integration decisions

- ADR-0029: central research lead and selectively activated search complexity
- ADR-0047: bounded central-lead runtime
- ADR-0051: bounded public scholarly web discovery (Crossref, superseded in
  part by ADR-0068 and ADR-0072)
- ADR-0055: two human novelty checkpoints; the `before_research` check is
  superseded in part by ADR-0072 for campaign runs, the `before_announcement`
  check stands
- ADR-0057: provenance-closed research campaign
- ADR-0064: processor-bound embedding rights; the per-document human-authorship
  mechanism is superseded in part by ADR-0072
- ADR-0065: campaign operator entrypoint
- ADR-0066: bounded campaign experiment sandbox
- ADR-0067: bounded corpus ingestion
- ADR-0068: accepted depth-one discovery-result following; implemented in the
  ADR-0075 offline end-to-end runtime
- ADR-0069: embedding provider and immutable vector artifacts
- ADR-0070: fixture-scoped semantic retrieval signal
- ADR-0071: terminal campaign resume and automatic unapproved LaTeX draft
- ADR-0072: end-to-end campaign authority under one initial authorization;
  implemented by the bounded slices while activating no live external service,
  and superseding named clauses of ADR-0047,
  ADR-0051, ADR-0055, ADR-0064, ADR-0067, ADR-0068, and ADR-0070
- ADR-0073: canonical identifier for the implemented campaign experiment and
  verifier-router wiring; supersedes the identifier authority of the historical
  parallel `0072-campaign-experiment-and-verifier-wiring.md`
- ADR-0074: persistent corpus-backed retrieval projections and partition-bound
  query/evidence replay
- ADR-0075: action-level checkpoints and the single-command offline end-to-end
  campaign runtime
- ADR-0076: closes the end-to-end acceptance path with consumed v2 planner
  actions, ordered refresh/retrieval, exact model-context rights, refute/repair/
  verify continuation, safe takedown authority, sealed resume configuration,
  cross-campaign vector reuse, and provenance-closed report generation

The end-to-end integration is documented in
[`../END_TO_END_RESEARCH_RUNTIME_PLAN.md`](../END_TO_END_RESEARCH_RUNTIME_PLAN.md).
ADR-0072 is the superseding decision that plan required before implementation;
Slices 2–8 now have offline acceptance coverage; live provider, snapshot,
container, and Lean execution retain their separate explicit gates.

## Duplicate ADR numbers

Two historical records use `0038`. Their filenames are the stable identifiers:

- `0038-provider-selection-on-the-run-path.md`
- `0038-phase2-secret-and-setting-file-split.md`

Do not cite bare “ADR-0038.” Cite the complete filename or descriptive title.
Renumbering either file would break historical references and recorded hashes.

Two parallel 2026-08-22 branches also produced distinct ADR-0072 records. The
end-to-end campaign-authority record is the current ADR-0072. The historical
campaign experiment/verifier record is retained under its original filename;
ADR-0073 is its canonical successor.
