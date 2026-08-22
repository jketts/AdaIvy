# Mathematics Problem Runbook

This is the shared procedure for Codex, Claude, and human operators handling a
mathematics problem in this repository. `AGENTS.md` takes precedence.

## Current limitation

The intended one-command research workflow is not implemented yet. Consult
`docs/CAPABILITY_STATUS.md` before starting. Until the end-to-end plan lands,
the host agent must not bridge missing campaign steps invisibly or call its own
work an AdaIvy discovery.

The current mandatory pre-research human novelty checkpoint remains active
under ADR-0055. The proposed runtime plan replaces it with campaign-contained,
non-authoritative search plus human review before publication, but that proposal
does not change current authority.

## Trust rule

A model response, retrieved passage, generated program, experiment, or proof
fragment is a proposal. Do not call a result solved, proved, refuted, novel, or
significant unless the corresponding records and applicable verifier support
that exact statement.

Lean checks the encoded proposition. It does not prove that the encoding matches
the informal problem, that a cited theorem applies, or that the result is new.

## 1. Check the environment

```bash
.venv/bin/python -V
make help
```

Use CPython 3.14. Use `.venv/bin/python` for live/provider operations. Offline
checks use `make check`. Network is off by default; only an explicitly activated
live command may open it.

## 2. Define and validate the problem

Create a declarative problem definition using the schema and fixture as guides:

```bash
PYTHONPATH=src .venv/bin/python -m math_research.cli problem schema
PYTHONPATH=src .venv/bin/python -m math_research.cli problem validate PROBLEM.json
PYTHONPATH=src .venv/bin/python -m math_research.cli problem create \
  PROBLEM.json RECORDED_AT work/RUN/dossier.json
PYTHONPATH=src .venv/bin/python -m math_research.cli inspect work/RUN/dossier.json
```

Freeze the informal statement, objects, quantifiers, assumptions, target,
semantic alignment, success criteria, budget, and stopping rules. Do not repair
ambiguity silently.

## 3. Satisfy the applicable research-start gate

The legacy `campaign run` contract still requires a human-created
`before_research` novelty re-check bound to the dossier hash and campaign ID:

```bash
PYTHONPATH=src .venv/bin/python -m math_research.cli novelty create before_research \
  SUBJECT_ID sha256:DOSSIER_HASH CAMPAIGN_ID HUMAN_ID PERFORMED_AT RECHECK.json \
  --recheck-id RECHECK_ID --protocol-id PROTOCOL_ID \
  --query-term TERM --searched-source SOURCE \
  --equivalence-check EQUIVALENT_FORMULATIONS_REVIEWED \
  --evidence-ref EVIDENCE_ID sha256:EVIDENCE_HASH \
  --outcome inconclusive --limitation COVERAGE_LIMIT
```

Allowed outcomes are `prior_art_found`, `not_found_under_protocol`, and
`inconclusive`. An empty search never means novel.

The ADR-0072+ v2 path instead records literature search before substantive
research under its initial bounded authorization. This does not remove the
mandatory `before_announcement` review.

## 4. Run only available capability paths

Use `docs/CAPABILITY_STATUS.md` to distinguish implemented components from
activated ones. The deterministic `campaign start` fixture traverses search,
acquisition, embedding, retrieval, experiment, and exact verification. The
model-driven v2 runtime can select those actions through an injected, closed
effect registry. This is orchestration evidence, not authorization for live
provider, discovery, snapshot, embedding, workspace OCI, Lean, or typesetting
effects.

If the operator runs a live campaign, every internal provider call must use the
selected AdaIvy configuration and appear in the campaign ledger. Work performed
by the host agent remains an explicit `external_codex`, `human`, or
`external_system` import.

Do not invent an ad hoc bridge between components and present it as a completed
campaign. A live run must first pass `campaign live-acceptance` with the sealed
gate active, the exact acknowledgement, and every named activation record. The
checked-in gate is pending and therefore refuses before network I/O.

## 5. Record conventions and target scope

For a contested term, use a content-hashed `ConventionRecord` with at least two
source-anchored readings. A named external target requires a `VerdictMatrix`
covering exactly the enumerated readings. Scope is derived and may demote the
claim; no input field may promote it.

```bash
PYTHONPATH=src .venv/bin/python -m math_research.cli conventions inspect \
  CONVENTIONS.json --matrix VERDICT_MATRIX.json
```

## 6. Verify candidates

Use an applicable exact verifier when one exists. Use the sealed Phase 3B Lean
runtime for an exact Lean statement and proof fragment:

```bash
make check-sealed
```

The current Phase 3B bridge does not derive Lean from informal mathematics and
does not machine-check statement correspondence. Only safe elaboration failures
may enter its bounded repair loop. Policy, meaning-test, and unapproved-
assumption failures remain terminal for that candidate.

The target runtime will make Lean accessible as a campaign action and normally
use it at the end for claims with an approved Lean representation. Until that
wiring exists, report Lean as a separate verification stage.

## 7. Report from records

Do not hand-edit a publication projection. The records are authoritative;
`paper.tex` and `paper.pdf` are derived products.

```bash
PYTHONPATH=src .venv/bin/python -m math_research.cli publication render \
  MANUSCRIPT.json --output-dir work/RUN/bundle
PYTHONPATH=src .venv/bin/python -m math_research.cli publication inspect \
  work/RUN/bundle
```

Publication approval requires the separate `before_announcement` human novelty
re-check over the exact result. Rendering is not approval.

## 8. Close the gates

```bash
make check
```

Run additional named live, OCI, Lean, or typesetting gates when the work touches
those capabilities. A missing prerequisite is a recorded blocker, never a pass.
Retain failed and inconclusive attempts.

`make check-campaign-live-definition` validates the Slice 16 gate definition
offline. It does not execute or activate a live campaign.

## Terminal outcomes

Acceptable outcomes include a verified proof, verified counterexample,
conditional theorem, reduction to named open obligations, reproducible partial
result, budget exhaustion, or explicit infrastructure/policy blocker. State
exactly which stage completed and which did not.
