# Phase 3A Bounded Research-Memory Report

Status: accepted implementation evidence
Date: 2026-08-19

## Outcome

The bounded, manually supplied research-memory vertical slice is implemented.
It adds immutable source/provenance records, an internal deterministic
`plain-text-v1` parser, exact UTF-8 byte spans, source-derived evidence
proposals, origin-distinct evidence relations, a rebuildable SQLite FTS5/BM25
projection, deterministic evidence packs, exact citation validation, canonical
ResearchMemoryExport v1 interchange, durable events/replay, and a minimal
offline CLI.

Phase 1 entities and trust projections are unchanged. ResearchDossier v1 is
unchanged. Parser-derived evidence, relations, foreign memory, and scripted
model-shaped artifacts remain proposals and cannot create warrants or close
obligations.

## Entry and compatibility gates

- ADR-0012, ADR-0013, and ADR-0014 are accepted.
- README, AGENTS.md, the blueprint, architecture proposal, threat model,
  entity proposal, matrix, bounded prompt, and deferred-work records agree on
  the Phase 3A/3B/4 sequence while retaining the superseded revision-0.2
  roadmap history.
- The immutable `phase-2` tag remains at
  `f8531aefc39792ecf02c61f0019cea087ebf87f2`.
- The sealed Phase 2 status, v2 database, v3 database, and v3 report hashes
  remain respectively `c29c13d8...1ac05`, `4c1c402d...d064`,
  `30e0db8d...e94`, and `ff706139...8cb9`.
- All 101 pre-existing Phase 0–2 tests passed before implementation and remain
  unchanged.

## Implemented requirements

P3-001 through P3-023 and P3-025 through P3-055 are implemented by the 55
tests mapped in `REQUIREMENT_TEST_MATRIX.md`. P3-024 (embeddings and an
embedding-provider port) is intentionally deferred to Phase 4 and absent from
code, configuration, dependencies, and runtime calls.

The Phase 3A migration is
`migrations/phase3a/0001_research_memory.sql`. It creates append-only canonical
record, command, event, and foreign-import-proposal tables plus the rebuildable
FTS5 projection. Phase 2 continues to apply only migrations 0001–0003; the
Phase 3A adapter applies its separately checksummed namespace after opening the
durable local workspace.

The only Phase 2 source change closes its SQLite connection when migration
initialization raises before re-raising the same error. This removes a resource
leak without changing migrations, persisted state, provider behavior, or trust
semantics.

The public interchange schema is
`schemas/research-memory-v1.schema.json`. Internal frozen records remain
separate from canonical JSON mapping and hashing.

## Acceptance corpus and licensing

Infrastructure acceptance uses only five project-authored synthetic fixtures:
primary, related, contradictory, malformed PDF-shaped, and prompt-injection
sources. They carry `LicenseRef-AdaIvy-Synthetic-Fixture`, explicit private
evaluation/local retrieval/evidence-pack rights, and an allowed redistribution
status.

The malformed and prompt-injection artifacts are retained in CAS and
quarantined. They produced no normalized document, span, or evidence unit and
no quarantined artifact appeared in retrieval. The quantum paper is an opaque
metadata-only `arxiv:quant-ph/0201109` locator with `content_hash: null`,
unresolved redistribution status, and no committed PDF or extracted text.

## Retrieval and provenance results

The pinned runtime recorded SQLite 3.53.3 with FTS5 and tokenizer
`unicode61 remove_diacritics 0`.

| Measure | Result | Gate |
|---|---:|---:|
| Recall@5 | 1.0 | 1.0 |
| MRR | 1.0 | >= 0.75 |
| Citation resolution precision | 1.0 | 1.0 |
| Quarantined evidence retrieved | 0 | 0 |
| Three repeats plus one restart | identical ordered-ID and pack hashes | identical |
| Exact provenance round trips | 18 / 18 spans | 100% |

All four ordered-result-set hashes are
`sha256:08d8f51567341a9ab17b03b913f1e5409e2b751e1aa4b60db068de72c72cbb0c`.
All four pack-set hashes are
`sha256:0586e955336e2e7322168f784662ac5beafaaac26259e07933c1af1deb7b5631`.
Raw BM25 float equality is not claimed across platforms.

## Canonical acceptance hashes

- source manifest: `sha256:8a1be7f6009b5fded8b7dc37adf473030115c73f5ef9c8f05f9675959e986d8e`
- evidence manifest: `sha256:d7541ba0952407d1248b8d01ca177ebffdb95c83e8cbe02f776c84dbd73686b3`
- corpus/index manifest: `sha256:473dadcf3f48cf4aa61e443e74dd9a9600708d712046341a8705b8d5a8e2473d`
- retrieval manifest: `sha256:fe5e9da683bd1c858cee102306a6818f245760ff02575471d49ec08bd3092ae1`
- evidence-pack manifest set: `sha256:0586e955336e2e7322168f784662ac5beafaaac26259e07933c1af1deb7b5631`
- ResearchMemoryExport content hash: `sha256:99891f3b0acd8493adae7976caad8d493995adf2c68522bca2e8da6845e21e4c`
- memory-event replay hash: `sha256:66998142ca524886b021958c54a80cfbb77002ce1035892f4c26ea54ba362e6c`
- traceable-report hash: `sha256:881b2d0a85da1c9c57181c0aeb28ae6efccbc88e4a6521f6d29bd60856544ac9`

Recorded file hashes are:

- acceptance JSON bytes: `sha256:c0ea908f3b6f1c9fd19d83180f3e55f865238dfc4f96727048531d51bfe8c241`
- canonical export bytes: `sha256:f1b57c2cae96638a7545476722685f17eb7470c5b4d0a790ca788de8e8756272`

Raw SQLite file-byte identity is not an acceptance invariant because WAL
checkpoints and rebuildable FTS maintenance can alter physical layout without
changing canonical state. The ResearchMemoryExport and event-replay hashes are
the durable semantic replay seals.

The canonical export contains 96 typed records. Export/import preserved its
IDs, meaning, canonical bytes, and content hash. Regenerating the report from
`acceptance.json` produced byte-identical output.

## Validation

- 156 / 156 unit, integration, adversarial, migration, replay, and acceptance
  tests passed: 101 unchanged Phase 0–2 tests plus 55 Phase 3A tests.
- 19 / 19 Phase 0 harness checks passed.
- ResearchMemoryExport schema and every JSON fixture validated.
- Source, normalized, structure-map, location-map, evidence-pack, database,
  event, export, acceptance, and report surfaces were scanned for credential
  leakage; zero matches were found.
- The acceptance run executed with network socket creation disabled and
  recorded zero model or external API calls.

## Deferred stop line

Phase 3B formal/symbolic/numerical tools, proof assistants, meaning tests, and
certified counterexample workflows are not implemented. Phase 4 crawling,
remote acquisition, licensed academic-corpus evaluation, PDF/OCR/richer
parsing, embeddings, hybrid retrieval, citation traversal, novelty automation,
and broader research automation are not implemented. Web/API surfaces,
multi-agent search, PostgreSQL, and the quantum convergence solver remain out
of scope.

## Proposed next Phase 3B task

Prepare a bounded Phase 3B entry-gate and local adapter spike that compares one
deterministic formal checker/proof-assistant path against the existing known
theorem, mistranslation, false-universal, and representation-bridge fixtures.
Freeze semantic-fidelity, kernel/replay, sandbox, dependency/license, and
failure-retention acceptance tests before selecting or implementing the
adapter. Do not combine that task with Phase 4 acquisition or embeddings.
