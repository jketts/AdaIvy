"""Exact validator plus the bounded noncommuting-SDP engine-comparison spike.

`validator.py` is the original design-only exact rational-complex checker. The
comparison experiment (ADR-0045) adds the exact algebraic domain, the exact
problem encoding, two licence-gated engine adapters, the reconstruction
attempts, and the canonical comparison report.

Nothing here integrates with Phase 5, changes its sealed records, enables search
tiers 2--4, imports a dependency on the offline path, or grants a mathematical
warrant to a numerical result.
"""

from .comparison import (
    COMPARISON_SCHEMA_VERSION,
    REQUIRED_INDEPENDENT_ENGINES,
    run_comparison,
    semantic_hash,
    operational_hash,
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
from .reconstruction import (
    NumericHypothesis,
    attempt_reconstruction,
    float_point_exact_audit,
)
from .validator import CertificateInputError, canonical_bytes, validate_fixture

__all__ = [
    "COMPARISON_SCHEMA_VERSION",
    "REQUIRED_INDEPENDENT_ENGINES",
    "AbsentModuleResolver",
    "CertificateInputError",
    "ClarabelEngine",
    "CvxpyScsEngine",
    "ExactProgram",
    "LicenseNotPermittedError",
    "NumericHypothesis",
    "attempt_reconstruction",
    "authorize_module",
    "canonical_bytes",
    "default_engines",
    "encode_case",
    "float_point_exact_audit",
    "load_fixture",
    "operational_hash",
    "run_comparison",
    "semantic_hash",
    "validate_fixture",
    "verify_report",
]
