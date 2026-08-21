"""Offline tests for the separately authorized Phase 4B live gate."""

from __future__ import annotations

import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from math_research.phase4b.acquisition import (
    AcquisitionPolicy, AcquisitionPolicyError, AcquisitionRequest,
    AuthorizedResource, RightsDecision, RobotsSnapshot, RunAuthorization,
    TermsSnapshot,
)
from math_research.phase4b.live_gate import (
    LiveGatePlan, live_gate_plan_bytes, live_gate_plan_hash,
    load_live_gate_plan, not_executed_report, run_live_gate,
    verify_live_gate_report,
)
from math_research.phase4b.live_transport import (
    LiveNetworkPermit, OptInHttpsTransport, OptInSystemResolver,
)
from math_research.phase4b.serialization import canonical_bytes, canonical_hash
from math_research.phase4b_cli import main as phase4b_main


URL = "https://papers.example/article?format=html"
ORIGIN = "https://papers.example"


class StepClock:
    def __init__(self) -> None: self.value = 0
    def now_milliseconds(self) -> int:
        self.value += 10
        return self.value


class TransportClock:
    def __init__(self) -> None: self.value = 99
    def __call__(self) -> int:
        self.value += 1
        return self.value


class ScriptedSocket:
    def __init__(self) -> None:
        self.response = bytearray(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 5\r\n\r\nproof"
        )
    def settimeout(self, _timeout: float) -> None: pass
    def getpeername(self): return ("93.184.216.34", 443)
    def sendall(self, _data: bytes) -> None: pass
    def recv(self, maximum: int) -> bytes:
        value = bytes(self.response[:maximum]); del self.response[:maximum]; return value
    def close(self) -> None: pass


def plan(*, url: str = URL, headers: tuple[tuple[str, str], ...] = ()) -> LiveGatePlan:
    policy = AcquisitionPolicy(max_retries=0)
    permit = LiveNetworkPermit(
        "run.live.gate", "human.operator", "human", "human_final",
        "capability.phase4b.live", (ORIGIN,), True,
    )
    authorization = RunAuthorization(
        permit.run_id, permit.actor_id, permit.actor_kind, permit.authority,
        permit.capability_id, "acquire_https", True, policy.content_hash,
        permit.approved_origins, (AuthorizedResource("request.1", url),),
    )
    return LiveGatePlan(
        permit, authorization, policy,
        (AcquisitionRequest(permit.run_id, "request.1", permit.actor_id, url, headers),),
        (
            RightsDecision("right.acquire", permit.run_id, url, "acquisition", "allowed", "human", "human_final", 0, None),
            RightsDecision("right.retain", permit.run_id, url, "storage_and_retention", "allowed", "human", "human_final", 0, None),
        ),
        (TermsSnapshot("terms.1", ORIGIN, "1" * 64, 10, True, True),),
        (RobotsSnapshot("robots.1", url, "2" * 64, 10, True, True),),
        20, 21,
    )


def executed_report() -> dict[str, object]:
    item = plan()
    resolver = OptInSystemResolver(
        item.permit, resolve_addresses=lambda _host: ("93.184.216.34",),
    )
    sock = ScriptedSocket()
    transport = OptInHttpsTransport(
        item.permit, dial=lambda _address, _timeout: sock,
        tls_wrap=lambda raw, _hostname: raw, now_milliseconds=TransportClock(),
    )
    return run_live_gate(
        item, resolver=resolver, transport=transport, start_clock=StepClock()
    )


class Phase4BLiveGateTests(unittest.TestCase):
    def test_plan_has_canonical_round_trip_and_rejects_tampering(self) -> None:
        original = plan()
        data = live_gate_plan_bytes(original)
        self.assertEqual(original, load_live_gate_plan(data))
        self.assertEqual(json.loads(data)["content_hash"], live_gate_plan_hash(original))
        value = json.loads(data)
        value["recorded_at_epoch"] += 1
        with self.assertRaisesRegex(ValueError, "content hash"):
            load_live_gate_plan(json.dumps(value).encode())

    def test_cli_defaults_to_verified_not_executed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "live-plan.json"
            output = root / "live-report.json"
            source.write_bytes(live_gate_plan_bytes(plan()))
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    0, phase4b_main(["live-gate", str(source), "--output", str(output)])
                )
            observed = json.loads(stdout.getvalue())
            self.assertEqual("not_executed", observed["execution_status"])
            self.assertEqual(observed, json.loads(output.read_text("utf-8")))

    def test_cli_execution_acknowledgement_is_bound_to_exact_plan_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "live-plan.json"
            source.write_bytes(live_gate_plan_bytes(plan()))
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    phase4b_main([
                        "live-gate", str(source), "--execute",
                        "--confirm-live-network",
                        "I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK",
                    ])
                with self.assertRaises(SystemExit):
                    phase4b_main([
                        "live-gate", str(source), "--execute",
                        "--confirm-live-network",
                        "I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK",
                        "--confirm-plan-hash", "sha256:" + "0" * 64,
                    ])

    def test_not_executed_report_is_deterministic_and_nonactivating(self) -> None:
        left = not_executed_report(plan())
        right = not_executed_report(plan())
        self.assertEqual(left, right)
        self.assertEqual("not_executed", left["execution_status"])
        self.assertFalse(left["counted_as_phase4b_activation"])
        verify_live_gate_report(left)

    def test_exact_opt_in_adapters_emit_redacted_hashed_evidence(self) -> None:
        report = executed_report()
        verify_live_gate_report(report)
        self.assertEqual("executed", report["execution_status"])
        self.assertEqual("candidate_acquired", report["outcomes"][0]["outcome"])
        self.assertTrue(report["network_evidence"][0]["connected_peer_in_resolved_set"])
        self.assertEqual("text/html", report["candidate_evidence"][0]["media_type"])
        rendered = canonical_bytes(report)
        for forbidden in (URL, ORIGIN, "93.184.216.34", "human.operator", "proof"):
            self.assertNotIn(forbidden.encode(), rendered)

    def test_credential_bearing_urls_and_headers_fail_before_adapter_creation(self) -> None:
        with self.assertRaisesRegex(AcquisitionPolicyError, "url_credentials"):
            plan(url="https://papers.example/article?api_key=secret")
        with self.assertRaisesRegex(AcquisitionPolicyError, "credential_header"):
            plan(headers=(("Authorization", "Bearer secret"),))
        with self.assertRaisesRegex(AcquisitionPolicyError, "header_not_allowed"):
            plan(headers=(("X-Trace", "opaque-secret"),))

    def test_adapter_permit_mismatch_fails_closed(self) -> None:
        item = plan()
        other = LiveNetworkPermit(
            "run.other", "human.operator", "human", "human_final",
            "capability.phase4b.live", (ORIGIN,), True,
        )
        resolver = OptInSystemResolver(other, resolve_addresses=lambda _host: ())
        transport = OptInHttpsTransport(other)
        with self.assertRaisesRegex(AcquisitionPolicyError, "adapter_permit_mismatch"):
            run_live_gate(item, resolver=resolver, transport=transport, start_clock=StepClock())

    def test_report_hash_tampering_is_rejected(self) -> None:
        report = json.loads(json.dumps(not_executed_report(plan())))
        report["request_count"] = 2
        with self.assertRaisesRegex(ValueError, "content hash"):
            verify_live_gate_report(report)

    def test_self_hashed_forged_or_secret_bearing_report_is_rejected(self) -> None:
        for field, value in (("request_count", -1), ("actor_id_hash", URL)):
            with self.subTest(field=field):
                report = json.loads(json.dumps(not_executed_report(plan())))
                if field == "actor_id_hash":
                    report["permit"][field] = value
                else:
                    report[field] = value
                report["content_hash"] = canonical_hash({
                    key: item for key, item in report.items() if key != "content_hash"
                })
                with self.assertRaises(ValueError):
                    verify_live_gate_report(report)

    def test_self_hashed_failed_outcome_cannot_retain_candidate_evidence(self) -> None:
        report = executed_report()
        report["outcomes"][0]["outcome"] = "failed"
        report["outcomes"][0]["reason"] = "http_status"
        report["content_hash"] = canonical_hash({
            key: item for key, item in report.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "outcome and candidate"):
            verify_live_gate_report(report)

    def test_self_hashed_candidate_cannot_omit_network_operations(self) -> None:
        report = executed_report()
        report["network_evidence"] = []
        report["content_hash"] = canonical_hash({
            key: item for key, item in report.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "lacks network"):
            verify_live_gate_report(report)

    def test_self_hashed_success_cannot_mix_policy_or_transport_failure(self) -> None:
        for field in ("policy_failure", "transport_failure"):
            with self.subTest(field=field):
                report = executed_report()
                report["network_evidence"][0][field] = "forged_failure"
                report["content_hash"] = canonical_hash({
                    key: item for key, item in report.items() if key != "content_hash"
                })
                with self.assertRaisesRegex(ValueError, "fields differ"):
                    verify_live_gate_report(report)

    def test_self_hashed_failed_outcome_cannot_be_backed_only_by_clean_200(self) -> None:
        report = executed_report()
        report["outcomes"][0]["outcome"] = "failed"
        report["outcomes"][0]["reason"] = "http_status"
        report["candidate_evidence"] = []
        report["content_hash"] = canonical_hash({
            key: item for key, item in report.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "terminal evidence"):
            verify_live_gate_report(report)


if __name__ == "__main__":
    unittest.main()
