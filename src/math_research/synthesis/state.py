"""The four independent state axes and the closed vocabularies around them.

Contract Section 2. Every structured result and relation exposes four axes. No
value on one axis implies a value on another, so this module deliberately
provides no ordering, no comparison, and no aggregate "confidence" projection.
"""

from __future__ import annotations

from enum import Enum


class ValueEnum(str, Enum):
    """String enum so `.value` and direct string comparison both work.

    Ordering is deliberately suppressed. None of the four state axes is a scale,
    and Section 2.4 requires admission policy to evaluate an explicit permitted
    set rather than infer that one warrant state sits above another. Inheriting
    `str` would otherwise supply a silent lexicographic order, making
    `counterexample_found < proof_reviewed` evaluate to a meaningless True.
    """

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.value

    def __lt__(self, other: object) -> bool:
        raise TypeError(f"{type(self).__name__} is not ordered; compare an explicit permitted set")

    __le__ = __lt__
    __gt__ = __lt__
    __ge__ = __lt__


class SynthesisValidationError(ValueError):
    """Fail-closed rejection of a synthesis record, policy, or transition."""


# --- Axis 1: source applicability (Section 2.1) ------------------------------
# Imported from the effective Phase 4A human ApplicabilityReview. Only Phase 4A
# named-human authority may produce the effective checked/applicable outcome.
class SourceApplicability(ValueEnum):
    PROPOSED = "proposed"
    CHECKED = "checked"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


# --- Axis 2: extraction fidelity (Section 2.2) ------------------------------
class ExtractionFidelity(ValueEnum):
    PROPOSED_EXTRACTION = "proposed_extraction"
    SOURCE_CHECKED = "source_checked"
    EXTRACTION_REJECTED = "extraction_rejected"


# --- Axis 3: mathematical warrant (Section 2.3) -----------------------------
# NOT a confidence scale. counterexample_found is a refutation outcome, not a
# rung toward proof, so admission policy must name an explicit permitted set.
class MathematicalWarrant(ValueEnum):
    UNASSESSED = "unassessed"
    EMPIRICALLY_TESTED = "empirically_tested"
    COUNTEREXAMPLE_FOUND = "counterexample_found"
    PROOF_REVIEWED = "proof_reviewed"
    FORMALLY_VERIFIED = "formally_verified"


# --- Axis 4: graph admission (Section 2.4) ----------------------------------
class GraphAdmission(ValueEnum):
    PROPOSED = "proposed"
    ADMITTED_UNDER_POLICY = "admitted_under_policy"
    EXCLUDED_UNDER_POLICY = "excluded_under_policy"
    INVALIDATED_BY_LATER_RECORD = "invalidated_by_later_record"


# --- Relations (Section 4) --------------------------------------------------
class RelationType(ValueEnum):
    DEPENDS_ON = "depends_on"
    IMPLIES = "implies"
    EQUIVALENT_TO = "equivalent_to"
    STRONGER_THAN = "stronger_than"
    WEAKER_THAN = "weaker_than"
    SPECIALIZES = "specializes"
    GENERALIZES = "generalizes"
    CONTRADICTS = "contradicts"
    USES_SAME_TECHNIQUE = "uses_same_technique"
    REQUIRES_BRIDGE = "requires_bridge"


# --- Verification funnel (Section 9) ---------------------------------------
# Stage-execution records, explicitly NOT state-axis values.
class VerificationStage(ValueEnum):
    SOURCE_FAITHFUL_EXTRACTION = "source_faithful_extraction"
    LOGICAL_COMPATIBILITY = "logical_compatibility"
    NUMERICAL_SYMBOLIC_TESTING = "numerical_symbolic_testing"
    COUNTEREXAMPLE_SEARCH = "counterexample_search"
    PROOF_REVIEW = "proof_review"
    FORMAL_VERIFICATION = "formal_verification"
    INDEPENDENT_REVIEW = "independent_review"
    HUMAN_ACCEPTANCE = "human_acceptance"


class StageOutcome(ValueEnum):
    NOT_RUN = "not_run"
    BLOCKED = "blocked"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    PASSED = "passed"


# --- Composition mismatch vocabulary (Section 8) ----------------------------
# Closed set. A mismatch outside this vocabulary fails closed rather than being
# recorded as free text, so ERS-AC-02/03/04 can assert an exact reason.
class MismatchKind(ValueEnum):
    ASSUMPTION = "assumption_mismatch"
    QUANTIFIER = "quantifier_mismatch"
    DOMAIN = "domain_mismatch"
    CODOMAIN = "codomain_mismatch"
    OBJECT_TYPE = "object_type_mismatch"
    REGULARITY = "regularity_mismatch"
    DEFINITION = "definition_mismatch"
    NOTATION = "notation_mismatch"
    SCOPE_OR_EXCEPTION = "scope_or_exception_mismatch"
    SOURCE_VERSION = "source_version_mismatch"
    CONCLUSION_STRENGTH = "conclusion_strength_mismatch"
    CONSUMED_TERM = "consumed_term_mismatch"
    IMPLICATION_DIRECTION = "implication_direction_mismatch"


# --- Strategy families (Section 7) -----------------------------------------
class StrategyFamily(ValueEnum):
    DIRECT_PROOF = "direct_proof"
    COUNTEREXAMPLE_SEARCH = "counterexample_search"
    RESTRICTED_CASES = "restricted_cases"
    COMPUTATIONAL_EXPERIMENTATION = "computational_experimentation"
    ALTERNATIVE_FORMULATION = "alternative_formulation"
    CROSS_DOMAIN_TRANSFER = "cross_domain_transfer"
    MULTI_PAPER_COMPOSITION = "multi_paper_composition"
    FORMALIZATION_VERIFICATION = "formalization_verification"


# --- Terminal reasons (Section 5) ------------------------------------------
TERMINAL_COMPLETED = "completed"
TERMINAL_CONVERGED = "converged_under_rule"
TERMINAL_USER_INTERVENTION = "user_intervention"
_TERMINAL_BARE = frozenset({TERMINAL_COMPLETED, TERMINAL_CONVERGED, TERMINAL_USER_INTERVENTION})


def budget_exhausted(counter: str) -> str:
    """`budget_exhausted:<counter>` terminal reason."""
    if not counter or ":" in counter:
        raise SynthesisValidationError("budget counter name must be non-empty and colon-free")
    return f"budget_exhausted:{counter}"


def blocked(reason: str) -> str:
    """`blocked:<reason>` terminal reason."""
    if not reason or ":" in reason:
        raise SynthesisValidationError("blocked reason must be non-empty and colon-free")
    return f"blocked:{reason}"


def validate_terminal_reason(value: str) -> str:
    """Exactly one deterministic terminal reason per run (Section 5)."""
    if value in _TERMINAL_BARE:
        return value
    for prefix in ("budget_exhausted:", "blocked:"):
        if value.startswith(prefix):
            suffix = value[len(prefix):]
            if suffix and ":" not in suffix:
                return value
            raise SynthesisValidationError(f"malformed terminal reason: {value}")
    raise SynthesisValidationError(f"unknown terminal reason: {value}")


def parse_enum(enum_type: type[ValueEnum], value: object, *, field: str) -> ValueEnum:
    """Fail-closed enum parse that names the field and the closed vocabulary."""
    if isinstance(value, enum_type):
        return value
    if isinstance(value, bool) or not isinstance(value, str):
        raise SynthesisValidationError(f"{field} must be a string from a closed vocabulary")
    try:
        return enum_type(value)
    except ValueError:
        allowed = ", ".join(sorted(item.value for item in enum_type))
        raise SynthesisValidationError(f"{field} must be one of: {allowed}") from None


# The effective Phase 4A state that permits any downstream synthesis use. A
# result is eligible only when its imported review is exactly checked/applicable;
# rejected and unresolved both fail closed (Section 11).
EFFECTIVE_APPLICABLE = SourceApplicability.CHECKED

__all__ = [
    "EFFECTIVE_APPLICABLE",
    "ExtractionFidelity",
    "GraphAdmission",
    "MathematicalWarrant",
    "MismatchKind",
    "RelationType",
    "SourceApplicability",
    "StageOutcome",
    "StrategyFamily",
    "SynthesisValidationError",
    "TERMINAL_COMPLETED",
    "TERMINAL_CONVERGED",
    "TERMINAL_USER_INTERVENTION",
    "ValueEnum",
    "VerificationStage",
    "blocked",
    "budget_exhausted",
    "parse_enum",
    "validate_terminal_reason",
]
