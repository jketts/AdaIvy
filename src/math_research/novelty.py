"""Content-bound novelty re-check records and lifecycle gates (ADR-0055).

A re-check records a bounded human literature-search act.  It is not a proof
of novelty and creates no mathematical warrant.  Freshness is structural: the
record is bound to the exact current subject and to the one action it permits.
It therefore cannot be reused after either the problem/result or action id
changes.

Finding prior art is not one undifferentiated outcome.  The record separately
states whether the earlier work is the same result, a stronger result, a weaker
result, merely overlapping, or unresolved; what kind of resolution it reports;
and whether AdaIvy independently verified that resolution.  The reader-facing
report classification is derived from those fields, never supplied as prose.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from .phase2.serialization import canonical_hash, canonical_json


SCHEMA_VERSION = "adaivy.novelty-recheck.v1"
POLICY_ID = "novelty-recheck-two-checkpoint-v1"
MAX_RECORD_BYTES = 65_536
MAX_FRESHNESS = timedelta(hours=24)
CHECKPOINTS = frozenset({"before_research", "before_announcement"})
OUTCOMES = frozenset({"prior_art_found", "not_found_under_protocol", "inconclusive"})
PRIOR_ART_RELATIONSHIPS = frozenset({
    "not_applicable", "same_result", "equivalent_result", "stronger_prior_result",
    "weaker_prior_result", "overlapping_result", "unresolved",
})
PRIOR_RESOLUTIONS = frozenset({
    "not_applicable", "proof", "refutation", "other_resolution", "unresolved",
})
PRIOR_RESOLUTION_VERIFICATIONS = frozenset({
    "not_applicable", "source_report_only", "independently_verified", "unresolved",
})
REPORT_CLASSIFICATIONS = frozenset({
    "no_prior_art_found_under_protocol", "prior_art_search_inconclusive",
    "reported_prior_resolution", "independent_verification",
    "extension_of_prior_result", "related_to_prior_result",
    "prior_art_relationship_unresolved",
})
TARGET_RESOLUTION_STATUSES = frozenset({
    "not_assessed", "reported_proved", "reported_refuted",
    "reported_resolved_other", "already_proved", "already_refuted",
    "already_resolved_other", "not_resolved_by_prior_result", "unresolved",
})

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


class NoveltyRecheckError(ValueError):
    """A novelty checkpoint is malformed, stale, or bound to another action."""


@dataclass(frozen=True, slots=True)
class PriorArtClassification:
    """Derived report role and target status; never a novelty or truth warrant."""

    report_classification: str
    target_resolution_status: str

    def payload(self) -> dict[str, str | bool]:
        return {
            "report_classification": self.report_classification,
            "target_resolution_status": self.target_resolution_status,
            "novelty_status": "not_assessed",
            "creates_mathematical_warrant": False,
        }


def classify_prior_art(
    *, outcome: str, relationship: str, prior_resolution: str,
    verification_status: str,
) -> PriorArtClassification:
    """Classify what a found source means for the research report.

    ``already_proved`` and ``already_refuted`` are reachable only when the
    earlier resolution is the same as, equivalent to, or stronger than the
    current result *and* AdaIvy independently verified it.  A source's own
    assertion yields only ``reported_*``.
    """

    if outcome not in OUTCOMES:
        raise NoveltyRecheckError("outcome_unknown")
    if relationship not in PRIOR_ART_RELATIONSHIPS:
        raise NoveltyRecheckError("prior_art_relationship_unknown")
    if prior_resolution not in PRIOR_RESOLUTIONS:
        raise NoveltyRecheckError("prior_resolution_unknown")
    if verification_status not in PRIOR_RESOLUTION_VERIFICATIONS:
        raise NoveltyRecheckError("prior_resolution_verification_unknown")

    if outcome == "not_found_under_protocol":
        if (relationship, prior_resolution, verification_status) != (
            "not_applicable", "not_applicable", "not_applicable"
        ):
            raise NoveltyRecheckError("prior_art_classification_inconsistent")
        return PriorArtClassification(
            "no_prior_art_found_under_protocol", "not_assessed"
        )
    if outcome == "inconclusive":
        if (relationship, prior_resolution, verification_status) != (
            "unresolved", "unresolved", "unresolved"
        ):
            raise NoveltyRecheckError("prior_art_classification_inconsistent")
        return PriorArtClassification("prior_art_search_inconclusive", "unresolved")

    # outcome == prior_art_found
    if relationship in {"not_applicable"} or prior_resolution == "not_applicable":
        raise NoveltyRecheckError("prior_art_classification_inconsistent")
    if relationship == "unresolved" or prior_resolution == "unresolved" \
            or verification_status == "unresolved":
        if relationship != "unresolved" or prior_resolution != "unresolved" \
                or verification_status != "unresolved":
            raise NoveltyRecheckError("prior_art_classification_inconsistent")
        return PriorArtClassification("prior_art_relationship_unresolved", "unresolved")
    if verification_status not in {"source_report_only", "independently_verified"}:
        raise NoveltyRecheckError("prior_art_classification_inconsistent")

    if relationship in {"weaker_prior_result"}:
        return PriorArtClassification(
            "extension_of_prior_result", "not_resolved_by_prior_result"
        )
    if relationship == "overlapping_result":
        return PriorArtClassification(
            "related_to_prior_result", "not_resolved_by_prior_result"
        )

    # Same, equivalent, or stronger prior results resolve the present target.
    if verification_status == "source_report_only":
        target = {
            "proof": "reported_proved",
            "refutation": "reported_refuted",
            "other_resolution": "reported_resolved_other",
        }[prior_resolution]
        return PriorArtClassification("reported_prior_resolution", target)
    target = {
        "proof": "already_proved",
        "refutation": "already_refuted",
        "other_resolution": "already_resolved_other",
    }[prior_resolution]
    return PriorArtClassification("independent_verification", target)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise NoveltyRecheckError(f"duplicate_field:{key}")
        value[key] = item
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\r" in value:
        raise NoveltyRecheckError(f"invalid_text:{field}")
    return value


def _identifier(value: Any, field: str) -> str:
    value = _text(value, field)
    if not _ID.fullmatch(value):
        raise NoveltyRecheckError(f"invalid_identifier:{field}")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise NoveltyRecheckError(f"invalid_hash:{field}")
    return value


def parse_instant(value: Any, field: str = "performed_at") -> datetime:
    value = _text(value, field)
    if not value.endswith("Z"):
        raise NoveltyRecheckError(f"instant_not_utc:{field}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise NoveltyRecheckError(f"instant_malformed:{field}") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise NoveltyRecheckError(f"instant_not_utc:{field}")
    return parsed


def _string_list(value: Any, field: str, *, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise NoveltyRecheckError(f"invalid_nonempty_list:{field}")
    items = tuple(_text(item, f"{field}[{index}]") for index, item in enumerate(value))
    if len(set(items)) != len(items):
        raise NoveltyRecheckError(f"duplicate_list_item:{field}")
    return items


@dataclass(frozen=True, slots=True, kw_only=True)
class NoveltyRecheck:
    recheck_id: str
    checkpoint: str
    subject_id: str
    subject_hash: str
    next_action_id: str
    performed_by: str
    performed_at: str
    protocol_id: str
    query_terms: tuple[str, ...]
    searched_sources: tuple[str, ...]
    equivalence_checks: tuple[str, ...]
    evidence_refs: tuple[tuple[str, str], ...]
    outcome: str
    prior_art_relationship: str
    prior_resolution: str
    prior_resolution_verification: str
    limitations: tuple[str, ...]
    previous_recheck_id: str | None = None
    previous_recheck_hash: str | None = None
    content_hash: str = ""

    def payload(self, *, include_hash: bool = True) -> dict[str, Any]:
        classification = self.classification()
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": POLICY_ID,
            "recheck_id": self.recheck_id,
            "checkpoint": self.checkpoint,
            "subject_id": self.subject_id,
            "subject_hash": self.subject_hash,
            "next_action_id": self.next_action_id,
            "performed_by": self.performed_by,
            "performer_kind": "human",
            "performed_at": self.performed_at,
            "search_protocol": {
                "protocol_id": self.protocol_id,
                "query_terms": list(self.query_terms),
                "searched_sources": list(self.searched_sources),
                "equivalence_checks": list(self.equivalence_checks),
            },
            "evidence_refs": [
                {"ref_id": ref_id, "content_hash": digest}
                for ref_id, digest in self.evidence_refs
            ],
            "outcome": self.outcome,
            "prior_art": {
                "relationship": self.prior_art_relationship,
                "resolution": self.prior_resolution,
                "verification_status": self.prior_resolution_verification,
                **classification.payload(),
            },
            "limitations": list(self.limitations),
            "previous_recheck_id": self.previous_recheck_id,
            "previous_recheck_hash": self.previous_recheck_hash,
            "creates_mathematical_warrant": False,
            "automatic_novelty_authority": False,
            "content_hash": self.content_hash if include_hash else None,
        }

    def classification(self) -> PriorArtClassification:
        return classify_prior_art(
            outcome=self.outcome,
            relationship=self.prior_art_relationship,
            prior_resolution=self.prior_resolution,
            verification_status=self.prior_resolution_verification,
        )

    def finalized(self) -> "NoveltyRecheck":
        return replace(self, content_hash=canonical_hash(self.payload(include_hash=False)))


_TOP_FIELDS = frozenset({
    "schema_version", "policy_id", "recheck_id", "checkpoint", "subject_id",
    "subject_hash", "next_action_id", "performed_by", "performer_kind",
    "performed_at", "search_protocol", "evidence_refs", "outcome", "limitations",
    "prior_art",
    "previous_recheck_id", "previous_recheck_hash", "creates_mathematical_warrant",
    "automatic_novelty_authority", "content_hash",
})


def load_recheck(payload: bytes | str | Mapping[str, Any]) -> NoveltyRecheck:
    if isinstance(payload, bytes):
        if len(payload) > MAX_RECORD_BYTES:
            raise NoveltyRecheckError("record_too_large")
        try:
            value = json.loads(payload.decode("utf-8"), object_pairs_hook=_strict_object,
                               parse_constant=lambda item: (_ for _ in ()).throw(
                                   NoveltyRecheckError(f"non_finite_json:{item}")))
        except UnicodeDecodeError as error:
            raise NoveltyRecheckError("record_not_utf8") from error
        except json.JSONDecodeError as error:
            raise NoveltyRecheckError("record_not_json") from error
    elif isinstance(payload, str):
        return load_recheck(payload.encode("utf-8"))
    else:
        try:
            value = json.loads(
                json.dumps(payload, allow_nan=False), object_pairs_hook=_strict_object,
            )
        except (TypeError, ValueError) as error:
            raise NoveltyRecheckError("record_not_json") from error
    if not isinstance(value, dict) or set(value) != set(_TOP_FIELDS):
        raise NoveltyRecheckError("field_set_mismatch")
    if value["schema_version"] != SCHEMA_VERSION or value["policy_id"] != POLICY_ID:
        raise NoveltyRecheckError("version_or_policy_unsupported")
    checkpoint = value["checkpoint"]
    if not isinstance(checkpoint, str) or checkpoint not in CHECKPOINTS:
        raise NoveltyRecheckError("checkpoint_unknown")
    outcome = value["outcome"]
    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        raise NoveltyRecheckError("outcome_unknown")
    prior_art = value["prior_art"]
    if not isinstance(prior_art, dict) or set(prior_art) != {
        "relationship", "resolution", "verification_status", "report_classification",
        "target_resolution_status", "novelty_status", "creates_mathematical_warrant",
    }:
        raise NoveltyRecheckError("prior_art_field_set_mismatch")
    classification = classify_prior_art(
        outcome=outcome,
        relationship=prior_art["relationship"],
        prior_resolution=prior_art["resolution"],
        verification_status=prior_art["verification_status"],
    )
    if (
        prior_art["report_classification"] != classification.report_classification
        or prior_art["target_resolution_status"] != classification.target_resolution_status
        or prior_art["novelty_status"] != "not_assessed"
        or prior_art["creates_mathematical_warrant"] is not False
    ):
        raise NoveltyRecheckError("prior_art_derived_classification_mismatch")
    if value["performer_kind"] != "human":
        raise NoveltyRecheckError("recheck_requires_human")
    if value["creates_mathematical_warrant"] is not False:
        raise NoveltyRecheckError("recheck_cannot_create_mathematical_warrant")
    if value["automatic_novelty_authority"] is not False:
        raise NoveltyRecheckError("automatic_novelty_authority_forbidden")
    protocol = value["search_protocol"]
    if not isinstance(protocol, dict) or set(protocol) != {
        "protocol_id", "query_terms", "searched_sources", "equivalence_checks",
    }:
        raise NoveltyRecheckError("search_protocol_field_set_mismatch")
    refs = value["evidence_refs"]
    if not isinstance(refs, list) or not refs or len(refs) > 32:
        raise NoveltyRecheckError("invalid_nonempty_list:evidence_refs")
    evidence: list[tuple[str, str]] = []
    for index, item in enumerate(refs):
        if not isinstance(item, dict) or set(item) != {"ref_id", "content_hash"}:
            raise NoveltyRecheckError(f"evidence_ref_field_set_mismatch:{index}")
        evidence.append((_identifier(item["ref_id"], f"evidence_refs[{index}].ref_id"),
                         _hash(item["content_hash"], f"evidence_refs[{index}].content_hash")))
    if len(set(evidence)) != len(evidence):
        raise NoveltyRecheckError("duplicate_list_item:evidence_refs")
    previous_id, previous_hash = value["previous_recheck_id"], value["previous_recheck_hash"]
    if (previous_id is None) != (previous_hash is None):
        raise NoveltyRecheckError("previous_recheck_reference_incomplete")
    if previous_id is not None:
        _identifier(previous_id, "previous_recheck_id")
        _hash(previous_hash, "previous_recheck_hash")
    record = NoveltyRecheck(
        recheck_id=_identifier(value["recheck_id"], "recheck_id"),
        checkpoint=checkpoint,
        subject_id=_identifier(value["subject_id"], "subject_id"),
        subject_hash=_hash(value["subject_hash"], "subject_hash"),
        next_action_id=_identifier(value["next_action_id"], "next_action_id"),
        performed_by=_identifier(value["performed_by"], "performed_by"),
        performed_at=_text(value["performed_at"], "performed_at"),
        protocol_id=_identifier(protocol["protocol_id"], "search_protocol.protocol_id"),
        query_terms=_string_list(protocol["query_terms"], "search_protocol.query_terms", maximum=32),
        searched_sources=_string_list(protocol["searched_sources"], "search_protocol.searched_sources", maximum=32),
        equivalence_checks=_string_list(protocol["equivalence_checks"], "search_protocol.equivalence_checks", maximum=32),
        evidence_refs=tuple(evidence), outcome=outcome,
        prior_art_relationship=prior_art["relationship"],
        prior_resolution=prior_art["resolution"],
        prior_resolution_verification=prior_art["verification_status"],
        limitations=_string_list(value["limitations"], "limitations", maximum=16),
        previous_recheck_id=previous_id, previous_recheck_hash=previous_hash,
        content_hash=_hash(value["content_hash"], "content_hash"),
    )
    parse_instant(record.performed_at)
    expected = record.finalized().content_hash
    if record.content_hash != expected:
        raise NoveltyRecheckError("content_hash_mismatch")
    return record


def read_recheck(path: Path) -> NoveltyRecheck:
    return load_recheck(path.read_bytes())


def write_recheck(record: NoveltyRecheck, path: Path) -> None:
    finalized = record.finalized()
    rendered = canonical_json(finalized.payload()) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise NoveltyRecheckError("recheck_record_overwrite_refused")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def require_checkpoint(
    record: NoveltyRecheck, *, checkpoint: str, subject_id: str, subject_hash: str,
    next_action_id: str, action_at: str | None = None,
) -> None:
    if record.checkpoint != checkpoint:
        raise NoveltyRecheckError("checkpoint_mismatch")
    if record.subject_id != subject_id or record.subject_hash != subject_hash:
        raise NoveltyRecheckError("stale_subject_binding")
    if record.next_action_id != next_action_id:
        raise NoveltyRecheckError("recheck_bound_to_different_action")
    if action_at is not None:
        elapsed = parse_instant(action_at, "action_at") - parse_instant(record.performed_at)
        if elapsed <= timedelta(0):
            raise NoveltyRecheckError("recheck_not_before_action")
        if elapsed > MAX_FRESHNESS:
            raise NoveltyRecheckError("recheck_too_old_for_action")


def require_announcement_chain(
    start: NoveltyRecheck, announcement: NoveltyRecheck, *, subject_id: str,
    subject_hash: str, approval_id: str, approval_at: str,
) -> None:
    if start.checkpoint != "before_research":
        raise NoveltyRecheckError("announcement_chain_missing_research_checkpoint")
    require_checkpoint(
        announcement, checkpoint="before_announcement", subject_id=subject_id,
        subject_hash=subject_hash, next_action_id=approval_id, action_at=approval_at,
    )
    if announcement.previous_recheck_id != start.recheck_id or announcement.previous_recheck_hash != start.content_hash:
        raise NoveltyRecheckError("announcement_chain_does_not_reference_research_recheck")
    if parse_instant(start.performed_at) >= parse_instant(announcement.performed_at):
        raise NoveltyRecheckError("announcement_recheck_not_fresh")
