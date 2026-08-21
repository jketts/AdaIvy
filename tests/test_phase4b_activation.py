"""Strict composition tests for non-mutating Phase 4B activation evidence."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from math_research.phase4b.acquisition import (
    AcquisitionPolicy, AcquisitionRequest, AuthorizedResource, RightsDecision,
    RobotsSnapshot, RunAuthorization, TermsSnapshot,
)
from math_research.phase4b.activation import (
    SandboxActivationAttestation, create_activation_evidence,
    load_activation_evidence, verify_activation_evidence,
)
from math_research.phase4b.live_gate import LiveGatePlan, not_executed_report, run_live_gate
from math_research.phase4b.live_transport import (
    LiveNetworkPermit, OptInHttpsTransport, OptInSystemResolver,
)
from math_research.phase4b.serialization import canonical_bytes, canonical_hash


ROOT = Path(__file__).resolve().parent.parent
URL = "https://papers.example/source"
ORIGIN = "https://papers.example"


class _StepClock:
    def __init__(self) -> None:
        self.value = 0

    def now_milliseconds(self) -> int:
        self.value += 10
        return self.value


class _TransportClock:
    def __init__(self) -> None:
        self.value = 99

    def __call__(self) -> int:
        self.value += 1
        return self.value


class _Socket:
    def __init__(self) -> None:
        self.response = bytearray(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
            b"Content-Length: 5\r\n\r\nproof"
        )

    def settimeout(self, _timeout: float) -> None: pass
    def getpeername(self): return ("93.184.216.34", 443)
    def sendall(self, _data: bytes) -> None: pass

    def recv(self, maximum: int) -> bytes:
        value = bytes(self.response[:maximum])
        del self.response[:maximum]
        return value

    def close(self) -> None: pass


def _live_plan() -> LiveGatePlan:
    policy = AcquisitionPolicy(max_retries=0)
    permit = LiveNetworkPermit(
        "run.activation", "human.operator", "human", "human_final",
        "capability.phase4b.live", (ORIGIN,), True,
    )
    authorization = RunAuthorization(
        permit.run_id, permit.actor_id, permit.actor_kind, permit.authority,
        permit.capability_id, "acquire_https", True, policy.content_hash,
        permit.approved_origins, (AuthorizedResource("request.1", URL),),
    )
    return LiveGatePlan(
        permit, authorization, policy,
        (AcquisitionRequest(permit.run_id, "request.1", permit.actor_id, URL),),
        (
            RightsDecision(
                "right.acquire", permit.run_id, URL, "acquisition", "allowed",
                "human", "human_final", 0, None,
            ),
            RightsDecision(
                "right.retain", permit.run_id, URL, "storage_and_retention",
                "allowed", "human", "human_final", 0, None,
            ),
        ),
        (TermsSnapshot("terms.1", ORIGIN, "1" * 64, 10, True, True),),
        (RobotsSnapshot("robots.1", URL, "2" * 64, 10, True, True),),
        20, 21,
    )


def _executed_live_report() -> dict[str, object]:
    plan = _live_plan()
    resolver = OptInSystemResolver(
        plan.permit, resolve_addresses=lambda _hostname: ("93.184.216.34",),
    )
    sock = _Socket()
    transport = OptInHttpsTransport(
        plan.permit, dial=lambda _address, _timeout: sock,
        tls_wrap=lambda raw, _hostname: raw, now_milliseconds=_TransportClock(),
    )
    return run_live_gate(
        plan, resolver=resolver, transport=transport, start_clock=_StepClock()
    )


def _sandbox_evidence(feasible: dict[str, object]) -> dict[str, object]:
    corpus = feasible["parser_corpus_authorization"]
    assert isinstance(corpus, dict)
    value: dict[str, object] = {
        "schema_version": "test.strict-parser-sandbox-evidence.v1",
        "parser_corpus_authorization_hash": corpus["content_hash"],
        "parser_artifacts_hash": canonical_hash(corpus["artifacts"]),
        "environment_hash": "sha256:" + "3" * 64,
        "policy_hash": "sha256:" + "4" * 64,
        "status": "authorized",
        "profiles_connected": ["html", "pdf", "tex"],
        "strict_transient_memory_enforcement": True,
        "no_network_enforcement": True,
        "read_only_input_and_root_enforcement": True,
        "bounded_noexec_temporary_enforcement": True,
        "no_ambient_secrets_enforcement": True,
        "resource_limits_enforcement": True,
        "production_parser_connected": True,
        "production_activated": False,
    }
    value["content_hash"] = canonical_hash(value)
    return value


def _verify_test_sandbox(value: object) -> SandboxActivationAttestation:
    fields = {
        "schema_version", "parser_corpus_authorization_hash",
        "parser_artifacts_hash", "environment_hash", "policy_hash", "status",
        "profiles_connected", "strict_transient_memory_enforcement",
        "no_network_enforcement", "read_only_input_and_root_enforcement",
        "bounded_noexec_temporary_enforcement", "no_ambient_secrets_enforcement",
        "resource_limits_enforcement", "production_parser_connected",
        "production_activated", "content_hash",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("test sandbox evidence shape differs")
    supplied = value["content_hash"]
    preimage = {key: item for key, item in value.items() if key != "content_hash"}
    if supplied != canonical_hash(preimage):
        raise ValueError("test sandbox evidence hash differs")
    return SandboxActivationAttestation(
        evidence_schema=str(value["schema_version"]),
        evidence_hash=str(supplied),
        parser_corpus_authorization_hash=str(value["parser_corpus_authorization_hash"]),
        parser_artifacts_hash=str(value["parser_artifacts_hash"]),
        environment_hash=str(value["environment_hash"]),
        policy_hash=str(value["policy_hash"]),
        status=str(value["status"]),
        profiles_connected=tuple(value["profiles_connected"]),
        strict_transient_memory_enforcement=value["strict_transient_memory_enforcement"],
        no_network_enforcement=value["no_network_enforcement"],
        read_only_input_and_root_enforcement=value["read_only_input_and_root_enforcement"],
        bounded_noexec_temporary_enforcement=value["bounded_noexec_temporary_enforcement"],
        no_ambient_secrets_enforcement=value["no_ambient_secrets_enforcement"],
        resource_limits_enforcement=value["resource_limits_enforcement"],
        production_parser_connected=value["production_parser_connected"],
        production_activated=value["production_activated"],
    )


class Phase4BActivationEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            gate_root = Path(temporary)
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            reports: list[dict[str, object]] = []
            for index in range(2):
                completed = subprocess.run(
                    [
                        sys.executable, "-m", "math_research.phase4b_cli", "gate",
                        str(ROOT), str(gate_root / f"gate-{index}"),
                    ],
                    cwd=ROOT, env=environment, check=True, capture_output=True,
                    text=True, timeout=30,
                )
                reports.append(json.loads(completed.stdout))
            cls.feasible_reports = tuple(reports)
        cls.live = _executed_live_report()
        cls.sandbox = _sandbox_evidence(cls.feasible_reports[0])

    def _create(self) -> dict[str, object]:
        return create_activation_evidence(
            self.feasible_reports, self.live, self.sandbox,
            repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
        )

    def test_combiner_preserves_sources_and_has_no_activation_effect(self) -> None:
        offline_before = tuple(canonical_bytes(item) for item in self.feasible_reports)
        live_before = canonical_bytes(self.live)
        report = self._create()
        self.assertEqual(
            offline_before,
            tuple(canonical_bytes(item) for item in self.feasible_reports),
        )
        self.assertEqual(live_before, canonical_bytes(self.live))
        self.assertEqual("evidence_complete_pending_owner_activation", report["status"])
        self.assertEqual("none", report["activation_effect"])
        self.assertFalse(report["production_activated"])
        self.assertEqual(
            2,
            report["deterministic_offline_evidence"]["independent_gate_process_count"],
        )
        self.assertEqual(
            [item["content_hash"] for item in self.feasible_reports],
            report["deterministic_offline_evidence"]["report_content_hashes"],
        )
        verify_activation_evidence(
            report, self.feasible_reports, self.live, self.sandbox,
            repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
        )
        self.assertEqual(
            report,
            load_activation_evidence(
                canonical_bytes(report), self.feasible_reports, self.live, self.sandbox,
                repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
            ),
        )

    def test_not_executed_or_failed_live_evidence_cannot_clear_gate(self) -> None:
        with self.assertRaisesRegex(ValueError, "did not execute"):
            create_activation_evidence(
                self.feasible_reports, not_executed_report(_live_plan()), self.sandbox,
                repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
            )

    def test_sampled_or_unbound_sandbox_evidence_cannot_clear_gate(self) -> None:
        weakened = copy.deepcopy(self.sandbox)
        weakened["strict_transient_memory_enforcement"] = False
        weakened["content_hash"] = canonical_hash({
            key: value for key, value in weakened.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "not strict"):
            create_activation_evidence(
                self.feasible_reports, self.live, weakened,
                repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
            )
        unbound = copy.deepcopy(self.sandbox)
        unbound["parser_artifacts_hash"] = "sha256:" + "0" * 64
        unbound["content_hash"] = canonical_hash({
            key: value for key, value in unbound.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "not bound"):
            create_activation_evidence(
                self.feasible_reports, self.live, unbound,
                repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
            )

    def test_self_rehashed_combined_forgery_cannot_replace_offline_evidence(self) -> None:
        report = self._create()
        report["deterministic_offline_evidence"]["semantic_export_hash"] = (
            "sha256:" + "9" * 64
        )
        report["content_hash"] = canonical_hash({
            key: value for key, value in report.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "does not match its sources"):
            verify_activation_evidence(
                report, self.feasible_reports, self.live, self.sandbox,
                repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
            )

    def test_combined_import_rejects_duplicate_or_noncanonical_json(self) -> None:
        report = self._create()
        data = canonical_bytes(report)
        duplicate = data.replace(
            b'{"activation_effect":', b'{"activation_effect":"none","activation_effect":', 1
        )
        for invalid in (duplicate, data + b"\n"):
            with self.subTest(invalid=invalid[-8:]):
                with self.assertRaises(ValueError):
                    load_activation_evidence(
                        invalid, self.feasible_reports, self.live, self.sandbox,
                        repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
                    )

    def test_one_report_or_two_different_offline_identities_cannot_clear_gate(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly two"):
            create_activation_evidence(
                self.feasible_reports[:1], self.live, self.sandbox,
                repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
            )
        changed = copy.deepcopy(self.feasible_reports[1])
        changed["determinism"]["semantic_export_hash"] = "sha256:" + "8" * 64
        changed["content_hash"] = canonical_hash({
            key: value for key, value in changed.items() if key != "content_hash"
        })
        with self.assertRaises(ValueError):
            create_activation_evidence(
                (self.feasible_reports[0], changed), self.live, self.sandbox,
                repository_root=ROOT, sandbox_verifier=_verify_test_sandbox,
            )


if __name__ == "__main__":
    unittest.main()
