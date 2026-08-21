"""Adaptive-search and exact quantum-discrimination vertical slice."""

SCHEMA_VERSION = "adaivy.phase5-record.v1"
EXPORT_VERSION = "adaivy.phase5-workspace.v1"
POLICY_ID = "policy.phase5-exact-v1"
POLICY_VERSION = "phase5-exact-v1"
CANONICALIZATION_VERSION = "phase5-canonical-json-v1"
MAX_RECORDS = 4096
MAX_INPUT_BYTES = 2_097_152
MAX_EXPORT_BYTES = 67_108_864

# ADR-0035 noncommuting expansion. These record shapes are NEW rather than
# altered: the sealed diagonal record types keep their schema versions, and the
# `adaivy.phase5-record.v1` envelope is unchanged, so existing sealed Phase 5
# records stay valid.
NONCOMMUTING_CASE_VERSION = "adaivy.phase5-noncommuting-case.v1"
NONCOMMUTING_FIXTURE_VERSION = "adaivy.phase5-noncommuting-fixture.v1"
NONCOMMUTING_RESULT_VERSION = "adaivy.phase5-noncommuting-result.v1"
NONCOMMUTING_REPORT_VERSION = "adaivy.phase5-noncommuting-report.v1"
NONCOMMUTING_RUN_VERSION = "adaivy.phase5-noncommuting-run-result.v1"
NONCOMMUTING_ADMISSION_VERSION = "adaivy.phase5-noncommuting-certificate-admission.v1"
NONCOMMUTING_FINDING_VERSION = "adaivy.phase5-noncommuting-finding.v1"

from .algebraic import AlgebraicFieldError
from .noncommuting import (
    NoncommutingCase, SuppliedCertificate, render_noncommuting_report, verify_case,
    verify_fixture,
)
from .quantum import DiagonalCase, QuantumInputError, run_case
from .service import Phase5Service
from .workspace import Phase5ValidationError, Phase5Workspace

__all__ = [
    "AlgebraicFieldError", "DiagonalCase", "NoncommutingCase", "Phase5Service",
    "Phase5ValidationError", "Phase5Workspace", "QuantumInputError",
    "SuppliedCertificate", "render_noncommuting_report", "run_case", "verify_case",
    "verify_fixture",
]
