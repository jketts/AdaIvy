# Phase 4B Security-Control Inventory

Status: accepted with ADR-0028

| ID | Control |
|---|---|
| P4B-SC-001 | Network defaults disabled; only explicit operator-created runs may instantiate the outward adapter. |
| P4B-SC-002 | Permit only normalized HTTPS URLs without user information, fragments, non-443 ports, ambiguous host syntax, or ambient proxy configuration. |
| P4B-SC-003 | Require an exact normalized-origin allowlist and current trusted-human authorization for the run. |
| P4B-SC-004 | Require current content-hashed terms and robots snapshots; robots is necessary but never sufficient authorization. |
| P4B-SC-005 | Require separate current Phase 4A `acquisition` and `storage/retention` rights before each request and write. |
| P4B-SC-006 | Resolve all addresses and verify the actual connected peer; deny loopback, private, link-local, multicast, unspecified, special-use, and address mismatch. |
| P4B-SC-007 | Reapply origin, DNS/peer, robots, terms, rights, header, and budget checks on every redirect. |
| P4B-SC-008 | Never forward authorization, cookies, origin-bound headers, or referrer data across origins. |
| P4B-SC-009 | Enforce request, redirect, concurrency, rate, retry, header, byte, time, and total-run bounds before visibility. |
| P4B-SC-010 | Record every failure and missing-tool result without fabricating response content. |
| P4B-SC-011 | Store source bytes only in an independently deletable, non-globally-deduplicated Phase 4 per-source object. |
| P4B-SC-012 | Keep source/reconstructive plaintext out of Phase 3A, metadata SQLite, immutable audit, canonical exports, logs, caches, and persistent indexes. |
| P4B-SC-013 | Suppress reads immediately on correction, revocation, withdrawal, takedown, deletion request, changed rights, or policy mismatch. |
| P4B-SC-014 | Reconcile interrupted deletion without restoring content; append completion only after a complete managed-store scan. |
| P4B-SC-015 | Treat all content, filenames, metadata, markup, formulas, references, parser messages, and embedded instructions as untrusted data. |
| P4B-SC-016 | Select parser by verified media/profile and content checks; mismatch, ambiguity, polyglot, truncation, or unsupported encryption quarantines. |
| P4B-SC-017 | Execute parsers non-root with no network, read-only input/root, empty bounded noexec temp, no ambient environment/secrets, bounded resources, and captured output. |
| P4B-SC-018 | Disable HTML scripts, styles with fetches, forms, events, active URLs, external entities/resources, browser execution, and active DOM interpretation. |
| P4B-SC-019 | Never compile TeX; reject shell escape, executable primitives, file/network includes, unsafe macro definitions, uncontrolled recursion, and external resource resolution. |
| P4B-SC-020 | Reject PDF JavaScript, launch/actions, embedded files, multimedia, external references, encryption without an approved profile, malformed cross-reference structures, and decompression-limit violations. |
| P4B-SC-021 | Preserve original bytes and record parser name/version/hash, dependency/environment identity, input hash, transformations, warnings, disposition, and operational result. |
| P4B-SC-022 | Require deterministic exact byte/page/object anchors for every admitted load-bearing segment; otherwise quarantine it. |
| P4B-SC-023 | Keep extraction fidelity, source applicability, mathematical warrant, and graph admission independent; parser output begins as a proposal. |
| P4B-SC-024 | Canonical semantic hashes exclude timestamps, durations, PIDs, temporary paths, row order, and scheduler state while a separate operational hash covers them. |
| P4B-SC-025 | Initial verification, import, replay, restart, and rebuild share one bounded strict raw-byte validation boundary with duplicate-key and unknown-field rejection. |
| P4B-SC-026 | Acceptance uses only project-authored content and deterministic fake resolver/transport/parser controls; socket and DNS creation are denied and audited. |
| P4B-SC-027 | Every direct/transitive production dependency is exact-version/hash pinned, license recorded, installed offline with `--require-hashes`, import-isolated, and removable. |
| P4B-SC-028 | Protected evidence and all existing exports, schemas, migrations, fixtures, and sealed records remain byte-identical. |
| P4B-SC-029 | Phase 4B exposes no embeddings, vector/hybrid retrieval, OCR, archive expansion, model/API, autonomous authority, scheduler, UI, publication, or redistribution path. |
| P4B-SC-030 | Every threshold boundary has an exact-at-limit pass and one-over-limit fail test; every forbidden outcome has a reachable adversarial attempt and a fail-closed assertion. |
