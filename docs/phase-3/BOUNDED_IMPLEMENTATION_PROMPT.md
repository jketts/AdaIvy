# Bounded Prompt for the Smallest Phase 3A Slice

Use this only after ADR-0012 through ADR-0014 and the Phase 3A entry-gate
decisions are accepted.

```text
Read README.md, TECHNICAL_BLUEPRINT.md, NOVELTY_LANDSCAPE.md, AGENTS.md, every
accepted ADR, the complete Phase 2 closeout/release manifest, and every Phase 3A
design artifact. Confirm the accepted Phase 2 evidence hashes and run the full
101-test suite plus all 19 Phase 0 checks before changing code.

Implement Phase 3A research memory only. Preserve the Phase 1 domain/trust model,
the Phase 2 provider/proposal/budget/recovery boundaries, and the immutable v1,
v2, and v3 live histories. Do not make a live API call.

Build the smallest local vertical slice:

1. immutable manual local-file import and opaque metadata-only URI records, with
   zero network resolution, SHA-256 identity for local bytes, null content hash
   for unresolved metadata-only records, complete provenance/rights metadata,
   version relations, quarantine, transactions, events, and idempotency;
2. the internal deterministic `plain-text-v1` UTF-8 parser producing form-feed
   page and section boundaries, stable UTF-8 byte spans, original-location maps,
   required markers, warnings, parser provenance, and derived-artifact hashes;
   quarantine PDFs, invalid UTF-8, and every unsupported media type without
   extraction;
3. immutable typed evidence units and origin-distinct relation proposals;
4. one rebuildable SQLite FTS5/BM25 index with a frozen tokenizer, deterministic
   tie-breaking, exact-span hits, query/index/result manifests, and no vector
   database;
5. deterministic bounded evidence packs with rights/quarantine filtering,
   deduplication, source diversity, inline provenance, contradiction retention,
   injection annotations, and complete inclusion/exclusion manifests;
6. scripted proposer/verifier citation validation proving that fabricated and
   out-of-pack IDs are rejected and all model output remains proposal-only; and
7. canonical ResearchMemoryExport import/export, crash/restart/replay, report,
   credential scan, and all tests in the Phase 3A requirement matrix.

Use project-authored synthetic primary, related, contradictory, malformed, and
prompt-injection fixtures for infrastructure acceptance. Represent the
quantum-state-discrimination paper as metadata only with `content_hash: null`.
Do not commit, extract, fabricate, or download its PDF/text.

Freeze retrieval acceptance at Recall@5 = 1.0, MRR >= 0.75, citation-resolution
precision = 1.0, zero quarantined evidence retrieved, and identical ordered
evidence IDs and evidence-pack hashes over three repeated runs and one restart.
Do not require cross-platform equality of raw floating-point BM25 scores.

Do not implement a crawler, remote source APIs, DNS/HTTP checks, PDF parser,
embeddings or an embedding-provider port, vector database, PaperQA2,
novelty/significance automation, formal/symbolic/numerical tools, Lean, Why3,
CAS, web/API surface, multi-agent search, PostgreSQL, quantum solver, or the
Phase 3B/Phase 4 roadmap.

At completion, run every Phase 0–3A test and schema validator, demonstrate
deterministic import/retrieval/pack/export/restart replay, report all hashes and
blockers, prove the old live evidence is unchanged, list deferred work, and stop.
```
