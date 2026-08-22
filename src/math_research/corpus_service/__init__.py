"""ADR-0072 Slice 3: the persistent corpus service.

One operator-selected AdaIvy data root, outside the Git working tree, holds
immutable acquired source bytes and parsed spans, append-only acquisition,
rights, lineage, tombstone and usage ledgers, and immutable content-addressed
corpus generation manifests.  The lifecycle is grow-only across runs: a second
run against the same data root sees the same corpus generation and does not
reacquire unchanged documents.  Ordinary campaign cleanup never deletes corpus
artifacts; only a recorded takedown/revoked-rights event removes bytes from
active use, and it leaves a non-reconstructive tombstone plus a dependency
record and invalidates the affected generations.

Rights are policy-derived under ADR-0072 Decision §7: a human authors one
content-hashed source-and-rights policy; every per-document ``embedding`` /
``model_context`` decision is then deterministically derived from the archive
manifest and the exact per-document licence metadata under that policy.  A
derived decision that does not record the policy content hash, the deriving
rule identifier, and the exact per-document licence inputs is refused, and a
decision authored by a model or carrying ``Authority.PROPOSAL`` still refuses.
Ambiguous or incompatible records are QUARANTINED — recorded, retained, and
excluded — never prompted on.  Every other ADR-0064 obligation (named
processor per disclosing use, no wildcards, expiry/revocation/takedown
semantics) stands and is exercised through the existing Phase 4A machinery.

Two boundaries repeated from the ADR-0067 slice because they still bind:

* **A corpus is not retrieval.**  Nothing here is retrieval-indexed; every
  generation manifest carries ``retrieval_indexed: false`` until Slice 4's own
  gate changes that.
* **A corpus document is an ``untrusted_inspiration_candidate``.**  It creates
  no applicability, no premise, no epistemic warrant, no graph admission, and
  no novelty or significance assessment.  Applicability stays human and stays
  the ceiling.
"""

DATA_ROOT_SCHEMA_VERSION = "adaivy.corpus-service-data-root.v1"
LEDGER_SCHEMA_VERSION = "adaivy.corpus-service-ledger-record.v1"
POLICY_SCHEMA_VERSION = "adaivy.corpus-service-source-rights-policy.v1"
ARCHIVE_MANIFEST_SCHEMA_VERSION = "adaivy.corpus-service-snapshot-archive-manifest.v1"
TRANCHE_CONFIG_SCHEMA_VERSION = "adaivy.corpus-service-tranche-config.v1"
DERIVED_DECISION_SCHEMA_VERSION = "adaivy.corpus-service-derived-rights-decision.v1"
PARSED_SPANS_SCHEMA_VERSION = "adaivy.corpus-service-parsed-spans.v1"
GENERATION_SCHEMA_VERSION = "adaivy.corpus-service-generation-manifest.v1"
RUN_REPORT_SCHEMA_VERSION = "adaivy.corpus-service-ingest-run-report.v1"
SNAPSHOT_ACTIVATION_SCHEMA_VERSION = "adaivy.corpus-service-snapshot-acquisition-activation.v1"

__all__ = [
    "ARCHIVE_MANIFEST_SCHEMA_VERSION",
    "DATA_ROOT_SCHEMA_VERSION",
    "DERIVED_DECISION_SCHEMA_VERSION",
    "GENERATION_SCHEMA_VERSION",
    "LEDGER_SCHEMA_VERSION",
    "PARSED_SPANS_SCHEMA_VERSION",
    "POLICY_SCHEMA_VERSION",
    "RUN_REPORT_SCHEMA_VERSION",
    "SNAPSHOT_ACTIVATION_SCHEMA_VERSION",
    "TRANCHE_CONFIG_SCHEMA_VERSION",
]
