"""Measure which field an ensemble's exact optimum actually lives in.

This module answers one question exactly: is the optimum of a supplied small
discrimination instance representable in a single quadratic extension of the
rationals?  It never approximates an eigenvalue and never returns a tolerance.

Two independent measurements are produced.

* :func:`spectral_field_report` computes the exact characteristic polynomial of
  the difference operator, peels every rational root, and reports the degree of
  the residual factor.  A residual cubic with no rational root is irreducible
  over Q, so its roots generate a degree-three extension and the trace norm --
  and therefore the optimum -- is provably *outside* the represented field.
  That is a measured boundary, not a limitation of the arithmetic.

* :func:`two_state_optimum` computes the closed-form Helstrom optimum for a
  two-outcome instance in dimension two, exactly, and reports it unavailable
  with a recorded reason otherwise.  It is an independent cross-check on a
  supplied certificate: duality already proves optimality when the gap is zero,
  so a disagreement here means the certificate or the checker is wrong.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from .algebraic import (
    RATIONAL_ONE,
    RATIONAL_ZERO,
    AlgebraicFieldError,
    Quadratic,
    quadratic,
    rational_sqrt,
)
from .matrices import (
    Matrix,
    determinant,
    is_hermitian,
    power,
    subtract,
    sum_matrices,
    trace,
)


SCHEMA_VERSION = "adaivy.phase5-noncommuting-field-probe.v1"

# Bounds the rational-root divisor enumeration.
MAX_ROOT_SEARCH_INTEGER = 10**9


def _absolute(value: Quadratic) -> Quadratic:
    return -value if value.sign() < 0 else value


def characteristic_polynomial(matrix: Matrix) -> tuple[Quadratic, ...]:
    """Coefficients from the leading term down, via Newton's identities.

    Returns ``(1, c_1, ..., c_n)`` for ``lambda^n + c_1 lambda^{n-1} + ... + c_n``.
    Requires a Hermitian matrix, so every coefficient is real.
    """

    if not is_hermitian(matrix):
        raise AlgebraicFieldError("characteristic polynomial probe requires a Hermitian matrix")
    size = len(matrix)
    power_traces = [
        trace(power(matrix, k)).real_part(f"trace of the {k}-th power")
        for k in range(1, size + 1)
    ]
    elementary = [RATIONAL_ONE]
    for k in range(1, size + 1):
        accumulator = RATIONAL_ZERO
        for i in range(1, k + 1):
            term = elementary[k - i] * power_traces[i - 1]
            accumulator = accumulator + (term if i % 2 == 1 else -term)
        elementary.append(accumulator * quadratic(Fraction(1, k)))
    return tuple(
        elementary[j] if j % 2 == 0 else -elementary[j] for j in range(size + 1)
    )


def _integer_coefficients(coefficients: tuple[Quadratic, ...]) -> tuple[int, ...] | None:
    if any(not item.is_rational for item in coefficients):
        return None
    denominator = 1
    for item in coefficients:
        denominator = denominator * item.rational.denominator // _gcd(
            denominator, item.rational.denominator
        )
    scaled = tuple(item.rational * denominator for item in coefficients)
    if any(value.denominator != 1 for value in scaled):
        return None
    return tuple(int(value) for value in scaled)


def _gcd(left: int, right: int) -> int:
    while right:
        left, right = right, left % right
    return abs(left)


def _divisors(value: int) -> tuple[int, ...]:
    value = abs(value)
    if value == 0 or value > MAX_ROOT_SEARCH_INTEGER:
        raise AlgebraicFieldError("rational-root divisor enumeration exceeded its bound")
    found: list[int] = []
    candidate = 1
    while candidate * candidate <= value:
        if value % candidate == 0:
            found.append(candidate)
            if candidate != value // candidate:
                found.append(value // candidate)
        candidate += 1
    return tuple(sorted(found))


def _evaluate(coefficients: tuple[Fraction, ...], point: Fraction) -> Fraction:
    result = Fraction(0)
    for item in coefficients:
        result = result * point + item
    return result


def _deflate(coefficients: tuple[Fraction, ...], root: Fraction) -> tuple[Fraction, ...]:
    quotient: list[Fraction] = []
    carry = Fraction(0)
    for item in coefficients[:-1]:
        carry = carry * root + item
        quotient.append(carry)
    return tuple(quotient)


def peel_rational_roots(
    coefficients: tuple[Fraction, ...],
) -> tuple[tuple[Fraction, ...], tuple[Fraction, ...]]:
    """Return ``(rational_roots_with_multiplicity, residual_coefficients)``."""

    roots: list[Fraction] = []
    working = coefficients
    while len(working) > 1:
        if working[-1] == 0:
            roots.append(Fraction(0))
            working = working[:-1]
            continue
        integers = _integer_coefficients(tuple(quadratic(item) for item in working))
        if integers is None:  # pragma: no cover - rationals always scale
            break
        found: Fraction | None = None
        for numerator in _divisors(integers[-1]):
            for denominator in _divisors(integers[0]):
                for sign in (1, -1):
                    candidate = Fraction(sign * numerator, denominator)
                    if _evaluate(working, candidate) == 0:
                        found = candidate
                        break
                if found is not None:
                    break
            if found is not None:
                break
        if found is None:
            break
        roots.append(found)
        working = _deflate(working, found)
    return tuple(sorted(roots)), working


def _sign_variations(coefficients: tuple[Fraction, ...]) -> int:
    signs = [1 if item > 0 else -1 for item in coefficients if item != 0]
    return sum(1 for left, right in zip(signs, signs[1:]) if left != right)


def real_root_signature(coefficients: tuple[Fraction, ...]) -> dict[str, int]:
    """Exact counts of positive, zero and negative roots.

    Descartes' rule of signs bounds the number of positive roots by the number
    of sign variations, with equality when every root is real.  The caller
    guarantees a Hermitian operator, so every root is real and the counts are
    exact rather than bounds.  Only integer sign comparisons are involved.
    """

    trailing = 0
    while len(coefficients) - trailing > 1 and coefficients[-1 - trailing] == 0:
        trailing += 1
    reduced = coefficients[: len(coefficients) - trailing]
    reflected = tuple(
        item if (len(reduced) - 1 - index) % 2 == 0 else -item
        for index, item in enumerate(reduced)
    )
    return {
        "positive": _sign_variations(reduced),
        "negative": _sign_variations(reflected),
        "zero": trailing,
    }


def _trace_norm_argument(
    signature: dict[str, int], first_coefficient: Quadratic, residual_degree: int
) -> str:
    """State exactly how far the probe can push the degree argument."""

    traceless = first_coefficient.is_zero()
    counts = (
        "every root is real: %(positive)d positive, %(negative)d negative, %(zero)d zero"
        % signature
    )
    if traceless and signature["negative"] == 1 and signature["zero"] == 0:
        return (
            counts
            + ". The operator is traceless with exactly one negative root, so the trace "
            "norm equals -2 times that root. That root is a root of an irreducible "
            "factor of degree %d, hence has degree %d over the rationals, so it is not "
            "of the form a + b*sqrt(d) with a and b rational."
            % (residual_degree, residual_degree)
        )
    if traceless and signature["positive"] == 1 and signature["zero"] == 0:
        return (
            counts
            + ". The operator is traceless with exactly one positive root, so the trace "
            "norm equals 2 times that root, an algebraic number of degree %d."
            % residual_degree
        )
    return (
        counts
        + ". The trace norm is a rational combination of roots of an irreducible factor "
        "of degree %d. This probe does not reduce it to a single root, so it reports the "
        "case as outside the represented field without claiming an exact degree."
        % residual_degree
    )


def spectral_field_report(matrix: Matrix, label: str) -> dict[str, Any]:
    """Exactly classify the field generated by ``matrix``'s eigenvalues."""

    coefficients = characteristic_polynomial(matrix)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "operator": label,
        "dimension": len(matrix),
        "characteristic_polynomial": [item.canonical() for item in coefficients],
    }
    if any(not item.is_rational for item in coefficients):
        report.update(
            {
                "determination": "undetermined_irrational_coefficients",
                "rational_roots": None,
                "residual_degree": None,
                "residual_irreducible": None,
                "eigenvalue_radicand": None,
                "representable_in_quadratic_extension": False,
                "reason": (
                    "the characteristic polynomial has irrational coefficients, so "
                    "rational-root peeling does not apply and the eigenvalue field is "
                    "not determined by this probe"
                ),
            }
        )
        return report
    rationals = tuple(item.rational for item in coefficients)
    report["real_root_signature"] = real_root_signature(rationals)
    roots, residual = peel_rational_roots(rationals)
    residual_degree = len(residual) - 1
    report["rational_roots"] = [
        (str(item.numerator) if item.denominator == 1 else f"{item.numerator}/{item.denominator}")
        for item in roots
    ]
    report["residual_degree"] = residual_degree
    if residual_degree == 0:
        report.update(
            {
                "determination": "rational_spectrum",
                "residual_irreducible": None,
                "eigenvalue_radicand": 1,
                "representable_in_quadratic_extension": True,
                "reason": None,
            }
        )
        return report
    if residual_degree == 2:
        lead, middle, constant = residual
        discriminant = middle * middle - 4 * lead * constant
        if discriminant < 0:  # pragma: no cover - Hermitian spectra are real
            raise AlgebraicFieldError("Hermitian operator produced a negative discriminant")
        radicand = rational_sqrt(discriminant).radicand
        report.update(
            {
                "determination": "quadratic_spectrum",
                "residual_irreducible": True,
                "discriminant": (
                    str(discriminant.numerator)
                    if discriminant.denominator == 1
                    else f"{discriminant.numerator}/{discriminant.denominator}"
                ),
                "eigenvalue_radicand": radicand,
                "representable_in_quadratic_extension": True,
                "reason": None,
            }
        )
        return report
    report.update(
        {
            "determination": (
                "irreducible_cubic_spectrum" if residual_degree == 3 else "higher_degree_spectrum"
            ),
            "residual_irreducible": True if residual_degree == 3 else None,
            "eigenvalue_radicand": None,
            "representable_in_quadratic_extension": False,
            "reason": (
                "the residual factor has degree %d with no rational root, so the "
                "eigenvalues generate an extension of degree at least three; the "
                "trace norm and therefore the exact optimum lie outside every "
                "quadratic extension of the rationals" % residual_degree
            ),
            "trace_norm_argument": _trace_norm_argument(
                report["real_root_signature"],
                coefficients[1],
                residual_degree,
            ),
        }
    )
    return report


def _two_state_optimum_value(
    weighted_states: tuple[Matrix, ...],
) -> tuple[Quadratic | None, str | None]:
    """The exact optimum as a field element, or ``(None, reason)``."""

    if len(weighted_states) != 2 or len(weighted_states[0]) != 2:
        return None, (
            "the exact closed form implemented here covers two outcomes in "
            "dimension two only; no closed form is claimed for this shape"
        )
    difference = subtract(weighted_states[0], weighted_states[1])
    difference_trace = trace(difference).real_part("difference operator trace")
    difference_determinant = determinant(difference).real_part("difference operator determinant")
    if difference_determinant.sign() < 0:
        # Opposite-sign eigenvalues, so the trace norm is the spectral spread.
        spread = (
            difference_trace * difference_trace - quadratic(4) * difference_determinant
        )
        try:
            trace_norm = spread.exact_sqrt()
        except AlgebraicFieldError as error:
            return None, str(error)
    else:
        # Same-sign or zero eigenvalues, so the trace norm is |trace|.
        trace_norm = _absolute(difference_trace)
    total_trace = trace(sum_matrices(list(weighted_states))).real_part("ensemble trace")
    return (total_trace + trace_norm) * quadratic(Fraction(1, 2)), None


def two_state_optimum(weighted_states: tuple[Matrix, ...]) -> dict[str, Any]:
    """The exact Helstrom optimum for two outcomes in dimension two."""

    optimum, reason = _two_state_optimum_value(weighted_states)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "closed_form": "helstrom_two_state_dimension_two",
        "available": optimum is not None,
        "optimum": None if optimum is None else optimum.canonical(),
        "optimum_is_rational": None if optimum is None else optimum.is_rational,
        "optimum_radicand": None if optimum is None else optimum.radicand,
        "reason": reason,
    }
    return report


def exact_two_state_optimum(weighted_states: tuple[Matrix, ...]) -> Quadratic | None:
    """The optimum as a field element, or ``None`` when unavailable."""

    return _two_state_optimum_value(weighted_states)[0]


__all__ = [
    "MAX_ROOT_SEARCH_INTEGER",
    "SCHEMA_VERSION",
    "characteristic_polynomial",
    "real_root_signature",
    "exact_two_state_optimum",
    "peel_rational_roots",
    "spectral_field_report",
    "two_state_optimum",
]
