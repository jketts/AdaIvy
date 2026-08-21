# ADR-0056: Automatically produce every solved-result report as a classic LaTeX bundle

- **Status:** accepted and implemented 21 August 2026
- **Date:** 2026-08-21
- **Blueprint requirement:** C9, C15, C19; Sections 15.3 and 19; ADR-0036,
  ADR-0052, ADR-0053, and ADR-0055
- **Decision owners:** repository owner and researcher

## Context

AdaIvy already had the pieces of a safe publication path: manuscript records,
a deterministic LaTeX projection, mandatory Lean artifacts for solved claims,
and a pinned reproducible PDF compiler.  They were exposed as separate commands.
That allowed a solved-result report to be written and converted with an
unrelated PDF library, bypassing the projection, ledger, linked Lean artifact,
classic-paper layout, pinned compiler, and manifest.  The Graffiti 322 draft
demonstrated this failure while the earlier Graffiti 197 paper followed the
intended structure.

Diagnostic phase reports are not mathematical papers.  Requiring every JSON or
Markdown gate report to masquerade as one would destroy their machine-readable
role.  The relevant invariant is therefore every **reader-facing solved-result
report**, meaning a manuscript projection containing at least one claim whose
computed evidence class is not `proposal`.

## Options considered

| Option | Evidence | Benefits | Costs/risks | Hard gates |
|---|---|---|---|---|
| Permit ad hoc PDF renderers | The first Graffiti 322 PDF was readable | Fast | Bypasses the publication ledger and reproducibility contract | Rejected |
| Keep render and typeset as unrelated manual commands | ADR-0036/0053 implementation | Existing primitives remain useful | A caller can stop after TeX or substitute another PDF | Retained only as low-level diagnostic commands |
| Add one automatic record-to-PDF command | Existing projection and pinned compiler compose without a new dependency | One fail-closed path emits records, TeX, Lean, manifest, and PDF | Requires the optional pinned TeX toolchain | Selected |

## Decision

`adaivy publication build MANUSCRIPT --output-dir DIR` is the supported
reader-facing publication command.  It performs, in one invocation:

1. strict manuscript validation and falsifiability probes;
2. deterministic projection to `paper.tex` from the records;
3. materialization of one content-hashed `.lean` file for every solved claim;
4. two clean, offline, `-no-shell-escape` compilations with the exact ADR-0053
   BasicTeX engine;
5. byte-identity comparison of the two PDFs; and
6. post-typeset verification of every file against `MANIFEST.json`.

The output directory must be fresh.  The command fails if the typesetter is
absent, the probe set is empty, a solved claim lacks its source citation,
auditable derivation, or Lean artifact, either compile fails, references are
undefined, PDF bytes differ, or final bundle verification fails.

The frozen publication template now uses the same classic 11-point `article`,
letter-sized page, Computer Modern, margins, paragraph spacing, theorem style,
status disclosure, citations, run disclosure, linked Lean artifact, and project
footer established by the Graffiti 197 paper.  Hand-written or alternative
PDF renderers are not a supported AdaIvy publication path.

The status block states successful Lean artifact checks before the computed
claim class and explicitly distinguishes a kernel-checked supporting artifact
from a completely represented, kernel-checked theorem.  Source citations in
article prose use only ordinary numeric markers such as `[1]`; titles,
identifiers, located-passage anchors, acquisition hashes, and other source
details appear in the References entry generated from the source records.

`make report`, the durable report command, now invokes the automatic build for
its publication component.  Consequently `make report` requires the pinned
typesetter; `make check` remains offline and dependency-free and continues to
test the uncompiled projection.  Low-level `publication render` and
`publication typeset` commands remain available for inspection and gate
diagnosis, not as the normal reader-facing workflow.

Novelty remains orthogonal.  Automatic paper production occurs for a solved
claim whether novelty is assessed or not, and the paper prints the exact status.
Publication approval still requires ADR-0055's distinct human
`before_announcement` re-check.  Producing a PDF neither claims priority nor
announces a result.

## Consequences

- Every AdaIvy-produced solved-result paper has the same artifact structure and
  can no longer silently omit its LaTeX source, Lean source, records, or hashes.
- The final PDF is always derived by the pinned LaTeX path; an attractive but
  untracked PDF is not accepted as an AdaIvy publication report.
- Durable report generation now fails closed when the optional typesetter is
  missing instead of quietly emitting an incomplete publication artifact.
- Gate, diagnostic, acquisition, and machine-readable phase reports remain in
  their native JSON/Markdown forms and are explicitly outside this paper
  contract.
- No correctness, novelty, significance, applicability, or publication warrant
  is created by rendering or typesetting.

## Blueprint deviation

The earlier roadmap treated PDF compilation as a manually separate gate.  This
ADR retains that separation for `make check`, but composes projection and the
gate atomically for durable reader-facing report production.  This is necessary
to prevent a report from being presented without having traversed the gate.

## Validation and revisit trigger

The acceptance suite must demonstrate that:

1. the automatic command writes `paper.tex`, `paper.pdf`, `MANIFEST.json`, and
   `build.json` in one fresh bundle;
2. every solved claim still emits and links its exact `.lean` source;
3. a nonempty output directory, empty falsifiability suite, absent or mismatched
   typesetter, compile failure, non-reproducible PDF, or post-build hash mismatch
   fails closed;
4. the template retains the Graffiti 197 classic-paper layout and package set;
5. `make report` uses the automatic command while `make check` performs no PDF
   compile; and
6. no module in `src/` imports an alternative PDF-generation library.

Revisit before admitting a second publication layout, a non-LaTeX PDF engine,
automatic publication approval, automatic novelty claims, or PDF compilation
inside the ordinary offline `make check` path.
