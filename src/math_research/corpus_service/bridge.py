"""The ADR-0080 silo bridge: arXiv metadata records into the corpus service.

The ADR-0067 arXiv metadata store (:mod:`math_research.corpus`) and the
ADR-0072 persistent corpus service grew as parallel silos.  This bridge feeds
the former into the latter: each verified arXiv corpus record becomes one
descriptive-metadata document — the quotation-capped title, the quotation-
capped abstract, and the link-out abstract URL, exactly the material the
metadata projection is already allowed to show — ingested through the ordinary
tranche path under the human-authored source-and-rights policy.

Rights restrictions are preserved, not translated away:

* the per-document licence inputs are the record's own metadata licence
  (CC0-1.0 for arXiv descriptive metadata), so the policy classifies them
  under an exact licence-string rule or quarantines them;
* the policy rule matching that licence must declare ``full_text: false`` —
  descriptive metadata never becomes stored full text, and a policy that says
  otherwise is refused before any bytes move.  The e-prints themselves remain
  unacquired; reaching them is the separately gated fetch path.

The bridge is deterministic: the same records and policy produce the same
archive manifest, the same tranche config, and therefore the same generation.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..corpus.constants import (
    MAX_QUOTED_ABSTRACT_CHARS,
    MAX_QUOTED_TITLE_CHARS,
    QUOTATION_ELLIPSIS,
)
from ..corpus.records import verify_record
from . import ARCHIVE_MANIFEST_SCHEMA_VERSION, TRANCHE_CONFIG_SCHEMA_VERSION
from .constants import PROVIDER
from .errors import (
    BridgeMetadataFullTextForbiddenError,
    BridgeRecordInvalidError,
)
from .extraction import ExtractorRegistry
from .policy import rule_for_licence, validate_policy
from .serialization import canonical_bytes, sealed, sha256_bytes
from .service import ingest_tranche
from .snapshot import validate_archive_manifest, validate_tranche_config

BRIDGE_ARCHIVE_ID = "archive.arxiv-metadata-bridge"
BRIDGE_MEDIA_TYPE = "text/plain"


def _quote(text: str, maximum: int) -> str:
    if len(text) <= maximum:
        return text
    return text[: maximum - len(QUOTATION_ELLIPSIS)] + QUOTATION_ELLIPSIS


def metadata_document_text(record: Mapping[str, Any]) -> str:
    """The deterministic descriptive-metadata rendering of one record.

    Quotation caps from the ADR-0067 slice apply: the terms oblige a
    projection to link out rather than reproduce, so the document quotes,
    truncates, and carries the abstract-page URL.
    """

    title = _quote(record["title"], MAX_QUOTED_TITLE_CHARS)
    abstract = _quote(record["abstract"], MAX_QUOTED_ABSTRACT_CHARS)
    return f"{title}\n\n{abstract}\n\n{record['abstract_url']}\n"


def build_bridge_archive(
    records: Iterable[Mapping[str, Any]], *, archive_version: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """(sealed archive manifest, relative_path -> document bytes)."""

    documents: list[dict[str, Any]] = []
    bodies: dict[str, bytes] = {}
    seen: set[str] = set()
    for record in records:
        verified = verify_record(record)
        document_id = verified["source_id"]
        if document_id in seen:
            raise BridgeRecordInvalidError(
                f"two records map to document {document_id}"
            )
        seen.add(document_id)
        body = metadata_document_text(verified).encode("utf-8")
        relative_path = f"arxiv/{document_id}.txt"
        bodies[relative_path] = body
        documents.append({
            "document_id": document_id,
            "relative_path": relative_path,
            "media_type": BRIDGE_MEDIA_TYPE,
            "byte_count": len(body),
            "sha256": sha256_bytes(body),
            "licence": {
                "licence": verified["metadata_licence"],
                "licence_url": verified["metadata_licence_url"],
            },
        })
    if not documents:
        raise BridgeRecordInvalidError("the bridge needs at least one record")
    documents.sort(key=lambda item: item["document_id"])
    manifest = validate_archive_manifest(sealed({
        "schema_version": ARCHIVE_MANIFEST_SCHEMA_VERSION,
        "provider": PROVIDER,
        "archive_id": BRIDGE_ARCHIVE_ID,
        "archive_version": archive_version,
        "documents": documents,
        "document_count": len(documents),
        "total_bytes": sum(item["byte_count"] for item in documents),
        "content_hash": None,
    }))
    return manifest, bodies


class MappingArchiveSource:
    """An in-memory archive: the bridge's manifest plus rendered bodies."""

    def __init__(self, manifest: Mapping[str, Any], bodies: Mapping[str, bytes]) -> None:
        self._manifest = validate_archive_manifest(manifest)
        self._bodies = dict(bodies)

    def manifest_bytes(self) -> bytes:
        return canonical_bytes(self._manifest) + b"\n"

    def document_bytes(self, relative_path: str) -> bytes:
        try:
            return self._bodies[relative_path]
        except KeyError as error:
            raise BridgeRecordInvalidError(
                f"bridge archive document {relative_path!r} is absent"
            ) from error


def _assert_metadata_stays_metadata(
    policy: Mapping[str, Any], manifest: Mapping[str, Any],
) -> None:
    for document in manifest["documents"]:
        rule = rule_for_licence(policy, document["licence"]["licence"])
        if rule is not None and rule["full_text"]:
            raise BridgeMetadataFullTextForbiddenError(
                f"policy rule {rule['rule_id']} stores full text for licence "
                f"{document['licence']['licence']!r}; arXiv descriptive "
                "metadata never authorizes full-text storage — the e-print is "
                "a separate, separately gated acquisition"
            )


def import_arxiv_metadata(
    root, *, records: Iterable[Mapping[str, Any]], policy: Mapping[str, Any],
    tranche_id: str, archive_version: str, run_id: str, recorded_at: str,
    max_document_bytes: int = 65_536,
    extractors: ExtractorRegistry | None = None,
) -> dict[str, Any]:
    """One-shot bridge import through the ordinary tranche machinery.

    The tranche config is sealed here, selected by the policy's human-final
    author: the human act that authorizes the import is the policy naming the
    bridge archive, exactly as ADR-0072 §7 moved rights authority into it.
    """

    validated_policy = validate_policy(policy)
    manifest, bodies = build_bridge_archive(records, archive_version=archive_version)
    _assert_metadata_stays_metadata(validated_policy, manifest)
    config = validate_tranche_config(sealed({
        "schema_version": TRANCHE_CONFIG_SCHEMA_VERSION,
        "tranche_id": tranche_id,
        "archive_manifest_hash": manifest["content_hash"],
        "policy_content_hash": validated_policy["content_hash"],
        "max_documents": manifest["document_count"],
        "max_total_bytes": max(manifest["total_bytes"], 1),
        "max_document_bytes": max_document_bytes,
        "selected_by": dict(validated_policy["authored_by"]),
        "content_hash": None,
    }))
    return ingest_tranche(
        root, policy=validated_policy,
        archive=MappingArchiveSource(manifest, bodies),
        tranche_config=config, run_id=run_id, recorded_at=recorded_at,
        extractors=extractors,
    )


__all__ = [
    "BRIDGE_ARCHIVE_ID",
    "BRIDGE_MEDIA_TYPE",
    "MappingArchiveSource",
    "build_bridge_archive",
    "import_arxiv_metadata",
    "metadata_document_text",
]
