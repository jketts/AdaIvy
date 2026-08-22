"""Derive corpus records from stored response bytes and per-document rights.

Ingestion is a pure function of the response store plus the tranche plan: given
the same bytes and the same plan it produces byte-identical records, which is
what makes replay meaningful.

**Ordering, stated because it is subtle.**  A document's identity is only known
after its feed entry is decoded, so the three Phase 4A decisions cannot all
precede every byte being touched.  The ordering this module implements is:

1. the plan's human-final rights declaration exists before any byte is fetched
   (:mod:`acquisition` refuses without it);
2. the stored Atom response is decoded into declared metadata fields -- this is
   the metadata decode covered by the acquisition and retention declaration;
3. one acquisition, one storage/retention and one parsing decision are appended
   per identified document;
4. all three are re-evaluated per document, and only then is a record
   materialized.  A document whose rights do not evaluate permitted produces no
   record at all, and the run fails closed rather than skipping it quietly.

Nothing here assesses applicability.  ``records_with_applicability_record`` is
COMPUTED from durable Phase 4A applicability reviews, so on a fresh tranche it
is zero and the report says so next to the record count.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from . import INGESTION_SCHEMA_VERSION
from .atom import parse_feed
from .constants import (
    APPLICABILITY_CEILING, CORPUS_SCOPE, PROVIDER, TIMESTAMP_PATTERN, TRUST_EFFECTS,
)
from .errors import (
    CategoryNotMathematicsError, CorpusError, TrancheBoundExceededError,
)
from .records import build_record, source_id_for, verify_record
from .serialization import sealed
from .store import load_manifest, read_response, verify_manifest_against_plan
from .tranche import validate_plan


def _recorded_at(value: Any) -> str:
    if not isinstance(value, str) or TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise CorpusError(
            f"recorded_at must be a canonical UTC timestamp argument, not a clock "
            f"read: {value!r}",
            code="corpus_recorded_at_invalid",
        )
    return value


def decode_pages(root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read and decode every stored page. Absent bytes refuse; nothing refetches."""

    decoded: list[dict[str, Any]] = []
    for page in manifest["pages"]:
        body = read_response(root, page["response_sha256"])
        feed = parse_feed(body)
        decoded.append({
            "page_index": page["page_index"],
            "response_sha256": page["response_sha256"],
            "entry_count": feed["entry_count"],
            "entries": feed["entries"],
        })
    return decoded


def ingest_from_store(
    root: Path, plan: Mapping[str, Any], *, rights_writer: Any, recorded_at: str,
    expected_manifest_hash: str | None = None,
) -> dict[str, Any]:
    """Build the tranche's corpus records from stored bytes. No network."""

    validated_plan = validate_plan(plan)
    recorded_at = _recorded_at(recorded_at)
    manifest = load_manifest(root, expected_manifest_hash=expected_manifest_hash)
    verify_manifest_against_plan(manifest, validated_plan)

    permitted_categories = set(validated_plan["categories"])
    entries: list[dict[str, Any]] = []
    response_by_id: dict[str, str] = {}
    duplicates: list[str] = []
    seen: set[str] = set()
    for page in decode_pages(root, manifest):
        for entry in page["entries"]:
            identifier = entry["arxiv_id"]
            if identifier in seen:
                duplicates.append(identifier)
                continue
            if not permitted_categories.intersection(entry["categories"]):
                raise CategoryNotMathematicsError(
                    f"{identifier} carries none of the planned categories "
                    f"{sorted(permitted_categories)}; a corpus run does not widen "
                    "its own tranche"
                )
            seen.add(identifier)
            entries.append(entry)
            response_by_id[identifier] = page["response_sha256"]

    if len(entries) > validated_plan["max_records"]:
        raise TrancheBoundExceededError(
            f"the store yields {len(entries)} records; the plan pins "
            f"{validated_plan['max_records']}"
        )

    source_ids = [source_id_for(entry["arxiv_id"]) for entry in entries]
    rights_writer.write_tranche_rights(source_ids, recorded_at=recorded_at)

    records: list[dict[str, Any]] = []
    for entry in entries:
        source_id = source_id_for(entry["arxiv_id"])
        decision_ids = rights_writer.require_document_rights(source_id, at=recorded_at)
        records.append(verify_record(build_record(
            entry,
            tranche_id=str(validated_plan["tranche_id"]),
            plan_hash=str(validated_plan["content_hash"]),
            response_sha256=response_by_id[entry["arxiv_id"]],
            rights_decision_ids=decision_ids,
        )))
    records.sort(key=lambda record: record["record_id"])

    applicability = list(rights_writer.applicability_source_ids())
    result = {
        "schema_version": INGESTION_SCHEMA_VERSION,
        "provider": PROVIDER,
        "tranche_id": validated_plan["tranche_id"],
        "plan_hash": validated_plan["content_hash"],
        "manifest_hash": manifest["content_hash"],
        "page_count": manifest["page_count"],
        "record_count": len(records),
        "records": records,
        "duplicate_arxiv_ids": sorted(set(duplicates)),
        "rights_shards": list(rights_writer.shard_names_written()),
        "rights_records_written": rights_writer.rights_record_count(),
        "records_with_applicability_record": len(applicability),
        "applicability_evidence": applicability,
        "applicability_ceiling": APPLICABILITY_CEILING,
        "scope": dict(CORPUS_SCOPE),
        "trust_effects": dict(TRUST_EFFECTS),
        "network_requests": 0,
        "content_hash": None,
    }
    return sealed(result)


__all__ = ["decode_pages", "ingest_from_store"]
