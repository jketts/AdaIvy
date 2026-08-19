from __future__ import annotations

import dataclasses
import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from math_research.application.manual_slice import ACTOR, STAMP, build_known_valid_theorem_dossier
from math_research.domain.entities import ALL_ENTITY_TYPES, AuditEvent, ProtocolPhase, oid
from math_research.domain.repositories import AppendOnlyRepository, EventStore
from math_research.domain.policies import TrustPolicy
from math_research.interchange import ENTITY_SCHEMA_VERSION
from phase0_harness.scorecard import derive_correction

ROOT = Path(__file__).resolve().parents[1]


class ImmutableEntityTests(unittest.TestCase):
    def test_required_entities_are_frozen_versioned_and_store_no_projection(self) -> None:
        required = {
            "ResearchProblem", "Formalization", "SemanticAlignmentRecord", "Claim",
            "EpistemicWarrant", "Evidence", "SourceApplicabilityRecord",
            "ProofObligation", "RepresentationMap", "VerificationRecord",
            "EvaluationProtocol", "ResearchDossier", "AuditEvent",
        }
        self.assertEqual(required, {item.__name__ for item in ALL_ENTITY_TYPES})
        for entity_type in ALL_ENTITY_TYPES:
            params = entity_type.__dataclass_params__
            self.assertTrue(params.frozen, entity_type.__name__)
            names = {field.name for field in dataclasses.fields(entity_type)}
            self.assertIn("schema_version", names)
            self.assertNotIn("truth_status", names)
            self.assertNotIn("confidence_score", names)

    def test_entities_and_opaque_ids_are_immutable(self) -> None:
        dossier = build_known_valid_theorem_dossier()
        with self.assertRaises(FrozenInstanceError):
            dossier.problem.title = "changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            dossier.id.value = "changed"  # type: ignore[misc]

    def test_confirmatory_protocol_is_frozen_and_cannot_be_revised(self) -> None:
        protocol = build_known_valid_theorem_dossier().evaluation_protocol
        self.assertEqual(ProtocolPhase.CONFIRMATORY, protocol.phase)
        self.assertTrue(protocol.is_frozen)
        with self.assertRaisesRegex(ValueError, "cannot be revised"):
            protocol.revise(metrics=("changed_after_freeze",))

    def test_projection_keeps_trust_dimensions_orthogonal(self) -> None:
        projection = TrustPolicy(build_known_valid_theorem_dossier()).target_resolution()
        self.assertEqual("approved_equivalent", projection.semantic_alignment_status)
        self.assertEqual("proved", projection.logical_status)
        self.assertEqual(("rigorous_derivation",), projection.warrant_kinds)
        self.assertEqual("not_assessed", projection.novelty_status)
        self.assertEqual("not_assessed", projection.significance_status)
        self.assertEqual("unattributed", projection.contribution_status)


class AppendOnlyRepositoryTests(unittest.TestCase):
    def test_repository_accepts_idempotent_identical_append_but_rejects_rewrite(self) -> None:
        dossier = build_known_valid_theorem_dossier()
        repository = AppendOnlyRepository()
        self.assertIs(dossier.problem, repository.append(dossier.problem))
        self.assertIs(dossier.problem, repository.append(dossier.problem))
        with self.assertRaisesRegex(ValueError, "different immutable content"):
            repository.append(replace(dossier.problem, title="rewritten"))
        self.assertEqual(1, len(repository))

    def test_retrying_event_command_does_not_duplicate_semantic_event(self) -> None:
        aggregate = oid("problem.retry.v1")
        first = AuditEvent(
            id=oid("event.retry.first"), created_at=STAMP, created_by=ACTOR,
            aggregate_id=aggregate, event_type="claim_recorded",
            payload=(("claim_id", "claim.retry.v1"),), idempotency_key="command.retry.1",
        )
        retry = replace(first, id=oid("event.retry.second"))
        store = EventStore()
        self.assertEqual(first, store.append_once(first))
        self.assertEqual(first, store.append_once(retry))
        self.assertEqual((first,), store.all())


class CorrectedScorecardTests(unittest.TestCase):
    def test_unexecuted_candidates_have_null_capability_and_raw_is_unchanged(self) -> None:
        raw_path = ROOT / "reports" / "phase-0" / "results.json"
        raw_bytes = raw_path.read_bytes()
        observed_hash = hashlib.sha256(raw_bytes).hexdigest()
        self.assertEqual("e8166fed8063ade26d74b55f0139fc2adfd2900d2c8db4a4c3fb8c4a5b144533", observed_hash)
        correction = derive_correction(json.loads(raw_bytes), raw_sha256=observed_hash)
        by_id = {item["component_id"]: item for item in correction["components"]}
        self.assertEqual(100.0, by_id["file-baseline"]["capability_score"])
        self.assertEqual(69.4, by_id["omdoc-projection"]["capability_score"])
        for item in correction["components"]:
            if item["evaluation_status"].startswith("not_evaluated"):
                self.assertIsNone(item["capability_score"])
                self.assertIsNone(item["comparison_to_file_baseline"])
                self.assertIsNone(item["integration_effort"])


if __name__ == "__main__":
    unittest.main()
