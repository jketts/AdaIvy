"""Append-only human steering over the exploration portfolio.

Contract Section 1 item 11 and Section 11: steering appends authorized decisions
and never overwrites prior graph, branch, event, or steering history.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .budget import BudgetPolicy
from .records import identifier, text
from .serialization import canonical_hash, stable_id
from .state import SynthesisValidationError, ValueEnum, parse_enum

# The authority pair a steering principal must hold. Mirrors the Phase 5 gate:
# automation, model, and system principals cannot steer, and a human without
# final authority cannot either.
REQUIRED_ACTOR_KIND = "human"
REQUIRED_AUTHORITY = "human_final"
REQUIRED_CAPABILITY = "steer_research"


class SteeringAction(ValueEnum):
    """Bounded instructions a steering record may carry (ERS-AC-12)."""

    SELECT_BRANCH = "select_branch"
    REBUDGET = "rebudget"
    REDIRECT_OBJECTIVE = "redirect_objective"
    STOP = "stop"


_REQUIRES_TARGET = frozenset({SteeringAction.SELECT_BRANCH.value, SteeringAction.REDIRECT_OBJECTIVE.value})


@dataclass(frozen=True, slots=True, kw_only=True)
class SteeringPrincipal:
    """An authorized steering actor and its capability."""

    principal_id: str
    actor_kind: str
    authority: str
    capability_id: str
    capability_operation: str

    def __post_init__(self) -> None:
        identifier(self.principal_id, field="principal_id")
        identifier(self.capability_id, field="capability_id")

    def authorize(self) -> None:
        """Fail closed unless this is a trusted human-final steering principal."""
        if self.capability_operation != REQUIRED_CAPABILITY:
            raise PermissionError("capability does not authorize the steering operation")
        if self.actor_kind != REQUIRED_ACTOR_KIND or self.authority != REQUIRED_AUTHORITY:
            raise PermissionError("steering requires a trusted human-final principal")

    def value(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "actor_kind": self.actor_kind,
            "authority": self.authority,
            "capability_id": self.capability_id,
            "capability_operation": self.capability_operation,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SteeringRecord:
    """One appended steering decision."""

    steering_id: str
    sequence: int
    action: SteeringAction
    principal_id: str
    capability_id: str
    idempotency_key: str
    causal_predecessor_id: str
    previous_view_identity: str
    target_branch_id: str | None
    target_objective_id: str | None
    instruction: str
    budget_policy_version: str
    semantic_digest: str

    def value(self) -> dict[str, Any]:
        return {
            "steering_id": self.steering_id,
            "sequence": self.sequence,
            "action": self.action.value,
            "principal_id": self.principal_id,
            "capability_id": self.capability_id,
            "idempotency_key": self.idempotency_key,
            "causal_predecessor_id": self.causal_predecessor_id,
            "previous_view_identity": self.previous_view_identity,
            "target_branch_id": self.target_branch_id,
            "target_objective_id": self.target_objective_id,
            "instruction": self.instruction,
            "budget_policy_version": self.budget_policy_version,
            "semantic_digest": self.semantic_digest,
            "effective_actor_kind": REQUIRED_ACTOR_KIND,
            "authority": REQUIRED_AUTHORITY,
            "required_capability": REQUIRED_CAPABILITY,
        }


class SteeringLog:
    """Append-only steering history rooted at an objective."""

    def __init__(self, *, root_id: str, policy: BudgetPolicy) -> None:
        identifier(root_id, field="root_id")
        self.root_id = root_id
        self._policy = policy
        self._records: list[SteeringRecord] = []
        self._by_key: dict[str, SteeringRecord] = {}

    @property
    def policy(self) -> BudgetPolicy:
        """The current effective policy after any appended rebudgets."""
        return self._policy

    def records(self) -> tuple[SteeringRecord, ...]:
        return tuple(self._records)

    def current_view_identity(self) -> str:
        """Identity of the view derived from the immutable record sequence."""
        return canonical_hash(
            {
                "root_id": self.root_id,
                "records": [record.value() for record in self._records],
                "policy": self._policy.value(),
            }
        )

    def append(
        self,
        *,
        principal: SteeringPrincipal,
        action: SteeringAction | str,
        instruction: str,
        idempotency_key: str,
        target_branch_id: str | None = None,
        target_objective_id: str | None = None,
        lowered_bounds: Mapping[str, int] | None = None,
    ) -> SteeringRecord:
        """Append one authorized steering decision.

        An exact retry returns the existing record; a reused key with different
        semantics fails closed. A rebudget may only lower bounds.
        """
        principal.authorize()
        chosen = parse_enum(SteeringAction, action, field="action")
        text(instruction, field="instruction")
        text(idempotency_key, field="idempotency_key")

        needs_target = chosen.value in _REQUIRES_TARGET
        supplied = [item for item in (target_branch_id, target_objective_id) if item is not None]
        if needs_target and len(supplied) != 1:
            raise SynthesisValidationError(f"{chosen.value} requires exactly one target")
        if not needs_target and supplied:
            raise SynthesisValidationError(f"{chosen.value} takes no target")

        if chosen is SteeringAction.REBUDGET:
            if not lowered_bounds:
                raise SynthesisValidationError("a rebudget must lower at least one bound")
        elif lowered_bounds:
            raise SynthesisValidationError("only a rebudget may change bounds")

        # `restrict` refuses any raise, so an unauthorized budget increase cannot
        # be recorded even by an authorized principal.
        candidate_policy = (
            self._policy.restrict(**dict(lowered_bounds)) if lowered_bounds else self._policy
        )

        semantic = canonical_hash(
            {
                "action": chosen.value,
                "capability_id": principal.capability_id,
                "instruction": instruction,
                "lowered_bounds": dict(sorted((lowered_bounds or {}).items())),
                "principal_id": principal.principal_id,
                "target_branch_id": target_branch_id,
                "target_objective_id": target_objective_id,
            }
        )
        existing = self._by_key.get(idempotency_key)
        if existing is not None:
            if existing.semantic_digest != semantic:
                raise SynthesisValidationError(
                    "steering idempotency key reused with different semantics"
                )
            return existing

        sequence = len(self._records) + 1
        predecessor = self._records[-1].steering_id if self._records else self.root_id
        previous_view = self.current_view_identity()
        record = SteeringRecord(
            steering_id=stable_id(
                "steering", {"root_id": self.root_id, "idempotency_key": idempotency_key}
            ),
            sequence=sequence,
            action=chosen,
            principal_id=principal.principal_id,
            capability_id=principal.capability_id,
            idempotency_key=idempotency_key,
            causal_predecessor_id=predecessor,
            previous_view_identity=previous_view,
            target_branch_id=target_branch_id,
            target_objective_id=target_objective_id,
            instruction=instruction,
            budget_policy_version=candidate_policy.policy_version,
            semantic_digest=semantic,
        )
        self._records.append(record)
        self._by_key[idempotency_key] = record
        self._policy = candidate_policy
        return record

    def value(self) -> dict[str, Any]:
        return {
            "root_id": self.root_id,
            "records": [record.value() for record in self._records],
            "effective_policy": self._policy.value(),
            "current_view_identity": self.current_view_identity(),
        }


__all__ = [
    "REQUIRED_ACTOR_KIND",
    "REQUIRED_AUTHORITY",
    "REQUIRED_CAPABILITY",
    "SteeringAction",
    "SteeringLog",
    "SteeringPrincipal",
    "SteeringRecord",
]
