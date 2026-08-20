# Phase 4B Acceptance-Threshold Inventory

Status: accepted with ADR-0028

Every threshold is exact. A later acceptance suite is the executable authority;
no prose term such as "bounded", "safe", or "deterministic" may weaken these
values.

## Fixture and correctness thresholds

| ID | Exact threshold |
|---|---|
| P4B-AT-001 | Project-authored fixture count equals 30. |
| P4B-AT-002 | Acquisition-policy fixtures equal 12: 3 allowed and 9 required denials. |
| P4B-AT-003 | Rich-parser fixtures equal 12: 4 HTML, 4 TeX, and 4 PDF. |
| P4B-AT-004 | Lifecycle/integration fixtures equal 6. |
| P4B-AT-005 | Authorized acquisition success accuracy equals 1.0. |
| P4B-AT-006 | Required acquisition-denial accuracy equals 1.0. |
| P4B-AT-007 | Parser disposition accuracy equals 1.0. |
| P4B-AT-008 | False acquisition authorizations equal 0. |
| P4B-AT-009 | False parser admissions equal 0. |
| P4B-AT-010 | Prohibited-rights actions and content writes each equal 0. |
| P4B-AT-011 | Admitted load-bearing segment anchor coverage equals 1.0. |
| P4B-AT-012 | Original-byte hash agreement equals 1.0. |
| P4B-AT-013 | Exact expected failure/quarantine reason accuracy equals 1.0. |
| P4B-AT-014 | Active-content, external-reference, shell, macro-execution, JavaScript, PDF-action, and embedded-file executions each equal 0. |
| P4B-AT-015 | Acceptance DNS, socket, HTTP, model, and external API calls each equal 0. |
| P4B-AT-016 | Deleted-source marker matches across managed content, plaintext, cache, index, export, temp, SQLite journal/WAL/SHM, and log scans equal 0 after completion. |
| P4B-AT-017 | Phase 3A writes caused by Phase 4B equal 0. |
| P4B-AT-018 | Applicability, warrant, admission, novelty, significance, publication, and redistribution promotions caused by acquisition or parsing each equal 0. |

## Per-resource and run bounds

| ID | Exact threshold |
|---|---|
| P4B-AT-019 | Normalized URL length is at most 2,048 UTF-8 bytes. |
| P4B-AT-020 | Approved origins per run are at most 4. |
| P4B-AT-021 | Requested resources per run are at most 100. |
| P4B-AT-022 | Redirects per resource are at most 5 and every hop is reauthorized. |
| P4B-AT-023 | Concurrent requests are at most 1 per origin and 4 globally. |
| P4B-AT-024 | Start rate is at most 1 request/second/origin. |
| P4B-AT-025 | Retry count is at most 2, only for idempotent GET transport errors, 408, 429, or 5xx. |
| P4B-AT-026 | Robots policy age is at most 86,400 seconds; missing, invalid, ambiguous, unreachable, 4xx, or 5xx robots state denies crawling. |
| P4B-AT-027 | Response-header bytes are at most 65,536. |
| P4B-AT-028 | Raw/compressed source bytes per resource are at most 2,097,152. |
| P4B-AT-029 | Decoded parser output per resource is at most 8,388,608 bytes and expansion ratio is at most 20:1. |
| P4B-AT-030 | Total decoded acquisition bytes per run are at most 67,108,864. |
| P4B-AT-031 | Parser wall time is at most 30 seconds, memory 536,870,912 bytes, writable temp 67,108,864 bytes, processes 16, and open files 64. |
| P4B-AT-032 | A parse proposal contains at most 4,096 segments, 2,048 formulas, 2,048 references, nesting depth 128, and 16,384 warnings. |
| P4B-AT-033 | Acquisition run wall time is at most 1,800 seconds and external spend is USD 0 in acceptance. |

## Determinism and preservation thresholds

| ID | Exact threshold |
|---|---|
| P4B-AT-034 | In-process accepted repeat count equals 3 and semantic bytes/hashes are identical. |
| P4B-AT-035 | Independent gate-process count equals 2 and semantic export hashes are identical. |
| P4B-AT-036 | Fresh-process restart, canonical replay, and reverse-order projection rebuild counts are each at least 1 and semantic bytes/hashes are identical. |
| P4B-AT-037 | Dependency wheel/hash/license/inventory mismatches equal 0; undeclared production third-party imports equal 0. |
| P4B-AT-038 | Existing Phase 3A Recall@5 remains 1.0, MRR remains at least 0.75, citation precision remains 1.0, and quarantined retrieval count remains 0. |
| P4B-AT-039 | Modified protected-evidence objects, existing canonical exports, and sealed fixture records each equal 0. |
| P4B-AT-040 | `make check`, repository invariants, Phase 4A tests, Phase 4B acceptance, strict raw-boundary tests, credential scan, protected-evidence verification, and `git diff --check` all pass; unavailable sealed environments are reported and never counted as passes. |

## Mandatory forbidden outcomes

The suite must prove impossible, not merely omit:

- fetch before exact origin/run, robots, terms, acquisition-right, and retention-right approval;
- private, loopback, link-local, multicast, unspecified, special-use, or DNS/
  connected-address mismatch access at any redirect;
- HTTP downgrade, URI user information, ambient proxy use, cross-origin auth or
  cookie forwarding, or unbounded retry;
- content visibility before all byte limits and content-object writes succeed;
- parsing after rights revocation, takedown, deletion request, truncation, hash
  mismatch, unsupported media, or policy-version mismatch;
- TeX compilation, include resolution, shell escape, macro programming, HTML
  active content, PDF actions/embedded files, or parser network access;
- reconstructed source plaintext in immutable audit/export/index/log state;
- silent best-effort parse when anchors, version, dependency, or sandbox is
  unavailable;
- parse or acquisition success implying applicability, warrant, admission,
  novelty, significance, redistribution, publication, or objective completion.
