"""ADR-0042 human review decisions and warrant granting.

This is the only place in the system where an `EpistemicWarrant` can be created
from a real run. Nothing here derives trust from a model's own output: every
warrant this package projects traces to a named human reviewer, or to a Phase 3B
kernel attestation whose meaning link a named human approved.

The package is append-only. A decision is recorded once under a derived
idempotency key; replaying the same decision is a no-op and reusing a key for
different content is a refusal. Dossiers are immutable content-hashed values, so
applying decisions produces a SUCCESSOR dossier with a new content hash rather
than mutating anything.
"""

SCHEMA_VERSION = "adaivy.review-decision.v1"
EXPORT_VERSION = "adaivy.review-journal.v1"
REFUSAL_SCHEMA_VERSION = "adaivy.review-refusal.v1"
SUCCESSOR_SCHEMA_VERSION = "adaivy.review-successor.v1"

# Semantic identity excludes `recorded_at` and `sequence`; the operational hash
# carries them. Phase 3B established the split and the synthesis slice reuses it.
HASH_PROFILE = "review-semantic-v1"

MAX_DECISIONS = 4_096
MAX_REFUSALS = 4_096
MAX_TEXT_LENGTH = 4_096
MAX_FORMAL_FINDING_BYTES = 262_144

#: Human review of a model candidate can license these warrant kinds and no
#: others. `formal_proof` is absent by design: a human reading model prose is not
#: a kernel. `model_agreement` is absent because this slice measures no
#: agreement, and `source_report` is absent because it needs a checked
#: `SourceApplicabilityRecord`, which ADR-0039 defers.
HUMAN_REVIEW_WARRANT_KINDS = (
    "exact_counterexample",
    "experimental_observation",
    "rigorous_derivation",
)

#: A Phase 3B kernel attestation licenses exactly one warrant kind.
FORMAL_KERNEL_WARRANT_KINDS = ("formal_proof",)

#: Phase 3B outcomes that may support a warrant. Every other member of
#: `FormalCheckOutcome` is a refusal named by its own outcome value.
KERNEL_CHECKED_OUTCOMES = (
    "kernel_checked",
    "kernel_checked_approved_standard_axioms",
)
