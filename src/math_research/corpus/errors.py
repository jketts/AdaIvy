"""Coded, fail-closed refusals for the ADR-0067 corpus slice.

Every refusal carries a stable ``code``.  The falsifiability probes assert on
the code rather than on a message, so rewording a diagnostic cannot silently
turn a probe into a no-op.  This mirrors :mod:`math_research.embedding.errors`.
"""

from __future__ import annotations


class CorpusError(ValueError):
    """Base refusal. ``code`` is part of the acceptance contract."""

    code = "corpus_error"

    def __init__(self, detail: str = "", *, code: str | None = None) -> None:
        if code is not None:
            self.code = code
        self.detail = detail
        super().__init__(f"{self.code}: {detail}" if detail else self.code)


# -- scope: full text is out of scope and unreachable -----------------------

class FullTextForbiddenError(CorpusError):
    """A request target that could return an e-print rather than metadata."""

    code = "full_text_url_forbidden"


class FullTextTokenOnAcquisitionPathError(CorpusError):
    """A module that can build a request mentions an e-print path."""

    code = "full_text_token_on_acquisition_path"


class OriginNotAuthorizedError(CorpusError):
    code = "origin_not_authorized"


class UnplannedRequestUrlError(CorpusError):
    """A stored request URL the pinned plan does not derive: result following."""

    code = "unplanned_request_url"


class FeedLinkSurfacedError(CorpusError):
    """A parsed entry surfaced a URL taken from the feed rather than derived."""

    code = "feed_link_surfaced"


# -- pinned traffic bounds --------------------------------------------------

class RateLimitViolationError(CorpusError):
    code = "arxiv_rate_limit_violated"


class ConcurrentRequestForbiddenError(CorpusError):
    code = "arxiv_concurrent_request_forbidden"


class ClockNonMonotonicError(CorpusError):
    code = "corpus_clock_not_monotonic"


class RequestBudgetExceededError(CorpusError):
    code = "corpus_request_budget_exceeded"


# -- activation and plan ---------------------------------------------------

class ActivationInvalidError(CorpusError):
    code = "corpus_activation_invalid"


class ActivationNotActiveError(CorpusError):
    code = "corpus_activation_not_active"


class AcknowledgementRequiredError(CorpusError):
    code = "corpus_acknowledgement_required"


class PlanInvalidError(CorpusError):
    code = "corpus_plan_invalid"


class PlanHashMismatchError(CorpusError):
    code = "corpus_plan_hash_mismatch"


class TrancheBoundExceededError(CorpusError):
    code = "tranche_record_bound_exceeded"


class TermsReviewStaleError(CorpusError):
    code = "corpus_terms_review_stale_or_future"


# -- stored bytes and replay ----------------------------------------------

class StoredResponseMissingError(CorpusError):
    """Replay never re-fetches; absent bytes are a refusal."""

    code = "stored_response_missing"


class StoredResponseHashMismatchError(CorpusError):
    code = "stored_response_hash_mismatch"


class StoreOverwriteRefusedError(CorpusError):
    code = "stored_response_overwrite_refused"


class ManifestInvalidError(CorpusError):
    code = "corpus_store_manifest_invalid"


class ManifestHashMismatchError(CorpusError):
    code = "corpus_store_manifest_hash_mismatch"


class TransportCallDuringReplayError(CorpusError):
    code = "transport_call_during_replay"


class TransportCallForbiddenError(CorpusError):
    """Raised by the forbidding transport; the replay path never reaches it."""

    code = "transport_call_forbidden"


# -- feed parsing ---------------------------------------------------------

class FeedBytesInvalidError(CorpusError):
    code = "corpus_feed_bytes_invalid"


class XmlDeclarationForbiddenError(CorpusError):
    """No DOCTYPE, entity declaration, comment or CDATA on the parse path."""

    code = "xml_declaration_forbidden"


class FeedStructureInvalidError(CorpusError):
    code = "corpus_feed_structure_invalid"


class EntryIdNotCanonicalError(CorpusError):
    code = "corpus_entry_id_not_canonical"


class CategoryNotMathematicsError(CorpusError):
    code = "corpus_category_not_mathematics"


# -- rights ---------------------------------------------------------------

class DocumentRightsAbsentError(CorpusError):
    """No per-document Phase 4A decision: the archive licence is only a ceiling."""

    code = "corpus_document_rights_absent"


class DisclosingRightsUseForbiddenError(CorpusError):
    """This slice never requests a use that discloses text to a processor."""

    code = "corpus_disclosing_rights_use_forbidden"


class RightsShardBoundExceededError(CorpusError):
    code = "corpus_rights_shard_bound_exceeded"


# -- trust promotion ------------------------------------------------------

class ApplicabilityPromotionForbiddenError(CorpusError):
    code = "corpus_applicability_promotion_forbidden"


class WarrantPromotionForbiddenError(CorpusError):
    code = "corpus_warrant_promotion_forbidden"


class RetrievalScopeClaimForbiddenError(CorpusError):
    """A corpus is not retrieval; a report may not claim Phase 4C reads it."""

    code = "retrieval_scope_claim_forbidden"


class ApplicabilityCountInconsistentError(CorpusError):
    code = "applicability_count_inconsistent"


# -- projection -----------------------------------------------------------

class AbstractLinkMissingError(CorpusError):
    """The terms oblige every surfaced record to link to its abstract page."""

    code = "abstract_link_missing"


class QuotationBoundExceededError(CorpusError):
    code = "abstract_reproduction_exceeds_fair_quotation"


class ProjectionInvalidError(CorpusError):
    code = "corpus_projection_invalid"


class RecordInvalidError(CorpusError):
    code = "corpus_record_invalid"


class ReportInvalidError(CorpusError):
    code = "corpus_report_invalid"


__all__ = [
    "AbstractLinkMissingError",
    "AcknowledgementRequiredError",
    "ActivationInvalidError",
    "ActivationNotActiveError",
    "ApplicabilityCountInconsistentError",
    "ApplicabilityPromotionForbiddenError",
    "CategoryNotMathematicsError",
    "ClockNonMonotonicError",
    "ConcurrentRequestForbiddenError",
    "CorpusError",
    "DisclosingRightsUseForbiddenError",
    "DocumentRightsAbsentError",
    "EntryIdNotCanonicalError",
    "FeedBytesInvalidError",
    "FeedLinkSurfacedError",
    "FeedStructureInvalidError",
    "FullTextForbiddenError",
    "FullTextTokenOnAcquisitionPathError",
    "ManifestHashMismatchError",
    "ManifestInvalidError",
    "OriginNotAuthorizedError",
    "PlanHashMismatchError",
    "PlanInvalidError",
    "ProjectionInvalidError",
    "QuotationBoundExceededError",
    "RateLimitViolationError",
    "RecordInvalidError",
    "ReportInvalidError",
    "RequestBudgetExceededError",
    "RetrievalScopeClaimForbiddenError",
    "RightsShardBoundExceededError",
    "StoreOverwriteRefusedError",
    "StoredResponseHashMismatchError",
    "StoredResponseMissingError",
    "TermsReviewStaleError",
    "TrancheBoundExceededError",
    "TransportCallDuringReplayError",
    "TransportCallForbiddenError",
    "UnplannedRequestUrlError",
    "WarrantPromotionForbiddenError",
    "XmlDeclarationForbiddenError",
]
