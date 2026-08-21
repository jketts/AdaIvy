# ADR-0054: Cite the original problem, render an auditable derivation, and explain AdaIvy

- **Status:** accepted for the publication projection
- **Date:** 2026-08-21
- **Blueprint requirement:** Sections 12.4, 15, 16 and 19; ADR-0036 publication
  closure; ADR-0052 AI and formal-artifact disclosure
- **Decision owners:** repository owner and researcher

## Context

A solved result can be mathematically correct yet difficult for a new reader to
evaluate if the paper does not identify the original problem, says only that a
model found it, or uses internal status language such as "awaiting human review"
without explanation. Search-derived influences also require the same acquisition
and passage discipline as any other factual dependency.

Private model chain-of-thought is neither a stable research artifact nor
independently checkable evidence. What a paper needs is an auditable derivation:
the concise mathematical steps a reader can reproduce, the computations and
formal checks those steps rely on, and citations for ideas or statements that
came from retrieved sources.

## Decision

Every claim record gains `original_problem_citation_id` and `derivation`.
A claim whose computed evidence class is not `proposal` is refused unless:

1. `original_problem_citation_id` resolves to a `source_record` citation whose
   cited object is `problem` and whose located passage and publication rights
   pass the existing acquisition boundary; and
2. `derivation.status` is `included` with a nonempty plain-language summary.

Derivation citations use the existing citation registry. A retrieved-source
influence therefore reaches the paper only through an acquisition record,
content hash, rights decision, and—where it attributes a problem, theorem,
lemma, definition, or hypothesis—a located passage. Unrecorded influence remains
an open obligation and cannot be rendered as a citation.

The derivation is explicitly an auditable reconstruction, not private model
chain-of-thought. It should state mathematical reductions, case splits,
calculations, experiments, and formal checks at the level needed for a reader to
reproduce the result. It must not invent introspective claims about hidden model
states.

Every generated paper ends with an unsuppressible final footnote explaining
that AdaIvy is an open-source AI-assisted mathematical research project with
separate retrieval, computation, formal-checking, human-review, and publication
boundaries, and links to `https://github.com/jketts/AdaIvy`.

Every manuscript also carries a mandatory run disclosure: provider/model
identifiers, call counts, measured USD cost, authorized cost cap, input tokens,
output tokens, total tokens, measurement scope, and whether the accounting is
complete, partial, or unavailable. Counts and amounts may be null only when the
paper prints that they were not recorded; they are never estimated. Token totals
must close arithmetically and model call totals must equal the per-model rows.

Reader-facing review language must be plain: "the mathematical result has not
yet been approved by a human reviewer; automated checks alone do not make it an
endorsed result." A machine status may follow parenthetically for auditability.

## Consequences and gates

- A solved result cannot be published without identifying the problem it
  answers or without showing reproducible reasoning.
- Bibliography closure now includes original-problem and derivation citations.
- Two falsifiability probes remove the original-problem citation and derivation
  status independently; both must produce their named refusals.
- The final project note is renderer-owned, ledger-backed, and cannot be removed
  by a manuscript field.
- No warrant, novelty assessment, significance assessment, or publication
  approval is created by these disclosures.

## Revisit trigger

Revisit before accepting an unlocated original problem, rendering model
chain-of-thought, bypassing acquisition rights for attribution, allowing a
manuscript to suppress or replace the project footnote, or treating an auditable
derivation as formal proof.

Presentation clarification (2026-08-21): located source references are rendered
as conventional LaTeX citations with their passage anchor as the citation
locator. The paper's run disclosure reports usage-bearing models, completed
calls, cost, and tokens; low-level transport and authorization failures remain
in machine-readable run evidence and are not projected into the paper.
