"""Offline acceptance for owner-activated public unauthenticated acquisition."""

from __future__ import annotations

import copy
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from math_research.phase4a.records import RightsReason, RightsUse, RightsValue
from math_research.phase4a.service import Phase4Service
from math_research.phase4b.acquisition import (
    AcquisitionPolicy, AcquisitionPolicyError, AcquisitionRequest,
    AuthorizedResource, Resolution, RightsDecision, RobotsSnapshot,
    RunAuthorization, TermsSnapshot, TransportFailure, TransportRequest,
    TransportResponse,
)
from math_research.phase4b.live_gate import (
    LiveGatePlan, live_gate_plan_bytes, live_gate_plan_hash,
)
from math_research.phase4b.live_transport import LiveNetworkPermit
from math_research.phase4b.public_acquisition import (
    ACTIVATION_HASH, LIVE_NETWORK_ACKNOWLEDGEMENT, acquire_public_plan,
    load_public_activation, validate_public_plan,
)
from math_research.phase4b.serialization import canonical_bytes, canonical_hash
from math_research.phase4b.service import Phase4BService
from math_research.phase4b.workspace import Phase4BWorkspace
from math_research.phase4b_cli import main as phase4b_main


ROOT = Path(__file__).resolve().parents[1]
ACTIVATION = ROOT / "config/phase4b-public-acquisition-activation-v1.json"
EVIDENCE = ROOT / "reports/phase-4b-activation/activation-evidence.json"
URL = "https://papers.example/open-paper.html"
ORIGIN = "https://papers.example"
ADDRESS = "93.184.216.34"


class Clock:
    def __init__(self) -> None:
        self.value = 0

    def now_milliseconds(self) -> int:
        self.value += 1
        return self.value


class Resolver:
    def __init__(self, permit: LiveNetworkPermit) -> None:
        self.permit = permit
        self.calls = 0

    def resolve(self, hostname: str) -> Resolution:
        self.calls += 1
        return Resolution(hostname, (ADDRESS,))


class Transport:
    def __init__(self, permit: LiveNetworkPermit) -> None:
        self.permit = permit
        self.calls = 0

    def fetch(self, _request: TransportRequest) -> TransportResponse:
        self.calls += 1
        body = b"<article><p>Open theorem candidate.</p></article>"
        return TransportResponse(
            200, (("content-type", "text/html"),), body, ADDRESS, 1,
        )


class FailingTransport(Transport):
    def fetch(self, _request: TransportRequest) -> TransportResponse:
        self.calls += 1
        raise TransportFailure("offline fixture failure")


def plan(
    *, headers: tuple[tuple[str, str], ...] = (), retries: int = 0,
    redirects: int = 0, rights_until: int | None = None,
) -> LiveGatePlan:
    policy = AcquisitionPolicy(max_retries=retries, max_redirects=redirects)
    permit = LiveNetworkPermit(
        "run.public.1", "human.operator", "human", "human_final",
        "capability.phase4b.live", (ORIGIN,), True,
    )
    authorization = RunAuthorization(
        permit.run_id, permit.actor_id, permit.actor_kind, permit.authority,
        permit.capability_id, "acquire_https", True, policy.content_hash,
        permit.approved_origins, (AuthorizedResource("request.public.1", URL),),
    )
    return LiveGatePlan(
        permit, authorization, policy,
        (AcquisitionRequest(permit.run_id, "request.public.1", permit.actor_id, URL, headers),),
        (
            RightsDecision(
                "right.public.acquire", permit.run_id, URL, "acquisition", "allowed",
                "human", "human_final", 1_787_235_349, rights_until,
            ),
            RightsDecision(
                "right.public.retain", permit.run_id, URL, "storage_and_retention",
                "allowed", "human", "human_final", 1_787_235_349, rights_until,
            ),
        ),
        (TermsSnapshot("terms.public.1", ORIGIN, "1" * 64, 1_787_235_349, True, True),),
        (RobotsSnapshot("robots.public.1", URL, "2" * 64, 1_787_235_349, True, True),),
        1_787_235_349, 1_787_235_349,
    )


class PublicAcquisitionTests(unittest.TestCase):
    def test_checked_in_owner_activation_is_bound_to_completed_evidence(self) -> None:
        activation = load_public_activation(ACTIVATION.read_bytes(), EVIDENCE.read_bytes())
        self.assertEqual("active", activation["status"])
        self.assertEqual("public_unauthenticated", activation["scope"]["access_mode"])
        self.assertFalse(activation["scope"]["credentials_allowed"])
        self.assertFalse(activation["scope"]["crawler_enabled"])

        changed = copy.deepcopy(activation)
        changed["scope"]["credentials_allowed"] = True
        changed["content_hash"] = canonical_hash(
            {key: value for key, value in changed.items() if key != "content_hash"}
        )
        with self.assertRaisesRegex(ValueError, "identity differs"):
            load_public_activation(canonical_bytes(changed), EVIDENCE.read_bytes())

    def test_public_subset_rejects_headers_and_retries_before_io(self) -> None:
        queried = plan()
        queried_url = URL + "?page=1"
        queried = replace(
            queried,
            requests=(replace(queried.requests[0], url=queried_url),),
            authorization=replace(
                queried.authorization,
                resources=(replace(queried.authorization.resources[0], url=queried_url),),
            ),
            rights=tuple(replace(right, url=queried_url) for right in queried.rights),
            robots=(replace(queried.robots[0], url=queried_url),),
        )
        for item, message in (
            (plan(headers=(("Accept", "text/html"),)), "headers_forbidden"),
            (plan(retries=1), "retries_forbidden"),
            (plan(redirects=1), "redirects_forbidden"),
            (queried, "query_forbidden"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(AcquisitionPolicyError, message):
                    validate_public_plan(item)

    def test_execute_persists_candidate_through_deletable_boundary(self) -> None:
        item = plan(rights_until=1_787_235_409)
        resolver, transport = Resolver(item.permit), Transport(item.permit)
        with tempfile.TemporaryDirectory() as temporary:
            with Phase4BWorkspace(Path(temporary) / "workspace") as workspace:
                with Phase4BService(workspace) as service:
                    stored = acquire_public_plan(
                        service, "source.public.1", item,
                        activation_data=ACTIVATION.read_bytes(),
                        activation_evidence_data=EVIDENCE.read_bytes(),
                        execution_epoch=item.now_epoch,
                        resolver=resolver, transport=transport, start_clock=Clock(),
                        network_acknowledgement=LIVE_NETWORK_ACKNOWLEDGEMENT,
                        confirmed_plan_hash=live_gate_plan_hash(item),
                    )
                    self.assertEqual(1, len(stored.result.candidates))
                    self.assertEqual(1, resolver.calls)
                    self.assertEqual(1, transport.calls)
                    record = stored.records[0]
                    self.assertEqual(
                        stored.result.candidates[0].body,
                        service.content.read(
                            "source.public.1",
                            expected_hash=record["payload"]["artifact_hash"],
                        ),
                    )
                    exported = workspace.export_bytes()
                    self.assertNotIn(b"Open theorem candidate", exported)
                    for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION):
                        self.assertTrue(
                            service.rights.evaluate_rights(
                                "source.public.1", use, at="2026-08-20T14:15:49Z"
                            ).allowed
                        )
                    decisions = [
                        record for record in service.rights.workspace.records()
                        if record["record_type"] == "source_rights_decision"
                    ]
                    self.assertEqual(2, len(decisions))
                    self.assertTrue(all(
                        record["payload"]["valid_until"] == "2026-08-20T14:16:49Z"
                        for record in decisions
                    ))
                    expected_refs = {
                        "evidence.phase4b-public-activation."
                        + ACTIVATION_HASH.removeprefix("sha256:"),
                        "evidence.phase4b-public-plan."
                        + live_gate_plan_hash(item).removeprefix("sha256:"),
                    }
                    self.assertTrue(all(
                        set(record["evidence_refs"]) == expected_refs
                        for record in decisions
                    ))

    def test_existing_blocking_right_is_never_overridden(self) -> None:
        item = plan()
        resolver, transport = Resolver(item.permit), Transport(item.permit)
        with tempfile.TemporaryDirectory() as temporary:
            with Phase4BWorkspace(Path(temporary) / "workspace") as workspace:
                rights = Phase4Service(workspace.phase4a)
                rights.initialize_policy(
                    actor_id="human.operator", recorded_at="2026-08-20T14:15:49Z"
                )
                rights.append_rights(
                    source_id="source.public.blocked",
                    intended_use=RightsUse.STORAGE_AND_RETENTION,
                    value=RightsValue.PROHIBITED,
                    reason_code=RightsReason.EXPLICITLY_PROHIBITED,
                    reason_detail="negative control",
                    evidence_refs=("evidence.public-rights-block",),
                    actor_id="human.operator",
                    valid_from="2026-08-20T14:15:49Z",
                    valid_until=None,
                    recorded_at="2026-08-20T14:15:49Z",
                    lifecycle_id="rights-lifecycle.public-block",
                )
                with Phase4BService(workspace) as service:
                    before = len(service.rights.workspace.records())
                    with self.assertRaisesRegex(
                        AcquisitionPolicyError, "existing_rights_block"
                    ):
                        acquire_public_plan(
                            service, "source.public.blocked", item,
                            activation_data=ACTIVATION.read_bytes(),
                            activation_evidence_data=EVIDENCE.read_bytes(),
                            execution_epoch=item.now_epoch,
                            resolver=resolver, transport=transport, start_clock=Clock(),
                            network_acknowledgement=LIVE_NETWORK_ACKNOWLEDGEMENT,
                            confirmed_plan_hash=live_gate_plan_hash(item),
                        )
                    self.assertEqual(before, len(service.rights.workspace.records()))
                self.assertEqual(0, resolver.calls)
                self.assertEqual(0, transport.calls)

    def test_execution_boundary_requires_ack_hash_and_fresh_record_time(self) -> None:
        original = plan()
        cases = (
            ({"network_acknowledgement": "wrong",
              "confirmed_plan_hash": live_gate_plan_hash(original)},
             "acknowledgement_required", original),
            ({"network_acknowledgement": LIVE_NETWORK_ACKNOWLEDGEMENT,
              "confirmed_plan_hash": "sha256:" + "0" * 64},
             "plan_hash_confirmation_invalid", original),
            ({"network_acknowledgement": LIVE_NETWORK_ACKNOWLEDGEMENT,
              "confirmed_plan_hash": live_gate_plan_hash(replace(original, recorded_at_epoch=0))},
             "plan_stale", replace(original, recorded_at_epoch=0)),
        )
        for confirmation, message, item in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary:
                resolver, transport = Resolver(item.permit), Transport(item.permit)
                with Phase4BWorkspace(Path(temporary) / "workspace") as workspace:
                    with Phase4BService(workspace) as service:
                        before = len(workspace.records())
                        with self.assertRaisesRegex(AcquisitionPolicyError, message):
                            acquire_public_plan(
                                service, "source.public.rejected", item,
                                activation_data=ACTIVATION.read_bytes(),
                                activation_evidence_data=EVIDENCE.read_bytes(),
                                execution_epoch=original.now_epoch,
                                resolver=resolver, transport=transport,
                                start_clock=Clock(), **confirmation,
                            )
                        self.assertEqual(before, len(workspace.records()))
                self.assertEqual(0, resolver.calls)
                self.assertEqual(0, transport.calls)

    def test_malformed_exact_plan_envelope_fails_before_mutation_or_io(self) -> None:
        original = plan()
        malformed = replace(original, rights=(original.rights[0], original.rights[0]))
        resolver, transport = Resolver(malformed.permit), Transport(malformed.permit)
        with tempfile.TemporaryDirectory() as temporary:
            with Phase4BWorkspace(Path(temporary) / "workspace") as workspace:
                with Phase4BService(workspace) as service:
                    with self.assertRaisesRegex(AcquisitionPolicyError, "rights_invalid"):
                        acquire_public_plan(
                            service, "source.public.malformed", malformed,
                            activation_data=ACTIVATION.read_bytes(),
                            activation_evidence_data=EVIDENCE.read_bytes(),
                            execution_epoch=malformed.now_epoch,
                            resolver=resolver, transport=transport, start_clock=Clock(),
                            network_acknowledgement=LIVE_NETWORK_ACKNOWLEDGEMENT,
                            confirmed_plan_hash=live_gate_plan_hash(malformed),
                        )
                    self.assertEqual((), workspace.records())
                    self.assertEqual((), service.rights.workspace.records())
        self.assertEqual(0, resolver.calls)
        self.assertEqual(0, transport.calls)

    def test_preexisting_allowed_rights_still_record_each_execution_hash(self) -> None:
        for failure in (False, True):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                item = plan()
                root = Path(temporary) / "workspace"
                source_id = "source.public.preallowed"
                with Phase4BWorkspace(root) as workspace:
                    rights = Phase4Service(workspace.phase4a)
                    rights.initialize_policy(
                        actor_id="human.operator", recorded_at="2026-08-20T14:15:49Z"
                    )
                    for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION):
                        rights.append_rights(
                            source_id=source_id, intended_use=use,
                            value=RightsValue.ALLOWED, reason_code=RightsReason.PERMITTED,
                            reason_detail="preexisting allowed fixture",
                            evidence_refs=("evidence.preexisting.allowed",),
                            actor_id="human.operator", valid_from="2026-08-20T14:15:49Z",
                            valid_until=None, recorded_at="2026-08-20T14:15:49Z",
                            lifecycle_id=f"rights-lifecycle.preexisting.{use.value}",
                        )
                    resolver = Resolver(item.permit)
                    transport = FailingTransport(item.permit) if failure else Transport(item.permit)
                    with Phase4BService(workspace) as service:
                        stored = acquire_public_plan(
                            service, source_id, item,
                            activation_data=ACTIVATION.read_bytes(),
                            activation_evidence_data=EVIDENCE.read_bytes(),
                            execution_epoch=item.now_epoch,
                            resolver=resolver, transport=transport, start_clock=Clock(),
                            network_acknowledgement=LIVE_NETWORK_ACKNOWLEDGEMENT,
                            confirmed_plan_hash=live_gate_plan_hash(item),
                        )
                        self.assertEqual(failure, not bool(stored.result.candidates))
                with Phase4BWorkspace(root) as reopened:
                    current_rights = [
                        record for record in reopened.phase4a.records()
                        if record["record_type"] == "source_rights_decision"
                        and record["subject_id"] == source_id
                    ][-2:]
                    expected_refs = {
                        "evidence.phase4b-public-activation."
                        + ACTIVATION_HASH.removeprefix("sha256:"),
                        "evidence.phase4b-public-plan."
                        + live_gate_plan_hash(item).removeprefix("sha256:"),
                    }
                    self.assertTrue(all(
                        set(record["evidence_refs"]) == expected_refs
                        for record in current_rights
                    ))
                    exported = reopened.export_bytes()
                    record_types = {record["record_type"] for record in reopened.records()}
                    self.assertIn(
                        "failure" if failure else "acquisition_candidate",
                        record_types,
                    )

    def test_stale_plan_fails_before_rights_or_network(self) -> None:
        item = plan()
        resolver, transport = Resolver(item.permit), Transport(item.permit)
        with tempfile.TemporaryDirectory() as temporary:
            with Phase4BWorkspace(Path(temporary) / "workspace") as workspace:
                with Phase4BService(workspace) as service:
                    with self.assertRaisesRegex(AcquisitionPolicyError, "plan_stale"):
                        acquire_public_plan(
                            service, "source.public.stale", item,
                            activation_data=ACTIVATION.read_bytes(),
                            activation_evidence_data=EVIDENCE.read_bytes(),
                            execution_epoch=item.now_epoch + 301,
                            resolver=resolver, transport=transport, start_clock=Clock(),
                            network_acknowledgement=LIVE_NETWORK_ACKNOWLEDGEMENT,
                            confirmed_plan_hash=live_gate_plan_hash(item),
                        )
                    self.assertEqual((), service.rights.workspace.records())
        self.assertEqual(0, resolver.calls)
        self.assertEqual(0, transport.calls)

    def test_cli_defaults_to_non_mutating_dry_run(self) -> None:
        item = plan()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            workspace = root / "workspace"
            plan_path.write_bytes(live_gate_plan_bytes(item))
            stdout = StringIO()
            with redirect_stdout(stdout):
                result = phase4b_main([
                    "public-acquire", str(workspace), "source.public.dry-run",
                    str(plan_path), "--activation", str(ACTIVATION),
                    "--activation-evidence", str(EVIDENCE),
                ])
            self.assertEqual(0, result)
            self.assertEqual("not_executed", __import__("json").loads(stdout.getvalue())["execution_status"])
            self.assertFalse(workspace.exists())


if __name__ == "__main__":
    unittest.main()
