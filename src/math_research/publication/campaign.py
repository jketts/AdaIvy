"""Fail-closed bridge from campaign provenance to publication claims.

The publication manuscript is not evidence that AdaIvy performed the research
described by it.  This module joins each claim and certificate to the immutable
actions and artifacts in a verified campaign export.  It also derives, rather
than accepts, contribution attribution and reader-facing usage disclosure.

This module intentionally does not change mathematical evidence classes.  An
externally originated counterexample can still be exactly verified; it simply
cannot be represented as an AdaIvy discovery or as completely accounted AdaIvy
spend.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from typing import Any, Mapping

from ..campaign import (
    ActorType,
    CampaignExport,
    ExternalOrigin,
    ImportRecord,
    ModelCallRecord,
    RecordStatus,
    ToolRunRecord,
    verify_campaign_export,
)
from .errors import PublicationValidationError
from .manuscript import load_manuscript
from .serialization import canonical_hash


LINK_SCHEMA_VERSION = "adaivy.publication-campaign-link.v1"
AUTHORSHIP_KINDS = frozenset({"adaivy_campaign", "external_codex", "human", "mixed"})
_HASH_FIELDS = frozenset({"campaign_content_hash", "campaign_operational_hash"})


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimContribution:
    """The complete material lineage used to author one publication claim."""

    claim_id: str
    discovery_action_ids: tuple[str, ...]
    contribution_action_ids: tuple[str, ...]
    artifact_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CertificateContribution:
    """One manuscript certificate bound to its producing campaign action."""

    certificate_id: str
    action_id: str
    artifact_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicationCampaignLink:
    schema_version: str
    campaign_id: str
    campaign_content_hash: str
    campaign_operational_hash: str
    claims: tuple[ClaimContribution, ...]
    certificates: tuple[CertificateContribution, ...]
    content_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicationCampaignProjection:
    """Validated data safe for a renderer to consume without free-text claims."""

    campaign_id: str
    campaign_content_hash: str
    campaign_operational_hash: str
    claim_authorship: Mapping[str, str]
    adaivy_attribution_allowed: Mapping[str, bool]
    disclosure: Mapping[str, Any]
    link_hash: str


def _public(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _public(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _public(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_public(item) for item in value]
    return value


def _hash(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise PublicationValidationError("campaign_hash_malformed", field)
    return value


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PublicationValidationError("campaign_identifier_malformed", field)
    return value


def _unique_strings(value: object, field: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise PublicationValidationError("campaign_link_field_invalid", field)
    result = tuple(value)
    if nonempty and not result:
        raise PublicationValidationError("campaign_contribution_empty", field)
    if len(result) != len(set(result)):
        raise PublicationValidationError("campaign_contribution_duplicate", field)
    return result


def _link_preimage(link: PublicationCampaignLink) -> dict[str, Any]:
    value = _public(link)
    value["content_hash"] = None
    return value


def build_publication_campaign_link(
    campaign: CampaignExport,
    *,
    claims: tuple[ClaimContribution, ...],
    certificates: tuple[CertificateContribution, ...],
) -> PublicationCampaignLink:
    """Create a content-hashed link; semantic validation occurs in the bridge."""

    link = PublicationCampaignLink(
        schema_version=LINK_SCHEMA_VERSION,
        campaign_id=campaign.campaign_id,
        campaign_content_hash=campaign.content_hash,
        campaign_operational_hash=campaign.operational_hash,
        claims=claims,
        certificates=certificates,
        content_hash="",
    )
    return replace(link, content_hash=canonical_hash(_link_preimage(link)))


def _parse_link(value: PublicationCampaignLink | Mapping[str, Any]) -> PublicationCampaignLink:
    if isinstance(value, PublicationCampaignLink):
        link = value
    else:
        required = {
            "schema_version", "campaign_id", "campaign_content_hash",
            "campaign_operational_hash", "claims", "certificates", "content_hash",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise PublicationValidationError(
                "campaign_link_schema_mismatch", "publication campaign link fields differ",
            )
        raw_claims = value["claims"]
        raw_certificates = value["certificates"]
        if not isinstance(raw_claims, list) or not isinstance(raw_certificates, list):
            raise PublicationValidationError(
                "campaign_link_field_invalid", "claims and certificates must be arrays",
            )
        claims: list[ClaimContribution] = []
        for index, item in enumerate(raw_claims):
            field = f"campaign_link.claims[{index}]"
            if not isinstance(item, Mapping) or set(item) != {
                "claim_id", "discovery_action_ids", "contribution_action_ids", "artifact_hashes",
            }:
                raise PublicationValidationError("campaign_link_schema_mismatch", field)
            claims.append(ClaimContribution(
                claim_id=_identifier(item["claim_id"], f"{field}.claim_id"),
                discovery_action_ids=_unique_strings(
                    item["discovery_action_ids"], f"{field}.discovery_action_ids", nonempty=True,
                ),
                contribution_action_ids=_unique_strings(
                    item["contribution_action_ids"], f"{field}.contribution_action_ids", nonempty=True,
                ),
                artifact_hashes=_unique_strings(
                    item["artifact_hashes"], f"{field}.artifact_hashes", nonempty=True,
                ),
            ))
        certificates: list[CertificateContribution] = []
        for index, item in enumerate(raw_certificates):
            field = f"campaign_link.certificates[{index}]"
            if not isinstance(item, Mapping) or set(item) != {
                "certificate_id", "action_id", "artifact_hash",
            }:
                raise PublicationValidationError("campaign_link_schema_mismatch", field)
            certificates.append(CertificateContribution(
                certificate_id=_identifier(item["certificate_id"], f"{field}.certificate_id"),
                action_id=_identifier(item["action_id"], f"{field}.action_id"),
                artifact_hash=_hash(item["artifact_hash"], f"{field}.artifact_hash"),
            ))
        link = PublicationCampaignLink(
            schema_version=str(value["schema_version"]),
            campaign_id=_identifier(value["campaign_id"], "campaign_link.campaign_id"),
            campaign_content_hash=_hash(
                value["campaign_content_hash"], "campaign_link.campaign_content_hash",
            ),
            campaign_operational_hash=_hash(
                value["campaign_operational_hash"], "campaign_link.campaign_operational_hash",
            ),
            claims=tuple(claims),
            certificates=tuple(certificates),
            content_hash=_hash(value["content_hash"], "campaign_link.content_hash"),
        )
    if link.schema_version != LINK_SCHEMA_VERSION:
        raise PublicationValidationError(
            "campaign_link_schema_unsupported", f"schema_version={link.schema_version!r}",
        )
    for field in _HASH_FIELDS:
        _hash(getattr(link, field), f"campaign_link.{field}")
    for index, claim in enumerate(link.claims):
        field = f"campaign_link.claims[{index}]"
        _identifier(claim.claim_id, f"{field}.claim_id")
        _unique_strings(claim.discovery_action_ids, f"{field}.discovery_action_ids", nonempty=True)
        _unique_strings(
            claim.contribution_action_ids, f"{field}.contribution_action_ids", nonempty=True,
        )
        for artifact_hash in _unique_strings(
            claim.artifact_hashes, f"{field}.artifact_hashes", nonempty=True,
        ):
            _hash(artifact_hash, f"{field}.artifact_hashes")
    for index, certificate in enumerate(link.certificates):
        field = f"campaign_link.certificates[{index}]"
        _identifier(certificate.certificate_id, f"{field}.certificate_id")
        _identifier(certificate.action_id, f"{field}.action_id")
        _hash(certificate.artifact_hash, f"{field}.artifact_hash")
    _hash(link.content_hash, "campaign_link.content_hash")
    if canonical_hash(_link_preimage(link)) != link.content_hash:
        raise PublicationValidationError("campaign_link_hash_mismatch", "campaign link was edited")
    return link


def _verified_campaign(value: CampaignExport | bytes | str | Mapping[str, Any]) -> CampaignExport:
    try:
        # verify_campaign_export deliberately accepts serialized/mapping input.
        # Re-serialize an already parsed object so its hashes and all closure
        # invariants are checked again at the publication boundary.
        if isinstance(value, CampaignExport):
            value = _public(value)
        return verify_campaign_export(value)
    except Exception as error:
        raise PublicationValidationError(
            "campaign_export_invalid", f"campaign provenance did not verify: {error}",
        ) from error


def _manuscript_collections(manuscript: Any) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if hasattr(manuscript, "claims") and hasattr(manuscript, "certificates"):
        return dict(manuscript.claims), dict(manuscript.certificates)
    if not isinstance(manuscript, Mapping):
        raise PublicationValidationError("campaign_manuscript_invalid", "manuscript is not a mapping")

    def indexed(key: str, id_field: str) -> dict[str, Mapping[str, Any]]:
        rows = manuscript.get(key)
        if not isinstance(rows, list) or any(not isinstance(item, Mapping) for item in rows):
            raise PublicationValidationError("campaign_manuscript_invalid", key)
        result = {str(item.get(id_field, "")): item for item in rows}
        if "" in result or len(result) != len(rows):
            raise PublicationValidationError("campaign_manuscript_invalid", key)
        return result

    return indexed("claims", "claim_id"), indexed("certificates", "certificate_id")


def _ancestor_closure(action_ids: tuple[str, ...], actions: Mapping[str, Any]) -> set[str]:
    pending = list(action_ids)
    result: set[str] = set()
    while pending:
        action_id = pending.pop()
        if action_id in result:
            continue
        action = actions.get(action_id)
        if action is None:
            raise PublicationValidationError(
                "campaign_action_unresolved", f"action {action_id!r} is not in the campaign",
            )
        result.add(action_id)
        pending.extend(action.parent_action_ids)
    return result


def _derive_authorship(action_ids: tuple[str, ...], campaign: CampaignExport) -> str:
    actions = {item.action_id: item for item in campaign.actions}
    imports: dict[str, list[ImportRecord]] = {}
    for item in campaign.imports:
        imports.setdefault(item.action_id, []).append(item)
    origins: set[str] = set()
    for action_id in _ancestor_closure(action_ids, actions):
        action = actions[action_id]
        imported = imports.get(action_id, ())
        if imported:
            for item in imported:
                if item.origin_type is ExternalOrigin.EXTERNAL_CODEX:
                    origins.add("external_codex")
                elif item.origin_type is ExternalOrigin.HUMAN:
                    origins.add("human")
                else:
                    origins.add("other_external")
        elif action.actor_type is ActorType.HUMAN:
            origins.add("human")
        elif action.actor_type is ActorType.EXTERNAL_SYSTEM:
            origins.add("other_external")
        else:
            origins.add("adaivy_campaign")
    if origins == {"adaivy_campaign"}:
        return "adaivy_campaign"
    if origins == {"external_codex"}:
        return "external_codex"
    if origins == {"human"}:
        return "human"
    return "mixed"


def _usd(microusd: int) -> str:
    whole, fraction = divmod(microusd, 1_000_000)
    return str(whole) if fraction == 0 else f"{whole}.{fraction:06d}".rstrip("0")


def _disclosure(campaign: CampaignExport, origins: Mapping[str, str]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for call in campaign.model_calls:
        key = (call.provider, call.model_identifier)
        row = grouped.setdefault(key, {
            "provider": call.provider,
            "model": call.model_identifier,
            "requests_attempted": 0,
            "responses_completed": 0,
            "responses_failed": 0,
            "responses_incomplete": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_microusd": 0,
        })
        row["requests_attempted"] += 1
        row[f"responses_{call.status.value}"] += 1
        row["input_tokens"] += call.input_tokens
        row["output_tokens"] += call.output_tokens
        row["estimated_cost_microusd"] += call.estimated_cost_microusd or 0
    models = []
    for key in sorted(grouped):
        row = grouped[key]
        row["total_tokens"] = row["input_tokens"] + row["output_tokens"]
        row["estimated_cost_usd"] = _usd(row["estimated_cost_microusd"])
        models.append(row)

    usage = dict(campaign.usage)
    estimated = int(usage["estimated_cost_microusd"])
    status = campaign.measurement_status
    if status == "complete":
        note = (
            "Accounting is complete for the provenance-closed campaign. Monetary cost is "
            "an estimate from recorded usage and pinned pricing, not provider-billed spend."
        )
    elif status == "partial":
        note = (
            "Recorded subset only: total campaign usage and cost are unknown. The displayed "
            "amount is an estimate for measured records, not complete or provider-billed spend."
        )
    else:
        note = "Campaign usage and total cost are unavailable; no complete spend is reported."
    return {
        "campaign_id": campaign.campaign_id,
        "campaign_content_hash": campaign.content_hash,
        "campaign_operational_hash": campaign.operational_hash,
        "measurement_status": status,
        "accounting_complete": status == "complete",
        "attribution_status": campaign.attribution_status,
        "claim_authorship": dict(sorted(origins.items())),
        "models": models,
        "live_configuration_hashes": sorted({
            item.live_configuration_hash for item in campaign.model_calls
        }),
        "pricing_snapshot_hashes": sorted({
            item.pricing_snapshot_hash for item in campaign.model_calls
        }),
        **usage,
        "estimated_cost_usd": _usd(estimated),
        "cost_kind": "estimated_not_billed",
        "note": note,
    }


def bridge_campaign_to_publication(
    manuscript: Any,
    campaign_value: CampaignExport | bytes | str | Mapping[str, Any],
    link_value: PublicationCampaignLink | Mapping[str, Any],
) -> PublicationCampaignProjection:
    """Validate campaign lineage and derive safe attribution/accounting.

    Every manuscript claim and certificate must occur exactly once in the link.
    All linked actions must have completed and every linked artifact must be an
    output of a linked action.  Certificate hashes additionally have to resolve
    to a completed tool run.  A manuscript may claim the AdaIvy project as the
    generator only when discovery is internal and campaign accounting is closed.
    """

    campaign = _verified_campaign(campaign_value)
    link = _parse_link(link_value)
    if (
        link.campaign_id != campaign.campaign_id
        or link.campaign_content_hash != campaign.content_hash
        or link.campaign_operational_hash != campaign.operational_hash
    ):
        raise PublicationValidationError(
            "campaign_link_identity_mismatch", "link does not bind the verified campaign export",
        )
    claims, certificates = _manuscript_collections(manuscript)
    claim_links = {item.claim_id: item for item in link.claims}
    certificate_links = {item.certificate_id: item for item in link.certificates}
    if len(claim_links) != len(link.claims) or set(claim_links) != set(claims):
        raise PublicationValidationError(
            "campaign_claim_coverage_incomplete", "every manuscript claim must have one campaign link",
        )
    if len(certificate_links) != len(link.certificates) or set(certificate_links) != set(certificates):
        raise PublicationValidationError(
            "campaign_certificate_coverage_incomplete",
            "every manuscript certificate must have one campaign link",
        )

    actions = {item.action_id: item for item in campaign.actions}
    tool_runs: dict[str, list[ToolRunRecord]] = {}
    for item in campaign.tool_runs:
        tool_runs.setdefault(item.action_id, []).append(item)
    origins: dict[str, str] = {}
    for claim_id, contribution in claim_links.items():
        if not set(contribution.discovery_action_ids).issubset(contribution.contribution_action_ids):
            raise PublicationValidationError(
                "campaign_discovery_not_material", f"claim {claim_id} discovery is outside contributions",
            )
        contribution_actions = [actions.get(item) for item in contribution.contribution_action_ids]
        if any(action is None for action in contribution_actions):
            raise PublicationValidationError("campaign_action_unresolved", f"claim {claim_id}")
        if any(action.status is not RecordStatus.COMPLETED for action in contribution_actions if action):
            raise PublicationValidationError(
                "campaign_contribution_not_completed", f"claim {claim_id}",
            )
        produced = {
            artifact
            for action in contribution_actions if action is not None
            for artifact in action.output_artifact_hashes
        }
        if not contribution.artifact_hashes or not set(contribution.artifact_hashes).issubset(produced):
            raise PublicationValidationError(
                "campaign_artifact_unresolved", f"claim {claim_id} has an unproduced artifact",
            )
        for action in contribution_actions:
            assert action is not None
            if not set(action.output_artifact_hashes).intersection(contribution.artifact_hashes):
                raise PublicationValidationError(
                    "campaign_action_not_material", f"claim {claim_id} links action {action.action_id}",
                )
        origins[claim_id] = _derive_authorship(contribution.discovery_action_ids, campaign)

    for certificate_id, contribution in certificate_links.items():
        certificate = certificates[certificate_id]
        action = actions.get(contribution.action_id)
        tools = tool_runs.get(contribution.action_id, ())
        if action is None or action.status is not RecordStatus.COMPLETED:
            raise PublicationValidationError(
                "campaign_certificate_action_unresolved", f"certificate {certificate_id}",
            )
        matching_tools = [
            tool for tool in tools
            if tool.status is RecordStatus.COMPLETED
            and tool.result_hash == contribution.artifact_hash
        ]
        if not matching_tools:
            raise PublicationValidationError(
                "campaign_certificate_without_tool_run", f"certificate {certificate_id}",
            )
        if (
            certificate.get("run_id") != campaign.campaign_id
            or certificate.get("result_hash") != contribution.artifact_hash
            or contribution.artifact_hash not in action.output_artifact_hashes
        ):
            raise PublicationValidationError(
                "campaign_certificate_lineage_mismatch", f"certificate {certificate_id}",
            )
        linked_claims = [
            item for item in claims.values() if item.get("certificate_id") == certificate_id
        ]
        if not linked_claims:
            raise PublicationValidationError(
                "campaign_certificate_orphaned", f"certificate {certificate_id}",
            )
        for claim in linked_claims:
            claim_link = claim_links[str(claim["claim_id"])]
            if (
                contribution.action_id not in claim_link.contribution_action_ids
                or contribution.artifact_hash not in claim_link.artifact_hashes
            ):
                raise PublicationValidationError(
                    "campaign_certificate_not_in_claim_lineage", f"certificate {certificate_id}",
                )

    for claim_id, claim in claims.items():
        declared = claim.get("authorship")
        if not isinstance(declared, Mapping):
            raise PublicationValidationError("campaign_authorship_missing", f"claim {claim_id}")
        is_ai = declared.get("ai_generated") is True
        says_adaivy = is_ai and declared.get("generator") == "AdaIvy project"
        allowed = (
            origins[claim_id] == "adaivy_campaign"
            and campaign.attribution_status == "adaivy_campaign"
            and campaign.measurement_status == "complete"
        )
        if origins[claim_id] == "adaivy_campaign" and not allowed:
            raise PublicationValidationError(
                "adaivy_origin_requires_closed_campaign",
                f"claim {claim_id} has origin={origins[claim_id]}, "
                f"attribution={campaign.attribution_status}, measurement={campaign.measurement_status}",
            )
        if says_adaivy and origins[claim_id] != "adaivy_campaign":
            raise PublicationValidationError(
                "adaivy_origin_requires_closed_campaign",
                f"claim {claim_id} has origin={origins[claim_id]}",
            )
        if declared.get("ai_generated") is False and origins[claim_id] != "human":
            raise PublicationValidationError(
                "campaign_authorship_mismatch",
                f"claim {claim_id} is labelled human but derives from {origins[claim_id]}",
            )

    return PublicationCampaignProjection(
        campaign_id=campaign.campaign_id,
        campaign_content_hash=campaign.content_hash,
        campaign_operational_hash=campaign.operational_hash,
        claim_authorship=dict(sorted(origins.items())),
        adaivy_attribution_allowed={
            claim_id: (
                origin == "adaivy_campaign"
                and campaign.attribution_status == "adaivy_campaign"
                and campaign.measurement_status == "complete"
            )
            for claim_id, origin in sorted(origins.items())
        },
        disclosure=_disclosure(campaign, origins),
        link_hash=link.content_hash,
    )


def apply_campaign_projection(
    manuscript: Any,
    projection: PublicationCampaignProjection,
) -> Any:
    """Return a renderer-ready manuscript whose disclosure is campaign-derived.

    The source manuscript has already passed its closed structural validator.
    This function replaces only the two fields that ADR-0057 forbids authors to
    self-attest: result origin and run accounting.  The campaign/link hashes are
    carried in ``usage_scope`` and the resulting manuscript hash therefore binds
    the projection used to render it.
    """

    if not hasattr(manuscript, "value") or not hasattr(manuscript, "claims"):
        raise PublicationValidationError(
            "campaign_manuscript_invalid", "a validated Manuscript is required",
        )
    value = copy.deepcopy(dict(manuscript.value))
    origin_label = {
        "adaivy_campaign": (True, "AdaIvy project"),
        "external_codex": (True, "external Codex"),
        "mixed": (True, "mixed external and AdaIvy campaign"),
        "human": (False, "human"),
    }
    for claim in value["claims"]:
        claim_id = str(claim["claim_id"])
        origin = projection.claim_authorship[claim_id]
        ai_generated, generator = origin_label[origin]
        claim["authorship"] = {
            "ai_generated": ai_generated,
            "generator": generator,
        }

    disclosure = projection.disclosure
    complete = disclosure["measurement_status"] == "complete"
    available = disclosure["measurement_status"] != "unavailable"
    tool_summary = (
        f" Tool runs: {disclosure['tool_runs_attempted']} attempted, "
        f"{disclosure['tool_runs_completed']} completed, "
        f"{disclosure['tool_runs_failed']} failed, "
        f"{disclosure['tool_runs_incomplete']} incomplete."
    )
    value["run_disclosure"] = {
        "run_id": projection.campaign_id,
        "usage_scope": (
            "verified campaign export " + projection.campaign_content_hash
            + "; operational " + projection.campaign_operational_hash
            + "; publication link " + projection.link_hash
            + "; live configurations "
            + ",".join(disclosure["live_configuration_hashes"])
            + "; pricing snapshots "
            + ",".join(disclosure["pricing_snapshot_hashes"])
        ),
        "measurement_status": disclosure["measurement_status"],
        "models": [
            {
                "provider": row["provider"],
                "model": row["model"],
                # This legacy field now means requests attempted.  Renderer
                # wording and the outcome make that meaning explicit.
                "calls": row["requests_attempted"],
                "outcome": (
                    f"completed={row['responses_completed']}; "
                    f"failed={row['responses_failed']}; "
                    f"incomplete={row['responses_incomplete']}"
                ),
            }
            for row in disclosure["models"]
        ] or [{
            "provider": "none",
            "model": "none",
            "calls": 0,
            "outcome": "no model request recorded",
        }],
        "model_calls": disclosure["requests_attempted"] if available else None,
        "cost_usd": disclosure["estimated_cost_usd"] if available else None,
        # The current campaign export binds the configuration hash but does not
        # yet project a numeric cap.  Do not copy a manuscript-authored cap.
        "budget_cap_usd": None,
        "input_tokens": disclosure["input_tokens"] if available else None,
        "output_tokens": disclosure["output_tokens"] if available else None,
        "total_tokens": disclosure["total_tokens"] if available else None,
        "note": disclosure["note"] + tool_summary + (
            " Causal and operational closure verified."
            if complete else " Complete campaign spend is not claimed."
        ),
    }
    return load_manuscript(value)


__all__ = [
    "AUTHORSHIP_KINDS", "LINK_SCHEMA_VERSION", "CertificateContribution",
    "ClaimContribution", "PublicationCampaignLink", "PublicationCampaignProjection",
    "apply_campaign_projection", "bridge_campaign_to_publication",
    "build_publication_campaign_link",
]
