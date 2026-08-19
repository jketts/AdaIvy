# Proposed Phase 3 Requirement-to-Test Matrix

Status: acceptance design only  
Date: 2026-08-19

Test names are proposed identifiers. None is implemented by this design task.

| ID | Requirement | Proposed acceptance test/evidence |
|---|---|---|
| P3-001 | Preserve Phase 1 trust semantics and Phase 2 durability | Run all existing 101 tests unchanged before and after Phase 3A; prohibit edits that weaken them |
| P3-002 | Manual local-file import only | `SourceAcquisitionTests.test_regular_local_file_import_is_content_addressed` |
| P3-003 | Manual URL metadata import without autonomous fetch | `SourceAcquisitionTests.test_url_metadata_import_performs_no_network_access_and_stays_metadata_only` |
| P3-004 | Identical source has identical identity/hash | `SourceIdentityTests.test_identical_bytes_are_idempotent_across_paths_and_restarts` |
| P3-005 | Changed source creates a distinct version | `SourceIdentityTests.test_changed_bytes_create_distinct_artifact_with_explicit_version_edge` |
| P3-006 | Source metadata, timestamps, media type, parser, and rights retained | `SourceAcquisitionTests.test_complete_metadata_and_rights_round_trip` |
| P3-007 | Untrusted external content is quarantined | `SourceAcquisitionTests.test_unreviewed_or_media_mismatched_content_is_quarantined` |
| P3-008 | Symlink/path/device and oversized input rejected | `SourceAcquisitionAdversarialTests.test_unsafe_local_inputs_never_reach_cas_or_parser` |
| P3-009 | Original source remains authoritative | `NormalizationTests.test_normalized_document_is_derived_and_cannot_replace_source_bytes` |
| P3-010 | Deterministic normalization/export | `NormalizationTests.test_same_source_parser_and_config_produce_identical_bytes_and_hash` |
| P3-011 | Page/section and typed marker retention | `NormalizationTests.test_page_section_equation_theorem_definition_proof_table_and_reference_markers` |
| P3-012 | Stable source-span round trip | `SpanCoordinateTests.test_every_gold_span_maps_to_exact_original_locator_and_back` |
| P3-013 | Extraction warnings/confidence do not confer trust | `NormalizationTrustTests.test_confidence_is_diagnostic_and_unsupported_output_stays_quarantined` |
| P3-014 | All required evidence-unit types are immutable/versioned | `EvidenceUnitTests.test_required_unit_types_are_frozen_versioned_and_origin_checked` |
| P3-015 | Every source-derived unit has exact provenance | `EvidenceUnitTests.test_source_units_require_artifact_document_and_valid_spans` |
| P3-016 | Model claim never masquerades as source evidence | `EvidenceUnitTrustTests.test_model_proposed_claim_requires_model_origin_and_proposal_disposition` |
| P3-017 | Typed graph relations preserve origin/trust state | `EvidenceRelationTests.test_source_parser_model_and_human_relations_are_not_interchangeable` |
| P3-018 | Conflicting evidence is preserved | `EvidenceRelationTests.test_contradictory_units_and_edges_coexist_and_are_retrievable` |
| P3-019 | Relation acceptance does not award a warrant | `EvidenceRelationTrustTests.test_accepted_source_assertion_does_not_change_claim_projection` |
| P3-020 | SQLite FTS5/BM25 is a derived deterministic baseline | `RetrievalTests.test_rebuild_from_canonical_memory_is_byte_and_order_stable_under_pinned_engine` |
| P3-021 | Exact retrieval evidence returned | `RetrievalTests.test_hits_include_unit_source_span_score_method_version_query_hash` |
| P3-022 | Deterministic tie-breaking | `RetrievalTests.test_equal_scores_order_by_source_span_and_unit_id` |
| P3-023 | Complete retrieval manifest | `RetrievalTests.test_manifest_reconstructs_exact_query_index_and_result_order` |
| P3-024 | Optional embeddings cannot own canonical state | `EmbeddingPortTests.test_dropping_embedding_projection_preserves_export_and_fts_acceptance` |
| P3-025 | Deterministic pack construction and hash | `EvidencePackTests.test_same_query_corpus_policy_and_budget_produce_identical_pack_hash` |
| P3-026 | Byte/token budgets enforced | `EvidencePackTests.test_budget_exclusions_are_complete_and_deterministic` |
| P3-027 | Deterministic deduplication and source diversity | `EvidencePackTests.test_duplicates_removed_and_per_source_cap_applied_before_fill` |
| P3-028 | Provenance inline; no summary replacement | `EvidencePackTests.test_every_excerpt_carries_ids_and_exact_span_and_summary_is_separate_proposal` |
| P3-029 | Prompt-like text treated as source content | `PromptInjectionTests.test_malicious_source_text_is_quoted_annotated_and_never_executed_as_policy` |
| P3-030 | Malformed document rejected or quarantined | `ParserAdversarialTests.test_malformed_gold_fixture_retains_failure_without_evidence_import` |
| P3-031 | Unsupported parser output cannot become trusted | `ParserAdversarialTests.test_unmapped_or_unstable_output_cannot_enter_accepted_memory` |
| P3-032 | Exact citation resolution | `CitationValidationTests.test_cited_id_resolves_to_exact_pack_unit_and_span` |
| P3-033 | Fabricated citation rejected | `CitationValidationTests.test_unknown_unit_id_rejects_proposal_without_domain_mutation` |
| P3-034 | Out-of-pack citation rejected | `CitationValidationTests.test_globally_real_but_unsupplied_unit_id_is_rejected` |
| P3-035 | Citation does not imply applicability | Existing real-but-inapplicable-source adversarial test plus `CitationValidationTests.test_pack_membership_awards_no_warrant` |
| P3-036 | Proposer/verifier agreement cannot promote trust | Existing agreement adversarial test plus `ModelMemoryBoundaryTests.test_same_model_agreement_remains_two_proposals` |
| P3-037 | Verifier context remains isolated | `ModelMemoryBoundaryTests.test_verifier_pack_excludes_proposer_commentary_and_records_manifest` |
| P3-038 | Model summaries are clearly proposals | `ModelMemoryBoundaryTests.test_generated_summary_has_no_source_origin_or_accepted_disposition` |
| P3-039 | Crash between artifact and semantic commit recovers once | `ResearchMemoryRecoveryTests.test_orphan_normalization_retry_commits_one_document_units_and_events` |
| P3-040 | Restart/event replay preserves canonical memory | `ResearchMemoryRecoveryTests.test_restart_preserves_ids_hashes_spans_relations_index_manifest_and_pack` |
| P3-041 | Retry does not duplicate sources, units, relations, packs, jobs, or events | `ResearchMemoryRecoveryTests.test_idempotent_commands_have_one_semantic_result` |
| P3-042 | Parser/model budgets stop further work | `ResearchMemoryBudgetTests.test_exhausted_time_size_attempt_or_optional_model_budget_prevents_commit` |
| P3-043 | Cancelled/timed-out work cannot commit later | `ResearchMemoryBudgetTests.test_late_parser_or_model_success_is_rejected` |
| P3-044 | Deterministic canonical import/export | `ResearchMemoryInterchangeTests.test_export_import_preserves_ids_meaning_bytes_and_content_hash` |
| P3-045 | Foreign memory imports as proposals only | `ResearchMemoryInterchangeTests.test_external_export_cannot_write_accepted_memory` |
| P3-046 | Gold corpus has four required classes | `GoldCorpusTests.test_manifest_contains_primary_related_contradictory_and_injection_sources` |
| P3-047 | Quantum paper is generic fixture only | `ScopeGuardTests.test_core_has_no_quantum_specific_import_type_or_solver` |
| P3-048 | No crawler/vector DB/required embeddings/tools/UI/API/multi-agent scope | `ScopeGuardTests.test_phase3a_forbidden_dependencies_and_features_absent` |
| P3-049 | Clean report/provenance regeneration | `ResearchMemoryReportTests.test_report_is_reproducible_from_durable_canonical_state` |
| P3-050 | Credential scan remains clean | `ResearchMemorySecurityTests.test_no_secret_in_sources_indexes_packs_events_logs_database_or_reports` |
| P3-051 | Rights policy controls export/context | `RightsPolicyTests.test_restricted_source_span_is_excluded_with_manifest_reason` |
| P3-052 | No live/model API needed for acceptance | Full acceptance suite runs with network disabled and scripted model adapter only |

## Measurable acceptance thresholds

- 100% of accepted evidence units resolve to an existing source artifact,
  normalized document, and valid nonempty span, except the structurally distinct
  `model_proposed_claim` type.
- 100% of citations in imported model proposals resolve to IDs in the exact
  supplied evidence-pack manifest.
- Repeated import, normalization, FTS rebuild, retrieval, pack construction,
  export/import, restart replay, and report rendering produce identical bytes or
  explicitly recorded engine-version blockers.
- Zero automatic warrants, obligation discharges, or accepted claims result
  from parser, retrieval, relation, summary, proposer, or verifier output.
- Zero credential matches and zero unauthorized network requests occur.
- All Phase 0–2 tests and checks pass unchanged.

Thresholds for semantic retrieval quality, such as necessary-passage recall,
must be frozen with a human-authored relevance judgment set before Phase 3A
implementation acceptance. They are an unresolved approval item; no favorable
threshold is invented after viewing results.
