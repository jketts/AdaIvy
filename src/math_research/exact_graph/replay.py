"""Counter-candidate replay: evaluate a prior witness under every reading.

This is the module that makes a definitional fork a record instead of a remark.
A published candidate refutation of Graffiti 322 rests on two contested terms --
whether ``Even(v)`` counts ``v``, and whether "range" means the number of
distinct distance eigenvalues or ``lambda_max - lambda_min``.  Free prose can
pick one reading and never mention the others.  :func:`replay_candidate` cannot:
it evaluates the witness under **all four** reading tuples and records a verdict
for each, so an asymmetry between witnesses appears in the record rather than in
someone's commentary.

Three boundaries are enforced.

* **No reading is privileged.**  There is no default reading argument anywhere
  in this package.  A result that holds under one tuple and fails under another
  is reported as exactly that.
* **A failure is retained, never dropped.**  A witness that is disconnected, a
  vertex with an empty even-distance set, a spectrum too large for the dense
  route with no decomposition supplied -- each becomes a ``not_evaluated``
  verdict carrying its refusal code in ``detail``.  Nothing is silently omitted
  and no missing evaluation reads as a passing one.
* **A replay is not a warrant.**  ``creates_mathematical_warrant`` is ``False``
  unconditionally.  A ``refutes`` verdict states that two exactly computed
  values stand in a strict inequality under a named reading.  It does not
  establish novelty, significance, source applicability, or that the reading is
  the source's.

Every value is exact.  ``float_used`` is ``False`` structurally: no ``float`` is
constructed anywhere in :mod:`math_research.exact_graph`, and the field exists
so a consumer can refuse a payload that claims otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any

from ..phase2.serialization import canonical_hash
from .graph import ExactGraphError, Graph, is_connected, is_triangle_free
from .invariants import EVEN_READINGS, InvariantError, inverse_even
from .spectrum import (
    MAX_DENSE_ORDER,
    RANGE_READINGS,
    Decomposition,
    SpectrumError,
    decomposition_root_polynomial,
    distance_matrix,
    distinct_eigenvalue_count,
    minimal_polynomial,
    rayleigh_extent_bound,
    spectral_extent_vs,
    verify_decomposition,
)

REPLAY_SCHEMA_VERSION = "adaivy.counter-candidate-replay.v1"

# The engine name recorded in ``cert.graffiti-322-exact-separation``.  This
# package is its first in-repository implementation; the certificate was
# previously reproducible only from an external script and a result hash.
ENGINE_ID = "exact_graph_distance_and_invariant_space_v2"

# A reading tuple is one choice per contested term, in this order.
READING_TUPLES = (
    ("even_includes_v", "range_distinct_count"),   # the reading AdaIvy froze
    ("even_includes_v", "range_extent"),
    ("even_excludes_v", "range_distinct_count"),   # the reading R&C's C4 needs
    ("even_excludes_v", "range_extent"),
)

VERDICTS = ("refutes", "does_not_refute", "not_evaluated")


def reading_tuple_product() -> tuple[tuple[str, str], ...]:
    """The cartesian product of the two contested terms' readings.

    :data:`READING_TUPLES` is written out literally because its order is frozen
    and consumed downstream.  This function derives the same set from
    ``EVEN_READINGS`` and ``RANGE_READINGS`` so that adding a reading to either
    vocabulary without extending the tuple list fails a test instead of
    silently shrinking the coverage a replay claims.
    """

    return tuple(
        (even, extent) for even in EVEN_READINGS for extent in RANGE_READINGS
    )

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")


class ReplayError(ExactGraphError):
    """A replay cannot be constructed as asked."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ReadingResult:
    """One reading tuple's exact evaluation.  ``range_value`` is never a float.

    For ``range_distinct_count`` it is the decimal count as a string.  For
    ``range_extent`` it is the *comparison outcome* against the Inverse Even
    value, written ``"<outcome>_than:<p/q>"`` (or ``"equal_to:<p/q>"``), because
    the extent itself is in general an algebraic number of degree above one and
    writing it as a decimal would require inventing a float.
    """

    reading: tuple[str, str]
    inverse_even: str
    range_value: str
    verdict: str
    detail: str

    def payload(self) -> dict[str, Any]:
        return {
            "reading": list(self.reading),
            "inverse_even": self.inverse_even,
            "range_value": self.range_value,
            "verdict": self.verdict,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplayResult:
    """A content-hashed replay of one witness under every reading tuple."""

    replay_id: str
    witness_graph_id: str
    witness_spec_hash: str
    engine: str = ENGINE_ID
    arithmetic: str = "fractions-exact"
    float_used: bool = False
    order: int
    triangle_free: bool
    connected: bool
    readings: tuple[ReadingResult, ...]
    result_hash: str = ""

    def payload(self, *, include_hash: bool = True) -> dict[str, Any]:
        return {
            "schema_version": REPLAY_SCHEMA_VERSION,
            "replay_id": self.replay_id,
            "witness_graph_id": self.witness_graph_id,
            "witness_spec_hash": self.witness_spec_hash,
            "engine": self.engine,
            "arithmetic": self.arithmetic,
            "float_used": self.float_used,
            "order": self.order,
            "triangle_free": self.triangle_free,
            "connected": self.connected,
            "readings": [item.payload() for item in self.readings],
            "creates_mathematical_warrant": False,
            "result_hash": self.result_hash if include_hash else None,
        }

    def finalized(self) -> "ReplayResult":
        return replace(self, result_hash=canonical_hash(self.payload(include_hash=False)))

    def verdict_for(self, reading: tuple[str, str]) -> str:
        for item in self.readings:
            if item.reading == tuple(reading):
                return item.verdict
        raise ReplayError("replay_reading_absent", str(reading))

    def scope_inputs(self) -> tuple[str, ...]:
        """Verdicts in ``READING_TUPLES`` order, for a downstream verdict matrix."""

        return tuple(self.verdict_for(reading) for reading in READING_TUPLES)


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}" if value.denominator != 1 else str(value.numerator)


def _distinct_count(
    g: Graph, decomposition: Decomposition | None
) -> tuple[int | None, str]:
    if decomposition is not None:
        return verify_decomposition(g, decomposition), "verified_decomposition"
    if g.order > MAX_DENSE_ORDER:
        return None, "spectrum_too_large_without_decomposition"
    return distinct_eigenvalue_count(g), "confirmed_minimal_polynomial"


def _extent_polynomial(
    g: Graph, decomposition: Decomposition | None
) -> tuple[tuple[int, ...] | None, str]:
    if decomposition is not None:
        verify_decomposition(g, decomposition)
        return decomposition_root_polynomial(decomposition), "verified_decomposition"
    if g.order > MAX_DENSE_ORDER:
        return None, "spectrum_too_large_without_decomposition"
    return minimal_polynomial(distance_matrix(g)), "confirmed_minimal_polynomial"


def replay_candidate(
    g: Graph, *, replay_id: str, decomposition: Decomposition | None = None
) -> ReplayResult:
    """Evaluate ``g`` as a Graffiti 322 candidate under every reading tuple.

    ``refutes`` means ``InvEven(g) > range(g)`` strictly, under that tuple.
    Equality is ``does_not_refute``: the conjecture asserts an upper bound, and a
    witness that merely meets it refutes nothing.

    For ``range_extent`` the exact rational bound
    ``lambda_max - lambda_min > 2W/n`` settles the comparison outright whenever
    ``2W/n`` already reaches the Inverse Even value, with no eigenvalue work at
    all; :func:`spectral_extent_vs` is the general fallback.

    ``decomposition`` is an operator-supplied invariant-subspace decomposition.
    It is verified against ``g``'s own distance matrix before any verdict is
    formed, and a mismatch propagates as a refusal rather than becoming a
    ``not_evaluated`` verdict -- a wrong decomposition is a defect in the input,
    not an unevaluated reading.
    """

    if not isinstance(replay_id, str) or not _ID.fullmatch(replay_id):
        raise ReplayError("replay_id_invalid", str(replay_id))
    if not isinstance(g, Graph):
        raise ReplayError("replay_witness_invalid", type(g).__name__)

    triangle_free = is_triangle_free(g)
    connected = is_connected(g)

    results: list[ReadingResult] = []
    if not connected:
        for reading in READING_TUPLES:
            results.append(ReadingResult(
                reading=reading, inverse_even="not_evaluated",
                range_value="not_evaluated", verdict="not_evaluated",
                detail="graph_not_connected: graph distance is undefined, so no "
                       "reading of Graffiti 322 can be evaluated on this witness",
            ))
        return ReplayResult(
            replay_id=replay_id, witness_graph_id=g.graph_id,
            witness_spec_hash=g.spec_hash(), order=g.order,
            triangle_free=triangle_free, connected=connected,
            readings=tuple(results),
        ).finalized()

    inverse: dict[str, Fraction | None] = {}
    inverse_detail: dict[str, str] = {}
    for reading in EVEN_READINGS:
        try:
            inverse[reading] = inverse_even(g, reading)
            inverse_detail[reading] = "exact_rational"
        except InvariantError as error:
            inverse[reading] = None
            inverse_detail[reading] = f"{error.code}: {error.detail}"

    count: int | None
    count_detail: str
    try:
        count, count_detail = _distinct_count(g, decomposition)
    except SpectrumError as error:
        if error.code == "spectrum_too_large_without_decomposition":
            count, count_detail = None, f"{error.code}: {error.detail}"
        else:
            raise

    extent_bound = rayleigh_extent_bound(g)
    extent_poly: tuple[int, ...] | None = None
    extent_detail = ""

    for even_reading, range_reading in READING_TUPLES:
        value = inverse[even_reading]
        if value is None:
            results.append(ReadingResult(
                reading=(even_reading, range_reading),
                inverse_even="not_evaluated", range_value="not_evaluated",
                verdict="not_evaluated", detail=inverse_detail[even_reading],
            ))
            continue
        value_text = _fraction_text(value)
        if range_reading == "range_distinct_count":
            if count is None:
                results.append(ReadingResult(
                    reading=(even_reading, range_reading), inverse_even=value_text,
                    range_value="not_evaluated", verdict="not_evaluated",
                    detail=count_detail,
                ))
                continue
            verdict = "refutes" if value > count else "does_not_refute"
            results.append(ReadingResult(
                reading=(even_reading, range_reading), inverse_even=value_text,
                range_value=str(count), verdict=verdict,
                detail=f"|spec(D)|={count} via {count_detail}",
            ))
            continue
        # range_extent
        if extent_bound >= value and g.order >= 2:
            results.append(ReadingResult(
                reading=(even_reading, range_reading), inverse_even=value_text,
                range_value=f"greater_than:{value_text}", verdict="does_not_refute",
                detail=f"rayleigh_extent_bound=2W/n={_fraction_text(extent_bound)} "
                       f">= InvEven, and lambda_max-lambda_min > 2W/n exactly",
            ))
            continue
        if extent_poly is None and not extent_detail:
            try:
                extent_poly, extent_detail = _extent_polynomial(g, decomposition)
                if extent_poly is None:
                    extent_detail = f"spectrum_too_large_without_decomposition: {extent_detail}"
            except SpectrumError as error:
                if error.code == "spectrum_too_large_without_decomposition":
                    extent_poly, extent_detail = None, f"{error.code}: {error.detail}"
                else:
                    raise
        if extent_poly is None:
            results.append(ReadingResult(
                reading=(even_reading, range_reading), inverse_even=value_text,
                range_value="not_evaluated", verdict="not_evaluated",
                detail=extent_detail,
            ))
            continue
        try:
            outcome = spectral_extent_vs(extent_poly, value)
        except SpectrumError as error:
            results.append(ReadingResult(
                reading=(even_reading, range_reading), inverse_even=value_text,
                range_value="not_evaluated", verdict="not_evaluated",
                detail=f"{error.code}: {error.detail}",
            ))
            continue
        range_value = (
            f"equal_to:{value_text}" if outcome == "equal" else f"{outcome}_than:{value_text}"
        )
        verdict = "refutes" if outcome == "less" else "does_not_refute"
        results.append(ReadingResult(
            reading=(even_reading, range_reading), inverse_even=value_text,
            range_value=range_value, verdict=verdict,
            detail=f"lambda_max-lambda_min is {outcome} than InvEven, by exact "
                   f"Sturm comparison via {extent_detail}",
        ))

    return ReplayResult(
        replay_id=replay_id, witness_graph_id=g.graph_id,
        witness_spec_hash=g.spec_hash(), order=g.order,
        triangle_free=triangle_free, connected=connected,
        readings=tuple(results),
    ).finalized()
