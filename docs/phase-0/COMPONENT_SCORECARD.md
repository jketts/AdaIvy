# Phase 0 Component Scorecard

This file defines the corrected interpretation of the frozen Phase 0
observations. The raw run remains unchanged in `reports/phase-0/results.json`
(SHA-256 `e8166fed8063ade26d74b55f0139fc2adfd2900d2c8db4a4c3fb8c4a5b144533`).
ADR-0004 explains why the original aggregate score was invalid.

## Evaluation dimensions

Each candidate is reported using independent dimensions:

- **evaluation status:** whether a selected integration actually executed;
- **runnability:** runnable, unavailable on the host, or not attempted;
- **measured capability:** only capabilities exercised on the common fixture;
- **integration effort:** setup/review cost observed during an execution;
- **evidence completeness:** complete, partial, or no execution evidence;
- **license status:** verified, unresolved, absent, restrictive, or not
  applicable;
- **blockers:** preserved hard gates and missing prerequisites.

Blocked and deferred candidates are **not evaluated**. Their
`capability_score` and baseline comparison are `null`, not zero and not low.
License and maintenance observations remain visible but never contribute to a
capability score.

For executed candidates, each measured capability criterion retains the frozen
`0`/`1`/`2` observation:

| Criterion | Weight | Required evidence |
|---|---:|---|
| Target fidelity | 3 | Target and approved-alignment identifiers/meaning survive round-trip |
| Applicability separation | 3 | Citation existence and mathematical applicability remain distinct |
| Obligations and failed routes | 3 | Open gaps and failures export and replay |
| Evidence/warrant typing | 3 | Unlike evidence cannot silently promote status |
| Exportability | 2 | Machine-readable complete artifact export |
| Replay determinism | 2 | Clean second run matches semantic output hash |
| Verifier isolation/reconstruction | 2 | Inputs can be enumerated without proposer narrative |
| Local/offline operation | separate | Runnability dimension |
| License clarity | separate | License-status dimension |
| Maintenance evidence | separate | Evidence-completeness context |
| Security boundary | separate | Runnability/integration context |
| Setup/review cost | separate | Integration-effort dimension |

`capability_score` is `sum(score × weight) / (2 × sum(weights)) × 100` over the
first seven capability rows only. It does not override a blocker.

## Hard gates

A component cannot be recommended for direct adoption if any applies:

- license is absent, incompatible, or unverified;
- accepted state cannot be exported without loss;
- it can mutate trusted verdicts without a local validation boundary;
- the reference run cannot be reproduced or its version cannot be fixed;
- it requires sending dossier contents to an undisclosed service;
- failed routes or open obligations are silently discarded.

## Baseline comparison

The file baseline is scored by the same capability rubric. Only executed
candidates receive a numeric comparison. Candidates must state the specific
capability they add over it and their additional dependency, operational, and
review cost. Equal or lower measured capability may still justify
interoperation for a specialized verifier, but not replacement of the canonical
interchange.

## Decision vocabulary

- **Adopt:** direct dependency; passes all hard gates and materially beats the
  baseline.
- **Wrap:** useful local capability behind a narrow adapter; canonical state
  stays in the dossier.
- **Interoperate:** external system owns its state; exchange only dossier and
  candidate-result envelopes.
- **Build:** implement the demonstrated missing capability locally in Phase 1+
  with an ADR citing the failed alternatives.
- **Defer:** insufficient evidence or no Phase 1 need.

Corrected results live in `reports/phase-0/scorecard.md` and
`reports/phase-0/evaluation-correction.json`. The historical observations remain
in `reports/phase-0/results.json` and are not rewritten.
