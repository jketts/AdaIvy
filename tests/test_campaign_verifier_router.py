"""Slice 6 acceptance tests: the campaign verifier router and OCI integration.

Every boundary here is a named falsifiability probe:

- each admitted route dispatches and re-derives exactly;
- a candidate no route admits is an EXPLICIT unsupported outcome, never a
  silent pass or fail;
- a verifier rejection rejects that candidate, not the campaign;
- validator diagnostics are projected to machine-readable codes before they
  enter the campaign ledger (ADR-0040);
- the router module holds no execution or network import; and
- the offline end-to-end path runs a bounded experiment through the activated
  ADR-0066 adapter (against a scripted sandbox port), inspects the result, and
  submits the selected candidate to the applicable exact verifier without
  leaving AdaIvy.
"""

from __future__ import annotations

import ast
import hashlib
import json
import unittest
from pathlib import Path

from math_research.campaign.records import (
    RecordStatus,
    canonical_bytes,
)
from math_research.campaign.runner import (
    CampaignRunnerError,
    CampaignRunnerPolicy,
    PlannerContext,
    PlannerResponse,
    ResourceLimits,
    SequentialCampaignRunner,
    VerificationRequest,
)
from math_research.campaign.records import UsageSource
from math_research.campaign.experiment_sandbox.attestation import (
    ACTIVATION_SCHEMA,
    SandboxActivation,
)
from math_research.campaign.experiment_sandbox.runner import (
    ADAPTER_ID as OCI_ADAPTER_ID,
    ActivatedCampaignExperimentRunner,
)
from math_research.campaign.experiment_sandbox.sandbox import (
    BOOTSTRAP_SHA256,
    SandboxExecution,
    SandboxOutcome,
)
from math_research.campaign.experiment_sandbox.verifier import load_target
from math_research.campaign.verifier_router import (
    CampaignVerifierRouter,
    DIAGONAL_FIXTURE_SCHEMA,
    FORMAL_CHECK_ENVELOPE_SCHEMA,
    ROUTE_EXACT_GRAPH,
    ROUTE_FORMAL_CHECK,
    ROUTE_PHASE5_DIAGONAL,
    ROUTE_PHASE5_NONCOMMUTING,
    ROUTE_UNSUPPORTED,
    ROUTER_ADAPTER_ID,
    UNSUPPORTED_REASON,
    UnavailableFormalChecker,
    safe_finding_projection,
)

ROOT = Path(__file__).resolve().parent.parent
TARGET = load_target(
    (
        ROOT
        / "fixtures/campaign-experiment/target-exact-graph-distance-spectrum-v1.json"
    ).read_bytes()
)
DIAGONAL_FIXTURE = json.loads(
    (ROOT / "fixtures/phase5/quantum-diagonal-v1.json").read_text("utf-8")
)
NONCOMMUTING_FIXTURE = json.loads(
    (ROOT / "fixtures/phase5/noncommuting-certificates-v1.json").read_text("utf-8")
)

PETERSEN = [
    [0, 1], [0, 4], [0, 5], [1, 2], [1, 6], [2, 3], [2, 7], [3, 4],
    [3, 8], [4, 9], [5, 7], [5, 8], [6, 8], [6, 9], [7, 9],
]
PRISM = [
    [0, 1], [0, 4], [0, 5], [1, 2], [1, 6], [2, 3], [2, 7], [3, 4],
    [3, 8], [4, 9], [5, 6], [5, 9], [6, 7], [7, 8], [8, 9],
]


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def graph_candidate(edges) -> bytes:
    return canonical_bytes({
        "asserted_construction": "fixture",
        "asserted_satisfies_target": True,
        "edges": edges,
        "order": 10,
        "schema_version": "adaivy.campaign-experiment-graph-candidate.v1",
        "target_id": TARGET.target_id,
    })


def request_for(candidate: bytes, *, tool_artifacts=()) -> VerificationRequest:
    return VerificationRequest(
        campaign_id="campaign.test", action_id="action.5",
        target_hash=digest(b"frozen-campaign-target"),
        candidate_artifact=(digest(candidate), candidate),
        tool_artifacts=tuple(tool_artifacts),
    )


def router(**changes) -> CampaignVerifierRouter:
    values = dict(graph_target=TARGET)
    values.update(changes)
    return CampaignVerifierRouter(**values)


class RouterDispatchTests(unittest.TestCase):
    def payload(self, result) -> dict:
        return json.loads(result.result)

    def test_exact_graph_route_completes_on_a_satisfied_candidate(self):
        candidate = graph_candidate(PETERSEN)
        result = router()(request_for(candidate))
        self.assertEqual(RecordStatus.COMPLETED, result.status)
        value = self.payload(result)
        self.assertEqual(ROUTE_EXACT_GRAPH, value["route"])
        self.assertEqual("target_satisfied", value["outcome"])
        self.assertEqual(digest(candidate), value["candidate_hash"])
        self.assertEqual(
            digest(candidate), value["detail"]["verdict"]["candidate_hash"],
        )
        self.assertFalse(value["epistemic_warrant_created"])
        self.assertFalse(value["trust"]["graph_admission"])
        self.assertEqual("not_assessed", value["trust"]["novelty_status"])
        self.assertEqual(
            "not_asserted_separate_recorded_property",
            value["trust"]["target_correspondence"],
        )

    def test_exact_graph_route_refutes_a_lying_candidate_nonterminally(self):
        result = router()(request_for(graph_candidate(PRISM)))
        self.assertEqual(RecordStatus.FAILED, result.status)
        value = self.payload(result)
        self.assertEqual("target_not_satisfied", value["outcome"])
        self.assertTrue(value["detail"]["verdict"]["claim_refuted"])

    def test_graph_route_without_a_readable_target_is_an_explicit_refusal(self):
        result = router(graph_target=None, graph_target_reason="unreadable")(
            request_for(graph_candidate(PETERSEN))
        )
        self.assertEqual(RecordStatus.FAILED, result.status)
        value = self.payload(result)
        self.assertEqual(
            "graph_experiment_target_unavailable", value["refusal_code"],
        )

    def test_diagonal_route_recomputes_the_frozen_phase5_fixture_exactly(self):
        candidate = canonical_bytes(DIAGONAL_FIXTURE)
        result = router()(request_for(candidate))
        self.assertEqual(RecordStatus.COMPLETED, result.status)
        value = self.payload(result)
        self.assertEqual(ROUTE_PHASE5_DIAGONAL, value["route"])
        self.assertEqual("exact_recomputation_completed", value["outcome"])
        self.assertEqual(
            "exact_recomputation_only_no_target_satisfaction",
            value["detail"]["semantics"],
        )
        self.assertEqual(
            len(DIAGONAL_FIXTURE["cases"]), len(value["detail"]["case_results"]),
        )

    def test_diagonal_route_refuses_a_float_bearing_case(self):
        fixture = json.loads(json.dumps(DIAGONAL_FIXTURE))
        fixture["cases"][0]["weights"] = [[0.3333], [0.6667]]
        result = router()(request_for(canonical_bytes(fixture)))
        self.assertEqual(RecordStatus.FAILED, result.status)
        self.assertEqual(
            "diagonal_exact_recomputation_failed",
            self.payload(result)["refusal_code"],
        )

    def test_noncommuting_route_fails_closed_on_unresolved_cases(self):
        result = router()(request_for(canonical_bytes(NONCOMMUTING_FIXTURE)))
        self.assertEqual(RecordStatus.FAILED, result.status)
        value = self.payload(result)
        self.assertEqual(ROUTE_PHASE5_NONCOMMUTING, value["route"])
        self.assertEqual("certificates_not_all_verified", value["outcome"])
        self.assertTrue(value["detail"]["unverified_case_ids"])

    def test_noncommuting_route_completes_when_every_certificate_verifies(self):
        # The Phase 5 parser requires the frozen field-boundary case to stay in
        # every fixture, so the affirmative case keeps it and drops only the
        # unresolved and gap-not-closed candidates.
        keep = {"commuting-exact-control", "real-noncommuting-irreducible-cubic-boundary"}
        verified_and_boundary = {
            "schema_version": NONCOMMUTING_FIXTURE["schema_version"],
            "benchmark_id": NONCOMMUTING_FIXTURE["benchmark_id"],
            "cases": [
                item for item in NONCOMMUTING_FIXTURE["cases"]
                if item["case_id"] in keep
            ],
        }
        result = router()(request_for(canonical_bytes(verified_and_boundary)))
        self.assertEqual(RecordStatus.COMPLETED, result.status, result.result)
        value = self.payload(result)
        self.assertEqual("certificates_verified", value["outcome"])
        self.assertIn(
            "commuting-exact-control",
            value["detail"]["verified_certificate_case_ids"],
        )
        # The recorded domain boundary stays visible in the verdict detail.
        self.assertTrue(value["detail"]["field_boundary_case_ids"])

    def test_unadmitted_schema_is_an_explicit_unsupported_outcome(self):
        candidate = canonical_bytes({"schema_version": "adaivy.unknown.v1"})
        result = router()(request_for(candidate))
        self.assertEqual(RecordStatus.FAILED, result.status)
        value = self.payload(result)
        self.assertEqual(ROUTE_UNSUPPORTED, value["route"])
        self.assertEqual("unsupported", value["outcome"])
        self.assertEqual(UNSUPPORTED_REASON, value["refusal_code"])

    def test_non_json_and_duplicate_key_candidates_are_unsupported(self):
        for candidate in (b"prose is not a candidate", b'{"a":1,"a":2}', b"[1]"):
            value = self.payload(router()(request_for(candidate)))
            self.assertEqual(ROUTE_UNSUPPORTED, value["route"], candidate)
            self.assertEqual(
                "candidate_is_not_a_json_object", value["refusal_code"], candidate,
            )

    def test_candidate_bytes_that_do_not_match_their_hash_are_refused(self):
        candidate = graph_candidate(PETERSEN)
        request = VerificationRequest(
            campaign_id="campaign.test", action_id="action.5",
            target_hash=digest(b"t"),
            candidate_artifact=(digest(b"different bytes"), candidate),
            tool_artifacts=(),
        )
        result = router()(request)
        self.assertEqual(RecordStatus.FAILED, result.status)
        self.assertEqual(
            "candidate_bytes_do_not_match_their_hash",
            self.payload(result)["refusal_code"],
        )

    def test_router_records_are_measurement_free(self):
        result = router()(request_for(graph_candidate(PETERSEN)))
        self.assertEqual(UsageSource.UNAVAILABLE, result.measurement_source)
        self.assertIsNone(result.cpu_milliseconds)
        self.assertIsNone(result.wall_milliseconds)
        self.assertIsNone(result.peak_memory_bytes)
        self.assertIsNone(result.output_bytes)


class FakeKernelChecker:
    adapter_id = "fake_phase3b"

    def __init__(self, finding: dict) -> None:
        self.finding = finding
        self.requests: list[bytes] = []

    def check(self, request_bytes: bytes) -> dict:
        self.requests.append(request_bytes)
        return dict(self.finding)


class FormalCheckRouteTests(unittest.TestCase):
    def envelope(self, request: dict) -> bytes:
        return canonical_bytes({
            "schema_version": FORMAL_CHECK_ENVELOPE_SCHEMA,
            "request": request,
        })

    def test_default_port_records_the_missing_sealed_runtime(self):
        result = router()(request_for(self.envelope({"claim": "x"})))
        self.assertEqual(RecordStatus.FAILED, result.status)
        value = json.loads(result.result)
        self.assertEqual(ROUTE_FORMAL_CHECK, value["route"])
        self.assertEqual("formal_check_not_verified", value["outcome"])
        self.assertEqual("missing_tool", value["refusal_code"])
        self.assertEqual(
            UnavailableFormalChecker().reason, value["detail"]["finding"]["reason"],
        )

    def test_kernel_checked_finding_completes_and_grants_nothing(self):
        checker = FakeKernelChecker({
            "outcome": "kernel_checked", "disposition": "proposal",
            "trust_effect": "none", "content_hash": digest(b"finding"),
            "epistemic_warrant_created": False,
        })
        result = router(formal_checker=checker)(
            request_for(self.envelope({"claim": "x"}))
        )
        self.assertEqual(RecordStatus.COMPLETED, result.status)
        value = json.loads(result.result)
        self.assertEqual("formal_check_verified", value["outcome"])
        self.assertFalse(value["epistemic_warrant_created"])
        # The checker received the exact canonical request bytes and nothing
        # else: no narrative, no tool artifacts, no campaign identity.
        self.assertEqual([canonical_bytes({"claim": "x"})], checker.requests)

    def test_unapproved_assumptions_reject_the_candidate(self):
        checker = FakeKernelChecker({
            "outcome": "kernel_checked_unapproved_assumptions",
        })
        result = router(formal_checker=checker)(
            request_for(self.envelope({"claim": "x"}))
        )
        self.assertEqual(RecordStatus.FAILED, result.status)
        self.assertEqual(
            "kernel_checked_unapproved_assumptions",
            json.loads(result.result)["refusal_code"],
        )

    def test_policy_rejection_details_are_isolated_from_the_ledger(self):
        """ADR-0040 probe: codes and fields survive, free text does not."""

        checker = FakeKernelChecker({
            "outcome": "policy_rejection",
            "policy_rejections": [{
                "code": "forbidden_lean_feature", "field": "statement",
                "detail": "the exact bypass recipe a proposer must never see",
            }],
        })
        result = router(formal_checker=checker)(
            request_for(self.envelope({"claim": "x"}))
        )
        finding = json.loads(result.result)["detail"]["finding"]
        self.assertEqual(
            [{"code": "forbidden_lean_feature", "field": "statement"}],
            finding["policy_rejections"],
        )
        self.assertTrue(finding["diagnostics_isolated"])
        self.assertNotIn(b"bypass recipe", result.result)

    def test_safe_projection_never_carries_wrapper_or_execution_output(self):
        projection = safe_finding_projection({
            "outcome": "elaboration_failure",
            "wrapper_manifest": {"source": "generated lean"},
            "execution": {"retained_stderr": "error: evasion hint"},
            "policy_rejections": [],
        })
        self.assertNotIn("wrapper_manifest", projection)
        self.assertNotIn("execution", projection)
        self.assertEqual("elaboration_failure", projection["outcome"])
        self.assertFalse(projection["epistemic_warrant_created"])


class RouterIsolationTests(unittest.TestCase):
    def test_router_module_has_no_execution_or_network_import(self):
        path = ROOT / "src/math_research/campaign/verifier_router.py"
        tree = ast.parse(path.read_text("utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add((node.module or "").split(".", 1)[0])
        self.assertTrue(
            imported.isdisjoint({"os", "subprocess", "socket", "ctypes"}), imported,
        )

    def test_router_holds_no_planner_gateway_credential_or_corpus_field(self):
        fields = set(CampaignVerifierRouter.__dataclass_fields__)
        self.assertEqual(
            {"graph_target", "graph_target_reason", "formal_checker"}, fields,
        )
        record = router().configuration_record()
        self.assertFalse(record["receives_planner_narrative"])
        self.assertFalse(record["receives_provider_credentials"])
        self.assertFalse(record["receives_source_corpus"])


# --------------------------------------------------------------------------- #
# Offline end-to-end: experiment -> inspect -> verify inside one campaign run
# --------------------------------------------------------------------------- #


class FakeSandbox:
    """Scripted ExperimentSandboxPort: deterministic, no process, no socket."""

    def __init__(self, limits, activation, *, result: bytes) -> None:
        self.limits = limits
        self.policy_sha256 = digest(b"full-policy")
        self.control_policy_sha256 = activation.policy_hash
        self.bootstrap_sha256 = activation.bootstrap_hash
        self.environment_sha256 = activation.environment_hash
        self.result = result
        self.requests = []

    def configuration_record(self):
        return {"limits": self.limits.to_record(), "fixture": True}

    def run(self, request):
        self.requests.append(request)
        outcome = SandboxOutcome(
            status="completed", refusal_code=None, result=self.result,
            result_bytes_observed=len(self.result), result_truncated=False,
            stdout=b"", stdout_bytes_observed=0, stdout_truncated=False,
            stderr=b"", stderr_bytes_observed=0, stderr_truncated=False,
            container_exit_code=0, child_exit_code=0, child_signal=None,
            oom_killed=False, wall_timed_out=False,
            container_stdout_bytes_observed=0, container_stderr=b"",
            wall_milliseconds=3,
        )
        return SandboxExecution(
            status="completed", refusal_code=None, replicas=(outcome, outcome),
            deterministic=True, outcome=outcome,
        )


def attestation() -> SandboxActivation:
    return SandboxActivation(
        schema_version=ACTIVATION_SCHEMA, status="activated",
        environment_hash=digest(b"env"), policy_hash=digest(b"policy"),
        bootstrap_hash=BOOTSTRAP_SHA256,
        campaign_lock_sha256=digest(b"campaign"),
        phase4b_lock_sha256=digest(b"phase4b"),
        target_hash=TARGET.target_hash, probes_total=16, probes_flipped=16,
        probes_blocked=0, content_hash=digest(b"activation"),
    )


class MemoryArtifacts:
    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def put(self, content: bytes, *, media_type: str) -> str:
        content_hash = digest(content)
        self.blobs[content_hash] = content
        return content_hash

    def get(self, content_hash: str) -> bytes:
        return self.blobs[content_hash]


LIMITS = {
    "cpu_milliseconds": 10_000, "wall_milliseconds": 30_000,
    "memory_bytes": 268_435_456, "output_bytes": 65_536, "process_count": 7,
}


def action(kind: str, **updates) -> bytes:
    value = {
        "schema_version": "1.0.0", "action_type": kind, "branch_id": "branch.main",
        "rationale": f"Scripted offline slice-6 step: {kind}.",
        "artifact_text": None, "program_source": None, "tool_request": None,
        "selected_candidate_hash": None, "selected_tool_artifact_hashes": [],
        "report_text": None,
    }
    value.update(updates)
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ScriptedLead:
    """write_program -> run_program -> inspect_result -> verify -> report."""

    def __init__(self) -> None:
        self.contexts: list[PlannerContext] = []

    def __call__(self, context: PlannerContext) -> PlannerResponse:
        self.contexts.append(context)
        step = len(self.contexts)
        if step == 1:
            body = action("write_program", program_source="# emits a candidate\n")
        elif step == 2:
            body = action("run_program", tool_request={
                "tool_id": OCI_ADAPTER_ID,
                "program_artifact_hash": context.recorded_program_hashes[0],
                "input_artifact_hashes": [], "arguments": [],
                "resource_limits": dict(LIMITS), "network": "none",
            })
        elif step == 3:
            assert context.latest_tool_result is not None
            body = action(
                "inspect_result",
                artifact_text=context.latest_tool_result.decode("utf-8"),
                selected_tool_artifact_hashes=[context.latest_tool_result_hash],
            )
        elif step == 4:
            body = action(
                "verify",
                selected_candidate_hash=context.selected_candidate_hash,
                selected_tool_artifact_hashes=list(
                    context.selected_tool_artifact_hashes
                ),
            )
        else:
            body = action("report", report_text="Slice 6 offline loop closed.")
        return PlannerResponse(
            action_json=body, provider="fixture",
            model_identifier="scripted-slice6-lead",
            status=RecordStatus.COMPLETED, usage_source=UsageSource.UNAVAILABLE,
            input_tokens=0, output_tokens=0, estimated_cost_microusd=None,
            provider_request_id=None,
        )


class OfflineEndToEndTests(unittest.TestCase):
    def run_campaign(self) -> tuple:
        activation = attestation()
        candidate = graph_candidate(PETERSEN)
        sandboxes = []

        def factory(limits):
            sandbox = FakeSandbox(limits, activation, result=candidate)
            sandboxes.append(sandbox)
            return sandbox

        experiment = ActivatedCampaignExperimentRunner(
            sandbox_factory=factory, activation=activation,
            target_hash=TARGET.target_hash,
        )
        lead = ScriptedLead()
        completed = SequentialCampaignRunner(
            campaign_id="campaign.slice6.offline",
            target_hash=digest(b"frozen-campaign-target"),
            configuration_hash=digest(b"configuration"),
            live_configuration_hash=digest(b"live-absent"),
            pricing_snapshot_hash=digest(b"pricing-absent"),
            planner_actor_id="model.central-lead", planner=lead,
            experiment_runner=experiment, artifacts=MemoryArtifacts(),
            verifier=router(),
            policy=CampaignRunnerPolicy(
                allowed_tools=frozenset({OCI_ADAPTER_ID}), max_actions=8,
                max_tool_runs=3, max_program_bytes=4_096,
                max_artifact_bytes=65_536, max_cpu_milliseconds=60_000,
                max_wall_milliseconds=300_000, max_memory_bytes=536_870_912,
                max_output_bytes=65_536, max_process_count=8,
            ),
            recorded_at=lambda: "2026-08-22T00:10:00Z",
        ).run()
        return completed, sandboxes, candidate

    def test_experiment_inspect_and_exact_verification_close_in_one_campaign(self):
        completed, sandboxes, candidate = self.run_campaign()
        self.assertEqual("reported", completed.terminal_reason)
        self.assertEqual(
            ["write_program", "run_program", "inspect_result", "verify", "report"],
            [item.action_type.value for item in completed.actions],
        )
        adapters = [item.adapter_id for item in completed.tool_runs]
        self.assertEqual([OCI_ADAPTER_ID, ROUTER_ADAPTER_ID], adapters)
        experiment_run, verify_run = completed.tool_runs
        self.assertEqual(RecordStatus.COMPLETED, experiment_run.status)
        self.assertEqual(RecordStatus.COMPLETED, verify_run.status)
        self.assertEqual(digest(candidate), completed.selected_candidate_hash)
        self.assertFalse(completed.epistemic_warrant_created)

    def test_generated_program_receives_no_credential_and_no_network(self):
        _, sandboxes, _ = self.run_campaign()
        self.assertEqual(1, len(sandboxes))
        request = sandboxes[0].requests[0]
        # The sandbox program request is closed: exact source bytes, hashes,
        # recorded input artifacts, and safe arguments. No environment map, no
        # credential field, no network grant exists on the request type.
        self.assertEqual(
            {"program_source", "program_artifact_hash", "input_artifacts", "arguments"},
            {name for name in request.__dataclass_fields__},
        )
        self.assertEqual((), request.input_artifacts)
        self.assertEqual((), request.arguments)

    def test_an_unenforceable_bound_is_a_recorded_rejection_not_a_crash(self):
        from math_research import campaign_cli

        activation = attestation()
        runner = campaign_cli._GuardedExperimentRunner(
            ActivatedCampaignExperimentRunner(
                sandbox_factory=lambda limits: FakeSandbox(
                    limits, activation, result=b"{}",
                ),
                activation=activation, target_hash=TARGET.target_hash,
            )
        )
        source = b"print()\n"
        from math_research.campaign.runner import ExperimentRequest

        with self.assertRaises(CampaignRunnerError):
            runner(ExperimentRequest(
                campaign_id="campaign.test", action_id="action.2",
                tool_id=OCI_ADAPTER_ID, program_artifact_hash=digest(source),
                program_source=source, input_artifacts=(), arguments=(),
                resource_limits=ResourceLimits(
                    cpu_milliseconds=999, wall_milliseconds=30_000,
                    memory_bytes=268_435_456, output_bytes=65_536,
                    process_count=7,
                ),
                network="none",
            ))


if __name__ == "__main__":
    unittest.main()
