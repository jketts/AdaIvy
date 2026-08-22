"""Frozen vocabularies for the ADR-0065 embedding slice.

Defined once so the partition-key validator, the run-configuration validator,
the ingestion guard and the manifest writer cannot drift apart.
"""

from __future__ import annotations

import re

from ..phase2 import SUPPORTED_LIVE_PROVIDERS

#: The single non-provider partition value. It may be authored and read offline
#: and can never be produced by the live ingestion path. Any manifest built on
#: it carries ``corpus_provenance == "project_authored"``, mirroring ADR-0034's
#: ``control_corpus_provenance``, so a synthetic-vector result is never mistaken
#: for evidence about real embedding quality.
FIXTURE_SYNTHETIC_PROVIDER = "fixture_synthetic"

#: Providers that can actually reach an embeddings endpoint in this repository.
#: Both go through the `openai` SDK, which is already a declared gated import.
#: A provider admitted at the Phase 2 model boundary but absent here has no
#: embedding adapter and is therefore unreachable, not merely unconfigured.
SUPPORTED_EMBEDDING_PROVIDERS = frozenset({"azure_openai", "openai"})

#: Values admissible in the ``provider`` component of a partition key.
PARTITION_PROVIDERS = frozenset(SUPPORTED_LIVE_PROVIDERS) | {FIXTURE_SYNTHETIC_PROVIDER}

#: Quantization schemes, name -> binary scale exponent. The scheme is NOT a free
#: parameter hidden in code: it is the ``normalization`` component of the
#: blueprint's partition tuple, so changing it changes the partition and
#: therefore forces a full rebuild.
NORMALIZATION_SCHEMES: dict[str, int] = {
    "round_half_even_scale_2p20": 20,
    "round_half_even_scale_2p30": 30,
}

DEFAULT_NORMALIZATION = "round_half_even_scale_2p30"

CORPUS_PROVENANCE_PROJECT_AUTHORED = "project_authored"
CORPUS_PROVENANCE_PROVIDER_EMBEDDED = "provider_embedded"
CORPUS_PROVENANCE_VALUES = (
    CORPUS_PROVENANCE_PROJECT_AUTHORED,
    CORPUS_PROVENANCE_PROVIDER_EMBEDDED,
)

#: Output tokens for an embeddings call, as a stated constant rather than an
#: accident of a provider payload. A result claiming otherwise is refused.
OUTPUT_TOKENS_CONSTANT = 0

MIN_DIMENSION = 1
MAX_DIMENSION = 8192

#: Identifier charset for every component that becomes a path segment. Lowercase
#: only: `reports/` lives on case-insensitive filesystems, so two identifiers
#: differing only in case would collide silently, and a silent collision in a
#: content-addressed store is exactly the failure this slice exists to prevent.
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")

HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

#: Exact string required alongside ``--execute`` before any text leaves the
#: process. Ingestion is billable and a provider seeing the text is irreversible.
LIVE_EMBEDDING_ACKNOWLEDGEMENT = "I_ACKNOWLEDGE_LIVE_EMBEDDING_INGESTION"


__all__ = [
    "CORPUS_PROVENANCE_PROJECT_AUTHORED",
    "CORPUS_PROVENANCE_PROVIDER_EMBEDDED",
    "CORPUS_PROVENANCE_VALUES",
    "DEFAULT_NORMALIZATION",
    "FIXTURE_SYNTHETIC_PROVIDER",
    "HASH_PATTERN",
    "IDENTIFIER_PATTERN",
    "LIVE_EMBEDDING_ACKNOWLEDGEMENT",
    "MAX_DIMENSION",
    "MIN_DIMENSION",
    "NORMALIZATION_SCHEMES",
    "OUTPUT_TOKENS_CONSTANT",
    "PARTITION_PROVIDERS",
    "SUPPORTED_EMBEDDING_PROVIDERS",
]
