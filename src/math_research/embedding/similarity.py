"""Exact integer cosine comparison. No float, no division, no square root.

Ranking by cosine is ranking by ``dot(u,v) / sqrt(|u|^2 |v|^2)``. That quotient
is irrational in general, so computing it needs a float and a float comparison
sits on machine noise -- and a tie at the boundary becomes undecidable in exactly
the way ``exact_graph`` refuses to be. So no cosine is ever computed here.

Each candidate is carried as the pair ``(dot, norm_squared(u) * norm_squared(v))``
and two candidates are compared by cross-multiplying integers. Squaring the dot
product removes the sign, so the sign is compared FIRST and the cross-multiplied
result is inverted when both dot products are negative. A tie returns ``0``;
callers break ties by ``document_id`` ascending, matching ``fusion.py:204`` and
``lexical.py:42``.

This module is on the replay path. :mod:`readpath` sweeps it for float
construction and division, and `pr.no-float-in-retrieval-path` asserts it clean.
"""

from __future__ import annotations

import functools
from typing import Sequence

from .errors import (
    NonIntegerCoordinateError,
    PartitionMismatchError,
    ZeroNormVectorError,
)
from .partition import PartitionKey, PartitionedVector


def _exact_vector(value: Sequence[int], where: str) -> tuple[int, ...]:
    if not isinstance(value, tuple):
        value = tuple(value)
    if not value:
        raise NonIntegerCoordinateError(f"{where} must be non-empty")
    for index, item in enumerate(value):
        if not isinstance(item, int) or isinstance(item, bool):
            raise NonIntegerCoordinateError(f"{where}[{index}] is not an exact integer")
    return value


def _same_length(u: tuple[int, ...], v: tuple[int, ...]) -> None:
    if len(u) != len(v):
        raise PartitionMismatchError(
            "dimension", f"operand lengths {len(u)} and {len(v)} differ"
        )


def dot(u: tuple[int, ...], v: tuple[int, ...]) -> int:
    """Exact integer inner product."""

    left = _exact_vector(u, "u")
    right = _exact_vector(v, "v")
    _same_length(left, right)
    total = 0
    for index in range(len(left)):
        total += left[index] * right[index]
    return total


def norm_squared(u: tuple[int, ...]) -> int:
    """Exact ``|u|^2``. Never ``|u|``: the square root would be irrational."""

    left = _exact_vector(u, "u")
    total = 0
    for value in left:
        total += value * value
    return total


def cosine_terms(u: tuple[int, ...], v: tuple[int, ...]) -> tuple[int, int]:
    """``(dot(u,v), norm_squared(u) * norm_squared(v))``; second element > 0.

    A zero vector has no direction, so its cosine is undefined rather than zero.
    That is a refusal, not a silently-ranked candidate.
    """

    left = _exact_vector(u, "u")
    right = _exact_vector(v, "v")
    _same_length(left, right)
    product = norm_squared(left) * norm_squared(right)
    if product <= 0:
        raise ZeroNormVectorError("cosine is undefined for a zero-norm vector")
    return dot(left, right), product


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _checked_terms(terms: tuple[int, int], where: str) -> tuple[int, int]:
    if not isinstance(terms, tuple) or len(terms) != 2:
        raise NonIntegerCoordinateError(f"{where} must be a (dot, norm_squared_product) pair")
    numerator, denominator = terms
    for name, value in (("dot", numerator), ("norm_squared_product", denominator)):
        if not isinstance(value, int) or isinstance(value, bool):
            raise NonIntegerCoordinateError(f"{where}.{name} is not an exact integer")
    if denominator <= 0:
        raise ZeroNormVectorError(f"{where}.norm_squared_product must be positive")
    return numerator, denominator


def compare_cosine(a: tuple[int, int], b: tuple[int, int]) -> int:
    """``-1``, ``0`` or ``+1``: is ``a``'s cosine less than, equal to, or greater
    than ``b``'s? Exact and square-root free.

    ``cos = dot / sqrt(n)`` with ``n > 0``. Comparing two such quantities by
    squaring is valid only within a sign class, because squaring is not
    monotone across zero, so:

    * signs differ -> the positive dot product has the larger cosine;
    * both dot products non-negative -> ``da^2 * nb`` vs ``db^2 * na``, larger
      cross-product means larger cosine;
    * both dot products negative -> the same cross-product, then inverted,
      because a larger magnitude means a more negative cosine.
    """

    da, na = _checked_terms(a, "a")
    db, nb = _checked_terms(b, "b")
    sign_a = _sign(da)
    sign_b = _sign(db)
    if sign_a != sign_b:
        return 1 if sign_a > sign_b else -1
    if sign_a == 0:
        return 0
    left = da * da * nb
    right = db * db * na
    if left == right:
        return 0
    ordering = 1 if left > right else -1
    return -ordering if sign_a < 0 else ordering


def require_same_partition(
    left: PartitionedVector, right: PartitionedVector,
) -> PartitionKey:
    """Refuse any comparison whose operands are in different partitions.

    `TECHNICAL_BLUEPRINT.md:1661-1663`: "A query vector is only ever compared
    against vectors in its own partition. There is no default or fallback
    partition." Two same-dimension models from different vendors produce a
    silently degraded index, so this is a refusal and never a coercion.
    """

    for component in ("provider", "model_identifier", "dimension", "normalization"):
        mine = getattr(left.partition_key, component)
        theirs = getattr(right.partition_key, component)
        if mine != theirs:
            raise PartitionMismatchError(
                component, f"{mine!r} against {theirs!r}"
            )
    return left.partition_key


def cosine_terms_within_partition(
    left: PartitionedVector, right: PartitionedVector,
) -> tuple[int, int]:
    require_same_partition(left, right)
    return cosine_terms(left.coordinates, right.coordinates)


def rank_exact_cosine(
    query: PartitionedVector, candidates: Sequence[PartitionedVector],
) -> tuple[tuple[str, tuple[int, int]], ...]:
    """Order candidates by exact cosine descending, then ``document_id`` ascending.

    This is an ordering primitive over already-frozen artifacts, not retrieval:
    it generates no query, reads no corpus, fuses no signal, and produces no
    report. Phase 4C is untouched by this slice.
    """

    scored: list[tuple[str, tuple[int, int]]] = []
    for candidate in candidates:
        scored.append((
            candidate.document_id,
            cosine_terms_within_partition(query, candidate),
        ))
    # Two passes over a stable sort: document_id ascending first, then cosine
    # descending. Equal cosines therefore retain document_id ascending order,
    # independent of the caller's input order and of the hash seed.
    scored.sort(key=lambda item: item[0])
    scored.sort(key=functools.cmp_to_key(
        lambda left, right: compare_cosine(right[1], left[1])
    ))
    return tuple(scored)


__all__ = [
    "compare_cosine",
    "cosine_terms",
    "cosine_terms_within_partition",
    "dot",
    "norm_squared",
    "rank_exact_cosine",
    "require_same_partition",
]
