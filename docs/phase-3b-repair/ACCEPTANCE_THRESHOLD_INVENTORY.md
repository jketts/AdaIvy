# Acceptance Threshold Inventory — Phase 3B Bounded Proof Repair

ADR-0040. Every threshold below is an executable assertion in
`tests/test_phase3b_proof_repair.py`. Per ADR-0026 this inventory is a reading
aid; the suite is the record.

## Hard bounds

| Threshold | Value | Where enforced | Where asserted |
|---|---|---|---|
| Attempts per session, including the origin | default 4, range 1–16 | `RepairLimits.__post_init__` | `test_the_attempt_cap_is_hard_and_counts_the_origin`, `test_limits_reject_an_unbounded_or_absurd_configuration` |
| Diagnostic bytes handed to a proposer | default 4,096, range 256–65,536 | `RepairLimits.__post_init__`, `_bounded_diagnostic` | `test_the_diagnostic_is_truncated_and_the_truncation_is_reported` |
| Identical candidate resubmissions | 0 | `seen_fragments` | `test_a_duplicate_candidate_ends_the_session_without_resubmission`, `test_repeating_the_origin_fragment_is_also_a_duplicate` |
| Wrapper bytes per submission | 262,144 (inherited, unchanged) | sealed wrapper generator | `test_every_submitted_wrapper_is_generated_by_the_sealed_generator` |
| Model calls on the acceptance path | 0 | scripted proposer only | `test_no_model_or_network_call_occurs_on_the_acceptance_path` |
| Network calls on the acceptance path | 0 | no network surface in module | `test_no_model_or_network_call_occurs_on_the_acceptance_path` |
| Trust promotions | 0 | `epistemic_warrant_created = False` | `test_no_session_ever_creates_an_epistemic_warrant` |

A limit of 1 attempt must permit no repair at all, not one repair
(`test_a_single_attempt_limit_permits_no_repair_at_all`). This is the boundary
most likely to drift to an off-by-one.

## Repairable-outcome closure

`REPAIRABLE_OUTCOMES` is exactly `{ELABORATION_FAILURE}`, asserted by equality
rather than membership (`test_only_elaboration_failure_is_declared_repairable`)
so that adding an outcome fails the suite.

| Outcome | Repairable | Termination | Rationale |
|---|---|---|---|
| `elaboration_failure` | **yes** | continues | Lean rejecting a proof is a proof error |
| `kernel_checked` | no | `kernel_checked` | success |
| `kernel_checked_approved_standard_axioms` | no | `kernel_checked` | success, axioms disclosed |
| `kernel_checked_unapproved_assumptions` | no | `outcome_not_repairable` | iterating here optimizes toward clean-looking axioms |
| `meaning_test_failure` | no | `outcome_not_repairable` | iterating here optimizes against the semantic check |
| `policy_rejection` (origin) | no | `origin_unparsable` | no theorem identity to freeze |
| `policy_rejection` (repair) | no | `proposer_rejected` | a validator diagnostic describes how to evade the validator |
| `timeout` | no | `outcome_not_repairable` | no diagnostic, highest budget cost |
| `output_limit` | no | `outcome_not_repairable` | no usable diagnostic |
| `sandbox_failure` | no | `outcome_not_repairable` | infrastructure, not mathematics |

`test_every_non_elaboration_outcome_terminates_without_a_proposal` additionally
asserts the proposer is **never consulted** on a terminal outcome, so a
non-repairable result cannot spend a proposer call.

## Theorem identity

Frozen from the origin request and re-derived from candidate bytes before every
submission: target statement, import manifest, assumption manifest, declaration
name, claim identity, meaning tests.

The strongest assertion is
`test_a_repaired_request_differs_only_in_proof_identity_and_source`, which
computes the full set of differing dataclass fields and requires it to equal
exactly `{request_id, source_kind, proof_fragment}`. A new field on
`FormalCheckRequest` that a repair could vary will fail this test rather than
slip through.

## Provenance and determinism

| Property | Assertion |
|---|---|
| A repaired attempt is attributed to `MODEL`, never inherited | `test_a_repaired_attempt_is_attributed_to_the_model_not_the_operator` |
| A successful repair is not reported as operator-authored | `test_kernel_checked_after_repair_is_not_reported_as_operator_authored` |
| Each attempt has a distinct request id, request hash, and finding hash | `test_each_attempt_carries_a_distinct_request_and_finding_hash` |
| Attempts are appended in order | `test_attempts_are_appended_in_order_and_never_replaced` |
| The diagnostic fed in is recorded by hash | `test_the_first_repair_records_the_diagnostic_it_was_given` |
| Identical runs agree on the session hash | `test_two_identical_runs_agree_on_the_session_hash` |
| Elapsed time does not enter the session hash | `test_elapsed_time_does_not_change_the_session_hash` |
| A different repair changes the session hash | `test_a_different_repair_changes_the_session_hash` |

## Mutation evidence

Six adversarial edits to `repair.py`, each confirmed to fail the suite. Recorded
because a threshold inventory that has never been tested against a violation is
a claim, not evidence.

| Mutation | Failures |
|---|---|
| widen `REPAIRABLE_OUTCOMES` to policy rejection and meaning-test failure | 2 |
| keep operator attribution on a repaired attempt | 3 |
| remove the attempt cap | 3 |
| set `epistemic_warrant_created = True` | 5 |
| disable duplicate-candidate detection | 2 |
| disable the theorem-identity check | 2 |

## Thresholds deliberately absent

- **Solve rate.** No live proposer exists, so any figure would be a property of
  the scripted fixtures.
- **Cost per closed obligation.** Requires per-phase cost attribution, which
  does not exist. Named as a blocker in the entry gate report.
- **Repair depth that helps.** An ADR-0029 retention question, unmeasurable
  without a live proposer.
