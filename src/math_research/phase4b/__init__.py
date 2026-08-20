"""Bounded Phase 4B ports. Submodules do not activate external surfaces."""

# Shared raw-content bound from P4B-AT-028. Parser and deletable-content
# boundaries intentionally enforce the same exact byte ceiling.
MAX_SOURCE_BYTES = 2_097_152
from .records import (  # noqa: E402 -- constants follow the package-level byte bound.
    EXPORT_VERSION as EXPORT_SCHEMA_VERSION,
    MAX_EXPORT_BYTES,
    MAX_RECORDS,
    SCHEMA_VERSION,
)

__all__ = [
    "EXPORT_SCHEMA_VERSION",
    "MAX_EXPORT_BYTES",
    "MAX_RECORDS",
    "MAX_SOURCE_BYTES",
    "SCHEMA_VERSION",
]
