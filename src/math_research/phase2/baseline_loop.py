"""The single bounded Phase 2 proposer/verifier workflow."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from ..domain.entities import Disposition, Entity, OpaqueId, ResearchDossier
from ..interchange import export_dossier_dict
from . import PHASE2_SCHEMA_VERSION
from .model_gateway import StructuredOutputError, validate_structured_output
from .openai_schema import ProviderSchemaError
from .ports import ArtifactStore, DurableWorkspace, ModelGateway
from .pricing import estimate_cost_microusd
from .prompt_templates import PromptCatalog
from .records import (
    BudgetLimits,
    CostEstimate,
    JobStatus,
    ModelRequest,
    ModelResult,
    ModelResultStatus,
    PricingSnapshot,
    ProposalRecord,
    RunRecord,
    RunStatus,
    VerifierContextManifest,
    VerifierIndependence,
)
from .serialization import canonical_bytes, canonical_hash, canonical_json, public_value, sha256_bytes
from .sqlite_workspace import BudgetExhausted, LateCommitRejected


POLICY_VERSION = "phase1-trust-policy-v1"


class InjectedCrash(RuntimeError):
    pass


class BaselineResearchLoop:
    """Orchestrates exactly one proposer call and one isolated verifier call."""

    def __init__(
        self, *, workspace: DurableWorkspace, artifacts: ArtifactStore,
        proposer: ModelGateway, verifier: ModelGateway,
        independence: VerifierIndependence,
        now: Callable[[], datetime] | None = None,
        prompt_catalog: PromptCatalog | None = None,
        schema_dir: Path | None = None,
        worker_id: str = "phase2.local-worker",
        lease_milliseconds: int = 30_000,
        call_timeout_milliseconds: int = 20_000,
        estimated_output_tokens: int = 512,
        fault_after_proposal_artifact_once: bool = False,
        before_proposal_commit: Callable[[OpaqueId], None] | None = None,
        pricing_snapshot: PricingSnapshot | None = None,
    ) -> None:
        self.workspace = workspace
        self.artifacts = artifacts
        self.proposer = proposer
        self.verifier = verifier
        self.independence = independence
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.prompts = prompt_catalog or PromptCatalog()
        self.schema_dir = schema_dir or Path(__file__).resolve().parents[3] / "schemas"
        self.worker_id = worker_id
        self.lease_milliseconds = lease_milliseconds
        self.call_timeout_milliseconds = call_timeout_milliseconds
        self.estimated_output_tokens = estimated_output_tokens
        self.fault_after_proposal_artifact_once = fault_after_proposal_artifact_once
        self.before_proposal_commit = before_proposal_commit
        self.pricing_snapshot = pricing_snapshot

    def start(
        self, *, run_id: OpaqueId, dossier: ResearchDossier, limits: BudgetLimits,
        deadline_milliseconds: int = 120_000,
    ) -> RunRecord:
        now = self._now()
        budget_id = OpaqueId(f"budget.{run_id.value}")
        record = self.workspace.create_run(
            run_id=run_id, dossier=dossier, budget_id=budget_id, limits=limits, now=now,
        )
        deadline = self._after(deadline_milliseconds)
        self.workspace.enqueue_job(
            job_id=OpaqueId(f"job.{run_id.value}.proposer"), run_id=run_id,
            kind="proposer", idempotency_key=f"job:{run_id.value}:proposer",
            payload_hash=record.dossier_hash, max_attempts=2,
            deadline_at=deadline, now=now,
        )
        return self.workspace.set_run_status(
            run_id, RunStatus.RUNNING.value, now=now,
            idempotency_key=f"run:{run_id.value}:running",
        )

    def pause(self, run_id: OpaqueId) -> RunRecord:
        return self.workspace.set_run_status(
            run_id, RunStatus.PAUSED.value, now=self._now(),
            idempotency_key=f"run:{run_id.value}:paused",
        )

    def resume(self, run_id: OpaqueId) -> RunRecord:
        return self.workspace.set_run_status(
            run_id, RunStatus.RUNNING.value, now=self._now(),
            idempotency_key=f"run:{run_id.value}:resumed",
        )

    def cancel(self, run_id: OpaqueId) -> RunRecord:
        return self.workspace.set_run_status(
            run_id, RunStatus.CANCELLED.value, now=self._now(),
            idempotency_key=f"run:{run_id.value}:cancelled",
        )

    def advance(self, run_id: OpaqueId) -> RunRecord:
        run = self.workspace.get_run(run_id)
        if run.status is not RunStatus.RUNNING:
            return run
        jobs = self.workspace.list_jobs(run_id)
        proposer = next((item for item in jobs if item.kind == "proposer"), None)
        if proposer and proposer.status in {JobStatus.QUEUED, JobStatus.RETRYABLE}:
            self._execute_proposer(run)
            return self.workspace.get_run(run_id)
        verifier = next((item for item in jobs if item.kind == "verifier"), None)
        if verifier and verifier.status in {JobStatus.QUEUED, JobStatus.RETRYABLE}:
            self._execute_verifier(run)
        return self.workspace.get_run(run_id)

    def run_to_terminal(self, run_id: OpaqueId, *, max_steps: int = 4) -> RunRecord:
        previous: tuple[str, tuple[tuple[str, str], ...]] | None = None
        for _ in range(max_steps):
            current = self.workspace.get_run(run_id)
            state = (current.status.value, tuple((item.kind, item.status.value) for item in self.workspace.list_jobs(run_id)))
            if current.status in {RunStatus.AWAITING_REVIEW, RunStatus.UNRESOLVED, RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.PAUSED}:
                return current
            if state == previous:
                return current
            previous = state
            self.advance(run_id)
        return self.workspace.get_run(run_id)

    def _execute_proposer(self, run: RunRecord) -> None:
        job = self.workspace.claim_job(
            run_id=run.run_id, kind="proposer", worker_id=self.worker_id,
            lease_until=self._after(self.lease_milliseconds), now=self._now(),
        )
        if job is None:
            return
        dossier = self.workspace.load_dossier(run.dossier_id)
        context, referenced = self._proposer_context(dossier)
        request = self._request(run, "proposer", context, referenced)
        result, output, result_hash, call_id = self._call(run, job.job_id, request)
        if output is None:
            self._non_success(run, job.job_id, result, result_hash, "proposer")
            return
        try:
            self._validate_target_and_refs(output, dossier, expected_hash=None)
        except StructuredOutputError:
            malformed = replace(result, status=ModelResultStatus.MALFORMED)
            self._non_success(run, job.job_id, malformed, result_hash, "proposer")
            return
        candidate = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "result_type": output["result_type"],
            "target_claim_id": output["target_claim_id"],
            "mathematical_payload": output["mathematical_payload"],
            "referenced_entity_ids": output["referenced_entity_ids"],
        }
        artifact = self.artifacts.put(canonical_bytes(candidate), media_type="application/vnd.adaivy.proposal+json")
        if self.fault_after_proposal_artifact_once:
            self.fault_after_proposal_artifact_once = False
            raise InjectedCrash("simulated crash after artifact creation before semantic commit")
        if self.before_proposal_commit:
            self.before_proposal_commit(run.run_id)
        proposal = ProposalRecord(
            proposal_id=OpaqueId(f"proposal.{run.run_id.value}.proposer"), run_id=run.run_id,
            proposal_kind=output["result_type"], artifact_hash=artifact.content_hash,
            source_kind="model", source_id=call_id.value,
            target_claim_id=dossier.formalization.target_claim_id,
        )
        try:
            self.workspace.commit_proposal(
                proposal, job_id=job.job_id, worker_id=self.worker_id, now=self._now(),
                event_key=f"proposal:{run.run_id.value}:proposer",
            )
            self.workspace.finish_job(
                job.job_id, worker_id=self.worker_id, status=JobStatus.SUCCEEDED.value,
                result_hash=artifact.content_hash, now=self._now(),
                idempotency_key=f"job:{run.run_id.value}:proposer:succeeded",
            )
        except LateCommitRejected:
            return
        self.workspace.enqueue_job(
            job_id=OpaqueId(f"job.{run.run_id.value}.verifier"), run_id=run.run_id,
            kind="verifier", idempotency_key=f"job:{run.run_id.value}:verifier",
            payload_hash=artifact.content_hash, max_attempts=2,
            deadline_at=job.deadline_at, now=self._now(),
        )

    def _execute_verifier(self, run: RunRecord) -> None:
        job = self.workspace.claim_job(
            run_id=run.run_id, kind="verifier", worker_id=self.worker_id,
            lease_until=self._after(self.lease_milliseconds), now=self._now(),
        )
        if job is None:
            return
        dossier = self.workspace.load_dossier(run.dossier_id)
        proposer = next(item for item in self.workspace.list_proposals(run.run_id) if item.source_kind == "model" and item.proposal_id.value.endswith(".proposer"))
        candidate = json.loads(self.artifacts.get(proposer.artifact_hash))
        context, included, excluded = self._verifier_context(dossier, proposer, candidate)
        context_text = canonical_json(context)
        context_artifact = self.artifacts.put(context_text.encode("utf-8"), media_type="application/vnd.adaivy.verifier-context+json")
        manifest = VerifierContextManifest(
            manifest_id=OpaqueId(f"manifest.{run.run_id.value}.verifier"), run_id=run.run_id,
            included_entity_ids=included, excluded_entity_ids=excluded,
            policy_version=POLICY_VERSION, serialized_context_hash=sha256_bytes(context_text.encode("utf-8")),
            context_artifact_hash=context_artifact.content_hash, independence=self.independence,
        )
        manifest_json = canonical_json(manifest)
        self.workspace.save_manifest(manifest, canonical_json=manifest_json, now=self._now())
        request = self._request(run, "verifier", context, included)
        result, output, result_hash, call_id = self._call(run, job.job_id, request)
        if output is None:
            self._non_success(run, job.job_id, result, result_hash, "verifier")
            return
        try:
            self._validate_target_and_refs(output, dossier, expected_hash=proposer.artifact_hash)
        except StructuredOutputError:
            malformed = replace(result, status=ModelResultStatus.MALFORMED)
            self._non_success(run, job.job_id, malformed, result_hash, "verifier")
            return
        finding = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "result_type": output["result_type"],
            "target_claim_id": output["target_claim_id"],
            "candidate_artifact_hash": output["candidate_artifact_hash"],
            "findings": output["findings"],
            "recommendation": output["recommendation"],
            "declared_rationale": output["declared_rationale"],
        }
        artifact = self.artifacts.put(canonical_bytes(finding), media_type="application/vnd.adaivy.verifier-finding+json")
        proposal = ProposalRecord(
            proposal_id=OpaqueId(f"proposal.{run.run_id.value}.verifier"), run_id=run.run_id,
            proposal_kind="verifier_finding", artifact_hash=artifact.content_hash,
            source_kind="model", source_id=call_id.value,
            target_claim_id=dossier.formalization.target_claim_id,
        )
        try:
            self.workspace.commit_proposal(
                proposal, job_id=job.job_id, worker_id=self.worker_id, now=self._now(),
                event_key=f"proposal:{run.run_id.value}:verifier",
            )
            self.workspace.finish_job(
                job.job_id, worker_id=self.worker_id, status=JobStatus.SUCCEEDED.value,
                result_hash=artifact.content_hash, now=self._now(),
                idempotency_key=f"job:{run.run_id.value}:verifier:succeeded",
            )
        except LateCommitRejected:
            return
        terminal = RunStatus.AWAITING_REVIEW if output["recommendation"] == "manual_review" else RunStatus.UNRESOLVED
        self.workspace.set_run_status(
            run.run_id, terminal.value, now=self._now(),
            idempotency_key=f"run:{run.run_id.value}:{terminal.value}",
        )

    def _call(self, run: RunRecord, job_id: OpaqueId, request: ModelRequest) -> tuple[ModelResult, dict[str, object] | None, str | None, OpaqueId]:
        job = next(item for item in self.workspace.list_jobs(run.run_id) if item.job_id == job_id)
        call_id = OpaqueId(f"call.{run.run_id.value}.{request.purpose}.attempt.{job.attempts}")
        gateway = self.proposer if request.purpose == "proposer" else self.verifier
        request_ref = self.artifacts.put(canonical_bytes(request), media_type="application/vnd.adaivy.model-request+json")
        try:
            preparation = gateway.prepare(request)
        except ProviderSchemaError as error:
            compatibility_ref = self.artifacts.put(
                canonical_bytes(error.report),
                media_type="application/vnd.adaivy.provider-schema-compatibility+json",
            )
            config = getattr(gateway, "config", None)
            result = ModelResult(
                status=ModelResultStatus.FAILED,
                provider="openai" if config is not None else "provider",
                model_identifier=getattr(config, "model_identifier", "unknown"),
                capabilities=tuple(getattr(config, "capabilities", ())),
                structured_output=None,
                declared_rationale=None,
                refusal=None,
                usage=self._zero_usage(),
                retry_classification="fatal:provider_schema_incompatible",
                compatibility_report_hash=compatibility_ref.content_hash,
            )
            result_ref = self.artifacts.put(
                canonical_bytes(result), media_type="application/vnd.adaivy.model-result+json",
            )
            self.workspace.record_model_call(
                call_id=call_id, run_id=run.run_id, purpose=request.purpose,
                request_hash=request_ref.content_hash, result_hash=result_ref.content_hash,
                result=result, now=self._now(),
                idempotency_key=f"call:{run.run_id.value}:{request.purpose}:attempt:{job.attempts}",
            )
            return result, None, result_ref.content_hash, call_id
        estimate = max(1, (len(request.serialized_context) + len(request.template_text)) // 4)
        estimated_cost = (
            estimate_cost_microusd(
                self.pricing_snapshot,
                input_tokens=estimate,
                output_tokens=self.estimated_output_tokens,
            )
            if self.pricing_snapshot is not None else 0
        )
        try:
            self.workspace.reserve_call(
                run.budget_id, estimated_input_tokens=estimate,
                estimated_output_tokens=self.estimated_output_tokens,
                estimated_cost_microusd=estimated_cost, now=self._now(),
            )
        except BudgetExhausted:
            result = ModelResult(
                status=ModelResultStatus.FAILED, provider="none", model_identifier="none",
                capabilities=(), structured_output=None, declared_rationale=None, refusal=None,
                usage=self._zero_usage(), retry_classification="fatal:budget_exhausted",
            )
            return result, None, None, call_id
        if self.pricing_snapshot is not None:
            self.workspace.record_cost_estimate(
                CostEstimate(
                    estimate_id=OpaqueId(f"estimate.{call_id.value}"), call_id=call_id,
                    run_id=run.run_id, pricing_snapshot_id=self.pricing_snapshot.snapshot_id,
                    input_token_estimate=estimate,
                    output_token_estimate=self.estimated_output_tokens,
                    estimated_cost_microusd=estimated_cost,
                ),
                now=self._now(),
            )
        projection_manifest_hash = None
        compatibility_report_hash = None
        provider_schema_hash = None
        if preparation is not None:
            provider_ref = self.artifacts.put(
                preparation.provider_schema_json.encode("utf-8"),
                media_type="application/vnd.adaivy.provider-schema+json",
            )
            manifest_ref = self.artifacts.put(
                preparation.transformation_manifest_json.encode("utf-8"),
                media_type="application/vnd.adaivy.schema-projection-manifest+json",
            )
            compatibility_ref = self.artifacts.put(
                preparation.compatibility_report_json.encode("utf-8"),
                media_type="application/vnd.adaivy.provider-schema-compatibility+json",
            )
            self.artifacts.put(
                preparation.compatibility_report_text.encode("utf-8"),
                media_type="text/markdown",
            )
            if provider_ref.content_hash != preparation.provider_schema_hash:
                raise RuntimeError("persisted provider schema hash differs from preparation")
            provider_schema_hash = preparation.provider_schema_hash
            projection_manifest_hash = manifest_ref.content_hash
            compatibility_report_hash = compatibility_ref.content_hash
        result = gateway.complete(request, preparation)
        result = replace(
            result,
            provider_schema_hash=provider_schema_hash,
            projection_manifest_hash=projection_manifest_hash,
            compatibility_report_hash=compatibility_report_hash,
        )
        if self.pricing_snapshot is not None:
            actual_estimate = estimate_cost_microusd(
                self.pricing_snapshot,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
            )
            result = replace(
                result,
                usage=replace(
                    result.usage,
                    estimated_cost_microusd=actual_estimate,
                    pricing_snapshot_id=self.pricing_snapshot.snapshot_id,
                ),
            )
        output: dict[str, object] | None = None
        if result.status is ModelResultStatus.SUCCEEDED and result.structured_output is not None:
            try:
                output = validate_structured_output(
                    request.purpose, result.structured_output, schema_dir=self.schema_dir,
                )
            except StructuredOutputError:
                result = replace(result, status=ModelResultStatus.MALFORMED)
        result_ref = self.artifacts.put(canonical_bytes(result), media_type="application/vnd.adaivy.model-result+json")
        self.workspace.record_usage(
            run.budget_id, input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            cost_microusd=result.usage.estimated_cost_microusd or 0,
            now=self._now(),
        )
        self.workspace.record_model_call(
            call_id=call_id, run_id=run.run_id,
            purpose=request.purpose, request_hash=request_ref.content_hash,
            result_hash=result_ref.content_hash, result=result, now=self._now(),
            idempotency_key=f"call:{run.run_id.value}:{request.purpose}:attempt:{job.attempts}",
        )
        if result.status is not ModelResultStatus.SUCCEEDED or output is None:
            return result, None, result_ref.content_hash, call_id
        return result, output, result_ref.content_hash, call_id

    def _non_success(self, run: RunRecord, job_id: OpaqueId, result: ModelResult, result_hash: str | None, purpose: str) -> None:
        status = JobStatus.TIMED_OUT if result.status is ModelResultStatus.TIMED_OUT else JobStatus.FAILED
        try:
            self.workspace.finish_job(
                job_id, worker_id=self.worker_id, status=status.value,
                result_hash=result_hash, now=self._now(),
                idempotency_key=f"job:{run.run_id.value}:{purpose}:{status.value}",
            )
        except LateCommitRejected:
            return
        self.workspace.set_run_status(
            run.run_id, RunStatus.UNRESOLVED.value, now=self._now(),
            idempotency_key=f"run:{run.run_id.value}:unresolved",
        )

    def _request(self, run: RunRecord, purpose: str, context: dict[str, object], referenced: tuple[OpaqueId, ...]) -> ModelRequest:
        template = self.prompts.load(purpose)
        schema = (self.schema_dir / f"model-{purpose}-v1.schema.json").read_text(encoding="utf-8")
        return ModelRequest(
            request_id=OpaqueId(f"request.{run.run_id.value}.{purpose}"), run_id=run.run_id,
            purpose=purpose, template_id=template.template_id, template_version=template.version,
            template_hash=template.content_hash, template_text=template.text,
            serialized_context=canonical_json(context), response_schema=schema,
            referenced_entity_ids=referenced, timeout_milliseconds=self.call_timeout_milliseconds,
            max_output_tokens=self.estimated_output_tokens,
        )

    @staticmethod
    def _proposer_context(dossier: ResearchDossier) -> tuple[dict[str, object], tuple[OpaqueId, ...]]:
        payload = export_dossier_dict(dossier)
        target_id = dossier.formalization.target_claim_id
        target = next(item for item in payload["claims"] if item["id"] == target_id.value)
        premise_ids = set(dossier.formalization.assumption_claim_ids)
        premises = [item for item in payload["claims"] if item["id"] in {value.value for value in premise_ids}]
        obligations = [item for item in payload["obligations"] if item["claim_id"] == target_id.value and item["status"] in {"open", "blocked"}]
        referenced = tuple(sorted((target_id, dossier.formalization.id, dossier.semantic_alignment.id, *premise_ids), key=lambda item: item.value))
        return {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "purpose": "bounded_proposal",
            "approved_target": target,
            "formalization": payload["formalization"],
            "semantic_alignment": payload["semantic_alignment"],
            "accepted_premises": premises,
            "open_obligations": obligations,
            "verification_policy": {"policy_version": POLICY_VERSION, "model_outputs_are_proposals": True, "models_cannot_award_warrants": True},
        }, referenced

    def _verifier_context(
        self, dossier: ResearchDossier, proposal: ProposalRecord, candidate: dict[str, object],
    ) -> tuple[dict[str, object], tuple[OpaqueId, ...], tuple[OpaqueId, ...]]:
        payload = export_dossier_dict(dossier)
        target_id = dossier.formalization.target_claim_id
        target = next(item for item in payload["claims"] if item["id"] == target_id.value)
        premise_ids = set(dossier.formalization.assumption_claim_ids)
        premises = [item for item in payload["claims"] if item["id"] in {value.value for value in premise_ids}]
        accepted_evidence = [item for item in payload["evidence"] if item["disposition"] == Disposition.ACCEPTED.value]
        included_set = {
            target_id, dossier.formalization.id, dossier.semantic_alignment.id,
            proposal.proposal_id, *premise_ids,
            *(item.id for item in dossier.evidence if item.disposition is Disposition.ACCEPTED),
        }
        all_ids = self._dossier_entity_ids(dossier)
        proposer_call_id = OpaqueId(proposal.source_id)
        excluded_set = (all_ids - included_set) | {proposer_call_id}
        included = tuple(sorted(included_set, key=lambda item: item.value))
        excluded = tuple(sorted(excluded_set, key=lambda item: item.value))
        context = {
            "schema_version": PHASE2_SCHEMA_VERSION,
            "purpose": "isolated_verification",
            "approved_target": target,
            "formalization": payload["formalization"],
            "semantic_alignment": payload["semantic_alignment"],
            "accepted_premises": premises,
            "raw_evidence_and_source_spans": accepted_evidence,
            "candidate": {"proposal_id": proposal.proposal_id.value, "artifact_hash": proposal.artifact_hash, **candidate},
            "verification_policy": {
                "policy_version": POLICY_VERSION,
                "allowed_result": "finding_only",
                "models_cannot_award_warrants": True,
                "manual_review_required_for_acceptance": True,
            },
        }
        return context, included, excluded

    @staticmethod
    def _dossier_entity_ids(dossier: ResearchDossier) -> set[OpaqueId]:
        values: list[Entity] = [
            dossier.problem, dossier.formalization, dossier.semantic_alignment,
            *dossier.claims, *dossier.warrants, *dossier.evidence,
            *dossier.source_applicability, *dossier.obligations,
            *dossier.representation_maps, *dossier.verification_records,
            dossier.evaluation_protocol, *dossier.audit_events,
        ]
        return {item.id for item in values}

    @staticmethod
    def _validate_target_and_refs(output: dict[str, object], dossier: ResearchDossier, expected_hash: str | None) -> None:
        if output.get("target_claim_id") != dossier.formalization.target_claim_id.value:
            raise StructuredOutputError("model output targets a different claim")
        if expected_hash is not None and output.get("candidate_artifact_hash") != expected_hash:
            raise StructuredOutputError("verifier output targets a different candidate artifact")
        known = {item.value for item in BaselineResearchLoop._dossier_entity_ids(dossier)}
        references: list[str] = []
        if "referenced_entity_ids" in output:
            references.extend(output["referenced_entity_ids"])  # type: ignore[arg-type]
        for finding in output.get("findings", []):  # type: ignore[union-attr]
            references.extend(finding["referenced_entity_ids"])
        if not set(references).issubset(known):
            raise StructuredOutputError("model output references unknown entity IDs")

    @staticmethod
    def _zero_usage():
        from .records import ModelUsage
        return ModelUsage(input_tokens=0, output_tokens=0, total_tokens=0, usage_source="unavailable")

    def _now(self) -> str:
        value = self.now().astimezone(timezone.utc)
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _after(self, milliseconds: int) -> str:
        value = self.now().astimezone(timezone.utc) + timedelta(milliseconds=milliseconds)
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def deterministic_candidate(target_claim_id: str, premise_id: str) -> dict[str, object]:
    return {
        "schema_version": PHASE2_SCHEMA_VERSION,
        "result_type": "proof_attempt",
        "target_claim_id": target_claim_id,
        "mathematical_payload": {
            "statement": "Let a=2k and b=2l; then a+b=2(k+l), so a+b is even.",
            "steps": ["Expand both even integers by the accepted definition.", "Factor 2 from their sum."],
            "witness": "k+l",
        },
        "declared_rationale": "Direct use of the accepted definition of even.",
        "referenced_entity_ids": [premise_id],
    }


def deterministic_fake_results(target_claim_id: str, premise_id: str) -> tuple[ModelResult, ModelResult]:
    from .records import ModelUsage
    proposer_value = deterministic_candidate(target_claim_id, premise_id)
    candidate = {key: value for key, value in proposer_value.items() if key != "declared_rationale"}
    candidate_hash = sha256_bytes(canonical_bytes(candidate))
    verifier_value = {
        "schema_version": PHASE2_SCHEMA_VERSION,
        "result_type": "finding",
        "target_claim_id": target_claim_id,
        "candidate_artifact_hash": candidate_hash,
        "findings": [{
            "code": "derivation_checks_out",
            "outcome": "supports",
            "detail": "Each displayed algebraic step follows from the accepted definition, subject to manual trust review.",
            "referenced_entity_ids": [premise_id],
        }],
        "declared_rationale": "The isolated candidate is internally consistent with the supplied premise.",
        "recommendation": "manual_review",
    }
    common = {
        "status": ModelResultStatus.SUCCEEDED,
        "provider": "scripted",
        "model_identifier": "scripted-v1",
        "capabilities": ("structured_output", "deterministic"),
        "refusal": None,
        "retry_classification": "none",
    }
    return (
        ModelResult(**common, structured_output=canonical_json(proposer_value), declared_rationale=proposer_value["declared_rationale"], usage=ModelUsage(input_tokens=120, output_tokens=80, total_tokens=200, usage_source="fixture")),
        ModelResult(**common, structured_output=canonical_json(verifier_value), declared_rationale=verifier_value["declared_rationale"], usage=ModelUsage(input_tokens=160, output_tokens=90, total_tokens=250, usage_source="fixture")),
    )
