"""Grounded, bounded Crossref discovery with no trust or acquisition effect."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import json
import re
import unicodedata
from typing import Any, Iterable
from urllib.parse import quote, quote_plus

from ..phase4b.acquisition import (
    AcquisitionPolicyError, Resolution, TransportFailure, TransportRequest,
)
from ..phase4b.live_transport import LiveNetworkPermit
from ..phase4b.serialization import canonical_bytes, canonical_hash, sha256_bytes


CONFIG_SCHEMA = "adaivy.phase4d-public-discovery-config.v1"
REPORT_SCHEMA = "adaivy.phase4d-public-discovery-report.v1"
CONFIG_HASH = "sha256:64380e9f2d515d92b63d1b227063c2479ef55ab51f0de5b00f4a15e01b92abad"
CAPABILITY_ID = "capability.phase4d.public-scholarly-discovery"
LIVE_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_PUBLIC_WEB_DISCOVERY"
MAX_CONFIG_BYTES = 16_384
MAX_REPORT_BYTES = 1_048_576
MAX_SOURCE_BYTES = 65_536
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_TERM_TOKEN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_CANDIDATE_ID = re.compile(r"^discovery\.[0-9a-f]{24}$")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _json(data: bytes, maximum: int, label: str) -> Any:
    if not isinstance(data, bytes) or not data or len(data) > maximum:
        raise ValueError(f"{label} byte bound differs")
    try:
        return json.loads(
            data.decode("utf-8", "strict"), object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value forbidden: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} JSON is invalid") from error


def load_config(data: bytes) -> dict[str, Any]:
    value = _json(data, MAX_CONFIG_BYTES, "discovery config")
    if not isinstance(value, dict) or data not in {
        canonical_bytes(value), canonical_bytes(value) + b"\n",
    }:
        raise ValueError("discovery config is not canonical")
    fields = {
        "schema_version", "status", "provider", "origin", "path",
        "access_mode", "credentials_allowed", "max_results",
        "max_query_terms", "max_query_bytes", "max_response_bytes",
        "timeout_milliseconds", "terms_url", "terms_reviewed_at",
        "max_terms_age_seconds",
        "activated_by", "trust_effects", "content_hash",
    }
    if set(value) != fields or value.get("schema_version") != CONFIG_SCHEMA:
        raise ValueError("discovery config fields differ")
    supplied = value.get("content_hash")
    if supplied != CONFIG_HASH or _SHA256.fullmatch(str(supplied)) is None:
        raise ValueError("discovery config identity differs")
    if canonical_hash({key: item for key, item in value.items() if key != "content_hash"}) != supplied:
        raise ValueError("discovery config hash differs")
    expected = {
        "status": "active",
        "provider": "crossref",
        "origin": "https://api.crossref.org",
        "path": "/works",
        "access_mode": "public_unauthenticated",
        "credentials_allowed": False,
        "max_results": 10,
        "max_query_terms": 12,
        "max_query_bytes": 256,
        "max_response_bytes": 1_048_576,
        "timeout_milliseconds": 15_000,
        "max_terms_age_seconds": 2_592_000,
        "terms_url": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
        "terms_reviewed_at": "2026-08-21",
        "activated_by": {
            "actor_id": "human.repository-owner",
            "actor_kind": "human",
            "authority": "human_final",
        },
        "trust_effects": {
            "acquisition_authorized": False,
            "applicability": "not_assessed",
            "graph_admission": "not_admitted",
            "mathematical_warrant": "none",
            "novelty": "not_assessed",
            "significance": "not_assessed",
        },
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("discovery config policy differs")
    return value


def _normal_text(value: str, *, maximum: int, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} is not text")
    text = " ".join(unicodedata.normalize("NFKC", value).split())
    if not text or len(text.encode("utf-8")) > maximum or any(ord(c) < 32 for c in text):
        raise ValueError(f"{label} is invalid")
    return text


def _is_normal_text(value: object, maximum: int) -> bool:
    try:
        return isinstance(value, str) and value == _normal_text(
            value, maximum=maximum, label="text"
        )
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class GroundedQuery:
    terms: tuple[str, ...]
    source_sha256: str
    query_text: str
    query_hash: str

    @classmethod
    def create(
        cls, terms: Iterable[str], source_bytes: bytes, *,
        max_terms: int = 12, max_query_bytes: int = 256,
    ) -> "GroundedQuery":
        if not isinstance(source_bytes, bytes) or not 1 <= len(source_bytes) <= MAX_SOURCE_BYTES:
            raise ValueError("terminology source byte bound differs")
        try:
            source = unicodedata.normalize("NFKC", source_bytes.decode("utf-8", "strict"))
        except UnicodeDecodeError as error:
            raise ValueError("terminology source is not UTF-8") from error
        normalized_source = " ".join(source.casefold().split())
        normalized: list[str] = []
        for raw in terms:
            term = _normal_text(raw, maximum=80, label="search term")
            folded = term.casefold()
            if folded in normalized:
                raise ValueError("search terms must be unique")
            if not _TERM_TOKEN.search(term) or folded not in normalized_source:
                raise ValueError("search term is not grounded in the supplied source")
            normalized.append(folded)
        if not 1 <= len(normalized) <= max_terms:
            raise ValueError("search term count is out of bounds")
        query_text = " ".join(normalized)
        if len(query_text.encode("utf-8")) > max_query_bytes:
            raise ValueError("search query byte bound exceeded")
        source_hash = sha256_bytes(source_bytes)
        query_hash = canonical_hash({
            "terms": normalized, "source_sha256": source_hash,
            "grounding": "exact_nfkc_casefolded_substring_v1",
        })
        return cls(tuple(normalized), source_hash, query_text, query_hash)


def _validate_query(query: GroundedQuery) -> None:
    if not isinstance(query, GroundedQuery) or not 1 <= len(query.terms) <= 12:
        raise ValueError("grounded query shape differs")
    if any(
        term != _normal_text(term, maximum=80, label="search term").casefold()
        for term in query.terms
    ) or len(set(query.terms)) != len(query.terms):
        raise ValueError("grounded query terms differ")
    if query.query_text != " ".join(query.terms) or len(query.query_text.encode("utf-8")) > 256:
        raise ValueError("grounded query text differs")
    if (
        not isinstance(query.source_sha256, str)
        or not isinstance(query.query_hash, str)
        or _SHA256.fullmatch(query.source_sha256) is None
        or query.query_hash != canonical_hash({
        "terms": list(query.terms), "source_sha256": query.source_sha256,
        "grounding": "exact_nfkc_casefolded_substring_v1",
        })
    ):
        raise ValueError("grounded query identity differs")


def _public_addresses(resolution: Resolution, hostname: str) -> tuple[str, ...]:
    if resolution.hostname != hostname or not 1 <= len(resolution.addresses) <= 16:
        raise AcquisitionPolicyError("discovery_resolver_identity_invalid")
    result: list[str] = []
    for raw in resolution.addresses:
        try:
            address = ipaddress.ip_address(raw)
        except ValueError as error:
            raise AcquisitionPolicyError("discovery_resolved_address_invalid") from error
        if not address.is_global or address.is_multicast or address.is_unspecified:
            raise AcquisitionPolicyError("discovery_resolved_address_forbidden")
        if address.compressed not in result:
            result.append(address.compressed)
    if not result:
        raise AcquisitionPolicyError("discovery_resolved_address_empty")
    return tuple(sorted(result))


def request_url(config: dict[str, Any], query: GroundedQuery) -> str:
    _validate_query(query)
    return (
        str(config["origin"]) + str(config["path"])
        + "?query.bibliographic=" + quote_plus(query.query_text)
        + "&rows=" + str(config["max_results"])
    )


def _clean_optional(value: object, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return _normal_text(value, maximum=maximum, label="provider text")
    except ValueError:
        return None


def _candidates(
    body: bytes, *, max_response_bytes: int, max_results: int,
) -> tuple[list[dict[str, Any]], int]:
    root = _json(body, max_response_bytes, "Crossref response")
    if not isinstance(root, dict) or root.get("status") != "ok":
        raise ValueError("Crossref response envelope is invalid")
    message = root.get("message")
    items = message.get("items") if isinstance(message, dict) else None
    if not isinstance(items, list):
        raise ValueError("Crossref response items are invalid")
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    discarded = 0
    for item in items[:max_results]:
        if not isinstance(item, dict):
            discarded += 1
            continue
        doi = _clean_optional(item.get("DOI"), 256)
        titles = item.get("title")
        title = _clean_optional(titles[0], 1_024) if isinstance(titles, list) and titles else None
        if doi is None or title is None or _DOI.fullmatch(doi) is None:
            discarded += 1
            continue
        key = doi.casefold()
        if key in seen:
            discarded += 1
            continue
        seen.add(key)
        publisher = _clean_optional(item.get("publisher"), 512)
        work_type = _clean_optional(item.get("type"), 128)
        core = {
            "provider": "crossref", "provider_id": key, "title": title,
            "publisher": publisher, "work_type": work_type,
            "candidate_url": "https://doi.org/" + quote(key, safe="/"),
        }
        candidates.append({
            "candidate_id": "discovery." + canonical_hash(core).removeprefix("sha256:")[:24],
            "rank": len(candidates) + 1, **core,
            "status": "untrusted_inspiration_candidate",
            "relevance": "not_assessed", "applicability": "not_assessed",
            "acquisition_authorized": False, "mathematical_warrant": "none",
            "novelty": "not_assessed", "significance": "not_assessed",
        })
    return candidates, discarded


def _report(
    config: dict[str, Any], query: GroundedQuery, *, status: str,
    observed_at_epoch: int, network_requests: int, candidates: list[dict[str, Any]],
    discarded_items: int, response_sha256: str | None, failure_code: str | None,
    operator_id: str | None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "provider": config["provider"], "config_hash": config["content_hash"],
        "query": {"terms": list(query.terms), "source_sha256": query.source_sha256,
                  "query_hash": query.query_hash},
        "status": status, "observed_at_epoch": observed_at_epoch,
        "operator_id": operator_id,
        "network_requests": network_requests, "response_sha256": response_sha256,
        "candidate_count": len(candidates), "discarded_items": discarded_items,
        "candidates": candidates, "failure_code": failure_code,
        "trust_effects": config["trust_effects"],
        "inspiration_only": True,
    }
    value["content_hash"] = canonical_hash(value)
    return value


def dry_run(config: dict[str, Any], query: GroundedQuery, observed_at_epoch: int) -> dict[str, Any]:
    config = load_config(canonical_bytes(config))
    _validate_query(query)
    if isinstance(observed_at_epoch, bool) or not isinstance(observed_at_epoch, int) or observed_at_epoch < 0:
        raise ValueError("discovery observation time is invalid")
    return _report(
        config, query, status="not_executed", observed_at_epoch=observed_at_epoch,
        network_requests=0, candidates=[], discarded_items=0,
        response_sha256=None, failure_code=None, operator_id=None,
    )


def search(
    config: dict[str, Any], query: GroundedQuery, *, permit: LiveNetworkPermit,
    resolver: Any, transport: Any, observed_at_epoch: int,
    acknowledgement: str, confirmed_query_hash: str,
) -> dict[str, Any]:
    config = load_config(canonical_bytes(config))
    _validate_query(query)
    if isinstance(observed_at_epoch, bool) or not isinstance(observed_at_epoch, int):
        raise AcquisitionPolicyError("discovery_observation_time_invalid")
    if acknowledgement != LIVE_ACKNOWLEDGEMENT:
        raise AcquisitionPolicyError("discovery_acknowledgement_required")
    if confirmed_query_hash != query.query_hash:
        raise AcquisitionPolicyError("discovery_query_hash_confirmation_invalid")
    reviewed_at = int(datetime.strptime(
        config["terms_reviewed_at"], "%Y-%m-%d"
    ).replace(tzinfo=timezone.utc).timestamp())
    if not reviewed_at <= observed_at_epoch <= reviewed_at + config["max_terms_age_seconds"]:
        raise AcquisitionPolicyError("discovery_terms_review_stale_or_future")
    if (
        permit.capability_id != CAPABILITY_ID
        or permit.approved_origins != (config["origin"],)
        or resolver.permit != permit or transport.permit != permit
        or permit.actor_id != _normal_text(
            permit.actor_id, maximum=128, label="operator identity"
        )
    ):
        raise AcquisitionPolicyError("discovery_permit_invalid")
    hostname = "api.crossref.org"
    try:
        resolution = resolver.resolve(hostname)
        addresses = _public_addresses(resolution, hostname)
        response = transport.fetch(TransportRequest(
            "GET", request_url(config, query), (), addresses,
            config["timeout_milliseconds"], 65_536, config["max_response_bytes"],
        ))
        if response.status != 200:
            return _report(
                config, query, status="failed", observed_at_epoch=observed_at_epoch,
                network_requests=1, candidates=[], discarded_items=0,
                response_sha256=sha256_bytes(response.body),
                failure_code="http_status_not_ok", operator_id=permit.actor_id,
            )
        headers = {name.casefold(): value for name, value in response.headers}
        if headers.get("content-type", "").split(";", 1)[0].strip().casefold() != "application/json":
            raise ValueError("Crossref response media type is invalid")
        candidates, discarded = _candidates(
            response.body,
            max_response_bytes=config["max_response_bytes"],
            max_results=config["max_results"],
        )
        return _report(
            config, query, status="executed", observed_at_epoch=observed_at_epoch,
            network_requests=1, candidates=candidates, discarded_items=discarded,
            response_sha256=sha256_bytes(response.body), failure_code=None,
            operator_id=permit.actor_id,
        )
    except AcquisitionPolicyError:
        raise
    except TransportFailure as error:
        return _report(
            config, query, status="failed", observed_at_epoch=observed_at_epoch,
            network_requests=1, candidates=[], discarded_items=0,
            response_sha256=None,
            failure_code=str(error)[:128] or "transport_failure",
            operator_id=permit.actor_id,
        )
    except ValueError:
        return _report(
            config, query, status="failed", observed_at_epoch=observed_at_epoch,
            network_requests=1, candidates=[], discarded_items=0,
            response_sha256=None, failure_code="provider_response_invalid",
            operator_id=permit.actor_id,
        )


def verify_report(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA:
        raise ValueError("discovery report schema differs")
    supplied = report.get("content_hash")
    if _SHA256.fullmatch(str(supplied)) is None or canonical_hash(
        {key: value for key, value in report.items() if key != "content_hash"}
    ) != supplied:
        raise ValueError("discovery report hash differs")
    if report.get("status") not in {"not_executed", "executed", "failed"}:
        raise ValueError("discovery report status differs")
    expected_fields = {
        "schema_version", "provider", "config_hash", "query", "status",
        "observed_at_epoch", "operator_id", "network_requests", "response_sha256",
        "candidate_count", "discarded_items", "candidates", "failure_code",
        "trust_effects", "inspiration_only", "content_hash",
    }
    if set(report) != expected_fields or report.get("provider") != "crossref":
        raise ValueError("discovery report fields differ")
    if report.get("config_hash") != CONFIG_HASH:
        raise ValueError("discovery report config identity differs")
    query = report.get("query")
    if (
        not isinstance(query, dict)
        or set(query) != {"terms", "source_sha256", "query_hash"}
        or not isinstance(query.get("terms"), list)
        or not 1 <= len(query["terms"]) <= 12
        or not all(
            _is_normal_text(term, 80) and term == term.casefold()
            for term in query["terms"]
        )
        or len(set(query["terms"])) != len(query["terms"])
        or len(" ".join(query["terms"]).encode("utf-8")) > 256
        or _SHA256.fullmatch(str(query.get("source_sha256"))) is None
        or _SHA256.fullmatch(str(query.get("query_hash"))) is None
    ):
        raise ValueError("discovery report query differs")
    expected_query_hash = canonical_hash({
        "terms": query["terms"], "source_sha256": query["source_sha256"],
        "grounding": "exact_nfkc_casefolded_substring_v1",
    })
    if query["query_hash"] != expected_query_hash:
        raise ValueError("discovery report query identity differs")
    observed = report.get("observed_at_epoch")
    operator_id = report.get("operator_id")
    discarded = report.get("discarded_items")
    candidate_count = report.get("candidate_count")
    network_requests = report.get("network_requests")
    if (
        isinstance(observed, bool) or not isinstance(observed, int) or observed < 0
        or isinstance(discarded, bool) or not isinstance(discarded, int) or discarded < 0
        or isinstance(candidate_count, bool) or not isinstance(candidate_count, int)
        or isinstance(network_requests, bool) or not isinstance(network_requests, int)
    ):
        raise ValueError("discovery report scalar bounds differ")
    if report.get("inspiration_only") is not True or report.get("trust_effects") != {
        "acquisition_authorized": False, "applicability": "not_assessed",
        "graph_admission": "not_admitted", "mathematical_warrant": "none",
        "novelty": "not_assessed", "significance": "not_assessed",
    }:
        raise ValueError("discovery report attempts a trust promotion")
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or report.get("candidate_count") != len(candidates):
        raise ValueError("discovery candidate count differs")
    if len(candidates) > 10:
        raise ValueError("discovery candidate bound exceeded")
    for rank, item in enumerate(candidates, 1):
        expected_candidate_fields = {
            "candidate_id", "rank", "provider", "provider_id", "title",
            "publisher", "work_type", "candidate_url", "status", "relevance",
            "applicability", "acquisition_authorized", "mathematical_warrant",
            "novelty", "significance",
        }
        if (
            not isinstance(item, dict) or set(item) != expected_candidate_fields
            or item.get("rank") != rank
            or _CANDIDATE_ID.fullmatch(str(item.get("candidate_id"))) is None
            or item.get("provider") != "crossref"
            or _DOI.fullmatch(str(item.get("provider_id"))) is None
            or item.get("provider_id") != item["provider_id"].casefold()
            or item.get("candidate_url") != "https://doi.org/" + quote(item["provider_id"], safe="/")
            or not _is_normal_text(item.get("title"), 1_024)
            or item.get("publisher") is not None and not _is_normal_text(item["publisher"], 512)
            or item.get("work_type") is not None and not _is_normal_text(item["work_type"], 128)
            or item.get("status") != "untrusted_inspiration_candidate"
            or item.get("relevance") != "not_assessed"
            or item.get("applicability") != "not_assessed"
            or item.get("acquisition_authorized") is not False
            or item.get("mathematical_warrant") != "none"
            or item.get("novelty") != "not_assessed"
            or item.get("significance") != "not_assessed"
        ):
            raise ValueError("discovery candidate semantics differ")
        core = {
            key: item[key]
            for key in ("provider", "provider_id", "title", "publisher", "work_type", "candidate_url")
        }
        expected_id = "discovery." + canonical_hash(core).removeprefix("sha256:")[:24]
        if item["candidate_id"] != expected_id:
            raise ValueError("discovery candidate identity differs")
    response_hash = report.get("response_sha256")
    failure_code = report.get("failure_code")
    operator_valid = operator_id is not None and _is_normal_text(operator_id, 128)
    if report["status"] == "not_executed":
        valid_status = (
            network_requests == 0 and not candidates and discarded == 0
            and response_hash is None and failure_code is None and operator_id is None
        )
    elif report["status"] == "executed":
        valid_status = (
            network_requests == 1 and _SHA256.fullmatch(str(response_hash)) is not None
            and failure_code is None and operator_valid
        )
    else:
        valid_status = (
            network_requests == 1 and not candidates and discarded == 0
            and (response_hash is None or _SHA256.fullmatch(str(response_hash)) is not None)
            and _is_normal_text(failure_code, 128)
            and operator_valid
        )
    if not valid_status:
        raise ValueError("discovery report execution semantics differ")
    return report


__all__ = [
    "CAPABILITY_ID", "CONFIG_HASH", "CONFIG_SCHEMA", "GroundedQuery",
    "LIVE_ACKNOWLEDGEMENT", "MAX_CONFIG_BYTES", "MAX_REPORT_BYTES",
    "REPORT_SCHEMA", "dry_run", "load_config", "request_url", "search",
    "verify_report",
]
