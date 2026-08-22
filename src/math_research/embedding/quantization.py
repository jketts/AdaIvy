"""Provider floats -> exact integers, exactly once, at ingestion.

A provider returns IEEE-754 doubles. Every double is exactly a dyadic rational,
so ``Fraction(value)`` is an exact conversion with no interpretation. Scaling by
a declared power of two and rounding half-to-even yields the integer the artifact
stores; the float is then discarded and never reconstructed.

The scale is the ``normalization`` component of the partition key, so a change of
scale is a change of partition and therefore a full rebuild -- not a migration.

Saturation is a FAULT. `ADR-0069`: "A saturating coordinate is a fault, not a
rounding detail, and halts ingestion." The declared scale represents the closed
interval ``[-1, 1]``, which is where an L2-normalized embedding coordinate lives;
a coordinate outside it means the model is not the model the partition declares,
and clamping would hide that behind a plausible number.

This module is NOT on the replay path. It is the one place a float legitimately
exists, and it exists only between the provider response and the integer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Sequence

from .constants import NORMALIZATION_SCHEMES
from .errors import CoordinateSaturatedError, NormalizationUnknownError

#: Magnitude the declared scale represents, as an exact rational.
SATURATION_MAGNITUDE = Fraction(1, 1)


def scale_exponent(normalization: str) -> int:
    try:
        return NORMALIZATION_SCHEMES[normalization]
    except KeyError as error:
        raise NormalizationUnknownError(repr(normalization)) from error


def scale_factor(normalization: str) -> int:
    return 1 << scale_exponent(normalization)


def round_half_even(value: Fraction) -> int:
    """Exact round-half-to-even on a rational. No float, no ``decimal``."""

    floor_value = value.numerator // value.denominator
    remainder = value - floor_value
    doubled = remainder * 2
    if doubled < 1:
        return floor_value
    if doubled > 1:
        return floor_value + 1
    return floor_value if floor_value % 2 == 0 else floor_value + 1


@dataclass(frozen=True, slots=True, kw_only=True)
class QuantizedVector:
    normalization: str
    scale_exponent: int
    coordinates: tuple[int, ...]
    #: Always zero in a vector that exists: saturation halts ingestion. Recorded
    #: so the ingestion record states the count rather than leaving it implied.
    saturated_coordinate_count: int = 0


def quantize_coordinate(value: object, *, normalization: str, position: int = 0) -> int:
    exponent = scale_exponent(normalization)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CoordinateSaturatedError(
            f"coordinate[{position}] is not a real number: {value!r}",
            code="coordinate_not_real",
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise CoordinateSaturatedError(
            f"coordinate[{position}] is not finite: {value!r}",
            code="coordinate_not_finite",
        )
    exact = Fraction(value)
    if exact > SATURATION_MAGNITUDE or exact < -SATURATION_MAGNITUDE:
        raise CoordinateSaturatedError(
            f"coordinate[{position}] magnitude {exact} exceeds the "
            f"declared scale {normalization}; this is a fault, not a rounding detail"
        )
    return round_half_even(exact * (1 << exponent))


def quantize(values: Sequence[object], *, normalization: str) -> QuantizedVector:
    """Convert a provider vector once. Halts on the first saturating coordinate."""

    exponent = scale_exponent(normalization)
    if not values:
        raise CoordinateSaturatedError(
            "provider returned no coordinates", code="coordinate_vector_empty",
        )
    coordinates = tuple(
        quantize_coordinate(value, normalization=normalization, position=index)
        for index, value in enumerate(values)
    )
    return QuantizedVector(
        normalization=normalization, scale_exponent=exponent,
        coordinates=coordinates, saturated_coordinate_count=0,
    )


__all__ = [
    "QuantizedVector",
    "SATURATION_MAGNITUDE",
    "quantize",
    "quantize_coordinate",
    "round_half_even",
    "scale_exponent",
    "scale_factor",
]
