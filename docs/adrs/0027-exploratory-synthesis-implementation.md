# ADR-0027: Implement ADR-0025 exploratory synthesis as a `synthesis` package

- **Status:** accepted
- **Date:** 2026-08-20
- **Blueprint requirement:** Section 19 Phase 5 deferred expansion; ADR-0025
- **Decision owners:** repository owner

## Context

`docs/phase-4/EXPLORATORY_RESEARCH_SYNTHESIS_V1.md` is a complete normative
contract: Sections 1--13 define the architecture and Section 14 defines twelve
acceptance scenarios `ERS-AC-01` through `ERS-AC-12`, each naming its fixture
inputs, required trace, expected output, forbidden output, and failure
conditions. It required no new dependency and no network access, so ADR-0026
selected it as the first slice of resumed delivery.

Mapping the integration surface first surfaced three facts that shaped the
design, each verified against the code rather than assumed:

1. **Phase 4A has no effective-applicability resolver.** Applicability reviews
   are `AuditRecord` rows with an untyped payload. Phase 4A validates each review
   as it is written but nothing resolves which review is currently in force.
   A review's `subject_id` is the source, not the evidence card, and unlike
   rights decisions its `supersedes` edge is not forced to point at the latest
   prior review, so a chain can fork. Contract Section 2.1 requires importing the
   *effective* decision, so this slice must supply the rule.
2. **Nothing writes a material-result lifecycle record.** The Phase 5 projection
   reads `material_partial_result_lifecycle` and derives `current_validity` from
   it, but no Phase 5 code path ever appends one. `ERS-AC-09` requires exactly
   that invalidation path.
3. **Phase 5 permits self-authorization.** `surface_material_result` never
   compares `originating_principal_id` with `created_by_principal_id`, and its
   own deterministic demo path passes the same system principal for both.
   `ERS-AC-07` forbids self-authorization.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (extend sealed Phase 5 in place) | Phase 5 already holds branch, steering, and material-result machinery | No new package; one record table | Reopens a sealed slice, invalidates its ADR-0023 acceptance, and mixes exact-quantum scope with exploratory scope | Re-audit of ADR-0023 |
| Wrap (new `synthesis` package over Phase 6) | Phases 3B--6 each layer this way | Sealed boundaries stay intact; one SQLite file; prefixed tables | One more workspace layer to keep integrity-checked | Full offline suite green |
| Interoperate (separate database and process) | -- | Strong isolation | Loses the shared append log, semantic events, and cross-phase closure the contract requires reusing | -- |
| Build/defer | -- | -- | Contract stays unimplemented | -- |

## Decision

Wrap. Add `src/math_research/synthesis/`, layered over `Phase6Workspace` on the
existing single SQLite file with `synthesis_`-prefixed tables and a checksum-
pinned migration under `migrations/synthesis/`.

The package is deliberately **not** named `phase7`: the blueprint has no Phase 7,
and this is the separately gated Phase 5 exploratory expansion rather than a new
roadmap phase.

Scope implemented, by contract section:

- **2** the four independent state axes, with ordering suppressed on the shared
  enum base so no code can infer that one warrant state sits above another;
- **3** representation and version disagreement warnings, plus explicit fidelity
  narrowing as the only route from a disagreement to `source_checked`;
- **4** `StructuredResearchResult`, the ten relation types, and separate
  state-axis records for results and relations;
- **5/5.1** all fifteen run bounds with fail-closed validation, a named-counter
  ledger, and the enforceable exploration reserve including the
  `reserve_unavailable` waiver rule;
- **6** bounded multi-hop retrieval over the unmodified Phase 3A FTS5/BM25 index
  behind a `ResultIndex` port, with the full per-iteration trace;
- **7** the finite portfolio and the exact duplicate-attempt key, with abandoned
  attempts addressable and retries requiring an identified changed input;
- **8** the thirteen-dimension composition comparison and locally minimal bridge
  candidates evaluated over every enumerated proper subset;
- **9** the eight verification stages by five outcomes, as execution records
  distinct from axis values;
- **10** material-result surfacing delegated to sealed Phase 5, plus the missing
  lifecycle writer and the separation-of-duty precondition;
- **11** transitive influence closure, the fourteen propagation triggers, and
  append-only invalidation with deterministic view rebuild;
- **12** captured proposal envelopes with a replay mode that refuses to invoke a
  generator.

Two boundaries are held deliberately. First, no result extractor is added:
Section 13 forbids one, so traversal metadata for the acceptance corpus is
declarative project-authored manifest data and retrieval remains real BM25 over
really ingested sources. Second, semantic and operational hashes are separated
following the Phase 3B and 4A precedent rather than the Phase 5 and 6 convention
of hashing an injected instant, because `ERS-AC-10` forbids an operational
timestamp in semantic identity.

## Consequences

The acceptance suite adds 170 tests across eight files, grouped by scenario,
and every scenario's forbidden outcomes are asserted impossible rather than
absent. The complete offline check is green at 445 tests.

Negative consequences. The slice is large for one ADR, and under ADR-0026's
lightweight process the tests are the only executable record of its thresholds,
so a weak test is a direct loss of auditability. The effective-applicability
fork rule is a judgement this slice introduces rather than imports: Phase 4A
could later adopt a different rule, and the two would then disagree. The
separation-of-duty check applies only to paths routed through
`synthesis.material`; calling sealed Phase 5 directly still permits
self-authorization, which is a boundary, not a fix. The declarative traversal
manifest means `ERS-AC-01` proves the retrieval *loop* is genuinely multi-hop but
does not prove structure can be extracted from real source text, which remains
out of scope.

## Blueprint deviation

Two, both recorded in ADR-0026 and restated here. ADR-0025 Section 13 requires an
owner-approved plan and an independent integration re-audit before implementation
begins; the owner authorized proceeding with this ADR plus the acceptance suite as
the substitute, and the compensating control is that all twelve scenarios
including every forbidden outcome are implemented. Section 19 lists this work
behind a dedicated entry gate that was not run.

The package name departs from the `phaseN` convention, deliberately, because
inventing a Phase 7 would imply a roadmap entry that does not exist.

## Validation and revisit trigger

Valid while `make check` stays green, the slice makes zero network, model, and
external API calls, adds no production dependency, and leaves every Phase 3A,
4A, 5, and 6 record byte-identical.

Reconsider if Phase 4A adopts its own effective-applicability rule that differs
from `synthesis/applicability.py`; if ADR-0019 defines the lifecycle vocabulary
this slice anticipates, in which case the writer must be reconciled with it; or
if a forbidden outcome from Section 14 is demonstrated reachable.
