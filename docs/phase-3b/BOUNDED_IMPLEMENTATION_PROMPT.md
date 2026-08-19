# Next Bounded Production Phase 3B Task

Read `README.md`, `TECHNICAL_BLUEPRINT.md`, `NOVELTY_LANDSCAPE.md`, all current
ADRs, and the complete `reports/phase-3b-entry-gate/v4/` evidence first.

Implement only the first production Lean formal-checking vertical slice behind
the existing `MathTool`/verifier boundaries. Reuse the exact accepted pins and
the sealed shell-free runtime manifest from entry-gate repair v4. Do not perform
network acquisition, rebuild or expand the toolchain, change the Landlock or
seccomp policy, or treat the twelve gate fixtures as a production interface. If
the sealed runtime cannot support the bounded production input contract without
a policy or runtime change, stop and require a fresh entry gate.

The slice may add:

- one versioned restricted theorem/proof-fragment schema;
- deterministic validation that rejects arbitrary Lean files, unknown imports,
  placeholders, unsafe/FFI/native/evaluation features, and undeclared axioms;
- one deterministic trusted-wrapper generator with exact source, target,
  declaration, import, wrapper, invocation, policy, and runtime hashes;
- one adapter invocation of the fixed launcher under the accepted offline
  Docker/Landlock controls and bounded diagnostics;
- proposal-only formal-check findings with distinct outcomes for kernel checked,
  approved standard axioms, unapproved assumptions, policy rejection,
  elaboration failure, timeout, output limit, and sandbox failure; and
- canonical persistence/replay, CLI inspection, and acceptance fixtures for
  valid, placeholder, axiom, malformed, mistranslated/meaning-test, and resource
  cases.

The adapter must never approve semantic alignment, source applicability,
novelty, significance, contribution, or an `EpistemicWarrant`. A kernel-checked
result applies only to the exact hashed statement and assumptions. Meaning tests
are diagnostic and cannot promote trust.

Keep all Phase 0–3A behavior and hashes compatible. Run all existing tests and
validators plus the new adapter, restart/replay, sandbox, placeholder/axiom,
meaning-test, and zero-network/API tests. Preserve failed attempts and bounded
raw stdout/stderr in machine-readable records.

Do not add Why3, SMT, CAS, interval or optimization adapters, premise retrieval,
proof search or repair, model/API calls, multi-agent orchestration, a web/HTTP
surface, crawling, embeddings, PDF parsing, broader Phase 3B workflows, Phase 4,
or quantum convergence work. Do not commit, tag, push, or publish unless a later
request explicitly authorizes it.
