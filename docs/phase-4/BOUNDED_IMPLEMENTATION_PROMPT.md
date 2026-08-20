# Next Bounded Production Task: Phase 4A Local Rights and Applicability Review

Status: **passed entry gate; prospective production scope only**

This prompt defines the next bounded task. It does not execute or authorize
implementation merely by existing in the repository. Begin only when the
repository owner explicitly invokes it.

## Accepted baseline and evidence

Start from repaired `main`
`e7db0ffa2d3fe4609c8a62642ec70fc5343776e3`. Preserve repair commit
`beae447cf38328d7021643e6adbbb75cc42e97e1`, annotated tag
`phase-3b-canonical-stability-v1`, and original `phase-3b` tag target
`226b47863f565c9c5a7dc7ac9ac08d490420ecf2`.

Read and verify these accepted gate artifacts before changing production code:

| Artifact | SHA-256 |
|---|---|
| `docs/adrs/0017-phase4a-local-rights-applicability-review.md` | `78719c5723dd13a4f401c477b8dcc8ecce368ff83faea843acb07ae22761e659` |
| `docs/adrs/0018-phase4-gate-security-reproducibility-controls.md` | `b5321b3846029bfbd203adcd73e18e77640820ee6fd15cbc95c1546801da53f4` |
| `docs/phase-4/SECURITY_CONTROL_INVENTORY.md` | `91e33b025dc65414d51735bfaf978a36eb26c064f0bc81470930f47d2f55001b` |
| `docs/phase-4/ACCEPTANCE_THRESHOLD_INVENTORY.md` | `1d28107aa339caff20bbd706a41dc267bea70a79d8f05031825e9ded387a6283` |
| `docs/phase-4/DEPENDENCY_LICENSE_ASSESSMENT.md` | `9d60becb5e49ec601a46d90cbf097a2919029b3567b228a693cabf5c6af30a83` |
| `docs/phase-4/REQUIREMENT_TEST_MATRIX.md` | `b0e7df79fa0e05986c69fccdf215dc7ae5f9c419bce69706fe462ff7be4fb61c` |
| `requirements-phase4-gate-py314-macos-arm64.txt` | `5467b0a521e823b183622961ad4a18aa8536a9172afd2c3ecffb10ffc5436295` |
| `fixtures/phase4-gate/corpus.json` | `d168974199b17a847c4280a6ad2c6affee87188e198603b970251723abebb524` |
| `fixtures/phase4-gate/manifest.json` | `aff0338510b876df4c727b2f048272e1f28af8bbad6a448d90f878494c3623e7` |
| `fixtures/phase4-gate/cases.json` | `638b8705695239c63087b0232790cd4351d873ccd65f3dd6bf4f1fa7b7d8c7f3` |
| `schemas/phase4-gate-fixture-v1.schema.json` | `ad52d76139362380d89bea28c2399cd703cc2ab7dab298fa175b40b086537858` |
| `spikes/phase4_gate/gate_spike.py` | `c7c9af20db5c8d80d9c3a3d585170aa6a1237d956ff751c65352de9aff214832` |
| `tests/test_phase4_gate.py` | `b3a0815bfe68ae378574972c4fe41fb40f183a57ce2e5f7703641525a9e2907f` |

The accepted nonproduction candidate export hash is
`sha256:b9120dacc09262594932bee8bc535e51f0f6a2ea2b94b8c4e0e32d63bbe4a7ed`.
Stop on any mismatch. Do not repair, regenerate, or reinterpret gate evidence
inside the production task.

## Implement exactly one slice

Implement **Phase 4A local rights and source-applicability review** only.
Supported inputs remain explicit local, user-supplied regular files already
eligible for Phase 3A `plain-text-v1`, at most 2,097,152 bytes. Reuse the
existing Phase 3A source-reference, source-artifact, CAS, exact-span, evidence-
unit, FTS5, and quarantine boundaries without changing their meaning.

Add only these versioned concepts:

1. `SourceRightsDecision`: separate decisions for acquisition,
   storage/retention, parsing, excerpting, embedding, model context,
   redistribution, and publication. Values are `allowed`, `prohibited`, and
   `unresolved`.
2. `SourceLifecycleAction`: append-only correction, revocation, takedown,
   suppression, restore, legal-hold, deletion-request, and deletion-completion
   events.
3. `EvidenceCard`: an exact source-artifact/evidence-unit/span reference with
   imported statement, hypotheses, definitions, scope, and exceptions. It is
   source-derived evidence, not an applicability approval or warrant.
4. `ApplicabilityReview`: `proposed`, `checked`, `rejected`, or `unresolved`
   plus exactly the reason vocabulary accepted in control `P4A-SC-017`.
5. `Phase4PolicySnapshot`: content-hashed schema, rights, applicability,
   lifecycle, and canonical-identity policy versions referenced by every
   Phase 4A decision.

Every decision/action records actor, exact reason, evidence, timestamp,
version, and supersession linkage. Records are immutable and append-only.
Unknown fields, malformed payloads, and unknown or mixed versions fail closed.

## Persistence and interchange

- Add one checksum-protected additive migration named
  `phase4/0001_rights_applicability_review.sql` behind existing workspace
  ports. Do not rewrite or reinterpret Phase 0-3B tables or records.
- Add the minimum repositories/services needed for the five concepts above.
- Add a separate canonical `phase4-review-v1` export/import surface. Do not
  change ResearchDossier v1, ResearchMemoryExport v1, or FormalCheckingExport
  semantics or hashes.
- Canonical identity follows `P4A-SC-020`. Operational time/path/process/store
  observations remain present under a separate operational hash.
- Derived suppression and retrieval projections are rebuildable. They never
  become canonical source or trust state.

## Rights, lifecycle, and deletion behavior

- Never infer rights from possession, accessibility, metadata, or another use.
- Absent, ambiguous, expired, revoked, prohibited, or incompatible rights
  block the requested action.
- Rights evidence is a human-reviewed record, not a legal determination.
- Takedown immediately suppresses the source from parsing, retrieval, model
  context, export, and publication projections.
- Preserve append-only audit identity without retaining source content after a
  valid policy decision prohibits continued retention.
- Legal hold blocks physical deletion. Physical deletion requires distinct
  request and completion actions. Restore requires a new reviewed action.

## Applicability authority

- Only an explicit named-human command may create `checked/applicable`.
- Automated/model assessments, imports, and external artifacts remain
  proposals and cannot promote themselves.
- Rights approval and applicability approval remain distinct.
- Checked applicability requires exact evidence/span, bibliographic identity,
  imported statement, hypothesis compatibility, definition mapping,
  scope/exceptions, and implication obligation review.
- Retrieval, parsing, model agreement, formal checking, and confidence never
  establish applicability or create an `EpistemicWarrant`.

## Minimal interface

Extend the existing CLI only as needed to:

- append and inspect a rights decision;
- append and inspect a lifecycle action;
- create and inspect a source-derived evidence card;
- propose, human-check, reject, or leave unresolved an applicability review;
- export, import/replay, and inspect `phase4-review-v1`; and
- rebuild suppression/index projections from canonical state.

No web UI, HTTP API, worker scheduler, background job, or autonomous action is
part of this slice.

## Dependencies and execution

Add no runtime or development dependency. Use the existing Python/SQLite/CAS
boundary and standard library. Do not install, download, import, or call a
crawler, remote acquisition client, rich parser, archive library, embedding
model/runtime, vector database, reranker, model/provider SDK, or research agent.

Use only project-authored synthetic fixtures. Do not process real copyrighted,
sensitive, or remotely acquired research content.

## Acceptance

Implement tests and evidence for every control `P4A-SC-001`–`P4A-SC-024` and
threshold `P4A-AT-001`–`P4A-AT-028`. At minimum verify:

- a maximum local source size of exactly 2,097,152 bytes (2 MiB), accepting the
  boundary and rejecting 2,097,153 bytes before parsing;
- at most 256 review records, accepting 256 and rejecting 257;
- at most 67,108,864 bytes (64 MiB) of export/output data, enforced by the
  actual incremental deterministic exporter before each UTF-8 byte write;
  accept the boundary, stop before byte 67,108,865, hash exactly the bytes
  written, discard failures, and publish verified output atomically without
  first constructing the complete serialized output;
- at most 600 seconds of execution under a cooperative monotonic internal
  deadline checked throughout bounded work and an independent parent-process
  hard timeout; do not claim cooperative checks can preempt arbitrary blocking
  code;
- exactly USD 0 model/provider/API cost and an empty external-call inventory;
- all 16 accepted fixtures and their hashes;
- exact spans and a full canonical audit export containing provenance, rights,
  applicability proposals/decisions, lifecycle events, corrections,
  supersessions, revocations, deletions, and takedowns, with complete actor,
  actor-type, authority, reason, evidence, timestamp, version, order, link,
  use-scope, target, and original semantic-hash fields;
- distinct permitted, explicitly prohibited, missing/unknown, expired, revoked,
  and requested-use-incompatible rights outcomes, all non-permitted outcomes
  failing closed at the fixed fixture evaluation timestamp;
- byte-immutable append-only correction/revocation/takedown/deletion/restore
  behavior with monotonic order, unique IDs, valid targets, acyclic links,
  complete tombstones, and deterministic replay;
- source-content removal with retained non-content audit identity;
- human-only final applicability authority across every outcome; model,
  automation, and system outputs remain proposals with no final-status value;
- one strict raw-byte acceptance boundary used by initial verification, import,
  replay, restart, and fresh-process verification: enforce the input cap,
  decode strictly, validate the exact whole-envelope Draft 2020-12 schema,
  enforce all domain/actor/authority/rights/applicability/graph/history
  invariants, and verify the canonical envelope hash last; schema validation
  alone is not domain acceptance and the accepted snapshot must not alias
  caller-controlled mutable data;
- strict duplicate-key decoding and all
  hashed malformed, unknown-field, missing-field, wrong-type, mixed-version,
  duplicate-ID, dangling-link, cycle, reordered-history, mutated-history, and
  nonhuman-final adversarial cases, including independently rehashed missing
  `actor_id`, missing `authority`, source-proposal authority, invalid
  actor/authority, nonhuman-final, mandatory-audit-field, and actor/reference
  inconsistencies through both replay and restart;
- separate export round trip, three repeats, two independent runs, one fresh-
  process restart, one replay, and one reverse-order projection rebuild;
- unchanged FTS5 Recall@5 1.0 and MRR at least 0.75;
- zero prohibited rights actions, false applicability accepts, quarantine
  escapes, trust promotions, model/API calls, network actions, and new
  production or ordinary-development dependencies (the accepted gate-only
  validator environment remains isolated); and
- exact report/export consistency with no protected-evidence mutation; and
- deterministic no-sleep cooperative-expiry and disposable parent hard-timeout
  tests, both proving failed or partial output is never accepted or published.

Run the complete documented Phase 0-3B verification, two sealed Phase 3B v5
runs and replay, all recorded v5 conditions, JSON/schema validation, protected
seals, persisted credential scan, and `git diff --check` in disposable state.

## Hard stop

Do not implement or enable external acquisition/crawling, robots processing,
rich/active parsers, archive expansion, embeddings, vector or hybrid retrieval,
model/provider calls, research automation, scheduling, autonomous
applicability, quantum discrimination, or other Phase 5 work.

Stop after this single Phase 4A slice and its acceptance evidence. Any control,
record meaning, dependency, authority, or scope not named above requires renewed
owner review and a new bounded prompt.
