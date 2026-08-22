"""Acceptance tests for batch public acquisition under one plan approval (ADR-0081)."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

from math_research.phase4b.acquisition import (
    AcquisitionPolicyError, Resolution, TransportRequest, TransportResponse,
)
from math_research.phase4b.batch_acquisition import (
    BATCH_ACKNOWLEDGEMENT, BATCH_ACTIVATION_HASH, BATCH_CAPABILITY_ID,
    build_batch_plan, execute_batch_plan, load_batch_activation,
    validate_batch_plan, verify_batch_report,
)
from math_research.phase4b.live_transport import LiveNetworkPermit
from math_research.phase4b.serialization import canonical_hash

ROOT = Path(__file__).resolve().parents[1]
ACTIVATION = (ROOT / "config/phase4b-public-acquisition-activation-v2.json").read_bytes()
EVIDENCE = (ROOT / "reports/phase-4b-activation/activation-evidence.json").read_bytes()
EXECUTION_EPOCH = 1_787_400_000
ADDRESSES = {
    "arxiv.org": "128.84.21.199",
    "papers.example.org": "93.184.216.34",
}


def request(index: int, host: str = "arxiv.org") -> dict:
    return {
        "request_id": f"req-{index:04d}".replace("0", "a"),
        "url": f"https://{host}/abs/paper-{index}",
        "origin_selected_by": "human",
        "provenance": None,
        "rights": {"acquisition": "allowed", "storage_and_retention": "allowed"},
    }


def plan_for(requests: list[dict], hosts: list[str] | None = None) -> dict:
    return build_batch_plan(
        run_id="run.batch.alpha",
        actor_id="human.researcher",
        approved_at_epoch=EXECUTION_EPOCH - 60,
        allowlist_hosts=hosts or ["arxiv.org", "papers.example.org"],
        requests=requests,
    )


def permit_for(plan: dict) -> LiveNetworkPermit:
    origins = tuple(sorted({
        "https://" + item["url"].split("/")[2] for item in plan["requests"]
    }))
    return LiveNetworkPermit(
        plan["run_id"], "human.researcher", "human", "human_final",
        BATCH_CAPABILITY_ID, origins, True,
    )


class FakeResolver:
    def __init__(self, permit: LiveNetworkPermit) -> None:
        self.permit = permit

    def resolve(self, hostname: str) -> Resolution:
        return Resolution(hostname, (ADDRESSES[hostname],))


class FakeTransport:
    def __init__(
        self, permit: LiveNetworkPermit, *,
        statuses: dict[str, int] | None = None,
    ) -> None:
        self.permit = permit
        self.statuses = statuses or {}
        self.requests: list[TransportRequest] = []

    def fetch(self, request: TransportRequest) -> TransportResponse:
        self.requests.append(request)
        status = self.statuses.get(request.url, 200)
        body = b"%PDF-1.7 fake body for " + request.url.encode("utf-8")
        return TransportResponse(
            status, (("content-type", "application/pdf"),), body,
            request.connect_addresses[0], 1,
        )


def execute(plan: dict, transport: FakeTransport | None = None):
    permit = permit_for(plan)
    transport = transport or FakeTransport(permit)
    transport.permit = permit
    return execute_batch_plan(
        plan, activation_data=ACTIVATION, activation_evidence_data=EVIDENCE,
        permit=permit, resolver=FakeResolver(permit), transport=transport,
        execution_epoch=EXECUTION_EPOCH,
        network_acknowledgement=BATCH_ACKNOWLEDGEMENT,
        confirmed_plan_hash=plan["content_hash"],
    ), transport


class BatchActivationTests(unittest.TestCase):
    def test_activation_is_pinned_and_keeps_v1_discipline(self) -> None:
        activation = load_batch_activation(ACTIVATION, EVIDENCE)
        self.assertEqual(BATCH_ACTIVATION_HASH, activation["content_hash"])
        scope = activation["scope"]
        self.assertEqual(32, scope["max_requests_per_run"])
        self.assertFalse(scope["credentials_allowed"])
        self.assertFalse(scope["redirects_allowed"])
        self.assertFalse(scope["query_strings_allowed"])
        self.assertEqual([], scope["request_headers_allowed"])
        self.assertTrue(scope["per_plan_human_final_approval_required"])
        self.assertFalse(scope["per_url_human_approval_required"])

    def test_widened_scope_is_refused(self) -> None:
        import json

        value = json.loads(ACTIVATION)
        value["scope"]["max_requests_per_run"] = 10_000
        value["content_hash"] = canonical_hash({
            key: item for key, item in value.items() if key != "content_hash"
        })
        from math_research.phase4b.serialization import canonical_bytes

        with self.assertRaisesRegex(ValueError, "identity differs"):
            load_batch_activation(canonical_bytes(value), EVIDENCE)


class BatchPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.activation = load_batch_activation(ACTIVATION, EVIDENCE)

    def test_one_approval_covers_n_urls(self) -> None:
        plan = plan_for(
            [request(index) for index in range(1, 9)]
            + [request(9, "papers.example.org")],
        )
        validate_batch_plan(self.activation, plan, execution_epoch=EXECUTION_EPOCH)
        (report, bodies), transport = execute(plan)
        verify_batch_report(report, plan)
        self.assertEqual("plan", report["approval_scope"])
        self.assertEqual(9, report["totals"]["requests"])
        self.assertEqual(9, report["totals"]["stored"])
        self.assertEqual(9, len(report["url_ledger"]))
        self.assertEqual(9, len(bodies))
        for entry in report["url_ledger"]:
            self.assertEqual("stored_candidate", entry["outcome"])
            self.assertEqual("untrusted_candidate", entry["disposition"])
            self.assertEqual("not_assessed", entry["applicability"])
        for sent in transport.requests:
            self.assertEqual((), sent.headers)
            self.assertEqual("GET", sent.method)

    def test_over_count_plan_is_refused(self) -> None:
        plan = plan_for([request(index) for index in range(1, 34)])
        with self.assertRaisesRegex(AcquisitionPolicyError, "request_count"):
            validate_batch_plan(
                self.activation, plan, execution_epoch=EXECUTION_EPOCH,
            )

    def test_offlist_origin_is_refused(self) -> None:
        plan = plan_for([request(1, "evil.example.org")])
        with self.assertRaisesRegex(AcquisitionPolicyError, "offlist"):
            validate_batch_plan(
                self.activation, plan, execution_epoch=EXECUTION_EPOCH,
            )

    def test_query_string_is_refused(self) -> None:
        item = request(1)
        item["url"] = "https://arxiv.org/abs/paper-1?session=1"
        plan = plan_for([item])
        with self.assertRaisesRegex(AcquisitionPolicyError, "query_string"):
            validate_batch_plan(
                self.activation, plan, execution_epoch=EXECUTION_EPOCH,
            )

    def test_automation_selection_requires_provenance_edge(self) -> None:
        item = request(1)
        item["origin_selected_by"] = "automation"
        plan = plan_for([item])
        with self.assertRaisesRegex(AcquisitionPolicyError, "origin_selection"):
            validate_batch_plan(
                self.activation, plan, execution_epoch=EXECUTION_EPOCH,
            )
        item["provenance"] = {
            "origin_document_id": "doc.alpha",
            "origin_acquisition_record_id": "phase4b.acquisition.alpha",
            "reference_field": "reference_url",
            "reference_index": 0,
            "reference_value": item["url"],
        }
        plan = plan_for([item])
        validate_batch_plan(self.activation, plan, execution_epoch=EXECUTION_EPOCH)

    def test_stale_plan_is_refused(self) -> None:
        plan = plan_for([request(1)])
        with self.assertRaisesRegex(AcquisitionPolicyError, "stale"):
            validate_batch_plan(
                self.activation, plan, execution_epoch=EXECUTION_EPOCH + 100_000,
            )


class BatchExecutionTests(unittest.TestCase):
    def test_redirect_is_refused_and_retained_per_url(self) -> None:
        plan = plan_for([request(1), request(2)])
        permit = permit_for(plan)
        transport = FakeTransport(
            permit, statuses={plan["requests"][0]["url"]: 302},
        )
        (report, bodies), _ = execute(plan, transport)
        verify_batch_report(report, plan)
        first, second = report["url_ledger"]
        self.assertEqual("failed", first["outcome"])
        self.assertEqual("redirect_refused", first["failure_code"])
        self.assertEqual("stored_candidate", second["outcome"])
        self.assertEqual(1, len(bodies))
        self.assertEqual(1, report["totals"]["failed"])

    def test_wrong_acknowledgement_or_hash_refuses_everything(self) -> None:
        plan = plan_for([request(1)])
        permit = permit_for(plan)
        transport = FakeTransport(permit)
        with self.assertRaisesRegex(AcquisitionPolicyError, "acknowledgement"):
            execute_batch_plan(
                plan, activation_data=ACTIVATION, activation_evidence_data=EVIDENCE,
                permit=permit, resolver=FakeResolver(permit), transport=transport,
                execution_epoch=EXECUTION_EPOCH,
                network_acknowledgement="wrong",
                confirmed_plan_hash=plan["content_hash"],
            )
        with self.assertRaisesRegex(AcquisitionPolicyError, "hash_confirmation"):
            execute_batch_plan(
                plan, activation_data=ACTIVATION, activation_evidence_data=EVIDENCE,
                permit=permit, resolver=FakeResolver(permit), transport=transport,
                execution_epoch=EXECUTION_EPOCH,
                network_acknowledgement=BATCH_ACKNOWLEDGEMENT,
                confirmed_plan_hash="sha256:" + "0" * 64,
            )
        self.assertEqual([], transport.requests)

    def test_tampered_report_accounting_is_detected(self) -> None:
        plan = plan_for([request(1)])
        (report, _), _ = execute(plan)
        changed = copy.deepcopy(report)
        changed["totals"]["stored"] = 2
        changed["content_hash"] = canonical_hash({
            key: value for key, value in changed.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "accounting"):
            verify_batch_report(changed, plan)

    def test_report_never_claims_discovery_authorized_acquisition(self) -> None:
        plan = plan_for([request(1)])
        (report, _), _ = execute(plan)
        self.assertFalse(report["acquisition_authorized_by_discovery"])

    def test_each_request_is_bounded_by_remaining_run_bytes(self) -> None:
        plan = plan_for([request(1), request(2)])
        (report, _), transport = execute(plan)
        verify_batch_report(report, plan)
        scope = load_batch_activation(ACTIVATION, EVIDENCE)["scope"]
        first_bytes = report["url_ledger"][0]["body_bytes"]
        self.assertEqual(
            scope["max_response_bytes_per_request"],
            transport.requests[0].max_body_bytes,
        )
        self.assertEqual(
            min(
                scope["max_response_bytes_per_request"],
                scope["max_response_bytes_per_run"] - first_bytes,
            ),
            transport.requests[1].max_body_bytes,
        )

    def test_rehashed_report_cannot_exceed_response_byte_budgets(self) -> None:
        plan = plan_for([request(1)])
        (report, _), _ = execute(plan)
        changed = copy.deepcopy(report)
        changed["url_ledger"][0]["body_bytes"] = 33_554_433
        changed["totals"]["body_bytes"] = 33_554_433
        changed["content_hash"] = canonical_hash({
            key: value for key, value in changed.items() if key != "content_hash"
        })
        with self.assertRaisesRegex(ValueError, "per-request byte budget"):
            verify_batch_report(changed, plan)


if __name__ == "__main__":
    unittest.main()
