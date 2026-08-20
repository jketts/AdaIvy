# Phase 4A Accepted Acceptance-Threshold Inventory

Status: accepted by repository owner on 2026-08-20

The pre-change threshold audit used gate report SHA-256
`ccd382ebab45eb6eab574ed0794c9252d60829ae20aa12ba270d92a20b8f7d56`
and machine-evidence SHA-256
`89544036e7f300851277b46b1b5403672ca1a6f2a8887366ffb8445b9d3fc117`.
The audit found no undefined Phase 4A acceptance threshold. “Strict” in the
owner approval refers exactly to this inventory and does not introduce a new
qualitative threshold.

## Numeric thresholds

| ID | Exact threshold |
|---|---|
| P4A-AT-001 | Fixture count equals 16. |
| P4A-AT-002 | `applicable` primary-class count equals 4. |
| P4A-AT-003 | `incompatible_hypotheses` count equals 4. |
| P4A-AT-004 | `definition_mismatch` count equals 2. |
| P4A-AT-005 | `scope_or_exception` count equals 2. |
| P4A-AT-006 | `misquotation` count equals 1. |
| P4A-AT-007 | `contradiction` count equals 1. |
| P4A-AT-008 | `prompt_injection` count equals 1. |
| P4A-AT-009 | `rights_or_takedown` count equals 1. |
| P4A-AT-010 | Exact provenance/span validation rate equals 1.0. |
| P4A-AT-011 | Human-review coverage for every `checked` applicability result equals 1.0. |
| P4A-AT-012 | False applicability accepts equal 0. |
| P4A-AT-013 | Prohibited-rights actions equal 0. |
| P4A-AT-014 | Quarantine escapes equal 0. |
| P4A-AT-015 | Exact expected-reason accuracy equals 1.0. |
| P4A-AT-016 | In-process canonical repeat count equals 3 and every semantic hash is identical. |
| P4A-AT-017 | Fresh-process restart count is at least 1, its semantic hash is identical, and acceptance traverses the same strict raw-byte verifier as initial verification. |
| P4A-AT-018 | Canonical replay count is at least 1, its bytes/hash are identical, and acceptance traverses the same strict raw-byte verifier as initial verification. |
| P4A-AT-019 | Reverse-order index/projection rebuild count is at least 1 and its semantic hash is identical. |
| P4A-AT-020 | Independent Phase 4 gate-process run count is at least 2 and all canonical export hashes are identical. |
| P4A-AT-021 | Existing FTS5 necessary-lemma Recall@5 is at least 1.0. |
| P4A-AT-022 | Existing FTS5 MRR is at least 0.75. |
| P4A-AT-023 | Local source size is at most 2,097,152 bytes. |
| P4A-AT-024 | Candidate review records per gate run are at most 256. |
| P4A-AT-025 | Derived review/export data per gate run is at most 67,108,864 bytes, enforced before every write by the real incremental deterministic exporter; byte 67,108,865 is rejected before visibility and failed temporary output is discarded. |
| P4A-AT-026 | Gate wall time is at most 600 seconds, enforced cooperatively by a monotonic internal budget throughout bounded work and independently by a parent-process hard timeout. |
| P4A-AT-027 | External spend equals USD 0. |
| P4A-AT-028 | Model/provider/API calls, external sources, crawls, model downloads, production Phase 4 entities/databases/schemas/migrations, Phase 5 actions, trust promotions, commits, tags, pushes, publications, and PRs each equal 0. |

## Categorical thresholds

Every item below must be `true`; there is no partial-credit state:

1. all 16 fixture canonical hashes match the accepted manifest;
2. corpus and fixture-schema file hashes match the manifest;
3. initial verification, import, replay, restart, and fresh-process acceptance
   share one strict raw-byte boundary; duplicate keys, unknown fields, malformed
   JSON, unknown versions, mixed versions, and schema-valid domain violations
   fail closed;
4. absent, ambiguous, expired, revoked, prohibited, and incompatible rights
   each block the requested use;
5. a model or automation actor cannot create `checked/applicable`; independently
   rehashed missing or inconsistent actor/authority mutations fail through both
   replay and restart;
6. rights and applicability outcomes are independently recorded;
7. append-only takedown/deletion history remains in the candidate export while
   prohibited source content is absent;
8. the separate export has exactly version
   `adaivy.phase4-gate-candidate-export.v1`;
9. all rejection reasons match the closed reason vocabulary and expected value;
10. unsupported/quarantined material is never retrievable;
11. zero production dependencies are added, and exactly five gate-only wheels
    match `requirements-phase4-gate-py314-macos-arm64.txt`, install offline into
    a disposable environment, and remain unavailable to production imports;
12. all controls `P4A-SC-001` through `P4A-SC-024` remain satisfied;
13. every current test, Phase 0 check, Phase 3A check, two sealed Phase 3B runs,
    sealed-v5 condition, schema/JSON validation, protected seal, credential scan,
    and `git diff --check` passes; and
14. verification leaves every protected historical report byte-identical; and
15. output is incrementally UTF-8 encoded, counted, hashed, and written without
    constructing the complete output string before the limit decision; internal
    expiry is cooperative and the parent subprocess timeout is the hard wall.

Categorical threshold 11 originally required “no new dependency is installed
or imported by the gate spike.” The owner-approved replacement above is bound
to approval SHA-256
`98244f19de93af73e220dd0d57b0a9b70921f0b8381e0e7b2cc2c2fa47b8846b`.
All other thresholds remain unchanged.

The fixture manifest at `fixtures/phase4-gate/manifest.json` is the machine-
readable copy of the numeric corpus and metric thresholds. Future deferred-
capability parameters are not Phase 4A acceptance thresholds.
