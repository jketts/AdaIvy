"""Coded, fail-closed refusals for the ADR-0069 embedding slice.

Every refusal carries a stable ``code``. The falsifiability probes assert on the
code rather than on a message, so a reworded diagnostic cannot silently turn a
probe into a no-op.
"""

from __future__ import annotations


class EmbeddingError(ValueError):
    """Base refusal. ``code`` is part of the acceptance contract."""

    code = "embedding_error"

    def __init__(self, detail: str = "", *, code: str | None = None) -> None:
        if code is not None:
            self.code = code
        self.detail = detail
        super().__init__(f"{self.code}: {detail}" if detail else self.code)


class PartitionKeyError(EmbeddingError):
    code = "partition_key_invalid"


class PartitionMismatchError(EmbeddingError):
    """Two operands do not share a partition. There is no coercion."""

    code = "partition_mismatch"

    def __init__(self, component: str, detail: str = "") -> None:
        self.component = component
        super().__init__(detail, code=f"partition_mismatch:{component}")


class PartitionAbsentError(EmbeddingError):
    code = "partition_absent"


class PartitionSchemaError(EmbeddingError):
    code = "partition_schema_invalid"


class ManifestKeyMismatchError(EmbeddingError):
    code = "manifest_key_mismatch"


class ManifestHashMismatchError(EmbeddingError):
    code = "manifest_hash_mismatch"


class ArtifactMissingError(EmbeddingError):
    code = "artifact_missing"


class ArtifactHashMismatchError(EmbeddingError):
    code = "artifact_hash_mismatch"


class ArtifactOverwriteRefused(EmbeddingError):
    code = "artifact_overwrite_refused"


class DocumentAbsentError(EmbeddingError):
    code = "document_absent"


class ZeroNormVectorError(EmbeddingError):
    code = "zero_norm_vector"


class NonIntegerCoordinateError(EmbeddingError):
    code = "non_integer_coordinate"


class CoordinateSaturatedError(EmbeddingError):
    """A coordinate outside the declared scale. A fault, never a clamp."""

    code = "coordinate_saturated"


class NormalizationUnknownError(EmbeddingError):
    code = "normalization_unknown"


class OutputTokensNotZeroError(EmbeddingError):
    code = "output_tokens_not_zero"


class EmbeddingRunConfigurationError(EmbeddingError):
    code = "embedding_run_configuration_invalid"


class EmbeddingIngestionError(EmbeddingError):
    code = "embedding_ingestion_refused"


class FixtureProviderNotIngestibleError(EmbeddingError):
    """``fixture_synthetic`` may be authored offline and never produced live."""

    code = "fixture_provider_not_ingestible"


class ProviderCallForbiddenError(EmbeddingError):
    """Raised by the forbidding gateway: the replay path must never reach it."""

    code = "provider_call_forbidden"


class RightsSeamUnavailableError(EmbeddingError):
    """ADR-0064's processor-bound ``require_rights`` is not present yet."""

    code = "processor_bound_rights_unavailable"


class ProcessorNotNamedError(EmbeddingError):
    code = "processor_not_named"


class ReadPathPurityError(EmbeddingError):
    code = "float_on_read_path"


class TieOrderError(EmbeddingError):
    code = "tie_order_not_document_id_ascending"


__all__ = [
    "ArtifactHashMismatchError",
    "ArtifactMissingError",
    "ArtifactOverwriteRefused",
    "CoordinateSaturatedError",
    "DocumentAbsentError",
    "EmbeddingError",
    "EmbeddingIngestionError",
    "EmbeddingRunConfigurationError",
    "FixtureProviderNotIngestibleError",
    "ManifestHashMismatchError",
    "ManifestKeyMismatchError",
    "NonIntegerCoordinateError",
    "NormalizationUnknownError",
    "OutputTokensNotZeroError",
    "PartitionAbsentError",
    "PartitionKeyError",
    "PartitionMismatchError",
    "PartitionSchemaError",
    "ProcessorNotNamedError",
    "ProviderCallForbiddenError",
    "ReadPathPurityError",
    "RightsSeamUnavailableError",
    "TieOrderError",
    "ZeroNormVectorError",
]
