"""Embedding provider port and exact content-hashed vector artifacts (ADR-0065).

`TECHNICAL_BLUEPRINT.md` Section 12.2.1 imposes four obligations on any vector
projection, and this package implements them as written:

* a vector index is partitioned by ``(provider, model_identifier, dimension,
  normalization)`` with no default and no fallback partition (`:1661-1663`);
* a provider or model change is a full rebuild, never a mixed backfill
  (`:1664-1666`) -- there is no code path here that merges two partitions, and
  the absence is the enforcement;
* produced vectors are immutable content-hashed artifacts whose bytes are bound
  into canonical identity, and a rebuild replays them without calling the
  provider (`:1667-1671`);
* each provider carries its own pinned pricing snapshot, and embedding models are
  input-token-only (`:1676-1678`).

Two constraints demand the same architecture. The blueprint wants replay from
bytes because a remote API is not bit-reproducible; Phase 4C's acceptance path
independently forbids the live call outright. So EMBEDDING IS AN INGESTION-TIME
ACT, RETRIEVAL IS A READ OVER FROZEN ARTIFACTS, AND THE TWO NEVER SHARE A
PROCESS.

Exactness. Provider floats are converted once, at ingestion, by round-half-even
scaling at a declared power of two; only the integers are stored and the read
path constructs no float and never divides. Similarity is compared by
cross-multiplying integers, so there is no square root, no division and no
epsilon, and a tie is exactly decidable rather than machine noise.

What this package does NOT do. It adds no retrieval behaviour: Phase 4C is
untouched, and its seven gates, report hashes and fixture cardinalities are
unmodified. A vector is not evidence -- an artifact records that a text was
embedded by a named processor and creates no applicability record, no premise, no
graph admission and no warrant. An artifact store full of vectors is not a
literature search and must not be reported as one.
"""

from __future__ import annotations

from .authoring import (
    AUTHORING_SPEC_SCHEMA_VERSION,
    AuthoringSpec,
    author_partition,
    load_authoring_spec,
)
from .constants import (
    CORPUS_PROVENANCE_PROJECT_AUTHORED,
    CORPUS_PROVENANCE_PROVIDER_EMBEDDED,
    DEFAULT_NORMALIZATION,
    FIXTURE_SYNTHETIC_PROVIDER,
    LIVE_EMBEDDING_ACKNOWLEDGEMENT,
    NORMALIZATION_SCHEMES,
    OUTPUT_TOKENS_CONSTANT,
    PARTITION_PROVIDERS,
    SUPPORTED_EMBEDDING_PROVIDERS,
)
from .errors import EmbeddingError
from .partition import (
    ARTIFACT_SCHEMA_VERSION,
    PARTITION_SCHEMA_VERSION,
    Partition,
    PartitionKey,
    PartitionedVector,
    VectorArtifact,
    create_vector_artifact,
    load_partition,
    write_partition,
    write_vector_artifact,
)
from .ports import EmbeddingGateway, RightsGate, SourceTextReader
from .quantization import QuantizedVector, quantize, round_half_even
from .readpath import READ_PATH_MODULES, sweep_read_path
from .records import EmbeddingRequest, EmbeddingResult, EmbeddingUsage
from .replay import REPLAY_REPORT_SCHEMA_VERSION, replay_partition
from .rights import Phase4ProcessorRightsGate, processor_bound_rights_supported
from .run_config import (
    EMBEDDING_RUN_CONFIG_SCHEMA_VERSION,
    EmbeddingBudget,
    EmbeddingRunConfiguration,
    create_embedding_run_configuration,
    load_embedding_run_configuration,
    write_embedding_run_configuration,
)
from .similarity import (
    compare_cosine,
    cosine_terms,
    cosine_terms_within_partition,
    dot,
    norm_squared,
    rank_exact_cosine,
    require_same_partition,
)

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORING_SPEC_SCHEMA_VERSION",
    "AuthoringSpec",
    "CORPUS_PROVENANCE_PROJECT_AUTHORED",
    "CORPUS_PROVENANCE_PROVIDER_EMBEDDED",
    "DEFAULT_NORMALIZATION",
    "EMBEDDING_RUN_CONFIG_SCHEMA_VERSION",
    "EmbeddingBudget",
    "EmbeddingError",
    "EmbeddingGateway",
    "EmbeddingRequest",
    "EmbeddingResult",
    "EmbeddingRunConfiguration",
    "EmbeddingUsage",
    "FIXTURE_SYNTHETIC_PROVIDER",
    "LIVE_EMBEDDING_ACKNOWLEDGEMENT",
    "NORMALIZATION_SCHEMES",
    "OUTPUT_TOKENS_CONSTANT",
    "PARTITION_PROVIDERS",
    "PARTITION_SCHEMA_VERSION",
    "Partition",
    "PartitionKey",
    "PartitionedVector",
    "Phase4ProcessorRightsGate",
    "QuantizedVector",
    "READ_PATH_MODULES",
    "REPLAY_REPORT_SCHEMA_VERSION",
    "RightsGate",
    "SUPPORTED_EMBEDDING_PROVIDERS",
    "SourceTextReader",
    "VectorArtifact",
    "author_partition",
    "compare_cosine",
    "cosine_terms",
    "cosine_terms_within_partition",
    "create_embedding_run_configuration",
    "create_vector_artifact",
    "dot",
    "load_authoring_spec",
    "load_embedding_run_configuration",
    "load_partition",
    "norm_squared",
    "processor_bound_rights_supported",
    "quantize",
    "rank_exact_cosine",
    "replay_partition",
    "require_same_partition",
    "round_half_even",
    "sweep_read_path",
    "write_embedding_run_configuration",
    "write_partition",
    "write_vector_artifact",
]
