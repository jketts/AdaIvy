# ADR-0028: Gate Phase 4B authorized acquisition and rich parsing

- **Status:** accepted for bounded Phase 4B implementation
- **Date:** 2026-08-20
- **Blueprint requirement:** Section 7 and Section 19 Phase 4; ADR-0026 WP1
- **Decision owners:** repository owner and researcher

## Context

Phase 4A supplies local per-use rights decisions, human applicability review,
deletable per-source content objects, and append-only audit identity. It does
not authorize URI resolution, crawling, robots processing, rich parsing, or
archives. Phase 3A stores only manually supplied UTF-8 plain text and treats
PDF and other media as quarantined. The benchmark paper therefore remains a
metadata-only record.

ADR-0026 orders Phase 4B acquisition and parsing before Phase 4C hybrid
retrieval. It normally permits one ADR plus tests per slice, but requires the
full gate package when work touches Phase 4A rights, deletable content, or
protected evidence. Phase 4B touches all three, so the full package in
`docs/phase-4b/` is normative for this slice.

The blueprint header and its inactive-C17 prose still say exploratory synthesis
is deferred. That description is stale: accepted ADR-0027 implements the
bounded synthesis package and its twelve scenarios. ADR-0027 is authoritative.
The accompanying descriptive blueprint correction is a documentation
reconciliation, not a prerequisite for or expansion of Phase 4B; it does not
rewrite the accepted ADR history.

## Options considered

| Option | Benefit | Risk | Decision |
|---|---|---|---|
| Unrestricted crawler plus parser pipeline | Broadest corpus | Bypasses origin, rights, deletion, and hostile-input controls | Rejected |
| Download directly into Phase 3A | Reuses ingestion | Makes revocable bytes immutable and undeletable | Rejected |
| Local-only rich parsing | Exercises parser boundary | Benchmark remains metadata-only; no acquisition path | Rejected as incomplete |
| Authorized acquisition port plus isolated rich-parser ports over Phase 4 content objects | Bounded, replaceable, auditable | More explicit gates and failure states | Selected |

## Decision

Implement Phase 4B as additive adapters over Phase 4A. Discovery metadata is a
candidate only. A fetch may begin only when a trusted human has authorized the
exact normalized origin and run, current terms and robots snapshots permit it,
and current Phase 4A rights independently allow both `acquisition` and
`storage/retention`. Only HTTPS GET is in scope. Every redirect, DNS answer,
connected address, response limit, and content type is revalidated. Network is
disabled by default and live acquisition is an explicit operator action.

Fetched bytes enter a source-specific Phase 4 deletable content object before
any parsing. They never enter Phase 3A CAS, canonical records, FTS tables,
immutable exports, logs, or caches. Acquisition attempts, including robots,
terms, DNS, redirect, timeout, size, policy, and deletion failures, are retained
as append-only machine-readable audit records without retaining prohibited
content.

Add replaceable parsers for authoritative structured HTML, bounded TeX/LaTeX
source, and born-digital PDF, in that preference order. OCR, archive expansion,
Office/EPUB, browser execution, and scanned-PDF interpretation remain deferred.
Each parser runs in an isolated no-network worker with a read-only input, empty
bounded temporary directory, fixed resource limits, and no active content,
external reference, executable, shell, macro-programming, JavaScript, or PDF
action support. TeX is data and is never compiled. A parser returns an
untrusted, versioned proposal containing deterministic segments, formulas,
references, warnings, and exact anchors to original bytes. Unsupported,
ambiguous, hostile, truncated, or unmappable content is quarantined.

Original bytes remain authoritative. A parse cannot create applicability,
mathematical warrant, graph admission, novelty, or significance. Load-bearing
use still requires an exact span and the existing human-only applicability
decision. Correction, withdrawal, revocation, takedown, deletion, changed
rights, or superseding applicability propagates through existing append-only
invalidation without rewriting history.

Production dependencies are allowed only after the dependency assessment names
exact artifacts, hashes, licenses, transitive closure, offline installation,
import boundary, and removal path. No candidate parser library is authorized by
name in this ADR. The standard-library acquisition policy engine and
deterministic injected offline transports add no dependency. Every documented
acceptance run uses only
project-authored fixtures and fake transports and makes zero network, model, or
external API calls.

The bounded implementation is activation-ready except for the separately
acknowledged external live gate. Its acquisition policy
engine and metadata workspace are executable, but its standard-library parser
is a fixture oracle and the production parser entry point fails closed. A new
dependency-free exact-source candidate parses only a strict UTF-8 HTML subset
and a non-expanding TeX subset with checked source-byte anchors. A separate
strict born-digital PDF candidate accepts only classic, flat, uncompressed
Base-14 text PDFs and anchors surfaced literal payloads exactly; general PDF
extraction remains unsupported. Self-contained source-bound bridges run all
three strict semantics through the named Darwin sandbox without exposing a
project path or weakening the read profile. Exact-image OCI bridges additionally
provide strict production resource enforcement. The
append-only metadata schema now atomically retains a versioned per-attempt
acquisition trace and a replayable, non-reconstructive rich parse proposal.
Proposal text, reference targets, warnings, transformations, segment IDs, and
parser object IDs are represented by hashes and bounded lengths; original
source bytes remain only in the deletable content boundary. Legacy v1 audit
exports remain importable without fabricating absent replay evidence. The six
lifecycle gate fixtures now execute end to end through the bounded production
service, persistence, deletion, restart, replay, and raw trust-validation paths.
An opt-in standard-library HTTPS adapter now exists behind a human-final permit.
Its content-hashed operator plan and CLI default to a deterministic
`not_executed` report and require a second exact acknowledgement before any
network operation. DNS runs in a killable bounded child, HTTP uses one absolute
deadline across dial, TLS, send, headers, and slow-drip bodies, and the redacted
report verifier checks its complete closed schema rather than trusting its hash
alone. The external live-network gate has not executed. Two independent
feasible-gate processes now produce identical canonical evidence, and the exact
OCI gate closes the remaining parser-sandbox controls.
A named Darwin sandbox probe now demonstrates actual OS denials for network,
filesystem writes, process forks, unapproved reads, and inherited secrets. It
is now accompanied by a protocol-connected fixture worker with parent-enforced
wall/output controls, POSIX CPU/open-file/process/file-size limits, and
per-process CPU plus sampled RSS measurements. Short-lived RSS spikes can evade
the sampler. The strict HTML, TeX, and PDF candidates are now connected workers.
An executable authorization measurement runs all twelve actual parser fixtures
through those source-bound workers with exact media/profile binding,
conservative content checks, fixture hashes, and result hashes. The two positive
PDF fixtures are deterministic valid strict-subset PDFs; the adversarial PDF
fixtures remain unchanged. The worker protocol now distinguishes a pinned
parser's content rejection from an infrastructure or worker failure, mapping
the former to a content-free `quarantined/rejected` result and preserving the
latter as `failed`. Current named-Darwin evidence records twelve exact
disposition matches out of twelve and zero false admissions, clearing the
actual-corpus parser-profile authorization measurement. No generic portable
claim is made for the Darwin worker. The exact Linux/arm64 OCI gate supplies
strict cgroup memory, network, filesystem, noexec temporary storage, secret,
process, CPU, and file controls for an explicitly configured production worker.
Activation evidence remains separate from parser results and cannot promote
trust.

## Consequences

- Phase 4B can acquire authorized source bytes and produce auditable rich-parse
  proposals without weakening Phase 4A or Phase 3A.
- The acquisition adapter is not a general web crawler and cannot discover its
  own origins or broaden a run.
- Rich parsing increases the hostile-input and dependency surface, so the
  complete Phase 4B gate must pass before production activation.
- Phase 4C may consume admitted Phase 4B parse projections only after this
  contract is frozen; Phase 4B creates no embedding, vector, or hybrid index.
- The synthesis package remains layered over the sealed Phase 6 workspace; this
  slice does not mutate its accepted fixtures or records.

## Explicit deferrals

Phase 4B does not add embeddings, vector or hybrid retrieval, novelty or
significance automation, a model/provider call, autonomous applicability,
scheduled research, multi-agent search, an HTTP API or UI, OCR, archive
expansion, arbitrary browser execution, a noncommuting solver, or search tiers
2--4. It does not enable publication or redistribution merely because content
was fetched or parsed.

## Validation and revisit trigger

Activation requires owner acceptance of this ADR and the complete
`docs/phase-4b/` gate package, an acceptance suite enforcing every
`P4B-AT` threshold and `P4B-SC` control, `make check`, the applicable sealed and
gate checks, unchanged protected evidence, offline dependency installation,
and two independent deterministic gate runs.

Revisit before adding a parser dependency, media type, archive or OCR path,
ambient proxy, credentialed origin, non-HTTPS transport, persistent Phase 4
index/cache, increased bound, autonomous origin selection, or any change to
Phase 4A rights, deletion, applicability, or protected-evidence semantics.
