"""The live arXiv metadata acquisition path, and the dry run that is the default.

This module does not widen ADR-0050.  That record activates one exact-URL public
fetch per invocation and pins ``max_requests_per_run: 1``; nothing here routes
through ``phase4b.acquisition.acquire`` or touches that record.  Like ADR-0051's
Crossref query, this is a distinct capability with its own content-hashed
activation record, its own single origin and its own pinned bounds, so a wider
corpus capability is visible as a new authorized record rather than as a
loosened old one.

Dry run is the default and performs no I/O of any kind.  Live acquisition needs
all of: an ACTIVE activation record whose bounds match the ones pinned in code,
the exact acknowledgement string, the exact plan hash, a terms review inside its
window, a named human operator, and a pacer carrying the pinned traffic bounds.
Each is a separate refusal.

Failures are preserved.  A page that fails leaves a recorded failure entry with
its code and stops the run; it is never dropped and never retried, because a
retry is a second request and the interval bound governs requests, not attempts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .activation import require_active, require_current_terms
from .atom import assert_markup_restricted, parse_feed
from .constants import (
    APPLICABILITY_CEILING, CORPUS_SCOPE, LIVE_ACKNOWLEDGEMENT, PROVIDER,
    TRUST_EFFECTS,
)
from .errors import (
    AcknowledgementRequiredError, ActivationInvalidError, CorpusError,
    RateLimitViolationError,
)
from .ports import MetadataRequest
from .serialization import operational_hash_of, sealed, sha256_bytes
from .store import build_manifest, write_manifest, write_response
from .tranche import (
    assert_metadata_target, plan_hash, planned_request_urls, request_budget,
    request_url, require_plan_hash, validate_plan,
)

ACQUISITION_SCHEMA_VERSION = "adaivy.corpus-acquisition-result.v1"
STATUS_NOT_EXECUTED = "not_executed"
STATUS_ACQUIRED = "acquired"
STATUS_FAILED = "failed"

_ATOM_MEDIA_TYPES = frozenset({
    "application/atom+xml", "application/xml", "text/xml",
})


def _boundaries() -> dict[str, Any]:
    """The two statements ADR-0067 requires every corpus report to carry."""

    return {
        "corpus_is_not_retrieval": (
            "This slice builds a corpus of untrusted candidates. It does not "
            "point retrieval at it; Phase 4C still reads its own frozen "
            "19-document fixture, and wiring real documents into retrieval is a "
            "later slice."
        ),
        "record_is_an_untrusted_inspiration_candidate": (
            "A corpus record creates no applicability, premise, epistemic "
            "warrant or graph admission, and no novelty or significance "
            "assessment. Applicability is human and stays the ceiling."
        ),
        "link_out_obligation": (
            "The arXiv API terms oblige every projection surfacing a record to "
            "link to its abstract page and not to reproduce abstract or title "
            "text beyond fair quotation."
        ),
    }


def dry_run(
    activation: Mapping[str, Any], plan: Mapping[str, Any], *, observed_at_epoch: int,
) -> dict[str, Any]:
    """Show exactly what a live run would request. Performs no I/O."""

    from .activation import validate_activation

    validated_activation = validate_activation(activation)
    validated_plan = validate_plan(plan)
    if isinstance(observed_at_epoch, bool) or not isinstance(observed_at_epoch, int) or observed_at_epoch < 0:
        raise CorpusError("observation time is invalid", code="corpus_observation_time_invalid")
    urls = planned_request_urls(validated_plan)
    return sealed({
        "schema_version": ACQUISITION_SCHEMA_VERSION,
        "provider": PROVIDER,
        "status": STATUS_NOT_EXECUTED,
        "activation_status": validated_activation["status"],
        "activation_hash": validated_activation["content_hash"],
        "tranche_id": validated_plan["tranche_id"],
        "plan_hash": validated_plan["content_hash"],
        "observed_at_epoch": observed_at_epoch,
        "operator_id": None,
        "planned_request_count": len(urls),
        "planned_request_urls": list(urls),
        "min_request_interval_milliseconds": validated_activation[
            "min_request_interval_milliseconds"
        ],
        "max_concurrent_connections": validated_activation["max_concurrent_connections"],
        "requests_made": 0,
        "network_requests": 0,
        "pages": [],
        "failures": [],
        "manifest_hash": None,
        "entry_count": 0,
        "scope": dict(CORPUS_SCOPE),
        "trust_effects": dict(TRUST_EFFECTS),
        "applicability_ceiling": APPLICABILITY_CEILING,
        "boundaries": _boundaries(),
        "content_hash": None,
    })


def acquire_tranche(
    activation: Mapping[str, Any], plan: Mapping[str, Any], *, store_root: Path,
    transport: Any, pacer: Any, acknowledgement: str, confirmed_plan_hash: str,
    observed_at_epoch: int, operator_id: str,
) -> dict[str, Any]:
    """Fetch the tranche's metadata pages under every pinned bound."""

    validated_activation = require_active(activation)
    if acknowledgement != LIVE_ACKNOWLEDGEMENT:
        raise AcknowledgementRequiredError(
            "live arXiv metadata acquisition requires the exact acknowledgement "
            f"{LIVE_ACKNOWLEDGEMENT}"
        )
    validated_plan = require_plan_hash(plan, confirmed_plan_hash)
    require_current_terms(validated_activation, observed_at_epoch)
    if not isinstance(operator_id, str) or not operator_id.strip():
        raise CorpusError("live acquisition names one human operator", code="corpus_operator_absent")
    if getattr(pacer, "min_interval_milliseconds", None) != validated_activation[
        "min_request_interval_milliseconds"
    ]:
        raise RateLimitViolationError(
            "the pacer interval must be exactly the interval pinned in the "
            "activation record"
        )
    if getattr(pacer, "max_concurrent_connections", None) != validated_activation[
        "max_concurrent_connections"
    ]:
        raise RateLimitViolationError(
            "the pacer connection bound must be exactly the pinned bound"
        )
    if validated_activation["full_text_authorized"] is not False:
        raise ActivationInvalidError("full text is not authorized under ADR-0067")

    budget = request_budget(validated_plan)
    pages: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    entry_total = 0
    status = STATUS_ACQUIRED
    for page_index in range(budget):
        url = assert_metadata_target(request_url(validated_plan, page_index))
        try:
            with pacer.request():
                response = transport.fetch(MetadataRequest(
                    url=url,
                    timeout_milliseconds=validated_activation["request_timeout_milliseconds"],
                    max_response_bytes=validated_activation["max_response_bytes"],
                ))
            if response.status != 200:
                raise CorpusError(
                    f"arXiv returned HTTP {response.status}",
                    code="corpus_response_status_not_ok",
                )
            media_type = str(response.media_type).split(";", 1)[0].strip().casefold()
            if media_type not in _ATOM_MEDIA_TYPES:
                raise CorpusError(
                    f"arXiv returned media type {media_type!r}",
                    code="corpus_response_media_type_invalid",
                )
            body = assert_markup_restricted(response.body)
            feed = parse_feed(body)
        except CorpusError as error:
            failures.append({
                "page_index": page_index,
                "request_url": url,
                "failure_code": error.code,
                "failure_detail": str(error)[:512],
            })
            status = STATUS_FAILED
            break
        except Exception as error:  # noqa: BLE001 - an adapter fault is recorded, not raised
            failures.append({
                "page_index": page_index,
                "request_url": url,
                "failure_code": "corpus_transport_adapter_error",
                "failure_detail": type(error).__name__,
            })
            status = STATUS_FAILED
            break
        digest = write_response(store_root, body)
        if digest != sha256_bytes(body):  # pragma: no cover - defensive
            raise CorpusError("stored response identity differs", code="stored_response_hash_mismatch")
        pages.append({
            "page_index": page_index,
            "request_url": url,
            "response_sha256": digest,
            "response_bytes": len(body),
        })
        entry_total += feed["entry_count"]
        if feed["entry_count"] < min(
            validated_plan["page_size"],
            validated_plan["max_records"] - page_index * validated_plan["page_size"],
        ):
            break

    manifest_hash: str | None = None
    if pages:
        manifest_hash = write_manifest(store_root, build_manifest(
            tranche_id=str(validated_plan["tranche_id"]),
            plan_hash=str(validated_plan["content_hash"]),
            pages=pages,
        ))

    semantic = {
        "schema_version": ACQUISITION_SCHEMA_VERSION,
        "provider": PROVIDER,
        "status": status,
        "activation_status": validated_activation["status"],
        "activation_hash": validated_activation["content_hash"],
        "tranche_id": validated_plan["tranche_id"],
        "plan_hash": plan_hash(validated_plan),
        "observed_at_epoch": observed_at_epoch,
        "operator_id": operator_id.strip(),
        "planned_request_count": budget,
        "planned_request_urls": list(planned_request_urls(validated_plan)),
        "min_request_interval_milliseconds": validated_activation[
            "min_request_interval_milliseconds"
        ],
        "max_concurrent_connections": validated_activation["max_concurrent_connections"],
        "requests_made": len(pages) + len(failures),
        "network_requests": len(pages) + len(failures),
        "pages": pages,
        "failures": failures,
        "manifest_hash": manifest_hash,
        "entry_count": entry_total,
        "scope": dict(CORPUS_SCOPE),
        "trust_effects": dict(TRUST_EFFECTS),
        "applicability_ceiling": APPLICABILITY_CEILING,
        "boundaries": _boundaries(),
        "content_hash": None,
    }
    result = sealed(semantic)
    result["operational"] = pacer.observation()
    result["operational_hash"] = operational_hash_of(result)
    return result


__all__ = [
    "ACQUISITION_SCHEMA_VERSION",
    "STATUS_ACQUIRED",
    "STATUS_FAILED",
    "STATUS_NOT_EXECUTED",
    "acquire_tranche",
    "dry_run",
]
