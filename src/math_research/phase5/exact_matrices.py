"""Exact small-matrix algebra over the measured algebraic field.

Every operation is exact.  Positive semidefiniteness is decided by the signs of
*all* principal minors, which is a theorem-backed exact criterion for Hermitian
matrices rather than an eigenvalue approximation, so no spectrum is ever
computed numerically and no tolerance decides a sign.  The dimension bound keeps
the minor enumeration finite.
"""

from __future__ import annotations

import itertools
from typing import Any, Iterable, Sequence

from .algebraic import (
    ONE,
    ZERO,
    AlgebraicComplex,
    AlgebraicFieldError,
    Quadratic,
    parse_algebraic,
)

MAX_DIMENSION = 4

Matrix = tuple[tuple[AlgebraicComplex, ...], ...]


def parse_matrix(value: Any) -> Matrix:
    if not isinstance(value, list) or not value:
        raise AlgebraicFieldError("matrix must be a nonempty array")
    if any(not isinstance(row, list) for row in value):
        raise AlgebraicFieldError("matrix rows must be arrays")
    rows = tuple(tuple(parse_algebraic(item) for item in row) for row in value)
    if any(len(row) != len(rows) for row in rows):
        raise AlgebraicFieldError("matrix must be square")
    if len(rows) > MAX_DIMENSION:
        raise AlgebraicFieldError("matrix exceeds the exact Phase 5 dimension bound")
    return rows


def total(values: Iterable[AlgebraicComplex]) -> AlgebraicComplex:
    result = ZERO
    for value in values:
        result = result + value
    return result


def add(left: Matrix, right: Matrix) -> Matrix:
    return tuple(
        tuple(left[i][j] + right[i][j] for j in range(len(left))) for i in range(len(left))
    )


def subtract(left: Matrix, right: Matrix) -> Matrix:
    return tuple(
        tuple(left[i][j] - right[i][j] for j in range(len(left))) for i in range(len(left))
    )


def multiply(left: Matrix, right: Matrix) -> Matrix:
    size = len(left)
    return tuple(
        tuple(total(left[i][k] * right[k][j] for k in range(size)) for j in range(size))
        for i in range(size)
    )


def scale(matrix: Matrix, factor: AlgebraicComplex) -> Matrix:
    return tuple(tuple(item * factor for item in row) for row in matrix)


def zero(size: int) -> Matrix:
    return tuple(tuple(ZERO for _ in range(size)) for _ in range(size))


def identity(size: int) -> Matrix:
    return tuple(tuple(ONE if i == j else ZERO for j in range(size)) for i in range(size))


def sum_matrices(matrices: Sequence[Matrix]) -> Matrix:
    result = zero(len(matrices[0]))
    for matrix in matrices:
        result = add(result, matrix)
    return result


def trace(matrix: Matrix) -> AlgebraicComplex:
    return total(matrix[i][i] for i in range(len(matrix)))


def dagger(matrix: Matrix) -> Matrix:
    return tuple(
        tuple(matrix[j][i].conjugate() for j in range(len(matrix))) for i in range(len(matrix))
    )


def is_hermitian(matrix: Matrix) -> bool:
    return matrix == dagger(matrix)


def is_zero_matrix(matrix: Matrix) -> bool:
    return all(item.is_zero() for row in matrix for item in row)


def commutator(left: Matrix, right: Matrix) -> Matrix:
    return subtract(multiply(left, right), multiply(right, left))


def determinant(matrix: Matrix) -> AlgebraicComplex:
    size = len(matrix)
    if size == 1:
        return matrix[0][0]
    result = ZERO
    for column in range(size):
        minor = tuple(tuple(row[j] for j in range(size) if j != column) for row in matrix[1:])
        term = matrix[0][column] * determinant(minor)
        result = result + (term if column % 2 == 0 else -term)
    return result


def principal(matrix: Matrix, indices: Sequence[int]) -> Matrix:
    return tuple(tuple(matrix[i][j] for j in indices) for i in indices)


def principal_minors(matrix: Matrix) -> tuple[Quadratic, ...]:
    if not is_hermitian(matrix):
        raise AlgebraicFieldError("matrix is not Hermitian")
    values: list[Quadratic] = []
    for count in range(1, len(matrix) + 1):
        for indices in itertools.combinations(range(len(matrix)), count):
            value = determinant(principal(matrix, indices))
            values.append(value.real_part("Hermitian principal determinant"))
    return tuple(values)


def is_psd(matrix: Matrix) -> bool:
    return all(item.sign() >= 0 for item in principal_minors(matrix))


def is_positive_definite(matrix: Matrix) -> bool:
    if not is_hermitian(matrix):
        return False
    for count in range(1, len(matrix) + 1):
        leading = tuple(tuple(matrix[i][j] for j in range(count)) for i in range(count))
        value = determinant(leading)
        if not value.is_real() or value.real.sign() <= 0:
            return False
    return True


def power(matrix: Matrix, exponent: int) -> Matrix:
    result = identity(len(matrix))
    for _ in range(exponent):
        result = multiply(result, matrix)
    return result


def canonical_matrix(matrix: Matrix) -> list[list[Any]]:
    return [[item.canonical() for item in row] for row in matrix]


def all_values(matrices: Sequence[Matrix]) -> list[AlgebraicComplex]:
    return [item for matrix in matrices for row in matrix for item in row]


__all__ = [
    "MAX_DIMENSION",
    "Matrix",
    "add",
    "all_values",
    "canonical_matrix",
    "commutator",
    "dagger",
    "determinant",
    "identity",
    "is_hermitian",
    "is_positive_definite",
    "is_psd",
    "is_zero_matrix",
    "multiply",
    "parse_matrix",
    "power",
    "principal",
    "principal_minors",
    "scale",
    "subtract",
    "sum_matrices",
    "total",
    "trace",
    "zero",
]
