"""ADR-0036 publication projection.

Records are the artifact of record, ``paper.tex`` is a projection of them, and
``paper.pdf`` is a build product of the projection. Nothing flows back. Every
rendered content block carries at least one record reference, the evidence class
of a claim is computed rather than declared, demotion is the default, and the
document's status block cannot be suppressed by any manuscript field.
"""

from __future__ import annotations

SCHEMA_VERSION = "1.0.0"
POLICY_ID = "publication.projection"
POLICY_VERSION = "1.0.0"
CANONICALIZATION_VERSION = "1.0.0"

#: Frozen instant used for ``SOURCE_DATE_EPOCH``. An input, never a clock read:
#: the projection is byte-reproducible and a moving clock would break it.
SOURCE_DATE_EPOCH = 1_577_836_800  # 2020-01-01T00:00:00Z

from .bundle import BUNDLE_SCHEMA_VERSION, build_bundle, write_bundle  # noqa: E402
from .errors import PublicationValidationError  # noqa: E402
from .evidence import EVIDENCE_CLASSES, classify_claim  # noqa: E402
from .manuscript import Manuscript, load_manuscript, manuscript_hash  # noqa: E402
from .probes import run_probes  # noqa: E402
from .render import (  # noqa: E402
    TEMPLATE_HASH,
    RenderedDocument,
    render_manuscript,
    verify_ledger_closure,
)

__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "CANONICALIZATION_VERSION",
    "EVIDENCE_CLASSES",
    "Manuscript",
    "POLICY_ID",
    "POLICY_VERSION",
    "PublicationValidationError",
    "RenderedDocument",
    "SCHEMA_VERSION",
    "SOURCE_DATE_EPOCH",
    "TEMPLATE_HASH",
    "build_bundle",
    "classify_claim",
    "load_manuscript",
    "manuscript_hash",
    "render_manuscript",
    "run_probes",
    "verify_ledger_closure",
    "write_bundle",
]
