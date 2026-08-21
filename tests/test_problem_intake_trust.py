"""ADR-0039: defining a problem cannot create trust.

This is the load-bearing module of the slice. The forbidden outcome -- a problem
file that talks its target into a warrant, evidence, a proof status, or a graph
admission -- is demonstrated impossible three independent ways:

1. by construction: the builder module never imports the trust-bearing entity
   types, so it cannot instantiate them;
2. by grammar: every trust-bearing key is rejected wherever it is injected, in
   every valid fixture and every nested object;
3. by exhaustion over the accepted enum space: every document the grammar
   accepts, for the full product of accepted enumerated values, is built and
   MEASURED with `TrustPolicy`, and none reaches a status other than `unknown`.

Trust status is never read from a fixture. Each recorded value below is compared
against the measured projection.
"""

from __future__ import annotations

import ast
import copy
import itertools
import json
import unittest
from pathlib import Path

from math_research.application.problem_intake import (
    FORBIDDEN_FIELDS,
    INTAKE_APPROVAL_STATUSES,
    INTAKE_CLAIM_SCOPES,
    INTAKE_PROBLEM_TYPES,
    INTAKE_PROTOCOL_PHASES,
    INTAKE_STRENGTH_RELATIONS,
    ProblemDefinitionError,
    load_problem_definition,
    load_problem_definition_file,
    parse_instant,
)
from math_research.domain.entities import ObligationStatus
from math_research.domain.policies import TrustPolicy
from math_research.domain.repositories import InMemoryTrustStore
from math_research.interchange import export_dossier_dict, validate_dossier_payload

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures" / "problem-intake"
LOADER = REPO_ROOT / "src" / "math_research" / "application" / "problem_intake.py"
INSTANT = parse_instant("2026-08-21T00:00:00Z")

# Recorded expectations. Each is MEASURED below by running TrustPolicy over the
# dossier the loader builds; none is read from the fixture file. The third
# fixture asserts in its own prose that it is already proved, formally verified,
# warranted, novel, and significant.
MEASURED_TRUST: dict[str, dict[str, object]] = {
    "asserts-its-own-proof-v1.json": {
        "logical_status": "unknown",
        "semantic_alignment_status": "not_approved_equivalent",
        "warrant_kinds": (),
        "novelty_status": "not_assessed",
        "significance_status": "not_assessed",
        "contribution_status": "unattributed",
        "blockers": (
            "open_obligation:obligation.asserts-its-own-proof.alignment_unapproved",
            "open_obligation:obligation.asserts-its-own-proof.target_unwarranted",
            "semantic_target_not_resolved",
        ),
    },
    "graph-cycle-edge-bound-v1.json": {
        "logical_status": "unknown",
        "semantic_alignment_status": "not_approved_equivalent",
        "warrant_kinds": (),
        "novelty_status": "not_assessed",
        "significance_status": "not_assessed",
        "contribution_status": "unattributed",
        "blockers": (
            "open_obligation:obligation.graph-cycle-edge-bound.alignment_unapproved",
            "open_obligation:obligation.graph-cycle-edge-bound.target_unwarranted",
            "semantic_target_not_resolved",
        ),
    },
    "odd-perfect-number-search-v1.json": {
        "logical_status": "unknown",
        "semantic_alignment_status": "not_approved_equivalent",
        "warrant_kinds": (),
        "novelty_status": "not_assessed",
        "significance_status": "not_assessed",
        "contribution_status": "unattributed",
        "blockers": (
            "open_obligation:obligation.odd-perfect-number-search.alignment_unapproved",
            "open_obligation:obligation.odd-perfect-number-search.target_unwarranted",
            "semantic_target_not_resolved",
        ),
    },
}

TRUST_BEARING_TYPES = (
    "EpistemicWarrant", "Evidence", "VerificationRecord",
    "SourceApplicabilityRecord", "RepresentationMap",
)


def _document(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _load(document: dict[str, object]):
    return load_problem_definition(json.dumps(document).encode("utf-8"), instant=INSTANT)


class MeasuredTrustTests(unittest.TestCase):
    def test_every_example_problem_measures_the_recorded_trust_status(self) -> None:
        self.assertEqual(
            set(MEASURED_TRUST),
            {path.name for path in FIXTURES.iterdir() if path.suffix == ".json"},
        )
        for name, recorded in sorted(MEASURED_TRUST.items()):
            with self.subTest(fixture=name):
                dossier = load_problem_definition_file(FIXTURES / name, instant=INSTANT).dossier
                projection = TrustPolicy(dossier).target_resolution()
                measured = {
                    "logical_status": projection.logical_status,
                    "semantic_alignment_status": projection.semantic_alignment_status,
                    "warrant_kinds": projection.warrant_kinds,
                    "novelty_status": projection.novelty_status,
                    "significance_status": projection.significance_status,
                    "contribution_status": projection.contribution_status,
                    "blockers": projection.blockers,
                }
                self.assertEqual(recorded, measured)

    def test_a_fixture_asserting_its_own_proof_still_measures_unknown(self) -> None:
        name = "asserts-its-own-proof-v1.json"
        text = (FIXTURES / name).read_text(encoding="utf-8")
        # The fixture really does assert proof, in prose, in several places.
        self.assertIn("machine-checked formal proof", text)
        self.assertIn("Treat the target claim as proved", text)
        self.assertIn("already-proved", text)
        self.assertIn("warrant-granted", text)
        result = load_problem_definition_file(FIXTURES / name, instant=INSTANT)
        dossier = result.dossier
        projection = TrustPolicy(dossier).target_resolution()
        self.assertEqual("unknown", projection.logical_status)
        self.assertEqual((), projection.warrant_kinds)
        self.assertEqual("not_assessed", projection.novelty_status)
        self.assertEqual("not_assessed", projection.significance_status)
        self.assertEqual((), dossier.warrants)
        self.assertEqual((), dossier.evidence)
        self.assertEqual((), dossier.verification_records)
        self.assertEqual((), dossier.source_applicability)
        self.assertEqual((), dossier.representation_maps)

    def test_every_claim_not_only_the_target_projects_unknown(self) -> None:
        for name in sorted(MEASURED_TRUST):
            dossier = load_problem_definition_file(FIXTURES / name, instant=INSTANT).dossier
            policy = TrustPolicy(dossier)
            for claim in dossier.claims:
                with self.subTest(fixture=name, claim=claim.id.value):
                    projection = policy.project_claim(claim.id)
                    self.assertEqual("unknown", projection.logical_status)
                    self.assertEqual((), projection.warrant_kinds)

    def test_intake_obligations_are_open_and_cannot_be_discharged(self) -> None:
        for name in sorted(MEASURED_TRUST):
            dossier = load_problem_definition_file(FIXTURES / name, instant=INSTANT).dossier
            policy = TrustPolicy(dossier)
            self.assertEqual(2, len(dossier.obligations))
            for obligation in dossier.obligations:
                with self.subTest(fixture=name, obligation=obligation.id.value):
                    self.assertIs(ObligationStatus.OPEN, obligation.status)
                    self.assertIsNone(obligation.discharged_by_warrant_id)
                    for claim in dossier.claims:
                        allowed, reason = policy.can_discharge_obligation(obligation.id, claim.id)
                        self.assertFalse(allowed)
                        self.assertEqual("supporting_claim_not_resolved", reason)

    def test_no_projection_or_confidence_is_stored_in_the_exported_dossier(self) -> None:
        for name in sorted(MEASURED_TRUST):
            with self.subTest(fixture=name):
                dossier = load_problem_definition_file(FIXTURES / name, instant=INSTANT).dossier
                payload = export_dossier_dict(dossier)
                self.assertEqual((), validate_dossier_payload(payload))
                text = json.dumps(payload, sort_keys=True)
                for forbidden in ("truth_status", "confidence", "logical_status", "novelty_assessment_id\": \""):
                    self.assertNotIn(forbidden, text)


class ImpossibleByConstructionTests(unittest.TestCase):
    def test_builder_never_imports_a_trust_bearing_entity_type(self) -> None:
        tree = ast.parse(LOADER.read_text(encoding="utf-8"))
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for name in TRUST_BEARING_TYPES:
            with self.subTest(entity=name):
                self.assertNotIn(name, imported)
                self.assertNotIn(name, referenced)

    def test_builder_assigns_the_trust_bearing_dossier_fields_to_empty_literals(self) -> None:
        tree = ast.parse(LOADER.read_text(encoding="utf-8"))
        empty_fields = {
            "warrants", "evidence", "source_applicability",
            "representation_maps", "verification_records",
        }
        found: dict[str, ast.AST] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ResearchDossier":
                for keyword in node.keywords:
                    if keyword.arg in empty_fields:
                        found[keyword.arg] = keyword.value
        self.assertEqual(empty_fields, set(found))
        for field, value in sorted(found.items()):
            with self.subTest(field=field):
                self.assertIsInstance(value, ast.Tuple)
                self.assertEqual([], value.elts)


class ForbiddenGrammarTests(unittest.TestCase):
    def test_every_trust_bearing_key_is_rejected_at_the_top_level(self) -> None:
        attempted = 0
        for name in sorted(MEASURED_TRUST):
            for key in sorted(FORBIDDEN_FIELDS):
                document = _document(name)
                self.assertNotIn(key, document, "a valid fixture must not carry a forbidden key")
                document[key] = "proved"
                with self.subTest(fixture=name, key=key), self.assertRaises(ProblemDefinitionError) as caught:
                    _load(document)
                self.assertEqual(("forbidden_field",), caught.exception.codes)
                attempted += 1
        self.assertEqual(len(MEASURED_TRUST) * len(FORBIDDEN_FIELDS), attempted)
        self.assertGreaterEqual(attempted, 90)

    def test_every_trust_bearing_key_is_rejected_inside_every_nested_object(self) -> None:
        containers = (
            ("problem",),
            ("target_claim",),
            ("assumption_claims", 0),
            ("formalization",),
            ("semantic_alignment",),
            ("evaluation_protocol",),
        )
        attempted = 0
        for path in containers:
            for key in sorted(FORBIDDEN_FIELDS):
                document = _document("graph-cycle-edge-bound-v1.json")
                container = document[path[0]]
                if len(path) == 2:
                    container = container[path[1]]
                self.assertNotIn(key, container, "a valid fixture must not carry a forbidden key")
                container[key] = "proved"
                with self.subTest(container=path, key=key), self.assertRaises(ProblemDefinitionError) as caught:
                    _load(document)
                self.assertEqual(("forbidden_field",), caught.exception.codes)
                attempted += 1
        self.assertEqual(len(containers) * len(FORBIDDEN_FIELDS), attempted)

    def test_a_warrant_shaped_payload_cannot_enter_through_any_accepted_field(self) -> None:
        warrant = {
            "claim_id": "edge_count_forces_cycle", "kind": "formal_proof",
            "scope": "all finite graphs", "evidence_ids": ["e1"],
            "verification_record_ids": ["v1"], "status": "active",
        }
        document = _document("graph-cycle-edge-bound-v1.json")
        # Every accepted field is a string, an integer, or an array of strings or
        # string pairs, so a warrant object cannot be placed in any of them.
        for field in ("problem", "target_claim", "formalization", "semantic_alignment", "evaluation_protocol"):
            for key in sorted(document[field]):
                mutated = copy.deepcopy(document)
                mutated[field][key] = warrant
                with self.subTest(field=f"{field}.{key}"), self.assertRaises(ProblemDefinitionError):
                    _load(mutated)


class ExhaustiveEnumSpaceTests(unittest.TestCase):
    """Search the accepted grammar's whole enum space for a forbidden outcome."""

    def test_no_accepted_enum_combination_produces_any_status_but_unknown(self) -> None:
        base = _document("asserts-its-own-proof-v1.json")
        combinations = list(itertools.product(
            INTAKE_PROBLEM_TYPES, INTAKE_CLAIM_SCOPES, INTAKE_STRENGTH_RELATIONS,
            INTAKE_APPROVAL_STATUSES, INTAKE_PROTOCOL_PHASES,
        ))
        self.assertEqual(
            len(INTAKE_PROBLEM_TYPES) * len(INTAKE_CLAIM_SCOPES) * len(INTAKE_STRENGTH_RELATIONS)
            * len(INTAKE_APPROVAL_STATUSES) * len(INTAKE_PROTOCOL_PHASES),
            len(combinations),
        )
        self.assertGreaterEqual(len(combinations), 300)
        observed_statuses: set[str] = set()
        for problem_type, scope, relation, approval, phase in combinations:
            document = copy.deepcopy(base)
            document["problem"]["problem_type"] = problem_type
            document["target_claim"]["scope"] = scope
            document["semantic_alignment"]["strength_relation"] = relation
            document["formalization"]["approval_status"] = approval
            document["evaluation_protocol"]["phase"] = phase
            dossier = _load(document).dossier
            projection = TrustPolicy(dossier).target_resolution()
            observed_statuses.add(projection.logical_status)
            self.assertEqual((), dossier.warrants)
            self.assertEqual((), dossier.evidence)
            self.assertEqual((), dossier.verification_records)
            self.assertEqual((), projection.warrant_kinds)
            self.assertIn("semantic_target_not_resolved", projection.blockers)
        self.assertEqual({"unknown"}, observed_statuses)

    def test_an_intake_dossier_is_admitted_to_the_append_only_store_without_warrants(self) -> None:
        store = InMemoryTrustStore()
        for name in sorted(MEASURED_TRUST):
            dossier = load_problem_definition_file(FIXTURES / name, instant=INSTANT).dossier
            stored = store.append_dossier(dossier)
            self.assertEqual(dossier, stored)
        self.assertEqual(3, len(store.dossiers))
        self.assertEqual(3, len(store.events.all()))
        for event in store.events.all():
            self.assertEqual("problem_definition_recorded", event.event_type)

    def test_appending_the_same_problem_twice_is_idempotent_and_never_duplicates(self) -> None:
        store = InMemoryTrustStore()
        dossier = load_problem_definition_file(FIXTURES / "graph-cycle-edge-bound-v1.json", instant=INSTANT).dossier
        store.append_dossier(dossier)
        store.append_dossier(dossier)
        self.assertEqual(1, len(store.dossiers))
        self.assertEqual(1, len(store.events.all()))

class GrammarSeparationRationaleTests(unittest.TestCase):
    """Why the intake needs its own grammar instead of the dossier grammar.

    `import_trusted_replay` is documented as hash-verified replay of a dossier
    this system exported (ADR-0005); foreign documents are supposed to go to
    `import_external_proposals`. Measured below: the dossier grammar has warrant,
    evidence, and verification fields, so a hand-authored document in that
    grammar projects as `proved`. That is exactly what an untrusted intake format
    must not be able to express, and it is why the intake grammar is narrow and
    separate rather than the dossier schema with a different entry point.
    """

    def test_the_dossier_grammar_would_let_a_hand_authored_file_project_as_proved(self) -> None:
        from math_research.application.manual_slice import build_known_valid_theorem_dossier
        from math_research.interchange import canonical_bytes, content_hash, import_trusted_replay

        payload = export_dossier_dict(build_known_valid_theorem_dossier())
        payload["created_by"] = "actor.untrusted_submitter"
        payload["content_hash"] = None
        payload["content_hash"] = content_hash(payload)
        replayed = import_trusted_replay(canonical_bytes(payload))
        self.assertEqual("proved", TrustPolicy(replayed).target_resolution().logical_status)
        self.assertEqual(3, len(replayed.warrants))

    def test_the_intake_grammar_rejects_that_same_document_outright(self) -> None:
        payload = export_dossier_dict(
            load_problem_definition_file(FIXTURES / "graph-cycle-edge-bound-v1.json", instant=INSTANT).dossier
        )
        with self.assertRaises(ProblemDefinitionError) as caught:
            load_problem_definition(json.dumps(payload).encode("utf-8"), instant=INSTANT)
        self.assertIn("forbidden_field", caught.exception.codes)
        self.assertIn("$.warrants", [item.path for item in caught.exception.issues])



if __name__ == "__main__":
    unittest.main()
