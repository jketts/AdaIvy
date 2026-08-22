# ADR-0064: Phase 4A embedding rights bind a named processor

- **Status:** accepted and implemented; the first of three slices activating
  embedding-backed semantic retrieval, and a hard prerequisite for ADR-0069
  and ADR-0070. Superseded in part by ADR-0072: the human-authorship mechanism
  for per-document rights decisions, the
  `pr.nonhuman-embedding-decision-refused` probe, and the
  non-human-author revisit item are superseded (per-document decisions may be
  deterministically derived from an operator-approved content-hashed
  source-and-rights policy; a model still may not author one); the named
  processor, one-decision-one-processor rule, and every other clause stand.
- **Date:** 2026-08-22
- **Blueprint requirement:** Section 12.2.1 (provider binding for vector
  projections); Section 2 C1 (provenance completeness), C12 (citation
  applicability); ADR-0017 (Phase 4A local rights); ADR-0031 (the deferral this
  slice lifts)
- **Decision owners:** repository owner and researcher

## Context

`TECHNICAL_BLUEPRINT.md:1672-1675` states the rule this ADR implements:

> "Rights bind the processor, not only the use. A current Phase 4A `embedding`
> rights decision authorizes a named processor. Sending the same source text to
> a second provider requires its own decision, because it is a distinct
> disclosure."

Nothing in the implementation can express that sentence. `RightsUse.EMBEDDING`
exists at `src/math_research/phase4a/records.py:35` and, verified by full-repo
grep, is referenced nowhere else: no service call, no test, no fixture. It is an
enum value awaiting an implementation, exactly as `docs/TECHNICAL_DETAILS.md:216-218`
records.

The obstruction is that a rights decision has no place to put a processor name.
A decision is a generic `AuditRecord` whose `payload` is a **closed** six-field
object -- `source_id`, `intended_use`, `value`, `valid_from`, `valid_until`,
`lifecycle_id` -- enforced by an exact field-set check at
`src/math_research/phase4a/validation.py:224-229` and mirrored for durable
records at `validation.py:374-388`, against `schemas/phase4-review-v1.schema.json`
`$defs/rights`.

So granting `embedding` today would produce a decision that authorizes the *use*
while saying nothing about *who receives the text*. That is precisely the
disclosure the blueprint separates, and ADR-0031:72 already names the failure
mode: reusing `EMBEDDING`/`MODEL_CONTEXT` against their meaning.

Three consequences of the closed schema are load-bearing and must be stated
before the decision rather than discovered during it:

1. The rights payload field set is closed in ONE place, not two. **This ADR
   originally said two and was wrong.** `_exact(...)` for the rights payload
   exists only in `_validate_payload`, which both `validate_record_for_append`
   and `validate_durable_records` reach through `validate_structure`. What is
   duplicated at `validation.py:374-388` is the *domain* block -- reason/value
   consistency and timestamp checks -- not the field set. The coupling rule
   therefore belongs in the shared structural check, mirrored defensively in both
   domain blocks to match the file's existing idiom.
2. `PRODUCTION_SCHEMA_SHA256` at `validation.py:28` pins the schema digest. Any
   field addition moves it.
3. ADR-0026:108-110 routes any slice touching the Phase 4A rights boundary back
   to the full gate package -- entry gate, acceptance fixtures, protected
   evidence, production-path tests, owner approval -- rather than the lightweight
   per-slice process. **This slice is therefore not lightweight, and pretending
   otherwise would be the cheapest way to get it wrong.**

## Options considered

| Option | Evidence | Benefits | Cost/risk | Decision |
|---|---|---|---|---|
| Encode the processor in `lifecycle_id` | field exists, no schema change | zero schema churn; ships today | reuses a field against its meaning, the exact error ADR-0031:72 names; a processor becomes invisible to validation and unqueryable; silently defeats the blueprint rule while appearing to satisfy it | Rejected |
| Grant `embedding` with no processor binding | `RightsUse.EMBEDDING` already exists | no schema change at all | authorizes disclosure to an unnamed recipient; a second provider inherits the first's grant, which `TECHNICAL_BLUEPRINT.md:1674-1675` forbids in terms | Rejected |
| Add a `processor` object to the closed `rights` payload | `validation.py:224-229`; `$defs/rights` | says what the blueprint says; validated, queryable, per-processor expiry inherited from existing validity semantics | moves `PRODUCTION_SCHEMA_SHA256`; reopens the ADR-0026 gate package; existing rights fixtures must be regenerated | **Selected** |
| New `EMBEDDING_PROCESSOR_DECISION` record type beside rights | `RecordType` is an enum, extensible | leaves the rights payload untouched | still a Phase 4A schema change with the same digest and gate consequences, and splits one authorization across two records so a partial grant becomes representable | Rejected: same cost, worse invariant |

## Decision

Extend the Phase 4A rights payload with a required `processor` field, and make it
load-bearing for `embedding` and `model_context` decisions.

`processor` is an object with a closed field set:

- `processor_id` -- id-pattern identifier, e.g. `processor.azure-openai.text-embedding-3-large`
- `provider` -- must be a member of `SUPPORTED_LIVE_PROVIDERS`
- `model_identifier` -- non-empty string
- `disclosure_kind` -- one of `text_leaves_process`, `text_stays_local`

For every `intended_use` other than `embedding` and `model_context`, `processor`
must be `null`: acquisition and parsing do not disclose text to a third party,
and a processor named there would be decoration that later reads as an
authorization. For `embedding` and `model_context` it must be present.

### Named boundaries

- **One decision authorizes one processor.** Rights lookup already keys on
  `(source_id, intended_use)` and takes the latest decision
  (`service.py:158`). `require_rights` gains an optional `processor_id`
  argument; when supplied and the live decision names a different processor, the
  outcome is a new `RightsOutcome.PROCESSOR_NOT_AUTHORIZED` and
  `require_rights` raises `RightsBlocked` as it does for every other
  non-permitted outcome. A caller that omits `processor_id` for an `embedding`
  use is a programming error and raises, rather than defaulting to permitted.
- **A second provider is a second decision, never an inherited one.** There is
  no wildcard `processor_id`, no `any`, and no fallback. This mirrors §12.2.1's
  no-fallback-partition rule on the storage side.
- **`disclosure_kind` is recorded, not inferred.** A local model still discloses
  text to a process boundary and still needs a decision; the field distinguishes
  the two cases for audit without making either automatic.
- **Expiry semantics are inherited unchanged.** `valid_from`/`valid_until` and
  the revocation/takedown override at `service.py:129-144` apply to embedding
  decisions exactly as to every other use. An expired embedding decision means
  no new vectors may be produced; it does not retroactively invalidate vectors
  already produced under it, which is ADR-0069's retention question and is
  explicitly open here.
- **Human authority is unchanged and unweakened.** Rights decisions stay pinned
  to `(ActorKind.HUMAN, Authority.HUMAN_FINAL)` at `service.py:110` and
  `validation.py:287`. No model, automation, or campaign may author one.

## What this decision does not license

It does not create an embedding capability: no provider port, no vector, no
index, no retrieval change. Those are ADR-0069 and ADR-0070 and each needs its
own decision. It does not assess novelty, significance, or source
applicability, does not create mathematical warrant or graph admission, and does
not make any source applicable to any claim. Granting the right to embed a
document says nothing whatever about whether that document supports a claim --
`TECHNICAL_BLUEPRINT.md:176-182` (C12) keeps bibliographic existence and
mathematical applicability separate verdicts, and a vector cannot bridge them.

## Consequences

- `PRODUCTION_SCHEMA_SHA256` moves. Every existing rights fixture, including
  `fixtures/phase4a-production/canonical-workflow-v1.json`, must be regenerated
  with an explicit `"processor": null`, and the differential conformance test at
  `tests/test_phase4a_schema_conformance.py:132-159` must round-trip the new
  field through the real Draft 2020-12 validator.
- The ADR-0026 full gate package applies. This is the stated cost of touching
  the rights boundary and is not negotiable down.
- A durable workspace written before this change re-verifies as invalid, because
  the closed field set changed. Existing Phase 4A workspaces are gate artifacts
  under `work/`, which is gitignored and per-run fresh, so there is no migration;
  a persisted production workspace, if one ever exists, is a rebuild.
- `RightsOutcome` gains a seventh member, so the
  `test_six_rights_outcomes_and_per_use_separation` test at
  `tests/test_phase4a_production.py:194` becomes a seven-outcome test.

## Blueprint deviation

None. This slice implements a blueprint rule that had no implementation, and
narrows what a rights decision can mean rather than widening it.

## Falsifiability probes

Each mutates one field and must produce the named refusal. `probes_flipped ==
probes_total` is a release gate, because a rule that cannot be made to fail
proves nothing.

- `pr.embedding-rights-require-processor` -- an `embedding` decision with
  `processor: null` must refuse with `embedding_use_requires_processor`.
- `pr.acquisition-rights-forbid-processor` -- an `acquisition` decision naming a
  processor must refuse with `non_disclosing_use_forbids_processor`.
- `pr.processor-mismatch-blocks` -- `require_rights` for a processor other than
  the one named must yield `PROCESSOR_NOT_AUTHORIZED`, not `PERMITTED`.
- `pr.processor-omitted-for-embedding-raises` -- calling `require_rights` for
  `embedding` without a `processor_id` must raise, not pass.
- `pr.second-provider-not-inherited` -- with a live decision for provider A,
  a request naming provider B's processor must be refused.
- `pr.unknown-provider-refused` -- a processor whose `provider` is outside
  `SUPPORTED_LIVE_PROVIDERS` must refuse at validation.
- `pr.expired-embedding-decision-blocks` -- a decision past `valid_until` must
  yield `EXPIRED`, not `PERMITTED`.
- `pr.nonhuman-embedding-decision-refused` -- a decision authored with
  `ActorKind.MODEL` or `Authority.PROPOSAL` must refuse.
- `pr.processor-field-set-closed` -- an unknown key inside `processor` must
  refuse rather than be ignored.

## Validation and revisit trigger

The decision stays valid while: the rights payload field set stays closed in
both validation paths; `processor` stays required for the two disclosing uses
and forbidden for the rest; every probe flips; and rights decisions stay
human-authored.

Reconsider if a provider ever needs more than one embedding model under one
decision -- the answer is a second decision, and a request to relax that is a
signal the partitioning rule is being eroded.

Revisit with a new ADR before: allowing a processor wildcard; letting a
non-human author a rights decision; making an expired decision invalidate
already-produced vectors; or extending `processor` to non-disclosing uses.

## Explicit deferrals

- The provider port, vector arithmetic, and artifact store: ADR-0069.
- The retrieval signal and any fusion change: ADR-0070.
- Corpus ingestion beyond the frozen Phase 4C fixture set: unaddressed here and
  the real limit on "wide" retrieval; see ADR-0070's context.
- Whether vectors produced under a later-revoked decision must be deleted: an
  ADR-0021 deletable-content question, open.
