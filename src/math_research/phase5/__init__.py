"""Adaptive-search and exact quantum-discrimination vertical slice."""

SCHEMA_VERSION = "adaivy.phase5-record.v1"
EXPORT_VERSION = "adaivy.phase5-workspace.v1"
POLICY_ID = "policy.phase5-exact-v1"
POLICY_VERSION = "phase5-exact-v1"
CANONICALIZATION_VERSION = "phase5-canonical-json-v1"
MAX_RECORDS = 4096
MAX_INPUT_BYTES = 2_097_152
MAX_EXPORT_BYTES = 67_108_864

from .quantum import DiagonalCase, QuantumInputError, run_case
from .service import Phase5Service
from .workspace import Phase5ValidationError, Phase5Workspace

__all__ = [
    "DiagonalCase", "Phase5Service", "Phase5ValidationError", "Phase5Workspace",
    "QuantumInputError", "run_case",
]
