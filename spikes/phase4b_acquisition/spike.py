"""Bounded, offline-testable acquisition/crawler adoption spike.

This module deliberately does not provide a live HTTP adapter.  It defines the
capability and transport boundaries, then exercises them with an injected
scripted transport.  A later gated slice may implement the transport without
moving network access into the trusted acquisition policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit


SCHEMA_VERSION = "adaivy.phase4b-acquisition-spike.v1"
INTENDED_USE = "acquisition"


class AcquisitionError(ValueError):
    """A fail-closed acquisition policy or replay error."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_url(raw: str, allowed_hosts: frozenset[str]) -> str:
    parts = urlsplit(raw)
    if parts.scheme != "https":
        raise AcquisitionError("https_required")
    if not parts.hostname or parts.username is not None or parts.password is not None:
        raise AcquisitionError("invalid_authority")
    host = parts.hostname.casefold()
    if host not in allowed_hosts:
        raise AcquisitionError("host_not_allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise AcquisitionError("invalid_port") from exc
    if port not in (None, 443):
        raise AcquisitionError("https_default_port_required")
    if parts.fragment:
        raise AcquisitionError("fragment_forbidden")
    path = parts.path or "/"
    authority = host if port is None else f"{host}:443"
    return urlunsplit(("https", authority, path, parts.query, ""))


@dataclass(frozen=True, slots=True)
class AcquisitionCapability:
    capability_id: str
    actor_id: str
    network_enabled: bool


@dataclass(frozen=True, slots=True)
class AcquisitionPolicy:
    allowed_hosts: frozenset[str]
    max_redirects: int
    max_response_bytes: int
    max_wall_ms: int
    max_sources: int

    def __post_init__(self) -> None:
        if not self.allowed_hosts or any(host != host.casefold() for host in self.allowed_hosts):
            raise AcquisitionError("allowed_hosts_must_be_nonempty_lowercase")
        if self.max_redirects < 0 or min(
            self.max_response_bytes, self.max_wall_ms, self.max_sources
        ) <= 0:
            raise AcquisitionError("bounds_must_be_positive")


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    request_id: str
    url: str


@dataclass(frozen=True, slots=True)
class RightsDecision:
    decision_id: str
    url: str
    intended_use: str
    value: str


@dataclass(frozen=True, slots=True)
class RobotsDecision:
    decision_id: str
    url: str
    allowed: bool
    source: str = "operator_supplied"


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    elapsed_ms: int


class Transport(Protocol):
    def fetch(self, url: str, *, timeout_ms: int, byte_limit: int) -> TransportResponse:
        """Return an untrusted response or raise an implementation exception."""


class ScriptedTransport:
    """Offline transport whose complete response set is project-authored input."""

    def __init__(self, script: Mapping[str, Mapping[str, Any]]) -> None:
        self._script = dict(script)
        self.calls: list[dict[str, object]] = []

    def fetch(self, url: str, *, timeout_ms: int, byte_limit: int) -> TransportResponse:
        self.calls.append({"url": url, "timeout_ms": timeout_ms, "byte_limit": byte_limit})
        item = self._script.get(url)
        if item is None:
            raise LookupError("no_scripted_response")
        if "error" in item:
            raise OSError(str(item["error"]))
        headers_value = item.get("headers", {})
        if not isinstance(headers_value, dict):
            raise TypeError("scripted headers must be an object")
        body_value = item.get("body", "")
        if not isinstance(body_value, str):
            raise TypeError("scripted body must be text")
        return TransportResponse(
            status=int(item["status"]),
            headers=tuple(sorted((str(k).casefold(), str(v)) for k, v in headers_value.items())),
            body=body_value.encode("utf-8"),
            elapsed_ms=int(item.get("elapsed_ms", 0)),
        )


def _decision_map(items: Sequence[RightsDecision | RobotsDecision]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items:
        if item.url in result:
            raise AcquisitionError("duplicate_preflight_decision")
        result[item.url] = item
    return result


def _failure(request_id: str, url: str, reason: str, detail: str = "") -> dict[str, Any]:
    # Failure records intentionally contain no body, content hash, or invented source.
    result = {
        "request_id": request_id,
        "url": url,
        "outcome": "failed",
        "reason": reason,
        "detail": detail,
    }
    result["manifest_hash"] = _hash(result)
    return result


def acquire_candidates(
    requests: Sequence[AcquisitionRequest],
    *,
    capability: AcquisitionCapability,
    policy: AcquisitionPolicy,
    rights: Sequence[RightsDecision],
    robots: Sequence[RobotsDecision],
    transport: Transport,
) -> dict[str, Any]:
    """Acquire untrusted candidates after explicit authorization and policy checks."""

    rights_by_url = _decision_map(rights)
    robots_by_url = _decision_map(robots)
    responses: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    elapsed_ms = 0
    source_attempts = 0

    for request in requests:
        if source_attempts >= policy.max_sources:
            failures.append(_failure(request.request_id, request.url, "source_count_exhausted"))
            continue
        source_attempts += 1
        current = request.url
        visited: set[str] = set()
        redirect_count = 0

        while True:
            try:
                current = canonical_url(current, policy.allowed_hosts)
            except AcquisitionError as exc:
                failures.append(_failure(request.request_id, current, str(exc)))
                break
            if current in visited:
                failures.append(_failure(request.request_id, current, "redirect_cycle"))
                break
            visited.add(current)

            rights_decision = rights_by_url.get(current)
            if (
                rights_decision is None
                or rights_decision.intended_use != INTENDED_USE
                or rights_decision.value != "allowed"
            ):
                failures.append(_failure(request.request_id, current, "rights_not_authorized"))
                break
            robots_decision = robots_by_url.get(current)
            if robots_decision is None or not robots_decision.allowed:
                failures.append(_failure(request.request_id, current, "robots_not_authorized"))
                break
            if robots_decision.source != "operator_supplied":
                failures.append(_failure(request.request_id, current, "robots_input_not_offline"))
                break
            if not capability.network_enabled:
                failures.append(_failure(request.request_id, current, "network_capability_disabled"))
                break
            remaining_ms = policy.max_wall_ms - elapsed_ms
            if remaining_ms <= 0:
                failures.append(_failure(request.request_id, current, "wall_time_exhausted"))
                break

            try:
                response = transport.fetch(
                    current, timeout_ms=remaining_ms, byte_limit=policy.max_response_bytes
                )
            except Exception as exc:  # The adapter boundary converts failures into data.
                failures.append(_failure(request.request_id, current, "transport_failure", type(exc).__name__))
                break
            if response.elapsed_ms < 0 or response.elapsed_ms > remaining_ms:
                failures.append(_failure(request.request_id, current, "wall_time_exhausted"))
                break
            elapsed_ms += response.elapsed_ms
            if len(response.body) > policy.max_response_bytes:
                failures.append(_failure(request.request_id, current, "response_too_large"))
                break

            headers = dict(response.headers)
            response_manifest = {
                "request_id": request.request_id,
                "url": current,
                "status": response.status,
                "headers": [[key, value] for key, value in response.headers],
                "byte_length": len(response.body),
                "content_sha256": _bytes_hash(response.body),
                "content_base64": base64.b64encode(response.body).decode("ascii"),
                "elapsed_ms": response.elapsed_ms,
                "rights_decision_id": rights_decision.decision_id,
                "robots_decision_id": robots_decision.decision_id,
            }
            response_manifest["manifest_hash"] = _hash(response_manifest)
            responses.append(response_manifest)

            if response.status in {301, 302, 303, 307, 308}:
                location = headers.get("location")
                if not location:
                    failures.append(_failure(request.request_id, current, "redirect_missing_location"))
                    break
                if redirect_count >= policy.max_redirects:
                    failures.append(_failure(request.request_id, current, "redirect_limit_exhausted"))
                    break
                redirect_count += 1
                current = location
                continue
            if not 200 <= response.status < 300:
                failures.append(_failure(request.request_id, current, "http_status", str(response.status)))
                break

            candidate_identity = {
                "request_id": request.request_id,
                "source_url": current,
                "content_sha256": response_manifest["content_sha256"],
            }
            candidate = {
                "candidate_id": "candidate." + _hash(candidate_identity),
                "request_id": request.request_id,
                "source_url": current,
                "response_manifest_hash": response_manifest["manifest_hash"],
                "content_sha256": response_manifest["content_sha256"],
                "byte_length": len(response.body),
                "content_base64": base64.b64encode(response.body).decode("ascii"),
                "disposition": "untrusted_candidate",
                "proof_status": "none",
                "applicability_status": "not_assessed",
            }
            candidates.append(candidate)
            break

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capability_id": capability.capability_id,
        "actor_id": capability.actor_id,
        "policy": {
            "allowed_hosts": sorted(policy.allowed_hosts),
            "max_redirects": policy.max_redirects,
            "max_response_bytes": policy.max_response_bytes,
            "max_wall_ms": policy.max_wall_ms,
            "max_sources": policy.max_sources,
        },
        "responses": responses,
        "failures": failures,
        "candidates": candidates,
        "source_attempts": source_attempts,
        "elapsed_ms": elapsed_ms,
    }
    manifest["content_hash"] = _hash(manifest)
    return manifest


def replay_manifest(data: bytes) -> dict[str, Any]:
    """Verify a captured run without invoking any transport or policy adapter."""

    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionError("invalid_manifest_json") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise AcquisitionError("unsupported_manifest_schema")
    supplied_hash = value.get("content_hash")
    unhashed = dict(value)
    unhashed.pop("content_hash", None)
    if supplied_hash != _hash(unhashed):
        raise AcquisitionError("manifest_hash_mismatch")
    for response in value.get("responses", []):
        item = dict(response)
        supplied = item.pop("manifest_hash", None)
        if supplied != _hash(item):
            raise AcquisitionError("response_manifest_hash_mismatch")
        content = base64.b64decode(response["content_base64"], validate=True)
        if len(content) != response["byte_length"] or _bytes_hash(content) != response["content_sha256"]:
            raise AcquisitionError("response_content_mismatch")
    for failure in value.get("failures", []):
        item = dict(failure)
        supplied = item.pop("manifest_hash", None)
        if supplied != _hash(item):
            raise AcquisitionError("failure_manifest_hash_mismatch")
    for candidate in value.get("candidates", []):
        content = base64.b64decode(candidate["content_base64"], validate=True)
        if len(content) != candidate["byte_length"] or _bytes_hash(content) != candidate["content_sha256"]:
            raise AcquisitionError("candidate_content_mismatch")
        expected_id = "candidate." + _hash(
            {
                "request_id": candidate["request_id"],
                "source_url": candidate["source_url"],
                "content_sha256": candidate["content_sha256"],
            }
        )
        if candidate.get("candidate_id") != expected_id:
            raise AcquisitionError("candidate_identity_mismatch")
        if candidate.get("disposition") != "untrusted_candidate":
            raise AcquisitionError("candidate_trust_boundary_breached")
    return value
