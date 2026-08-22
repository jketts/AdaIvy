"""The operator-selected AdaIvy data root and its immutable object store.

ADR-0072 §4: one operator-selected data root, outside the Git working tree,
grow-only across runs.  The live store is local operational state and is never
committed to Git, so :func:`assert_outside_git_tree` refuses a root that is
inside any Git working tree at all — the cheapest way to make "never committed"
a property instead of a habit.

The object store is content-addressed and write-once: identical bytes are a
no-op, differing bytes under the same hash are tamper evidence, and absent
bytes are a refusal rather than a re-fetch.  Parsed-span documents are stored
through the same store as canonical JSON bytes, so one immutability rule covers
every artifact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import DATA_ROOT_SCHEMA_VERSION
from .constants import HASH_PATTERN, IDENTIFIER_PATTERN, TIMESTAMP_PATTERN
from .errors import (
    CorpusArtifactDeletionForbiddenError,
    DataRootInsideGitTreeError,
    DataRootInvalidError,
    ObjectHashMismatchError,
    ObjectMissingError,
    ObjectOverwriteRefusedError,
)
from .serialization import (
    canonical_bytes,
    sealed,
    sha256_bytes,
    strict_canonical_object,
    verify_sealed,
)

MARKER_FILENAME = "data-root.json"
OBJECTS_DIRNAME = "objects"
LEDGERS_DIRNAME = "ledgers"
GENERATIONS_DIRNAME = "generations"
RIGHTS_DIRNAME = "rights"
SCRATCH_DIRNAME = "scratch"

#: Every directory ordinary cleanup must never touch.
PROTECTED_DIRNAMES = (
    OBJECTS_DIRNAME, LEDGERS_DIRNAME, GENERATIONS_DIRNAME, RIGHTS_DIRNAME,
)

MARKER_FIELDS = frozenset({
    "schema_version", "data_root_id", "layout", "initialized_at", "content_hash",
})

LAYOUT = {
    "generations": GENERATIONS_DIRNAME,
    "ledgers": LEDGERS_DIRNAME,
    "objects": OBJECTS_DIRNAME,
    "rights": RIGHTS_DIRNAME,
    "scratch": SCRATCH_DIRNAME,
}


def assert_outside_git_tree(root: Path) -> Path:
    """Refuse a data root inside any Git working tree."""

    resolved = Path(root).resolve()
    for ancestor in (resolved, *resolved.parents):
        if ancestor.joinpath(".git").exists():
            raise DataRootInsideGitTreeError(
                f"{resolved} is inside the Git working tree rooted at "
                f"{ancestor}; the live corpus store is local operational "
                "state and is never committed to Git"
            )
    return resolved


def objects_dir(root: Path) -> Path:
    return Path(root).joinpath(OBJECTS_DIRNAME)


def ledgers_dir(root: Path) -> Path:
    return Path(root).joinpath(LEDGERS_DIRNAME)


def generations_dir(root: Path) -> Path:
    return Path(root).joinpath(GENERATIONS_DIRNAME)


def rights_dir(root: Path) -> Path:
    return Path(root).joinpath(RIGHTS_DIRNAME)


def scratch_dir(root: Path) -> Path:
    return Path(root).joinpath(SCRATCH_DIRNAME)


def marker_path(root: Path) -> Path:
    return Path(root).joinpath(MARKER_FILENAME)


def initialize_data_root(
    root: Path, *, data_root_id: str, initialized_at: str,
) -> dict[str, Any]:
    """Create the layout and the sealed marker. Idempotent for the same marker."""

    resolved = assert_outside_git_tree(root)
    if not isinstance(data_root_id, str) or IDENTIFIER_PATTERN.fullmatch(data_root_id) is None:
        raise DataRootInvalidError(f"not a data root identifier: {data_root_id!r}")
    if not isinstance(initialized_at, str) or TIMESTAMP_PATTERN.fullmatch(initialized_at) is None:
        raise DataRootInvalidError(
            "initialized_at must be a canonical UTC timestamp argument, not a clock read"
        )
    marker = sealed({
        "schema_version": DATA_ROOT_SCHEMA_VERSION,
        "data_root_id": data_root_id,
        "layout": dict(LAYOUT),
        "initialized_at": initialized_at,
        "content_hash": None,
    })
    path = marker_path(resolved)
    if path.exists():
        existing = open_data_root(resolved)
        if existing["data_root_id"] != data_root_id:
            raise DataRootInvalidError(
                f"{resolved} already holds data root "
                f"{existing['data_root_id']!r}, not {data_root_id!r}"
            )
        return existing
    resolved.mkdir(parents=True, exist_ok=True)
    for name in (*PROTECTED_DIRNAMES, SCRATCH_DIRNAME):
        resolved.joinpath(name).mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(canonical_bytes(marker) + b"\n")
    temporary.replace(path)
    return marker


def open_data_root(root: Path) -> dict[str, Any]:
    """Validate an existing data root and return its marker."""

    resolved = assert_outside_git_tree(root)
    path = marker_path(resolved)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise DataRootInvalidError(f"no data root marker at {path}") from error
    marker = verify_sealed(
        strict_canonical_object(
            data, maximum=16_384, label="data root marker",
            code=DataRootInvalidError.code,
        ),
        label="data root marker", code=DataRootInvalidError.code,
    )
    if set(marker) != MARKER_FIELDS:
        raise DataRootInvalidError(
            "data root marker fields differ: "
            f"missing={sorted(MARKER_FIELDS - set(marker))}, "
            f"extra={sorted(set(marker) - MARKER_FIELDS)}"
        )
    if marker["schema_version"] != DATA_ROOT_SCHEMA_VERSION:
        raise DataRootInvalidError("data root marker schema differs")
    if marker["layout"] != LAYOUT:
        raise DataRootInvalidError("data root marker layout differs")
    if not isinstance(marker["data_root_id"], str) or IDENTIFIER_PATTERN.fullmatch(
        marker["data_root_id"]
    ) is None:
        raise DataRootInvalidError("data root marker identifier differs")
    return marker


def object_path(root: Path, object_sha256: str) -> Path:
    if not isinstance(object_sha256, str) or HASH_PATTERN.fullmatch(object_sha256) is None:
        raise ObjectMissingError(f"not a sha256 value: {object_sha256!r}")
    digest = object_sha256.removeprefix("sha256:")
    return objects_dir(root).joinpath(digest[:2], digest + ".bin")


def write_object(root: Path, body: bytes) -> str:
    """Store immutable bytes by content hash. Returns the hash."""

    if not isinstance(body, bytes) or not body:
        raise ObjectOverwriteRefusedError("an object must be nonempty bytes")
    digest = sha256_bytes(body)
    path = object_path(root, digest)
    if path.exists():
        if path.read_bytes() != body:
            raise ObjectOverwriteRefusedError(
                f"a different object already occupies {digest}"
            )
        return digest
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(body)
    temporary.replace(path)
    return digest


def read_object(root: Path, object_sha256: str) -> bytes:
    """Read stored bytes, verifying the hash. Absence is a refusal."""

    path = object_path(root, object_sha256)
    try:
        body = path.read_bytes()
    except OSError as error:
        raise ObjectMissingError(
            f"object {object_sha256} is absent from the store; a replay never "
            "re-fetches"
        ) from error
    if sha256_bytes(body) != object_sha256:
        raise ObjectHashMismatchError(
            f"stored object bytes do not hash to {object_sha256}"
        )
    return body


def object_exists(root: Path, object_sha256: str) -> bool:
    return object_path(root, object_sha256).exists()


def ordinary_cleanup(root: Path) -> tuple[str, ...]:
    """Delete run scratch only. Corpus artifacts are outside its reach.

    Returns the relative paths removed.  Asking it to clean anything under a
    protected directory is a coded refusal, not a warning.
    """

    marker = open_data_root(root)
    del marker
    resolved = Path(root).resolve()
    scratch = scratch_dir(resolved)
    removed: list[str] = []
    if scratch.exists():
        for path in sorted(scratch.rglob("*"), reverse=True):
            relative = path.relative_to(resolved)
            for protected in PROTECTED_DIRNAMES:
                if relative.parts and relative.parts[0] == protected:
                    raise CorpusArtifactDeletionForbiddenError(str(relative))
            if path.is_dir():
                path.rmdir()
            else:
                path.unlink()
            removed.append(str(relative))
    return tuple(sorted(removed))


__all__ = [
    "GENERATIONS_DIRNAME",
    "LAYOUT",
    "LEDGERS_DIRNAME",
    "MARKER_FILENAME",
    "OBJECTS_DIRNAME",
    "PROTECTED_DIRNAMES",
    "RIGHTS_DIRNAME",
    "SCRATCH_DIRNAME",
    "assert_outside_git_tree",
    "generations_dir",
    "initialize_data_root",
    "ledgers_dir",
    "marker_path",
    "object_exists",
    "object_path",
    "objects_dir",
    "open_data_root",
    "ordinary_cleanup",
    "read_object",
    "rights_dir",
    "scratch_dir",
    "write_object",
]
