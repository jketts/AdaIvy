"""One-shot production of a complete AdaIvy publication report.

The manuscript records are the input, ``paper.tex`` is their deterministic
projection, every solved claim emits a linked Lean source, and ``paper.pdf`` is
compiled by the pinned reproducible typesetter.  This is the only supported
one-shot path for a reader-facing solved-result report.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from ..campaign import CampaignExport, export_campaign_bytes, verify_campaign_export
from .bundle import build_bundle, verify_bundle, write_bundle
from .campaign import apply_campaign_projection, bridge_campaign_to_publication
from .errors import PublicationValidationError
from .manuscript import Manuscript
from .serialization import canonical_bytes
from .typeset import toolchain_status, typeset_bundle


def produce_publication(
    manuscript: Manuscript,
    output_dir: Path,
    toolchain: Mapping[str, Any],
    *,
    campaign_value: Any | None = None,
    campaign_link: Any | None = None,
) -> dict[str, Any]:
    """Project and typeset one complete publication bundle, or fail closed."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise PublicationValidationError(
            "publication_output_not_empty",
            f"{output_dir} is not empty; use a fresh output directory",
        )
    status = toolchain_status(toolchain)
    if not status.available:
        raise PublicationValidationError("typeset_toolchain_absent", status.reason)

    ai_claims = [
        claim_id for claim_id, claim in manuscript.claims.items()
        if claim["authorship"]["ai_generated"] is True
    ]
    if ai_claims and (campaign_value is None or campaign_link is None):
        raise PublicationValidationError(
            "publication_campaign_provenance_required",
            "AI-authored claims require a verified campaign export and publication link: "
            + ", ".join(sorted(ai_claims)),
        )
    if (campaign_value is None) != (campaign_link is None):
        raise PublicationValidationError(
            "publication_campaign_inputs_incomplete",
            "campaign export and publication link must be supplied together",
        )
    campaign_records: dict[str, bytes] = {}
    if campaign_value is not None and campaign_link is not None:
        projection = bridge_campaign_to_publication(
            manuscript, campaign_value, campaign_link,
        )
        manuscript = apply_campaign_projection(manuscript, projection)
        verified_campaign = (
            verify_campaign_export(export_campaign_bytes(campaign_value))
            if isinstance(campaign_value, CampaignExport)
            else verify_campaign_export(campaign_value)
        )
        link_record = asdict(campaign_link) if is_dataclass(campaign_link) else campaign_link
        campaign_records = {
            "records/campaign.json": export_campaign_bytes(verified_campaign),
            "records/publication-campaign-link.json": canonical_bytes(link_record) + b"\n",
        }

    bundle = build_bundle(
        manuscript, toolchain=toolchain, record_files=campaign_records,
    )
    if bundle.manifest["probes_total"] < 1:
        raise PublicationValidationError(
            "publication_has_no_falsifiability_probe",
            "automatic publication requires at least one manuscript mutation probe",
        )
    write_bundle(bundle, output_dir)
    result = typeset_bundle(output_dir, toolchain)
    verified = verify_bundle(output_dir)
    if result["bundle_hash"] != verified["bundle_hash"]:
        raise PublicationValidationError(
            "publication_post_typeset_verification_failed",
            "typeset result and independently verified manifest disagree",
        )
    required = {"paper.tex", "paper.pdf", "MANIFEST.json", "build.json"}
    missing = sorted(name for name in required if not (output_dir / name).is_file())
    if missing:
        raise PublicationValidationError(
            "publication_artifact_missing", f"automatic publication omitted {missing}",
        )
    return verified
