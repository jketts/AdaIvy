# Phase 1 Architecture Conflict Assessment

## Conflicts found

1. `AGENTS.md` still declared Phase 0 and prohibited the trust domain. The
   explicit Phase 1 request advances repository phase scope; `AGENTS.md` is
   updated before implementation.
2. The Phase 0 dossier claim shape stores `truth_status` and nested warrant
   summaries. Revision 0.2 requires both to be independent records/projections.
   ADR-0005 keeps the Phase 0 fixture historical and introduces a separate
   Phase 1 mapping.
3. The original Phase 0 scorecard combined capability with license,
   maintenance, runnability, security, and effort, assigning numeric results to
   integrations that never ran. ADR-0004 corrects the interpretation without
   modifying raw observations.

## No conflict

- A standard-library typed layer is allowed: the blueprint calls Pydantic a
  suggested default, not a permanent constraint.
- Append-only in-memory repositories, manual CLI construction, frozen
  protocols, policy projections, and canonical dossier interchange are the
  stated Phase 1 exit path.
- Novelty, significance, and contribution stay explicit independent axes but
  are `not_assessed`/unlinked in Phase 1; no automation is introduced.

No other material departure from architecture revision 0.2 is required.
