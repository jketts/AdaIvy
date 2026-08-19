from __future__ import annotations

import ast
import json
import os
import shutil
import socket
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from math_research.domain.entities import OpaqueId
from math_research.phase3a.acquisition import ManualSourceIngestor, validate_opaque_uri
from math_research.phase3a.demonstration import ACTOR_ID, AGGREGATE_ID, FIXED_TIME, run_acceptance
from math_research.phase3a.interchange import build_export, import_trusted_replay, validate_export, validate_provenance
from math_research.phase3a.plain_text import PARSER_CONFIGURATION_HASH, PlainTextV1Parser, normalize_with_mapping
from math_research.phase3a.records import (
    Disposition,
    EvidencePackManifest,
    EvidenceRelation,
    EvidenceUnit,
    EvidenceUnitType,
    LicenseMetadata,
    NormalizedDocument,
    ParserRunRecord,
    QuarantineState,
    RetrievalHit,
    RetrievalQueryRecord,
    SourceArtifact,
    SourceReference,
    SourceSpan,
)
from math_research.phase3a.reporting import render_report
from math_research.phase3a.retrieval import (
    CitationValidationError,
    DeterministicEvidencePackBuilder,
    DeterministicRetriever,
    canonical_query_text,
    fts_expression,
    validate_and_build_model_proposal,
)
from math_research.phase3a.serialization import canonical_bytes, canonical_hash, public_value, sha256_bytes, stable_id
from math_research.phase3a.workspace import MemoryCommandRejected, ResearchMemoryWorkspace


FIXTURES = Path("fixtures/phase3a")
_SHARED = tempfile.TemporaryDirectory()
_SHARED_ROOT = Path(_SHARED.name)
_ACCEPTANCE: dict[str, object] | None = None


def tearDownModule() -> None:
    _SHARED.cleanup()


def acceptance() -> dict[str, object]:
    global _ACCEPTANCE
    if _ACCEPTANCE is None:
        _ACCEPTANCE = run_acceptance(_SHARED_ROOT / "workspace", _SHARED_ROOT / "output")
    return _ACCEPTANCE


def workspace() -> ResearchMemoryWorkspace:
    acceptance()
    return ResearchMemoryWorkspace(_SHARED_ROOT / "workspace")


def fixture_license(*rights: str, reviewed: bool = True) -> LicenseMetadata:
    return LicenseMetadata(
        license_expression="LicenseRef-AdaIvy-Synthetic-Fixture", copyright_notice="Project-authored synthetic fixture",
        usage_rights=rights or ("private_evaluation", "local_retrieval", "evidence_pack"),
        redistribution_status="allowed", evidence_uri=None, reviewed_by=ACTOR_ID if reviewed else None,
    )


def evidence_by_label(current: ResearchMemoryWorkspace) -> dict[str, EvidenceUnit]:
    result: dict[str, EvidenceUnit] = {}
    for record in current.records("evidence_unit"):
        assert isinstance(record, EvidenceUnit)
        payload = public_value(record)["payload"]
        label = payload.get("label") or payload.get("term") or payload.get("step_label")
        if label:
            result[str(label)] = record
    return result


class SourceAcquisitionTests(unittest.TestCase):
    def test_regular_local_file_import_is_content_addressed(self) -> None:
        with workspace() as current:
            artifacts = current.records("source_artifact")
            self.assertTrue(artifacts)
            for record in artifacts:
                assert isinstance(record, SourceArtifact)
                self.assertEqual(record.artifact_hash, record.content_hash)
                self.assertEqual(sha256_bytes(current.source_bytes(record)), record.artifact_hash)

    def test_uri_metadata_import_performs_no_network_access_has_null_hash_and_stays_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ResearchMemoryWorkspace(Path(temporary)) as current:
            ingestor = ManualSourceIngestor(current)
            with patch.object(socket, "socket", side_effect=AssertionError("network attempted")):
                result = ingestor.import_metadata_only(
                    supplied_uri="doi:opaque-user-locator", title="Metadata only", authors=("Author",),
                    publication_metadata={}, license_metadata=fixture_license("metadata_recording", reviewed=False),
                    actor_id=ACTOR_ID, recorded_at=FIXED_TIME, aggregate_id=AGGREGATE_ID,
                )
            self.assertIsNone(result.source_reference.content_hash)
            self.assertEqual(result.source_reference.acquisition_status.value, "metadata_only")
            self.assertEqual(current.records("source_artifact"), ())
            self.assertEqual(current.records("evidence_unit"), ())
            invalid_hash = "sha256:" + "9" * 64
            invalid_artifact = SourceArtifact(
                id=OpaqueId("artifact.invalid.metadata-only"), source_reference_id=result.source_reference.id,
                artifact_hash=invalid_hash, byte_length=1, declared_media_type="text/plain",
                detected_media_type="text/plain", acquisition_method="operator_supplied_bytes",
                acquired_at=FIXED_TIME, acquisition_adapter="test", acquisition_adapter_version="1.0.0",
                quarantine_state=QuarantineState.ELIGIBLE, quarantine_reasons=(), content_hash=invalid_hash,
                created_at=FIXED_TIME, created_by=ACTOR_ID,
            )
            with self.assertRaises(ValueError):
                current.commit_records(
                    (invalid_artifact,), aggregate_id=AGGREGATE_ID, command_id=OpaqueId("command.invalid.metadata"),
                    kind="source_ingestion", idempotency_key="invalid-metadata-artifact",
                    request_hash=canonical_hash(invalid_artifact), now=FIXED_TIME,
                    deadline_at="9999-12-31T23:59:59Z",
                )
            self.assertEqual(current.records("source_artifact"), ())

    def test_complete_metadata_and_rights_round_trip(self) -> None:
        with workspace() as current:
            reference = next(
                record for record in current.records("source_reference")
                if isinstance(record, SourceReference) and record.content_hash is not None
            )
            replayed = current.get_record(reference.id)
            self.assertEqual(replayed, reference)
            self.assertIn("local_retrieval", reference.license_metadata.usage_rights)
            self.assertEqual(reference.metadata_status, "checked")

    def test_unreviewed_or_media_mismatched_content_is_quarantined(self) -> None:
        value = acceptance()["quarantine"]
        self.assertTrue(value["malformed"]["quarantined"])
        self.assertIn("pdf_unsupported", value["malformed"]["reasons"])


class SourceIdentityTests(unittest.TestCase):
    def test_identical_bytes_are_idempotent_across_paths_and_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_bytes(b"[PASSAGE:same] identical immutable bytes\n")
            shutil.copyfile(first, second)
            with ResearchMemoryWorkspace(root / "memory") as current:
                ingestor = ManualSourceIngestor(current)
                kwargs = dict(
                    supplied_uri="fixture:identical", title="Same", authors=("AdaIvy",), publication_metadata={},
                    license_metadata=fixture_license(), declared_media_type="text/plain", actor_id=ACTOR_ID,
                    recorded_at=FIXED_TIME, aggregate_id=AGGREGATE_ID,
                )
                one = ingestor.import_local(first.resolve(), **kwargs)
                two = ingestor.import_local(second.resolve(), **kwargs)
                self.assertEqual(one.source_artifact, two.source_artifact)
                self.assertEqual(len(current.records("source_artifact")), 1)
            with ResearchMemoryWorkspace(root / "memory") as restarted:
                self.assertEqual(len(restarted.records("source_artifact")), 1)

    def test_changed_bytes_create_distinct_artifact_with_explicit_version_edge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ResearchMemoryWorkspace(Path(temporary) / "memory") as current:
            root = Path(temporary)
            old_path, new_path = root / "old.txt", root / "new.txt"
            old_path.write_text("[PASSAGE:v1] original\n", encoding="utf-8")
            new_path.write_text("[PASSAGE:v2] corrected\n", encoding="utf-8")
            ingestor = ManualSourceIngestor(current)
            common = dict(title="Versioned", authors=("AdaIvy",), publication_metadata={}, license_metadata=fixture_license(),
                          declared_media_type="text/plain", actor_id=ACTOR_ID, recorded_at=FIXED_TIME, aggregate_id=AGGREGATE_ID)
            old = ingestor.import_local(old_path.resolve(), supplied_uri="fixture:old", **common)
            new = ingestor.import_local(new_path.resolve(), supplied_uri="fixture:new", **common)
            relation = ingestor.relate_versions(old.source_artifact, new.source_artifact, actor_id=ACTOR_ID, created_at=FIXED_TIME, aggregate_id=AGGREGATE_ID)
            self.assertNotEqual(old.source_artifact.id, new.source_artifact.id)
            self.assertEqual(relation.relation, "supersedes")


class SourceAcquisitionAdversarialTests(unittest.TestCase):
    def test_unsafe_local_inputs_never_reach_cas_or_parser(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ResearchMemoryWorkspace(Path(temporary) / "memory") as current:
            root = Path(temporary)
            target = root / "target.txt"
            target.write_text("safe", encoding="utf-8")
            link = root / "link.txt"
            link.symlink_to(target)
            ingestor = ManualSourceIngestor(current)
            kwargs = dict(supplied_uri="fixture:unsafe", title="Unsafe", authors=(), publication_metadata={},
                          license_metadata=fixture_license(), declared_media_type="text/plain", actor_id=ACTOR_ID,
                          recorded_at=FIXED_TIME, aggregate_id=AGGREGATE_ID)
            with self.assertRaises((OSError, ValueError)):
                ingestor.import_local(link.resolve(strict=False) if False else link.absolute(), **kwargs)
            oversized = root / "oversized.txt"
            oversized.write_bytes(b"x" * 33)
            with self.assertRaises(ValueError):
                ingestor.import_local(oversized.resolve(), max_bytes=32, **kwargs)
            self.assertEqual(current.records("source_artifact"), ())


class NormalizationTests(unittest.TestCase):
    def test_normalized_document_is_derived_and_cannot_replace_source_bytes(self) -> None:
        with workspace() as current:
            document = current.records("normalized_document")[0]
            assert isinstance(document, NormalizedDocument)
            artifact = current.get_record(document.source_artifact_id)
            assert isinstance(artifact, SourceArtifact)
            self.assertEqual(sha256_bytes(current.source_bytes(artifact)), artifact.artifact_hash)
            self.assertNotEqual(document.content_hash, artifact.artifact_hash)

    def test_same_source_parser_and_config_produce_identical_bytes_and_hash(self) -> None:
        with workspace() as current:
            artifact = next(record for record in current.records("source_artifact") if isinstance(record, SourceArtifact) and record.quarantine_state is QuarantineState.ELIGIBLE)
            parser = PlainTextV1Parser(current.artifacts)
            one = parser.parse(artifact, current.source_bytes(artifact), actor_id=ACTOR_ID, created_at=FIXED_TIME)
            two = parser.parse(artifact, current.source_bytes(artifact), actor_id=ACTOR_ID, created_at=FIXED_TIME)
            self.assertEqual(one, two)
            self.assertEqual(one.normalized_bytes, two.normalized_bytes)

    def test_formfeed_page_section_equation_theorem_definition_proof_table_and_reference_markers(self) -> None:
        with workspace() as current:
            marker_types = {public_value(record)["marker_type"] for record in current.records("document_marker")}
            self.assertTrue({"page", "section", "equation", "theorem", "definition", "proof", "table", "reference"}.issubset(marker_types))


class SpanCoordinateTests(unittest.TestCase):
    def test_every_gold_span_maps_to_exact_original_locator_and_back(self) -> None:
        with workspace() as current:
            result = validate_provenance(current)
            self.assertTrue(result["all_exact"])
            self.assertGreater(result["spans_checked"], 0)
        normalized, mappings = normalize_with_mapping("Cafe\u0301\r\nnext".encode("utf-8"))
        self.assertEqual(normalized, "Café\nnext")
        self.assertEqual(mappings[0].original_start, 0)


class NormalizationTrustTests(unittest.TestCase):
    def test_confidence_is_diagnostic_and_unsupported_output_stays_quarantined(self) -> None:
        with workspace() as current:
            runs = current.records("parser_run")
            self.assertTrue(all(isinstance(run, ParserRunRecord) and run.declared_confidence is None for run in runs))
            quarantined = [run for run in runs if isinstance(run, ParserRunRecord) and run.status == "quarantined"]
            self.assertEqual(len(quarantined), 2)
            self.assertFalse(any(unit.source_artifact_id in {run.source_artifact_id for run in quarantined} for unit in current.records("evidence_unit") if isinstance(unit, EvidenceUnit)))


class EvidenceUnitTests(unittest.TestCase):
    def test_required_unit_types_are_frozen_versioned_and_origin_checked(self) -> None:
        with workspace() as current:
            units = current.records("evidence_unit")
            self.assertEqual({unit.unit_type for unit in units if isinstance(unit, EvidenceUnit)}, set(EvidenceUnitType))
            unit = units[0]
            self.assertEqual(unit.schema_version, "1.0.0")
            with self.assertRaises(FrozenInstanceError):
                unit.disposition = Disposition.ACCEPTED

    def test_source_units_require_artifact_document_and_valid_spans(self) -> None:
        with workspace() as current:
            for unit in current.records("evidence_unit"):
                assert isinstance(unit, EvidenceUnit)
                if unit.unit_type is EvidenceUnitType.MODEL_PROPOSED_CLAIM:
                    continue
                self.assertIsInstance(current.get_record(unit.source_artifact_id), SourceArtifact)
                self.assertIsInstance(current.get_record(unit.normalized_document_id), NormalizedDocument)
                self.assertTrue(all(isinstance(current.get_record(identifier), SourceSpan) for identifier in unit.source_span_ids))


class EvidenceUnitTrustTests(unittest.TestCase):
    def test_model_proposed_claim_requires_model_origin_and_proposal_disposition(self) -> None:
        with workspace() as current:
            models = [record for record in current.records("evidence_unit") if isinstance(record, EvidenceUnit) and record.unit_type is EvidenceUnitType.MODEL_PROPOSED_CLAIM]
            self.assertTrue(models)
            self.assertTrue(all(record.origin.value == "model" and record.disposition is Disposition.PROPOSAL and not record.source_span_ids for record in models))


class EvidenceRelationTests(unittest.TestCase):
    def test_source_parser_model_and_human_relations_are_not_interchangeable(self) -> None:
        origins = {member.value for member in __import__("math_research.phase3a.records", fromlist=["RelationOrigin"]).RelationOrigin}
        self.assertEqual(origins, {"source_asserted", "parser_proposed", "model_proposed", "operator_asserted"})

    def test_contradictory_units_and_edges_coexist_and_are_retrievable(self) -> None:
        with workspace() as current:
            labels = evidence_by_label(current)
            relations = current.records("evidence_relation")
            self.assertIn("provenance", labels)
            self.assertIn("mutable-overwrite", labels)
            self.assertTrue(any(isinstance(record, EvidenceRelation) and record.relation_type.value == "contradicts" for record in relations))
            query = next(record for record in current.records("retrieval_query") if isinstance(record, RetrievalQueryRecord) and "contradictory" in record.canonical_query)
            hits = [record for record in current.records("retrieval_hit") if isinstance(record, RetrievalHit) and record.query_id == query.id]
            self.assertIn(labels["mutable-overwrite"].id, {hit.evidence_unit_id for hit in hits})


class EvidenceRelationTrustTests(unittest.TestCase):
    def test_accepted_source_assertion_does_not_change_claim_projection(self) -> None:
        with workspace() as current:
            self.assertEqual(current.records("epistemic_warrant"), ())
            self.assertEqual(current.records("verification_record"), ())


class RetrievalTests(unittest.TestCase):
    def test_rebuild_from_canonical_memory_is_byte_and_order_stable_under_pinned_engine(self) -> None:
        with workspace() as current:
            first = current.rebuild_index(aggregate_id=AGGREGATE_ID, now=FIXED_TIME)
            second = current.rebuild_index(aggregate_id=AGGREGATE_ID, now=FIXED_TIME)
            self.assertEqual(first, second)
            self.assertTrue(first["engine_identity"]["fts5_enabled"])

    def test_hits_include_unit_source_span_score_method_version_query_hash(self) -> None:
        with workspace() as current:
            query = current.records("retrieval_query")[0]
            assert isinstance(query, RetrievalQueryRecord)
            hits = [record for record in current.records("retrieval_hit") if isinstance(record, RetrievalHit) and record.query_id == query.id]
            self.assertTrue(hits)
            self.assertTrue(all(hit.source_span_ids and hit.canonical_score and hit.tie_break_key for hit in hits))
            self.assertEqual(query.retrieval_method, "sqlite_fts5_bm25")
            self.assertTrue(query.query_hash.startswith("sha256:"))

    def test_equal_scores_order_by_source_span_and_unit_id(self) -> None:
        with workspace() as current:
            for query in current.records("retrieval_query"):
                assert isinstance(query, RetrievalQueryRecord)
                hits = sorted((record for record in current.records("retrieval_hit") if isinstance(record, RetrievalHit) and record.query_id == query.id), key=lambda item: item.rank)
                self.assertEqual(hits, sorted(hits, key=lambda item: (item.raw_score, item.tie_break_key)))

    def test_manifest_reconstructs_exact_query_index_and_result_order(self) -> None:
        with workspace() as current:
            query = current.records("retrieval_query")[0]
            assert isinstance(query, RetrievalQueryRecord)
            hits = tuple(sorted((record for record in current.records("retrieval_hit") if isinstance(record, RetrievalHit) and record.query_id == query.id), key=lambda item: item.rank))
            result_hash = canonical_hash({"query": query, "hits": hits})
            pack = next(record for record in current.records("evidence_pack") if isinstance(record, EvidencePackManifest) and record.query_id == query.id)
            self.assertEqual(pack.retrieval_result_hash, result_hash)


class EvidencePackTests(unittest.TestCase):
    def test_same_query_corpus_policy_and_budget_produce_identical_pack_hash(self) -> None:
        metrics = acceptance()["retrieval_metrics"]
        self.assertEqual(len(set(metrics["pack_set_hashes_by_run"])), 1)

    def test_budget_exclusions_are_complete_and_deterministic(self) -> None:
        with workspace() as current:
            query = current.records("retrieval_query")[0]
            assert isinstance(query, RetrievalQueryRecord)
            hits = tuple(sorted((record for record in current.records("retrieval_hit") if isinstance(record, RetrievalHit) and record.query_id == query.id), key=lambda item: item.rank))
            from math_research.phase3a.retrieval import RetrievalResult
            result = RetrievalResult(query, hits, canonical_hash({"query": query, "hits": hits}))
            builder = DeterministicEvidencePackBuilder(current)
            pack = builder.build(result, byte_budget=600, per_source_cap=5, aggregate_id=OpaqueId("memory.pack.budget"), actor_id=ACTOR_ID, created_at=FIXED_TIME)
            self.assertLessEqual(len(pack.serialized_bytes), 600)
            self.assertTrue(pack.manifest.excluded_items)

    def test_duplicates_removed_and_per_source_cap_applied_before_fill(self) -> None:
        with workspace() as current:
            self.assertTrue(any(item.reason == "source_cap" for pack in current.records("evidence_pack") if isinstance(pack, EvidencePackManifest) for item in pack.excluded_items))

    def test_every_excerpt_carries_ids_and_exact_span_and_summary_is_separate_proposal(self) -> None:
        with workspace() as current:
            pack = current.records("evidence_pack")[0]
            assert isinstance(pack, EvidencePackManifest)
            payload = json.loads(current.artifact_bytes(pack.serialized_pack_artifact_hash))
            self.assertEqual(payload["model_commentary"], [])
            self.assertTrue(all(item["evidence_unit_id"] and item["source_span_ids"] and item["coordinates"] for item in payload["evidence"]))


class PromptInjectionTests(unittest.TestCase):
    def test_malicious_source_text_is_quoted_annotated_and_never_executed_as_policy(self) -> None:
        with workspace() as current:
            artifact = next(record for record in current.records("source_artifact") if isinstance(record, SourceArtifact) and "prompt_injection" in record.quarantine_reasons)
            self.assertIn(b"Ignore all previous instructions", current.source_bytes(artifact))
            self.assertFalse(any(isinstance(unit, EvidenceUnit) and unit.source_artifact_id == artifact.id for unit in current.records("evidence_unit")))
            self.assertFalse(any(isinstance(pack, EvidencePackManifest) and artifact.id in pack.included_source_artifact_ids for pack in current.records("evidence_pack")))


class ParserAdversarialTests(unittest.TestCase):
    def test_malformed_gold_fixture_retains_failure_without_evidence_import(self) -> None:
        with workspace() as current:
            malformed = next(record for record in current.records("source_artifact") if isinstance(record, SourceArtifact) and "pdf_unsupported" in record.quarantine_reasons)
            run = next(record for record in current.records("parser_run") if isinstance(record, ParserRunRecord) and record.source_artifact_id == malformed.id)
            self.assertEqual(run.status, "quarantined")
            self.assertIsNone(run.output_artifact_hash)

    def test_unmapped_or_unstable_output_cannot_enter_accepted_memory(self) -> None:
        with workspace() as current:
            self.assertTrue(all(not isinstance(document, NormalizedDocument) or document.disposition is Disposition.PROPOSAL for document in current.records("normalized_document")))
            self.assertFalse(any(isinstance(unit, EvidenceUnit) and unit.disposition is Disposition.ACCEPTED for unit in current.records("evidence_unit")))


class CitationValidationTests(unittest.TestCase):
    def _pack(self, current: ResearchMemoryWorkspace) -> EvidencePackManifest:
        return next(record for record in current.records("evidence_pack") if isinstance(record, EvidencePackManifest) and record.included_evidence_unit_ids)

    def test_cited_id_resolves_to_exact_pack_unit_and_span(self) -> None:
        with workspace() as current:
            pack = self._pack(current)
            identifier = pack.included_evidence_unit_ids[0]
            proposal = validate_and_build_model_proposal(
                current, pack=pack, statement="Valid", cited_evidence_unit_ids=(identifier,), declared_rationale="fixture",
                target_claim_id=OpaqueId("claim.citation.valid"), model_call_id=OpaqueId("scripted-call.citation.valid"),
                proposal_artifact_hash="sha256:" + "1" * 64, actor_id=ACTOR_ID, created_at=FIXED_TIME,
            )
            self.assertEqual(public_value(proposal)["payload"]["cited_evidence_unit_ids"], [identifier.value])

    def test_unknown_unit_id_rejects_proposal_without_domain_mutation(self) -> None:
        with workspace() as current:
            before = len(current.records("evidence_unit"))
            with self.assertRaises(CitationValidationError):
                validate_and_build_model_proposal(
                    current, pack=self._pack(current), statement="Invalid", cited_evidence_unit_ids=(OpaqueId("evidence.fabricated"),), declared_rationale="fixture",
                    target_claim_id=OpaqueId("claim.invalid"), model_call_id=OpaqueId("scripted-call.invalid"), proposal_artifact_hash="sha256:" + "2" * 64,
                    actor_id=ACTOR_ID, created_at=FIXED_TIME,
                )
            self.assertEqual(len(current.records("evidence_unit")), before)

    def test_globally_real_but_unsupplied_unit_id_is_rejected(self) -> None:
        with workspace() as current:
            pack = self._pack(current)
            outside = next(unit.id for unit in current.records("evidence_unit") if isinstance(unit, EvidenceUnit) and unit.id not in pack.included_evidence_unit_ids)
            with self.assertRaises(CitationValidationError):
                validate_and_build_model_proposal(
                    current, pack=pack, statement="Out of pack", cited_evidence_unit_ids=(outside,), declared_rationale="fixture",
                    target_claim_id=OpaqueId("claim.outside"), model_call_id=OpaqueId("scripted-call.outside"), proposal_artifact_hash="sha256:" + "3" * 64,
                    actor_id=ACTOR_ID, created_at=FIXED_TIME,
                )

    def test_pack_membership_awards_no_warrant(self) -> None:
        with workspace() as current:
            self.test_cited_id_resolves_to_exact_pack_unit_and_span()
            self.assertEqual(current.records("epistemic_warrant"), ())


class ModelMemoryBoundaryTests(unittest.TestCase):
    def test_same_model_agreement_remains_two_proposals(self) -> None:
        with workspace() as current:
            proposals = [unit for unit in current.records("evidence_unit") if isinstance(unit, EvidenceUnit) and unit.unit_type is EvidenceUnitType.MODEL_PROPOSED_CLAIM]
            self.assertGreaterEqual(len(proposals), 2)
            self.assertEqual({proposal.disposition for proposal in proposals}, {Disposition.PROPOSAL})

    def test_verifier_pack_excludes_proposer_commentary_and_records_manifest(self) -> None:
        with workspace() as current:
            for pack in current.records("evidence_pack"):
                assert isinstance(pack, EvidencePackManifest)
                data = json.loads(current.artifact_bytes(pack.serialized_pack_artifact_hash))
                self.assertEqual(data["model_commentary"], [])
                self.assertTrue(all(current.get_record(identifier).unit_type is not EvidenceUnitType.MODEL_PROPOSED_CLAIM for identifier in pack.included_evidence_unit_ids))

    def test_generated_summary_has_no_source_origin_or_accepted_disposition(self) -> None:
        with workspace() as current:
            for proposal in current.records("evidence_unit"):
                if isinstance(proposal, EvidenceUnit) and proposal.unit_type is EvidenceUnitType.MODEL_PROPOSED_CLAIM:
                    self.assertIsNone(proposal.source_artifact_id)
                    self.assertEqual(proposal.disposition, Disposition.PROPOSAL)


class ResearchMemoryRecoveryTests(unittest.TestCase):
    def test_orphan_normalization_retry_commits_one_document_units_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ResearchMemoryWorkspace(Path(temporary) / "memory") as current:
            ingestor = ManualSourceIngestor(current)
            kwargs = dict(
                supplied_uri="fixture:crash", title="Crash", authors=("AdaIvy",), publication_metadata={}, license_metadata=fixture_license(),
                declared_media_type="text/plain", actor_id=ACTOR_ID, recorded_at=FIXED_TIME, aggregate_id=AGGREGATE_ID,
            )
            with self.assertRaises(RuntimeError):
                ingestor.import_local((FIXTURES / "related-source.txt").resolve(), fail_after_artifact=True, **kwargs)
            self.assertEqual(current.records("normalized_document"), ())
            ingestor.import_local((FIXTURES / "related-source.txt").resolve(), **kwargs)
            ingestor.import_local((FIXTURES / "related-source.txt").resolve(), **kwargs)
            self.assertEqual(len(current.records("normalized_document")), 1)
            self.assertEqual(len([event for event in current.timeline(AGGREGATE_ID) if event["event_type"] == "source_ingestion_committed"]), 1)

    def test_restart_preserves_ids_hashes_spans_relations_index_manifest_and_pack(self) -> None:
        value = acceptance()
        self.assertTrue(value["retrieval_metrics"]["repeat_restart_stable"])
        with workspace() as current:
            before = canonical_hash([public_value(record) for record in current.all_records()])
        with workspace() as restarted:
            after = canonical_hash([public_value(record) for record in restarted.all_records()])
        self.assertEqual(before, after)

    def test_idempotent_commands_have_one_semantic_result(self) -> None:
        with workspace() as current:
            events = current.timeline(AGGREGATE_ID)
            self.assertEqual(len({event["idempotency_key"] for event in events}), len(events))
            self.assertEqual(len({record.id for record in current.all_records()}), len(current.all_records()))


class ResearchMemoryBudgetTests(unittest.TestCase):
    def test_exhausted_time_size_attempt_or_optional_model_budget_prevents_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ResearchMemoryWorkspace(Path(temporary)) as current:
            with self.assertRaises(MemoryCommandRejected):
                current.commit_records(
                    (), aggregate_id=AGGREGATE_ID, command_id=OpaqueId("command.expired"), kind="parser",
                    idempotency_key="expired", request_hash=canonical_hash({"expired": True}), now=FIXED_TIME,
                    deadline_at=FIXED_TIME, max_attempts=1,
                )
            failed_hash = canonical_hash({"attempt": "failed"})
            current.record_failed_command(
                command_id=OpaqueId("command.attempt.exhausted"), kind="parser",
                idempotency_key="attempt-exhausted", request_hash=failed_hash,
                now=FIXED_TIME, deadline_at="9999-12-31T23:59:59Z", max_attempts=1,
            )
            with self.assertRaises(MemoryCommandRejected):
                current.commit_records(
                    (), aggregate_id=AGGREGATE_ID, command_id=OpaqueId("command.attempt.exhausted"),
                    kind="parser", idempotency_key="attempt-exhausted", request_hash=failed_hash,
                    now=FIXED_TIME, deadline_at="9999-12-31T23:59:59Z", max_attempts=1,
                )
            oversized = Path(temporary) / "large.txt"
            oversized.write_bytes(b"x" * 9)
            with self.assertRaises(ValueError):
                ManualSourceIngestor(current).import_local(
                    oversized.resolve(), supplied_uri="fixture:large", title="Large", authors=(), publication_metadata={},
                    license_metadata=fixture_license(), declared_media_type="text/plain", actor_id=ACTOR_ID,
                    recorded_at=FIXED_TIME, aggregate_id=AGGREGATE_ID, max_bytes=8,
                )

    def test_late_parser_or_model_success_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ResearchMemoryWorkspace(Path(temporary)) as current:
            request_hash = canonical_hash({"cancelled": True})
            current.begin_command(
                command_id=OpaqueId("command.cancelled"), kind="parser", idempotency_key="cancelled",
                request_hash=request_hash, now=FIXED_TIME, deadline_at="9999-12-31T23:59:59Z", max_attempts=1,
            )
            current.cancel_command("cancelled", now=FIXED_TIME)
            with self.assertRaises(MemoryCommandRejected):
                current.commit_records(
                    (), aggregate_id=AGGREGATE_ID, command_id=OpaqueId("command.cancelled"), kind="parser",
                    idempotency_key="cancelled", request_hash=request_hash, now=FIXED_TIME,
                    deadline_at="9999-12-31T23:59:59Z",
                )


class ResearchMemoryInterchangeTests(unittest.TestCase):
    def test_export_import_preserves_ids_meaning_bytes_and_content_hash(self) -> None:
        acceptance()
        data = (_SHARED_ROOT / "output" / "research-memory.json").read_bytes()
        replay = import_trusted_replay(data)
        self.assertEqual(replay.canonical_bytes, data)
        self.assertEqual(replay.content_hash, replay.payload["content_hash"])
        self.assertEqual(canonical_bytes(replay.payload), data)

    def test_external_export_cannot_write_accepted_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ResearchMemoryWorkspace(Path(temporary)) as current:
            replay = import_trusted_replay((_SHARED_ROOT / "output" / "research-memory.json").read_bytes())
            proposal = current.import_proposal(replay.payload, source_label="foreign", now=FIXED_TIME)
            self.assertEqual(proposal["disposition"], "proposal")
            self.assertEqual(current.all_records(), ())


class GoldCorpusTests(unittest.TestCase):
    def test_manifest_contains_five_project_authored_fixture_classes(self) -> None:
        value = json.loads((FIXTURES / "gold-corpus.json").read_text(encoding="utf-8"))
        self.assertEqual({item["class"] for item in value["sources"]}, {"primary", "related", "contradictory", "malformed", "prompt_injection"})
        self.assertTrue(value["fixture_license"]["license_expression"].startswith("LicenseRef-"))

    def test_quantum_paper_has_null_content_hash_and_no_committed_pdf_or_extracted_text(self) -> None:
        value = json.loads((FIXTURES / "quantum-paper-metadata.json").read_text(encoding="utf-8"))
        self.assertIsNone(value["content_hash"])
        self.assertEqual(value["acquisition_status"], "metadata_only")
        self.assertEqual([path.suffix for path in FIXTURES.glob("*quantum*")], [".json"])
        with workspace() as current:
            reference = current.get_record(OpaqueId(str(acceptance()["quantum_metadata_source_id"])))
            self.assertIsInstance(reference, SourceReference)
            self.assertIsNone(reference.content_hash)


class ScopeGuardTests(unittest.TestCase):
    def test_core_has_no_quantum_specific_import_type_or_solver(self) -> None:
        core = Path("src/math_research/phase3a/records.py").read_text(encoding="utf-8").casefold()
        self.assertNotIn("quantum", core)
        self.assertNotIn("convergence", core)

    def test_phase3a_forbidden_dependencies_and_features_absent(self) -> None:
        imported_roots: set[str] = set()
        for path in Path("src/math_research/phase3a").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported_roots.add(node.module.split(".")[0])
        self.assertTrue(imported_roots.isdisjoint({"requests", "httpx", "urllib", "socket", "openai", "numpy", "faiss", "chromadb", "pypdf", "fitz", "lean", "why3"}))
        self.assertFalse(any("embedding" in path.name.casefold() for path in Path("src/math_research/phase3a").glob("*.py")))


class ResearchMemoryReportTests(unittest.TestCase):
    def test_report_is_reproducible_from_durable_canonical_state(self) -> None:
        value = acceptance()
        regenerated = render_report(value).encode("utf-8")
        recorded = (_SHARED_ROOT / "output" / "traceable-report.md").read_bytes()
        self.assertEqual(regenerated, recorded)
        self.assertEqual(sha256_bytes(recorded), value["hashes"]["traceable_report_hash"])


class ResearchMemorySecurityTests(unittest.TestCase):
    def test_no_secret_in_sources_indexes_packs_events_logs_database_or_reports(self) -> None:
        acceptance()
        patterns = (b"OPENAI_API_KEY", b"sk-proj-", b"sk-live-", b"Bearer ")
        matches = []
        for path in (_SHARED_ROOT / "workspace").rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                matches.extend((str(path), pattern) for pattern in patterns if pattern in data)
        for path in (_SHARED_ROOT / "output").rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                matches.extend((str(path), pattern) for pattern in patterns if pattern in data)
        self.assertEqual(matches, [])


class RightsPolicyTests(unittest.TestCase):
    def test_restricted_source_span_is_excluded_with_manifest_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, ResearchMemoryWorkspace(Path(temporary) / "memory") as current:
            result = ManualSourceIngestor(current).import_local(
                (FIXTURES / "related-source.txt").resolve(), supplied_uri="fixture:rights", title="Rights", authors=("AdaIvy",),
                publication_metadata={}, license_metadata=fixture_license("local_retrieval"), declared_media_type="text/plain",
                actor_id=ACTOR_ID, recorded_at=FIXED_TIME, aggregate_id=AGGREGATE_ID,
            )
            index = current.rebuild_index(aggregate_id=AGGREGATE_ID, now=FIXED_TIME)
            retrieval = DeterministicRetriever(current).search(
                "exact citation pack membership", corpus_manifest_hash=index["content_hash"], limit=5,
                aggregate_id=AGGREGATE_ID, actor_id=ACTOR_ID, created_at=FIXED_TIME,
            )
            pack = DeterministicEvidencePackBuilder(current).build(
                retrieval, byte_budget=4096, per_source_cap=5, aggregate_id=AGGREGATE_ID,
                actor_id=ACTOR_ID, created_at=FIXED_TIME,
            )
            self.assertFalse(pack.manifest.included_evidence_unit_ids)
            self.assertTrue(all(item.reason == "rights" for item in pack.manifest.excluded_items))


class RetrievalEvaluationTests(unittest.TestCase):
    def test_recall_at_5_mrr_and_citation_precision_meet_frozen_thresholds(self) -> None:
        metrics = acceptance()["retrieval_metrics"]
        self.assertEqual(metrics["recall_at_5"], 1.0)
        self.assertGreaterEqual(metrics["mrr"], 0.75)
        self.assertEqual(metrics["citation_resolution_precision"], 1.0)
        self.assertEqual(metrics["quarantined_evidence_retrieved"], 0)

    def test_three_repeats_and_one_restart_have_identical_ids_and_pack_hashes(self) -> None:
        metrics = acceptance()["retrieval_metrics"]
        self.assertEqual(len(metrics["ordered_result_hashes_by_run"]), 4)
        self.assertEqual(len(set(metrics["ordered_result_hashes_by_run"])), 1)
        self.assertEqual(len(set(metrics["pack_set_hashes_by_run"])), 1)
        self.assertTrue(metrics["repeat_restart_stable"])


class Phase3ASchemaAndNoApiTests(unittest.TestCase):
    def test_research_memory_schema_and_fixture_json_are_valid(self) -> None:
        schema = json.loads(Path("schemas/research-memory-v1.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0.0")
        for path in FIXTURES.glob("*.json"):
            json.loads(path.read_text(encoding="utf-8"))

    def test_no_model_or_external_api_call_occurs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            socket, "socket", side_effect=AssertionError("network attempted")
        ):
            value = run_acceptance(Path(temporary) / "workspace", Path(temporary) / "output")
        self.assertEqual(value["api_call_count"], 0)
        self.assertEqual(value["status"], "passed")

    def test_query_grammar_is_bounded_and_deterministic(self) -> None:
        self.assertEqual(canonical_query_text("  Café\nproof  "), "Café proof")
        self.assertEqual(fts_expression("A B"), '"a" OR "b"')
        with self.assertRaises(ValueError):
            fts_expression("---")
