"""Batch public unauthenticated acquisition under one plan approval (ADR-0081).

The v2 activation permits N allowlisted exact URLs per run under an explicit
request-and-byte budget. The human final approval moves to the *plan* level:
one acknowledgement and one confirmed plan hash cover the whole batch, and the
per-URL discipline is unchanged from ADR-0050 — HTTPS only, no redirects, no
query strings, no request headers, no credentials. Every URL produces its own
ledger record; failures are retained, never retried here.

Fetched bodies are returned to the caller as untrusted candidates for the
existing Phase 4A/4B rights, storage, and parsing path. Nothing here creates
warrant, applicability, novelty, or significance.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

from .acquisition import (
    AcquisitionPolicyError, Resolution, TransportFailure, TransportRequest,
    canonical_url, origin_for,
)
from .public_acquisition import _canonical_object, _verify_evidence
from .serialization import canonical_hash, sha256_bytes

BATCH_ACTIVATION_SCHEMA = "adaivy.phase4b-public-acquisition-activation.v2"
BATCH_ACTIVATION_HASH = "sha256:50066cdcdd1c0b9d5c0413191bdc43cde51550e17334b2cc79716756cdd37ef3"
BATCH_PLAN_SCHEMA = "adaivy.phase4b-batch-acquisition-plan.v2"
BATCH_REPORT_SCHEMA = "adaivy.phase4b-batch-acquisition-report.v2"
BATCH_CAPABILITY_ID = "capability.phase4b.live.batch"
BATCH_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_PHASE4B_BATCH_ACQUISITION"
MAX_BATCH_ACTIVATION_BYTES = 32_768
MAX_BATCH_REQUESTS_CEILING = 32
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUEST_ID = re.compile(r"^req-[a-z0-9][a-z0-9-]{0,62}$")
_HOST = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?)+$")
_DOCUMENT_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_EXPECTED_SCOPE = {
    "access_mode": "public_unauthenticated",
    "credentials_allowed": False,
    "crawler_enabled": False,
    "http_methods": ["GET"],
    "max_origins_per_run": 4,
    "max_plan_age_seconds": 600,
    "max_requests_per_run": 32,
    "max_response_bytes_per_request": 33_554_432,
    "max_response_bytes_per_run": 268_435_456,
    "network_default": "disabled",
    "origin_allowlist_required": True,
    "origin_selection_recorded_per_url": True,
    "per_plan_human_final_approval_required": True,
    "per_url_human_approval_required": False,
    "query_strings_allowed": False,
    "redirects_allowed": False,
    "request_headers_allowed": [],
    "timeout_milliseconds": 30_000,
}


def _reject_floats(value: Any, path: str) -> None:
    if isinstance(value, float):
        raise ValueError(f"batch report contains a float at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


def load_batch_activation(
    activation_data: bytes, activation_evidence_data: bytes,
) -> dict[str, Any]:
    """Load the pinned owner decision that permits batch plans at all."""

    activation = _canonical_object(
        activation_data, MAX_BATCH_ACTIVATION_BYTES, "batch acquisition activation"
    )
    evidence = _canonical_object(
        activation_evidence_data, 65_536, "Phase 4B activation evidence"
    )
    _verify_evidence(evidence)
    expected = {
        "schema_version", "status", "activated_at", "activated_by",
        "capability_id", "scope", "activation_evidence", "content_hash",
    }
    if set(activation) != expected \
            or activation.get("schema_version") != BATCH_ACTIVATION_SCHEMA:
        raise ValueError("batch acquisition activation fields differ")
    supplied = activation.get("content_hash")
    if supplied != BATCH_ACTIVATION_HASH or _SHA256.fullmatch(str(supplied)) is None:
        raise ValueError("batch acquisition activation identity differs")
    if canonical_hash(
        {key: item for key, item in activation.items() if key != "content_hash"}
    ) != supplied:
        raise ValueError("batch acquisition activation hash differs")
    if (
        activation.get("status") != "active"
        or activation.get("capability_id") != BATCH_CAPABILITY_ID
        or not isinstance(activation.get("activated_at"), str)
        or activation.get("activated_by") != {
            "actor_id": "human.repository-owner",
            "actor_kind": "human",
            "authority": "human_final",
        }
        or activation.get("scope") != _EXPECTED_SCOPE
        or activation.get("activation_evidence") != {
            "content_hash": evidence["content_hash"],
            "schema_version": evidence["schema_version"],
        }
    ):
        raise ValueError("batch acquisition activation scope differs")
    return activation


def build_batch_plan(
    *, run_id: str, actor_id: str, approved_at_epoch: int,
    allowlist_hosts: list[str], requests: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the single content-hashed plan a human approves once."""

    value: dict[str, Any] = {
        "schema_version": BATCH_PLAN_SCHEMA,
        "run_id": run_id,
        "approved_by": {
            "actor_id": actor_id, "actor_kind": "human", "authority": "human_final",
        },
        "approved_at_epoch": approved_at_epoch,
        "approval_scope": "plan",
        "origin_allowlist": sorted(set(allowlist_hosts)),
        "requests": requests,
        "rights_basis": "per_url_human_final_in_plan",
    }
    value["content_hash"] = canonical_hash(value)
    return value


def validate_batch_plan(
    activation: dict[str, Any], plan: Any, *, execution_epoch: int,
) -> dict[str, Any]:
    scope = activation["scope"]
    expected = {
        "schema_version", "run_id", "approved_by", "approved_at_epoch",
        "approval_scope", "origin_allowlist", "requests", "rights_basis",
        "content_hash",
    }
    if not isinstance(plan, dict) or set(plan) != expected \
            or plan.get("schema_version") != BATCH_PLAN_SCHEMA:
        raise AcquisitionPolicyError("batch_plan_fields_invalid")
    supplied = plan.get("content_hash")
    if _SHA256.fullmatch(str(supplied)) is None or canonical_hash(
        {key: value for key, value in plan.items() if key != "content_hash"}
    ) != supplied:
        raise AcquisitionPolicyError("batch_plan_identity_invalid")
    if (
        not isinstance(plan.get("run_id"), str)
        or _DOCUMENT_ID.fullmatch(plan["run_id"]) is None
        or plan.get("approval_scope") != "plan"
        or plan.get("rights_basis") != "per_url_human_final_in_plan"
        or not isinstance(plan.get("approved_by"), dict)
        or plan["approved_by"].get("actor_kind") != "human"
        or plan["approved_by"].get("authority") != "human_final"
        or not isinstance(plan["approved_by"].get("actor_id"), str)
        or not plan["approved_by"]["actor_id"].strip()
    ):
        raise AcquisitionPolicyError("batch_plan_approval_invalid")
    approved_at = plan.get("approved_at_epoch")
    if (
        isinstance(approved_at, bool) or not isinstance(approved_at, int)
        or isinstance(execution_epoch, bool) or not isinstance(execution_epoch, int)
        or not 0 <= execution_epoch - approved_at <= scope["max_plan_age_seconds"]
    ):
        raise AcquisitionPolicyError("batch_plan_stale")
    allowlist = plan.get("origin_allowlist")
    if (
        not isinstance(allowlist, list) or not allowlist
        or allowlist != sorted(set(allowlist))
        or any(not isinstance(host, str) or _HOST.fullmatch(host) is None for host in allowlist)
    ):
        raise AcquisitionPolicyError("batch_plan_allowlist_invalid")
    requests = plan.get("requests")
    if not isinstance(requests, list) \
            or not 1 <= len(requests) <= scope["max_requests_per_run"]:
        raise AcquisitionPolicyError("batch_plan_request_count_invalid")
    request_ids: set[str] = set()
    urls: set[str] = set()
    origins: set[str] = set()
    for request in requests:
        if (
            not isinstance(request, dict)
            or set(request) != {"request_id", "url", "origin_selected_by", "provenance", "rights"}
            or not isinstance(request.get("request_id"), str)
            or _REQUEST_ID.fullmatch(request["request_id"]) is None
            or request["request_id"] in request_ids
        ):
            raise AcquisitionPolicyError("batch_plan_request_record_invalid")
        request_ids.add(request["request_id"])
        url = request.get("url")
        if not isinstance(url, str) or url != canonical_url(url) or url in urls:
            raise AcquisitionPolicyError("batch_plan_url_invalid")
        urls.add(url)
        parts = urlsplit(url)
        if parts.query or parts.fragment:
            raise AcquisitionPolicyError("batch_plan_query_string_forbidden")
        if parts.hostname not in set(allowlist):
            raise AcquisitionPolicyError("batch_plan_offlist_origin_refused")
        origins.add(origin_for(url))
        selected_by = request.get("origin_selected_by")
        provenance = request.get("provenance")
        if selected_by == "human":
            if provenance is not None:
                raise AcquisitionPolicyError("batch_plan_origin_selection_invalid")
        elif selected_by == "automation":
            if (
                not isinstance(provenance, dict)
                or set(provenance) != {
                    "origin_document_id", "origin_acquisition_record_id",
                    "reference_field", "reference_index", "reference_value",
                }
            ):
                raise AcquisitionPolicyError("batch_plan_origin_selection_invalid")
        else:
            raise AcquisitionPolicyError("batch_plan_origin_selection_invalid")
        if request.get("rights") != {
            "acquisition": "allowed", "storage_and_retention": "allowed",
        }:
            raise AcquisitionPolicyError("batch_plan_rights_invalid")
    if len(origins) > scope["max_origins_per_run"]:
        raise AcquisitionPolicyError("batch_plan_origin_count_invalid")
    return plan


def _public_addresses(resolution: Resolution, hostname: str) -> tuple[str, ...]:
    if resolution.hostname != hostname or not 1 <= len(resolution.addresses) <= 16:
        raise AcquisitionPolicyError("batch_resolver_identity_invalid")
    result: list[str] = []
    for raw in resolution.addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as error:
            raise AcquisitionPolicyError("batch_resolved_address_invalid") from error
        if not address.is_global or address.is_multicast or address.is_unspecified:
            raise AcquisitionPolicyError("batch_resolved_address_forbidden")
        if address.compressed not in result:
            result.append(address.compressed)
    if not result:
        raise AcquisitionPolicyError("batch_resolved_address_empty")
    return tuple(sorted(result))


def execute_batch_plan(
    plan: dict[str, Any], *, activation_data: bytes, activation_evidence_data: bytes,
    permit: Any, resolver: Any, transport: Any, execution_epoch: int,
    network_acknowledgement: str, confirmed_plan_hash: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Execute one approved batch; one approval covers every URL in it."""

    activation = load_batch_activation(activation_data, activation_evidence_data)
    validate_batch_plan(activation, plan, execution_epoch=execution_epoch)
    scope = activation["scope"]
    if network_acknowledgement != BATCH_ACKNOWLEDGEMENT:
        raise AcquisitionPolicyError("batch_acknowledgement_required")
    if confirmed_plan_hash != plan["content_hash"]:
        raise AcquisitionPolicyError("batch_plan_hash_confirmation_invalid")
    plan_origins = tuple(sorted({origin_for(item["url"]) for item in plan["requests"]}))
    if (
        permit.capability_id != BATCH_CAPABILITY_ID
        or tuple(sorted(permit.approved_origins)) != plan_origins
        or resolver.permit != permit or transport.permit != permit
        or permit.actor_id != plan["approved_by"]["actor_id"]
    ):
        raise AcquisitionPolicyError("batch_permit_invalid")
    addresses: dict[str, tuple[str, ...]] = {}
    ledger: list[dict[str, Any]] = []
    bodies: dict[str, bytes] = {}
    bytes_used = 0
    for request in plan["requests"]:
        url = request["url"]
        hostname = str(urlsplit(url).hostname)
        entry: dict[str, Any] = {
            "request_id": request["request_id"], "url": url,
            "origin": origin_for(url),
            "origin_selected_by": request["origin_selected_by"],
            "provenance": request["provenance"],
            "network": False, "http_status": None,
            "body_bytes": 0, "body_sha256": None,
            "outcome": "refused_budget_exhausted", "failure_code": None,
            "disposition": "untrusted_candidate",
            "applicability": "not_assessed",
            "mathematical_warrant": "none",
        }
        if bytes_used >= scope["max_response_bytes_per_run"]:
            entry["failure_code"] = "batch_byte_budget_exhausted"
            ledger.append(entry)
            continue
        try:
            if hostname not in addresses:
                addresses[hostname] = _public_addresses(
                    resolver.resolve(hostname), hostname
                )
            entry["network"] = True
            remaining_bytes = scope["max_response_bytes_per_run"] - bytes_used
            response_limit = min(
                scope["max_response_bytes_per_request"], remaining_bytes,
            )
            response = transport.fetch(TransportRequest(
                "GET", url, (), addresses[hostname],
                scope["timeout_milliseconds"], 65_536,
                response_limit,
            ))
            if len(response.body) > response_limit:
                raise RuntimeError("batch transport violated its response byte limit")
            entry["http_status"] = response.status
            entry["body_bytes"] = len(response.body)
            entry["body_sha256"] = sha256_bytes(response.body)
            bytes_used += len(response.body)
            if 300 <= response.status < 400:
                entry["outcome"] = "failed"
                entry["failure_code"] = "redirect_refused"
            elif response.status != 200:
                entry["outcome"] = "failed"
                entry["failure_code"] = "http_status_not_ok"
            else:
                entry["outcome"] = "stored_candidate"
                bodies[request["request_id"]] = response.body
        except AcquisitionPolicyError as error:
            entry["outcome"] = "failed"
            entry["failure_code"] = str(error)[:128]
        except TransportFailure as error:
            entry["outcome"] = "failed"
            entry["failure_code"] = str(error)[:128] or "transport_failure"
        ledger.append(entry)
    report: dict[str, Any] = {
        "schema_version": BATCH_REPORT_SCHEMA,
        "activation_hash": activation["content_hash"],
        "plan_hash": plan["content_hash"],
        "run_id": plan["run_id"],
        "approved_by": plan["approved_by"],
        "approval_scope": "plan",
        "execution_epoch": execution_epoch,
        "totals": {
            "requests": sum(1 for entry in ledger if entry["network"]),
            "stored": sum(1 for entry in ledger if entry["outcome"] == "stored_candidate"),
            "failed": sum(1 for entry in ledger if entry["outcome"] == "failed"),
            "refused": sum(
                1 for entry in ledger if entry["outcome"] == "refused_budget_exhausted"
            ),
            "body_bytes": sum(entry["body_bytes"] for entry in ledger),
        },
        "url_ledger": ledger,
        "acquisition_authorized_by_discovery": False,
    }
    report["content_hash"] = canonical_hash(report)
    return report, bodies


def verify_batch_report(report: Any, plan: dict[str, Any]) -> dict[str, Any]:
    """Recheck batch accounting: every planned URL has exactly one record."""

    expected = {
        "schema_version", "activation_hash", "plan_hash", "run_id", "approved_by",
        "approval_scope", "execution_epoch", "totals", "url_ledger",
        "acquisition_authorized_by_discovery", "content_hash",
    }
    if not isinstance(report, dict) or set(report) != expected \
            or report.get("schema_version") != BATCH_REPORT_SCHEMA:
        raise ValueError("batch report fields differ")
    _reject_floats(report, "report")
    validate_batch_plan(
        {"scope": _EXPECTED_SCOPE}, plan,
        execution_epoch=report.get("execution_epoch"),
    )
    supplied = report.get("content_hash")
    if _SHA256.fullmatch(str(supplied)) is None or canonical_hash(
        {key: value for key, value in report.items() if key != "content_hash"}
    ) != supplied:
        raise ValueError("batch report identity differs")
    if (
        report.get("plan_hash") != plan.get("content_hash")
        or report.get("activation_hash") != BATCH_ACTIVATION_HASH
        or report.get("run_id") != plan.get("run_id")
        or report.get("approved_by") != plan.get("approved_by")
        or report.get("approval_scope") != "plan"
        or report.get("acquisition_authorized_by_discovery") is not False
    ):
        raise ValueError("batch report binding differs")
    ledger = report.get("url_ledger")
    planned = {item["request_id"]: item["url"] for item in plan["requests"]}
    if not isinstance(ledger, list) or len(ledger) != len(planned) \
            or [entry.get("request_id") for entry in ledger if isinstance(entry, dict)] \
            != [item["request_id"] for item in plan["requests"]]:
        raise ValueError("batch report ledger coverage differs")
    requests = stored = failed = refused = body_bytes = 0
    seen_request_ids: set[str] = set()
    for entry in ledger:
        expected_entry_fields = {
            "request_id", "url", "origin", "origin_selected_by", "provenance",
            "network", "http_status", "body_bytes", "body_sha256", "outcome",
            "failure_code", "disposition", "applicability", "mathematical_warrant",
        }
        request_id = entry.get("request_id") if isinstance(entry, dict) else None
        planned_request = next(
            (item for item in plan["requests"] if item["request_id"] == request_id), None,
        )
        if (
            not isinstance(entry, dict) or set(entry) != expected_entry_fields
            or request_id in seen_request_ids
            or planned_request is None
            or planned.get(request_id) != entry.get("url")
            or entry.get("origin") != origin_for(planned_request["url"])
            or entry.get("origin_selected_by") != planned_request["origin_selected_by"]
            or entry.get("provenance") != planned_request["provenance"]
        ):
            raise ValueError("batch report ledger entry differs")
        seen_request_ids.add(request_id)
        if isinstance(entry.get("body_bytes"), bool) \
                or not isinstance(entry.get("body_bytes"), int) or entry["body_bytes"] < 0:
            raise ValueError("batch report byte accounting differs")
        body_bytes += entry["body_bytes"]
        if entry["body_bytes"] > _EXPECTED_SCOPE["max_response_bytes_per_request"]:
            raise ValueError("batch report exceeds per-request byte budget")
        digest = entry.get("body_sha256")
        if entry["body_bytes"] > 0 and _SHA256.fullmatch(str(digest)) is None:
            raise ValueError("batch report body hash differs")
        if entry["body_bytes"] == 0 and digest is not None:
            raise ValueError("batch report empty body has a hash")
        outcome = entry.get("outcome")
        if outcome == "stored_candidate":
            if entry.get("network") is not True or entry.get("http_status") != 200 \
                    or entry.get("failure_code") is not None:
                raise ValueError("batch stored outcome differs")
            stored += 1
        elif outcome == "failed":
            if not isinstance(entry.get("failure_code"), str) \
                    or not entry["failure_code"]:
                raise ValueError("batch failed outcome differs")
            if entry.get("network") is False and (
                entry.get("http_status") is not None or entry["body_bytes"] != 0
                or entry.get("body_sha256") is not None
            ):
                raise ValueError("batch pre-network failure claims a response")
            if entry.get("network") is not False and entry.get("network") is not True:
                raise ValueError("batch failed network marker differs")
            failed += 1
        elif outcome == "refused_budget_exhausted":
            refused += 1
            if entry.get("network") is not False or entry["body_bytes"] != 0 \
                    or entry.get("http_status") is not None \
                    or entry.get("failure_code") != "batch_byte_budget_exhausted" \
                    or body_bytes < _EXPECTED_SCOPE["max_response_bytes_per_run"]:
                raise ValueError("batch report refused entry claims network effect")
        else:
            raise ValueError("batch report outcome differs")
        if entry.get("network") is True:
            requests += 1
        elif outcome not in {"refused_budget_exhausted", "failed"}:
            raise ValueError("batch report outcome lacks its network effect")
        if entry.get("disposition") != "untrusted_candidate" \
                or entry.get("applicability") != "not_assessed" \
                or entry.get("mathematical_warrant") != "none":
            raise ValueError("batch report attempts a trust promotion")
    if report.get("totals") != {
        "requests": requests, "stored": stored, "failed": failed,
        "refused": refused, "body_bytes": body_bytes,
    }:
        raise ValueError("batch report accounting differs")
    if body_bytes > _EXPECTED_SCOPE["max_response_bytes_per_run"]:
        raise ValueError("batch report exceeds run response byte budget")
    return report


__all__ = [
    "BATCH_ACKNOWLEDGEMENT", "BATCH_ACTIVATION_HASH", "BATCH_ACTIVATION_SCHEMA",
    "BATCH_CAPABILITY_ID", "BATCH_PLAN_SCHEMA", "BATCH_REPORT_SCHEMA",
    "MAX_BATCH_ACTIVATION_BYTES", "MAX_BATCH_REQUESTS_CEILING",
    "build_batch_plan", "execute_batch_plan", "load_batch_activation",
    "validate_batch_plan", "verify_batch_report",
]
