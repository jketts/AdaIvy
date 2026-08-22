"""Frozen resource bounds and closed vocabularies for the Phase 4C slice.

Bounds follow the Phase 4B `ParserBounds` precedent: a frozen dataclass with a
`to_record()` projection and a `policy_sha256` content hash, so the declared
policy cannot drift from the policy enforced.

Every violation raises `Phase4CValidationError`. Nothing here coerces.
"""

from __future__ import annotations

from dataclasses import dataclass

from .serialization import canonical_bytes, sha256_bytes


# ADR-0070 adds a fourth signal, so every hit gains semantic fields and the
# report gains two partition-identity fields. That is a report-shape change,
# and the shape is versioned rather than extended in place.
SCHEMA_VERSION = "adaivy.phase4c-hybrid-retrieval.v3"
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

# --------------------------------------------------------------------------
# ADR-0070: the semantic signal's declared partition and its frozen tiering.
#
# THESE CONSTANTS WERE FIXED BEFORE ANY GATE WAS MEASURED AND ARE NOT TO BE
# ADJUSTED AFTER SEEING A GATE RESULT. If a gate regresses, the regression is
# the finding. Retuning a threshold against the fixtures it is measured on
# would make the whole benchmark worthless.
# --------------------------------------------------------------------------

#: The single declared partition. There is no default and no fallback: a
#: manifest declaring anything else is a refusal, per
#: `TECHNICAL_BLUEPRINT.md:1661-1663`.
SEMANTIC_PARTITION_PROVIDER = "fixture_synthetic"
SEMANTIC_PARTITION_MODEL_IDENTIFIER = "adaivy-cooccurrence-anchor-v1"
SEMANTIC_PARTITION_DIMENSION = 32
SEMANTIC_PARTITION_NORMALIZATION = "round_half_even_scale_2p30"
#: Sibling of the Phase 4C fixture directory. Derived from the fixture root
#: rather than read from the working directory, so a benchmark run from any
#: directory reads the same partition or refuses.
SEMANTIC_PARTITION_DIRNAME = "phase4c-semantic"
SEMANTIC_PARTITION_MANIFEST_NAME = "manifest.json"
#: The fixture manifest and every artifact state this rule. Phase 4C itself POPS
#: the hash key (`serialization.py`); this partition SETS IT TO NULL, and mixing
#: the two changes every hash, so the rule is read from the bytes and honoured
#: rather than assumed.
SEMANTIC_HASH_RULE = "content_hash_over_canonical_body_with_hash_field_set_to_null"
SEMANTIC_MANIFEST_SCHEMA_VERSION = "adaivy.vector-partition-manifest.v1"
SEMANTIC_ARTIFACT_SCHEMA_VERSION = "adaivy.vector-artifact.v1"
SEMANTIC_CORPUS_PROVENANCE = "project_authored"

#: Rank tiers, `(first_rank, last_rank, tier_credit)`, inclusive on both ends.
#: Three points is deliberately below ADR-0031's smallest measured BM25 gold
#: margin, so the signal can promote a document the lexical signal missed
#: entirely and cannot on its own invert a lexical gold ordering.
SEMANTIC_TIERS = (
    (1, 2, 3),
    (3, 5, 2),
    (6, 10, 1),
)
#: The largest credit any rank can earn, derived from the tiers rather than
#: restated, so a declared ceiling cannot drift from the enforced one.
MAXIMUM_SEMANTIC_TIER_CREDIT = max(credit for _first, _last, credit in SEMANTIC_TIERS)


def semantic_tier_credit(rank: int) -> int:
    """Tier credit for a 1-based exact-cosine rank. Outside every tier: `0`."""

    if isinstance(rank, bool) or not isinstance(rank, int):
        raise Phase4CValidationError(
            f"semantic rank must be an integer, got {type(rank).__name__}"
        )
    if rank < 1:
        raise Phase4CValidationError(f"semantic rank must be at least 1, got {rank}")
    for first, last, credit in SEMANTIC_TIERS:
        if first <= rank <= last:
            return credit
    return 0


def semantic_tier_rule() -> list[dict[str, int]]:
    """The declared tiering, projected from the constants that enforce it."""

    return [
        {"first_rank": first, "last_rank": last, "tier_credit": credit}
        for first, last, credit in SEMANTIC_TIERS
    ]


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
    # ADR-0070, frozen before measurement. The semantic signal asks for ten
    # candidates and each carries at most three points.
    semantic_candidate_limit: int = 10
    semantic_tier_points: int = 1

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
            "semantic_candidate_limit": self.semantic_candidate_limit,
            "semantic_tier_points": self.semantic_tier_points,
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
    "MAXIMUM_SEMANTIC_TIER_CREDIT",
    "Phase4CValidationError",
    "SCHEMA_VERSION",
    "SEMANTIC_ARTIFACT_SCHEMA_VERSION",
    "SEMANTIC_CORPUS_PROVENANCE",
    "SEMANTIC_HASH_RULE",
    "SEMANTIC_MANIFEST_SCHEMA_VERSION",
    "SEMANTIC_PARTITION_DIMENSION",
    "SEMANTIC_PARTITION_DIRNAME",
    "SEMANTIC_PARTITION_MANIFEST_NAME",
    "SEMANTIC_PARTITION_MODEL_IDENTIFIER",
    "SEMANTIC_PARTITION_NORMALIZATION",
    "SEMANTIC_PARTITION_PROVIDER",
    "SEMANTIC_TIERS",
    "SOURCE_CLASSES",
    "THRESHOLD_KEYS",
    "TOP_K_BY_CATEGORY",
    "semantic_tier_credit",
    "semantic_tier_rule",
]
