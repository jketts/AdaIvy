"""Mandatory finite run bounds and the enforceable exploration reserve.

Contract Section 5 and 5.1. Every bound is validated before a run begins, no
component may raise a bound, and every loop body or branch transition consumes a
named counter before the work it guards executes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .state import StrategyFamily, SynthesisValidationError, budget_exhausted, parse_enum

# Section 5: these maxima must be positive integers. Each name carries its unit
# explicitly, so a unitless bound cannot be supplied.
POSITIVE_BOUNDS: tuple[str, ...] = (
    "retrieval_iterations",
    "citation_dependency_hops",
    "query_fan_out",
    "results_per_query",
    "unique_discovered_sources",
    "graph_nodes",
    "graph_edges",
    "branch_count",
    "branch_generation_attempts",
    "wall_clock_seconds",
)

# Section 5: these maxima may be zero or a positive integer. Zero disables the
# capability rather than meaning "unbounded".
ZERO_OR_POSITIVE_BOUNDS: tuple[str, ...] = (
    "acquired_sources",
    "acquired_bytes",
    "branch_depth",
    "model_calls",
    "tool_calls",
)

RESERVE_FIELDS: tuple[str, ...] = (
    "exploration_reserve_numerator",
    "exploration_reserve_denominator",
)

BOUND_FIELDS: frozenset[str] = frozenset(POSITIVE_BOUNDS + ZERO_OR_POSITIVE_BOUNDS + RESERVE_FIELDS)


class BudgetExhausted(SynthesisValidationError):
    """A named counter reached its bound. Carries the terminal reason."""

    def __init__(self, counter: str) -> None:
        self.counter = counter
        self.terminal_reason = budget_exhausted(counter)
        super().__init__(self.terminal_reason)


def _strict_int(value: object, *, field: str) -> int:
    """Reject Boolean, non-integer, and non-finite values.

    `bool` is checked before `int` because `bool` is a subclass of `int` in
    Python and `True` would otherwise pass as 1.
    """
    if isinstance(value, bool):
        raise SynthesisValidationError(f"{field} must be an integer, not a Boolean")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SynthesisValidationError(f"{field} must be finite")
        raise SynthesisValidationError(f"{field} must be an integer, not a float")
    if not isinstance(value, int):
        raise SynthesisValidationError(f"{field} must be an integer")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class BudgetPolicy:
    """One validated, versioned budget policy. Immutable by construction."""

    policy_version: str
    retrieval_iterations: int
    citation_dependency_hops: int
    query_fan_out: int
    results_per_query: int
    unique_discovered_sources: int
    graph_nodes: int
    graph_edges: int
    branch_count: int
    branch_generation_attempts: int
    wall_clock_seconds: int
    acquired_sources: int
    acquired_bytes: int
    branch_depth: int
    model_calls: int
    tool_calls: int
    exploration_reserve_numerator: int
    exploration_reserve_denominator: int

    def __post_init__(self) -> None:
        if not self.policy_version:
            raise SynthesisValidationError("budget policy requires an explicit version")
        for field in POSITIVE_BOUNDS:
            value = _strict_int(getattr(self, field), field=field)
            if value <= 0:
                raise SynthesisValidationError(f"{field} must be a positive integer")
        for field in ZERO_OR_POSITIVE_BOUNDS:
            value = _strict_int(getattr(self, field), field=field)
            if value < 0:
                raise SynthesisValidationError(f"{field} must be zero or a positive integer")
        # Section 5: acquired_sources and acquired_bytes are zero if and only if
        # both are zero. One-sided acquisition bounds are internally inconsistent.
        if (self.acquired_sources == 0) != (self.acquired_bytes == 0):
            raise SynthesisValidationError(
                "acquired_sources and acquired_bytes are zero if and only if both are zero"
            )
        numerator = _strict_int(self.exploration_reserve_numerator, field=RESERVE_FIELDS[0])
        denominator = _strict_int(self.exploration_reserve_denominator, field=RESERVE_FIELDS[1])
        if denominator <= 0:
            raise SynthesisValidationError("exploration_reserve_denominator must be positive")
        if not 0 < numerator < denominator:
            raise SynthesisValidationError(
                "exploration reserve requires 0 < numerator < denominator"
            )

    @classmethod
    def from_value(cls, value: object) -> BudgetPolicy:
        """Strict parse. Missing or unknown fields both fail closed."""
        if not isinstance(value, Mapping):
            raise SynthesisValidationError("budget policy must be an object")
        expected = BOUND_FIELDS | {"policy_version"}
        observed = set(value)
        missing = sorted(expected - observed)
        unknown = sorted(observed - expected)
        if missing:
            raise SynthesisValidationError(f"budget policy missing bounds: {', '.join(missing)}")
        if unknown:
            raise SynthesisValidationError(f"budget policy has unknown fields: {', '.join(unknown)}")
        version = value["policy_version"]
        if not isinstance(version, str) or not version:
            raise SynthesisValidationError("policy_version must be a non-empty string")
        return cls(
            policy_version=version,
            **{field: _strict_int(value[field], field=field) for field in sorted(BOUND_FIELDS)},
        )

    def value(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"policy_version": self.policy_version}
        payload.update({field: getattr(self, field) for field in sorted(BOUND_FIELDS)})
        return payload

    def reserved_attempts(self) -> int:
        """`ceil(B * numerator / denominator)` for branch-generation budget B."""
        return -(
            -self.branch_generation_attempts * self.exploration_reserve_numerator
            // self.exploration_reserve_denominator
        )

    def restrict(self, **lowered: int) -> BudgetPolicy:
        """Return a policy with the named bounds lowered.

        Section 5: no component may increase a bound, so raising one is refused
        here rather than being silently accepted.
        """
        for field, value in lowered.items():
            if field not in BOUND_FIELDS:
                raise SynthesisValidationError(f"unknown bound: {field}")
            if field in RESERVE_FIELDS:
                raise SynthesisValidationError("the exploration reserve ratio cannot be restricted")
            if _strict_int(value, field=field) > getattr(self, field):
                raise SynthesisValidationError(f"no component may increase the bound {field}")
        return replace(self, **lowered)


class BudgetLedger:
    """Consumes a named counter before the work it guards executes."""

    def __init__(self, policy: BudgetPolicy) -> None:
        self.policy = policy
        self._consumed: dict[str, int] = {field: 0 for field in sorted(BOUND_FIELDS - set(RESERVE_FIELDS))}

    def consumed(self) -> dict[str, int]:
        return dict(self._consumed)

    def remaining(self, counter: str) -> int:
        if counter not in self._consumed:
            raise SynthesisValidationError(f"unknown budget counter: {counter}")
        return getattr(self.policy, counter) - self._consumed[counter]

    def consume(self, counter: str, amount: int = 1) -> None:
        """Charge a counter. Raises before the guarded work runs."""
        if counter not in self._consumed:
            raise SynthesisValidationError(f"unknown budget counter: {counter}")
        if _strict_int(amount, field="amount") <= 0:
            raise SynthesisValidationError("budget consumption must be a positive integer")
        bound = getattr(self.policy, counter)
        if self._consumed[counter] + amount > bound:
            raise BudgetExhausted(counter)
        self._consumed[counter] += amount

    def ledger_value(self) -> dict[str, Any]:
        """Exported before/after ledger (Section 6 trace requirement)."""
        return {
            "policy_version": self.policy.policy_version,
            "bounds": {field: getattr(self.policy, field) for field in sorted(BOUND_FIELDS)},
            "consumed": self.consumed(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ReserveAllocation:
    """One validated branch-generation allocation plus its reserve evidence."""

    reserved: int
    incumbent_family: str
    allocations: tuple[tuple[str, int], ...]
    eligible_families: tuple[str, ...]
    waivers: tuple[tuple[str, ...], ...]

    def value(self) -> dict[str, Any]:
        return {
            "reserved": self.reserved,
            "incumbent_family": self.incumbent_family,
            "allocations": [{"family": name, "attempts": count} for name, count in self.allocations],
            "eligible_families": list(self.eligible_families),
            "reserve_unavailable": [
                {"evaluated_families": list(entry[:-1]), "exclusion_reason": entry[-1]}
                for entry in self.waivers
            ],
        }


def allocate_with_reserve(
    policy: BudgetPolicy,
    *,
    incumbent_family: str,
    eligible_families: Sequence[str],
    allocations: Mapping[str, int],
    waivers: Sequence[Mapping[str, Any]] = (),
) -> ReserveAllocation:
    """Validate a branch-generation allocation against the Section 5.1 reserve.

    Over-allocation, a zero reserve, an unsubstantiated waiver, and allocation to
    an ineligible family each fail closed here rather than at export.
    """
    budget = policy.branch_generation_attempts
    reserved = policy.reserved_attempts()
    if reserved <= 0:
        raise SynthesisValidationError("exploration reserve must reserve at least one attempt")
    if reserved > budget:
        raise SynthesisValidationError("exploration reserve exceeds the branch-generation budget")

    families = tuple(parse_enum(StrategyFamily, name, field="strategy_family").value for name in eligible_families)
    if len(set(families)) != len(families):
        raise SynthesisValidationError("eligible strategy families must be distinct")
    incumbent = parse_enum(StrategyFamily, incumbent_family, field="incumbent_family").value

    charged = {}
    for name, count in allocations.items():
        family = parse_enum(StrategyFamily, name, field="strategy_family").value
        if family not in families:
            raise SynthesisValidationError(f"allocation to ineligible strategy family: {family}")
        if _strict_int(count, field=f"allocation[{family}]") < 0:
            raise SynthesisValidationError("allocation attempts must be zero or positive")
        charged[family] = count

    total = sum(charged.values())
    if total > budget:
        raise SynthesisValidationError("allocation exceeds the branch-generation budget")

    incumbent_share = charged.get(incumbent, 0)
    non_incumbent = total - incumbent_share

    parsed_waivers: list[tuple[str, ...]] = []
    for entry in waivers:
        if not isinstance(entry, Mapping):
            raise SynthesisValidationError("reserve_unavailable record must be an object")
        evaluated = entry.get("evaluated_families")
        reason = entry.get("exclusion_reason")
        if not isinstance(evaluated, Sequence) or isinstance(evaluated, (str, bytes)) or not evaluated:
            raise SynthesisValidationError("reserve_unavailable must name every evaluated family")
        if not isinstance(reason, str) or not reason:
            raise SynthesisValidationError("reserve_unavailable requires an exclusion reason")
        names = tuple(
            parse_enum(StrategyFamily, name, field="evaluated_family").value for name in evaluated
        )
        # Section 5.1: the record must name every evaluated family and its
        # exclusion reason, so a waiver cannot be substantiated by naming a
        # convenient subset.
        if set(names) != {family.value for family in StrategyFamily}:
            raise SynthesisValidationError(
                "reserve_unavailable must name every evaluated strategy family"
            )
        parsed_waivers.append(names + (reason,))

    if len(families) >= 2:
        # Section 5.1: no unavailability waiver applies while two families are
        # eligible.
        if parsed_waivers:
            raise SynthesisValidationError(
                "no unavailability waiver applies while two strategy families are eligible"
            )
        if non_incumbent < reserved:
            raise SynthesisValidationError(
                f"exploration reserve requires at least {reserved} non-incumbent attempts"
            )
        if incumbent_share > budget - reserved:
            raise SynthesisValidationError(
                f"incumbent family may receive at most {budget - reserved} attempts"
            )
    else:
        unfilled = max(0, reserved - non_incumbent)
        if len(parsed_waivers) != unfilled:
            raise SynthesisValidationError(
                f"each of the {unfilled} unfilled reserved slots requires a reserve_unavailable record"
            )

    return ReserveAllocation(
        reserved=reserved,
        incumbent_family=incumbent,
        allocations=tuple(sorted(charged.items())),
        eligible_families=tuple(sorted(families)),
        waivers=tuple(parsed_waivers),
    )


__all__ = [
    "BOUND_FIELDS",
    "BudgetExhausted",
    "BudgetLedger",
    "BudgetPolicy",
    "POSITIVE_BOUNDS",
    "RESERVE_FIELDS",
    "ReserveAllocation",
    "ZERO_OR_POSITIVE_BOUNDS",
    "allocate_with_reserve",
]
