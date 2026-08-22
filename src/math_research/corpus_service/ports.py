"""Inward-facing ports for the persistent corpus service.

The archive source is a port so the offline check can ingest a synthetic
fixture archive from disk while the (still gated, still pending) live snapshot
acquisition would produce exactly the same shape: an already-acquired,
content-hashed local archive.  There is deliberately no network transport port
in this package — querying the snapshot source is local search over
already-acquired bytes (ADR-0072 §6), and the bytes arrive through the
separately gated acquisition capability, never through ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .constants import MAX_ARCHIVE_MANIFEST_BYTES, MAX_DOCUMENT_BYTES
from .errors import ArchiveDocumentMismatchError, ArchiveManifestInvalidError


class ArchiveSource(Protocol):
    """One already-acquired, locally held snapshot archive."""

    def manifest_bytes(self) -> bytes:
        """The archive manifest bytes, canonical JSON."""

    def document_bytes(self, relative_path: str) -> bytes:
        """The exact bytes of one archived document. Absence is a refusal."""


@dataclass(frozen=True, slots=True)
class DirectoryArchiveSource:
    """An archive laid out as ``archive-manifest.json`` plus document files."""

    root: Path

    MANIFEST_FILENAME = "archive-manifest.json"

    def manifest_bytes(self) -> bytes:
        path = Path(self.root).joinpath(self.MANIFEST_FILENAME)
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ArchiveManifestInvalidError(
                f"no archive manifest at {path}"
            ) from error
        if not data or len(data) > MAX_ARCHIVE_MANIFEST_BYTES:
            raise ArchiveManifestInvalidError("archive manifest byte bound differs")
        return data

    def document_bytes(self, relative_path: str) -> bytes:
        base = Path(self.root).resolve()
        path = base.joinpath(relative_path).resolve()
        if base not in path.parents:
            raise ArchiveDocumentMismatchError(
                f"archive document path escapes the archive: {relative_path!r}"
            )
        try:
            data = path.read_bytes()
        except OSError as error:
            raise ArchiveDocumentMismatchError(
                f"archive document {relative_path!r} is absent"
            ) from error
        if not data or len(data) > MAX_DOCUMENT_BYTES:
            raise ArchiveDocumentMismatchError(
                f"archive document {relative_path!r} byte bound differs"
            )
        return data


__all__ = ["ArchiveSource", "DirectoryArchiveSource"]
