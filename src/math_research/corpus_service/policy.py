"""The human-authored, content-hashed source-and-rights policy (ADR-0072 §7).

The policy is where human authority now lives: a human authors and approves it
once, and every per-document rights decision is a deterministic function of the
archive manifest, the per-document licence metadata, and this policy.  So the
policy itself is validated as a human-final act — a policy authored by a model
or carrying proposal authority is refused, because deriving thousands of
decisions from a non-decision would be the exact bypass ADR-0072 forbids.

ADR-0064's unsuperseded clauses bind every rule: a rule allowing ``embedding``
or ``model_context`` must name exactly one closed-field processor, and no
wildcard, ``any``, or cross-provider inheritance can be expressed.  The default
action for a document the policy cannot classify is quarantine and is pinned,
not configurable.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..phase2 import SUPPORTED_LIVE_PROVIDERS
from ..phase4a.records import DisclosureKind
from . import POLICY_SCHEMA_VERSION
from .constants import DATE_PATTERN_TEXT, IDENTIFIER_PATTERN, MAX_POLICY_BYTES
from .errors import (
    PolicyInvalidError,
    PolicyNotHumanAuthoredError,
    ProcessorWildcardForbiddenError,
)
from .serialization import strict_canonical_object, verify_sealed

POLICY_FIELDS = frozenset({
    "schema_version", "policy_id", "archive", "authored_by",
    "terms_reviewed_at", "licence_diligence_adr", "default_action", "rules",
    "content_hash",
})
_ARCHIVE_FIELDS = frozenset({"archive_id", "archive_version"})
_AUTHORED_BY_FIELDS = frozenset({"actor_id", "actor_kind", "authority"})
_RULE_FIELDS = frozenset({
    "rule_id", "licence", "licence_url", "acquisition", "storage_and_retention",
    "parsing", "full_text", "embedding", "model_context",
})
_USE_DECISION_FIELDS = frozenset({"value", "processor"})
_PROCESSOR_FIELDS = frozenset({
    "processor_id", "provider", "model_identifier", "disclosure_kind",
})

#: Pinned: quarantine is the only default the schema can express.
DEFAULT_ACTION = "quarantine"

_WILDCARD_TOKENS = ("*", "any", "all")
_DATE_PATTERN = re.compile(DATE_PATTERN_TEXT)
_DISCLOSURE_KINDS = frozenset(item.value for item in DisclosureKind)


def _assert_no_wildcard(value: str, label: str) -> str:
    if value.strip().casefold() in _WILDCARD_TOKENS or "*" in value:
        raise ProcessorWildcardForbiddenError(
            f"{label} must name one exact value, never a wildcard: {value!r}"
        )
    return value


def _validate_processor(value: Any, *, rule_id: str, use: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PROCESSOR_FIELDS:
        raise PolicyInvalidError(
            f"rule {rule_id} {use} processor fields differ; the processor "
            "field set is closed (ADR-0064)"
        )
    processor_id = value["processor_id"]
    if not isinstance(processor_id, str) or IDENTIFIER_PATTERN.fullmatch(processor_id) is None:
        raise PolicyInvalidError(f"rule {rule_id} {use} processor_id differs")
    _assert_no_wildcard(processor_id, f"rule {rule_id} {use} processor_id")
    provider = value["provider"]
    if not isinstance(provider, str) or provider not in SUPPORTED_LIVE_PROVIDERS:
        raise PolicyInvalidError(
            f"rule {rule_id} {use} provider {provider!r} is not a supported "
            "live provider"
        )
    model_identifier = value["model_identifier"]
    if not isinstance(model_identifier, str) or not model_identifier.strip():
        raise PolicyInvalidError(f"rule {rule_id} {use} model_identifier differs")
    _assert_no_wildcard(model_identifier, f"rule {rule_id} {use} model_identifier")
    if value["disclosure_kind"] not in _DISCLOSURE_KINDS:
        raise PolicyInvalidError(f"rule {rule_id} {use} disclosure_kind differs")
    return dict(value)


def _validate_use_decision(value: Any, *, rule_id: str, use: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _USE_DECISION_FIELDS:
        raise PolicyInvalidError(f"rule {rule_id} {use} decision fields differ")
    if value["value"] not in {"allowed", "prohibited"}:
        raise PolicyInvalidError(
            f"rule {rule_id} {use} value must be allowed or prohibited; "
            "anything unresolved is quarantine, not a rule"
        )
    if value["value"] == "allowed":
        processor = _validate_processor(value["processor"], rule_id=rule_id, use=use)
        return {"value": "allowed", "processor": processor}
    if value["processor"] is not None:
        raise PolicyInvalidError(
            f"rule {rule_id} {use} is prohibited and must not name a processor"
        )
    return {"value": "prohibited", "processor": None}


def _validate_rule(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RULE_FIELDS:
        raise PolicyInvalidError(f"policy rule {index} fields differ")
    rule_id = value["rule_id"]
    if not isinstance(rule_id, str) or IDENTIFIER_PATTERN.fullmatch(rule_id) is None:
        raise PolicyInvalidError(f"policy rule {index} rule_id differs")
    licence = value["licence"]
    if not isinstance(licence, str) or not licence.strip():
        raise PolicyInvalidError(f"rule {rule_id} licence differs")
    _assert_no_wildcard(licence, f"rule {rule_id} licence")
    licence_url = value["licence_url"]
    if not isinstance(licence_url, str) or not licence_url.strip():
        raise PolicyInvalidError(f"rule {rule_id} licence_url differs")
    for use in ("acquisition", "storage_and_retention"):
        if value[use] != "allowed":
            raise PolicyInvalidError(
                f"rule {rule_id} {use} must be allowed; a licence the policy "
                "cannot acquire or retain under is quarantine, not a rule"
            )
    if value["parsing"] not in {"allowed", "prohibited"}:
        raise PolicyInvalidError(f"rule {rule_id} parsing differs")
    if not isinstance(value["full_text"], bool):
        raise PolicyInvalidError(f"rule {rule_id} full_text must be a boolean")
    if value["full_text"] and value["parsing"] != "allowed":
        raise PolicyInvalidError(
            f"rule {rule_id} stores full text but does not permit parsing"
        )
    embedding = _validate_use_decision(value["embedding"], rule_id=rule_id, use="embedding")
    model_context = _validate_use_decision(
        value["model_context"], rule_id=rule_id, use="model_context",
    )
    return {
        "rule_id": rule_id,
        "licence": licence,
        "licence_url": licence_url,
        "acquisition": "allowed",
        "storage_and_retention": "allowed",
        "parsing": value["parsing"],
        "full_text": value["full_text"],
        "embedding": embedding,
        "model_context": model_context,
    }


def validate_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    policy = verify_sealed(
        value, label="source-and-rights policy", code=PolicyInvalidError.code,
    )
    if set(policy) != POLICY_FIELDS:
        raise PolicyInvalidError(
            "source-and-rights policy fields differ: "
            f"missing={sorted(POLICY_FIELDS - set(policy))}, "
            f"extra={sorted(set(policy) - POLICY_FIELDS)}"
        )
    if policy["schema_version"] != POLICY_SCHEMA_VERSION:
        raise PolicyInvalidError("source-and-rights policy schema differs")
    if not isinstance(policy["policy_id"], str) or IDENTIFIER_PATTERN.fullmatch(
        policy["policy_id"]
    ) is None:
        raise PolicyInvalidError("source-and-rights policy identifier differs")
    archive = policy["archive"]
    if (
        not isinstance(archive, Mapping) or set(archive) != _ARCHIVE_FIELDS
        or not isinstance(archive["archive_id"], str)
        or IDENTIFIER_PATTERN.fullmatch(archive["archive_id"]) is None
        or not isinstance(archive["archive_version"], str)
        or not archive["archive_version"].strip()
    ):
        raise PolicyInvalidError("source-and-rights policy archive identity differs")
    authored_by = policy["authored_by"]
    if (
        not isinstance(authored_by, Mapping)
        or set(authored_by) != _AUTHORED_BY_FIELDS
        or not isinstance(authored_by.get("actor_id"), str)
        or IDENTIFIER_PATTERN.fullmatch(authored_by["actor_id"]) is None
    ):
        raise PolicyInvalidError("source-and-rights policy author differs")
    if authored_by["actor_kind"] != "human" or authored_by["authority"] != "human_final":
        raise PolicyNotHumanAuthoredError(
            "a source-and-rights policy is the human act ADR-0072 §7 moves "
            "authority into; it must be authored by "
            "(actor_kind=human, authority=human_final), got "
            f"({authored_by['actor_kind']!r}, {authored_by['authority']!r})"
        )
    if not isinstance(policy["terms_reviewed_at"], str) or _DATE_PATTERN.fullmatch(
        policy["terms_reviewed_at"]
    ) is None:
        raise PolicyInvalidError("source-and-rights policy terms review date differs")
    if not isinstance(policy["licence_diligence_adr"], str) or not policy[
        "licence_diligence_adr"
    ].strip():
        raise PolicyInvalidError("source-and-rights policy licence diligence differs")
    if policy["default_action"] != DEFAULT_ACTION:
        raise PolicyInvalidError(
            "the default action for an unclassifiable document is quarantine "
            "and is not configurable"
        )
    rules = policy["rules"]
    if not isinstance(rules, list) or not rules:
        raise PolicyInvalidError("source-and-rights policy needs at least one rule")
    validated = [_validate_rule(rule, index) for index, rule in enumerate(rules)]
    rule_ids = [rule["rule_id"] for rule in validated]
    licences = [rule["licence"] for rule in validated]
    if rule_ids != sorted(rule_ids) or len(set(rule_ids)) != len(rule_ids):
        raise PolicyInvalidError("policy rules must be sorted and unique by rule_id")
    if len(set(licences)) != len(licences):
        raise PolicyInvalidError(
            "two policy rules classify the same licence; the derivation must "
            "be a function"
        )
    return policy


def load_policy(data: bytes) -> dict[str, Any]:
    return validate_policy(strict_canonical_object(
        data, maximum=MAX_POLICY_BYTES, label="source-and-rights policy",
        code=PolicyInvalidError.code,
    ))


def rule_for_licence(policy: Mapping[str, Any], licence: str) -> dict[str, Any] | None:
    """The unique rule classifying ``licence``, or None (quarantine)."""

    for rule in policy["rules"]:
        if rule["licence"] == licence:
            return dict(rule)
    return None


__all__ = [
    "DEFAULT_ACTION",
    "POLICY_FIELDS",
    "load_policy",
    "rule_for_licence",
    "validate_policy",
]
