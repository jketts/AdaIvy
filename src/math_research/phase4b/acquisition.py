"""Bounded Phase 4B acquisition policy and injected network ports.

There is deliberately no live resolver or transport in this module.  Production
policy is exercised with deterministic fakes, while a future outward adapter
must implement the same narrow interfaces without weakening these checks.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
import json
import re
from typing import Protocol, Sequence
from urllib.parse import urljoin, urlsplit, urlunsplit


MAX_URL_BYTES = 2_048
MAX_ORIGINS = 4
MAX_SOURCES = 100
MAX_REDIRECTS = 5
MAX_RETRIES = 2
MAX_SNAPSHOT_AGE_SECONDS = 86_400
MAX_HEADER_BYTES = 65_536
MAX_BODY_BYTES = 2_097_152
MAX_TOTAL_BODY_BYTES = 67_108_864
MAX_RUN_MILLISECONDS = 1_800_000
MAX_RESOLVED_ADDRESSES = 16
MIN_ORIGIN_START_INTERVAL_MILLISECONDS = 1_000
SEMANTIC_SCHEMA = "adaivy.phase4b-acquisition-semantic.v1"
OPERATIONAL_SCHEMA = "adaivy.phase4b-acquisition-operational.v1"

_HASH = re.compile(r"^[0-9a-f]{64}$")
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CROSS_ORIGIN_HEADERS = frozenset(
    {"authorization", "cookie", "origin", "proxy-authorization", "referer"}
)
_RETRYABLE_STATUS = frozenset({408, 429})


class AcquisitionPolicyError(ValueError):
    """An input or authorization failed closed before content visibility."""


class TransportFailure(OSError):
    """An injected transport reports an idempotent GET failure."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bytes_hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validated_hash(value: str, label: str) -> str:
    if not _HASH.fullmatch(value):
        raise AcquisitionPolicyError(f"{label}_hash_invalid")
    return value


def canonical_url(raw: str) -> str:
    if not isinstance(raw, str) or not raw or len(raw.encode("utf-8")) > MAX_URL_BYTES:
        raise AcquisitionPolicyError("url_length_invalid")
    if any(ord(char) < 33 or ord(char) == 127 for char in raw) or "\\" in raw:
        raise AcquisitionPolicyError("url_ambiguous")
    parts = urlsplit(raw)
    if parts.scheme.casefold() != "https" or not parts.netloc:
        raise AcquisitionPolicyError("https_required")
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise AcquisitionPolicyError("url_authority_invalid")
    try:
        port = parts.port
    except ValueError as exc:
        raise AcquisitionPolicyError("url_port_invalid") from exc
    if port not in (None, 443):
        raise AcquisitionPolicyError("url_port_invalid")
    hostname = parts.hostname
    if hostname is None or hostname.endswith("."):
        raise AcquisitionPolicyError("url_host_invalid")
    try:
        hostname.encode("ascii", "strict")
    except UnicodeEncodeError as exc:
        raise AcquisitionPolicyError("url_host_must_be_ascii") from exc
    host = hostname.casefold()
    if "%" in host:
        raise AcquisitionPolicyError("url_host_invalid")
    try:
        parsed_address = ipaddress.ip_address(host)
    except ValueError:
        labels = host.split(".")
        if len(host) > 253 or any(_DNS_LABEL.fullmatch(label) is None for label in labels):
            raise AcquisitionPolicyError("url_host_invalid")
        authority = host
    else:
        authority = f"[{host}]" if parsed_address.version == 6 else host
    path = parts.path or "/"
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise AcquisitionPolicyError("url_dot_segment_forbidden")
    result = urlunsplit(("https", authority, path, parts.query, ""))
    if len(result.encode("utf-8")) > MAX_URL_BYTES:
        raise AcquisitionPolicyError("url_length_invalid")
    return result


def origin_for(url: str) -> str:
    parts = urlsplit(canonical_url(url))
    return f"https://{parts.netloc}"


@dataclass(frozen=True, slots=True)
class AcquisitionPolicy:
    max_sources: int = MAX_SOURCES
    max_redirects: int = MAX_REDIRECTS
    max_retries: int = MAX_RETRIES
    max_snapshot_age_seconds: int = MAX_SNAPSHOT_AGE_SECONDS
    max_header_bytes: int = MAX_HEADER_BYTES
    max_body_bytes: int = MAX_BODY_BYTES
    max_total_body_bytes: int = MAX_TOTAL_BODY_BYTES
    max_run_milliseconds: int = MAX_RUN_MILLISECONDS

    def __post_init__(self) -> None:
        maxima = (
            (self.max_sources, MAX_SOURCES),
            (self.max_redirects, MAX_REDIRECTS),
            (self.max_retries, MAX_RETRIES),
            (self.max_snapshot_age_seconds, MAX_SNAPSHOT_AGE_SECONDS),
            (self.max_header_bytes, MAX_HEADER_BYTES),
            (self.max_body_bytes, MAX_BODY_BYTES),
            (self.max_total_body_bytes, MAX_TOTAL_BODY_BYTES),
            (self.max_run_milliseconds, MAX_RUN_MILLISECONDS),
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > maximum for value, maximum in maxima):
            raise AcquisitionPolicyError("policy_bound_invalid")
        if min(
            self.max_sources, self.max_snapshot_age_seconds, self.max_header_bytes,
            self.max_body_bytes, self.max_total_body_bytes, self.max_run_milliseconds,
        ) == 0:
            raise AcquisitionPolicyError("policy_positive_bound_required")

    def value(self) -> dict[str, int | str]:
        return {
            "policy_version": "phase4b-acquisition-v1",
            "max_sources": self.max_sources,
            "max_redirects": self.max_redirects,
            "max_retries": self.max_retries,
            "max_snapshot_age_seconds": self.max_snapshot_age_seconds,
            "max_header_bytes": self.max_header_bytes,
            "max_body_bytes": self.max_body_bytes,
            "max_total_body_bytes": self.max_total_body_bytes,
            "max_run_milliseconds": self.max_run_milliseconds,
        }

    @property
    def content_hash(self) -> str:
        return _hash(self.value())


@dataclass(frozen=True, slots=True)
class AuthorizedResource:
    request_id: str
    url: str


@dataclass(frozen=True, slots=True)
class RunAuthorization:
    run_id: str
    actor_id: str
    actor_kind: str
    authority: str
    capability_id: str
    operation: str
    network_enabled: bool
    policy_hash: str
    approved_origins: tuple[str, ...]
    resources: tuple[AuthorizedResource, ...]


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    run_id: str
    request_id: str
    actor_id: str
    url: str
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class RightsDecision:
    decision_id: str
    run_id: str
    url: str
    intended_use: str
    value: str
    actor_kind: str
    authority: str
    valid_from_epoch: int
    valid_until_epoch: int | None


@dataclass(frozen=True, slots=True)
class TermsSnapshot:
    snapshot_id: str
    origin: str
    content_hash: str
    captured_at_epoch: int
    valid: bool
    acquisition_allowed: bool


@dataclass(frozen=True, slots=True)
class RobotsSnapshot:
    snapshot_id: str
    url: str
    content_hash: str
    captured_at_epoch: int
    valid: bool
    allowed: bool


@dataclass(frozen=True, slots=True)
class Resolution:
    hostname: str
    addresses: tuple[str, ...]


class Resolver(Protocol):
    def resolve(self, hostname: str) -> Resolution:
        """Resolve without using ambient DNS state."""


class StartClock(Protocol):
    def now_milliseconds(self) -> int:
        """Return injected monotonic time for run-deadline checkpoints."""


@dataclass(frozen=True, slots=True)
class TransportRequest:
    method: str
    url: str
    headers: tuple[tuple[str, str], ...]
    connect_addresses: tuple[str, ...]
    timeout_milliseconds: int
    max_header_bytes: int
    max_body_bytes: int


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    connected_peer: str
    elapsed_milliseconds: int


class Transport(Protocol):
    def fetch(self, request: TransportRequest) -> TransportResponse:
        """Execute one injected HTTPS GET or raise TransportFailure."""


@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    candidate_id: str
    request_id: str
    source_url: str
    content_sha256: str
    media_type: str
    body: bytes
    disposition: str = "untrusted_candidate"
    applicability_status: str = "not_assessed"
    mathematical_warrant: str = "none"
    graph_admission: str = "not_admitted"


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    semantic_bytes: bytes
    semantic_hash: str
    operational_bytes: bytes
    operational_hash: str
    candidates: tuple[CandidateArtifact, ...]


def _validated_headers(headers: Sequence[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    observed: set[str] = set()
    if isinstance(headers, (str, bytes)) or not isinstance(headers, Sequence):
        raise AcquisitionPolicyError("header_collection_invalid")
    for item in headers:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise AcquisitionPolicyError("header_collection_invalid")
        raw_name, raw_value = item
        if not isinstance(raw_name, str) or not isinstance(raw_value, str):
            raise AcquisitionPolicyError("header_type_invalid")
        name = raw_name.casefold()
        if not _HEADER_NAME.fullmatch(raw_name) or name in observed:
            raise AcquisitionPolicyError("header_invalid_or_duplicate")
        if "\r" in raw_value or "\n" in raw_value or "\x00" in raw_value:
            raise AcquisitionPolicyError("header_value_invalid")
        observed.add(name)
        result.append((name, raw_value))
    return tuple(sorted(result))


def _header_bytes(headers: Sequence[tuple[str, str]]) -> int:
    return sum(len(name.encode("ascii")) + 2 + len(value.encode("utf-8")) + 2 for name, value in headers)


def _snapshot_current(captured_at: int, now_epoch: int, maximum_age: int) -> bool:
    return captured_at <= now_epoch and now_epoch - captured_at <= maximum_age


def _public_addresses(resolution: Resolution, expected_hostname: str) -> tuple[str, ...]:
    if (
        not isinstance(resolution.hostname, str)
        or resolution.hostname.casefold() != expected_hostname
        or not isinstance(resolution.addresses, tuple)
        or not 1 <= len(resolution.addresses) <= MAX_RESOLVED_ADDRESSES
    ):
        raise AcquisitionPolicyError("resolver_identity_invalid")
    parsed: list[str] = []
    for raw in resolution.addresses:
        if not isinstance(raw, str):
            raise AcquisitionPolicyError("resolved_address_invalid")
        try:
            address = ipaddress.ip_address(raw)
        except (TypeError, ValueError) as exc:
            raise AcquisitionPolicyError("resolved_address_invalid") from exc
        if not address.is_global or address.is_multicast or address.is_unspecified:
            raise AcquisitionPolicyError("resolved_address_forbidden")
        normalized = address.compressed
        if normalized in parsed:
            raise AcquisitionPolicyError("resolved_address_duplicate")
        parsed.append(normalized)
    return tuple(sorted(parsed))


def _retryable_status(status: int) -> bool:
    return status in _RETRYABLE_STATUS or 500 <= status <= 599


def _origin_authorizations(
    authorization: RunAuthorization, policy: AcquisitionPolicy
) -> tuple[dict[str, str], frozenset[str]]:
    if (
        not authorization.run_id
        or not authorization.actor_id
        or not authorization.capability_id
        or authorization.actor_kind != "human"
        or authorization.authority != "human_final"
        or authorization.operation != "acquire_https"
        or not authorization.network_enabled
        or authorization.policy_hash != policy.content_hash
    ):
        raise AcquisitionPolicyError("run_authority_invalid")
    if not 1 <= len(authorization.approved_origins) <= MAX_ORIGINS:
        raise AcquisitionPolicyError("approved_origin_count_invalid")
    origins: list[str] = []
    for raw in authorization.approved_origins:
        if raw != origin_for(raw + "/"):
            raise AcquisitionPolicyError("approved_origin_not_canonical")
        if raw in origins:
            raise AcquisitionPolicyError("approved_origin_duplicate")
        origins.append(raw)
    if not 1 <= len(authorization.resources) <= policy.max_sources:
        raise AcquisitionPolicyError("authorized_resource_count_invalid")
    resources: dict[str, str] = {}
    for resource in authorization.resources:
        url = canonical_url(resource.url)
        if not resource.request_id or resource.request_id in resources or url != resource.url or origin_for(url) not in origins:
            raise AcquisitionPolicyError("authorized_resource_invalid")
        resources[resource.request_id] = url
    return resources, frozenset(origins)


def _indexed(items: Sequence[object], key: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        value = getattr(item, key)
        if value in result:
            raise AcquisitionPolicyError(f"duplicate_{key}")
        result[value] = item
    return result


def _preflight(
    *,
    url: str,
    run_id: str,
    now_epoch: int,
    policy: AcquisitionPolicy,
    approved_origins: frozenset[str],
    rights_by_key: dict[tuple[str, str], RightsDecision],
    terms_by_origin: dict[str, TermsSnapshot],
    robots_by_url: dict[str, RobotsSnapshot],
) -> tuple[RightsDecision, RightsDecision, TermsSnapshot, RobotsSnapshot]:
    origin = origin_for(url)
    if origin not in approved_origins:
        raise AcquisitionPolicyError("origin_not_authorized")
    acquisition = rights_by_key.get((url, "acquisition"))
    storage = rights_by_key.get((url, "storage_and_retention"))
    for decision, intended_use in ((acquisition, "acquisition"), (storage, "storage_and_retention")):
        if (
            decision is None
            or decision.run_id != run_id
            or decision.intended_use != intended_use
            or decision.value != "allowed"
            or decision.actor_kind != "human"
            or decision.authority != "human_final"
            or decision.valid_from_epoch > now_epoch
            or (decision.valid_until_epoch is not None and now_epoch > decision.valid_until_epoch)
        ):
            raise AcquisitionPolicyError(f"{intended_use}_rights_invalid")
    terms = terms_by_origin.get(origin)
    if (
        terms is None
        or terms.origin != origin
        or not terms.valid
        or not terms.acquisition_allowed
        or not _snapshot_current(terms.captured_at_epoch, now_epoch, policy.max_snapshot_age_seconds)
    ):
        raise AcquisitionPolicyError("terms_snapshot_invalid_or_stale")
    _validated_hash(terms.content_hash, "terms")
    robots = robots_by_url.get(url)
    if (
        robots is None
        or robots.url != url
        or not robots.valid
        or not robots.allowed
        or not _snapshot_current(robots.captured_at_epoch, now_epoch, policy.max_snapshot_age_seconds)
    ):
        raise AcquisitionPolicyError("robots_snapshot_invalid_or_stale")
    _validated_hash(robots.content_hash, "robots")
    return acquisition, storage, terms, robots


def _result(
    *,
    authorization: RunAuthorization,
    policy: AcquisitionPolicy,
    semantic_results: list[dict[str, object]],
    operations: list[dict[str, object]],
    recorded_at_epoch: int,
    candidates: list[CandidateArtifact],
) -> AcquisitionResult:
    semantic = {
        "schema_version": SEMANTIC_SCHEMA,
        "run_id": authorization.run_id,
        "policy_hash": policy.content_hash,
        "results": semantic_results,
    }
    semantic_bytes = canonical_bytes(semantic)
    semantic_hash = _bytes_hash(semantic_bytes)
    operational = {
        "schema_version": OPERATIONAL_SCHEMA,
        "semantic_hash": semantic_hash,
        "actor_id": authorization.actor_id,
        "capability_id": authorization.capability_id,
        "recorded_at_epoch": recorded_at_epoch,
        "operations": operations,
    }
    operational_bytes = canonical_bytes(operational)
    return AcquisitionResult(
        semantic_bytes=semantic_bytes,
        semantic_hash=semantic_hash,
        operational_bytes=operational_bytes,
        operational_hash=_bytes_hash(operational_bytes),
        candidates=tuple(candidates),
    )


def acquire(
    requests: Sequence[AcquisitionRequest],
    *,
    authorization: RunAuthorization,
    policy: AcquisitionPolicy,
    rights: Sequence[RightsDecision],
    terms: Sequence[TermsSnapshot],
    robots: Sequence[RobotsSnapshot],
    resolver: Resolver,
    transport: Transport,
    start_clock: StartClock,
    now_epoch: int,
    recorded_at_epoch: int,
) -> AcquisitionResult:
    """Run an authorized, sequential, bounded acquisition over injected ports."""

    resources, approved_origins = _origin_authorizations(authorization, policy)
    if not 1 <= len(requests) <= policy.max_sources:
        raise AcquisitionPolicyError("request_count_invalid")
    rights_by_key: dict[tuple[str, str], RightsDecision] = {}
    for decision in rights:
        url = canonical_url(decision.url)
        key = (url, decision.intended_use)
        if url != decision.url or key in rights_by_key:
            raise AcquisitionPolicyError("rights_input_invalid_or_duplicate")
        rights_by_key[key] = decision
    terms_by_origin = _indexed(terms, "origin")
    robots_by_url = _indexed(robots, "url")
    semantic_results: list[dict[str, object]] = []
    operations: list[dict[str, object]] = []
    candidates: list[CandidateArtifact] = []
    total_body_bytes = 0
    observed_requests: set[str] = set()
    last_start_by_origin: dict[str, int] = {}
    run_started_at: int | None = None
    last_clock_observation: int | None = None

    def observe_clock() -> tuple[int, int]:
        """Read and validate the sole authority for the absolute run deadline."""

        nonlocal run_started_at, last_clock_observation
        try:
            observed = start_clock.now_milliseconds()
        except Exception as exc:
            raise AcquisitionPolicyError("start_clock_failed") from exc
        if (
            isinstance(observed, bool)
            or not isinstance(observed, int)
            or observed < 0
            or (
                last_clock_observation is not None
                and observed < last_clock_observation
            )
        ):
            raise AcquisitionPolicyError("start_clock_invalid")
        if run_started_at is None:
            run_started_at = observed
        elapsed = observed - run_started_at
        last_clock_observation = observed
        if elapsed > policy.max_run_milliseconds:
            raise AcquisitionPolicyError("run_time_exhausted")
        return observed, elapsed

    for request in requests:
        if request.request_id in observed_requests:
            raise AcquisitionPolicyError("request_id_duplicate")
        observed_requests.add(request.request_id)
        try:
            current = canonical_url(request.url)
            if (
                request.run_id != authorization.run_id
                or request.actor_id != authorization.actor_id
                or resources.get(request.request_id) != current
            ):
                raise AcquisitionPolicyError("request_not_exactly_authorized")
            headers = _validated_headers(request.headers)
            if _header_bytes(headers) > policy.max_header_bytes:
                raise AcquisitionPolicyError("request_headers_too_large")
        except AcquisitionPolicyError as exc:
            semantic_results.append(
                {"request_id": request.request_id, "outcome": "failed", "reason": str(exc)}
            )
            operations.append(
                {"request_id": request.request_id, "url": request.url, "policy_failure": str(exc)}
            )
            continue

        redirects: list[str] = []
        hops: list[dict[str, object]] = []
        visited: set[str] = set()
        request_complete = False
        while not request_complete:
            if current in visited:
                semantic_results.append(
                    {"request_id": request.request_id, "outcome": "failed", "reason": "redirect_cycle", "redirects": redirects}
                )
                break
            visited.add(current)
            retry = 0
            while True:
                try:
                    observe_clock()
                    try:
                        acquisition_right, storage_right, terms_snapshot, robots_snapshot = _preflight(
                            url=current,
                            run_id=authorization.run_id,
                            now_epoch=now_epoch,
                            policy=policy,
                            approved_origins=approved_origins,
                            rights_by_key=rights_by_key,
                            terms_by_origin=terms_by_origin,  # type: ignore[arg-type]
                            robots_by_url=robots_by_url,  # type: ignore[arg-type]
                        )
                    except AcquisitionPolicyError:
                        # A failing preflight still has an absolute deadline
                        # checkpoint and a closed operation record.
                        observe_clock()
                        raise
                    _resolver_started, resolver_run_elapsed = observe_clock()
                    hostname = urlsplit(current).hostname
                    if hostname is None:
                        raise AcquisitionPolicyError("url_host_invalid")
                    resolver_remaining = policy.max_run_milliseconds - resolver_run_elapsed
                    if resolver_remaining <= 0:
                        raise AcquisitionPolicyError("run_time_exhausted")
                    try:
                        bounded_resolve = getattr(resolver, "resolve_with_timeout", None)
                        if callable(bounded_resolve):
                            resolution = bounded_resolve(hostname, resolver_remaining)
                        else:
                            resolution = resolver.resolve(hostname)
                    except Exception as exc:
                        # Measure resolver failures before closing the attempt.  Adapter
                        # exception text and types never cross the trust boundary.
                        observe_clock()
                        raise AcquisitionPolicyError("resolver_adapter_error") from exc
                    started_at, run_elapsed = observe_clock()
                    if not isinstance(resolution, Resolution):
                        raise AcquisitionPolicyError("resolver_response_invalid")
                    addresses = _public_addresses(resolution, hostname)
                    remaining = policy.max_run_milliseconds - run_elapsed
                    if remaining <= 0:
                        raise AcquisitionPolicyError("run_time_exhausted")
                    origin = origin_for(current)
                    previous_origin_start = last_start_by_origin.get(origin)
                    if (
                        previous_origin_start is not None
                        and started_at - previous_origin_start
                        < MIN_ORIGIN_START_INTERVAL_MILLISECONDS
                    ):
                        raise AcquisitionPolicyError("origin_start_rate_exceeded")
                    last_start_by_origin[origin] = started_at
                    transport_failure: str | None = None
                    try:
                        response = transport.fetch(
                            TransportRequest(
                                method="GET",
                                url=current,
                                headers=headers,
                                connect_addresses=addresses,
                                timeout_milliseconds=remaining,
                                max_header_bytes=policy.max_header_bytes,
                                max_body_bytes=policy.max_body_bytes,
                            )
                        )
                    except TransportFailure:
                        transport_failure = "transport_failure"
                        response = None
                    except Exception:
                        transport_failure = "transport_adapter_error"
                        response = None
                    # The monotonic checkpoint covers time consumed even by a failed
                    # adapter call; claimed response elapsed time is only a secondary
                    # consistency bound.
                    observe_clock()
                    if transport_failure is not None:
                        operations.append(
                            {
                                "request_id": request.request_id,
                                "url": current,
                                "retry": retry,
                                "transport_failure": transport_failure,
                            }
                        )
                        if retry < policy.max_retries:
                            retry += 1
                            continue
                        semantic_results.append(
                            {"request_id": request.request_id, "outcome": "failed", "reason": "retry_exhausted_transport", "redirects": redirects}
                        )
                        request_complete = True
                        break
                    if not isinstance(response, TransportResponse):
                        raise AcquisitionPolicyError("transport_response_invalid")
                    if (
                        isinstance(response.elapsed_milliseconds, bool)
                        or not isinstance(response.elapsed_milliseconds, int)
                        or response.elapsed_milliseconds < 0
                    ):
                        raise AcquisitionPolicyError("response_elapsed_invalid")
                    if response.elapsed_milliseconds > remaining:
                        raise AcquisitionPolicyError("run_time_exhausted")
                    if not isinstance(response.connected_peer, str):
                        raise AcquisitionPolicyError("connected_peer_invalid")
                    if not isinstance(response.body, bytes):
                        raise AcquisitionPolicyError("response_body_invalid")
                    try:
                        peer_address = ipaddress.ip_address(response.connected_peer)
                    except ValueError as exc:
                        raise AcquisitionPolicyError("connected_peer_invalid") from exc
                    if not peer_address.is_global or peer_address.is_multicast or peer_address.is_unspecified:
                        raise AcquisitionPolicyError("connected_peer_forbidden")
                    peer = peer_address.compressed
                    if peer not in addresses:
                        raise AcquisitionPolicyError("connected_peer_mismatch")
                    response_headers = _validated_headers(response.headers)
                    header_size = _header_bytes(response_headers)
                    if isinstance(response.status, bool) or not isinstance(response.status, int) or not 100 <= response.status <= 599:
                        raise AcquisitionPolicyError("response_status_invalid")
                    if header_size > policy.max_header_bytes:
                        raise AcquisitionPolicyError("response_headers_too_large")
                    if len(response.body) > policy.max_body_bytes:
                        raise AcquisitionPolicyError("response_body_too_large")
                    if total_body_bytes + len(response.body) > policy.max_total_body_bytes:
                        raise AcquisitionPolicyError("run_body_budget_exhausted")
                    total_body_bytes += len(response.body)
                    operation = {
                        "request_id": request.request_id,
                        "url": current,
                        "retry": retry,
                        "started_at_milliseconds": started_at,
                        "resolved_addresses": list(addresses),
                        "connected_peer": peer,
                        "status": response.status,
                        "elapsed_milliseconds": response.elapsed_milliseconds,
                    }
                    operations.append(operation)
                except AcquisitionPolicyError as exc:
                    operations.append(
                        {"request_id": request.request_id, "url": current, "retry": retry, "policy_failure": str(exc)}
                    )
                    semantic_results.append(
                        {"request_id": request.request_id, "outcome": "failed", "reason": str(exc), "redirects": redirects}
                    )
                    request_complete = True
                    break

                if _retryable_status(response.status):
                    if retry < policy.max_retries:
                        retry += 1
                        continue
                    semantic_results.append(
                        {"request_id": request.request_id, "outcome": "failed", "reason": "retry_exhausted_status", "status": response.status, "redirects": redirects}
                    )
                    request_complete = True
                    break

                header_map = dict(response_headers)
                if response.status in {301, 302, 303, 307, 308}:
                    location = header_map.get("location")
                    if location is None:
                        semantic_results.append(
                            {"request_id": request.request_id, "outcome": "failed", "reason": "redirect_location_missing", "redirects": redirects}
                        )
                        request_complete = True
                        break
                    if len(redirects) >= policy.max_redirects:
                        semantic_results.append(
                            {"request_id": request.request_id, "outcome": "failed", "reason": "redirect_limit_exhausted", "redirects": redirects}
                        )
                        request_complete = True
                        break
                    try:
                        redirected = canonical_url(urljoin(current, location))
                    except AcquisitionPolicyError as exc:
                        semantic_results.append(
                            {"request_id": request.request_id, "outcome": "failed", "reason": str(exc), "redirects": redirects}
                        )
                        request_complete = True
                        break
                    if origin_for(redirected) != origin_for(current):
                        headers = tuple((name, value) for name, value in headers if name not in _CROSS_ORIGIN_HEADERS)
                    redirects.append(redirected)
                    hops.append(
                        {
                            "url": current,
                            "status": response.status,
                            "header_hash": _hash(response_headers),
                            "rights": [acquisition_right.decision_id, storage_right.decision_id],
                            "terms_snapshot_id": terms_snapshot.snapshot_id,
                            "terms_content_hash": terms_snapshot.content_hash,
                            "robots_snapshot_id": robots_snapshot.snapshot_id,
                            "robots_content_hash": robots_snapshot.content_hash,
                        }
                    )
                    current = redirected
                    break

                if not 200 <= response.status <= 299:
                    semantic_results.append(
                        {"request_id": request.request_id, "outcome": "failed", "reason": "http_status", "status": response.status, "redirects": redirects}
                    )
                    request_complete = True
                    break

                # Recheck retention immediately before making the complete bytes visible.
                try:
                    _preflight(
                        url=current,
                        run_id=authorization.run_id,
                        now_epoch=now_epoch,
                        policy=policy,
                        approved_origins=approved_origins,
                        rights_by_key=rights_by_key,
                        terms_by_origin=terms_by_origin,  # type: ignore[arg-type]
                        robots_by_url=robots_by_url,  # type: ignore[arg-type]
                    )
                except AcquisitionPolicyError as exc:
                    semantic_results.append(
                        {"request_id": request.request_id, "outcome": "failed", "reason": str(exc), "redirects": redirects}
                    )
                    request_complete = True
                    break
                digest = _bytes_hash(response.body)
                media_type = header_map.get("content-type", "application/octet-stream").split(";", 1)[0].strip().casefold()
                candidate = CandidateArtifact(
                    candidate_id="candidate." + _hash(
                        {
                            "run_id": authorization.run_id,
                            "request_id": request.request_id,
                            "source_url": current,
                            "content_sha256": digest,
                        }
                    ),
                    request_id=request.request_id,
                    source_url=current,
                    content_sha256=digest,
                    media_type=media_type,
                    body=response.body,
                )
                candidates.append(candidate)
                hops.append(
                    {
                        "url": current,
                        "status": response.status,
                        "header_hash": _hash(response_headers),
                        "header_bytes": header_size,
                        "content_sha256": digest,
                        "byte_length": len(response.body),
                        "rights": [acquisition_right.decision_id, storage_right.decision_id],
                        "terms_snapshot_id": terms_snapshot.snapshot_id,
                        "terms_content_hash": terms_snapshot.content_hash,
                        "robots_snapshot_id": robots_snapshot.snapshot_id,
                        "robots_content_hash": robots_snapshot.content_hash,
                    }
                )
                semantic_results.append(
                    {
                        "request_id": request.request_id,
                        "outcome": "candidate_acquired",
                        "candidate_id": candidate.candidate_id,
                        "disposition": candidate.disposition,
                        "applicability_status": candidate.applicability_status,
                        "mathematical_warrant": candidate.mathematical_warrant,
                        "graph_admission": candidate.graph_admission,
                        "redirects": redirects,
                        "hops": hops,
                    }
                )
                request_complete = True
                break

    return _result(
        authorization=authorization,
        policy=policy,
        semantic_results=semantic_results,
        operations=operations,
        recorded_at_epoch=recorded_at_epoch,
        candidates=candidates,
    )


__all__ = [
    "AcquisitionPolicy", "AcquisitionPolicyError", "AcquisitionRequest",
    "AcquisitionResult", "AuthorizedResource", "CandidateArtifact", "Resolution",
    "RightsDecision", "RobotsSnapshot", "RunAuthorization", "TermsSnapshot",
    "TransportFailure", "TransportRequest", "TransportResponse", "acquire",
    "canonical_bytes", "canonical_url", "origin_for",
]
