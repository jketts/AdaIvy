"""Bounded exact reconstruction of an optimum, and honest failure records.

`DEPENDENCY_LICENSE_COMPARISON.md` requires the comparison experiment to
"attempt rational/algebraic or interval reconstruction", and records the blocker
it has to face: the noncommuting fixtures have feasible rational primal and dual
points that leave an exact ``1/4`` gap, the true optimum is irrational, and
"accepting a tolerance-sized gap would violate the benchmark's exact semantics".

This module runs five attempts per case and records the outcome of every one,
including the ones that fail:

1. ``exact_spectral_reconstruction`` -- for a two-outcome case in dimension two,
   construct the optimum exactly. The two-state discrimination optimum is
   attained by the spectral projector onto the positive part of ``W_1 - W_2``.
   The characteristic polynomial of a 2x2 Hermitian matrix is quadratic, so the
   eigenvalues lie in ``Q(sqrt(disc))``, and the projector is
   ``(D - lambda_- I) / sqrt(disc)`` -- no eigenvector algebra, no numerics.
   Anything outside that bounded shape is recorded as unsupported, never
   guessed.
2. ``exact_certificate_verification`` -- the constructed point is *checked*, not
   trusted. Exact weak duality plus exact two-sided complementarity is what
   makes the result a certificate; the construction only proposes it. This is
   the only step that may report an exact optimum.
3. ``rational_reconstruction`` -- attempt to express the verified optimum as a
   rational. For the noncommuting fixtures this FAILS, and the failure is
   recorded with its reason: the value is ``a + b*sqrt(s)`` with ``b != 0`` and
   ``s`` squarefree, hence irrational, so no rational of any denominator equals
   it. The closest bounded-denominator rational is recorded together with the
   exact, nonzero gap it leaves.
4. ``interval_reconstruction`` -- a rigorous rational enclosure from
   :func:`math.isqrt`, so a float observation can be compared against the exact
   value without the exact value being replaced by a float.
5. ``numeric_hypothesis_consistency`` -- if an engine (or a recorded test input)
   supplied a number, check it against the rigorous enclosure. This step is
   explicitly marked as not evidence of correctness. It cannot change any
   disposition.

Separately, :func:`float_point_exact_audit` takes the floating-point point an
engine actually returned, converts it to exact rationals (every float *is* a
dyadic rational, so this conversion is exact and invents nothing), and checks it
exactly. That is the executable demonstration that a solver point accurate to
``1e-9`` is not an exact certificate.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Sequence

from . import algebraic as alg
from .algebraic import AlgComplex, AlgMatrix, AlgebraicFieldError, Surd, rational_text
from .encoding import ComplexMatrix, ExactProgram, parse_matrix
from .validator import CertificateInputError

RECONSTRUCTION_SCHEMA_VERSION = "adaivy.phase5-noncommuting-sdp-reconstruction.v1"

SUPPORTED_OUTCOMES = 2
"""The bounded shape the exact spectral construction covers."""

SUPPORTED_STATE_DIMENSION = 2

MAX_RATIONAL_DENOMINATOR = 10**6
"""Bound on the denominator of a rational reconstruction candidate."""


@dataclass(frozen=True, slots=True)
class NumericHypothesis:
    """A number that came from outside the exact domain. Never a warrant.

    ``provenance`` records where it came from. ``engine_observed`` means an
    authorised engine returned it in this run; ``recorded_test_input`` means a
    test supplied it and no engine ran; ``absent`` means there is no number.
    """

    provenance: str = "absent"
    engine_id: str | None = None
    value: float | None = None
    declared_tolerance: float | None = None

    def public(self) -> dict[str, Any]:
        return {
            "provenance": self.provenance,
            "engine_id": self.engine_id,
            "value": self.value,
            "declared_tolerance": self.declared_tolerance,
            "is_warrant": False,
            "is_evidence_of_correctness": False,
            # A float from outside the exact domain is an operational observation.
            "hash_class": "operational_only",
        }


ABSENT_HYPOTHESIS = NumericHypothesis()


@dataclass(frozen=True, slots=True)
class AlgebraicCertificate:
    """An exact candidate optimum in one real quadratic field."""

    case_id: str
    radicand: int
    weighted_states: tuple[AlgMatrix, ...]
    povm: tuple[AlgMatrix, ...]
    dual: AlgMatrix
    construction: str


def to_algebraic(matrix: ComplexMatrix) -> AlgMatrix:
    """Lift an exact rational-complex matrix into the algebraic domain."""

    return tuple(
        tuple(AlgComplex.rational(item.real, item.imag) for item in row) for row in matrix
    )


def _rational_entry(value: AlgComplex, label: str) -> Fraction:
    if not value.imag.is_zero():
        raise AlgebraicFieldError(f"{label} must be real")
    return value.real.as_fraction()


def spectral_reconstruction(
    case_id: str, states: Sequence[AlgMatrix]
) -> tuple[AlgebraicCertificate | None, dict[str, Any]]:
    """Construct the exact two-outcome optimum, or record why it cannot."""

    record: dict[str, Any] = {
        "attempt": "exact_spectral_reconstruction",
        "uses_floating_point": False,
        "uses_a_solver": False,
        "bounded_shape": {
            "outcomes": SUPPORTED_OUTCOMES,
            "state_dimension": SUPPORTED_STATE_DIMENSION,
        },
    }
    if len(states) != SUPPORTED_OUTCOMES:
        record.update(
            status="unsupported_shape",
            reason_code="outcome_count_outside_bounded_construction",
            detail=(
                f"the exact construction covers exactly {SUPPORTED_OUTCOMES} outcomes; "
                f"this case has {len(states)}. No optimum is claimed."
            ),
        )
        return (None, record)
    dimension = len(states[0])
    if dimension != SUPPORTED_STATE_DIMENSION:
        record.update(
            status="unsupported_shape",
            reason_code="state_dimension_outside_bounded_construction",
            detail=(
                f"the closed-form quadratic spectral construction covers dimension "
                f"{SUPPORTED_STATE_DIMENSION}; this case has {dimension}. No optimum is claimed."
            ),
        )
        return (None, record)

    first, second = states[0], states[1]
    difference = alg.subtract(first, second)
    if not alg.is_hermitian(difference):
        record.update(
            status="failed",
            reason_code="difference_not_hermitian",
            detail="W_1 - W_2 is not Hermitian, so it has no real spectral decomposition.",
        )
        return (None, record)
    try:
        trace = _rational_entry(alg.trace(difference), "trace(W_1 - W_2)")
        determinant = _rational_entry(alg.determinant(difference), "det(W_1 - W_2)")
    except AlgebraicFieldError as error:
        record.update(status="failed", reason_code="nonreal_invariant", detail=str(error))
        return (None, record)

    discriminant = trace * trace - 4 * determinant
    record["characteristic_polynomial"] = {
        "form": "lambda^2 - trace*lambda + determinant",
        "trace": rational_text(trace),
        "determinant": rational_text(determinant),
        "discriminant": rational_text(discriminant),
    }
    if discriminant < 0:
        record.update(
            status="failed",
            reason_code="negative_discriminant",
            detail="a Hermitian matrix cannot have a negative discriminant; input is malformed.",
        )
        return (None, record)
    try:
        root = Surd.sqrt_of(discriminant)
    except AlgebraicFieldError as error:
        record.update(
            status="failed",
            reason_code="field_extension_outside_bound",
            detail=(
                "the optimum needs a quadratic field outside the bounded radicand/"
                f"extraction limits: {error}"
            ),
        )
        return (None, record)

    identity = alg.identity(dimension)
    half = Surd.rational(Fraction(1, 2))
    lambda_plus = (Surd.rational(trace) + root) * half
    lambda_minus = (Surd.rational(trace) - root) * half
    record["eigenvalues"] = {
        "lambda_plus": lambda_plus.public(),
        "lambda_minus": lambda_minus.public(),
        "field_radicand": root.radicand,
        "repeated": root.is_zero(),
    }

    if root.is_zero():
        # A Hermitian matrix with a repeated eigenvalue is that scalar times I.
        positive = lambda_plus.sign() > 0
        effect_one = identity if positive else alg.zeros(dimension)
        positive_part = difference if positive else alg.zeros(dimension)
        construction = "repeated_eigenvalue_scalar_matrix"
    else:
        projector_plus = alg.scalar_multiply(
            alg.subtract(difference, alg.scalar_multiply(identity, lambda_minus)),
            root.inverse(),
        )
        projector_minus = alg.subtract(identity, projector_plus)
        pieces: list[AlgMatrix] = []
        effects: list[AlgMatrix] = []
        for value, projector in ((lambda_plus, projector_plus), (lambda_minus, projector_minus)):
            if value.sign() > 0:
                pieces.append(alg.scalar_multiply(projector, value))
                effects.append(projector)
        effect_one = alg.sum_matrices(effects) if effects else alg.zeros(dimension)
        positive_part = alg.sum_matrices(pieces) if pieces else alg.zeros(dimension)
        construction = "spectral_projector_of_positive_part"

    effect_two = alg.subtract(identity, effect_one)
    dual = alg.add(second, positive_part)
    record.update(
        status="constructed",
        construction=construction,
        field_radicand=root.radicand,
        note=(
            "a construction is a proposal; only exact_certificate_verification may "
            "call the result a certificate."
        ),
    )
    certificate = AlgebraicCertificate(
        case_id=case_id,
        radicand=root.radicand,
        weighted_states=(first, second),
        povm=(effect_one, effect_two),
        dual=dual,
        construction=construction,
    )
    return (certificate, record)


def verify_certificate(certificate: AlgebraicCertificate) -> tuple[Surd | None, dict[str, Any]]:
    """Exactly verify primal feasibility, dual feasibility and a closed gap."""

    record: dict[str, Any] = {
        "attempt": "exact_certificate_verification",
        "arithmetic": f"exact_Q(sqrt({certificate.radicand}))",
        "uses_floating_point": False,
        "tolerance_used": None,
        "case_id": certificate.case_id,
        "construction": certificate.construction,
    }
    states = certificate.weighted_states
    povm = certificate.povm
    dual = certificate.dual
    dimension = len(dual)

    state_psd = [alg.is_psd(item) for item in states]
    effect_psd = [alg.is_psd(item) for item in povm]
    completeness = alg.sum_matrices(povm) == alg.identity(dimension)
    dual_psd = alg.is_psd(dual)
    slacks = tuple(alg.subtract(dual, item) for item in states)
    slack_psd = [alg.is_psd(item) for item in slacks]

    primal = alg.ZERO
    for state, effect in zip(states, povm):
        primal = primal + alg.real_trace(alg.multiply(state, effect))
    dual_value = alg.real_trace(dual)
    gap = dual_value - primal
    left = tuple(alg.multiply(slack, effect) for slack, effect in zip(slacks, povm))
    right = tuple(alg.multiply(effect, slack) for slack, effect in zip(slacks, povm))
    complementary = all(alg.is_zero_matrix(item) for item in (*left, *right))

    primal_feasible = all(effect_psd) and completeness
    dual_feasible = dual_psd and all(slack_psd)
    gap_sign = gap.sign()
    if gap_sign < 0 and primal_feasible and dual_feasible:
        raise AssertionError("exact weak duality was violated by feasible candidates")
    exact = primal_feasible and dual_feasible and gap_sign == 0 and complementary

    record.update(
        weighted_states_psd=state_psd,
        povm_effects_psd=effect_psd,
        povm_completeness_exact=completeness,
        primal_feasible_exact=primal_feasible,
        dual_psd=dual_psd,
        dual_slacks_psd=slack_psd,
        dual_feasible_exact=dual_feasible,
        primal_value=primal.public(),
        dual_value=dual_value.public(),
        primal_dual_gap=gap.public(),
        gap_is_exactly_zero=gap_sign == 0,
        complementarity_exact=complementary,
        povm=[alg.public_matrix(item) for item in povm],
        dual_matrix=alg.public_matrix(dual),
        left_complementarity_residuals=[alg.public_matrix(item) for item in left],
        right_complementarity_residuals=[alg.public_matrix(item) for item in right],
        exact_optimum_certificate=exact,
        status="verified_exact_optimum" if exact else "refuted_not_an_exact_optimum",
        basis=(
            "exact weak duality with a zero gap and exact two-sided complementarity"
            if exact
            else "one or more exact conditions failed"
        ),
    )
    return (primal if exact else None, record)


def rational_reconstruction(
    optimum: Surd, hypothesis: NumericHypothesis
) -> dict[str, Any]:
    """Attempt a rational form for the optimum. Records failure explicitly."""

    record: dict[str, Any] = {
        "attempt": "rational_reconstruction",
        "max_denominator": MAX_RATIONAL_DENOMINATOR,
        "exact_value": optimum.public(),
    }
    if optimum.is_rational():
        value = optimum.as_fraction()
        record.update(
            status="succeeded",
            rational_value=rational_text(value),
            denominator=value.denominator,
            within_denominator_bound=value.denominator <= MAX_RATIONAL_DENOMINATOR,
            detail="the exact optimum is rational, so the rational domain suffices.",
        )
        return record

    low, high = optimum.enclosure()
    midpoint = (low + high) / 2
    approximation = midpoint.limit_denominator(MAX_RATIONAL_DENOMINATOR)
    residual = Surd.rational(approximation) - optimum
    record.update(
        status="failed",
        reason_code="optimum_is_irrational",
        detail=(
            f"the exact optimum is a + b*sqrt({optimum.radicand}) with b != 0 and "
            f"sqrt({optimum.radicand}) irrational, so no rational of any denominator "
            "equals it; the rational domain cannot close this gap."
        ),
        proof_of_irrationality={
            "surd_coefficient": rational_text(optimum.b),
            "radicand": optimum.radicand,
            "radicand_is_squarefree_and_not_one": optimum.radicand > 1,
        },
        closest_bounded_rational=rational_text(approximation),
        exact_residual_of_closest_rational=residual.public(),
        exact_residual_is_zero=residual.is_zero(),
        exact_residual_enclosure=alg.enclosure(residual),
        tolerance_sized_gap_accepted=False,
        hypothesis=hypothesis.public(),
    )
    return record


def interval_reconstruction(optimum: Surd) -> dict[str, Any]:
    return {
        "attempt": "interval_reconstruction",
        "status": "succeeded",
        "exact_value": optimum.public(),
        "enclosure": alg.enclosure(optimum),
        "detail": (
            "a rigorous rational enclosure from math.isqrt; the exact value is never "
            "replaced by a float, and the enclosure alone is not an optimality proof."
        ),
    }


def hypothesis_consistency(optimum: Surd, hypothesis: NumericHypothesis) -> dict[str, Any]:
    record: dict[str, Any] = {
        "attempt": "numeric_hypothesis_consistency",
        "hypothesis": hypothesis.public(),
        "is_evidence_of_correctness": False,
        "can_change_disposition": False,
        # Derived from an engine float, so it is excluded from semantic identity.
        "hash_class": "operational_only",
        "note": (
            "agreement between a numerical engine and an exact value is not evidence "
            "of correctness; it is recorded only as an observation about the engine."
        ),
    }
    if hypothesis.value is None:
        record.update(status="no_hypothesis", consistent=None)
        return record
    low, high = optimum.enclosure()
    tolerance = Fraction(0)
    if hypothesis.declared_tolerance is not None:
        tolerance = Fraction(hypothesis.declared_tolerance).limit_denominator(10**18)
    observed = Fraction(hypothesis.value)
    consistent = (low - tolerance) <= observed <= (high + tolerance)
    record.update(
        status="checked",
        consistent=consistent,
        observed_value_exact_form=rational_text(observed),
        enclosure=alg.enclosure(optimum),
        widened_by_declared_tolerance=rational_text(tolerance),
    )
    return record


def _project_from_embedding(
    matrix: tuple[tuple[Fraction, ...], ...], dimension: int
) -> tuple[AlgMatrix, Fraction]:
    """Read a Hermitian matrix out of a real-embedded block, exactly.

    Returns the projected matrix and the exact maximum absolute entry of the
    part of the input that is NOT in the image of ``J``. A nonzero residual
    means the engine's point was not exactly in the embedded subspace.
    """

    real = [[Fraction(0)] * dimension for _ in range(dimension)]
    imag = [[Fraction(0)] * dimension for _ in range(dimension)]
    for i in range(dimension):
        for j in range(dimension):
            real[i][j] = (matrix[i][j] + matrix[i + dimension][j + dimension]) / 2
            imag[i][j] = (matrix[i + dimension][j] - matrix[i][j + dimension]) / 2
    residual = Fraction(0)
    for i in range(dimension):
        for j in range(dimension):
            expected_upper_left = real[i][j]
            expected_upper_right = -imag[i][j]
            residual = max(
                residual,
                abs(matrix[i][j] - expected_upper_left),
                abs(matrix[i][j + dimension] - expected_upper_right),
            )
    lifted = tuple(
        tuple(AlgComplex.rational(real[i][j], imag[i][j]) for j in range(dimension))
        for i in range(dimension)
    )
    return (lifted, residual)


def _rationalise(matrix: Sequence[Sequence[float]]) -> tuple[tuple[Fraction, ...], ...]:
    """Exact conversion of a float matrix. Every float is a dyadic rational."""

    return tuple(tuple(Fraction(float(value)) for value in row) for row in matrix)


def float_point_exact_audit(
    program: ExactProgram,
    states: Sequence[AlgMatrix],
    primal_blocks: Sequence[Sequence[Sequence[float]]],
    dual_block: Sequence[Sequence[float]],
    *,
    source: str,
) -> dict[str, Any]:
    """Exactly audit the floating-point point an engine actually returned.

    Every float is converted to the exact dyadic rational it already is, so
    nothing is invented and nothing is rounded away. The point is then held to
    the same exact conditions as any other candidate.
    """

    record: dict[str, Any] = {
        "attempt": "float_point_exact_audit",
        "source": source,
        "conversion": "float_to_exact_dyadic_rational",
        "tolerance_used": None,
    }
    dimension = program.state_dimension
    if len(primal_blocks) != program.outcomes or not dual_block:
        record.update(
            status="not_attempted",
            reason_code="incomplete_engine_point",
            detail="the engine did not return a complete primal/dual point.",
        )
        return record

    effects: list[AlgMatrix] = []
    residuals: list[str] = []
    for block in primal_blocks:
        rational = _rationalise(block)
        if program.complex_field:
            lifted, residual = _project_from_embedding(rational, dimension)
        else:
            lifted = tuple(
                tuple(AlgComplex.rational(value, Fraction(0)) for value in row)
                for row in rational
            )
            residual = Fraction(0)
        effects.append(lifted)
        residuals.append(rational_text(residual))
    rational_dual = _rationalise(dual_block)
    if program.complex_field:
        dual, dual_residual = _project_from_embedding(rational_dual, dimension)
    else:
        dual = tuple(
            tuple(AlgComplex.rational(value, Fraction(0)) for value in row)
            for row in rational_dual
        )
        dual_residual = Fraction(0)

    identity = alg.identity(dimension)
    completeness_error = alg.subtract(alg.sum_matrices(effects), identity)
    hermitian = [alg.is_hermitian(item) for item in effects]
    psd = [alg.is_psd(item) for item in effects]
    dual_hermitian = alg.is_hermitian(dual)
    dual_psd = alg.is_psd(dual)
    slacks = tuple(alg.subtract(dual, item) for item in states)
    slack_psd = [alg.is_psd(item) for item in slacks]
    primal = alg.ZERO
    for state, effect in zip(states, effects):
        primal = primal + alg.trace(alg.multiply(state, effect)).real
    dual_trace = alg.trace(dual).real
    gap = dual_trace - primal
    exact_zero_gap = gap.is_zero()
    completeness_exact = alg.is_zero_matrix(completeness_error)
    left = tuple(alg.multiply(slack, effect) for slack, effect in zip(slacks, effects))
    right = tuple(alg.multiply(effect, slack) for slack, effect in zip(slacks, effects))
    complementary = all(alg.is_zero_matrix(item) for item in (*left, *right))
    embedding_exact = all(item == "0" for item in residuals) and dual_residual == 0
    accepted = (
        all(hermitian)
        and all(psd)
        and completeness_exact
        and dual_hermitian
        and dual_psd
        and all(slack_psd)
        and exact_zero_gap
        and complementary
        and embedding_exact
    )
    if accepted:
        reason = "every exact condition happened to hold for the rationalised point"
    elif not exact_zero_gap:
        reason = "tolerance_sized_gap_is_not_an_exact_gap"
    else:
        reason = "exact_gap_is_zero_but_an_exact_feasibility_condition_failed"

    record.update(
        status=(
            "accepted_exact_certificate_from_rationalised_point"
            if accepted
            else "rejected_not_an_exact_certificate"
        ),
        embedding_projection_residual=residuals,
        dual_embedding_projection_residual=rational_text(dual_residual),
        embedding_projection_exact=embedding_exact,
        povm_effects_hermitian_exact=hermitian,
        povm_effects_psd_exact=psd,
        povm_completeness_exact=completeness_exact,
        max_completeness_error=rational_text(_max_abs_entry(completeness_error)),
        dual_hermitian_exact=dual_hermitian,
        dual_psd_exact=dual_psd,
        dual_slacks_psd_exact=slack_psd,
        primal_value_exact_form=primal.public(),
        dual_value_exact_form=dual_trace.public(),
        primal_dual_gap_exact_form=gap.public(),
        gap_is_exactly_zero=exact_zero_gap,
        gap_enclosure=alg.enclosure(gap),
        complementarity_exact=complementary,
        exact_optimum_certificate=accepted,
        reason_code=reason,
        detail=(
            "the engine's floating-point point is exactly representable as rationals, "
            "so this audit invents nothing; it holds that point to the benchmark's "
            "exact conditions. A tolerance-sized gap is not a closed gap."
        ),
    )
    return record


def _max_abs_entry(matrix: AlgMatrix) -> Fraction:
    largest = Fraction(0)
    for row in matrix:
        for item in row:
            for part in (item.real, item.imag):
                if not part.is_rational():
                    raise AlgebraicFieldError("expected a rational entry")
                largest = max(largest, abs(part.as_fraction()))
    return largest


@dataclass(frozen=True, slots=True)
class ReconstructionResult:
    record: dict[str, Any]
    optimum: Surd | None
    certificate: AlgebraicCertificate | None

    @property
    def certified(self) -> bool:
        return self.optimum is not None


def attempt_reconstruction(
    case: dict[str, Any],
    program: ExactProgram,
    hypothesis: NumericHypothesis = ABSENT_HYPOTHESIS,
) -> ReconstructionResult:
    """Run every reconstruction attempt and record each outcome."""

    raw_states = case.get("weighted_states")
    if not isinstance(raw_states, list):
        raise CertificateInputError("weighted_states must be an array")
    states = tuple(
        to_algebraic(parse_matrix(item, label=f"weighted state {index}"))
        for index, item in enumerate(raw_states)
    )
    attempts: list[dict[str, Any]] = []
    certificate, construction_record = spectral_reconstruction(program.case_id, states)
    attempts.append(construction_record)

    optimum: Surd | None = None
    if certificate is None:
        attempts.append(
            {
                "attempt": "exact_certificate_verification",
                "status": "not_attempted",
                "reason_code": "no_construction_available",
                "exact_optimum_certificate": False,
            }
        )
        attempts.append(
            {
                "attempt": "rational_reconstruction",
                "status": "not_attempted",
                "reason_code": "no_verified_optimum_to_express",
            }
        )
        attempts.append(
            {
                "attempt": "interval_reconstruction",
                "status": "not_attempted",
                "reason_code": "no_verified_optimum_to_enclose",
            }
        )
        attempts.append(
            {
                "attempt": "numeric_hypothesis_consistency",
                "status": "not_attempted",
                "reason_code": "no_verified_optimum_to_compare_against",
                "hypothesis": hypothesis.public(),
                "is_evidence_of_correctness": False,
            }
        )
    else:
        optimum, verification = verify_certificate(certificate)
        attempts.append(verification)
        if optimum is None:
            attempts.append(
                {
                    "attempt": "rational_reconstruction",
                    "status": "not_attempted",
                    "reason_code": "construction_was_refuted_by_exact_verification",
                }
            )
            attempts.append(
                {
                    "attempt": "interval_reconstruction",
                    "status": "not_attempted",
                    "reason_code": "construction_was_refuted_by_exact_verification",
                }
            )
            attempts.append(
                {
                    "attempt": "numeric_hypothesis_consistency",
                    "status": "not_attempted",
                    "reason_code": "construction_was_refuted_by_exact_verification",
                    "hypothesis": hypothesis.public(),
                    "is_evidence_of_correctness": False,
                }
            )
        else:
            attempts.append(rational_reconstruction(optimum, hypothesis))
            attempts.append(interval_reconstruction(optimum))
            attempts.append(hypothesis_consistency(optimum, hypothesis))

    certified = optimum is not None
    record: dict[str, Any] = {
        "schema_version": RECONSTRUCTION_SCHEMA_VERSION,
        "case_id": program.case_id,
        "attempts": attempts,
        "attempt_order": [item["attempt"] for item in attempts],
        "failed_attempts": [
            item["attempt"]
            for item in attempts
            if item.get("status") in {"failed", "unsupported_shape", "not_attempted", "refuted_not_an_exact_optimum"}
        ],
        "exact_optimum_certified": certified,
        "exact_optimum": optimum.public() if optimum is not None else None,
        "exact_optimum_enclosure": alg.enclosure(optimum) if optimum is not None else None,
        "optimum_is_rational": optimum.is_rational() if optimum is not None else None,
        "field": f"Q(sqrt({certificate.radicand}))" if certificate is not None else None,
        "hypothesis": hypothesis.public(),
        "disposition": (
            "exact_algebraic_optimum_certified" if certified else "unresolved_no_exact_certificate"
        ),
        "warrant_created": False,
        "note": (
            "a certified exact optimum here is a spike-local exact check, not an "
            "EpistemicWarrant and not a Phase 5 result."
        ),
    }
    return ReconstructionResult(record=record, optimum=optimum, certificate=certificate)


__all__ = [
    "ABSENT_HYPOTHESIS",
    "MAX_RATIONAL_DENOMINATOR",
    "RECONSTRUCTION_SCHEMA_VERSION",
    "SUPPORTED_OUTCOMES",
    "SUPPORTED_STATE_DIMENSION",
    "AlgebraicCertificate",
    "NumericHypothesis",
    "ReconstructionResult",
    "attempt_reconstruction",
    "float_point_exact_audit",
    "hypothesis_consistency",
    "interval_reconstruction",
    "rational_reconstruction",
    "spectral_reconstruction",
    "to_algebraic",
    "verify_certificate",
]
