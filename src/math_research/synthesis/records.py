"""Structured result and relation model.

Contract Section 4, with the four independent state-axis records of Section 2
attached separately to every result and every relation. A relation never
inherits an endpoint's states.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .serialization import canonical_hash, public_value, stable_id
from .state import (
    ExtractionFidelity,
    GraphAdmission,
    MathematicalWarrant,
    RelationType,
    SourceApplicability,
    StageOutcome,
    SynthesisValidationError,
    ValueEnum,
    VerificationStage,
    parse_enum,
)

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
MAX_TEXT_BYTES = 8192
MAX_LIST_ITEMS = 32


class NoveltyStatus(ValueEnum):
    """Orthogonal novelty status (Sections 4 and 8).

    Deliberately has no value asserting novelty. Section 8 requires that search
    noncoverage be recorded as `search_incomplete` or `not_found_under_protocol`
    and never as novel, and automated novelty assessment is out of scope, so no
    value here can express a positive novelty claim.
    """

    NOT_ASSESSED = "not_assessed"
    SEARCH_INCOMPLETE = "search_incomplete"
    NOT_FOUND_UNDER_PROTOCOL = "not_found_under_protocol"
    KNOWN_PRIOR_RESULT = "known_prior_result"


class QuantifierKind(ValueEnum):
    UNIVERSAL = "universal"
    EXISTENTIAL = "existential"
    UNIQUE_EXISTENTIAL = "unique_existential"
    BOUNDED_UNIVERSAL = "bounded_universal"
    BOUNDED_EXISTENTIAL = "bounded_existential"


def identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.match(value):
        raise SynthesisValidationError(f"{field} must match {IDENTIFIER.pattern}")
    return value


def text(value: object, *, field: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SynthesisValidationError(f"{field} must be a string")
    if not allow_empty and not value:
        raise SynthesisValidationError(f"{field} must be non-empty")
    if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        raise SynthesisValidationError(f"{field} exceeds {MAX_TEXT_BYTES} UTF-8 bytes")
    return value


def content_hash_value(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.match(value):
        raise SynthesisValidationError(f"{field} must be a sha256: hash")
    return value


def text_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SynthesisValidationError(f"{field} must be a list of strings")
    if len(value) > MAX_LIST_ITEMS:
        raise SynthesisValidationError(f"{field} exceeds {MAX_LIST_ITEMS} items")
    return tuple(text(item, field=f"{field}[]") for item in value)


def _exact_fields(value: object, *, expected: frozenset[str], label: str) -> Mapping[str, Any]:
    """Fail closed on both missing and unknown fields."""
    if not isinstance(value, Mapping):
        raise SynthesisValidationError(f"{label} must be an object")
    observed = set(value)
    missing = sorted(expected - observed)
    unknown = sorted(observed - expected)
    if missing:
        raise SynthesisValidationError(f"{label} missing fields: {', '.join(missing)}")
    if unknown:
        raise SynthesisValidationError(f"{label} has unknown fields: {', '.join(unknown)}")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceAnchor:
    """Exact source identity, version, and span anchors (Section 3.2).

    `evidence_card_id` is the Phase 4A card the anchor was excerpted through, so
    an anchor cannot exist without a rights-gated, span-verified excerpt.
    """

    source_id: str
    source_version: str
    representation_role: str
    artifact_hash: str
    span_ids: tuple[str, ...]
    evidence_card_id: str

    FIELDS = frozenset(
        {
            "source_id",
            "source_version",
            "representation_role",
            "artifact_hash",
            "span_ids",
            "evidence_card_id",
        }
    )
    # Section 3.1 preferred reading order. The order grants no acquisition or
    # use authority; it only names which retained layer an anchor points at.
    ROLES = frozenset({"structured_html", "tex_source", "born_digital_pdf", "ocr_fallback", "plain_text"})

    def __post_init__(self) -> None:
        identifier(self.source_id, field="source_id")
        text(self.source_version, field="source_version")
        identifier(self.evidence_card_id, field="evidence_card_id")
        content_hash_value(self.artifact_hash, field="artifact_hash")
        if self.representation_role not in self.ROLES:
            raise SynthesisValidationError(
                f"representation_role must be one of: {', '.join(sorted(self.ROLES))}"
            )
        if not self.span_ids:
            raise SynthesisValidationError("source anchor requires at least one span")
        for span in self.span_ids:
            identifier(span, field="span_ids[]")
        if len(set(self.span_ids)) != len(self.span_ids):
            raise SynthesisValidationError("source anchor span ids must be distinct")

    @classmethod
    def from_value(cls, value: object) -> SourceAnchor:
        data = _exact_fields(value, expected=cls.FIELDS, label="source anchor")
        return cls(
            source_id=data["source_id"],
            source_version=data["source_version"],
            representation_role=data["representation_role"],
            artifact_hash=data["artifact_hash"],
            span_ids=tuple(data["span_ids"]),
            evidence_card_id=data["evidence_card_id"],
        )

    def value(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_version": self.source_version,
            "representation_role": self.representation_role,
            "artifact_hash": self.artifact_hash,
            "span_ids": list(self.span_ids),
            "evidence_card_id": self.evidence_card_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class NotationTransformation:
    """An explicit normalization record (Section 4).

    Notation normalization never establishes equivalence by itself, so this
    record carries no equivalence verdict at all. Establishing an equivalence
    requires a separate `equivalent_to` relation with its own state axes.
    """

    rule_id: str
    rule_version: str
    original_notation: str
    normalized_notation: str
    definition_mapping: tuple[tuple[str, str], ...]

    FIELDS = frozenset(
        {"rule_id", "rule_version", "original_notation", "normalized_notation", "definition_mapping"}
    )

    def __post_init__(self) -> None:
        identifier(self.rule_id, field="rule_id")
        text(self.rule_version, field="rule_version")
        text(self.original_notation, field="original_notation")
        text(self.normalized_notation, field="normalized_notation")

    @classmethod
    def from_value(cls, value: object) -> NotationTransformation:
        data = _exact_fields(value, expected=cls.FIELDS, label="notation transformation")
        mapping = data["definition_mapping"]
        if not isinstance(mapping, Sequence) or isinstance(mapping, (str, bytes)):
            raise SynthesisValidationError("definition_mapping must be a list of pairs")
        pairs: list[tuple[str, str]] = []
        for entry in mapping:
            item = _exact_fields(entry, expected=frozenset({"symbol", "definition"}), label="definition mapping")
            pairs.append((text(item["symbol"], field="symbol"), text(item["definition"], field="definition")))
        return cls(
            rule_id=data["rule_id"],
            rule_version=data["rule_version"],
            original_notation=data["original_notation"],
            normalized_notation=data["normalized_notation"],
            definition_mapping=tuple(sorted(pairs)),
        )

    def value(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "original_notation": self.original_notation,
            "normalized_notation": self.normalized_notation,
            "definition_mapping": [
                {"symbol": symbol, "definition": definition}
                for symbol, definition in self.definition_mapping
            ],
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StateAxes:
    """The four independent axes for one result or relation (Section 2)."""

    source_applicability: SourceApplicability
    extraction_fidelity: ExtractionFidelity
    mathematical_warrant: MathematicalWarrant
    graph_admission: GraphAdmission

    FIELDS = frozenset(
        {"source_applicability", "extraction_fidelity", "mathematical_warrant", "graph_admission"}
    )

    @classmethod
    def initial(cls) -> StateAxes:
        """The only state a freshly extracted proposal may hold."""
        return cls(
            source_applicability=SourceApplicability.PROPOSED,
            extraction_fidelity=ExtractionFidelity.PROPOSED_EXTRACTION,
            mathematical_warrant=MathematicalWarrant.UNASSESSED,
            graph_admission=GraphAdmission.PROPOSED,
        )

    @classmethod
    def from_value(cls, value: object) -> StateAxes:
        data = _exact_fields(value, expected=cls.FIELDS, label="state axes")
        return cls(
            source_applicability=parse_enum(
                SourceApplicability, data["source_applicability"], field="source_applicability"
            ),
            extraction_fidelity=parse_enum(
                ExtractionFidelity, data["extraction_fidelity"], field="extraction_fidelity"
            ),
            mathematical_warrant=parse_enum(
                MathematicalWarrant, data["mathematical_warrant"], field="mathematical_warrant"
            ),
            graph_admission=parse_enum(GraphAdmission, data["graph_admission"], field="graph_admission"),
        )

    def value(self) -> dict[str, Any]:
        return {
            "source_applicability": self.source_applicability.value,
            "extraction_fidelity": self.extraction_fidelity.value,
            "mathematical_warrant": self.mathematical_warrant.value,
            "graph_admission": self.graph_admission.value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredResearchResult:
    """One source-anchored extraction proposal (Section 4).

    The extraction never replaces the source statement: `exact_statement` is the
    verbatim source text and `normalized_notation` is a separate, transformation-
    recorded rendering of it.
    """

    result_id: str
    exact_statement: str
    notation: NotationTransformation
    assumptions: tuple[str, ...]
    domains: tuple[str, ...]
    codomains: tuple[str, ...]
    object_types: tuple[str, ...]
    regularity: tuple[str, ...]
    quantifiers: tuple[tuple[str, QuantifierKind, str], ...]
    conclusion: str
    conclusion_strength: str
    scope: tuple[str, ...]
    exceptions: tuple[str, ...]
    proof_technique: str
    dependencies: tuple[str, ...]
    limitations: tuple[str, ...]
    anchors: tuple[SourceAnchor, ...]
    axes: StateAxes
    confidence_proposal: str
    extraction_method: str
    extraction_version: str
    known_counterexamples: tuple[str, ...]
    novelty_status: NoveltyStatus

    FIELDS = frozenset(
        {
            "result_id",
            "exact_statement",
            "notation",
            "assumptions",
            "domains",
            "codomains",
            "object_types",
            "regularity",
            "quantifiers",
            "conclusion",
            "conclusion_strength",
            "scope",
            "exceptions",
            "proof_technique",
            "dependencies",
            "limitations",
            "anchors",
            "axes",
            "confidence_proposal",
            "extraction_method",
            "extraction_version",
            "known_counterexamples",
            "novelty_status",
        }
    )
    STRENGTHS = frozenset({"exact", "asymptotic", "bounded", "existential_witness", "conditional"})

    def __post_init__(self) -> None:
        identifier(self.result_id, field="result_id")
        text(self.exact_statement, field="exact_statement")
        text(self.conclusion, field="conclusion")
        text(self.proof_technique, field="proof_technique")
        text(self.extraction_method, field="extraction_method")
        text(self.extraction_version, field="extraction_version")
        # Section 4: the confidence proposal is explicitly non-authoritative, so
        # it is recorded as free text and never as a number that could be
        # compared, ranked, or thresholded into a trust decision.
        text(self.confidence_proposal, field="confidence_proposal")
        if self.conclusion_strength not in self.STRENGTHS:
            raise SynthesisValidationError(
                f"conclusion_strength must be one of: {', '.join(sorted(self.STRENGTHS))}"
            )
        if not self.anchors:
            raise SynthesisValidationError("a structured result requires at least one source anchor")
        if not self.quantifiers:
            raise SynthesisValidationError("a structured result must declare its quantifiers")
        if not self.domains:
            raise SynthesisValidationError("a structured result must declare its domains")

    @classmethod
    def from_value(cls, value: object) -> StructuredResearchResult:
        data = _exact_fields(value, expected=cls.FIELDS, label="structured result")
        quantifiers: list[tuple[str, QuantifierKind, str]] = []
        raw = data["quantifiers"]
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise SynthesisValidationError("quantifiers must be a list")
        for entry in raw:
            item = _exact_fields(
                entry, expected=frozenset({"variable", "kind", "bound"}), label="quantifier"
            )
            quantifiers.append(
                (
                    text(item["variable"], field="quantifier.variable"),
                    parse_enum(QuantifierKind, item["kind"], field="quantifier.kind"),
                    text(item["bound"], field="quantifier.bound", allow_empty=True),
                )
            )
        anchors = data["anchors"]
        if isinstance(anchors, (str, bytes)) or not isinstance(anchors, Sequence):
            raise SynthesisValidationError("anchors must be a list")
        return cls(
            result_id=data["result_id"],
            exact_statement=data["exact_statement"],
            notation=NotationTransformation.from_value(data["notation"]),
            assumptions=text_tuple(data["assumptions"], field="assumptions"),
            domains=text_tuple(data["domains"], field="domains"),
            codomains=text_tuple(data["codomains"], field="codomains"),
            object_types=text_tuple(data["object_types"], field="object_types"),
            regularity=text_tuple(data["regularity"], field="regularity"),
            quantifiers=tuple(quantifiers),
            conclusion=data["conclusion"],
            conclusion_strength=data["conclusion_strength"],
            scope=text_tuple(data["scope"], field="scope"),
            exceptions=text_tuple(data["exceptions"], field="exceptions"),
            proof_technique=data["proof_technique"],
            dependencies=text_tuple(data["dependencies"], field="dependencies"),
            limitations=text_tuple(data["limitations"], field="limitations"),
            anchors=tuple(SourceAnchor.from_value(item) for item in anchors),
            axes=StateAxes.from_value(data["axes"]),
            confidence_proposal=data["confidence_proposal"],
            extraction_method=data["extraction_method"],
            extraction_version=data["extraction_version"],
            known_counterexamples=text_tuple(
                data["known_counterexamples"], field="known_counterexamples"
            ),
            novelty_status=parse_enum(NoveltyStatus, data["novelty_status"], field="novelty_status"),
        )

    def value(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "exact_statement": self.exact_statement,
            "notation": self.notation.value(),
            "assumptions": list(self.assumptions),
            "domains": list(self.domains),
            "codomains": list(self.codomains),
            "object_types": list(self.object_types),
            "regularity": list(self.regularity),
            "quantifiers": [
                {"variable": variable, "kind": kind.value, "bound": bound}
                for variable, kind, bound in self.quantifiers
            ],
            "conclusion": self.conclusion,
            "conclusion_strength": self.conclusion_strength,
            "scope": list(self.scope),
            "exceptions": list(self.exceptions),
            "proof_technique": self.proof_technique,
            "dependencies": list(self.dependencies),
            "limitations": list(self.limitations),
            "anchors": [anchor.value() for anchor in self.anchors],
            "axes": self.axes.value(),
            "confidence_proposal": self.confidence_proposal,
            "extraction_method": self.extraction_method,
            "extraction_version": self.extraction_version,
            "known_counterexamples": list(self.known_counterexamples),
            "novelty_status": self.novelty_status.value,
        }

    def semantic_digest(self) -> str:
        """Identity of the mathematical content, independent of its axes.

        The four axes are excluded so that recording a verification outcome does
        not change which result the record refers to.
        """
        payload = self.value()
        payload.pop("axes")
        return canonical_hash(payload)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultRelation:
    """An attributed relation proposal with its own four state axes (Section 4).

    A relation never inherits an endpoint's states, so `axes` here is entirely
    separate from either endpoint's axes.
    """

    relation_id: str
    relation_type: RelationType
    source_result_id: str
    source_result_digest: str
    target_result_id: str
    target_result_digest: str
    proposer_id: str
    extractor_id: str
    evidence_anchors: tuple[SourceAnchor, ...]
    comparison_rationale: str
    open_obligation_ids: tuple[str, ...]
    axes: StateAxes

    FIELDS = frozenset(
        {
            "relation_id",
            "relation_type",
            "source_result_id",
            "source_result_digest",
            "target_result_id",
            "target_result_digest",
            "proposer_id",
            "extractor_id",
            "evidence_anchors",
            "comparison_rationale",
            "open_obligation_ids",
            "axes",
        }
    )

    def __post_init__(self) -> None:
        identifier(self.relation_id, field="relation_id")
        identifier(self.source_result_id, field="source_result_id")
        identifier(self.target_result_id, field="target_result_id")
        identifier(self.proposer_id, field="proposer_id")
        identifier(self.extractor_id, field="extractor_id")
        content_hash_value(self.source_result_digest, field="source_result_digest")
        content_hash_value(self.target_result_digest, field="target_result_digest")
        text(self.comparison_rationale, field="comparison_rationale")
        if self.source_result_id == self.target_result_id:
            raise SynthesisValidationError("a relation requires two distinct endpoints")

    @classmethod
    def from_value(cls, value: object) -> ResultRelation:
        data = _exact_fields(value, expected=cls.FIELDS, label="result relation")
        anchors = data["evidence_anchors"]
        if isinstance(anchors, (str, bytes)) or not isinstance(anchors, Sequence):
            raise SynthesisValidationError("evidence_anchors must be a list")
        obligations = data["open_obligation_ids"]
        if isinstance(obligations, (str, bytes)) or not isinstance(obligations, Sequence):
            raise SynthesisValidationError("open_obligation_ids must be a list")
        return cls(
            relation_id=data["relation_id"],
            relation_type=parse_enum(RelationType, data["relation_type"], field="relation_type"),
            source_result_id=data["source_result_id"],
            source_result_digest=data["source_result_digest"],
            target_result_id=data["target_result_id"],
            target_result_digest=data["target_result_digest"],
            proposer_id=data["proposer_id"],
            extractor_id=data["extractor_id"],
            evidence_anchors=tuple(SourceAnchor.from_value(item) for item in anchors),
            comparison_rationale=data["comparison_rationale"],
            open_obligation_ids=tuple(
                identifier(item, field="open_obligation_ids[]") for item in obligations
            ),
            axes=StateAxes.from_value(data["axes"]),
        )

    def value(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "relation_type": self.relation_type.value,
            "source_result_id": self.source_result_id,
            "source_result_digest": self.source_result_digest,
            "target_result_id": self.target_result_id,
            "target_result_digest": self.target_result_digest,
            "proposer_id": self.proposer_id,
            "extractor_id": self.extractor_id,
            "evidence_anchors": [anchor.value() for anchor in self.evidence_anchors],
            "comparison_rationale": self.comparison_rationale,
            "open_obligation_ids": list(self.open_obligation_ids),
            "axes": self.axes.value(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class VerificationExecution:
    """One stage-execution record (Section 9).

    Not a state-axis value. Only the authority defined for an axis may append
    that axis's state record, and it must cite these executions.
    """

    execution_id: str
    subject_id: str
    stage: VerificationStage
    outcome: StageOutcome
    method: str
    executed_by: str
    detail: str

    FIELDS = frozenset(
        {"execution_id", "subject_id", "stage", "outcome", "method", "executed_by", "detail"}
    )

    def __post_init__(self) -> None:
        identifier(self.execution_id, field="execution_id")
        identifier(self.subject_id, field="subject_id")
        identifier(self.executed_by, field="executed_by")
        text(self.method, field="method")
        text(self.detail, field="detail")

    @classmethod
    def create(
        cls,
        *,
        subject_id: str,
        stage: VerificationStage,
        outcome: StageOutcome,
        method: str,
        executed_by: str,
        detail: str,
    ) -> VerificationExecution:
        execution_id = stable_id(
            "verification-execution",
            {"subject_id": subject_id, "stage": stage.value, "method": method},
        )
        return cls(
            execution_id=execution_id,
            subject_id=subject_id,
            stage=stage,
            outcome=outcome,
            method=method,
            executed_by=executed_by,
            detail=detail,
        )

    @classmethod
    def from_value(cls, value: object) -> VerificationExecution:
        data = _exact_fields(value, expected=cls.FIELDS, label="verification execution")
        return cls(
            execution_id=data["execution_id"],
            subject_id=data["subject_id"],
            stage=parse_enum(VerificationStage, data["stage"], field="stage"),
            outcome=parse_enum(StageOutcome, data["outcome"], field="outcome"),
            method=data["method"],
            executed_by=data["executed_by"],
            detail=data["detail"],
        )

    def value(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "subject_id": self.subject_id,
            "stage": self.stage.value,
            "outcome": self.outcome.value,
            "method": self.method,
            "executed_by": self.executed_by,
            "detail": self.detail,
        }


__all__ = [
    "HASH_PATTERN",
    "IDENTIFIER",
    "MAX_LIST_ITEMS",
    "MAX_TEXT_BYTES",
    "NotationTransformation",
    "NoveltyStatus",
    "QuantifierKind",
    "ResultRelation",
    "SourceAnchor",
    "StateAxes",
    "StructuredResearchResult",
    "VerificationExecution",
    "content_hash_value",
    "identifier",
    "public_value",
    "text",
    "text_tuple",
]
