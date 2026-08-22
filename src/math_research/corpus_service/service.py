"""Tranche ingestion into the persistent data root. Local bytes only.

``ingest_tranche`` is a deterministic function of (data root state, policy,
archive, tranche config, recorded_at):

1. validate everything, fail closed, and refuse an archive exceeding its
   tranche bounds rather than truncating it;
2. for each archived document in identifier order: reuse the stored bytes if
   the same ``(document_id, sha256)`` was already acquired (**a second run
   reacquires nothing**), otherwise verify the archive bytes against the
   manifest hash and store them write-once;
3. derive the per-document rights decision from the policy (ADR-0072 §7),
   quarantining anything the policy cannot classify;
4. for admitted documents whose rule permits parsing, parse exact spans and
   store them content-addressed; a parse failure quarantines the document;
5. materialize the Phase 4A decisions through the unchanged ADR-0064 machinery;
6. compute the whole-store generation manifest and publish it only if it
   differs from the latest published generation — an unchanged store yields
   the same content-addressed generation and publishes nothing new;
7. append the campaign-to-corpus usage record for this run.

No step touches the network.  Quarantined and failed documents are retained in
the ledgers and in the run report; they are never discarded.
"""

from __future__ import annotations

import fcntl
from pathlib import Path
from typing import Any, Mapping

from . import GENERATION_SCHEMA_VERSION, RUN_REPORT_SCHEMA_VERSION
from .constants import (
    APPLICABILITY_CEILING,
    CANDIDATE_STATUS,
    IDENTIFIER_PATTERN,
    PROVIDER,
    TIMESTAMP_PATTERN,
    TRUST_EFFECTS,
)
from .dataroot import ledgers_dir, open_data_root, read_object, write_object
from .derivation import (
    STATUS_DERIVED,
    STATUS_QUARANTINED,
    derive_document_rights,
    quarantine_decision,
    verify_derived_decision,
)
from .errors import ArchiveDocumentMismatchError, CorpusServiceError
from .generation import (
    latest_generation_id,
    publish_generation,
    seal_generation,
    tombstoned_document_ids,
)
from .ledger import append_ledger, read_ledger
from .policy import validate_policy
from .ports import ArchiveSource
from .rightsstore import PolicyDerivedRightsWriter
from .serialization import canonical_bytes, sealed, sha256_bytes
from .serialization import strict_canonical_object, verify_sealed
from .snapshot import (
    assert_tranche_within_bounds,
    load_archive_manifest,
    validate_tranche_config,
)
from .spans import ParseFailure, parse_spans


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise CorpusServiceError(f"{label} must be an identifier: {value!r}")
    return value


def _recorded_at(value: Any) -> str:
    if not isinstance(value, str) or TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise CorpusServiceError(
            "recorded_at must be a canonical UTC timestamp argument, not a "
            f"clock read: {value!r}"
        )
    return value


def _latest_rights_state(root: Path) -> dict[str, dict[str, Any]]:
    """document_id -> the latest rights ledger state for it."""

    state: dict[str, dict[str, Any]] = {}
    for record in read_ledger(root, "rights"):
        if record["kind"] in {"rights_derived", "rights_quarantined"}:
            payload = record["payload"]
            document_id = payload["decision"]["document_id"]
            state[document_id] = {
                "decision": verify_derived_decision(payload["decision"]),
                "phase4a_decision_ids": list(payload.get("phase4a_decision_ids") or []),
                "kind": record["kind"],
            }
    return state


def _spans_by_document(root: Path) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for record in read_ledger(root, "rights"):
        if record["kind"] == "spans_parsed":
            payload = record["payload"]
            found[(payload["document_id"], payload["source_sha256"])] = payload["spans_sha256"]
    return found


def _acquired(root: Path) -> dict[str, dict[str, Any]]:
    """document_id -> latest acquisition payload."""

    found: dict[str, dict[str, Any]] = {}
    for record in read_ledger(root, "acquisitions"):
        if record["kind"] == "document_acquired":
            found[record["payload"]["document_id"]] = dict(record["payload"])
    return found


def build_current_generation(root: Path) -> dict[str, Any]:
    """The whole-store generation manifest, computed from the ledgers."""

    tombstoned = tombstoned_document_ids(root)
    rights_state = _latest_rights_state(root)
    spans = _spans_by_document(root)
    acquired = _acquired(root)
    entries: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for document_id in sorted(acquired):
        if document_id in tombstoned:
            continue
        state = rights_state.get(document_id)
        if state is None:
            raise CorpusServiceError(
                f"acquired document {document_id} carries no rights ledger "
                "state; the store is inconsistent",
                code="corpus_store_inconsistent",
            )
        decision = state["decision"]
        payload = acquired[document_id]
        if decision["status"] == STATUS_QUARANTINED:
            quarantined.append({
                "document_id": document_id,
                "source_sha256": payload["source_sha256"],
                "quarantine_reason": decision["quarantine_reason"],
                "policy_content_hash": decision["policy_content_hash"],
                "licence_inputs": dict(decision["licence_inputs"]),
                "decision_content_hash": decision["content_hash"],
            })
            continue
        uses = decision["uses"]
        entries.append({
            "document_id": document_id,
            "source_id": decision["source_id"],
            "source_sha256": payload["source_sha256"],
            "byte_count": payload["byte_count"],
            "media_type": payload["media_type"],
            "licence_inputs": dict(decision["licence_inputs"]),
            "policy_content_hash": decision["policy_content_hash"],
            "rule_id": decision["rule_id"],
            "decision_content_hash": decision["content_hash"],
            "phase4a_decision_ids": sorted(state["phase4a_decision_ids"]),
            "spans_sha256": spans.get((document_id, payload["source_sha256"])),
            "full_text_stored": (document_id, payload["source_sha256"]) in spans,
            "embedding": {
                "value": uses["embedding"]["value"],
                "processor_id": (
                    uses["embedding"]["processor"]["processor_id"]
                    if uses["embedding"]["value"] == "allowed" else None
                ),
            },
            "model_context": {
                "value": uses["model_context"]["value"],
                "processor_id": (
                    uses["model_context"]["processor"]["processor_id"]
                    if uses["model_context"]["value"] == "allowed" else None
                ),
            },
        })
    return seal_generation({
        "schema_version": GENERATION_SCHEMA_VERSION,
        "generation_id": None,
        "provider": PROVIDER,
        "entry_count": len(entries),
        "quarantined_count": len(quarantined),
        "entries": entries,
        "quarantined": quarantined,
        "tombstoned_document_ids": sorted(tombstoned),
        "retrieval_indexed": False,
        "status": CANDIDATE_STATUS,
        "trust_effects": dict(TRUST_EFFECTS),
        "applicability_ceiling": APPLICABILITY_CEILING,
        "content_hash": None,
    })


def _ingest_tranche_unlocked(
    root: Path, *, policy: Mapping[str, Any], archive: ArchiveSource,
    tranche_config: Mapping[str, Any], run_id: str, recorded_at: str,
) -> dict[str, Any]:
    """Ingest one bounded tranche; returns the sealed run report."""

    open_data_root(root)
    run_id = _identifier(run_id, "run_id")
    recorded_at = _recorded_at(recorded_at)
    validated_policy = validate_policy(policy)
    manifest = load_archive_manifest(archive.manifest_bytes())
    config = validate_tranche_config(tranche_config)
    if validated_policy["archive"] != {
        "archive_id": manifest["archive_id"],
        "archive_version": manifest["archive_version"],
    }:
        raise CorpusServiceError(
            "the source-and-rights policy names a different archive identity",
            code="snapshot_policy_archive_mismatch",
        )
    if config["policy_content_hash"] != validated_policy["content_hash"]:
        raise CorpusServiceError(
            "the tranche config pins a different source-and-rights policy",
            code="snapshot_tranche_config_invalid",
        )
    assert_tranche_within_bounds(manifest, config)
    policy_object_hash = write_object(root, canonical_bytes(validated_policy) + b"\n")
    manifest_object_hash = write_object(root, canonical_bytes(manifest) + b"\n")
    config_object_hash = write_object(root, canonical_bytes(config) + b"\n")
    prior_runs = [
        record for record in read_ledger(root, "usage")
        if record["kind"] == "corpus_used" and record["payload"].get("run_id") == run_id
    ]
    if prior_runs:
        payload = prior_runs[-1]["payload"]
        if (
            payload.get("archive_manifest_hash") != manifest["content_hash"]
            or payload.get("policy_content_hash") != validated_policy["content_hash"]
            or payload.get("tranche_id") != config["tranche_id"]
        ):
            raise CorpusServiceError(
                "run_id already identifies a different corpus operation",
                code="corpus_run_id_conflict",
            )
        report_hash = payload.get("run_report_object_hash")
        if report_hash is None:
            raise CorpusServiceError(
                "legacy run record has no replayable terminal report",
                code="corpus_run_not_replayable",
            )
        return verify_sealed(
            strict_canonical_object(
                read_object(root, report_hash), maximum=1_048_576,
                label="corpus run report", code="corpus_run_report_invalid",
            ),
            label="corpus run report", code="corpus_run_report_invalid",
        )

    already_acquired = _acquired(root)
    rights_state = _latest_rights_state(root)
    spans_by_document = _spans_by_document(root)
    tombstoned = tombstoned_document_ids(root)
    writer = PolicyDerivedRightsWriter(
        root, actor_id=validated_policy["authored_by"]["actor_id"],
        valid_from=recorded_at, valid_until=None,
    )

    documents_acquired = 0
    documents_reused = 0
    documents_quarantined = 0
    documents_admitted = 0
    documents_tombstone_skipped = 0
    quarantine_reasons: dict[str, str] = {}

    for document in manifest["documents"]:
        document_id = document["document_id"]
        if document_id in tombstoned:
            # A takedown is not undone by re-ingesting the archive.
            documents_tombstone_skipped += 1
            continue

        prior = already_acquired.get(document_id)
        if prior is not None and prior["source_sha256"] == document["sha256"]:
            read_object(root, prior["source_sha256"])
            documents_reused += 1
        else:
            body = archive.document_bytes(document["relative_path"])
            if sha256_bytes(body) != document["sha256"] or len(body) != document["byte_count"]:
                raise ArchiveDocumentMismatchError(
                    f"archive bytes for {document_id} do not match the "
                    "manifest; a corrupt archive is refused, not repaired"
                )
            write_object(root, body)
            append_ledger(root, "acquisitions", kind="document_acquired", recorded_at=recorded_at, payload={
                "document_id": document_id,
                "source_sha256": document["sha256"],
                "byte_count": document["byte_count"],
                "media_type": document["media_type"],
                "archive_manifest_hash": manifest["content_hash"],
                "tranche_id": config["tranche_id"],
                "run_id": run_id,
            })
            documents_acquired += 1

        decision = derive_document_rights(validated_policy, document)
        if decision["status"] == STATUS_DERIVED:
            rule = next(
                item for item in validated_policy["rules"]
                if item["rule_id"] == decision["rule_id"]
            )
            if (
                rule["full_text"]
                and (document_id, document["sha256"]) not in spans_by_document
            ):
                body = archive.document_bytes(document["relative_path"])
                try:
                    spans_doc = parse_spans(
                        body, document_id=document_id,
                        source_sha256=document["sha256"],
                    )
                except ParseFailure as failure:
                    decision = quarantine_decision(
                        validated_policy, document, "parse_failure",
                    )
                    quarantine_reasons[document_id] = (
                        f"parse_failure: {failure.reason}"
                    )
                else:
                    spans_sha256 = write_object(
                        root, canonical_bytes(spans_doc) + b"\n",
                    )
                    append_ledger(root, "rights", kind="spans_parsed", recorded_at=recorded_at, payload={
                        "document_id": document_id,
                        "source_sha256": document["sha256"],
                        "spans_sha256": spans_sha256,
                        "span_count": spans_doc["span_count"],
                        "transformation": spans_doc["transformation"],
                    })
                    spans_by_document[(document_id, document["sha256"])] = spans_sha256

        existing = rights_state.get(document_id)
        if existing is None or existing["decision"]["content_hash"] != decision["content_hash"]:
            if decision["status"] == STATUS_DERIVED:
                shard_name, record_ids = writer.write_derived_decision(
                    decision, recorded_at=recorded_at,
                )
                append_ledger(root, "rights", kind="rights_derived", recorded_at=recorded_at, payload={
                    "decision": decision,
                    "phase4a_decision_ids": list(record_ids),
                    "rights_shard": shard_name,
                })
                rights_state[document_id] = {
                    "decision": decision,
                    "phase4a_decision_ids": list(record_ids),
                    "kind": "rights_derived",
                }
            else:
                append_ledger(root, "rights", kind="rights_quarantined", recorded_at=recorded_at, payload={
                    "decision": decision,
                    "phase4a_decision_ids": [],
                })
                rights_state[document_id] = {
                    "decision": decision,
                    "phase4a_decision_ids": [],
                    "kind": "rights_quarantined",
                }
        if decision["status"] == STATUS_QUARANTINED:
            documents_quarantined += 1
            quarantine_reasons.setdefault(
                document_id, decision["quarantine_reason"],
            )
        else:
            documents_admitted += 1

    previous_generation_id = latest_generation_id(root)
    generation = build_current_generation(root)
    generation_published = generation["generation_id"] != previous_generation_id
    if generation_published:
        publish_generation(root, generation, run_id=run_id, recorded_at=recorded_at)

    report = sealed({
        "schema_version": RUN_REPORT_SCHEMA_VERSION,
        "provider": PROVIDER,
        "run_id": run_id,
        "tranche_id": config["tranche_id"],
        "archive_manifest_hash": manifest["content_hash"],
        "policy_content_hash": validated_policy["content_hash"],
        "generation_id": generation["generation_id"],
        "generation_hash": generation["content_hash"],
        "generation_published": generation_published,
        "parent_generation_id": previous_generation_id if generation_published else None,
        "documents_total": manifest["document_count"],
        "documents_acquired": documents_acquired,
        "documents_reused": documents_reused,
        "documents_admitted": documents_admitted,
        "documents_quarantined": documents_quarantined,
        "documents_tombstone_skipped": documents_tombstone_skipped,
        "quarantine_reasons": {
            key: quarantine_reasons[key] for key in sorted(quarantine_reasons)
        },
        "documents_with_applicability_record": 0,
        "applicability_ceiling": APPLICABILITY_CEILING,
        "retrieval_indexed": False,
        "status": CANDIDATE_STATUS,
        "trust_effects": dict(TRUST_EFFECTS),
        "network_requests": 0,
        "content_hash": None,
    })
    run_report_object_hash = write_object(root, canonical_bytes(report) + b"\n")
    append_ledger(root, "usage", kind="corpus_used", recorded_at=recorded_at, payload={
        "run_id": run_id,
        "generation_id": generation["generation_id"],
        "tranche_id": config["tranche_id"],
        "archive_manifest_hash": manifest["content_hash"],
        "policy_content_hash": validated_policy["content_hash"],
        "governing_input_object_hashes": {
            "archive_manifest": manifest_object_hash,
            "source_rights_policy": policy_object_hash,
            "tranche_config": config_object_hash,
        },
        "run_report_object_hash": run_report_object_hash,
        "documents_total": manifest["document_count"],
        "documents_acquired": documents_acquired,
        "documents_reused": documents_reused,
        "documents_admitted": documents_admitted,
        "documents_quarantined": documents_quarantined,
        "documents_tombstone_skipped": documents_tombstone_skipped,
    })

    return report


def ingest_tranche(
    root: Path, *, policy: Mapping[str, Any], archive: ArchiveSource,
    tranche_config: Mapping[str, Any], run_id: str, recorded_at: str,
) -> dict[str, Any]:
    """Serialize a whole ingestion transaction and replay duplicate run ids."""

    open_data_root(root)
    lock_path = ledgers_dir(root).joinpath("ingest.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            return _ingest_tranche_unlocked(
                root, policy=policy, archive=archive,
                tranche_config=tranche_config, run_id=run_id,
                recorded_at=recorded_at,
            )
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


__all__ = ["build_current_generation", "ingest_tranche"]
