"""Deterministic per-document rights derivation (ADR-0072 §7).

``derive_document_rights`` is a pure function of the content-hashed policy and
one archive-manifest entry.  The decision it produces records the policy
content hash, the deriving rule identifier, and the exact per-document licence
inputs; :func:`verify_derived_decision` refuses a decision missing any of the
three, and refuses a decision authored by a model or carrying proposal
authority regardless of everything else — that recording obligation replaced
ADR-0064's ``pr.nonhuman-embedding-decision-refused`` probe and is checked
first, before any hash arithmetic, so a bypass attempt is named as one.

A document the policy cannot classify is QUARANTINED: recorded, retained, and
excluded.  There is no prompt, no default admission, and no rule inference.
"""

from __future__ import annotations

from typing import Any, Mapping

from . import DERIVED_DECISION_SCHEMA_VERSION
from .constants import (
    HASH_PATTERN,
    IDENTIFIER_PATTERN,
    PARSABLE_MEDIA_TYPES,
    QUARANTINE_REASONS,
)
from .errors import (
    DerivedDecisionInvalidError,
    DerivedDecisionMissingLicenceInputsError,
    DerivedDecisionMissingPolicyHashError,
    DerivedDecisionMissingRuleIdError,
    NonHumanDerivedDecisionRefusedError,
    ProcessorWildcardForbiddenError,
)
from .serialization import canonical_hash, content_hash_of, public_value

DECISION_FIELDS = frozenset({
    "schema_version", "decision_id", "document_id", "source_id",
    "archive_id", "archive_version", "source_sha256",
    "policy_content_hash", "rule_id", "licence_inputs", "derivation",
    "authored_by", "status", "quarantine_reason", "uses", "content_hash",
})
_AUTHORED_BY_FIELDS = frozenset({"actor_id", "actor_kind", "authority"})
_USE_KEYS = (
    "acquisition", "storage_and_retention", "parsing", "embedding",
    "model_context",
)

STATUS_DERIVED = "derived"
STATUS_QUARANTINED = "quarantined"

DERIVATION_MECHANISM = "adaivy.policy-derivation.v1"

SOURCE_ID_PREFIX = "snapshot."


def source_id_for(document_id: str) -> str:
    """The Phase 4A subject identifier for one snapshot document."""

    if not isinstance(document_id, str) or IDENTIFIER_PATTERN.fullmatch(document_id) is None:
        raise DerivedDecisionInvalidError(f"not a document identifier: {document_id!r}")
    identifier = SOURCE_ID_PREFIX + document_id
    if IDENTIFIER_PATTERN.fullmatch(identifier) is None:
        raise DerivedDecisionInvalidError(
            f"the derived Phase 4A source id is not an identifier: {identifier!r}"
        )
    return identifier


def _decision_id(core: Mapping[str, Any]) -> str:
    return "crights." + canonical_hash(dict(core)).removeprefix("sha256:")[:24]


def _seal(decision: dict[str, Any]) -> dict[str, Any]:
    core = {key: decision[key] for key in sorted(decision) if key not in {
        "decision_id", "content_hash",
    }}
    decision["decision_id"] = _decision_id(core)
    decision["content_hash"] = content_hash_of(decision)
    return decision


def _base(policy: Mapping[str, Any], document: Mapping[str, Any]) -> dict[str, Any]:
    document_id = str(document["document_id"])
    licence_inputs = {
        "licence": document["licence"]["licence"],
        "licence_url": document["licence"]["licence_url"],
    }
    return {
        "schema_version": DERIVED_DECISION_SCHEMA_VERSION,
        "decision_id": None,
        "document_id": document_id,
        "source_id": source_id_for(document_id),
        "archive_id": policy["archive"]["archive_id"],
        "archive_version": policy["archive"]["archive_version"],
        "source_sha256": document["sha256"],
        "policy_content_hash": policy["content_hash"],
        "derivation": DERIVATION_MECHANISM,
        "authored_by": dict(policy["authored_by"]),
        "licence_inputs": licence_inputs,
        "content_hash": None,
    }


def quarantine_decision(
    policy: Mapping[str, Any], document: Mapping[str, Any], reason: str,
) -> dict[str, Any]:
    """A quarantine decision: recorded, retained, excluded. Never a prompt."""

    return verify_derived_decision(_seal({
        **_base(policy, document),
        "rule_id": None,
        "status": STATUS_QUARANTINED,
        "quarantine_reason": reason,
        "uses": None,
    }))


def derive_document_rights(
    policy: Mapping[str, Any], document: Mapping[str, Any],
    *, parsable_media_types: frozenset[str] = PARSABLE_MEDIA_TYPES,
) -> dict[str, Any]:
    """One deterministic decision per archive document. Pure, no clock.

    ``parsable_media_types`` is supplied by the extraction registry in use
    (ADR-0080); the default is the built-in identity set so a caller without a
    registry keeps the pre-ADR-0080 behavior exactly.
    """

    base = _base(policy, document)
    licence_inputs = base["licence_inputs"]
    if licence_inputs["licence"] is None:
        return quarantine_decision(policy, document, "licence_missing")
    rule = None
    for candidate in policy["rules"]:
        if candidate["licence"] == licence_inputs["licence"]:
            rule = candidate
            break
    if rule is None:
        return quarantine_decision(policy, document, "licence_unknown")
    if (
        licence_inputs["licence_url"] is not None
        and licence_inputs["licence_url"] != rule["licence_url"]
    ):
        return quarantine_decision(policy, document, "licence_conflicting")
    if rule["full_text"] and document["media_type"] not in parsable_media_types:
        return quarantine_decision(policy, document, "unsupported_media_type")
    uses = {
        "acquisition": {"value": "allowed", "processor": None},
        "storage_and_retention": {"value": "allowed", "processor": None},
        "parsing": {"value": rule["parsing"], "processor": None},
        "embedding": dict(rule["embedding"]),
        "model_context": dict(rule["model_context"]),
    }
    return verify_derived_decision(_seal({
        **base,
        "rule_id": rule["rule_id"],
        "status": STATUS_DERIVED,
        "quarantine_reason": None,
        "uses": uses,
    }))


def verify_derived_decision(value: Mapping[str, Any]) -> dict[str, Any]:
    """Fail-closed verification, authorship and recording obligations first."""

    if not isinstance(value, Mapping):
        raise DerivedDecisionInvalidError("a derived rights decision must be an object")
    decision = dict(public_value(value))
    if set(decision) != DECISION_FIELDS:
        raise DerivedDecisionInvalidError(
            "derived rights decision fields differ: "
            f"missing={sorted(DECISION_FIELDS - set(decision))}, "
            f"extra={sorted(set(decision) - DECISION_FIELDS)}"
        )

    authored_by = decision["authored_by"]
    if (
        not isinstance(authored_by, Mapping)
        or set(authored_by) != _AUTHORED_BY_FIELDS
        or not isinstance(authored_by.get("actor_id"), str)
        or IDENTIFIER_PATTERN.fullmatch(authored_by["actor_id"]) is None
    ):
        raise DerivedDecisionInvalidError("derived rights decision author differs")
    if authored_by["actor_kind"] != "human" or authored_by["authority"] != "human_final":
        raise NonHumanDerivedDecisionRefusedError(
            "a rights decision authored by a model or carrying proposal "
            "authority refuses; policy derivation moved human authority into "
            "the policy, it did not remove it — got "
            f"({authored_by['actor_kind']!r}, {authored_by['authority']!r})"
        )
    policy_hash = decision["policy_content_hash"]
    if not isinstance(policy_hash, str) or HASH_PATTERN.fullmatch(policy_hash) is None:
        raise DerivedDecisionMissingPolicyHashError(
            "a policy-derived decision that does not record the policy "
            "content hash must refuse"
        )
    licence_inputs = decision["licence_inputs"]
    if (
        not isinstance(licence_inputs, Mapping)
        or set(licence_inputs) != {"licence", "licence_url"}
        or any(
            item is not None and not isinstance(item, str)
            for item in licence_inputs.values()
        )
    ):
        raise DerivedDecisionMissingLicenceInputsError(
            "a policy-derived decision that does not record the exact "
            "per-document licence inputs must refuse"
        )
    if decision["derivation"] != DERIVATION_MECHANISM:
        raise DerivedDecisionInvalidError("derived rights decision mechanism differs")
    if decision["schema_version"] != DERIVED_DECISION_SCHEMA_VERSION:
        raise DerivedDecisionInvalidError("derived rights decision schema differs")

    document_id = decision["document_id"]
    if not isinstance(document_id, str) or IDENTIFIER_PATTERN.fullmatch(document_id) is None:
        raise DerivedDecisionInvalidError("derived rights decision document differs")
    if decision["source_id"] != source_id_for(document_id):
        raise DerivedDecisionInvalidError(
            "derived rights decision source_id is not the derived identity"
        )
    for name in ("archive_id", "archive_version"):
        if not isinstance(decision[name], str) or not decision[name]:
            raise DerivedDecisionInvalidError(
                f"derived rights decision {name} differs"
            )
    if not isinstance(decision["source_sha256"], str) or HASH_PATTERN.fullmatch(
        decision["source_sha256"]
    ) is None:
        raise DerivedDecisionInvalidError(
            "derived rights decision source hash differs"
        )

    status = decision["status"]
    if status == STATUS_QUARANTINED:
        if decision["rule_id"] is not None or decision["uses"] is not None:
            raise DerivedDecisionInvalidError(
                "a quarantined document carries no rule and no allowances"
            )
        if decision["quarantine_reason"] not in QUARANTINE_REASONS:
            raise DerivedDecisionInvalidError(
                f"unknown quarantine reason {decision['quarantine_reason']!r}"
            )
    elif status == STATUS_DERIVED:
        rule_id = decision["rule_id"]
        if not isinstance(rule_id, str) or IDENTIFIER_PATTERN.fullmatch(rule_id) is None:
            raise DerivedDecisionMissingRuleIdError(
                "a policy-derived decision that does not record the deriving "
                "rule identifier must refuse"
            )
        if decision["quarantine_reason"] is not None:
            raise DerivedDecisionInvalidError(
                "a derived decision cannot also carry a quarantine reason"
            )
        uses = decision["uses"]
        if not isinstance(uses, Mapping) or tuple(sorted(uses)) != tuple(sorted(_USE_KEYS)):
            raise DerivedDecisionInvalidError("derived rights decision uses differ")
        for use in _USE_KEYS:
            entry = uses[use]
            if not isinstance(entry, Mapping) or set(entry) != {"value", "processor"}:
                raise DerivedDecisionInvalidError(f"derived {use} decision fields differ")
            if entry["value"] not in {"allowed", "prohibited"}:
                raise DerivedDecisionInvalidError(f"derived {use} value differs")
            processor = entry["processor"]
            if use in {"embedding", "model_context"}:
                if entry["value"] == "allowed":
                    if not isinstance(processor, Mapping) or set(processor) != {
                        "processor_id", "provider", "model_identifier",
                        "disclosure_kind",
                    }:
                        raise DerivedDecisionInvalidError(
                            f"an allowed {use} decision must name one closed-"
                            "field processor (ADR-0064)"
                        )
                    for key in ("processor_id", "provider", "model_identifier"):
                        item = processor[key]
                        if (
                            not isinstance(item, str)
                            or item.strip().casefold() in {"*", "any", "all"}
                            or "*" in item
                        ):
                            raise ProcessorWildcardForbiddenError(
                                f"derived {use} {key} must name one exact "
                                f"value: {item!r}"
                            )
                elif processor is not None:
                    raise DerivedDecisionInvalidError(
                        f"a prohibited {use} decision must not name a processor"
                    )
            elif processor is not None:
                raise DerivedDecisionInvalidError(
                    f"{use} is non-disclosing and must not name a processor"
                )
        if uses["acquisition"]["value"] != "allowed" or uses[
            "storage_and_retention"
        ]["value"] != "allowed":
            raise DerivedDecisionInvalidError(
                "a derived (non-quarantined) decision must permit acquisition "
                "and retention; anything else is quarantine"
            )
    else:
        raise DerivedDecisionInvalidError(f"unknown decision status {status!r}")

    core = {key: decision[key] for key in sorted(decision) if key not in {
        "decision_id", "content_hash",
    }}
    if decision["decision_id"] != _decision_id(core):
        raise DerivedDecisionInvalidError(
            "derived rights decision identity differs from its content"
        )
    supplied = decision["content_hash"]
    if not isinstance(supplied, str) or HASH_PATTERN.fullmatch(supplied) is None:
        raise DerivedDecisionInvalidError(
            "derived rights decision content hash is not a sha256 value"
        )
    if content_hash_of(decision) != supplied:
        raise DerivedDecisionInvalidError(
            "derived rights decision content hash does not match its content"
        )
    return decision


__all__ = [
    "DECISION_FIELDS",
    "DERIVATION_MECHANISM",
    "SOURCE_ID_PREFIX",
    "STATUS_DERIVED",
    "STATUS_QUARANTINED",
    "derive_document_rights",
    "quarantine_decision",
    "source_id_for",
    "verify_derived_decision",
]
