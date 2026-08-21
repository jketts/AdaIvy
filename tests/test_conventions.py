"""Acceptance tests for definitional-reading records and derived claim scope.

The Graffiti 322 report was exact and still misdescribed itself, because the two
contested readings it depended on lived in prose.  These tests hold the record
layer to the two properties that failure needs: the scope of a claim is derived
from a verdict matrix and cannot be supplied, and a matrix that does not cover
the whole reading space cannot pass as one that does.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from math_research.cli import main as root_main
from math_research.conventions import (
    CONVENTION_SCOPES,
    READING_STATUSES,
    SCHEMA_VERSION,
    VERDICTS,
    ContestedTerm,
    ConventionError,
    ConventionRecord,
    Reading,
    ReadingVerdict,
    VerdictMatrix,
    classify_scope,
    load_convention,
    load_verdict_matrix,
    read_convention,
    read_verdict_matrix,
    reading_coupling_index,
    require_convention_binding,
    weakest_reading_status,
    write_convention,
)
from math_research.conventions_cli import main as conventions_main


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures/conventions"
CONVENTION = FIXTURES / "graffiti-322-readings-v1.json"
GRAFFITI_197 = ROOT / "fixtures/novelty/graffiti-197-prior-resolution-v1.json"
SCOPE_FIXTURES = {
    "unconditional": FIXTURES / "verdict-matrix-unconditional-v1.json",
    "convention_relative": FIXTURES / "verdict-matrix-convention-relative-c4-v1.json",
    "contested_unevaluated": FIXTURES / "verdict-matrix-contested-unevaluated-g322-v1.json",
    "refuted_under_no_reading": FIXTURES / "verdict-matrix-refuted-under-no-reading-v1.json",
}

TUPLES = (
    ("even_excludes_v", "range_distinct_count"),
    ("even_excludes_v", "range_extent"),
    ("even_includes_v", "range_distinct_count"),
    ("even_includes_v", "range_extent"),
)


def verdict(reading_tuple: tuple[str, ...], outcome: str) -> ReadingVerdict:
    return ReadingVerdict(
        reading_tuple=reading_tuple,
        verdict=outcome,
        evidence_ref=None if outcome == "not_evaluated" else "replay.test.witness.v1",
        detail="Synthetic verdict for the scope derivation.",
    )


def matrix(outcomes: dict[tuple[str, ...], str], *, convention: ConventionRecord) -> VerdictMatrix:
    return VerdictMatrix(
        matrix_id="vm.test.matrix.v1", claim_id="cl.test.claim",
        convention_id=convention.convention_id,
        convention_hash=convention.content_hash,
        verdicts=tuple(verdict(key, outcomes[key]) for key in sorted(outcomes)),
    ).finalized()


class VocabularyTests(unittest.TestCase):
    def test_frozen_vocabularies_are_exactly_the_contracted_sets(self) -> None:
        self.assertEqual({"verbatim_confirmed", "transcribed", "asserted"}, set(READING_STATUSES))
        self.assertEqual({"refutes", "does_not_refute", "not_evaluated"}, set(VERDICTS))
        self.assertEqual(
            {
                "unconditional", "convention_relative", "contested_unevaluated",
                "refuted_under_no_reading",
            },
            set(CONVENTION_SCOPES),
        )


class ConventionRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.convention = read_convention(CONVENTION)

    def test_round_trip_is_canonical(self) -> None:
        self.assertEqual(self.convention, load_convention(self.convention.payload()))
        self.assertEqual(
            self.convention.content_hash, self.convention.finalized().content_hash
        )

    def test_reading_tuples_are_the_sorted_cartesian_product(self) -> None:
        self.assertEqual(TUPLES, self.convention.reading_tuples())

    def test_reading_tuple_layout_is_independent_of_input_order(self) -> None:
        reversed_terms = ConventionRecord(
            convention_id=self.convention.convention_id,
            subject_ids=self.convention.subject_ids,
            coupled_subject_ids=self.convention.coupled_subject_ids,
            terms=tuple(
                ContestedTerm(
                    term_id=term.term_id, term=term.term,
                    readings=tuple(reversed(term.readings)),
                )
                for term in reversed(self.convention.terms)
            ),
        )
        self.assertEqual(TUPLES, reversed_terms.reading_tuples())

    def test_a_single_reading_is_not_a_contest(self) -> None:
        payload = self.convention.payload()
        payload["terms"][0]["readings"] = payload["terms"][0]["readings"][:1]
        with self.assertRaisesRegex(ConventionError, "term_not_contested"):
            load_convention(payload)

    def test_derived_reading_tuples_cannot_be_narrowed_in_the_payload(self) -> None:
        payload = self.convention.payload()
        payload["reading_tuples"] = payload["reading_tuples"][:1]
        with self.assertRaisesRegex(ConventionError, "reading_tuples_derived_mismatch"):
            load_convention(payload)

    def test_a_convention_record_cannot_claim_warrant_or_resolve_the_fork(self) -> None:
        expected = {
            "creates_mathematical_warrant": "convention_cannot_create_mathematical_warrant",
            "resolves_contested_reading": "convention_cannot_resolve_contested_reading",
        }
        for field, code in expected.items():
            with self.subTest(field=field):
                payload = self.convention.payload()
                payload[field] = True
                with self.assertRaisesRegex(ConventionError, code):
                    load_convention(payload)

    def test_unknown_and_missing_fields_and_duplicate_keys_are_refused(self) -> None:
        payload = self.convention.payload()
        payload["extra"] = "unexpected"
        with self.assertRaisesRegex(ConventionError, "field_set_mismatch"):
            load_convention(payload)
        payload = self.convention.payload()
        payload.pop("coupled_subject_ids")
        with self.assertRaisesRegex(ConventionError, "field_set_mismatch"):
            load_convention(payload)
        raw = json.dumps(self.convention.payload())
        doubled = raw[:-1] + ', "convention_id": "conv.other.v1"}'
        with self.assertRaisesRegex(ConventionError, "duplicate_field:convention_id"):
            load_convention(doubled)

    def test_unknown_schema_or_policy_and_oversized_records_are_refused(self) -> None:
        payload = self.convention.payload()
        payload["schema_version"] = "adaivy.convention-reading.v2"
        with self.assertRaisesRegex(ConventionError, "version_or_policy_unsupported"):
            load_convention(payload)
        payload = self.convention.payload()
        payload["policy_id"] = "convention-relative-claim-v2"
        with self.assertRaisesRegex(ConventionError, "version_or_policy_unsupported"):
            load_convention(payload)
        with self.assertRaisesRegex(ConventionError, "record_too_large"):
            load_convention(b"{" + b" " * 70_000 + b"}")
        with self.assertRaisesRegex(ConventionError, "record_not_json"):
            load_convention(b"{not json")

    def test_an_unknown_reading_status_is_refused(self) -> None:
        payload = self.convention.payload()
        payload["terms"][0]["readings"][0]["reading_status"] = "source_faithful"
        with self.assertRaisesRegex(ConventionError, "reading_status_unknown"):
            load_convention(payload)

    def test_a_reading_id_cannot_be_reused_across_terms(self) -> None:
        payload = self.convention.payload()
        payload["terms"][1]["readings"][0]["reading_id"] = "even_includes_v"
        with self.assertRaisesRegex(ConventionError, "reading_id_duplicated"):
            load_convention(payload)

    def test_editing_a_reading_changes_the_content_hash(self) -> None:
        payload = self.convention.payload()
        payload["terms"][0]["readings"][0]["reading_status"] = "verbatim_confirmed"
        with self.assertRaisesRegex(ConventionError, "content_hash_mismatch"):
            load_convention(payload)

    def test_write_refuses_to_overwrite_a_differing_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conv.json"
            write_convention(self.convention, path)
            write_convention(self.convention, path)
            other = ConventionRecord(
                convention_id="conv.other.v1", subject_ids=("problem.other",),
                coupled_subject_ids=(), terms=self.convention.terms,
            ).finalized()
            with self.assertRaisesRegex(ConventionError, "convention_record_overwrite_refused"):
                write_convention(other, path)


class CouplingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.convention = read_convention(CONVENTION)

    def test_the_322_record_couples_the_197_subject_that_shares_its_range_reading(self) -> None:
        prior = json.loads(GRAFFITI_197.read_text(encoding="utf-8"))
        self.assertEqual("problem.graffiti-197", prior["subject_id"])
        self.assertIn(prior["subject_id"], self.convention.coupled_subject_ids)
        self.assertEqual(
            ("problem.graffiti-197", "problem.graffiti-322"),
            self.convention.governed_subject_ids(),
        )

    def test_every_reading_names_every_subject_it_can_invalidate(self) -> None:
        index = reading_coupling_index([self.convention])
        self.assertEqual(
            ["even_excludes_v", "even_includes_v", "range_distinct_count", "range_extent"],
            list(index),
        )
        for reading_id, subjects in index.items():
            with self.subTest(reading_id=reading_id):
                self.assertEqual(
                    ("problem.graffiti-197", "problem.graffiti-322"), subjects
                )

    def test_a_coupled_subject_cannot_be_the_records_own_subject(self) -> None:
        payload = self.convention.payload()
        payload["coupled_subject_ids"] = ["problem.graffiti-322"]
        with self.assertRaisesRegex(ConventionError, "coupled_subject_is_own_subject"):
            load_convention(payload)


class ScopeDerivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.convention = read_convention(CONVENTION)

    def test_each_fixture_derives_its_named_scope(self) -> None:
        for scope, path in SCOPE_FIXTURES.items():
            with self.subTest(scope=scope):
                loaded = read_verdict_matrix(path)
                require_convention_binding(loaded, self.convention)
                self.assertEqual(scope, loaded.scope(convention=self.convention))
                self.assertEqual(scope, loaded.payload()["derived_scope"])
                self.assertIn(scope, CONVENTION_SCOPES)

    def test_the_shipped_graffiti_322_matrix_evaluated_one_reading_of_four(self) -> None:
        loaded = read_verdict_matrix(SCOPE_FIXTURES["contested_unevaluated"])
        self.assertEqual("cl.graffiti-322-counterexample", loaded.claim_id)
        outcomes = {item.reading_tuple: item.verdict for item in loaded.verdicts}
        self.assertEqual("refutes", outcomes[("even_includes_v", "range_distinct_count")])
        self.assertEqual(
            3, sum(1 for value in outcomes.values() if value == "not_evaluated")
        )

    def test_the_prior_c4_candidate_refutes_under_exactly_one_reading(self) -> None:
        loaded = read_verdict_matrix(SCOPE_FIXTURES["convention_relative"])
        outcomes = {item.reading_tuple: item.verdict for item in loaded.verdicts}
        self.assertEqual("refutes", outcomes[("even_excludes_v", "range_distinct_count")])
        self.assertEqual(
            1, sum(1 for value in outcomes.values() if value == "refutes")
        )
        self.assertEqual("convention_relative", loaded.scope(convention=self.convention))

    def test_flipping_one_verdict_demotes_an_unconditional_scope(self) -> None:
        loaded = read_verdict_matrix(SCOPE_FIXTURES["unconditional"])
        self.assertEqual("unconditional", loaded.scope(convention=self.convention))
        for outcome, expected in (
            ("does_not_refute", "convention_relative"),
            ("not_evaluated", "contested_unevaluated"),
        ):
            with self.subTest(outcome=outcome):
                mutated = list(loaded.verdicts)
                mutated[0] = verdict(mutated[0].reading_tuple, outcome)
                self.assertEqual(expected, classify_scope(tuple(mutated)))

    def test_an_unevaluated_reading_outranks_every_other_signal(self) -> None:
        outcomes = {key: "refutes" for key in TUPLES}
        outcomes[TUPLES[0]] = "not_evaluated"
        outcomes[TUPLES[1]] = "does_not_refute"
        self.assertEqual(
            "contested_unevaluated",
            classify_scope(tuple(verdict(key, value) for key, value in outcomes.items())),
        )

    def test_a_partial_matrix_does_not_read_as_full_coverage(self) -> None:
        loaded = read_verdict_matrix(SCOPE_FIXTURES["unconditional"])
        partial = tuple(
            item for item in loaded.verdicts
            if item.reading_tuple != ("even_includes_v", "range_extent")
        )
        self.assertEqual("unconditional", classify_scope(partial))
        with self.assertRaisesRegex(ConventionError, "verdict_matrix_incomplete"):
            classify_scope(partial, reading_tuples=self.convention.reading_tuples())

    def test_a_matrix_naming_an_unenumerated_reading_is_incomplete(self) -> None:
        extra = (
            verdict(("even_includes_v", "range_distinct_count"), "refutes"),
            verdict(("even_includes_v", "range_extent"), "refutes"),
            verdict(("even_excludes_v", "range_distinct_count"), "refutes"),
            verdict(("even_excludes_v", "range_undefined"), "refutes"),
        )
        with self.assertRaisesRegex(ConventionError, "verdict_matrix_incomplete"):
            classify_scope(extra, reading_tuples=self.convention.reading_tuples())

    def test_degenerate_verdict_sets_are_refused(self) -> None:
        with self.assertRaisesRegex(ConventionError, "invalid_nonempty_list:verdicts"):
            classify_scope(())
        with self.assertRaisesRegex(ConventionError, "verdict_unknown"):
            classify_scope((verdict(TUPLES[0], "probably_refutes"),))
        with self.assertRaisesRegex(ConventionError, "verdict_matrix_duplicate_reading_tuple"):
            classify_scope((verdict(TUPLES[0], "refutes"), verdict(TUPLES[0], "does_not_refute")))
        with self.assertRaisesRegex(ConventionError, "verdict_matrix_arity_inconsistent"):
            classify_scope((verdict(TUPLES[0], "refutes"), verdict(("even_includes_v",), "refutes")))
        with self.assertRaisesRegex(ConventionError, "verdict_matrix_reading_tuple_malformed"):
            classify_scope((verdict((), "refutes"),))


class VerdictMatrixRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.convention = read_convention(CONVENTION)
        self.matrix = read_verdict_matrix(SCOPE_FIXTURES["convention_relative"])

    def test_round_trip_is_canonical(self) -> None:
        self.assertEqual(self.matrix, load_verdict_matrix(self.matrix.payload()))

    def test_the_scope_cannot_be_supplied_even_with_a_rehash(self) -> None:
        payload = self.matrix.payload()
        payload["derived_scope"] = "unconditional"
        payload["content_hash"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ConventionError, "scope_derived_classification_mismatch"):
            load_verdict_matrix(payload)

    def test_an_unknown_scope_string_is_still_a_derivation_mismatch(self) -> None:
        payload = self.matrix.payload()
        payload["derived_scope"] = "source_faithful"
        with self.assertRaisesRegex(ConventionError, "scope_derived_classification_mismatch"):
            load_verdict_matrix(payload)

    def test_a_matrix_cannot_claim_warrant_or_novelty(self) -> None:
        expected = {
            "creates_mathematical_warrant": "verdict_matrix_cannot_create_mathematical_warrant",
            "creates_novelty_status": "verdict_matrix_cannot_create_novelty_status",
        }
        for field, code in expected.items():
            with self.subTest(field=field):
                payload = self.matrix.payload()
                payload[field] = True
                with self.assertRaisesRegex(ConventionError, code):
                    load_verdict_matrix(payload)

    def test_an_evaluated_verdict_needs_evidence_and_an_unevaluated_one_forbids_it(self) -> None:
        payload = self.matrix.payload()
        payload["verdicts"][0]["evidence_ref"] = None
        with self.assertRaisesRegex(ConventionError, "verdict_evidence_ref_required"):
            load_verdict_matrix(payload)
        payload = read_verdict_matrix(SCOPE_FIXTURES["contested_unevaluated"]).payload()
        unevaluated = next(
            item for item in payload["verdicts"] if item["verdict"] == "not_evaluated"
        )
        unevaluated["evidence_ref"] = "replay.invented.v1"
        with self.assertRaisesRegex(ConventionError, "verdict_evidence_ref_forbidden"):
            load_verdict_matrix(payload)

    def test_field_sets_are_exact(self) -> None:
        payload = self.matrix.payload()
        payload["verdicts"][0]["note"] = "prose"
        with self.assertRaisesRegex(ConventionError, "verdict_field_set_mismatch"):
            load_verdict_matrix(payload)
        payload = self.matrix.payload()
        payload.pop("claim_id")
        with self.assertRaisesRegex(ConventionError, "field_set_mismatch"):
            load_verdict_matrix(payload)

    def test_a_convention_payload_cannot_load_as_a_verdict_matrix(self) -> None:
        with self.assertRaisesRegex(ConventionError, "field_set_mismatch"):
            load_verdict_matrix(self.convention.payload())
        with self.assertRaisesRegex(ConventionError, "field_set_mismatch"):
            load_convention(self.matrix.payload())


class BindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.convention = read_convention(CONVENTION)

    def test_every_fixture_matrix_binds_to_the_fixture_convention(self) -> None:
        for path in SCOPE_FIXTURES.values():
            with self.subTest(path=path.name):
                require_convention_binding(read_verdict_matrix(path), self.convention)

    def test_rereading_a_word_strands_every_matrix_asserted_under_the_old_reading(self) -> None:
        payload = copy.deepcopy(self.convention.payload())
        payload["terms"][0]["readings"][0]["reading_status"] = "verbatim_confirmed"
        rehashed = load_convention(
            ConventionRecord(
                convention_id=self.convention.convention_id,
                subject_ids=self.convention.subject_ids,
                coupled_subject_ids=self.convention.coupled_subject_ids,
                terms=(
                    ContestedTerm(
                        term_id=self.convention.terms[0].term_id,
                        term=self.convention.terms[0].term,
                        readings=(
                            Reading(
                                reading_id="even_includes_v",
                                statement=self.convention.terms[0].readings[0].statement,
                                source_passage_ref="psg.wow.even-definition",
                                reading_status="verbatim_confirmed",
                                attributed_to="adaivy",
                            ),
                            self.convention.terms[0].readings[1],
                        ),
                    ),
                    self.convention.terms[1],
                ),
            ).finalized().payload()
        )
        self.assertNotEqual(self.convention.content_hash, rehashed.content_hash)
        for path in SCOPE_FIXTURES.values():
            with self.subTest(path=path.name):
                with self.assertRaisesRegex(ConventionError, "convention_hash_mismatch"):
                    require_convention_binding(read_verdict_matrix(path), rehashed)

    def test_a_matrix_naming_another_convention_is_refused(self) -> None:
        loaded = read_verdict_matrix(SCOPE_FIXTURES["unconditional"])
        payload = loaded.payload()
        payload["convention_id"] = "conv.other-readings.v1"
        payload["content_hash"] = VerdictMatrix(
            matrix_id=loaded.matrix_id, claim_id=loaded.claim_id,
            convention_id="conv.other-readings.v1",
            convention_hash=loaded.convention_hash, verdicts=loaded.verdicts,
        ).finalized().content_hash
        with self.assertRaisesRegex(ConventionError, "convention_id_mismatch"):
            require_convention_binding(load_verdict_matrix(payload), self.convention)

    def test_binding_enforces_exact_reading_coverage(self) -> None:
        loaded = read_verdict_matrix(SCOPE_FIXTURES["unconditional"])
        partial = VerdictMatrix(
            matrix_id=loaded.matrix_id, claim_id=loaded.claim_id,
            convention_id=loaded.convention_id,
            convention_hash=loaded.convention_hash,
            verdicts=loaded.verdicts[:3],
        ).finalized()
        self.assertEqual("unconditional", partial.scope())
        with self.assertRaisesRegex(ConventionError, "verdict_matrix_incomplete"):
            require_convention_binding(partial, self.convention)


class WeakestReadingStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.convention = read_convention(CONVENTION)

    def test_the_shipped_result_rests_on_a_passage_nobody_could_re_extract(self) -> None:
        for reading_tuple in self.convention.reading_tuples():
            with self.subTest(reading_tuple=reading_tuple):
                self.assertEqual(
                    "asserted", weakest_reading_status(self.convention, reading_tuple)
                )

    def test_a_tuple_is_only_as_strong_as_its_weakest_reading(self) -> None:
        record = ConventionRecord(
            convention_id="conv.test.mixed.v1", subject_ids=("problem.test",),
            coupled_subject_ids=(),
            terms=(
                ContestedTerm(
                    term_id="first_term", term="A",
                    readings=(
                        Reading(
                            reading_id="a_confirmed", statement="Confirmed reading.",
                            source_passage_ref="psg.test.a", reading_status="verbatim_confirmed",
                            attributed_to=None,
                        ),
                        Reading(
                            reading_id="a_asserted", statement="Asserted reading.",
                            source_passage_ref="psg.test.a", reading_status="asserted",
                            attributed_to=None,
                        ),
                    ),
                ),
                ContestedTerm(
                    term_id="second_term", term="B",
                    readings=(
                        Reading(
                            reading_id="b_confirmed", statement="Confirmed reading.",
                            source_passage_ref="psg.test.b", reading_status="verbatim_confirmed",
                            attributed_to=None,
                        ),
                        Reading(
                            reading_id="b_transcribed", statement="Transcribed reading.",
                            source_passage_ref="psg.test.b", reading_status="transcribed",
                            attributed_to=None,
                        ),
                    ),
                ),
            ),
        ).finalized()
        expected = {
            ("a_asserted", "b_confirmed"): "asserted",
            ("a_asserted", "b_transcribed"): "asserted",
            ("a_confirmed", "b_confirmed"): "verbatim_confirmed",
            ("a_confirmed", "b_transcribed"): "transcribed",
        }
        self.assertEqual(tuple(sorted(expected)), record.reading_tuples())
        for reading_tuple, status in expected.items():
            with self.subTest(reading_tuple=reading_tuple):
                self.assertEqual(status, weakest_reading_status(record, reading_tuple))

    def test_an_unenumerated_reading_tuple_is_refused(self) -> None:
        with self.assertRaisesRegex(ConventionError, "reading_tuple_not_enumerated"):
            weakest_reading_status(self.convention, ("even_includes_v",))
        with self.assertRaisesRegex(ConventionError, "reading_tuple_not_enumerated"):
            weakest_reading_status(self.convention, ("even_includes_v", "range_undefined"))


class CommandLineTests(unittest.TestCase):
    def run_cli(self, argv: list[str], *, main=conventions_main) -> tuple[int, dict]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            status = main(argv)
        return status, json.loads(stream.getvalue())

    def test_inspect_reports_reading_tuples_and_the_derived_scope(self) -> None:
        status, report = self.run_cli(["inspect", str(CONVENTION)])
        self.assertEqual(0, status)
        self.assertIsNone(report["derived_scope"])
        self.assertEqual(
            ["asserted"] * 4,
            [item["weakest_reading_status"] for item in report["reading_tuples"]],
        )
        self.assertIs(False, report["resolves_contested_reading"])
        for scope, path in SCOPE_FIXTURES.items():
            with self.subTest(scope=scope):
                status, report = self.run_cli(
                    ["inspect", str(CONVENTION), "--matrix", str(path)]
                )
                self.assertEqual(0, status)
                self.assertEqual(scope, report["derived_scope"])
                self.assertEqual(4, len(report["verdict_matrix"]["verdicts"]))

    def test_inspect_refuses_a_matrix_bound_to_another_reading_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "matrix.json"
            loaded = read_verdict_matrix(SCOPE_FIXTURES["unconditional"])
            payload = loaded.payload()
            payload["convention_hash"] = "sha256:" + "b" * 64
            payload["content_hash"] = VerdictMatrix(
                matrix_id=loaded.matrix_id, claim_id=loaded.claim_id,
                convention_id=loaded.convention_id,
                convention_hash="sha256:" + "b" * 64, verdicts=loaded.verdicts,
            ).finalized().content_hash
            path.write_text(json.dumps(payload), encoding="utf-8")
            status, report = self.run_cli(
                ["inspect", str(CONVENTION), "--matrix", str(path)]
            )
            self.assertEqual(2, status)
            self.assertEqual(
                {"accepted": False, "reason": "convention_hash_mismatch"}, report
            )

    def test_couplings_lists_the_subjects_a_reading_change_invalidates(self) -> None:
        status, report = self.run_cli(["couplings", str(CONVENTION)])
        self.assertEqual(0, status)
        self.assertEqual(
            [
                {
                    "reading_id": reading_id,
                    "subject_ids": ["problem.graffiti-197", "problem.graffiti-322"],
                }
                for reading_id in (
                    "even_excludes_v", "even_includes_v", "range_distinct_count",
                    "range_extent",
                )
            ],
            report["coupled_by_reading"],
        )

    def test_a_missing_record_is_a_coded_refusal_and_not_a_traceback(self) -> None:
        status, report = self.run_cli(["inspect", str(FIXTURES / "absent.json")])
        self.assertEqual(2, status)
        self.assertIs(False, report["accepted"])

    def test_the_subcommand_is_reachable_from_the_root_cli(self) -> None:
        for argv in (["couplings", str(CONVENTION)], ["inspect", str(CONVENTION)]):
            with self.subTest(argv=argv[0]):
                status, report = self.run_cli(["conventions", *argv], main=root_main)
                self.assertEqual(0, status)
                self.assertEqual(
                    "conv.graffiti-322-readings.v1",
                    report.get("convention_id")
                    or report["conventions"][0]["convention_id"],
                )


class FixtureIntegrityTests(unittest.TestCase):
    def test_every_fixture_is_loadable_and_content_bound(self) -> None:
        paths = sorted(FIXTURES.glob("*.json"))
        self.assertEqual(5, len(paths))
        for path in paths:
            with self.subTest(path=path.name):
                value = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(SCHEMA_VERSION, value["schema_version"])
                loader = load_convention if "convention_id" in value and "terms" in value else load_verdict_matrix
                record = loader(path.read_bytes())
                self.assertEqual(record.content_hash, record.finalized().content_hash)

    def test_the_four_scopes_are_each_demonstrated_by_a_distinct_fixture(self) -> None:
        convention = read_convention(CONVENTION)
        observed = {
            read_verdict_matrix(path).scope(convention=convention): path.name
            for path in SCOPE_FIXTURES.values()
        }
        self.assertEqual(set(CONVENTION_SCOPES), set(observed))
        self.assertEqual(4, len(set(observed.values())))


if __name__ == "__main__":
    unittest.main()
