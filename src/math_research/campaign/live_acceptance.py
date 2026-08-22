"""Fail-closed Slice 16 live end-to-end acceptance gate definition."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..corpus_service.serialization import strict_canonical_object
from .records import canonical_hash

LIVE_ACCEPTANCE_SCHEMA = "adaivy.campaign-live-acceptance-gate.v1"
LIVE_ACCEPTANCE_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_LIVE_END_TO_END_CAMPAIGN"
_FIELDS = frozenset({
    "schema_version", "gate_id", "status", "provider", "model_identifier",
    "target_id", "action_schema", "budget", "retry_policy",
    "required_gate_evidence", "required_human_checkpoint", "content_hash",
})
_BUDGET_FIELDS = frozenset({
    "max_model_requests", "max_embedding_requests", "max_network_requests",
    "max_tool_runs", "max_storage_bytes", "max_wall_milliseconds",
})
_RETRY_FIELDS = frozenset({
    "retryable_http_statuses", "initial_backoff_milliseconds",
    "maximum_backoff_milliseconds", "max_retries", "jitter",
})


class LiveAcceptanceGateError(ValueError):
    pass


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise LiveAcceptanceGateError("live acceptance configuration contains a float")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, list):
        for item in value:
            _reject_floats(item)


def load_live_acceptance_gate(path: Path) -> dict[str, Any]:
    value = strict_canonical_object(
        path.read_bytes(), maximum=1_048_576,
        label="campaign live acceptance gate",
        code="campaign_live_acceptance_gate_invalid",
    )
    _reject_floats(value)
    if set(value) != _FIELDS or value["schema_version"] != LIVE_ACCEPTANCE_SCHEMA:
        raise LiveAcceptanceGateError("live acceptance gate fields differ")
    supplied = value["content_hash"]
    if supplied != canonical_hash({key: item for key, item in value.items() if key != "content_hash"}):
        raise LiveAcceptanceGateError("live acceptance gate content hash differs")
    if value["status"] not in {"pending_operator_activation", "active"}:
        raise LiveAcceptanceGateError("live acceptance gate status differs")
    if value["provider"] != "azure_openai" or not isinstance(value["model_identifier"], str):
        raise LiveAcceptanceGateError("live acceptance provider binding differs")
    if value["action_schema"] != "schemas/model-campaign-action-v2.schema.json":
        raise LiveAcceptanceGateError("live acceptance action schema differs")
    budget = value["budget"]
    if not isinstance(budget, dict) or set(budget) != _BUDGET_FIELDS:
        raise LiveAcceptanceGateError("live acceptance budget fields differ")
    if any(not isinstance(item, int) or isinstance(item, bool) or item < 1 for item in budget.values()):
        raise LiveAcceptanceGateError("live acceptance budgets must be positive integers")
    retry = value["retry_policy"]
    if not isinstance(retry, dict) or set(retry) != _RETRY_FIELDS:
        raise LiveAcceptanceGateError("live acceptance retry policy fields differ")
    if retry != {
        "retryable_http_statuses": [408, 409, 429, 500, 502, 503, 504],
        "initial_backoff_milliseconds": 2_000,
        "maximum_backoff_milliseconds": 60_000,
        "max_retries": 4,
        "jitter": "none_deterministic",
    }:
        raise LiveAcceptanceGateError("live acceptance retry policy differs")
    evidence = value["required_gate_evidence"]
    if not isinstance(evidence, list) or len(evidence) != len(set(evidence)) or not evidence:
        raise LiveAcceptanceGateError("live acceptance evidence list differs")
    if value["required_human_checkpoint"] != "before_announcement":
        raise LiveAcceptanceGateError("before_announcement checkpoint must remain mandatory")
    return value


def assess_live_acceptance_gate(
    gate: Mapping[str, Any], *, execute: bool, acknowledgement: str,
    evidence_directory: Path | None,
) -> dict[str, Any]:
    """Return a truthful readiness record; this function performs no effects."""

    missing: list[str] = []
    invalid: list[str] = []
    if evidence_directory is None:
        missing = list(gate["required_gate_evidence"])
    else:
        for name in gate["required_gate_evidence"]:
            path = evidence_directory / f"{name}.json"
            if not path.is_file():
                missing.append(name)
                continue
            try:
                record = strict_canonical_object(
                    path.read_bytes(), maximum=16_777_216,
                    label=f"live gate evidence {name}", code="live_gate_evidence_invalid",
                )
                supplied = record.get("content_hash")
                core = {key: item for key, item in record.items() if key != "content_hash"}
                if supplied != canonical_hash(core) or (
                    record.get("status") not in {"passed", "completed", "active"}
                    and record.get("probe_status") != "passed"
                ):
                    invalid.append(name)
            except (OSError, TypeError, ValueError):
                invalid.append(name)
    activated = gate["status"] == "active"
    acknowledged = acknowledgement == LIVE_ACCEPTANCE_ACKNOWLEDGEMENT
    ready = execute and activated and acknowledged and not missing and not invalid
    reason = None
    if not execute:
        reason = "live_execution_not_requested"
    elif not activated:
        reason = "live_acceptance_pending_operator_activation"
    elif not acknowledged:
        reason = "live_acceptance_not_acknowledged"
    elif missing:
        reason = "live_acceptance_evidence_missing"
    elif invalid:
        reason = "live_acceptance_evidence_invalid"
    return {
        "schema_version": "adaivy.campaign-live-acceptance-readiness.v1",
        "gate_hash": gate["content_hash"],
        "status": "ready_for_live_execution" if ready else "not_executed",
        "reason": reason, "missing_gate_evidence": missing,
        "invalid_gate_evidence": invalid,
        "provider_requests_made": 0, "network_requests": 0,
        "retry_policy": gate["retry_policy"],
        "before_announcement_human_checkpoint_required": True,
        "epistemic_warrant_created": False,
    }


__all__ = [
    "LIVE_ACCEPTANCE_ACKNOWLEDGEMENT", "LIVE_ACCEPTANCE_SCHEMA",
    "LiveAcceptanceGateError", "assess_live_acceptance_gate",
    "load_live_acceptance_gate",
]
