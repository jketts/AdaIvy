"""Frozen resource bounds and closed vocabularies for the Phase 4C slice.

Bounds follow the Phase 4B `ParserBounds` precedent: a frozen dataclass with a
`to_record()` projection and a `policy_sha256` content hash, so the declared
policy cannot drift from the policy enforced.

Every violation raises `Phase4CValidationError`. Nothing here coerces.
"""

from __future__ import annotations

from dataclasses import dataclass

from .serialization import canonical_bytes, sha256_bytes


SCHEMA_VERSION = "adaivy.phase4c-hybrid-retrieval.v2"
CORPUS_SCHEMA_VERSION = "adaivy.phase4c-corpus.v1"
GOLD_SCHEMA_VERSION = "adaivy.phase4c-gold-queries.v1"
ALIAS_SCHEMA_VERSION = "adaivy.phase4c-name-aliases.v1"
FIXTURE_LICENSE = "LicenseRef-AdaIvy-Synthetic-Fixture"

CATEGORIES = (
    "necessary_lemma",
    "applicability",
    "contradiction",
    "notation_variant",
    "renamed_known_result",
)
# Cardinalities are part of the frozen benchmark contract, not a default.
# ADR-0032 is the third fixture extension: 19 documents and 17 queries, with 6
# applicability queries. Values measured before it describe a different corpus.
CATEGORY_COUNTS = {
    "necessary_lemma": 3,
    "applicability": 6,
    "contradiction": 2,
    "notation_variant": 2,
    "renamed_known_result": 4,
}
TOP_K_BY_CATEGORY = {
    "necessary_lemma": 5,
    "applicability": 5,
    "contradiction": 5,
    "notation_variant": 5,
    "renamed_known_result": 10,
}
SOURCE_CLASSES = ("primary", "secondary", "historical", "informal")
APPLICABILITY_CLASSES = (
    "applicable",
    "incompatible_hypotheses",
    "insufficient_evidence",
)

THRESHOLD_KEYS = (
    "necessary_lemma_recall_at_5",
    "applicability_precision_at_5",
    "contradiction_recall_at_5",
    "notation_variant_recall_at_5",
    "renamed_known_result_recall_at_10",
    "duplicate_rate_at_5_maximum",
    "external_spend_usd",
)
# threshold key -> (measured metric name, comparison)
GATE_COMPARISONS = {
    "necessary_lemma_recall_at_5": ("necessary_lemma_recall_at_5", "at_least"),
    "applicability_precision_at_5": ("applicability_precision_at_5", "at_least"),
    "contradiction_recall_at_5": ("contradiction_recall_at_5", "at_least"),
    "notation_variant_recall_at_5": ("notation_variant_recall_at_5", "at_least"),
    "renamed_known_result_recall_at_10": ("renamed_known_result_recall_at_10", "at_least"),
    "duplicate_rate_at_5_maximum": ("duplicate_rate_at_5", "at_most"),
    "external_spend_usd": ("external_spend_usd", "exactly"),
}


class Phase4CValidationError(ValueError):
    """The single Phase 4C rejection type. Every check fails closed."""


@dataclass(frozen=True)
class HybridRetrievalBounds:
    """Benchmark-scoped resource bounds. All limits are inclusive maxima."""

    document_count: int = 19
    query_count: int = 17
    max_query_bytes: int = 4_096
    top_k_default: int = 5
    top_k_renamed_control: int = 10
    max_candidates_per_signal: int = 50
    max_report_bytes: int = 262_144
    max_derived_db_bytes: int = 2_097_152
    max_elapsed_ms: int = 10_000
    duplicate_cutoff: int = 5

    def to_record(self) -> dict[str, int]:
        return {
            "document_count": self.document_count,
            "duplicate_cutoff": self.duplicate_cutoff,
            "max_candidates_per_signal": self.max_candidates_per_signal,
            "max_derived_db_bytes": self.max_derived_db_bytes,
            "max_elapsed_ms": self.max_elapsed_ms,
            "max_query_bytes": self.max_query_bytes,
            "max_report_bytes": self.max_report_bytes,
            "query_count": self.query_count,
            "top_k_default": self.top_k_default,
            "top_k_renamed_control": self.top_k_renamed_control,
        }

    @property
    def policy_sha256(self) -> str:
        return sha256_bytes(canonical_bytes(self.to_record()))


BOUNDS = HybridRetrievalBounds()


__all__ = [
    "ALIAS_SCHEMA_VERSION",
    "APPLICABILITY_CLASSES",
    "BOUNDS",
    "CATEGORIES",
    "CATEGORY_COUNTS",
    "CORPUS_SCHEMA_VERSION",
    "FIXTURE_LICENSE",
    "GATE_COMPARISONS",
    "GOLD_SCHEMA_VERSION",
    "HybridRetrievalBounds",
    "Phase4CValidationError",
    "SCHEMA_VERSION",
    "SOURCE_CLASSES",
    "THRESHOLD_KEYS",
    "TOP_K_BY_CATEGORY",
]
