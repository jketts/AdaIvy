"""Declarative problem intake: build a Phase 1 dossier from a problem file.

This module is a BUILDER over the existing Phase 1 entities. It changes no
trust semantics and adds no entity field. A problem definition is an UNTRUSTED
input: it declares what the researcher wants investigated, and nothing else.

Four properties are structural rather than checked at the end:

- The intake never constructs an ``EpistemicWarrant``, ``Evidence``,
  ``VerificationRecord``, ``SourceApplicabilityRecord``, or
  ``RepresentationMap``. Those tuples are literal empty tuples below, and the
  problem-definition grammar has no field that could populate them.
- Semantic alignment is always recorded as ``AlignmentStatus.PROPOSED`` with
  ``approved_by=None``. Approving a target interpretation is a researcher act
  (blueprint Section 4.15), so the grammar has no field for it.
- Every claim origin is ``ClaimOrigin.USER``. Declaring ``source`` origin would
  assert provenance the intake cannot supply (correctness contract C1), so the
  grammar has no field for it.
- Novelty, significance, and contribution links are never set.

Determinism: no wall clock and no randomness. The dossier is a pure function of
(document bytes, instant). The canonical hash of the accepted document is bound
into the dossier ID and into an append-only audit event, so a dossier traces
back to the problem definition that produced it. The raw source-byte hash is
operational (it moves with reformatting that does not change meaning) and is
returned alongside the dossier rather than stored inside it.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..domain.entities import (
    AlignmentStatus,
    ApprovalStatus,
    AuditEvent,
    Claim,
    ClaimOrigin,
    ClaimScope,
    EvaluationProtocol,
    Formalization,
    ObligationStatus,
    OpaqueId,
    ProblemType,
    ProofObligation,
    ProtocolPhase,
    ResearchDossier,
    ResearchProblem,
    SemanticAlignmentRecord,
    StrengthRelation,
    oid,
)
from ..interchange import canonical_bytes, content_hash

PROBLEM_DEFINITION_SCHEMA_VERSION = "1.0.0"
PROBLEM_DEFINITION_SCHEMA_ID = "https://adaivy.local/schemas/problem-definition-1.0.0.json"
INTAKE_CAPABILITIES = ("canonical_json", "declarative_problem_intake", "policy_projection")

MAX_DOCUMENT_BYTES = 262_144
MAX_TITLE_LENGTH = 200
MAX_STATEMENT_LENGTH = 8_192
MAX_SHORT_TEXT_LENGTH = 512
MAX_LIST_ITEMS = 64
MAX_ASSUMPTION_CLAIMS = 32

SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[-_.][a-z0-9]+)*$")
LOCAL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
KIND_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
DOMAIN_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
FORMAL_LANGUAGE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
INSTANT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


# ---------------------------------------------------------------------------
# Enumerated values, derived from the Phase 1 domain enums.
#
# Nothing below re-lists a domain value as a literal. A new member of a Phase 1
# enum appears here automatically; a member that must stay outside the intake is
# named once, as a forbidden member of its own enum, with the reason.
# ---------------------------------------------------------------------------

def _values(members: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted(member.value for member in members))


# Approving a formalization is a researcher act; superseding is a lifecycle act
# on an existing record. An intake document may only propose.
FORBIDDEN_APPROVAL_STATUS = {
    ApprovalStatus.APPROVED: "approving a formalization is a researcher act, not an intake declaration",
    ApprovalStatus.SUPERSEDED: "superseding is a lifecycle transition over an existing record",
}
# A confirmatory protocol must be frozen (entities.EvaluationProtocol), and
# freezing an evaluation protocol is a researcher act.
FORBIDDEN_PROTOCOL_PHASE = {
    ProtocolPhase.CONFIRMATORY: "a confirmatory protocol must be frozen by a researcher before use",
}

INTAKE_PROBLEM_TYPES = _values(ProblemType)
INTAKE_CLAIM_SCOPES = _values(ClaimScope)
INTAKE_STRENGTH_RELATIONS = _values(StrengthRelation)
INTAKE_APPROVAL_STATUSES = _values(set(ApprovalStatus) - set(FORBIDDEN_APPROVAL_STATUS))
INTAKE_PROTOCOL_PHASES = _values(set(ProtocolPhase) - set(FORBIDDEN_PROTOCOL_PHASE))

# Values the intake never accepts as input and always supplies itself.
INTAKE_CLAIM_ORIGIN = ClaimOrigin.USER
INTAKE_ALIGNMENT_STATUS = AlignmentStatus.PROPOSED


# ---------------------------------------------------------------------------
# Field vocabulary.
# ---------------------------------------------------------------------------

DOCUMENT_FIELDS = frozenset({
    "schema_version", "problem_definition_id", "declared_domain",
    "originating_principal", "problem", "target_claim", "assumption_claims",
    "formalization", "semantic_alignment", "evaluation_protocol",
})
PROBLEM_FIELDS = frozenset({"title", "informal_statement", "problem_type", "tags"})
CLAIM_FIELDS = frozenset({"local_id", "kind", "statement", "scope"})
FORMALIZATION_FIELDS = frozenset({
    "version", "statement", "formal_language", "quantifiers",
    "assumption_local_ids", "approval_status",
})
ALIGNMENT_FIELDS = frozenset({
    "quantifier_mapping", "definition_mapping", "assumption_delta",
    "edge_case_delta", "strength_relation",
})
PROTOCOL_FIELDS = frozenset({"version", "phase", "metrics", "success_criteria", "stopping_rules"})

_TRUST_REASON = "the intake creates no warrant, evidence, verification record, or applicability record"
_PROJECTION_REASON = "logical status and confidence are policy projections and are never stored"
_ASSESSMENT_REASON = "novelty, significance, and contribution stay not_assessed"

# Keys that are rejected with a named reason instead of a bare "unknown field",
# so a document that tries to buy trust is told exactly what it may not do.
FORBIDDEN_FIELDS: Mapping[str, str] = {
    "warrants": _TRUST_REASON,
    "epistemic_warrants": _TRUST_REASON,
    "evidence": _TRUST_REASON,
    "verification_records": _TRUST_REASON,
    "source_applicability": _TRUST_REASON,
    "representation_maps": _TRUST_REASON,
    "obligations": "proof obligations are derived by the intake and are opened, never discharged",
    "proof_status": _PROJECTION_REASON,
    "logical_status": _PROJECTION_REASON,
    "truth_status": _PROJECTION_REASON,
    "confidence": _PROJECTION_REASON,
    "confidence_score": _PROJECTION_REASON,
    "novelty": _ASSESSMENT_REASON,
    "novelty_assessment_id": _ASSESSMENT_REASON,
    "significance": _ASSESSMENT_REASON,
    "significance_assessment_id": _ASSESSMENT_REASON,
    "contribution_ids": _ASSESSMENT_REASON,
    "capabilities": "dossier capabilities are supplied by the intake, not declared by the document",
    "audit_events": "audit events are append-only and are minted by the intake",
    "claims": "claims are declared as target_claim and assumption_claims",
    "content_hash": "the canonical hash is computed, never declared",
    "created_at": "the intake instant is an explicit argument, so there is exactly one source of time",
    "instant": "the intake instant is an explicit argument, so there is exactly one source of time",
    "status": "semantic alignment approval is a researcher act and has no intake field",
    "approved_by": "semantic alignment approval is a researcher act and has no intake field",
    "approval_artifact_id": "semantic alignment approval is a researcher act and has no intake field",
    "origin": "every intake claim originates with the declaring principal (correctness contract C1)",
    "representation_map_ids": "representation bridges are separate verified records, not intake fields",
    "assumption_claim_ids": "assumption links are declared as local IDs in formalization.assumption_local_ids",
    "target_claim_id": "the target is declared as target_claim, not as an entity ID",
    "frozen_at": "freezing an evaluation protocol is a researcher act",
    "frozen_by": "freezing an evaluation protocol is a researcher act",
    "active_formalization_id": "the intake links the single declared formalization itself",
}

ISSUE_CODES = frozenset({
    "control_character", "duplicate_item", "duplicate_key", "duplicate_local_id", "empty",
    "enum", "forbidden_enum_value", "forbidden_field", "identifier", "instant",
    "malformed_json", "non_finite_number", "not_nfc", "not_utf8", "reference",
    "required", "too_large", "too_long", "too_many", "type", "unknown_field",
    "version", "whitespace",
})


@dataclass(frozen=True, slots=True, kw_only=True)
class ProblemDefinitionIssue:
    schema_version: str
    path: str
    code: str
    message: str


class ProblemDefinitionError(ValueError):
    """The single typed rejection for every problem-definition failure class."""

    def __init__(self, issues: tuple[ProblemDefinitionIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{item.path}: [{item.code}] {item.message}" for item in issues))

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(sorted({item.code for item in self.issues}))


# ---------------------------------------------------------------------------
# Accepted document records.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True, kw_only=True)
class ProblemSpec:
    title: str
    informal_statement: str
    problem_type: ProblemType
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimSpec:
    local_id: str
    kind: str
    statement: str
    scope: ClaimScope


@dataclass(frozen=True, slots=True, kw_only=True)
class FormalizationSpec:
    version: int
    statement: str
    formal_language: str
    quantifiers: tuple[str, ...]
    assumption_local_ids: tuple[str, ...]
    approval_status: ApprovalStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class AlignmentSpec:
    quantifier_mapping: tuple[tuple[str, str], ...]
    definition_mapping: tuple[tuple[str, str], ...]
    assumption_delta: tuple[str, ...]
    edge_case_delta: tuple[str, ...]
    strength_relation: StrengthRelation


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtocolSpec:
    version: int
    phase: ProtocolPhase
    metrics: tuple[str, ...]
    success_criteria: tuple[str, ...]
    stopping_rules: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProblemDefinition:
    schema_version: str
    problem_definition_id: str
    declared_domain: str
    originating_principal: OpaqueId
    problem: ProblemSpec
    target_claim: ClaimSpec
    assumption_claims: tuple[ClaimSpec, ...]
    formalization: FormalizationSpec
    semantic_alignment: AlignmentSpec
    evaluation_protocol: ProtocolSpec
    canonical_document: str
    canonical_document_hash: str
    source_bytes_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProblemIntakeResult:
    """Semantic dossier plus the operational hash of the exact source bytes."""

    schema_version: str
    definition: ProblemDefinition
    dossier: ResearchDossier
    instant: datetime


# ---------------------------------------------------------------------------
# Primitive validation helpers. Every helper appends issues and returns a
# placeholder; nothing coerces and nothing defaults.
# ---------------------------------------------------------------------------

class _DuplicateKey(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise _DuplicateKey(key)
        seen.add(key)
    return dict(pairs)


def _reject_constant(value: str) -> Any:
    raise _NonFiniteNumber(value)


class _NonFiniteNumber(ValueError):
    pass


class _Collector:
    def __init__(self) -> None:
        self.issues: list[ProblemDefinitionIssue] = []

    def add(self, path: str, code: str, message: str) -> None:
        assert code in ISSUE_CODES, code
        self.issues.append(
            ProblemDefinitionIssue(
                schema_version=PROBLEM_DEFINITION_SCHEMA_VERSION,
                path=path,
                code=code,
                message=message,
            )
        )

    def raise_if_any(self) -> None:
        if self.issues:
            ordered = tuple(sorted(self.issues, key=lambda item: (item.path, item.code, item.message)))
            raise ProblemDefinitionError(ordered)


def _child(
    parent: Mapping[str, Any], key: str, path: str, issues: _Collector,
) -> tuple[Mapping[str, Any], _Collector]:
    """Scope child validation to a present key.

    A missing object is already reported once as `required` on the parent, so
    the child's own issues are routed to a discarded collector rather than
    reported a second time as a wrong type and a wall of missing subfields.
    """
    if key not in parent:
        return {}, _Collector()
    return _mapping(parent[key], path, issues), issues


def _mapping(value: Any, path: str, issues: _Collector) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        issues.add(path, "type", "must be an object")
        return {}
    return value


def _exact_fields(value: Mapping[str, Any], expected: frozenset[str], path: str, issues: _Collector) -> None:
    for key in sorted(expected - set(value)):
        issues.add(f"{path}.{key}", "required", "field is required")
    for key in sorted(set(value) - expected):
        reason = FORBIDDEN_FIELDS.get(key)
        if reason is not None:
            issues.add(f"{path}.{key}", "forbidden_field", reason)
        else:
            issues.add(f"{path}.{key}", "unknown_field", "field is not part of the problem-definition grammar")


def _text(value: Any, path: str, issues: _Collector, *, max_length: int, multiline: bool = False) -> str:
    if not isinstance(value, str):
        issues.add(path, "type", "must be a string")
        return ""
    if not value:
        issues.add(path, "empty", "must not be empty")
        return ""
    if value != value.strip():
        issues.add(path, "whitespace", "must not have leading or trailing whitespace")
        return ""
    if len(value) > max_length:
        issues.add(path, "too_long", f"must be at most {max_length} characters")
        return ""
    allowed_controls = {"\n"} if multiline else set()
    for character in value:
        if character < " " and character not in allowed_controls:
            issues.add(path, "control_character", f"control character {ord(character):#04x} is not allowed")
            return ""
        if character == "\x7f":
            issues.add(path, "control_character", "delete character is not allowed")
            return ""
    if unicodedata.normalize("NFC", value) != value:
        issues.add(path, "not_nfc", "text must already be Unicode NFC; the intake never normalizes silently")
        return ""
    return value


def _pattern(value: Any, path: str, issues: _Collector, *, pattern: re.Pattern[str], max_length: int) -> str:
    text = _text(value, path, issues, max_length=max_length)
    if not text:
        return ""
    if not pattern.fullmatch(text):
        issues.add(path, "identifier", f"must match {pattern.pattern}")
        return ""
    return text


def _enum(value: Any, member_type: Any, allowed: tuple[str, ...], forbidden: Mapping[Any, str], path: str, issues: _Collector) -> Any:
    if not isinstance(value, str):
        issues.add(path, "type", "must be a string")
        return None
    forbidden_values = {member.value: reason for member, reason in forbidden.items()}
    if value in forbidden_values:
        issues.add(path, "forbidden_enum_value", forbidden_values[value])
        return None
    if value not in allowed:
        issues.add(path, "enum", f"must be one of {list(allowed)}")
        return None
    return member_type(value)


def _integer(value: Any, path: str, issues: _Collector, *, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        issues.add(path, "type", "must be an integer")
        return 0
    if value < minimum or value > maximum:
        issues.add(path, "type", f"must be between {minimum} and {maximum}")
        return 0
    return value


def _string_list(
    value: Any, path: str, issues: _Collector, *, max_items: int = MAX_LIST_ITEMS,
    max_length: int = MAX_SHORT_TEXT_LENGTH, unique: bool = True,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        issues.add(path, "type", "must be an array")
        return ()
    if len(value) > max_items:
        issues.add(path, "too_many", f"must have at most {max_items} items")
        return ()
    items = tuple(
        _text(item, f"{path}[{index}]", issues, max_length=max_length)
        for index, item in enumerate(value)
    )
    if unique and len(set(items)) != len(items):
        issues.add(path, "duplicate_item", "items must be unique")
        return ()
    return items


def _pair_list(value: Any, path: str, issues: _Collector) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        issues.add(path, "type", "must be an array")
        return ()
    if len(value) > MAX_LIST_ITEMS:
        issues.add(path, "too_many", f"must have at most {MAX_LIST_ITEMS} items")
        return ()
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, list) or len(item) != 2:
            issues.add(item_path, "type", "must be a two-element [key, value] array")
            continue
        key = _text(item[0], f"{item_path}[0]", issues, max_length=MAX_SHORT_TEXT_LENGTH)
        mapped = _text(item[1], f"{item_path}[1]", issues, max_length=MAX_SHORT_TEXT_LENGTH)
        if key and mapped:
            pairs.append((key, mapped))
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        issues.add(path, "duplicate_item", "mapping keys must be unique")
        return ()
    return tuple(pairs)


def _claim_spec(value: Any, path: str, issues: _Collector) -> ClaimSpec:
    payload = _mapping(value, path, issues)
    _exact_fields(payload, CLAIM_FIELDS, path, issues)
    return ClaimSpec(
        local_id=_pattern(payload.get("local_id"), f"{path}.local_id", issues, pattern=LOCAL_ID_PATTERN, max_length=64),
        kind=_pattern(payload.get("kind"), f"{path}.kind", issues, pattern=KIND_PATTERN, max_length=64),
        statement=_text(payload.get("statement"), f"{path}.statement", issues, max_length=MAX_STATEMENT_LENGTH, multiline=True),
        scope=_enum(payload.get("scope"), ClaimScope, INTAKE_CLAIM_SCOPES, {}, f"{path}.scope", issues),
    )


# ---------------------------------------------------------------------------
# Parsing.
# ---------------------------------------------------------------------------

def parse_instant(value: str) -> datetime:
    """Parse an explicit UTC instant. There is no clock read anywhere here."""
    issues = _Collector()
    if not isinstance(value, str) or not INSTANT_PATTERN.fullmatch(value):
        issues.add("$.instant", "instant", "must be an explicit UTC instant such as 2026-08-21T00:00:00Z")
        issues.raise_if_any()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def parse_problem_definition(data: bytes) -> ProblemDefinition:
    """Validate untrusted problem-definition bytes. Fails closed, once."""
    issues = _Collector()
    if len(data) > MAX_DOCUMENT_BYTES:
        issues.add("$", "too_large", f"document must be at most {MAX_DOCUMENT_BYTES} bytes")
        issues.raise_if_any()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        issues.add("$", "not_utf8", str(error))
        issues.raise_if_any()
        raise  # pragma: no cover - raise_if_any always raises above
    try:
        payload = json.loads(
            text, object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except _DuplicateKey as error:
        issues.add("$", "duplicate_key", f"duplicate object key {error.key!r}")
        issues.raise_if_any()
        raise  # pragma: no cover
    except _NonFiniteNumber as error:
        issues.add("$", "non_finite_number", f"non-finite JSON constant {error.args[0]!r}")
        issues.raise_if_any()
        raise  # pragma: no cover
    except json.JSONDecodeError as error:
        issues.add("$", "malformed_json", f"line {error.lineno} column {error.colno}: {error.msg}")
        issues.raise_if_any()
        raise  # pragma: no cover

    document = _mapping(payload, "$", issues)
    _exact_fields(document, DOCUMENT_FIELDS, "$", issues)
    if document.get("schema_version") != PROBLEM_DEFINITION_SCHEMA_VERSION:
        issues.add(
            "$.schema_version", "version",
            f"unsupported problem-definition schema version: {document.get('schema_version')!r}",
        )

    slug = _pattern(document.get("problem_definition_id"), "$.problem_definition_id", issues, pattern=SLUG_PATTERN, max_length=96)
    domain = _pattern(document.get("declared_domain"), "$.declared_domain", issues, pattern=DOMAIN_PATTERN, max_length=64)
    principal_text = _text(document.get("originating_principal"), "$.originating_principal", issues, max_length=96)
    principal: OpaqueId | None = None
    if principal_text:
        try:
            principal = OpaqueId(principal_text)
        except ValueError:
            issues.add("$.originating_principal", "identifier", "must be a valid opaque principal ID")

    problem_payload, problem_issues = _child(document, "problem", "$.problem", issues)
    _exact_fields(problem_payload, PROBLEM_FIELDS, "$.problem", problem_issues)
    problem = ProblemSpec(
        title=_text(problem_payload.get("title"), "$.problem.title", problem_issues, max_length=MAX_TITLE_LENGTH),
        informal_statement=_text(
            problem_payload.get("informal_statement"), "$.problem.informal_statement", problem_issues,
            max_length=MAX_STATEMENT_LENGTH, multiline=True,
        ),
        problem_type=_enum(problem_payload.get("problem_type"), ProblemType, INTAKE_PROBLEM_TYPES, {}, "$.problem.problem_type", problem_issues),
        tags=_string_list(problem_payload.get("tags"), "$.problem.tags", problem_issues, max_length=64),
    )

    target_payload, target_issues = _child(document, "target_claim", "$.target_claim", issues)
    target = _claim_spec(target_payload, "$.target_claim", target_issues)
    assumption_payload = document.get("assumption_claims")
    assumptions: tuple[ClaimSpec, ...] = ()
    if not isinstance(assumption_payload, list):
        issues.add("$.assumption_claims", "type", "must be an array")
    elif len(assumption_payload) > MAX_ASSUMPTION_CLAIMS:
        issues.add("$.assumption_claims", "too_many", f"must have at most {MAX_ASSUMPTION_CLAIMS} claims")
    else:
        assumptions = tuple(
            _claim_spec(item, f"$.assumption_claims[{index}]", issues)
            for index, item in enumerate(assumption_payload)
        )

    local_ids = [item.local_id for item in assumptions if item.local_id]
    if target.local_id:
        local_ids.append(target.local_id)
    if len(set(local_ids)) != len(local_ids):
        issues.add("$", "duplicate_local_id", "target_claim and assumption_claims must have distinct local IDs")

    formalization_payload, formalization_issues = _child(document, "formalization", "$.formalization", issues)
    _exact_fields(formalization_payload, FORMALIZATION_FIELDS, "$.formalization", formalization_issues)
    declared_assumption_ids = _string_list(
        formalization_payload.get("assumption_local_ids"), "$.formalization.assumption_local_ids",
        formalization_issues, max_length=64,
    )
    known = {item.local_id for item in assumptions if item.local_id}
    for index, name in enumerate(declared_assumption_ids):
        if name and name not in known:
            formalization_issues.add(
                f"$.formalization.assumption_local_ids[{index}]", "reference",
                f"no assumption claim declares local_id {name!r}",
            )
    formalization = FormalizationSpec(
        version=_integer(formalization_payload.get("version"), "$.formalization.version", formalization_issues, minimum=1, maximum=9_999),
        statement=_text(formalization_payload.get("statement"), "$.formalization.statement", formalization_issues, max_length=MAX_STATEMENT_LENGTH, multiline=True),
        formal_language=_pattern(formalization_payload.get("formal_language"), "$.formalization.formal_language", formalization_issues, pattern=FORMAL_LANGUAGE_PATTERN, max_length=64),
        quantifiers=_string_list(formalization_payload.get("quantifiers"), "$.formalization.quantifiers", formalization_issues),
        assumption_local_ids=declared_assumption_ids,
        approval_status=_enum(
            formalization_payload.get("approval_status"), ApprovalStatus, INTAKE_APPROVAL_STATUSES,
            FORBIDDEN_APPROVAL_STATUS, "$.formalization.approval_status", formalization_issues,
        ),
    )

    alignment_payload, alignment_issues = _child(document, "semantic_alignment", "$.semantic_alignment", issues)
    _exact_fields(alignment_payload, ALIGNMENT_FIELDS, "$.semantic_alignment", alignment_issues)
    alignment = AlignmentSpec(
        quantifier_mapping=_pair_list(alignment_payload.get("quantifier_mapping"), "$.semantic_alignment.quantifier_mapping", alignment_issues),
        definition_mapping=_pair_list(alignment_payload.get("definition_mapping"), "$.semantic_alignment.definition_mapping", alignment_issues),
        assumption_delta=_string_list(alignment_payload.get("assumption_delta"), "$.semantic_alignment.assumption_delta", alignment_issues),
        edge_case_delta=_string_list(alignment_payload.get("edge_case_delta"), "$.semantic_alignment.edge_case_delta", alignment_issues),
        strength_relation=_enum(
            alignment_payload.get("strength_relation"), StrengthRelation, INTAKE_STRENGTH_RELATIONS, {},
            "$.semantic_alignment.strength_relation", alignment_issues,
        ),
    )

    protocol_payload, protocol_issues = _child(document, "evaluation_protocol", "$.evaluation_protocol", issues)
    _exact_fields(protocol_payload, PROTOCOL_FIELDS, "$.evaluation_protocol", protocol_issues)
    protocol = ProtocolSpec(
        version=_integer(protocol_payload.get("version"), "$.evaluation_protocol.version", protocol_issues, minimum=1, maximum=9_999),
        phase=_enum(
            protocol_payload.get("phase"), ProtocolPhase, INTAKE_PROTOCOL_PHASES, FORBIDDEN_PROTOCOL_PHASE,
            "$.evaluation_protocol.phase", protocol_issues,
        ),
        metrics=_string_list(protocol_payload.get("metrics"), "$.evaluation_protocol.metrics", protocol_issues),
        success_criteria=_string_list(protocol_payload.get("success_criteria"), "$.evaluation_protocol.success_criteria", protocol_issues),
        stopping_rules=_string_list(protocol_payload.get("stopping_rules"), "$.evaluation_protocol.stopping_rules", protocol_issues),
    )

    issues.raise_if_any()
    assert principal is not None
    canonical = canonical_bytes(document).decode("utf-8")
    return ProblemDefinition(
        schema_version=PROBLEM_DEFINITION_SCHEMA_VERSION,
        problem_definition_id=slug,
        declared_domain=domain,
        originating_principal=principal,
        problem=problem,
        target_claim=target,
        assumption_claims=assumptions,
        formalization=formalization,
        semantic_alignment=alignment,
        evaluation_protocol=protocol,
        canonical_document=canonical,
        canonical_document_hash=content_hash(document),
        source_bytes_hash=content_hash(data.decode("utf-8")),
    )


# ---------------------------------------------------------------------------
# Building. No warrant, evidence, verification record, applicability record, or
# representation map is constructible from this function.
# ---------------------------------------------------------------------------

def build_dossier(definition: ProblemDefinition, *, instant: datetime) -> ResearchDossier:
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ProblemDefinitionError(
            (
                ProblemDefinitionIssue(
                    schema_version=PROBLEM_DEFINITION_SCHEMA_VERSION,
                    path="$.instant", code="instant",
                    message="the intake instant must be timezone-aware",
                ),
            )
        )
    stamp = instant.astimezone(timezone.utc)
    slug = definition.problem_definition_id
    actor = definition.originating_principal
    digest = definition.canonical_document_hash.removeprefix("sha256:")[:16]

    def claim_of(spec: ClaimSpec, assumption_ids: tuple[OpaqueId, ...]) -> Claim:
        return Claim(
            id=oid(f"claim.{slug}.{spec.local_id}"), created_at=stamp, created_by=actor,
            kind=spec.kind, statement=spec.statement,
            assumption_claim_ids=assumption_ids,
            origin=INTAKE_CLAIM_ORIGIN, scope=spec.scope,
            representation_map_ids=(),
            novelty_assessment_id=None, significance_assessment_id=None, contribution_ids=(),
        )

    assumption_claims = tuple(claim_of(spec, ()) for spec in definition.assumption_claims)
    by_local_id = {
        spec.local_id: claim.id
        for spec, claim in zip(definition.assumption_claims, assumption_claims, strict=True)
    }
    linked = tuple(by_local_id[name] for name in definition.formalization.assumption_local_ids)
    target_claim = claim_of(definition.target_claim, linked)

    problem_id = oid(f"problem.{slug}")
    formalization_id = oid(f"formalization.{slug}.v{definition.formalization.version}")
    problem = ResearchProblem(
        id=problem_id, created_at=stamp, created_by=actor,
        title=definition.problem.title,
        informal_statement=definition.problem.informal_statement,
        problem_type=definition.problem.problem_type,
        tags=definition.problem.tags,
        active_formalization_id=formalization_id,
    )
    formalization = Formalization(
        id=formalization_id, created_at=stamp, created_by=actor,
        problem_id=problem_id, version=definition.formalization.version,
        statement=definition.formalization.statement,
        formal_language=definition.formalization.formal_language,
        quantifiers=definition.formalization.quantifiers,
        assumption_claim_ids=linked,
        target_claim_id=target_claim.id,
        approval_status=definition.formalization.approval_status,
    )
    alignment = SemanticAlignmentRecord(
        id=oid(f"alignment.{slug}.v{definition.formalization.version}"), created_at=stamp, created_by=actor,
        problem_id=problem_id, formalization_id=formalization_id, compared_claim_id=target_claim.id,
        quantifier_mapping=definition.semantic_alignment.quantifier_mapping,
        definition_mapping=definition.semantic_alignment.definition_mapping,
        assumption_delta=definition.semantic_alignment.assumption_delta,
        edge_case_delta=definition.semantic_alignment.edge_case_delta,
        strength_relation=definition.semantic_alignment.strength_relation,
        # Forced: only a researcher approves a target interpretation.
        status=INTAKE_ALIGNMENT_STATUS,
        approved_by=None,
    )
    warrant_obligation = ProofObligation(
        id=oid(f"obligation.{slug}.target_unwarranted"), created_at=stamp, created_by=actor,
        claim_id=target_claim.id,
        description=(
            "The declarative problem intake supplies no warrant, evidence, or verification record "
            "for the target claim."
        ),
        category="logical_gap", status=ObligationStatus.OPEN,
        normalized_statement=None, discharged_by_warrant_id=None, parent_obligation_id=None,
    )
    alignment_obligation = ProofObligation(
        id=oid(f"obligation.{slug}.alignment_unapproved"), created_at=stamp, created_by=actor,
        claim_id=target_claim.id,
        description=(
            "The declared target interpretation is proposed and awaits researcher approval of the "
            "semantic alignment record."
        ),
        category="semantic_alignment", status=ObligationStatus.OPEN,
        normalized_statement=None, discharged_by_warrant_id=None, parent_obligation_id=None,
    )
    protocol = EvaluationProtocol(
        id=oid(f"protocol.{slug}.v{definition.evaluation_protocol.version}"), created_at=stamp, created_by=actor,
        version=definition.evaluation_protocol.version,
        phase=definition.evaluation_protocol.phase,
        metrics=definition.evaluation_protocol.metrics,
        success_criteria=definition.evaluation_protocol.success_criteria,
        stopping_rules=definition.evaluation_protocol.stopping_rules,
        # Forced: freezing is a researcher act, so an intake protocol is never frozen.
        frozen_at=None, frozen_by=None,
    )
    event = AuditEvent(
        id=oid(f"event.{slug}.problem_definition_recorded"), created_at=stamp, created_by=actor,
        aggregate_id=problem_id, event_type="problem_definition_recorded",
        payload=tuple(sorted((
            ("declared_domain", definition.declared_domain),
            ("intake_creates_no_warrant", "true"),
            ("originating_principal", actor.value),
            ("problem_definition_canonical_hash", definition.canonical_document_hash),
            ("problem_definition_id", slug),
            ("problem_definition_schema_version", definition.schema_version),
            ("target_claim_id", target_claim.id.value),
        ))),
        idempotency_key=f"problem-definition-recorded:{slug}:{definition.canonical_document_hash}",
    )
    return ResearchDossier(
        id=oid(f"dossier.{slug}.intake.sha256-{digest}"), created_at=stamp, created_by=actor,
        problem=problem, formalization=formalization, semantic_alignment=alignment,
        claims=(*assumption_claims, target_claim),
        warrants=(),
        evidence=(),
        source_applicability=(),
        obligations=(alignment_obligation, warrant_obligation),
        representation_maps=(),
        verification_records=(),
        evaluation_protocol=protocol,
        audit_events=(event,),
        capabilities=INTAKE_CAPABILITIES,
    )


def load_problem_definition(data: bytes, *, instant: datetime) -> ProblemIntakeResult:
    definition = parse_problem_definition(data)
    return ProblemIntakeResult(
        schema_version=PROBLEM_DEFINITION_SCHEMA_VERSION,
        definition=definition,
        dossier=build_dossier(definition, instant=instant),
        instant=instant.astimezone(timezone.utc),
    )


def load_problem_definition_file(path: Path, *, instant: datetime) -> ProblemIntakeResult:
    return load_problem_definition(path.read_bytes(), instant=instant)


# ---------------------------------------------------------------------------
# Derived JSON Schema. `schemas/problem-definition-v1.schema.json` is this
# value, so the published schema cannot drift from the Phase 1 enums.
# ---------------------------------------------------------------------------

def problem_definition_schema() -> dict[str, Any]:
    text = {"type": "string", "minLength": 1, "maxLength": MAX_SHORT_TEXT_LENGTH}
    statement = {"type": "string", "minLength": 1, "maxLength": MAX_STATEMENT_LENGTH}
    string_array = {
        "type": "array", "maxItems": MAX_LIST_ITEMS, "uniqueItems": True, "items": text,
    }
    pair_array = {
        "type": "array", "maxItems": MAX_LIST_ITEMS,
        "items": {"type": "array", "prefixItems": [text, text], "items": False, "minItems": 2, "maxItems": 2},
    }
    claim = {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(CLAIM_FIELDS),
        "properties": {
            "local_id": {"type": "string", "pattern": LOCAL_ID_PATTERN.pattern, "maxLength": 64},
            "kind": {"type": "string", "pattern": KIND_PATTERN.pattern, "maxLength": 64},
            "statement": statement,
            "scope": {"enum": list(INTAKE_CLAIM_SCOPES)},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROBLEM_DEFINITION_SCHEMA_ID,
        "title": "Declarative research problem definition",
        "description": (
            "Untrusted declarative intake for a research problem. Every enumerated value is "
            "derived from the Phase 1 domain enums in src/math_research/domain/entities.py. The "
            "grammar has no field for a warrant, evidence, verification record, source "
            "applicability record, representation map, proof status, confidence, novelty, "
            "significance, contribution, semantic-alignment approval, protocol freeze, or "
            "timestamp: defining a problem cannot create trust."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": sorted(DOCUMENT_FIELDS),
        "properties": {
            "schema_version": {"const": PROBLEM_DEFINITION_SCHEMA_VERSION},
            "problem_definition_id": {"type": "string", "pattern": SLUG_PATTERN.pattern, "maxLength": 96},
            "declared_domain": {"type": "string", "pattern": DOMAIN_PATTERN.pattern, "maxLength": 64},
            "originating_principal": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9._:-]*$", "maxLength": 96},
            "problem": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(PROBLEM_FIELDS),
                "properties": {
                    "title": {"type": "string", "minLength": 1, "maxLength": MAX_TITLE_LENGTH},
                    "informal_statement": statement,
                    "problem_type": {"enum": list(INTAKE_PROBLEM_TYPES)},
                    "tags": {"type": "array", "maxItems": MAX_LIST_ITEMS, "uniqueItems": True,
                             "items": {"type": "string", "minLength": 1, "maxLength": 64}},
                },
            },
            "target_claim": claim,
            "assumption_claims": {"type": "array", "maxItems": MAX_ASSUMPTION_CLAIMS, "items": claim},
            "formalization": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(FORMALIZATION_FIELDS),
                "properties": {
                    "version": {"type": "integer", "minimum": 1, "maximum": 9999},
                    "statement": statement,
                    "formal_language": {"type": "string", "pattern": FORMAL_LANGUAGE_PATTERN.pattern, "maxLength": 64},
                    "quantifiers": string_array,
                    "assumption_local_ids": {
                        "type": "array", "maxItems": MAX_LIST_ITEMS, "uniqueItems": True,
                        "items": {"type": "string", "pattern": LOCAL_ID_PATTERN.pattern, "maxLength": 64},
                    },
                    "approval_status": {"enum": list(INTAKE_APPROVAL_STATUSES)},
                },
            },
            "semantic_alignment": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(ALIGNMENT_FIELDS),
                "properties": {
                    "quantifier_mapping": pair_array,
                    "definition_mapping": pair_array,
                    "assumption_delta": string_array,
                    "edge_case_delta": string_array,
                    "strength_relation": {"enum": list(INTAKE_STRENGTH_RELATIONS)},
                },
            },
            "evaluation_protocol": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(PROTOCOL_FIELDS),
                "properties": {
                    "version": {"type": "integer", "minimum": 1, "maximum": 9999},
                    "phase": {"enum": list(INTAKE_PROTOCOL_PHASES)},
                    "metrics": string_array,
                    "success_criteria": string_array,
                    "stopping_rules": string_array,
                },
            },
        },
    }


def problem_definition_schema_text() -> str:
    return json.dumps(problem_definition_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
