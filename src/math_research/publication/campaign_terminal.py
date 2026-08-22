"""Deterministic terminal-status publication projection for campaigns.

This is deliberately a status manuscript, not a mathematical result manuscript.
The campaign export does not yet carry the typed claims, citations, formal
attestations, and applicability records required to promote mathematical prose.
Consequently this adapter emits no claims, records one open formalization
obligation, and leaves publication approval, novelty, and significance unset.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from ..campaign import CampaignExport, export_campaign_bytes
from .bundle import build_bundle, verify_bundle, write_bundle
from .errors import PublicationValidationError
from .manuscript import load_manuscript
from .serialization import canonical_bytes


REPORT_DIRECTORY = "publication-draft"
REPORT_STATUS_FILE = "publication-draft.json"


def _identifier(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}.{digest}"


def _usd(microusd: int) -> str:
    whole, fraction = divmod(microusd, 1_000_000)
    return str(whole) if fraction == 0 else f"{whole}.{fraction:06d}".rstrip("0")


def _models(export: CampaignExport) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}
    for call in export.model_calls:
        key = (call.provider, call.model_identifier)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return [{
            "provider": "none", "model": "none", "calls": 0,
            "outcome": "no model calls recorded",
        }]
    return [
        {
            "provider": provider,
            "model": model,
            "calls": calls,
            "outcome": "recorded in the verified campaign export",
        }
        for (provider, model), calls in sorted(counts.items())
    ]


def campaign_status_manuscript(
    export: CampaignExport,
    facts: Mapping[str, Any],
    configuration: Any,
) -> Mapping[str, Any]:
    """Derive a claim-free, visibly unapproved manuscript from campaign records."""

    usage = export.usage
    terminal_action = str(facts.get("terminal_action_type", "unknown"))
    manuscript_id = _identifier("ms.campaign-status", export.content_hash)
    run_id = _identifier("run.campaign-status", export.campaign_id)
    obligation_id = "obl.campaign-terminal-review"
    return {
        "schema_version": "1.4.0",
        "manuscript_id": manuscript_id,
        "title_stem": "Campaign terminal status",
        "authors": [{"name": "AdaIvy project", "role": "automated status projection"}],
        "abstract": (
            "This unapproved draft records that a bounded campaign stopped. "
            "It creates no mathematical warrant and leaves interpretation of "
            "the recorded work open."
        ),
        "corpus_provenance": "project_authored",
        "novelty": {"status": "not_assessed", "inferred_from_warrant": False},
        "significance": {"status": "not_assessed", "inferred_from_warrant": False},
        "publication_approval": None,
        "run_disclosure": {
            "run_id": run_id,
            "usage_scope": "verified campaign terminal ledger",
            "measurement_status": export.measurement_status,
            "models": _models(export),
            "model_calls": int(usage["requests_attempted"]),
            "cost_usd": _usd(int(usage["estimated_cost_microusd"])),
            "budget_cap_usd": _usd(int(configuration.max_cost_microusd)),
            "input_tokens": int(usage["input_tokens"]),
            "output_tokens": int(usage["output_tokens"]),
            "total_tokens": int(usage["total_tokens"]),
            "note": (
                "Usage and estimated cost are derived from the campaign export. "
                "They are not billed-spend assertions."
            ),
        },
        "toolchain": {
            "elan_version": "not-invoked",
            "lean_version": "not-invoked",
            "lean_commit": "0" * 40,
            "mathlib_version": "not-invoked",
            "mathlib_commit": "0" * 40,
        },
        "sources": [],
        "citations": [],
        "attestations": [],
        "certificates": [],
        "claims": [],
        "obligations": [{
            "obligation_id": obligation_id,
            "statement": (
                "Convert any material mathematical candidate in the campaign ledger "
                "into typed claims with source, applicability, and verification records "
                "before treating it as a mathematical report."
            ),
            "status": "open",
            "reason": (
                f"The terminal action is {terminal_action}. The campaign export does not "
                "itself contain a publication-ready typed mathematical claim."
            ),
            "tags": ["formalization"],
        }],
        "conventions": [],
        "verdict_matrices": [],
        "counter_candidate_replays": [],
        "prior_art_engagement": None,
        "novelty_rechecks": [],
        "sections": [{
            "section_id": "sec.campaign-terminal-status",
            "title": "Campaign status",
            "blocks": [{
                "block_id": "blk.campaign-terminal-status",
                "kind": "prose",
                "record_refs": [obligation_id],
                "runs": [{
                    "t": "text",
                    "v": (
                        "The campaign reached a terminal state. The attached campaign "
                        "records preserve its actions, artifacts, usage, and unresolved "
                        "work. This draft remains unapproved and creates no mathematical "
                        "warrant."
                    ),
                }],
                "citations": [],
            }],
        }],
        "render_probes": [{
            "probe_id": "pr.campaign-status.abstract-overclaim",
            "field": "abstract",
            "value": "This report proves the target conjecture.",
            "expected_outcome": "refusal",
            "expected": {"code": "abstract_overclaims_evidence"},
            "rationale": "A status-only draft must refuse unsupported resolution language.",
        }],
    }


def finalize_campaign_report(
    root: Path,
    export: CampaignExport,
    facts: Mapping[str, Any],
    configuration: Any,
) -> Mapping[str, Any]:
    """Create or verify the deterministic terminal report without external work."""

    manuscript = load_manuscript(campaign_status_manuscript(export, facts, configuration))
    record_files = {
        "records/campaign.json": export_campaign_bytes(export),
        "records/campaign-facts.json": canonical_bytes(facts) + b"\n",
    }
    expected = build_bundle(manuscript, record_files=record_files)
    output = root / REPORT_DIRECTORY
    if output.exists():
        if not output.is_dir():
            raise PublicationValidationError(
                "campaign_report_path_not_directory", str(output)
            )
        actual = verify_bundle(output)
        if actual["manuscript_hash"] != expected.manifest["manuscript_hash"]:
            raise PublicationValidationError(
                "campaign_report_mismatch",
                "the existing report was not derived from this campaign ledger",
            )
        if (
            (output / "records/campaign.json").read_bytes()
            != record_files["records/campaign.json"]
            or (output / "records/campaign-facts.json").read_bytes()
            != record_files["records/campaign-facts.json"]
        ):
            raise PublicationValidationError(
                "campaign_report_record_mismatch",
                "the existing report embeds different campaign records",
            )
        status = "verified_existing"
        manifest = actual
    else:
        root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".publication-draft-", dir=root))
        try:
            write_bundle(expected, temporary)
            verify_bundle(temporary)
            temporary.replace(output)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        status = "written"
        manifest = expected.manifest
    return {
        "schema_version": "adaivy.campaign-terminal-report.v1",
        "status": status,
        "campaign_id": export.campaign_id,
        "campaign_content_hash": export.content_hash,
        "path": str(output),
        "bundle_hash": manifest["bundle_hash"],
        "manuscript_hash": manifest["manuscript_hash"],
        "typeset_status": manifest["typeset_status"],
        "pdf_sha256": manifest["pdf_sha256"],
        "typeset_reason": (
            "The automatic campaign finalizer emits the complete LaTeX bundle without "
            "starting a subprocess. PDF compilation remains the explicit pinned "
            "publication typeset gate."
        ),
        "publication_approval": None,
        "epistemic_warrant_created": False,
    }


__all__ = [
    "REPORT_DIRECTORY", "REPORT_STATUS_FILE", "campaign_status_manuscript",
    "finalize_campaign_report",
]
