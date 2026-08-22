"""Immutable, content-addressed corpus generations, and takedown.

A generation manifest is the whole active corpus at a point in history:
admitted entries with their rights provenance and span hashes, quarantined
documents, and the tombstoned identifiers excluded from active use.  Its
identity is its content, so two runs over an unchanged store compute the same
``generation_id`` and the second run publishes nothing — that is the Slice 3
exit criterion made structural.  A changed store publishes a NEW generation;
an old one is never edited, and lineage (which generation followed which, and
which takedown invalidated which) lives in the append-only ledgers.

A takedown removes bytes from active use, appends a non-reconstructive
tombstone (hashes and identifiers only, no content), appends a dependency
record naming every generation that carried the document, and invalidates
those generations for active use.  ``require_active_generation`` is the gate a
projection must pass; an invalidated generation stays on disk for audit and
refuses for use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from . import GENERATION_SCHEMA_VERSION
from .constants import (
    APPLICABILITY_CEILING,
    CANDIDATE_STATUS,
    HASH_PATTERN,
    IDENTIFIER_PATTERN,
    MAX_GENERATION_BYTES,
    PROVIDER,
    QUARANTINE_REASONS,
    TRUST_EFFECTS,
)
from .dataroot import generations_dir, object_path
from .errors import (
    DocumentAlreadyTombstonedError,
    DocumentUnknownError,
    GenerationInvalidError,
    GenerationInvalidatedError,
    GenerationMissingError,
    GenerationOverwriteRefusedError,
)
from .ledger import append_ledger, read_ledger
from .serialization import (
    canonical_bytes,
    canonical_hash,
    content_hash_of,
    public_value,
    strict_canonical_object,
)

GENERATION_FIELDS = frozenset({
    "schema_version", "generation_id", "provider", "entry_count",
    "quarantined_count", "entries", "quarantined", "tombstoned_document_ids",
    "retrieval_indexed", "status", "trust_effects", "applicability_ceiling",
    "content_hash",
})
_ENTRY_FIELDS = frozenset({
    "document_id", "source_id", "source_sha256", "byte_count", "media_type",
    "licence_inputs", "policy_content_hash", "rule_id",
    "decision_content_hash", "phase4a_decision_ids", "spans_sha256",
    "full_text_stored", "embedding", "model_context",
})
_QUARANTINED_FIELDS = frozenset({
    "document_id", "source_sha256", "quarantine_reason", "policy_content_hash",
    "licence_inputs", "decision_content_hash",
})
_USE_SUMMARY_FIELDS = frozenset({"value", "processor_id"})

GENERATION_ID_PREFIX = "corpusgen."


def _generation_id(manifest: Mapping[str, Any]) -> str:
    core = {
        key: manifest[key] for key in sorted(manifest)
        if key not in {"generation_id", "content_hash"}
    }
    return GENERATION_ID_PREFIX + canonical_hash(core).removeprefix("sha256:")[:24]


def seal_generation(manifest: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(public_value(manifest))
    result["generation_id"] = _generation_id(result)
    result["content_hash"] = None
    result["content_hash"] = content_hash_of(result)
    return verify_generation(result)


def verify_generation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerationInvalidError("a generation manifest must be an object")
    manifest = dict(public_value(value))
    if set(manifest) != GENERATION_FIELDS:
        raise GenerationInvalidError(
            "generation manifest fields differ: "
            f"missing={sorted(GENERATION_FIELDS - set(manifest))}, "
            f"extra={sorted(set(manifest) - GENERATION_FIELDS)}"
        )
    if manifest["schema_version"] != GENERATION_SCHEMA_VERSION:
        raise GenerationInvalidError("generation manifest schema differs")
    if manifest["provider"] != PROVIDER:
        raise GenerationInvalidError("generation manifest provider differs")
    if manifest["retrieval_indexed"] is not False:
        raise GenerationInvalidError(
            "this slice builds a corpus and does not point retrieval at it; "
            "retrieval_indexed stays false until Slice 4's own gate"
        )
    if manifest["status"] != CANDIDATE_STATUS:
        raise GenerationInvalidError(
            f"every generation document is {CANDIDATE_STATUS!r}"
        )
    if manifest["trust_effects"] != TRUST_EFFECTS:
        raise GenerationInvalidError("generation trust effects differ")
    if manifest["applicability_ceiling"] != APPLICABILITY_CEILING:
        raise GenerationInvalidError("applicability stays human and stays the ceiling")

    entries = manifest["entries"]
    quarantined = manifest["quarantined"]
    tombstoned = manifest["tombstoned_document_ids"]
    if not isinstance(entries, list) or not isinstance(quarantined, list) or not isinstance(tombstoned, list):
        raise GenerationInvalidError("generation manifest lists differ")
    if manifest["entry_count"] != len(entries) or manifest["quarantined_count"] != len(quarantined):
        raise GenerationInvalidError("generation manifest counts differ")

    seen_ids: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != _ENTRY_FIELDS:
            raise GenerationInvalidError(f"generation entry {index} fields differ")
        document_id = entry["document_id"]
        if not isinstance(document_id, str) or IDENTIFIER_PATTERN.fullmatch(document_id) is None:
            raise GenerationInvalidError(f"generation entry {index} identifier differs")
        seen_ids.append(document_id)
        for key in ("source_sha256", "policy_content_hash", "decision_content_hash"):
            if not isinstance(entry[key], str) or HASH_PATTERN.fullmatch(entry[key]) is None:
                raise GenerationInvalidError(f"entry {document_id} {key} differs")
        if entry["spans_sha256"] is not None and (
            not isinstance(entry["spans_sha256"], str)
            or HASH_PATTERN.fullmatch(entry["spans_sha256"]) is None
        ):
            raise GenerationInvalidError(f"entry {document_id} spans hash differs")
        if not isinstance(entry["full_text_stored"], bool):
            raise GenerationInvalidError(f"entry {document_id} full_text_stored differs")
        if entry["full_text_stored"] and entry["spans_sha256"] is None:
            raise GenerationInvalidError(
                f"entry {document_id} stores full text without exact spans"
            )
        if not isinstance(entry["rule_id"], str) or IDENTIFIER_PATTERN.fullmatch(
            entry["rule_id"]
        ) is None:
            raise GenerationInvalidError(f"entry {document_id} rule id differs")
        ids = entry["phase4a_decision_ids"]
        if (
            not isinstance(ids, list) or not ids or ids != sorted(set(ids))
            or any(not isinstance(item, str) for item in ids)
        ):
            raise GenerationInvalidError(f"entry {document_id} decision ids differ")
        for use in ("embedding", "model_context"):
            summary = entry[use]
            if not isinstance(summary, Mapping) or set(summary) != _USE_SUMMARY_FIELDS:
                raise GenerationInvalidError(f"entry {document_id} {use} summary differs")
            if summary["value"] not in {"allowed", "prohibited"}:
                raise GenerationInvalidError(f"entry {document_id} {use} value differs")
            if (summary["value"] == "allowed") != (summary["processor_id"] is not None):
                raise GenerationInvalidError(
                    f"entry {document_id} {use} must name exactly one processor "
                    "when allowed and none otherwise (ADR-0064)"
                )
    if seen_ids != sorted(set(seen_ids)):
        raise GenerationInvalidError("generation entries must be sorted and unique")

    q_ids: list[str] = []
    for index, entry in enumerate(quarantined):
        if not isinstance(entry, Mapping) or set(entry) != _QUARANTINED_FIELDS:
            raise GenerationInvalidError(f"quarantined entry {index} fields differ")
        if entry["quarantine_reason"] not in QUARANTINE_REASONS:
            raise GenerationInvalidError(
                f"quarantined entry {index} reason {entry['quarantine_reason']!r} differs"
            )
        q_ids.append(str(entry["document_id"]))
    if q_ids != sorted(set(q_ids)):
        raise GenerationInvalidError("quarantined entries must be sorted and unique")
    if tombstoned != sorted(set(tombstoned)):
        raise GenerationInvalidError("tombstoned ids must be sorted and unique")
    overlap = set(seen_ids) & (set(q_ids) | set(tombstoned))
    if overlap:
        raise GenerationInvalidError(
            f"documents cannot be both active and excluded: {sorted(overlap)}"
        )

    if manifest["generation_id"] != _generation_id(manifest):
        raise GenerationInvalidError("generation identity differs from its content")
    supplied = manifest["content_hash"]
    if not isinstance(supplied, str) or HASH_PATTERN.fullmatch(supplied) is None:
        raise GenerationInvalidError("generation content hash is not a sha256 value")
    if content_hash_of(manifest) != supplied:
        raise GenerationInvalidError("generation content hash does not match its content")
    return manifest


def generation_path(root: Path, generation_id: str) -> Path:
    if not isinstance(generation_id, str) or IDENTIFIER_PATTERN.fullmatch(generation_id) is None:
        raise GenerationMissingError(f"not a generation identifier: {generation_id!r}")
    return generations_dir(root).joinpath(generation_id + ".json")


def publish_generation(
    root: Path, manifest: Mapping[str, Any], *, run_id: str, recorded_at: str,
) -> dict[str, Any]:
    """Write the immutable manifest (write-once) and the lineage event.

    If the identical generation is already published, nothing is written and
    the existing lineage record is returned unchanged — publication is
    idempotent, never a mutation.
    """

    verified = verify_generation(manifest)
    generation_id = verified["generation_id"]
    lineage = read_ledger(root, "lineage")
    publications = [
        record for record in lineage if record["kind"] == "generation_published"
    ]
    for record in publications:
        if record["payload"]["generation_id"] == generation_id:
            return record
    parent = publications[-1]["payload"]["generation_id"] if publications else None
    path = generation_path(root, generation_id)
    if path.exists():
        existing = strict_canonical_object(
            path.read_bytes(), maximum=MAX_GENERATION_BYTES,
            label="generation manifest", code=GenerationInvalidError.code,
        )
        if existing != verified:
            raise GenerationOverwriteRefusedError(
                f"a different manifest already occupies {generation_id}"
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".partial")
        temporary.write_bytes(canonical_bytes(verified) + b"\n")
        temporary.replace(path)
    return append_ledger(root, "lineage", kind="generation_published", recorded_at=recorded_at, payload={
        "generation_id": generation_id,
        "generation_hash": verified["content_hash"],
        "parent_generation_id": parent,
        "run_id": run_id,
    })


def load_generation(root: Path, generation_id: str) -> dict[str, Any]:
    path = generation_path(root, generation_id)
    try:
        data = path.read_bytes()
    except OSError as error:
        raise GenerationMissingError(f"no generation manifest at {path}") from error
    manifest = verify_generation(strict_canonical_object(
        data, maximum=MAX_GENERATION_BYTES, label="generation manifest",
        code=GenerationInvalidError.code,
    ))
    if manifest["generation_id"] != generation_id:
        raise GenerationInvalidError(
            f"manifest at {path} declares {manifest['generation_id']!r}"
        )
    return manifest


def invalidated_generation_ids(root: Path) -> frozenset[str]:
    return frozenset(
        record["payload"]["generation_id"]
        for record in read_ledger(root, "lineage")
        if record["kind"] == "generation_invalidated"
    )


def latest_generation_id(root: Path) -> str | None:
    publications = [
        record for record in read_ledger(root, "lineage")
        if record["kind"] == "generation_published"
    ]
    return publications[-1]["payload"]["generation_id"] if publications else None


def tombstoned_document_ids(root: Path) -> frozenset[str]:
    return frozenset(
        record["payload"]["document_id"]
        for record in read_ledger(root, "tombstones")
        if record["kind"] == "document_tombstoned"
    )


def require_active_generation(root: Path, generation_id: str) -> dict[str, Any]:
    """The gate a projection must pass before serving a generation."""

    manifest = load_generation(root, generation_id)
    if generation_id in invalidated_generation_ids(root):
        raise GenerationInvalidatedError(
            f"{generation_id} was invalidated by a takedown and is retained "
            "for audit only"
        )
    tombstoned = tombstoned_document_ids(root)
    struck = sorted(
        entry["document_id"] for entry in manifest["entries"]
        if entry["document_id"] in tombstoned
    )
    if struck:
        raise GenerationInvalidatedError(
            f"{generation_id} carries tombstoned documents {struck}"
        )
    return manifest


def record_takedown(
    root: Path, *, document_id: str, reason_detail: str, actor_id: str,
    recorded_at: str, rights_writer: Any,
) -> dict[str, Any]:
    """Remove one document from active use. Non-reconstructive, recorded.

    Deletes the source bytes (and span object) only when no other active
    document shares them; appends the tombstone with hashes only; supersedes
    the document's Phase 4A decisions with PROHIBITED / rights_revoked;
    invalidates every generation that carried the document.  Nothing is ever
    prompted and nothing else is deleted.
    """

    existing_tombstone = next((
        record for record in reversed(read_ledger(root, "tombstones"))
        if record["kind"] == "document_tombstoned"
        and record["payload"]["document_id"] == document_id
    ), None)
    if existing_tombstone is not None:
        return existing_tombstone
    acquisitions = [
        record for record in read_ledger(root, "acquisitions")
        if record["kind"] == "document_acquired"
        and record["payload"]["document_id"] == document_id
    ]
    if not acquisitions:
        raise DocumentUnknownError(
            f"no acquisition record names {document_id}; nothing to take down"
        )
    payload = acquisitions[-1]["payload"]
    source_sha256 = payload["source_sha256"]
    source_hashes = sorted({record["payload"]["source_sha256"] for record in acquisitions})
    spans_sha256 = None
    span_hashes: set[str] = set()
    for record in read_ledger(root, "rights"):
        if record["kind"] == "spans_parsed" and record["payload"]["document_id"] == document_id:
            spans_sha256 = record["payload"]["spans_sha256"]
            span_hashes.add(spans_sha256)

    dependent = sorted(
        record["payload"]["generation_id"]
        for record in read_ledger(root, "lineage")
        if record["kind"] == "generation_published"
        and any(
            entry["document_id"] == document_id
            for entry in load_generation(
                root, record["payload"]["generation_id"]
            )["entries"]
        )
    )

    # Resolve vector artifacts through the retrieval service's strict loader
    # while the dependent corpus generations are still active.  Raw projection
    # JSON is never deletion authority: an attacker must not be able to place a
    # self-consistent-looking file in ``generations/retrieval`` and cause an
    # arbitrary object-store digest to be unlinked during takedown.
    vector_hashes: set[str] = set()
    retrieval_dir = generations_dir(root).joinpath("retrieval")
    if retrieval_dir.exists():
        from ..corpus_retrieval import CorpusRetrievalError, load_projection

        for projection_path in sorted(retrieval_dir.glob("retrievalgen.*.json")):
            try:
                projection = load_projection(root, projection_path.stem)
            except (CorpusRetrievalError, OSError, KeyError, TypeError, ValueError):
                continue
            for entry in projection.manifest["vectors"]:
                if entry["document_id"] == document_id:
                    vector_hashes.add(entry["artifact_object_hash"])

    from .derivation import source_id_for
    source_id = source_id_for(document_id)
    revocation_record_ids: list[str] = []
    if rights_writer.locate(source_id) is not None:
        revocation_record_ids = list(rights_writer.record_takedown(
            source_id, actor_id=actor_id, reason_detail=reason_detail,
            evidence_refs=(f"evidence.corpus-takedown.{document_id}",),
            recorded_at=recorded_at,
        ))

    for generation_id in dependent:
        already = invalidated_generation_ids(root)
        if generation_id not in already:
            append_ledger(root, "lineage", kind="generation_invalidated", recorded_at=recorded_at, payload={
                "generation_id": generation_id,
                "cause": "takedown",
                "document_id": document_id,
            })

    still_referenced = {
        record["payload"]["source_sha256"]
        for record in read_ledger(root, "acquisitions")
        if record["kind"] == "document_acquired"
        and record["payload"]["document_id"] != document_id
        and record["payload"]["document_id"] not in tombstoned_document_ids(root)
    }
    for digest in (*source_hashes, *sorted(span_hashes), *sorted(vector_hashes)):
        if digest is None or digest in still_referenced:
            continue
        path = object_path(root, digest)
        if path.exists():
            path.unlink()
    return append_ledger(root, "tombstones", kind="document_tombstoned", recorded_at=recorded_at, payload={
        "document_id": document_id,
        "source_sha256": source_sha256,
        "source_sha256_history": source_hashes,
        "spans_sha256": spans_sha256,
        "spans_sha256_history": sorted(span_hashes),
        "vector_artifact_hashes_removed": sorted(vector_hashes),
        "reason_detail": reason_detail,
        "actor_id": actor_id,
        "dependent_generation_ids": dependent,
        "phase4a_revocation_record_ids": sorted(revocation_record_ids),
        "bytes_removed_from_active_use": True,
    })


__all__ = [
    "GENERATION_FIELDS",
    "GENERATION_ID_PREFIX",
    "generation_path",
    "invalidated_generation_ids",
    "latest_generation_id",
    "load_generation",
    "publish_generation",
    "record_takedown",
    "require_active_generation",
    "seal_generation",
    "tombstoned_document_ids",
    "verify_generation",
]
