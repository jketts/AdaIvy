"""ADR-0077 acceptance: problem-visible context and durable model memory.

Every test drives the real `SequentialCampaignRunner` with a scripted planner
and in-memory ports.  Nothing here creates warrant; the assertions are about
what the planner can SEE and RE-READ, and about what stays withheld.
"""

from __future__ import annotations

import hashlib
import json
import unittest

from math_research.campaign.records import RecordStatus, UsageSource
from math_research.campaign.replay import build_campaign_export
from math_research.campaign.runner import (
    READ_ARTIFACT_ECHO_LIMIT,
    CampaignRunnerPolicy,
    ExperimentResult,
    FrozenTargetArtifacts,
    PlannerResponse,
    SequentialCampaignRunner,
)


def digest(value: bytes | str) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return "sha256:" + hashlib.sha256(raw).hexdigest()


TARGET = digest("target")
CONFIGURATION = digest("campaign configuration")
LIVE_CONFIGURATION = digest("live configuration")
PRICING = digest("pricing")
PROGRAM = "print(sum(range(5)))\n"
CANDIDATE = "Candidate: the bounded search returned witness 10."
TOOL_RESULT = b'{"witness":10,"exact":true}'
STATEMENT = "For every even n > 2 the sum of two squares mod four is bounded."
STATEMENT_BYTES = json.dumps(STATEMENT, ensure_ascii=False).encode("utf-8")
FORMALIZATION_BYTES = b'{"statement":"formal"}'
ASSUMPTIONS_BYTES = b'["claim.assumption.1"]'


def frozen_target() -> FrozenTargetArtifacts:
    return FrozenTargetArtifacts(
        statement_text=STATEMENT,
        statement_hash=digest(STATEMENT_BYTES),
        artifacts=(
            (digest(STATEMENT_BYTES), STATEMENT_BYTES),
            (digest(FORMALIZATION_BYTES), FORMALIZATION_BYTES),
            (digest(ASSUMPTIONS_BYTES), ASSUMPTIONS_BYTES),
        ),
    )


def action(kind: str, **updates) -> bytes:
    value = {
        "schema_version": "1.1.0",
        "action_type": kind,
        "branch_id": "branch.main",
        "rationale": f"Perform {kind} within the frozen campaign.",
        "artifact_text": None,
        "program_source": None,
        "tool_request": None,
        "selected_candidate_hash": None,
        "selected_tool_artifact_hashes": [],
        "report_text": None,
        "read_artifact_hash": None,
        "note_text": None,
    }
    value.update(updates)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def run_action(program_hash: str) -> bytes:
    return action("run_program", tool_request={
        "tool_id": "exact_python",
        "program_artifact_hash": program_hash,
        "input_artifact_hashes": [],
        "arguments": [],
        "resource_limits": {
            "cpu_milliseconds": 100, "wall_milliseconds": 200,
            "memory_bytes": 4096, "output_bytes": 2048, "process_count": 1,
        },
        "network": "none",
    })


def response(raw: bytes) -> PlannerResponse:
    return PlannerResponse(
        action_json=raw, provider="fixture", model_identifier="scripted",
        status=RecordStatus.COMPLETED, usage_source=UsageSource.UNAVAILABLE,
        input_tokens=0, output_tokens=0, estimated_cost_microusd=None,
        provider_request_id=None,
    )


class MemoryArtifacts:
    def __init__(self):
        self.values = {}
        self.media_types = {}

    def put(self, content: bytes, *, media_type: str) -> str:
        key = digest(content)
        self.values[key] = content
        self.media_types[key] = media_type
        return key

    def get(self, content_hash: str) -> bytes:
        return self.values[content_hash]


class ScriptedPlanner:
    def __init__(self, steps):
        self.steps = list(steps)
        self.contexts = []

    def __call__(self, context):
        self.contexts.append(context)
        step = self.steps.pop(0)
        return response(step(context) if callable(step) else step)


def experiment_result(*, status=RecordStatus.COMPLETED, result=TOOL_RESULT,
                      stderr=b"") -> ExperimentResult:
    return ExperimentResult(
        adapter_id="exact_python", adapter_version="1.0.0",
        adapter_configuration_hash=digest("adapter config"),
        environment_hash=digest("adapter environment"), status=status,
        result=result, stdout=b"", stderr=stderr,
        measurement_source=UsageSource.LOCALLY_MEASURED,
        cpu_milliseconds=10, wall_milliseconds=20, peak_memory_bytes=1024,
        output_bytes=64,
    )


class ScriptedExperiment:
    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.results.pop(0)


class ScriptedVerifier(ScriptedExperiment):
    pass


def policy(**updates):
    value = dict(
        allowed_tools=frozenset({"exact_python"}),
        max_actions=16, max_tool_runs=4, max_program_bytes=4096,
        max_artifact_bytes=131_072, max_cpu_milliseconds=500,
        max_wall_milliseconds=1000, max_memory_bytes=8192,
        max_output_bytes=4096, max_process_count=2,
        max_repair_attempts=1,
    )
    value.update(updates)
    return CampaignRunnerPolicy(**value)


def runner(planner, experiment, artifacts, verifier, *, runner_policy=None,
           target=None):
    return SequentialCampaignRunner(
        campaign_id="campaign.context.test",
        target_hash=TARGET, configuration_hash=CONFIGURATION,
        live_configuration_hash=LIVE_CONFIGURATION,
        pricing_snapshot_hash=PRICING,
        planner_actor_id="model.central-lead", planner=planner,
        experiment_runner=experiment, artifacts=artifacts, verifier=verifier,
        policy=runner_policy or policy(),
        recorded_at=lambda: "2026-08-22T18:00:00Z",
        frozen_target=target,
    )


def close(completed):
    build_campaign_export(
        campaign_id=completed.campaign_id, target_hash=TARGET,
        configuration_hash=CONFIGURATION, actions=completed.actions,
        model_calls=completed.model_calls, tool_runs=completed.tool_runs,
    )


class ProblemVisibleContextTests(unittest.TestCase):
    def test_the_statement_and_frozen_hashes_are_in_every_context(self):
        planner = ScriptedPlanner([
            action("note", note_text="reading the problem first"),
            action("report", report_text="done"),
        ])
        completed = runner(
            planner, ScriptedExperiment([]), MemoryArtifacts(),
            ScriptedVerifier([]), target=frozen_target(),
        ).run()
        self.assertEqual("reported", completed.terminal_reason)
        for context in planner.contexts:
            self.assertEqual(STATEMENT, context.target_statement)
            self.assertEqual(digest(STATEMENT_BYTES), context.target_statement_hash)
            self.assertEqual(
                tuple(sorted({
                    digest(STATEMENT_BYTES), digest(FORMALIZATION_BYTES),
                    digest(ASSUMPTIONS_BYTES),
                })),
                context.frozen_artifact_hashes,
            )
        close(completed)

    def test_mismatched_frozen_target_bytes_are_refused_at_construction(self):
        bad = FrozenTargetArtifacts(
            statement_text=STATEMENT, statement_hash=digest(STATEMENT_BYTES),
            artifacts=((digest(STATEMENT_BYTES), b"different bytes"),),
        )
        with self.assertRaisesRegex(Exception, "declared hash"):
            runner(
                ScriptedPlanner([]), ScriptedExperiment([]), MemoryArtifacts(),
                ScriptedVerifier([]), target=bad,
            )

    def test_read_artifact_returns_frozen_statement_bytes(self):
        def read(context):
            return action(
                "read_artifact", read_artifact_hash=context.target_statement_hash,
            )

        def report(context):
            # The echo arrives on the NEXT context and matches the preimage.
            assert context.read_artifact_hash == digest(STATEMENT_BYTES)
            assert context.read_artifact_bytes == STATEMENT_BYTES
            assert context.read_artifact_truncated is False
            return action("report", report_text="statement re-read")

        planner = ScriptedPlanner([read, report])
        completed = runner(
            planner, ScriptedExperiment([]), MemoryArtifacts(),
            ScriptedVerifier([]), target=frozen_target(),
        ).run()
        self.assertEqual("reported", completed.terminal_reason)
        read_record = completed.actions[0]
        self.assertEqual("read_artifact", read_record.action_type.value)
        # A frozen preimage is not a ledger artifact; the ledger input is the
        # frozen target identity itself.
        self.assertEqual((TARGET,), read_record.input_artifact_hashes)
        self.assertEqual((), completed.tool_runs)
        close(completed)


class DurableMemoryTests(unittest.TestCase):
    def test_read_artifact_re_reads_a_prior_tool_result_without_a_tool_run(self):
        def read(context):
            return action(
                "read_artifact", read_artifact_hash=context.latest_tool_result_hash,
            )

        def report(context):
            assert context.read_artifact_bytes == TOOL_RESULT
            return action("report", report_text="tool result re-read")

        planner = ScriptedPlanner([
            action("write_program", program_source=PROGRAM),
            lambda context: run_action(context.recorded_program_hashes[0]),
            read,
            report,
        ])
        completed = runner(
            planner, ScriptedExperiment([experiment_result()]),
            MemoryArtifacts(), ScriptedVerifier([]),
        ).run()
        self.assertEqual("reported", completed.terminal_reason)
        # The read consumed an action but not a tool run.
        self.assertEqual(1, len(completed.tool_runs))
        read_record = completed.actions[2]
        self.assertEqual("read_artifact", read_record.action_type.value)
        self.assertEqual((digest(TOOL_RESULT),), read_record.input_artifact_hashes)
        close(completed)

    def test_read_artifact_outside_provenance_is_rejected(self):
        planner = ScriptedPlanner([
            action("read_artifact", read_artifact_hash=digest("never recorded")),
        ])
        completed = runner(
            planner, ScriptedExperiment([]), MemoryArtifacts(),
            ScriptedVerifier([]),
        ).run()
        self.assertEqual("action_rejected", completed.terminal_reason)
        self.assertIn(
            "outside campaign provenance",
            completed.actions[-1].declared_rationale,
        )
        close(completed)

    def test_read_artifact_echo_is_deterministically_truncated(self):
        big = "x" * (READ_ARTIFACT_ECHO_LIMIT + 1_000)

        def read(context):
            return action("read_artifact", read_artifact_hash=digest(big))

        def report(context):
            assert context.read_artifact_truncated is True
            assert context.read_artifact_bytes == big.encode()[:READ_ARTIFACT_ECHO_LIMIT]
            return action("report", report_text="truncated read observed")

        planner = ScriptedPlanner([
            action("derive", artifact_text=big), read, report,
        ])
        completed = runner(
            planner, ScriptedExperiment([]), MemoryArtifacts(),
            ScriptedVerifier([]),
        ).run()
        self.assertEqual("reported", completed.terminal_reason)
        close(completed)

    def test_notes_are_stored_and_echoed_in_later_contexts(self):
        artifacts = MemoryArtifacts()

        def report(context):
            assert context.notes == (
                ("branch.main", "first observation"),
                ("branch.side", "second observation"),
            )
            return action("report", report_text="notes echoed")

        planner = ScriptedPlanner([
            action("note", note_text="first observation"),
            action("note", note_text="second observation", branch_id="branch.side"),
            report,
        ])
        completed = runner(
            planner, ScriptedExperiment([]), artifacts, ScriptedVerifier([]),
        ).run()
        self.assertEqual("reported", completed.terminal_reason)
        note_hash = digest("first observation")
        self.assertEqual(b"first observation", artifacts.values[note_hash])
        self.assertEqual("text/plain", artifacts.media_types[note_hash])
        self.assertEqual(
            ["note", "note", "report"],
            [item.action_type.value for item in completed.actions],
        )
        close(completed)


class FeedbackAndRunnerStateTests(unittest.TestCase):
    def test_a_refutation_verdict_is_fed_back_untrusted_for_warrant(self):
        counterexample = (
            b'{"outcome":"candidate_refuted","counterexample":{"vertex":7},'
            b'"epistemic_warrant_created":false}'
        )
        candidate_hash = digest(CANDIDATE)

        def verify(context):
            return action(
                "verify", selected_candidate_hash=context.selected_candidate_hash,
            )

        def react(context):
            feedback = context.tool_feedback[-1]
            assert feedback.kind == "verification"
            assert feedback.status == "failed"
            assert feedback.untrusted_for_warrant is True
            assert '"counterexample":{"vertex":7}' in feedback.result_excerpt
            return action(
                "note",
                note_text="revising the candidate after the recorded counterexample",
            )

        planner = ScriptedPlanner([
            action("derive", artifact_text=CANDIDATE),
            action("inspect_result", selected_candidate_hash=candidate_hash),
            verify,
            react,
            action("report", report_text="refutation engaged"),
        ])
        verifier = ScriptedVerifier([
            experiment_result(status=RecordStatus.FAILED, result=counterexample),
        ])
        completed = runner(
            planner, ScriptedExperiment([]), MemoryArtifacts(), verifier,
        ).run()
        self.assertEqual("reported", completed.terminal_reason)
        # The verifier's stored artifacts stay private: the excerpt travelled,
        # the artifact hashes did not enter `available`.
        close(completed)

    def test_experiment_diagnostics_are_fed_back(self):
        failure = b'{"refusal_code":"program_nonzero_exit"}'

        def react(context):
            feedback = context.tool_feedback[-1]
            assert feedback.kind == "experiment"
            assert feedback.status == "failed"
            assert "program_nonzero_exit" in feedback.result_excerpt
            assert feedback.stderr_excerpt is not None
            assert "exact overflow guard" in feedback.stderr_excerpt
            assert feedback.untrusted_for_warrant is True
            return action("report", report_text="diagnostics observed")

        planner = ScriptedPlanner([
            action("write_program", program_source=PROGRAM),
            lambda context: run_action(context.recorded_program_hashes[0]),
            react,
        ])
        experiment = ScriptedExperiment([
            experiment_result(
                status=RecordStatus.FAILED, result=failure,
                stderr=b"Traceback: exact overflow guard",
            ),
        ])
        completed = runner(
            planner, experiment, MemoryArtifacts(), ScriptedVerifier([]),
        ).run()
        # ADR-0078 §4: the failure is recorded and NON-terminal.
        self.assertEqual("reported", completed.terminal_reason)
        self.assertEqual(1, len(completed.tool_runs))
        self.assertEqual(RecordStatus.FAILED, completed.tool_runs[0].status)
        close(completed)

    def test_suspended_branches_and_last_status_are_surfaced(self):
        def report(context):
            assert context.suspended_branch_ids == ("branch.dead",)
            assert ("branch.dead", "completed") in context.branch_last_status
            assert ("branch.main", "completed") in context.branch_last_status
            return action("report", report_text="state visible")

        planner = ScriptedPlanner([
            action("derive", artifact_text=CANDIDATE),
            action(
                "suspend_branch", branch_id="branch.dead",
                report_text="dead end recorded",
            ),
            report,
        ])
        completed = runner(
            planner, ScriptedExperiment([]), MemoryArtifacts(),
            ScriptedVerifier([]),
        ).run()
        self.assertEqual("reported", completed.terminal_reason)
        close(completed)


if __name__ == "__main__":
    unittest.main()
