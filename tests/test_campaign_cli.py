"""Offline acceptance tests for the ADR-0065 campaign operator entrypoint.

Every assertion here encodes an ADR-0065 acceptance gate. The fixture path is
driven through `campaign_cli.main` with `socket`, `subprocess` and the provider
gateway builder replaced by callables that raise, so "made no model or network
call" is measured rather than asserted in prose. Each new boundary additionally
carries a named single-field falsifiability probe: a boundary that cannot be
made to fail proves nothing.
"""

from __future__ import annotations

import contextlib
import io
import json
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from math_research import campaign_cli
from math_research.campaign.records import canonical_bytes, canonical_hash
from math_research.campaign.replay import verify_campaign_export
from math_research.campaign_cli import (
    MAX_ACTIONS_CEILING,
    REFUSAL_ACTIVATION_FAILED,
    REFUSAL_ACTIVATION_NOT_EXECUTED,
    REFUSAL_ARTIFACT_BYTES,
    REFUSAL_BUDGET_EXCEEDS_CAP,
    REFUSAL_FACTS_MISMATCH,
    REFUSAL_LIVE_REQUIRES_ARTIFACTS,
    REFUSAL_LIVE_REQUIRES_EXECUTE,
    REFUSAL_NOT_ACKNOWLEDGED,
    REFUSAL_NOVELTY_ABSENT,
    REFUSAL_PROVIDER_MISMATCH,
    REFUSAL_ROOT_RECORDED,
    REFUSAL_TARGET_MISMATCH,
    SANDBOX_GATE_DECISION,
    SANDBOX_REFUSAL_REASON,
    VERIFIER_ABSENT_REASON,
)
from math_research.domain.entities import OpaqueId
from math_research.novelty import NoveltyRecheck, write_recheck
from math_research.phase2.live_config import (
    create_live_run_configuration,
    write_live_run_configuration,
)
from math_research.phase2.pricing import create_pricing_snapshot, write_pricing_snapshot
from math_research.phase2.records import BudgetLimits
from math_research.provider_activation import (
    LIVE_PROBE_ACKNOWLEDGEMENT,
    LiveProviderProbeResult,
    StaticProviderPreflight,
)


CAMPAIGN_ID = "campaign.offline.acceptance.v1"
RECHECK_INSTANT = "2026-08-22T00:00:00Z"
RUN_INSTANT = "2026-08-22T00:10:00Z"

#: Bounds are derived from ADR-0065 ceilings, never tuned to a fixture.
BOUNDS = {
    "max_actions": 8,
    "max_tool_runs": 3,
    "max_model_calls": 8,
    "max_input_tokens": 20_000,
    "max_output_tokens": 20_000,
    "max_cost_microusd": 1_000_000,
    "max_program_bytes": 4_096,
    "max_artifact_bytes": 65_536,
    "max_context_bytes": 65_536,
    "max_cpu_milliseconds": 1_000,
    "max_wall_milliseconds": 2_000,
    "max_memory_bytes": 67_108_864,
    "max_output_bytes": 65_536,
    "max_process_count": 1,
}


def invoke(*argv: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = campaign_cli.main(list(argv))
    return code, json.loads(buffer.getvalue())


def _forbidden(name: str):
    def refuse(*_args, **_kwargs):
        raise AssertionError(f"offline campaign path performed {name}")

    return refuse


@contextlib.contextmanager
def no_effects():
    """Fail loudly if an offline path opens a socket, a process, or a gateway."""

    with (
        mock.patch.object(socket, "socket", _forbidden("a socket call")),
        mock.patch.object(socket, "create_connection", _forbidden("a socket connect")),
        mock.patch.object(socket, "getaddrinfo", _forbidden("a DNS lookup")),
        mock.patch.object(subprocess, "Popen", _forbidden("a subprocess spawn")),
        mock.patch.object(subprocess, "run", _forbidden("a subprocess run")),
        mock.patch.object(campaign_cli, "build_gateway", _forbidden("a gateway build")),
        mock.patch.object(
            campaign_cli, "run_live_provider_probe", _forbidden("an activation probe"),
        ),
    ):
        yield


def write_config(root: Path, **overrides: int) -> Path:
    path = root / "config.json"
    bounds = {**BOUNDS, **overrides}
    argv = [
        "config-create", str(path),
        "--campaign-configuration-id", "config.campaign.offline.v1",
        "--allowed-tool", "exact_python",
    ]
    for name, value in sorted(bounds.items()):
        argv.extend(["--" + name.replace("_", "-"), str(value)])
    code, payload = invoke(*argv)
    if code != 0:
        raise AssertionError(payload)
    return path


def write_target(root: Path) -> tuple[Path, dict]:
    path = root / "target.json"
    code, payload = invoke("target", str(path))
    assert code == 0, payload
    return path, json.loads(path.read_text(encoding="utf-8"))


def write_novelty(root: Path, target: dict, *, next_action_id: str = CAMPAIGN_ID) -> Path:
    path = root / f"novelty-recheck-{next_action_id}.json"
    record = NoveltyRecheck(
        recheck_id="recheck.campaign.offline.v1",
        checkpoint="before_research",
        subject_id=target["problem_id"],
        subject_hash=target["dossier_content_hash"],
        next_action_id=next_action_id,
        performed_by="operator.repository-owner",
        performed_at=RECHECK_INSTANT,
        protocol_id="protocol.offline.no-search.v1",
        query_terms=("even sum",),
        searched_sources=("none: the offline fixture path performs no search",),
        equivalence_checks=("none: the offline fixture path performs no check",),
        evidence_refs=(("evidence.campaign.frozen-target", target["dossier_hash"]),),
        outcome="inconclusive",
        limitations=(
            "No literature search was performed; this record binds the offline "
            "acceptance run and asserts no novelty.",
        ),
        prior_art_relationship="unresolved",
        prior_resolution="unresolved",
        prior_resolution_verification="unresolved",
        previous_recheck_id=None,
        previous_recheck_hash=None,
    ).finalized()
    write_recheck(record, path)
    return path


def live_pair(root: Path, *, provider: str = "azure_openai", attempts: int = 4):
    pricing = create_pricing_snapshot(
        snapshot_id=OpaqueId("pricing.campaign.offline.v1"), provider=provider,
        model_identifier="gpt-5.6-sol", source="confirmed acceptance rate",
        captured_at="2026-08-21T00:00:00Z", currency="USD",
        input_microusd_per_million_tokens=10_000_000,
        output_microusd_per_million_tokens=20_000_000,
    )
    configuration = create_live_run_configuration(
        configuration_id=OpaqueId("config.campaign.live.v1"), provider=provider,
        model_identifier="gpt-5.6-sol",
        pricing_snapshot_id=OpaqueId("pricing.campaign.offline.v1"),
        call_timeout_milliseconds=10_000, per_call_input_token_reserve=100,
        per_call_output_token_reserve=100,
        budget=BudgetLimits(
            max_input_tokens=1_000, max_output_tokens=1_000,
            max_cost_microusd=1_000_000, max_wall_milliseconds=60_000,
            max_attempts=attempts,
        ),
    )
    live_path = root / "live-config.json"
    pricing_path = root / "pricing.json"
    write_live_run_configuration(configuration, live_path)
    write_pricing_snapshot(pricing, pricing_path)
    return configuration, pricing, live_path, pricing_path


def passed_static(configuration, pricing) -> StaticProviderPreflight:
    return StaticProviderPreflight(
        status="passed", provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        configuration_hash=configuration.content_hash,
        pricing_snapshot_hash=pricing.content_hash,
        route_hash=canonical_hash({"route": "stubbed-for-offline-test"}),
        missing_variables=(), failed_checks=(), reserved_probe_cost_microusd=1_000,
    )


def failed_activation(configuration, pricing, *, executed: bool) -> LiveProviderProbeResult:
    """A 401-shaped activation: one attempted request, zero completed responses."""

    return LiveProviderProbeResult(
        probe_status="failed" if executed else "not_executed",
        provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        configuration_hash=configuration.content_hash,
        pricing_snapshot_hash=pricing.content_hash,
        route_hash=canonical_hash({"route": "stubbed-for-offline-test"}),
        probe_request_hash=(canonical_hash({"probe": "request"}) if executed else None),
        observed_at=RUN_INSTANT, acknowledgement_confirmed=True,
        static_preflight_status="passed",
        endpoint_reachability="reached" if executed else "not_tested",
        authentication_status="rejected" if executed else "not_tested",
        deployment_route_status="indeterminate" if executed else "not_tested",
        provider_identity_status="failed" if executed else "not_tested",
        structured_output_capability="failed" if executed else "not_tested",
        operational_readiness="failed" if executed else "not_tested",
        failure_classification="auth_failed" if executed else "live_probe_not_acknowledged",
        sanitized_failure=None,
        requests_attempted=1 if executed else 0,
        responses_completed=0, responses_succeeded=0,
        responses_failed=1 if executed else 0, responses_incomplete=0,
        usage_reported_calls=0, input_tokens=0, output_tokens=0,
        estimated_cost_microusd=0, provider_request_id=None,
    )


class CampaignEntrypointFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        with no_effects():
            self.config = write_config(self.root)
            self.target_path, self.target = write_target(self.root)
            self.recheck = write_novelty(self.root, self.target)

    def run_campaign(self, name: str, *extra: str) -> tuple[int, dict, Path]:
        root = self.root / name
        with no_effects():
            code, payload = invoke(
                "run", str(root), CAMPAIGN_ID,
                "--config", str(self.config),
                "--recorded-at", RUN_INSTANT,
                "--novelty-recheck", str(self.recheck),
                *extra,
            )
        return code, payload, root

    # --- gate 1: the fixture path closes a campaign with no model or network ---

    def test_fixture_path_closes_a_campaign_with_zero_model_and_network_calls(self):
        code, payload, root = self.run_campaign("first")
        self.assertEqual(0, code, payload)
        self.assertEqual("recorded", payload["status"])
        self.assertEqual("reported", payload["terminal_reason"])
        facts = payload["facts"]
        self.assertEqual(["fixture"], facts["providers"])
        self.assertEqual(
            ["derive", "inspect_result", "verify", "report"], facts["action_types"],
        )
        self.assertEqual("report", facts["terminal_action_type"])
        # A scripted planner produced no provider usage, so the campaign may not
        # present itself as measured work.
        self.assertEqual("unavailable", facts["measurement_status"])
        self.assertEqual(0, facts["usage"]["usage_reported_calls"])
        self.assertEqual(0, facts["usage"]["estimated_cost_microusd"])
        export = verify_campaign_export((root / "campaign.json").read_bytes())
        self.assertEqual(facts["content_hash"], export.content_hash)
        self.assertEqual(facts["operational_hash"], export.operational_hash)
        self.assertNotEqual(export.content_hash, export.operational_hash)

    # --- gate 2: byte-identical output across runs and processes ---

    def test_two_fixture_runs_on_identical_inputs_are_byte_identical(self):
        _, _, first = self.run_campaign("first")
        _, _, second = self.run_campaign("second")
        for name in ("campaign.json", "campaign-facts.json", "target.json"):
            self.assertEqual(
                (first / name).read_bytes(), (second / name).read_bytes(), name,
            )

    def test_a_recorded_campaign_root_is_append_only(self):
        self.run_campaign("first")
        code, payload, _ = self.run_campaign("first")
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_ROOT_RECORDED, payload["reason"])

    # --- gates 3-5: live-provider refusals ---

    def test_live_provider_without_execute_refuses_and_builds_no_gateway(self):
        code, payload, root = self.run_campaign("live", "--provider", "azure_openai")
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_LIVE_REQUIRES_EXECUTE, payload["reason"])
        self.assertFalse(root.exists())

    def test_live_provider_without_config_or_pricing_refuses(self):
        code, payload, _ = self.run_campaign(
            "live", "--provider", "azure_openai", "--execute",
        )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_LIVE_REQUIRES_ARTIFACTS, payload["reason"])

    def test_provider_and_live_configuration_mismatch_refuses(self):
        _, _, live_path, pricing_path = live_pair(self.root)
        code, payload, _ = self.run_campaign(
            "live", "--provider", "openai", "--execute",
            "--live-config", str(live_path), "--pricing-snapshot", str(pricing_path),
        )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_PROVIDER_MISMATCH, payload["reason"])
        self.assertEqual("openai", payload["requested"])
        self.assertEqual("azure_openai", payload["configured"])

    def test_live_provider_without_the_exact_acknowledgement_refuses(self):
        _, _, live_path, pricing_path = live_pair(self.root)
        code, payload, _ = self.run_campaign(
            "live", "--provider", "azure_openai", "--execute",
            "--live-config", str(live_path), "--pricing-snapshot", str(pricing_path),
        )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_NOT_ACKNOWLEDGED, payload["reason"])

    def test_live_budget_above_the_campaign_cap_refuses(self):
        _, _, live_path, pricing_path = live_pair(self.root, attempts=4)
        config = write_config(self.root / "tight", max_model_calls=2, max_actions=2)
        with no_effects():
            code, payload = invoke(
                "run", str(self.root / "tight-run"), CAMPAIGN_ID,
                "--config", str(config), "--recorded-at", RUN_INSTANT,
                "--novelty-recheck", str(self.recheck),
                "--provider", "azure_openai", "--execute",
                "--live-config", str(live_path),
                "--pricing-snapshot", str(pricing_path),
                "--activation-acknowledgement", LIVE_PROBE_ACKNOWLEDGEMENT,
            )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_BUDGET_EXCEEDS_CAP, payload["reason"])
        self.assertEqual(["max_attempts"], payload["exceeded_bounds"])

    # --- gate 6: run_program fails closed and names its gate ---

    def test_run_program_fails_closed_citing_the_pending_sandbox_gate(self):
        code, payload, root = self.run_campaign(
            "program", "--fixture-script", "program-sandbox-refusal",
        )
        self.assertEqual(0, code, payload)
        facts = payload["facts"]
        self.assertEqual(
            ["derive", "write_program", "run_program", "report"], facts["action_types"],
        )
        self.assertEqual({
            "status": "pending_gate",
            "blocking_decision": SANDBOX_GATE_DECISION,
            "reason": SANDBOX_REFUSAL_REASON,
            "programs_recorded": 1,
            "programs_executed": 0,
            "execution_refusals_recorded": 1,
        }, facts["experiment_sandbox"])
        self.assertEqual("ADR-0066", SANDBOX_GATE_DECISION)
        export = verify_campaign_export((root / "campaign.json").read_bytes())
        run = next(
            item for item in export.tool_runs
            if item.adapter_id == campaign_cli.SANDBOX_ADAPTER_ID
        )
        self.assertEqual("failed", run.status.value)
        self.assertEqual("unavailable", run.measurement_source.value)
        result = json.loads(
            (root / "artifacts" / ("sha256-" + run.result_hash[len("sha256:"):]))
            .read_text(encoding="utf-8")
        )
        self.assertEqual(SANDBOX_REFUSAL_REASON, result["reason"])
        self.assertEqual(SANDBOX_GATE_DECISION, result["blocking_decision"])
        self.assertFalse(result["executed"])
        self.assertFalse(result["subprocess_opened"])
        self.assertFalse(result["epistemic_warrant_created"])

    # --- gate 7: the isolated verifier is recorded as absent ---

    def test_verify_records_the_absent_isolated_verifier(self):
        _, payload, root = self.run_campaign("verified")
        self.assertEqual({
            "status": "absent",
            "reason": VERIFIER_ABSENT_REASON,
            "verifications_completed": 0,
            "verification_refusals_recorded": 1,
        }, payload["facts"]["isolated_verifier"])
        export = verify_campaign_export((root / "campaign.json").read_bytes())
        verify_action = next(
            item for item in export.actions if item.action_type.value == "verify"
        )
        self.assertEqual("failed", verify_action.status.value)

    # --- gate 8: ADR-0055 binds before research starts ---

    def test_run_without_a_novelty_recheck_refuses(self):
        with no_effects():
            code, payload = invoke(
                "run", str(self.root / "unbound"), CAMPAIGN_ID,
                "--config", str(self.config), "--recorded-at", RUN_INSTANT,
            )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_NOVELTY_ABSENT, payload["reason"])

    def test_recheck_bound_to_another_action_is_refused(self):
        other = write_novelty(self.root, self.target, next_action_id="campaign.other.v1")
        with no_effects():
            code, payload = invoke(
                "run", str(self.root / "misbound"), CAMPAIGN_ID,
                "--config", str(self.config), "--recorded-at", RUN_INSTANT,
                "--novelty-recheck", str(other),
            )
        self.assertEqual(2, code)
        self.assertEqual("recheck_bound_to_different_action", payload["reason"])

    def test_a_stale_recheck_is_refused_at_research_start(self):
        with no_effects():
            code, payload = invoke(
                "run", str(self.root / "stale"), CAMPAIGN_ID,
                "--config", str(self.config),
                "--recorded-at", "2026-08-24T00:00:00Z",
                "--novelty-recheck", str(self.recheck),
            )
        self.assertEqual(2, code)
        self.assertEqual("recheck_too_old_for_action", payload["reason"])

    # --- gate 9: configuration bounds fail closed ---

    def test_a_bound_above_its_ceiling_is_refused_rather_than_clamped(self):
        code, payload = invoke(
            "config-create", str(self.root / "over.json"),
            "--campaign-configuration-id", "config.over.v1",
            "--allowed-tool", "exact_python",
            *[
                argument
                for name, value in sorted({
                    **BOUNDS, "max_actions": MAX_ACTIONS_CEILING + 1,
                }.items())
                for argument in ("--" + name.replace("_", "-"), str(value))
            ],
        )
        self.assertEqual(2, code)
        self.assertIn("exceeds the hard ceiling", payload["reason"])
        self.assertFalse((self.root / "over.json").exists())

    def test_a_single_action_bound_leaves_no_research_action(self):
        code, payload = invoke(
            "config-create", str(self.root / "tiny.json"),
            "--campaign-configuration-id", "config.tiny.v1",
            "--allowed-tool", "exact_python",
            *[
                argument
                for name, value in sorted({
                    **BOUNDS, "max_actions": 1, "max_model_calls": 1,
                }.items())
                for argument in ("--" + name.replace("_", "-"), str(value))
            ],
        )
        self.assertEqual(2, code)
        self.assertIn("max_actions must be at least two", payload["reason"])

    def test_duplicate_and_unknown_configuration_fields_are_refused(self):
        original = json.loads(self.config.read_text(encoding="utf-8"))
        unknown = self.root / "unknown.json"
        unknown.write_text(
            json.dumps({**original, "host_path": "/tmp"}), encoding="utf-8",
        )
        duplicated = self.root / "duplicated.json"
        text = self.config.read_text(encoding="utf-8")
        duplicated.write_text(
            text.replace('"max_actions":8', '"max_actions":8,"max_actions":9', 1),
            encoding="utf-8",
        )
        for path, expected in (
            (unknown, "fields differ from the closed schema"),
            (duplicated, "duplicate campaign configuration field: max_actions"),
        ):
            with no_effects():
                code, payload = invoke(
                    "run", str(self.root / f"cfg-{path.stem}"), CAMPAIGN_ID,
                    "--config", str(path), "--recorded-at", RUN_INSTANT,
                    "--novelty-recheck", str(self.recheck),
                )
            self.assertEqual(2, code, payload)
            self.assertIn(expected, payload["reason"])

    # --- gate 10: replay is model-free and tool-free ---

    def test_replay_verifies_with_zero_provider_network_subprocess_or_tool_calls(self):
        _, _, root = self.run_campaign("replayed")
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(0, code, payload)
        self.assertTrue(payload["verified"])
        self.assertEqual(0, payload["model_calls_made"])
        self.assertEqual(0, payload["provider_requests_made"])
        self.assertEqual(0, payload["tool_calls_made"])
        self.assertEqual(0, payload["subprocesses_opened"])
        self.assertEqual(0, payload["network_requests"])
        self.assertEqual(7, len(payload["checks"]))
        self.assertTrue(all(item["passed"] for item in payload["checks"]))
        self.assertLess(0, payload["artifacts_resolved"])

    def test_inspect_verifies_without_provider_network_or_subprocess_work(self):
        _, run_payload, root = self.run_campaign("inspected")
        with no_effects():
            code, payload = invoke("inspect", str(root))
        self.assertEqual(0, code, payload)
        self.assertEqual("verified", payload["status"])
        self.assertEqual(run_payload["facts"]["content_hash"], payload["content_hash"])

    # --- gate 11: falsifiability probes on the ledger ---

    def _rewrite_campaign(self, root: Path, mutate) -> None:
        payload = json.loads((root / "campaign.json").read_text(encoding="utf-8"))
        mutate(payload)
        (root / "campaign.json").write_bytes(canonical_bytes(payload) + b"\n")

    def test_probe_mutated_ancestor_rationale_breaks_the_semantic_hash(self):
        _, _, root = self.run_campaign("probe-rationale")

        def mutate(payload):
            payload["actions"][0]["declared_rationale"] += " (edited)"

        self._rewrite_campaign(root, mutate)
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertIn("content_hash mismatch", payload["reason"])

    def test_probe_mutated_ancestor_recorded_at_breaks_the_operational_hash(self):
        _, _, root = self.run_campaign("probe-recorded-at")

        def mutate(payload):
            payload["actions"][0]["recorded_at"] = "2026-08-22T09:99:99Z"

        self._rewrite_campaign(root, mutate)
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertIn("operational_hash mismatch", payload["reason"])

    def test_probe_deleted_ancestor_breaks_replay_closure(self):
        _, _, root = self.run_campaign("probe-deleted")

        def mutate(payload):
            del payload["actions"][0]

        self._rewrite_campaign(root, mutate)
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertIn("sequence is not contiguous", payload["reason"])

    def test_probe_mutated_artifact_bytes_break_artifact_closure(self):
        _, _, root = self.run_campaign("probe-artifact")
        artifact = sorted((root / "artifacts").iterdir())[0]
        artifact.write_bytes(artifact.read_bytes() + b"x")
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertIn(REFUSAL_ARTIFACT_BYTES, payload["reason"])

    def test_probe_flipped_facts_guardrail_is_refused_by_inspect(self):
        _, _, root = self.run_campaign("probe-guardrail")
        facts = json.loads((root / "campaign-facts.json").read_text(encoding="utf-8"))
        facts["guardrails"]["epistemic_warrant_created"] = True
        (root / "campaign-facts.json").write_bytes(canonical_bytes(facts) + b"\n")
        with no_effects():
            code, payload = invoke("inspect", str(root))
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_FACTS_MISMATCH, payload["reason"])

    def test_probe_swapped_target_record_is_refused(self):
        _, _, root = self.run_campaign("probe-target")
        record = json.loads((root / "target.json").read_text(encoding="utf-8"))
        record["target_claim_id"] = "claim.substituted.v1"
        (root / "target.json").write_bytes(canonical_bytes(record) + b"\n")
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertIn(REFUSAL_TARGET_MISMATCH, payload["reason"])

    # --- gate 12: the export is what publication consumes ---

    def test_export_bytes_match_the_ledger_and_reverify(self):
        _, _, root = self.run_campaign("exported")
        output = self.root / "campaign-export.json"
        with no_effects():
            code, payload = invoke("export", str(root), str(output))
        self.assertEqual(0, code, payload)
        self.assertEqual(
            (root / "campaign.json").read_bytes(), output.read_bytes(),
        )
        # This is exactly the value `publication build --campaign-export` reads.
        export = verify_campaign_export(output.read_bytes())
        self.assertEqual(payload["content_hash"], export.content_hash)
        self.assertEqual(payload["operational_hash"], export.operational_hash)

    # --- gate 13: nothing is promoted on any path ---

    def test_no_fixture_path_creates_a_warrant_or_an_assessment(self):
        for script in campaign_cli.FIXTURE_SCRIPTS:
            code, payload, _ = self.run_campaign(
                f"guard-{script}", "--fixture-script", script,
            )
            self.assertEqual(0, code, payload)
            self.assertFalse(payload["epistemic_warrant_created"])
            for name, value in payload["facts"]["guardrails"].items():
                self.assertIn(value, (False, 0), name)
            # The derived prior-art classification is the only novelty-adjacent
            # field, and an inconclusive search cannot become a novelty claim.
            self.assertEqual(
                "prior_art_search_inconclusive",
                payload["facts"]["novelty_recheck"]["report_classification"],
            )
            self.assertEqual(
                "unresolved",
                payload["facts"]["novelty_recheck"]["target_resolution_status"],
            )


class CampaignActivationTests(unittest.TestCase):
    """ADR-0057 §3: one no-retry activation, retained pass or fail, no fallback."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        with no_effects():
            self.config = write_config(self.root)
            _, self.target = write_target(self.root)
            self.recheck = write_novelty(self.root, self.target)
        self.live, self.pricing, self.live_path, self.pricing_path = live_pair(self.root)

    def _run_live(self, name: str, activation: LiveProviderProbeResult):
        gateways: list[tuple[str, str]] = []

        def build(provider: str, model_identifier: str, **_kwargs):
            gateways.append((provider, model_identifier))
            return object()

        root = self.root / name
        with (
            mock.patch.object(socket, "socket", _forbidden("a socket call")),
            mock.patch.object(subprocess, "Popen", _forbidden("a subprocess spawn")),
            mock.patch.object(campaign_cli, "build_gateway", build),
            mock.patch.object(
                campaign_cli, "static_provider_preflight",
                lambda *_a, **_k: passed_static(self.live, self.pricing),
            ),
            mock.patch.object(
                campaign_cli, "run_live_provider_probe", lambda *_a, **_k: activation,
            ),
        ):
            code, payload = invoke(
                "run", str(root), CAMPAIGN_ID,
                "--config", str(self.config), "--recorded-at", RUN_INSTANT,
                "--novelty-recheck", str(self.recheck),
                "--provider", "azure_openai", "--execute",
                "--live-config", str(self.live_path),
                "--pricing-snapshot", str(self.pricing_path),
                "--activation-acknowledgement", LIVE_PROBE_ACKNOWLEDGEMENT,
            )
        return code, payload, root, gateways

    def test_failed_activation_is_terminal_recorded_and_never_a_decline(self):
        code, payload, root, gateways = self._run_live(
            "failed", failed_activation(self.live, self.pricing, executed=True),
        )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_ACTIVATION_FAILED, payload["reason"])
        self.assertEqual(REFUSAL_ACTIVATION_FAILED, payload["terminal_reason"])
        self.assertFalse(payload["fallback_gateway_used"])
        # Exactly one gateway is built: there is no fallback provider.
        self.assertEqual([("azure_openai", "gpt-5.6-sol")], gateways)
        self.assertNotIn("proposer_declined", json.dumps(payload))
        self.assertNotEqual("completed", payload["facts"]["terminal_action_status"])
        facts = payload["facts"]
        self.assertEqual(["plan"], facts["action_types"])
        self.assertEqual("failed", facts["terminal_action_status"])
        # A 401 is one attempted request and zero completed responses.
        self.assertEqual(1, facts["usage"]["requests_attempted"])
        self.assertEqual(0, facts["usage"]["responses_completed"])
        self.assertEqual(1, facts["usage"]["responses_failed"])
        self.assertEqual(0, facts["usage"]["usage_reported_calls"])
        # The activation is retained even though it failed.
        export = verify_campaign_export((root / "campaign.json").read_bytes())
        self.assertEqual(("call.activation",), tuple(
            item.call_id for item in export.model_calls
        ))
        self.assertEqual("failed", export.model_calls[0].status.value)
        self.assertTrue((root / "activation.json").exists())

    def test_unexecuted_activation_records_zero_attempted_requests(self):
        code, payload, root, gateways = self._run_live(
            "not-executed", failed_activation(self.live, self.pricing, executed=False),
        )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_ACTIVATION_NOT_EXECUTED, payload["reason"])
        self.assertEqual(0, payload["requests_attempted"])
        self.assertEqual([("azure_openai", "gpt-5.6-sol")], gateways)
        self.assertTrue((root / "activation.json").exists())
        self.assertFalse((root / "campaign.json").exists())


if __name__ == "__main__":
    unittest.main()
