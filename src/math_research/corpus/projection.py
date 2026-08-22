"""The reader-facing projection of corpus records, and its standing obligation.

The arXiv API Terms of Use require directing users to arXiv.org for e-print
content and linking to abstract pages.  ADR-0067 restates that as a standing
obligation on every projection.  It is encoded here as two checkable properties
rather than as guidance:

* **Every surfaced entry links out.**  :func:`verify_projection` refuses an
  entry whose ``abstract_url`` is absent, null, or anything other than the
  pinned composition over the validated arXiv identifier.  A projection that
  loses the link cannot be produced or verified.
* **Nothing is reproduced beyond fair quotation.**  Title and abstract are
  QUOTED to pinned character bounds and marked truncated when they are cut.
  An entry whose quotation exceeds the bound, or whose quotation is not the
  bounded prefix of the record's own text, is refused.

A projection also restates that this corpus is not wired into retrieval.  A
projection claiming otherwise is refused, so corpus size can never be presented
as retrieval quality.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import PROJECTION_SCHEMA_VERSION
from .constants import (
    APPLICABILITY_CEILING, ARXIV_ABSTRACT_URL_PREFIX, ARXIV_ID_PATTERN,
    MAX_QUOTED_ABSTRACT_CHARS, MAX_QUOTED_TITLE_CHARS, PROVIDER,
    QUOTATION_ELLIPSIS, TRUST_EFFECTS,
)
from .errors import (
    AbstractLinkMissingError, ProjectionInvalidError, QuotationBoundExceededError,
    RetrievalScopeClaimForbiddenError,
)
from .records import verify_record
from .serialization import sealed, verify_sealed

QUOTATION_POLICY = {
    "policy_version": "corpus-fair-quotation-v1",
    "max_title_characters": MAX_QUOTED_TITLE_CHARS,
    "max_abstract_characters": MAX_QUOTED_ABSTRACT_CHARS,
    "full_text_reproduced": False,
    "link_out_required": True,
}

PROJECTION_FIELDS = frozenset({
    "schema_version", "provider", "entry_count", "entries", "quotation_policy",
    "retrieval_corpus_wired", "applicability_ceiling", "trust_effects",
    "link_out_statement", "content_hash",
})
ENTRY_FIELDS = frozenset({
    "record_id", "arxiv_id", "abstract_url", "title_quotation", "title_truncated",
    "abstract_quotation", "abstract_truncated", "primary_category", "published",
})

LINK_OUT_STATEMENT = (
    "Every record links to its arXiv abstract page. Title and abstract text are "
    "quoted within a pinned bound and never reproduced in full; retrieve the "
    "e-print from arXiv.org."
)


def quote_text(text: str, maximum: int) -> tuple[str, bool]:
    """Bounded quotation. Returns the quotation and whether it was truncated."""

    if not isinstance(text, str) or not text:
        raise ProjectionInvalidError("quotable text must be nonempty")
    if maximum < 2:
        raise ProjectionInvalidError("a quotation bound must admit an ellipsis")
    if len(text) <= maximum:
        return text, False
    return text[: maximum - 1] + QUOTATION_ELLIPSIS, True


def project_record(record: Mapping[str, Any]) -> dict[str, Any]:
    validated = verify_record(record)
    title, title_truncated = quote_text(validated["title"], MAX_QUOTED_TITLE_CHARS)
    abstract, abstract_truncated = quote_text(
        validated["abstract"], MAX_QUOTED_ABSTRACT_CHARS,
    )
    return {
        "record_id": validated["record_id"],
        "arxiv_id": validated["arxiv_id"],
        "abstract_url": validated["abstract_url"],
        "title_quotation": title,
        "title_truncated": title_truncated,
        "abstract_quotation": abstract,
        "abstract_truncated": abstract_truncated,
        "primary_category": validated["primary_category"],
        "published": validated["published"],
    }


def build_projection(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    entries = [project_record(record) for record in records]
    entries.sort(key=lambda entry: entry["record_id"])
    return sealed({
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "provider": PROVIDER,
        "entry_count": len(entries),
        "entries": entries,
        "quotation_policy": dict(QUOTATION_POLICY),
        "retrieval_corpus_wired": False,
        "applicability_ceiling": APPLICABILITY_CEILING,
        "trust_effects": dict(TRUST_EFFECTS),
        "link_out_statement": LINK_OUT_STATEMENT,
        "content_hash": None,
    })


def verify_projection(
    value: Mapping[str, Any], *, records: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Refuse a projection that drops a link, over-quotes, or claims retrieval."""

    if not isinstance(value, Mapping):
        raise ProjectionInvalidError("a corpus projection must be an object")
    projection = dict(value)
    if set(projection) != PROJECTION_FIELDS:
        raise ProjectionInvalidError(
            "corpus projection fields differ: "
            f"missing={sorted(PROJECTION_FIELDS - set(projection))}, "
            f"extra={sorted(set(projection) - PROJECTION_FIELDS)}"
        )
    if projection["retrieval_corpus_wired"] is not False:
        raise RetrievalScopeClaimForbiddenError(
            "a corpus projection may not claim the corpus is wired into "
            "retrieval; Phase 4C still reads its own frozen fixture"
        )
    if projection["quotation_policy"] != QUOTATION_POLICY:
        raise QuotationBoundExceededError(
            "the fair-quotation policy is pinned and may not be restated"
        )
    if projection["link_out_statement"] != LINK_OUT_STATEMENT:
        raise AbstractLinkMissingError(
            "a corpus projection must carry the link-out statement verbatim"
        )
    if (
        projection["schema_version"] != PROJECTION_SCHEMA_VERSION
        or projection["provider"] != PROVIDER
        or projection["applicability_ceiling"] != APPLICABILITY_CEILING
        or projection["trust_effects"] != TRUST_EFFECTS
    ):
        raise ProjectionInvalidError("corpus projection header differs")
    entries = projection["entries"]
    if not isinstance(entries, list) or projection["entry_count"] != len(entries):
        raise ProjectionInvalidError("corpus projection entry count differs")
    by_record = {
        str(item["record_id"]): item for item in (records or ())
    }
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != ENTRY_FIELDS:
            raise ProjectionInvalidError(f"projection entry {index} fields differ")
        identifier = entry["arxiv_id"]
        if not isinstance(identifier, str) or ARXIV_ID_PATTERN.fullmatch(identifier) is None:
            raise ProjectionInvalidError(f"projection entry {index} identifier differs")
        link = entry["abstract_url"]
        if not isinstance(link, str) or link != ARXIV_ABSTRACT_URL_PREFIX + identifier:
            raise AbstractLinkMissingError(
                f"projection entry {index} ({identifier}) does not link to its "
                "arXiv abstract page; the arXiv terms require linking out"
            )
        for field, bound, flag in (
            ("title_quotation", MAX_QUOTED_TITLE_CHARS, "title_truncated"),
            ("abstract_quotation", MAX_QUOTED_ABSTRACT_CHARS, "abstract_truncated"),
        ):
            quotation = entry[field]
            if not isinstance(quotation, str) or not quotation:
                raise ProjectionInvalidError(f"projection entry {index} {field} differs")
            if len(quotation) > bound:
                raise QuotationBoundExceededError(
                    f"projection entry {index} {field} reproduces "
                    f"{len(quotation)} characters; fair quotation is bounded at "
                    f"{bound}"
                )
            if not isinstance(entry[flag], bool):
                raise ProjectionInvalidError(f"projection entry {index} {flag} differs")
        if entry["record_id"] in seen:
            raise ProjectionInvalidError("corpus projection repeats a record")
        seen.add(str(entry["record_id"]))
        source = by_record.get(str(entry["record_id"]))
        if source is not None:
            expected = project_record(source)
            if entry != expected:
                raise QuotationBoundExceededError(
                    f"projection entry {index} is not the bounded quotation of "
                    "its own record"
                )
    verify_sealed(
        projection, label="corpus projection", code=ProjectionInvalidError.code,
    )
    return projection


__all__ = [
    "ENTRY_FIELDS",
    "LINK_OUT_STATEMENT",
    "PROJECTION_FIELDS",
    "QUOTATION_POLICY",
    "build_projection",
    "project_record",
    "quote_text",
    "verify_projection",
]
