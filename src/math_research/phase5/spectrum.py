"""Measure which field an ensemble's exact optimum lives in, and cross-check it.

Two exact measurements live here.  Neither searches and neither produces a
certificate.

* :func:`spectral_field_report` computes the exact characteristic polynomial of
  the difference operator, peels every rational root, and reports the degree of
  the residual factor.  A residual cubic with no rational root is irreducible
  over ``Q``, so its roots have degree three, and the trace norm -- therefore
  the optimum -- is provably outside every quadratic extension.  That is the
  measured field boundary ADR-0035 keeps visible in every run, not a limitation
  of the arithmetic.

* :func:`closed_form_crosscheck` evaluates the exact two-state Helstrom optimum
  for two outcomes in dimension two and reports itself unavailable with a
  recorded reason otherwise.  It yields a *scalar value* used to cross-check a
  supplied certificate.  It yields no POVM and no dual operator, so it is not a
  certificate and cannot stand in for one: a case with no supplied certificate
  stays unresolved even where this cross-check is available.

The probe is conservative in one direction only.  A residual quartic that
happens to factor into two rational quadratics of the same square class is in
fact representable and is reported as outside the field; a three-outcome case is
reported unrepresentable regardless of its actual optimum.  It can under-claim
representability, never over-claim it.  It also cannot distinguish a
high-degree algebraic optimum from a transcendental one, and does not claim to.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from .algebraic import (
    RATIONAL_ONE,
    RATIONAL_ZERO,
    AlgebraicFieldError,
    HigherDegreeExtensionError,
    Quadratic,
    quadratic,
    rational_sqrt,
    rational_text,
)
from .exact_matrices import (
    Matrix,
    determinant,
    is_hermitian,
    power,
    subtract,
    sum_matrices,
    trace,
)

PROBE_SCHEMA_VERSION = "adaivy.phase5-noncommuting-field-probe.v1"
CROSSCHECK_SCHEMA_VERSION = "adaivy.phase5-noncommuting-closed-form-crosscheck.v1"

# Bounds the rational-root divisor enumeration.
MAX_ROOT_SEARCH_INTEGER = 10**9


def _absolute(value: Quadratic) -> Quadratic:
    return -value if value.sign() < 0 else value


def characteristic_polynomial(matrix: Matrix) -> tuple[Quadratic, ...]:
    """Coefficients from the leading term down, via Newton's identities.

    Returns ``(1, c_1, ..., c_n)`` for ``x^n + c_1 x^(n-1) + ... + c_n``.
    Requires a Hermitian matrix, so every coefficient is real.
    """

    if not is_hermitian(matrix):
        raise AlgebraicFieldError("the field probe requires a Hermitian matrix")
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
    return tuple(elementary[j] if j % 2 == 0 else -elementary[j] for j in range(size + 1))


def _gcd(left: int, right: int) -> int:
    while right:
        left, right = right, left % right
    return abs(left)


def _integer_coefficients(coefficients: tuple[Fraction, ...]) -> tuple[int, ...]:
    denominator = 1
    for item in coefficients:
        denominator = denominator * item.denominator // _gcd(denominator, item.denominator)
    scaled = tuple(item * denominator for item in coefficients)
    if any(value.denominator != 1 for value in scaled):  # pragma: no cover - exact by construction
        raise AlgebraicFieldError("clearing denominators did not produce integers")
    return tuple(int(value) for value in scaled)


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
    """Return ``(rational_roots_with_multiplicity, residual_coefficients)``.

    This is exact factor extraction over ``Q``, not a numerical root finder: a
    candidate is admitted only when the polynomial evaluates to exactly zero.
    """

    roots: list[Fraction] = []
    working = coefficients
    while len(working) > 1:
        if working[-1] == 0:
            roots.append(Fraction(0))
            working = working[:-1]
            continue
        integers = _integer_coefficients(working)
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
    of sign variations and differs from it by an even number, so equality holds
    when every root is real.  The caller guarantees a Hermitian operator, so
    every root is real and these counts are exact rather than bounds.  Only
    integer sign comparisons are involved.
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
        "negative": _sign_variations(reflected),
        "positive": _sign_variations(reduced),
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
        "schema_version": PROBE_SCHEMA_VERSION,
        "characteristic_polynomial": [item.canonical() for item in coefficients],
        "dimension": len(matrix),
        "distinguishes_high_degree_from_transcendental": False,
        "operator": label,
        "tolerance": None,
    }
    if any(not item.is_rational for item in coefficients):
        report.update(
            {
                "determination": "undetermined_irrational_coefficients",
                "eigenvalue_radicand": None,
                "rational_roots": None,
                "reason": (
                    "the characteristic polynomial has irrational coefficients, so "
                    "rational-root peeling does not apply and the eigenvalue field is "
                    "not determined by this probe"
                ),
                "representable_in_quadratic_extension": False,
                "residual_degree": None,
                "residual_irreducible": None,
            }
        )
        return report
    rationals = tuple(item.rational for item in coefficients)
    report["real_root_signature"] = real_root_signature(rationals)
    roots, residual = peel_rational_roots(rationals)
    residual_degree = len(residual) - 1
    report["rational_roots"] = [rational_text(item) for item in roots]
    report["residual_degree"] = residual_degree
    if residual_degree == 0:
        report.update(
            {
                "determination": "rational_spectrum",
                "eigenvalue_radicand": 1,
                "reason": None,
                "representable_in_quadratic_extension": True,
                "residual_irreducible": None,
            }
        )
        return report
    if residual_degree == 2:
        lead, middle, constant = residual
        discriminant = middle * middle - 4 * lead * constant
        if discriminant < 0:  # pragma: no cover - Hermitian spectra are real
            raise AlgebraicFieldError("a Hermitian operator produced a negative discriminant")
        report.update(
            {
                "determination": "quadratic_spectrum",
                "discriminant": rational_text(discriminant),
                "eigenvalue_radicand": rational_sqrt(discriminant).radicand,
                "reason": None,
                "representable_in_quadratic_extension": True,
                "residual_irreducible": True,
            }
        )
        return report
    report.update(
        {
            "determination": (
                "irreducible_cubic_spectrum" if residual_degree == 3 else "higher_degree_spectrum"
            ),
            "eigenvalue_radicand": None,
            "reason": (
                "the residual factor has degree %d with no rational root, so the "
                "eigenvalues generate an extension of degree at least three; the trace "
                "norm and therefore the exact optimum lie outside every quadratic "
                "extension of the rationals" % residual_degree
            ),
            "rejection_reason_code": HigherDegreeExtensionError.reason_code,
            "representable_in_quadratic_extension": False,
            "residual_irreducible": True if residual_degree == 3 else None,
            "trace_norm_argument": _trace_norm_argument(
                report["real_root_signature"], coefficients[1], residual_degree
            ),
        }
    )
    return report


def _closed_form_value(
    weighted_states: tuple[Matrix, ...],
) -> tuple[Quadratic | None, str | None]:
    """The exact two-state optimum as a field element, or ``(None, reason)``."""

    if len(weighted_states) != 2 or len(weighted_states[0]) != 2:
        return None, (
            "the exact closed form implemented here covers two outcomes in dimension "
            "two only; no closed form is claimed for this shape"
        )
    difference = subtract(weighted_states[0], weighted_states[1])
    difference_trace = trace(difference).real_part("difference operator trace")
    difference_determinant = determinant(difference).real_part("difference operator determinant")
    if difference_determinant.sign() < 0:
        # Opposite-sign eigenvalues, so the trace norm is the spectral spread.
        spread = difference_trace * difference_trace - quadratic(4) * difference_determinant
        try:
            trace_norm = spread.exact_sqrt()
        except AlgebraicFieldError as error:
            return None, str(error)
    else:
        # Same-sign or zero eigenvalues, so the trace norm is |trace|.
        trace_norm = _absolute(difference_trace)
    total_trace = trace(sum_matrices(list(weighted_states))).real_part("ensemble trace")
    return (total_trace + trace_norm) * quadratic(Fraction(1, 2)), None


def closed_form_crosscheck(weighted_states: tuple[Matrix, ...]) -> dict[str, Any]:
    """Report the exact two-state Helstrom optimum used as a cross-check.

    This is explicitly not a discovery path and explicitly not a certificate: it
    returns a scalar, never a POVM or a dual operator, so it cannot close a case
    on its own.
    """

    optimum, reason = _closed_form_value(weighted_states)
    return {
        "schema_version": CROSSCHECK_SCHEMA_VERSION,
        "available": optimum is not None,
        "closed_form": "helstrom_two_state_dimension_two",
        "is_certificate": False,
        "is_discovery": False,
        "optimum": None if optimum is None else optimum.canonical(),
        "optimum_is_rational": None if optimum is None else optimum.is_rational,
        "optimum_radicand": None if optimum is None else optimum.radicand,
        "produces_dual_operator": False,
        "produces_povm": False,
        "reason": reason,
        "role": "independent_crosscheck_of_a_supplied_certificate",
    }


def closed_form_optimum(weighted_states: tuple[Matrix, ...]) -> Quadratic | None:
    """The cross-check optimum as a field element, or ``None`` when unavailable."""

    return _closed_form_value(weighted_states)[0]


__all__ = [
    "CROSSCHECK_SCHEMA_VERSION",
    "MAX_ROOT_SEARCH_INTEGER",
    "PROBE_SCHEMA_VERSION",
    "characteristic_polynomial",
    "closed_form_crosscheck",
    "closed_form_optimum",
    "peel_rational_roots",
    "real_root_signature",
    "spectral_field_report",
]
