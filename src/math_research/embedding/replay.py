"""Replay a partition from bytes. No provider, no credential, no network.

`TECHNICAL_BLUEPRINT.md:1667-1671`: "A rebuild replays those artifacts and does
not call the provider again." A gateway may be passed in ONLY so a caller can
prove it was never used: `ForbiddingEmbeddingGateway` raises on any call, and
`pr.rebuild-makes-no-provider-call` asserts the manifest hash is reproduced with
it installed and its attempt count still zero.

This module is on the replay path and is swept by :mod:`readpath`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import EmbeddingError
from .partition import PARTITION_SCHEMA_VERSION, Partition, PartitionKey, load_partition

REPLAY_REPORT_SCHEMA_VERSION = "adaivy.vector-partition-replay-report.v1"


def _attempts(gateway: Any) -> int:
    value = getattr(gateway, "attempts", None)
    if value is None:
        value = getattr(gateway, "call_count", None)
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool):
        raise EmbeddingError("gateway attempt counter is not an integer",
                             code="replay_gateway_uncountable")
    return value


def replay_partition(
    root: Path, key: PartitionKey, *, gateway: Any | None = None,
    expected_manifest_hash: str | None = None,
) -> tuple[Partition, dict[str, Any]]:
    """Load, verify and report. Raises if a provider was touched at all."""

    before = _attempts(gateway) if gateway is not None else 0
    partition = load_partition(root, key)
    after = _attempts(gateway) if gateway is not None else 0
    if after != before:
        raise EmbeddingError(
            "a replay attempted a provider call",
            code="provider_call_during_replay",
        )
    if expected_manifest_hash is not None and partition.manifest_hash != expected_manifest_hash:
        raise EmbeddingError(
            f"replayed manifest hash {partition.manifest_hash} differs from "
            f"expected {expected_manifest_hash}",
            code="manifest_hash_mismatch",
        )
    report = {
        "schema_version": REPLAY_REPORT_SCHEMA_VERSION,
        "manifest_schema_version": PARTITION_SCHEMA_VERSION,
        "partition_key": partition.key.payload(),
        "partition_key_string": partition.key.key_string(),
        "corpus_provenance": partition.corpus_provenance,
        "is_project_authored": partition.is_project_authored,
        "manifest_hash": partition.manifest_hash,
        "vector_count": partition.vector_count,
        "document_ids": list(partition.document_ids()),
        "provider_calls": 0,
        "network_requests": 0,
        "artifact_content_hashes": [
            partition.vector(item).content_hash for item in partition.document_ids()
        ],
        "creates_epistemic_warrant": False,
        "asserts_source_applicability": False,
        "novelty_status": "not_assessed",
        "significance_status": "not_assessed",
    }
    return partition, report


__all__ = ["REPLAY_REPORT_SCHEMA_VERSION", "replay_partition"]
