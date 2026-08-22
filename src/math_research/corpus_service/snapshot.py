"""Snapshot archive manifests and the operator-configured bounded tranche.

ADR-0067 option C stands: one authorized bulk open-access snapshot, one
archive, one version, one content hash, no traversal of anything inside it.
The archive manifest is the human tranche-selection act made checkable: it
lists exactly the documents in scope with their exact per-document licence
metadata, and ingestion refuses an archive whose totals exceed the tranche
config's pinned bounds rather than truncating it — a tranche is a chosen,
content-hashed subset, never "the first N that fit".
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from . import ARCHIVE_MANIFEST_SCHEMA_VERSION, TRANCHE_CONFIG_SCHEMA_VERSION
from .constants import (
    HASH_PATTERN,
    IDENTIFIER_PATTERN,
    MAX_ARCHIVE_MANIFEST_BYTES,
    MAX_DOCUMENT_BYTES,
    MAX_TRANCHE_CONFIG_BYTES,
    MAX_TRANCHE_DOCUMENTS_STRUCTURAL_CEILING,
    MAX_TRANCHE_TOTAL_BYTES,
    PROVIDER,
    RELATIVE_PATH_PATTERN_TEXT,
)
from .errors import ArchiveManifestInvalidError, TrancheBoundExceededError, TrancheConfigInvalidError
from .serialization import strict_canonical_object, verify_sealed

ARCHIVE_MANIFEST_FIELDS = frozenset({
    "schema_version", "provider", "archive_id", "archive_version", "documents",
    "document_count", "total_bytes", "content_hash",
})
_DOCUMENT_FIELDS = frozenset({
    "document_id", "relative_path", "media_type", "byte_count", "sha256",
    "licence",
})
_LICENCE_FIELDS = frozenset({"licence", "licence_url"})

TRANCHE_CONFIG_FIELDS = frozenset({
    "schema_version", "tranche_id", "archive_manifest_hash",
    "policy_content_hash", "max_documents", "max_total_bytes",
    "max_document_bytes", "selected_by", "content_hash",
})
_SELECTED_BY_FIELDS = frozenset({"actor_id", "actor_kind", "authority"})

_RELATIVE_PATH_PATTERN = re.compile(RELATIVE_PATH_PATTERN_TEXT)
_MEDIA_TYPE_PATTERN = re.compile(r"^[a-z0-9!#$&^_.+-]{1,64}/[a-z0-9!#$&^_.+-]{1,64}$")


def _validate_document(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _DOCUMENT_FIELDS:
        raise ArchiveManifestInvalidError(f"archive document {index} fields differ")
    document_id = value["document_id"]
    if not isinstance(document_id, str) or IDENTIFIER_PATTERN.fullmatch(document_id) is None:
        raise ArchiveManifestInvalidError(f"archive document {index} identifier differs")
    relative_path = value["relative_path"]
    if (
        not isinstance(relative_path, str)
        or _RELATIVE_PATH_PATTERN.fullmatch(relative_path) is None
        or ".." in relative_path.split("/")
    ):
        raise ArchiveManifestInvalidError(
            f"archive document {document_id} relative path differs"
        )
    media_type = value["media_type"]
    if not isinstance(media_type, str) or _MEDIA_TYPE_PATTERN.fullmatch(media_type) is None:
        raise ArchiveManifestInvalidError(
            f"archive document {document_id} media type differs"
        )
    byte_count = value["byte_count"]
    if (
        isinstance(byte_count, bool) or not isinstance(byte_count, int)
        or not 1 <= byte_count <= MAX_DOCUMENT_BYTES
    ):
        raise ArchiveManifestInvalidError(
            f"archive document {document_id} byte count differs"
        )
    digest = value["sha256"]
    if not isinstance(digest, str) or HASH_PATTERN.fullmatch(digest) is None:
        raise ArchiveManifestInvalidError(
            f"archive document {document_id} content hash differs"
        )
    licence = value["licence"]
    if not isinstance(licence, Mapping) or set(licence) != _LICENCE_FIELDS:
        raise ArchiveManifestInvalidError(
            f"archive document {document_id} licence metadata fields differ; "
            "the exact per-document licence inputs are load-bearing"
        )
    for key in _LICENCE_FIELDS:
        item = licence[key]
        if item is not None and (not isinstance(item, str) or not item.strip()):
            raise ArchiveManifestInvalidError(
                f"archive document {document_id} licence {key} differs"
            )
    return {
        "document_id": document_id,
        "relative_path": relative_path,
        "media_type": media_type,
        "byte_count": byte_count,
        "sha256": digest,
        "licence": {key: licence[key] for key in sorted(_LICENCE_FIELDS)},
    }


def validate_archive_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = verify_sealed(
        value, label="snapshot archive manifest",
        code=ArchiveManifestInvalidError.code,
    )
    if set(manifest) != ARCHIVE_MANIFEST_FIELDS:
        raise ArchiveManifestInvalidError(
            "snapshot archive manifest fields differ: "
            f"missing={sorted(ARCHIVE_MANIFEST_FIELDS - set(manifest))}, "
            f"extra={sorted(set(manifest) - ARCHIVE_MANIFEST_FIELDS)}"
        )
    if manifest["schema_version"] != ARCHIVE_MANIFEST_SCHEMA_VERSION:
        raise ArchiveManifestInvalidError("snapshot archive manifest schema differs")
    if manifest["provider"] != PROVIDER:
        raise ArchiveManifestInvalidError("snapshot archive manifest provider differs")
    if not isinstance(manifest["archive_id"], str) or IDENTIFIER_PATTERN.fullmatch(
        manifest["archive_id"]
    ) is None:
        raise ArchiveManifestInvalidError("snapshot archive identifier differs")
    if not isinstance(manifest["archive_version"], str) or not manifest[
        "archive_version"
    ].strip():
        raise ArchiveManifestInvalidError("snapshot archive version differs")
    documents = manifest["documents"]
    if not isinstance(documents, list) or not documents:
        raise ArchiveManifestInvalidError("snapshot archive lists no documents")
    validated = [_validate_document(item, index) for index, item in enumerate(documents)]
    ids = [item["document_id"] for item in validated]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise ArchiveManifestInvalidError(
            "archive documents must be sorted and unique by document_id"
        )
    paths = [item["relative_path"] for item in validated]
    if len(set(paths)) != len(paths):
        raise ArchiveManifestInvalidError("archive documents repeat a relative path")
    if manifest["document_count"] != len(validated):
        raise ArchiveManifestInvalidError("archive document count differs")
    total = sum(item["byte_count"] for item in validated)
    if manifest["total_bytes"] != total:
        raise ArchiveManifestInvalidError("archive total bytes differ")
    return manifest


def load_archive_manifest(data: bytes) -> dict[str, Any]:
    return validate_archive_manifest(strict_canonical_object(
        data, maximum=MAX_ARCHIVE_MANIFEST_BYTES,
        label="snapshot archive manifest", code=ArchiveManifestInvalidError.code,
    ))


def validate_tranche_config(value: Mapping[str, Any]) -> dict[str, Any]:
    config = verify_sealed(
        value, label="snapshot tranche config", code=TrancheConfigInvalidError.code,
    )
    if set(config) != TRANCHE_CONFIG_FIELDS:
        raise TrancheConfigInvalidError(
            "snapshot tranche config fields differ: "
            f"missing={sorted(TRANCHE_CONFIG_FIELDS - set(config))}, "
            f"extra={sorted(set(config) - TRANCHE_CONFIG_FIELDS)}"
        )
    if config["schema_version"] != TRANCHE_CONFIG_SCHEMA_VERSION:
        raise TrancheConfigInvalidError("snapshot tranche config schema differs")
    if not isinstance(config["tranche_id"], str) or IDENTIFIER_PATTERN.fullmatch(
        config["tranche_id"]
    ) is None:
        raise TrancheConfigInvalidError("snapshot tranche identifier differs")
    for key in ("archive_manifest_hash", "policy_content_hash"):
        if not isinstance(config[key], str) or HASH_PATTERN.fullmatch(config[key]) is None:
            raise TrancheConfigInvalidError(f"snapshot tranche {key} differs")
    bounds = (
        # ADR-0080: max_documents is operator-budgeted; the structural
        # ceiling is pinned in code and never widened by a config.  Live
        # acquisition volume stays separately bounded by the activation
        # record's own (smaller) max_tranche_documents pin.
        ("max_documents", MAX_TRANCHE_DOCUMENTS_STRUCTURAL_CEILING),
        ("max_total_bytes", MAX_TRANCHE_TOTAL_BYTES),
        ("max_document_bytes", MAX_DOCUMENT_BYTES),
    )
    for key, ceiling in bounds:
        item = config[key]
        if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= ceiling:
            raise TrancheConfigInvalidError(
                f"snapshot tranche {key} must be 1..{ceiling}; a config states "
                "a bound, it never widens one"
            )
    selected_by = config["selected_by"]
    if (
        not isinstance(selected_by, Mapping)
        or set(selected_by) != _SELECTED_BY_FIELDS
        or not isinstance(selected_by.get("actor_id"), str)
        or IDENTIFIER_PATTERN.fullmatch(selected_by["actor_id"]) is None
        or selected_by.get("actor_kind") != "human"
        or selected_by.get("authority") != "human_final"
    ):
        raise TrancheConfigInvalidError(
            "archive and tranche selection remain human acts (ADR-0067); the "
            "tranche config must name one human-final selector"
        )
    return config


def load_tranche_config(data: bytes) -> dict[str, Any]:
    return validate_tranche_config(strict_canonical_object(
        data, maximum=MAX_TRANCHE_CONFIG_BYTES,
        label="snapshot tranche config", code=TrancheConfigInvalidError.code,
    ))


def assert_tranche_within_bounds(
    manifest: Mapping[str, Any], config: Mapping[str, Any],
) -> None:
    """Refuse an archive exceeding its tranche bounds; never truncate."""

    if config["archive_manifest_hash"] != manifest["content_hash"]:
        raise TrancheConfigInvalidError(
            "the tranche config pins a different archive manifest hash; the "
            "tranche is a content-hashed selection, not a directory"
        )
    if manifest["document_count"] > config["max_documents"]:
        raise TrancheBoundExceededError(
            f"the archive lists {manifest['document_count']} documents; the "
            f"tranche pins {config['max_documents']}"
        )
    if manifest["total_bytes"] > config["max_total_bytes"]:
        raise TrancheBoundExceededError(
            f"the archive totals {manifest['total_bytes']} bytes; the tranche "
            f"pins {config['max_total_bytes']}"
        )
    for document in manifest["documents"]:
        if document["byte_count"] > config["max_document_bytes"]:
            raise TrancheBoundExceededError(
                f"document {document['document_id']} is "
                f"{document['byte_count']} bytes; the tranche pins "
                f"{config['max_document_bytes']} per document"
            )


__all__ = [
    "ARCHIVE_MANIFEST_FIELDS",
    "TRANCHE_CONFIG_FIELDS",
    "assert_tranche_within_bounds",
    "load_archive_manifest",
    "load_tranche_config",
    "validate_archive_manifest",
    "validate_tranche_config",
]
