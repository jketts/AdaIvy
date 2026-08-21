# ADR-0043: The Phase 2 to Phase 3B request bridge carries provenance, not meaning

- **Status:** accepted for the bounded request-bridge slice; implemented
  21 August 2026 with the acceptance suite in
  `tests/test_phase3b_request_bridge.py` (44 tests, offline)
- **Date:** 2026-08-21
- **Blueprint requirement:** Section 4.15 semantic custody, Section 5 trust
  model (proposal-only tool output), Section 12 formal-checking boundary,
  Section 21.2 inward dependency direction
- **Decision owners:** repository owner

## Context

Phase 3B is an island, and the two halves of that sentence are measured.

**Measured: nothing outside the dispatcher references it.** `grep -rn phase3b
src --include='*.py'`, excluding `phase3b/` and `phase3b_cli.py` itself, returns
five lines and all five are in `cli.py`: the subparser, its `REMAINDER`
argument, and the lazy dispatch. No phase produces a `FormalCheckRequest`.

**Measured: the request consumes hand-authored Lean.**
`phase3b/records.py:FormalCheckRequest` carries `target_statement` and
`proof_fragment` as restricted Lean strings, and the only requests in the tree
are the nine hand-authored JSON files in `fixtures/phase3b/`, which
`phase3b/demonstration.py` reads. There is no code path from a Phase 2 run to
the kernel.

**Measured: the ceiling this creates.** `publication/evidence.py` reaches
`kernel_checked_theorem` only for an attestation whose outcome is bare
`kernel_checked`, with no unapproved assumption, on a `verified`
representation. Absent any producer of such an attestation, every new problem
tops out at `Conjecture` no matter how much Phase 2 work it accumulates. The
`make check` publication target asserts exactly that:
`kernel_checked_theorem == 0`.

**Measured: the defect to avoid.** The offline Phase 2 path already exhibits the
failure this bridge could industrialise. `reports/phase-2` holds a committed
proposal whose payload is the *even integers* argument
(`Let a=2k and b=2l; then a+b=2(k+l)`), and the same canned candidate is what
`deterministic_fake_results` emits for whatever `target_claim_id` it is handed.
A bridge that paired that text with an unrelated claim ID, or paired unrelated
Lean with that claim ID, would look exactly like a working formalization
pipeline.

Three constraints follow, and the honest one is first.

1. **Prose-to-Lean translation is out of scope and must not be faked.** A Phase
   2 `mathematical_payload` is prose plus informal steps. Producing Lean from it
   is a modelling problem; producing Lean *near* it is worse than producing
   none, because the result carries a claim ID that says it is about something
   specific.
2. **Building a request must not require the sealed runtime.** ADR-0016's image
   is a separate `make check-sealed` target by design. Construction has to be
   part of the offline gate, so it cannot import the adapter.
3. **Identity is checkable; meaning is not.** A bridge can compare identifiers,
   hashes, and record links. It cannot compare a paragraph of English with a
   Lean proposition. Any design that blurs those two is the trust hole.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Adopt (generate Lean from the Phase 2 payload) | `deterministic_fake_results` shows how easily canned text attaches to an arbitrary claim ID | Would look end-to-end | Fabricates the one step nothing here can do; a template that "usually" matches produces kernel-checked theorems about the wrong statement | Would need a measured translation-fidelity result; none exists |
| Adopt (reuse `fixtures/phase3b/*.json` per problem) | Status quo | No new code | Every problem is a hand-edited JSON file with a hand-copied claim ID; no lineage from a finding to a proposal; the mod-4 defect by hand | -- |
| **Wrap (envelope-and-provenance bridge; Lean is an input)** | `FormalCheckRequest` already separates identity from Lean text; `SQLiteWorkspace` and `FileArtifactStore` already expose the read side | Closes the seam today; claim ID and alignment ID come from the dossier; the proposal artifact hash, run and model call become durable lineage; works offline | A well-formed request is not a *correct* formalization; the correspondence stays unverified and must be visible as such | Correspondence recorded as unchecked; refusal on any absent input; no warrant, no approval flag; determinism |
| Interoperate (have Phase 2 emit requests itself) | `baseline_loop.py` drives off `dossier.formalization` only | No new module | Puts Lean authoring inside the model loop, where a model's Lean would arrive with the model's own claim about what it proves | Would need `phase2/` changes, which this slice is forbidden to make |
| Build/defer (leave the island) | -- | -- | The measured ceiling stays at `Conjecture`; the gap is architectural, and AGENTS.md forbids silent drift | -- |

## Decision

Adopt the wrap option.

Add `src/math_research/phase3b/bridge.py`, four `bridge-` prefixed subcommands
on `src/math_research/phase3b_cli.py` (`bridge-request`, `bridge-attest`,
`bridge-status`, `bridge-trace`), and one append-only migration in its own
sequence, `migrations/phase3b-bridge/0001_request_bridge.sql`. `phase2/`,
`publication/`, `review*`, `domain/entities.py`, `cli.py`, `AGENTS.md`, the
`Makefile`, and **every pre-existing module in the `phase3b` package** are
unchanged; `phase3b_cli.py` is the single edited file.

Nine boundaries are part of this decision.

**The slice is additive, so it cannot collide with another Phase 3B slice.**
Every symbol -- the records, the ports, the store, the validators -- lives in
`bridge.py`. Nothing is added to `phase3b/__init__.py`, `records.py`,
`validation.py`, `serialization.py`, `ports.py`, or `workspace.py`, and nothing
is added to the `migrations/phase3b/` sequence: the store keeps its own
`bridge.sqlite3` beside `workspace.sqlite3` in the same workspace directory,
under its own migration directory. The findings side is read through a
`FindingSource` Protocol rather than by importing `FormalCheckWorkspace`, so
there is no import cycle and no dependency on that module's shape. Every command
name is `bridge-` prefixed, reserving no generic verb such as `prepare`,
`build`, `repair`, or `trace`. `AdditiveSliceTests` asserts all of this:
no pre-existing `phase3b` module mentions the bridge, the two migration
sequences are disjoint, and the registered subcommand list is pinned
byte-for-byte.

**The bridge never authors Lean.** `target_statement` and `proof_fragment` are
file inputs. There is no template, no fallback, no completion, and no repair. An
absent, empty, oversized, or non-UTF-8 input is a structured refusal that names
the field (`missing_lean_input`, `empty_lean_input`, `lean_input_too_large`,
`invalid_utf8`), and Lean that violates the ADR-0016 policy is refused with that
policy's own codes rather than rewritten.

**The claim ID is read, never invented and never parsed out of Lean.** It comes
from `dossier.formalization.target_claim_id`; `semantic_alignment_id` comes from
`dossier.semantic_alignment.id` with its status and `approved_by` recorded as
read. The record states `claim_id_source` and carries
`claim_id_derived_from_lean: false`, and `validate_bridged_record_dict` refuses
any document that flips either.

**The correspondence is named as unchecked, and the name cannot be misread.**
Every record carries `bridge_correspondence_check: "none_performed_by_bridge"`
and, at build time, `correspondence_state_at_build:
"unattested_operator_correspondence"`. The SQLite schema enforces both with
CHECK constraints, so no row can exist that claims the bridge compared the prose
with the Lean. A deliberately mismatched pair -- the even-sum payload with a
mod-4 Lean statement -- is *carried*, and the acceptance suite asserts that it
is carried rather than caught, because pretending otherwise would be the lie
this ADR exists to prevent.

**Attestation is separate, named, and still not verification.**
`bridge-attest` appends a `CorrespondenceAttestation` with a required
attester principal, `attester_role: operator`, `basis: human_reading`, an
explicit instant, and the operator's own statement, binding the payload hash and
both Lean hashes. There is no tool-checked basis, because no tool here checks
it. The state is *resolved* from the append-only records by
`resolve_correspondence`, never stored as a mutable column: absent a resolving
attestation the answer is `unattested_operator_correspondence`, and the resolved
view always reports
`correspondence_machine_verified_by_this_slice: false`.

**Identity cross-checks are performed and their limit is stated.** The bridge
refuses when the proposal record or the artifact names a claim other than the
dossier's target (`proposal_target_claim_mismatch`,
`artifact_target_claim_mismatch`), when the proposal names no claim, when the
artifact carries no `mathematical_payload`, or when the stored dossier does not
re-derive the run's `dossier_hash`. These compare identifiers. They say nothing
about whether the Lean means the claim.

**Provenance is durable and traceable in both directions.** The record binds the
run, run status, dossier ID and hash, proposal ID, kind, disposition, source
kind, artifact hash, `model_call_id` (present only when the proposal's source
kind is `model`), and the canonical hash of the payload itself. Both request
hashes are stored, so a finding resolves without any change to the findings
table: `request_canonical_hash` equals the finding's
`wrapper_manifest.source_hash`, `request_bytes_hash` equals the sha256 of the
bytes handed to `phase3b check`, and the content-derived `request_id` is the
fallback for a policy-rejection finding that has no wrapper manifest.
`phase3b bridge-trace <workspace> <finding-id>` resolves a finding to the exact
proposal it formalizes -- and reports `bridge_provenance: absent` for a
hand-authored request rather than inventing a lineage.

**Nothing grants trust.** Records carry `disposition: proposal`,
`trust_effect: none`, and a `trust_grants` block whose six fields --
semantic alignment, source applicability, novelty, significance, contribution,
and `epistemic_warrant_created` -- are permanently `false`. The workspace
refuses to persist a record in which any is true, and no CLI flag exists to set
one.

**Time and identity are inputs, not observations.** `--created-at` is a required
explicit UTC instant, matching the ADR-0039 convention. `request_id`, the
derived `declaration_name`, and `bridge_id` are content hashes of the semantic
preimage. Following the Phase 3B semantic/operational split, `created_at` and
the operational block (file paths, raw byte lengths, raw source-byte hashes) sit
outside `content_hash` and inside `operational_hash`: moving the input files or
adding a trailing newline changes the operational hash and nothing else. The
module imports no clock, `random`, `secrets`, `time`, or `subprocess`, and the
acceptance suite asserts their absence by parsing the module source.

The recorded command sequence from a parked Phase 2 run to a checked request:

```
python3 -m math_research.cli phase3b bridge-request \
  --phase2-workspace reports/phase-2 \
  --artifacts reports/phase-2/artifacts \
  --run-id run.phase2.demo.fake.v1 \
  --proposal-id proposal.run.phase2.demo.fake.v1.proposer \
  --target-statement fixtures/phase3b/bridge/even-sum-target.lean \
  --proof-fragment fixtures/phase3b/bridge/even-sum-proof.lean \
  --lean-source-kind operator --lean-authored-by operator.example \
  --created-at 2026-08-21T00:00:00Z \
  --workspace WS --output WS/request.json --record WS/record.json

python3 -m math_research.cli phase3b bridge-attest <bridge-id> \
  --workspace WS --attester operator.example --attested-at 2026-08-21T01:00:00Z \
  --statement "read the payload and the Lean target together"

python3 -m math_research.cli phase3b check WS/request.json --workspace WS   # sealed image
python3 -m math_research.cli phase3b bridge-trace WS <finding-id>
```

The first, second, and fourth commands are offline. Only the third needs the
ADR-0016 v5 image, and its absence is a failure of that step alone.

## Consequences

- **Operational.** `phase3b` gains an offline surface, so a request can be built
  and reviewed on a machine with no container runtime and executed elsewhere.
  The store creates `bridge.sqlite3` on first use inside the workspace
  directory; existing Phase 3B workspaces and their `formal_check_attempts`
  table are untouched, and `BridgeStore.migration_versions` reports
  `phase3b-bridge:0001` separately from the findings database.
- **Security.** The Phase 2 port exposes only `get_run`, `load_dossier`, and
  `list_proposals`, so the bridge cannot write to the run it formalizes; the
  acceptance suite hashes the Phase 2 database before and after a build. Neither
  the SQLite workspace nor the artifact store is created on demand: a mistyped
  path is a refusal, not a silently empty run.
- **Reproducibility.** Two builds from the same inputs produce byte-identical
  request bytes and byte-identical record bytes. A rebuild at a different
  instant yields the same `bridge_id` and `content_hash` with different
  canonical bytes, and the append-only store refuses it as a rewrite rather than
  overwriting.
- **Negative consequence, stated plainly.** A bridged request is a well-formed
  envelope, not a correct formalization. If the sealed runtime later reports
  `kernel_checked` for a request whose Lean does not express the claim, the
  system holds a kernel-checked proof of the wrong statement carrying the right
  claim ID. The correspondence field, the resolver, and the attestation record
  make that visible; they do not make it impossible. Any consumer that promotes
  a claim on a Phase 3B attestation must read the correspondence state first,
  and `publication/evidence.py` does not yet do so -- see the revisit trigger.
- **Negative consequence.** An operator attestation is a human assertion. It is
  worth exactly what the named attester's reading is worth, and the record says
  so (`basis: human_reading`).
- **Licensing.** None. Standard library only; no new dependency.
- **Migration.** No existing record changes. `FormalCheckRequest`,
  `FormalCheckFinding`, and every hash profile in `phase3b/serialization.py` are
  untouched, so previously exported findings still import.
- **Testing.** `tests/test_phase3b_request_bridge.py` runs inside `make check`
  and needs no image: the one finding it builds comes from the pure
  `verify_output` classification path over a synthetic execution transcript.

## Blueprint deviation

None. The bridge adds no entity, changes no trust semantics, and creates no
warrant. It depends inward (Phase 3B reads Phase 2 records and the Phase 1
canonical dossier hash), which `phase3b/workspace.py` already did by building on
`SQLiteWorkspace`. One convention is bent deliberately and recorded here rather
than hidden: the repo keeps `Protocol` ports in `<phase>/ports.py`, and this
slice keeps its three ports in `bridge.py` instead, so that no pre-existing
module in the package is edited. Reconcile at the next Phase 3B slice if that
package-wide convention matters more than merge isolation.

## Validation and revisit trigger

The acceptance suite is the executable record. It asserts: the bridged request
parses under `parse_request_bytes`; two builds are byte-identical; an absent
Lean input is a structured refusal naming the field; the claim ID equals the
dossier's target and the Lean does not even contain it; a mismatched
prose/Lean pair is carried with the correspondence unattested; the operator
attestation is recorded with its named attester and never rewrites the bridge
row; a record that claims a correspondence check, claims its claim ID came from
Lean, or grants any orthogonal decision is refused; a finding traces back to the
exact proposal, and a finding with no bridge reports absent lineage.

Reconsider when any of the following holds.

1. **A consumer promotes on a Phase 3B attestation without reading the
   correspondence state.** `publication/evidence.py` currently promotes to
   `Theorem` on a bare `kernel_checked` outcome plus a `verified`
   representation, with no reference to this bridge. That is the next slice's
   work, not a silent assumption of this one: until it lands, a kernel-checked
   bridged request can reach `Theorem` with an *unattested* correspondence.
2. **Someone proposes machine-checking the correspondence.** That needs its own
   ADR, its own measured fidelity result, and a different name for the field --
   never a redefinition of `none_performed_by_bridge`.
3. **Another Phase 3B slice wants a shared record or port.** The ports and the
   trust-grant block in `bridge.py` are plausible candidates for
   `phase3b/ports.py` and `phase3b/records.py`. Moving them is a deliberate
   consolidation with its own review, not a drive-by edit.
4. **A second Lean authoring source appears.** `external` is refused today
   because the bridge cannot name the responsible third party; admitting it
   requires deciding who is accountable for the text.
5. **The Phase 3B request schema grows a field.** `FormalCheckRequest` is
   validated by `parse_request` with exact-field matching, so a new field fails
   this bridge closed rather than silently defaulting.
