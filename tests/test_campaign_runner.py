"""Scripted, zero-process acceptance tests for the bounded campaign runner."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from math_research.campaign.records import RecordStatus, UsageSource
from math_research.campaign.replay import build_campaign_export
from math_research.campaign.runner import (
    CampaignRunnerError,
    CampaignRunnerPolicy,
    ExperimentResult,
    PlannerResponse,
    SequentialCampaignRunner,
    parse_campaign_action,
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


def action(kind: str, **updates) -> bytes:
    value = {
        "schema_version": "1.0.0",
        "action_type": kind,
        "branch_id": "branch.main",
        "rationale": f"Perform {kind} within the frozen campaign.",
        "artifact_text": None,
        "program_source": None,
        "tool_request": None,
        "selected_candidate_hash": None,
        "selected_tool_artifact_hashes": [],
        "report_text": None,
    }
    value.update(updates)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def limits(**updates):
    value = {
        "cpu_milliseconds": 100,
        "wall_milliseconds": 200,
        "memory_bytes": 4096,
        "output_bytes": 2048,
        "process_count": 1,
    }
    value.update(updates)
    return value


def run_action(program_hash: str, **updates) -> bytes:
    request = {
        "tool_id": "exact_python",
        "program_artifact_hash": program_hash,
        "input_artifact_hashes": [],
        "arguments": ["bound=5"],
        "resource_limits": limits(),
        "network": "none",
    }
    request.update(updates)
    return action("run_program", tool_request=request)


def response(raw: bytes) -> PlannerResponse:
    return PlannerResponse(
        action_json=raw,
        provider="azure_openai",
        model_identifier="gpt-5.6-sol",
        status=RecordStatus.COMPLETED,
        usage_source=UsageSource.API_REPORTED,
        input_tokens=20,
        output_tokens=10,
        estimated_cost_microusd=100,
        provider_request_id="provider-request",
    )


def tool_result(*, adapter="exact_python") -> ExperimentResult:
    return ExperimentResult(
        adapter_id=adapter,
        adapter_version="1.0.0",
        adapter_configuration_hash=digest(f"{adapter} config"),
        environment_hash=digest(f"{adapter} environment"),
        status=RecordStatus.COMPLETED,
        result=TOOL_RESULT if adapter == "exact_python" else b'{"verified":true}',
        stdout=b"stdout-exact\n",
        stderr=b"stderr-empty\n",
        measurement_source=UsageSource.LOCALLY_MEASURED,
        cpu_milliseconds=10,
        wall_milliseconds=20,
        peak_memory_bytes=1024,
        output_bytes=64,
    )


class MemoryArtifacts:
    def __init__(self, events):
        self.values = {}
        self.events = events

    def put(self, content: bytes, *, media_type: str) -> str:
        content_hash = digest(content)
        self.values[content_hash] = content
        self.events.append(("artifact", content_hash, media_type))
        return content_hash

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


class RecordingExperiment:
    def __init__(self, events):
        self.requests = []
        self.events = events

    def __call__(self, request):
        self.requests.append(request)
        self.events.append(("execute", request.program_artifact_hash))
        return tool_result()


class RecordingVerifier:
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return tool_result(adapter="exact_verifier")


def policy(**updates):
    value = dict(
        allowed_tools=frozenset({"exact_python"}),
        max_actions=8,
        max_tool_runs=3,
        max_program_bytes=4096,
        max_artifact_bytes=8192,
        max_cpu_milliseconds=500,
        max_wall_milliseconds=1000,
        max_memory_bytes=8192,
        max_output_bytes=4096,
        max_process_count=2,
    )
    value.update(updates)
    return CampaignRunnerPolicy(**value)


def runner(planner, experiment, artifacts, verifier, *, runner_policy=None):
    return SequentialCampaignRunner(
        campaign_id="campaign.runner.test",
        target_hash=TARGET,
        configuration_hash=CONFIGURATION,
        live_configuration_hash=LIVE_CONFIGURATION,
        pricing_snapshot_hash=PRICING,
        planner_actor_id="model.central-lead",
        planner=planner,
        experiment_runner=experiment,
        artifacts=artifacts,
        verifier=verifier,
        policy=runner_policy or policy(),
        recorded_at=lambda: "2026-08-21T18:00:00Z",
    )


class CampaignRunnerTests(unittest.TestCase):
    def test_failed_planner_attempt_is_retained_in_the_campaign_ledger(self):
        events = []
        artifacts = MemoryArtifacts(events)

        class FailedPlanner:
            def __call__(self, context):
                return PlannerResponse(
                    action_json=b'{"provider_result":"failed"}',
                    provider="azure_openai", model_identifier="gpt-5.6-sol",
                    status=RecordStatus.FAILED, usage_source=UsageSource.API_REPORTED,
                    input_tokens=7, output_tokens=0, estimated_cost_microusd=77,
                    provider_request_id="failed-provider-request",
                )

        completed = runner(
            FailedPlanner(), RecordingExperiment(events), artifacts, RecordingVerifier(),
        ).run()
        self.assertEqual("planner_failed", completed.terminal_reason)
        self.assertEqual("plan", completed.actions[0].action_type.value)
        self.assertEqual(RecordStatus.FAILED, completed.actions[0].status)
        self.assertEqual(RecordStatus.FAILED, completed.model_calls[0].status)
        build_campaign_export(
            campaign_id=completed.campaign_id, target_hash=TARGET,
            configuration_hash=CONFIGURATION, actions=completed.actions,
            model_calls=completed.model_calls, tool_runs=completed.tool_runs,
        )

    def test_plan_write_run_inspect_select_verify_and_report(self):
        events = []
        artifacts = MemoryArtifacts(events)
        candidate_hash = digest(CANDIDATE)
        program_hash = digest(PROGRAM)

        def inspect(context):
            self.assertEqual(TOOL_RESULT, context.latest_tool_result)
            self.assertEqual(digest(TOOL_RESULT), context.latest_tool_result_hash)
            return action(
                "inspect_result",
                selected_candidate_hash=candidate_hash,
                selected_tool_artifact_hashes=[context.latest_tool_result_hash],
            )

        def verify(context):
            return action(
                "verify",
                selected_candidate_hash=context.selected_candidate_hash,
                selected_tool_artifact_hashes=list(context.selected_tool_artifact_hashes),
            )

        planner = ScriptedPlanner([
            action("derive", artifact_text=CANDIDATE),
            action("write_program", program_source=PROGRAM),
            lambda context: run_action(context.recorded_program_hashes[0]),
            inspect,
            verify,
            action("report", report_text="Bounded campaign completed; warrant remains absent."),
        ])
        experiment = RecordingExperiment(events)
        verifier = RecordingVerifier()
        completed = runner(planner, experiment, artifacts, verifier).run()

        self.assertEqual("reported", completed.terminal_reason)
        self.assertEqual(
            ["derive", "write_program", "run_program", "inspect_result", "verify", "report"],
            [item.action_type.value for item in completed.actions],
        )
        self.assertEqual(candidate_hash, completed.selected_candidate_hash)
        self.assertEqual((digest(TOOL_RESULT),), completed.selected_tool_artifact_hashes)
        self.assertFalse(completed.epistemic_warrant_created)
        self.assertEqual(6, len(completed.model_calls))
        self.assertEqual(2, len(completed.tool_runs))
        # Program bytes are durably stored before the injected executor is called.
        self.assertLess(
            events.index(("artifact", program_hash, "text/x-python")),
            events.index(("execute", program_hash)),
        )
        self.assertEqual(PROGRAM.encode(), experiment.requests[0].program_source)

        self.assertEqual(1, len(verifier.requests))
        request = verifier.requests[0]
        self.assertEqual((candidate_hash, CANDIDATE.encode()), request.candidate_artifact)
        self.assertEqual(((digest(TOOL_RESULT), TOOL_RESULT),), request.tool_artifacts)
        # No program, planner ledger, unselected stdout, or stderr reaches verifier.
        self.assertNotIn(PROGRAM.encode(), repr(request).encode())
        self.assertNotIn(b"stdout-exact", repr(request).encode())
        exported = build_campaign_export(
            campaign_id=completed.campaign_id,
            target_hash=TARGET,
            configuration_hash=CONFIGURATION,
            actions=completed.actions,
            model_calls=completed.model_calls,
            tool_runs=completed.tool_runs,
        )
        self.assertEqual("adaivy_campaign", exported.attribution_status)
        self.assertEqual(6, exported.usage["requests_attempted"])

    def test_schema_file_is_closed_and_matches_runner_actions(self):
        schema = json.loads(Path("schemas/model-campaign-action-v1.schema.json").read_text())
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            {
                "derive", "write_program", "run_program", "inspect_result", "falsify",
                "verify", "ask_user", "suspend_branch", "report",
            },
            set(schema["properties"]["action_type"]["enum"]),
        )
        self.assertEqual(set(schema["required"]), set(schema["properties"]))

    def test_unknown_action_and_extra_field_are_rejected(self):
        with self.assertRaisesRegex(CampaignRunnerError, "unknown"):
            parse_campaign_action(action("launch_shell"))
        extra = json.loads(action("derive", artifact_text="candidate"))
        extra["host_path"] = "/tmp"
        with self.assertRaisesRegex(CampaignRunnerError, "closed schema"):
            parse_campaign_action(json.dumps(extra))

    def _assert_run_rejected_before_executor(self, run_step, pattern, *, runner_policy=None):
        events = []
        experiment = RecordingExperiment(events)
        planner = ScriptedPlanner([
            action("write_program", program_source=PROGRAM),
            run_step,
        ])
        with self.assertRaisesRegex(CampaignRunnerError, pattern):
            runner(
                planner, experiment, MemoryArtifacts(events), RecordingVerifier(),
                runner_policy=runner_policy,
            ).run()
        self.assertEqual([], experiment.requests)
        self.assertFalse(any(item[0] == "execute" for item in events))

    def test_unknown_tool_is_rejected_before_executor(self):
        self._assert_run_rejected_before_executor(
            lambda context: run_action(context.recorded_program_hashes[0], tool_id="shell"),
            "unknown campaign tool",
        )

    def test_only_a_prior_recorded_program_may_run(self):
        self._assert_run_rejected_before_executor(
            run_action(digest("unrecorded source")),
            "prior recorded program",
        )

    def test_host_path_argument_is_rejected_before_executor(self):
        self._assert_run_rejected_before_executor(
            lambda context: run_action(
                context.recorded_program_hashes[0], arguments=["/Users/operator/secret"],
            ),
            "host path",
        )

    def test_environment_request_is_rejected_before_executor(self):
        self._assert_run_rejected_before_executor(
            lambda context: run_action(
                context.recorded_program_hashes[0], environment={"TOKEN": "secret"},
            ),
            "closed schema",
        )

    def test_network_request_is_rejected_before_executor(self):
        self._assert_run_rejected_before_executor(
            lambda context: run_action(
                context.recorded_program_hashes[0], network="egress",
            ),
            "network must be exactly",
        )

    def test_unknown_resource_request_is_rejected_before_executor(self):
        requested = limits(gpus=1)
        self._assert_run_rejected_before_executor(
            lambda context: run_action(
                context.recorded_program_hashes[0], resource_limits=requested,
            ),
            "resource_limits fields differ",
        )

    def test_excess_resource_request_is_rejected_before_executor(self):
        requested = limits(memory_bytes=999_999)
        self._assert_run_rejected_before_executor(
            lambda context: run_action(
                context.recorded_program_hashes[0], resource_limits=requested,
            ),
            "memory_bytes exceeds",
        )

    def test_verify_cannot_add_unselected_tool_artifact(self):
        events = []
        artifacts = MemoryArtifacts(events)
        candidate_hash = digest(CANDIDATE)

        def inspect(context):
            return action(
                "inspect_result", selected_candidate_hash=candidate_hash,
                selected_tool_artifact_hashes=[context.latest_tool_result_hash],
            )

        planner = ScriptedPlanner([
            action("derive", artifact_text=CANDIDATE),
            action("write_program", program_source=PROGRAM),
            lambda context: run_action(context.recorded_program_hashes[0]),
            inspect,
            lambda context: action(
                "verify", selected_candidate_hash=context.selected_candidate_hash,
                selected_tool_artifact_hashes=[*context.selected_tool_artifact_hashes, digest("extra")],
            ),
        ])
        verifier = RecordingVerifier()
        with self.assertRaisesRegex(CampaignRunnerError, "differ from the inspected selection"):
            runner(planner, RecordingExperiment(events), artifacts, verifier).run()
        self.assertEqual([], verifier.requests)


if __name__ == "__main__":
    unittest.main()
