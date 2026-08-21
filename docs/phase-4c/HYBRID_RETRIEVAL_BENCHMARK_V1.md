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

- `fixtures/phase4c/corpus-manifest.json` names exactly 17 UTF-8 documents.
- Every document is project-authored under
  `LicenseRef-AdaIvy-Synthetic-Fixture` and carries an applicability class,
  source class, contradiction flag, and optional duplicate group.
- `fixtures/phase4c/gold-queries.json` names exactly 15 frozen queries: three
  necessary-lemma, four applicability, two contradiction, two notation-variant,
  and four renamed-known-result controls.
- `fixtures/phase4c/name-aliases.json` names a content-keyed alias table of at
  least nine entries. Each entry maps an alias name phrase to content phrases
  only; a document identifier never appears in the file. At least five entries
  are exercised by no query and match no corpus document, so a signal that uses
  the table must consult a reference work rather than an answer key.
- The lexical baseline uses Unicode NFC normalization, alphanumeric token
  extraction, case folding, FTS5 `unicode61 remove_diacritics 0`, OR-combined
  quoted tokens, the Phase 3A title/body/type BM25 weights `2.0/1.0/0.5`, and
  document ID as the deterministic tie-break.
- Raw BM25 floats and wall time are operational observations. Canonical identity
  binds corpus/query hashes, ordered result IDs, classifications, and metrics.

## Fixture extension, 21 August 2026

This corpus and query set were extended from 14 documents and 10 queries under
ADR-0031, with owner approval, before the hybrid candidate was measured.

The reason was that two gates could otherwise be met without being tested. The
renamed-known-result gate had exactly one control query, so an alias table
containing exactly that one alias would have scored `1.0` while demonstrating
nothing. Applicability precision was measured over two queries and five
observations, which is too narrow to distinguish a general discrimination signal
from one fitted to two known false hits. The extension adds three renamed
controls over genuine mathematical name aliases and two applicability controls
that exercise documents the discrimination signal was not authored against.

Adding the controls did not move either measured value: applicability precision
stayed at `0.6` (now 6 of 10 observations rather than 3 of 5) and
renamed-known-result recall stayed at `0.0` (now 0 of 4). Queries were not
selected for their score, which the forbidden outcomes below prohibit.

Measured values recorded before this extension describe a different corpus and
are not comparable with values recorded after it. The discontinuity is recorded
here, in ADR-0031, and in the fixture manifest so that it is visible rather than
inferred. The lexical baseline's own pinned values were re-established from
scratch on the extended fixtures.

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

Resource gates are: exactly 17 documents, exactly 15 queries, maximum query
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
`embedding` rights decision naming the processor that receives the source text.
A second provider is a distinct disclosure and needs its own decision.

## Multi-provider constraint

If the model-provider boundary ever admits more than one provider, a hybrid
candidate must bind the producing provider into the vector projection's identity
per `TECHNICAL_BLUEPRINT.md` Section 12.2.1: partition by `(provider,
model_identifier, dimension, normalization)`, compare only within a partition,
rebuild rather than backfill on any provider or model change, and store produced
vectors as immutable content-hashed artifacts so the deterministic-rebuild gate
replays bytes instead of re-calling a provider that is neither bit-reproducible
nor stable behind its own model aliases.

The failure this prevents is silent. Two same-dimension models from different
vendors yield a corrupted similarity space that still returns a full, plausibly
ordered result set, so none of the recall or precision gates above detects it on
its own.

## Forbidden outcomes

The benchmark must make these impossible:

- using gold labels, applicability labels, duplicate groups, or expected IDs as
  retrieval features;
- treating retrieval rank, metric success, or agreement among signals as proof;
- hiding a failed query, zero-hit query, duplicate, or inapplicable hit;
- downloading a model, resolving a URI, opening a socket, or calling an API;
- mutating Phase 3A FTS, Phase 4 content, or synthesis state;
- selecting thresholds after observing a hybrid candidate;
- reporting renamed-result noncoverage as novelty;
- comparing, merging, or ranking vectors produced by different providers or
  different embedding models within one similarity space.

## Spike outcome

`spikes/phase4c_benchmark/evaluator.py` is intentionally a benchmark-only
lexical evaluator. Its tests verify fixture integrity, honest metrics,
deterministic rebuild, zero external surfaces, and separation between measured
baseline values and proposed future thresholds. Passing the spike does not mean
the Phase 4C gates pass.
