# ADR-0004: Correct Phase 0 scorecard without rewriting observations

- Status: accepted
- Date: 2026-08-19
- Deciders: repository maintainers
- Scope: Phase 0 evaluation reporting

## Context

The Phase 0 raw result mixed measured capability with license clarity,
maintenance evidence, security posture, and setup cost. A missing executable or
deferred spike therefore appeared as a low numeric performer even though no
capability evaluation had executed. This confuses absence of evidence with
negative evidence.

## Decision

Keep `reports/phase-0/results.json` immutable as the raw observation record and
derive a versioned correction artifact from it. Report evaluation status,
runnability, capability, integration effort, evidence completeness, license
status, and blockers independently. Set capability and baseline comparison to
`null` unless the candidate integration executed. Capability scores use only
the seven frozen capability criteria.

## Consequences

Only the file baseline and OMDoc projection have numeric capability results in
the completed run. Blocked and deferred systems remain candidates with explicit
blockers; they are not ranked below the baseline. Historical aggregate scores
remain inspectable in raw evidence but are deprecated for decisions.

## Alternatives rejected

- Re-running the original harness would overwrite timing/environment evidence.
- Treating blockers as zero would continue to claim an evaluation that did not
  occur.
- Deleting the historical aggregate would weaken auditability.
