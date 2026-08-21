"""Bounded exact discovery for two-outcome, two-dimensional ensembles.

ADR-0049 promotes the exact spectral construction measured by ADR-0045.  The
constructor proposes a primal/dual pair; it cannot accept its own result.  The
candidate is passed to ``noncommuting.verify_exact_certificate_candidate``,
whose exact PSD, weak-duality, zero-gap, and complementarity checks are the only
authority.  No float, tolerance, numerical engine, model, or network call is
used on this path.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping

from .algebraic import (
    RATIONAL_ZERO,
    AlgebraicComplex,
    AlgebraicFieldError,
    HigherDegreeExtensionError,
    Quadratic,
    exact_hash,
)
from .exact_matrices import (
    Matrix,
    add,
    canonical_matrix,
    determinant,
    identity,
    is_hermitian,
    scale,
    subtract,
    sum_matrices,
    trace,
    zero,
)
from .noncommuting import (
    BENCHMARK_ID,
    NoncommutingCase,
    parse_fixture,
    verify_exact_certificate_candidate,
)

SOLVER_SCHEMA_VERSION = "adaivy.phase5-noncommuting-exact-solver.v1"
SOLVER_REPORT_VERSION = "adaivy.phase5-noncommuting-exact-solver-report.v1"
SUPPORTED_OUTCOMES = 2
SUPPORTED_DIMENSION = 2

STATUS_VERIFIED = "discovered_and_exactly_verified"
STATUS_UNSUPPORTED = "unresolved_unsupported_shape"
STATUS_OUTSIDE_FIELD = "unresolved_outside_represented_field"
STATUS_REFUTED = "candidate_refuted_by_exact_verifier"
SOLVER_STATUSES = (STATUS_VERIFIED, STATUS_UNSUPPORTED, STATUS_OUTSIDE_FIELD, STATUS_REFUTED)


@dataclass(frozen=True, slots=True)
class GeneratedCertificate:
    """A solver-produced candidate, explicitly distinct from human input."""

    primal_povm: tuple[Matrix, ...]
    dual_gamma: Matrix
    construction: str

    def provenance(self) -> dict[str, Any]:
        return {
            "admitted_through": "bounded_exact_solver_candidate_boundary",
            "certificate_origin": "system_generated",
            "construction": self.construction,
            "deriving_principal_id": "component.phase5.exact-spectral-solver",
            "system_generated": True,
        }


def _real(value: AlgebraicComplex, label: str) -> Quadratic:
    return value.real_part(label)


def _as_scalar(value: Quadratic) -> AlgebraicComplex:
    return AlgebraicComplex(value, RATIONAL_ZERO)


def _unresolved(case: NoncommutingCase, status: str, reason_code: str, detail: str) -> dict[str, Any]:
    result = {
        "schema_version": SOLVER_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "case_id": case.case_id,
        "solver_status": status,
        "reason_code": reason_code,
        "detail": detail,
        "bounded_shape": {"outcomes": SUPPORTED_OUTCOMES, "dimension": SUPPORTED_DIMENSION},
        "candidate_constructed": False,
        "exact_verification_performed": False,
        "optimum_discovered": False,
        "mathematical_warrant": "none_unresolved",
        "tolerance": None,
        "uses_floating_point": False,
        "uses_model": False,
        "uses_network": False,
        "search_tiers_enabled": False,
    }
    result["result_hash"] = exact_hash(result)
    return result


def solve_case(case: NoncommutingCase) -> dict[str, Any]:
    """Construct and exactly verify the supported Helstrom certificate."""

    states = case.weighted_states
    if len(states) != SUPPORTED_OUTCOMES:
        return _unresolved(
            case, STATUS_UNSUPPORTED, "outcome_count_outside_bounded_solver",
            f"the solver covers exactly {SUPPORTED_OUTCOMES} outcomes; this case has {len(states)}",
        )
    if len(states[0]) != SUPPORTED_DIMENSION:
        return _unresolved(
            case, STATUS_UNSUPPORTED, "dimension_outside_bounded_solver",
            f"the solver covers dimension {SUPPORTED_DIMENSION}; this case has {len(states[0])}",
        )

    difference = subtract(states[0], states[1])
    if not is_hermitian(difference):
        return _unresolved(case, STATUS_REFUTED, "difference_not_hermitian", "W0-W1 is not Hermitian")
    difference_trace = _real(trace(difference), "difference trace")
    difference_determinant = _real(determinant(difference), "difference determinant")
    discriminant = difference_trace * difference_trace - Quadratic(Fraction(4), Fraction(0), 1) * difference_determinant
    try:
        root = discriminant.exact_sqrt()
    except HigherDegreeExtensionError as error:
        return _unresolved(case, STATUS_OUTSIDE_FIELD, error.reason_code, str(error))
    except AlgebraicFieldError as error:
        return _unresolved(case, STATUS_REFUTED, error.reason_code, str(error))

    half = Quadratic(Fraction(1, 2), Fraction(0), 1)
    lambda_plus = (difference_trace + root) * half
    lambda_minus = (difference_trace - root) * half
    unit = identity(SUPPORTED_DIMENSION)
    if root.is_zero():
        effect_zero = unit if lambda_plus.sign() > 0 else zero(SUPPORTED_DIMENSION)
        positive_part = difference if lambda_plus.sign() > 0 else zero(SUPPORTED_DIMENSION)
        construction = "repeated_eigenvalue_scalar_matrix"
    else:
        projector_plus = scale(
            subtract(difference, scale(unit, _as_scalar(lambda_minus))),
            _as_scalar(root.reciprocal()),
        )
        projector_minus = subtract(unit, projector_plus)
        positive_effects: list[Matrix] = []
        positive_parts: list[Matrix] = []
        for eigenvalue, projector in (
            (lambda_plus, projector_plus), (lambda_minus, projector_minus)
        ):
            if eigenvalue.sign() > 0:
                positive_effects.append(projector)
                positive_parts.append(scale(projector, _as_scalar(eigenvalue)))
        effect_zero = (
            sum_matrices(positive_effects) if positive_effects else zero(SUPPORTED_DIMENSION)
        )
        positive_part = (
            sum_matrices(positive_parts) if positive_parts else zero(SUPPORTED_DIMENSION)
        )
        construction = "helstrom_positive_spectral_projector"
    effect_one = subtract(unit, effect_zero)
    gamma = add(states[1], positive_part)
    candidate = GeneratedCertificate((effect_zero, effect_one), gamma, construction)
    checked = verify_exact_certificate_candidate(case, candidate)
    verified = checked["accepted"]
    result = {
        "schema_version": SOLVER_SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "case_id": case.case_id,
        "solver_status": STATUS_VERIFIED if verified else STATUS_REFUTED,
        "reason_code": None if verified else "exact_verifier_rejected_candidate",
        "bounded_shape": {"outcomes": SUPPORTED_OUTCOMES, "dimension": SUPPORTED_DIMENSION},
        "candidate_constructed": True,
        "candidate": {
            "construction": construction,
            "dual_gamma": canonical_matrix(gamma),
            "primal_povm": [canonical_matrix(item) for item in candidate.primal_povm],
            "provenance": candidate.provenance(),
        },
        "characteristic_data": {
            "trace": difference_trace.canonical(),
            "determinant": difference_determinant.canonical(),
            "discriminant": discriminant.canonical(),
            "lambda_plus": lambda_plus.canonical(),
            "lambda_minus": lambda_minus.canonical(),
        },
        "exact_verification_performed": True,
        "exact_verification": checked,
        "optimum_discovered": verified,
        "mathematical_warrant": (
            "exact_noncommuting_certificate_verification" if verified else "none_unresolved"
        ),
        "tolerance": None,
        "uses_floating_point": False,
        "uses_model": False,
        "uses_network": False,
        "search_tiers_enabled": False,
    }
    result["result_hash"] = exact_hash(result)
    return result


def solve_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Solve every case independently and preserve every unresolved outcome."""

    cases = parse_fixture(fixture)
    results = [solve_case(case) for case in cases]
    counts = {status: sum(item["solver_status"] == status for item in results) for status in SOLVER_STATUSES}
    report = {
        "schema_version": SOLVER_REPORT_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "solver": "bounded_exact_helstrom_two_outcome_dimension_two",
        "bounded_shape": {"outcomes": SUPPORTED_OUTCOMES, "dimension": SUPPORTED_DIMENSION},
        "exact_verifier_is_final_authority": True,
        "general_noncommuting_convergence_answered": False,
        "status_counts": counts,
        "results": results,
        "tolerance": None,
        "uses_floating_point": False,
        "uses_model": False,
        "uses_network": False,
        "search_tiers_enabled": False,
    }
    report["content_hash"] = exact_hash(report)
    return report


__all__ = [
    "GeneratedCertificate", "SOLVER_REPORT_VERSION", "SOLVER_SCHEMA_VERSION",
    "SOLVER_STATUSES", "STATUS_OUTSIDE_FIELD", "STATUS_REFUTED", "STATUS_UNSUPPORTED",
    "STATUS_VERIFIED", "SUPPORTED_DIMENSION", "SUPPORTED_OUTCOMES", "solve_case",
    "solve_fixture",
]
