# Dependency and License Policy

## Purpose

Phase 0 must remain reproducible and legally reviewable while probing immature
research systems. Adding a package is an architectural decision, not a shortcut
around a ten-line standard-library implementation.

## Dependency rules

1. The evaluation harness and schema validator use the Python standard library.
2. External components run through bounded subprocess adapters or isolated
   optional environments; they are not imported into the canonical harness.
3. Every direct dependency must have an exact version, upstream URL, retrieved
   artifact hash, license identifier, reason, owner, and removal path.
4. Lockfiles are committed when a package manager is introduced. Floating Git
   branches, unpinned containers, and mutable download URLs are prohibited in
   reproducible results.
5. Optional spikes must report `blocked` when their executable/package is
   missing. Checks may not auto-install or access the network.
6. External commands run with a timeout, explicit working directory, captured
   output, minimal environment, and network disabled where the platform permits.
7. No credentials, user home configuration, or globally installed plugin state
   may be required for the baseline.

## License rules

- Record license facts only from a repository license file, package metadata,
  standards body, or official project documentation.
- `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `Apache-2.0`, `ISC`, and similarly
  permissive licenses are normally acceptable for evaluation.
- Weak/strong copyleft, source-available, research-only, non-commercial, custom,
  or missing licenses require an ADR and human review before distribution or a
  production dependency decision.
- A paper, website, or hosted service without reusable code is inventoried as
  `artifact/service`, not “open source.”
- Dataset, model-weight, paper-text, and software licenses are recorded
  separately; one does not imply another.
- Preserve copyright notices and attribution required by any exported fixture.

## Security and supply chain

- Prefer signed releases or immutable commit hashes and verify SHA-256 hashes.
- Generate a dependency/license inventory for any adopted package.
- Do not execute code fetched during a check run.
- Treat component output as untrusted; validate it against the result schema.
- Quarantine partial outputs and retain stderr/failure metadata.
- Components that require unrestricted network, inherited secrets, or execution
  outside a bounded workspace fail the Phase 0 security hard gate.

## Approval record

The component inventory records `evaluation_allowed`, `distribution_allowed`,
and `production_decision`. Phase 0 evaluation is not production approval.
