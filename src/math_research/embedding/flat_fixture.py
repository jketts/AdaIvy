"""Strict reader for the flat, checked-in Phase 4C vector fixture.

The production partition store uses keyed directories.  The historical Phase
4C benchmark fixture predates that layout and deliberately keeps its manifest
at the fixture root.  This adapter is the sole parser for those frozen bytes;
it returns the same immutable :class:`Partition` view used by retrieval.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, Sequence

from ..phase2.serialization import canonical_json
from .errors import PartitionSchemaError
from .partition import (
    ARTIFACT_KIND_DOCUMENT,
    ARTIFACT_KIND_QUERY,
    Partition,
    PartitionKey,
    VectorArtifact,
    partition_key_from_payload,
    require_within_scale,
)

HASH_RULE = "content_hash_over_canonical_body_with_hash_field_set_to_null"
MANIFEST_SCHEMA = "adaivy.vector-partition-manifest.v1"
ARTIFACT_SCHEMA = "adaivy.vector-artifact.v1"
_MANIFEST_FIELDS = frozenset({
    "schema_version", "fixture_license", "corpus_provenance",
    "corpus_fixture_root", "generator", "hash_rule", "partition_key",
    "expected_counts", "documents", "queries", "content_hash",
})
_COUNT_FIELDS = frozenset({
    "artifact_count", "coordinate_bound_absolute", "coordinates_per_artifact",
    "document_count", "query_count",
})
_ENTRY_FIELDS = frozenset({
    "artifact_path", "artifact_sha256", "byte_length", "content_hash",
    "document_id", "source_content_hash",
})
_ARTIFACT_FIELDS = frozenset({
    "schema_version", "artifact_kind", "document_id", "source_content_hash",
    "coordinates", "content_hash",
})


def _reject_float(raw: str) -> NoReturn:
    raise PartitionSchemaError(f"inexact literal {raw!r}")


def _pairs(items: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise PartitionSchemaError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise PartitionSchemaError(f"{path} is absent")
    raw = path.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8"), parse_float=_reject_float,
            object_pairs_hook=_pairs,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PartitionSchemaError(f"malformed JSON in {path}") from error
    if not isinstance(value, dict):
        raise PartitionSchemaError(f"{path} must contain an object")
    return value, raw


def _fields(value: dict[str, Any], expected: frozenset[str], where: str) -> None:
    missing = sorted(expected - set(value))
    if missing:
        raise PartitionSchemaError(f"{where} missing keys {missing}")
    unknown = sorted(set(value) - expected)
    if unknown:
        raise PartitionSchemaError(f"{where} unknown keys {unknown}")


def _integer(value: Any, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PartitionSchemaError(f"{where}: expected an integer")
    return value


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sealed_hash(value: dict[str, Any]) -> str:
    body = dict(value)
    body["content_hash"] = None
    return _sha256(canonical_json(body).encode("utf-8"))


def _canonical_relative_path(value: Any, *, kind: str, identifier: str) -> str:
    bucket = "documents" if kind == ARTIFACT_KIND_DOCUMENT else "queries"
    expected = f"artifacts/{bucket}/{identifier}.json"
    if not isinstance(value, str):
        raise PartitionSchemaError("artifact_path must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != expected:
        raise PartitionSchemaError(f"artifact_path is not canonical: {value!r}")
    return value


def load_flat_fixture_partition(root: Path, requested: PartitionKey) -> Partition:
    manifest, _raw = _read_json(root.joinpath("manifest.json"))
    _fields(manifest, _MANIFEST_FIELDS, "manifest")
    if manifest["schema_version"] != MANIFEST_SCHEMA:
        raise PartitionSchemaError("unsupported manifest schema_version")
    if manifest["hash_rule"] != HASH_RULE:
        raise PartitionSchemaError("manifest.hash_rule is not supported")
    if manifest["corpus_provenance"] != "project_authored":
        raise PartitionSchemaError("manifest.corpus_provenance must be project_authored")
    if manifest["partition_key"] != requested.payload():
        raise PartitionSchemaError("semantic partition mismatch")
    declared = partition_key_from_payload(manifest["partition_key"])
    if _sealed_hash(manifest) != manifest["content_hash"]:
        raise PartitionSchemaError("manifest content hash mismatch")

    counts = manifest["expected_counts"]
    if not isinstance(counts, dict):
        raise PartitionSchemaError("expected_counts must be an object")
    _fields(counts, _COUNT_FIELDS, "expected_counts")
    dimension = _integer(counts["coordinates_per_artifact"], "coordinates_per_artifact")
    if dimension != requested.dimension:
        raise PartitionSchemaError("declared coordinate dimension mismatch")
    if _integer(counts["coordinate_bound_absolute"], "coordinate_bound_absolute") != requested.coordinate_limit:
        raise PartitionSchemaError("declared coordinate bound mismatch")

    vectors: dict[str, VectorArtifact] = {}
    expected_total = 0
    declared_total = _integer(counts["artifact_count"], "artifact_count")
    actual_total = sum(
        len(manifest[name]) if isinstance(manifest[name], list) else 0
        for name in ("documents", "queries")
    )
    if declared_total != actual_total:
        raise PartitionSchemaError("artifact count disagrees with manifest bytes")
    for bucket, kind in (("documents", ARTIFACT_KIND_DOCUMENT), ("queries", ARTIFACT_KIND_QUERY)):
        entries = manifest[bucket]
        if not isinstance(entries, list):
            raise PartitionSchemaError(f"manifest.{bucket} must be an array")
        expected_total += len(entries)
        declared_count = _integer(counts[f"{kind}_count"], f"{kind}_count")
        if declared_count != len(entries):
            raise PartitionSchemaError(f"{kind} count disagrees with manifest bytes")
        previous = ""
        for position, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise PartitionSchemaError(f"{bucket}[{position}] must be an object")
            _fields(entry, _ENTRY_FIELDS, f"{bucket}[{position}]")
            identifier = entry["document_id"]
            if not isinstance(identifier, str) or identifier <= previous:
                raise PartitionSchemaError(f"{bucket} ids must be sorted and unique")
            previous = identifier
            if identifier in vectors:
                raise PartitionSchemaError(f"{identifier} appears twice in the partition")
            relative = _canonical_relative_path(
                entry["artifact_path"], kind=kind, identifier=identifier
            )
            body, raw = _read_json(root.joinpath(*PurePosixPath(relative).parts))
            if _integer(entry["byte_length"], "byte_length") != len(raw):
                raise PartitionSchemaError(f"{identifier}: byte_length mismatch")
            if entry["artifact_sha256"] != _sha256(raw):
                raise PartitionSchemaError(f"{identifier}: artifact_sha256 mismatch")
            _fields(body, _ARTIFACT_FIELDS, f"artifact {identifier}")
            if body["schema_version"] != ARTIFACT_SCHEMA:
                raise PartitionSchemaError("unsupported artifact schema_version")
            if body["artifact_kind"] != kind:
                raise PartitionSchemaError(f"{identifier}: artifact_kind mismatch")
            if body["document_id"] != identifier:
                raise PartitionSchemaError(f"{identifier}: document_id mismatch")
            if body["source_content_hash"] != entry["source_content_hash"]:
                raise PartitionSchemaError(f"{identifier}: source_content_hash mismatch")
            if body["content_hash"] != entry["content_hash"] or _sealed_hash(body) != body["content_hash"]:
                raise PartitionSchemaError(f"{identifier}: content hash mismatch")
            coordinates = body["coordinates"]
            if not isinstance(coordinates, list):
                raise PartitionSchemaError(f"{identifier}.coordinates must be an array")
            exact = tuple(
                _integer(item, f"{identifier}.coordinates[{index}]")
                for index, item in enumerate(coordinates)
            )
            if len(exact) != requested.dimension:
                raise PartitionSchemaError(f"{identifier}: dimension mismatch")
            require_within_scale(exact, key=requested, where=f"{identifier}.coordinates")
            vectors[identifier] = VectorArtifact(
                document_id=identifier,
                source_content_hash=body["source_content_hash"],
                coordinates=exact,
                content_hash=body["content_hash"],
                artifact_kind=kind,
            )
    if declared_total != expected_total:
        raise PartitionSchemaError("artifact count disagrees with manifest bytes")
    return Partition(
        key=requested,
        manifest_hash=manifest["content_hash"],
        corpus_provenance="project_authored",
        vectors=vectors,
    )


__all__ = ["load_flat_fixture_partition"]
