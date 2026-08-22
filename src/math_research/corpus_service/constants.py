"""Pinned bounds and frozen vocabularies for the persistent corpus service.

Every bound is defined once, in code, so a config file can state it but never
widen it.  Where a value restates an ADR-0067/ADR-0064 constant, it is imported
from the original module rather than retyped.
"""

from __future__ import annotations

from ..corpus.constants import (  # noqa: F401 -- re-exported pinned patterns
    APPLICABILITY_CEILING,
    CANDIDATE_STATUS,
    HASH_PATTERN,
    IDENTIFIER_PATTERN,
    TIMESTAMP_PATTERN,
)

PROVIDER = "open_access_snapshot"

#: ADR-0067 option C: the bounded first tranche is "low thousands of documents
#: at most".  These ceilings bound the operator-configured tranche; a tranche
#: config may pin smaller values, never larger.
MAX_TRANCHE_DOCUMENTS = 2_048
MAX_TRANCHE_TOTAL_BYTES = 268_435_456
MAX_DOCUMENT_BYTES = 8_388_608
MAX_DOCUMENT_CHARS = 2_097_152
MAX_SPANS_PER_DOCUMENT = 16_384

MAX_POLICY_BYTES = 65_536
MAX_ARCHIVE_MANIFEST_BYTES = 8_388_608
MAX_TRANCHE_CONFIG_BYTES = 16_384
MAX_GENERATION_BYTES = 67_108_864
MAX_LEDGER_RECORD_BYTES = 1_048_576
MAX_ACTIVATION_BYTES = 16_384

#: Only these media types have an exact parser in this slice.  Anything else is
#: quarantined as ``unsupported_media_type`` — recorded, retained, excluded.
PARSABLE_MEDIA_TYPES = frozenset({"text/plain", "text/markdown"})

#: The exact span transformation identifier (ADR-0060 conventions): character
#: offsets into the strict UTF-8 decode of the immutable source bytes, exact
#: substring, no normalization.
SPAN_TRANSFORMATION = "utf8_exact_char_spans_v1"

#: Phase 4A caps a workspace at 256 append-only records.  One admitted document
#: needs at most five initial decisions and five later superseding/revocation
#: decisions. Reserve the complete lifecycle: 1 + 25 * 10 = 251 of 256.
RIGHTS_SHARD_MAX_DOCUMENTS = 25

#: Exact acknowledgement for the live snapshot acquisition gate.  Acquiring a
#: bulk archive sends traffic to a third party under its terms; not a default.
LIVE_SNAPSHOT_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_LIVE_OPEN_ACCESS_SNAPSHOT_ACQUISITION"

CAPABILITY_ID = "capability.corpus-service.open-access-snapshot-tranche"

#: Trust every corpus-service artifact carries.  Nothing here may be promoted:
#: policy-derived rights govern processing, never meaning.
TRUST_EFFECTS = {
    "applicability": "not_assessed",
    "epistemic_warrant_created": False,
    "graph_admission": "not_admitted",
    "mathematical_warrant": "none",
    "novelty": "not_assessed",
    "premise_created": False,
    "relevance": "not_assessed",
    "significance": "not_assessed",
}

#: Closed set of quarantine reasons.  Quarantine is recorded, retained, and
#: excluded; it never prompts and it is never silently admitted (ADR-0072 §7).
QUARANTINE_REASONS = (
    "licence_missing",
    "licence_unknown",
    "licence_conflicting",
    "unsupported_media_type",
    "parse_failure",
)

RELATIVE_PATH_PATTERN_TEXT = r"^[a-z0-9][a-z0-9._/-]{0,255}$"

DATE_PATTERN_TEXT = r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:[0-2][0-9]|3[01])$"

__all__ = [
    "APPLICABILITY_CEILING",
    "CANDIDATE_STATUS",
    "CAPABILITY_ID",
    "DATE_PATTERN_TEXT",
    "HASH_PATTERN",
    "IDENTIFIER_PATTERN",
    "LIVE_SNAPSHOT_ACKNOWLEDGEMENT",
    "MAX_ACTIVATION_BYTES",
    "MAX_ARCHIVE_MANIFEST_BYTES",
    "MAX_DOCUMENT_BYTES",
    "MAX_DOCUMENT_CHARS",
    "MAX_GENERATION_BYTES",
    "MAX_LEDGER_RECORD_BYTES",
    "MAX_POLICY_BYTES",
    "MAX_SPANS_PER_DOCUMENT",
    "MAX_TRANCHE_CONFIG_BYTES",
    "MAX_TRANCHE_DOCUMENTS",
    "MAX_TRANCHE_TOTAL_BYTES",
    "PARSABLE_MEDIA_TYPES",
    "PROVIDER",
    "QUARANTINE_REASONS",
    "RELATIVE_PATH_PATTERN_TEXT",
    "RIGHTS_SHARD_MAX_DOCUMENTS",
    "SPAN_TRANSFORMATION",
    "TIMESTAMP_PATTERN",
    "TRUST_EFFECTS",
]
