"""Frozen confirmatory evaluation and replayable release slice."""

SCHEMA_VERSION = "adaivy.phase6-record.v1"
EXPORT_VERSION = "adaivy.phase6-release.v1"
MAX_RECORDS = 1024
MAX_INPUT_BYTES = 2_097_152
MAX_EXPORT_BYTES = 67_108_864

from .errors import GeneralitySuiteError, Phase6ValidationError
from .generality import load_suite, run_suite, suite_hash, validate_suite
from .heldout import HeldOutView
from .service import Phase6Service, render_report
from .workspace import Phase6Workspace

__all__ = [
    "GeneralitySuiteError", "HeldOutView", "Phase6Service", "Phase6ValidationError",
    "Phase6Workspace", "load_suite", "render_report", "run_suite", "suite_hash",
    "validate_suite",
]
