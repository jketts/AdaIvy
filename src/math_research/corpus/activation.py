"""The content-hashed corpus activation record.

ADR-0050 activates ONE exact-URL public fetch per invocation and pins
``max_requests_per_run: 1``.  This slice does not widen that record and does not
route through ``phase4b.acquisition.acquire``; like ADR-0051's Crossref query it
is a distinct capability with its own activation record, its own origin and its
own bounds.  Saying so is the point: a wider corpus capability must be visible as
a separate authorized record rather than as a loosened old one.

Every traffic and scope bound in the record is ALSO pinned in
:mod:`math_research.corpus.constants` and re-checked here, so editing the JSON
cannot widen a bound.  What the record legitimately carries is the human act:
who authorized it, when the terms were read, and whether it is active at all.
The shipped record is ``pending_owner_activation``; live acquisition refuses
until the owner changes that and the pinned hash below is updated with it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from . import ACTIVATION_SCHEMA_VERSION
from .constants import (
    APPLICABILITY_CEILING, ARXIV_API_ORIGIN, ARXIV_API_QUERY_PATH,
    ARXIV_API_TERMS_URL, CAPABILITY_ID, IDENTIFIER_PATTERN, MAX_ACTIVATION_BYTES,
    MAX_CONCURRENT_CONNECTIONS, MAX_RECORDS_PER_REQUEST, MAX_REQUESTS_PER_RUN,
    MAX_RESPONSE_BYTES, MAX_RIGHTS_SHARDS, MAX_TERMS_AGE_SECONDS,
    METADATA_LICENCE, METADATA_LICENCE_URL, MIN_REQUEST_INTERVAL_MILLISECONDS,
    PROVIDER, REQUEST_TIMEOUT_MILLISECONDS, RIGHTS_SHARD_MAX_DOCUMENTS,
    TERMS_REVIEWED_AT, TRANCHE_MAX_RECORDS, TRUST_EFFECTS,
)
from .errors import (
    ActivationInvalidError, ActivationNotActiveError, TermsReviewStaleError,
)
from .serialization import strict_canonical_object, verify_sealed

#: The exact content hash of ``config/corpus-arxiv-metadata-activation-v1.json``
#: as shipped.  Activation is a human act that changes this record, and the
#: production loader pins the hash so the record and the code are reviewed
#: together.
PRODUCTION_ACTIVATION_HASH = (
    "sha256:c2b53dd9c6d39144d2bb043fd9d103a4ab36f09c0888efc9688f180fae0d1e52"
)

STATUS_ACTIVE = "active"
STATUS_PENDING = "pending_owner_activation"
STATUS_VALUES = (STATUS_ACTIVE, STATUS_PENDING)

ACTIVATION_FIELDS = frozenset({
    "schema_version", "status", "capability_id", "provider", "origin",
    "query_path", "access_mode", "credentials_allowed", "metadata_licence",
    "metadata_licence_url", "full_text_authorized", "full_text_paths_forbidden",
    "min_request_interval_milliseconds", "max_concurrent_connections",
    "max_requests_per_run", "max_records_per_request", "max_records_per_tranche",
    "max_response_bytes", "request_timeout_milliseconds",
    "rights_shard_max_documents", "max_rights_shards",
    "crawling_allowed", "result_following_allowed", "citation_traversal_allowed",
    "export_service_crawling_allowed", "autonomous_origin_selection",
    "terms_url", "terms_reviewed_at", "max_terms_age_seconds",
    "licence_diligence_adr", "applicability_ceiling", "retrieval_corpus_wired",
    "authorized_by", "trust_effects", "content_hash",
})

_AUTHORIZED_BY_FIELDS = frozenset({"actor_id", "actor_kind", "authority"})

#: Every value the record is allowed to state.  A record differing anywhere here
#: is refused, so the JSON is a human signature over pinned bounds rather than a
#: place to negotiate them.
_PINNED: dict[str, Any] = {
    "schema_version": ACTIVATION_SCHEMA_VERSION,
    "capability_id": CAPABILITY_ID,
    "provider": PROVIDER,
    "origin": ARXIV_API_ORIGIN,
    "query_path": ARXIV_API_QUERY_PATH,
    "access_mode": "public_unauthenticated",
    "credentials_allowed": False,
    "metadata_licence": METADATA_LICENCE,
    "metadata_licence_url": METADATA_LICENCE_URL,
    "full_text_authorized": False,
    "full_text_paths_forbidden": True,
    "min_request_interval_milliseconds": MIN_REQUEST_INTERVAL_MILLISECONDS,
    "max_concurrent_connections": MAX_CONCURRENT_CONNECTIONS,
    "max_requests_per_run": MAX_REQUESTS_PER_RUN,
    "max_records_per_request": MAX_RECORDS_PER_REQUEST,
    "max_records_per_tranche": TRANCHE_MAX_RECORDS,
    "max_response_bytes": MAX_RESPONSE_BYTES,
    "request_timeout_milliseconds": REQUEST_TIMEOUT_MILLISECONDS,
    "rights_shard_max_documents": RIGHTS_SHARD_MAX_DOCUMENTS,
    "max_rights_shards": MAX_RIGHTS_SHARDS,
    "crawling_allowed": False,
    "result_following_allowed": False,
    "citation_traversal_allowed": False,
    "export_service_crawling_allowed": False,
    "autonomous_origin_selection": False,
    "terms_url": ARXIV_API_TERMS_URL,
    "terms_reviewed_at": TERMS_REVIEWED_AT,
    "max_terms_age_seconds": MAX_TERMS_AGE_SECONDS,
    "licence_diligence_adr": "adr-0067",
    "applicability_ceiling": APPLICABILITY_CEILING,
    "retrieval_corpus_wired": False,
    "trust_effects": dict(TRUST_EFFECTS),
}


def validate_activation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Structural, exact-field-set and pinned-bound validation of a record."""

    record = verify_sealed(
        value, label="corpus activation record",
        code=ActivationInvalidError.code,
    )
    if set(record) != ACTIVATION_FIELDS:
        raise ActivationInvalidError(
            "corpus activation fields differ: "
            f"missing={sorted(ACTIVATION_FIELDS - set(record))}, "
            f"extra={sorted(set(record) - ACTIVATION_FIELDS)}"
        )
    if record["status"] not in STATUS_VALUES:
        raise ActivationInvalidError(f"unknown activation status {record['status']!r}")
    differing = sorted(key for key, item in _PINNED.items() if record.get(key) != item)
    if differing:
        raise ActivationInvalidError(
            "corpus activation record differs from the bounds pinned in code "
            f"for {differing}; a bound is not negotiable from a config file"
        )
    authorized_by = record["authorized_by"]
    if (
        not isinstance(authorized_by, dict)
        or set(authorized_by) != _AUTHORIZED_BY_FIELDS
        or not isinstance(authorized_by.get("actor_id"), str)
        or IDENTIFIER_PATTERN.fullmatch(authorized_by["actor_id"]) is None
        or authorized_by.get("actor_kind") != "human"
        or authorized_by.get("authority") != "human_final"
    ):
        raise ActivationInvalidError(
            "a corpus activation record is a human-final act and must name one "
            "human actor"
        )
    return record


def load_activation(data: bytes) -> dict[str, Any]:
    """Parse and validate activation bytes. The hash is checked against itself."""

    return validate_activation(strict_canonical_object(
        data, maximum=MAX_ACTIVATION_BYTES,
        label="corpus activation record", code=ActivationInvalidError.code,
    ))


def load_production_activation(data: bytes) -> dict[str, Any]:
    """As :func:`load_activation`, plus the hash pinned in this module."""

    record = load_activation(data)
    if record["content_hash"] != PRODUCTION_ACTIVATION_HASH:
        raise ActivationInvalidError(
            "the corpus activation record does not match the hash pinned in "
            f"code: {record['content_hash']} != {PRODUCTION_ACTIVATION_HASH}"
        )
    return record


def require_active(record: Mapping[str, Any]) -> dict[str, Any]:
    """Live acquisition needs an ACTIVE record; the shipped one is pending."""

    validated = validate_activation(record)
    if validated["status"] != STATUS_ACTIVE:
        raise ActivationNotActiveError(
            "live arXiv metadata acquisition needs an active corpus activation "
            f"record; this one is {validated['status']!r}"
        )
    return validated


def require_current_terms(record: Mapping[str, Any], observed_at_epoch: int) -> None:
    """The terms must have been read, and read recently enough."""

    if isinstance(observed_at_epoch, bool) or not isinstance(observed_at_epoch, int):
        raise TermsReviewStaleError("observation time is not an integer epoch")
    reviewed_at = int(
        datetime.strptime(str(record["terms_reviewed_at"]), "%Y-%m-%d")
        .replace(tzinfo=timezone.utc).timestamp()
    )
    if not reviewed_at <= observed_at_epoch <= reviewed_at + int(record["max_terms_age_seconds"]):
        raise TermsReviewStaleError(
            "the arXiv API terms review is stale or in the future relative to "
            f"the observation time {observed_at_epoch}"
        )


__all__ = [
    "ACTIVATION_FIELDS",
    "PRODUCTION_ACTIVATION_HASH",
    "STATUS_ACTIVE",
    "STATUS_PENDING",
    "STATUS_VALUES",
    "load_activation",
    "load_production_activation",
    "require_active",
    "require_current_terms",
    "validate_activation",
]
