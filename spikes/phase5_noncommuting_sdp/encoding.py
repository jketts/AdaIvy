"""Exact, solver-agnostic encoding of one quantum-discrimination SDP.

`DEPENDENCY_LICENSE_COMPARISON.md` requires the comparison experiment to
"retain raw solver status/residuals and exact problem encodings". This module
produces the exact encoding, and it is the *only* thing the engine adapters are
allowed to consume, so both engines receive byte-identical problem data and a
disagreement cannot be blamed on two different models of the problem.

The primal problem, for weighted states ``W_i = p_i rho_i``:

    maximise    sum_i <W_i, E_i>     subject to   sum_i E_i = I,  E_i >= 0

and its dual:

    minimise    tr(Y)                subject to   Y - W_i >= 0

Complex Hermitian data is carried into a real symmetric cone by the standard
embedding ``J(A + iB) = [[A, -B], [B, A]]``. That embedding is a ring
homomorphism with ``tr(J(H)) = 2 tr(H)``, which is where ``objective_scale``
comes from. The real relaxation is exact, not an approximation, because
``K = J(i*I)`` is orthogonal and for any real symmetric feasible ``X`` the
average ``(X + K X K^T)/2`` is feasible, has the same objective value, and lies
in the image of ``J``. That justification is recorded in the encoding itself so
a reader does not have to reconstruct it.

Everything stored is an exact rational. The float vectors an engine needs are
produced separately by :meth:`ExactProgram.float_blocks`, which also records,
per entry, whether the conversion was exact -- a dyadic rational such as
``1/4`` converts exactly, a value such as ``1/3`` does not, and pretending
otherwise would silently change the problem the engine solves.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Sequence

from .comparison_algebraic import rational_text
from .comparison_validator import (
    MAX_DIMENSION,
    MAX_OUTCOMES,
    CertificateInputError,
    QComplex,
    canonical_bytes,
    qcomplex,
)

ENCODING_SCHEMA_VERSION = "adaivy.phase5-noncommuting-sdp-encoding.v1"

RealMatrix = tuple[tuple[Fraction, ...], ...]
ComplexMatrix = tuple[tuple[QComplex, ...], ...]

EMBEDDING_JUSTIFICATION = (
    "K = J(i*I) is orthogonal, J is a ring homomorphism, and for real symmetric X "
    "the average (X + K X K^T)/2 is feasible, has the same objective value, and "
    "lies in the image of J; so the real symmetric relaxation is exact, not a bound."
)


def parse_matrix(value: object, *, label: str) -> ComplexMatrix:
    """Parse one exact rational-complex square matrix, failing closed."""

    if not isinstance(value, list) or not value:
        raise CertificateInputError(f"{label} must be a nonempty array")
    rows = tuple(
        tuple(qcomplex(item) for item in row) for row in value if isinstance(row, list)
    )
    if len(rows) != len(value) or any(len(row) != len(rows) for row in rows):
        raise CertificateInputError(f"{label} must be square")
    if len(rows) > MAX_DIMENSION:
        raise CertificateInputError(f"{label} exceeds the exact spike dimension bound")
    return rows


def is_real(matrix: ComplexMatrix) -> bool:
    return all(item.imag == 0 for row in matrix for item in row)


def embed_hermitian(matrix: ComplexMatrix) -> RealMatrix:
    """``J(A + iB) = [[A, -B], [B, A]]`` as an exact rational real matrix."""

    size = len(matrix)
    out: list[tuple[Fraction, ...]] = []
    for i in range(size):
        out.append(
            tuple(matrix[i][j].real for j in range(size))
            + tuple(-matrix[i][j].imag for j in range(size))
        )
    for i in range(size):
        out.append(
            tuple(matrix[i][j].imag for j in range(size))
            + tuple(matrix[i][j].real for j in range(size))
        )
    return tuple(out)


def real_part_matrix(matrix: ComplexMatrix) -> RealMatrix:
    return tuple(tuple(item.real for item in row) for row in matrix)


def upper_triangle_indices(size: int) -> tuple[tuple[int, int], ...]:
    """Column-major upper triangle, the order both engines' cones expect."""

    return tuple((i, j) for j in range(size) for i in range(j + 1))


def _float_exact(value: Fraction) -> bool:
    """True iff ``float(value)`` round-trips back to the same exact rational."""

    try:
        return Fraction(float(value)) == value
    except (OverflowError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class ExactProgram:
    """The exact primal/dual pair handed to every engine, unchanged."""

    case_id: str
    state_dimension: int
    outcomes: int
    complex_field: bool
    block_dimension: int
    objective_scale: Fraction
    objective_blocks: tuple[RealMatrix, ...]
    """``J(W_i)`` (or ``W_i`` when the data is real), exact rationals."""

    @property
    def svec_dimension(self) -> int:
        m = self.block_dimension
        return m * (m + 1) // 2

    def float_blocks(self) -> tuple[tuple[tuple[tuple[float, ...], ...], ...], dict[str, Any]]:
        """Float view of the objective blocks plus an exactness audit."""

        blocks: list[tuple[tuple[float, ...], ...]] = []
        total = 0
        inexact: list[dict[str, Any]] = []
        for index, block in enumerate(self.objective_blocks):
            rows: list[tuple[float, ...]] = []
            for i, row in enumerate(block):
                for j, item in enumerate(row):
                    total += 1
                    if not _float_exact(item):
                        inexact.append(
                            {
                                "block": index,
                                "row": i,
                                "column": j,
                                "exact_value": rational_text(item),
                            }
                        )
                rows.append(tuple(float(item) for item in row))
            blocks.append(tuple(rows))
        audit = {
            "entries": total,
            "inexact_entries": inexact,
            "all_entries_exactly_representable": not inexact,
            "note": (
                "A float conversion that is not exact changes the problem the engine "
                "solves; it is recorded, never silently accepted."
            ),
        }
        return (tuple(blocks), audit)

    def public(self) -> dict[str, Any]:
        _, audit = self.float_blocks()
        body: dict[str, Any] = {
            "schema_version": ENCODING_SCHEMA_VERSION,
            "case_id": self.case_id,
            "arithmetic": "exact_rational",
            "sense": "maximise_primal_minimise_dual",
            "state_dimension": self.state_dimension,
            "outcomes": self.outcomes,
            "field": "complex_hermitian" if self.complex_field else "real_symmetric",
            "real_embedding": "hermitian_to_real_2d" if self.complex_field else "identity",
            "real_embedding_justification": EMBEDDING_JUSTIFICATION,
            "block_dimension": self.block_dimension,
            "psd_blocks": [self.block_dimension] * self.outcomes,
            "objective_scale": rational_text(self.objective_scale),
            "objective_blocks": [
                [[rational_text(item) for item in row] for row in block]
                for block in self.objective_blocks
            ],
            "primal_constraint": "sum_of_psd_blocks_equals_identity",
            "equality_constraints": self.svec_dimension,
            "vectorisation": "upper_triangle_column_major_offdiagonal_scaled_by_sqrt_2",
            "dual_constraint": "dual_block_minus_objective_block_is_psd",
            "dual_objective": "scaled_trace_of_dual_block",
            "float_conversion_audit": audit,
        }
        body["content_hash"] = "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()
        return body


def encode_case(case: dict[str, Any]) -> ExactProgram:
    """Build the exact encoding for one fixture case. Fails closed."""

    if not isinstance(case, dict):
        raise CertificateInputError("case must be an object")
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise CertificateInputError("case_id must be a nonempty string")
    raw_states = case.get("weighted_states")
    if not isinstance(raw_states, list) or not 1 <= len(raw_states) <= MAX_OUTCOMES:
        raise CertificateInputError("weighted_states must be a bounded nonempty array")
    states = tuple(
        parse_matrix(item, label=f"weighted state {index}")
        for index, item in enumerate(raw_states)
    )
    dimension = len(states[0])
    if any(len(item) != dimension for item in states):
        raise CertificateInputError("weighted-state dimensions disagree")
    complex_field = not all(is_real(item) for item in states)
    if complex_field:
        blocks = tuple(embed_hermitian(item) for item in states)
        block_dimension = 2 * dimension
        scale = Fraction(1, 2)
    else:
        blocks = tuple(real_part_matrix(item) for item in states)
        block_dimension = dimension
        scale = Fraction(1)
    return ExactProgram(
        case_id=case_id,
        state_dimension=dimension,
        outcomes=len(states),
        complex_field=complex_field,
        block_dimension=block_dimension,
        objective_scale=scale,
        objective_blocks=blocks,
    )


def encoding_hash(program: ExactProgram) -> str:
    return program.public()["content_hash"]


def content_hash(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    """`object_pairs_hook` that fails closed on a duplicate JSON key."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CertificateInputError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_fixture(path: Any) -> tuple[dict[str, Any], str]:
    """Read the frozen fixture file and return ``(document, content_hash)``."""

    raw = path.read_bytes()
    try:
        document = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CertificateInputError(f"{path} is not valid UTF-8 JSON") from error
    if not isinstance(document, dict) or not isinstance(document.get("cases"), list):
        raise CertificateInputError(f"{path} must contain an object with a cases array")
    return (document, content_hash(raw))


__all__ = [
    "EMBEDDING_JUSTIFICATION",
    "ENCODING_SCHEMA_VERSION",
    "ComplexMatrix",
    "ExactProgram",
    "RealMatrix",
    "content_hash",
    "embed_hermitian",
    "encode_case",
    "encoding_hash",
    "is_real",
    "load_fixture",
    "parse_matrix",
    "real_part_matrix",
    "reject_duplicate_keys",
    "upper_triangle_indices",
]
