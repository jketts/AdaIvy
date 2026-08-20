# ADR-0017: Limit Phase 4A to local rights and human applicability review

- **Status:** accepted
- **Date:** 2026-08-20
- **Blueprint requirement:** Phase 4 entry gate; applicability-before-citation and human-authority invariants
- **Decision owners:** repository owner and researcher

## Context

The repaired Phase 3B baseline is integrated at
`e7db0ffa2d3fe4609c8a62642ec70fc5343776e3`. The repository owner approved a
single Phase 4A direction on 2026-08-20 but explicitly withheld production
authorization. The decision was made against these complete pre-approval gate
artifacts:

- `docs/phase-4/ENTRY_GATE_REPORT.md` SHA-256
  `ccd382ebab45eb6eab574ed0794c9252d60829ae20aa12ba270d92a20b8f7d56`;
- `reports/phase-4-entry-gate/entry-gate.json` SHA-256
  `89544036e7f300851277b46b1b5403672ca1a6f2a8887366ffb8445b9d3fc117`.

The accepted control and threshold inventories are
`docs/phase-4/SECURITY_CONTROL_INVENTORY.md` and
`docs/phase-4/ACCEPTANCE_THRESHOLD_INVENTORY.md`. Their hashes are recorded in
the final machine gate evidence. Those inventories narrow this ADR; prose may
not silently expand it.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Begin crawling and rich parsing | Documentation research only | Broader corpus | Rights, hostile parsing, network, and dependency boundaries unmeasured | Rejected for Phase 4A |
| Add embeddings/hybrid retrieval | Unapproved model-card candidate only | Potential recall gain | Weights/runtime/data rights and determinism unvalidated | Rejected for Phase 4A |
| Local rights and applicability review | Existing Phase 1 applicability and Phase 3A provenance contracts | Resolves pre-acquisition trust controls without new runtime | Adds explicit review records and policy work | Selected |
| Defer all Phase 4 work | Repaired baseline | No new risk | Leaves rights/applicability gate unavailable | Rejected by owner direction |

## Decision

The prospective first production slice is **Phase 4A local rights and source-
applicability review**. It is limited to local user-supplied material already
eligible for `plain-text-v1`, explicit per-use rights decisions, provenance,
human applicability review, and deterministic audit/export.

The production design may add versioned records for rights decisions, source
lifecycle actions, evidence cards, applicability reviews, and policy snapshots,
plus a separate Phase 4 v1 export. The design must be additive. Unknown or mixed
versions fail closed. Phase 0-3B records and exports retain their exact meaning.
This ADR approves the architecture direction only; it does not create or
authorize production records, schema, migration, service, or workflow code.

Rights are never inferred from possession or accessibility. Acquisition,
storage/retention, parsing, excerpting, embedding, model context,
redistribution, and publication are separate decisions. Absent, ambiguous,
expired, revoked, prohibited, or incompatible rights block the requested use.
AdaIvy records evidence and reviewer decisions but makes no legal
determination.

Only an explicit human action may mark applicability `checked` or applicable.
Automated/model assessments remain proposals and cannot promote themselves.
Rights and applicability remain separate. Every decision retains actor, exact
reason, evidence, timestamp, version, and supersession linkage.

Corrections, revocations, takedowns, and deletions are append-only actions.
Historical audit identity is retained without retaining source content whose
continued retention is prohibited.

## Explicit deferrals

Phase 4A excludes crawler/remote acquisition, robots processing, rich or active-
content parsers, archive expansion, embeddings, vector indexes, hybrid
retrieval, model/provider calls, research automation, scheduled jobs,
autonomous applicability decisions, and all Phase 5 work. Values documented
for possible future adapters are neither capability approval nor production
authorization. Enabling any deferred capability requires renewed owner review
and a new or superseding ADR.

## Consequences

The first production prompt can be narrow and dependency-free if the complete
gate passes. Review storage is more explicit, and deletions require tombstone/
suppression semantics rather than record mutation. Human review is a throughput
constraint by design. No broad Phase 4 acquisition or retrieval claim may be
made from this slice.

## Blueprint deviation

The Phase 4A ordering is a bounded subdivision of Phase 4. It puts the rights
and applicability control plane before broader acquisition, rather than
implementing the whole Phase 4 objective at once.

## Validation and revisit trigger

Keep this decision only while the 16 content-hashed synthetic fixtures and the
nonproduction candidate spike pass every exact threshold in the accepted
inventory; two independent gate runs plus fresh-process restart have identical
canonical hashes; Phase 0-3B and sealed v5 checks pass; protected evidence is
unchanged; and zero network/model/API calls occur. Revisit for any new record
meaning, version rule, rights action, automated authority, dependency, parser,
network path, embedding, index, scheduler, or production-scope expansion.
