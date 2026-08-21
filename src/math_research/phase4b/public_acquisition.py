"""Owner-activated public, unauthenticated Phase 4B acquisition.

This module activates only the already-gated HTTPS port.  It does not select
origins, crawl links, use credentials, or infer rights from public visibility.
Every execution remains bound to one human-final ``LiveGatePlan`` and stores
bytes only through :class:`Phase4BService`'s deletable content boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any
from urllib.parse import urlsplit

from ..phase4a.records import RecordType as Phase4ARecordType
from ..phase4a.records import RightsReason, RightsUse, RightsValue
from .acquisition import AcquisitionPolicyError, origin_for
from .live_gate import LiveGatePlan, live_gate_plan_hash
from .serialization import canonical_bytes, canonical_hash
from .service import Phase4BService, StoredAcquisition


ACTIVATION_SCHEMA = "adaivy.phase4b-public-acquisition-activation.v1"
ACTIVATION_HASH = (
    "sha256:cd4ecd460e32e9d1ff285827ab1f9a2bd2fb1996bfd91d32ca2c2581a977711d"
)
ACTIVATION_EVIDENCE_SCHEMA = "adaivy.phase4b-activation-evidence.v1"
ACTIVATION_EVIDENCE_HASH = (
    "sha256:e85fe8de43fe325bd47b8e48bf244e52c123b2416c2a1f92d88e49c82d0dff0b"
)
CAPABILITY_ID = "capability.phase4b.live"
LIVE_NETWORK_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_PHASE4B_LIVE_NETWORK"
MAX_ACTIVATION_BYTES = 32_768
MAX_EVIDENCE_BYTES = 65_536
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate activation key")
        value[key] = item
    return value


def _canonical_object(data: bytes, maximum: int, label: str) -> dict[str, Any]:
    if not isinstance(data, bytes) or not data or len(data) > maximum:
        raise ValueError(f"{label} byte bound differs")
    try:
        value = json.loads(
            data.decode("utf-8", "strict"), object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value forbidden: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} JSON is invalid") from error
    if not isinstance(value, dict) or data not in {
        canonical_bytes(value), canonical_bytes(value) + b"\n",
    }:
        raise ValueError(f"{label} is not canonical")
    return value


def _verify_evidence(value: dict[str, Any]) -> None:
    if value.get("schema_version") != ACTIVATION_EVIDENCE_SCHEMA:
        raise ValueError("activation evidence schema differs")
    if (
        value.get("status") != "evidence_complete_pending_owner_activation"
        or value.get("activation_effect") != "none"
        or value.get("production_activated") is not False
    ):
        raise ValueError("activation evidence is not the completed pre-activation record")
    supplied = value.get("content_hash")
    if supplied != ACTIVATION_EVIDENCE_HASH or _SHA256.fullmatch(str(supplied)) is None:
        raise ValueError("activation evidence identity differs")
    preimage = {key: item for key, item in value.items() if key != "content_hash"}
    if canonical_hash(preimage) != supplied:
        raise ValueError("activation evidence content hash differs")


def load_public_activation(
    activation_data: bytes, activation_evidence_data: bytes,
) -> dict[str, Any]:
    """Load the exact owner decision and bind it to the completed gate evidence."""

    activation = _canonical_object(
        activation_data, MAX_ACTIVATION_BYTES, "public acquisition activation"
    )
    evidence = _canonical_object(
        activation_evidence_data, MAX_EVIDENCE_BYTES, "Phase 4B activation evidence"
    )
    _verify_evidence(evidence)
    expected = {
        "schema_version", "status", "activated_at", "activated_by",
        "capability_id", "scope", "activation_evidence", "content_hash",
    }
    if set(activation) != expected:
        raise ValueError("public acquisition activation fields differ")
    supplied = activation.get("content_hash")
    if supplied != ACTIVATION_HASH or _SHA256.fullmatch(str(supplied)) is None:
        raise ValueError("public acquisition activation identity differs")
    preimage = {key: item for key, item in activation.items() if key != "content_hash"}
    if canonical_hash(preimage) != supplied:
        raise ValueError("public acquisition activation hash differs")
    actor = activation.get("activated_by")
    scope = activation.get("scope")
    evidence_ref = activation.get("activation_evidence")
    if (
        activation.get("status") != "active"
        or activation.get("capability_id") != CAPABILITY_ID
        or not isinstance(activation.get("activated_at"), str)
        or actor != {
            "actor_id": "human.repository-owner",
            "actor_kind": "human",
            "authority": "human_final",
        }
        or scope != {
            "access_mode": "public_unauthenticated",
            "autonomous_origin_selection": False,
            "credentials_allowed": False,
            "crawler_enabled": False,
            "http_methods": ["GET"],
            "max_origins_per_run": 1,
            "max_plan_age_seconds": 300,
            "max_requests_per_run": 1,
            "network_default": "disabled",
            "per_run_human_final_plan_required": True,
            "per_run_operator_acknowledgement_required": True,
            "query_strings_allowed": False,
            "redirects_allowed": False,
            "request_headers_allowed": [],
        }
        or evidence_ref != {
            "content_hash": ACTIVATION_EVIDENCE_HASH,
            "schema_version": ACTIVATION_EVIDENCE_SCHEMA,
        }
    ):
        raise ValueError("public acquisition activation scope differs")
    return activation


def validate_public_plan(plan: LiveGatePlan) -> None:
    """Enforce the activated subset before a resolver or transport can run."""

    if plan.permit.capability_id != CAPABILITY_ID:
        raise AcquisitionPolicyError("public_acquisition_capability_invalid")
    if len(plan.requests) != 1 or len(plan.authorization.resources) != 1:
        raise AcquisitionPolicyError("public_acquisition_requires_one_exact_url")
    request = plan.requests[0]
    resource = plan.authorization.resources[0]
    expected_origin = origin_for(request.url)
    if (
        resource.request_id != request.request_id
        or resource.url != request.url
        or plan.permit.approved_origins != (expected_origin,)
    ):
        raise AcquisitionPolicyError("public_acquisition_exact_resource_mismatch")
    if urlsplit(request.url).query:
        raise AcquisitionPolicyError("public_acquisition_query_forbidden")
    if request.headers:
        raise AcquisitionPolicyError("public_acquisition_headers_forbidden")
    if plan.policy.max_retries != 0:
        raise AcquisitionPolicyError("public_acquisition_retries_forbidden")
    if plan.policy.max_redirects != 0:
        raise AcquisitionPolicyError("public_acquisition_redirects_forbidden")
    if (
        len(plan.terms) != 1
        or plan.terms[0].origin != expected_origin
        or len(plan.robots) != 1
        or plan.robots[0].url != request.url
    ):
        raise AcquisitionPolicyError("public_acquisition_evidence_envelope_mismatch")
    rights = {(item.url, item.intended_use): item for item in plan.rights}
    required_rights = {
        (request.url, "acquisition"),
        (request.url, "storage_and_retention"),
    }
    if len(plan.rights) != 2 or set(rights) != required_rights:
        raise AcquisitionPolicyError("public_acquisition_rights_invalid")
    for decision in rights.values():
        if (
            decision.run_id != plan.authorization.run_id
            or decision.value != "allowed"
            or decision.actor_kind != "human"
            or decision.authority != "human_final"
            or decision.valid_from_epoch > plan.now_epoch
            or (
                decision.valid_until_epoch is not None
                and plan.now_epoch > decision.valid_until_epoch
            )
        ):
            raise AcquisitionPolicyError("public_acquisition_rights_invalid")


def recorded_at(plan: LiveGatePlan) -> str:
    """Derive the durable timestamp from the content-hashed plan, not a clock read."""

    return datetime.fromtimestamp(plan.recorded_at_epoch, timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _epoch_timestamp(value: int) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _ensure_phase4a_rights(
    service: Phase4BService, source_id: str, plan: LiveGatePlan,
) -> None:
    rights = service.rights
    timestamp = recorded_at(plan)
    records = rights.workspace.records()
    policies = [
        item for item in records
        if item["record_type"] == Phase4ARecordType.POLICY_SNAPSHOT.value
    ]
    if not records:
        rights.initialize_policy(actor_id=plan.authorization.actor_id, recorded_at=timestamp)
    elif len(policies) != 1:
        raise ValueError("public acquisition workspace lacks exactly one Phase 4A policy")
    plan_hash = live_gate_plan_hash(plan)
    evidence_refs = (
        "evidence.phase4b-public-activation." + ACTIVATION_HASH.removeprefix("sha256:"),
        "evidence.phase4b-public-plan." + plan_hash.removeprefix("sha256:"),
    )
    plan_rights = {
        item.intended_use: item
        for item in plan.rights
        if item.url == plan.requests[0].url
    }
    decisions_to_record: list[tuple[RightsUse, RightsDecision]] = []
    for use in (RightsUse.ACQUISITION, RightsUse.STORAGE_AND_RETENTION):
        evaluation = rights.evaluate_rights(source_id, use, at=timestamp)
        prior = [
            item for item in rights.workspace.records()
            if item["record_type"] == Phase4ARecordType.RIGHTS_DECISION.value
            and item["subject_id"] == source_id
            and item["payload"]["intended_use"] == use.value
        ]
        if prior and not evaluation.allowed:
            raise AcquisitionPolicyError("public_acquisition_existing_rights_block")
        decisions_to_record.append((use, plan_rights[use.value]))
    for use, decision in decisions_to_record:
        rights.append_rights(
            source_id=source_id,
            intended_use=use,
            value=RightsValue.ALLOWED,
            reason_code=RightsReason.PERMITTED,
            reason_detail=(
                "human-final public unauthenticated Phase 4B plan permits this exact use"
            ),
            evidence_refs=evidence_refs,
            actor_id=plan.authorization.actor_id,
            valid_from=_epoch_timestamp(decision.valid_from_epoch),
            valid_until=(
                None
                if decision.valid_until_epoch is None
                else _epoch_timestamp(decision.valid_until_epoch)
            ),
            recorded_at=timestamp,
            lifecycle_id=f"rights-lifecycle.phase4b-public.{use.value}",
        )


def acquire_public_plan(
    service: Phase4BService,
    source_id: str,
    plan: LiveGatePlan,
    *,
    activation_data: bytes,
    activation_evidence_data: bytes,
    execution_epoch: int,
    resolver: Any,
    transport: Any,
    start_clock: Any,
    network_acknowledgement: str,
    confirmed_plan_hash: str,
) -> StoredAcquisition:
    """Execute one activated plan through the authoritative persistence service."""

    load_public_activation(activation_data, activation_evidence_data)
    validate_public_plan(plan)
    if network_acknowledgement != LIVE_NETWORK_ACKNOWLEDGEMENT:
        raise AcquisitionPolicyError("public_acquisition_acknowledgement_required")
    if confirmed_plan_hash != live_gate_plan_hash(plan):
        raise AcquisitionPolicyError("public_acquisition_plan_hash_confirmation_invalid")
    if (
        isinstance(execution_epoch, bool)
        or not isinstance(execution_epoch, int)
        or abs(execution_epoch - plan.now_epoch) > 300
        or plan.recorded_at_epoch != plan.now_epoch
    ):
        raise AcquisitionPolicyError("public_acquisition_plan_stale")
    if resolver.permit != plan.permit or transport.permit != plan.permit:
        raise AcquisitionPolicyError("public_acquisition_adapter_permit_mismatch")
    _ensure_phase4a_rights(service, source_id, plan)
    return service.acquire(
        source_id,
        plan.requests,
        authorization=plan.authorization,
        policy=plan.policy,
        terms=plan.terms,
        robots=plan.robots,
        resolver=resolver,
        transport=transport,
        start_clock=start_clock,
        now_epoch=plan.now_epoch,
        recorded_at_epoch=plan.recorded_at_epoch,
        recorded_at=recorded_at(plan),
    )


__all__ = [
    "ACTIVATION_EVIDENCE_HASH", "ACTIVATION_HASH", "ACTIVATION_SCHEMA", "CAPABILITY_ID",
    "LIVE_NETWORK_ACKNOWLEDGEMENT", "MAX_ACTIVATION_BYTES", "MAX_EVIDENCE_BYTES", "acquire_public_plan",
    "load_public_activation", "recorded_at", "validate_public_plan",
]
