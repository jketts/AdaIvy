"""Slice 16 gate-definition acceptance tests; all paths are offline."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from math_research.campaign.live_acceptance import (
    LIVE_ACCEPTANCE_ACKNOWLEDGEMENT,
    LiveAcceptanceGateError,
    assess_live_acceptance_gate,
    load_live_acceptance_gate,
)
from math_research.campaign.records import canonical_bytes, canonical_hash
from math_research.phase2.live_config import load_live_run_configuration


ROOT = Path(__file__).resolve().parents[1]


class LiveAcceptanceGateTests(unittest.TestCase):
    def test_shipped_gate_is_sealed_pending_and_performs_no_effects(self) -> None:
        gate = load_live_acceptance_gate(ROOT / "config/campaign-live-acceptance-v1.json")
        result = assess_live_acceptance_gate(
            gate, execute=True,
            acknowledgement=LIVE_ACCEPTANCE_ACKNOWLEDGEMENT,
            evidence_directory=None,
        )
        self.assertEqual("not_executed", result["status"])
        self.assertEqual("live_acceptance_pending_operator_activation", result["reason"])
        self.assertEqual(0, result["provider_requests_made"])
        self.assertEqual(0, result["network_requests"])
        self.assertEqual(4, result["retry_policy"]["max_retries"])
        live = load_live_run_configuration(
            ROOT / "config/campaign-live-azure-openai-v2.json"
        )
        self.assertEqual(16, live.budget.max_attempts)
        self.assertEqual(8_192, live.per_call_output_token_reserve)

    def test_tamper_and_float_configuration_refuse(self) -> None:
        original = json.loads(
            (ROOT / "config/campaign-live-acceptance-v1.json").read_text()
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gate.json"
            tampered = dict(original)
            tampered["budget"] = dict(tampered["budget"])
            tampered["budget"]["max_model_requests"] = 33
            path.write_bytes(canonical_bytes(tampered) + b"\n")
            with self.assertRaisesRegex(LiveAcceptanceGateError, "content hash"):
                load_live_acceptance_gate(path)

            floated = dict(original)
            floated["budget"] = dict(floated["budget"])
            floated["budget"]["max_model_requests"] = 32.0
            floated["content_hash"] = canonical_hash({
                key: item for key, item in floated.items() if key != "content_hash"
            })
            path.write_bytes(canonical_bytes(floated) + b"\n")
            with self.assertRaisesRegex(LiveAcceptanceGateError, "float"):
                load_live_acceptance_gate(path)

    def test_active_gate_still_requires_ack_and_verified_evidence(self) -> None:
        gate = load_live_acceptance_gate(ROOT / "config/campaign-live-acceptance-v1.json")
        active = dict(gate)
        active["status"] = "active"
        active["content_hash"] = canonical_hash({
            key: item for key, item in active.items() if key != "content_hash"
        })
        no_ack = assess_live_acceptance_gate(
            active, execute=True, acknowledgement="", evidence_directory=ROOT / "absent",
        )
        self.assertEqual("live_acceptance_not_acknowledged", no_ack["reason"])

    def test_rehashed_gate_cannot_remove_evidence_or_raise_budget_ceiling(self) -> None:
        original = json.loads(
            (ROOT / "config/campaign-live-acceptance-v1.json").read_text()
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gate.json"
            for changed in ("evidence", "budget"):
                value = json.loads(json.dumps(original))
                if changed == "evidence":
                    value["required_gate_evidence"].remove("verifier_activation")
                else:
                    value["budget"]["max_network_requests"] = 4_097
                value["content_hash"] = canonical_hash({
                    key: item for key, item in value.items() if key != "content_hash"
                })
                path.write_bytes(canonical_bytes(value) + b"\n")
                with self.assertRaises(LiveAcceptanceGateError):
                    load_live_acceptance_gate(path)
