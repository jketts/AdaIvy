"""Frozen vocabularies and pinned bounds for the ADR-0067 corpus slice.

Every bound here comes from the arXiv API Terms of Use as recorded in ADR-0067's
"Licence diligence, performed 2026-08-22" section.  They are defined once, in
code, so the activation-record validator, the plan validator, the pacer and the
probe suite cannot drift apart, and so a caller cannot supply a wider value.
"""

from __future__ import annotations

import re

PROVIDER = "arxiv"

#: The single authorized origin.  Not a crawl, not a traversal, and not the
#: separate export service that arXiv's bulk-data page mentions.
ARXIV_API_ORIGIN = "https://export.arxiv.org"
ARXIV_API_QUERY_PATH = "/api/query"
ARXIV_API_HOSTNAME = "export.arxiv.org"

#: Where a reader must be sent for the e-print itself.  Composed from a pinned
#: template and the validated identifier; never taken from the feed.
ARXIV_ABSTRACT_URL_PREFIX = "https://arxiv.org/abs/"

#: "Make no more than one request every three seconds, and limit requests to a
#: single connection at a time."  Both are pinned, not configurable.
MIN_REQUEST_INTERVAL_MILLISECONDS = 3_000
MAX_CONCURRENT_CONNECTIONS = 1

#: Descriptive metadata is CC0 1.0; the e-prints are not.  ``CORPUS_SCOPE``
#: is echoed into every record, ingestion result and report.
METADATA_LICENCE = "CC0-1.0"
METADATA_LICENCE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
ARXIV_API_TERMS_URL = "https://info.arxiv.org/help/api/tou.html"
TERMS_REVIEWED_AT = "2026-08-22"
MAX_TERMS_AGE_SECONDS = 2_592_000

#: Phase 4A caps one workspace at 256 append-only records
#: (``phase4a/__init__.py``: ``MAX_RECORDS = 256``).  One document needs three
#: rights decisions -- acquisition, storage/retention, parsing -- and a
#: workspace needs one policy snapshot, so 85 documents exactly fill a shard
#: (1 + 85 * 3 = 256).  The tranche bound is DERIVED from that rather than
#: chosen, so a larger tranche cannot be pinned without also deciding how its
#: rights records are stored.
RIGHTS_SHARD_MAX_DOCUMENTS = 85
MAX_RIGHTS_SHARDS = 24
TRANCHE_MAX_RECORDS = RIGHTS_SHARD_MAX_DOCUMENTS * MAX_RIGHTS_SHARDS

#: arXiv serves at most a page at a time; 100 keeps a single response small
#: enough to hash, store and re-parse.
MAX_RECORDS_PER_REQUEST = 100
#: ``ceil(TRANCHE_MAX_RECORDS / MAX_RECORDS_PER_REQUEST)``, stated so the
#: activation record can pin it and the pacer can refuse past it.
MAX_REQUESTS_PER_RUN = -(-TRANCHE_MAX_RECORDS // MAX_RECORDS_PER_REQUEST)

MAX_RESPONSE_BYTES = 4_194_304
MAX_ACTIVATION_BYTES = 16_384
MAX_PLAN_BYTES = 16_384
MAX_MANIFEST_BYTES = 1_048_576
MAX_REPORT_BYTES = 8_388_608
REQUEST_TIMEOUT_MILLISECONDS = 30_000

#: Exact string required alongside ``--execute``.  Live acquisition sends
#: traffic to a third party under its terms; that is not a default.
LIVE_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_LIVE_ARXIV_METADATA_ACQUISITION"

CAPABILITY_ID = "capability.corpus.arxiv-metadata-tranche"

#: The complete arXiv mathematics category set.  A plan naming anything else is
#: refused: "over mathematics categories" is a bound, not a description.
MATHEMATICS_CATEGORIES = (
    "math.AC", "math.AG", "math.AP", "math.AT", "math.CA", "math.CO",
    "math.CT", "math.CV", "math.DG", "math.DS", "math.FA", "math.GM",
    "math.GN", "math.GR", "math.GT", "math.HO", "math.IT", "math.KT",
    "math.LO", "math.MG", "math.MP", "math.NA", "math.NT", "math.OA",
    "math.OC", "math.PR", "math.QA", "math.RA", "math.RT", "math.SG",
    "math.SP", "math.ST",
)
MATHEMATICS_CATEGORY_SET = frozenset(MATHEMATICS_CATEGORIES)
MAX_PLAN_CATEGORIES = len(MATHEMATICS_CATEGORIES)

#: Sort order is pinned ascending on submission date over a pinned window, so a
#: tranche is a reproducible set rather than "whatever was newest that day".
SORT_BY = "submittedDate"
SORT_ORDER = "ascending"

#: Reader-facing quotation bounds.  The terms oblige a projection to link out
#: rather than reproduce, so a projection quotes and truncates.
MAX_QUOTED_TITLE_CHARS = 300
MAX_QUOTED_ABSTRACT_CHARS = 240
QUOTATION_ELLIPSIS = "…"

MAX_TITLE_CHARS = 1_024
MAX_ABSTRACT_CHARS = 16_384
MAX_AUTHORS_PER_ENTRY = 64
MAX_AUTHOR_CHARS = 256
MAX_CATEGORIES_PER_ENTRY = 32

ARXIV_ID_PATTERN = re.compile(
    r"^(?:[0-9]{4}\.[0-9]{4,5}|[a-z]+(?:-[a-z]+)?(?:\.[A-Z]{2})?/[0-9]{7})(?:v[1-9][0-9]{0,2})?$"
)
DOI_PATTERN = re.compile(r"^10\.[0-9]{4,9}/\S{1,240}$")
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
SUBMITTED_WINDOW_PATTERN = re.compile(r"^[0-9]{12}$")
TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:[0-2][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)

#: Values every corpus record and report carries.  A corpus record is an
#: untrusted inspiration candidate and nothing here may be promoted.
CANDIDATE_STATUS = "untrusted_inspiration_candidate"
TRUST_EFFECTS = {
    "acquisition_authorized_for_full_text": False,
    "applicability": "not_assessed",
    "epistemic_warrant_created": False,
    "graph_admission": "not_admitted",
    "mathematical_warrant": "none",
    "novelty": "not_assessed",
    "premise_created": False,
    "relevance": "not_assessed",
    "significance": "not_assessed",
}

#: Applicability is human and stays the ceiling (ADR-0067).  A report states the
#: ceiling explicitly rather than letting a record count imply knowledge.
APPLICABILITY_CEILING = "human_only"

CORPUS_SCOPE = {
    "descriptive_metadata": True,
    "abstracts": True,
    "full_text": False,
    "full_text_authorized": False,
    "metadata_licence": METADATA_LICENCE,
    "metadata_licence_url": METADATA_LICENCE_URL,
}


__all__ = [
    "APPLICABILITY_CEILING",
    "ARXIV_ABSTRACT_URL_PREFIX",
    "ARXIV_API_HOSTNAME",
    "ARXIV_API_ORIGIN",
    "ARXIV_API_QUERY_PATH",
    "ARXIV_API_TERMS_URL",
    "ARXIV_ID_PATTERN",
    "CANDIDATE_STATUS",
    "CAPABILITY_ID",
    "CORPUS_SCOPE",
    "DOI_PATTERN",
    "HASH_PATTERN",
    "IDENTIFIER_PATTERN",
    "LIVE_ACKNOWLEDGEMENT",
    "MATHEMATICS_CATEGORIES",
    "MATHEMATICS_CATEGORY_SET",
    "MAX_ABSTRACT_CHARS",
    "MAX_ACTIVATION_BYTES",
    "MAX_AUTHORS_PER_ENTRY",
    "MAX_AUTHOR_CHARS",
    "MAX_CATEGORIES_PER_ENTRY",
    "MAX_CONCURRENT_CONNECTIONS",
    "MAX_MANIFEST_BYTES",
    "MAX_PLAN_BYTES",
    "MAX_PLAN_CATEGORIES",
    "MAX_QUOTED_ABSTRACT_CHARS",
    "MAX_QUOTED_TITLE_CHARS",
    "MAX_RECORDS_PER_REQUEST",
    "MAX_REPORT_BYTES",
    "MAX_REQUESTS_PER_RUN",
    "MAX_RESPONSE_BYTES",
    "MAX_RIGHTS_SHARDS",
    "MAX_TERMS_AGE_SECONDS",
    "MAX_TITLE_CHARS",
    "METADATA_LICENCE",
    "METADATA_LICENCE_URL",
    "MIN_REQUEST_INTERVAL_MILLISECONDS",
    "PROVIDER",
    "QUOTATION_ELLIPSIS",
    "REQUEST_TIMEOUT_MILLISECONDS",
    "RIGHTS_SHARD_MAX_DOCUMENTS",
    "SORT_BY",
    "SORT_ORDER",
    "SUBMITTED_WINDOW_PATTERN",
    "TERMS_REVIEWED_AT",
    "TIMESTAMP_PATTERN",
    "TRANCHE_MAX_RECORDS",
    "TRUST_EFFECTS",
]
