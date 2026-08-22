# ADR-0067: Corpus ingestion at volume (owner decision required)

- **Status:** accepted for option C. The owner selected the bulk open-access
  snapshot and declined the batched-manifest intermediate step. Option B
  (following discovery results) was opened over a recorded recommendation
  against it and is carried into ADR-0068 rather than here.
- **Date:** 2026-08-22
- **Blueprint requirement:** Section 7.3 (retrieval strategy); Section 7.1
  (crawlers produce candidates, not trusted documents); ADR-0050 (public
  unauthenticated acquisition); ADR-0051 (bounded scholarly discovery);
  ADR-0064/0062/0063 (the semantic capability this would feed)
- **Decision owners:** repository owner. **This ADR asks a question rather than
  answering one.**

## Context

ADR-0064 through ADR-0066 add embedding-backed semantic retrieval. They do not
make retrieval wide, and the reason is not the signal — it is the corpus.

Phase 4C retrieves over exactly 19 documents. `phase4c/fixtures.py` enforces
that count and fails closed on any other. Semantic search over 19 documents is a
retrieval benchmark, not a literature search, and ADR-0066 says so in terms.

What stands between the current state and a real corpus is acquisition volume,
governed today by two deliberately narrow capabilities:

- **ADR-0050** permits public, unauthenticated, human-planned, exact-URL
  acquisition, **one request at a time**, with no crawling, no result following,
  and no autonomous origin selection. The activation record at
  `config/phase4b-public-acquisition-activation-v1.json` pins
  `max_requests_per_run: 1`, `max_origins_per_run: 1`, and
  `max_plan_age_seconds: 300`.
- **ADR-0051** permits one Crossref metadata query returning at most ten DOI
  candidates, every one an `untrusted_inspiration_candidate` with relevance,
  applicability, novelty, and significance `not_assessed`, and acquisition
  explicitly unauthorized.

Both are working as designed. Neither can build a corpus, and no combination of
them can: ten inspiration candidates that may not be fetched, plus one
human-typed URL per run, is not an ingestion path.

The blueprint anticipates this and constrains the answer.
`TECHNICAL_BLUEPRINT.md:1129-1130`: "Do not build unrestricted crawling into the
trusted core. Crawlers produce candidate documents that pass through validation
and ingestion." So volume is permitted in principle; what is forbidden is volume
that arrives pre-trusted.

Two costs scale with the corpus and are usually forgotten. Every document needs
a Phase 4A rights decision for acquisition, retention, and parsing, plus — now —
an ADR-0064 processor decision before it may be embedded. And C12
(`:176-182`) means every load-bearing passage still needs its statement,
hypotheses, definition correspondence, and checked implication recorded by hand.
**Ingestion scales with money and compute; applicability scales with human
attention, and that is the real ceiling.** A 10,000-document corpus with no
applicability records is not 500x more useful than a 20-document one; it is a
larger pile of untrusted candidates.

## Options considered

| Option | What changes | Benefit | Cost/risk | Recommendation |
|---|---|---|---|---|
| **A. Batched human-authored URL manifest** | one plan lists N exact URLs; execution stays sequential and per-URL; `max_requests_per_run` rises from 1 to N with N pinned per plan | the human still chooses every origin, so `autonomous_origin_selection` stays `false` and no crawler exists; smallest honest delta from ADR-0050; rights stay per document | N grows only as fast as a human can curate; does not reach thousands | Recommended first step; **not selected** |
| **B. Follow Phase 4D discovery results** | machine selects URLs from Crossref output | genuinely wide, low human cost | crosses `autonomous_origin_selection`, the line ADR-0050 and ADR-0051 both draw explicitly; a poisoned metadata record becomes a fetch target; ADR-0051's "does not follow results" is load-bearing prompt-injection defence given `:1801` | Not recommended without a separate injection-containment decision |
| **C. One authorized bulk open-access snapshot** (arXiv bulk, OpenAlex) | one provenance-bearing archive instead of N fetches | reaches real scale; one rights decision over one licensed corpus; content-hashed and replayable, which suits §12.2.1 | licence diligence is the whole job; a snapshot is a dependency with a version; storage and embedding cost become real; per-document applicability still manual | **Selected** |
| **D. Do nothing; keep the 19-document benchmark** | nothing | zero risk; benchmark stays clean | leaves the owner's stated goal unmet and leaves ADR-0066 measuring a system nobody wants | Rejected, but honest to name |

## Decision

Adopt option C: one authorized bulk open-access snapshot, acquired as a
provenance-bearing archive rather than as a traversal. Option A is skipped.

### The cost of skipping A, stated plainly

A existed to exercise the ingestion pipeline at a scale where a mistake is
cheap. Skipping it means the first real run of rights-per-document, parsing,
chunking, embedding, and partition construction happens at bulk scale, where a
design error is discovered after the expensive part rather than before it.

Two mitigations are therefore mandatory rather than optional, and they are the
condition on which this option is accepted:

1. **A bounded first tranche.** The first ingestion processes a pinned,
   content-hashed subset of the snapshot — low thousands of documents at most —
   and its report is reviewed before the remainder is touched. This recovers
   most of A's value without a separate acquisition capability, because the
   subset is selected from an already-acquired archive rather than fetched.
2. **Licence diligence precedes acquisition, not ingestion.** The archive's
   licence, its per-record licence heterogeneity, and the redistribution
   posture are recorded before the snapshot is fetched. An archive whose records
   carry mixed licences requires a per-record rights derivation, and discovering
   that after download means holding bytes we may not process.

### Named boundaries

- **A snapshot is an acquisition, not a crawl.** One archive, one version, one
  content hash, no traversal of anything inside it.
- **Per-document rights do not become per-archive rights.** One licence decision
  over the archive establishes the *ceiling*; each document still needs its
  Phase 4A decisions and, to be embedded, its ADR-0064 processor decision. A
  bulk grant that skips this is the failure mode this repository exists to
  prevent.
- **Applicability stays manual and stays the ceiling.** Scale changes the
  candidate count, not the number of passages a human has actually read. Every
  report must separate corpus size from the count of documents carrying an
  applicability record, or corpus size reads as knowledge.
- **Archive selection is a human act.** Which archive, which version, which
  tranche: recorded, not inferred, and never chosen by a model.

Until a tranche is ingested, ADR-0066's semantic signal is measured over 19
project-authored documents and every report from it must say so.

## What this ADR does not do

It authorizes nothing. It adds no capability, changes no bound, and moves no
activation record. It does not assess novelty, significance, or applicability,
and it does not license a crawler under any option, including C — a bulk
snapshot is an acquisition, not a traversal.

## Blueprint deviation

None yet. Option B would deviate from the no-result-following posture and would
need that deviation stated explicitly rather than buried in a bound change.

## Validation and revisit trigger

Revisit when the owner answers the three questions above. Reconsider the whole
framing if applicability recording is ever automated, because the human-attention
ceiling is the premise of the recommendation and automating it would change the
answer.
