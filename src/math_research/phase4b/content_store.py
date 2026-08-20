"""Source-specific deletable content storage for Phase 4B.

The secure descriptor-relative implementation is reused from Phase 4A, while
Phase 4B owns a separate root so rich source media cannot be mistaken for the
sealed Phase 4A UTF-8 ``text/plain`` profile. Metadata and canonical exports
refer only to object IDs, hashes, lengths, and anchors; source plaintext stays
inside this boundary.
"""

from __future__ import annotations

from pathlib import Path

from ..phase4a.content_store import ContentStoreError, Phase4ContentStore
from ..phase4a.serialization import sha256_bytes
from . import MAX_SOURCE_BYTES


class Phase4BContentStore:
    """No-dedup per-source objects with idempotent verified publication."""

    def __init__(self, root: Path) -> None:
        self._store = Phase4ContentStore(root)
        self.root = self._store.root

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> "Phase4BContentStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def object_id(self, source_id: str) -> str:
        return self._store.object_id(source_id)

    def publish(self, source_id: str, data: bytes, *, expected_hash: str) -> str:
        if not data or len(data) > MAX_SOURCE_BYTES:
            raise ValueError("Phase 4B source byte bound violated")
        if sha256_bytes(data) != expected_hash:
            raise ContentStoreError("Phase 4B source hash differs before publication")
        return self._store.put_source(source_id, data)

    def read(self, source_id: str, *, expected_hash: str) -> bytes:
        data = self._store.read_source(source_id)
        if len(data) > MAX_SOURCE_BYTES or sha256_bytes(data) != expected_hash:
            raise ContentStoreError("Phase 4B retained source integrity differs")
        return data

    def remove(self, source_id: str) -> None:
        self._store.remove_source(source_id)

    def state(self, source_id: str) -> str:
        return self._store.source_state(source_id)

    def verify_absent(self, source_id: str) -> None:
        if not self._store.source_absent(source_id):
            raise ContentStoreError("Phase 4B source content remains")

    def verify_inventory(self, active_source_ids: set[str]) -> None:
        if set(self._store.root_names()) != {"objects", "temporary"}:
            raise ContentStoreError("Phase 4B content root contains undeclared data")
        expected = {self._store.object_key(source_id) for source_id in active_source_ids}
        if set(self._store.object_names()) != expected:
            raise ContentStoreError("Phase 4B content inventory drift")
        for source_id in active_source_ids:
            if self._store.source_state(source_id) != "active":
                raise ContentStoreError("Phase 4B active source content is missing")
            if set(self._store.source_names(source_id)) != {"cards", "source.bin"}:
                raise ContentStoreError("Phase 4B source object contains undeclared data")
            if self._store.card_names(source_id):
                raise ContentStoreError("Phase 4B reconstructive parse plaintext was persisted")
        if not self._store.temporary_empty():
            raise ContentStoreError("Phase 4B temporary content remains")


__all__ = ["ContentStoreError", "Phase4BContentStore"]
