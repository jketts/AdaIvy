# Phase 2 Requirement-to-Test Matrix

This map records the completed acceptance evidence. All identifiers below are
executed by the repository's documented full-suite command.

| Requirement | Acceptance test or demonstration |
|---|---|
| Phase 1 clean before change | Pre-change 28-test/19-check gate and hashes recorded in `PHASE_2_REPORT.md` |
| Preserve Phase 1 entities, policies, imports, and adversarial behavior | Existing `test_phase1_*` suite, unchanged |
| Transactional local persistence behind ports | `SQLiteWorkspaceTests.test_atomic_semantic_commit_rolls_back_as_a_unit` |
| SQLite foreign keys and WAL | `SQLiteWorkspaceTests.test_foreign_keys_and_wal_are_enabled` |
| Schema-versioned, checksum-protected migrations | `MigrationTests.test_fresh_upgrade_restart_and_checksum_drift` |
| Persistent append-only events | `SQLiteWorkspaceTests.test_events_are_append_only_and_idempotent` |
| Content-addressed filesystem artifacts | `ArtifactStoreTests.test_atomic_put_get_and_hash_verification` |
| Durable jobs with leases, retries, deadlines, and idempotency | `DurableJobTests.test_lease_retry_deadline_and_idempotent_enqueue` |
| Token, cost, time, and attempt budgets | `BudgetTests.test_each_budget_dimension_prevents_further_calls` |
| Pause, resume, cancellation, and crash recovery | `WorkflowControlTests.test_pause_restart_resume_and_cancel`; `DurableJobTests.test_lease_retry_deadline_and_idempotent_enqueue`; `RecoveryTests.test_orphan_artifact_retry_commits_once` |
| Audit timeline reconstructed from canonical state | `DurableReplayTests.test_timeline_is_reconstructed_from_events` |
| Provider-neutral `ModelGateway` | `ModelGatewayContractTests.test_scripted_and_live_adapter_share_contract` |
| Deterministic scripted/fake adapter | `ModelGatewayContractTests.test_scripted_gateway_is_deterministic` |
| One opt-in configured live adapter | `LiveProviderConfigurationTests.test_live_adapter_is_opt_in_and_requires_environment_secret` and live demonstration |
| Validated structured responses | `ModelBoundaryTests.test_malformed_model_output_causes_no_domain_mutation` |
| Versioned prompt templates | `PromptTemplateTests.test_template_version_and_hash_are_recorded` |
| Normalized usage and cost | `ModelGatewayContractTests.test_usage_integer_cost_provider_metadata_and_bounded_request_are_normalized` |
| Timeouts and retry classification | `ModelGatewayContractTests.test_timeout_and_retry_classification` |
| Refusal handling | `ModelBoundaryTests.test_refusal_is_explicit_non_success` |
| Capabilities and model identifier recorded | `BaselineLoopTests.test_deterministic_fake_end_to_end`; `ModelGatewayContractTests.test_usage_integer_cost_provider_metadata_and_bounded_request_are_normalized` |
| Secret redaction | `ModelGatewayContractTests.test_secrets_never_enter_artifacts_events_or_metadata` |
| No hidden chain-of-thought required or retained | `ModelBoundaryTests.test_only_structured_output_and_declared_rationale_are_retained` |
| Build dossier from accepted state | `BaselineLoopTests.test_proposer_context_comes_from_accepted_dossier` |
| Bounded proposer context and schema-valid candidate/failure | `BaselineLoopTests.test_proposer_context_comes_from_accepted_dossier`; `ModelBoundaryTests.test_malformed_model_output_causes_no_domain_mutation` |
| All proposer output is proposal-only | `ModelBoundaryTests.test_proposer_output_cannot_award_a_warrant` |
| Deterministic isolated verifier context includes only approved target/alignment, accepted premises, raw evidence/spans, candidate math, and policy | `VerifierIsolationTests.test_verifier_context_excludes_proposer_narrative_by_default`; `VerifierIsolationTests.test_manifest_exactly_represents_serialized_context` |
| Exclude proposer narrative, ratings, persuasive summary, unrelated history | `VerifierIsolationTests.test_verifier_context_excludes_proposer_narrative_by_default` |
| Persist exact `VerifierContextManifest` IDs, exclusions, policy, and context hash | `VerifierIsolationTests.test_manifest_exactly_represents_serialized_context` |
| Verifier findings cannot exceed policy | `ModelBoundaryTests.test_invalid_verifier_output_does_not_alter_claim_status`; `BaselineLoopTests.test_verifier_yields_finding_not_self_awarded_warrant` |
| Manual review or honest unresolved terminal result | `BaselineLoopTests.test_run_finishes_awaiting_review_or_unresolved` |
| Workflow owns transitions; models cannot access repositories | `BaselineLoopTests.test_gateway_receives_value_request_only` |
| Seven explicit verifier-independence dimensions | `VerifierIsolationTests.test_all_independence_dimensions_are_serialized` |
| Same-model call is isolated but not provider/full independent | `VerifierIsolationTests.test_same_model_is_context_isolated_not_fully_independent` |
| Filesystem/process adapter exports canonical dossier and manifest to isolated directory | `ExternalBackendTests.test_process_evidence_is_complete` |
| Command or fixture may return a schema-valid package | `ExternalBackendTests.test_successful_package_imports_proposals_only` |
| Capture stdout, stderr, status, environment identity, and output hashes | `ExternalBackendTests.test_process_evidence_is_complete` |
| Validate before import; mathematics remains proposals | `ExternalBackendTests.test_malicious_and_malformed_packages_are_rejected`; `ExternalBackendTests.test_successful_package_imports_proposals_only` |
| Reject traversal, unexpected files, invalid hashes, and schema mismatch | `ExternalBackendTests.test_malicious_and_malformed_packages_are_rejected` |
| Timeout and cancellation | `ExternalBackendTests.test_timeout_and_cancellation_cannot_commit` |
| No named unavailable research/formal system integration | `ScopeGuardTests.test_no_forbidden_phase3_imports_or_integrations` |
| CLI starts baseline run and inspects jobs/budgets | `Phase2CliTests.test_start_inspect_pause_resume_export_timeline_and_report_commands` |
| CLI pauses/resumes and survives restart | Same CLI acceptance test plus `WorkflowControlTests.test_pause_restart_resume_and_cancel` |
| CLI views proposer/verifier artifacts, manifest, and proposals | `Phase2CliTests.test_start_inspect_pause_resume_export_timeline_and_report_commands` |
| CLI exports dossier, timeline, and traceable report | `Phase2CliTests.test_start_inspect_pause_resume_export_timeline_and_report_commands` |
| Malformed model output causes no domain mutation | `ModelBoundaryTests.test_malformed_model_output_causes_no_domain_mutation` |
| Refusal is explicit non-success | `ModelBoundaryTests.test_refusal_is_explicit_non_success` |
| Proposer cannot award a warrant | `ModelBoundaryTests.test_proposer_output_cannot_award_a_warrant` |
| Invalid verifier output cannot change claim status | `ModelBoundaryTests.test_invalid_verifier_output_does_not_alter_claim_status` |
| Retries do not duplicate jobs, events, evidence, or warrants | `RecoveryTests.test_retry_is_semantically_idempotent` |
| Crash after artifact creation but before state commit produces one semantic result | `RecoveryTests.test_orphan_artifact_retry_commits_once` |
| Exhausted budgets prevent calls | `BudgetTests.test_each_budget_dimension_prevents_further_calls`; `WorkflowBudgetAndCancellationTests.test_exhausted_budget_prevents_gateway_call` |
| Cancelled/timed-out job cannot later commit success | `WorkflowControlTests.test_late_success_is_rejected`; `WorkflowBudgetAndCancellationTests.test_cancelled_job_cannot_commit_after_model_returns` |
| External results remain proposals | `ExternalBackendTests.test_successful_package_imports_proposals_only` |
| Malicious package cannot escape run directory | `ExternalBackendTests.test_malicious_and_malformed_packages_are_rejected` |
| Restart preserves IDs, hashes, events, obligations, projections | `DurableReplayTests.test_database_restart_preserves_canonical_meaning` |
| Traceable report is reproducible from durable state | `DurableReplayTests.test_report_bytes_and_hash_are_reproducible` |
| Fake-provider end-to-end fixture | `BaselineLoopTests.test_deterministic_fake_end_to_end` and demonstration record |
| One live proposer/verifier run when configured | Passed v3 record in `reports/phase-2/live-provider-status.json`; `Phase2DemonstrationEvidenceTests.test_live_provider_status_is_honest` |
| Live calls have distinct response IDs and API-reported usage | `Phase2DemonstrationEvidenceTests.test_live_provider_status_is_honest` |
| Live estimated costs reference the pinned pricing snapshot | `Phase2DemonstrationEvidenceTests.test_live_provider_status_is_honest` |
| Live manifest, event replay, restart report, proposal boundary, and independence labels reproduce | `Phase2DemonstrationEvidenceTests.test_live_provider_status_is_honest` |
| Live credential-leak scan records zero matches | Passed v3 status plus independent completion scan |
| Pause/restart/resume demonstration | `reports/phase-2/demonstration.json` backed by CLI test |
| Failed and successful external imports | `reports/phase-2/demonstration.json` backed by external tests |
| Clean report regeneration from persisted state | Demonstration compares two report byte hashes |
| Stop before Phase 3 | `ScopeGuardTests.test_no_forbidden_phase3_imports_or_integrations` plus `DEFERRED_WORK.md` |
| Canonical schemas are never sent directly to OpenAI | `ModelGatewayContractTests.test_usage_integer_cost_provider_metadata_and_bounded_request_are_normalized`; `OpenAISchemaProjectionTests.test_projection_is_deterministic_and_canonical_schemas_are_unchanged` |
| Provider projection is deterministic and manifest-complete | `OpenAISchemaProjectionTests.test_projection_is_deterministic_and_canonical_schemas_are_unchanged`; generated manifests under `reports/phase-2/provider-compatibility/` |
| `uniqueItems` is omitted only at the provider boundary and enforced locally | `OpenAISchemaProjectionTests.test_unique_items_is_projected_out_but_enforced_canonically`; `ProviderPreflightWorkflowTests.test_duplicate_provider_output_imports_nothing_and_skips_verifier` |
| Every provider object is closed and all properties required | `OpenAISchemaProjectionTests.test_nested_objects_are_closed_and_all_properties_required` |
| Canonical optional fields project to required nullable fields | `OpenAISchemaProjectionTests.test_optional_property_becomes_required_nullable` |
| Root `anyOf` and unknown keywords fail with exact paths | `OpenAISchemaProjectionTests.test_root_anyof_and_unsupported_keyword_report_exact_paths` |
| Provider depth, property, enum, and string budgets are enforced | `OpenAISchemaProjectionTests.test_depth_and_property_limits_are_enforced`; `OpenAISchemaProjectionTests.test_enum_and_schema_string_budgets_are_enforced` |
| Provider linter runs before budget reservation and network | `ProviderPreflightWorkflowTests.test_incompatible_schema_fails_before_budget_and_network` |
| HTTP 400 diagnostics retain safe detail and full-body identity | `ProviderDiagnosticTests.test_sanitized_http_400_retains_request_id_full_hash_and_bounded_body` |
| Failed request IDs persist and secrets/headers do not | `ProviderDiagnosticTests.test_sanitized_http_400_retains_request_id_full_hash_and_bounded_body`; `ProviderDiagnosticTests.test_failed_call_debits_no_usage_creates_no_proposal_and_never_calls_verifier` |
| HTTP 400 is fatal, has no automatic retry, no usage debit, and no verifier | `ProviderDiagnosticTests.test_sanitized_http_400_retains_request_id_full_hash_and_bounded_body`; `ProviderDiagnosticTests.test_failed_call_debits_no_usage_creates_no_proposal_and_never_calls_verifier` |
| Earlier failed live history remains immutable | `ProviderDiagnosticTests.test_v2_workspace_status_request_id_and_diagnostics_remain_unchanged` |
| All six live const/enum terminals receive provider-only explicit types | `OpenAISchemaProjectionTests.test_all_six_live_schema_terminals_receive_provider_only_string_types` |
| String, boolean, integer, finite-number, and mixed numeric inference is deterministic | `OpenAISchemaProjectionTests.test_scalar_terminal_type_inference_and_numeric_merge_policy` |
| Boolean values never infer integer | `OpenAISchemaProjectionTests.test_scalar_terminal_type_inference_and_numeric_merge_policy` |
| Empty, heterogeneous, null-only, object, and array inference fails closed | `OpenAISchemaProjectionTests.test_ambiguous_empty_null_object_and_array_terminals_fail_closed` |
| Explicit terminal types are retained and conflicts rejected | `OpenAISchemaProjectionTests.test_explicit_terminal_type_is_retained_or_rejected_on_conflict` |
| Properties, items, `$defs`, `anyOf`, and resolved `$ref` terminals are checked | `OpenAISchemaProjectionTests.test_nested_properties_items_defs_anyof_and_resolved_refs_are_typed` |
| Linter rejects missing types, unsupported unions, and non-finite values | `OpenAISchemaProjectionTests.test_linter_rejects_untyped_invalid_unions_and_non_finite_values` |
