"""Content-addressed filesystem artifact adapter."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from .records import ArtifactRef


class ArtifactIntegrityError(RuntimeError):
    pass


class FileArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        (self.root / "sha256").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _path(self, content_hash: str) -> Path:
        if not content_hash.startswith("sha256:"):
            raise ValueError("artifact hash must use sha256 prefix")
        digest = content_hash[7:]
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("invalid artifact sha256")
        return self.root / "sha256" / digest[:2] / digest

    def put(self, data: bytes, *, media_type: str) -> ArtifactRef:
        digest = self._digest(data)
        content_hash = f"sha256:{digest}"
        target = self._path(content_hash)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            observed = self._digest(target.read_bytes())
            if observed != digest:
                raise ArtifactIntegrityError(f"existing artifact is corrupt: {content_hash}")
        else:
            descriptor, temporary = tempfile.mkstemp(prefix=".artifact-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return ArtifactRef(content_hash=content_hash, size_bytes=len(data), media_type=media_type)

    def get(self, content_hash: str) -> bytes:
        data = self._path(content_hash).read_bytes()
        if f"sha256:{self._digest(data)}" != content_hash:
            raise ArtifactIntegrityError(f"artifact hash mismatch: {content_hash}")
        return data

    def exists(self, content_hash: str) -> bool:
        try:
            return self._path(content_hash).is_file()
        except ValueError:
            return False

