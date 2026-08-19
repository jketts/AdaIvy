# ADR-0012: Re-sequence research memory as proposed Phase 3A

- **Status:** proposed
- **Date:** 2026-08-19
- **Blueprint requirement:** §§7 and 19; explicit roadmap governance
- **Decision owners:** researcher and repository maintainer

## Context

Architecture revision 0.2 assigns mathematical tools and early formal grounding
to Phase 3, and source acquisition/retrieval to Phase 4. The requested next
vertical slice instead prioritizes manually supplied research memory, immutable
source provenance, deterministic retrieval, and evidence packs. README, Phase 0
ADR-0003, Phase 1 deferred work, and `AGENTS.md` reflect the existing order.
Silently implementing the request as ordinary Phase 3 would contradict those
records.

The requested slice does not require a crawler, embeddings, PaperQA2, novelty
automation, or the quantum solver. It can exercise provenance needed by later
tool/model work using the accepted Phase 2 durability and proposal boundaries.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Keep tools as Phase 3; schedule memory as Phase 4 | Current blueprint and ADR-0003 | No roadmap churn | Defers the operator-selected trust bottleneck | Reject requested sequencing |
| Replace the old Phase 3 silently | None | Simple numbering | Loses prior decisions and tool commitments | Prohibited |
| Name memory Phase 3A and tools Phase 3B | Bounded design and existing modular ports | Preserves both scopes and makes ordering explicit | Documentation/version complexity | Human approval and coordinated roadmap update |
| Combine memory and tools in one Phase 3 | Blueprint sections 7 and 9 | Broader capability | Too large; dependencies and acceptance signals confound | Violates bounded-slice principle |

## Proposed decision

Designate the bounded research-memory slice as Phase 3A. Retain the existing
tool/formal-grounding scope unchanged as Phase 3B. Phase 3A may supply evidence
packs to the existing scripted proposer/verifier loop, but no live call or tool
integration is required.

After approval, update README, blueprint roadmap, deferred-work records, and
`AGENTS.md` together in a dedicated architecture commit before implementation.
Until then, those files remain authoritative and this ADR is only a proposal.

## Consequences

Source provenance and deterministic retrieval become available earlier. Lean,
Why3, CAS, interval, optimization, SMT, meaning tests, and certified
counterexamples are delayed in sequence but not rejected. Automated literature
acquisition and novelty assessment remain later work. Phase numbers must use the
3A/3B labels consistently to avoid misleading release claims.

## Blueprint deviation

Proposed deviation: swap a bounded subset of existing Phase 4 ahead of existing
Phase 3 without combining their implementations. Necessity is the explicit
operator-selected vertical slice. Revisit if source-memory work cannot be
completed without the deferred tool stack or if the researcher prefers the
original ordering.

## Validation and revisit trigger

Approve only with a frozen Phase 3A requirement matrix, corpus-rights decision,
dependency spike, and continued Phase 0–2 compatibility. Revisit before any
crawler, automated novelty workflow, formal tool, or Phase 3B implementation.
