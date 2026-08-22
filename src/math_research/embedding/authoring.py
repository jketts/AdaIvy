"""Offline authoring of ``fixture_synthetic`` partitions.

The offline acceptance path needs vectors and must make no provider call, so
exactly one non-provider partition value exists. It is authored here, it can
never be produced by `ingest_partition`, and every manifest built on it carries
``corpus_provenance: "project_authored"`` -- mirroring ADR-0034's
``control_corpus_provenance``, for the same reason: a gate result computed over
synthetic vectors demonstrates boundary enforcement and is NOT evidence about
real embedding quality.

Coordinates are authored as exact integers at the declared scale. No float is
parsed and none is constructed, so an authored partition is byte-reproducible
without any reference to IEEE-754 at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ..phase2.serialization import sha256_bytes
from .constants import FIXTURE_SYNTHETIC_PROVIDER, IDENTIFIER_PATTERN
from .errors import EmbeddingError, FixtureProviderNotIngestibleError, PartitionSchemaError
from .partition import (
    ARTIFACT_KINDS,
    DEFAULT_ARTIFACT_KIND,
    DEFAULT_HASH_RULE,
    HASH_RULES,
    Partition,
    PartitionKey,
    VectorArtifact,
    create_vector_artifact,
    write_partition,
)

AUTHORING_SPEC_SCHEMA_VERSION = "adaivy.vector-partition-authoring-spec.v1"
MAX_SPEC_BYTES = 1_048_576

_SPEC_REQUIRED = frozenset({
    "schema_version", "provider", "model_identifier", "dimension",
    "normalization", "vectors",
})
_SPEC_OPTIONAL = frozenset({"fixture_license", "hash_rule"})
_SPEC_VECTOR_REQUIRED = frozenset({"document_id", "source_text", "coordinates"})
_SPEC_VECTOR_OPTIONAL = frozenset({"artifact_kind"})


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthoringSpec:
    key: PartitionKey
    fixture_license: str
    hash_rule: str
    artifacts: tuple[VectorArtifact, ...]


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise PartitionSchemaError(f"duplicate JSON key: {key!r}")
        seen[key] = value
    return seen


def _reject_decimal(raw: str) -> Any:
    raise PartitionSchemaError(
        f"an authored fixture vector must be exact integers, not {raw!r}"
    )


def load_authoring_spec(path: Path) -> AuthoringSpec:
    raw = path.read_bytes()
    if len(raw) > MAX_SPEC_BYTES:
        raise PartitionSchemaError(f"authoring spec exceeds {MAX_SPEC_BYTES} bytes")
    try:
        payload = json.loads(
            raw.decode("utf-8"), parse_float=_reject_decimal,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PartitionSchemaError(f"cannot parse authoring spec {path}") from error
    if not isinstance(payload, dict):
        raise PartitionSchemaError("authoring spec must be a JSON object")
    missing = sorted(_SPEC_REQUIRED - set(payload))
    unknown = sorted(set(payload) - _SPEC_REQUIRED - _SPEC_OPTIONAL)
    if missing or unknown:
        raise PartitionSchemaError(
            f"authoring spec fields differ from schema: missing {missing}, "
            f"unknown {unknown}"
        )
    if payload["schema_version"] != AUTHORING_SPEC_SCHEMA_VERSION:
        raise PartitionSchemaError("unsupported authoring spec schema_version")
    if payload["provider"] != FIXTURE_SYNTHETIC_PROVIDER:
        raise FixtureProviderNotIngestibleError(
            "only the fixture_synthetic provider may be authored offline; a real "
            f"provider partition is produced by ingestion, not by hand: "
            f"{payload['provider']!r}"
        )
    fixture_license = payload.get("fixture_license", "LicenseRef-AdaIvy-Synthetic-Fixture")
    if not isinstance(fixture_license, str) or not fixture_license:
        raise PartitionSchemaError("fixture_license must be a non-empty string")
    hash_rule = payload.get("hash_rule", DEFAULT_HASH_RULE)
    if hash_rule not in HASH_RULES:
        raise PartitionSchemaError(f"unknown hash_rule {hash_rule!r}")
    key = PartitionKey(
        provider=str(payload["provider"]),
        model_identifier=str(payload["model_identifier"]),
        dimension=payload["dimension"],
        normalization=str(payload["normalization"]),
    )
    entries = payload["vectors"]
    if not isinstance(entries, list) or not entries:
        raise PartitionSchemaError("authoring spec vectors must be a non-empty array")
    artifacts: list[VectorArtifact] = []
    seen: set[str] = set()
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise PartitionSchemaError(f"vectors[{position}] must be an object")
        entry_missing = sorted(_SPEC_VECTOR_REQUIRED - set(entry))
        entry_unknown = sorted(set(entry) - _SPEC_VECTOR_REQUIRED - _SPEC_VECTOR_OPTIONAL)
        if entry_missing or entry_unknown:
            raise PartitionSchemaError(
                f"vectors[{position}] fields differ from schema: missing "
                f"{entry_missing}, unknown {entry_unknown}"
            )
        artifact_kind = entry.get("artifact_kind", DEFAULT_ARTIFACT_KIND)
        if artifact_kind not in ARTIFACT_KINDS:
            raise PartitionSchemaError(
                f"vectors[{position}].artifact_kind must be one of {list(ARTIFACT_KINDS)}"
            )
        document_id = entry["document_id"]
        if not isinstance(document_id, str) or IDENTIFIER_PATTERN.fullmatch(document_id) is None:
            raise PartitionSchemaError(f"vectors[{position}].document_id is not path-safe")
        if document_id in seen:
            raise PartitionSchemaError(f"duplicate document_id {document_id!r}")
        seen.add(document_id)
        source_text = entry["source_text"]
        if not isinstance(source_text, str) or not source_text:
            raise PartitionSchemaError(f"vectors[{position}].source_text must be non-empty")
        coordinates = entry["coordinates"]
        if not isinstance(coordinates, list):
            raise PartitionSchemaError(f"vectors[{position}].coordinates must be an array")
        artifacts.append(create_vector_artifact(
            key, document_id=document_id,
            source_content_hash=sha256_bytes(source_text.encode("utf-8")),
            coordinates=coordinates, artifact_kind=str(artifact_kind),
            hash_rule=str(hash_rule),
        ))
    return AuthoringSpec(
        key=key, fixture_license=fixture_license, hash_rule=str(hash_rule),
        artifacts=tuple(sorted(artifacts, key=lambda item: item.document_id)),
    )


def author_partition(root: Path, spec: AuthoringSpec) -> Partition:
    if not spec.key.is_fixture_synthetic:  # pragma: no cover - defended above too
        raise EmbeddingError(
            "author_partition writes fixture_synthetic partitions only",
            code="authoring_provider_refused",
        )
    return write_partition(
        root, spec.key, spec.artifacts, hash_rule=spec.hash_rule,
    )


__all__ = [
    "AUTHORING_SPEC_SCHEMA_VERSION",
    "AuthoringSpec",
    "MAX_SPEC_BYTES",
    "author_partition",
    "load_authoring_spec",
]
