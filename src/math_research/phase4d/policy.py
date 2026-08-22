"""Query-policy authorization for paginated discovery (ADR-0081).

One human-final authorization covers a content-hashed *policy* — grounding
sources, term-expansion rules, provider allowlist, and budget — instead of a
per-query acknowledgement. Every generated query is still refused unless each
term is an exact NFKC-casefolded substring of an authorized grounding source,
and every query record carries the grounding evidence (source and span).

Nothing here grants trust: a policy authorizes inspection-only discovery.
Acquisition authorization remains a separate rights-checked Phase 4A/4B step.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

from ..phase4b.serialization import canonical_hash, sha256_bytes
from .discovery import MAX_SOURCE_BYTES, _normal_text

POLICY_SCHEMA = "adaivy.phase4d-query-policy.v1"
AUTHORIZATION_SCHEMA = "adaivy.phase4d-query-policy-authorization.v1"
QUERY_SCHEMA = "adaivy.phase4d-grounded-query.v2"
GROUNDING_VERSION = "exact_nfkc_casefolded_substring_v1"
KNOWN_PROVIDERS = ("arxiv", "crossref", "openalex")
MAX_GROUNDING_SOURCES = 8
MAX_TERM_BYTES = 80

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_TERM_TOKEN = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


def _bounded_int(value: object, low: int, high: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{label} is out of bounds")
    return value


def normalized_source_text(source_bytes: bytes) -> str:
    """Project a grounding source onto its NFKC-casefolded search text."""

    if not isinstance(source_bytes, bytes) or not 1 <= len(source_bytes) <= MAX_SOURCE_BYTES:
        raise ValueError("grounding source byte bound differs")
    try:
        text = source_bytes.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise ValueError("grounding source is not UTF-8") from error
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def build_policy(
    *,
    grounding_sources: Mapping[str, bytes],
    provider_allowlist: Iterable[str],
    max_requests: int,
    max_response_bytes: int,
    max_candidates: int,
    max_queries: int,
    max_terms_per_query: int = 12,
    max_query_bytes: int = 256,
) -> dict[str, Any]:
    """Assemble the content-hashed query policy an operator authorizes once."""

    if not isinstance(grounding_sources, Mapping) or not (
        1 <= len(grounding_sources) <= MAX_GROUNDING_SOURCES
    ):
        raise ValueError("grounding source count is out of bounds")
    sources = []
    for source_id in sorted(grounding_sources):
        if _SOURCE_ID.fullmatch(str(source_id)) is None:
            raise ValueError("grounding source identifier is invalid")
        normalized = normalized_source_text(grounding_sources[source_id])
        if not normalized:
            raise ValueError("grounding source has no searchable text")
        sources.append({
            "source_id": source_id,
            "source_sha256": sha256_bytes(grounding_sources[source_id]),
        })
    providers = list(provider_allowlist)
    if (
        not 1 <= len(providers) <= len(KNOWN_PROVIDERS)
        or len(set(providers)) != len(providers)
        or any(name not in KNOWN_PROVIDERS for name in providers)
    ):
        raise ValueError("provider allowlist is invalid")
    value: dict[str, Any] = {
        "schema_version": POLICY_SCHEMA,
        "grounding_sources": sources,
        "term_rules": {
            "grounding": GROUNDING_VERSION,
            "max_terms_per_query": _bounded_int(max_terms_per_query, 1, 12, "max terms per query"),
            "max_term_bytes": MAX_TERM_BYTES,
            "max_query_bytes": _bounded_int(max_query_bytes, 16, 512, "max query bytes"),
        },
        "provider_allowlist": providers,
        "budget": {
            "max_requests": _bounded_int(max_requests, 1, 512, "budget max requests"),
            "max_response_bytes": _bounded_int(
                max_response_bytes, 1_024, 1_073_741_824, "budget max response bytes"
            ),
            "max_candidates": _bounded_int(max_candidates, 1, 10_000, "budget max candidates"),
        },
        "max_queries": _bounded_int(max_queries, 1, 64, "max queries"),
    }
    value["content_hash"] = canonical_hash(value)
    return value


def validate_policy(policy: Any) -> dict[str, Any]:
    expected = {
        "schema_version", "grounding_sources", "term_rules", "provider_allowlist",
        "budget", "max_queries", "content_hash",
    }
    if not isinstance(policy, dict) or set(policy) != expected:
        raise ValueError("query policy fields differ")
    if policy.get("schema_version") != POLICY_SCHEMA:
        raise ValueError("query policy schema differs")
    supplied = policy.get("content_hash")
    if _SHA256.fullmatch(str(supplied)) is None or canonical_hash(
        {key: value for key, value in policy.items() if key != "content_hash"}
    ) != supplied:
        raise ValueError("query policy identity differs")
    sources = policy.get("grounding_sources")
    if (
        not isinstance(sources, list)
        or not 1 <= len(sources) <= MAX_GROUNDING_SOURCES
        or any(
            not isinstance(item, dict)
            or set(item) != {"source_id", "source_sha256"}
            or _SOURCE_ID.fullmatch(str(item.get("source_id"))) is None
            or _SHA256.fullmatch(str(item.get("source_sha256"))) is None
            for item in sources
        )
        or len({item["source_id"] for item in sources}) != len(sources)
        or [item["source_id"] for item in sources] != sorted(item["source_id"] for item in sources)
    ):
        raise ValueError("query policy grounding sources differ")
    rules = policy.get("term_rules")
    if (
        not isinstance(rules, dict)
        or set(rules) != {"grounding", "max_terms_per_query", "max_term_bytes", "max_query_bytes"}
        or rules.get("grounding") != GROUNDING_VERSION
        or rules.get("max_term_bytes") != MAX_TERM_BYTES
    ):
        raise ValueError("query policy term rules differ")
    _bounded_int(rules.get("max_terms_per_query"), 1, 12, "max terms per query")
    _bounded_int(rules.get("max_query_bytes"), 16, 512, "max query bytes")
    providers = policy.get("provider_allowlist")
    if (
        not isinstance(providers, list)
        or not 1 <= len(providers) <= len(KNOWN_PROVIDERS)
        or len(set(providers)) != len(providers)
        or any(name not in KNOWN_PROVIDERS for name in providers)
    ):
        raise ValueError("query policy provider allowlist differs")
    budget = policy.get("budget")
    if not isinstance(budget, dict) or set(budget) != {
        "max_requests", "max_response_bytes", "max_candidates",
    }:
        raise ValueError("query policy budget differs")
    _bounded_int(budget.get("max_requests"), 1, 512, "budget max requests")
    _bounded_int(budget.get("max_response_bytes"), 1_024, 1_073_741_824, "budget max response bytes")
    _bounded_int(budget.get("max_candidates"), 1, 10_000, "budget max candidates")
    _bounded_int(policy.get("max_queries"), 1, 64, "max queries")
    return policy


def authorize_policy(
    policy: dict[str, Any], *, actor_id: str, authorized_at_epoch: int,
    capability_id: str,
) -> dict[str, Any]:
    """Record the single human-final authorization for one policy hash."""

    validate_policy(policy)
    if isinstance(authorized_at_epoch, bool) or not isinstance(authorized_at_epoch, int) \
            or authorized_at_epoch < 0:
        raise ValueError("policy authorization time is invalid")
    value: dict[str, Any] = {
        "schema_version": AUTHORIZATION_SCHEMA,
        "policy_hash": policy["content_hash"],
        "capability_id": capability_id,
        "authorized_by": {
            "actor_id": _normal_text(actor_id, maximum=128, label="operator identity"),
            "actor_kind": "human",
            "authority": "human_final",
        },
        "authorized_at_epoch": authorized_at_epoch,
        "trust_effects": "inspection_only",
    }
    value["content_hash"] = canonical_hash(value)
    return value


def validate_authorization(
    authorization: Any, policy: dict[str, Any], *, capability_id: str,
) -> dict[str, Any]:
    expected = {
        "schema_version", "policy_hash", "capability_id", "authorized_by",
        "authorized_at_epoch", "trust_effects", "content_hash",
    }
    if not isinstance(authorization, dict) or set(authorization) != expected:
        raise ValueError("policy authorization fields differ")
    if authorization.get("schema_version") != AUTHORIZATION_SCHEMA:
        raise ValueError("policy authorization schema differs")
    supplied = authorization.get("content_hash")
    if _SHA256.fullmatch(str(supplied)) is None or canonical_hash(
        {key: value for key, value in authorization.items() if key != "content_hash"}
    ) != supplied:
        raise ValueError("policy authorization identity differs")
    actor = authorization.get("authorized_by")
    if (
        authorization.get("policy_hash") != policy.get("content_hash")
        or authorization.get("capability_id") != capability_id
        or authorization.get("trust_effects") != "inspection_only"
        or not isinstance(actor, dict)
        or set(actor) != {"actor_id", "actor_kind", "authority"}
        or actor.get("actor_kind") != "human"
        or actor.get("authority") != "human_final"
        or actor.get("actor_id") != _normal_text(
            str(actor.get("actor_id")), maximum=128, label="operator identity"
        )
    ):
        raise ValueError("policy authorization scope differs")
    authorized_at = authorization.get("authorized_at_epoch")
    if isinstance(authorized_at, bool) or not isinstance(authorized_at, int) or authorized_at < 0:
        raise ValueError("policy authorization time is invalid")
    return authorization


def ground_query(
    policy: dict[str, Any],
    grounding_sources: Mapping[str, bytes],
    terms: Iterable[str],
) -> dict[str, Any]:
    """Build one ledgered query whose every term carries grounding evidence.

    Term expansion is free to propose candidates, but a term survives only as
    an exact NFKC-casefolded substring of an authorized grounding source. The
    recorded span makes the grounding independently checkable.
    """

    validate_policy(policy)
    declared = {item["source_id"]: item["source_sha256"] for item in policy["grounding_sources"]}
    if not isinstance(grounding_sources, Mapping) or set(grounding_sources) != set(declared):
        raise ValueError("grounding sources differ from the authorized policy")
    normalized_sources: dict[str, str] = {}
    for source_id, data in grounding_sources.items():
        if sha256_bytes(data) != declared[source_id]:
            raise ValueError("grounding source content differs from the authorized policy")
        normalized_sources[source_id] = normalized_source_text(data)
    rules = policy["term_rules"]
    folded_terms: list[str] = []
    grounding: list[dict[str, Any]] = []
    for raw in terms:
        term = _normal_text(raw, maximum=rules["max_term_bytes"], label="search term")
        folded = term.casefold()
        if folded in folded_terms:
            raise ValueError("search terms must be unique")
        if not _TERM_TOKEN.search(term):
            raise ValueError("search term has no searchable token")
        evidence = None
        for source_id in sorted(normalized_sources):
            start = normalized_sources[source_id].find(folded)
            if start >= 0:
                evidence = {
                    "term": folded,
                    "source_id": source_id,
                    "source_sha256": declared[source_id],
                    "span_start": start,
                    "span_end": start + len(folded),
                }
                break
        if evidence is None:
            raise ValueError("search term is not grounded in an authorized source")
        folded_terms.append(folded)
        grounding.append(evidence)
    if not 1 <= len(folded_terms) <= rules["max_terms_per_query"]:
        raise ValueError("search term count is out of bounds")
    query_text = " ".join(folded_terms)
    if len(query_text.encode("utf-8")) > rules["max_query_bytes"]:
        raise ValueError("search query byte bound exceeded")
    value: dict[str, Any] = {
        "schema_version": QUERY_SCHEMA,
        "terms": folded_terms,
        "query_text": query_text,
        "grounding": grounding,
        "grounding_version": GROUNDING_VERSION,
        "policy_hash": policy["content_hash"],
    }
    value["query_hash"] = canonical_hash(value)
    return value


def validate_query(query: Any, policy: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version", "terms", "query_text", "grounding",
        "grounding_version", "policy_hash", "query_hash",
    }
    if not isinstance(query, dict) or set(query) != expected:
        raise ValueError("grounded query fields differ")
    if query.get("schema_version") != QUERY_SCHEMA \
            or query.get("grounding_version") != GROUNDING_VERSION:
        raise ValueError("grounded query schema differs")
    supplied = query.get("query_hash")
    if _SHA256.fullmatch(str(supplied)) is None or canonical_hash(
        {key: value for key, value in query.items() if key != "query_hash"}
    ) != supplied:
        raise ValueError("grounded query identity differs")
    if query.get("policy_hash") != policy.get("content_hash"):
        raise ValueError("grounded query policy binding differs")
    rules = policy["term_rules"]
    terms = query.get("terms")
    grounding = query.get("grounding")
    declared = {item["source_id"]: item["source_sha256"] for item in policy["grounding_sources"]}
    if (
        not isinstance(terms, list) or not isinstance(grounding, list)
        or not 1 <= len(terms) <= rules["max_terms_per_query"]
        or len(grounding) != len(terms)
        or len(set(terms)) != len(terms)
        or query.get("query_text") != " ".join(str(term) for term in terms)
        or len(str(query["query_text"]).encode("utf-8")) > rules["max_query_bytes"]
    ):
        raise ValueError("grounded query terms differ")
    for term, evidence in zip(terms, grounding):
        if (
            not isinstance(evidence, dict)
            or set(evidence) != {"term", "source_id", "source_sha256", "span_start", "span_end"}
            or evidence.get("term") != term
            or not isinstance(term, str)
            or term != _normal_text(term, maximum=rules["max_term_bytes"], label="search term").casefold()
            or declared.get(evidence.get("source_id")) != evidence.get("source_sha256")
            or isinstance(evidence.get("span_start"), bool)
            or not isinstance(evidence.get("span_start"), int)
            or evidence["span_start"] < 0
            or evidence.get("span_end") != evidence["span_start"] + len(term)
        ):
            raise ValueError("grounded query grounding evidence differs")
    return query


__all__ = [
    "AUTHORIZATION_SCHEMA", "GROUNDING_VERSION", "KNOWN_PROVIDERS",
    "MAX_GROUNDING_SOURCES", "POLICY_SCHEMA", "QUERY_SCHEMA",
    "authorize_policy", "build_policy", "ground_query",
    "normalized_source_text", "validate_authorization", "validate_policy",
    "validate_query",
]
