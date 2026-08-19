# Next Bounded Production Phase 3B Task After Dynamic-Input Gate v5

Read `README.md`, `TECHNICAL_BLUEPRINT.md`, `NOVELTY_LANDSCAPE.md`, all current
ADRs, the complete `reports/phase-3b-entry-gate/v4/` evidence, and the complete
`reports/phase-3b-entry-gate/v5/` evidence first.

Implement only the first production Lean formal-checking vertical slice behind
the existing `MathTool`/verifier boundaries. Reuse the exact ADR-0015 pins and
the ADR-0016 v5 image
`adaivy-phase3b-gate-v5:lean-v4.32.1@sha256:39457cf097e89537ac90e7ddee08cbda8f7f2d49e443cc60a87d6d02d8cb896f`.
Do not perform network acquisition, rebuild or expand the toolchain, change the
launcher, fixed invocation, 262,144-byte stdin bound, fixed
`/tmp/adaivy-input.lean` path, Landlock hardener, seccomp policy, Docker
controls, executable inventory, or dependency closure. Do not treat any v4 or
v5 gate fixture as a production interface. If the exact v5 runtime is absent,
mismatched, or cannot support the bounded production contract unchanged, stop
and require a fresh entry gate.

The slice may add:

- one versioned restricted theorem/proof-fragment schema;
- deterministic validation that rejects arbitrary Lean files, user-controlled
  or unknown imports, placeholders, unsafe/FFI/native/evaluation features,
  undeclared axioms, package commands, and side-effect APIs;
- one deterministic trusted-wrapper generator with exact source, target,
  declaration, import, wrapper, invocation, policy, and runtime hashes;
- one adapter invocation that sends only the generated wrapper bytes on stdin
  to the fixed v5 launcher under the accepted offline Docker/Landlock controls,
  with no source path, host mount, container copy, repository mount, secret
  environment, or user-controlled argument;
- bounded streaming stdout/stderr capture that preserves full-stream hashes and
  lengths plus bounded retained bytes, terminates the container/process group
  on wall timeout or output limit, removes the container, and distinguishes
  timeout, output-limit, and sandbox/adapter failures;
- proposal-only formal-check findings with distinct outcomes for kernel checked,
  approved standard axioms, unapproved assumptions, policy rejection,
  elaboration failure, timeout, output limit, and sandbox failure; and
- canonical persistence/replay, CLI inspection, and acceptance fixtures for
  valid, placeholder, axiom, malformed, mistranslated/meaning-test, timeout,
  output-limit, and sandbox cases.

The adapter must never approve semantic alignment, source applicability,
novelty, significance, contribution, or an `EpistemicWarrant`. A kernel-checked
result applies only to the exact hashed statement, wrapper, imports, runtime,
and disclosed assumptions. Meaning tests are diagnostic and cannot promote
trust. Imported or model-created proof text remains an untrusted proposal.

Keep all Phase 0-3A behavior and hashes compatible. Preserve failed attempts
and bounded raw diagnostics in machine-readable records. Run all existing tests
and validators plus the new validation, wrapper-hash, dynamic-stdin adapter,
restart/replay, sandbox, placeholder/axiom, meaning-test, timeout, output-limit,
and zero-network/model/API tests. Run Phase 3A acceptance against a disposable
workspace so verification adds no tracked working-tree drift.

Do not add Why3, SMT, CAS, interval or optimization adapters, premise retrieval,
proof search or repair, model/API calls, multi-agent orchestration, a web/HTTP
surface, crawling, embeddings, PDF parsing, broader Phase 3B workflows, Phase
4, or quantum convergence work. Do not commit, tag, push, or publish unless a
later request explicitly authorizes it.
