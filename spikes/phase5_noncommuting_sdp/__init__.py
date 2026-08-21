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
from .comparison import (
    COMPARISON_SCHEMA_VERSION,
    REQUIRED_INDEPENDENT_ENGINES,
    operational_hash,
    run_comparison,
    semantic_hash,
    verify_report,
)
from .encoding import ExactProgram, encode_case, load_fixture
from .engines import (
    AbsentModuleResolver,
    ClarabelEngine,
    CvxpyScsEngine,
    LicenseNotPermittedError,
    authorize_module,
    default_engines,
)
from .reconstruction import NumericHypothesis, attempt_reconstruction, float_point_exact_audit

__all__ = [
    "AbsentModuleResolver",
    "AlgebraicComplex",
    "AlgebraicFieldError",
    "COMPARISON_SCHEMA_VERSION",
    "CertificateInputError",
    "ClarabelEngine",
    "CvxpyScsEngine",
    "ExactProgram",
    "FIXTURE_SCHEMA_VERSION",
    "LicenseNotPermittedError",
    "NumericHypothesis",
    "Quadratic",
    "REPORT_SCHEMA_VERSION",
    "REQUIRED_INDEPENDENT_ENGINES",
    "RESULT_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "algebraic",
    "attempt_reconstruction",
    "authorize_module",
    "canonical_bytes",
    "canonical_hash",
    "characteristic_polynomial",
    "common_radicand",
    "default_engines",
    "encode_case",
    "exact_two_state_optimum",
    "field_descriptor",
    "imaginary",
    "float_point_exact_audit",
    "load_document",
    "load_fixture",
    "operational_hash",
    "parse_algebraic",
    "parse_quadratic",
    "quadratic",
    "rational_sqrt",
    "reject_floats",
    "run_comparison",
    "semantic_hash",
    "spectral_field_report",
    "two_state_optimum",
    "validate_document",
    "validate_fixture",
    "verify_report",
]
