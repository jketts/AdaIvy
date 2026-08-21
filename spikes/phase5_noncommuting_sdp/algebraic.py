"""Exact arithmetic in a real quadratic field, for certificate checking only.

`validator.py` checks candidates whose entries are rational. The noncommuting
fixtures expose the blocker recorded in `DEPENDENCY_LICENSE_COMPARISON.md`: the
optimum of a two-state discrimination SDP is generally irrational, so no
rational candidate can close the gap exactly. This module extends the exact
domain to ``Q(sqrt(s))`` for one squarefree ``s`` per case, which is the
smallest field extension that can hold the optimum of a two-outcome case.

Everything here is exact. There is no tolerance, no floating-point comparison,
and no eigenvalue approximation:

* ordering in ``Q(sqrt(s))`` is decided by comparing ``a**2`` with ``s*b**2``;
* positive semidefiniteness is decided by the signs of all principal minors;
* ``sqrt`` is only ever taken of a nonnegative rational, and only after the
  square part has been extracted by bounded trial division.

The rational enclosures produced by :func:`enclosure` are rigorous: they are
built from :func:`math.isqrt`, so the true value is always inside the returned
closed interval. They exist so a floating-point observation can be compared
against an exact value without the exact value ever being replaced by a float.

Nothing in this module reads a solver result, and no function here can return
"verified" for an unchecked input.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Sequence

MAX_SQUARE_EXTRACTION_INPUT = 10**8
"""Bound on the integer whose square part is extracted by trial division."""

MAX_SQUAREFREE_RADICAND = 1000
"""Bound on the squarefree radicand of an admissible field extension."""

ENCLOSURE_DIGITS = 30
"""Decimal digits used for the rigorous rational enclosure of a surd."""

MAX_ALGEBRAIC_DIMENSION = 4
"""Matches ``validator.MAX_DIMENSION``; keeps minor enumeration bounded."""


class AlgebraicFieldError(ValueError):
    """The requested exact operation is outside this module's bounded domain."""


def rational_text(value: Fraction) -> str:
    """Canonical text for an exact rational. No decimals, no rounding."""

    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def square_free_part(value: int) -> tuple[int, int]:
    """Return ``(k, s)`` with ``value == k * k * s`` and ``s`` squarefree.

    Bounded by :data:`MAX_SQUARE_EXTRACTION_INPUT`; larger inputs fail closed
    rather than running an unbounded factorisation.
    """

    if value < 0:
        raise AlgebraicFieldError("square-free extraction requires a nonnegative integer")
    if value > MAX_SQUARE_EXTRACTION_INPUT:
        raise AlgebraicFieldError(
            f"{value} exceeds the bounded square-free extraction input {MAX_SQUARE_EXTRACTION_INPUT}"
        )
    if value in (0, 1):
        return (value, 1)
    remaining = value
    extracted = 1
    divisor = 2
    while divisor * divisor <= remaining:
        square = divisor * divisor
        while remaining % square == 0:
            remaining //= square
            extracted *= divisor
        divisor += 1
    return (extracted, remaining)


@dataclass(frozen=True, slots=True)
class Surd:
    """The exact real number ``a + b * sqrt(radicand)``.

    Normalised so that ``b == 0`` implies ``radicand == 1``, which makes a
    rational value comparable with any field, and makes equality structural.
    """

    a: Fraction = Fraction()
    b: Fraction = Fraction()
    radicand: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.a, Fraction) or not isinstance(self.b, Fraction):
            raise AlgebraicFieldError("surd coefficients must be Fraction values")
        if not isinstance(self.radicand, int) or isinstance(self.radicand, bool):
            raise AlgebraicFieldError("radicand must be an int")
        if self.radicand < 1:
            raise AlgebraicFieldError("radicand must be positive")
        if self.radicand > MAX_SQUAREFREE_RADICAND:
            raise AlgebraicFieldError(
                f"radicand {self.radicand} exceeds the bound {MAX_SQUAREFREE_RADICAND}"
            )
        if self.radicand != 1:
            _, remaining = square_free_part(self.radicand)
            if remaining != self.radicand:
                raise AlgebraicFieldError("radicand must be squarefree")
        if self.radicand == 1 and self.b != 0:
            object.__setattr__(self, "a", self.a + self.b)
            object.__setattr__(self, "b", Fraction())
        if self.b == 0 and self.radicand != 1:
            object.__setattr__(self, "radicand", 1)

    # -- construction ----------------------------------------------------

    @staticmethod
    def rational(value: Fraction | int) -> "Surd":
        return Surd(Fraction(value), Fraction(), 1)

    @staticmethod
    def sqrt_of(value: Fraction) -> "Surd":
        """Exact ``sqrt(value)`` for a nonnegative rational, inside the bound."""

        if value < 0:
            raise AlgebraicFieldError("sqrt of a negative rational is not real")
        if value == 0:
            return Surd()
        numerator, denominator = value.numerator, value.denominator
        extracted, remaining = square_free_part(numerator * denominator)
        # sqrt(p/q) == sqrt(p*q)/q == extracted*sqrt(remaining)/q
        return Surd(Fraction(), Fraction(extracted, denominator), remaining)

    # -- field operations ------------------------------------------------

    def _field(self, other: "Surd") -> int:
        if self.b == 0:
            return other.radicand
        if other.b == 0:
            return self.radicand
        if self.radicand != other.radicand:
            raise AlgebraicFieldError(
                f"refusing to mix Q(sqrt({self.radicand})) with Q(sqrt({other.radicand}))"
            )
        return self.radicand

    def __add__(self, other: "Surd") -> "Surd":
        return Surd(self.a + other.a, self.b + other.b, self._field(other))

    def __neg__(self) -> "Surd":
        return Surd(-self.a, -self.b, self.radicand)

    def __sub__(self, other: "Surd") -> "Surd":
        return self + (-other)

    def __mul__(self, other: "Surd") -> "Surd":
        radicand = self._field(other)
        return Surd(
            self.a * other.a + radicand * self.b * other.b,
            self.a * other.b + other.a * self.b,
            radicand,
        )

    def inverse(self) -> "Surd":
        norm = self.a * self.a - self.radicand * self.b * self.b
        if norm == 0:
            raise AlgebraicFieldError("cannot invert zero in the quadratic field")
        return Surd(self.a / norm, -self.b / norm, self.radicand)

    def is_zero(self) -> bool:
        return self.a == 0 and self.b == 0

    def is_rational(self) -> bool:
        return self.b == 0

    def as_fraction(self) -> Fraction:
        if self.b != 0:
            raise AlgebraicFieldError("value is irrational; it has no exact Fraction form")
        return self.a

    def sign(self) -> int:
        """Exact sign in ``{-1, 0, 1}``. No tolerance is involved."""

        if self.b == 0:
            return (self.a > 0) - (self.a < 0)
        if self.a == 0:
            return (self.b > 0) - (self.b < 0)
        if self.a > 0 and self.b > 0:
            return 1
        if self.a < 0 and self.b < 0:
            return -1
        left = self.a * self.a
        right = self.radicand * self.b * self.b
        if left == right:
            return 0
        if self.a > 0:
            return 1 if left > right else -1
        return 1 if right > left else -1

    def enclosure(self, digits: int = ENCLOSURE_DIGITS) -> tuple[Fraction, Fraction]:
        """A rigorous closed rational interval containing this exact value."""

        if digits < 1:
            raise AlgebraicFieldError("enclosure digits must be at least one")
        if self.b == 0:
            return (self.a, self.a)
        scale = 10**digits
        root = math.isqrt(self.radicand * scale * scale)
        low = Fraction(root, scale)
        high = Fraction(root + 1, scale)
        if self.b > 0:
            return (self.a + self.b * low, self.a + self.b * high)
        return (self.a + self.b * high, self.a + self.b * low)

    def public(self) -> dict[str, object]:
        return {
            "rational_part": rational_text(self.a),
            "surd_coefficient": rational_text(self.b),
            "radicand": self.radicand,
        }


ZERO = Surd()
ONE = Surd.rational(1)


def enclosure(value: Surd, digits: int = ENCLOSURE_DIGITS) -> dict[str, object]:
    low, high = value.enclosure(digits)
    return {
        "method": "isqrt_directed_rational_bounds",
        "digits": digits,
        "lower_bound": rational_text(low),
        "upper_bound": rational_text(high),
        "rigorous": True,
    }


@dataclass(frozen=True, slots=True)
class AlgComplex:
    """``real + i * imag`` with both parts in the same real quadratic field."""

    real: Surd = ZERO
    imag: Surd = ZERO

    @staticmethod
    def rational(re: Fraction | int, im: Fraction | int = 0) -> "AlgComplex":
        return AlgComplex(Surd.rational(re), Surd.rational(im))

    def __add__(self, other: "AlgComplex") -> "AlgComplex":
        return AlgComplex(self.real + other.real, self.imag + other.imag)

    def __neg__(self) -> "AlgComplex":
        return AlgComplex(-self.real, -self.imag)

    def __sub__(self, other: "AlgComplex") -> "AlgComplex":
        return self + (-other)

    def __mul__(self, other: "AlgComplex") -> "AlgComplex":
        return AlgComplex(
            self.real * other.real - self.imag * other.imag,
            self.real * other.imag + self.imag * other.real,
        )

    def conjugate(self) -> "AlgComplex":
        return AlgComplex(self.real, -self.imag)

    def scale(self, factor: Surd) -> "AlgComplex":
        return AlgComplex(self.real * factor, self.imag * factor)

    def is_zero(self) -> bool:
        return self.real.is_zero() and self.imag.is_zero()

    def public(self) -> dict[str, object]:
        return {"re": self.real.public(), "im": self.imag.public()}


AZERO = AlgComplex()
AONE = AlgComplex(ONE, ZERO)
AlgMatrix = tuple[tuple[AlgComplex, ...], ...]


def matrix_from_pairs(rows: Sequence[Sequence[tuple[Fraction, Fraction]]]) -> AlgMatrix:
    """Build a matrix from ``(real, imag)`` rational pairs."""

    return tuple(tuple(AlgComplex.rational(re, im) for re, im in row) for row in rows)


def identity(size: int) -> AlgMatrix:
    return tuple(tuple(AONE if i == j else AZERO for j in range(size)) for i in range(size))


def zeros(size: int) -> AlgMatrix:
    return tuple(tuple(AZERO for _ in range(size)) for _ in range(size))


def add(left: AlgMatrix, right: AlgMatrix) -> AlgMatrix:
    return tuple(
        tuple(left[i][j] + right[i][j] for j in range(len(left)))
        for i in range(len(left))
    )


def subtract(left: AlgMatrix, right: AlgMatrix) -> AlgMatrix:
    return tuple(
        tuple(left[i][j] - right[i][j] for j in range(len(left)))
        for i in range(len(left))
    )


def multiply(left: AlgMatrix, right: AlgMatrix) -> AlgMatrix:
    size = len(left)
    out: list[tuple[AlgComplex, ...]] = []
    for i in range(size):
        row: list[AlgComplex] = []
        for j in range(size):
            total = AZERO
            for k in range(size):
                total = total + left[i][k] * right[k][j]
            row.append(total)
        out.append(tuple(row))
    return tuple(out)


def scalar_multiply(matrix: AlgMatrix, factor: Surd) -> AlgMatrix:
    return tuple(tuple(item.scale(factor) for item in row) for row in matrix)


def sum_matrices(matrices: Sequence[AlgMatrix]) -> AlgMatrix:
    if not matrices:
        raise AlgebraicFieldError("cannot sum an empty matrix sequence")
    total = zeros(len(matrices[0]))
    for matrix in matrices:
        total = add(total, matrix)
    return total


def dagger(matrix: AlgMatrix) -> AlgMatrix:
    size = len(matrix)
    return tuple(
        tuple(matrix[j][i].conjugate() for j in range(size)) for i in range(size)
    )


def trace(matrix: AlgMatrix) -> AlgComplex:
    total = AZERO
    for i in range(len(matrix)):
        total = total + matrix[i][i]
    return total


def is_hermitian(matrix: AlgMatrix) -> bool:
    return matrix == dagger(matrix)


def is_zero_matrix(matrix: AlgMatrix) -> bool:
    return all(item.is_zero() for row in matrix for item in row)


def determinant(matrix: AlgMatrix) -> AlgComplex:
    size = len(matrix)
    if size == 0:
        raise AlgebraicFieldError("determinant of an empty matrix is undefined")
    if size == 1:
        return matrix[0][0]
    total = AZERO
    for column in range(size):
        minor = tuple(
            tuple(row[j] for j in range(size) if j != column) for row in matrix[1:]
        )
        term = matrix[0][column] * determinant(minor)
        total = total + (term if column % 2 == 0 else -term)
    return total


def principal_minor_signs(matrix: AlgMatrix) -> tuple[int, ...]:
    """Signs of every principal minor. Raises unless the matrix is Hermitian."""

    if len(matrix) > MAX_ALGEBRAIC_DIMENSION:
        raise AlgebraicFieldError("matrix exceeds the bounded exact dimension")
    if not is_hermitian(matrix):
        raise AlgebraicFieldError("principal minors require a Hermitian matrix")
    signs: list[int] = []
    for count in range(1, len(matrix) + 1):
        for indices in itertools.combinations(range(len(matrix)), count):
            block = tuple(tuple(matrix[i][j] for j in indices) for i in indices)
            value = determinant(block)
            if not value.imag.is_zero():
                raise AlgebraicFieldError("Hermitian principal minor was not real")
            signs.append(value.real.sign())
    return tuple(signs)


def is_psd(matrix: AlgMatrix) -> bool:
    """Exact positive semidefiniteness via all principal minors."""

    if not is_hermitian(matrix):
        return False
    return all(sign >= 0 for sign in principal_minor_signs(matrix))


def real_trace(matrix: AlgMatrix) -> Surd:
    value = trace(matrix)
    if not value.imag.is_zero():
        raise AlgebraicFieldError("trace is not real")
    return value.real


def public_matrix(matrix: AlgMatrix) -> list[list[dict[str, object]]]:
    return [[item.public() for item in row] for row in matrix]


def compare(left: Surd, right: Surd) -> int:
    """Exact three-way comparison of two field elements."""

    return (left - right).sign()


__all__ = [
    "AONE",
    "AZERO",
    "AlgComplex",
    "AlgMatrix",
    "AlgebraicFieldError",
    "ENCLOSURE_DIGITS",
    "MAX_ALGEBRAIC_DIMENSION",
    "MAX_SQUAREFREE_RADICAND",
    "MAX_SQUARE_EXTRACTION_INPUT",
    "ONE",
    "Surd",
    "ZERO",
    "add",
    "compare",
    "dagger",
    "determinant",
    "enclosure",
    "identity",
    "is_hermitian",
    "is_psd",
    "is_zero_matrix",
    "matrix_from_pairs",
    "multiply",
    "principal_minor_signs",
    "public_matrix",
    "rational_text",
    "real_trace",
    "scalar_multiply",
    "square_free_part",
    "subtract",
    "sum_matrices",
    "trace",
    "zeros",
]
