"""One unified campaign budget with per-capability sub-budgets (Slice 2).

Model tokens/cost, embedding tokens and document counts, network bytes, tool
runs, storage growth, and wall time all close over ONE campaign budget.  The
ledger is append-only: every attempted request -- completed, failed,
incomplete, or refused by the provider -- is preserved as a charge event, and
rate-limit observations are retained rather than discarded.  Backoff is a
bounded, deterministic integer schedule, never a rapid reconnect loop and
never a float.

Following the Phase 3B precedent, provider-reported usage, observed costs, and
timestamps are operational observations: they live in the operational hash and
are excluded from the semantic content hash.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Iterable

from .credentials import CampaignRoutePolicy
from .records import (
    CampaignProvenanceError,
    RecordStatus,
    UsageSource,
    canonical_hash,
    public_value,
)


BUDGET_SCHEMA_VERSION = "adaivy.campaign-budget.v1"

#: Structural ceiling on retries so an exponential schedule stays bounded.
#: This is a bound on authorization, not a tuned performance constant.
MAX_RETRY_CEILING = 64


class CampaignBudgetError(CampaignProvenanceError):
    """A budget, charge, or backoff request is malformed or unauthorized."""


class BudgetExhaustedError(CampaignBudgetError):
    """The unified campaign budget admits no further request on this route."""


class BudgetCapability(str, Enum):
    MODEL = "model"
    EMBEDDING = "embedding"
    NETWORK = "network"
    TOOL = "tool"
    STORAGE = "storage"


_QUANTITY_FIELDS = (
    "requests", "input_tokens", "output_tokens", "cost_microusd",
    "bytes_transferred", "documents",
)


def _nonnegative(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CampaignBudgetError(f"{field} must be a non-negative integer")
    return value


def _positive(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CampaignBudgetError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class SubBudget:
    """Exact integer ceilings for one capability.  Zero means none admitted."""

    max_requests: int
    max_input_tokens: int
    max_output_tokens: int
    max_cost_microusd: int
    max_bytes: int
    max_documents: int

    def __post_init__(self) -> None:
        for name in (
            "max_requests", "max_input_tokens", "max_output_tokens",
            "max_cost_microusd", "max_bytes", "max_documents",
        ):
            _nonnegative(getattr(self, name), name)


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignBudget:
    """The one campaign budget frozen at start, with a pinned price snapshot."""

    campaign_id: str
    pricing_snapshot_hash: str
    #: Pinned at start when the campaign's profile names an embedding model.
    #: An embedding route with no pinned embedding price may charge nothing.
    embedding_pricing_snapshot_hash: str | None = None
    max_total_cost_microusd: int
    max_wall_milliseconds: int
    model: SubBudget
    embedding: SubBudget
    network: SubBudget
    tool: SubBudget
    storage: SubBudget
    #: Present only when the frozen route policy names a fallback profile.
    #: A fallback route may charge nothing without its own dedicated budget.
    fallback_model: SubBudget | None = None
    schema_version: str = BUDGET_SCHEMA_VERSION
    record_type: str = "campaign_budget"
    content_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != BUDGET_SCHEMA_VERSION:
            raise CampaignBudgetError("unsupported campaign-budget schema")
        if self.record_type != "campaign_budget":
            raise CampaignBudgetError("unsupported campaign-budget record type")
        if not isinstance(self.campaign_id, str) or not self.campaign_id:
            raise CampaignBudgetError("campaign_id must be a non-empty string")
        if not isinstance(self.pricing_snapshot_hash, str) or not (
            self.pricing_snapshot_hash.startswith("sha256:")
        ):
            raise CampaignBudgetError("pricing_snapshot_hash is not a sha256 content hash")
        if self.embedding_pricing_snapshot_hash is not None and not (
            isinstance(self.embedding_pricing_snapshot_hash, str)
            and self.embedding_pricing_snapshot_hash.startswith("sha256:")
        ):
            raise CampaignBudgetError(
                "embedding_pricing_snapshot_hash is not a sha256 content hash"
            )
        _nonnegative(self.max_total_cost_microusd, "max_total_cost_microusd")
        _nonnegative(self.max_wall_milliseconds, "max_wall_milliseconds")
        for name in ("model", "embedding", "network", "tool", "storage"):
            if not isinstance(getattr(self, name), SubBudget):
                raise CampaignBudgetError(f"{name} must be a SubBudget")
        if self.fallback_model is not None and not isinstance(self.fallback_model, SubBudget):
            raise CampaignBudgetError("fallback_model must be a SubBudget or None")

    def sub_budget(self, capability: BudgetCapability) -> SubBudget:
        return getattr(self, capability.value)

    def finalized(self) -> "CampaignBudget":
        payload = public_value(replace(self, content_hash=""))
        return replace(self, content_hash=canonical_hash(payload))

    def verify_hashes(self) -> None:
        if self.content_hash != self.finalized().content_hash:
            raise CampaignBudgetError("campaign budget content_hash mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class ChargeEvent:
    """One attempted request charged against the unified budget.

    Failed and incomplete attempts are events too: they are preserved, never
    deleted, and a superseding retry is a NEW event rather than a mutation.
    Rate-limit observations travel in the operational hash because they are
    race-dependent observations, not semantic identity.
    """

    sequence: int
    campaign_id: str
    capability: BudgetCapability
    credential_profile_id: str
    purpose: str
    status: RecordStatus
    request_hash: str
    usage_source: UsageSource
    requests: int
    input_tokens: int
    output_tokens: int
    cost_microusd: int
    bytes_transferred: int
    documents: int
    failure_classification: str | None
    rate_limit_retry_after_milliseconds: int | None
    recorded_at: str
    schema_version: str = BUDGET_SCHEMA_VERSION
    record_type: str = "campaign_charge"
    content_hash: str = ""
    operational_hash: str = ""

    OPERATIONAL_FIELDS = frozenset({
        "usage_source", "input_tokens", "output_tokens", "cost_microusd",
        "bytes_transferred", "failure_classification",
        "rate_limit_retry_after_milliseconds", "recorded_at",
    })

    def __post_init__(self) -> None:
        if self.schema_version != BUDGET_SCHEMA_VERSION:
            raise CampaignBudgetError("unsupported charge-event schema")
        if self.record_type != "campaign_charge":
            raise CampaignBudgetError("unsupported charge-event record type")
        _positive(self.sequence, "sequence")
        for field in ("campaign_id", "credential_profile_id", "purpose", "recorded_at"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise CampaignBudgetError(f"{field} must be a non-empty string")
        if not isinstance(self.capability, BudgetCapability):
            raise CampaignBudgetError("capability must be a BudgetCapability")
        if not isinstance(self.status, RecordStatus):
            raise CampaignBudgetError("status must be a RecordStatus")
        if not isinstance(self.usage_source, UsageSource):
            raise CampaignBudgetError("usage_source must be a UsageSource")
        if not isinstance(self.request_hash, str) or not self.request_hash.startswith("sha256:"):
            raise CampaignBudgetError("request_hash is not a sha256 content hash")
        for field in _QUANTITY_FIELDS:
            _nonnegative(getattr(self, field), field)
        _positive(self.requests, "requests")
        if self.rate_limit_retry_after_milliseconds is not None:
            _nonnegative(
                self.rate_limit_retry_after_milliseconds,
                "rate_limit_retry_after_milliseconds",
            )
        if self.failure_classification is not None and not (
            isinstance(self.failure_classification, str) and self.failure_classification
        ):
            raise CampaignBudgetError("failure_classification must be a non-empty string or null")
        if self.status is RecordStatus.COMPLETED and self.failure_classification is not None:
            raise CampaignBudgetError("a completed charge carries no failure classification")
        if self.usage_source is UsageSource.UNAVAILABLE and (
            self.input_tokens or self.output_tokens or self.cost_microusd
        ):
            raise CampaignBudgetError(
                "unavailable usage cannot carry measured tokens or cost"
            )

    def finalized(self) -> "ChargeEvent":
        payload = public_value(replace(self, content_hash="", operational_hash=""))
        semantic = {
            key: item for key, item in payload.items()
            if key not in self.OPERATIONAL_FIELDS
            and key not in {"content_hash", "operational_hash"}
        }
        content_hash = canonical_hash(semantic)
        payload["content_hash"] = content_hash
        payload.pop("operational_hash", None)
        return replace(
            self, content_hash=content_hash, operational_hash=canonical_hash(payload),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityCloseout:
    """Per-capability closing totals and remaining allowances (exact integers)."""

    capability: BudgetCapability
    requests_attempted: int
    requests_completed: int
    requests_failed: int
    requests_incomplete: int
    input_tokens: int
    output_tokens: int
    cost_microusd: int
    bytes_transferred: int
    documents: int
    remaining_requests: int
    remaining_input_tokens: int
    remaining_output_tokens: int
    remaining_cost_microusd: int
    remaining_bytes: int
    remaining_documents: int


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetCloseout:
    """The unified closing statement for one campaign budget.

    ``remaining_*`` values may be negative: an actual usage report can exceed
    the reservation that admitted the request, and hiding the excess would be
    tuning the record to look clean.  ``status`` says so explicitly.
    """

    campaign_id: str
    budget_content_hash: str
    pricing_snapshot_hash: str
    status: str
    exceeded_bounds: tuple[str, ...]
    capabilities: tuple[CapabilityCloseout, ...]
    #: Closing totals for the authorized fallback model route, present exactly
    #: when the budget carries a dedicated ``fallback_model`` sub-budget.
    fallback_model: CapabilityCloseout | None
    total_cost_microusd: int
    remaining_total_cost_microusd: int
    wall_milliseconds_used: int
    remaining_wall_milliseconds: int
    charge_event_count: int
    failure_event_sequences: tuple[int, ...]
    rate_limit_event_sequences: tuple[int, ...]
    recorded_at: str
    schema_version: str = BUDGET_SCHEMA_VERSION
    record_type: str = "campaign_budget_closeout"
    content_hash: str = ""
    operational_hash: str = ""

    OPERATIONAL_FIELDS = frozenset({
        "status", "exceeded_bounds", "capabilities", "fallback_model",
        "total_cost_microusd",
        "remaining_total_cost_microusd", "wall_milliseconds_used",
        "remaining_wall_milliseconds", "charge_event_count",
        "failure_event_sequences", "rate_limit_event_sequences", "recorded_at",
    })

    def finalized(self) -> "BudgetCloseout":
        payload = public_value(replace(self, content_hash="", operational_hash=""))
        semantic = {
            key: item for key, item in payload.items()
            if key not in self.OPERATIONAL_FIELDS
            and key not in {"content_hash", "operational_hash"}
        }
        content_hash = canonical_hash(semantic)
        payload["content_hash"] = content_hash
        payload.pop("operational_hash", None)
        return replace(
            self, content_hash=content_hash, operational_hash=canonical_hash(payload),
        )


class CampaignBudgetLedger:
    """Append-only charge ledger closing over one campaign budget.

    ``admit`` fails closed BEFORE an effect; ``charge`` preserves the attempt
    AFTER the effect even when the observed usage breaches a bound, because a
    paid request that happened must never be discarded.  Once any bound is
    breached the ledger admits nothing further.
    """

    def __init__(
        self,
        budget: CampaignBudget,
        *,
        recorded_at: Callable[[], str],
        route_policy: CampaignRoutePolicy | None = None,
        initial_events: Iterable[ChargeEvent] = (),
        event_sink: Callable[[ChargeEvent], None] | None = None,
    ) -> None:
        budget.verify_hashes()
        if route_policy is not None and route_policy.fallback_profile_id is not None:
            if budget.fallback_model is None:
                raise CampaignBudgetError(
                    "the route policy names a fallback profile but the campaign "
                    "budget carries no dedicated fallback_model sub-budget; a "
                    "fallback route may charge nothing without its own budget"
                )
        self.budget = budget
        self.recorded_at = recorded_at
        self.route_policy = route_policy
        self._fallback_profile_id = (
            route_policy.fallback_profile_id if route_policy is not None else None
        )
        self._events: list[ChargeEvent] = []
        self._totals: dict[BudgetCapability, dict[str, int]] = {
            capability: {field: 0 for field in _QUANTITY_FIELDS}
            for capability in BudgetCapability
        }
        self._fallback_totals: dict[str, int] = {
            field: 0 for field in _QUANTITY_FIELDS
        }
        self._exceeded: list[str] = []
        self._closed = False
        self._event_sink = event_sink
        for event in initial_events:
            if event.campaign_id != budget.campaign_id:
                raise CampaignBudgetError("prior charge belongs to another campaign")
            if event.sequence != len(self._events) + 1:
                raise CampaignBudgetError("prior charge sequence is not contiguous")
            expected = event.finalized()
            if (
                event.content_hash != expected.content_hash
                or event.operational_hash != expected.operational_hash
            ):
                raise CampaignBudgetError("prior charge hash differs")
            if event.capability is BudgetCapability.MODEL:
                bucket_name, _, totals = self._model_bucket(event.credential_profile_id)
            else:
                bucket_name = event.capability.value
                totals = self._totals[event.capability]
            self._events.append(event)
            for field in _QUANTITY_FIELDS:
                totals[field] += getattr(event, field)
            self._note_breaches(bucket_name, totals)

    def _model_bucket(
        self, credential_profile_id: str | None,
    ) -> tuple[str, SubBudget, dict[str, int]]:
        """Which sub-budget a MODEL request charges, keyed by its profile.

        With a route policy, a model request must name the primary or the
        authorized fallback profile; anything else is an unauthorized route
        and fails closed.  Without a policy (or a profile) everything is the
        primary route, preserving the pre-fallback behaviour.
        """

        if credential_profile_id is None or self.route_policy is None:
            return "model", self.budget.model, self._totals[BudgetCapability.MODEL]
        if credential_profile_id == self.route_policy.primary_profile_id:
            return "model", self.budget.model, self._totals[BudgetCapability.MODEL]
        if credential_profile_id == self._fallback_profile_id:
            if self.budget.fallback_model is None:
                raise CampaignBudgetError(
                    "the fallback route has no dedicated fallback_model "
                    "sub-budget and may therefore charge nothing"
                )
            return "fallback_model", self.budget.fallback_model, self._fallback_totals
        raise CampaignBudgetError(
            f"profile {credential_profile_id!r} is neither the primary nor the "
            "authorized fallback route of this campaign's frozen route policy"
        )

    @property
    def events(self) -> tuple[ChargeEvent, ...]:
        return tuple(self._events)

    def admit(
        self,
        capability: BudgetCapability,
        *,
        credential_profile_id: str | None = None,
        requests: int = 1,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_microusd: int = 0,
        bytes_transferred: int = 0,
        documents: int = 0,
    ) -> None:
        """Refuse a request that cannot fit; performs and records nothing."""

        if self._closed:
            raise BudgetExhaustedError("the campaign budget is already closed")
        if self._exceeded:
            raise BudgetExhaustedError(
                "the campaign budget was breached and admits no further "
                "request: " + ", ".join(sorted(set(self._exceeded)))
            )
        _positive(requests, "requests")
        if capability is BudgetCapability.MODEL:
            _, sub, totals = self._model_bucket(credential_profile_id)
        else:
            sub = self.budget.sub_budget(capability)
            totals = self._totals[capability]
        reserved = {
            "requests": requests, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "cost_microusd": cost_microusd,
            "bytes_transferred": bytes_transferred, "documents": documents,
        }
        limits = {
            "requests": sub.max_requests, "input_tokens": sub.max_input_tokens,
            "output_tokens": sub.max_output_tokens,
            "cost_microusd": sub.max_cost_microusd,
            "bytes_transferred": sub.max_bytes, "documents": sub.max_documents,
        }
        for field, amount in reserved.items():
            _nonnegative(amount, field)
            if totals[field] + amount > limits[field]:
                raise BudgetExhaustedError(
                    f"{capability.value} sub-budget admits no further {field}"
                )
        if self._total_cost() + cost_microusd > self.budget.max_total_cost_microusd:
            raise BudgetExhaustedError("the unified campaign cost bound admits no further cost")

    def charge(
        self,
        *,
        capability: BudgetCapability,
        credential_profile_id: str,
        purpose: str,
        status: RecordStatus,
        request_hash: str,
        usage_source: UsageSource,
        requests: int = 1,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_microusd: int = 0,
        bytes_transferred: int = 0,
        documents: int = 0,
        failure_classification: str | None = None,
        rate_limit_retry_after_milliseconds: int | None = None,
    ) -> ChargeEvent:
        if self._closed:
            raise CampaignBudgetError("a closed budget accepts no further charge")
        if capability is BudgetCapability.MODEL:
            # Resolve the bucket BEFORE constructing the event: a fallback
            # profile without its own sub-budget, or a profile outside the
            # frozen route policy, is an unauthorized route and fails closed.
            bucket_name, _, totals = self._model_bucket(credential_profile_id)
        else:
            bucket_name = capability.value
            totals = self._totals[capability]
        event = ChargeEvent(
            sequence=len(self._events) + 1,
            campaign_id=self.budget.campaign_id,
            capability=capability,
            credential_profile_id=credential_profile_id,
            purpose=purpose,
            status=status,
            request_hash=request_hash,
            usage_source=usage_source,
            requests=requests,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_microusd=cost_microusd,
            bytes_transferred=bytes_transferred,
            documents=documents,
            failure_classification=failure_classification,
            rate_limit_retry_after_milliseconds=rate_limit_retry_after_milliseconds,
            recorded_at=self.recorded_at(),
        ).finalized()
        self._events.append(event)
        for field in _QUANTITY_FIELDS:
            totals[field] += getattr(event, field)
        self._note_breaches(bucket_name, totals)
        if self._event_sink is not None:
            self._event_sink(event)
        return event

    def _total_cost(self) -> int:
        return (
            sum(totals["cost_microusd"] for totals in self._totals.values())
            + self._fallback_totals["cost_microusd"]
        )

    def _bucket_limits(self, bucket_name: str) -> SubBudget:
        if bucket_name == "fallback_model":
            assert self.budget.fallback_model is not None
            return self.budget.fallback_model
        return self.budget.sub_budget(BudgetCapability(bucket_name))

    def _note_breaches(self, bucket_name: str, totals: dict[str, int]) -> None:
        sub = self._bucket_limits(bucket_name)
        checks = (
            ("requests", sub.max_requests),
            ("input_tokens", sub.max_input_tokens),
            ("output_tokens", sub.max_output_tokens),
            ("cost_microusd", sub.max_cost_microusd),
            ("bytes_transferred", sub.max_bytes),
            ("documents", sub.max_documents),
        )
        for field, limit in checks:
            if totals[field] > limit:
                self._exceeded.append(f"{bucket_name}.{field}")
        if self._total_cost() > self.budget.max_total_cost_microusd:
            self._exceeded.append("total.cost_microusd")

    def close(self, *, wall_milliseconds_used: int) -> BudgetCloseout:
        _nonnegative(wall_milliseconds_used, "wall_milliseconds_used")
        if self._closed:
            raise CampaignBudgetError("the campaign budget was already closed")
        self._closed = True
        exceeded = list(self._exceeded)
        if wall_milliseconds_used > self.budget.max_wall_milliseconds:
            exceeded.append("total.wall_milliseconds")
        def _closeout(
            capability: BudgetCapability, sub: SubBudget,
            totals: dict[str, int], events: list[ChargeEvent],
        ) -> CapabilityCloseout:
            return CapabilityCloseout(
                capability=capability,
                requests_attempted=totals["requests"],
                requests_completed=sum(
                    item.requests for item in events
                    if item.status is RecordStatus.COMPLETED
                ),
                requests_failed=sum(
                    item.requests for item in events
                    if item.status is RecordStatus.FAILED
                ),
                requests_incomplete=sum(
                    item.requests for item in events
                    if item.status is RecordStatus.INCOMPLETE
                ),
                input_tokens=totals["input_tokens"],
                output_tokens=totals["output_tokens"],
                cost_microusd=totals["cost_microusd"],
                bytes_transferred=totals["bytes_transferred"],
                documents=totals["documents"],
                remaining_requests=sub.max_requests - totals["requests"],
                remaining_input_tokens=sub.max_input_tokens - totals["input_tokens"],
                remaining_output_tokens=sub.max_output_tokens - totals["output_tokens"],
                remaining_cost_microusd=sub.max_cost_microusd - totals["cost_microusd"],
                remaining_bytes=sub.max_bytes - totals["bytes_transferred"],
                remaining_documents=sub.max_documents - totals["documents"],
            )

        def _is_fallback(event: ChargeEvent) -> bool:
            return (
                event.capability is BudgetCapability.MODEL
                and self._fallback_profile_id is not None
                and event.credential_profile_id == self._fallback_profile_id
            )

        capabilities = []
        for capability in BudgetCapability:
            events = [
                item for item in self._events
                if item.capability is capability and not _is_fallback(item)
            ]
            capabilities.append(_closeout(
                capability, self.budget.sub_budget(capability),
                self._totals[capability], events,
            ))
        fallback_closeout = None
        if self.budget.fallback_model is not None:
            fallback_closeout = _closeout(
                BudgetCapability.MODEL, self.budget.fallback_model,
                self._fallback_totals,
                [item for item in self._events if _is_fallback(item)],
            )
        return BudgetCloseout(
            campaign_id=self.budget.campaign_id,
            budget_content_hash=self.budget.content_hash,
            pricing_snapshot_hash=self.budget.pricing_snapshot_hash,
            status="within_bounds" if not exceeded else "exceeded",
            exceeded_bounds=tuple(sorted(set(exceeded))),
            capabilities=tuple(capabilities),
            fallback_model=fallback_closeout,
            total_cost_microusd=self._total_cost(),
            remaining_total_cost_microusd=(
                self.budget.max_total_cost_microusd - self._total_cost()
            ),
            wall_milliseconds_used=wall_milliseconds_used,
            remaining_wall_milliseconds=(
                self.budget.max_wall_milliseconds - wall_milliseconds_used
            ),
            charge_event_count=len(self._events),
            failure_event_sequences=tuple(
                item.sequence for item in self._events
                if item.status is not RecordStatus.COMPLETED
            ),
            rate_limit_event_sequences=tuple(
                item.sequence for item in self._events
                if item.rate_limit_retry_after_milliseconds is not None
            ),
            recorded_at=self.recorded_at(),
        ).finalized()


@dataclass(frozen=True, slots=True, kw_only=True)
class BackoffPolicy:
    """Bounded, deterministic integer backoff.  No floats, no jitter, no loop.

    The delay before retry ``n`` (1-based) is
    ``min(max_delay_milliseconds, base * num**(n-1) // den**(n-1))``.
    """

    base_milliseconds: int
    multiplier_numerator: int
    multiplier_denominator: int
    max_delay_milliseconds: int
    max_retries: int

    def __post_init__(self) -> None:
        _positive(self.base_milliseconds, "base_milliseconds")
        _positive(self.multiplier_numerator, "multiplier_numerator")
        _positive(self.multiplier_denominator, "multiplier_denominator")
        if self.multiplier_numerator < self.multiplier_denominator:
            raise CampaignBudgetError("a backoff multiplier below one is a reconnect loop")
        _positive(self.max_delay_milliseconds, "max_delay_milliseconds")
        if self.max_delay_milliseconds < self.base_milliseconds:
            raise CampaignBudgetError("max_delay_milliseconds must be at least the base delay")
        _nonnegative(self.max_retries, "max_retries")
        if self.max_retries > MAX_RETRY_CEILING:
            raise CampaignBudgetError(
                f"max_retries exceeds the structural ceiling of {MAX_RETRY_CEILING}"
            )


def backoff_delays_milliseconds(policy: BackoffPolicy) -> tuple[int, ...]:
    """The complete deterministic schedule, one exact delay per admitted retry."""

    delays = []
    for attempt in range(policy.max_retries):
        exact = (
            policy.base_milliseconds
            * policy.multiplier_numerator ** attempt
            // policy.multiplier_denominator ** attempt
        )
        delays.append(min(policy.max_delay_milliseconds, exact))
    return tuple(delays)


def next_retry_delay_milliseconds(
    policy: BackoffPolicy,
    *,
    retries_performed: int,
    observed_retry_after_milliseconds: int | None = None,
) -> int | None:
    """The next admitted delay, or ``None`` when the route is terminal.

    A provider-observed ``Retry-After`` can lengthen a wait (never shorten it
    below the schedule) and is itself capped by the policy ceiling; it never
    grants an extra retry.  Note the deliberate consequence: a Retry-After
    ABOVE ``max_delay_milliseconds`` is truncated to the ceiling, so the next
    attempt may fire before the provider asked -- the bounded-wall-time bound
    wins over the provider hint, and the 429 that follows is preserved as
    another recorded observation rather than looped on.
    """

    _nonnegative(retries_performed, "retries_performed")
    if retries_performed >= policy.max_retries:
        return None
    delay = backoff_delays_milliseconds(policy)[retries_performed]
    if observed_retry_after_milliseconds is not None:
        _nonnegative(
            observed_retry_after_milliseconds, "observed_retry_after_milliseconds",
        )
        delay = max(
            delay,
            min(observed_retry_after_milliseconds, policy.max_delay_milliseconds),
        )
    return delay


__all__ = [
    "BUDGET_SCHEMA_VERSION",
    "BackoffPolicy",
    "BudgetCapability",
    "BudgetCloseout",
    "BudgetExhaustedError",
    "CampaignBudget",
    "CampaignBudgetError",
    "CampaignBudgetLedger",
    "CapabilityCloseout",
    "ChargeEvent",
    "MAX_RETRY_CEILING",
    "SubBudget",
    "backoff_delays_milliseconds",
    "next_retry_delay_milliseconds",
]
