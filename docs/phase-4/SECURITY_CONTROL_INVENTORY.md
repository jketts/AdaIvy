# Phase 4A Accepted Security and Reproducibility Control Inventory

Status: accepted by repository owner on 2026-08-20; production authorization withheld

## Binding

This inventory binds ADR-0017 and ADR-0018 to the exact pre-approval artifacts:

- `docs/phase-4/ENTRY_GATE_REPORT.md` SHA-256
  `ccd382ebab45eb6eab574ed0794c9252d60829ae20aa12ba270d92a20b8f7d56`;
- `reports/phase-4-entry-gate/entry-gate.json` SHA-256
  `89544036e7f300851277b46b1b5403672ca1a6f2a8887366ffb8445b9d3fc117`.

Markdown locations name the pre-approval report section. JSON locations are
JSON Pointers in the pre-approval machine evidence. These controls approve the
Phase 4A boundary only. Future-capability parameters in the source artifacts
remain unapproved until a later owner review authorizes that capability.

## Controls

| ID | Accepted control | Exact pre-approval locations |
|---|---|---|
| P4A-SC-001 | Inputs are explicit local user-supplied regular files; symlinks and special files are rejected. | Report §“Acquisition, crawling, robots, and terms”; `/policies/acquisition` |
| P4A-SC-002 | A local source is at most 2,097,152 bytes. | Same report section; `/policies/acquisition/max_source_bytes` |
| P4A-SC-003 | Phase 4A performs no network acquisition, crawling, URI resolution, robots processing, remote API use, redirects, DNS, or scheduling. | Report §§1 and 8; `/selected_slice/excluded`, `/policies/network_and_crawling/phase4a_enabled`, `/policies/automation_and_stop_conditions/phase4a_autonomous_actions` |
| P4A-SC-004 | Only existing valid UTF-8 `text/plain` through `plain-text-v1` is eligible; every richer or active format is quarantined without extraction. | Report §“Parsing, hostile content, and resource limits”; `/policies/parsing` |
| P4A-SC-005 | Archive expansion and recursion are disabled in Phase 4A. | Same report section; `/policies/archives/phase4a_enabled` |
| P4A-SC-006 | Source bytes and extracted text are untrusted data, never instructions; they cannot change policy, invoke tools, disclose secrets, broaden authority, or grant trust. | Same report section; `/policies/hostile_content` |
| P4A-SC-007 | Rights are separate for acquisition, storage/retention, parsing, excerpting, embedding, model context, redistribution, and publication. | Report §“Corpus licensing and rights by use”; `/policies/rights/actions` |
| P4A-SC-008 | Rights values are `allowed`, `prohibited`, or `unresolved`; absence, ambiguity, expiry, revocation, prohibition, or incompatibility blocks the requested use. | Same report section; `/policies/rights` plus owner clarification |
| P4A-SC-009 | Rights require explicit human evidence/review, and SPDX terms are recording vocabulary rather than legal interpretation; AdaIvy makes no legal determination. | Same report section; `/policies/rights/human_review_required`, `/policies/rights/spdx_role` |
| P4A-SC-010 | Every rights/applicability/lifecycle decision records actor, exact reason, evidence, timestamp, version, and supersession linkage. | Report capability map and §§2, 3, 7; `/selected_slice/proposed_records`, `/policies/rights`, `/policies/applicability` plus owner clarification |
| P4A-SC-011 | Corrections, revocations, takedowns, deletion requests/completions, and restore actions are append-only; no historical record is rewritten. | Report §“Provenance, deletion, and takedown”; `/policies/provenance_and_takedown` |
| P4A-SC-012 | Takedown immediately suppresses parsing, retrieval, context, export, and publication. Historical identity remains visible, while prohibited source content is not retained. Legal hold blocks physical deletion. | Same report section; `/policies/provenance_and_takedown` plus owner clarification |
| P4A-SC-013 | Original content-addressed bytes are authoritative while permitted; exact byte spans and source hashes anchor derived evidence. | Report §§3, 4 and preservation boundary; `/policies/provenance_and_takedown/original_bytes_authoritative` |
| P4A-SC-014 | Rights approval and applicability approval are distinct records and neither implies the other. | Report capability map and §7; `/selected_slice/capabilities`, `/policies/applicability` plus owner clarification |
| P4A-SC-015 | Only a named human action may create `checked/applicable`; deterministic code may reject but cannot approve. | Report §“Applicability and human authority”; `/policies/applicability/checked_applicable_authority`, `/policies/applicability/deterministic_code` |
| P4A-SC-016 | Automated/model applicability output remains a proposal and cannot promote itself. Retrieval, parsing, embedding, model agreement, and formal checking are non-authoritative. | Same report section; `/policies/applicability/retrieval_parser_embedding_model_formal_checking` |
| P4A-SC-017 | Status vocabulary is `proposed`, `checked`, `rejected`, `unresolved`; the ten enumerated reason codes are closed and versioned. | Same report section; `/policies/applicability/statuses`, `/policies/applicability/reason_codes` |
| P4A-SC-018 | Phase 4 uses additive versioned records and a separate `phase4-review-v1` export; Phase 0-3B formats are not reinterpreted. Initial verification, import, replay, restart, and fresh-process acceptance use one strict raw-byte boundary and return a detached verified snapshot. | Report capability map and synthetic gate evidence; `/selected_slice/proposed_export_schema`, `/selected_slice/proposed_records` |
| P4A-SC-019 | Unknown, malformed, duplicate-key, or mixed record/export versions fail closed. Whole-envelope Draft 2020-12 schema validation is followed by domain, graph, history, and hash validation; schema validity alone never establishes acceptance. | Report gate conditions and synthetic gate evidence; owner-approved schema decision |
| P4A-SC-020 | Canonical identity includes semantic schema/policy/record/reviewer content and excludes timestamps, elapsed time, process IDs, temporary paths, row order, database layout, scheduler state, and measured scores; excluded operations remain separately hashed. | Report proposed capability map; `/policies/canonical_identity` |
| P4A-SC-021 | Existing FTS5 remains the lexical baseline; indexes are rebuildable projections and cannot mutate canonical state. No embedding, vector, or hybrid index is part of Phase 4A. | Report §“Embeddings, indexes, and retrieval determinism”; `/policies/indexes_and_hybrid`, `/policies/embeddings/phase4a_enabled` |
| P4A-SC-022 | Phase 4A adds zero production dependencies. Gate validation uses exactly five owner-approved, hash-locked binary wheels only in an isolated disposable CPython 3.14/macOS 11+/ARM64 environment: `jsonschema`, `attrs`, `jsonschema-specifications`, `referencing`, and `rpds-py`. Source distributions/builds, unsupported platforms, production imports, ordinary-development installation, and changes to Phase 2 provider requirements are prohibited. | Owner amendment SHA-256 `98244f19de93af73e220dd0d57b0a9b70921f0b8381e0e7b2cc2c2fa47b8846b`; dependency assessment; platform requirements manifest |
| P4A-SC-023 | One gate run is capped at 256 review records, 67,108,864 derived bytes, 600 seconds, and USD 0 external spend. The actual exporter incrementally UTF-8 encodes, counts, hashes, and writes through one bounded sink, then atomically publishes only a completely verified artifact. A monotonic cooperative budget checks bounded work; an independent parent-process timeout is the hard termination boundary. | Report §“Automation, scheduling, budgets, secrets, and audit” and synthetic gate evidence; `/policies/scheduling_and_budgets/phase4a` |
| P4A-SC-024 | Phase 4A uses no secret, model/provider call, production database/schema/migration, external source, publication, commit/tag/push/PR, or Phase 5 action; protected reports remain byte-identical. | Report §§8, complete verification, and scope; `/scope_guards` |

## Deferred controls are not capability approval

The pre-approval artifacts also enumerate possible future network, robots,
parser-isolation, archive, embedding, hybrid-ranking, retry, credential, and
audit controls. They remain documented minimum guardrails only. No corresponding
adapter, dependency, spike, or production capability is authorized by this
inventory. Any change to this inventory or activation of a deferred capability
requires renewed owner approval.

## Owner-approved amendment after pre-commit audit

The original P4A-SC-022 text was: “Phase 4A adds no dependency. Any later
dependency requires exact pins/hashes, transitive licenses/notices, runtime
behavior, offline replay, vulnerability/cost review, and removal plan before
installation.” The repository owner replaced only that gate-validation clause
with the exact five-wheel boundary above on 2026-08-20. The approval text has
SHA-256 `98244f19de93af73e220dd0d57b0a9b70921f0b8381e0e7b2cc2c2fa47b8846b`.
Production remains dependency-free for this slice.
