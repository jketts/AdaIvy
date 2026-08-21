"""Exact noncommuting quantum-discrimination certificate verification.

ADR-0035 scopes this module precisely, and each boundary is enforced here rather
than described.

**Verification only, never discovery.** The module admits a certificate and
checks primal feasibility, dual feasibility, and an exactly closed gap.  There
is no search, no iteration toward an optimum, and no candidate generation: the
only construction site of :class:`SuppliedCertificate` is its own
``from_value`` parser, and a case arriving *without* a certificate produces an
explicit unresolved outcome rather than an attempt or a silent default.  The
independent closed-form cross-check in :mod:`math_research.phase5.spectrum`
yields a scalar, never a POVM or a dual operator, so it cannot stand in for a
certificate: an uncertificated case stays unresolved even where the cross-check
is available.

**Certificate provenance is recorded.** Every certificate carries the principal
that derived it and the derivation it came from.  A certificate with no recorded
principal is a typed rejection, and a certificate declaring a solver or
discovery origin is rejected outright.

**Coverage status is mandatory.** Every result carries ``coverage_status`` from
one frozen vocabulary.  ``optimum_discovered`` is named as forbidden and is
unproducible: :func:`_checked_coverage_status` admits only the frozen values.
The honest risk ADR-0035 names is a coverage illusion -- exactly-zero gaps read
as "noncommuting is handled" when only two-outcome ensembles with a
human-derived Helstrom closed form are.  The measured cubic boundary stays in
the fixtures so the limit is visible in every run.

**Field boundary.** ``Q(sqrt d)(i)`` for one squarefree ``d`` per case, with the
radicand measured from the case values rather than declared.  Two distinct
surds, a cubic or higher irreducible extension, a declared transcendental value,
and any float or tolerance are typed rejections.

**Search tiers 2--4 stay disabled**, unchanged by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from . import (
    NONCOMMUTING_CASE_VERSION,
    NONCOMMUTING_FIXTURE_VERSION,
    NONCOMMUTING_REPORT_VERSION,
    NONCOMMUTING_RESULT_VERSION,
)
from .algebraic import (
    FIELD_REJECTION_CODES,
    AlgebraicFieldError,
    Quadratic,
    exact_hash,
    field_descriptor,
    join_radicands,
    measure_radicand,
    quadratic,
    reject_inexact,
)
from .exact_matrices import (
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
from .spectrum import PROBE_SCHEMA_VERSION, closed_form_crosscheck, closed_form_optimum, spectral_field_report

MAX_OUTCOMES = 8

BENCHMARK_ID = "QD-NC-01"

# -- coverage vocabulary ---------------------------------------------------
#
# ADR-0035 requires a machine-readable field distinguishing a verified supplied
# certificate from a discovered optimum.  The forbidden value is named so a
# reader can check its absence, and it is unproducible by construction.
COVERAGE_CERTIFICATE_VERIFIED = "certificate_supplied_and_verified"
COVERAGE_GAP_NOT_CLOSED = "certificate_supplied_gap_not_closed"
COVERAGE_OUTSIDE_FIELD = "certificate_supplied_outside_represented_field"
COVERAGE_REFUTED = "certificate_supplied_and_refuted"
COVERAGE_UNRESOLVED = "unresolved_no_certificate_supplied"
FORBIDDEN_COVERAGE_STATUS = "optimum_discovered"
COVERAGE_STATUSES = (
    COVERAGE_CERTIFICATE_VERIFIED,
    COVERAGE_GAP_NOT_CLOSED,
    COVERAGE_OUTSIDE_FIELD,
    COVERAGE_REFUTED,
    COVERAGE_UNRESOLVED,
)

COVERED_FAMILY = "two_outcome_ensembles_with_a_human_derived_closed_form_certificate"
COVERAGE_STATEMENT = (
    "This slice verifies certificates supplied to it and never discovers them. "
    "Only instances whose optimum a human already derived in closed form are "
    "covered, which is a small structured family. It does not answer general "
    "noncommuting JRF convergence, and an exactly zero gap on a covered case is "
    "not evidence of reach."
)

# Recorded derivations.  A certificate that declares a machine origin is
# rejected: it may not be laundered through the human-steering boundary.  This
# is a declaration check, not detection -- nothing here can tell a hand
# derivation from a transcribed solver output.
HUMAN_DERIVATIONS = (
    "hand_derived_by_inspection",
    "hand_derived_from_helstrom_closed_form",
)
PROHIBITED_DERIVATIONS = (
    "interval_arithmetic",
    "numerical_solver",
    "residual_reconstruction",
    "search",
    "solver_output",
)

CERTIFICATE_BOUNDARY = "authorized_human_steering"

REQUIRED_CASE_FIELDS = frozenset(
    {
        "case_id",
        "certificate",
        "expected_coverage_status",
        "expected_noncommuting",
        "expected_optimum_representable",
        "expected_primal_dual_gap",
        "schema_version",
        "weighted_states",
    }
)
REQUIRED_CERTIFICATE_FIELDS = frozenset(
    {"derivation", "deriving_principal_id", "dual_gamma", "primal_povm"}
)


class CertificateInputError(AlgebraicFieldError):
    """A supplied case or certificate is malformed or violates a constraint."""

    reason_code = "malformed_certificate_input"


class CertificateProvenanceError(CertificateInputError):
    """A certificate arrived without a recorded deriving principal."""

    reason_code = "certificate_without_recorded_principal"


class DiscoveryProhibitedError(CertificateInputError):
    """A certificate declared a solver, search, or discovery origin."""

    reason_code = "discovery_or_solver_origin_prohibited"


def _bool_field(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise CertificateInputError(f"{label} must be a boolean")
    return value


def _text_field(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CertificateInputError(f"{label} must be a nonempty string")
    return value


def _typed(error: AlgebraicFieldError, label: str) -> AlgebraicFieldError:
    """Re-raise a field rejection with context, PRESERVING its exact type.

    ADR-0035 requires explicit typed failures, so a mixed radicand must not
    arrive at the caller as a generic input error.
    """

    return type(error)(f"{label}: {error}")


def _matrix(value: Any, label: str) -> Matrix:
    try:
        return parse_matrix(value)
    except CertificateInputError:
        raise
    except AlgebraicFieldError as error:
        raise _typed(error, label) from error


def _real(matrix: Matrix, label: str) -> Quadratic:
    try:
        return trace(matrix).real_part(f"{label} trace")
    except CertificateInputError:
        raise
    except AlgebraicFieldError as error:
        raise _typed(error, label) from error


def _measure(values: Any, label: str) -> int:
    try:
        return measure_radicand(values)
    except CertificateInputError:
        raise
    except AlgebraicFieldError as error:
        raise _typed(error, label) from error


def _reject_inexact(value: Any, label: str) -> None:
    try:
        reject_inexact(value)
    except CertificateInputError:
        raise
    except AlgebraicFieldError as error:
        raise _typed(error, label) from error


@dataclass(frozen=True, slots=True)
class SuppliedCertificate:
    """A human-derived primal/dual certificate admitted for checking.

    The only construction site is :meth:`from_value`, which parses recorded
    input.  Nothing in this package computes one.
    """

    primal_povm: tuple[Matrix, ...]
    dual_gamma: Matrix
    deriving_principal_id: str
    derivation: str
    boundary: str

    @classmethod
    def from_value(cls, value: Any, *, case_id: str) -> "SuppliedCertificate":
        if not isinstance(value, dict):
            raise CertificateInputError("certificate must be an object")
        keys = frozenset(value)
        if "deriving_principal_id" not in keys:
            raise CertificateProvenanceError(
                f"the certificate for {case_id!r} records no deriving principal; a "
                "certificate is a human input and its provenance is mandatory"
            )
        if keys != REQUIRED_CERTIFICATE_FIELDS:
            raise CertificateInputError("certificate has missing or unknown fields")
        _reject_inexact(value, "certificate")
        principal_id = value["deriving_principal_id"]
        if not isinstance(principal_id, str) or not principal_id:
            raise CertificateProvenanceError(
                f"the certificate for {case_id!r} records an empty deriving principal"
            )
        derivation = _text_field(value["derivation"], "certificate derivation")
        if derivation in PROHIBITED_DERIVATIONS:
            raise DiscoveryProhibitedError(
                f"derivation {derivation!r} declares a discovery or solver origin; "
                "ADR-0035 admits verification of human-derived certificates only"
            )
        if derivation not in HUMAN_DERIVATIONS:
            raise CertificateInputError(f"unrecorded certificate derivation {derivation!r}")
        povm = value["primal_povm"]
        if not isinstance(povm, list) or not povm:
            raise CertificateInputError("primal_povm must be a nonempty array")
        return cls(
            primal_povm=tuple(
                _matrix(item, f"POVM effect {index}") for index, item in enumerate(povm)
            ),
            dual_gamma=_matrix(value["dual_gamma"], "dual gamma"),
            deriving_principal_id=principal_id,
            derivation=derivation,
            boundary=CERTIFICATE_BOUNDARY,
        )

    def provenance(self) -> dict[str, Any]:
        return {
            "admitted_through": self.boundary,
            "certificate_origin": "human_supplied",
            "derivation": self.derivation,
            "deriving_principal_id": self.deriving_principal_id,
            "system_generated": False,
        }


@dataclass(frozen=True, slots=True)
class NoncommutingCase:
    """One exact ensemble plus, optionally, one supplied certificate."""

    case_id: str
    weighted_states: tuple[Matrix, ...]
    certificate: SuppliedCertificate | None
    expected_noncommuting: bool
    expected_optimum_representable: bool
    expected_coverage_status: str
    expected_primal_dual_gap: Any

    @classmethod
    def from_value(cls, value: Any) -> "NoncommutingCase":
        if not isinstance(value, dict):
            raise CertificateInputError("noncommuting case must be an object")
        if set(value) != REQUIRED_CASE_FIELDS:
            raise CertificateInputError("noncommuting case has missing or unknown fields")
        if value["schema_version"] != NONCOMMUTING_CASE_VERSION:
            raise CertificateInputError("unsupported noncommuting case schema version")
        _reject_inexact(value, "case")
        case_id = _text_field(value["case_id"], "case_id")
        states = value["weighted_states"]
        if not isinstance(states, list) or not states:
            raise CertificateInputError("weighted_states must be a nonempty array")
        expected_status = _text_field(
            value["expected_coverage_status"], "expected_coverage_status"
        )
        if expected_status not in COVERAGE_STATUSES:
            raise CertificateInputError(
                f"expected_coverage_status {expected_status!r} is not in the frozen "
                "coverage vocabulary"
            )
        raw_certificate = value["certificate"]
        certificate = (
            None
            if raw_certificate is None
            else SuppliedCertificate.from_value(raw_certificate, case_id=case_id)
        )
        if certificate is None and expected_status != COVERAGE_UNRESOLVED:
            raise CertificateInputError(
                "a case with no certificate can only expect "
                f"{COVERAGE_UNRESOLVED!r}, never {expected_status!r}"
            )
        return cls(
            case_id=case_id,
            weighted_states=tuple(
                _matrix(item, f"weighted state {index}") for index, item in enumerate(states)
            ),
            certificate=certificate,
            expected_noncommuting=_bool_field(
                value["expected_noncommuting"], "expected_noncommuting"
            ),
            expected_optimum_representable=_bool_field(
                value["expected_optimum_representable"], "expected_optimum_representable"
            ),
            expected_coverage_status=expected_status,
            expected_primal_dual_gap=value["expected_primal_dual_gap"],
        )


def _checked_coverage_status(status: str) -> str:
    """Admit only the frozen vocabulary; ``optimum_discovered`` is unproducible."""

    if status == FORBIDDEN_COVERAGE_STATUS or status not in COVERAGE_STATUSES:
        raise AssertionError(
            f"coverage status {status!r} is not producible by this module; "
            "ADR-0035 forbids reporting a discovered optimum"
        )
    return status


def validate_ensemble(weighted_states: Sequence[Matrix]) -> tuple[Quadratic, ...]:
    """Exact ensemble domain checks.  A violation is a reject, not a finding."""

    if not 1 <= len(weighted_states) <= MAX_OUTCOMES:
        raise CertificateInputError("outcome count is outside the exact Phase 5 bound")
    size = len(weighted_states[0])
    if size > MAX_DIMENSION or any(len(item) != size for item in weighted_states):
        raise CertificateInputError("weighted-state dimensions disagree")
    traces: list[Quadratic] = []
    for index, state in enumerate(weighted_states):
        label = f"weighted state {index}"
        if not is_hermitian(state):
            raise CertificateInputError(f"{label} is not Hermitian")
        if not is_psd(state):
            raise CertificateInputError(f"{label} is not positive semidefinite")
        value = _real(state, label)
        if value.sign() <= 0:
            raise CertificateInputError("weighted-state priors must be positive")
        traces.append(value)
    total = traces[0]
    for item in traces[1:]:
        total = total + item
    if total != quadratic(1):
        raise CertificateInputError("weighted-state traces must sum to one")
    if not is_positive_definite(sum_matrices(list(weighted_states))):
        raise CertificateInputError("ensemble is not restricted to its effective support")
    return tuple(traces)


def _field_probe(weighted_states: tuple[Matrix, ...]) -> dict[str, Any]:
    if len(weighted_states) == 2:
        return spectral_field_report(
            subtract(weighted_states[0], weighted_states[1]), "weighted_state_difference"
        )
    return {
        "schema_version": PROBE_SCHEMA_VERSION,
        "determination": "not_applicable_outcome_count",
        "distinguishes_high_degree_from_transcendental": False,
        "operator": "weighted_state_difference",
        "reason": (
            "the exact spectral field probe implemented here covers two outcomes only; "
            "no determination is claimed for this shape, which under-claims "
            "representability rather than over-claiming it"
        ),
        "representable_in_quadratic_extension": False,
        "tolerance": None,
    }


def _coverage(status: str, certificate: SuppliedCertificate | None) -> dict[str, Any]:
    return {
        "covered_family": COVERED_FAMILY,
        "certificate_origin": "human_supplied" if certificate else "none_supplied",
        "discovery_performed": False,
        "general_noncommuting_convergence_answered": False,
        "read_coverage_before_gap": True,
        "statement": COVERAGE_STATEMENT,
        "status": _checked_coverage_status(status),
        "status_vocabulary": list(COVERAGE_STATUSES),
        "unproducible_status": FORBIDDEN_COVERAGE_STATUS,
    }


def _unresolved_result(
    *,
    traces: tuple[Quadratic, ...],
    radicand: int,
    noncommuting: bool,
    probe: dict[str, Any],
    crosscheck: dict[str, Any],
) -> dict[str, Any]:
    return {
        "coverage": _coverage(COVERAGE_UNRESOLVED, None),
        "coverage_status": _checked_coverage_status(COVERAGE_UNRESOLVED),
        "certificate_provenance": None,
        "certificate_supplied": False,
        "complementarity_exact": None,
        "dual_feasible": None,
        "dual_value": None,
        "independent_closed_form_crosscheck": crosscheck,
        "left_complementarity_residuals": None,
        "primal_dual_gap": None,
        "primal_feasible": None,
        "primal_value": None,
        "refutation_reasons": [],
        "right_complementarity_residuals": None,
        "unresolved_reason": (
            "No certificate was supplied for this case. ADR-0035 scopes this module to "
            "verification, so it neither searched for one nor defaulted to any "
            "candidate. The independent closed-form cross-check yields a scalar and no "
            "POVM or dual operator, so it cannot stand in for a certificate."
        ),
        "weighted_state_traces": [item.canonical() for item in traces],
        "_shared": {
            "radicand": radicand,
            "noncommuting": noncommuting,
            "probe": probe,
        },
    }


def _certificate_result(
    case: NoncommutingCase,
    certificate: SuppliedCertificate,
    *,
    traces: tuple[Quadratic, ...],
    ensemble_radicand: int,
    noncommuting: bool,
    probe: dict[str, Any],
    crosscheck: dict[str, Any],
) -> dict[str, Any]:
    size = len(case.weighted_states[0])
    if len(certificate.primal_povm) != len(case.weighted_states):
        raise CertificateInputError("certificate outcome count differs from the ensemble")
    if len(certificate.dual_gamma) != size or any(
        len(item) != size for item in certificate.primal_povm
    ):
        raise CertificateInputError("certificate dimensions differ from the ensemble")
    certificate_radicand = _measure(
        all_values((*certificate.primal_povm, certificate.dual_gamma)), "certificate"
    )
    try:
        radicand = join_radicands(ensemble_radicand, certificate_radicand)
    except AlgebraicFieldError as error:
        raise _typed(error, "case field") from error

    refutations: list[str] = []
    for index, effect in enumerate(certificate.primal_povm):
        if not is_hermitian(effect):
            refutations.append(f"POVM effect {index} is not Hermitian")
        elif not is_psd(effect):
            refutations.append(f"POVM effect {index} is not positive semidefinite")
    if sum_matrices(list(certificate.primal_povm)) != identity(size):
        refutations.append("POVM effects do not sum to the identity")
    primal_feasible = not refutations

    gamma = certificate.dual_gamma
    dual_reasons: list[str] = []
    if not is_hermitian(gamma):
        dual_reasons.append("dual operator is not Hermitian")
    elif not is_psd(gamma):
        dual_reasons.append("dual operator is not positive semidefinite")
    slacks: tuple[Matrix, ...] = tuple(
        subtract(gamma, state) for state in case.weighted_states
    )
    if not dual_reasons:
        for index, slack in enumerate(slacks):
            if not is_psd(slack):
                dual_reasons.append(f"dual domination Gamma >= A_{index} fails")
    dual_feasible = not dual_reasons
    refutations.extend(dual_reasons)

    primal_value: Quadratic | None = None
    dual_value: Quadratic | None = None
    gap: Quadratic | None = None
    try:
        terms = tuple(
            _real(multiply(state, effect), "primal term")
            for state, effect in zip(case.weighted_states, certificate.primal_povm)
        )
        primal_value = terms[0]
        for item in terms[1:]:
            primal_value = primal_value + item
        dual_value = _real(gamma, "dual objective")
        gap = dual_value - primal_value
    except AlgebraicFieldError as error:
        if primal_feasible and dual_feasible:
            raise
        refutations.append(f"certificate objective is not real: {error}")

    left = tuple(multiply(slack, effect) for slack, effect in zip(slacks, certificate.primal_povm))
    right = tuple(multiply(effect, slack) for slack, effect in zip(slacks, certificate.primal_povm))
    complementary = all(is_zero_matrix(item) for item in (*left, *right))

    if primal_feasible and dual_feasible and gap is not None and gap.sign() < 0:
        raise AssertionError(
            "exact weak duality was violated by feasible primal and dual points; "
            "the checker is wrong, not the certificate"
        )

    closed = (
        primal_feasible and dual_feasible and gap is not None and gap.sign() == 0 and complementary
    )
    representable = bool(probe["representable_in_quadratic_extension"])
    independent = closed_form_optimum(case.weighted_states)
    if closed and independent is not None and primal_value != independent:
        raise AssertionError(
            "a zero-gap certificate disagreed with the independent closed-form optimum"
        )

    if not (primal_feasible and dual_feasible):
        status = COVERAGE_REFUTED
    elif closed:
        status = COVERAGE_CERTIFICATE_VERIFIED
    elif not representable:
        status = COVERAGE_OUTSIDE_FIELD
    else:
        status = COVERAGE_GAP_NOT_CLOSED

    return {
        "coverage": _coverage(status, certificate),
        "coverage_status": _checked_coverage_status(status),
        "certificate_provenance": certificate.provenance(),
        "certificate_supplied": True,
        "complementarity_exact": complementary,
        "dual_feasible": dual_feasible,
        "dual_value": None if dual_value is None else dual_value.canonical(),
        "independent_closed_form_crosscheck": crosscheck,
        "left_complementarity_residuals": [canonical_matrix(item) for item in left],
        "primal_dual_gap": None if gap is None else gap.canonical(),
        "primal_feasible": primal_feasible,
        "primal_value": None if primal_value is None else primal_value.canonical(),
        "refutation_reasons": sorted(refutations),
        "right_complementarity_residuals": [canonical_matrix(item) for item in right],
        "unresolved_reason": None,
        "weighted_state_traces": [item.canonical() for item in traces],
        "_shared": {
            "radicand": radicand,
            "noncommuting": noncommuting,
            "probe": probe,
            "primal_matches_crosscheck": (
                None if independent is None or primal_value is None else primal_value == independent
            ),
            "dual_matches_crosscheck": (
                None if independent is None or dual_value is None else dual_value == independent
            ),
        },
    }


def verify_case(case: NoncommutingCase) -> dict[str, Any]:
    """Check one supplied certificate exactly, or report the case unresolved."""

    traces = validate_ensemble(case.weighted_states)
    ensemble_radicand = _measure(all_values(case.weighted_states), "ensemble")
    noncommuting = any(
        not is_zero_matrix(commutator(case.weighted_states[i], case.weighted_states[j]))
        for i in range(len(case.weighted_states))
        for j in range(i + 1, len(case.weighted_states))
    )
    probe = _field_probe(case.weighted_states)
    crosscheck = closed_form_crosscheck(case.weighted_states)

    if case.certificate is None:
        body = _unresolved_result(
            traces=traces,
            radicand=ensemble_radicand,
            noncommuting=noncommuting,
            probe=probe,
            crosscheck=crosscheck,
        )
    else:
        body = _certificate_result(
            case,
            case.certificate,
            traces=traces,
            ensemble_radicand=ensemble_radicand,
            noncommuting=noncommuting,
            probe=probe,
            crosscheck=crosscheck,
        )
    shared = body.pop("_shared")
    representable = bool(probe["representable_in_quadratic_extension"])

    if noncommuting is not case.expected_noncommuting:
        raise CertificateInputError(
            "case noncommutativity expectation disagrees with the exact check"
        )
    if representable is not case.expected_optimum_representable:
        raise CertificateInputError(
            "case representability expectation disagrees with the exact spectral probe"
        )
    if body["coverage_status"] != case.expected_coverage_status:
        raise CertificateInputError(
            "case coverage expectation %r disagrees with the measured status %r"
            % (case.expected_coverage_status, body["coverage_status"])
        )
    if body["primal_dual_gap"] != case.expected_primal_dual_gap:
        raise CertificateInputError(
            "case gap expectation disagrees with the measured exact gap; a fixture may "
            "not be relabelled to make a check pass, in either direction"
        )

    verified = body["coverage_status"] == COVERAGE_CERTIFICATE_VERIFIED
    result: dict[str, Any] = {
        "schema_version": NONCOMMUTING_RESULT_VERSION,
        "applicability_status": "benchmark_local",
        "arithmetic": "exact_algebraic_quadratic_complex",
        "benchmark_id": BENCHMARK_ID,
        "case_id": case.case_id,
        "dimension": len(case.weighted_states[0]),
        "ensemble_effective_support": True,
        "field": field_descriptor(shared["radicand"]),
        "field_rejection_codes": list(FIELD_REJECTION_CODES),
        "graph_admitted": False,
        "mathematical_warrant": (
            "exact_noncommuting_certificate_verification" if verified else "none_unresolved"
        ),
        "noncommuting": shared["noncommuting"],
        "optimum_representable_in_quadratic_extension": representable,
        "outcomes": len(case.weighted_states),
        "primal_matches_independent_crosscheck": shared.get("primal_matches_crosscheck"),
        "dual_matches_independent_crosscheck": shared.get("dual_matches_crosscheck"),
        "proposal_status": "checked_result" if verified else "candidate_check_only",
        "search_tiers": {
            "tier_0": "enabled_deterministic",
            "tier_2": "disabled_no_measured_cost_adjusted_gain",
            "tier_3": "disabled_no_measured_cost_adjusted_gain",
            "tier_4": "disabled_no_measured_cost_adjusted_gain",
        },
        "spectral_field_probe": shared["probe"],
        "tolerance": None,
        "verification_mode": "verifies_supplied_certificate_never_discovers",
        **body,
    }
    result["result_hash"] = exact_hash(result)
    return result


def parse_fixture(fixture: Mapping[str, Any]) -> tuple[NoncommutingCase, ...]:
    """Validate the frozen fixture envelope and parse every case.

    Fails closed on unknown fields, an unsupported or mixed schema version, a
    repeated case identifier, and every case-level or field-level violation.
    """

    if not isinstance(fixture, dict):
        raise CertificateInputError("noncommuting fixture must be an object")
    _reject_inexact(fixture, "fixture")
    if set(fixture) != {"schema_version", "benchmark_id", "cases"}:
        raise CertificateInputError("noncommuting fixture has missing or unknown fields")
    if fixture["schema_version"] != NONCOMMUTING_FIXTURE_VERSION:
        raise CertificateInputError("unsupported noncommuting fixture schema version")
    if fixture["benchmark_id"] != BENCHMARK_ID:
        raise CertificateInputError("unsupported noncommuting benchmark identifier")
    cases = fixture["cases"]
    if not isinstance(cases, list) or not cases:
        raise CertificateInputError("noncommuting fixture must carry a nonempty case list")
    versions = sorted(
        {str(item.get("schema_version")) for item in cases if isinstance(item, dict)}
    )
    if versions != [NONCOMMUTING_CASE_VERSION]:
        raise CertificateInputError(
            "noncommuting fixture mixes or omits case schema versions: %s" % versions
        )
    parsed = tuple(NoncommutingCase.from_value(item) for item in cases)
    identifiers = [item.case_id for item in parsed]
    if len(set(identifiers)) != len(identifiers):
        raise CertificateInputError("noncommuting fixture repeats a case identifier")
    return parsed


def verify_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a whole frozen fixture document into one canonical report."""

    parsed = parse_fixture(fixture)
    results = [verify_case(item) for item in parsed]
    by_status = {
        status: [item["case_id"] for item in results if item["coverage_status"] == status]
        for status in COVERAGE_STATUSES
    }
    report: dict[str, Any] = {
        "schema_version": NONCOMMUTING_REPORT_VERSION,
        "arithmetic": "exact_algebraic_quadratic_complex",
        "benchmark_id": BENCHMARK_ID,
        "case_count": len(results),
        "case_schema_version": NONCOMMUTING_CASE_VERSION,
        "coverage_illusion_warning": (
            "Read the coverage status before the gap. Exactly zero gaps below are "
            "verified human-derived certificates on two-outcome ensembles with a "
            "closed form. They are not evidence that the noncommuting case is "
            "answered in general, and the retained cubic-boundary case is a genuine "
            "noncommuting ensemble this design provably cannot close."
        ),
        "coverage_statement": COVERAGE_STATEMENT,
        "coverage_status_counts": {status: len(by_status[status]) for status in COVERAGE_STATUSES},
        "coverage_status_vocabulary": list(COVERAGE_STATUSES),
        "covered_family": COVERED_FAMILY,
        "discovery_performed": False,
        "field_boundary_case_ids": by_status[COVERAGE_OUTSIDE_FIELD],
        "field_rejection_codes": list(FIELD_REJECTION_CODES),
        "general_noncommuting_convergence_answered": False,
        "gap_not_closed_case_ids": by_status[COVERAGE_GAP_NOT_CLOSED],
        "radicands_used": sorted({item["field"]["radicand"] for item in results}),
        "refuted_case_ids": by_status[COVERAGE_REFUTED],
        "results": results,
        "search_tiers_enabled": False,
        "source_schema_version": fixture["schema_version"],
        "tolerance": None,
        "unproducible_coverage_status": FORBIDDEN_COVERAGE_STATUS,
        "unresolved_case_ids": by_status[COVERAGE_UNRESOLVED],
        "verified_certificate_case_ids": by_status[COVERAGE_CERTIFICATE_VERIFIED],
    }
    if not report["field_boundary_case_ids"]:
        raise CertificateInputError(
            "the frozen fixture must retain a measured field-boundary case so the limit "
            "is visible in every run rather than inferred from an ADR"
        )
    report["content_hash"] = exact_hash(report)
    return report


# -- rendering -------------------------------------------------------------
#
# ADR-0035 requires the coverage field to be read before the gap field and the
# report to make that ordering obvious rather than available.  These phrases are
# forbidden in rendered output; the guard runs on every render, so a summary line
# claiming general noncommuting capability cannot be emitted.
FORBIDDEN_SUMMARY_PHRASES = (
    "discovered the optimum",
    "general noncommuting convergence answered",
    "general noncommuting convergence is answered",
    "handles noncommuting",
    "handles the noncommuting case",
    "noncommuting capability",
    "noncommuting is handled",
    "noncommuting sdp solver",
    "noncommuting solved",
    "optimum discovered",
    "optimum was discovered",
    "resolves qd-fs-01",
    "solves noncommuting",
)


def assert_no_capability_claim(text: str) -> str:
    """Fail closed if rendered output claims general noncommuting capability."""

    lowered = text.lower()
    found = sorted(phrase for phrase in FORBIDDEN_SUMMARY_PHRASES if phrase in lowered)
    if found:
        raise AssertionError(
            "rendered Phase 5 noncommuting output claims capability this slice does "
            "not have: %s" % ", ".join(found)
        )
    return text


def _canonical_text(value: Any) -> str:
    if value is None:
        return "not measured"
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and "radicand" in value:
        return "%s + (%s)*sqrt(%d)" % (value["rational"], value["surd"], value["radicand"])
    if isinstance(value, dict) and "re" in value:
        return "%s + i*(%s)" % (_canonical_text(value["re"]), _canonical_text(value["im"]))
    raise AssertionError(f"unrenderable exact value: {value!r}")


def render_noncommuting_report(report: Mapping[str, Any]) -> str:
    """Render the report with coverage before gap, and no capability claim."""

    lines = [
        "# Phase 5 Noncommuting Certificate Verification",
        "",
        "## Coverage (read this before any gap)",
        "",
        f"- Verification mode: verifies supplied certificates; performs no discovery.",
        f"- Coverage statement: {report['coverage_statement']}",
        f"- Covered family: `{report['covered_family']}`",
        "- General noncommuting JRF convergence: NOT answered by this slice.",
        f"- Status vocabulary: {', '.join(report['coverage_status_vocabulary'])}.",
        f"- Never produced: `{report['unproducible_coverage_status']}`.",
        f"- {report['coverage_illusion_warning']}",
        "",
        "## Coverage status counts",
        "",
    ]
    for status in report["coverage_status_vocabulary"]:
        lines.append(f"- `{status}`: {report['coverage_status_counts'][status]}")
    lines.extend(
        [
            "",
            "## Measured field boundary retained in every run",
            "",
        ]
    )
    for case_id in report["field_boundary_case_ids"]:
        lines.append(
            f"- `{case_id}` is a genuine noncommuting ensemble whose optimum has degree "
            "three over the rationals, so no certificate over any quadratic extension "
            "can close it."
        )
    lines.extend(["", "## Per-case exact measurements", ""])
    for item in report["results"]:
        lines.extend(
            [
                f"### `{item['case_id']}`",
                "",
                f"- Coverage status: `{item['coverage_status']}`",
                f"- Certificate supplied: {'yes' if item['certificate_supplied'] else 'no'}",
                f"- Certificate provenance: "
                + (
                    f"derived by `{item['certificate_provenance']['deriving_principal_id']}` "
                    f"via `{item['certificate_provenance']['derivation']}`, admitted through "
                    f"`{item['certificate_provenance']['admitted_through']}`"
                    if item["certificate_provenance"]
                    else "none recorded (no certificate supplied)"
                ),
                f"- Field: `{item['field']['notation']}`, radicand measured from case values",
                f"- Noncommuting: {'yes' if item['noncommuting'] else 'no'}",
                f"- Primal value: {_canonical_text(item['primal_value'])}",
                f"- Dual value: {_canonical_text(item['dual_value'])}",
                f"- Exact primal/dual gap: {_canonical_text(item['primal_dual_gap'])}",
                f"- Tolerance applied: none",
                "",
            ]
        )
        if item["unresolved_reason"]:
            lines.extend([f"- Unresolved: {item['unresolved_reason']}", ""])
        if item["refutation_reasons"]:
            lines.extend(
                [f"- Refutation: {reason}" for reason in item["refutation_reasons"]] + [""]
            )
    lines.extend(
        [
            "## Search tiers",
            "",
            "- tier_2, tier_3, tier_4: `disabled_no_measured_cost_adjusted_gain`.",
            "",
            f"- Report content hash: `{report['content_hash']}`",
            "",
        ]
    )
    return assert_no_capability_claim("\n".join(lines))


__all__ = [
    "BENCHMARK_ID",
    "CERTIFICATE_BOUNDARY",
    "COVERAGE_CERTIFICATE_VERIFIED",
    "COVERAGE_GAP_NOT_CLOSED",
    "COVERAGE_OUTSIDE_FIELD",
    "COVERAGE_REFUTED",
    "COVERAGE_STATEMENT",
    "COVERAGE_STATUSES",
    "COVERAGE_UNRESOLVED",
    "COVERED_FAMILY",
    "FORBIDDEN_COVERAGE_STATUS",
    "FORBIDDEN_SUMMARY_PHRASES",
    "HUMAN_DERIVATIONS",
    "MAX_OUTCOMES",
    "PROHIBITED_DERIVATIONS",
    "CertificateInputError",
    "CertificateProvenanceError",
    "DiscoveryProhibitedError",
    "NoncommutingCase",
    "SuppliedCertificate",
    "assert_no_capability_claim",
    "parse_fixture",
    "render_noncommuting_report",
    "validate_ensemble",
    "verify_case",
    "verify_fixture",
]
