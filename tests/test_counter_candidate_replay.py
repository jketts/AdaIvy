"""Acceptance suite for counter-candidate replay.

The load-bearing fact here is an asymmetry produced mechanically, with no human
noticing anything: the prior published C4 candidate refutes Graffiti 322 under
exactly one of the four reading tuples, and the shipped G(14,18) witness refutes
under two.  Neither statement is derivable from any single reading, and neither
is written down anywhere in the shipped report.
"""

from __future__ import annotations

import json
import unittest
from fractions import Fraction
from pathlib import Path

from math_research.exact_graph import (
    ENGINE_ID,
    MAX_DENSE_ORDER,
    READING_TUPLES,
    REPLAY_SCHEMA_VERSION,
    VERDICTS,
    Decomposition,
    ReplayError,
    SpectrumError,
    build_graph,
    cycle,
    graffiti_family,
    load_decomposition_blocks,
    load_graph_spec,
    propose_graffiti_decomposition,
    reading_tuple_product,
    replay_candidate,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "exact-graph"
C4_SPEC = FIXTURES / "c4-witness-v1.json"
BLOCKS = FIXTURES / "graffiti-322-blocks-v1.json"


def paper_decomposition() -> Decomposition:
    blocks = load_decomposition_blocks(BLOCKS.read_bytes())
    return propose_graffiti_decomposition(
        blocks.r, blocks.t,
        scalar_blocks=blocks.scalar_blocks, quotient_blocks=blocks.quotient_blocks,
    )


class ReplayShapeTests(unittest.TestCase):
    def test_reading_tuples_cover_the_whole_vocabulary_product(self) -> None:
        self.assertEqual(set(reading_tuple_product()), set(READING_TUPLES))
        self.assertEqual(len(reading_tuple_product()), len(READING_TUPLES))

    def test_every_reading_tuple_is_present_exactly_once(self) -> None:
        result = replay_candidate(cycle(4), replay_id="rp.c4-shape-v1")
        self.assertEqual(READING_TUPLES, tuple(item.reading for item in result.readings))
        self.assertEqual(4, len(READING_TUPLES))
        for item in result.readings:
            self.assertIn(item.verdict, VERDICTS)

    def test_payload_is_exact_deterministic_and_claims_no_warrant(self) -> None:
        first = replay_candidate(cycle(4), replay_id="rp.c4-shape-v1")
        second = replay_candidate(
            load_graph_spec(C4_SPEC.read_bytes()), replay_id="rp.c4-shape-v1"
        )
        payload = first.payload()
        self.assertEqual(REPLAY_SCHEMA_VERSION, payload["schema_version"])
        self.assertEqual(ENGINE_ID, payload["engine"])
        self.assertEqual("fractions-exact", payload["arithmetic"])
        self.assertIs(False, payload["float_used"])
        self.assertIs(False, payload["creates_mathematical_warrant"])
        self.assertEqual({
            "schema_version", "replay_id", "witness_graph_id", "witness_spec_hash",
            "engine", "arithmetic", "float_used", "order", "triangle_free",
            "connected", "readings", "creates_mathematical_warrant", "result_hash",
        }, set(payload))
        self.assertTrue(payload["result_hash"].startswith("sha256:"))
        # The spec hash is structural, so the same C4 under a different name
        # replays to the same witness hash; only the graph_id differs.
        self.assertEqual(first.witness_spec_hash, second.witness_spec_hash)
        self.assertEqual(
            json.dumps(first.payload()["readings"], sort_keys=True),
            json.dumps(second.payload()["readings"], sort_keys=True),
        )
        # No float anywhere in the serialized record.
        self.assertNotIn(float, {type(value) for value in _flatten(payload)})

    def test_replay_id_and_witness_are_validated(self) -> None:
        with self.assertRaises(ReplayError) as ctx:
            replay_candidate(cycle(4), replay_id="Bad Id")
        self.assertEqual("replay_id_invalid", ctx.exception.code)
        with self.assertRaises(ReplayError) as ctx:
            replay_candidate("not-a-graph", replay_id="rp.x-v1")  # type: ignore[arg-type]
        self.assertEqual("replay_witness_invalid", ctx.exception.code)


def _flatten(value: object) -> list[object]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _flatten(child)]
    if isinstance(value, list):
        return [item for child in value for item in _flatten(child)]
    return [value]


class PriorCandidateTests(unittest.TestCase):
    """C4, the candidate Roucairol & Cazenave publish for Graffiti 322."""

    def test_c4_refutes_under_exactly_one_reading_tuple(self) -> None:
        result = replay_candidate(
            load_graph_spec(C4_SPEC.read_bytes()), replay_id="rp.c4-candidate-v1"
        )
        self.assertEqual(4, result.order)
        self.assertTrue(result.triangle_free)
        self.assertTrue(result.connected)
        verdicts = {item.reading: item for item in result.readings}

        includes_count = verdicts[("even_includes_v", "range_distinct_count")]
        self.assertEqual("2", includes_count.inverse_even)
        self.assertEqual("3", includes_count.range_value)
        self.assertEqual("does_not_refute", includes_count.verdict)

        excludes_count = verdicts[("even_excludes_v", "range_distinct_count")]
        self.assertEqual("4", excludes_count.inverse_even)
        self.assertEqual("3", excludes_count.range_value)
        self.assertEqual("refutes", excludes_count.verdict)

        for even_reading in ("even_includes_v", "even_excludes_v"):
            extent = verdicts[(even_reading, "range_extent")]
            self.assertEqual("does_not_refute", extent.verdict)
            self.assertTrue(extent.range_value.startswith("greater_than:"))

        self.assertEqual(
            1, sum(1 for item in result.readings if item.verdict == "refutes")
        )
        self.assertEqual(
            ("does_not_refute", "does_not_refute", "refutes", "does_not_refute"),
            result.scope_inputs(),
        )

    def test_the_definitional_fork_is_visible_without_human_insight(self) -> None:
        result = replay_candidate(cycle(4), replay_id="rp.c4-fork-v1")
        refuting = {item.reading for item in result.readings if item.verdict == "refutes"}
        not_refuting = {
            item.reading for item in result.readings if item.verdict == "does_not_refute"
        }
        self.assertTrue(refuting)
        self.assertTrue(not_refuting)
        self.assertFalse(
            any(item.verdict == "not_evaluated" for item in result.readings)
        )


class ShippedWitnessTests(unittest.TestCase):
    """G(14,18), the witness the shipped report offers."""

    def test_g14_18_refutes_under_both_readings_of_even(self) -> None:
        g = graffiti_family(14, 18)
        result = replay_candidate(
            g, replay_id="rp.g14-18-v1", decomposition=paper_decomposition()
        )
        self.assertEqual(448, result.order)
        self.assertTrue(result.triangle_free)
        self.assertTrue(result.connected)
        verdicts = {item.reading: item for item in result.readings}

        frozen = verdicts[("even_includes_v", "range_distinct_count")]
        self.assertEqual("40049/4444", frozen.inverse_even)
        self.assertEqual("9", frozen.range_value)
        self.assertEqual("refutes", frozen.verdict)

        excluded = verdicts[("even_excludes_v", "range_distinct_count")]
        self.assertEqual("8772568/953095", excluded.inverse_even)
        self.assertEqual("9", excluded.range_value)
        self.assertEqual("refutes", excluded.verdict)

        for even_reading in ("even_includes_v", "even_excludes_v"):
            extent = verdicts[(even_reading, "range_extent")]
            self.assertEqual("does_not_refute", extent.verdict)
            self.assertIn("2W/n=32915/16", extent.detail)

        self.assertEqual(
            2, sum(1 for item in result.readings if item.verdict == "refutes")
        )
        self.assertEqual(
            ("refutes", "does_not_refute", "refutes", "does_not_refute"),
            result.scope_inputs(),
        )

    def test_the_two_witnesses_are_not_interchangeable(self) -> None:
        # This is the asymmetry the shipped report does not record: the prior
        # candidate and the new witness refute under different sets of readings,
        # so "already refuted" and "newly refuted" are both reading-relative.
        prior = replay_candidate(cycle(4), replay_id="rp.c4-compare-v1")
        current = replay_candidate(
            graffiti_family(14, 18), replay_id="rp.g14-18-compare-v1",
            decomposition=paper_decomposition(),
        )
        self.assertNotEqual(prior.scope_inputs(), current.scope_inputs())
        shared = {
            reading
            for reading in READING_TUPLES
            if prior.verdict_for(reading) == "refutes"
            and current.verdict_for(reading) == "refutes"
        }
        self.assertEqual({("even_excludes_v", "range_distinct_count")}, shared)

    def test_a_wrong_decomposition_refuses_and_does_not_become_not_evaluated(self) -> None:
        good = paper_decomposition()
        first, second = good.quotient_blocks
        rows = [list(row) for row in first[0]]
        rows[2][1] -= 1
        broken = Decomposition(
            scalar_blocks=good.scalar_blocks,
            quotient_blocks=((tuple(tuple(row) for row in rows), first[1]), second),
            basis_witness=good.basis_witness,
        )
        with self.assertRaises(SpectrumError) as ctx:
            replay_candidate(
                graffiti_family(14, 18), replay_id="rp.g14-18-broken-v1",
                decomposition=broken,
            )
        self.assertEqual("decomposition_action_mismatch", ctx.exception.code)


class PreservedFailureTests(unittest.TestCase):
    def test_a_disconnected_witness_yields_four_not_evaluated_verdicts(self) -> None:
        result = replay_candidate(
            build_graph("two-components", 4, [[0, 1], [2, 3]]),
            replay_id="rp.disconnected-v1",
        )
        self.assertFalse(result.connected)
        self.assertEqual(
            ("not_evaluated",) * 4, tuple(item.verdict for item in result.readings)
        )
        for item in result.readings:
            self.assertIn("graph_not_connected", item.detail)

    def test_an_empty_even_set_is_retained_as_not_evaluated_per_reading(self) -> None:
        star = build_graph("K1-3", 4, [[0, 1], [0, 2], [0, 3]])
        result = replay_candidate(star, replay_id="rp.star-v1")
        by_reading = {item.reading: item for item in result.readings}
        for range_reading in ("range_distinct_count", "range_extent"):
            included = by_reading[("even_includes_v", range_reading)]
            self.assertNotEqual("not_evaluated", included.verdict)
            excluded = by_reading[("even_excludes_v", range_reading)]
            self.assertEqual("not_evaluated", excluded.verdict)
            self.assertIn("even_count_zero", excluded.detail)

    def test_a_spectrum_above_the_dense_bound_with_no_decomposition_is_retained(self) -> None:
        big = cycle(MAX_DENSE_ORDER + 2)
        result = replay_candidate(big, replay_id="rp.big-cycle-v1")
        by_reading = {item.reading: item for item in result.readings}
        for even_reading in ("even_includes_v", "even_excludes_v"):
            counted = by_reading[(even_reading, "range_distinct_count")]
            self.assertEqual("not_evaluated", counted.verdict)
            self.assertIn("spectrum_too_large_without_decomposition", counted.detail)
            # The extent reading is still decided, exactly, by the rational
            # Rayleigh bound: no eigenvalue work and no refusal.
            extent = by_reading[(even_reading, "range_extent")]
            self.assertEqual("does_not_refute", extent.verdict)
            self.assertIn("rayleigh_extent_bound", extent.detail)


class DeterminismTests(unittest.TestCase):
    def test_result_hash_is_stable_across_processes_and_orderings(self) -> None:
        expected = replay_candidate(cycle(4), replay_id="rp.c4-hash-v1").result_hash
        for _ in range(3):
            self.assertEqual(
                expected, replay_candidate(cycle(4), replay_id="rp.c4-hash-v1").result_hash
            )
        shuffled = build_graph("C4", 4, [[3, 0], [2, 3], [1, 2], [0, 1]])
        self.assertEqual(
            expected, replay_candidate(shuffled, replay_id="rp.c4-hash-v1").result_hash
        )

    def test_result_hash_changes_when_a_verdict_changes(self) -> None:
        c4 = replay_candidate(cycle(4), replay_id="rp.same-id-v1")
        c6 = replay_candidate(cycle(6), replay_id="rp.same-id-v1")
        self.assertNotEqual(c4.result_hash, c6.result_hash)

    def test_verdict_for_refuses_an_absent_reading(self) -> None:
        result = replay_candidate(cycle(4), replay_id="rp.c4-absent-v1")
        with self.assertRaises(ReplayError) as ctx:
            result.verdict_for(("even_maybe_v", "range_distinct_count"))
        self.assertEqual("replay_reading_absent", ctx.exception.code)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
