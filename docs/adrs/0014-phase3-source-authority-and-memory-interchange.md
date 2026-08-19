# ADR-0014: Original source bytes remain authoritative across research memory

- **Status:** proposed
- **Date:** 2026-08-19
- **Blueprint requirement:** C1, C3, C12, §§7.1–7.4 and 11.5
- **Decision owners:** researcher and repository maintainer

## Context

PDF/text parsers can reorder text, lose formulas, merge columns, or infer
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

## Proposed decision

Original content-addressed bytes are authoritative. Normalized text, markers,
evidence units, and relations are derived immutable records with parser/method
provenance, warnings, exact source coordinates, and explicit dispositions.
Parser/model/external output enters as proposal or quarantine. Model-proposed
claims are structurally distinct from source-derived evidence.

Create canonical `ResearchMemoryExport` v1 separate from ResearchDossier v1.
Evidence packs are content-addressed artifacts referenced by model requests.
Any future ResearchDossier v2 linkage requires a new ADR, schema migration, and
backward-compatibility tests.

## Consequences

Auditors can inspect the original source for every accepted span, and parser
upgrades cannot overwrite earlier interpretations. The domain gains more entity
types and explicit cross-reference validation. Citation resolution proves ID and
pack membership only; SourceApplicabilityRecord remains necessary for
load-bearing mathematical use.

## Blueprint deviation

None. The separate export is a conservative implementation of the blueprint's
canonical source/index distinction and the existing internal/interchange
boundary.

## Validation and revisit trigger

Require stable span round trips, immutable source bytes, versioned parser output,
proposal-only foreign import, exact citation membership, canonical export/import,
and unchanged Phase 1 dossier bytes/hashes. Revisit before a dossier v2 or any
policy allowing deterministic extraction to create accepted records.
