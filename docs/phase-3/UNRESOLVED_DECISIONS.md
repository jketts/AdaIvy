# Phase 3A Decisions Requiring Human Approval

Status: unresolved  
Date: 2026-08-19

1. Approve ADR-0012's roadmap resequencing, reject it, or retain tools/formal
   grounding as Phase 3 and name research memory Phase 4.
2. Decide whether the old tool phase becomes Phase 3B or retains another public
   version number; update the blueprint, README, deferred lists, and `AGENTS.md`
   together only after approval.
3. Choose and publish a repository software/documentation license, or explicitly
   retain an all-rights-reserved private-repository policy.
4. Verify and approve redistribution/context rights for the 2002 quantum paper.
5. Select the related gold source and verify its exact version and rights.
6. Select the PDF parser after the common-fixture spike; approve every direct
   and transitive license and a fully pinned lock.
7. Decide whether a deterministic normalized-text companion supplied by a human
   is acceptable when PDF extraction cannot preserve equations/coordinates.
8. Approve the UTF-8 byte/page-region coordinate convention and expected
   behavior when a parser cannot supply original coordinates.
9. Freeze the human relevance judgments and numerical retrieval thresholds
   before implementation results are inspected.
10. Approve exact source-diversity, deduplication, contradiction, rights, and
    prompt-injection pack policies.
11. Decide which parser-derived structures can be accepted deterministically and
    which require explicit human review.
12. Decide whether source-explicit citation edges can be marked accepted as
    faithful extraction without suggesting mathematical applicability.
13. Choose separate `ResearchMemoryExport` v1 versus a later ResearchDossier v2.
    This proposal recommends the separate export for Phase 3A.
14. Define copyright/retention rules for exact spans in model prompts, logs,
    reports, and exported packs before any restricted source is used.
15. Decide whether Phase 3A includes any live model demonstration. It is not
    required by this design and would need separate authorization and budget.
16. Decide how strictly SQLite/tokenizer versions must match for cross-machine
    replay and what constitutes an acceptable explicit blocker.
17. Define a human proposal-review/disposition workflow if live-test or Phase 3A
    proposals are ever to be evaluated. Phase 2 intentionally lacks one.

No unresolved decision authorizes a permissive default. Rights, trust,
compatibility, and engine-version ambiguity fail closed.
