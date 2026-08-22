"""Paginated, budgeted, policy-authorized discovery (ADR-0081).

One operator authorization covers a content-hashed query policy; the engine
then sweeps allowlisted providers with cursor/offset pagination under a hard
per-run budget in requests and response bytes. Every request — including the
refused over-budget one — is ledgered with provider, query hash, cursor, byte
count, and outcome. Results remain ``untrusted_inspiration_candidate`` with no
acquisition authorization and every assessment ``not_assessed``.

Timing observations (per-request waits honouring provider rate limits) are
operational, not semantic: they live under ``operational`` and are hashed into
``operational_hash``, never into ``content_hash`` (Phase 3B precedent).
"""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Iterable, Mapping

from ..phase4b.acquisition import (
    AcquisitionPolicyError, TransportFailure, TransportRequest,
)
from ..phase4b.serialization import canonical_bytes, canonical_hash, sha256_bytes
from .discovery import _is_normal_text, _json, _normal_text, _public_addresses
from .policy import (
    KNOWN_PROVIDERS, ground_query, validate_authorization, validate_policy,
    verify_query_grounding,
)
from .providers import (
    INITIAL_CURSOR, media_type_allowed, parse_page, request_url,
)

CONFIG_SCHEMA_V2 = "adaivy.phase4d-public-discovery-config.v2"
REPORT_SCHEMA_V2 = "adaivy.phase4d-public-discovery-report.v2"
OPERATIONAL_SCHEMA_V2 = "adaivy.phase4d-public-discovery-operational.v2"
CONFIG_HASH_V2 = "sha256:dd368a28da42b70e55adf0dd07a9b7af74cad823a683ca9193089e475be068c9"
CAPABILITY_ID_V2 = "capability.phase4d.public-scholarly-discovery.v2"
MAX_CONFIG_BYTES_V2 = 32_768
MAX_REPORT_BYTES_V2 = 8_388_608

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_CANDIDATE_ID = re.compile(r"^discovery\.[0-9a-f]{24}$")
_PROVIDER_HOSTS = {
    "crossref": "api.crossref.org",
    "arxiv": "export.arxiv.org",
    "openalex": "api.openalex.org",
}
_PROVIDER_INTERVALS = {"crossref": 1_000, "arxiv": 3_000, "openalex": 1_000}
_PINNED_PROVIDER_REQUESTS = {
    "arxiv": {
        "origin": "https://export.arxiv.org", "path": "/api/query", "page_size": 50,
    },
    "crossref": {
        "origin": "https://api.crossref.org", "path": "/works", "page_size": 50,
    },
    "openalex": {
        "origin": "https://api.openalex.org", "path": "/works", "page_size": 50,
    },
}
_TRUST_EFFECTS = {
    "acquisition_authorized": False,
    "applicability": "not_assessed",
    "graph_admission": "not_admitted",
    "mathematical_warrant": "none",
    "novelty": "not_assessed",
    "significance": "not_assessed",
}
_OUTCOMES = {
    "executed", "http_status_not_ok", "transport_failure",
    "provider_response_invalid", "refused_budget_exhausted",
}


def load_config_v2(data: bytes) -> dict[str, Any]:
    value = _json(data, MAX_CONFIG_BYTES_V2, "discovery v2 config")
    if not isinstance(value, dict) or data not in {
        canonical_bytes(value), canonical_bytes(value) + b"\n",
    }:
        raise ValueError("discovery v2 config is not canonical")
    fields = {
        "schema_version", "status", "access_mode", "credentials_allowed",
        "providers", "max_requests_per_run", "max_response_bytes_per_run",
        "max_response_bytes_per_request", "max_candidates_per_run",
        "max_queries_per_run", "max_pages_per_query", "timeout_milliseconds",
        "terms_reviewed_at", "max_terms_age_seconds", "terms_urls",
        "activated_by", "trust_effects", "content_hash",
    }
    if set(value) != fields or value.get("schema_version") != CONFIG_SCHEMA_V2:
        raise ValueError("discovery v2 config fields differ")
    supplied = value.get("content_hash")
    if supplied != CONFIG_HASH_V2 or _SHA256.fullmatch(str(supplied)) is None:
        raise ValueError("discovery v2 config identity differs")
    if canonical_hash(
        {key: item for key, item in value.items() if key != "content_hash"}
    ) != supplied:
        raise ValueError("discovery v2 config hash differs")
    expected = {
        "status": "active",
        "access_mode": "public_unauthenticated",
        "credentials_allowed": False,
        "max_requests_per_run": 64,
        "max_response_bytes_per_run": 33_554_432,
        "max_response_bytes_per_request": 2_097_152,
        "max_candidates_per_run": 1_000,
        "max_queries_per_run": 16,
        "max_pages_per_query": 8,
        "timeout_milliseconds": 15_000,
        "terms_reviewed_at": "2026-08-22",
        "max_terms_age_seconds": 2_592_000,
        "providers": {
            "arxiv": {
                "origin": "https://export.arxiv.org", "path": "/api/query",
                "pagination": "offset", "page_size": 50,
                "min_interval_milliseconds": 3_000,
            },
            "crossref": {
                "origin": "https://api.crossref.org", "path": "/works",
                "pagination": "cursor", "page_size": 50,
                "min_interval_milliseconds": 1_000,
            },
            "openalex": {
                "origin": "https://api.openalex.org", "path": "/works",
                "pagination": "cursor", "page_size": 50,
                "min_interval_milliseconds": 1_000,
            },
        },
        "terms_urls": {
            "arxiv": "https://info.arxiv.org/help/api/tou.html",
            "crossref": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
            "openalex": "https://openalex.org/terms",
        },
        "activated_by": {
            "actor_id": "human.repository-owner",
            "actor_kind": "human",
            "authority": "human_final",
        },
        "trust_effects": _TRUST_EFFECTS,
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("discovery v2 config policy differs")
    return value


def _candidate(core: Mapping[str, Any], rank: int) -> dict[str, Any]:
    core = dict(core)
    return {
        "candidate_id": "discovery." + canonical_hash(core).removeprefix("sha256:")[:24],
        "rank": rank, **core,
        "status": "untrusted_inspiration_candidate",
        "relevance": "not_assessed", "applicability": "not_assessed",
        "acquisition_authorized": False, "mathematical_warrant": "none",
        "novelty": "not_assessed", "significance": "not_assessed",
    }


def _finish(
    *, config: dict[str, Any], policy: dict[str, Any], authorization: dict[str, Any] | None,
    status: str, observed_at_epoch: int, operator_id: str | None,
    queries: list[dict[str, Any]], ledger: list[dict[str, Any]],
    candidates: list[dict[str, Any]], discarded: int,
    timings: list[dict[str, Any]],
) -> dict[str, Any]:
    executed = [entry for entry in ledger if entry["network"]]
    value: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_V2,
        "config_hash": config["content_hash"],
        "policy_hash": policy["content_hash"],
        "authorization_hash": None if authorization is None else authorization["content_hash"],
        "status": status,
        "observed_at_epoch": observed_at_epoch,
        "operator_id": operator_id,
        "budget": dict(policy["budget"]),
        "totals": {
            "requests": len(executed),
            "response_bytes": sum(entry["response_bytes"] for entry in executed),
            "candidates": len(candidates),
            "discarded_items": discarded,
        },
        "queries": queries,
        "request_ledger": ledger,
        "candidates": candidates,
        "trust_effects": _TRUST_EFFECTS,
        "inspiration_only": True,
    }
    value["content_hash"] = canonical_hash(value)
    operational = {
        "schema_version": OPERATIONAL_SCHEMA_V2,
        "timings": timings,
    }
    value["operational"] = operational
    value["operational_hash"] = canonical_hash(operational)
    return value


def dry_run_v2(
    config: dict[str, Any], policy: dict[str, Any],
    grounding_sources: Mapping[str, bytes], term_sets: Iterable[Iterable[str]],
    observed_at_epoch: int,
) -> dict[str, Any]:
    """Ground queries and account budgets with zero network effect."""

    config = load_config_v2(canonical_bytes(config))
    validate_policy(policy)
    _check_policy_within_config(config, policy)
    if isinstance(observed_at_epoch, bool) or not isinstance(observed_at_epoch, int) \
            or observed_at_epoch < 0:
        raise ValueError("discovery observation time is invalid")
    queries = _grounded_queries(config, policy, grounding_sources, term_sets)
    return _finish(
        config=config, policy=policy, authorization=None, status="not_executed",
        observed_at_epoch=observed_at_epoch, operator_id=None, queries=queries,
        ledger=[], candidates=[], discarded=0, timings=[],
    )


def _check_policy_within_config(config: dict[str, Any], policy: dict[str, Any]) -> None:
    budget = policy["budget"]
    if (
        budget["max_requests"] > config["max_requests_per_run"]
        or budget["max_response_bytes"] > config["max_response_bytes_per_run"]
        or budget["max_candidates"] > config["max_candidates_per_run"]
        or policy["max_queries"] > config["max_queries_per_run"]
        or policy["term_rules"]["max_query_bytes"] > 512
    ):
        raise ValueError("query policy exceeds the activated configuration ceiling")
    if any(name not in config["providers"] for name in policy["provider_allowlist"]):
        raise ValueError("query policy names an unactivated provider")


def _grounded_queries(
    config: dict[str, Any], policy: dict[str, Any],
    grounding_sources: Mapping[str, bytes], term_sets: Iterable[Iterable[str]],
) -> list[dict[str, Any]]:
    queries = [ground_query(policy, grounding_sources, terms) for terms in term_sets]
    if not 1 <= len(queries) <= policy["max_queries"]:
        raise ValueError("query count exceeds the authorized policy")
    if len({query["query_hash"] for query in queries}) != len(queries):
        raise ValueError("queries must be unique")
    return queries


def sweep(
    config: dict[str, Any], policy: dict[str, Any], authorization: dict[str, Any],
    grounding_sources: Mapping[str, bytes], term_sets: Iterable[Iterable[str]], *,
    permit: Any, resolver: Any, transport: Any, clock: Any, sleeper: Any,
    observed_at_epoch: int,
) -> dict[str, Any]:
    """Execute one budgeted multi-provider paginated discovery run."""

    config = load_config_v2(canonical_bytes(config))
    validate_policy(policy)
    validate_authorization(authorization, policy, capability_id=CAPABILITY_ID_V2)
    _check_policy_within_config(config, policy)
    if isinstance(observed_at_epoch, bool) or not isinstance(observed_at_epoch, int):
        raise AcquisitionPolicyError("discovery_observation_time_invalid")
    reviewed_at = int(datetime.strptime(
        config["terms_reviewed_at"], "%Y-%m-%d"
    ).replace(tzinfo=timezone.utc).timestamp())
    if not reviewed_at <= observed_at_epoch <= reviewed_at + config["max_terms_age_seconds"]:
        raise AcquisitionPolicyError("discovery_terms_review_stale_or_future")
    providers = list(policy["provider_allowlist"])
    expected_origins = tuple(sorted(
        config["providers"][name]["origin"] for name in providers
    ))
    if (
        permit.capability_id != CAPABILITY_ID_V2
        or tuple(sorted(permit.approved_origins)) != expected_origins
        or resolver.permit != permit or transport.permit != permit
        or permit.actor_id != _normal_text(
            permit.actor_id, maximum=128, label="operator identity"
        )
        or permit.actor_id != authorization["authorized_by"]["actor_id"]
    ):
        raise AcquisitionPolicyError("discovery_permit_invalid")
    queries = _grounded_queries(config, policy, grounding_sources, term_sets)

    budget = policy["budget"]
    ledger: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    discarded = 0
    requests_used = 0
    bytes_used = 0
    last_request_ms: dict[str, int] = {}
    addresses: dict[str, tuple[str, ...]] = {}
    budget_refused = False

    def over_budget() -> bool:
        return requests_used >= budget["max_requests"] or bytes_used >= budget["max_response_bytes"]

    for query in queries:
        if budget_refused or len(candidates) >= budget["max_candidates"]:
            break
        for name in providers:
            if budget_refused or len(candidates) >= budget["max_candidates"]:
                break
            base = config["providers"][name]
            cursor: str | None = INITIAL_CURSOR[name]
            for _page in range(config["max_pages_per_query"]):
                if cursor is None or len(candidates) >= budget["max_candidates"]:
                    break
                url = request_url(name, base, query["query_text"], cursor)
                if over_budget():
                    ledger.append({
                        "sequence": len(ledger) + 1, "provider": name,
                        "query_hash": query["query_hash"], "cursor": cursor,
                        "url": url, "network": False, "http_status": None,
                        "response_bytes": 0, "response_sha256": None,
                        "min_interval_milliseconds": base["min_interval_milliseconds"],
                        "outcome": "refused_budget_exhausted",
                    })
                    budget_refused = True
                    break
                hostname = _PROVIDER_HOSTS[name]
                if name not in addresses:
                    addresses[name] = _public_addresses(resolver.resolve(hostname), hostname)
                now = clock.now_milliseconds()
                waited = 0
                earliest = last_request_ms.get(name)
                if earliest is not None and now < earliest + base["min_interval_milliseconds"]:
                    waited = earliest + base["min_interval_milliseconds"] - now
                    sleeper.sleep_milliseconds(waited)
                    now = clock.now_milliseconds()
                last_request_ms[name] = now
                requests_used += 1
                entry = {
                    "sequence": len(ledger) + 1, "provider": name,
                    "query_hash": query["query_hash"], "cursor": cursor,
                    "url": url, "network": True, "http_status": None,
                    "response_bytes": 0, "response_sha256": None,
                    "min_interval_milliseconds": base["min_interval_milliseconds"],
                    "outcome": "transport_failure",
                }
                timings.append({
                    "sequence": entry["sequence"], "waited_milliseconds": waited,
                })
                next_cursor: str | None = None
                try:
                    remaining_bytes = budget["max_response_bytes"] - bytes_used
                    response_limit = min(
                        config["max_response_bytes_per_request"], remaining_bytes,
                    )
                    response = transport.fetch(TransportRequest(
                        "GET", url, (), addresses[name],
                        config["timeout_milliseconds"], 65_536,
                        response_limit,
                    ))
                    if len(response.body) > response_limit:
                        raise RuntimeError(
                            "discovery transport violated its response byte limit"
                        )
                    entry["http_status"] = response.status
                    entry["response_bytes"] = len(response.body)
                    entry["response_sha256"] = sha256_bytes(response.body)
                    bytes_used += len(response.body)
                    if response.status != 200:
                        entry["outcome"] = "http_status_not_ok"
                    else:
                        headers = {
                            key.casefold(): value for key, value in response.headers
                        }
                        if not media_type_allowed(name, headers.get("content-type", "")):
                            entry["outcome"] = "provider_response_invalid"
                        else:
                            page = parse_page(
                                name, response.body, cursor=cursor,
                                page_size=base["page_size"],
                                max_response_bytes=config["max_response_bytes_per_request"],
                            )
                            entry["outcome"] = "executed"
                            discarded += page.discarded
                            for core in page.cores:
                                key = (core["provider"], core["provider_id"])
                                if key in seen:
                                    discarded += 1
                                    continue
                                if len(candidates) >= budget["max_candidates"]:
                                    break
                                seen.add(key)
                                candidates.append(_candidate(core, len(candidates) + 1))
                            next_cursor = page.next_cursor
                except TransportFailure:
                    entry["outcome"] = "transport_failure"
                except ValueError:
                    entry["outcome"] = "provider_response_invalid"
                ledger.append(entry)
                if entry["outcome"] != "executed":
                    break
                cursor = next_cursor

    status = "budget_exhausted" if budget_refused else "executed"
    return _finish(
        config=config, policy=policy, authorization=authorization, status=status,
        observed_at_epoch=observed_at_epoch, operator_id=permit.actor_id,
        queries=queries, ledger=ledger, candidates=candidates,
        discarded=discarded, timings=timings,
    )


def _reject_floats(value: Any, path: str) -> None:
    if isinstance(value, float):
        raise ValueError(f"discovery v2 report contains a float at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


def verify_report_v2(
    report: dict[str, Any], policy: dict[str, Any],
    grounding_sources: Mapping[str, bytes],
) -> dict[str, Any]:
    """Recheck a v2 report without trusting the process that produced it."""

    if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA_V2:
        raise ValueError("discovery v2 report schema differs")
    if len(canonical_bytes(report)) > MAX_REPORT_BYTES_V2:
        raise ValueError("discovery v2 report byte bound differs")
    _reject_floats(report, "report")
    expected_fields = {
        "schema_version", "config_hash", "policy_hash", "authorization_hash",
        "status", "observed_at_epoch", "operator_id", "budget", "totals",
        "queries", "request_ledger", "candidates", "trust_effects",
        "inspiration_only", "content_hash", "operational", "operational_hash",
    }
    if set(report) != expected_fields:
        raise ValueError("discovery v2 report fields differ")
    supplied = report.get("content_hash")
    semantic = {
        key: value for key, value in report.items()
        if key not in {"content_hash", "operational", "operational_hash"}
    }
    if _SHA256.fullmatch(str(supplied)) is None or canonical_hash(semantic) != supplied:
        raise ValueError("discovery v2 report hash differs")
    operational = report.get("operational")
    if (
        not isinstance(operational, dict)
        or operational.get("schema_version") != OPERATIONAL_SCHEMA_V2
        or set(operational) != {"schema_version", "timings"}
        or canonical_hash(operational) != report.get("operational_hash")
    ):
        raise ValueError("discovery v2 report operational identity differs")
    if report.get("config_hash") != CONFIG_HASH_V2:
        raise ValueError("discovery v2 report config identity differs")
    validate_policy(policy)
    if report.get("policy_hash") != policy["content_hash"] \
            or report.get("budget") != policy["budget"]:
        raise ValueError("discovery v2 report policy binding differs")
    if report.get("status") not in {"not_executed", "executed", "budget_exhausted"}:
        raise ValueError("discovery v2 report status differs")
    observed = report.get("observed_at_epoch")
    if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
        raise ValueError("discovery v2 report observation time differs")
    if report.get("inspiration_only") is not True \
            or report.get("trust_effects") != _TRUST_EFFECTS:
        raise ValueError("discovery v2 report attempts a trust promotion")
    queries = report.get("queries")
    if not isinstance(queries, list) or not 1 <= len(queries) <= policy["max_queries"]:
        raise ValueError("discovery v2 report query count differs")
    query_hashes = set()
    query_text_by_hash: dict[str, str] = {}
    for query in queries:
        verify_query_grounding(query, policy, grounding_sources)
        query_hashes.add(query["query_hash"])
        query_text_by_hash[query["query_hash"]] = query["query_text"]
    if len(query_hashes) != len(queries):
        raise ValueError("discovery v2 report queries are not unique")
    ledger = report.get("request_ledger")
    if not isinstance(ledger, list):
        raise ValueError("discovery v2 report ledger differs")
    executed_requests = 0
    total_bytes = 0
    refused = 0
    for sequence, entry in enumerate(ledger, 1):
        expected_entry = {
            "sequence", "provider", "query_hash", "cursor", "url", "network",
            "http_status", "response_bytes", "response_sha256",
            "min_interval_milliseconds", "outcome",
        }
        if (
            not isinstance(entry, dict) or set(entry) != expected_entry
            or entry.get("sequence") != sequence
            or entry.get("provider") not in policy["provider_allowlist"]
            or entry.get("provider") not in KNOWN_PROVIDERS
            or entry.get("query_hash") not in query_hashes
            or entry.get("outcome") not in _OUTCOMES
            or entry.get("min_interval_milliseconds")
            != _PROVIDER_INTERVALS.get(entry.get("provider"))
            or not isinstance(entry.get("url"), str)
            or not isinstance(entry.get("cursor"), str)
        ):
            raise ValueError("discovery v2 request ledger entry differs")
        try:
            expected_url = request_url(
                entry["provider"], _PINNED_PROVIDER_REQUESTS[entry["provider"]],
                query_text_by_hash[entry["query_hash"]], entry["cursor"],
            )
        except (KeyError, ValueError) as error:
            raise ValueError("discovery v2 request ledger URL differs") from error
        if entry["url"] != expected_url:
            raise ValueError("discovery v2 request ledger URL differs")
        response_bytes = entry.get("response_bytes")
        if isinstance(response_bytes, bool) or not isinstance(response_bytes, int) \
                or response_bytes < 0:
            raise ValueError("discovery v2 ledger byte accounting differs")
        if entry["outcome"] == "refused_budget_exhausted":
            refused += 1
            if entry.get("network") is not False or response_bytes != 0 \
                    or entry.get("response_sha256") is not None \
                    or entry.get("http_status") is not None \
                    or not (
                        executed_requests >= policy["budget"]["max_requests"]
                        or total_bytes >= policy["budget"]["max_response_bytes"]
                    ):
                raise ValueError("discovery v2 refused entry claims network effect")
        else:
            if entry.get("network") is not True:
                raise ValueError("discovery v2 executed entry accounting differs")
            executed_requests += 1
            total_bytes += response_bytes
            if response_bytes > 2_097_152:
                raise ValueError("discovery v2 response exceeds per-request byte budget")
            digest = entry.get("response_sha256")
            if response_bytes > 0 and _SHA256.fullmatch(str(digest)) is None:
                raise ValueError("discovery v2 ledger response hash differs")
            if response_bytes == 0 and digest is not None:
                raise ValueError("discovery v2 empty response has a response hash")
            status_code = entry.get("http_status")
            if (
                entry["outcome"] == "transport_failure"
                and (status_code is not None or response_bytes != 0)
            ):
                raise ValueError("discovery v2 transport failure claims a response")
            if entry["outcome"] in {"executed", "provider_response_invalid"} \
                    and status_code != 200:
                raise ValueError("discovery v2 response outcome differs")
            if entry["outcome"] == "http_status_not_ok" \
                    and (isinstance(status_code, bool) or not isinstance(status_code, int)
                         or status_code == 200):
                raise ValueError("discovery v2 HTTP outcome differs")
    totals = report.get("totals")
    if (
        not isinstance(totals, dict)
        or set(totals) != {"requests", "response_bytes", "candidates", "discarded_items"}
        or totals.get("requests") != executed_requests
        or totals.get("response_bytes") != total_bytes
    ):
        raise ValueError("discovery v2 request accounting differs")
    if executed_requests > policy["budget"]["max_requests"]:
        raise ValueError("discovery v2 report exceeds the request budget")
    if total_bytes > policy["budget"]["max_response_bytes"]:
        raise ValueError("discovery v2 report exceeds the response byte budget")
    if report["status"] == "not_executed" and (ledger or executed_requests):
        raise ValueError("discovery v2 dry run claims network effect")
    if report["status"] == "budget_exhausted" and refused == 0:
        raise ValueError("discovery v2 exhaustion status lacks a refused entry")
    if report["status"] != "budget_exhausted" and refused != 0:
        raise ValueError("discovery v2 refused entry lacks exhaustion status")
    timings = operational["timings"]
    network_sequences = [entry["sequence"] for entry in ledger if entry["network"]]
    if not isinstance(timings, list) or len(timings) != len(network_sequences):
        raise ValueError("discovery v2 operational timings differ")
    for timing, expected_sequence in zip(timings, network_sequences):
        ledger_entry = ledger[expected_sequence - 1]
        if (
            not isinstance(timing, dict)
            or set(timing) != {"sequence", "waited_milliseconds"}
            or timing.get("sequence") != expected_sequence
            or isinstance(timing.get("waited_milliseconds"), bool)
            or not isinstance(timing.get("waited_milliseconds"), int)
            or timing["waited_milliseconds"] < 0
            or timing["waited_milliseconds"]
            > ledger_entry["min_interval_milliseconds"]
        ):
            raise ValueError("discovery v2 operational timing entry differs")
    operator_id = report.get("operator_id")
    if report["status"] == "not_executed":
        if operator_id is not None or report.get("authorization_hash") is not None:
            raise ValueError("discovery v2 dry run claims an authorization")
    else:
        if not _is_normal_text(operator_id, 128) \
                or _SHA256.fullmatch(str(report.get("authorization_hash"))) is None:
            raise ValueError("discovery v2 report authorization binding differs")
    candidates = report.get("candidates")
    if not isinstance(candidates, list) or totals.get("candidates") != len(candidates):
        raise ValueError("discovery v2 candidate count differs")
    if len(candidates) > policy["budget"]["max_candidates"]:
        raise ValueError("discovery v2 candidate bound exceeded")
    discarded = totals.get("discarded_items")
    if isinstance(discarded, bool) or not isinstance(discarded, int) or discarded < 0:
        raise ValueError("discovery v2 discard accounting differs")
    seen: set[tuple[str, str]] = set()
    expected_candidate_fields = {
        "candidate_id", "rank", "provider", "provider_id", "title",
        "publisher", "work_type", "candidate_url", "status", "relevance",
        "applicability", "acquisition_authorized", "mathematical_warrant",
        "novelty", "significance",
    }
    for rank, item in enumerate(candidates, 1):
        if (
            not isinstance(item, dict) or set(item) != expected_candidate_fields
            or item.get("rank") != rank
            or _CANDIDATE_ID.fullmatch(str(item.get("candidate_id"))) is None
            or item.get("provider") not in policy["provider_allowlist"]
            or not _is_normal_text(item.get("provider_id"), 256)
            or item.get("provider_id") != str(item["provider_id"]).casefold()
            or not _is_normal_text(item.get("title"), 1_024)
            or not _is_normal_text(item.get("candidate_url"), 512)
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
            raise ValueError("discovery v2 candidate semantics differ")
        key = (item["provider"], item["provider_id"])
        if key in seen:
            raise ValueError("discovery v2 candidates are not deduplicated")
        seen.add(key)
        core = {
            field: item[field]
            for field in (
                "provider", "provider_id", "title", "publisher", "work_type",
                "candidate_url",
            )
        }
        expected_id = "discovery." + canonical_hash(core).removeprefix("sha256:")[:24]
        if item["candidate_id"] != expected_id:
            raise ValueError("discovery v2 candidate identity differs")
    return report


__all__ = [
    "CAPABILITY_ID_V2", "CONFIG_HASH_V2", "CONFIG_SCHEMA_V2",
    "MAX_CONFIG_BYTES_V2", "MAX_REPORT_BYTES_V2", "OPERATIONAL_SCHEMA_V2",
    "REPORT_SCHEMA_V2", "dry_run_v2", "load_config_v2", "sweep",
    "verify_report_v2",
]
