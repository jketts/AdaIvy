"""Replay a tranche from stored bytes. No transport, no credential, no network.

ADR-0065's vector replay is the model: a rebuild replays the stored artifacts and
does not call the provider again.  A transport may be passed in ONLY so a caller
can prove it was never used -- :class:`ForbiddingMetadataTransport` raises on any
call and counts the attempt, and ``pr.corpus-replay-makes-zero-network-requests``
asserts the records are reproduced with it installed and its attempt count still
zero.

Absent stored bytes are :class:`StoredResponseMissingError`.  There is no
fallback: a replay that can reach the network to fill a gap is not a replay, and
the missing-bytes case is exactly where such a fallback would hide.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .errors import (
    CorpusError, TransportCallDuringReplayError, TransportCallForbiddenError,
)
from .ingestion import ingest_from_store
from .ports import MetadataRequest, MetadataResponse


class ForbiddingMetadataTransport:
    """Raises on any call. Installed to prove the replay path never fetches."""

    def __init__(self) -> None:
        self.attempts = 0

    def fetch(self, request: MetadataRequest) -> MetadataResponse:
        self.attempts += 1
        raise TransportCallForbiddenError(
            "the corpus replay path must not reach a transport"
        )


def _attempts(transport: Any) -> int:
    if transport is None:
        return 0
    value = getattr(transport, "attempts", None)
    if value is None:
        value = getattr(transport, "call_count", None)
    if value is None:
        raise CorpusError(
            "a transport handed to the replay path must expose an attempt counter",
            code="replay_transport_uncountable",
        )
    if isinstance(value, bool) or not isinstance(value, int):
        raise CorpusError(
            "transport attempt counter is not an integer",
            code="replay_transport_uncountable",
        )
    return value


def replay_tranche(
    root: Path, plan: Mapping[str, Any], *, rights_writer: Any, recorded_at: str,
    transport: Any | None = None, expected_manifest_hash: str | None = None,
) -> dict[str, Any]:
    """Rebuild every corpus record from stored bytes and verify no fetch occurred."""

    before = _attempts(transport)
    result = ingest_from_store(
        root, plan, rights_writer=rights_writer, recorded_at=recorded_at,
        expected_manifest_hash=expected_manifest_hash,
    )
    after = _attempts(transport)
    if after != before:
        raise TransportCallDuringReplayError(
            f"a replay attempted {after - before} transport call(s)"
        )
    return result


__all__ = ["ForbiddingMetadataTransport", "replay_tranche"]
