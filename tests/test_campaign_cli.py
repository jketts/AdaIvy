"""Offline acceptance tests for the ADR-0065 campaign operator entrypoint.

Every assertion here encodes an ADR-0065 acceptance gate. "Made no process,
socket or provider call" is measured by a CPython audit hook over the real
interpreter events, following ADR-0066's acceptance suite, plus a patched
gateway builder that raises. The mock net this replaces asserted the property
against patched module attributes and could be escaped four ways -- `os.system`,
`os.posix_spawn`, `os.exec*`, and any module holding a pre-bound `socket.socket`
reference -- so the measurement, not the behaviour, was the defect.

Each boundary carries a named falsifiability probe: a boundary that cannot be
made to fail proves nothing. `test_probe_replay_effect_counters_move_when_replay_
does_work` is the probe for the effect counters themselves.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from math_research import campaign_cli
from math_research.campaign.records import canonical_bytes, canonical_hash
from math_research.campaign.replay import verify_campaign_export
from math_research.campaign_cli import (
    _CONFIG_BOUNDS,
    MAX_ACTIONS_CEILING,
    MAX_ALLOWED_TOOLS_CEILING,
    MAX_TOOL_RUNS_CEILING,
    REFUSAL_ACTION_REJECTED,
    REFUSAL_ACTION_SCHEMA_UNREADABLE,
    REFUSAL_ACTIVATION_FAILED,
    REFUSAL_ACTIVATION_NOT_EXECUTED,
    REFUSAL_ACTIVATION_RETAINED,
    REFUSAL_ARTIFACT_BYTES,
    REFUSAL_ARTIFACT_LOG,
    REFUSAL_ARTIFACT_UNRECORDED,
    REFUSAL_BOUND_VIOLATION,
    REFUSAL_BUDGET_EXCEEDS_CAP,
    REFUSAL_CONFIG_REJECTED,
    REFUSAL_DURABLE_IO,
    REFUSAL_DURABLE_REWRITE,
    REFUSAL_FACTS_MISMATCH,
    REFUSAL_FIXTURE_WITH_LIVE_FLAGS,
    REFUSAL_LEDGER_INVALID,
    REFUSAL_LIVE_REQUIRES_ARTIFACTS,
    REFUSAL_LIVE_REQUIRES_EXECUTE,
    REFUSAL_NOT_ACKNOWLEDGED,
    REFUSAL_NOVELTY_ABSENT,
    REFUSAL_PLANNER_NOT_CONSTRUCTED,
    REFUSAL_PROVIDER_MISMATCH,
    REFUSAL_REPLAY_PERFORMED_WORK,
    REFUSAL_ROOT_RECORDED,
    REFUSAL_RUNNER_REJECTED,
    REFUSAL_TARGET_MISMATCH,
    SANDBOX_GATE_DECISION,
    SANDBOX_REFUSAL_REASON,
    VERIFIER_ABSENT_REASON,
)
from math_research.campaign.records import CampaignProvenanceError, RecordStatus, UsageSource
from math_research.campaign.runner import CampaignRunnerError, PlannerResponse
from math_research.domain.entities import OpaqueId
from math_research.novelty import NoveltyRecheck, write_recheck
from math_research.phase2.live_config import (
    create_live_run_configuration,
    write_live_run_configuration,
)
from math_research.phase2.pricing import create_pricing_snapshot, write_pricing_snapshot
from math_research.phase2.records import BudgetLimits
from math_research.publication.bundle import verify_bundle
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


#: CPython's own audit-event names. `socket.socket` is NOT an audit event, so a
#: watcher that lists it observes nothing; `socket.__new__` is the real name.
#: This set is defined here independently of the module under test, so the test
#: measures the behaviour rather than trusting the module's own accounting.
_WATCHED_EVENTS = frozenset({
    "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn",
    "os.fork", "os.forkpty", "os.fork_exec", "pty.spawn",
    "socket.__new__", "socket.connect", "socket.bind", "socket.sendto",
    "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
    "urllib.Request", "ftplib.connect", "http.client.connect",
    "smtplib.connect", "imaplib.open", "poplib.connect",
})
_OBSERVED: list[str] = []
_WATCHING = False


def _observe(event: str, _arguments: object) -> None:
    if _WATCHING and event in _WATCHED_EVENTS:
        _OBSERVED.append(event)


sys.addaudithook(_observe)


@contextlib.contextmanager
def observe_effects():
    """Record the real interpreter process and socket events of the block."""

    global _WATCHING
    _OBSERVED.clear()
    _WATCHING = True
    try:
        yield _OBSERVED
    finally:
        _WATCHING = False


@contextlib.contextmanager
def no_effects():
    """Fail loudly if an offline path starts a process, opens a socket, or
    builds a gateway.

    The process/socket half is a CPython audit hook rather than a set of patched
    module attributes, because a mock is escapable: `os.system`, `os.posix_spawn`,
    `os.exec*` and any pre-bound `socket.socket` reference all bypass one, and an
    audit hook observes the interpreter event instead of a name lookup.
    """

    with observe_effects() as observed:
        with (
            mock.patch.object(
                campaign_cli, "build_gateway", _forbidden("a gateway build"),
            ),
            mock.patch.object(
                campaign_cli, "run_live_provider_probe",
                _forbidden("an activation probe"),
            ),
        ):
            yield observed
    if observed:
        raise AssertionError(
            f"offline campaign path performed: {sorted(set(observed))}"
        )


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
        # The honest property: zero PROVIDER requests, zero sockets and zero
        # processes -- not zero planner calls. The ledger records four scripted
        # planner calls and says so, and these counters are measured, which is
        # why three of the five are nonzero here.
        self.assertEqual(0, payload["effects"]["provider_requests_made"])
        self.assertEqual(0, payload["effects"]["subprocesses_opened"])
        self.assertEqual(0, payload["effects"]["network_requests"])
        self.assertEqual(4, payload["effects"]["model_calls_made"])
        self.assertEqual(1, payload["effects"]["tool_calls_made"])
        self.assertEqual(4, facts["usage"]["requests_attempted"])
        self.assertEqual(4, facts["usage"]["responses_completed"])
        self.assertTrue(payload["effect_measurement"]["audit_hook_installed"])
        self.assertEqual("within_bounds", facts["bound_compliance"]["status"])
        export = verify_campaign_export((root / "campaign.json").read_bytes())
        self.assertEqual(facts["content_hash"], export.content_hash)
        self.assertEqual(facts["operational_hash"], export.operational_hash)
        self.assertNotEqual(export.content_hash, export.operational_hash)

    def test_terminal_campaign_automatically_writes_an_unapproved_latex_draft(self):
        code, payload, root = self.run_campaign("automatic-publication-draft")
        self.assertEqual(0, code, payload)
        report = payload["publication_draft"]
        self.assertEqual("written", report["status"])
        self.assertEqual("not_typeset", report["typeset_status"])
        self.assertIsNone(report["publication_approval"])
        self.assertFalse(report["epistemic_warrant_created"])
        bundle = root / "publication-draft"
        self.assertTrue((bundle / "paper.tex").is_file())
        self.assertFalse((bundle / "paper.pdf").exists())
        manifest = verify_bundle(bundle)
        self.assertEqual(report["bundle_hash"], manifest["bundle_hash"])
        manuscript = json.loads(
            (bundle / "records/manuscript.json").read_text(encoding="utf-8")
        )
        self.assertEqual([], manuscript["claims"])
        self.assertIsNone(manuscript["publication_approval"])

    def test_resume_only_verifies_terminal_state_and_finishes_missing_report(self):
        _, first, root = self.run_campaign("terminal-resume")
        campaign_before = (root / "campaign.json").read_bytes()
        report_before = (root / "publication-draft/MANIFEST.json").read_bytes()
        with no_effects():
            code, resumed = invoke("resume", str(root))
        self.assertEqual(0, code, resumed)
        self.assertEqual("terminal_finalization_only", resumed["resume_scope"])
        self.assertFalse(resumed["paid_work_repeated"])
        self.assertEqual("verified_existing", resumed["publication_draft"]["status"])
        self.assertEqual(first["facts"]["content_hash"], resumed["campaign_content_hash"])
        self.assertEqual(campaign_before, (root / "campaign.json").read_bytes())
        self.assertEqual(report_before, (root / "publication-draft/MANIFEST.json").read_bytes())
        self.assertEqual(0, resumed["effects"]["provider_requests_made"])
        self.assertEqual(0, resumed["effects"]["network_requests"])
        self.assertEqual(0, resumed["effects"]["subprocesses_opened"])

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
            ["derive", "write_program", "run_program"], facts["action_types"],
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

    def test_every_bound_above_its_ceiling_is_refused(self):
        """ADR-0065 §1 claims each bound is checked against a hard ceiling.

        Only `max_actions` was ever asserted. The mechanism is table-driven, so
        the claim was probably true; "probably true" is not an acceptance gate.
        """

        self.assertEqual(14, len(_CONFIG_BOUNDS))
        for name, ceiling in _CONFIG_BOUNDS:
            with self.subTest(bound=name):
                code, payload = invoke(
                    "config-create", str(self.root / f"over-{name}.json"),
                    "--campaign-configuration-id", "config.over.v1",
                    "--allowed-tool", "exact_python",
                    *[
                        argument
                        for bound, value in sorted({
                            **BOUNDS, name: ceiling + 1,
                        }.items())
                        for argument in ("--" + bound.replace("_", "-"), str(value))
                    ],
                )
                self.assertEqual(2, code, payload)
                self.assertEqual(
                    f"{name} of {ceiling + 1} exceeds the hard ceiling of {ceiling}",
                    payload["reason"],
                )
                self.assertFalse((self.root / f"over-{name}.json").exists())

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
        self.assertEqual(10, len(payload["checks"]))
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


def incomplete_activation(configuration, pricing) -> LiveProviderProbeResult:
    """A timed-out activation: one attempted request, one INCOMPLETE response.

    ADR-0057 §3 keeps `responses_failed` and `responses_incomplete` distinct.
    """

    return LiveProviderProbeResult(
        probe_status="failed", provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        configuration_hash=configuration.content_hash,
        pricing_snapshot_hash=pricing.content_hash,
        route_hash=canonical_hash({"route": "stubbed-for-offline-test"}),
        probe_request_hash=canonical_hash({"probe": "request"}),
        observed_at=RUN_INSTANT, acknowledgement_confirmed=True,
        static_preflight_status="passed", endpoint_reachability="reached",
        authentication_status="indeterminate",
        deployment_route_status="indeterminate",
        provider_identity_status="indeterminate",
        structured_output_capability="indeterminate",
        operational_readiness="failed", failure_classification="timeout",
        sanitized_failure=None,
        requests_attempted=1, responses_completed=0, responses_succeeded=0,
        responses_failed=0, responses_incomplete=1,
        usage_reported_calls=0, input_tokens=0, output_tokens=0,
        estimated_cost_microusd=0, provider_request_id=None,
    )


def passed_activation(configuration, pricing) -> LiveProviderProbeResult:
    """A fully passing activation: one attempted request, one succeeded."""

    return LiveProviderProbeResult(
        probe_status="passed", provider=configuration.provider,
        model_identifier=configuration.model_identifier,
        configuration_hash=configuration.content_hash,
        pricing_snapshot_hash=pricing.content_hash,
        route_hash=canonical_hash({"route": "stubbed-for-offline-test"}),
        probe_request_hash=canonical_hash({"probe": "request"}),
        observed_at=RUN_INSTANT, acknowledgement_confirmed=True,
        static_preflight_status="passed", endpoint_reachability="reached",
        authentication_status="accepted", deployment_route_status="resolved",
        provider_identity_status="confirmed",
        structured_output_capability="confirmed",
        operational_readiness="passed", failure_classification=None,
        sanitized_failure=None,
        requests_attempted=1, responses_completed=1, responses_succeeded=1,
        responses_failed=0, responses_incomplete=0,
        usage_reported_calls=1, input_tokens=40, output_tokens=12,
        estimated_cost_microusd=640, provider_request_id="request.activation.v1",
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

    def _run_live(self, name: str, activation: LiveProviderProbeResult, *extra: str):
        gateways: list[tuple[str, str]] = []

        def build(provider: str, model_identifier: str, **_kwargs):
            gateways.append((provider, model_identifier))
            return object()

        root = self.root / name
        with (
            observe_effects() as observed,
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
                *extra,
            )
        # The gateway and the probe are stubbed, so a real process or socket
        # event here would mean the entrypoint did something else as well.
        if observed:
            raise AssertionError(f"live campaign harness performed: {observed}")
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

    # --- C5: an incomplete activation is not a failed one ------------------

    def test_an_incomplete_activation_is_not_recorded_as_failed(self):
        """ADR-0057 §3 counters are distinct; the status was hardcoded `failed`.

        The truth survived in `activation.json` either way, so a gate that reads
        only the artifact cannot see this. `campaign.json` and
        `campaign-facts.json` are what a reader and `publication` consume.
        """

        code, payload, root, _ = self._run_live(
            "incomplete", incomplete_activation(self.live, self.pricing),
        )
        self.assertEqual(2, code)
        usage = payload["facts"]["usage"]
        self.assertEqual(1, usage["requests_attempted"])
        self.assertEqual(1, usage["responses_incomplete"])
        self.assertEqual(0, usage["responses_failed"])
        self.assertEqual(0, usage["responses_completed"])
        export = verify_campaign_export((root / "campaign.json").read_bytes())
        self.assertEqual(
            RecordStatus.INCOMPLETE, export.model_calls[0].status,
        )
        # The action is still failed: no research action was ever admitted.
        self.assertEqual(RecordStatus.FAILED, export.actions[0].status)

    def test_a_failed_activation_is_still_recorded_as_failed(self):
        code, payload, _, _ = self._run_live(
            "failed-status", failed_activation(self.live, self.pricing, executed=True),
        )
        self.assertEqual(2, code)
        usage = payload["facts"]["usage"]
        self.assertEqual(1, usage["responses_failed"])
        self.assertEqual(0, usage["responses_incomplete"])

    # --- C1: a paid request is never dropped outside every ledger ----------

    def test_an_unreadable_action_schema_refuses_before_any_gateway(self):
        """`--action-schema` defaults to a RELATIVE path.

        Reading it during planner construction meant that running `campaign run`
        from any directory but the repository root fired the one paid probe and
        then failed on an inert local file.
        """

        code, payload, root, gateways = self._run_live(
            "schema-missing", passed_activation(self.live, self.pricing),
            "--action-schema", str(self.root / "no-such-schema.json"),
        )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_ACTION_SCHEMA_UNREADABLE, payload["reason"])
        # No gateway, therefore no request, therefore nothing to retain.
        self.assertEqual([], gateways)
        self.assertFalse(root.exists())

    def test_a_passed_activation_is_retained_when_the_campaign_never_starts(self):
        """The retention branch used to be guarded by `probe_status != passed`.

        A passing probe followed by any downstream failure therefore persisted no
        `campaign.json`, no `ModelCallRecord` and no `ActionRecord`: one real
        billable request, zero records.
        """

        activation = passed_activation(self.live, self.pricing)
        with mock.patch(
            "math_research.campaign.planner.GatewayCampaignPlanner",
            side_effect=CampaignRunnerError("planner refused after the paid probe"),
        ):
            code, payload, root, gateways = self._run_live("retained", activation)
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_PLANNER_NOT_CONSTRUCTED, payload["reason"])
        self.assertEqual(REFUSAL_ACTIVATION_RETAINED, payload["terminal_reason"])
        self.assertEqual([("azure_openai", "gpt-5.6-sol")], gateways)
        self.assertTrue((root / "activation.json").exists())
        # The one paid request is in the ledger, not only on stdout.
        export = verify_campaign_export((root / "campaign.json").read_bytes())
        self.assertEqual(
            ("call.activation",), tuple(item.call_id for item in export.model_calls),
        )
        self.assertEqual(RecordStatus.COMPLETED, export.model_calls[0].status)
        self.assertEqual(UsageSource.API_REPORTED, export.model_calls[0].usage_source)
        self.assertEqual(RecordStatus.FAILED, export.actions[0].status)
        usage = payload["facts"]["usage"]
        self.assertEqual(1, usage["requests_attempted"])
        self.assertEqual(1, usage["responses_completed"])
        self.assertEqual(1, usage["usage_reported_calls"])
        self.assertEqual(640, usage["estimated_cost_microusd"])
        self.assertNotIn("proposer_declined", json.dumps(payload))
        # It is not `provider_activation_failed`: the probe passed.
        self.assertNotEqual(REFUSAL_ACTIVATION_FAILED, payload["terminal_reason"])


#: The real scripted planner, captured before any test patches the module
#: attribute, so a wrapper can delegate to it without recursing.
_REAL_SCRIPTED_PLANNER = campaign_cli.ScriptedCampaignPlanner


class _UsageBearingPlanner:
    """A scripted planner that reports provider usage.

    It exists to drive a campaign past its own caps without touching a bound:
    `BOUNDS` is unchanged and these usage numbers are the test double's, not a
    retuned ceiling.
    """

    def __init__(self, **kwargs: object) -> None:
        self._inner = _REAL_SCRIPTED_PLANNER(**kwargs)  # type: ignore[arg-type]

    def __call__(self, context):
        response = self._inner(context)
        return PlannerResponse(
            action_json=response.action_json,
            provider=response.provider,
            model_identifier=response.model_identifier,
            status=response.status,
            usage_source=UsageSource.API_REPORTED,
            input_tokens=10_000,
            output_tokens=10_000,
            estimated_cost_microusd=900_000,
            provider_request_id=None,
        )


class _RaisingPlanner:
    """A planner that rejects before returning anything to retain."""

    def __init__(self, **_kwargs: object) -> None:
        pass

    def __call__(self, _context):
        raise CampaignRunnerError("scripted planner refused to plan")


class CampaignRepairedDefectTests(unittest.TestCase):
    """The findings of the ADR-0065 adversarial audit, as executable gates."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        with no_effects():
            self.config = write_config(self.root)
            self.target_path, self.target = write_target(self.root)
            self.recheck = write_novelty(self.root, self.target)

    def run_campaign(self, name: str, *extra: str, config: Path | None = None):
        root = self.root / name
        with no_effects():
            code, payload = invoke(
                "run", str(root), CAMPAIGN_ID,
                "--config", str(config or self.config),
                "--recorded-at", RUN_INSTANT,
                "--novelty-recheck", str(self.recheck),
                *extra,
            )
        return code, payload, root

    # --- C7: `--provider fixture` may not silently discard live flags ------

    def test_fixture_provider_refuses_live_activation_flags(self):
        """The label stayed honest, but an operator who asked for a live run got
        a green scripted one, which is the substitution this ADR exists to stop.
        """

        code, payload, root = self.run_campaign(
            "fixture-live", "--execute",
            "--live-config", str(self.root / "nonexistent-live.json"),
            "--pricing-snapshot", str(self.root / "nonexistent-pricing.json"),
            "--activation-acknowledgement", "WRONG STRING",
        )
        self.assertEqual(2, code, payload)
        self.assertEqual(REFUSAL_FIXTURE_WITH_LIVE_FLAGS, payload["reason"])
        self.assertEqual([
            "--activation-acknowledgement", "--execute", "--live-config",
            "--pricing-snapshot",
        ], payload["live_arguments"])
        self.assertFalse(root.exists())

    def test_the_fixture_default_still_needs_no_live_flag(self):
        code, payload, _ = self.run_campaign("fixture-clean")
        self.assertEqual(0, code, payload)
        self.assertEqual("fixture", payload["provider"])

    # --- C2: a bound violation is durable and blocks the export -----------

    def _over_budget(self, name: str):
        root = self.root / name
        with no_effects(), mock.patch.object(
            campaign_cli, "ScriptedCampaignPlanner", _UsageBearingPlanner,
        ):
            code, payload = invoke(
                "run", str(root), CAMPAIGN_ID,
                "--config", str(self.config), "--recorded-at", RUN_INSTANT,
                "--novelty-recheck", str(self.recheck),
            )
        return code, payload, root

    def test_a_bound_violation_is_recorded_in_durable_output(self):
        code, payload, root = self._over_budget("over-budget")
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_BOUND_VIOLATION, payload["reason"])
        self.assertEqual(
            ["max_cost_microusd", "max_input_tokens", "max_output_tokens"],
            payload["exceeded_bounds"],
        )
        # The violation is in the file, not only on stdout.
        stored = json.loads((root / "campaign-facts.json").read_text(encoding="utf-8"))
        compliance = stored["bound_compliance"]
        self.assertEqual("exceeded", compliance["status"])
        self.assertEqual(
            ["max_cost_microusd", "max_input_tokens", "max_output_tokens"],
            compliance["exceeded_bounds"],
        )
        self.assertEqual(40_000, compliance["observed"]["max_input_tokens"])
        self.assertEqual(20_000, compliance["configured"]["max_input_tokens"])

    def test_an_over_budget_campaign_cannot_inspect_replay_or_export_as_clean(self):
        _, _, root = self._over_budget("over-budget-export")
        output = self.root / "over-budget-export.json"
        with no_effects():
            inspect_code, inspect_payload = invoke("inspect", str(root))
            replay_code, replay_payload = invoke("replay", str(root))
            export_code, export_payload = invoke("export", str(root), str(output))
        self.assertEqual(2, inspect_code)
        self.assertEqual(REFUSAL_BOUND_VIOLATION, inspect_payload["reason"])
        self.assertEqual(2, replay_code)
        self.assertFalse(replay_payload["verified"])
        self.assertEqual(REFUSAL_BOUND_VIOLATION, replay_payload["reason"])
        self.assertIn(
            {"name": "recorded_usage_is_within_configured_bounds", "passed": False},
            replay_payload["checks"],
        )
        self.assertEqual(2, export_code)
        self.assertEqual(REFUSAL_BOUND_VIOLATION, export_payload["reason"])
        # Nothing was written for `publication build --campaign-export` to read.
        self.assertFalse(output.exists())

    def test_a_within_bounds_campaign_still_exports(self):
        _, _, root = self.run_campaign("in-budget")
        output = self.root / "in-budget-export.json"
        with no_effects():
            code, payload = invoke("export", str(root), str(output))
        self.assertEqual(0, code, payload)
        self.assertEqual((root / "campaign.json").read_bytes(), output.read_bytes())

    # --- C4: a rejected action retains its partial ledger ------------------

    def _rejected_run(self, name: str):
        config = write_config(self.root / f"{name}-cfg", max_program_bytes=1)
        return self.run_campaign(
            name, "--fixture-script", "program-sandbox-refusal", config=config,
        )

    def test_a_rejected_action_retains_the_partial_ledger(self):
        """`SequentialCampaignRunner` used to raise and discard the ledger while
        `FileArtifactStore.put` had already written the bytes, so a discarded run
        left model-authored Python source on disk with no record at all.
        """

        code, payload, root = self._rejected_run("rejected")
        self.assertEqual(2, code, payload)
        self.assertEqual(REFUSAL_ACTION_REJECTED, payload["reason"])
        self.assertEqual("action_rejected", payload["terminal_reason"])
        facts = payload["facts"]
        self.assertEqual(["derive", "plan"], facts["action_types"])
        self.assertEqual("failed", facts["terminal_action_status"])
        self.assertTrue((root / "campaign.json").exists())
        export = verify_campaign_export((root / "campaign.json").read_bytes())
        # The refused program bytes are named by the terminal action.
        program_hash = campaign_cli._raw_hash(
            campaign_cli.FIXTURE_PROGRAM_SOURCE.encode("utf-8"),
        )
        self.assertIn(program_hash, export.actions[-1].output_artifact_hashes)
        self.assertIn("program exceeds campaign byte bound",
                      export.actions[-1].declared_rationale)
        self.assertEqual(("call.2",), export.actions[-1].source_record_ids)
        # Nothing on disk is orphaned any more.
        with no_effects():
            replay_code, replay_payload = invoke("replay", str(root))
        self.assertEqual(0, replay_code, replay_payload)
        self.assertTrue(replay_payload["verified"])
        self.assertEqual(2, replay_payload["artifacts_resolved"])

    def test_a_root_holding_a_partial_ledger_refuses_a_second_run(self):
        _, _, root = self._rejected_run("rejected-twice")
        code, payload, _ = self.run_campaign(
            "rejected-twice", "--fixture-script", "program-sandbox-refusal",
            config=write_config(self.root / "rejected-twice-cfg2", max_program_bytes=1),
        )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_ROOT_RECORDED, payload["reason"])

    def test_a_root_holding_only_artifacts_is_already_recorded(self):
        """The guard keyed on `campaign.json` alone, so a root holding a
        discarded run's artifacts admitted a second run on top of them.
        """

        root = self.root / "artifacts-only"
        (root / "artifacts").mkdir(parents=True)
        (root / "artifacts" / ("sha256-" + "0" * 64)).write_bytes(b"orphan")
        code, payload, _ = self.run_campaign("artifacts-only")
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_ROOT_RECORDED, payload["reason"])
        self.assertEqual(["artifacts/"], payload["recorded_files"])

    def test_an_unrecorded_artifact_file_breaks_replay(self):
        _, _, root = self.run_campaign("orphan")
        orphan = "sha256-" + campaign_cli._raw_hash(b"orphan")[len("sha256:"):]
        (root / "artifacts" / orphan).write_bytes(b"orphan")
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertIn(REFUSAL_ARTIFACT_UNRECORDED, payload["reason"])

    def test_a_misnamed_artifact_file_breaks_replay(self):
        """`_artifact_hashes` only checked that ledger-named hashes resolve, so a
        file whose NAME is a hash its own bytes do not produce was never read.
        """

        _, _, root = self.run_campaign("misnamed")
        (root / "artifacts" / ("sha256-" + "a" * 64)).write_bytes(b"not that hash")
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertIn(REFUSAL_ARTIFACT_BYTES, payload["reason"])

    def test_a_file_that_is_not_an_artifact_name_breaks_replay(self):
        _, _, root = self.run_campaign("badname")
        (root / "artifacts" / "notes.txt").write_bytes(b"hand written")
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertIn(REFUSAL_ARTIFACT_UNRECORDED, payload["reason"])

    def test_an_artifact_log_entry_outside_the_ledger_breaks_replay(self):
        _, _, root = self.run_campaign("log-drift")
        with (root / "artifact-log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "content_hash": campaign_cli._raw_hash(b"never recorded"),
                "media_type": "text/plain",
            }, sort_keys=True, separators=(",", ":")) + "\n")
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertIn(REFUSAL_ARTIFACT_LOG, payload["reason"])

    # --- C3: the replay effect counters are measured -----------------------

    def test_probe_replay_effect_counters_move_when_replay_does_work(self):
        """The falsifiability probe for the effect counters themselves.

        The five counters were literal zeroes compared against a literal zero
        tuple, so an audit that made `_replay` open a socket and start a process
        still reported `(0, 0, 0, 0, 0)` and still passed the gate.
        """

        _, _, root = self.run_campaign("effect-probe")
        real = campaign_cli._reconcile_artifact_log

        def working(root_path, expected):
            # A UDP socket sends nothing and this command does not exist, so the
            # exec fails -- but both interpreter events are real.
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM).close()
            with contextlib.suppress(OSError):
                subprocess.run(
                    ["adaivy-campaign-effect-probe-no-such-command"],
                    capture_output=True,
                )
            return real(root_path, expected)

        with mock.patch.object(campaign_cli, "_reconcile_artifact_log", working):
            code, payload = invoke("replay", str(root))
        self.assertEqual(2, code)
        self.assertFalse(payload["verified"])
        self.assertEqual(REFUSAL_REPLAY_PERFORMED_WORK, payload["reason"])
        self.assertLess(0, payload["network_requests"])
        self.assertLess(0, payload["subprocesses_opened"])

    def test_a_clean_replay_measures_zero_of_all_five_effects(self):
        _, _, root = self.run_campaign("clean-replay")
        with no_effects():
            code, payload = invoke("replay", str(root))
        self.assertEqual(0, code, payload)
        self.assertEqual(
            (0, 0, 0, 0, 0),
            (
                payload["model_calls_made"], payload["provider_requests_made"],
                payload["tool_calls_made"], payload["subprocesses_opened"],
                payload["network_requests"],
            ),
        )
        self.assertEqual(
            "sys.addaudithook", payload["effect_measurement"]["mechanism"],
        )
        self.assertTrue(payload["effect_measurement"]["audit_hook_installed"])
        self.assertIn(
            "socket.__new__", payload["effect_measurement"]["network_events_watched"],
        )
        self.assertIn(
            "os.system", payload["effect_measurement"]["process_events_watched"],
        )

    # --- C6: `campaign.json` is the last durable write ---------------------

    def test_campaign_json_is_written_last(self):
        written: list[str] = []
        files = [
            ("campaign.json", b"a"), ("target.json", b"b"),
            ("campaign-facts.json", b"c"), ("novelty-recheck.json", b"d"),
        ]
        with mock.patch.object(
            campaign_cli, "_write_once",
            lambda path, content: written.append(path.name),
        ):
            campaign_cli._write_durable(self.root / "order", files)
        self.assertEqual("campaign.json", written[-1])
        self.assertEqual(sorted(name for name, _ in files), sorted(written))

    def test_a_failed_facts_write_leaves_no_campaign_json(self):
        """Writing `campaign.json` first wedged the root permanently: the
        append-only guard keys on it, so the pair could never be repaired.
        """

        real = campaign_cli._write_once

        def failing(path: Path, content: bytes) -> None:
            if path.name == "campaign-facts.json":
                raise OSError("simulated durable write failure")
            real(path, content)

        root = self.root / "wedged"
        with no_effects(), mock.patch.object(
            campaign_cli, "_write_once", failing,
        ):
            code, payload = invoke(
                "run", str(root), CAMPAIGN_ID,
                "--config", str(self.config), "--recorded-at", RUN_INSTANT,
                "--novelty-recheck", str(self.recheck),
            )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_DURABLE_IO, payload["reason"])
        # Earlier durable files were written; `campaign.json` -- the file the
        # append-only guard keys on -- was not, because it goes last.
        self.assertTrue((root / "campaign-config.json").exists())
        self.assertFalse((root / "campaign.json").exists())

    # --- C9: `allowed_tools` is validated and capped -----------------------

    def test_allowed_tools_ceiling_is_derived_from_the_tool_run_ceiling(self):
        # No campaign can perform more tool runs than `MAX_TOOL_RUNS_CEILING`,
        # so a longer allowlist grants authority no campaign can exercise.
        self.assertEqual(MAX_TOOL_RUNS_CEILING, MAX_ALLOWED_TOOLS_CEILING)

    def test_a_path_traversal_tool_identifier_is_refused(self):
        code, payload = invoke(
            "config-create", str(self.root / "traversal.json"),
            "--campaign-configuration-id", "config.traversal.v1",
            "--allowed-tool", "../../etc/passwd",
            *[
                argument for name, value in sorted(BOUNDS.items())
                for argument in ("--" + name.replace("_", "-"), str(value))
            ],
        )
        self.assertEqual(2, code)
        self.assertIn("tool identifier rule", payload["reason"])
        self.assertFalse((self.root / "traversal.json").exists())

    def test_a_duplicate_tool_identifier_is_refused_not_deduplicated(self):
        code, payload = invoke(
            "config-create", str(self.root / "duplicate-tool.json"),
            "--campaign-configuration-id", "config.duplicate.v1",
            "--allowed-tool", "exact_python", "--allowed-tool", "exact_python",
            *[
                argument for name, value in sorted(BOUNDS.items())
                for argument in ("--" + name.replace("_", "-"), str(value))
            ],
        )
        self.assertEqual(2, code)
        self.assertIn("duplicate tool identifier", payload["reason"])

    def test_an_allowlist_above_the_ceiling_is_refused(self):
        tools = [f"tool_{index:05d}" for index in range(MAX_ALLOWED_TOOLS_CEILING + 1)]
        arguments: list[str] = []
        for tool in tools:
            arguments.extend(["--allowed-tool", tool])
        code, payload = invoke(
            "config-create", str(self.root / "many-tools.json"),
            "--campaign-configuration-id", "config.many.v1", *arguments,
            *[
                argument for name, value in sorted(BOUNDS.items())
                for argument in ("--" + name.replace("_", "-"), str(value))
            ],
        )
        self.assertEqual(2, code)
        self.assertEqual(
            f"allowed_tools of {len(tools)} exceeds the hard ceiling of "
            f"{MAX_ALLOWED_TOOLS_CEILING}",
            payload["reason"],
        )

    def test_an_allowlist_at_the_ceiling_is_admitted(self):
        tools = [f"tool_{index:05d}" for index in range(MAX_ALLOWED_TOOLS_CEILING)]
        arguments: list[str] = []
        for tool in tools:
            arguments.extend(["--allowed-tool", tool])
        code, payload = invoke(
            "config-create", str(self.root / "ceiling-tools.json"),
            "--campaign-configuration-id", "config.ceiling.v1", *arguments,
            *[
                argument for name, value in sorted(BOUNDS.items())
                for argument in ("--" + name.replace("_", "-"), str(value))
            ],
        )
        self.assertEqual(0, code, payload)
        self.assertEqual(tools, payload["allowed_tools"])

    # --- C11: one reason per rejecting class -------------------------------

    def test_each_rejection_class_reports_its_own_reason(self):
        pairs = (
            (campaign_cli.CampaignDurableRewriteError("x"), REFUSAL_DURABLE_REWRITE),
            (campaign_cli.CampaignConfigurationError("x"), REFUSAL_CONFIG_REJECTED),
            (CampaignRunnerError("x"), REFUSAL_RUNNER_REJECTED),
            (CampaignProvenanceError("x"), REFUSAL_LEDGER_INVALID),
            (OSError("x"), REFUSAL_DURABLE_IO),
        )
        for error, expected in pairs:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(expected, campaign_cli._rejection_reason(error))
        self.assertEqual(len(pairs), len({expected for _, expected in pairs}))

    def test_a_planner_that_raises_is_reported_as_a_runner_rejection(self):
        root = self.root / "planner-raises"
        with no_effects(), mock.patch.object(
            campaign_cli, "ScriptedCampaignPlanner", _RaisingPlanner,
        ):
            code, payload = invoke(
                "run", str(root), CAMPAIGN_ID,
                "--config", str(self.config), "--recorded-at", RUN_INSTANT,
                "--novelty-recheck", str(self.recheck),
            )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_RUNNER_REJECTED, payload["reason"])
        self.assertIn("scripted planner refused to plan", payload["detail"])

    def test_a_ledger_provenance_failure_is_not_a_runner_rejection(self):
        root = self.root / "ledger-invalid"
        with no_effects(), mock.patch.object(
            campaign_cli, "build_campaign_export",
            mock.Mock(side_effect=CampaignProvenanceError("ledger is not closed")),
        ):
            code, payload = invoke(
                "run", str(root), CAMPAIGN_ID,
                "--config", str(self.config), "--recorded-at", RUN_INSTANT,
                "--novelty-recheck", str(self.recheck),
            )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_LEDGER_INVALID, payload["reason"])

    def test_a_durable_rewrite_is_refused_by_its_own_name(self):
        """ADR-0065 §6 names this refusal and it was never a reported `reason`."""

        path = self.root / "rewritten-config.json"
        first = write_config(self.root / "rewrite-a")
        (path).write_bytes(first.read_bytes())
        code, payload = invoke(
            "config-create", str(path),
            "--campaign-configuration-id", "config.rewrite.v1",
            "--allowed-tool", "exact_python",
            *[
                argument for name, value in sorted(BOUNDS.items())
                for argument in ("--" + name.replace("_", "-"), str(value))
            ],
        )
        self.assertEqual(2, code)
        self.assertEqual(REFUSAL_DURABLE_REWRITE, payload["reason"])


if __name__ == "__main__":
    unittest.main()
