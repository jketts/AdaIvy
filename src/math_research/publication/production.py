"""One-shot production of a complete AdaIvy publication report.

The manuscript records are the input, ``paper.tex`` is their deterministic
projection, every solved claim emits a linked Lean source, and ``paper.pdf`` is
compiled by the pinned reproducible typesetter.  This is the only supported
one-shot path for a reader-facing solved-result report.

This module is where the epistemic gates have teeth, because it is where a
reader-facing artifact comes into existence.  ADR-0055's novelty gate hangs off
``publication_approval``, which is null for every draft, so it had no effect on
the artifacts that actually circulate.  Amendment A4 moves the requirement here:
a resolution-typed claim needs a prior-art classification bound to this
manuscript before any bundle is written, and a publication needs at least one
falsifiability probe aimed at its reader-facing text.
"""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from ..campaign import CampaignExport, export_campaign_bytes, verify_campaign_export
from .bundle import build_bundle, verify_bundle, write_bundle
from .campaign import apply_campaign_projection, bridge_campaign_to_publication
from .errors import PublicationValidationError
from .manuscript import Manuscript, announcement_subject_hash
from .serialization import canonical_bytes
from .typeset import toolchain_status, typeset_bundle


#: A probe whose mutated field is reader-facing text. ADR-0058's whole finding is
#: that the title and abstract were the only strings in the projection with no
#: derivation and no probe, so an automatic publication must carry at least one
#: probe aimed at that surface. ``claims[...].prose_statement`` counts because
#: amendment B6 put claim prose on the same footing.
HEADLINE_PROBE_FIELDS = frozenset({"title_stem", "abstract"})
_CLAIM_TEXT_PROBE = re.compile(r"^claims\[[^\]]+\]\.(prose_statement|resolution_target)$")


def _headline_probe_present(manuscript: Manuscript) -> bool:
    for probe in manuscript.value["render_probes"]:
        field = str(probe["field"])
        if field in HEADLINE_PROBE_FIELDS or _CLAIM_TEXT_PROBE.match(field):
            return True
    return False


def _require_prior_art_classification(manuscript: Manuscript) -> None:
    """Amendment A4. The teeth move from the announcement act to the artifact.

    ADR-0055's novelty gate hangs off ``publication_approval``, which is null for
    every draft, so the two-checkpoint policy had no effect on any artifact that
    had not already reached human approval -- and drafts are what circulate. A
    resolution-typed claim therefore requires a prior-art classification here, at
    the point the reader-facing artifact is produced.

    Named boundary, not an oversight: this gate requires the re-check to be
    **bound to this manuscript's subject hash** and deliberately does *not*
    enforce ADR-0055's 24-hour freshness window. Freshness is a property of the
    announcement act. Re-enforcing it at render time would make yesterday's
    bundle unrebuildable and break ADR-0036's guarantee that a bundle is
    regenerable from ``records/`` alone. Subject binding is time-invariant, so it
    costs nothing and cannot expire. ``require_checkpoint`` is deliberately not
    wired into this path.
    """

    resolution_claims = manuscript.resolution_claim_ids()
    if not resolution_claims:
        return
    if manuscript.value["prior_art_engagement"] is None:
        raise PublicationValidationError(
            "resolution_claim_without_prior_art_classification",
            "claims " + ", ".join(resolution_claims) + " assert a resolution, so this "
            "artifact requires a recorded prior-art classification; an approval-time gate "
            "is inert on a draft, and drafts are what circulate",
        )
    recheck = manuscript.prior_art_recheck()
    if recheck is None:
        raise PublicationValidationError(
            "resolution_claim_without_prior_art_classification",
            "prior_art_engagement names a re-check this manuscript does not carry",
        )
    expected = announcement_subject_hash(manuscript)
    if recheck.subject_id != manuscript.manuscript_id or recheck.subject_hash != expected:
        raise PublicationValidationError(
            "prior_art_recheck_subject_mismatch",
            f"re-check {recheck.recheck_id} covers subject {recheck.subject_id!r} at "
            f"{recheck.subject_hash}, but this manuscript is {manuscript.manuscript_id} at "
            f"{expected}; a classification of some other statement classifies nothing here",
        )


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
    _require_prior_art_classification(manuscript)

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
    if not _headline_probe_present(manuscript):
        raise PublicationValidationError(
            "publication_has_no_headline_probe",
            "automatic publication requires at least one probe on reader-facing text "
            f"({sorted(HEADLINE_PROBE_FIELDS)} or a claim prose_statement/resolution_target); "
            "the shipped Graffiti 322 report had ten probes and none of them touched the "
            "title, which is why its headline out-claimed its own body",
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
