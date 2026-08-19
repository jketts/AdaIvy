# Phase 0 Outcome and Phase 1 Proposal

## Outcome

Phase 0 fixed a minimal, hash-stable ResearchDossier and external
`BackendResult` contract, implemented a dependency-free evaluation harness,
created positive and adversarial fixtures, and compared nineteen candidates or
reference approaches against one file baseline. It did not implement any
production domain, database, crawler, UI, model orchestration, or quantum
research code.

Raw observations are preserved in `reports/phase-0/results.json`; their
corrected interpretation is authoritative in `reports/phase-0/scorecard.md` and
`reports/phase-0/evaluation-correction.json`. The key outcomes are:

- file baseline: **100.0 measured capability**, executed successfully;
- OMDoc concept projection: **69.4 measured capability**, executed partially
  and sidecar-dependent;
- every blocked or deferred candidate: **not evaluated**, with
  `capability_score: null` and its original blockers retained;
- licenses, runnability, effort, and evidence completeness are reported as
  independent dimensions rather than folded into capability.

The three adversarial fixtures passed: target drift, inapplicable citation, and
experimental overreach are rejected. The backend-result fixture also proves
that external artifacts must retain `proposal` disposition.

No model calls or paid services were used. Wall time and external-process count
are recorded per component. Expert mathematical review was not performed in
Phase 0 and is explicitly stored as `null`, rather than reported as zero effort.

## Adopt/wrap/interoperate/build recommendations

No external candidate is recommended for direct adoption in Phase 1.

- **Build:** only the Phase 1 trust core and manual in-memory slice, using the
  fixed dossier semantics. The Phase 0 file baseline remains the comparison and
  interchange fixture, not production persistence.
- **Wrap later:** Why3 and Lean in Phase 3; PaperQA2 in Phase 4. Their tool
  outputs must enter as evidence/proposals through narrow adapters.
- **Interoperate later:** Albilich proof state, OMDoc mathematical content, and
  possibly Eigenius typed artifacts. MMT requires legal review.
- **Defer:** MathGraph pending a license; LeanDojo/LeanSearch pending benchmark
  and environment fit; ASTRA, RMA, Aletheia, AlphaProof Nexus, ProofAtlas,
  FunSearch, and AlphaEvolve until a lower-phase need and runnable artifact
  exist.

## Unresolved decisions

1. Repository license and version-control initialization.
2. Albilich’s exact stable import/export surface and whether interoperation is
   worth its orchestration/model cost.
3. Whether a conformant OMDoc/MMT adapter can preserve trust metadata without a
   JSON sidecar, plus MMT licensing treatment.
4. Phase 1 schema primitive (Pydantic-style dependency versus a smaller local
   validated type layer) and its license/lockfile.
5. Pinned Why3 prover and Lean toolchain; both remain Phase 3 decisions.
6. PaperQA2 local-model/index configuration and copyright policy; Phase 4.
7. First proof assistant, graph database, job engine, UI, and search-tier policy
   remain open exactly as scheduled by the blueprint.

## Evidence-backed Phase 1 proposal

Proceed with the blueprint’s Phase 1 trust core and manual vertical slice, with
no external research-system dependency:

1. Implement typed in-memory entities only for semantic alignment, claims,
   source applicability, orthogonal warrants, proof obligations, frozen
   evaluation protocols, verifier manifests, and append-only events.
2. Import/export the frozen dossier and external-result envelopes without
   weakening their proposal-only boundary.
3. Implement policy projections that reject the three demonstrated adversarial
   cases plus formally-proved-wrong-target, premise-smuggling, and verifier
   contamination fixtures.
4. Provide a manual CLI for constructing and auditing one dossier and rendering
   a claim-linked report. Do not add a database, workers, model provider, crawler,
   or external research backend.
5. Add property tests for append-only records, orthogonal trust dimensions,
   assumption references, source-span provenance, and confirmatory immutability.

This proposal is supported by the only successful local result: files can
preserve the complete trust boundary and replay deterministically. No external
candidate demonstrated a safe replacement, and the OMDoc spike showed that a
math representation alone does not carry the required epistemic governance.

Phase 1 exit should require one complete in-memory manual dossier, every report
sentence linked to a claim, and explicit rejection of a formally valid but
semantically wrong target and a real-but-inapplicable citation. External
integration work should remain out of Phase 1 until the recorded blockers are
resolved.
