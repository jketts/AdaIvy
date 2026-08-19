# Phase 0 Corrected Scorecard

Raw observation SHA-256: `e8166fed8063ade26d74b55f0139fc2adfd2900d2c8db4a4c3fb8c4a5b144533`  
Observed: 2026-08-19T04:15:59.943765+00:00  
Blocked and deferred candidates were not evaluated. Their capability and baseline comparison are `null`.

| Component | Evaluation | Runnability | Capability | Effort | Evidence | License | vs file | Recommendation | Blockers |
|---|---|---|---:|---|---|---|---:|---|---|
| File baseline | evaluated_complete | runnable | 100.0 | low | complete_for_selected_spike | unresolved | +0.0 | build | repository_license_unresolved |
| OMDoc concept projection | evaluated_partial | runnable_with_limitations | 69.4 | low | partial_for_selected_spike | unresolved | -30.6 | interoperate | format_license_unresolved, xml_projection_is_lossy_without_sidecar |
| Albilich | not_evaluated_blocked | unavailable_on_observed_host | null | null | prerequisite_evidence_only | identified | null | interoperate | albilich_repository_unavailable |
| MathGraph | not_evaluated_deferred | not_attempted | null | null | inventory_only | absent | null | defer | license_absent |
| MMT | not_evaluated_blocked | unavailable_on_observed_host | null | null | prerequisite_evidence_only | restrictive | null | interoperate | modification_not_permitted |
| Why3 | not_evaluated_blocked | unavailable_on_observed_host | null | null | prerequisite_evidence_only | identified | null | wrap | why3_executable_missing |
| Lean 4 | not_evaluated_blocked | unavailable_on_observed_host | null | null | prerequisite_evidence_only | identified | null | wrap | lean_executable_missing |
| LeanDojo | not_evaluated_deferred | not_attempted | null | null | inventory_only | identified | null | defer | host_python_unsupported, deprecated_generation |
| LeanSearch v2 | not_evaluated_deferred | not_attempted | null | null | inventory_only | identified | null | defer | gpu_and_model_prerequisites_unavailable |
| PaperQA2 | not_evaluated_blocked | unavailable_on_observed_host | null | null | prerequisite_evidence_only | identified | null | wrap | paperqa_package_missing |
| Eigenius | not_evaluated_blocked | unavailable_on_observed_host | null | null | prerequisite_evidence_only | identified | null | interoperate | local_toolchain_unavailable |
| ASTRA | not_evaluated_deferred | not_attempted | null | null | inventory_only | absent | null | defer | license_absent, host_python_unsupported |
| RMA | not_evaluated_deferred | not_attempted | null | null | inventory_only | not_applicable_to_runnable_code | null | defer | implementation_unavailable |
| Aletheia | not_evaluated_deferred | not_attempted | null | null | inventory_only | not_applicable_to_runnable_code | null | defer | implementation_unavailable |
| AlphaProof Nexus | not_evaluated_deferred | not_attempted | null | null | inventory_only | not_applicable_to_runnable_code | null | defer | implementation_unavailable |
| ProofAtlas | not_evaluated_deferred | not_attempted | null | null | inventory_only | not_applicable_to_runnable_code | null | defer | implementation_unavailable |
| FunSearch | not_evaluated_deferred | not_attempted | null | null | inventory_only | identified | null | defer | omits_model_and_sandbox |
| AlphaEvolve | not_evaluated_deferred | not_attempted | null | null | inventory_only | not_applicable_to_runnable_code | null | defer | implementation_unavailable |
| The Agentic Researcher | not_evaluated_deferred | not_attempted | null | null | inventory_only | not_applicable_to_runnable_code | null | reference | not_a_component |

## Interpretation

The file baseline is the only complete executed interchange result. The OMDoc projection is an executed partial result whose lossless replay depends on the canonical JSON sidecar. All other entries retain blockers or deferral evidence without a capability ranking.

The historical aggregate `weighted_score` fields remain only in the immutable raw result and must not be used for adoption decisions.
