"""Reproducible synthetic Phase 3A acceptance demonstration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..domain.entities import OpaqueId
from . import MEMORY_SCHEMA_VERSION
from .acquisition import ManualSourceIngestor
from .interchange import build_export, import_trusted_replay, validate_provenance, write_export
from .records import (
    Disposition,
    EvidenceRelation,
    EvidenceUnit,
    LicenseMetadata,
    RelationOrigin,
    RelationType,
    SourceArtifact,
)
from .reporting import render_report
from .retrieval import DeterministicEvidencePackBuilder, DeterministicRetriever, validate_and_build_model_proposal
from .serialization import ZERO_HASH, canonical_bytes, canonical_hash, finalize_content_hash, public_value, sha256_bytes, stable_id
from .workspace import ResearchMemoryWorkspace

FIXED_TIME = "2026-08-19T00:00:00Z"
ACTOR_ID = OpaqueId("actor.phase3a.operator")
AGGREGATE_ID = OpaqueId("memory.phase3a.synthetic.v1")


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _fixture_manifest() -> tuple[Path, dict[str, Any]]:
    directory = _root() / "fixtures" / "phase3a"
    return directory, json.loads((directory / "gold-corpus.json").read_text(encoding="utf-8"))


def _license(manifest: dict[str, Any]) -> LicenseMetadata:
    value = manifest["fixture_license"]
    return LicenseMetadata(
        license_expression=value["license_expression"], copyright_notice=value["copyright_notice"],
        usage_rights=tuple(value["usage_rights"]), redistribution_status=value["redistribution_status"],
        evidence_uri=None, reviewed_by=ACTOR_ID,
    )


def _labels(workspace: ResearchMemoryWorkspace) -> dict[str, EvidenceUnit]:
    result: dict[str, EvidenceUnit] = {}
    for record in workspace.records("evidence_unit"):
        assert isinstance(record, EvidenceUnit)
        payload = public_value(record)["payload"]
        label = payload.get("label") or payload.get("term") or payload.get("step_label")
        if label:
            result[str(label)] = record
    return result


def _append_contradiction(workspace: ResearchMemoryWorkspace) -> EvidenceRelation:
    labels = _labels(workspace)
    relation = EvidenceRelation(
        id=stable_id("relation", {"source": labels["mutable-overwrite"].id.value, "target": labels["provenance"].id.value, "type": "contradicts"}),
        source_unit_id=labels["mutable-overwrite"].id, target_unit_id=labels["provenance"].id,
        relation_type=RelationType.CONTRADICTS, assertion_origin=RelationOrigin.OPERATOR_ASSERTED,
        assertion_span_ids=labels["mutable-overwrite"].source_span_ids,
        extraction_or_actor_id=ACTOR_ID.value, disposition=Disposition.PROPOSAL, review_record_ids=(),
        content_hash=ZERO_HASH, created_at=FIXED_TIME, created_by=ACTOR_ID,
    )
    relation = finalize_content_hash(relation)  # type: ignore[assignment]
    request_hash = canonical_hash({"operation": "relation", "record": relation})
    workspace.commit_records(
        (relation,), aggregate_id=AGGREGATE_ID, command_id=stable_id("command", request_hash), kind="evidence_relation",
        idempotency_key=f"relation:{relation.id.value}", request_hash=request_hash, now=FIXED_TIME,
        deadline_at="9999-12-31T23:59:59Z",
    )
    return relation


def _run_queries(
    workspace: ResearchMemoryWorkspace,
    manifest: dict[str, Any],
    corpus_hash: str,
) -> tuple[list[list[str]], list[list[str]], list[object], list[object]]:
    retriever = DeterministicRetriever(workspace)
    builder = DeterministicEvidencePackBuilder(workspace)
    ordered_ids: list[list[str]] = []
    pack_hashes: list[list[str]] = []
    results: list[object] = []
    packs: list[object] = []
    one_run_ids: list[str] = []
    one_run_packs: list[str] = []
    for query in manifest["queries"]:
        result = retriever.search(
            query["query"], corpus_manifest_hash=corpus_hash, limit=5,
            aggregate_id=AGGREGATE_ID, actor_id=ACTOR_ID, created_at=FIXED_TIME,
        )
        pack = builder.build(
            result, byte_budget=65536, per_source_cap=3,
            aggregate_id=AGGREGATE_ID, actor_id=ACTOR_ID, created_at=FIXED_TIME,
        )
        one_run_ids.append(canonical_hash([hit.evidence_unit_id.value for hit in result.hits]))
        one_run_packs.append(pack.manifest.content_hash)
        results.append(result)
        packs.append(pack)
    ordered_ids.append(one_run_ids)
    pack_hashes.append(one_run_packs)
    return ordered_ids, pack_hashes, results, packs


def run_acceptance(workspace_root: Path, output_dir: Path) -> dict[str, Any]:
    fixture_dir, manifest = _fixture_manifest()
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace = ResearchMemoryWorkspace(workspace_root)
    ingestor = ManualSourceIngestor(workspace)
    license_metadata = _license(manifest)
    quarantine: dict[str, object] = {}
    source_results = []
    for source in manifest["sources"]:
        result = ingestor.import_local(
            (fixture_dir / source["path"]).resolve(), supplied_uri=f"fixture:{source['class']}",
            title=f"Phase 3A synthetic {source['class']} source", authors=("AdaIvy contributors",),
            publication_metadata={"fixture_class": source["class"], "project_authored": True},
            license_metadata=license_metadata, declared_media_type=source["declared_media_type"],
            actor_id=ACTOR_ID, recorded_at=FIXED_TIME, aggregate_id=AGGREGATE_ID,
        )
        source_results.append(result)
        quarantine[source["class"]] = {
            "quarantined": result.quarantined, "reasons": list(result.quarantine_reasons),
            "artifact_id": result.source_artifact.id.value if result.source_artifact else None,
        }
    quantum = json.loads((fixture_dir / "quantum-paper-metadata.json").read_text(encoding="utf-8"))
    quantum_license = quantum["license_metadata"]
    quantum_result = ingestor.import_metadata_only(
        supplied_uri=quantum["supplied_uri"], title=quantum["title"], authors=tuple(quantum["authors"]),
        publication_metadata=quantum["publication_metadata"],
        license_metadata=LicenseMetadata(
            license_expression=quantum_license["license_expression"], copyright_notice=quantum_license["copyright_notice"],
            usage_rights=tuple(quantum_license["usage_rights"]), redistribution_status=quantum_license["redistribution_status"],
            evidence_uri=quantum_license["evidence_uri"], reviewed_by=None,
        ), actor_id=ACTOR_ID, recorded_at=FIXED_TIME, aggregate_id=AGGREGATE_ID,
    )
    _append_contradiction(workspace)
    index_manifest = workspace.rebuild_index(aggregate_id=AGGREGATE_ID, now=FIXED_TIME)
    all_order_hashes: list[list[str]] = []
    all_pack_hashes: list[list[str]] = []
    final_results: list[Any] = []
    final_packs: list[Any] = []
    for _ in range(3):
        orders, packs, final_results, final_packs = _run_queries(workspace, manifest, index_manifest["content_hash"])
        all_order_hashes.extend(orders)
        all_pack_hashes.extend(packs)
    workspace.close()

    workspace = ResearchMemoryWorkspace(workspace_root)
    restart_index = workspace.rebuild_index(aggregate_id=AGGREGATE_ID, now=FIXED_TIME)
    restart_orders, restart_packs, final_results, final_packs = _run_queries(
        workspace, manifest, restart_index["content_hash"]
    )
    all_order_hashes.extend(restart_orders)
    all_pack_hashes.extend(restart_packs)

    labels = _labels(workspace)
    reciprocal_ranks: list[float] = []
    recalled = 0
    citation_successes = 0
    for query, result, pack in zip(manifest["queries"], final_results, final_packs):
        expected = labels[query["relevant_label"]].id
        ids = [hit.evidence_unit_id for hit in result.hits]
        if expected in ids:
            recalled += 1
            reciprocal_ranks.append(1.0 / (ids.index(expected) + 1))
        else:
            reciprocal_ranks.append(0.0)
        proposal_data = canonical_bytes(
            {"statement": f"Scripted proposal citing {expected.value}", "citations": [expected.value]}
        )
        proposal_artifact = workspace.artifacts.put(proposal_data, media_type="application/json")
        proposal = validate_and_build_model_proposal(
            workspace, pack=pack.manifest, statement=f"Scripted proposal for {query['id']}",
            cited_evidence_unit_ids=(expected,), declared_rationale="Static value fixture; no model call.",
            target_claim_id=OpaqueId(f"claim.{query['id']}"), model_call_id=OpaqueId(f"scripted-call.{query['id']}"),
            proposal_artifact_hash=proposal_artifact.content_hash, actor_id=ACTOR_ID, created_at=FIXED_TIME,
        )
        request_hash = canonical_hash({"operation": "scripted_proposal", "record": proposal})
        workspace.commit_records(
            (proposal,), aggregate_id=AGGREGATE_ID, command_id=stable_id("command", request_hash), kind="model_shaped_proposal",
            idempotency_key=f"scripted-proposal:{proposal.id.value}", request_hash=request_hash, now=FIXED_TIME,
            deadline_at="9999-12-31T23:59:59Z",
        )
        citation_successes += 1

    source_artifacts = [record for record in workspace.records("source_artifact") if isinstance(record, SourceArtifact)]
    quarantined_ids = {record.id for record in source_artifacts if record.quarantine_state.value == "quarantined"}
    quarantined_retrieved = sum(
        hit.source_artifact_id in quarantined_ids for result in final_results for hit in result.hits
    )
    metrics = {
        "recall_at_5": recalled / len(manifest["queries"]),
        "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
        "citation_resolution_precision": citation_successes / len(manifest["queries"]),
        "quarantined_evidence_retrieved": quarantined_retrieved,
        "repeat_restart_stable": len({canonical_hash(value) for value in all_order_hashes}) == 1
        and len({canonical_hash(value) for value in all_pack_hashes}) == 1,
        "ordered_result_hashes_by_run": [canonical_hash(value) for value in all_order_hashes],
        "pack_set_hashes_by_run": [canonical_hash(value) for value in all_pack_hashes],
    }
    thresholds = manifest["thresholds"]
    passed = (
        metrics["recall_at_5"] == thresholds["recall_at_5"]
        and metrics["mrr"] >= thresholds["mrr_minimum"]
        and metrics["citation_resolution_precision"] == thresholds["citation_resolution_precision"]
        and metrics["quarantined_evidence_retrieved"] == thresholds["quarantined_evidence_retrieved"]
        and metrics["repeat_restart_stable"]
    )
    provenance = validate_provenance(workspace)
    memory_export = build_export(
        workspace, export_id=OpaqueId("memory-export.phase3a.synthetic.v1"), aggregate_id=AGGREGATE_ID,
        created_at=FIXED_TIME, created_by=ACTOR_ID,
    )
    export_path = output_dir / "research-memory.json"
    write_export(memory_export, export_path)
    replay = import_trusted_replay(export_path.read_bytes())
    source_hash = canonical_hash(
        [{"id": result.source_reference.id.value, "content_hash": result.source_reference.content_hash} for result in source_results]
        + [{"id": quantum_result.source_reference.id.value, "content_hash": None}]
    )
    evidence_hash = canonical_hash([public_value(record) for record in workspace.records("evidence_unit")])
    retrieval_hash = canonical_hash(
        [[hit.evidence_unit_id.value for hit in result.hits] for result in final_results]
    )
    pack_hash = canonical_hash([pack.manifest.content_hash for pack in final_packs])
    evidence: dict[str, Any] = {
        "schema_version": MEMORY_SCHEMA_VERSION, "aggregate_id": AGGREGATE_ID.value,
        "status": "passed" if passed else "failed", "api_call_count": 0,
        "retrieval_metrics": metrics, "quarantine": quarantine,
        "licensing": {
            "synthetic_fixture_license": manifest["fixture_license"],
            "quantum_paper": "metadata_only_rights_unresolved_no_bytes",
        },
        "provenance_round_trip": {**provenance, "export_hash_preserved": replay.content_hash == memory_export["content_hash"]},
        "record_counts": {
            kind: len(workspace.records(kind)) for kind in (
                "source_reference", "source_artifact", "parser_run", "normalized_document", "source_span",
                "document_marker", "evidence_unit", "evidence_relation", "retrieval_query", "retrieval_hit", "evidence_pack",
            )
        },
        "hashes": {
            "source_manifest_hash": source_hash, "evidence_manifest_hash": evidence_hash,
            "corpus_index_manifest_hash": index_manifest["content_hash"], "retrieval_manifest_hash": retrieval_hash,
            "evidence_pack_manifest_hash": pack_hash, "research_memory_export_hash": memory_export["content_hash"],
            "event_replay_hash": workspace.event_replay_hash(AGGREGATE_ID),
        },
        "quantum_metadata_source_id": quantum_result.source_reference.id.value,
        "quantum_metadata_content_hash": quantum_result.source_reference.content_hash,
        "migrations": list(workspace.migration_versions), "engine_identity": workspace.engine_identity,
    }
    report = render_report(evidence)
    report_path = output_dir / "traceable-report.md"
    report_path.write_text(report, encoding="utf-8")
    evidence["hashes"]["traceable_report_hash"] = sha256_bytes(report.encode("utf-8"))
    evidence["hashes"]["acceptance_evidence_preimage_hash"] = canonical_hash(evidence)
    acceptance_path = output_dir / "acceptance.json"
    acceptance_path.write_bytes(canonical_bytes(evidence))
    workspace.close()
    return evidence
