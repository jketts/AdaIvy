"""The bounded, content-hashed first tranche and the only URLs it derives.

ADR-0067 accepts option C on two mandatory conditions, and this module is the
first: "A bounded first tranche.  The first ingestion processes a pinned,
content-hashed subset ... and its report is reviewed before the remainder is
touched."

A plan is a human artifact.  It names mathematics categories and a pinned
submission window, so a tranche is a reproducible SET rather than "whatever was
newest that day".  Everything else is derived:

* the request budget is ``ceil(max_records / page_size)`` and is never declared,
  so a plan cannot claim a budget its own bounds do not imply;
* every request URL is derived from the plan, so the set of URLs a run may
  request is fixed before the run starts.  There is no code path from a fetched
  response to a new URL, which is what "no crawling, no result following, no
  citation traversal" means operationally.

:func:`assert_metadata_target` is the single choke point every request URL
passes.  It admits exactly the pinned metadata query endpoint.
"""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote_plus, urlsplit

from . import PLAN_SCHEMA_VERSION
from .constants import (
    ARXIV_API_HOSTNAME, ARXIV_API_ORIGIN, ARXIV_API_QUERY_PATH,
    ARXIV_API_TERMS_URL, IDENTIFIER_PATTERN, MATHEMATICS_CATEGORY_SET,
    MAX_PLAN_BYTES, MAX_PLAN_CATEGORIES, MAX_RECORDS_PER_REQUEST,
    MAX_REQUESTS_PER_RUN, METADATA_LICENCE, PROVIDER, SORT_BY, SORT_ORDER,
    SUBMITTED_WINDOW_PATTERN, TIMESTAMP_PATTERN, TRANCHE_MAX_RECORDS,
)
from .errors import (
    CategoryNotMathematicsError, FullTextForbiddenError, OriginNotAuthorizedError,
    PlanHashMismatchError, PlanInvalidError, RequestBudgetExceededError,
    TrancheBoundExceededError,
)
from .serialization import strict_canonical_object, verify_sealed

PLAN_FIELDS = frozenset({
    "schema_version", "tranche_id", "provider", "categories", "submitted_from",
    "submitted_until", "max_records", "page_size", "rights_declaration",
    "content_hash",
})
_RIGHTS_DECLARATION_FIELDS = frozenset({
    "actor_id", "licence_basis", "terms_url", "terms_reviewed_at",
    "valid_from", "valid_until", "evidence_refs",
})

#: The permitted request prefix.  Composed from pinned constants so a typo
#: cannot silently point the slice somewhere else.
QUERY_URL_PREFIX = ARXIV_API_ORIGIN + ARXIV_API_QUERY_PATH + "?"


def assert_metadata_target(url: str) -> str:
    """Admit exactly the pinned arXiv metadata query endpoint.

    Every request in this slice passes here.  The check is positive: a URL is
    admitted because it IS the metadata endpoint, not because it failed to look
    like something forbidden.  A denylist of e-print paths would be a widening
    surface; an allowlist of one endpoint has nothing to widen.
    """

    if not isinstance(url, str) or not url or len(url) > 4_096:
        raise FullTextForbiddenError("a corpus request URL must be bounded text")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != ARXIV_API_HOSTNAME or parts.port is not None:
        raise OriginNotAuthorizedError(
            f"the only authorized corpus origin is {ARXIV_API_ORIGIN}; got {url!r}"
        )
    if parts.username is not None or parts.password is not None or parts.fragment:
        raise OriginNotAuthorizedError("a corpus request URL carries no credential or fragment")
    if parts.path != ARXIV_API_QUERY_PATH:
        raise FullTextForbiddenError(
            "only the arXiv metadata query path may be requested; ADR-0067 "
            f"excludes e-prints entirely, so {parts.path!r} is unreachable"
        )
    if not parts.query or not url.startswith(QUERY_URL_PREFIX):
        raise FullTextForbiddenError("a corpus request must be a metadata query")
    return url


def _text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise PlanInvalidError(f"{label} must be text of length 1..{maximum}")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise PlanInvalidError(f"{label} must be a lowercase identifier: {value!r}")
    return value


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise PlanInvalidError(f"{label} must be a canonical UTC timestamp: {value!r}")
    return value


def validate_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    """Exact-field-set validation plus every pinned tranche bound."""

    plan = verify_sealed(
        value, label="corpus tranche plan", code=PlanInvalidError.code,
    )
    if set(plan) != PLAN_FIELDS:
        raise PlanInvalidError(
            "corpus tranche plan fields differ: "
            f"missing={sorted(PLAN_FIELDS - set(plan))}, "
            f"extra={sorted(set(plan) - PLAN_FIELDS)}"
        )
    if plan["schema_version"] != PLAN_SCHEMA_VERSION:
        raise PlanInvalidError(f"unknown plan schema {plan['schema_version']!r}")
    if plan["provider"] != PROVIDER:
        raise PlanInvalidError(f"the only corpus provider is {PROVIDER}")
    _identifier(plan["tranche_id"], "tranche_id")

    categories = plan["categories"]
    if (
        not isinstance(categories, list) or not categories
        or len(categories) > MAX_PLAN_CATEGORIES
        or any(not isinstance(item, str) for item in categories)
        or categories != sorted(set(categories))
    ):
        raise PlanInvalidError(
            "categories must be a sorted, unique, nonempty list of category terms"
        )
    unknown = sorted(set(categories) - MATHEMATICS_CATEGORY_SET)
    if unknown:
        raise CategoryNotMathematicsError(
            f"the tranche is bounded to arXiv mathematics categories; got {unknown}"
        )

    for field in ("submitted_from", "submitted_until"):
        if (
            not isinstance(plan[field], str)
            or SUBMITTED_WINDOW_PATTERN.fullmatch(plan[field]) is None
        ):
            raise PlanInvalidError(f"{field} must be a YYYYMMDDHHMM window bound")
    if plan["submitted_from"] >= plan["submitted_until"]:
        raise PlanInvalidError("the submission window must be nonempty and ordered")

    for field in ("max_records", "page_size"):
        if isinstance(plan[field], bool) or not isinstance(plan[field], int) or plan[field] < 1:
            raise PlanInvalidError(f"{field} must be a positive integer")
    if plan["max_records"] > TRANCHE_MAX_RECORDS:
        raise TrancheBoundExceededError(
            f"the first tranche is pinned at {TRANCHE_MAX_RECORDS} records; the "
            f"plan asks for {plan['max_records']}. ADR-0067 requires the tranche "
            "report be reviewed before the remainder is touched"
        )
    if plan["page_size"] > MAX_RECORDS_PER_REQUEST:
        raise PlanInvalidError(
            f"page_size may not exceed {MAX_RECORDS_PER_REQUEST}"
        )

    declaration = plan["rights_declaration"]
    if not isinstance(declaration, dict) or set(declaration) != _RIGHTS_DECLARATION_FIELDS:
        raise PlanInvalidError(
            "rights_declaration fields differ: "
            f"missing={sorted(_RIGHTS_DECLARATION_FIELDS - set(declaration or {}))}, "
            f"extra={sorted(set(declaration or {}) - _RIGHTS_DECLARATION_FIELDS)}"
        )
    _identifier(declaration["actor_id"], "rights_declaration.actor_id")
    if declaration["licence_basis"] != METADATA_LICENCE:
        raise PlanInvalidError(
            f"the per-record rights basis is {METADATA_LICENCE}; a different "
            "basis is a different licence diligence and a different ADR"
        )
    if declaration["terms_url"] != ARXIV_API_TERMS_URL:
        raise PlanInvalidError("rights_declaration.terms_url is not the arXiv API terms")
    _text(declaration["terms_reviewed_at"], "rights_declaration.terms_reviewed_at", maximum=10)
    _timestamp(declaration["valid_from"], "rights_declaration.valid_from")
    if declaration["valid_until"] is not None:
        _timestamp(declaration["valid_until"], "rights_declaration.valid_until")
        if declaration["valid_until"] < declaration["valid_from"]:
            raise PlanInvalidError("rights_declaration.valid_until precedes valid_from")
    refs = declaration["evidence_refs"]
    if (
        not isinstance(refs, list) or not 1 <= len(refs) <= 8
        or refs != sorted(set(refs))
    ):
        raise PlanInvalidError(
            "rights_declaration.evidence_refs must be 1..8 sorted unique identifiers"
        )
    for ref in refs:
        _identifier(ref, "rights_declaration.evidence_refs[]")

    request_budget = -(-plan["max_records"] // plan["page_size"])
    if request_budget > MAX_REQUESTS_PER_RUN:
        raise RequestBudgetExceededError(
            f"the plan derives {request_budget} requests; the pinned budget is "
            f"{MAX_REQUESTS_PER_RUN}"
        )
    return plan


def load_plan(data: bytes) -> dict[str, Any]:
    return validate_plan(strict_canonical_object(
        data, maximum=MAX_PLAN_BYTES, label="corpus tranche plan",
        code=PlanInvalidError.code,
    ))


def require_plan_hash(plan: Mapping[str, Any], confirmed_hash: str) -> dict[str, Any]:
    validated = validate_plan(plan)
    if confirmed_hash != validated["content_hash"]:
        raise PlanHashMismatchError(
            "the confirmed plan hash differs from the plan; the operator must "
            "confirm the exact tranche being acquired"
        )
    return validated


def plan_hash(plan: Mapping[str, Any]) -> str:
    return str(validate_plan(plan)["content_hash"])


def request_budget(plan: Mapping[str, Any]) -> int:
    validated = validate_plan(plan)
    return -(-validated["max_records"] // validated["page_size"])


def search_query(plan: Mapping[str, Any]) -> str:
    """The pinned arXiv search expression this plan denotes."""

    validated = validate_plan(plan)
    categories = " OR ".join(f"cat:{item}" for item in validated["categories"])
    window = (
        f"submittedDate:[{validated['submitted_from']} TO "
        f"{validated['submitted_until']}]"
    )
    return f"({categories}) AND {window}"


def request_url(plan: Mapping[str, Any], page_index: int) -> str:
    """The one URL page ``page_index`` of this plan may request."""

    validated = validate_plan(plan)
    budget = -(-validated["max_records"] // validated["page_size"])
    if isinstance(page_index, bool) or not isinstance(page_index, int):
        raise PlanInvalidError("page index must be an integer")
    if not 0 <= page_index < budget:
        raise RequestBudgetExceededError(
            f"page {page_index} is outside this plan's {budget}-request budget"
        )
    start = page_index * validated["page_size"]
    remaining = validated["max_records"] - start
    size = min(validated["page_size"], remaining)
    url = (
        QUERY_URL_PREFIX
        + "search_query=" + quote_plus(search_query(validated))
        + "&start=" + str(start)
        + "&max_results=" + str(size)
        + "&sortBy=" + SORT_BY
        + "&sortOrder=" + SORT_ORDER
    )
    return assert_metadata_target(url)


def planned_request_urls(plan: Mapping[str, Any]) -> tuple[str, ...]:
    """The complete, fixed URL set for this plan. Nothing may be added to it."""

    return tuple(request_url(plan, index) for index in range(request_budget(plan)))


__all__ = [
    "PLAN_FIELDS",
    "QUERY_URL_PREFIX",
    "assert_metadata_target",
    "load_plan",
    "plan_hash",
    "planned_request_urls",
    "request_budget",
    "request_url",
    "require_plan_hash",
    "search_query",
    "validate_plan",
]
