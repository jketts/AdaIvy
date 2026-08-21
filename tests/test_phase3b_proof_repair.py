"""Acceptance suite for ADR-0040 bounded Phase 3B proof repair.

Per ADR-0026 this suite is the slice's only executable record of its thresholds,
so every forbidden outcome is demonstrated impossible rather than left untested.

The sealed runtime is never invoked. `ScriptedLeanAdapter` overrides exactly one
method, `execute`, and inherits the real `validate` and `verify_output`, so
classification under test is the production classifier and only the container
call is scripted. That is what lets these cases run offline and still mean
something.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from math_research.phase3b.adapter import DockerLeanAdapter
from math_research.phase3b.records import (
    DeclaredAssumption,
    ExecutionLimits,
    FormalCheckOutcome,
    GeneratedWrapper,
    RawExecution,
    SourceKind,
    StreamCapture,
)
from math_research.phase3b.repair import (
    REPAIRABLE_OUTCOMES,
    _identity_hashes,
    ProofRepairService,
    ProposedProof,
    RepairContext,
    RepairLimits,
    RepairTermination,
    TheoremIdentityViolation,
    _repaired_request_bytes,
)
from math_research.phase3b.serialization import canonical_bytes, public_value, sha256_bytes
from math_research.phase3b.service import FormalCheckingService
from math_research.phase3b.validation import parse_request_bytes

FIXTURES = Path("fixtures/phase3b")
FIXED_TIME = "2026-08-19T00:00:00Z"

ELABORATION_ERROR = json.dumps({"severity": "error", "data": "unsolved goals", "pos": {"line": 3}})
NO_AXIOMS = json.dumps({"severity": "information", "data": "does not depend on any axioms"})
UNAPPROVED = json.dumps({"severity": "information", "data": "depends on axioms: [AdaIvyAssumptionFoo]"})
APPROVED = json.dumps({"severity": "information", "data": "depends on axioms: [propext]"})


def capture(text: str) -> StreamCapture:
    data = text.encode()
    return StreamCapture(len(data), sha256_bytes(data), text, len(data), False)


def execution(stdout: str, *, exit_code: int = 0, reason: str = "completed", removed: bool = True) -> RawExecution:
    return RawExecution(exit_code, reason, 10, capture(stdout), capture(""), removed, ())


ELABORATION_FAILED = execution(ELABORATION_ERROR, exit_code=1)
KERNEL_CHECKED = execution(NO_AXIOMS)


class ScriptedLeanAdapter(DockerLeanAdapter):
    """Real validation and classification; scripted container execution."""

    def __init__(self, script: list[RawExecution], limits: ExecutionLimits | None = None) -> None:
        super().__init__(limits or ExecutionLimits())
        self.script = list(script)
        self.wrappers: list[GeneratedWrapper] = []

    def execute(self, wrapper: GeneratedWrapper) -> RawExecution:
        self.wrappers.append(wrapper)
        if not self.script:
            raise AssertionError("the checker was called more times than the script allows")
        return self.script.pop(0)


class ScriptedProposer:
    """Deterministic proposer. Performs no model or network call."""

    def __init__(self, fragments: list[str | None]) -> None:
        self.fragments = list(fragments)
        self.contexts: list[RepairContext] = []

    def propose(self, context: RepairContext) -> ProposedProof | None:
        self.contexts.append(context)
        if not self.fragments:
            return None
        fragment = self.fragments.pop(0)
        return None if fragment is None else ProposedProof(fragment)


def origin_bytes(name: str = "valid", **overrides: object) -> bytes:
    request = parse_request_bytes((FIXTURES / f"{name}.json").read_bytes())
    if overrides:
        request = replace(request, **overrides)
    return canonical_bytes(request)


def session(
    script: list[RawExecution],
    fragments: list[str | None],
    *,
    limits: RepairLimits | None = None,
    source: bytes | None = None,
):
    adapter = ScriptedLeanAdapter(script)
    proposer = ScriptedProposer(fragments)
    service = ProofRepairService(FormalCheckingService(adapter), proposer, limits)
    result = service.run(source or origin_bytes(), created_at=FIXED_TIME)
    return result, adapter, proposer


class RepairableBoundaryTests(unittest.TestCase):
    """Only Lean's elaboration failure may be followed. Everything else stops."""

    def test_only_elaboration_failure_is_declared_repairable(self) -> None:
        self.assertEqual(REPAIRABLE_OUTCOMES, frozenset({FormalCheckOutcome.ELABORATION_FAILURE}))

    def test_an_elaboration_failure_is_repaired_and_can_succeed(self) -> None:
        result, adapter, proposer = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        self.assertIs(result.termination, RepairTermination.KERNEL_CHECKED)
        self.assertEqual(result.attempts_used, 2)
        self.assertEqual(len(proposer.contexts), 1)
        self.assertEqual(adapter.script, [])

    def test_a_policy_rejection_is_never_repaired(self) -> None:
        """A validator diagnostic describes how to evade the validator."""
        result, _, proposer = session([], ["by simp"], source=b'{"malformed"')
        self.assertIs(result.termination, RepairTermination.ORIGIN_UNPARSABLE)
        self.assertEqual(result.attempts_used, 1)
        self.assertEqual(proposer.contexts, [])
        self.assertIs(result.attempts[0].outcome, FormalCheckOutcome.POLICY_REJECTION)

    def test_a_model_fragment_the_validator_refuses_stops_the_loop(self) -> None:
        """The loop must not iterate against the validator."""
        result, _, proposer = session([ELABORATION_FAILED], ["by exact? sorry"])
        self.assertIs(result.termination, RepairTermination.PROPOSER_REJECTED)
        self.assertIs(result.attempts[-1].outcome, FormalCheckOutcome.POLICY_REJECTION)
        self.assertEqual(len(proposer.contexts), 1, "no second proposal after a policy rejection")

    def test_every_non_elaboration_outcome_terminates_without_a_proposal(self) -> None:
        cases = (
            (execution(NO_AXIOMS), FormalCheckOutcome.KERNEL_CHECKED, RepairTermination.KERNEL_CHECKED),
            (execution(APPROVED), FormalCheckOutcome.KERNEL_CHECKED_APPROVED_AXIOMS, RepairTermination.KERNEL_CHECKED),
            (execution(UNAPPROVED), FormalCheckOutcome.KERNEL_CHECKED_UNAPPROVED_ASSUMPTIONS, RepairTermination.OUTCOME_NOT_REPAIRABLE),
            (execution("", reason="timeout"), FormalCheckOutcome.TIMEOUT, RepairTermination.OUTCOME_NOT_REPAIRABLE),
            (execution("", reason="output_limit"), FormalCheckOutcome.OUTPUT_LIMIT, RepairTermination.OUTCOME_NOT_REPAIRABLE),
            (execution("", reason="sandbox_failure"), FormalCheckOutcome.SANDBOX_FAILURE, RepairTermination.OUTCOME_NOT_REPAIRABLE),
            (execution(NO_AXIOMS, removed=False), FormalCheckOutcome.SANDBOX_FAILURE, RepairTermination.OUTCOME_NOT_REPAIRABLE),
        )
        for raw, outcome, termination in cases:
            with self.subTest(outcome=outcome.value):
                result, _, proposer = session([raw], ["by simp"])
                self.assertIs(result.attempts[0].outcome, outcome)
                self.assertIs(result.termination, termination)
                self.assertEqual(result.attempts_used, 1)
                self.assertEqual(proposer.contexts, [], "a terminal outcome must not consult a proposer")

    def test_a_meaning_test_failure_is_never_repaired(self) -> None:
        """Repairing until meaning tests pass would optimize against the check."""
        source = origin_bytes("meaning-test")
        request = parse_request_bytes(source)
        self.assertTrue(request.meaning_tests, "fixture must carry meaning tests")
        failure = execution(json.dumps({"severity": "error", "data": "unsolved goals", "pos": {"line": 4096}}), exit_code=1)
        result, _, proposer = session([failure], ["by simp"], source=source)
        self.assertIs(result.attempts[0].outcome, FormalCheckOutcome.MEANING_TEST_FAILURE)
        self.assertIs(result.termination, RepairTermination.OUTCOME_NOT_REPAIRABLE)
        self.assertEqual(proposer.contexts, [])


class TheoremIdentityTests(unittest.TestCase):
    """A repair may change the proof and nothing else."""

    def test_the_proposer_surface_exposes_only_a_proof_fragment(self) -> None:
        self.assertEqual([field for field in ProposedProof.__dataclass_fields__], ["proof_fragment"])

    def test_a_repaired_request_differs_only_in_proof_identity_and_source(self) -> None:
        origin = parse_request_bytes(origin_bytes())
        candidate_bytes, candidate_id = _repaired_request_bytes(origin, fragment="by simp", attempt_index=1)
        candidate = parse_request_bytes(candidate_bytes)
        self.assertEqual(candidate.target_statement, origin.target_statement)
        self.assertEqual(candidate.imports, origin.imports)
        self.assertEqual(candidate.assumptions, origin.assumptions)
        self.assertEqual(candidate.declaration_name, origin.declaration_name)
        self.assertEqual(candidate.claim_id, origin.claim_id)
        self.assertEqual(candidate.meaning_tests, origin.meaning_tests)
        self.assertEqual(candidate.semantic_alignment_id, origin.semantic_alignment_id)
        self.assertEqual(candidate.proof_fragment, "by simp")
        self.assertEqual(candidate.request_id, candidate_id)
        self.assertNotEqual(candidate.request_id, origin.request_id)
        differing = {
            name for name in origin.__dataclass_fields__
            if getattr(origin, name) != getattr(candidate, name)
        }
        self.assertEqual(differing, {"request_id", "source_kind", "proof_fragment"})

    def test_identity_hashes_are_frozen_from_the_origin_and_survive_repair(self) -> None:
        result, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        origin = parse_request_bytes(origin_bytes())
        self.assertTrue(result.theorem_identity_preserved)
        for attempt in result.attempts:
            request = parse_request_bytes(
                _repaired_request_bytes(origin, fragment="ignored", attempt_index=0)[0]
            )
            self.assertEqual(request.target_statement, origin.target_statement)
            self.assertIsNotNone(attempt.request_id)

    def test_a_candidate_that_alters_the_theorem_raises_rather_than_records(self) -> None:
        """Structurally unreachable through the port; asserted anyway."""
        origin = parse_request_bytes(origin_bytes())
        adapter = ScriptedLeanAdapter([ELABORATION_FAILED])
        service = ProofRepairService(FormalCheckingService(adapter), ScriptedProposer([]))
        widened = canonical_bytes(replace(origin, target_statement="(n : Nat) : n = n + 0"))
        with self.assertRaises(TheoremIdentityViolation):
            service._assert_identity(widened, _identity_hashes(origin), origin)

    def test_an_assumption_cannot_be_smuggled_in_through_a_repair(self) -> None:
        origin = parse_request_bytes(origin_bytes())
        adapter = ScriptedLeanAdapter([ELABORATION_FAILED])
        service = ProofRepairService(FormalCheckingService(adapter), ScriptedProposer([]))
        smuggled = canonical_bytes(
            replace(origin, assumptions=(DeclaredAssumption("AdaIvyAssumptionFree", "(n : Nat)"),))
        )
        with self.assertRaises(TheoremIdentityViolation):
            service._assert_identity(smuggled, _identity_hashes(origin), origin)


class BoundedBudgetTests(unittest.TestCase):
    """A stuck proof cannot silently consume the run."""

    def test_the_attempt_cap_is_hard_and_counts_the_origin(self) -> None:
        result, adapter, proposer = session(
            [ELABORATION_FAILED] * 3, ["by simp", "by omega", "by decide"], limits=RepairLimits(max_attempts=3)
        )
        self.assertIs(result.termination, RepairTermination.ATTEMPTS_EXHAUSTED)
        self.assertEqual(result.attempts_used, 3)
        self.assertEqual(result.attempts_allowed, 3)
        self.assertEqual(len(proposer.contexts), 2, "two repairs after the origin, then the cap")
        self.assertEqual(adapter.script, [])

    def test_a_single_attempt_limit_permits_no_repair_at_all(self) -> None:
        result, _, proposer = session([ELABORATION_FAILED], ["by simp"], limits=RepairLimits(max_attempts=1))
        self.assertIs(result.termination, RepairTermination.ATTEMPTS_EXHAUSTED)
        self.assertEqual(result.attempts_used, 1)
        self.assertEqual(proposer.contexts, [])

    def test_a_declining_proposer_ends_the_session(self) -> None:
        result, _, _ = session([ELABORATION_FAILED], [None])
        self.assertIs(result.termination, RepairTermination.PROPOSER_DECLINED)
        self.assertEqual(result.attempts_used, 1)

    def test_a_duplicate_candidate_ends_the_session_without_resubmission(self) -> None:
        result, adapter, _ = session(
            [ELABORATION_FAILED] * 3, ["by simp", "by simp"], limits=RepairLimits(max_attempts=4)
        )
        self.assertIs(result.termination, RepairTermination.DUPLICATE_CANDIDATE)
        self.assertEqual(result.attempts_used, 2, "the origin and one distinct repair")
        self.assertEqual(len(adapter.script), 1, "the repeated candidate was never sent")

    def test_repeating_the_origin_fragment_is_also_a_duplicate(self) -> None:
        origin = parse_request_bytes(origin_bytes())
        result, adapter, _ = session([ELABORATION_FAILED], [origin.proof_fragment])
        self.assertIs(result.termination, RepairTermination.DUPLICATE_CANDIDATE)
        self.assertEqual(result.attempts_used, 1)

    def test_limits_reject_an_unbounded_or_absurd_configuration(self) -> None:
        for attempts in (0, -1, 17):
            with self.subTest(attempts=attempts), self.assertRaises(ValueError):
                RepairLimits(max_attempts=attempts)
        for size in (0, 255, 65_537):
            with self.subTest(size=size), self.assertRaises(ValueError):
                RepairLimits(max_diagnostic_bytes=size)

    def test_proposer_calls_are_counted_in_the_record(self) -> None:
        result, _, _ = session(
            [ELABORATION_FAILED] * 3, ["by simp", "by omega", "by decide"], limits=RepairLimits(max_attempts=3)
        )
        self.assertEqual(result.proposer_calls, 2)


class ProvenanceTests(unittest.TestCase):
    """Every attempt is its own record, and model authorship is never hidden."""

    def test_a_repaired_attempt_is_attributed_to_the_model_not_the_operator(self) -> None:
        result, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        self.assertIs(result.attempts[0].source_kind, SourceKind.OPERATOR)
        self.assertIs(result.attempts[1].source_kind, SourceKind.MODEL)
        self.assertIs(result.attempts[1].finding.source_kind, SourceKind.MODEL)

    def test_each_attempt_carries_a_distinct_request_and_finding_hash(self) -> None:
        result, _, _ = session(
            [ELABORATION_FAILED] * 3, ["by simp", "by omega"], limits=RepairLimits(max_attempts=3)
        )
        self.assertEqual(len({attempt.request_id.value for attempt in result.attempts}), 3)
        self.assertEqual(len({attempt.request_hash for attempt in result.attempts}), 3)
        self.assertEqual(len({attempt.finding_content_hash for attempt in result.attempts}), 3)

    def test_attempts_are_appended_in_order_and_never_replaced(self) -> None:
        result, _, _ = session(
            [ELABORATION_FAILED] * 3, ["by simp", "by omega"], limits=RepairLimits(max_attempts=3)
        )
        self.assertEqual([attempt.attempt_index for attempt in result.attempts], [0, 1, 2])

    def test_the_first_repair_records_the_diagnostic_it_was_given(self) -> None:
        result, _, proposer = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        self.assertIsNone(result.attempts[0].diagnostic_hash, "the origin had no diagnostic")
        self.assertEqual(result.attempts[1].diagnostic_hash, proposer.contexts[0].diagnostic_hash)

    def test_the_session_is_immutable(self) -> None:
        result, _, _ = session([KERNEL_CHECKED], [])
        with self.assertRaises(FrozenInstanceError):
            result.termination = RepairTermination.ATTEMPTS_EXHAUSTED  # type: ignore[misc]


class NoTrustPromotionTests(unittest.TestCase):
    """Repair adds no warrant, on any path."""

    def test_no_session_ever_creates_an_epistemic_warrant(self) -> None:
        cases = (
            ([KERNEL_CHECKED], []),
            ([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"]),
            ([ELABORATION_FAILED, ELABORATION_FAILED], ["by simp", None]),
            ([execution(UNAPPROVED)], []),
        )
        for script, fragments in cases:
            with self.subTest(script=len(script)):
                result, _, _ = session(list(script), list(fragments))
                self.assertFalse(result.epistemic_warrant_created)
                for attempt in result.attempts:
                    self.assertFalse(attempt.finding.epistemic_warrant_created)
                    self.assertEqual(attempt.finding.disposition, "proposal")
                    self.assertEqual(attempt.finding.trust_effect, "none")
                    self.assertFalse(attempt.finding.semantic_alignment_approved)
                    self.assertFalse(attempt.finding.novelty_approved)
                    self.assertFalse(attempt.finding.significance_approved)
                    self.assertFalse(attempt.finding.contribution_approved)
                    self.assertFalse(attempt.finding.source_applicability_approved)

    def test_a_kernel_checked_repair_still_only_claims_the_exact_statement(self) -> None:
        result, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        self.assertTrue(result.kernel_checked)
        final = result.final_finding
        assert final is not None
        self.assertTrue(final.exact_statement_only)
        self.assertTrue(final.meaning_tests_diagnostic_only)

    def test_kernel_checked_after_repair_is_not_reported_as_operator_authored(self) -> None:
        """The successful proof came from the model; the record must say so."""
        result, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        final = result.final_finding
        assert final is not None
        self.assertIs(final.source_kind, SourceKind.MODEL)


class DiagnosticBoundTests(unittest.TestCase):
    """What goes back to a proposer is bounded, hashed, and honestly labelled."""

    def test_the_diagnostic_is_truncated_and_the_truncation_is_reported(self) -> None:
        noisy = execution(json.dumps({"severity": "error", "data": "x" * 9_000, "pos": {"line": 3}}), exit_code=1)
        result, _, proposer = session([noisy, KERNEL_CHECKED], ["by simp"], limits=RepairLimits(max_attempts=2, max_diagnostic_bytes=512))
        context = proposer.contexts[0]
        self.assertTrue(context.diagnostic_truncated)
        self.assertLessEqual(len(context.diagnostic.encode()), 512)
        self.assertIs(result.termination, RepairTermination.KERNEL_CHECKED)

    def test_a_short_diagnostic_is_not_marked_truncated(self) -> None:
        _, _, proposer = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        self.assertFalse(proposer.contexts[0].diagnostic_truncated)
        self.assertIn("unsolved goals", proposer.contexts[0].diagnostic)

    def test_the_context_reports_the_rejected_fragment_and_remaining_budget(self) -> None:
        origin = parse_request_bytes(origin_bytes())
        _, _, proposer = session(
            [ELABORATION_FAILED, ELABORATION_FAILED, KERNEL_CHECKED],
            ["by simp", "by omega"],
            limits=RepairLimits(max_attempts=3),
        )
        first, second = proposer.contexts
        self.assertEqual(first.rejected_proof_fragment, origin.proof_fragment)
        self.assertEqual(second.rejected_proof_fragment, "by simp")
        self.assertEqual(first.attempts_remaining, 2)
        self.assertEqual(second.attempts_remaining, 1)

    def test_the_context_never_exposes_a_mutable_request(self) -> None:
        _, _, proposer = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        context = proposer.contexts[0]
        with self.assertRaises(FrozenInstanceError):
            context.target_statement = "anything"  # type: ignore[misc]


class DeterminismTests(unittest.TestCase):
    """The same script yields the same session hash."""

    def test_two_identical_runs_agree_on_the_session_hash(self) -> None:
        first, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        second, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        self.assertEqual(first.content_hash, second.content_hash)
        self.assertEqual(first.id, second.id)

    def test_elapsed_time_does_not_change_the_session_hash(self) -> None:
        baseline, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        slow = replace(ELABORATION_FAILED, elapsed_milliseconds=99_999)
        other, _, _ = session([slow, KERNEL_CHECKED], ["by simp"])
        self.assertEqual(baseline.content_hash, other.content_hash)

    def test_a_different_repair_changes_the_session_hash(self) -> None:
        first, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        second, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by omega"])
        self.assertNotEqual(first.content_hash, second.content_hash)

    def test_the_session_serializes_to_canonical_json(self) -> None:
        result, _, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        value = public_value(result)
        self.assertEqual(value["termination"], "kernel_checked")
        self.assertEqual(value["epistemic_warrant_created"], False)
        self.assertEqual(value["policy_version"], "phase3b-proof-repair-v1")
        canonical_bytes(result)


class SealedRuntimeTests(unittest.TestCase):
    """The slice adds no Lean capability and touches no sealed control."""

    def test_repair_does_not_reference_docker_the_launcher_or_the_invocation(self) -> None:
        source = Path("src/math_research/phase3b/repair.py").read_text()
        for forbidden in ("subprocess", "docker", "Popen", "INVOCATION", "FIXED_INPUT_PATH", "RUNTIME_DIGEST"):
            self.assertNotIn(forbidden, source, f"repair must not reach {forbidden}")

    def test_repair_reaches_the_checker_only_through_the_public_check_method(self) -> None:
        calls: list[bytes] = []

        class RecordingService(FormalCheckingService):
            def check(self, request_bytes: bytes, *, created_at: str):
                calls.append(request_bytes)
                return super().check(request_bytes, created_at=created_at)

        adapter = ScriptedLeanAdapter([ELABORATION_FAILED, KERNEL_CHECKED])
        service = ProofRepairService(RecordingService(adapter), ScriptedProposer(["by simp"]))
        result = service.run(origin_bytes(), created_at=FIXED_TIME)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.attempts_used, 2)
        for payload in calls:
            parse_request_bytes(payload)

    def test_every_submitted_wrapper_is_generated_by_the_sealed_generator(self) -> None:
        result, adapter, _ = session([ELABORATION_FAILED, KERNEL_CHECKED], ["by simp"])
        self.assertEqual(len(adapter.wrappers), 2)
        for wrapper in adapter.wrappers:
            self.assertLessEqual(wrapper.manifest.wrapper_byte_length, 262_144)
            self.assertTrue(wrapper.manifest.runtime_hash)
        self.assertNotEqual(
            adapter.wrappers[0].manifest.wrapper_hash, adapter.wrappers[1].manifest.wrapper_hash
        )
        self.assertEqual(
            adapter.wrappers[0].manifest.target_hash, adapter.wrappers[1].manifest.target_hash,
            "the target must be byte-identical across a repair",
        )
        self.assertEqual(result.attempts_used, 2)

    def test_no_model_or_network_call_occurs_on_the_acceptance_path(self) -> None:
        source = Path("src/math_research/phase3b/repair.py").read_text()
        for forbidden in ("http", "socket", "urllib", "requests", "openai", "anthropic"):
            self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
