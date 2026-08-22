"""Depth-one discovery-result following (ADR-0068, implemented by ADR-0081).

References, DOIs, and links found in the metadata of an *already acquired*
document may be enqueued as discovery candidates — never fetched here, never
trusted, and never followed further. Enforced structurally:

- depth is exactly one: a followed candidate, or any document carrying a
  followed-provenance marker, is refused as an origin;
- the target host must be on a content-hashed human-maintained allowlist;
- at most ``max_followed_per_run`` candidates are enqueued; the overflow is
  retained as machine-readable refusals, not silently dropped;
- every followed candidate records its provenance edge (which document, which
  reference field, which value) and ``origin_selected_by: "automation"``;
- enqueued candidates keep ``acquisition_authorized: false`` and every
  assessment ``not_assessed``: acquisition remains a separate rights-checked
  Phase 4A/4B decision.
"""

from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import quote, urlsplit

from ..phase4b.serialization import canonical_hash
from .discovery import _is_normal_text

ALLOWLIST_SCHEMA = "adaivy.phase4d-follow-allowlist.v1"
FOLLOW_SCHEMA = "adaivy.phase4d-followed-candidates.v1"
MAX_ALLOWLIST_HOSTS = 32
MAX_FOLLOWED_PER_RUN_CEILING = 128
MAX_REFERENCES_PER_DOCUMENT = 256
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_HOST = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?)+$")
_DOCUMENT_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_REFERENCE_FIELDS = {"reference_doi", "reference_url"}
_FOLLOWED_MARKERS = frozenset({"provenance", "origin_selected_by", "depth"})


def build_follow_allowlist(hosts: Iterable[str]) -> dict[str, Any]:
    """Content-hash the human-maintained set of followable hosts."""

    values = sorted(set(hosts))
    if not 1 <= len(values) <= MAX_ALLOWLIST_HOSTS or any(
        _HOST.fullmatch(host) is None for host in values
    ):
        raise ValueError("follow allowlist hosts are invalid")
    value: dict[str, Any] = {"schema_version": ALLOWLIST_SCHEMA, "hosts": values}
    value["content_hash"] = canonical_hash(value)
    return value


def validate_follow_allowlist(allowlist: Any) -> dict[str, Any]:
    if (
        not isinstance(allowlist, dict)
        or set(allowlist) != {"schema_version", "hosts", "content_hash"}
        or allowlist.get("schema_version") != ALLOWLIST_SCHEMA
    ):
        raise ValueError("follow allowlist fields differ")
    supplied = allowlist.get("content_hash")
    if _SHA256.fullmatch(str(supplied)) is None or canonical_hash(
        {key: value for key, value in allowlist.items() if key != "content_hash"}
    ) != supplied:
        raise ValueError("follow allowlist identity differs")
    hosts = allowlist.get("hosts")
    if (
        not isinstance(hosts, list) or not 1 <= len(hosts) <= MAX_ALLOWLIST_HOSTS
        or hosts != sorted(set(hosts))
        or any(not isinstance(host, str) or _HOST.fullmatch(host) is None for host in hosts)
    ):
        raise ValueError("follow allowlist hosts differ")
    return allowlist


def _reference_url(field: str, value: str) -> str | None:
    if field == "reference_doi":
        if _DOI.fullmatch(value) is None:
            return None
        return "https://doi.org/" + quote(value.casefold(), safe="/")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.query or parts.fragment:
        return None
    return value


def follow_references(
    documents: Iterable[dict[str, Any]], *, allowlist: dict[str, Any],
    max_followed_per_run: int,
) -> dict[str, Any]:
    """Enqueue depth-one follow candidates from acquired document metadata."""

    validate_follow_allowlist(allowlist)
    if (
        isinstance(max_followed_per_run, bool)
        or not isinstance(max_followed_per_run, int)
        or not 1 <= max_followed_per_run <= MAX_FOLLOWED_PER_RUN_CEILING
    ):
        raise ValueError("max_followed_per_run is out of bounds")
    hosts = set(allowlist["hosts"])
    followed: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    seen_urls: set[str] = set()
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("followed-origin document is not a record")
        if _FOLLOWED_MARKERS & set(document):
            # Depth two, absolutely refused: a followed candidate never
            # becomes an origin (ADR-0068 control 2).
            raise ValueError("a followed candidate may not originate further follows")
        if set(document) != {"document_id", "acquired", "references"}:
            raise ValueError("followed-origin document fields differ")
        document_id = document.get("document_id")
        if not isinstance(document_id, str) or _DOCUMENT_ID.fullmatch(document_id) is None:
            raise ValueError("followed-origin document identifier is invalid")
        if document.get("acquired") is not True:
            raise ValueError("only an acquired document may originate follows")
        if document_id in seen_documents:
            raise ValueError("followed-origin documents must be unique")
        seen_documents.add(document_id)
        references = document.get("references")
        if not isinstance(references, list) or len(references) > MAX_REFERENCES_PER_DOCUMENT:
            raise ValueError("followed-origin references are invalid")
        for index, reference in enumerate(references):
            if (
                not isinstance(reference, dict)
                or set(reference) != {"field", "value"}
                or reference.get("field") not in _REFERENCE_FIELDS
                or not _is_normal_text(reference.get("value"), 512)
            ):
                raise ValueError("followed-origin reference record is invalid")
            field = reference["field"]
            value = reference["value"]
            provenance = {
                "origin_document_id": document_id,
                "reference_field": field,
                "reference_index": index,
                "reference_value": value,
            }
            url = _reference_url(field, value)
            if url is None:
                refused.append({**provenance, "reason": "refused_reference_malformed"})
                continue
            host = urlsplit(url).hostname
            if host not in hosts:
                refused.append({**provenance, "reason": "refused_offlist_origin"})
                continue
            if url in seen_urls:
                refused.append({**provenance, "reason": "refused_duplicate_target"})
                continue
            if len(followed) >= max_followed_per_run:
                refused.append({**provenance, "reason": "refused_fanout_bound"})
                continue
            seen_urls.add(url)
            core = {"candidate_url": url, "provenance": provenance}
            followed.append({
                "candidate_id": "followed." + canonical_hash(core).removeprefix("sha256:")[:24],
                "candidate_url": url,
                "provider": "followed_reference",
                "origin_selected_by": "automation",
                "depth": 1,
                "provenance": provenance,
                "status": "untrusted_inspiration_candidate",
                "relevance": "not_assessed",
                "applicability": "not_assessed",
                "acquisition_authorized": False,
                "mathematical_warrant": "none",
                "novelty": "not_assessed",
                "significance": "not_assessed",
            })
    value: dict[str, Any] = {
        "schema_version": FOLLOW_SCHEMA,
        "allowlist_hash": allowlist["content_hash"],
        "max_followed_per_run": max_followed_per_run,
        "followed_count": len(followed),
        "refused_count": len(refused),
        "followed": followed,
        "refused": refused,
        "inspiration_only": True,
    }
    value["content_hash"] = canonical_hash(value)
    return value


def verify_followed(record: Any, allowlist: dict[str, Any]) -> dict[str, Any]:
    """Recheck a followed-candidates record against the pinned allowlist."""

    validate_follow_allowlist(allowlist)
    expected = {
        "schema_version", "allowlist_hash", "max_followed_per_run",
        "followed_count", "refused_count", "followed", "refused",
        "inspiration_only", "content_hash",
    }
    if not isinstance(record, dict) or set(record) != expected \
            or record.get("schema_version") != FOLLOW_SCHEMA:
        raise ValueError("followed-candidates record fields differ")
    supplied = record.get("content_hash")
    if _SHA256.fullmatch(str(supplied)) is None or canonical_hash(
        {key: value for key, value in record.items() if key != "content_hash"}
    ) != supplied:
        raise ValueError("followed-candidates record identity differs")
    if record.get("allowlist_hash") != allowlist["content_hash"] \
            or record.get("inspiration_only") is not True:
        raise ValueError("followed-candidates record binding differs")
    cap = record.get("max_followed_per_run")
    if isinstance(cap, bool) or not isinstance(cap, int) \
            or not 1 <= cap <= MAX_FOLLOWED_PER_RUN_CEILING:
        raise ValueError("followed-candidates cap differs")
    followed = record.get("followed")
    refused = record.get("refused")
    if (
        not isinstance(followed, list) or not isinstance(refused, list)
        or record.get("followed_count") != len(followed)
        or record.get("refused_count") != len(refused)
        or len(followed) > cap
    ):
        raise ValueError("followed-candidates accounting differs")
    hosts = set(allowlist["hosts"])
    for item in followed:
        provenance = item.get("provenance") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict) or not isinstance(provenance, dict)
            or item.get("origin_selected_by") != "automation"
            or item.get("depth") != 1
            or item.get("provider") != "followed_reference"
            or item.get("status") != "untrusted_inspiration_candidate"
            or item.get("acquisition_authorized") is not False
            or item.get("mathematical_warrant") != "none"
            or item.get("relevance") != "not_assessed"
            or item.get("applicability") != "not_assessed"
            or item.get("novelty") != "not_assessed"
            or item.get("significance") != "not_assessed"
            or set(provenance) != {
                "origin_document_id", "reference_field", "reference_index",
                "reference_value",
            }
            or provenance.get("reference_field") not in _REFERENCE_FIELDS
            or urlsplit(str(item.get("candidate_url"))).hostname not in hosts
        ):
            raise ValueError("followed candidate semantics differ")
        core = {"candidate_url": item["candidate_url"], "provenance": provenance}
        expected_id = "followed." + canonical_hash(core).removeprefix("sha256:")[:24]
        if item.get("candidate_id") != expected_id:
            raise ValueError("followed candidate identity differs")
    return record


__all__ = [
    "ALLOWLIST_SCHEMA", "FOLLOW_SCHEMA", "MAX_ALLOWLIST_HOSTS",
    "MAX_FOLLOWED_PER_RUN_CEILING", "MAX_REFERENCES_PER_DOCUMENT",
    "build_follow_allowlist", "follow_references", "validate_follow_allowlist",
    "verify_followed",
]
