# Proposed Phase 3 Entities and Interchange Schemas

Status: design proposal only  
Date: 2026-08-19

## Compatibility rules

- These are new immutable typed records; they do not mutate Phase 1 entities.
- Every public object carries `schema_version`.
- Internal frozen types remain separate from canonical JSON mappers.
- IDs are opaque. Source identity is deterministically allocated from a content
  hash by repository policy but consumers must not parse the ID.
- Canonical JSON uses sorted keys, UTF-8, no insignificant whitespace, finite
  JSON numbers only, and content hashes calculated with the object's own
  `content_hash` field set to `null` where applicable.
- Existing ResearchDossier v1 is not edited in place. Phase 3A exports a separate
  `ResearchMemoryExport` and supplies content-addressed evidence packs to Phase 2
  model requests. A future dossier v2 requires a separate ADR and migration.
- Parser, model, or external relations enter as proposals/quarantined records.
  Only explicit application commands may append accepted records under policy.

## Core acquisition records

```yaml
SourceReference:
  schema_version: "1.0.0"
  id: SourceReferenceId
  canonical_uri: string
  supplied_uri: string
  title: string
  authors: [string]
  publication_metadata: object
  metadata_assertion_source: operator | source_embedded | registry | publisher
  metadata_status: proposed | checked | disputed
  retrieved_or_recorded_at: datetime
  license_metadata:
    license_expression: string | null
    copyright_notice: string | null
    usage_rights: [string]
    redistribution_status: allowed | prohibited | unresolved
    evidence_uri: string | null
    reviewed_by: ActorId | null
  acquisition_status: metadata_only | bytes_available | rejected
  created_at: datetime
  created_by: ActorId
```

`metadata_only` records are quarantined references and cannot produce spans or
evidence units.

```yaml
SourceArtifact:
  schema_version: "1.0.0"
  id: SourceArtifactId
  source_reference_id: SourceReferenceId
  artifact_hash: sha256
  byte_length: integer
  declared_media_type: string
  detected_media_type: string
  acquisition_method: local_file | operator_supplied_bytes
  acquired_at: datetime
  acquisition_adapter: string
  acquisition_adapter_version: string
  quarantine_state: quarantined | eligible_for_parsing | rejected
  quarantine_reasons: [string]
  content_hash: sha256
  created_at: datetime
  created_by: ActorId

SourceVersionRelation:
  schema_version: "1.0.0"
  id: SourceVersionRelationId
  source_artifact_id: SourceArtifactId
  target_artifact_id: SourceArtifactId
  relation: supersedes | is_version_of | corrects
  assertion_origin: source_metadata | operator | parser_proposal
  disposition: proposal | accepted | rejected
  evidence_span_id: SourceSpanId | null
  created_at: datetime
  created_by: ActorId
```

Identical bytes resolve to the same source artifact and hash. Changed bytes
always resolve to a distinct source artifact; version relations never overwrite
the earlier artifact.

## Parser and normalization records

```yaml
ParserRunRecord:
  schema_version: "1.0.0"
  id: ParserRunId
  source_artifact_id: SourceArtifactId
  parser_name: string
  parser_version: string
  parser_configuration_hash: sha256
  dependency_environment_hash: sha256
  input_hash: sha256
  status: succeeded | failed | timed_out | cancelled | quarantined
  warning_codes: [string]
  declared_confidence: finite_number | null
  stdout_artifact_hash: sha256
  stderr_artifact_hash: sha256
  output_artifact_hash: sha256 | null
  idempotency_key: string
  created_at: datetime

NormalizedDocument:
  schema_version: "1.0.0"
  id: NormalizedDocumentId
  source_artifact_id: SourceArtifactId
  parser_run_id: ParserRunId
  normalized_text_artifact_hash: sha256
  structure_map_artifact_hash: sha256
  location_map_artifact_hash: sha256
  unicode_normalization: NFC
  newline_policy: LF
  coordinate_unit: utf8_byte
  normalization_version: string
  warnings: [ExtractionWarning]
  disposition: proposal | accepted | rejected | quarantined
  content_hash: sha256
  created_at: datetime
  created_by: ActorId
```

```yaml
SourceSpan:
  schema_version: "1.0.0"
  id: SourceSpanId
  source_artifact_id: SourceArtifactId
  normalized_document_id: NormalizedDocumentId
  normalized_start: integer       # zero-based inclusive UTF-8 byte offset
  normalized_end: integer         # zero-based exclusive UTF-8 byte offset
  page_number: integer | null     # one-based human page locator
  section_path: [string]
  original_locator:
    locator_kind: text_bytes | page_region | parser_tokens | unknown
    page_number: integer | null
    region_microunits: [integer, integer, integer, integer] | null
    original_start: integer | null
    original_end: integer | null
    parser_token_start: integer | null
    parser_token_end: integer | null
  exact_text_hash: sha256
  original_quote_hash: sha256 | null
  content_hash: sha256
```

```yaml
DocumentMarker:
  schema_version: "1.0.0"
  id: DocumentMarkerId
  normalized_document_id: NormalizedDocumentId
  span_id: SourceSpanId
  marker_type: page | section | equation | theorem | proposition | definition |
               proof | table | figure | reference | footnote
  label: string | null
  ordinal: integer | null
  extraction_method: parser | deterministic_rule | operator
  disposition: proposal | accepted | rejected | quarantined
  warning_codes: [string]
  content_hash: sha256
```

The location-map artifact contains ordered mapping segments. Each segment maps
an original locator to a normalized half-open byte interval and retains hashes
of both extracts. Gaps and many-to-one mappings are explicit warning-bearing
segments, never silently interpolated.

## Evidence units

```yaml
EvidenceUnit:
  schema_version: "1.0.0"
  id: EvidenceUnitId
  unit_type: source_passage | definition | theorem_or_proposition | assumption |
             equation | proof_step | empirical_or_numerical_result |
             bibliographic_reference | model_proposed_claim
  origin: source_explicit | parser_derived | operator_curated | model
  source_artifact_id: SourceArtifactId | null
  normalized_document_id: NormalizedDocumentId | null
  source_span_ids: [SourceSpanId]
  model_call_id: ModelCallId | null
  proposal_artifact_hash: sha256 | null
  payload: EvidenceUnitPayload
  extraction_method: string
  extraction_version: string
  warning_codes: [string]
  disposition: proposal | accepted | rejected | quarantined
  content_hash: sha256
  created_at: datetime
  created_by: ActorId
```

Typed payload contracts:

| Unit type | Required payload fields |
|---|---|
| `source_passage` | `verbatim_text`, `language` |
| `definition` | `term`, `definiens`, `scope`, `verbatim_text` |
| `theorem_or_proposition` | `label`, `statement`, `hypotheses`, `scope`, `verbatim_text` |
| `assumption` | `statement`, `scope`, `verbatim_text` |
| `equation` | `presentation`, `normalized_expression`, `label`, `normalization_status` |
| `proof_step` | `statement`, `local_premise_unit_ids`, `step_label`, `verbatim_text` |
| `empirical_or_numerical_result` | `statement`, `method_text`, `parameters_text`, `reported_uncertainty`, `verbatim_text` |
| `bibliographic_reference` | `citation_text`, `identifier_candidates`, `resolved_source_reference_id` |
| `model_proposed_claim` | `statement`, `cited_evidence_unit_ids`, `declared_rationale`, `target_claim_id` |

For every source-derived type, source/document/span fields are required and the
model fields must be null. For `model_proposed_claim`, source/document/span
fields must be empty, model-call/proposal fields are required, origin must be
`model`, and disposition must be `proposal`.

## Typed graph relations

```yaml
EvidenceRelation:
  schema_version: "1.0.0"
  id: EvidenceRelationId
  source_unit_id: EvidenceUnitId
  target_unit_id: EvidenceUnitId
  relation_type: supports | contradicts | defines | assumes | derives_from |
                 cites | equivalent_to | specializes | supersedes
  assertion_origin: source_asserted | parser_proposed | model_proposed |
                    operator_asserted
  assertion_span_ids: [SourceSpanId]
  extraction_or_actor_id: string
  disposition: proposal | accepted | rejected | quarantined
  review_record_ids: [VerificationRecordId]
  content_hash: sha256
  created_at: datetime
  created_by: ActorId
```

Accepted relation means the relation was faithfully captured under its origin;
it does not create an `EpistemicWarrant` or establish local applicability.

## Retrieval and pack records

```yaml
RetrievalQueryRecord:
  schema_version: "1.0.0"
  id: RetrievalQueryId
  canonical_query: string
  query_hash: sha256
  corpus_manifest_hash: sha256
  retrieval_method: sqlite_fts5_bm25
  retrieval_version: string
  engine_version: string
  tokenizer_configuration: string
  field_weights: [finite_number]
  filters: object
  requested_limit: integer
  created_at: datetime
  created_by: ActorId

RetrievalHit:
  schema_version: "1.0.0"
  id: RetrievalHitId
  query_id: RetrievalQueryId
  rank: integer
  evidence_unit_id: EvidenceUnitId
  source_artifact_id: SourceArtifactId
  source_span_ids: [SourceSpanId]
  raw_score: finite_number
  canonical_score: string
  tie_break_key: string
```

```yaml
EvidencePackManifest:
  schema_version: "1.0.0"
  id: EvidencePackId
  query_id: RetrievalQueryId
  retrieval_result_hash: sha256
  policy_version: string
  byte_budget: integer
  token_budget: integer | null
  token_counter_id: string | null
  included_evidence_unit_ids: [EvidenceUnitId]
  included_source_artifact_ids: [SourceArtifactId]
  included_source_span_ids: [SourceSpanId]
  excluded_items:
    - evidence_unit_id: EvidenceUnitId
      reason: duplicate | source_cap | quarantine | rights | byte_budget |
              token_budget | lower_rank
  source_diversity_policy: object
  injection_annotations: [SourceSpanId]
  serialized_pack_artifact_hash: sha256
  content_hash: sha256
  created_at: datetime
  created_by: ActorId
```

Pack membership is authoritative for model citation validation. Retrieval hits
that were excluded from the pack cannot be cited as supplied context.

## Canonical interchange proposal

```yaml
ResearchMemoryExport:
  schema_version: "1.0.0"
  id: ResearchMemoryExportId
  source_references: [SourceReference]
  source_artifacts: [SourceArtifact]
  source_version_relations: [SourceVersionRelation]
  parser_runs: [ParserRunRecord]
  normalized_documents: [NormalizedDocument]
  source_spans: [SourceSpan]
  markers: [DocumentMarker]
  evidence_units: [EvidenceUnit]
  evidence_relations: [EvidenceRelation]
  retrieval_queries: [RetrievalQueryRecord]
  retrieval_hits: [RetrievalHit]
  evidence_packs: [EvidencePackManifest]
  audit_event_ids: [AuditEventId]
  content_hash: sha256
  created_at: datetime
  created_by: ActorId
```

Import validates schema, hashes, cross-references, coordinates, origin/type
rules, rights/quarantine states, and pack membership. External exports enter an
import-proposal repository. Hash-preserving local replay is a separate path and
does not grant trust to foreign content.

## Repository/port proposal

Add inward protocols only after ADR approval:

```text
SourceReferenceRepository
SourceArtifactRepository
NormalizedDocumentRepository
EvidenceUnitRepository
EvidenceRelationRepository
ResearchMemoryExportRepository
DocumentParser
RetrievalIndex
EvidencePackBuilder
EmbeddingProvider (optional)
```

All append operations are idempotent by canonical content hash and command
idempotency key. SQLite/CAS adapters implement these ports; domain types do not
import them.
