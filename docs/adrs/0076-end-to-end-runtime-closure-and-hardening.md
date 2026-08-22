# ADR-0076: End-to-end runtime closure and trust-boundary hardening

- **Status:** Accepted and implemented for the offline end-to-end runtime
- **Date:** 2026-08-22
- **Extends:** ADR-0072 and ADR-0074
- **Supersedes in part:** ADR-0075's rule that every orphaned intent is
  ambiguous; only paid or irreversible orphaned intents stop automatically

## Context

The first ADR-0075 acceptance path proved sequential component invocation, but
its fixture still left several requirements as declarations: the v2 planner
schema was not consumed, distinct campaigns could not share one data root,
exact evidence could enter model context without checking that separate use,
the experiment was a no-execution placeholder, verification did not decide the
candidate, and the generated TeX was not a provenance-closed bundle. A raw
projection file could also influence takedown deletion.

## Decision

The `campaign start` operator path is the v2 end-to-end campaign contract. It:

1. requires an explicit credential-profile identifier, persistent data-root
   identifier, and finite model, embedding, network, tool, storage, and wall
   budgets;
2. seals those values with the frozen target and verifies them on resume;
3. consumes the closed `model-campaign-action-v2` contract for profile-bound
   query generation and evidence-guided planning;
4. enforces search/follow/acquire/parse/embed/refresh/retrieve order, with
   depth-one result following restricted to a request-bound origin allowlist;
5. checks `model_context` rights for the exact processor, provider, model, and
   time before retrieved source text is placed in planning context;
6. checkpoints the retrieval result identifier, manifest hash, and evidence
   card content/object hashes;
7. runs a bounded built-in exact experiment, retains an independently produced
   refuting finding, performs a causally linked repair, and independently
   verifies the replacement against an exact target binding;
8. retries only orphaned idempotent local intents; an orphaned paid or
   irreversible intent remains unresolved;
9. writes a provenance-closed unapproved publication bundle and invokes the
   pinned typesetter automatically only when the exact toolchain is present;
   and
10. proves cross-campaign reuse by running two campaign identifiers over one
    operator-selected data-root identity and requiring zero document embedding
    calls in the second campaign.

Checkpoint readers validate their exact record schema, identity, request/result
hashes, idempotency derivation, and intent/terminal binding. Takedown collects
vector object hashes only from projections that pass the complete ADR-0074
loader while their corpus generation is active; raw or forged projection JSON
is never deletion authority.

The offline exact experiment is not the generated-program OCI sandbox. The
legacy `campaign run` entrypoint retains the ADR-0073 activated OCI and verifier
router paths. Live provider, discovery, acquisition, embedding, OCI, and Lean
effects retain their separate activation requirements.

## Consequences

- A model call and every embedding call in the acceptance path cross the same
  selected profile and unified durable budget ledger.
- A verifier refutation is a candidate outcome, not a campaign failure; the
  retained finding may influence a later valid action while budget remains.
- Retrieval citations locate an immutable result manifest and exact card
  objects, while applicability and mathematical warrant remain unresolved.
- The generated report is reconstructible from target, action, evidence,
  verification, and budget records, but remains visibly unapproved.
- Passing the offline gate demonstrates orchestration only. It does not activate
  external services or establish mathematical truth, novelty, significance, or
  source applicability.
