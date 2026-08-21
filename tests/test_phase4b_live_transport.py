"""Offline acceptance for the explicit Phase 4B live-network adapter."""

from __future__ import annotations

import unittest
import subprocess
from unittest.mock import patch

from math_research.phase4b.acquisition import (
    AcquisitionPolicyError, TransportFailure, TransportRequest,
)
from math_research.phase4b.live_transport import (
    LiveNetworkPermit, OptInHttpsTransport, OptInSystemResolver,
)


URL = "https://papers.example/source?q=1"


class ScriptedSocket:
    def __init__(self, response: bytes, peer: str = "93.184.216.34") -> None:
        self.response = bytearray(response)
        self.peer = peer
        self.sent = b""
        self.closed = False

    def settimeout(self, _timeout: float) -> None: pass
    def getpeername(self): return (self.peer, 443)
    def sendall(self, data: bytes) -> None: self.sent += data
    def recv(self, maximum: int) -> bytes:
        data = bytes(self.response[:maximum]); del self.response[:maximum]; return data
    def close(self) -> None: self.closed = True


class Clock:
    def __init__(self, step: int = 1) -> None: self.value = 99; self.step = step
    def __call__(self) -> int:
        self.value += self.step
        return self.value


class SlowSocket(ScriptedSocket):
    def recv(self, _maximum: int) -> bytes:
        return super().recv(1)


def permit() -> LiveNetworkPermit:
    return LiveNetworkPermit(
        "run.live.1", "human.operator", "human", "human_final",
        "capability.phase4b.live", ("https://papers.example",), True,
    )


def request(**changes) -> TransportRequest:
    values = {
        "method": "GET", "url": URL, "headers": (),
        "connect_addresses": ("93.184.216.34",),
        "timeout_milliseconds": 1_000, "max_header_bytes": 1_024,
        "max_body_bytes": 64,
    }
    values.update(changes)
    return TransportRequest(**values)


class Phase4BLiveTransportTests(unittest.TestCase):
    def transport(self, sock: ScriptedSocket) -> OptInHttpsTransport:
        return OptInHttpsTransport(
            permit(), dial=lambda _address, _timeout: sock,
            tls_wrap=lambda raw, _hostname: raw, now_milliseconds=Clock(),
        )

    def test_explicit_human_final_permit_is_required(self) -> None:
        for change in ({"network_enabled": False}, {"actor_kind": "automation"}, {"authority": "proposal"}):
            values = {
                "run_id": "run.live.1", "actor_id": "human.operator",
                "actor_kind": "human", "authority": "human_final",
                "capability_id": "capability.phase4b.live",
                "approved_origins": ("https://papers.example",),
                "network_enabled": True,
            }
            values.update(change)
            with self.assertRaises(AcquisitionPolicyError):
                LiveNetworkPermit(**values)

    def test_resolver_is_origin_bound_and_injectable_for_offline_acceptance(self) -> None:
        calls: list[str] = []
        resolver = OptInSystemResolver(
            permit(),
            resolve_addresses=lambda hostname: calls.append(hostname) or ("93.184.216.34",),
        )
        self.assertEqual(("93.184.216.34",), resolver.resolve("papers.example").addresses)
        self.assertEqual(["papers.example"], calls)
        with self.assertRaisesRegex(AcquisitionPolicyError, "not_permitted"):
            resolver.resolve("other.example")

    def test_bounded_identity_response_uses_exact_resolved_peer(self) -> None:
        sock = ScriptedSocket(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 5\r\n\r\nproof"
        )
        response = self.transport(sock).fetch(request())
        self.assertEqual(200, response.status)
        self.assertEqual(b"proof", response.body)
        self.assertEqual("93.184.216.34", response.connected_peer)
        self.assertGreater(response.elapsed_milliseconds, 0)
        self.assertLessEqual(response.elapsed_milliseconds, 1_000)
        self.assertIn(b"GET /source?q=1 HTTP/1.1\r\n", sock.sent)
        self.assertIn(b"accept-encoding: identity\r\n", sock.sent)
        self.assertTrue(sock.closed)

    def test_chunked_body_is_decoded_within_bound(self) -> None:
        sock = ScriptedSocket(
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            b"3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n"
        )
        self.assertEqual(b"abcde", self.transport(sock).fetch(request()).body)

    def test_chunk_line_already_buffered_over_bound_is_rejected(self) -> None:
        sock = ScriptedSocket(
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            + b"1" * 4_097 + b"\r\n"
        )
        with self.assertRaisesRegex(TransportFailure, "chunk_line_too_large"):
            self.transport(sock).fetch(request())

    def test_unconsumed_response_headers_are_discarded_at_the_boundary(self) -> None:
        sock = ScriptedSocket(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 5\r\n"
            b"Set-Cookie: a=1; Secure\r\nSet-Cookie: b=2; Secure\r\n"
            b"Date: Thu, 20 Aug 2026 00:00:00 GMT\r\nX-Request-Id: 7f3a\r\n\r\nproof"
        )
        response = self.transport(sock).fetch(request())
        self.assertEqual(b"proof", response.body)
        self.assertEqual(
            (("content-length", "5"), ("content-type", "text/plain")), response.headers
        )

    def test_duplicate_framing_headers_remain_a_hard_failure(self) -> None:
        cases = (
            b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Length: 6\r\n\r\nproof",
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nTransfer-Encoding: identity\r\n\r\n",
            b"HTTP/1.1 301 Moved\r\nLocation: /a\r\nLocation: /b\r\nContent-Length: 0\r\n\r\n",
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Type: text/html\r\n\r\n",
        )
        for response in cases:
            with self.subTest(response=response.split(b"\r\n")[1]):
                with self.assertRaisesRegex(TransportFailure, "response_header_duplicate"):
                    self.transport(ScriptedSocket(response)).fetch(request())

    def test_malformed_header_name_is_rejected_even_when_discarded(self) -> None:
        sock = ScriptedSocket(
            b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nX Bad Name: v\r\n\r\nproof"
        )
        with self.assertRaisesRegex(TransportFailure, "response_header_invalid"):
            self.transport(sock).fetch(request())

    def test_origin_headers_compression_and_response_bounds_fail_closed(self) -> None:
        cases = (
            (request(url="https://other.example/x"), b"", "not_permitted"),
            (request(headers=(("host", "evil.example"),)), b"", "header_forbidden"),
            (request(headers=(("x-test", "ok\r\nX-Evil: yes"),)), b"", "header_invalid"),
            (request(max_header_bytes=24), b"HTTP/1.1 200 OK\r\nX-Long: abcdefghijklmnop\r\n\r\n", "headers_too_large"),
            (request(max_body_bytes=4), b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nproof", "body_too_large"),
            (request(), b"HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 1\r\n\r\nx", "content_encoding_forbidden"),
            (request(url="https://papers.example/π"), b"", "target_not_ascii"),
        )
        for item, response, reason in cases:
            with self.subTest(reason=reason):
                sock = ScriptedSocket(response)
                with self.assertRaisesRegex((AcquisitionPolicyError, OSError), reason):
                    self.transport(sock).fetch(item)

    def test_connected_peer_must_equal_the_address_actually_dialed(self) -> None:
        sock = ScriptedSocket(
            b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n",
            peer="8.8.8.8",
        )
        with self.assertRaisesRegex(TransportFailure, "peer_dial_mismatch"):
            self.transport(sock).fetch(
                request(connect_addresses=("93.184.216.34", "8.8.8.8"))
            )

    def test_slow_drip_reads_cannot_refresh_the_absolute_deadline(self) -> None:
        sock = SlowSocket(
            b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nproof"
        )
        transport = OptInHttpsTransport(
            permit(), dial=lambda _address, _timeout: sock,
            tls_wrap=lambda raw, _hostname: raw, now_milliseconds=Clock(step=10),
        )
        with self.assertRaisesRegex(TransportFailure, "deadline_exceeded"):
            transport.fetch(request(timeout_milliseconds=200))

    def test_resolver_timeout_is_bounded_before_any_lookup(self) -> None:
        with self.assertRaisesRegex(AcquisitionPolicyError, "timeout_invalid"):
            OptInSystemResolver(permit(), timeout_milliseconds=30_001)
        resolver = OptInSystemResolver(permit(), timeout_milliseconds=10)
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(("resolver",), 0.01),
        ) as invoked:
            with self.assertRaisesRegex(TransportFailure, "system_dns_failed"):
                resolver.resolve_with_timeout("papers.example", 5)
        self.assertEqual(0.005, invoked.call_args.kwargs["timeout"])

    def test_ambient_proxy_and_redirect_behavior_do_not_exist_in_adapter(self) -> None:
        sock = ScriptedSocket(
            b"HTTP/1.1 302 Found\r\nLocation: https://archive.example/x\r\nContent-Length: 0\r\n\r\n"
        )
        response = self.transport(sock).fetch(request())
        self.assertEqual(302, response.status)
        self.assertEqual(b"", response.body)
        self.assertEqual(1, sock.sent.count(b"GET "))


if __name__ == "__main__":
    unittest.main()
