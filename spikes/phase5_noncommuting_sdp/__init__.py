"""Design-only exact validator for a future noncommuting SDP adapter.

Arithmetic is exact over one quadratic extension of the rationals per case; see
`algebraic.py` for the represented field and `docs/adrs/0033-...` for what falls
outside it.  Nothing here integrates with Phase 5 or grants a warrant.
"""

from .algebraic import (
    AlgebraicComplex,
    AlgebraicFieldError,
    Quadratic,
    algebraic,
    canonical_bytes,
    canonical_hash,
    common_radicand,
    field_descriptor,
    imaginary,
    parse_algebraic,
    parse_quadratic,
    quadratic,
    rational_sqrt,
    reject_floats,
)
from .field_probe import (
    characteristic_polynomial,
    exact_two_state_optimum,
    spectral_field_report,
    two_state_optimum,
)
from .validator import (
    FIXTURE_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    SCHEMA_VERSION,
    CertificateInputError,
    load_document,
    validate_document,
    validate_fixture,
)

__all__ = [
    "AlgebraicComplex",
    "AlgebraicFieldError",
    "CertificateInputError",
    "FIXTURE_SCHEMA_VERSION",
    "Quadratic",
    "REPORT_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "algebraic",
    "canonical_bytes",
    "canonical_hash",
    "characteristic_polynomial",
    "common_radicand",
    "exact_two_state_optimum",
    "field_descriptor",
    "imaginary",
    "load_document",
    "parse_algebraic",
    "parse_quadratic",
    "quadratic",
    "rational_sqrt",
    "reject_floats",
    "spectral_field_report",
    "two_state_optimum",
    "validate_document",
    "validate_fixture",
]
