# Proposed Next Bounded Phase 3B Task

Do not begin the production Phase 3B domain model or orchestration.

First obtain explicit authorization for a networked acquisition-only step.
Acquire elan v4.2.1, Lean `leanprover/lean4:v4.32.1`, and mathlib v4.32.1 into a
disposable local environment without Homebrew or shell-startup edits. Resolve
and record full commits, `lake-manifest.json`, licenses, download/source/binary
hashes, and actual download/expanded sizes. Do not fetch during checking.

Provide or select an OS/container sandbox that demonstrably enforces:

- no network and no inherited secrets;
- no repository or home-directory access;
- read-only pinned toolchain/dependencies;
- one disposable writable run directory;
- CPU, wall, memory, process, output, and file-count/size limits;
- command and import allowlists; and
- process-group termination and cleanup.

Then implement only an entry-gate spike around a generated trusted Lean wrapper
and the twelve synthetic fixtures in `FIXTURE_RESULTS.md`. The spike must retain
raw bounded diagnostics, exact warnings, `#print axioms`, source/wrapper/
toolchain/invocation hashes, and canonical classifications from
`TRUST_CLASSIFICATION_POLICY.md`. Static scanning is defense in depth, not the
sandbox.

Run every fixture twice and once after a clean restart with network disabled.
Prove that timing/PID/temp paths do not affect canonical hashes. Run all existing
Phase 0–3A tests, validators, seal/hash checks, and credential scans again.

Stop and report blocked if any of the following remains unreliable:

- placeholder or axiom detection;
- exact declaration/target identification;
- sandbox network/filesystem/process containment;
- deterministic canonical result replay;
- dependency pinning or licensing.

If and only if this rerun passes, amend ADR-0015 to accepted and propose a
separate production-adapter task. Do not add Why3, SMT, other proof assistants,
models, autonomous proof generation, or quantum convergence work.
