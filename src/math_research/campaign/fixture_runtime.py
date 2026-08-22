"""Deterministic offline end-to-end campaign used by the acceptance gate.

It exercises the same profile-bound embedding boundary, unified budget,
persistent corpus, retrieval, checkpoint, experiment, verification and report
records as a live campaign while deliberately making no network, live-provider,
or container call. Its scripted model responses still cross the selected
profile and budget boundary. Its artifacts state fixture provenance and create
no warrant.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from ..corpus_retrieval import (
    build_projection, embed_query, load_projection, load_retrieval_result,
    retrieve_evidence,
)
from ..corpus_service.dataroot import initialize_data_root, read_object
from ..corpus_service.generation import require_active_generation
from ..corpus_service.policy import load_policy
from ..corpus_service.ports import DirectoryArchiveSource
from ..corpus_service.serialization import (
    canonical_bytes, sealed, sha256_bytes, strict_canonical_object, verify_sealed,
)
from ..corpus_service.service import ingest_tranche
from ..corpus_service.snapshot import load_tranche_config
from ..corpus_service.spans import verify_spans, verify_spans_against_source
from ..domain.entities import OpaqueId
from ..embedding.gateways import ScriptedEmbeddingGateway
from ..embedding.partition import PartitionKey
from ..phase2.pricing import create_pricing_snapshot
from ..phase2.model_gateway import ScriptedModelGateway
from ..phase2.records import ModelRequest, ModelResult, ModelResultStatus, ModelUsage
from ..publication.bundle import verify_bundle
from ..publication.latexsafe import escape_prose
from ..publication.serialization import canonical_hash as publication_canonical_hash
from ..publication.serialization import sha256_bytes as publication_sha256_bytes
from ..publication.typeset import load_toolchain, toolchain_status, typeset_bundle
from .budget import (
    BudgetCapability, CampaignBudget, CampaignBudgetLedger, ChargeEvent, SubBudget,
)
from .checkpoint import ActionCheckpointStore
from .credentials import CredentialProfile, select_credential_profile
from .end_to_end import EndToEndCampaignRunner, RuntimeAction, parse_planned_action
from .records import ActionType, RecordStatus, UsageSource, canonical_hash, public_value
from .routing import ProfileBoundEmbeddingGateway, ProfileBoundModelGateway


PROCESSOR_ID = "processor.openai.synthetic-fixture-embedding"
EMBEDDING_MODEL = "synthetic-fixture-embedding-v1"
PROFILE_ID = "adaivy"
MODEL_IDENTIFIER = "synthetic-fixture-context-v1"
RUNTIME_CONFIG_SCHEMA_VERSION = "adaivy.end-to-end-runtime-config.v1"


def load_fixture_runtime_config(path: Path) -> dict[str, Any]:
    value = verify_sealed(
        strict_canonical_object(
            path.read_bytes(), maximum=1_048_576, label="end-to-end runtime config",
            code="end_to_end_runtime_config_invalid",
        ), label="end-to-end runtime config",
        code="end_to_end_runtime_config_invalid",
    )
    expected = {
        "schema_version", "mode", "campaign_id", "recorded_at", "data_root",
        "data_root_id", "repository_root", "target_hash", "max_model_requests",
        "max_embedding_requests", "max_network_requests", "max_tool_runs",
        "max_storage_bytes", "max_wall_milliseconds", "profile_id", "content_hash",
    }
    if set(value) != expected or value["schema_version"] != RUNTIME_CONFIG_SCHEMA_VERSION:
        raise ValueError("end-to-end runtime config fields differ")
    if value["mode"] != "fixture":
        raise ValueError("unsupported end-to-end runtime mode")
    ActionCheckpointStore(Path("."), value["campaign_id"])
    ActionCheckpointStore(Path("."), value["profile_id"])
    ActionCheckpointStore(Path("."), value["data_root_id"])
    for field in (
        "max_model_requests", "max_embedding_requests", "max_network_requests",
        "max_tool_runs",
    ):
        item = value[field]
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise ValueError(f"{field} must be a non-negative integer")
    for field in ("max_storage_bytes", "max_wall_milliseconds"):
        item = value[field]
        if not isinstance(item, int) or isinstance(item, bool) or item < 1:
            raise ValueError(f"{field} must be a positive integer")
    for field in ("data_root", "repository_root"):
        if not isinstance(value[field], str) or not Path(value[field]).is_absolute():
            raise ValueError(f"{field} must be an absolute path")
    if value["profile_id"] != PROFILE_ID:
        raise ValueError("runtime config names an unavailable fixture profile")
    if not isinstance(value["recorded_at"], str) or not value["recorded_at"]:
        raise ValueError("runtime recorded_at differs")
    if not isinstance(value["target_hash"], str) or re.fullmatch(
        r"sha256:[0-9a-f]{64}", value["target_hash"],
    ) is None:
        raise ValueError("runtime target hash differs")
    return value


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


def _publication_bundle(
    campaign_root: Path, *, summary: Mapping[str, Any], target: Mapping[str, Any],
    checkpoints: ActionCheckpointStore, toolchain_path: Path,
) -> dict[str, Any]:
    """Write and, when possible, typeset a provenance-closed status bundle."""

    publication = campaign_root / "publication"
    manifest_path = publication / "MANIFEST.json"
    if manifest_path.exists():
        return verify_bundle(publication)

    terminals = list(checkpoints.completed())
    action_hashes = [item["content_hash"] for item in terminals]
    report_result = next((
        item["result"] for item in reversed(terminals)
        if item["action_type"] == ActionType.REPORT.value
    ), {})
    verification_results = [
        item["result"] for item in terminals
        if item["action_type"] == ActionType.VERIFY.value
    ]
    ledger = sealed({
        "schema_version": "adaivy.end-to-end-publication-ledger.v1",
        "campaign_id": summary["campaign_id"],
        "campaign_summary_hash": summary["content_hash"],
        "target_hash": target["content_hash"],
        "action_checkpoint_hashes": action_hashes,
        "retrieval_id": report_result.get("retrieval_id"),
        "retrieval_result_hash": report_result.get("retrieval_result_hash"),
        "evidence_card_hashes": report_result.get("evidence_card_hashes", []),
        "verification_results": verification_results,
        "budget_hash": summary["budget_hash"],
        "budget_closeout_hash": summary["budget_closeout_hash"],
        "approval": "unapproved",
        "creates_mathematical_warrant": False,
        "content_hash": None,
    })
    action_lines = "\n".join(
        r"\item \texttt{" + escape_prose(item, "action checkpoint hash") + "}"
        for item in action_hashes
    ) or r"\item No action reached a terminal checkpoint."
    evidence = ", ".join(report_result.get("evidence_card_hashes", [])) or "none"
    verification = ", ".join(
        str(item.get("verification_status", item.get("status", "unresolved")))
        for item in verification_results
    ) or "none"
    tex = (
        "\\documentclass{article}\n"
        "\\usepackage[T1]{fontenc}\n"
        "\\begin{document}\n"
        "\\section*{AdaIvy campaign status (unapproved draft)}\n"
        "Campaign: \\texttt{" + escape_prose(str(summary["campaign_id"]), "campaign id") + "}\\\\\n"
        "Status: \\texttt{" + escape_prose(str(summary["status"]), "status") + "}\\\\\n"
        "Target record: \\texttt{" + escape_prose(str(target["content_hash"]), "target hash") + "}\\\\\n"
        "Campaign closeout: \\texttt{" + escape_prose(str(summary["content_hash"]), "summary hash") + "}\\\\\n"
        "Budget closeout: \\texttt{" + escape_prose(str(summary["budget_closeout_hash"]), "budget hash") + "}\\\\\n"
        "Retrieval record: \\texttt{" + escape_prose(str(report_result.get("retrieval_id", "none")), "retrieval id") + "}\\\\\n"
        "Evidence cards: \\texttt{" + escape_prose(evidence, "evidence hashes") + "}\\\\\n"
        "Verifier outcomes: \\texttt{" + escape_prose(verification, "verification outcomes") + "}.\n"
        "\\subsection*{Action checkpoint hashes}\n\\begin{itemize}\n"
        + action_lines + "\n\\end{itemize}\n"
        "This record-driven status projection creates no novelty, significance, "
        "mathematical-warrant, publication-approval, or announcement decision.\n"
        "\\end{document}\n"
    ).encode("utf-8")
    toolchain = load_toolchain(toolchain_path)
    status = toolchain_status(toolchain)
    build = {
        "schema_version": "adaivy.end-to-end-publication-build.v1",
        "source_date_epoch": 1735689600, "force_source_date": 1,
        "tex_entrypoint": "paper.tex", "typeset_status": "not_typeset",
        "pdf_sha256": None, "toolchain": dict(toolchain),
        "typeset_reason": status.reason,
    }
    files: dict[str, bytes] = {
        "paper.tex": tex,
        "records/campaign-target.json": canonical_bytes(target) + b"\n",
        "records/campaign-closeout.json": canonical_bytes(summary) + b"\n",
        "records/ledger.json": canonical_bytes(ledger) + b"\n",
        "records/action-checkpoints.json": canonical_bytes(terminals) + b"\n",
        "records/credential-profile.json": (campaign_root / "credential-profile.json").read_bytes(),
        "records/credential-selection.json": (campaign_root / "credential-selection.json").read_bytes(),
        "records/campaign-budget.json": (campaign_root / "campaign-budget.json").read_bytes(),
        "records/budget-closeout.json": (campaign_root / "budget-closeout.json").read_bytes(),
        "build.json": canonical_bytes(build) + b"\n",
    }
    retrieval_id = report_result.get("retrieval_id")
    if retrieval_id is not None:
        data_root = Path(str(summary["corpus_data_root"]))
        retrieval = load_retrieval_result(data_root, retrieval_id)
        if retrieval["content_hash"] != report_result.get("retrieval_result_hash"):
            raise ValueError("publication retrieval binding differs")
        files["records/retrieval-result.json"] = canonical_bytes(retrieval) + b"\n"
        for index, object_hash in enumerate(retrieval["evidence_card_object_hashes"], start=1):
            files[f"records/evidence-card-{index:03d}.json"] = read_object(
                data_root, object_hash,
            )
    publication.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        _write_bytes_once(publication / relative, content)
    manifest: dict[str, Any] = {
        "schema_version": "adaivy.end-to-end-publication-bundle.v1",
        "campaign_id": summary["campaign_id"],
        "campaign_summary_hash": summary["content_hash"],
        "target_hash": target["content_hash"],
        "ledger_hash": ledger["content_hash"],
        "publication_approval": "unapproved",
        "before_announcement": "human_approval_required",
        "typeset_status": "not_typeset", "pdf_sha256": None,
        "files": [
            {"path": name, "sha256": publication_sha256_bytes(content), "bytes": len(content)}
            for name, content in sorted(files.items())
        ],
    }
    manifest["bundle_hash"] = publication_canonical_hash(manifest)
    _write_once(manifest_path, manifest)
    if status.available:
        try:
            return typeset_bundle(publication, toolchain)
        except Exception as error:
            _write_once(campaign_root / "publication-generation-error.json", sealed({
                "schema_version": "adaivy.end-to-end-publication-error.v1",
                "error_class": type(error).__name__, "content_hash": None,
            }))
    return verify_bundle(publication)


def run_fixture_campaign(
    campaign_root: Path, *, data_root: Path, campaign_id: str,
    recorded_at: str, repository_root: Path, problem_bytes: bytes | None = None,
    max_embedding_requests: int = 64,
    profile_id: str = PROFILE_ID,
    max_model_requests: int = 64,
    max_network_requests: int = 64,
    max_tool_runs: int = 64,
    max_storage_bytes: int = 100_000_000,
    max_wall_milliseconds: int = 3_600_000,
    data_root_id: str = "dataroot.adaivy.persistent",
) -> dict[str, Any]:
    """Initialize and run/resume the complete offline fixture in one call."""

    # Validate all externally supplied identifiers before creating any file.
    ActionCheckpointStore(campaign_root, campaign_id)
    ActionCheckpointStore(campaign_root, profile_id)
    ActionCheckpointStore(campaign_root, data_root_id)
    if profile_id != PROFILE_ID:
        raise ValueError("offline fixture registers only the explicit 'adaivy' profile")
    for field, value in (
        ("max_model_requests", max_model_requests),
        ("max_embedding_requests", max_embedding_requests),
        ("max_network_requests", max_network_requests),
        ("max_tool_runs", max_tool_runs),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{field} must be a non-negative integer")
    for field, value in (
        ("max_storage_bytes", max_storage_bytes),
        ("max_wall_milliseconds", max_wall_milliseconds),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{field} must be a positive integer")
    repository_root = repository_root.resolve()
    data_root = data_root.resolve()
    if data_root == repository_root or repository_root in data_root.parents:
        raise ValueError("persistent corpus data root must be outside the Git working tree")
    campaign_root.mkdir(parents=True, exist_ok=True)
    problem_path = campaign_root / "problem.bin"
    if problem_path.exists():
        frozen_problem = problem_path.read_bytes()
        if problem_bytes is not None and problem_bytes != frozen_problem:
            raise ValueError("campaign target is already frozen to different bytes")
    else:
        frozen_problem = problem_bytes or b"Offline fixture: retrieve exact synthetic passages.\n"
        if not frozen_problem or len(frozen_problem) > 1_048_576:
            raise ValueError("campaign problem must be nonempty and at most 1048576 bytes")
        _write_bytes_once(problem_path, frozen_problem)
    if not frozen_problem or len(frozen_problem) > 1_048_576:
        raise ValueError("frozen campaign problem size differs")
    target = {
        "schema_version": "adaivy.end-to-end-target.v1",
        "campaign_id": campaign_id,
        "problem_sha256": sha256_bytes(frozen_problem),
        "byte_count": len(frozen_problem),
        "frozen_at": recorded_at,
    }
    target["content_hash"] = canonical_hash(target)
    _write_once(campaign_root / "campaign-target.json", target)
    runtime_config = sealed({
        "schema_version": RUNTIME_CONFIG_SCHEMA_VERSION,
        "mode": "fixture",
        "campaign_id": campaign_id,
        "recorded_at": recorded_at,
        "data_root": str(data_root.resolve()),
        "data_root_id": data_root_id,
        "repository_root": str(repository_root.resolve()),
        "target_hash": target["content_hash"],
        "max_embedding_requests": max_embedding_requests,
        "max_model_requests": max_model_requests,
        "max_network_requests": max_network_requests,
        "max_tool_runs": max_tool_runs,
        "max_storage_bytes": max_storage_bytes,
        "max_wall_milliseconds": max_wall_milliseconds,
        "profile_id": profile_id,
        "content_hash": None,
    })
    _write_once(campaign_root / "end-to-end-runtime-config.json", runtime_config)
    initialize_data_root(
        data_root, data_root_id=data_root_id,
        initialized_at=recorded_at,
    )
    profile = CredentialProfile(
        profile_id=profile_id, provider="openai", model_identifier=MODEL_IDENTIFIER,
        embedding_model_identifier=EMBEDDING_MODEL, endpoint_settings=(),
        credential_source="offline-fixture",
    ).finalized()
    profile, selection = select_credential_profile(
        {profile_id: profile}, profile_id, campaign_id=campaign_id,
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
        model_identifier=MODEL_IDENTIFIER, source="offline fixture; no charge",
        captured_at=recorded_at, currency="USD",
        input_microusd_per_million_tokens=0,
        output_microusd_per_million_tokens=0,
    )
    model_budget = SubBudget(
        max_requests=max_model_requests, max_input_tokens=1_000_000,
        max_output_tokens=1_000_000, max_cost_microusd=0,
        max_bytes=max_storage_bytes, max_documents=2_048,
    )
    embedding_budget = SubBudget(
        max_requests=max_embedding_requests, max_input_tokens=1_000_000,
        max_output_tokens=0, max_cost_microusd=0, max_bytes=max_storage_bytes,
        max_documents=2_048,
    )
    network_budget = SubBudget(
        max_requests=max_network_requests, max_input_tokens=0, max_output_tokens=0,
        max_cost_microusd=0, max_bytes=max_storage_bytes, max_documents=2_048,
    )
    tool_budget = SubBudget(
        max_requests=max_tool_runs, max_input_tokens=0, max_output_tokens=0,
        max_cost_microusd=0, max_bytes=max_storage_bytes, max_documents=2_048,
    )
    storage_budget = SubBudget(
        max_requests=64, max_input_tokens=0, max_output_tokens=0,
        max_cost_microusd=0, max_bytes=max_storage_bytes, max_documents=2_048,
    )
    budget = CampaignBudget(
        campaign_id=campaign_id, pricing_snapshot_hash=model_pricing.content_hash,
        embedding_pricing_snapshot_hash=embedding_pricing.content_hash,
        max_total_cost_microusd=0, max_wall_milliseconds=max_wall_milliseconds,
        model=model_budget, embedding=embedding_budget, network=network_budget,
        tool=tool_budget, storage=storage_budget,
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
    problem_text = frozen_problem.decode("utf-8", "replace")
    problem_terms = re.findall(r"[A-Za-z0-9]+", problem_text.casefold())[:8]
    query_text = " ".join(problem_terms) or "synthetic fixture exact span"
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
        max_actions=20,
    ).checkpoints

    def result(sequence: int) -> dict[str, Any]:
        terminal = checkpoints.load(sequence, "terminal")
        if terminal is None or terminal["status"] != "completed":
            raise ValueError(f"required action {sequence} is not complete")
        return terminal["result"]

    action_schema = (repository_root / "schemas" / "model-campaign-action-v2.schema.json").read_text(
        encoding="utf-8"
    )

    def model_action(
        *, purpose: str, sequence: int, action: dict[str, Any], context: dict[str, Any],
    ) -> dict[str, Any]:
        rendered = json.dumps(action, separators=(",", ":"), sort_keys=True)
        provider = ScriptedModelGateway({purpose: [ModelResult(
            status=ModelResultStatus.SUCCEEDED, provider="openai",
            model_identifier=MODEL_IDENTIFIER, capabilities=("structured_output",),
            structured_output=rendered, declared_rationale=None, refusal=None,
            usage=ModelUsage(
                input_tokens=0, output_tokens=0, total_tokens=0,
                usage_source="fixture",
            ),
            retry_classification="none", provider_request_id=None,
        )]})
        routed = ProfileBoundModelGateway(
            profile=profile, selection=selection, gateway=provider,
            pricing=model_pricing, ledger=ledger,
        )
        request = ModelRequest(
            request_id=OpaqueId(f"request.fixture.{campaign_id}.{sequence}"),
            run_id=OpaqueId(f"run.fixture.{campaign_id}"), purpose=purpose,
            template_id="campaign.end_to_end.fixture",
            template_version="1.0.0",
            template_hash=sha256_bytes(b"campaign.end_to_end.fixture.v1"),
            template_text="Return one action matching the closed campaign v2 schema.",
            serialized_context=json.dumps(context, separators=(",", ":"), sort_keys=True),
            response_schema=action_schema, referenced_entity_ids=(),
            timeout_milliseconds=10_000, max_output_tokens=2_048,
        )
        response = routed.complete(request, routed.prepare(request))
        if response.status is not ModelResultStatus.SUCCEEDED or response.structured_output is None:
            raise ValueError("fixture campaign planner did not return a completed action")
        parsed = json.loads(response.structured_output)
        # Parsing here makes the same v2 contract executable on the campaign
        # path; the returned operation remains untrusted until its worker gate.
        parse_planned_action(response.structured_output, lambda _: {})
        return {
            "profile_id": profile.profile_id,
            "provider": response.provider,
            "model_identifier": response.model_identifier,
            "planner_action": parsed,
            "planner_action_hash": canonical_hash(parsed),
        }

    def plan_search(_key: str) -> dict[str, Any]:
        return model_action(
            purpose="campaign_literature_query", sequence=1,
            action={
                "schema_version": "2.0.0", "action_type": "search_literature",
                "branch_id": "branch.main",
                "rationale": "Generate a bounded terminology query before research.",
                "operation_request": {
                    "query": query_text, "max_results": 2,
                    "source_policy": "fixture-open-access-v1",
                },
            },
            context={
                "target_hash": target["content_hash"],
                "problem_sha256": target["problem_sha256"],
                "problem_excerpt": problem_text[:4_096],
            },
        )

    def search(_key: str) -> dict[str, Any]:
        planned = result(1)["planner_action"]
        parsed = parse_planned_action(canonical_bytes(planned), lambda _: {})
        if parsed.action_type is not ActionType.SEARCH_LITERATURE:
            raise ValueError("planner did not request literature search")
        return {
            "provider": "fixture", "network_requests": 0,
            "candidate_ids": ["doc-open-alpha", "doc-open-beta"],
            "query": parsed.request["query"],
            "planner_action_hash": result(1)["planner_action_hash"],
            "status": "untrusted_inspiration_candidate",
        }

    def follow(_key: str) -> dict[str, Any]:
        return {
            "followed_candidate_ids": result(2)["candidate_ids"],
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
        generation = require_active_generation(data_root, result(4)["generation_id"])
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
            data_root, generation_id=result(4)["generation_id"], key=key,
            gateway=gateway, processor_id=PROCESSOR_ID, max_input_tokens=8192,
            timeout_milliseconds=10_000, recorded_at=recorded_at,
        )
        return {
            "projection_id": projection.projection_id,
            "projection_hash": projection.manifest["content_hash"],
            "provider_calls": projection.provider_calls,
        }

    def refresh(_key: str) -> dict[str, Any]:
        projection = load_projection(data_root, result(6)["projection_id"])
        return {
            "projection_id": projection.projection_id,
            "vector_count": len(projection.vectors), "provider_calls": 0,
        }

    def retrieve(_key: str) -> dict[str, Any]:
        query = embed_query(
            data_root, projection_id=result(6)["projection_id"], query=result(2)["query"],
            gateway=gateway, processor_id=PROCESSOR_ID,
            max_input_tokens=1024, timeout_milliseconds=10_000,
        )
        retrieval = retrieve_evidence(
            data_root, query_embedding_id=query["query_embedding_id"], limit=2,
            include_result=True,
            model_context_route={
                "processor_id": "processor.openai.synthetic-fixture-context",
                "provider": profile.provider,
                "model_identifier": profile.model_identifier,
                "at": recorded_at,
            },
        )
        assert isinstance(retrieval, dict)
        cards = retrieval["cards"]
        manifest = retrieval["manifest"]
        return {
            "query_embedding_id": query["query_embedding_id"],
            "retrieval_id": manifest["retrieval_id"],
            "retrieval_result_hash": manifest["content_hash"],
            "evidence_card_hashes": [item["content_hash"] for item in cards],
            "evidence_card_object_hashes": manifest["evidence_card_object_hashes"],
            "exact_passages": [item["exact_text"] for item in cards],
            "model_context_route": manifest["model_context_route"],
            "provider_calls_during_retrieval": 0,
        }

    def plan_research(_key: str) -> dict[str, Any]:
        evidence = result(8)
        return model_action(
            purpose="campaign_evidence_guided_ideation", sequence=9,
            action={
                "schema_version": "2.0.0", "action_type": "experiment",
                "branch_id": "branch.main",
                "rationale": "Test a deliberately fallible candidate derived from cited passages.",
                "operation_request": {
                    "operation": "sum_utf8_byte_lengths", "proposed_offset": 1,
                    "retrieval_id": evidence["retrieval_id"],
                    "evidence_card_hashes": evidence["evidence_card_hashes"],
                },
            },
            context={
                "target_hash": target["content_hash"],
                "retrieval_id": evidence["retrieval_id"],
                "evidence_card_hashes": evidence["evidence_card_hashes"],
                "exact_passages": evidence["exact_passages"],
                "untrusted_data": True,
            },
        )

    def _charge_tool(purpose: str, request: dict[str, Any]) -> None:
        ledger.admit(BudgetCapability.TOOL, credential_profile_id=profile.profile_id, requests=1)
        ledger.charge(
            capability=BudgetCapability.TOOL,
            credential_profile_id=profile.profile_id, purpose=purpose,
            status=RecordStatus.COMPLETED, request_hash=canonical_hash(request),
            usage_source=UsageSource.LOCALLY_MEASURED, requests=1,
        )

    def experiment(_key: str) -> dict[str, Any]:
        planned = result(9)["planner_action"]
        parsed = parse_planned_action(canonical_bytes(planned), lambda _: {})
        if parsed.action_type is not ActionType.EXPERIMENT:
            raise ValueError("planner did not request a bounded experiment")
        passages = result(8)["exact_passages"]
        observed = sum(len(item.encode("utf-8")) for item in passages)
        verification_target = canonical_hash({
            "campaign_target_hash": target["content_hash"],
            "operation": parsed.request["operation"],
            "evidence_card_object_hashes": result(8)["evidence_card_object_hashes"],
        })
        request = {
            "operation": parsed.request["operation"],
            "retrieval_id": result(8)["retrieval_id"],
            "verification_target_hash": verification_target,
        }
        _charge_tool("campaign_bounded_exact_experiment", request)
        candidate = {
            "verification_target_hash": verification_target,
            "claimed_value": observed + parsed.request["proposed_offset"],
            "retrieval_id": result(8)["retrieval_id"],
        }
        return {
            "adapter_id": "builtin.exact-byte-length-experiment.v1",
            "status": "candidate", "candidate": candidate,
            "candidate_hash": canonical_hash(candidate), "network": "none",
            "bounded": True, "creates_warrant": False,
        }

    def independently_observed() -> tuple[int, str]:
        evidence = result(8)
        exact: list[str] = []
        for digest in evidence["evidence_card_object_hashes"]:
            card = verify_sealed(
                json.loads(read_object(data_root, digest)),
                label="evidence card", code="fixture_verifier_evidence_invalid",
            )
            exact.append(card["exact_text"])
        observed = sum(len(item.encode("utf-8")) for item in exact)
        expected_target = canonical_hash({
            "campaign_target_hash": target["content_hash"],
            "operation": "sum_utf8_byte_lengths",
            "evidence_card_object_hashes": evidence["evidence_card_object_hashes"],
        })
        return observed, expected_target

    def verify_candidate(candidate: dict[str, Any], purpose: str) -> dict[str, Any]:
        observed, expected_target = independently_observed()
        request = {
            "candidate_hash": canonical_hash(candidate),
            "target_hash": expected_target,
            "retrieval_id": result(8)["retrieval_id"],
        }
        _charge_tool(purpose, request)
        applicable = candidate.get("verification_target_hash") == expected_target
        verified = applicable and candidate.get("claimed_value") == observed
        return {
            "verifier": "builtin.independent-exact-byte-length-verifier.v1",
            "verification_status": "candidate_verified" if verified else "candidate_refuted",
            "candidate_hash": canonical_hash(candidate),
            "target_hash": expected_target, "target_correspondence": "exact",
            "applicable": applicable, "observed_value": observed,
            "creates_warrant": False,
        }

    def verify_first(_key: str) -> dict[str, Any]:
        return verify_candidate(result(10)["candidate"], "campaign_exact_verifier_refutation")

    def falsify(_key: str) -> dict[str, Any]:
        finding = result(11)
        if finding["verification_status"] != "candidate_refuted":
            raise ValueError("falsification requires the retained refuting finding")
        candidate = {
            "verification_target_hash": finding["target_hash"],
            "claimed_value": finding["observed_value"],
            "retrieval_id": result(8)["retrieval_id"],
        }
        return {
            "status": "candidate_repaired_after_refutation", "candidate": candidate,
            "candidate_hash": canonical_hash(candidate),
            "influenced_by_finding_hash": canonical_hash(finding),
            "evidence_card_hashes": result(8)["evidence_card_hashes"],
        }

    def verify_repaired(_key: str) -> dict[str, Any]:
        return verify_candidate(result(12)["candidate"], "campaign_exact_verifier_final")

    def formal(_key: str) -> dict[str, Any]:
        return {
            "status": "not_requested", "reason": "fixture has no formal proposition",
            "creates_warrant": False,
        }

    def report(_key: str) -> dict[str, Any]:
        return {
            "status": "claim_free_status_report",
            "retrieval_id": result(8)["retrieval_id"],
            "retrieval_result_hash": result(8)["retrieval_result_hash"],
            "evidence_card_hashes": result(8)["evidence_card_hashes"],
            "experiment_status": result(10)["status"],
            "initial_verification_status": result(11)["verification_status"],
            "verification_status": result(13)["verification_status"],
            "before_announcement": "human_approval_required",
        }

    actions = (
        RuntimeAction(ActionType.PLAN, {"purpose": "campaign_literature_query"}, plan_search, True),
        RuntimeAction(ActionType.SEARCH_LITERATURE, lambda: result(1)["planner_action"]["operation_request"], search),
        RuntimeAction(ActionType.FOLLOW_DISCOVERY_RESULTS, {
            "max_depth": 1, "origin": "local-fixture",
            "allowed_origins": ["local-fixture"],
        }, follow),
        RuntimeAction(ActionType.ACQUIRE_SOURCE, lambda: {
            "source": "fixture-snapshot", "discovery_candidate_ids": result(2)["candidate_ids"],
        }, acquire),
        RuntimeAction(ActionType.PARSE_SOURCE, lambda: {
            "parser": "utf8_exact_char_spans_v1", "generation_id": result(4)["generation_id"],
        }, parse),
        RuntimeAction(ActionType.EMBED_SOURCES, lambda: {
            "partition": key.payload(), "generation_id": result(4)["generation_id"],
        }, embed, True),
        RuntimeAction(ActionType.REFRESH_RETRIEVAL_INDEX, lambda: {
            "policy": "immutable_projection_v1", "projection_id": result(6)["projection_id"],
        }, refresh),
        RuntimeAction(ActionType.RETRIEVE_EVIDENCE, lambda: {
            "query_hash": sha256_bytes(result(2)["query"].encode()),
            "projection_id": result(7)["projection_id"],
        }, retrieve, True),
        RuntimeAction(ActionType.PLAN, lambda: {
            "purpose": "campaign_evidence_guided_ideation",
            "retrieval_id": result(8)["retrieval_id"],
            "evidence_card_hashes": result(8)["evidence_card_hashes"],
        }, plan_research, True),
        RuntimeAction(ActionType.EXPERIMENT, lambda: result(9)["planner_action"]["operation_request"], experiment),
        RuntimeAction(ActionType.VERIFY, lambda: {
            "candidate_hash": result(10)["candidate_hash"],
            "retrieval_id": result(8)["retrieval_id"],
        }, verify_first),
        RuntimeAction(ActionType.FALSIFY, lambda: {
            "finding_hash": canonical_hash(result(11)),
            "candidate_hash": result(10)["candidate_hash"],
        }, falsify),
        RuntimeAction(ActionType.VERIFY, lambda: {
            "candidate_hash": result(12)["candidate_hash"],
            "retrieval_id": result(8)["retrieval_id"],
        }, verify_repaired),
        RuntimeAction(ActionType.FORMAL_CHECK, lambda: {
            "mode": "not_applicable", "verification_status": result(13)["verification_status"],
        }, formal),
        RuntimeAction(ActionType.REPORT, lambda: {
            "format": "claim_free_status",
            "evidence_card_hashes": result(8)["evidence_card_hashes"],
            "verification_status": result(13)["verification_status"],
        }, report),
    )
    summary = EndToEndCampaignRunner(
        campaign_root, campaign_id=campaign_id, recorded_at=recorded_at,
        max_actions=20,
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
        "document_embedding_provider_calls": (
            result(6)["provider_calls"] if checkpoints.load(6, "terminal") is not None
            and checkpoints.load(6, "terminal")["status"] == "completed" else None
        ),
        "retrieval_id": (
            result(8)["retrieval_id"] if checkpoints.load(8, "terminal") is not None
            and checkpoints.load(8, "terminal")["status"] == "completed" else None
        ),
        "initial_verification_status": (
            result(11)["verification_status"] if checkpoints.load(11, "terminal") is not None
            and checkpoints.load(11, "terminal")["status"] == "completed" else None
        ),
        "final_verification_status": (
            result(13)["verification_status"] if checkpoints.load(13, "terminal") is not None
            and checkpoints.load(13, "terminal")["status"] == "completed" else None
        ),
    })
    summary["content_hash"] = canonical_hash({
        key: value for key, value in summary.items() if key != "content_hash"
    })
    _write_once(campaign_root / "end-to-end-closeout.json", summary)
    try:
        _publication_bundle(
            campaign_root, summary=summary, target=target, checkpoints=checkpoints,
            toolchain_path=repository_root / "config" / "publication-typeset-toolchain-v1.json",
        )
    except Exception as error:
        _write_once(campaign_root / "publication-generation-error.json", sealed({
            "schema_version": "adaivy.end-to-end-publication-error.v1",
            "campaign_summary_hash": summary["content_hash"],
            "error_class": type(error).__name__, "content_hash": None,
        }))
    return summary


__all__ = ["load_fixture_runtime_config", "run_fixture_campaign"]
