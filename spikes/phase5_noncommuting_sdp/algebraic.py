"""Exact real-algebraic arithmetic over a single quadratic extension of Q.

The represented field is

    F_d = Q(sqrt(d))(i) = { (a + b*sqrt(d)) + i*(c + e*sqrt(d)) }

for one squarefree integer ``d >= 2`` per value, with ``a, b, c, e`` rational.
``d == 1`` denotes the rational subfield, which is compatible with every other
radicand.  Two values whose radicands are distinct and both nontrivial are
*outside* the field this module represents: ``sqrt(2) + sqrt(3)`` needs the
degree-four field ``Q(sqrt 2, sqrt 3)``, so it is rejected rather than coerced,
approximated, or silently promoted.

Everything here is exact.  There is no float, no ``decimal``, no ``math``
import, no tolerance, and no epsilon comparison anywhere on this path;
comparison is decided by integer sign arithmetic on ``Fraction`` components.

Canonicalization is total: a value has exactly one in-memory representation and
exactly one canonical JSON form, so ``sqrt(8)/2`` and ``sqrt(2)`` are the same
object and hash to the same digest.

Following the ``QuantumInputError`` precedent in
``src/math_research/phase5/quantum.py``, every rejection raises one explicit
exception type, ``AlgebraicFieldError``.  The validator's
``CertificateInputError`` is a subclass of it, so the whole spike has a single
error root and no rejection can be mistaken for a coercion.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from typing import Any


SCHEMA_VERSION = "adaivy.phase5-noncommuting-algebraic-value.v1"

# Bounds keep every exact operation terminating on adversarial input.  The
# radicand bound bounds squarefree factoring; the denominator bound bounds the
# size of intermediate integers in determinant expansion.
MAX_RADICAND = 10**6
MAX_DENOMINATOR = 10**12


class AlgebraicFieldError(ValueError):
    """A value or operation falls outside the represented algebraic field."""


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


def _fraction(value: Any) -> Fraction:
    """Parse an exact rational.  Integers and canonical strings only."""

    if isinstance(value, bool):
        raise AlgebraicFieldError("booleans are not rational values")
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, int):
        result = Fraction(value)
    elif isinstance(value, float):
        raise AlgebraicFieldError(
            "floating-point values are outside the exact field; supply an "
            "integer or a canonical rational string"
        )
    elif isinstance(value, str):
        try:
            result = Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise AlgebraicFieldError(f"invalid rational: {value!r}") from error
    else:
        raise AlgebraicFieldError("rational values must be integers or canonical strings")
    if result.denominator > MAX_DENOMINATOR:
        raise AlgebraicFieldError("rational denominator exceeds the exact spike bound")
    return result


def _rational_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _squarefree(radicand: int) -> tuple[int, int]:
    """Split ``radicand`` into ``(squarefree_part, extracted_square_root)``."""

    if isinstance(radicand, bool) or not isinstance(radicand, int):
        raise AlgebraicFieldError("radicand must be an integer")
    if radicand < 1:
        raise AlgebraicFieldError(
            "radicand must be a positive integer; an imaginary radical is not a "
            "member of the represented real quadratic extension"
        )
    if radicand > MAX_RADICAND:
        raise AlgebraicFieldError("radicand exceeds the exact spike bound")
    extracted = 1
    remaining = radicand
    factor = 2
    while factor * factor <= remaining:
        square = factor * factor
        while remaining % square == 0:
            remaining //= square
            extracted *= factor
        factor += 1
    return remaining, extracted


@dataclass(frozen=True, slots=True, order=False)
class Quadratic:
    """``rational + surd * sqrt(radicand)`` in canonical form.

    Canonical means: ``radicand`` is squarefree and ``>= 2`` when ``surd != 0``,
    and ``radicand == 1`` with ``surd == 0`` for a rational.  Construct through
    :func:`quadratic`; the constructor only validates.
    """

    rational: Fraction
    surd: Fraction
    radicand: int

    def __post_init__(self) -> None:
        if not isinstance(self.rational, Fraction) or not isinstance(self.surd, Fraction):
            raise AlgebraicFieldError("quadratic components must be Fractions")
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
            raise AlgebraicFieldError(
                "mixed radicands sqrt(%d) and sqrt(%d) require a degree-four "
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
        """Exact sign in ``{-1, 0, 1}``; no epsilon is involved."""

        if self.surd == 0:
            return (self.rational > 0) - (self.rational < 0)
        if self.rational == 0:
            return (self.surd > 0) - (self.surd < 0)
        rational_sign = 1 if self.rational > 0 else -1
        surd_sign = 1 if self.surd > 0 else -1
        if rational_sign == surd_sign:
            return rational_sign
        # Opposite signs: compare squared magnitudes exactly.
        left = self.rational * self.rational
        right = self.surd * self.surd * self.radicand
        if left == right:
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
        # sqrt(a + b sqrt d) = x + y sqrt d requires x^2 + y^2 d = a and
        # 2xy = b, so x^2 is a rational root of t^2 - a t + b^2 d / 4.
        discriminant = self.norm()
        root = rational_sqrt_or_none(discriminant)
        if root is None:
            raise AlgebraicFieldError(
                "square root of this element needs a degree-four extension, "
                "which is outside the represented field"
            )
        for candidate in ((self.rational + root) / 2, (self.rational - root) / 2):
            if candidate < 0:
                continue
            outer = rational_sqrt_or_none(candidate)
            if outer is None:
                continue
            if outer == 0:
                continue
            inner = self.surd / (2 * outer)
            result = quadratic(outer, inner, self.radicand)
            if result * result == self:
                return result
        raise AlgebraicFieldError(
            "square root of this element is outside the represented field"
        )

    # -- serialization -----------------------------------------------------
    def canonical(self) -> str | dict[str, Any]:
        if self.surd == 0:
            return _rational_text(self.rational)
        return {
            "rational": _rational_text(self.rational),
            "surd": _rational_text(self.surd),
            "radicand": self.radicand,
        }


def quadratic(rational: Any = 0, surd: Any = 0, radicand: int = 1) -> Quadratic:
    """Build the canonical :class:`Quadratic` for ``rational + surd*sqrt(radicand)``."""

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
        return {"re": self.real.canonical(), "im": self.imag.canonical()}

    def value_hash(self) -> str:
        return sha256_bytes(canonical_bytes(self.canonical()))


ZERO = AlgebraicComplex(RATIONAL_ZERO, RATIONAL_ZERO)
ONE = AlgebraicComplex(RATIONAL_ONE, RATIONAL_ZERO)
IMAGINARY_UNIT = AlgebraicComplex(RATIONAL_ZERO, RATIONAL_ONE)


_QUADRATIC_KEYS = frozenset({"rational", "surd", "radicand"})
_COMPLEX_KEYS = frozenset({"re", "im"})


def parse_quadratic(value: Any) -> Quadratic:
    """Parse the canonical real form: a rational, or a surd object."""

    if isinstance(value, Quadratic):
        return value
    if isinstance(value, dict):
        keys = frozenset(value)
        if keys == _COMPLEX_KEYS:
            raise AlgebraicFieldError("a complex value cannot appear where a real part is required")
        if keys != _QUADRATIC_KEYS:
            raise AlgebraicFieldError(
                "an algebraic real requires exactly rational, surd and radicand"
            )
        radicand = value["radicand"]
        if isinstance(radicand, bool) or not isinstance(radicand, int):
            raise AlgebraicFieldError("radicand must be an integer")
        return quadratic(value["rational"], value["surd"], radicand)
    return quadratic(value)


def parse_algebraic(value: Any) -> AlgebraicComplex:
    """Parse the canonical value form into an :class:`AlgebraicComplex`."""

    if isinstance(value, AlgebraicComplex):
        return value
    if isinstance(value, Quadratic):
        return AlgebraicComplex(value, RATIONAL_ZERO)
    if isinstance(value, dict) and frozenset(value) == _COMPLEX_KEYS:
        return AlgebraicComplex(parse_quadratic(value["re"]), parse_quadratic(value["im"]))
    return AlgebraicComplex(parse_quadratic(value), RATIONAL_ZERO)


def algebraic(rational: Any = 0, surd: Any = 0, radicand: int = 1) -> AlgebraicComplex:
    """A real algebraic value, for construction in code rather than JSON."""

    return AlgebraicComplex(quadratic(rational, surd, radicand), RATIONAL_ZERO)


def imaginary(rational: Any = 0, surd: Any = 0, radicand: int = 1) -> AlgebraicComplex:
    return AlgebraicComplex(RATIONAL_ZERO, quadratic(rational, surd, radicand))


def common_radicand(values: Any) -> int:
    """The single nontrivial radicand of a nested structure of values.

    Rejects a structure that mixes two distinct nontrivial radicands, because
    such a structure is not contained in any single represented field even when
    no arithmetic has combined the two yet.
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
                raise AlgebraicFieldError(
                    "certificate mixes sqrt(%d) and sqrt(%d); a single quadratic "
                    "extension cannot represent both" % (found, candidate)
                )
            found = candidate
    return found


def reject_floats(value: Any, path: str = "$") -> None:
    """Fail closed on any float, complex, or otherwise non-exact JSON leaf."""

    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return
    if isinstance(value, (float, complex)):
        raise AlgebraicFieldError(f"inexact numeric value at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AlgebraicFieldError(f"non-string key at {path}")
            reject_floats(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            reject_floats(item, f"{path}[{index}]")
        return
    raise AlgebraicFieldError(f"unserializable value at {path}")


def canonical_bytes(value: Any) -> bytes:
    """Deterministic serialization.  Floats are rejected, never rounded."""

    reject_floats(value)
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def field_descriptor(radicand: int) -> dict[str, Any]:
    """The represented field, recorded next to every measurement."""

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "quadratic_extension_of_rationals_with_imaginary_unit",
        "radicand": radicand,
        "degree_over_rationals": 2 if radicand != 1 else 1,
        "notation": "Q(i)" if radicand == 1 else f"Q(sqrt({radicand}))(i)",
        "outside_field": [
            "a value needing two distinct square roots, for example sqrt(2)+sqrt(3)",
            "a value needing a cubic or higher irreducible extension",
            "a transcendental value",
            "any floating-point or tolerance-based approximation",
        ],
    }


__all__ = [
    "MAX_DENOMINATOR",
    "MAX_RADICAND",
    "SCHEMA_VERSION",
    "AlgebraicComplex",
    "AlgebraicFieldError",
    "IMAGINARY_UNIT",
    "ONE",
    "Quadratic",
    "RATIONAL_ONE",
    "RATIONAL_ZERO",
    "ZERO",
    "algebraic",
    "canonical_bytes",
    "canonical_hash",
    "common_radicand",
    "field_descriptor",
    "imaginary",
    "parse_algebraic",
    "parse_quadratic",
    "quadratic",
    "rational_sqrt",
    "rational_sqrt_or_none",
    "reject_floats",
    "sha256_bytes",
]
