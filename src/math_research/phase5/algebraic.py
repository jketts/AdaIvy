"""Exact arithmetic over one quadratic extension of the rationals per case.

The represented field is stated rather than implied::

    F_d = Q(sqrt(d))(i) = { (a + b*sqrt(d)) + i*(c + e*sqrt(d)) }

for one squarefree integer ``d >= 2``, with ``a, b, c, e`` rational.  ``d == 1``
denotes ``Q(i)``, which is compatible with every other radicand.  ADR-0035 binds
the radicand to be *measured* from a case's values, never declared, so this
module offers no way to assert a field a value does not live in.

Four things fall outside ``F_d`` and are typed rejections rather than
approximations (ADR-0035 field boundary):

* two distinct nontrivial radicands -> :class:`MixedRadicandError`
* a cubic or higher irreducible extension -> :class:`HigherDegreeExtensionError`
* a value declared non-algebraic -> :class:`TranscendentalValueError`
* any float, tolerance, or non-finite literal -> :class:`InexactValueError`

Everything here is exact.  There is no float, no ``decimal``, no ``math``
import, no tolerance and no epsilon on any path; sign and comparison are decided
by integer arithmetic on :class:`~fractions.Fraction` components.  Canonical
form is total, so ``sqrt(8)/2`` and ``sqrt(2)`` are one object with one
canonical JSON form and one digest.

Errors descend from ``QuantumInputError`` so the Phase 5 package keeps a single
error root, following the precedent in :mod:`math_research.phase5.quantum`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .quantum import QuantumInputError
from .serialization import sha256_bytes

VALUE_SCHEMA_VERSION = "adaivy.phase5-noncommuting-algebraic-value.v1"

# Bounds keep every exact operation terminating on adversarial input: the
# radicand bound bounds squarefree factoring, the denominator bound bounds
# intermediate integer growth in determinant expansion.
MAX_RADICAND = 10**6
MAX_DENOMINATOR = 10**12


class AlgebraicFieldError(QuantumInputError):
    """A value or operation falls outside the represented algebraic field."""

    reason_code = "outside_represented_field"


class MixedRadicandError(AlgebraicFieldError):
    """Two distinct nontrivial radicands need a degree-four real extension."""

    reason_code = "two_distinct_surds"


class HigherDegreeExtensionError(AlgebraicFieldError):
    """The value needs a cubic or higher irreducible extension."""

    reason_code = "cubic_or_higher_irreducible_extension"


class TranscendentalValueError(AlgebraicFieldError):
    """The value was declared non-algebraic.

    Detection is *not* claimed: ADR-0033 records that this slice cannot
    distinguish a high-degree algebraic optimum from a transcendental one from
    the values alone.  What is enforced is that a case may not *declare* a
    transcendental quantity and have it coerced into the field.
    """

    reason_code = "transcendental_value"


class InexactValueError(AlgebraicFieldError):
    """A float, tolerance, or non-finite literal reached the exact path."""

    reason_code = "inexact_or_tolerance_value"


FIELD_REJECTION_CODES = (
    HigherDegreeExtensionError.reason_code,
    InexactValueError.reason_code,
    MixedRadicandError.reason_code,
    TranscendentalValueError.reason_code,
)


def _integer_sqrt(value: int) -> int:
    """Exact integer square root by Newton iteration; no float is involved."""

    if value < 0:
        raise AlgebraicFieldError("integer square root of a negative integer")
    if value < 2:
        return value
    guess = 1 << ((value.bit_length() + 1) // 2)
    while True:
        candidate = (guess + value // guess) // 2
        if candidate >= guess:
            return guess
        guess = candidate


def _perfect_square_root(value: int) -> int | None:
    root = _integer_sqrt(value)
    return root if root * root == value else None


def _bounded(value: Fraction, label: str = "rational") -> Fraction:
    """Bound the size of a PARSED input component.

    The bound belongs on input, not on computed values: applying it to every
    intermediate would reject legitimate exact arithmetic on admissible input
    (a 2x2 determinant squares the denominators). Growth stays bounded anyway,
    because the dimension bound in `exact_matrices` bounds the degree of every
    polynomial in the entries.
    """

    if value.denominator > MAX_DENOMINATOR:
        raise AlgebraicFieldError(f"{label} denominator exceeds the exact Phase 5 bound")
    return value


def _fraction(value: Any) -> Fraction:
    """Parse an exact rational.  Integers and canonical strings only."""

    if isinstance(value, bool):
        raise AlgebraicFieldError("booleans are not rational values")
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, int):
        result = Fraction(value)
    elif isinstance(value, float):
        raise InexactValueError(
            "a floating-point value is outside the exact field; supply an "
            "integer or a canonical rational string"
        )
    elif isinstance(value, str):
        if "." in value or "e" in value.lower():
            # Fraction() would read "1.5" exactly as 3/2, but admitting the
            # spelling creates a second representation of one value.  The
            # canonical p/q form is the only accepted spelling.
            raise InexactValueError(
                f"decimal spelling {value!r} is not the canonical rational form; "
                "supply an integer or p/q"
            )
        try:
            result = Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise AlgebraicFieldError(f"invalid rational: {value!r}") from error
    else:
        raise AlgebraicFieldError("rational values must be integers or canonical strings")
    return result


def rational_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


_SQUAREFREE_CACHE: dict[int, tuple[int, int]] = {}


def _squarefree(radicand: Any) -> tuple[int, int]:
    """Split ``radicand`` into ``(squarefree_part, extracted_square_root)``."""

    if isinstance(radicand, bool) or not isinstance(radicand, int):
        raise AlgebraicFieldError("radicand must be an integer")
    if radicand < 1:
        raise AlgebraicFieldError(
            "radicand must be a positive integer; an imaginary radical is not a "
            "member of the represented real quadratic extension"
        )
    if radicand > MAX_RADICAND:
        raise AlgebraicFieldError("radicand exceeds the exact Phase 5 bound")
    cached = _SQUAREFREE_CACHE.get(radicand)
    if cached is not None:
        return cached
    extracted = 1
    remaining = radicand
    factor = 2
    while factor * factor <= remaining:
        square = factor * factor
        while remaining % square == 0:
            remaining //= square
            extracted *= factor
        factor += 1
    result = (remaining, extracted)
    _SQUAREFREE_CACHE[radicand] = result
    return result


@dataclass(frozen=True, slots=True, order=False)
class Quadratic:
    """``rational + surd*sqrt(radicand)`` in canonical form.

    Canonical means ``radicand`` is squarefree and ``>= 2`` when ``surd != 0``,
    and ``radicand == 1`` with ``surd == 0`` for a rational.  Build through
    :func:`quadratic`; the constructor only validates.
    """

    rational: Fraction
    surd: Fraction
    radicand: int

    def __post_init__(self) -> None:
        if not isinstance(self.rational, Fraction) or not isinstance(self.surd, Fraction):
            raise AlgebraicFieldError("quadratic components must be exact Fractions")
        if isinstance(self.radicand, bool) or not isinstance(self.radicand, int):
            raise AlgebraicFieldError("radicand must be an integer")
        if self.surd == 0:
            if self.radicand != 1:
                raise AlgebraicFieldError("a rational value must carry radicand 1")
        else:
            if self.radicand < 2:
                raise AlgebraicFieldError("an irrational value needs a radicand of at least 2")
            if _squarefree(self.radicand) != (self.radicand, 1):
                raise AlgebraicFieldError("radicand must be squarefree in canonical form")

    # -- structure ---------------------------------------------------------
    @property
    def is_rational(self) -> bool:
        return self.surd == 0

    def is_zero(self) -> bool:
        return self.rational == 0 and self.surd == 0

    def _radicand_with(self, other: "Quadratic") -> int:
        if self.is_rational:
            return other.radicand
        if other.is_rational:
            return self.radicand
        if self.radicand != other.radicand:
            raise MixedRadicandError(
                "mixed radicands sqrt(%d) and sqrt(%d) require a degree-four real "
                "extension, which is outside the represented field"
                % (self.radicand, other.radicand)
            )
        return self.radicand

    # -- arithmetic --------------------------------------------------------
    def __add__(self, other: "Quadratic") -> "Quadratic":
        radicand = self._radicand_with(other)
        return quadratic(self.rational + other.rational, self.surd + other.surd, radicand)

    def __neg__(self) -> "Quadratic":
        return quadratic(-self.rational, -self.surd, self.radicand)

    def __sub__(self, other: "Quadratic") -> "Quadratic":
        return self + (-other)

    def __mul__(self, other: "Quadratic") -> "Quadratic":
        radicand = self._radicand_with(other)
        return quadratic(
            self.rational * other.rational + self.surd * other.surd * radicand,
            self.rational * other.surd + self.surd * other.rational,
            radicand,
        )

    def field_conjugate(self) -> "Quadratic":
        """The nontrivial Galois conjugate ``a - b*sqrt(d)``."""

        return quadratic(self.rational, -self.surd, self.radicand)

    def norm(self) -> Fraction:
        """``N(a + b*sqrt(d)) = a^2 - b^2 d``, a rational."""

        return self.rational * self.rational - self.surd * self.surd * self.radicand

    def reciprocal(self) -> "Quadratic":
        norm = self.norm()
        if norm == 0:
            # sqrt(d) is irrational for squarefree d >= 2, so a^2 = b^2 d
            # forces a = b = 0.
            raise AlgebraicFieldError("division by an exact zero")
        return quadratic(self.rational / norm, -self.surd / norm, self.radicand)

    def __truediv__(self, other: "Quadratic") -> "Quadratic":
        return self * other.reciprocal()

    # -- exact total comparison inside one field ---------------------------
    def sign(self) -> int:
        """Exact sign in ``{-1, 0, 1}``.  No epsilon and no threshold."""

        if self.surd == 0:
            return (self.rational > 0) - (self.rational < 0)
        if self.rational == 0:
            return (self.surd > 0) - (self.surd < 0)
        rational_sign = 1 if self.rational > 0 else -1
        surd_sign = 1 if self.surd > 0 else -1
        if rational_sign == surd_sign:
            return rational_sign
        left = self.rational * self.rational
        right = self.surd * self.surd * self.radicand
        if left == right:  # unreachable for squarefree d >= 2; kept total
            return 0
        return rational_sign if left > right else surd_sign

    def compare(self, other: "Quadratic") -> int:
        return (self - other).sign()

    def __lt__(self, other: "Quadratic") -> bool:
        return self.compare(other) < 0

    def __le__(self, other: "Quadratic") -> bool:
        return self.compare(other) <= 0

    def __gt__(self, other: "Quadratic") -> bool:
        return self.compare(other) > 0

    def __ge__(self, other: "Quadratic") -> bool:
        return self.compare(other) >= 0

    def exact_sqrt(self) -> "Quadratic":
        """The exact nonnegative square root when it stays inside the field."""

        if self.sign() < 0:
            raise AlgebraicFieldError("square root of a negative element")
        if self.is_rational:
            return rational_sqrt(self.rational)
        discriminant = self.norm()
        root = rational_sqrt_or_none(discriminant)
        if root is None:
            raise HigherDegreeExtensionError(
                "the square root of this element needs a degree-four extension, "
                "which is outside the represented field"
            )
        for candidate in ((self.rational + root) / 2, (self.rational - root) / 2):
            if candidate < 0:
                continue
            outer = rational_sqrt_or_none(candidate)
            if outer is None or outer == 0:
                continue
            inner = self.surd / (2 * outer)
            result = quadratic(outer, inner, self.radicand)
            if result * result == self:
                return result
        raise HigherDegreeExtensionError(
            "the square root of this element is outside the represented field"
        )

    # -- serialization -----------------------------------------------------
    def canonical(self) -> str | dict[str, Any]:
        if self.surd == 0:
            return rational_text(self.rational)
        return {
            "radicand": self.radicand,
            "rational": rational_text(self.rational),
            "surd": rational_text(self.surd),
        }


def quadratic(rational: Any = 0, surd: Any = 0, radicand: Any = 1) -> Quadratic:
    """Canonical :class:`Quadratic` for ``rational + surd*sqrt(radicand)``."""

    rational_part = _fraction(rational)
    surd_part = _fraction(surd)
    if surd_part == 0:
        _squarefree(radicand)  # still validated, so sqrt(-1) is rejected
        return Quadratic(rational_part, Fraction(0), 1)
    squarefree, extracted = _squarefree(radicand)
    surd_part = surd_part * extracted
    if squarefree == 1:
        return Quadratic(rational_part + surd_part, Fraction(0), 1)
    return Quadratic(rational_part, surd_part, squarefree)


def rational_sqrt_or_none(value: Fraction) -> Fraction | None:
    if value < 0:
        return None
    numerator = _perfect_square_root(value.numerator)
    denominator = _perfect_square_root(value.denominator)
    if numerator is None or denominator is None:
        return None
    return Fraction(numerator, denominator)


def rational_sqrt(value: Fraction) -> Quadratic:
    """``sqrt(n/m) = sqrt(n*m)/m`` exactly, as a canonical quadratic."""

    if value < 0:
        raise AlgebraicFieldError("square root of a negative rational")
    exact = rational_sqrt_or_none(value)
    if exact is not None:
        return quadratic(exact)
    return quadratic(0, Fraction(1, value.denominator), value.numerator * value.denominator)


RATIONAL_ZERO = quadratic(0)
RATIONAL_ONE = quadratic(1)


@dataclass(frozen=True, slots=True)
class AlgebraicComplex:
    """``real + i*imag`` with both parts in one quadratic extension of Q."""

    real: Quadratic
    imag: Quadratic

    def __post_init__(self) -> None:
        if not isinstance(self.real, Quadratic) or not isinstance(self.imag, Quadratic):
            raise AlgebraicFieldError("complex parts must be canonical quadratics")
        self.real._radicand_with(self.imag)

    # -- structure ---------------------------------------------------------
    @property
    def radicand(self) -> int:
        return self.real.radicand if not self.real.is_rational else self.imag.radicand

    @property
    def is_rational(self) -> bool:
        return self.real.is_rational and self.imag.is_rational

    def is_zero(self) -> bool:
        return self.real.is_zero() and self.imag.is_zero()

    def is_real(self) -> bool:
        return self.imag.is_zero()

    # -- arithmetic --------------------------------------------------------
    def __add__(self, other: "AlgebraicComplex") -> "AlgebraicComplex":
        return AlgebraicComplex(self.real + other.real, self.imag + other.imag)

    def __neg__(self) -> "AlgebraicComplex":
        return AlgebraicComplex(-self.real, -self.imag)

    def __sub__(self, other: "AlgebraicComplex") -> "AlgebraicComplex":
        return self + (-other)

    def __mul__(self, other: "AlgebraicComplex") -> "AlgebraicComplex":
        return AlgebraicComplex(
            self.real * other.real - self.imag * other.imag,
            self.real * other.imag + self.imag * other.real,
        )

    def conjugate(self) -> "AlgebraicComplex":
        return AlgebraicComplex(self.real, -self.imag)

    def modulus_squared(self) -> Quadratic:
        return self.real * self.real + self.imag * self.imag

    def reciprocal(self) -> "AlgebraicComplex":
        modulus = self.modulus_squared()
        if modulus.is_zero():
            raise AlgebraicFieldError("division by an exact zero")
        inverse = modulus.reciprocal()
        return AlgebraicComplex(self.real * inverse, -self.imag * inverse)

    def __truediv__(self, other: "AlgebraicComplex") -> "AlgebraicComplex":
        return self * other.reciprocal()

    def real_part(self, label: str) -> Quadratic:
        """The real part, rejecting a value that must be real but is not."""

        if not self.is_real():
            raise AlgebraicFieldError(f"{label} is not real")
        return self.real

    # -- serialization -----------------------------------------------------
    def canonical(self) -> str | dict[str, Any]:
        if self.imag.is_zero():
            return self.real.canonical()
        return {"im": self.imag.canonical(), "re": self.real.canonical()}

    def value_hash(self) -> str:
        return sha256_bytes(exact_bytes(self.canonical()))


ZERO = AlgebraicComplex(RATIONAL_ZERO, RATIONAL_ZERO)
ONE = AlgebraicComplex(RATIONAL_ONE, RATIONAL_ZERO)
IMAGINARY_UNIT = AlgebraicComplex(RATIONAL_ZERO, RATIONAL_ONE)


_QUADRATIC_KEYS = frozenset({"radicand", "rational", "surd"})
_COMPLEX_KEYS = frozenset({"im", "re"})
_TRANSCENDENTAL_KEYS = frozenset({"transcendental"})


def parse_quadratic(value: Any) -> Quadratic:
    """Parse the canonical real form: a rational, or a surd object."""

    if isinstance(value, Quadratic):
        return value
    if isinstance(value, dict):
        keys = frozenset(value)
        if keys == _TRANSCENDENTAL_KEYS:
            raise TranscendentalValueError(
                "a declared transcendental quantity (%r) is outside every algebraic "
                "number field and is rejected rather than approximated"
                % (value["transcendental"],)
            )
        if keys == _COMPLEX_KEYS:
            raise AlgebraicFieldError(
                "a complex value cannot appear where a real part is required"
            )
        if keys != _QUADRATIC_KEYS:
            raise AlgebraicFieldError(
                "an algebraic real requires exactly radicand, rational and surd"
            )
        return quadratic(
            _bounded(_fraction(value["rational"]), "rational part"),
            _bounded(_fraction(value["surd"]), "surd part"),
            value["radicand"],
        )
    return quadratic(_bounded(_fraction(value)))


def parse_algebraic(value: Any) -> AlgebraicComplex:
    """Parse the canonical value form into an :class:`AlgebraicComplex`."""

    if isinstance(value, AlgebraicComplex):
        return value
    if isinstance(value, Quadratic):
        return AlgebraicComplex(value, RATIONAL_ZERO)
    if isinstance(value, dict) and frozenset(value) == _COMPLEX_KEYS:
        return AlgebraicComplex(parse_quadratic(value["re"]), parse_quadratic(value["im"]))
    return AlgebraicComplex(parse_quadratic(value), RATIONAL_ZERO)


def algebraic(rational: Any = 0, surd: Any = 0, radicand: Any = 1) -> AlgebraicComplex:
    """A real algebraic value, for construction in code rather than JSON."""

    return AlgebraicComplex(quadratic(rational, surd, radicand), RATIONAL_ZERO)


def imaginary(rational: Any = 0, surd: Any = 0, radicand: Any = 1) -> AlgebraicComplex:
    return AlgebraicComplex(RATIONAL_ZERO, quadratic(rational, surd, radicand))


def measure_radicand(values: Any) -> int:
    """The single nontrivial radicand MEASURED from a structure of values.

    ADR-0035 requires the radicand to be measured, not declared, so this is the
    only way the field of a case is determined.  A structure mixing two distinct
    nontrivial radicands is rejected here, before any arithmetic combines them,
    because it is not contained in any single represented field.
    """

    found = 1
    stack = [values]
    while stack:
        item = stack.pop()
        if isinstance(item, AlgebraicComplex):
            candidates = (item.real.radicand, item.imag.radicand)
        elif isinstance(item, Quadratic):
            candidates = (item.radicand,)
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
            continue
        else:
            raise AlgebraicFieldError("radicand survey reached a non-algebraic value")
        for candidate in candidates:
            if candidate == 1:
                continue
            if found not in (1, candidate):
                raise MixedRadicandError(
                    "values mix sqrt(%d) and sqrt(%d); a single quadratic extension "
                    "cannot represent both" % (found, candidate)
                )
            found = candidate
    return found


def join_radicands(left: int, right: int) -> int:
    """The common radicand of two measured fields, or a typed rejection."""

    if left == 1:
        return right
    if right == 1:
        return left
    if left != right:
        raise MixedRadicandError(
            "the ensemble lives in Q(sqrt(%d)) and the certificate in Q(sqrt(%d)); "
            "one case must live in one quadratic extension" % (left, right)
        )
    return left


def reject_inexact(value: Any, path: str = "$") -> None:
    """Fail closed on any float, complex, or otherwise non-exact JSON leaf."""

    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return
    if isinstance(value, (float, complex)):
        raise InexactValueError(f"inexact numeric value at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AlgebraicFieldError(f"non-string key at {path}")
            reject_inexact(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_inexact(item, f"{path}[{index}]")
        return
    raise AlgebraicFieldError(f"unserializable value at {path}")


def exact_bytes(value: Any) -> bytes:
    """Deterministic serialization.  Floats are rejected, never rounded."""

    reject_inexact(value)
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def exact_hash(value: Any) -> str:
    return sha256_bytes(exact_bytes(value))


def field_descriptor(radicand: int) -> dict[str, Any]:
    """The measured field, recorded next to every measurement.

    Both degrees are recorded because they differ and conflating them
    understates the field: ``Q(sqrt d)`` is degree two over ``Q`` while
    ``Q(sqrt d)(i)`` is degree four, and ``Q(i)`` is degree two rather than one.
    """

    return {
        "schema_version": VALUE_SCHEMA_VERSION,
        "degree_over_rationals": 2 if radicand == 1 else 4,
        "kind": "quadratic_extension_of_rationals_with_imaginary_unit",
        "notation": "Q(i)" if radicand == 1 else f"Q(sqrt({radicand}))(i)",
        "outside_field": [
            "a value needing two distinct square roots, for example sqrt(2)+sqrt(3)",
            "a value needing a cubic or higher irreducible extension",
            "a value declared transcendental",
            "any floating-point or tolerance-based approximation",
        ],
        "radicand": radicand,
        "radicand_source": "measured_from_case_values",
        "real_subfield_degree_over_rationals": 1 if radicand == 1 else 2,
        "tolerance": None,
    }


__all__ = [
    "FIELD_REJECTION_CODES",
    "IMAGINARY_UNIT",
    "MAX_DENOMINATOR",
    "MAX_RADICAND",
    "ONE",
    "RATIONAL_ONE",
    "RATIONAL_ZERO",
    "VALUE_SCHEMA_VERSION",
    "ZERO",
    "AlgebraicComplex",
    "AlgebraicFieldError",
    "HigherDegreeExtensionError",
    "InexactValueError",
    "MixedRadicandError",
    "Quadratic",
    "TranscendentalValueError",
    "algebraic",
    "exact_bytes",
    "exact_hash",
    "field_descriptor",
    "imaginary",
    "join_radicands",
    "measure_radicand",
    "parse_algebraic",
    "parse_quadratic",
    "quadratic",
    "rational_sqrt",
    "rational_sqrt_or_none",
    "rational_text",
    "reject_inexact",
]
