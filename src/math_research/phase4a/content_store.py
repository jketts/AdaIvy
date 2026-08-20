"""Descriptor-anchored, per-source deletable Phase 4A content storage."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import MAX_SOURCE_BYTES
from .serialization import canonical_bytes


class ContentStoreError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PublishedObject:
    device: int
    inode: int
    byte_length: int
    sha256: str


_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_HAS_NOFOLLOW = hasattr(os, "O_NOFOLLOW")
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_READ_FLAGS = os.O_RDONLY | _CLOEXEC | _NOFOLLOW | _NONBLOCK
_DIR_FLAGS = os.O_RDONLY | _CLOEXEC | _NOFOLLOW | _DIRECTORY


def _read_descriptor(descriptor: int, *, max_bytes: int) -> bytes:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError("Phase 4A content must be a regular file")
    if metadata.st_size > max_bytes:
        raise ValueError(f"Phase 4A content exceeds {max_bytes} bytes")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(64 * 1024, max_bytes + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"Phase 4A content exceeds {max_bytes} bytes")
        chunks.append(chunk)


def read_bounded_regular_file(path: Path, *, max_bytes: int) -> bytes:
    """Open one explicit regular file fail-closed, including FIFOs and symlinks."""

    before = None
    if not _HAS_NOFOLLOW:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode):
            raise OSError("Phase 4A content must be a regular file")
    descriptor = os.open(path, _READ_FLAGS)
    try:
        if before is not None:
            opened = os.fstat(descriptor)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise OSError("Phase 4A input changed while opening")
        return _read_descriptor(descriptor, max_bytes=max_bytes)
    finally:
        os.close(descriptor)


def read_local_text(path: Path, *, max_bytes: int = MAX_SOURCE_BYTES) -> bytes:
    return read_bounded_regular_file(path, max_bytes=max_bytes)


def read_interchange_file(path: Path, *, max_bytes: int) -> bytes:
    return read_bounded_regular_file(path, max_bytes=max_bytes)


class Phase4ContentStore:
    """No-dedup content boundary secured beneath verified directory descriptors."""

    def __init__(self, root: Path) -> None:
        if not _HAS_NOFOLLOW or not os.supports_dir_fd:
            raise ContentStoreError("secure descriptor-relative content storage is unavailable")
        self.root = root.absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise ContentStoreError("Phase 4A content root must be a real directory")
        self.objects = self.root / "objects"
        self.temporary = self.root / "temporary"
        self.objects.mkdir(exist_ok=True)
        self.temporary.mkdir(exist_ok=True)
        self._root_fd = os.open(self.root, _DIR_FLAGS)
        self._objects_fd: int | None = None
        self._temporary_fd: int | None = None
        try:
            self._objects_fd = self._open_dir("objects", self._root_fd)
            self._temporary_fd = self._open_dir("temporary", self._root_fd)
        except BaseException:
            if self._objects_fd is not None:
                os.close(self._objects_fd)
            os.close(self._root_fd)
            raise

    def close(self) -> None:
        for name in ("_temporary_fd", "_objects_fd", "_root_fd"):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, name, None)

    @staticmethod
    def object_key(source_id: str) -> str:
        return hashlib.sha256(source_id.encode("utf-8")).hexdigest()

    def object_id(self, source_id: str) -> str:
        return "phase4-content." + self.object_key(source_id)[:32]

    def _source_name(self, source_id: str) -> str:
        return self.object_key(source_id)

    def _deleting_name(self, source_id: str) -> str:
        return ".deleting-" + self.object_key(source_id)

    def _source_root(self, source_id: str) -> Path:
        return self.objects / self._source_name(source_id)

    def _deleting_root(self, source_id: str) -> Path:
        return self.objects / self._deleting_name(source_id)

    def source_path(self, source_id: str) -> Path:
        return self._source_root(source_id) / "source.bin"

    def card_path(self, source_id: str, card_id: str) -> Path:
        key = hashlib.sha256(card_id.encode("utf-8")).hexdigest()
        return self._source_root(source_id) / "cards" / f"{key}.json"

    @staticmethod
    def _open_dir(name: str, parent_fd: int) -> int:
        descriptor = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise ContentStoreError("content-store component is not a directory")
        return descriptor

    @staticmethod
    def _revalidate_dir(name: str, parent_fd: int, descriptor: int) -> None:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise ContentStoreError("content-store directory component changed during operation")

    @staticmethod
    def _mkdir(name: str, parent_fd: int) -> None:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            descriptor = Phase4ContentStore._open_dir(name, parent_fd)
            os.close(descriptor)

    @staticmethod
    def _exists(name: str, parent_fd: int) -> bool:
        try:
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def _read_file(name: str, parent_fd: int, *, max_bytes: int) -> bytes:
        descriptor = os.open(name, _READ_FLAGS, dir_fd=parent_fd)
        try:
            return _read_descriptor(descriptor, max_bytes=max_bytes)
        finally:
            os.close(descriptor)

    @staticmethod
    def _require_regular_identity(
        metadata: os.stat_result, *, expected: os.stat_result | None = None,
        byte_length: int, links: int,
    ) -> None:
        if not stat.S_ISREG(metadata.st_mode):
            raise ContentStoreError("published content is not a regular file")
        if metadata.st_size != byte_length or metadata.st_nlink != links:
            raise ContentStoreError("published content size or link identity differs")
        if expected is not None and (
            metadata.st_dev, metadata.st_ino
        ) != (
            expected.st_dev, expected.st_ino
        ):
            raise ContentStoreError("published content inode identity differs")

    @staticmethod
    def _unlink_matching_entry(
        name: str, parent_fd: int, expected: os.stat_result | None,
    ) -> None:
        """Unlink only a bound inode, or a symlink entry without following it."""

        try:
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(current.st_mode):
            os.unlink(name, dir_fd=parent_fd)
            return
        if stat.S_ISDIR(current.st_mode) or expected is None:
            return
        if (current.st_dev, current.st_ino) == (expected.st_dev, expected.st_ino):
            os.unlink(name, dir_fd=parent_fd)

    def _atomic_write(self, target_name: str, target_fd: int, data: bytes) -> PublishedObject:
        temporary_name = "phase4-content-" + secrets.token_hex(16)
        retired_name = temporary_name + ".retired"
        descriptor = os.open(
            temporary_name, os.O_RDWR | os.O_CREAT | os.O_EXCL | _CLOEXEC | _NOFOLLOW,
            0o600, dir_fd=self._temporary_fd,
        )
        expected_hash = "sha256:" + hashlib.sha256(data).hexdigest()
        initial = os.fstat(descriptor)
        temporary_cleanup: os.stat_result | None = initial
        retired_cleanup: os.stat_result | None = None
        target_cleanup: os.stat_result | None = None
        published_descriptor = -1
        try:
            self._require_regular_identity(initial, byte_length=0, links=1)
            offset = 0
            written_hash = hashlib.sha256()
            while offset < len(data):
                count = os.write(descriptor, data[offset:])
                if count <= 0:
                    raise OSError("content-store write made no progress")
                written_hash.update(data[offset:offset + count])
                offset += count
            if "sha256:" + written_hash.hexdigest() != expected_hash:
                raise ContentStoreError("temporary content hash differs while writing")
            os.fsync(descriptor)
            written = os.fstat(descriptor)
            self._require_regular_identity(
                written, expected=initial, byte_length=len(data), links=1,
            )

            # Bind the directory entry to a separately opened descriptor immediately
            # before publication, without following a substituted symlink.
            binding_descriptor = os.open(temporary_name, _READ_FLAGS, dir_fd=self._temporary_fd)
            try:
                bound = os.fstat(binding_descriptor)
                temporary_entry = os.stat(
                    temporary_name, dir_fd=self._temporary_fd, follow_symlinks=False,
                )
                temporary_cleanup = bound
                self._require_regular_identity(
                    bound, expected=written, byte_length=len(data), links=1,
                )
                self._require_regular_identity(
                    temporary_entry, expected=bound, byte_length=len(data), links=1,
                )
            finally:
                os.close(binding_descriptor)

            if self._exists(target_name, target_fd):
                raise ContentStoreError("published content destination already exists")

            # An exclusive hard-link reservation makes destination creation
            # no-clobber while preserving the retained temporary inode.
            os.link(
                temporary_name, target_name,
                src_dir_fd=self._temporary_fd, dst_dir_fd=target_fd,
                follow_symlinks=False,
            )
            reserved = os.stat(target_name, dir_fd=target_fd, follow_symlinks=False)
            target_cleanup = reserved
            self._require_regular_identity(
                reserved, expected=written, byte_length=len(data), links=2,
            )

            # Retire the temporary pathname within its own directory. Moving it
            # over the durable destination would let a last-moment symlink
            # substitution become briefly visible at the published path before
            # verification and rollback.
            os.replace(
                temporary_name, retired_name,
                src_dir_fd=self._temporary_fd, dst_dir_fd=self._temporary_fd,
            )
            retired = os.stat(
                retired_name, dir_fd=self._temporary_fd, follow_symlinks=False,
            )
            retired_cleanup = retired
            self._require_regular_identity(
                retired, expected=written, byte_length=len(data), links=2,
            )
            os.unlink(retired_name, dir_fd=self._temporary_fd)
            retired_cleanup = None

            published_descriptor = os.open(target_name, _READ_FLAGS, dir_fd=target_fd)
            published = os.fstat(published_descriptor)
            target_cleanup = published
            published_entry = os.stat(
                target_name, dir_fd=target_fd, follow_symlinks=False,
            )
            self._require_regular_identity(
                published, expected=written, byte_length=len(data), links=1,
            )
            self._require_regular_identity(
                published_entry, expected=published, byte_length=len(data), links=1,
            )
            observed_hash = "sha256:" + hashlib.sha256(
                _read_descriptor(published_descriptor, max_bytes=len(data))
            ).hexdigest()
            if observed_hash != expected_hash:
                raise ContentStoreError("published content hash differs")
            os.fsync(published_descriptor)
            os.fsync(target_fd)
            os.fsync(self._temporary_fd)
            return PublishedObject(
                published.st_dev, published.st_ino, published.st_size, observed_hash,
            )
        except BaseException:
            try:
                self._unlink_matching_entry(
                    temporary_name, self._temporary_fd, temporary_cleanup,
                )
            except OSError:
                pass
            try:
                self._unlink_matching_entry(
                    retired_name, self._temporary_fd, retired_cleanup,
                )
            except OSError:
                pass
            try:
                current_target = os.stat(
                    target_name, dir_fd=target_fd, follow_symlinks=False,
                )
                if stat.S_ISLNK(current_target.st_mode):
                    target_cleanup = current_target
            except FileNotFoundError:
                pass
            try:
                self._unlink_matching_entry(target_name, target_fd, target_cleanup)
            except OSError:
                pass
            try:
                os.fsync(target_fd)
                os.fsync(self._temporary_fd)
            except OSError:
                pass
            raise
        finally:
            if published_descriptor >= 0:
                os.close(published_descriptor)
            os.close(descriptor)

    def _clear_open_directory(self, descriptor: int) -> None:
        for child in os.listdir(descriptor):
            metadata = os.stat(child, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                child_fd = self._open_dir(child, descriptor)
                try:
                    self._clear_open_directory(child_fd)
                finally:
                    os.close(child_fd)
                os.rmdir(child, dir_fd=descriptor)
            else:
                os.unlink(child, dir_fd=descriptor)

    def _remove_created_source(self, source_name: str, source_fd: int) -> None:
        """Remove a failed object by its retained directory identity."""

        identity = os.fstat(source_fd)
        self._clear_open_directory(source_fd)
        for child in os.listdir(self._objects_fd):
            metadata = os.stat(child, dir_fd=self._objects_fd, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode) or (
                metadata.st_dev, metadata.st_ino
            ) != (
                identity.st_dev, identity.st_ino
            ):
                continue
            checked = self._open_dir(child, self._objects_fd)
            try:
                self._revalidate_dir(child, self._objects_fd, checked)
            finally:
                os.close(checked)
            os.rmdir(child, dir_fd=self._objects_fd)
            break

        # A replacement at the expected name is removed only when it is a
        # symlink entry; its target is never followed or modified.
        try:
            substitute = os.stat(
                source_name, dir_fd=self._objects_fd, follow_symlinks=False,
            )
        except FileNotFoundError:
            substitute = None
        if substitute is not None and stat.S_ISLNK(substitute.st_mode):
            os.unlink(source_name, dir_fd=self._objects_fd)
        os.fsync(self._objects_fd)

    def put_source(self, source_id: str, data: bytes) -> str:
        source_name = self._source_name(source_id)
        if self._exists(source_name, self._objects_fd) or self._exists(self._deleting_name(source_id), self._objects_fd):
            raise ContentStoreError("Phase 4A source content object already exists")
        self._mkdir(source_name, self._objects_fd)
        source_fd = self._open_dir(source_name, self._objects_fd)
        try:
            self._mkdir("cards", source_fd)
            self._atomic_write("source.bin", source_fd, data)
            self._revalidate_dir(source_name, self._objects_fd, source_fd)
        except BaseException:
            try:
                self._remove_created_source(source_name, source_fd)
            except (ContentStoreError, OSError):
                pass
            os.close(source_fd)
            raise
        os.close(source_fd)
        return self.object_id(source_id)

    def read_source(self, source_id: str) -> bytes:
        source_fd = self._open_dir(self._source_name(source_id), self._objects_fd)
        try:
            return self._read_file("source.bin", source_fd, max_bytes=MAX_SOURCE_BYTES)
        finally:
            os.close(source_fd)

    def put_card(self, source_id: str, card_id: str, value: dict[str, Any]) -> None:
        source_fd = self._open_dir(self._source_name(source_id), self._objects_fd)
        try:
            self._read_file("source.bin", source_fd, max_bytes=MAX_SOURCE_BYTES)
            cards_fd = self._open_dir("cards", source_fd)
            try:
                name = hashlib.sha256(card_id.encode("utf-8")).hexdigest() + ".json"
                data = canonical_bytes(value)
                if self._exists(name, cards_fd):
                    if self._read_file(name, cards_fd, max_bytes=MAX_SOURCE_BYTES) != data:
                        raise ContentStoreError("evidence-card content cannot be rewritten")
                    return
                self._atomic_write(name, cards_fd, data)
                self._revalidate_dir("cards", source_fd, cards_fd)
                self._revalidate_dir(self._source_name(source_id), self._objects_fd, source_fd)
            finally:
                os.close(cards_fd)
        finally:
            os.close(source_fd)

    def read_card(self, source_id: str, card_id: str) -> dict[str, Any]:
        source_fd = self._open_dir(self._source_name(source_id), self._objects_fd)
        try:
            cards_fd = self._open_dir("cards", source_fd)
            try:
                name = hashlib.sha256(card_id.encode("utf-8")).hexdigest() + ".json"
                data = self._read_file(name, cards_fd, max_bytes=MAX_SOURCE_BYTES)
            finally:
                os.close(cards_fd)
        finally:
            os.close(source_fd)
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ContentStoreError("evidence-card content is malformed") from error
        if not isinstance(value, dict) or canonical_bytes(value) != data:
            raise ContentStoreError("evidence-card content is malformed or noncanonical")
        return value

    def remove_card(self, source_id: str, card_id: str) -> None:
        source_fd = self._open_dir(self._source_name(source_id), self._objects_fd)
        try:
            cards_fd = self._open_dir("cards", source_fd)
            try:
                name = hashlib.sha256(card_id.encode("utf-8")).hexdigest() + ".json"
                try:
                    os.unlink(name, dir_fd=cards_fd)
                except FileNotFoundError:
                    pass
            finally:
                os.close(cards_fd)
        finally:
            os.close(source_fd)

    def _remove_tree(self, name: str, parent_fd: int) -> None:
        try:
            descriptor = self._open_dir(name, parent_fd)
        except FileNotFoundError:
            return
        try:
            for child in os.listdir(descriptor):
                metadata = os.stat(child, dir_fd=descriptor, follow_symlinks=False)
                if stat.S_ISDIR(metadata.st_mode):
                    self._remove_tree(child, descriptor)
                elif stat.S_ISREG(metadata.st_mode):
                    os.unlink(child, dir_fd=descriptor)
                else:
                    raise ContentStoreError("unexpected content-store entry")
        finally:
            os.close(descriptor)
        os.rmdir(name, dir_fd=parent_fd)

    def remove_source(self, source_id: str) -> None:
        active = self._source_name(source_id)
        deleting = self._deleting_name(source_id)
        if self._exists(active, self._objects_fd):
            if self._exists(deleting, self._objects_fd):
                self._remove_tree(deleting, self._objects_fd)
            os.replace(active, deleting, src_dir_fd=self._objects_fd, dst_dir_fd=self._objects_fd)
            os.fsync(self._objects_fd)
        self._remove_tree(deleting, self._objects_fd)

    def source_state(self, source_id: str) -> str:
        active = self._exists(self._source_name(source_id), self._objects_fd)
        deleting = self._exists(self._deleting_name(source_id), self._objects_fd)
        if active and deleting:
            return "ambiguous"
        return "active" if active else "deleting" if deleting else "absent"

    def source_absent(self, source_id: str) -> bool:
        return self.source_state(source_id) == "absent"

    def object_names(self) -> tuple[str, ...]:
        return tuple(sorted(os.listdir(self._objects_fd)))

    def root_names(self) -> tuple[str, ...]:
        return tuple(sorted(os.listdir(self._root_fd)))

    def source_names(self, source_id: str) -> tuple[str, ...]:
        source_fd = self._open_dir(self._source_name(source_id), self._objects_fd)
        try:
            return tuple(sorted(os.listdir(source_fd)))
        finally:
            os.close(source_fd)

    def card_names(self, source_id: str) -> tuple[str, ...]:
        source_fd = self._open_dir(self._source_name(source_id), self._objects_fd)
        try:
            cards_fd = self._open_dir("cards", source_fd)
            try:
                return tuple(sorted(os.listdir(cards_fd)))
            finally:
                os.close(cards_fd)
        finally:
            os.close(source_fd)

    def clear_temporary(self) -> None:
        for child in os.listdir(self._temporary_fd):
            metadata = os.stat(child, dir_fd=self._temporary_fd, follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                self._remove_tree(child, self._temporary_fd)
            elif stat.S_ISREG(metadata.st_mode):
                os.unlink(child, dir_fd=self._temporary_fd)
            else:
                raise ContentStoreError("unexpected temporary content-store entry")

    def temporary_empty(self) -> bool:
        return not os.listdir(self._temporary_fd)
