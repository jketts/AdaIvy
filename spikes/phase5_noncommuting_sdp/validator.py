"""Exact small-matrix checks for quantum-discrimination SDP candidates.

The spike validates supplied primal/dual candidates.  It does not search for a
solution, approximate eigenvalues, certify floating-point output, or alter the
Phase 5 benchmark implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import itertools
import json
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = "adaivy.phase5-noncommuting-sdp-spike.v1"
MAX_DIMENSION = 4
MAX_OUTCOMES = 8


class CertificateInputError(ValueError):
    """The exact candidate is malformed or violates a required constraint."""


def _fraction(value: Any) -> Fraction:
    if isinstance(value, bool):
        raise CertificateInputError("booleans are not rational values")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise CertificateInputError(f"invalid rational {value!r}") from exc
    raise CertificateInputError("rationals must be integers or strings")


def _rational_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


@dataclass(frozen=True, slots=True)
class QComplex:
    real: Fraction = Fraction()
    imag: Fraction = Fraction()

    def __add__(self, other: object) -> "QComplex":
        value = qcomplex(other)
        return QComplex(self.real + value.real, self.imag + value.imag)

    __radd__ = __add__

    def __neg__(self) -> "QComplex":
        return QComplex(-self.real, -self.imag)

    def __sub__(self, other: object) -> "QComplex":
        return self + (-qcomplex(other))

    def __rsub__(self, other: object) -> "QComplex":
        return qcomplex(other) - self

    def __mul__(self, other: object) -> "QComplex":
        value = qcomplex(other)
        return QComplex(
            self.real * value.real - self.imag * value.imag,
            self.real * value.imag + self.imag * value.real,
        )

    __rmul__ = __mul__

    def conjugate(self) -> "QComplex":
        return QComplex(self.real, -self.imag)

    def is_zero(self) -> bool:
        return self.real == 0 and self.imag == 0

    def value(self) -> str | dict[str, str]:
        if self.imag == 0:
            return _rational_text(self.real)
        return {"re": _rational_text(self.real), "im": _rational_text(self.imag)}


ZERO = QComplex()
ONE = QComplex(Fraction(1))
Matrix = tuple[tuple[QComplex, ...], ...]


def qcomplex(value: object) -> QComplex:
    if isinstance(value, QComplex):
        return value
    if isinstance(value, dict):
        if set(value) != {"re", "im"}:
            raise CertificateInputError("complex rationals require exactly re and im")
        return QComplex(_fraction(value["re"]), _fraction(value["im"]))
    return QComplex(_fraction(value))


def _matrix(value: object) -> Matrix:
    if not isinstance(value, list) or not value:
        raise CertificateInputError("matrix must be a nonempty array")
    rows = tuple(tuple(qcomplex(item) for item in row) for row in value if isinstance(row, list))
    if len(rows) != len(value) or any(len(row) != len(rows) for row in rows):
        raise CertificateInputError("matrix must be square")
    if len(rows) > MAX_DIMENSION:
        raise CertificateInputError("matrix exceeds exact spike dimension bound")
    return rows


def _shape_equal(matrices: Sequence[Matrix]) -> bool:
    return bool(matrices) and all(len(item) == len(matrices[0]) for item in matrices)


def _add(left: Matrix, right: Matrix) -> Matrix:
    return tuple(
        tuple(left[i][j] + right[i][j] for j in range(len(left)))
        for i in range(len(left))
    )


def _subtract(left: Matrix, right: Matrix) -> Matrix:
    return tuple(
        tuple(left[i][j] - right[i][j] for j in range(len(left)))
        for i in range(len(left))
    )


def _multiply(left: Matrix, right: Matrix) -> Matrix:
    size = len(left)
    return tuple(
        tuple(sum((left[i][k] * right[k][j] for k in range(size)), ZERO) for j in range(size))
        for i in range(size)
    )


def _zero(size: int) -> Matrix:
    return tuple(tuple(ZERO for _ in range(size)) for _ in range(size))


def _sum_matrices(matrices: Sequence[Matrix]) -> Matrix:
    result = _zero(len(matrices[0]))
    for matrix in matrices:
        result = _add(result, matrix)
    return result


def _identity(size: int) -> Matrix:
    return tuple(tuple(ONE if i == j else ZERO for j in range(size)) for i in range(size))


def _trace(matrix: Matrix) -> QComplex:
    return sum((matrix[i][i] for i in range(len(matrix))), ZERO)


def _dagger(matrix: Matrix) -> Matrix:
    return tuple(
        tuple(matrix[j][i].conjugate() for j in range(len(matrix)))
        for i in range(len(matrix))
    )


def _is_zero_matrix(matrix: Matrix) -> bool:
    return all(item.is_zero() for row in matrix for item in row)


def _determinant(matrix: Matrix) -> QComplex:
    size = len(matrix)
    if size == 1:
        return matrix[0][0]
    total = ZERO
    for column in range(size):
        minor = tuple(
            tuple(row[j] for j in range(size) if j != column)
            for row in matrix[1:]
        )
        term = matrix[0][column] * _determinant(minor)
        total = total + (term if column % 2 == 0 else -term)
    return total


def _principal(matrix: Matrix, indices: tuple[int, ...]) -> Matrix:
    return tuple(tuple(matrix[i][j] for j in indices) for i in indices)


def _hermitian(matrix: Matrix) -> bool:
    return matrix == _dagger(matrix)


def _principal_minors(matrix: Matrix) -> tuple[Fraction, ...]:
    if not _hermitian(matrix):
        raise CertificateInputError("matrix is not Hermitian")
    values: list[Fraction] = []
    for count in range(1, len(matrix) + 1):
        for indices in itertools.combinations(range(len(matrix)), count):
            determinant = _determinant(_principal(matrix, indices))
            if determinant.imag != 0:
                raise AssertionError("Hermitian principal determinant was not real")
            values.append(determinant.real)
    return tuple(values)


def _psd(matrix: Matrix) -> bool:
    return all(item >= 0 for item in _principal_minors(matrix))


def _positive_definite(matrix: Matrix) -> bool:
    if not _hermitian(matrix):
        return False
    for count in range(1, len(matrix) + 1):
        determinant = _determinant(tuple(tuple(matrix[i][j] for j in range(count)) for i in range(count)))
        if determinant.imag != 0 or determinant.real <= 0:
            return False
    return True


def _public_matrix(matrix: Matrix) -> list[list[str | dict[str, str]]]:
    return [[item.value() for item in row] for row in matrix]


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _real_trace(matrix: Matrix, label: str) -> Fraction:
    value = _trace(matrix)
    if value.imag != 0:
        raise CertificateInputError(f"{label} trace is not real")
    return value.real


def _commutator(left: Matrix, right: Matrix) -> Matrix:
    return _subtract(_multiply(left, right), _multiply(right, left))


def _validate_psd(matrix: Matrix, label: str) -> None:
    if not _hermitian(matrix):
        raise CertificateInputError(f"{label} is not Hermitian")
    if not _psd(matrix):
        raise CertificateInputError(f"{label} is not positive semidefinite")


def validate_fixture(value: dict[str, Any]) -> dict[str, Any]:
    """Validate one exact ensemble plus supplied primal and dual candidates."""

    required = {
        "schema_version", "case_id", "weighted_states", "primal_povm",
        "dual_gamma", "expected_noncommuting", "expected_zero_gap",
    }
    if set(value) != required or value.get("schema_version") != SCHEMA_VERSION:
        raise CertificateInputError("fixture has missing, unknown, or unsupported fields")
    if not isinstance(value["expected_noncommuting"], bool) or not isinstance(value["expected_zero_gap"], bool):
        raise CertificateInputError("fixture expectations must be booleans")
    weighted_states = tuple(_matrix(item) for item in value["weighted_states"])
    povm = tuple(_matrix(item) for item in value["primal_povm"])
    gamma = _matrix(value["dual_gamma"])
    if not 1 <= len(weighted_states) <= MAX_OUTCOMES or len(povm) != len(weighted_states):
        raise CertificateInputError("outcome count is invalid")
    if not _shape_equal((*weighted_states, *povm, gamma)):
        raise CertificateInputError("matrix dimensions disagree")

    traces: list[Fraction] = []
    for index, state in enumerate(weighted_states):
        _validate_psd(state, f"weighted state {index}")
        trace = _real_trace(state, f"weighted state {index}")
        if trace <= 0:
            raise CertificateInputError("weighted-state priors must be positive")
        traces.append(trace)
    if sum(traces, Fraction()) != 1:
        raise CertificateInputError("weighted-state traces must sum to one")
    total_state = _sum_matrices(weighted_states)
    if not _positive_definite(total_state):
        raise CertificateInputError("ensemble is not restricted to its effective support")

    for index, effect in enumerate(povm):
        _validate_psd(effect, f"POVM effect {index}")
    povm_sum = _sum_matrices(povm)
    if povm_sum != _identity(len(gamma)):
        raise CertificateInputError("POVM effects do not sum to identity")

    _validate_psd(gamma, "dual gamma")
    slacks = tuple(_subtract(gamma, state) for state in weighted_states)
    for index, slack in enumerate(slacks):
        _validate_psd(slack, f"dual slack {index}")

    primal_terms = tuple(_real_trace(_multiply(state, effect), "primal term") for state, effect in zip(weighted_states, povm))
    primal_value = sum(primal_terms, Fraction())
    dual_value = _real_trace(gamma, "dual objective")
    gap = dual_value - primal_value
    if gap < 0:
        raise AssertionError("exact weak duality was violated by feasible candidates")
    left_residuals = tuple(_multiply(slack, effect) for slack, effect in zip(slacks, povm))
    right_residuals = tuple(_multiply(effect, slack) for slack, effect in zip(slacks, povm))
    complementary = all(_is_zero_matrix(item) for item in (*left_residuals, *right_residuals))
    exact_optimum = gap == 0 and complementary
    noncommuting = any(
        not _is_zero_matrix(_commutator(weighted_states[i], weighted_states[j]))
        for i in range(len(weighted_states))
        for j in range(i + 1, len(weighted_states))
    )
    if noncommuting is not value["expected_noncommuting"]:
        raise CertificateInputError("fixture noncommutativity expectation disagrees with exact check")
    if exact_optimum is not value["expected_zero_gap"]:
        raise CertificateInputError("fixture exact-certificate expectation disagrees with residuals")

    result: dict[str, Any] = {
        "schema_version": "adaivy.phase5-noncommuting-sdp-validation.v1",
        "case_id": value["case_id"],
        "arithmetic": "exact_rational_complex",
        "dimension": len(gamma),
        "outcomes": len(weighted_states),
        "noncommuting": noncommuting,
        "weighted_state_traces": [_rational_text(item) for item in traces],
        "ensemble_effective_support": True,
        "povm_feasible": True,
        "dual_feasible": True,
        "primal_value": _rational_text(primal_value),
        "dual_value": _rational_text(dual_value),
        "primal_dual_gap": _rational_text(gap),
        "left_complementarity_residuals": [_public_matrix(item) for item in left_residuals],
        "right_complementarity_residuals": [_public_matrix(item) for item in right_residuals],
        "complementarity_exact": complementary,
        "exact_optimum_certificate": exact_optimum,
        "disposition": "exact_certificate_checked" if exact_optimum else "candidate_only_unresolved",
        "blocked_without_solver": not exact_optimum,
        "blocked_reason": None if exact_optimum else (
            "No exact rational optimum certificate was supplied; a numerical SDP candidate still "
            "requires rigorous rational/algebraic or interval reconstruction before it can close the gap."
        ),
        "phase5_integrated": False,
        "search_tiers_enabled": False,
    }
    result["content_hash"] = _hash(result)
    return result
