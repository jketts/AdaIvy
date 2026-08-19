# Phase 1 Requirement-to-Test Matrix

| Requirement | Evidence/test |
|---|---|
| Correct Phase 0 dimensions; null unexecuted capability | `CorrectedScorecardTests.test_unexecuted_candidates_have_null_capability_and_raw_is_unchanged` |
| Preserve Phase 0 raw observations | Same test fixes raw SHA-256 to `e8166fed8063ade26d74b55f0139fc2adfd2900d2c8db4a4c3fb8c4a5b144533` |
| All thirteen required typed entities | `ImmutableEntityTests.test_required_entities_are_frozen_versioned_and_store_no_projection` |
| Immutable entities and opaque IDs | `ImmutableEntityTests.test_entities_and_opaque_ids_are_immutable` |
| Separate internal and canonical representations | `DossierInterchangeTests.test_canonical_export_import_preserves_ids_meaning_bytes_and_hash` exercises explicit mapper/decoder |
| `schema_version` on every public object | Entity inventory test plus `validate_dossier_payload` object walk |
| Deterministic canonical JSON and content hash | Canonical byte/hash round-trip test |
| Append-only repositories | `AppendOnlyRepositoryTests.test_repository_accepts_idempotent_identical_append_but_rejects_rewrite` |
| Append-only, idempotent events | `AppendOnlyRepositoryTests.test_retrying_event_command_does_not_duplicate_semantic_event` |
| Policy projections; no stored confidence/truth status | Entity inventory test and `TrustPolicy` adversarial suite |
| Orthogonal semantic/logical/warrant/novelty/significance/contribution | `TrustProjection` emits each independent dimension; manual report asserts them separately |
| Frozen confirmatory protocol | `ImmutableEntityTests.test_confirmatory_protocol_is_frozen_and_cannot_be_revised` |
| External imports are proposals | `DossierInterchangeTests.test_imported_external_proof_artifacts_remain_untrusted_proposals` |
| Dossier import/validation/export/hash preservation | Canonical round-trip and schema tests |
| Minimal create/inspect CLI | `ManualVerticalSliceTests.test_manual_cli_creates_inspects_replays_and_reports` |
| Every report statement traces to entity IDs | Manual vertical-slice report assertion |
| Agreement cannot prove | `TrustBoundaryAdversarialTests.test_model_or_external_system_agreement_cannot_prove_claim` |
| Finite experiment cannot prove universal theorem | `TrustBoundaryAdversarialTests.test_finite_experiments_cannot_prove_unrestricted_universal_theorem` |
| Unresolved representation bridge blocks original | `TrustBoundaryAdversarialTests.test_unresolved_representation_bridge_cannot_support_original_claim` |
| Formal proof of weakened/mistranslated target does not solve approved target | `TrustBoundaryAdversarialTests.test_formal_warrant_for_weakened_target_does_not_resolve_user_target` |
| Inapplicable real citation cannot close obligation | `TrustBoundaryAdversarialTests.test_real_citation_with_incompatible_hypotheses_cannot_close_obligation` |
| Restating helper lemma remains open | `TrustBoundaryAdversarialTests.test_helper_lemma_that_restates_target_remains_open` |
| Exact counterexample disproves false universal | `TrustBoundaryAdversarialTests.test_exact_counterexample_disproves_false_universal` |
| Five required versioned fixtures | `DossierInterchangeTests.test_every_phase1_scenario_fixture_is_versioned_and_known` |
| Phase 0 compatibility | All nine `test_phase0_harness` tests remain in the full suite |

The complete suite is the command documented in `README.md` and requires no
network or optional integration.
