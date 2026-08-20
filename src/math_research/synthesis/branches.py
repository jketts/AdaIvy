"""Finite exploration portfolio with exact duplicate-attempt prevention.

Contract Section 7. Branch transitions are append-only, abandoned attempts stay
addressable, and the exact duplicate key cannot be re-enqueued without an
authorized retry that identifies changed inputs or policy.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import CANONICALIZATION_VERSION, DUPLICATE_KEY_VERSION
from .budget import BudgetExhausted, BudgetLedger, BudgetPolicy
from .records import identifier, text, text_tuple
from .serialization import canonical_hash, stable_id
from .state import StrategyFamily, SynthesisValidationError, ValueEnum, parse_enum, validate_terminal_reason


class BranchState(ValueEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    ABANDONED = "abandoned"
    COMPLETED = "completed"
    BLOCKED = "blocked"


# Append-only transitions still need a legal-successor rule, otherwise a branch
# could move from a terminal state back into work without a retry record.
_ALLOWED_TRANSITIONS: Mapping[str, frozenset[str]] = {
    BranchState.PROPOSED.value: frozenset({BranchState.ACTIVE.value, BranchState.BLOCKED.value, BranchState.ABANDONED.value}),
    BranchState.ACTIVE.value: frozenset({BranchState.COMPLETED.value, BranchState.ABANDONED.value, BranchState.BLOCKED.value}),
    BranchState.BLOCKED.value: frozenset({BranchState.ACTIVE.value, BranchState.ABANDONED.value}),
    BranchState.ABANDONED.value: frozenset(),
    BranchState.COMPLETED.value: frozenset(),
}


def normalize_hypothesis(value: str) -> str:
    """Named canonicalization for a hypothesis before digesting it.

    NFC, casefold, and whitespace collapse, so trivial restatements produce the
    same digest and therefore the same duplicate key. This is exact-identity
    normalization only; genuine semantic equivalence is never inferred here.
    """
    text(value, field="hypothesis")
    folded = unicodedata.normalize("NFC", value).casefold()
    return " ".join(folded.split())


def normalized_hypothesis_digest(value: str) -> str:
    return canonical_hash(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "normalized_hypothesis": normalize_hypothesis(value),
        }
    )


def constraint_configuration_digest(configuration: Mapping[str, Any]) -> str:
    if not isinstance(configuration, Mapping):
        raise SynthesisValidationError("constraint configuration must be an object")
    return canonical_hash(
        {"canonicalization_version": CANONICALIZATION_VERSION, "configuration": dict(configuration)}
    )


def duplicate_attempt_key(
    *,
    hypothesis_digest: str,
    parent_branch_identity: str | None,
    strategy_family: StrategyFamily | str,
    input_graph_snapshot_identity: str,
    constraint_digest: str,
) -> str:
    """The Section 7 exact duplicate-attempt key.

    `H(normalized_hypothesis_digest, parent_branch_identity,
    strategy_family_identity, input_graph_snapshot_identity,
    constraint_configuration_digest)` under the named canonicalization and hash
    versions, both of which are inputs so a version change yields a new key.
    """
    family = parse_enum(StrategyFamily, strategy_family, field="strategy_family")
    return canonical_hash(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "constraint_configuration_digest": constraint_digest,
            "duplicate_key_version": DUPLICATE_KEY_VERSION,
            "input_graph_snapshot_identity": input_graph_snapshot_identity,
            "normalized_hypothesis_digest": hypothesis_digest,
            "parent_branch_identity": parent_branch_identity,
            "strategy_family_identity": family.value,
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class Branch:
    """One attempt in the finite portfolio (Section 7)."""

    branch_id: str
    parent_branch_id: str | None
    strategy_family: StrategyFamily
    hypothesis: str
    objective_delta: str
    required_evidence: tuple[str, ...]
    falsification_conditions: tuple[str, ...]
    depth: int
    budget_policy_version: str
    duplicate_key: str
    state: BranchState
    confidence_proposal: str
    failure_detail: str
    discoveries: tuple[str, ...]
    stop_reason: str | None

    def __post_init__(self) -> None:
        identifier(self.branch_id, field="branch_id")
        if self.parent_branch_id is not None:
            identifier(self.parent_branch_id, field="parent_branch_id")
            if self.parent_branch_id == self.branch_id:
                raise SynthesisValidationError("a branch cannot be its own parent")
        text(self.hypothesis, field="hypothesis")
        text(self.objective_delta, field="objective_delta")
        text(self.confidence_proposal, field="confidence_proposal")
        if self.depth < 0:
            raise SynthesisValidationError("branch depth must be zero or positive")
        if (self.parent_branch_id is None) != (self.depth == 0):
            raise SynthesisValidationError("a root branch has depth zero and no parent")
        # Section 7: every branch records its falsification conditions. A branch
        # with none could never be refuted, which defeats the falsification-first
        # requirement.
        if not self.falsification_conditions:
            raise SynthesisValidationError("a branch must declare its falsification conditions")
        if self.stop_reason is not None:
            validate_terminal_reason(self.stop_reason)

    def value(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "parent_branch_id": self.parent_branch_id,
            "strategy_family": self.strategy_family.value,
            "hypothesis": self.hypothesis,
            "objective_delta": self.objective_delta,
            "required_evidence": list(self.required_evidence),
            "falsification_conditions": list(self.falsification_conditions),
            "depth": self.depth,
            "budget_policy_version": self.budget_policy_version,
            "duplicate_key": self.duplicate_key,
            "state": self.state.value,
            "confidence_proposal": self.confidence_proposal,
            "failure_detail": self.failure_detail,
            "discoveries": list(self.discoveries),
            "stop_reason": self.stop_reason,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class BranchTransition:
    """An append-only state transition for one branch."""

    transition_id: str
    branch_id: str
    from_state: BranchState
    to_state: BranchState
    reason: str
    actor_id: str
    sequence: int

    def value(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "branch_id": self.branch_id,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "reason": self.reason,
            "actor_id": self.actor_id,
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryAuthorization:
    """An authorized retry identifying changed inputs or policy (Section 7)."""

    retry_id: str
    original_branch_id: str
    changed_field: str
    previous_value: str
    new_value: str
    authorized_by: str

    CHANGEABLE = frozenset(
        {
            "hypothesis",
            "strategy_family",
            "input_graph_snapshot_identity",
            "constraint_configuration",
            "budget_policy",
        }
    )

    def __post_init__(self) -> None:
        identifier(self.original_branch_id, field="original_branch_id")
        identifier(self.authorized_by, field="authorized_by")
        if self.changed_field not in self.CHANGEABLE:
            raise SynthesisValidationError(
                f"a retry must identify a changed input or policy from: "
                f"{', '.join(sorted(self.CHANGEABLE))}"
            )
        if self.previous_value == self.new_value:
            raise SynthesisValidationError("a retry must identify an actual change")

    def value(self) -> dict[str, Any]:
        return {
            "retry_id": self.retry_id,
            "original_branch_id": self.original_branch_id,
            "changed_field": self.changed_field,
            "previous_value": self.previous_value,
            "new_value": self.new_value,
            "authorized_by": self.authorized_by,
        }


class DuplicateAttemptRejected(SynthesisValidationError):
    """An exact duplicate key was re-enqueued without an authorized retry."""

    def __init__(self, duplicate_key: str, existing_branch_id: str) -> None:
        self.duplicate_key = duplicate_key
        self.existing_branch_id = existing_branch_id
        super().__init__(
            f"exact duplicate attempt key already enqueued as {existing_branch_id}; "
            "an authorized retry must identify changed inputs or policy"
        )


class BranchPortfolio:
    """A finite portfolio enforcing exact duplicate prevention.

    Holds no mutable branch state: every change appends a new `Branch` snapshot
    plus a `BranchTransition`, and prior snapshots stay addressable.
    """

    def __init__(self, policy: BudgetPolicy) -> None:
        self.policy = policy
        self.ledger = BudgetLedger(policy)
        self._branches: dict[str, Branch] = {}
        self._by_key: dict[str, str] = {}
        self._transitions: list[BranchTransition] = []
        self._retries: dict[str, RetryAuthorization] = {}
        self._history: list[Branch] = []

    def branches(self) -> tuple[Branch, ...]:
        """Current snapshot of every branch, including abandoned ones."""
        return tuple(self._branches[key] for key in sorted(self._branches))

    def history(self) -> tuple[Branch, ...]:
        """Every snapshot ever appended, in append order."""
        return tuple(self._history)

    def transitions(self) -> tuple[BranchTransition, ...]:
        return tuple(self._transitions)

    def retries(self) -> tuple[RetryAuthorization, ...]:
        return tuple(self._retries[key] for key in sorted(self._retries))

    def get(self, branch_id: str) -> Branch:
        """Abandoned attempts remain addressable by identity."""
        if branch_id not in self._branches:
            raise KeyError(branch_id)
        return self._branches[branch_id]

    def find_by_key(self, duplicate_key: str) -> Branch | None:
        existing = self._by_key.get(duplicate_key)
        return None if existing is None else self._branches[existing]

    def _consume_creation_budget(self) -> None:
        """Atomically charge the two counters guarded by branch creation."""
        counters = ("branch_generation_attempts", "branch_count")
        for counter in counters:
            if self.ledger.remaining(counter) < 1:
                raise BudgetExhausted(counter)
        for counter in counters:
            self.ledger.consume(counter)

    def enqueue(
        self,
        *,
        hypothesis: str,
        strategy_family: StrategyFamily | str,
        objective_delta: str,
        falsification_conditions: Sequence[str],
        input_graph_snapshot_identity: str,
        constraint_configuration: Mapping[str, Any],
        required_evidence: Sequence[str] = (),
        parent_branch_id: str | None = None,
        confidence_proposal: str = "non-authoritative proposal",
        retry: RetryAuthorization | None = None,
    ) -> Branch:
        """Enqueue an attempt, refusing an exact duplicate key.

        A retry is accepted only when it changes an input or policy, which by
        construction produces a different key.
        """
        family = parse_enum(StrategyFamily, strategy_family, field="strategy_family")
        depth = 0 if parent_branch_id is None else self.get(parent_branch_id).depth + 1
        if depth > self.policy.branch_depth:
            raise SynthesisValidationError(
                f"branch depth {depth} exceeds the bound {self.policy.branch_depth}"
            )
        key = duplicate_attempt_key(
            hypothesis_digest=normalized_hypothesis_digest(hypothesis),
            parent_branch_identity=parent_branch_id,
            strategy_family=family,
            input_graph_snapshot_identity=input_graph_snapshot_identity,
            constraint_digest=constraint_configuration_digest(constraint_configuration),
        )
        existing = self._by_key.get(key)
        if existing is not None:
            # Section 7: the same key cannot be enqueued again. A retry that did
            # not actually change an input lands here too, because an unchanged
            # input yields the same key.
            raise DuplicateAttemptRejected(key, existing)

        branch_id = stable_id("branch", {"duplicate_key": key})
        branch = Branch(
            branch_id=branch_id,
            parent_branch_id=parent_branch_id,
            strategy_family=family,
            hypothesis=hypothesis,
            objective_delta=objective_delta,
            required_evidence=text_tuple(list(required_evidence), field="required_evidence"),
            falsification_conditions=text_tuple(
                list(falsification_conditions), field="falsification_conditions"
            ),
            depth=depth,
            budget_policy_version=self.policy.policy_version,
            duplicate_key=key,
            state=BranchState.PROPOSED,
            confidence_proposal=confidence_proposal,
            failure_detail="",
            discoveries=(),
            stop_reason=None,
        )
        if retry is not None:
            if retry.original_branch_id not in self._branches:
                raise SynthesisValidationError("a retry must reference an existing branch")
        # Section 5: charge every branch creation before any append-only state
        # is changed. Preflight makes the two-counter charge atomic.
        self._consume_creation_budget()
        if retry is not None:
            self._retries[retry.retry_id] = retry
        self._branches[branch_id] = branch
        self._by_key[key] = branch_id
        self._history.append(branch)
        return branch

    def transition(
        self,
        branch_id: str,
        *,
        to_state: BranchState | str,
        reason: str,
        actor_id: str,
        failure_detail: str = "",
        discoveries: Sequence[str] = (),
        stop_reason: str | None = None,
    ) -> Branch:
        """Append a transition. Prior snapshots are never modified."""
        current = self.get(branch_id)
        target = parse_enum(BranchState, to_state, field="to_state")
        allowed = _ALLOWED_TRANSITIONS[current.state.value]
        if target.value not in allowed:
            raise SynthesisValidationError(
                f"branch {branch_id} cannot move from {current.state.value} to {target.value}"
            )
        identifier(actor_id, field="actor_id")
        text(reason, field="reason")
        updated = Branch(
            branch_id=current.branch_id,
            parent_branch_id=current.parent_branch_id,
            strategy_family=current.strategy_family,
            hypothesis=current.hypothesis,
            objective_delta=current.objective_delta,
            required_evidence=current.required_evidence,
            falsification_conditions=current.falsification_conditions,
            depth=current.depth,
            budget_policy_version=current.budget_policy_version,
            duplicate_key=current.duplicate_key,
            state=target,
            confidence_proposal=current.confidence_proposal,
            failure_detail=failure_detail or current.failure_detail,
            # Section 7 and the general rule that failures are preserved:
            # discoveries accumulate and are never dropped on a later transition.
            discoveries=current.discoveries
            + text_tuple(list(discoveries), field="discoveries"),
            stop_reason=stop_reason if stop_reason is not None else current.stop_reason,
        )
        # Section 5 has no separate transition bound, so transitions consume
        # the named branch-generation-attempt counter before history changes.
        self.ledger.consume("branch_generation_attempts")
        sequence = len(self._transitions) + 1
        self._transitions.append(
            BranchTransition(
                transition_id=stable_id(
                    "branch-transition",
                    {"branch_id": branch_id, "to_state": target.value, "sequence": sequence},
                ),
                branch_id=branch_id,
                from_state=current.state,
                to_state=target,
                reason=reason,
                actor_id=actor_id,
                sequence=sequence,
            )
        )
        self._branches[branch_id] = updated
        self._history.append(updated)
        return updated

    def value(self) -> dict[str, Any]:
        return {
            "duplicate_key_version": DUPLICATE_KEY_VERSION,
            "branches": [branch.value() for branch in self.branches()],
            "transitions": [item.value() for item in self.transitions()],
            "retry_authorizations": [item.value() for item in self.retries()],
            "budget_ledger": self.ledger.ledger_value(),
        }


__all__ = [
    "Branch",
    "BranchPortfolio",
    "BranchState",
    "BranchTransition",
    "DuplicateAttemptRejected",
    "RetryAuthorization",
    "constraint_configuration_digest",
    "duplicate_attempt_key",
    "normalize_hypothesis",
    "normalized_hypothesis_digest",
]
