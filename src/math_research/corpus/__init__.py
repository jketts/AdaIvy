"""ADR-0067 corpus ingestion: arXiv descriptive metadata and abstracts only.

The licence diligence recorded in ADR-0067 fixes the scope of this package and
nothing in it may widen that scope:

* arXiv descriptive metadata is CC0 1.0 and may be retrieved, stored,
  transformed and shared.  Titles, abstracts, authors, categories, DOIs and
  dates are in scope.
* arXiv e-prints -- PDFs, source packages, any other full-text form -- may not
  be stored or served without the copyright holder's permission, and copyright
  sits with the individual authors.  **Full text is out of scope and a code
  path that could fetch it must not exist.**  :mod:`sourcesweep` checks that
  as a property of the source text rather than trusting this docstring.
* The terms fix a rate limit of one request every three seconds over a single
  connection.  It is pinned in :mod:`constants` and in the activation record,
  never taken from a caller.

Two boundaries are stated here because every report from this package repeats
them:

* **A corpus is not retrieval.**  This package builds a content-hashed corpus of
  untrusted candidates.  It does not point Phase 4C at it; Phase 4C still reads
  its own frozen 19-document fixture.  A large corpus is therefore never
  evidence of improved retrieval.
* **A corpus record is an ``untrusted_inspiration_candidate``.**  It creates no
  applicability, no premise, no epistemic warrant, no graph admission, and no
  novelty or significance assessment.  Applicability is human and stays the
  ceiling, so every report counts records carrying an applicability record
  separately from records.
"""

SCHEMA_VERSION = "adaivy.corpus-record.v1"
ACTIVATION_SCHEMA_VERSION = "adaivy.corpus-arxiv-metadata-activation.v1"
PLAN_SCHEMA_VERSION = "adaivy.corpus-arxiv-tranche-plan.v1"
STORE_MANIFEST_SCHEMA_VERSION = "adaivy.corpus-response-store-manifest.v1"
INGESTION_SCHEMA_VERSION = "adaivy.corpus-ingestion-result.v1"
REPORT_SCHEMA_VERSION = "adaivy.corpus-ingestion-report.v1"
PROJECTION_SCHEMA_VERSION = "adaivy.corpus-record-projection.v1"
PROBE_REPORT_SCHEMA_VERSION = "adaivy.corpus-probe-report.v1"

__all__ = [
    "ACTIVATION_SCHEMA_VERSION",
    "INGESTION_SCHEMA_VERSION",
    "PLAN_SCHEMA_VERSION",
    "PROBE_REPORT_SCHEMA_VERSION",
    "PROJECTION_SCHEMA_VERSION",
    "REPORT_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "STORE_MANIFEST_SCHEMA_VERSION",
]
