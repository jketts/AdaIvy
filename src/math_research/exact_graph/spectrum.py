"""Exact distance spectra: counts, extents, and verified decompositions.

Nothing here is numerical.  Coefficients are integers, comparisons are made in
``fractions.Fraction``, and every quantity that cannot be decided exactly is a
typed refusal.  There is no tolerance, no epsilon, no ``float``, and no
iteration toward an eigenvalue.

Three boundaries are enforced.

* **"Range" has two readings and they are not interchangeable.**
  ``range_distinct_count`` is ``|spec(D)|``; ``range_extent`` is
  ``lambda_max - lambda_min``.  Both are computed here, exactly, and the caller
  must say which one it means.

* **A distinct-eigenvalue count is proved, never sampled.**  For a symmetric
  integer matrix every eigenvalue is real and the minimal polynomial is
  squarefree, so ``deg(minpoly(D))`` *is* the number of distinct eigenvalues.
  :func:`minimal_polynomial` builds a candidate by exact Krylov elimination on
  deterministic seeds and then **confirms** it by checking ``p(D) e_i = 0`` for
  every standard basis vector.  Agreement across several seeds is evidence, not
  proof: a single seed's annihilator only divides the minimal polynomial.  An
  unconfirmed candidate is refused (``minimal_polynomial_unconfirmed``), and
  :func:`distinct_eigenvalue_lower_bound` exists precisely so the cheap,
  provably-one-sided result is reported as the one-sided result it is.

* **An operator-supplied decomposition is verified, never trusted.**
  :func:`verify_decomposition` checks the dimension sum, the exact eigenvector
  relation on every scalar basis vector, the exact quotient action on every
  quotient basis vector, and full rank of the whole witness over ``Q``.  Only
  then does it count distinct roots of the product of the small block
  polynomials.  Any mismatch is a refusal, never a warning.  Dropping the rank
  check would make the count unsound, so it is not optional.

Polynomial convention, frozen: a polynomial is a tuple of ``int`` coefficients
in **descending** degree order, so ``(1, 0, -12, -16, 0)`` is
``x^4 - 12 x^2 - 16 x``.  This never changes.

Matrix convention for a quotient block, frozen: ``Q`` acts on coordinate
column vectors, i.e. ``D v_j = sum_i Q[i][j] v_i`` for the supplied basis
``v_0, ..., v_{k-1}``.  This never changes either.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fractions import Fraction
from math import gcd
from operator import mul
from typing import Any, Iterable, Mapping, Sequence

from .graph import (
    ExactGraphError,
    Graph,
    bfs_distances,
    graffiti_family,
    graffiti_family_layout,
)

# One choice per contested term, frozen; see EVEN_READINGS in ``invariants``.
RANGE_READINGS = ("range_distinct_count", "range_extent")

BLOCKS_SCHEMA_VERSION = "adaivy.exact-graph-decomposition-blocks.v1"

# Honest declared bound for the *dense* route, i.e. the route that needs a
# characteristic or minimal polynomial of the whole distance matrix and a
# confirmation pass over a full basis.  The confirmation is O(order * degree)
# exact matrix-vector products, so the cost is measured, not guessed; see
# ``tests/test_exact_graph_engine.py::test_dense_route_cost_bound_is_measured``.
# Above this bound the dense route refuses and a verified decomposition (or the
# one-sided Krylov lower bound) is required.
MAX_DENSE_ORDER = 512

# Bounds the rational-root divisor enumeration used to pin exact rational
# spectral extremes.  Beyond it, exact-rational detection reports itself
# unavailable rather than guessing.
MAX_ROOT_ENUMERATION = 10**9

# Bounds root isolation and interval refinement.  Exceeding either is a typed
# refusal, never a returned approximation.
MAX_ISOLATION_STEPS = 512
MAX_REFINEMENT_STEPS = 512

_ZERO_POLY: tuple[int, ...] = (0,)


class SpectrumError(ExactGraphError):
    """A spectral quantity cannot be produced exactly under the stated bounds."""


# --------------------------------------------------------------------------
# Exact integer polynomial arithmetic, descending coefficient order.
# --------------------------------------------------------------------------


def _normalize(poly: Iterable[Any]) -> tuple[int, ...]:
    items = list(poly)
    for item in items:
        if isinstance(item, bool) or not isinstance(item, int):
            raise SpectrumError("polynomial_not_integral", f"coefficient:{item!r}")
    index = 0
    while index < len(items) - 1 and items[index] == 0:
        index += 1
    trimmed = tuple(items[index:])
    return trimmed if trimmed else _ZERO_POLY


def _is_zero(poly: tuple[int, ...]) -> bool:
    return all(item == 0 for item in poly)


def _degree(poly: tuple[int, ...]) -> int:
    poly = _normalize(poly)
    return -1 if _is_zero(poly) else len(poly) - 1


def _derivative(poly: tuple[int, ...]) -> tuple[int, ...]:
    n = len(poly) - 1
    return _normalize([poly[i] * (n - i) for i in range(n)]) if n >= 1 else _ZERO_POLY


def _content(poly: tuple[int, ...]) -> int:
    value = 0
    for item in poly:
        value = gcd(value, abs(item))
    return value or 1


def _primitive(poly: tuple[int, ...]) -> tuple[int, ...]:
    poly = _normalize(poly)
    divisor = _content(poly)
    return _normalize([item // divisor for item in poly])


def _poly_mul(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
    if _is_zero(a) or _is_zero(b):
        return _ZERO_POLY
    result = [0] * (len(a) + len(b) - 1)
    for i, left in enumerate(a):
        if left:
            for j, right in enumerate(b):
                result[i + j] += left * right
    return _normalize(result)


def _pseudo_remainder(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
    """``lc(b)^(deg a - deg b + 1) * a  mod  b``, entirely in ``Z``."""

    if _is_zero(b):
        raise SpectrumError("polynomial_division_by_zero", "pseudo_remainder")
    a = _normalize(a)
    b = _normalize(b)
    if _degree(a) < _degree(b):
        return a
    lead_b = b[0]
    steps = _degree(a) - _degree(b) + 1
    work = list(a)
    for _ in range(steps):
        lead = work[0]
        work = [lead_b * item for item in work]
        for j in range(len(b)):
            work[j] -= lead * b[j]
        work = work[1:]
        if not work:
            return _ZERO_POLY
    return _normalize(work)


def _poly_gcd(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
    """Primitive greatest common divisor over ``Q``, via a primitive PRS.

    Content is removed at every step so integer coefficients cannot blow up.
    """

    a, b = _normalize(a), _normalize(b)
    if _is_zero(a):
        return _primitive(b) if not _is_zero(b) else _ZERO_POLY
    if _is_zero(b):
        return _primitive(a)
    if _degree(a) < _degree(b):
        a, b = b, a
    a, b = _primitive(a), _primitive(b)
    while not _is_zero(b):
        a, b = b, _primitive(_pseudo_remainder(a, b))
    return a


def _poly_div_exact(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[Fraction, ...]:
    """Exact quotient over ``Q``; refuses when ``b`` does not divide ``a``."""

    a = _normalize(a)
    b = _normalize(b)
    if _is_zero(b):
        raise SpectrumError("polynomial_division_by_zero", "exact_division")
    if _is_zero(a):
        return (Fraction(0),)
    if _degree(a) < _degree(b):
        raise SpectrumError("polynomial_division_inexact", "degree")
    work = [Fraction(item) for item in a]
    quotient: list[Fraction] = []
    lead_b = Fraction(b[0])
    for _ in range(_degree(a) - _degree(b) + 1):
        factor = work[0] / lead_b
        quotient.append(factor)
        for j in range(len(b)):
            work[j] -= factor * b[j]
        if work[0] != 0:
            raise SpectrumError("polynomial_division_inexact", "leading_residue")
        work = work[1:]
    if any(item != 0 for item in work):
        raise SpectrumError("polynomial_division_inexact", "remainder")
    return tuple(quotient)


def _monic_integer(poly: Sequence[Fraction]) -> tuple[int, ...]:
    items = list(poly)
    while len(items) > 1 and items[0] == 0:
        items = items[1:]
    if not items or items[0] == 0:
        raise SpectrumError("polynomial_not_monic", "zero_leading_coefficient")
    scaled = [item / items[0] for item in items]
    if any(item.denominator != 1 for item in scaled):
        raise SpectrumError("polynomial_not_integral", "monic_form_not_integral")
    return _normalize([int(item) for item in scaled])


def _poly_lcm(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
    """Monic integer least common multiple of two monic integer polynomials."""

    if _degree(a) < 0:
        return _normalize(b)
    if _degree(b) < 0:
        return _normalize(a)
    divisor = _poly_gcd(a, b)
    return _monic_integer(_poly_div_exact(_poly_mul(a, b), divisor))


def _evaluate(poly: tuple[int, ...], point: Fraction) -> Fraction:
    result = Fraction(0)
    for item in poly:
        result = result * point + item
    return result


def _divisors(value: int) -> tuple[int, ...]:
    value = abs(value)
    if value == 0 or value > MAX_ROOT_ENUMERATION:
        raise SpectrumError("rational_root_enumeration_bound", f"value:{value}")
    found: list[int] = []
    candidate = 1
    while candidate * candidate <= value:
        if value % candidate == 0:
            found.append(candidate)
            other = value // candidate
            if other != candidate:
                found.append(other)
        candidate += 1
    return tuple(sorted(found))


def _rational_roots(poly: tuple[int, ...]) -> tuple[Fraction, ...] | None:
    """Every rational root of a squarefree integer polynomial, or ``None``.

    ``None`` means the divisor enumeration bound was exceeded, so exact rational
    detection is *unavailable*.  It never means "there are none".
    """

    poly = _primitive(poly)
    if _degree(poly) < 1:
        return ()
    roots: list[Fraction] = []
    work = list(poly)
    while len(work) > 1 and work[-1] == 0:
        roots.append(Fraction(0))
        work = work[:-1]
    stripped = _normalize(work)
    if _degree(stripped) < 1:
        return tuple(sorted(set(roots)))
    try:
        numerators = _divisors(stripped[-1])
        denominators = _divisors(stripped[0])
    except SpectrumError:
        return None
    for numerator in numerators:
        for denominator in denominators:
            for sign in (1, -1):
                candidate = Fraction(sign * numerator, denominator)
                if _evaluate(stripped, candidate) == 0:
                    roots.append(candidate)
    return tuple(sorted(set(roots)))


def _deflate_rational(poly: tuple[int, ...], roots: Iterable[Fraction]) -> tuple[int, ...]:
    """Divide out ``(x - r)`` for each supplied rational root, exactly.

    A monic integer polynomial has only integer rational roots, so this is exact
    synthetic division with an exactly-zero remainder; a nonzero remainder means
    the caller supplied a non-root and is refused.
    """

    work = [Fraction(item) for item in _normalize(poly)]
    for root in roots:
        if len(work) < 2:
            raise SpectrumError("polynomial_division_inexact", f"root:{root}")
        quotient: list[Fraction] = []
        carry = Fraction(0)
        for item in work[:-1]:
            carry = item + carry * root
            quotient.append(carry)
        if work[-1] + carry * root != 0:
            raise SpectrumError("polynomial_division_inexact", f"root:{root}")
        work = quotient
    return _monic_integer(work)


def _common_denominator(items: Iterable[Fraction]) -> int:
    value = 1
    for item in items:
        value = value * item.denominator // gcd(value, item.denominator)
    return value


# --------------------------------------------------------------------------
# Distance matrices and cheap exact bounds.
# --------------------------------------------------------------------------


def distance_matrix(g: Graph) -> tuple[tuple[int, ...], ...]:
    """The all-pairs graph distance matrix, by breadth-first search, in ``Z``.

    Refuses ``graph_not_connected``: an entry of the distance matrix of a
    disconnected graph does not exist, and this package will not invent one.
    """

    return tuple(bfs_distances(g, v) for v in range(g.order))


def total_distance(g: Graph) -> int:
    """``1^T D 1``, the sum of distances over all *ordered* pairs (twice the
    Wiener index).  Exact integer."""

    return sum(sum(row) for row in distance_matrix(g))


def rayleigh_extent_bound(g: Graph) -> Fraction:
    """An exact rational strict lower bound for ``lambda_max - lambda_min``.

    The Rayleigh quotient of ``D`` at the all-ones vector is
    ``(1^T D 1) / (1^T 1) = 2W/n``, a rational, and it is at most
    ``lambda_max``.  ``trace(D) = 0`` and ``D != 0`` force ``lambda_min < 0``,
    so ``lambda_max - lambda_min > lambda_max >= 2W/n``.  The bound therefore
    settles ``range_extent`` comparisons outright whenever it already exceeds
    the value being compared, with no eigenvalue work at all.

    On an order-one graph ``D = 0`` and the extent is exactly ``0``; the
    returned ``0`` is then the value itself, not a strict bound, which is why
    :func:`spectral_extent_vs` remains the only decider of the general case.
    """

    if g.order < 2:
        _ = distance_matrix(g)
        return Fraction(0)
    return Fraction(total_distance(g), g.order)


def _require_square_symmetric(m: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    rows = tuple(tuple(row) for row in m)
    n = len(rows)
    if n == 0 or any(len(row) != n for row in rows):
        raise SpectrumError("matrix_not_square", f"rows:{n}")
    for row in rows:
        for item in row:
            if isinstance(item, bool) or not isinstance(item, int):
                raise SpectrumError("matrix_not_integral", f"entry:{item!r}")
    for i in range(n):
        for j in range(i + 1, n):
            if rows[i][j] != rows[j][i]:
                raise SpectrumError("matrix_not_symmetric", f"entry:{i},{j}")
    return rows


def _matvec(m: Sequence[Sequence[int]], v: Sequence[int]) -> list[int]:
    return [sum(map(mul, row, v)) for row in m]


# --------------------------------------------------------------------------
# Characteristic polynomial (division-free) and root counting.
# --------------------------------------------------------------------------


def characteristic_polynomial(m: Sequence[Sequence[int]]) -> tuple[int, ...]:
    """``det(lambda I - m)`` over ``Z``, by the division-free Samuelson-Berkowitz
    recursion.  Coefficients are returned in **descending** degree order and the
    result is monic.  The order is frozen and must never change.
    """

    rows = tuple(tuple(row) for row in m)
    n = len(rows)
    if n == 0 or any(len(row) != n for row in rows):
        raise SpectrumError("matrix_not_square", f"rows:{n}")
    poly: list[int] = [1]
    for k in range(n - 1, -1, -1):
        size = n - k
        a = rows[k][k]
        r_vec = [rows[k][j] for j in range(k + 1, n)]
        s_vec = [rows[i][k] for i in range(k + 1, n)]
        sub = [[rows[i][j] for j in range(k + 1, n)] for i in range(k + 1, n)]
        v: list[int] = [1, -a]
        w = list(s_vec)
        for _ in range(size - 1):
            v.append(-sum(map(mul, r_vec, w)))
            w = _matvec(sub, w)
        new = [
            sum(
                v[i - j] * poly[j]
                for j in range(max(0, i - size), min(i, size - 1) + 1)
            )
            for i in range(size + 1)
        ]
        poly = new
    return _normalize(poly)


def distinct_root_count(poly: Iterable[int]) -> int:
    """``deg(P / gcd(P, P'))`` over ``Q``: the number of distinct roots of ``P``.

    For the characteristic or minimal polynomial of a symmetric integer matrix
    every root is real, so this is ``|spec|``.  Exact; no root is ever located.
    """

    poly = _normalize(poly)
    if _degree(poly) < 1:
        raise SpectrumError("polynomial_degenerate", "degree_below_one")
    return _degree(poly) - _degree(_poly_gcd(poly, _derivative(poly)))


def squarefree_part(poly: Iterable[int]) -> tuple[int, ...]:
    """``P / gcd(P, P')`` as a monic integer polynomial: the radical of ``P``."""

    poly = _normalize(poly)
    if _degree(poly) < 1:
        raise SpectrumError("polynomial_degenerate", "degree_below_one")
    return _monic_integer(_poly_div_exact(poly, _poly_gcd(poly, _derivative(poly))))


# --------------------------------------------------------------------------
# Minimal polynomial by exact Krylov elimination, then confirmed.
# --------------------------------------------------------------------------


def _deterministic_seeds(n: int) -> tuple[tuple[int, ...], ...]:
    """Fixed, reproducible seed vectors.  No randomness anywhere in this package."""

    seeds = [
        tuple(1 for _ in range(n)),
        tuple(1 if i == 0 else 0 for i in range(n)),
        tuple(1 + (i % 5) for i in range(n)),
        tuple(1 if i % 2 == 0 else -1 for i in range(n)),
        tuple(1 if i == n - 1 else 0 for i in range(n)),
    ]
    return tuple(seeds)


def krylov_annihilator(
    m: Sequence[Sequence[int]], seed: Sequence[int]
) -> tuple[int, ...]:
    """The monic minimal polynomial ``p`` with ``p(m) seed = 0``, exactly.

    ``p`` **divides** the minimal polynomial of ``m``, so its degree is only a
    *lower* bound on the number of distinct eigenvalues.  This function is
    deliberately named for what it computes and not for what a caller might
    hope it computes.
    """

    rows = _require_square_symmetric(m)
    n = len(rows)
    if len(seed) != n:
        raise SpectrumError("krylov_seed_dimension_mismatch", f"len:{len(seed)}")
    if all(item == 0 for item in seed):
        raise SpectrumError("krylov_seed_zero", "seed")
    # Incremental exact elimination.  ``reduced`` holds row-echelon images of
    # the Krylov iterates, ``combos`` the coefficients expressing each image in
    # terms of the original iterates.
    reduced: list[tuple[int, list[Fraction]]] = []
    combos: list[list[Fraction]] = []
    current = [Fraction(item) for item in seed]
    for step in range(n + 1):
        row = list(current)
        combo = [Fraction(0)] * (step + 1)
        combo[step] = Fraction(1)
        for position, (pivot, prow) in enumerate(reduced):
            if row[pivot] != 0:
                factor = row[pivot]
                pcombo = combos[position]
                row = [x - factor * y for x, y in zip(row, prow)]
                for index, value in enumerate(pcombo):
                    combo[index] -= factor * value
        pivot = next((index for index, value in enumerate(row) if value != 0), None)
        if pivot is None:
            # ``sum_j combo[j] * m^j seed = 0`` with combo[step] == 1.
            return _monic_integer(tuple(reversed(combo)))
        inverse = row[pivot]
        reduced.append((pivot, [item / inverse for item in row]))
        combos.append([item / inverse for item in combo])
        current = _matvec_fraction(rows, current)
    raise SpectrumError("krylov_did_not_terminate", f"order:{n}")


def _matvec_fraction(
    m: Sequence[Sequence[int]], v: Sequence[Fraction]
) -> list[Fraction]:
    return [sum((a * b for a, b in zip(row, v)), Fraction(0)) for row in m]


def _annihilates(m: Sequence[Sequence[int]], poly: tuple[int, ...]) -> bool:
    """``poly(m) == 0``, checked exactly on every standard basis vector.

    This is the confirmation step.  ``poly(m) e_i == 0`` for all ``i`` is
    equivalent to ``poly(m) == 0``; checking a handful of seeds instead would be
    evidence and not proof, because a single seed's annihilator only divides the
    minimal polynomial.
    """

    n = len(m)
    coefficients = list(poly)
    for i in range(n):
        acc = [0] * n
        acc[i] = coefficients[0]
        for coefficient in coefficients[1:]:
            acc = _matvec(m, acc)
            if coefficient:
                acc[i] += coefficient
        if any(acc):
            return False
    return True


def minimal_polynomial(m: Sequence[Sequence[int]]) -> tuple[int, ...]:
    """The exact minimal polynomial of a symmetric integer matrix, confirmed.

    A candidate is assembled as the least common multiple of the annihilators
    of several fixed deterministic seeds, and is then **confirmed** by
    :func:`_annihilates` on a full basis.  A candidate that cannot be confirmed
    is refused with ``minimal_polynomial_unconfirmed``; it is never returned
    with a caveat.

    Refuses ``spectrum_too_large_without_decomposition`` above
    :data:`MAX_DENSE_ORDER`, because the confirmation pass is
    ``order * degree`` exact matrix-vector products and that cost is declared
    rather than silently absorbed.
    """

    rows = _require_square_symmetric(m)
    n = len(rows)
    if n > MAX_DENSE_ORDER:
        raise SpectrumError(
            "spectrum_too_large_without_decomposition", f"order:{n}>{MAX_DENSE_ORDER}"
        )
    candidate: tuple[int, ...] = (1,)
    for seed in _deterministic_seeds(n):
        candidate = _poly_lcm(candidate, krylov_annihilator(rows, seed))
    # Exactly one confirmation pass: the least common multiple over every seed is
    # still only a divisor of the minimal polynomial, so confirming the largest
    # candidate once is both the cheapest and the only sound order of work.
    if not _annihilates(rows, candidate):
        raise SpectrumError("minimal_polynomial_unconfirmed", f"degree:{_degree(candidate)}")
    if distinct_root_count(candidate) != _degree(candidate):
        raise SpectrumError(
            "minimal_polynomial_not_squarefree", f"degree:{_degree(candidate)}"
        )
    return candidate


def distinct_eigenvalue_count(g: Graph) -> int:
    """``|spec(D(g))|``, exactly.

    Uses the confirmed minimal polynomial: for a symmetric integer matrix the
    minimal polynomial is squarefree, so its degree is the number of distinct
    eigenvalues.  Refuses ``spectrum_too_large_without_decomposition`` above
    :data:`MAX_DENSE_ORDER`; a larger graph needs
    :func:`verify_decomposition`.
    """

    if g.order > MAX_DENSE_ORDER:
        raise SpectrumError(
            "spectrum_too_large_without_decomposition",
            f"order:{g.order}>{MAX_DENSE_ORDER}",
        )
    return _degree(minimal_polynomial(distance_matrix(g)))


def distinct_eigenvalue_lower_bound(g: Graph) -> int:
    """A **proved lower bound** on ``|spec(D(g))|``, with no confirmation pass.

    Each deterministic seed's Krylov annihilator divides the minimal
    polynomial, so its degree can only under-count.  Reported as a one-sided
    result on purpose: it is cheap enough to run at order 448, and pairing it
    with :func:`verify_decomposition`'s exact count gives two independent exact
    routes that must meet.
    """

    matrix = distance_matrix(g)
    best = 0
    for seed in _deterministic_seeds(g.order):
        best = max(best, _degree(krylov_annihilator(matrix, seed)))
    return best


# --------------------------------------------------------------------------
# Sturm sequences over Q: the exact spectral-extent comparison.
# --------------------------------------------------------------------------


def _sturm_chain(poly: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    """Sturm chain of a squarefree integer polynomial.

    Each member is normalized by a **positive** rational factor only (content
    removal plus a sign correction for the pseudo-division multiplier), which
    leaves the sign-variation count unchanged.
    """

    chain = [_primitive(poly), _primitive(_derivative(poly))]
    while _degree(chain[-1]) > 0:
        a, b = chain[-2], chain[-1]
        steps = _degree(a) - _degree(b) + 1
        remainder = _pseudo_remainder(a, b)
        if b[0] < 0 and steps % 2 == 1:
            remainder = _normalize([-item for item in remainder])
        if _is_zero(remainder):
            raise SpectrumError("sturm_chain_not_squarefree", "zero_remainder")
        remainder = _primitive(remainder)
        chain.append(_normalize([-item for item in remainder]))
    return tuple(chain)


def _sign_variations(chain: Sequence[tuple[int, ...]], point: Fraction) -> int:
    signs: list[int] = []
    for member in chain:
        value = _evaluate(member, point)
        if value > 0:
            signs.append(1)
        elif value < 0:
            signs.append(-1)
    return sum(1 for a, b in zip(signs, signs[1:]) if a != b)


def _root_bound(poly: tuple[int, ...]) -> Fraction:
    """A strict Cauchy bound: every real root ``lambda`` has ``|lambda| < B``."""

    lead = abs(poly[0])
    largest = max((abs(item) for item in poly[1:]), default=0)
    return Fraction(largest, lead) + 1


def _count_in(chain: Sequence[tuple[int, ...]], lo: Fraction, hi: Fraction) -> int:
    """Distinct real roots of ``chain[0]`` in ``(lo, hi)``, by Sturm's theorem.

    Sturm's theorem needs both endpoints to be non-roots.  Every endpoint this
    module supplies is a non-root by construction, because the rational roots
    are divided out before the chain is built.  When rational-root detection was
    unavailable that guarantee is gone, so an endpoint that turns out to be a
    root is a refusal rather than a possibly-wrong count.
    """

    for point in (lo, hi):
        if _evaluate(chain[0], point) == 0:
            raise SpectrumError("spectral_extent_comparison_undecided", f"endpoint_is_root:{point}")
    return _sign_variations(chain, lo) - _sign_variations(chain, hi)


def _isolate_extreme(
    chain: Sequence[tuple[int, ...]], lo: Fraction, hi: Fraction, *, largest: bool
) -> tuple[Fraction, Fraction]:
    """Narrow ``(lo, hi)`` to an interval holding exactly the extreme root."""

    for _ in range(MAX_ISOLATION_STEPS):
        count = _count_in(chain, lo, hi)
        if count <= 1:
            return lo, hi
        mid = (lo + hi) / 2
        upper = _count_in(chain, mid, hi)
        if largest:
            if upper >= 1:
                lo = mid
            else:
                hi = mid
        else:
            if count - upper >= 1:
                hi = mid
            else:
                lo = mid
    raise SpectrumError("spectral_extent_comparison_undecided", "isolation_steps")


@dataclass(frozen=True, slots=True, kw_only=True)
class _Extreme:
    exact: Fraction | None
    lo: Fraction
    hi: Fraction

    def bounds(self) -> tuple[Fraction, Fraction]:
        if self.exact is not None:
            return self.exact, self.exact
        return self.lo, self.hi


def _extremes(poly: tuple[int, ...]) -> tuple[_Extreme, _Extreme]:
    """Exact-or-bracketed largest and smallest real roots of ``poly``."""

    radical = squarefree_part(poly)
    rational = _rational_roots(radical)
    if rational is None:
        rational_roots: tuple[Fraction, ...] = ()
        irrational = radical
    else:
        rational_roots = rational
        irrational = _deflate_rational(radical, rational_roots) if rational_roots else radical
    if _degree(irrational) < 1:
        if not rational_roots:
            raise SpectrumError("spectral_extent_no_real_root", "empty_spectrum")
        top = max(rational_roots)
        bottom = min(rational_roots)
        return (
            _Extreme(exact=top, lo=top, hi=top),
            _Extreme(exact=bottom, lo=bottom, hi=bottom),
        )
    chain = _sturm_chain(irrational)
    bound = _root_bound(irrational)
    if _count_in(chain, -bound, bound) < 1:
        if not rational_roots:
            raise SpectrumError("spectral_extent_no_real_root", "no_real_root")
        top = max(rational_roots)
        bottom = min(rational_roots)
        return (
            _Extreme(exact=top, lo=top, hi=top),
            _Extreme(exact=bottom, lo=bottom, hi=bottom),
        )
    top_rational = max(rational_roots) if rational_roots else None
    bottom_rational = min(rational_roots) if rational_roots else None
    if top_rational is not None and _count_in(chain, top_rational, bound) == 0:
        largest = _Extreme(exact=top_rational, lo=top_rational, hi=top_rational)
    else:
        lo, hi = _isolate_extreme(chain, -bound, bound, largest=True)
        if top_rational is not None and top_rational > lo:
            lo = top_rational
        largest = _Extreme(exact=None, lo=lo, hi=hi)
    if bottom_rational is not None and _count_in(chain, -bound, bottom_rational) == 0:
        smallest = _Extreme(exact=bottom_rational, lo=bottom_rational, hi=bottom_rational)
    else:
        lo, hi = _isolate_extreme(chain, -bound, bound, largest=False)
        if bottom_rational is not None and bottom_rational < hi:
            hi = bottom_rational
        smallest = _Extreme(exact=None, lo=lo, hi=hi)
    return largest, smallest


def _refine(
    chain: Sequence[tuple[int, ...]], extreme: _Extreme, *, largest: bool
) -> _Extreme:
    if extreme.exact is not None:
        return extreme
    mid = (extreme.lo + extreme.hi) / 2
    if largest:
        if _count_in(chain, mid, extreme.hi) >= 1:
            return _Extreme(exact=None, lo=mid, hi=extreme.hi)
        return _Extreme(exact=None, lo=extreme.lo, hi=mid)
    if _count_in(chain, extreme.lo, mid) >= 1:
        return _Extreme(exact=None, lo=extreme.lo, hi=mid)
    return _Extreme(exact=None, lo=mid, hi=extreme.hi)


def spectral_extent_vs(poly: Iterable[int], value: Fraction) -> str:
    """Compare ``lambda_max - lambda_min`` of ``poly``'s real roots with ``value``.

    Exact throughout: the squarefree part is taken, rational roots are pinned
    by the rational-root theorem, and the remaining irrational extremes are
    bracketed by Sturm sequences with rational interval refinement.

    Returns ``"less"``, ``"greater"``, or ``"equal"``.  ``"equal"`` is only ever
    returned when both extremes are exactly rational and the difference *is* the
    supplied value; the alternative -- refusing a comparison that has in fact
    been decided exactly -- would be a false refusal.  When a bounded number of
    refinements cannot separate the extent from ``value`` this refuses
    ``spectral_extent_comparison_undecided``.  It never guesses and never
    constructs a ``float``.
    """

    poly = _normalize(poly)
    if not isinstance(value, (int, Fraction)) or isinstance(value, bool):
        raise SpectrumError("spectral_extent_value_not_rational", f"value:{value!r}")
    value = Fraction(value)
    largest, smallest = _extremes(poly)
    if largest.exact is not None and smallest.exact is not None:
        extent = largest.exact - smallest.exact
        if extent < value:
            return "less"
        if extent > value:
            return "greater"
        return "equal"
    radical = squarefree_part(poly)
    rational = _rational_roots(radical)
    irrational = (
        _deflate_rational(radical, rational) if rational else radical
    )
    chain = _sturm_chain(irrational)
    for _ in range(MAX_REFINEMENT_STEPS):
        top_lo, top_hi = largest.bounds()
        bot_lo, bot_hi = smallest.bounds()
        upper = top_hi - bot_lo
        lower = top_lo - bot_hi
        if upper <= value:
            return "less"
        if lower >= value:
            return "greater"
        largest = _refine(chain, largest, largest=True)
        smallest = _refine(chain, smallest, largest=False)
    raise SpectrumError("spectral_extent_comparison_undecided", "refinement_steps")


# --------------------------------------------------------------------------
# Operator-supplied decompositions, verified.
# --------------------------------------------------------------------------

Vector = tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class BasisWitness:
    """Explicit exact basis vectors backing a :class:`Decomposition`.

    Vectors are integer vectors.  This is no restriction: multiplying an entire
    basis by a common denominator clears any rational entries and leaves the
    supplied quotient matrix ``Q`` unchanged, because ``D(Lv_j) = sum_i Q[i][j]
    (L v_i)``.
    """

    scalar_vectors: tuple[tuple[Vector, ...], ...]
    quotient_vectors: tuple[tuple[tuple[Vector, ...], ...], ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Decomposition:
    """Operator-supplied invariant-subspace decomposition, VERIFIED not trusted.

    ``scalar_blocks`` are ``(eigenvalue, dimension)`` pairs; ``quotient_blocks``
    are ``(matrix, multiplicity)`` pairs where ``matrix`` acts on coordinate
    column vectors of the supplied basis of each copy.  Nothing in this object
    is believed until :func:`verify_decomposition` has checked it against the
    graph's own distance matrix.
    """

    scalar_blocks: tuple[tuple[int, int], ...]
    quotient_blocks: tuple[tuple[tuple[tuple[int, ...], ...], int], ...]
    basis_witness: BasisWitness

    def claimed_order(self) -> int:
        scalar = sum(dimension for _, dimension in self.scalar_blocks)
        quotient = sum(len(matrix) * multiplicity for matrix, multiplicity in self.quotient_blocks)
        return scalar + quotient


def decomposition_root_polynomial(d: Decomposition) -> tuple[int, ...]:
    """Product of each distinct block polynomial taken **once**.

    The full characteristic polynomial is
    ``prod (x - e)^dim * prod charpoly(Q)^mult``; its *root set* is unchanged by
    dropping every multiplicity, and only the root set matters for a distinct
    count or a spectral extent.  Taking each factor once keeps the degree small
    (nine, for the shipped G(14,18) blocks) instead of 448.
    """

    poly: tuple[int, ...] = (1,)
    for eigenvalue, _ in d.scalar_blocks:
        poly = _poly_mul(poly, (1, -eigenvalue))
    for matrix, _ in d.quotient_blocks:
        poly = _poly_mul(poly, characteristic_polynomial(matrix))
    return poly


def _sparse(vector: Vector) -> tuple[tuple[int, int], ...]:
    return tuple((index, value) for index, value in enumerate(vector) if value)


def _apply_sparse(
    matrix: Sequence[Sequence[int]], sparse: Sequence[tuple[int, int]], order: int
) -> list[int]:
    acc = [0] * order
    for index, value in sparse:
        row = matrix[index]
        acc = [a + value * b for a, b in zip(acc, row)]
    return acc


def _full_rank(vectors: Sequence[Vector], order: int) -> bool:
    """Exact rank test over ``Q`` by sparse elimination with min-index pivots.

    Each pivot row's minimum column *is* its pivot column, so reducing a row
    against the pivot with the smallest pivoted column strictly increases that
    minimum and the loop terminates.  Without this test the whole
    decomposition route would be unsound: repeating one basis vector would
    satisfy every action check while spanning nothing.
    """

    pivots: dict[int, dict[int, Fraction]] = {}
    ordered = sorted(vectors, key=lambda item: sum(1 for value in item if value))
    for vector in ordered:
        row: dict[int, Fraction] = {
            index: Fraction(value) for index, value in enumerate(vector) if value
        }
        while True:
            shared = [column for column in row if column in pivots]
            if not shared:
                break
            column = min(shared)
            factor = row[column]
            for index, value in pivots[column].items():
                updated = row.get(index, Fraction(0)) - factor * value
                if updated:
                    row[index] = updated
                else:
                    row.pop(index, None)
        if not row:
            continue
        column = min(row)
        inverse = row[column]
        pivots[column] = {index: value / inverse for index, value in row.items()}
    return len(pivots) == order


def verify_decomposition(g: Graph, d: Decomposition) -> int:
    """Check an operator-supplied decomposition exactly, then count distinct roots.

    Checks, in order and all exact:

    1. the claimed dimensions sum to ``g.order``, and the basis witness has
       exactly the claimed shape (``decomposition_dimension_mismatch``);
    2. ``D v == lambda v`` on every supplied scalar basis vector
       (``decomposition_action_mismatch``);
    3. ``D v_j == sum_i Q[i][j] v_i`` on every supplied quotient basis vector of
       every copy (``decomposition_action_mismatch``);
    4. the whole witness has full rank ``g.order`` over ``Q``
       (``decomposition_basis_rank_deficient``).

    Only then is the distinct-root count of
    :func:`decomposition_root_polynomial` returned.  Under (1)-(4) ``D`` is
    similar to the block diagonal, so the two polynomials have the same root
    set and the count is exact.  Any mismatch is a refusal.
    """

    matrix = _require_square_symmetric(distance_matrix(g))
    order = g.order
    scalar_blocks = tuple(d.scalar_blocks)
    quotient_blocks = tuple(d.quotient_blocks)
    for eigenvalue, dimension in scalar_blocks:
        if isinstance(eigenvalue, bool) or not isinstance(eigenvalue, int):
            raise SpectrumError("decomposition_dimension_mismatch", "scalar_eigenvalue")
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 1:
            raise SpectrumError("decomposition_dimension_mismatch", f"scalar_dimension:{dimension}")
    for matrix_block, multiplicity in quotient_blocks:
        size = len(matrix_block)
        if size < 1 or any(len(row) != size for row in matrix_block):
            raise SpectrumError("decomposition_dimension_mismatch", "quotient_not_square")
        if isinstance(multiplicity, bool) or not isinstance(multiplicity, int) or multiplicity < 1:
            raise SpectrumError(
                "decomposition_dimension_mismatch", f"quotient_multiplicity:{multiplicity}"
            )
    if d.claimed_order() != order:
        raise SpectrumError(
            "decomposition_dimension_mismatch", f"claimed:{d.claimed_order()};order:{order}"
        )
    witness = d.basis_witness
    if len(witness.scalar_vectors) != len(scalar_blocks):
        raise SpectrumError("decomposition_dimension_mismatch", "scalar_block_count")
    if len(witness.quotient_vectors) != len(quotient_blocks):
        raise SpectrumError("decomposition_dimension_mismatch", "quotient_block_count")

    collected: list[Vector] = []
    for (eigenvalue, dimension), vectors in zip(scalar_blocks, witness.scalar_vectors):
        if len(vectors) != dimension:
            raise SpectrumError(
                "decomposition_dimension_mismatch", f"scalar_basis:{len(vectors)}!={dimension}"
            )
        for vector in vectors:
            if len(vector) != order:
                raise SpectrumError("decomposition_dimension_mismatch", "scalar_vector_length")
            sparse = _sparse(vector)
            if not sparse:
                raise SpectrumError("decomposition_basis_rank_deficient", "zero_scalar_vector")
            image = _apply_sparse(matrix, sparse, order)
            if any(a != eigenvalue * b for a, b in zip(image, vector)):
                raise SpectrumError(
                    "decomposition_action_mismatch", f"scalar_eigenvalue:{eigenvalue}"
                )
            collected.append(tuple(vector))
    for index, ((block, multiplicity), copies) in enumerate(
        zip(quotient_blocks, witness.quotient_vectors)
    ):
        size = len(block)
        if len(copies) != multiplicity:
            raise SpectrumError(
                "decomposition_dimension_mismatch", f"quotient_copies:{len(copies)}!={multiplicity}"
            )
        for copy_index, vectors in enumerate(copies):
            if len(vectors) != size:
                raise SpectrumError(
                    "decomposition_dimension_mismatch", f"quotient_basis:{len(vectors)}!={size}"
                )
            for vector in vectors:
                if len(vector) != order:
                    raise SpectrumError(
                        "decomposition_dimension_mismatch", "quotient_vector_length"
                    )
                if not any(vector):
                    raise SpectrumError(
                        "decomposition_basis_rank_deficient", "zero_quotient_vector"
                    )
            for column in range(size):
                image = _apply_sparse(matrix, _sparse(vectors[column]), order)
                expected = [0] * order
                for row in range(size):
                    coefficient = block[row][column]
                    if coefficient:
                        expected = [
                            a + coefficient * b for a, b in zip(expected, vectors[row])
                        ]
                if image != expected:
                    raise SpectrumError(
                        "decomposition_action_mismatch",
                        f"quotient_block:{index};copy:{copy_index};column:{column}",
                    )
            collected.extend(tuple(vector) for vector in vectors)
    if len(collected) != order:
        raise SpectrumError(
            "decomposition_dimension_mismatch", f"witness_vectors:{len(collected)}!={order}"
        )
    if not _full_rank(collected, order):
        raise SpectrumError("decomposition_basis_rank_deficient", f"order:{order}")
    return distinct_root_count(decomposition_root_polynomial(d))


# --------------------------------------------------------------------------
# The shipped G(r,t) block proposal, and its fixture loader.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class DecompositionBlocks:
    """A decomposition *proposal* read from a fixture, plus what it claims.

    Every ``claimed_*`` field is something this package **checks**.  None of
    them is believed, and none of them is allowed to stand in for a computation.
    """

    blocks_id: str
    source_ref: str
    family: str
    r: int
    t: int
    scalar_blocks: tuple[tuple[int, int], ...]
    quotient_blocks: tuple[tuple[tuple[tuple[int, ...], ...], int], ...]
    claimed_order: int
    claimed_size: int
    claimed_triangle_free: bool
    claimed_connected: bool
    claimed_inverse_even_includes_v: str
    claimed_distinct_eigenvalues: int
    claimed_quotient_polynomials: tuple[tuple[int, ...], ...]


_BLOCKS_FIELDS = frozenset({
    "schema_version", "blocks_id", "source_ref", "graph_family",
    "scalar_blocks", "quotient_blocks", "shipped_claims",
})
_FAMILY_FIELDS = frozenset({"family", "r", "t"})
_CLAIM_FIELDS = frozenset({
    "order", "size", "triangle_free", "connected",
    "inverse_even_even_includes_v", "distinct_distance_eigenvalues",
    "quotient_characteristic_polynomials",
})


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise SpectrumError("decomposition_blocks_malformed", f"duplicate_field:{key}")
        value[key] = item
    return value


def _int_matrix(value: Any, field: str) -> tuple[tuple[int, ...], ...]:
    if not isinstance(value, list) or not value:
        raise SpectrumError("decomposition_blocks_malformed", f"not_matrix:{field}")
    rows: list[tuple[int, ...]] = []
    for row in value:
        if not isinstance(row, list) or len(row) != len(value):
            raise SpectrumError("decomposition_blocks_malformed", f"not_square:{field}")
        for item in row:
            if isinstance(item, bool) or not isinstance(item, int):
                raise SpectrumError("decomposition_blocks_malformed", f"not_integer:{field}")
        rows.append(tuple(row))
    return tuple(rows)


def load_decomposition_blocks(
    payload: bytes | str | Mapping[str, Any]
) -> DecompositionBlocks:
    """Read a block proposal fixture, failing closed on anything unexpected."""

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            value = json.loads(payload, object_pairs_hook=_strict_object)
        except json.JSONDecodeError as error:
            raise SpectrumError("decomposition_blocks_malformed", "not_json") from error
    else:
        value = json.loads(json.dumps(payload, allow_nan=False), object_pairs_hook=_strict_object)
    if not isinstance(value, dict) or set(value) != set(_BLOCKS_FIELDS):
        raise SpectrumError("decomposition_blocks_malformed", "field_set_mismatch")
    if value["schema_version"] != BLOCKS_SCHEMA_VERSION:
        raise SpectrumError("decomposition_blocks_malformed", "schema_version_unsupported")
    family = value["graph_family"]
    if not isinstance(family, dict) or set(family) != set(_FAMILY_FIELDS):
        raise SpectrumError("decomposition_blocks_malformed", "graph_family_field_set_mismatch")
    claims = value["shipped_claims"]
    if not isinstance(claims, dict) or set(claims) != set(_CLAIM_FIELDS):
        raise SpectrumError("decomposition_blocks_malformed", "shipped_claims_field_set_mismatch")
    scalar_raw = value["scalar_blocks"]
    if not isinstance(scalar_raw, list) or not scalar_raw:
        raise SpectrumError("decomposition_blocks_malformed", "scalar_blocks")
    scalar: list[tuple[int, int]] = []
    for item in scalar_raw:
        if not isinstance(item, list) or len(item) != 2 or any(
            isinstance(part, bool) or not isinstance(part, int) for part in item
        ):
            raise SpectrumError("decomposition_blocks_malformed", "scalar_block_pair")
        scalar.append((item[0], item[1]))
    quotient_raw = value["quotient_blocks"]
    if not isinstance(quotient_raw, list) or not quotient_raw:
        raise SpectrumError("decomposition_blocks_malformed", "quotient_blocks")
    quotient: list[tuple[tuple[tuple[int, ...], ...], int]] = []
    for index, item in enumerate(quotient_raw):
        if not isinstance(item, dict) or set(item) != {"matrix", "multiplicity"}:
            raise SpectrumError("decomposition_blocks_malformed", f"quotient_block:{index}")
        multiplicity = item["multiplicity"]
        if isinstance(multiplicity, bool) or not isinstance(multiplicity, int) or multiplicity < 1:
            raise SpectrumError("decomposition_blocks_malformed", f"multiplicity:{index}")
        quotient.append((_int_matrix(item["matrix"], f"quotient_blocks[{index}]"), multiplicity))
    polynomials_raw = claims["quotient_characteristic_polynomials"]
    if not isinstance(polynomials_raw, list) or len(polynomials_raw) != len(quotient):
        raise SpectrumError("decomposition_blocks_malformed", "quotient_polynomial_count")
    polynomials: list[tuple[int, ...]] = []
    for item in polynomials_raw:
        if not isinstance(item, list) or not item or any(
            isinstance(part, bool) or not isinstance(part, int) for part in item
        ):
            raise SpectrumError("decomposition_blocks_malformed", "quotient_polynomial")
        polynomials.append(tuple(item))
    for field in ("order", "size", "distinct_distance_eigenvalues"):
        if isinstance(claims[field], bool) or not isinstance(claims[field], int):
            raise SpectrumError("decomposition_blocks_malformed", f"claim_not_integer:{field}")
    for field in ("triangle_free", "connected"):
        if not isinstance(claims[field], bool):
            raise SpectrumError("decomposition_blocks_malformed", f"claim_not_boolean:{field}")
    if not isinstance(claims["inverse_even_even_includes_v"], str):
        raise SpectrumError("decomposition_blocks_malformed", "claim_not_string")
    if not isinstance(family["r"], int) or isinstance(family["r"], bool):
        raise SpectrumError("decomposition_blocks_malformed", "family_r")
    if not isinstance(family["t"], int) or isinstance(family["t"], bool):
        raise SpectrumError("decomposition_blocks_malformed", "family_t")
    if not isinstance(family["family"], str) or not isinstance(value["blocks_id"], str) \
            or not isinstance(value["source_ref"], str):
        raise SpectrumError("decomposition_blocks_malformed", "text_field")
    return DecompositionBlocks(
        blocks_id=value["blocks_id"],
        source_ref=value["source_ref"],
        family=family["family"],
        r=family["r"],
        t=family["t"],
        scalar_blocks=tuple(scalar),
        quotient_blocks=tuple(quotient),
        claimed_order=claims["order"],
        claimed_size=claims["size"],
        claimed_triangle_free=claims["triangle_free"],
        claimed_connected=claims["connected"],
        claimed_inverse_even_includes_v=claims["inverse_even_even_includes_v"],
        claimed_distinct_eigenvalues=claims["distinct_distance_eigenvalues"],
        claimed_quotient_polynomials=tuple(polynomials),
    )


def _kernel_basis(rows: Sequence[Sequence[int]], columns: int) -> tuple[Vector, ...]:
    """Integer basis of the kernel of an integer constraint matrix, exactly."""

    work = [[Fraction(item) for item in row] for row in rows]
    pivot_of_column: dict[int, int] = {}
    pivot_row = 0
    for column in range(columns):
        target = next(
            (index for index in range(pivot_row, len(work)) if work[index][column] != 0), None
        )
        if target is None:
            continue
        work[pivot_row], work[target] = work[target], work[pivot_row]
        inverse = work[pivot_row][column]
        work[pivot_row] = [item / inverse for item in work[pivot_row]]
        for index in range(len(work)):
            if index != pivot_row and work[index][column] != 0:
                factor = work[index][column]
                work[index] = [a - factor * b for a, b in zip(work[index], work[pivot_row])]
        pivot_of_column[column] = pivot_row
        pivot_row += 1
    basis: list[Vector] = []
    for free in range(columns):
        if free in pivot_of_column:
            continue
        vector = [Fraction(0)] * columns
        vector[free] = Fraction(1)
        for column, row in pivot_of_column.items():
            vector[column] = -work[row][free]
        denominator = _common_denominator(vector)
        basis.append(tuple(int(item * denominator) for item in vector))
    return tuple(basis)


def _solve_in_basis(
    vectors: Sequence[Vector], target: Sequence[int]
) -> tuple[Fraction, ...]:
    """Coordinates of ``target`` in ``vectors``; refuses when it is not in the span."""

    k = len(vectors)
    n = len(target)
    rows = [
        [Fraction(vectors[i][p]) for i in range(k)] + [Fraction(target[p])]
        for p in range(n)
    ]
    used: set[int] = set()
    pivot_rows: list[int] = []
    for column in range(k):
        chosen = next(
            (index for index in range(n) if index not in used and rows[index][column] != 0), None
        )
        if chosen is None:
            raise SpectrumError("decomposition_proposal_not_invariant", f"dependent_basis:{column}")
        used.add(chosen)
        pivot_rows.append(chosen)
        inverse = rows[chosen][column]
        rows[chosen] = [item / inverse for item in rows[chosen]]
        for index in range(n):
            if index != chosen and rows[index][column] != 0:
                factor = rows[index][column]
                rows[index] = [a - factor * b for a, b in zip(rows[index], rows[chosen])]
    solution = [Fraction(0)] * k
    for column, index in enumerate(pivot_rows):
        solution[column] = rows[index][k]
    for index in range(n):
        if index in used:
            continue
        if rows[index][k] != 0:
            raise SpectrumError("decomposition_proposal_not_invariant", "target_outside_span")
    return tuple(solution)


def propose_graffiti_decomposition(
    r: int,
    t: int,
    *,
    scalar_blocks: Sequence[tuple[int, int]] | None = None,
    quotient_blocks: Sequence[tuple[Sequence[Sequence[int]], int]] | None = None,
) -> Decomposition:
    """Build a candidate decomposition of ``D(G(r,t))``.  A PROPOSAL, not a result.

    The basis witness is generated from the frozen vertex layout: within-cluster
    leaf differences; zero-row-and-column internal arrays; the three
    orbit-constant vectors; and, for each of the ``r-1`` zero-sum vectors
    ``e_0 - e_m``, the four standard vectors (branch, row-internal,
    col-internal, leaf).

    When ``scalar_blocks`` and ``quotient_blocks`` are supplied they are used
    **exactly as given** -- that is how the shipped paper's claimed blocks get
    checked rather than re-derived.  When they are omitted they are solved for
    from the graph's own distance matrix, which is still only a proposal.
    Either way nothing is established until :func:`verify_decomposition` has
    run.
    """

    layout = graffiti_family_layout(r, t)
    order = layout.order

    def unit(pairs: Sequence[tuple[int, int]]) -> Vector:
        vector = [0] * order
        for index, value in pairs:
            vector[index] += value
        return tuple(vector)

    leaf_differences = tuple(
        unit(((layout.leaf(i, a), 1), (layout.leaf(i, a + 1), -1)))
        for i in range(r)
        for a in range(t - 1)
    )
    pairs = layout.internal_pairs()
    constraint_rows: list[list[int]] = []
    for i in range(r):
        constraint_rows.append([1 if a == i else 0 for a, _ in pairs])
    for j in range(r):
        constraint_rows.append([1 if b == j else 0 for _, b in pairs])
    internal_kernel = _kernel_basis(constraint_rows, len(pairs))
    internal_vectors = tuple(
        unit(tuple(
            (layout.internal(i, j), coefficient)
            for (i, j), coefficient in zip(pairs, vector)
            if coefficient
        ))
        for vector in internal_kernel
    )
    orbit_vectors = (
        unit(tuple((layout.branch(i), 1) for i in range(r))),
        unit(tuple((layout.internal(i, j), 1) for i, j in pairs)),
        unit(tuple((layout.leaf(i, a), 1) for i in range(r) for a in range(t))),
    )
    standard_copies: list[tuple[Vector, ...]] = []
    for m in range(1, r):
        weight = {0: 1, m: -1}
        standard_copies.append((
            unit(tuple((layout.branch(i), c) for i, c in weight.items())),
            unit(tuple(
                (layout.internal(i, j), weight[i]) for i, j in pairs if i in weight
            )),
            unit(tuple(
                (layout.internal(i, j), weight[j]) for i, j in pairs if j in weight
            )),
            unit(tuple(
                (layout.leaf(i, a), c) for i, c in weight.items() for a in range(t)
            )),
        ))

    if scalar_blocks is None:
        scalar_blocks = ((-2, len(leaf_differences)), (-1, len(internal_vectors)))
    resolved_scalar = tuple((int(e), int(dim)) for e, dim in scalar_blocks)

    if quotient_blocks is None:
        matrix = distance_matrix(graffiti_family(r, t))
        derived: list[tuple[tuple[tuple[int, ...], ...], int]] = []
        for basis, multiplicity in ((orbit_vectors, 1), (standard_copies[0], len(standard_copies))):
            size = len(basis)
            columns: list[list[int]] = []
            for column in range(size):
                image = _apply_sparse(matrix, _sparse(basis[column]), order)
                solution = _solve_in_basis(basis, image)
                if any(item.denominator != 1 for item in solution):
                    raise SpectrumError(
                        "decomposition_proposal_not_invariant", "non_integral_quotient"
                    )
                columns.append([int(item) for item in solution])
            block = tuple(
                tuple(columns[column][row] for column in range(size)) for row in range(size)
            )
            derived.append((block, multiplicity))
        quotient_blocks = tuple(derived)
    resolved_quotient = tuple(
        (tuple(tuple(int(item) for item in row) for row in matrix_block), int(multiplicity))
        for matrix_block, multiplicity in quotient_blocks
    )

    witness = BasisWitness(
        scalar_vectors=(leaf_differences, internal_vectors),
        quotient_vectors=((orbit_vectors,), tuple(standard_copies)),
    )
    return Decomposition(
        scalar_blocks=resolved_scalar,
        quotient_blocks=resolved_quotient,
        basis_witness=witness,
    )
