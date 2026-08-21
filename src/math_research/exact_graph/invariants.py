"""Graffiti 322's left-hand side, under each contested reading of "Even".

Graffiti 322 compares ``InvEven(G)`` with the "range" of the distance
spectrum.  Neither term is unambiguous in the source, and the ambiguity is not
cosmetic: it decides whether a witness refutes.  This module refuses to hide
that.  ``even_count`` takes the reading as an argument and has no default, so
no caller can compute an Inverse Even value without recording which reading it
used.

``even_includes_v`` counts ``v`` itself, because ``d(v, v) = 0`` and zero is
even.  ``even_excludes_v`` does not.  Both are computed from the same exact
breadth-first distances; the difference is one vertex per term, and on the
shipped G(14,18) witness it moves the Inverse Even value from ``40049/4444`` to
``8772568/953095``.  Both exceed nine.

Every value is a :class:`fractions.Fraction`.  A zero denominator is a typed
refusal (``even_count_zero``); this module never returns an infinity, a
sentinel, or a float.
"""

from __future__ import annotations

from fractions import Fraction

from .graph import ExactGraphError, Graph, bfs_distances

# One choice per contested term, frozen.  Order is load-bearing: it fixes the
# order of the reading tuples in :mod:`math_research.exact_graph.replay`.
EVEN_READINGS = ("even_includes_v", "even_excludes_v")


class InvariantError(ExactGraphError):
    """An Even/Inverse Even value cannot be computed exactly as asked."""


def _reading(reading: str) -> str:
    if reading not in EVEN_READINGS:
        raise InvariantError("even_reading_unknown", str(reading))
    return reading


def even_count(g: Graph, v: int, reading: str) -> int:
    """Number of vertices at even graph distance from ``v`` under ``reading``.

    Distance ``0`` is even, so ``even_includes_v`` counts ``v`` and
    ``even_excludes_v`` does not.  Refuses ``graph_not_connected`` rather than
    treating an unreachable vertex as being at no distance at all.
    """

    reading = _reading(reading)
    distances = bfs_distances(g, v)
    count = sum(1 for item in distances if item % 2 == 0)
    if reading == "even_excludes_v":
        count -= 1
    return count


def inverse_even(g: Graph, reading: str) -> Fraction:
    """``sum_v 1 / Even(v)`` as an exact rational.

    Refuses ``even_count_zero`` when some vertex has an empty even-distance set
    under the requested reading.  Under ``even_excludes_v`` that is reachable:
    the centre of a star has no other vertex at even distance.  Returning an
    infinity there would let a graph "refute" 322 by division by zero.
    """

    reading = _reading(reading)
    total = Fraction(0)
    for v in range(g.order):
        count = even_count(g, v, reading)
        if count == 0:
            raise InvariantError("even_count_zero", f"vertex:{v};reading:{reading}")
        total += Fraction(1, count)
    return total


def even_count_profile(g: Graph, reading: str) -> tuple[tuple[int, int], ...]:
    """``(even_count, number_of_vertices)`` pairs, sorted by count.

    Reported so a reviewer can see the classification the shipped derivation
    asserts in prose ("three even-distance counts") as a computed value.
    """

    reading = _reading(reading)
    tally: dict[int, int] = {}
    for v in range(g.order):
        count = even_count(g, v, reading)
        tally[count] = tally.get(count, 0) + 1
    return tuple(sorted(tally.items()))
