"""Append-only, hash-chained JSONL ledgers.

Acquisition, rights, lineage, tombstone and usage history each live in one
ledger file.  A record is sealed, carries a contiguous ``sequence`` and the
``content_hash`` of its predecessor, and is appended after re-verifying the
tail — so truncation, reordering, or in-place edits surface as a broken chain
rather than as silently different history.  Nothing here mutates or deletes:
superseded state is superseded by a later record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from . import LEDGER_SCHEMA_VERSION
from .constants import (
    IDENTIFIER_PATTERN, MAX_LEDGER_RECORD_BYTES, TIMESTAMP_PATTERN,
)
from .dataroot import ledgers_dir
from .errors import LedgerChainBrokenError, LedgerInvalidError
from .serialization import (
    canonical_bytes, sealed, strict_canonical_object, verify_sealed,
)

LEDGER_NAMES = ("acquisitions", "rights", "lineage", "tombstones", "usage")

RECORD_FIELDS = frozenset({
    "schema_version", "ledger", "sequence", "prev_content_hash", "kind",
    "recorded_at", "payload", "content_hash",
})


def ledger_path(root: Path, name: str) -> Path:
    if name not in LEDGER_NAMES:
        raise LedgerInvalidError(f"unknown ledger {name!r}")
    return ledgers_dir(root).joinpath(name + ".jsonl")


def _verify_record(value: Mapping[str, Any], *, name: str) -> dict[str, Any]:
    record = verify_sealed(
        value, label=f"{name} ledger record", code=LedgerInvalidError.code,
    )
    if set(record) != RECORD_FIELDS:
        raise LedgerInvalidError(
            f"{name} ledger record fields differ: "
            f"missing={sorted(RECORD_FIELDS - set(record))}, "
            f"extra={sorted(set(record) - RECORD_FIELDS)}"
        )
    if record["schema_version"] != LEDGER_SCHEMA_VERSION:
        raise LedgerInvalidError(f"{name} ledger record schema differs")
    if record["ledger"] != name:
        raise LedgerInvalidError(
            f"a record for ledger {record['ledger']!r} sits in {name!r}"
        )
    sequence = record["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise LedgerInvalidError(f"{name} ledger sequence differs")
    if not isinstance(record["kind"], str) or IDENTIFIER_PATTERN.fullmatch(
        record["kind"]
    ) is None:
        raise LedgerInvalidError(f"{name} ledger record kind differs")
    if not isinstance(record["recorded_at"], str) or TIMESTAMP_PATTERN.fullmatch(
        record["recorded_at"]
    ) is None:
        raise LedgerInvalidError(f"{name} ledger recorded_at differs")
    if not isinstance(record["payload"], Mapping):
        raise LedgerInvalidError(f"{name} ledger payload must be an object")
    return record


def read_ledger(root: Path, name: str) -> list[dict[str, Any]]:
    """Read and verify one full ledger. An absent file is an empty history."""

    path = ledger_path(root, name)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    prev_hash: str | None = None
    with path.open("rb") as handle:
        for index, line in enumerate(handle):
            record = _verify_record(strict_canonical_object(
                line.rstrip(b"\n") + b"\n", maximum=MAX_LEDGER_RECORD_BYTES,
                label=f"{name} ledger line {index}", code=LedgerInvalidError.code,
            ), name=name)
            if record["sequence"] != index:
                raise LedgerChainBrokenError(
                    f"{name} ledger line {index} declares sequence "
                    f"{record['sequence']}; ledgers are contiguous from zero"
                )
            if record["prev_content_hash"] != prev_hash:
                raise LedgerChainBrokenError(
                    f"{name} ledger line {index} does not chain to its "
                    "predecessor"
                )
            prev_hash = record["content_hash"]
            records.append(record)
    return records


def append_ledger(
    root: Path, name: str, *, kind: str, recorded_at: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the tail, then append one sealed, chained record."""

    existing = read_ledger(root, name)
    prev_hash = existing[-1]["content_hash"] if existing else None
    record = _verify_record(sealed({
        "schema_version": LEDGER_SCHEMA_VERSION,
        "ledger": name,
        "sequence": len(existing),
        "prev_content_hash": prev_hash,
        "kind": kind,
        "recorded_at": recorded_at,
        "payload": dict(payload),
        "content_hash": None,
    }), name=name)
    path = ledger_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical_bytes(record) + b"\n")
        handle.flush()
    return record


__all__ = ["LEDGER_NAMES", "RECORD_FIELDS", "append_ledger", "ledger_path", "read_ledger"]
