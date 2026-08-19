# ADR-0014: Original source bytes remain authoritative across research memory

- **Status:** accepted
- **Date:** 2026-08-19
- **Blueprint requirement:** C1, C3, C12, §§7.1–7.4 and 11.5
- **Decision owners:** researcher and repository maintainer

## Context

Document parsers can reorder text, lose formulas, merge regions, or infer
structures incorrectly. Models can generate plausible summaries and citations.
The existing Phase 1 `Evidence` record is intentionally small and its
`source_ref` string cannot express durable page/region/normalization mappings.
Changing it would risk Phase 1 trust semantics and existing dossier hashes.

ResearchDossier v1 also has no canonical research-memory package. Adding source
records directly to that schema would be a breaking contract change.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Treat extracted text as source truth | Typical RAG store | Simple | Normalization errors become authoritative | Reject |
| Add fields to Phase 1 `Evidence`/dossier v1 | Existing domain | Fewer types | Breaks semantics/hashes and conflates boundaries | Reject |
| Add immutable source/normalization/span/unit records and separate export | Blueprint C1 and Phase 1 boundary ADR-0005 | Exact provenance, versioning, compatible replay | More explicit mapping code | Selected proposal |
| Adopt model summaries as canonical units | None | Compact contexts | Summary laundering and citation drift | Prohibited |

## Decision

Original content-addressed bytes are authoritative. Normalized text, markers,
evidence units, and relations are derived immutable records with parser/method
provenance, warnings, exact source coordinates, and explicit dispositions.
Parser/model/external output enters as proposal or quarantine. Model-proposed
claims are structurally distinct from source-derived evidence.

Create canonical `ResearchMemoryExport` v1 separate from ResearchDossier v1.
Evidence packs are content-addressed artifacts referenced by model requests.
Any future ResearchDossier v2 linkage requires a new ADR, schema migration, and
backward-compatibility tests.

Phase 3A uses only the internal deterministic UTF-8 parser
`plain-text-v1`. Supported inputs are valid UTF-8 plain text. PDFs and every
other media type are retained as immutable quarantined source artifacts without
extraction. A metadata-only URI is an opaque user-supplied locator: only local
syntax validation is permitted, no network operation occurs, its
`content_hash` is null, its status remains unresolved, and it cannot produce a
source artifact, span, or evidence unit.

The quantum-state-discrimination paper is metadata-only until redistribution
rights and local bytes are supplied. Phase 3A infrastructure acceptance uses
project-authored synthetic primary, related, contradictory, malformed, and
prompt-injection fixtures.

## Consequences

Auditors can inspect the original local source for every accepted span, and
parser upgrades cannot overwrite earlier interpretations. Unsupported media
remain auditable without being extracted. The domain gains more entity types and
explicit cross-reference validation. Citation resolution proves ID and pack
membership only; SourceApplicabilityRecord remains necessary for load-bearing
mathematical use.

## Blueprint deviation

None. The separate export is a conservative implementation of the blueprint's
canonical source/index distinction and the existing internal/interchange
boundary.

## Validation and revisit trigger

Require stable UTF-8 byte-span round trips, immutable source bytes, deterministic
`plain-text-v1` output, unsupported-media quarantine, proposal-only foreign
import, exact citation membership, canonical export/import, and unchanged Phase
1 dossier bytes/hashes. Revisit before PDF parsing, a dossier v2, or any policy
allowing deterministic extraction to create accepted mathematics.
