"""The exact engine's refusal boundaries, exercised rather than asserted.

`exact_graph` claims it never guesses: no float is constructed, and a quantity
it cannot decide exactly becomes a typed refusal. That claim rests entirely on
these guards, so each one reachable from the public API is driven here. An
untested guard is a rule nobody can show fails, which is the same defect this
whole change exists to remove.

Note which function enforces symmetry, because it is a real distinction.
`characteristic_polynomial` accepts any square integer matrix, since a
characteristic polynomial is defined for one. Symmetry is required only where
the engine infers a *distinct eigenvalue count* from a minimal-polynomial
degree, which needs a real, diagonalizable spectrum -- so `minimal_polynomial`,
`krylov_annihilator` and `distinct_eigenvalue_count` demand it and the
characteristic polynomial does not.

Four guards are bounded-iteration backstops -- `krylov_did_not_terminate`,
`minimal_polynomial_unconfirmed`, `spectral_extent_comparison_undecided` and
`sturm_chain_not_squarefree`. They are unreachable from the public API with a
well-formed graph, because a graph distance matrix is always square, symmetric
and integral. They are deliberately not faked here: a contrived test that reached
them through a private path would assert nothing about the engine's behaviour on
real input.
"""

from __future__ import annotations

import unittest
from fractions import Fraction

from math_research.exact_graph import (
    MAX_DENSE_ORDER,
    SpectrumError,
    characteristic_polynomial,
    cycle,
    distance_matrix,
    distinct_eigenvalue_count,
    distinct_root_count,
    graffiti_family,
    krylov_annihilator,
    minimal_polynomial,
    rayleigh_extent_bound,
    spectral_extent_vs,
)


def _code(call, *args) -> str:
    try:
        call(*args)
    except SpectrumError as error:
        return error.code
    raise AssertionError(f"{call.__name__} did not refuse {args!r}")


class MatrixShapeRefusalTests(unittest.TestCase):
    """The distinct-eigenvalue inference demands a real symmetric spectrum."""

    def test_a_non_square_matrix_is_refused(self) -> None:
        self.assertEqual("matrix_not_square", _code(minimal_polynomial, [[1, 2]]))

    def test_a_ragged_matrix_is_refused(self) -> None:
        self.assertEqual("matrix_not_square", _code(minimal_polynomial, [[1, 2], [3]]))

    def test_an_asymmetric_matrix_is_refused_by_the_inference_that_needs_symmetry(self) -> None:
        self.assertEqual(
            "matrix_not_symmetric", _code(minimal_polynomial, [[0, 1], [2, 0]])
        )

    def test_the_characteristic_polynomial_does_not_demand_symmetry(self) -> None:
        # Defined for any square matrix, so refusing here would be wrong.
        # Coefficients are descending, leading first: (1, 0, -2) is lambda^2 - 2.
        self.assertEqual((1, 0, -2), tuple(characteristic_polynomial([[0, 1], [2, 0]])))

    def test_a_float_entry_is_refused_rather_than_coerced(self) -> None:
        # 0.5 is exactly representable, so coercion would "work". That is the
        # point: a float must not enter the engine even when it is harmless.
        self.assertEqual(
            "matrix_not_integral", _code(minimal_polynomial, [[0, 0.5], [0.5, 0]])
        )

    def test_a_fraction_entry_is_refused(self) -> None:
        half = Fraction(1, 2)
        self.assertEqual(
            "matrix_not_integral", _code(minimal_polynomial, [[0, half], [half, 0]])
        )


class KrylovSeedRefusalTests(unittest.TestCase):
    """A Krylov degree is a lower bound; its preconditions are checked."""

    def test_a_seed_of_the_wrong_length_is_refused(self) -> None:
        matrix = distance_matrix(cycle(4))
        self.assertEqual(
            "krylov_seed_dimension_mismatch", _code(krylov_annihilator, matrix, [1, 2])
        )

    def test_a_zero_seed_is_refused_rather_than_returning_a_trivial_answer(self) -> None:
        matrix = distance_matrix(cycle(4))
        self.assertEqual(
            "krylov_seed_zero", _code(krylov_annihilator, matrix, [0, 0, 0, 0])
        )


class PolynomialRefusalTests(unittest.TestCase):
    """Distinct-root counting refuses input it cannot answer for."""

    def test_a_constant_polynomial_has_no_root_count(self) -> None:
        self.assertEqual("polynomial_degenerate", _code(distinct_root_count, [1]))

    def test_a_float_coefficient_is_refused(self) -> None:
        self.assertEqual(
            "polynomial_not_integral", _code(distinct_root_count, [1.0, 2.0, 1.0])
        )


class DenseBoundRefusalTests(unittest.TestCase):
    """The dense bound is a declared boundary, not a silent truncation."""

    def test_the_bound_admits_the_shipped_448_vertex_witness(self) -> None:
        witness = graffiti_family(14, 18)
        self.assertEqual(448, witness.order)
        self.assertLessEqual(witness.order, MAX_DENSE_ORDER)

    def test_a_graph_past_the_bound_refuses_instead_of_approximating(self) -> None:
        oversized = graffiti_family(24, 2)          # 24^2 + 48 = 624 > 512
        self.assertGreater(oversized.order, MAX_DENSE_ORDER)
        self.assertEqual(
            "spectrum_too_large_without_decomposition",
            _code(distinct_eigenvalue_count, oversized),
        )


class ExtentComparisonRefusalTests(unittest.TestCase):
    """Spectral extent is compared exactly against a rational, or not at all."""

    def _c4_poly(self) -> tuple[int, ...]:
        return characteristic_polynomial(distance_matrix(cycle(4)))

    def test_a_float_comparand_is_refused(self) -> None:
        self.assertEqual(
            "spectral_extent_value_not_rational",
            _code(spectral_extent_vs, self._c4_poly(), 2.5),
        )

    def test_c4_extent_is_exactly_six_and_compares_exactly(self) -> None:
        # C4's distance spectrum is {4, 0, -2, -2}, so the extent is exactly 6.
        poly = self._c4_poly()
        self.assertEqual("greater", spectral_extent_vs(poly, Fraction(2)))
        self.assertEqual("greater", spectral_extent_vs(poly, Fraction(4)))
        self.assertEqual("equal", spectral_extent_vs(poly, Fraction(6)))
        self.assertEqual("less", spectral_extent_vs(poly, Fraction(7)))

    def test_the_rayleigh_bound_is_rational_and_settles_the_shipped_witness(self) -> None:
        bound = rayleigh_extent_bound(graffiti_family(14, 18))
        self.assertIsInstance(bound, Fraction)
        self.assertEqual(Fraction(32915, 16), bound)        # 2W/n, W = 460810, n = 448
        # The extent reading cannot refute: the bound alone dwarfs Inverse Even.
        self.assertGreater(bound, Fraction(40049, 4444))


if __name__ == "__main__":
    unittest.main()
