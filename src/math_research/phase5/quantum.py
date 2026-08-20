"""Exact diagonal quantum-discrimination benchmark plugin.

Diagonal weighted states are a genuine commuting subset of the SDP.  Fraction
arithmetic makes feasibility, the JRF update, the primal value, and the
independent diagonal dual certificate exact rather than tolerance-based.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterable, Sequence

from .serialization import canonical_hash


class QuantumInputError(ValueError):
    pass


def _fraction(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise QuantumInputError("boolean is not a rational number")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise QuantumInputError(f"invalid rational: {value!r}") from error
    raise QuantumInputError("rational values must be integers or canonical strings")


def _text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _matrix(value: Iterable[Iterable[Any]]) -> tuple[tuple[Fraction, ...], ...]:
    rows = tuple(tuple(_fraction(item) for item in row) for row in value)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise QuantumInputError("matrix must be nonempty and rectangular")
    return rows


@dataclass(frozen=True, slots=True)
class DiagonalCase:
    case_id: str
    statement_variant: str
    weights: tuple[tuple[Fraction, ...], ...]
    initial_povm: tuple[tuple[Fraction, ...], ...]
    iterations: int
    expected_classification: str

    @classmethod
    def from_value(cls, value: dict[str, Any]) -> "DiagonalCase":
        required = {
            "case_id", "statement_variant", "weights", "initial_povm",
            "iterations", "expected_classification",
        }
        if set(value) != required:
            raise QuantumInputError("quantum case has missing or unknown fields")
        weights = _matrix(value["weights"])
        initial = _matrix(value["initial_povm"])
        if len(initial) != len(weights) or len(initial[0]) != len(weights[0]):
            raise QuantumInputError("weights and POVM dimensions differ")
        iterations = value["iterations"]
        if isinstance(iterations, bool) or not isinstance(iterations, int) or not 0 <= iterations <= 256:
            raise QuantumInputError("iterations must be an integer in 0..256")
        return cls(
            case_id=value["case_id"], statement_variant=value["statement_variant"],
            weights=weights, initial_povm=initial, iterations=iterations,
            expected_classification=value["expected_classification"],
        )


def validate_case(case: DiagonalCase) -> None:
    m, d = len(case.weights), len(case.weights[0])
    if any(value < 0 for row in case.weights for value in row):
        raise QuantumInputError("weighted states must be positive semidefinite")
    priors = tuple(sum(row, Fraction()) for row in case.weights)
    if any(prior <= 0 for prior in priors) or sum(priors, Fraction()) != 1:
        raise QuantumInputError("weighted-state traces must be positive priors summing to one")
    if any(sum(case.weights[i][j] for i in range(m)) <= 0 for j in range(d)):
        raise QuantumInputError("operators must be restricted to the effective support")
    if any(value < 0 for row in case.initial_povm for value in row):
        raise QuantumInputError("POVM effects must be positive semidefinite")
    if any(sum(case.initial_povm[i][j] for i in range(m)) != 1 for j in range(d)):
        raise QuantumInputError("diagonal POVM effects must sum to identity")
    if case.statement_variant == "qd-fs-01" and any(
        value <= 0 for row in case.initial_povm for value in row
    ):
        raise QuantumInputError("QD-FS-01 requires every initial component to be positive definite")


def _objective(weights: Sequence[Sequence[Fraction]], povm: Sequence[Sequence[Fraction]]) -> Fraction:
    return sum(
        (weights[i][j] * povm[i][j] for i in range(len(weights)) for j in range(len(weights[0]))),
        Fraction(),
    )


def _step(
    weights: tuple[tuple[Fraction, ...], ...],
    povm: tuple[tuple[Fraction, ...], ...],
) -> tuple[tuple[Fraction, ...], ...]:
    m, d = len(weights), len(weights[0])
    denominators = tuple(
        sum((weights[i][j] ** 2) * povm[i][j] for i in range(m)) for j in range(d)
    )
    if any(value <= 0 for value in denominators):
        raise QuantumInputError("ordinary inverse JRF step is undefined because K is singular")
    return tuple(
        tuple((weights[i][j] ** 2) * povm[i][j] / denominators[j] for j in range(d))
        for i in range(m)
    )


def _public_matrix(value: Sequence[Sequence[Fraction]]) -> list[list[str]]:
    return [[_text(item) for item in row] for row in value]


def run_case(case: DiagonalCase) -> dict[str, Any]:
    validate_case(case)
    trajectory = [case.initial_povm]
    objectives = [_objective(case.weights, case.initial_povm)]
    for _ in range(case.iterations):
        trajectory.append(_step(case.weights, trajectory[-1]))
        objectives.append(_objective(case.weights, trajectory[-1]))
    if any(right < left for left, right in zip(objectives, objectives[1:])):
        raise AssertionError("exact JRF objective decreased")

    m, d = len(case.weights), len(case.weights[0])
    dual_gamma = tuple(max(case.weights[i][j] for i in range(m)) for j in range(d))
    optimum = sum(dual_gamma, Fraction())
    optimal_effects = tuple(
        tuple(Fraction(int(i == min(k for k in range(m) if case.weights[k][j] == dual_gamma[j]))) for j in range(d))
        for i in range(m)
    )
    primal_optimum = _objective(case.weights, optimal_effects)
    if primal_optimum != optimum:
        raise AssertionError("independent diagonal primal and dual optima disagree")

    final = trajectory[-1]
    final_value = objectives[-1]
    fixed = _step(case.weights, final) == final
    full_support = all(value > 0 for row in case.initial_povm for value in row)
    unique_maxima = all(
        sum(case.weights[i][j] == dual_gamma[j] for i in range(m)) == 1 for j in range(d)
    )
    closed_form_limit_optimal = full_support and unique_maxima
    nonoptimal_fixed_point = fixed and final_value < optimum
    ykl_domination = all(
        dual_gamma[j] - case.weights[i][j] >= 0 for i in range(m) for j in range(d)
    )
    result = {
        "schema_version": "adaivy.quantum-diagonal-result.v1",
        "benchmark_id": "QD-FS-01",
        "case_id": case.case_id,
        "statement_variant": case.statement_variant,
        "algorithm_variant": "normalization_corrected_ordinary_inverse",
        "arithmetic": "fractions-exact",
        "iterations": case.iterations,
        "initial_full_support": full_support,
        "trajectory": [_public_matrix(item) for item in trajectory],
        "objective_values": [_text(item) for item in objectives],
        "final_objective": _text(final_value),
        "independent_primal_optimum": _text(primal_optimum),
        "independent_dual_optimum": _text(optimum),
        "dual_gamma": [_text(item) for item in dual_gamma],
        "primal_dual_gap": _text(optimum - final_value),
        "fixed_point": fixed,
        "nonoptimal_fixed_point": nonoptimal_fixed_point,
        "ykl_dual_domination_certificate": ykl_domination,
        "closed_form_accumulation_point_optimal": closed_form_limit_optimal,
        "proposal_status": "checked_result",
        "mathematical_warrant": "exact_commuting_derivation",
        "applicability_status": "benchmark_local",
        "graph_admitted": False,
        "expected_classification": case.expected_classification,
        "operation_count": case.iterations * m * d,
    }
    result["result_hash"] = canonical_hash(result)
    return result
