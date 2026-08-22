"""The explicit named gate for live snapshot acquisition.

Ingestion in this package is local: it reads an already-acquired archive from
disk.  Acquiring the archive itself sends traffic to a third party under its
terms, so it stays behind this activation record exactly as the ADR-0067
metadata slice's live path does.  The shipped record is
``pending_owner_activation`` and no network fetcher for a snapshot archive
exists in this package at all; when one is built under its own gate, it must
refuse without an ACTIVE record, the exact acknowledgement string, and the
human operator identity.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import SNAPSHOT_ACTIVATION_SCHEMA_VERSION
from .constants import (
    CAPABILITY_ID,
    IDENTIFIER_PATTERN,
    LIVE_SNAPSHOT_ACKNOWLEDGEMENT,
    MAX_ACTIVATION_BYTES,
    MAX_TRANCHE_DOCUMENTS,
    MAX_TRANCHE_TOTAL_BYTES,
)
from .errors import SnapshotAcquisitionNotActiveError, SnapshotActivationInvalidError
from .serialization import strict_canonical_object, verify_sealed

#: The exact content hash of
#: ``config/corpus-service-snapshot-activation-v1.json`` as shipped.
PRODUCTION_ACTIVATION_HASH = (
    "sha256:22674615ee25d1af2b9a3bc2e720cf8c158e74be9953a637e5bb0447383177fc"
)

STATUS_ACTIVE = "active"
STATUS_PENDING = "pending_owner_activation"
STATUS_VALUES = (STATUS_ACTIVE, STATUS_PENDING)

ACTIVATION_FIELDS = frozenset({
    "schema_version", "status", "capability_id", "acknowledgement_required",
    "max_tranche_documents", "max_tranche_total_bytes", "crawling_allowed",
    "result_following_allowed", "credentials_allowed",
    "autonomous_origin_selection", "network_discovery_origin",
    "licence_diligence_adr", "authorized_by", "content_hash",
})
_AUTHORIZED_BY_FIELDS = frozenset({"actor_id", "actor_kind", "authority"})

_PINNED: dict[str, Any] = {
    "schema_version": SNAPSHOT_ACTIVATION_SCHEMA_VERSION,
    "capability_id": CAPABILITY_ID,
    "acknowledgement_required": LIVE_SNAPSHOT_ACKNOWLEDGEMENT,
    "max_tranche_documents": MAX_TRANCHE_DOCUMENTS,
    "max_tranche_total_bytes": MAX_TRANCHE_TOTAL_BYTES,
    "crawling_allowed": False,
    "result_following_allowed": False,
    "credentials_allowed": False,
    "autonomous_origin_selection": False,
    # ADR-0072 §6: Crossref remains the only network discovery origin; a
    # snapshot is an acquisition, and querying it is local search.
    "network_discovery_origin": "crossref_only_per_adr_0051",
    "licence_diligence_adr": "adr-0067",
}


def validate_snapshot_activation(value: Mapping[str, Any]) -> dict[str, Any]:
    record = verify_sealed(
        value, label="snapshot acquisition activation",
        code=SnapshotActivationInvalidError.code,
    )
    if set(record) != ACTIVATION_FIELDS:
        raise SnapshotActivationInvalidError(
            "snapshot activation fields differ: "
            f"missing={sorted(ACTIVATION_FIELDS - set(record))}, "
            f"extra={sorted(set(record) - ACTIVATION_FIELDS)}"
        )
    if record["status"] not in STATUS_VALUES:
        raise SnapshotActivationInvalidError(
            f"unknown activation status {record['status']!r}"
        )
    differing = sorted(key for key, item in _PINNED.items() if record.get(key) != item)
    if differing:
        raise SnapshotActivationInvalidError(
            "snapshot activation record differs from the bounds pinned in "
            f"code for {differing}"
        )
    authorized_by = record["authorized_by"]
    if (
        not isinstance(authorized_by, Mapping)
        or set(authorized_by) != _AUTHORIZED_BY_FIELDS
        or not isinstance(authorized_by.get("actor_id"), str)
        or IDENTIFIER_PATTERN.fullmatch(authorized_by["actor_id"]) is None
        or authorized_by.get("actor_kind") != "human"
        or authorized_by.get("authority") != "human_final"
    ):
        raise SnapshotActivationInvalidError(
            "a snapshot activation record is a human-final act and must name "
            "one human actor"
        )
    return record


def load_snapshot_activation(data: bytes) -> dict[str, Any]:
    return validate_snapshot_activation(strict_canonical_object(
        data, maximum=MAX_ACTIVATION_BYTES,
        label="snapshot acquisition activation",
        code=SnapshotActivationInvalidError.code,
    ))


def load_production_activation(data: bytes) -> dict[str, Any]:
    """As :func:`load_snapshot_activation`, plus the hash pinned here."""

    record = load_snapshot_activation(data)
    if record["content_hash"] != PRODUCTION_ACTIVATION_HASH:
        raise SnapshotActivationInvalidError(
            "the snapshot activation record does not match the hash pinned "
            f"in code: {record['content_hash']} != {PRODUCTION_ACTIVATION_HASH}"
        )
    return record


def require_active(record: Mapping[str, Any], *, acknowledgement: str | None) -> dict[str, Any]:
    """Live snapshot acquisition needs an ACTIVE record and the exact string."""

    validated = validate_snapshot_activation(record)
    if validated["status"] != STATUS_ACTIVE:
        raise SnapshotAcquisitionNotActiveError(
            "live open-access snapshot acquisition needs an active record; "
            f"this one is {validated['status']!r}"
        )
    if acknowledgement != LIVE_SNAPSHOT_ACKNOWLEDGEMENT:
        raise SnapshotAcquisitionNotActiveError(
            "live open-access snapshot acquisition requires the exact "
            "acknowledgement " + LIVE_SNAPSHOT_ACKNOWLEDGEMENT
        )
    return validated


__all__ = [
    "ACTIVATION_FIELDS",
    "PRODUCTION_ACTIVATION_HASH",
    "STATUS_ACTIVE",
    "STATUS_PENDING",
    "STATUS_VALUES",
    "load_production_activation",
    "load_snapshot_activation",
    "require_active",
    "validate_snapshot_activation",
]
