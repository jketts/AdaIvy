"""Graph admission under a named, versioned, deterministic policy.

Contract Section 2.4. Admission means inclusion in one deterministic research
view. It never means universally true, novel, significant, or permanently valid.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import ADMISSION_POLICY_VERSION
from .composition import CompositionComparison
from .records import StateAxes, content_hash_value, identifier, text
from .serialization import stable_id
from .state import (
    EFFECTIVE_APPLICABLE,
    ExtractionFidelity,
    GraphAdmission,
    MathematicalWarrant,
    SourceApplicability,
    SynthesisValidationError,
    parse_enum,
)


class ExclusionReason:
    """Closed exclusion vocabulary, so a reason is never free text."""

    APPLICABILITY_NOT_EFFECTIVE = "applicability_not_effective"
    EXTRACTION_NOT_CHECKED = "extraction_fidelity_not_source_checked"
    WARRANT_NOT_PERMITTED = "mathematical_warrant_not_in_permitted_set"
    COMPOSITION_MISMATCH = "composition_mismatch"
    INFLUENCE_CLOSURE_INVALIDATED = "influence_closure_invalidated"
    ALREADY_INVALIDATED = "invalidated_by_later_record"

    ALL = frozenset(
        {
            APPLICABILITY_NOT_EFFECTIVE,
            EXTRACTION_NOT_CHECKED,
            WARRANT_NOT_PERMITTED,
            COMPOSITION_MISMATCH,
            INFLUENCE_CLOSURE_INVALIDATED,
            ALREADY_INVALIDATED,
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class AdmissionPolicy:
    """One named research view's admission requirements.

    `permitted_warrants` is authoritative. `minimum_documented_warrant` is
    recorded for human readers only and is deliberately never consulted:
    Section 2.4 forbids inferring that one warrant state sits above another, so
    a documented minimum cannot widen or narrow the permitted set.
    """

    view_id: str
    policy_version: str
    required_applicability: SourceApplicability
    required_fidelity: ExtractionFidelity
    minimum_documented_warrant: MathematicalWarrant
    permitted_warrants: frozenset[MathematicalWarrant]

    def __post_init__(self) -> None:
        identifier(self.view_id, field="view_id")
        text(self.policy_version, field="policy_version")
        if not self.permitted_warrants:
            raise SynthesisValidationError(
                "an admission policy must name at least one permitted mathematical-warrant state"
            )
        # A policy that requires anything other than the effective Phase 4A
        # checked/applicable state would admit unreviewed source material.
        if self.required_applicability is not EFFECTIVE_APPLICABLE:
            raise SynthesisValidationError(
                "admission requires the effective checked source-applicability state"
            )
        if self.required_fidelity is not ExtractionFidelity.SOURCE_CHECKED:
            raise SynthesisValidationError(
                "admission requires the source_checked extraction-fidelity state"
            )
        if self.minimum_documented_warrant not in self.permitted_warrants:
            raise SynthesisValidationError(
                "the documented minimum warrant must itself be in the permitted set"
            )

    @classmethod
    def create(
        cls,
        *,
        view_id: str,
        permitted_warrants: Iterable[MathematicalWarrant | str],
        minimum_documented_warrant: MathematicalWarrant | str,
        policy_version: str = ADMISSION_POLICY_VERSION,
    ) -> AdmissionPolicy:
        permitted = frozenset(
            parse_enum(MathematicalWarrant, item, field="permitted_warrants[]")
            for item in permitted_warrants
        )
        return cls(
            view_id=view_id,
            policy_version=policy_version,
            required_applicability=EFFECTIVE_APPLICABLE,
            required_fidelity=ExtractionFidelity.SOURCE_CHECKED,
            minimum_documented_warrant=parse_enum(
                MathematicalWarrant, minimum_documented_warrant, field="minimum_documented_warrant"
            ),
            permitted_warrants=permitted,
        )

    @classmethod
    def from_value(cls, value: object) -> AdmissionPolicy:
        fields = frozenset(
            {
                "view_id",
                "policy_version",
                "required_applicability",
                "required_fidelity",
                "minimum_documented_warrant",
                "permitted_warrants",
            }
        )
        if not isinstance(value, Mapping) or set(value) != fields:
            raise SynthesisValidationError("admission policy field set is not exact")
        permitted = value["permitted_warrants"]
        if isinstance(permitted, (str, bytes)) or not isinstance(permitted, Sequence):
            raise SynthesisValidationError("permitted_warrants must be a list")
        return cls(
            view_id=value["view_id"],
            policy_version=value["policy_version"],
            required_applicability=parse_enum(
                SourceApplicability,
                value["required_applicability"],
                field="required_applicability",
            ),
            required_fidelity=parse_enum(
                ExtractionFidelity, value["required_fidelity"], field="required_fidelity"
            ),
            minimum_documented_warrant=parse_enum(
                MathematicalWarrant,
                value["minimum_documented_warrant"],
                field="minimum_documented_warrant",
            ),
            permitted_warrants=frozenset(
                parse_enum(MathematicalWarrant, item, field="permitted_warrants[]")
                for item in permitted
            ),
        )
    def value(self) -> dict[str, Any]:
        return {
            "view_id": self.view_id,
            "policy_version": self.policy_version,
            "required_applicability": self.required_applicability.value,
            "required_fidelity": self.required_fidelity.value,
            "minimum_documented_warrant": self.minimum_documented_warrant.value,
            "permitted_warrants": sorted(item.value for item in self.permitted_warrants),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AdmissionRecord:
    """The complete admission decision for one result or relation."""

    admission_id: str
    subject_id: str
    subject_kind: str
    decision: GraphAdmission
    exclusion_reasons: tuple[str, ...]
    exclusion_detail: tuple[str, ...]
    policy: AdmissionPolicy
    evaluated_axes: StateAxes
    input_record_ids: tuple[str, ...]
    influence_closure_id: str
    admitting_actor_id: str
    admitting_authority: str

    def admitted(self) -> bool:
        return self.decision is GraphAdmission.ADMITTED_UNDER_POLICY

    def value(self) -> dict[str, Any]:
        return {
            "admission_id": self.admission_id,
            "subject_id": self.subject_id,
            "subject_kind": self.subject_kind,
            "decision": self.decision.value,
            "exclusion_reasons": list(self.exclusion_reasons),
            "exclusion_detail": list(self.exclusion_detail),
            "policy": self.policy.value(),
            "evaluated_axes": self.evaluated_axes.value(),
            "input_record_ids": list(self.input_record_ids),
            "influence_closure_id": self.influence_closure_id,
            "admitting_actor_id": self.admitting_actor_id,
            "admitting_authority": self.admitting_authority,
        }


def evaluate_admission(
    policy: AdmissionPolicy,
    *,
    subject_id: str,
    subject_kind: str,
    axes: StateAxes,
    input_record_ids: Sequence[str],
    influence_closure_id: str,
    admitting_actor_id: str,
    admitting_authority: str,
    comparisons: Sequence[CompositionComparison] = (),
    closure_invalidated: bool = False,
) -> AdmissionRecord:
    """Deterministically decide admission for one result or relation.

    Every requirement is evaluated independently and every failed requirement is
    reported, so an excluded subject carries the complete reason set rather than
    only the first failure.
    """
    identifier(subject_id, field="subject_id")
    identifier(admitting_actor_id, field="admitting_actor_id")
    content_hash_value(influence_closure_id, field="influence_closure_id")
    if subject_kind not in {"structured_result", "result_relation", "composition"}:
        raise SynthesisValidationError(f"unknown admission subject kind: {subject_kind}")

    reasons: list[str] = []
    detail: list[str] = []

    if axes.graph_admission is GraphAdmission.INVALIDATED_BY_LATER_RECORD:
        reasons.append(ExclusionReason.ALREADY_INVALIDATED)
        detail.append("a later append-only record already invalidated this subject")

    if axes.source_applicability is not policy.required_applicability:
        reasons.append(ExclusionReason.APPLICABILITY_NOT_EFFECTIVE)
        detail.append(
            f"effective source applicability is {axes.source_applicability.value}, "
            f"policy requires {policy.required_applicability.value}"
        )

    if axes.extraction_fidelity is not policy.required_fidelity:
        reasons.append(ExclusionReason.EXTRACTION_NOT_CHECKED)
        detail.append(
            f"extraction fidelity is {axes.extraction_fidelity.value}, "
            f"policy requires {policy.required_fidelity.value}"
        )

    # Explicit set membership only. No comparison operator is applied to the
    # warrant axis anywhere in this function.
    if axes.mathematical_warrant not in policy.permitted_warrants:
        reasons.append(ExclusionReason.WARRANT_NOT_PERMITTED)
        detail.append(
            f"mathematical warrant {axes.mathematical_warrant.value} is not in the permitted set "
            f"{{{', '.join(sorted(item.value for item in policy.permitted_warrants))}}}"
        )

    for comparison in comparisons:
        if not comparison.compatible:
            reasons.append(ExclusionReason.COMPOSITION_MISMATCH)
            for kind in comparison.mismatch_kinds():
                detail.append(f"composition {comparison.comparison_id} has {kind}")

    if closure_invalidated:
        reasons.append(ExclusionReason.INFLUENCE_CLOSURE_INVALIDATED)
        detail.append("an input in the influence closure is no longer current")

    unknown = set(reasons) - ExclusionReason.ALL
    if unknown:
        raise SynthesisValidationError(f"exclusion reason outside the closed vocabulary: {unknown}")

    decision = (
        GraphAdmission.EXCLUDED_UNDER_POLICY if reasons else GraphAdmission.ADMITTED_UNDER_POLICY
    )
    ordered_inputs = tuple(identifier(item, field="input_record_ids[]") for item in input_record_ids)
    admission_id = stable_id(
        "admission",
        {
            "subject_id": subject_id,
            "policy": policy.value(),
            "axes": axes.value(),
            "inputs": sorted(ordered_inputs),
            "influence_closure_id": influence_closure_id,
            "decision": decision.value,
            "reasons": sorted(set(reasons)),
        },
    )
    return AdmissionRecord(
        admission_id=admission_id,
        subject_id=subject_id,
        subject_kind=subject_kind,
        decision=decision,
        exclusion_reasons=tuple(sorted(set(reasons))),
        exclusion_detail=tuple(sorted(set(detail))),
        policy=policy,
        evaluated_axes=axes,
        input_record_ids=ordered_inputs,
        influence_closure_id=influence_closure_id,
        admitting_actor_id=admitting_actor_id,
        admitting_authority=admitting_authority,
    )


__all__ = ["AdmissionPolicy", "AdmissionRecord", "ExclusionReason", "evaluate_admission"]
