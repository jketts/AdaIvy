"""Acceptance scenarios ERS-AC-02 through ERS-AC-05.

Scenario definitions are normative in
`docs/phase-4/EXPLORATORY_RESEARCH_SYNTHESIS_V1.md` Section 14. Each test
asserts the expected output, the required trace, and — critically — that the
scenario's forbidden output is impossible rather than merely absent.
"""

from __future__ import annotations

import unittest

import sys
from pathlib import Path

# See tests/synthesis_fixtures.py: makes the sibling helper import work whether
# this module is run via `unittest discover -s tests` or by dotted module name.
sys.path.insert(0, str(Path(__file__).resolve().parent))


from math_research.synthesis.admission import (
    AdmissionPolicy,
    ExclusionReason,
    evaluate_admission,
)
from math_research.synthesis.composition import COMPARED_DIMENSIONS, compare_for_composition
from math_research.synthesis.records import ResultRelation, StateAxes
from math_research.synthesis.representation import (
    detect_disagreements,
    narrow_fidelity,
    permitted_fidelity,
)
from math_research.synthesis.state import (
    ExtractionFidelity,
    SynthesisValidationError,
    GraphAdmission,
    MathematicalWarrant,
    MismatchKind,
    SourceApplicability,
)
from synthesis_fixtures import anchor, artifact_hash, eligible_axes, result

CLOSURE = "sha256:" + "a" * 64
POLICY = AdmissionPolicy.create(
    view_id="view.synthesis-main",
    permitted_warrants=["proof_reviewed", "formally_verified"],
    minimum_documented_warrant="proof_reviewed",
)


def admit(subject_id, axes, *, kind="structured_result", comparisons=()):
    return evaluate_admission(
        POLICY,
        subject_id=subject_id,
        subject_kind=kind,
        axes=axes,
        input_record_ids=[subject_id],
        influence_closure_id=CLOSURE,
        admitting_actor_id="actor.owner",
        admitting_authority="human_final",
        comparisons=comparisons,
    )


class QuantifierMismatchTests(unittest.TestCase):
    """ERS-AC-02: quantifier mismatch rejection."""

    def setUp(self) -> None:
        # Individually eligible results. The premise proves a universal claim;
        # the consumer needs the same variable only existentially.
        self.premise = result(
            result_id="result.universal-premise",
            statement="For every n >= 1 the operator sum S(n) is positive.",
            conclusion="S(n) is positive for every n",
            quantifiers=({"variable": "n", "kind": "universal", "bound": "n >= 1"},),
        )
        self.consumer = result(
            result_id="result.existential-consumer",
            statement="There exists n >= 1 with S(n) positive, hence the bound holds.",
            assumptions=("S(n) is positive for every n",),
            conclusion="the bound holds",
            quantifiers=({"variable": "n", "kind": "existential", "bound": "n >= 1"},),
        )

    def test_quantifier_comparison_is_explicit_in_the_trace(self) -> None:
        comparison = compare_for_composition(
            self.premise, self.consumer, consumed_term="S(n) is positive for every n"
        )
        self.assertIn("quantifier_kinds_and_bounds", comparison.compared_dimensions)
        self.assertIn(MismatchKind.QUANTIFIER.value, comparison.mismatch_kinds())
        # Every mismatch opens an obligation (Section 8).
        self.assertTrue(comparison.obligation_ids())

    def test_composition_is_excluded_with_a_named_quantifier_reason(self) -> None:
        comparison = compare_for_composition(
            self.premise, self.consumer, consumed_term="S(n) is positive for every n"
        )
        record = admit(
            "result.existential-consumer",
            eligible_axes(),
            kind="composition",
            comparisons=[comparison],
        )
        self.assertIs(record.decision, GraphAdmission.EXCLUDED_UNDER_POLICY)
        self.assertIn(ExclusionReason.COMPOSITION_MISMATCH, record.exclusion_reasons)
        self.assertTrue(
            any(MismatchKind.QUANTIFIER.value in item for item in record.exclusion_detail)
        )

    def test_forbidden_admitted_composition_is_impossible(self) -> None:
        """Forbidden: an admitted composition or silent quantifier weakening."""
        comparison = compare_for_composition(
            self.premise, self.consumer, consumed_term="S(n) is positive for every n"
        )
        # Even with perfect axes on every other dimension, the mismatch alone
        # forces exclusion. There is no argument combination that admits it.
        for warrant in (MathematicalWarrant.PROOF_REVIEWED, MathematicalWarrant.FORMALLY_VERIFIED):
            with self.subTest(warrant=warrant):
                record = admit(
                    "result.existential-consumer",
                    eligible_axes(warrant=warrant),
                    kind="composition",
                    comparisons=[comparison],
                )
                self.assertNotEqual(record.decision, GraphAdmission.ADMITTED_UNDER_POLICY)

    def test_matching_quantifiers_leave_no_mismatch(self) -> None:
        """False-positive control: the detector must not fire on agreement."""
        consumer = result(
            result_id="result.universal-consumer",
            statement="For every n >= 1, since S(n) is positive for every n, the bound holds.",
            assumptions=("S(n) is positive for every n",),
            conclusion="the bound holds",
            quantifiers=({"variable": "n", "kind": "universal", "bound": "n >= 1"},),
        )
        comparison = compare_for_composition(
            self.premise, consumer, consumed_term="S(n) is positive for every n"
        )
        self.assertEqual(comparison.mismatches, ())
        self.assertTrue(comparison.compatible)


class DomainTypeRegularityMismatchTests(unittest.TestCase):
    """ERS-AC-03: domain, type, or regularity mismatch rejection."""

    def premise_consumer(self, **consumer_kwargs):
        premise = result(
            result_id="result.premise-real",
            statement="On finite dimensional spaces the map M is contractive.",
            conclusion="M is contractive",
            domains=("finite_dimensional_hilbert_space",),
            object_types=("positive_semidefinite_operator",),
            regularity=(),
        )
        consumer = result(
            result_id="result.consumer-other",
            statement="Given M contractive the limit exists.",
            assumptions=("M is contractive",),
            conclusion="the limit exists",
            **consumer_kwargs,
        )
        return premise, consumer

    def test_domain_mismatch_is_named_and_excluded(self) -> None:
        premise, consumer = self.premise_consumer(domains=("separable_banach_space",))
        comparison = compare_for_composition(premise, consumer, consumed_term="M is contractive")
        self.assertIn(MismatchKind.DOMAIN.value, comparison.mismatch_kinds())
        record = admit(consumer.result_id, eligible_axes(), kind="composition", comparisons=[comparison])
        self.assertIs(record.decision, GraphAdmission.EXCLUDED_UNDER_POLICY)
        # Expected: an unresolved obligation accompanies the exclusion.
        self.assertTrue(comparison.obligation_ids())

    def test_object_type_mismatch_is_named(self) -> None:
        premise, consumer = self.premise_consumer(object_types=("unbounded_self_adjoint_operator",))
        comparison = compare_for_composition(premise, consumer, consumed_term="M is contractive")
        self.assertIn(MismatchKind.OBJECT_TYPE.value, comparison.mismatch_kinds())

    def test_codomain_mismatch_is_named(self) -> None:
        premise, consumer = self.premise_consumer(codomains=("complex_numbers",))
        comparison = compare_for_composition(premise, consumer, consumed_term="M is contractive")
        self.assertIn(MismatchKind.CODOMAIN.value, comparison.mismatch_kinds())

    def test_regularity_mismatch_is_named(self) -> None:
        premise, consumer = self.premise_consumer(regularity=("twice_continuously_differentiable",))
        comparison = compare_for_composition(premise, consumer, consumed_term="M is contractive")
        self.assertIn(MismatchKind.REGULARITY.value, comparison.mismatch_kinds())

    def test_no_coercion_or_assumption_insertion_occurs(self) -> None:
        """Forbidden: coercion or assumption insertion.

        The comparison must report the gap rather than repair it, so the
        consumer's own declared requirements are unchanged afterwards.
        """
        premise, consumer = self.premise_consumer(domains=("separable_banach_space",))
        before = consumer.value()
        compare_for_composition(premise, consumer, consumed_term="M is contractive")
        self.assertEqual(consumer.value(), before)
        self.assertEqual(consumer.domains, ("separable_banach_space",))


class ScopeAndAssumptionMismatchTests(unittest.TestCase):
    """Adversarial control: restrictions cannot disappear in composition."""

    def test_incompatible_scope_and_extra_assumption_cannot_be_admitted(self) -> None:
        premise = result(
            result_id="result.finite-scope-premise",
            statement="For finite systems, M is contractive.",
            conclusion="M is contractive",
            scope=("finite systems",),
        )
        consumer = result(
            result_id="result.all-systems-consumer",
            statement="For all systems, compactness and contractivity imply convergence.",
            assumptions=("M is contractive", "the state space is compact"),
            conclusion="the iteration converges",
            scope=("all systems",),
        )

        comparison = compare_for_composition(premise, consumer, consumed_term="M is contractive")

        self.assertIn(MismatchKind.ASSUMPTION.value, comparison.mismatch_kinds())
        self.assertIn(MismatchKind.SCOPE_OR_EXCEPTION.value, comparison.mismatch_kinds())
        self.assertFalse(comparison.compatible)
        admission = admit(
            consumer.result_id,
            eligible_axes(),
            kind="composition",
            comparisons=[comparison],
        )
        self.assertIs(admission.decision, GraphAdmission.EXCLUDED_UNDER_POLICY)
        self.assertIn(ExclusionReason.COMPOSITION_MISMATCH, admission.exclusion_reasons)


class NotationEquivalenceTests(unittest.TestCase):
    """ERS-AC-04: notation equivalence with false-positive control."""

    def relation(self, left, right, *, relation_id, axes):
        return ResultRelation.from_value(
            {
                "relation_id": relation_id,
                "relation_type": "equivalent_to",
                "source_result_id": left.result_id,
                "source_result_digest": left.semantic_digest(),
                "target_result_id": right.result_id,
                "target_result_digest": right.semantic_digest(),
                "proposer_id": "actor.proposer",
                "extractor_id": "actor.extractor",
                "evidence_anchors": [anchor(source_id="source.a").value()],
                "comparison_rationale": "declared notation correspondence",
                "open_obligation_ids": [],
                "axes": axes.value(),
            }
        )

    def test_valid_pair_moves_from_proposed_to_admitted(self) -> None:
        # Same symbol, same definition, same normalization rule.
        left = result(
            result_id="result.notation-left",
            statement="Tr(T rho) equals one.",
            conclusion="Tr(T rho) = 1",
            definition_mapping=({"symbol": "T", "definition": "a trace-preserving map"},),
        )
        right = result(
            result_id="result.notation-right",
            statement="The trace of T applied to rho equals one.",
            assumptions=("Tr(T rho) = 1",),
            conclusion="normalization holds",
            definition_mapping=({"symbol": "T", "definition": "a trace-preserving map"},),
        )
        comparison = compare_for_composition(left, right, consumed_term="Tr(T rho) = 1")
        self.assertEqual(comparison.mismatches, ())
        relation = self.relation(left, right, relation_id="relation.valid", axes=eligible_axes())
        # The relation starts proposed and carries its own axes.
        self.assertIs(relation.axes.graph_admission, GraphAdmission.PROPOSED)
        record = evaluate_admission(
            POLICY,
            subject_id=relation.relation_id,
            subject_kind="result_relation",
            axes=relation.axes,
            input_record_ids=[left.result_id, right.result_id],
            influence_closure_id=CLOSURE,
            admitting_actor_id="actor.owner",
            admitting_authority="human_final",
            comparisons=[comparison],
        )
        self.assertIs(record.decision, GraphAdmission.ADMITTED_UNDER_POLICY)

    def test_control_reusing_a_symbol_in_another_domain_is_excluded(self) -> None:
        """Forbidden: symbol-string equality as equivalence evidence."""
        left = result(
            result_id="result.control-left",
            statement="Tr(T rho) equals one.",
            conclusion="Tr(T rho) = 1",
            domains=("finite_dimensional_hilbert_space",),
            definition_mapping=({"symbol": "T", "definition": "a trace-preserving map"},),
        )
        control = result(
            result_id="result.control-right",
            statement="T denotes the stopping time of the walk.",
            assumptions=("Tr(T rho) = 1",),
            conclusion="the walk terminates",
            domains=("discrete_probability_space",),
            definition_mapping=({"symbol": "T", "definition": "a stopping time"},),
        )
        comparison = compare_for_composition(left, control, consumed_term="Tr(T rho) = 1")
        # The same symbol string is present in both, yet the definitions differ.
        self.assertIn(MismatchKind.DEFINITION.value, comparison.mismatch_kinds())
        self.assertIn(MismatchKind.DOMAIN.value, comparison.mismatch_kinds())
        relation = self.relation(left, control, relation_id="relation.control", axes=eligible_axes())
        record = evaluate_admission(
            POLICY,
            subject_id=relation.relation_id,
            subject_kind="result_relation",
            axes=relation.axes,
            input_record_ids=[left.result_id, control.result_id],
            influence_closure_id=CLOSURE,
            admitting_actor_id="actor.owner",
            admitting_authority="human_final",
            comparisons=[comparison],
        )
        self.assertIs(record.decision, GraphAdmission.EXCLUDED_UNDER_POLICY)
        self.assertIn(ExclusionReason.COMPOSITION_MISMATCH, record.exclusion_reasons)

    def test_a_relation_does_not_inherit_endpoint_states(self) -> None:
        """Section 4: a relation cannot inherit an endpoint's states."""
        left = result(result_id="result.left", statement="A.", conclusion="A")
        right = result(result_id="result.right", statement="B.", conclusion="B", assumptions=("A",))
        # Endpoints are fully eligible; the relation is not.
        relation = self.relation(
            left,
            right,
            relation_id="relation.unassessed",
            axes=StateAxes(
                source_applicability=SourceApplicability.PROPOSED,
                extraction_fidelity=ExtractionFidelity.PROPOSED_EXTRACTION,
                mathematical_warrant=MathematicalWarrant.UNASSESSED,
                graph_admission=GraphAdmission.PROPOSED,
            ),
        )
        self.assertIs(left.axes.source_applicability, SourceApplicability.CHECKED)
        self.assertIs(relation.axes.source_applicability, SourceApplicability.PROPOSED)
        record = evaluate_admission(
            POLICY,
            subject_id=relation.relation_id,
            subject_kind="result_relation",
            axes=relation.axes,
            input_record_ids=[left.result_id, right.result_id],
            influence_closure_id=CLOSURE,
            admitting_actor_id="actor.owner",
            admitting_authority="human_final",
        )
        self.assertIs(record.decision, GraphAdmission.EXCLUDED_UNDER_POLICY)


class RepresentationDisagreementTests(unittest.TestCase):
    """ERS-AC-05: version or representation disagreement."""

    def setUp(self) -> None:
        self.tex = result(
            result_id="result.tex-reading",
            statement="The iteration converges for every full-support prior.",
            conclusion="the iteration converges",
            anchors=(anchor(source_id="source.paper", version="v1", role="tex_source"),),
        )
        # Same source, different retained representation, materially different
        # statement: the PDF reading drops the full-support hypothesis.
        self.pdf = result(
            result_id="result.pdf-reading",
            statement="The iteration converges for every prior.",
            conclusion="the iteration converges",
            anchors=(anchor(source_id="source.paper", version="v1", role="born_digital_pdf"),),
        )

    def test_disagreement_produces_a_warning_with_exact_identities(self) -> None:
        warnings = detect_disagreements([self.tex, self.pdf])
        self.assertEqual(len(warnings), 1)
        warning = warnings[0]
        self.assertEqual(warning.source_id, "source.paper")
        self.assertEqual(warning.difference_kind, "representation_disagreement")
        # Exact identities, hashes, and anchors are all recorded.
        self.assertNotEqual(warning.left_statement_hash, warning.right_statement_hash)
        self.assertEqual(
            warning.left_artifact_hash, artifact_hash("source.paper:v1:born_digital_pdf")
        )
        self.assertEqual({warning.left_role, warning.right_role}, {"tex_source", "born_digital_pdf"})

    def test_warning_identity_is_independent_of_input_order(self) -> None:
        first = detect_disagreements([self.tex, self.pdf])
        second = detect_disagreements([self.pdf, self.tex])
        self.assertEqual([item.value() for item in first], [item.value() for item in second])

    def test_disputed_content_cannot_reach_source_checked(self) -> None:
        warnings = detect_disagreements([self.tex, self.pdf])
        for disputed in (self.tex, self.pdf):
            with self.subTest(result_id=disputed.result_id):
                self.assertIs(
                    permitted_fidelity(disputed, warnings=warnings),
                    ExtractionFidelity.PROPOSED_EXTRACTION,
                )

    def test_disputed_content_stays_excluded_until_narrowed(self) -> None:
        warnings = detect_disagreements([self.tex, self.pdf])
        axes = StateAxes(
            source_applicability=SourceApplicability.CHECKED,
            extraction_fidelity=permitted_fidelity(self.tex, warnings=warnings),
            mathematical_warrant=MathematicalWarrant.PROOF_REVIEWED,
            graph_admission=GraphAdmission.PROPOSED,
        )
        record = admit(self.tex.result_id, axes)
        self.assertIs(record.decision, GraphAdmission.EXCLUDED_UNDER_POLICY)
        self.assertIn(ExclusionReason.EXTRACTION_NOT_CHECKED, record.exclusion_reasons)

    def test_explicit_narrowing_resolves_the_chosen_representation_only(self) -> None:
        warnings = detect_disagreements([self.tex, self.pdf])
        narrowing = narrow_fidelity(
            warnings[0],
            chosen=self.tex,
            rationale="the TeX source layer carries the full-support hypothesis",
            narrowed_by="actor.reviewer",
        )
        self.assertIs(
            permitted_fidelity(self.tex, warnings=warnings, narrowings=[narrowing]),
            ExtractionFidelity.SOURCE_CHECKED,
        )
        # The representation that was narrowed away is rejected, not silently
        # promoted alongside the chosen one.
        self.assertIs(
            permitted_fidelity(self.pdf, warnings=warnings, narrowings=[narrowing]),
            ExtractionFidelity.EXTRACTION_REJECTED,
        )

    def test_no_silent_representation_selection_occurs(self) -> None:
        """Forbidden: silent representation selection or overwritten source text.

        Detection alone must not choose a layer, and both exact statements must
        survive unchanged.
        """
        before = (self.tex.exact_statement, self.pdf.exact_statement)
        detect_disagreements([self.tex, self.pdf])
        self.assertEqual((self.tex.exact_statement, self.pdf.exact_statement), before)
        self.assertNotEqual(self.tex.exact_statement, self.pdf.exact_statement)

    def test_narrowing_must_choose_one_of_the_disagreeing_representations(self) -> None:
        warnings = detect_disagreements([self.tex, self.pdf])
        unrelated = result(result_id="result.unrelated", statement="Z.", conclusion="Z")
        with self.assertRaises(SynthesisValidationError) as caught:
            narrow_fidelity(
                warnings[0], chosen=unrelated, rationale="wrong", narrowed_by="actor.reviewer"
            )
        self.assertIn("one of the two disagreeing representations", str(caught.exception))

    def test_identical_statements_produce_no_warning(self) -> None:
        """False-positive control: agreeing representations are not a warning."""
        agreeing = result(
            result_id="result.pdf-agreeing",
            statement=self.tex.exact_statement,
            conclusion="the iteration converges",
            anchors=(anchor(source_id="source.paper", version="v1", role="born_digital_pdf"),),
        )
        self.assertEqual(detect_disagreements([self.tex, agreeing]), ())


class ComparedDimensionTests(unittest.TestCase):
    def test_every_contract_dimension_is_compared(self) -> None:
        """Section 8 names the dimensions; the trace must list all of them."""
        for dimension in (
            "assumptions",
            "consumed_term",
            "implication_direction",
            "quantifier_kinds_and_bounds",
            "domains",
            "codomains",
            "object_types",
            "regularity",
            "definition_correspondence",
            "notation_correspondence",
            "scope_and_exceptions",
            "source_versions",
            "conclusion_strength",
        ):
            self.assertIn(dimension, COMPARED_DIMENSIONS)


if __name__ == "__main__":
    unittest.main()
