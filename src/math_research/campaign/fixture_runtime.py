"""Deterministic offline end-to-end campaign used by the acceptance gate.

It exercises the same profile-bound embedding boundary, unified budget,
persistent corpus, retrieval, checkpoint, experiment, verification and report
records as a live campaign while deliberately making no network/model/container
call.  Its artifacts state fixture provenance and create no warrant.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..corpus_retrieval import (
    build_projection, embed_query, load_projection, retrieve_evidence,
)
from ..corpus_service.dataroot import initialize_data_root, read_object
from ..corpus_service.generation import require_active_generation
from ..corpus_service.policy import load_policy
from ..corpus_service.ports import DirectoryArchiveSource
from ..corpus_service.serialization import canonical_bytes, sha256_bytes
from ..corpus_service.service import ingest_tranche
from ..corpus_service.snapshot import load_tranche_config
from ..corpus_service.spans import verify_spans, verify_spans_against_source
from ..domain.entities import OpaqueId
from ..embedding.gateways import ScriptedEmbeddingGateway
from ..embedding.partition import PartitionKey
from ..phase2.pricing import create_pricing_snapshot
from .budget import (
    BudgetCapability, CampaignBudget, CampaignBudgetLedger, ChargeEvent, SubBudget,
)
from .credentials import CredentialProfile, select_credential_profile
from .end_to_end import EndToEndCampaignRunner, RuntimeAction
from .records import ActionType, RecordStatus, UsageSource, canonical_hash, public_value
from .routing import ProfileBoundEmbeddingGateway


PROCESSOR_ID = "processor.openai.synthetic-fixture-embedding"
EMBEDDING_MODEL = "synthetic-fixture-embedding-v1"
PROFILE_ID = "adaivy"


def _write_once(path: Path, value: Any) -> None:
    rendered = canonical_bytes(value) + b"\n"
    if path.exists():
        if path.read_bytes() != rendered:
            raise ValueError(f"immutable runtime record differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(rendered)
    temporary.replace(path)


def _write_bytes_once(path: Path, value: bytes) -> None:
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"immutable runtime bytes differ: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(value)
    temporary.replace(path)


def _charge_from_value(value: dict[str, Any]) -> ChargeEvent:
    return ChargeEvent(
        sequence=value["sequence"], campaign_id=value["campaign_id"],
        capability=BudgetCapability(value["capability"]),
        credential_profile_id=value["credential_profile_id"], purpose=value["purpose"],
        status=RecordStatus(value["status"]), request_hash=value["request_hash"],
        usage_source=UsageSource(value["usage_source"]), requests=value["requests"],
        input_tokens=value["input_tokens"], output_tokens=value["output_tokens"],
        cost_microusd=value["cost_microusd"], bytes_transferred=value["bytes_transferred"],
        documents=value["documents"], failure_classification=value["failure_classification"],
        rate_limit_retry_after_milliseconds=value["rate_limit_retry_after_milliseconds"],
        recorded_at=value["recorded_at"], schema_version=value["schema_version"],
        record_type=value["record_type"], content_hash=value["content_hash"],
        operational_hash=value["operational_hash"],
    )


def run_fixture_campaign(
    campaign_root: Path, *, data_root: Path, campaign_id: str,
    recorded_at: str, repository_root: Path, problem_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Initialize and run/resume the complete offline fixture in one call."""

    campaign_root.mkdir(parents=True, exist_ok=True)
    problem_path = campaign_root / "problem.bin"
    if problem_path.exists():
        frozen_problem = problem_path.read_bytes()
        if problem_bytes is not None and problem_bytes != frozen_problem:
            raise ValueError("campaign target is already frozen to different bytes")
    else:
        frozen_problem = problem_bytes or b"Offline fixture: retrieve exact synthetic passages.\n"
        if not frozen_problem:
            raise ValueError("campaign problem must be nonempty")
        _write_bytes_once(problem_path, frozen_problem)
    target = {
        "schema_version": "adaivy.end-to-end-target.v1",
        "campaign_id": campaign_id,
        "problem_sha256": sha256_bytes(frozen_problem),
        "byte_count": len(frozen_problem),
        "frozen_at": recorded_at,
    }
    target["content_hash"] = canonical_hash(target)
    _write_once(campaign_root / "campaign-target.json", target)
    _write_once(campaign_root / "end-to-end-runtime-config.json", {
        "schema_version": "adaivy.end-to-end-runtime-config.v1",
        "mode": "fixture",
        "campaign_id": campaign_id,
        "recorded_at": recorded_at,
        "data_root": str(data_root.resolve()),
        "repository_root": str(repository_root.resolve()),
        "target_hash": target["content_hash"],
    })
    initialize_data_root(
        data_root, data_root_id="dataroot." + canonical_hash(campaign_id).removeprefix("sha256:")[:24],
        initialized_at=recorded_at,
    )
    profile = CredentialProfile(
        profile_id=PROFILE_ID, provider="openai", model_identifier="fixture-lead-v1",
        embedding_model_identifier=EMBEDDING_MODEL, endpoint_settings=(),
        credential_source="offline-fixture",
    ).finalized()
    profile, selection = select_credential_profile(
        {PROFILE_ID: profile}, PROFILE_ID, campaign_id=campaign_id,
        selected_at=recorded_at,
    )
    embedding_pricing = create_pricing_snapshot(
        snapshot_id=OpaqueId("pricing.fixture.embedding.v1"), provider="openai",
        model_identifier=EMBEDDING_MODEL, source="offline fixture; no charge",
        captured_at=recorded_at, currency="USD",
        input_microusd_per_million_tokens=0,
        output_microusd_per_million_tokens=0,
    )
    model_pricing = create_pricing_snapshot(
        snapshot_id=OpaqueId("pricing.fixture.model.v1"), provider="openai",
        model_identifier="fixture-lead-v1", source="offline fixture; no charge",
        captured_at=recorded_at, currency="USD",
        input_microusd_per_million_tokens=0,
        output_microusd_per_million_tokens=0,
    )
    generous = SubBudget(
        max_requests=64, max_input_tokens=1_000_000, max_output_tokens=1_000_000,
        max_cost_microusd=0, max_bytes=100_000_000, max_documents=2_048,
    )
    budget = CampaignBudget(
        campaign_id=campaign_id, pricing_snapshot_hash=model_pricing.content_hash,
        embedding_pricing_snapshot_hash=embedding_pricing.content_hash,
        max_total_cost_microusd=0, max_wall_milliseconds=3_600_000,
        model=generous, embedding=generous, network=generous, tool=generous,
        storage=generous,
    ).finalized()
    _write_once(campaign_root / "credential-profile.json", public_value(profile))
    _write_once(campaign_root / "credential-selection.json", public_value(selection))
    _write_once(campaign_root / "campaign-budget.json", public_value(budget))

    charges_dir = campaign_root / "budget-charges"
    prior_events = []
    if charges_dir.exists():
        for path in sorted(charges_dir.glob("*.json")):
            prior_events.append(_charge_from_value(json.loads(path.read_text())))

    def persist_charge(event: ChargeEvent) -> None:
        _write_once(
            charges_dir / f"{event.sequence:06d}.json", public_value(event),
        )

    ledger = CampaignBudgetLedger(
        budget, recorded_at=lambda: recorded_at, initial_events=prior_events,
        event_sink=persist_charge,
    )
    query_text = "synthetic fixture exact span"
    query_id = "query." + sha256_bytes(query_text.encode("utf-8")).removeprefix("sha256:")[:24]
    scripted = ScriptedEmbeddingGateway(
        provider="openai", model_identifier=EMBEDDING_MODEL,
        vectors={
            "doc-open-alpha": (1.0, 0.0, 0.0),
            "doc-open-beta": (0.0, 1.0, 0.0),
            query_id: (1.0, 0.0, 0.0),
        },
    )
    gateway = ProfileBoundEmbeddingGateway(
        profile=profile, selection=selection, gateway=scripted,
        pricing=embedding_pricing, ledger=ledger,
        purpose="campaign_literature_embedding",
    )
    fixture_root = repository_root / "fixtures" / "corpus-service"
    checkpoints = EndToEndCampaignRunner(
        campaign_root, campaign_id=campaign_id, recorded_at=recorded_at,
        max_actions=16,
    ).checkpoints

    def result(sequence: int) -> dict[str, Any]:
        terminal = checkpoints.load(sequence, "terminal")
        if terminal is None or terminal["status"] != "completed":
            raise ValueError(f"required action {sequence} is not complete")
        return terminal["result"]

    def search(_key: str) -> dict[str, Any]:
        return {
            "provider": "fixture", "network_requests": 0,
            "candidate_ids": ["doc-open-alpha", "doc-open-beta"],
            "status": "untrusted_inspiration_candidate",
        }

    def follow(_key: str) -> dict[str, Any]:
        return {
            "followed_candidate_ids": result(1)["candidate_ids"],
            "max_depth": 1, "allowlisted_origin": "local-fixture",
            "network_requests": 0,
        }

    def acquire(_key: str) -> dict[str, Any]:
        report = ingest_tranche(
            data_root,
            policy=load_policy((fixture_root / "fixture-source-rights-policy-v1.json").read_bytes()),
            archive=DirectoryArchiveSource(fixture_root / "fixture-snapshot-archive-v1"),
            tranche_config=load_tranche_config(
                (fixture_root / "fixture-tranche-config-v1.json").read_bytes()
            ),
            run_id=campaign_id + ".corpus", recorded_at=recorded_at,
        )
        return {"generation_id": report["generation_id"], "report_hash": report["content_hash"]}

    def parse(_key: str) -> dict[str, Any]:
        generation = require_active_generation(data_root, result(3)["generation_id"])
        verified = 0
        for entry in generation["entries"]:
            if entry["spans_sha256"] is None:
                continue
            body = read_object(data_root, entry["source_sha256"])
            spans = verify_spans(json.loads(read_object(data_root, entry["spans_sha256"])))
            verify_spans_against_source(spans, body)
            verified += 1
        return {"generation_id": generation["generation_id"], "verified_span_documents": verified}

    key = PartitionKey(
        provider="openai", model_identifier=EMBEDDING_MODEL, dimension=3,
        normalization="round_half_even_scale_2p20",
    )

    def embed(_key: str) -> dict[str, Any]:
        projection = build_projection(
            data_root, generation_id=result(3)["generation_id"], key=key,
            gateway=gateway, processor_id=PROCESSOR_ID, max_input_tokens=8192,
            timeout_milliseconds=10_000, recorded_at=recorded_at,
        )
        return {
            "projection_id": projection.projection_id,
            "projection_hash": projection.manifest["content_hash"],
            "provider_calls": projection.provider_calls,
        }

    def refresh(_key: str) -> dict[str, Any]:
        projection = load_projection(data_root, result(5)["projection_id"])
        return {
            "projection_id": projection.projection_id,
            "vector_count": len(projection.vectors), "provider_calls": 0,
        }

    def retrieve(_key: str) -> dict[str, Any]:
        query = embed_query(
            data_root, projection_id=result(5)["projection_id"], query=query_text,
            gateway=gateway, processor_id=PROCESSOR_ID,
            max_input_tokens=1024, timeout_milliseconds=10_000,
        )
        cards = retrieve_evidence(
            data_root, query_embedding_id=query["query_embedding_id"], limit=2,
        )
        return {
            "query_embedding_id": query["query_embedding_id"],
            "evidence_card_hashes": [item["content_hash"] for item in cards],
            "exact_passages": [item["exact_text"] for item in cards],
            "provider_calls_during_retrieval": 0,
        }

    def write_program(_key: str) -> dict[str, Any]:
        source = b"print(sum(len(item) for item in evidence_passages))\n"
        return {"program_hash": sha256_bytes(source), "network": "none"}

    def run_program(_key: str) -> dict[str, Any]:
        # This fixture outcome stands in for the already separately gated OCI
        # runner; it is explicitly not a production sandbox execution.
        passages = result(7)["exact_passages"]
        return {
            "adapter_id": "fixture.no-execution",
            "status": "completed", "value": sum(len(item) for item in passages),
            "network": "none", "creates_warrant": False,
        }

    def inspect(_key: str) -> dict[str, Any]:
        return {"selected_result": result(9)["value"], "status": "candidate"}

    def verify(_key: str) -> dict[str, Any]:
        cards = result(7)["exact_passages"]
        return {
            "verifier": "exact_sha256_recomputation",
            "passage_hashes": [sha256_bytes(item.encode("utf-8")) for item in cards],
            "status": "verified_artifact_integrity",
            "target_correspondence": "not_assessed",
            "creates_warrant": False,
        }

    def formal(_key: str) -> dict[str, Any]:
        return {
            "status": "not_requested", "reason": "fixture has no formal proposition",
            "creates_warrant": False,
        }

    def report(_key: str) -> dict[str, Any]:
        return {
            "status": "claim_free_status_report",
            "evidence_card_hashes": result(7)["evidence_card_hashes"],
            "experiment_status": result(9)["status"],
            "verification_status": result(11)["status"],
            "before_announcement": "human_approval_required",
        }

    actions = (
        RuntimeAction(ActionType.SEARCH_LITERATURE, {"terms": ["synthetic", "fixture"]}, search),
        RuntimeAction(ActionType.FOLLOW_DISCOVERY_RESULTS, {"max_depth": 1}, follow),
        RuntimeAction(ActionType.ACQUIRE_SOURCE, lambda: {
            "source": "fixture-snapshot", "discovery_candidate_ids": result(1)["candidate_ids"],
        }, acquire),
        RuntimeAction(ActionType.PARSE_SOURCE, lambda: {
            "parser": "utf8_exact_char_spans_v1", "generation_id": result(3)["generation_id"],
        }, parse),
        RuntimeAction(ActionType.EMBED_SOURCES, lambda: {
            "partition": key.payload(), "generation_id": result(3)["generation_id"],
        }, embed, True),
        RuntimeAction(ActionType.REFRESH_RETRIEVAL_INDEX, lambda: {
            "policy": "immutable_projection_v1", "projection_id": result(5)["projection_id"],
        }, refresh),
        RuntimeAction(ActionType.RETRIEVE_EVIDENCE, lambda: {
            "query_hash": sha256_bytes(query_text.encode()),
            "projection_id": result(6)["projection_id"],
        }, retrieve, True),
        RuntimeAction(ActionType.WRITE_PROGRAM, lambda: {
            "program": "fixture_length_sum",
            "evidence_card_hashes": result(7)["evidence_card_hashes"],
        }, write_program),
        RuntimeAction(ActionType.RUN_PROGRAM, lambda: {
            "sandbox": "fixture_no_execution", "program_hash": result(8)["program_hash"],
        }, run_program),
        RuntimeAction(ActionType.INSPECT_RESULT, lambda: {
            "selection": "fixture_length", "experiment_value": result(9)["value"],
        }, inspect),
        RuntimeAction(ActionType.VERIFY, lambda: {
            "method": "exact_sha256_recomputation",
            "evidence_card_hashes": result(7)["evidence_card_hashes"],
        }, verify),
        RuntimeAction(ActionType.FORMAL_CHECK, lambda: {
            "mode": "not_requested", "verification_status": result(11)["status"],
        }, formal),
        RuntimeAction(ActionType.REPORT, lambda: {
            "format": "claim_free_status",
            "evidence_card_hashes": result(7)["evidence_card_hashes"],
        }, report),
    )
    summary = EndToEndCampaignRunner(
        campaign_root, campaign_id=campaign_id, recorded_at=recorded_at,
        max_actions=16,
    ).run(actions)
    closeout_path = campaign_root / "budget-closeout.json"
    closeout = ledger.close(wall_milliseconds_used=0)
    _write_once(closeout_path, public_value(closeout))
    summary = dict(summary)
    summary.update({
        "profile_selection_hash": selection.content_hash,
        "budget_hash": budget.content_hash,
        "budget_closeout_hash": closeout.content_hash,
        "charge_event_count": len(ledger.events),
        "corpus_data_root": str(data_root.resolve()),
        "target_hash": target["content_hash"],
    })
    summary["content_hash"] = canonical_hash({
        key: value for key, value in summary.items() if key != "content_hash"
    })
    _write_once(campaign_root / "end-to-end-closeout.json", summary)
    publication = campaign_root / "publication"
    latex_campaign_id = campaign_id.replace("_", "\\_")
    tex = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\section*{AdaIvy campaign status (unapproved draft)}\n"
        f"Campaign: \\texttt{{{latex_campaign_id}}}\\\\\n"
        f"Status: \\texttt{{{summary['status']}}}\\\\\n"
        "This claim-free status report creates no mathematical warrant, "
        "novelty finding, significance finding, or publication approval.\n"
        "\\end{document}\n"
    ).encode("utf-8")
    _write_bytes_once(publication / "paper.tex", tex)
    _write_once(publication / "status.json", {
        "schema_version": "adaivy.end-to-end-publication-status.v1",
        "campaign_id": campaign_id, "campaign_summary_hash": summary["content_hash"],
        "paper_tex_sha256": sha256_bytes(tex), "approval": "unapproved",
        "typeset_status": "not_typeset", "pdf_sha256": None,
        "before_announcement": "human_approval_required",
    })
    return summary


__all__ = ["run_fixture_campaign"]
