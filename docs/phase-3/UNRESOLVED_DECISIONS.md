# Phase 3A Decision Record

Status: entry gate resolved
Date: 2026-08-19

## Resolved Phase 3A decisions

1. ADR-0012 through ADR-0014 are accepted.
2. Phase sequence is Phase 3A research memory, Phase 3B formal tools, and Phase 4
   broader acquisition/crawling/embeddings/research automation.
3. URI metadata is opaque, local-only, unresolved, null-hash, and non-evidentiary.
4. Phase 3A contains no embeddings or embedding-provider port.
5. The only parser is internal `plain-text-v1`; PDFs/unsupported media are
   quarantined without extraction.
6. The quantum paper is metadata-only; its PDF/text is not committed.
7. Infrastructure acceptance uses five project-authored synthetic fixtures.
8. Retrieval thresholds are Recall@5 1.0, MRR at least 0.75, citation precision
   1.0, zero quarantined hits, and identical ordered IDs/pack hashes over three
   runs and one restart. Raw BM25 float equality is not cross-platform.
9. Research memory uses a separate `ResearchMemoryExport` v1; ResearchDossier v1
   remains unchanged.
10. No model/external API call is part of Phase 3A.

## Decisions deferred beyond Phase 3A

- repository/publication licensing and real-paper redistribution rights;
- real related academic source selection and licensed academic-corpus replay;
- PDF/OCR parser selection;
- embedding/hybrid retrieval and its evaluation;
- human promotion of model/parser proposals;
- multi-user retention, legal hold, and restricted-source context policy;
- Phase 3B formal-tool selection.

Deferred ambiguity fails closed and does not block the synthetic, private,
plain-text Phase 3A acceptance slice.
