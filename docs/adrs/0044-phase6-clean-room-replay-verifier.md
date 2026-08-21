# ADR-0044: Phase 6 clean-room replay verifier

> **Number.** Filed as **0044**. This record was drafted as 0033 while that
> number looked free; 0032--0043 were allocated by concurrent sessions before it
> landed, so it was renumbered on merge with no change to its content.

- **Status:** proposed
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 19 deferred expansion, "clean-room replay
  and release packaging" (`TECHNICAL_BLUEPRINT.md`:2236); deferred exit criteria
  "complete traces expose negative and superseded attempts" (:2242) and
  "independent replay reproduces accepted tool/formal artifacts" (:2245);
  ADR-0024:25-27; ADR-0026 WP5
- **Decision owners:** repository owner (accept/reject), Phase 6 slice implementer

## Context

ADR-0024:25-27 states that the Phase 6 release package "binds the Phase 5
export, protocol, confirmatory result, controls, assessments, contributions, and
limitations for restart and clean-room replay". **Restart is real** and tested
(`tests/test_phase6_confirmatory.py`:55-65 re-opens the workspace and asserts
byte-identical re-execution). **Clean-room replay was not implemented.**

`phase6 replay` (`src/math_research/phase6_cli.py`:66-69) is a single call to
`Phase6Workspace.save_verified_export` (`src/math_research/phase6/workspace.py`
:156-167), which checks only three things: the envelope field set, the envelope
`schema_version`, and `value["content_hash"] == content_hash(value)`. Because
`content_hash` (`src/math_research/phase5/serialization.py`:27-30) hashes the
envelope minus its own hash key, the sole check is envelope self-consistency.
The accepted blob is stored in `phase6_verified_exports`, a table
`verify_integrity` (`workspace.py`:124-138) never reads.

**The vulnerability is the absence of re-derivation, not a weak comparison.**
Nothing in the ingest path recomputes a record's `content_hash` from its
payload, or a `record_id` from `stable_id`, or the release hash, or the held-out
case. A verifier that merely compared declared values in place would already
reject the forgery described below, which is precisely the evidence that no such
comparison runs today.

Verified by execution before this slice was written:

- A valid export was produced through the `make check` phase6 demo path,
  `graph_admitted` was flipped from `false` to `true` inside the
  `confirmatory_result` record payload, and only the top-level `content_hash`
  was recomputed exactly as `save_verified_export` does. **The forged export was
  accepted and stored**, with the tampered record's own `content_hash` left
  stale. Flipping `graph_admitted` is exactly the trust promotion AGENTS.md
  :53-57 forbids.
- With the forged export sitting in `phase6_verified_exports`,
  `workspace.verify_integrity()` **passes**, because it queries `phase6_records`
  while imported exports land in a different table. The workspace reports itself
  intact while holding a forgery. `verify_integrity` therefore cannot stand in
  for bundle verification, and
  `tests/test_phase6_clean_room_replay.py::test_verify_integrity_cannot_stand_in_for_bundle_verification`
  records that so the verifier is not later deleted as redundant.

Four release fields are also affirmations that no record in the bundle supports.
They fall into two materially different kinds, and one label for both would let a
reader treat a constant as a measurement of unknown quality:

*Outside the system's view.* `semantic_fidelity: "researcher_approved"`
(`service.py`:273) has no corresponding semantic-alignment review record.
`negative_and_superseded_attempts_retained: True` (`service.py`:285) is a
literal; retention *completeness* is not expressible from the bundle.

*Constants presented as measured outcomes.* Verified by reading the source:

- `_generality_controls()` (`service.py`:26-68) takes no argument and reads no
  state. All five candidates carry the literal `False` as their admission, and
  `passed` is defined as `admitted is False`, so `5/5` is structural and cannot
  vary. Its docstring says "Execute the compact trust-policy controls"; nothing
  is executed. The docstring's inaccuracy is recorded here and deliberately not
  corrected, because the producer is out of scope for this slice.
- **There is no positive control** — not one case where a pass requires
  admission. The suite therefore cannot distinguish "correctly refuses unsound
  candidates" from "refuses everything, sound candidates included". A
  blanket-refusal system scores `5/5` identically. Adding a positive control is
  the only change that would make the score informative; it is out of scope
  here, and its absence is recorded as the reason the score is uninformative,
  not as work in flight.
- The sharpest illustration: control 1 is named `unsupported_consensus` with the
  reason "model agreement cannot create proof status" — AGENTS.md's first
  engineering rule. The control asserting that rule is itself a hardcoded
  assertion granted pass status. It exhibits the exact failure mode it names.
- `simplest_baseline_passed: 0` (`service.py`:288) is a literal and the only
  occurrence of `simplest_baseline` anywhere in `src/`. The baseline the protocol
  names, `arithmetic_only_without_trust_controls`
  (`fixtures/phase6/confirmatory-protocol-v1.json`:27), is never executed and
  never referenced by name. `phase6_passed` is `controls_passed`
  (`service.py`:289), which is always 5. So the release package asserts a
  5-versus-0 comparative advantage **in which both operands are literals**. That
  is not an unverified comparison; it is a comparison that was never performed,
  formatted as a result. Of the four fields this is the most serious, and it must
  not be reported under a label as mild as "unverifiable".

The in-repo precedent for what was missing already exists one phase earlier:
`math_research.phase4b.interchange.verify_export_bytes` (:333-386) rejects
non-canonical bytes (:337), validates every record against an expected sequence
(:350-357), re-derives the projection rather than reading it (:358-364),
re-derives the envelope hashes last (:382-385), and is exposed side-effect-free
as `replay()` (:408-410).

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt: harden `save_verified_export` in place | Producer is one function; the forgery reproduces in ~20 lines | One code path; nothing new to discover | Mutates the producer this slice is meant to audit; ingest and verification stay indistinguishable; a verifier that shares the producer's helpers can share its blind spots | Rejected: the producer must stay untouched for the audit to mean anything |
| Wrap: new read-only `phase6/replay.py`, new `phase6 verify` subcommand, `replay` kept | Phase 4B `verify_export_bytes` is the same shape and is green | Independent derivation; ingest-versus-verify visible in the CLI; zero producer risk; historical `release_hash` values unaffected | Producer constants are restated and can drift | **Chosen.** Drift is pinned by the acceptance suite against the live producer |
| Interoperate: call `phase4b.interchange.verify_export_bytes` | Function exists | No new code | Wrong schema, wrong records, wrong hashes; would only appear to verify | Rejected: the brief requires mirroring its shape, not calling it |
| Build/defer: derive the four asserted fields properly | Straightforward per field | Removes the gaps outright | Changes `release_hash` for every historical Phase 6 release; needs an owner-approved release schema bump | Deferred to a separate ADR and an owner ruling |

## Decision

Add `src/math_research/phase6/replay.py` exposing
`verify_release_bundle(phase6_export_bytes, phase5_export_bytes,
phase5_fixture_bytes)`. It creates and discards a temporary clean room, copies
the three inputs into it, reads only those copies, and re-derives the release
from the bundle alone. It returns
`{"schema_version", "verified", "checks", "unverifiable", "not_derived",
"bound_identities"}` and raises `Phase6ReplayError` on anything it cannot
reproduce.

Fifteen recorded checks, grouped below in execution order (item 2 covers the
Phase 6 and Phase 5 record passes, which are two separate recorded checks).
Ordering is part of the contract, not an implementation detail:

1. canonical byte encoding, closed envelopes, bounded size, duplicate-key and
   non-finite-number rejection;
2. every Phase 6 and Phase 5 record's `content_hash` **re-derived from its
   payload**, `sequence` contiguous from zero, no duplicate `record_id`, and the
   frozen record-type emission order (which is the only thing a re-sealed
   reordering violates);
3. `protocol_hash == canonical_hash(protocol)` plus every producer guard from
   `service.py`:123-142 re-run, so a retroactively loosened protocol is refused;
4. `canonical_hash(phase5_fixture) == protocol["phase5_fixture_hash"]`, which
   holds **before** any held-out recomputation;
5. `run_case` recomputation of `case_result_hash`, warrant, applicability, and
   primal/dual agreement — the discharge of blueprint :2245;
6. generality controls compared candidate by candidate against a restated table;
7. confirmatory-run identity, frozen method, access manifest, and the Phase 5
   run binding, including `phase5_run_id` re-derived from the objective and this
   fixture;
8. `result_id`, assessment, and contribution identities, with the three
   contributions re-derived (contribution 2 names the recomputed case hash);
9. release field set, `release_hash`, `release_id`, and agreement between the
   release and every record it embeds;
10. `phase5_export_hash` agreement across the Phase 6 envelope
    (`workspace.py`:145), the release (`service.py`:267), and the supplied Phase
    5 export;
11. `material_result_count` derived from the Phase 5 export's `material_results`
    for this run, and required non-empty;
12. retained negative and superseded attempts **derived from records**: the
    expected dead-end branch set is recomputed from the fixture using the
    producer's duplicate-result rule and must equal the observed `dead_end`
    records exactly, so both a stripped and a forged dead end fail; falsification
    branches and restricting/refuting materiality classifications are counted and
    at least one negative artefact is required;
13. refusal invariants: `graph_admitted is False` (record and embedded copy),
    novelty and significance `not_assessed` and not inferred from a warrant,
    `heldout_accesses == 1`, `adaptations_after_access == 0`, `model_calls == 0`,
    `network_calls == 0`, `external_cost_usd == 0`;
14. envelope hashes re-derived last, following the Phase 4B shape.

**Reporting is split in two.** `unverifiable` names claims about facts outside
the system's view (`semantic_fidelity`,
`negative_and_superseded_attempts_retained`). `not_derived` names constants the
release presents as measured outcomes (`controls_passed`, `controls_total`,
`baseline_comparison` as a block, `baseline_comparison.simplest_baseline_passed`,
`baseline_comparison.phase6_passed`). Every entry in both lists carries
`counted_as_evidence: false`; `not_derived` entries additionally carry
`varies: false`. No field in either list appears as a check name.

One honest tension is recorded rather than smoothed over: `controls_passed` and
`controls_total` **are** bound against the re-derived constant, because an
inflated count must be refused. That binding is anti-tamper, not measurement,
and the check reports `measures_capability: false` and
`positive_control_present: false` in its own detail so it cannot be read as a
capability result. `simplest_baseline_passed` is bound to nothing at all — there
is nothing to bind it to — so a bundle with an altered baseline literal still
verifies, and the verdict reports the altered value under `not_derived`. That is
demonstrated by an explicit test, so the boundary is visible rather than assumed.

Boundaries: the producer is untouched (`phase6/service.py`,
`phase6/workspace.py`, `migrations/phase6/`,
`fixtures/phase6/confirmatory-protocol-v1.json`), asserted structurally by
pinned SHA-256 digests. `phase6 replay` is kept as ingest; `phase6 verify` is
added beside it so the ingest-versus-verify distinction is visible rather than
hidden. Verification writes nothing to any caller workspace and adds no row to
`phase6_verified_exports`. Standard library only; no network, model call, or
subprocess. Nothing here creates an `EpistemicWarrant`, approves semantic
alignment, asserts source applicability, or sets novelty or significance.

## Consequences

- **Operational.** `make check` now runs `phase6 verify` inside the phase6
  target, pinning `verified: true`, the check count, both named-gap lists, and
  that no named gap is counted as evidence. A regression in the demo bundle now
  fails the offline entrypoint.
- **Security.** The demonstrated forgery is refused at all four re-seal levels.
  A forger who re-seals the envelope fails on the record hash; who also re-seals
  record hashes fails on identity derivation; who also re-derives identities
  fails on a dangling downstream reference; who produces an internally perfect
  bundle fails on the refusal invariant or the independent `run_case`
  recomputation.
- **Reproducibility.** The verdict is byte-identical across calls and across
  processes; the acceptance suite pins its canonical hash to a literal computed
  in a different process. Frozen instants are inputs; no clock is read.
- **Negative consequence: restated constants can drift.** `PROTOCOL_FIELDS`,
  `ALLOWED_CAPABILITIES`, `EXPECTED_CONTROLS`, `EXPECTED_METHOD`,
  `EXPECTED_RECORD_TYPES`, `RELEASE_FIELDS`, and the schema-version strings are
  restated for independence. `test_restated_producer_constants_do_not_drift`
  compares each against the live producer, so drift fails loudly rather than
  silently weakening the check.
- **Negative consequence: brittleness by design.** The producer digest pin, the
  frozen record-type order, and the verdict-hash pin all fail on legitimate
  future change. Each failure message says what to update. This follows the
  ADR-0031 phase4c precedent: a silent improvement to a frozen artefact is an
  unreviewed change.
- **Negative consequence: the four asserted fields are still asserted.** This
  slice names them; it does not fix them. A reader who ignores `not_derived`
  can still misread `5/5` and `5 versus 0` as measurements.
- **Migration.** None. No schema, no migration, no stored data changes, and no
  historical `release_hash` moves.
- **Licensing.** No dependency added.
- **Testing.** `tests/test_phase6_clean_room_replay.py` adds 59 tests and no
  skips. The existing seven assertions in `tests/test_phase6_confirmatory.py` are
  unmodified. The suite skip count stays at 16, so
  `.github/workflows/check.yml`:56-59 and :65 are untouched.

## Blueprint deviation

Two real deviations, both taken deliberately.

**1. Order deviation: WP5 work taken ahead of WP4.** ADR-0026:58-60 records the
accepted order as WP4 (noncommuting Phase 5 expansion and search tiers 2–4),
then WP5 (Phase 6 external evaluation and release hardening). This slice is WP5
work executed first. *Necessity:* the defect is live in the current tree — an
export with `graph_admitted` flipped to `true` is accepted today, and that is the
one promotion AGENTS.md:53-57 forbids absolutely. Leaving a trust-boundary hole
open through an entire work package to preserve sequencing would trade a real
integrity failure for a scheduling preference. Nothing here enables any WP5
capability beyond verification: no external evaluation, no novelty or
significance assessment, no new search tier. *Revisit trigger:* if WP4 lands and
extends the Phase 5 record set or the noncommuting result shape, the restated
`RELEASE_FIELDS`, `EXPECTED_RECORD_TYPES`, and Phase 5 record-identity rules must
be re-derived against the new producer, and the digest pins re-taken.

**2. Scope deviation: only the replay half of blueprint :2236.** That bullet is
"clean-room replay **and release packaging**". This slice delivers replay
verification and defers packaging entirely — no signed or distributable release
artefact, no publication path, no external distribution format. *Necessity:*
packaging an artefact whose contents could not be independently re-derived would
ship the forgery surface rather than close it, so verification is the correct
half to take first; and packaging touches the release schema, which is exactly
what deriving the four asserted fields also requires. *Revisit trigger:*
packaging must be a separate slice with its own ADR, and it should be sequenced
after — or together with — the owner ruling on deriving `semantic_fidelity`,
`negative_and_superseded_attempts_retained`, and the baseline comparison, because
both change `release_hash` for every historical Phase 6 release and a single
schema bump should carry both.

A third, smaller departure from this slice's own brief is recorded here rather
than buried: canonical **byte** encoding is enforced on the two machine-produced
export envelopes but not on `phase5_fixture_bytes`. The repository's own fixture
(`fixtures/phase5/quantum-diagonal-v1.json`) is indented, human-authored, and
carries no declared hash of its own; the protocol binds it by *value*
(`canonical_hash`). Enforcing byte canonicality there would make the verifier
reject the very artefact the frozen protocol pins. The verifier therefore binds
the fixture by value and reports `phase5_fixture_bytes_canonical` as an
observation in its `canonical_input_encoding` check detail. If a future fixture
format carries its own declared hash, this should become an enforced check.

## Validation and revisit trigger

Checks that keep this decision valid:

- `make check` (which runs `make test` and the phase6 target) stays green, with
  the phase6 target asserting `verified: true`, exactly 15 checks, both named-gap
  lists pinned in order, and no named gap counted as evidence.
- The suite skip count stays at 16.
- Every tamper case in `tests/test_phase6_clean_room_replay.py` continues to be
  refused *after* re-sealing, at the recorded level and with the recorded reason.
- `test_producer_files_are_untouched` and
  `test_restated_producer_constants_do_not_drift` both hold.
- `test_verify_integrity_cannot_stand_in_for_bundle_verification` continues to
  demonstrate that the workspace's own integrity check does not cover an
  imported bundle.

Evidence that would cause reconsideration:

- An owner ruling to derive `semantic_fidelity`,
  `negative_and_superseded_attempts_retained`, or the baseline comparison, with
  the release schema bump that implies. `not_derived` should shrink accordingly.
- A positive generality control being added, which would make the control score
  informative and change what `controls_passed` means.
- A decision to harden `save_verified_export` itself, at which point the
  producer-untouched claim, the digest pins, and
  `test_currently_accepted_forgery`-style expectations must all be revised in the
  same change.
- WP4 landing and changing the Phase 5 or Phase 6 record shape.
- Release packaging being scheduled, which should supersede the scope half of
  the deviation above.
