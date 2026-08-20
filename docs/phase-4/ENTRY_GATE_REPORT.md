# Phase 4 Entry-Gate Report

Status: **passed**
Date: 2026-08-20
Gate scope: proposal and verification only; no Phase 4 production implementation

## Result

The Phase 3B canonical-stability prerequisite is resolved. The repaired baseline
is `e7db0ffa2d3fe4609c8a62642ec70fc5343776e3`, the repair commit is
`beae447cf38328d7021643e6adbbb75cc42e97e1`, and the annotated repair tag is
`phase-3b-canonical-stability-v1`. The original annotated `phase-3b` tag remains
at `226b47863f565c9c5a7dc7ac9ac08d490420ecf2`.

The repository owner accepted the bounded Phase 4A policy direction on
2026-08-20 without authorizing production implementation. ADR-0017 and
ADR-0018 capture that approval and bind it to stable control and threshold
inventories plus the full pre-approval gate-artifact hashes. Sixteen synthetic
fixtures are individually content-hashed, and the nonproduction candidate
spike passes every frozen contract over independent runs and restart.

All nine entry-gate conditions now pass. The gate result is **passed** and the
bounded prompt has been converted to the prospective Phase 4A production task.
No production Phase 4 entity, schema, migration, service, database, or workflow
was implemented, and the prompt does not begin implementation by itself.

## Baseline and branch verification

| Check | Evidence | Result |
|---|---|---|
| Phase 4 branch head | `7832f9f5f7d0cd504a28107fbf0b489522652e46` | pass |
| Repaired `main` and merge base | `e7db0ffa2d3fe4609c8a62642ec70fc5343776e3` | pass |
| Ahead/behind against `main` | `1/0` | pass |
| Upstream | none | pass |
| Replayed Phase 4 documentation commit | old `17baf546`, new `7832f9f` | pass |
| Repair commit in ancestry | `beae447cf38328d7021643e6adbbb75cc42e97e1` | pass |
| Repair tag target | `e7db0ffa2d3fe4609c8a62642ec70fc5343776e3` | pass |
| Original tag target | `226b47863f565c9c5a7dc7ac9ac08d490420ecf2` | pass |
| Initial worktree/index | clean | pass |

## Accepted prospective first production slice

The owner selected exactly one slice: **Phase 4A local rights and source-applicability
review**.

The slice would accept only manually supplied regular local files already
eligible for `plain-text-v1`. It would add immutable, reviewable rights
decisions, evidence cards, source-applicability reviews, and source lifecycle
actions. A human would decide whether an exact imported statement applies to a
local claim under compatible hypotheses, definitions, scope, and exceptions.
It would not crawl, resolve a URI, add a parser, embed text, add a vector index,
call a model, or automate research authority.

This is the smallest complete Phase 4 step because it addresses the rights and
applicability controls required before broader corpus acquisition while using
the already accepted source bytes, spans, FTS5 index, evidence proposals, and
Phase 1 applicability policy. Retrieval, parsing, or formal checking still
cannot create an applicability approval or warrant.

### Accepted capability map

| Capability | Existing authority | Proposed additive record/port | Trust and persistence |
|---|---|---|---|
| Rights by intended use | `LicenseMetadata`, original CAS bytes | `SourceRightsDecision`, `SourceRightsPolicy` | Human-reviewed; append-only; unresolved use fails closed |
| Lifecycle and takedown | immutable source/reference records | `SourceLifecycleAction`, suppression projection | Append-only action/tombstone; indexes are rebuilt projections |
| Evidence card | evidence unit/span/relation | `EvidenceCard`, `EvidenceCardRepository` | Source-derived proposal only |
| Applicability review | Phase 1 `SourceApplicabilityRecord` and trust policy | additive `ApplicabilityReview` with reason code | Only a named human reviewer may mark checked/applicable |
| Policy provenance | canonical event/config patterns | `Phase4PolicySnapshot` | Content-hashed, versioned, referenced by every decision |
| Interchange | existing dossier/research-memory exports | separate `phase4-review-v1` export | Does not change Phase 0-3B canonical formats |

Proposed migration name: `phase4/0001_rights_applicability_review.sql`.
It would add append-only tables and foreign keys to existing opaque IDs without
rewriting existing records. This is a plan only: no schema or migration was
created by this gate.

Canonical identities would include schema/policy versions, referenced semantic
IDs and hashes, rights values, reason codes, reviewer identity, and the signed
review content. They would exclude timestamps, elapsed time, process IDs,
temporary paths, row order, database layout, scheduler state, and measured
scores. Excluded operational values would remain auditable under a separate
operational hash, following repaired Phase 3B practice.

## Accepted policies and deferred boundaries

The Phase 4A controls in this section are accepted exactly as enumerated in
`SECURITY_CONTROL_INVENTORY.md`. Values describing possible future network,
parser, archive, embedding, or hybrid capabilities remain minimum guardrails,
not approval to implement or even spike those deferred capabilities.

### 1. Acquisition, crawling, robots, and terms

- Phase 4A remains local-only. It accepts explicit regular files, refuses
  symlinks and special files, retains the Phase 3A 2 MiB source limit, and
  performs no URI resolution or network operation.
- A future network adapter must be separately authorized per origin and remain
  outside the trusted core. It may use HTTPS on port 443 only, a normalized
  hostname allowlist, no URI user information, and no ambient proxy settings.
- Every DNS result and connected address, including every redirect, must be
  rejected if it is loopback, link-local, private, multicast, unspecified, or
  otherwise special-use. Redirects are capped at five and revalidated; auth,
  cookies, and origin-bound headers never cross origins.
- `robots.txt` is necessary but not authorization. The adapter follows RFC
  9309 but is stricter: missing, unreachable, invalid, ambiguous, 4xx, or 5xx
  robots state means no crawl. A successful policy is cached for at most 24
  hours. An explicit disallow denies access. Robots content is untrusted data.
- Site terms and source rights are independent of robots. Before enabling an
  origin, a human must approve a content-hashed terms snapshot containing URL,
  retrieval time, applicable actor/use, reviewer, and decision. Any changed or
  unavailable terms suspend the origin.

### 2. Corpus licensing and rights by use

Each source version receives a human decision for eight independent actions:
acquisition, storage/retention, parsing, excerpting, embedding, model context,
redistribution, and publication. Each action is `allowed`, `prohibited`, or
`unresolved`, with evidence URI/hash, attribution/notices, jurisdictional or
contract constraints, reviewer, effective time, and superseded decision.
`unresolved` and `prohibited` both block that action. SPDX expressions are
recording vocabulary, not legal interpretation. Project-authored synthetic
fixtures retain `LicenseRef-AdaIvy-Synthetic-Fixture`; no academic bytes may be
committed or redistributed without source-specific permission.

### 3. Provenance, deletion, and takedown

Original bytes remain authoritative and content-addressed. A takedown creates
an append-only lifecycle action and immediate suppression projection for
parsing, retrieval, contexts, exports, and publication. Derived indexes are
rebuilt without the source. Prior reports retain the source hash and a visible
unavailable/takedown state; history is never silently rewritten. Legal hold
prevents physical deletion. Physical CAS deletion requires a distinct approved
retention job and completion event. Restore requires a new reviewed action;
every dependent rebuild records the policy/action IDs.

### 4. Parsing, hostile content, and resource limits

- Phase 4A adds no parser. Only valid UTF-8 `text/plain` is eligible; all HTML,
  PDF, XML, Office, EPUB, image, OCR, and archive inputs remain quarantined.
- Document bytes and extracted text are data, never instructions. Prompt-like
  content is retained verbatim for provenance, labelled untrusted, and cannot
  alter policies, invoke tools, reveal secrets, broaden network scope, or grant
  trust. Evidence packs delimit and attribute each span. Human applicability
  review remains mandatory.
- A future parser must run non-root in an isolated no-network worker with a
  read-only input, new empty writable temp directory, no executable/macro/JS or
  external-reference support, and bounded CPU, memory, output, and wall time.
  It must produce an exact byte-to-normalized-span map or quarantine the item.
- Future non-archive response limits: 2 MiB compressed/raw input, 8 MiB decoded
  output, expansion ratio at most 20:1, 30 seconds wall time, 512 MiB memory,
  and 64 MiB writable temporary storage.
- Archives remain excluded from Phase 4A. A future archive spike is capped at
  one nesting level, 128 regular-file members, 2 MiB per member, 16 MiB total
  decoded bytes, 20:1 aggregate expansion, and 255-byte names. Absolute paths,
  traversal, duplicate/case-colliding names, links, devices, pipes, encrypted
  members, unknown sizes, and nested archives are rejected before extraction.
- The standard-library `HTMLParser` is not accepted as a rich parser because
  its permissive recovery cannot by itself establish exact mathematical
  structure or source mapping. Python's archive filters are also insufficient
  alone; official documentation requires inspection and external resource
  bounds for untrusted archives.

### 5. Embeddings, indexes, and retrieval determinism

Embeddings and vector retrieval are excluded from Phase 4A. The documentation-
only future candidate is
`sentence-transformers/all-MiniLM-L6-v2` at revision
`b9db1e8a0d3a51769172ba8546f282a73f066e47`. It is not approved: its Apache-2.0
model-card label, training-data notices, artifact hashes, transitive runtime
licenses, 256-wordpiece truncation, and deterministic replay still require a
complete audited manifest and a local spike. No model files were downloaded.

If later approved, embedding executes locally, offline, CPU-only, from pinned
`safetensors` blobs with every blob/tokenizer/config hash recorded. Dynamic
code, external inference, provider APIs, unpinned aliases, auto-download,
quantization, and nondeterministic kernels are prohibited. A separate decision
would be required for any external provider and would have to address source
rights, data retention, credentials, pricing, and reproducibility.

FTS5 remains the lexical baseline and records SQLite version, compile options,
tokenizer, corpus manifest, query, and explicit semantic-ID tie-break. Indexes
and embeddings are rebuildable projections, never canonical evidence state.
An embedding manifest would include source/evidence-unit hashes, exact input
text hash, model/runtime/blob hashes, dimension, dtype, normalization, and
batch policy.

A future hybrid spike would use exact-rational reciprocal-rank fusion with
`k=60`, equal lexical/vector weights, and at most 50 candidates from each
index. It must compute comparison values with integer arithmetic over common
denominators and tie-break by source-artifact ID, byte start, byte end, then
evidence-unit ID. Raw floating scores remain operational only.

### 6. Evaluation corpus and frozen thresholds

The proposed project-authored corpus contains 16 cases: four applicable, four
incompatible-hypothesis, two definition-mismatch, two scope/exception, one
misquotation, one contradiction, one prompt-injection, and one
rights/takedown case. Cases may exercise more than one adversarial property but
must retain distinct expected outcomes. It also freezes a renamed-result case,
a malicious markup/archive case for quarantine, and restart/replay/index-
rebuild variants. Exact bytes and expected manifests must be content-hashed
before production code.

Required Phase 4A thresholds are: 100% provenance/span validation; 100% human
review coverage for checked applicability; zero false applicability accepts;
zero prohibited-rights actions; zero quarantine escapes; all rejection reason
codes exact; identical canonical bytes/hashes over three repeats, one restart,
one replay, and one index rebuild; and no regression from the accepted FTS5
necessary-lemma recall@5 of 1.0 or MRR of 0.75. A future hybrid candidate must
equal all safety/determinism thresholds and improve a separately frozen primary
retrieval metric without worsening any adversarial case.

### 7. Applicability and human authority

The existing statuses remain `proposed`, `checked`, `rejected`, and
`unresolved`; Phase 4 adds a required reason classification:
`applicable`, `incompatible_hypotheses`, `definition_mismatch`,
`scope_or_exception`, `misquotation`, `contradiction`, `insufficient_evidence`,
`rights_blocked`, `source_withdrawn`, or `malicious_content`.

Only a named human reviewer may create `checked/applicable`, after verifying
the imported statement, bibliographic identity, hypotheses, definition map,
scope/exceptions, exact evidence span, local implication, and open/discharged
obligation. Deterministic code may reject malformed or policy-blocked inputs
but cannot approve applicability. Retrieval, parser output, embeddings, model
agreement, and formal checking remain non-authoritative.

### 8. Automation, scheduling, budgets, secrets, and audit

Phase 4A has no autonomous scheduling, network, model, or publication action.
It is bounded to 256 review records, 64 MiB of derived review/export data, ten
minutes per local gate run, and zero external spend. A future research planner
may propose work only; a human authorizes each origin/crawl run, rights change,
applicability approval, and publication action.

A future network run is capped at one concurrent request and one request per
second per origin, four globally, 100 requests, 64 MiB total decoded bytes, and
30 minutes. Only idempotent GET is retryable, at most twice, for transport
errors, 408, 429, or 5xx. `Retry-After` is honored up to 24 hours; otherwise
bounded exponential delays are operational metadata. Stop immediately on
robots/terms/rights uncertainty, origin or budget exhaustion, redirect/DNS
policy failure, credential exposure, policy hash mismatch, parser quarantine,
or repeated failure.

Phase 4A requires no secret. Future credentials must be explicit per-adapter
environment inputs, absent from URIs, canonical records, logs, subprocess
inheritance, and artifacts. TLS verification is mandatory. Networking is
disabled by default and enabled only for an approved adapter policy. Audit
records retain sanitized canonical request metadata, destination and resolved
address, redirect chain, response status/headers allowlist/body hash, robots
and terms decision IDs, budgets, retries, failures, and policy version; they
never retain authorization, cookies, or secret-bearing query values.

### 9. Dependencies, licenses, hashes, and reproducibility

Phase 4A adds no production dependency. Standards-conforming gate-only schema
validation uses exactly five owner-approved, hash-locked binary wheels in an
isolated disposable CPython 3.14/macOS ARM64 environment. The manifest is
`requirements-phase4-gate-py314-macos-arm64.txt`; source builds, unsupported
platforms, ordinary-development installation, and production imports fail
closed. Production continues to use the existing Python standard library,
CAS/workspace, and SQLite FTS5. Every later parser,
model, vector library, or service requires exact version/revision, source and
wheel/blob hashes, complete transitive license/notices, training-data and model
license assessment where applicable, supported-platform manifest, offline
rebuild proof, runtime/network behavior, vulnerability review, cost, and a
removal/rollback plan before installation. Floating versions and aliases fail
closed. Failed candidates and missing tools remain machine-readable evidence.

## Threat model and preservation boundary

Threats include hostile source bytes and prompt injection, archive bombs and
path traversal, parser escapes, SSRF/DNS rebinding/redirect abuse, ambiguous
licenses and changed terms, secret leakage, poisoned indexes, non-deterministic
ranking, source deletion without provenance, automated trust promotion, and
resource/cost exhaustion. The proposed controls above preserve original bytes,
quarantine unsupported inputs, isolate derived projections, require explicit
rights and human applicability review, bind operations to policy hashes, and
retain append-only failures. All Phase 0-3B trust, replay, runtime, and formal-
checking seals remain unchanged.

## Owner decisions

| Decision | Accepted option | Status |
|---|---|---|
| First slice | Local rights + human applicability review | accepted in ADR-0017 |
| Schema/interchange | Additive v1 records, fail-closed versions, separate export | accepted in ADR-0017 |
| Rights/lifecycle | Per-use fail-closed rights and append-only correction/revocation/takedown/deletion | accepted in ADR-0017 |
| Applicability authority | Closed reason vocabulary and human-only checked/applicable | accepted in ADR-0017 |
| Fixtures/thresholds | Exact 16-case corpus and P4A-AT-001–028 | accepted and passing |
| Deferred capabilities | No crawler, robots, rich parser, archive, embedding, vector/hybrid index, model/API, automation, scheduling, or Phase 5 work | accepted stop line |
| Security/reproducibility | Exactly P4A-SC-001–024; changes require renewed owner review | accepted in ADR-0018 |

Pre-approval report SHA-256:
`ccd382ebab45eb6eab574ed0794c9252d60829ae20aa12ba270d92a20b8f7d56`.
Pre-approval machine-evidence SHA-256:
`89544036e7f300851277b46b1b5403672ca1a6f2a8887366ffb8445b9d3fc117`.

## Phase 4 synthetic gate evidence

| Evidence | Result |
|---|---|
| Fixture corpus | 16/16 Draft 2020-12 schema-valid; exact class counts; every canonical hash matches manifest |
| Contract/adversarial cases | 31/31 passed; every descriptor/raw artifact individually hashed, including seven independently rehashed actor/authority replay mutations |
| Manifest canonical hash | `sha256:a4125f09770a65250784e873fbf42a6cff248b3f4776f34783e67af110d27854` |
| Candidate export hash | `sha256:b9120dacc09262594932bee8bc535e51f0f6a2ea2b94b8c4e0e32d63bbe4a7ed` |
| Provenance/human coverage/reason accuracy | 1.0 / 1.0 / 1.0 |
| False accepts/prohibited actions/quarantine escapes | 0 / 0 / 0 |
| Fail-closed rights | permitted, explicitly prohibited, missing/unknown, expired, lifecycle-revoked, and use-incompatible are independently modeled and tested |
| Human authority | complete 20-cell actor × outcome matrix; all 15 nonhuman cells remain proposal-only, all five outcome cells have an explicit human-final mapping, and unknown actors fail closed |
| Lifecycle | correction, revocation, deletion, and takedown prove immutable append, monotonic chains, acyclic links, complete tombstones, and replay |
| Audit export | 68 full canonical records; duplicate/dangling/broken/cyclic/reordered/mutated/mixed history rejected |
| Determinism | three repeats, two independent processes, fresh-process restart, replay, reverse rebuild all identical; initial/replay/restart/fresh-process acceptance uses the same strict raw-byte verifier |
| Resources | exact 2 MiB/256-record/64 MiB boundaries and +1 rejection pass through actual bounded paths; cooperative monotonic expiry and independent 600-second parent hard timeout pass; USD 0 |
| Normal-run observations | maximum/total fixture source 1/16 bytes; 16 reviews; 68 export records; 67,724 output bytes; output stream `sha256:5701e6996fb5fd1e254a85009973e29728658c63f35ff71c496f799ee2e773d0` over 8,153 writes; maximum observed elapsed time 3.090 seconds; USD 0; empty external-call inventory |
| Dependencies/licenses | zero production dependencies; exactly five approved gate-only wheels verified and installed offline |
| Validator provenance | CPython 3.14.4, `cpython-314-darwin`, macOS 26.5.2 ARM64, pip 26.0.1; requirements `5467b0a5…`; wheel inventory `ee7e0354…`; all five PyPI provenance endpoints HTTP 200 with one attestation bundle each |
| Production prompt SHA-256 | `da1ab3a700d8926abc51849983b1b8ee5ddcf5127251f80de330ab13fcc420c2` |

### Final P1 enforcement corrections

Initial verification, import, replay, restart, and fresh-process verification
now enter through the same public raw-byte boundary. It applies the input cap,
strict UTF-8/JSON and duplicate-key rejection, exact profile/version checks,
whole-envelope Draft 2020-12 validation, domain invariants, record/reference/
graph/history checks, and the envelope hash in fail-closed order. Schema
validation alone is not domain validation. The returned accepted snapshot is a
detached copy and retains no mutable alias to caller-controlled input.

Seven missing or inconsistent actor/authority variants were independently
rehashed before testing: missing `actor_id`, missing `authority`, source
authority changed to `proposal`, an invalid actor/authority pairing, nonhuman
final authority, a mandatory audit-field omission, and an actor/reference
inconsistency. All seven were rejected through both the normal replay and
restart entry points before state acceptance; the valid export passed initial,
replay, restart, and fresh-process verification.

The 64 MiB control is enforced by the real deterministic streaming writer.
`JSONEncoder.iterencode()` output is UTF-8 encoded, counted, written, and hashed
incrementally through the same bounded sink used by the exporter; no complete
serialized output string exists before the size decision. Exactly 64 MiB is
accepted and byte 67,108,865 is rejected before it becomes visible. Output is
published atomically only after serialization, bounds, hash, and strict
verification succeed; overflow, expiry, and other failure discard temporary
output and publish neither an accepted nor partial artifact.

The internal monotonic deadline is cooperative and is checked throughout input,
iteration, validation, graph/history, serialization, write, and finalization
boundaries. It does not claim to preempt arbitrary blocking code. The parent
subprocess timeout is the independent hard termination boundary. A deterministic
injected-clock operation expired mid-write without sleeping and left no file or
temporary artifact; a disposable overlong child was hard-terminated and reaped
by its parent.

## Pre-commit audit repair history

The read-only pre-commit audit returned `changes_required`. Its findings remain
part of the gate history and are resolved as follows:

1. incomplete export provenance: replaced ID-only projections with complete
   canonical provenance, rights, applicability, lifecycle, evidence-link, and
   tombstone records plus a strict export verifier;
2. nonhuman final statuses: every model, automation, and system outcome is now
   proposal-only with `final_status: null`; final classifications require a
   separate human record;
3. collapsed rights failures: expiry uses explicit validity plus the fixed
   evaluation timestamp, revocation is append-only, use incompatibility is
   derived independently, and missing differs from explicit prohibition;
4. weak lifecycle/adversarial coverage: 31 hashed cases now cover malformed and
   duplicate JSON, schema errors, both mixed-version directions, one mismatched
   record, duplicate/dangling/cyclic/reordered/mutated history, seven fully
   rehashed actor/authority failures, correction, revocation, deletion, and
   takedown;
5. permissive schema: every security-relevant object is closed and validated by
   `Draft202012Validator` after draft and internal-reference checks;
6. unmeasured resources: actual input, record, streaming output, elapsed-time,
   and cost observations are recorded separately from semantic hashes; the real
   exporter and bounded reader exercise every exact boundary, cooperative
   expiry, atomic failure, and the independent parent hard timeout; and
7. incomplete production prompt: all production-critical numeric, authority,
   audit, rights, lifecycle, schema, and adversarial requirements are now stated
   explicitly.

The audit result remains historically valid for the prior candidate. It did not
indicate a Phase 0-3B regression and did not authorize production work.

## Read-only documentation evidence

- RFC 9309, Robots Exclusion Protocol: <https://www.rfc-editor.org/rfc/rfc9309.html>
- RFC 3986, URI generic syntax: <https://www.rfc-editor.org/rfc/rfc3986.html>
- RFC 9110, HTTP semantics: <https://www.rfc-editor.org/rfc/rfc9110.html>
- RFC 6890, special-purpose address registries: <https://www.rfc-editor.org/rfc/rfc6890.html>
- Python `tarfile` security guidance: <https://docs.python.org/3.14/library/tarfile.html>
- Python `zipfile` security guidance: <https://docs.python.org/3.14/library/zipfile.html>
- Python `HTMLParser`: <https://docs.python.org/3/library/html.parser.html>
- SQLite FTS5: <https://www.sqlite.org/fts5.html>
- SPDX specifications/licensing: <https://spdx.dev/use/specifications/>, <https://spdx.dev/learn/areas-of-interest/licensing/>
- Pinned embedding candidate documentation only: <https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/b9db1e8a0d3a51769172ba8546f282a73f066e47>

No site was crawled, no corpus was acquired, no URI was resolved by AdaIvy, no
model/provider/API was called, and no embedding/model artifact was downloaded.

## Complete baseline verification

The documented commands were rerun after updating this decision package, with
disposable output roots where the README paths would overwrite protected
reports.

| Verification | Result |
|---|---|
| Unit/integration/adversarial/evaluation tests | 191/191 passed |
| Phase 0 harness | 19/19 passed |
| Phase 1 demo, inspect, round trip | passed; `sha256:ee299e0a6d6295dd005f0292ab5b0ac89320862ed1853935ddc0da5d5b9f96fa` |
| Phase 2 deterministic report | passed; audit replay `sha256:8c185deeb88a6e981bfd5376c868d62163a748f686bf04e5004b89c5d68bea9c` |
| Phase 3A demo, inspect, repeats/restart | passed; export `sha256:99891f3b0acd8493adae7976caad8d493995adf2c68522bca2e8da6845e21e4c`; recall@5/MRR 1.0/1.0 |
| Phase 3B sealed host run 1 | passed; export `sha256:78a08bc23ba34bcc2d78d11a5e75c4c6da053d6aa95c15d4de4f2046a3c3636d` |
| Phase 3B sealed host run 2 | passed; same export and all nine semantic finding IDs/hashes identical |
| Phase 3B restart/replay and trust boundary | preserved; zero trust promotions, model calls, or external API calls |
| Recorded v5 conditions | 29/29 true; sealed image digest exact; no containers remain |
| V4 artifacts and protected seals | 53/53 v4 artifacts and 10/10 named seals match |
| JSON/schema validation | 101 applicable JSON documents parse and 12 schemas pass schema checks; intentional malformed Phase 3B and malformed/duplicate-key Phase 4 fixtures retained and rejected by their dedicated checks; hostile remote `$ref` is rejected without retrieval |
| Persisted credential scan | 200 files; zero exact or token-pattern matches |
| Protected report hashes | all 199 files unchanged before/after |
| Diff validation | `git diff --check` passed; only authorized Phase 4 gate artifacts changed |

Verification result: **passed**. Gate conditions 1-9 are satisfied.

## Historical blocked result (2026-08-19)

The previous report was blocked for two independent reasons:

1. no Phase 4 slice, rights policy, dependency/parser/embedding/acquisition
   boundary, schemas, migrations, fixtures, thresholds, threat model, or owner
   acceptance existed; and
2. independent Phase 3B runs produced different canonical semantic identities
   because timing and termination-race observations were included.

That report evaluated the original Phase 3B baseline
`226b47863f565c9c5a7dc7ac9ac08d490420ecf2`, ran 173 tests and Phase 0 at
19/19, and recorded status `blocked`. Its report SHA-256 was
`1cd5b4f55e9fe0cc4d216e4cf842364df48c309103af626e28c6416d4488aac1`; its
machine-evidence file SHA-256 was
`5baf3a1fce46a9ab072d63b271811a7eca9a8366d78338cb6f8e2a0b2ed4133c`.
The canonical-stability reason was resolved by `beae447` and `e7db0ff`. The
governance/specification reasons were then converted into the decision-ready
package whose pre-approval report and machine hashes are recorded above. Owner
approval, accepted ADRs, hashed fixtures, candidate checks, and final
verification have now resolved those later blockers. This historical result is
evidence, not a claim that the repaired or current baseline failed.

The intermediate 2026-08-20 result was also `blocked`: the repaired baseline
passed 182 tests and sealed replay, but owner acceptance, accepted ADRs, hashed
fixtures, and candidate spikes were absent. That exact pre-approval state is
preserved by report SHA-256 `ccd382ebab45eb6eab574ed0794c9252d60829ae20aa12ba270d92a20b8f7d56`
and machine-evidence SHA-256
`89544036e7f300851277b46b1b5403672ca1a6f2a8887366ffb8445b9d3fc117`.
