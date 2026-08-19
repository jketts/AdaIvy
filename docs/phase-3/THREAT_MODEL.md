# Phase 3A Threat Model

Status: accepted for bounded implementation
Date: 2026-08-19

## Protected properties

- Original source bytes remain immutable and content-addressed.
- Derived text never silently replaces the original.
- Source spans resolve exactly and survive export/import.
- External/parser/model output cannot create trusted mathematics.
- Retrieval and evidence-pack composition are reproducible and auditable.
- Prompt-like source content cannot alter system policy or tool permissions.
- Licensing, quarantine, budget, and project boundaries cannot be bypassed.

## Trust zones

| Zone | Examples | Default trust |
|---|---|---|
| Operator-approved policy | schemas, parser allowlist, budgets, trust policy | trusted configuration after hash verification |
| Canonical source store | immutable bytes and source metadata | authentic bytes, not mathematically true content |
| Derived parser output | normalized text, markers, spans, relations | untrusted derived proposal until deterministic validation/review |
| Retrieval projections | FTS tables and scores | rebuildable, no warrant authority |
| Model/backend output | summaries, claims, relation suggestions | proposal only |
| Published report/context | rendered excerpts and citations | derived view requiring traceability |

## Threats and required controls

| Threat | Failure mode | Required design control | Acceptance evidence |
|---|---|---|---|
| Prompt injection in a paper | Source text tells a model to ignore policy or expose secrets | Quote source text in a data-only section; annotate injection markers; no tools or policy are derived from source text | Prompt-injection fixture remains literal content and cannot modify the request envelope |
| Unsupported or malformed input | Binary/PDF/invalid UTF-8 content reaches extraction | `plain-text-v1` accepts UTF-8 text only; unsupported or malformed inputs are quarantined without extraction | Malformed and unsupported fixtures create no spans or evidence units |
| Path traversal or symlink input | Import reads outside operator-selected file | Require regular non-symlink files; resolve and bind exact path before read; copy only verified bytes to CAS | Traversal/symlink adversarial tests |
| URI/metadata SSRF | A supplied locator causes network access to local/internal resources | Store an opaque user-supplied locator; perform local syntax validation only; prohibit DNS, HTTP, redirect, availability, and content checks | Network-disabled test records zero resolution/fetch attempts |
| Media-type spoofing | Executable or archive is labeled as PDF/text | Inspect magic bytes; compare declared/detected media types; quarantine mismatch | Mismatch fixture is not parsed |
| Oversized text input | Input exhausts memory or storage | Input byte, line, and output caps before normalization | Resource-limit fixture terminates safely |
| Hash/identity confusion | Different bytes overwrite one logical source | SHA-256 content identity, uniqueness constraint, immutable version edges, collision handling that refuses aliasing | Changed-byte fixture creates a distinct source version |
| Metadata spoofing | False authors/title/license are treated as verified | Record assertion source and reviewer; metadata remains proposed/unverified until checked | Export exposes metadata provenance and state |
| License leakage | Restricted full text enters reports/model context | Usage-rights policy on each source; context/export policy by purpose; exact audit of included spans | Restricted fixture is excluded with reason |
| Parser normalization drift | Upgrade changes spans or equations invisibly | Parser/config/dependency hashes; normalized-document versioning; no in-place replacement | Reparse under changed version creates a distinct derived artifact |
| Unicode/offset ambiguity | Citation points to the wrong characters | Frozen Unicode and newline policy; UTF-8 half-open byte offsets; quote hashes; round-trip tests | Every gold span round-trips exactly |
| Formula corruption | OCR/text extraction changes mathematical meaning | Preserve raw rendered region/LaTeX where available; formula warnings; unsupported formula output quarantined | Known equation fixture retains original locator and warning |
| Unsupported parser output promoted | Low-confidence or incomplete parse becomes accepted evidence | Confidence is diagnostic only; validation gates stable map, schema, and quarantine; human acceptance is separate | Unsupported marker cannot become trusted |
| Index poisoning | Quarantined/model text dominates retrieval | Index policy records allowed dispositions and origins; separate fields; deterministic filters | Quarantined/model units are excluded by default |
| SQL/FTS query injection | User query changes SQL or FTS semantics | Parameterized SQL; frozen query parser; reject unsupported syntax; record canonical query | Injection-like query is treated as text or rejected |
| Nondeterministic ranking | Equal scores reorder packs across runs | Pinned engine/tokenizer, canonical score serialization, deterministic ID/span tie-breakers | Repeat/restart produces identical hit and pack hashes |
| Fabricated citation ID | Model invents a plausible unit ID | Validate all IDs against the supplied pack manifest before import | Proposal import rejected with no mutation |
| Citation outside supplied context | Model cites real memory it did not receive | Require exact pack membership, not global existence | Out-of-pack citation rejected |
| Summary laundering | Generated summary is stored as source truth | Separate `model_proposed_claim`; prohibit source coordinates without a source unit; proposal disposition enforced | Summary remains proposal after replay |
| False entailment | Exact citation exists but does not support claim | Citation membership is not applicability; Phase 1 applicability obligation remains required | Inapplicable-source adversarial tests continue to pass |
| Contradiction erasure | Import merges inconsistent evidence into one resolved statement | Preserve immutable units/edges and explicit `contradicts`; no automatic reconciliation | Both sides remain retrievable and reportable |
| Cross-project leakage | Retrieval returns another project’s source | Project/visibility IDs on canonical rows, indexes, queries, and packs | Tenant/project isolation test |
| Crash between blob and commit | Orphan or duplicate source/evidence appears | Phase 2 CAS + transactional semantic commit + idempotency key; orphan remains inert | Crash/restart yields one semantic unit/event |
| Budget bypass | Parser/model retries exceed resource or token limits | Durable jobs and Phase 2 budget reservation/late-commit guards | Exhaustion prevents subsequent call/parse commit |
| Event tampering | Replay omits or reorders imports | Append-only events, canonical event hash, sequence verification | Restart replay hash is stable |
| Secret exposure | Credentials leak into metadata, parser environment, logs, or packs | No acquisition credential in Phase 3A; minimal environment; existing redaction scan extended to all new stores | Zero persisted-secret matches |

## Residual risks

- SHA-256 collision risk is accepted for this phase; collision evidence must
  fail closed rather than merge records.
- Plain-text marker inference may remain incomplete even when deterministic.
  Warnings and authoritative original bytes reduce, but do not eliminate,
  expert review.
- SQLite FTS5 ranking is reproducible only under the recorded engine/tokenizer
  identity. Cross-version equality is not assumed.
- A correctly quoted malicious instruction may still influence a model. Pack
  separation, explicit warnings, verifier isolation, and proposal-only output
  limit impact; they do not guarantee model noncompliance.
- Source authenticity and publisher metadata are not established merely by
  hashing operator-supplied bytes.

## Security acceptance gate

No Phase 3A implementation is acceptable unless malformed/untrusted content can
be quarantined without canonical trust mutation, source injection cannot gain
workflow authority, citation membership is enforced exactly, all new jobs obey
Phase 2 cancellation/recovery/budget rules, and the Phase 0–2 adversarial suite
continues to pass unchanged.
