"""Partitioned, content-hashed exact vector artifacts (ADR-0069).

`TECHNICAL_BLUEPRINT.md:1661-1663` requires a vector index partitioned by the
tuple ``(provider, model_identifier, dimension, normalization)``, with no
default and no fallback partition. `:1667-1671` requires produced vectors to be
immutable content-hashed artifacts whose bytes are bound into canonical
identity, and a rebuild to replay those artifacts rather than call the provider
again. This module is that store.

READ PATH PURITY. This module, :mod:`similarity` and :mod:`replay` are the
replay path. None constructs a float and none divides: a coordinate arrives as an
exact integer at the declared scale or it is refused. ``json.loads`` is given a
``parse_float`` hook that raises, so a decimal in a persisted artifact is a
refusal rather than an IEEE-754 value that happens to round-trip.
:mod:`readpath` sweeps all three and `pr.no-float-in-retrieval-path` asserts the
sweep is clean.

HASH RULE. This subsystem sets the hash field to ``None`` before hashing, the
`phase2/live_config.py` convention. `phase4c/serialization.py` POPS the key
instead, and `synthesis/serialization.py` records that mixing the two changes
every hash. So the rule is not hardcoded on read: a manifest or artifact states
its own ``hash_rule`` and this module honours what it states. Absent, the
subsystem default applies.

ARTIFACT KIND. Query vectors live in the same partition as corpus documents --
they must, because a query is only ever compared inside its own geometry. Each
artifact therefore declares ``artifact_kind``, ``"document"`` or ``"query"``.
Absence is read as ``"document"`` for tolerance; the explicit field is preferred
and this module always writes it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, NoReturn, Sequence

from ..phase2.serialization import canonical_hash, canonical_json
from .constants import (
    CORPUS_PROVENANCE_PROJECT_AUTHORED,
    CORPUS_PROVENANCE_PROVIDER_EMBEDDED,
    CORPUS_PROVENANCE_VALUES,
    FIXTURE_SYNTHETIC_PROVIDER,
    HASH_PATTERN,
    IDENTIFIER_PATTERN,
    MAX_DIMENSION,
    MIN_DIMENSION,
    NORMALIZATION_SCHEMES,
    PARTITION_PROVIDERS,
)
from .errors import (
    ArtifactHashMismatchError,
    ArtifactMissingError,
    ArtifactOverwriteRefused,
    CoordinateSaturatedError,
    DocumentAbsentError,
    ManifestHashMismatchError,
    ManifestKeyMismatchError,
    NonIntegerCoordinateError,
    PartitionAbsentError,
    PartitionKeyError,
    PartitionSchemaError,
)

PARTITION_SCHEMA_VERSION = "adaivy.vector-partition-manifest.v1"
ARTIFACT_SCHEMA_VERSION = "adaivy.vector-artifact.v1"

MANIFEST_FILENAME = "manifest.json"

#: RESOLVED by the ADR-0069 amendment of 2026-08-22, recorded here because the
#: conflict was real and the resolution is a decision rather than a rename.
#:
#: ADR-0069 says artifacts are durable evidence bytes; `.gitignore` ignores
#: `vectors/`, `vector-store/`, and `embeddings/` because `AGENTS.md` holds that
#: a derived index is never a source of truth and "a committed one would let a
#: stale index outlive the corpus it was built from".
#:
#: Both hold, because they are about different things. A derived index is
#: rebuildable FROM THE RECORDS by definition. A vector artifact is not: it
#: required a provider call that is not bit-reproducible, which is the entire
#: reason `TECHNICAL_BLUEPRINT.md:1667-1671` says to store the bytes and have a
#: rebuild replay them. So an artifact is primary evidence of a disclosure that
#: happened, closer to an acquisition than to an index, and the ignore rule was
#: never aimed at it. An ANN or similarity index built OVER these artifacts is a
#: derived index and stays ignored.
#:
#: The directory is therefore a non-ignored name, which also closes the
#: half-commit trap: a manifest can no longer be tracked while its artifacts are
#: silently dropped. `ArtifactDirectoryIsIgnoredTests` now asserts the resolution
#: instead of the collision.
VECTOR_DIRNAME = "vector-artifacts"

#: Separator for :meth:`PartitionKey.key_string`. Excluded from
#: ``IDENTIFIER_PATTERN``, so the composition is injective: no two distinct
#: key tuples can produce the same string.
KEY_SEPARATOR = "~"

#: ``phase2/live_config.py``: set the hash field to ``None``, then hash.
HASH_RULE_SET_NULL = "set_null_before_hash"
#: ``phase4c/serialization.py``: remove the key, then hash.
HASH_RULE_POP = "pop_before_hash"
HASH_RULES = (HASH_RULE_POP, HASH_RULE_SET_NULL)
DEFAULT_HASH_RULE = HASH_RULE_SET_NULL

ARTIFACT_KIND_DOCUMENT = "document"
ARTIFACT_KIND_QUERY = "query"
ARTIFACT_KINDS = (ARTIFACT_KIND_DOCUMENT, ARTIFACT_KIND_QUERY)
#: Absence is tolerated and read as a corpus document. The explicit field is
#: preferred and is always written.
DEFAULT_ARTIFACT_KIND = ARTIFACT_KIND_DOCUMENT

# --- accepted field sets ----------------------------------------------------
# Required fields must be present; optional fields are validated when present;
# anything else is a refusal. The split exists because a hand-authored fixture
# legitimately omits fields this writer derives, while an UNKNOWN field is still
# a fail-closed schema error.

_MANIFEST_REQUIRED = frozenset({
    "schema_version", "partition_key", "vectors", "manifest_hash",
})
_MANIFEST_OPTIONAL = frozenset({
    "hash_rule", "partition_key_string", "corpus_provenance", "vector_count",
    "fixture_license",
})
_MANIFEST_KEY_FIELDS = frozenset({
    "provider", "model_identifier", "dimension", "normalization",
})
_MANIFEST_ENTRY_REQUIRED = frozenset({
    "document_id", "source_content_hash", "artifact_content_hash",
})
_MANIFEST_ENTRY_OPTIONAL = frozenset({
    "artifact_path", "artifact_kind",
})
_ARTIFACT_REQUIRED = frozenset({
    "schema_version", "document_id", "source_content_hash", "coordinates",
    "content_hash", "partition_key_string",
})
_ARTIFACT_OPTIONAL = frozenset({
    "artifact_kind", "hash_rule", "dimension",
})


def _reject_float(raw: str) -> NoReturn:
    """``json`` hook: a decimal literal in the read path is a refusal."""

    raise PartitionSchemaError(f"decimal literal on the read path: {raw!r}")


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise PartitionSchemaError(f"duplicate JSON key: {key!r}")
        seen[key] = value
    return seen


def _strict_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PartitionSchemaError(f"cannot read {path}") from error
    try:
        value = json.loads(
            raw, parse_float=_reject_float, object_pairs_hook=_reject_duplicate_keys,
        )
    except json.JSONDecodeError as error:
        raise PartitionSchemaError(f"malformed JSON in {path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise PartitionSchemaError(f"{path} must contain a JSON object")
    return value


def _accepted_fields(
    value: Mapping[str, Any], required: frozenset[str], optional: frozenset[str],
    where: str,
) -> None:
    present = set(value)
    missing = sorted(required - present)
    if missing:
        raise PartitionSchemaError(f"{where} is missing required fields {missing}")
    unknown = sorted(present - required - optional)
    if unknown:
        raise PartitionSchemaError(f"{where} has unknown fields {unknown}")


def _identifier(value: Any, where: str) -> str:
    if not isinstance(value, str) or IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise PartitionSchemaError(f"{where} is not a valid lowercase identifier")
    return value


def _hash(value: Any, where: str) -> str:
    if not isinstance(value, str) or HASH_PATTERN.fullmatch(value) is None:
        raise PartitionSchemaError(f"{where} is not a sha256 content hash")
    return value


def _exact_integer(value: Any, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise NonIntegerCoordinateError(f"{where} must be an exact integer")
    return value


def _artifact_kind(value: Any, where: str) -> str:
    if value is None:
        return DEFAULT_ARTIFACT_KIND
    if value not in ARTIFACT_KINDS:
        raise PartitionSchemaError(
            f"{where} must be one of {list(ARTIFACT_KINDS)}, got {value!r}"
        )
    return str(value)


def _hash_rule(value: Any, where: str) -> str:
    if value is None:
        return DEFAULT_HASH_RULE
    if value not in HASH_RULES:
        raise PartitionSchemaError(
            f"{where} must be one of {list(HASH_RULES)}, got {value!r}"
        )
    return str(value)


def apply_hash_rule(
    payload: Mapping[str, Any], *, hash_field: str, hash_rule: str,
) -> dict[str, Any]:
    """The exact preimage a declared ``hash_rule`` covers."""

    body = dict(payload)
    if hash_rule == HASH_RULE_POP:
        body.pop(hash_field, None)
        return body
    if hash_rule == HASH_RULE_SET_NULL:
        body[hash_field] = None
        return body
    raise PartitionSchemaError(f"unknown hash_rule {hash_rule!r}")


def payload_hash(
    payload: Mapping[str, Any], *, hash_field: str, hash_rule: str,
) -> str:
    return canonical_hash(
        apply_hash_rule(payload, hash_field=hash_field, hash_rule=hash_rule)
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class PartitionKey:
    """The blueprint's four-component tuple, and nothing else."""

    provider: str
    model_identifier: str
    dimension: int
    normalization: str

    def __post_init__(self) -> None:
        if self.provider not in PARTITION_PROVIDERS:
            raise PartitionKeyError(f"unsupported partition provider: {self.provider!r}")
        if IDENTIFIER_PATTERN.fullmatch(self.model_identifier) is None:
            raise PartitionKeyError(
                "model_identifier must match "
                f"{IDENTIFIER_PATTERN.pattern} (lowercase, path-safe): "
                f"{self.model_identifier!r}"
            )
        if not isinstance(self.dimension, int) or isinstance(self.dimension, bool):
            raise PartitionKeyError("dimension must be an integer")
        if not MIN_DIMENSION <= self.dimension <= MAX_DIMENSION:
            raise PartitionKeyError(f"dimension out of range: {self.dimension}")
        if self.normalization not in NORMALIZATION_SCHEMES:
            raise PartitionKeyError(f"unknown normalization: {self.normalization!r}")

    @property
    def is_fixture_synthetic(self) -> bool:
        return self.provider == FIXTURE_SYNTHETIC_PROVIDER

    @property
    def scale_exponent(self) -> int:
        return NORMALIZATION_SCHEMES[self.normalization]

    @property
    def coordinate_limit(self) -> int:
        """Largest representable magnitude. ``2**k`` is IN range; above halts."""

        return 1 << self.scale_exponent

    def key_string(self) -> str:
        """Canonical, stable identity. Used in paths and in hashes."""

        return KEY_SEPARATOR.join((
            self.provider,
            self.model_identifier,
            f"d{self.dimension}",
            self.normalization,
        ))

    def payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_identifier": self.model_identifier,
            "dimension": self.dimension,
            "normalization": self.normalization,
        }

    def required_corpus_provenance(self) -> str:
        """``fixture_synthetic`` forces ``project_authored``. No exception."""

        if self.is_fixture_synthetic:
            return CORPUS_PROVENANCE_PROJECT_AUTHORED
        return CORPUS_PROVENANCE_PROVIDER_EMBEDDED

    def directory(self, root: Path) -> Path:
        return root.joinpath(self.key_string())


def partition_key_from_payload(payload: Any) -> PartitionKey:
    if not isinstance(payload, dict):
        raise PartitionSchemaError("partition_key must be an object")
    _accepted_fields(payload, _MANIFEST_KEY_FIELDS, frozenset(), "partition_key")
    return PartitionKey(
        provider=str(payload["provider"]),
        model_identifier=str(payload["model_identifier"]),
        dimension=_exact_integer(payload["dimension"], "partition_key.dimension"),
        normalization=str(payload["normalization"]),
    )


def require_within_scale(
    coordinates: Sequence[int], *, key: PartitionKey, where: str,
) -> None:
    """``|c| <= 2**k``. The maximum is attained exactly; above it halts.

    The declared scale is a closed range, so a coordinate at the boundary is
    correct data and a coordinate beyond it is a fault -- ADR-0069: "A saturating
    coordinate is a fault, not a rounding detail." Clamping would hide a model
    that is not the model the partition declares.
    """

    limit = key.coordinate_limit
    for index, value in enumerate(coordinates):
        if value > limit or value < -limit:
            raise CoordinateSaturatedError(
                f"{where}[{index}] = {value} exceeds the declared scale "
                f"{key.normalization} (limit {limit}); this is a fault, not a "
                "rounding detail"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class VectorArtifact:
    """An immutable exact vector. ``coordinates`` are integers at the scale."""

    document_id: str
    source_content_hash: str
    coordinates: tuple[int, ...]
    content_hash: str
    #: ``"document"`` or ``"query"``. Queries share the partition by necessity.
    artifact_kind: str = field(default=DEFAULT_ARTIFACT_KIND)

    def __post_init__(self) -> None:
        _identifier(self.document_id, "document_id")
        _hash(self.source_content_hash, "source_content_hash")
        _hash(self.content_hash, "content_hash")
        if self.artifact_kind not in ARTIFACT_KINDS:
            raise PartitionSchemaError(
                f"artifact_kind must be one of {list(ARTIFACT_KINDS)}"
            )
        if not isinstance(self.coordinates, tuple) or not self.coordinates:
            raise PartitionSchemaError("coordinates must be a non-empty tuple")
        for index, value in enumerate(self.coordinates):
            _exact_integer(value, f"coordinates[{index}]")

    @property
    def is_query(self) -> bool:
        return self.artifact_kind == ARTIFACT_KIND_QUERY


@dataclass(frozen=True, slots=True, kw_only=True)
class PartitionedVector:
    """A vector that knows which geometry it belongs to.

    Similarity is only ever computed between two of these, so a comparison
    across providers, models, dimensions or scales is a refusal rather than a
    number.
    """

    partition_key: PartitionKey
    document_id: str
    coordinates: tuple[int, ...]
    artifact_kind: str = field(default=DEFAULT_ARTIFACT_KIND)


def artifact_payload(
    key: PartitionKey, artifact: VectorArtifact, *, hash_rule: str = DEFAULT_HASH_RULE,
) -> dict[str, Any]:
    """Canonical artifact body. The partition key is bound into identity."""

    body = _artifact_body(
        key, document_id=artifact.document_id,
        source_content_hash=artifact.source_content_hash,
        coordinates=artifact.coordinates, artifact_kind=artifact.artifact_kind,
        hash_rule=hash_rule,
    )
    body["content_hash"] = artifact.content_hash
    return body


def _artifact_body(
    key: PartitionKey, *, document_id: str, source_content_hash: str,
    coordinates: Sequence[int], artifact_kind: str, hash_rule: str,
) -> dict[str, Any]:
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "hash_rule": hash_rule,
        "partition_key_string": key.key_string(),
        "artifact_kind": artifact_kind,
        "document_id": document_id,
        "dimension": len(coordinates),
        "source_content_hash": source_content_hash,
        "coordinates": list(coordinates),
        "content_hash": None,
    }


def artifact_content_hash(
    key: PartitionKey, *, document_id: str, source_content_hash: str,
    coordinates: Sequence[int], artifact_kind: str = DEFAULT_ARTIFACT_KIND,
    hash_rule: str = DEFAULT_HASH_RULE,
) -> str:
    """Hash the canonical body under the declared rule."""

    body = _artifact_body(
        key, document_id=document_id, source_content_hash=source_content_hash,
        coordinates=coordinates, artifact_kind=artifact_kind, hash_rule=hash_rule,
    )
    return payload_hash(body, hash_field="content_hash", hash_rule=hash_rule)


def create_vector_artifact(
    key: PartitionKey, *, document_id: str, source_content_hash: str,
    coordinates: Sequence[int], artifact_kind: str = DEFAULT_ARTIFACT_KIND,
    hash_rule: str = DEFAULT_HASH_RULE,
) -> VectorArtifact:
    _identifier(document_id, "document_id")
    _hash(source_content_hash, "source_content_hash")
    kind = _artifact_kind(artifact_kind, "artifact_kind")
    rule = _hash_rule(hash_rule, "hash_rule")
    exact = tuple(
        _exact_integer(value, f"coordinates[{index}]")
        for index, value in enumerate(coordinates)
    )
    if len(exact) != key.dimension:
        raise PartitionSchemaError(
            f"{document_id}: {len(exact)} coordinates for dimension {key.dimension}"
        )
    require_within_scale(exact, key=key, where=f"{document_id}.coordinates")
    return VectorArtifact(
        document_id=document_id,
        source_content_hash=source_content_hash,
        coordinates=exact,
        artifact_kind=kind,
        content_hash=artifact_content_hash(
            key, document_id=document_id,
            source_content_hash=source_content_hash, coordinates=exact,
            artifact_kind=kind, hash_rule=rule,
        ),
    )


def artifact_relative_path(document_id: str) -> str:
    return f"{VECTOR_DIRNAME}/{document_id}.json"


def _write_immutable(path: Path, rendered: str) -> None:
    """Append-only bytes. Same body is idempotent; different body is refused.

    Follows the ``write_recheck`` precedent at ``novelty.py:395-404``.
    """

    if path.exists():
        if path.read_text(encoding="utf-8") == rendered:
            return
        raise ArtifactOverwriteRefused(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def write_vector_artifact(
    root: Path, key: PartitionKey, artifact: VectorArtifact, *,
    hash_rule: str = DEFAULT_HASH_RULE,
) -> Path:
    expected = artifact_content_hash(
        key, document_id=artifact.document_id,
        source_content_hash=artifact.source_content_hash,
        coordinates=artifact.coordinates, artifact_kind=artifact.artifact_kind,
        hash_rule=hash_rule,
    )
    if expected != artifact.content_hash:
        raise ArtifactHashMismatchError(artifact.document_id)
    path = key.directory(root).joinpath(artifact_relative_path(artifact.document_id))
    _write_immutable(
        path, canonical_json(artifact_payload(key, artifact, hash_rule=hash_rule)) + "\n"
    )
    return path


def manifest_payload(
    key: PartitionKey, artifacts: Sequence[VectorArtifact], *, corpus_provenance: str,
    hash_rule: str = DEFAULT_HASH_RULE,
) -> dict[str, Any]:
    ordered = sorted(artifacts, key=lambda item: item.document_id)
    identifiers = [item.document_id for item in ordered]
    if len(set(identifiers)) != len(identifiers):
        raise PartitionSchemaError("duplicate document_id in partition manifest")
    payload: dict[str, Any] = {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "hash_rule": _hash_rule(hash_rule, "hash_rule"),
        "partition_key": key.payload(),
        "partition_key_string": key.key_string(),
        "corpus_provenance": corpus_provenance,
        "vector_count": len(ordered),
        "vectors": [
            {
                "document_id": item.document_id,
                "artifact_kind": item.artifact_kind,
                "source_content_hash": item.source_content_hash,
                "artifact_content_hash": item.content_hash,
                "artifact_path": artifact_relative_path(item.document_id),
            }
            for item in ordered
        ],
        "manifest_hash": None,
    }
    payload["manifest_hash"] = payload_hash(
        payload, hash_field="manifest_hash", hash_rule=payload["hash_rule"],
    )
    return payload


def _validated_corpus_provenance(key: PartitionKey, declared: str) -> str:
    if declared not in CORPUS_PROVENANCE_VALUES:
        raise PartitionSchemaError(f"unknown corpus_provenance: {declared!r}")
    if key.is_fixture_synthetic and declared != CORPUS_PROVENANCE_PROJECT_AUTHORED:
        raise PartitionSchemaError(
            "a fixture_synthetic partition must declare corpus_provenance "
            "project_authored so its vectors are never read as provider evidence"
        )
    return declared


class Partition:
    """A loaded partition. Immutable view over replayed artifact bytes."""

    __slots__ = ("key", "manifest_hash", "corpus_provenance", "hash_rule", "_vectors")

    def __init__(
        self, *, key: PartitionKey, manifest_hash: str, corpus_provenance: str,
        vectors: Mapping[str, VectorArtifact], hash_rule: str = DEFAULT_HASH_RULE,
    ) -> None:
        self.key = key
        self.manifest_hash = manifest_hash
        self.corpus_provenance = corpus_provenance
        self.hash_rule = hash_rule
        self._vectors = dict(sorted(vectors.items()))

    def document_ids(self) -> tuple[str, ...]:
        """Every artifact id in the partition, sorted. Includes query vectors."""

        return tuple(self._vectors)

    def ids_of_kind(self, artifact_kind: str) -> tuple[str, ...]:
        if artifact_kind not in ARTIFACT_KINDS:
            raise PartitionSchemaError(f"unknown artifact_kind {artifact_kind!r}")
        return tuple(
            key for key, value in self._vectors.items()
            if value.artifact_kind == artifact_kind
        )

    def corpus_document_ids(self) -> tuple[str, ...]:
        return self.ids_of_kind(ARTIFACT_KIND_DOCUMENT)

    def query_ids(self) -> tuple[str, ...]:
        return self.ids_of_kind(ARTIFACT_KIND_QUERY)

    def artifact_kinds(self) -> dict[str, str]:
        return {key: value.artifact_kind for key, value in self._vectors.items()}

    def vector(self, document_id: str) -> VectorArtifact:
        try:
            return self._vectors[document_id]
        except KeyError as error:
            raise DocumentAbsentError(
                f"{document_id} is not in partition {self.key.key_string()}"
            ) from error

    def partitioned_vector(self, document_id: str) -> PartitionedVector:
        artifact = self.vector(document_id)
        return PartitionedVector(
            partition_key=self.key,
            document_id=artifact.document_id,
            coordinates=artifact.coordinates,
            artifact_kind=artifact.artifact_kind,
        )

    def partitioned_vectors(
        self, *, artifact_kind: str | None = None,
    ) -> tuple[PartitionedVector, ...]:
        identifiers = (
            self.document_ids() if artifact_kind is None
            else self.ids_of_kind(artifact_kind)
        )
        return tuple(self.partitioned_vector(item) for item in identifiers)

    @property
    def vector_count(self) -> int:
        return len(self._vectors)

    @property
    def is_project_authored(self) -> bool:
        return self.corpus_provenance == CORPUS_PROVENANCE_PROJECT_AUTHORED


def write_partition(
    root: Path, key: PartitionKey, artifacts: Sequence[VectorArtifact], *,
    corpus_provenance: str | None = None, hash_rule: str = DEFAULT_HASH_RULE,
) -> Partition:
    """Write artifacts then the manifest that binds their bytes into identity."""

    provenance = _validated_corpus_provenance(
        key, corpus_provenance or CORPUS_PROVENANCE_PROJECT_AUTHORED
    )
    if provenance == CORPUS_PROVENANCE_PROVIDER_EMBEDDED:
        raise PartitionSchemaError(
            "provider_embedded provenance requires the live ingestion writer"
        )
    return _write_partition(
        root, key, artifacts, corpus_provenance=provenance, hash_rule=hash_rule,
    )


def _write_provider_partition(
    root: Path, key: PartitionKey, artifacts: Sequence[VectorArtifact], *,
    hash_rule: str = DEFAULT_HASH_RULE,
) -> Partition:
    """Ingestion-only route for artifacts returned by a live provider."""

    if key.is_fixture_synthetic:
        raise PartitionSchemaError("fixture_synthetic cannot be provider_embedded")
    return _write_partition(
        root, key, artifacts,
        corpus_provenance=CORPUS_PROVENANCE_PROVIDER_EMBEDDED,
        hash_rule=hash_rule,
    )


def _write_partition(
    root: Path, key: PartitionKey, artifacts: Sequence[VectorArtifact], *,
    corpus_provenance: str, hash_rule: str,
) -> Partition:
    provenance = _validated_corpus_provenance(key, corpus_provenance)
    rule = _hash_rule(hash_rule, "hash_rule")
    for artifact in sorted(artifacts, key=lambda item: item.document_id):
        if len(artifact.coordinates) != key.dimension:
            raise PartitionSchemaError(
                f"{artifact.document_id}: dimension differs from the partition key"
            )
        require_within_scale(
            artifact.coordinates, key=key, where=f"{artifact.document_id}.coordinates"
        )
        write_vector_artifact(root, key, artifact, hash_rule=rule)
    payload = manifest_payload(
        key, artifacts, corpus_provenance=provenance, hash_rule=rule,
    )
    _write_immutable(
        key.directory(root).joinpath(MANIFEST_FILENAME),
        canonical_json(payload) + "\n",
    )
    return load_partition(root, key)


def load_partition(root: Path, key: PartitionKey) -> Partition:
    """Replay a partition from bytes.

    Fails closed on an absent partition, a manifest whose key differs from the
    requested key, a manifest hash mismatch, a missing artifact, an artifact
    whose recomputed content hash differs from the recorded one, and a
    coordinate outside the declared scale. There is no fallback partition and no
    re-embedding: a rebuild that cannot find an artifact is an error, never a
    provider call.
    """

    directory = key.directory(root)
    manifest_path = directory.joinpath(MANIFEST_FILENAME)
    if not manifest_path.is_file():
        raise PartitionAbsentError(
            f"no partition {key.key_string()} under {root}; there is no fallback"
        )
    payload = _strict_json(manifest_path)
    _accepted_fields(payload, _MANIFEST_REQUIRED, _MANIFEST_OPTIONAL, "manifest")
    if payload["schema_version"] != PARTITION_SCHEMA_VERSION:
        raise PartitionSchemaError(
            f"unsupported manifest schema_version: {payload['schema_version']!r}"
        )
    rule = _hash_rule(payload.get("hash_rule"), "manifest.hash_rule")
    declared_key = partition_key_from_payload(payload["partition_key"])
    if declared_key != key:
        raise ManifestKeyMismatchError(
            f"manifest declares {declared_key.key_string()}, requested {key.key_string()}"
        )
    if "partition_key_string" in payload and payload["partition_key_string"] != key.key_string():
        raise ManifestKeyMismatchError("partition_key_string does not match partition_key")
    # A manifest that does not state its provenance cannot claim provider
    # evidence, so the fail-closed reading is project_authored.
    provenance = _validated_corpus_provenance(
        key, str(payload.get("corpus_provenance", CORPUS_PROVENANCE_PROJECT_AUTHORED)),
    )
    recorded_hash = _hash(payload["manifest_hash"], "manifest_hash")
    if payload_hash(payload, hash_field="manifest_hash", hash_rule=rule) != recorded_hash:
        raise ManifestHashMismatchError(
            f"{key.key_string()} under hash_rule {rule}"
        )

    entries = payload["vectors"]
    if not isinstance(entries, list) or not entries:
        raise PartitionSchemaError("manifest vectors must be a non-empty array")
    if "vector_count" in payload:
        if _exact_integer(payload["vector_count"], "vector_count") != len(entries):
            raise PartitionSchemaError("vector_count does not match the vector list")

    vectors: dict[str, VectorArtifact] = {}
    previous = ""
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise PartitionSchemaError(f"vectors[{position}] must be an object")
        _accepted_fields(
            entry, _MANIFEST_ENTRY_REQUIRED, _MANIFEST_ENTRY_OPTIONAL,
            f"vectors[{position}]",
        )
        document_id = _identifier(entry["document_id"], f"vectors[{position}].document_id")
        if document_id <= previous:
            raise PartitionSchemaError(
                "manifest vectors must be sorted by document_id ascending and unique"
            )
        previous = document_id
        expected_path = artifact_relative_path(document_id)
        if "artifact_path" in entry and entry["artifact_path"] != expected_path:
            raise PartitionSchemaError(f"vectors[{position}].artifact_path is not canonical")
        vectors[document_id] = _load_artifact(
            directory.joinpath(expected_path), key, entry, default_hash_rule=rule,
        )
    return Partition(
        key=key, manifest_hash=recorded_hash, corpus_provenance=provenance,
        vectors=vectors, hash_rule=rule,
    )


def _load_artifact(
    path: Path, key: PartitionKey, entry: Mapping[str, Any], *, default_hash_rule: str,
) -> VectorArtifact:
    if not path.is_file():
        raise ArtifactMissingError(
            f"{entry['document_id']}: {path} is absent; a rebuild does not re-embed"
        )
    payload = _strict_json(path)
    _accepted_fields(payload, _ARTIFACT_REQUIRED, _ARTIFACT_OPTIONAL, "artifact")
    if payload["schema_version"] != ARTIFACT_SCHEMA_VERSION:
        raise PartitionSchemaError(
            f"unsupported artifact schema_version: {payload['schema_version']!r}"
        )
    rule = _hash_rule(payload.get("hash_rule", default_hash_rule), "artifact.hash_rule")
    if "partition_key_string" in payload and payload["partition_key_string"] != key.key_string():
        raise ManifestKeyMismatchError(
            f"artifact {path} is bound to partition {payload['partition_key_string']!r}"
        )
    document_id = _identifier(payload["document_id"], "artifact.document_id")
    if document_id != entry["document_id"]:
        raise PartitionSchemaError(f"artifact {path} names a different document")
    kind = _artifact_kind(payload.get("artifact_kind"), "artifact.artifact_kind")
    if "artifact_kind" in entry and _artifact_kind(
        entry["artifact_kind"], "manifest.artifact_kind"
    ) != kind:
        raise PartitionSchemaError(f"artifact {path} artifact_kind differs from manifest")
    coordinates_raw = payload["coordinates"]
    if not isinstance(coordinates_raw, list) or not coordinates_raw:
        raise PartitionSchemaError(f"artifact {path} coordinates must be a non-empty array")
    coordinates = tuple(
        _exact_integer(value, f"artifact.coordinates[{index}]")
        for index, value in enumerate(coordinates_raw)
    )
    if "dimension" in payload:
        if _exact_integer(payload["dimension"], "artifact.dimension") != len(coordinates):
            raise PartitionSchemaError(f"artifact {path} dimension does not match coordinates")
    if len(coordinates) != key.dimension:
        raise PartitionSchemaError(
            f"artifact {path} has dimension {len(coordinates)}, partition wants {key.dimension}"
        )
    require_within_scale(coordinates, key=key, where=f"{document_id}.coordinates")
    source_content_hash = _hash(payload["source_content_hash"], "artifact.source_content_hash")
    if source_content_hash != entry["source_content_hash"]:
        raise PartitionSchemaError(f"artifact {path} source_content_hash differs from manifest")
    recorded = _hash(payload["content_hash"], "artifact.content_hash")
    recomputed = payload_hash(payload, hash_field="content_hash", hash_rule=rule)
    if recomputed != recorded or recorded != entry["artifact_content_hash"]:
        raise ArtifactHashMismatchError(
            f"{document_id}: recorded {recorded}, recomputed {recomputed}, "
            f"manifest {entry['artifact_content_hash']}"
        )
    return VectorArtifact(
        document_id=document_id, source_content_hash=source_content_hash,
        coordinates=coordinates, artifact_kind=kind, content_hash=recorded,
    )


__all__ = [
    "ARTIFACT_KINDS",
    "ARTIFACT_KIND_DOCUMENT",
    "ARTIFACT_KIND_QUERY",
    "ARTIFACT_SCHEMA_VERSION",
    "DEFAULT_ARTIFACT_KIND",
    "DEFAULT_HASH_RULE",
    "HASH_RULES",
    "HASH_RULE_POP",
    "HASH_RULE_SET_NULL",
    "MANIFEST_FILENAME",
    "PARTITION_SCHEMA_VERSION",
    "Partition",
    "PartitionKey",
    "PartitionedVector",
    "VECTOR_DIRNAME",
    "VectorArtifact",
    "apply_hash_rule",
    "artifact_content_hash",
    "artifact_payload",
    "artifact_relative_path",
    "create_vector_artifact",
    "load_partition",
    "manifest_payload",
    "partition_key_from_payload",
    "payload_hash",
    "require_within_scale",
    "write_partition",
    "write_vector_artifact",
]
