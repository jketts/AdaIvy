"""Exact small-matrix checks for quantum-discrimination SDP candidates.

The spike validates supplied primal/dual candidates.  It does not search for a
solution, approximate eigenvalues, certify floating-point output, or alter the
Phase 5 benchmark implementation.

Arithmetic is exact over the algebraic field described in :mod:`algebraic`:
``Q(sqrt(d))(i)`` for one squarefree ``d`` per case, with ``d == 1`` meaning the
rational subfield.  Every check -- Hermiticity, positive semidefiniteness,
trace normalization, POVM completeness, dual domination, primal and dual
values, and two-sided complementarity -- runs over that field, so a certificate
whose entries are irrational is checked exactly rather than numerically.

Nothing here grants a mathematical warrant, integrates with Phase 5, or enables
search tiers 2--4.
"""

from __future__ import annotations

import json
from typing import Any, Sequence

from .algebraic import (
    AlgebraicComplex,
    AlgebraicFieldError,
    Quadratic,
    canonical_bytes,
    canonical_hash,
    common_radicand,
    field_descriptor,
    quadratic,
    reject_floats,
)
from .field_probe import SCHEMA_VERSION as PROBE_SCHEMA_VERSION
from .field_probe import exact_two_state_optimum, spectral_field_report, two_state_optimum
from .matrices import (
    MAX_DIMENSION,
    Matrix,
    all_values,
    canonical_matrix,
    commutator,
    identity,
    is_hermitian,
    is_positive_definite,
    is_psd,
    is_zero_matrix,
    multiply,
    parse_matrix,
    subtract,
    sum_matrices,
    trace,
)


SCHEMA_VERSION = "adaivy.phase5-noncommuting-sdp-spike.v2"
FIXTURE_SCHEMA_VERSION = "adaivy.phase5-noncommuting-sdp-fixtures.v2"
RESULT_SCHEMA_VERSION = "adaivy.phase5-noncommuting-sdp-validation.v2"
REPORT_SCHEMA_VERSION = "adaivy.phase5-noncommuting-sdp-report.v1"
MAX_OUTCOMES = 8

REQUIRED_CASE_FIELDS = frozenset(
    {
        "schema_version",
        "case_id",
        "weighted_states",
        "primal_povm",
        "dual_gamma",
        "expected_noncommuting",
        "expected_zero_gap",
        "expected_quadratic_representable",
        "expected_independent_optimum",
    }
)


class CertificateInputError(AlgebraicFieldError):
    """The exact candidate is malformed or violates a required constraint.

    A subclass of :class:`AlgebraicFieldError` so the spike has one error root:
    every rejection is a reject, and no path coerces an out-of-field value.
    """


def _matrix(value: Any, label: str) -> Matrix:
    try:
        return parse_matrix(value)
    except CertificateInputError:
        raise
    except AlgebraicFieldError as error:
        raise CertificateInputError(f"{label}: {error}") from error


def _shape_equal(matrices: Sequence[Matrix]) -> bool:
    return bool(matrices) and all(len(item) == len(matrices[0]) for item in matrices)


def _real(value: AlgebraicComplex, label: str) -> Quadratic:
    try:
        return value.real_part(label)
    except CertificateInputError:
        raise
    except AlgebraicFieldError as error:
        raise CertificateInputError(str(error)) from error


def _real_trace(matrix: Matrix, label: str) -> Quadratic:
    return _real(trace(matrix), f"{label} trace")


def _validate_psd(matrix: Matrix, label: str) -> None:
    if not is_hermitian(matrix):
        raise CertificateInputError(f"{label} is not Hermitian")
    if not is_psd(matrix):
        raise CertificateInputError(f"{label} is not positive semidefinite")


def _reject_floats(value: Any) -> None:
    try:
        reject_floats(value)
    except CertificateInputError:
        raise
    except AlgebraicFieldError as error:
        raise CertificateInputError(str(error)) from error


def _bool_field(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise CertificateInputError(f"{label} must be a boolean")
    return value


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CertificateInputError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_inexact(value: str) -> Any:
    raise CertificateInputError(
        f"the fixture contains the inexact numeric literal {value!r}; every "
        "value on the certificate path must be an exact integer, rational "
        "string, or canonical algebraic object"
    )


def load_document(text: str) -> dict[str, Any]:
    """Parse a fixture document, failing closed on floats and duplicate keys."""

    try:
        document = json.loads(
            text,
            object_pairs_hook=_no_duplicate_keys,
            parse_float=_reject_inexact,
            parse_constant=_reject_inexact,
        )
    except CertificateInputError:
        raise
    except json.JSONDecodeError as error:
        raise CertificateInputError(f"malformed fixture JSON: {error}") from error
    if not isinstance(document, dict):
        raise CertificateInputError("fixture document must be an object")
    _reject_floats(document)
    return document


def validate_fixture(value: dict[str, Any]) -> dict[str, Any]:
    """Validate one exact ensemble plus supplied primal and dual candidates."""

    if not isinstance(value, dict):
        raise CertificateInputError("fixture case must be an object")
    if set(value) != REQUIRED_CASE_FIELDS or value.get("schema_version") != SCHEMA_VERSION:
        raise CertificateInputError("fixture has missing, unknown, or unsupported fields")
    _reject_floats(value)
    expected_noncommuting = _bool_field(value["expected_noncommuting"], "expected_noncommuting")
    expected_zero_gap = _bool_field(value["expected_zero_gap"], "expected_zero_gap")
    expected_representable = _bool_field(
        value["expected_quadratic_representable"], "expected_quadratic_representable"
    )

    weighted_states = tuple(
        _matrix(item, f"weighted state {index}")
        for index, item in enumerate(value["weighted_states"])
    )
    povm = tuple(
        _matrix(item, f"POVM effect {index}") for index, item in enumerate(value["primal_povm"])
    )
    gamma = _matrix(value["dual_gamma"], "dual gamma")
    if not 1 <= len(weighted_states) <= MAX_OUTCOMES or len(povm) != len(weighted_states):
        raise CertificateInputError("outcome count is invalid")
    if not _shape_equal((*weighted_states, *povm, gamma)):
        raise CertificateInputError("matrix dimensions disagree")

    # One case lives in one quadratic extension.  A case mixing sqrt(2) and
    # sqrt(3) is rejected here rather than at the first arithmetic operation.
    try:
        radicand = common_radicand(all_values((*weighted_states, *povm, gamma)))
    except CertificateInputError:
        raise
    except AlgebraicFieldError as error:
        raise CertificateInputError(str(error)) from error

    traces: list[Quadratic] = []
    for index, state in enumerate(weighted_states):
        _validate_psd(state, f"weighted state {index}")
        state_trace = _real_trace(state, f"weighted state {index}")
        if state_trace.sign() <= 0:
            raise CertificateInputError("weighted-state priors must be positive")
        traces.append(state_trace)
    total_trace = traces[0]
    for item in traces[1:]:
        total_trace = total_trace + item
    if total_trace != quadratic(1):
        raise CertificateInputError("weighted-state traces must sum to one")
    total_state = sum_matrices(weighted_states)
    if not is_positive_definite(total_state):
        raise CertificateInputError("ensemble is not restricted to its effective support")

    for index, effect in enumerate(povm):
        _validate_psd(effect, f"POVM effect {index}")
    if sum_matrices(povm) != identity(len(gamma)):
        raise CertificateInputError("POVM effects do not sum to identity")

    _validate_psd(gamma, "dual gamma")
    slacks = tuple(subtract(gamma, state) for state in weighted_states)
    for index, slack in enumerate(slacks):
        _validate_psd(slack, f"dual slack {index}")

    primal_terms = tuple(
        _real_trace(multiply(state, effect), "primal term")
        for state, effect in zip(weighted_states, povm)
    )
    primal_value = primal_terms[0]
    for item in primal_terms[1:]:
        primal_value = primal_value + item
    dual_value = _real_trace(gamma, "dual objective")
    gap = dual_value - primal_value
    if gap.sign() < 0:
        raise AssertionError("exact weak duality was violated by feasible candidates")

    left_residuals = tuple(multiply(slack, effect) for slack, effect in zip(slacks, povm))
    right_residuals = tuple(multiply(effect, slack) for slack, effect in zip(slacks, povm))
    complementary = all(is_zero_matrix(item) for item in (*left_residuals, *right_residuals))
    exact_optimum = gap.sign() == 0 and complementary
    noncommuting = any(
        not is_zero_matrix(commutator(weighted_states[i], weighted_states[j]))
        for i in range(len(weighted_states))
        for j in range(i + 1, len(weighted_states))
    )

    difference = (
        subtract(weighted_states[0], weighted_states[1]) if len(weighted_states) == 2 else None
    )
    probe = (
        spectral_field_report(difference, "weighted_state_difference")
        if difference is not None
        else {
            "schema_version": PROBE_SCHEMA_VERSION,
            "operator": "weighted_state_difference",
            "determination": "not_applicable_outcome_count",
            "representable_in_quadratic_extension": False,
            "reason": (
                "the spectral field probe implemented here covers two outcomes only; "
                "no determination is claimed for this shape"
            ),
        }
    )
    representable = bool(probe["representable_in_quadratic_extension"])
    independent = two_state_optimum(weighted_states)
    independent_value = exact_two_state_optimum(weighted_states)

    if exact_optimum and independent_value is not None and primal_value != independent_value:
        raise AssertionError(
            "a zero-gap certificate disagreed with the independent closed-form optimum"
        )

    if noncommuting is not expected_noncommuting:
        raise CertificateInputError("fixture noncommutativity expectation disagrees with exact check")
    if exact_optimum is not expected_zero_gap:
        raise CertificateInputError("fixture exact-certificate expectation disagrees with residuals")
    if representable is not expected_representable:
        raise CertificateInputError(
            "fixture quadratic-representability expectation disagrees with the exact "
            "spectral field probe"
        )
    if value["expected_independent_optimum"] != independent["optimum"]:
        raise CertificateInputError(
            "fixture independent-optimum expectation disagrees with the exact closed form"
        )

    if exact_optimum:
        disposition = "exact_certificate_checked"
        blocked_reason = None
    elif representable:
        disposition = "candidate_only_unresolved"
        blocked_reason = (
            "No exact optimum certificate was supplied, although the exact optimum for "
            "this case is representable in the recorded quadratic extension; the "
            "supplied candidate is feasible but not optimal."
        )
    else:
        disposition = "candidate_only_outside_represented_field"
        blocked_reason = (
            "The exact optimum for this case is not representable in any quadratic "
            "extension of the rationals, so no certificate over this field can close "
            "the gap. " + str(probe.get("reason"))
        )

    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "case_id": value["case_id"],
        "arithmetic": "exact_algebraic_quadratic_complex",
        "field": field_descriptor(radicand),
        "dimension": len(gamma),
        "outcomes": len(weighted_states),
        "noncommuting": noncommuting,
        "weighted_state_traces": [item.canonical() for item in traces],
        "ensemble_effective_support": True,
        "povm_feasible": True,
        "dual_feasible": True,
        "primal_value": primal_value.canonical(),
        "dual_value": dual_value.canonical(),
        "primal_dual_gap": gap.canonical(),
        "primal_value_is_rational": primal_value.is_rational,
        "dual_value_is_rational": dual_value.is_rational,
        "left_complementarity_residuals": [canonical_matrix(item) for item in left_residuals],
        "right_complementarity_residuals": [canonical_matrix(item) for item in right_residuals],
        "complementarity_exact": complementary,
        "exact_optimum_certificate": exact_optimum,
        "independent_optimum": independent,
        "spectral_field_probe": probe,
        "optimum_representable_in_quadratic_extension": representable,
        "primal_matches_independent_optimum": (
            None if independent_value is None else primal_value == independent_value
        ),
        "dual_matches_independent_optimum": (
            None if independent_value is None else dual_value == independent_value
        ),
        "shortfall_to_independent_optimum": (
            None if independent_value is None else (independent_value - primal_value).canonical()
        ),
        "disposition": disposition,
        "blocked_without_solver": not exact_optimum,
        "blocked_reason": blocked_reason,
        "proposal_status": "candidate_check_only",
        "mathematical_warrant": "none_spike_only",
        "applicability_status": "spike_local",
        "graph_admitted": False,
        "phase5_integrated": False,
        "search_tiers_enabled": False,
    }
    result["content_hash"] = canonical_hash(result)
    return result


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    """Validate a whole frozen fixture document into one canonical report."""

    if not isinstance(document, dict):
        raise CertificateInputError("fixture document must be an object")
    if set(document) != {"schema_version", "cases"}:
        raise CertificateInputError("fixture document has missing or unknown fields")
    if document["schema_version"] != FIXTURE_SCHEMA_VERSION:
        raise CertificateInputError("fixture document schema version is unsupported")
    cases = document["cases"]
    if not isinstance(cases, list) or not cases:
        raise CertificateInputError("fixture document must carry a nonempty case list")
    versions = sorted({str(case.get("schema_version")) for case in cases if isinstance(case, dict)})
    if versions != [SCHEMA_VERSION]:
        raise CertificateInputError(
            "fixture document mixes or omits case schema versions: %s" % versions
        )
    results = [validate_fixture(case) for case in cases]
    identifiers = [item["case_id"] for item in results]
    if len(set(identifiers)) != len(identifiers):
        raise CertificateInputError("fixture document repeats a case identifier")
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "source_schema_version": document["schema_version"],
        "case_schema_version": SCHEMA_VERSION,
        "arithmetic": "exact_algebraic_quadratic_complex",
        "case_count": len(results),
        "results": results,
        "exact_certificate_case_ids": [
            item["case_id"] for item in results if item["exact_optimum_certificate"]
        ],
        "unresolved_case_ids": [
            item["case_id"]
            for item in results
            if not item["exact_optimum_certificate"]
            and item["optimum_representable_in_quadratic_extension"]
        ],
        "outside_field_case_ids": [
            item["case_id"]
            for item in results
            if not item["optimum_representable_in_quadratic_extension"]
        ],
        "radicands_used": sorted({item["field"]["radicand"] for item in results}),
        "phase5_integrated": False,
        "search_tiers_enabled": False,
        "mathematical_warrant": "none_spike_only",
    }
    report["content_hash"] = canonical_hash(report)
    return report


__all__ = [
    "FIXTURE_SCHEMA_VERSION",
    "MAX_DIMENSION",
    "MAX_OUTCOMES",
    "REPORT_SCHEMA_VERSION",
    "REQUIRED_CASE_FIELDS",
    "RESULT_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "CertificateInputError",
    "canonical_bytes",
    "load_document",
    "validate_document",
    "validate_fixture",
]
