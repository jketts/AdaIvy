"""The corpus record: descriptive metadata, an abstract, and no trust at all.

A corpus record is an ``untrusted_inspiration_candidate``.  It creates no
applicability, no premise, no epistemic warrant, no graph admission, and no
novelty or significance assessment, and it is not indexed for retrieval.  Those
are not comments here: :func:`verify_record` refuses a record that claims any of
them, with a distinct refusal code per claim so the probe suite can tell which
promotion was attempted.

``source_id`` is the Phase 4A subject identifier for the same document.  Phase
4A identifiers are lowercase ``[a-z][a-z0-9_.-]+``, and arXiv identifiers start
with a digit and may contain ``/``, so the mapping is explicit and injective:
``/`` becomes ``--`` and the whole thing is prefixed.  A record is refused if
its ``source_id`` is not exactly that composition.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import SCHEMA_VERSION
from .atom import TEXT_NORMALIZATION, abstract_url_for
from .constants import (
    ARXIV_ABSTRACT_URL_PREFIX, ARXIV_ID_PATTERN, CANDIDATE_STATUS, CORPUS_SCOPE,
    DOI_PATTERN, HASH_PATTERN, IDENTIFIER_PATTERN, MAX_ABSTRACT_CHARS,
    MAX_AUTHORS_PER_ENTRY, MAX_AUTHOR_CHARS, MAX_CATEGORIES_PER_ENTRY,
    MAX_TITLE_CHARS, METADATA_LICENCE, METADATA_LICENCE_URL, PROVIDER,
    TRUST_EFFECTS,
)
from .errors import (
    AbstractLinkMissingError, ApplicabilityPromotionForbiddenError,
    EntryIdNotCanonicalError, RecordInvalidError, RetrievalScopeClaimForbiddenError,
    WarrantPromotionForbiddenError,
)
from .serialization import canonical_hash, content_hash_of, public_value

RECORD_FIELDS = frozenset({
    "schema_version", "record_id", "provider", "arxiv_id", "source_id",
    "abstract_url", "title", "abstract", "authors", "primary_category",
    "categories", "doi", "published", "updated", "text_normalization",
    "metadata_licence", "metadata_licence_url", "response_sha256", "tranche_id",
    "plan_hash", "scope", "rights_decision_ids", "rights_uses", "status",
    "trust_effects", "retrieval_indexed", "content_hash",
})

#: The three non-disclosing Phase 4A uses this slice records per document.
RIGHTS_USES = ("acquisition", "storage_and_retention", "parsing")

SOURCE_ID_PREFIX = "arxiv."


def source_id_for(arxiv_id: str) -> str:
    """The Phase 4A subject identifier for one arXiv record."""

    if not isinstance(arxiv_id, str) or ARXIV_ID_PATTERN.fullmatch(arxiv_id) is None:
        raise EntryIdNotCanonicalError(f"not a canonical arXiv identifier: {arxiv_id!r}")
    identifier = SOURCE_ID_PREFIX + arxiv_id.replace("/", "--").casefold()
    if IDENTIFIER_PATTERN.fullmatch(identifier) is None:
        raise EntryIdNotCanonicalError(
            f"the derived Phase 4A source id is not an identifier: {identifier!r}"
        )
    return identifier


def record_identity_core(entry: Mapping[str, Any]) -> dict[str, Any]:
    """The semantic preimage of a record identity: metadata, nothing else."""

    return {
        "provider": PROVIDER,
        "arxiv_id": entry["arxiv_id"],
        "title": entry["title"],
        "abstract": entry["abstract"],
        "authors": list(entry["authors"]),
        "primary_category": entry["primary_category"],
        "categories": list(entry["categories"]),
        "doi": entry["doi"],
        "published": entry["published"],
        "updated": entry["updated"],
        "text_normalization": TEXT_NORMALIZATION,
    }


def record_id_for(entry: Mapping[str, Any]) -> str:
    return "corpus." + canonical_hash(record_identity_core(entry)).removeprefix("sha256:")[:24]


def build_record(
    entry: Mapping[str, Any], *, tranche_id: str, plan_hash: str,
    response_sha256: str, rights_decision_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Compose one corpus record. Every trust field is a constant, not an input."""

    record = {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id_for(entry),
        "provider": PROVIDER,
        "arxiv_id": entry["arxiv_id"],
        "source_id": source_id_for(entry["arxiv_id"]),
        "abstract_url": abstract_url_for(entry["arxiv_id"]),
        "title": entry["title"],
        "abstract": entry["abstract"],
        "authors": list(entry["authors"]),
        "primary_category": entry["primary_category"],
        "categories": list(entry["categories"]),
        "doi": entry["doi"],
        "published": entry["published"],
        "updated": entry["updated"],
        "text_normalization": TEXT_NORMALIZATION,
        "metadata_licence": METADATA_LICENCE,
        "metadata_licence_url": METADATA_LICENCE_URL,
        "response_sha256": response_sha256,
        "tranche_id": tranche_id,
        "plan_hash": plan_hash,
        "scope": dict(CORPUS_SCOPE),
        "rights_decision_ids": sorted(rights_decision_ids),
        "rights_uses": list(RIGHTS_USES),
        "status": CANDIDATE_STATUS,
        "trust_effects": dict(TRUST_EFFECTS),
        "retrieval_indexed": False,
        "content_hash": None,
    }
    record["content_hash"] = content_hash_of(record)
    return record


def _text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise RecordInvalidError(f"{label} must be text of length 1..{maximum}")
    if value != " ".join(value.split()):
        raise RecordInvalidError(f"{label} is not whitespace-normalized")
    return value


def verify_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed verification of one corpus record.

    Ordered so a trust promotion is reported as a trust promotion rather than as
    a hash mismatch: the promotion checks run before the identity checks.
    """

    if not isinstance(value, Mapping):
        raise RecordInvalidError("a corpus record must be an object")
    record = dict(public_value(value))
    if set(record) != RECORD_FIELDS:
        raise RecordInvalidError(
            "corpus record fields differ: "
            f"missing={sorted(RECORD_FIELDS - set(record))}, "
            f"extra={sorted(set(record) - RECORD_FIELDS)}"
        )
    effects = record["trust_effects"]
    if not isinstance(effects, Mapping) or set(effects) != set(TRUST_EFFECTS):
        raise RecordInvalidError("corpus record trust_effects fields differ")
    if effects.get("applicability") != TRUST_EFFECTS["applicability"] or effects.get(
        "premise_created"
    ) is not False:
        raise ApplicabilityPromotionForbiddenError(
            "a corpus record cannot carry applicability or create a premise; "
            "applicability is a human Phase 4A review over a located passage"
        )
    if (
        effects.get("mathematical_warrant") != TRUST_EFFECTS["mathematical_warrant"]
        or effects.get("epistemic_warrant_created") is not False
        or effects.get("graph_admission") != TRUST_EFFECTS["graph_admission"]
    ):
        raise WarrantPromotionForbiddenError(
            "a corpus record cannot carry a mathematical warrant or graph admission"
        )
    if record.get("retrieval_indexed") is not False:
        raise RetrievalScopeClaimForbiddenError(
            "this slice builds a corpus and does not point retrieval at it"
        )
    differing = sorted(key for key, item in TRUST_EFFECTS.items() if effects.get(key) != item)
    if differing:
        raise RecordInvalidError(f"corpus record trust effects differ for {differing}")
    if record["status"] != CANDIDATE_STATUS:
        raise RecordInvalidError(f"a corpus record status is {CANDIDATE_STATUS!r}")

    if record["schema_version"] != SCHEMA_VERSION or record["provider"] != PROVIDER:
        raise RecordInvalidError("corpus record schema or provider differs")
    arxiv_id = record["arxiv_id"]
    if not isinstance(arxiv_id, str) or ARXIV_ID_PATTERN.fullmatch(arxiv_id) is None:
        raise RecordInvalidError(f"not a canonical arXiv identifier: {arxiv_id!r}")
    if record["source_id"] != source_id_for(arxiv_id):
        raise RecordInvalidError("corpus record source_id is not the derived Phase 4A identity")
    if record["abstract_url"] != ARXIV_ABSTRACT_URL_PREFIX + arxiv_id:
        raise AbstractLinkMissingError(
            "a corpus record must carry the composed arXiv abstract page URL"
        )
    _text(record["title"], "title", maximum=MAX_TITLE_CHARS)
    _text(record["abstract"], "abstract", maximum=MAX_ABSTRACT_CHARS)
    authors = record["authors"]
    if (
        not isinstance(authors, list) or not 1 <= len(authors) <= MAX_AUTHORS_PER_ENTRY
    ):
        raise RecordInvalidError("corpus record authors bound differs")
    for author in authors:
        _text(author, "author", maximum=MAX_AUTHOR_CHARS)
    categories = record["categories"]
    if (
        not isinstance(categories, list) or not 1 <= len(categories) <= MAX_CATEGORIES_PER_ENTRY
        or categories != sorted(set(categories))
        or record["primary_category"] not in categories
    ):
        raise RecordInvalidError("corpus record categories differ")
    if record["doi"] is not None and (
        not isinstance(record["doi"], str)
        or DOI_PATTERN.fullmatch(record["doi"]) is None
    ):
        raise RecordInvalidError("corpus record doi differs")
    if record["text_normalization"] != TEXT_NORMALIZATION:
        raise RecordInvalidError("corpus record text normalization differs")
    if (
        record["metadata_licence"] != METADATA_LICENCE
        or record["metadata_licence_url"] != METADATA_LICENCE_URL
    ):
        raise RecordInvalidError("corpus record licence basis differs")
    if record["scope"] != CORPUS_SCOPE:
        raise RecordInvalidError(
            "corpus record scope differs; full text is out of scope under ADR-0067"
        )
    if not isinstance(record["response_sha256"], str) or HASH_PATTERN.fullmatch(
        record["response_sha256"]
    ) is None:
        raise RecordInvalidError("corpus record response hash differs")
    if not isinstance(record["plan_hash"], str) or HASH_PATTERN.fullmatch(
        record["plan_hash"]
    ) is None:
        raise RecordInvalidError("corpus record plan hash differs")
    if not isinstance(record["tranche_id"], str) or IDENTIFIER_PATTERN.fullmatch(
        record["tranche_id"]
    ) is None:
        raise RecordInvalidError("corpus record tranche id differs")
    if record["rights_uses"] != list(RIGHTS_USES):
        raise RecordInvalidError(
            "a corpus record records exactly the three non-disclosing Phase 4A uses"
        )
    decisions = record["rights_decision_ids"]
    if (
        not isinstance(decisions, list) or len(decisions) != len(RIGHTS_USES)
        or decisions != sorted(set(decisions))
        or any(
            not isinstance(item, str) or IDENTIFIER_PATTERN.fullmatch(item) is None
            for item in decisions
        )
    ):
        raise RecordInvalidError(
            "a corpus record links one Phase 4A rights decision per recorded use"
        )
    if record["record_id"] != record_id_for(record):
        raise RecordInvalidError("corpus record identity differs from its metadata")
    supplied = record["content_hash"]
    if not isinstance(supplied, str) or HASH_PATTERN.fullmatch(supplied) is None:
        raise RecordInvalidError("corpus record content hash is not a sha256 value")
    if content_hash_of(record) != supplied:
        raise RecordInvalidError("corpus record content hash does not match its content")
    return record


__all__ = [
    "RECORD_FIELDS",
    "RIGHTS_USES",
    "SOURCE_ID_PREFIX",
    "build_record",
    "record_id_for",
    "record_identity_core",
    "source_id_for",
    "verify_record",
]
