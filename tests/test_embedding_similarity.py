"""ADR-0065 exact integer similarity.

The comparator is where the exactness claim either holds or does not, so these
tests exhaust the sign cases rather than sampling them: squaring the dot product
destroys sign information, and a comparator that skips the sign check ranks a
strongly negative cosine above a weakly positive one.
"""

from __future__ import annotations

import itertools
import subprocess
import sys
import unittest
from fractions import Fraction
from pathlib import Path

from math_research.embedding.errors import (
    NonIntegerCoordinateError,
    PartitionMismatchError,
    ZeroNormVectorError,
)
from math_research.embedding.partition import PartitionKey, PartitionedVector
from math_research.embedding.similarity import (
    compare_cosine,
    cosine_terms,
    cosine_terms_within_partition,
    dot,
    norm_squared,
    rank_exact_cosine,
    require_same_partition,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _key(
    *, provider: str = "fixture_synthetic",
    model_identifier: str = "project-authored-v1",
    dimension: int = 3,
    normalization: str = "round_half_even_scale_2p30",
) -> PartitionKey:
    return PartitionKey(
        provider=provider, model_identifier=model_identifier,
        dimension=dimension, normalization=normalization,
    )


def _vector(
    key: PartitionKey, document_id: str, coordinates: tuple[int, ...],
) -> PartitionedVector:
    return PartitionedVector(
        partition_key=key, document_id=document_id, coordinates=coordinates,
    )


class ExactPrimitiveTests(unittest.TestCase):
    def test_dot_and_norm_squared_are_exact_integers(self) -> None:
        self.assertEqual(dot((1, 2, 3), (4, 5, 6)), 32)
        self.assertEqual(norm_squared((3, 4)), 25)
        big = (1 << 60, -(1 << 60))
        self.assertEqual(norm_squared(big), 2 * (1 << 120))
        self.assertIsInstance(norm_squared(big), int)

    def test_cosine_terms_denominator_is_positive(self) -> None:
        numerator, denominator = cosine_terms((1, 0), (0, 1))
        self.assertEqual(numerator, 0)
        self.assertGreater(denominator, 0)

    def test_zero_vector_has_no_cosine(self) -> None:
        with self.assertRaises(ZeroNormVectorError):
            cosine_terms((0, 0), (1, 1))

    def test_boolean_coordinate_is_not_an_integer(self) -> None:
        with self.assertRaises(NonIntegerCoordinateError):
            dot((True, 1), (1, 1))

    def test_length_mismatch_is_a_dimension_refusal(self) -> None:
        with self.assertRaises(PartitionMismatchError) as caught:
            dot((1, 2), (1, 2, 3))
        self.assertEqual(caught.exception.component, "dimension")


class CompareCosineTests(unittest.TestCase):
    """`compare_cosine` against an independent exact `Fraction` oracle."""

    VECTORS = (
        (1, 0), (0, 1), (1, 1), (3, 1), (1, 3), (-1, 0), (-1, -1), (-3, -1),
        (2, -1), (-1, 2), (5, 5), (7, 1), (-7, -1), (1, -3),
    )
    QUERIES = ((1, 1), (1, 0), (-1, 2), (3, -1))

    @staticmethod
    def _oracle(query: tuple[int, ...], candidate: tuple[int, ...]) -> Fraction:
        """Exact ``cos^2`` carrying the sign; only used to order candidates."""

        numerator = dot(query, candidate)
        denominator = norm_squared(query) * norm_squared(candidate)
        magnitude = Fraction(numerator * numerator, denominator)
        return magnitude if numerator >= 0 else -magnitude

    def test_matches_an_exact_fraction_oracle_on_every_pair(self) -> None:
        checked = 0
        for query in self.QUERIES:
            for left, right in itertools.product(self.VECTORS, repeat=2):
                observed = compare_cosine(
                    cosine_terms(query, left), cosine_terms(query, right),
                )
                expected_left = self._oracle(query, left)
                expected_right = self._oracle(query, right)
                if expected_left == expected_right:
                    expected = 0
                else:
                    expected = 1 if expected_left > expected_right else -1
                self.assertEqual(
                    observed, expected, f"query={query} left={left} right={right}",
                )
                checked += 1
        self.assertEqual(checked, len(self.QUERIES) * len(self.VECTORS) ** 2)

    def test_positive_dot_outranks_negative_dot(self) -> None:
        positive = cosine_terms((1, 1), (1, 1))
        negative = cosine_terms((1, 1), (-5, -5))
        self.assertEqual(compare_cosine(positive, negative), 1)
        self.assertEqual(compare_cosine(negative, positive), -1)

    def test_squaring_alone_would_invert_the_negative_branch(self) -> None:
        """A larger magnitude with a negative dot is a SMALLER cosine."""

        weak = cosine_terms((1, 0), (-1, 9))
        strong = cosine_terms((1, 0), (-9, 1))
        self.assertEqual(compare_cosine(weak, strong), 1)

    def test_zero_dot_ranks_between_positive_and_negative(self) -> None:
        zero = cosine_terms((1, 0), (0, 1))
        positive = cosine_terms((1, 0), (1, 1))
        negative = cosine_terms((1, 0), (-1, 1))
        self.assertEqual(compare_cosine(zero, positive), -1)
        self.assertEqual(compare_cosine(zero, negative), 1)
        self.assertEqual(compare_cosine(zero, cosine_terms((1, 0), (0, -1))), 0)

    def test_denominator_must_be_positive(self) -> None:
        with self.assertRaises(ZeroNormVectorError):
            compare_cosine((1, 0), (1, 4))

    def test_scale_invariance_of_the_comparison(self) -> None:
        query = (3, 1)
        for factor in (1, 2, 7, 1 << 20):
            scaled = tuple(value * factor for value in (1, 4))
            self.assertEqual(
                compare_cosine(
                    cosine_terms(query, (1, 4)), cosine_terms(query, scaled),
                ),
                0,
            )


class PartitionGuardTests(unittest.TestCase):
    def test_same_partition_is_accepted(self) -> None:
        key = _key()
        self.assertEqual(
            require_same_partition(
                _vector(key, "a", (1, 2, 3)), _vector(key, "b", (3, 2, 1)),
            ),
            key,
        )

    def test_each_component_is_load_bearing(self) -> None:
        base = _key()
        variants = {
            "provider": _key(provider="openai"),
            "model_identifier": _key(model_identifier="project-authored-v2"),
            "dimension": _key(dimension=2),
            "normalization": _key(normalization="round_half_even_scale_2p20"),
        }
        for component, other in variants.items():
            with self.subTest(component=component):
                with self.assertRaises(PartitionMismatchError) as caught:
                    cosine_terms_within_partition(
                        _vector(base, "a", (1, 2, 3)),
                        _vector(other, "b", (1, 2, 3)[: other.dimension]),
                    )
                self.assertEqual(caught.exception.component, component)
                self.assertEqual(
                    caught.exception.code, f"partition_mismatch:{component}",
                )


class TieBreakTests(unittest.TestCase):
    KEY = _key(dimension=2)

    def _candidates(self, reverse: bool) -> list[PartitionedVector]:
        items = [
            _vector(self.KEY, "aaa-doc", (3, 1)),
            _vector(self.KEY, "zzz-doc", (1, 3)),
        ]
        return list(reversed(items)) if reverse else items

    def test_equal_cosines_order_by_document_id_ascending(self) -> None:
        query = _vector(self.KEY, "query", (1, 1))
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                ordered = rank_exact_cosine(query, self._candidates(reverse))
                self.assertEqual(
                    [item[0] for item in ordered], ["aaa-doc", "zzz-doc"],
                )
                self.assertEqual(compare_cosine(ordered[0][1], ordered[1][1]), 0)

    def test_ordering_is_cosine_descending_then_identifier(self) -> None:
        query = _vector(self.KEY, "query", (1, 1))
        candidates = self._candidates(False) + [
            _vector(self.KEY, "mmm-doc", (1, 1)),
            _vector(self.KEY, "nnn-doc", (-1, -1)),
        ]
        ordered = [item[0] for item in rank_exact_cosine(query, candidates)]
        self.assertEqual(ordered, ["mmm-doc", "aaa-doc", "zzz-doc", "nnn-doc"])

    def test_tie_order_is_identical_under_a_different_hash_seed(self) -> None:
        """`PYTHONHASHSEED` must not reach the ordering, in a fresh process."""

        script = (
            "from math_research.embedding.partition import PartitionKey, "
            "PartitionedVector\n"
            "from math_research.embedding.similarity import rank_exact_cosine\n"
            "k = PartitionKey(provider='fixture_synthetic', "
            "model_identifier='project-authored-v1', dimension=2, "
            "normalization='round_half_even_scale_2p30')\n"
            "def v(i, c):\n"
            "    return PartitionedVector(partition_key=k, document_id=i, coordinates=c)\n"
            "q = v('query', (1, 1))\n"
            "print([x[0] for x in rank_exact_cosine("
            "q, [v('zzz-doc', (1, 3)), v('aaa-doc', (3, 1))])])\n"
        )
        outputs = set()
        for seed in ("0", "1", "12345", "random"):
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
                env={
                    "PYTHONPATH": "src", "PYTHONHASHSEED": seed,
                    "PATH": "/usr/bin:/bin",
                },
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            outputs.add(completed.stdout.strip())
        self.assertEqual(outputs, {"['aaa-doc', 'zzz-doc']"})


if __name__ == "__main__":
    unittest.main()
