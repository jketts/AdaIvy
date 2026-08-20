# Proposed Phase 4C Hybrid-Retrieval Benchmark v1

Status: design-only, nonproduction spike

## Purpose

This benchmark freezes a project-authored corpus and gold queries before any
Phase 4C index is implemented. It measures the existing SQLite FTS5/BM25-style
lexical baseline and defines proposed gates for a later hybrid candidate. It
does not authorize embeddings, model calls, vector storage, a production index,
or a change to Phase 3A, Phase 4A, or Phase 4B.

Retrieval produces candidates, never premises or warrants. Applicability,
extraction fidelity, mathematical warrant, and graph admission remain separate.

## Corpus and query contract

- `fixtures/phase4c/corpus-manifest.json` names exactly 14 UTF-8 documents.
- Every document is project-authored under
  `LicenseRef-AdaIvy-Synthetic-Fixture` and carries an applicability class,
  source class, contradiction flag, and optional duplicate group.
- `fixtures/phase4c/gold-queries.json` names exactly 10 frozen queries: three
  necessary-lemma, two applicability, two contradiction, two notation-variant,
  and one renamed-known-result control.
- The lexical baseline uses Unicode NFC normalization, alphanumeric token
  extraction, case folding, FTS5 `unicode61 remove_diacritics 0`, OR-combined
  quoted tokens, the Phase 3A title/body/type BM25 weights `2.0/1.0/0.5`, and
  document ID as the deterministic tie-break.
- Raw BM25 floats and wall time are operational observations. Canonical identity
  binds corpus/query hashes, ordered result IDs, classifications, and metrics.

## Metrics

| Metric | Definition | Proposed Phase 4C gate |
|---|---|---|
| Necessary-lemma Recall@5 | Gold necessary-lemma documents found in the first five results, micro-averaged | `1.0` |
| Applicability precision@5 | Applicable documents divided by all topically relevant retrieved documents for applicability queries | `1.0` |
| Contradiction Recall@5 | Gold contradictory documents found in the first five results, micro-averaged | `1.0` |
| Notation-variant Recall@5 | Gold documents found for symbol/name variants absent from their primary wording | `1.0` |
| Renamed-known-result Recall@10 | Gold prior result found under its frozen alternate name | `1.0` |
| Duplicate rate@5 | Retrieved hits after the first member of any declared duplicate group, divided by all retrieved hits | at most `0.05` |
| Deterministic rebuild | Ordered IDs and canonical report hash across three normal builds, one reverse-insertion build, and one fresh-process run | exact equality |
| External cost | Network, model/API calls, downloaded artifacts, and external spend | all `0`; USD `0` |

Resource gates are: exactly 14 documents, exactly 10 queries, maximum query
length 4,096 UTF-8 bytes, top-k 5 except renamed control top-k 10, at most 50
candidates per future signal, canonical report at most 262,144 bytes, derived
benchmark database at most 2,097,152 bytes, and a 10-second parent-process hard
timeout for this corpus. Runtime is reported but is not part of semantic identity.

## Required comparison

A future hybrid candidate must run on these exact bytes and queries alongside
the lexical baseline. It must meet every metric gate, preserve exact spans and
source applicability, retrieve no quarantined or rights-blocked content, and
show a gain on at least one metric on which the lexical baseline is below the
gate. It may not worsen any metric already met by the baseline.

Any new signal must be a rebuildable projection. Index deletion or rebuild may
not change canonical source, rights, applicability, evidence, or synthesis
records. Embedding source use requires an independent current Phase 4A
`embedding` rights decision.

## Forbidden outcomes

The benchmark must make these impossible:

- using gold labels, applicability labels, duplicate groups, or expected IDs as
  retrieval features;
- treating retrieval rank, metric success, or agreement among signals as proof;
- hiding a failed query, zero-hit query, duplicate, or inapplicable hit;
- downloading a model, resolving a URI, opening a socket, or calling an API;
- mutating Phase 3A FTS, Phase 4 content, or synthesis state;
- selecting thresholds after observing a hybrid candidate;
- reporting renamed-result noncoverage as novelty.

## Spike outcome

`spikes/phase4c_benchmark/evaluator.py` is intentionally a benchmark-only
lexical evaluator. Its tests verify fixture integrity, honest metrics,
deterministic rebuild, zero external surfaces, and separation between measured
baseline values and proposed future thresholds. Passing the spike does not mean
the Phase 4C gates pass.
