"""Credential-free provider adapters for paginated discovery (ADR-0081).

Each adapter turns a grounded query and a cursor into exactly one request URL
and parses one untrusted response page into normalized candidate cores. Only
identifier, title, publisher, and work type survive the provider boundary; the
raw body is hashed by the engine but never persisted in the report.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from urllib.parse import quote, quote_plus
from xml.etree import ElementTree

_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_ARXIV_ABS = re.compile(r"^https?://arxiv\.org/abs/([A-Za-z0-9._/-]+?)(v\d+)?$")
_ARXIV_ID = re.compile(r"^[a-z0-9._/-]+$")
_OPENALEX_WORK = re.compile(r"^https?://openalex\.org/([Ww]\d{4,})$")
_CURSOR = re.compile(r"^[\x21-\x7e]{1,512}$")
_ATOM = "{http://www.w3.org/2005/Atom}"
INITIAL_CURSOR = {"crossref": "*", "openalex": "*", "arxiv": "0"}
MEDIA_TYPES = {
    "crossref": frozenset({"application/json"}),
    "openalex": frozenset({"application/json"}),
    "arxiv": frozenset({"application/atom+xml", "application/xml", "text/xml"}),
}


@dataclass(frozen=True, slots=True)
class ProviderPage:
    """One parsed untrusted response page."""

    cores: tuple[dict[str, Any], ...]
    next_cursor: str | None
    discarded: int
    raw_items: int


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _json(body: bytes, maximum: int) -> Any:
    if not isinstance(body, bytes) or not body or len(body) > maximum:
        raise ValueError("provider response byte bound differs")
    try:
        return json.loads(
            body.decode("utf-8", "strict"), object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON value forbidden: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("provider response JSON is invalid") from error


def _clean(value: object, maximum: int) -> str | None:
    import unicodedata

    if not isinstance(value, str):
        return None
    text = " ".join(unicodedata.normalize("NFKC", value).split())
    if not text or len(text.encode("utf-8")) > maximum or any(ord(c) < 32 for c in text):
        return None
    return text


def _validate_cursor(cursor: str) -> str:
    if not isinstance(cursor, str) or _CURSOR.fullmatch(cursor) is None:
        raise ValueError("provider cursor is invalid")
    return cursor


def request_url(
    provider: str, base: dict[str, Any], query_text: str, cursor: str,
) -> str:
    """Build the single request this page is allowed to make."""

    _validate_cursor(cursor)
    origin = str(base["origin"])
    path = str(base["path"])
    page_size = int(base["page_size"])
    if provider == "crossref":
        return (
            origin + path
            + "?query.bibliographic=" + quote_plus(query_text)
            + "&rows=" + str(page_size)
            + "&cursor=" + quote_plus(cursor)
        )
    if provider == "openalex":
        return (
            origin + path
            + "?search=" + quote_plus(query_text)
            + "&per-page=" + str(page_size)
            + "&cursor=" + quote_plus(cursor)
        )
    if provider == "arxiv":
        offset = int(cursor)
        if str(offset) != cursor or offset < 0:
            raise ValueError("arXiv cursor is not a nonnegative offset")
        return (
            origin + path
            + "?search_query=all:" + quote_plus('"' + query_text + '"')
            + "&start=" + str(offset)
            + "&max_results=" + str(page_size)
        )
    raise ValueError("unknown discovery provider")


def _crossref_page(body: bytes, page_size: int, maximum: int) -> ProviderPage:
    root = _json(body, maximum)
    if not isinstance(root, dict) or root.get("status") != "ok":
        raise ValueError("Crossref response envelope is invalid")
    message = root.get("message")
    items = message.get("items") if isinstance(message, dict) else None
    if not isinstance(items, list):
        raise ValueError("Crossref response items are invalid")
    cores: list[dict[str, Any]] = []
    discarded = 0
    for item in items[:page_size]:
        if not isinstance(item, dict):
            discarded += 1
            continue
        doi = _clean(item.get("DOI"), 256)
        titles = item.get("title")
        title = _clean(titles[0], 1_024) if isinstance(titles, list) and titles else None
        if doi is None or title is None or _DOI.fullmatch(doi) is None:
            discarded += 1
            continue
        key = doi.casefold()
        cores.append({
            "provider": "crossref", "provider_id": key, "title": title,
            "publisher": _clean(item.get("publisher"), 512),
            "work_type": _clean(item.get("type"), 128),
            "candidate_url": "https://doi.org/" + quote(key, safe="/"),
        })
    raw_next = message.get("next-cursor") if isinstance(message, dict) else None
    next_cursor = None
    if isinstance(raw_next, str) and raw_next and len(items) >= page_size:
        next_cursor = _validate_cursor(raw_next)
    return ProviderPage(tuple(cores), next_cursor, discarded, len(items))


def _openalex_page(body: bytes, page_size: int, maximum: int) -> ProviderPage:
    root = _json(body, maximum)
    if not isinstance(root, dict) or not isinstance(root.get("results"), list):
        raise ValueError("OpenAlex response envelope is invalid")
    items = root["results"]
    cores: list[dict[str, Any]] = []
    discarded = 0
    for item in items[:page_size]:
        if not isinstance(item, dict):
            discarded += 1
            continue
        identity = _clean(item.get("id"), 256)
        title = _clean(item.get("display_name"), 1_024) or _clean(item.get("title"), 1_024)
        match = _OPENALEX_WORK.fullmatch(identity) if identity else None
        if match is None or title is None:
            discarded += 1
            continue
        work_id = match.group(1).upper()
        cores.append({
            "provider": "openalex", "provider_id": work_id.casefold(),
            "title": title,
            "publisher": _clean(item.get("host_venue_name"), 512),
            "work_type": _clean(item.get("type"), 128),
            "candidate_url": "https://openalex.org/" + work_id,
        })
    meta = root.get("meta")
    raw_next = meta.get("next_cursor") if isinstance(meta, dict) else None
    next_cursor = None
    if isinstance(raw_next, str) and raw_next and len(items) >= page_size:
        next_cursor = _validate_cursor(raw_next)
    return ProviderPage(tuple(cores), next_cursor, discarded, len(items))


def _arxiv_page(body: bytes, cursor: str, page_size: int, maximum: int) -> ProviderPage:
    if not isinstance(body, bytes) or not body or len(body) > maximum:
        raise ValueError("provider response byte bound differs")
    # Scan the complete bounded body before invoking ElementTree. Internal
    # declarations can otherwise hide beyond an arbitrary prefix and expand
    # while the parser constructs the tree.
    if re.search(br"<!\s*(?:doctype|entity)\b", body, re.IGNORECASE):
        raise ValueError("arXiv response declares forbidden markup")
    try:
        root = ElementTree.fromstring(body.decode("utf-8", "strict"))
    except (UnicodeDecodeError, ElementTree.ParseError) as error:
        raise ValueError("arXiv response Atom XML is invalid") from error
    if root.tag != _ATOM + "feed":
        raise ValueError("arXiv response is not an Atom feed")
    entries = root.findall(_ATOM + "entry")
    cores: list[dict[str, Any]] = []
    discarded = 0
    for entry in entries[:page_size]:
        identity = _clean(getattr(entry.find(_ATOM + "id"), "text", None), 256)
        title = _clean(getattr(entry.find(_ATOM + "title"), "text", None), 1_024)
        match = _ARXIV_ABS.fullmatch(identity) if identity else None
        arxiv_id = match.group(1).casefold() + (match.group(2) or "") if match else None
        if arxiv_id is None or title is None or _ARXIV_ID.fullmatch(match.group(1).casefold()) is None:
            discarded += 1
            continue
        cores.append({
            "provider": "arxiv", "provider_id": arxiv_id,
            "title": title, "publisher": None, "work_type": "preprint",
            "candidate_url": "https://arxiv.org/abs/" + quote(arxiv_id, safe="/."),
        })
    next_cursor = None
    if len(entries) >= page_size:
        next_cursor = str(int(cursor) + len(entries))
    return ProviderPage(tuple(cores), next_cursor, discarded, len(entries))


def parse_page(
    provider: str, body: bytes, *, cursor: str, page_size: int, max_response_bytes: int,
) -> ProviderPage:
    """Parse one page or raise ``ValueError`` for any malformed response."""

    if provider == "crossref":
        return _crossref_page(body, page_size, max_response_bytes)
    if provider == "openalex":
        return _openalex_page(body, page_size, max_response_bytes)
    if provider == "arxiv":
        return _arxiv_page(body, cursor, page_size, max_response_bytes)
    raise ValueError("unknown discovery provider")


def media_type_allowed(provider: str, content_type: str) -> bool:
    allowed = MEDIA_TYPES.get(provider)
    if allowed is None:
        raise ValueError("unknown discovery provider")
    return content_type.split(";", 1)[0].strip().casefold() in allowed


__all__ = [
    "INITIAL_CURSOR", "MEDIA_TYPES", "ProviderPage", "media_type_allowed",
    "parse_page", "request_url",
]
