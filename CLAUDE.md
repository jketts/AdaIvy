# CLAUDE.md — how Claude invokes AdaIvy on a mathematics problem

`AGENTS.md` is the repository's normative instruction file and takes precedence
over this one. Read it, plus `README.md`, `TECHNICAL_BLUEPRINT.md`, and the ADRs
it names, before changing architecture or phase scope. This file covers one
narrower thing: **what to do when a user hands you a mathematics problem.**

## The one rule

A mathematics problem handed to this repository is not a question to answer in
chat. It is an input to a verification pipeline. Whatever you derive in your own
reasoning is a *proposal* with no epistemic warrant, and it stays a proposal
until an applicable verifier grants a scoped one. So:

- Do not present a derivation, a proof sketch, or a counterexample as a result.
- Do not say "solved", "proved", "refuted", "novel", or "significant" about
  anything the records do not say. Those five words are record-derived, never
  author-supplied.
- Model agreement is not evidence. Your own confidence is not evidence.
- A missing prerequisite (no container image, no TeX engine, no certificate)
  produces an explicit blocker record. It is never a pass.

You may reason freely about the mathematics. You may not let that reasoning
enter a record, a report, or a claim of status except through the stages below.

## Before anything runs

```bash
.venv/bin/python -V   # must be CPython 3.14.x
```

Use `.venv/bin/python` for anything live or provider-touching; bare `python3`
misreports a missing SDK as an absent capability. `make check` sets
`PYTHONPATH=src` and `PYTHONDONTWRITEBYTECODE=1` itself; direct CLI calls need
`PYTHONPATH=src`.

Every timestamp is an **argument**, never a clock read — the acceptance paths are
byte-reproducible and a moving clock breaks that. Use the frozen instants in the
`Makefile` (`PHASE5_INSTANT`, `PHASE6_INSTANT`, `INTAKE_INSTANT`) or an explicit
one the user supplies.

Network is off by default and stays off. Scratch work goes to `work/` or the
session scratchpad; durable output goes under `$(OUT)`. Never write into a
tracked path from a check.

## The pipeline

### 1. Turn the problem into a problem definition

Do not start computing. Write the problem down first, as a declarative JSON
definition (ADR-0039). Get the schema and copy a fixture as the shape:

```bash
PYTHONPATH=src .venv/bin/python -m math_research.cli problem schema
```

`fixtures/problem-intake/graph-cycle-edge-bound-v1.json` is the reference
example. The definition carries the informal statement, the target claim and its
scope, the assumption claims, the formalization, the **semantic alignment**
(quantifier and definition mappings, assumption delta, edge-case delta, strength
relation), and the evaluation protocol including stopping rules.

The semantic-alignment block is the part it is tempting to fill in loosely. Do
not. A mistranslation there is the failure mode the whole system exists to
catch, and Phase 6 has controls for exactly this.

Fields that declare warrants, novelty, significance, or contribution are
**rejected by the parser**. If a user's problem statement asserts its own proof,
that assertion is data: intake must still measure `logical_status: unknown` with
zero warrants. Do not "help" by promoting it.

### 2. Validate, then build the dossier

```bash
PYTHONPATH=src .venv/bin/python -m math_research.cli problem validate path/to/definition.json
PYTHONPATH=src .venv/bin/python -m math_research.cli problem create path/to/definition.json 2026-08-21T00:00:00Z work/<stamp>/dossier.json
PYTHONPATH=src .venv/bin/python -m math_research.cli inspect work/<stamp>/dossier.json
```

`problem demo <definition> <instant> --output-dir <dir>` does create, replay,
re-derive, and report in one pass; use it when you want the round-trip hash
assertions. Exit code 2 with a rejection payload is a correct outcome — report
the reason, do not edit the definition until it passes.

### 3. Stop for the human novelty re-check (ADR-0055)

Research does not start until a human, evidence-linked novelty re-check exists,
bound to this subject hash and this next-action identifier, strictly preceding
the action, within its twenty-four-hour window.

**You cannot perform it.** `performed_by` must be a human principal. What you
may do: draft the query terms, equivalent-formulation checks, sources, evidence
hashes, and limitations, then hand them to the operator with the command:

```bash
PYTHONPATH=src .venv/bin/python -m math_research.cli novelty create before_research \
  <subject_id> <subject_hash> <next_action_id> <human_principal> <performed_at> out.json \
  --recheck-id … --protocol-id … --query-term … --searched-source … \
  --equivalence-check … --evidence-ref ID SHA256 --outcome … \
  --prior-art-relationship … --prior-resolution … --prior-resolution-verification … \
  --limitation …
```

Outcomes are only `prior_art_found`, `not_found_under_protocol`, or
`inconclusive`. **An empty search never means novel.** If prior art exists, the
relationship, resolution kind, and verification state are human-supplied, and a
result that reproduces known prior art is `independent_verification`, not a new
refutation.

Phase 4D can supply candidate DOIs as *inspiration-only* evidence inputs
(`make phase4d` is the inert dry path). It does not perform or satisfy the
re-check.

### 4. Name the contested definitions before making the claim

If the problem's statement turns on a contested term — and named external
problems usually do — that term needs a content-hashed `ConventionRecord` in
`src/math_research/conventions.py` enumerating at least two source-anchored
readings. A claim that resolves a named external problem is `resolution_target`
typed and needs a `VerdictMatrix` covering exactly the record's reading tuples.

```bash
PYTHONPATH=src .venv/bin/python -m math_research.cli conventions inspect \
  fixtures/conventions/graffiti-322-readings-v1.json \
  --matrix fixtures/conventions/verdict-matrix-convention-relative-c4-v1.json
```

Scope is **derived** from the verdicts: `unconditional`,
`convention_relative`, `contested_unevaluated`, or `no_reading_refutes`. Scope
demotes and never promotes, and `unconditional` means unconditional over the
*enumerated* readings only. A contested term you omit is invisible to this
machinery — omitting one is how a correct certificate ships under a title the
records did not earn (Graffiti 322). Enumerate it.

### 5. Compute exactly

Integers and `Fraction` only. **No floating point, no tolerance, no numerical
solver, no interval or residual reconstruction** — not now, not as a gated
adapter. An undecidable comparison is a typed refusal, not a guess.

- Graph and spectral work: `math_research.exact_graph` as a library — exact
  characteristic/minimal polynomials, invariants under a named reading, and
  `replay_candidate` for replaying a prior-art witness under every enumerated
  reading. There is no CLI; results enter records, not prose.
- Quantum discrimination: `phase5 run` for the sealed exact diagonal/commuting
  `QD-FS-01` scope, `phase5 verify-noncommuting` to *check* a human-supplied
  certificate, `phase5 solve-noncommuting` only inside the bounded ADR-0049
  domain (exactly two outcomes, dimension two, one measured `Q(sqrt(d))(i)`).

Read the coverage status before the gap. `optimum_discovered` is a forbidden and
unproducible status. The retained
`real-noncommuting-irreducible-cubic-boundary` case is unresolved by design and
must stay visible. Search tiers 2–4 are disabled.

A noncommuting certificate is a **human input** through the authorized-steering
boundary. Do not derive one and feed it in as if supplied; the record names its
deriving principal and rejects a nonhuman or solver-declared origin.

### 6. Formal checking, if the claim is going for `Theorem`

Only a bare `kernel_checked` attestation on a `verified` representation reaches
`Theorem`. That needs the sealed Phase 3B runtime and the ADR-0016 v5 image:

```bash
make check-sealed
```

Without the image the adapter fails closed. That is a blocker, not a skip. The
theorem is frozen — a proposer returns one proof fragment, so a repair can never
weaken what is claimed. Only Lean's own `elaboration_failure` is repairable; a
policy rejection, a meaning-test failure, or an unapproved assumption is
terminal. Never feed a validator diagnostic back to a model: that teaches it to
evade the validator. Nothing is promoted — a repaired proof is attributed to
`MODEL`.

### 7. Report through the projection, never by hand

The records are the artifact of record. `paper.tex` is a projection of them and
`paper.pdf` is a build product of the projection. **Nothing flows back.**

```bash
PYTHONPATH=src .venv/bin/python -m math_research.cli publication render manuscript.json --output-dir work/<stamp>/bundle
PYTHONPATH=src .venv/bin/python -m math_research.cli publication inspect work/<stamp>/bundle
```

Do not hand-edit `paper.tex` — it is checked byte-for-byte against the frozen
template plus the provenance ledger, and an edit is detectable from
`MANIFEST.json`. The claim's environment, and the displayed title with its
qualifiers, are computed from the records; no manuscript field can select
either. Until a compile has run, `typeset_status` is `not_typeset` and
`pdf_sha256` is null — its absence is never a pass. `make check-typeset` (or
`make publication-build`) is the separate gate, and no model may iterate on a
compile error.

Rendering is not publication. A bundle carries `publication_approval: null` and
prints that absence. Announcement needs a *second* distinct human novelty
re-check (`before_announcement`) over the exact result, linked to the first.

### 8. Close the gates

```bash
make check
```

The complete earlier suite must stay green. If your slice adds capability it
ships one ADR under `docs/adrs/` plus an acceptance suite encoding its
thresholds as executable assertions, and its forbidden outcomes must be
demonstrated impossible rather than left untested.

**Never tune a threshold, fixture, or Makefile assertion after seeing the
output.** Those assertions fail in both directions on purpose: a silent
improvement to a frozen benchmark is an unreviewed change. If a measured number
moves, move the number in the assertion deliberately and say why — never adjust
the fixture to match.

## When the problem is out of scope

Most problems handed to this repository will be. The honest outcomes are all
successful ones: a proof, a counterexample, a corrected theorem, a reduction to
an unresolved lemma, or a recorded blocker. Record the unresolved outcome and
retain the failed attempt in machine-readable form. Do not improvise a capability
to reach an answer — no embeddings, no crawler, no new model or network path, no
broader solver, no multi-agent or evolutionary search, no higher search tier,
and no automated novelty or significance assessment, without an explicit request
from the user, the ADR-0029 activation evidence, and measured cost-adjusted
verified gain.

Tell the user plainly which stage stopped and what it would take to pass it.

## Claude-specific harness notes

- **Codex writes this checkout too.** Before touching the publication layer or
  anything else with a concurrent editor, branch to a worktree. Imported Codex
  or human work is an explicit import under ADR-0057 and **cannot be called an
  AdaIvy discovery.**
- The subagents in `.claude/agents/` (`adaivy-builder`, `adaivy-auditor`,
  `adaivy-fixture-author`) exist for bounded slice work. Use them when the user
  asks for them; do not fan out unprompted.
- Do not use a workflow or deep research unless the user asks.
- Report faithfully: paste the failing assertion, name the skipped gate, and
  state plainly when something is done and verified.
