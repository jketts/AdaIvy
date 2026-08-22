"""Profile-bound gateway wrappers: every campaign AI call crosses one boundary.

`ProfileBoundModelGateway` satisfies `phase2.ports.ModelGateway` and
`ProfileBoundEmbeddingGateway` satisfies `embedding.ports.EmbeddingGateway`, so
existing adapters (the campaign planner, embedding ingestion) can route through
a selected credential profile without any change to their own contracts.

Each completed, failed, or incomplete request becomes exactly one append-only
`ChargeEvent` on the ONE campaign budget ledger, stamped with the credential
profile identifier and the declared purpose.  A response whose provider or
model identity differs from the selected profile is a routing violation:
the mismatch is preserved as a failed charge and then raised, because a
campaign path must never silently accept another provider's answer.  Records
carry identifiers and hashes only; a configured secret value appearing in a
serialized event is itself a refusal.
"""

from __future__ import annotations

from ..embedding.records import EmbeddingRequest, EmbeddingResult
from ..phase2.ports import ModelGateway
from ..phase2.pricing import estimate_cost_microusd
from ..phase2.records import (
    ModelRequest,
    ModelResult,
    ModelResultStatus,
    PricingSnapshot,
    ProviderSchemaPreparation,
)
from .budget import BudgetCapability, CampaignBudgetLedger
from .credentials import (
    CredentialProfile,
    CredentialProfileError,
    ProfileSelectionRecord,
    assert_no_secret_values,
)
from .records import RecordStatus, UsageSource, canonical_hash


class ProfileRoutingError(CredentialProfileError):
    """A campaign call tried to cross the boundary outside its profile."""


def _require_matching_selection(
    profile: CredentialProfile, selection: ProfileSelectionRecord,
) -> None:
    profile.verify_hashes()
    selection.verify_hashes()
    if (
        selection.profile_id != profile.profile_id
        or selection.profile_content_hash != profile.content_hash
        or selection.provider != profile.provider
    ):
        raise ProfileRoutingError(
            "the recorded profile selection does not match the supplied profile"
        )


def _require_matching_pricing(
    profile: CredentialProfile, pricing: PricingSnapshot, *, model_identifier: str,
) -> None:
    if pricing.provider != profile.provider or pricing.model_identifier != model_identifier:
        raise ProfileRoutingError(
            "the pinned pricing snapshot does not price the profile's route"
        )


def _model_status(status: ModelResultStatus) -> RecordStatus:
    if status is ModelResultStatus.SUCCEEDED:
        return RecordStatus.COMPLETED
    if status in {ModelResultStatus.INCOMPLETE, ModelResultStatus.TIMED_OUT}:
        return RecordStatus.INCOMPLETE
    return RecordStatus.FAILED


class ProfileBoundModelGateway:
    """Wrap a Phase 2 model gateway inside one selected credential profile."""

    def __init__(
        self,
        *,
        profile: CredentialProfile,
        selection: ProfileSelectionRecord,
        gateway: ModelGateway,
        pricing: PricingSnapshot,
        ledger: CampaignBudgetLedger,
        secret_values: tuple[str, ...] = (),
    ) -> None:
        _require_matching_selection(profile, selection)
        _require_matching_pricing(
            profile, pricing, model_identifier=profile.model_identifier,
        )
        if pricing.content_hash != ledger.budget.pricing_snapshot_hash:
            raise ProfileRoutingError(
                "the supplied pricing snapshot is not the one pinned by the "
                "campaign budget"
            )
        self.profile = profile
        self.selection = selection
        self.gateway = gateway
        self.pricing = pricing
        self.ledger = ledger
        self.secret_values = secret_values

    def prepare(self, request: ModelRequest) -> ProviderSchemaPreparation | None:
        return self.gateway.prepare(request)

    def complete(
        self,
        request: ModelRequest,
        preparation: ProviderSchemaPreparation | None = None,
    ) -> ModelResult:
        if not isinstance(request.purpose, str) or not request.purpose:
            raise ProfileRoutingError("a campaign model call requires a declared purpose")
        request_hash = canonical_hash({
            "request_id": request.request_id.value,
            "run_id": request.run_id.value,
            "purpose": request.purpose,
            "template_hash": request.template_hash,
            "serialized_context_hash": canonical_hash(request.serialized_context),
            "response_schema_hash": canonical_hash(request.response_schema),
            "max_output_tokens": request.max_output_tokens,
        })
        # Fail closed BEFORE the effect: an exhausted budget performs no call.
        self.ledger.admit(BudgetCapability.MODEL, requests=1)
        result = self.gateway.complete(request, preparation)

        identity_matches = (
            result.provider == self.profile.provider
            and result.model_identifier == self.profile.model_identifier
        )
        status = _model_status(result.status)
        usage_reported = result.usage.usage_source == "api_reported"
        cost = (
            estimate_cost_microusd(
                self.pricing,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
            )
            if usage_reported else 0
        )
        failure = result.provider_failure
        rate_limited = failure is not None and failure.http_status_code == 429
        classification: str | None = None
        if not identity_matches:
            status = RecordStatus.FAILED
            classification = "profile_identity_mismatch"
        elif status is not RecordStatus.COMPLETED:
            classification = result.retry_classification or "unclassified_failure"
        event = self.ledger.charge(
            capability=BudgetCapability.MODEL,
            credential_profile_id=self.profile.profile_id,
            purpose=request.purpose,
            status=status,
            request_hash=request_hash,
            usage_source=(
                UsageSource.API_REPORTED if usage_reported else UsageSource.UNAVAILABLE
            ),
            input_tokens=result.usage.input_tokens if usage_reported else 0,
            output_tokens=result.usage.output_tokens if usage_reported else 0,
            cost_microusd=cost,
            failure_classification=classification,
            rate_limit_retry_after_milliseconds=0 if rate_limited else None,
        )
        assert_no_secret_values(event, self.secret_values)
        if not identity_matches:
            raise ProfileRoutingError(
                "the provider response identity does not match the selected "
                f"credential profile {self.profile.profile_id!r}; the mismatch "
                "was preserved as a failed charge and the route is refused"
            )
        return result


class ProfileBoundEmbeddingGateway:
    """Wrap an ADR-0069 embedding gateway inside the same selected profile."""

    def __init__(
        self,
        *,
        profile: CredentialProfile,
        selection: ProfileSelectionRecord,
        gateway: object,
        pricing: PricingSnapshot,
        ledger: CampaignBudgetLedger,
        purpose: str,
        secret_values: tuple[str, ...] = (),
    ) -> None:
        _require_matching_selection(profile, selection)
        if profile.embedding_model_identifier is None:
            raise ProfileRoutingError(
                f"profile {profile.profile_id!r} names no embedding model; an "
                "embedding call through it is refused rather than re-routed"
            )
        _require_matching_pricing(
            profile, pricing, model_identifier=profile.embedding_model_identifier,
        )
        if pricing.content_hash != ledger.budget.embedding_pricing_snapshot_hash:
            raise ProfileRoutingError(
                "the supplied embedding pricing snapshot is not the one pinned "
                "by the campaign budget"
            )
        if not isinstance(purpose, str) or not purpose:
            raise ProfileRoutingError("a campaign embedding route requires a declared purpose")
        self.profile = profile
        self.selection = selection
        self.gateway = gateway
        self.pricing = pricing
        self.ledger = ledger
        self.purpose = purpose
        self.secret_values = secret_values

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        request_hash = canonical_hash({
            "document_id": request.document_id,
            "source_id": request.source_id,
            "source_content_hash": request.source_content_hash,
            "text_hash": canonical_hash(request.text),
            "processor_id": request.processor_id,
            "max_input_tokens": request.max_input_tokens,
        })
        self.ledger.admit(BudgetCapability.EMBEDDING, requests=1, documents=1)
        result = self.gateway.embed(request)

        identity_matches = (
            result.provider == self.profile.provider
            and result.model_identifier == self.profile.embedding_model_identifier
        )
        usage_reported = result.usage.usage_source == "api_reported"
        cost = (
            estimate_cost_microusd(
                self.pricing,
                input_tokens=result.usage.input_tokens,
                output_tokens=0,
            )
            if usage_reported else 0
        )
        event = self.ledger.charge(
            capability=BudgetCapability.EMBEDDING,
            credential_profile_id=self.profile.profile_id,
            purpose=self.purpose,
            status=(
                RecordStatus.COMPLETED if identity_matches else RecordStatus.FAILED
            ),
            request_hash=request_hash,
            usage_source=(
                UsageSource.API_REPORTED if usage_reported else UsageSource.UNAVAILABLE
            ),
            input_tokens=result.usage.input_tokens if usage_reported else 0,
            cost_microusd=cost,
            documents=1,
            failure_classification=(
                None if identity_matches else "profile_identity_mismatch"
            ),
        )
        assert_no_secret_values(event, self.secret_values)
        if not identity_matches:
            raise ProfileRoutingError(
                "the embedding response identity does not match the selected "
                f"credential profile {self.profile.profile_id!r}; the mismatch "
                "was preserved as a failed charge and the route is refused"
            )
        return result


__all__ = [
    "ProfileBoundEmbeddingGateway",
    "ProfileBoundModelGateway",
    "ProfileRoutingError",
]
