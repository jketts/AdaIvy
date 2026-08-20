"""Explicit opt-in HTTPS resolver and transport for Phase 4B.

The ordinary repository path never imports networking modules or constructs
these adapters.  A trusted operator must supply a bounded permit; the Phase 4B
acquisition engine still performs the authoritative run, rights, robots,
terms, redirect, address, rate, and budget checks around this outward port.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
import time
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from .acquisition import (
    AcquisitionPolicyError, Resolution, TransportFailure, TransportRequest,
    TransportResponse, canonical_url, origin_for,
)


MAX_STATUS_LINE_BYTES = 4_096
READ_CHUNK_BYTES = 16_384
DEFAULT_DNS_TIMEOUT_MILLISECONDS = 10_000
MAX_DNS_TIMEOUT_MILLISECONDS = 30_000
_FORBIDDEN_REQUEST_HEADERS = frozenset(
    {
        "accept-encoding", "connection", "content-length", "host", "proxy-authorization",
        "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade",
        "user-agent",
    }
)
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


@dataclass(frozen=True, slots=True)
class LiveNetworkPermit:
    """Human-final operator acknowledgement for a bounded origin set."""

    run_id: str
    actor_id: str
    actor_kind: str
    authority: str
    capability_id: str
    approved_origins: tuple[str, ...]
    network_enabled: bool

    def __post_init__(self) -> None:
        if (
            not self.run_id
            or not self.actor_id
            or not self.capability_id
            or self.actor_kind != "human"
            or self.authority != "human_final"
            or not self.network_enabled
            or not 1 <= len(self.approved_origins) <= 4
        ):
            raise AcquisitionPolicyError("live_network_permit_invalid")
        normalized: list[str] = []
        for origin in self.approved_origins:
            if origin != origin_for(origin + "/") or origin in normalized:
                raise AcquisitionPolicyError("live_network_permit_origin_invalid")
            normalized.append(origin)

    @property
    def hostnames(self) -> frozenset[str]:
        return frozenset(
            str(urlsplit(origin).hostname) for origin in self.approved_origins
        )


class SystemMonotonicClock:
    def now_milliseconds(self) -> int:
        return time.monotonic_ns() // 1_000_000


def _system_resolve_addresses(
    hostname: str, timeout_milliseconds: int,
) -> tuple[str, ...]:
    """Resolve in a killable child so host resolver stalls have a hard bound."""
    import json
    import subprocess
    import sys

    program = (
        "import json,socket,sys;"
        "a=socket.getaddrinfo(sys.argv[1],443,family=socket.AF_UNSPEC,"
        "type=socket.SOCK_STREAM,proto=socket.IPPROTO_TCP);"
        "print(json.dumps(sorted({str(x[4][0]) for x in a})))"
    )
    try:
        completed = subprocess.run(
            (sys.executable, "-I", "-S", "-c", program, hostname),
            check=True, capture_output=True, text=False,
            timeout=timeout_milliseconds / 1_000,
            env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        )
        if completed.stderr or len(completed.stdout) > 65_536:
            raise ValueError("resolver child output invalid")
        value = json.loads(completed.stdout)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("resolver child response invalid")
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
        raise TransportFailure("system_dns_failed") from error
    return tuple(value)


class OptInSystemResolver:
    """Resolve only permit-bound hostnames; lazy import keeps offline startup inert."""

    def __init__(
        self, permit: LiveNetworkPermit,
        *, resolve_addresses: Callable[[str], Iterable[str]] | None = None,
        timeout_milliseconds: int = DEFAULT_DNS_TIMEOUT_MILLISECONDS,
    ) -> None:
        if (
            isinstance(timeout_milliseconds, bool)
            or not isinstance(timeout_milliseconds, int)
            or not 1 <= timeout_milliseconds <= MAX_DNS_TIMEOUT_MILLISECONDS
        ):
            raise AcquisitionPolicyError("live_resolver_timeout_invalid")
        self.permit = permit
        self.timeout_milliseconds = timeout_milliseconds
        self._resolve_addresses = resolve_addresses

    def resolve(self, hostname: str) -> Resolution:
        return self.resolve_with_timeout(hostname, self.timeout_milliseconds)

    def resolve_with_timeout(
        self, hostname: str, remaining_milliseconds: int,
    ) -> Resolution:
        if hostname not in self.permit.hostnames:
            raise AcquisitionPolicyError("live_resolver_hostname_not_permitted")
        if (
            isinstance(remaining_milliseconds, bool)
            or not isinstance(remaining_milliseconds, int)
            or remaining_milliseconds <= 0
        ):
            raise AcquisitionPolicyError("live_resolver_deadline_exhausted")
        try:
            if self._resolve_addresses is None:
                raw = _system_resolve_addresses(
                    hostname, min(self.timeout_milliseconds, remaining_milliseconds)
                )
            else:
                # Injected resolvers exist only for deterministic offline tests;
                # the live system resolver above is the killable production path.
                raw = self._resolve_addresses(hostname)
            addresses = tuple(sorted(set(raw)))
        except TransportFailure:
            raise
        except Exception as error:
            raise TransportFailure("system_dns_failed") from error
        return Resolution(hostname, addresses)


def _default_dial(address: str, timeout_seconds: float) -> Any:
    import socket

    return socket.create_connection((address, 443), timeout=timeout_seconds)


def _default_tls_wrap(sock: Any, hostname: str) -> Any:
    import ssl

    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context.wrap_socket(sock, server_hostname=hostname)


def _read_until(
    recv: Callable[[int], bytes], marker: bytes, maximum: int,
) -> tuple[bytes, bytes]:
    chunks = bytearray()
    while marker not in chunks:
        if len(chunks) >= maximum:
            raise TransportFailure("response_headers_too_large")
        data = recv(min(READ_CHUNK_BYTES, maximum + 1 - len(chunks)))
        if not isinstance(data, bytes):
            raise TransportFailure("transport_recv_type_invalid")
        if not data:
            raise TransportFailure("response_headers_truncated")
        chunks.extend(data)
    head, remainder = bytes(chunks).split(marker, 1)
    if len(head) + len(marker) > maximum:
        raise TransportFailure("response_headers_too_large")
    return head, remainder


def _parse_head(head: bytes) -> tuple[int, tuple[tuple[str, str], ...]]:
    try:
        lines = head.decode("iso-8859-1").split("\r\n")
    except UnicodeDecodeError as error:
        raise TransportFailure("response_header_encoding_invalid") from error
    if not lines or len(lines[0].encode("iso-8859-1")) > MAX_STATUS_LINE_BYTES:
        raise TransportFailure("response_status_line_invalid")
    parts = lines[0].split(" ", 2)
    if len(parts) < 2 or parts[0] not in {"HTTP/1.0", "HTTP/1.1"}:
        raise TransportFailure("response_status_line_invalid")
    try:
        status = int(parts[1])
    except ValueError as error:
        raise TransportFailure("response_status_line_invalid") from error
    headers: list[tuple[str, str]] = []
    observed: set[str] = set()
    for line in lines[1:]:
        if not line or line[:1] in {" ", "\t"} or ":" not in line:
            raise TransportFailure("response_header_invalid")
        name, value = line.split(":", 1)
        normalized = name.casefold()
        if normalized in observed:
            raise TransportFailure("response_header_duplicate")
        observed.add(normalized)
        headers.append((normalized, value.strip(" \t")))
    return status, tuple(sorted(headers))


def _header_map(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {name.casefold(): value for name, value in headers}


def _read_exact_or_eof(
    recv: Callable[[int], bytes], initial: bytes, maximum: int, length: int | None,
) -> bytes:
    body = bytearray(initial)
    target = length
    if target is not None and target > maximum:
        raise TransportFailure("response_body_too_large")
    while target is None or len(body) < target:
        if len(body) > maximum:
            raise TransportFailure("response_body_too_large")
        data = recv(min(READ_CHUNK_BYTES, maximum + 1 - len(body)))
        if not isinstance(data, bytes):
            raise TransportFailure("transport_recv_type_invalid")
        if not data:
            break
        body.extend(data)
    if len(body) > maximum:
        raise TransportFailure("response_body_too_large")
    if target is not None:
        if len(body) != target:
            raise TransportFailure("response_body_truncated_or_surplus")
    return bytes(body)


def _read_chunked(
    recv: Callable[[int], bytes], initial: bytes, maximum: int,
) -> bytes:
    buffer = bytearray(initial)
    body = bytearray()

    def ensure_line() -> bytes:
        while b"\r\n" not in buffer:
            if len(buffer) > MAX_STATUS_LINE_BYTES:
                raise TransportFailure("chunk_line_too_large")
            data = recv(READ_CHUNK_BYTES)
            if not data:
                raise TransportFailure("chunked_body_truncated")
            buffer.extend(data)
        line, remainder = bytes(buffer).split(b"\r\n", 1)
        if len(line) > MAX_STATUS_LINE_BYTES:
            raise TransportFailure("chunk_line_too_large")
        buffer[:] = remainder
        return line

    while True:
        line = ensure_line()
        token = line.split(b";", 1)[0]
        try:
            size = int(token, 16)
        except ValueError as error:
            raise TransportFailure("chunk_size_invalid") from error
        if size < 0 or len(body) + size > maximum:
            raise TransportFailure("response_body_too_large")
        while len(buffer) < size + 2:
            data = recv(min(READ_CHUNK_BYTES, size + 2 - len(buffer)))
            if not data:
                raise TransportFailure("chunked_body_truncated")
            buffer.extend(data)
        chunk = bytes(buffer[:size])
        if bytes(buffer[size:size + 2]) != b"\r\n":
            raise TransportFailure("chunk_terminator_invalid")
        del buffer[:size + 2]
        if size == 0:
            # Trailers are deliberately unsupported: they would add a second
            # header surface after the bounded policy check.
            if bytes(buffer) not in {b"", b"\r\n"}:
                raise TransportFailure("response_trailers_forbidden")
            return bytes(body)
        body.extend(chunk)


class _AbsoluteDeadline:
    def __init__(self, now: Callable[[], int], maximum_milliseconds: int) -> None:
        self._now = now
        self.maximum_milliseconds = maximum_milliseconds
        self.started = self._observe(None)
        self.last = self.started

    def _observe(self, previous: int | None) -> int:
        try:
            observed = self._now()
        except Exception as error:
            raise TransportFailure("transport_clock_failed") from error
        if (
            isinstance(observed, bool)
            or not isinstance(observed, int)
            or observed < 0
            or (previous is not None and observed < previous)
        ):
            raise TransportFailure("transport_clock_invalid")
        return observed

    def checkpoint(self) -> int:
        observed = self._observe(self.last)
        self.last = observed
        elapsed = observed - self.started
        if elapsed > self.maximum_milliseconds:
            raise TransportFailure("transport_deadline_exceeded")
        return elapsed

    def remaining_seconds(self) -> float:
        elapsed = self.checkpoint()
        remaining = self.maximum_milliseconds - elapsed
        if remaining <= 0:
            raise TransportFailure("transport_deadline_exceeded")
        return max(0.001, remaining / 1_000)

    def recv(self, sock: Any, maximum: int) -> bytes:
        sock.settimeout(self.remaining_seconds())
        value = sock.recv(maximum)
        self.checkpoint()
        return value


class OptInHttpsTransport:
    """Minimal TLS HTTP/1.1 GET transport with no proxy or ambient redirect use."""

    def __init__(
        self,
        permit: LiveNetworkPermit,
        *,
        dial: Callable[[str, float], Any] | None = None,
        tls_wrap: Callable[[Any, str], Any] | None = None,
        now_milliseconds: Callable[[], int] | None = None,
    ) -> None:
        self.permit = permit
        self._dial = dial or _default_dial
        self._tls_wrap = tls_wrap or _default_tls_wrap
        self._now = now_milliseconds or SystemMonotonicClock().now_milliseconds

    def fetch(self, request: TransportRequest) -> TransportResponse:
        url = canonical_url(request.url)
        if request.method != "GET" or origin_for(url) not in self.permit.approved_origins:
            raise AcquisitionPolicyError("live_transport_request_not_permitted")
        if not request.connect_addresses:
            raise AcquisitionPolicyError("live_transport_address_set_empty")
        parts = urlsplit(url)
        hostname = parts.hostname
        if hostname is None:
            raise AcquisitionPolicyError("live_transport_hostname_invalid")
        supplied: list[tuple[str, str]] = []
        for name, value in request.headers:
            if (
                not isinstance(name, str)
                or not isinstance(value, str)
                or _HEADER_NAME.fullmatch(name) is None
                or any(character in value for character in ("\r", "\n", "\x00"))
            ):
                raise AcquisitionPolicyError("live_transport_header_invalid")
            if name.casefold() in _FORBIDDEN_REQUEST_HEADERS:
                raise AcquisitionPolicyError("live_transport_header_forbidden")
            supplied.append((name, value))
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        try:
            target_bytes = target.encode("ascii")
        except UnicodeEncodeError as error:
            raise AcquisitionPolicyError("live_transport_target_not_ascii") from error
        headers = [
            ("host", parts.netloc), ("connection", "close"),
            ("accept-encoding", "identity"), ("user-agent", "AdaIvy-Phase4B/1"),
            *supplied,
        ]
        request_bytes = (
            b"GET " + target_bytes + b" HTTP/1.1\r\n"
            + b"".join(
                name.encode("ascii") + b": " + value.encode("utf-8") + b"\r\n"
                for name, value in headers
            )
            + b"\r\n"
        )
        if len(request_bytes) > request.max_header_bytes:
            raise AcquisitionPolicyError("live_transport_request_headers_too_large")
        deadline = _AbsoluteDeadline(self._now, request.timeout_milliseconds)
        last_error: BaseException | None = None
        for address in request.connect_addresses:
            raw = None
            secured = None
            try:
                raw = self._dial(address, deadline.remaining_seconds())
                deadline.checkpoint()
                raw.settimeout(deadline.remaining_seconds())
                secured = self._tls_wrap(raw, hostname)
                deadline.checkpoint()
                secured.settimeout(deadline.remaining_seconds())
                try:
                    peer = ipaddress.ip_address(str(secured.getpeername()[0])).compressed
                    dialed = ipaddress.ip_address(address).compressed
                except ValueError as error:
                    raise TransportFailure("connected_peer_invalid") from error
                if peer != dialed:
                    raise TransportFailure("connected_peer_dial_mismatch")
                secured.settimeout(deadline.remaining_seconds())
                secured.sendall(request_bytes)
                deadline.checkpoint()
                head, remainder = _read_until(
                    lambda maximum: deadline.recv(secured, maximum),
                    b"\r\n\r\n", request.max_header_bytes,
                )
                status, response_headers = _parse_head(head)
                mapped = _header_map(response_headers)
                encoding = mapped.get("content-encoding", "identity").casefold()
                if encoding not in {"", "identity"}:
                    raise TransportFailure("response_content_encoding_forbidden")
                transfer = mapped.get("transfer-encoding")
                content_length = mapped.get("content-length")
                if transfer is not None and content_length is not None:
                    raise TransportFailure("response_framing_ambiguous")
                if transfer is not None:
                    if transfer.casefold() != "chunked":
                        raise TransportFailure("response_transfer_encoding_forbidden")
                    body = _read_chunked(
                        lambda maximum: deadline.recv(secured, maximum),
                        remainder, request.max_body_bytes,
                    )
                else:
                    length = None
                    if content_length is not None:
                        try:
                            length = int(content_length)
                        except ValueError as error:
                            raise TransportFailure("response_content_length_invalid") from error
                        if length < 0:
                            raise TransportFailure("response_content_length_invalid")
                    body = _read_exact_or_eof(
                        lambda maximum: deadline.recv(secured, maximum),
                        remainder, request.max_body_bytes, length,
                    )
                elapsed = deadline.checkpoint()
                return TransportResponse(
                    status, response_headers, body, peer, elapsed
                )
            except (AcquisitionPolicyError, TransportFailure):
                raise
            except BaseException as error:
                last_error = error
            finally:
                for sock in (secured, raw):
                    if sock is not None:
                        try:
                            sock.close()
                        except Exception:
                            pass
            continue
        raise TransportFailure("all_permitted_addresses_failed") from last_error


__all__ = [
    "LiveNetworkPermit", "OptInHttpsTransport", "OptInSystemResolver",
    "SystemMonotonicClock",
]
