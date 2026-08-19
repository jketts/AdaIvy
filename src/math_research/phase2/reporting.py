"""Deterministic reports rebuilt from durable canonical state."""

from __future__ import annotations

from ..domain.entities import OpaqueId
from ..domain.policies import TrustPolicy
from .records import VerifierContextManifest
from .serialization import canonical_bytes, canonical_hash


def durable_report_data(workspace: object, run_id: OpaqueId) -> dict[str, object]:
    run = workspace.get_run(run_id)
    dossier = workspace.load_dossier(run.dossier_id)
    projection = TrustPolicy(dossier).target_resolution()
    jobs = workspace.list_jobs(run_id)
    proposals = workspace.list_proposals(run_id)
    budget = workspace.budget(run.budget_id, now=run.updated_at)
    timeline = workspace.timeline(run_id)
    calls = workspace.list_model_calls(run_id)
    estimates = workspace.list_cost_estimates(run_id)
    try:
        manifest: VerifierContextManifest | None = workspace.get_manifest(run_id)
    except KeyError:
        manifest = None
    return {
        "schema_version": "2.0.0",
        "run": run,
        "accepted_dossier": {
            "dossier_id": dossier.id,
            "content_hash": run.dossier_hash,
            "target_claim_id": projection.claim_id,
            "logical_status": projection.logical_status,
            "semantic_alignment_status": projection.semantic_alignment_status,
            "blockers": projection.blockers,
            "warrant_ids": [item.id for item in dossier.warrants],
            "evidence_ids": [item.id for item in dossier.evidence],
            "obligation_ids": [item.id for item in dossier.obligations],
        },
        "jobs": jobs,
        "budget": budget,
        "proposals": proposals,
        "verifier_context_manifest": manifest,
        "model_calls": calls,
        "cost_estimates": estimates,
        "audit_timeline": timeline,
        "audit_replay_hash": canonical_hash(timeline),
    }


def render_durable_report(workspace: object, run_id: OpaqueId) -> str:
    data = durable_report_data(workspace, run_id)
    run = data["run"]
    accepted = data["accepted_dossier"]
    proposals = data["proposals"]
    manifest = data["verifier_context_manifest"]
    lines = [
        "# Durable Phase 2 Traceable Report",
        "",
        f"- Run `{run.run_id}` is `{run.status.value}` for dossier `{run.dossier_id}` with canonical hash `{run.dossier_hash}`. [refs: {run.run_id}, {run.dossier_id}]",
        f"- The accepted target `{accepted['target_claim_id']}` remains policy-projected as `{accepted['logical_status']}`; model/backend output did not mutate it. [refs: {accepted['target_claim_id']} ]",
        f"- Durable state contains {len(proposals)} proposal-only artifacts and {len(data['jobs'])} jobs. [refs: {', '.join(item.proposal_id.value for item in proposals) or 'none'}]",
        f"- Audit replay hash is `{data['audit_replay_hash']}`. [refs: {run.run_id}]",
    ]
    if manifest is not None:
        lines.extend(
            [
                f"- Verifier context `{manifest.manifest_id}` has exact serialized hash `{manifest.serialized_context_hash}`. [refs: {manifest.manifest_id}]",
                f"- Verifier independence: context-isolated=`{str(manifest.independence.context_isolated).lower()}`, separate-call=`{str(manifest.independence.separate_model_call).lower()}`, different-model=`{str(manifest.independence.different_model).lower()}`, different-provider=`{str(manifest.independence.different_provider).lower()}`, fully-independent=`{str(manifest.independence.fully_independent).lower()}`. [refs: {manifest.manifest_id}]",
            ]
        )
    if data["cost_estimates"]:
        calls = data["model_calls"]
        lines.append(
            f"- API-reported usage totals {sum(item['total_tokens'] for item in calls)} tokens; estimated cost is {sum((item['estimated_cost_microusd'] or 0) for item in calls)} micro-USD, with every estimate linked to its pinned pricing snapshot. [refs: {', '.join(item['call_id'] for item in calls)}]"
        )
    lines.append("")
    return "\n".join(lines)


def report_hash(workspace: object, run_id: OpaqueId) -> str:
    from .serialization import sha256_bytes
    return sha256_bytes(render_durable_report(workspace, run_id).encode("utf-8"))
