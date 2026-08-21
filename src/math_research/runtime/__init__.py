"""Bounded iterative research runtime -- ADR-0047's central research lead.

This package is the missing runtime, not a new phase. Everything under it
orchestrates *strictly above* slices that are already sealed, and it adds no
capability to any of them. Concretely, it imports the Phase 2 loop, gateway,
and durable workspace and modifies none of them. No file under ``phase2/`` or
``phase3b/`` changes to make this work.

What it adds is the one thing the architecture described and never had: a
*second outer turn*. ADR-0041 permits bounded refinement inside one Phase 2
run; this runtime instead composes distinct one-round Phase 2 runs and carries
a bounded session ledger between them. Nested Phase 2 refinement is refused,
so there is one visible source of iteration rather than two overlapping loops.

Five boundaries carry the slice. Each is enforced in code here and each has a
named falsifiability probe in ``tests/test_runtime_lead.py``; a boundary whose
probe stops flipping is a boundary that proves nothing.

- **The target is frozen for the life of a session.** Every iteration re-derives
  the target claim, formalization statement, and assumption manifest from the
  dossier and compares them against hashes taken before the first model call. A
  mismatch raises rather than records: a session that cannot vouch for the
  identity of its own target has no meaning worth persisting. This is the
  anti-premise-smuggling control, and it is why iteration cannot drift onto an
  easier theorem.

- **The growing context is proposer-only.** The iteration ledger -- what was
  already tried and what the verifier said about it -- enters the *proposer*
  context and never the verifier context. The verifier sees exactly the
  per-iteration context the sealed single-shot path builds, so the measured
  independence of Phase 2's verifier boundary carries over unchanged instead of
  being silently widened by iteration.

- **Nothing is promoted.** ``epistemic_warrant_created`` is ``False``
  unconditionally, ``obligations_discharged`` is always zero, and a session
  ends by *reporting* to a human rather than by accepting anything. The runtime
  holds no reference to ``TrustPolicy`` and writes no warrant, evidence
  disposition, applicability record, or graph admission. A verifier saying
  ``manual_review`` stops the run; it does not accept the proposal.

- **Bounds are external and unraisable.** Session bounds arrive as a
  content-hashed configuration artifact, are checked before each iteration is
  created, and are enforced twice: once by this runtime for the session and
  again by the Phase 2 per-run budget for each iteration. No component may
  raise a bound mid-run.

- **Replay never calls a model.** The report is rendered from the durable
  workspace alone. ``GatewayCalledDuringReplay`` exists so that a replay path
  that reaches a gateway fails loudly instead of quietly spending money.

Two things this package deliberately does NOT do. It does not decide whether
iterating helps -- no retention measurement, no comparison against the
single-shot baseline, no verified-progress-per-unit-cost figure. That is the
ADR-0029 retention question and it stays open; the stagnation rule here is a
*stop* rule and is not a progress metric. And it activates no search tier: one
lead, one centralized verifier, no specialists, no evolutionary selection, no
parallel workers. Branches are explored one at a time, in a deterministic
order, by the same lead.
"""

from __future__ import annotations

SCHEMA_VERSION = "adaivy.runtime-session.v2"
POLICY_VERSION = "runtime-central-lead-v2"
CANONICALIZATION_VERSION = "runtime-canonical-json-v1"
SESSION_CONFIG_SCHEMA_VERSION = "1.0.0"

#: Hard ceiling on any session bound, regardless of what a configuration asks
#: for. A configuration file is an operator input and is not trusted to be
#: sane; these are the values above which a run is refused outright.
MAX_ITERATIONS_CEILING = 64
MAX_MODEL_CALLS_CEILING = 256
MAX_COST_MICROUSD_CEILING = 25_000_000
MAX_WALL_MILLISECONDS_CEILING = 7_200_000

#: Bounds on the proposer-only iteration ledger. The ledger is what makes a
#: second turn worth taking, and it is also the one part of the context that
#: grows, so it is capped in both entries and bytes and reports its own
#: truncation rather than presenting a clipped history as a complete one.
MAX_LEDGER_ENTRIES = 12
MAX_LEDGER_BYTES = 32_768
MAX_LEDGER_FIELD_BYTES = 2_048

__all__ = [
    "CANONICALIZATION_VERSION",
    "MAX_COST_MICROUSD_CEILING",
    "MAX_ITERATIONS_CEILING",
    "MAX_LEDGER_BYTES",
    "MAX_LEDGER_ENTRIES",
    "MAX_LEDGER_FIELD_BYTES",
    "MAX_MODEL_CALLS_CEILING",
    "MAX_WALL_MILLISECONDS_CEILING",
    "POLICY_VERSION",
    "SCHEMA_VERSION",
    "SESSION_CONFIG_SCHEMA_VERSION",
]
