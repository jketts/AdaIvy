"""Acceptance suite for the exact graph spectral engine.

Every number asserted here is *derived* by the engine from a construction, and
the shipped Graffiti 322 report's claimed values are treated as claims to be
checked rather than as expected outputs.  Where the report and the engine agree
the test says so explicitly, so a future divergence fails here.

The suite also enforces the arithmetic boundary structurally: a source scan
refuses any ``float``, any tolerance, any square root, and any randomness in
``src/math_research/exact_graph``.
"""

from __future__ import annotations

import ast
import json
import unittest
from fractions import Fraction
from pathlib import Path

from math_research.exact_graph import (
    MAX_DENSE_ORDER,
    BasisWitness,
    Decomposition,
    ExactGraphError,
    GraphError,
    InvariantError,
    SpectrumError,
    build_graph,
    characteristic_polynomial,
    cycle,
    decomposition_root_polynomial,
    distance_matrix,
    distinct_eigenvalue_count,
    distinct_eigenvalue_lower_bound,
    distinct_root_count,
    even_count,
    even_count_profile,
    graffiti_family,
    graffiti_family_layout,
    inverse_even,
    is_connected,
    is_triangle_free,
    kneser,
    krylov_annihilator,
    load_decomposition_blocks,
    load_graph_spec,
    minimal_polynomial,
    propose_graffiti_decomposition,
    rayleigh_extent_bound,
    spectral_extent_vs,
    squarefree_part,
    total_distance,
    verify_decomposition,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "math_research" / "exact_graph"
FIXTURES = ROOT / "fixtures" / "exact-graph"
C4_SPEC = FIXTURES / "c4-witness-v1.json"
BLOCKS = FIXTURES / "graffiti-322-blocks-v1.json"


def code(context: "unittest._AssertRaisesContext[ExactGraphError]") -> str:
    return context.exception.code


class GraphSpecTests(unittest.TestCase):
    def test_witness_fixture_loads_and_hashes_deterministically(self) -> None:
        first = load_graph_spec(C4_SPEC.read_bytes())
        second = load_graph_spec(C4_SPEC.read_text(encoding="utf-8"))
        self.assertEqual(4, first.order)
        self.assertEqual(((0, 1), (0, 3), (1, 2), (2, 3)), first.edges())
        self.assertEqual(first.spec_hash(), second.spec_hash())
        self.assertTrue(first.spec_hash().startswith("sha256:"))

    def test_spec_hash_is_structural_and_ignores_the_name(self) -> None:
        named = load_graph_spec(C4_SPEC.read_bytes())
        renamed = build_graph("some-other-name", 4, [[0, 1], [1, 2], [2, 3], [3, 0]])
        self.assertEqual(named.spec_hash(), renamed.spec_hash())
        self.assertNotEqual(named.graph_id, renamed.graph_id)

    def test_self_loop_is_refused(self) -> None:
        with self.assertRaises(GraphError) as ctx:
            load_graph_spec({"graph_id": "g", "order": 3, "edges": [[0, 0]]})
        self.assertEqual("graph_self_loop", code(ctx))

    def test_vertex_out_of_range_is_refused(self) -> None:
        with self.assertRaises(GraphError) as ctx:
            load_graph_spec({"graph_id": "g", "order": 3, "edges": [[0, 3]]})
        self.assertEqual("graph_vertex_out_of_range", code(ctx))

    def test_duplicate_edge_unknown_field_and_duplicate_key_are_refused(self) -> None:
        for payload in (
            {"graph_id": "g", "order": 3, "edges": [[0, 1], [1, 0]]},
            {"graph_id": "g", "order": 3, "edges": [[0, 1]], "extra": 1},
            {"graph_id": "g", "order": 3},
        ):
            with self.assertRaises(GraphError) as ctx:
                load_graph_spec(payload)
            self.assertEqual("graph_spec_malformed", code(ctx))
        with self.assertRaises(GraphError) as ctx:
            load_graph_spec('{"graph_id": "g", "order": 3, "order": 4, "edges": []}')
        self.assertEqual("graph_spec_malformed", code(ctx))

    def test_float_and_boolean_endpoints_are_refused(self) -> None:
        for payload in (
            {"graph_id": "g", "order": 3.0, "edges": [[0, 1]]},
            {"graph_id": "g", "order": 3, "edges": [[0.0, 1]]},
            {"graph_id": "g", "order": 3, "edges": [[True, 1]]},
        ):
            with self.assertRaises(GraphError) as ctx:
                load_graph_spec(payload)
            self.assertEqual("graph_spec_malformed", code(ctx))

    def test_disconnected_graph_is_reported_not_repaired(self) -> None:
        g = build_graph("two-edges", 4, [[0, 1], [2, 3]])
        self.assertFalse(is_connected(g))
        with self.assertRaises(GraphError) as ctx:
            distance_matrix(g)
        self.assertEqual("graph_not_connected", code(ctx))
        with self.assertRaises(GraphError) as ctx:
            even_count(g, 0, "even_includes_v")
        self.assertEqual("graph_not_connected", code(ctx))


class ConstructionTests(unittest.TestCase):
    def test_cycle_and_kneser_are_deterministic_constructions(self) -> None:
        self.assertEqual("C4", cycle(4).graph_id)
        with self.assertRaises(GraphError) as ctx:
            cycle(2)
        self.assertEqual("graph_spec_malformed", code(ctx))
        petersen = kneser(5, 2)
        self.assertEqual("K5-2", petersen.graph_id)
        self.assertEqual(10, petersen.order)
        self.assertEqual(15, petersen.size())
        self.assertTrue(is_connected(petersen))
        # D(Petersen) = 2J - 2I - A, so spec(D) = {15, 0, -3}: three values.
        self.assertEqual(3, distinct_eigenvalue_count(petersen))

    def test_graffiti_family_reproduces_its_own_order_and_size_formulas(self) -> None:
        for r, t in ((4, 2), (5, 3), (14, 18)):
            g = graffiti_family(r, t)
            self.assertEqual(r * r + r * t, g.order)
            self.assertEqual(3 * r * (r - 1) // 2 + r * t, g.size())
            self.assertTrue(is_triangle_free(g))
            self.assertTrue(is_connected(g))

    def test_graffiti_family_refuses_outside_the_sources_stated_domain(self) -> None:
        for r, t in ((3, 2), (4, 1)):
            with self.assertRaises(GraphError) as ctx:
                graffiti_family(r, t)
            self.assertEqual("graph_spec_malformed", code(ctx))

    def test_g14_18_matches_the_shipped_orders_and_sizes(self) -> None:
        g = graffiti_family(14, 18)
        self.assertEqual(448, g.order)
        self.assertEqual(525, g.size())
        layout = graffiti_family_layout(14, 18)
        self.assertEqual(448, layout.order)
        self.assertEqual(14, len(set(layout.branch_indices())))
        self.assertEqual(182, len(set(layout.internal_indices())))
        self.assertEqual(252, len(set(layout.leaf_indices())))
        self.assertEqual(
            448,
            len(set(layout.branch_indices()) | set(layout.internal_indices())
                | set(layout.leaf_indices())),
        )


class InvariantTests(unittest.TestCase):
    def test_c4_inverse_even_under_both_readings(self) -> None:
        c4 = cycle(4)
        self.assertEqual(2, even_count(c4, 0, "even_includes_v"))
        self.assertEqual(1, even_count(c4, 0, "even_excludes_v"))
        self.assertEqual(Fraction(2), inverse_even(c4, "even_includes_v"))
        self.assertEqual(Fraction(4), inverse_even(c4, "even_excludes_v"))

    def test_unknown_reading_is_refused_and_has_no_default(self) -> None:
        with self.assertRaises(InvariantError) as ctx:
            inverse_even(cycle(4), "even")
        self.assertEqual("even_reading_unknown", code(ctx))
        with self.assertRaises(TypeError):
            inverse_even(cycle(4))  # type: ignore[call-arg]

    def test_empty_even_set_refuses_instead_of_dividing_by_zero(self) -> None:
        star = build_graph("K1-3", 4, [[0, 1], [0, 2], [0, 3]])
        self.assertEqual(1, even_count(star, 0, "even_includes_v"))
        self.assertEqual(0, even_count(star, 0, "even_excludes_v"))
        self.assertEqual(Fraction(2), inverse_even(star, "even_includes_v"))
        with self.assertRaises(InvariantError) as ctx:
            inverse_even(star, "even_excludes_v")
        self.assertEqual("even_count_zero", code(ctx))

    def test_g14_18_even_profile_and_inverse_even_are_derived(self) -> None:
        g = graffiti_family(14, 18)
        # The shipped derivation asserts three even-distance counts in prose:
        # E(b_i)=404, E(x_ij)=56, E(l_ia)=44 at r=14, t=18.  Computed here.
        self.assertEqual(
            ((44, 252), (56, 182), (404, 14)), even_count_profile(g, "even_includes_v")
        )
        self.assertEqual(1 + 13 * 13 + 13 * 18, 404)
        self.assertEqual(3 * 14 - 4 + 18, 56)
        self.assertEqual(2 * 14 - 2 + 18, 44)
        self.assertEqual(Fraction(40049, 4444), inverse_even(g, "even_includes_v"))
        self.assertEqual(
            ((43, 252), (55, 182), (403, 14)), even_count_profile(g, "even_excludes_v")
        )
        self.assertEqual(Fraction(8772568, 953095), inverse_even(g, "even_excludes_v"))
        # Both readings exceed nine; the exclude-v reading is the larger.
        self.assertGreater(inverse_even(g, "even_excludes_v"), 9)
        self.assertGreater(inverse_even(g, "even_includes_v"), 9)
        self.assertGreater(
            inverse_even(g, "even_excludes_v"), inverse_even(g, "even_includes_v")
        )


class PolynomialTests(unittest.TestCase):
    def test_characteristic_polynomial_is_exact_and_descending(self) -> None:
        self.assertEqual((1, -5, 6), characteristic_polynomial(((2, 0), (0, 3))))
        self.assertEqual((1, 0, -12, -16, 0), characteristic_polynomial(distance_matrix(cycle(4))))

    def test_distinct_root_count_strips_multiplicity(self) -> None:
        # (x - 1)^2 (x + 2) = x^3 - 3x + 2
        self.assertEqual(2, distinct_root_count((1, 0, -3, 2)))
        self.assertEqual((1, 1, -2), squarefree_part((1, 0, -3, 2)))
        with self.assertRaises(SpectrumError) as ctx:
            distinct_root_count((7,))
        self.assertEqual("polynomial_degenerate", code(ctx))

    def test_minimal_polynomial_of_c4_is_confirmed_and_squarefree(self) -> None:
        matrix = distance_matrix(cycle(4))
        self.assertEqual((1, -2, -8, 0), minimal_polynomial(matrix))
        self.assertEqual(3, distinct_eigenvalue_count(cycle(4)))
        self.assertEqual(3, distinct_eigenvalue_lower_bound(cycle(4)))

    def test_a_single_seed_annihilator_is_only_a_divisor(self) -> None:
        matrix = distance_matrix(cycle(4))
        # The all-ones vector is the Perron eigenvector of D(C4): its own
        # annihilator is degree one, far below the three distinct eigenvalues.
        self.assertEqual((1, -4), krylov_annihilator(matrix, (1, 1, 1, 1)))
        self.assertEqual(3, len(minimal_polynomial(matrix)) - 1)

    def test_dense_route_refuses_above_its_declared_bound(self) -> None:
        big = cycle(MAX_DENSE_ORDER + 2)
        with self.assertRaises(SpectrumError) as ctx:
            distinct_eigenvalue_count(big)
        self.assertEqual("spectrum_too_large_without_decomposition", code(ctx))


class SpectralExtentTests(unittest.TestCase):
    def test_c4_extent_is_exactly_six(self) -> None:
        poly = characteristic_polynomial(distance_matrix(cycle(4)))
        self.assertEqual("greater", spectral_extent_vs(poly, Fraction(2)))
        self.assertEqual("greater", spectral_extent_vs(poly, Fraction(4)))
        self.assertEqual("equal", spectral_extent_vs(poly, Fraction(6)))
        self.assertEqual("less", spectral_extent_vs(poly, Fraction(10)))
        self.assertEqual("less", spectral_extent_vs(poly, Fraction(121, 20)))
        self.assertEqual("greater", spectral_extent_vs(poly, Fraction(119, 20)))

    def test_rayleigh_bound_is_exact_and_settles_c4_and_g14_18(self) -> None:
        c4 = cycle(4)
        self.assertEqual(16, total_distance(c4))
        self.assertEqual(Fraction(4), rayleigh_extent_bound(c4))
        g = graffiti_family(14, 18)
        self.assertEqual(921620, total_distance(g))
        self.assertEqual(Fraction(32915, 16), rayleigh_extent_bound(g))
        self.assertGreater(rayleigh_extent_bound(g), inverse_even(g, "even_excludes_v"))

    def test_sturm_fallback_brackets_irrational_extremes_of_g14_18(self) -> None:
        # The general Sturm path, exercised on a spectrum whose extreme roots are
        # both irrational: lambda_max is a root of x^3-2048x^2-25454x-54228 in
        # (2060, 2061) and lambda_min a root of x^4+109x^3-146x^2-442x-20 in
        # (-111, -110), so the extent lies strictly between 2170 and 2172.
        poly = decomposition_root_polynomial(_paper_decomposition())
        self.assertEqual("greater", spectral_extent_vs(poly, Fraction(2170)))
        self.assertEqual("less", spectral_extent_vs(poly, Fraction(2172)))
        self.assertEqual("greater", spectral_extent_vs(poly, Fraction(40049, 4444)))
        self.assertEqual("greater", spectral_extent_vs(poly, Fraction(8772568, 953095)))

    def test_extent_of_a_degenerate_polynomial_is_refused(self) -> None:
        with self.assertRaises(SpectrumError) as ctx:
            spectral_extent_vs((3,), Fraction(1))
        self.assertEqual("polynomial_degenerate", code(ctx))
        with self.assertRaises(SpectrumError) as ctx:
            spectral_extent_vs((1, 0, 1), Fraction(1))
        self.assertEqual("spectral_extent_no_real_root", code(ctx))


def _paper_decomposition() -> Decomposition:
    blocks = load_decomposition_blocks(BLOCKS.read_bytes())
    return propose_graffiti_decomposition(
        blocks.r, blocks.t,
        scalar_blocks=blocks.scalar_blocks, quotient_blocks=blocks.quotient_blocks,
    )


class DecompositionTests(unittest.TestCase):
    def test_blocks_fixture_loads_and_fails_closed(self) -> None:
        blocks = load_decomposition_blocks(BLOCKS.read_bytes())
        self.assertEqual("graffiti-322-g14-18-blocks-v1", blocks.blocks_id)
        self.assertEqual((14, 18), (blocks.r, blocks.t))
        self.assertEqual(((-2, 238), (-1, 155)), blocks.scalar_blocks)
        self.assertEqual(9, blocks.claimed_distinct_eigenvalues)
        raw = json.loads(BLOCKS.read_text(encoding="utf-8"))
        for mutate in (
            lambda payload: payload.pop("source_ref"),
            lambda payload: payload.update({"extra": 1}),
            lambda payload: payload.update({"schema_version": "other.v1"}),
            lambda payload: payload["shipped_claims"].pop("order"),
            lambda payload: payload["quotient_blocks"][0].update({"multiplicity": 0}),
        ):
            payload = json.loads(json.dumps(raw))
            mutate(payload)
            with self.assertRaises(SpectrumError) as ctx:
                load_decomposition_blocks(payload)
            self.assertEqual("decomposition_blocks_malformed", code(ctx))

    def test_shipped_blocks_verify_to_nine_distinct_eigenvalues(self) -> None:
        blocks = load_decomposition_blocks(BLOCKS.read_bytes())
        g = graffiti_family(blocks.r, blocks.t)
        decomposition = _paper_decomposition()
        self.assertEqual(g.order, decomposition.claimed_order())
        self.assertEqual(238 + 155 + 3 + 4 * 13, g.order)
        self.assertEqual(9, verify_decomposition(g, decomposition))
        # And the claims the shipped report makes, checked rather than trusted.
        self.assertEqual(blocks.claimed_order, g.order)
        self.assertEqual(blocks.claimed_size, g.size())
        self.assertEqual(blocks.claimed_triangle_free, is_triangle_free(g))
        self.assertEqual(blocks.claimed_connected, is_connected(g))
        self.assertEqual(
            blocks.claimed_inverse_even_includes_v,
            str(inverse_even(g, "even_includes_v")),
        )
        self.assertEqual(
            blocks.claimed_distinct_eigenvalues, verify_decomposition(g, decomposition)
        )
        for (matrix, _), claimed in zip(
            blocks.quotient_blocks, blocks.claimed_quotient_polynomials
        ):
            self.assertEqual(claimed, characteristic_polynomial(matrix))

    def test_derived_blocks_reproduce_the_papers_matrices_independently(self) -> None:
        blocks = load_decomposition_blocks(BLOCKS.read_bytes())
        derived = propose_graffiti_decomposition(blocks.r, blocks.t)
        self.assertEqual(blocks.scalar_blocks, derived.scalar_blocks)
        self.assertEqual(blocks.quotient_blocks, derived.quotient_blocks)
        self.assertEqual(9, verify_decomposition(graffiti_family(14, 18), derived))

    def test_two_independent_exact_routes_agree_on_a_small_family_member(self) -> None:
        g = graffiti_family(4, 2)
        self.assertEqual(24, g.order)
        dense = distinct_eigenvalue_count(g)
        decomposed = verify_decomposition(g, propose_graffiti_decomposition(4, 2))
        self.assertEqual(dense, decomposed)
        self.assertEqual(dense, distinct_eigenvalue_lower_bound(g))

    def test_krylov_lower_bound_independently_reaches_nine_at_order_448(self) -> None:
        # Each seed's annihilator divides the minimal polynomial, so this can
        # only under-count.  It reaches nine without reading the paper's blocks,
        # supplying the lower half of the acceptance fact from a route with no
        # shared input with verify_decomposition.
        self.assertEqual(9, distinct_eigenvalue_lower_bound(graffiti_family(14, 18)))

    def test_dense_route_cost_bound_is_measured(self) -> None:
        """The declared MAX_DENSE_ORDER is measured, not assumed.

        The confirmation pass is ``order * degree`` exact matrix-vector products.
        At order 448 and degree 9 this test executes it end to end -- roughly
        nineteen seconds of exact integer arithmetic on the machine of record --
        and obtains nine, with no decomposition and no input from the shipped
        paper at all.  MAX_DENSE_ORDER is set to 512 on the strength of this
        measurement; raising it further requires re-measuring, not editing.
        """

        self.assertGreaterEqual(MAX_DENSE_ORDER, 448)
        self.assertEqual(9, distinct_eigenvalue_count(graffiti_family(14, 18)))

    def test_dimension_mismatch_is_refused(self) -> None:
        g = graffiti_family(4, 2)
        good = propose_graffiti_decomposition(4, 2)
        broken = Decomposition(
            scalar_blocks=((-2, 3), (-1, 5)),
            quotient_blocks=good.quotient_blocks,
            basis_witness=good.basis_witness,
        )
        with self.assertRaises(SpectrumError) as ctx:
            verify_decomposition(g, broken)
        self.assertEqual("decomposition_dimension_mismatch", code(ctx))

    def test_a_single_wrong_quotient_entry_is_refused(self) -> None:
        g = graffiti_family(4, 2)
        good = propose_graffiti_decomposition(4, 2)
        first, second = good.quotient_blocks
        rows = [list(row) for row in second[0]]
        rows[0][0] += 1
        broken = Decomposition(
            scalar_blocks=good.scalar_blocks,
            quotient_blocks=(first, (tuple(tuple(row) for row in rows), second[1])),
            basis_witness=good.basis_witness,
        )
        with self.assertRaises(SpectrumError) as ctx:
            verify_decomposition(g, broken)
        self.assertEqual("decomposition_action_mismatch", code(ctx))

    def test_a_wrong_scalar_eigenvalue_is_refused(self) -> None:
        g = graffiti_family(4, 2)
        good = propose_graffiti_decomposition(4, 2)
        broken = Decomposition(
            scalar_blocks=((-3, good.scalar_blocks[0][1]), good.scalar_blocks[1]),
            quotient_blocks=good.quotient_blocks,
            basis_witness=good.basis_witness,
        )
        with self.assertRaises(SpectrumError) as ctx:
            verify_decomposition(g, broken)
        self.assertEqual("decomposition_action_mismatch", code(ctx))

    def test_a_repeated_basis_vector_is_refused_as_rank_deficient(self) -> None:
        # Without the rank check this decomposition would pass every action
        # check while spanning one dimension too few, and the count would be
        # unsound.  This is the probe for that.
        g = graffiti_family(4, 2)
        good = propose_graffiti_decomposition(4, 2)
        leaves = list(good.basis_witness.scalar_vectors[0])
        leaves[-1] = leaves[0]
        broken = Decomposition(
            scalar_blocks=good.scalar_blocks,
            quotient_blocks=good.quotient_blocks,
            basis_witness=BasisWitness(
                scalar_vectors=(tuple(leaves), good.basis_witness.scalar_vectors[1]),
                quotient_vectors=good.basis_witness.quotient_vectors,
            ),
        )
        with self.assertRaises(SpectrumError) as ctx:
            verify_decomposition(g, broken)
        self.assertEqual("decomposition_basis_rank_deficient", code(ctx))

    def test_a_zero_basis_vector_is_refused(self) -> None:
        g = graffiti_family(4, 2)
        good = propose_graffiti_decomposition(4, 2)
        leaves = list(good.basis_witness.scalar_vectors[0])
        leaves[0] = tuple(0 for _ in range(g.order))
        broken = Decomposition(
            scalar_blocks=good.scalar_blocks,
            quotient_blocks=good.quotient_blocks,
            basis_witness=BasisWitness(
                scalar_vectors=(tuple(leaves), good.basis_witness.scalar_vectors[1]),
                quotient_vectors=good.basis_witness.quotient_vectors,
            ),
        )
        with self.assertRaises(SpectrumError) as ctx:
            verify_decomposition(g, broken)
        self.assertEqual("decomposition_basis_rank_deficient", code(ctx))

    def test_root_polynomial_drops_multiplicity_only(self) -> None:
        decomposition = _paper_decomposition()
        poly = decomposition_root_polynomial(decomposition)
        self.assertEqual(9, len(poly) - 1)
        self.assertEqual(9, distinct_root_count(poly))
        for eigenvalue in (-1, -2):
            self.assertEqual(0, sum(
                coefficient * eigenvalue ** (len(poly) - 1 - index)
                for index, coefficient in enumerate(poly)
            ))


class ArithmeticBoundaryTests(unittest.TestCase):
    """The oldest rule in this repository, enforced structurally."""

    FORBIDDEN_NAMES = frozenset({
        "float", "complex", "sqrt", "isqrt", "isclose", "round", "pow",
        "fsum", "hypot", "exp", "log", "sin", "cos", "atan2", "nextafter",
        "random", "uniform", "randint", "choice", "shuffle",
    })
    FORBIDDEN_MODULES = frozenset({
        "decimal", "statistics", "random", "secrets", "numpy", "scipy", "sympy",
        "cmath", "mpmath",
    })
    ALLOWED_MATH_NAMES = frozenset({"gcd", "lcm"})

    def sources(self) -> list[tuple[Path, ast.Module]]:
        paths = sorted(PACKAGE.glob("*.py"))
        self.assertEqual(
            ["__init__.py", "graph.py", "invariants.py", "replay.py", "spectrum.py"],
            [item.name for item in paths],
        )
        return [(item, ast.parse(item.read_text(encoding="utf-8"))) for item in paths]

    def test_no_float_literal_and_no_forbidden_name_anywhere(self) -> None:
        for path, tree in self.sources():
            # ``isinstance(x, float)`` is the one admitted mention of the type:
            # it is how a spec loader *refuses* a float rather than accepting one.
            exempt = {
                id(argument)
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "isinstance"
                for argument in node.args
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, float):
                    self.fail(f"{path.name}: float literal")
                if isinstance(node, ast.Name) and node.id in self.FORBIDDEN_NAMES:
                    if node.id == "float" and id(node) in exempt:
                        continue
                    self.fail(f"{path.name}: forbidden name {node.id}")
                if isinstance(node, ast.Attribute) and node.attr in self.FORBIDDEN_NAMES:
                    self.fail(f"{path.name}: forbidden attribute {node.attr}")

    def test_the_float_scan_can_be_made_to_fail(self) -> None:
        # A rule that cannot be made to fail proves nothing.  A float literal, a
        # bare float() call, and a math.sqrt attribute must each be caught.
        for source in ("x = 1.5\n", "x = float(2)\n", "import math\nx = math.sqrt(2)\n"):
            tree = ast.parse(source)
            caught = any(
                (isinstance(node, ast.Constant) and isinstance(node.value, float))
                or (isinstance(node, ast.Name) and node.id in self.FORBIDDEN_NAMES)
                or (isinstance(node, ast.Attribute) and node.attr in self.FORBIDDEN_NAMES)
                for node in ast.walk(tree)
            )
            self.assertTrue(caught, source)

    def test_no_forbidden_module_and_math_is_only_used_for_integer_gcd(self) -> None:
        for path, tree in self.sources():
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], self.FORBIDDEN_MODULES)
                        self.assertNotEqual("math", alias.name)
                if isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".")[0]
                    self.assertNotIn(root, self.FORBIDDEN_MODULES)
                    if node.module == "math":
                        for alias in node.names:
                            self.assertIn(alias.name, self.ALLOWED_MATH_NAMES)

    def test_true_division_never_produces_a_float_in_this_package(self) -> None:
        # Every ``/`` in the package divides Fractions or ints-into-Fractions.
        # Exercising the exact paths and asserting the types is the check that a
        # future edit cannot silently reintroduce binary floating point.
        values = [
            inverse_even(cycle(4), "even_includes_v"),
            rayleigh_extent_bound(graffiti_family(4, 2)),
        ]
        for value in values:
            self.assertIsInstance(value, Fraction)
            self.assertNotIsInstance(value, float)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
