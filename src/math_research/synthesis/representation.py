"""Version and representation disagreement warnings.

Contract Section 3.1: when two retained versions or representations of the same
source carry a material statement difference, the disagreement creates an
append-only warning and blocks silent selection. Section 2.2: the disputed
content cannot reach `source_checked` until the warning is resolved or the
fidelity record explicitly narrows itself to one identified representation.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .records import StructuredResearchResult, identifier, text
from .serialization import canonical_hash, stable_id
from .state import ExtractionFidelity, SynthesisValidationError

# Section 3.1 preferred reading order. Recorded so a warning can state which
# layer would have been preferred, while never selecting one automatically.
PREFERRED_ORDER: tuple[str, ...] = (
    "structured_html",
    "tex_source",
    "born_digital_pdf",
    "ocr_fallback",
    "plain_text",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RepresentationDisagreement:
    """One append-only disagreement warning over a single source."""

    warning_id: str
    source_id: str
    left_result_id: str
    right_result_id: str
    left_version: str
    right_version: str
    left_role: str
    right_role: str
    left_statement_hash: str
    right_statement_hash: str
    left_artifact_hash: str
    right_artifact_hash: str
    difference_kind: str

    def value(self) -> dict[str, Any]:
        return {
            "warning_id": self.warning_id,
            "source_id": self.source_id,
            "left_result_id": self.left_result_id,
            "right_result_id": self.right_result_id,
            "left_version": self.left_version,
            "right_version": self.right_version,
            "left_role": self.left_role,
            "right_role": self.right_role,
            "left_statement_hash": self.left_statement_hash,
            "right_statement_hash": self.right_statement_hash,
            "left_artifact_hash": self.left_artifact_hash,
            "right_artifact_hash": self.right_artifact_hash,
            "difference_kind": self.difference_kind,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class FidelityNarrowing:
    """An explicit narrowing to one identified representation (Section 2.2).

    This is the only way disputed content may reach `source_checked`: the
    fidelity record must name the exact representation it is scoped to, and the
    warning it resolves remains addressable.
    """

    narrowing_id: str
    warning_id: str
    source_id: str
    chosen_result_id: str
    chosen_role: str
    chosen_version: str
    rationale: str
    narrowed_by: str

    def value(self) -> dict[str, Any]:
        return {
            "narrowing_id": self.narrowing_id,
            "warning_id": self.warning_id,
            "source_id": self.source_id,
            "chosen_result_id": self.chosen_result_id,
            "chosen_role": self.chosen_role,
            "chosen_version": self.chosen_version,
            "rationale": self.rationale,
            "narrowed_by": self.narrowed_by,
        }


def detect_disagreements(
    results: Sequence[StructuredResearchResult],
) -> tuple[RepresentationDisagreement, ...]:
    """Find every material statement difference over a shared source.

    Two results disagree when they anchor the same source but carry different
    exact statements. The comparison is over the exact source statement, so a
    difference in normalized notation alone is not a disagreement.
    """
    warnings: list[RepresentationDisagreement] = []
    for left_index in range(len(results)):
        for right_index in range(left_index + 1, len(results)):
            left, right = results[left_index], results[right_index]
            if left.exact_statement == right.exact_statement:
                continue
            left_anchors = {anchor.source_id: anchor for anchor in left.anchors}
            for anchor in right.anchors:
                other = left_anchors.get(anchor.source_id)
                if other is None:
                    continue
                if other.source_version != anchor.source_version:
                    kind = "version_disagreement"
                elif other.representation_role != anchor.representation_role:
                    kind = "representation_disagreement"
                else:
                    # Same source, same version, same representation, yet a
                    # different exact statement: the extractions themselves
                    # disagree, which is the most serious of the three.
                    kind = "extraction_disagreement"
                # Endpoints are ordered by result id so the warning identity does
                # not depend on the order results were supplied in.
                first, second = sorted(
                    ((left, other), (right, anchor)), key=lambda pair: pair[0].result_id
                )
                warning_id = stable_id(
                    "representation-warning",
                    {
                        "source_id": anchor.source_id,
                        "left": first[0].result_id,
                        "right": second[0].result_id,
                        "difference_kind": kind,
                    },
                )
                warnings.append(
                    RepresentationDisagreement(
                        warning_id=warning_id,
                        source_id=anchor.source_id,
                        left_result_id=first[0].result_id,
                        right_result_id=second[0].result_id,
                        left_version=first[1].source_version,
                        right_version=second[1].source_version,
                        left_role=first[1].representation_role,
                        right_role=second[1].representation_role,
                        left_statement_hash=canonical_hash(first[0].exact_statement),
                        right_statement_hash=canonical_hash(second[0].exact_statement),
                        left_artifact_hash=first[1].artifact_hash,
                        right_artifact_hash=second[1].artifact_hash,
                        difference_kind=kind,
                    )
                )
    return tuple(sorted(warnings, key=lambda item: item.warning_id))


def narrow_fidelity(
    warning: RepresentationDisagreement,
    *,
    chosen: StructuredResearchResult,
    rationale: str,
    narrowed_by: str,
) -> FidelityNarrowing:
    """Explicitly narrow a disagreement to one identified representation."""
    identifier(narrowed_by, field="narrowed_by")
    text(rationale, field="rationale")
    if chosen.result_id not in {warning.left_result_id, warning.right_result_id}:
        raise SynthesisValidationError(
            "a narrowing must choose one of the two disagreeing representations"
        )
    anchor = next(
        (item for item in chosen.anchors if item.source_id == warning.source_id),
        None,
    )
    if anchor is None:
        raise SynthesisValidationError("the chosen result does not anchor the disputed source")
    return FidelityNarrowing(
        narrowing_id=stable_id(
            "fidelity-narrowing",
            {"warning_id": warning.warning_id, "chosen_result_id": chosen.result_id},
        ),
        warning_id=warning.warning_id,
        source_id=warning.source_id,
        chosen_result_id=chosen.result_id,
        chosen_role=anchor.representation_role,
        chosen_version=anchor.source_version,
        rationale=rationale,
        narrowed_by=narrowed_by,
    )


def permitted_fidelity(
    result: StructuredResearchResult,
    *,
    warnings: Sequence[RepresentationDisagreement],
    narrowings: Sequence[FidelityNarrowing] = (),
) -> ExtractionFidelity:
    """The strongest fidelity state a result may hold given open warnings.

    Section 2.2: a representation disagreement prevents `source_checked` for the
    disputed content until the warning is resolved or the fidelity record
    explicitly narrows itself to one identified representation.
    """
    resolved = {item.warning_id for item in narrowings}
    for warning in warnings:
        if result.result_id not in {warning.left_result_id, warning.right_result_id}:
            continue
        if warning.warning_id not in resolved:
            return ExtractionFidelity.PROPOSED_EXTRACTION
        narrowing = next(item for item in narrowings if item.warning_id == warning.warning_id)
        if narrowing.chosen_result_id != result.result_id:
            # The disagreement was narrowed to the other representation, so this
            # one is rejected rather than merely unresolved.
            return ExtractionFidelity.EXTRACTION_REJECTED
    return ExtractionFidelity.SOURCE_CHECKED


__all__ = [
    "PREFERRED_ORDER",
    "FidelityNarrowing",
    "RepresentationDisagreement",
    "detect_disagreements",
    "narrow_fidelity",
    "permitted_fidelity",
]
