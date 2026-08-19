# ADR-0012: Re-sequence research memory as Phase 3A

- **Status:** accepted
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

## Decision

Use this sequence:

- **Phase 3A:** bounded, manually supplied research-memory vertical slice;
- **Phase 3B:** formal-tool and proof-assistant grounding; and
- **Phase 4:** broader acquisition, crawling, embeddings, and research
  automation.

Phase 3A may supply evidence packs to the existing scripted proposer/verifier
loop, but no live call or tool integration is required. Update README, blueprint
roadmap, deferred-work records, and `AGENTS.md` together before Phase 3A
implementation so the accepted sequence is not represented inconsistently.

## Consequences

Source provenance and deterministic retrieval become available earlier. Lean,
Why3, CAS, interval, optimization, SMT, meaning tests, and certified
counterexamples remain Phase 3B. Broader acquisition, crawling, embeddings,
literature automation, and research automation remain Phase 4. Phase numbers
must use the 3A/3B labels consistently to avoid misleading release claims.

## Blueprint deviation

Accepted deviation: move a bounded, manually supplied research-memory subset
ahead of the existing formal-tool work without combining their implementations.
Necessity is the explicit researcher-approved vertical slice. Revisit if
source-memory work cannot be completed without the deferred tool stack.

## Validation and revisit trigger

Keep the decision only with a frozen Phase 3A requirement matrix, explicit
corpus-rights treatment, a recorded parser/dependency decision, and continued
Phase 0–2 compatibility. Revisit before Phase 3B implementation or any Phase 4
crawler, embedding, or research-automation work.
