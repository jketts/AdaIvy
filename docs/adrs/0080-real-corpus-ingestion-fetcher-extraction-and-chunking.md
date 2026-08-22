# ADR-0080: Real corpus ingestion — snapshot fetcher, extraction toolchain, bulk rights, silo bridge, chunked retrieval

- **Status:** accepted
- **Date:** 2026-08-22
- **Supersedes (in part):** ADR-0067 — specifically its no-fetcher clause
  ("no network fetcher for a snapshot archive exists in this package at all")
  and its metadata-only/plain-text-only parsing ceiling. Everything else in
  ADR-0067 stands: option C (one authorized bulk open-access snapshot), licence
  diligence before acquisition, human archive and tranche selection, the
  manual applicability ceiling, and "a snapshot is an acquisition, not a
  crawl."
- **Plan slice:** `docs/CAMPAIGN_DEPTH_AND_BREADTH_PLAN.md` Slice 13
- **Blueprint requirement:** Section 7.1 (crawlers produce candidates, never
  trusted documents), Section 7.3 (retrieval strategy), ADR-0064 (named
  processor per disclosing use), ADR-0072 §7 (policy-derived rights with
  quarantine)
- **Decision owners:** repository owner

## Context

ADR-0067/ADR-0072 built the persistent corpus service but left it deliberately
unable to fill itself: no snapshot fetcher existed, only `text/plain` and
`text/markdown` could be parsed, retrieval embedded one vector per whole
document, the tranche ceiling was pinned at 2,048 documents, and the ADR-0067
arXiv metadata store remained a disconnected silo. The Slice 13 exit criterion
is that one operator command ingests several hundred licensed full-text papers
from an allowlisted snapshot into a retrievable generation and a second run
ingests only deltas.

## Decision

### 1. Snapshot fetcher, behind the existing gate

`corpus_service/fetcher.py` implements live snapshot acquisition behind the
unchanged `pending_owner_activation` record
(`config/corpus-service-snapshot-activation-v1.json`, hash-pinned; still
pending as shipped). `fetch_snapshot` refuses without an ACTIVE record, the
exact acknowledgement string, and the human operator identity.

- **Allowlist pinned in code.** `ALLOWLISTED_SNAPSHOT_ORIGINS` is a closed
  tuple (arXiv and OpenAlex origins). An off-allowlist origin refuses before
  any request, and the refusal is itself appended to the ledger.
- **Pinned pacing.** One connection, ≥ 3,000 ms between requests
  (`FETCH_MIN_REQUEST_INTERVAL_MILLISECONDS`, `FETCH_MAX_CONCURRENT_CONNECTIONS
  = 1`). The pacer's clock and sleep are injected; elapsed time never enters a
  content hash.
- **Bytes land like the local-archive path.** Each response is verified
  against the archive manifest's per-document sha256 and byte count, then
  stored write-once in the grow-only object store.
  `ObjectStoreArchiveSource` then serves ingestion with zero network access —
  ingestion cannot tell fetched bytes from locally supplied bytes.
- **Resumable, delta-only.** Documents whose exact bytes are already stored
  are skipped without a request; an interrupted tranche resumes where it
  stopped and a repeat fetch makes zero requests.
- **Everything recorded.** A new append-only `fetches` ledger records every
  request's origin, URL, byte count, and outcome (closed vocabulary:
  `fetched`, `hash_mismatch`, `refused_off_allowlist`, `transport_error`),
  plus a per-run summary. Failures are retained, never discarded.
- The live transport is stdlib `urllib` with redirects refused, https only,
  and a bounded read; it is constructed only on the gated CLI path. All tests
  use injected fake transports; the offline gate performs zero network I/O.
- The activation record's `max_tranche_documents`/`max_tranche_total_bytes`
  pins bound **live acquisition volume** and are unchanged.

### 2. Extraction toolchain port (PDF and LaTeX-source)

`corpus_service/extraction.py` defines the `DocumentExtractor` port: media
types in, extracted UTF-8 text out, with a closed identity
`{tool, version, binary_sha256}`. Adapters:

- **Identity** (`text/plain`, `text/markdown`) — the pre-ADR-0080 behavior,
  now stated as an identity transformation.
- **LaTeX-source** (`text/x-tex`, `application/x-latex`) — a deterministic,
  versioned, stdlib-only in-repo reduction; no external binary.
- **Pinned external tool** (e.g. `pdftotext` for `application/pdf`) — an
  explicit operator opt-in naming the binary path, its expected sha256, and
  its expected version; absent, differently hashed, or differently versioned
  binaries are coded refusals (`extractor_not_pinned`), following the pinned
  LaTeX-typesetter pattern. Execution is bounded (timeout, output cap) and
  never part of the default registry.
- **Fixture** — a deterministic mapping for offline tests.

Spans remain `utf8_exact_char_spans_v1` — exact character offsets carried with
the sha256 of their exact substring — but over the **extracted** text. The
extractor identity and the extracted-text hash are recorded in the
`spans_parsed` ledger payload and in every generation entry (generation
manifest schema bumped to `…generation-manifest.v2` with `extracted_sha256`
and `extraction` fields; for identity documents `extracted_sha256 ==
source_sha256`). `PARSABLE_MEDIA_TYPES` widens through the registry in use;
a media type without a registered extractor still quarantines as
`unsupported_media_type`, and an extraction failure quarantines as
`parse_failure` — recorded, retained, excluded.

### 3. Bulk rights derivation (unchanged mechanism, stated scope)

Per-document rights remain a deterministic function of the human-authored
content-hashed policy and the exact per-document licence metadata in the
archive/snapshot manifest (`licence`, `licence_url`) under ADR-0072 §7. This
ADR adds no inference: classification is exact licence-string matching against
the explicit policy rule table; a conflicting licence URL, an unknown licence,
or a missing licence quarantines exactly as before. No threshold exists to
tune. The multi-hundred-document acceptance exercises this in bulk, including
quarantines at volume.

### 4. Silo bridge: arXiv metadata into the corpus service

`corpus_service/bridge.py` (`corpus-service bridge-arxiv`) imports verified
ADR-0067 arXiv corpus records into the persistent corpus service as
**descriptive-metadata documents**: the quotation-capped title, the
quotation-capped abstract (ADR-0067's reader-facing caps and pinned ellipsis),
and the link-out abstract URL, under the record's own metadata licence
(CC0-1.0). Rights restrictions are preserved: the policy rule classifying the
metadata licence must state `full_text: false` — a policy that would store
full text for descriptive metadata is refused
(`bridge_metadata_full_text_forbidden`) before any bytes move. The e-prints
themselves remain unacquired; reaching them is the separately gated fetch
path. The bridge is deterministic and delta-only through the ordinary tranche
machinery.

### 5. Chunked embeddings and per-chunk evidence cards

`corpus_retrieval/chunked.py` adds chunked projections
(`adaivy.corpus-retrieval-chunked-projection.v1`): deterministic fixed-size
character windows with declared overlap (`fixed_char_window_v1`; window ≤
8,192 chars, ≤ 4,096 chunks/document, both pinned) over the extracted text.
The chunking parameters are declared in the projection manifest; chunk spans
are the retrieval unit; retrieval returns per-chunk evidence cards carrying
exact offsets, the exact text hash, the extractor identity, and the unchanged
trust fields (`untrusted_inspiration_candidate`, applicability unresolved,
`creates_warrant: false`). A document may yield many cards. Partition purity
and the per-document ADR-0064 embedding-rights check are identical to v1;
deltas replay stored vector artifacts with zero provider calls.

The v1 whole-document projection is retained unchanged for identity-extracted
documents and **refuses** extractor-derived documents rather than mis-anchor
their offsets.

### 6. Operator-budgeted tranche ceiling

`max_documents` in the tranche config becomes operator-budgeted:
`MAX_TRANCHE_DOCUMENTS = 2_048` remains the shipped default and the live
acquisition activation pin; a new structural ceiling
`MAX_TRANCHE_DOCUMENTS_STRUCTURAL_CEILING = 65_536` is pinned in code and no
config may state a wider bound.

### Performance note (recorded because it touched shared modules)

Two O(n²) hot paths made a 300-document ingest take minutes: per-document
rights-shard rescans and whole-ledger re-verification on every append. The
shard-membership scan is now cached per writer instance (one transaction, one
exclusive ingest lock), and `append_ledger` verifies the sealed tail record it
chains onto instead of the whole file — the full chain is still re-verified by
`read_ledger` on every read path, so in-place edits anywhere still surface as
`corpus_ledger_chain_broken` before any history is used. No verification any
reader relies on was removed.

## What this ADR does not do

It does not activate live acquisition — the shipped activation record remains
`pending_owner_activation` and its content hash is unchanged. It does not
relax quarantine, licence diligence, human archive/tranche selection, the
named-processor rule, or the applicability ceiling. It does not authorize
crawling, result following, or autonomous origin selection (ADR-0068/ADR-0051
territory, Slice 14). It creates no warrant, no premise, no novelty or
significance assessment.

## Consequences

- The generation manifest schema is v2; fresh data roots produce v2
  generations. No production data root predates this change.
- A live operator can, once the owner activates the gate, run
  `corpus-service acquire` → `corpus-service ingest` and reach a retrievable
  generation of several hundred licensed full-text documents; the offline
  acceptance proves the same path against a fake transport, including
  interruption/resume and delta-only second runs.
- PDF extraction quality depends on the pinned external tool; a bad
  extraction quarantines rather than admitting garbage, and the extractor
  identity in provenance makes any later re-extraction an auditable new
  transformation rather than a silent change.

## Blueprint deviation

None. Volume arrives untrusted, through validation and ingestion, exactly as
Section 7.1 requires.

## Validation and revisit trigger

`make check` runs the offline acceptance: gated fetch with a rate-limit
observation and a ledgered off-allowlist refusal, a 300-document synthetic
snapshot fetched (with one interruption and resume), ingested, and re-ingested
delta-only; LaTeX/PDF-fixture extraction with recorded extractor identity;
bulk rights with quarantine; the arXiv bridge import; and chunked
multi-chunk retrieval. Revisit when Slice 14 (discovery at scale) needs
origins beyond the pinned allowlist, or if a takedown/licence-withdrawal case
shows extracted-text objects or chunk vectors surviving active use.
