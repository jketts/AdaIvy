"""Human-authorized, fail-closed evidence harness for the Phase 4B live port.

Importing this module performs no network operation.  An executed gate requires
the concrete opt-in resolver and HTTPS transport, both bound to the exact same
human-final permit.  Reports contain hashes and counts, never response bodies,
raw URLs, addresses, actor identities, or request header values.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .acquisition import (
    AcquisitionPolicy, AcquisitionPolicyError, AcquisitionRequest,
    AuthorizedResource, MAX_BODY_BYTES, MAX_REDIRECTS, MAX_RESOLVED_ADDRESSES,
    MAX_RETRIES, MAX_SOURCES, RightsDecision, RobotsSnapshot, RunAuthorization,
    StartClock, TermsSnapshot, acquire, canonical_url,
)
from .live_transport import (
    LiveNetworkPermit, OptInHttpsTransport, OptInSystemResolver,
)
from .serialization import canonical_bytes, canonical_hash, sha256_bytes


REPORT_SCHEMA = "adaivy.phase4b-live-gate-evidence.v1"
PLAN_SCHEMA = "adaivy.phase4b-live-gate-plan.v1"
MAX_PLAN_BYTES = 262_144
_SECRET_HEADER_NAMES = frozenset(
    {"authorization", "cookie", "proxy-authorization", "x-api-key", "x-auth-token"}
)
_SAFE_REQUEST_HEADER_NAMES = frozenset(
    {"accept", "accept-language", "if-modified-since", "if-none-match", "range"}
)
_SECRET_QUERY_FRAGMENTS = (
    "api_key", "apikey", "auth", "credential", "key", "password", "secret",
    "signature", "token",
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_CLOSED_CODE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,127}$")
_MEDIA_TYPE = re.compile(r"^[a-z0-9!#$&^_.+-]{1,64}/[a-z0-9!#$&^_.+-]{1,64}$")


def _identity_hash(label: str, value: str) -> str:
    return canonical_hash({"kind": label, "value": value})


def _url_is_credential_free(url: str) -> bool:
    for name, _value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        normalized = name.casefold().replace("-", "_")
        if any(fragment in normalized for fragment in _SECRET_QUERY_FRAGMENTS):
            return False
    return True


def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields differ")
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value forbidden: {value}")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class LiveGatePlan:
    permit: LiveNetworkPermit
    authorization: RunAuthorization
    policy: AcquisitionPolicy
    requests: tuple[AcquisitionRequest, ...]
    rights: tuple[RightsDecision, ...]
    terms: tuple[TermsSnapshot, ...]
    robots: tuple[RobotsSnapshot, ...]
    now_epoch: int
    recorded_at_epoch: int

    def __post_init__(self) -> None:
        authorization = self.authorization
        permit = self.permit
        if (
            permit.run_id != authorization.run_id
            or permit.actor_id != authorization.actor_id
            or permit.actor_kind != authorization.actor_kind
            or permit.authority != authorization.authority
            or permit.capability_id != authorization.capability_id
            or permit.approved_origins != authorization.approved_origins
            or permit.network_enabled != authorization.network_enabled
        ):
            raise AcquisitionPolicyError("live_gate_permit_authorization_mismatch")
        if (
            isinstance(self.now_epoch, bool)
            or not isinstance(self.now_epoch, int)
            or self.now_epoch < 0
            or isinstance(self.recorded_at_epoch, bool)
            or not isinstance(self.recorded_at_epoch, int)
            or self.recorded_at_epoch < 0
        ):
            raise AcquisitionPolicyError("live_gate_epoch_invalid")
        if not self.requests:
            raise AcquisitionPolicyError("live_gate_requests_empty")
        for request in self.requests:
            url = canonical_url(request.url)
            if url != request.url or not _url_is_credential_free(url):
                raise AcquisitionPolicyError("live_gate_url_credentials_forbidden")
            for name, _value in request.headers:
                normalized = name.casefold()
                if normalized in _SECRET_HEADER_NAMES:
                    raise AcquisitionPolicyError("live_gate_credential_header_forbidden")
                if normalized not in _SAFE_REQUEST_HEADER_NAMES:
                    raise AcquisitionPolicyError("live_gate_request_header_not_allowed")


def live_gate_plan_value(plan: LiveGatePlan) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA,
        "permit": {
            "run_id": plan.permit.run_id, "actor_id": plan.permit.actor_id,
            "actor_kind": plan.permit.actor_kind, "authority": plan.permit.authority,
            "capability_id": plan.permit.capability_id,
            "approved_origins": list(plan.permit.approved_origins),
            "network_enabled": plan.permit.network_enabled,
        },
        "policy": plan.policy.value(),
        "authorization": {
            "run_id": plan.authorization.run_id,
            "actor_id": plan.authorization.actor_id,
            "actor_kind": plan.authorization.actor_kind,
            "authority": plan.authorization.authority,
            "capability_id": plan.authorization.capability_id,
            "operation": plan.authorization.operation,
            "network_enabled": plan.authorization.network_enabled,
            "policy_hash": plan.authorization.policy_hash,
            "approved_origins": list(plan.authorization.approved_origins),
            "resources": [
                {"request_id": item.request_id, "url": item.url}
                for item in plan.authorization.resources
            ],
        },
        "requests": [
            {
                "run_id": item.run_id, "request_id": item.request_id,
                "actor_id": item.actor_id, "url": item.url,
                "headers": [list(header) for header in item.headers],
            }
            for item in plan.requests
        ],
        "rights": [
            {
                "decision_id": item.decision_id, "run_id": item.run_id,
                "url": item.url, "intended_use": item.intended_use,
                "value": item.value, "actor_kind": item.actor_kind,
                "authority": item.authority,
                "valid_from_epoch": item.valid_from_epoch,
                "valid_until_epoch": item.valid_until_epoch,
            }
            for item in plan.rights
        ],
        "terms": [
            {
                "snapshot_id": item.snapshot_id, "origin": item.origin,
                "content_hash": item.content_hash,
                "captured_at_epoch": item.captured_at_epoch, "valid": item.valid,
                "acquisition_allowed": item.acquisition_allowed,
            }
            for item in plan.terms
        ],
        "robots": [
            {
                "snapshot_id": item.snapshot_id, "url": item.url,
                "content_hash": item.content_hash,
                "captured_at_epoch": item.captured_at_epoch, "valid": item.valid,
                "allowed": item.allowed,
            }
            for item in plan.robots
        ],
        "now_epoch": plan.now_epoch,
        "recorded_at_epoch": plan.recorded_at_epoch,
    }
    value["content_hash"] = canonical_hash(value)
    return value


def live_gate_plan_bytes(plan: LiveGatePlan) -> bytes:
    return canonical_bytes(live_gate_plan_value(plan))


def live_gate_plan_hash(plan: LiveGatePlan) -> str:
    """Return the exact content hash an operator must acknowledge to execute."""

    return str(live_gate_plan_value(plan)["content_hash"])


def load_live_gate_plan(data: bytes) -> LiveGatePlan:
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_PLAN_BYTES:
        raise ValueError("live gate plan size invalid")
    try:
        value = json.loads(
            data.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("live gate plan JSON invalid") from error
    root = _exact(value, {
        "schema_version", "permit", "policy", "authorization", "requests",
        "rights", "terms", "robots", "now_epoch", "recorded_at_epoch",
        "content_hash",
    }, "live gate plan")
    if root["schema_version"] != PLAN_SCHEMA:
        raise ValueError("live gate plan schema differs")
    supplied_hash = root["content_hash"]
    preimage = {key: item for key, item in root.items() if key != "content_hash"}
    if supplied_hash != canonical_hash(preimage):
        raise ValueError("live gate plan content hash differs")
    permit_value = _exact(root["permit"], {
        "run_id", "actor_id", "actor_kind", "authority", "capability_id",
        "approved_origins", "network_enabled",
    }, "permit")
    policy_value = _exact(root["policy"], {
        "policy_version", "max_sources", "max_redirects", "max_retries",
        "max_snapshot_age_seconds", "max_header_bytes", "max_body_bytes",
        "max_total_body_bytes", "max_run_milliseconds",
    }, "policy")
    if policy_value["policy_version"] != "phase4b-acquisition-v1":
        raise ValueError("live gate policy version differs")
    policy = AcquisitionPolicy(**{
        key: item for key, item in policy_value.items() if key != "policy_version"
    })
    permit = LiveNetworkPermit(
        permit_value["run_id"], permit_value["actor_id"],
        permit_value["actor_kind"], permit_value["authority"],
        permit_value["capability_id"], tuple(permit_value["approved_origins"]),
        permit_value["network_enabled"],
    )
    auth = _exact(root["authorization"], {
        "run_id", "actor_id", "actor_kind", "authority", "capability_id",
        "operation", "network_enabled", "policy_hash", "approved_origins",
        "resources",
    }, "authorization")
    resources = tuple(
        AuthorizedResource(**_exact(item, {"request_id", "url"}, "resource"))
        for item in auth["resources"]
    )
    authorization = RunAuthorization(
        auth["run_id"], auth["actor_id"], auth["actor_kind"], auth["authority"],
        auth["capability_id"], auth["operation"], auth["network_enabled"],
        auth["policy_hash"], tuple(auth["approved_origins"]), resources,
    )
    requests = tuple(
        AcquisitionRequest(
            item["run_id"], item["request_id"], item["actor_id"], item["url"],
            tuple(tuple(header) for header in item["headers"]),
        )
        for raw in root["requests"]
        for item in [_exact(raw, {"run_id", "request_id", "actor_id", "url", "headers"}, "request")]
    )
    rights = tuple(
        RightsDecision(**_exact(item, {
            "decision_id", "run_id", "url", "intended_use", "value",
            "actor_kind", "authority", "valid_from_epoch", "valid_until_epoch",
        }, "rights decision"))
        for item in root["rights"]
    )
    terms = tuple(
        TermsSnapshot(**_exact(item, {
            "snapshot_id", "origin", "content_hash", "captured_at_epoch", "valid",
            "acquisition_allowed",
        }, "terms snapshot"))
        for item in root["terms"]
    )
    robots = tuple(
        RobotsSnapshot(**_exact(item, {
            "snapshot_id", "url", "content_hash", "captured_at_epoch", "valid",
            "allowed",
        }, "robots snapshot"))
        for item in root["robots"]
    )
    return LiveGatePlan(
        permit, authorization, policy, requests, rights, terms, robots,
        root["now_epoch"], root["recorded_at_epoch"],
    )


def _base_report(plan: LiveGatePlan, status: str) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "execution_status": status,
        "activation_effect": "none",
        "counted_as_phase4b_activation": False,
        "permit": {
            "run_id_hash": _identity_hash("run_id", plan.permit.run_id),
            "actor_id_hash": _identity_hash("actor_id", plan.permit.actor_id),
            "capability_id_hash": _identity_hash(
                "capability_id", plan.permit.capability_id
            ),
            "authority": plan.permit.authority,
            "approved_origin_hashes": [
                _identity_hash("origin", item) for item in plan.permit.approved_origins
            ],
        },
        "policy_hash": "sha256:" + plan.policy.content_hash,
        "request_count": len(plan.requests),
        "semantic_result_hash": None,
        "operational_result_hash": None,
        "outcomes": [],
        "network_evidence": [],
        "candidate_evidence": [],
    }
    report["content_hash"] = canonical_hash(report)
    return report


def not_executed_report(plan: LiveGatePlan) -> dict[str, Any]:
    """Return deterministic evidence that no external operation was attempted."""

    report = _base_report(plan, "not_executed")
    verify_live_gate_report(report)
    return report


def run_live_gate(
    plan: LiveGatePlan,
    *,
    resolver: OptInSystemResolver,
    transport: OptInHttpsTransport,
    start_clock: StartClock,
) -> dict[str, Any]:
    """Execute the exact permit through the real opt-in adapter boundary."""

    if resolver.permit != plan.permit or transport.permit != plan.permit:
        raise AcquisitionPolicyError("live_gate_adapter_permit_mismatch")
    result = acquire(
        plan.requests,
        authorization=plan.authorization,
        policy=plan.policy,
        rights=plan.rights,
        terms=plan.terms,
        robots=plan.robots,
        resolver=resolver,
        transport=transport,
        start_clock=start_clock,
        now_epoch=plan.now_epoch,
        recorded_at_epoch=plan.recorded_at_epoch,
    )
    semantic = json.loads(result.semantic_bytes)
    operational = json.loads(result.operational_bytes)
    outcomes: list[dict[str, Any]] = []
    for item in semantic["results"]:
        outcomes.append(
            {
                "request_id_hash": _identity_hash("request_id", item["request_id"]),
                "outcome": item["outcome"],
                "reason": item.get("reason"),
                "redirect_count": len(item.get("redirects", [])),
            }
        )
    operations: list[dict[str, Any]] = []
    for item in operational["operations"]:
        common = {
            "request_id_hash": _identity_hash("request_id", item["request_id"]),
            "url_hash": _identity_hash("url", item["url"]),
            "retry": item.get("retry"),
        }
        if "policy_failure" in item:
            operations.append({
                **common, "kind": "policy_failure",
                "failure_code": item["policy_failure"],
            })
        elif "transport_failure" in item:
            operations.append({
                **common, "kind": "transport_failure",
                "failure_code": item["transport_failure"],
            })
        else:
            addresses = item["resolved_addresses"]
            peer = item["connected_peer"]
            operations.append({
                **common, "kind": "http_response", "status": item["status"],
                "resolved_address_hashes": [
                    _identity_hash("address", address) for address in addresses
                ],
                "connected_peer_hash": _identity_hash("address", peer),
                "connected_peer_in_resolved_set": peer in addresses,
            })
    candidates = [
        {
            "request_id_hash": _identity_hash("request_id", item.request_id),
            "source_url_hash": _identity_hash("url", item.source_url),
            "content_sha256": "sha256:" + item.content_sha256,
            "byte_length": len(item.body),
            "media_type": item.media_type,
            "disposition": item.disposition,
            "mathematical_warrant": item.mathematical_warrant,
        }
        for item in result.candidates
    ]
    report = _base_report(plan, "executed")
    report.update(
        {
            "semantic_result_hash": "sha256:" + result.semantic_hash,
            "operational_result_hash": "sha256:" + result.operational_hash,
            "outcomes": outcomes,
            "network_evidence": operations,
            "candidate_evidence": candidates,
        }
    )
    report["content_hash"] = canonical_hash(
        {key: value for key, value in report.items() if key != "content_hash"}
    )
    # This is a defense-in-depth assertion over the persisted representation.
    # Request header values, bodies, URLs and addresses are never inserted above.
    canonical_bytes(report)
    verify_live_gate_report(report)
    return report


def verify_live_gate_report(report: dict[str, Any]) -> None:
    expected = {
        "schema_version", "execution_status", "activation_effect",
        "counted_as_phase4b_activation", "permit", "policy_hash", "request_count",
        "semantic_result_hash", "operational_result_hash", "outcomes",
        "network_evidence", "candidate_evidence", "content_hash",
    }
    if set(report) != expected or report.get("schema_version") != REPORT_SCHEMA:
        raise ValueError("live gate report shape differs")
    supplied = report.get("content_hash")
    preimage = {key: value for key, value in report.items() if key != "content_hash"}
    if supplied != canonical_hash(preimage):
        raise ValueError("live gate report content hash differs")
    if report.get("activation_effect") != "none" or report.get(
        "counted_as_phase4b_activation"
    ) is not False:
        raise ValueError("live gate report cannot activate Phase 4B")
    status = report.get("execution_status")
    if status not in {"not_executed", "executed"}:
        raise ValueError("live gate execution status differs")
    count = report.get("request_count")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_SOURCES:
        raise ValueError("live gate request count invalid")
    if not isinstance(report.get("policy_hash"), str) or _SHA256.fullmatch(report["policy_hash"]) is None:
        raise ValueError("live gate policy hash invalid")
    permit = _exact(report.get("permit"), {
        "run_id_hash", "actor_id_hash", "capability_id_hash", "authority",
        "approved_origin_hashes",
    }, "live gate report permit")
    origins = permit["approved_origin_hashes"]
    if (
        permit["authority"] != "human_final"
        or not isinstance(origins, list)
        or not 1 <= len(origins) <= 4
        or len(set(origins)) != len(origins)
        or any(not isinstance(item, str) or _SHA256.fullmatch(item) is None for item in origins)
        or any(
            not isinstance(permit[field], str) or _SHA256.fullmatch(permit[field]) is None
            for field in ("run_id_hash", "actor_id_hash", "capability_id_hash")
        )
    ):
        raise ValueError("live gate permit evidence invalid")
    outcomes = report.get("outcomes")
    operations = report.get("network_evidence")
    candidates = report.get("candidate_evidence")
    if not all(isinstance(item, list) for item in (outcomes, operations, candidates)):
        raise ValueError("live gate evidence collections invalid")
    if status == "not_executed":
        if (
            report.get("semantic_result_hash") is not None
            or report.get("operational_result_hash") is not None
            or outcomes or operations or candidates
        ):
            raise ValueError("not-executed live gate contains execution evidence")
        return
    for field in ("semantic_result_hash", "operational_result_hash"):
        value = report.get(field)
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise ValueError(f"live gate {field} invalid")
    if len(outcomes) != count or len(candidates) > count:
        raise ValueError("live gate outcome cardinality invalid")
    request_hashes: set[str] = set()
    for raw in outcomes:
        item = _exact(raw, {
            "request_id_hash", "outcome", "reason", "redirect_count",
        }, "live gate outcome")
        request_hash = item["request_id_hash"]
        redirect_count = item["redirect_count"]
        reason = item["reason"]
        if (
            not isinstance(request_hash, str) or _SHA256.fullmatch(request_hash) is None
            or request_hash in request_hashes
            or item["outcome"] not in {"candidate_acquired", "failed"}
            or isinstance(redirect_count, bool) or not isinstance(redirect_count, int)
            or not 0 <= redirect_count <= MAX_REDIRECTS
            or (reason is not None and (
                not isinstance(reason, str) or _CLOSED_CODE.fullmatch(reason) is None
            ))
            or (item["outcome"] == "candidate_acquired" and reason is not None)
            or (item["outcome"] == "failed" and reason is None)
        ):
            raise ValueError("live gate outcome evidence invalid")
        request_hashes.add(request_hash)
    maximum_operations = count * (MAX_REDIRECTS + 1) * (MAX_RETRIES + 1)
    if len(operations) > maximum_operations:
        raise ValueError("live gate operation count invalid")
    typed_operations: list[dict[str, Any]] = []
    common_fields = {"kind", "request_id_hash", "url_hash", "retry"}
    for raw in operations:
        if not isinstance(raw, dict):
            raise ValueError("live gate network evidence is not a mapping")
        kind = raw.get("kind")
        fields = (
            common_fields | {"failure_code"}
            if kind in {"policy_failure", "transport_failure"}
            else common_fields | {
                "status", "resolved_address_hashes", "connected_peer_hash",
                "connected_peer_in_resolved_set",
            }
            if kind == "http_response"
            else set()
        )
        if not fields:
            raise ValueError("live gate operation kind invalid")
        item = dict(_exact(raw, fields, "live gate network evidence"))
        retry = item["retry"]
        if (
            item["request_id_hash"] not in request_hashes
            or not isinstance(item["url_hash"], str) or _SHA256.fullmatch(item["url_hash"]) is None
            or (retry is not None and (
                isinstance(retry, bool) or not isinstance(retry, int) or not 0 <= retry <= MAX_RETRIES
            ))
        ):
            raise ValueError("live gate network evidence invalid")
        if kind == "policy_failure":
            if retry is not None and not isinstance(retry, int):
                raise ValueError("live gate policy operation retry invalid")
        if kind in {"policy_failure", "transport_failure"}:
            value = item["failure_code"]
            if not isinstance(value, str) or _CLOSED_CODE.fullmatch(value) is None:
                raise ValueError("live gate failure evidence invalid")
            if kind == "transport_failure" and (
                retry is None
                or value not in {"transport_failure", "transport_adapter_error"}
            ):
                raise ValueError("live gate transport failure evidence invalid")
        else:
            addresses = item["resolved_address_hashes"]
            http_status = item["status"]
            peer = item["connected_peer_hash"]
            if (
                not isinstance(addresses, list)
                or not 1 <= len(addresses) <= MAX_RESOLVED_ADDRESSES
                or len(set(addresses)) != len(addresses)
                or any(not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in addresses)
                or isinstance(http_status, bool) or not isinstance(http_status, int)
                or not 100 <= http_status <= 599
                or retry is None
                or not isinstance(peer, str) or _SHA256.fullmatch(peer) is None
                or peer not in addresses
                or item["connected_peer_in_resolved_set"] is not True
            ):
                raise ValueError("live gate HTTP response evidence invalid")
        typed_operations.append(item)
    candidate_request_hashes: set[str] = set()
    for raw in candidates:
        item = _exact(raw, {
            "request_id_hash", "source_url_hash", "content_sha256", "byte_length",
            "media_type", "disposition", "mathematical_warrant",
        }, "live gate candidate evidence")
        length = item["byte_length"]
        if (
            item["request_id_hash"] not in request_hashes
            or not isinstance(item["source_url_hash"], str) or _SHA256.fullmatch(item["source_url_hash"]) is None
            or not isinstance(item["content_sha256"], str) or _SHA256.fullmatch(item["content_sha256"]) is None
            or isinstance(length, bool) or not isinstance(length, int) or not 0 <= length <= MAX_BODY_BYTES
            or not isinstance(item["media_type"], str) or _MEDIA_TYPE.fullmatch(item["media_type"]) is None
            or item["disposition"] != "untrusted_candidate"
            or item["mathematical_warrant"] != "none"
            or item["request_id_hash"] in candidate_request_hashes
        ):
            raise ValueError("live gate candidate evidence invalid")
        candidate_request_hashes.add(item["request_id_hash"])
    successful_request_hashes = {
        item["request_id_hash"]
        for item in outcomes
        if item["outcome"] == "candidate_acquired"
    }
    if candidate_request_hashes != successful_request_hashes:
        raise ValueError("live gate outcome and candidate evidence differ")
    candidates_by_request = {
        item["request_id_hash"]: item for item in candidates
    }
    operations_by_request: dict[str, list[dict[str, Any]]] = {
        request_hash: [] for request_hash in request_hashes
    }
    for item in typed_operations:
        operations_by_request[item["request_id_hash"]].append(item)
    if any(not values for values in operations_by_request.values()):
        raise ValueError("live gate outcome lacks network or policy evidence")
    redirect_statuses = {301, 302, 303, 307, 308}
    redirect_input_failures = {
        "url_length_invalid", "url_ambiguous", "https_required",
        "url_authority_invalid", "url_port_invalid", "url_host_invalid",
        "url_host_must_be_ascii", "url_dot_segment_forbidden",
    }
    for outcome in outcomes:
        request_hash = outcome["request_id_hash"]
        request_operations = operations_by_request[request_hash]
        terminal = request_operations[-1]
        for preceding in request_operations[:-1]:
            if preceding["kind"] == "policy_failure" or (
                preceding["kind"] == "http_response"
                and preceding["status"] not in redirect_statuses
                and preceding["status"] not in {408, 429}
                and not 500 <= preceding["status"] <= 599
            ):
                raise ValueError("live gate operation sequence has nonterminal result")
        response_redirects = sum(
            item["kind"] == "http_response" and item["status"] in redirect_statuses
            for item in request_operations
        )
        reason = outcome["reason"]
        expected_redirects = outcome["redirect_count"]
        if outcome["outcome"] == "candidate_acquired":
            if (
                terminal["kind"] != "http_response"
                or not 200 <= terminal["status"] <= 299
                or response_redirects != expected_redirects
                or any(item["kind"] == "policy_failure" for item in request_operations)
                or candidates_by_request[request_hash]["source_url_hash"]
                != terminal["url_hash"]
            ):
                raise ValueError("live gate success lacks terminal clean peer-bound 2xx")
            continue
        if terminal["kind"] == "policy_failure":
            consistent = reason == terminal["failure_code"]
            redirect_delta = 0
        elif terminal["kind"] == "transport_failure":
            consistent = reason == "retry_exhausted_transport"
            redirect_delta = 0
        else:
            terminal_status = terminal["status"]
            if reason == "retry_exhausted_status":
                consistent = terminal_status in {408, 429} or 500 <= terminal_status <= 599
                redirect_delta = 0
            elif reason == "http_status":
                consistent = (
                    not 200 <= terminal_status <= 299
                    and terminal_status not in redirect_statuses
                    and terminal_status not in {408, 429}
                    and not 500 <= terminal_status <= 599
                )
                redirect_delta = 0
            elif reason == "redirect_cycle":
                consistent = terminal_status in redirect_statuses and expected_redirects > 0
                redirect_delta = 0
            elif reason in {
                "redirect_location_missing", "redirect_limit_exhausted",
            } | redirect_input_failures:
                consistent = terminal_status in redirect_statuses
                redirect_delta = 1
            else:
                consistent = False
                redirect_delta = 0
        if not consistent or response_redirects != expected_redirects + redirect_delta:
            raise ValueError("live gate failure terminal evidence inconsistent")


__all__ = [
    "LiveGatePlan", "MAX_PLAN_BYTES", "PLAN_SCHEMA", "REPORT_SCHEMA",
    "live_gate_plan_bytes", "live_gate_plan_hash", "live_gate_plan_value",
    "load_live_gate_plan", "not_executed_report", "run_live_gate",
    "verify_live_gate_report",
]
