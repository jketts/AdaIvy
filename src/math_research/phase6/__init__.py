"""Frozen confirmatory evaluation and replayable release slice."""

SCHEMA_VERSION = "adaivy.phase6-record.v1"
EXPORT_VERSION = "adaivy.phase6-release.v1"
MAX_RECORDS = 1024
MAX_INPUT_BYTES = 2_097_152
MAX_EXPORT_BYTES = 67_108_864

from .service import Phase6Service, Phase6ValidationError, render_report
from .workspace import Phase6Workspace

__all__ = ["Phase6Service", "Phase6ValidationError", "Phase6Workspace", "render_report"]
