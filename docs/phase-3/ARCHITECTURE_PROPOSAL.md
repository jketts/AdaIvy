# Phase 3A Research-Memory Architecture

Status: accepted for bounded implementation
Date: 2026-08-19

## Bounded goal

Convert a small, manually supplied research corpus into immutable,
provenance-preserving evidence units that can be deterministically retrieved
and supplied to proposer/verifier jobs without treating extracted or
model-generated summaries as source truth.

The 2002 quantum-state-discrimination paper is retained only as a generic
metadata record and future demonstration anchor. Project-authored synthetic
sources are the Phase 3A acceptance corpus. No quantum-specific entity,
retrieval rule, solver, or convergence claim belongs in the core.

## Roadmap reconciliation and history

This goal conflicts with the architecture baseline rather than merely refining
it.

| Existing record | Existing Phase 3 | Requested slice | Conflict |
|---|---|---|---|
| `README.md` build sequence | Tools and early formal grounding | Research memory and retrieval | Direct ordering conflict |
| Blueprint §19 | Sandbox, exact/numeric/SMT, proof assistant, meaning tests, counterexamples | Source acquisition, normalization, FTS retrieval, evidence packs | Requested work is mostly existing Phase 4 |
| Phase 0 ADR-0003 | Wrap Why3 and Lean in Phase 3; PaperQA2 no earlier than Phase 4 | No tools; deterministic local retrieval only | Integration schedule changes |
| Phase 1 deferred work | Tools in Phase 3, acquisition/retrieval in Phase 4 | Acquisition/retrieval in Phase 3 | Direct ordering conflict |
| Phase 2 deferred work | Groups both categories as Phase 3 and later | Selects research memory first | Compatible only at a broad stop-line level |
| `AGENTS.md` | Phase 2 remains current and forbids Phase 3 features | Design only now; implementation later | Instructions must change only after human approval |

The table above preserves the superseded revision-0.2 roadmap conflict. Accepted
ADR-0012 resolves it: the bounded slice is Phase 3A, formal-tool and
proof-assistant grounding is Phase 3B, and broader acquisition, crawling,
embeddings, and research automation are Phase 4. Quantum convergence work is
not part of Phase 3A.

## Architectural boundaries

```text
manual file/metadata input
        |
        v
quarantine + immutable source bytes (CAS)
        |
        v
deterministic parser run --> normalized derived document + location map
        |
        v
typed evidence-unit proposals + typed relation proposals
        |
        v
accepted source-derived memory ----> rebuildable SQLite FTS5 projection
        |                                      |
        +-------------------+------------------+
                            v
                  deterministic evidence pack
                            |
                 +----------+----------+
                 v                     v
             proposer               verifier
                 |                     |
                 +---- proposal-only --+
```

Canonical source bytes, source metadata, normalized derived artifacts, evidence
units, relations, and pack manifests are immutable records. The FTS index,
rankings, and rendered context are rebuildable projections. Phase 3A contains no
embedding boundary. Domain entities and trust policy do not import SQLite,
parser, model, CLI, or vector-database packages.

## 1. Source acquisition boundary

The only Phase 3A acquisition actions are explicit operator commands:

- import a local regular file with separately supplied metadata;
- import an opaque user-supplied URI metadata record without dereferencing it;
  or
- associate manually acquired bytes with an existing metadata-only record.

There is no autonomous crawler, recursive link following, browser automation,
or scheduled refresh. A metadata-only URI receives local syntax validation only:
no DNS, HTTP, redirect, availability, or content check occurs. Its
`content_hash` remains null, its status is unresolved, and it cannot produce a
`SourceArtifact`, span, or evidence unit.

A source import must record:

- immutable source bytes in the Phase 2 content-addressed artifact store;
- content SHA-256 and byte length;
- canonical and originally supplied URI;
- acquisition mode and retrieval/import timestamp;
- title, authors, publication identifiers, version, and publication date;
- media type determined independently of the filename;
- license, copyright, usage-rights, and redistribution status;
- acquisition adapter/version and operator ID;
- `supersedes`, `is_version_of`, or `corrects` relationships; and
- quarantine state plus exact reasons.

Local paths are acquisition inputs, never durable source identities. Symlinks,
devices, directories, oversized files, media-type mismatches, and content that
cannot be hashed completely fail or remain quarantined before parsing.

## 2. Document normalization

The original source artifact remains authoritative. Normalization produces a
separate content-addressed derived artifact with parser provenance.

The sole Phase 3A parser is the internal, versioned `plain-text-v1` parser. It
accepts valid UTF-8 plain text only. PDFs and other media types are stored in
quarantine without extraction. The normalized representation is deterministic
UTF-8 text plus a canonical structure map. It records:

- page and hierarchical section boundaries;
- zero-based, half-open UTF-8 byte coordinates in normalized text;
- original UTF-8 byte offsets and quote hashes;
- equation, theorem/proposition, definition, proof, table, figure, footnote,
  and bibliographic-reference markers;
- a segment-by-segment original-to-normalized location map;
- Unicode normalization policy, whitespace policy, and formula representation;
- extraction warnings, declared parser confidence, and unsupported constructs;
- parser name/version/configuration/dependency hash; and
- source-artifact and normalized-artifact hashes.

Parser confidence is diagnostic metadata and never a warrant. A parser that
cannot provide a stable mapping may emit a quarantined normalization proposal,
but its output cannot enter accepted source-derived memory. Re-running the same
parser/configuration on identical bytes must produce identical canonical bytes
and hash.

## 3. Typed evidence units

One immutable envelope carries an explicit `unit_type`, source origin,
coordinates, provenance, disposition, and typed payload. Required types are:

- `source_passage`;
- `definition`;
- `theorem_or_proposition`;
- `assumption`;
- `equation`;
- `proof_step`;
- `empirical_or_numerical_result`;
- `bibliographic_reference`; and
- `model_proposed_claim`.

Every source-derived unit must resolve to a `SourceArtifact`,
`NormalizedDocument`, and exact `SourceSpan`. Its displayed text is derived;
the location mapping permits inspection of the authoritative original.

A `model_proposed_claim` must instead reference a model-call/proposal artifact,
carry `origin=model`, and retain `disposition=proposal`. It cannot claim a
source span merely because the model quoted text. A model may propose a link to
an existing evidence unit, but it may not create or alter source-derived units.

## 4. Claim and citation graph

Relations are immutable edges with one of these types:

- `supports`, `contradicts`, `defines`, `assumes`, `derives_from`, `cites`,
  `equivalent_to`, `specializes`, or `supersedes`.

Every edge records source and target IDs, origin, assertion coordinates where
applicable, extraction method, disposition, and verification/review records.
An explicit citation printed in a source is `source_asserted`; a parser-inferred
edge is `parser_proposed`; a model-generated edge is `model_proposed`; a human
curation edge is `human_asserted`. These states are not interchangeable.

An accepted source-derived edge establishes what the source says, not that the
mathematical relation is true or locally applicable. Load-bearing use still
requires the Phase 1 `SourceApplicabilityRecord` and trust policy.
Contradictory edges and units coexist; ingestion never silently reconciles or
deletes them.

## 5. Deterministic retrieval

The required baseline is a local SQLite FTS5 index using a frozen tokenizer,
normalization function, field weights, BM25 configuration, and query grammar.
The current Python runtime exposes SQLite 3.53.3 with FTS5 enabled, but the
implementation must preflight and record the actual SQLite version and compile
option rather than assume availability.

Canonical memory is not stored only in FTS. The index is rebuilt exclusively
from accepted/quarantined-policy-eligible canonical records and is identified
by an index-manifest hash. Retrieval records:

- canonical query text and query hash;
- retrieval method/version, SQLite version, tokenizer, weights, and corpus
  manifest hash;
- evidence-unit and source IDs;
- exact span IDs and coordinates;
- raw BM25 score plus a canonical serialized score representation;
- deterministic order: score, source ID, span start, then evidence-unit ID;
- all filters and quarantine decisions; and
- a complete retrieval-result manifest and hash.

Cross-runtime byte identity is claimed only for a pinned SQLite/tokenizer
identity. A version mismatch is an explicit reproducibility blocker, not an
opportunity to silently rebuild different rankings. No cross-platform equality
is required for raw floating-point BM25 scores. Acceptance requires Recall@5 of
1.0, MRR of at least 0.75, citation-resolution precision of 1.0, zero
quarantined evidence retrieved, and identical ordered evidence IDs and pack
hashes over three repeated runs and one restart.

Embeddings and an embedding-provider port are wholly deferred to Phase 4.

## 6. Evidence-pack construction

The pack builder accepts a retrieval manifest and explicit byte/token limits.
It emits canonical bytes plus an `EvidencePackManifest` containing included and
excluded unit IDs, order, exact source spans, query/index hashes, size accounting,
deduplication decisions, source-diversity decisions, and pack hash.

Rules are deterministic:

1. exclude disallowed quarantine classes;
2. retain contradictory evidence rather than selecting a preferred answer;
3. deduplicate identical source spans by content and coordinates;
4. enforce a configurable per-source cap before filling remaining capacity;
5. include provenance adjacent to every excerpt;
6. keep source text, normalized structure, and model commentary in separate
   labeled sections; and
7. treat instruction-like source text as quoted data with an injection warning,
   never as model or workflow policy.

No chat summary may replace original evidence. Optional summaries are separate
proposal artifacts and do not reduce the requirement to include cited source
units and exact spans.

## 7. Model boundary

The existing Phase 2 proposer/verifier workflow may receive an evidence-pack
artifact through a versioned request contract. Model output remains
proposal-only and cannot write repositories or create warrants.

Every source-dependent model claim must list evidence-unit IDs. Validation
fails before proposal import if an ID is unknown, fabricated, excluded, or not
present in the exact supplied pack. Citation validation confirms identity and
pack membership; it does not by itself confirm entailment or applicability.

The verifier receives a deterministic pack/context assembled independently of
the proposer narrative. Agreement by a same-model, same-provider verifier does
not change claim status and retains the Phase 2 independence dimensions.

No model or external API call is permitted in Phase 3A. Scripted value fixtures
exercise citation validation without invoking a model gateway.

## Gold corpus design

Infrastructure acceptance uses five project-authored synthetic plain-text
fixtures: primary, related, contradictory, malformed, and prompt injection. The
fixed queries and relevance judgments are frozen with the metric thresholds
above.

M. Jezek, J. Rehacek, and J. Fiurasek, “Finding optimal strategies for
minimum-error quantum-state discrimination,” arXiv:quant-ph/0201109, is retained
as a metadata-only generic fixture. Its `content_hash` is null and no PDF or
extracted text is committed until redistribution rights are confirmed. The
real-academic-corpus demonstration is Phase 4 work. Phase 3A does not attempt to
prove convergence of the paper’s iterative algorithm.

## Acceptance stop line

Phase 3A stops after one manually supplied corpus can be imported, normalized,
indexed, deterministically retrieved, packed, replayed after restart, and
passed through proposal-only citation validation. It includes no crawler,
automatic novelty/significance assessment, vector database, required embedding
service or port, PDF parser, formal/math tool, web/API surface, multi-agent
search, quantum solver, or Phase 3B/Phase 4 implementation.
