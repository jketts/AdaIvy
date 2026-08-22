"""Strict, bounded parsing of one arXiv Atom metadata response.

Two things make this narrow on purpose.

**XML is an attack surface, so the markup is restricted before it is parsed.**
A byte-level pre-check refuses any DOCTYPE, entity declaration, comment, CDATA
section, extra processing instruction, or entity reference outside the five
predefined names and numeric character references.  Expansion attacks and
external-entity reads therefore cannot reach the parser at all, rather than
being mitigated inside it.

**Links in the feed are never read.**  The entry identifier is validated against
a pinned pattern and the arXiv identifier is extracted from it; the abstract
page URL is then COMPOSED from a pinned prefix.  No ``<link>`` element is
consulted, so there is no code path from a response to a new request target.
:func:`assert_no_foreign_urls` checks that as a property of the parsed payload.
"""

from __future__ import annotations

import re
from typing import Any, Mapping
from xml.etree import ElementTree

from .constants import (
    ARXIV_ABSTRACT_URL_PREFIX, ARXIV_ID_PATTERN, DOI_PATTERN, MAX_ABSTRACT_CHARS,
    MAX_AUTHOR_CHARS, MAX_AUTHORS_PER_ENTRY, MAX_CATEGORIES_PER_ENTRY,
    MAX_RECORDS_PER_REQUEST, MAX_RESPONSE_BYTES, MAX_TITLE_CHARS,
)
from .errors import (
    EntryIdNotCanonicalError, FeedBytesInvalidError, FeedLinkSurfacedError,
    FeedStructureInvalidError, XmlDeclarationForbiddenError,
)

ATOM_NS = "http://www.w3.org/2005/Atom"
ARXIV_NS = "http://arxiv.org/schemas/atom"
OPENSEARCH_NS = "http://a9.com/-/spec/opensearch/1.1/"

#: The declared transformation applied to every text field.  Named in the record
#: so a reader knows the stored text is not byte-identical to the response.
TEXT_NORMALIZATION = "whitespace_collapsed_v1"

_ENTRY_ID = re.compile(r"^https?://arxiv\.org/abs/(?P<identifier>[^\s?#]{1,64})$")
_CATEGORY_TERM = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,31}$")
_ATOM_TIMESTAMP = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:[0-2][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)
_ALLOWED_ENTITY = re.compile(r"^(?:amp|lt|gt|quot|apos|#[0-9]{1,7}|#x[0-9A-Fa-f]{1,6});")
_LEADING_DECLARATION = re.compile(rb"^<\?xml[^>]{0,128}\?>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

ENTRY_FIELDS = (
    "arxiv_id", "abstract_url", "title", "abstract", "authors",
    "primary_category", "categories", "doi", "published", "updated",
)


def assert_markup_restricted(data: bytes) -> bytes:
    """Refuse markup constructs the metadata profile does not need."""

    if not isinstance(data, bytes) or not data:
        raise FeedBytesInvalidError("an arXiv metadata response must be nonempty bytes")
    if len(data) > MAX_RESPONSE_BYTES:
        raise FeedBytesInvalidError(
            f"response exceeds the pinned {MAX_RESPONSE_BYTES}-byte bound"
        )
    body = _LEADING_DECLARATION.sub(b"", data, count=1)
    if b"<!" in body:
        raise XmlDeclarationForbiddenError(
            "no DOCTYPE, entity declaration, comment or CDATA section is "
            "admitted on the corpus parse path"
        )
    if b"<?" in body:
        raise XmlDeclarationForbiddenError(
            "no processing instruction beyond a leading XML declaration is admitted"
        )
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise FeedBytesInvalidError("an arXiv metadata response must be UTF-8") from error
    for index, character in enumerate(text):
        if character != "&":
            continue
        if _ALLOWED_ENTITY.match(text[index + 1: index + 12]) is None:
            raise XmlDeclarationForbiddenError(
                "only the five predefined entities and numeric character "
                "references are admitted on the corpus parse path"
            )
    return data


def _clean(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise FeedStructureInvalidError(f"{label} is absent")
    text = " ".join(value.split())
    if not text:
        raise FeedStructureInvalidError(f"{label} is empty")
    if _CONTROL.search(text) is not None:
        raise FeedStructureInvalidError(f"{label} contains control characters")
    if len(text) > maximum:
        raise FeedStructureInvalidError(f"{label} exceeds {maximum} characters")
    return text


def _child_text(element: Any, tag: str, label: str, *, maximum: int) -> str:
    found = element.find(tag)
    if found is None:
        raise FeedStructureInvalidError(f"{label} is absent")
    return _clean(found.text, label, maximum=maximum)


def _timestamp(value: str, label: str) -> str:
    if _ATOM_TIMESTAMP.fullmatch(value) is None:
        raise FeedStructureInvalidError(f"{label} is not a canonical UTC instant: {value!r}")
    return value


def abstract_url_for(arxiv_id: str) -> str:
    """Compose the abstract page URL from a pinned prefix, never from the feed."""

    if not isinstance(arxiv_id, str) or ARXIV_ID_PATTERN.fullmatch(arxiv_id) is None:
        raise EntryIdNotCanonicalError(f"not a canonical arXiv identifier: {arxiv_id!r}")
    return ARXIV_ABSTRACT_URL_PREFIX + arxiv_id


def _entry(element: Any) -> dict[str, Any]:
    raw_id = _child_text(element, f"{{{ATOM_NS}}}id", "entry id", maximum=256)
    matched = _ENTRY_ID.fullmatch(raw_id)
    if matched is None:
        raise EntryIdNotCanonicalError(
            f"an entry identifier must be an arXiv abstract identity: {raw_id!r}"
        )
    arxiv_id = matched.group("identifier")
    if ARXIV_ID_PATTERN.fullmatch(arxiv_id) is None:
        raise EntryIdNotCanonicalError(f"not a canonical arXiv identifier: {arxiv_id!r}")

    authors: list[str] = []
    for author in element.findall(f"{{{ATOM_NS}}}author"):
        authors.append(_child_text(
            author, f"{{{ATOM_NS}}}name", "author name", maximum=MAX_AUTHOR_CHARS,
        ))
    if not authors or len(authors) > MAX_AUTHORS_PER_ENTRY:
        raise FeedStructureInvalidError(
            f"entry {arxiv_id} names {len(authors)} authors; expected 1..{MAX_AUTHORS_PER_ENTRY}"
        )

    primary = element.find(f"{{{ARXIV_NS}}}primary_category")
    if primary is None:
        raise FeedStructureInvalidError(f"entry {arxiv_id} has no primary category")
    primary_term = _clean(primary.get("term"), "primary category term", maximum=32)
    categories: list[str] = [primary_term]
    for category in element.findall(f"{{{ATOM_NS}}}category"):
        term = _clean(category.get("term"), "category term", maximum=32)
        if term not in categories:
            categories.append(term)
    if len(categories) > MAX_CATEGORIES_PER_ENTRY:
        raise FeedStructureInvalidError(f"entry {arxiv_id} declares too many categories")
    for term in categories:
        if _CATEGORY_TERM.fullmatch(term) is None:
            raise FeedStructureInvalidError(f"category term is not a category: {term!r}")

    doi_element = element.find(f"{{{ARXIV_NS}}}doi")
    doi: str | None = None
    if doi_element is not None:
        doi = _clean(doi_element.text, "doi", maximum=256)
        if DOI_PATTERN.fullmatch(doi) is None:
            raise FeedStructureInvalidError(f"not a DOI: {doi!r}")

    payload = {
        "arxiv_id": arxiv_id,
        "abstract_url": abstract_url_for(arxiv_id),
        "title": _child_text(element, f"{{{ATOM_NS}}}title", "title", maximum=MAX_TITLE_CHARS),
        "abstract": _child_text(
            element, f"{{{ATOM_NS}}}summary", "abstract", maximum=MAX_ABSTRACT_CHARS,
        ),
        "authors": authors,
        "primary_category": primary_term,
        "categories": sorted(categories),
        "doi": doi,
        "published": _timestamp(
            _child_text(element, f"{{{ATOM_NS}}}published", "published", maximum=32),
            "published",
        ),
        "updated": _timestamp(
            _child_text(element, f"{{{ATOM_NS}}}updated", "updated", maximum=32),
            "updated",
        ),
    }
    assert_no_foreign_urls(payload)
    return payload


def assert_no_foreign_urls(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    """No URL in a parsed entry may come from the feed.

    The only admissible URL is the abstract page composed from the validated
    identifier.  A scheme appearing anywhere else means a feed link reached the
    payload, which is the first step of result following.
    """

    permitted = entry.get("abstract_url")

    def scan(value: Any, path: str) -> None:
        if isinstance(value, str):
            lowered = value.casefold()
            if ("://" in lowered or lowered.startswith("www.")) and value != permitted:
                raise FeedLinkSurfacedError(
                    f"{path} carries a URL taken from the feed: {value!r}"
                )
        elif isinstance(value, Mapping):
            for key, item in value.items():
                scan(item, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                scan(item, f"{path}[{index}]")

    for key, item in entry.items():
        if key == "abstract_url":
            continue
        scan(item, str(key))
    if not isinstance(permitted, str) or not permitted.startswith(ARXIV_ABSTRACT_URL_PREFIX):
        raise FeedLinkSurfacedError("the abstract URL is not the pinned composition")
    return entry


def parse_feed(data: bytes) -> dict[str, Any]:
    """Parse one bounded arXiv Atom response into declared metadata entries."""

    assert_markup_restricted(data)
    try:
        root = ElementTree.fromstring(data.decode("utf-8", "strict"))
    except ElementTree.ParseError as error:
        raise FeedStructureInvalidError(f"arXiv Atom response is not well formed: {error}") from error
    if root.tag != f"{{{ATOM_NS}}}feed":
        raise FeedStructureInvalidError(f"response root is {root.tag!r}, not an Atom feed")
    elements = root.findall(f"{{{ATOM_NS}}}entry")
    if len(elements) > MAX_RECORDS_PER_REQUEST:
        raise FeedStructureInvalidError(
            f"response carries {len(elements)} entries; the pinned page bound is "
            f"{MAX_RECORDS_PER_REQUEST}"
        )
    if len(elements) == 1:
        only = elements[0].find(f"{{{ATOM_NS}}}id")
        if only is not None and isinstance(only.text, str) and "/api/errors" in only.text:
            raise FeedStructureInvalidError(
                "arXiv returned an API error feed rather than metadata"
            )
    entries = [_entry(element) for element in elements]
    identifiers = [entry["arxiv_id"] for entry in entries]
    if len(set(identifiers)) != len(identifiers):
        raise FeedStructureInvalidError("response repeats an arXiv identifier")
    total = root.find(f"{{{OPENSEARCH_NS}}}totalResults")
    total_results: int | None = None
    if total is not None and isinstance(total.text, str) and total.text.strip().isdigit():
        total_results = int(total.text.strip())
    return {
        "entry_count": len(entries),
        "entries": entries,
        "provider_total_results": total_results,
        "text_normalization": TEXT_NORMALIZATION,
    }


__all__ = [
    "ARXIV_NS",
    "ATOM_NS",
    "ENTRY_FIELDS",
    "OPENSEARCH_NS",
    "TEXT_NORMALIZATION",
    "abstract_url_for",
    "assert_markup_restricted",
    "assert_no_foreign_urls",
    "parse_feed",
]
