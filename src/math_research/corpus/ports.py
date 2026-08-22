"""Inward-facing corpus ports.

The clock and the sleeper are ports and not calls into :mod:`time` for one
reason: the arXiv terms fix a minimum interval of three seconds between
requests, and a bound nobody can test is a bound nobody enforces.  Injecting
both lets the acceptance suite prove the pacer refuses a too-early request
without a test suite that sleeps.

``MetadataTransport`` is deliberately narrower than
:class:`math_research.phase4b.acquisition.Transport`: it takes no headers, no
method and no redirect budget, so there is no argument through which a caller
could aim it at an e-print.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class MonotonicClock(Protocol):
    def now_milliseconds(self) -> int:
        """Return injected monotonic milliseconds; never a wall clock."""


class Sleeper(Protocol):
    def sleep_milliseconds(self, milliseconds: int) -> None:
        """Wait at least ``milliseconds``.  The pacer re-reads the clock after."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MetadataRequest:
    """One bounded GET against the pinned arXiv metadata query endpoint."""

    url: str
    timeout_milliseconds: int
    max_response_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MetadataResponse:
    status: int
    media_type: str
    body: bytes


class MetadataTransport(Protocol):
    def fetch(self, request: MetadataRequest) -> MetadataResponse:
        """Execute one metadata GET or raise. Implementations count attempts."""


class RightsWriter(Protocol):
    """Writes the per-document Phase 4A decisions ADR-0067 requires.

    ``processor`` is absent from this port on purpose.  Acquisition, retention
    and parsing are non-disclosing uses, so ADR-0064 requires ``processor:
    null``; a port that could name one would be an authorization waiting to be
    mistaken for a decision.
    """

    def write_document_rights(
        self, *, source_id: str, recorded_at: str, valid_from: str,
        valid_until: str | None,
    ) -> tuple[str, ...]: ...

    def evaluate_document_rights(self, *, source_id: str, at: str) -> dict[str, Any]: ...


__all__ = [
    "MetadataRequest",
    "MetadataResponse",
    "MetadataTransport",
    "MonotonicClock",
    "RightsWriter",
    "Sleeper",
]
