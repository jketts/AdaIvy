"""Coded, fail-closed refusals for the persistent corpus service.

Every refusal carries a stable ``code`` so tests assert on the code rather than
on wording, mirroring :mod:`math_research.corpus.errors`.
"""

from __future__ import annotations


class CorpusServiceError(ValueError):
    """Base refusal. ``code`` is part of the acceptance contract."""

    code = "corpus_service_error"

    def __init__(self, detail: str = "", *, code: str | None = None) -> None:
        if code is not None:
            self.code = code
        self.detail = detail
        super().__init__(f"{self.code}: {detail}" if detail else self.code)


# -- data root ---------------------------------------------------------------

class DataRootInsideGitTreeError(CorpusServiceError):
    """The live store is local operational state and never lives in Git."""

    code = "data_root_inside_git_tree"


class DataRootInvalidError(CorpusServiceError):
    code = "data_root_invalid"


class ObjectOverwriteRefusedError(CorpusServiceError):
    """Content-addressed bytes are immutable; a differing write is tampering."""

    code = "object_overwrite_refused"


class ObjectMissingError(CorpusServiceError):
    code = "object_missing"


class ObjectHashMismatchError(CorpusServiceError):
    code = "object_hash_mismatch"


class CorpusArtifactDeletionForbiddenError(CorpusServiceError):
    """Ordinary cleanup must never delete corpus artifacts."""

    code = "corpus_artifact_deletion_forbidden"


# -- ledgers -----------------------------------------------------------------

class LedgerInvalidError(CorpusServiceError):
    code = "corpus_ledger_invalid"


class LedgerChainBrokenError(CorpusServiceError):
    code = "corpus_ledger_chain_broken"


# -- policy and derivation ----------------------------------------------------

class PolicyInvalidError(CorpusServiceError):
    code = "source_rights_policy_invalid"


class PolicyNotHumanAuthoredError(CorpusServiceError):
    """The policy is the human act; a non-human author is not a policy."""

    code = "source_rights_policy_not_human_authored"


class ProcessorWildcardForbiddenError(CorpusServiceError):
    """ADR-0064 stands: no wildcard, no ``any``, no cross-provider inheritance."""

    code = "processor_wildcard_forbidden"


class DerivedDecisionInvalidError(CorpusServiceError):
    code = "derived_rights_decision_invalid"


class DerivedDecisionMissingPolicyHashError(CorpusServiceError):
    """ADR-0072 §7: no policy content hash recorded means refusal."""

    code = "derived_decision_missing_policy_hash"


class DerivedDecisionMissingRuleIdError(CorpusServiceError):
    code = "derived_decision_missing_rule_id"


class DerivedDecisionMissingLicenceInputsError(CorpusServiceError):
    code = "derived_decision_missing_licence_inputs"


class NonHumanDerivedDecisionRefusedError(CorpusServiceError):
    """A decision authored by a model or carrying PROPOSAL still refuses."""

    code = "nonhuman_derived_decision_refused"


# -- snapshot archive and tranche ----------------------------------------------

class ArchiveManifestInvalidError(CorpusServiceError):
    code = "snapshot_archive_manifest_invalid"


class TrancheConfigInvalidError(CorpusServiceError):
    code = "snapshot_tranche_config_invalid"


class TrancheBoundExceededError(CorpusServiceError):
    code = "snapshot_tranche_bound_exceeded"


class ArchiveDocumentMismatchError(CorpusServiceError):
    """Archive bytes that do not hash to their manifest entry are corruption."""

    code = "snapshot_archive_document_mismatch"


class SnapshotAcquisitionNotActiveError(CorpusServiceError):
    """The live snapshot acquisition path is an explicit named gate."""

    code = "snapshot_acquisition_not_active"


class SnapshotActivationInvalidError(CorpusServiceError):
    code = "snapshot_activation_invalid"


# -- snapshot fetcher (ADR-0080) -------------------------------------------------

class SnapshotOriginNotAllowlistedError(CorpusServiceError):
    """A fetch origin outside the pinned allowlist refuses before any request."""

    code = "snapshot_origin_not_allowlisted"


class SnapshotFetchFailedError(CorpusServiceError):
    """A transport failure; recorded in the fetch ledger and resumable."""

    code = "snapshot_fetch_failed"


class SnapshotFetchBoundExceededError(CorpusServiceError):
    """The activation record bounds live acquisition volume."""

    code = "snapshot_fetch_bound_exceeded"


# -- extraction (ADR-0080) --------------------------------------------------------

class ExtractorNotPinnedError(CorpusServiceError):
    """The pinned external extraction tool is absent or differs from its pin."""

    code = "extractor_not_pinned"


class ExtractorRegistryInvalidError(CorpusServiceError):
    code = "extractor_registry_invalid"


# -- silo bridge (ADR-0080) -------------------------------------------------------

class BridgeRecordInvalidError(CorpusServiceError):
    code = "bridge_record_invalid"


class BridgeMetadataFullTextForbiddenError(CorpusServiceError):
    """arXiv descriptive metadata never authorizes full-text storage."""

    code = "bridge_metadata_full_text_forbidden"


# -- spans ---------------------------------------------------------------------

class SpansInvalidError(CorpusServiceError):
    code = "parsed_spans_invalid"


# -- generations and takedown ---------------------------------------------------

class GenerationInvalidError(CorpusServiceError):
    code = "corpus_generation_invalid"


class GenerationOverwriteRefusedError(CorpusServiceError):
    """A generation is immutable; a new one is published, never a mutation."""

    code = "corpus_generation_overwrite_refused"


class GenerationInvalidatedError(CorpusServiceError):
    """A takedown invalidated this generation for active use."""

    code = "corpus_generation_invalidated"


class GenerationMissingError(CorpusServiceError):
    code = "corpus_generation_missing"


class TombstoneInvalidError(CorpusServiceError):
    code = "corpus_tombstone_invalid"


class DocumentAlreadyTombstonedError(CorpusServiceError):
    code = "corpus_document_already_tombstoned"


class DocumentUnknownError(CorpusServiceError):
    code = "corpus_document_unknown"


__all__ = sorted(name for name in dir() if name.endswith("Error"))
