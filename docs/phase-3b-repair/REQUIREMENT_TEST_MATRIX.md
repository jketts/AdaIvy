# Requirement / Test Matrix — Phase 3B Bounded Proof Repair

ADR-0040. All 38 cases live in `tests/test_phase3b_proof_repair.py` and run
offline; the sealed runtime is never invoked.

| # | Requirement | Test |
|---|---|---|
| R1 | Only Lean's elaboration failure is repairable, by set equality | `test_only_elaboration_failure_is_declared_repairable` |
| R2 | An elaboration failure is repaired and can reach kernel-checked | `test_an_elaboration_failure_is_repaired_and_can_succeed` |
| R3 | An unparsable origin is never repaired | `test_a_policy_rejection_is_never_repaired` |
| R4 | A validator-refused model fragment stops the loop | `test_a_model_fragment_the_validator_refuses_stops_the_loop` |
| R5 | Every non-elaboration outcome terminates without consulting a proposer | `test_every_non_elaboration_outcome_terminates_without_a_proposal` |
| R6 | A meaning-test failure is never repaired | `test_a_meaning_test_failure_is_never_repaired` |
| R7 | The proposer surface is one proof fragment and nothing else | `test_the_proposer_surface_exposes_only_a_proof_fragment` |
| R8 | A repaired request differs in exactly `{request_id, source_kind, proof_fragment}` | `test_a_repaired_request_differs_only_in_proof_identity_and_source` |
| R9 | Identity hashes are frozen from the origin and survive repair | `test_identity_hashes_are_frozen_from_the_origin_and_survive_repair` |
| R10 | Altering the theorem raises rather than records | `test_a_candidate_that_alters_the_theorem_raises_rather_than_records` |
| R11 | An assumption cannot be smuggled in through a repair | `test_an_assumption_cannot_be_smuggled_in_through_a_repair` |
| R12 | The attempt cap is hard and counts the origin | `test_the_attempt_cap_is_hard_and_counts_the_origin` |
| R13 | A one-attempt limit permits no repair at all | `test_a_single_attempt_limit_permits_no_repair_at_all` |
| R14 | A declining proposer ends the session | `test_a_declining_proposer_ends_the_session` |
| R15 | A duplicate candidate ends the session without resubmission | `test_a_duplicate_candidate_ends_the_session_without_resubmission` |
| R16 | Repeating the origin fragment counts as a duplicate | `test_repeating_the_origin_fragment_is_also_a_duplicate` |
| R17 | Absurd or unbounded limits are refused at construction | `test_limits_reject_an_unbounded_or_absurd_configuration` |
| R18 | Proposer calls are counted in the record | `test_proposer_calls_are_counted_in_the_record` |
| R19 | A repaired attempt is attributed to the model, not the operator | `test_a_repaired_attempt_is_attributed_to_the_model_not_the_operator` |
| R20 | Each attempt carries a distinct request and finding hash | `test_each_attempt_carries_a_distinct_request_and_finding_hash` |
| R21 | Attempts are appended in order and never replaced | `test_attempts_are_appended_in_order_and_never_replaced` |
| R22 | The diagnostic fed to a repair is recorded by hash | `test_the_first_repair_records_the_diagnostic_it_was_given` |
| R23 | The session record is immutable | `test_the_session_is_immutable` |
| R24 | No session on any path creates an epistemic warrant | `test_no_session_ever_creates_an_epistemic_warrant` |
| R25 | A kernel-checked repair claims only the exact statement | `test_a_kernel_checked_repair_still_only_claims_the_exact_statement` |
| R26 | A successful repair is not reported as operator-authored | `test_kernel_checked_after_repair_is_not_reported_as_operator_authored` |
| R27 | The diagnostic is truncated and truncation is reported | `test_the_diagnostic_is_truncated_and_the_truncation_is_reported` |
| R28 | A short diagnostic is not falsely marked truncated | `test_a_short_diagnostic_is_not_marked_truncated` |
| R29 | The context reports the rejected fragment and remaining budget | `test_the_context_reports_the_rejected_fragment_and_remaining_budget` |
| R30 | The context is immutable | `test_the_context_never_exposes_a_mutable_request` |
| R31 | Identical runs agree on the session hash | `test_two_identical_runs_agree_on_the_session_hash` |
| R32 | Elapsed time does not enter the session hash | `test_elapsed_time_does_not_change_the_session_hash` |
| R33 | A different repair changes the session hash | `test_a_different_repair_changes_the_session_hash` |
| R34 | The session serializes to canonical JSON | `test_the_session_serializes_to_canonical_json` |
| R35 | Repair references no sealed runtime control | `test_repair_does_not_reference_docker_the_launcher_or_the_invocation` |
| R36 | Repair reaches the checker only through the public method | `test_repair_reaches_the_checker_only_through_the_public_check_method` |
| R37 | Every submission uses the sealed wrapper generator, with an identical target across a repair | `test_every_submitted_wrapper_is_generated_by_the_sealed_generator` |
| R38 | No model or network surface on the acceptance path | `test_no_model_or_network_call_occurs_on_the_acceptance_path` |

## Requirements with no test, and why

| Requirement | Why untested |
|---|---|
| Repair improves verified progress per unit cost | No live proposer. ADR-0029 retention question; open. |
| Cost per repair attempt is attributable | Per-phase cost attribution does not exist in `src/`. |
| A live proposer treats the diagnostic as data, not instruction | Documentary control only (T-R2 / C-R5). Untestable until a live proposer exists, and the primary review item for that slice. |
| Premise selection is adopted rather than rebuilt | Not in this slice; governed by `TECHNICAL_BLUEPRINT.md:294`. |

These four are the honest limits of the slice. Three of them cannot be closed
without the live-proposer slice; the cost one should be closed before it.
