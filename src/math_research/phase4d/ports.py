"""Outward ports for paginated Phase 4D discovery (ADR-0081).

Discovery v2 talks to the network only through these injected ports. The
ordinary repository path constructs fake implementations; live adapters are an
explicit operator opt-in exactly as in Phase 4B.
"""

from __future__ import annotations

from typing import Protocol

from ..phase4b.acquisition import (
    Resolution, TransportRequest, TransportResponse,
)


class DiscoveryResolver(Protocol):
    """Resolve one provider hostname without ambient DNS state."""

    def resolve(self, hostname: str) -> Resolution:
        """Return the addresses the transport may connect to."""


class DiscoveryTransport(Protocol):
    """Execute one bounded HTTPS GET against an approved provider origin."""

    def fetch(self, request: TransportRequest) -> TransportResponse:
        """Execute the request or raise ``TransportFailure``."""


class MonotonicClock(Protocol):
    """Injected monotonic milliseconds for rate-limit accounting."""

    def now_milliseconds(self) -> int:
        """Return monotonic milliseconds; never wall-clock semantics."""


class IntervalSleeper(Protocol):
    """Injected wait used to honour per-provider minimum request intervals."""

    def sleep_milliseconds(self, milliseconds: int) -> None:
        """Block for at least the requested interval."""


__all__ = [
    "DiscoveryResolver", "DiscoveryTransport", "IntervalSleeper",
    "MonotonicClock", "Resolution", "TransportRequest", "TransportResponse",
]
